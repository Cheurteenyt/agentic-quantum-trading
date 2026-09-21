from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.aster_mcp_market_data_adapter import get_aster_perps_reality_check_preview
from services.onchain.aster.backtest_strategy_discovery import run_discovery


CSV_FILE = Path(__file__).with_name("paper_trading_reality_checked_backtest.csv")
JSON_FILE = Path(__file__).with_name("paper_trading_reality_checked_backtest_latest.json")
HEARTBEAT_FILE = Path(__file__).with_name("paper_trading_reality_checked_heartbeat.json")
SCHEMA_VERSION = "aster_reality_checked_backtest_v1"

HEADERS = [
    "schema_version",
    "timestamp",
    "run_id",
    "output_tag",
    "strategy_profile_id",
    "symbol_preset",
    "search_mode",
    "trigger_reference",
    "execution_model",
    "leverage_values",
    "rank",
    "symbol",
    "side",
    "interval",
    "roi_pct_on_paper_balance",
    "win_rate",
    "profit_factor",
    "closed_trades",
    "max_drawdown_usd",
    "best_tradable_leverage",
    "quality_score",
    "quality_verdict",
    "quality_risks",
    "quality_warnings",
    "premium_bps",
    "spread_bps",
    "quote_volume_24h",
    "top10_depth_usd",
    "trigger_protect",
    "market_take_bound",
    "min_notional",
    "price_tick_size",
    "quantity_step_size",
    "market_step_size",
    "order_types",
    "time_in_force",
    "candidate_json",
    "quality_json",
]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(path)


def _safe_tag(value: str | None) -> str:
    tag = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or "").strip().lower())
    return tag or "reality_checked"


def _artifact_paths(output_tag: str | None) -> tuple[Path, Path, Path]:
    tag = _safe_tag(output_tag)
    if tag == "reality_checked":
        return CSV_FILE, JSON_FILE, HEARTBEAT_FILE
    return (
        Path(__file__).with_name(f"paper_trading_reality_checked_backtest_{tag}.csv"),
        Path(__file__).with_name(f"paper_trading_reality_checked_backtest_{tag}_latest.json"),
        Path(__file__).with_name(f"paper_trading_reality_checked_heartbeat_{tag}.json"),
    )


def _ensure_csv(path: Path = CSV_FILE) -> None:
    if path.exists():
        try:
            with path.open("r", newline="", encoding="utf-8") as handle:
                first = next(csv.reader(handle), [])
            if first == HEADERS:
                return
        except (OSError, StopIteration):
            pass
        legacy = path.with_name(f"{path.stem}.legacy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{path.suffix}")
        path.replace(legacy)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(HEADERS)


def _csv_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return "" if value is None else str(value)


def _quality_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("symbol") or "").upper(): row for row in rows if row.get("symbol")}


def _quality_pass(row: dict[str, Any], min_quality_score: int, allowed_verdicts: set[str]) -> bool:
    verdict = str(row.get("verdict") or "")
    try:
        score = int(float(row.get("quality_score") or 0))
    except (TypeError, ValueError):
        score = 0
    return verdict in allowed_verdicts and score >= min_quality_score


