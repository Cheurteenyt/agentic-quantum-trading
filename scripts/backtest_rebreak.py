#!/usr/bin/env python
"""LE RE-BREAK LONG — l'inversion ingénieuse de notre propre découverte.

Nous avons mesuré : 92 % des failed_ATH sont RE-CASSÉS à la hausse dans
les 14 jours (le squeeze extirpe les shorts). Tout le monde shorterait
l'échec — notre donnée dit que le mouvement DOMINANT est le re-break à la
hausse. Le signal : LONG quand le prix re-casse le niveau de l'ATH raté
(dans les 14 jours), l'échec a déjà purgé les late-shorts.

Entrée : l'open de la bougie qui clôture AU-DESSUS du niveau raté.
Horizons : 3j/7j/14j/30j. Baseline blind LONG par horizon (le juge).

  .venv/bin/python scripts/backtest_rebreak.py
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

from scripts.backtest_indicators import load_df, COST_PCT  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
LEV = 3  # le plafond memecoins
HORIZONS = (72, 168, 336, 720)
REBREAK_WINDOW = 336  # 14 jours en bougies 1h


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]

    pooled: dict[int, list[float]] = defaultdict(list)
    delays: list[float] = []
    n_events = n_rebreaks = 0
    blind: dict[int, list[float]] = defaultdict(list)

    for sym in sorted(symbols):
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        close_s = df["close"]
        closes, opens = close_s.values, df["open"].values
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        ath = close_s.cummax().shift(1)
        made = (close_s > ath)
        failed = made.shift(1, fill_value=False) & (close_s < ath.shift(1)).fillna(True)

        for t in np.where(failed.values)[0]:
            if t + REBREAK_WINDOW + max(HORIZONS) >= len(idx) or t < 2:
                continue
            n_events += 1
            ath_level = ath.values[t]
            # le re-break : la première clôture AU-DESSUS du niveau raté
            rb = None
            for k in range(t + 1, t + 1 + REBREAK_WINDOW):
                if closes[k] > ath_level:
                    rb = k
                    break
            if rb is None:
                continue  # jamais re-cassé dans les 14 jours
            n_rebreaks += 1
            delay_h = (rb - t)
            delays.append(float(delay_h))
            entry = opens[rb + 1] if rb + 1 < len(idx) else None
            if not entry or entry <= 0:
                continue
            for h in HORIZONS:
                j = rb + 1 + h - 1
                if j >= len(idx):
                    continue
                ret = ((closes[j] - entry) / entry * 100 - COST_PCT) * LEV
                pooled[h].append(ret)
                # la baseline : un blind long pris au MÊME moment
                blind[h].append((closes[min(rb + h, len(idx) - 1)] - opens[rb])
                                / opens[rb] * 100 - COST_PCT)

    con.close()

    lines = [
        "# LE RE-BREAK LONG — l'inversion du failed_ATH (notre donnée, notre edge)",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {n_events} failed_ATH, "
        f"{n_rebreaks} re-cassures ({n_rebreaks/max(n_events,1)*100:.0f} % de base rate).",
        f"Le délai médian du re-break : {sorted(delays)[len(delays)//2]:.0f} h.",
        f"Levier {LEV}x, coûts {COST_PCT} %, entrée à l'open du re-break.", "",
        "| Horizon | N | WR | Médiane marge | Baseline blind long | Écart |",
        "|---|---|---|---|---|---|",
    ]
    for h in HORIZONS:
        rets = pooled[h]
        if len(rets) < 30:
            continue
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        med = sorted(rets)[len(rets) // 2]
        bl = sum(1 for r in blind[h] if r > 0) / len(blind[h]) * 100
        lines.append(f"| +{h//24}j | {len(rets)} | {wr:.1f} % | {sorted(rets)[len(rets)//2]:+.1f} % "
                     f"| {bl:.1f} % | {wr-bl:+.1f} pts |")

    out = REPORTS / f"backtest-rebreak-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[rebreak] {n_events} échecs, {n_rebreaks} re-breaks -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
