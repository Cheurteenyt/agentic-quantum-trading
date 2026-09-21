from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


ASTER_FAPI_V3_BASE_URL = "https://fapi.asterdex.com"
USER_AGENT = "CoreEquityAsterMcpReadOnlyAdapter/0.1"

READ_ONLY_TOOLS = {
    "ping",
    "get_server_info",
    "get_exchange_info",
    "get_ticker",
    "get_order_book",
    "get_klines",
    "get_funding_rate",
    "get_funding_info",
    "get_leverage_bracket",
    "get_commission_rate",
    "get_balance",
    "get_positions",
    "get_account_info",
    "get_account_v4",
}

BLOCKED_TOOLS = {
    "create_order",
    "create_spot_order",
    "cancel_order",
    "cancel_all_orders",
    "set_leverage",
    "set_margin_mode",
    "transfer_funds",
    "transfer_spot_futures",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _clean_symbol(value: Any) -> str:
    clean = "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())
    return clean[:32]


def _parse_symbols(value: Any, limit: int) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw = [str(item or "") for item in value]
    else:
        raw = str(value or "BTCUSDT").replace(";", ",").split(",")
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        symbol = _clean_symbol(item)
        if symbol and symbol not in seen:
            out.append(symbol)
            seen.add(symbol)
        if len(out) >= limit:
            break
    return out or ["BTCUSDT"]


def _fetch_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            headers = {
                key: response.headers.get(key)
                for key in (
                    "x-mbx-used-weight-1m",
                    "x-mbx-used-weight",
                    "retry-after",
                )
                if response.headers.get(key) is not None
            }
            return {
                "ok": True,
                "status": "ok",
                "http_status": int(response.status),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "payload": json.loads(raw.decode("utf-8")) if raw else None,
                "rate_limit_headers": headers,
            }
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:500]
        except Exception:
            body = ""
        status = {
            403: "blocked_by_waf",
            418: "ip_auto_banned",
            429: "rate_limited",
            404: "not_found",
            503: "execution_status_unknown",
        }.get(int(exc.code), "http_error")
        return {
            "ok": False,
            "status": status,
            "http_status": int(exc.code),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "retry_after": exc.headers.get("retry-after"),
            "error_payload": body or None,
            "rate_limit_headers": {
                key: exc.headers.get(key)
                for key in ("x-mbx-used-weight-1m", "x-mbx-used-weight", "retry-after")
                if exc.headers.get(key) is not None
            },
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "request_failed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": type(exc).__name__,
        }


def _url(base: str, path: str, params: dict[str, Any] | None = None) -> str:
    clean_base = str(base or ASTER_FAPI_V3_BASE_URL).rstrip("/")
    if not params:
        return f"{clean_base}{path}"
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return f"{clean_base}{path}?{query}"


