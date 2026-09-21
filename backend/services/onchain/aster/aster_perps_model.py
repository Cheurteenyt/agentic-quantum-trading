from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ASTER_FAPI_V3_BASE_URL = "https://fapi.asterdex.com"
FUNDING_CACHE_FILE = Path(__file__).with_name("aster_public_funding_history_cache.json")
EXCHANGE_INFO_CACHE_FILE = Path(__file__).with_name("aster_public_exchange_info_cache.json")


DEFAULT_ASSUMPTIONS: dict[str, Any] = {
    "assumed_margin_mode": "isolated",
    "assumed_asset_mode": "single_asset",
    "assumed_position_mode": "one_way",
    "assumed_execution_model": "taker_market",
    "assumed_trigger_reference": "mark_price_for_liquidation_last_price_for_entry_exit",
    "reduce_only_required_for_exits": True,
    "source": "aster_official_docs_gap_audit_2026_05_31",
}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def quote_asset_for_symbol(symbol: str | None) -> str:
    clean = str(symbol or "").strip().upper()
    if clean.endswith("USD1"):
        return "USD1"
    if clean.endswith("USDT"):
        return "USDT"
    return "UNKNOWN"


def taker_fee_bps_for_symbol(symbol: str | None) -> float:
    quote = quote_asset_for_symbol(symbol)
    if quote == "USD1":
        return 0.5
    if quote == "USDT":
        return 4.0
    return 4.0


def maker_fee_bps_for_symbol(symbol: str | None) -> float:
    quote = quote_asset_for_symbol(symbol)
    if quote in {"USDT", "USD1"}:
        return 0.0
    return 0.0


def execution_fee_bps(symbol: str | None, execution_model: str | None = None) -> float:
    model = str(execution_model or "taker_market").strip().lower()
    if model in {"maker_post_only", "bbo_limit_maker", "post_only"}:
        return maker_fee_bps_for_symbol(symbol)
    return taker_fee_bps_for_symbol(symbol)


def _read_funding_cache() -> dict[str, Any]:
    try:
        return json.loads(FUNDING_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"symbols": {}}


