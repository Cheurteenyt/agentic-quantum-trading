import json
import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ARKHAM_EXPLORER_ROOT = "https://intel.arkm.com/explorer"
DEFAULT_CAPTURE_XHR_PATTERN = r"https://.*"
KEYWORD_HINTS = (
    "holder",
    "holders",
    "transfer",
    "transfers",
    "counterparty",
    "counterparties",
    "inflow",
    "outflow",
    "swap",
    "swaps",
    "mint",
    "burn",
    "wallet",
    "entity",
    "portfolio",
    "balance",
    "history",
    "flow",
    "liquidity",
)
PROBE_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "arkham" / "scrapling"
NORMALIZED_OUTPUT_DIR = PROBE_OUTPUT_DIR / "normalized"
DEFAULT_SNAPSHOT_TTL_SECONDS = 900
TOKEN_SNAPSHOT_SCHEMA_VERSION = 2
ENTITY_SNAPSHOT_SCHEMA_VERSION = 2
CHAIN_ALIASES = {
    "arbitrum-one": "arbitrum",
    "binance-smart-chain": "bsc",
    "bnb-smart-chain": "bsc",
    "ethereum-mainnet": "ethereum",
    "polygon-pos": "polygon",
}
PARTY_FLAG_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("hot wallet", "hot wallet"),
    ("cold wallet", "cold wallet"),
    ("deposit", "deposit"),
    ("withdraw", "withdrawal"),
    ("bridge", "bridge"),
    ("router", "router"),
    ("vault", "vault"),
    ("pool", "pool"),
    ("proxy", "proxy"),
    ("prime", "prime"),
    ("custody", "custody"),
    ("exchange", "exchange"),
    ("cex", "exchange"),
    ("dex", "dex"),
)
XHR_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("/intelligence/entity_balance_changes", "entity_balance_changes"),
    ("/intelligence/entity/", "entity_profile"),
    ("/intelligence/token/", "token_profile"),
    ("/balances/entity_top_address/", "top_address"),
    ("/balances/entity", "balances"),
    ("/history/entity/", "history"),
    ("/transfers", "transfers"),
    ("/token/price/history/", "price_history"),
    ("/token/market/", "token_market"),
    ("/token/volume/", "token_volume"),
    ("/token/addresses/", "token_addresses"),
    ("/token/holders", "token_holders"),
    ("/marketdata/max_instrument_funding_rates_time_series", "funding_rates"),
    ("/marketdata/earliest_perp_instrument", "perp_instrument"),
    ("/volume/entity/", "entity_volume"),
    ("/loans/entity/", "loans"),
)


class ScraplingProbeError(RuntimeError):
    pass


def _slugify(value: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "-" for ch in (value or "").strip()]
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _clean_text(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _semantic_hits(*chunks: str) -> list[str]:
    blob = " ".join(_clean_text(chunk).lower() for chunk in chunks if chunk)
    return [hint for hint in KEYWORD_HINTS if hint in blob]


def _maybe_json_from_body(body: Any, content_type: str = "") -> tuple[Any | None, str | None]:
    if body is None:
        return None, None

    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    else:
        text = str(body)

    stripped = text.strip()
    if not stripped:
        return None, text[:400]

    looks_json = "json" in (content_type or "").lower() or stripped[:1] in {"{", "["}
    if not looks_json:
        return None, text[:400]

    try:
        return json.loads(stripped), text[:400]
    except json.JSONDecodeError:
        return None, text[:400]


def _categorize_xhr(url: str) -> str:
    for needle, category in XHR_CATEGORY_RULES:
        if needle in (url or ""):
            return category
    return "other"


def _interesting_score(url: str, category: str, semantic_hits: list[str], status: Any) -> int:
    score = 0
    if str(status) == "200":
        score += 20
    if category != "other":
        score += 30
    score += len(semantic_hits) * 5
    if "api.arkm.com" in (url or ""):
        score += 10
    return score


def _summarize_json_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        first_keys = list(payload.keys())[:20]
        nested = {
            key: type(value).__name__
            for key, value in list(payload.items())[:10]
        }
        return {
            "kind": "dict",
            "keys": first_keys,
            "nested_types": nested,
        }

    if isinstance(payload, list):
        sample = payload[0] if payload else None
        sample_keys = list(sample.keys())[:20] if isinstance(sample, dict) else None
        return {
            "kind": "list",
            "length": len(payload),
            "sample_type": type(sample).__name__ if sample is not None else None,
            "sample_keys": sample_keys,
        }

    return {
        "kind": type(payload).__name__,
        "value_preview": _clean_text(str(payload))[:200],
    }


def _extract_texts(page: Any, selector: str, limit: int = 20) -> list[str]:
    try:
        values = page.css(f"{selector}::text").getall()
    except Exception:
        return []
    cleaned: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _extract_page_summary(page: Any) -> dict[str, Any]:
    headings = _extract_texts(page, "h1, h2, h3", limit=24)
    buttons = _extract_texts(page, "button", limit=24)
    links = _extract_texts(page, "a", limit=24)
    body_text = _extract_texts(page, "body, body *", limit=200)

    hero_title = headings[0] if headings else None
    interesting_links = [text for text in links if len(text) <= 40][:12]
    interesting_buttons = [text for text in buttons if len(text) <= 40][:16]
    excerpt = _clean_text(" ".join(body_text))[:2000]

    return {
        "title": hero_title,
        "headings": headings,
        "buttons": interesting_buttons,
        "links": interesting_links,
        "body_excerpt": excerpt,
        "semantic_hits": _semantic_hits(excerpt, " ".join(headings), " ".join(interesting_buttons)),
    }


def _build_probe_url(kind: Literal["entity", "token"], target: str) -> str:
    normalized = _slugify(target)
    if not normalized:
        raise ScraplingProbeError("Target is empty")
    return f"{ARKHAM_EXPLORER_ROOT}/{kind}/{normalized}"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = re.sub(r"[^0-9eE+\-\.]", "", str(value))
        if not cleaned:
            return None
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=lambda item: str(item))]
    if isinstance(value, Path):
        return str(value)
    return value


