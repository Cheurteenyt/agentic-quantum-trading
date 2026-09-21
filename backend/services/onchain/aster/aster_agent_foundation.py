from __future__ import annotations
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any
from services.onchain.behavioral_evidence_bridge import (
    get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview,
)
ASTER_REST_BASE_URL = "https://fapi.asterdex.com"
ASTER_WS_URL = "wss://fstream.asterdex.com/ws"
BSC_RPC_URL = "https://bsc-dataseed.binance.org/"
BSC_USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
try:  # Optional dependency in this project environment.
    from eth_account import Account  # type: ignore
    from eth_account.messages import encode_defunct  # type: ignore
except Exception:  # pragma: no cover - depends on local env.
    Account = None
    encode_defunct = None
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
def _audit(component: str, event: str, status: str, **extra: Any) -> dict[str, Any]:
    safe_extra = {k: v for k, v in extra.items() if "key" not in k.lower() and "secret" not in k.lower()}
    return {"ts": _now(), "component": component, "event": event, "status": status, **safe_extra}
def _clean_address(value: Any) -> str:
    clean = str(value or "").strip()
    if ADDRESS_RE.match(clean) or (clean.lower().startswith("0x") and len(clean) == 42 and all(c in "0123456789abcdefABCDEF" for c in clean[2:])):
        return "0x" + clean[2:].lower()
    return ""
