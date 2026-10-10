"""Alpha Lab Router — Unified On-Chain + Alpha"""
from __future__ import annotations

import asyncio
import base64
import hmac
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response

from services.onchain_engine import analyze_wallet as get_wallet_summary
from services.alpha_lab import (
    analyze_token_risk,
    dedupe_alpha_events,
    get_alpha_sources,
    simulate_prediction_copy,
    simulate_manipulation_strategy,
)

router = APIRouter()

WALLET_PROOFS_PATH = Path(__file__).resolve().parents[1] / "data" / "alpha" / "wallet_proofs.json"
ALPHA_USAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "alpha" / "usage_events.jsonl"
WALLET_VERIFICATION_MAX_AGE_SECONDS = 10 * 60
WALLET_PROOF_TTL_SECONDS = 24 * 60 * 60
CLIENT_SESSION_TTL_SECONDS = 6 * 60 * 60
CLIENT_SESSION_COOKIE = "core_client_session"
FRESH_FLOW_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
NATIVE_ASSETS = {"eth", "bnb", "matic", "pol", "avax", "sol", "btc", "trx", "arb", "op", "base"}
KNOWN_CEX_NAMES = ("binance", "bitget", "gate", "mexc", "okx", "coinbase", "kraken", "kucoin")
USAGE_EXTRA_MAX_KEYS = 16
USAGE_EXTRA_MAX_TEXT = 240
USAGE_EXTRA_MAX_DEPTH = 2
ALPHA_CLIENT_MAX_ITEMS = 250
ALPHA_CLIENT_MAX_PAYLOAD_BYTES = 250_000
USAGE_SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|signature|private|seed|mnemonic|password|auth|cookie|key)",
    re.IGNORECASE,
)


def _bounded_client_payload(payload: dict[str, Any], list_key: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON object payload required.")
    try:
        payload_bytes = len(json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8"))
    except Exception:
        payload_bytes = ALPHA_CLIENT_MAX_PAYLOAD_BYTES + 1
    if payload_bytes > ALPHA_CLIENT_MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Alpha Lab payload is too large.")
    if list_key:
        items = payload.get(list_key, [])
        if items is None:
            return payload
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail=f"{list_key} must be a list.")
        if len(items) > ALPHA_CLIENT_MAX_ITEMS:
            raise HTTPException(status_code=413, detail=f"{list_key} exceeds the Alpha Lab item limit.")
    return payload


def _require_alpha_admin(x_core_admin_token: str | None = Header(default=None)) -> None:
    token = os.getenv("CORE_ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=403, detail="CORE_ADMIN_TOKEN is not configured")
    if not hmac.compare_digest(str(x_core_admin_token or ""), token):
        raise HTTPException(status_code=403, detail="Core Equity admin token required")


def _client_session_secret() -> str:
    admin = os.getenv("CORE_ADMIN_TOKEN", "").strip()
    secret = os.getenv("CORE_CLIENT_SESSION_SECRET", "").strip() or admin
    if not secret:
        raise HTTPException(status_code=503, detail="CORE_CLIENT_SESSION_SECRET is required for client sessions")
    return secret


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("ascii"))


def _sign_client_session(payload: dict[str, Any]) -> str:
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(_client_session_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(sig)}"


def _read_client_session(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, sig = token.split(".", 1)
    expected = hmac.new(_client_session_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    try:
        provided = _b64url_decode(sig)
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except Exception:
        return None
    exp = _safe_int(payload.get("exp"), 0)
    if not exp or exp < int(time.time()):
        return None
    return payload


def _require_client_wallet_session(wallet: str, token: str | None) -> dict[str, Any]:
    address = _validate_wallet(wallet)
    session = _read_client_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Active Core Equity client session required.")
    if str(session.get("wallet", "")).lower() != address.lower():
        raise HTTPException(status_code=403, detail="Client session does not match requested wallet.")
    if str(session.get("scope") or "") != "alpha_lab_read_only":
        raise HTTPException(status_code=403, detail="Client session scope is not valid for Alpha Lab.")
    return session


def _require_explicit_client_write(action: str | None, expected: str, operation: str) -> None:
    if not hmac.compare_digest(str(action or ""), expected):
        raise HTTPException(status_code=403, detail=f"Explicit client action header required for {operation}.")


def _cookie_secure(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )

try:
    from eth_account.messages import encode_defunct
    from eth_account import Account
except Exception:
    Account = None
    encode_defunct = None


# ── Alpha Lab core endpoints ─────────────────────────────────────────────────

@router.get("/collectors/status")
async def _collectors_status():
    return get_alpha_sources()


@router.get("/sources")
async def _sources_alias():
    return get_alpha_sources()


@router.get("/prediction/markets")
async def _prediction_markets(
    source: str = "all",
    query: str | None = None,
    limit: int = 30,
    cache: str = "true",
):
    return {
        "source": source,
        "query": query,
        "count": 0,
        "markets": [],
        "source_status": [],
        "latency_ms": 0,
        "note": "Prediction market adapter is planned but not yet implemented.",
    }


@router.post("/simulate/prediction-copy")
async def _simulate_prediction_copy(payload: dict):
    payload = _bounded_client_payload(payload, "trades")
    return await asyncio.to_thread(simulate_prediction_copy, payload)


@router.post("/simulate/manipulation")
async def _simulate_manipulation(payload: dict):
    payload = _bounded_client_payload(payload, "events")
    return await asyncio.to_thread(simulate_manipulation_strategy, payload)


@router.post("/events/dedupe")
async def _events_dedupe(payload: dict):
    payload = _bounded_client_payload(payload, "events")
    return await asyncio.to_thread(dedupe_alpha_events, payload.get("events", []))


@router.post("/risk/token")
async def _risk_token(payload: dict):
    payload = _bounded_client_payload(payload)
    return await asyncio.to_thread(analyze_token_risk, payload)


@router.post("/usage/event")
async def _usage_event(payload: dict, request: Request):
    """Store privacy-minimized Alpha Lab product analytics.

    We keep enough to understand client usage and conversion, but avoid raw
    wallet addresses, signatures, auth tokens or private transaction data.
    """
    fp = _wallet_fingerprint(payload.get("wallet"))
    event = {
        **payload,
        **fp,
        "wallet": None,
        "client": {
            "host_hash": _sha256_text(request.client.host) if request.client and request.client.host else None,
            "user_agent": (request.headers.get("user-agent") or "")[:180],
        },
    }
    stored = await asyncio.to_thread(_append_usage_event, event)
    return {"ok": True, "stored": True, "event": stored}


@router.get("/usage/stats")
async def _usage_stats(limit: int = 500, _: None = Depends(_require_alpha_admin)):
    if not ALPHA_USAGE_PATH.exists():
        return {"ok": True, "events": 0, "actions": {}, "wallets": 0, "recent": []}
    rows: list[dict[str, Any]] = []
    with ALPHA_USAGE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    recent = rows[-max(1, min(limit, 2000)) :]
    actions: dict[str, int] = {}
    wallets: set[str] = set()
    for row in rows:
        action = str(row.get("action") or "unknown")
        actions[action] = actions.get(action, 0) + 1
        if row.get("wallet_hash"):
            wallets.add(str(row["wallet_hash"]))
    return {
        "ok": True,
        "events": len(rows),
        "actions": actions,
        "wallets": len(wallets),
        "recent": recent[-25:],
    }


# ── Wallet helpers ───────────────────────────────────────────────────────────

def _validate_wallet(wallet: str) -> str:
    wallet = wallet.strip()
    if re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet):
        return wallet.lower()
    if re.fullmatch(r"[a-zA-Z0-9\-]+\.eth", wallet):
        return wallet.lower()
    if re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", wallet):
        return wallet
    raise HTTPException(400, f"Adresse wallet invalide : {wallet!r}")


def _load_wallet_proofs() -> dict:
    if not WALLET_PROOFS_PATH.exists():
        return {"proofs": []}
    try:
        return json.loads(WALLET_PROOFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"proofs": []}


def _save_wallet_proof(proof: dict) -> dict:
    WALLET_PROOFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _load_wallet_proofs()
    proofs = [
        item for item in data.get("proofs", [])
        if str(item.get("address", "")).lower() != str(proof.get("address", "")).lower()
    ]
    proofs.insert(0, proof)
    data["proofs"] = proofs[:200]
    WALLET_PROOFS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return proof


def _get_wallet_proof(address: str) -> dict | None:
    normalized = str(address or "").lower()
    for proof in _load_wallet_proofs().get("proofs", []):
        if str(proof.get("address", "")).lower() == normalized:
            return proof
    return None


def _wallet_proof_status(proof: dict | None) -> dict[str, Any]:
    if not proof:
        return {
            "verified": False,
            "expired": False,
            "proof_age_seconds": None,
            "expires_at": None,
            "execution_gate": "read_only_unverified_wallet",
            "source": "no_server_proof",
        }
    verified_at = _safe_int(proof.get("verified_at"), 0)
    age = max(0, int(time.time()) - verified_at) if verified_at else None
    expires_at = verified_at + WALLET_PROOF_TTL_SECONDS if verified_at else None
    expired = bool(age is None or age > WALLET_PROOF_TTL_SECONDS)
    verified = bool(proof.get("verified")) and not expired
    return {
        "verified": verified,
        "expired": expired,
        "proof_age_seconds": age,
        "expires_at": expires_at,
        "execution_gate": "ownership_verified" if verified else ("ownership_proof_expired" if expired else "read_only_unverified_wallet"),
        "source": proof.get("source") or "core_equity_client_wallet",
    }


def _wallet_fingerprint(wallet: str | None) -> dict[str, str | None]:
    raw = str(wallet or "").strip()
    if not raw:
        return {"wallet_hash": None, "wallet_short": None}
    digest = hashlib.sha256(raw.lower().encode("utf-8")).hexdigest()
    if len(raw) > 14:
        short = f"{raw[:6]}...{raw[-4:]}"
    else:
        short = raw
    return {"wallet_hash": digest, "wallet_short": short}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sanitize_usage_value(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:USAGE_EXTRA_MAX_TEXT]
    if depth >= USAGE_EXTRA_MAX_DEPTH:
        return str(value)[:USAGE_EXTRA_MAX_TEXT]
    if isinstance(value, list):
        return [_sanitize_usage_value(item, depth + 1) for item in value[:10]]
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in list(value.items())[:USAGE_EXTRA_MAX_KEYS]:
            key_text = str(key)[:64]
            if USAGE_SENSITIVE_KEY_RE.search(key_text):
                clean[key_text] = "[redacted]"
                continue
            clean[key_text] = _sanitize_usage_value(item, depth + 1)
        return clean
    return str(value)[:USAGE_EXTRA_MAX_TEXT]


def _append_usage_event(event: dict[str, Any]) -> dict[str, Any]:
    ALPHA_USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe_event = {
        "ts": round(time.time(), 3),
        "page": str(event.get("page") or "alpha")[:64],
        "action": str(event.get("action") or "unknown")[:96],
        "wallet_hash": event.get("wallet_hash"),
        "wallet_short": event.get("wallet_short"),
        "connected_wallets": _safe_int(event.get("connected_wallets"), 0),
        "status": str(event.get("status") or "")[:64],
        "extra": _sanitize_usage_value(event.get("extra") if isinstance(event.get("extra"), dict) else {}),
        "client": event.get("client") if isinstance(event.get("client"), dict) else {},
    }
    with ALPHA_USAGE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe_event, ensure_ascii=False, separators=(",", ":")) + "\n")
    return safe_event


