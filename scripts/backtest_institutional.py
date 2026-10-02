#!/usr/bin/env python
"""Les CRASHS INSTITUTIONNELS — les 3σ dumps conditionnés par la foule piégée.

L'idée : un 3σ dump dans le VIDE (personne n'est positionné) = bruit.
Un 3σ dump quand les LONGS sont BONDÉS (le funding était extrême) = les
institutions qui liquident la foule → la continuation est beaucoup plus
forte, parce que les liquidations forcées alimentent la cascade.

Les signaux conditionnés :
  A. crash_3sigma SEUL (la référence : le signal non-conditionné)
  B. crash_3sigma + funding > p75  (la foule longue piégée → short)
  C. crash_3sigma + funding < p25  (la foule courte piégée → long, le squeeze)
  D. crash_3sigma + funding > p90  (l'extrême = les institutions ciblent)
  E. crash_3sigma + vol 3× + funding > p75 (le triple confluence)

La comparaison A vs B/C/D/E = L'EDGE ADDITIONNEL du conditionnement.
La géométrie : stop 1,2 % / target 2,4 % à 20x (le profil du crash_accel).

  .venv/bin/python scripts/backtest_institutional.py
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
MAX_BARS = 24


def walk(df, entry_i, direction, stop_pct, target_pct, max_bars):
    """La marche stop/target : le stop d'abord = perte conservatrice."""
    entry = df["open"].values[entry_i]
    stop_px = entry * (1 - stop_pct / 100) if direction > 0 else entry * (1 + stop_pct / 100)
    tgt_px = entry * (1 + target_pct / 100) if direction > 0 else entry * (1 - target_pct / 100)
    lows, highs = df["low"].values, df["high"].values
    for k in range(entry_i, min(entry_i + max_bars, len(df.index))):
        lo, hi = lows[k], highs[k]
        if direction > 0:
            if lo <= stop_px:
                return "stop", -stop_pct * LEV
            if hi >= tgt_px:
                return "target", target_pct * LEV
        else:
            if hi >= stop_px:
                return "stop", -stop_pct * LEV
            if lo <= tgt_px:
                return "target", target_pct * LEV
    x = df["close"].values[min(entry_i + max_bars, len(df.index) - 1)]
    ret = (x - entry) / entry * 100 * direction - COST_NOTIONAL
    return "timeout", ret


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
    ret_sigma = 2.5

    # les résultats par condition
    conditions = [
        ("A_crash_seul", "crash_seul", None),
        ("B_crash_funding_p75", "funding_extreme_pos", 0.75),
        ("C_crash_funding_p25", "funding_extreme_neg", 0.25),
        ("D_crash_funding_p90", "funding_extreme_pos", 0.90),
        ("E_crash_vol3x", "crash_volume3x", None),
    ]
    results: dict[str, dict] = defaultdict(lambda: {"n": 0, "wins": 0, "sum": 0.0, "liq": 0})

    for sym in majors:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        ret1 = df["close"].pct_change() * 100
        sigma = ret1.rolling(168).std()
        vol_z = ((df["volume"] - df["volume"].rolling(168).mean())
                 / df["volume"].rolling(168).std().where(lambda s: s > 0))
        # le funding : les derniers taux avant chaque bougie (expanding)
        fh = pd.read_sql_query("SELECT funding_time, rate FROM funding_history WHERE symbol=?",
                               con, params=(sym,))
        if len(fh) >= 30:
            fh = fh.sort_values("funding_time")
            s_idx = pd.to_datetime(fh["funding_time"].astype(float), unit="ms")
            rate_s = pd.Series(fh["rate"].astype(float).values, index=s_idx)
            aligned = rate_s.reindex(df.index, method="ffill", limit=8)
            # le percentile rolling du funding (sans look-ahead)
            fund_pctile = aligned.rolling(168, min_periods=30).rank(pct=True).shift(1)
        else:
            fund_pctile = pd.Series(0.5, index=df.index)

        crash3 = (ret1 <= -ret_sigma * sigma).fillna(False)
        crash3_up = (ret1 >= ret_sigma * sigma).fillna(False)
        vol3x = (vol_z >= 3).fillna(False)

        # les événements par condition
        events: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i in np.where(crash3)[0]:
            if i + 2 >= len(df.index):
                continue
            events["A_crash_seul"].append((i, -1))
            fp = fund_pctile.iloc[i] if i < len(fund_pctile) else 0.5
            if pd.notna(fp) and fp >= 0.75:
                events["B_crash_funding_p75"].append((i, -1))
            if pd.notna(fp) and fp <= 0.25:
                events["C_crash_funding_p25"].append((i, +1))  # les shorts piégés → long squeeze
            if pd.notna(fp) and fp >= 0.90:
                events["D_crash_funding_p90"].append((i, -1))
            if vol3x.iloc[i]:
                events["E_crash_vol3x"].append((i, -1))
        for i in np.where(crash3_up)[0]:
            if i + 2 >= len(df.index):
                continue
            fp = fund_pctile.iloc[i] if i < len(fund_pctile) else 0.5
            if pd.notna(fp) and fp <= 0.25:
                events["C_crash_funding_p25"].append((i, +1))  # les shorts piégés → squeeze long

        for cond_name, _fam, _th in conditions:
            if cond_name not in events:
                continue
            d = results[cond_name]
            for i, direction in events[cond_name]:
                outcome, margin = walk(df, i + 1, direction, STOP_PCT, TARGET_PCT, MAX_BARS)
                liq = margin <= -100
                d["n"] += 1
                d["wins"] += outcome == "target"
                d["sum"] += margin
                d["liq"] += liq
    con.close()

    lines = [
        "# LES CRASHS INSTITUTIONNELS — les 3σ dumps conditionnés par la foule",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — 6 majeures, 1 an, "
        f"levier {LEV}x, stop {STOP_PCT} % / target {TARGET_PCT} %.", "",
        "| Condition | N | WR target | Liq | Espérance marge |", "|---|---|---|---|---|",
    ]
    for cond_name, _fam, _th in conditions:
        d = results[cond_name]
        n = d["n"]
        if n < 15:
            continue
        wr = d["wins"] / n * 100
        exp = d["sum"] / n
        liq = d["liq"] / n * 100
        lines.append(f"| {cond_name} | {n} | {wr:.1f} % | {liq:.1f} % | {exp:+.1f} % |")

    # l'edge additionnel du conditionnement
    a = results.get("A_crash_seul", {"sum": 0, "n": 1})
    exp_a = a["sum"] / max(a["n"], 1)
    lines += ["", "## L'EDGE ADDITIONNEL du conditionnement funding", ""]
    for cond_name in ("B_crash_funding_p75", "D_crash_funding_p90"):
        d = results[cond_name]
        if d["n"] < 15:
            continue
        exp = d["sum"] / d["n"]
        lines.append(f"- **{cond_name}** : espérance {exp:+.1f} % vs A {exp_a:+.1f} % "
                     f"= edge additionnel {exp - exp_a:+.1f} %")

    out = REPORTS / f"backtest-institutional-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[institutional] {len(results)} conditions -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
