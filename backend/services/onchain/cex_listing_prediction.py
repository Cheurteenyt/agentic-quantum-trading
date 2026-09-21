from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from services.onchain.behavioral_evidence_bridge import (
    get_manipulation_detection_stealth_accumulation_anomaly_scan_preview,
    get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview,
    get_manipulation_detection_top_expansion_directional_intent_classifier_preview,
)
from services.onchain.events.parsers import _decode_uint_words


def _engine():
    from services import onchain_engine

    return onchain_engine


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _clean_address(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if clean.startswith("0x") and len(clean) == 42:
        return clean
    return ""


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_iso_timestamp(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return None


_POSITIVE_LISTING_TIERS = {"tier_1_listing", "tier_2_listing", "positive_listing"}
_NEGATIVE_LISTING_TIERS = {
    "never_listed_90d",
    "negative_never_listed_90d",
    "documented_scam_never_listed",
    "documented_honeypot_never_listed",
}
_SOURCE_TIERS = {"tier_1", "tier_2", "manual_source_backed", "security_api"}
_KNOWN_POSITIVE_LISTING_TOKENS = {
    "0x7ec43cf65f1663f820427c62a5780b8f2e25593a",
    "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    "0x9eca8dedb4882bd694aea786c0cbe770e70d52e3",
}
_CEX_LISTING_POSITIVE_SEED_ROWS = [
    {
        "chain": "bsc",
        "token_address": "0x7ec43cf65f1663f820427c62a5780b8f2e25593a",
        "token_symbol": "LAB",
        "cex_name": "Bitget",
        "market_pair": "LAB/USDT",
        "announcement_url": "https://www.bitget.com/en-CA/support/articles/12560603839482",
        "announcement_at": "2025-10-13T09:30:00Z",
        "listing_at": "2025-10-14T12:00:00Z",
        "listing_tier": "tier_2_listing",
        "source_tier": "tier_2",
    },
    {
        "chain": "bsc",
        "token_address": "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
        "token_symbol": "B",
        "cex_name": "Bitget",
        "market_pair": "B/USDT",
        "announcement_url": "https://www.bitget.com/support/articles/12560603827935",
        "announcement_at": "2025-05-22T09:11:00Z",
        "listing_at": "2025-05-22T12:00:00Z",
        "listing_tier": "tier_2_listing",
        "source_tier": "tier_2",
    },
    {
        "chain": "bsc",
        "token_address": "0x9eca8dedb4882bd694aea786c0cbe770e70d52e3",
        "token_symbol": "LONG",
        "cex_name": "Gate",
        "market_pair": "LONG/USDT",
        "announcement_url": "https://www.gate.com/tr/announcements/article/47986",
        "announcement_at": "2025-11-04T10:22:01Z",
        "listing_at": "2025-11-06T12:00:00Z",
        "listing_tier": "tier_2_listing",
        "source_tier": "tier_2",
    },
]
_BSC_INFRA_TOKEN_ADDRESSES = {
    "0x55d398326f99059ff775485246999027b3197955",  # USDT
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
    "0xe9e7cea3dedca5984780bafc599bd69add087d56",  # BUSD
    "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3",  # DAI
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB
    "0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c",  # BTCB
}
_INFRA_SYMBOLS = {"WBNB", "WETH", "ETH", "BNB", "BTCB", "USDT", "USDC", "BUSD", "DAI"}
_COINGECKO_PLATFORM_IDS = {
    "bsc": "binance-smart-chain",
    "bnb": "binance-smart-chain",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum-one",
    "polygon": "polygon-pos",
}
_CEX_MARKET_ALIASES = {
    "binance": "Binance",
    "okx": "OKX",
    "gate": "Gate",
    "gate.io": "Gate",
    "mexc": "MEXC",
    "bitget": "Bitget",
    "kucoin": "KuCoin",
    "xt": "XT",
    "xt.com": "XT",
    "bybit_spot": "Bybit",
    "bybit": "Bybit",
    "crypto_com": "Crypto.com",
    "cryptocom": "Crypto.com",
    "htx": "HTX",
}


def _is_infrastructure_symbol(symbol: str) -> bool:
    clean = str(symbol or "").strip().upper()
    return clean in _INFRA_SYMBOLS or clean.endswith("-LP") or clean.endswith(" LP")


def _listing_tier(score: int) -> str:
    if score >= 70:
        return "high_listing_research_priority"
    if score >= 50:
        return "medium_listing_research_priority"
    if score >= 30:
        return "watchlist_only"
    return "insufficient_evidence"


def _ground_truth_dedupe_key(row: dict[str, Any]) -> str:
    return "|".join([
        _clean_text(row.get("chain")).lower(),
        _clean_text(row.get("token_address")).lower(),
        _clean_text(row.get("cex_name")).lower(),
        _clean_text(row.get("market_pair")).upper(),
        _clean_text(row.get("announcement_at")),
        _clean_text(row.get("source_digest")).lower(),
    ])


def _positive_seed_ground_truth_rows(chain: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in _CEX_LISTING_POSITIVE_SEED_ROWS:
        if _clean_text(seed.get("chain")).lower() != chain:
            continue
        payload = {
            "ground_truth_type": "positive_cex_listing_seed",
            "source_url": seed.get("announcement_url"),
            "token_address": seed.get("token_address"),
            "cex_name": seed.get("cex_name"),
            "market_pair": seed.get("market_pair"),
            "announcement_at": seed.get("announcement_at"),
            "listing_at": seed.get("listing_at"),
        }
        row = dict(seed)
        digest = _digest(payload)
        row["source_digest"] = digest
        row["source_excerpt_digest"] = digest
        row["payload_json"] = payload
        row["source_policy"] = "source-backed positive CEX listing seed row for bridge backtesting only"
        rows.append(row)
    return rows


def _normalize_ground_truth_row(row: dict[str, Any], default_chain: str) -> tuple[dict[str, Any], list[str]]:
    clean_chain = _clean_text(row.get("chain") or default_chain).lower()
    token_address = _clean_address(row.get("token_address"))
    token_symbol = _clean_text(row.get("token_symbol")).upper()
    cex_name = _clean_text(row.get("cex_name"))
    market_pair = _clean_text(row.get("market_pair")).upper()
    announcement_url = _clean_text(row.get("announcement_url") or row.get("source_url"))
    announcement_at = _clean_text(row.get("announcement_at")) or None
    listing_at = _clean_text(row.get("listing_at")) or None
    listing_tier = _clean_text(row.get("listing_tier") or row.get("ground_truth_label"))
    source_tier = _clean_text(row.get("source_tier"))
    source_digest = _clean_text(row.get("source_digest")).lower()
    source_excerpt_digest = _clean_text(row.get("source_excerpt_digest")).lower() or None
    payload_json = row.get("payload_json")
    if isinstance(payload_json, str) and payload_json.strip():
        try:
            parsed_payload = json.loads(payload_json)
        except json.JSONDecodeError:
            parsed_payload = {"raw_payload_json": payload_json}
    elif isinstance(payload_json, dict):
        parsed_payload = payload_json
    else:
        parsed_payload = {
            "source_url": announcement_url,
            "ground_truth_label": listing_tier,
            "input_row": row,
        }

    normalized = {
        "chain": clean_chain,
        "token_address": token_address,
        "token_symbol": token_symbol,
        "cex_name": cex_name,
        "market_pair": market_pair,
        "announcement_url": announcement_url,
        "announcement_at": announcement_at,
        "listing_at": listing_at,
        "listing_tier": listing_tier,
        "source_tier": source_tier,
        "source_digest": source_digest,
        "source_excerpt_digest": source_excerpt_digest,
        "payload_json": _canonical_json(parsed_payload),
        "source_policy": _clean_text(row.get("source_policy")) or (
            "manual source-backed CEX listing ground-truth row for bridge backtesting only"
        ),
    }
    normalized["dedupe_key"] = _clean_text(row.get("dedupe_key")) or _ground_truth_dedupe_key(normalized)

    blockers: list[str] = []
    if not token_address:
        blockers.append("token_address_required")
    if not token_symbol:
        blockers.append("token_symbol_required")
    if not cex_name:
        blockers.append("cex_name_required")
    if not market_pair:
        blockers.append("market_pair_required")
    if not announcement_url:
        blockers.append("announcement_url_or_source_url_required")
    if not listing_tier:
        blockers.append("listing_tier_or_ground_truth_label_required")
    if source_tier not in _SOURCE_TIERS:
        blockers.append("source_tier_invalid")
    if not source_digest:
        blockers.append("source_digest_required")
    if listing_tier not in _POSITIVE_LISTING_TIERS | _NEGATIVE_LISTING_TIERS:
        blockers.append("listing_tier_invalid")
    if listing_tier in _NEGATIVE_LISTING_TIERS:
        if cex_name.upper() != "NONE":
            blockers.append("negative_rows_must_use_cex_name_NONE")
        if market_pair.upper() != "NONE":
            blockers.append("negative_rows_must_use_market_pair_NONE")
    else:
        if not announcement_at and not listing_at:
            blockers.append("positive_listing_requires_announcement_at_or_listing_at")

    return normalized, blockers


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _table_count(conn: Any, table_name: str) -> int | None:
    if not _table_exists(conn, table_name):
        return None
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
    except Exception:
        return None


def _parse_token_addresses(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [part.strip() for part in value.replace("\n", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []
    addresses: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        address = _clean_address(item)
        if address and address not in seen:
            addresses.append(address)
            seen.add(address)
    return addresses


def _security_chain_id(chain: str) -> str | None:
    chain_ids = {
        "bsc": "56",
        "bnb": "56",
        "eth": "1",
        "ethereum": "1",
        "base": "8453",
        "arbitrum": "42161",
        "polygon": "137",
    }
    return chain_ids.get(str(chain or "").strip().lower())


def _coingecko_platform_id(chain: str) -> str | None:
    return _COINGECKO_PLATFORM_IDS.get(str(chain or "").strip().lower())


def _http_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "CoreEquityReadOnly/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read(2_000_000)
    decoded = payload.decode("utf-8", errors="replace")
    return json.loads(decoded)


def _coingecko_contract_url(chain: str, token: str) -> str | None:
    platform_id = _coingecko_platform_id(chain)
    if not platform_id:
        return None
    return (
        "https://api.coingecko.com/api/v3/coins/"
        + urllib.parse.quote(platform_id)
        + "/contract/"
        + urllib.parse.quote(token)
        + "?"
        + urllib.parse.urlencode({
            "localization": "false",
            "tickers": "true",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        })
    )


def _extract_coingecko_cex_markets(payload: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ticker in list(payload.get("tickers") or []):
        market = ticker.get("market") or {}
        identifier = str(market.get("identifier") or "").strip().lower()
        name = str(market.get("name") or "").strip()
        name_key = name.lower()
        alias = None
        for key, value in _CEX_MARKET_ALIASES.items():
            if identifier == key or name_key == key or key in identifier or key in name_key:
                alias = value
                break
        if not alias:
            continue
        pair = f"{ticker.get('base') or ''}/{ticker.get('target') or ''}".strip("/").upper()
        dedupe = f"{alias}|{pair}|{ticker.get('trade_url') or ''}"
        if dedupe in seen:
            continue
        seen.add(dedupe)
        matches.append({
            "cex_name": alias,
            "market_identifier": identifier or None,
            "market_name": name or alias,
            "market_pair": pair or None,
            "trade_url": ticker.get("trade_url"),
            "last_traded_at": ticker.get("last_traded_at"),
            "is_anomaly": bool(ticker.get("is_anomaly")),
            "is_stale": bool(ticker.get("is_stale")),
        })
        if len(matches) >= limit:
            break
    return matches


def _known_token_symbols_from_local_context(chain: str, addresses: list[str]) -> dict[str, str]:
    if not addresses:
        return {}
    placeholders = ",".join("?" for _ in addresses)
    symbols: dict[str, str] = {}
    conn = _engine()._get_db()
    try:
        for table_name in ("token_metadata", "pair_tokens"):
            if not _table_exists(conn, table_name):
                continue
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
            metadata_address_col = "address" if "address" in columns else "token_address"
            if table_name == "token_metadata" and {metadata_address_col, "symbol"}.issubset(columns):
                query = f"SELECT LOWER({metadata_address_col}), symbol FROM token_metadata WHERE LOWER({metadata_address_col}) IN ({placeholders})"
                for row in conn.execute(query, tuple(addresses)).fetchall():
                    if row[0] and row[1]:
                        symbols.setdefault(str(row[0]).lower(), str(row[1]).upper())
            if table_name == "pair_tokens":
                for token_col, symbol_col in (("token0", "token0_symbol"), ("token1", "token1_symbol")):
                    if {token_col, symbol_col}.issubset(columns):
                        query = (
                            f"SELECT LOWER({token_col}), {symbol_col} FROM pair_tokens "
                            f"WHERE chain = ? AND LOWER({token_col}) IN ({placeholders})"
                        )
                        for row in conn.execute(query, (chain, *addresses)).fetchall():
                            if row[0] and row[1]:
                                symbols.setdefault(str(row[0]).lower(), str(row[1]).upper())
    finally:
        conn.close()
    return symbols


def _existing_ground_truth_tokens(conn: Any) -> set[str]:
    if not _table_exists(conn, "cex_listing_ground_truth_dataset"):
        return set()
    return {
        str(row[0] or "").lower()
        for row in conn.execute("SELECT token_address FROM cex_listing_ground_truth_dataset").fetchall()
    }


def _local_scam_negative_candidate_scope(chain: str, limit: int, max_scan_rows: int) -> list[dict[str, Any]]:
    bridge = get_manipulation_detection_cex_listing_probability_bridge_preview(
        chain=chain,
        limit=limit,
        dry_run=True,
        min_behavioral_score=20,
        cex_deposit_limit=200,
    )
    candidates: dict[str, dict[str, Any]] = {}

    def add_candidate(address: Any, source: str, **fields: Any) -> None:
        token = _clean_address(address)
        if not token:
            return
        row = candidates.setdefault(
            token,
            {
                "chain": chain,
                "token_address": token,
                "candidate_sources": [],
                "pair_occurrences": 0,
                "transfer_rows": 0,
                "behavioral_score": 0,
                "listing_probability_score": 0,
            },
        )
        if source not in row["candidate_sources"]:
            row["candidate_sources"].append(source)
        for key, value in fields.items():
            if key in {"pair_occurrences", "transfer_rows", "behavioral_score", "listing_probability_score"}:
                row[key] = max(_as_int(row.get(key)), _as_int(value))
            elif value not in (None, ""):
                row.setdefault(key, value)

    for row in list(bridge.get("candidates") or [])[:limit]:
        add_candidate(
            row.get("token_address"),
            "cex_listing_bridge_candidate",
            token_symbol=row.get("token_symbol"),
            pool_address=row.get("pool_address"),
            behavioral_score=row.get("behavioral_anomaly_score"),
            listing_probability_score=row.get("listing_probability_score"),
        )

    conn = _engine()._get_db()
    try:
        existing_tokens = _existing_ground_truth_tokens(conn)
        excluded_tokens = _KNOWN_POSITIVE_LISTING_TOKENS | existing_tokens
        if chain == "bsc":
            excluded_tokens |= _BSC_INFRA_TOKEN_ADDRESSES
        if _table_exists(conn, "token_transfers"):
            for row in conn.execute(
                """
                SELECT lower(token), COUNT(*), MIN(timestamp), MAX(timestamp)
                FROM token_transfers
                WHERE lower(chain)=? AND token IS NOT NULL AND token != ''
                GROUP BY lower(token)
                ORDER BY COUNT(*) DESC
                LIMIT ?
                """,
                (chain, max_scan_rows),
            ).fetchall():
                add_candidate(
                    row[0],
                    "token_transfers_activity",
                    transfer_rows=row[1],
                    first_seen_timestamp=row[2],
                    last_seen_timestamp=row[3],
                )
        if _table_exists(conn, "pair_tokens"):
            columns = {row[1] for row in conn.execute("PRAGMA table_info(pair_tokens)").fetchall()}
            for token_col, symbol_col in (("token0", "token0_symbol"), ("token1", "token1_symbol")):
                if token_col not in columns:
                    continue
                symbol_select = symbol_col if symbol_col in columns else "NULL"
                for row in conn.execute(
                    f"""
                    SELECT lower({token_col}), {symbol_select}, COUNT(*)
                    FROM pair_tokens
                    WHERE lower(chain)=? AND {token_col} IS NOT NULL AND {token_col} != ''
                    GROUP BY lower({token_col}), {symbol_select}
                    ORDER BY COUNT(*) DESC
                    LIMIT ?
                    """,
                    (chain, max_scan_rows),
                ).fetchall():
                    add_candidate(
                        row[0],
                        "pair_tokens_pool_presence",
                        token_symbol=str(row[1] or "").upper() or None,
                        pair_occurrences=row[2],
                    )
    finally:
        conn.close()

    symbols = _known_token_symbols_from_local_context(chain, list(candidates))
    filtered: list[dict[str, Any]] = []
    for token, row in candidates.items():
        symbol = str(row.get("token_symbol") or symbols.get(token) or "").upper()
        blockers = [
            *("known_positive_listing_seed_token" for _ in [1] if token in _KNOWN_POSITIVE_LISTING_TOKENS),
            *("already_in_ground_truth_dataset" for _ in [1] if token in existing_tokens),
            *("infrastructure_token_excluded" for _ in [1] if token in _BSC_INFRA_TOKEN_ADDRESSES or _is_infrastructure_symbol(symbol)),
        ]
        row["token_symbol"] = symbol or "UNKNOWN"
        row["scope_score"] = (
            _as_int(row.get("behavioral_score")) * 3
            + _as_int(row.get("listing_probability_score")) * 2
            + min(50, _as_int(row.get("transfer_rows")))
            + min(25, _as_int(row.get("pair_occurrences")) * 5)
        )
        row["scope_status"] = "selected_for_security_api_probe" if not blockers else "excluded"
        row["blockers"] = blockers
        if not blockers:
            filtered.append(row)

    filtered.sort(
        key=lambda row: (
            _as_int(row.get("scope_score")),
            _as_int(row.get("behavioral_score")),
            _as_int(row.get("transfer_rows")),
            _as_int(row.get("pair_occurrences")),
        ),
        reverse=True,
    )
    return filtered[:limit]


def _local_token_context_profiles(
    chain: str,
    token_addresses: list[str],
    bridge_candidates: list[dict[str, Any]] | None = None,
    scope_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    addresses = _parse_token_addresses(token_addresses)
    profiles = {
        address: {
            "chain": chain,
            "token_address": address,
            "token_symbol": None,
            "local_context_status": "missing_local_context",
            "behavioral_score": 0,
            "listing_probability_score": 0,
            "cex_deposit_count": 0,
            "fresh_like_depositors": 0,
            "shared_funders_proxy": 0,
            "stealth_accumulation_candidate": False,
            "transfer_rows": 0,
            "pair_occurrences": 0,
            "raw_swap_rows": 0,
            "first_seen_timestamp": None,
            "last_seen_timestamp": None,
            "age_days": None,
            "candidate_sources": [],
        }
        for address in addresses
    }
    bridge_by_token = {
        _clean_address(row.get("token_address")): row
        for row in list(bridge_candidates or [])
        if _clean_address(row.get("token_address"))
    }
    scope_by_token = {
        _clean_address(row.get("token_address")): row
        for row in list(scope_candidates or [])
        if _clean_address(row.get("token_address"))
    }
    now_ts = int(time.time())
    for token, row in bridge_by_token.items():
        if token not in profiles:
            continue
        cex_signal = row.get("cex_deposit_signal") or {}
        signals = list(row.get("evidence_signals") or [])
        profiles[token].update({
            "token_symbol": row.get("token_symbol") or profiles[token].get("token_symbol"),
            "behavioral_score": _as_int(row.get("behavioral_anomaly_score")),
            "listing_probability_score": _as_int(row.get("listing_probability_score")),
            "cex_deposit_count": _as_int(cex_signal.get("matching_deposits")),
            "fresh_like_depositors": _as_int(cex_signal.get("fresh_like_depositors")),
            "shared_funders_proxy": _as_int(cex_signal.get("shared_funders_proxy")),
            "stealth_accumulation_candidate": "stealth_accumulation_candidate" in signals,
        })
        profiles[token]["candidate_sources"].append("cex_listing_bridge_candidate")
    for token, row in scope_by_token.items():
        if token not in profiles:
            continue
        profiles[token].update({
            "token_symbol": row.get("token_symbol") or profiles[token].get("token_symbol"),
            "transfer_rows": max(_as_int(profiles[token].get("transfer_rows")), _as_int(row.get("transfer_rows"))),
            "pair_occurrences": max(_as_int(profiles[token].get("pair_occurrences")), _as_int(row.get("pair_occurrences"))),
            "first_seen_timestamp": row.get("first_seen_timestamp") or profiles[token].get("first_seen_timestamp"),
            "last_seen_timestamp": row.get("last_seen_timestamp") or profiles[token].get("last_seen_timestamp"),
        })
        for source in list(row.get("candidate_sources") or []):
            if source not in profiles[token]["candidate_sources"]:
                profiles[token]["candidate_sources"].append(source)

    conn = _engine()._get_db()
    try:
        symbols = _known_token_symbols_from_local_context(chain, addresses)
        for token, symbol in symbols.items():
            if token in profiles:
                profiles[token]["token_symbol"] = profiles[token].get("token_symbol") or symbol
        if _table_exists(conn, "token_transfers"):
            for token in addresses:
                row = conn.execute(
                    """
                    SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
                    FROM token_transfers
                    WHERE lower(chain)=? AND lower(token)=?
                    """,
                    (chain, token),
                ).fetchone()
                if row:
                    profiles[token]["transfer_rows"] = max(_as_int(profiles[token]["transfer_rows"]), _as_int(row[0]))
                    profiles[token]["first_seen_timestamp"] = profiles[token]["first_seen_timestamp"] or row[1]
                    profiles[token]["last_seen_timestamp"] = profiles[token]["last_seen_timestamp"] or row[2]
        if _table_exists(conn, "pair_tokens"):
            columns = {row[1] for row in conn.execute("PRAGMA table_info(pair_tokens)").fetchall()}
            for token in addresses:
                total_pairs = 0
                for token_col in ("token0", "token1"):
                    if token_col not in columns:
                        continue
                    total_pairs += _as_int(conn.execute(
                        f"SELECT COUNT(*) FROM pair_tokens WHERE lower(chain)=? AND lower({token_col})=?",
                        (chain, token),
                    ).fetchone()[0])
                profiles[token]["pair_occurrences"] = max(_as_int(profiles[token]["pair_occurrences"]), total_pairs)
        if _table_exists(conn, "dex_raw_swap_events") and _table_exists(conn, "pair_tokens"):
            columns = {row[1] for row in conn.execute("PRAGMA table_info(pair_tokens)").fetchall()}
            if {"pool", "token0", "token1"}.issubset(columns):
                for token in addresses:
                    pools = [
                        str(row[0]).lower()
                        for row in conn.execute(
                            """
                            SELECT lower(pool) FROM pair_tokens
                            WHERE lower(chain)=? AND (lower(token0)=? OR lower(token1)=?)
                            LIMIT 25
                            """,
                            (chain, token, token),
                        ).fetchall()
                        if row[0]
                    ]
                    if pools:
                        placeholders = ",".join("?" for _ in pools)
                        row = conn.execute(
                            f"""
                            SELECT COUNT(*), MIN(block_timestamp), MAX(block_timestamp)
                            FROM dex_raw_swap_events
                            WHERE lower(chain)=? AND lower(pair_address) IN ({placeholders})
                            """,
                            (chain, *pools),
                        ).fetchone()
                        profiles[token]["raw_swap_rows"] = _as_int(row[0]) if row else 0
                        if row:
                            profiles[token]["first_seen_timestamp"] = profiles[token]["first_seen_timestamp"] or row[1]
                            profiles[token]["last_seen_timestamp"] = profiles[token]["last_seen_timestamp"] or row[2]
    finally:
        conn.close()

    for profile in profiles.values():
        first_seen = _as_int(profile.get("first_seen_timestamp"))
        if first_seen > 0:
            profile["age_days"] = round((now_ts - first_seen) / 86_400, 2)
        evidence_fields = [
            profile.get("behavioral_score"),
            profile.get("listing_probability_score"),
            profile.get("cex_deposit_count"),
            profile.get("transfer_rows"),
            profile.get("pair_occurrences"),
            profile.get("raw_swap_rows"),
        ]
        if any(_as_int(value) > 0 for value in evidence_fields):
            profile["local_context_status"] = "local_context_present"
        profile["token_symbol"] = profile.get("token_symbol") or "UNKNOWN"
        profile["candidate_sources"] = list(dict.fromkeys(profile.get("candidate_sources") or []))
    return profiles


def _local_native_ground_truth_candidates(chain: str, limit: int, min_swaps: int, min_transfers: int) -> list[dict[str, Any]]:
    conn = _engine()._get_db()
    try:
        if not _table_exists(conn, "pair_tokens"):
            return []
        pair_columns = {row[1] for row in conn.execute("PRAGMA table_info(pair_tokens)").fetchall()}
        if not {"pool", "token0", "token1"}.issubset(pair_columns):
            return []

        stats: dict[str, dict[str, Any]] = {}

        def add_token(token: Any, quote_token: Any = None, pool: Any = None, **fields: Any) -> None:
            address = _clean_address(token)
            if not address:
                return
            quote = _clean_address(quote_token)
            symbol = str(fields.pop("token_symbol", "") or "").upper()
            row = stats.setdefault(
                address,
                {
                    "chain": chain,
                    "token_address": address,
                    "token_symbol": symbol or "UNKNOWN",
                    "pool_addresses": set(),
                    "quote_tokens": set(),
                    "swap_rows": 0,
                    "swap_txs": 0,
                    "swap_wallets": 0,
                    "transfer_rows": 0,
                    "transfer_wallets": 0,
                    "pair_occurrences": 0,
                    "first_seen_timestamp": None,
                    "last_seen_timestamp": None,
                    "candidate_sources": set(),
                },
            )
            if symbol and row["token_symbol"] == "UNKNOWN":
                row["token_symbol"] = symbol
            if pool:
                row["pool_addresses"].add(str(pool).lower())
            if quote:
                row["quote_tokens"].add(quote)
            for key in ("swap_rows", "swap_txs", "swap_wallets", "transfer_rows", "transfer_wallets", "pair_occurrences"):
                if key in fields:
                    row[key] += _as_int(fields[key])
            if fields.get("first_seen_timestamp"):
                current = _as_int(row.get("first_seen_timestamp"))
                candidate = _as_int(fields.get("first_seen_timestamp"))
                row["first_seen_timestamp"] = candidate if not current else min(current, candidate)
            if fields.get("last_seen_timestamp"):
                current = _as_int(row.get("last_seen_timestamp"))
                candidate = _as_int(fields.get("last_seen_timestamp"))
                row["last_seen_timestamp"] = max(current, candidate)
            if fields.get("candidate_source"):
                row["candidate_sources"].add(str(fields["candidate_source"]))

        symbols = _known_token_symbols_from_local_context(chain, [])
        if _table_exists(conn, "dex_raw_swap_events"):
            swap_rows = conn.execute(
                """
                SELECT lower(p.pool), lower(p.token0), lower(p.token1),
                       COUNT(e.id), COUNT(DISTINCT e.tx_hash),
                       COUNT(DISTINCT e.sender) + COUNT(DISTINCT e.recipient),
                       MIN(e.block_timestamp), MAX(e.block_timestamp)
                FROM pair_tokens p
                JOIN dex_raw_swap_events e
                  ON lower(e.chain)=lower(p.chain)
                 AND lower(e.pair_address)=lower(p.pool)
                WHERE lower(p.chain)=?
                GROUP BY lower(p.pool), lower(p.token0), lower(p.token1)
                ORDER BY COUNT(e.id) DESC
                LIMIT ?
                """,
                (chain, max(limit * 10, 100)),
            ).fetchall()
            for pool, token0, token1, swap_count, tx_count, wallet_count, first_ts, last_ts in swap_rows:
                quote_info = _quote_token_for_candidates(chain, token0, token1)
                target = quote_info["target_token"]
                quote = quote_info["quote_token"]
                add_token(
                    target,
                    quote,
                    pool,
                    swap_rows=swap_count,
                    swap_txs=tx_count,
                    swap_wallets=wallet_count,
                    first_seen_timestamp=first_ts,
                    last_seen_timestamp=last_ts,
                    candidate_source="dex_raw_swap_events",
                )

        pair_rows = conn.execute(
            """
            SELECT lower(pool), lower(token0), lower(token1), COUNT(*), MIN(observed_at), MAX(observed_at)
            FROM pair_tokens
            WHERE lower(chain)=?
            GROUP BY lower(pool), lower(token0), lower(token1)
            LIMIT ?
            """,
            (chain, max(limit * 20, 200)),
        ).fetchall()
        for pool, token0, token1, pair_count, first_ts, last_ts in pair_rows:
            quote_info = _quote_token_for_candidates(chain, token0, token1)
            add_token(
                quote_info["target_token"],
                quote_info["quote_token"],
                pool,
                pair_occurrences=pair_count,
                first_seen_timestamp=first_ts,
                last_seen_timestamp=last_ts,
                candidate_source="pair_tokens",
            )

        if _table_exists(conn, "token_transfers"):
            transfer_rows = conn.execute(
                """
                SELECT lower(token), COUNT(*),
                       COUNT(DISTINCT from_addr) + COUNT(DISTINCT to_addr),
                       MIN(timestamp), MAX(timestamp)
                FROM token_transfers
                WHERE lower(chain)=? AND token IS NOT NULL AND token != ''
                GROUP BY lower(token)
                ORDER BY COUNT(*) DESC
                LIMIT ?
                """,
                (chain, max(limit * 20, 200)),
            ).fetchall()
            for token, transfer_count, wallet_count, first_ts, last_ts in transfer_rows:
                add_token(
                    token,
                    None,
                    None,
                    transfer_rows=transfer_count,
                    transfer_wallets=wallet_count,
                    first_seen_timestamp=first_ts,
                    last_seen_timestamp=last_ts,
                    candidate_source="token_transfers",
                )

        all_addresses = list(stats)
        symbols = _known_token_symbols_from_local_context(chain, all_addresses)
        now_ts = int(time.time())
        rows: list[dict[str, Any]] = []
        existing_tokens = _existing_ground_truth_tokens(conn)
        for token, row in stats.items():
            symbol = str(symbols.get(token) or row.get("token_symbol") or "UNKNOWN").upper()
            infra = token in _BSC_INFRA_TOKEN_ADDRESSES or _is_infrastructure_symbol(symbol)
            known_positive = token in _KNOWN_POSITIVE_LISTING_TOKENS
            already_ground_truth = token in existing_tokens
            enough_local = _as_int(row.get("swap_rows")) >= min_swaps or _as_int(row.get("transfer_rows")) >= min_transfers
            first_seen = _as_int(row.get("first_seen_timestamp"))
            age_days = round((now_ts - first_seen) / 86_400, 2) if first_seen else None
            blockers = [
                *("infrastructure_token_excluded" for _ in [1] if infra),
                *("known_positive_seed_token_excluded" for _ in [1] if known_positive),
                *("already_in_ground_truth_dataset" for _ in [1] if already_ground_truth),
                *("insufficient_native_local_context" for _ in [1] if not enough_local),
            ]
            label_payload = {
                "token_address": token,
                "token_symbol": symbol,
                "coingecko_search_url": f"https://www.coingecko.com/en/search?query={token}",
                "honeypot_url": "https://api.honeypot.is/v2/IsHoneypot?" + urllib.parse.urlencode({"address": token, "chainID": _security_chain_id(chain) or ""}),
                "goplus_url": (
                    "https://api.gopluslabs.io/api/v1/token_security/"
                    + urllib.parse.quote(_security_chain_id(chain) or "")
                    + "?"
                    + urllib.parse.urlencode({"contract_addresses": token})
                ),
                "required_label_classes": [
                    "positive_native_cex_listing",
                    "documented_honeypot_or_scam_negative",
                    "organic_never_listed_negative",
                    "blocked_unclear",
                ],
            }
            native_score = (
                min(200, _as_int(row.get("swap_rows")))
                + min(100, _as_int(row.get("transfer_rows")))
                + min(50, _as_int(row.get("swap_wallets")) + _as_int(row.get("transfer_wallets")))
                + min(25, _as_int(row.get("pair_occurrences")) * 5)
            )
            rows.append({
                "chain": chain,
                "token_address": token,
                "token_symbol": symbol,
                "native_context_status": "labeling_candidate" if not blockers else "excluded",
                "native_context_score": native_score,
                "swap_rows": _as_int(row.get("swap_rows")),
                "swap_txs": _as_int(row.get("swap_txs")),
                "swap_wallets": _as_int(row.get("swap_wallets")),
                "transfer_rows": _as_int(row.get("transfer_rows")),
                "transfer_wallets": _as_int(row.get("transfer_wallets")),
                "pair_occurrences": _as_int(row.get("pair_occurrences")),
                "pool_addresses": sorted(row.get("pool_addresses") or []),
                "quote_tokens": sorted(row.get("quote_tokens") or []),
                "first_seen_timestamp": first_seen or None,
                "last_seen_timestamp": _as_int(row.get("last_seen_timestamp")) or None,
                "age_days": age_days,
                "candidate_sources": sorted(row.get("candidate_sources") or []),
                "labeling_payload": label_payload,
                "labeling_payload_digest": _digest(label_payload),
                "blockers": blockers,
            })
        rows = [row for row in rows if row["native_context_status"] == "labeling_candidate"]
        rows.sort(
            key=lambda row: (
                _as_int(row.get("native_context_score")),
                _as_int(row.get("swap_rows")),
                _as_int(row.get("transfer_rows")),
            ),
            reverse=True,
        )
        return rows[:limit]
    finally:
        conn.close()


def _quote_token_for_candidates(chain: str, token0: Any, token1: Any) -> dict[str, str]:
    clean0 = _clean_address(token0)
    clean1 = _clean_address(token1)
    infra = _BSC_INFRA_TOKEN_ADDRESSES if chain == "bsc" else set()
    if clean0 in infra and clean1:
        return {"quote_token": clean0, "target_token": clean1}
    if clean1 in infra and clean0:
        return {"quote_token": clean1, "target_token": clean0}
    return {"quote_token": clean0, "target_token": clean1 or clean0}


def _timestamp_from_rows(values: list[Any]) -> int | None:
    clean = [_as_int(value) for value in values if _as_int(value) > 0]
    if not clean:
        return None
    return min(clean)


def _tier2_cex_hint(deposits: list[dict[str, Any]]) -> dict[str, Any]:
    tier2_terms = ("gate", "mexc", "bitget", "kucoin")
    major_terms = ("binance", "okx", "coinbase", "kraken")
    labels: list[str] = []
    for row in deposits:
        labels.extend([
            str(row.get("target_entity") or ""),
            str(row.get("target_label") or ""),
            str(row.get("target_address_kind") or ""),
        ])
    text = " ".join(labels).lower()
    tier2_matches = sorted({term for term in tier2_terms if term in text})
    major_matches = sorted({term for term in major_terms if term in text})
    return {
        "tier2_hint": bool(tier2_matches),
        "tier2_matches": tier2_matches,
        "major_cex_matches": major_matches,
        "hint_policy": "tier2 hint is a research prior, not listing evidence",
    }


def get_manipulation_detection_cex_listing_probability_bridge_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    min_behavioral_score: int = 50,
    cex_deposit_limit: int = 100,
    token_addresses: list[str] | str | None = None,
) -> dict[str, Any]:
    """Read-only bridge between behavioral accumulation hints and CEX token-deposit flow."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_min_score = max(1, min(int(min_behavioral_score or 50), 100))
    safe_cex_limit = max(1, min(int(cex_deposit_limit or 100), 200))
    explicit_tokens = _parse_token_addresses(token_addresses)
    source_policy = (
        "admin-only read-only CEX listing probability bridge. It joins local behavioral anomaly previews "
        "with local token transfers into source-backed/exchange-like CEX wallets. It is a research priority "
        "score only: not listing proof, not a client signal, not a trade, not a mapping and not a persisted score."
    )
    disabled = {
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "bridge_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    scoring = get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        token_addresses=explicit_tokens,
    )
    intent = get_manipulation_detection_top_expansion_directional_intent_classifier_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_behavioral_score=safe_min_score,
    )
    stealth = get_manipulation_detection_stealth_accumulation_anomaly_scan_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        max_pools=max(clean_limit, 50),
        max_circularity_pct=30.0,
        min_hold_freeze_proxy_pct=70.0,
        min_buy_flows=3,
        token_addresses=explicit_tokens,
    )
    cex_deposits = _engine().get_token_transfer_cex_deposit_scan(
        chain=clean_chain,
        limit=safe_cex_limit,
        token_addresses=explicit_tokens,
    )

    deposit_rows = list(cex_deposits.get("rows") or [])
    deposits_by_token: dict[str, list[dict[str, Any]]] = {}
    for row in deposit_rows:
        token = _clean_address(row.get("token"))
        if token:
            deposits_by_token.setdefault(token, []).append(row)

    intent_by_pool = {
        _clean_address(row.get("pool_address")): row
        for row in list(intent.get("candidates") or [])
        if _clean_address(row.get("pool_address"))
    }
    stealth_by_pool = {
        _clean_address(row.get("pool_address")): row
        for row in list(stealth.get("candidates") or [])
        if _clean_address(row.get("pool_address"))
    }
    cex_summary = dict(cex_deposits.get("summary") or {})
    global_shared_funders = _as_int(cex_summary.get("shared_funders"))

    candidates: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    for scored in list(scoring.get("candidates") or []):
        behavior_score = _as_int(scored.get("behavioral_anomaly_score"))
        if behavior_score < safe_min_score:
            continue
        pool = _clean_address(scored.get("pool_address"))
        intent_row = intent_by_pool.get(pool, {})
        stealth_row = stealth_by_pool.get(pool, {})
        token = (
            _clean_address(scored.get("target_token"))
            or _clean_address(intent_row.get("target_token"))
            or _clean_address(stealth_row.get("target_token"))
        )
        if not token:
            continue
        seen_tokens.add(token)
        token_deposits = deposits_by_token.get(token, [])
        fresh_like_depositors = {
            str(row.get("from_addr") or "").lower()
            for row in token_deposits
            if row.get("depositor_fresh_like") and row.get("from_addr")
        }
        target_wallets = {
            str(row.get("to_addr") or "").lower()
            for row in token_deposits
            if row.get("to_addr")
        }
        source_backed_targets = {
            str(row.get("to_addr") or "").lower()
            for row in token_deposits
            if row.get("target_source_backed") and row.get("to_addr")
        }
        tier2_hint = _tier2_cex_hint(token_deposits)
        intent_classifier = dict(intent_row.get("intent_classifier") or {})
        shared_funder_proxy = global_shared_funders if token_deposits else 0
        listing_score = int(min(100, round(
            behavior_score * 0.30
            + len(fresh_like_depositors) * 8
            + shared_funder_proxy * 12
            + len(token_deposits) * 15
            + (20 if tier2_hint.get("tier2_hint") else 0)
        )))
        evidence_factors = [
            "behavioral_anomaly_score",
            *("matching_cex_token_deposits" for _ in [1] if token_deposits),
            *("fresh_like_cex_depositors" for _ in [1] if fresh_like_depositors),
            *("shared_funder_proxy_from_cex_deposit_scan" for _ in [1] if shared_funder_proxy),
            *("tier2_cex_hint" for _ in [1] if tier2_hint.get("tier2_hint")),
            *("stealth_accumulation_candidate" for _ in [1] if stealth_row),
        ]
        blockers = list(dict.fromkeys([
            *("no_matching_cex_deposit_for_behavioral_token" for _ in [1] if not token_deposits),
            *("no_fresh_like_cex_depositor_for_token" for _ in [1] if not fresh_like_depositors),
            *("no_shared_funder_token_specific_proof" for _ in [1] if not shared_funder_proxy),
            *("cex_target_source_backing_incomplete" for _ in [1] if token_deposits and len(source_backed_targets) < len(target_wallets)),
            "listing_calendar_backtest_missing",
            "cex_announcement_ground_truth_missing",
            "not_listing_proof",
            "client_signal_disabled",
            "trade_disabled",
        ]))
        candidates.append({
            "chain": clean_chain,
            "pool_address": pool,
            "token_address": token,
            "token_symbol": scored.get("target_symbol") or intent_row.get("target_symbol") or stealth_row.get("target_symbol"),
            "behavioral_anomaly_score": behavior_score,
            "behavioral_anomaly_tier": scored.get("behavioral_anomaly_tier"),
            "intent_classification": intent_classifier.get("intent_classification"),
            "hold_freeze_proxy_pct": (intent_classifier.get("hold_freeze_proxy") or {}).get("hold_freeze_proxy_pct"),
            "circularity_ratio_pct": (intent_classifier.get("circularity") or {}).get("circularity_ratio_pct"),
            "cex_deposit_signal": {
                "matching_deposits": len(token_deposits),
                "fresh_like_depositors": len(fresh_like_depositors),
                "target_exchange_wallets": len(target_wallets),
                "source_backed_target_wallets": len(source_backed_targets),
                "shared_funders_proxy": shared_funder_proxy,
                "tier2_hint": tier2_hint,
            },
            "listing_probability_score": listing_score,
            "listing_probability_tier": _listing_tier(listing_score),
            "evidence_factors": evidence_factors,
            "blockers": blockers,
            "next_safe_step": (
                "listing_calendar_backtest_read_only"
                if listing_score >= 50 and token_deposits else
                "collect_or_repair_token_specific_cex_deposit_context_read_only"
            ),
            "client_signal_ready": False,
            "trade_ready": False,
        })

    # Also expose CEX-only tokens that do not yet match behavioral candidates.
    cex_only: list[dict[str, Any]] = []
    for token, token_deposits in deposits_by_token.items():
        if token in seen_tokens:
            continue
        if len(cex_only) >= clean_limit:
            break
        fresh_like = sum(1 for row in token_deposits if row.get("depositor_fresh_like"))
        tier2_hint = _tier2_cex_hint(token_deposits)
        cex_only.append({
            "token_address": token,
            "token_symbol": next((row.get("token_symbol") for row in token_deposits if row.get("token_symbol")), None),
            "matching_deposits": len(token_deposits),
            "fresh_like_depositors": fresh_like,
            "tier2_hint": tier2_hint,
            "reason": "cex_deposit_flow_without_current_behavioral_candidate",
            "next_safe_step": "behavioral_context_lookup_for_cex_deposit_token_read_only",
        })

    candidates.sort(
        key=lambda row: (
            _as_int(row.get("listing_probability_score")),
            _as_int(row.get("behavioral_anomaly_score")),
        ),
        reverse=True,
    )
    high_priority = [row for row in candidates if row.get("listing_probability_tier") == "high_listing_research_priority"]
    medium_priority = [row for row in candidates if row.get("listing_probability_tier") == "medium_listing_research_priority"]
    bridge_digest = _digest({
        "chain": clean_chain,
        "min_behavioral_score": safe_min_score,
        "candidate_scores": [
            {
                "pool": row.get("pool_address"),
                "token": row.get("token_address"),
                "score": row.get("listing_probability_score"),
                "tier": row.get("listing_probability_tier"),
            }
            for row in candidates[:clean_limit]
        ],
        "cex_only_tokens": [
            {
                "token": row.get("token_address"),
                "deposits": row.get("matching_deposits"),
            }
            for row in cex_only[:clean_limit]
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "bridge_status": "ready_but_disabled",
        "chain": clean_chain,
        "token_addresses": explicit_tokens,
        "explicit_token_filter": bool(explicit_tokens),
        "cex_listing_probability_bridge_digest": bridge_digest,
        "formula": {
            "behavioral_score_weight": "behavioral_anomaly_score * 0.30",
            "fresh_like_depositors_weight": "fresh_like_depositors * 8",
            "shared_funders_weight": "shared_funders_proxy * 12",
            "cex_deposit_count_weight": "matching_deposits * 15",
            "tier2_cex_hint_weight": "20 if Gate/MEXC/Bitget/KuCoin hint",
            "cap": 100,
            "policy": "research priority score only; not listing proof",
        },
        "behavioral_snapshot": {
            "summary": scoring.get("summary"),
            "intent_summary": intent.get("summary"),
            "stealth_summary": stealth.get("summary"),
        },
        "cex_deposit_snapshot": {
            "summary": cex_summary,
            "temporal_profile": cex_deposits.get("temporal_profile"),
            "funding_graph_summary": (cex_deposits.get("funding_graph") or {}).get("summary"),
            "source_policy": cex_deposits.get("source_policy"),
        },
        "candidates": candidates[:clean_limit],
        "cex_deposit_only_candidates": cex_only[:clean_limit],
        "summary": {
            "behavioral_candidates_checked": len(candidates),
            "explicit_tokens_checked": len(explicit_tokens),
            "candidates_with_matching_cex_deposits": sum(1 for row in candidates if (row.get("cex_deposit_signal") or {}).get("matching_deposits")),
            "high_listing_research_priority": len(high_priority),
            "medium_listing_research_priority": len(medium_priority),
            "cex_deposit_only_tokens": len(cex_only),
            "can_predict_listing_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *("no_behavioral_candidates_above_threshold" for _ in [1] if not candidates),
            *("explicit_tokens_not_found_in_behavioral_candidates" for _ in [1] if explicit_tokens and not any(row.get("token_address") in explicit_tokens for row in candidates)),
            *("no_behavioral_candidate_with_matching_cex_deposit" for _ in [1] if candidates and not any((row.get("cex_deposit_signal") or {}).get("matching_deposits") for row in candidates)),
            "listing_calendar_backtest_missing",
            "cex_announcement_ground_truth_missing",
            "token_specific_shared_funder_proof_missing",
            "not_listing_proof",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "listing_calendar_backtest_read_only"
            if high_priority or medium_priority else
            "cex_listing_ground_truth_dataset_plan_read_only"
        ),
        "plain_summary_fr": (
            "Ce pont teste l'hypothese Qwen: accumulation comportementale + flux vers CEX pourrait predire "
            "un futur listing. Ici, le score reste une priorite de recherche, pas une preuve de listing ni un signal."
        ),
        **disabled,
    }


def get_manipulation_detection_cex_listing_negative_cohort_discovery_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    min_behavioral_score: int = 20,
    min_age_days: int = 90,
) -> dict[str, Any]:
    """Read-only local discovery of potential negative listing cohort candidates."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_min_score = max(1, min(int(min_behavioral_score or 20), 100))
    safe_min_age_days = max(1, min(int(min_age_days or 90), 3650))
    now_ts = int(time.time())
    min_age_seconds = safe_min_age_days * 86_400
    source_policy = (
        "admin-only read-only CEX listing negative cohort discovery. It reads local behavioral previews, "
        "raw swap/transfer tables and the existing ground-truth dataset only. It does not call providers, "
        "does not scrape, does not insert negative rows, and does not create listing/client signals or trades."
    )
    disabled = {
        "would_insert_ground_truth_rows": False,
        "would_call_provider": False,
        "would_scrape": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "discovery_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    bridge = get_manipulation_detection_cex_listing_probability_bridge_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_behavioral_score=safe_min_score,
        cex_deposit_limit=200,
    )
    positive_tokens = {
        "0x7ec43cf65f1663f820427c62a5780b8f2e25593a",
        "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
        "0x9eca8dedb4882bd694aea786c0cbe770e70d52e3",
    }
    conn = _engine()._get_db()
    conn.row_factory = None
    candidates: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        existing_ground_truth_tokens = set()
        if _table_exists(conn, "cex_listing_ground_truth_dataset"):
            existing_ground_truth_tokens = {
                str(row[0] or "").lower()
                for row in conn.execute("SELECT token_address FROM cex_listing_ground_truth_dataset").fetchall()
            }
        for row in list(bridge.get("candidates") or []):
            token = _clean_address(row.get("token_address"))
            if not token or token in positive_tokens:
                continue
            pool = _clean_address(row.get("pool_address"))
            timestamps: list[Any] = []
            raw_swap_count = 0
            transfer_count = 0
            if pool and _table_exists(conn, "dex_raw_swap_events"):
                raw = conn.execute(
                    """
                    SELECT MIN(block_timestamp), MAX(block_timestamp), COUNT(*)
                    FROM dex_raw_swap_events
                    WHERE lower(chain)=? AND lower(pair_address)=?
                    """,
                    (clean_chain, pool),
                ).fetchone()
                timestamps.extend([raw[0], raw[1]])
                raw_swap_count = _as_int(raw[2])
            if _table_exists(conn, "token_transfers"):
                transfers = conn.execute(
                    """
                    SELECT MIN(timestamp), MAX(timestamp), COUNT(*)
                    FROM token_transfers
                    WHERE lower(chain)=? AND lower(token)=?
                    """,
                    (clean_chain, token),
                ).fetchone()
                timestamps.extend([transfers[0], transfers[1]])
                transfer_count = _as_int(transfers[2])
            first_seen_ts = _timestamp_from_rows(timestamps)
            age_days = round((now_ts - first_seen_ts) / 86_400, 2) if first_seen_ts else None
            listing_score = _as_int(row.get("listing_probability_score"))
            cex_deposits = _as_int((row.get("cex_deposit_signal") or {}).get("matching_deposits"))
            candidate_blockers = [
                *("already_in_ground_truth_dataset" for _ in [1] if token in existing_ground_truth_tokens),
                *("too_recent_for_never_listed_90d" for _ in [1] if age_days is None or age_days < safe_min_age_days),
                *("no_matching_cex_deposit_context" for _ in [1] if cex_deposits < 1),
                *("low_listing_probability_score_for_negative_control" for _ in [1] if listing_score < safe_min_score),
                "external_no_listing_verification_required",
                "absence_of_search_result_is_not_proof",
            ]
            candidate_status = (
                "external_verification_required"
                if age_days is not None
                and age_days * 86_400 >= min_age_seconds
                and cex_deposits >= 1
                else "blocked_not_admissible_negative_yet"
            )
            candidates.append({
                "chain": clean_chain,
                "token_address": token,
                "token_symbol": row.get("token_symbol"),
                "pool_address": pool,
                "listing_probability_score": listing_score,
                "behavioral_anomaly_score": row.get("behavioral_anomaly_score"),
                "intent_classification": row.get("intent_classification"),
                "cex_deposit_signal": row.get("cex_deposit_signal"),
                "first_seen_timestamp": first_seen_ts,
                "age_days": age_days,
                "raw_swap_rows": raw_swap_count,
                "token_transfer_rows": transfer_count,
                "negative_candidate_status": candidate_status,
                "negative_row_allowed_now": False,
                "suggested_negative_listing_tier": "negative_never_listed_90d",
                "required_external_checks": [
                    "CoinGecko contract markets no CEX market or explicit not found",
                    "search official CEX announcements for token address/symbol",
                    "document checked_at timestamp and source digest",
                    "do not use if token is younger than min_age_days",
                ],
                "blockers": list(dict.fromkeys(candidate_blockers)),
            })
    finally:
        conn.close()

    ready_for_external = [
        row for row in candidates
        if row.get("negative_candidate_status") == "external_verification_required"
    ]
    blockers.extend([
        *("no_local_candidate_ready_for_negative_external_verification" for _ in [1] if not ready_for_external),
        "negative_rows_not_inserted",
        "manual_or_bounded_external_verification_required",
        "client_signal_disabled",
        "trade_disabled",
    ])
    return {
        "ok": True,
        "dry_run": True,
        "discovery_status": "ready_but_disabled",
        "chain": clean_chain,
        "min_behavioral_score": safe_min_score,
        "min_age_days": safe_min_age_days,
        "bridge_snapshot": {
            "summary": bridge.get("summary"),
            "blockers": bridge.get("blockers"),
        },
        "candidates": candidates[:clean_limit],
        "summary": {
            "local_candidates_checked": len(candidates),
            "ready_for_external_verification": len(ready_for_external),
            "negative_rows_allowed_now": 0,
            "too_recent_candidates": sum(
                1 for item in candidates
                if "too_recent_for_never_listed_90d" in list(item.get("blockers") or [])
            ),
            "can_backtest_listing_bridge_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "bounded_external_negative_verification_read_only"
            if ready_for_external else
            "collect_older_or_more_cex_like_behavioral_candidates_read_only"
        ),
        "plain_summary_fr": (
            "Cette lane cherche des negatifs sans tricher. Elle ne transforme jamais une absence de resultat web "
            "en preuve: il faut des candidats assez ages, un contexte CEX-like, puis une verification externe bornee."
        ),
        **disabled,
    }


def get_manipulation_detection_external_scam_negative_intake_preview(
    chain: str | None = "bsc",
    token_addresses: list[str] | str | None = None,
    limit: int = 20,
    dry_run: bool = True,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Read-only bounded security-API preview for documented scam negative controls."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 20), 50))
    safe_timeout = max(1, min(int(timeout_seconds or 10), 30))
    chain_id = _security_chain_id(clean_chain)
    source_policy = (
        "admin-only read-only external scam negative intake preview. It performs bounded security API "
        "lookups against explicit/local candidate token addresses to find documented honeypot/scam "
        "negative controls for CEX listing bridge backtests. Scam negatives are not organic never-listed "
        "negatives and cannot prove absence of future listings by themselves."
    )
    disabled = {
        "would_insert_ground_truth_rows": False,
        "would_call_unbounded_provider": False,
        "would_scrape": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "intake_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            "preview_ground_truth_rows": [],
            **disabled,
        }
    if not chain_id:
        return {
            "ok": False,
            "dry_run": True,
            "intake_status": "blocked",
            "chain": clean_chain,
            "blockers": ["unsupported_security_api_chain"],
            "candidates": [],
            "preview_ground_truth_rows": [],
            **disabled,
        }

    explicit_addresses = _parse_token_addresses(token_addresses)
    bridge = get_manipulation_detection_cex_listing_probability_bridge_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_behavioral_score=20,
        cex_deposit_limit=200,
    )
    candidate_addresses = list(explicit_addresses)
    if not candidate_addresses:
        candidate_addresses = _parse_token_addresses([
            row.get("token_address")
            for row in list(bridge.get("candidates") or [])[:clean_limit]
        ])
    candidate_addresses = candidate_addresses[:clean_limit]
    symbols = _known_token_symbols_from_local_context(clean_chain, candidate_addresses)
    for row in list(bridge.get("candidates") or []):
        token = _clean_address(row.get("token_address"))
        if token and row.get("token_symbol"):
            symbols.setdefault(token, str(row.get("token_symbol")).upper())

    candidates: list[dict[str, Any]] = []
    preview_rows: list[dict[str, Any]] = []
    for token in candidate_addresses:
        honeypot_url = (
            "https://api.honeypot.is/v2/IsHoneypot?"
            + urllib.parse.urlencode({"address": token, "chainID": chain_id})
        )
        goplus_url = (
            "https://api.gopluslabs.io/api/v1/token_security/"
            + urllib.parse.quote(chain_id)
            + "?"
            + urllib.parse.urlencode({"contract_addresses": token})
        )
        source_results: dict[str, Any] = {}
        errors: list[str] = []
        if use_honeypot:
            try:
                source_results["honeypot"] = {
                    "source_url": honeypot_url,
                    "payload": _http_json(honeypot_url, safe_timeout),
                }
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                errors.append(f"honeypot_lookup_failed:{type(exc).__name__}")
        if use_goplus:
            try:
                source_results["goplus"] = {
                    "source_url": goplus_url,
                    "payload": _http_json(goplus_url, safe_timeout),
                }
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                errors.append(f"goplus_lookup_failed:{type(exc).__name__}")

        hp_payload = ((source_results.get("honeypot") or {}).get("payload") or {})
        hp_result = hp_payload.get("honeypotResult") or {}
        honeypot_detected = bool(hp_result.get("isHoneypot") or hp_payload.get("isHoneypot"))
        gp_payload = ((source_results.get("goplus") or {}).get("payload") or {})
        gp_result_map = gp_payload.get("result") or {}
        gp_result = gp_result_map.get(token) or gp_result_map.get(token.lower()) or gp_result_map.get(token.upper()) or {}
        goplus_honeypot = str(gp_result.get("is_honeypot") or "").strip() == "1"
        documented_negative = honeypot_detected or goplus_honeypot
        listing_tier = (
            "documented_honeypot_never_listed"
            if honeypot_detected or goplus_honeypot
            else "documented_scam_never_listed"
        )
        payload = {
            "chain": clean_chain,
            "token_address": token,
            "security_sources": source_results,
            "classification": {
                "honeypot_detected": honeypot_detected,
                "goplus_honeypot": goplus_honeypot,
                "goplus_is_open_source": gp_result.get("is_open_source"),
                "goplus_buy_tax": gp_result.get("buy_tax"),
                "goplus_sell_tax": gp_result.get("sell_tax"),
                "policy": "documented scam negative control only; not organic never-listed proof",
            },
            "errors": errors,
        }
        digest = _digest(payload)
        source_url = (
            ((source_results.get("honeypot") or {}).get("source_url"))
            or ((source_results.get("goplus") or {}).get("source_url"))
            or honeypot_url
        )
        preview_row = {
            "chain": clean_chain,
            "token_address": token,
            "token_symbol": symbols.get(token) or "UNKNOWN",
            "cex_name": "NONE",
            "market_pair": "NONE",
            "announcement_url": source_url,
            "announcement_at": None,
            "listing_at": None,
            "listing_tier": listing_tier,
            "source_tier": "security_api",
            "source_digest": digest,
            "source_excerpt_digest": digest,
            "payload_json": payload,
            "source_policy": source_policy,
        }
        normalized, row_blockers = _normalize_ground_truth_row(preview_row, clean_chain)
        row_eligible = bool(documented_negative and not row_blockers)
        if row_eligible:
            preview_rows.append(normalized)
        candidate_blockers = [
            *("not_documented_as_honeypot_or_scam_by_enabled_sources" for _ in [1] if not documented_negative),
            *row_blockers,
            *errors,
            "scam_negative_is_not_organic_negative_control",
        ]
        candidates.append({
            "chain": clean_chain,
            "token_address": token,
            "token_symbol": preview_row["token_symbol"],
            "candidate_status": "documented_scam_negative_ready_for_intake_preview" if row_eligible else "blocked",
            "documented_negative": documented_negative,
            "honeypot_detected": honeypot_detected,
            "goplus_honeypot": goplus_honeypot,
            "source_digest": digest,
            "source_urls": {
                "honeypot": honeypot_url if use_honeypot else None,
                "goplus": goplus_url if use_goplus else None,
            },
            "preview_ground_truth_row": normalized if row_eligible else None,
            "blockers": list(dict.fromkeys(candidate_blockers)),
        })

    blockers = [
        *("token_addresses_or_local_candidates_required" for _ in [1] if not candidate_addresses),
        *("no_security_sources_enabled" for _ in [1] if not use_honeypot and not use_goplus),
        *("no_documented_scam_negative_found" for _ in [1] if candidate_addresses and not preview_rows),
        "organic_negative_cohort_still_required_for_final_backtest",
        "negative_rows_not_inserted",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "intake_status": "ready_but_disabled" if preview_rows else "blocked",
        "chain": clean_chain,
        "security_chain_id": chain_id,
        "limit": clean_limit,
        "timeout_seconds": safe_timeout,
        "enabled_sources": {
            "honeypot": bool(use_honeypot),
            "goplus": bool(use_goplus),
        },
        "bridge_snapshot": {
            "summary": bridge.get("summary"),
            "blockers": bridge.get("blockers"),
        },
        "candidates": candidates,
        "preview_ground_truth_rows": preview_rows,
        "expected_dedupe_keys_if_inserted_later": [row.get("dedupe_key") for row in preview_rows],
        "documented_scam_negative_rows": len(preview_rows),
        "summary": {
            "tokens_checked": len(candidate_addresses),
            "documented_scam_negative_rows": len(preview_rows),
            "scam_negative_ready_for_ground_truth_intake": bool(preview_rows),
            "organic_negative_rows_still_missing": True,
            "can_backtest_listing_bridge_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "cex_listing_ground_truth_dataset_insert_dry_run_with_positive_and_scam_negative_rows"
            if preview_rows else
            "expand_security_negative_candidate_scope_or_collect_older_local_candidates"
        ),
        "plain_summary_fr": (
            "Cette lane suit le pivot Qwen: utiliser des scams/honeypots documentes comme negatifs forts. "
            "C'est utile pour tester le bridge, mais ce n'est pas encore le negatif organique final."
        ),
        **disabled,
    }


def get_manipulation_detection_documented_scam_negative_candidate_scope_expansion_preview(
    chain: str | None = "bsc",
    limit: int = 20,
    dry_run: bool = True,
    max_scan_rows: int = 500,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Read-only local candidate expansion followed by bounded security negative preview."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 20), 50))
    safe_max_scan_rows = max(10, min(int(max_scan_rows or 500), 5_000))
    safe_timeout = max(1, min(int(timeout_seconds or 10), 30))
    source_policy = (
        "admin-only read-only documented scam negative candidate scope expansion. It selects local token "
        "candidates from bridge, transfer and pair context, excludes infrastructure/known positives, then "
        "runs only bounded Honeypot.is/GoPlus probes through the existing external scam intake preview."
    )
    disabled = {
        "would_insert_ground_truth_rows": False,
        "would_call_unbounded_provider": False,
        "would_scrape": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "scope_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidate_scope": [],
            **disabled,
        }

    candidate_scope = _local_scam_negative_candidate_scope(
        clean_chain,
        clean_limit,
        safe_max_scan_rows,
    )
    token_addresses = [row["token_address"] for row in candidate_scope]
    intake = get_manipulation_detection_external_scam_negative_intake_preview(
        chain=clean_chain,
        token_addresses=token_addresses,
        limit=clean_limit,
        dry_run=True,
        use_honeypot=use_honeypot,
        use_goplus=use_goplus,
        timeout_seconds=safe_timeout,
    )
    documented_rows = list(intake.get("preview_ground_truth_rows") or [])
    blockers = [
        *("no_local_candidate_scope_selected" for _ in [1] if not candidate_scope),
        *("no_documented_scam_negative_found" for _ in [1] if candidate_scope and not documented_rows),
        "scam_negatives_are_not_organic_never_listed_negatives",
        "ground_truth_rows_not_inserted",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "scope_status": "ready_but_disabled" if documented_rows else "blocked",
        "chain": clean_chain,
        "limit": clean_limit,
        "max_scan_rows": safe_max_scan_rows,
        "candidate_scope": candidate_scope,
        "selected_token_addresses": token_addresses,
        "security_intake": {
            "intake_status": intake.get("intake_status"),
            "documented_scam_negative_rows": intake.get("documented_scam_negative_rows"),
            "blockers": intake.get("blockers"),
            "summary": intake.get("summary"),
        },
        "preview_ground_truth_rows": documented_rows,
        "expected_dedupe_keys_if_inserted_later": intake.get("expected_dedupe_keys_if_inserted_later") or [],
        "summary": {
            "local_candidates_selected": len(candidate_scope),
            "tokens_checked_by_security_api": (intake.get("summary") or {}).get("tokens_checked", 0),
            "documented_scam_negative_rows": len(documented_rows),
            "organic_negative_rows_still_missing": True,
            "can_backtest_listing_bridge_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "cex_listing_ground_truth_seed_insert_dry_run_with_positive_and_scam_negative_rows"
            if documented_rows else
            "expand_local_candidate_collection_or_provide_known_scam_addresses_read_only"
        ),
        "plain_summary_fr": (
            "On elargit le radar de negatifs scams sans ecrire: selection locale bornee, verification securite "
            "Honeypot/GoPlus, puis rows preview seulement si une preuve scam/honeypot existe."
        ),
        **disabled,
    }


def get_manipulation_detection_cex_listing_ground_truth_seed_coherence_checkpoint(
    chain: str | None = "bsc",
    dry_run: bool = True,
    negative_limit: int = 20,
    max_scan_rows: int = 500,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
    allow_exploratory_majority_context: bool = False,
    token_addresses: list[str] | str | None = None,
) -> dict[str, Any]:
    """Read-only coherence checkpoint before CEX listing ground-truth seed intake."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_negative_limit = max(1, min(int(negative_limit or 20), 50))
    safe_max_scan_rows = max(10, min(int(max_scan_rows or 500), 5_000))
    safe_timeout = max(1, min(int(timeout_seconds or 10), 30))
    explicit_tokens = _parse_token_addresses(token_addresses)
    source_policy = (
        "admin-only read-only CEX listing ground-truth seed coherence checkpoint. It compares "
        "positive CEX listing seed rows with documented scam/honeypot negative rows before any "
        "ground-truth insert. It may perform bounded security API checks through the existing preview "
        "but it creates no rows, no signal and no trade."
    )
    disabled = {
        "would_insert_ground_truth_rows": False,
        "would_call_unbounded_provider": False,
        "would_scrape": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "coherence_status": "blocked",
            "blockers": ["dry_run_required"],
            **disabled,
        }

    positive_rows: list[dict[str, Any]] = []
    positive_blockers: list[str] = []
    for idx, row in enumerate(_positive_seed_ground_truth_rows(clean_chain)):
        normalized, row_blockers = _normalize_ground_truth_row(row, clean_chain)
        normalized["seed_role"] = "positive_listing"
        normalized["row_blockers"] = row_blockers
        positive_rows.append(normalized)
        positive_blockers.extend([f"positive_row_{idx}_{blocker}" for blocker in row_blockers])

    negative_scope = get_manipulation_detection_documented_scam_negative_candidate_scope_expansion_preview(
        chain=clean_chain,
        limit=clean_negative_limit,
        dry_run=True,
        max_scan_rows=safe_max_scan_rows,
        use_honeypot=use_honeypot,
        use_goplus=use_goplus,
        timeout_seconds=safe_timeout,
    )
    negative_rows = list(negative_scope.get("preview_ground_truth_rows") or [])[:3]
    for row in negative_rows:
        row["seed_role"] = "documented_scam_negative"

    bridge = get_manipulation_detection_cex_listing_probability_bridge_preview(
        chain=clean_chain,
        limit=50,
        dry_run=True,
        min_behavioral_score=20,
        cex_deposit_limit=200,
        token_addresses=explicit_tokens or None,
    )
    all_tokens = [row["token_address"] for row in positive_rows + negative_rows if row.get("token_address")]
    profiles = _local_token_context_profiles(
        clean_chain,
        all_tokens,
        bridge_candidates=list(bridge.get("candidates") or []),
        scope_candidates=list(negative_scope.get("candidate_scope") or []),
    )

    def group_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        token_profiles = [profiles.get(row["token_address"], {}) for row in rows if row.get("token_address")]
        if not token_profiles:
            return {
                "rows": 0,
                "avg_behavioral_score": 0,
                "avg_listing_probability_score": 0,
                "avg_transfer_rows": 0,
                "avg_pair_occurrences": 0,
                "with_local_context": 0,
                "with_cex_deposit_context": 0,
            }
        return {
            "rows": len(token_profiles),
            "avg_behavioral_score": round(sum(_as_int(row.get("behavioral_score")) for row in token_profiles) / len(token_profiles), 2),
            "avg_listing_probability_score": round(sum(_as_int(row.get("listing_probability_score")) for row in token_profiles) / len(token_profiles), 2),
            "avg_transfer_rows": round(sum(_as_int(row.get("transfer_rows")) for row in token_profiles) / len(token_profiles), 2),
            "avg_pair_occurrences": round(sum(_as_int(row.get("pair_occurrences")) for row in token_profiles) / len(token_profiles), 2),
            "with_local_context": sum(1 for row in token_profiles if row.get("local_context_status") == "local_context_present"),
            "with_cex_deposit_context": sum(1 for row in token_profiles if _as_int(row.get("cex_deposit_count")) > 0),
        }

    seed_rows = positive_rows + negative_rows
    seed_preview = insert_manipulation_detection_cex_listing_ground_truth_rows(
        rows=seed_rows,
        chain=clean_chain,
        dry_run=True,
    ) if seed_rows else {"insert_status": "blocked", "blockers": ["seed_rows_missing"]}
    positive_stats = group_stats(positive_rows)
    negative_stats = group_stats(negative_rows)
    positive_missing_local = [
        row["token_address"]
        for row in positive_rows
        if (profiles.get(row["token_address"]) or {}).get("local_context_status") != "local_context_present"
    ]
    negative_missing_local = [
        row["token_address"]
        for row in negative_rows
        if (profiles.get(row["token_address"]) or {}).get("local_context_status") != "local_context_present"
    ]
    blockers = [
        *positive_blockers,
        *("positive_seed_rows_missing" for _ in [1] if len(positive_rows) < 3),
        *("documented_scam_negative_rows_below_3" for _ in [1] if len(negative_rows) < 3),
        *("positive_seed_local_behavioral_context_missing" for _ in [1] if positive_missing_local),
        *("negative_seed_local_context_missing" for _ in [1] if negative_missing_local),
        *("seed_intake_preview_blocked" for _ in [1] if seed_preview.get("insert_status") != "ready_but_disabled"),
        "organic_negative_rows_still_required_for_final_backtest",
        "seed_rows_not_inserted",
        "client_signal_disabled",
        "trade_disabled",
    ]
    seed_shape_ready = (
        len(positive_rows) == 3
        and len(negative_rows) == 3
        and seed_preview.get("insert_status") == "ready_but_disabled"
    )
    positive_local_count = _as_int(positive_stats.get("with_local_context"))
    negative_local_count = _as_int(negative_stats.get("with_local_context"))
    exploratory_majority_ready = (
        bool(allow_exploratory_majority_context)
        and seed_shape_ready
        and len(positive_rows) >= 3
        and positive_local_count >= 2
        and len(negative_rows) >= 3
        and negative_local_count >= 3
    )
    backtest_ready = seed_shape_ready and not positive_missing_local and not negative_missing_local
    return {
        "ok": True,
        "dry_run": True,
        "coherence_status": (
            "ready_for_seed_insert_dry_run" if seed_shape_ready else "blocked"
        ),
        "backtest_homogeneity_status": (
            "ready_for_shadow_backtest_design" if backtest_ready else
            "ready_for_exploratory_shadow_backtest_with_limits" if exploratory_majority_ready else
            "blocked_missing_comparable_local_context"
        ),
        "chain": clean_chain,
        "token_addresses": explicit_tokens,
        "explicit_filter": bool(explicit_tokens),
        "positive_rows": positive_rows,
        "negative_rows": negative_rows,
        "seed_rows": seed_rows,
        "profiles_by_token": profiles,
        "metrics_comparison": {
            "positive_seed": positive_stats,
            "documented_scam_negative": negative_stats,
            "exploratory_majority_context": {
                "enabled": bool(allow_exploratory_majority_context),
                "ready": exploratory_majority_ready,
                "positive_local_context_required": "at least 2 of 3 positive rows",
                "negative_local_context_required": "at least 3 documented scam negative rows",
                "limitations": [
                    "exploratory only; not a final statistical backtest",
                    "LONG remains missing local context",
                    "scam negatives are not organic never-listed negatives",
                    "small sample and no client/trade decision allowed",
                ],
            },
            "interpretation": (
                "Seed shape can be tested if insert preview is ready, but backtest claims need comparable local "
                "behavioral/CEX context for both groups."
            ),
        },
        "positive_missing_local_context": positive_missing_local,
        "negative_missing_local_context": negative_missing_local,
        "negative_scope_snapshot": {
            "scope_status": negative_scope.get("scope_status"),
            "summary": negative_scope.get("summary"),
            "blockers": negative_scope.get("blockers"),
        },
        "seed_intake_preview": {
            "insert_status": seed_preview.get("insert_status"),
            "input_rows": seed_preview.get("input_rows"),
            "eligible_rows": seed_preview.get("eligible_rows"),
            "positive_rows": seed_preview.get("positive_rows"),
            "negative_rows": seed_preview.get("negative_rows"),
            "expected_dedupe_keys_required_for_real": seed_preview.get("expected_dedupe_keys_required_for_real"),
            "would_insert_ground_truth_rows": seed_preview.get("would_insert_ground_truth_rows"),
            "row_count_before": seed_preview.get("row_count_before"),
            "row_count_after": seed_preview.get("row_count_after"),
            "blockers": seed_preview.get("blockers"),
        },
        "summary": {
            "positive_rows": len(positive_rows),
            "negative_rows": len(negative_rows),
            "seed_rows": len(seed_rows),
            "seed_shape_ready_for_dry_run": seed_shape_ready,
            "backtest_ready_now": backtest_ready,
            "exploratory_backtest_ready_now": exploratory_majority_ready,
            "organic_negative_rows_still_missing": True,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "cex_listing_exploratory_shadow_backtest_preview_read_only"
            if exploratory_majority_ready else
            "cex_listing_ground_truth_seed_insert_dry_run_with_6_rows"
            if seed_shape_ready else
            "repair_seed_coherence_or_find_replacement_negative_controls"
        ),
        "plain_summary_fr": (
            "Le checkpoint suit l'alerte Qwen: les 6 lignes peuvent former un seed si l'intake passe, "
            "mais le backtest ne doit pas pretendre etre valide si le contexte comportemental local est incomplet."
        ),
        **disabled,
    }


def get_manipulation_detection_local_native_ground_truth_discovery_preview(
    chain: str | None = "bsc",
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 5,
    min_transfers: int = 10,
) -> dict[str, Any]:
    """Read-only data-first discovery of local tokens worth external ground-truth labeling."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 50), 100))
    safe_min_swaps = max(0, min(int(min_swaps or 5), 10_000))
    safe_min_transfers = max(0, min(int(min_transfers or 10), 100_000))
    source_policy = (
        "admin-only read-only local native ground-truth discovery. It starts from tokens already present "
        "in local pair/swap/transfer data and prepares labeling payloads for CoinGecko/Honeypot/GoPlus. "
        "It does not call those sources, insert ground truth, score clients or trade."
    )
    disabled = {
        "would_call_provider": False,
        "would_scrape": False,
        "would_insert_ground_truth_rows": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "discovery_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    conn = _engine()._get_db()
    try:
        table_counts = {
            table: _table_count(conn, table)
            for table in ["dex_raw_swap_events", "pair_tokens", "token_transfers", "token_metadata"]
        }
    finally:
        conn.close()

    candidates = _local_native_ground_truth_candidates(
        clean_chain,
        clean_limit,
        safe_min_swaps,
        safe_min_transfers,
    )
    blockers = [
        *("no_native_ground_truth_candidates_found" for _ in [1] if not candidates),
        "external_labeling_not_performed",
        "ground_truth_rows_not_inserted",
        "organic_negative_rows_still_required_for_final_backtest",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "discovery_status": "ready_but_disabled" if candidates else "blocked",
        "chain": clean_chain,
        "limit": clean_limit,
        "min_swaps": safe_min_swaps,
        "min_transfers": safe_min_transfers,
        "table_counts": table_counts,
        "candidates": candidates,
        "labeling_plan": {
            "goal": "label local-native tokens instead of backfilling external tokens like LONG",
            "allowed_future_sources": [
                "CoinGecko markets for CEX listing presence",
                "official CEX announcement pages for positive listing date",
                "Honeypot.is / GoPlus for documented scam negatives",
                "manual source-backed verification for organic never-listed negatives",
            ],
            "required_classes": [
                "positive_native_cex_listing",
                "documented_honeypot_or_scam_negative",
                "organic_never_listed_negative",
                "blocked_unclear",
            ],
        },
        "summary": {
            "native_candidates": len(candidates),
            "ready_for_external_labeling": len(candidates),
            "can_replace_long_now": False,
            "ground_truth_insert_ready_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "local_native_ground_truth_labeling_lookup_dry_run"
            if candidates else
            "collect_more_local_native_swap_transfer_data"
        ),
        "plain_summary_fr": (
            "On pivote data-first: au lieu de forcer LONG dans la base, on sort les tokens deja riches "
            "localement et on prepare leur etiquetage externe."
        ),
        **disabled,
    }


def get_manipulation_detection_native_positive_candidate_replacement_discovery_preview(
    chain: str | None = "bsc",
    limit: int = 20,
    dry_run: bool = True,
    min_swaps: int = 100,
    min_transfers: int = 200,
) -> dict[str, Any]:
    """Read-only local search for a better native positive CEX-listing seed than B."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 20), 50))
    safe_min_swaps = max(0, min(int(min_swaps or 100), 10_000))
    safe_min_transfers = max(0, min(int(min_transfers or 200), 100_000))
    source_policy = (
        "admin-only read-only native positive replacement discovery. It searches local-native tokens with "
        "strong raw context and local CEX destination evidence, to replace B in the exploratory CEX-listing "
        "backtest. It calls no providers, scrapes nothing, inserts no ground truth, creates no labels, "
        "signals, mappings or trades."
    )
    disabled = {
        "would_call_provider": False,
        "would_scrape": False,
        "would_insert_ground_truth_rows": False,
        "would_create_cex_label": False,
        "would_update_wallet_state": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_create_dex_mapping": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "discovery_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    local_discovery = get_manipulation_detection_local_native_ground_truth_discovery_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        min_transfers=safe_min_transfers,
    )
    local_candidates = list(local_discovery.get("candidates") or [])[:clean_limit]
    candidates: list[dict[str, Any]] = []
    for row in local_candidates:
        token = _clean_address(row.get("token_address"))
        if not token:
            continue
        cex_scan = _engine().get_token_transfer_cex_deposit_scan(
            chain=clean_chain,
            limit=100,
            token_addresses=[token],
        )
        cex_summary = dict(cex_scan.get("summary") or {})
        deposits = _as_int(cex_summary.get("deposits"))
        source_backed_targets = _as_int(cex_summary.get("source_backed_target_wallets"))
        exchange_targets = _as_int(cex_summary.get("target_exchange_wallets"))
        destination_status = "no_local_cex_destination"
        if source_backed_targets > 0:
            destination_status = "source_backed_cex_destination"
        elif exchange_targets > 0:
            destination_status = "exchange_like_destination_unbacked"

        distribution_risk = "unknown"
        conn = _engine()._get_db()
        try:
            outgoing_rows = 0
            destination_rows = 0
            if _table_exists(conn, "erc20_transfer_events"):
                destination_rows += _as_int(conn.execute(
                    """
                    SELECT COUNT(DISTINCT lower(to_address))
                    FROM erc20_transfer_events
                    WHERE lower(chain)=? AND lower(token_address)=?
                    """,
                    (clean_chain, token),
                ).fetchone()[0])
                outgoing_rows += _as_int(conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM erc20_transfer_events
                    WHERE lower(chain)=? AND lower(token_address)=?
                      AND lower(from_address) IN (
                          SELECT DISTINCT lower(to_address)
                          FROM erc20_transfer_events
                          WHERE lower(chain)=? AND lower(token_address)=?
                      )
                    """,
                    (clean_chain, token, clean_chain, token),
                ).fetchone()[0])
            if _table_exists(conn, "token_transfers"):
                destination_rows += _as_int(conn.execute(
                    """
                    SELECT COUNT(DISTINCT lower(to_addr))
                    FROM token_transfers
                    WHERE lower(chain)=? AND lower(token)=?
                    """,
                    (clean_chain, token),
                ).fetchone()[0])
                outgoing_rows += _as_int(conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM token_transfers
                    WHERE lower(chain)=? AND lower(token)=?
                      AND lower(from_addr) IN (
                          SELECT DISTINCT lower(to_addr)
                          FROM token_transfers
                          WHERE lower(chain)=? AND lower(token)=?
                      )
                    """,
                    (clean_chain, token, clean_chain, token),
                ).fetchone()[0])
        finally:
            conn.close()
        if destination_rows and outgoing_rows / max(destination_rows, 1) >= 0.5:
            distribution_risk = "distribution_heavy"
        elif destination_rows:
            distribution_risk = "not_distribution_heavy_local_proxy"

        replacement_ready = bool(source_backed_targets > 0 and deposits > 0 and distribution_risk != "distribution_heavy")
        blockers = list(dict.fromkeys([
            *("no_source_backed_cex_destination" for _ in [1] if source_backed_targets <= 0),
            *("exchange_like_destination_needs_source_backing" for _ in [1] if exchange_targets > 0 and source_backed_targets <= 0),
            *("distribution_heavy_local_flow" for _ in [1] if distribution_risk == "distribution_heavy"),
            *("external_listing_label_still_required" for _ in [1] if replacement_ready),
            "ground_truth_not_inserted",
            "client_signal_disabled",
            "trade_disabled",
        ]))
        candidates.append({
            "chain": clean_chain,
            "token_address": token,
            "token_symbol": row.get("token_symbol"),
            "replacement_status": "candidate_for_positive_ground_truth_labeling" if replacement_ready else "blocked",
            "native_context": {
                "native_context_score": row.get("native_context_score"),
                "swap_rows": row.get("swap_rows"),
                "transfer_rows": row.get("transfer_rows"),
                "pool_addresses": row.get("pool_addresses"),
                "age_days": row.get("age_days"),
                "candidate_sources": row.get("candidate_sources"),
            },
            "cex_deposit_context": {
                "destination_status": destination_status,
                "deposits": deposits,
                "target_exchange_wallets": exchange_targets,
                "source_backed_target_wallets": source_backed_targets,
                "fresh_like_depositors": _as_int(cex_summary.get("fresh_like_depositors")),
                "shared_funders": _as_int(cex_summary.get("shared_funders")),
                "coordination_score": _as_int(cex_summary.get("coordination_score")),
                "coordination_tier": cex_summary.get("coordination_tier"),
            },
            "flow_proxy": {
                "destination_rows": destination_rows,
                "outgoing_rows_from_destinations": outgoing_rows,
                "distribution_risk": distribution_risk,
            },
            "labeling_payload": row.get("labeling_payload"),
            "blockers": blockers,
        })

    ready = [row for row in candidates if row.get("replacement_status") == "candidate_for_positive_ground_truth_labeling"]
    blockers = list(dict.fromkeys([
        *("lab_missing_local_raw_context" for _ in [1]),
        *("b_rejected_as_cex_positive_distribution_routing" for _ in [1]),
        *("no_replacement_positive_candidate_with_source_backed_cex_destination" for _ in [1] if not ready),
        "external_labeling_not_performed",
        "ground_truth_rows_not_inserted",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    return {
        "ok": True,
        "dry_run": True,
        "discovery_status": "ready_but_disabled" if candidates else "blocked",
        "chain": clean_chain,
        "limit": clean_limit,
        "min_swaps": safe_min_swaps,
        "min_transfers": safe_min_transfers,
        "lab_context_status": {
            "token_address": "0x7ec43cf65f1663f820427c62a5780b8f2e25593a",
            "status": "missing_local_raw_context_needs_pair_discovery_or_backfill",
        },
        "b_context_status": {
            "token_address": "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
            "status": "research_control_not_positive_cex_listing",
        },
        "local_discovery_snapshot": {
            "summary": local_discovery.get("summary"),
            "blockers": local_discovery.get("blockers"),
        },
        "candidates": candidates,
        "replacement_candidates": ready,
        "summary": {
            "local_candidates_checked": len(candidates),
            "replacement_candidates": len(ready),
            "tokens_with_any_cex_deposit_rows": sum(1 for row in candidates if _as_int((row.get("cex_deposit_context") or {}).get("deposits")) > 0),
            "tokens_with_source_backed_cex_destinations": sum(1 for row in candidates if _as_int((row.get("cex_deposit_context") or {}).get("source_backed_target_wallets")) > 0),
            "positive_replacement_ready_now": bool(ready),
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "external_labeling_lookup_for_replacement_candidate_read_only"
            if ready else
            "cex_wallet_reference_collection_or_lab_raw_backfill_decision_read_only"
        ),
        "plain_summary_fr": (
            "Cette preview cherche un remplacant positif natif a B. Elle exige un contexte local fort et un "
            "indice CEX local; sinon le backtest listing resterait artificiel."
        ),
        **disabled,
    }


def get_manipulation_detection_local_native_ground_truth_labeling_lookup_preview(
    chain: str | None = "bsc",
    limit: int = 20,
    dry_run: bool = True,
    min_swaps: int = 1,
    min_transfers: int = 5,
    use_coingecko: bool = True,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Read-only bounded lookup that labels local-native candidates without inserting ground truth."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 20), 50))
    safe_min_swaps = max(0, min(int(min_swaps or 1), 10_000))
    safe_min_transfers = max(0, min(int(min_transfers or 5), 100_000))
    safe_timeout = max(1, min(int(timeout_seconds or 10), 30))
    coingecko_platform = _coingecko_platform_id(clean_chain)
    source_policy = (
        "admin-only read-only local-native ground-truth labeling lookup. It starts from local candidates, "
        "performs bounded CoinGecko/Honeypot/GoPlus lookups, classifies candidates for future ground-truth "
        "intake, and never inserts rows, creates signals, maps, labels or trades."
    )
    disabled = {
        "would_insert_ground_truth_rows": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_call_unbounded_provider": False,
        "would_scrape": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "lookup_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    discovery = get_manipulation_detection_local_native_ground_truth_discovery_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        min_transfers=safe_min_transfers,
    )
    local_candidates = [
        row
        for row in list(discovery.get("candidates") or [])
        if row.get("native_context_status") == "labeling_candidate"
    ][:clean_limit]
    token_addresses = _parse_token_addresses([row.get("token_address") for row in local_candidates])

    security_preview = get_manipulation_detection_external_scam_negative_intake_preview(
        chain=clean_chain,
        token_addresses=token_addresses,
        limit=clean_limit,
        dry_run=True,
        use_honeypot=use_honeypot,
        use_goplus=use_goplus,
        timeout_seconds=safe_timeout,
    ) if token_addresses and (use_honeypot or use_goplus) else {
        "candidates": [],
        "preview_ground_truth_rows": [],
        "summary": {"documented_scam_negative_rows": 0},
        "blockers": ["security_sources_disabled_or_no_candidates"],
    }
    security_by_token = {
        _clean_address(row.get("token_address")): row
        for row in list(security_preview.get("candidates") or [])
        if _clean_address(row.get("token_address"))
    }

    candidates: list[dict[str, Any]] = []
    bounded_source_calls = 0
    for local in local_candidates:
        token = _clean_address(local.get("token_address"))
        security_row = security_by_token.get(token) or {}
        coingecko_url = _coingecko_contract_url(clean_chain, token)
        coingecko_payload: dict[str, Any] = {}
        coingecko_errors: list[str] = []
        cex_market_matches: list[dict[str, Any]] = []
        if use_coingecko and coingecko_url:
            try:
                bounded_source_calls += 1
                coingecko_payload = _http_json(coingecko_url, safe_timeout)
                cex_market_matches = _extract_coingecko_cex_markets(coingecko_payload)
            except urllib.error.HTTPError as exc:
                code = getattr(exc, "code", "unknown")
                coingecko_errors.append(f"coingecko_lookup_http_{code}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                coingecko_errors.append(f"coingecko_lookup_failed:{type(exc).__name__}")

        documented_negative = bool(security_row.get("documented_negative"))
        positive_cex_market = bool(cex_market_matches)
        coingecko_snapshot = {
            "source_url": coingecko_url,
            "coin_id": coingecko_payload.get("id"),
            "coin_symbol": coingecko_payload.get("symbol"),
            "coin_name": coingecko_payload.get("name"),
            "cex_market_matches": cex_market_matches,
            "source_digest": _digest(coingecko_payload) if coingecko_payload else None,
            "errors": coingecko_errors,
        }
        if documented_negative:
            classification = "documented_honeypot_or_scam_negative"
            candidate_status = "documented_negative_ready_for_ground_truth_intake_preview"
        elif positive_cex_market:
            classification = "positive_native_cex_listing_candidate"
            candidate_status = "positive_needs_official_cex_announcement_source"
        else:
            classification = "organic_or_unclear_needs_manual_90d_check"
            candidate_status = "blocked_unclear"

        blockers = [
            *("official_cex_announcement_source_required_before_positive_intake" for _ in [1] if positive_cex_market),
            *("not_documented_negative_by_enabled_security_sources" for _ in [1] if not documented_negative),
            *("no_cex_market_match_from_coingecko" for _ in [1] if not positive_cex_market),
            *coingecko_errors,
            "ground_truth_rows_not_inserted",
            "client_signal_disabled",
            "trade_disabled",
        ]
        if documented_negative:
            blockers = [
                "scam_negative_is_not_organic_negative_control",
                "ground_truth_rows_not_inserted",
                "client_signal_disabled",
                "trade_disabled",
            ]
        candidates.append({
            "chain": clean_chain,
            "token_address": token,
            "token_symbol": local.get("token_symbol") or "UNKNOWN",
            "native_context": {
                "native_context_score": local.get("native_context_score"),
                "swap_rows": local.get("swap_rows"),
                "transfer_rows": local.get("transfer_rows"),
                "pair_occurrences": local.get("pair_occurrences"),
                "pool_addresses": local.get("pool_addresses"),
                "candidate_sources": local.get("candidate_sources"),
            },
            "candidate_status": candidate_status,
            "label_classification": classification,
            "security_classification": {
                "documented_negative": documented_negative,
                "honeypot_detected": bool(security_row.get("honeypot_detected")),
                "goplus_honeypot": bool(security_row.get("goplus_honeypot")),
                "source_digest": security_row.get("source_digest"),
                "preview_ground_truth_row": security_row.get("preview_ground_truth_row"),
            },
            "coingecko_listing_snapshot": coingecko_snapshot,
            "blockers": list(dict.fromkeys(blockers)),
        })

    positive_candidates = [row for row in candidates if row["label_classification"] == "positive_native_cex_listing_candidate"]
    negative_candidates = [row for row in candidates if row["label_classification"] == "documented_honeypot_or_scam_negative"]
    blockers = [
        *("no_local_native_candidates_found" for _ in [1] if not local_candidates),
        *("coingecko_platform_unsupported" for _ in [1] if use_coingecko and not coingecko_platform),
        *("no_positive_native_cex_listing_candidate_found" for _ in [1] if local_candidates and not positive_candidates),
        *("no_documented_scam_negative_found" for _ in [1] if local_candidates and not negative_candidates),
        "official_cex_announcement_source_required_before_replacing_long",
        "ground_truth_rows_not_inserted",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "lookup_status": "ready_but_disabled" if candidates else "blocked",
        "chain": clean_chain,
        "limit": clean_limit,
        "min_swaps": safe_min_swaps,
        "min_transfers": safe_min_transfers,
        "timeout_seconds": safe_timeout,
        "enabled_sources": {
            "coingecko": bool(use_coingecko),
            "honeypot": bool(use_honeypot),
            "goplus": bool(use_goplus),
        },
        "coingecko_platform": coingecko_platform,
        "discovery_snapshot": {
            "summary": discovery.get("summary"),
            "blockers": discovery.get("blockers"),
        },
        "security_snapshot": {
            "summary": security_preview.get("summary"),
            "blockers": security_preview.get("blockers"),
        },
        "candidates": candidates,
        "preview_ground_truth_negative_rows": [
            row["security_classification"]["preview_ground_truth_row"]
            for row in negative_candidates
            if row["security_classification"].get("preview_ground_truth_row")
        ],
        "bounded_source_calls_performed": bounded_source_calls + len(token_addresses) * int(bool(use_honeypot or use_goplus)),
        "summary": {
            "local_native_candidates_checked": len(local_candidates),
            "positive_native_cex_listing_candidates": len(positive_candidates),
            "documented_scam_negative_candidates": len(negative_candidates),
            "long_replacement_ready_now": False,
            "can_replace_long_now": False,
            "ground_truth_insert_ready_now": bool(negative_candidates),
            "backtest_ready_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "official_cex_announcement_lookup_for_native_positive_candidates"
            if positive_candidates else
            "expand_local_native_candidate_labeling_or_collect_more_local_context"
        ),
        "plain_summary_fr": (
            "On etiquete ce que la base possede deja. Les honeypots documentes peuvent devenir des negatifs "
            "preview; les listings CoinGecko restent des candidats positifs tant qu'une source CEX officielle "
            "n'a pas fixe la date d'annonce/listing."
        ),
        **disabled,
    }


def get_manipulation_detection_cex_listing_exploratory_shadow_backtest_preview(
    chain: str | None = "bsc",
    dry_run: bool = True,
    score_threshold: int = 50,
    negative_limit: int = 20,
    max_scan_rows: int = 500,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
    token_addresses: list[str] | str | None = None,
) -> dict[str, Any]:
    """Read-only exploratory matrix for the tiny CEX listing seed cohort."""
    clean_chain = str(chain or "bsc").strip().lower()
    safe_threshold = max(0, min(int(score_threshold or 50), 100))
    clean_negative_limit = max(1, min(int(negative_limit or 20), 50))
    safe_max_scan_rows = max(10, min(int(max_scan_rows or 500), 5_000))
    safe_timeout = max(1, min(int(timeout_seconds or 10), 30))
    explicit_tokens = _parse_token_addresses(token_addresses)
    source_policy = (
        "admin-only read-only exploratory CEX listing shadow backtest preview. It uses the seed coherence "
        "checkpoint in majority-context mode to produce a first confusion matrix from current local features. "
        "It is exploratory only and cannot create a client signal or trade."
    )
    disabled = {
        "would_insert_ground_truth_rows": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_call_unbounded_provider": False,
        "would_scrape": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "backtest_status": "blocked",
            "blockers": ["dry_run_required"],
            **disabled,
        }

    checkpoint = get_manipulation_detection_cex_listing_ground_truth_seed_coherence_checkpoint(
        chain=clean_chain,
        dry_run=True,
        negative_limit=clean_negative_limit,
        max_scan_rows=safe_max_scan_rows,
        use_honeypot=use_honeypot,
        use_goplus=use_goplus,
        timeout_seconds=safe_timeout,
        allow_exploratory_majority_context=True,
        token_addresses=explicit_tokens or None,
    )
    profiles = checkpoint.get("profiles_by_token") or {}
    rows: list[dict[str, Any]] = []
    for label, seed_rows in (("positive", checkpoint.get("positive_rows") or []), ("negative", checkpoint.get("negative_rows") or [])):
        for seed in seed_rows:
            token = _clean_address(seed.get("token_address"))
            profile = profiles.get(token) or {}
            local_context = profile.get("local_context_status") == "local_context_present"
            listing_score = _as_int(profile.get("listing_probability_score"))
            behavioral_score = _as_int(profile.get("behavioral_score"))
            composite_score = max(listing_score, behavioral_score)
            predicted_positive = bool(local_context and composite_score >= safe_threshold)
            rows.append({
                "token_address": token,
                "token_symbol": seed.get("token_symbol") or profile.get("token_symbol") or "UNKNOWN",
                "true_label": label,
                "used_in_matrix": local_context,
                "local_context_status": profile.get("local_context_status"),
                "listing_probability_score": listing_score,
                "behavioral_score": behavioral_score,
                "composite_score": composite_score,
                "predicted_label": "positive" if predicted_positive else "negative",
                "seed_role": seed.get("seed_role"),
                "limitations": [
                    *("missing_local_context_excluded_from_matrix" for _ in [1] if not local_context),
                    *("score_zero_or_below_threshold" for _ in [1] if local_context and composite_score < safe_threshold),
                ],
            })

    usable_rows = [row for row in rows if row.get("used_in_matrix")]
    tp = sum(1 for row in usable_rows if row["true_label"] == "positive" and row["predicted_label"] == "positive")
    fp = sum(1 for row in usable_rows if row["true_label"] == "negative" and row["predicted_label"] == "positive")
    fn = sum(1 for row in usable_rows if row["true_label"] == "positive" and row["predicted_label"] == "negative")
    tn = sum(1 for row in usable_rows if row["true_label"] == "negative" and row["predicted_label"] == "negative")
    precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    recall = round(tp / (tp + fn), 4) if (tp + fn) else None
    accuracy = round((tp + tn) / len(usable_rows), 4) if usable_rows else None
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision and recall and (precision + recall) else None
    any_signal = any(_as_int(row.get("composite_score")) > 0 for row in usable_rows)
    blockers = [
        *("exploratory_majority_context_not_ready" for _ in [1] if not (checkpoint.get("summary") or {}).get("exploratory_backtest_ready_now")),
        *("no_usable_rows_for_matrix" for _ in [1] if not usable_rows),
        *("current_local_scores_are_zero_or_below_threshold" for _ in [1] if usable_rows and not any_signal),
        "exploratory_only_not_final_backtest",
        "organic_negative_rows_still_required",
        "long_missing_local_context",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "backtest_status": "ready_but_disabled" if usable_rows else "blocked",
        "chain": clean_chain,
        "token_addresses": explicit_tokens,
        "explicit_filter": bool(explicit_tokens),
        "score_threshold": safe_threshold,
        "coherence_snapshot": {
            "coherence_status": checkpoint.get("coherence_status"),
            "backtest_homogeneity_status": checkpoint.get("backtest_homogeneity_status"),
            "summary": checkpoint.get("summary"),
            "positive_missing_local_context": checkpoint.get("positive_missing_local_context"),
            "negative_missing_local_context": checkpoint.get("negative_missing_local_context"),
        },
        "rows": rows,
        "confusion_matrix": {
            "threshold": safe_threshold,
            "usable_rows": len(usable_rows),
            "excluded_rows": len(rows) - len(usable_rows),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
            "precision": precision,
            "recall": recall,
            "accuracy": accuracy,
            "f1": f1,
        },
        "interpretation": {
            "verdict": (
                "no_predictive_signal_from_current_local_scores"
                if usable_rows and not any_signal else
                "exploratory_matrix_ready_for_review"
                if usable_rows else
                "blocked"
            ),
            "plain_summary_fr": (
                "Le backtest exploratoire tourne, mais les scores locaux actuels ne distinguent pas encore "
                "les listings des honeypots. C'est un resultat utile: le dataset peut etre rejoue, mais "
                "le modele/features doivent etre enrichis avant tout signal."
                if usable_rows and not any_signal else
                "Le backtest exploratoire produit une matrice a examiner, sans decision client ni trade."
            ),
            "limits": [
                "sample too small",
                "LONG excluded from usable matrix because local context is missing",
                "negative controls are honeypots, not organic never-listed tokens",
                "no temporal J-30/J-7/J-1 leakage-safe replay yet",
            ],
        },
        "summary": {
            "seed_rows": len(rows),
            "usable_rows": len(usable_rows),
            "exploratory_matrix_ready": bool(usable_rows),
            "final_backtest_ready_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "cex_listing_feature_repair_or_honeypot_correlation_scan_read_only"
            if usable_rows and not any_signal else
            "review_exploratory_matrix_then_expand_dataset_read_only"
        ),
        **disabled,
    }


def get_manipulation_detection_cex_listing_feature_wiring_diagnostic_preview(
    chain: str | None = "bsc",
    dry_run: bool = True,
    cex_deposit_limit: int = 100,
) -> dict[str, Any]:
    """Read-only diagnostic explaining why seed CEX-listing scores are zero."""
    clean_chain = str(chain or "bsc").strip().lower()
    safe_cex_limit = max(1, min(int(cex_deposit_limit or 100), 200))
    seed_rows = _positive_seed_ground_truth_rows(clean_chain)
    seed_tokens = [row["token_address"] for row in seed_rows]
    source_policy = (
        "admin-only read-only CEX listing feature wiring diagnostic. It inspects local tables and previews "
        "to explain whether listing scores are zero because feature tables are empty, preview joins miss the "
        "seed tokens, or the score formula is too weak. It writes nothing and creates no signal."
    )
    disabled = {
        "would_insert_ground_truth_rows": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_call_provider": False,
        "would_scrape": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "diagnostic_status": "blocked",
            "blockers": ["dry_run_required"],
            **disabled,
        }

    expected_feature_tables = [
        "cex_token_deposits",
        "wallet_funding_graph",
        "behavioral_stealth_accumulation_scan",
        "behavioral_evidence_bridge_results",
    ]
    conn = _engine()._get_db()
    try:
        materialized_tables = {}
        for table in expected_feature_tables:
            exists = _table_exists(conn, table)
            materialized_tables[table] = {
                "exists": exists,
                "row_count": _table_count(conn, table) if exists else None,
                "status": "present" if exists else "missing_materialized_feature_table",
            }
    finally:
        conn.close()

    bridge = get_manipulation_detection_cex_listing_probability_bridge_preview(
        chain=clean_chain,
        limit=50,
        dry_run=True,
        min_behavioral_score=20,
        cex_deposit_limit=safe_cex_limit,
    )
    cex_scan = _engine().get_token_transfer_cex_deposit_scan(
        chain=clean_chain,
        limit=safe_cex_limit,
    )
    bridge_candidates = list(bridge.get("candidates") or [])
    cex_deposit_rows = list(cex_scan.get("rows") or [])
    profiles = _local_token_context_profiles(
        clean_chain,
        seed_tokens,
        bridge_candidates=bridge_candidates,
    )
    bridge_by_token = {
        _clean_address(row.get("token_address")): row
        for row in bridge_candidates
        if _clean_address(row.get("token_address"))
    }
    deposits_by_token: dict[str, list[dict[str, Any]]] = {}
    for row in cex_deposit_rows:
        token = _clean_address(row.get("token"))
        if token:
            deposits_by_token.setdefault(token, []).append(row)

    seed_diagnostics: list[dict[str, Any]] = []
    for seed in seed_rows:
        token = seed["token_address"]
        profile = profiles.get(token) or {}
        bridge_row = bridge_by_token.get(token)
        token_deposits = deposits_by_token.get(token, [])
        missing = [
            *("not_present_in_bridge_candidates" for _ in [1] if not bridge_row),
            *("no_matching_cex_deposit_rows_for_token" for _ in [1] if not token_deposits),
            *("local_context_missing" for _ in [1] if profile.get("local_context_status") != "local_context_present"),
            *("listing_probability_score_zero" for _ in [1] if _as_int(profile.get("listing_probability_score")) == 0),
            *("behavioral_score_zero" for _ in [1] if _as_int(profile.get("behavioral_score")) == 0),
        ]
        seed_diagnostics.append({
            "token_symbol": seed.get("token_symbol"),
            "token_address": token,
            "local_context_status": profile.get("local_context_status"),
            "transfer_rows": profile.get("transfer_rows"),
            "pair_occurrences": profile.get("pair_occurrences"),
            "raw_swap_rows": profile.get("raw_swap_rows"),
            "bridge_candidate_present": bool(bridge_row),
            "bridge_listing_probability_score": (bridge_row or {}).get("listing_probability_score"),
            "bridge_behavioral_score": (bridge_row or {}).get("behavioral_anomaly_score"),
            "matching_cex_deposit_rows": len(token_deposits),
            "missing_features": list(dict.fromkeys(missing)),
        })

    materialized_missing = all(not row["exists"] for row in materialized_tables.values())
    any_seed_bridge = any(row["bridge_candidate_present"] for row in seed_diagnostics)
    any_seed_deposit = any(_as_int(row["matching_cex_deposit_rows"]) > 0 for row in seed_diagnostics)
    any_seed_score = any(_as_int(row.get("bridge_listing_probability_score")) > 0 or _as_int(row.get("bridge_behavioral_score")) > 0 for row in seed_diagnostics)
    if materialized_missing and not any_seed_bridge and not any_seed_deposit:
        scenario = "A_feature_tables_empty_or_not_materialized_for_seed_tokens"
        recommended_action = "repair_preview_feature_wiring_or_run_seed_specific_context_lookup_read_only"
    elif any_seed_deposit and not any_seed_score:
        scenario = "B_features_exist_but_score_aggregation_misses_seed_tokens"
        recommended_action = "repair_score_aggregation_between_cex_scan_bridge_and_seed_profiles"
    elif any_seed_score and max(_as_int(row.get("bridge_listing_probability_score")) for row in seed_diagnostics) < 30:
        scenario = "C_features_wired_but_current_model_weak"
        recommended_action = "run_honeypot_correlation_scan_read_only_or_reweight_listing_features"
    else:
        scenario = "mixed_or_inconclusive"
        recommended_action = "inspect_seed_specific_bridge_candidates_and_cex_deposit_rows"

    blockers = [
        *("materialized_feature_tables_missing" for _ in [1] if materialized_missing),
        *("seed_tokens_not_present_in_bridge_candidates" for _ in [1] if not any_seed_bridge),
        *("seed_tokens_have_no_matching_cex_deposit_rows" for _ in [1] if not any_seed_deposit),
        *("seed_scores_zero" for _ in [1] if not any_seed_score),
        "diagnostic_only_no_signal",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "diagnostic_status": "ready_but_disabled",
        "chain": clean_chain,
        "seed_tokens": seed_diagnostics,
        "materialized_feature_tables": materialized_tables,
        "preview_sources": {
            "bridge_summary": bridge.get("summary"),
            "bridge_blockers": bridge.get("blockers"),
            "cex_deposit_scan_summary": cex_scan.get("summary"),
            "cex_deposit_scan_blockers": cex_scan.get("blockers"),
        },
        "scenario_diagnosis": {
            "scenario": scenario,
            "recommended_action": recommended_action,
            "plain_summary_fr": (
                "Les scores LAB/B/LONG sont a zero surtout parce que les features ne sont pas materialisees "
                "en tables persistantes et que les previews actuelles ne remontent pas les seed tokens comme "
                "candidats avec depots CEX. Le souci est le cablage/selection des features, pas le backtest."
            ),
        },
        "summary": {
            "materialized_feature_tables_present": sum(1 for row in materialized_tables.values() if row["exists"]),
            "seed_tokens_checked": len(seed_diagnostics),
            "seed_tokens_in_bridge": sum(1 for row in seed_diagnostics if row["bridge_candidate_present"]),
            "seed_tokens_with_cex_deposit_rows": sum(1 for row in seed_diagnostics if _as_int(row["matching_cex_deposit_rows"]) > 0),
            "seed_tokens_with_nonzero_score": sum(1 for row in seed_diagnostics if _as_int(row.get("bridge_listing_probability_score")) > 0 or _as_int(row.get("bridge_behavioral_score")) > 0),
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": recommended_action,
        **disabled,
    }


def get_manipulation_detection_feature_backfill_orchestrator_preview(
    chain: str | None = "bsc",
    token_addresses: list[str] | str | None = None,
    dry_run: bool = True,
    run_existing_previews: bool = True,
    cex_deposit_limit: int = 100,
    min_raw_swaps_for_feature_backfill: int = 50,
) -> dict[str, Any]:
    """Read-only orchestrator preview for rerunning existing feature pipelines on explicit tokens."""
    clean_chain = str(chain or "bsc").strip().lower()
    safe_cex_limit = max(1, min(int(cex_deposit_limit or 100), 200))
    safe_min_swaps = max(1, min(int(min_raw_swaps_for_feature_backfill or 50), 10_000))
    requested_tokens = _parse_token_addresses(token_addresses)
    if not requested_tokens:
        requested_tokens = [
            row["token_address"]
            for row in _positive_seed_ground_truth_rows(clean_chain)
            if row.get("token_symbol") in {"LAB", "B"}
        ]
    requested_tokens = requested_tokens[:20]
    source_policy = (
        "admin-only read-only feature backfill orchestrator preview. It checks whether existing feature "
        "pipelines can be rerun on explicit tokens and reports raw-data blockers. It does not create "
        "feature tables, insert rows, materialize scores, create signals or trade."
    )
    disabled = {
        "would_create_feature_tables": False,
        "would_insert_feature_rows": False,
        "would_persist_listing_probability": False,
        "would_insert_ground_truth_rows": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_call_provider": False,
        "would_scrape": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "orchestrator_status": "blocked",
            "blockers": ["dry_run_required"],
            "tokens": [],
            **disabled,
        }

    diagnostic = get_manipulation_detection_cex_listing_feature_wiring_diagnostic_preview(
        chain=clean_chain,
        dry_run=True,
        cex_deposit_limit=safe_cex_limit,
    )
    profiles = _local_token_context_profiles(clean_chain, requested_tokens)
    cex_scan = _engine().get_token_transfer_cex_deposit_scan(
        chain=clean_chain,
        limit=safe_cex_limit,
        token_addresses=requested_tokens,
    )
    cex_rows = list(cex_scan.get("rows") or [])
    deposits_by_token: dict[str, list[dict[str, Any]]] = {}
    for row in cex_rows:
        token = _clean_address(row.get("token"))
        if token:
            deposits_by_token.setdefault(token, []).append(row)

    token_results: list[dict[str, Any]] = []
    for token in requested_tokens:
        profile = profiles.get(token) or {}
        token_deposits = deposits_by_token.get(token, [])
        raw_swaps = _as_int(profile.get("raw_swap_rows"))
        transfers = _as_int(profile.get("transfer_rows"))
        pair_occurrences = _as_int(profile.get("pair_occurrences"))
        raw_ready = raw_swaps >= safe_min_swaps
        transfer_ready = transfers > 0
        funder_preview: dict[str, Any] | None = None
        stealth_preview: dict[str, Any] | None = None
        behavioral_preview: dict[str, Any] | None = None
        if run_existing_previews:
            try:
                funder_preview = _engine().get_adaptive_accumulator_funder_graph_scan(
                    chain=clean_chain,
                    token=token,
                    limit=1,
                    wallet_limit=5,
                    baseline_swaps=1,
                    confirmation_swaps=1,
                    pre_event_swaps=5,
                )
            except Exception as exc:  # pragma: no cover - defensive preview reporting only
                funder_preview = {
                    "ok": False,
                    "blockers": [f"funder_graph_preview_failed:{type(exc).__name__}"],
                }
            try:
                stealth_preview = get_manipulation_detection_stealth_accumulation_anomaly_scan_preview(
                    chain=clean_chain,
                    limit=1,
                    dry_run=True,
                    max_pools=25,
                    max_circularity_pct=30.0,
                    min_hold_freeze_proxy_pct=70.0,
                    min_buy_flows=3,
                    token_addresses=[token],
                )
            except Exception as exc:  # pragma: no cover - defensive preview reporting only
                stealth_preview = {
                    "ok": False,
                    "blockers": [f"stealth_preview_failed:{type(exc).__name__}"],
                }
            try:
                behavioral_preview = _engine().get_manipulation_detection_behavioral_evidence_bridge(
                    chain=clean_chain,
                    token=token,
                    limit=1,
                    wallet_limit=5,
                    dry_run=True,
                    baseline_swaps=1,
                    confirmation_swaps=1,
                    pre_event_swaps=5,
                )
            except Exception as exc:  # pragma: no cover - defensive preview reporting only
                behavioral_preview = {
                    "ok": False,
                    "blockers": [f"behavioral_bridge_preview_failed:{type(exc).__name__}"],
                }

        pipeline_results = {
            "cex_deposit_flow_scan": {
                "existing_function": "get_token_transfer_cex_deposit_scan",
                "supports_explicit_token_addresses_now": True,
                "current_matching_deposit_rows": len(token_deposits),
                "status": "explicit_filter_ran_no_matching_cex_deposits" if not token_deposits else "context_present",
                "next_repair": "repair CEX hot wallet/reference coverage if zero rows remain for explicit token",
            },
            "adaptive_accumulator_funder_graph_scan": {
                "existing_function": "get_adaptive_accumulator_funder_graph_scan",
                "supports_explicit_token_now": True,
                "preview_summary": (funder_preview or {}).get("summary"),
                "preview_blockers": (funder_preview or {}).get("blockers"),
                "status": "preview_ran_read_only" if funder_preview is not None else "preview_skipped",
            },
            "stealth_accumulation_scan": {
                "existing_function": "get_manipulation_detection_stealth_accumulation_anomaly_scan_preview",
                "supports_explicit_token_addresses_now": True,
                "required_raw_context": "pair + raw Swap/Sync/Transfer context",
                "preview_summary": (stealth_preview or {}).get("summary"),
                "preview_blockers": (stealth_preview or {}).get("blockers"),
                "status": "raw_context_insufficient" if not raw_ready else "preview_ran_read_only" if stealth_preview is not None else "preview_skipped",
            },
            "behavioral_evidence_bridge": {
                "existing_function": "get_manipulation_detection_behavioral_evidence_bridge",
                "supports_explicit_token_now": True,
                "required_raw_context": "candidate must be surfaced by upstream behavioral/top-expansion scans",
                "preview_summary": (behavioral_preview or {}).get("summary"),
                "preview_blockers": (behavioral_preview or {}).get("blockers"),
                "status": "not_surfaceable_from_current_raw_context" if not raw_ready else "preview_ran_read_only" if behavioral_preview is not None else "preview_skipped",
            },
        }
        blockers = [
            *("raw_swap_context_below_minimum_for_feature_backfill" for _ in [1] if not raw_ready),
            *("token_transfer_context_missing" for _ in [1] if not transfer_ready),
            *("pair_context_missing" for _ in [1] if pair_occurrences <= 0),
            *("cex_deposit_context_missing" for _ in [1] if not token_deposits),
            "feature_backfill_not_executed",
            "materialized_feature_writes_disabled",
            "client_signal_disabled",
            "trade_disabled",
        ]
        token_results.append({
            "chain": clean_chain,
            "token_address": token,
            "token_symbol": profile.get("token_symbol") or "UNKNOWN",
            "raw_context": {
                "local_context_status": profile.get("local_context_status"),
                "transfer_rows": transfers,
                "pair_occurrences": pair_occurrences,
                "raw_swap_rows": raw_swaps,
                "age_days": profile.get("age_days"),
                "raw_ready_for_feature_backfill": raw_ready,
                "min_raw_swaps_required": safe_min_swaps,
            },
            "pipeline_results": pipeline_results,
            "orchestration_status": "raw_context_ready_for_feature_pipeline_replay" if raw_ready else "blocked_raw_context_insufficient",
            "blockers": list(dict.fromkeys(blockers)),
            "next_safe_step": (
                "run_existing_feature_previews_with_token_filters_read_only"
                if raw_ready else
                "targeted_raw_swap_sync_transfer_backfill_plan_read_only"
            ),
        })

    raw_ready_count = sum(1 for row in token_results if row["raw_context"]["raw_ready_for_feature_backfill"])
    blockers = [
        *("token_addresses_required" for _ in [1] if not requested_tokens),
        *("no_tokens_raw_ready_for_feature_backfill" for _ in [1] if requested_tokens and raw_ready_count == 0),
        *("feature_tables_not_materialized" for _ in [1] if (diagnostic.get("summary") or {}).get("materialized_feature_tables_present") == 0),
        "orchestrator_preview_only",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "orchestrator_status": "ready_but_disabled" if requested_tokens else "blocked",
        "chain": clean_chain,
        "token_addresses": requested_tokens,
        "run_existing_previews": bool(run_existing_previews),
        "cex_deposit_limit": safe_cex_limit,
        "min_raw_swaps_for_feature_backfill": safe_min_swaps,
        "feature_wiring_diagnostic_snapshot": {
            "scenario": (diagnostic.get("scenario_diagnosis") or {}).get("scenario"),
            "summary": diagnostic.get("summary"),
            "blockers": diagnostic.get("blockers"),
        },
        "tokens": token_results,
        "summary": {
            "tokens_checked": len(token_results),
            "raw_ready_tokens": raw_ready_count,
            "tokens_requiring_raw_backfill_first": len(token_results) - raw_ready_count,
            "feature_backfill_executable_now": raw_ready_count > 0,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "run_feature_pipeline_replay_preview_for_raw_ready_tokens"
            if raw_ready_count else
            "targeted_seed_raw_context_backfill_plan_read_only"
        ),
        "plain_summary_fr": (
            "L'orchestrateur confirme que le probleme n'est pas un backtest a reparer mais une absence de "
            "contexte brut suffisant pour rejouer les pipelines de features sur ces tokens."
        ),
        **disabled,
    }


def get_manipulation_detection_b_feature_backfill_replay_diagnostic_preview(
    chain: str | None = "bsc",
    token_address: str | None = "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    pool_address: str | None = "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
    dry_run: bool = True,
    sample_limit: int = 25,
) -> dict[str, Any]:
    """Read-only SQL diagnostic before replaying feature pipelines on the B seed raw context."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_token = _clean_address(token_address)
    clean_pool = _clean_address(pool_address)
    safe_sample_limit = max(1, min(int(sample_limit or 25), 100))
    b_token = "0x6bdcce4a559076e37755a78ce0c06214e59e4444"
    b_pool = "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0"
    source_marker = "cex_listing_seed_backfill"
    source_policy = (
        "admin-only read-only B feature backfill replay diagnostic. It reads local raw SQL context "
        "inserted as evidence-only and reports whether existing feature lanes have enough dependencies "
        "to be replayed. It does not materialize feature rows, create labels, mappings, signals or trades."
    )
    disabled = {
        "would_create_feature_tables": False,
        "would_insert_feature_rows": False,
        "would_persist_listing_probability": False,
        "would_insert_ground_truth_rows": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_call_provider": False,
        "would_call_rpc": False,
        "would_call_sqd": False,
        "would_scrape": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "diagnostic_status": "blocked",
            "blockers": ["dry_run_required"],
            **disabled,
        }
    if clean_token != b_token or clean_pool != b_pool:
        return {
            "ok": False,
            "dry_run": True,
            "diagnostic_status": "blocked",
            "chain": clean_chain,
            "token_address": clean_token,
            "pool_address": clean_pool,
            "blockers": ["b_seed_token_and_pool_required"],
            **disabled,
        }

    def table_columns(conn: Any, table_name: str) -> set[str]:
        if not _table_exists(conn, table_name):
            return set()
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}

    def source_clause(columns: set[str]) -> tuple[str, tuple[Any, ...]]:
        if "source_policy" in columns:
            return " AND source_policy LIKE ?", (f"%{source_marker}%",)
        return "", ()

    def alias_source_clause(columns: set[str], alias: str) -> tuple[str, tuple[Any, ...]]:
        if "source_policy" in columns:
            return f" AND {alias}.source_policy LIKE ?", (f"%{source_marker}%",)
        return "", ()

    def event_stats(
        conn: Any,
        table_name: str,
        address_col: str,
        address_value: str,
        participant_cols: tuple[str, ...],
    ) -> dict[str, Any]:
        columns = table_columns(conn, table_name)
        if not columns:
            return {
                "table_exists": False,
                "row_count": 0,
                "unique_tx_hashes": 0,
                "unique_participants": 0,
                "min_block": None,
                "max_block": None,
                "source_policy_bound_rows": 0,
                "sample_rows": [],
            }
        clause, params = source_clause(columns)
        block_col = "block_number" if "block_number" in columns else "NULL"
        count_row = conn.execute(
            f"""
            SELECT COUNT(*), COUNT(DISTINCT tx_hash), MIN({block_col}), MAX({block_col})
            FROM {table_name}
            WHERE lower(chain)=? AND lower({address_col})=?{clause}
            """,
            (clean_chain, address_value, *params),
        ).fetchone()
        participants: set[str] = set()
        for col in participant_cols:
            if col not in columns:
                continue
            for row in conn.execute(
                f"""
                SELECT DISTINCT lower({col})
                FROM {table_name}
                WHERE lower(chain)=? AND lower({address_col})=?{clause}
                LIMIT 500
                """,
                (clean_chain, address_value, *params),
            ).fetchall():
                participant = _clean_address(row[0])
                if participant:
                    participants.add(participant)
        select_cols = [
            col for col in ["tx_hash", "log_index", "block_number", *participant_cols]
            if col in columns
        ]
        sample_rows: list[dict[str, Any]] = []
        if select_cols:
            rows = conn.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM {table_name}
                WHERE lower(chain)=? AND lower({address_col})=?{clause}
                ORDER BY block_number ASC, log_index ASC
                LIMIT ?
                """,
                (clean_chain, address_value, *params, safe_sample_limit),
            ).fetchall()
            sample_rows = [
                {select_cols[idx]: row[idx] for idx in range(len(select_cols))}
                for row in rows
            ]
        return {
            "table_exists": True,
            "row_count": _as_int(count_row[0]) if count_row else 0,
            "unique_tx_hashes": _as_int(count_row[1]) if count_row else 0,
            "unique_participants": len(participants),
            "participant_sample": sorted(participants)[:safe_sample_limit],
            "min_block": count_row[2] if count_row else None,
            "max_block": count_row[3] if count_row else None,
            "source_policy_bound_rows": _as_int(count_row[0]) if "source_policy" in columns else None,
            "sample_rows": sample_rows,
        }

    conn = _engine()._get_db()
    try:
        swap_stats = event_stats(conn, "dex_raw_swap_events", "pair_address", clean_pool, ("sender", "recipient"))
        sync_stats = event_stats(conn, "dex_raw_sync_events", "pair_address", clean_pool, ())
        transfer_stats = event_stats(conn, "erc20_transfer_events", "token_address", clean_token, ("from_address", "to_address"))

        swap_columns = table_columns(conn, "dex_raw_swap_events")
        sync_columns = table_columns(conn, "dex_raw_sync_events")
        sync_swap_tx_overlap = 0
        if swap_columns and sync_columns and {"tx_hash", "chain", "pair_address"}.issubset(swap_columns | sync_columns):
            swap_clause, swap_params = alias_source_clause(swap_columns, "s")
            sync_clause, sync_params = alias_source_clause(sync_columns, "y")
            sync_swap_tx_overlap = _as_int(conn.execute(
                f"""
                SELECT COUNT(DISTINCT s.tx_hash)
                FROM dex_raw_swap_events s
                INNER JOIN dex_raw_sync_events y ON lower(y.tx_hash)=lower(s.tx_hash)
                WHERE lower(s.chain)=? AND lower(s.pair_address)=?{swap_clause}
                  AND lower(y.chain)=? AND lower(y.pair_address)=?{sync_clause}
                """,
                (clean_chain, clean_pool, *swap_params, clean_chain, clean_pool, *sync_params),
            ).fetchone()[0])

        token_transfer_rows = 0
        token_transfer_wallets = 0
        if _table_exists(conn, "token_transfers"):
            token_transfer_rows = _as_int(conn.execute(
                "SELECT COUNT(*) FROM token_transfers WHERE lower(chain)=? AND lower(token)=?",
                (clean_chain, clean_token),
            ).fetchone()[0])
            token_transfer_wallets = _as_int(conn.execute(
                """
                SELECT COUNT(DISTINCT wallet)
                FROM (
                    SELECT lower(from_addr) AS wallet FROM token_transfers WHERE lower(chain)=? AND lower(token)=?
                    UNION
                    SELECT lower(to_addr) AS wallet FROM token_transfers WHERE lower(chain)=? AND lower(token)=?
                )
                WHERE wallet IS NOT NULL AND wallet != ''
                """,
                (clean_chain, clean_token, clean_chain, clean_token),
            ).fetchone()[0])

        pair_context: list[dict[str, Any]] = []
        if _table_exists(conn, "pair_tokens"):
            for row in conn.execute(
                """
                SELECT lower(pool), lower(token0), lower(token1), rpc_source, observed_at
                FROM pair_tokens
                WHERE lower(chain)=? AND lower(pool)=?
                LIMIT 5
                """,
                (clean_chain, clean_pool),
            ).fetchall():
                pair_context.append({
                    "pool_address": row[0],
                    "token0": row[1],
                    "token1": row[2],
                    "rpc_source": row[3],
                    "observed_at": row[4],
                })

        participant_addresses = sorted(set(swap_stats.get("participant_sample") or []) | set(transfer_stats.get("participant_sample") or []))
        wallet_state_matches = 0
        wallet_state_labeled = 0
        if participant_addresses and _table_exists(conn, "wallet_chain_state"):
            placeholders = ",".join("?" for _ in participant_addresses)
            rows = conn.execute(
                f"""
                SELECT COUNT(*), SUM(CASE WHEN COALESCE(label, entity, '') != '' THEN 1 ELSE 0 END)
                FROM wallet_chain_state
                WHERE lower(chain)=? AND lower(address) IN ({placeholders})
                """,
                (clean_chain, *participant_addresses),
            ).fetchone()
            wallet_state_matches = _as_int(rows[0]) if rows else 0
            wallet_state_labeled = _as_int(rows[1]) if rows else 0
    finally:
        conn.close()

    raw_ready = (
        _as_int(swap_stats.get("row_count")) >= 50
        and _as_int(sync_stats.get("row_count")) > 0
        and _as_int(transfer_stats.get("row_count")) > 0
        and bool(pair_context)
    )
    pipeline_diagnostics = {
        "cex_deposit_flow_scan": {
            "existing_function": "get_token_transfer_cex_deposit_scan",
            "data_dependencies_met": _as_int(transfer_stats.get("row_count")) > 0,
            "raw_transfer_event_rows": transfer_stats.get("row_count"),
            "legacy_token_transfer_rows": token_transfer_rows,
            "status": "raw_context_present_but_reference_or_token_filter_missing",
            "blockers": [
                "no_materialized_cex_deposit_rows_for_b_seed",
                "cex_hot_wallet_reference_or_token_filter_not_verified",
                "no_feature_row_write_in_this_diagnostic",
            ],
        },
        "adaptive_accumulator_funder_graph_scan": {
            "existing_function": "get_adaptive_accumulator_funder_graph_scan",
            "data_dependencies_met": _as_int(swap_stats.get("unique_participants")) > 0,
            "swap_participants": swap_stats.get("unique_participants"),
            "transfer_participants": transfer_stats.get("unique_participants"),
            "wallet_chain_state_matches": wallet_state_matches,
            "wallet_chain_state_labeled": wallet_state_labeled,
            "status": "needs_bounded_funding_expansion_or_local_wallet_state",
            "blockers": [
                *("wallet_chain_state_missing_for_b_participants" for _ in [1] if wallet_state_matches == 0),
                "upstream_funder_edges_not_materialized_for_b_seed",
                "no_feature_row_write_in_this_diagnostic",
            ],
        },
        "stealth_accumulation_scan": {
            "existing_function": "get_manipulation_detection_stealth_accumulation_anomaly_scan_preview",
            "data_dependencies_met": raw_ready,
            "pair_context_rows": len(pair_context),
            "raw_swap_rows": swap_stats.get("row_count"),
            "raw_sync_rows": sync_stats.get("row_count"),
            "raw_transfer_event_rows": transfer_stats.get("row_count"),
            "status": "ready_for_token_filter_preview" if raw_ready else "raw_context_incomplete",
            "blockers": [
                *("pair_context_missing" for _ in [1] if not pair_context),
                *("raw_swap_rows_below_50" for _ in [1] if _as_int(swap_stats.get("row_count")) < 50),
                *("raw_sync_rows_missing" for _ in [1] if _as_int(sync_stats.get("row_count")) <= 0),
                *("raw_transfer_event_rows_missing" for _ in [1] if _as_int(transfer_stats.get("row_count")) <= 0),
                "existing_preview_needs_explicit_token_filter",
                "no_feature_row_write_in_this_diagnostic",
            ],
        },
        "behavioral_evidence_bridge": {
            "existing_function": "get_manipulation_detection_behavioral_evidence_bridge",
            "data_dependencies_met": raw_ready,
            "status": "blocked_until_upstream_feature_previews_accept_explicit_token",
            "blockers": [
                "upstream_cex_deposit_funder_stealth_outputs_not_materialized",
                "candidate_injection_or_explicit_token_filter_missing",
                "no_listing_probability_score_persisted",
            ],
        },
    }
    blockers = [
        *("raw_sql_context_incomplete" for _ in [1] if not raw_ready),
        "feature_replay_not_executed",
        "feature_tables_not_materialized",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "diagnostic_status": "ready_but_disabled",
        "chain": clean_chain,
        "token_address": clean_token,
        "token_symbol": "B",
        "pool_address": clean_pool,
        "collection_context": source_marker,
        "raw_sql_context": {
            "pair_context": pair_context,
            "swap_events": swap_stats,
            "sync_events": sync_stats,
            "erc20_transfer_events": transfer_stats,
            "legacy_token_transfers": {
                "row_count": token_transfer_rows,
                "unique_wallets": token_transfer_wallets,
            },
            "sync_swap_tx_overlap": sync_swap_tx_overlap,
            "sync_swap_binding_ok": sync_swap_tx_overlap > 0,
        },
        "pipeline_diagnostics": pipeline_diagnostics,
        "summary": {
            "raw_sql_visible": raw_ready,
            "raw_swap_rows": swap_stats.get("row_count"),
            "raw_sync_rows": sync_stats.get("row_count"),
            "raw_transfer_event_rows": transfer_stats.get("row_count"),
            "sync_swap_tx_overlap": sync_swap_tx_overlap,
            "pipelines_with_dependencies_met": sum(
                1 for row in pipeline_diagnostics.values() if row.get("data_dependencies_met")
            ),
            "feature_backfill_executable_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": "add_explicit_token_filter_support_to_existing_feature_previews_read_only",
        "plain_summary_fr": (
            "La data brute B est maintenant visible en SQL. Le blocage restant n'est pas la collecte brute, "
            "mais le replay des lanes de features existantes avec un token explicite, sans creer de lane ad-hoc."
        ),
        **disabled,
    }


def get_manipulation_detection_b_cex_destination_wallet_reference_repair_preview(
    chain: str | None = "bsc",
    token_address: str | None = "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    dry_run: bool = True,
    limit: int = 20,
) -> dict[str, Any]:
    """Read-only diagnostic of B transfer destinations before any CEX label/reference repair."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_token = _clean_address(token_address)
    b_token = "0x6bdcce4a559076e37755a78ce0c06214e59e4444"
    safe_limit = max(1, min(int(limit or 20), 100))
    cex_terms = ("exchange", "cex", "binance", "coinbase", "okx", "kraken", "kucoin", "bitget", "mexc", "gate")
    dex_risk_terms = ("router", "dex", "swap", "pancake", "uniswap", "sushi", "pair", "pool", "bridge", "mixer")
    source_policy = (
        "admin-only read-only B CEX destination wallet reference repair preview. It reads B raw Transfer "
        "destinations and local wallet_chain_state only. It does not create labels, update wallet state, "
        "persist evidence, create scores, signals, mappings, trades or opt-ins."
    )
    disabled = {
        "would_create_cex_label": False,
        "would_update_wallet_state": False,
        "would_persist_wallet_reference_evidence": False,
        "would_persist_listing_probability": False,
        "would_insert_ground_truth_rows": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_create_dex_mapping": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_call_provider": False,
        "would_scrape": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "preview_status": "blocked",
            "blockers": ["dry_run_required"],
            **disabled,
        }
    if clean_token != b_token:
        return {
            "ok": False,
            "dry_run": True,
            "preview_status": "blocked",
            "chain": clean_chain,
            "token_address": clean_token,
            "blockers": ["b_seed_token_required"],
            **disabled,
        }

    def decode_json(value: Any) -> Any:
        try:
            return json.loads(str(value or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            return [] if str(value or "").strip().startswith("[") else {}

    def source_backed(label_sources_json: Any, source_attribution_json: Any) -> bool:
        label_sources = decode_json(label_sources_json)
        source_attribution = decode_json(source_attribution_json)
        return bool(label_sources or source_attribution)

    conn = _engine()._get_db()
    try:
        if not _table_exists(conn, "erc20_transfer_events"):
            return {
                "ok": True,
                "dry_run": True,
                "preview_status": "blocked",
                "chain": clean_chain,
                "token_address": clean_token,
                "destinations": [],
                "summary": {
                    "raw_transfer_rows": 0,
                    "unique_destinations": 0,
                    "source_backed_cex_destinations": 0,
                    "exchange_like_unbacked_destinations": 0,
                    "unknown_destinations": 0,
                    "contract_or_router_risk_destinations": 0,
                    "cex_deposit_flow_unlockable_now": 0,
                    "client_signal_ready": False,
                    "trade_ready": False,
                },
                "blockers": ["erc20_transfer_events_missing"],
                **disabled,
            }
        rows = conn.execute(
            """
            SELECT
                lower(ev.to_address) AS to_address,
                COUNT(*) AS transfer_count,
                SUM(CAST(ev.value_raw AS REAL)) AS total_value_raw,
                MIN(ev.block_number) AS first_block,
                MAX(ev.block_number) AS last_block,
                COUNT(DISTINCT ev.tx_hash) AS unique_txs,
                ws.label, ws.entity, ws.confidence, ws.address_kind, ws.is_contract,
                ws.label_sources_json, ws.source_attribution_json, ws.observed_at
            FROM erc20_transfer_events ev
            LEFT JOIN wallet_chain_state ws
              ON lower(ws.chain)=lower(ev.chain)
             AND lower(ws.address)=lower(ev.to_address)
            WHERE lower(ev.chain)=? AND lower(ev.token_address)=?
            GROUP BY lower(ev.to_address), ws.label, ws.entity, ws.confidence, ws.address_kind,
                     ws.is_contract, ws.label_sources_json, ws.source_attribution_json, ws.observed_at
            ORDER BY transfer_count DESC, total_value_raw DESC
            LIMIT ?
            """,
            (clean_chain, clean_token, safe_limit),
        ).fetchall()
        total_row = conn.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT lower(to_address))
            FROM erc20_transfer_events
            WHERE lower(chain)=? AND lower(token_address)=?
            """,
            (clean_chain, clean_token),
        ).fetchone()
        destinations: list[dict[str, Any]] = []
        for row in rows:
            destination = _clean_address(row[0])
            label = str(row[6] or "")
            entity = str(row[7] or "")
            confidence = row[8]
            address_kind = str(row[9] or "")
            is_contract = bool(row[10])
            backed = source_backed(row[11], row[12])
            text = " ".join([label, entity, address_kind]).lower()
            cex_like = any(term in text for term in cex_terms)
            contract_or_router_risk = bool(is_contract or any(term in text for term in dex_risk_terms))
            if cex_like and backed and not contract_or_router_risk:
                status = "source_backed_cex"
            elif cex_like:
                status = "exchange_like_unbacked"
            elif contract_or_router_risk:
                status = "contract_or_router_risk"
            else:
                status = "unknown"
            distinct_tokens_to_destination = 0
            if _table_exists(conn, "erc20_transfer_events"):
                distinct_tokens_to_destination += _as_int(conn.execute(
                    """
                    SELECT COUNT(DISTINCT lower(token_address))
                    FROM erc20_transfer_events
                    WHERE lower(chain)=? AND lower(to_address)=?
                    """,
                    (clean_chain, destination),
                ).fetchone()[0])
            if _table_exists(conn, "token_transfers"):
                distinct_tokens_to_destination += _as_int(conn.execute(
                    """
                    SELECT COUNT(DISTINCT lower(token))
                    FROM token_transfers
                    WHERE lower(chain)=? AND lower(to_addr)=?
                    """,
                    (clean_chain, destination),
                ).fetchone()[0])
            destinations.append({
                "destination_address": destination,
                "transfer_count": _as_int(row[1]),
                "total_value_raw": str(row[2] or "0"),
                "first_block": row[3],
                "last_block": row[4],
                "unique_txs": _as_int(row[5]),
                "wallet_state_present": row[6] is not None or row[7] is not None or row[13] is not None,
                "current_label": label or None,
                "current_entity": entity or None,
                "current_confidence": confidence,
                "current_address_kind": address_kind or None,
                "is_contract": is_contract,
                "label_source_backed": backed,
                "distinct_tokens_to_destination": distinct_tokens_to_destination,
                "destination_status": status,
                "would_unlock_cex_deposit_flow_if_source_backed": status == "exchange_like_unbacked",
                "blockers": list(dict.fromkeys([
                    *("wallet_chain_state_missing" for _ in [1] if not (row[6] is not None or row[7] is not None or row[13] is not None)),
                    *("exchange_like_label_not_source_backed" for _ in [1] if cex_like and not backed),
                    *("contract_or_router_risk_requires_not_cex_filter" for _ in [1] if contract_or_router_risk),
                    *("not_exchange_like_locally" for _ in [1] if not cex_like),
                    "read_only_no_label_created",
                ])),
            })
    finally:
        conn.close()

    status_counts: dict[str, int] = {}
    for row in destinations:
        status = str(row.get("destination_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    source_backed_cex = status_counts.get("source_backed_cex", 0)
    exchange_like_unbacked = status_counts.get("exchange_like_unbacked", 0)
    unknown = status_counts.get("unknown", 0)
    contract_risk = status_counts.get("contract_or_router_risk", 0)
    blockers = list(dict.fromkeys([
        *("no_b_raw_transfer_destinations" for _ in [1] if not destinations),
        *("no_source_backed_cex_destination_for_b" for _ in [1] if destinations and not source_backed_cex),
        *("exchange_like_destinations_need_source_backing" for _ in [1] if exchange_like_unbacked),
        *("unknown_destinations_need_reference_lookup" for _ in [1] if unknown),
        *("contract_or_router_destinations_must_not_be_treated_as_cex" for _ in [1] if contract_risk),
        "no_label_or_wallet_state_write_in_this_preview",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready_but_disabled",
        "chain": clean_chain,
        "token_address": clean_token,
        "token_symbol": "B",
        "limit": safe_limit,
        "destinations": destinations,
        "classification_policy": {
            "source_backed_cex": "local CEX-like label/entity/address_kind plus label source attribution and no router/contract risk",
            "exchange_like_unbacked": "local CEX-like text exists but source attribution is missing or contract/router risk exists",
            "unknown": "no local CEX-like wallet state",
            "contract_or_router_risk": "contract/router/dex/bridge/mixer-like local context must not become a CEX deposit",
        },
        "summary": {
            "raw_transfer_rows": _as_int(total_row[0]) if total_row else 0,
            "unique_destinations": _as_int(total_row[1]) if total_row else 0,
            "destinations_returned": len(destinations),
            "source_backed_cex_destinations": source_backed_cex,
            "exchange_like_unbacked_destinations": exchange_like_unbacked,
            "unknown_destinations": unknown,
            "contract_or_router_risk_destinations": contract_risk,
            "cex_deposit_flow_unlockable_now": source_backed_cex,
            "source_repair_candidates": exchange_like_unbacked,
            "external_reference_lookup_candidates": unknown,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "rerun_cex_deposit_scan_for_b_read_only"
            if source_backed_cex else
            "source_backed_cex_wallet_evidence_intake_or_external_reference_lookup_read_only"
            if exchange_like_unbacked or unknown else
            "inspect_contract_router_destinations_read_only"
        ),
        "plain_summary_fr": (
            "Cette preview explique pourquoi B ne score pas encore en CEX deposit: les destinations des transfers "
            "doivent etre reconnues comme CEX source-backed avant que le pipeline puisse les compter."
        ),
        **disabled,
    }


def get_manipulation_detection_b_destination_holder_distribution_flow_check_preview(
    chain: str | None = "bsc",
    token_address: str | None = "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    pool_address: str | None = "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
    dry_run: bool = True,
    limit: int = 20,
) -> dict[str, Any]:
    """Read-only flow classification for B destinations after raw transfer intake."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_token = _clean_address(token_address)
    clean_pool = _clean_address(pool_address)
    b_token = "0x6bdcce4a559076e37755a78ce0c06214e59e4444"
    b_pool = "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0"
    safe_limit = max(1, min(int(limit or 20), 100))
    source_policy = (
        "admin-only read-only B destination holder/distribution flow check. It classifies B raw transfer "
        "destinations using local erc20_transfer_events, dex_raw_swap_events, transactions and wallet_chain_state. "
        "It does not create labels, persist evidence, create scores, signals, mappings, trades or opt-ins."
    )
    disabled = {
        "would_create_cex_label": False,
        "would_update_wallet_state": False,
        "would_persist_flow_classification": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_create_dex_mapping": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_call_provider": False,
        "would_scrape": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "flow_check_status": "blocked",
            "blockers": ["dry_run_required"],
            **disabled,
        }
    if clean_token != b_token or clean_pool != b_pool:
        return {
            "ok": False,
            "dry_run": True,
            "flow_check_status": "blocked",
            "chain": clean_chain,
            "token_address": clean_token,
            "pool_address": clean_pool,
            "blockers": ["b_seed_token_and_pool_required"],
            **disabled,
        }

    conn = _engine()._get_db()
    try:
        if not _table_exists(conn, "erc20_transfer_events"):
            return {
                "ok": True,
                "dry_run": True,
                "flow_check_status": "blocked",
                "chain": clean_chain,
                "token_address": clean_token,
                "destinations": [],
                "summary": {
                    "raw_transfer_rows": 0,
                    "unique_destinations": 0,
                    "holder_candidates": 0,
                    "distributors": 0,
                    "intermediaries": 0,
                    "contract_router_risk": 0,
                    "unknown_insufficient_history": 0,
                    "client_signal_ready": False,
                    "trade_ready": False,
                },
                "blockers": ["erc20_transfer_events_missing"],
                **disabled,
            }
        destination_rows = conn.execute(
            """
            SELECT lower(to_address), COUNT(*), SUM(CAST(value_raw AS REAL)), MIN(block_number), MAX(block_number)
            FROM erc20_transfer_events
            WHERE lower(chain)=? AND lower(token_address)=?
            GROUP BY lower(to_address)
            ORDER BY COUNT(*) DESC, SUM(CAST(value_raw AS REAL)) DESC
            LIMIT ?
            """,
            (clean_chain, clean_token, safe_limit),
        ).fetchall()
        total_row = conn.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT lower(to_address))
            FROM erc20_transfer_events
            WHERE lower(chain)=? AND lower(token_address)=?
            """,
            (clean_chain, clean_token),
        ).fetchone()
        destinations: list[dict[str, Any]] = []
        for row in destination_rows:
            destination = _clean_address(row[0])
            received_count = _as_int(row[1])
            received_value = float(row[2] or 0.0)
            first_block = _as_int(row[3])
            last_block = _as_int(row[4])
            outgoing_row = conn.execute(
                """
                SELECT COUNT(*), SUM(CAST(value_raw AS REAL)), COUNT(DISTINCT lower(to_address)),
                       MIN(block_number), MAX(block_number)
                FROM erc20_transfer_events
                WHERE lower(chain)=? AND lower(token_address)=? AND lower(from_address)=?
                """,
                (clean_chain, clean_token, destination),
            ).fetchone()
            outgoing_count = _as_int(outgoing_row[0]) if outgoing_row else 0
            outgoing_value = float(outgoing_row[1] or 0.0) if outgoing_row else 0.0
            onward_destinations = _as_int(outgoing_row[2]) if outgoing_row else 0
            outgoing_first_block = outgoing_row[3] if outgoing_row else None
            outgoing_last_block = outgoing_row[4] if outgoing_row else None
            pool_return_count = _as_int(conn.execute(
                """
                SELECT COUNT(*)
                FROM erc20_transfer_events
                WHERE lower(chain)=? AND lower(token_address)=? AND lower(from_address)=? AND lower(to_address)=?
                """,
                (clean_chain, clean_token, destination, clean_pool),
            ).fetchone()[0])
            swap_participation = 0
            if _table_exists(conn, "dex_raw_swap_events"):
                swap_participation = _as_int(conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM dex_raw_swap_events
                    WHERE lower(chain)=? AND (lower(sender)=? OR lower(recipient)=?)
                    """,
                    (clean_chain, destination, destination),
                ).fetchone()[0])
            native_tx_count = 0
            first_native_tx = None
            last_native_tx = None
            if _table_exists(conn, "transactions"):
                tx_row = conn.execute(
                    """
                    SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
                    FROM transactions
                    WHERE lower(chain)=? AND (lower(from_addr)=? OR lower(to_addr)=?)
                    """,
                    (clean_chain, destination, destination),
                ).fetchone()
                native_tx_count = _as_int(tx_row[0]) if tx_row else 0
                first_native_tx = tx_row[1] if tx_row else None
                last_native_tx = tx_row[2] if tx_row else None
            wallet_row = None
            if _table_exists(conn, "wallet_chain_state"):
                wallet_row = conn.execute(
                    """
                    SELECT label, entity, confidence, address_kind, is_contract, observed_at
                    FROM wallet_chain_state
                    WHERE lower(chain)=? AND lower(address)=?
                    """,
                    (clean_chain, destination),
                ).fetchone()
            label = str(wallet_row[0] or "") if wallet_row else ""
            entity = str(wallet_row[1] or "") if wallet_row else ""
            address_kind = str(wallet_row[3] or "") if wallet_row else ""
            is_contract = bool(wallet_row[4]) if wallet_row else False
            text = " ".join([label, entity, address_kind]).lower()
            contract_router_risk = bool(
                is_contract
                or any(term in text for term in ("contract", "router", "dex", "swap", "bridge", "mixer", "pool"))
                or destination == clean_pool
            )
            sent_ratio = (outgoing_value / received_value) if received_value > 0 else 0.0
            if contract_router_risk:
                classification = "contract_router_risk"
            elif outgoing_count == 0 and swap_participation == 0:
                classification = "holder_candidate"
            elif pool_return_count > 0 or swap_participation > 0 or sent_ratio >= 0.50:
                classification = "distributor"
            elif outgoing_count > 0:
                classification = "intermediary"
            else:
                classification = "unknown_insufficient_history"
            destinations.append({
                "destination_address": destination,
                "received_transfers": received_count,
                "received_value_raw": str(row[2] or "0"),
                "first_receive_block": first_block or None,
                "last_receive_block": last_block or None,
                "outgoing_b_transfers": outgoing_count,
                "outgoing_b_value_raw": str(outgoing_row[1] or "0") if outgoing_row else "0",
                "outgoing_value_ratio": round(sent_ratio, 6) if received_value > 0 else None,
                "onward_destinations": onward_destinations,
                "outgoing_first_block": outgoing_first_block,
                "outgoing_last_block": outgoing_last_block,
                "pool_return_transfers": pool_return_count,
                "dex_raw_swap_participation": swap_participation,
                "native_tx_count": native_tx_count,
                "first_native_tx_timestamp": first_native_tx,
                "last_native_tx_timestamp": last_native_tx,
                "wallet_state": {
                    "present": wallet_row is not None,
                    "label": label or None,
                    "entity": entity or None,
                    "confidence": wallet_row[2] if wallet_row else None,
                    "address_kind": address_kind or None,
                    "is_contract": is_contract,
                    "observed_at": wallet_row[5] if wallet_row else None,
                },
                "flow_classification": classification,
                "blockers": list(dict.fromkeys([
                    *("contract_or_router_risk_do_not_count_as_holder" for _ in [1] if contract_router_risk),
                    *("no_outgoing_b_seen_local_holder_proxy_only" for _ in [1] if classification == "holder_candidate"),
                    *("b_outgoing_or_pool_return_observed" for _ in [1] if classification == "distributor"),
                    *("onward_routing_requires_next_hop_reference_lookup" for _ in [1] if classification == "intermediary"),
                    *("native_tx_history_missing_or_sparse" for _ in [1] if native_tx_count == 0),
                    "read_only_no_classification_persisted",
                ])),
            })
    finally:
        conn.close()

    class_counts: dict[str, int] = {}
    for destination in destinations:
        classification = str(destination.get("flow_classification") or "unknown_insufficient_history")
        class_counts[classification] = class_counts.get(classification, 0) + 1
    holder_candidates = class_counts.get("holder_candidate", 0)
    distributors = class_counts.get("distributor", 0)
    intermediaries = class_counts.get("intermediary", 0)
    contract_risk = class_counts.get("contract_router_risk", 0)
    unknown_history = class_counts.get("unknown_insufficient_history", 0)
    blockers = list(dict.fromkeys([
        *("no_b_destinations_to_classify" for _ in [1] if not destinations),
        *("contract_router_destinations_require_manual_contract_role_check" for _ in [1] if contract_risk),
        *("distribution_or_pool_return_observed" for _ in [1] if distributors),
        *("intermediary_next_hop_reference_lookup_needed" for _ in [1] if intermediaries),
        *("holder_candidates_are_local_proxy_not_balance_snapshot" for _ in [1] if holder_candidates),
        "no_signal_or_trade_from_flow_classification",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    next_step = (
        "contract_role_source_lookup_read_only"
        if contract_risk else
        "holder_balance_snapshot_or_next_hop_reference_lookup_read_only"
        if holder_candidates or intermediaries else
        "abandon_b_as_cex_listing_positive_or_collect_new_native_positive"
    )
    return {
        "ok": True,
        "dry_run": True,
        "flow_check_status": "ready_but_disabled",
        "chain": clean_chain,
        "token_address": clean_token,
        "token_symbol": "B",
        "pool_address": clean_pool,
        "destinations": destinations,
        "classification_policy": {
            "holder_candidate": "received B and no local outgoing B or DEX swap participation observed; proxy only, not a balance snapshot",
            "distributor": "outgoing B, pool return, DEX swap participation, or >=50% local outgoing value observed",
            "intermediary": "outgoing B exists without clear pool return; next-hop reference lookup needed",
            "contract_router_risk": "contract/router/pool/bridge/mixer-like local context; not a holder or CEX proof",
            "unknown_insufficient_history": "local history too sparse for a stronger classification",
        },
        "summary": {
            "raw_transfer_rows": _as_int(total_row[0]) if total_row else 0,
            "unique_destinations": _as_int(total_row[1]) if total_row else 0,
            "destinations_returned": len(destinations),
            "holder_candidates": holder_candidates,
            "distributors": distributors,
            "intermediaries": intermediaries,
            "contract_router_risk": contract_risk,
            "unknown_insufficient_history": unknown_history,
            "b_cex_listing_positive_supported_now": False,
            "b_stealth_non_cex_research_supported": holder_candidates > 0 and distributors == 0,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": next_step,
        "plain_summary_fr": (
            "Cette preview dit si B ressemble plutot a accumulation stealth, distribution ou routing inconnu. "
            "Elle ne transforme pas ces indices en score ni en signal."
        ),
        **disabled,
    }


def get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan(
    chain: str | None = "bsc",
    token_addresses: list[str] | str | None = None,
    dry_run: bool = True,
    block_padding: int = 50_000,
    max_window_blocks: int = 250_000,
) -> dict[str, Any]:
    """Read-only raw-context plan for seed CEX listing tokens before feature backfill."""
    clean_chain = str(chain or "bsc").strip().lower()
    safe_padding = max(1, min(int(block_padding or 50_000), 500_000))
    safe_max_window = max(10_000, min(int(max_window_blocks or 250_000), 2_000_000))
    seed_by_token = {
        row["token_address"]: row
        for row in _positive_seed_ground_truth_rows(clean_chain)
    }
    requested_tokens = _parse_token_addresses(token_addresses)
    if not requested_tokens:
        requested_tokens = [
            row["token_address"]
            for row in _positive_seed_ground_truth_rows(clean_chain)
            if row.get("token_symbol") in {"LAB", "B"}
        ]
    requested_tokens = requested_tokens[:20]
    source_policy = (
        "admin-only read-only LAB/B targeted raw context backfill plan. It reads local token, pair and raw "
        "event tables to define bounded future Swap/Sync/Transfer lookup filters. It does not call RPC, SQD, "
        "explorers or providers and writes nothing."
    )
    disabled = {
        "would_call_provider": False,
        "would_call_rpc": False,
        "would_call_sqd": False,
        "would_scrape": False,
        "would_insert_raw_swap_events": False,
        "would_insert_raw_sync_events": False,
        "would_insert_erc20_transfer_events": False,
        "would_create_feature_tables": False,
        "would_insert_feature_rows": False,
        "would_insert_ground_truth_rows": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "plan_status": "blocked",
            "blockers": ["dry_run_required"],
            "tokens": [],
            **disabled,
        }

    orchestrator = get_manipulation_detection_feature_backfill_orchestrator_preview(
        chain=clean_chain,
        token_addresses=requested_tokens,
        dry_run=True,
        run_existing_previews=False,
        cex_deposit_limit=100,
        min_raw_swaps_for_feature_backfill=50,
    )
    profiles = _local_token_context_profiles(clean_chain, requested_tokens)
    conn = _engine()._get_db()
    try:
        table_counts = {
            table: _table_count(conn, table)
            for table in [
                "pair_tokens",
                "dex_raw_swap_events",
                "dex_raw_sync_events",
                "erc20_transfer_events",
                "token_transfers",
            ]
        }
        token_plans: list[dict[str, Any]] = []
        for token in requested_tokens:
            seed = seed_by_token.get(token, {})
            profile = profiles.get(token) or {}
            transfer_rows = []
            if _table_exists(conn, "token_transfers"):
                transfer_rows = conn.execute(
                    """
                    SELECT MIN(block_number), MAX(block_number), MIN(timestamp), MAX(timestamp), COUNT(*)
                    FROM token_transfers
                    WHERE lower(chain)=? AND lower(token)=?
                    """,
                    (clean_chain, token),
                ).fetchone() or []
            min_block = _as_int(transfer_rows[0]) if transfer_rows else 0
            max_block = _as_int(transfer_rows[1]) if transfer_rows else 0
            transfer_count = _as_int(transfer_rows[4]) if transfer_rows else 0
            pair_rows = []
            if _table_exists(conn, "pair_tokens"):
                pair_rows = conn.execute(
                    """
                    SELECT lower(pool), lower(token0), lower(token1), rpc_source, observed_at
                    FROM pair_tokens
                    WHERE lower(chain)=? AND (lower(token0)=? OR lower(token1)=?)
                    ORDER BY observed_at DESC
                    LIMIT 10
                    """,
                    (clean_chain, token, token),
                ).fetchall()
            pools = [str(row[0]).lower() for row in pair_rows if row[0]]
            pool_context = []
            for row in pair_rows:
                pool = str(row[0]).lower()
                swap_count = 0
                sync_count = 0
                if _table_exists(conn, "dex_raw_swap_events"):
                    swap_count = _as_int(conn.execute(
                        "SELECT COUNT(*) FROM dex_raw_swap_events WHERE lower(chain)=? AND lower(pair_address)=?",
                        (clean_chain, pool),
                    ).fetchone()[0])
                if _table_exists(conn, "dex_raw_sync_events"):
                    sync_count = _as_int(conn.execute(
                        "SELECT COUNT(*) FROM dex_raw_sync_events WHERE lower(chain)=? AND lower(pair_address)=?",
                        (clean_chain, pool),
                    ).fetchone()[0])
                pool_context.append({
                    "pool_address": pool,
                    "token0": row[1],
                    "token1": row[2],
                    "rpc_source": row[3],
                    "observed_at": row[4],
                    "local_raw_swap_rows": swap_count,
                    "local_raw_sync_rows": sync_count,
                })

            if min_block and max_block:
                from_block = max(0, min_block - safe_padding)
                to_block = min(max_block + safe_padding, from_block + safe_max_window)
            else:
                from_block = None
                to_block = None
            announcement_ts = _parse_iso_timestamp(seed.get("announcement_at"))
            listing_ts = _parse_iso_timestamp(seed.get("listing_at"))
            planned_filters = {
                "pair_discovery": {
                    "required": not bool(pools),
                    "reason": "no local pair_tokens pool for token" if not pools else "local pair_tokens pool exists",
                    "future_method": "bounded factory/getPair or source-backed pair discovery, read-only first",
                    "token_address": token,
                },
                "swap_logs": {
                    "required": bool(pools),
                    "event": "UniswapV2/PancakeV2 Swap(address,uint256,uint256,uint256,uint256,address)",
                    "pair_addresses": pools,
                    "from_block": from_block,
                    "to_block": to_block,
                    "blocked_until_pair_discovered": not bool(pools),
                },
                "sync_logs": {
                    "required": bool(pools),
                    "event": "UniswapV2/PancakeV2 Sync(uint112,uint112)",
                    "pair_addresses": pools,
                    "from_block": from_block,
                    "to_block": to_block,
                    "blocked_until_pair_discovered": not bool(pools),
                },
                "transfer_logs": {
                    "required": True,
                    "event": "ERC20 Transfer(address,address,uint256)",
                    "token_address": token,
                    "from_block": from_block,
                    "to_block": to_block,
                    "current_local_token_transfers": transfer_count,
                },
            }
            blockers = [
                *("pair_discovery_required_before_swap_sync_lookup" for _ in [1] if not pools),
                *("block_window_missing_from_local_transfers" for _ in [1] if not min_block or not max_block),
                *("raw_swap_context_missing" for _ in [1] if not _as_int(profile.get("raw_swap_rows"))),
                *("raw_sync_context_missing" for _ in [1] if pools and not any(_as_int(row.get("local_raw_sync_rows")) for row in pool_context)),
                "future_lookup_must_be_bounded_and_confirmed",
                "no_raw_event_persistence_in_this_plan",
                "feature_backfill_still_blocked",
                "client_signal_disabled",
                "trade_disabled",
            ]
            token_plans.append({
                "chain": clean_chain,
                "token_address": token,
                "token_symbol": seed.get("token_symbol") or profile.get("token_symbol") or "UNKNOWN",
                "seed_listing_context": {
                    "cex_name": seed.get("cex_name"),
                    "market_pair": seed.get("market_pair"),
                    "announcement_at": seed.get("announcement_at"),
                    "listing_at": seed.get("listing_at"),
                    "announcement_timestamp": announcement_ts,
                    "listing_timestamp": listing_ts,
                },
                "current_local_context": {
                    "transfer_rows": transfer_count,
                    "pair_occurrences": len(pools),
                    "raw_swap_rows": profile.get("raw_swap_rows"),
                    "local_context_status": profile.get("local_context_status"),
                    "min_transfer_block": min_block or None,
                    "max_transfer_block": max_block or None,
                },
                "pool_context": pool_context,
                "planned_filters": planned_filters,
                "plan_readiness": "ready_for_bounded_raw_lookup_dry_run" if from_block is not None and pools else "blocked_needs_pair_or_block_window",
                "blockers": list(dict.fromkeys(blockers)),
                "next_safe_step": (
                    "bounded_raw_swap_sync_transfer_lookup_dry_run"
                    if from_block is not None and pools else
                    "bounded_pair_discovery_then_raw_lookup_plan"
                ),
            })
    finally:
        conn.close()

    ready_tokens = sum(1 for row in token_plans if row.get("plan_readiness") == "ready_for_bounded_raw_lookup_dry_run")
    blockers = [
        *("token_addresses_required" for _ in [1] if not requested_tokens),
        *("no_token_ready_for_raw_lookup" for _ in [1] if requested_tokens and not ready_tokens),
        "raw_lookup_not_executed",
        "raw_event_persistence_disabled",
        "feature_backfill_not_executed",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if requested_tokens else "blocked",
        "chain": clean_chain,
        "block_padding": safe_padding,
        "max_window_blocks": safe_max_window,
        "table_counts": table_counts,
        "feature_backfill_orchestrator_snapshot": {
            "summary": orchestrator.get("summary"),
            "blockers": orchestrator.get("blockers"),
            "next_safe_step": orchestrator.get("next_safe_step"),
        },
        "tokens": token_plans,
        "summary": {
            "tokens_planned": len(token_plans),
            "ready_for_bounded_raw_lookup": ready_tokens,
            "tokens_needing_pair_discovery_first": sum(1 for row in token_plans if (row.get("planned_filters") or {}).get("pair_discovery", {}).get("required")),
            "feature_backfill_executable_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "bounded_raw_lookup_dry_run_for_ready_tokens"
            if ready_tokens else
            "bounded_pair_discovery_plan_for_seed_tokens"
        ),
        "plain_summary_fr": (
            "Ce plan prepare la collecte brute minimale pour rendre LAB/B exploitables par les pipelines "
            "de features. Il ne collecte rien et n'ecrit rien."
        ),
        **disabled,
    }


def _b_seed_raw_context_filter_plan(
    clean_chain: str,
    clean_token: str,
    clean_pool: str,
    block_padding: int,
    max_window_blocks: int,
    max_sqd_block_span: int,
    max_sqd_calls: int,
) -> dict[str, Any]:
    plan = get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan(
        chain=clean_chain,
        token_addresses=[clean_token],
        dry_run=True,
        block_padding=block_padding,
        max_window_blocks=max_window_blocks,
    )
    token_plans = [
        row for row in list(plan.get("tokens") or [])
        if _clean_address(row.get("token_address")) == clean_token
    ]
    token_plan = token_plans[0] if token_plans else {}
    event_topics = {
        "Swap": _engine().SWAP_TOPIC,
        "Sync": "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1",
        "ERC20 Transfer": _engine().TRANSFER_TOPIC,
    }
    filters: list[dict[str, Any]] = []
    planned = token_plan.get("planned_filters") or {}
    for family, event_name in (("swap_logs", "Swap"), ("sync_logs", "Sync")):
        row = planned.get(family) or {}
        for pair in list(row.get("pair_addresses") or []):
            clean_pair = _clean_address(pair)
            if not clean_pair or clean_pair != clean_pool:
                continue
            filters.append({
                "chain": clean_chain,
                "candidate_pool_address": clean_pool,
                "filter_family": family,
                "event_name": event_name,
                "address": clean_pair,
                "from_block": row.get("from_block"),
                "to_block": row.get("to_block"),
                "topics": [event_topics[event_name]],
            })
    transfer_filter = planned.get("transfer_logs") or {}
    filters.append({
        "chain": clean_chain,
        "candidate_pool_address": clean_pool,
        "filter_family": "transfer_logs",
        "event_name": "ERC20 Transfer",
        "address": clean_token,
        "from_block": transfer_filter.get("from_block"),
        "to_block": transfer_filter.get("to_block"),
        "topics": [event_topics["ERC20 Transfer"]],
    })
    blockers = [
        *("seed_raw_context_plan_not_ready" for _ in [1] if plan.get("plan_status") != "ready_but_disabled"),
        *("b_seed_plan_not_found" for _ in [1] if not token_plan),
        *("b_seed_not_ready_for_bounded_raw_lookup" for _ in [1] if token_plan.get("plan_readiness") != "ready_for_bounded_raw_lookup_dry_run"),
        *("no_bounded_filters_available" for _ in [1] if not filters),
    ]

    def _chunk_filter(row_filter: dict[str, Any]) -> list[dict[str, Any]]:
        start = _as_int(row_filter.get("from_block"))
        end = _as_int(row_filter.get("to_block"))
        if not start or not end or end < start:
            return []
        chunks = []
        cursor = start
        index = 0
        while cursor <= end:
            chunk_end = min(end, cursor + max_sqd_block_span - 1)
            chunks.append({
                **row_filter,
                "parent_from_block": start,
                "parent_to_block": end,
                "chunk_index": index,
                "from_block": cursor,
                "to_block": chunk_end,
            })
            cursor = chunk_end + 1
            index += 1
        return chunks

    chunks = [chunk for row_filter in filters for chunk in _chunk_filter(row_filter)]
    if not chunks:
        blockers.append("filter_block_windows_missing")

    def _balanced_select(items: list[dict[str, Any]], limit_count: int) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen: set[int] = set()
        event_names = ("Swap", "Sync", "ERC20 Transfer")
        positions_by_event: dict[str, list[int]] = {}
        for event_name in event_names:
            event_items = [(idx, item) for idx, item in enumerate(items) if item.get("event_name") == event_name]
            if not event_items:
                continue
            positions_by_event[event_name] = [0, len(event_items) // 2, len(event_items) - 1]
        for round_index in range(3):
            for event_name in event_names:
                event_items = [(idx, item) for idx, item in enumerate(items) if item.get("event_name") == event_name]
                if not event_items:
                    continue
                candidate_index = positions_by_event.get(event_name, [])[round_index]
                original_index, item = event_items[candidate_index]
                if original_index in seen:
                    continue
                selected.append(item)
                seen.add(original_index)
                if len(selected) >= limit_count:
                    return selected
        for index, item in enumerate(items):
            if len(selected) >= limit_count:
                break
            if index not in seen:
                selected.append(item)
                seen.add(index)
        return selected

    return {
        "plan": plan,
        "token_plan": token_plan,
        "filters": filters,
        "chunks": chunks,
        "selected_filters": _balanced_select(chunks, max_sqd_calls),
        "blockers": list(dict.fromkeys(blockers)),
    }


def get_manipulation_detection_b_seed_bounded_raw_context_lookup_dry_run(
    chain: str | None = "bsc",
    token_address: str | None = "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    pool_address: str | None = "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    block_padding: int = 50_000,
    max_window_blocks: int = 250_000,
    max_sqd_calls: int = 18,
    max_sqd_block_span: int = 5_000,
    max_logs_total: int = 600,
    max_logs_per_filter: int = 80,
    timeout: int = 8,
) -> dict[str, Any]:
    """Bounded read-only SQD lookup for B seed raw context, with no persistence."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_token = _clean_address(token_address) or "0x6bdcce4a559076e37755a78ce0c06214e59e4444"
    clean_pool = _clean_address(pool_address) or "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0"
    safe_calls = max(1, min(int(max_sqd_calls or 18), 60))
    safe_span = max(100, min(int(max_sqd_block_span or 5_000), 50_000))
    safe_logs_total = max(1, min(int(max_logs_total or 600), 5_000))
    safe_logs_per_filter = max(1, min(int(max_logs_per_filter or 80), safe_logs_total))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    required_confirm = "RUN_B_SEED_RAW_CONTEXT_LOOKUP"
    source_policy = (
        "admin-only bounded read-only raw context lookup for the B CEX listing seed. It may call SQD Portal "
        "only after explicit confirmation, parses Swap/Sync/Transfer logs in memory, and persists nothing."
    )
    disabled = {
        "would_call_provider": bool(allow_external and confirm != required_confirm),
        "would_call_sqd": bool(allow_external and confirm != required_confirm),
        "would_insert_raw_swap_events": False,
        "would_insert_raw_sync_events": False,
        "would_insert_erc20_transfer_events": False,
        "would_create_feature_tables": False,
        "would_insert_feature_rows": False,
        "would_insert_ground_truth_rows": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "lookup_status": "blocked",
            "blockers": ["dry_run_required"],
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            **disabled,
        }

    filter_plan = _b_seed_raw_context_filter_plan(
        clean_chain=clean_chain,
        clean_token=clean_token,
        clean_pool=clean_pool,
        block_padding=block_padding,
        max_window_blocks=max_window_blocks,
        max_sqd_block_span=safe_span,
        max_sqd_calls=safe_calls,
    )
    plan = filter_plan["plan"]
    token_plan = filter_plan["token_plan"]
    filters = filter_plan["filters"]
    chunks = filter_plan["chunks"]
    selected_filters = filter_plan["selected_filters"]
    blockers = list(filter_plan["blockers"])
    if blockers:
        return {
            "ok": True,
            "dry_run": True,
            "lookup_status": "blocked",
            "chain": clean_chain,
            "token_address": clean_token,
            "pool_address": clean_pool,
            "seed_raw_context_plan": {
                "plan_status": plan.get("plan_status"),
                "summary": plan.get("summary"),
                "token_plan": token_plan,
            },
            "planned_filter_count": len(filters),
            "planned_filter_chunk_count": len(chunks),
            "selected_filter_count": 0,
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "parsed_previews": [],
            "blockers": list(dict.fromkeys(blockers)),
            "feature_backfill_executable_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
            **disabled,
        }
    if not allow_external:
        return {
            "ok": True,
            "dry_run": True,
            "lookup_status": "ready_but_external_disabled",
            "chain": clean_chain,
            "token_address": clean_token,
            "pool_address": clean_pool,
            "required_confirm": required_confirm,
            "seed_raw_context_plan": {
                "plan_status": plan.get("plan_status"),
                "summary": plan.get("summary"),
                "token_plan": token_plan,
            },
            "planned_filter_count": len(filters),
            "planned_filter_chunk_count": len(chunks),
            "selected_filter_count": len(selected_filters),
            "selected_filters_preview": selected_filters,
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "parsed_previews": [],
            "blockers": ["allow_external_required_for_bounded_lookup"],
            "feature_backfill_executable_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
            **disabled,
        }
    if confirm != required_confirm:
        return {
            "ok": False,
            "dry_run": True,
            "lookup_status": "blocked",
            "chain": clean_chain,
            "token_address": clean_token,
            "pool_address": clean_pool,
            "required_confirm": required_confirm,
            "planned_filter_count": len(filters),
            "planned_filter_chunk_count": len(chunks),
            "selected_filter_count": len(selected_filters),
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "parsed_previews": [],
            "blockers": ["confirm_RUN_B_SEED_RAW_CONTEXT_LOOKUP_required"],
            "feature_backfill_executable_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
            **disabled,
        }

    def _log_int(value: Any) -> int | None:
        try:
            if isinstance(value, str) and value.startswith("0x"):
                return int(value, 16)
            return int(value)
        except (TypeError, ValueError):
            return None

    def _topic_address(topics: Any, index: int) -> str | None:
        if not isinstance(topics, list) or len(topics) <= index:
            return None
        raw = str(topics[index] or "").lower()
        if raw.startswith("0x") and len(raw) >= 42:
            return "0x" + raw[-40:]
        return None

    def _preview(row_filter: dict[str, Any], log: dict[str, Any]) -> dict[str, Any]:
        event_name = str(row_filter.get("event_name") or "unknown")
        topics = log.get("topics") if isinstance(log.get("topics"), list) else []
        words = _decode_uint_words(log.get("data"), 4)
        preview = {
            "chain": clean_chain,
            "token_address": clean_token,
            "pool_address": clean_pool,
            "filter_family": row_filter.get("filter_family"),
            "event_name": event_name,
            "address": str(log.get("address") or row_filter.get("address") or "").lower(),
            "block_number": _log_int(log.get("blockNumber")),
            "block_timestamp": _log_int(log.get("timestamp")),
            "tx_hash": str(log.get("transactionHash") or "").lower() or None,
            "log_index": _log_int(log.get("logIndex")),
            "topic0": topics[0] if topics else (row_filter.get("topics") or [None])[0],
            "data_digest": hashlib.sha256(str(log.get("data") or "0x").encode("utf-8")).hexdigest(),
            "event_dedupe_key": (
                f"{clean_chain}|{event_name}|"
                f"{str(log.get('address') or row_filter.get('address') or '').lower()}|"
                f"{str(log.get('transactionHash') or '').lower()}|{_log_int(log.get('logIndex'))}"
            ),
            "would_persist": False,
        }
        if event_name == "Swap":
            preview.update({
                "sender": _topic_address(topics, 1),
                "to": _topic_address(topics, 2),
                "amount0_in": words[0] if len(words) > 0 else None,
                "amount1_in": words[1] if len(words) > 1 else None,
                "amount0_out": words[2] if len(words) > 2 else None,
                "amount1_out": words[3] if len(words) > 3 else None,
            })
        elif event_name == "Sync":
            preview.update({
                "reserve0": words[0] if len(words) > 0 else None,
                "reserve1": words[1] if len(words) > 1 else None,
            })
        elif event_name == "ERC20 Transfer":
            preview.update({
                "from": _topic_address(topics, 1),
                "to": _topic_address(topics, 2),
                "amount": words[0] if len(words) > 0 else None,
            })
        return preview

    event_counts: dict[str, int] = {}
    endpoint_statuses: list[dict[str, Any]] = []
    parsed_previews: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    endpoint_counts: dict[str, int] = {}
    key_sources: dict[str, int] = {}
    total_logs_seen = 0
    truncated = False
    per_filter_truncated = False
    for row_filter in selected_filters:
        if total_logs_seen >= safe_logs_total:
            truncated = True
            break
        log_filter = {
            "address": row_filter.get("address"),
            "fromBlock": hex(_as_int(row_filter.get("from_block"))),
            "toBlock": hex(_as_int(row_filter.get("to_block"))),
            "topics": list(row_filter.get("topics") or []),
        }
        logs, endpoint, error, key_source, request_preview = _engine()._sqd_portal_event_logs(
            clean_chain,
            log_filter,
            timeout=safe_timeout,
        )
        if endpoint:
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1
        if key_source:
            key_sources[key_source] = key_sources.get(key_source, 0) + 1
        status = {
            "event_name": row_filter.get("event_name"),
            "filter_family": row_filter.get("filter_family"),
            "address": row_filter.get("address"),
            "from_block": row_filter.get("from_block"),
            "to_block": row_filter.get("to_block"),
            "parent_from_block": row_filter.get("parent_from_block"),
            "parent_to_block": row_filter.get("parent_to_block"),
            "chunk_index": row_filter.get("chunk_index"),
            "endpoint": endpoint,
            "api_key_configured": bool((request_preview or {}).get("api_key_configured")),
            "api_key_source": key_source,
            "log_count": len(logs),
            "error": error,
        }
        endpoint_statuses.append(status)
        if error:
            errors.append(status)
            continue
        remaining = min(safe_logs_per_filter, max(0, safe_logs_total - total_logs_seen))
        selected_logs = logs[:remaining]
        if len(logs) > len(selected_logs):
            truncated = True
            per_filter_truncated = True
            status["truncated_log_count"] = len(logs) - len(selected_logs)
        total_logs_seen += len(selected_logs)
        event_name = str(row_filter.get("event_name") or "unknown")
        event_counts[event_name] = event_counts.get(event_name, 0) + len(selected_logs)
        for log in selected_logs:
            if len(parsed_previews) >= min(50, safe_logs_total):
                break
            parsed_previews.append(_preview(row_filter, log))
    lookup_digest = _digest({
        "chain": clean_chain,
        "token_address": clean_token,
        "pool_address": clean_pool,
        "selected_filters": selected_filters,
        "event_counts": event_counts,
        "total_logs_seen": total_logs_seen,
    })
    partial = len(selected_filters) < len(chunks)
    lookup_status = (
        "partial_with_errors_no_persistence" if partial and errors else
        "partial_no_persistence" if partial else
        "completed_with_errors_no_persistence" if errors else
        "completed_with_raw_context_no_persistence" if total_logs_seen else
        "completed_no_events_no_persistence"
    )
    return {
        "ok": True,
        "dry_run": True,
        "lookup_status": lookup_status,
        "chain": clean_chain,
        "token_address": clean_token,
        "pool_address": clean_pool,
        "raw_context_lookup_digest": lookup_digest,
        "seed_raw_context_plan": {
            "plan_status": plan.get("plan_status"),
            "summary": plan.get("summary"),
            "token_plan": token_plan,
        },
        "planned_filter_count": len(filters),
        "planned_filter_chunk_count": len(chunks),
        "selected_filter_count": len(selected_filters),
        "selection_strategy": "event_balanced_first_middle_last_then_fill",
        "external_calls_performed": len(endpoint_statuses),
        "total_logs_seen": total_logs_seen,
        "event_counts": event_counts,
        "endpoint_counts": endpoint_counts,
        "api_key_sources_used": key_sources,
        "endpoint_statuses": endpoint_statuses,
        "parsed_preview_count": len(parsed_previews),
        "parsed_previews": parsed_previews,
        "errors": errors[:10],
        "truncated": truncated,
        "per_filter_truncated": per_filter_truncated,
        "blockers": list(dict.fromkeys([
            *("sqd_errors_observed" for _ in [1] if errors),
            *("partial_lookup_due_to_max_sqd_calls" for _ in [1] if partial),
            *("lookup_truncated_by_max_logs_per_filter" for _ in [1] if per_filter_truncated),
            *("lookup_truncated_by_max_logs_total" for _ in [1] if truncated and not per_filter_truncated),
            "raw_context_not_persisted",
            "feature_backfill_not_executed",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "raw_context_evidence_only_schema_plan_read_only"
            if total_logs_seen and not errors else
            "reduce_or_repair_b_seed_sqd_lookup_or_try_lab_pair_discovery"
        ),
        "plain_summary_fr": (
            "Le lookup borne a recupere du contexte brut pour B en memoire seulement. Cela peut preparer une "
            "future persistence evidence-only, mais ce n'est toujours pas un score, signal ou trade."
            if total_logs_seen else
            "Le lookup borne n'a pas recupere de logs exploitables pour B. La piste reste bloquee cote contexte brut."
        ),
        "feature_backfill_executable_now": False,
        "client_signal_ready": False,
        "trade_ready": False,
        **{**disabled, "would_call_provider": False, "would_call_sqd": False},
    }


def insert_manipulation_detection_b_seed_raw_context_evidence(
    chain: str | None = "bsc",
    token_address: str | None = "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    pool_address: str | None = "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_raw_context_lookup_digest: str | None = None,
    block_padding: int = 50_000,
    max_window_blocks: int = 250_000,
    max_sqd_calls: int = 9,
    max_sqd_block_span: int = 25_000,
    max_logs_total: int = 180,
    max_logs_per_filter: int = 20,
    timeout: int = 8,
) -> dict[str, Any]:
    """Dry-run-first persistence of B seed raw Swap/Sync/Transfer evidence only."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_token = _clean_address(token_address) or "0x6bdcce4a559076e37755a78ce0c06214e59e4444"
    clean_pool = _clean_address(pool_address) or "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0"
    safe_calls = max(1, min(int(max_sqd_calls or 9), 60))
    safe_span = max(100, min(int(max_sqd_block_span or 25_000), 50_000))
    safe_logs_total = max(1, min(int(max_logs_total or 180), 5_000))
    safe_logs_per_filter = max(1, min(int(max_logs_per_filter or 20), safe_logs_total))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    preview_confirm = "PREVIEW_B_SEED_RAW_CONTEXT_EVIDENCE_INSERT"
    insert_confirm = "INSERT_B_SEED_RAW_CONTEXT_EVIDENCE"
    lookup_confirm = "RUN_B_SEED_RAW_CONTEXT_LOOKUP"
    required_tables = ["dex_raw_swap_events", "dex_raw_sync_events", "erc20_transfer_events"]
    source_policy = (
        "cex_listing_seed_backfill evidence-only raw context for B. Source SQD Portal. Inserts only raw "
        "Swap/Sync/ERC20 Transfer observations into existing raw tables; creates no features, labels, "
        "mappings, signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_create_feature_tables": False,
        "would_insert_feature_rows": False,
        "would_insert_ground_truth_rows": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_policy": source_policy,
    }
    blockers: list[str] = []
    if not allow_external:
        blockers.append("allow_external_required_for_insert_preview")
    if dry_run and allow_external and confirm not in {preview_confirm, lookup_confirm, insert_confirm}:
        blockers.append("confirm_PREVIEW_B_SEED_RAW_CONTEXT_EVIDENCE_INSERT_required")
    if not dry_run:
        if confirm != insert_confirm:
            blockers.append("confirm_INSERT_B_SEED_RAW_CONTEXT_EVIDENCE_required")
        if not str(expected_raw_context_lookup_digest or "").strip():
            blockers.append("expected_raw_context_lookup_digest_required")

    filter_plan = _b_seed_raw_context_filter_plan(
        clean_chain=clean_chain,
        clean_token=clean_token,
        clean_pool=clean_pool,
        block_padding=block_padding,
        max_window_blocks=max_window_blocks,
        max_sqd_block_span=safe_span,
        max_sqd_calls=safe_calls,
    )
    if filter_plan["blockers"]:
        blockers.extend(filter_plan["blockers"])
    selected_filters = list(filter_plan["selected_filters"] or [])
    if not selected_filters:
        blockers.append("no_selected_b_seed_filters")

    table_status: dict[str, dict[str, Any]] = {}
    conn = _engine()._get_db()
    try:
        for table_name in required_tables:
            exists = _table_exists(conn, table_name)
            columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()] if exists else []
            table_status[table_name] = {
                "exists": exists,
                "row_count": int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0] or 0) if exists else 0,
                "columns": columns,
            }
            if not exists:
                blockers.append(f"{table_name}_missing")
    finally:
        conn.close()

    def _log_int(value: Any) -> int | None:
        try:
            if isinstance(value, str) and value.startswith("0x"):
                return int(value, 16)
            return int(value)
        except (TypeError, ValueError):
            return None

    def _topic_address(topics: Any, index: int) -> str | None:
        if not isinstance(topics, list) or len(topics) <= index:
            return None
        raw = str(topics[index] or "").lower()
        if raw.startswith("0x") and len(raw) >= 42:
            return "0x" + raw[-40:]
        return None

    def _raw_payload(row_filter: dict[str, Any], log: dict[str, Any], event_name: str) -> tuple[str, str]:
        payload = {
            "source": "SQD Portal",
            "lane": "cex_listing_seed_raw_context",
            "collection_context": "cex_listing_seed_backfill",
            "seed_token_address": clean_token,
            "seed_pool_address": clean_pool,
            "filter_family": row_filter.get("filter_family"),
            "event_name": event_name,
            "from_block": row_filter.get("from_block"),
            "to_block": row_filter.get("to_block"),
            "log": log,
        }
        raw_json = _canonical_json(payload)
        return raw_json, _digest(payload)

    def _candidate(row_filter: dict[str, Any], log: dict[str, Any]) -> dict[str, Any]:
        event_name = str(row_filter.get("event_name") or "")
        topics = log.get("topics") if isinstance(log.get("topics"), list) else []
        word_count = 4 if event_name == "Swap" else 2 if event_name == "Sync" else 1
        words = _decode_uint_words(log.get("data"), word_count)
        tx_hash = str(log.get("transactionHash") or "").lower()
        log_index = _log_int(log.get("logIndex"))
        block_number = _log_int(log.get("blockNumber"))
        block_hash = str(log.get("blockHash") or "").strip() or None
        block_timestamp = _log_int(log.get("timestamp"))
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        raw_log_json, payload_digest = _raw_payload(row_filter, log, event_name)
        topic0 = str(topics[0] if topics else (row_filter.get("topics") or [None])[0] or "").lower()
        blockers_for_row: list[str] = []
        if not tx_hash:
            blockers_for_row.append("tx_hash_missing")
        if log_index is None:
            blockers_for_row.append("log_index_missing")
        if block_number is None:
            blockers_for_row.append("block_number_missing")
        if event_name in {"Swap", "Sync"} and str(log.get("address") or "").lower() != clean_pool:
            blockers_for_row.append("pool_address_mismatch")
        if event_name == "ERC20 Transfer" and str(log.get("address") or "").lower() != clean_token:
            blockers_for_row.append("token_address_mismatch")
        if event_name == "Swap":
            if topic0 != str(_engine().SWAP_TOPIC).lower():
                blockers_for_row.append("swap_topic_mismatch")
            if len(words) < 4:
                blockers_for_row.append("swap_amount_words_missing")
            dedupe_key = f"{clean_chain}|Swap|{clean_pool}|{tx_hash}|{log_index}"
            insert_values = {
                "checkpoint_id": None,
                "chain": clean_chain,
                "pair_address": clean_pool,
                "sender": _topic_address(topics, 1),
                "recipient": _topic_address(topics, 2),
                "amount0_in": str(words[0]) if len(words) > 0 else None,
                "amount1_in": str(words[1]) if len(words) > 1 else None,
                "amount0_out": str(words[2]) if len(words) > 2 else None,
                "amount1_out": str(words[3]) if len(words) > 3 else None,
                "tx_hash": tx_hash,
                "log_index": log_index,
                "block_number": block_number,
                "block_hash": block_hash,
                "block_timestamp": block_timestamp,
                "event_topic": topic0,
                "raw_log_json": raw_log_json,
                "payload_digest": payload_digest,
                "event_dedupe_key": dedupe_key,
                "status": "raw_observed",
                "created_at": created_at,
                "source_policy": source_policy,
            }
            target_table = "dex_raw_swap_events"
        elif event_name == "Sync":
            if topic0 != "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1":
                blockers_for_row.append("sync_topic_mismatch")
            if len(words) < 2:
                blockers_for_row.append("sync_reserve_words_missing")
            dedupe_key = f"{clean_chain}|Sync|{clean_pool}|{tx_hash}|{log_index}"
            insert_values = {
                "checkpoint_id": None,
                "chain": clean_chain,
                "pair_address": clean_pool,
                "reserve0": str(words[0]) if len(words) > 0 else None,
                "reserve1": str(words[1]) if len(words) > 1 else None,
                "tx_hash": tx_hash,
                "log_index": log_index,
                "block_number": block_number,
                "raw_log_json": raw_log_json,
                "payload_digest": payload_digest,
                "event_dedupe_key": dedupe_key,
                "status": "raw_observed",
                "created_at": created_at,
                "source_policy": source_policy,
            }
            target_table = "dex_raw_sync_events"
        elif event_name == "ERC20 Transfer":
            if topic0 != str(_engine().TRANSFER_TOPIC).lower():
                blockers_for_row.append("transfer_topic_mismatch")
            if len(words) < 1:
                blockers_for_row.append("transfer_amount_word_missing")
            from_address = _topic_address(topics, 1)
            to_address = _topic_address(topics, 2)
            if not from_address:
                blockers_for_row.append("from_address_missing")
            if not to_address:
                blockers_for_row.append("to_address_missing")
            dedupe_key = f"{clean_chain}|Transfer|{clean_token}|{tx_hash}|{log_index}|{from_address}|{to_address}"
            insert_values = {
                "checkpoint_id": None,
                "chain": clean_chain,
                "token_address": clean_token,
                "from_address": from_address,
                "to_address": to_address,
                "value_raw": str(words[0]) if words else None,
                "tx_hash": tx_hash,
                "log_index": log_index,
                "block_number": block_number,
                "raw_log_json": raw_log_json,
                "payload_digest": payload_digest,
                "event_dedupe_key": dedupe_key,
                "status": "raw_observed",
                "created_at": created_at,
                "source_policy": source_policy,
            }
            target_table = "erc20_transfer_events"
        else:
            dedupe_key = ""
            insert_values = {}
            target_table = ""
            blockers_for_row.append("unsupported_event_name")
        return {
            "target_table": target_table,
            "event_name": event_name,
            "event_dedupe_key": dedupe_key,
            "payload_digest": payload_digest,
            "insert_values": insert_values,
            "row_status": "eligible" if not blockers_for_row else "blocked",
            "row_blockers": blockers_for_row,
            "preview": {
                "target_table": target_table,
                "event_name": event_name,
                "tx_hash": tx_hash,
                "log_index": log_index,
                "block_number": block_number,
                "event_dedupe_key": dedupe_key,
                "payload_digest": payload_digest,
                "blockers": blockers_for_row,
            },
        }

    call_results: list[dict[str, Any]] = []
    raw_candidates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    event_counts: dict[str, int] = {}
    total_logs_seen = 0
    truncated = False
    if not blockers:
        for row_filter in selected_filters:
            if total_logs_seen >= safe_logs_total:
                truncated = True
                break
            log_filter = {
                "address": row_filter.get("address"),
                "fromBlock": hex(_as_int(row_filter.get("from_block"))),
                "toBlock": hex(_as_int(row_filter.get("to_block"))),
                "topics": list(row_filter.get("topics") or []),
            }
            logs, endpoint, error, key_source, request_preview = _engine()._sqd_portal_event_logs(
                clean_chain,
                log_filter,
                timeout=safe_timeout,
            )
            status = {
                "event_name": row_filter.get("event_name"),
                "filter_family": row_filter.get("filter_family"),
                "address": row_filter.get("address"),
                "from_block": row_filter.get("from_block"),
                "to_block": row_filter.get("to_block"),
                "endpoint": endpoint,
                "api_key_configured": bool((request_preview or {}).get("api_key_configured")),
                "api_key_source": key_source,
                "log_count": len(logs),
                "error": error,
            }
            call_results.append(status)
            if error:
                errors.append(status)
                continue
            selected_logs = logs[:min(safe_logs_per_filter, max(0, safe_logs_total - total_logs_seen))]
            if len(logs) > len(selected_logs):
                truncated = True
                status["truncated_log_count"] = len(logs) - len(selected_logs)
            total_logs_seen += len(selected_logs)
            event_name = str(row_filter.get("event_name") or "unknown")
            event_counts[event_name] = event_counts.get(event_name, 0) + len(selected_logs)
            raw_candidates.extend(_candidate(row_filter, log) for log in selected_logs)
    if errors:
        blockers.append("sqd_lookup_errors_observed")
    if not raw_candidates and not blockers:
        blockers.append("no_raw_context_logs_to_insert")
    if truncated:
        blockers.append("lookup_truncated_by_bounded_limits")

    lookup_digest = _digest({
        "chain": clean_chain,
        "token_address": clean_token,
        "pool_address": clean_pool,
        "selected_filters": selected_filters,
        "event_counts": event_counts,
        "total_logs_seen": total_logs_seen,
    })
    if not dry_run and lookup_digest != str(expected_raw_context_lookup_digest or "").strip():
        blockers.append("expected_raw_context_lookup_digest_mismatch")

    duplicate_keys: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    conn = _engine()._get_db()
    try:
        for row in raw_candidates:
            if row.get("row_status") != "eligible":
                continue
            table_name = str(row.get("target_table") or "")
            insert_values = dict(row.get("insert_values") or {})
            columns = set(table_status.get(table_name, {}).get("columns") or [])
            missing = sorted(set(insert_values) - columns)
            if missing:
                missing_columns[table_name] = sorted(set(missing_columns.get(table_name, []) + missing))
                continue
            existing = conn.execute(
                f"SELECT id FROM {table_name} WHERE event_dedupe_key=? LIMIT 1",
                (row.get("event_dedupe_key"),),
            ).fetchone()
            if existing:
                duplicate_keys.append(str(row.get("event_dedupe_key")))
    finally:
        conn.close()
    if missing_columns:
        blockers.append("raw_target_table_missing_columns")
    if duplicate_keys:
        blockers.append("duplicate_event_dedupe_key")

    clean_candidates = [
        row for row in raw_candidates
        if row.get("row_status") == "eligible"
        and row.get("event_dedupe_key") not in duplicate_keys
        and not missing_columns.get(str(row.get("target_table") or ""))
    ]
    target_counts: dict[str, int] = {}
    for row in clean_candidates:
        table_name = str(row.get("target_table") or "")
        target_counts[table_name] = target_counts.get(table_name, 0) + 1
    hard_blockers = [
        blocker for blocker in blockers
        if blocker not in {"lookup_truncated_by_bounded_limits"}
    ]
    would_insert = bool(clean_candidates and not hard_blockers)
    if dry_run or hard_blockers:
        return {
            "ok": bool(not hard_blockers),
            "dry_run": bool(dry_run),
            "insert_status": "ready_for_insert" if would_insert else "blocked",
            "chain": clean_chain,
            "token_address": clean_token,
            "pool_address": clean_pool,
            "planned_filter_count": len(filter_plan["filters"]),
            "planned_filter_chunk_count": len(filter_plan["chunks"]),
            "selected_filter_count": len(selected_filters),
            "external_calls_performed": len(call_results),
            "total_logs_seen": total_logs_seen,
            "event_counts": event_counts,
            "raw_event_candidates": len(raw_candidates),
            "clean_raw_event_candidates": len(clean_candidates),
            "target_insert_counts": target_counts,
            "raw_context_lookup_digest": lookup_digest,
            "expected_raw_context_lookup_digest": expected_raw_context_lookup_digest,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "call_results": call_results,
            "raw_event_previews": [row.get("preview") for row in raw_candidates[:25]],
            "duplicate_event_dedupe_keys": duplicate_keys[:25],
            "missing_columns": missing_columns,
            "blockers": list(dict.fromkeys(blockers)),
            "would_call_external": bool(allow_external),
            "would_insert_raw_context": would_insert,
            "would_insert_raw_context_count": len(clean_candidates) if would_insert else 0,
            "inserted": False,
            "rows_inserted": 0,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            **disabled,
        }

    conn = _engine()._get_db()
    try:
        for row in clean_candidates:
            table_name = str(row.get("target_table") or "")
            insert_values = dict(row.get("insert_values") or {})
            columns = list(insert_values.keys())
            placeholders = ", ".join("?" for _ in columns)
            conn.execute(
                f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
                [insert_values[column] for column in columns],
            )
        conn.commit()
        row_counts_after = {
            table_name: int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0] or 0)
            for table_name in required_tables
        }
    finally:
        conn.close()
    return {
        "ok": True,
        "dry_run": False,
        "insert_status": "inserted",
        "chain": clean_chain,
        "token_address": clean_token,
        "pool_address": clean_pool,
        "external_calls_performed": len(call_results),
        "total_logs_seen": total_logs_seen,
        "event_counts": event_counts,
        "raw_event_candidates": len(raw_candidates),
        "clean_raw_event_candidates": len(clean_candidates),
        "target_insert_counts": target_counts,
        "raw_context_lookup_digest": lookup_digest,
        "row_counts_after": row_counts_after,
        "blockers": [],
        "would_call_external": False,
        "would_insert_raw_context": False,
        "inserted": True,
        "rows_inserted": len(clean_candidates),
        "would_write": False,
        "real_write_enabled": True,
        "writes_performed": len(clean_candidates),
        **disabled,
    }


def get_manipulation_detection_cex_listing_ground_truth_dataset_plan_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    lookback_days: int = 365,
) -> dict[str, Any]:
    """Read-only plan for a future CEX listing ground-truth dataset."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_lookback_days = max(1, min(int(lookback_days or 365), 1095))
    target_table = "cex_listing_ground_truth_dataset"
    source_policy = (
        "admin-only read-only CEX listing ground-truth dataset plan. It defines how future "
        "source-backed listing rows could be collected for backtesting the CEX listing bridge. "
        "It does not call providers, scrape websites, create a table, insert rows, produce a "
        "client signal or execute a trade."
    )
    disabled = {
        "would_create_ground_truth_table": False,
        "would_insert_ground_truth_rows": False,
        "would_call_provider": False,
        "would_scrape": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "plan_status": "blocked",
            "blockers": ["dry_run_required"],
            "target_table": target_table,
            **disabled,
        }

    conn = _engine()._get_db()
    try:
        table_exists = _table_exists(conn, target_table)
        local_data_snapshot = {
            table: _table_count(conn, table)
            for table in [
                "pair_tokens",
                "swaps",
                "token_transfers",
                "wallet_chain_state",
                "dex_raw_swap_events",
                "dex_raw_sync_events",
                "erc20_transfer_events",
            ]
        }
    finally:
        conn.close()

    bridge_preview = get_manipulation_detection_cex_listing_probability_bridge_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_behavioral_score=50,
        cex_deposit_limit=100,
    )
    bridge_summary = dict(bridge_preview.get("summary") or {})
    schema_preview = [
        {"name": "listing_ground_truth_id", "type": "INTEGER PRIMARY KEY AUTOINCREMENT"},
        {"name": "chain", "type": "TEXT NOT NULL"},
        {"name": "token_address", "type": "TEXT NOT NULL"},
        {"name": "token_symbol", "type": "TEXT"},
        {"name": "cex_name", "type": "TEXT NOT NULL"},
        {"name": "market_pair", "type": "TEXT NOT NULL"},
        {"name": "announcement_url", "type": "TEXT NOT NULL"},
        {"name": "announcement_at", "type": "TEXT"},
        {"name": "listing_at", "type": "TEXT"},
        {"name": "listing_tier", "type": "TEXT NOT NULL"},
        {"name": "source_tier", "type": "TEXT NOT NULL"},
        {"name": "source_digest", "type": "TEXT NOT NULL"},
        {"name": "source_excerpt_digest", "type": "TEXT"},
        {"name": "payload_json", "type": "TEXT NOT NULL"},
        {"name": "dedupe_key", "type": "TEXT NOT NULL UNIQUE"},
        {"name": "status", "type": "TEXT NOT NULL DEFAULT 'pending_source_review'"},
        {"name": "created_at", "type": "TEXT NOT NULL"},
        {"name": "source_policy", "type": "TEXT NOT NULL"},
    ]
    indexes_preview = [
        "UNIQUE(dedupe_key)",
        "INDEX(chain, token_address)",
        "INDEX(cex_name, market_pair)",
        "INDEX(announcement_at)",
        "INDEX(listing_at)",
        "INDEX(status)",
        "INDEX(source_tier)",
    ]
    constraints_preview = [
        "source_tier must be tier_1, tier_2, manual_source_backed, or security_api",
        "listing_tier may include documented_scam_never_listed or documented_honeypot_never_listed for scam negative controls",
        "status enum: pending_source_review, accepted_for_backtest, needs_better_source, rejected",
        "announcement_url and source_digest are required before any row can become backtestable",
        "duplicate dedupe_key must block; no overwrite, no upsert, no silent success",
        "dataset rows are ground truth for backtest only; they are not listing predictions",
    ]
    source_catalog = [
        {
            "source": "Binance announcements",
            "use": "official listing announcement ground truth when token/pair/date is visible",
            "mode_now": "planned_only_no_call",
        },
        {
            "source": "OKX announcements",
            "use": "official listing announcement ground truth when token/pair/date is visible",
            "mode_now": "planned_only_no_call",
        },
        {
            "source": "Gate announcements",
            "use": "tier-2 listing ground truth and early listing cohort",
            "mode_now": "planned_only_no_call",
        },
        {
            "source": "MEXC announcements",
            "use": "tier-2 listing ground truth and early listing cohort",
            "mode_now": "planned_only_no_call",
        },
        {
            "source": "Bitget announcements",
            "use": "tier-2 listing ground truth and early listing cohort",
            "mode_now": "planned_only_no_call",
        },
        {
            "source": "CoinGecko market metadata",
            "use": "corroboration of exchange markets, not announcement truth by itself",
            "mode_now": "planned_only_no_call",
        },
        {
            "source": "Honeypot.is / GoPlus security APIs",
            "use": "documented scam or honeypot negative controls; not organic never-listed proof",
            "mode_now": "bounded_dry_run_preview_only",
        },
        {
            "source": "CCXT exchange market metadata",
            "use": "market availability corroboration, not announcement truth by itself",
            "mode_now": "planned_only_no_call",
        },
        {
            "source": "manual source-backed entry",
            "use": "admin-provided URL/date/pair with digest when automated collection is unavailable",
            "mode_now": "template_only",
        },
    ]
    required_fields = [
        "chain",
        "token_address",
        "token_symbol",
        "cex_name",
        "market_pair",
        "announcement_url",
        "announcement_at",
        "listing_at",
        "listing_tier",
        "source_tier",
        "source_digest",
        "dedupe_key",
    ]
    backtest_windows = [
        {"name": "J-30", "purpose": "did the bridge rank the token before public announcement?"},
        {"name": "J-7", "purpose": "did the score strengthen near announcement?"},
        {"name": "J-1", "purpose": "avoid lookahead leakage before announcement/listing"},
        {"name": "J+1/J+7", "purpose": "measure post-announcement outcome without live trading"},
    ]
    dedupe_key_template = (
        "chain|token_address|cex_name|market_pair|announcement_at|source_digest"
    )
    blockers = list(dict.fromkeys([
        *("ground_truth_table_already_exists_but_plan_is_read_only" for _ in [1] if table_exists),
        "ground_truth_rows_missing",
        "provider_collection_not_enabled",
        "scraping_not_enabled",
        "announcement_source_digest_required",
        "backtest_runner_not_enabled",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled",
        "chain": clean_chain,
        "target_table": target_table,
        "table_exists": table_exists,
        "migration_required": not table_exists,
        "confirm_required": "future separate DDL goal only",
        "lookback_days": safe_lookback_days,
        "required_fields": required_fields,
        "schema_preview": schema_preview,
        "indexes_preview": indexes_preview,
        "constraints_preview": constraints_preview,
        "dedupe_key_template": dedupe_key_template,
        "source_catalog": source_catalog,
        "manual_entry_template": {
            "chain": clean_chain,
            "token_address": "0x...",
            "token_symbol": "TOKEN",
            "cex_name": "Gate|MEXC|Bitget|Binance|OKX",
            "market_pair": "TOKEN/USDT",
            "announcement_url": "https://...",
            "announcement_at": "YYYY-MM-DDTHH:MM:SSZ",
            "listing_at": "YYYY-MM-DDTHH:MM:SSZ",
            "source_tier": "tier_1|tier_2",
            "source_digest": "sha256(...)",
        },
        "backtest_plan": {
            "purpose": "measure whether the bridge would have ranked tokens before the CEX announcement",
            "windows": backtest_windows,
            "bridge_inputs": [
                "behavioral_anomaly_score",
                "stealth_accumulation_candidate",
                "fresh_like_cex_depositors",
                "shared_funder_proxy",
                "matching_cex_token_deposits",
                "tier2_cex_hint",
            ],
            "success_metrics": [
                "score_above_threshold_before_announcement",
                "days_of_lead_time",
                "false_positive_rate",
                "post_announcement_mfe_after_friction",
                "liquidity_capacity_at_entry_and_exit",
            ],
            "leakage_guard": "features must be computed only from data timestamped before each test window",
        },
        "current_bridge_snapshot": {
            "bridge_status": bridge_preview.get("bridge_status"),
            "summary": bridge_summary,
            "next_safe_step": bridge_preview.get("next_safe_step"),
            "blockers": bridge_preview.get("blockers"),
        },
        "local_data_snapshot": local_data_snapshot,
        "summary": {
            "ground_truth_dataset_ready_now": False,
            "known_listing_rows_available": 0,
            "bridge_backtest_ready_now": False,
            "can_predict_listing_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "cex_listing_ground_truth_dataset_confirmed_ddl_migration"
            if not table_exists else
            "cex_listing_ground_truth_manual_or_bounded_source_intake_preview"
        ),
        "plain_summary_fr": (
            "Cette etape prepare la verite terrain des listings CEX. Sans dates de listing fiables, "
            "on ne peut pas savoir si notre pont CEX predit quelque chose ou s'il raconte juste une belle histoire."
        ),
        **disabled,
    }


def create_manipulation_detection_cex_listing_ground_truth_dataset(
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Confirmed DDL-only creation of the CEX listing ground-truth dataset table."""
    clean_chain = str(chain or "bsc").strip().lower()
    target_table = "cex_listing_ground_truth_dataset"
    required_confirm = "CREATE_CEX_LISTING_GROUND_TRUTH_DATASET"
    source_policy = (
        "admin-confirmed DDL-only CEX listing ground-truth dataset migration. It creates only "
        "the empty cex_listing_ground_truth_dataset table and indexes if absent. It inserts zero "
        "rows, calls no provider, performs no scraping, creates no listing signal, client signal, "
        "trade, wallet order, label, mapping or opt-in."
    )
    disabled = {
        "would_insert_ground_truth_rows": False,
        "would_call_provider": False,
        "would_scrape": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "source_policy": source_policy,
    }

    plan = get_manipulation_detection_cex_listing_ground_truth_dataset_plan_preview(
        chain=clean_chain,
        limit=1,
        dry_run=True,
        lookback_days=365,
    )
    blockers: list[str] = []
    if plan.get("target_table") != target_table:
        blockers.append("cex_listing_ground_truth_schema_plan_target_mismatch")
    if plan.get("plan_status") != "ready_but_disabled":
        blockers.append("cex_listing_ground_truth_schema_plan_not_ready")
    if not dry_run and confirm != required_confirm:
        blockers.append("confirm_CREATE_CEX_LISTING_GROUND_TRUTH_DATASET_required")

    expected_columns = [
        "listing_ground_truth_id",
        "chain",
        "token_address",
        "token_symbol",
        "cex_name",
        "market_pair",
        "announcement_url",
        "announcement_at",
        "listing_at",
        "listing_tier",
        "source_tier",
        "source_digest",
        "source_excerpt_digest",
        "payload_json",
        "dedupe_key",
        "status",
        "created_at",
        "source_policy",
    ]
    index_sql = [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cex_listing_ground_truth_dedupe ON cex_listing_ground_truth_dataset(dedupe_key)",
        "CREATE INDEX IF NOT EXISTS idx_cex_listing_ground_truth_chain_token ON cex_listing_ground_truth_dataset(chain, token_address)",
        "CREATE INDEX IF NOT EXISTS idx_cex_listing_ground_truth_cex_pair ON cex_listing_ground_truth_dataset(cex_name, market_pair)",
        "CREATE INDEX IF NOT EXISTS idx_cex_listing_ground_truth_announcement ON cex_listing_ground_truth_dataset(announcement_at)",
        "CREATE INDEX IF NOT EXISTS idx_cex_listing_ground_truth_listing ON cex_listing_ground_truth_dataset(listing_at)",
        "CREATE INDEX IF NOT EXISTS idx_cex_listing_ground_truth_status ON cex_listing_ground_truth_dataset(status)",
        "CREATE INDEX IF NOT EXISTS idx_cex_listing_ground_truth_source_tier ON cex_listing_ground_truth_dataset(source_tier)",
    ]

    conn = _engine()._get_db()
    try:
        table_exists = _table_exists(conn, target_table)
        row_count = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0) if table_exists else 0
        if table_exists:
            existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({target_table})").fetchall()}
            if any(column not in existing_columns for column in expected_columns):
                blockers.append("cex_listing_ground_truth_dataset_schema_drift_detected")
    finally:
        conn.close()

    blockers = list(dict.fromkeys(blockers))
    migration_required = not table_exists
    if dry_run or blockers:
        return {
            "ok": not blockers,
            "dry_run": bool(dry_run),
            "create_status": "ready_but_disabled" if not blockers else "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "table_exists": table_exists,
            "migration_required": migration_required,
            "confirm_required": required_confirm,
            "would_create_ground_truth_table": bool(migration_required and not blockers),
            "table_created": False,
            "indexes_created": [],
            "rows_inserted": 0,
            "row_count": row_count,
            "known_listing_rows_available": row_count,
            "can_predict_listing_now": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": blockers,
            **disabled,
        }

    conn = _engine()._get_db()
    try:
        before_exists = _table_exists(conn, target_table)
        before_indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
                (target_table,),
            ).fetchall()
            if not str(row[0]).startswith("sqlite_autoindex_")
        }
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cex_listing_ground_truth_dataset (
                listing_ground_truth_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                token_address TEXT NOT NULL,
                token_symbol TEXT,
                cex_name TEXT NOT NULL,
                market_pair TEXT NOT NULL,
                announcement_url TEXT NOT NULL,
                announcement_at TEXT,
                listing_at TEXT,
                listing_tier TEXT NOT NULL,
                source_tier TEXT NOT NULL,
                source_digest TEXT NOT NULL,
                source_excerpt_digest TEXT,
                payload_json TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending_source_review',
                created_at TEXT NOT NULL,
                source_policy TEXT NOT NULL
            )
            """
        )
        for sql in index_sql:
            conn.execute(sql)
        conn.commit()
        after_exists = _table_exists(conn, target_table)
        after_indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
                (target_table,),
            ).fetchall()
            if not str(row[0]).startswith("sqlite_autoindex_")
        }
        row_count = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
    finally:
        conn.close()

    table_created = after_exists and not before_exists
    created_indexes = sorted(after_indexes - before_indexes)
    return {
        "ok": True,
        "dry_run": False,
        "create_status": "created" if table_created else "already_exists",
        "chain": clean_chain,
        "target_table": target_table,
        "table_exists": after_exists,
        "migration_required": False,
        "confirm_required": required_confirm,
        "would_create_ground_truth_table": False,
        "table_created": table_created,
        "indexes_created": created_indexes,
        "rows_inserted": 0,
        "row_count": row_count,
        "known_listing_rows_available": row_count,
        "can_predict_listing_now": False,
        "would_write": False,
        "real_write_enabled": bool(table_created or created_indexes),
        "writes_performed": (1 if table_created else 0) + len(created_indexes),
        "blockers": [],
        **disabled,
    }


def insert_manipulation_detection_cex_listing_ground_truth_rows(
    rows: list[dict[str, Any]] | None,
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
    expected_dedupe_keys: list[str] | str | None = None,
) -> dict[str, Any]:
    """Dry-run-first insert of manual source-backed CEX listing ground-truth rows."""
    clean_chain = str(chain or "bsc").strip().lower()
    target_table = "cex_listing_ground_truth_dataset"
    required_confirm = "INSERT_CEX_LISTING_GROUND_TRUTH_ROWS"
    source_policy = (
        "admin-confirmed manual CEX listing ground-truth row intake. Rows are used only to "
        "backtest the CEX Listing Bridge. This path calls no provider, performs no scraping, "
        "creates no listing signal, client signal, trade, wallet order, label, mapping or opt-in."
    )
    disabled = {
        "would_call_provider": False,
        "would_scrape": False,
        "would_persist_listing_probability": False,
        "would_create_listing_signal": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "source_policy": source_policy,
    }
    candidate_rows = [row for row in (rows or []) if isinstance(row, dict)]
    expected_keys = (
        [part.strip() for part in expected_dedupe_keys.split(",") if part.strip()]
        if isinstance(expected_dedupe_keys, str)
        else [str(part).strip() for part in (expected_dedupe_keys or []) if str(part).strip()]
    )

    normalized_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_keys: set[str] = set()
    for idx, row in enumerate(candidate_rows):
        normalized, row_blockers = _normalize_ground_truth_row(row, clean_chain)
        normalized["input_index"] = idx
        normalized["row_blockers"] = row_blockers
        normalized["eligible"] = not row_blockers
        normalized_rows.append(normalized)
        if row_blockers:
            blockers.extend([f"row_{idx}_{blocker}" for blocker in row_blockers])
        dedupe_key = normalized.get("dedupe_key")
        if dedupe_key in seen_keys:
            normalized["eligible"] = False
            normalized["row_blockers"].append("duplicate_dedupe_key_in_payload")
            blockers.append(f"row_{idx}_duplicate_dedupe_key_in_payload")
        seen_keys.add(str(dedupe_key))

    positive_rows = [
        row for row in normalized_rows
        if row.get("listing_tier") in _POSITIVE_LISTING_TIERS
    ]
    negative_rows = [
        row for row in normalized_rows
        if row.get("listing_tier") in _NEGATIVE_LISTING_TIERS
    ]
    if not candidate_rows:
        blockers.append("ground_truth_rows_required")
    if candidate_rows and not positive_rows:
        blockers.append("positive_listing_rows_missing")
    if candidate_rows and not negative_rows:
        blockers.append("negative_cohort_rows_missing_survival_bias_risk")

    conn = _engine()._get_db()
    try:
        table_exists = _table_exists(conn, target_table)
        existing_keys: set[str] = set()
        if table_exists:
            existing_keys = {
                str(row[0])
                for row in conn.execute(
                    f"SELECT dedupe_key FROM {target_table} WHERE dedupe_key IN ({','.join('?' for _ in seen_keys)})",
                    tuple(seen_keys),
                ).fetchall()
            } if seen_keys else set()
            row_count_before = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
        else:
            row_count_before = 0
    finally:
        conn.close()

    if not table_exists:
        blockers.append("cex_listing_ground_truth_dataset_missing_run_confirmed_ddl_first")
    for row in normalized_rows:
        if row.get("dedupe_key") in existing_keys:
            row["eligible"] = False
            row["row_blockers"].append("duplicate_dedupe_key_already_exists")
            blockers.append(f"row_{row.get('input_index')}_duplicate_dedupe_key_already_exists")

    eligible_rows = [row for row in normalized_rows if row.get("eligible")]
    eligible_keys = [str(row.get("dedupe_key")) for row in eligible_rows]
    if not dry_run:
        if confirm != required_confirm:
            blockers.append("confirm_INSERT_CEX_LISTING_GROUND_TRUTH_ROWS_required")
        if not expected_keys:
            blockers.append("expected_dedupe_keys_required")
        if sorted(expected_keys) != sorted(eligible_keys):
            blockers.append("expected_dedupe_keys_mismatch")

    blockers = list(dict.fromkeys(blockers))
    if dry_run or blockers:
        return {
            "ok": not blockers,
            "dry_run": bool(dry_run),
            "insert_status": "ready_but_disabled" if eligible_rows and not blockers else "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "table_exists": table_exists,
            "input_rows": len(candidate_rows),
            "eligible_rows": len(eligible_rows),
            "positive_rows": len(positive_rows),
            "negative_rows": len(negative_rows),
            "preview_rows": normalized_rows,
            "expected_dedupe_keys_required_for_real": eligible_keys,
            "would_insert_ground_truth_rows": bool(eligible_rows and not blockers),
            "rows_inserted": 0,
            "row_count_before": row_count_before,
            "row_count_after": row_count_before,
            "can_predict_listing_now": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": blockers,
            **disabled,
        }

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _engine()._get_db()
    try:
        before = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
        inserted = 0
        for row in eligible_rows:
            conn.execute(
                f"""
                INSERT INTO {target_table} (
                    chain, token_address, token_symbol, cex_name, market_pair,
                    announcement_url, announcement_at, listing_at, listing_tier,
                    source_tier, source_digest, source_excerpt_digest, payload_json,
                    dedupe_key, status, created_at, source_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_source_review', ?, ?)
                """,
                (
                    row["chain"],
                    row["token_address"],
                    row["token_symbol"],
                    row["cex_name"],
                    row["market_pair"],
                    row["announcement_url"],
                    row["announcement_at"],
                    row["listing_at"],
                    row["listing_tier"],
                    row["source_tier"],
                    row["source_digest"],
                    row["source_excerpt_digest"],
                    row["payload_json"],
                    row["dedupe_key"],
                    now,
                    row["source_policy"],
                ),
            )
            inserted += 1
        conn.commit()
        after = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
    finally:
        conn.close()

    return {
        "ok": True,
        "dry_run": False,
        "insert_status": "inserted" if inserted else "already_exists_or_empty",
        "chain": clean_chain,
        "target_table": target_table,
        "table_exists": True,
        "input_rows": len(candidate_rows),
        "eligible_rows": len(eligible_rows),
        "positive_rows": len(positive_rows),
        "negative_rows": len(negative_rows),
        "preview_rows": normalized_rows,
        "expected_dedupe_keys_required_for_real": eligible_keys,
        "would_insert_ground_truth_rows": False,
        "rows_inserted": inserted,
        "row_count_before": before,
        "row_count_after": after,
        "can_predict_listing_now": False,
        "would_write": False,
        "real_write_enabled": bool(inserted),
        "writes_performed": inserted,
        "blockers": [],
        **disabled,
    }
