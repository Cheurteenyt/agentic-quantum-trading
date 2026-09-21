"""Collection helpers for extracted on-chain modules."""

from __future__ import annotations


def _dedupe_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = str(item or "")
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out

