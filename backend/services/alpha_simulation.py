"""Alpha Lab counterfactual simulation engines."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PredictionTrade(BaseModel):
    """Flexible trade input for prediction-market copy simulations."""

    model_config = ConfigDict(extra="allow")

    side: str = "buy"
    market_id: str = ""
    ticker: str | None = None
    outcome: str = ""
    asset: str | None = None
    price: float = 0.0
    size_usd: float = 0.0
    notional_usd: float | None = None
    mark_price: float | None = None
    current_price: float | None = None


class PredictionCopyInput(BaseModel):
    capital: float = 100.0
    lag_seconds: float = 60.0
    slippage_bps: float = 75.0
    fee_bps: float = 0.0
    max_trade_pct: float = 0.25
    trades: list[PredictionTrade] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_max_trade_pct(self) -> "PredictionCopyInput":
        if not (0.01 <= self.max_trade_pct <= 1.0):
            raise ValueError("max_trade_pct must be between 0.01 and 1.0")
        return self


class PredictionCopyResult(BaseModel):
    mode: str = "prediction_copy"
    capital: float
    current_value: float
    pnl: float
    roi_pct: float
    cash: float
    positions: dict[str, dict[str, float]] = Field(default_factory=dict)
    copied_trades: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)


class ManipulationEvent(BaseModel):
    """Flexible event input for manipulation counterfactual simulations."""

    model_config = ConfigDict(extra="allow")

    token: str = "unknown"
    symbol: str | None = None
    chain: str = "unknown"
    network: str | None = None
    confidence: float = 0.0
    entry_price: float = 0.0
    detection_price: float | None = None
    exit_price: float | None = None
    current_price: float | None = None
    risk: dict[str, Any] | None = None
    signal: str | None = None
    type: str | None = None


class ManipulationInput(BaseModel):
    capital: float = 100.0
    allocation_pct: float = 0.2
    confidence_threshold: float = 0.65
    take_profit_pct: float = 0.35
    stop_loss_pct: float = 0.12
    events: list[ManipulationEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_ranges(self) -> "ManipulationInput":
        if not (0.01 <= self.allocation_pct <= 1.0):
            raise ValueError("allocation_pct must be between 0.01 and 1.0")
        if not (0.0 <= self.confidence_threshold <= 1.0):
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        return self


class ManipulationResult(BaseModel):
    mode: str = "manipulation_counterfactual"
    capital: float
    ending_value: float
    pnl: float
    roi_pct: float
    trades: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)


def simulate_prediction_copy(payload: dict[str, Any]) -> dict[str, Any]:
    inp = PredictionCopyInput(**(payload or {}))

    capital = _float(inp.capital, 100.0)
    lag_seconds = max(0.0, _float(inp.lag_seconds, 60.0))
    slippage_bps = max(0.0, _float(inp.slippage_bps, 75.0))
    fee_bps = max(0.0, _float(inp.fee_bps, 0.0))
    max_trade_pct = inp.max_trade_pct
    trades = inp.trades

    remaining_cash = capital
    positions: dict[str, dict[str, float]] = {}
    copied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for trade in trades:
        side = str(trade.side or "buy").lower()
        market_id = str(trade.market_id or trade.ticker or "unknown")
        outcome = str(trade.outcome or trade.asset or "YES")
        key = f"{market_id}:{outcome}"
        observed_price = _bounded_probability(_float(trade.price, 0.0))
        trade_dump = trade.model_dump()
        if observed_price <= 0:
            skipped.append({"reason": "missing_price", "trade": trade_dump})
            continue

        fill_price = _apply_probability_cost(observed_price, side, slippage_bps, fee_bps)
        requested_usd = _float(trade.size_usd or trade.notional_usd, capital * max_trade_pct)
        allocation = min(requested_usd, capital * max_trade_pct, remaining_cash)

        if side in {"sell", "short"}:
            pos = positions.get(key)
            if not pos or pos["shares"] <= 0:
                skipped.append({"reason": "no_position_to_sell", "trade": trade_dump})
                continue
            shares_to_sell = min(pos["shares"], allocation / max(fill_price, 0.01))
            proceeds = shares_to_sell * fill_price
            pos["shares"] -= shares_to_sell
            remaining_cash += proceeds
            copied.append({
                "market_id": market_id,
                "outcome": outcome,
                "side": "sell",
                "observed_price": observed_price,
                "fill_price": fill_price,
                "shares": shares_to_sell,
                "cash_after": remaining_cash,
                "lag_seconds": lag_seconds,
            })
            continue

        if allocation <= 0:
            skipped.append({"reason": "cash_exhausted", "trade": trade_dump})
            continue

        shares = allocation / fill_price
        pos = positions.setdefault(key, {"shares": 0.0, "cost": 0.0, "mark_price": fill_price})
        pos["shares"] += shares
        pos["cost"] += allocation
        pos["mark_price"] = _bounded_probability(
            _float(trade.mark_price if trade.mark_price is not None else trade.current_price, fill_price)
        )
        remaining_cash -= allocation
        copied.append({
            "market_id": market_id,
            "outcome": outcome,
            "side": "buy",
            "observed_price": observed_price,
            "fill_price": fill_price,
            "allocation": allocation,
            "shares": shares,
            "cash_after": remaining_cash,
            "lag_seconds": lag_seconds,
        })

    current_value = remaining_cash
    for pos in positions.values():
        current_value += pos["shares"] * pos["mark_price"]

    pnl = current_value - capital
    return PredictionCopyResult(
        capital=capital,
        current_value=round(current_value, 6),
        pnl=round(pnl, 6),
        roi_pct=round(_safe_ratio(pnl, capital) * 100, 4),
        cash=round(remaining_cash, 6),
        positions=positions,
        copied_trades=copied,
        skipped=skipped,
        assumptions={
            "lag_seconds": lag_seconds,
            "slippage_bps": slippage_bps,
            "fee_bps": fee_bps,
            "max_trade_pct": max_trade_pct,
            "note": "Backtest only. Live fills need orderbook depth and timestamped liquidity snapshots.",
        },
    ).model_dump()


def simulate_manipulation_strategy(
    payload: dict[str, Any],
    risk_analyzer: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    inp = ManipulationInput(**(payload or {}))

    capital = _float(inp.capital, 100.0)
    allocation_pct = inp.allocation_pct
    confidence_threshold = inp.confidence_threshold
    take_profit_pct = max(0.0, _float(inp.take_profit_pct, 0.35))
    stop_loss_pct = max(0.0, _float(inp.stop_loss_pct, 0.12))
    events = inp.events

    cash = capital
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for event in events:
        event_dump = event.model_dump()
        token_risk = risk_analyzer(event.risk if isinstance(event.risk, dict) else event_dump)
        if token_risk["block_trade"]:
            skipped.append({"reason": "token_risk_block", "risk": token_risk, "event": event_dump})
            continue

        confidence = min(1.0, max(0.0, _float(event.confidence, 0.0)))
        risk_penalty = min(0.35, token_risk["risk_score"] / 300.0)
        effective_confidence = max(0.0, confidence - risk_penalty)
        if effective_confidence < confidence_threshold:
            skipped.append({
                "reason": "low_confidence_after_risk",
                "confidence": confidence,
                "effective_confidence": round(effective_confidence, 4),
                "risk": token_risk,
                "event": event_dump,
            })
            continue

        entry_price = _float(event.entry_price or event.detection_price, 0.0)
        if entry_price <= 0:
            skipped.append({"reason": "missing_entry_price", "event": event_dump})
            continue

        allocation = min(capital * allocation_pct, cash)
        if allocation <= 0:
            skipped.append({"reason": "cash_exhausted", "event": event_dump})
            continue

        target_price = entry_price * (1.0 + take_profit_pct)
        stop_price = entry_price * (1.0 - stop_loss_pct)
        observed_exit = _float(event.exit_price if event.exit_price is not None else event.current_price, entry_price)
        exit_reason = "observed_exit"
        if observed_exit >= target_price:
            exit_price = target_price
            exit_reason = "take_profit"
        elif observed_exit <= stop_price:
            exit_price = stop_price
            exit_reason = "stop_loss"
        else:
            exit_price = observed_exit

        qty = allocation / entry_price
        exit_value = qty * exit_price
        pnl = exit_value - allocation
        cash += pnl
        trades.append({
            "token": event.token or event.symbol or "unknown",
            "chain": event.chain or event.network or "unknown",
            "signal": event.signal or event.type or "manipulation_candidate",
            "confidence": confidence,
            "effective_confidence": round(effective_confidence, 4),
            "risk_score": token_risk["risk_score"],
            "profit_integrity": token_risk["profit_integrity"],
            "allocation": round(allocation, 6),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "pnl": round(pnl, 6),
            "roi_pct": round(_safe_ratio(pnl, allocation) * 100, 4),
        })

    pnl_total = cash - capital
    return ManipulationResult(
        capital=capital,
        ending_value=round(cash, 6),
        pnl=round(pnl_total, 6),
        roi_pct=round(_safe_ratio(pnl_total, capital) * 100, 4),
        trades=trades,
        skipped=skipped,
        assumptions={
            "allocation_pct": allocation_pct,
            "confidence_threshold": confidence_threshold,
            "take_profit_pct": take_profit_pct,
            "stop_loss_pct": stop_loss_pct,
            "note": "Counterfactual only. Production needs timestamped liquidity, MEV/slippage, contract proofs, and successful sell proofs.",
        },
    ).model_dump()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def _bounded_probability(value: float) -> float:
    return min(0.999, max(0.001, value))


def _apply_probability_cost(price: float, side: str, slippage_bps: float, fee_bps: float) -> float:
    adjustment = (slippage_bps + fee_bps) / 10000.0
    if side in {"sell", "short"}:
        return _bounded_probability(price * (1.0 - adjustment))
    return _bounded_probability(price * (1.0 + adjustment))
