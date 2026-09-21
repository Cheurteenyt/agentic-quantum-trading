"""Entity naming helpers for local Arkham-style coverage."""

from __future__ import annotations

from typing import Any


ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "Binance": ("Binance Wallet",),
    "Coinbase": ("Coinbase Prime", "Coinbase Wallet"),
    "OKX": ("Dex Router (OKX)", "OKX Wallet"),
    "Uniswap": ("Uniswap Labs",),
    "PancakeSwap": ("Pancakeswap",),
    "BlackRock": ("Blackrock", "BlackRock: IBIT Bitcoin ETF"),
    "Polymarket": (),
    "Bitget": (),
    "Kraken": ("Kraken Exchange",),
    "KuCoin": ("Kucoin",),
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def canonical_entity_name(entity: Any) -> str:
    """Return the display/canonical entity name for aliases we understand."""
    clean = _clean(entity)
    if not clean:
        return ""
    lowered = clean.lower()
    for canonical, aliases in ENTITY_ALIASES.items():
        if lowered == canonical.lower() or lowered in {alias.lower() for alias in aliases}:
            return canonical
    return clean


def entity_aliases(entity: Any) -> list[str]:
    """Return canonical + known aliases, preserving deterministic order."""
    clean = _clean(entity)
    if not clean:
        return []
    canonical = canonical_entity_name(clean)
    candidates = [canonical, clean, *ENTITY_ALIASES.get(canonical, ())]
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if candidate and key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def entity_matches(value: Any, requested: Any) -> bool:
    aliases = {item.lower() for item in entity_aliases(requested)}
    return bool(aliases) and _clean(value).lower() in aliases


def entity_in_clause(column: str, entity: Any) -> tuple[str, list[str]]:
    """Build a safe SQL IN clause for canonical entity aliases."""
    aliases = entity_aliases(entity)
    if not aliases:
        return "", []
    placeholders = ", ".join("LOWER(?)" for _ in aliases)
    return f"LOWER({column}) IN ({placeholders})", aliases
