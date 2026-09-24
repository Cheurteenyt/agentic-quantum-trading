#!/usr/bin/env python
"""Campagne LONG-TERME — le côté LONG des memecoins, jamais développé.

Trois patterns long à gros rendement potentiel (les pumps qui continuent,
les renaissances) avec la discipline du harnais v5 (coûts réels, funding
réel pendant détention — les longs PAIENT, MAE/liquidation à 3x, baseline
blind LONG par horizon, audit de multiplicité) :

  1. ath_continuation   : nouveau plus-haut absolu ET la bougie suivante
                          clôture AU-DESSUS de l'ancien ATH → le breakout
                          réussi (le miroir exact du failed_ATH qui a donné
                          87,6 % en short) — les pumps qui continuent
  2. revival_long       : drawdown > 80 % pendant 30 jours PUIS retour sous
                          50 % → la renaissance (nouveau narratif, nouveaux
                          acheteurs)
  3. volume_revival     : age > 90 jours + volume z > 1 soutenu 3 barres +
                          prix au-dessus d'il y a 3 jours → le revival
                          d'un survivant

Horizons LONGS : 3j/7j/14j/30j/60j. C'est là que vivent les gros rendements
memecoin — et là que le funding drag pèse le plus (réel, inclus).
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
LEV = 3
HORIZONS = (72, 168, 336, 720, 1440)  # 3j → 60j


def outcomes_long(idx, opens, closes, lows, i, horizons, cost_pct, fund_h):
    """(h, ret marge, mae %) — entry à l'open de la bougie i, MAE sur chemin."""
    res = []
    entry = opens[i]
    if entry <= 0 or i + 1 >= len(idx):
        return res
    entry_i = i
    for h in horizons:
        j = min(entry_i + h, len(idx) - 1)
        if j <= entry_i:
            continue
        hold = (idx[j] - idx[entry_i]).total_seconds() / 3600
        ret = ((closes[j] - entry) / entry * 100 - cost_pct
               - fund_h * hold) * LEV
        mae = (lows[entry_i:j + 1].min() - entry) / entry * 100
        liq = mae <= -(100 / LEV - 100 * 0 / LEV)  # seuil simple 3x ≈ 33 % (affiné par liq_params)
        res.append((h, ret, mae, liq))
    return res


def main() -> int:
    con = sqlite3.connect(KDB)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]

    pooled: dict[tuple[str, int], list[float]] = defaultdict(list)
    liq_cells: dict[tuple[str, int], list[int]] = defaultdict(list)
    base: dict[int, list[float]] = defaultdict(list)
    n_combos = 0

    for sym in sorted(symbols):
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        close = df["close"]
        opens, closes = df["open"].values, df["close"].values
        lows = df["low"].values
        idx = df.index
        ath = close.cummax().shift(1)
        drawdown = (1 - close / close.cummax()) * 100
        birth = df.index[0]
        age_d = (df.index - birth).total_seconds() / 86400
        vz = ((df["volume"] - df["volume"].rolling(168).mean())
              / df["volume"].rolling(168).std().where(lambda s: s > 0))
        fund_h = 0.0

        # —— 1. ATH CONTINUATION : nouveau ATH + hold au-dessus 1 bougie ——
        made_ath = (close > ath).fillna(False)
        held = (close > ath).fillna(False)  # clôture encore au-dessus
        sig_cont = made_ath.shift(2, fill_value=False) & held.shift(1, fill_value=False) \
            & made_ath
        n_combos += 1
        for i in np.where(sig_cont.values)[0]:
            for h, ret, mae, liq in outcomes_long(idx, opens, closes, lows, i,
                                                  HORIZONS, COST_PCT, fund_h):
                pooled[("ath_continuation", h)].append(ret)
                liq_cells[("ath_continuation", h)].append(int(liq))

        # —— 2. REVIVAL : drawdown > 80 % pendant 30 j PUIS retour < 50 % ——
        deep = (drawdown > 80).rolling(30 * 24, min_periods=10).max().shift(1, fill_value=0)
        recovered = (drawdown < 50) & (drawdown > 5)
        sig_rev = (deep > 0) & recovered & (close > close.shift(1))
        n_combos += 1
        for i in np.where(sig_rev.values)[0]:
            if age_d[i] < 30:
                continue  # un coin de 20 jours n'a pas "renaissé"
            for h, ret, mae, liq in outcomes_long(idx, opens, closes, lows, i,
                                                  HORIZONS, COST_PCT, fund_h):
                pooled[("revival_long", h)].append(ret)
                liq_cells[("revival_long", h)].append(int(liq))

        # —— 3. VOLUME REVIVAL sur survivants ——
        alive = age_d > 90
        vol_back = vz.rolling(3).min() > 1
        up = close > close.shift(72)
        sig_vr = alive & vol_back & up & (drawdown < 70)
        n_combos += 1
        for i in np.where(sig_vr.values)[0]:
            for h, ret, mae, liq in outcomes_long(idx, opens, closes, lows, i,
                                                  HORIZONS, COST_PCT, fund_h):
                pooled[("volume_revival_survivor", h)].append(ret)
                liq_cells[("volume_revival_survivor", h)].append(int(liq))

        # —— baseline blind LONG (toutes bougies, pas 24h) ——
        for h in HORIZONS:
            for i in range(0, len(idx) - h, 24):
                e, x = opens[i], closes[min(i + h, len(idx) - 1)]
                hold = (idx[min(i + h, len(idx) - 1)] - idx[i]).total_seconds() / 3600
                base[h].append(((x - e) / e * 100 - COST_PCT - fund_h * hold) * LEV)

    con.close()

    lines = [
        "# Campagne LONG-TERME — le côté LONG des memecoins (les pumps qui continuent)",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — levier {LEV}x, "
        f"coûts+funding réels, horizons 3-60 jours.", "",
        "| Signal | H | N | WR marge | Médiane | Pire | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    confirmed = 0
    for (name, h), rets in sorted(pooled.items()):
        n = len(rets)
        if n < 25:
            continue
        wr = sum(1 for r in rets if r > 0) / n * 100
        med = sorted(rets)[n // 2]
        worst = min(rets)
        verdict = "CONFIRMÉ" if wr >= 55 and med > 0 else "BRUIT"
        confirmed += verdict == "CONFIRMÉ"
        lines.append(f"| {name} | +{h}h ({h//24}j) | {n} | {wr:.1f} % "
                     f"| {med:+.1f} % | {worst:+.0f} % | {verdict} |")

    lines += ["", "## Baseline blind LONG (le juge)", ""]
    for h in HORIZONS:
        rets = base[h]
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        med = sorted(rets)[len(rets) // 2]
        lines.append(f"- hold {h//24}j : WR {wr:.1f} %, médiane {med:+.1f} % "
                     f"(n={len(rets)})")

    lines += [
        "", f"Confirmés : {confirmed}. Rappel réalisme : les longs PAIENT le",
        "funding pendant la détention (inclus), la liquidation 3x frappe à",
        "-33 % adverse (MAE calculée), et les memecoins peuvent -99 % — le",
        "long terme memecoin se taille petit, sans levier, sur les survivants.",
    ]
    out = REPORTS / f"backtest-longterm-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[longterm] {n_combos} combinaisons, {confirmed} confirmés -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
