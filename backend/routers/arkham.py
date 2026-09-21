"""
Arkham API Router — Endpoints Smart Money Tracking + Token Intelligence
========================================================================
Endpoints:
  GET  /api/arkham/status              → Statut DB + tracker
  GET  /api/arkham/signals             → Signaux récents identifiés
  GET  /api/arkham/flows               → Flows cumulés par entité
  GET  /api/arkham/smart-money         → Activité smart money
  GET  /api/arkham/search?q=           → Recherche wallets/entités/tokens
  GET  /api/arkham/entity/{slug}       → Détails d'une entité
  GET  /api/arkham/token/{symbol}      → Détails d'un token (CoinGecko + Etherscan + Arkham)
  GET  /api/arkham/lookup/{address}    → Lookup une adresse on-chain
  GET  /api/arkham/source-backed-inventory -> Inventaire preuve Arkham local read-only
  POST /api/arkham/scrape/full         → Déclencher full scrape
  POST /api/arkham/scrape/delta        → Déclencher delta scan
"""

import asyncio
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Query

router = APIRouter(tags=["arkham"])

SCRAPLING_NORMALIZED_DIR = Path(__file__).resolve().parents[1] / "data" / "arkham" / "scrapling" / "normalized"
BACKEND_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_SCRAPLING_SEARCH_INDEX_CACHE: dict[str, Any] = {"signature": None, "index": None}


TOKEN_METADATA = {
    "usdt": {"symbol": "USDT", "name": "Tether USDt", "decimals": 6, "stablecoin": True},
    "usdc": {"symbol": "USDC", "name": "USD Coin", "decimals": 6, "stablecoin": True},
    "dai": {"symbol": "DAI", "name": "Dai", "decimals": 18, "stablecoin": True},
    "busd": {"symbol": "BUSD", "name": "Binance USD", "decimals": 18, "stablecoin": True},
    "wbtc": {"symbol": "WBTC", "name": "Wrapped Bitcoin", "decimals": 8, "stablecoin": False},
    "weth": {"symbol": "WETH", "name": "Wrapped Ether", "decimals": 18, "stablecoin": False},
    "eth": {"symbol": "ETH", "name": "Ether", "decimals": 18, "stablecoin": False},
    "btc": {"symbol": "BTC", "name": "Bitcoin", "decimals": 8, "stablecoin": False},
    "link": {"symbol": "LINK", "name": "Chainlink", "decimals": 18, "stablecoin": False},
    "uni": {"symbol": "UNI", "name": "Uniswap", "decimals": 18, "stablecoin": False},
    "aave": {"symbol": "AAVE", "name": "Aave", "decimals": 18, "stablecoin": False},
    "mkr": {"symbol": "MKR", "name": "Maker", "decimals": 18, "stablecoin": False},
    "shib": {"symbol": "SHIB", "name": "Shiba Inu", "decimals": 18, "stablecoin": False},
    "pepe": {"symbol": "PEPE", "name": "Pepe", "decimals": 18, "stablecoin": False},
}

FLAG_KEYWORDS = {
    "exchange": "exchange",
    "hot-wallet": "hot wallet",
    "hot wallet": "hot wallet",
    "cold wallet": "cold wallet",
    "deposit": "deposit",
    "reserve": "reserves",
    "proof-of-reserves": "reserves",
    "bridge": "bridge",
    "aggregator": "aggregator",
    "router": "router",
    "validator": "validator",
    "market-maker": "market maker",
    "market maker": "market maker",
    "custody": "custody",
    "vault": "vault",
    "pool": "pool",
    "proxy": "proxy",
    "etf": "etf",
    "dex": "dex",
    "amm": "amm",
}

EVM_CHAINS = {"ethereum", "bsc", "arbitrum", "polygon", "optimism", "base", "avalanche"}

ARKHAM_CHAIN_REFERENCE = {
    "ethereum": {"arkham_coverage_pct": 95, "family": "evm", "local_rpc": "HERMES_RPC_ETHEREUM", "local_ingestion": True},
    "solana": {"arkham_coverage_pct": 98, "family": "solana", "local_rpc": "HERMES_RPC_SOLANA", "local_ingestion": False},
    "bitcoin": {"arkham_coverage_pct": 73, "family": "utxo", "local_rpc": None, "local_ingestion": False},
    "tron": {"arkham_coverage_pct": 57, "family": "tron", "local_rpc": None, "local_ingestion": False},
    "dogecoin": {"arkham_coverage_pct": 49, "family": "utxo", "local_rpc": None, "local_ingestion": False},
    "ton": {"arkham_coverage_pct": 99, "family": "ton", "local_rpc": None, "local_ingestion": False},
    "base": {"arkham_coverage_pct": 100, "family": "evm", "local_rpc": None, "local_ingestion": False},
    "arbitrum": {"arkham_coverage_pct": 100, "family": "evm", "local_rpc": None, "local_ingestion": False},
    "optimism": {"arkham_coverage_pct": 100, "family": "evm", "local_rpc": None, "local_ingestion": False},
    "avalanche": {"arkham_coverage_pct": 99, "family": "evm", "local_rpc": None, "local_ingestion": False},
    "bsc": {"arkham_coverage_pct": 95, "family": "evm", "local_rpc": "HERMES_RPC_BSC", "local_ingestion": True},
    "polygon": {"arkham_coverage_pct": 96, "family": "evm", "local_rpc": None, "local_ingestion": False},
    "flare": {"arkham_coverage_pct": 93, "family": "evm", "local_rpc": None, "local_ingestion": False},
    "zcash": {"arkham_coverage_pct": 53, "family": "utxo", "local_rpc": None, "local_ingestion": False},
    "hyperevm": {"arkham_coverage_pct": 91, "family": "evm", "local_rpc": None, "local_ingestion": False},
}

ARKHAM_REFERENCE_METRICS = {
    "addresses_labelled": 3_100_000_000,
    "source": "https://intel.arkm.com/api",
}

ACQUISITION_SOURCE_CATALOG = {
    "openlabels_blockscout": {
        "purpose": "label extraction from explorer metadata and holder tags",
        "risk": "low",
        "dedupe_key": "chain:address:label_source",
    },
    "scrapling_arkham_snapshots": {
        "purpose": "UI-observed entities, portfolios, counterparties and social/profile metadata",
        "risk": "medium",
        "dedupe_key": "source:kind:target:generated_at",
    },
    "evm_rpc_logs": {
        "purpose": "raw transfers, swaps, first_seen, last_seen and wallet activity",
        "risk": "medium",
        "dedupe_key": "chain:tx_hash:log_index",
    },
    "zerion_cielo_wallet_intel": {
        "purpose": "wallet portfolio, PnL hints, discovery and cross-provider validation",
        "risk": "medium",
        "dedupe_key": "provider:chain:wallet:asset",
    },
    "curated_static_entities": {
        "purpose": "high-confidence exchange/fund/protocol seed labels",
        "risk": "low",
        "dedupe_key": "entity_slug:chain:address",
    },
}


