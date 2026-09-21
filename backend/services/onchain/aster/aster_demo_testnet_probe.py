from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


TESTNET_FAPI_V3_BASE_URL = "https://fapi.asterdex-testnet.com"
MAINNET_FAPI_V3_BASE_URL = "https://fapi.asterdex.com"
PROJECT_BACKEND_ENV = Path(__file__).resolve().parents[3] / ".env"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


def _url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    return f"{base_url.rstrip('/')}{path}" + (f"?{query}" if query else "")


def _fetch_json(url: str, timeout_seconds: int, headers: dict[str, str] | None = None) -> dict[str, Any]:
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 15))
    request = urllib.request.Request(url, headers={"User-Agent": "CoreEquityAsterDemoProbe/1.0", **(headers or {})})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=safe_timeout) as response:
            text = response.read().decode("utf-8")
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            return {"ok": False, "status": "invalid_json", "latency_ms": latency_ms}
        return {"ok": True, "status": "ready", "latency_ms": latency_ms, "payload": payload}
    except urllib.error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        status = "rate_limited" if exc.code == 429 else "blocked_by_aster" if exc.code == 403 else "http_error"
        body = ""
        try:
            body = exc.read().decode("utf-8")[:300]
        except Exception:
            body = ""
        return {"ok": False, "status": status, "http_status": exc.code, "latency_ms": latency_ms, "error_preview": body}
    except (urllib.error.URLError, TimeoutError) as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        return {"ok": False, "status": "request_failed", "latency_ms": latency_ms, "error_preview": str(exc)[:300]}


def _fetch_exchange_info_symbol(base_url: str, symbol: str, timeout_seconds: int) -> dict[str, Any]:
    result = _fetch_json(_url(base_url, "/fapi/v3/exchangeInfo", {"symbol": symbol}), timeout_seconds)
    payload = result.get("payload")
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("symbols") or []
    row = next((item for item in rows if isinstance(item, dict) and str(item.get("symbol") or "").upper() == symbol), None)
    return {**result, "symbol_row": row}


def _filter_map(symbol_row: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(symbol_row, dict):
        return {}
    return {str(item.get("filterType") or ""): item for item in symbol_row.get("filters") or [] if isinstance(item, dict)}


def _load_backend_env_if_present() -> dict[str, Any]:
    loaded_keys: list[str] = []
    if not PROJECT_BACKEND_ENV.exists():
        return {"env_file": str(PROJECT_BACKEND_ENV), "env_file_exists": False, "loaded_keys": loaded_keys}
    try:
        lines = PROJECT_BACKEND_ENV.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"env_file": str(PROJECT_BACKEND_ENV), "env_file_exists": True, "loaded_keys": loaded_keys, "load_error": "read_failed"}
    allowed = {
        "ASTER_TESTNET_USER_ADDRESS",
        "ASTER_TESTNET_AGENT_ADDRESS",
        "ASTER_TESTNET_AGENT_PRIVATE_KEY",
        "ASTER_TESTNET_API_KEY",
        "ASTER_TESTNET_API_SECRET",
    }
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key not in allowed or os.getenv(key):
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value
        loaded_keys.append(key)
    return {"env_file": str(PROJECT_BACKEND_ENV), "env_file_exists": True, "loaded_keys": loaded_keys}