def _symbol_exchange_info(exchange_info: Any, symbol: str) -> dict[str, Any]:
    symbols = (exchange_info or {}).get("symbols") if isinstance(exchange_info, dict) else []
    row = next((item for item in symbols or [] if str(item.get("symbol", "")).upper() == symbol), None)
    if not row:
        return {"symbol": symbol, "status": "not_found_in_exchange_info"}
    filters = {item.get("filterType"): item for item in row.get("filters") or [] if isinstance(item, dict)}
    order_types = row.get("orderTypes") or row.get("orderType") or []
    time_in_force = row.get("timeInForce") or []
    return {
        "symbol": symbol,
        "status": row.get("status"),
        "contract_type": row.get("contractType"),
        "base_asset": row.get("baseAsset"),
        "quote_asset": row.get("quoteAsset"),
        "margin_asset": row.get("marginAsset"),
        "trigger_protect": row.get("triggerProtect"),
        "order_types": ",".join(str(item) for item in order_types) if isinstance(order_types, list) else str(order_types or ""),
        "time_in_force": ",".join(str(item) for item in time_in_force) if isinstance(time_in_force, list) else str(time_in_force or ""),
        "price_min": (filters.get("PRICE_FILTER") or {}).get("minPrice"),
        "price_max": (filters.get("PRICE_FILTER") or {}).get("maxPrice"),
        "price_tick_size": (filters.get("PRICE_FILTER") or {}).get("tickSize"),
        "lot_min_qty": (filters.get("LOT_SIZE") or {}).get("minQty"),
        "lot_max_qty": (filters.get("LOT_SIZE") or {}).get("maxQty"),
        "quantity_step_size": (filters.get("LOT_SIZE") or {}).get("stepSize"),
        "market_lot_min_qty": (filters.get("MARKET_LOT_SIZE") or {}).get("minQty"),
        "market_lot_max_qty": (filters.get("MARKET_LOT_SIZE") or {}).get("maxQty"),
        "market_step_size": (filters.get("MARKET_LOT_SIZE") or {}).get("stepSize"),
        "min_notional": (filters.get("MIN_NOTIONAL") or {}).get("notional"),
        "percent_price_multiplier_up": (filters.get("PERCENT_PRICE") or {}).get("multiplierUp"),
        "percent_price_multiplier_down": (filters.get("PERCENT_PRICE") or {}).get("multiplierDown"),
        "max_num_orders": (filters.get("MAX_NUM_ORDERS") or {}).get("limit"),
        "max_num_algo_orders": (filters.get("MAX_NUM_ALGO_ORDERS") or {}).get("limit"),
        "liquidation_fee": row.get("liquidationFee"),
        "market_take_bound": row.get("marketTakeBound"),
    }


def _ticker_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "missing"}
    return {
        "last_price": _as_float(payload.get("lastPrice")),
        "price_change_pct": _as_float(payload.get("priceChangePercent")),
        "volume_base_24h": _as_float(payload.get("volume")),
        "volume_quote_24h": _as_float(payload.get("quoteVolume")),
        "weighted_avg_price": _as_float(payload.get("weightedAvgPrice")),
        "trade_count_24h": _as_int(payload.get("count")),
    }


def _order_book_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "missing"}
    bids = payload.get("bids") or []
    asks = payload.get("asks") or []
    best_bid = _as_float((bids[0] or [None])[0]) if bids else None
    best_ask = _as_float((asks[0] or [None])[0]) if asks else None
    mid = ((best_bid + best_ask) / 2) if best_bid and best_ask else None
    spread_bps = ((best_ask - best_bid) / mid * 10_000) if mid and best_ask and best_bid else None
    bid_depth = sum((_as_float(row[0]) or 0) * (_as_float(row[1]) or 0) for row in bids[:10])
    ask_depth = sum((_as_float(row[0]) or 0) * (_as_float(row[1]) or 0) for row in asks[:10])
    total_depth = bid_depth + ask_depth
    imbalance = ((bid_depth - ask_depth) / total_depth) if total_depth else None
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_bps": round(spread_bps, 4) if spread_bps is not None else None,
        "top10_bid_depth_usd": round(bid_depth, 4),
        "top10_ask_depth_usd": round(ask_depth, 4),
        "top10_depth_imbalance": round(imbalance, 6) if imbalance is not None else None,
        "last_update_id": payload.get("lastUpdateId"),
    }