def _is_probable_evm_signature(signature: str) -> bool:
    return bool(re.fullmatch(r"0x[0-9a-fA-F]{130}", signature.strip()))


def _parse_wallet_verification_message(message: str, address: str, network: str) -> dict[str, Any]:
    lines = [line.strip() for line in message.splitlines()]
    if len(lines) != 4 or lines[0] != "Core Equity wallet verification":
        raise HTTPException(400, "Invalid wallet verification message format.")

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if ": " not in line:
            raise HTTPException(400, "Invalid wallet verification message field.")
        key, value = line.split(": ", 1)
        fields[key.lower()] = value.strip()

    if fields.get("address", "").lower() != address.lower():
        raise HTTPException(400, "Verification message does not match wallet address.")
    if fields.get("network", "").lower() != network.lower():
        raise HTTPException(400, "Verification message does not match wallet network.")

    raw_time = fields.get("time", "")
    try:
        signed_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception as exc:
        raise HTTPException(400, "Invalid wallet verification timestamp.") from exc

    age_seconds = abs((datetime.now(timezone.utc) - signed_at).total_seconds())
    if age_seconds > WALLET_VERIFICATION_MAX_AGE_SECONDS:
        raise HTTPException(400, "Wallet verification signature is expired. Please sign a fresh message.")

    return {"address": fields["address"], "network": fields["network"], "signed_at": int(signed_at.timestamp())}


def _recover_evm_signer(message: str, signature: str) -> str | None:
    if not Account or not encode_defunct:
        return None
    encoded = encode_defunct(text=message)
    recovered = Account.recover_message(encoded, signature=signature)
    return recovered.lower()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
        return result if result == result and result not in {float("inf"), float("-inf")} else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _wallet_pool_snapshot_contract(event: dict[str, Any]) -> dict[str, Any]:
    existing = event.get("pool_snapshot") if isinstance(event.get("pool_snapshot"), dict) else {}
    pool_address = event.get("pool_address") or event.get("pair_address") or event.get("pair")
    reserve0 = _optional_float(event.get("reserve0") if event.get("reserve0") is not None else existing.get("reserve0"))
    reserve1 = _optional_float(event.get("reserve1") if event.get("reserve1") is not None else existing.get("reserve1"))
    liquidity_usd = _optional_float(
        event.get("pool_liquidity_usd")
        or event.get("liquidity_usd")
        or event.get("entry_liquidity_usd")
        or existing.get("liquidity_usd")
    )
    provider = event.get("pool_snapshot_provider") or event.get("reserve_provider") or existing.get("pool_snapshot_provider")
    has_reserves = reserve0 is not None and reserve1 is not None
    has_liquidity = liquidity_usd is not None
    snapshot_quality = (
        "historical_reserves_and_liquidity"
        if has_reserves and has_liquidity
        else "historical_reserves_only"
        if has_reserves
        else "liquidity_value_only"
        if has_liquidity
        else str(existing.get("snapshot_quality") or "missing_reserves")
    )
    return {
        "pool_snapshot_provider": provider,
        "pool_address": pool_address or existing.get("pool_address"),
        "chain": event.get("chain") or existing.get("chain"),
        "block_number": event.get("block_number") or existing.get("block_number"),
        "timestamp": event.get("timestamp") or existing.get("timestamp"),
        "reserve0": reserve0,
        "reserve1": reserve1,
        "reserve0_raw": existing.get("reserve0_raw"),
        "reserve1_raw": existing.get("reserve1_raw"),
        "liquidity_usd": liquidity_usd,
        "snapshot_quality": snapshot_quality,
        "liquidity_proxy_hint": not (has_reserves and has_liquidity and provider),
        "missing_proofs": existing.get("missing_proofs") or ([] if has_reserves and has_liquidity and provider else ["pool_liquidity_usd"]),
        "source_policy": (
            existing.get("source_policy")
            or
            "pool snapshot is execution-grade only when historical reserves, liquidity value, "
            "provider, pool address, timestamp and block number are present; trade-only context is a proxy"
        ),
    }


def _wallet_replay_market_proof(event: dict[str, Any]) -> dict[str, Any]:
    timestamp = event.get("timestamp")
    tx_hash = event.get("tx_hash") or event.get("source_event_id")
    provider = event.get("market_provider") or event.get("price_provider") or event.get("provider")
    chain = event.get("chain")
    asset = event.get("asset") or event.get("token")
    dex = event.get("dex")
    pair_address = event.get("pair_address") or event.get("pair")
    entry_price = _optional_float(event.get("entry_price_usd") or event.get("price_usd"))
    exit_price = _optional_float(event.get("exit_price_usd"))
    entry_liquidity = _optional_float(event.get("entry_liquidity_usd") or event.get("liquidity_usd"))
    exit_liquidity = _optional_float(event.get("exit_liquidity_usd"))
    pool_snapshot = _wallet_pool_snapshot_contract(event)
    local_price_proxy = event.get("local_price_proxy") if isinstance(event.get("local_price_proxy"), dict) else {}
    price_proofs = []
    for candidate in local_price_proxy.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        price = _optional_float(candidate.get("price_proxy_usd"))
        if price is None:
            continue
        price_proofs.append({
            "provider": local_price_proxy.get("provider") or "local_swaps.amount_usd_over_token_amount",
            "token_address": candidate.get("token"),
            "price_usd": price,
            "price_quality": candidate.get("price_quality") or "local_swap_proxy",
            "tx_hash": candidate.get("tx_hash") or tx_hash,
            "pair_address": candidate.get("pair_address") or pair_address,
            "dex": candidate.get("dex") or dex,
            "block_number": candidate.get("block_number") or event.get("block_number"),
            "distance_blocks": candidate.get("distance_blocks"),
            "missing_proofs": candidate.get("missing_proofs") or ["timestamped_token_price"],
            "source_policy": (
                candidate.get("source_policy")
                or
                "local amount_usd/token_amount is a research proxy only; it does not satisfy "
                "timestamped entry/exit price proof"
            ),
        })

    entry_price_ok = bool(entry_price is not None and timestamp and tx_hash and provider)
    exit_price_ok = bool(exit_price is not None and timestamp and tx_hash and provider)
    snapshot_liquidity_ok = pool_snapshot["liquidity_proxy_hint"] is False
    entry_liq_ok = bool(entry_liquidity is not None and timestamp and pair_address and dex and snapshot_liquidity_ok)
    exit_liq_ok = bool(exit_liquidity is not None and timestamp and pair_address and dex and snapshot_liquidity_ok)
    gates = {
        "entry_price_proof": entry_price_ok,
        "exit_price_proof": exit_price_ok,
        "liquidity_at_entry": entry_liq_ok,
        "liquidity_at_exit": exit_liq_ok,
    }
    missing = [key for key, ok in gates.items() if not ok]
    missing.extend(
        f"pool_snapshot:{item}"
        for item in (pool_snapshot.get("missing_proofs") or [])
        if str(item).strip()
    )
    missing.extend(
        f"price_proof:{item}"
        for proof in price_proofs
        for item in (proof.get("missing_proofs") or [])
        if str(item).strip()
    )
    return {
        "asset": asset,
        "chain": chain,
        "timestamp": timestamp,
        "tx_hash": tx_hash,
        "provider": provider,
        "dex": dex,
        "pair_address": pair_address,
        "token_in": event.get("token_in"),
        "token_out": event.get("token_out"),
        "amount_in": _optional_float(event.get("amount_in")),
        "amount_out": _optional_float(event.get("amount_out")),
        "amount_usd": _optional_float(event.get("amount_usd")),
        "local_price_proxy": local_price_proxy or None,
        "price_proofs": price_proofs,
        "pool_snapshot": pool_snapshot,
        "token_identity_quality": event.get("token_identity_quality"),
        "entry": {
            "price_usd": entry_price,
            "liquidity_usd": entry_liquidity,
            "status": "confirmed" if entry_price_ok and entry_liq_ok else "missing_or_partial",
        },
        "exit": {
            "price_usd": exit_price,
            "liquidity_usd": exit_liquidity,
            "status": "confirmed" if exit_price_ok and exit_liq_ok else "missing_or_partial",
        },
        "proof_gates": gates,
        "missing_proofs": _dedupe_text(missing),
        "price_proxy_hint": bool(missing),
        "source_policy": (
            "replay market proof requires timestamped tx, provider, pair/dex, entry/exit price "
            "and entry/exit liquidity; partial data remains a proxy hint"
        ),
    }


