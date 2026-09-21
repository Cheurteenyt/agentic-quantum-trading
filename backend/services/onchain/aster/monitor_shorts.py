from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from services.onchain.aster.aster_paper_trading_sandbox import (
    SELECTED_SHORT_FADE_FORWARD_SYMBOLS,
    _aster_score_proxy,
    _fetch_recent_trades_with_spot_fallback,
    _replay_trade_diagnostics,
    _replay_trades,
    _trade_price,
    get_aster_paper_trading_ledger_analytics,
    get_aster_selected_short_fade_forward_monitor_preview,
    get_aster_volatile_universe_short_backtest_preview,
)


SUMMARY_LOG_FILE = Path(__file__).with_name("paper_trading_multi_strategy_monitor.csv")
STRATEGY_LOG_FILE = Path(__file__).with_name("paper_trading_strategy_monitor.csv")
DIRECTIONAL_LOG_FILE = Path(__file__).with_name("paper_trading_directional_strategy_monitor.csv")
SELECTED_SYMBOLS_CSV = ",".join(SELECTED_SHORT_FADE_FORWARD_SYMBOLS)
SELECTED_LONG_BREAKOUT_SYMBOLS = ["TIAUSDT", "SEIUSDT", "JUPUSDT", "WLDUSDT"]
LONG_SYMBOLS_CSV = ",".join(SELECTED_LONG_BREAKOUT_SYMBOLS)
CONFIRM = "CONFIRM_STATEFUL_FORWARD_PAPER_TRADE"

LONG_STRATEGIES = [
    {
        "name": "long_quick_scalp_70",
        "min_score": 70.0,
        "min_volume": 1_000.0,
        "stop_loss": -2.5,
        "take_profit": 3.5,
        "trail_activation": 2.0,
        "trail_distance": 1.0,
    },
    {
        "name": "long_momentum_balanced_70",
        "min_score": 70.0,
        "min_volume": 1_000.0,
        "stop_loss": -4.0,
        "take_profit": 6.0,
        "trail_activation": 4.0,
        "trail_distance": 2.0,
    },
    {
        "name": "long_strict_momentum_80",
        "min_score": 80.0,
        "min_volume": 1_000.0,
        "stop_loss": -5.0,
        "take_profit": 8.0,
        "trail_activation": 5.0,
        "trail_distance": 2.5,
    },
    {
        "name": "long_high_volume_breakout_75",
        "min_score": 75.0,
        "min_volume": 5_000.0,
        "stop_loss": -6.0,
        "take_profit": 10.0,
        "trail_activation": 6.0,
        "trail_distance": 3.0,
    },
    {
        "name": "long_high_volume_scalp_75",
        "min_score": 75.0,
        "min_volume": 5_000.0,
        "stop_loss": -3.0,
        "take_profit": 5.0,
        "trail_activation": 3.0,
        "trail_distance": 1.5,
    },
    {
        "name": "long_extreme_volume_breakout_80",
        "min_score": 80.0,
        "min_volume": 5_000.0,
        "stop_loss": -5.0,
        "take_profit": 8.0,
        "trail_activation": 4.0,
        "trail_distance": 2.0,
    },
    {
        "name": "long_whale_volume_breakout_75",
        "min_score": 75.0,
        "min_volume": 10_000.0,
        "stop_loss": -5.0,
        "take_profit": 8.0,
        "trail_activation": 4.0,
        "trail_distance": 2.0,
    },
]

LONG_PULLBACK_STRATEGIES = [
    {"name": "long_pullback_2_tp4_sl3", "pullback": 2.0, "take_profit": 4.0, "stop_loss": -3.0, "wait_trades": 120, "max_hold": 300},
    {"name": "long_pullback_3_tp6_sl4", "pullback": 3.0, "take_profit": 6.0, "stop_loss": -4.0, "wait_trades": 160, "max_hold": 400},
    {"name": "long_pullback_5_tp8_sl5", "pullback": 5.0, "take_profit": 8.0, "stop_loss": -5.0, "wait_trades": 220, "max_hold": 500},
]

