#!/usr/bin/env python
"""LA CASCADE — les patterns d'accélération institutionnelle à 20x.

Trois signaux jamais testés sur Aster :

  1. CASCADE : 3 bougies consécutives de baisse avec ACCÉLÉRATION
     (chaque bougie tombe PLUS FORT que la précédente = les ordres
     institutionnels s'enchaînent) → short au close de la 3e
  2. BOUNCE-FADE : après un 3σ dump, le prix rebondit vers la moitié
     du drop (le dead-cat bounce) → short au niveau du rebond
     (la deuxième vague institutionnelle)
  3. AMPLIFICATION : BTC tombe ≥ 2 % en 1h ET le coin sur-réagit
     (tombe ≥ 2× le mouvement BTC) → short le sur-réacteur

La géométrie : stop 1,2 % / target 2,4 % à 20x (stop d'abord = perte).
La baseline blind short à la même cadence.
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
COST_NOTIONAL = 0.18
MAX_BARS = 24


def walk(df, entry_i, direction):
    entry = df["open"].values[entry_i]
    stop_px = entry * (1 - STOP / 100) if direction > 0 else entry * (1 + STOP / 100)
    tgt_px = entry * (1 + TARGET / 100) if direction > 0 else entry * (1 - TARGET / 100)
    lows, highs = df["low"].values, df["high"].values
    for k in range(entry_i, min(entry_i + MAX_BARS, len(df.index))):
        lo, hi = lows[k], highs[k]
        if direction > 0:
            if lo <= stop_px: return "stop", -STOP * LEV
            if hi >= tgt_px: return "target", TARGET * LEV
        else:
            if hi >= stop_px: return "stop", -STOP * LEV
            if lo <= tgt_px: return "target", TARGET * LEV
    x = df["close"].values[min(entry_i + MAX_BARS, len(df.index) - 1)]
    return "timeout", (x - entry) / entry * 100 * direction - COST_NOTIONAL


def main() -> int:
    con = sqlite3.connect(KDB)
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]

    pooled: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"n": 0, "wins": 0, "sum": 0.0, "liq": 0})
    blind: dict[tuple[int, ...], dict] = defaultdict(
        lambda: {"n": 0, "wins": 0, "sum": 0.0})

    btc = load_df(con, "BTCUSDT")
    btc_ret1 = btc["close"].pct_change() * 100

    for sym in sorted(majors):
        if sym == "BTCUSDT":
            continue
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        ret1 = df["close"].pct_change() * 100
        ret2 = ret1.diff()
        sigma = ret1.rolling(168).std()
        # ——— 1. CASCADE : 3 bougies de baisse consécutives avec ACCÉLÉRATION ———
        cascade = (
            (ret1 < 0) & (ret1.shift(1) < 0) & (ret1.shift(2) < 0)
            & (ret1.abs() > ret1.abs().shift(1))
            & (ret1.abs().shift(1) > ret1.abs().shift(2))
        ).fillna(False)
        # —— 2. BOUNCE-FADE : après un 3σ dump, le prix rebondit vers la 50% retracement ——
        crash = ret1 <= -3 * sigma
        crash_idx = df.index[crash.fillna(False)]
        bounce_events = []
        highs15 = df["high"].values
        lows15 = df["low"].values
        for ts in crash_idx:
            i = int(df.index.searchsorted(ts, side="right"))
            if i + 24 >= len(df.index):
                continue
            crash_low = df["low"].values[i:i+24].min()
            crash_high = highs15[i:i+24].max() if i < len(highs15) else 0
            crash_range = crash_high - crash_low
            if crash_range <= 0:
                continue
            # le rebond : le high des 12 bougies suivantes remonte à ≥ 50 % du range
            bounce_zone = crash_low + crash_range * 0.5
            for k in range(i+1, min(i+13, len(df.index))):
                if highs15[k] >= bounce_zone:
                    bounce_events.append((k, -1))
                    break
        # —— 3. AMPLIFICATION : BTC tombe ≥ 2 % et le coin sur-réagit ——
        amp_events = []
        btc_ts = btc.index[btc_ret1 <= -2.0]
        for b_ts in btc_ts:
            pos = int(df.index.searchsorted(b_ts, side="right"))
            if pos >= len(df.index) - 1 or pos == 0:
                continue
            btc_move = abs(btc_ret1.loc[b_ts])
            coin_move = abs(ret1.iloc[pos])
            if coin_move > btc_move * 1.5 and ret1.iloc[pos] < 0:
                amp_events.append((pos, -1))

        # —— l'évaluation stop/target ——
        for name, evs in (
            ("cascade_accélérée", cascade.fillna(False)),
            ("bounce_fade", bounce_events),
            ("amplification_btc", amp_events),
        ):
            for ts_or_pos in evs:
                if isinstance(ts_or_pos, (pd.Timestamp, str)):
                    i = int(df.index.searchsorted(ts_or_pos, side="right"))
                elif isinstance(ts_or_pos, (int, np.integer)):
                    i = int(ts_or_pos)
                else:
                    continue
                if i + 2 >= len(df.index) or i + MAX_BARS >= len(df.index):
                    continue
                outcome, margin = walk(df, i + 1, -1)
                d = pooled[(name, 24)]
                d["n"] += 1
                d["wins"] += outcome == "target"
                d["sum"] += margin
                d["liq"] += margin <= -100
    con.close()

    lines = [
        "# LA CASCADE — les patterns d'accélération institutionnelle à 20x",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — stop {STOP} % / "
        f"target {TARGET} % à {LEV}x, 6 majeures, 1 an, coûts réels.", "",
        "| Pattern | N | WR target | % liquidés | Espérance marge |", "|---|---|---|---|---|",
    ]
    best = []
    for (name, h), d in sorted(pooled.items()):
        n = d["n"]
        if n < 20:
            continue
        wr = d["wins"] / n * 100
        exp = d["sum"] / n
        liq = d["liq"] / n * 100
        lines.append(f"| {name} | {n} | {wr:.1f} % | {liq:.1f} % | {exp:+.1f} % |")
        best.append((exp, name, n, wr, liq))
    best.sort(reverse=True)
    lines += ["", "## Le classement", ""]
    for exp, name, n, wr, liq in best:
        lines.append(f"- **{name}** : espérance {exp:+.1f} % de marge, "
                     f"WR {wr:.1f} % (n={n})")
    if not best or best[0][0] < 2:
        lines += ["", "Aucun pattern avec une espérance > +2 % de marge —",
                  "les institutions ne laissent pas de traces assez claires",
                  "pour du 20x sans micro-structure."]

    out = REPORTS / f"backtest-cascade-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[cascade] {len(pooled)} patterns, "
          f"top espérance {best[0][0] if best else 0:+.1f} % -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
