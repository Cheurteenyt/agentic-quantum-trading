from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.backtest_strategy_discovery import run_discovery, run_rotation


BASE_DIR = Path(__file__).resolve().parents[1]
WATCHLIST_FILE = BASE_DIR / "aster_priority_watchlist_latest.json"
PLAN_FILE = BASE_DIR / "aster_priority_watchlist_backtest_plan_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_symbols(value: str | list[str] | None) -> set[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    return {
        "".join(ch for ch in str(item or "").strip().upper() if ch.isalnum())[:32]
        for item in raw
        if str(item or "").strip()
    }


def _candidate_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for section in ("priority_watchlist", "candidate_watchlist", "top_scored_sample"):
        for row in payload.get(section) or []:
            if isinstance(row, dict) and row.get("symbol"):
                rows.append(row)
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol not in best or _float(row.get("priority_score")) > _float(best[symbol].get("priority_score")):
            best[symbol] = row
    return sorted(best.values(), key=lambda item: _float(item.get("priority_score")), reverse=True)


def build_priority_watchlist_backtest_plan(
    max_symbols: int = 12,
    min_priority_score: float = 35.0,
    include_statuses: str | list[str] | None = "priority,candidate",
    exclude_symbols: str | list[str] | None = None,
    write_snapshot: bool = True,
) -> dict[str, Any]:
    safe_max = max(1, min(int(max_symbols or 12), 50))
    safe_min_score = max(0.0, min(float(min_priority_score or 0.0), 100.0))
    statuses = {item.lower() for item in _parse_symbols(include_statuses)} or {"priority", "candidate"}
    excluded = _parse_symbols(exclude_symbols)
    payload = _load_json(WATCHLIST_FILE)
    if not payload:
        return {
            "ok": False,
            "status": "blocked_missing_priority_watchlist_snapshot",
            "snapshot_path": str(WATCHLIST_FILE),
            "symbols": [],
            "would_run_backtest": False,
        }

    selected = []
    rejected = []
    for row in _candidate_rows(payload):
        symbol = str(row.get("symbol") or "").upper()
        score = _float(row.get("priority_score"))
        status = str(row.get("priority_status") or "").lower()
        blockers = list(row.get("blockers") or [])
        if symbol in excluded:
            rejected.append({"symbol": symbol, "reason": "explicitly_excluded", "priority_score": score})
            continue
        if blockers:
            rejected.append({"symbol": symbol, "reason": "watchlist_blockers_present", "blockers": blockers, "priority_score": score})
            continue
        if status not in statuses:
            rejected.append({"symbol": symbol, "reason": "status_not_included", "priority_status": status, "priority_score": score})
            continue
        if score < safe_min_score:
            rejected.append({"symbol": symbol, "reason": "priority_score_below_threshold", "priority_score": score})
            continue
        selected.append(
            {
                "symbol": symbol,
                "priority_score": score,
                "priority_status": row.get("priority_status"),
                "quote_volume_24h": row.get("quote_volume_24h"),
                "price_change_pct_24h": row.get("price_change_pct_24h"),
                "spread_bps": row.get("spread_bps"),
                "ws_quality_verdict": row.get("ws_quality_verdict"),
                "mark_index_verdict": row.get("mark_index_verdict"),
                "reasons": row.get("reasons") or [],
            }
        )
        if len(selected) >= safe_max:
            break

    plan = {
        "ok": True,
        "status": "ready" if selected else "blocked_no_symbols_selected",
        "source_policy": "local_priority_watchlist_to_existing_backtest_runner",
        "generated_at": _now(),
        "inputs": {
            "priority_watchlist_snapshot": str(WATCHLIST_FILE),
            "max_symbols": safe_max,
            "min_priority_score": safe_min_score,
            "include_statuses": sorted(statuses),
            "exclude_symbols": sorted(excluded),
        },
        "symbols": [row["symbol"] for row in selected],
        "symbols_csv": ",".join(row["symbol"] for row in selected),
        "selected_rows": selected,
        "rejected_sample": rejected[:25],
        "runner": {
            "module": "services.onchain.aster.backtest_priority_watchlist",
            "delegates_to": "services.onchain.aster.backtest_strategy_discovery",
            "output_tag_default": "priority_watchlist",
            "symbol_preset_label": "priority_watchlist",
        },
        "safety": {
            "would_write_db": False,
            "would_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_external_api": False,
            "writes_performed": 0,
        },
    }
    if write_snapshot:
        PLAN_FILE.write_text(json.dumps(plan, indent=2, sort_keys=True, default=str), encoding="utf-8")
        plan["plan_path"] = str(PLAN_FILE)
        plan["safety"]["writes_performed"] = 1
    return plan


