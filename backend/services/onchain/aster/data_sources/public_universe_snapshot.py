from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.aster_mcp_market_data_adapter import (
    ASTER_FAPI_V3_BASE_URL,
    _as_float,
    _as_int,
    _fetch_json,
    _symbol_exchange_info,
    _url,
)


BASE_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_FILE = BASE_DIR / "aster_public_universe_snapshot_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _by_symbol(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            out[symbol] = row
    return out


def _spread_bps(book: dict[str, Any] | None) -> float | None:
    if not isinstance(book, dict):
        return None
    bid = _as_float(book.get("bidPrice"))
    ask = _as_float(book.get("askPrice"))
    if not bid or not ask:
        return None
    mid = (bid + ask) / 2
    return ((ask - bid) / mid) * 10_000 if mid else None


def _premium_bps(premium: dict[str, Any] | None) -> float | None:
    if not isinstance(premium, dict):
        return None
    mark = _as_float(premium.get("markPrice"))
    index = _as_float(premium.get("indexPrice"))
    if mark is None or not index:
        return None
    return ((mark - index) / index) * 10_000


def _as_sorted(rows: list[dict[str, Any]], key: str, limit: int, reverse: bool = True) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: _as_float(row.get(key)) or 0.0, reverse=reverse)[:limit]


def _build_row(
    symbol: str,
    exchange: dict[str, Any],
    ticker: dict[str, Any] | None,
    book: dict[str, Any] | None,
    premium: dict[str, Any] | None,
    funding: dict[str, Any] | None,
) -> dict[str, Any]:
    filters = exchange.get(symbol) or {"symbol": symbol, "status": "not_found_in_exchange_info"}
    quote_volume = _as_float((ticker or {}).get("quoteVolume"))
    trade_count = _as_int((ticker or {}).get("count"))
    price_change_pct = _as_float((ticker or {}).get("priceChangePercent"))
    spread = _spread_bps(book)
    premium_live = _premium_bps(premium)
    funding_rate = _as_float((premium or {}).get("lastFundingRate"))
    funding_cap = _as_float((funding or {}).get("fundingFeeCap"))
    funding_floor = _as_float((funding or {}).get("fundingFeeFloor"))
    flags: list[str] = []
    if filters.get("status") != "TRADING":
        flags.append("not_trading")
    if quote_volume is not None and quote_volume < 50_000:
        flags.append("low_24h_quote_volume")
    if spread is not None and spread > 30:
        flags.append("wide_spread")
    if premium_live is not None and abs(premium_live) > 50:
        flags.append("large_mark_index_premium")
    if funding_rate is not None and abs(funding_rate) > 0.001:
        flags.append("high_funding_rate")
    if funding_cap is not None and funding_floor is not None and (abs(funding_cap) >= 0.02 or abs(funding_floor) >= 0.02):
        flags.append("wide_funding_cap_floor")

    return {
        "symbol": symbol,
        "status": filters.get("status"),
        "contract_type": filters.get("contract_type"),
        "base_asset": filters.get("base_asset"),
        "quote_asset": filters.get("quote_asset"),
        "margin_asset": filters.get("margin_asset"),
        "quote_volume_24h": quote_volume,
        "trade_count_24h": trade_count,
        "price_change_pct_24h": price_change_pct,
        "last_price": _as_float((ticker or {}).get("lastPrice")),
        "spread_bps": round(spread, 6) if spread is not None else None,
        "bid_price": _as_float((book or {}).get("bidPrice")),
        "ask_price": _as_float((book or {}).get("askPrice")),
        "mark_price": _as_float((premium or {}).get("markPrice")),
        "index_price": _as_float((premium or {}).get("indexPrice")),
        "premium_bps": round(premium_live, 6) if premium_live is not None else None,
        "last_funding_rate": funding_rate,
        "funding_interval_hours": _as_int((funding or {}).get("fundingIntervalHours")),
        "funding_fee_cap": funding_cap,
        "funding_fee_floor": funding_floor,
        "trigger_protect": filters.get("trigger_protect"),
        "market_take_bound": filters.get("market_take_bound"),
        "min_notional": filters.get("min_notional"),
        "order_types": filters.get("order_types"),
        "time_in_force": filters.get("time_in_force"),
        "data_flags": flags,
        "usable_for_research": filters.get("status") == "TRADING" and quote_volume is not None and spread is not None,
    }


