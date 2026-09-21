"""Volatility-breakout strategy (Piste 1, strategies_v2).

Directional: emits BOTH long and short signals. The legacy Aster suite was
long-only stateful and got cooked in an extreme regime; this one flips side
with the breakout direction and bows out when the regime filter says "extreme
+ gap risk".

Signal (per candle, evaluated on close):
- band = ema_close +/- k * atr   (k configurable, default 2.0)
- long  if close > upper_band AND not gap_risk AND funding not violently against
- short if close < lower_band AND not gap_risk AND funding not violently against
- exit when price crosses back inside the band (or hard ATR-multiple stop)

Funding guard (perps): if |lastFundingRate| > funding_skip_threshold we skip the
trade in that direction (a one-sided crowded book is a liquidation trap).
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

FUNDING_SKIP_ABS = 0.0009   # ~0.09% per 8h funding => crowded, skip that side


@dataclass
class VolBreakoutConfig:
    ema_period: int = 50
    atr_period: int = 14
    k: float = 2.0
    stop_atr_mult: float = 3.0
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


def ema_series(x: list[float], period: int) -> list[float]:
    out = [float("nan")] * len(x)
    if not x:
        return out
    alpha = 2.0 / (period + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * alpha + out[i - 1] * (1 - alpha)
    return out


def signal_at(index: int, opens: list[float], highs: list[float], lows: list[float],
              closes: list[float], funding_rates: Optional[list[float]],
              cfg: VolBreakoutConfig | None = None) -> Signal:
    cfg = cfg or VolBreakoutConfig()
    if index < max(cfg.ema_period, cfg.atr_period) + 1:
        return Signal("flat", 0.0, cfg.regime.max_leverage_normal, "warmup")

    ema = ema_series(closes, cfg.ema_period)
    # ATR reuse
    from services.onchain.aster.strategies_v2.regime_filter import atr_series
    atr = atr_series(highs, lows, closes, cfg.atr_period)
    band = cfg.k * atr[index]
    upper = ema[index] + band
    lower = ema[index] - band

    frame: RegimeFrame = frame_at(index, highs, lows, opens, closes, cfg.regime)
    mult = size_multiplier(frame)
    if mult == 0.0:
        return Signal("flat", 0.0, frame.allowed_leverage, "extreme+gap_risk")

    fund = 0.0
    if funding_rates is not None and index < len(funding_rates) and funding_rates[index] is not None:
        fund = funding_rates[index]
    fund_skip_long = fund <= -FUNDING_SKIP_ABS     # shorts crowding => long trap
    fund_skip_short = fund >= FUNDING_SKIP_ABS      # longs crowding => short trap

    close = closes[index]
    if close > upper and not fund_skip_long:
        return Signal("long", mult, frame.allowed_leverage, f"breakout_up atr={atr[index]:.4f}")
    if close < lower and not fund_skip_short:
        return Signal("short", mult, frame.allowed_leverage, f"breakout_dn atr={atr[index]:.4f}")
    return Signal("flat", mult, frame.allowed_leverage, "inside_band")
