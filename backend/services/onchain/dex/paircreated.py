"""Bounded DEX PairCreated/indexer helpers.

These helpers perform no persistence and are kept behind the
``services.onchain_engine`` compatibility facade for existing route/tests.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from services.onchain.core.addresses import _is_evm_address
from services.onchain.core.constants import (
    BLOCKSCOUT_API_BASE_URLS,
    PAIR_CREATED_TOPIC,
    SQD_PORTAL_DATASET_URLS,
)
from services.onchain.events.parsers import _hex_to_int_or_none
from services.onchain_chains import normalize_chain as _normalize_chain


def _decode_paircreated_pair_address(log: dict[str, Any]) -> str | None:
    data = str((log or {}).get("data") or "").strip().lower()
    if data.startswith("0x"):
        data = data[2:]
    if len(data) < 64:
        return None
    pair = "0x" + data[:64][-40:]
    return pair if _is_evm_address(pair) else None


def _blockscout_legacy_paircreated_logs(
    chain: str,
    log_filter: dict[str, Any],
    timeout: int = 6,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Fetch bounded PairCreated logs from Blockscout's no-key legacy logs API."""
    normalized_chain = _normalize_chain(chain or "")
    base = BLOCKSCOUT_API_BASE_URLS.get(normalized_chain)
    if not base:
        return [], None, "blockscout_chain_not_supported"
    address = str((log_filter or {}).get("address") or "").strip().lower()
    topics = [str(topic or "").strip().lower() for topic in ((log_filter or {}).get("topics") or [])]
    from_block = _hex_to_int_or_none((log_filter or {}).get("fromBlock"))
    to_block = _hex_to_int_or_none((log_filter or {}).get("toBlock"))
    if not (_is_evm_address(address) and len(topics) >= 3 and topics[0] == PAIR_CREATED_TOPIC):
        return [], None, "blockscout_logs_filter_missing_or_invalid"
    if from_block is None or to_block is None:
        return [], None, "blockscout_logs_block_range_missing"

    def _fetch_v2_address_logs(fallback_reason: str) -> tuple[list[dict[str, Any]], str | None, str | None]:
        v2_url = f"{base}/addresses/{urllib.parse.quote(address)}/logs"
        v2_req = urllib.request.Request(
            v2_url,
            headers={"Accept": "application/json", "User-Agent": "CoreEquityPairCreatedLookup/1.0"},
        )
        try:
            with urllib.request.urlopen(v2_req, timeout=max(2, min(int(timeout or 6), 15))) as resp:
                v2_payload = json.loads(resp.read(1_000_000).decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            return [], v2_url, f"{fallback_reason};blockscout_v2_logs_http_error:{exc.code}"
        except Exception as exc:
            return [], v2_url, f"{fallback_reason};blockscout_v2_logs_error:{type(exc).__name__}"
        if not isinstance(v2_payload, dict):
            return [], v2_url, f"{fallback_reason};blockscout_v2_logs_invalid_payload"
        items = v2_payload.get("items")
        if not isinstance(items, list):
            return [], v2_url, f"{fallback_reason};blockscout_v2_logs_missing_items"
        matching_items: list[dict[str, Any]] = []
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            item_topics = [str(topic or "").strip().lower() for topic in (item.get("topics") or [])]
            block_number = _hex_to_int_or_none(item.get("blockNumber")) or _hex_to_int_or_none(item.get("block_number"))
            if block_number is not None and not (from_block <= block_number <= to_block):
                continue
            if len(item_topics) < 3 or item_topics[:3] != topics[:3]:
                continue
            normalized_item = dict(item)
            normalized_item.setdefault("address", address)
            matching_items.append(normalized_item)
        if matching_items:
            return matching_items, v2_url, None
        return [], v2_url, f"{fallback_reason};blockscout_v2_no_matching_paircreated_in_first_page"

    params = {
        "module": "logs",
        "action": "getLogs",
        "fromBlock": str(from_block),
        "toBlock": str(to_block),
        "address": address,
        "topic0": topics[0],
        "topic1": topics[1],
        "topic2": topics[2],
        "topic0_1_opr": "and",
        "topic0_2_opr": "and",
    }
    legacy_base = base.replace("/api/v2", "/api")
    url = f"{legacy_base}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "CoreEquityPairCreatedLookup/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=max(2, min(int(timeout or 6), 15))) as resp:
            payload = json.loads(resp.read(1_000_000).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return _fetch_v2_address_logs(f"blockscout_legacy_logs_http_error:{exc.code}")
        return [], url, f"blockscout_logs_http_error:{exc.code}"
    except Exception as exc:
        return [], url, f"blockscout_logs_error:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return [], url, "blockscout_logs_invalid_payload"
    result = payload.get("result")
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)], url, None
    message = str(payload.get("message") or payload.get("result") or "").strip()
    status = str(payload.get("status") or "").strip()
    if status == "0" and re.search(r"no records|not found|empty", message, flags=re.I):
        return [], url, "blockscout_logs_no_records"
    return [], url, f"blockscout_logs_unexpected_response:{message[:120] or status or 'missing_result'}"


