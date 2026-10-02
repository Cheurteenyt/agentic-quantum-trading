#!/usr/bin/env python
"""Slippage MESURÉ depuis nos carnets d'ordres réels (depth.db).

Pour chaque snapshot du carnet : un ordre au marché de notional N avale les
bins côté ask (achat) ou bid (vente) depuis le mid — le slippage est la
distance entre le prix moyen d'exécution et le mid, en bps. Médiane sur les
snapshots récents = le coût d'exécution RÉEL, pas une estimation.

  .venv/bin/python scripts/slippage_measured.py --notional 2000
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "depth.db"
OUT = ROOT / "data" / "warehouse" / "klines.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notional", type=float, default=2000.0)
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--max-snaps", type=int, default=300)
    args = ap.parse_args()

    con = sqlite3.connect(DB, timeout=60)
    since = time.time() - args.hours * 3600
    mids = {(r[0], r[1]): r[2] for r in con.execute(
        "SELECT symbol, ts, mid FROM depth_meta WHERE ts > ?", (since,))}
    snaps: dict[tuple, dict[float, float]] = defaultdict(lambda: {"bid": {}, "ask": {}})
    for sym, ts, side, price, qty in con.execute(
        "SELECT symbol, ts, side, bin_price, qty FROM depth_bins WHERE ts > ?",
        (since,)):
        if (sym, ts) not in mids:
            continue
        snaps[(sym, ts)][side][price] = snaps[(sym, ts)][side].get(price, 0) + qty

    results: dict[str, list[float]] = defaultdict(list)
    tested_by_sym: dict[str, int] = defaultdict(int)
    for (sym, ts), book in sorted(snaps.items()):
        if tested_by_sym[sym] >= args.max_snaps:
            continue
        mid = mids[(sym, ts)]
        if mid <= 0:
            continue
        tested_by_sym[sym] += 1
        for side_sign, side_key in ((+1, "ask"), (-1, "bid")):
            levels = sorted(book[side_key].items(),
                            reverse=(side_key == "bid"))  # du plus proche au plus loin
            filled, notional, cost = 0.0, 0.0, 0.0
            for price, qty in levels:
                if filled >= args.notional:
                    break
                take = min(qty, (args.notional - filled) / price)
                notional += take * price
                cost += take * price * price
                filled += take * price
            if filled < args.notional * 0.99:
                continue  # carnet trop mince pour ce notional
            vwap = cost / notional
            slip = abs(vwap - mid) / mid * 10_000
            results[sym].append(slip * (1 if side_sign > 0 else 1))

    con.close()
    con2 = sqlite3.connect(OUT, timeout=60)
    con2.execute("""CREATE TABLE IF NOT EXISTS slippage_measured (
        symbol TEXT NOT NULL, notional REAL NOT NULL, slip_bps REAL NOT NULL,
        n_snaps INTEGER, captured_at REAL NOT NULL,
        PRIMARY KEY (symbol, notional))""")
    now = time.time()
    for sym, slips in sorted(results.items()):
        slips.sort()
        med = slips[len(slips) // 2]
        con2.execute("INSERT OR REPLACE INTO slippage_measured VALUES (?,?,?,?,?)",
                     (sym, args.notional, round(med, 2), len(slips), now))
        print(f"[slip] {sym}: médiane {med:.1f} bps "
              f"(p90 {slips[int(len(slips)*0.9)]:.1f}) sur {len(slips)} snapshots "
              f"pour ${args.notional:,.0f}")
    con2.commit()
    con2.close()
    if not results:
        print("[slip] aucun carnet exploitable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