def _pick(source: dict[str, Any] | None, *keys: str) -> Any:
    if not isinstance(source, dict):
        return None
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _to_unix_timestamp(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def _normalize_chain_name(value: Any) -> str:
    normalized = _slugify(str(value or ""))
    if not normalized:
        return "unknown"
    return CHAIN_ALIASES.get(normalized, normalized)


def _titleize_slug(value: Any) -> str:
    return " ".join(part.capitalize() for part in str(value or "").replace("_", "-").split("-") if part)


def _matches_token_identifier(value: Any, *candidates: str) -> bool:
    normalized = _slugify(str(value or ""))
    if not normalized:
        return False
    return any(normalized == _slugify(candidate) for candidate in candidates if candidate)


def _extract_party_identity(party: Any) -> dict[str, Any]:
    if not isinstance(party, dict):
        return {
            "address": None,
            "chain": None,
            "label": None,
            "entity": None,
            "wallet_type": None,
        }

    entity_obj = _pick(party, "arkhamEntity", "entity")
    label_obj = _pick(party, "arkhamLabel", "label")

    entity_name = None
    entity_id = None
    entity_type = None
    if isinstance(entity_obj, dict):
        entity_name = _pick(entity_obj, "name", "label", "id")
        entity_id = _pick(entity_obj, "id", "slug")
        entity_type = _pick(entity_obj, "type", "entityType", "category")
    elif entity_obj not in (None, "", [], {}):
        entity_name = str(entity_obj)

    label_name = None
    if isinstance(label_obj, dict):
        label_name = _pick(label_obj, "name", "label", "displayName")
    elif label_obj not in (None, "", [], {}):
        label_name = str(label_obj)

    if not label_name:
        label_name = _pick(party, "name", "displayName")
    if not label_name and entity_name:
        label_name = entity_name

    service_id = _pick(party, "depositServiceID", "withdrawalServiceID", "serviceID", "serviceId")

    return {
        "address": _pick(party, "address", "addressHash", "hash"),
        "chain": _normalize_chain_name(_pick(party, "chain", "network")),
        "label": label_name,
        "entity": entity_name,
        "entity_id": entity_id,
        "service_id": service_id,
        "wallet_type": _pick(party, "type", "addressType", "walletType") or entity_type,
        "is_contract": bool(_pick(party, "contract", "isContract")),
    }


def _venue_like(name: Any, entity_type: Any = None) -> bool:
    label = str(name or "").lower()
    kind = str(entity_type or "").lower()
    if kind in {"cex", "dex", "exchange", "bridge", "protocol", "misc"}:
        return True
    return any(
        keyword in label
        for keyword in (
            "swap",
            "router",
            "pool",
            "vault",
            "bridge",
            "binance",
            "coinbase",
            "kraken",
            "mexc",
            "bitget",
            "gate",
            "kucoin",
            "okx",
            "bybit",
            "htx",
            "uniswap",
            "pancake",
        )
    )


def _normalize_entity_balance_changes(
    payload: Any,
    *,
    target_slug: str,
    target_symbol: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        token_balances = item.get("tokenBalances") or []
        relevant_balances = []
        for token_balance in token_balances:
            if not isinstance(token_balance, dict):
                continue
            if _matches_token_identifier(
                token_balance.get("tokenId"),
                target_slug,
                target_symbol,
            ) or _matches_token_identifier(
                token_balance.get("tokenSymbol"),
                target_slug,
                target_symbol,
            ):
                relevant_balances.append(token_balance)

        if not relevant_balances:
            continue

        balance_usd = sum(_safe_float(tb.get("balanceUsd")) or 0.0 for tb in relevant_balances)
        prev_balance_usd = sum(_safe_float(tb.get("prevBalanceUsd")) or 0.0 for tb in relevant_balances)
        change_usd = round(balance_usd - prev_balance_usd, 2)
        balance_unit = sum(_safe_float(tb.get("balanceUnit")) or 0.0 for tb in relevant_balances)
        prev_balance_unit = sum(_safe_float(tb.get("prevBalanceUnit")) or 0.0 for tb in relevant_balances)
        change_unit = balance_unit - prev_balance_unit
        entity_name = str(item.get("entityName") or item.get("entityId") or "Unknown")

        rows.append(
            {
                "entity": entity_name,
                "entity_id": item.get("entityId"),
                "entity_type": item.get("entityType"),
                "balance_usd": round(balance_usd, 2),
                "prev_balance_usd": round(prev_balance_usd, 2),
                "change_usd": change_usd,
                "balance_unit": balance_unit,
                "prev_balance_unit": prev_balance_unit,
                "change_unit": change_unit,
                "direction": "inflow" if change_usd >= 0 else "outflow",
                "is_venue": _venue_like(entity_name, item.get("entityType")),
            }
        )

    rows.sort(key=lambda entry: abs(entry.get("change_usd") or 0.0), reverse=True)
    return rows


def _normalize_arkham_transfers(
    payload: Any,
    *,
    target_symbol: str,
) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict):
        return [], 0

    items = payload.get("transfers") or payload.get("items") or []
    count = _safe_int(payload.get("count")) or len(items)
    if not isinstance(items, list):
        return [], count

    normalized: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        tx_hash = _pick(item, "transactionHash", "txHash", "hash")
        transfer_id = _pick(item, "id")
        dedupe_key = str(tx_hash or transfer_id or "")
        if dedupe_key and dedupe_key in seen_keys:
            continue
        if dedupe_key:
            seen_keys.add(dedupe_key)

        from_party = _extract_party_identity(_pick(item, "fromAddress", "from"))
        to_party = _extract_party_identity(_pick(item, "toAddress", "to"))
        token_info = _pick(item, "token", "tokenInfo", "tokenMetadata") or {}
        token_symbol = _pick(token_info, "symbol", "ticker") or _pick(item, "tokenSymbol", "symbol") or str(target_symbol).upper()
        token_name = _pick(token_info, "name", "label") or _pick(item, "tokenName", "name") or str(target_symbol).upper()
        token_decimals = _safe_int(_pick(item, "decimals", "tokenDecimals")) or _safe_int(_pick(token_info, "decimals")) or 18

        human_value = _safe_float(_pick(item, "unitValue", "amount", "quantity", "tokenAmount"))
        raw_value = _pick(item, "value", "rawValue", "tokenValue")
        if human_value is None and raw_value not in (None, "", [], {}):
            raw_float = _safe_float(raw_value)
            if raw_float is not None:
                human_value = raw_float / (10 ** token_decimals)

        value_usd = _safe_float(
            _pick(
                item,
                "historicalUSD",
                "valueUsd",
                "valueUSD",
                "amountUsd",
                "amountUSD",
                "usd",
            )
        )
        if value_usd is None and human_value is not None:
            unit_price_usd = _safe_float(_pick(item, "unitPriceUsd", "unitPriceUSD")) or _safe_float(
                _pick(token_info, "priceUsd", "priceUSD", "price")
            )
            if unit_price_usd is not None:
                value_usd = round(human_value * unit_price_usd, 2)

        normalized.append(
            {
                "tx_hash": tx_hash or transfer_id or "",
                "timestamp": _to_unix_timestamp(_pick(item, "blockTimestamp", "timestamp", "time", "datetime")),
                "from": from_party.get("address") or "",
                "to": to_party.get("address") or "",
                "from_chain": from_party.get("chain"),
                "to_chain": to_party.get("chain"),
                "value": str(raw_value or ""),
                "token_symbol": str(token_symbol).upper(),
                "token_decimal": str(token_decimals),
                "token_name": token_name,
                "human_value": human_value,
                "value_usd": round(value_usd, 2) if value_usd is not None else None,
                "method": _pick(item, "method"),
                "transfer_type": _pick(item, "flow", "direction", "type"),
                "from_wallet_type": from_party.get("wallet_type"),
                "to_wallet_type": to_party.get("wallet_type"),
                "from_is_contract": from_party.get("is_contract"),
                "to_is_contract": to_party.get("is_contract"),
                "from_label": from_party.get("label"),
                "from_entity": from_party.get("entity"),
                "from_entity_id": from_party.get("entity_id"),
                "from_service_id": from_party.get("service_id"),
                "from_display_label": _display_party_label(from_party),
                "to_label": to_party.get("label"),
                "to_entity": to_party.get("entity"),
                "to_entity_id": to_party.get("entity_id"),
                "to_service_id": to_party.get("service_id"),
                "to_display_label": _display_party_label(to_party),
                "chain": _normalize_chain_name(_pick(item, "chain", "network") or from_party.get("chain") or to_party.get("chain")),
            }
        )

    normalized.sort(key=lambda entry: entry.get("timestamp") or 0, reverse=True)
    return normalized, count


def _history_bucket_label(start_ts: int | None, end_ts: int | None) -> str:
    if not start_ts:
        return "Recent"

    start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    if not end_ts or end_ts == start_ts:
        return start_dt.strftime("%d %b")

    end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)
    if start_dt.date() == end_dt.date():
        return start_dt.strftime("%d %b")
    return f"{start_dt.strftime('%d %b')} - {end_dt.strftime('%d %b')}"


def _display_party_label(party: dict[str, Any] | None) -> str:
    party = party or {}
    entity = str(party.get("entity") or "").strip()
    label = str(party.get("label") or "").strip()
    service_id = str(party.get("service_id") or "").strip()
    address = str(party.get("address") or "").strip()

    if entity and label:
        if _slugify(entity) == _slugify(label):
            return entity
        return f"{entity}: {label}"
    if entity:
        return entity
    if label:
        return label
    if service_id:
        return _titleize_slug(service_id)
    return address


def _derive_wallet_flags(*values: Any) -> list[str]:
    blob = " | ".join(str(value or "") for value in values).lower()
    flags: list[str] = []
    for keyword, label in PARTY_FLAG_KEYWORDS:
        if keyword in blob and label not in flags:
            flags.append(label)
    return flags or ["wallet"]


