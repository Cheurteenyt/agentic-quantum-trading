"""Strategies v2 — viable crypto strategies for extreme-volatility regimes.

Post-Aster cleanup (2026-08-09). These are NEW modules. They DO NOT modify any
existing runner. They are read-only on market data and paper-only by design.

Design rules (see docs/strategy-roadmap-2026-08.md):
- directional (long AND short)
- regime/vol filter
- strict train/validation OOS benchmark from day one
- real costs (fees + funding on notional + slippage + liquidation risk)
- microstructure validation via legacy tools before any promotion
"""
from __future__ import annotations

__all__ = [
    "regime_filter",
    "vol_breakout",
    "funding_mean_reversion",
    "backtest_strict",
]
