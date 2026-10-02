#!/usr/bin/env python
"""LE FILTRE DE RÉGIME — quand les shorts marchent et quand ils tuent.

Le régime est défini par BTC (la référence du marché) :
  - TENDANCE : close > EMA(7j) = haussier, close < EMA(7j) = baissier
  - VOLATILITÉ : l'ATR(24h) au-dessus/en-dessous de sa médiane 30j

Les 4 régimes : haussier/vol_basse, haussier/vol_haute,
               baissier/vol_basse, baissier/vol_haute

Le test : le WR de la cascade short conditionné par le régime.
Si le WR varie fortement par régime → le filtre de régime = le gate
qui réduit le drawdown en bloquant les trades dans le mauvais régime.

  .venv/bin/python scripts/regime_filter.py
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
COST = 0.28
STOP_PCT = 1.2
H = 8


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval = '1h' "
        "AND symbol != 'BTCUSDT' ORDER BY symbol")]
    btc = load_df(con, "BTCUSDT")
    if btc is None or len(btc) < 500:
        print("pas de BTC", file=sys.stderr)
        return 1
    close_btc = btc["close"]
    ema7 = close_btc.ewm(span=7, adjust=False).mean()
    trend = np.where(close_btc > ema7, "haussier", "baissier")
    ret1 = close_btc.pct_change() * 100
    atr = (close_btc - close_btc.shift(1)).abs().rolling(24).mean()
    atr_med = atr.rolling(30 * 24, min_periods=100).median()
    vol_reg = np.where(atr > atr_med, "vol_haute", "vol_basse")
    regime = [f"{t}/{v}" for t, v in zip(trend, vol_reg)]
    btc_regime = pd.Series(regime, index=btc.index)

    # les résultats par régime
    regime_stats: dict[str, dict] = defaultdict(lambda: {"n": 0, "w": 0, "s": 0.0})
    gated = {"n": 0, "w": 0, "s": 0.0}
    ungated = {"n": 0, "w": 0, "s": 0.0}
    no_slaughter = {"n": 0, "w": 0, "s": 0.0}

    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        close = df["close"]
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        r1 = close.pct_change() * 100
        ra = r1.abs()
        cascade = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
                   & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        # le régime du symbole = le régime BTC à chaque bougie
        sym_regime = btc_regime.reindex(idx, method="ffill", limit=48).fillna("?")
        gate_bear = pd.Series(
            np.where(sym_regime.str.contains("baissier"), 1, 0), index=idx)

        for t in np.where(cascade)[0]:
            if t + 1 + H >= len(idx_ns):
                continue
            entry_i = t + 1
            entry = df["open"].values[entry_i]
            if entry <= 0:
                continue
            exit_open = idx_ns[entry_i] + H * 3600 * 10**9
            j = int(np.searchsorted(idx_ns, exit_open, side="left"))
            if j >= len(idx_ns):
                continue
            x = df["close"].values[j]
            margin = max((x - entry)/entry*100*(-1) * LEV, -STOP_PCT * LEV) - COST * LEV
            regime_name = sym_regime.iloc[entry_i] if entry_i < len(sym_regime) else "?"
            regime_stats[regime_name]["n"] += 1
            regime_stats[regime_name]["w"] += margin > 0
            regime_stats[regime_name]["s"] += margin
            # gate = on trade SEULEMENT en régime baissier
            if entry_i < len(gate_bear) and gate_bear.iloc[entry_i]:
                gated["n"] += 1; gated["w"] += margin > 0; gated["s"] += margin
            # gate inverse = on exclut SEULEMENT le quadrant massacre
            if regime_name != "haussier/vol_haute":
                no_slaughter["n"] += 1; no_slaughter["w"] += margin > 0; no_slaughter["s"] += margin
            ungated["n"] += 1; ungated["w"] += margin > 0; ungated["s"] += margin
    con.close()

    # le rapport
    lines = [
        "# LE FILTRE DE RÉGIME — quand les shorts marchent",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"le régime = BTC trend × volatilité, évalué à l'entrée de chaque trade.", "",
        "## Le WR de la cascade short PAR RÉGIME", "",
        "| Régime | N | WR | Esp marge (lev 20x) |", "|---|---|---|---|",
    ]
    for reg, d in sorted(regime_stats.items()):
        if d["n"] < 10:
            continue
        wr = d["w"] / d["n"] * 100
        avg = d["s"] / d["n"]
        lines.append(f"| {reg} | {d['n']} | {wr:.1f} % | {avg:+.1f} % |")

    lines += ["", "## L'impact des GATES (lev 20x)", ""]
    for label, d in (("SANS gate", ungated),
                     ("AVEC gate (baissier only)", gated),
                     ("GATE anti-massacre (exclut haussier/vol_haute)", no_slaughter)):
        if d["n"] < 10:
            continue
        wr = d["w"] / d["n"] * 100
        avg = d["s"] / d["n"]
        lines.append(f"- {label} : N={d['n']}, WR {wr:.1f} %, "
                     f"espérance {avg:+.1f} % de marge")

    if gated["n"] > 0 and ungated["n"] > 0:
        wr_g = gated["w"] / gated["n"] * 100
        wr_u = ungated["w"] / ungated["n"] * 100
        wr_ns = no_slaughter["w"] / no_slaughter["n"] * 100 if no_slaughter["n"] else 0
        sd_u = (wr_u * (100 - wr_u) / ungated["n"]) ** 0.5
        lines += ["", f"**Gate baissier : {wr_g - wr_u:+.1f} pts de WR "
                  f"({wr_g:.1f} vs {wr_u:.1f}, sd ≈ {sd_u:.1f} pts → faible)**",
                  f"**Gate anti-massacre : {wr_ns - wr_u:+.1f} pts de WR**"]

    out = REPORTS / f"regime-filter-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[regime] {len(regime_stats)} régimes, {len(ungated)} trades -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
