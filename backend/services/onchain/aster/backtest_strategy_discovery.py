from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.aster_perps_model import (
    exchange_info_reality_verdict,
    funding_cost_usd_estimate,
    get_public_exchange_info_snapshot,
    get_public_funding_history_snapshot,
    perps_assumptions,
    round_trip_fee_usd,
)
from services.onchain.aster.aster_paper_trading_sandbox import (
    EXTENDED_BACKTEST_SYMBOLS,
    get_aster_paper_trading_focused_optimization_preview,
)


CSV_FILE = Path(__file__).with_name("paper_trading_strategy_discovery.csv")
JSON_FILE = Path(__file__).with_name("paper_trading_strategy_discovery_latest.json")
ROTATION_FILE = Path(__file__).with_name("paper_trading_strategy_rotation_latest.json")
HEARTBEAT_FILE = Path(__file__).with_name("paper_trading_strategy_discovery_heartbeat.json")
MARK_INDEX_FILE = Path(__file__).with_name("aster_mark_index_replay_filter_latest.json")
WS_QUALITY_FILE = Path(__file__).with_name("aster_ws_symbol_quality_report_latest.json")
SCHEMA_VERSION = "aster_strategy_discovery_v2_1"

LOW_INTERVALS = "15m,30m,1h"
HIGH_INTERVALS = "2h,3h,4h,5h,6h"
DEFAULT_LEVERAGE_VALUES = [1.0, 2.0, 3.0, 5.0]
DEFAULT_MAINTENANCE_MARGIN_RATE = 0.005
DEFAULT_FUNDING_BPS_PER_8H = 1.0
ASTER_COMMODITY_SYMBOLS = [
    "XAUUSDT",
    "XAGUSDT",
    "CLUSDT",
    "BZUSDT",
    "CRCLUSDT",
    "ORCLUSDT",
]
ASTER_EQUITY_SYMBOLS = [
    "AAPLUSDT",
    "TSLAUSDT",
    "NVDAUSDT",
    "AMZNUSDT",
    "METAUSDT",
    "MSFTUSDT",
    "INTCUSDT",
    "MSTRUSDT",
    "GOOGLUSDT",
    "DRAMUSDT",
    "COINUSDT",
    "AMDUSDT",
]
SYMBOL_PRESETS = {
    "core": list(EXTENDED_BACKTEST_SYMBOLS),
    "macro": ASTER_COMMODITY_SYMBOLS,
    "equities": ASTER_EQUITY_SYMBOLS,
    "macro_equity": [*ASTER_COMMODITY_SYMBOLS, *ASTER_EQUITY_SYMBOLS],
    "all": [*EXTENDED_BACKTEST_SYMBOLS, *ASTER_COMMODITY_SYMBOLS, *ASTER_EQUITY_SYMBOLS],
}

HEADERS = [
    "timestamp",
    "run_id",
    "batch_id",
    "symbol_group",
    "intervals",
    "tested_combinations",
    "accepted_candidates",
    "rank",
    "symbol",
    "interval",
    "risk_profile",
    "min_aster_score",
    "min_window_volume_usd",
    "closed_trades",
    "win_rate",
    "profit_factor",
    "pnl_total_usd",
    "roi_pct_on_paper_balance",
    "max_drawdown_usd",
    "positive_windows",
    "verdict",
]

V2_HEADERS = [
    "schema_version",
    "timestamp",
    "run_id",
    "output_tag",
    "strategy_profile_id",
    "strategy_profile_family",
    "strategy_profile_key",
    "symbol_preset",
    "symbol_universe_count",
    "batch_id",
    "symbol_group",
    "interval_group",
    "intervals",
    "lookback_days",
    "windows",
    "min_closed_trades_required",
    "wallet_balance_usd_assumed",
    "leverage_values",
    "tested_combinations",
    "accepted_candidates",
    "rank",
    "selection_score",
    "risk_efficiency_ratio",
    "symbol",
    "side",
    "interval",
    "search_mode",
    "trigger_reference",
    "execution_model",
    "score_window_size",
    "risk_profile",
    "min_aster_score",
    "min_window_volume_usd",
    "stop_loss_pct",
    "take_profit_pct",
    "trailing_stop_activation_pct",
    "trailing_stop_distance_pct",
    "max_holding_trades",
    "entries",
    "closed_trades",
    "wins",
    "losses",
    "win_rate",
    "profit_factor",
    "gross_profit_usd",
    "gross_loss_usd",
    "pnl_total_usd",
    "pnl_realized_usd",
    "open_unrealized_pnl_usd",
    "pnl_total_including_unrealized_usd",
    "roi_pct_on_paper_balance",
    "max_drawdown_usd",
    "train_closed_trades",
    "train_win_rate",
    "train_profit_factor",
    "train_pnl_total_usd",
    "validation_closed_trades",
    "validation_win_rate",
    "validation_profit_factor",
    "validation_pnl_total_usd",
    "train_validation_split",
    "out_of_sample_status",
    "max_drawdown_pct_on_paper_balance",
    "best_tradable_leverage",
    "best_tradable_leverage_roi_pct_on_margin",
    "best_tradable_leverage_roi_pct_on_paper_balance",
    "best_tradable_leverage_pnl_after_costs_usd",
    "best_tradable_leverage_funding_cost_usd",
    "best_tradable_leverage_round_trip_fee_usd",
    "best_tradable_leverage_exposure_notional_usd",
    "best_tradable_leverage_margin_used_usd",
    "perps_invalid_leverages",
    "effective_fee_bps",
    "round_trip_fee_usd_estimate",
    "funding_source",
    "funding_status",
    "funding_count",
    "funding_avg_bps_per_8h",
    "funding_cost_usd_estimate",
    "mark_index_verdict",
    "mark_index_p95_last_index_bps",
    "mark_index_avg_last_index_bps",
    "mark_index_warnings",
    "mark_index_blockers",
    "ws_quality_verdict",
    "ws_quality_score",
    "ws_quality_risks",
    "ws_quality_warnings",
    "ws_quote_volume_24h",
    "ws_spread_bps",
    "ws_latency_ms",
    "ws_streams_received",
    "ws_streams_expected",
    "exchange_info_status",
    "symbol_status",
    "trigger_protect",
    "market_take_bound",
    "percent_price_up",
    "percent_price_down",
    "min_notional",
    "tick_size",
    "step_size",
    "market_step_size",
    "liquidation_fee_rate",
    "exchange_filter_verdict",
    "exchange_filter_warnings",
    "exchange_filter_blockers",
    "assumed_margin_mode",
    "assumed_asset_mode",
    "assumed_position_mode",
    "assumed_execution_model",
    "assumed_trigger_reference",
    "positive_windows",
    "verdict",
    "perps_assumptions_json",
    "leverage_scenarios_json",
    "perps_scenarios_json",
    "candidate_json",
]


def _parse_csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    rows = [item.strip().upper() for item in str(value).replace(";", ",").split(",") if item.strip()]
    return rows or default


def _dedupe_symbols(symbols: list[str]) -> list[str]:
    return list(dict.fromkeys([symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()]))


def _symbols_from_preset(symbols: str | None, symbol_preset: str) -> list[str]:
    preset_symbols = SYMBOL_PRESETS.get(symbol_preset, SYMBOL_PRESETS["core"])
    if symbols:
        return _parse_csv(symbols, preset_symbols)
    return _dedupe_symbols(preset_symbols)


def _exclude_symbols(symbols: list[str], exclude_symbols: str | None) -> list[str]:
    excluded = set(_parse_csv(exclude_symbols, [])) if exclude_symbols else set()
    if not excluded:
        return symbols
    return [symbol for symbol in symbols if symbol not in excluded]


def _parse_leverage_values(value: str | None) -> list[float]:
    if not value:
        return DEFAULT_LEVERAGE_VALUES
    values: list[float] = []
    for item in str(value).replace(";", ",").split(","):
        try:
            parsed = float(item.strip())
        except (TypeError, ValueError):
            continue
        if 0.0 < parsed <= 20.0:
            values.append(parsed)
    return values or DEFAULT_LEVERAGE_VALUES


def _clean_output_tag(value: str | None, fallback: str) -> str:
    raw = str(value or fallback or "core").strip().lower()
    clean = re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("._-")
    return clean or "core"


def _profile_slug(value: Any, default: str = "na") -> str:
    raw = str(value if value not in (None, "") else default).strip().lower()
    raw = raw.replace("-", "neg")
    clean = re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("._-")
    return clean or default


def _strategy_profile_family(symbol_preset: str, candidate: dict[str, Any]) -> str:
    preset = _profile_slug(symbol_preset)
    symbol = str(candidate.get("symbol") or "").upper()
    if preset in {"macro", "macro_equity"} and symbol in ASTER_COMMODITY_SYMBOLS:
        return "macro_commodity_slow_confirmation"
    if preset in {"equities", "macro_equity"} and symbol in ASTER_EQUITY_SYMBOLS:
        return "equity_synth_slow_confirmation"
    if preset in {"aster_v2", "priority_watchlist"}:
        return "priority_watchlist_exploration"
    return "crypto_liquid_momentum"


