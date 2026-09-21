from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.aster_paper_trading_sandbox import (
    get_aster_paper_trading_focused_optimization_preview,
)


CSV_FILE = Path(__file__).with_name("paper_trading_champion_lanes_backtest.csv")
JSON_FILE = Path(__file__).with_name("paper_trading_champion_lanes_backtest_latest.json")

DEFAULT_SYMBOLS = "TIAUSDT,INJUSDT,NEARUSDT"
DEFAULT_LOW_INTERVALS = "15m,30m,1h"
DEFAULT_HIGH_INTERVALS = "2h,3h,4h,5h,6h"

HEADERS = [
    "timestamp",
    "batch_id",
    "symbols",
    "intervals",
    "tested_combinations",
    "accepted_candidates",
    "rank",
    "symbol",
    "interval",
    "risk_profile",
    "min_aster_score",
    "min_window_volume_usd",
    "stop_loss_pct",
    "take_profit_pct",
    "closed_trades",
    "win_rate",
    "profit_factor",
    "pnl_total_usd",
    "roi_pct_on_paper_balance",
    "max_drawdown_usd",
    "positive_windows",
    "verdict",
]


def _ensure_csv() -> None:
    if CSV_FILE.exists():
        return
    with CSV_FILE.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(HEADERS)


def _row(timestamp: str, batch_id: str, symbols: str, intervals: str, result: dict[str, Any], rank: int, candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "batch_id": batch_id,
        "symbols": symbols,
        "intervals": intervals,
        "tested_combinations": result.get("tested_combinations"),
        "accepted_candidates": result.get("accepted_candidates"),
        "rank": rank,
        "symbol": candidate.get("symbol"),
        "interval": candidate.get("interval"),
        "risk_profile": candidate.get("risk_profile"),
        "min_aster_score": candidate.get("min_aster_score"),
        "min_window_volume_usd": candidate.get("min_window_volume_usd"),
        "stop_loss_pct": candidate.get("stop_loss_pct"),
        "take_profit_pct": candidate.get("take_profit_pct"),
        "closed_trades": candidate.get("closed_trades"),
        "win_rate": candidate.get("win_rate"),
        "profit_factor": candidate.get("profit_factor"),
        "pnl_total_usd": candidate.get("pnl_total_usd"),
        "roi_pct_on_paper_balance": candidate.get("roi_pct_on_paper_balance"),
        "max_drawdown_usd": candidate.get("max_drawdown_usd"),
        "positive_windows": candidate.get("positive_windows"),
        "verdict": candidate.get("verdict"),
    }


def _write_csv(rows: list[dict[str, Any]]) -> None:
    _ensure_csv()
    with CSV_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([row.get(key) for key in HEADERS])


def run_batch(
    batch_id: str,
    symbols: str,
    intervals: str,
    lookback_days: int = 60,
    windows: int = 3,
    min_closed_trades: int = 8,
    top_n: int = 15,
) -> dict[str, Any]:
    result = get_aster_paper_trading_focused_optimization_preview(
        symbols=symbols,
        intervals=intervals,
        lookback_days=lookback_days,
        windows=windows,
        min_closed_trades=min_closed_trades,
        dry_run=True,
        rate_limit_delay_ms=100,
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    candidates = (result.get("ranked_candidates") or [])[: max(1, min(int(top_n or 15), 50))]
    rows = [_row(timestamp, batch_id, symbols, intervals, result, index + 1, candidate) for index, candidate in enumerate(candidates)]
    _write_csv(rows)
    payload = {
        "ok": bool(result.get("ok")),
        "timestamp": timestamp,
        "batch_id": batch_id,
        "symbols": symbols,
        "intervals": intervals,
        "lookback_days": lookback_days,
        "windows": windows,
        "min_closed_trades": min_closed_trades,
        "tested_combinations": result.get("tested_combinations"),
        "accepted_candidates": result.get("accepted_candidates"),
        "recommendation": result.get("recommendation"),
        "best_by_symbol": result.get("best_by_symbol"),
        "top_candidates": candidates,
        "failed_fetches": result.get("failed_fetches"),
        "csv_path": str(CSV_FILE),
    }
    JSON_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest focalise des lanes Aster championnes.")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--low-intervals", default=DEFAULT_LOW_INTERVALS)
    parser.add_argument("--high-intervals", default=DEFAULT_HIGH_INTERVALS)
    parser.add_argument("--group", choices=["low", "high", "both"], default="both")
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--min-closed-trades", type=int, default=8)
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args()

    batches: list[tuple[str, str]] = []
    if args.group in {"low", "both"}:
        batches.append(("champion_low_tf", args.low_intervals))
    if args.group in {"high", "both"}:
        batches.append(("champion_high_tf", args.high_intervals))

    for batch_id, intervals in batches:
        payload = run_batch(
            batch_id=batch_id,
            symbols=args.symbols,
            intervals=intervals,
            lookback_days=args.lookback_days,
            windows=args.windows,
            min_closed_trades=args.min_closed_trades,
            top_n=args.top_n,
        )
        rec = payload.get("recommendation") or {}
        print(
            f"[{payload['timestamp']}] batch={batch_id} tested={payload.get('tested_combinations')} "
            f"accepted={payload.get('accepted_candidates')} best={rec.get('symbol')} {rec.get('interval')} "
            f"roi={rec.get('roi_pct_on_paper_balance')} wr={rec.get('win_rate')} pf={rec.get('profit_factor')}"
        )
    print(f"csv={CSV_FILE}")
    print(f"json={JSON_FILE}")


if __name__ == "__main__":
    main()