def _row(
    timestamp: str,
    run_id: str,
    output_tag: str,
    run_strategy_profile_id: str,
    rank: int,
    candidate: dict[str, Any],
    quality: dict[str, Any],
    search_mode: str,
    trigger_reference: str,
    execution_model: str,
    symbol_preset: str,
    leverage_values: str,
) -> dict[str, Any]:
    metrics = quality.get("key_metrics") or {}
    candidate_trigger_reference = str(candidate.get("trigger_reference") or candidate.get("assumed_trigger_reference") or trigger_reference)
    candidate_execution_model = str(candidate.get("execution_model") or candidate.get("assumed_execution_model") or execution_model)
    candidate_strategy_profile_id = str(candidate.get("strategy_profile_id") or "").strip()
    if not candidate_strategy_profile_id:
        candidate_strategy_profile_id = "|".join(
            [
                output_tag,
                symbol_preset,
                search_mode,
                candidate_trigger_reference,
                candidate_execution_model,
                str(candidate.get("best_tradable_leverage") or ""),
                str(candidate.get("strategy_profile_key") or ""),
                str(candidate.get("symbol") or "").upper(),
                str(candidate.get("interval") or ""),
                str(candidate.get("side") or "long"),
            ]
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": timestamp,
        "run_id": run_id,
        "output_tag": output_tag,
        "strategy_profile_id": candidate_strategy_profile_id,
        "symbol_preset": symbol_preset,
        "search_mode": search_mode,
        "trigger_reference": candidate_trigger_reference,
        "execution_model": candidate_execution_model,
        "leverage_values": leverage_values,
        "rank": rank,
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "interval": candidate.get("interval"),
        "roi_pct_on_paper_balance": candidate.get("roi_pct_on_paper_balance"),
        "win_rate": candidate.get("win_rate"),
        "profit_factor": candidate.get("profit_factor"),
        "closed_trades": candidate.get("closed_trades"),
        "max_drawdown_usd": candidate.get("max_drawdown_usd"),
        "best_tradable_leverage": candidate.get("best_tradable_leverage"),
        "quality_score": quality.get("quality_score"),
        "quality_verdict": quality.get("verdict"),
        "quality_risks": ",".join(quality.get("risks") or []),
        "quality_warnings": ",".join(quality.get("warnings") or []),
        "premium_bps": metrics.get("premium_bps"),
        "spread_bps": metrics.get("spread_bps"),
        "quote_volume_24h": metrics.get("quote_volume_24h"),
        "top10_depth_usd": metrics.get("top10_depth_usd"),
        "trigger_protect": metrics.get("trigger_protect"),
        "market_take_bound": metrics.get("market_take_bound"),
        "min_notional": metrics.get("min_notional"),
        "price_tick_size": metrics.get("price_tick_size"),
        "quantity_step_size": metrics.get("quantity_step_size"),
        "market_step_size": metrics.get("market_step_size"),
        "order_types": metrics.get("order_types"),
        "time_in_force": metrics.get("time_in_force"),
        "candidate_json": candidate,
        "quality_json": quality,
    }


def _write_rows(rows: list[dict[str, Any]], path: Path = CSV_FILE) -> None:
    _ensure_csv(path)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([_csv_value(row.get(key)) for key in HEADERS])


