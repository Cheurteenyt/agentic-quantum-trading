#!/usr/bin/env python
"""Détecteur d'Ondes — la fusion baleines fomo × X.com × Aster.

Score d'onde composite (transparent, 0-100) :
  - baleines : min(nb_baleines/10, 1) x 40   (fomo.db, positions réelles)
  - social   : vélocité X (x_mentions aujourd'hui vs hier) x 20
               + calls du registre 24h (>= 2 -> +10)
  - exécution: perp Aster tradable (spread < 20 bps) -> 30 ; fomo-only -> 15

LEDGER INTÉGRÉ : chaque token dont le score >= seuil est flaggé avec son
prix (perp Aster si listé). Les passages suivants remplissent ret_24h /
ret_72h depuis les klines — le détecteur construit SON propre backtest,
règle pré-enregistrée inchangée (N >= 10, winrate >= 55 %).

Usage :
  .venv/bin/python scripts/wave_detector.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.memecoin_pulse import spread_bps  # noqa: E402

FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"
X_DB = ROOT / "data" / "warehouse" / "x_posts.db"
KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
WAVE_THRESHOLD = 60
TICKER_URL = "https://fapi.asterdex.com/fapi/v1/ticker/price"

WAVE_DDL = """
CREATE TABLE IF NOT EXISTS wave_flags (
    ticker        TEXT    NOT NULL,
    flagged_at    REAL    NOT NULL,
    score         REAL    NOT NULL,
    price_at_flag REAL,
    venue         TEXT    NOT NULL,
    ret_24h       REAL,
    ret_72h       REAL,
    PRIMARY KEY (ticker, flagged_at)
);
"""


def whales_confluence() -> dict[str, dict]:
    con = sqlite3.connect(f"file:{FOMO_DB}?mode=ro", uri=True)
    try:
        rows = con.execute("""
            SELECT handle, ticker, value_usd, dir FROM fomo_positions p
            WHERE captured_at = (SELECT MAX(captured_at) FROM fomo_positions p2
                                 WHERE p2.handle = p.handle AND p2.ticker = p.ticker)
        """).fetchall()
    finally:
        con.close()
    by_ticker: dict[str, dict] = defaultdict(lambda: {"traders": [], "total": 0.0, "dirs": []})
    for handle, ticker, value, dirn in rows:
        r = by_ticker[ticker]
        if handle not in r["traders"]:
            r["traders"].append(handle)
        r["total"] += value or 0
        r["dirs"].append(dirn)
    return by_ticker


def x_velocity(symbol: str, today: str) -> tuple[int, float | None]:
    """(mentions aujourd'hui, ratio vs hier)."""
    con = sqlite3.connect(f"file:{X_DB}?mode=ro", uri=True)
    try:
        (n_today,) = con.execute(
            "SELECT COALESCE(SUM(n), 0) FROM x_mentions WHERE symbol = ? AND day = ?",
            (symbol, today)).fetchone()
        (n_yday,) = con.execute(
            "SELECT COALESCE(SUM(n), 0) FROM x_mentions WHERE symbol = ? AND day = "
            "date(?, '-1 day')", (symbol, today)).fetchone()
        ratio = (n_today / n_yday) if n_yday else (2.0 if n_today else None)
        return int(n_today), ratio
    except Exception:  # noqa: BLE001
        return 0, None
    finally:
        con.close()


def calls_24h(symbol: str) -> int:
    con = sqlite3.connect(f"file:{X_DB}?mode=ro", uri=True)
    try:
        cutoff = time.time() - 86400
        (n,) = con.execute(
            "SELECT COUNT(*) FROM x_calls c JOIN x_call_scores s ON s.call_id = c.call_id "
            "WHERE c.symbol = ? AND CAST(strftime('%s', s.posted_at) AS INTEGER) >= ?",
            (symbol, cutoff)).fetchone()
        return int(n)
    except Exception:  # noqa: BLE001
        return 0
    finally:
        con.close()


def aster_price(symbol: str) -> float | None:
    try:
        req = urllib.request.Request(f"{TICKER_URL}?symbol={symbol}",
                                     headers={"User-Agent": "trading-agent/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return float(json.load(resp)["price"])
    except Exception:  # noqa: BLE001
        return None


def aster_ret_since(symbol: str, since_ts: float, hours: float) -> float | None:
    """Rendement % depuis flagged_at jusqu'à flagged_at + hours (klines 1h)."""
    try:
        con = sqlite3.connect(f"file:{KLINES_DB}?mode=ro", uri=True)
        row = con.execute(
            "SELECT open_time, close FROM klines WHERE symbol = ? AND interval = '1h' "
            "AND open_time >= ? ORDER BY open_time LIMIT 1", (symbol, int(since_ts * 1000)),
        ).fetchone()
        target_ms = int((since_ts + hours * 3600) * 1000)
        row2 = con.execute(
            "SELECT close FROM klines WHERE symbol = ? AND interval = '1h' "
            "AND open_time <= ? ORDER BY open_time DESC LIMIT 1", (symbol, target_ms),
        ).fetchone()
        con.close()
        if not row or not row2:
            return None
        return (row2[0] / row[1] - 1) * 100
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    con = sqlite3.connect(FOMO_DB)
    con.executescript(WAVE_DDL)
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    by_ticker = whales_confluence()

    scored = []
    for ticker, v in by_ticker.items():
        n_whales = len(v["traders"])
        if n_whales < 3 or v["total"] < 5000 or v["total"] / n_whales < 2000:
            continue  # pas une conviction
        base = ticker if not ticker.startswith("1000") else ticker.replace("1000", "")
        mentions, ratio = x_velocity(base, today)
        n_calls = calls_24h(base)
        spread = spread_bps(f"{base}USDT")
        aster = spread is not None and spread < 20.0
        whale_pts = min(n_whales / 10, 1.0) * 40
        vel_pts = 0.0
        if ratio is not None:
            vel_pts = 20 if ratio >= 2 else 15 if ratio >= 1.5 else 10 if ratio >= 1 else 0
        call_pts = 10 if n_calls >= 2 else 0
        exec_pts = 30 if aster else 15
        score = round(whale_pts + vel_pts + call_pts + exec_pts, 1)
        scored.append({
            "ticker": ticker, "whales": n_whales, "whale_usd": v["total"],
            "mentions": mentions, "vel_ratio": ratio, "calls_24h": n_calls,
            "spread_bps": None if spread is None else round(spread, 1),
            "aster": aster, "score": score,
        })
    scored.sort(key=lambda r: -r["score"])

    # ledger : flag les ondes, remplir les rets des anciens flags
    for r in scored:
        if r["score"] < WAVE_THRESHOLD:
            continue
        existing = con.execute(
            "SELECT 1 FROM wave_flags WHERE ticker = ? AND flagged_at > ?",
            (r["ticker"], time.time() - 72 * 3600)).fetchone()
        if existing:
            continue  # déjà flaggé récemment : pas de double comptage
        price = aster_price(f"{r['ticker']}USDT") if r["aster"] else None
        con.execute("INSERT OR IGNORE INTO wave_flags VALUES (?,?,?,?,?,?,?)",
                    (r["ticker"], time.time(), r["score"], price,
                     "aster" if r["aster"] else "fomo", None, None))
    for (ticker, flagged_at, price, ret24, ret72, venue) in con.execute(
            "SELECT ticker, flagged_at, price_at_flag, ret_24h, ret_72h, venue "
            "FROM wave_flags").fetchall():
        updates = {}
        if ret24 is None and flagged_at <= time.time() - 24 * 3600 and venue == "aster":
            # ⚠️ les klines sont stockées sous TICKER+USDT (bug PONS corrigé)
            updates["ret_24h"] = aster_ret_since(ticker + "USDT", flagged_at, 24)
        if ret72 is None and flagged_at <= time.time() - 72 * 3600 and venue == "aster":
            updates["ret_72h"] = aster_ret_since(ticker + "USDT", flagged_at, 72)
        for col, val in updates.items():
            if val is not None:
                con.execute(f"UPDATE wave_flags SET {col} = ? WHERE ticker = ? AND flagged_at = ?",
                            (val, ticker, flagged_at))
    con.commit()

    waves = [r for r in scored if r["score"] >= WAVE_THRESHOLD]
    lines = [
        f"# Détecteur d'Ondes — {datetime.now(tz=timezone.utc):%d/%m/%Y %H:%M} UTC",
        "Confluence baleines fomo × vélocité X × exécution Aster. Seuil onde :",
        f"{WAVE_THRESHOLD}/100. Chaque onde est flaggée avec son prix : le ledger",
        "remplit ret_24h/ret_72h aux passages suivants (auto-backtest, règle",
        "pré-enregistrée N >= 10 / 55 % avant tout verdict).",
        "",
        "## Ondes actives",
        "",
    ]
    if not waves:
        lines.append("Aucune onde >= seuil pour l'instant (normal en début d'accumulation).")
    else:
        lines += ["| Token | Score | Baleines | $ tenus | Mentions X (ratio) | Calls 24h | Exécution |",
                  "|---|---|---|---|---|---|---|"]
        for r in waves:
            lines.append(
                f"| **{r['ticker']}** | {r['score']} | {r['whales']}/35 | ${r['whale_usd']:,.0f} | "
                f"{r['mentions']} ({r['vel_ratio'] if r['vel_ratio'] is not None else '—'}) | "
                f"{r['calls_24h']} | {'Aster perp' if r['aster'] else 'fomo (manuel)'} |")
    lines += ["", "## Ledger des ondes passées", ""]
    flags = con.execute("SELECT ticker, score, venue, ret_24h, ret_72h FROM wave_flags "
                        "ORDER BY flagged_at DESC LIMIT 15").fetchall()
    if flags:
        lines += ["| Token | Score | Venue | ret 24h | ret 72h |", "|---|---|---|---|---|"]
        for t, s, venue, r24, r72 in flags:
            fmt = lambda v: f"{v:+.2f} %" if v is not None else "—"
            lines.append(f"| {t} | {s} | {venue} | {fmt(r24)} | {fmt(r72)} |")
    else:
        lines.append("Vide — les premières ondes s'inscrivent à partir d'aujourd'hui.")
    con.close()
    out = REPORTS / f"wave-detector-{datetime.now(tz=timezone.utc):%Y%m%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[onde] {out} — {len(waves)} onde(s) active(s)")
    for r in waves:
        print(f"  {r['ticker']:<12} score={r['score']} baleines={r['whales']} "
              f"mentions={r['mentions']} aster={r['aster']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