def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(parsed, high))
def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
def _parse_csv(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw = [str(item or "").strip() for item in value]
    else:
        raw = [item.strip() for item in str(value or "").split(",")]
    parsed = [item.upper() for item in raw if item]
    return parsed or default
def _json_request(url: str, timeout_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "CoreEquityAsterAgent/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read()
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            payload = json.loads(raw.decode("utf-8")) if raw else None
            return {
                "status": "ok",
                "http_status": int(response.status),
                "latency_ms": latency_ms,
                "payload": payload,
                "rate_limit_headers": {
                    key: response.headers.get(key)
                    for key in ("x-mbx-used-weight-1m", "x-ratelimit-limit", "x-ratelimit-remaining", "retry-after")
                    if response.headers.get(key) is not None
                },
            }
    except urllib.error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "status": "rate_limited" if exc.code == 429 else "not_found" if exc.code == 404 else "http_error",
            "http_status": int(exc.code),
            "latency_ms": latency_ms,
            "rate_limit_headers": {"retry-after": exc.headers.get("retry-after")} if exc.headers.get("retry-after") else {},
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {"status": "request_failed", "latency_ms": latency_ms, "error": type(exc).__name__}
def _post_rpc(url: str, method: str, params: list[Any], timeout_seconds: int) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "CoreEquityAsterAgent/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if "error" in payload:
                return {"status": "rpc_error", "error": payload.get("error")}
            return {"status": "ok", "result": payload.get("result")}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "request_failed", "error": type(exc).__name__}
def _probe_rest(base_url: str, symbol: str, timeout_seconds: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = base_url.rstrip("/")
    endpoints = [
        ("ping", f"{base}/fapi/v1/ping"),
        ("server_time", f"{base}/fapi/v1/time"),
        ("exchange_info", f"{base}/fapi/v1/exchangeInfo"),
        ("recent_trades", f"{base}/fapi/v1/trades?symbol={urllib.parse.quote(symbol)}&limit=10"),
        ("ticker_24h", f"{base}/fapi/v1/ticker/24hr?symbol={urllib.parse.quote(symbol)}"),
        ("book_ticker", f"{base}/fapi/v1/ticker/bookTicker?symbol={urllib.parse.quote(symbol)}"),
    ]
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for name, url in endpoints:
        result = _json_request(url, timeout_seconds)
        payload = result.pop("payload", None)
        rows.append(
            {
                "name": name,
                "url": url,
                **result,
                "data_shape": _payload_shape(payload),
                "sample": _payload_sample(payload),
            }
        )
        audit.append(_audit("aster_api_explorer", name, str(result.get("status")), latency_ms=result.get("latency_ms")))
    return rows, audit
def _payload_shape(payload: Any) -> str:
    if isinstance(payload, list):
        return f"list[{len(payload)}]"
    if isinstance(payload, dict):
        return "object:" + ",".join(sorted(str(k) for k in list(payload.keys())[:8]))
    if payload is None:
        return "empty"
    return type(payload).__name__
def _payload_sample(payload: Any) -> Any:
    if isinstance(payload, list):
        return payload[:2]
    if isinstance(payload, dict):
        return {k: payload.get(k) for k in list(payload.keys())[:8]}
    return payload
def _probe_websocket(ws_url: str, timeout_seconds: int) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(ws_url)
    host = parsed.hostname
    port = parsed.port or 443
    if not host:
        return {"status": "invalid_ws_url", "url": ws_url}
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return {
                "status": "tcp_reachable",
                "url": ws_url,
                "latency_ms": latency_ms,
                "note": "handshake_subscription_not_started_dry_run_only",
            }
    except OSError as exc:
        return {"status": "unreachable", "url": ws_url, "error": type(exc).__name__}
def _hex_to_int(value: Any) -> int:
    try:
        return int(str(value or "0x0"), 16)
    except ValueError:
        return 0
def _wallet_preview(timeout_seconds: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    audit: list[dict[str, Any]] = []
    key = os.getenv("ASTER_AGENT_PRIVATE_KEY", "").strip()
    rpc_url = os.getenv("ASTER_AGENT_BSC_RPC_URL", os.getenv("BSC_RPC_URL", BSC_RPC_URL)).strip() or BSC_RPC_URL
    if not key:
        audit.append(_audit("wallet_controller", "load_private_key", "missing_env"))
        return {
            "wallet_status": "private_key_missing",
            "env_var": "ASTER_AGENT_PRIVATE_KEY",
            "private_key_logged": False,
            "can_sign_message": False,
        }, audit
    if Account is None or encode_defunct is None:
        audit.append(_audit("wallet_controller", "optional_dependency", "eth_account_missing"))
        return {
            "wallet_status": "eth_account_dependency_missing",
            "private_key_logged": False,
            "can_sign_message": False,
            "dependency": "eth_account",
        }, audit
    try:
        account = Account.from_key(key)
        address = account.address
        checksum_valid = bool(ADDRESS_RE.match(address)) and address != address.lower() and address != address.upper()
        native = _post_rpc(rpc_url, "eth_getBalance", [address, "latest"], timeout_seconds)
        usdt_raw = _erc20_balance(rpc_url, BSC_USDT_ADDRESS, address, timeout_seconds)
        message = f"Core Equity Aster Agent read-only wallet check {_now()}"
        signed = Account.sign_message(encode_defunct(text=message), private_key=key)
        audit.append(_audit("wallet_controller", "wallet_preview", "ok", address=address))
        return {
            "wallet_status": "ok",
            "address": address,
            "checksum_valid": checksum_valid,
            "bnb_balance_wei": str(_hex_to_int(native.get("result"))) if native.get("status") == "ok" else None,
            "bnb_balance_status": native.get("status"),
            "usdt_balance_raw": str(usdt_raw.get("balance_raw")) if usdt_raw.get("status") == "ok" else None,
            "usdt_balance_status": usdt_raw.get("status"),
            "usdt_contract": BSC_USDT_ADDRESS,
            "signature_preview": {
                "message": message,
                "signature": signed.signature.hex(),
                "signed_transaction": False,
            },
            "private_key_logged": False,
            "can_sign_message": True,
        }, audit
    except Exception as exc:
        audit.append(_audit("wallet_controller", "wallet_preview", "failed", error=type(exc).__name__))
        return {"wallet_status": "failed", "error": type(exc).__name__, "private_key_logged": False, "can_sign_message": False}, audit
def _erc20_balance(rpc_url: str, token: str, wallet: str, timeout_seconds: int) -> dict[str, Any]:
    data = "0x70a08231" + wallet[2:].lower().rjust(64, "0")
    result = _post_rpc(rpc_url, "eth_call", [{"to": token, "data": data}, "latest"], timeout_seconds)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "balance_raw": _hex_to_int(result.get("result"))}
def _listener_preview(rest_base_url: str, symbol: str, max_swaps: int, timeout_seconds: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    url = f"{rest_base_url.rstrip('/')}/fapi/v1/trades?symbol={urllib.parse.quote(symbol)}&limit={max_swaps}"
    result = _json_request(url, timeout_seconds)
    payload = result.pop("payload", None)
    swaps: list[dict[str, Any]] = []
    if result.get("status") == "ok" and isinstance(payload, list):
        for row in payload[:max_swaps]:
            if not isinstance(row, dict):
                continue
            swaps.append(
                {
                    "timestamp": row.get("time"),
                    "symbol": symbol,
                    "amount": row.get("qty"),
                    "price": row.get("price"),
                    "wallet_addresses": [],
                    "wallet_note": "centralized_orderbook_trade_no_onchain_wallets_in_public_trade_feed",
                }
            )
    status = "ready" if swaps else str(result.get("status") or "blocked")
    return {
        "listener_status": status,
        "mode": "single_poll_dry_run",
        "symbol": symbol,
        "request_url": url,
        "swaps_returned": len(swaps),
        "swaps": swaps,
        "websocket_subscription_started": False,
    }, [_audit("real_time_listener", "recent_swaps_poll", status, swaps_returned=len(swaps))]
def _order_book_snapshot(rest_base_url: str, symbol: str, depth_limit: int, timeout_seconds: int) -> dict[str, Any]:
    url = f"{rest_base_url.rstrip('/')}/fapi/v1/depth?symbol={urllib.parse.quote(symbol)}&limit={depth_limit}"
    result = _json_request(url, timeout_seconds)
    payload = result.pop("payload", None)
    if result.get("status") != "ok" or not isinstance(payload, dict):
        return {"symbol": symbol, "snapshot_status": result.get("status"), "request_url": url, **result}
    return {
        "symbol": symbol,
        "snapshot_status": "ok",
        "request_url": url,
        "captured_at": _now(),
        "last_update_id": payload.get("lastUpdateId"),
        "bids": payload.get("bids") or [],
        "asks": payload.get("asks") or [],
        **result,
    }
def _depth_rows_value(rows: list[Any]) -> tuple[float, float]:
    total = 0.0
    largest = 0.0
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        notional = _as_float(row[0]) * _as_float(row[1])
        total += notional
        largest = max(largest, notional)
    return total, largest
def _order_book_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    bids = snapshot.get("bids") if isinstance(snapshot.get("bids"), list) else []
    asks = snapshot.get("asks") if isinstance(snapshot.get("asks"), list) else []
    best_bid = _as_float((bids[0] if bids else [0])[0])
    best_ask = _as_float((asks[0] if asks else [0])[0])
    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
    bid_depth, bid_largest = _depth_rows_value(bids[:20])
    ask_depth, ask_largest = _depth_rows_value(asks[:20])
    total_depth = bid_depth + ask_depth
    spread_pct = ((best_ask - best_bid) / mid * 100) if mid else 0.0
    imbalance = abs(bid_depth - ask_depth) / total_depth if total_depth else 0.0
    concentration = max(bid_largest, ask_largest) / total_depth if total_depth else 0.0
    score = min(100.0, (imbalance * 55.0) + (concentration * 35.0) + min(10.0, spread_pct * 5.0))
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_pct": round(spread_pct, 6),
        "top20_bid_depth_usd": round(bid_depth, 2),
        "top20_ask_depth_usd": round(ask_depth, 2),
        "depth_imbalance": round(imbalance, 6),
        "order_concentration": round(concentration, 6),
        "order_book_anomaly_score": round(score, 2),
    }
def _ticker_metrics(rest_base_url: str, symbol: str, timeout_seconds: int) -> dict[str, Any]:
    url = f"{rest_base_url.rstrip('/')}/fapi/v1/ticker/24hr?symbol={urllib.parse.quote(symbol)}"
    result = _json_request(url, timeout_seconds)
    payload = result.pop("payload", None)
    if result.get("status") != "ok" or not isinstance(payload, dict):
        return {"volume_status": result.get("status"), "request_url": url, "volume_anomaly_score": 0, **result}
    quote_volume = _as_float(payload.get("quoteVolume"))
    trade_count = _as_float(payload.get("count"))
    price_change_pct = abs(_as_float(payload.get("priceChangePercent")))
    # Aster public 24h ticker does not expose a 7d baseline, so this is a baseline-aware preview.
    score = min(100.0, min(55.0, quote_volume / 1_000_000.0) + min(25.0, trade_count / 20_000.0) + min(20.0, price_change_pct))
    return {
        "volume_status": "ok",
        "request_url": url,
        "volume_24h_usd": round(quote_volume, 2),
        "trade_count_24h": int(trade_count),
        "price_change_24h_pct_abs": round(price_change_pct, 4),
        "volume_spike_ratio": None,
        "baseline_status": "seven_day_average_not_available_from_public_24h_ticker",
        "volume_anomaly_score": round(score, 2),
    }
def _order_flow_metrics(rest_base_url: str, symbol: str, max_trades: int, timeout_seconds: int) -> dict[str, Any]:
    url = f"{rest_base_url.rstrip('/')}/fapi/v1/trades?symbol={urllib.parse.quote(symbol)}&limit={max_trades}"
    result = _json_request(url, timeout_seconds)
    payload = result.pop("payload", None)
    if result.get("status") != "ok" or not isinstance(payload, list):
        return {"order_flow_status": result.get("status"), "request_url": url, "order_flow_anomaly_score": 0, **result}
    rows = [row for row in payload if isinstance(row, dict)]
    buys = sum(1 for row in rows if not bool(row.get("isBuyerMaker")))
    sells = sum(1 for row in rows if bool(row.get("isBuyerMaker")))
    sizes = [_as_float(row.get("qty")) for row in rows]
    notionals = [_as_float(row.get("qty")) * _as_float(row.get("price")) for row in rows]
    times = [_as_float(row.get("time")) for row in rows if row.get("time") is not None]
    intervals = [abs(times[i] - times[i - 1]) for i in range(1, len(times))]
    buy_sell_ratio = buys / max(1, sells)
    avg_notional = sum(notionals) / max(1, len(notionals))
    largest_share = max(notionals or [0]) / max(1.0, sum(notionals))
    repeated_sizes = len(sizes) - len({round(size, 8) for size in sizes})
    regularity = 1.0 / max(1.0, (max(intervals or [1]) - min(intervals or [1])))
    wash_like = min(1.0, (repeated_sizes / max(1, len(rows))) + min(0.4, regularity))
    score = min(100.0, min(35.0, abs(buy_sell_ratio - 1.0) * 18.0) + min(35.0, largest_share * 80.0) + (wash_like * 30.0))
    return {
        "order_flow_status": "ok",
        "request_url": url,
        "trades_analyzed": len(rows),
        "aggressive_buys": buys,
        "aggressive_sells": sells,
        "buy_sell_ratio": round(buy_sell_ratio, 6),
        "avg_trade_notional_usd": round(avg_notional, 2),
        "largest_trade_share": round(largest_share, 6),
        "wash_like_repetition_ratio": round(wash_like, 6),
        "order_flow_anomaly_score": round(score, 2),
    }
def _dex_behavioral_score(token_address: str, chain: str) -> dict[str, Any]:
    token = _clean_address(token_address)
    if not token:
        return {"dex_behavioral_status": "token_address_missing", "behavioral_score": None}
    preview = get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
        chain=chain,
        limit=5,
        dry_run=True,
        token_addresses=[token],
    )
    scores = [
        int(row.get("behavioral_anomaly_score") or 0)
        for row in (preview.get("scored_candidates") or [])
        if _clean_address(row.get("target_token")) == token
    ]
    return {
        "dex_behavioral_status": "found" if scores else "not_found_in_local_context",
        "behavioral_score": max(scores) if scores else None,
        "candidates_scored": preview.get("candidates_scored"),
    }
def get_aster_order_book_anomaly_detection_test(
    symbols: str | list[str] | None = "BTCUSDT",
    token_addresses: str | list[str] | None = None,
    chain: str | None = "bsc",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 5,
    max_snapshots_per_symbol: int = 1,
    snapshot_interval_ms: int = 0,
    depth_limit: int = 100,
) -> dict[str, Any]:
    safe_timeout = _safe_int(timeout_seconds, 8, 1, 10)
    safe_symbols = _parse_csv(symbols, ["BTCUSDT"])[: _safe_int(max_symbols, 5, 1, 5)]
    safe_snapshots = _safe_int(max_snapshots_per_symbol, 1, 1, 10)
    safe_interval = _safe_int(snapshot_interval_ms, 0, 0, 30_000)
    safe_depth = _safe_int(depth_limit, 100, 5, 100)
    clean_chain = str(chain or "bsc").strip().lower()
    rest_base = os.getenv("ASTER_AGENT_REST_BASE_URL", ASTER_REST_BASE_URL).strip() or ASTER_REST_BASE_URL
    disabled = {"source_policy": "aster_order_book_anomaly_read_only_phase_2", "would_execute_trade": False, "would_send_transaction": False, "would_write_db": False, "would_create_client_signal": False, "would_create_label": False, "would_create_mapping": False, "writes_performed": 0}
    if not dry_run:
        return {"ok": False, "dry_run": False, "detection_status": "blocked", "blockers": ["dry_run_required"], **disabled}
    token_list = [_clean_address(item) for item in _parse_csv(token_addresses, [])]
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for index, symbol in enumerate(safe_symbols):
        snapshots = []
        for snap_index in range(safe_snapshots):
            if safe_interval and snap_index:
                time.sleep(safe_interval / 1000)
            snapshot = _order_book_snapshot(rest_base, symbol, safe_depth, safe_timeout)
            metrics = _order_book_metrics(snapshot) if snapshot.get("snapshot_status") == "ok" else {"order_book_anomaly_score": 0}
            snapshots.append({"snapshot_status": snapshot.get("snapshot_status"), "captured_at": snapshot.get("captured_at"), "metrics": metrics})
        latest_metrics = snapshots[-1]["metrics"] if snapshots else {"order_book_anomaly_score": 0}
        volume = _ticker_metrics(rest_base, symbol, safe_timeout)
        flow = _order_flow_metrics(rest_base, symbol, 100, safe_timeout)
        aster_score = (
            _as_float(latest_metrics.get("order_book_anomaly_score")) * 0.4
            + _as_float(volume.get("volume_anomaly_score")) * 0.3
            + _as_float(flow.get("order_flow_anomaly_score")) * 0.3
        )
        dex_context = _dex_behavioral_score(token_list[index], clean_chain) if index < len(token_list) and token_list[index] else {"dex_behavioral_status": "not_requested", "behavioral_score": None}
        behavioral = dex_context.get("behavioral_score")
        combined = ((aster_score * 0.5) + (_as_float(behavioral) * 0.5)) if behavioral is not None else aster_score
        row = {
            "symbol": symbol,
            "token_address": token_list[index] if index < len(token_list) and token_list[index] else None,
            "snapshots_collected": len(snapshots),
            "order_book_snapshots": snapshots,
            "volume_anomaly": volume,
            "order_flow_anomaly": flow,
            "aster_anomaly_score": round(aster_score, 2),
            "dex_behavioral_context": dex_context,
            "combined_anomaly_score": round(combined, 2),
            "suspicious": bool(combined >= 70),
        }
        rows.append(row)
        audit.append(_audit("aster_order_book_anomaly", "symbol_scored", "ready", symbol=symbol, combined_anomaly_score=row["combined_anomaly_score"]))
    return {
        "ok": True,
        "dry_run": True,
        "detection_status": "ready" if rows else "blocked",
        "rest_base_url": rest_base,
        "chain": clean_chain,
        "symbols_checked": len(rows),
        "suspicious_count": sum(1 for row in rows if row.get("suspicious")),
        "results": rows,
        "audit_events": audit,
        "blockers": [] if rows else ["no_symbols_supplied"],
        **disabled,
    }
def get_aster_agent_foundation_test(
    symbol: str | None = "BTCUSDT",
    pool_address: str | None = None,
    chain: str | None = "bsc",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_swaps: int = 10,
) -> dict[str, Any]:
    safe_timeout = _safe_int(timeout_seconds, 8, 1, 10)
    safe_max_swaps = _safe_int(max_swaps, 10, 1, 10)
    clean_symbol = str(symbol or os.getenv("ASTER_AGENT_TEST_SYMBOL", "BTCUSDT")).strip().upper() or "BTCUSDT"
    clean_chain = str(chain or "bsc").strip().lower()
    rest_base = os.getenv("ASTER_AGENT_REST_BASE_URL", ASTER_REST_BASE_URL).strip() or ASTER_REST_BASE_URL
    ws_url = os.getenv("ASTER_AGENT_WS_URL", ASTER_WS_URL).strip() or ASTER_WS_URL
    disabled = {"source_policy": "aster_agent_foundation_read_only_phase_1", "would_create_trade": False, "would_execute_trade": False, "would_send_transaction": False, "would_write_db": False, "would_create_signal": False, "would_create_label": False, "would_create_mapping": False, "writes_performed": 0}
    if not dry_run:
        return {"ok": False, "dry_run": False, "foundation_status": "blocked", "blockers": ["dry_run_required"], **disabled}
    api_rows, api_audit = _probe_rest(rest_base, clean_symbol, safe_timeout)
    websocket = _probe_websocket(ws_url, safe_timeout)
    wallet, wallet_audit = _wallet_preview(safe_timeout)
    listener, listener_audit = _listener_preview(rest_base, clean_symbol, safe_max_swaps, safe_timeout)
    latencies = [float(row.get("latency_ms") or 0) for row in api_rows if row.get("latency_ms") is not None]
    pool = _clean_address(pool_address)
    data_available = {
        "recent_swaps": listener.get("swaps_returned", 0) > 0,
        "liquidity": any(row.get("name") in {"book_ticker", "ticker_24h"} and row.get("status") == "ok" for row in api_rows),
        "token_info": any(row.get("name") == "exchange_info" and row.get("status") == "ok" for row in api_rows),
        "websocket_tcp_reachable": websocket.get("status") == "tcp_reachable",
        "pool_address_supported": bool(pool),
    }
    return {
        "ok": True,
        "dry_run": True,
        "foundation_status": "ready",
        "chain": clean_chain,
        "symbol": clean_symbol,
        "pool_address": pool or None,
        "api_explorer": {
            "rest_base_url": rest_base,
            "endpoints_tested": api_rows,
            "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "data_available": data_available,
            "rate_limit_observed": any(row.get("status") == "rate_limited" for row in api_rows),
        },
        "websocket_probe": websocket,
        "wallet_controller": wallet,
        "real_time_event_listener": listener,
        "audit_events": api_audit + [_audit("websocket_probe", "tcp_probe", str(websocket.get("status")))] + wallet_audit + listener_audit,
        "blockers": [] if wallet.get("wallet_status") == "ok" else [str(wallet.get("wallet_status"))],
        **disabled,
    }
