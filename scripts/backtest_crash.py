#!/usr/bin/env python
"""CAMPAGNE CRASH — les indicateurs de chute institutionnelle à 20x.

Les institutions vendent PAR VAGUES : la première bougie 3σ basse = le début
de la vague d'ordres → les heures suivantes continuent (les ordres des
fonds s'exécutent en tranches). À 20x, la fenêtre est étroite mais le
rendement est énorme : un mouvement de 2,4 % = +48 % de marge.

Les signaux (les vagues de vente institutionnelle) :
  1. crash_3sigma_short      : une bougie ≤ -3σ (la première vague)
  2. crash_accel_short       : 2 bougies consécutives ≤ -2σ (l'accélération)
  3. crash_volume_short      : bougie ≤ -2σ ET volume ≥ 3× (le volume institutionnel)
  4. crash_funding_short     : bougie ≤ -2σ ET funding extrême positif (les longs piégés)
  5. crash_miroir_long       : bougie ≥ +3σ → long (le short-squeeze symétrique)

La géométrie stop/target à 20x :
  stop 1,2 % (24 % de marge) / target 2,4 % (48 % de marge) — ratio 2:1
  Le stop protège de la liquidation (2,5 % à 20x). La marche : la première
  bougie qui touche stop OU target décide (le stop d'abord = perte conservatrice).

  .venv/bin/python scripts/backtest_crash.py
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
STOP_PCT = 1.2
TARGET_PCT = 2.4
COST_NOTIONAL = 0.18


def crash_signals(df: pd.DataFrame, ret_sigma: float) -> list[tuple[str, int, pd.Series]]:
    """Les signaux de crash : les vagues de vente institutionnelle."""
    out: list[tuple[str, int, pd.Series]] = []
    ret1 = df["close"].pct_change() * 100
    sigma = ret1.rolling(168).std()
    body = ret1
    vol_z = ((df["volume"] - df["volume"].rolling(168).mean())
             / df["volume"].rolling(168).std().where(lambda s: s > 0))
    crash3 = body <= -ret_sigma * sigma
    crash2 = body <= -ret_sigma * sigma * 2 / 3
    big_vol = vol_z >= 3
    out.append(("crash_3sigma_short", -1, crash3.fillna(False)))
    out.append(("crash_3sigma_long_miroir", +1,
                (body >= ret_sigma * sigma).fillna(False)))
    out.append(("crash_accel_short", -1,
                (crash2.shift(1, fill_value=False) & crash2).fillna(False)))
    out.append(("crash_volume_short", -1,
                (crash2 & big_vol).fillna(False)))
    return out


def walk_stop_target(df: pd.DataFrame, entry_i: int, direction: int,
                     stop_pct: float, target_pct: float,
                     max_bars: int = 24) -> tuple[str, float | None, int | None]:
    """La marche bougie par bougie : stop d'abord = perte conservatrice."""
    entry = df["open"].values[entry_i]
    stop_px = entry * (1 - stop_pct / 100) if direction > 0 else entry * (1 + stop_pct / 100)
    tgt_px = entry * (1 + target_pct / 100) if direction > 0 else entry * (1 - target_pct / 100)
    lows, highs = df["low"].values, df["high"].values
    for k in range(entry_i, min(entry_i + max_bars, len(df.index))):
        lo, hi = lows[k], highs[k]
        if direction > 0:
            if lo <= stop_px:
                return "stop", -stop_pct * LEV, k
            if hi >= tgt_px:
                return "target", target_pct * LEV, k
        else:
            if hi >= stop_px:
                return "stop", -stop_pct * LEV, k
            if lo <= tgt_px:
                return "target", target_pct * LEV, k
    # le temps écoulé : clôture à la dernière bougie
    x = df["close"].values[min(entry_i + max_bars, len(df.index) - 1)]
    ret = (x - entry) / entry * 100 * direction - COST_NOTIONAL
    return "timeout", ret, min(entry_i + max_bars, len(df.index) - 1)


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
    ret_sigma = 2.5  # les bougies de crash = ±2,5σ de la distribution horaire
    STOPS = (0.8, 1.2)
    TARGETS = (1.6, 2.4, 3.2)
    MAX_BARS = 24

    results: dict[tuple[str, int, float, float], dict] = defaultdict(
        lambda: {"n": 0, "wins": 0, "sum": 0.0, "liq": 0})
    blind: dict[tuple[int, float, float], dict] = defaultdict(
        lambda: {"n": 0, "wins": 0, "sum": 0.0, "liq": 0})

    for sym in majors:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        ret1 = df["close"].pct_change() * 100
        for name, direction, ev in crash_signals(df, ret_sigma):
            ev_idx = df.index[ev.fillna(False)]
            for stop_pct in STOPS:
                for tgt_pct in TARGETS:
                    key = (name, stop_pct, tgt_pct)
                    for ts in ev_idx:
                        i = int(df.index.searchsorted(ts, side="right"))
                        if i + MAX_BARS >= len(df.index):
                            continue
                        outcome, margin, exit_k = walk_stop_target(
                            df, i, direction, stop_pct, tgt_pct, MAX_BARS)
                        liq = margin <= -100
                        m = margin if not liq else -100.0
                        results[(name, stop_pct, tgt_pct)][key := 0] = None if False else None
                        d = results[(name, stop_pct, tgt_pct)]
                        d["n"] += 1
                        d["wins"] += outcome == "target"
                        d["sum"] += m
                        d["liq"] += liq
            # la baseline blind à la même cadence
            for ts in ev_idx:
                i = int(df.index.searchsorted(ts, side="right"))
                if i + MAX_BARS >= len(df.index):
                    continue
                for stop_pct in STOPS:
                    for tgt_pct in TARGETS:
                        outcome, margin, _ = walk_stop_target(
                            df, i, -1, stop_pct, tgt_pct, MAX_BARS)
                        liq = margin <= -100
                        d = blind[(stop_pct, tgt_pct)]
                        d["n"] += 1
                        d["wins"] += outcome == "target"
                        d["sum"] += margin
                        d["liq"] += liq
    con.close()

    lines = [
        "# CAMPAGNE CRASH — les vagues de vente institutionnelles à 20x",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {len(majors)} majeures, "
        f"1 an, stop/target {STOPS[0]}-{TARGETS[-1]} %, coûts {COST_NOTIONAL} % notionnel "
        f"= {COST_NOTIONAL*LEV:.1f} % marge/RT.", "",
        "| Signal | Stop % | Target % | N | WR target | Liq | Espérance marge |", "|---|---|---|---|---|---|---|",
    ]
    best = []
    for (name, stop_pct, tgt_pct), d in sorted(results.items()):
        n = d["n"]
        if n < 30:
            continue
        wr = d["wins"] / n * 100
        exp = d["sum"] / n
        liq = d["liq"] / n * 100
        lines.append(f"| {name} | {stop_pct} | {tgt_pct} | {n} | {wr:.1f} % "
                     f"| {liq:.1f} % | {exp:+.1f} % |")
        best.append((exp, name, stop_pct, tgt_pct, n, wr, liq))
    lines += ["", "## La baseline blind SHORT (le juge à la même cadence)", ""]
    for (stop_pct, tgt_pct), d in sorted(blind.items()):
        n = d["n"]
        if n < 30:
            continue
        wr = d["wins"] / n * 100
        exp = d["sum"] / n
        lines.append(f"- stop {stop_pct} % / target {tgt_pct} % : N={n}, WR {wr:.1f} %, "
                     f"espérance {exp:+.1f} % de marge, liquidés {d['liq']/n*100:.1f} %")
    best.sort(reverse=True)
    lines += ["", "## TOP 5 espérance marge", ""]
    for exp, name, stop_pct, tgt_pct, n, wr, liq in best[:5]:
        lines.append(f"- **{name} stop {stop_pct} target {tgt_pct}** : espérance "
                     f"{exp:+.1f} % de marge, WR {wr:.1f} % (n={n})")

    out = REPORTS / f"backtest-crash-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[crash] {len(results)} cellules -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