def _mask_address(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return f"{text[:6]}...{text[-4:]}" if len(text) > 12 else "***"


def _is_eth_address(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) != 42 or not text.startswith("0x"):
        return False
    try:
        int(text[2:], 16)
    except ValueError:
        return False
    return True


def _is_private_key_shape(value: str) -> bool:
    text = str(value or "").strip()
    if text.startswith("0x"):
        text = text[2:]
    if len(text) != 64:
        return False
    try:
        int(text, 16)
    except ValueError:
        return False
    return True


def _credentials_status() -> dict[str, Any]:
    _load_backend_env_if_present()
    api_key = os.getenv("ASTER_TESTNET_API_KEY", "").strip()
    api_secret = os.getenv("ASTER_TESTNET_API_SECRET", "").strip()
    user = os.getenv("ASTER_TESTNET_USER_ADDRESS", "").strip()
    signer = os.getenv("ASTER_TESTNET_AGENT_ADDRESS", "").strip()
    agent_private_key = os.getenv("ASTER_TESTNET_AGENT_PRIVATE_KEY", "").strip()
    return {
        "api_key_present": bool(api_key),
        "api_secret_present": bool(api_secret),
        "user_address_present": bool(user),
        "agent_address_present": bool(signer),
        "agent_private_key_present": bool(agent_private_key),
        "masked_user_address": _mask_address(user),
        "masked_agent_address": _mask_address(signer),
        "user_address_valid_shape": _is_eth_address(user),
        "agent_address_valid_shape": _is_eth_address(signer),
        "agent_private_key_valid_shape": _is_private_key_shape(agent_private_key),
        "credentials_ready": bool(
            user
            and signer
            and agent_private_key
            and _is_eth_address(user)
            and _is_eth_address(signer)
            and _is_private_key_shape(agent_private_key)
        ),
        "auth_model": "aster_v3_agent_wallet_eip712",
        "env_vars": [
            "ASTER_TESTNET_USER_ADDRESS",
            "ASTER_TESTNET_AGENT_ADDRESS",
            "ASTER_TESTNET_AGENT_PRIVATE_KEY",
        ],
    }


def _signed_query(secret: str, params: dict[str, Any]) -> str:
    query = urllib.parse.urlencode(params)
    signature = hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{query}&signature={signature}"


def _signed_read_only_probe(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    env_load = _load_backend_env_if_present()
    user = os.getenv("ASTER_TESTNET_USER_ADDRESS", "").strip()
    signer = os.getenv("ASTER_TESTNET_AGENT_ADDRESS", "").strip()
    agent_private_key = os.getenv("ASTER_TESTNET_AGENT_PRIVATE_KEY", "").strip()
    if not user or not signer or not agent_private_key:
        return {
            "ok": False,
            "status": "credentials_missing",
            "endpoint": "GET /fapi/v3/balance",
            "would_call_signed_user_data": False,
            "env_load": env_load,
        }
    if not _is_eth_address(user) or not _is_eth_address(signer):
        return {
            "ok": False,
            "status": "invalid_address_shape",
            "endpoint": "GET /fapi/v3/balance",
            "would_call_signed_user_data": False,
            "env_load": env_load,
            "masked_user_address": _mask_address(user),
            "masked_agent_address": _mask_address(signer),
        }
    if not _is_private_key_shape(agent_private_key):
        return {
            "ok": False,
            "status": "invalid_agent_private_key_shape",
            "endpoint": "GET /fapi/v3/balance",
            "would_call_signed_user_data": False,
            "env_load": env_load,
            "hint": "ASTER_TESTNET_AGENT_PRIVATE_KEY must be the 32-byte private key, not the 20-byte agent wallet address.",
        }
    signature = _aster_v3_eip712_signature_preview(
        {"user": user, "signer": signer, "nonce": _microsecond_nonce()},
        agent_private_key,
    )
    if not signature.get("ok"):
        return {
            "ok": False,
            "status": signature.get("status"),
            "endpoint": "GET /fapi/v3/balance",
            "would_call_signed_user_data": False,
            "env_load": env_load,
            "signing_readiness": signature,
        }
    params = {
        "user": user,
        "signer": signer,
        "nonce": signature["nonce"],
        "signature": signature["signature"],
    }
    query = urllib.parse.urlencode(params)
    result = _fetch_json(f"{base_url.rstrip()}/fapi/v3/balance?{query}", timeout_seconds)
    payload = result.get("payload")
    redacted_assets = []
    if isinstance(payload, list):
        for row in payload[:10]:
            if not isinstance(row, dict):
                continue
            redacted_assets.append(
                {
                    "asset": row.get("asset"),
                    "balance_present": row.get("balance") is not None,
                    "available_balance_present": row.get("availableBalance") is not None,
                    "margin_available": row.get("marginAvailable"),
                }
            )
    return {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "endpoint": "GET /fapi/v3/balance",
        "latency_ms": result.get("latency_ms"),
        "http_status": result.get("http_status"),
        "error_preview": result.get("error_preview"),
        "redacted_asset_rows": redacted_assets,
        "would_call_signed_user_data": True,
        "auth_model": "aster_v3_agent_wallet_eip712",
    }


def _microsecond_nonce() -> str:
    return str(int(time.time() * 1_000_000))


def _aster_v3_eip712_signature_preview(params: dict[str, Any], private_key: str) -> dict[str, Any]:
    try:
        from eth_account import Account  # type: ignore
        try:
            from eth_account.messages import encode_typed_data  # type: ignore
        except ImportError:
            from eth_account.messages import encode_structured_data as encode_typed_data  # type: ignore
    except Exception:
        return {
            "ok": False,
            "status": "eth_account_dependency_missing",
            "dependency_required": "eth-account",
            "safe_next_action": "install_dependency_only_after_user_approval_or_use_official_aster_mcp_signer",
            "private_key_loaded": bool(private_key),
        }
    nonce = str(params.get("nonce") or _microsecond_nonce())
    signing_params = {
        "user": str(params.get("user") or ""),
        "signer": str(params.get("signer") or ""),
        "nonce": nonce,
    }
    msg = urllib.parse.urlencode(signing_params)
    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Message": [{"name": "msg", "type": "string"}],
        },
        "primaryType": "Message",
        "domain": {
            "name": "AsterSignTransaction",
            "version": "1",
            "chainId": 714,
            "verifyingContract": "0x0000000000000000000000000000000000000000",
        },
        "message": {"msg": msg},
    }
    try:
        try:
            message = encode_typed_data(full_message=typed_data)
        except TypeError:
            message = encode_typed_data(typed_data)
        signed = Account.sign_message(message, private_key=private_key)
    except Exception as exc:
        return {"ok": False, "status": "signature_failed", "error_preview": str(exc)[:200]}
    return {
        "ok": True,
        "status": "signature_ready",
        "nonce": nonce,
        "message_params": {**signing_params, "user": _mask_address(signing_params["user"]), "signer": _mask_address(signing_params["signer"])},
        "signature": signed.signature.hex(),
    }


