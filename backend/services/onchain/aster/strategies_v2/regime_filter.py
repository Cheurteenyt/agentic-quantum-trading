"""Regime & volatility filter for strategies_v2.

Pure functions over OHLCV arrays. No I/O, no external state. Designed to be
called per-candle by the backtester and by live forward monitors.

Key idea (lesson from dead Aster suite): in an extreme-volatility regime a
single-directional stateful position gets cooked. We quantify regime with ATR
vs its own rolling median and a gap-risk detector, and we expose a per-candle
`regime` tag the strategy uses to size down or skip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


@dataclass
class RegimeConfig:
    atr_period: int = 14
    vol_median_period: int = 168          # ~7 days of 1h candles
    vol_expand_threshold: float = 1.8     # ATR / median ATR above this => "extreme"
    vol_contract_threshold: float = 0.6   # below this => "calm"
    gap_pct_threshold: float = 0.012      # 1.2% open-gap vs prior close => gap risk
    max_leverage_in_extreme: float = 2.0  # hard cap when regime is extreme
    max_leverage_normal: float = 5.0


@dataclass
class RegimeFrame:
    atr: float
    atr_median: float
    vol_ratio: float                       # atr / atr_median
    regime: str                            # "calm" | "normal" | "extreme"
    gap_risk: bool
    allowed_leverage: float


def true_range(high: float, low: float, prev_close: float) -> float:
    return float(max(high - low, abs(high - prev_close), abs(low - prev_close)))


def atr_series(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
               period: int = 14) -> list[float]:
    tr = [float("nan")]
    for i in range(1, len(highs)):
        tr.append(true_range(highs[i], lows[i], closes[i - 1]))
    out: list[float] = [float("nan")] * len(tr)
    if len(tr) > period:
        out[period] = float(np.nanmean(tr[1:period + 1]))
        for i in range(period + 1, len(tr)):
            out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def rolling_median(x: Sequence[float], window: int) -> list[float]:
    out: list[float] = [float("nan")] * len(x)
    for i in range(len(x)):
        lo = max(0, i - window + 1)
        seg = [v for v in x[lo:i + 1] if not np.isnan(v)]
        if seg:
            out[i] = float(np.median(seg))
    return out


def frame_at(index: int, highs: Sequence[float], lows: Sequence[float],
             opens: Sequence[float], closes: Sequence[float],
             cfg: RegimeConfig | None = None) -> RegimeFrame:
    cfg = cfg or RegimeConfig()
    atr = atr_series(highs, lows, closes, cfg.atr_period)
    atr_med = rolling_median(atr, cfg.vol_median_period)
    a = atr[index]
    m = atr_med[index]
    vol_ratio = (a / m) if (m and not np.isnan(m) and m > 0) else float("nan")
    if np.isnan(vol_ratio):
        regime = "normal"
    elif vol_ratio >= cfg.vol_expand_threshold:
        regime = "extreme"
    elif vol_ratio <= cfg.vol_contract_threshold:
        regime = "calm"
    else:
        regime = "normal"
    gap_risk = False
    if index > 0 and closes[index - 1] != 0:
        gap = abs(opens[index] - closes[index - 1]) / closes[index - 1]
        gap_risk = gap >= cfg.gap_pct_threshold
    allowed = cfg.max_leverage_normal if regime != "extreme" else cfg.max_leverage_in_extreme
    return RegimeFrame(atr=a, atr_median=m, vol_ratio=vol_ratio, regime=regime,
                       gap_risk=gap_risk, allowed_leverage=allowed)


def size_multiplier(frame: RegimeFrame) -> float:
    """Position-size multiplier the strategy applies to its base size."""
    if frame.regime == "extreme":
        return 0.4 if not frame.gap_risk else 0.0   # skip in gap risk
    if frame.regime == "calm":
        return 1.0
    return 0.7