def _downsample_balance_history(points: list[dict[str, Any]], max_points: int = 16) -> list[dict[str, Any]]:
    if not points:
        return []

    ordered = sorted(
        [
            {
                "timestamp": _safe_int(point.get("timestamp")),
                "usd": _safe_float(point.get("usd")),
            }
            for point in points
            if _safe_int(point.get("timestamp")) is not None and _safe_float(point.get("usd")) is not None
        ],
        key=lambda point: point["timestamp"] or 0,
    )
    if not ordered:
        return []

    if len(ordered) <= max_points:
        chunked = [[point] for point in ordered]
    else:
        chunk_size = max(1, (len(ordered) + max_points - 1) // max_points)
        chunked = [ordered[index:index + chunk_size] for index in range(0, len(ordered), chunk_size)]

    buckets: list[dict[str, Any]] = []
    baseline = chunked[0][0]["usd"] or 0.0
    for index, chunk in enumerate(chunked):
        start = chunk[0]
        end = chunk[-1]
        net_usd = (end["usd"] or 0.0) - (start["usd"] or 0.0)
        buckets.append(
            {
                "key": f"bucket-{index}",
                "label": _history_bucket_label(start["timestamp"], end["timestamp"]),
                "start_ts": start["timestamp"],
                "end_ts": end["timestamp"],
                "balance_estimate_usd": round(end["usd"] or 0.0, 2),
                "inflow_usd": round(net_usd, 2) if net_usd > 0 else 0.0,
                "outflow_usd": round(abs(net_usd), 2) if net_usd < 0 else 0.0,
                "net_usd": round(net_usd, 2),
                "cumulative_net_usd": round((end["usd"] or 0.0) - baseline, 2),
                "tx_count": len(chunk),
            }
        )
    return buckets


def _normalize_entity_profile_payload(payload: Any, target_slug: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "name": _titleize_slug(target_slug) or target_slug,
            "id": target_slug,
            "type": None,
            "website": None,
            "socials": {},
            "badges": [],
            "tags": [],
            "note": None,
            "crunchbase": None,
        }

    tags = []
    badges = []
    for raw_tag in payload.get("populatedTags") or []:
        if not isinstance(raw_tag, dict):
            continue
        label = str(raw_tag.get("label") or "").strip()
        if not label:
            continue
        tags.append(label)
        if not raw_tag.get("disablePage"):
            badges.append(label)

    socials = {
        "x": payload.get("twitter"),
        "linkedin": payload.get("linkedin"),
        "crunchbase": payload.get("crunchbase"),
    }

    return {
        "name": payload.get("name") or _titleize_slug(target_slug) or target_slug,
        "id": payload.get("id") or target_slug,
        "type": payload.get("type"),
        "website": payload.get("website"),
        "socials": {key: value for key, value in socials.items() if value},
        "badges": list(dict.fromkeys(badges))[:16],
        "tags": list(dict.fromkeys(tags))[:64],
        "note": payload.get("note") or None,
        "crunchbase": payload.get("crunchbase"),
    }


def _normalize_entity_balances_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "summary": {
                "total_balance_usd": None,
                "total_balance_24h_ago_usd": None,
                "balance_change_24h_usd": None,
                "balance_change_24h_pct": None,
            },
            "holdings": [],
            "network_usage": [],
        }

    balances = payload.get("balances") if isinstance(payload.get("balances"), dict) else {}
    holdings: list[dict[str, Any]] = []
    network_usage_map: dict[str, dict[str, Any]] = {}

    for chain_name, items in balances.items():
        if not isinstance(items, list):
            continue
        chain = _normalize_chain_name(chain_name)
        network_entry = network_usage_map.setdefault(
            chain,
            {
                "chain": chain,
                "observed_value_usd": 0.0,
                "inflow_usd": 0.0,
                "outflow_usd": 0.0,
                "net_usd": 0.0,
                "tx_count": 0,
                "wallet_count": None,
                "asset_count": 0,
            },
        )
        asset_count = 0
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "UNKNOWN").upper()
            asset_id = _pick(item, "underlyingAssetID", "id") or symbol.lower()
            contract_address = _pick(item, "underlyingAssetAddress", "address", "market")
            balance = _safe_float(item.get("balance"))
            usd_value = _safe_float(item.get("usd"))
            price = _safe_float(item.get("price"))
            price_change_pct = _safe_float(item.get("priceChange24hPercent"))
            holdings.append(
                {
                    "key": f"{chain}:{contract_address or asset_id or index}",
                    "symbol": symbol,
                    "name": item.get("name") or symbol,
                    "chain": chain,
                    "contract_address": contract_address,
                    "asset_id": asset_id,
                    "human_balance_total": balance,
                    "wallet_count": None,
                    "estimated_value_usd": round(usd_value, 2) if usd_value is not None else None,
                    "price_usd": price,
                    "price_change_24h_pct": price_change_pct,
                    "max_holder_share_pct": None,
                    "protocol": item.get("protocol"),
                    "position_type": item.get("type"),
                    "quote_time": item.get("quoteTime"),
                }
            )
            if usd_value is not None:
                network_entry["observed_value_usd"] += usd_value
            asset_count += 1
        network_entry["asset_count"] += asset_count

    total_balance = _safe_float(payload.get("totalBalance"))
    total_balance_24h_ago = _safe_float(payload.get("totalBalance24hAgo"))
    balance_change_24h_usd = None
    balance_change_24h_pct = None
    if total_balance is not None and total_balance_24h_ago is not None:
        balance_change_24h_usd = round(total_balance - total_balance_24h_ago, 2)
        if total_balance_24h_ago:
            balance_change_24h_pct = round(((total_balance - total_balance_24h_ago) / total_balance_24h_ago) * 100, 4)

    holdings.sort(key=lambda item: item.get("estimated_value_usd") or 0.0, reverse=True)
    network_usage = sorted(
        (
            {
                **entry,
                "observed_value_usd": round(entry["observed_value_usd"], 2) if entry["observed_value_usd"] else None,
            }
            for entry in network_usage_map.values()
        ),
        key=lambda entry: entry.get("observed_value_usd") or 0.0,
        reverse=True,
    )

    return {
        "summary": {
            "total_balance_usd": round(total_balance, 2) if total_balance is not None else None,
            "total_balance_24h_ago_usd": round(total_balance_24h_ago, 2) if total_balance_24h_ago is not None else None,
            "balance_change_24h_usd": balance_change_24h_usd,
            "balance_change_24h_pct": balance_change_24h_pct,
        },
        "holdings": holdings,
        "network_usage": network_usage,
    }


def _normalize_entity_history_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"balances_history": [], "history_by_chain": {}}

    aggregate_map: dict[int, float] = {}
    history_by_chain: dict[str, list[dict[str, Any]]] = {}
    for chain_name, items in payload.items():
        if not isinstance(items, list):
            continue
        chain = _normalize_chain_name(chain_name)
        chain_points: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            timestamp = _to_unix_timestamp(item.get("time"))
            usd_value = _safe_float(item.get("usd"))
            if timestamp is None or usd_value is None:
                continue
            chain_points.append({"timestamp": timestamp, "usd": usd_value})
            aggregate_map[timestamp] = aggregate_map.get(timestamp, 0.0) + usd_value
        if chain_points:
            history_by_chain[chain] = chain_points[-180:]

    aggregate_points = [
        {"timestamp": timestamp, "usd": usd_value}
        for timestamp, usd_value in sorted(aggregate_map.items())
    ]
    return {
        "balances_history": _downsample_balance_history(aggregate_points),
        "history_by_chain": history_by_chain,
    }


