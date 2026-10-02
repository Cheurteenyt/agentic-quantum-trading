#!/usr/bin/env python
"""CASCADE x CYCLE DE VIE — le filtre qui dit OU la cascade marche."""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
LEV = 20
COST = 0.28
STOP_PCT = 1.2
H = 8

def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
    results = defaultdict(lambda: {"n": 0, "w": 0, "s": 0.0})
    for sym in majors:
        df = load_df(con, sym)
        if df is None or len(df) < 500: continue
        cs = df["close"]
        op, cl = df["open"].values, df["close"].values
        lo = df["low"].values
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        birth = idx[0]
        age_d = (idx - birth).total_seconds() / 86400
        dd = (1 - cs / cs.cummax()) * 100
        r1 = cs.pct_change() * 100
        ra = r1.abs()
        casc = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
                & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        for t in np.where(casc)[0]:
            ei = t + 1
            if ei + H >= len(idx_ns) or ei >= len(idx_ns): continue
            entry = op[ei]
            if entry <= 0: continue
            exit_open = idx_ns[ei] + H * 3600 * 10**9
            j = int(np.searchsorted(idx_ns, exit_open, side="left"))
            if j >= len(idx_ns): continue
            x = cl[j]
            pr = (x - entry)/entry*100
            mae = (lo[ei:j+1].min() - entry)/entry*100
            margin = max(pr * (-1) * LEV, -STOP_PCT * LEV) - COST * LEV
            age = age_d[ei]
            ddv = dd.values[ei]
            gates = {"tous": True, "age_7_90": 7 <= age <= 90,
                     "dd_20_50": 20 <= ddv <= 50,
                     "age_7_90_and_dd_20_50": 7 <= age <= 90 and 20 <= ddv <= 50,
                     "age_lt_7": age < 7, "age_gt_90": age > 90}
            for gate, cond in gates.items():
                if cond:
                    results[gate]["n"] += 1
                    results[gate]["w"] += margin > 0
                    results[gate]["s"] += margin
    con.close()
    print("=== CASCADE x CYCLE DE VIE a 20x ===")
    for gate, d in sorted(results.items()):
        if d["n"] < 20: continue
        wr = d["w"]/d["n"]*100
        avg = d["s"]/d["n"]
        print(f"  {gate:28s} N={d['n']:5d} WR={wr:5.1f}% avg={avg:+6.1f}%")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