SUMMARY_HEADERS = [
    "timestamp",
    "mode",
    "symbols",
    "ledger_total_entries",
    "ledger_total_exits",
    "ledger_win_rate",
    "ledger_net_pnl_usd",
    "ledger_max_drawdown_usd",
    "forward_closed_this_scan",
    "forward_realized_pnl_this_scan",
    "forward_would_insert_rows",
    "forward_rows_inserted",
    "forward_health_status",
    "best_strategy_name",
    "best_strategy_entries",
    "best_strategy_closed_trades",
    "best_strategy_win_rate",
    "best_strategy_profit_factor",
    "best_strategy_pnl_usd",
    "best_strategy_max_drawdown_usd",
]

STRATEGY_HEADERS = [
    "timestamp",
    "strategy_name",
    "symbols",
    "entries",
    "closed_trades",
    "win_rate",
    "profit_factor",
    "pnl_total_usd",
    "max_drawdown_usd",
    "robustness_status",
    "source_verdict",
]

DIRECTIONAL_HEADERS = [
    "timestamp",
    "direction",
    "strategy_name",
    "symbols",
    "entries",
    "closed_trades",
    "win_rate",
    "profit_factor",
    "pnl_total_usd",
    "max_drawdown_usd",
    "avg_mfe_pct",
    "stop_loss_hit_rate",
    "status",
]


def _ensure_csv(path: Path, headers: list[str]) -> None:
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(headers)


def _write_row(path: Path, headers: list[str], row: dict[str, Any]) -> None:
    _ensure_csv(path, headers)
    with path.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow([row.get(key) for key in headers])