def _strategy_profile_identity(
    *,
    output_tag: str,
    symbol_preset: str,
    leverage_values: list[float],
    candidate: dict[str, Any],
    best_leverage: float | None = None,
) -> dict[str, str]:
    symbol = _profile_slug(candidate.get("symbol"))
    side = _profile_slug(candidate.get("side"), "long")
    interval = _profile_slug(candidate.get("interval"))
    search_mode = _profile_slug(candidate.get("search_mode"), "standard")
    trigger = _profile_slug(candidate.get("trigger_reference"), "last_price")
    execution = _profile_slug(candidate.get("execution_model"), "taker_market")
    risk = _profile_slug(candidate.get("risk_profile"), "standard")
    score = _profile_slug(candidate.get("min_aster_score"), "score_na")
    volume = _profile_slug(candidate.get("min_window_volume_usd"), "vol_na")
    stop = _profile_slug(candidate.get("stop_loss_pct"), "sl_na")
    take = _profile_slug(candidate.get("take_profit_pct"), "tp_na")
    trail_activation = _profile_slug(candidate.get("trailing_stop_activation_pct"), "ta_na")
    trail_distance = _profile_slug(candidate.get("trailing_stop_distance_pct"), "td_na")
    holding = _profile_slug(candidate.get("max_holding_trades"), "hold_na")
    score_window = _profile_slug(candidate.get("score_window_size"), "win_na")
    leverage = _profile_slug("_".join(str(value).replace(".", "p") for value in leverage_values), "lev_na")
    selected_leverage = _as_float(best_leverage)
    if selected_leverage > 0:
        leverage = str(selected_leverage).rstrip("0").rstrip(".").replace(".", "p")
    family = _strategy_profile_family(symbol_preset, candidate)
    key_parts = [
        _profile_slug(output_tag),
        _profile_slug(symbol_preset),
        symbol,
        side,
        interval,
        search_mode,
        trigger,
        execution,
        risk,
        f"s{score}",
        f"v{volume}",
        f"sl{stop}",
        f"tp{take}",
        f"ta{trail_activation}",
        f"td{trail_distance}",
        f"h{holding}",
        f"w{score_window}",
        f"lev{leverage}",
    ]
    profile_key = "|".join(key_parts)
    profile_id = "aster_strategy:" + ":".join(key_parts)
    return {
        "strategy_profile_id": profile_id,
        "strategy_profile_family": family,
        "strategy_profile_key": profile_key,
    }


def _strategy_signature_key(candidate: dict[str, Any]) -> tuple[str, ...]:
    strategy_profile_id = str(candidate.get("strategy_profile_id") or "").strip()
    if strategy_profile_id:
        return ("strategy_profile_id", strategy_profile_id)
    strategy_profile_key = str(candidate.get("strategy_profile_key") or "").strip()
    if strategy_profile_key:
        return ("strategy_profile_key", strategy_profile_key)
    return (
        "legacy",
        str(candidate.get("output_tag") or ""),
        str(candidate.get("symbol") or "").upper(),
        str(candidate.get("interval") or ""),
        str(candidate.get("side") or ""),
        str(candidate.get("trigger_reference") or ""),
        str(candidate.get("execution_model") or candidate.get("assumed_execution_model") or ""),
        str(candidate.get("best_tradable_leverage") or ""),
        str(candidate.get("risk_profile") or ""),
        str(candidate.get("min_aster_score") or ""),
        str(candidate.get("min_window_volume_usd") or ""),
        str(candidate.get("stop_loss_pct") or ""),
        str(candidate.get("take_profit_pct") or ""),
        str(candidate.get("trailing_stop_activation_pct") or ""),
        str(candidate.get("trailing_stop_distance_pct") or ""),
        str(candidate.get("max_holding_trades") or ""),
        str(candidate.get("score_window_size") or ""),
        str(candidate.get("search_mode") or ""),
    )


