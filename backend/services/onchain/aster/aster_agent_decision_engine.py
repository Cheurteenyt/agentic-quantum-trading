from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from services.onchain.aster.aster_agent_foundation import get_aster_order_book_anomaly_detection_test


class AgentState(Enum):
    IDLE = "idle"
    OBSERVING = "observing"
    ANALYZING = "analyzing"
    DECIDING = "deciding"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    EXITING = "exiting"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_csv(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw = [str(item or "").strip() for item in value]
    else:
        raw = [item.strip() for item in str(value or "").split(",")]
    return [item for item in raw if item] or default


def _audit(event: str, state: AgentState, status: str, **extra: Any) -> dict[str, Any]:
    return {"ts": _now(), "component": "aster_agent_decision_engine", "event": event, "state": state.value, "status": status, **extra}


def should_enter_position(
    aster_score: float,
    behavioral_score: float | None = None,
    volume_24h_usd: float = 0.0,
    min_aster_score: float = 70.0,
    min_behavioral_score: float = 60.0,
    min_volume_usd: float = 50_000.0,
) -> bool:
    if aster_score < min_aster_score:
        return False
    if behavioral_score is not None and behavioral_score < min_behavioral_score:
        return False
    if volume_24h_usd < min_volume_usd:
        return False
    return True


def should_exit_position(
    entry_price: float,
    current_price: float,
    stop_loss_pct: float = -15.0,
    take_profit_pct: float = 50.0,
) -> tuple[bool, str]:
    if entry_price <= 0 or current_price <= 0:
        return False, "price_unavailable"
    pnl_pct = ((current_price - entry_price) / entry_price) * 100
    if pnl_pct <= stop_loss_pct:
        return True, "stop_loss_triggered"
    if pnl_pct >= take_profit_pct:
        return True, "take_profit_triggered"
    return False, "holding"


def calculate_position_size(
    wallet_balance_usd: float,
    max_position_pct: float = 5.0,
    aster_score: float = 0.0,
) -> float:
    safe_balance = max(0.0, wallet_balance_usd)
    safe_pct = max(0.0, min(max_position_pct, 5.0))
    base_size = safe_balance * (safe_pct / 100)
    score_multiplier = min(2.0, max(0.0, aster_score) / 50)
    return round(base_size * score_multiplier, 2)


def _current_price_from_row(row: dict[str, Any]) -> float | None:
    snapshots = row.get("order_book_snapshots") if isinstance(row.get("order_book_snapshots"), list) else []
    metrics = (snapshots[-1].get("metrics") if snapshots and isinstance(snapshots[-1], dict) else {}) or {}
    bid = _as_float(metrics.get("best_bid"))
    ask = _as_float(metrics.get("best_ask"))
    if bid > 0 and ask > 0:
        return round((bid + ask) / 2, 12)
    return None


def _behavioral_score(row: dict[str, Any]) -> float | None:
    context = row.get("dex_behavioral_context") if isinstance(row.get("dex_behavioral_context"), dict) else {}
    value = context.get("behavioral_score")
    return None if value is None else _as_float(value)


def _volume_24h(row: dict[str, Any]) -> float:
    volume = row.get("volume_anomaly") if isinstance(row.get("volume_anomaly"), dict) else {}
    return _as_float(volume.get("volume_24h_usd"))


def _disabled() -> dict[str, Any]:
    return {
        "source_policy": "aster_agent_decision_engine_dry_run_only_phase_3",
        "would_execute_trade": False,
        "would_send_transaction": False,
        "would_write_db": False,
        "would_create_client_signal": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "writes_performed": 0,
    }


async def agent_loop(
    wallet_address: str | None = None,
    symbols: str | list[str] | None = "BTCUSDT",
    token_addresses: str | list[str] | None = None,
    dry_run: bool = True,
    max_cycles: int = 1,
    timeout_seconds: int = 8,
    wallet_balance_usd: float | None = None,
    max_position_pct: float = 5.0,
    stop_loss_pct: float = -15.0,
    take_profit_pct: float = 50.0,
) -> dict[str, Any]:
    disabled = _disabled()
    if not dry_run:
        return {"ok": False, "dry_run": False, "agent_status": "blocked", "blockers": ["dry_run_required"], **disabled}

    safe_cycles = max(1, min(int(max_cycles or 1), 3))
    safe_timeout = max(1, min(int(timeout_seconds or 8), 10))
    safe_balance = _as_float(wallet_balance_usd if wallet_balance_usd is not None else os.getenv("ASTER_AGENT_DRY_RUN_BALANCE_USD", "1000"))
    positions: dict[str, dict[str, Any]] = {}
    decisions: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    state = AgentState.IDLE

    for cycle in range(safe_cycles):
        state = AgentState.OBSERVING
        audit.append(_audit("observe", state, "started", cycle=cycle + 1))
        preview = await asyncio.to_thread(
            get_aster_order_book_anomaly_detection_test,
            symbols,
            token_addresses,
            "bsc",
            True,
            safe_timeout,
            5,
            1,
            0,
            100,
        )
        state = AgentState.ANALYZING
        rows = [row for row in preview.get("results") or [] if isinstance(row, dict)]
        audit.append(_audit("analyze", state, "ready", candidates=len(rows)))

        state = AgentState.DECIDING
        for row in rows:
            symbol = str(row.get("symbol") or "")
            token = str(row.get("token_address") or symbol)
            aster_score = _as_float(row.get("combined_anomaly_score") or row.get("aster_anomaly_score"))
            behavioral = _behavioral_score(row)
            volume = _volume_24h(row)
            price = _current_price_from_row(row)
            enter = should_enter_position(aster_score, behavioral, volume)
            decision = {
                "symbol": symbol,
                "token_address": row.get("token_address"),
                "state": state.value,
                "aster_score": round(aster_score, 2),
                "behavioral_score": behavioral,
                "volume_24h_usd": volume,
                "current_price": price,
                "should_enter": enter,
                "reason": "entry_rules_passed" if enter else "entry_rules_not_met",
            }
            if enter and token not in positions:
                state = AgentState.EXECUTING
                size = calculate_position_size(safe_balance, max_position_pct, aster_score)
                positions[token] = {"symbol": symbol, "entry_price": price, "size_usd": size, "entry_time": _now(), "dry_run_position": True}
                decision.update({"state": state.value, "position_size_usd": size, "execution_status": "simulated_only_dry_run"})
            decisions.append(decision)

        state = AgentState.MONITORING if positions else AgentState.IDLE
        for token, position in list(positions.items()):
            current = _as_float(position.get("entry_price"))
            should_exit, reason = should_exit_position(_as_float(position.get("entry_price")), current, stop_loss_pct, take_profit_pct)
            decisions.append({"token": token, "state": state.value, "monitor_status": reason, "should_exit": should_exit, "execution_status": "simulated_only_dry_run"})
            if should_exit:
                state = AgentState.EXITING
                del positions[token]
        audit.append(_audit("cycle_complete", state, "ready", open_positions=len(positions)))

    return {
        "ok": True,
        "dry_run": True,
        "agent_status": "ready",
        "current_state": state.value,
        "wallet_address": wallet_address,
        "wallet_balance_usd_assumed": safe_balance,
        "risk_management": {"max_position_pct": min(max_position_pct, 5.0), "stop_loss_pct": stop_loss_pct, "take_profit_pct": take_profit_pct},
        "positions_open": positions,
        "decisions": decisions,
        "audit_events": audit,
        "blockers": [],
        **disabled,
    }


def run_aster_agent_loop_test(
    wallet_address: str | None = None,
    symbols: str | list[str] | None = "BTCUSDT",
    token_addresses: str | list[str] | None = None,
    dry_run: bool = True,
    max_cycles: int = 1,
    timeout_seconds: int = 8,
    wallet_balance_usd: float | None = None,
) -> dict[str, Any]:
    return asyncio.run(agent_loop(wallet_address, symbols, token_addresses, dry_run, max_cycles, timeout_seconds, wallet_balance_usd))