def get_aster_public_universe_snapshot_preview(
    dry_run: bool = True,
    timeout_seconds: int = 8,
    top_n: int = 30,
    base_url: str | None = None,
    write_snapshot: bool = False,
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

    safe_timeout = max(1, min(int(timeout_seconds or 8), 15))
    safe_top = max(1, min(int(top_n or 30), 100))
    clean_base = str(base_url or ASTER_FAPI_V3_BASE_URL).rstrip("/")

    exchange_result = _fetch_json(_url(clean_base, "/fapi/v3/exchangeInfo"), safe_timeout)
    ticker_result = _fetch_json(_url(clean_base, "/fapi/v3/ticker/24hr"), safe_timeout)
    book_result = _fetch_json(_url(clean_base, "/fapi/v3/ticker/bookTicker"), safe_timeout)
    premium_result = _fetch_json(_url(clean_base, "/fapi/v3/premiumIndex"), safe_timeout)
    funding_result = _fetch_json(_url(clean_base, "/fapi/v3/fundingInfo"), safe_timeout)

    exchange_payload = exchange_result.get("payload") if exchange_result.get("ok") else {}
    exchange_symbols = (exchange_payload or {}).get("symbols") if isinstance(exchange_payload, dict) else []
    symbol_set = sorted({str(row.get("symbol") or "").upper() for row in exchange_symbols or [] if isinstance(row, dict) and row.get("symbol")})
    exchange = {symbol: _symbol_exchange_info(exchange_payload, symbol) for symbol in symbol_set}
    ticker = _by_symbol(ticker_result.get("payload"))
    book = _by_symbol(book_result.get("payload"))
    premium = _by_symbol(premium_result.get("payload"))
    funding = _by_symbol(funding_result.get("payload"))

    all_symbols = sorted(set(symbol_set) | set(ticker.keys()) | set(book.keys()) | set(premium.keys()) | set(funding.keys()))
    rows = [_build_row(symbol, exchange, ticker.get(symbol), book.get(symbol), premium.get(symbol), funding.get(symbol)) for symbol in all_symbols]
    research_rows = [row for row in rows if row.get("usable_for_research")]
    trading_rows = [row for row in rows if row.get("status") == "TRADING"]
    flag_counts: dict[str, int] = {}
    for row in rows:
        for flag in row.get("data_flags") or []:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    payload = {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source_policy": "official_public_rest_universe_snapshot",
        "base_url": clean_base,
        "generated_at": _now(),
        "summary": {
            "symbols_total": len(rows),
            "symbols_trading": len(trading_rows),
            "symbols_usable_for_research": len(research_rows),
            "flag_counts": flag_counts,
            "endpoint_status": {
                "exchangeInfo": exchange_result.get("status"),
                "ticker_24h_all": ticker_result.get("status"),
                "bookTicker_all": book_result.get("status"),
                "premiumIndex_all": premium_result.get("status"),
                "fundingInfo_all": funding_result.get("status"),
            },
        },
        "top_by_quote_volume": _as_sorted(research_rows, "quote_volume_24h", safe_top),
        "top_by_abs_price_change": sorted(
            research_rows,
            key=lambda row: abs(_as_float(row.get("price_change_pct_24h")) or 0.0),
            reverse=True,
        )[:safe_top],
        "top_by_funding_abs": sorted(
            research_rows,
            key=lambda row: abs(_as_float(row.get("last_funding_rate")) or 0.0),
            reverse=True,
        )[:safe_top],
        "top_clean_research_universe": [
            row
            for row in _as_sorted(research_rows, "quote_volume_24h", safe_top * 2)
            if not row.get("data_flags")
        ][:safe_top],
        "all_research_universe": research_rows,
        "all_rows": rows,
        "rows_sample": rows[:safe_top],
        "safety": {
            "would_write": bool(write_snapshot),
            "writes_performed": 0,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_trade_endpoint": False,
            "would_store_credentials": False,
        },
    }
    if write_snapshot:
        SNAPSHOT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["safety"]["writes_performed"] = 1
        payload["snapshot_path"] = str(SNAPSHOT_FILE)
    return payload
