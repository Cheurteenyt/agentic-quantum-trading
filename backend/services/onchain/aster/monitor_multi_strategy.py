from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.aster_paper_trading_sandbox import (
    get_aster_optimized_long_stateful_monitor,
    get_aster_paper_trading_ledger_analytics,
)


LOG_FILE = Path(__file__).with_name("paper_trading_multi_strategy_stateful_monitor.csv")
HEARTBEAT_FILE = Path(__file__).with_name("paper_trading_multi_strategy_stateful_heartbeat.json")
CONFIRM = "CONFIRM_FORWARD_PAPER_TRADE"

STRATEGIES: dict[str, dict[str, Any]] = {
    "baseline": {
        "symbols": "INJUSDT,NEARUSDT,TIAUSDT",
        "allowed_entry_utc_hours": None,
        "event_type": "forward_optimized_long_ms_baseline",
        "persist_allowed": True,
    },
    "regime_filtered": {
        "symbols": "INJUSDT,NEARUSDT,TIAUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_regime_filtered",
        "persist_allowed": True,
    },
    "inj_tia_regime_filtered": {
        "symbols": "INJUSDT,TIAUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_inj_tia_regime",
        "persist_allowed": True,
    },
    "inj_tia_plus_candidates": {
        "symbols": "INJUSDT,TIAUSDT,JUPUSDT,BOMEUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_inj_tia_plus_candidates",
        "persist_allowed": True,
    },
    "inj_tia_fast_time_stop": {
        "symbols": "INJUSDT,TIAUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_inj_tia_fast_ts300",
        "max_holding_trades": 300,
        "persist_allowed": True,
    },
    "inj_fast_tia_standard": {
        "symbols": "INJUSDT,TIAUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_inj_fast_tia_standard",
        "max_holding_trades_by_symbol": {"INJUSDT": 300, "TIAUSDT": 600},
        "persist_allowed": True,
    },
    "inj_fast_time_stop": {
        "symbols": "INJUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_inj_fast_ts300",
        "max_holding_trades": 300,
        "persist_allowed": True,
    },
    "tia_fast_time_stop": {
        "symbols": "TIAUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_tia_fast_ts300",
        "max_holding_trades": 300,
        "persist_allowed": True,
    },
    "inj_only": {
        "symbols": "INJUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_inj_only",
        "persist_allowed": True,
    },
    "tia_only": {
        "symbols": "TIAUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_tia_only",
        "persist_allowed": True,
    },
    "near_only_observation": {
        "symbols": "NEARUSDT",
        "allowed_entry_utc_hours": "0-12,14-18,21-23",
        "event_type": "forward_optimized_long_ms_near_only_observation",
        "persist_allowed": True,
    },
    "utc_01_cluster": {
        "symbols": "INJUSDT,NEARUSDT,TIAUSDT",
        "allowed_entry_utc_hours": "1",
        "event_type": "forward_optimized_long_ms_utc01",
        "persist_allowed": True,
    },
}

HEADERS = [
    "timestamp",
    "strategy_id",
    "event_type",
    "mode",
    "symbols",
    "allowed_entry_utc_hours",
    "max_holding_trades",
    "persist_allowed",
    "health_status",
    "rows_inserted",
    "deduped_rows",
    "would_insert_rows",
    "closed_in_session",
    "realized_pnl_session",
    "session_win_rate",
    "active_positions_count",
    "active_unrealized_pnl_usd",
    "new_trades_replayed_total",
    "ledger_total_entries",
    "ledger_total_exits",
    "ledger_win_rate",
    "ledger_profit_factor",
    "ledger_net_pnl_usd",
    "ledger_max_drawdown_usd",
    "failed_symbols_count",
]


def _ensure_csv() -> None:
    if LOG_FILE.exists():
        try:
            with LOG_FILE.open("r", newline="", encoding="utf-8") as handle:
                first_row = next(csv.reader(handle), [])
        except (OSError, StopIteration):
            first_row = []
        if first_row == HEADERS:
            return
        legacy = LOG_FILE.with_name(f"{LOG_FILE.stem}.legacy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{LOG_FILE.suffix}")
        LOG_FILE.replace(legacy)
    if LOG_FILE.exists():
        return
    with LOG_FILE.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(HEADERS)


def _write_rows(rows: list[dict[str, Any]]) -> None:
    _ensure_csv()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([row.get(key) for key in HEADERS])


def _write_heartbeat(payload: dict[str, Any]) -> None:
    HEARTBEAT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _parse_strategy_ids(value: str | None) -> list[str]:
    if not value:
        return list(STRATEGIES)
    wanted = [item.strip() for item in str(value).replace(";", ",").split(",") if item.strip()]
    return [item for item in wanted if item in STRATEGIES] or list(STRATEGIES)


