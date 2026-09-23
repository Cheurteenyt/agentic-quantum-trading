#!/usr/bin/env python3
"""Registre X — phase 3 : scoring des calls contre les klines reelles.

Le principe : un call sans consequence verifiee n'est qu'une opinion. Ce
script rejoue chaque call parse du registre contre le warehouse klines :

  - resolution de la date du post (les horodatages X sont relatifs ou ambigus)
  - prix d'entree = prix declare s'il existe, sinon close au moment du post
  - rendements forward directionnels a +1h / +24h / +7j (short = retour inverse)
  - rapport d'honnetete horodate dans reports/

Idempotent : chaque run re-score (les horizons se remplissent quand la data
arrive, comme les candidats murissent en 30 jours). Le registre mesure les
comptes, pas le marche ; il ne prouve aucun edge, il tient le score.

    python scripts/score_x_calls.py --score
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.onchain.aster.aster_perps_model import (  # noqa: E402
    taker_fee_bps_for_symbol,
)
from scripts.fetch_klines import init_db as init_klines_db  # noqa: E402
from scripts.fetch_klines import load_bars  # noqa: E402
from scripts.fetch_x_posts import DB_PATH, _connect  # noqa: E402

REPORTS = ROOT / "reports"
ENGINE_VERSION = "v0-horizons"
HORIZONS_H = {"ret_1h": 1, "ret_24h": 24, "ret_7d": 168}

DEPTH_URL = "https://fapi.asterdex.com/fapi/v1/depth"
SPREAD_BPS_LIMIT = 20.0  # seuil legacy microstructure (spread top-10)


def _live_spread_bps(symbol_pair: str) -> float | None:
    """Spread top-10 live en bps (même mesure que le gate legacy)."""
    try:
        req = urllib.request.Request(
            f"{DEPTH_URL}?symbol={symbol_pair}&limit=10",
            headers={"User-Agent": "trading-agent/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.load(resp)
        bid, ask = float(d["bids"][0][0]), float(d["asks"][0][0])
        mid = (bid + ask) / 2.0
        return (ask - bid) / mid * 10000.0
    except Exception:  # noqa: BLE001 — un symbole injoignable ne bloque pas le rapport
        return None


def tradability(symbols: set[str], spread_fetch=_live_spread_bps) -> dict[str, dict]:
    """Tradabilité réelle par symbole : spread top-10 live + frais taker Aster.

    Le registre mesure les COMPTES (la prédiction) ; la tradabilité est un
    autre regard : un call parfait sur un marché à 200 bps de spread n'était
    pas encaissable. Renvoie {base: {spread_bps, fee_bps, collectionnable}}.
    """
    out: dict[str, dict] = {}
    for base in sorted({(s or "").upper() for s in symbols if s}):
        pair = f"{base}USDT"
        spread = spread_fetch(pair)
        out[base] = {
            "spread_bps": round(spread, 1) if spread is not None else None,
            "fee_bps": taker_fee_bps_for_symbol(pair),
            "collectionnable": spread is not None and spread < SPREAD_BPS_LIMIT,
        }
    return out

SCORES_SCHEMA = """
CREATE TABLE IF NOT EXISTS x_call_scores (
    call_id        INTEGER PRIMARY KEY REFERENCES x_calls(call_id),
    posted_at      TEXT,
    entry_resolved REAL,
    ret_1h         REAL,
    ret_24h        REAL,
    ret_7d         REAL,
    status         TEXT NOT NULL,
    scored_at      TEXT NOT NULL,
    engine_version TEXT NOT NULL
);
"""

VERDICTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS x_call_verdicts (
    call_id        INTEGER PRIMARY KEY REFERENCES x_calls(call_id),
    verdict        TEXT NOT NULL,
    resolved_ts    TEXT,
    engine_version TEXT NOT NULL,
    scored_at      TEXT NOT NULL
);
"""

