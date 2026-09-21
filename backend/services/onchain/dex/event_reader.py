"""Pure helpers for the DEX local event-reader lane."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping

from services.onchain.core.addresses import _is_evm_address
from services.onchain.core.constants import PAIR_CREATED_TOPIC, SWAP_TOPIC, TRANSFER_TOPIC
from services.onchain_chains import normalize_chain as _normalize_chain


def _dex_event_reader_log_preview(event_name: str, log: Mapping[str, Any]) -> dict[str, Any]:
    topics = [str(item).lower() for item in (log.get("topics") or [])]
    data = str(log.get("data") or "0x")
    preview: dict[str, Any] = {
        "address": str(log.get("address") or "").lower(),
        "block_number": int(str(log.get("blockNumber") or "0x0"), 16)
        if str(log.get("blockNumber") or "").startswith("0x")
        else log.get("blockNumber"),
        "tx_hash": str(log.get("transactionHash") or "").lower(),
        "log_index": int(str(log.get("logIndex") or "0x0"), 16)
        if str(log.get("logIndex") or "").startswith("0x")
        else log.get("logIndex"),
        "topic0": topics[0] if topics else None,
        "topics_count": len(topics),
        "data_digest": hashlib.sha256(data.encode()).hexdigest(),
    }
    if event_name == "PairCreated":
        preview["token0"] = "0x" + topics[1][-40:] if len(topics) > 1 else None
        preview["token1"] = "0x" + topics[2][-40:] if len(topics) > 2 else None
        cleaned = data[2:] if data.startswith("0x") else data
        preview["pair_address"] = "0x" + cleaned[24:64] if len(cleaned) >= 64 else None
    elif event_name == "Swap":
        preview["sender"] = "0x" + topics[1][-40:] if len(topics) > 1 else None
        preview["to"] = "0x" + topics[2][-40:] if len(topics) > 2 else None
    elif event_name == "ERC20 Transfer":
        preview["from"] = "0x" + topics[1][-40:] if len(topics) > 1 else None
        preview["to"] = "0x" + topics[2][-40:] if len(topics) > 2 else None
    return preview


def _dex_event_reader_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text, 16) if text.startswith("0x") else int(text)
    except ValueError:
        return None


def _dex_event_reader_topic_address(topic: Any) -> str | None:
    text = str(topic or "").strip().lower()
    if len(text) < 42:
        return None
    address = "0x" + text[-40:]
    return address if _is_evm_address(address) else None


def _dex_event_reader_uint_word(data: Any, index: int) -> str:
    cleaned = str(data or "0x")
    cleaned = cleaned[2:] if cleaned.startswith("0x") else cleaned
    start = max(0, int(index)) * 64
    word = cleaned[start : start + 64]
    if len(word) != 64:
        return "0"
    try:
        return str(int(word, 16))
    except ValueError:
        return "0"


def _dex_event_reader_raw_log_json_and_digest(log: Mapping[str, Any]) -> tuple[str, str]:
    raw_log_json = json.dumps(dict(log), sort_keys=True, separators=(",", ":"), default=str)
    return raw_log_json, hashlib.sha256(raw_log_json.encode("utf-8")).hexdigest()


def _dex_event_reader_raw_candidate_from_log(
    event_name: str,
    call: Mapping[str, Any],
    log: Mapping[str, Any],
    chain: str,
    source_policy: str,
) -> dict[str, Any]:
    topics = [str(item).lower() for item in (log.get("topics") or [])]
    data = str(log.get("data") or "0x")
    address = str(log.get("address") or call.get("address") or "").strip().lower()
    tx_hash = str(log.get("transactionHash") or "").strip().lower()
    log_index = _dex_event_reader_int(log.get("logIndex"))
    block_number = _dex_event_reader_int(log.get("blockNumber"))
    block_hash = str(log.get("blockHash") or "").strip() or None
    block_timestamp = _dex_event_reader_int(log.get("timestamp"))
    checkpoint_id = int(call.get("checkpoint_id") or 0)
    raw_log_json, payload_digest = _dex_event_reader_raw_log_json_and_digest(log)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    blockers: list[str] = []

    if not _is_evm_address(address):
        blockers.append("log_address_invalid")
    if not tx_hash.startswith("0x"):
        blockers.append("tx_hash_missing")
    if log_index is None:
        blockers.append("log_index_missing")
    if block_number is None:
        blockers.append("block_number_missing")
    if not topics:
        blockers.append("event_topic_missing")
    if checkpoint_id <= 0:
        blockers.append("checkpoint_id_missing")

    event_topic = topics[0] if topics else None
    normalized_chain = _normalize_chain(chain or "bsc")
    event_dedupe_key = f"{normalized_chain}|{event_name}|{address}|{tx_hash}|{log_index}"
    base = {
        "checkpoint_id": checkpoint_id,
        "chain": normalized_chain,
        "event_name": event_name,
        "event_topic": event_topic,
        "contract_address": address,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "block_number": block_number,
        "block_hash": block_hash,
        "block_timestamp": block_timestamp,
        "raw_log_json": raw_log_json,
        "payload_digest": payload_digest,
        "event_dedupe_key": event_dedupe_key,
        "status": "raw_observed",
        "created_at": created_at,
        "source_policy": source_policy,
        "blockers": blockers,
    }

    if event_name == "PairCreated":
        token0 = _dex_event_reader_topic_address(topics[1] if len(topics) > 1 else None)
        token1 = _dex_event_reader_topic_address(topics[2] if len(topics) > 2 else None)
        pair_address = _dex_event_reader_topic_address("0x" + data[2:66] if data.startswith("0x") else "0x" + data[:64])
        if event_topic != PAIR_CREATED_TOPIC:
            blockers.append("paircreated_topic_mismatch")
        if not token0:
            blockers.append("token0_missing")
        if not token1:
            blockers.append("token1_missing")
        if not pair_address:
            blockers.append("pair_address_missing")
        return {
            **base,
            "target_table": "dex_raw_paircreated_events",
            "insert_columns": [
                "checkpoint_id",
                "chain",
                "factory_address",
                "token0",
                "token1",
                "pair_address",
                "tx_hash",
                "log_index",
                "block_number",
                "block_hash",
                "block_timestamp",
                "event_topic",
                "raw_log_json",
                "payload_digest",
                "event_dedupe_key",
                "status",
                "created_at",
                "source_policy",
            ],
            "insert_values": [
                checkpoint_id,
                normalized_chain,
                address,
                token0,
                token1,
                pair_address,
                tx_hash,
                log_index,
                block_number,
                block_hash,
                block_timestamp,
                event_topic,
                raw_log_json,
                payload_digest,
                event_dedupe_key,
                "raw_observed",
                created_at,
                source_policy,
            ],
            "preview": {
                "target_table": "dex_raw_paircreated_events",
                "checkpoint_id": checkpoint_id,
                "factory_address": address,
                "token0": token0,
                "token1": token1,
                "pair_address": pair_address,
                "tx_hash": tx_hash,
                "log_index": log_index,
                "block_number": block_number,
                "event_dedupe_key": event_dedupe_key,
                "payload_digest": payload_digest,
                "blockers": blockers,
            },
        }

    if event_name == "Swap":
        sender = _dex_event_reader_topic_address(topics[1] if len(topics) > 1 else None)
        recipient = _dex_event_reader_topic_address(topics[2] if len(topics) > 2 else None)
        if event_topic != SWAP_TOPIC:
            blockers.append("swap_topic_mismatch")
        return {
            **base,
            "target_table": "dex_raw_swap_events",
            "insert_columns": [
                "checkpoint_id",
                "chain",
                "pair_address",
                "sender",
                "recipient",
                "amount0_in",
                "amount1_in",
                "amount0_out",
                "amount1_out",
                "tx_hash",
                "log_index",
                "block_number",
                "block_hash",
                "block_timestamp",
                "event_topic",
                "raw_log_json",
                "payload_digest",
                "event_dedupe_key",
                "status",
                "created_at",
                "source_policy",
            ],
            "insert_values": [
                checkpoint_id,
                normalized_chain,
                address,
                sender,
                recipient,
                _dex_event_reader_uint_word(data, 0),
                _dex_event_reader_uint_word(data, 1),
                _dex_event_reader_uint_word(data, 2),
                _dex_event_reader_uint_word(data, 3),
                tx_hash,
                log_index,
                block_number,
                block_hash,
                block_timestamp,
                event_topic,
                raw_log_json,
                payload_digest,
                event_dedupe_key,
                "raw_observed",
                created_at,
                source_policy,
            ],
            "preview": {
                "target_table": "dex_raw_swap_events",
                "checkpoint_id": checkpoint_id,
                "pair_address": address,
                "sender": sender,
                "recipient": recipient,
                "tx_hash": tx_hash,
                "log_index": log_index,
                "block_number": block_number,
                "event_dedupe_key": event_dedupe_key,
                "payload_digest": payload_digest,
                "blockers": blockers,
            },
        }

    if event_name == "ERC20 Transfer":
        from_address = _dex_event_reader_topic_address(topics[1] if len(topics) > 1 else None)
        to_address = _dex_event_reader_topic_address(topics[2] if len(topics) > 2 else None)
        if event_topic != TRANSFER_TOPIC:
            blockers.append("transfer_topic_mismatch")
        if not from_address:
            blockers.append("from_address_missing")
        if not to_address:
            blockers.append("to_address_missing")
        return {
            **base,
            "target_table": "erc20_transfer_events",
            "insert_columns": [
                "checkpoint_id",
                "chain",
                "token_address",
                "from_address",
                "to_address",
                "value_raw",
                "tx_hash",
                "log_index",
                "block_number",
                "raw_log_json",
                "payload_digest",
                "event_dedupe_key",
                "status",
                "created_at",
                "source_policy",
            ],
            "insert_values": [
                checkpoint_id,
                normalized_chain,
                address,
                from_address,
                to_address,
                _dex_event_reader_uint_word(data, 0),
                tx_hash,
                log_index,
                block_number,
                raw_log_json,
                payload_digest,
                event_dedupe_key,
                "raw_observed",
                created_at,
                source_policy,
            ],
            "preview": {
                "target_table": "erc20_transfer_events",
                "checkpoint_id": checkpoint_id,
                "token_address": address,
                "from_address": from_address,
                "to_address": to_address,
                "value_raw": _dex_event_reader_uint_word(data, 0),
                "tx_hash": tx_hash,
                "log_index": log_index,
                "block_number": block_number,
                "event_dedupe_key": event_dedupe_key,
                "payload_digest": payload_digest,
                "blockers": blockers,
            },
        }

    blockers.append(f"unsupported_event_{event_name}")
    return {
        **base,
        "target_table": None,
        "insert_columns": [],
        "insert_values": [],
        "preview": {
            "event_name": event_name,
            "event_dedupe_key": event_dedupe_key,
            "blockers": blockers,
        },
    }

