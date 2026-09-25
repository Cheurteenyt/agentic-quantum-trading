#!/usr/bin/env python
"""L'AUDIT DES SIGNAUX — re-vérification indépendante, à la main.

Les cross-checks comparaient deux implémentations ; si les deux
partagent un même bug de définition, il passe. Ici chaque signal est
re-calculé depuis les VALEURS BRUTES (numpy pur, boucles explicites,
aucun helper pandas/ta partagé) sur les événements qu'il a émis :
  - cascade accélérée (anti_liq)   : 3 clôtures baisse + accélération
  - vwap_extreme_reprise_short     : dev > 3σ(168)
  - sweep_liquidite_short          : mèche > prior_high + 0,15 ATR14
  - failed_ath_breakout_short      : ATH raté
Un seul mismatch = le signal est marqué et corrigé.

  .venv/bin/python scripts/signal_audit.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df, price_signals  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series  # noqa: E402

SAMPLE = 5


def wilder_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
               i: int, period: int = 14) -> float:
    """ATR de Wilder recalculé à la main jusqu'à la bougie i."""
    trs = []
    for j in range(max(1, i - period * 3), i + 1):
        tr = max(highs[j] - lows[j],
                 abs(highs[j] - closes[j - 1]),
                 abs(lows[j] - closes[j - 1]))
        trs.append(tr)
    atr = trs[0]
    for tr in trs[1:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def audit_cascade(con: sqlite3.Connection) -> tuple[int, int]:
    regime = btc_regime_series()
    events = [e for e in collect_featured(regime, "majors")
              if e["sym"] == "BTCUSDT"][:SAMPLE]
    df = load_df(con, "BTCUSDT")
    c = df["close"].values
    idx_ns = df.index.astype("datetime64[ns]").asi8
    ok = bad = 0
    for e in events:
        t = int(np.searchsorted(idx_ns, e["ts_ms"], side="left")) - 1  # signal
        r1 = c[t] / c[t - 1] - 1
        r2 = c[t - 1] / c[t - 2] - 1
        r3 = c[t - 2] / c[t - 3] - 1
        good = (r1 < 0 and r2 < 0 and r3 < 0
                and abs(r1) > abs(r2) > abs(r3))
        ok, bad = ok + good, bad + (not good)
        if not good:
            print(f"  ✗ cascade {e['sym']} ts={e['ts_ms']} : "
                  f"r=({r1:+.4f}, {r2:+.4f}, {r3:+.4f})")
    return ok, bad


def audit_signal(con: sqlite3.Connection, name: str, symbols: list[str],
                 check) -> tuple[int, int]:
    ok = bad = 0
    for sym in symbols:
        df = load_df(con, sym)
        if df is None:
            continue
        btc = load_df(con, "BTCUSDT")
        sig = dict((n, (d, s)) for n, d, s in price_signals(df, btc))
        if name not in sig:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        fired = df.index[sig[name][1].fillna(False)]
        for t in list(np.where(sig[name][1].fillna(False))[0])[-SAMPLE:]:
            if check(df, int(t)):
                ok += 1
            else:
                bad += 1
                print(f"  ✗ {name} {sym} barre {t} "
                      f"({df.index[t]}) : condition non reproduite")
    return ok, bad


def main() -> int:
    con = sqlite3.connect(KDB)

    print("== CASCADE (3 clôtures baisse + accélération) ==")
    ok, bad = audit_cascade(con)
    print(f"  {ok} vérifiés, {bad} mismatch\n")

    def chk_vwap(df: pd.DataFrame, t: int) -> bool:
        c = df["close"].values
        tp = (df["high"].values + df["low"].values + c) / 3
        v = df["volume"].values

        def vwap_at(j: int) -> float:
            lo_j = j - 167
            return (tp[lo_j:j + 1] * v[lo_j:j + 1]).sum() / v[lo_j:j + 1].sum()

        devs = [(c[j] - vwap_at(j)) / vwap_at(j) for j in range(t - 167, t + 1)]
        return devs[-1] > 3 * float(np.std(devs))

    print("== VWAP_EXTREME_SHORT (dev > 3σ des 168 dernières bougies) ==")
    ok, bad = audit_signal(con, "vwap_extreme_reprise_short",
                           ["BTCUSDT", "ETHUSDT", "SOLUSDT"], chk_vwap)
    print(f"  {ok} vérifiés, {bad} mismatch\n")

    def chk_sweep(df: pd.DataFrame, t: int) -> bool:
        h = df["high"].values
        l = df["low"].values
        c = df["close"].values
        prior_high = h[t - 20:t].max()
        atr = wilder_atr(h, l, c, t)
        return h[t] > prior_high + 0.15 * atr and c[t] < prior_high

    print("== SWEEP_SHORT (mèche > prior_high 20b + 0,15 ATR, clôture dessous) ==")
    ok, bad = audit_signal(con, "sweep_liquidite_short",
                           ["BTCUSDT", "ETHUSDT", "SOLUSDT"], chk_sweep)
    print(f"  {ok} vérifiés, {bad} mismatch\n")

    def chk_failed(df: pd.DataFrame, t: int) -> bool:
        c = df["close"].values
        prior_max = c[:t - 1].max()          # max(close[0..t-2])
        made = c[t - 1] > c[:t - 1].max()    # t-1 clôture au-dessus de tout
        return made and c[t] < prior_max

    print("== FAILED_ATH_SHORT (t-1 nouvel ATH en clôture, t clôture dessous) ==")
    ok, bad = audit_signal(con, "failed_ath_breakout_short",
                           ["BTCUSDT", "ETHUSDT", "SOLUSDT"], chk_failed)
    print(f"  {ok} vérifiés, {bad} mismatch\n")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
