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


LOG_FILE = Path(__file__).with_name("paper_trading_optimized_long_stateful_monitor.csv")
HEARTBEAT_FILE = Path(__file__).with_name("paper_trading_optimized_long_stateful_heartbeat.json")
DEFAULT_SYMBOLS = "INJUSDT,NEARUSDT,TIAUSDT"
CONFIRM = "CONFIRM_FORWARD_PAPER_TRADE"

HEADERS = [
    "timestamp",
    "mode",
    "symbols",
    "rows_inserted",
    "deduped_rows",
    "would_insert_rows",
    "health_status",
    "forward_pnl_usd",
    "forward_win_rate",
    "ledger_total_entries",
    "ledger_total_exits",
    "ledger_win_rate",
    "ledger_profit_factor",
    "ledger_net_pnl_usd",
    "ledger_max_drawdown_usd",
    "active_positions_count",
    "active_unrealized_pnl_usd",
    "new_trades_replayed_total",
    "mark_to_market_rows_total",
    "inj_entries",
    "inj_closed",
    "inj_new_trades_replayed",
    "inj_last_processed_before",
    "inj_has_active_position",
    "inj_unrealized_pnl_usd",
    "inj_current_price",
    "inj_last_processed_trade_id",
    "inj_trades_held",
    "near_entries",
    "near_closed",
    "near_new_trades_replayed",
    "near_last_processed_before",
    "near_has_active_position",
    "near_unrealized_pnl_usd",
    "near_current_price",
    "near_last_processed_trade_id",
    "near_trades_held",
    "tia_entries",
    "tia_closed",
    "tia_new_trades_replayed",
    "tia_last_processed_before",
    "tia_has_active_position",
    "tia_unrealized_pnl_usd",
    "tia_current_price",
    "tia_last_processed_trade_id",
    "tia_trades_held",
]


def _ensure_csv(path: Path) -> None:
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(HEADERS)


def _write_row(row: dict[str, Any]) -> None:
    _ensure_csv(LOG_FILE)
    with LOG_FILE.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow([row.get(key) for key in HEADERS])


def _write_heartbeat(payload: dict[str, Any], path: Path = HEARTBEAT_FILE) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _symbol_report(reports: dict[str, Any], symbol: str, key: str) -> Any:
    return (reports.get(symbol) or {}).get(key)


def _active_unrealized_pnl(reports: dict[str, Any], symbol: str) -> Any:
    active = (reports.get(symbol) or {}).get("active_position")
    if not isinstance(active, dict):
        return None
    return active.get("pnl_unrealized_usd")


def _active_field(reports: dict[str, Any], symbol: str, key: str) -> Any:
    active = (reports.get(symbol) or {}).get("active_position")
    if not isinstance(active, dict):
        return None
    return active.get(key)