def _sqd_portal_api_key() -> tuple[str | None, str | None]:
    for source in ("SQD_PORTAL_API_KEY", "CORE_SQD_PORTAL_API_KEY", "SUBSQUID_API_KEY"):
        key = os.getenv(source, "").strip()
        if key:
            return key, source
    return None, None


def _sqd_portal_paircreated_logs(
    chain: str,
    log_filter: dict[str, Any],
    timeout: int = 6,
) -> tuple[list[dict[str, Any]], str | None, str | None, str | None, dict[str, Any]]:
    """Fetch bounded PairCreated logs from SQD Portal; caller must keep results non-persistent."""
    normalized_chain = _normalize_chain(chain or "")
    endpoint = SQD_PORTAL_DATASET_URLS.get(normalized_chain)
    if not endpoint:
        return [], None, "sqd_chain_not_supported", None, {}
    address = str((log_filter or {}).get("address") or "").strip().lower()
    topics = [str(topic or "").strip().lower() for topic in ((log_filter or {}).get("topics") or [])]
    from_block = _hex_to_int_or_none((log_filter or {}).get("fromBlock"))
    to_block = _hex_to_int_or_none((log_filter or {}).get("toBlock"))
    if not (_is_evm_address(address) and len(topics) >= 3 and topics[0] == PAIR_CREATED_TOPIC):
        return [], endpoint, "sqd_logs_filter_missing_or_invalid", None, {}
    if from_block is None or to_block is None:
        return [], endpoint, "sqd_logs_block_range_missing", None, {}
    api_key, key_source = _sqd_portal_api_key()
    payload = {
        "type": "evm",
        "fromBlock": int(from_block),
        "toBlock": int(to_block),
        "fields": {
            "block": {"number": True, "hash": True, "timestamp": True},
            "log": {
                "address": True,
                "topics": True,
                "data": True,
                "transactionHash": True,
                "logIndex": True,
            },
        },
        "logs": [{
            "address": [address],
            "topic0": [topics[0]],
            "topic1": [topics[1]],
            "topic2": [topics[2]],
        }],
    }
    headers = {
        "Accept": "application/x-ndjson, application/json",
        "Content-Type": "application/json",
        "User-Agent": "CoreEquitySQDPairCreatedLookup/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request_preview = {
        "endpoint": endpoint,
        "payload": payload,
        "api_key_configured": bool(api_key),
        "api_key_source": key_source,
        "authorization_header_redacted": bool(api_key),
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    max_response_bytes = 8_000_000
    max_stream_logs = 5_000
    try:
        with urllib.request.urlopen(req, timeout=max(2, min(int(timeout or 6), 15))) as resp:
            chunks: list[bytes] = []
            total_bytes = 0
            while total_bytes < max_response_bytes:
                chunk = resp.read(min(262_144, max_response_bytes - total_bytes))
                if not chunk:
                    break
                chunks.append(chunk)
                total_bytes += len(chunk)
            response_truncated = total_bytes >= max_response_bytes
            body = b"".join(chunks).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return [], endpoint, f"sqd_portal_http_error:{exc.code}", key_source, request_preview
    except Exception as exc:
        return [], endpoint, f"sqd_portal_error:{type(exc).__name__}", key_source, request_preview

    logs: list[dict[str, Any]] = []
    try:
        lines = [line for line in body.splitlines() if line.strip()]
        if response_truncated and body and not body.endswith(("\n", "\r")) and lines:
            # SQD streams JSONL by block. A dense range can exceed our read cap and leave
            # the final line incomplete; keep complete records instead of failing the call.
            lines = lines[:-1]
        for line in lines:
            if len(logs) >= max_stream_logs:
                break
            item = json.loads(line)
            if not isinstance(item, dict):
                continue
            header = item.get("header") if isinstance(item.get("header"), dict) else {}
            block_number = header.get("number")
            block_hash = header.get("hash")
            block_timestamp = header.get("timestamp")
            for raw_log in item.get("logs") or []:
                if not isinstance(raw_log, dict):
                    continue
                normalized_log = dict(raw_log)
                normalized_log.setdefault("blockNumber", block_number)
                normalized_log.setdefault("blockHash", block_hash)
                normalized_log.setdefault("timestamp", block_timestamp)
                logs.append(normalized_log)
                if len(logs) >= max_stream_logs:
                    break
    except Exception as exc:
        return [], endpoint, f"sqd_portal_parse_error:{type(exc).__name__}", key_source, request_preview
    if response_truncated:
        return logs, endpoint, (
            "sqd_portal_response_truncated_after_partial_logs"
            if logs else "sqd_portal_response_too_large_before_first_record"
        ), key_source, request_preview
    return logs, endpoint, None, key_source, request_preview


def _sqd_portal_event_logs(
    chain: str,
    log_filter: dict[str, Any],
    timeout: int = 6,
) -> tuple[list[dict[str, Any]], str | None, str | None, str | None, dict[str, Any]]:
    """Fetch bounded generic EVM logs from SQD Portal; caller must not persist them directly."""
    normalized_chain = _normalize_chain(chain or "")
    endpoint = SQD_PORTAL_DATASET_URLS.get(normalized_chain)
    if not endpoint:
        return [], None, "sqd_chain_not_supported", None, {}
    address = str((log_filter or {}).get("address") or "").strip().lower()
    topics = [
        str(topic).strip().lower() if topic is not None else None
        for topic in ((log_filter or {}).get("topics") or [])
    ]
    from_block = _hex_to_int_or_none((log_filter or {}).get("fromBlock"))
    to_block = _hex_to_int_or_none((log_filter or {}).get("toBlock"))
    if not (_is_evm_address(address) and topics and topics[0]):
        return [], endpoint, "sqd_event_filter_missing_or_invalid", None, {}
    if from_block is None or to_block is None:
        return [], endpoint, "sqd_event_block_range_missing", None, {}
    log_query: dict[str, Any] = {
        "address": [address],
        "topic0": [topics[0]],
    }
    for idx, topic in enumerate(topics[1:4], start=1):
        if topic:
            log_query[f"topic{idx}"] = [topic]
    api_key, key_source = _sqd_portal_api_key()
    payload = {
        "type": "evm",
        "fromBlock": int(from_block),
        "toBlock": int(to_block),
        "fields": {
            "block": {"number": True, "hash": True, "timestamp": True},
            "log": {
                "address": True,
                "topics": True,
                "data": True,
                "transactionHash": True,
                "logIndex": True,
            },
        },
        "logs": [log_query],
    }
    headers = {
        "Accept": "application/x-ndjson, application/json",
        "Content-Type": "application/json",
        "User-Agent": "CoreEquitySQDEventReaderLookup/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request_preview = {
        "endpoint": endpoint,
        "payload": payload,
        "api_key_configured": bool(api_key),
        "api_key_source": key_source,
        "authorization_header_redacted": bool(api_key),
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(2, min(int(timeout or 6), 15))) as resp:
            body = resp.read(2_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return [], endpoint, f"sqd_portal_http_error:{exc.code}", key_source, request_preview
    except Exception as exc:
        return [], endpoint, f"sqd_portal_error:{type(exc).__name__}", key_source, request_preview

    logs: list[dict[str, Any]] = []
    try:
        lines = [line for line in body.splitlines() if line.strip()]
        for line in lines[:1_000]:
            item = json.loads(line)
            if not isinstance(item, dict):
                continue
            header = item.get("header") if isinstance(item.get("header"), dict) else {}
            block_number = header.get("number")
            block_hash = header.get("hash")
            block_timestamp = header.get("timestamp")
            for raw_log in item.get("logs") or []:
                if not isinstance(raw_log, dict):
                    continue
                normalized_log = dict(raw_log)
                normalized_log.setdefault("blockNumber", block_number)
                normalized_log.setdefault("blockHash", block_hash)
                normalized_log.setdefault("timestamp", block_timestamp)
                logs.append(normalized_log)
    except Exception as exc:
        return [], endpoint, f"sqd_portal_parse_error:{type(exc).__name__}", key_source, request_preview
    return logs, endpoint, None, key_source, request_preview