def get_aster_demo_testnet_readiness_preview(
    symbol: str | None = "BTCUSDT",
    dry_run: bool = True,
    timeout_seconds: int = 10,
    include_signed_readonly_probe: bool = False,
) -> dict[str, Any]:
    safe_symbol = str(symbol or "BTCUSDT").strip().upper() or "BTCUSDT"
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 15))
    env_load = _load_backend_env_if_present()
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "readiness_status": "blocked",
            "blockers": ["dry_run_required_demo_testnet_probe_is_read_only"],
            "would_place_order": False,
            "would_execute_trade": False,
            "would_write": False,
            "writes_performed": 0,
        }

    public_checks = {
        "testnet_ping": _fetch_json(_url(TESTNET_FAPI_V3_BASE_URL, "/fapi/v3/ping"), safe_timeout),
        "testnet_time": _fetch_json(_url(TESTNET_FAPI_V3_BASE_URL, "/fapi/v3/time"), safe_timeout),
        "testnet_exchange_info": _fetch_json(_url(TESTNET_FAPI_V3_BASE_URL, "/fapi/v3/exchangeInfo"), safe_timeout),
        "testnet_book_ticker": _fetch_json(
            _url(TESTNET_FAPI_V3_BASE_URL, "/fapi/v3/ticker/bookTicker", {"symbol": safe_symbol}),
            safe_timeout,
        ),
        "mainnet_book_ticker_reference": _fetch_json(
            _url(MAINNET_FAPI_V3_BASE_URL, "/fapi/v3/ticker/bookTicker", {"symbol": safe_symbol}),
            safe_timeout,
        ),
    }
    credentials = _credentials_status()
    signed_probe = (
        _signed_read_only_probe(TESTNET_FAPI_V3_BASE_URL, safe_timeout)
        if include_signed_readonly_probe
        else {"ok": None, "status": "skipped", "would_call_signed_user_data": False}
    )
    public_ready = all(public_checks[name].get("ok") for name in ("testnet_ping", "testnet_time", "testnet_exchange_info"))
    symbol_public_ready = bool(public_checks["testnet_book_ticker"].get("ok"))
    blockers = []
    if not public_ready:
        blockers.append("testnet_public_api_not_ready")
    if not symbol_public_ready:
        blockers.append("symbol_not_available_on_testnet_or_public_ticker_failed")
    if include_signed_readonly_probe and not signed_probe.get("ok"):
        blockers.append("signed_readonly_user_data_not_ready")
    if not credentials.get("credentials_ready"):
        blockers.append("testnet_credentials_missing_for_balance_or_demo_execution")

    return {
        "ok": True,
        "dry_run": True,
        "generated_at": _now(),
        "readiness_status": "ready_for_demo_shadow_validation" if not blockers else "blocked_or_partial",
        "symbol": safe_symbol,
        "base_urls": {
            "testnet_futures_v3": TESTNET_FAPI_V3_BASE_URL,
            "mainnet_futures_v3_reference": MAINNET_FAPI_V3_BASE_URL,
        },
        "public_checks": {
            key: {k: value.get(k) for k in ("ok", "status", "latency_ms", "http_status", "error_preview")}
            for key, value in public_checks.items()
        },
        "credentials": credentials,
        "env_load": env_load,
        "signed_readonly_probe": signed_probe,
        "blockers": blockers,
        "next_steps": [
            "If credentials are missing, create Aster testnet/demo API credentials with no real funds.",
            "Run this preview with include_signed_readonly_probe=true to verify USER_DATA read-only balance.",
            "Only after read-only user data passes, add a dry-run order-payload validator; do not place orders yet.",
        ],
        "source_policy": "aster_demo_testnet_readiness_read_only",
        "would_place_order": False,
        "would_execute_trade": False,
        "would_send_transaction": False,
        "would_use_real_funds": False,
        "would_write": False,
        "writes_performed": 0,
    }