def _local_exact_swap_context(tx_hash: Any, chain: Any = None) -> dict[str, Any] | None:
    tx = str(tx_hash or "").strip()
    if not tx:
        return None
    try:
        from services.onchain.core.paths import DB_PATH
    except Exception:
        return None

    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        params: list[Any] = [tx]
        where = "tx_hash = ?"
        if chain:
            where += " AND chain = ?"
            params.append(str(chain))
        row = conn.execute(
            f"""
            SELECT tx_hash, chain, block_number, timestamp, dex, token_in, token_out, amount_in,
                   amount_out, amount_usd, pool, token_identity_quality,
                   pair_rpc_source, venue_source, venue_confidence
            FROM swaps
            WHERE {where}
            ORDER BY
                CASE WHEN token_identity_quality = 'exact_pair_log_direction' THEN 0 ELSE 1 END,
                COALESCE(venue_confidence, 0) DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
    except (sqlite3.Error, OSError):
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    if not row:
        return None

    amount_usd = _optional_float(row["amount_usd"])
    proxy_candidates = []
    for token_key, amount_key in (("token_in", "amount_in"), ("token_out", "amount_out")):
        amount = _optional_float(row[amount_key])
        if amount_usd and amount and amount > 0:
            proxy_candidates.append({
                "token": row[token_key],
                "amount_column": amount_key,
                "price_proxy_usd": round(amount_usd / amount, 12),
                "price_quality": "local_swap_timestamped_proxy",
                "tx_hash": row["tx_hash"],
                "pair_address": row["pool"],
                "dex": row["dex"],
                "block_number": row["block_number"],
                "timestamp": row["timestamp"],
                "distance_blocks": 0,
                "missing_proofs": ["oracle_historical_price"],
                "source_policy": (
                    "price is derived from this exact local onchain.db swap row; it is timestamped "
                    "research context, not oracle/execution-grade price proof"
                ),
            })

    pool_snapshot = {
        "pool_snapshot_provider": None,
        "pool_address": row["pool"],
        "chain": row["chain"],
        "block_number": row["block_number"],
        "timestamp": row["timestamp"],
        "reserve0": None,
        "reserve1": None,
        "reserve0_raw": None,
        "reserve1_raw": None,
        "liquidity_usd": None,
        "snapshot_quality": "missing_reserves",
        "liquidity_proxy_hint": True,
        "missing_proofs": ["historical_pool_reserves", "pool_liquidity_usd"],
        "source_policy": "local swaps table does not store historical reserves/liquidity yet",
    }
    if row["pool"] and row["block_number"]:
        try:
            from services.onchain_engine import get_pool_reserve_snapshot

            snapshot = get_pool_reserve_snapshot(row["chain"], row["pool"], row["block_number"])
            pool_snapshot.update({
                "pool_snapshot_provider": snapshot.get("provider"),
                "pool_address": snapshot.get("pool_address") or row["pool"],
                "chain": snapshot.get("chain") or row["chain"],
                "block_number": snapshot.get("block_number") or row["block_number"],
                "reserve0": snapshot.get("reserve0"),
                "reserve1": snapshot.get("reserve1"),
                "reserve0_raw": snapshot.get("reserve0_raw"),
                "reserve1_raw": snapshot.get("reserve1_raw"),
                "liquidity_usd": snapshot.get("liquidity_usd"),
                "snapshot_quality": snapshot.get("snapshot_quality") or pool_snapshot["snapshot_quality"],
                "missing_proofs": snapshot.get("missing_proofs") or pool_snapshot["missing_proofs"],
                "source_policy": snapshot.get("source_policy") or pool_snapshot["source_policy"],
            })
            pool_snapshot["liquidity_proxy_hint"] = not (
                pool_snapshot.get("reserve0") is not None
                and pool_snapshot.get("reserve1") is not None
                and pool_snapshot.get("liquidity_usd") is not None
                and pool_snapshot.get("pool_snapshot_provider")
            )
        except Exception:
            pass

    return {
        "market_provider": "local_exact_swap_cache",
        "provider": "local_exact_swap_cache",
        "chain": row["chain"],
        "timestamp": row["timestamp"],
        "tx_hash": row["tx_hash"],
        "dex": row["dex"],
        "pair_address": row["pool"],
        "token_in": row["token_in"],
        "token_out": row["token_out"],
        "amount_in": row["amount_in"],
        "amount_out": row["amount_out"],
        "amount_usd": row["amount_usd"],
        "block_number": row["block_number"],
        "token_identity_quality": row["token_identity_quality"],
        "pool_snapshot_provider": pool_snapshot.get("pool_snapshot_provider"),
        "pool_snapshot": pool_snapshot,
        "local_price_proxy": {
            "provider": "local_swaps.amount_usd_over_token_amount",
            "candidates": proxy_candidates,
            "source_policy": (
                "local exact swap context is a research proxy only; amount_usd/token_amount "
                "does not satisfy entry/exit price proof or liquidity proof"
            ),
        },
        "source_policy": (
            "read-only local swap context from onchain.db; exact token direction may support "
            "research replay context but not execution-grade price/liquidity proof"
        ),
    }


def _wallet_copy_backtest_from_surface(
    wallet: str,
    surface: dict[str, Any],
    probe: dict[str, Any],
    *,
    capital: float = 100.0,
    max_trade_pct: float = 0.20,
    slippage_bps: float = 75.0,
    fee_bps: float = 20.0,
) -> dict[str, Any]:
    """Read-only counterfactual copy replay from observed wallet flow.

    This is intentionally conservative: no execution, no guaranteed profit, and
    no ROI claim when provider PnL/sellability evidence is weak.
    """
    safe_capital = max(10.0, min(_safe_float(capital, 100.0), 100_000.0))
    max_trade_pct = max(0.01, min(_safe_float(max_trade_pct, 0.20), 0.50))
    total_cost_bps = max(0.0, _safe_float(slippage_bps, 75.0) + _safe_float(fee_bps, 20.0))
    activity = [row for row in surface.get("activity") or [] if isinstance(row, dict)]
    risk = probe.get("risk_summary") or {}
    suspicious = {
        str(asset).lower()
        for asset in risk.get("suspicious_assets", [])
        if str(asset).strip()
    }
    cash = safe_capital
    simulated_value = safe_capital
    copied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    market_proofs: list[dict[str, Any]] = []
    assets_seen: set[str] = set()
    chains_seen: set[str] = set()

    for event in activity[:50]:
        event_type = str(event.get("event_type") or "").lower()
        direction = str(event.get("direction") or "").lower()
        asset = str(event.get("asset") or "unknown")
        chain = str(event.get("chain") or "unknown")
        amount_usd = abs(_safe_float(event.get("amount_usd"), 0.0))
        assets_seen.add(asset.lower())
        chains_seen.add(chain)
        if amount_usd <= 0:
            skipped.append({"reason": "missing_usd_value", "asset": asset, "chain": chain})
            continue
        if asset.lower() in suspicious:
            skipped.append({"reason": "suspicious_asset_blocked", "asset": asset, "chain": chain, "observed_usd": round(amount_usd, 4)})
            continue
        if event_type not in {"swap", "transfer"}:
            skipped.append({"reason": "unsupported_event_type", "event_type": event_type or "unknown", "asset": asset})
            continue
        allocation = min(cash, safe_capital * max_trade_pct, amount_usd)
        if allocation <= 0:
            skipped.append({"reason": "cash_exhausted", "asset": asset, "chain": chain})
            continue
        cost = allocation * (total_cost_bps / 10_000.0)
        # Without historical price marks, we only prove capital discipline and
        # downside from execution costs. Provider PnL can improve this later.
        simulated_value -= cost
        cash -= allocation
        proof_event = dict(event)
        local_context = _local_exact_swap_context(event.get("tx_hash"), chain)
        if local_context:
            for key, value in local_context.items():
                if value not in (None, "", []):
                    proof_event.setdefault(key, value)
        market_proof = _wallet_replay_market_proof(proof_event)
        market_proofs.append(market_proof)
        copied.append(
            {
                "asset": asset,
                "chain": chain,
                "event_type": event_type,
                "direction": direction or "unknown",
                "observed_usd": round(amount_usd, 4),
                "allocation": round(allocation, 4),
                "estimated_cost": round(cost, 6),
                "timestamp": event.get("timestamp"),
                "tx_hash": event.get("tx_hash"),
                "market_proof": market_proof,
            }
        )

    pnl = simulated_value - safe_capital
    providers = probe.get("provider_health") or {}
    provider_ok = int(providers.get("ok") or 0)
    provider_total = int(providers.get("total") or 0)
    blockers: list[str] = []
    if not activity:
        blockers.append("no_observed_wallet_activity")
    if not copied:
        blockers.append("no_copyable_events_after_risk_filters")
    if provider_ok == 0:
        blockers.append("no_provider_pnl_confirmation")
    if int(risk.get("blocked_rows") or 0) > 0:
        blockers.append("blocked_or_fake_profit_rows_present")
    if int(risk.get("untrusted_rows") or 0) > 0:
        blockers.append("untrusted_profit_rows_present")
    if len(chains_seen) == 0:
        blockers.append("no_chain_coverage")

    source_freshness_detail = _wallet_source_freshness(surface)
    provider_cex_flow_gate = _wallet_cex_flow_gate(surface)
    rpc_tx_enrichment = _wallet_rpc_tx_enrichment(wallet, activity)
    local_cex_deposit_surface = _wallet_local_cex_deposit_surface(wallet)
    cex_flow_gate = _merge_cex_flow_gate(provider_cex_flow_gate, local_cex_deposit_surface)
    funder_graph = _wallet_funder_graph_readiness(wallet, sorted(chains_seen))
    coordination_surface = _wallet_coordination_surface(
        wallet=wallet,
        chains=sorted(chains_seen),
        cex_flow=cex_flow_gate,
        funder_graph=funder_graph,
        activity=activity,
    )
    replay_proof_gates = {
        "entry_price_proof": bool(market_proofs) and all(item["proof_gates"]["entry_price_proof"] for item in market_proofs),
        "exit_price_proof": bool(market_proofs) and all(item["proof_gates"]["exit_price_proof"] for item in market_proofs),
        "liquidity_at_entry": bool(market_proofs) and all(item["proof_gates"]["liquidity_at_entry"] for item in market_proofs),
        "liquidity_at_exit": bool(market_proofs) and all(item["proof_gates"]["liquidity_at_exit"] for item in market_proofs),
        "slippage_model": slippage_bps is not None and _safe_float(slippage_bps, -1.0) >= 0,
        "fee_model": fee_bps is not None and _safe_float(fee_bps, -1.0) >= 0,
    }
    replay_missing_proofs = [key for key, ok in replay_proof_gates.items() if not ok]
    for proof in market_proofs:
        replay_missing_proofs.extend(
            str(item)
            for item in (proof.get("missing_proofs") or [])
            if str(item).strip()
        )
    replay_missing_proofs = _dedupe_text(replay_missing_proofs)
    if replay_missing_proofs:
        blockers.append("replay_price_liquidity_proof_missing")

    token_risk_watchlist = _wallet_token_risk_watchlist(probe)
    copied_assets = {str(row.get("asset") or "").lower() for row in copied if str(row.get("asset") or "").strip()}
    if copied_assets and token_risk_watchlist:
        token_risk_watchlist = [
            row for row in token_risk_watchlist
            if str(row.get("asset") or "").lower() in copied_assets
        ]
    if copied_assets and not token_risk_watchlist:
        token_risk_watchlist = [
            {
                "asset": asset.upper(),
                "chain": "unknown",
                "risk_flag": "replay_token_needs_price_liquidity_proof",
                "copy_allowed": None,
                "missing_proofs": ["successful_sell_proof", "liquidity_snapshot"],
                "source_policy": "replay token inferred from wallet surface; token-level sellability proof still required",
            }
            for asset in sorted(copied_assets)[:8]
            if asset and asset != "unknown"
        ]

    confidence_score = max(
        0,
        min(
            100,
            round(
                (min(len(copied), 10) * 5)
                + (20 if provider_ok else 0)
                + (10 if provider_total and provider_ok >= provider_total else 0)
                + (min(len(chains_seen), 4) * 5)
                - min(30, len(skipped) * 2)
                - min(30, len(blockers) * 8),
                2,
            ),
        ),
    )
    verdict = "blocked" if blockers else "research_only"
    if confidence_score >= 70 and not blockers:
        verdict = "manual_review_ready"
    source_trace = {
        "surface": "alpha_wallets.get_wallet_surface",
        "probe": "alpha_wallets.probe_wallet_candidate",
        "source_freshness": source_freshness_detail,
        "provider_cex_flow_gate": provider_cex_flow_gate,
        "cex_flow_gate": cex_flow_gate,
        "local_cex_deposit_surface": local_cex_deposit_surface,
        "rpc_tx_enrichment": rpc_tx_enrichment,
        "funder_graph_readiness": funder_graph,
        "coordination_surface": coordination_surface,
        "price_source": "event_market_proof" if any(not item["price_proxy_hint"] for item in market_proofs) else "not_available",
        "price_proxy_hint": any(item["price_proxy_hint"] for item in market_proofs) if market_proofs else True,
        "market_proofs": market_proofs[:20],
        "replay_policy": "cost_only_until_timestamped_price_liquidity_and_sell_proofs_exist",
    }
    data_quality = {
        "source_freshness": source_freshness_detail["freshness_policy"],
        "source_freshness_detail": source_freshness_detail,
        "provider_cex_flow_gate": provider_cex_flow_gate,
        "cex_flow_gate": cex_flow_gate,
        "local_cex_deposit_surface": local_cex_deposit_surface,
        "rpc_tx_enrichment": rpc_tx_enrichment,
        "funder_graph_readiness": funder_graph,
        "coordination_surface": coordination_surface,
        "token_sellability": "needs_token_level_proof" if token_risk_watchlist else "not_available",
        "replay_proof_gates": replay_proof_gates,
        "replay_missing_proofs": replay_missing_proofs,
    }
    scorecard = {
        "providers_ok": provider_ok,
        "providers_total": provider_total,
        "estimated_value": round(simulated_value, 6),
        "roi_pct": round((pnl / safe_capital) * 100, 4),
    }
    investment_readiness = _wallet_investment_readiness(
        mode="copy_backtest_read_only",
        readiness_score=confidence_score,
        blockers=blockers,
        source_trace=source_trace,
        data_quality=data_quality,
        token_risk_watchlist=token_risk_watchlist,
        scorecard=scorecard,
    )
    manipulation_readiness = _wallet_manipulation_readiness(
        market_proofs=market_proofs,
        token_risk_watchlist=token_risk_watchlist,
        source_trace=source_trace,
        data_quality=data_quality,
        activity=activity,
        copied=copied,
        skipped=skipped,
    )
    return {
        "ok": True,
        "wallet": wallet,
        "mode": "copy_backtest_read_only",
        "capital": round(safe_capital, 2),
        "current_value": round(simulated_value, 6),
        "pnl": round(pnl, 6),
        "roi_pct": round((pnl / safe_capital) * 100, 4),
        "confidence_score": confidence_score,
        "verdict": verdict,
        "execution_enabled": False,
        "copy_trade_enabled": False,
        "profit_guarantee_allowed": False,
        "trade_signal_allowed": False,
        "copied_trades": copied[:20],
        "skipped": skipped[:20],
        "blockers": blockers,
        "source_trace": source_trace,
        "source_policy": (
            "Replay is read-only and remains inconclusive until entry/exit price proof, "
            "entry/exit liquidity, slippage/fee model, sell proof and source freshness are traceable."
        ),
        "replay_quality": {
            "verdict": "inconclusive" if replay_missing_proofs else "price_liquidity_proven",
            "proof_gates": replay_proof_gates,
            "missing_proofs": replay_missing_proofs,
            "market_proofs": market_proofs[:20],
            "price_proxy_hint": any(item["price_proxy_hint"] for item in market_proofs) if market_proofs else True,
            "source_policy": "cost-only replay is not a profit proof; missing market marks keep client result inconclusive",
        },
        "investment_readiness": investment_readiness,
        "manipulation_readiness": manipulation_readiness,
        "coverage": {
            "events_observed": len(activity),
            "events_copied": len(copied),
            "events_skipped": len(skipped),
            "assets_seen": len([asset for asset in assets_seen if asset and asset != "unknown"]),
            "chains_seen": sorted(chains_seen)[:8],
            "providers_ok": provider_ok,
            "providers_total": provider_total,
        },
        "assumptions": {
            "max_trade_pct": max_trade_pct,
            "slippage_bps": slippage_bps,
            "fee_bps": fee_bps,
            "profit_policy": "Cost-only replay until timestamped prices, liquidity depth and sell proofs are available.",
            "safety": "Backtest only. No orders, no private keys, no guarantee of future profit.",
        },
    }


def _wallet_manipulation_readiness(
    *,
    market_proofs: list[dict[str, Any]],
    token_risk_watchlist: list[dict[str, Any]],
    source_trace: dict[str, Any],
    data_quality: dict[str, Any],
    activity: list[dict[str, Any]],
    copied: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    """Research-only manipulation evidence score. This is never a trade signal."""
    cex_flow = data_quality.get("cex_flow_gate") or {}
    funder_graph = data_quality.get("funder_graph_readiness") or {}
    coordination = data_quality.get("coordination_surface") or {}
    freshness = data_quality.get("source_freshness_detail") or {}
    freshness_policy = str(freshness.get("freshness_policy") or data_quality.get("source_freshness") or "")

    pool_snapshots = [
        proof.get("pool_snapshot") or {}
        for proof in market_proofs
        if isinstance(proof.get("pool_snapshot"), dict)
    ]
    price_proofs = [
        proof
        for market_proof in market_proofs
        for proof in (market_proof.get("price_proofs") or [])
        if isinstance(proof, dict)
    ]
    evidence_present = {
        "fresh_wallet_surface": bool(activity),
        "source_freshness": freshness_policy not in {"", "missing_timestamp", "stale_over_7d", "rpc_fallback_only", "no_recent_sample"},
        "cex_flow": cex_flow.get("confirmed") is True,
        "cex_flow_hint": cex_flow.get("hint_only") is True,
        "pool_reserve_snapshot": any(
            snap.get("reserve0") is not None and snap.get("reserve1") is not None
            for snap in pool_snapshots
        ),
        "local_swap_timestamped_proxy": any(
            proof.get("price_quality") == "local_swap_timestamped_proxy"
            for proof in price_proofs
        ),
        "token_risk_surface": bool(token_risk_watchlist),
        "copyable_activity_surface": bool(copied),
        "funder_graph_surface": funder_graph.get("ok") is True,
        "coordination_surface": coordination.get("ok") is True,
    }
    missing: list[str] = []
    risk_factors: list[str] = []
    if not evidence_present["fresh_wallet_surface"]:
        missing.append("wallet_activity_surface")
    if not evidence_present["source_freshness"]:
        missing.append("fresh_timestamped_flow_sample")
    if not (evidence_present["cex_flow"] or evidence_present["cex_flow_hint"]):
        missing.append("cex_flow_or_hint")
    if evidence_present["cex_flow_hint"] and not evidence_present["cex_flow"]:
        risk_factors.append("cex_flow_label_hint_only")
        missing.append("cex_flow_confirmation")
    if not evidence_present["pool_reserve_snapshot"]:
        missing.append("historical_pool_reserves")
    if not evidence_present["local_swap_timestamped_proxy"]:
        missing.append("local_swap_timestamped_proxy")
    if not evidence_present["token_risk_surface"]:
        missing.append("token_safety_surface")
    if not evidence_present["funder_graph_surface"]:
        missing.extend(funder_graph.get("missing_proofs") or ["funder_graph_surface"])
    for hint in funder_graph.get("cluster_hints") or []:
        if isinstance(hint, dict) and hint.get("type"):
            risk_factors.append(str(hint.get("type")))
    if not evidence_present["coordination_surface"]:
        missing.extend(coordination.get("missing_proofs") or ["coordination_surface"])
    for hint in coordination.get("coordination_hints") or []:
        if isinstance(hint, dict) and hint.get("type"):
            risk_factors.append(str(hint.get("type")))

    for item in data_quality.get("replay_missing_proofs") or []:
        text = str(item or "").strip()
        if text:
            missing.append(f"replay:{text}")
    for row in token_risk_watchlist:
        risk_flag = str(row.get("risk_flag") or "").strip()
        if risk_flag and risk_flag not in {"major_token", "neutral"}:
            risk_factors.append(f"{row.get('asset') or 'unknown'}:{risk_flag}")
        if row.get("block_trade") is True or row.get("copy_allowed") is False:
            risk_factors.append(f"{row.get('asset') or 'unknown'}:trade_blocked")

    if skipped:
        risk_factors.append("some_events_skipped_by_replay_filters")
    evidence_score = sum(1 for value in evidence_present.values() if value is True)
    confidence_score = max(
        0,
        min(
            100,
            (evidence_score * 12)
            - min(35, len(_dedupe_text(missing)) * 3)
            - min(20, len(_dedupe_text(risk_factors)) * 2),
        ),
    )
    status = "data_gap"
    if confidence_score >= 60 and evidence_present["pool_reserve_snapshot"] and evidence_present["local_swap_timestamped_proxy"]:
        status = "research_ready"
    if any(str(item).endswith(":trade_blocked") for item in risk_factors):
        status = "blocked_by_token_risk"
    return {
        "status": status,
        "verdict": "inconclusive",
        "confidence_score": int(confidence_score),
        "evidence_present": evidence_present,
        "missing_proofs": _dedupe_text(missing),
        "risk_factors": _dedupe_text(risk_factors),
        "next_safe_action": (
            "Review token blockers and collect independent sellability/liquidity proofs."
            if status == "blocked_by_token_risk"
            else "Collect missing evidence before treating this as more than research."
            if missing
            else "Research review can continue; this is not a client action."
        ),
        "source_policy": (
            "manipulation_readiness is a read-only research score built from existing Alpha Lab "
            "evidence; it is not a trade signal and cannot enable client execution"
        ),
    }


def _wallet_coordination_surface(
    *,
    wallet: str,
    chains: list[str],
    cex_flow: dict[str, Any],
    funder_graph: dict[str, Any],
    activity: list[dict[str, Any]],
) -> dict[str, Any]:
    cex_present = cex_flow.get("confirmed") is True
    cex_hint_only = cex_flow.get("hint_only") is True
    funder_present = funder_graph.get("ok") is True
    gas_distributors = funder_graph.get("gas_distributors") or []
    cluster_hints = funder_graph.get("cluster_hints") or []
    shared_funder_count = sum(
        1
        for hint in cluster_hints
        if isinstance(hint, dict) and hint.get("type") == "shared_native_funder"
    )
    gas_distributor_count = len([row for row in gas_distributors if isinstance(row, dict)])
    fresh_surface = bool(activity)
    hints: list[dict[str, Any]] = []
    if (cex_present or cex_hint_only) and shared_funder_count:
        hints.append({
            "type": "shared_funder_with_cex_flow",
            "cex_flow_confirmed": cex_present,
            "cex_flow_hint_only": cex_hint_only,
            "shared_funder_count": shared_funder_count,
            "source": "alpha_lab.cex_flow_gate+funder_graph_readiness",
        })
    if (cex_present or cex_hint_only) and fresh_surface:
        hints.append({
            "type": "fresh_wallet_with_cex_flow",
            "cex_flow_confirmed": cex_present,
            "cex_flow_hint_only": cex_hint_only,
            "activity_count": len(activity),
            "source": "wallet_surface.activity+alpha_lab.cex_flow_gate",
        })
    if gas_distributor_count:
        hints.append({
            "type": "gas_distributor_cluster_hint",
            "gas_distributor_count": gas_distributor_count,
            "source": "funder_graph_readiness.gas_distributors",
        })

    missing: list[str] = []
    if not (cex_present or cex_hint_only):
        missing.append("cex_flow_or_hint")
    if not funder_present:
        missing.append("funder_graph_surface")
    if not fresh_surface:
        missing.append("fresh_wallet_surface")
    if not hints:
        missing.append("coordination_hints")

    return {
        "ok": bool(hints),
        "provider": "alpha_lab_existing_evidence",
        "wallet": wallet,
        "chain": (chains[0] if len(chains) == 1 else None),
        "cex_flow_present": cex_present,
        "cex_flow_hint_only": cex_hint_only,
        "funder_graph_present": funder_present,
        "shared_funder_count": shared_funder_count,
        "gas_distributor_count": gas_distributor_count,
        "fresh_wallet_surface": fresh_surface,
        "coordination_hints": hints,
        "missing_proofs": _dedupe_text(missing),
        "source_policy": (
            "coordination_surface correlates existing CEX flow, wallet activity and local funder graph "
            "evidence only; hints are research signals, not identity proof or trade signals"
        ),
    }


def _wallet_funder_graph_readiness(wallet: str, chains: list[str]) -> dict[str, Any]:
    preferred_chain = None
    chain_aliases = {
        "ethereum": "eth",
        "eth": "eth",
        "bnb": "bsc",
        "binance": "bsc",
        "bsc": "bsc",
        "polygon": "polygon",
        "matic": "polygon",
        "base": "base",
        "arbitrum": "arbitrum",
        "arb": "arbitrum",
    }
    evm_chains = _dedupe_text(
        chain_aliases.get(str(chain or "").strip().lower(), str(chain or "").strip().lower())
        for chain in chains
        if str(chain or "").strip()
    )
    evm_chains = [chain for chain in evm_chains if chain in {"eth", "bsc", "polygon", "base", "arbitrum"}]
    if len(evm_chains) == 1:
        preferred_chain = evm_chains[0]
    try:
        from services.onchain_engine import get_funder_graph_readiness

        return get_funder_graph_readiness(wallet, preferred_chain, limit=25)
    except Exception as exc:
        return {
            "ok": False,
            "provider": "local_onchain_db",
            "wallet": wallet,
            "chain": preferred_chain,
            "funders": [],
            "gas_distributors": [],
            "linked_wallet_count": 0,
            "cluster_hints": [],
            "missing_proofs": ["wallet_funding_history"],
            "error": str(exc)[:160],
            "source_policy": "funder graph lookup failed; no wallet links are inferred",
        }


def _wallet_chain_coverage(surface: dict[str, Any], probe: dict[str, Any]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}

    def touch(chain: Any, *, events: int = 0, usd: float = 0.0, assets: list[str] | None = None) -> None:
        name = str(chain or "unknown").strip() or "unknown"
        row = rows.setdefault(name, {"chain": name, "events": 0, "amount_usd": 0.0, "assets": set()})
        row["events"] += events
        row["amount_usd"] += usd
        for asset in assets or []:
            if asset:
                row["assets"].add(str(asset))

    for item in probe.get("asset_focus") or []:
        touch(item.get("chain"), events=_safe_int(item.get("events")), usd=_safe_float(item.get("amount_usd")), assets=[str(item.get("asset") or "")])
    for item in surface.get("activity") or []:
        touch(item.get("chain"), events=1, usd=_safe_float(item.get("amount_usd")), assets=[str(item.get("asset") or "")])

    ranked = sorted(rows.values(), key=lambda row: (row["amount_usd"], row["events"]), reverse=True)
    return [
        {
            "chain": row["chain"],
            "events": row["events"],
            "amount_usd": round(row["amount_usd"], 4),
            "assets": sorted(row["assets"])[:8],
        }
        for row in ranked[:8]
    ]


def _wallet_token_risk_watchlist(probe: dict[str, Any]) -> list[dict[str, Any]]:
    risk = probe.get("risk_summary") or {}
    suspicious = {
        str(asset).lower()
        for asset in risk.get("suspicious_assets", [])
        if str(asset).strip()
    }
    pnl_rows = [
        row
        for row in ((probe.get("intel") or {}).get("pnl") or [])
        if isinstance(row, dict) and str(row.get("token") or row.get("asset") or "").strip()
    ]
    focus_by_asset = {
        str(item.get("asset") or "").lower(): item
        for item in probe.get("asset_focus") or []
        if str(item.get("asset") or "").strip()
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in pnl_rows:
        asset = str(row.get("token") or row.get("asset") or "unknown")
        asset_key = asset.lower()
        focus = focus_by_asset.get(asset_key, {})
        flags = row.get("flags") if isinstance(row.get("flags"), list) else []
        missing_proofs = row.get("missing_proofs") if isinstance(row.get("missing_proofs"), list) else []
        block_trade = bool(row.get("block_trade"))
        risk_flag = _first_risk_code(flags) or str(row.get("profit_integrity") or "needs_sellability_proof")
        copy_allowed = False if block_trade or asset_key in suspicious else True if not missing_proofs and _safe_int(row.get("risk_score")) <= 20 else None
        rows.append({
            "asset": asset,
            "chain": row.get("chain") or focus.get("chain") or "unknown",
            "token_address": row.get("token_address"),
            "events": _safe_int(focus.get("events")),
            "observed_usd": round(_safe_float(focus.get("amount_usd") or row.get("total_pnl_usd")), 4),
            "risk_flag": risk_flag,
            "risk_score": _safe_int(row.get("risk_score")),
            "block_trade": block_trade,
            "profit_integrity": row.get("profit_integrity") or "unknown",
            "flags": flags,
            "missing_proofs": missing_proofs,
            "source_policy": row.get("source_policy") or "token risk source policy missing; keep inconclusive",
            "source_trace": row.get("source_trace") or {},
            "copy_allowed": copy_allowed,
        })
        seen.add(asset_key)

    for item in probe.get("asset_focus") or []:
        asset = str(item.get("asset") or "unknown")
        asset_key = asset.lower()
        if asset_key in seen:
            continue
        risk_flag = "suspicious_name_or_provider_flag" if asset_key in suspicious else "needs_sellability_proof"
        rows.append({
            "asset": asset,
            "chain": item.get("chain") or "unknown",
            "token_address": item.get("token_address"),
            "events": _safe_int(item.get("events")),
            "observed_usd": round(_safe_float(item.get("amount_usd")), 4),
            "risk_flag": risk_flag,
            "risk_score": 0,
            "block_trade": asset_key in suspicious,
            "profit_integrity": "unknown",
            "flags": [],
            "missing_proofs": ["token_sellability_contract", "successful_sell_proof", "liquidity_snapshot"],
            "source_policy": "asset focus lacks token-level TokenRiskResult; keep inconclusive",
            "source_trace": {"asset_focus": "alpha_wallets.probe_wallet_candidate"},
            "copy_allowed": False if asset_key in suspicious else None,
        })
    return rows[:8]


def _first_risk_code(flags: list[Any]) -> str | None:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    normalized = [flag for flag in flags if isinstance(flag, dict) and flag.get("code")]
    if not normalized:
        return None
    normalized.sort(key=lambda flag: severity_order.get(str(flag.get("severity") or "").lower(), 9))
    return str(normalized[0].get("code"))


def _wallet_rpc_chain_rows(rpc_summary: dict[str, Any], rpc_source: dict[str, Any]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}

    def touch(chain: Any, *, tx_count: int = 0, native_usd: float = 0.0, token_count: int = 0, quality: int = 0) -> None:
        name = str(chain or "unknown").strip() or "unknown"
        row = rows.setdefault(name, {
            "chain": name,
            "tx_count": 0,
            "native_value_usd": 0.0,
            "token_count": 0,
            "data_quality_score": 0,
        })
        row["tx_count"] = max(row["tx_count"], tx_count)
        row["native_value_usd"] += native_usd
        row["token_count"] = max(row["token_count"], token_count)
        row["data_quality_score"] = max(row["data_quality_score"], quality)

    token_counts: dict[str, int] = {}
    for token in rpc_summary.get("token_balances") or []:
        chain = str(token.get("chain") or "unknown")
        token_counts[chain] = token_counts.get(chain, 0) + 1
    for chain in rpc_summary.get("chains") or []:
        touch(
            chain.get("chain"),
            tx_count=_safe_int(chain.get("tx_count")),
            token_count=token_counts.get(str(chain.get("chain") or "unknown"), 0),
        )
    for row in rpc_source.get("rows") or []:
        touch(
            row.get("chain"),
            tx_count=_safe_int(row.get("tx_count")),
            native_usd=_safe_float(row.get("native_value_usd")),
            quality=_safe_int(row.get("data_quality_score")),
        )

    ranked = sorted(rows.values(), key=lambda row: (row["native_value_usd"], row["tx_count"], row["token_count"]), reverse=True)
    return [
        {
            "chain": row["chain"],
            "tx_count": row["tx_count"],
            "native_value_usd": round(row["native_value_usd"], 4),
            "token_count": row["token_count"],
            "data_quality_score": row["data_quality_score"],
        }
        for row in ranked[:8]
    ]


def _wallet_rpc_token_watchlist(rpc_summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for token in rpc_summary.get("token_balances") or []:
        rows.append({
            "asset": token.get("symbol") or token.get("coin_id") or "unknown",
            "chain": token.get("chain") or "unknown",
            "balance": _safe_float(token.get("balance")),
            "token_address": token.get("token_address"),
            "risk_flag": "major_token_balance_needs_sellability_context",
            "copy_allowed": None,
        })
    return rows[:8]


def _parse_event_timestamp(value: Any) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            return dt, dt.isoformat().replace("+00:00", "Z")
        except (OSError, OverflowError, ValueError):
            return None, str(value)
    text = str(value).strip()
    if not text:
        return None, None
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), text
    except ValueError:
        return None, text


def _source_freshness_policy(age_seconds: int | None) -> str:
    if age_seconds is None:
        return "missing_timestamp"
    if age_seconds <= 24 * 60 * 60:
        return "fresh_24h"
    if age_seconds <= FRESH_FLOW_MAX_AGE_SECONDS:
        return "stale_7d"
    return "stale_over_7d"


def _wallet_source_freshness(surface: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    for row in surface.get("activity") or []:
        if not isinstance(row, dict):
            continue
        dt, raw_ts = _parse_event_timestamp(row.get("timestamp"))
        candidates.append({
            "dt": dt,
            "latest_seen": raw_ts,
            "source": "wallet_surface.activity",
            "provider": row.get("provider") or "alpha_wallets.get_wallet_surface",
            "chain": row.get("chain"),
            "tx_hash": row.get("tx_hash"),
            "event_type": row.get("event_type"),
        })

    for group_name in ("counterparties", "venues"):
        for row in surface.get(group_name) or []:
            if not isinstance(row, dict):
                continue
            dt, raw_ts = _parse_event_timestamp(row.get("last_seen"))
            candidates.append({
                "dt": dt,
                "latest_seen": raw_ts,
                "source": f"wallet_surface.{group_name}",
                "provider": row.get("provider") or "alpha_wallets.get_wallet_surface",
                "chain": row.get("latest_chain"),
                "tx_hash": row.get("latest_tx"),
                "event_type": "aggregate",
            })

    valid = [item for item in candidates if item.get("dt")]
    latest = max(valid, key=lambda item: item["dt"]) if valid else (candidates[0] if candidates else {})
    latest_dt = latest.get("dt")
    age_seconds = None
    if latest_dt:
        age_seconds = max(0, int((datetime.now(timezone.utc) - latest_dt).total_seconds()))

    return {
        "latest_seen": latest.get("latest_seen"),
        "age_seconds": age_seconds,
        "source": latest.get("source") or "wallet_surface",
        "provider": latest.get("provider") or "alpha_wallets.get_wallet_surface",
        "chain": latest.get("chain"),
        "tx_hash": latest.get("tx_hash"),
        "event_type": latest.get("event_type"),
        "freshness_policy": _source_freshness_policy(age_seconds),
        "source_policy": (
            "freshness is derived from timestamped wallet surface events; missing or stale "
            "samples keep client investment inconclusive"
        ),
    }


def _contains_known_cex(*values: Any) -> str | None:
    text = " ".join(str(value or "") for value in values).lower()
    for name in KNOWN_CEX_NAMES:
        if name in text:
            return name
    return None


def _cex_flow_type(row: dict[str, Any]) -> str:
    asset = str(row.get("asset") or "").lower()
    if asset and asset not in NATIVE_ASSETS:
        return "token_transfer_to_cex"
    return "native_transfer_to_cex"


def _wallet_cex_flow_gate(surface: dict[str, Any]) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    token_count = 0
    native_count = 0
    heuristic_count = 0

    for row in surface.get("activity") or []:
        if not isinstance(row, dict):
            continue
        counterparty = row.get("counterparty") or {}
        cex = _contains_known_cex(
            counterparty.get("label"),
            counterparty.get("address"),
            row.get("dex"),
        )
        if not cex:
            continue
        direction = str(row.get("direction") or "").lower()
        event_type = str(row.get("event_type") or "").lower()
        if event_type != "transfer" or direction != "outflow":
            heuristic_count += 1
            flow_type = "cex_flow_hint"
        else:
            flow_type = _cex_flow_type(row)
            if flow_type == "token_transfer_to_cex":
                token_count += 1
            else:
                native_count += 1
        targets.append({
            "entity": cex,
            "label": counterparty.get("label") or cex,
            "address": counterparty.get("address"),
            "chain": row.get("chain"),
            "tx_hash": row.get("tx_hash"),
            "asset": row.get("asset"),
            "flow_type": flow_type,
            "source": "wallet_surface.activity",
        })

    for row in surface.get("counterparties") or []:
        if not isinstance(row, dict):
            continue
        cex = _contains_known_cex(row.get("label"), row.get("address"))
        if not cex:
            continue
        if any(target.get("tx_hash") and target.get("tx_hash") == row.get("latest_tx") for target in targets):
            continue
        heuristic_count += 1
        targets.append({
            "entity": cex,
            "label": row.get("label") or cex,
            "address": row.get("address"),
            "chain": row.get("latest_chain"),
            "tx_hash": row.get("latest_tx"),
            "asset": (row.get("assets") or [None])[0] if isinstance(row.get("assets"), list) else None,
            "flow_type": "label_heuristic_cex_counterparty",
            "source": "wallet_surface.counterparties",
        })

    confirmed = token_count + native_count
    status = "missing"
    if token_count:
        status = "confirmed_token_transfer"
    elif native_count:
        status = "confirmed_native_transfer"
    elif heuristic_count:
        status = "heuristic_hint"

    return {
        "status": status,
        "confirmed": confirmed > 0,
        "hint_only": confirmed == 0 and heuristic_count > 0,
        "deposit_count": confirmed,
        "token_transfer_count": token_count,
        "native_transfer_count": native_count,
        "heuristic_count": heuristic_count,
        "targets": targets[:8],
        "source_policy": (
            "CEX flow is confirmed only for timestamped outbound transfer rows to known CEX labels; "
            "aggregate labels are exposed as cex_flow_hint only"
        ),
        }


def _wallet_rpc_tx_enrichment(wallet: str, activity: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        from services.onchain_engine import enrich_wallet_events_from_rpc

        return enrich_wallet_events_from_rpc(wallet, activity, max_txs=10)
    except Exception as exc:
        return {
            "ok": False,
            "provider": "local_rpc",
            "wallet": wallet,
            "tx_candidates": 0,
            "tx_enriched": 0,
            "token_transfers_found": 0,
            "missing_proofs": ["rpc_targeted_wallet_tx_enrichment"],
            "error": str(exc)[:160],
            "source_policy": (
                "bounded RPC tx enrichment failed; no wallet links, labels, "
                "signals or execution settings are inferred"
            ),
        }


def _wallet_local_cex_deposit_surface(wallet: str) -> dict[str, Any]:
    try:
        from services.onchain_engine import get_wallet_cex_deposit_surface

        return get_wallet_cex_deposit_surface(wallet, limit=25)
    except Exception as exc:
        return {
            "ok": False,
            "confirmed": False,
            "hint_only": False,
            "deposits": [],
            "token_transfer_count": 0,
            "native_transfer_count": 0,
            "missing_proofs": ["local_cex_deposit_surface"],
            "error": str(exc)[:160],
            "source_policy": (
                "local CEX deposit surface failed; provider surface remains available "
                "but no local DB confirmation is inferred"
            ),
        }


def _merge_cex_flow_gate(provider_gate: dict[str, Any], local_surface: dict[str, Any]) -> dict[str, Any]:
    merged = dict(provider_gate or {})
    provider_targets = list(merged.get("targets") or [])
    local_deposits = list((local_surface or {}).get("deposits") or [])
    local_targets = [
        {
            "entity": deposit.get("entity"),
            "label": deposit.get("target_label") or deposit.get("entity"),
            "address": deposit.get("to_addr"),
            "chain": deposit.get("chain"),
            "tx_hash": deposit.get("tx_hash"),
            "asset": deposit.get("token") if deposit.get("transfer_type") == "token" else None,
            "flow_type": (
                "token_transfer_to_cex"
                if deposit.get("transfer_type") == "token"
                else "native_transfer_to_cex"
            ),
            "source": deposit.get("source") or "local_onchain_db",
            "confirmed": deposit.get("confirmed") is True,
            "proof_status": deposit.get("proof_status"),
        }
        for deposit in local_deposits
    ]
    local_confirmed = local_surface.get("confirmed") is True
    local_hint = local_surface.get("hint_only") is True
    local_token_count = int(local_surface.get("token_transfer_count") or 0)
    local_native_count = int(local_surface.get("native_transfer_count") or 0)
    token_count = int(merged.get("token_transfer_count") or 0) + local_token_count
    native_count = int(merged.get("native_transfer_count") or 0) + local_native_count
    confirmed_count = int(merged.get("deposit_count") or 0) + local_token_count + local_native_count
    heuristic_count = int(merged.get("heuristic_count") or 0) + int(local_surface.get("hint_count") or 0)

    status = str(merged.get("status") or "missing")
    if local_confirmed:
        status = "confirmed_local_db_cex_deposit"
    elif status == "missing" and local_hint:
        status = "local_db_cex_hint"

    merged.update({
        "status": status,
        "confirmed": bool(merged.get("confirmed")) or local_confirmed,
        "hint_only": not (bool(merged.get("confirmed")) or local_confirmed) and (bool(merged.get("hint_only")) or local_hint),
        "deposit_count": confirmed_count,
        "token_transfer_count": token_count,
        "native_transfer_count": native_count,
        "heuristic_count": heuristic_count,
        "targets": (provider_targets + local_targets)[:8],
        "local_cex_deposit_surface": local_surface,
        "source_policy": (
            "CEX flow merges provider activity hints with strict local DB confirmation; "
            "local confirmation requires RPC-enriched transfer plus source-backed CEX destination label"
        ),
    })
    return merged


def _wallet_investment_readiness(
    *,
    mode: str,
    readiness_score: int,
    blockers: list[str],
    source_trace: dict[str, Any],
    data_quality: dict[str, Any],
    token_risk_watchlist: list[dict[str, Any]],
    scorecard: dict[str, Any],
) -> dict[str, Any]:
    """Client-facing investment gate. It is intentionally non-executable."""
    missing: list[str] = []
    critical: list[str] = []
    token_sell_proof_ok = True
    liquidity_snapshot_ok = True

    if blockers:
        missing.extend(blockers)
    if int(scorecard.get("providers_ok") or 0) <= 0:
        missing.append("provider_pnl_or_wallet_evidence")
    if data_quality.get("token_sellability") == "needs_token_level_proof":
        missing.append("token_sellability_contract")
    if data_quality.get("source_freshness") in {"rpc_fallback_only", "no_recent_sample", None}:
        missing.append("fresh_timestamped_flow_sample")
    if not source_trace:
        missing.append("source_trace")

    replay_missing = [str(item) for item in (data_quality.get("replay_missing_proofs") or []) if str(item).strip()]
    missing.extend(f"replay:{item}" for item in replay_missing)

    freshness = data_quality.get("source_freshness_detail") or {}
    freshness_policy = str(freshness.get("freshness_policy") or data_quality.get("source_freshness") or "")
    freshness_age = freshness.get("age_seconds")
    if freshness_policy in {"missing_timestamp", "stale_over_7d", "rpc_fallback_only", "no_recent_sample", ""}:
        missing.append("fresh_timestamped_flow_sample")
    if isinstance(freshness_age, (int, float)) and freshness_age > FRESH_FLOW_MAX_AGE_SECONDS:
        missing.append("fresh_timestamped_flow_sample")
    for key in ("latest_seen", "source", "provider", "chain", "tx_hash"):
        if not freshness.get(key):
            missing.append(f"source_freshness:{key}")

    cex_flow = data_quality.get("cex_flow_gate") or {}
    if cex_flow.get("status") == "heuristic_hint" or cex_flow.get("hint_only") is True:
        missing.append("cex_flow_confirmation")
    elif cex_flow.get("confirmed") is not True:
        missing.append("confirmed_cex_flow_or_transfer_surface")

    for row in token_risk_watchlist:
        risk_flag = str(row.get("risk_flag") or "")
        if row.get("block_trade") is True or row.get("copy_allowed") is False:
            critical.append(f"{row.get('asset') or 'unknown'}:{risk_flag or 'copy_blocked'}")
        row_missing = [str(item) for item in (row.get("missing_proofs") or []) if str(item).strip()]
        if row_missing:
            missing.extend(f"{row.get('asset') or 'unknown'}:{item}" for item in row_missing[:4])
            asset = row.get("asset") or "unknown"
            if "successful_sell_proof" in row_missing:
                token_sell_proof_ok = False
                missing.append(f"{asset}:sell_proof_missing")
            if "liquidity_snapshot" in row_missing:
                liquidity_snapshot_ok = False
                missing.append(f"{asset}:liquidity_snapshot_missing")
        elif row.get("copy_allowed") is not True:
            missing.append(f"{row.get('asset') or 'unknown'}:sellability_not_proven")
        if not row.get("source_policy"):
            missing.append(f"{row.get('asset') or 'unknown'}:source_policy")

    replay_gates = data_quality.get("replay_proof_gates") or {}

    status = "not_ready"
    if critical:
        status = "not_ready"
    elif not blockers and readiness_score >= 75:
        status = "manual_review_only"
    elif readiness_score >= 45:
        status = "research_ready"

    verdict = "inconclusive" if missing or critical else "manual_review_only"
    return {
        "status": status,
        "verdict": verdict,
        "readiness_score": readiness_score,
        "client_investment_enabled": False,
        "execution_enabled": False,
        "copy_trade_enabled": False,
        "profit_guarantee_allowed": False,
        "trade_signal_allowed": False,
        "manual_review_allowed": status == "manual_review_only",
        "critical_blockers": critical,
        "missing_proofs": _dedupe_text(missing),
        "required_gates": {
            "wallet_evidence": int(scorecard.get("providers_ok") or 0) > 0,
            "replay_available": scorecard.get("estimated_value") is not None or scorecard.get("roi_pct") is not None,
            "token_sellability": data_quality.get("token_sellability") != "needs_token_level_proof",
            "token_sell_proof_ok": token_sell_proof_ok,
            "liquidity_snapshot_ok": liquidity_snapshot_ok,
            "entry_price_proof": replay_gates.get("entry_price_proof") is True,
            "exit_price_proof": replay_gates.get("exit_price_proof") is True,
            "liquidity_at_entry": replay_gates.get("liquidity_at_entry") is True,
            "liquidity_at_exit": replay_gates.get("liquidity_at_exit") is True,
            "slippage_model": replay_gates.get("slippage_model") is True,
            "fee_model": replay_gates.get("fee_model") is True,
            "source_trace": bool(source_trace),
            "freshness": (
                freshness_policy not in {"missing_timestamp", "stale_over_7d", "rpc_fallback_only", "no_recent_sample", ""}
                and not any(str(item).startswith("source_freshness:") for item in missing)
            ),
            "confirmed_cex_flow": cex_flow.get("confirmed") is True,
            "no_critical_token_blockers": not critical,
            "explicit_client_consent": False,
            "execution_system_audited": False,
        },
        "source_policy": (
            "client investment stays disabled until wallet evidence, replay, token sellability, "
            "fresh source trace, explicit consent and an audited execution system are all present"
        ),
        "next_safe_action": (
            "Fix critical token blockers before any client-facing action."
            if critical
            else "Collect missing proofs and keep the result as research-only."
            if missing
            else "Manual review can start; execution remains disabled."
        ),
    }


def _dedupe_text(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result[:20]


# ── Legacy wallet endpoints (SPECIFIC paths first) ───────────────────────────

@router.get("/wallet/probe/{wallet}")
async def _wallet_probe(
    wallet: str,
    limit: int = 20,
    timeframe: str = "30d",
    chains: str | None = None,
):
    wallet = _validate_wallet(wallet)
    from services.alpha_wallets import probe_wallet_candidate
    return await asyncio.to_thread(
        probe_wallet_candidate,
        wallet,
        source="all",
        timeframe=timeframe,
        limit=limit,
        chains=chains,
    )


@router.post("/wallet/verify")
async def _wallet_verify(payload: dict, request: Request, response: Response):
    address = _validate_wallet(str(payload.get("address") or ""))
    wallet_type = str(payload.get("type") or "evm").lower()
    provider = str(payload.get("provider") or "unknown")[:80]
    network = str(payload.get("network") or "unknown")[:80]
    message = str(payload.get("message") or "")
    signature = str(payload.get("signature") or "")

    if wallet_type == "evm":
        parsed_message = _parse_wallet_verification_message(message, address, network)
        if not _is_probable_evm_signature(signature):
            raise HTTPException(400, "Invalid EVM signature shape.")
        if not Account or not encode_defunct:
            raise HTTPException(
                503,
                "EVM signature verification is unavailable on this server. Install the verifier dependency before trusting wallet ownership.",
            )
        recovered = _recover_evm_signer(message, signature)
        verified = recovered == address
        method = "personal_sign_recovered"
        if not verified:
            raise HTTPException(401, "Signature signer does not match wallet address.")
    else:
        raise HTTPException(501, "Only EVM wallet ownership verification is supported right now.")

    proof = _save_wallet_proof({
        "address": address,
        "type": wallet_type,
        "provider": provider,
        "network": network,
        "verified": verified,
        "method": method,
        "recovery_available": bool(Account and encode_defunct),
        "message_hash": _sha256_text(message),
        "signature_hash": _sha256_text(signature),
        "signed_at": parsed_message["signed_at"],
        "verified_at": int(time.time()),
        "source": "core_equity_client_wallet",
    })
    session_payload = {
        "wallet": address,
        "network": network,
        "provider": provider,
        "iat": int(time.time()),
        "exp": int(time.time()) + CLIENT_SESSION_TTL_SECONDS,
        "proof_verified_at": proof["verified_at"],
        "scope": "alpha_lab_read_only",
    }
    response.set_cookie(
        CLIENT_SESSION_COOKIE,
        _sign_client_session(session_payload),
        max_age=CLIENT_SESSION_TTL_SECONDS,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/api/alpha",
    )

    return {
        "ok": True,
        "verified": verified,
        "address": address,
        "provider": provider,
        "network": network,
        "method": method,
        "recovery_available": bool(Account and encode_defunct),
        "verified_at": proof["verified_at"],
        "session": {
            "ok": True,
            "scope": session_payload["scope"],
            "expires_at": session_payload["exp"],
        },
    }


@router.get("/wallet/ownership/{wallet}")
async def _wallet_ownership(wallet: str, core_client_session: str | None = Cookie(default=None)):
    address = _validate_wallet(wallet)
    proof = _get_wallet_proof(address)
    status = _wallet_proof_status(proof)
    session = _read_client_session(core_client_session)
    session_matches = bool(
        session
        and str(session.get("wallet", "")).lower() == address.lower()
        and str(session.get("scope") or "") == "alpha_lab_read_only"
    )
    return {
        "ok": True,
        "address": address,
        "verified": status["verified"],
        "session_active": session_matches,
        "session_expires_at": session.get("exp") if session_matches else None,
        "expired": status["expired"],
        "proof_age_seconds": status["proof_age_seconds"],
        "expires_at": status["expires_at"],
        "method": proof.get("method") if proof else None,
        "provider": proof.get("provider") if proof else None,
        "network": proof.get("network") if proof else None,
        "verified_at": proof.get("verified_at") if proof else None,
        "recovery_available": bool(Account and encode_defunct),
        "source": status["source"],
        "execution_gate": status["execution_gate"] if not status["verified"] or session_matches else "client_session_required",
    }


@router.get("/wallet/copy-plan/{wallet}")
async def _wallet_copy_plan(
    wallet: str,
    capital: float = 100.0,
    limit: int = 20,
    timeframe: str = "30d",
    chains: str | None = None,
    core_client_session: str | None = Cookie(default=None),
):
    wallet = _validate_wallet(wallet)
    _require_client_wallet_session(wallet, core_client_session)
    from services.alpha_wallets import probe_wallet_candidate

    probe = await asyncio.to_thread(
        probe_wallet_candidate,
        wallet,
        source="all",
        timeframe=timeframe,
        limit=limit,
        chains=chains,
    )
    status = str(probe.get("status") or "")
    preview = probe.get("copy_preview") or {}
    risk = probe.get("risk_summary") or {}
    asset_focus = probe.get("asset_focus") or []
    suspicious_assets = {
        str(asset).lower()
        for asset in risk.get("suspicious_assets", [])
        if str(asset).strip()
    }
    ready = status == "candidate" and probe.get("confidence") in {"high", "medium"}
    scorecard = {
        "status": status,
        "label": probe.get("status_label"),
        "confidence": probe.get("confidence"),
        "estimated_value": preview.get("estimated_value"),
        "roi_pct": preview.get("roi_pct"),
        "suspect_rows": risk.get("untrusted_rows", 0),
        "blocked_rows": risk.get("blocked_rows", 0),
        "providers_ok": (probe.get("provider_health") or {}).get("ok", 0),
        "providers_total": (probe.get("provider_health") or {}).get("total", 0),
    }
    copy_blockers: list[str] = []
    if not ready:
        copy_blockers.append("Wallet is not ready for manual review.")
    if int(risk.get("blocked_rows") or 0) > 0:
        copy_blockers.append("Blocked/freeze/honeypot-like rows must be filtered first.")
    token_risk_watchlist = _wallet_token_risk_watchlist(probe)
    if not token_risk_watchlist:
        token_risk_watchlist = [
            {
                "asset": item.get("asset"),
                "chain": item.get("chain"),
                "risk_flag": "suspicious_name_or_provider_flag" if str(item.get("asset") or "").lower() in suspicious_assets else "needs_sellability_proof",
                "copy_allowed": False if str(item.get("asset") or "").lower() in suspicious_assets else None,
            }
            for item in asset_focus[:6]
        ]
    source_freshness_detail = {
        "latest_seen": None,
        "age_seconds": None,
        "source": "alpha_wallets.probe_wallet_candidate",
        "provider": "copy_plan_probe_only",
        "chain": chains,
        "tx_hash": None,
        "freshness_policy": "missing_timestamp",
        "source_policy": "copy-plan does not include wallet surface rows; automation-plan is required for timestamped flow proof",
    }
    cex_flow_gate = _wallet_cex_flow_gate({})
    source_trace = {
        "probe": "alpha_wallets.probe_wallet_candidate",
        "providers_ok": scorecard["providers_ok"],
        "providers_total": scorecard["providers_total"],
        "freshness_policy": source_freshness_detail["freshness_policy"],
        "source_freshness": source_freshness_detail,
        "cex_flow_gate": cex_flow_gate,
    }
    data_quality = {
        "source_freshness": source_freshness_detail["freshness_policy"],
        "source_freshness_detail": source_freshness_detail,
        "cex_flow_gate": cex_flow_gate,
        "token_sellability": "needs_token_level_proof",
    }

    return {
        "ok": True,
        "wallet": wallet,
        "capital": round(max(0.0, capital), 2),
        "mode": "manual_review_ready" if ready else "watch_only",
        "execution_enabled": False,
        "reason": (
            "Wallet has enough trusted proof for a manual copy review."
            if ready
            else "Automation stays disabled until profit, sellability and provider coverage are proven."
        ),
        "scorecard": scorecard,
        "allocation": [
            {
                "asset": item.get("asset"),
                "chain": item.get("chain"),
                "max_weight_pct": round(min(25.0, max(5.0, float(item.get("amount_usd") or 0.0) / 1000.0)), 2),
                "evidence_events": item.get("events", 0),
                "observed_usd": item.get("amount_usd", 0),
            }
            for item in asset_focus[:6]
            if str(item.get("asset") or "").lower() not in suspicious_assets
        ],
        "guards": [
            "No automatic trade execution yet.",
            "Require sell proof and liquidity before copying any token.",
            "Block suspicious/freeze/honeypot/fake-profit assets.",
            "Cap one asset at 25% until wallet repeatability is proven.",
            "Keep source trace: Cielo/Zerion/RPC/provider status per decision.",
        ],
        "investment_readiness": _wallet_investment_readiness(
            mode="manual_review_ready" if ready else "watch_only",
            readiness_score=65 if ready else 25,
            blockers=copy_blockers,
            source_trace=source_trace,
            data_quality=data_quality,
            token_risk_watchlist=token_risk_watchlist,
            scorecard=scorecard,
        ),
        "requirements": probe.get("requirements", []),
    }


@router.get("/wallet/copy-backtest/{wallet}")
async def _wallet_copy_backtest(
    wallet: str,
    capital: float = 100.0,
    limit: int = 30,
    timeframe: str = "30d",
    chains: str | None = None,
    max_trade_pct: float = 0.20,
    slippage_bps: float = 75.0,
    fee_bps: float = 20.0,
    core_client_session: str | None = Cookie(default=None),
):
    wallet = _validate_wallet(wallet)
    _require_client_wallet_session(wallet, core_client_session)
    from services.alpha_wallets import get_wallet_surface, probe_wallet_candidate

    probe, surface = await asyncio.gather(
        asyncio.to_thread(
            probe_wallet_candidate,
            wallet,
            source="all",
            timeframe=timeframe,
            limit=limit,
            chains=chains,
        ),
        asyncio.to_thread(get_wallet_surface, wallet, limit=max(10, limit), chains=chains),
    )
    return _wallet_copy_backtest_from_surface(
        wallet,
        surface,
        probe,
        capital=capital,
        max_trade_pct=max_trade_pct,
        slippage_bps=slippage_bps,
        fee_bps=fee_bps,
    )


@router.get("/wallet/automation-plan/{wallet}")
async def _wallet_automation_plan(
    wallet: str,
    capital: float = 100.0,
    limit: int = 20,
    timeframe: str = "30d",
    chains: str | None = None,
    persist_rpc: bool = True,
    refresh_after_hours: int = 12,
    force_rpc_refresh: bool = False,
    core_client_session: str | None = Cookie(default=None),
    x_core_client_action: str | None = Header(default=None),
):
    """Read-only client automation plan.

    This endpoint is the safe bridge between a connected wallet and Alpha Lab:
    it can decide what to analyze next, but it never enables execution.
    """
    wallet = _validate_wallet(wallet)
    _require_client_wallet_session(wallet, core_client_session)
    from services.alpha_wallets import (
        get_wallet_identity_graph,
        get_wallet_surface,
        probe_wallet_candidate,
    )
    from services.onchain_engine import get_rpc_wallet_source, persist_wallet_analysis_rpc_snapshot

    probe, surface, graph, rpc_summary, rpc_source = await asyncio.gather(
        asyncio.to_thread(
            probe_wallet_candidate,
            wallet,
            source="all",
            timeframe=timeframe,
            limit=limit,
            chains=chains,
        ),
        asyncio.to_thread(get_wallet_surface, wallet, limit=max(10, limit), chains=chains),
        asyncio.to_thread(get_wallet_identity_graph, wallet, limit=max(10, limit), chains=chains),
        asyncio.to_thread(get_wallet_summary, wallet),
        asyncio.to_thread(get_rpc_wallet_source, wallet, chains),
    )
    rpc_persist_result: dict[str, Any] | None = None
    if persist_rpc and str(wallet).startswith("0x"):
        _require_explicit_client_write(
            x_core_client_action,
            "persist-rpc-snapshot",
            "wallet RPC snapshot persistence",
        )
        rpc_persist_result = await asyncio.to_thread(
            persist_wallet_analysis_rpc_snapshot,
            wallet,
            chains=chains,
            include_tokens=True,
            refresh_after_hours=refresh_after_hours,
            force_refresh=force_rpc_refresh,
        )
        rpc_source = await asyncio.to_thread(get_rpc_wallet_source, wallet, chains)

    status = str(probe.get("status") or "unknown")
    confidence = str(probe.get("confidence") or "low")
    risk = probe.get("risk_summary") or {}
    provider_health = probe.get("provider_health") or {}
    preview = probe.get("copy_preview") or {}
    surface_summary = surface.get("summary") or {}
    graph_summary = graph.get("summary") or {}
    activity = [row for row in surface.get("activity") or [] if isinstance(row, dict)]
    latest_seen = max((str(row.get("timestamp") or "") for row in activity), default=None) or None
    source_freshness_detail = _wallet_source_freshness(surface)
    provider_cex_flow_gate = _wallet_cex_flow_gate(surface)
    local_cex_deposit_surface = _wallet_local_cex_deposit_surface(wallet)
    cex_flow_gate = _merge_cex_flow_gate(provider_cex_flow_gate, local_cex_deposit_surface)
    chain_coverage = _wallet_chain_coverage(surface, probe)
    rpc_chain_rows = _wallet_rpc_chain_rows(rpc_summary, rpc_source)
    token_risk_watchlist = _wallet_token_risk_watchlist(probe)
    rpc_token_watchlist = _wallet_rpc_token_watchlist(rpc_summary)
    if not chain_coverage:
        chain_coverage = [
            {
                "chain": row["chain"],
                "events": row["tx_count"],
                "amount_usd": row["native_value_usd"],
                "assets": [f"{row['token_count']} tracked tokens"] if row["token_count"] else [],
            }
            for row in rpc_chain_rows
        ]
    if not token_risk_watchlist:
        token_risk_watchlist = [
            {
                "asset": row["asset"],
                "chain": row["chain"],
                "events": 0,
                "observed_usd": 0.0,
                "risk_flag": row["risk_flag"],
                "copy_allowed": row["copy_allowed"],
            }
            for row in rpc_token_watchlist
        ]

    confidence_score = {"high": 35, "medium": 24, "low": 10}.get(confidence, 8)
    provider_total = int(provider_health.get("total") or 0)
    provider_ok = int(provider_health.get("ok") or 0)
    provider_score = 20 if provider_total and provider_ok >= provider_total else 12 if provider_ok else 0
    flow_score = 15 if int(surface_summary.get("events") or 0) >= 10 else 8 if int(surface_summary.get("events") or 0) else 0
    graph_score = 15 if int(graph_summary.get("edges") or 0) >= 5 else 8 if int(graph_summary.get("edges") or 0) else 0
    rpc_backbone_score = 15 if rpc_chain_rows and any(row["tx_count"] > 0 or row["native_value_usd"] > 0 for row in rpc_chain_rows) else 5 if rpc_chain_rows else 0
    risk_penalty = min(25, int(risk.get("untrusted_rows") or 0) * 4 + int(risk.get("blocked_rows") or 0) * 8)
    flow_confidence_score = max(0, min(100, provider_score + flow_score + graph_score + rpc_backbone_score + min(20, len(chain_coverage) * 5) - risk_penalty))
    readiness_score = max(0, min(100, confidence_score + provider_score + flow_score + graph_score + rpc_backbone_score + 15 - risk_penalty))

    blockers: list[str] = []
    if provider_ok == 0:
        blockers.append("No live provider confirmed this wallet yet.")
    if status != "candidate":
        blockers.append("Wallet is not a proven copy candidate yet.")
    if int(risk.get("blocked_rows") or 0) > 0:
        blockers.append("Blocked/freeze/honeypot-like rows must be filtered first.")
    if int(surface_summary.get("events") or 0) == 0:
        blockers.append("No recent transfer surface was observed.")
    if int(graph_summary.get("edges") or 0) == 0:
        blockers.append("Identity graph has no useful linked counterparties yet.")
    if rpc_chain_rows and provider_ok == 0:
        blockers.append("RPC fallback exists, but provider PnL/copy evidence is still missing.")

    mode = "watch_only"
    if readiness_score >= 75 and not blockers:
        mode = "manual_review_ready"
    elif readiness_score >= 45:
        mode = "research_ready"
    source_trace = {
        "probe": "alpha_wallets.probe_wallet_candidate",
        "surface": "alpha_wallets.get_wallet_surface",
        "graph": "alpha_wallets.get_wallet_identity_graph",
        "providers_ok": provider_ok,
        "providers_total": provider_total,
        "rpc_events": int(surface_summary.get("events") or 0),
        "graph_edges": int(graph_summary.get("edges") or 0),
        "freshness_policy": (
            rpc_persist_result.get("freshness_policy")
            if rpc_persist_result
            else source_freshness_detail["freshness_policy"]
        ),
        "latest_seen": latest_seen,
        "source_freshness": source_freshness_detail,
        "provider_cex_flow_gate": provider_cex_flow_gate,
        "cex_flow_gate": cex_flow_gate,
        "local_cex_deposit_surface": local_cex_deposit_surface,
        "rpc_source_rows": int(rpc_source.get("total") or 0),
    }
    data_quality = {
        "chain_count": len(chain_coverage),
        "asset_count": len({str(item.get("asset") or "").lower() for item in probe.get("asset_focus") or [] if item.get("asset")}),
        "flow_confidence_score": flow_confidence_score,
        "rpc_backbone_score": rpc_backbone_score,
        "source_freshness": source_freshness_detail["freshness_policy"],
        "source_freshness_detail": source_freshness_detail,
        "provider_cex_flow_gate": provider_cex_flow_gate,
        "cex_flow_gate": cex_flow_gate,
        "local_cex_deposit_surface": local_cex_deposit_surface,
        "holder_confidence": "not_available_for_wallet_probe",
        "token_sellability": "needs_token_level_proof",
    }
    scorecard = {
        "status": status,
        "confidence": confidence,
        "estimated_value": preview.get("estimated_value"),
        "roi_pct": preview.get("roi_pct"),
        "untrusted_rows": int(risk.get("untrusted_rows") or 0),
        "blocked_rows": int(risk.get("blocked_rows") or 0),
        "providers_ok": provider_ok,
        "providers_total": provider_total,
    }

    return {
        "ok": True,
        "wallet": wallet,
        "capital": round(max(0.0, capital), 2),
        "mode": mode,
        "execution_enabled": False,
        "readiness_score": readiness_score,
        "decision": (
            "Manual review can start, but execution remains disabled."
            if mode == "manual_review_ready"
            else "Keep analyzing before any copy decision."
        ),
        "blockers": blockers,
        "next_actions": [
            "Refresh provider/RPC evidence for this wallet.",
            "Confirm sellability and liquidity for every copied token.",
            "Reject fake PnL from frozen, blacklisted or illiquid assets.",
            "Require explicit client consent before any future execution module.",
        ],
        "source_trace": source_trace,
        "data_quality": data_quality,
        "chain_coverage": chain_coverage,
        "token_risk_watchlist": token_risk_watchlist,
        "rpc_backbone": {
            "ok": bool(rpc_summary.get("ok")) or bool(rpc_source.get("ok")),
            "wallet_label": rpc_summary.get("label"),
            "primary_chain": rpc_summary.get("chain"),
            "tx_count": rpc_summary.get("tx_count"),
            "swap_count": rpc_summary.get("swap_count"),
            "volume": rpc_summary.get("volume"),
            "net_worth_usd": rpc_summary.get("net_worth_usd"),
            "source_rows": rpc_source.get("total"),
            "traceable_rows": rpc_source.get("traceable_rows"),
            "chain_rows": rpc_chain_rows,
            "persisted_snapshot": rpc_persist_result,
        },
        "scorecard": scorecard,
        "investment_readiness": _wallet_investment_readiness(
            mode=mode,
            readiness_score=readiness_score,
            blockers=blockers,
            source_trace=source_trace,
            data_quality=data_quality,
            token_risk_watchlist=token_risk_watchlist,
            scorecard=scorecard,
        ),
        "rails": {
            "contract": "read_only_analysis_plan",
            "execution_gate": "hard_disabled_in_code",
            "private_key_required": False,
            "signature_required_for_analysis": False,
            "client_visible": True,
            "trusted_auto_execution": False,
        },
    }


@router.get("/wallet/surface/{wallet}")
async def _wallet_surface(
    wallet: str,
    limit: int = 30,
    chains: str | None = None,
):
    wallet = _validate_wallet(wallet)
    from services.alpha_wallets import get_wallet_surface
    return await asyncio.to_thread(get_wallet_surface, wallet, limit=limit, chains=chains)


@router.get("/wallet/graph/{wallet}")
async def _wallet_graph(
    wallet: str,
    limit: int = 40,
    chains: str | None = None,
):
    wallet = _validate_wallet(wallet)
    from services.alpha_wallets import get_wallet_identity_graph
    return await asyncio.to_thread(get_wallet_identity_graph, wallet, limit=limit, chains=chains)


@router.get("/wallet/status")
async def _wallet_status():
    from services.alpha_wallets import get_wallet_provider_status
    return await asyncio.to_thread(get_wallet_provider_status)


@router.get("/wallet/discovery")
async def _wallet_discovery(
    limit: int = 12,
    feed_limit: int = 50,
    tx_types: str = "swap",
    new_trades: str = "true",
    cache: str = "true",
    min_usd: float | None = None,
    tokens: str | None = None,
    chains: str | None = None,
):
    from services.alpha_wallets import get_wallet_discovery
    return await asyncio.to_thread(
        get_wallet_discovery,
        limit=limit,
        feed_limit=feed_limit,
        chains=chains,
        tx_types=tx_types,
        tokens=tokens,
        min_usd=min_usd,
        new_trades=new_trades.lower() == "true",
        use_cache=cache.lower() == "true",
    )


# ── NEW: Unified wallet endpoint (CATCH-ALL last) ────────────────────────────

@router.get("/wallet/summary/{address}")
async def _wallet(address: str):
    """Unified wallet summary across all chains.

    Returns: balance, swap_count, volume, label, tx_count
    """
    return await asyncio.to_thread(get_wallet_summary, address)


# ── Premium intelligence ─────────────────────────────────────────────────────

@router.get("/intelligence")
async def _premium_intelligence(limit: int = 20):
    from services.scrapling_intelligence import get_premium_intelligence
    return await asyncio.to_thread(get_premium_intelligence, limit)


@router.get("/premium/stats")
async def _premium_stats(
    wallet: str | None = None,
    feed_limit: int = 100,
):
    from services.alpha_premium_data import get_premium_alpha_stats
    return await asyncio.to_thread(get_premium_alpha_stats, wallet, feed_limit)


__all__ = []
