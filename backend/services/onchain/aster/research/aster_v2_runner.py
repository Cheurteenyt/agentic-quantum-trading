from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.backtest_strategy_discovery import (
    ASTER_COMMODITY_SYMBOLS,
    ASTER_EQUITY_SYMBOLS,
    run_discovery,
    run_rotation,
)


BASE_DIR = Path(__file__).resolve().parents[1]
CHAMPIONS_FILE = BASE_DIR / "aster_exploitation_champions_latest.json"
WATCHLIST_PLAN_FILE = BASE_DIR / "aster_priority_watchlist_backtest_plan_latest.json"
UNIVERSE_FILE = BASE_DIR / "aster_public_universe_snapshot_latest.json"
WS_QUALITY_FILE = BASE_DIR / "aster_ws_symbol_quality_report_latest.json"
PLAN_FILE = BASE_DIR / "aster_v2_runner_plan_latest.json"

DEFAULT_REVIEW_DECISIONS = {"needs_reality_check"}
DEFAULT_EXPLOIT_DECISIONS = {"keep_testing", "promote_to_forward_candidate"}
STATIC_MACRO_EQUITY_SYMBOLS = [*ASTER_COMMODITY_SYMBOLS, *ASTER_EQUITY_SYMBOLS]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_tag(value: str | None) -> str:
    tag = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or "").strip().lower())
    return tag or "aster_v2"


def _plan_file_for_tag(output_tag: str | None) -> Path:
    tag = _safe_tag(output_tag)
    if tag == "aster_v2":
        return PLAN_FILE
    return BASE_DIR / f"aster_v2_runner_plan_{tag}_latest.json"


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


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys([item for item in items if item]))


def _rank_symbols_by_universe(
    symbols: list[str],
    universe: dict[str, dict[str, Any]],
    excluded: set[str],
    used: set[str],
) -> list[str]:
    clean = _dedupe([str(symbol or "").upper() for symbol in symbols])

    def score(symbol: str) -> tuple[int, float, float, float]:
        row = universe.get(symbol) or {}
        flags = set(row.get("data_flags") or [])
        tradable = 1 if row.get("status") == "TRADING" else 0
        clean_market = 1 if "wide_spread" not in flags else 0
        volume = _float(row.get("quote_volume_24h"))
        spread = _float(row.get("spread_bps"), 999999.0)
        return (tradable, clean_market, volume, -spread)

    return [
        symbol
        for symbol in sorted(clean, key=score, reverse=True)
        if symbol and symbol not in excluded and symbol not in used
    ]


def _top_universe_crypto_symbols(
    universe: dict[str, dict[str, Any]],
    excluded: set[str],
    used: set[str],
    limit: int = 30,
) -> list[str]:
    macro_equity = set(STATIC_MACRO_EQUITY_SYMBOLS)
    rows = [
        row
        for row in universe.values()
        if str(row.get("symbol") or "").upper()
        and str(row.get("symbol") or "").upper() not in macro_equity
        and str(row.get("quote_asset") or "").upper() in {"USDT", "USD1"}
    ]
    ranked = sorted(
        rows,
        key=lambda row: (
            1 if row.get("status") == "TRADING" else 0,
            0 if "wide_spread" in set(row.get("data_flags") or []) else 1,
            _float(row.get("quote_volume_24h")),
            abs(_float(row.get("price_change_pct_24h"))),
        ),
        reverse=True,
    )
    return _rank_symbols_by_universe(
        [str(row.get("symbol") or "").upper() for row in ranked[: max(10, limit * 3)]],
        universe,
        excluded,
        used,
    )[:limit]


