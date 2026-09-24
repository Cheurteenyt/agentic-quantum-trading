#!/usr/bin/env python
"""Ingénierie du failed_ATH : entrée RETEST vs entrée directe.

Le pattern : bougie t-1 fait un ATH absolu, bougie t clôture sous l'ancien
ATH → short. Trois variantes d'ENTRÉE sur le même événement :

  directe : open de la bougie t+1 (l'entrée naïve du harnais v5)
  retest  : on ATTEND que le prix rebondisse vers le niveau cassé
            (dans les 72 bougies suivantes, high ≥ ancien ATH × (1 − 0,5 %))
            et on shorte à ce niveau — entrée plus haute = médiane plus forte
  retest+stop : pareil, mais stop si le prix repasse AU-DESSUS de l'ancien
            ATH × (1 + 1 %) → le pattern est invalidé, perte bornée

La profondeur de cassure (close sous l'ancien ATH) est bucketée : une
cassure marginale ≠ une cassure franche. Horizons 72h/168h/720h/1440h.
Coûts réels + funding réel pendant détention, comme le harnais v5.
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
from scripts import aster_indicators as ta  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
LEV = 3  # levier réaliste memecoins (plafond exchangeInfo)
HORIZONS = (72, 168, 720, 1440)
RETEST_WINDOW = 72   # bougies pour que le retest se produise
RETEST_GAP = 0.005   # le retest doit revenir à ≤ 0,5 % sous l'ancien ATH
STOP_ABOVE = 1.01    # stop si le prix repasse à +1 % au-dessus de l'ATH raté


def funding_hourly(con) -> dict[str, float]:
    import statistics
    by_sym: dict[str, list[float]] = defaultdict(list)
    by_ts: dict[str, list[float]] = defaultdict(list)
    for s, t, rate in con.execute("SELECT symbol, funding_time, rate FROM funding_history"):
        try:
            by_sym[s].append(float(rate))
            by_ts[s].append(float(t))
        except (TypeError, ValueError):
            continue
    out: dict[str, float] = {}
    for s, rates in by_sym.items():
        ts = sorted(by_ts[s])
        gaps = [(ts[i + 1] - ts[i]) / 3600000 for i in range(len(ts) - 1)
                if 0 < ts[i + 1] - ts[i] < 40000000]
        iv = statistics.median(gaps) if gaps else 8.0
        out[s] = (statistics.mean(rates) * 100) / max(iv, 0.5)
    return out


def main() -> int:
    con = sqlite3.connect(KDB)
    funding = funding_hourly(con)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]

    store: dict[tuple[str, int], list[float]] = defaultdict(list)
    depth_buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    n_events = 0
    for sym in sorted(symbols):
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        close, opens = df["close"], df["open"]
        closes, opens_v = close.values, opens.values
        highs = df["high"].values
        idx = df.index
        fund_h = funding.get(sym, 0.0)

        ath = close.cummax().shift(1)
        made_ath = (close > ath).fillna(False)
        failed = made_ath.shift(1, fill_value=False) & (close < ath.shift(1, fill_value=False))
        n_events += int(failed.sum())

        for t_pos in np.where(failed.values)[0]:
            if t_pos + 1 >= len(idx):
                continue
            ath_level = ath.values[t_pos]
            fail_close = closes[t_pos]
            depth = (ath_level - fail_close) / ath_level * 100  # % sous l'ATH
            entry_ts_ms = idx[t_pos + 1].value // 10**6

            # ——— variante 1 : ENTRÉE DIRECTE (naïve) ———
            for h in HORIZONS:
                j = t_pos + 1 + h - 1
                if j >= len(idx):
                    continue
                hold_h = (idx[j] - idx[t_pos + 1]).total_seconds() / 3600
                ret = ((closes[j] - opens_v[t_pos + 1]) / opens_v[t_pos + 1] * 100
                       - COST_PCT - fund_h * hold_h) * LEV
                store[(f"directe_{h}h", "todo")].append(ret)
                d_bucket = ("0-1 %" if depth < 1 else "1-3 %" if depth < 3 else ">3 %")
                depth_buckets[(f"directe_{h}h", d_bucket)].append(ret)

            # ——— variante 2/3 : RETEST (avec ou sans stop) ———
            retest_level = ath_level * (1 - RETEST_GAP)
            stop_level = ath_level * STOP_ABOVE
            filled = False
            for k in range(t_pos + 1, min(t_pos + 1 + RETEST_WINDOW, len(idx))):
                if highs[k] >= retest_level:
                    # retest touché : entrée au niveau du retest
                    for h in HORIZONS:
                        j = k + h
                        if j >= len(idx):
                            continue
                        hold_h = (idx[j] - idx[k]).total_seconds() / 3600
                        ret = ((closes[j] - retest_level) / retest_level * 100
                               - COST_PCT - fund_h * hold_h) * LEV
                        # stop : le prix a-t-il repassé le stop entre k et j ?
                        stopped = (highs[k:j + 1].max() >= stop_level)
                        if stopped:
                            # sortie contrôlée au stop : perte bornée
                            # (~1,5 % adverse × 3 levier), pas une liquidation
                            ret = -((stop_level - retest_level) / retest_level
                                    * 100 * LEV + COST_PCT * LEV)
                        store[(f"retest_{h}h", "todo")].append(ret if not stopped else ret)
                        d_bucket = ("0-1 %" if depth < 1 else "1-3 %" if depth < 3 else ">3 %")
                        depth_buckets[(f"retest_{h}h", d_bucket)].append(ret)
                    filled = True
                    break
                if highs[k] >= stop_level:
                    break  # le pattern est invalidé avant le retest
    con.close()

    # ——— rapport ———
    lines = [
        "# failed_ATH — ingénierie d'entrée (directe vs retest vs retest+stop)",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {n_events} événements, "
        f"levier {LEV}x, coûts {COST_PCT} % + funding réel, retest ≤ 72 bougies.",
        "",
        "## Entrée DIRECTE (naïve, référence du harnais v5)", "",
        "| Horizon | N | WR | Médiane marge |", "|---|---|---|---|",
    ]
    for (kind, h), rets in sorted(store.items()):
        if not kind.startswith("directe") or len(rets) < 10:
            continue
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        lines.append(f"| {h} | {len(rets)} | {wr:.1f} % | {sorted(rets)[len(rets)//2]:+.1f} % |")

    lines += ["", "## Entrée RETEST (rebond vers le niveau cassé)", "",
              "| Horizon | N | WR | Médiane marge |", "|---|---|---|---|"]
    for (kind, h), rets in sorted(store.items()):
        if not kind.startswith("retest") or len(rets) < 10:
            continue
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        lines.append(f"| {h} | {len(rets)} | {wr:.1f} % | {sorted(rets)[len(rets)//2]:+.1f} % |")

    lines += ["", "## Profondeur de cassure (entrée directe, horizons 720/1440h)", "",
              "| Profondeur | H | N | WR | Médiane |", "|---|---|---|---|---|"]
    for (kind, d_bucket), rets in sorted(depth_buckets.items()):
        if not kind.startswith("directe") or len(rets) < 10:
            continue
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        lines.append(f"| {d_bucket} | {kind.replace('directe_', '')} | {len(rets)} "
                     f"| {wr:.1f} % | {sorted(rets)[len(rets)//2]:+.1f} % |")

    out = REPORTS / f"backtest-retest-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[retest] {n_events} événements failed_ATH -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
