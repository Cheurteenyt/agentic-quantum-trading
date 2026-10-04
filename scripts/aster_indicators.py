#!/usr/bin/env python
"""Batterie d'indicateurs techniques — calculs maison sur les klines Aster.

Chaque fonction prend un DataFrame (colonnes open/high/low/close/volume,
index temporel croissant) et retourne une Series alignée. Implémentations
manuelles (pas de lib TA) : lisible, vérifiable, aucune dépendance.

C'est le socle du backtest : des SIGNAUX discrets (événements datés) que
backtest_indicators.py évalue avec la discipline du registre.
"""
from __future__ import annotations

import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI de Wilder STRICT (FIX audit v3, C17).

    Seed = SMA des n premiers deltas (le classique de Wilder 1978), puis le
    lissage moyenne-alpha. Pertes nulles → RS infini → RSI 100 (et non NaN) ;
    gains nuls → RSI 0. Les n premiers points sont NaN (pas de seed inventé).
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.copy() * float("nan")
    avg_loss = loss.copy() * float("nan")
    if len(delta) > n:
        avg_gain.iloc[n] = gain.iloc[1:n + 1].mean()
        avg_loss.iloc[n] = loss.iloc[1:n + 1].mean()
        for i in range(n + 1, len(delta)):
            avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (n - 1)
                                + gain.iloc[i]) / n
            avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (n - 1)
                                + loss.iloc[i]) / n
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi_v = 100 - 100 / (1 + rs)
    return rsi_v.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0).where(
        ~((avg_gain == 0) & (avg_loss == 0)), 50.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26,
         sig: int = 9) -> tuple[pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    return line, line.ewm(span=sig, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std()
    return mid - k * sd, mid, mid + k * sd


def bandwidth(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    lo, mid, hi = bollinger(close, n, k)
    return (hi - lo) / mid


def donchian_high(df: pd.DataFrame, n: int = 20) -> pd.Series:
    return df["high"].rolling(n).max().shift(1)


def donchian_low(df: pd.DataFrame, n: int = 20) -> pd.Series:
    return df["low"].rolling(n).min().shift(1)


def stoch(df: pd.DataFrame, n: int = 14, d: int = 3):
    lo = df["low"].rolling(n).min()
    hi = df["high"].rolling(n).max()
    k = 100 * (df["close"] - lo) / (hi - lo)
    return k, k.rolling(d).mean()


def roc(close: pd.Series, n: int = 10) -> pd.Series:
    return close.pct_change(n) * 100


def volume_z(volume: pd.Series, n: int = 20) -> pd.Series:
    m = volume.rolling(n).mean()
    s = volume.rolling(n).std()
    return (volume - m) / s.where(s > 0)  # where() garde le dtype float (NaN, pas NA)


def obv(df: pd.DataFrame) -> pd.Series:
    direction = df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * df["volume"]).cumsum()


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """True à la bougie où a passe AU-DESSUS de b."""
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))