def _diversified_exploration_symbols(
    max_exploration: int,
    excluded: set[str],
    used: set[str],
) -> tuple[list[str], dict[str, list[str]]]:
    universe = _universe_map()
    cap = max(0, min(int(max_exploration or 0), 60))
    buckets = {
        "priority_watchlist": _rank_symbols_by_universe(_watchlist_symbols(), universe, excluded, used),
        "crypto_universe": _top_universe_crypto_symbols(universe, excluded, used),
        "commodities": _rank_symbols_by_universe(ASTER_COMMODITY_SYMBOLS, universe, excluded, used),
        "equities": _rank_symbols_by_universe(ASTER_EQUITY_SYMBOLS, universe, excluded, used),
    }
    selected: list[str] = []
    while len(selected) < cap:
        progressed = False
        for bucket_symbols in buckets.values():
            while bucket_symbols and bucket_symbols[0] in {*used, *selected}:
                bucket_symbols.pop(0)
            if bucket_symbols and len(selected) < cap:
                selected.append(bucket_symbols.pop(0))
                progressed = True
        if not progressed:
            break
    selected_set = set(selected)
    selected_buckets = {
        name: [symbol for symbol in original if symbol in selected_set]
        for name, original in {
            "priority_watchlist": _watchlist_symbols(),
            "crypto_universe": _top_universe_crypto_symbols(universe, excluded, used, limit=cap),
            "commodities": ASTER_COMMODITY_SYMBOLS,
            "equities": ASTER_EQUITY_SYMBOLS,
        }.items()
    }
    return _dedupe(selected), selected_buckets


def _champion_rows() -> list[dict[str, Any]]:
    return list(_load_json(CHAMPIONS_FILE).get("rows") or [])


def _watchlist_symbols() -> list[str]:
    payload = _load_json(WATCHLIST_PLAN_FILE)
    return [str(item or "").upper() for item in payload.get("symbols") or [] if item]


def _universe_map() -> dict[str, dict[str, Any]]:
    payload = _load_json(UNIVERSE_FILE)
    rows: list[dict[str, Any]] = []
    for section in ("all_research_universe", "all_rows", "top_clean_research_universe", "top_by_quote_volume", "top_by_abs_price_change", "top_by_funding_abs", "rows_sample"):
        rows.extend([row for row in payload.get(section) or [] if isinstance(row, dict)])
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        existing = best.get(symbol, {})
        best[symbol] = {**existing, **row}
    return best


def _ws_map() -> dict[str, dict[str, Any]]:
    payload = _load_json(WS_QUALITY_FILE)
    return {
        str(row.get("symbol") or "").upper(): row
        for row in payload.get("rows") or []
        if isinstance(row, dict) and row.get("symbol")
    }


def _preflight_symbol(symbol: str, universe: dict[str, Any] | None, ws: dict[str, Any] | None, lane: str) -> dict[str, Any]:
    flags = list((universe or {}).get("data_flags") or [])
    status = "backtest_ready"
    blockers: list[str] = []
    warnings: list[str] = []
    if not universe:
        if lane in {"exploitation", "review"}:
            status = "needs_universe_refresh"
            warnings.append("missing_from_public_universe_snapshot_but_has_champion_validation")
        else:
            status = "blocked_data_quality"
            blockers.append("missing_from_public_universe_snapshot")
    else:
        if universe.get("status") != "TRADING":
            blockers.append("not_trading")
        if "wide_spread" in flags:
            blockers.append("wide_spread")
        if "low_24h_quote_volume" in flags:
            warnings.append("low_24h_quote_volume")
        if "large_mark_index_premium" in flags:
            warnings.append("large_mark_index_premium")
    ws_verdict = str((ws or {}).get("ws_quality_verdict") or "not_checked")
    if ws_verdict == "ws_forward_risky":
        warnings.append("ws_forward_risky")
        if status == "backtest_ready":
            status = "needs_ws_validation"
    elif ws_verdict == "not_checked":
        warnings.append("ws_not_checked")
        if status == "backtest_ready":
            status = "needs_ws_validation"
    if blockers:
        status = "blocked_data_quality"
    return {
        "symbol": symbol,
        "lane": lane,
        "preflight_status": status,
        "blockers": blockers,
        "warnings": warnings,
        "quote_volume_24h": (universe or {}).get("quote_volume_24h"),
        "spread_bps": (universe or {}).get("spread_bps"),
        "price_change_pct_24h": (universe or {}).get("price_change_pct_24h"),
        "universe_flags": flags,
        "ws_quality_score": (ws or {}).get("ws_quality_score"),
        "ws_quality_verdict": ws_verdict,
    }


