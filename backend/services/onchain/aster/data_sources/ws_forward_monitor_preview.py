from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import time
from datetime import datetime, timezone
from typing import Any

from services.onchain.aster.aster_mcp_market_data_adapter import (
    ASTER_FAPI_V3_BASE_URL,
    _as_float,
    _fetch_json,
    _url,
)
from services.onchain.aster.data_sources.ws_market_stream_validation import WS_HOST


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_symbol(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())[:32] or "BTCUSDT"


def _read_until(sock: ssl.SSLSocket, marker: bytes, max_bytes: int = 8192) -> bytes:
    data = b""
    while marker not in data and len(data) < max_bytes:
        chunk = sock.recv(1024)
        if not chunk:
            break
        data += chunk
    return data


def _read_ws_frame(sock: ssl.SSLSocket, max_payload_bytes: int = 1_000_000) -> bytes:
    header = sock.recv(2)
    if len(header) < 2:
        raise RuntimeError("ws_frame_header_missing")
    _b1, b2 = header
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", sock.recv(8))[0]
    if length > max_payload_bytes:
        raise RuntimeError(f"ws_payload_too_large:{length}")
    mask = sock.recv(4) if masked else b""
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            break
        payload += chunk
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return payload


def _ws_read_one(stream: str, timeout_seconds: int) -> dict[str, Any]:
    path = f"/ws/{stream}"
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {WS_HOST}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "User-Agent: CoreEquityAsterWsForwardPreview/0.1\r\n\r\n"
    )
    started = time.perf_counter()
    sock: ssl.SSLSocket | None = None
    try:
        raw_sock = socket.create_connection((WS_HOST, 443), timeout=timeout_seconds)
        sock = ssl.create_default_context().wrap_socket(raw_sock, server_hostname=WS_HOST)
        sock.settimeout(timeout_seconds)
        sock.sendall(request.encode("ascii"))
        response = _read_until(sock, b"\r\n\r\n")
        status_line = response.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
        if "101" not in status_line:
            return {"ok": False, "stream": stream, "status": "handshake_failed", "http_status_line": status_line}
        payload_raw = _read_ws_frame(sock)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "ok": True,
            "stream": stream,
            "status": "ok",
            "latency_ms": latency_ms,
            "payload": json.loads(payload_raw.decode("utf-8")),
        }
    except (OSError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
        return {"ok": False, "stream": stream, "status": "failed", "error": type(exc).__name__, "error_message": str(exc)[:240]}
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def _combined_stream_read(streams: list[str], timeout_seconds: int, expected: int) -> dict[str, Any]:
    path = "/stream?streams=" + "/".join(streams)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {WS_HOST}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "User-Agent: CoreEquityAsterWsForwardPreview/0.1\r\n\r\n"
    )
    started = time.perf_counter()
    sock: ssl.SSLSocket | None = None
    events: list[dict[str, Any]] = []
    try:
        raw_sock = socket.create_connection((WS_HOST, 443), timeout=timeout_seconds)
        sock = ssl.create_default_context().wrap_socket(raw_sock, server_hostname=WS_HOST)
        sock.settimeout(timeout_seconds)
        sock.sendall(request.encode("ascii"))
        response = _read_until(sock, b"\r\n\r\n")
        status_line = response.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
        if "101" not in status_line:
            return {"ok": False, "status": "handshake_failed", "http_status_line": status_line, "events": []}
        deadline = time.perf_counter() + timeout_seconds
        while len(events) < expected and time.perf_counter() < deadline:
            payload_raw = _read_ws_frame(sock)
            payload = json.loads(payload_raw.decode("utf-8"))
            if isinstance(payload, dict) and "stream" in payload and "data" in payload:
                events.append(payload)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {"ok": True, "status": "ok", "latency_ms": latency_ms, "events": events}
    except (OSError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
        return {"ok": False, "status": "failed", "error": type(exc).__name__, "error_message": str(exc)[:240], "events": events}
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def _extract_trade(payload: dict[str, Any] | None) -> dict[str, Any]:
    row = payload or {}
    return {
        "price": _as_float(row.get("p")),
        "qty": _as_float(row.get("q")),
        "event_time": row.get("E"),
        "trade_time": row.get("T"),
        "buyer_is_maker": row.get("m"),
        "agg_trade_id": row.get("a"),
    }


def _extract_kline(payload: dict[str, Any] | None) -> dict[str, Any]:
    kline = (payload or {}).get("k") if isinstance(payload, dict) else {}
    return {
        "interval": kline.get("i") if isinstance(kline, dict) else None,
        "open": _as_float(kline.get("o")) if isinstance(kline, dict) else None,
        "high": _as_float(kline.get("h")) if isinstance(kline, dict) else None,
        "low": _as_float(kline.get("l")) if isinstance(kline, dict) else None,
        "close": _as_float(kline.get("c")) if isinstance(kline, dict) else None,
        "quote_volume": _as_float(kline.get("q")) if isinstance(kline, dict) else None,
        "trade_count": kline.get("n") if isinstance(kline, dict) else None,
        "closed": kline.get("x") if isinstance(kline, dict) else None,
    }


def _extract_depth(payload: dict[str, Any] | None) -> dict[str, Any]:
    row = payload or {}
    bids = row.get("b") or []
    asks = row.get("a") or []
    bid = _as_float((bids[0] or [None])[0]) if bids else None
    ask = _as_float((asks[0] or [None])[0]) if asks else None
    spread_bps = None
    if bid and ask:
        mid = (bid + ask) / 2
        spread_bps = ((ask - bid) / mid) * 10_000 if mid else None
    return {
        "best_bid": bid,
        "best_ask": ask,
        "spread_bps": round(spread_bps, 6) if spread_bps is not None else None,
        "bid_levels": len(bids),
        "ask_levels": len(asks),
        "first_update_id": row.get("U"),
        "final_update_id": row.get("u"),
    }


def _extract_mark_arr(payload: Any, symbol: str) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else []
    match = next((row for row in rows if isinstance(row, dict) and str(row.get("s") or "").upper() == symbol), None)
    return {
        "array_count": len(rows),
        "symbol_found": bool(match),
        "mark_price": _as_float((match or {}).get("p")),
        "index_price": _as_float((match or {}).get("i")),
        "funding_rate": _as_float((match or {}).get("r")),
        "next_funding_time": (match or {}).get("T"),
    }


def _rest_snapshot(symbol: str, timeout_seconds: int) -> dict[str, Any]:
    clean_base = ASTER_FAPI_V3_BASE_URL
    ticker = _fetch_json(_url(clean_base, "/fapi/v3/ticker/24hr", {"symbol": symbol}), timeout_seconds)
    book = _fetch_json(_url(clean_base, "/fapi/v3/ticker/bookTicker", {"symbol": symbol}), timeout_seconds)
    premium = _fetch_json(_url(clean_base, "/fapi/v3/premiumIndex", {"symbol": symbol}), timeout_seconds)
    ticker_payload = ticker.get("payload") if ticker.get("ok") else {}
    book_payload = book.get("payload") if book.get("ok") else {}
    premium_payload = premium.get("payload") if premium.get("ok") else {}
    return {
        "endpoint_status": {
            "ticker_24h": ticker.get("status"),
            "book_ticker": book.get("status"),
            "premium_index": premium.get("status"),
        },
        "last_price": _as_float(ticker_payload.get("lastPrice")) if isinstance(ticker_payload, dict) else None,
        "quote_volume_24h": _as_float(ticker_payload.get("quoteVolume")) if isinstance(ticker_payload, dict) else None,
        "trade_count_24h": ticker_payload.get("count") if isinstance(ticker_payload, dict) else None,
        "best_bid": _as_float(book_payload.get("bidPrice")) if isinstance(book_payload, dict) else None,
        "best_ask": _as_float(book_payload.get("askPrice")) if isinstance(book_payload, dict) else None,
        "mark_price": _as_float(premium_payload.get("markPrice")) if isinstance(premium_payload, dict) else None,
        "index_price": _as_float(premium_payload.get("indexPrice")) if isinstance(premium_payload, dict) else None,
        "funding_rate": _as_float(premium_payload.get("lastFundingRate")) if isinstance(premium_payload, dict) else None,
    }


def get_aster_ws_forward_monitor_preview(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    use_combined_stream: bool = True,
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

    clean_symbol = _clean_symbol(symbol)
    lower = clean_symbol.lower()
    clean_interval = "".join(ch for ch in str(interval or "1m") if ch.isalnum())[:8] or "1m"
    safe_timeout = max(1, min(int(timeout_seconds or 8), 15))
    streams = [f"{lower}@aggTrade", f"{lower}@kline_{clean_interval}", f"{lower}@depth5@500ms", "!markPrice@arr@1s"]

    rest = _rest_snapshot(clean_symbol, safe_timeout)
    if use_combined_stream:
        ws = _combined_stream_read(streams, safe_timeout, expected=4)
        by_stream = {str(row.get("stream") or ""): row.get("data") for row in ws.get("events") or []}
        ws_rows = [
            {"stream": stream, "status": "ok" if stream in by_stream else "missing_in_window", "payload": by_stream.get(stream)}
            for stream in streams
        ]
        for index, row in enumerate(list(ws_rows)):
            if row.get("status") == "ok":
                continue
            fallback = _ws_read_one(row["stream"], safe_timeout)
            if fallback.get("ok"):
                ws_rows[index] = {
                    "stream": row["stream"],
                    "status": "ok",
                    "payload": fallback.get("payload"),
                    "fallback_individual": True,
                    "fallback_latency_ms": fallback.get("latency_ms"),
                }
    else:
        ws_rows = [_ws_read_one(stream, safe_timeout) for stream in streams]
        ws = {
            "ok": all(row.get("ok") for row in ws_rows),
            "status": "ok" if all(row.get("ok") for row in ws_rows) else "partial",
            "latency_ms": round(sum(float(row.get("latency_ms") or 0) for row in ws_rows), 2),
        }

    payload_by_stream = {row["stream"]: row.get("payload") for row in ws_rows}
    trade = _extract_trade(payload_by_stream.get(f"{lower}@aggTrade"))
    kline = _extract_kline(payload_by_stream.get(f"{lower}@kline_{clean_interval}"))
    depth = _extract_depth(payload_by_stream.get(f"{lower}@depth5@500ms"))
    mark = _extract_mark_arr(payload_by_stream.get("!markPrice@arr@1s"), clean_symbol)

    ws_trade_price = trade.get("price")
    rest_last_price = rest.get("last_price")
    price_delta_bps = None
    if ws_trade_price is not None and rest_last_price:
        price_delta_bps = ((ws_trade_price - rest_last_price) / rest_last_price) * 10_000
    ws_mark = mark.get("mark_price")
    rest_mark = rest.get("mark_price")
    mark_delta_bps = None
    if ws_mark is not None and rest_mark:
        mark_delta_bps = ((ws_mark - rest_mark) / rest_mark) * 10_000

    failed_streams = [row for row in ws_rows if row.get("status") not in {"ok"}]
    return {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source_policy": "public_ws_vs_public_rest_forward_preview",
        "symbol": clean_symbol,
        "streams": streams,
        "use_combined_stream": use_combined_stream,
        "health_status": "active" if not failed_streams and ws.get("ok") else "degraded",
        "ws_summary": {
            "status": ws.get("status"),
            "latency_ms": ws.get("latency_ms"),
            "streams_received": sum(1 for row in ws_rows if row.get("status") == "ok"),
            "streams_expected": len(streams),
        },
        "rest_snapshot": rest,
        "ws_snapshot": {
            "trade": trade,
            "kline": kline,
            "depth": depth,
            "mark_index": mark,
        },
        "consistency": {
            "ws_trade_vs_rest_last_price_bps": round(price_delta_bps, 6) if price_delta_bps is not None else None,
            "ws_mark_vs_rest_mark_bps": round(mark_delta_bps, 6) if mark_delta_bps is not None else None,
        },
        "stream_rows": [
            {key: value for key, value in row.items() if key != "payload"}
            for row in ws_rows
        ],
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
