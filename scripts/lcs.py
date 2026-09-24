#!/usr/bin/env python
"""LCS — Lifecycle Composite Score : TOUT le savoir du projet en un chiffre.

Par coin et par jour (SANS look-ahead : chaque composante n'utilise que le
passé), quatre dimensions VÉRIFIÉES par les campagnes précédentes :

  1. ÉTIREMENT VWAP   : déviation au vwap 7j, en σ (l'épuisement géométrique)
  2. ACCEL FUNDING    : pente du funding sur 3 règlements (la foule s'empile)
  3. DRAWDOWN         : dans la bande 20-50 % (la zone de chasse du short)
  4. ÂGE              : dans la zone 7-90 j (la période de mort)

Chaque composante est normalisée en percentile ROLLING (le score d'hier ne
sait rien de demain) puis agrégé : LCS ∈ [0, 100]. LCS haut = terrain short.

Backtest : winrate du SHORT 24h par décile de LCS (lag d'un jour : le score
d'hier prédit aujourd'hui). Baseline incluse.

  .venv/bin/python scripts/lcs.py --backtest     # la preuve sur 1 an
  .venv/bin/python scripts/lcs.py --today        # la carte de chasse du jour
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df, COST_PCT  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"


def rolling_pctile(s: pd.Series, window: int = 90) -> pd.Series:
    """Percentile de la valeur courante dans les `window` jours précédents
    (fenêtre décalée d'un jour — zéro look-ahead)."""
    ranks = s.rolling(window).rank(pct=True)
    return ranks.shift(1)


def symbol_lcs(df: pd.DataFrame, rate_s: pd.Series | None) -> pd.DataFrame:
    close = df["close"]
    daily = close.resample("1D").last().dropna()
    out = pd.DataFrame(index=daily.index)
    out["close"] = daily

    # 1. étirement vwap (dernier σ du jour)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = ((tp * df["volume"]).rolling(168).sum()
            / df["volume"].rolling(168).sum().where(lambda s: s > 0))
    dev = ((df["close"] - vwap) / vwap).astype(float)
    dev_sd = dev.rolling(168).std()
    stretch = (dev / dev_sd.where(lambda s: s > 0)).resample("1D").last()
    out["stretch_sig"] = rolling_pctile(stretch, 90)

    # 2. accélération de funding (dernière valeur du jour)
    if rate_s is not None:
        aligned = rate_s.reindex(df.index, method="ffill", limit=8)
        accel = aligned.diff(3).resample("1D").last()
        out["funding_sig"] = rolling_pctile(accel, 90)
    else:
        out["funding_sig"] = 0.5

    # 3. drawdown dans la bande 20-50 %
    dd = (1 - close / close.cummax()) * 100
    dd_d = dd.resample("1D").last()
    out["dd_sig"] = ((dd_d >= 20) & (dd_d <= 50)).astype(float)

    # 4. âge dans la zone 7-90 j
    age_d = (daily.index - df.index[0]).total_seconds() / 86400
    out["age_sig"] = ((age_d >= 7) & (age_d <= 90)).astype(float)

    # LCS : moyenne des 4 composantes × 100
    out["lcs"] = (out["stretch_sig"].fillna(0.5) + out["funding_sig"].fillna(0.5)
                  + out["dd_sig"] + out["age_sig"]) / 4 * 100
    # rendement futur 24h (la cible du backtest)
    out["fwd24"] = (daily.shift(-1) / daily - 1) * 100
    return out.dropna(subset=["lcs"])


def main() -> int:
    ap = sys.argv[1] if len(sys.argv) > 1 else "--backtest"
    con = sqlite3.connect(KDB)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]
    fh = pd.read_sql_query("SELECT symbol, funding_time, rate FROM funding_history", con)

    all_days: list[pd.DataFrame] = []
    for sym in sorted(symbols):
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        g = fh[fh.symbol == sym]
        rate_s = None
        if len(g) >= 30:
            g = g.sort_values("funding_time")
            s_idx = pd.to_datetime(g["funding_time"].astype(float), unit="ms")
            rate_s = pd.Series(g["rate"].astype(float).values, index=s_idx)
        ldf = symbol_lcs(df, rate_s)
        ldf["symbol"] = sym
        all_days.append(ldf)
    con.close()
    panel = pd.concat(all_days)

    if ap == "--today":
        today = panel[panel.index == panel.index.max()].sort_values("lcs", ascending=False)
        print(f"LCS du {panel.index.max():%d/%m/%Y} — la carte de chasse du jour :")
        for sym, row in today.head(12).iterrows():
            tag = "SHORT-TERRAIN" if row["lcs"] >= 75 else ("long-terrain" if row["lcs"] <= 25 else "")
            print(f"  {sym:14s} LCS {row['lcs']:.0f} {tag}")
        return 0

    # backtest : short 24h conditionné au LCS D'HIER (lag 1 jour)
    panel["lcs_lag"] = panel.groupby("symbol")["lcs"].shift(1)
    panel["decile"] = pd.qcut(panel["lcs_lag"], 10, labels=False, duplicates="drop")
    lines = [
        "# LCS — le score composite (vwap + funding + drawdown + âge)",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — backtest 1 an, "
        "score d'HIER → short 24h aujourd'hui (zéro look-ahead).", "",
        "| Décile LCS (hier) | N | WR short 24h | Médiane |", "|---|---|---|---|",
    ]
    for d in sorted(panel["decile"].dropna().unique()):
        sub = panel[panel["decile"] == d].dropna(subset=["fwd24"])
        if len(sub) < 50:
            continue
        rets = sub["fwd24"].values * (-1) - COST_PCT  # short
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        lines.append(f"| D{int(d)+1} | {len(rets)} | {wr:.1f} % | {sorted(rets)[len(rets)//2]:+.2f} % |")

    top = panel[panel["lcs_lag"] >= 75].dropna(subset=["fwd24"])
    if len(top) >= 30:
        rets = top["fwd24"].values * (-1) - COST_PCT
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        lines += ["", f"**LCS ≥ 75** : N={len(rets)}, WR short 24h **{wr:.1f} %**, "
                  f"médiane {sorted(rets)[len(rets)//2]:+.2f} %"]

    out = REPORTS / f"lcs-backtest-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[lcs] {len(panel)} jours×symboles -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