def run_cycle(
    symbols: str = DEFAULT_SYMBOLS,
    persist: bool = False,
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
    allowed_entry_utc_hours: str | None = None,
) -> dict[str, Any]:
    monitor = get_aster_optimized_long_stateful_monitor(
        symbols=symbols,
        dry_run=not persist,
        confirm=CONFIRM if persist else None,
        forward_window_trades=forward_window_trades,
        timeout_seconds=timeout_seconds,
        rate_limit_delay_ms=rate_limit_delay_ms,
        allowed_entry_utc_hours=allowed_entry_utc_hours,
    )
    analytics = get_aster_paper_trading_ledger_analytics(dry_run=True)
    reports = monitor.get("symbol_reports") or {}
    active_positions = monitor.get("active_positions") or []
    active_unrealized = sum(
        float(position.get("pnl_unrealized_usd") or 0.0)
        for position in active_positions
        if isinstance(position, dict)
    )
    new_trades_total = sum(int((report or {}).get("new_trades_replayed") or 0) for report in reports.values())
    mark_rows_total = sum(int((report or {}).get("mark_to_market_rows") or 0) for report in reports.values())
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "persist" if persist else "dry_run",
        "symbols": symbols,
        "rows_inserted": monitor.get("rows_inserted"),
        "deduped_rows": monitor.get("deduped_rows"),
        "would_insert_rows": monitor.get("would_insert_rows"),
        "health_status": monitor.get("health_status"),
        "forward_pnl_usd": monitor.get("realized_pnl_session"),
        "forward_win_rate": monitor.get("session_win_rate"),
        "ledger_total_entries": analytics.get("total_entries"),
        "ledger_total_exits": analytics.get("total_exits"),
        "ledger_win_rate": analytics.get("win_rate"),
        "ledger_profit_factor": analytics.get("profit_factor"),
        "ledger_net_pnl_usd": analytics.get("net_pnl_usd"),
        "ledger_max_drawdown_usd": analytics.get("max_drawdown_usd"),
        "active_positions_count": len(active_positions),
        "active_unrealized_pnl_usd": round(active_unrealized, 6),
        "new_trades_replayed_total": new_trades_total,
        "mark_to_market_rows_total": mark_rows_total,
        "inj_entries": _symbol_report(reports, "INJUSDT", "entries"),
        "inj_closed": _symbol_report(reports, "INJUSDT", "exits"),
        "inj_new_trades_replayed": _symbol_report(reports, "INJUSDT", "new_trades_replayed"),
        "inj_last_processed_before": _symbol_report(reports, "INJUSDT", "last_processed_trade_id_before_cycle"),
        "inj_has_active_position": _symbol_report(reports, "INJUSDT", "has_active_position"),
        "inj_unrealized_pnl_usd": _active_unrealized_pnl(reports, "INJUSDT"),
        "inj_current_price": _active_field(reports, "INJUSDT", "current_price"),
        "inj_last_processed_trade_id": _active_field(reports, "INJUSDT", "last_processed_trade_id"),
        "inj_trades_held": _active_field(reports, "INJUSDT", "trades_held"),
        "near_entries": _symbol_report(reports, "NEARUSDT", "entries"),
        "near_closed": _symbol_report(reports, "NEARUSDT", "exits"),
        "near_new_trades_replayed": _symbol_report(reports, "NEARUSDT", "new_trades_replayed"),
        "near_last_processed_before": _symbol_report(reports, "NEARUSDT", "last_processed_trade_id_before_cycle"),
        "near_has_active_position": _symbol_report(reports, "NEARUSDT", "has_active_position"),
        "near_unrealized_pnl_usd": _active_unrealized_pnl(reports, "NEARUSDT"),
        "near_current_price": _active_field(reports, "NEARUSDT", "current_price"),
        "near_last_processed_trade_id": _active_field(reports, "NEARUSDT", "last_processed_trade_id"),
        "near_trades_held": _active_field(reports, "NEARUSDT", "trades_held"),
        "tia_entries": _symbol_report(reports, "TIAUSDT", "entries"),
        "tia_closed": _symbol_report(reports, "TIAUSDT", "exits"),
        "tia_new_trades_replayed": _symbol_report(reports, "TIAUSDT", "new_trades_replayed"),
        "tia_last_processed_before": _symbol_report(reports, "TIAUSDT", "last_processed_trade_id_before_cycle"),
        "tia_has_active_position": _symbol_report(reports, "TIAUSDT", "has_active_position"),
        "tia_unrealized_pnl_usd": _active_unrealized_pnl(reports, "TIAUSDT"),
        "tia_current_price": _active_field(reports, "TIAUSDT", "current_price"),
        "tia_last_processed_trade_id": _active_field(reports, "TIAUSDT", "last_processed_trade_id"),
        "tia_trades_held": _active_field(reports, "TIAUSDT", "trades_held"),
    }
    _write_row(row)
    return {"monitor": monitor, "analytics": analytics, "csv_row": row, "csv_path": str(LOG_FILE)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor paper-trading des longs Aster optimises.")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--cycles", type=int, default=1, help="Nombre de scans. Utilise --run-forever pour un mode AFK.")
    parser.add_argument("--sleep-seconds", type=int, default=300)
    parser.add_argument("--error-sleep-seconds", type=int, default=60)
    parser.add_argument("--run-forever", action="store_true", help="Tourne jusqu'a CTRL+C au lieu de s'arreter apres --cycles.")
    parser.add_argument("--max-runtime-hours", type=float, default=None, help="Stoppe automatiquement apres N heures, meme avec --run-forever.")
    parser.add_argument("--persist", action="store_true", help="Persiste dans le ledger paper avec confirm interne.")
    parser.add_argument("--forward-window-trades", type=int, default=800)
    parser.add_argument("--allowed-entry-utc-hours", default=None, help="Filtre optionnel des nouvelles entrees, ex: 12-18 ou 8,9,13. Les positions ouvertes restent monitorees.")
    args = parser.parse_args()

    cycles = None if args.run_forever else max(1, min(int(args.cycles or 1), 288))
    sleep_seconds = max(30, int(args.sleep_seconds or 300))
    error_sleep_seconds = max(30, int(args.error_sleep_seconds or 60))
    max_runtime_seconds = None
    if args.max_runtime_hours is not None:
        max_runtime_seconds = max(1, float(args.max_runtime_hours)) * 3600

    started_at = time.monotonic()
    index = 0
    while cycles is None or index < cycles:
        if max_runtime_seconds is not None and time.monotonic() - started_at >= max_runtime_seconds:
            print(f"[{datetime.now(timezone.utc).isoformat()}] max_runtime_reached stopping=true")
            break
        try:
            result = run_cycle(
                symbols=args.symbols,
                persist=bool(args.persist),
                forward_window_trades=args.forward_window_trades,
                allowed_entry_utc_hours=args.allowed_entry_utc_hours,
            )
            row = result["csv_row"]
            heartbeat = {
                "ok": True,
                "last_cycle_at": row["timestamp"],
                "mode": row["mode"],
                "cycle_index": index + 1,
                "run_forever": bool(args.run_forever),
                "allowed_entry_utc_hours": args.allowed_entry_utc_hours,
                "csv_path": str(LOG_FILE),
                "ledger_exits": row["ledger_total_exits"],
                "ledger_net_pnl_usd": row["ledger_net_pnl_usd"],
                "ledger_win_rate": row["ledger_win_rate"],
                "active_positions_count": row["active_positions_count"],
                "active_unrealized_pnl_usd": row["active_unrealized_pnl_usd"],
                "new_trades_replayed_total": row["new_trades_replayed_total"],
                "health_status": row["health_status"],
            }
            _write_heartbeat(heartbeat)
            print(
                f"[{row['timestamp']}] mode={row['mode']} "
                f"inserted={row['rows_inserted']} deduped={row['deduped_rows']} "
                f"ledger_exits={row['ledger_total_exits']} pnl={row['ledger_net_pnl_usd']} "
                f"wr={row['ledger_win_rate']} active={row['active_positions_count']} "
                f"latent={row['active_unrealized_pnl_usd']} new_trades={row['new_trades_replayed_total']} "
                f"health={row['health_status']}"
            )
            index += 1
            should_sleep = cycles is None or index < cycles
            if should_sleep:
                time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            print(f"[{datetime.now(timezone.utc).isoformat()}] interrupted stopping=true")
            break
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            _write_heartbeat({
                "ok": False,
                "last_cycle_at": now,
                "cycle_index": index + 1,
                "run_forever": bool(args.run_forever),
                "error": str(exc),
                "retry_in_seconds": error_sleep_seconds,
            })
            print(f"[{now}] cycle_error={type(exc).__name__}: {exc} retry_in={error_sleep_seconds}s")
            time.sleep(error_sleep_seconds)


if __name__ == "__main__":
    main()