def _best_strategy(aggregate: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    best_name: str | None = None
    best_score: float | None = None
    best_row: dict[str, Any] = {}
    for name, row in aggregate.items():
        pnl = float(row.get("pnl_total_usd") or 0.0)
        closed = int(row.get("closed_trades") or 0)
        win_rate = row.get("win_rate")
        pf = row.get("profit_factor")
        pf_eval = 999.0 if pf == "unbounded_no_losses" else float(pf or 0.0)
        score = pnl + closed + (float(win_rate or 0.0) * 25.0) + min(25.0, pf_eval)
        if best_score is None or score > best_score:
            best_name = name
            best_score = score
            best_row = row
    return best_name, best_row


def _long_summary_from_rows(rows: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    diag = _replay_trade_diagnostics(rows)
    closed = diag.get("closed_trades") or []
    wins = int(diag.get("wins") or 0)
    losses = int(diag.get("losses") or 0)
    win_rate = round(wins / len(closed), 6) if closed else None
    return {
        "entries": report.get("simulated_trade_count"),
        "closed_trades": len(closed),
        "win_rate": win_rate,
        "profit_factor": diag.get("profit_factor") or ("unbounded_no_losses" if wins > 0 and losses == 0 else None),
        "pnl_total_usd": report.get("pnl_total_usd"),
        "max_drawdown_usd": report.get("max_drawdown_usd"),
        "avg_mfe_pct": diag.get("avg_mfe_pct"),
        "stop_loss_hit_rate": diag.get("stop_loss_hit_rate"),
    }


def _aggregate_long_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    entries = sum(int(row.get("entries") or 0) for row in summaries)
    closed = sum(int(row.get("closed_trades") or 0) for row in summaries)
    pnl = sum(float(row.get("pnl_total_usd") or 0.0) for row in summaries)
    max_dd = max([float(row.get("max_drawdown_usd") or 0.0) for row in summaries] or [0.0])
    wins = 0
    stop_weight = 0.0
    stop_count = 0
    mfe_weight = 0.0
    mfe_count = 0
    gross_profit_proxy = 0.0
    gross_loss_proxy = 0.0
    for row in summaries:
        row_closed = int(row.get("closed_trades") or 0)
        row_win_rate = row.get("win_rate")
        if row_win_rate is not None and row_closed:
            wins += round(float(row_win_rate) * row_closed)
        row_pnl = float(row.get("pnl_total_usd") or 0.0)
        if row_pnl > 0:
            gross_profit_proxy += row_pnl
        elif row_pnl < 0:
            gross_loss_proxy += abs(row_pnl)
        if row.get("stop_loss_hit_rate") is not None and row_closed:
            stop_weight += float(row.get("stop_loss_hit_rate") or 0.0) * row_closed
            stop_count += row_closed
        if row.get("avg_mfe_pct") is not None and row_closed:
            mfe_weight += float(row.get("avg_mfe_pct") or 0.0) * row_closed
            mfe_count += row_closed
    return {
        "entries": entries,
        "closed_trades": closed,
        "win_rate": round(wins / closed, 6) if closed else None,
        "profit_factor": round(gross_profit_proxy / gross_loss_proxy, 6) if gross_loss_proxy else ("unbounded_no_losses" if gross_profit_proxy > 0 and closed else None),
        "pnl_total_usd": round(pnl, 6),
        "max_drawdown_usd": round(max_dd, 6),
        "avg_mfe_pct": round(mfe_weight / mfe_count, 6) if mfe_count else None,
        "stop_loss_hit_rate": round(stop_weight / stop_count, 6) if stop_count else None,
    }


def _replay_long_pullback(trades: list[dict[str, Any]], strategy: dict[str, Any]) -> dict[str, Any]:
    balance = 1000.0
    initial_balance = balance
    position: dict[str, float] | None = None
    setup: dict[str, float | int] | None = None
    closed: list[float] = []
    max_drawdown = 0.0
    peak_equity = balance
    entries = 0
    fee_bps = 6.0
    slippage_bps = 10.0
    for idx, trade in enumerate(trades):
        price = _trade_price(trade)
        if price <= 0:
            continue
        if position:
            entry = float(position["entry"])
            size = float(position["size"])
            peak = max(float(position["peak"]), price)
            position["peak"] = peak
            pnl_unrealized = ((price - entry) / entry * size) if entry > 0 else 0.0
            equity = balance + pnl_unrealized
            peak_equity = max(peak_equity, equity)
            max_drawdown = max(max_drawdown, peak_equity - equity)
            pnl_pct = ((price - entry) / entry * 100) if entry > 0 else 0.0
            trailing_active = peak >= entry * 1.03 if entry > 0 else False
            trailing_exit = trailing_active and price <= peak * 0.98
            time_exit = idx - int(position["entry_idx"]) >= int(strategy["max_hold"])
            if pnl_pct <= float(strategy["stop_loss"]) or pnl_pct >= float(strategy["take_profit"]) or trailing_exit or time_exit:
                fees = size * fee_bps / 10_000
                slippage = size * slippage_bps / 10_000
                pnl = pnl_unrealized - fees - slippage
                balance += pnl
                closed.append(pnl)
                position = None
            continue

        if setup:
            if idx - int(setup["idx"]) > int(strategy["wait_trades"]):
                setup = None
            elif price <= float(setup["anchor"]) * (1 - float(strategy["pullback"]) / 100):
                score = float(setup["score"])
                size = 50.0 * min(2.0, max(0.0, score) / 50.0)
                fees = size * fee_bps / 10_000
                slippage = size * slippage_bps / 10_000
                balance -= fees + slippage
                position = {"entry": price, "size": size, "peak": price, "entry_idx": float(idx)}
                entries += 1
                setup = None
            continue

        window = trades[max(0, idx - 19) : idx + 1]
        score = _aster_score_proxy(window)
        if float(score.get("aster_score") or 0.0) >= 70.0 and float(score.get("window_volume_usd") or 0.0) >= 1000.0:
            setup = {"idx": idx, "anchor": price, "score": float(score.get("aster_score") or 0.0)}
    if position and trades:
        price = _trade_price(trades[-1])
        entry = float(position["entry"])
        size = float(position["size"])
        balance += ((price - entry) / entry * size) if entry > 0 else 0.0
    wins = sum(1 for pnl in closed if pnl > 0)
    losses = sum(1 for pnl in closed if pnl < 0)
    gross_profit = sum(pnl for pnl in closed if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in closed if pnl < 0))
    return {
        "entries": entries,
        "closed_trades": len(closed),
        "win_rate": round(wins / len(closed), 6) if closed else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else ("unbounded_no_losses" if gross_profit > 0 and closed else None),
        "pnl_total_usd": round(balance - initial_balance, 6),
        "max_drawdown_usd": round(max_drawdown, 6),
        "wins": wins,
        "losses": losses,
    }


def run_long_pullback_backtest_cycle(
    *,
    symbols: str = SELECTED_SYMBOLS_CSV,
    max_events: int = 1000,
) -> dict[str, Any]:
    clean_symbols = [item.strip().upper() for item in str(symbols or "").split(",") if item.strip()][:10]
    by_strategy: dict[str, list[dict[str, Any]]] = {str(item["name"]): [] for item in LONG_PULLBACK_STRATEGIES}
    failed_symbols: list[dict[str, Any]] = []
    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, max_events, 10)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status")})
            continue
        trades = fetched.get("trades") or []
        for strategy in LONG_PULLBACK_STRATEGIES:
            by_strategy[str(strategy["name"])].append(_replay_long_pullback(trades, strategy))
    aggregate = {name: _aggregate_long_summaries(rows) for name, rows in by_strategy.items()}
    best_name, best = _best_strategy(aggregate)
    return {
        "ok": True,
        "dry_run": True,
        "symbols": clean_symbols,
        "direction": "long_pullback",
        "aggregate_by_strategy": aggregate,
        "best_pullback_strategy_name": best_name,
        "best_pullback_strategy": best,
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
    }