def run_priority_watchlist_backtest(
    max_symbols: int = 12,
    min_priority_score: float = 35.0,
    include_statuses: str | list[str] | None = "priority,candidate",
    exclude_symbols: str | list[str] | None = None,
    groups: str = "both",
    lookback_days: int = 60,
    windows: int = 3,
    min_closed_trades: int = 6,
    top_n_per_batch: int = 10,
    top_n_global: int = 60,
    batch_size: int = 3,
    leverage_values: str | None = "1,2,3,5,10,20",
    wallet_balance_usd: float = 1_000.0,
    output_tag: str = "priority_watchlist",
    search_mode: str = "exploration",
    trigger_reference: str = "last_price",
    execution_model: str = "taker_market",
    cycles: int | None = 1,
    sleep_seconds: int = 1200,
    run_forever: bool = False,
    plan_only: bool = False,
) -> dict[str, Any]:
    plan = build_priority_watchlist_backtest_plan(
        max_symbols=max_symbols,
        min_priority_score=min_priority_score,
        include_statuses=include_statuses,
        exclude_symbols=exclude_symbols,
        write_snapshot=True,
    )
    if plan_only or not plan.get("symbols_csv"):
        return {**plan, "plan_only": bool(plan_only), "would_run_backtest": bool(plan.get("symbols_csv"))}

    kwargs = {
        "symbols": plan["symbols_csv"],
        "exclude_symbols": None,
        "groups": groups,
        "lookback_days": lookback_days,
        "windows": windows,
        "min_closed_trades": min_closed_trades,
        "top_n_per_batch": top_n_per_batch,
        "top_n_global": top_n_global,
        "batch_size": batch_size,
        "leverage_values": leverage_values,
        "wallet_balance_usd": wallet_balance_usd,
        "symbol_preset": "priority_watchlist",
        "output_tag": output_tag,
        "search_mode": search_mode,
        "trigger_reference": trigger_reference,
        "execution_model": execution_model,
    }
    if run_forever or (cycles is not None and int(cycles or 1) > 1):
        result = run_rotation(
            **kwargs,
            cycles=None if run_forever else int(cycles or 1),
            sleep_seconds=sleep_seconds,
        )
    else:
        result = run_discovery(**kwargs)
    return {
        "ok": True,
        "status": "completed",
        "plan": plan,
        "backtest_result": result,
        "symbols": plan["symbols"],
        "output_tag": output_tag,
        "would_write_db": False,
        "would_trade": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Aster strategy discovery from the local priority watchlist snapshot.")
    parser.add_argument("--max-symbols", type=int, default=12)
    parser.add_argument("--min-priority-score", type=float, default=35.0)
    parser.add_argument("--include-statuses", default="priority,candidate")
    parser.add_argument("--exclude-symbols", default=None)
    parser.add_argument("--groups", choices=["low", "high", "both"], default="both")
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--min-closed-trades", type=int, default=6)
    parser.add_argument("--top-n-per-batch", type=int, default=10)
    parser.add_argument("--top-n-global", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--leverage-values", default="1,2,3,5,10,20")
    parser.add_argument("--wallet-balance-usd", type=float, default=1000.0)
    parser.add_argument("--output-tag", default="priority_watchlist")
    parser.add_argument("--search-mode", choices=["standard", "exploration", "deep"], default="exploration")
    parser.add_argument("--trigger-reference", choices=["last_price", "mark_price"], default="last_price")
    parser.add_argument("--execution-model", choices=["taker_market", "maker_post_only", "bbo_limit"], default="taker_market")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=int, default=1200)
    parser.add_argument("--run-forever", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    result = run_priority_watchlist_backtest(
        max_symbols=args.max_symbols,
        min_priority_score=args.min_priority_score,
        include_statuses=args.include_statuses,
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
        output_tag=args.output_tag,
        search_mode=args.search_mode,
        trigger_reference=args.trigger_reference,
        execution_model=args.execution_model,
        cycles=None if args.run_forever else args.cycles,
        sleep_seconds=args.sleep_seconds,
        run_forever=args.run_forever,
        plan_only=args.plan_only,
    )
    if args.plan_only:
        print(f"[{result.get('generated_at')}] plan_only symbols={','.join(result.get('symbols') or [])} path={result.get('plan_path')}")
        return
    backtest = result.get("backtest_result") or {}
    best = (backtest.get("top_global") or [{}])[0]
    print(
        f"[{backtest.get('timestamp') or backtest.get('finished_at')}] priority_watchlist symbols={','.join(result.get('symbols') or [])} "
        f"best={best.get('symbol')} {best.get('interval')} roi={best.get('roi_pct_on_paper_balance')} "
        f"wr={best.get('win_rate')} pf={best.get('profit_factor')}"
    )


if __name__ == "__main__":
    main()
