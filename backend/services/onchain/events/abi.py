"""Small ABI result decoders used by on-chain metadata enrichment."""

from __future__ import annotations

from typing import Any


def _decode_erc20_string_result(raw: Any) -> str | None:
    text = str(raw or "").strip()
    if not text or text == "0x":
        return None
    data = text[2:] if text.startswith("0x") else text
    try:
        if len(data) >= 128:
            offset = int(data[:64], 16)
            length_start = offset * 2
            length_end = length_start + 64
            if length_end <= len(data):
                length = int(data[length_start:length_end], 16)
                value_hex = data[length_end : length_end + length * 2]
                decoded = bytes.fromhex(value_hex).decode("utf-8", errors="ignore").strip("\x00").strip()
                if decoded:
                    return decoded[:80]
        if len(data) >= 64:
            decoded = bytes.fromhex(data[:64]).decode("utf-8", errors="ignore").strip("\x00").strip()
            return decoded[:80] if decoded else None
    except Exception:
        return None
    return None


def _decode_erc20_uint_result(raw: Any) -> int | None:
    text = str(raw or "").strip()
    if not text or text == "0x":
        return None
    data = text[2:] if text.startswith("0x") else text
    try:
        return int(data[-64:] if len(data) >= 64 else data, 16)
    except ValueError:
        return None