def _dedupe_by_signature(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = _strategy_signature_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _artifact_paths(output_tag: str) -> dict[str, Path]:
    safe_tag = _clean_output_tag(output_tag, "core")
    return {
        "csv_v2": Path(__file__).with_name(f"paper_trading_strategy_discovery_{safe_tag}_v2.csv"),
        "latest_json": Path(__file__).with_name(f"paper_trading_strategy_discovery_{safe_tag}_latest.json"),
        "rotation_json": Path(__file__).with_name(f"paper_trading_strategy_rotation_{safe_tag}_latest.json"),
        "progress_csv_v2": Path(__file__).with_name(f"paper_trading_strategy_discovery_{safe_tag}_progress_v2.csv"),
        "progress_json": Path(__file__).with_name(f"paper_trading_strategy_discovery_{safe_tag}_progress_latest.json"),
    }


def _heartbeat_path(output_tag: str | None) -> Path:
    safe_tag = _clean_output_tag(output_tag, "core")
    return Path(__file__).with_name(f"paper_trading_strategy_discovery_{safe_tag}_heartbeat.json")


def _chunks(items: list[str], size: int) -> list[list[str]]:
    safe_size = max(1, min(int(size or 5), 5))
    return [items[index : index + safe_size] for index in range(0, len(items), safe_size)]


def _ensure_csv() -> None:
    if CSV_FILE.exists():
        return
    with CSV_FILE.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(HEADERS)


def _ensure_csv_path(path: Path, headers: list[str]) -> None:
    if path.exists():
        try:
            with path.open("r", newline="", encoding="utf-8") as handle:
                first_row = next(csv.reader(handle), [])
        except (OSError, StopIteration):
            first_row = []
        if first_row == headers:
            return
        legacy = path.with_name(f"{path.stem}.legacy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{path.suffix}")
        path.replace(legacy)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(headers)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    temp_path.replace(path)


def _write_heartbeat(payload: dict[str, Any]) -> None:
    _write_json_atomic(HEARTBEAT_FILE, payload)
    output_tag = payload.get("output_tag")
    if output_tag:
        _write_json_atomic(_heartbeat_path(str(output_tag)), payload)


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _load_mark_index_snapshot() -> dict[tuple[str, str], dict[str, Any]]:
    try:
        payload = json.loads(MARK_INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else []
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        interval = str(row.get("interval") or "")
        if symbol and interval:
            out[(symbol, interval)] = row
    return out


def _load_ws_quality_snapshot() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(WS_QUALITY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            out[symbol] = row
    return out


def _candidate_score(candidate: dict[str, Any]) -> float:
    adjusted_roi = candidate.get("best_tradable_leverage_roi_pct_on_paper_balance")
    roi = _as_float(adjusted_roi if adjusted_roi not in (None, "") else candidate.get("roi_pct_on_paper_balance"))
    pf = _as_float(candidate.get("profit_factor"))
    wr = _as_float(candidate.get("win_rate"))
    closed = _as_int(candidate.get("closed_trades"))
    positives = _as_int(candidate.get("positive_windows"))
    drawdown = _as_float(candidate.get("max_drawdown_usd"))
    score = (roi * 10.0) + (pf * 3.0) + (wr * 10.0) + min(closed, 30) + (positives * 2.0) - (drawdown * 0.15)
    validation = candidate.get("validation_stats") if isinstance(candidate.get("validation_stats"), dict) else {}
    train = candidate.get("train_stats") if isinstance(candidate.get("train_stats"), dict) else {}
    if validation:
        validation_pnl = _as_float(validation.get("pnl_total_usd"))
        validation_pf = _as_float(validation.get("profit_factor"))
        validation_closed = _as_int(validation.get("closed_trades"))
        train_pnl = _as_float(train.get("pnl_total_usd")) if train else 0.0
        score += min(max(validation_pnl, -20.0), 30.0) * 2.0
        score += min(validation_pf, 10.0) * 3.0
        if validation_closed <= 0 or validation_pnl <= 0:
            score -= 35.0
        if validation_pnl <= 0 or validation_pf < 1.0:
            score -= 75.0
        if train and train_pnl > 0 and validation_pnl > 0:
            score += 12.0
    else:
        score -= 15.0
    if not candidate.get("best_tradable_leverage"):
        score -= 25.0
    return score


def _risk_ratio(candidate: dict[str, Any]) -> float:
    drawdown = max(0.01, _as_float(candidate.get("max_drawdown_usd")))
    return _as_float(candidate.get("pnl_total_usd")) / drawdown


def _leverage_scenarios(candidate: dict[str, Any], leverage_values: list[float], wallet_balance_usd: float) -> dict[str, dict[str, Any]]:
    balance = max(1.0, _as_float(wallet_balance_usd))
    pnl = _as_float(candidate.get("pnl_total_usd"))
    roi = _as_float(candidate.get("roi_pct_on_paper_balance"))
    drawdown = _as_float(candidate.get("max_drawdown_usd"))
    scenarios: dict[str, dict[str, Any]] = {}
    for leverage in leverage_values:
        suffix = str(int(leverage)) if float(leverage).is_integer() else str(leverage).replace(".", "_")
        leveraged_pnl = pnl * leverage
        leveraged_drawdown = drawdown * leverage
        drawdown_pct = leveraged_drawdown / balance * 100.0
        scenarios[f"x{suffix}"] = {
            "leverage": leverage,
            "pnl_total_usd_proxy": round(leveraged_pnl, 6),
            "roi_pct_on_paper_balance_proxy": round(roi * leverage, 6),
            "max_drawdown_usd_proxy": round(leveraged_drawdown, 6),
            "max_drawdown_pct_on_paper_balance_proxy": round(drawdown_pct, 6),
            "risk_bucket": (
                "high_risk" if drawdown_pct >= 25.0 else
                "medium_risk" if drawdown_pct >= 10.0 else
                "controlled_risk"
            ),
        }
    return scenarios


def _side(candidate: dict[str, Any]) -> str:
    side = str(candidate.get("side") or "long").strip().lower()
    return "short" if side == "short" else "long"


def _estimated_adverse_move_pct(candidate: dict[str, Any], wallet_balance_usd: float) -> float:
    size = max(1.0, _as_float(candidate.get("position_size_usd") or candidate.get("avg_position_size_usd") or 100.0))
    drawdown = max(0.0, _as_float(candidate.get("max_drawdown_usd")))
    observed_drawdown_pct = drawdown / size * 100.0
    side = _side(candidate)
    stop = _as_float(candidate.get("stop_loss_pct"))
    if side == "short":
        stop_abs = abs(stop) if stop > 0 else 15.0
    else:
        stop_abs = abs(stop) if stop < 0 else 15.0
    return max(0.0, observed_drawdown_pct, stop_abs)


def _liquidation_move_pct(leverage: float, maintenance_margin_rate: float) -> float:
    safe_leverage = max(1.0, _as_float(leverage))
    maint = max(0.0, min(_as_float(maintenance_margin_rate), 0.2))
    return max(0.0, (1.0 / safe_leverage - maint) * 100.0)


def _perps_scenarios(
    candidate: dict[str, Any],
    leverage_values: list[float],
    wallet_balance_usd: float,
    maintenance_margin_rate: float = DEFAULT_MAINTENANCE_MARGIN_RATE,
    funding_bps_per_8h: float = DEFAULT_FUNDING_BPS_PER_8H,
    funding_snapshot: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    assumptions = perps_assumptions(candidate.get("symbol"), candidate.get("execution_model"))
    base_pnl = _as_float(candidate.get("pnl_total_usd"))
    base_drawdown = _as_float(candidate.get("max_drawdown_usd"))
    roi_on_balance = _as_float(candidate.get("roi_pct_on_paper_balance"))
    base_margin_usd = max(1.0, _as_float(candidate.get("position_size_usd") or candidate.get("avg_position_size_usd") or 100.0))
    adverse_move_pct = _estimated_adverse_move_pct(candidate, wallet_balance_usd)
    scenarios: dict[str, dict[str, Any]] = {}
    for leverage in leverage_values:
        safe_leverage = max(1.0, _as_float(leverage))
        suffix = str(int(safe_leverage)) if float(safe_leverage).is_integer() else str(safe_leverage).replace(".", "_")
        margin_used = base_margin_usd
        exposure_notional = base_margin_usd * safe_leverage
        liquidation_move = _liquidation_move_pct(safe_leverage, maintenance_margin_rate)
        liquidation_before_stop = adverse_move_pct >= liquidation_move if liquidation_move > 0 else True
        leveraged_pnl = base_pnl * safe_leverage
        leveraged_drawdown = base_drawdown * safe_leverage
        funding_meta = funding_cost_usd_estimate(exposure_notional, _side(candidate), funding_snapshot or candidate.get("funding_snapshot"))
        funding_cost = _as_float(funding_meta.get("funding_cost_usd_estimate"))
        official_round_trip_fee = round_trip_fee_usd(exposure_notional, candidate.get("symbol"), assumptions.get("assumed_execution_model"))
        adjusted_pnl = leveraged_pnl - funding_cost - official_round_trip_fee
        invalid_reasons: list[str] = []
        if liquidation_before_stop:
            invalid_reasons.append("estimated_adverse_move_reaches_liquidation_before_or_at_stop")
        if margin_used <= 0:
            invalid_reasons.append("invalid_margin_used")
        if leveraged_drawdown >= max(1.0, _as_float(wallet_balance_usd)) * 0.5:
            invalid_reasons.append("drawdown_exceeds_50pct_paper_balance")
        scenarios[f"x{suffix}"] = {
            "leverage": safe_leverage,
            "mode": "isolated_margin_proxy",
            "assumed_margin_mode": assumptions.get("assumed_margin_mode"),
            "assumed_asset_mode": assumptions.get("assumed_asset_mode"),
            "assumed_position_mode": assumptions.get("assumed_position_mode"),
            "assumed_execution_model": assumptions.get("assumed_execution_model"),
            "assumed_trigger_reference": assumptions.get("assumed_trigger_reference"),
            "quote_asset": assumptions.get("quote_asset"),
            "side": _side(candidate),
            "position_notional_usd_assumed": round(base_margin_usd, 6),
            "base_margin_usd_assumed": round(base_margin_usd, 6),
            "exposure_notional_usd_assumed": round(exposure_notional, 6),
            "margin_used_usd": round(margin_used, 6),
            "maintenance_margin_rate": maintenance_margin_rate,
            "maintenance_margin_source": assumptions.get("maintenance_margin_source"),
            "liquidation_reference_price": assumptions.get("liquidation_reference_price"),
            "liquidation_move_pct_estimate": round(liquidation_move, 6),
            "estimated_adverse_move_pct": round(adverse_move_pct, 6),
            "liquidation_before_stop": liquidation_before_stop,
            "funding_bps_per_8h_assumed": funding_meta.get("avg_funding_bps_per_8h", funding_bps_per_8h),
            "funding_source": funding_meta.get("funding_source") or assumptions.get("funding_source"),
            "funding_status": funding_meta.get("funding_status"),
            "funding_count": funding_meta.get("funding_count"),
            "latest_funding_bps_per_8h": funding_meta.get("latest_funding_bps_per_8h"),
            "funding_cost_usd_estimate": round(funding_cost, 6),
            "funding_cost_usd_proxy": round(funding_cost, 6),
            "effective_fee_bps": assumptions.get("effective_fee_bps"),
            "official_round_trip_fee_usd_estimate": round(official_round_trip_fee, 6),
            "pnl_total_usd_after_funding_and_fee_estimate": round(adjusted_pnl, 6),
            "pnl_total_usd_after_funding_and_fee_proxy": round(adjusted_pnl, 6),
            "pnl_total_usd_after_funding_proxy": round(adjusted_pnl, 6),
            "roi_pct_on_paper_balance_proxy": round((adjusted_pnl / max(1.0, _as_float(wallet_balance_usd)) * 100.0), 6),
            "roi_pct_on_margin_proxy": round((adjusted_pnl / margin_used * 100.0), 6) if margin_used > 0 else None,
            "max_drawdown_usd_proxy": round(leveraged_drawdown, 6),
            "is_tradable_under_proxy": not invalid_reasons,
            "invalid_reasons": invalid_reasons,
        }
    return scenarios


def _best_tradable_perps_scenario(perps_scenarios: dict[str, dict[str, Any]]) -> dict[str, Any]:
    tradable = [row for row in perps_scenarios.values() if row.get("is_tradable_under_proxy")]
    if not tradable:
        return {"best_tradable_leverage": None, "best_tradable_leverage_roi_pct_on_margin": None, "perps_invalid_leverages": ",".join(perps_scenarios.keys())}
    best = max(tradable, key=lambda row: (_as_float(row.get("roi_pct_on_margin_proxy")), _as_float(row.get("leverage"))))
    invalid = [key for key, row in perps_scenarios.items() if not row.get("is_tradable_under_proxy")]
    return {
        "best_tradable_leverage": best.get("leverage"),
        "best_tradable_leverage_roi_pct_on_margin": best.get("roi_pct_on_margin_proxy"),
        "best_tradable_leverage_roi_pct_on_paper_balance": best.get("roi_pct_on_paper_balance_proxy"),
        "best_tradable_leverage_pnl_after_costs_usd": best.get("pnl_total_usd_after_funding_and_fee_estimate"),
        "best_tradable_leverage_funding_cost_usd": best.get("funding_cost_usd_estimate"),
        "best_tradable_leverage_round_trip_fee_usd": best.get("official_round_trip_fee_usd_estimate"),
        "best_tradable_leverage_exposure_notional_usd": best.get("exposure_notional_usd_assumed"),
        "best_tradable_leverage_margin_used_usd": best.get("margin_used_usd"),
        "perps_invalid_leverages": ",".join(invalid),
    }


def _top_unique_symbols(candidates: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    top: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        symbol = str(candidate.get("symbol") or "").upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        top.append(candidate)
        if len(top) >= max(1, int(limit or 5)):
            break
    return top


def _format_top_unique(candidates: list[dict[str, Any]], limit: int = 5) -> str:
    rows = []
    for candidate in _top_unique_symbols(candidates, limit=limit):
        rows.append(
            f"{candidate.get('symbol')} {candidate.get('interval')} "
            f"roi={candidate.get('roi_pct_on_paper_balance')} "
            f"wr={candidate.get('win_rate')} pf={candidate.get('profit_factor')}"
        )
    return " | ".join(rows)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _unique_by_signature(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        key = _strategy_signature_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
        if len(unique) >= limit:
            break
    return unique


def _champion_categories(candidates: list[dict[str, Any]], limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    clean = [row for row in candidates if _as_int(row.get("closed_trades")) > 0]
    high_winrate = sorted(
        clean,
        key=lambda row: (_as_float(row.get("win_rate")), _as_int(row.get("closed_trades")), _as_float(row.get("profit_factor")), _as_float(row.get("roi_pct_on_paper_balance"))),
        reverse=True,
    )
    high_roi = sorted(
        clean,
        key=lambda row: (_as_float(row.get("roi_pct_on_paper_balance")), _as_float(row.get("profit_factor")), _as_float(row.get("win_rate"))),
        reverse=True,
    )
    balanced = sorted(clean, key=lambda row: (_candidate_score(row), _as_float(row.get("roi_pct_on_paper_balance"))), reverse=True)
    low_drawdown = sorted(
        clean,
        key=lambda row: (_risk_ratio(row), -_as_float(row.get("max_drawdown_usd")), _as_float(row.get("profit_factor"))),
        reverse=True,
    )
    deep_sample = sorted(
        clean,
        key=lambda row: (_as_int(row.get("closed_trades")), _as_float(row.get("profit_factor")), _as_float(row.get("roi_pct_on_paper_balance"))),
        reverse=True,
    )
    return {
        "high_winrate": _unique_by_signature(high_winrate, limit),
        "high_roi": _unique_by_signature(high_roi, limit),
        "balanced": _unique_by_signature(balanced, limit),
        "low_drawdown_efficiency": _unique_by_signature(low_drawdown, limit),
        "deep_sample": _unique_by_signature(deep_sample, limit),
    }


def _row(timestamp: str, run_id: str, batch_id: str, symbol_group: str, intervals: str, result: dict[str, Any], rank: int, candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "run_id": run_id,
        "batch_id": batch_id,
        "symbol_group": symbol_group,
        "intervals": intervals,
        "tested_combinations": result.get("tested_combinations"),
        "accepted_candidates": result.get("accepted_candidates"),
        "rank": rank,
        "symbol": candidate.get("symbol"),
        "interval": candidate.get("interval"),
        "risk_profile": candidate.get("risk_profile"),
        "min_aster_score": candidate.get("min_aster_score"),
        "min_window_volume_usd": candidate.get("min_window_volume_usd"),
        "closed_trades": candidate.get("closed_trades"),
        "win_rate": candidate.get("win_rate"),
        "profit_factor": candidate.get("profit_factor"),
        "pnl_total_usd": candidate.get("pnl_total_usd"),
        "roi_pct_on_paper_balance": candidate.get("roi_pct_on_paper_balance"),
        "max_drawdown_usd": candidate.get("max_drawdown_usd"),
        "positive_windows": candidate.get("positive_windows"),
        "verdict": candidate.get("verdict"),
    }


def _row_v2(
    *,
    timestamp: str,
    run_id: str,
    output_tag: str,
    symbol_preset: str,
    symbol_universe_count: int,
    batch_id: str,
    symbol_group: str,
    interval_group: str,
    intervals: str,
    lookback_days: int,
    windows: int,
    min_closed_trades: int,
    wallet_balance_usd: float,
    leverage_values: list[float],
    result: dict[str, Any],
    rank: int,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    leverage_scenarios = candidate.get("leverage_scenarios") or _leverage_scenarios(candidate, leverage_values, wallet_balance_usd)
    perps_scenarios = candidate.get("perps_scenarios") or _perps_scenarios(candidate, leverage_values, wallet_balance_usd)
    best_perps = _best_tradable_perps_scenario(perps_scenarios)
    profile = _strategy_profile_identity(
        output_tag=output_tag,
        symbol_preset=symbol_preset,
        leverage_values=leverage_values,
        candidate=candidate,
        best_leverage=best_perps.get("best_tradable_leverage"),
    )
    assumptions = perps_assumptions(candidate.get("symbol"), candidate.get("execution_model"))
    funding_snapshot = candidate.get("funding_snapshot") if isinstance(candidate.get("funding_snapshot"), dict) else {}
    mark_index_snapshot = candidate.get("mark_index_snapshot") if isinstance(candidate.get("mark_index_snapshot"), dict) else {}
    ws_quality_snapshot = candidate.get("ws_quality_snapshot") if isinstance(candidate.get("ws_quality_snapshot"), dict) else {}
    exchange_info_snapshot = candidate.get("exchange_info_snapshot") if isinstance(candidate.get("exchange_info_snapshot"), dict) else {}
    train_stats = candidate.get("train_stats") if isinstance(candidate.get("train_stats"), dict) else {}
    validation_stats = candidate.get("validation_stats") if isinstance(candidate.get("validation_stats"), dict) else {}
    ws_summary = ws_quality_snapshot.get("ws_summary") if isinstance(ws_quality_snapshot.get("ws_summary"), dict) else {}
    ws_rest = ws_quality_snapshot.get("rest_snapshot") if isinstance(ws_quality_snapshot.get("rest_snapshot"), dict) else {}
    ws_depth = ((ws_quality_snapshot.get("ws_snapshot") or {}).get("depth") or {}) if isinstance(ws_quality_snapshot.get("ws_snapshot"), dict) else {}
    position_notional = max(1.0, _as_float(candidate.get("position_size_usd") or candidate.get("avg_position_size_usd") or 100.0))
    best_exposure_notional = max(
        position_notional,
        _as_float(best_perps.get("best_tradable_leverage_exposure_notional_usd")),
    )
    funding_meta = funding_cost_usd_estimate(best_exposure_notional, _side(candidate), funding_snapshot)
    exchange_verdict = exchange_info_reality_verdict(exchange_info_snapshot, position_notional_usd=best_exposure_notional)
    max_drawdown = _as_float(candidate.get("max_drawdown_usd"))
    balance = max(1.0, _as_float(wallet_balance_usd))
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": timestamp,
        "run_id": run_id,
        "output_tag": output_tag,
        "strategy_profile_id": profile["strategy_profile_id"],
        "strategy_profile_family": profile["strategy_profile_family"],
        "strategy_profile_key": profile["strategy_profile_key"],
        "symbol_preset": symbol_preset,
        "symbol_universe_count": symbol_universe_count,
        "batch_id": batch_id,
        "symbol_group": symbol_group,
        "interval_group": interval_group,
        "intervals": intervals,
        "lookback_days": lookback_days,
        "windows": windows,
        "min_closed_trades_required": min_closed_trades,
        "wallet_balance_usd_assumed": wallet_balance_usd,
        "leverage_values": ",".join(str(value) for value in leverage_values),
        "tested_combinations": result.get("tested_combinations"),
        "accepted_candidates": result.get("accepted_candidates"),
        "rank": rank,
        "selection_score": candidate.get("selection_score", round(_candidate_score(candidate), 6)),
        "risk_efficiency_ratio": round(_risk_ratio(candidate), 6),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "interval": candidate.get("interval"),
        "search_mode": candidate.get("search_mode"),
        "trigger_reference": candidate.get("trigger_reference") or "last_price",
        "execution_model": candidate.get("execution_model") or assumptions.get("assumed_execution_model") or "taker_market",
        "score_window_size": candidate.get("score_window_size"),
        "risk_profile": candidate.get("risk_profile"),
        "min_aster_score": candidate.get("min_aster_score"),
        "min_window_volume_usd": candidate.get("min_window_volume_usd"),
        "stop_loss_pct": candidate.get("stop_loss_pct"),
        "take_profit_pct": candidate.get("take_profit_pct"),
        "trailing_stop_activation_pct": candidate.get("trailing_stop_activation_pct"),
        "trailing_stop_distance_pct": candidate.get("trailing_stop_distance_pct"),
        "max_holding_trades": candidate.get("max_holding_trades"),
        "entries": candidate.get("entries"),
        "closed_trades": candidate.get("closed_trades"),
        "wins": candidate.get("wins"),
        "losses": candidate.get("losses"),
        "win_rate": candidate.get("win_rate"),
        "profit_factor": candidate.get("profit_factor"),
        "gross_profit_usd": candidate.get("gross_profit_usd"),
        "gross_loss_usd": candidate.get("gross_loss_usd"),
        "pnl_total_usd": candidate.get("pnl_total_usd"),
        "pnl_realized_usd": candidate.get("pnl_realized_usd", candidate.get("pnl_total_usd")),
        "open_unrealized_pnl_usd": candidate.get("open_unrealized_pnl_usd"),
        "pnl_total_including_unrealized_usd": candidate.get("pnl_total_including_unrealized_usd"),
        "roi_pct_on_paper_balance": candidate.get("roi_pct_on_paper_balance"),
        "max_drawdown_usd": candidate.get("max_drawdown_usd"),
        "train_closed_trades": train_stats.get("closed_trades"),
        "train_win_rate": train_stats.get("win_rate"),
        "train_profit_factor": train_stats.get("profit_factor"),
        "train_pnl_total_usd": train_stats.get("pnl_total_usd"),
        "validation_closed_trades": validation_stats.get("closed_trades"),
        "validation_win_rate": validation_stats.get("win_rate"),
        "validation_profit_factor": validation_stats.get("profit_factor"),
        "validation_pnl_total_usd": validation_stats.get("pnl_total_usd"),
        "train_validation_split": candidate.get("train_validation_split"),
        "out_of_sample_status": (
            "passed_latest_window_validation"
            if validation_stats and _as_float(validation_stats.get("pnl_total_usd")) > 0 and _as_float(validation_stats.get("profit_factor")) >= 1.0
            else "not_available"
            if not validation_stats
            else "failed_latest_window_validation"
        ),
        "max_drawdown_pct_on_paper_balance": round(max_drawdown / balance * 100.0, 6),
        "best_tradable_leverage": best_perps.get("best_tradable_leverage"),
        "best_tradable_leverage_roi_pct_on_margin": best_perps.get("best_tradable_leverage_roi_pct_on_margin"),
        "best_tradable_leverage_roi_pct_on_paper_balance": best_perps.get("best_tradable_leverage_roi_pct_on_paper_balance"),
        "best_tradable_leverage_pnl_after_costs_usd": best_perps.get("best_tradable_leverage_pnl_after_costs_usd"),
        "best_tradable_leverage_funding_cost_usd": best_perps.get("best_tradable_leverage_funding_cost_usd"),
        "best_tradable_leverage_round_trip_fee_usd": best_perps.get("best_tradable_leverage_round_trip_fee_usd"),
        "best_tradable_leverage_exposure_notional_usd": best_perps.get("best_tradable_leverage_exposure_notional_usd"),
        "best_tradable_leverage_margin_used_usd": best_perps.get("best_tradable_leverage_margin_used_usd"),
        "perps_invalid_leverages": best_perps.get("perps_invalid_leverages"),
        "effective_fee_bps": assumptions.get("effective_fee_bps"),
        "round_trip_fee_usd_estimate": round(round_trip_fee_usd(best_exposure_notional, candidate.get("symbol"), assumptions.get("assumed_execution_model")), 6),
        "funding_source": funding_meta.get("funding_source"),
        "funding_status": funding_meta.get("funding_status"),
        "funding_count": funding_meta.get("funding_count"),
        "funding_avg_bps_per_8h": funding_meta.get("avg_funding_bps_per_8h"),
        "funding_cost_usd_estimate": funding_meta.get("funding_cost_usd_estimate"),
        "mark_index_verdict": mark_index_snapshot.get("verdict") or "not_checked",
        "mark_index_p95_last_index_bps": mark_index_snapshot.get("p95_last_index_close_bps"),
        "mark_index_avg_last_index_bps": mark_index_snapshot.get("avg_last_index_close_bps"),
        "mark_index_warnings": ",".join(mark_index_snapshot.get("warnings") or []),
        "mark_index_blockers": ",".join(mark_index_snapshot.get("blockers") or []),
        "ws_quality_verdict": ws_quality_snapshot.get("ws_quality_verdict") or "not_checked",
        "ws_quality_score": ws_quality_snapshot.get("ws_quality_score"),
        "ws_quality_risks": ",".join(ws_quality_snapshot.get("ws_quality_risks") or []),
        "ws_quality_warnings": ",".join(ws_quality_snapshot.get("ws_quality_warnings") or []),
        "ws_quote_volume_24h": ws_rest.get("quote_volume_24h"),
        "ws_spread_bps": ws_depth.get("spread_bps"),
        "ws_latency_ms": ws_summary.get("latency_ms"),
        "ws_streams_received": ws_summary.get("streams_received"),
        "ws_streams_expected": ws_summary.get("streams_expected"),
        "exchange_info_status": exchange_info_snapshot.get("exchange_info_status") or "not_checked",
        "symbol_status": exchange_info_snapshot.get("symbol_status"),
        "trigger_protect": exchange_info_snapshot.get("trigger_protect"),
        "market_take_bound": exchange_info_snapshot.get("market_take_bound"),
        "percent_price_up": exchange_info_snapshot.get("percent_price_up"),
        "percent_price_down": exchange_info_snapshot.get("percent_price_down"),
        "min_notional": exchange_info_snapshot.get("min_notional"),
        "tick_size": exchange_info_snapshot.get("tick_size"),
        "step_size": exchange_info_snapshot.get("step_size"),
        "market_step_size": exchange_info_snapshot.get("market_step_size"),
        "liquidation_fee_rate": exchange_info_snapshot.get("liquidation_fee_rate"),
        "exchange_filter_verdict": exchange_verdict.get("exchange_filter_verdict"),
        "exchange_filter_warnings": ",".join(exchange_verdict.get("exchange_filter_warnings") or []),
        "exchange_filter_blockers": ",".join(exchange_verdict.get("exchange_filter_blockers") or []),
        "assumed_margin_mode": assumptions.get("assumed_margin_mode"),
        "assumed_asset_mode": assumptions.get("assumed_asset_mode"),
        "assumed_position_mode": assumptions.get("assumed_position_mode"),
        "assumed_execution_model": assumptions.get("assumed_execution_model"),
        "assumed_trigger_reference": candidate.get("trigger_reference") or assumptions.get("assumed_trigger_reference"),
        "positive_windows": candidate.get("positive_windows"),
        "verdict": candidate.get("verdict"),
        "perps_assumptions_json": _json_dumps(assumptions),
        "leverage_scenarios_json": _json_dumps(leverage_scenarios),
        "perps_scenarios_json": _json_dumps(perps_scenarios),
        "candidate_json": _json_dumps(candidate),
    }


def _write_csv(rows: list[dict[str, Any]]) -> None:
    _ensure_csv()
    with CSV_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([row.get(key) for key in HEADERS])


def _write_csv_v2(path: Path, rows: list[dict[str, Any]]) -> None:
    _ensure_csv_path(path, V2_HEADERS)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([row.get(key) for key in V2_HEADERS])


def _write_csv_v2_replace(path: Path, rows: list[dict[str, Any]]) -> None:
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with temp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(V2_HEADERS)
        for row in rows:
            writer.writerow([row.get(key) for key in V2_HEADERS])
    temp_path.replace(path)


def _write_progress_artifacts(
    *,
    artifact_paths: dict[str, Path],
    run_id: str,
    output_tag: str,
    symbol_preset: str,
    search_mode: str,
    trigger_reference: str,
    execution_model: str,
    current_batch: int,
    total_batches: int,
    all_candidates: list[dict[str, Any]],
    all_rows_v2: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    all_rows_v2_unique = _dedupe_by_signature(all_rows_v2)
    ranked = _unique_by_signature(
        sorted(
            all_candidates,
            key=lambda row: (_candidate_score(row), _as_float(row.get("roi_pct_on_paper_balance"))),
            reverse=True,
        ),
        min(20, len(all_candidates)),
    )
    _write_csv_v2_replace(artifact_paths["progress_csv_v2"], all_rows_v2_unique)
    _write_json_atomic(
        artifact_paths["progress_json"],
        {
            "ok": True,
            "mode": "discovery_progress_partial",
            "run_id": run_id,
            "output_tag": output_tag,
            "symbol_preset": symbol_preset,
            "search_mode": search_mode,
            "trigger_reference": trigger_reference,
            "execution_model": execution_model,
            "last_progress_at": datetime.now(timezone.utc).isoformat(),
            "current_batch": current_batch,
            "total_batches": total_batches,
            "candidates_so_far": len(all_candidates),
            "failures_so_far": len(failures),
            "top_global_so_far": ranked[:20],
            "top_unique_symbols_so_far": _top_unique_symbols(ranked, limit=10),
            "progress_csv_v2_path": str(artifact_paths["progress_csv_v2"]),
            "final_csv_v2_path": str(artifact_paths["csv_v2"]),
            "final_tagged_json_path": str(artifact_paths["latest_json"]),
            "would_write_db": False,
            "would_trade": False,
        },
    )


def run_discovery(
    symbols: str | None = None,
    exclude_symbols: str | None = None,
    groups: str = "both",
    lookback_days: int = 60,
    windows: int = 3,
    min_closed_trades: int = 8,
    top_n_per_batch: int = 10,
    top_n_global: int = 30,
    batch_size: int = 5,
    leverage_values: str | None = None,
    wallet_balance_usd: float = 1_000.0,
    symbol_preset: str = "core",
    output_tag: str | None = None,
    search_mode: str = "standard",
    trigger_reference: str = "last_price",
    execution_model: str = "taker_market",
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    run_id = f"strategy-discovery-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    clean_symbols = _exclude_symbols(_symbols_from_preset(symbols, symbol_preset), exclude_symbols)
    clean_leverage_values = _parse_leverage_values(leverage_values)
    clean_output_tag = _clean_output_tag(output_tag, symbol_preset)
    clean_search_mode = str(search_mode or "standard").strip().lower()
    if clean_search_mode not in {"standard", "exploration", "deep"}:
        clean_search_mode = "standard"
    clean_trigger_reference = str(trigger_reference or "last_price").strip().lower()
    if clean_trigger_reference not in {"last_price", "mark_price"}:
        clean_trigger_reference = "last_price"
    clean_execution_model = str(execution_model or "taker_market").strip().lower()
    if clean_execution_model not in {"taker_market", "maker_post_only", "bbo_limit"}:
        clean_execution_model = "taker_market"
    try:
        clean_lookback_days = max(1, int(lookback_days))
    except (TypeError, ValueError):
        clean_lookback_days = 60
    try:
        clean_windows = max(1, int(windows))
    except (TypeError, ValueError):
        clean_windows = 3
    artifact_paths = _artifact_paths(clean_output_tag)
    interval_batches: list[tuple[str, str]] = []
    if groups in {"low", "both"}:
        interval_batches.append(("low_tf", LOW_INTERVALS))
    if groups in {"high", "both"}:
        interval_batches.append(("high_tf", HIGH_INTERVALS))

    all_rows: list[dict[str, Any]] = []
    all_rows_v2: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    batch_reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    symbol_groups = _chunks(clean_symbols, batch_size)
    total_batches = max(1, len(symbol_groups) * max(1, len(interval_batches)))
    funding_snapshot = get_public_funding_history_snapshot(clean_symbols, limit=100, timeout_seconds=5, cache_ttl_seconds=900)
    funding_ready = sum(1 for row in funding_snapshot.values() if row.get("status") == "ok")
    exchange_info_snapshot = get_public_exchange_info_snapshot(clean_symbols, timeout_seconds=8, cache_ttl_seconds=900)
    exchange_info_ready = sum(1 for row in exchange_info_snapshot.values() if row.get("exchange_info_status") == "ok")
    mark_index_lookup = _load_mark_index_snapshot()
    ws_quality_lookup = _load_ws_quality_snapshot()
    _write_heartbeat(
        {
            "ok": True,
            "mode": "discovery_progress",
            "phase": "started",
            "run_id": run_id,
            "output_tag": clean_output_tag,
            "symbol_preset": symbol_preset,
            "search_mode": clean_search_mode,
            "trigger_reference": clean_trigger_reference,
            "execution_model": clean_execution_model,
            "started_at": timestamp,
            "last_progress_at": datetime.now(timezone.utc).isoformat(),
            "current_batch": 0,
            "total_batches": total_batches,
            "symbols_total": len(clean_symbols),
            "funding_source": "aster_public_funding_history_fapi_v3",
            "funding_symbols_ready": funding_ready,
            "funding_symbols_total": len(funding_snapshot),
            "exchange_info_source": "aster_public_exchange_info_fapi_v3",
            "exchange_info_symbols_ready": exchange_info_ready,
            "exchange_info_symbols_total": len(exchange_info_snapshot),
            "mark_index_snapshot_rows": len(mark_index_lookup),
            "ws_quality_snapshot_rows": len(ws_quality_lookup),
            "csv_v2_path": str(artifact_paths["csv_v2"]),
            "tagged_json_path": str(artifact_paths["latest_json"]),
        }
    )
    for group_index, symbol_group in enumerate(symbol_groups, start=1):
        group_text = ",".join(symbol_group)
        for interval_index, (interval_id, intervals) in enumerate(interval_batches, start=1):
            batch_id = f"{interval_id}_g{group_index:02d}"
            current_batch = ((group_index - 1) * len(interval_batches)) + interval_index
            progress_at = datetime.now(timezone.utc).isoformat()
            _write_heartbeat(
                {
                    "ok": True,
                    "mode": "discovery_progress",
                    "phase": "batch_started",
                    "run_id": run_id,
                    "output_tag": clean_output_tag,
                    "symbol_preset": symbol_preset,
                    "search_mode": clean_search_mode,
                    "trigger_reference": clean_trigger_reference,
                    "execution_model": clean_execution_model,
                    "last_progress_at": progress_at,
                    "current_batch": current_batch,
                    "total_batches": total_batches,
                    "batch_id": batch_id,
                    "symbol_group": group_text,
                    "intervals": intervals,
                    "candidates_so_far": len(all_candidates),
                    "failures_so_far": len(failures),
                    "csv_v2_path": str(artifact_paths["csv_v2"]),
                    "tagged_json_path": str(artifact_paths["latest_json"]),
                }
            )
            print(
                f"[{progress_at}] progress tag={clean_output_tag} batch={current_batch}/{total_batches} "
                f"{batch_id} symbols={group_text} intervals={intervals} phase=start",
                flush=True,
            )
            try:
                result = get_aster_paper_trading_focused_optimization_preview(
                    symbols=group_text,
                    intervals=intervals,
                    lookback_days=clean_lookback_days,
                    windows=clean_windows,
                    min_closed_trades=min_closed_trades,
                    dry_run=True,
                    rate_limit_delay_ms=100,
                    search_mode=clean_search_mode,
                    trigger_reference=clean_trigger_reference,
                    execution_model=clean_execution_model,
                )
            except Exception as exc:
                failure = {
                    "batch_id": batch_id,
                    "symbol_group": group_text,
                    "intervals": intervals,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                failures.append(failure)
                batch_reports.append(
                    {
                        "batch_id": batch_id,
                        "symbol_group": group_text,
                        "intervals": intervals,
                        "tested_combinations": 0,
                        "accepted_candidates": 0,
                        "recommendation": "batch_failed_continue_next_batch",
                        "error": failure,
                    }
                )
                _write_heartbeat(
                    {
                        "ok": False,
                        "mode": "discovery_progress",
                        "phase": "batch_failed",
                        "run_id": run_id,
                        "output_tag": clean_output_tag,
                        "symbol_preset": symbol_preset,
                        "search_mode": clean_search_mode,
                        "trigger_reference": clean_trigger_reference,
                        "execution_model": clean_execution_model,
                        "last_progress_at": datetime.now(timezone.utc).isoformat(),
                        "current_batch": current_batch,
                        "total_batches": total_batches,
                        "batch_id": batch_id,
                        "symbol_group": group_text,
                        "intervals": intervals,
                        "error": failure,
                        "candidates_so_far": len(all_candidates),
                        "failures_so_far": len(failures),
                        "csv_v2_path": str(artifact_paths["csv_v2"]),
                        "tagged_json_path": str(artifact_paths["latest_json"]),
                    }
                )
                continue
            candidates = (result.get("ranked_candidates") or [])[: max(1, min(int(top_n_per_batch or 10), 50))]
            for index, candidate in enumerate(candidates, start=1):
                candidate_trigger_reference = candidate.get("trigger_reference") or clean_trigger_reference
                candidate_execution_model = candidate.get("execution_model") or clean_execution_model
                candidate = {
                    **candidate,
                    "trigger_reference": candidate_trigger_reference,
                    "execution_model": candidate_execution_model,
                }
                leverage_scenarios = _leverage_scenarios(candidate, clean_leverage_values, wallet_balance_usd)
                symbol_funding = funding_snapshot.get(str(candidate.get("symbol") or "").upper()) or {}
                symbol_exchange_info = exchange_info_snapshot.get(str(candidate.get("symbol") or "").upper()) or {}
                symbol_mark_index = mark_index_lookup.get((str(candidate.get("symbol") or "").upper(), str(candidate.get("interval") or ""))) or {}
                symbol_ws_quality = ws_quality_lookup.get(str(candidate.get("symbol") or "").upper()) or {}
                perps_scenarios = _perps_scenarios(candidate, clean_leverage_values, wallet_balance_usd, funding_snapshot=symbol_funding)
                best_perps = _best_tradable_perps_scenario(perps_scenarios)
                enriched = {
                    **candidate,
                    "batch_id": batch_id,
                    "symbol_group": group_text,
                    "intervals": intervals,
                    "leverage_scenarios": leverage_scenarios,
                    "perps_scenarios": perps_scenarios,
                    "trigger_reference": candidate_trigger_reference,
                    "execution_model": candidate_execution_model,
                    "funding_snapshot": symbol_funding,
                    "exchange_info_snapshot": symbol_exchange_info,
                    "mark_index_snapshot": symbol_mark_index,
                    "ws_quality_snapshot": symbol_ws_quality,
                    "best_tradable_leverage": best_perps.get("best_tradable_leverage"),
                    "best_tradable_leverage_roi_pct_on_margin": best_perps.get("best_tradable_leverage_roi_pct_on_margin"),
                    "best_tradable_leverage_roi_pct_on_paper_balance": best_perps.get("best_tradable_leverage_roi_pct_on_paper_balance"),
                    "best_tradable_leverage_pnl_after_costs_usd": best_perps.get("best_tradable_leverage_pnl_after_costs_usd"),
                    "best_tradable_leverage_funding_cost_usd": best_perps.get("best_tradable_leverage_funding_cost_usd"),
                    "best_tradable_leverage_round_trip_fee_usd": best_perps.get("best_tradable_leverage_round_trip_fee_usd"),
                    "best_tradable_leverage_exposure_notional_usd": best_perps.get("best_tradable_leverage_exposure_notional_usd"),
                    "best_tradable_leverage_margin_used_usd": best_perps.get("best_tradable_leverage_margin_used_usd"),
                    "perps_invalid_leverages": best_perps.get("perps_invalid_leverages"),
                }
                enriched["selection_score"] = round(_candidate_score(enriched), 6)
                enriched.update(
                    _strategy_profile_identity(
                        output_tag=clean_output_tag,
                        symbol_preset=symbol_preset,
                        leverage_values=clean_leverage_values,
                        candidate=enriched,
                        best_leverage=best_perps.get("best_tradable_leverage"),
                    )
                )
                all_candidates.append(enriched)
                all_rows.append(_row(timestamp, run_id, batch_id, group_text, intervals, result, index, enriched))
                all_rows_v2.append(
                    _row_v2(
                        timestamp=timestamp,
                        run_id=run_id,
                        output_tag=clean_output_tag,
                        symbol_preset=symbol_preset,
                        symbol_universe_count=len(clean_symbols),
                        batch_id=batch_id,
                        symbol_group=group_text,
                        interval_group=interval_id,
                        intervals=intervals,
                        lookback_days=clean_lookback_days,
                        windows=clean_windows,
                        min_closed_trades=min_closed_trades,
                        wallet_balance_usd=wallet_balance_usd,
                        leverage_values=clean_leverage_values,
                        result=result,
                        rank=index,
                        candidate=enriched,
                    )
                )
            batch_reports.append(
                {
                    "batch_id": batch_id,
                    "symbol_group": group_text,
                    "intervals": intervals,
                    "tested_combinations": result.get("tested_combinations"),
                    "accepted_candidates": result.get("accepted_candidates"),
                    "recommendation": result.get("recommendation"),
                }
            )
            failures.extend(result.get("failed_fetches") or [])
            completed_at = datetime.now(timezone.utc).isoformat()
            best_batch = candidates[0] if candidates else {}
            _write_progress_artifacts(
                artifact_paths=artifact_paths,
                run_id=run_id,
                output_tag=clean_output_tag,
                symbol_preset=symbol_preset,
                search_mode=clean_search_mode,
                trigger_reference=clean_trigger_reference,
                execution_model=clean_execution_model,
                current_batch=current_batch,
                total_batches=total_batches,
                all_candidates=all_candidates,
                all_rows_v2=all_rows_v2,
                failures=failures,
            )
            _write_heartbeat(
                {
                    "ok": True,
                    "mode": "discovery_progress",
                    "phase": "batch_completed",
                    "run_id": run_id,
                    "output_tag": clean_output_tag,
                    "symbol_preset": symbol_preset,
                    "search_mode": clean_search_mode,
                    "trigger_reference": clean_trigger_reference,
                    "execution_model": clean_execution_model,
                    "last_progress_at": completed_at,
                    "current_batch": current_batch,
                    "total_batches": total_batches,
                    "batch_id": batch_id,
                    "symbol_group": group_text,
                    "intervals": intervals,
                    "tested_combinations": result.get("tested_combinations"),
                    "accepted_candidates": result.get("accepted_candidates"),
                    "batch_best": {
                        "symbol": best_batch.get("symbol"),
                        "interval": best_batch.get("interval"),
                        "roi_pct_on_paper_balance": best_batch.get("roi_pct_on_paper_balance"),
                        "win_rate": best_batch.get("win_rate"),
                        "profit_factor": best_batch.get("profit_factor"),
                    },
                    "candidates_so_far": len(all_candidates),
                    "failures_so_far": len(failures),
                    "csv_v2_path": str(artifact_paths["csv_v2"]),
                    "tagged_json_path": str(artifact_paths["latest_json"]),
                    "progress_csv_v2_path": str(artifact_paths["progress_csv_v2"]),
                    "progress_json_path": str(artifact_paths["progress_json"]),
                }
            )
            print(
                f"[{completed_at}] progress tag={clean_output_tag} batch={current_batch}/{total_batches} "
                f"{batch_id} accepted={result.get('accepted_candidates')} best={best_batch.get('symbol')} "
                f"{best_batch.get('interval')} roi={best_batch.get('roi_pct_on_paper_balance')} phase=done",
                flush=True,
            )

    all_candidates.sort(key=lambda row: (_candidate_score(row), _as_float(row.get("roi_pct_on_paper_balance"))), reverse=True)
    top_global = _unique_by_signature(all_candidates, max(1, min(int(top_n_global or 30), 100)))
    out_of_sample_passed = [
        row
        for row in all_candidates
        if isinstance(row.get("validation_stats"), dict)
        and _as_float((row.get("validation_stats") or {}).get("pnl_total_usd")) > 0
        and _as_float((row.get("validation_stats") or {}).get("profit_factor")) >= 1.0
    ]
    out_of_sample_failed = [
        row
        for row in all_candidates
        if isinstance(row.get("validation_stats"), dict)
        and (
            _as_float((row.get("validation_stats") or {}).get("pnl_total_usd")) <= 0
            or _as_float((row.get("validation_stats") or {}).get("profit_factor")) < 1.0
        )
    ]
    best_by_symbol: dict[str, dict[str, Any]] = {}
    best_by_interval: dict[str, dict[str, Any]] = {}
    for candidate in all_candidates:
        symbol = str(candidate.get("symbol") or "")
        interval = str(candidate.get("interval") or "")
        best_by_symbol.setdefault(symbol, candidate)
        best_by_interval.setdefault(interval, candidate)
    categories = _champion_categories(
        _unique_by_signature(all_candidates, len(all_candidates)),
        limit=max(3, min(int(top_n_global or 30), 20)),
    )

    _write_csv(all_rows)
    _write_csv_v2(artifact_paths["csv_v2"], _dedupe_by_signature(all_rows_v2))
    payload = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "timestamp": timestamp,
        "run_id": run_id,
        "methodology": "broad_multi_symbol_multi_timeframe_kline_proxy_discovery_read_only",
        "symbols": clean_symbols,
        "exclude_symbols": _parse_csv(exclude_symbols, []) if exclude_symbols else [],
        "symbol_preset": symbol_preset,
        "output_tag": clean_output_tag,
        "search_mode": clean_search_mode,
        "trigger_reference": clean_trigger_reference,
        "execution_model": clean_execution_model,
        "groups": groups,
        "lookback_days": clean_lookback_days,
        "windows": clean_windows,
        "min_closed_trades": min_closed_trades,
        "wallet_balance_usd_assumed": wallet_balance_usd,
        "leverage_values": clean_leverage_values,
        "leverage_methodology": "perps_proxy_applies_official_fee_estimate_public_funding_history_and_liquidation_distance_screen",
        "perps_methodology": {
            "mode": "isolated_margin_proxy",
            "assumed_margin_mode": "isolated",
            "assumed_asset_mode": "single_asset",
            "assumed_position_mode": "one_way",
            "assumed_execution_model": clean_execution_model,
            "assumed_trigger_reference": "mark_price_for_liquidation_last_price_for_entry_exit",
            "maintenance_margin_rate": DEFAULT_MAINTENANCE_MARGIN_RATE,
            "maintenance_margin_source": "proxy_until_signed_leverage_bracket_policy",
            "funding_source": "aster_public_funding_history_fapi_v3_with_fixed_fallback",
            "funding_symbols_ready": funding_ready,
            "funding_symbols_total": len(funding_snapshot),
            "exchange_info_source": "aster_public_exchange_info_fapi_v3",
            "exchange_info_symbols_ready": exchange_info_ready,
            "exchange_info_symbols_total": len(exchange_info_snapshot),
            "ws_quality_snapshot_rows": len(ws_quality_lookup),
            "exchange_filter_model": "public_exchangeInfo_fields_recorded_per_candidate_not_yet_hard_rejecting_candidates",
            "fee_model": "Aster official docs: USDT taker 4bps, USD1 taker 0.5bps, maker 0bps; applied as round-trip estimate in perps scenarios",
            "liquidation_rule": "scenario_invalid_when_estimated_adverse_move_pct_reaches_liquidation_move_before_or_at_stop",
            "caveat": "proxy_not_exchange_exact_margin_engine",
        },
        "batches": batch_reports,
        "total_candidates": len(all_candidates),
        "top_global": top_global,
        "out_of_sample_summary": {
            "methodology": "latest_walkforward_windows_reserved_as_validation_by_focused_optimizer",
            "passed_latest_window_validation": len(out_of_sample_passed),
            "failed_latest_window_validation": len(out_of_sample_failed),
            "without_validation_stats": len(all_candidates) - len(out_of_sample_passed) - len(out_of_sample_failed),
        },
        "top_out_of_sample_passed": _unique_by_signature(out_of_sample_passed, max(1, min(int(top_n_global or 30), 50))),
        "top_unique_symbols": _top_unique_symbols(all_candidates, limit=10),
        "champion_categories": categories,
        "best_by_symbol": best_by_symbol,
        "best_by_interval": best_by_interval,
        "failed_fetches": failures,
        "csv_path": str(CSV_FILE),
        "csv_v2_path": str(artifact_paths["csv_v2"]),
        "json_path": str(JSON_FILE),
        "tagged_json_path": str(artifact_paths["latest_json"]),
        "artifact_policy": "legacy_csv_and_latest_kept_for_compatibility_tagged_v2_outputs_are_primary_for_research",
        "would_write_db": False,
        "would_trade": False,
    }
    _write_json_atomic(artifact_paths["latest_json"], payload)
    _write_json_atomic(JSON_FILE, payload)
    _write_heartbeat(
        {
            "ok": True,
            "mode": "discovery_progress",
            "phase": "completed",
            "last_run_at": timestamp,
            "last_progress_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "output_tag": clean_output_tag,
            "search_mode": clean_search_mode,
            "current_batch": total_batches,
            "total_batches": total_batches,
            "total_candidates": len(all_candidates),
            "top_unique_symbols": [
                {
                    "symbol": row.get("symbol"),
                    "interval": row.get("interval"),
                    "roi_pct_on_paper_balance": row.get("roi_pct_on_paper_balance"),
                    "win_rate": row.get("win_rate"),
                    "profit_factor": row.get("profit_factor"),
                    "best_tradable_leverage": row.get("best_tradable_leverage"),
                }
                for row in _top_unique_symbols(all_candidates, limit=5)
            ],
            "failed_batches": len([failure for failure in failures if failure.get("batch_id")]),
            "csv_v2_path": str(artifact_paths["csv_v2"]),
            "tagged_json_path": str(artifact_paths["latest_json"]),
        }
    )
    return payload


def run_rotation(
    symbols: str | None = None,
    exclude_symbols: str | None = None,
    groups: str = "high",
    cycles: int | None = 1,
    sleep_seconds: int = 300,
    lookback_days: int = 60,
    windows: int = 3,
    min_closed_trades: int = 8,
    top_n_per_batch: int = 10,
    top_n_global: int = 30,
    batch_size: int = 5,
    leverage_values: str | None = None,
    wallet_balance_usd: float = 1_000.0,
    symbol_preset: str = "core",
    output_tag: str | None = None,
    search_mode: str = "standard",
    trigger_reference: str = "last_price",
    execution_model: str = "taker_market",
) -> dict[str, Any]:
    safe_cycles = None if cycles is None else max(1, min(int(cycles or 1), 288))
    safe_sleep = max(30, int(sleep_seconds or 300))
    clean_output_tag = _clean_output_tag(output_tag, symbol_preset)
    artifact_paths = _artifact_paths(clean_output_tag)
    cycle_reports: list[dict[str, Any]] = []
    global_candidates: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc).isoformat()
    index = 0
    while safe_cycles is None or index < safe_cycles:
        payload = run_discovery(
            symbols=symbols,
            exclude_symbols=exclude_symbols,
            groups=groups,
            lookback_days=lookback_days,
            windows=windows,
            min_closed_trades=min_closed_trades,
            top_n_per_batch=top_n_per_batch,
            top_n_global=top_n_global,
            batch_size=batch_size,
            leverage_values=leverage_values,
            wallet_balance_usd=wallet_balance_usd,
            symbol_preset=symbol_preset,
            output_tag=clean_output_tag,
            search_mode=search_mode,
            trigger_reference=trigger_reference,
            execution_model=execution_model,
        )
        top = payload.get("top_global") or []
        top_unique = payload.get("top_unique_symbols") or _top_unique_symbols(top, limit=5)
        global_candidates.extend(top)
        best = top[0] if top else {}
        cycle_report = {
            "cycle": index + 1,
            "run_id": payload.get("run_id"),
            "timestamp": payload.get("timestamp"),
            "total_candidates": payload.get("total_candidates"),
            "best": best,
            "top_unique_symbols": top_unique[:5],
            "failed_fetches_count": len(payload.get("failed_fetches") or []),
        }
        cycle_reports.append(cycle_report)
        _write_heartbeat(
            {
                "ok": True,
                "mode": "rotation",
                "last_cycle_at": payload.get("timestamp"),
                "cycle": index + 1,
                "cycles": safe_cycles if safe_cycles is not None else "forever",
                "run_id": payload.get("run_id"),
                "output_tag": clean_output_tag,
                "search_mode": str(search_mode or "standard").strip().lower(),
                "total_candidates": payload.get("total_candidates"),
                "failed_fetches_count": len(payload.get("failed_fetches") or []),
                "best": {
                    "symbol": best.get("symbol"),
                    "interval": best.get("interval"),
                    "roi_pct_on_paper_balance": best.get("roi_pct_on_paper_balance"),
                    "win_rate": best.get("win_rate"),
                    "profit_factor": best.get("profit_factor"),
                    "best_tradable_leverage": best.get("best_tradable_leverage"),
                },
                "top_unique_symbols": [
                    {
                        "symbol": row.get("symbol"),
                        "interval": row.get("interval"),
                        "roi_pct_on_paper_balance": row.get("roi_pct_on_paper_balance"),
                        "win_rate": row.get("win_rate"),
                        "profit_factor": row.get("profit_factor"),
                        "best_tradable_leverage": row.get("best_tradable_leverage"),
                    }
                    for row in top_unique[:5]
                ],
                "csv_v2_path": str(artifact_paths["csv_v2"]),
                "tagged_json_path": str(artifact_paths["latest_json"]),
            }
        )
        print(
            f"[{payload['timestamp']}] cycle={index + 1}/{safe_cycles if safe_cycles is not None else 'forever'} candidates={payload.get('total_candidates')} "
            f"best={best.get('symbol')} {best.get('interval')} roi={best.get('roi_pct_on_paper_balance')} "
            f"wr={best.get('win_rate')} pf={best.get('profit_factor')}",
            flush=True,
        )
        top_unique_text = _format_top_unique(top_unique, limit=5)
        if top_unique_text:
            print(f"top_unique={top_unique_text}", flush=True)
        index += 1
        if safe_cycles is None or index < safe_cycles:
            time.sleep(safe_sleep)

    global_candidates.sort(key=lambda row: (_candidate_score(row), _as_float(row.get("roi_pct_on_paper_balance"))), reverse=True)
    payload = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "mode": "rotation",
        "groups": groups,
        "symbol_preset": symbol_preset,
        "exclude_symbols": _parse_csv(exclude_symbols, []) if exclude_symbols else [],
        "output_tag": clean_output_tag,
        "search_mode": str(search_mode or "standard").strip().lower(),
        "trigger_reference": str(trigger_reference or "last_price").strip().lower(),
        "execution_model": str(execution_model or "taker_market").strip().lower(),
        "cycles": safe_cycles if safe_cycles is not None else "forever",
        "sleep_seconds": safe_sleep,
        "wallet_balance_usd_assumed": wallet_balance_usd,
        "leverage_values": _parse_leverage_values(leverage_values),
        "perps_methodology": {
            "mode": "isolated_margin_proxy",
            "assumed_margin_mode": "isolated",
            "assumed_asset_mode": "single_asset",
            "assumed_position_mode": "one_way",
            "assumed_execution_model": str(execution_model or "taker_market").strip().lower(),
            "assumed_trigger_reference": "mark_price_for_liquidation_last_price_for_entry_exit",
            "maintenance_margin_rate": DEFAULT_MAINTENANCE_MARGIN_RATE,
            "maintenance_margin_source": "proxy_until_signed_leverage_bracket_policy",
            "funding_source": "aster_public_funding_history_fapi_v3_with_fixed_fallback",
            "fee_model": "Aster official docs: USDT taker 4bps, USD1 taker 0.5bps, maker 0bps; applied as round-trip estimate in perps scenarios",
            "liquidation_rule": "scenario_invalid_when_estimated_adverse_move_pct_reaches_liquidation_move_before_or_at_stop",
            "caveat": "proxy_not_exchange_exact_margin_engine",
        },
        "total_candidates_seen": len(global_candidates),
        "cycle_reports": cycle_reports,
        "top_global": _unique_by_signature(global_candidates, max(1, min(int(top_n_global or 30), 100))),
        "top_unique_symbols": _top_unique_symbols(global_candidates, limit=10),
        "champion_categories": _champion_categories(global_candidates, limit=max(3, min(int(top_n_global or 30), 20))),
        "csv_path": str(CSV_FILE),
        "csv_v2_path": str(artifact_paths["csv_v2"]),
        "json_path": str(JSON_FILE),
        "tagged_json_path": str(artifact_paths["latest_json"]),
        "rotation_json_path": str(ROTATION_FILE),
        "tagged_rotation_json_path": str(artifact_paths["rotation_json"]),
        "artifact_policy": "legacy_csv_and_latest_kept_for_compatibility_tagged_v2_outputs_are_primary_for_research",
        "would_write_db": False,
        "would_trade": False,
    }
    _write_json_atomic(artifact_paths["rotation_json"], payload)
    _write_json_atomic(ROTATION_FILE, payload)
    _write_heartbeat(
        {
            "ok": True,
            "mode": "rotation_complete",
            "finished_at": payload.get("finished_at"),
            "cycles": safe_cycles if safe_cycles is not None else "forever",
            "output_tag": clean_output_tag,
            "total_candidates_seen": len(global_candidates),
            "tagged_rotation_json_path": str(artifact_paths["rotation_json"]),
        }
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Discovery large multi-symboles/multi-timeframes Aster, read-only.")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--exclude-symbols", default=None, help="Liste de symboles a exclure du preset, utile pour les lanes exploration.")
    parser.add_argument("--search-mode", choices=["standard", "exploration", "deep"], default="standard", help="standard=grille actuelle, exploration=grille elargie, deep=plus lent.")
    parser.add_argument("--trigger-reference", choices=["last_price", "mark_price"], default="last_price", help="last_price=ancien replay, mark_price=utilise markPriceKlines futures quand disponible.")
    parser.add_argument("--execution-model", choices=["taker_market", "maker_post_only", "bbo_limit"], default="taker_market", help="Mode cout execution: taker immediat, maker post-only cout seul, ou BBO proxy.")
    parser.add_argument("--symbol-preset", choices=sorted(SYMBOL_PRESETS.keys()), default="core")
    parser.add_argument("--output-tag", default=None, help="Tag stable pour separer les artefacts CSV/JSON, ex: core, macro, equities.")
    parser.add_argument("--groups", choices=["low", "high", "both"], default="both")
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--min-closed-trades", type=int, default=8)
    parser.add_argument("--top-n-per-batch", type=int, default=10)
    parser.add_argument("--top-n-global", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--leverage-values", default="1,2,3,5")
    parser.add_argument("--wallet-balance-usd", type=float, default=1000.0)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=int, default=300)
    parser.add_argument("--run-forever", action="store_true")
    args = parser.parse_args()

    cycles = None if args.run_forever else args.cycles
    if args.run_forever or int(cycles or 1) > 1:
        payload = run_rotation(
            symbols=args.symbols,
            exclude_symbols=args.exclude_symbols,
            groups=args.groups,
            cycles=cycles,
            sleep_seconds=args.sleep_seconds,
            lookback_days=args.lookback_days,
            windows=args.windows,
            min_closed_trades=args.min_closed_trades,
            top_n_per_batch=args.top_n_per_batch,
            top_n_global=args.top_n_global,
            batch_size=args.batch_size,
            leverage_values=args.leverage_values,
            wallet_balance_usd=args.wallet_balance_usd,
            symbol_preset=args.symbol_preset,
            output_tag=args.output_tag,
            search_mode=args.search_mode,
            trigger_reference=args.trigger_reference,
            execution_model=args.execution_model,
        )
        best = (payload.get("top_global") or [{}])[0]
        print(
            f"[{payload['finished_at']}] rotation_complete cycles={payload.get('cycles')} "
            f"best={best.get('symbol')} {best.get('interval')} roi={best.get('roi_pct_on_paper_balance')} "
            f"wr={best.get('win_rate')} pf={best.get('profit_factor')}"
        )
        print(f"csv={CSV_FILE}")
        print(f"csv_v2={payload.get('csv_v2_path')}")
        print(f"json={JSON_FILE}")
        print(f"tagged_json={payload.get('tagged_json_path')}")
        print(f"rotation_json={ROTATION_FILE}")
        print(f"tagged_rotation_json={payload.get('tagged_rotation_json_path')}")
        return

    payload = run_discovery(
        symbols=args.symbols,
        exclude_symbols=args.exclude_symbols,
        groups=args.groups,
        lookback_days=args.lookback_days,
        windows=args.windows,
        min_closed_trades=args.min_closed_trades,
        top_n_per_batch=args.top_n_per_batch,
        top_n_global=args.top_n_global,
        batch_size=args.batch_size,
        leverage_values=args.leverage_values,
        wallet_balance_usd=args.wallet_balance_usd,
        symbol_preset=args.symbol_preset,
        output_tag=args.output_tag,
        search_mode=args.search_mode,
        trigger_reference=args.trigger_reference,
        execution_model=args.execution_model,
    )
    best = (payload.get("top_global") or [{}])[0]
    print(
        f"[{payload['timestamp']}] run={payload['run_id']} candidates={payload['total_candidates']} "
        f"best={best.get('symbol')} {best.get('interval')} roi={best.get('roi_pct_on_paper_balance')} "
        f"wr={best.get('win_rate')} pf={best.get('profit_factor')}"
    )
    print(f"csv={CSV_FILE}")
    print(f"csv_v2={payload.get('csv_v2_path')}")
    print(f"json={JSON_FILE}")
    print(f"tagged_json={payload.get('tagged_json_path')}")


if __name__ == "__main__":
    main()