def _normalize_entity_loans_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"positions": [], "protocols": [], "total_positions": 0}

    positions: list[dict[str, Any]] = []
    protocol_map: dict[str, dict[str, Any]] = {}
    balances = payload.get("balances") if isinstance(payload.get("balances"), dict) else {}
    for chain_name, items in balances.items():
        if not isinstance(items, list):
            continue
        chain = _normalize_chain_name(chain_name)
        for item in items:
            if not isinstance(item, dict):
                continue
            usd_value = _safe_float(item.get("usd"))
            protocol = str(item.get("protocol") or "UNKNOWN").upper()
            position_type = str(item.get("type") or "position").lower()
            positions.append(
                {
                    "chain": chain,
                    "protocol": protocol,
                    "type": position_type,
                    "name": item.get("name") or item.get("symbol") or protocol,
                    "symbol": item.get("symbol"),
                    "asset_id": _pick(item, "underlyingAssetID", "id"),
                    "contract_address": _pick(item, "underlyingAssetAddress", "address", "market"),
                    "balance": _safe_float(item.get("balance")),
                    "value_usd": round(usd_value, 2) if usd_value is not None else None,
                    "price_usd": _safe_float(item.get("price")),
                }
            )
            protocol_entry = protocol_map.setdefault(
                protocol,
                {"protocol": protocol, "value_usd": 0.0, "positions": 0},
            )
            if usd_value is not None:
                protocol_entry["value_usd"] += usd_value
            protocol_entry["positions"] += 1

    positions.sort(key=lambda position: position.get("value_usd") or 0.0, reverse=True)
    protocols = sorted(
        (
            {
                "protocol": protocol,
                "value_usd": round(entry["value_usd"], 2) if entry["value_usd"] else None,
                "positions": entry["positions"],
            }
            for protocol, entry in protocol_map.items()
        ),
        key=lambda entry: entry.get("value_usd") or 0.0,
        reverse=True,
    )
    return {
        "positions": positions[:40],
        "protocols": protocols[:12],
        "total_positions": _safe_int(payload.get("totalPositions")) or len(positions),
    }


def _normalize_entity_volume_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"exchange_usage": [], "network_flows": {}}

    exchange_map: dict[str, dict[str, Any]] = {}
    network_flows: dict[str, dict[str, Any]] = {}
    for chain_name, items in payload.items():
        if not isinstance(items, list):
            continue
        chain = _normalize_chain_name(chain_name)
        chain_entry = network_flows.setdefault(
            chain,
            {"inflow_usd": 0.0, "outflow_usd": 0.0, "net_usd": 0.0, "tx_count": 0},
        )
        for item in items:
            if not isinstance(item, dict):
                continue
            for volume in item.get("volumes") or []:
                if not isinstance(volume, dict):
                    continue
                exchange_name = str(_pick(volume, "exchangeName", "exchangeID") or "Unknown")
                inflow_usd = _safe_float(volume.get("depositedUSD")) or 0.0
                outflow_usd = _safe_float(volume.get("withdrawnUSD")) or 0.0
                row = exchange_map.setdefault(
                    exchange_name,
                    {
                        "label": exchange_name,
                        "category": "exchange",
                        "inflow_usd": 0.0,
                        "outflow_usd": 0.0,
                        "net_usd": 0.0,
                        "tx_count": 0,
                        "token_symbols": [],
                    },
                )
                row["inflow_usd"] += inflow_usd
                row["outflow_usd"] += outflow_usd
                row["net_usd"] = row["inflow_usd"] - row["outflow_usd"]
                row["tx_count"] += 1

                chain_entry["inflow_usd"] += inflow_usd
                chain_entry["outflow_usd"] += outflow_usd
                chain_entry["net_usd"] = chain_entry["inflow_usd"] - chain_entry["outflow_usd"]
                chain_entry["tx_count"] += 1

    exchange_usage = sorted(
        (
            {
                **row,
                "inflow_usd": round(row["inflow_usd"], 2) if row["inflow_usd"] else 0.0,
                "outflow_usd": round(row["outflow_usd"], 2) if row["outflow_usd"] else 0.0,
                "net_usd": round(row["net_usd"], 2) if row["net_usd"] else 0.0,
            }
            for row in exchange_map.values()
            if row["inflow_usd"] or row["outflow_usd"]
        ),
        key=lambda row: (abs(row.get("net_usd") or 0.0), row.get("tx_count") or 0),
        reverse=True,
    )[:20]
    return {"exchange_usage": exchange_usage, "network_flows": network_flows}


def _entity_transfer_matches_target(
    transfer: dict[str, Any],
    side: str,
    *,
    target_slug: str,
    target_name: str,
) -> bool:
    target_slug_norm = _slugify(target_slug)
    target_name_norm = _slugify(target_name)
    entity_id = _slugify(str(transfer.get(f"{side}_entity_id") or ""))
    entity_name = _slugify(str(transfer.get(f"{side}_entity") or ""))
    display_label = _slugify(str(transfer.get(f"{side}_display_label") or transfer.get(f"{side}_label") or ""))
    return any(
        candidate
        for candidate in (entity_id, entity_name, display_label)
        if candidate and candidate in {target_slug_norm, target_name_norm}
    )


def _normalize_entity_transfers_payload(
    transfers: list[dict[str, Any]],
    *,
    target_slug: str,
    target_name: str,
    generated_at: int,
) -> dict[str, Any]:
    wallets: dict[str, dict[str, Any]] = {}
    counterparties: dict[str, dict[str, Any]] = {}
    recent_activity: list[dict[str, Any]] = []
    flow_window_start = generated_at - 86400
    flow_summary = {"inflow": 0.0, "outflow": 0.0, "net_flow": 0.0, "tx_count": 0}

    for transfer in transfers:
        from_match = _entity_transfer_matches_target(transfer, "from", target_slug=target_slug, target_name=target_name)
        to_match = _entity_transfer_matches_target(transfer, "to", target_slug=target_slug, target_name=target_name)
        if not from_match and not to_match:
            continue
        if from_match and to_match:
            continue

        direction = "outflow" if from_match else "inflow"
        own_prefix = "from" if from_match else "to"
        other_prefix = "to" if from_match else "from"

        wallet_address = str(transfer.get(own_prefix) or "").strip()
        wallet_label = str(
            transfer.get(f"{own_prefix}_display_label")
            or transfer.get(f"{own_prefix}_label")
            or transfer.get(f"{own_prefix}_entity")
            or wallet_address
        ).strip()
        counterparty_address = str(transfer.get(other_prefix) or "").strip() or None
        counterparty_label = str(
            transfer.get(f"{other_prefix}_display_label")
            or transfer.get(f"{other_prefix}_label")
            or transfer.get(f"{other_prefix}_entity")
            or transfer.get(f"{other_prefix}_service_id")
            or counterparty_address
            or "Unknown"
        ).strip()

        token_symbol = str(transfer.get("token_symbol") or "UNKNOWN").upper()
        timestamp = _safe_int(transfer.get("timestamp"))
        value_usd = _safe_float(transfer.get("value_usd"))
        amount = _safe_float(transfer.get("human_value"))

        if wallet_address:
            wallet = wallets.setdefault(
                wallet_address.lower(),
                {
                    "address": wallet_address.lower(),
                    "chain": transfer.get(f"{own_prefix}_chain") or transfer.get("chain"),
                    "label": wallet_label,
                    "entity": target_name,
                    "confidence": "high",
                    "flags": set(),
                    "matched_tags": set(),
                    "token_symbols": set(),
                    "observed_value_usd": None,
                    "observed_token_count": 0,
                    "activity_profile": {
                        "transactions_count": 0,
                        "token_transfers_count": 0,
                        "activity_bucket": None,
                    },
                },
            )
            wallet["flags"].update(
                _derive_wallet_flags(
                    wallet_label,
                    transfer.get(f"{own_prefix}_wallet_type"),
                    transfer.get(f"{own_prefix}_service_id"),
                )
            )
            wallet["token_symbols"].add(token_symbol)
            wallet["activity_profile"]["transactions_count"] += 1
            wallet["activity_profile"]["token_transfers_count"] += 1

        activity_row = {
            "tx_hash": transfer.get("tx_hash"),
            "timestamp": timestamp,
            "direction": direction,
            "token_symbol": token_symbol,
            "token_name": transfer.get("token_name"),
            "chain": transfer.get("chain") or transfer.get(f"{own_prefix}_chain") or transfer.get(f"{other_prefix}_chain"),
            "amount": amount,
            "value_usd": round(value_usd, 2) if value_usd is not None else None,
            "wallet_label": wallet_label,
            "wallet_address": wallet_address or None,
            "counterparty_label": counterparty_label,
            "counterparty_address": counterparty_address,
            "counterparty_entity": transfer.get(f"{other_prefix}_entity"),
        }
        recent_activity.append(activity_row)

        counterparty_key = str(
            transfer.get(f"{other_prefix}_entity_id")
            or counterparty_address
            or counterparty_label
        ).lower()
        counterparty = counterparties.setdefault(
            counterparty_key,
            {
                "label": counterparty_label,
                "address": counterparty_address,
                "tx_count": 0,
                "inflow_count": 0,
                "outflow_count": 0,
                "value_usd": 0.0,
            },
        )
        counterparty["tx_count"] += 1
        if direction == "inflow":
            counterparty["inflow_count"] += 1
        else:
            counterparty["outflow_count"] += 1
        if value_usd is not None:
            counterparty["value_usd"] += value_usd

        if timestamp and timestamp >= flow_window_start:
            flow_summary["tx_count"] += 1
            if direction == "inflow" and value_usd is not None:
                flow_summary["inflow"] += value_usd
            elif direction == "outflow" and value_usd is not None:
                flow_summary["outflow"] += value_usd

    flow_summary["inflow"] = round(flow_summary["inflow"], 2)
    flow_summary["outflow"] = round(flow_summary["outflow"], 2)
    flow_summary["net_flow"] = round(flow_summary["inflow"] - flow_summary["outflow"], 2)

    wallet_list = []
    role_counter: Counter[str] = Counter()
    for wallet in wallets.values():
        tx_count = wallet["activity_profile"]["transactions_count"]
        wallet["activity_profile"]["activity_bucket"] = "high" if tx_count >= 20 else "medium" if tx_count >= 5 else "low"
        wallet["flags"] = sorted(wallet["flags"])
        wallet["matched_tags"] = sorted(wallet["matched_tags"])
        wallet["token_symbols"] = sorted(wallet["token_symbols"])
        wallet["observed_token_count"] = len(wallet["token_symbols"])
        for flag in wallet["flags"] or ["wallet"]:
            role_counter[flag] += 1
        wallet_list.append(wallet)

    wallet_list.sort(
        key=lambda wallet: (
            wallet.get("activity_profile", {}).get("transactions_count") or 0,
            wallet.get("observed_token_count") or 0,
        ),
        reverse=True,
    )
    recent_activity.sort(key=lambda row: row.get("timestamp") or 0, reverse=True)
    counterparty_list = sorted(
        (
            {
                **counterparty,
                "value_usd": round(counterparty["value_usd"], 2) if counterparty["value_usd"] else None,
            }
            for counterparty in counterparties.values()
        ),
        key=lambda row: (row.get("value_usd") or 0.0, row.get("tx_count") or 0),
        reverse=True,
    )
    role_clusters = [
        {
            "role": role,
            "wallet_count": count,
            "share_pct": round((count / len(wallet_list)) * 100, 2) if wallet_list else None,
        }
        for role, count in role_counter.most_common(12)
    ]
    return {
        "wallets": wallet_list[:40],
        "recent_activity": recent_activity[:60],
        "counterparties": counterparty_list[:20],
        "flow_summary": flow_summary,
        "role_clusters": role_clusters,
    }