def _strategy_row(strategy_id: str, strategy: dict[str, Any], monitor: dict[str, Any], analytics: dict[str, Any], persist: bool) -> dict[str, Any]:
    reports = monitor.get("symbol_reports") or {}
    active_positions = monitor.get("active_positions") or []
    active_unrealized = sum(
        float(position.get("pnl_unrealized_usd") or 0.0)
        for position in active_positions
        if isinstance(position, dict)
    )
    new_trades = sum(int((report or {}).get("new_trades_replayed") or 0) for report in reports.values())
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy_id": strategy_id,
        "event_type": strategy.get("event_type"),
        "mode": "persist" if persist else "dry_run",
        "symbols": strategy.get("symbols"),
        "allowed_entry_utc_hours": strategy.get("allowed_entry_utc_hours"),
        "max_holding_trades": strategy.get("max_holding_trades") or strategy.get("max_holding_trades_by_symbol"),
        "persist_allowed": bool(strategy.get("persist_allowed")),
        "health_status": monitor.get("health_status"),
        "rows_inserted": monitor.get("rows_inserted"),
        "deduped_rows": monitor.get("deduped_rows"),
        "would_insert_rows": monitor.get("would_insert_rows"),
        "closed_in_session": monitor.get("closed_in_session"),
        "realized_pnl_session": monitor.get("realized_pnl_session"),
        "session_win_rate": monitor.get("session_win_rate"),
        "active_positions_count": len(active_positions),
        "active_unrealized_pnl_usd": round(active_unrealized, 6),
        "new_trades_replayed_total": new_trades,
        "ledger_total_entries": analytics.get("total_entries"),
        "ledger_total_exits": analytics.get("total_exits"),
        "ledger_win_rate": analytics.get("win_rate"),
        "ledger_profit_factor": analytics.get("profit_factor"),
        "ledger_net_pnl_usd": analytics.get("net_pnl_usd"),
        "ledger_max_drawdown_usd": analytics.get("max_drawdown_usd"),
        "failed_symbols_count": len(monitor.get("failed_symbols") or []),
    }


def run_cycle(
    strategy_ids: list[str] | None = None,
    persist: bool = False,
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for strategy_id in strategy_ids or list(STRATEGIES):
        strategy = STRATEGIES[strategy_id]
        strategy_persist = bool(persist and strategy.get("persist_allowed"))
        monitor = get_aster_optimized_long_stateful_monitor(
            symbols=strategy["symbols"],
            dry_run=not strategy_persist,
            confirm=CONFIRM if strategy_persist else None,
            forward_window_trades=forward_window_trades,
            timeout_seconds=timeout_seconds,
            rate_limit_delay_ms=rate_limit_delay_ms,
            allowed_entry_utc_hours=strategy.get("allowed_entry_utc_hours"),
            event_type_override=strategy.get("event_type"),
            max_holding_trades_override=strategy.get("max_holding_trades"),
            max_holding_trades_by_symbol=strategy.get("max_holding_trades_by_symbol"),
        )
        analytics = get_aster_paper_trading_ledger_analytics(dry_run=True, event_type=strategy.get("event_type"))
        row = _strategy_row(strategy_id, strategy, monitor, analytics, strategy_persist)
        rows.append(row)
        details[strategy_id] = {"monitor": monitor, "analytics": analytics, "csv_row": row}
    _write_rows(rows)
    _write_heartbeat({
        "ok": True,
        "last_cycle_at": datetime.now(timezone.utc).isoformat(),
        "strategies": strategy_ids or list(STRATEGIES),
        "csv_path": str(LOG_FILE),
        "rows": rows,
    })
    return {"ok": True, "rows": rows, "details": details, "csv_path": str(LOG_FILE), "heartbeat_path": str(HEARTBEAT_FILE)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor multi-strategies Aster paper-trading.")
    parser.add_argument("--strategies", default=None, help=f"Liste: {','.join(STRATEGIES)}")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=int, default=300)
    parser.add_argument("--error-sleep-seconds", type=int, default=60)
    parser.add_argument("--run-forever", action="store_true")
    parser.add_argument("--max-runtime-hours", type=float, default=None)
    parser.add_argument("--persist", action="store_true", help="Persiste seulement les strategies marquees persist_allowed.")
    parser.add_argument("--forward-window-trades", type=int, default=800)
    args = parser.parse_args()

    strategies = _parse_strategy_ids(args.strategies)
    cycles = None if args.run_forever else max(1, min(int(args.cycles or 1), 288))
    sleep_seconds = max(30, int(args.sleep_seconds or 300))
    error_sleep_seconds = max(30, int(args.error_sleep_seconds or 60))
    max_runtime_seconds = max(1, float(args.max_runtime_hours)) * 3600 if args.max_runtime_hours is not None else None
    started_at = time.monotonic()
    index = 0
    while cycles is None or index < cycles:
        if max_runtime_seconds is not None and time.monotonic() - started_at >= max_runtime_seconds:
            print(f"[{datetime.now(timezone.utc).isoformat()}] max_runtime_reached stopping=true")
            break
        try:
            result = run_cycle(
                strategy_ids=strategies,
                persist=bool(args.persist),
                forward_window_trades=args.forward_window_trades,
            )
            for row in result["rows"]:
                print(
                    f"[{row['timestamp']}] strategy={row['strategy_id']} mode={row['mode']} "
                    f"inserted={row['rows_inserted']} exits={row['ledger_total_exits']} "
                    f"pnl={row['ledger_net_pnl_usd']} wr={row['ledger_win_rate']} "
                    f"active={row['active_positions_count']} latent={row['active_unrealized_pnl_usd']} "
                    f"new_trades={row['new_trades_replayed_total']} health={row['health_status']}"
                )
            index += 1
            if cycles is None or index < cycles:
                time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            print(f"[{datetime.now(timezone.utc).isoformat()}] interrupted stopping=true")
            break
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            _write_heartbeat({"ok": False, "last_cycle_at": now, "error": str(exc), "retry_in_seconds": error_sleep_seconds})
            print(f"[{now}] cycle_error={type(exc).__name__}: {exc} retry_in={error_sleep_seconds}s")
            time.sleep(error_sleep_seconds)


if __name__ == "__main__":
    main()
