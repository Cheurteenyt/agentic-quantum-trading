#!/usr/bin/env python
"""Le MOTEUR D'ENTRÉES — le point d'entrée comme citoyen de première classe.

Trois règles d'entrée simulées avec leurs fills exacts :

  next_open : ordre au marché à l'open de la bougie suivant le signal
              (l'entrée naïve du harnais) + slippage mesuré
  limit     : ordre limite à un niveau précis (ex : le retest du niveau
              cassé, le pullback vwap) — remplit SEULEMENT si le prix
              touche le niveau dans la fenêtre d'attente
  market_now: ordre au marché immédiatement au signal (le prix de clôture
              de la bougie de signal)

Chaque règle retourne : rempli (oui/non), prix de fill exact, timestamp.
Le backtest consomme ces fills — l'entrée n'est plus une approximation.

  .venv/bin/python scripts/entry_rules.py --demo failed_ath
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402

KDB = ROOT / 'data' / 'warehouse' / 'klines.db'


def fill_next_open(df: pd.DataFrame, signal_ts: pd.Timestamp,
                   slip_bps: float = 10.0) -> tuple[bool, float | None, pd.Timestamp | None]:
    i = int(df.index.searchsorted(signal_ts, side="right"))
    if i >= len(df.index):
        return False, None, None
    px = df["open"].values[i]
    return True, px * (1 + slip_bps / 10000), df.index[i]


def fill_limit(df: pd.DataFrame, signal_ts: pd.Timestamp, level: float,
               direction: int, window_bars: int = 72) -> tuple[bool, float | None, pd.Timestamp | None]:
    """Ordre limite : remplit quand le prix TOUCHE le niveau (pour un short,
    le prix doit MONTER au niveau). Fill exact au niveau de l'ordre."""
    i0 = int(df.index.searchsorted(signal_ts, side="right"))
    for k in range(i0, min(i0 + window_bars, len(df.index))):
        hi, lo = df["high"].values[k], df["low"].values[k]
        if direction < 0 and hi >= level:
            return True, level, df.index[k]
        if direction > 0 and lo <= level:
            return True, level, df.index[k]
    return False, None, None


def fill_market_now(df: pd.DataFrame, signal_ts: pd.Timestamp,
                    slip_bps: float = 10.0) -> tuple[bool, float | None, pd.Timestamp | None]:
    i = int(df.index.searchsorted(signal_ts, side="left"))
    if i >= len(df.index):
        return False, None, None
    px = df["close"].values[i]
    return True, px * (1 + slip_bps / 10000), df.index[i]


def demo_failed_ath(sym: str = "MEMEUSDT") -> int:
    """Le failed_ATH avec les 3 entrées côte à côte sur les derniers événements."""
    con = sqlite3.connect(KDB)
    df = load_df(con, sym)
    con.close()
    if df is None or len(df) < 500:
        print("pas de données")
        return 1
    close = df["close"]
    ath = close.cummax().shift(1)
    made = (close > ath).fillna(False).astype(bool)
    failed = made.shift(1, fill_value=False) & (close < ath.shift(1)).fillna(True)
    ev_idx = df.index[failed]
    print(f"{sym} : {len(ev_idx)} événements failed_ATH — les 3 dernières entrées comparées :\n")
    for ts in ev_idx[-3:]:
        t_pos = int(df.index.searchsorted(ts, side="right"))
        ath_level = float(ath.loc[ts]) if ts in ath.index else None
        if ath_level is None:
            continue
        retest_level = ath_level * 0.995  # le retest à -0,5 % de l'ATH raté
        fills = {}
        ok, px, ft = fill_next_open(df, ts)
        fills["next_open (marché)"] = (ok, px, ft)
        ok, px, ft = fill_limit(df, ts, retest_level, -1, window_bars=72)
        fills["retest limit -0,5 %"] = (ok, px, ft)
        ok, px, ft = fill_market_now(df, ts)
        fills["market au signal"] = (ok, px, ft)
        print(f"  signal {ts:%d/%m %H:%M} — ATH raté à {ath_level:.6g} :")
        for k, (ok, px, ft) in fills.items():
            if ok:
                print(f"    {k:22s} : REMPLI @ {px:.6g} ({ft:%d/%m %H:%M})")
            else:
                print(f"    {k:22s} : NON rempli (le retest n'est jamais monté)")
        print()
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--demo":
        raise SystemExit(demo_failed_ath(sys.argv[2]))
    raise SystemExit(demo_failed_ath())