def _payload_richness(payload: Any) -> int:
    if isinstance(payload, dict):
        score = len(payload)
        for value in payload.values():
            if isinstance(value, (dict, list)):
                score += len(value)
            elif value not in (None, "", [], {}):
                score += 1
        return score
    if isinstance(payload, list):
        score = len(payload)
        if payload and isinstance(payload[0], (dict, list)):
            score += len(payload[0])
        return score
    return len(str(payload or ""))


def _derive_token_flows(
    entity_changes: list[dict[str, Any]],
    transfers: list[dict[str, Any]],
) -> dict[str, Any]:
    inflows = [
        {
            "entity": entry.get("entity"),
            "amount": abs(entry.get("change_usd") or 0.0),
            "timestamp": entry.get("timestamp"),
        }
        for entry in entity_changes
        if (entry.get("change_usd") or 0.0) > 0
    ]
    outflows = [
        {
            "entity": entry.get("entity"),
            "amount": abs(entry.get("change_usd") or 0.0),
            "timestamp": entry.get("timestamp"),
        }
        for entry in entity_changes
        if (entry.get("change_usd") or 0.0) < 0
    ]
    inflows.sort(key=lambda entry: entry.get("amount") or 0.0, reverse=True)
    outflows.sort(key=lambda entry: entry.get("amount") or 0.0, reverse=True)

    venue_map: dict[str, dict[str, Any]] = {}
    for entry in entity_changes:
        if not entry.get("is_venue"):
            continue
        label = str(entry.get("entity") or "Unknown")
        row = venue_map.setdefault(
            label,
            {"exchange": label, "net": 0.0, "inflow": 0.0, "outflow": 0.0, "tx_count": 0},
        )
        change_usd = entry.get("change_usd") or 0.0
        row["net"] += change_usd
        if change_usd >= 0:
            row["inflow"] += change_usd
        else:
            row["outflow"] += abs(change_usd)

    for transfer in transfers:
        value_usd = transfer.get("value_usd") or 0.0
        if value_usd <= 0:
            continue

        for side, direction in (("from", "outflow"), ("to", "inflow")):
            entity_label = transfer.get(f"{side}_entity") or transfer.get(f"{side}_label")
            if not _venue_like(entity_label):
                continue
            row = venue_map.setdefault(
                str(entity_label),
                {"exchange": str(entity_label), "net": 0.0, "inflow": 0.0, "outflow": 0.0, "tx_count": 0},
            )
            row["tx_count"] += 1
            if direction == "inflow":
                row["inflow"] += value_usd
                row["net"] += value_usd
            else:
                row["outflow"] += value_usd
                row["net"] -= value_usd

    exchange_flows = sorted(venue_map.values(), key=lambda row: abs(row.get("net") or 0.0), reverse=True)[:12]
    for row in exchange_flows:
        row["net"] = round(row.get("net") or 0.0, 2)
        row["inflow"] = round(row.get("inflow") or 0.0, 2)
        row["outflow"] = round(row.get("outflow") or 0.0, 2)

    if not inflows and not outflows:
        inflow_map: dict[str, float] = {}
        outflow_map: dict[str, float] = {}
        for transfer in transfers:
            value_usd = transfer.get("value_usd") or 0.0
            if value_usd <= 0:
                continue

            to_label = transfer.get("to_entity") or transfer.get("to_label")
            from_label = transfer.get("from_entity") or transfer.get("from_label")

            if to_label:
                inflow_map[str(to_label)] = inflow_map.get(str(to_label), 0.0) + value_usd
            if from_label:
                outflow_map[str(from_label)] = outflow_map.get(str(from_label), 0.0) + value_usd

        inflows = sorted(
            [{"entity": label, "amount": round(amount, 2), "timestamp": None} for label, amount in inflow_map.items()],
            key=lambda entry: entry.get("amount") or 0.0,
            reverse=True,
        )[:12]
        outflows = sorted(
            [{"entity": label, "amount": round(amount, 2), "timestamp": None} for label, amount in outflow_map.items()],
            key=lambda entry: entry.get("amount") or 0.0,
            reverse=True,
        )[:12]

    total_entities_tracked = len(entity_changes)
    if total_entities_tracked == 0:
        labels = {
            str(label)
            for transfer in transfers
            for label in (
                transfer.get("from_entity") or transfer.get("from_label"),
                transfer.get("to_entity") or transfer.get("to_label"),
            )
            if label
        }
        total_entities_tracked = len(labels)

    return {
        "entity_balance_changes": [
            {
                "entity": entry.get("entity"),
                "change": round(entry.get("change_usd") or 0.0, 2),
                "direction": entry.get("direction"),
                "timestamp": entry.get("timestamp"),
            }
            for entry in entity_changes[:25]
        ],
        "top_inflows": inflows[:12],
        "top_outflows": outflows[:12],
        "exchange_flows": exchange_flows,
        "total_entities_tracked": total_entities_tracked,
    }