def _write_funding_cache(payload: dict[str, Any]) -> None:
    try:
        temp_path = FUNDING_CACHE_FILE.with_name(f"{FUNDING_CACHE_FILE.name}.{os.getpid()}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        temp_path.replace(FUNDING_CACHE_FILE)
    except OSError:
        return


def _read_exchange_info_cache() -> dict[str, Any]:
    try:
        return json.loads(EXCHANGE_INFO_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"symbols": {}}


def _write_exchange_info_cache(payload: dict[str, Any]) -> None:
    try:
        temp_path = EXCHANGE_INFO_CACHE_FILE.with_name(f"{EXCHANGE_INFO_CACHE_FILE.name}.{os.getpid()}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        temp_path.replace(EXCHANGE_INFO_CACHE_FILE)
    except OSError:
        return


def _normalize_exchange_info_symbol(row: dict[str, Any] | None, symbol: str) -> dict[str, Any]:
    clean_symbol = str(symbol or "").strip().upper()
    if not isinstance(row, dict):
        return {"symbol": clean_symbol, "exchange_info_status": "not_found"}
    filters = {item.get("filterType"): item for item in row.get("filters") or [] if isinstance(item, dict)}
    price_filter = filters.get("PRICE_FILTER") or {}
    lot_size = filters.get("LOT_SIZE") or {}
    market_lot_size = filters.get("MARKET_LOT_SIZE") or {}
    min_notional = filters.get("MIN_NOTIONAL") or {}
    percent_price = filters.get("PERCENT_PRICE") or {}
    order_types = row.get("orderTypes") or row.get("orderType") or []
    time_in_force = row.get("timeInForce") or []
    return {
        "symbol": clean_symbol,
        "exchange_info_status": "ok",
        "symbol_status": row.get("status"),
        "contract_type": row.get("contractType"),
        "base_asset": row.get("baseAsset"),
        "quote_asset": row.get("quoteAsset"),
        "margin_asset": row.get("marginAsset"),
        "trigger_protect": row.get("triggerProtect"),
        "market_take_bound": row.get("marketTakeBound"),
        "liquidation_fee_rate": row.get("liquidationFee"),
        "price_min": price_filter.get("minPrice"),
        "price_max": price_filter.get("maxPrice"),
        "tick_size": price_filter.get("tickSize"),
        "lot_min_qty": lot_size.get("minQty"),
        "lot_max_qty": lot_size.get("maxQty"),
        "step_size": lot_size.get("stepSize"),
        "market_lot_min_qty": market_lot_size.get("minQty"),
        "market_lot_max_qty": market_lot_size.get("maxQty"),
        "market_step_size": market_lot_size.get("stepSize"),
        "min_notional": min_notional.get("notional"),
        "percent_price_up": percent_price.get("multiplierUp"),
        "percent_price_down": percent_price.get("multiplierDown"),
        "max_num_orders": (filters.get("MAX_NUM_ORDERS") or {}).get("limit"),
        "max_num_algo_orders": (filters.get("MAX_NUM_ALGO_ORDERS") or {}).get("limit"),
        "order_types": ",".join(str(item) for item in order_types) if isinstance(order_types, list) else str(order_types or ""),
        "time_in_force": ",".join(str(item) for item in time_in_force) if isinstance(time_in_force, list) else str(time_in_force or ""),
    }


def _fetch_exchange_info(timeout_seconds: int) -> dict[str, dict[str, Any]]:
    url = f"{ASTER_FAPI_V3_BASE_URL}/fapi/v3/exchangeInfo"
    request = urllib.request.Request(url, headers={"User-Agent": "CoreEquityAsterExchangeInfo/0.1"})
    with urllib.request.urlopen(request, timeout=max(1, min(int(timeout_seconds or 8), 15))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("symbols") if isinstance(payload, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol:
            result[symbol] = _normalize_exchange_info_symbol(row, symbol)
    return result


def get_public_exchange_info_snapshot(
    symbols: list[str] | tuple[str, ...] | set[str],
    *,
    timeout_seconds: int = 8,
    cache_ttl_seconds: int = 900,
) -> dict[str, dict[str, Any]]:
    """Return public exchangeInfo filters per symbol, using one all-symbol fetch."""
    now = time.time()
    safe_symbols = list(dict.fromkeys(str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()))
    cache = _read_exchange_info_cache()
    cache_symbols = cache.get("symbols") if isinstance(cache.get("symbols"), dict) else {}
    cache_status = str(cache.get("status") or "")
    if cache_status == "ok" and now - float(cache.get("cached_at") or 0) <= max(0, int(cache_ttl_seconds or 0)):
        return {
            symbol: {**(cache_symbols.get(symbol) or {"symbol": symbol, "exchange_info_status": "not_found"}), "cache_status": "hit"}
            for symbol in safe_symbols
        }
    try:
        fetched = _fetch_exchange_info(timeout_seconds)
        cache = {"status": "ok", "cached_at": now, "symbols": fetched, "symbol_count": len(fetched)}
        _write_exchange_info_cache(cache)
        return {
            symbol: {**(fetched.get(symbol) or {"symbol": symbol, "exchange_info_status": "not_found"}), "cache_status": "miss"}
            for symbol in safe_symbols
        }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        status = f"error_{type(exc).__name__}"
        if isinstance(exc, urllib.error.HTTPError):
            status = {403: "blocked_by_aster", 404: "not_found", 418: "ip_auto_banned", 429: "rate_limited"}.get(exc.code, f"http_{exc.code}")
        return {
            symbol: {
                **(cache_symbols.get(symbol) or {"symbol": symbol}),
                "exchange_info_status": status,
                "cache_status": "stale" if cache_symbols else "missing",
            }
            for symbol in safe_symbols
        }


def exchange_info_reality_verdict(
    snapshot: dict[str, Any] | None,
    *,
    position_notional_usd: float | None = None,
) -> dict[str, Any]:
    row = snapshot if isinstance(snapshot, dict) else {}
    warnings: list[str] = []
    blockers: list[str] = []
    status = str(row.get("exchange_info_status") or "missing")
    if status != "ok":
        blockers.append(status)
    if str(row.get("symbol_status") or "").upper() not in {"", "TRADING"}:
        blockers.append("symbol_not_trading")
    min_notional = _as_float(row.get("min_notional"))
    notional = _as_float(position_notional_usd)
    if min_notional is not None and notional is not None and notional < min_notional:
        blockers.append("position_below_min_notional")
    market_take_bound = _as_float(row.get("market_take_bound"))
    if market_take_bound is not None:
        if market_take_bound <= 0.02:
            warnings.append("tight_market_take_bound")
        elif market_take_bound >= 0.10:
            warnings.append("wide_market_take_bound")
    if not row.get("tick_size"):
        warnings.append("missing_tick_size")
    if not row.get("step_size"):
        warnings.append("missing_step_size")
    if not row.get("percent_price_up") or not row.get("percent_price_down"):
        warnings.append("missing_percent_price")
    return {
        "exchange_filter_verdict": "blocked" if blockers else ("warning" if warnings else "ok"),
        "exchange_filter_warnings": warnings,
        "exchange_filter_blockers": blockers,
    }


def _funding_metrics(symbol: str, rows: Any, status: str) -> dict[str, Any]:
    if not isinstance(rows, list) or not rows:
        return {
            "symbol": symbol,
            "status": status if status != "ok" else "missing",
            "funding_count": 0,
            "source": "aster_public_funding_history_unavailable",
        }
    rates = [_as_float(row.get("fundingRate")) for row in rows if isinstance(row, dict)]
    rates = [rate for rate in rates if rate is not None]
    times = [_as_int(row.get("fundingTime")) for row in rows if isinstance(row, dict)]
    times = [value for value in times if value is not None]
    avg_rate = (sum(rates) / len(rates)) if rates else None
    latest_rate = rates[-1] if rates else None
    return {
        "symbol": symbol,
        "status": status,
        "source": "aster_public_funding_history_fapi_v3",
        "funding_count": len(rows),
        "avg_funding_rate": round(avg_rate, 10) if avg_rate is not None else None,
        "latest_funding_rate": latest_rate,
        "min_funding_rate": min(rates) if rates else None,
        "max_funding_rate": max(rates) if rates else None,
        "avg_funding_bps_per_8h": round(avg_rate * 10_000.0, 6) if avg_rate is not None else None,
        "latest_funding_bps_per_8h": round(latest_rate * 10_000.0, 6) if latest_rate is not None else None,
        "first_funding_time": min(times) if times else None,
        "last_funding_time": max(times) if times else None,
    }


def _fetch_funding_history(symbol: str, limit: int, timeout_seconds: int) -> dict[str, Any]:
    query = urllib.parse.urlencode({"symbol": symbol, "limit": max(1, min(int(limit or 100), 1000))})
    url = f"{ASTER_FAPI_V3_BASE_URL}/fapi/v3/fundingRate?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "CoreEquityAsterFundingModel/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=max(1, min(int(timeout_seconds or 5), 10))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _funding_metrics(symbol, payload, "ok")
    except urllib.error.HTTPError as exc:
        status = {403: "blocked_by_aster", 404: "not_found", 418: "ip_auto_banned", 429: "rate_limited"}.get(exc.code, f"http_{exc.code}")
        return _funding_metrics(symbol, [], status)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "symbol": symbol,
            "status": type(exc).__name__,
            "funding_count": 0,
            "source": "aster_public_funding_history_error",
        }


def get_public_funding_history_snapshot(
    symbols: list[str] | tuple[str, ...] | set[str],
    *,
    limit: int = 100,
    timeout_seconds: int = 5,
    cache_ttl_seconds: int = 900,
) -> dict[str, dict[str, Any]]:
    """Return one public funding snapshot per symbol, using a short local cache."""
    now = time.time()
    safe_symbols = list(dict.fromkeys(str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()))
    cache = _read_funding_cache()
    cache_symbols = cache.setdefault("symbols", {})
    results: dict[str, dict[str, Any]] = {}
    changed = False
    for symbol in safe_symbols:
        cached = cache_symbols.get(symbol)
        if isinstance(cached, dict) and now - float(cached.get("cached_at") or 0) <= max(0, int(cache_ttl_seconds or 0)):
            row = dict(cached.get("data") or {})
            row["cache_status"] = "hit"
            results[symbol] = row
            continue
        row = _fetch_funding_history(symbol, limit=limit, timeout_seconds=timeout_seconds)
        row["cache_status"] = "miss"
        results[symbol] = row
        cache_symbols[symbol] = {"cached_at": now, "data": row}
        changed = True
    if changed:
        cache["updated_at"] = now
        _write_funding_cache(cache)
    return results


def funding_cost_usd_estimate(position_notional_usd: float, side: str | None, funding_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    notional = max(0.0, float(position_notional_usd or 0.0))
    clean_side = str(side or "long").strip().lower()
    snapshot = funding_snapshot if isinstance(funding_snapshot, dict) else {}
    rate = _as_float(snapshot.get("avg_funding_rate"))
    if rate is None:
        rate = DEFAULT_FUNDING_BPS_PER_8H_FALLBACK / 10_000.0
        source = "fallback_fixed_funding_rate"
    else:
        source = str(snapshot.get("source") or "aster_public_funding_history_fapi_v3")
    # Positive funding: longs pay shorts. Negative funding: shorts pay longs.
    side_multiplier = -1.0 if clean_side == "short" else 1.0
    cost = notional * rate * side_multiplier
    return {
        "funding_source": source,
        "funding_status": snapshot.get("status") or ("fallback" if not snapshot else "unknown"),
        "funding_count": snapshot.get("funding_count") or 0,
        "avg_funding_rate": round(rate, 10),
        "avg_funding_bps_per_8h": round(rate * 10_000.0, 6),
        "latest_funding_rate": snapshot.get("latest_funding_rate"),
        "latest_funding_bps_per_8h": snapshot.get("latest_funding_bps_per_8h"),
        "funding_cost_usd_estimate": round(cost, 6),
    }


DEFAULT_FUNDING_BPS_PER_8H_FALLBACK = 1.0


def perps_assumptions(symbol: str | None, execution_model: str | None = None) -> dict[str, Any]:
    model = str(execution_model or DEFAULT_ASSUMPTIONS["assumed_execution_model"]).strip().lower()
    quote = quote_asset_for_symbol(symbol)
    return {
        **DEFAULT_ASSUMPTIONS,
        "symbol": str(symbol or "").strip().upper(),
        "quote_asset": quote,
        "assumed_execution_model": model,
        "maker_fee_bps": maker_fee_bps_for_symbol(symbol),
        "taker_fee_bps": taker_fee_bps_for_symbol(symbol),
        "effective_fee_bps": execution_fee_bps(symbol, model),
        "fee_discount_assumed": False,
        "funding_source": "public_funding_history_fapi_v3_when_available",
        "maintenance_margin_source": "proxy_until_signed_leverage_bracket_policy",
        "liquidation_reference_price": "mark_price",
    }


def round_trip_fee_usd(notional_usd: float, symbol: str | None, execution_model: str | None = None) -> float:
    try:
        notional = max(0.0, float(notional_usd or 0.0))
    except (TypeError, ValueError):
        notional = 0.0
    return notional * (execution_fee_bps(symbol, execution_model) / 10_000.0) * 2.0
