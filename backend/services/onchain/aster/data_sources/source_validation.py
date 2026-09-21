from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.aster_mcp_market_data_adapter import (
    ASTER_FAPI_V3_BASE_URL,
    _fetch_json,
    _parse_symbols,
    _url,
)


OFFICIAL_DOC_URL = "https://asterdex.github.io/aster-api-website/futures-v3/market-data/"
BASE_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_FILE = BASE_DIR / "aster_data_source_validation_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_len(payload: Any) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return len(payload)
    return None


def _has_fields(payload: Any, fields: list[str]) -> bool:
    return isinstance(payload, dict) and all(field in payload for field in fields)


def _list_has_fields(payload: Any, fields: list[str]) -> bool:
    if not isinstance(payload, list) or not payload:
        return False
    first = payload[0]
    return isinstance(first, dict) and all(field in first for field in fields)


def _kline_shape_ok(payload: Any) -> bool:
    return isinstance(payload, list) and bool(payload) and isinstance(payload[0], list) and len(payload[0]) >= 11


def _endpoint_specs(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "name": "ping",
            "path": "/fapi/v3/ping",
            "params": {},
            "doc_status": "official_public",
            "utility": "connectivity_health",
            "validator": lambda payload: isinstance(payload, dict),
        },
        {
            "name": "time",
            "path": "/fapi/v3/time",
            "params": {},
            "doc_status": "official_public",
            "utility": "clock_drift_guard",
            "validator": lambda payload: _has_fields(payload, ["serverTime"]),
        },
        {
            "name": "exchange_info",
            "path": "/fapi/v3/exchangeInfo",
            "params": {},
            "doc_status": "official_public",
            "utility": "symbol_filters_and_execution_rules",
            "validator": lambda payload: isinstance(payload, dict) and isinstance(payload.get("symbols"), list),
        },
        {
            "name": "ticker_24h",
            "path": "/fapi/v3/ticker/24hr",
            "params": {"symbol": symbol},
            "doc_status": "official_public",
            "utility": "volume_liquidity_gate",
            "validator": lambda payload: _has_fields(payload, ["symbol", "lastPrice", "quoteVolume", "count"]),
        },
        {
            "name": "ticker_price",
            "path": "/fapi/v3/ticker/price",
            "params": {"symbol": symbol},
            "doc_status": "official_public",
            "utility": "last_price_reference",
            "validator": lambda payload: _has_fields(payload, ["symbol", "price"]),
        },
        {
            "name": "book_ticker",
            "path": "/fapi/v3/ticker/bookTicker",
            "params": {"symbol": symbol},
            "doc_status": "official_public",
            "utility": "best_bid_ask_spread_guard",
            "validator": lambda payload: _has_fields(payload, ["symbol", "bidPrice", "askPrice"]),
        },
        {
            "name": "depth",
            "path": "/fapi/v3/depth",
            "params": {"symbol": symbol, "limit": 10},
            "doc_status": "official_public",
            "utility": "order_book_depth_guard",
            "validator": lambda payload: isinstance(payload, dict) and isinstance(payload.get("bids"), list) and isinstance(payload.get("asks"), list),
        },
        {
            "name": "recent_trades",
            "path": "/fapi/v3/trades",
            "params": {"symbol": symbol, "limit": min(limit, 1000)},
            "doc_status": "official_public",
            "utility": "order_flow_replay",
            "validator": lambda payload: _list_has_fields(payload, ["id", "price", "qty", "time", "isBuyerMaker"]),
        },
        {
            "name": "aggregate_trades",
            "path": "/fapi/v3/aggTrades",
            "params": {"symbol": symbol, "limit": min(limit, 1000)},
            "doc_status": "official_public",
            "utility": "compressed_order_flow_replay",
            "validator": lambda payload: _list_has_fields(payload, ["a", "p", "q", "T", "m"]),
        },
        {
            "name": "klines",
            "path": "/fapi/v3/klines",
            "params": {"symbol": symbol, "interval": interval, "limit": min(limit, 1500)},
            "doc_status": "official_public",
            "utility": "historical_backtest_bars",
            "validator": _kline_shape_ok,
        },
        {
            "name": "mark_price_klines",
            "path": "/fapi/v3/markPriceKlines",
            "params": {"symbol": symbol, "interval": interval, "limit": min(limit, 1500)},
            "doc_status": "official_public",
            "utility": "liquidation_and_trigger_reference",
            "validator": _kline_shape_ok,
        },
        {
            "name": "index_price_klines",
            "path": "/fapi/v3/indexPriceKlines",
            "params": {"pair": symbol, "interval": interval, "limit": min(limit, 1500)},
            "doc_status": "official_public",
            "utility": "mark_index_divergence_filter",
            "validator": _kline_shape_ok,
        },
        {
            "name": "premium_index",
            "path": "/fapi/v3/premiumIndex",
            "params": {"symbol": symbol},
            "doc_status": "official_public",
            "utility": "live_mark_index_funding_snapshot",
            "validator": lambda payload: _has_fields(payload, ["symbol", "markPrice", "indexPrice", "lastFundingRate"]),
        },
        {
            "name": "funding_rate",
            "path": "/fapi/v3/fundingRate",
            "params": {"symbol": symbol, "limit": min(limit, 1000)},
            "doc_status": "official_public",
            "utility": "funding_cost_history",
            "validator": lambda payload: isinstance(payload, list),
        },
        {
            "name": "funding_info",
            "path": "/fapi/v3/fundingInfo",
            "params": {"symbol": symbol},
            "doc_status": "official_public",
            "utility": "funding_interval_caps",
            "validator": lambda payload: isinstance(payload, (dict, list)),
        },
        {
            "name": "index_references",
            "path": "/fapi/v3/indexreferences",
            "params": {"symbol": symbol},
            "doc_status": "official_public",
            "utility": "index_constituent_quality",
            "validator": lambda payload: isinstance(payload, dict),
        },
    ]