def _slugify_text(value: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "-" for ch in (value or "").strip()]
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _compact_search_text(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _truncate_addr(addr: str, left: int = 6, right: int = 4) -> str:
    if not addr or len(addr) <= left + right + 2:
        return addr
    return f"{addr[:left + 2]}...{addr[-right:]}"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _sum_estimated_value_usd(rows: Any) -> float | None:
    if not isinstance(rows, list):
        return None
    total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = _safe_float(
            row.get("estimated_value_usd")
            or row.get("value_usd")
            or row.get("usd_value")
            or row.get("balance_usd")
        )
        if value and value > 0:
            total += value
    return round(total, 2) if total > 0 else None


def _asset_surface_key(row: dict[str, Any]) -> str:
    chain = str(row.get("chain") or "unknown").strip().lower()
    identifier = (
        row.get("contract_address")
        or row.get("asset_id")
        or row.get("symbol")
        or row.get("name")
        or "unknown"
    )
    return f"{chain}:{str(identifier).strip().lower()}"


def _to_unix_timestamp(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return int(stripped)
        try:
            return int(datetime.fromisoformat(stripped.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def _parse_holders_cache_key(key: str) -> tuple[str | None, str | None]:
    parts = key.split(":")
    if len(parts) < 3 or parts[0] != "holders":
        return None, None
    return parts[1], parts[2].lower()


def _coverage_chain_key(chain: str) -> str:
    normalized = str(chain or "").strip().lower()
    aliases = {
        "eth": "ethereum",
        "ethereum-mainnet": "ethereum",
        "bnb": "bsc",
        "bnb-chain": "bsc",
        "binance-smart-chain": "bsc",
        "arbitrum-one": "arbitrum",
        "matic": "polygon",
        "op": "optimism",
        "avax": "avalanche",
    }
    return aliases.get(normalized, normalized)


def _entity_aliases(entity_slug: str, entity: dict[str, Any] | None) -> set[str]:
    aliases = {
        _slugify_text(entity_slug),
        _slugify_text(entity_slug.replace("-", " ")),
    }
    if entity:
        aliases.add(_slugify_text(entity.get("name", "")))
        aliases.add(_slugify_text(entity.get("slug", "")))
    return {alias for alias in aliases if alias}


def _extract_holder_tags(holder: dict[str, Any]) -> list[dict[str, str]]:
    extracted: list[dict[str, str]] = []
    for raw_tag in holder.get("metadata_tags") or []:
        if not isinstance(raw_tag, dict):
            continue
        meta = raw_tag.get("meta") or {}
        extracted.append({
            "name": str(raw_tag.get("name") or "").strip(),
            "slug": _slugify_text(str(raw_tag.get("slug") or raw_tag.get("name") or "")),
            "tag_type": str(raw_tag.get("tagType") or "").strip(),
            "main_entity": str(meta.get("main_entity") or "").strip(),
        })
    return extracted


def _match_entity_tags(tags: list[dict[str, str]], aliases: set[str]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for tag in tags:
        candidates = {
            _slugify_text(tag.get("name", "")),
            _slugify_text(tag.get("slug", "")),
            _slugify_text(tag.get("main_entity", "")),
        }
        candidates.discard("")
        if any(
            alias == candidate or alias in candidate or candidate in alias
            for alias in aliases
            for candidate in candidates
        ):
            matches.append(tag)
    return matches


def _best_wallet_label(tags: list[dict[str, str]], address: str) -> str:
    for tag in tags:
        if tag.get("tag_type") == "name" and tag.get("name"):
            return tag["name"]
    for tag in tags:
        if tag.get("name"):
            return tag["name"]
    return _truncate_addr(address)


def _wallet_flags(tags: list[dict[str, str]]) -> list[str]:
    flags: list[str] = []
    joined = " | ".join(
        part
        for tag in tags
        for part in [tag.get("name", ""), tag.get("slug", ""), tag.get("main_entity", "")]
        if part
    ).lower()
    for keyword, label in FLAG_KEYWORDS.items():
        if keyword in joined and label not in flags:
            flags.append(label)
    return flags


def _wallet_confidence(tags: list[dict[str, str]], aliases: set[str]) -> str:
    for tag in tags:
        main_entity = _slugify_text(tag.get("main_entity", ""))
        if main_entity and main_entity in aliases:
            return "high"
        tag_name = _slugify_text(tag.get("name", ""))
        if tag_name in aliases:
            return "high"
    if tags:
        return "medium"
    return "low"


def _address_tags_from_info(address_info: dict[str, Any] | None) -> list[dict[str, str]]:
    info = address_info or {}
    extracted = _extract_holder_tags({"metadata_tags": (info.get("metadata") or {}).get("tags") or []})
    seen: set[tuple[str, str, str]] = {
        (tag.get("name", ""), tag.get("tag_type", ""), tag.get("main_entity", ""))
        for tag in extracted
    }

    def _append(name: str | None, tag_type: str, main_entity: str = "") -> None:
        cleaned = str(name or "").strip()
        if not cleaned or cleaned.lower().startswith("note_"):
            return
        key = (cleaned, tag_type, str(main_entity or "").strip())
        if key in seen:
            return
        extracted.append({
            "name": cleaned,
            "slug": _slugify_text(cleaned),
            "tag_type": tag_type,
            "main_entity": str(main_entity or "").strip(),
        })
        seen.add(key)

    _append(info.get("name"), "name")

    for impl in info.get("implementations") or []:
        if isinstance(impl, dict):
            _append(impl.get("name"), "implementation")
        else:
            _append(impl, "implementation")

    for raw_tag in info.get("public_tags") or []:
        if isinstance(raw_tag, dict):
            _append(
                raw_tag.get("name") or raw_tag.get("label") or raw_tag.get("display_name"),
                "public_tag",
                raw_tag.get("main_entity") or "",
            )
        else:
            _append(raw_tag, "public_tag")

    return extracted


def _resolve_address_identity(address: str, address_info: dict[str, Any] | None) -> dict[str, Any]:
    info = address_info or {}
    tags = _address_tags_from_info(info)
    impl_names = [str(impl.get("name") or impl).strip() for impl in info.get("implementations") or [] if impl]
    display_tags = [tag.get("name") for tag in tags if tag.get("name") and not tag.get("name", "").lower().startswith("note_")]
    entity = next((tag.get("main_entity") for tag in tags if tag.get("main_entity")), None)
    flags = _wallet_flags(tags)

    name = str(info.get("name") or "").strip()
    if name == "SafeProxy" or any(impl_name == "Safe" for impl_name in impl_names):
        if "safe" not in flags:
            flags.append("safe")
        return {
            "label": "Gnosis Safe Proxy",
            "entity": entity or "Gnosis Safe",
            "wallet_type": "safe",
            "tags": display_tags[:8],
            "flags": flags,
        }

    label = _best_wallet_label(tags, address) if tags else None
    wallet_type = "contract" if info.get("is_contract") else "wallet"
    if flags:
        wallet_type = flags[0]

    return {
        "label": label or None,
        "entity": entity,
        "wallet_type": wallet_type,
        "tags": display_tags[:8],
        "flags": flags,
    }


def _contract_token_metadata(chain: str, contract: str) -> dict[str, Any]:
    from services.arkham_scraper import KNOWN_CONTRACTS

    for symbol, chain_map in KNOWN_CONTRACTS.items():
        known_contract = str(chain_map.get(chain) or "").lower()
        if known_contract and known_contract == contract.lower():
            meta = TOKEN_METADATA.get(symbol, {})
            return {
                "symbol": meta.get("symbol", symbol.upper()),
                "name": meta.get("name", symbol.upper()),
                "decimals": meta.get("decimals", 18),
                "stablecoin": meta.get("stablecoin", False),
            }
    return {
        "symbol": contract[:6].upper(),
        "name": "Observed Token",
        "decimals": 18,
        "stablecoin": False,
    }


def _human_balance(raw_balance: Any, decimals: int) -> float | None:
    try:
        raw_int = int(str(raw_balance or "0"))
        return raw_int / (10 ** decimals)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _merge_wallet_sources(primary_wallets: list[dict[str, Any]], derived_wallets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for wallet in primary_wallets + derived_wallets:
        address = str(wallet.get("address") or "").lower()
        if not address:
            continue
        existing = merged.get(address, {"address": address})
        for key, value in wallet.items():
            if value not in (None, "", [], {}):
                existing[key] = value
        merged[address] = existing

    return list(merged.values())


def _counterparty_label(tags: list[str], address: str, aliases: set[str]) -> str:
    for tag in tags:
        normalized = _slugify_text(tag)
        if normalized and normalized not in aliases:
            return tag
    return _truncate_addr(address)


def _activity_bucket(tx_count: int | None, transfer_count: int | None) -> str | None:
    if tx_count is None and transfer_count is None:
        return None
    score = (tx_count or 0) + (transfer_count or 0)
    if score <= 25:
        return "low"
    if score <= 250:
        return "medium"
    return "high"


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def _flags_from_text(*parts: str) -> list[str]:
    joined = " | ".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())
    if not joined:
        return []
    flags: list[str] = []
    for keyword, label in FLAG_KEYWORDS.items():
        if keyword in joined and label not in flags:
            flags.append(label)
    return flags


def _search_query_variants(query: str) -> tuple[set[str], set[str]]:
    query_lower = str(query or "").strip().lower()
    if not query_lower:
        return set(), set()
    variants = {query_lower}
    if "gate " in query_lower:
        variants.add(query_lower.replace("gate ", "gate.io "))
        variants.add(query_lower.replace("gate ", "gateio "))
    compact_variants = {_compact_search_text(variant) for variant in variants if variant}
    return variants, compact_variants


def _matches_searchable_row(row: dict[str, Any], query_variants: set[str], query_compact_variants: set[str]) -> bool:
    searchable_text = str(row.get("searchable_text") or "").lower()
    searchable_compact = str(row.get("searchable_compact") or "").lower()
    if not searchable_text and not searchable_compact:
        return False
    return (
        any(variant in searchable_text for variant in query_variants)
        or any(variant and variant in searchable_compact for variant in query_compact_variants)
    )


def _strip_search_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in {"searchable_text", "searchable_compact"}}


def _load_scrapling_search_index() -> dict[str, list[dict[str, Any]]]:
    if not SCRAPLING_NORMALIZED_DIR.exists():
        return {"entities": [], "wallets": [], "tokens": []}

    files = sorted(SCRAPLING_NORMALIZED_DIR.glob("*.json"))
    signature = tuple((path.name, path.stat().st_mtime_ns, path.stat().st_size) for path in files)
    cached_signature = _SCRAPLING_SEARCH_INDEX_CACHE.get("signature")
    cached_index = _SCRAPLING_SEARCH_INDEX_CACHE.get("index")
    if cached_signature == signature and isinstance(cached_index, dict):
        return cached_index

    entity_rows: list[dict[str, Any]] = []
    wallet_rows: list[dict[str, Any]] = []
    token_rows: list[dict[str, Any]] = []
    seen_entity_slugs: set[str] = set()
    seen_wallet_keys: set[tuple[str, str]] = set()
    seen_token_ids: set[str] = set()

    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        kind = str(payload.get("kind") or "").strip().lower()
        if kind == "entity":
            entity_obj = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
            profile_obj = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
            summary_obj = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            raw_slug = str(entity_obj.get("slug") or payload.get("target") or path.stem.replace("entity_", "")).strip().lower()
            raw_name = str(entity_obj.get("name") or profile_obj.get("name") or raw_slug).strip()
            raw_type = str(entity_obj.get("type") or profile_obj.get("type") or "").strip()
            raw_category = str(entity_obj.get("category") or profile_obj.get("category") or "").strip()
            raw_chains = _dedupe_keep_order([
                str(item.get("chain") or "").strip().lower()
                for item in payload.get("chains") or []
                if isinstance(item, dict) and item.get("chain")
            ])
            raw_badges = _dedupe_keep_order([str(item).strip() for item in profile_obj.get("badges") or [] if str(item).strip()])
            raw_tags = _dedupe_keep_order([str(item).strip() for item in profile_obj.get("tags") or [] if str(item).strip()])
            socials = profile_obj.get("socials") if isinstance(profile_obj.get("socials"), dict) else {}
            social_values = [str(value).strip() for value in socials.values() if str(value).strip()]

            if raw_slug and raw_slug not in seen_entity_slugs:
                entity_row = {
                    "slug": raw_slug,
                    "name": raw_name or raw_slug,
                    "type": raw_type,
                    "category": raw_category,
                    "balance_usd": _safe_float(entity_obj.get("balance_usd")) or _safe_float(summary_obj.get("total_balance_usd")),
                    "wallet_count": _safe_int(entity_obj.get("wallet_count")) or _safe_int(payload.get("coverage", {}).get("observed_wallets")),
                    "chains": raw_chains,
                    "source": "scrapling_snapshot",
                }
                entity_row["searchable_text"] = " | ".join(
                    part for part in [
                        entity_row["slug"],
                        entity_row["name"],
                        entity_row["type"],
                        entity_row["category"],
                        " ".join(raw_chains),
                        " ".join(raw_badges),
                        " ".join(raw_tags),
                        str(profile_obj.get("website") or "").strip(),
                        " ".join(social_values),
                    ] if part
                ).lower()
                entity_row["searchable_compact"] = _compact_search_text(entity_row["searchable_text"])
                entity_rows.append(entity_row)
                seen_entity_slugs.add(raw_slug)

            for wallet in payload.get("wallets") or []:
                if not isinstance(wallet, dict):
                    continue
                address = str(wallet.get("address") or "").strip().lower()
                chain = str(wallet.get("chain") or "").strip().lower()
                label = str(wallet.get("label") or "").strip()
                entity_name = str(wallet.get("entity") or raw_name or "").strip()
                wallet_type = str(wallet.get("wallet_type") or "").strip()
                if not address:
                    continue
                wallet_key = (address, chain)
                if wallet_key in seen_wallet_keys:
                    continue
                flags = _dedupe_keep_order(
                    [str(flag).strip() for flag in wallet.get("flags") or [] if str(flag).strip()]
                    + _flags_from_text(label, entity_name, wallet_type)
                )
                tags = _dedupe_keep_order(
                    [str(tag).strip() for tag in wallet.get("matched_tags") or [] if str(tag).strip()]
                    + [str(symbol).strip() for symbol in wallet.get("token_symbols") or [] if str(symbol).strip()]
                )
                wallet_row = {
                    "address": address,
                    "label": label or _truncate_addr(address),
                    "entity": entity_name,
                    "chain": chain,
                    "wallet_type": wallet_type or (flags[0] if flags else ""),
                    "flags": flags,
                    "tags": tags,
                    "balance_usd": _safe_float(wallet.get("observed_value_usd")),
                    "source": "scrapling_snapshot",
                }
                wallet_row["searchable_text"] = " | ".join(
                    part for part in [
                        wallet_row["address"],
                        wallet_row["label"],
                        wallet_row["entity"],
                        wallet_row["chain"],
                        wallet_row["wallet_type"],
                        " ".join(wallet_row["flags"]),
                    ] if part
                ).lower()
                wallet_row["searchable_compact"] = _compact_search_text(wallet_row["searchable_text"])
                wallet_rows.append(wallet_row)
                seen_wallet_keys.add(wallet_key)

            for counterparty in payload.get("counterparties") or []:
                if not isinstance(counterparty, dict):
                    continue
                address = str(counterparty.get("address") or "").strip().lower()
                label = str(counterparty.get("label") or "").strip()
                chain = str(counterparty.get("chain") or "").strip().lower()
                if not address and not label:
                    continue
                inferred_entity = label.split(":", 1)[0].strip() if ":" in label else ""
                wallet_key = (address or _compact_search_text(label), chain)
                if wallet_key in seen_wallet_keys:
                    continue
                flags = _flags_from_text(label, inferred_entity, raw_name)
                wallet_row = {
                    "address": address,
                    "label": label or _truncate_addr(address),
                    "entity": inferred_entity,
                    "chain": chain,
                    "wallet_type": flags[0] if flags else "",
                    "flags": flags,
                    "tags": [raw_name] if raw_name else [],
                    "balance_usd": _safe_float(counterparty.get("value_usd")),
                    "source": "scrapling_counterparty",
                }
                wallet_row["searchable_text"] = " | ".join(
                    part for part in [
                        wallet_row["address"],
                        wallet_row["label"],
                        wallet_row["entity"],
                        wallet_row["chain"],
                        wallet_row["wallet_type"],
                        " ".join(wallet_row["flags"]),
                    ] if part
                ).lower()
                wallet_row["searchable_compact"] = _compact_search_text(wallet_row["searchable_text"])
                wallet_rows.append(wallet_row)
                seen_wallet_keys.add(wallet_key)

        elif kind == "token":
            symbol = str(payload.get("symbol") or "").strip().upper()
            name = str(payload.get("name") or payload.get("target") or "").strip()
            token_id = str(payload.get("target") or symbol or name).strip().lower()
            market_obj = payload.get("market") if isinstance(payload.get("market"), dict) else {}
            addresses_obj = payload.get("addresses") if isinstance(payload.get("addresses"), dict) else {}
            contract_address = str(
                addresses_obj.get("contract_address")
                or addresses_obj.get("address")
                or addresses_obj.get("token_address")
                or ""
            ).strip()

            if token_id and token_id not in seen_token_ids:
                token_row = {
                    "id": token_id,
                    "symbol": symbol,
                    "name": name or token_id,
                    "contract_address": contract_address,
                    "market_cap_usd": _safe_float(market_obj.get("market_cap")) or _safe_float(market_obj.get("fdv")),
                    "price_usd": _safe_float(market_obj.get("price")),
                    "source": "scrapling_snapshot",
                }
                token_row["searchable_text"] = " | ".join(
                    part for part in [
                        token_row["id"],
                        token_row["symbol"],
                        token_row["name"],
                        token_row["contract_address"],
                    ] if part
                ).lower()
                token_row["searchable_compact"] = _compact_search_text(token_row["searchable_text"])
                token_rows.append(token_row)
                seen_token_ids.add(token_id)

            for tx in payload.get("transfers") or []:
                if not isinstance(tx, dict):
                    continue
                chain = str(tx.get("chain") or "").strip().lower()
                for side in ("from", "to"):
                    address = str(tx.get(side) or "").strip().lower()
                    label = str(tx.get(f"{side}_display_label") or tx.get(f"{side}_label") or "").strip()
                    entity_name = str(tx.get(f"{side}_entity") or "").strip()
                    wallet_type = str(tx.get(f"{side}_wallet_type") or "").strip()
                    if not address and not label:
                        continue
                    wallet_key = (address or _compact_search_text(label), str(tx.get(f"{side}_chain") or chain).strip().lower())
                    if wallet_key in seen_wallet_keys:
                        continue
                    flags = _flags_from_text(label, entity_name, wallet_type)
                    wallet_row = {
                        "address": address,
                        "label": label or _truncate_addr(address),
                        "entity": entity_name,
                        "chain": str(tx.get(f"{side}_chain") or chain).strip().lower(),
                        "wallet_type": wallet_type or (flags[0] if flags else ""),
                        "flags": flags,
                        "tags": _dedupe_keep_order([symbol, name] if symbol or name else []),
                        "balance_usd": None,
                        "source": "scrapling_token_transfer",
                    }
                    wallet_row["searchable_text"] = " | ".join(
                        part for part in [
                            wallet_row["address"],
                            wallet_row["label"],
                            wallet_row["entity"],
                            wallet_row["chain"],
                            wallet_row["wallet_type"],
                            " ".join(wallet_row["flags"]),
                        ] if part
                    ).lower()
                    wallet_row["searchable_compact"] = _compact_search_text(wallet_row["searchable_text"])
                    wallet_rows.append(wallet_row)
                    seen_wallet_keys.add(wallet_key)

    index = {"entities": entity_rows, "wallets": wallet_rows, "tokens": token_rows}
    _SCRAPLING_SEARCH_INDEX_CACHE["signature"] = signature
    _SCRAPLING_SEARCH_INDEX_CACHE["index"] = index
    return index


def _normalized_files_signature(files: list[Path]) -> tuple[tuple[str, int, int], ...]:
    return tuple((path.name, path.stat().st_mtime_ns, path.stat().st_size) for path in files)


def _iso_from_mtime(path: Path) -> str | None:
    try:
        return datetime.utcfromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") + "Z"
    except Exception:
        return None


def _age_seconds(path: Path) -> int | None:
    try:
        return max(0, int(datetime.utcnow().timestamp() - path.stat().st_mtime))
    except Exception:
        return None


def _scan_data_files(root: Path, pattern: str = "*") -> dict[str, Any]:
    files = sorted(root.rglob(pattern)) if root.exists() else []
    files = [path for path in files if path.is_file()]
    latest = max(files, key=lambda path: path.stat().st_mtime, default=None)
    return {
        "path": str(root),
        "exists": root.exists(),
        "file_count": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "latest_file": latest.name if latest else None,
        "latest_modified_at": _iso_from_mtime(latest) if latest else None,
        "latest_age_seconds": _age_seconds(latest) if latest else None,
    }


def _scan_sqlite_db(path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "modified_at": _iso_from_mtime(path) if path.exists() else None,
        "age_seconds": _age_seconds(path) if path.exists() else None,
        "tables": [],
        "ok": False,
    }
    if not path.exists():
        return report

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
        try:
            tables = [
                row[0]
                for row in conn.execute(
                    "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
                ).fetchall()
            ]
            for table in tables[:20]:
                try:
                    count = conn.execute(f'select count(*) from "{table}"').fetchone()[0]
                except Exception:
                    count = None
                report["tables"].append({"name": table, "rows": count})
            report["ok"] = True
        finally:
            conn.close()
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _scan_onchain_rows_by_chain(path: Path) -> dict[str, dict[str, int]]:
    rows_by_chain: dict[str, dict[str, int]] = {}
    if not path.exists():
        return rows_by_chain

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
        try:
            for table in ("blocks", "transactions", "swaps", "wallets"):
                try:
                    rows = conn.execute(
                        f'select chain, count(*) from "{table}" group by chain'
                    ).fetchall()
                except Exception:
                    continue
                for chain, count in rows:
                    chain_key = _coverage_chain_key(str(chain or "unknown"))
                    rows_by_chain.setdefault(chain_key, {})[table] = int(count or 0)
        finally:
            conn.close()
    except Exception:
        return rows_by_chain
    return rows_by_chain


def _scan_label_ledger(path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "labels": 0,
        "unique_addresses": 0,
        "strict_source_labels": 0,
        "legacy_or_unverified_labels": 0,
        "derived_labels": 0,
        "high_confidence": 0,
        "chains": [],
        "source_breakdown": {},
        "derived_chains": [],
        "top_entities": [],
        "derived_top_entities": [],
    }
    if not path.exists():
        return report

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
        try:
            report["labels"] = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
            rows = conn.execute("SELECT chain, address, sources_json FROM labels").fetchall()
            unique_addresses: set[tuple[str, str]] = set()
            source_breakdown = Counter()
            strict_count = 0
            for chain, address, sources_json in rows:
                normalized_chain = _coverage_chain_key(str(chain or "unknown"))
                if address:
                    unique_addresses.add((str(address).lower(), normalized_chain))
                sources = []
                if sources_json:
                    try:
                        parsed = json.loads(sources_json)
                        if isinstance(parsed, list):
                            sources = parsed
                    except Exception:
                        sources = []
                source_text = " ".join(
                    str(item.get("source") if isinstance(item, dict) else item)
                    for item in sources
                ).lower()
                if any(marker in source_text for marker in ("manual_verified", "candidate_promotion", "etherscan", "blockscout", "zerion", "cielo")):
                    bucket = "strict_or_external_public"
                    strict_count += 1
                elif "scrapling" in source_text:
                    bucket = "legacy_scrapling"
                elif "entity_labels_legacy" in source_text:
                    bucket = "legacy_local_seed"
                else:
                    bucket = "unknown"
                source_breakdown[bucket] += 1
            report["unique_addresses"] = len(unique_addresses)
            report["strict_source_labels"] = strict_count
            report["legacy_or_unverified_labels"] = max(0, int(report["labels"] or 0) - strict_count)
            report["source_breakdown"] = dict(source_breakdown)
            try:
                report["derived_labels"] = conn.execute("SELECT COUNT(*) FROM derived_labels").fetchone()[0]
            except Exception:
                report["derived_labels"] = 0
            report["high_confidence"] = conn.execute("SELECT COUNT(*) FROM labels WHERE confidence = 'high'").fetchone()[0]
            report["chains"] = [
                {"chain": row[0], "labels": row[1]}
                for row in conn.execute("SELECT chain, COUNT(*) FROM labels GROUP BY chain ORDER BY COUNT(*) DESC").fetchall()
            ]
            try:
                report["derived_chains"] = [
                    {"chain": row[0], "labels": row[1]}
                    for row in conn.execute(
                        "SELECT chain, COUNT(*) FROM derived_labels GROUP BY chain ORDER BY COUNT(*) DESC"
                    ).fetchall()
                ]
                report["derived_top_entities"] = [
                    {"entity": row[0] or "unknown", "labels": row[1]}
                    for row in conn.execute(
                        "SELECT related_entity, COUNT(*) FROM derived_labels GROUP BY related_entity ORDER BY COUNT(*) DESC LIMIT 12"
                    ).fetchall()
                ]
            except Exception:
                pass
            report["top_entities"] = [
                {"entity": row[0] or "unknown", "labels": row[1]}
                for row in conn.execute(
                    "SELECT entity, COUNT(*) FROM labels GROUP BY entity ORDER BY COUNT(*) DESC LIMIT 12"
                ).fetchall()
            ]
        finally:
            conn.close()
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _coverage_tier(metrics: dict[str, Any]) -> Literal["none", "seed", "partial", "useful", "strong"]:
    labelled = int(metrics.get("labelled_addresses") or 0)
    assets = int(metrics.get("assets_tracked") or 0)
    tx_rows = int(metrics.get("rpc_transactions") or 0)
    holders = int(metrics.get("holder_rows") or 0)
    if labelled >= 1000 and assets >= 50 and tx_rows >= 100000 and holders >= 1000:
        return "strong"
    if labelled >= 100 and assets >= 15 and tx_rows >= 10000:
        return "useful"
    if labelled or assets or tx_rows or holders:
        return "partial"
    if metrics.get("rpc_configured"):
        return "seed"
    return "none"


def _build_chain_coverage_matrix(
    *,
    labelled_addresses: set[tuple[str, str]],
    tracked_assets: set[tuple[str, str]],
    holder_rows_by_chain: Counter,
    transfer_rows_by_chain: Counter,
    transfer_value_by_chain: Counter,
    label_ledger: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    onchain_rows = _scan_onchain_rows_by_chain(BACKEND_DATA_DIR / "onchain" / "onchain.db")
    discovered_chains = {
        chain
        for _, chain in labelled_addresses
        if chain and chain != "unknown"
    } | {
        chain
        for _, chain in tracked_assets
        if chain and chain != "unknown"
    } | set(onchain_rows.keys()) | set(ARKHAM_CHAIN_REFERENCE.keys())

    address_counts = Counter(chain for _, chain in labelled_addresses if chain and chain != "unknown")
    for row in (label_ledger or {}).get("chains") or []:
        chain_key = _coverage_chain_key(str(row.get("chain") or "unknown"))
        address_counts[chain_key] = max(int(address_counts.get(chain_key, 0)), int(row.get("labels") or 0))
    derived_counts = Counter()
    for row in (label_ledger or {}).get("derived_chains") or []:
        chain_key = _coverage_chain_key(str(row.get("chain") or "unknown"))
        derived_counts[chain_key] += int(row.get("labels") or 0)
    asset_counts = Counter(chain for _, chain in tracked_assets if chain and chain != "unknown")

    matrix: list[dict[str, Any]] = []
    for chain in sorted(discovered_chains):
        reference = ARKHAM_CHAIN_REFERENCE.get(chain, {})
        db_rows = onchain_rows.get(chain, {})
        metrics = {
            "labelled_addresses": int(address_counts.get(chain, 0)),
            "assets_tracked": int(asset_counts.get(chain, 0)),
            "holder_rows": int(holder_rows_by_chain.get(chain, 0)),
            "transfer_rows": int(transfer_rows_by_chain.get(chain, 0)),
            "transfer_value_usd": round(float(transfer_value_by_chain.get(chain, 0.0)), 2),
            "rpc_blocks": int(db_rows.get("blocks", 0)),
            "rpc_transactions": int(db_rows.get("transactions", 0)),
            "rpc_swaps": int(db_rows.get("swaps", 0)),
            "rpc_wallets": int(db_rows.get("wallets", 0)),
            "derived_labels": int(derived_counts.get(chain, 0)),
            "rpc_configured": bool(reference.get("local_rpc")),
            "rpc_ingestion_enabled": bool(reference.get("local_ingestion")),
        }
        gaps: list[str] = []
        if not metrics["rpc_configured"]:
            gaps.append("rpc_not_configured")
        if not metrics["rpc_transactions"]:
            gaps.append("no_rpc_transactions")
        if metrics["labelled_addresses"] < 100:
            gaps.append("low_label_coverage")
        if metrics["holder_rows"] < 100:
            gaps.append("low_holder_coverage")
        if metrics["transfer_rows"] < 100:
            gaps.append("low_flow_history")

        matrix.append({
            "chain": chain,
            "family": reference.get("family", "unknown"),
            "arkham_reference_coverage_pct": reference.get("arkham_coverage_pct"),
            "local_tier": _coverage_tier(metrics),
            "metrics": metrics,
            "gaps": gaps,
            "next_step": (
                "ingest_recent_rpc_blocks"
                if metrics["rpc_configured"] and metrics["rpc_ingestion_enabled"]
                else "add_rpc_connector_or_snapshot_source"
            ),
        })

    priority = {"strong": 0, "useful": 1, "partial": 2, "seed": 3, "none": 4}
    return sorted(matrix, key=lambda row: (priority.get(row["local_tier"], 9), row["chain"]))


def _build_acquisition_plan(chain_coverage_matrix: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a non-destructive acquisition queue from measured coverage gaps."""
    candidates: list[dict[str, Any]] = []
    for row in chain_coverage_matrix:
        chain = row["chain"]
        metrics = row.get("metrics", {})
        gaps = set(row.get("gaps") or [])
        family = row.get("family") or "unknown"

        labels = int(metrics.get("labelled_addresses") or 0)
        holders = int(metrics.get("holder_rows") or 0)
        rpc_transactions = int(metrics.get("rpc_transactions") or 0)
        transfer_rows = int(metrics.get("transfer_rows") or 0)
        assets = int(metrics.get("assets_tracked") or 0)

        priority_score = 0
        if "low_label_coverage" in gaps:
            priority_score += 45
        if "low_flow_history" in gaps:
            priority_score += 25
        if "low_holder_coverage" in gaps:
            priority_score += 18
        if metrics.get("rpc_configured") and metrics.get("rpc_ingestion_enabled"):
            priority_score += 12
        if row.get("arkham_reference_coverage_pct"):
            priority_score += min(10, int(row["arkham_reference_coverage_pct"]) // 10)
        if chain in {"ethereum", "bsc", "base", "solana", "bitcoin"}:
            priority_score += 8

        next_sources: list[str] = []
        actions: list[str] = []
        if labels < 100:
            next_sources.extend(["openlabels_blockscout", "curated_static_entities", "scrapling_arkham_snapshots"])
            actions.append("seed high-confidence entity labels before increasing RPC volume")
        if holders < 100 and family == "evm":
            next_sources.append("openlabels_blockscout")
            actions.append("expand holder snapshots for top assets on this chain")
        if rpc_transactions < 10_000 and metrics.get("rpc_configured") and metrics.get("rpc_ingestion_enabled"):
            next_sources.append("evm_rpc_logs")
            actions.append("ingest recent confirmed blocks in small capped windows")
        if transfer_rows < 100:
            next_sources.append("scrapling_arkham_snapshots")
            actions.append("normalize entity transfer/counterparty snapshots")
        if assets < 20:
            next_sources.append("zerion_cielo_wallet_intel")
            actions.append("validate wallet asset surfaces through portfolio providers")

        candidates.append({
            "chain": chain,
            "family": family,
            "priority_score": priority_score,
            "local_tier": row.get("local_tier"),
            "current": {
                "labelled_addresses": labels,
                "holder_rows": holders,
                "rpc_transactions": rpc_transactions,
                "transfer_rows": transfer_rows,
                "assets_tracked": assets,
            },
            "next_sources": _dedupe_keep_order(next_sources),
            "safe_actions": _dedupe_keep_order(actions),
            "do_not_do_yet": [
                "full historical RPC backfill",
                "client-facing manipulation alerts",
                "copy-trading automation based on this chain alone",
            ] if row.get("local_tier") in {"none", "seed", "partial"} else [],
        })

    prioritized = sorted(candidates, key=lambda item: item["priority_score"], reverse=True)
    return {
        "reference": ARKHAM_REFERENCE_METRICS,
        "source_catalog": ACQUISITION_SOURCE_CATALOG,
        "strategy": [
            "label-first: increase address/entity attribution before bulk RPC ingestion",
            "chain-scoped: never merge ETH/BSC/Solana activity without explicit chain source",
            "raw-vs-intel: store raw RPC facts separately from labels, confidence and entity attribution",
            "dedupe-first: every imported row needs a deterministic dedupe key",
        ],
        "priority_queue": prioritized[:10],
        "minimum_useful_thresholds": {
            "per_chain_labelled_addresses": 1000,
            "per_chain_rpc_transactions": 100000,
            "per_chain_holder_rows": 1000,
            "per_chain_transfer_rows": 10000,
        },
    }


_ARKHAM_COVERAGE_CACHE: dict[str, Any] = {"signature": None, "report": None}


def _build_arkham_coverage_report() -> dict[str, Any]:
    """Return an honest local equivalent of Arkham API coverage metrics."""
    files = sorted(SCRAPLING_NORMALIZED_DIR.glob("*.json")) if SCRAPLING_NORMALIZED_DIR.exists() else []
    signature = _normalized_files_signature(files)
    if _ARKHAM_COVERAGE_CACHE.get("signature") == signature and _ARKHAM_COVERAGE_CACHE.get("report"):
        return _ARKHAM_COVERAGE_CACHE["report"]

    labelled_addresses: set[tuple[str, str]] = set()
    labelled_entities: set[str] = set()
    tracked_assets: set[tuple[str, str]] = set()
    tracked_chains: set[str] = set()
    source_files: list[dict[str, Any]] = []
    entity_values: dict[str, float] = {}
    transfer_value_usd = 0.0
    transfer_count = 0
    holder_rows = 0
    holder_tokens: dict[str, int] = {}
    holder_rows_by_chain = Counter()
    token_transfer_rows: dict[str, int] = {}
    entity_wallet_rows: dict[str, int] = {}
    transfer_rows_by_chain = Counter()
    transfer_value_by_chain = Counter()
    source_breakdown = Counter()
    cache_reports: list[dict[str, Any]] = []

    def register_wallet(address: str, chain: str, label: str = "", entity: str = "") -> None:
        address = str(address or "").strip().lower()
        chain = _coverage_chain_key(chain) or "unknown"
        if address:
            labelled_addresses.add((address, chain))
            tracked_chains.add(chain)
        if label:
            labelled_entities.add(str(label).split(":", 1)[0].strip().lower())
        if entity:
            labelled_entities.add(str(entity).strip().lower())

    def add_asset(symbol: str, chain: str) -> None:
        symbol = str(symbol or "").strip().upper()
        chain = _coverage_chain_key(chain) or "unknown"
        if symbol:
            tracked_assets.add((symbol, chain))
        if chain and chain != "unknown":
            tracked_chains.add(chain)

    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        kind = str(payload.get("kind") or "unknown").lower()
        target = str(payload.get("target") or path.stem).lower()
        source_breakdown[kind] += 1

        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        entity = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
        entity_name = str(entity.get("name") or target).strip().lower()
        wallets = payload.get("wallets") if isinstance(payload.get("wallets"), list) else []
        holdings = payload.get("holdings") if isinstance(payload.get("holdings"), list) else []
        counterparties = payload.get("counterparties") if isinstance(payload.get("counterparties"), list) else []
        transfers = payload.get("transfers") if isinstance(payload.get("transfers"), list) else []
        chains = payload.get("chains") if isinstance(payload.get("chains"), list) else []
        holdings_value = sum(
            _safe_float(holding.get("estimated_value_usd")) or 0.0
            for holding in holdings
            if isinstance(holding, dict)
        )
        value = (
            _safe_float(summary.get("total_balance_usd"))
            or _safe_float(entity.get("balance_usd"))
            or _safe_float(payload.get("estimated_total_value_usd"))
            or holdings_value
            or 0.0
        )
        if kind == "entity" and entity_name:
            entity_values[entity_name] = max(entity_values.get(entity_name, 0.0), value)

        for wallet in wallets:
            if not isinstance(wallet, dict):
                continue
            register_wallet(
                str(wallet.get("address") or ""),
                str(wallet.get("chain") or ""),
                str(wallet.get("label") or ""),
                str(wallet.get("entity") or entity_name or ""),
            )
        if wallets and entity_name:
            entity_wallet_rows[entity_name] = entity_wallet_rows.get(entity_name, 0) + len(wallets)

        for holding in holdings:
            if not isinstance(holding, dict):
                continue
            add_asset(str(holding.get("symbol") or holding.get("name") or ""), str(holding.get("chain") or ""))

        for counterparty in counterparties:
            if not isinstance(counterparty, dict):
                continue
            counterparty_chain = _coverage_chain_key(str(counterparty.get("chain") or ""))
            counterparty_value = _safe_float(counterparty.get("value_usd")) or 0.0
            register_wallet(
                str(counterparty.get("address") or ""),
                counterparty_chain,
                str(counterparty.get("label") or ""),
                str(counterparty.get("entity") or ""),
            )
            transfer_value_usd += counterparty_value
            if counterparty_chain:
                transfer_rows_by_chain[counterparty_chain] += 1
                transfer_value_by_chain[counterparty_chain] += counterparty_value

        for transfer in transfers:
            if not isinstance(transfer, dict):
                continue
            transfer_count += 1
            chain = _coverage_chain_key(str(transfer.get("chain") or transfer.get("from_chain") or transfer.get("to_chain") or ""))
            transfer_value = _safe_float(transfer.get("value_usd")) or 0.0
            transfer_value_usd += transfer_value
            if chain:
                transfer_rows_by_chain[chain] += 1
                transfer_value_by_chain[chain] += transfer_value
            add_asset(str(transfer.get("token_symbol") or ""), chain)
            token_transfer_rows[target] = token_transfer_rows.get(target, 0) + 1
            register_wallet(str(transfer.get("from") or ""), str(transfer.get("from_chain") or chain), str(transfer.get("from_label") or transfer.get("from_display_label") or ""), str(transfer.get("from_entity") or ""))
            register_wallet(str(transfer.get("to") or ""), str(transfer.get("to_chain") or chain), str(transfer.get("to_label") or transfer.get("to_display_label") or ""), str(transfer.get("to_entity") or ""))

        for chain_row in chains:
            if isinstance(chain_row, dict) and chain_row.get("chain"):
                tracked_chains.add(_coverage_chain_key(str(chain_row.get("chain"))))

        source_files.append({
            "file": path.name,
            "kind": kind,
            "target": target,
            "wallets": len(wallets),
            "holdings": len(holdings),
            "counterparties": len(counterparties),
            "transfers": len(transfers),
            "value_usd": round(value, 2),
            "generated_at": payload.get("generated_at"),
            "source": payload.get("source") or "scrapling_normalized",
        })

    for cache_path in [
        Path(__file__).resolve().parents[1] / "data" / "arkham" / "cache.json",
        Path(__file__).resolve().parents[2] / "data" / "arkham" / "cache.json",
    ]:
        if not cache_path.exists():
            continue
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        holders_cache = cache.get("holders_cache") if isinstance(cache.get("holders_cache"), dict) else {}
        cache_reports.append({
            "path": str(cache_path),
            "modified_at": _iso_from_mtime(cache_path),
            "age_seconds": _age_seconds(cache_path),
            "bytes": cache_path.stat().st_size,
            "entities": len(cache.get("entities", {}) if isinstance(cache.get("entities"), dict) else {}),
            "addresses": len(cache.get("addresses", {}) if isinstance(cache.get("addresses"), dict) else {}),
            "holders_tokens": len(holders_cache),
            "holders_rows": sum(len(rows) for rows in holders_cache.values() if isinstance(rows, list)),
            "search_cache_entries": len(cache.get("entities_search_cache", {}) if isinstance(cache.get("entities_search_cache"), dict) else {}),
            "metadata": cache.get("metadata") if isinstance(cache.get("metadata"), dict) else {},
        })
        for token_key, holders in holders_cache.items():
            if not isinstance(holders, list):
                continue
            chain_key, _ = _parse_holders_cache_key(str(token_key))
            chain_key = _coverage_chain_key(chain_key or "ethereum")
            previous_holder_count = holder_tokens.get(str(token_key), 0)
            holder_tokens[str(token_key)] = max(previous_holder_count, len(holders))
            holder_rows += len(holders)
            if len(holders) > previous_holder_count:
                holder_rows_by_chain[chain_key] += len(holders) - previous_holder_count
            for holder in holders:
                if not isinstance(holder, dict):
                    continue
                register_wallet(
                    str(holder.get("address") or ""),
                    str(holder.get("chain") or chain_key),
                    str(holder.get("arkham_label") or holder.get("label") or ""),
                    str(holder.get("arkham_entity") or ""),
                )

    label_ledger_report = _scan_label_ledger(BACKEND_DATA_DIR / "arkham" / "label_ledger.db")
    snapshot_labelled_addresses = len(labelled_addresses)
    ledger_unique_addresses = int(label_ledger_report.get("unique_addresses") or 0)
    chain_coverage_matrix = _build_chain_coverage_matrix(
        labelled_addresses=labelled_addresses,
        tracked_assets=tracked_assets,
        holder_rows_by_chain=holder_rows_by_chain,
        transfer_rows_by_chain=transfer_rows_by_chain,
        transfer_value_by_chain=transfer_value_by_chain,
        label_ledger=label_ledger_report,
    )
    acquisition_plan = _build_acquisition_plan(chain_coverage_matrix)

    report = {
        "ok": True,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "arkham_reference": {
            "url": "https://intel.arkm.com/api",
            "metrics_to_mirror": [
                "on_chain_value_attributed",
                "asset_flow_tracked",
                "addresses_labelled",
            ],
        },
        "coverage": {
            "on_chain_value_attributed_usd": round(sum(entity_values.values()), 2),
            "asset_flow_tracked_usd": round(transfer_value_usd, 2),
            "asset_flow_tracked_rows": transfer_count,
            "addresses_labelled": max(snapshot_labelled_addresses, ledger_unique_addresses),
            "snapshot_addresses_labelled": snapshot_labelled_addresses,
            "label_ledger_unique_addresses": ledger_unique_addresses,
            "strict_source_labels": label_ledger_report.get("strict_source_labels", 0),
            "legacy_or_unverified_labels": label_ledger_report.get("legacy_or_unverified_labels", 0),
            "entities_labelled": len([item for item in labelled_entities if item]),
            "assets_tracked": len(tracked_assets),
            "chains_tracked": len([chain for chain in tracked_chains if chain and chain != "unknown"]),
            "holder_rows_cached": sum(holder_tokens.values()),
            "holder_tokens_cached": len(holder_tokens),
            "normalized_snapshots": len(files),
        },
        "data_map": {
            "summary": {
                "local_sources": [
                    "scrapling_normalized",
                    "arkham_cache_json",
                    "onchain_sqlite",
                    "blockscout_holder_cache",
                    "static_entity_catalog",
                ],
                "live_sources": [
                    "rpc_when_endpoint_called",
                    "coingecko_when_token_endpoint_called",
                    "blockscout_when_holders_cache_miss",
                    "firecrawl_only_when_enabled_and_cache_miss",
                ],
                "not_yet_full_arkham": [
                    "complete historical balance archive",
                    "complete transfer archive per entity",
                    "full exchange wallet graph",
                    "fresh wallet clustering",
                    "social/profile pages for every entity",
                ],
            },
            "freshness": {
                "scrapling_normalized": _scan_data_files(SCRAPLING_NORMALIZED_DIR, "*.json"),
                "scrapling_raw": _scan_data_files(BACKEND_DATA_DIR / "arkham" / "scrapling", "*.json"),
                "arkham_cache": cache_reports,
                "onchain": _scan_data_files(BACKEND_DATA_DIR / "onchain", "*"),
            },
            "onchain_sqlite": [
                _scan_sqlite_db(path)
                for path in sorted((BACKEND_DATA_DIR / "onchain").glob("*.db"))[:20]
            ] if (BACKEND_DATA_DIR / "onchain").exists() else [],
            "label_ledger": label_ledger_report,
            "quality_policy": {
                "value_policy": "observed_local_value_only_not_full_archive",
                "holder_policy": "cached_rows_partial_source_trace_required",
                "rpc_policy": "chain_scoped_never_price_one_chain_with_another",
                "scraping_policy": "cache_first_firecrawl_last_resort",
            },
            "chain_coverage_matrix": chain_coverage_matrix,
            "acquisition_plan": acquisition_plan,
            "rpc_ingestion_gate": {
                "decision": "manual_small_windows_only_until_chain_tier_is_useful",
                "reason": "RPC gives raw facts; Arkham-like value requires labels, attribution, and chain-scoped source quality first.",
                "safe_now": [
                    "ethereum_recent_blocks",
                    "bsc_recent_blocks",
                ],
                "not_safe_yet": [
                    "full historical archive ingestion",
                    "cross-chain wallet clustering without confidence scoring",
                    "token manipulation alerts without holder/flow baselines",
                ],
            },
        },
        "source_breakdown": dict(source_breakdown),
        "top_entities_by_value": [
            {"entity": entity, "value_usd": round(value, 2), "wallet_rows": entity_wallet_rows.get(entity, 0)}
            for entity, value in sorted(entity_values.items(), key=lambda item: item[1], reverse=True)[:15]
        ],
        "top_holder_tokens": [
            {"token": token, "holders_cached": count}
            for token, count in sorted(holder_tokens.items(), key=lambda item: item[1], reverse=True)[:20]
        ],
        "top_transfer_snapshots": [
            {"target": target, "transfer_rows": count}
            for target, count in sorted(token_transfer_rows.items(), key=lambda item: item[1], reverse=True)[:20]
        ],
        "files": sorted(source_files, key=lambda row: (row["kind"], row["target"]))[:80],
        "limitations": [
            "This is local observed coverage, not full Arkham coverage.",
            "Holder rows come from cached Blockscout/API fallbacks and may be partial.",
            "Attributed value is summed from normalized entity snapshots, deduped by entity name.",
            "Flow value is observed transfer/counterparty USD value, not a complete chain archive.",
        ],
    }
    _ARKHAM_COVERAGE_CACHE["signature"] = signature
    _ARKHAM_COVERAGE_CACHE["report"] = report
    return report


def _search_wallets_from_scrapling_snapshots(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    query_variants, query_compact_variants = _search_query_variants(query)
    if not query_variants:
        return []
    matches: list[dict[str, Any]] = []
    for row in _load_scrapling_search_index().get("wallets", []):
        if not _matches_searchable_row(row, query_variants, query_compact_variants):
            continue
        matches.append(_strip_search_fields(row))
        if len(matches) >= limit:
            break
    return matches


def _search_entities_from_scrapling_snapshots(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    query_variants, query_compact_variants = _search_query_variants(query)
    if not query_variants:
        return []
    matches: list[dict[str, Any]] = []
    for row in _load_scrapling_search_index().get("entities", []):
        if not _matches_searchable_row(row, query_variants, query_compact_variants):
            continue
        matches.append(_strip_search_fields(row))
        if len(matches) >= limit:
            break
    return matches


def _search_tokens_from_scrapling_snapshots(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    query_variants, query_compact_variants = _search_query_variants(query)
    if not query_variants:
        return []
    matches: list[dict[str, Any]] = []
    for row in _load_scrapling_search_index().get("tokens", []):
        if not _matches_searchable_row(row, query_variants, query_compact_variants):
            continue
        matches.append(_strip_search_fields(row))
        if len(matches) >= limit:
            break
    return matches


def _merge_keyed_rows(
    primary_rows: list[dict[str, Any]] | None,
    secondary_rows: list[dict[str, Any]] | None,
    *,
    key_fields: list[str],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    def _row_key(row: dict[str, Any]) -> str | None:
        parts = [str(row.get(field) or "").strip().lower() for field in key_fields]
        if not any(parts):
            return None
        return "|".join(parts)

    for row in list(primary_rows or []) + list(secondary_rows or []):
        if not isinstance(row, dict):
            continue
        key = _row_key(row)
        if not key:
            continue
        existing = merged.get(key, {})
        combined = dict(existing)
        for field, value in row.items():
            if value not in (None, "", [], {}):
                combined[field] = value
        merged[key] = combined

    rows = list(merged.values())
    if limit is not None:
        return rows[:limit]
    return rows


def _merge_chain_rows(
    primary_rows: list[dict[str, Any]] | None,
    secondary_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in list(primary_rows or []) + list(secondary_rows or []):
        if not isinstance(row, dict):
            continue
        chain = str(row.get("chain") or "").strip().lower()
        if not chain:
            continue
        existing = merged.get(chain, {"chain": chain, "hits": 0})
        existing["hits"] = max(_safe_int(existing.get("hits")) or 0, _safe_int(row.get("hits")) or 0)
        merged[chain] = existing
    return sorted(merged.values(), key=lambda item: item.get("hits") or 0, reverse=True)


def _merge_tag_rows(
    primary_rows: list[dict[str, Any]] | None,
    secondary_rows: list[dict[str, Any]] | None,
    *,
    limit: int = 16,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in list(primary_rows or []) + list(secondary_rows or []):
        if not isinstance(row, dict):
            continue
        tag = str(row.get("tag") or "").strip()
        if not tag:
            continue
        key = tag.lower()
        existing = merged.get(key, {"tag": tag, "count": 0})
        existing["count"] = max(_safe_int(existing.get("count")) or 0, _safe_int(row.get("count")) or 0)
        merged[key] = existing
    return sorted(merged.values(), key=lambda item: item.get("count") or 0, reverse=True)[:limit]


def _canonical_surface_label(label: str | None, address: str | None = None) -> str:
    raw = str(label or "").strip()
    if not raw:
        fallback = _truncate_addr(str(address or ""))
        return fallback or "Unlabeled"

    compact = raw.split(" | ", 1)[0].strip()
    if ":" in compact:
        prefix = compact.split(":", 1)[0].strip()
        if prefix and len(prefix) >= 3:
            compact = prefix

    while compact.endswith(")") and "(" in compact:
        prefix, _, suffix = compact.rpartition("(")
        candidate = suffix[:-1].strip().lower()
        if candidate.startswith("0x") or len(candidate) <= 6:
            compact = prefix.strip()
            continue
        break

    return compact or raw


def _surface_category(label: str) -> str:
    normalized = str(label or "").lower()
    if any(keyword in normalized for keyword in ("binance", "coinbase", "kraken", "mexc", "bitget", "gate", "okx", "kucoin", "bybit", "htx", "exchange", "prime")):
        return "exchange"
    if any(keyword in normalized for keyword in ("swap", "dex", "router", "pool", "vault", "amm")):
        return "dex"
    if any(keyword in normalized for keyword in ("bridge", "debridge", "wormhole", "layerzero", "stargate")):
        return "bridge"
    if any(keyword in normalized for keyword in ("blackrock", "fidelity", "grayscale", "fund", "capital", "ventures", "etf")):
        return "fund"
    if any(keyword in normalized for keyword in ("custody", "treasury")):
        return "custody"
    return "wallet"


def _history_window_label(start_ts: int | None, end_ts: int | None) -> str:
    if not start_ts:
        return "Recent"

    start_dt = datetime.utcfromtimestamp(start_ts)
    if not end_ts or end_ts == start_ts:
        return start_dt.strftime("%d %b %H:%M")

    end_dt = datetime.utcfromtimestamp(end_ts)
    if start_dt.date() == end_dt.date():
        return f"{start_dt.strftime('%d %b')} {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"
    return f"{start_dt.strftime('%d %b')} - {end_dt.strftime('%d %b')}"


def _build_entity_surfaces(
    token_list: list[dict[str, Any]],
    wallet_list: list[dict[str, Any]],
    recent_activity: list[dict[str, Any]],
    total_value_usd: float,
) -> dict[str, Any]:
    token_surface_map: dict[str, dict[str, Any]] = {}
    network_map: dict[str, dict[str, Any]] = {}
    venue_map: dict[str, dict[str, Any]] = {}
    role_counter: Counter[str] = Counter()
    timed_activity: list[dict[str, Any]] = []

    for wallet in wallet_list:
        wallet_roles = wallet.get("flags") or ["wallet"]
        for role in wallet_roles:
            label = str(role or "").strip().lower()
            if label:
                role_counter[label] += 1

        chain = str(wallet.get("chain") or "unknown").lower()
        network_entry = network_map.setdefault(
            chain,
            {
                "chain": chain,
                "observed_value_usd": 0.0,
                "inflow_usd": 0.0,
                "outflow_usd": 0.0,
                "net_usd": 0.0,
                "tx_count": 0,
                "wallet_addresses": set(),
                "asset_keys": set(),
            },
        )
        address = str(wallet.get("address") or "").lower()
        if address:
            network_entry["wallet_addresses"].add(address)

    for token in token_list:
        token_key = _asset_surface_key(token)
        observed_value = _safe_float(token.get("estimated_value_usd")) or 0.0
        token_surface_map[token_key] = {
            "key": token_key,
            "symbol": token.get("symbol"),
            "name": token.get("name"),
            "chain": token.get("chain"),
            "contract_address": token.get("contract_address"),
            "observed_value_usd": round(observed_value, 2) if observed_value > 0 else None,
            "wallet_count": token.get("wallet_count") or 0,
            "share_pct": round((observed_value / total_value_usd) * 100, 2) if total_value_usd > 0 and observed_value > 0 else None,
            "recent_inflow_usd": 0.0,
            "recent_outflow_usd": 0.0,
            "recent_net_usd": 0.0,
            "recent_tx_count": 0,
            "price_usd": token.get("price_usd"),
            "max_holder_share_pct": token.get("max_holder_share_pct"),
        }

        chain = str(token.get("chain") or "unknown").lower()
        network_entry = network_map.setdefault(
            chain,
            {
                "chain": chain,
                "observed_value_usd": 0.0,
                "inflow_usd": 0.0,
                "outflow_usd": 0.0,
                "net_usd": 0.0,
                "tx_count": 0,
                "wallet_addresses": set(),
                "asset_keys": set(),
            },
        )
        network_entry["observed_value_usd"] += observed_value
        network_entry["asset_keys"].add(token_key)

    for activity in recent_activity:
        timestamp = _to_unix_timestamp(activity.get("timestamp"))
        direction = str(activity.get("direction") or "").lower()
        token_symbol = str(activity.get("token_symbol") or "").upper()
        chain = str(activity.get("chain") or "unknown").lower()
        value_usd = _safe_float(activity.get("value_usd")) or 0.0

        if timestamp is not None:
            timed_activity.append({
                "timestamp": timestamp,
                "direction": direction,
                "value_usd": value_usd,
                "token_symbol": token_symbol,
                "counterparty_label": activity.get("counterparty_label"),
            })

        token_match = next(
            (
                surface for surface in token_surface_map.values()
                if str(surface.get("symbol") or "").upper() == token_symbol and str(surface.get("chain") or "").lower() == chain
            ),
            None,
        )
        if token_match is None:
            token_key = f"{chain}:{token_symbol or 'unknown'}"
            token_match = token_surface_map.setdefault(
                token_key,
                {
                    "key": token_key,
                    "symbol": token_symbol or "UNKNOWN",
                    "name": activity.get("token_name") or token_symbol or "Observed Token",
                    "chain": chain,
                    "contract_address": None,
                    "observed_value_usd": None,
                    "wallet_count": 0,
                    "share_pct": None,
                    "recent_inflow_usd": 0.0,
                    "recent_outflow_usd": 0.0,
                    "recent_net_usd": 0.0,
                    "recent_tx_count": 0,
                    "price_usd": None,
                    "max_holder_share_pct": None,
                },
            )

        if direction == "inflow":
            token_match["recent_inflow_usd"] += value_usd
        elif direction == "outflow":
            token_match["recent_outflow_usd"] += value_usd
        token_match["recent_net_usd"] = token_match["recent_inflow_usd"] - token_match["recent_outflow_usd"]
        token_match["recent_tx_count"] += 1

        network_entry = network_map.setdefault(
            chain,
            {
                "chain": chain,
                "observed_value_usd": 0.0,
                "inflow_usd": 0.0,
                "outflow_usd": 0.0,
                "net_usd": 0.0,
                "tx_count": 0,
                "wallet_addresses": set(),
                "asset_keys": set(),
            },
        )
        if direction == "inflow":
            network_entry["inflow_usd"] += value_usd
        elif direction == "outflow":
            network_entry["outflow_usd"] += value_usd
        network_entry["net_usd"] = network_entry["inflow_usd"] - network_entry["outflow_usd"]
        network_entry["tx_count"] += 1
        if token_symbol:
            network_entry["asset_keys"].add(f"{chain}:{token_symbol}")

        venue_label = _canonical_surface_label(activity.get("counterparty_label"), activity.get("counterparty_address"))
        venue_key = _slugify_text(venue_label) or venue_label.lower()
        venue_entry = venue_map.setdefault(
            venue_key,
            {
                "label": venue_label,
                "category": _surface_category(venue_label),
                "inflow_usd": 0.0,
                "outflow_usd": 0.0,
                "net_usd": 0.0,
                "tx_count": 0,
                "token_symbols": set(),
            },
        )
        if direction == "inflow":
            venue_entry["inflow_usd"] += value_usd
        elif direction == "outflow":
            venue_entry["outflow_usd"] += value_usd
        venue_entry["net_usd"] = venue_entry["inflow_usd"] - venue_entry["outflow_usd"]
        venue_entry["tx_count"] += 1
        if token_symbol:
            venue_entry["token_symbols"].add(token_symbol)

    timed_activity.sort(key=lambda item: item["timestamp"])
    balances_history: list[dict[str, Any]] = []
    if timed_activity:
        bucket_count = min(8, len(timed_activity))
        chunk_size = max(1, (len(timed_activity) + bucket_count - 1) // bucket_count)
        for chunk_index, start_index in enumerate(range(0, len(timed_activity), chunk_size)):
            chunk = timed_activity[start_index:start_index + chunk_size]
            if not chunk:
                continue
            inflow_usd = sum(item["value_usd"] for item in chunk if item["direction"] == "inflow")
            outflow_usd = sum(item["value_usd"] for item in chunk if item["direction"] == "outflow")
            net_usd = inflow_usd - outflow_usd
            balances_history.append({
                "key": f"bucket-{chunk_index}",
                "label": _history_window_label(chunk[0]["timestamp"], chunk[-1]["timestamp"]),
                "start_ts": chunk[0]["timestamp"],
                "end_ts": chunk[-1]["timestamp"],
                "inflow_usd": round(inflow_usd, 2) if inflow_usd else 0.0,
                "outflow_usd": round(outflow_usd, 2) if outflow_usd else 0.0,
                "net_usd": round(net_usd, 2) if net_usd else 0.0,
                "tx_count": len(chunk),
                "dominant_token": Counter(item["token_symbol"] for item in chunk if item.get("token_symbol")).most_common(1)[0][0] if any(item.get("token_symbol") for item in chunk) else None,
                "dominant_counterparty": Counter(item["counterparty_label"] for item in chunk if item.get("counterparty_label")).most_common(1)[0][0] if any(item.get("counterparty_label") for item in chunk) else None,
            })

        total_net = sum(item["net_usd"] for item in balances_history)
        running_balance = max(total_value_usd - total_net, 0.0) if total_value_usd > 0 else 0.0
        cumulative_net = 0.0
        for bucket in balances_history:
            cumulative_net += bucket["net_usd"]
            if total_value_usd > 0:
                running_balance = max(running_balance + bucket["net_usd"], 0.0)
                bucket["balance_estimate_usd"] = round(running_balance, 2)
            else:
                bucket["balance_estimate_usd"] = round(cumulative_net, 2)
            bucket["cumulative_net_usd"] = round(cumulative_net, 2)

    token_balance_surface = sorted(
        (
            {
                **token,
                "recent_inflow_usd": round(token["recent_inflow_usd"], 2) if token["recent_inflow_usd"] else 0.0,
                "recent_outflow_usd": round(token["recent_outflow_usd"], 2) if token["recent_outflow_usd"] else 0.0,
                "recent_net_usd": round(token["recent_net_usd"], 2) if token["recent_net_usd"] else 0.0,
            }
            for token in token_surface_map.values()
        ),
        key=lambda item: (
            item.get("observed_value_usd") or 0,
            item.get("recent_tx_count") or 0,
            abs(item.get("recent_net_usd") or 0),
        ),
        reverse=True,
    )[:12]

    network_usage = sorted(
        (
            {
                "chain": item["chain"],
                "observed_value_usd": round(item["observed_value_usd"], 2) if item["observed_value_usd"] else None,
                "inflow_usd": round(item["inflow_usd"], 2) if item["inflow_usd"] else 0.0,
                "outflow_usd": round(item["outflow_usd"], 2) if item["outflow_usd"] else 0.0,
                "net_usd": round(item["net_usd"], 2) if item["net_usd"] else 0.0,
                "tx_count": item["tx_count"],
                "wallet_count": len(item["wallet_addresses"]),
                "asset_count": len(item["asset_keys"]),
            }
            for item in network_map.values()
        ),
        key=lambda item: (
            item.get("observed_value_usd") or 0,
            abs(item.get("net_usd") or 0),
            item.get("tx_count") or 0,
        ),
        reverse=True,
    )

    exchange_usage = sorted(
        (
            {
                "label": item["label"],
                "category": item["category"],
                "inflow_usd": round(item["inflow_usd"], 2) if item["inflow_usd"] else 0.0,
                "outflow_usd": round(item["outflow_usd"], 2) if item["outflow_usd"] else 0.0,
                "net_usd": round(item["net_usd"], 2) if item["net_usd"] else 0.0,
                "tx_count": item["tx_count"],
                "token_symbols": sorted(item["token_symbols"])[:6],
            }
            for item in venue_map.values()
        ),
        key=lambda item: (
            abs(item.get("net_usd") or 0),
            item.get("tx_count") or 0,
            item.get("inflow_usd") or 0,
            item.get("outflow_usd") or 0,
        ),
        reverse=True,
    )[:12]

    total_roles = sum(role_counter.values()) or 0
    role_clusters = [
        {
            "role": role,
            "wallet_count": count,
            "share_pct": round((count / total_roles) * 100, 2) if total_roles > 0 else None,
        }
        for role, count in role_counter.most_common(10)
    ]

    return {
        "balances_history": balances_history,
        "token_balance_surface": token_balance_surface,
        "network_usage": network_usage,
        "exchange_usage": exchange_usage,
        "role_clusters": role_clusters,
    }


def _entity_focus_pairs(entity_slug: str, entity: dict[str, Any] | None, profile: dict[str, Any] | None) -> list[dict[str, str]]:
    from services.arkham_scraper import KNOWN_CONTRACTS

    focus_pairs: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    explicit_pairs = (profile or {}).get("coverage_pairs") or []
    for raw_pair in explicit_pairs:
        if not isinstance(raw_pair, dict):
            continue
        chain = str(raw_pair.get("chain") or "").lower().strip()
        symbol = str(raw_pair.get("symbol") or "").lower().strip()
        contract_address = str(
            raw_pair.get("contract_address")
            or KNOWN_CONTRACTS.get(symbol, {}).get(chain)
            or ""
        ).strip()
        if chain not in EVM_CHAINS or not symbol or not contract_address.startswith("0x"):
            continue
        pair_key = (chain, contract_address.lower())
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        focus_pairs.append({
            "chain": chain,
            "symbol": symbol,
            "contract_address": contract_address.lower(),
        })

    if focus_pairs:
        return focus_pairs[:6]

    coverage_tokens = [
        str(token or "").lower().strip()
        for token in (profile or {}).get("coverage_tokens") or []
        if str(token or "").strip()
    ] or ["usdt", "usdc", "weth", "wbtc"]

    raw_chains = _dedupe_keep_order(
        list((profile or {}).get("coverage_chains") or [])
        + list((entity or {}).get("chains") or [])
    )
    if not raw_chains:
        raw_chains = ["ethereum"]

    for chain in raw_chains:
        chain_lower = chain.lower()
        if chain_lower not in EVM_CHAINS:
            continue
        for symbol in coverage_tokens:
            contract_address = str(KNOWN_CONTRACTS.get(symbol, {}).get(chain_lower) or "").strip()
            if not contract_address.startswith("0x"):
                continue
            pair_key = (chain_lower, contract_address.lower())
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            focus_pairs.append({
                "chain": chain_lower,
                "symbol": symbol,
                "contract_address": contract_address.lower(),
            })
            if len(focus_pairs) >= 6:
                return focus_pairs

    return focus_pairs


async def _warm_entity_observations(scraper: Any, entity_slug: str, entity: dict[str, Any] | None) -> dict[str, Any]:
    from services.arkham_scraper import get_entity_profile

    profile = get_entity_profile(entity_slug, entity)
    holders_cache = getattr(scraper, "_cache", {}).setdefault("holders_cache", {})
    focus_pairs = _entity_focus_pairs(entity_slug, entity, profile)

    warm_jobs = []
    for pair in focus_pairs:
        cache_key = f"holders:{pair['chain']}:{pair['contract_address']}"
        cached_holders = holders_cache.get(cache_key)
        if isinstance(cached_holders, list) and len(cached_holders) > 0:
            continue
        warm_jobs.append(
            asyncio.to_thread(
                scraper._fetch_token_holders,
                pair["contract_address"],
                pair["chain"],
            )
        )

    if warm_jobs:
        await asyncio.gather(*warm_jobs, return_exceptions=True)

    profile = dict(profile or {})
    if focus_pairs:
        profile["coverage_pairs"] = focus_pairs
    return profile


def _transfer_label_candidates(tx: dict[str, Any], side: str) -> list[str]:
    direct_tags = [str(tag) for tag in tx.get(f"{side}_tags") or [] if tag]
    address_name = str(tx.get(f"{side}_name") or "").strip()
    metadata_tags = [
        str(tag.get("name") or "").strip()
        for tag in tx.get(f"{side}_metadata_tags") or []
        if isinstance(tag, dict) and tag.get("name")
    ]
    return _dedupe_keep_order(direct_tags + ([address_name] if address_name else []) + metadata_tags)


def _fetch_blockscout_wallet_profile(chain: str, address: str) -> dict[str, Any] | None:
    from services.arkham_scraper import BLOCKSCOUT_API_URLS
    import json
    import urllib.request

    bs_url = BLOCKSCOUT_API_URLS.get(chain, BLOCKSCOUT_API_URLS.get("ethereum"))
    if not bs_url or "graphiql" in bs_url:
        return None

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    def _load(url: str) -> dict[str, Any] | None:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode())

    try:
        info = _load(f"{bs_url}/addresses/{address}") or {}
        counters = _load(f"{bs_url}/addresses/{address}/counters") or {}
        tx_count = _safe_int(counters.get("transactions_count"))
        transfer_count = _safe_int(counters.get("token_transfers_count"))
        bucket = _activity_bucket(tx_count, transfer_count)
        identity = _resolve_address_identity(address, info)
        return {
            "transactions_count": tx_count,
            "token_transfers_count": transfer_count,
            "coin_balance": info.get("coin_balance"),
            "creator_address_hash": info.get("creator_address_hash"),
            "creation_transaction_hash": info.get("creation_transaction_hash"),
            "name": info.get("name"),
            "proxy_type": info.get("proxy_type"),
            "is_verified": info.get("is_verified"),
            "metadata_tags": (info.get("metadata") or {}).get("tags") or [],
            "implementations": [impl.get("name") for impl in info.get("implementations") or [] if isinstance(impl, dict) and impl.get("name")],
            "label": identity.get("label"),
            "entity": identity.get("entity"),
            "wallet_type": identity.get("wallet_type"),
            "flags": identity.get("flags") or [],
            "tags": identity.get("tags") or [],
            "activity_bucket": bucket,
            "fresh_wallet_candidate": bool(bucket == "low"),
            "fresh_wallet_note": (
                "Heuristic based on low tx/token-transfer counts from Blockscout counters; not true wallet age."
                if bucket == "low"
                else None
            ),
        }
    except Exception:
        return None


async def _build_entity_intelligence(
    scraper: Any,
    db: Any,
    entity_slug: str,
    entity: dict[str, Any] | None,
    seed_wallets: list[dict[str, Any]],
) -> dict[str, Any]:
    aliases = _entity_aliases(entity_slug, entity)
    holders_cache = (
        getattr(scraper, "_cache", {}).get("holders_cache")
        or getattr(db, "_cache", {}).get("holders_cache", {})
    )
    observed_wallets: dict[str, dict[str, Any]] = {}
    observed_tokens: dict[str, dict[str, Any]] = {}
    chain_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    snapshots_scanned = 0
    holder_rows_scanned = 0
    rpc_verified_tokens = 0
    rpc_sources: set[str] = set()

    for wallet in seed_wallets or []:
        address = str(wallet.get("address") or "").lower()
        if not address:
            continue
        observed_wallets[address] = {
            "address": address,
            "chain": wallet.get("chain", "ethereum"),
            "label": wallet.get("label") or wallet.get("entity") or _truncate_addr(address),
            "entity": wallet.get("entity") or entity.get("name") if entity else entity_slug,
            "confidence": "high" if _slugify_text(wallet.get("entity", "")) in aliases else "medium",
            "flags": set([wallet.get("wallet_type")] if wallet.get("wallet_type") else []),
            "matched_tags": set(),
            "observed_tokens": [],
            "observed_token_keys": set(),
            "token_symbols": set(),
            "observed_value_usd": 0.0,
            "is_contract": bool(wallet.get("is_contract", False)),
            "ens_domain_name": wallet.get("ens_domain_name"),
            "sources": {"arkham_db"},
            "activity_profile": None,
        }

    for cache_key, holder_list in holders_cache.items():
        chain, contract = _parse_holders_cache_key(cache_key)
        if not chain or not contract or not isinstance(holder_list, list):
            continue

        snapshots_scanned += 1
        holder_rows_scanned += len(holder_list)
        token_meta = _contract_token_metadata(chain, contract)
        token_key = f"{chain}:{contract}"

        for holder in holder_list:
            tags = _extract_holder_tags(holder)
            matched_tags = _match_entity_tags(tags, aliases)
            if not matched_tags:
                continue

            address = str(holder.get("address") or "").lower()
            if not address:
                continue

            chain_counter[chain] += 1
            for tag in tags:
                if tag.get("name"):
                    tag_counter[tag["name"]] += 1

            wallet = observed_wallets.setdefault(
                address,
                {
                    "address": address,
                    "chain": chain,
                    "label": _best_wallet_label(tags, address),
                    "entity": entity.get("name") if entity else entity_slug,
                    "confidence": _wallet_confidence(matched_tags, aliases),
                    "flags": set(),
                    "matched_tags": set(),
                    "observed_tokens": [],
                    "observed_token_keys": set(),
                    "token_symbols": set(),
                    "observed_value_usd": 0.0,
                    "is_contract": bool(holder.get("is_contract", False)),
                    "ens_domain_name": holder.get("ens_domain_name"),
                    "sources": {"holders_cache"},
                    "activity_profile": None,
                },
            )

            wallet["chain"] = wallet.get("chain") or chain
            wallet["label"] = wallet.get("label") or _best_wallet_label(tags, address)
            wallet["confidence"] = "high" if wallet.get("confidence") == "high" else _wallet_confidence(matched_tags, aliases)
            wallet["flags"].update(_wallet_flags(tags))
            wallet["matched_tags"].update(tag.get("name") for tag in matched_tags if tag.get("name"))
            wallet["token_symbols"].add(token_meta["symbol"])
            wallet["sources"].add("holders_cache")
            wallet["is_contract"] = wallet.get("is_contract") or bool(holder.get("is_contract", False))
            wallet["ens_domain_name"] = wallet.get("ens_domain_name") or holder.get("ens_domain_name")

            human_balance = _human_balance(holder.get("balance"), token_meta["decimals"])
            token_observation = {
                "token_key": token_key,
                "symbol": token_meta["symbol"],
                "name": token_meta["name"],
                "chain": chain,
                "contract_address": contract,
                "balance_raw": holder.get("balance"),
                "human_balance": human_balance,
                "percentage": holder.get("percentage"),
                "stablecoin": token_meta["stablecoin"],
                "value_usd": None,
            }
            if token_key not in wallet["observed_token_keys"]:
                wallet["observed_tokens"].append(token_observation)
                wallet["observed_token_keys"].add(token_key)

            token_entry = observed_tokens.setdefault(
                token_key,
                {
                    "symbol": token_meta["symbol"],
                    "name": token_meta["name"],
                    "chain": chain,
                    "contract_address": contract,
                    "decimals": token_meta["decimals"],
                    "stablecoin": token_meta["stablecoin"],
                    "wallet_addresses": set(),
                    "labels": set(),
                    "wallet_count": 0,
                    "human_balance_total": 0.0,
                    "price_usd": None,
                    "estimated_value_usd": None,
                    "max_holder_share_pct": None,
                    "sources": set(["holders_cache"]),
                },
            )
            token_entry["wallet_addresses"].add(address)
            token_entry["labels"].add(wallet["label"])
            token_entry["sources"].add("holders_cache")
            if human_balance is not None:
                token_entry["human_balance_total"] += human_balance
            holder_pct = _safe_float(holder.get("percentage"))
            if holder_pct is not None:
                current_max = token_entry.get("max_holder_share_pct")
                token_entry["max_holder_share_pct"] = max(current_max or 0.0, holder_pct)

    token_list = list(observed_tokens.values())
    token_detail_jobs: list[tuple[dict[str, Any], Any]] = []
    for token in token_list[:6]:
        if token.get("symbol"):
            token_detail_jobs.append((token, asyncio.to_thread(scraper.get_token_detail, token["symbol"].lower(), token["chain"])))

    if token_detail_jobs:
        token_results = await asyncio.gather(*(job for _, job in token_detail_jobs), return_exceptions=True)
        for (token, _), detail in zip(token_detail_jobs, token_results):
            if isinstance(detail, Exception) or not isinstance(detail, dict):
                continue
            token["name"] = detail.get("name") or token["name"]
            token["price_usd"] = detail.get("price_usd")
            token["image"] = detail.get("image")
            token["market_source"] = detail.get("source") or "token_detail"
            token.setdefault("sources", set()).add(token["market_source"])

    rpc_meta_jobs: list[tuple[dict[str, Any], Any]] = []
    try:
        from services.wallet_analyzer import _rpc_erc20_metadata

        for token in token_list[:8]:
            chain = str(token.get("chain") or "").lower()
            rpc_chain = "eth" if chain == "ethereum" else chain
            contract = str(token.get("contract_address") or "").strip()
            if rpc_chain in {"eth", "bsc"} and contract.startswith("0x"):
                rpc_meta_jobs.append((token, asyncio.to_thread(_rpc_erc20_metadata, rpc_chain, contract)))
    except Exception:
        rpc_meta_jobs = []

    if rpc_meta_jobs:
        rpc_results = await asyncio.gather(*(job for _, job in rpc_meta_jobs), return_exceptions=True)
        for (token, _), meta in zip(rpc_meta_jobs, rpc_results):
            if isinstance(meta, Exception) or not isinstance(meta, dict) or meta.get("error"):
                continue
            token["rpc_verified"] = bool(meta.get("symbol") or meta.get("decimals") is not None or meta.get("total_supply_raw"))
            token["rpc_symbol"] = meta.get("symbol")
            token["rpc_decimals"] = meta.get("decimals")
            token["rpc_total_supply"] = meta.get("total_supply")
            token["rpc_source"] = meta.get("source")
            token.setdefault("sources", set()).add(meta.get("source") or "rpc")
            if token["rpc_verified"]:
                rpc_verified_tokens += 1
                if meta.get("source"):
                    rpc_sources.add(str(meta["source"]))

    for token in token_list:
        token["wallet_count"] = len(token.pop("wallet_addresses", set()))
        token["labels"] = sorted(token.pop("labels", set()))[:5]
        token["sources"] = sorted(source for source in token.pop("sources", set()) if source)
        price = _safe_float(token.get("price_usd"))
        if price is None and token.get("stablecoin"):
            price = 1.0
            token["price_usd"] = 1.0
        if price is not None:
            token["estimated_value_usd"] = round(token["human_balance_total"] * price, 2)

    price_by_token = {
        f"{token['chain']}:{token['contract_address']}": _safe_float(token.get("price_usd")) or (1.0 if token.get("stablecoin") else None)
        for token in token_list
    }

    wallet_list = list(observed_wallets.values())
    for wallet in wallet_list:
        total_value = 0.0
        for token_obs in wallet["observed_tokens"]:
            token_price = price_by_token.get(token_obs["token_key"])
            if token_price is not None and token_obs.get("human_balance") is not None:
                token_obs["value_usd"] = round(token_obs["human_balance"] * token_price, 2)
                total_value += token_obs["value_usd"]
        wallet["observed_value_usd"] = round(total_value, 2) if total_value > 0 else None
        wallet["flags"] = sorted(flag for flag in wallet["flags"] if flag)
        wallet["matched_tags"] = sorted(tag for tag in wallet["matched_tags"] if tag)[:6]
        wallet["token_symbols"] = sorted(sym for sym in wallet["token_symbols"] if sym)
        wallet["observed_tokens"] = sorted(
            wallet["observed_tokens"],
            key=lambda token_obs: (
                token_obs.get("value_usd") or 0,
                token_obs.get("human_balance") or 0,
            ),
            reverse=True,
        )
        wallet["observed_token_count"] = len(wallet["observed_tokens"])
        wallet["sources"] = sorted(wallet["sources"])
        wallet.pop("observed_token_keys", None)

    wallet_profile_jobs: list[tuple[dict[str, Any], Any]] = []
    for wallet in wallet_list[:8]:
        chain = str(wallet.get("chain") or "ethereum")
        address = str(wallet.get("address") or "")
        if chain in EVM_CHAINS and address.startswith("0x"):
            wallet_profile_jobs.append((wallet, asyncio.to_thread(_fetch_blockscout_wallet_profile, chain, address)))

    if wallet_profile_jobs:
        wallet_profiles = await asyncio.gather(*(job for _, job in wallet_profile_jobs), return_exceptions=True)
        for (wallet, _), profile in zip(wallet_profile_jobs, wallet_profiles):
            if not isinstance(profile, Exception):
                wallet["activity_profile"] = profile

    activity_sources = sorted(
        token_list,
        key=lambda token: (
            token.get("estimated_value_usd") or 0,
            token.get("wallet_count") or 0,
        ),
        reverse=True,
    )[:4]
    recent_activity: list[dict[str, Any]] = []
    counterparty_map: dict[str, dict[str, Any]] = {}
    wallet_addresses = {wallet["address"] for wallet in wallet_list}

    transfer_jobs: list[tuple[dict[str, Any], Any]] = []
    for token in activity_sources:
        transfer_jobs.append((
            token,
            asyncio.to_thread(scraper._fetch_token_transfers, token["contract_address"], token["chain"], 1, 25),
        ))

    if transfer_jobs:
        transfer_results = await asyncio.gather(*(job for _, job in transfer_jobs), return_exceptions=True)
        seen_tx: set[str] = set()
        for (token, _), transfers in zip(transfer_jobs, transfer_results):
            if isinstance(transfers, Exception) or not isinstance(transfers, list):
                continue
            for tx in transfers:
                tx_hash = str(tx.get("tx_hash") or "")
                if not tx_hash or tx_hash in seen_tx:
                    continue

                from_addr = str(tx.get("from") or "").lower()
                to_addr = str(tx.get("to") or "").lower()
                from_tags = _transfer_label_candidates(tx, "from")
                to_tags = _transfer_label_candidates(tx, "to")
                from_tag_match = any(
                    _slugify_text(tag) in aliases or any(alias in _slugify_text(tag) for alias in aliases)
                    for tag in from_tags
                )
                to_tag_match = any(
                    _slugify_text(tag) in aliases or any(alias in _slugify_text(tag) for alias in aliases)
                    for tag in to_tags
                )
                from_match = from_addr in wallet_addresses or from_tag_match
                to_match = to_addr in wallet_addresses or to_tag_match
                if not from_match and not to_match:
                    continue

                seen_tx.add(tx_hash)
                direction = "internal" if from_match and to_match else "outflow" if from_match else "inflow"
                counterparty_addr = to_addr if direction == "outflow" else from_addr
                counterparty_tags = to_tags if direction == "outflow" else from_tags
                amount = _human_balance(tx.get("value"), token.get("decimals", 18))
                price = _safe_float(token.get("price_usd")) or (1.0 if token.get("stablecoin") else None)
                value_usd = round(amount * price, 2) if amount is not None and price is not None else None
                counterparty_label = _counterparty_label(counterparty_tags, counterparty_addr, aliases)
                if direction in {"outflow", "internal"}:
                    matched_wallet = from_addr or to_addr
                    matched_wallet_tags = from_tags
                else:
                    matched_wallet = to_addr or from_addr
                    matched_wallet_tags = to_tags
                matched_wallet_label = observed_wallets.get(matched_wallet, {}).get("label")
                if not matched_wallet_label:
                    matched_wallet_label = _counterparty_label(matched_wallet_tags, matched_wallet, aliases)

                activity = {
                    "tx_hash": tx_hash,
                    "timestamp": _to_unix_timestamp(tx.get("timestamp")),
                    "direction": direction,
                    "token_symbol": token.get("symbol"),
                    "token_name": token.get("name"),
                    "chain": token.get("chain"),
                    "amount": amount,
                    "value_usd": value_usd,
                    "from": from_addr,
                    "to": to_addr,
                    "wallet_address": matched_wallet,
                    "wallet_label": matched_wallet_label,
                    "counterparty_address": counterparty_addr,
                    "counterparty_label": counterparty_label,
                    "counterparty_tags": counterparty_tags[:4],
                }
                recent_activity.append(activity)

                counterparty_key = (counterparty_addr or counterparty_label or tx_hash).lower()
                counterparty = counterparty_map.setdefault(
                    counterparty_key,
                    {
                        "label": counterparty_label,
                        "address": counterparty_addr,
                        "chain": token.get("chain"),
                        "tx_count": 0,
                        "inflow_count": 0,
                        "outflow_count": 0,
                        "value_usd": 0.0,
                        "source": "blockscout_transfers",
                    },
                )
                counterparty["tx_count"] += 1
                if direction == "inflow":
                    counterparty["inflow_count"] += 1
                elif direction == "outflow":
                    counterparty["outflow_count"] += 1
                if value_usd:
                    counterparty["value_usd"] += value_usd

    recent_activity.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    counterparties = sorted(
        counterparty_map.values(),
        key=lambda item: (item.get("value_usd") or 0, item.get("tx_count") or 0),
        reverse=True,
    )

    token_list.sort(
        key=lambda token: (
            token.get("estimated_value_usd") or 0,
            token.get("wallet_count") or 0,
        ),
        reverse=True,
    )
    wallet_list.sort(
        key=lambda wallet: (
            2 if wallet.get("confidence") == "high" else 1 if wallet.get("confidence") == "medium" else 0,
            wallet.get("observed_value_usd") or 0,
            wallet.get("observed_token_count") or 0,
        ),
        reverse=True,
    )

    total_value_usd = sum(token.get("estimated_value_usd") or 0 for token in token_list)
    surfaces = _build_entity_surfaces(token_list, wallet_list, recent_activity, total_value_usd)
    source_trace = [
        {
            "id": "entity_labels",
            "kind": "attribution",
            "source": "local_arkham_db",
            "count": len(seed_wallets or []),
            "confidence": "medium" if seed_wallets else "low",
            "note": "Seed wallets and locally known Arkham-style labels.",
        },
        {
            "id": "holder_snapshots",
            "kind": "holders",
            "source": "blockscout_holders_cache",
            "count": holder_rows_scanned,
            "confidence": "medium" if holder_rows_scanned else "low",
            "note": "Cached holder rows scanned for labels matching this entity.",
        },
        {
            "id": "rpc_contract_metadata",
            "kind": "rpc",
            "source": ", ".join(sorted(rpc_sources)) if rpc_sources else "not_verified",
            "count": rpc_verified_tokens,
            "confidence": "high" if rpc_verified_tokens else "low",
            "note": "Direct ERC-20 symbol, decimals and supply reads via eth_call where available.",
        },
        {
            "id": "recent_transfers",
            "kind": "transfers",
            "source": "blockscout_token_transfers",
            "count": len(recent_activity),
            "confidence": "medium" if recent_activity else "low",
            "note": "Recent token transfers matched against observed entity wallets.",
        },
    ]

    return {
        "coverage": {
            "snapshots_scanned": snapshots_scanned,
            "holder_rows_scanned": holder_rows_scanned,
            "observed_wallets": len(wallet_list),
            "observed_tokens": len(token_list),
            "recent_activity_count": len(recent_activity),
            "rpc_verified_tokens": rpc_verified_tokens,
            "source_trace": source_trace,
            "coverage_note": (
                "Derived from cached holder snapshots, wallet labels, observed portfolio mix and recent labeled token transfers. "
                "This is partial local coverage, not a full Arkham mirror yet."
            ),
        },
        "chains": [
            {"chain": chain, "hits": count}
            for chain, count in chain_counter.most_common()
        ],
        "top_tags": [
            {"tag": tag, "count": count}
            for tag, count in tag_counter.most_common(10)
            if tag and _slugify_text(tag) not in aliases
        ],
        "observed_holdings": token_list[:12],
        "wallets": wallet_list[:25],
        "recent_activity": recent_activity[:20],
        "counterparties": counterparties[:10],
        "surfaces": surfaces,
        "source_trace": source_trace,
        "estimated_total_value_usd": round(total_value_usd, 2) if total_value_usd > 0 else None,
    }


# =========================================================
# STATUS
# =========================================================

@router.get("/scrapling/probe")
async def arkham_scrapling_probe(
    target: str = Query(..., description="Arkham slug or search target, e.g. binance or ravedao"),
    kind: Literal["entity", "token"] = Query("entity", description="Probe an Arkham entity page or token page"),
    headless: bool = Query(True, description="Run the Scrapling browser headless"),
    real_chrome: bool = Query(False, description="Use local Google Chrome instead of bundled Chromium if available"),
    timeout_ms: int = Query(30000, ge=5000, le=120000, description="Browser timeout for the Scrapling probe"),
    max_xhr: int = Query(25, ge=1, le=100, description="Maximum captured XHR responses to include in the summary"),
    include_bodies: bool = Query(False, description="Include short response body previews in the API result"),
    persist: bool = Query(True, description="Persist the probe JSON into backend/data/arkham/scrapling"),
):
    """
    Probe une page Arkham externe avec Scrapling.

    Objectif:
    - capturer les requetes XHR/fetch de la SPA
    - voir quels payloads structurent la page
    - valider si Scrapling merite une vraie integration data
    """
    try:
        from services.scrapling_probe import (
            ScraplingProbeError,
            get_scrapling_probe_service,
        )

        service = get_scrapling_probe_service()
        result = await asyncio.to_thread(
            service.probe_arkham_page,
            kind,
            target,
            headless=headless,
            real_chrome=real_chrome,
            timeout_ms=timeout_ms,
            max_xhr=max_xhr,
            include_bodies=include_bodies,
            persist=persist,
        )
        return result
    except ScraplingProbeError as e:
        return {
            "available": False,
            "kind": kind,
            "target": target,
            "error": str(e),
            "note": "Install Scrapling in the backend Python runtime before using this probe.",
        }
    except Exception as e:
        return {
            "available": False,
            "kind": kind,
            "target": target,
            "error": str(e),
        }

@router.get("/status")
async def arkham_status():
    """
    Statut complet du système Arkham tracking.
    DB locale, tracker, dernier scrape.
    """
    result = {"status": "unknown", "database": None, "tracker": None}

    try:
        from services.arkham_scraper import get_arkham_db
        db = get_arkham_db()
        result["database"] = db.get_stats()
    except Exception as e:
        result["database_error"] = str(e)

    try:
        from services.arkham_tracker import get_arkham_tracker
        tracker = get_arkham_tracker()
        result["tracker"] = tracker.get_stats()
    except Exception as e:
        result["tracker_error"] = str(e)

    result["status"] = "active" if result["database"] or result["tracker"] else "error"
    return result


@router.get("/coverage")
async def arkham_coverage():
    """
    Local data coverage ledger.

    Mirrors the intent of Arkham's API coverage page, but only reports what
    Core Equity has actually cached/normalized locally.
    """
    return await asyncio.to_thread(_build_arkham_coverage_report)


@router.get("/source-backed-inventory")
async def arkham_source_backed_inventory(
    dry_run: bool = Query(True, description="Must stay true: this endpoint is read-only"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Read-only inventory of local Arkham/source-backed assets.

    This separates trusted local proof layers from hint-only Arkham cache,
    Scrapling snapshots, and disabled live/scraper tooling.
    """
    from services.arkham_source_registry import get_arkham_source_backed_inventory

    return await asyncio.to_thread(
        get_arkham_source_backed_inventory,
        limit=limit,
        dry_run=dry_run,
    )


# =========================================================
# SIGNAUX
# =========================================================

@router.get("/signals")
async def arkham_signals(
    limit: int = Query(50, ge=1, le=200),
    signal_type: Optional[str] = Query(None, description="Filtrer par type: EXCHANGE_DEPOSIT, SMART_MONEY_ACCUM, etc."),
    min_priority: Optional[str] = Query(None, description="Filtrer par priorité min: LOW, MEDIUM, HIGH, CRITICAL"),
):
    """
    Signaux récents du tracker Arkham.
    Filtrables par type et priorité.
    """
    try:
        from services.arkham_tracker import get_arkham_tracker

        tracker = get_arkham_tracker()
        signals = tracker.get_recent_signals(limit)

        # Filtrer par type
        if signal_type:
            signals = [s for s in signals if s.get("signal_type") == signal_type]

        # Filtrer par priorité minimum
        if min_priority:
            priority_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
            min_level = priority_order.get(min_priority, 0)
            signals = [
                s for s in signals
                if priority_order.get(s.get("priority", "LOW"), 0) >= min_level
            ]

        return {"signals": signals, "count": len(signals)}

    except Exception as e:
        return {"signals": [], "count": 0, "error": str(e)}


# =========================================================
# FLOWS
# =========================================================

@router.get("/flows")
async def arkham_flows(
    exchange: Optional[str] = Query(None, description="Filtrer par exchange: binance, coinbase, etc."),
):
    """
    Résumé des flows cumulés par entité.
    Inflow/outflow 24h, net flow, nombre de mouvements.
    """
    try:
        from services.arkham_tracker import get_arkham_tracker

        tracker = get_arkham_tracker()
        flows = tracker.get_entity_flow_summary()

        if exchange:
            exchange_lower = exchange.lower()
            flows = {k: v for k, v in flows.items() if exchange_lower in k.lower()}

        return {"flows": flows, "entities_count": len(flows)}

    except Exception as e:
        return {"flows": {}, "entities_count": 0, "error": str(e)}


# =========================================================
# SMART MONEY
# =========================================================

@router.get("/smart-money")
async def arkham_smart_money(
    limit: int = Query(50, ge=1, le=200),
):
    """
    Activité smart money récente.
    Transferts entre funds, VCs, market makers identifiés.
    """
    try:
        from services.arkham_tracker import get_arkham_tracker

        tracker = get_arkham_tracker()
        activity = tracker.get_smart_money_activity()

        return {"smart_money": activity[:limit], "count": len(activity)}

    except Exception as e:
        return {"smart_money": [], "count": 0, "error": str(e)}


# Singleton scraper — reuse cache across requests
_scraper_instance = None

def _get_scraper(force_reload: bool = False):
    global _scraper_instance
    import importlib
    import services.arkham_scraper as arkham_scraper_module

    if force_reload:
        arkham_scraper_module = importlib.reload(arkham_scraper_module)
        _scraper_instance = None

    if _scraper_instance is None:
        _scraper_instance = arkham_scraper_module.ArkhamScraper()
    return _scraper_instance


def _search_wallets_from_holders_cache(scraper: Any, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    query_lower = (query or "").strip().lower()
    if not query_lower:
        return []
    query_variants, query_compact_variants = _search_query_variants(query_lower)

    holders_cache = getattr(scraper, "_cache", {}).get("holders_cache", {}) or {}
    seen_addresses: set[str] = set()
    matches: list[dict[str, Any]] = []

    for cache_key, holder_list in holders_cache.items():
        chain, contract = _parse_holders_cache_key(cache_key)
        if not chain or not isinstance(holder_list, list):
            continue

        for holder in holder_list:
            address = str(holder.get("address") or "").strip().lower()
            if not address or address in seen_addresses:
                continue

            identity = _resolve_address_identity(address, holder)
            holder_meta_tags = _extract_holder_tags(holder)
            holder_label = str(holder.get("arkham_label") or "").strip()
            holder_entity = str(holder.get("arkham_entity") or "").strip()
            holder_wallet_type = str(holder.get("wallet_type") or "").strip()
            holder_flags = [str(flag).strip() for flag in (holder.get("wallet_flags") or []) if str(flag).strip()]
            holder_tags = [str(tag).strip() for tag in (holder.get("wallet_tags") or []) if str(tag).strip()]
            if holder_meta_tags:
                if not holder_label:
                    holder_label = _best_wallet_label(holder_meta_tags, address)
                if not holder_entity:
                    holder_entity = next((str(tag.get("main_entity") or "").strip() for tag in holder_meta_tags if tag.get("main_entity")), "")
                if not holder_wallet_type:
                    holder_wallet_type = next((flag for flag in _wallet_flags(holder_meta_tags) if flag), "")
                holder_flags = _dedupe_keep_order(holder_flags + _wallet_flags(holder_meta_tags))
                holder_tags = _dedupe_keep_order(holder_tags + [str(tag.get("name") or "").strip() for tag in holder_meta_tags if tag.get("name")])
            safe_like = (
                holder_wallet_type.lower() == "safe"
                or any("safe" in flag.lower() for flag in holder_flags)
                or any("safe" in tag.lower() or "safeproxy" in tag.lower() for tag in holder_tags)
            )
            if safe_like and not holder_label:
                holder_label = "Gnosis Safe Proxy"
            if safe_like and not holder_entity:
                holder_entity = "Gnosis Safe"
            searchable_parts = [
                address,
                holder_label,
                holder_entity,
                holder_wallet_type,
                " ".join(holder_flags),
                " ".join(holder_tags),
                str(identity.get("label") or ""),
                str(identity.get("entity") or ""),
                " ".join(identity.get("tags") or []),
                " ".join(identity.get("flags") or []),
                str(holder.get("ens_domain_name") or ""),
            ]
            searchable_text = " | ".join(part for part in searchable_parts if part).lower()
            searchable_compact = _compact_search_text(searchable_text)
            if (
                not any(variant in searchable_text for variant in query_variants)
                and not any(variant and variant in searchable_compact for variant in query_compact_variants)
            ):
                continue

            seen_addresses.add(address)
            matches.append({
                "address": address,
                "label": holder_label or identity.get("label") or _truncate_addr(address),
                "entity": holder_entity or identity.get("entity") or "",
                "chain": chain,
                "wallet_type": holder_wallet_type or identity.get("wallet_type") or "",
                "flags": _dedupe_keep_order(holder_flags + list(identity.get("flags") or [])),
                "tags": _dedupe_keep_order(holder_tags + list(identity.get("tags") or [])),
                "balance_usd": None,
                "source": "holders_cache",
                "contract_address": contract,
            })
            if len(matches) >= limit:
                return matches

    return matches


@router.get("/search")
async def arkham_search(
    q: str = Query("", min_length=0, max_length=200, description="Recherche: nom d'entité, label de wallet, adresse, token"),
    chain: str = Query("ethereum", description="Blockchain pour lookup adresse"),
):
    """
    Recherche un wallet, une entité ou un token.
    
    Détecte automatiquement:
    - Adresses 0x... → lookup on-chain
    - Noms d'entités → Arkham DB + static DB
    - Symboles de tokens → CoinGecko + cache
    
    Recherche floue sur les labels et noms d'entités.
    """
    if not q or len(q) < 1:
        return {"entities": [], "wallets": [], "tokens": [], "total": 0}

    try:
        from services.arkham_scraper import ArkhamScraper, get_arkham_db

        scraper = _get_scraper()
        db = get_arkham_db()

        entity_results = []
        wallet_results = []
        token_results = []

        # ── 1) Detect address pattern (0x...) ──
        if q.startswith("0x") and len(q) >= 40:
            # Address lookup mode
            addr_result = scraper.lookup_address(q, chain)
            if addr_result:
                wallet_results.append({
                    "address": q,
                    "label": addr_result.get("label", ""),
                    "entity": addr_result.get("entity", ""),
                    "chain": chain,
                    "wallet_type": addr_result.get("wallet_type", ""),
                    "balance_usd": addr_result.get("balance_usd"),
                    "balance_eth": addr_result.get("balance_eth"),
                    "identified": addr_result.get("identified", False),
                })

        # ── 2) Search Arkham DB (entities + wallets) ──
        if not (q.startswith("0x") and len(q) >= 40):
            wallets = db.search_wallets(q)
            wallet_results.extend([
                {"address": w.get("address", ""), "label": w.get("label", ""),
                 "entity": w.get("entity", ""), "chain": w.get("chain", "ethereum"),
                 "wallet_type": w.get("wallet_type", ""), "balance_usd": w.get("balance_usd")}
                for w in wallets[:20]
            ])

            if len(wallet_results) < 20:
                cached_wallets = _search_wallets_from_holders_cache(scraper, q, limit=20)
                existing_wallet_keys = {
                    (str(wallet.get("address") or "").lower(), str(wallet.get("chain") or "").lower())
                    for wallet in wallet_results
                }
                for wallet in cached_wallets:
                    wallet_key = (
                        str(wallet.get("address") or "").lower(),
                        str(wallet.get("chain") or "").lower(),
                    )
                    if wallet_key in existing_wallet_keys:
                        continue
                    wallet_results.append(wallet)
                    existing_wallet_keys.add(wallet_key)
                    if len(wallet_results) >= 20:
                        break

            if len(wallet_results) < 20:
                snapshot_wallets = _search_wallets_from_scrapling_snapshots(q, limit=20)
                existing_wallet_keys = {
                    (str(wallet.get("address") or "").lower(), str(wallet.get("chain") or "").lower())
                    for wallet in wallet_results
                }
                for wallet in snapshot_wallets:
                    wallet_key = (
                        str(wallet.get("address") or "").lower(),
                        str(wallet.get("chain") or "").lower(),
                    )
                    if wallet_key in existing_wallet_keys:
                        continue
                    wallet_results.append(wallet)
                    existing_wallet_keys.add(wallet_key)
                    if len(wallet_results) >= 20:
                        break

            # Search entities
            for slug, info in db.entities_by_name.items():
                if q.lower() in slug.lower() or q.lower() in info.get("name", "").lower():
                    entity_results.append({"slug": slug, **info})

            existing_entity_slugs = {str(entity.get("slug") or "").lower() for entity in entity_results}
            for entity in _search_entities_from_scrapling_snapshots(q, limit=8):
                slug = str(entity.get("slug") or "").lower()
                if slug and slug not in existing_entity_slugs:
                    entity_results.append(entity)
                    existing_entity_slugs.add(slug)

            # Search tokens in DB
            try:
                token_matches = db.search_tokens(q)
                for t in token_matches[:10]:
                    token_results.append({
                        "id": t.get("id", ""),
                        "symbol": t.get("symbol", ""),
                        "name": t.get("name", ""),
                        "contract_address": t.get("contract_address", ""),
                        "market_cap_usd": t.get("market_cap_usd"),
                        "price_usd": t.get("price_usd"),
                        "source": "cache",
                    })
            except Exception:
                pass

            existing_token_ids = {
                str(token.get("id") or token.get("contract_address") or "").lower()
                for token in token_results
            }
            for token in _search_tokens_from_scrapling_snapshots(q, limit=8):
                token_key = str(token.get("id") or token.get("contract_address") or "").lower()
                if token_key and token_key not in existing_token_ids:
                    token_results.append(token)
                    existing_token_ids.add(token_key)

        # ── 3) Free static DB search (no API key needed) ──
        if len(entity_results) < 3:
            try:
                free_results = await asyncio.to_thread(scraper.search_entity_free, q)
                for ent in (free_results or [])[:5]:
                    existing_slugs = {e.get("slug") for e in entity_results}
                    slug = ent.get("slug", ent.get("name", "").lower().replace(" ", "-"))
                    if slug not in existing_slugs:
                        entity_results.append({
                            "slug": slug,
                            "name": ent.get("name", ""),
                            "type": ent.get("type", ""),
                            "category": ent.get("category", ""),
                            "balance_usd": ent.get("balance_usd"),
                            "wallet_count": ent.get("wallet_count"),
                            "chains": ent.get("chains", []),
                            "source": "free_db",
                        })
            except Exception:
                pass

        # ── 4) CoinGecko token search (free, no key) ──
        if len(token_results) < 3:
            try:
                cg_results = await scraper.search_coingecko(q)
                for coin in (cg_results or [])[:8]:
                    existing_ids = {t.get("id") for t in token_results}
                    if coin.get("id") not in existing_ids:
                        token_results.append({
                            "id": coin.get("id", ""),
                            "symbol": coin.get("symbol", "").upper(),
                            "name": coin.get("name", ""),
                            "market_cap_rank": coin.get("market_cap_rank"),
                            "thumb": coin.get("thumb", ""),
                            "source": "coingecko",
                        })
            except Exception:
                pass

        # ── 5) Live scraper search only when local search is really empty ──
        if len(entity_results) < 3 and (len(entity_results) + len(wallet_results) + len(token_results) == 0):
            try:
                live = await asyncio.to_thread(scraper.search_entity, q)
                for ent in (live or [])[:5]:
                    existing_slugs = {e.get("slug") for e in entity_results}
                    slug = ent.get("slug", ent.get("name", "").lower().replace(" ", "-"))
                    if slug not in existing_slugs:
                        entity_results.append({
                            "slug": slug,
                            "name": ent.get("name", ""),
                            "type": ent.get("type", ""),
                            "source": "live_search",
                        })
            except Exception:
                pass

        return {
            "query": q,
            "wallets": wallet_results[:20],
            "wallets_count": len(wallet_results),
            "entities": entity_results[:10],
            "entities_count": len(entity_results),
            "tokens": token_results[:10],
            "tokens_count": len(token_results),
            "total": len(entity_results) + len(wallet_results) + len(token_results),
        }

    except Exception as e:
        return {"query": q, "wallets": [], "entities": [], "tokens": [], "error": str(e)}


# =========================================================
# ENTITY DÉTAILS
# =========================================================

@router.get("/entity/{entity_slug}")
async def arkham_entity(
    entity_slug: str,
    include_wallets: bool = Query(True, description="Inclure la liste des wallets"),
):
    """
    Détails d'une entité Arkham.
    Info, wallets identifiés, flows récents.
    """
    result = {
        "entity": None,
        "profile": None,
        "wallets": [],
        "flow": None,
        "wallets_count": 0,
        "intelligence": None,
        "snapshot_status": "local",
        "snapshot_retry_after_seconds": None,
    }
    entity_snapshot = None

    try:
        from services.arkham_scraper import get_arkham_db, get_entity_profile
        scraper = _get_scraper()
        db = get_arkham_db()
        entity = db.get_entity_info(entity_slug)
        wallets = []
        profile = get_entity_profile(entity_slug, entity)

        if entity and include_wallets:
            wallets = db.get_entity_wallets(entity_slug)

        # Fallback: static/live search results can exist even when the entity
        # is not yet present in the persisted Arkham DB cache.
        if not entity:
            query = entity_slug.replace("-", " ").strip()
            free_matches = await asyncio.to_thread(scraper.search_entity_free, query)
            entity = next(
                (
                    match for match in free_matches
                    if (match.get("slug") or "").lower() == entity_slug.lower()
                    or (match.get("name") or "").lower() == query.lower()
                ),
                None,
            )

        if not entity:
            query = entity_slug.replace("-", " ").strip()
            live_matches = await asyncio.to_thread(scraper.search_entity, query)
            entity = next(
                (
                    match for match in live_matches
                    if (match.get("slug") or "").lower() == entity_slug.lower()
                    or (match.get("name") or "").lower() == query.lower()
                ),
                None,
            )

        # Secondary fallback: surface wallet labels already known in the local DB.
        if include_wallets and not wallets:
            search_term = entity.get("name", entity_slug) if entity else entity_slug
            wallets = db.search_wallets(search_term)

        try:
            # Do not let opportunistic cache warming block the entity page for
            # empty or newly added profiles. We can still render the profile
            # immediately and progressively improve coverage on later visits.
            profile = await asyncio.wait_for(
                _warm_entity_observations(scraper, entity_slug, entity),
                timeout=4.0,
            )
        except asyncio.TimeoutError:
            profile = profile or {}
        intelligence = await _build_entity_intelligence(scraper, db, entity_slug, entity, wallets)

        try:
            from services.scrapling_probe import get_scrapling_probe_service

            probe_service = get_scrapling_probe_service()
            if probe_service.available:
                try:
                    entity_snapshot = await asyncio.wait_for(
                        asyncio.to_thread(
                            probe_service.get_entity_snapshot,
                            entity_slug,
                            headless=True,
                            real_chrome=False,
                            timeout_ms=30000,
                            max_xhr=60,
                            persist=True,
                        ),
                        timeout=8.0,
                    )
                    if entity_snapshot:
                        result["snapshot_status"] = "live"
                except asyncio.TimeoutError:
                    # The underlying thread keeps warming the live snapshot in the
                    # background. Return the local entity view immediately and let
                    # the frontend refresh after the snapshot has been persisted.
                    entity_snapshot = None
                    result["snapshot_status"] = "warming"
                    result["snapshot_retry_after_seconds"] = 25
                except Exception:
                    entity_snapshot = None
            else:
                result["snapshot_status"] = "disabled"
        except Exception:
            entity_snapshot = None

        if entity_snapshot:
            snapshot_profile = dict(entity_snapshot.get("profile") or {})
            snapshot_entity = dict(entity_snapshot.get("entity") or {})
            snapshot_summary = dict(entity_snapshot.get("summary") or {})
            snapshot_coverage = dict(entity_snapshot.get("coverage") or {})
            snapshot_surfaces = dict(entity_snapshot.get("surfaces") or {})
            snapshot_total_value_usd = (
                _safe_float(snapshot_summary.get("total_balance_usd"))
                or _safe_float(entity_snapshot.get("estimated_total_value_usd"))
                or _sum_estimated_value_usd(entity_snapshot.get("holdings"))
            )
            snapshot_chains = [str(item.get("chain") or "").strip().lower() for item in entity_snapshot.get("chains") or [] if item.get("chain")]
            snapshot_symbols = [str(item.get("symbol") or "").upper() for item in entity_snapshot.get("holdings") or [] if item.get("symbol")]

            intelligence = dict(intelligence or {})
            local_coverage = dict(intelligence.get("coverage") or {})
            intelligence["coverage"] = {
                "snapshots_scanned": max(_safe_int(local_coverage.get("snapshots_scanned")) or 0, _safe_int(snapshot_coverage.get("snapshots_scanned")) or 0),
                "holder_rows_scanned": max(_safe_int(local_coverage.get("holder_rows_scanned")) or 0, _safe_int(snapshot_coverage.get("holder_rows_scanned")) or 0),
                "observed_wallets": max(_safe_int(local_coverage.get("observed_wallets")) or 0, _safe_int(snapshot_coverage.get("observed_wallets")) or 0),
                "observed_tokens": max(_safe_int(local_coverage.get("observed_tokens")) or 0, _safe_int(snapshot_coverage.get("observed_tokens")) or 0),
                "recent_activity_count": max(_safe_int(local_coverage.get("recent_activity_count")) or 0, _safe_int(snapshot_coverage.get("recent_activity_count")) or 0),
                "rpc_verified_tokens": _safe_int(local_coverage.get("rpc_verified_tokens")) or 0,
                "coverage_note": snapshot_coverage.get("coverage_note") or local_coverage.get("coverage_note"),
                "source_trace": list(local_coverage.get("source_trace") or []),
            }
            intelligence["coverage"]["source_trace"].append({
                "id": "scrapling_live_snapshot",
                "kind": "arkham_surface",
                "source": "scrapling_arkham_page_probe",
                "count": 1,
                "confidence": "medium",
                "note": "Live Arkham page snapshot merged without overwriting local on-chain observations.",
            })
            intelligence["chains"] = _merge_chain_rows(entity_snapshot.get("chains"), intelligence.get("chains"))
            intelligence["top_tags"] = _merge_tag_rows(entity_snapshot.get("top_tags"), intelligence.get("top_tags"))
            intelligence["observed_holdings"] = _merge_keyed_rows(
                entity_snapshot.get("holdings"),
                intelligence.get("observed_holdings"),
                key_fields=["chain", "contract_address", "asset_id", "symbol"],
                limit=48,
            )
            intelligence["wallets"] = _merge_keyed_rows(
                entity_snapshot.get("wallets"),
                intelligence.get("wallets"),
                key_fields=["address"],
                limit=60,
            )
            intelligence["recent_activity"] = _merge_keyed_rows(
                entity_snapshot.get("recent_activity"),
                intelligence.get("recent_activity"),
                key_fields=["tx_hash"],
                limit=80,
            )
            intelligence["counterparties"] = _merge_keyed_rows(
                entity_snapshot.get("counterparties"),
                intelligence.get("counterparties"),
                key_fields=["address", "label"],
                limit=30,
            )
            merged_surfaces = dict(intelligence.get("surfaces") or {})
            for surface_key in ("balances_history", "history_by_chain", "token_balance_surface", "network_usage", "exchange_usage", "role_clusters", "loan_protocols"):
                if snapshot_surfaces.get(surface_key):
                    merged_surfaces[surface_key] = snapshot_surfaces.get(surface_key)
            intelligence["surfaces"] = merged_surfaces
            if snapshot_total_value_usd is not None:
                intelligence["estimated_total_value_usd"] = snapshot_total_value_usd
            intelligence["source_trace"] = intelligence["coverage"]["source_trace"]

            profile = dict(profile or {})
            if snapshot_profile.get("website"):
                profile["website"] = snapshot_profile.get("website")
            if snapshot_profile.get("socials"):
                profile["socials"] = {**dict(profile.get("socials") or {}), **dict(snapshot_profile.get("socials") or {})}
            if snapshot_profile.get("crunchbase"):
                profile["crunchbase"] = snapshot_profile.get("crunchbase")
            if snapshot_profile.get("badges"):
                profile["badges"] = _dedupe_keep_order(list(profile.get("badges") or []) + list(snapshot_profile.get("badges") or []))
            if snapshot_profile.get("tags"):
                profile["tags"] = _dedupe_keep_order(list(profile.get("tags") or []) + list(snapshot_profile.get("tags") or []))
            if snapshot_chains:
                profile["coverage_chains"] = _dedupe_keep_order(list(profile.get("coverage_chains") or []) + snapshot_chains)[:10]
            if snapshot_symbols:
                profile["coverage_tokens"] = _dedupe_keep_order(list(profile.get("coverage_tokens") or []) + snapshot_symbols)[:16]

            if entity:
                entity = dict(entity)
            else:
                entity = {
                    "slug": entity_slug,
                    "name": snapshot_entity.get("name") or snapshot_profile.get("name") or entity_slug,
                }

            raw_snapshot_type = str(snapshot_entity.get("type") or snapshot_profile.get("type") or "").strip().lower()
            if not entity.get("type"):
                if raw_snapshot_type == "cex":
                    entity["type"] = "exchange"
                elif raw_snapshot_type == "dex":
                    entity["type"] = "protocol"
            elif raw_snapshot_type:
                entity["type"] = raw_snapshot_type
            if raw_snapshot_type and not entity.get("category"):
                entity["category"] = raw_snapshot_type
            if snapshot_total_value_usd is not None:
                entity["balance_usd"] = snapshot_total_value_usd
            if snapshot_chains:
                entity["chains"] = _dedupe_keep_order(list(entity.get("chains") or []) + snapshot_chains)
            if snapshot_entity.get("website"):
                entity["website"] = snapshot_entity.get("website")
            if snapshot_entity.get("socials"):
                entity["socials"] = {**dict(entity.get("socials") or {}), **dict(snapshot_entity.get("socials") or {})}
            if snapshot_profile.get("badges"):
                entity["badges"] = _dedupe_keep_order(list(entity.get("badges") or []) + list(snapshot_profile.get("badges") or []))
            if snapshot_profile.get("tags"):
                entity["tags"] = _dedupe_keep_order(list(entity.get("tags") or []) + list(snapshot_profile.get("tags") or []))
            if snapshot_entity.get("top_address"):
                entity["top_address"] = snapshot_entity.get("top_address")
            if not entity.get("description") and snapshot_profile.get("note"):
                entity["description"] = snapshot_profile.get("note")

        merged_wallets = _merge_wallet_sources(wallets, intelligence.get("wallets", []))

        if entity:
            entity = dict(entity)
            entity["wallet_count"] = max(
                _safe_int(entity.get("wallet_count")) or 0,
                _safe_int(intelligence.get("coverage", {}).get("observed_wallets")) or 0,
            ) or None
            if not entity.get("balance_usd") and intelligence.get("estimated_total_value_usd") is not None:
                entity["balance_usd"] = intelligence["estimated_total_value_usd"]
            if intelligence.get("chains"):
                observed_chains = [item.get("chain") for item in intelligence["chains"] if item.get("chain")]
                if observed_chains:
                    entity["chains"] = observed_chains
            if not entity.get("chains") and profile.get("coverage_chains"):
                entity["chains"] = profile["coverage_chains"]
            if profile.get("badges"):
                entity["badges"] = _dedupe_keep_order(list(entity.get("badges") or []) + list(profile.get("badges") or []))
            if profile.get("socials"):
                entity["socials"] = profile.get("socials")
            if profile.get("website"):
                entity["website"] = profile.get("website")
            if profile.get("description"):
                entity["description"] = profile.get("description")

        result["entity"] = entity
        result["profile"] = profile or None
        result["intelligence"] = intelligence
        if include_wallets:
            result["wallets"] = merged_wallets[:50]
            result["wallets_count"] = len(merged_wallets)
    except Exception as e:
        result["entity_error"] = str(e)

    try:
        from services.arkham_tracker import get_arkham_tracker
        tracker = get_arkham_tracker()
        flow_data = tracker.entity_flows.get(entity_slug.lower())
        result["flow"] = flow_data.get_stats() if flow_data else None
    except Exception:
        pass

    if not result.get("flow") and entity_snapshot and entity_snapshot.get("flow_summary"):
        result["flow"] = entity_snapshot.get("flow_summary")

    return result


# =========================================================
# TOKEN DÉTAILS — CoinGecko + Etherscan + Arkham
# =========================================================

@router.get("/token/{symbol}")
async def arkham_token(
    symbol: str,
    chain: str = Query("ethereum", description="Blockchain: ethereum, bsc, arbitrum, polygon, solana, bitcoin"),
    include_holders: bool = Query(True, description="Inclure les top holders"),
    include_perp: bool = Query(True, description="Inclure données perpétuelles (funding, OI, CVD)"),
    include_flows: bool = Query(True, description="Inclure Arkham entity flows"),
):
    """
    Détails d'un token avec données multi-sources enrichies.
    
    Stratégie:
    1. Détecter chaîne native (BTC, SOL, ETH...)
    2. Cache local Arkham (GRATUIT)
    3. CoinGecko pour prix, market cap, supply (GRATUIT, 30 req/min)
    4. Données perpétuelles Hyperliquid + Binance (funding, OI, CVD)
    5. Arkham entity flows (si DB disponible)
    6. Etherscan pour top holders (GRATUIT si clé API)
    
    Retourne un dict complet style Arkham Intelligence:
    - Prix, market cap, supply, volume
    - Funding rates, OI, CVD (perp data)
    - Entity flows (smart money tracking)
    - Holders avec labels Arkham
    """
    try:
        scraper = _get_scraper()
        browser_snapshot = None
        
        # 1. Données de base du token
        result = await asyncio.to_thread(
            scraper.get_token_detail, symbol, chain
        )

        if not result or result.get("error"):
            return result or {"error": "No data", "symbol": symbol}

        # 2. Enrichir avec données perpétuelles
        if include_perp:
            result = scraper.enrich_with_perp_data(result)

        # 3. Enrichissement browser-native via Scrapling (Arkham SPA)
        if include_flows:
            try:
                from services.scrapling_probe import get_scrapling_probe_service

                probe_service = get_scrapling_probe_service()
                if probe_service.available:
                    browser_snapshot = await asyncio.wait_for(
                        asyncio.to_thread(
                            probe_service.get_token_snapshot,
                            symbol,
                            headless=True,
                            real_chrome=False,
                            timeout_ms=25000,
                            max_xhr=40,
                            persist=True,
                        ),
                        timeout=35.0,
                    )
            except asyncio.TimeoutError:
                browser_snapshot = None
            except Exception:
                browser_snapshot = None

        if browser_snapshot:
            addresses = browser_snapshot.get("addresses") or {}
            snapshot_market = browser_snapshot.get("market") or {}
            if not result.get("contract_address") and addresses.get(chain):
                result["contract_address"] = addresses.get(chain)
            if not result.get("price_usd") and snapshot_market.get("price") is not None:
                result["price_usd"] = snapshot_market.get("price")
            if not result.get("market_cap_usd") and snapshot_market.get("marketCap") is not None:
                result["market_cap_usd"] = snapshot_market.get("marketCap")
            if not result.get("volume_24h") and snapshot_market.get("totalVolume") is not None:
                result["volume_24h"] = snapshot_market.get("totalVolume")
            if not result.get("fdv") and snapshot_market.get("fullyDilutedValue") is not None:
                result["fdv"] = snapshot_market.get("fullyDilutedValue")
            if not result.get("total_supply") and snapshot_market.get("totalSupply") is not None:
                result["total_supply"] = snapshot_market.get("totalSupply")
            if not result.get("circulating_supply") and snapshot_market.get("circulatingSupply") is not None:
                result["circulating_supply"] = snapshot_market.get("circulatingSupply")
            if not result.get("ath") and snapshot_market.get("allTimeHigh") is not None:
                result["ath"] = snapshot_market.get("allTimeHigh")
            if not result.get("atl") and snapshot_market.get("allTimeLow") is not None:
                result["atl"] = snapshot_market.get("allTimeLow")
            result["arkham_addresses"] = addresses
            result["arkham_price_history"] = browser_snapshot.get("price_history") or []
            result["arkham_token_volume"] = browser_snapshot.get("token_volume") or []

        # 4. Enrichir avec Arkham flows
        if include_flows:
            if browser_snapshot and browser_snapshot.get("arkham_flows"):
                result["arkham_flows"] = browser_snapshot.get("arkham_flows")
            else:
                result["arkham_flows"] = scraper.get_token_arkham_flows(symbol)

        # 5. Holders (seulement si contrat ERC-20)
        if include_holders:
            contract = result.get("contract_address", "")
            if contract:
                try:
                    holders = await asyncio.to_thread(
                        scraper._fetch_token_holders, contract, chain
                    )
                    result["holders"] = holders[:25]
                    result["holders_count"] = len(holders)
                    
                    # Identifier via Arkham DB
                    try:
                        from services.arkham_scraper import get_arkham_db
                        db = get_arkham_db()
                        for h in holders[:25]:
                            addr = h.get("address", "")
                            if addr.startswith("0x"):
                                label = db.lookup_wallet(addr, chain)
                                if label:
                                    h["arkham_label"] = label.get("label")
                                    h["arkham_entity"] = label.get("entity")
                                    h["wallet_type"] = h.get("wallet_type") or label.get("wallet_type")
                                else:
                                    holder_info = {
                                        "name": h.get("ens_domain_name"),
                                        "metadata": {"tags": h.get("metadata_tags") or []},
                                        "is_contract": h.get("is_contract", False),
                                    }
                                    identity = _resolve_address_identity(addr, holder_info)
                                    if identity.get("label"):
                                        h["arkham_label"] = identity.get("label")
                                    if identity.get("entity"):
                                        h["arkham_entity"] = identity.get("entity")
                                    if identity.get("wallet_type"):
                                        h["wallet_type"] = h.get("wallet_type") or identity.get("wallet_type")
                                    if identity.get("tags"):
                                        h["wallet_tags"] = _dedupe_keep_order(
                                            list(h.get("wallet_tags") or []) + list(identity.get("tags") or [])
                                        )
                                    if identity.get("flags"):
                                        h["wallet_flags"] = _dedupe_keep_order(
                                            list(h.get("wallet_flags") or []) + list(identity.get("flags") or [])
                                        )
                                    if identity.get("label") and not h.get("label_source"):
                                        h["label_source"] = "blockscout_tags"
                    except Exception:
                        pass
                except Exception:
                    pass
            elif result.get("is_native"):
                # Pour les natives coins, holders = top wallets connues
                result["holders"] = []
                result["holders_count"] = 0
                result["holders_note"] = "Native coin — holders via blockchain explorer, not ERC-20"

        return result

    except Exception as e:
        return {"error": str(e), "symbol": symbol}


# =========================================================
# TOKEN TRANSFERS — ERC-20 Transfer events récents
# =========================================================

@router.get("/token/{symbol}/transfers")
async def arkham_token_transfers(
    symbol: str,
    chain: str = Query("ethereum", description="Blockchain"),
    page: int = Query(1, ge=1, le=10),
    limit: int = Query(50, ge=1, le=100),
):
    """
    Transferts ERC-20 récents pour un token.
    Utilise Blockscout (GRATUIT, no key) puis Etherscan fallback.
    """
    try:
        scraper = _get_scraper(force_reload=True)
        detail = await asyncio.to_thread(scraper.get_token_detail, symbol, chain)
        contract = detail.get("contract_address", "")
        browser_snapshot = None
        
        # For native coins, no transfers via ERC-20 endpoint
        if detail.get("is_native"):
            return {
                "transfers": [],
                "count": 0,
                "note": f"{symbol.upper()} is a native coin — transfers require blockchain-specific APIs",
            }
        
        if not contract:
            return {"transfers": [], "error": f"No contract address found for {symbol} on {chain}"}

        try:
            from services.scrapling_probe import get_scrapling_probe_service

            probe_service = get_scrapling_probe_service()
            if probe_service.available:
                browser_snapshot = await asyncio.wait_for(
                    asyncio.to_thread(
                        probe_service.get_token_snapshot,
                        symbol,
                        headless=True,
                        real_chrome=False,
                        timeout_ms=25000,
                        max_xhr=40,
                        persist=True,
                    ),
                    timeout=35.0,
                )
        except asyncio.TimeoutError:
            browser_snapshot = None
        except Exception:
            browser_snapshot = None

        if browser_snapshot and browser_snapshot.get("transfers"):
            all_transfers = list(browser_snapshot.get("transfers") or [])
            start_index = max((page - 1) * limit, 0)
            end_index = start_index + limit
            return {
                "transfers": all_transfers[start_index:end_index],
                "count": browser_snapshot.get("transfers_count") or len(all_transfers),
                "contract": contract,
                "token": symbol,
                "source": "arkham_scrapling",
            }

        # Use the new Blockscout-first method
        transfers = await asyncio.to_thread(
            scraper._fetch_token_transfers, contract, chain, page, limit
        )
        if not transfers:
            try:
                import json
                import urllib.request
                from services.arkham_scraper import BLOCKSCOUT_API_URLS

                bs_url = BLOCKSCOUT_API_URLS.get(chain, BLOCKSCOUT_API_URLS.get("ethereum"))
                if bs_url and "graphiql" not in bs_url:
                    req = urllib.request.Request(
                        f"{bs_url}/tokens/{contract}/transfers",
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        raw = json.loads(resp.read().decode())
                    items = raw.get("items", [])
                    for item in items[: max(limit, 1)]:
                        from_addr = item.get("from", {})
                        to_addr = item.get("to", {})
                        token_meta = item.get("token", {})
                        transfers.append({
                            "tx_hash": item.get("transaction_hash", ""),
                            "block_number": item.get("block_number"),
                            "timestamp": item.get("timestamp", ""),
                            "from": from_addr.get("hash", ""),
                            "to": to_addr.get("hash", ""),
                            "value": item.get("total", {}).get("value", "0"),
                            "token_name": token_meta.get("name", detail.get("name") or symbol),
                            "token_symbol": token_meta.get("symbol", detail.get("symbol") or symbol.upper()),
                            "token_decimal": str(token_meta.get("decimals", detail.get("decimals") or 18)),
                            "method": item.get("method", ""),
                            "transfer_type": item.get("type", ""),
                            "from_is_contract": from_addr.get("is_contract", False),
                            "to_is_contract": to_addr.get("is_contract", False),
                            "from_name": from_addr.get("name"),
                            "to_name": to_addr.get("name"),
                            "from_tags": [t.get("name", "") for t in ((from_addr.get("metadata") or {}).get("tags", []))],
                            "to_tags": [t.get("name", "") for t in ((to_addr.get("metadata") or {}).get("tags", []))],
                            "from_metadata_tags": (from_addr.get("metadata") or {}).get("tags", []),
                            "to_metadata_tags": (to_addr.get("metadata") or {}).get("tags", []),
                        })
            except Exception:
                pass
        transfers = transfers[:limit]
        price_usd = _safe_float(detail.get("price_usd"))
        
        # Enrich with Arkham DB labels
        try:
            from services.arkham_scraper import get_arkham_db
            db = get_arkham_db()
            for tx in transfers:
                token_decimals = _safe_int(tx.get("token_decimal")) or _safe_int(detail.get("decimals")) or 18
                tx["token_decimal"] = str(token_decimals)
                if not tx.get("token_symbol"):
                    tx["token_symbol"] = detail.get("symbol") or symbol.upper()
                if not tx.get("token_name"):
                    tx["token_name"] = detail.get("name") or symbol
                human_amount = _human_balance(tx.get("value"), token_decimals)
                tx["human_value"] = human_amount
                tx["value_usd"] = round(human_amount * price_usd, 2) if human_amount is not None and price_usd is not None else None
                for addr_field in ["from", "to"]:
                    addr = tx.get(addr_field, "")
                    if addr.startswith("0x"):
                        label = db.lookup_wallet(addr, chain)
                        if label:
                            tx[f"{addr_field}_label"] = label.get("label")
                            tx[f"{addr_field}_entity"] = label.get("entity")
                            tx[f"{addr_field}_wallet_type"] = label.get("wallet_type")
                        else:
                            party_info = {
                                "name": tx.get(f"{addr_field}_name"),
                                "metadata": {"tags": tx.get(f"{addr_field}_metadata_tags") or []},
                                "is_contract": tx.get(f"{addr_field}_is_contract", False),
                            }
                            identity = _resolve_address_identity(addr, party_info)
                            tx[f"{addr_field}_label"] = identity.get("label")
                            tx[f"{addr_field}_entity"] = identity.get("entity")
                            tx[f"{addr_field}_wallet_type"] = identity.get("wallet_type")
                            tx[f"{addr_field}_tags"] = identity.get("tags") or []
        except Exception:
            pass

        return {
            "transfers": transfers,
            "count": len(transfers),
            "contract": contract,
            "token": symbol,
            "source": "blockscout" if transfers else "none",
        }

    except Exception as e:
        return {"transfers": [], "error": str(e)}


# =========================================================
# TOKEN HOLDERS — Top holders d'un token
# =========================================================

@router.get("/token/{symbol}/holders")
async def arkham_token_holders(
    symbol: str,
    chain: str = Query("ethereum", description="Blockchain"),
):
    """
    Top holders d'un token avec identification Arkham.
    """
    try:
        scraper = _get_scraper()
        # Obtenir les détails du token pour avoir le contract_address
        detail = await asyncio.to_thread(scraper.get_token_detail, symbol, chain)
        contract = detail.get("contract_address", "")

        # Si c'est une native coin, pas de holders ERC-20
        if detail.get("is_native"):
            return {
                "holders": [],
                "count": 0,
                "note": f"{symbol.upper()} is a native coin on {chain} — holders data requires blockchain-specific APIs",
            }

        if not contract:
            # Si pas de contrat, essayer de le récupérer depuis CoinGecko platforms
            try:
                import urllib.request
                import urllib.parse
                cg_id = detail.get("id", symbol.lower())
                cg_url = f"https://api.coingecko.com/api/v3/coins/{cg_id}"
                req = urllib.request.Request(cg_url, headers={"User-Agent": "Hermes/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    cg_data = json.loads(resp.read().decode())
                    platforms = cg_data.get("platforms", {})
                    chain_map = {
                        "ethereum": "ethereum",
                        "bsc": "binance-smart-chain",
                        "arbitrum": "arbitrum-one",
                        "polygon": "polygon-pos",
                    }
                    cg_chain = chain_map.get(chain, chain)
                    contract = platforms.get(cg_chain, "")
            except Exception:
                pass

        if not contract:
            return {"holders": [], "error": f"No contract address found for {symbol} on {chain}"}

        holders = await asyncio.to_thread(scraper._fetch_token_holders, contract, chain)

        # Calc total supply for percentage
        total_supply = detail.get("total_supply") or detail.get("circulating_supply")
        decimals = detail.get("decimals", 18)
        if total_supply and decimals:
            for h in holders:
                try:
                    bal = float(h.get("balance", 0))
                    h["percentage"] = round((bal / (total_supply * (10 ** decimals))) * 100, 6)
                except (ValueError, TypeError, ZeroDivisionError):
                    h["percentage"] = None

        holders_preview = holders[:25]
        price_usd = _safe_float(detail.get("price_usd"))

        db = None
        try:
            from services.arkham_scraper import get_arkham_db
            db = get_arkham_db()
        except Exception:
            db = None

        profile_jobs: list[tuple[dict[str, Any], Any]] = []
        for holder in holders_preview:
            address = str(holder.get("address") or "")
            if address.startswith("0x") and chain in EVM_CHAINS:
                profile_jobs.append((holder, asyncio.to_thread(_fetch_blockscout_wallet_profile, chain, address)))

        profiles: list[Any] = []
        if profile_jobs:
            profiles = await asyncio.gather(*(job for _, job in profile_jobs), return_exceptions=True)

        profile_by_address: dict[str, dict[str, Any]] = {}
        for (holder, _), profile in zip(profile_jobs, profiles):
            if isinstance(profile, Exception) or not isinstance(profile, dict):
                continue
            profile_by_address[str(holder.get("address") or "").lower()] = profile

        for h in holders_preview:
            address = str(h.get("address") or "")
            address_lower = address.lower()
            profile = profile_by_address.get(address_lower)
            raw_balance = h.get("balance")
            human_balance = _human_balance(raw_balance, decimals or 18)
            h["human_balance"] = human_balance
            h["value_usd"] = round(human_balance * price_usd, 2) if human_balance is not None and price_usd is not None else None

            label = db.lookup_wallet(address, chain) if db and address.startswith("0x") else None
            has_db_identity = bool(
                isinstance(label, dict)
                and any(label.get(key) for key in ["label", "entity", "wallet_type"])
            )
            if has_db_identity:
                h["arkham_label"] = label.get("label")
                h["arkham_entity"] = label.get("entity")
                h["wallet_type"] = label.get("wallet_type")
                h["label_source"] = "arkham_db"
            elif profile:
                h["arkham_label"] = profile.get("label")
                h["arkham_entity"] = profile.get("entity")
                h["wallet_type"] = profile.get("wallet_type")
                h["wallet_flags"] = profile.get("flags") or []
                h["wallet_tags"] = profile.get("tags") or []
                h["fresh_wallet_candidate"] = profile.get("fresh_wallet_candidate")
                h["fresh_wallet_note"] = profile.get("fresh_wallet_note")
                h["activity_profile"] = {
                    "transactions_count": profile.get("transactions_count"),
                    "token_transfers_count": profile.get("token_transfers_count"),
                    "activity_bucket": profile.get("activity_bucket"),
                }
                h["label_source"] = "blockscout"

        return {
            "holders": holders_preview,
            "count": len(holders),
            "contract": contract,
            "token": symbol,
        }

    except Exception as e:
        return {"holders": [], "error": str(e)}


# =========================================================
# LOOKUP ADRESSE
# =========================================================

@router.get("/lookup/{address}")
async def arkham_lookup(
    address: str,
    chain: str = Query("ethereum", description="Blockchain: ethereum, bitcoin, solana, bsc, arbitrum, polygon"),
):
    """
    Lookup une adresse on-chain dans la DB Arkham.
    Retourne le label, l'entité, et le type de wallet si identifié.
    """
    try:
        from services.arkham_scraper import get_arkham_db

        db = get_arkham_db()
        lookup_result = db.lookup_wallet(address, chain)

        # Si pas dans la DB, essayer le scraper pour enrichir
        if not lookup_result:
            try:
                scraper = _get_scraper()
                blockchain_data = await asyncio.to_thread(
                    scraper._fetch_blockchain_data, address, chain
                )
                if blockchain_data and not blockchain_data.get("error"):
                    return {
                        "address": address,
                        "chain": chain,
                        "identified": False,
                        "blockchain_data": blockchain_data,
                        "note": "Address not in Arkham DB, showing raw blockchain data",
                    }
            except Exception:
                pass

        return {
            "address": address,
            "chain": chain,
            "identified": lookup_result is not None,
            "data": lookup_result,
        }

    except Exception as e:
        return {"address": address, "chain": chain, "identified": False, "error": str(e)}


# =========================================================
# DÉCLENCHEURS DE SCRAPE
# =========================================================

@router.post("/scrape/full")
async def trigger_full_scrape():
    """
    Déclenche un full scrape Arkham (long, ~30-60 min).
    Scrape TOUTES les entités, wallets, tokens, flows.
    Tourne en background.
    """
    try:
        from services.arkham_scraper import ArkhamScraper

        scraper = _get_scraper()
        if not scraper._firecrawl_available:
            return {"status": "error", "message": "FIRECRAWL_API_KEY not configured or no credits remaining"}

        async def _run_full_scrape():
            await scraper.get_exchange_wallets()

        asyncio.create_task(_run_full_scrape())

        return {
            "status": "started",
            "message": "Full scrape started in background. Estimated duration: 30-60 minutes.",
            "check_status": "/api/arkham/status",
            "credits_remaining": scraper._get_credits_remaining(),
        }

    except Exception as e:
        return {"status": "error", "message": f"Failed to start: {e}"}


@router.post("/scrape/delta")
async def trigger_delta_scan():
    """
    Déclenche un delta scan (quick, ~5-10 min).
    Ne scrape que les nouveautés depuis le dernier scrape.
    Tourne en background.
    """
    try:
        from services.arkham_scraper import ArkhamScraper

        scraper = _get_scraper()
        if not scraper._firecrawl_available:
            return {"status": "error", "message": "FIRECRAWL_API_KEY not configured or no credits remaining"}

        async def _run_delta_scan():
            # Delta scan = just refresh expired cache entries
            import time
            entities = scraper._cache.get("entities", {})
            for slug, data in entities.items():
                age = time.time() - data.get("scraped_at", 0)
                if age > scraper.CACHE_TTL:
                    await scraper._firecrawl_get_entity_addresses(slug)

        asyncio.create_task(_run_delta_scan())

        return {
            "status": "started",
            "message": "Delta scan started in background. Refreshing expired cache entries.",
            "check_status": "/api/arkham/status",
            "credits_remaining": scraper._get_credits_remaining(),
        }

    except Exception as e:
        return {"status": "error", "message": f"Failed to start: {e}"}


# =========================================================
# DB STATS & RELOAD
# =========================================================

@router.get("/db/stats")
async def arkham_db_stats():
    """Statistiques détaillées de la base de données Arkham."""
    try:
        from services.arkham_scraper import get_arkham_db

        db = get_arkham_db()
        scraper = _get_scraper()
        stats = db.get_stats()
        stats["firecrawl"] = scraper.get_stats()
        return stats

    except Exception as e:
        return {"error": str(e)}


@router.post("/db/reload")
async def arkham_db_reload():
    """
    Recharge la DB Arkham en mémoire depuis les fichiers JSON.
    Utile après un scrape manuel ou un modif des fichiers.
    """
    try:
        from services.arkham_scraper import get_arkham_db

        db = get_arkham_db()
        db.load()

        return {
            "status": "reloaded",
            "stats": db.get_stats(),
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