def _build_symbol_plan(
    max_exploitation: int,
    max_review: int,
    max_exploration: int,
    include_review: bool,
    include_exploration: bool,
    exclude_symbols: str | list[str] | None,
) -> dict[str, Any]:
    excluded = _parse_symbols(exclude_symbols)
    champions = sorted(_champion_rows(), key=lambda row: _float(row.get("validation_score")), reverse=True)
    exploitation = [
        row
        for row in champions
        if str(row.get("champion_decision") or "") in DEFAULT_EXPLOIT_DECISIONS
        and str(row.get("symbol") or "").upper() not in excluded
    ][: max(0, min(int(max_exploitation or 5), 20))]
    review = [
        row
        for row in champions
        if include_review
        and str(row.get("champion_decision") or "") in DEFAULT_REVIEW_DECISIONS
        and str(row.get("symbol") or "").upper() not in excluded
    ][: max(0, min(int(max_review or 2), 10))]
    exploration_symbols: list[str] = []
    exploration_buckets: dict[str, list[str]] = {}
    if include_exploration:
        used = {str(row.get("symbol") or "").upper() for row in [*exploitation, *review]}
        exploration_symbols, exploration_buckets = _diversified_exploration_symbols(
            max_exploration=max_exploration,
            excluded=excluded,
            used=used,
        )

    exploitation_symbols = [str(row.get("symbol") or "").upper() for row in exploitation]
    review_symbols = [str(row.get("symbol") or "").upper() for row in review]
    all_symbols = _dedupe([*exploitation_symbols, *review_symbols, *exploration_symbols])
    return {
        "exploitation_symbols": exploitation_symbols,
        "review_symbols": review_symbols,
        "exploration_symbols": exploration_symbols,
        "all_symbols": all_symbols,
        "champion_rows_used": exploitation + review,
        "excluded_symbols": sorted(excluded),
        "exploration_buckets": exploration_buckets,
    }


def build_aster_v2_runner_plan(
    max_exploitation: int = 5,
    max_review: int = 2,
    max_exploration: int = 16,
    include_review: bool = True,
    include_exploration: bool = True,
    exclude_symbols: str | list[str] | None = None,
    require_preflight_ready: bool = False,
    output_tag: str = "aster_v2",
    write_snapshot: bool = True,
) -> dict[str, Any]:
    symbol_plan = _build_symbol_plan(
        max_exploitation=max_exploitation,
        max_review=max_review,
        max_exploration=max_exploration,
        include_review=include_review,
        include_exploration=include_exploration,
        exclude_symbols=exclude_symbols,
    )
    universe = _universe_map()
    ws_quality = _ws_map()
    lane_by_symbol: dict[str, str] = {}
    for symbol in symbol_plan["exploitation_symbols"]:
        lane_by_symbol[symbol] = "exploitation"
    for symbol in symbol_plan["review_symbols"]:
        lane_by_symbol[symbol] = "review"
    for symbol in symbol_plan["exploration_symbols"]:
        lane_by_symbol[symbol] = "exploration"
    preflight_rows = [
        _preflight_symbol(symbol, universe.get(symbol), ws_quality.get(symbol), lane_by_symbol.get(symbol, "unknown"))
        for symbol in symbol_plan["all_symbols"]
    ]
    preflight_by_symbol = {row["symbol"]: row for row in preflight_rows}
    blocked_symbols = [row["symbol"] for row in preflight_rows if row["preflight_status"] == "blocked_data_quality"]
    needs_ws_symbols = [row["symbol"] for row in preflight_rows if row["preflight_status"] == "needs_ws_validation"]
    needs_universe_refresh_symbols = [row["symbol"] for row in preflight_rows if row["preflight_status"] == "needs_universe_refresh"]
    ready_symbols = [row["symbol"] for row in preflight_rows if row["preflight_status"] == "backtest_ready"]
    if require_preflight_ready:
        runnable_symbols = ready_symbols
    else:
        runnable_symbols = [symbol for symbol in symbol_plan["all_symbols"] if symbol not in set(blocked_symbols)]
    payload = {
        "ok": bool(runnable_symbols),
        "status": "ready" if runnable_symbols else "blocked_no_runnable_symbols",
        "source_policy": "local_aster_v2_orchestrator_plan",
        "generated_at": _now(),
        "inputs": {
            "champions_validation": str(CHAMPIONS_FILE),
            "priority_watchlist_plan": str(WATCHLIST_PLAN_FILE),
            "public_universe_snapshot": str(UNIVERSE_FILE),
            "ws_quality_snapshot": str(WS_QUALITY_FILE),
            "max_exploitation": max_exploitation,
            "max_review": max_review,
            "max_exploration": max_exploration,
            "include_review": include_review,
            "include_exploration": include_exploration,
            "exclude_symbols": symbol_plan["excluded_symbols"],
            "require_preflight_ready": require_preflight_ready,
        },
        "lanes": {
            "exploitation": symbol_plan["exploitation_symbols"],
            "review": symbol_plan["review_symbols"],
            "exploration": symbol_plan["exploration_symbols"],
            "exploration_buckets": symbol_plan["exploration_buckets"],
        },
        "preflight_summary": {
            "backtest_ready": len(ready_symbols),
            "needs_ws_validation": len(needs_ws_symbols),
            "needs_universe_refresh": len(needs_universe_refresh_symbols),
            "blocked_data_quality": len(blocked_symbols),
            "runnable_symbols": len(runnable_symbols),
        },
        "preflight_rows": preflight_rows,
        "symbols": runnable_symbols,
        "symbols_csv": ",".join(runnable_symbols),
        "blocked_symbols": blocked_symbols,
        "needs_ws_validation_symbols": needs_ws_symbols,
        "needs_universe_refresh_symbols": needs_universe_refresh_symbols,
        "backtest_ready_symbols": ready_symbols,
        "lane_preflight": {
            lane: [preflight_by_symbol.get(symbol) for symbol in symbols if preflight_by_symbol.get(symbol)]
            for lane, symbols in symbol_plan.items()
            if lane in {"exploitation_symbols", "review_symbols", "exploration_symbols"}
        },
        "champion_rows_used": symbol_plan["champion_rows_used"],
        "recommended_output_tag": output_tag,
        "runner": {
            "delegates_to": "services.onchain.aster.backtest_strategy_discovery",
            "purpose": "single v2 runner combining validated champions and filtered exploration symbols",
        },
        "safety": {
            "would_write_db": False,
            "would_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_signed_endpoint": False,
            "writes_performed": 0,
        },
    }
    if write_snapshot:
        plan_file = _plan_file_for_tag(output_tag)
        plan_file.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["plan_path"] = str(plan_file)
        payload["safety"]["writes_performed"] = 1
    return payload