class ScraplingProbeService:
    def __init__(self) -> None:
        self._import_error: str | None = None
        self._dynamic_session_cls: Any = None
        self._normalized_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._load_scrapling()

    def _load_scrapling(self) -> None:
        try:
            from scrapling.fetchers import DynamicSession  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            self._import_error = str(exc)
            self._dynamic_session_cls = None
            return

        self._dynamic_session_cls = DynamicSession
        self._import_error = None

    @property
    def available(self) -> bool:
        return self._dynamic_session_cls is not None

    def _capture_arkham_page(
        self,
        kind: Literal["entity", "token"],
        target: str,
        *,
        capture_xhr: str,
        timeout_ms: int,
        headless: bool,
        real_chrome: bool,
        max_xhr: int,
    ) -> dict[str, Any]:
        url = _build_probe_url(kind, target)
        started_at = time.time()
        logger.info("[SCRAPLING] Probing %s", url)

        with self._dynamic_session_cls(
            headless=headless,
            real_chrome=real_chrome,
            network_idle=True,
            wait_selector="body",
            timeout=timeout_ms,
            capture_xhr=capture_xhr,
            disable_resources=True,
        ) as session:
            page = session.fetch(url)

        xhr_domains: dict[str, int] = {}
        captured_xhr = list(getattr(page, "captured_xhr", []) or [])
        xhr_entries: list[dict[str, Any]] = []

        for index, xhr in enumerate(captured_xhr[:max_xhr], start=1):
            headers = dict(getattr(xhr, "headers", {}) or {})
            body = getattr(xhr, "body", b"")
            content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
            payload, preview = _maybe_json_from_body(body, content_type)
            url_value = str(getattr(xhr, "url", "") or "")
            parsed = urlparse(url_value)
            domain = parsed.netloc or ""
            if domain:
                xhr_domains[domain] = xhr_domains.get(domain, 0) + 1
            semantic_hits = _semantic_hits(url_value, preview or "", content_type)
            category = _categorize_xhr(url_value)
            xhr_entries.append(
                {
                    "index": index,
                    "url": url_value,
                    "domain": domain,
                    "status": getattr(xhr, "status", None),
                    "category": category,
                    "content_type": content_type or None,
                    "body_bytes": len(body or b""),
                    "semantic_hits": semantic_hits,
                    "json_summary": _summarize_json_payload(payload) if payload is not None else None,
                    "body_preview": preview,
                    "payload": payload,
                }
            )

        return {
            "available": True,
            "kind": kind,
            "target": _slugify(target),
            "url": url,
            "final_url": getattr(page, "url", url),
            "status": getattr(page, "status", None),
            "timing_ms": round((time.time() - started_at) * 1000, 2),
            "page_summary": _extract_page_summary(page),
            "captured_xhr_count": len(captured_xhr),
            "captured_xhr_domains": xhr_domains,
            "captured_xhr_raw": xhr_entries,
            "capture_pattern": capture_xhr,
            "generated_at": int(time.time()),
        }

    def probe_arkham_page(
        self,
        kind: Literal["entity", "token"],
        target: str,
        *,
        capture_xhr: str = DEFAULT_CAPTURE_XHR_PATTERN,
        timeout_ms: int = 30000,
        headless: bool = True,
        real_chrome: bool = False,
        max_xhr: int = 25,
        include_bodies: bool = False,
        persist: bool = True,
    ) -> dict[str, Any]:
        if not self.available:
            raise ScraplingProbeError(
                "Scrapling is not available in the current Python environment"
                + (f": {self._import_error}" if self._import_error else "")
            )

        raw_probe = self._capture_arkham_page(
            kind,
            target,
            capture_xhr=capture_xhr,
            timeout_ms=timeout_ms,
            headless=headless,
            real_chrome=real_chrome,
            max_xhr=max_xhr,
        )
        xhr_entries: list[dict[str, Any]] = []
        for entry in raw_probe.get("captured_xhr_raw", []):
            summary = {
                "index": entry.get("index"),
                "url": entry.get("url"),
                "domain": entry.get("domain"),
                "status": entry.get("status"),
                "category": entry.get("category"),
                "content_type": entry.get("content_type"),
                "body_bytes": entry.get("body_bytes"),
                "semantic_hits": entry.get("semantic_hits"),
                "json_summary": entry.get("json_summary"),
            }
            if include_bodies:
                summary["body_preview"] = entry.get("body_preview")
                if entry.get("payload") is not None:
                    summary["json_body"] = entry.get("payload")
            xhr_entries.append(summary)

        result = {
            key: value
            for key, value in raw_probe.items()
            if key != "captured_xhr_raw"
        }
        result["captured_xhr"] = xhr_entries
        result["interesting_api_calls"] = sorted(
            [entry for entry in xhr_entries if "api.arkm.com" in str(entry.get("url") or "")],
            key=lambda entry: _interesting_score(
                str(entry.get("url") or ""),
                str(entry.get("category") or "other"),
                list(entry.get("semantic_hits") or []),
                entry.get("status"),
            ),
            reverse=True,
        )[:12]

        if persist:
            result["artifact_path"] = str(self._persist_probe(result))

        return result

    def _normalized_snapshot_path(self, kind: str, target: str) -> Path:
        NORMALIZED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return NORMALIZED_OUTPUT_DIR / f"{_slugify(kind)}_{_slugify(target)}.json"

    def _load_normalized_snapshot(
        self,
        kind: str,
        target: str,
        *,
        fresh_for: int | None = DEFAULT_SNAPSHOT_TTL_SECONDS,
    ) -> dict[str, Any] | None:
        key = (_slugify(kind), _slugify(target))
        cached = self._normalized_cache.get(key)
        if cached:
            generated_at = _safe_int(cached.get("generated_at")) or 0
            if fresh_for is None or (generated_at and time.time() - generated_at <= fresh_for):
                return cached

        path = self._normalized_snapshot_path(kind, target)
        if not path.exists():
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        if _slugify(kind) == "token" and _safe_int(payload.get("snapshot_version")) != TOKEN_SNAPSHOT_SCHEMA_VERSION:
            return None
        if _slugify(kind) == "entity" and _safe_int(payload.get("snapshot_version")) != ENTITY_SNAPSHOT_SCHEMA_VERSION:
            return None

        generated_at = _safe_int(payload.get("generated_at")) or 0
        if fresh_for is not None and generated_at and time.time() - generated_at > fresh_for:
            return None

        self._normalized_cache[key] = payload
        return payload

    def _persist_normalized_snapshot(self, payload: dict[str, Any]) -> Path:
        path = self._normalized_snapshot_path(payload.get("kind") or "snapshot", payload.get("target") or "unknown")
        serializable_payload = _json_safe(payload)
        path.write_text(json.dumps(serializable_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._normalized_cache[(_slugify(str(payload.get("kind") or "")), _slugify(str(payload.get("target") or "")))] = serializable_payload
        return path

    def get_token_snapshot(
        self,
        target: str,
        *,
        headless: bool = True,
        real_chrome: bool = False,
        timeout_ms: int = 30000,
        max_xhr: int = 40,
        fresh_for: int = DEFAULT_SNAPSHOT_TTL_SECONDS,
        persist: bool = True,
    ) -> dict[str, Any]:
        if not self.available:
            raise ScraplingProbeError(
                "Scrapling is not available in the current Python environment"
                + (f": {self._import_error}" if self._import_error else "")
            )

        target_slug = _slugify(target)
        stale_snapshot = self._load_normalized_snapshot("token", target_slug, fresh_for=None)
        fresh_snapshot = self._load_normalized_snapshot("token", target_slug, fresh_for=fresh_for)
        if fresh_snapshot is not None:
            return fresh_snapshot

        try:
            raw_probe = self._capture_arkham_page(
                "token",
                target,
                capture_xhr=DEFAULT_CAPTURE_XHR_PATTERN,
                timeout_ms=timeout_ms,
                headless=headless,
                real_chrome=real_chrome,
                max_xhr=max_xhr,
            )
            snapshot = self._normalize_token_snapshot(target_slug, raw_probe)
            if persist:
                try:
                    snapshot["artifact_path"] = str(self._persist_normalized_snapshot(snapshot))
                    snapshot["probe_artifact_path"] = str(self._persist_probe(self._probe_result_from_raw(raw_probe)))
                except Exception as exc:
                    logger.warning("[SCRAPLING] Unable to persist token snapshot for %s: %s", target_slug, exc)
            return snapshot
        except Exception:
            if stale_snapshot is not None:
                return stale_snapshot
            raise

    def get_entity_snapshot(
        self,
        target: str,
        *,
        headless: bool = True,
        real_chrome: bool = False,
        timeout_ms: int = 30000,
        max_xhr: int = 60,
        fresh_for: int = DEFAULT_SNAPSHOT_TTL_SECONDS,
        persist: bool = True,
    ) -> dict[str, Any]:
        if not self.available:
            raise ScraplingProbeError(
                "Scrapling is not available in the current Python environment"
                + (f": {self._import_error}" if self._import_error else "")
            )

        target_slug = _slugify(target)
        stale_snapshot = self._load_normalized_snapshot("entity", target_slug, fresh_for=None)
        fresh_snapshot = self._load_normalized_snapshot("entity", target_slug, fresh_for=fresh_for)
        if fresh_snapshot is not None:
            return fresh_snapshot

        try:
            raw_probe = self._capture_arkham_page(
                "entity",
                target,
                capture_xhr=DEFAULT_CAPTURE_XHR_PATTERN,
                timeout_ms=timeout_ms,
                headless=headless,
                real_chrome=real_chrome,
                max_xhr=max_xhr,
            )
            snapshot = self._normalize_entity_snapshot(target_slug, raw_probe)
            if persist:
                try:
                    snapshot["artifact_path"] = str(self._persist_normalized_snapshot(snapshot))
                    snapshot["probe_artifact_path"] = str(self._persist_probe(self._probe_result_from_raw(raw_probe)))
                except Exception as exc:
                    logger.warning("[SCRAPLING] Unable to persist entity snapshot for %s: %s", target_slug, exc)
            return snapshot
        except Exception:
            if stale_snapshot is not None:
                return stale_snapshot
            raise

    def _probe_result_from_raw(self, raw_probe: dict[str, Any]) -> dict[str, Any]:
        result = {
            key: value
            for key, value in raw_probe.items()
            if key != "captured_xhr_raw"
        }
        result["captured_xhr"] = [
            {
                "index": entry.get("index"),
                "url": entry.get("url"),
                "domain": entry.get("domain"),
                "status": entry.get("status"),
                "category": entry.get("category"),
                "content_type": entry.get("content_type"),
                "body_bytes": entry.get("body_bytes"),
                "semantic_hits": entry.get("semantic_hits"),
                "json_summary": entry.get("json_summary"),
                "body_preview": entry.get("body_preview"),
            }
            for entry in raw_probe.get("captured_xhr_raw", [])
        ]
        result["interesting_api_calls"] = sorted(
            [entry for entry in result["captured_xhr"] if "api.arkm.com" in str(entry.get("url") or "")],
            key=lambda entry: _interesting_score(
                str(entry.get("url") or ""),
                str(entry.get("category") or "other"),
                list(entry.get("semantic_hits") or []),
                entry.get("status"),
            ),
            reverse=True,
        )[:12]
        return result

    def _normalize_token_snapshot(self, target_slug: str, raw_probe: dict[str, Any]) -> dict[str, Any]:
        payloads: dict[str, Any] = {}
        for entry in raw_probe.get("captured_xhr_raw", []):
            category = str(entry.get("category") or "other")
            payload = entry.get("payload")
            if payload is None or category == "other":
                continue
            existing = payloads.get(category)
            if existing is None or _payload_richness(payload) >= _payload_richness(existing):
                payloads[category] = payload

        token_profile = payloads.get("token_profile") if isinstance(payloads.get("token_profile"), dict) else {}
        identifier = token_profile.get("identifier") if isinstance(token_profile, dict) else {}
        pricing_id = _slugify(_pick(identifier, "pricingID", "pricingId", "id") or target_slug)
        token_symbol = str(token_profile.get("symbol") or target_slug).upper()
        token_symbol_slug = _slugify(token_profile.get("symbol") or target_slug)

        entity_changes = _normalize_entity_balance_changes(
            payloads.get("entity_balance_changes"),
            target_slug=pricing_id or target_slug,
            target_symbol=token_symbol_slug,
        )
        transfers, transfer_count = _normalize_arkham_transfers(
            payloads.get("transfers"),
            target_symbol=token_symbol,
        )
        arkham_flows = _derive_token_flows(entity_changes, transfers)

        market = payloads.get("token_market") if isinstance(payloads.get("token_market"), dict) else {}
        addresses = payloads.get("token_addresses") if isinstance(payloads.get("token_addresses"), dict) else {}
        price_history = payloads.get("price_history") if isinstance(payloads.get("price_history"), list) else []
        token_volume = payloads.get("token_volume") if isinstance(payloads.get("token_volume"), list) else []
        funding_rates = payloads.get("funding_rates") if isinstance(payloads.get("funding_rates"), dict) else {}
        perp_instrument = payloads.get("perp_instrument") if isinstance(payloads.get("perp_instrument"), dict) else {}

        snapshot = {
            "available": True,
            "kind": "token",
            "target": target_slug,
            "source": "scrapling_arkham",
            "snapshot_version": TOKEN_SNAPSHOT_SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "url": raw_probe.get("url"),
            "final_url": raw_probe.get("final_url"),
            "status": raw_probe.get("status"),
            "timing_ms": raw_probe.get("timing_ms"),
            "page_summary": raw_probe.get("page_summary"),
            "symbol": token_symbol,
            "name": token_profile.get("name") or target_slug,
            "pricing_id": pricing_id or target_slug,
            "market": market,
            "addresses": addresses,
            "price_history": price_history[:180],
            "token_volume": token_volume[:120],
            "funding_rates": funding_rates,
            "perp_instrument": perp_instrument,
            "transfers": transfers[:50],
            "transfers_count": transfer_count,
            "arkham_flows": arkham_flows,
        }
        self._normalized_cache[("token", target_slug)] = snapshot
        return snapshot

    def _normalize_entity_snapshot(self, target_slug: str, raw_probe: dict[str, Any]) -> dict[str, Any]:
        payloads: dict[str, Any] = {}
        for entry in raw_probe.get("captured_xhr_raw", []):
            category = str(entry.get("category") or "other")
            payload = entry.get("payload")
            if payload is None or category == "other":
                continue
            existing = payloads.get(category)
            if existing is None or _payload_richness(payload) >= _payload_richness(existing):
                payloads[category] = payload

        profile = _normalize_entity_profile_payload(payloads.get("entity_profile"), target_slug)
        balances_payload = _normalize_entity_balances_payload(payloads.get("balances"))
        history_payload = _normalize_entity_history_payload(payloads.get("history"))
        volume_payload = _normalize_entity_volume_payload(payloads.get("entity_volume"))
        loans_payload = _normalize_entity_loans_payload(payloads.get("loans"))
        transfers, transfer_count = _normalize_arkham_transfers(
            payloads.get("transfers"),
            target_symbol="",
        )
        transfer_payload = _normalize_entity_transfers_payload(
            transfers,
            target_slug=target_slug,
            target_name=str(profile.get("name") or target_slug),
            generated_at=int(time.time()),
        )

        holdings = list(balances_payload.get("holdings") or [])
        token_surface_map: dict[str, dict[str, Any]] = {
            str(item.get("key") or f"{item.get('chain')}:{item.get('symbol')}"): dict(item)
            for item in holdings
        }
        for row in transfer_payload.get("recent_activity") or []:
            token_key = None
            for holding in holdings:
                if (
                    _normalize_chain_name(holding.get("chain")) == _normalize_chain_name(row.get("chain"))
                    and str(holding.get("symbol") or "").upper() == str(row.get("token_symbol") or "").upper()
                ):
                    token_key = holding.get("key")
                    break
            token_key = str(token_key or f"{_normalize_chain_name(row.get('chain'))}:{str(row.get('token_symbol') or 'UNKNOWN').upper()}")
            token_entry = token_surface_map.setdefault(
                token_key,
                {
                    "key": token_key,
                    "symbol": row.get("token_symbol") or "UNKNOWN",
                    "name": row.get("token_name") or row.get("token_symbol") or "Unknown Asset",
                    "chain": _normalize_chain_name(row.get("chain")),
                    "contract_address": None,
                    "asset_id": None,
                    "human_balance_total": None,
                    "wallet_count": None,
                    "estimated_value_usd": None,
                    "price_usd": None,
                    "max_holder_share_pct": None,
                },
            )
            token_entry.setdefault("recent_inflow_usd", 0.0)
            token_entry.setdefault("recent_outflow_usd", 0.0)
            token_entry.setdefault("recent_net_usd", 0.0)
            token_entry.setdefault("recent_tx_count", 0)
            value_usd = _safe_float(row.get("value_usd")) or 0.0
            if row.get("direction") == "inflow":
                token_entry["recent_inflow_usd"] += value_usd
            elif row.get("direction") == "outflow":
                token_entry["recent_outflow_usd"] += value_usd
            token_entry["recent_net_usd"] = token_entry["recent_inflow_usd"] - token_entry["recent_outflow_usd"]
            token_entry["recent_tx_count"] += 1

        token_balance_surface = sorted(
            (
                {
                    **item,
                    "recent_inflow_usd": round(_safe_float(item.get("recent_inflow_usd")) or 0.0, 2),
                    "recent_outflow_usd": round(_safe_float(item.get("recent_outflow_usd")) or 0.0, 2),
                    "recent_net_usd": round(_safe_float(item.get("recent_net_usd")) or 0.0, 2),
                    "recent_tx_count": _safe_int(item.get("recent_tx_count")) or 0,
                    "share_pct": (
                        round(((item.get("estimated_value_usd") or 0.0) / (balances_payload["summary"].get("total_balance_usd") or 0.0)) * 100, 2)
                        if balances_payload["summary"].get("total_balance_usd") and item.get("estimated_value_usd") is not None
                        else None
                    ),
                }
                for item in token_surface_map.values()
            ),
            key=lambda item: (
                item.get("estimated_value_usd") or 0.0,
                abs(item.get("recent_net_usd") or 0.0),
                item.get("recent_tx_count") or 0,
            ),
            reverse=True,
        )[:24]

        network_usage_map: dict[str, dict[str, Any]] = {
            str(item.get("chain")): dict(item)
            for item in balances_payload.get("network_usage") or []
        }
        for chain, flow in (volume_payload.get("network_flows") or {}).items():
            entry = network_usage_map.setdefault(
                chain,
                {
                    "chain": chain,
                    "observed_value_usd": None,
                    "inflow_usd": 0.0,
                    "outflow_usd": 0.0,
                    "net_usd": 0.0,
                    "tx_count": 0,
                    "wallet_count": None,
                    "asset_count": 0,
                },
            )
            entry["inflow_usd"] = round((_safe_float(entry.get("inflow_usd")) or 0.0) + (_safe_float(flow.get("inflow_usd")) or 0.0), 2)
            entry["outflow_usd"] = round((_safe_float(entry.get("outflow_usd")) or 0.0) + (_safe_float(flow.get("outflow_usd")) or 0.0), 2)
            entry["net_usd"] = round((_safe_float(entry.get("inflow_usd")) or 0.0) - (_safe_float(entry.get("outflow_usd")) or 0.0), 2)
            entry["tx_count"] = (_safe_int(entry.get("tx_count")) or 0) + (_safe_int(flow.get("tx_count")) or 0)

        for row in transfer_payload.get("recent_activity") or []:
            chain = _normalize_chain_name(row.get("chain"))
            entry = network_usage_map.setdefault(
                chain,
                {
                    "chain": chain,
                    "observed_value_usd": None,
                    "inflow_usd": 0.0,
                    "outflow_usd": 0.0,
                    "net_usd": 0.0,
                    "tx_count": 0,
                    "wallet_count": None,
                    "asset_count": 0,
                },
            )
            value_usd = _safe_float(row.get("value_usd")) or 0.0
            if row.get("direction") == "inflow":
                entry["inflow_usd"] = round((_safe_float(entry.get("inflow_usd")) or 0.0) + value_usd, 2)
            elif row.get("direction") == "outflow":
                entry["outflow_usd"] = round((_safe_float(entry.get("outflow_usd")) or 0.0) + value_usd, 2)
            entry["net_usd"] = round((_safe_float(entry.get("inflow_usd")) or 0.0) - (_safe_float(entry.get("outflow_usd")) or 0.0), 2)
            entry["tx_count"] = (_safe_int(entry.get("tx_count")) or 0) + 1

        network_usage = sorted(
            network_usage_map.values(),
            key=lambda item: (
                item.get("observed_value_usd") or 0.0,
                abs(item.get("net_usd") or 0.0),
                item.get("tx_count") or 0,
            ),
            reverse=True,
        )[:16]

        top_tags = [
            {"tag": tag, "count": 1}
            for tag in list(dict.fromkeys(profile.get("tags") or []))[:16]
        ]
        chain_counter = Counter(item.get("chain") for item in holdings if item.get("chain"))
        chain_counter.update(item.get("chain") for item in network_usage if item.get("chain"))
        chains = [
            {"chain": chain, "hits": hits}
            for chain, hits in chain_counter.most_common(16)
            if chain
        ]

        coverage = {
            "snapshots_scanned": 1,
            "holder_rows_scanned": len(holdings),
            "observed_wallets": len(transfer_payload.get("wallets") or []),
            "observed_tokens": len(holdings),
            "recent_activity_count": len(transfer_payload.get("recent_activity") or []),
            "coverage_note": (
                "Live Arkham entity snapshot captured via Scrapling. Portfolio, balances history, transfers, venues and loans "
                "come from Arkham page XHRs, while the local cache can still augment missing labels."
            ),
        }

        snapshot = {
            "available": True,
            "kind": "entity",
            "target": target_slug,
            "source": "scrapling_arkham",
            "snapshot_version": ENTITY_SNAPSHOT_SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "url": raw_probe.get("url"),
            "final_url": raw_probe.get("final_url"),
            "status": raw_probe.get("status"),
            "timing_ms": raw_probe.get("timing_ms"),
            "page_summary": raw_probe.get("page_summary"),
            "entity": {
                "name": profile.get("name"),
                "slug": profile.get("id") or target_slug,
                "type": profile.get("type"),
                "website": profile.get("website"),
                "socials": profile.get("socials") or {},
                "badges": profile.get("badges") or [],
                "tags": profile.get("tags") or [],
                "top_address": payloads.get("top_address"),
            },
            "profile": profile,
            "summary": balances_payload.get("summary") or {},
            "holdings": holdings[:80],
            "history_by_chain": history_payload.get("history_by_chain") or {},
            "loans": loans_payload.get("positions") or [],
            "loan_protocols": loans_payload.get("protocols") or [],
            "loans_total_positions": loans_payload.get("total_positions") or 0,
            "transfers": transfers[:80],
            "transfers_count": transfer_count,
            "wallets": transfer_payload.get("wallets") or [],
            "recent_activity": transfer_payload.get("recent_activity") or [],
            "counterparties": transfer_payload.get("counterparties") or [],
            "flow_summary": transfer_payload.get("flow_summary") or {},
            "coverage": coverage,
            "chains": chains,
            "top_tags": top_tags,
            "estimated_total_value_usd": balances_payload["summary"].get("total_balance_usd"),
            "surfaces": {
                "balances_history": history_payload.get("balances_history") or [],
                "history_by_chain": history_payload.get("history_by_chain") or {},
                "token_balance_surface": token_balance_surface,
                "network_usage": network_usage,
                "exchange_usage": volume_payload.get("exchange_usage") or [],
                "role_clusters": transfer_payload.get("role_clusters") or [],
                "loan_protocols": loans_payload.get("protocols") or [],
            },
        }
        self._normalized_cache[("entity", target_slug)] = snapshot
        return snapshot

    def _persist_probe(self, payload: dict[str, Any]) -> Path:
        PROBE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        kind = _slugify(payload.get("kind") or "probe")
        target = _slugify(payload.get("target") or "unknown")
        path = PROBE_OUTPUT_DIR / f"{kind}_{target}_{timestamp}.json"
        path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


_probe_service_instance: ScraplingProbeService | None = None


def get_scrapling_probe_service() -> ScraplingProbeService:
    global _probe_service_instance
    if _probe_service_instance is None:
        _probe_service_instance = ScraplingProbeService()
    elif not _probe_service_instance.available:
        _probe_service_instance._load_scrapling()
    return _probe_service_instance
