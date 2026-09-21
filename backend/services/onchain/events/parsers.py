"""Pure EVM log/result parsers used by Core Equity.

These helpers intentionally avoid DB, RPC and provider calls so they can be
imported by extracted modules without loading the large onchain facade.
"""

from __future__ import annotations

from typing import Any

from services.onchain.core.constants import SWAP_TOPIC, TRANSFER_TOPIC


def _decode_uint_words(result: str | None, count: int) -> list[int]:
    if not result or result == "0x":
        return []
    cleaned = result[2:] if result.startswith("0x") else result
    if len(cleaned) < 64 * count:
        return []
    values = []
    for idx in range(count):
        word = cleaned[idx * 64 : (idx + 1) * 64]
        try:
            values.append(int(word, 16))
        except ValueError:
            return []
    return values


def _hex_to_uint(hex_str: str) -> int:
    if not hex_str or hex_str == "0x":
        return 0
    return int(hex_str, 16)


def _hex_to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        text = str(value).strip().lower()
        return int(text, 16) if text.startswith("0x") else int(text)
    except (TypeError, ValueError):
        return None


def _address_from_call_result(result: str | None) -> str:
    if not result or result == "0x":
        return ""
    cleaned = result[2:] if result.startswith("0x") else result
    if len(cleaned) < 40:
        return ""
    address = "0x" + cleaned[-40:]
    return address.lower() if len(address) == 42 else ""


def parse_swap_log(log: dict[str, Any]) -> dict[str, Any] | None:
    topics = log.get("topics", [])
    if not topics or str(topics[0]).lower() != SWAP_TOPIC:
        return None
    data = str(log.get("data", "0x"))[2:]
    if len(data) < 256:
        return None
    amount0_in = _hex_to_uint("0x" + data[0:64])
    amount1_in = _hex_to_uint("0x" + data[64:128])
    amount0_out = _hex_to_uint("0x" + data[128:192])
    amount1_out = _hex_to_uint("0x" + data[192:256])
    sender = "0x" + str(topics[1])[-40:] if len(topics) > 1 else ""
    to = "0x" + str(topics[2])[-40:] if len(topics) > 2 else ""
    return {
        "pool": str(log.get("address", "")).lower(),
        "sender": sender.lower(),
        "to": to.lower(),
        "amount0_in": amount0_in,
        "amount1_in": amount1_in,
        "amount0_out": amount0_out,
        "amount1_out": amount1_out,
        "tx_hash": log.get("transactionHash"),
        "block_number": log.get("blockNumber"),
    }


def parse_transfer_log(log: dict[str, Any]) -> dict[str, Any] | None:
    topics = log.get("topics", [])
    if len(topics) < 3 or str(topics[0]).lower() != TRANSFER_TOPIC:
        return None
    token = str(log.get("address") or "").lower()
    from_addr = "0x" + str(topics[1])[-40:]
    to_addr = "0x" + str(topics[2])[-40:]
    if not (token.startswith("0x") and len(token) == 42):
        return None
    if not (from_addr.startswith("0x") and len(from_addr) == 42 and to_addr.startswith("0x") and len(to_addr) == 42):
        return None
    log_index_raw = log.get("logIndex", "0x0")
    return {
        "tx_hash": log.get("transactionHash"),
        "log_index": _hex_to_uint(log_index_raw) if isinstance(log_index_raw, str) else int(log_index_raw or 0),
        "block_number": log.get("blockNumber"),
        "token": token,
        "from_addr": from_addr.lower(),
        "to_addr": to_addr.lower(),
        "value_raw": str(_hex_to_uint(str(log.get("data", "0x0")))),
    }