MONTHS = {
    "janv": 1, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6,
    "juil": 7, "aout": 8, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _norm_month(token: str) -> int | None:
    t = unicodedata.normalize("NFKD", token.strip().rstrip("."))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return MONTHS.get(t[:4])


def resolve_posted_at(raw: str | None, fetched_at: str) -> str | None:
    """Resout l'horodatage X (relatif ou date courte) en ISO UTC.

    Ambiguite classique de X : '16 sept.' sans annee = annee courante, sauf
    si la date resulte dans le futur (post de l'annee passee) — on retranche
    un an plutot que de croire a un post venu du futur.
    """
    if not raw:
        return None
    # ISO deja resolu (harvester headless) : pass-through
    if re.match(r"\d{4}-\d{2}-\d{2}T", raw.strip()):
        return raw.strip()
    now = datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    text = raw.strip().lower()
    rel = re.match(
        r"il y a (\d+)\s*(seconde|minute|heure|jour|semaine)s?", text
    )
    if rel:
        n, unit = int(rel.group(1)), rel.group(2)
        delta = {
            "seconde": timedelta(seconds=n), "minute": timedelta(minutes=n),
            "heure": timedelta(hours=n), "jour": timedelta(days=n),
            "semaine": timedelta(weeks=n),
        }[unit]
        return (now - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
    abs_m = re.match(r"(\d{1,2}) (\w{3,5})\.?(?: (\d{4}))?$", text)
    if abs_m:
        day, month = int(abs_m.group(1)), _norm_month(abs_m.group(2))
        if not month:
            return None
        year = int(abs_m.group(3)) if abs_m.group(3) else now.year
        try:
            dt = datetime(year, month, day, 12, 0, tzinfo=timezone.utc)
        except ValueError:
            return None
        if dt > now + timedelta(days=1):
            dt = dt.replace(year=year - 1)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def _forward_close(bars, posted_ms: int, hours: int):
    """Premiere bougie ouvrant a ou apres posted_ms + hours."""
    target = posted_ms + hours * 3_600_000
    for b in bars:
        if b.ts >= target:
            return b.close
    return None


def _entry_close(bars, posted_ms: int):
    """Close de la derniere bougie ouvrant avant le post (prix au moment du call)."""
    entry = None
    for b in bars:
        if b.ts > posted_ms:
            break
        entry = b.close
    return entry


def score_all() -> dict:
    con = _connect()
    con.executescript(SCORES_SCHEMA)
    kcon = init_klines_db()
    universe = {
        r[0] for r in kcon.execute("SELECT DISTINCT symbol FROM klines").fetchall()
    }
    rows = con.execute(
        """
        SELECT c.call_id, c.symbol, c.direction, c.entry_price, c.confidence,
               p.author_handle, p.posted_at_raw, p.fetched_at, p.metrics
        FROM x_calls c JOIN x_posts p ON p.post_id = c.post_id
        WHERE c.call_id IN (
            SELECT MAX(call_id) FROM x_calls GROUP BY post_id
        )
        """
    ).fetchall()
    stats = {"scored": 0, "partiel": 0, "hors_univers": 0, "date_unparseable": 0, "pas_de_prix": 0}
    scored_rows = []
    for (call_id, sym, direction, entry_declared, confidence,
         handle, posted_raw, fetched_at, metrics_raw) in rows:
        pair = f"{(sym or '').upper()}USDT"
        if pair not in universe:
            stats["hors_univers"] += 1
            con.execute(
                "INSERT OR REPLACE INTO x_call_scores VALUES (?,?,?,?,?,?,?,?,?)",
                (call_id, None, None, None, None, None, "hors_univers",
                 _utc_now(), ENGINE_VERSION),
            )
            continue
        posted_at = resolve_posted_at(posted_raw, fetched_at)
        if not posted_at:
            stats["date_unparseable"] += 1
            con.execute(
                "INSERT OR REPLACE INTO x_call_scores VALUES (?,?,?,?,?,?,?,?,?)",
                (call_id, None, None, None, None, None, "date_unparseable",
                 _utc_now(), ENGINE_VERSION),
            )
            continue
        if direction not in ("long", "short"):
            # v3.1 : direction "exit" (sold/selling/trimmed) = distribution,
            # PAS un short. Scoré comme short ce serait mentir.
            stats["exit_ignores"] = stats.get("exit_ignores", 0) + 1
            continue
        posted_iso = re.sub(r"\.\d+Z$", "Z", posted_at.strip())
        posted_ms = int(
            datetime.strptime(posted_iso, "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=timezone.utc).timestamp() * 1000
        )
        bars = load_bars(kcon, pair, "1h")
        entry = entry_declared or _entry_close(bars, posted_ms)
        if not entry:
            stats["pas_de_prix"] += 1
            con.execute(
                "INSERT OR REPLACE INTO x_call_scores VALUES (?,?,?,?,?,?,?,?,?)",
                (call_id, posted_at, None, None, None, None, "pas_de_prix",
                 _utc_now(), ENGINE_VERSION),
            )
            continue
        sign = 1.0 if direction == "long" else -1.0
        rets = {}
        for col, hours in HORIZONS_H.items():
            close = _forward_close(bars, posted_ms, hours)
            rets[col] = (close / entry - 1.0) * sign if close else None
        complete = all(v is not None for v in rets.values())
        stats["partiel" if not complete else "scored"] += 1
        con.execute(
            "INSERT OR REPLACE INTO x_call_scores VALUES (?,?,?,?,?,?,?,?,?)",
            (call_id, posted_at, entry, rets["ret_1h"], rets["ret_24h"],
             rets["ret_7d"], "partiel" if not complete else "scored",
             _utc_now(), ENGINE_VERSION),
        )
        try:
            _m = json.loads(metrics_raw) if metrics_raw else {}
        except Exception:  # noqa: BLE001
            _m = {}
        scored_rows.append({
            "call_id": call_id,
            "handle": handle, "symbol": sym, "direction": direction,
            "entry_declared": entry_declared, "entry": entry,
            "confidence": confidence, **rets,
            "views": int(_m.get("views") or 0),
            "bookmarks": int(_m.get("bookmarks") or 0),
        })
    con.commit()
    posts_total = con.execute("SELECT COUNT(*) FROM x_posts").fetchone()[0]
    accounts_total = con.execute(
        "SELECT COUNT(*) FROM x_accounts WHERE active = 1"
    ).fetchone()[0]
    con.close()
    kcon.close()
    stats["posts"] = posts_total
    stats["comptes"] = accounts_total
    return {"stats": stats, "rows": scored_rows}


def _first_hit(bars, posted_ms: int, direction: str, tp: float, sl: float):
    """Premier touch de TP ou SL sur les bougies reelles.

    TP et SL touches dans la MEME bougie = indecis : connaitre l'ordre
    intra-bougie est impossible, et deviner serait mentir.
    """
    for b in bars:
        if b.ts <= posted_ms:
            continue
        if direction == "long":
            hit_tp, hit_sl = b.high >= tp, b.low <= sl
        else:
            hit_tp, hit_sl = b.low <= tp, b.high >= sl
        if hit_tp and hit_sl:
            return "indecis", b.ts
        if hit_tp:
            return "win", b.ts
        if hit_sl:
            return "loss", b.ts
    return "en_cours", None


def trade_verdicts() -> dict:
    """Verdicts 'replay du trade' pour les calls qui donnent TP et SL.

    Un call avec TP/SL n'est plus une opinion directionnelle : c'est un
    ordre qu'on rejoue bougie par bougie. Sans TP/SL, le verdict reste
    horizons (retours directionnels).
    """
    con = _connect()
    con.executescript(VERDICTS_SCHEMA)
    kcon = init_klines_db()
    rows = con.execute(
        """
        SELECT c.call_id, c.symbol, c.direction, c.tp_price, c.sl_price,
               s.entry_resolved, s.posted_at
        FROM x_calls c
        LEFT JOIN x_call_scores s ON s.call_id = c.call_id
        WHERE c.call_id IN (
            SELECT MAX(call_id) FROM x_calls
            WHERE tp_price IS NOT NULL AND sl_price IS NOT NULL
            GROUP BY post_id
        )
        """
    ).fetchall()
    counts: dict[str, int] = {}
    for (call_id, sym, direction, tp, sl, entry_resolved, posted_at) in rows:
        entry = entry_resolved
        resolved_ts = None
        if direction not in ("long", "short"):
            verdict = "exit_ignores"
        elif not entry or not posted_at:
            verdict = "sans_entree"
        elif direction == "long" and not (sl < entry < tp):
            verdict = "incoherent"
        elif direction == "short" and not (tp < entry < sl):
            verdict = "incoherent"
        else:
            posted_iso = re.sub(r"\.\d+Z$", "Z", posted_at.strip())
            posted_ms = int(
                datetime.strptime(posted_iso, "%Y-%m-%dT%H:%M:%SZ")
                .replace(tzinfo=timezone.utc).timestamp() * 1000
            )
            bars = load_bars(kcon, f"{sym.upper()}USDT", "1h")
            verdict, hit_ts = _first_hit(bars, posted_ms, direction, tp, sl)
            resolved_ts = (
                datetime.fromtimestamp(hit_ts / 1000, tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                if hit_ts else None
            )
        con.execute(
            "INSERT OR REPLACE INTO x_call_verdicts VALUES (?,?,?,?,?)",
            (call_id, verdict, resolved_ts, ENGINE_VERSION, _utc_now()),
        )
        counts[verdict] = counts.get(verdict, 0) + 1
    con.commit()
    con.close()
    kcon.close()
    return {"counts": counts}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_pct(v: float | None) -> str:
    return f"{v * 100:+.2f} %" if v is not None else "—"


def write_report(result: dict) -> Path:
    now = _utc_now()
    stats = result["stats"]
    rows = result["rows"]
    lines = [
        "# Rapport d'honnetete du registre X",
        "",
        f"Genere : {now} | moteur : {ENGINE_VERSION}",
        "",
        "## Contexte",
        "",
        f"- posts dans le registre : {stats.get('posts', 0)}",
        f"- comptes en watchlist : {stats.get('comptes', 0)}",
        f"- calls scores : {stats['scored'] + stats['partiel']}"
        f" (complets : {stats['scored']}, en maturite : {stats['partiel']})",
        f"- ignores : {stats['hors_univers']} hors univers, "
        f"{stats['date_unparseable']} date illisible, {stats['pas_de_prix']} sans prix",
        "",
        "## Regle de lecture",
        "",
        "Rendements directionnels (short = retour inverse), frais et slippage NON",
        "inclus : on mesure les comptes, pas une strategie executable. Un petit N",
        "n'est pas une statistique — le registre a une culture : ne pas se mentir.",
        "",
        "## Calls",
        "",
    ]
    if not rows:
        lines.append("Aucun call scoreable pour l'instant.")
    else:
        trad = tradability({r["symbol"] for r in rows})
        lines.append(
            "| compte | call | entree (declaree -> resolue) | +1h | +24h | +7j | coll. (spread bps) | portée (vues) |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            declared = (
                f"{r['entry_declared']:g}" if r["entry_declared"] else "auto"
            )
            t = trad.get((r["symbol"] or "").upper(), {})
            spread = t.get("spread_bps")
            coll = "—" if spread is None else ("OUI" if t["collectionnable"] else f"non ({spread:g})")
            reach = r.get("views") or 0
            reach_s = f"{reach/1000:.1f}k" if reach >= 1000 else (str(reach) if reach else "—")
            lines.append(
                f"| @{r['handle']} | {r['symbol']} {r['direction'].upper()} "
                f"({r['confidence']}) | {declared} -> {r['entry']:.4g} "
                f"| {_fmt_pct(r['ret_1h'])} | {_fmt_pct(r['ret_24h'])} "
                f"| {_fmt_pct(r['ret_7d'])} | {coll} | {reach_s} |"
            )
        coll_rows = [r for r in rows
                     if trad.get((r["symbol"] or "").upper(), {}).get("collectionnable")]
        lines += [
            "",
            f"Collectionnables (spread top-10 < {SPREAD_BPS_LIMIT:g} bps, seuil legacy) : "
            f"{len(coll_rows)}/{len(rows)} calls affiches. Frais taker Aster : "
            "4 bps (USDT), 0,5 bps (USD1) — un aller-retour coute 2x les frais.",
            "Le registre mesure la PREDICTION des comptes ; la colonne coll. dit",
            "si le call etait reellement encaissable sur Aster au moment du score.",
        ]
    n24 = sum(1 for r in rows if r["ret_24h"] is not None)
    r24 = [r["ret_24h"] for r in rows if r["ret_24h"] is not None]
    inv_cum = -sum(r24) if r24 else None
    inv_wins = sum(1 for v in r24 if v < 0)
    verdicts: dict[int, str] = {}
    try:
        vcon = _connect()
        verdicts = dict(
            vcon.execute("SELECT call_id, verdict FROM x_call_verdicts").fetchall()
        )
        vcon.close()
    except Exception:
        pass
    vcounts: dict[str, int] = {}
    for v in verdicts.values():
        vcounts[v] = vcounts.get(v, 0) + 1
    lines += [
        "",
        "## La vue inversee (reverse trading)",
        "",
        f"Calls avec ret_24h : {len(r24)}. Direct : {len(r24) - inv_wins} gagnants, "
        f"{inv_wins} perdants. L'INVERSE des memes calls : {inv_wins} gagnants, "
        f"{len(r24) - inv_wins} perdants, cumul {_fmt_pct(inv_cum)}.",
        "Un compte dont les calls perdent systematiquement EST un signal —",
        "l'inverse d'un mauvais gourou est un gourou, aux frais et au spread pres",
        "(l'inverse paie deux fois les frais : jamais gratuit, jamais oublie).",
        "Agregats par compte des que >= 10 verdicts ; avant, ce sont des indices,",
        "pas des statistiques.",
        "",
        f"Verdicts trade (TP/SL rejoues) : "
        + (", ".join(f"{k} {v}" for k, v in sorted(vcounts.items())) or "aucun")
        + ".",
        "Les agregats par compte (hit rate, moyenne) restent MASQUES tant que",
        "ce nombre est sous 10 : un hit rate sur 2-3 calls, c'est se mentir",
        "avec un petit echantillon — exactement ce que le registre existe",
        "pour demasquer chez les autres.",
    ]
    out = REPORTS / f"registre-honnetete-{now.replace(':', '').replace('-', '')}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Scoring des calls du registre X")
    p.add_argument("--score", action="store_true", help="score tous les calls et genere le rapport")
    args = p.parse_args()
    if not args.score:
        p.print_help()
        return 2
    result = score_all()
    tv = trade_verdicts()
    out = write_report(result)
    s = result["stats"]
    print(f"[registre] scores : {s['scored']} complets, {s['partiel']} en maturite, "
          f"{s['hors_univers'] + s['date_unparseable'] + s['pas_de_prix']} ignores")
    print(f"[registre] verdicts trades : {tv['counts']}")
    print(f"[registre] rapport : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
