#!/usr/bin/env python
"""TAKER vs MAKER — la cascade accélérée à 20x avec les deux modes d'exécution.

Le taker (market) paie 4 bps de fee + 10 bps de slippage par side = 28 bps RT.
Le maker (GTX post-only) paie ~2 bps par side = 4 bps RT — mais l'ordre ne
remplit que si le prix REVIENT au niveau (le biais de sélection du maker).

La cascade accélérée : 3 bougies de baisse avec accélération → short.
  - TAKER : entre à l'open suivant (le prix de marché, slippage inclus)
  - MAKER : limite au close du signal — remplit si le high touche le niveau

À 20x, la différence de coûts = 28 - 4 = 24 bps × 20 = 4,8 % de marge par
trade — c'est LA différence entre rentable et non-rentable.

  .venv/bin/python scripts/backtest_maker_taker.py
"""
from __future__ import annotations

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
STOP = 1.2
TARGET = 2.4
MAX_BARS = 24
TAKER_COST = 0.28   # % notionnel RT (4 bps fee + 10 bps slip) × 2 sides
MAKER_COST = 0.04   # % notionnel RT (2 bps fee × 2 sides, pas de slippage)


def cascade_events(df):
    """3 bougies de baisse avec accélération → les ts des signaux."""
    ret1 = df["close"].pct_change() * 100
    ra = ret1.abs()
    cascade = ((ret1 < 0) & (ret1.shift(1) < 0) & (ret1.shift(2) < 0)
               & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
    return df.index[cascade]


def walk(df, entry_i, entry_px, direction, stop_pct, target_pct, max_bars):
    """La marche stop/target depuis le prix de fill."""
    stop_px = entry_px * (1 + stop_pct / 100) if direction < 0 else entry_px * (1 - stop_pct / 100)
    tgt_px = entry_px * (1 - target_pct / 100) if direction < 0 else entry_px * (1 + target_pct / 100)
    highs, lows = df["high"].values, df["low"].values
    for k in range(entry_i, min(entry_i + max_bars, len(df.index))):
        hi, lo = highs[k], lows[k]
        if direction < 0:
            if hi >= stop_px: return "stop", -stop_pct * LEV
            if lo <= tgt_px: return "target", target_pct * LEV
        else:
            if lo <= stop_px: return "stop", -stop_pct * LEV
            if hi >= tgt_px: return "target", target_pct * LEV
    x = df["close"].values[min(entry_i + max_bars, len(df.index) - 1)]
    return "timeout", (x - entry_px) / entry_px * 100 * direction


def main() -> int:
    con = sqlite3.connect(KDB)
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]

    results = {
        "taker": {"n": 0, "fills": 0, "wins": 0, "sum": 0.0, "liq": 0},
        "maker": {"n": 0, "fills": 0, "wins": 0, "sum": 0.0, "liq": 0},
    }

    for sym in majors:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        ev_ts = cascade_events(df)
        opens, closes = df["open"].values, df["close"].values
        highs, lows = df["high"].values, df["low"].values
        idx = df.index

        for ts in ev_ts:
            i_sig = int(idx.searchsorted(ts, side="left"))
            if i_sig + 1 + MAX_BARS >= len(idx):
                continue
            signal_close = closes[i_sig]

            # ——— TAKER : entre à l'open suivant au prix de marché ———
            entry_i_t = i_sig + 1
            if entry_i_t < len(idx):
                entry_t = opens[entry_i_t]  # pas de slippage (déjà dans les coûts)
                outcome, margin = walk(df, entry_i_t, entry_t, -1, STOP, TARGET, MAX_BARS)
                liq = margin <= -100
                d = results["taker"]
                d["n"] += 1; d["fills"] += 1; d["wins"] += outcome == "target"
                d["sum"] += margin - TAKER_COST * LEV if not liq else -100 - 2.5
                d["liq"] += liq

            # ——— MAKER : limite au close du signal ———
            limit_px = signal_close  # le short limite au prix de clôture du signal
            # le fill : le high de la bougie suivante doit ≥ limit_px
            fill_i = i_sig + 1
            if fill_i < len(idx) and highs[fill_i] >= limit_px:
                entry_m = limit_px
                outcome, margin = walk(df, fill_i, entry_m, -1, STOP, TARGET, MAX_BARS)
                liq = margin <= -100
                d = results["maker"]
                d["n"] += 1; d["fills"] += 1; d["wins"] += outcome == "target"
                d["sum"] += margin - MAKER_COST * LEV if not liq else -100 - 2.5
                d["liq"] += liq
    con.close()

    lines = [
        "# TAKER vs MAKER — la cascade accélérée à 20x",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — stop {STOP} % / "
        f"target {TARGET} % à {LEV}x, 6 majeures, 1 an.", "",
        "| Mode | Coûts RT | N | Fills | WR | Liq | Espérance marge |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode, cost in (("taker", TAKER_COST), ("maker", MAKER_COST)):
        d = results[mode]
        n = d["n"]
        if n == 0:
            continue
        wr = d["wins"] / n * 100
        exp = d["sum"] / n
        liq = d["liq"] / n * 100
        lines.append(f"| {mode} | {cost:.2f} % | {n} | {d['fills']} | {wr:.1f} % "
                     f"| {liq:.1f} % | {exp:+.1f} % |")

    dt = results["taker"]
    dm = results["maker"]
    if dm["n"] > 0 and dt["n"] > 0:
        lines += ["",
                  f"**La différence maker-taker** : espérance {dm['sum']/dm['n'] - dt['sum']/dt['n']:+.1f} % "
                  f"de marge par trade — les coûts maker sont "
                  f"{TAKER_COST - MAKER_COST:.1f} % notionnel plus bas.",
                  f"Le fill rate maker : {dm['fills']/max(dt['n'],1)*100:.0f} % "
                  f"(le maker ne remplit que sur le re-test du niveau)."]

    out = REPORTS / f"backtest-maker-taker-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[maker-taker] taker N={results['taker']['n']}, maker N={results['maker']['n']} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
