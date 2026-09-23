#!/usr/bin/env python3
"""Backtest du funding extreme — premiere vraie hypothese de l'ere moderne.

Hypothese (structurelle, pas un pattern de bougies) : quand le funding d'un
perp atteint un extreme de SON PROPRE historique, le prix a tendance a
revenir (les extremes de positionnement se debullent).

Protocol honnete :
  - percentile calcule DANS l'historique de chaque symbole (jamais compare
    entre symboles)
  - extreme = top 10% / bottom 10% des reglements
  - rendement forward mesure depuis les klines 1h reelles du warehouse
    (+24h, +72h), direction contrarian (funding extreme haut -> short
    gagne si le prix baisse)
  - mise en garde affichee : les extremes de funding CLUSTERN dans le temps
    (tous les symboles en meme temps) -> les evenements ne sont pas
    independants, le N est gonfle. Ce test dit une tendance, pas une loi.

    python scripts/funding_backtest.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_klines import DB_PATH, init_db, load_bars  # noqa: E402

CACHE = ROOT / "backend" / "services" / "onchain" / "aster" / \
    "aster_public_funding_history_cache.json"
REPORTS = ROOT / "reports"
USER_AGENT = "trading-agent-funding-bt/1.0"
PAUSE_MS = 220

SCHEMA = """
CREATE TABLE IF NOT EXISTS funding_history (
    symbol      TEXT    NOT NULL,
    funding_time INTEGER NOT NULL,
    rate        REAL    NOT NULL,
    fetched_at  REAL    NOT NULL,
    PRIMARY KEY (symbol, funding_time)
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_all_series(limit: int = 100) -> int:
    symbols = sorted(json.loads(CACHE.read_text(encoding="utf-8"))
                     .get("symbols", {}).keys())
    con = init_db(DB_PATH)
    con.executescript(SCHEMA)
    inserted = 0
    now_s = time.time()
    for i, sym in enumerate(symbols):
        url = ("https://fapi.asterdex.com/fapi/v3/fundingRate?"
               + urllib.parse.urlencode({"symbol": sym, "limit": limit}))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            print(f"[bt] {sym} : echec {type(exc).__name__}")
            continue
        for ev in data:
            con.execute(
                "INSERT OR REPLACE INTO funding_history VALUES (?,?,?,?)",
                (sym, int(ev["fundingTime"]), float(ev["fundingRate"]), now_s),
            )
            inserted += 1
        con.commit()
        if (i + 1) % 10 == 0:
            print(f"[bt] {i + 1}/{len(symbols)} series...")
        time.sleep(PAUSE_MS / 1000)
    con.close()
    print(f"[bt] {inserted} reglements stockes ({len(symbols)} symboles)")
    return inserted


def percentile_rank(values: list[float], v: float) -> float:
    below = sum(1 for x in values if x < v)
    return below / len(values)


def run_backtest(low_pctl: float = 0.10, high_pctl: float = 0.90) -> dict:
    con = init_db(DB_PATH)
    rows = con.execute(
        "SELECT symbol, funding_time, rate FROM funding_history ORDER BY symbol"
    ).fetchall()
    con.close()
    by_symbol: dict[str, list[tuple[int, float]]] = {}
    for sym, ts, rate in rows:
        by_symbol.setdefault(sym, []).append((ts, rate))

    events: list[dict] = []
    for sym, series in by_symbol.items():
        rates = [r for _, r in series]
        if len(rates) < 40:
            continue  # historique trop court pour un percentile honnete
        bars = load_bars(init_db(DB_PATH), f"{sym}USDT" if not sym.endswith("USDT") else sym, "1h")
        if len(bars) < 100:
            continue
        closes = [b.close for b in bars]
        times = [b.ts for b in bars]
        for ts, rate in series:
            pctl = percentile_rank(rates, rate)
            if low_pctl < pctl < high_pctl:
                continue
            side = "short" if rate >= high_pctl else "long"
            # prix d'entree : close de la bougie couvrant le reglement
            entry = None
            for b_ts, c in zip(times, closes):
                if b_ts <= ts:
                    entry = c
                else:
                    break
            if entry is None:
                continue
            for horizon_h in (24, 72):
                target_ts = ts + horizon_h * 3_600_000
                exit_price = None
                for b_ts, c in zip(times, closes):
                    if b_ts >= target_ts:
                        exit_price = c
                        break
                if exit_price is None:
                    continue
                raw = (exit_price / entry - 1)
                contrarian = -raw if side == "short" else raw
                # funding encaisse pendant la detention (side qui collecte)
                funding_earned = (rate if side == "short" else -rate) * (horizon_h / 8)
                events.append({
                    "symbol": sym, "ts": ts, "side": side,
                    "pctl": pctl, "horizon": horizon_h,
                    "contrarian_ret": contrarian,
                    "funding_earned": funding_earned,
                })
    return {"events": events}


def summarize(events: list[dict], horizon: int, key: str) -> dict | None:
    sel = [e for e in events if e["horizon"] == horizon]
    if len(sel) < 5:
        return None
    vals = [e[key] for e in sel]
    wins = sum(1 for v in vals if v > 0)
    return {
        "n": len(vals),
        "mean": sum(vals) / len(vals),
        "winrate": wins / len(vals),
        "median": sorted(vals)[len(vals) // 2],
    }


def write_report(events: list[dict]) -> Path:
    now = _utc_now()
    lines = [
        "# Backtest — le funding extreme predit-il le prix ?",
        "",
        f"Genere : {now} UTC — percentile DANS l'historique de chaque symbole,",
        "rendements forward depuis les klines 1h reelles, direction contrarian.",
        "",
        "## Mise en garde affichee d'office",
        "",
        "Les extremes de funding CLUSTERN dans le temps (plusieurs symboles au",
        "meme moment) : les evenements ne sont pas independants, le N est gonfle.",
        "Ce test decrit une tendance — il ne garantit rien et n'inclut pas les",
        "couts d'execution (hormis le funding encaisse, credité a la jambe qui",
        "collecte).",
        "",
    ]
    for horizon in (24, 72):
        s1 = summarize(events, horizon, "contrarian_ret")
        s2 = summarize(events, horizon, "funding_earned")
        if s1:
            lines += [
                f"## Horizon +{horizon}h",
                "",
                f"- evenements : {s1['n']}",
                f"- rendement contrarian moyen : {s1['mean'] * 100:+.3f} %"
                f" (median {s1['median'] * 100:+.3f} %)",
                f"- win rate contrarian : {s1['winrate'] * 100:.1f} %",
                f"- funding encaisse moyen : {s2['mean'] * 100:+.4f} %" if s2 else "",
                "",
            ]
    lines += [
        "## Lecture honnete",
        "",
        "Si le win rate et le mean restent dans le bruit (< 55 % et < 0.3 %),",
        "l'hypothese est CLASSÉE dans les resultats nuls — comme les autres.",
        "Si elle sort, elle devient un candidat a valider par la chaine",
        "complete (gates, walk-forward, multiplicity). Pas avant.",
    ]
    out = REPORTS / f"funding-extreme-backtest-{now.replace(':', '').replace('-', '')}.md"
    out.write_text("\n".join([l for l in lines if l != ""]) + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest du funding extreme Aster")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="reutilise funding_history deja en base")
    args = ap.parse_args()
    if not args.skip_fetch:
        fetch_all_series()
    result = run_backtest()
    events = result["events"]
    out = write_report(events)
    print(f"[bt] {len(events)} evenements extremes — rapport : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