def _kline_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, list) or not payload:
        return {"status": "missing", "kline_count": 0}
    closes = [_as_float(row[4]) for row in payload if isinstance(row, list) and len(row) > 5]
    highs = [_as_float(row[2]) for row in payload if isinstance(row, list) and len(row) > 5]
    lows = [_as_float(row[3]) for row in payload if isinstance(row, list) and len(row) > 5]
    quote_volumes = [_as_float(row[7]) for row in payload if isinstance(row, list) and len(row) > 8]
    trade_counts = [_as_int(row[8]) for row in payload if isinstance(row, list) and len(row) > 8]
    taker_buy_quote = [_as_float(row[10]) for row in payload if isinstance(row, list) and len(row) > 10]
    closes = [v for v in closes if v is not None]
    highs = [v for v in highs if v is not None]
    lows = [v for v in lows if v is not None]
    quote_volumes = [v for v in quote_volumes if v is not None]
    trade_counts = [v for v in trade_counts if v is not None]
    taker_buy_quote = [v for v in taker_buy_quote if v is not None]
    pct = None
    if len(closes) >= 2 and closes[0]:
        pct = ((closes[-1] - closes[0]) / closes[0]) * 100
    volatility_pct = None
    if highs and lows and closes and closes[-1]:
        volatility_pct = ((max(highs) - min(lows)) / closes[-1]) * 100
    quote_sum = sum(quote_volumes) if quote_volumes else None
    taker_buy_quote_sum = sum(taker_buy_quote) if taker_buy_quote else None
    taker_buy_quote_ratio = None
    if quote_sum and taker_buy_quote_sum is not None:
        taker_buy_quote_ratio = taker_buy_quote_sum / quote_sum
    return {
        "kline_count": len(payload),
        "first_close": closes[0] if closes else None,
        "last_close": closes[-1] if closes else None,
        "window_price_change_pct": round(pct, 6) if pct is not None else None,
        "window_volatility_pct": round(volatility_pct, 6) if volatility_pct is not None else None,
        "quote_volume_sum": round(quote_sum, 4) if quote_sum is not None else None,
        "trade_count_sum": sum(trade_counts) if trade_counts else None,
        "taker_buy_quote_ratio": round(taker_buy_quote_ratio, 6) if taker_buy_quote_ratio is not None else None,
    }


def _funding_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, list) or not payload:
        return {"status": "missing", "funding_count": 0}
    rates = [_as_float(row.get("fundingRate")) for row in payload if isinstance(row, dict)]
    rates = [v for v in rates if v is not None]
    return {
        "funding_count": len(payload),
        "latest_funding_rate": rates[-1] if rates else None,
        "avg_funding_rate": round(sum(rates) / len(rates), 10) if rates else None,
        "min_funding_rate": min(rates) if rates else None,
        "max_funding_rate": max(rates) if rates else None,
    }


def _premium_metrics(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        return {"status": "missing"}
    mark = _as_float(payload.get("markPrice"))
    index = _as_float(payload.get("indexPrice"))
    premium_bps = None
    if mark is not None and index:
        premium_bps = ((mark - index) / index) * 10_000
    return {
        "mark_price": mark,
        "index_price": index,
        "premium_bps": round(premium_bps, 6) if premium_bps is not None else None,
        "last_funding_rate": _as_float(payload.get("lastFundingRate")),
        "next_funding_time": _as_int(payload.get("nextFundingTime")),
        "interest_rate": _as_float(payload.get("interestRate")),
        "time": _as_int(payload.get("time")),
    }


def _funding_info_metrics(payload: Any, symbol: str) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = next((row for row in payload if isinstance(row, dict) and str(row.get("symbol", "")).upper() == symbol), None)
    if not isinstance(payload, dict):
        return {"status": "missing"}
    return {
        "interest_rate": _as_float(payload.get("interestRate")),
        "funding_interval_hours": _as_int(payload.get("fundingIntervalHours")),
        "funding_fee_cap": _as_float(payload.get("fundingFeeCap")),
        "funding_fee_floor": _as_float(payload.get("fundingFeeFloor")),
        "time": _as_int(payload.get("time")),
    }


def _index_reference_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "missing"}
    refs = payload.get("references") or []
    normalized_refs: list[dict[str, Any]] = []
    for row in refs[:10]:
        if not isinstance(row, dict):
            continue
        normalized_refs.append(
            {
                "exchange": row.get("exchange"),
                "symbol": row.get("symbol"),
                "weight": _as_float(row.get("weight")),
            }
        )
    return {
        "reference_count": len(refs),
        "references": normalized_refs,
    }