def run_aster_v2_runner(
    plan_only: bool = False,
    max_exploitation: int = 5,
    max_review: int = 2,
    max_exploration: int = 16,
    include_review: bool = True,
    include_exploration: bool = True,
    exclude_symbols: str | list[str] | None = None,
    require_preflight_ready: bool = False,
    groups: str = "both",
    lookback_days: int = 60,
    windows: int = 3,
    min_closed_trades: int = 6,
    top_n_per_batch: int = 10,
    top_n_global: int = 80,
    batch_size: int = 3,
    leverage_values: str | None = "1,2,3,5,10,20",
    wallet_balance_usd: float = 1_000.0,
    output_tag: str = "aster_v2",
    search_mode: str = "exploration",
    trigger_reference: str = "last_price",
    execution_model: str = "taker_market",
    auto_ws_preflight: bool = False,
    ws_preflight_max_symbols: int = 10,
    ws_preflight_batch_size: int = 5,
    cycles: int | None = 1,
    sleep_seconds: int = 1200,
    run_forever: bool = False,
) -> dict[str, Any]:
    plan = build_aster_v2_runner_plan(
        max_exploitation=max_exploitation,
        max_review=max_review,
        max_exploration=max_exploration,
        include_review=include_review,
        include_exploration=include_exploration,
        exclude_symbols=exclude_symbols,
        require_preflight_ready=require_preflight_ready,
        output_tag=output_tag,
        write_snapshot=True,
    )
    ws_preflight_refresh = None
    if auto_ws_preflight:
        from services.onchain.aster.research.aster_v2_ws_preflight_refresh import (
            get_aster_v2_ws_preflight_refresh_preview,
        )

        ws_preflight_refresh = get_aster_v2_ws_preflight_refresh_preview(
            selection_mode="needs_ws_validation",
            max_symbols=ws_preflight_max_symbols,
            batch_size=ws_preflight_batch_size,
            timeout_seconds=8,
            interval="1m",
            rate_limit_delay_ms=300,
            write_snapshot=True,
            regenerate_v2_plan=True,
        )
        plan = build_aster_v2_runner_plan(
            max_exploitation=max_exploitation,
            max_review=max_review,
            max_exploration=max_exploration,
            include_review=include_review,
            include_exploration=include_exploration,
            exclude_symbols=exclude_symbols,
            require_preflight_ready=require_preflight_ready,
            output_tag=output_tag,
            write_snapshot=True,
        )
    if plan_only or not plan.get("symbols_csv"):
        return {
            **plan,
            "plan_only": bool(plan_only),
            "would_run_backtest": bool(plan.get("symbols_csv")),
            "ws_preflight_refresh": ws_preflight_refresh,
        }
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
        "symbol_preset": "aster_v2",
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
        "ws_preflight_refresh": ws_preflight_refresh,
        "backtest_result": result,
        "symbols": plan["symbols"],
        "output_tag": output_tag,
        "would_write_db": False,
        "would_trade": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aster v2 runner: validated champions + priority watchlist exploration.")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--max-exploitation", type=int, default=5)
    parser.add_argument("--max-review", type=int, default=2)
    parser.add_argument("--max-exploration", type=int, default=16)
    parser.add_argument("--no-review", action="store_true")
    parser.add_argument("--no-exploration", action="store_true")
    parser.add_argument("--exclude-symbols", default=None)
    parser.add_argument("--require-preflight-ready", action="store_true", help="Only run symbols already marked backtest_ready by universe/WS preflight.")
    parser.add_argument("--groups", choices=["low", "high", "both"], default="both")
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--min-closed-trades", type=int, default=6)
    parser.add_argument("--top-n-per-batch", type=int, default=10)
    parser.add_argument("--top-n-global", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--leverage-values", default="1,2,3,5,10,20")
    parser.add_argument("--wallet-balance-usd", type=float, default=1000.0)
    parser.add_argument("--output-tag", default="aster_v2")
    parser.add_argument("--search-mode", choices=["standard", "exploration", "deep"], default="exploration")
    parser.add_argument("--trigger-reference", choices=["last_price", "mark_price"], default="last_price")
    parser.add_argument("--execution-model", choices=["taker_market", "maker_post_only", "bbo_limit"], default="taker_market")
    parser.add_argument("--auto-ws-preflight", action="store_true", help="Refresh missing WS quality rows before rebuilding the v2 symbol plan.")
    parser.add_argument("--ws-preflight-max-symbols", type=int, default=10)
    parser.add_argument("--ws-preflight-batch-size", type=int, default=5)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=int, default=1200)
    parser.add_argument("--run-forever", action="store_true")
    args = parser.parse_args()

    result = run_aster_v2_runner(
        plan_only=args.plan_only,
        max_exploitation=args.max_exploitation,
        max_review=args.max_review,
        max_exploration=args.max_exploration,
        include_review=not args.no_review,
        include_exploration=not args.no_exploration,
        exclude_symbols=args.exclude_symbols,
        require_preflight_ready=args.require_preflight_ready,
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
        auto_ws_preflight=args.auto_ws_preflight,
        ws_preflight_max_symbols=args.ws_preflight_max_symbols,
        ws_preflight_batch_size=args.ws_preflight_batch_size,
        cycles=None if args.run_forever else args.cycles,
        sleep_seconds=args.sleep_seconds,
        run_forever=args.run_forever,
    )
    if args.plan_only:
        plan = result.get("plan") or result
        lanes = plan.get("lanes") or {}
        print(
            f"[{plan.get('generated_at')}] symbols={','.join(plan.get('symbols') or [])} "
            f"exploitation={','.join(lanes.get('exploitation') or [])} "
            f"review={','.join(lanes.get('review') or [])} exploration={','.join(lanes.get('exploration') or [])} "
            f"preflight={plan.get('preflight_summary')}"
        )
        return
    backtest = result.get("backtest_result") or {}
    best = (backtest.get("top_global") or [{}])[0]
    print(
        f"[{backtest.get('timestamp') or backtest.get('finished_at')}] aster_v2 symbols={','.join(result.get('symbols') or [])} "
        f"best={best.get('symbol')} {best.get('interval')} roi={best.get('roi_pct_on_paper_balance')} "
        f"wr={best.get('win_rate')} pf={best.get('profit_factor')}"
    )


if __name__ == "__main__":
    main()