def _sample_fields(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload.keys())[:20]
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            return sorted(str(key) for key in first.keys())[:20]
        if isinstance(first, list):
            return [f"list[{index}]" for index in range(min(len(first), 12))]
    return []


def get_aster_data_source_validation_preview(
    symbols: str | list[str] | None = "LABUSDT,INJUSDT,BTCUSDT",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 3,
    interval: str = "1h",
    sample_limit: int = 20,
    base_url: str | None = None,
) -> dict[str, Any]:
    if not dry_run:
        return {
            "ok": False,
            "status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }

    clean_base = str(base_url or ASTER_FAPI_V3_BASE_URL).rstrip("/")
    safe_timeout = max(1, min(int(timeout_seconds or 8), 15))
    safe_symbols = _parse_symbols(symbols, max(1, min(int(max_symbols or 3), 5)))
    safe_limit = max(1, min(int(sample_limit or 20), 1000))
    clean_interval = str(interval or "1h").strip() or "1h"

    rows: list[dict[str, Any]] = []
    for symbol in safe_symbols:
        for spec in _endpoint_specs(symbol, clean_interval, safe_limit):
            result = _fetch_json(_url(clean_base, spec["path"], spec["params"]), safe_timeout)
            payload = result.get("payload") if result.get("ok") else None
            schema_ok = bool(spec["validator"](payload)) if result.get("ok") else False
            rows.append(
                {
                    "symbol": symbol,
                    "endpoint": spec["name"],
                    "path": spec["path"],
                    "params": spec["params"],
                    "doc_status": spec["doc_status"],
                    "utility": spec["utility"],
                    "fetch_status": result.get("status"),
                    "http_status": result.get("http_status"),
                    "latency_ms": result.get("latency_ms"),
                    "schema_ok": schema_ok,
                    "record_count": _payload_len(payload),
                    "sample_fields": _sample_fields(payload),
                    "rate_limit_headers": result.get("rate_limit_headers") or {},
                    "usable_for_backtest": bool(result.get("ok") and schema_ok),
                    "error": result.get("error") or result.get("error_payload"),
                }
            )

    usable = [row for row in rows if row["usable_for_backtest"]]
    failed = [row for row in rows if not row["usable_for_backtest"]]
    endpoint_health: dict[str, dict[str, Any]] = {}
    for name in sorted({str(row["endpoint"]) for row in rows}):
        subset = [row for row in rows if row["endpoint"] == name]
        ok_count = sum(1 for row in subset if row["usable_for_backtest"])
        endpoint_health[name] = {
            "ok_count": ok_count,
            "total": len(subset),
            "status": "validated" if ok_count == len(subset) else "partial" if ok_count else "failed",
        }

    return {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source_policy": "official_public_rest_validation_only",
        "official_doc_url": OFFICIAL_DOC_URL,
        "base_url": clean_base,
        "symbols": safe_symbols,
        "interval": clean_interval,
        "sample_limit": safe_limit,
        "summary": {
            "endpoint_probes": len(rows),
            "usable_for_backtest": len(usable),
            "failed_or_schema_mismatch": len(failed),
            "validated_endpoint_types": sum(1 for item in endpoint_health.values() if item["status"] == "validated"),
            "partial_endpoint_types": sum(1 for item in endpoint_health.values() if item["status"] == "partial"),
            "failed_endpoint_types": sum(1 for item in endpoint_health.values() if item["status"] == "failed"),
        },
        "endpoint_health": endpoint_health,
        "rows": rows,
        "failed_rows": failed,
        "safety": {
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_trade_endpoint": False,
            "would_store_credentials": False,
        },
        "generated_at": _now(),
    }


def write_aster_data_source_validation_snapshot(
    symbols: str | list[str] | None = "LABUSDT,INJUSDT,BTCUSDT",
    timeout_seconds: int = 8,
    max_symbols: int = 3,
    interval: str = "1h",
    sample_limit: int = 20,
) -> dict[str, Any]:
    payload = get_aster_data_source_validation_preview(
        symbols=symbols,
        dry_run=True,
        timeout_seconds=timeout_seconds,
        max_symbols=max_symbols,
        interval=interval,
        sample_limit=sample_limit,
    )
    SNAPSHOT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return payload