def get_aster_demo_order_intent_validator_preview(
    symbols: str | list[str] | None = None,
    side: str = "BUY",
    position_size_usd: float = 50.0,
    dry_run: bool = True,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    safe_symbols = []
    if isinstance(symbols, (list, tuple)):
        raw_symbols = symbols
    else:
        raw_symbols = str(symbols or "LABUSDT,INJUSDT,TIAUSDT,INTCUSDT").replace(";", ",").split(",")
    for item in raw_symbols:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in safe_symbols:
            safe_symbols.append(symbol)
    safe_symbols = safe_symbols[:10]
    safe_side = "SELL" if str(side or "").strip().upper() == "SELL" else "BUY"
    safe_notional = max(5.0, min(float(position_size_usd or 50.0), 1_000.0))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 15))
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "validator_status": "blocked",
            "blockers": ["dry_run_required_order_intent_validator_never_places_orders"],
            "would_place_order": False,
            "would_execute_trade": False,
            "would_write": False,
            "writes_performed": 0,
        }

    readiness = get_aster_demo_testnet_readiness_preview(
        safe_symbols[0] if safe_symbols else "BTCUSDT",
        dry_run=True,
        timeout_seconds=safe_timeout,
        include_signed_readonly_probe=True,
    )
    rows: list[dict[str, Any]] = []
    for symbol in safe_symbols:
        exchange = _fetch_exchange_info_symbol(TESTNET_FAPI_V3_BASE_URL, symbol, safe_timeout)
        ticker = _fetch_json(_url(TESTNET_FAPI_V3_BASE_URL, "/fapi/v3/ticker/bookTicker", {"symbol": symbol}), safe_timeout)
        symbol_row = exchange.get("symbol_row")
        filters = _filter_map(symbol_row)
        price_filter = filters.get("PRICE_FILTER") or {}
        lot_filter = filters.get("LOT_SIZE") or {}
        market_lot_filter = filters.get("MARKET_LOT_SIZE") or {}
        min_notional_filter = filters.get("MIN_NOTIONAL") or {}
        ticker_payload = ticker.get("payload") if isinstance(ticker.get("payload"), dict) else {}
        bid = _as_decimal(ticker_payload.get("bidPrice"))
        ask = _as_decimal(ticker_payload.get("askPrice"))
        reference_price = ask if safe_side == "BUY" else bid
        tick_size = _as_decimal(price_filter.get("tickSize"))
        step_size = _as_decimal(lot_filter.get("stepSize") or market_lot_filter.get("stepSize"))
        min_qty = _as_decimal(lot_filter.get("minQty") or market_lot_filter.get("minQty"))
        min_notional = _as_decimal(min_notional_filter.get("notional"))
        raw_qty = Decimal(str(safe_notional)) / reference_price if reference_price > 0 else Decimal("0")
        rounded_qty = _floor_to_step(raw_qty, step_size)
        rounded_price = _floor_to_step(reference_price, tick_size)
        rounded_notional = rounded_qty * rounded_price
        blockers: list[str] = []
        warnings: list[str] = []
        if not exchange.get("ok") or not isinstance(symbol_row, dict):
            blockers.append("symbol_not_found_on_testnet_exchange_info")
        if not ticker.get("ok") or reference_price <= 0:
            blockers.append("book_ticker_unavailable")
        if str((symbol_row or {}).get("status") or "").upper() not in {"", "TRADING"}:
            blockers.append("symbol_not_trading")
        if rounded_qty <= 0:
            blockers.append("rounded_quantity_zero")
        if min_qty > 0 and rounded_qty < min_qty:
            blockers.append("quantity_below_min_qty")
        if min_notional > 0 and rounded_notional < min_notional:
            blockers.append("notional_below_min_notional")
        if tick_size <= 0:
            warnings.append("missing_or_zero_tick_size")
        if step_size <= 0:
            warnings.append("missing_or_zero_step_size")
        order_intent = {
            "symbol": symbol,
            "side": safe_side,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": _decimal_text(rounded_qty),
            "price": _decimal_text(rounded_price),
            "notional_estimate_usd": _decimal_text(rounded_notional),
        }
        rows.append(
            {
                "symbol": symbol,
                "validator_verdict": "blocked" if blockers else ("warning" if warnings else "order_intent_shape_ok"),
                "blockers": blockers,
                "warnings": warnings,
                "exchange_status": exchange.get("status"),
                "ticker_status": ticker.get("status"),
                "symbol_status": (symbol_row or {}).get("status") if isinstance(symbol_row, dict) else None,
                "bid": _decimal_text(bid),
                "ask": _decimal_text(ask),
                "tick_size": _decimal_text(tick_size),
                "step_size": _decimal_text(step_size),
                "min_qty": _decimal_text(min_qty),
                "min_notional": _decimal_text(min_notional),
                "requested_notional_usd": round(safe_notional, 6),
                "order_intent": order_intent,
            }
        )

    return {
        "ok": True,
        "dry_run": True,
        "validator_status": "ready",
        "auth_readiness": {
            "readiness_status": readiness.get("readiness_status"),
            "blockers": readiness.get("blockers"),
            "signed_status": (readiness.get("signed_readonly_probe") or {}).get("status"),
            "credentials": readiness.get("credentials"),
        },
        "symbols_checked": safe_symbols,
        "side": safe_side,
        "position_size_usd": safe_notional,
        "results": rows,
        "summary": {
            "ok_count": sum(1 for row in rows if row.get("validator_verdict") == "order_intent_shape_ok"),
            "warning_count": sum(1 for row in rows if row.get("validator_verdict") == "warning"),
            "blocked_count": sum(1 for row in rows if row.get("validator_verdict") == "blocked"),
        },
        "source_policy": "aster_demo_order_intent_validator_read_only",
        "would_place_order": False,
        "would_execute_trade": False,
        "would_send_transaction": False,
        "would_write": False,
        "writes_performed": 0,
    }