def _call_status(results: list[dict[str, Any]]) -> str:
    statuses = [str(row.get("status")) for row in results]
    if any(status == "ip_auto_banned" for status in statuses):
        return "ip_auto_banned"
    if any(status in {"blocked_by_waf", "rate_limited"} for status in statuses):
        return "degraded"
    if all(status == "ok" for status in statuses):
        return "ok"
    return "partial"


def get_aster_mcp_market_data_adapter_preview(
    symbols: str | list[str] | None = "BTCUSDT,INJUSDT,LABUSDT",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 5,
    kline_interval: str = "1h",
    kline_limit: int = 50,
    funding_limit: int = 20,
    depth_limit: int = 50,
    base_url: str | None = None,
) -> dict[str, Any]:
    if not dry_run:
        return {
            "ok": False,
            "adapter_status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }

    safe_timeout = max(1, min(int(timeout_seconds or 8), 10))
    safe_symbols = _parse_symbols(symbols, max(1, min(int(max_symbols or 5), 10)))
    safe_kline_limit = max(1, min(int(kline_limit or 50), 1000))
    safe_funding_limit = max(1, min(int(funding_limit or 20), 1000))
    safe_depth_limit = min(max(int(depth_limit or 50), 5), 100)
    clean_interval = str(kline_interval or "1h").strip() or "1h"
    clean_base = str(base_url or ASTER_FAPI_V3_BASE_URL).rstrip("/")

    exchange = _fetch_json(_url(clean_base, "/fapi/v3/exchangeInfo"), safe_timeout)
    exchange_payload = exchange.get("payload") if exchange.get("ok") else None
    call_results = [exchange]
    rows: list[dict[str, Any]] = []

    for symbol in safe_symbols:
        ticker = _fetch_json(_url(clean_base, "/fapi/v3/ticker/24hr", {"symbol": symbol}), safe_timeout)
        depth = _fetch_json(_url(clean_base, "/fapi/v3/depth", {"symbol": symbol, "limit": safe_depth_limit}), safe_timeout)
        klines = _fetch_json(
            _url(clean_base, "/fapi/v3/klines", {"symbol": symbol, "interval": clean_interval, "limit": safe_kline_limit}),
            safe_timeout,
        )
        mark_klines = _fetch_json(
            _url(clean_base, "/fapi/v3/markPriceKlines", {"symbol": symbol, "interval": clean_interval, "limit": safe_kline_limit}),
            safe_timeout,
        )
        index_klines = _fetch_json(
            _url(clean_base, "/fapi/v3/indexPriceKlines", {"pair": symbol, "interval": clean_interval, "limit": safe_kline_limit}),
            safe_timeout,
        )
        premium = _fetch_json(_url(clean_base, "/fapi/v3/premiumIndex", {"symbol": symbol}), safe_timeout)
        funding = _fetch_json(_url(clean_base, "/fapi/v3/fundingRate", {"symbol": symbol, "limit": safe_funding_limit}), safe_timeout)
        funding_info = _fetch_json(_url(clean_base, "/fapi/v3/fundingInfo", {"symbol": symbol}), safe_timeout)
        index_references = _fetch_json(_url(clean_base, "/fapi/v3/indexreferences", {"symbol": symbol}), safe_timeout)
        call_results.extend([ticker, depth, klines, mark_klines, index_klines, premium, funding, funding_info, index_references])
        rows.append(
            {
                "symbol": symbol,
                "exchange_filters": _symbol_exchange_info(exchange_payload, symbol),
                "ticker": _ticker_metrics(ticker.get("payload")),
                "order_book": _order_book_metrics(depth.get("payload")),
                "klines": _kline_metrics(klines.get("payload")),
                "mark_price_klines": _kline_metrics(mark_klines.get("payload")),
                "index_price_klines": _kline_metrics(index_klines.get("payload")),
                "premium_index": _premium_metrics(premium.get("payload")),
                "funding": _funding_metrics(funding.get("payload")),
                "funding_info": _funding_info_metrics(funding_info.get("payload"), symbol),
                "index_references": _index_reference_metrics(index_references.get("payload")),
                "endpoint_status": {
                    "ticker": ticker.get("status"),
                    "depth": depth.get("status"),
                    "klines": klines.get("status"),
                    "mark_price_klines": mark_klines.get("status"),
                    "index_price_klines": index_klines.get("status"),
                    "premium_index": premium.get("status"),
                    "funding": funding.get("status"),
                    "funding_info": funding_info.get("status"),
                    "index_references": index_references.get("status"),
                },
            }
        )

    dangerous = sorted(BLOCKED_TOOLS)
    allowed = sorted(READ_ONLY_TOOLS)
    return {
        "ok": True,
        "dry_run": True,
        "adapter_status": _call_status(call_results),
        "source_mode": "public_rest_v3_preview_for_future_mcp_adapter",
        "base_url": clean_base,
        "symbols_requested": safe_symbols,
        "market_data": rows,
        "mcp_policy": {
            "allowed_read_only_tools": allowed,
            "blocked_tools": dangerous,
            "would_allow_trade_tools": False,
            "would_allow_transfer_tools": False,
            "requires_wrapper_before_agent_use": True,
        },
        "account_data_plan": {
            "status": "not_called",
            "reason": "private_user_data_endpoints_require_signed_credentials_and_are_blocked_in_this_preview",
            "future_read_only_tools": ["get_balance", "get_positions", "get_commission_rate", "get_leverage_bracket"],
            "blocked_until_credentials_policy_exists": ["leverageBracket", "commissionRate", "account", "positionRisk"],
        },
        "rate_limit_summary": {
            "calls_attempted": len(call_results),
            "statuses": {status: [row.get("status") for row in call_results].count(status) for status in sorted({str(row.get("status")) for row in call_results})},
            "headers_seen": [row.get("rate_limit_headers") for row in call_results if row.get("rate_limit_headers")],
        },
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


def _abs(value: float | None) -> float | None:
    return abs(value) if value is not None else None


def _round(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None else None


def _reality_check_row(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "")
    endpoints = row.get("endpoint_status") or {}
    exchange = row.get("exchange_filters") or {}
    ticker = row.get("ticker") or {}
    book = row.get("order_book") or {}
    klines = row.get("klines") or {}
    mark_klines = row.get("mark_price_klines") or {}
    index_klines = row.get("index_price_klines") or {}
    premium = row.get("premium_index") or {}
    funding = row.get("funding") or {}
    funding_info = row.get("funding_info") or {}
    index_refs = row.get("index_references") or {}

    risks: list[str] = []
    warnings: list[str] = []
    ok_count = sum(1 for status in endpoints.values() if status == "ok")
    if ok_count < max(1, len(endpoints)):
        risks.append("market_data_incomplete")
    if exchange.get("status") != "TRADING":
        risks.append("symbol_not_trading")

    quote_volume_24h = _as_float(ticker.get("volume_quote_24h"))
    quote_volume_window = _as_float(klines.get("quote_volume_sum"))
    trade_count_window = _as_int(klines.get("trade_count_sum"))
    spread_bps = _as_float(book.get("spread_bps"))
    bid_depth = _as_float(book.get("top10_bid_depth_usd")) or 0.0
    ask_depth = _as_float(book.get("top10_ask_depth_usd")) or 0.0
    top10_depth = bid_depth + ask_depth
    premium_bps = _as_float(premium.get("premium_bps"))
    latest_funding = _as_float(premium.get("last_funding_rate"))
    avg_funding = _as_float(funding.get("avg_funding_rate"))
    funding_cap = _as_float(funding_info.get("funding_fee_cap"))
    funding_floor = _as_float(funding_info.get("funding_fee_floor"))
    ref_count = _as_int(index_refs.get("reference_count"))
    mark_last = _as_float(mark_klines.get("last_close"))
    index_last = _as_float(index_klines.get("last_close"))
    trigger_protect = _as_float(exchange.get("trigger_protect"))
    market_take_bound = _as_float(exchange.get("market_take_bound"))
    min_notional = _as_float(exchange.get("min_notional"))
    price_tick_size = _as_float(exchange.get("price_tick_size"))
    quantity_step_size = _as_float(exchange.get("quantity_step_size"))
    market_step_size = _as_float(exchange.get("market_step_size"))
    percent_price_multiplier_up = _as_float(exchange.get("percent_price_multiplier_up"))
    percent_price_multiplier_down = _as_float(exchange.get("percent_price_multiplier_down"))
    order_types = str(exchange.get("order_types") or "")
    time_in_force = str(exchange.get("time_in_force") or "")
    mark_index_kline_bps = None
    if mark_last is not None and index_last:
        mark_index_kline_bps = ((mark_last - index_last) / index_last) * 10_000

    if not order_types:
        warnings.append("missing_order_type_filter")
    elif "MARKET" not in {item.strip().upper() for item in order_types.split(",")}:
        risks.append("market_orders_not_supported")
    if time_in_force and "GTX" not in {item.strip().upper() for item in time_in_force.split(",")}:
        warnings.append("post_only_tif_not_supported")
    if trigger_protect is None:
        warnings.append("missing_trigger_protect")
    elif trigger_protect <= 0.02:
        warnings.append("tight_trigger_protect")
    elif trigger_protect >= 0.10:
        warnings.append("wide_trigger_protect")
    if market_take_bound is None:
        warnings.append("missing_market_take_bound")
    elif market_take_bound <= 0.02:
        warnings.append("tight_market_take_bound")
    elif market_take_bound >= 0.10:
        warnings.append("wide_market_take_bound")
    if min_notional is None:
        warnings.append("missing_min_notional")
    elif min_notional > 50:
        warnings.append("high_min_notional")
    if price_tick_size is None or quantity_step_size is None or market_step_size is None:
        warnings.append("missing_precision_filter")
    if percent_price_multiplier_up is None or percent_price_multiplier_down is None:
        warnings.append("missing_percent_price_filter")

    if quote_volume_24h is not None and quote_volume_24h < 50_000:
        risks.append("low_24h_quote_volume")
    elif quote_volume_24h is not None and quote_volume_24h < 250_000:
        warnings.append("moderate_24h_quote_volume")
    if quote_volume_window is not None and quote_volume_window < 5_000:
        warnings.append("thin_kline_window_volume")
    if trade_count_window is not None and trade_count_window < 30:
        warnings.append("low_trade_count_window")
    if top10_depth and top10_depth < 10_000:
        warnings.append("thin_top10_depth")
    if spread_bps is not None and spread_bps > 30:
        risks.append("wide_spread")
    elif spread_bps is not None and spread_bps > 10:
        warnings.append("moderate_spread")
    if premium_bps is not None and abs(premium_bps) > 50:
        risks.append("large_mark_index_premium")
    elif premium_bps is not None and abs(premium_bps) > 15:
        warnings.append("moderate_mark_index_premium")
    if mark_index_kline_bps is not None and abs(mark_index_kline_bps) > 50:
        risks.append("large_mark_index_kline_divergence")
    elif mark_index_kline_bps is not None and abs(mark_index_kline_bps) > 15:
        warnings.append("moderate_mark_index_kline_divergence")
    if latest_funding is not None and abs(latest_funding) > 0.001:
        warnings.append("high_latest_funding")
    if avg_funding is not None and abs(avg_funding) > 0.001:
        warnings.append("high_average_funding")
    if funding_cap is not None and funding_floor is not None and (abs(funding_cap) >= 0.02 or abs(funding_floor) >= 0.02):
        warnings.append("wide_funding_cap_floor")
    if ref_count is not None and ref_count < 4:
        warnings.append("low_index_reference_count")

    quality_score = 100
    quality_score -= len(risks) * 18
    quality_score -= len(warnings) * 7
    quality_score = max(0, min(100, quality_score))
    verdict = (
        "backtest_quality_ok"
        if quality_score >= 80 and not risks
        else "backtest_quality_watch"
        if quality_score >= 60
        else "backtest_quality_risky"
    )
    return {
        "symbol": symbol,
        "quality_score": quality_score,
        "verdict": verdict,
        "risks": risks,
        "warnings": warnings,
        "key_metrics": {
            "quote_volume_24h": quote_volume_24h,
            "quote_volume_window": quote_volume_window,
            "trade_count_window": trade_count_window,
            "spread_bps": spread_bps,
            "top10_depth_usd": _round(top10_depth, 4),
            "premium_bps": premium_bps,
            "mark_index_kline_bps": _round(mark_index_kline_bps),
            "latest_funding_rate": latest_funding,
            "avg_funding_rate": avg_funding,
            "funding_interval_hours": _as_int(funding_info.get("funding_interval_hours")),
            "funding_fee_cap": funding_cap,
            "funding_fee_floor": funding_floor,
            "index_reference_count": ref_count,
            "trigger_protect": trigger_protect,
            "market_take_bound": market_take_bound,
            "min_notional": min_notional,
            "price_tick_size": price_tick_size,
            "quantity_step_size": quantity_step_size,
            "market_step_size": market_step_size,
            "percent_price_multiplier_up": percent_price_multiplier_up,
            "percent_price_multiplier_down": percent_price_multiplier_down,
            "order_types": order_types,
            "time_in_force": time_in_force,
            "window_volatility_pct": _as_float(klines.get("window_volatility_pct")),
            "taker_buy_quote_ratio": _as_float(klines.get("taker_buy_quote_ratio")),
        },
        "endpoint_status": endpoints,
    }


def get_aster_perps_reality_check_preview(
    symbols: str | list[str] | None = "LABUSDT,INJUSDT,BOMEUSDT,TIAUSDT,INTCUSDT,CRCLUSDT,MSFTUSDT",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 8,
    kline_interval: str = "1h",
    kline_limit: int = 50,
    funding_limit: int = 20,
    depth_limit: int = 50,
) -> dict[str, Any]:
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }

    adapter = get_aster_mcp_market_data_adapter_preview(
        symbols=symbols,
        dry_run=True,
        timeout_seconds=timeout_seconds,
        max_symbols=max_symbols,
        kline_interval=kline_interval,
        kline_limit=kline_limit,
        funding_limit=funding_limit,
        depth_limit=depth_limit,
    )
    rows = [_reality_check_row(row) for row in adapter.get("market_data") or []]
    counts = {
        "backtest_quality_ok": sum(1 for row in rows if row.get("verdict") == "backtest_quality_ok"),
        "backtest_quality_watch": sum(1 for row in rows if row.get("verdict") == "backtest_quality_watch"),
        "backtest_quality_risky": sum(1 for row in rows if row.get("verdict") == "backtest_quality_risky"),
    }
    promoted = [row for row in rows if row.get("verdict") == "backtest_quality_ok"]
    watch = [row for row in rows if row.get("verdict") == "backtest_quality_watch"]
    risky = [row for row in rows if row.get("verdict") == "backtest_quality_risky"]
    return {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source": "aster_public_v3_reality_check",
        "adapter_status": adapter.get("adapter_status"),
        "symbols_checked": adapter.get("symbols_requested"),
        "summary": {
            "total": len(rows),
            **counts,
            "recommended_for_reality_checked_backtest": [row.get("symbol") for row in promoted],
            "watchlist": [row.get("symbol") for row in watch],
            "avoid_or_manual_review": [row.get("symbol") for row in risky],
        },
        "rows": rows,
        "interpretation": {
            "backtest_quality_ok": "Market data is complete and no major public-perps quality risk was observed.",
            "backtest_quality_watch": "Backtest can continue, but lane promotion should be conservative.",
            "backtest_quality_risky": "Do not promote the lane without manual review or stronger evidence.",
        },
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