def run_long_directional_backtest_cycle(
    *,
    symbols: str = SELECTED_SYMBOLS_CSV,
    max_events: int = 1000,
) -> dict[str, Any]:
    clean_symbols = [item.strip().upper() for item in str(symbols or "").split(",") if item.strip()][:10]
    by_strategy: dict[str, list[dict[str, Any]]] = {str(item["name"]): [] for item in LONG_STRATEGIES}
    failed_symbols: list[dict[str, Any]] = []
    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, max_events, 10)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status")})
            continue
        trades = fetched.get("trades") or []
        for strategy in LONG_STRATEGIES:
            rows, report = _replay_trades(
                trades,
                f"long-directional-{strategy['name']}-{symbol}-{int(time.time())}",
                symbol,
                1000.0,
                6.0,
                10.0,
                20,
                min_aster_score=float(strategy["min_score"]),
                min_window_volume_usd=float(strategy["min_volume"]),
                stop_loss_pct=float(strategy["stop_loss"]),
                take_profit_pct=float(strategy["take_profit"]),
                trailing_stop_activation_pct=float(strategy["trail_activation"]),
                trailing_stop_distance_pct=float(strategy["trail_distance"]),
                max_holding_trades=600,
            )
            by_strategy[str(strategy["name"])].append(_long_summary_from_rows(rows, report))
    aggregate = {name: _aggregate_long_summaries(rows) for name, rows in by_strategy.items()}
    best_name, best = _best_strategy(aggregate)
    return {
        "ok": True,
        "dry_run": True,
        "symbols": clean_symbols,
        "direction": "long",
        "aggregate_by_strategy": aggregate,
        "best_long_strategy_name": best_name,
        "best_long_strategy": best,
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
    }