def run_reality_checked_backtest(
    symbols: str | None = None,
    groups: str = "both",
    lookback_days: int = 60,
    windows: int = 3,
    min_closed_trades: int = 8,
    top_n_per_batch: int = 10,
    top_n_global: int = 30,
    batch_size: int = 5,
    leverage_values: str | None = "1,2,3,5,10,20",
    wallet_balance_usd: float = 1_000.0,
    symbol_preset: str = "core",
    output_tag: str = "reality_checked",
    search_mode: str = "standard",
    trigger_reference: str = "last_price",
    execution_model: str = "taker_market",
    min_quality_score: int = 75,
    allowed_quality_verdicts: str = "backtest_quality_ok",
    kline_interval: str = "1h",
    kline_limit: int = 50,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    csv_path, json_path, heartbeat_path = _artifact_paths(output_tag)
    discovery = run_discovery(
        symbols=symbols,
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
        output_tag=f"{output_tag}_raw",
        search_mode=search_mode,
        trigger_reference=trigger_reference,
        execution_model=execution_model,
    )
    discovered = list(dict.fromkeys(str(row.get("symbol") or "").upper() for row in discovery.get("top_global") or [] if row.get("symbol")))
    discovered_symbols = ",".join(discovered)
    reality = get_aster_perps_reality_check_preview(
        symbols=discovered_symbols or symbols,
        dry_run=True,
        timeout_seconds=8,
        max_symbols=min(max(1, len(discovered)), 10),
        kline_interval=kline_interval,
        kline_limit=kline_limit,
        funding_limit=20,
        depth_limit=50,
    )
    quality_by_symbol = _quality_map(reality.get("rows") or [])
    allowed = {item.strip() for item in str(allowed_quality_verdicts or "backtest_quality_ok").split(",") if item.strip()}
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate in discovery.get("top_global") or []:
        symbol = str(candidate.get("symbol") or "").upper()
        quality = quality_by_symbol.get(symbol)
        if not quality:
            rejected.append({"symbol": symbol, "reason": "missing_reality_check", "candidate": candidate})
            continue
        if _quality_pass(quality, min_quality_score, allowed):
            candidates.append({**candidate, "reality_check": quality})
        else:
            rejected.append({"symbol": symbol, "reason": "quality_filter_failed", "candidate": candidate, "reality_check": quality})

    run_strategy_profile_id = f"{output_tag}|{symbol_preset}|{search_mode}|{trigger_reference}|{execution_model}|{leverage_values}"
    run_id = f"reality-checked-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    rows = [
        _row(
            timestamp,
            run_id,
            output_tag,
            run_strategy_profile_id,
            index + 1,
            candidate,
            candidate["reality_check"],
            search_mode,
            trigger_reference,
            execution_model,
            symbol_preset,
            leverage_values,
        )
        for index, candidate in enumerate(candidates)
    ]
    _write_rows(rows, csv_path)
    payload = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "timestamp": timestamp,
        "run_id": run_id,
        "output_tag": output_tag,
        "run_strategy_profile_id": run_strategy_profile_id,
        "methodology": "run_standard_discovery_then_filter_with_public_aster_perps_reality_check",
        "filters": {
            "min_quality_score": min_quality_score,
            "allowed_quality_verdicts": sorted(allowed),
        },
        "discovery_summary": {
            "raw_total_candidates": discovery.get("total_candidates"),
            "raw_top_count": len(discovery.get("top_global") or []),
            "symbols_reality_checked": reality.get("symbols_checked"),
            "reality_summary": reality.get("summary"),
            "symbol_preset": symbol_preset,
            "search_mode": search_mode,
            "trigger_reference": trigger_reference,
            "execution_model": execution_model,
            "leverage_values": leverage_values,
        },
        "accepted_count": len(candidates),
        "rejected_count": len(rejected),
        "accepted_candidates": candidates,
        "rejected_candidates": rejected[:50],
        "best": candidates[0] if candidates else None,
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "heartbeat_path": str(heartbeat_path),
        "raw_discovery_json_path": discovery.get("tagged_json_path"),
        "would_write_db": False,
        "would_trade": False,
    }
    _write_json_atomic(json_path, payload)
    _write_json_atomic(
        heartbeat_path,
        {
            "ok": True,
            "last_run_at": timestamp,
            "run_id": run_id,
            "run_strategy_profile_id": run_strategy_profile_id,
            "accepted_count": len(candidates),
            "rejected_count": len(rejected),
            "best": {
                "symbol": (payload.get("best") or {}).get("symbol") if payload.get("best") else None,
                "interval": (payload.get("best") or {}).get("interval") if payload.get("best") else None,
                "roi_pct_on_paper_balance": (payload.get("best") or {}).get("roi_pct_on_paper_balance") if payload.get("best") else None,
                "quality_score": ((payload.get("best") or {}).get("reality_check") or {}).get("quality_score") if payload.get("best") else None,
            },
            "csv_path": str(csv_path),
            "json_path": str(json_path),
        },
    )
    payload["csv_path"] = str(csv_path)
    payload["json_path"] = str(json_path)
    payload["heartbeat_path"] = str(heartbeat_path)
    return payload


