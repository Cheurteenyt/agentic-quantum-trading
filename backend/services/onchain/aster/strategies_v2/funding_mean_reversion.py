"""Funding mean-reversion strategy (Piste 2, strategies_v2).

On perps Aster: when funding is extremely one-sided (crowded book) AND price is
stretched, fade the consensus. Guards against trending regimes (the thing that
killed naive mean-reversion) with a trend filter from the close slope.

DIRECTIONAL and contrarian: goes long when shorts are crowded+stretched-down,
short when longs are crowded+stretched-up. Pair this with regime_filter so it
bows out in extreme volatility (where fades get run over).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

from services.onchain.aster.strategies_v2.regime_filter import (
    RegimeConfig,
    RegimeFrame,
    frame_at,
    size_multiplier,
)

Side = Literal["long", "short", "flat"]

FUNDING_EXTREME_ABS = 0.0009   # 0.09% per 8h => crowded
TREND_SLOPE_PERIOD = 20


@dataclass
class FundingMRConfig:
    funding_extreme_abs: float = FUNDING_EXTREME_ABS
    trend_period: int = TREND_SLOPE_PERIOD
    regime: RegimeConfig = None  # type: ignore

    def __post_init__(self):
        if self.regime is None:
            self.regime = RegimeConfig()


@dataclass
class Signal:
    side: Side
    size_mult: float
    allowed_leverage: float
    reason: str


def _slope(closes: list[float], index: int, period: int) -> float:
    lo = max(0, index - period)
    seg = closes[lo:index + 1]
    if len(seg) < 2:
        return 0.0
    return (seg[-1] - seg[0]) / seg[0]


def signal_at(index: int, opens: list[float], highs: list[float], lows: list[float],
              closes: list[float], funding_rates: Optional[list[float]],
              cfg: FundingMRConfig | None = None) -> Signal:
    cfg = cfg or FundingMRConfig()
    if funding_rates is None or index >= len(funding_rates) or funding_rates[index] is None:
        return Signal("flat", 0.0, cfg.regime.max_leverage_normal, "no_funding")
    if index < cfg.trend_period + 1:
        return Signal("flat", 0.0, cfg.regime.max_leverage_normal, "warmup")

    frame: RegimeFrame = frame_at(index, highs, lows, opens, closes, cfg.regime)
    mult = size_multiplier(frame)
    if mult == 0.0:
        return Signal("flat", 0.0, frame.allowed_leverage, "extreme+gap_risk")

    fund = funding_rates[index]
    slope = _slope(closes, index, cfg.trend_period)

    # Shorts crowded (fund<0 extreme) + price stretched down + not strong downtrend => long fade
    if fund <= -cfg.funding_extreme_abs and slope > -0.01:
        return Signal("long", mult, frame.allowed_leverage, f"fade_crowded_shorts fund={fund:.5f}")
    # Longs crowded (fund>0 extreme) + price stretched up + not strong uptrend => short fade
    if fund >= cfg.funding_extreme_abs and slope < 0.01:
        return Signal("short", mult, frame.allowed_leverage, f"fade_crowded_longs fund={fund:.5f}")
    return Signal("flat", mult, frame.allowed_leverage, "no_edge")
