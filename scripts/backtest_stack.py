#!/usr/bin/env python
"""PRECISION STACKING — tous les filtres empilés sur la cascade à 20x."""
from __future__ import annotations

import itertools
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
LEV = 20
COST = 0.28
STOP_PCT = 1.2
H = 8
MIN_N = 25

def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
    trades = []
    for sym in majors:
        df = load_df(con, sym)
        if df is None or len(df) < 500: continue
        cs = df["close"]
        op, cl = df["open"].values, df["close"].values
        lo, hi = df["low"].values, df["high"].values
        vol = df["volume"].values
        vol_ma = pd.Series(vol).rolling(168).mean().values
        vol_sd = pd.Series(vol).rolling(168).std().values
        vol_z = np.where(vol_sd > 0, (vol - vol_ma) / vol_sd, 0)
        tp = (df["high"] + df["low"] + cs) / 3
        vw_sum = pd.Series((tp * df["volume"]).rolling(168).sum().values)
        vw_vol = pd.Series(df["volume"].rolling(168).sum().values)
        vwap = pd.Series(np.where(vw_vol > 0, vw_sum / vw_vol, np.nan), index=df.index)
        dev = ((cs - vwap) / vwap.where(lambda s: s > 0)).astype(float)
        dev_sd = dev.rolling(168).std()
        vwap_sig = (dev / dev_sd.where(lambda s: s > 0)).fillna(0)
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        birth = idx[0]
        age_d = (idx - birth).total_seconds() / 86400
        dd = (1 - cs / cs.cummax()) * 100
        r1 = cs.pct_change() * 100
        ra = r1.abs()
        casc = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
                & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        ath = cs.cummax().shift(1)
        made_ath = (cs > ath).fillna(False).astype(bool)
        failed_ath = made_ath.shift(1, fill_value=False) & (cs < ath.shift(1)).fillna(True)
        dsfa = pd.Series(np.where(failed_ath, 0, np.nan), index=idx).ffill().fillna(999)
        recent_fa = (dsfa <= 14).values
        for t in np.where(casc)[0]:
            ei = t + 1
            if ei + H >= len(idx_ns) or ei == 0: continue
            entry = op[ei]
            if entry <= 0: continue
            exit_open = idx_ns[ei] + H * 3600 * 10**9
            j = int(np.searchsorted(idx_ns, exit_open, side="left"))
            if j >= len(idx_ns): continue
            x = cl[j]
            pr = (x - entry)/entry*100
            mae = (lo[ei:j+1].min() - entry)/entry*100
            liq = mae <= -STOP_PCT
            margin = -STOP_PCT * LEV if liq else (pr * (-1) * LEV - COST * LEV)
            trades.append({"sym": sym, "ts": idx_ns[ei], "age": age_d[ei],
                           "dd": dd.values[ei], "vwap_sig": vwap_sig.values[ei],
                           "vol_z": vol_z[ei], "recent_fa": bool(recent_fa[ei]),
                           "margin": margin})
    con.close()

    filters = {
        "age_7_90": lambda t: 7 <= t["age"] <= 90,
        "dd_20_50": lambda t: 20 <= t["dd"] <= 50,
        "vwap_2sig": lambda t: t["vwap_sig"] >= 2,
        "vwap_3sig": lambda t: t["vwap_sig"] >= 3,
        "vol_1sig": lambda t: t["vol_z"] >= 1,
        "failed_ath": lambda t: t["recent_fa"],
    }
    configs = []
    for r in range(len(filters) + 1):
        for combo in itertools.combinations(filters.keys(), r):
            filtered = [t for t in trades if all(filters[f](t) for f in combo)]
            n = len(filtered)
            if n < MIN_N: continue
            rets = [t["margin"] for t in filtered]
            wr = sum(1 for r in rets if r > 0)/n*100
            exp = sum(rets)/n
            med = sorted(rets)[n//2]
            liq = sum(1 for t in filtered if t["margin"] <= -STOP_PCT*LEV)/n*100
            configs.append({"f": combo, "n": n, "wr": wr, "exp": exp, "med": med, "liq": liq})
    configs.sort(key=lambda c: -c["exp"])

    lines = [
        "# PRECISION STACKING — la cascade à 20x × tous les filtres",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {len(trades)} trades de base, "
        f"{len(configs)} configs avec N≥{MIN_N}.", "",
        "| Filtres | N | WR | Esp marge | Médiane | Liq |", "|---|---|---|---|---|---|",
    ]
    for c in configs[:15]:
        f_str = " + ".join(c["f"]) if c["f"] else "(cascade seule)"
        lines.append(f"| {f_str} | {c['n']} | {c['wr']:.1f} % | {c['exp']:+.1f} % "
                     f"| {c['med']:+.1f} % | {c['liq']:.1f} % |")
    best_pos = [c for c in configs if c["exp"] > 0]
    lines += ["", "## Le meilleur config (N≥100, esp > 0)", ""]
    for c in configs:
        if c["n"] >= 100 and c["exp"] > 0:
            f_str = " + ".join(c["f"])
            lines.append(f"- **{f_str}** : N={c['n']}, WR {c['wr']:.1f} %, espérance {c['exp']:+.1f} %")
            break
    out = REPORTS / f"backtest-stack-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[stack] {len(trades)} trades, {len(configs)} configs -> {out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