def run_rotation(
    cycles: int | None,
    sleep_seconds: int,
    **kwargs: Any,
) -> dict[str, Any]:
    safe_cycles = None if cycles is None else max(1, min(int(cycles or 1), 288))
    safe_sleep = max(60, int(sleep_seconds or 900))
    reports: list[dict[str, Any]] = []
    index = 0
    while safe_cycles is None or index < safe_cycles:
        payload = run_reality_checked_backtest(**kwargs)
        reports.append(
            {
                "cycle": index + 1,
                "timestamp": payload.get("timestamp"),
                "accepted_count": payload.get("accepted_count"),
                "rejected_count": payload.get("rejected_count"),
                "best": payload.get("best"),
            }
        )
        best = payload.get("best") or {}
        print(
            f"[{payload['timestamp']}] cycle={index + 1}/{safe_cycles if safe_cycles is not None else 'forever'} "
            f"accepted={payload.get('accepted_count')} rejected={payload.get('rejected_count')} "
            f"best={best.get('symbol')} {best.get('interval')} roi={best.get('roi_pct_on_paper_balance')} "
            f"quality={(best.get('reality_check') or {}).get('quality_score')}",
            flush=True,
        )
        index += 1
        if safe_cycles is None or index < safe_cycles:
            time.sleep(safe_sleep)
    return {"ok": True, "cycles": safe_cycles if safe_cycles is not None else "forever", "reports": reports}


def main() -> None:
    parser = argparse.ArgumentParser(description="Discovery Aster filtre par reality check perps public V3.")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--symbol-preset", default="core")
    parser.add_argument("--output-tag", default="reality_checked")
    parser.add_argument("--trigger-reference", choices=["last_price", "mark_price"], default="last_price")
    parser.add_argument("--execution-model", choices=["taker_market", "maker_post_only", "bbo_limit"], default="taker_market")
    parser.add_argument("--groups", choices=["low", "high", "both"], default="both")
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--min-closed-trades", type=int, default=8)
    parser.add_argument("--top-n-per-batch", type=int, default=10)
    parser.add_argument("--top-n-global", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--leverage-values", default="1,2,3,5,10,20")
    parser.add_argument("--wallet-balance-usd", type=float, default=1000.0)
    parser.add_argument("--search-mode", choices=["standard", "exploration", "deep"], default="standard")
    parser.add_argument("--min-quality-score", type=int, default=75)
    parser.add_argument("--allowed-quality-verdicts", default="backtest_quality_ok")
    parser.add_argument("--kline-interval", default="1h")
    parser.add_argument("--kline-limit", type=int, default=50)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=int, default=900)
    parser.add_argument("--run-forever", action="store_true")
    args = parser.parse_args()

    kwargs = {
        "symbols": args.symbols,
        "groups": args.groups,
        "lookback_days": args.lookback_days,
        "windows": args.windows,
        "min_closed_trades": args.min_closed_trades,
        "top_n_per_batch": args.top_n_per_batch,
        "top_n_global": args.top_n_global,
        "batch_size": args.batch_size,
        "leverage_values": args.leverage_values,
        "wallet_balance_usd": args.wallet_balance_usd,
        "symbol_preset": args.symbol_preset,
        "output_tag": args.output_tag,
        "search_mode": args.search_mode,
        "trigger_reference": args.trigger_reference,
        "execution_model": args.execution_model,
        "min_quality_score": args.min_quality_score,
        "allowed_quality_verdicts": args.allowed_quality_verdicts,
        "kline_interval": args.kline_interval,
        "kline_limit": args.kline_limit,
    }
    if args.run_forever or args.cycles > 1:
        run_rotation(cycles=None if args.run_forever else args.cycles, sleep_seconds=args.sleep_seconds, **kwargs)
        return
    payload = run_reality_checked_backtest(**kwargs)
    best = payload.get("best") or {}
    print(
        f"[{payload['timestamp']}] accepted={payload.get('accepted_count')} rejected={payload.get('rejected_count')} "
        f"best={best.get('symbol')} {best.get('interval')} roi={best.get('roi_pct_on_paper_balance')} "
        f"quality={(best.get('reality_check') or {}).get('quality_score')}"
    )
    print(f"csv={payload.get('csv_path')}")
    print(f"json={payload.get('json_path')}")


if __name__ == "__main__":
    main()