def run_forward_selected_cycle(
    *,
    persist_forward: bool = False,
    symbols: str = SELECTED_SYMBOLS_CSV,
    forward_window_trades: int = 800,
) -> dict[str, Any]:
    return get_aster_selected_short_fade_forward_monitor_preview(
        symbols=symbols,
        dry_run=not persist_forward,
        confirm=CONFIRM if persist_forward else None,
        forward_window_trades=forward_window_trades,
        timeout_seconds=10,
        wallet_balance_usd=1000.0,
        rate_limit_delay_ms=300,
    )


def run_multi_strategy_backtest_cycle(
    *,
    symbols: str = SELECTED_SYMBOLS_CSV,
    max_events: int = 1000,
) -> dict[str, Any]:
    return get_aster_volatile_universe_short_backtest_preview(
        symbols=symbols,
        dry_run=True,
        max_symbols=10,
        max_events=max_events,
        timeout_seconds=10,
        wallet_balance_usd=1000.0,
        rate_limit_delay_ms=300,
        min_aster_score=70.0,
        min_window_volume_usd=1000.0,
    )


def run_cycle(
    *,
    persist_forward: bool | None = None,
    symbols: str = SELECTED_SYMBOLS_CSV,
    backtest_max_events: int = 1000,
    forward_window_trades: int = 800,
) -> dict[str, Any]:
    if persist_forward is None:
        persist_forward = os.getenv("ASTER_MONITOR_PERSIST", "").strip() == "1"

    timestamp = datetime.now().isoformat()
    forward = run_forward_selected_cycle(
        persist_forward=persist_forward,
        symbols=symbols,
        forward_window_trades=forward_window_trades,
    )
    backtest = run_multi_strategy_backtest_cycle(symbols=symbols, max_events=backtest_max_events)
    long_backtest = run_long_directional_backtest_cycle(symbols=symbols, max_events=backtest_max_events)
    pullback_backtest = run_long_pullback_backtest_cycle(symbols=symbols, max_events=backtest_max_events)
    metrics = get_aster_paper_trading_ledger_analytics(dry_run=True)

    aggregate = backtest.get("aggregate_by_params") or {}
    best_name, best = _best_strategy(aggregate)
    long_aggregate = long_backtest.get("aggregate_by_strategy") or {}
    best_long_name, best_long = _best_strategy(long_aggregate)
    pullback_aggregate = pullback_backtest.get("aggregate_by_strategy") or {}
    best_pullback_name, best_pullback = _best_strategy(pullback_aggregate)

    for strategy_name, row in aggregate.items():
        _write_row(
            DIRECTIONAL_LOG_FILE,
            DIRECTIONAL_HEADERS,
            {
                "timestamp": timestamp,
                "direction": "short",
                "strategy_name": strategy_name,
                "symbols": symbols,
                "entries": row.get("entries"),
                "closed_trades": row.get("closed_trades"),
                "win_rate": row.get("win_rate"),
                "profit_factor": row.get("profit_factor"),
                "pnl_total_usd": row.get("pnl_total_usd"),
                "max_drawdown_usd": row.get("max_drawdown_usd"),
                "avg_mfe_pct": None,
                "stop_loss_hit_rate": None,
                "status": row.get("robustness_status"),
            },
        )
        _write_row(
            STRATEGY_LOG_FILE,
            STRATEGY_HEADERS,
            {
                "timestamp": timestamp,
                "strategy_name": strategy_name,
                "symbols": symbols,
                "entries": row.get("entries"),
                "closed_trades": row.get("closed_trades"),
                "win_rate": row.get("win_rate"),
                "profit_factor": row.get("profit_factor"),
                "pnl_total_usd": row.get("pnl_total_usd"),
                "max_drawdown_usd": row.get("max_drawdown_usd"),
                "robustness_status": row.get("robustness_status"),
                "source_verdict": backtest.get("verdict"),
            },
        )

    for strategy_name, row in long_aggregate.items():
        _write_row(
            DIRECTIONAL_LOG_FILE,
            DIRECTIONAL_HEADERS,
            {
                "timestamp": timestamp,
                "direction": "long",
                "strategy_name": strategy_name,
                "symbols": symbols,
                "entries": row.get("entries"),
                "closed_trades": row.get("closed_trades"),
                "win_rate": row.get("win_rate"),
                "profit_factor": row.get("profit_factor"),
                "pnl_total_usd": row.get("pnl_total_usd"),
                "max_drawdown_usd": row.get("max_drawdown_usd"),
                "avg_mfe_pct": row.get("avg_mfe_pct"),
                "stop_loss_hit_rate": row.get("stop_loss_hit_rate"),
                "status": "directional_probe",
            },
        )

    for strategy_name, row in pullback_aggregate.items():
        _write_row(
            DIRECTIONAL_LOG_FILE,
            DIRECTIONAL_HEADERS,
            {
                "timestamp": timestamp,
                "direction": "long_pullback",
                "strategy_name": strategy_name,
                "symbols": symbols,
                "entries": row.get("entries"),
                "closed_trades": row.get("closed_trades"),
                "win_rate": row.get("win_rate"),
                "profit_factor": row.get("profit_factor"),
                "pnl_total_usd": row.get("pnl_total_usd"),
                "max_drawdown_usd": row.get("max_drawdown_usd"),
                "avg_mfe_pct": row.get("avg_mfe_pct"),
                "stop_loss_hit_rate": row.get("stop_loss_hit_rate"),
                "status": "pullback_probe",
            },
        )

    summary = {
        "timestamp": timestamp,
        "mode": "persist_forward" if persist_forward else "dry_run_forward",
        "symbols": symbols,
        "ledger_total_entries": metrics.get("total_entries"),
        "ledger_total_exits": metrics.get("total_exits"),
        "ledger_win_rate": metrics.get("win_rate"),
        "ledger_net_pnl_usd": metrics.get("net_pnl_usd"),
        "ledger_max_drawdown_usd": metrics.get("max_drawdown_usd"),
        "forward_closed_this_scan": forward.get("closed_in_session"),
        "forward_realized_pnl_this_scan": forward.get("realized_pnl_session"),
        "forward_would_insert_rows": forward.get("would_insert_rows"),
        "forward_rows_inserted": forward.get("rows_inserted"),
        "forward_health_status": forward.get("health_status"),
        "best_strategy_name": best_name,
        "best_strategy_entries": best.get("entries"),
        "best_strategy_closed_trades": best.get("closed_trades"),
        "best_strategy_win_rate": best.get("win_rate"),
        "best_strategy_profit_factor": best.get("profit_factor"),
        "best_strategy_pnl_usd": best.get("pnl_total_usd"),
        "best_strategy_max_drawdown_usd": best.get("max_drawdown_usd"),
    }
    _write_row(SUMMARY_LOG_FILE, SUMMARY_HEADERS, summary)

    return {
        "summary": summary,
        "forward_status": forward.get("selected_forward_status"),
        "forward_writes_performed": forward.get("writes_performed"),
        "backtest_verdict": backtest.get("verdict"),
        "best_long_strategy_name": best_long_name,
        "best_long_strategy": best_long,
        "best_pullback_strategy_name": best_pullback_name,
        "best_pullback_strategy": best_pullback,
        "directional_log_file": str(DIRECTIONAL_LOG_FILE),
        "strategy_log_file": str(STRATEGY_LOG_FILE),
        "summary_log_file": str(SUMMARY_LOG_FILE),
    }


def main() -> None:
    print("Aster multi-strategy paper monitor started. Press CTRL+C to stop.")
    print("Default mode is read-only. Set ASTER_MONITOR_PERSIST=1 to persist selected forward paper rows.")
    while True:
        try:
            result = run_cycle()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {result}")
            time.sleep(300)
        except KeyboardInterrupt:
            print("Aster multi-strategy paper monitor stopped.")
            break
        except Exception as exc:
            print(f"Monitor error: {exc}")
            time.sleep(60)


if __name__ == "__main__":
    main()
