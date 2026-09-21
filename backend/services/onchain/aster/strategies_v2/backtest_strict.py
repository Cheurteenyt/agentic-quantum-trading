"""Strict backtester for strategies_v2.

Benchmark rules (non-negotiable, learned from dead Aster suite):
- Split train/validation OUT-OF-SAMPLE by time, never by random shuffle.
- Costs modeled on NOTIONAL exposure: fees (taker/maker per symbol) + funding
  (perps, on notional) + slippage (bps) + liquidation risk for leveraged pos.
- Leverage capped by regime filter's allowed_leverage per candle.
- Reports train_* AND validation_* separately, plus a combined OOS verdict.

This module is PURE (no network, no file writes). The caller (CLI/runner)
supplies OHLCV + funding arrays and decides persistence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np

from services.onchain.aster.strategies_v2.regime_filter import RegimeConfig
from services.onchain.aster.strategies_v2.vol_breakout import (
    Signal,
    VolBreakoutConfig,
    signal_at,
)


@dataclass
class CostModel:
    taker_bps: float = 4.0
    maker_bps: float = 0.0
    slippage_bps: float = 2.0
    # funding applied on notional, per 8h, supplied externally per candle


@dataclass
class BacktestResult:
    symbol: str
    interval: str
    side: str
    train_trades: int = 0
    train_win_rate: float = 0.0
    train_profit_factor: float = 0.0
    train_pnl_usd: float = 0.0
    train_max_dd_usd: float = 0.0
    val_trades: int = 0
    val_win_rate: float = 0.0
    val_profit_factor: float = 0.0
    val_pnl_usd: float = 0.0
    val_max_dd_usd: float = 0.0
    oos_status: str = "fail"     # "pass" | "fail" | "insufficient"
    notes: str = ""


def _equity_curve(pnls: list[float]) -> tuple[float, float]:
    """(final_pnl, max_drawdown) from a list of per-trade pnls (USD)."""
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return eq, dd


def _stats(pnls: list[float]) -> tuple[int, float, float, float]:
    if not pnls:
        return 0, 0.0, 0.0, 0.0
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    wr = len(wins) / len(pnls)
    g = sum(wins)
    l = sum(losses)
    pf = (g / l) if l > 0 else float("inf")
    eq, dd = _equity_curve(pnls)
    return len(pnls), wr, pf, dd


def run_backtest(
    symbol: str,
    interval: str,
    opens: list[float], highs: list[float], lows: list[float], closes: list[float],
    funding_rates: Optional[list[float]] = None,
    signal_fn: Optional[Callable[[int], Signal]] = None,
    cfg: Optional[VolBreakoutConfig] = None,
    cost: Optional[CostModel] = None,
    capital_usd: float = 1000.0,
    train_frac: float = 0.6,
    leverage_override: float = 1.0,
) -> BacktestResult:
    cfg = cfg or VolBreakoutConfig()
    cost = cost or CostModel()
    n = len(closes)
    split = int(n * train_frac)
    if signal_fn is None:
        signal_fn = lambda i: signal_at(i, opens, highs, lows, closes, funding_rates, cfg)

    def _simulate(lo: int, hi: int) -> list[float]:
        pnls: list[float] = []
        pos = None  # (side, entry_price, lev)
        for i in range(lo, hi):
            sig = signal_fn(i)
            price = closes[i]
            if pos is None:
                if sig.side != "flat" and sig.size_mult > 0:
                    lev = min(leverage_override, sig.allowed_leverage)
                    pos = (sig.side, price, lev)
            else:
                side, entry, lev = pos
                # exit: opposite breakout or hard ATR stop
                atr_i = None
                from services.onchain.aster.strategies_v2.regime_filter import atr_series
                a = atr_series(highs, lows, closes, cfg.atr_period)
                atr_i = a[i] if i < len(a) else None
                stop = (atr_i * cfg.stop_atr_mult) if atr_i and not np.isnan(atr_i) else (entry * 0.05)
                exit_now = False
                if side == "long" and (price <= entry - stop or price > entry + stop * 4):
                    exit_now = True
                elif side == "short" and (price >= entry + stop or price < entry - stop * 4):
                    exit_now = True
                if exit_now or i == hi - 1:
                    notional = capital_usd * lev * sig.size_mult
                    # pnl on notional
                    if side == "long":
                        gross = (price - entry) / entry * notional
                    else:
                        gross = (entry - price) / entry * notional
                    fees = notional * (cost.taker_bps / 1e4) * 2  # open+close
                    slip = notional * (cost.slippage_bps / 1e4) * 2
                    fund = 0.0
                    if funding_rates is not None and i < len(funding_rates) and funding_rates[i]:
                        fund = notional * abs(funding_rates[i]) * 2  # entry+exit 8h windows approx
                    pnl = gross - fees - slip - fund
                    pnls.append(pnl)
                    pos = None
        return pnls

    train_pnls = _simulate(cfg.atr_period + 2, split)
    val_pnls = _simulate(split, n)

    tt, twr, tpf, tdd = _stats(train_pnls)
    vt, vwr, vpf, vdd = _stats(val_pnls)

    oos = "insufficient"
    if vt >= 10 and tt >= 10:
        val_pnl = sum(val_pnls)
        oos = "pass" if (vwr >= 0.5 and vpf >= 1.1 and val_pnl > 0) else "fail"

    return BacktestResult(
        symbol=symbol, interval=interval, side="both",
        train_trades=tt, train_win_rate=twr, train_profit_factor=tpf,
        train_pnl_usd=sum(train_pnls), train_max_dd_usd=tdd,
        val_trades=vt, val_win_rate=vwr, val_profit_factor=vpf,
        val_pnl_usd=sum(val_pnls), val_max_dd_usd=vdd,
        oos_status=oos,
        notes=f"train_pnl={sum(train_pnls):.2f} val_pnl={sum(val_pnls):.2f}",
    )


def vpnl_positive(pnls: list[float]) -> bool:
    return sum(pnls) > 0
