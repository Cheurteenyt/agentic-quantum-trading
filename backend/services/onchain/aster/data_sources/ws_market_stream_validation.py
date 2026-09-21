from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
from datetime import datetime, timezone
from typing import Any


WS_HOST = "fstream.asterdex.com"
WS_BASE = f"wss://{WS_HOST}"
DEFAULT_STREAMS = "btcusdt@aggTrade,btcusdt@kline_1m,btcusdt@depth5@500ms,!markPrice@arr@1s"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_stream(value: Any) -> str:
    clean = str(value or "").strip()
    return "".join(ch for ch in clean if ch.isalnum() or ch in "@_!./").strip("/")[:128]


def _parse_streams(value: str | list[str] | None, limit: int) -> list[str]:
    raw = value if isinstance(value, list) else str(value or DEFAULT_STREAMS).split(",")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        stream = _clean_stream(item)
        if stream and stream not in seen:
            out.append(stream)
            seen.add(stream)
        if len(out) >= limit:
            break
    return out or ["btcusdt@aggTrade"]


def _read_until(sock: ssl.SSLSocket, marker: bytes, max_bytes: int = 8192) -> bytes:
    data = b""
    while marker not in data and len(data) < max_bytes:
        chunk = sock.recv(1024)
        if not chunk:
            break
        data += chunk
    return data


def _read_ws_frame(sock: ssl.SSLSocket, max_payload_bytes: int) -> bytes:
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


def _validate_payload(stream: str, payload: Any) -> tuple[bool, list[str], str]:
    lower = stream.lower()
    if "aggtrade" in lower:
        fields = ["e", "E", "s", "a", "p", "q", "T", "m"]
        return isinstance(payload, dict) and all(field in payload for field in fields), fields, "aggregate_trade_stream"
    if "kline" in lower:
        fields = ["e", "E", "s", "k"]
        return isinstance(payload, dict) and all(field in payload for field in fields), fields, "kline_stream"
    if "depth" in lower:
        fields = ["e", "E", "s", "b", "a"]
        return isinstance(payload, dict) and all(field in payload for field in fields), fields, "order_book_depth_stream"
    if "markprice" in lower:
        fields = ["e", "E", "s", "p", "i", "r", "T"]
        if isinstance(payload, list):
            first = payload[0] if payload else {}
            return isinstance(first, dict) and all(field in first for field in fields), fields, "mark_price_array_stream"
        return isinstance(payload, dict) and all(field in payload for field in fields), fields, "mark_price_stream"
    return payload is not None, [], "unknown_stream_shape"


def _probe_stream(stream: str, timeout_seconds: int, max_payload_bytes: int) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    path = f"/ws/{stream}"
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {WS_HOST}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "User-Agent: CoreEquityAsterWsValidation/0.1\r\n\r\n"
    )
    sock: ssl.SSLSocket | None = None
    try:
        raw_sock = socket.create_connection((WS_HOST, 443), timeout=timeout_seconds)
        sock = ssl.create_default_context().wrap_socket(raw_sock, server_hostname=WS_HOST)
        sock.settimeout(timeout_seconds)
        sock.sendall(request.encode("ascii"))
        response = _read_until(sock, b"\r\n\r\n")
        status_line = response.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
        if "101" not in status_line:
            return {
                "stream": stream,
                "url": f"{WS_BASE}{path}",
                "fetch_status": "handshake_failed",
                "http_status_line": status_line,
                "schema_ok": False,
            }
        payload_raw = _read_ws_frame(sock, max_payload_bytes)
        payload_text = payload_raw.decode("utf-8", errors="replace")
        payload = json.loads(payload_text)
        schema_ok, expected_fields, stream_type = _validate_payload(stream, payload)
        latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        sample = payload[0] if isinstance(payload, list) and payload else payload
        return {
            "stream": stream,
            "url": f"{WS_BASE}{path}",
            "fetch_status": "ok",
            "http_status_line": status_line,
            "latency_ms": round(latency_ms, 2),
            "stream_type": stream_type,
            "schema_ok": schema_ok,
            "expected_fields": expected_fields,
            "payload_kind": type(payload).__name__,
            "array_count": len(payload) if isinstance(payload, list) else None,
            "sample_fields": sorted(sample.keys()) if isinstance(sample, dict) else [],
            "sample_digest": hashlib.sha256(payload_raw).hexdigest(),
        }
    except (OSError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
        return {
            "stream": stream,
            "url": f"{WS_BASE}{path}",
            "fetch_status": "failed",
            "schema_ok": False,
            "error": type(exc).__name__,
            "error_message": str(exc)[:240],
        }
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def get_aster_ws_market_stream_validation_preview(
    streams: str | list[str] | None = DEFAULT_STREAMS,
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_streams: int = 4,
    max_payload_bytes: int = 1_000_000,
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
    safe_max_streams = max(1, min(int(max_streams or 4), 8))
    safe_payload = max(1_024, min(int(max_payload_bytes or 1_000_000), 2_000_000))
    safe_streams = _parse_streams(streams, safe_max_streams)
    rows = [_probe_stream(stream, safe_timeout, safe_payload) for stream in safe_streams]
    validated = [row for row in rows if row.get("fetch_status") == "ok" and row.get("schema_ok")]
    failed = [row for row in rows if row not in validated]
    return {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source_policy": "official_public_websocket_validation_only",
        "base_url": WS_BASE,
        "streams": safe_streams,
        "summary": {
            "streams_tested": len(rows),
            "validated_streams": len(validated),
            "failed_or_schema_mismatch": len(failed),
        },
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
