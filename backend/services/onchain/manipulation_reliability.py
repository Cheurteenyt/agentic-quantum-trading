from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from services.onchain.core.constants import SWAP_TOPIC, TRANSFER_TOPIC
from services.onchain.events.parsers import _decode_uint_words

UNISWAP_V2_SYNC_TOPIC = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"
UNISWAP_V2_MINT_TOPIC = "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
UNISWAP_V2_BURN_TOPIC = "0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496"


def _engine():
    from services import onchain_engine

    return onchain_engine


def _normalize_chain(value: str) -> str:
    return _engine()._normalize_chain(value)


def _get_db() -> sqlite3.Connection:
    return _engine()._get_db()


def _load_token_metadata_cache(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    return _engine()._load_token_metadata_cache(conn)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return _engine()._table_exists(conn, table_name)


def _token_metadata_for(chain: Any, token_address: Any, metadata_cache: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    return _engine()._token_metadata_for(chain, token_address, metadata_cache)


def _uniswap_v2_liquidity_event_topics() -> list[dict[str, Any]]:
    return [
        {
            "event_name": "Sync",
            "signature": "Sync(uint112 reserve0,uint112 reserve1)",
            "topic0": UNISWAP_V2_SYNC_TOPIC,
            "target_table": "dex_raw_sync_events",
            "purpose": "reserve context for stale or incomplete outcome windows",
        },
        {
            "event_name": "Mint",
            "signature": "Mint(address indexed sender,uint256 amount0,uint256 amount1)",
            "topic0": UNISWAP_V2_MINT_TOPIC,
            "target_table": "dex_raw_liquidity_events",
            "purpose": "liquidity-add context around the outcome window",
        },
        {
            "event_name": "Burn",
            "signature": "Burn(address indexed sender,uint256 amount0,uint256 amount1,address indexed to)",
            "topic0": UNISWAP_V2_BURN_TOPIC,
            "target_table": "dex_raw_liquidity_events",
            "purpose": "liquidity-remove context around the outcome window",
        },
    ]


def _sync_liquidity_canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sync_liquidity_topic_address(topics: Any, index: int) -> str | None:
    if not isinstance(topics, list) or len(topics) <= index:
        return None
    raw = str(topics[index] or "").lower()
    if raw.startswith("0x") and len(raw) >= 42:
        return "0x" + raw[-40:]
    return None


def _sync_liquidity_log_int(value: Any) -> int | None:
    try:
        if isinstance(value, str) and value.startswith("0x"):
            return int(value, 16)
        return int(value)
    except (TypeError, ValueError):
        return None


def _sync_liquidity_payload_digest(payload: Any) -> str:
    return hashlib.sha256(_sync_liquidity_canonical_json(payload).encode("utf-8")).hexdigest()


def _build_sync_liquidity_event_row(row_filter: dict[str, Any], log: dict[str, Any]) -> dict[str, Any]:
    event_name = str(row_filter.get("event_name") or "unknown")
    chain = str(row_filter.get("chain") or "").strip().lower()
    pair_address = str(log.get("address") or row_filter.get("pair_address") or "").strip().lower()
    tx_hash = str(log.get("transactionHash") or "").strip().lower()
    log_index = _sync_liquidity_log_int(log.get("logIndex"))
    block_number = _sync_liquidity_log_int(log.get("blockNumber"))
    block_timestamp = _sync_liquidity_log_int(log.get("timestamp"))
    topics = log.get("topics") if isinstance(log.get("topics"), list) else []
    words = _decode_uint_words(log.get("data"), 2)
    raw_payload = {
        "source": "SQD Portal",
        "window_label": row_filter.get("window_label"),
        "filter_role": row_filter.get("filter_role"),
        "from_block": row_filter.get("from_block"),
        "to_block": row_filter.get("to_block"),
        "event_name": event_name,
        "log": log,
    }
    raw_log_json = _sync_liquidity_canonical_json(raw_payload)
    payload_digest = _sync_liquidity_payload_digest(raw_payload)
    event_dedupe_key = f"{chain}|{event_name}|{pair_address}|{tx_hash}|{log_index}"
    base = {
        "window_label": row_filter.get("window_label"),
        "filter_role": row_filter.get("filter_role"),
        "event_name": event_name,
        "chain": chain,
        "pair_address": pair_address,
        "block_number": block_number,
        "block_timestamp": block_timestamp,
        "tx_hash": tx_hash or None,
        "log_index": log_index,
        "topic0": topics[0] if topics else row_filter.get("topic0"),
        "raw_log_json": raw_log_json,
        "payload_digest": payload_digest,
        "event_dedupe_key": event_dedupe_key,
        "would_persist": False,
    }
    blockers: list[str] = []
    if not chain:
        blockers.append("chain_missing")
    if not pair_address:
        blockers.append("pair_address_missing")
    if not tx_hash:
        blockers.append("tx_hash_missing")
    if log_index is None:
        blockers.append("log_index_missing")
    if block_number is None:
        blockers.append("block_number_missing")
    if len(words) < 2:
        blockers.append("event_amount_words_missing")

    if event_name == "Sync":
        base["target_table"] = "dex_raw_sync_events"
        base["reserve0"] = words[0] if len(words) >= 1 else None
        base["reserve1"] = words[1] if len(words) >= 2 else None
        base["insert_values"] = {
            "checkpoint_id": None,
            "chain": chain,
            "pair_address": pair_address,
            "reserve0": str(base["reserve0"]) if base["reserve0"] is not None else None,
            "reserve1": str(base["reserve1"]) if base["reserve1"] is not None else None,
            "tx_hash": tx_hash,
            "log_index": log_index,
            "block_number": block_number,
            "raw_log_json": raw_log_json,
            "payload_digest": payload_digest,
            "event_dedupe_key": event_dedupe_key,
            "status": "raw_observed",
        }
    elif event_name in {"Mint", "Burn"}:
        base["target_table"] = "dex_raw_liquidity_events"
        base["sender"] = _sync_liquidity_topic_address(topics, 1)
        base["recipient"] = _sync_liquidity_topic_address(topics, 2) if event_name == "Burn" else None
        base["amount0"] = words[0] if len(words) >= 1 else None
        base["amount1"] = words[1] if len(words) >= 2 else None
        base["insert_values"] = {
            "checkpoint_id": None,
            "chain": chain,
            "pair_address": pair_address,
            "event_name": event_name,
            "sender": base["sender"],
            "recipient": base["recipient"],
            "amount0": str(base["amount0"]) if base["amount0"] is not None else None,
            "amount1": str(base["amount1"]) if base["amount1"] is not None else None,
            "tx_hash": tx_hash,
            "log_index": log_index,
            "block_number": block_number,
            "raw_log_json": raw_log_json,
            "payload_digest": payload_digest,
            "event_dedupe_key": event_dedupe_key,
            "status": "raw_observed",
        }
    else:
        base["target_table"] = None
        base["insert_values"] = {}
        blockers.append("unsupported_event_name")
    base["row_status"] = "eligible" if not blockers else "blocked"
    base["row_blockers"] = blockers
    return base


def _top_expansion_raw_log_json_and_digest(row_filter: dict[str, Any], log: dict[str, Any]) -> tuple[str, str]:
    payload = {
        "source": "SQD Portal",
        "lane": "top_expansion_raw_context",
        "candidate_pool_address": row_filter.get("candidate_pool_address"),
        "filter_family": row_filter.get("filter_family"),
        "filter_type": row_filter.get("filter_type"),
        "range_id": row_filter.get("range_id"),
        "from_block": row_filter.get("from_block"),
        "to_block": row_filter.get("to_block"),
        "event_name": row_filter.get("event_name"),
        "log": log,
    }
    raw_log_json = _sync_liquidity_canonical_json(payload)
    return raw_log_json, _sync_liquidity_payload_digest(payload)


def _build_top_expansion_swap_event_candidate(
    row_filter: dict[str, Any],
    log: dict[str, Any],
    source_policy: str,
) -> dict[str, Any]:
    chain = _normalize_chain(str(row_filter.get("chain") or "bsc"))
    pair_address = str(log.get("address") or row_filter.get("address") or "").strip().lower()
    tx_hash = str(log.get("transactionHash") or "").strip().lower()
    log_index = _sync_liquidity_log_int(log.get("logIndex"))
    block_number = _sync_liquidity_log_int(log.get("blockNumber"))
    block_hash = str(log.get("blockHash") or "").strip() or None
    block_timestamp = _sync_liquidity_log_int(log.get("timestamp"))
    topics = log.get("topics") if isinstance(log.get("topics"), list) else []
    words = _decode_uint_words(log.get("data"), 4)
    raw_log_json, payload_digest = _top_expansion_raw_log_json_and_digest(row_filter, log)
    event_topic = str(topics[0]).lower() if topics else SWAP_TOPIC.lower()
    event_dedupe_key = f"{chain}|Swap|{pair_address}|{tx_hash}|{log_index}"
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    blockers: list[str] = []
    if event_topic != SWAP_TOPIC.lower():
        blockers.append("swap_topic_mismatch")
    if not pair_address:
        blockers.append("pair_address_missing")
    if not tx_hash:
        blockers.append("tx_hash_missing")
    if log_index is None:
        blockers.append("log_index_missing")
    if block_number is None:
        blockers.append("block_number_missing")
    if len(words) < 4:
        blockers.append("swap_amount_words_missing")
    sender = _sync_liquidity_topic_address(topics, 1)
    recipient = _sync_liquidity_topic_address(topics, 2)
    insert_values = {
        "checkpoint_id": None,
        "chain": chain,
        "pair_address": pair_address,
        "sender": sender,
        "recipient": recipient,
        "amount0_in": str(words[0]) if len(words) > 0 else None,
        "amount1_in": str(words[1]) if len(words) > 1 else None,
        "amount0_out": str(words[2]) if len(words) > 2 else None,
        "amount1_out": str(words[3]) if len(words) > 3 else None,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "block_number": block_number,
        "block_hash": block_hash,
        "block_timestamp": block_timestamp,
        "event_topic": event_topic,
        "raw_log_json": raw_log_json,
        "payload_digest": payload_digest,
        "event_dedupe_key": event_dedupe_key,
        "status": "raw_observed",
        "created_at": created_at,
        "source_policy": source_policy,
    }
    return {
        "target_table": "dex_raw_swap_events",
        "event_name": "Swap",
        "event_dedupe_key": event_dedupe_key,
        "payload_digest": payload_digest,
        "insert_values": insert_values,
        "row_status": "eligible" if not blockers else "blocked",
        "row_blockers": blockers,
        "preview": {
            "target_table": "dex_raw_swap_events",
            "candidate_pool_address": row_filter.get("candidate_pool_address"),
            "pair_address": pair_address,
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


def _build_top_expansion_transfer_event_candidate(
    row_filter: dict[str, Any],
    log: dict[str, Any],
    source_policy: str,
) -> dict[str, Any]:
    chain = _normalize_chain(str(row_filter.get("chain") or "bsc"))
    token_address = str(log.get("address") or row_filter.get("address") or "").strip().lower()
    tx_hash = str(log.get("transactionHash") or "").strip().lower()
    log_index = _sync_liquidity_log_int(log.get("logIndex"))
    block_number = _sync_liquidity_log_int(log.get("blockNumber"))
    topics = log.get("topics") if isinstance(log.get("topics"), list) else []
    words = _decode_uint_words(log.get("data"), 1)
    raw_log_json, payload_digest = _top_expansion_raw_log_json_and_digest(row_filter, log)
    event_topic = str(topics[0]).lower() if topics else TRANSFER_TOPIC.lower()
    event_dedupe_key = f"{chain}|Transfer|{token_address}|{tx_hash}|{log_index}"
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    from_address = _sync_liquidity_topic_address(topics, 1)
    to_address = _sync_liquidity_topic_address(topics, 2)
    blockers: list[str] = []
    if event_topic != TRANSFER_TOPIC.lower():
        blockers.append("transfer_topic_mismatch")
    if not token_address:
        blockers.append("token_address_missing")
    if not from_address:
        blockers.append("from_address_missing")
    if not to_address:
        blockers.append("to_address_missing")
    if not tx_hash:
        blockers.append("tx_hash_missing")
    if log_index is None:
        blockers.append("log_index_missing")
    if block_number is None:
        blockers.append("block_number_missing")
    if not words:
        blockers.append("transfer_value_missing")
    insert_values = {
        "checkpoint_id": None,
        "chain": chain,
        "token_address": token_address,
        "from_address": from_address,
        "to_address": to_address,
        "value_raw": str(words[0]) if words else None,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "block_number": block_number,
        "raw_log_json": raw_log_json,
        "payload_digest": payload_digest,
        "event_dedupe_key": event_dedupe_key,
        "status": "raw_observed",
        "created_at": created_at,
        "source_policy": source_policy,
    }
    return {
        "target_table": "erc20_transfer_events",
        "event_name": "ERC20 Transfer",
        "event_dedupe_key": event_dedupe_key,
        "payload_digest": payload_digest,
        "insert_values": insert_values,
        "row_status": "eligible" if not blockers else "blocked",
        "row_blockers": blockers,
        "preview": {
            "target_table": "erc20_transfer_events",
            "candidate_pool_address": row_filter.get("candidate_pool_address"),
            "token_address": token_address,
            "from_address": from_address,
            "to_address": to_address,
            "tx_hash": tx_hash,
            "log_index": log_index,
            "block_number": block_number,
            "event_dedupe_key": event_dedupe_key,
            "payload_digest": payload_digest,
            "blockers": blockers,
        },
    }


def _build_top_expansion_raw_event_candidate(
    row_filter: dict[str, Any],
    log: dict[str, Any],
    source_policy: str,
) -> dict[str, Any]:
    event_name = str(row_filter.get("event_name") or "")
    if event_name == "Swap":
        return _build_top_expansion_swap_event_candidate(row_filter, log, source_policy)
    if event_name == "Sync":
        row = _build_sync_liquidity_event_row(row_filter, log)
        row.setdefault("insert_values", {})
        row["insert_values"]["created_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        row["insert_values"]["source_policy"] = source_policy
        row["source_policy"] = source_policy
        row["preview"] = {
            "target_table": row.get("target_table"),
            "candidate_pool_address": row_filter.get("candidate_pool_address"),
            "pair_address": row.get("pair_address"),
            "tx_hash": row.get("tx_hash"),
            "log_index": row.get("log_index"),
            "block_number": row.get("block_number"),
            "event_dedupe_key": row.get("event_dedupe_key"),
            "payload_digest": row.get("payload_digest"),
            "blockers": row.get("row_blockers"),
        }
        return row
    if event_name == "ERC20 Transfer":
        return _build_top_expansion_transfer_event_candidate(row_filter, log, source_policy)
    return {
        "target_table": None,
        "event_name": event_name,
        "event_dedupe_key": None,
        "payload_digest": None,
        "insert_values": {},
        "row_status": "blocked",
        "row_blockers": ["unsupported_top_expansion_event"],
        "preview": {
            "event_name": event_name,
            "blockers": ["unsupported_top_expansion_event"],
        },
    }


def get_manipulation_detection_reliability_engine(
    chain: str | None = "bsc",
    limit: int = 25,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only reliability engine for deciding whether manipulation detection is usable now."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 25), 100))
    source_policy = (
        "admin-only read-only manipulation detection reliability engine; reads local evidence, proof packages, "
        "raw event-reader rows, swaps, transfers, pair tokens, metadata and curated DEX rows. It does not call "
        "providers, scrape, write DB rows, create labels, mappings, router evidence, client signals, trades, "
        "wallet orders or opt-ins."
    )
    disabled = {
        "client_signal_ready": False,
        "trade_ready": False,
        "would_insert_candidate": False,
        "would_persist_evidence": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "engine_status": "blocked",
            "chain": clean_chain,
            "summary": {
                "can_detect_reliable_manipulation_now": False,
                "usable_candidates": 0,
                "research_leads": 0,
                "blocked_candidates": 0,
            },
            "candidates": [],
            "blockers": ["dry_run_required"],
            **disabled,
        }

    infrastructure_symbols = {"WETH", "WBNB", "USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USD1", "BTCB", "ETH", "BNB"}
    infrastructure_addresses = {
        "bsc": {
            "0x55d398326f99059ff775485246999027b3197955",  # USDT
            "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
            "0xe9e7cea3dedca5984780bafc599bd69add087d56",  # BUSD
            "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB
        }
    }
    table_counts: dict[str, int] = {}
    metadata_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _empty_candidate_key(pool: Any, token: Any) -> tuple[str, str]:
        return (str(pool or "").strip().lower(), str(token or "").strip().lower())

    def _token_meta(token_address: Any) -> dict[str, Any]:
        return _token_metadata_for(clean_chain, token_address, metadata_cache)

    def _token_symbol(token_address: Any) -> str | None:
        meta = _token_meta(token_address)
        symbol = str(meta.get("symbol") or meta.get("coin_id") or "").strip().upper()
        return symbol or None

    def _is_infra(token_address: Any) -> bool:
        address = str(token_address or "").strip().lower()
        symbol = _token_symbol(address) or ""
        return address in infrastructure_addresses.get(clean_chain, set()) or symbol.upper() in infrastructure_symbols

    def _choose_candidate_token(token0: Any, token1: Any) -> str | None:
        t0 = str(token0 or "").strip().lower()
        t1 = str(token1 or "").strip().lower()
        if t0 and not _is_infra(t0):
            return t0
        if t1 and not _is_infra(t1):
            return t1
        return t1 or t0 or None

    def _sql_count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> int:
        try:
            return int(conn.execute(sql, params).fetchone()[0] or 0)
        except sqlite3.OperationalError:
            return 0

    def _block_windows(conn: sqlite3.Connection, pool: str, token: str) -> int:
        windows: set[int] = set()
        if _table_exists(conn, "swaps"):
            for row in conn.execute(
                """
                SELECT block_number FROM swaps
                WHERE lower(chain) = ? AND lower(COALESCE(pool, '')) = ?
                """,
                (clean_chain, pool),
            ).fetchall():
                try:
                    windows.add(int(row[0]) // 5000)
                except (TypeError, ValueError):
                    pass
        if _table_exists(conn, "token_transfers"):
            for row in conn.execute(
                """
                SELECT block_number FROM token_transfers
                WHERE lower(chain) = ? AND (lower(COALESCE(token, '')) = ? OR lower(COALESCE(from_addr, '')) = ? OR lower(COALESCE(to_addr, '')) = ?)
                LIMIT 5000
                """,
                (clean_chain, token, pool, pool),
            ).fetchall():
                try:
                    windows.add(int(row[0]) // 5000)
                except (TypeError, ValueError):
                    pass
        return len(windows)

    def _raw_swap_repeatability(conn: sqlite3.Connection, pool: str) -> dict[str, Any]:
        if not _table_exists(conn, "dex_raw_swap_events"):
            return {
                "raw_independent_windows": 0,
                "raw_repeatability_from_events": False,
                "raw_windows": [],
                "raw_window_gap_blocks": 10_000,
                "raw_distinct_tx_hashes": 0,
                "raw_distinct_blocks": 0,
                "raw_payload_digest_missing_rows": 0,
                "raw_event_dedupe_missing_rows": 0,
                "raw_duplicate_event_dedupe_keys": 0,
            }

        rows = list(
            conn.execute(
                """
                SELECT block_number, block_timestamp, tx_hash, event_topic,
                       payload_digest, event_dedupe_key
                FROM dex_raw_swap_events
                WHERE lower(chain) = ? AND lower(pair_address) = ?
                ORDER BY block_number ASC, tx_hash ASC, log_index ASC
                """,
                (clean_chain, pool),
            )
        )
        gap_blocks = 10_000
        windows: list[dict[str, Any]] = []
        current: list[sqlite3.Row] = []
        previous_block: int | None = None

        def _flush_window() -> None:
            if not current:
                return
            blocks = [int(row["block_number"] or 0) for row in current]
            timestamps = [int(row["block_timestamp"] or 0) for row in current if row["block_timestamp"] is not None]
            txs = {str(row["tx_hash"] or "").lower() for row in current if row["tx_hash"]}
            windows.append(
                {
                    "window_index": len(windows) + 1,
                    "raw_swap_rows": len(current),
                    "distinct_tx_hashes": len(txs),
                    "distinct_blocks": len(set(blocks)),
                    "first_block": min(blocks) if blocks else None,
                    "last_block": max(blocks) if blocks else None,
                    "block_span": (max(blocks) - min(blocks) + 1) if blocks else 0,
                    "first_timestamp": min(timestamps) if timestamps else None,
                    "last_timestamp": max(timestamps) if timestamps else None,
                }
            )

        for row in rows:
            block_number = int(row["block_number"] or 0)
            if current and previous_block is not None and block_number - previous_block > gap_blocks:
                _flush_window()
                current = []
            current.append(row)
            previous_block = block_number
        _flush_window()

        tx_hashes = {str(row["tx_hash"] or "").lower() for row in rows if row["tx_hash"]}
        blocks = {int(row["block_number"] or 0) for row in rows if row["block_number"] is not None}
        missing_digest = sum(1 for row in rows if not str(row["payload_digest"] or "").strip())
        missing_dedupe = sum(1 for row in rows if not str(row["event_dedupe_key"] or "").strip())
        duplicate_dedupe = _sql_count(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT event_dedupe_key
                FROM dex_raw_swap_events
                WHERE lower(chain) = ? AND lower(pair_address) = ?
                GROUP BY event_dedupe_key
                HAVING COUNT(*) > 1
            )
            """,
            (clean_chain, pool),
        )
        repeatable = (
            len(rows) >= 10
            and len(tx_hashes) >= 10
            and len(blocks) >= 10
            and len(windows) >= 2
            and missing_digest == 0
            and missing_dedupe == 0
            and duplicate_dedupe == 0
        )
        return {
            "raw_independent_windows": len(windows),
            "raw_repeatability_from_events": bool(repeatable),
            "raw_windows": windows,
            "raw_window_gap_blocks": gap_blocks,
            "raw_distinct_tx_hashes": len(tx_hashes),
            "raw_distinct_blocks": len(blocks),
            "raw_payload_digest_missing_rows": missing_digest,
            "raw_event_dedupe_missing_rows": missing_dedupe,
            "raw_duplicate_event_dedupe_keys": duplicate_dedupe,
        }

    def _transfer_context_evidence_bridge(conn: sqlite3.Connection, pool: str, token: str) -> dict[str, Any]:
        if not _table_exists(conn, "dex_transfer_context_evidence"):
            return {
                "bridge_status": "not_available",
                "reviewed_evidence_rows": 0,
                "pool_evidence_rows": 0,
                "token_evidence_rows": 0,
                "ready_evidence_rows": 0,
                "ready_pool_evidence_rows": 0,
                "ready_token_evidence_rows": 0,
                "unique_wallets": 0,
                "unique_tx_hashes": 0,
                "unique_blocks": 0,
                "duplicate_event_dedupe_keys": 0,
                "blocked_rows": 0,
                "blockers": ["dex_transfer_context_evidence_table_missing"],
                "evidence_consumed_read_only": False,
            }

        transfer_topic = TRANSFER_TOPIC.lower()
        pool_address = str(pool or "").strip().lower()
        token_address = str(token or "").strip().lower()
        rows = list(
            conn.execute(
                """
                SELECT *
                FROM dex_transfer_context_evidence
                WHERE lower(chain) = ?
                  AND lower(COALESCE(pool_address, '')) = ?
                ORDER BY block_number ASC, tx_hash ASC, log_index ASC, id ASC
                LIMIT 5000
                """,
                (clean_chain, pool_address),
            )
        )
        duplicate_count = _sql_count(
            conn,
            """
            SELECT COUNT(*)
            FROM (
                SELECT event_dedupe_key
                FROM dex_transfer_context_evidence
                WHERE lower(chain) = ? AND lower(COALESCE(pool_address, '')) = ?
                GROUP BY event_dedupe_key
                HAVING COUNT(*) > 1
            )
            """,
            (clean_chain, pool_address),
        )
        ready_rows = 0
        ready_token_rows = 0
        blocked_rows = 0
        row_blockers: set[str] = set()
        wallets: set[str] = set()
        tx_hashes: set[str] = set()
        blocks: set[int] = set()
        tokens_seen: set[str] = set()

        for row in rows:
            raw_payload_json = str(row["raw_payload_json"] or "")
            raw_payload: dict[str, Any] | None = None
            try:
                loaded = json.loads(raw_payload_json)
                if isinstance(loaded, dict):
                    raw_payload = loaded
                else:
                    row_blockers.add("raw_payload_json_invalid")
            except Exception:
                row_blockers.add("raw_payload_json_invalid")

            current_digest = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest() if raw_payload_json else None
            payload_digest_bound = bool(row["payload_digest"] and row["payload_digest"] == current_digest)
            if not payload_digest_bound:
                row_blockers.add("payload_digest_not_bound")

            row_chain = str(row["chain"] or "").strip().lower()
            row_token = str(row["token_address"] or "").strip().lower()
            row_pool = str(row["pool_address"] or "").strip().lower()
            tx_hash = str(row["tx_hash"] or "").strip().lower()
            expected_dedupe_key = f"{row_chain}|Transfer|{row_token}|{tx_hash}|{row['log_index']}"
            dedupe_bound = bool(row["event_dedupe_key"] and str(row["event_dedupe_key"]) == expected_dedupe_key)
            if not dedupe_bound:
                row_blockers.add("event_dedupe_key_not_bound")

            raw_topic_bound = False
            if raw_payload:
                topics = [str(topic or "").strip().lower() for topic in raw_payload.get("topics") or []]
                raw_topic_bound = bool(topics and topics[0] == transfer_topic)
            event_topic_bound = bool(str(row["event_topic"] or "").strip().lower() == transfer_topic)
            if not event_topic_bound or not raw_topic_bound:
                row_blockers.add("transfer_topic_not_bound")

            source_bound = bool(
                str(row["source_type"] or "") == "sqd_portal_stream_api"
                and str(row["source_label"] or "") == "sqd_portal"
                and str(row["source_url"] or "").startswith("https://portal.sqd.dev/")
            )
            if not source_bound:
                row_blockers.add("source_context_not_bound")

            status_ready = bool(str(row["status"] or "") == "pending_admin_review")
            if not status_ready:
                row_blockers.add("status_not_pending_admin_review")

            pool_bound = bool(row_pool == pool_address)
            token_or_pair_context_bound = bool(row_token == token_address or row_pool == pool_address)
            if not pool_bound or not token_or_pair_context_bound:
                row_blockers.add("pool_or_token_context_not_bound")

            ready = bool(
                payload_digest_bound
                and dedupe_bound
                and event_topic_bound
                and raw_topic_bound
                and source_bound
                and status_ready
                and pool_bound
                and token_or_pair_context_bound
            )
            if ready:
                ready_rows += 1
                if row_token == token_address:
                    ready_token_rows += 1
            else:
                blocked_rows += 1

            if row_token:
                tokens_seen.add(row_token)
            if tx_hash:
                tx_hashes.add(tx_hash)
            if row["block_number"] is not None:
                try:
                    blocks.add(int(row["block_number"]))
                except (TypeError, ValueError):
                    pass
            for field in ("from_address", "to_address"):
                wallet = str(row[field] or "").strip().lower()
                if wallet and wallet != pool_address:
                    wallets.add(wallet)

        bridge_ready = bool(rows and ready_rows == len(rows) and duplicate_count == 0)
        blockers = list(
            dict.fromkeys(
                [
                    *("no_transfer_context_evidence_rows_for_pool" for _ in [1] if not rows),
                    *("duplicate_transfer_context_evidence_dedupe_keys" for _ in [1] if duplicate_count),
                    *("some_transfer_context_evidence_rows_blocked" for _ in [1] if blocked_rows),
                    *sorted(row_blockers),
                ]
            )
        )
        return {
            "bridge_status": "ready_read_only" if bridge_ready else "blocked",
            "reviewed_evidence_rows": len(rows),
            "pool_evidence_rows": len(rows),
            "token_evidence_rows": sum(1 for row in rows if str(row["token_address"] or "").strip().lower() == token_address),
            "ready_evidence_rows": ready_rows,
            "ready_pool_evidence_rows": ready_rows,
            "ready_token_evidence_rows": ready_token_rows,
            "unique_wallets": len(wallets),
            "unique_tx_hashes": len(tx_hashes),
            "unique_blocks": len(blocks),
            "unique_tokens": len(tokens_seen),
            "duplicate_event_dedupe_keys": duplicate_count,
            "blocked_rows": blocked_rows,
            "blockers": blockers,
            "evidence_consumed_read_only": bridge_ready,
            "would_insert_token_transfers": False,
            "would_mutate_erc20_transfer_events": False,
            "would_write": False,
        }

    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    def _candidate_for(pool: Any, token: Any, token0: Any = None, token1: Any = None) -> dict[str, Any] | None:
        clean_pool = str(pool or "").strip().lower()
        clean_token = str(token or "").strip().lower()
        if not clean_pool or not clean_token:
            return None
        key = _empty_candidate_key(clean_pool, clean_token)
        if key not in candidates:
            candidates[key] = {
                "chain": clean_chain,
                "pool": clean_pool,
                "token_address": clean_token,
                "token_symbol": _token_symbol(clean_token),
                "token0": str(token0 or "").strip().lower() or None,
                "token1": str(token1 or "").strip().lower() or None,
                "sources": set(),
                "route_proof_status": "unproven",
                "route_proof": {},
                "proof_package_context": {},
            }
        row = candidates[key]
        if token0 and not row.get("token0"):
            row["token0"] = str(token0).strip().lower()
        if token1 and not row.get("token1"):
            row["token1"] = str(token1).strip().lower()
        if not row.get("token_symbol"):
            row["token_symbol"] = _token_symbol(clean_token)
        return row

    conn = _get_db()
    conn.row_factory = sqlite3.Row
    try:
        metadata_cache = _load_token_metadata_cache(conn)
        source_tables = [
            "dex_paircreated_evidence",
            "dex_event_proof_packages",
            "dex_raw_paircreated_events",
            "dex_raw_swap_events",
            "erc20_transfer_events",
            "swaps",
            "token_transfers",
            "pair_tokens",
            "token_metadata",
            "dex_trades_curated",
            "wallet_chain_state",
        ]
        for table in source_tables:
            table_counts[table] = _sql_count(conn, f"SELECT COUNT(*) FROM {table}", ()) if _table_exists(conn, table) else 0

        if _table_exists(conn, "dex_paircreated_evidence"):
            for row in conn.execute(
                """
                SELECT * FROM dex_paircreated_evidence
                WHERE lower(chain) = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (clean_chain, clean_limit * 3),
            ).fetchall():
                token = _choose_candidate_token(row["token0"], row["token1"])
                candidate = _candidate_for(row["pair_address"], token, row["token0"], row["token1"])
                if not candidate:
                    continue
                candidate["sources"].add("dex_paircreated_evidence")
                accepted = str(row["status"] or "") == "accepted_for_future_mapping_review"
                candidate["route_proof_status"] = (
                    "source_backed_paircreated_evidence_accepted"
                    if accepted
                    else "paircreated_evidence_not_accepted"
                )
                candidate["route_proof"] = {
                    "paircreated_evidence_id": row["id"],
                    "status": row["status"],
                    "factory_address": row["factory_address"],
                    "pair_address": row["pair_address"],
                    "tx_hash": row["tx_hash"],
                    "log_index": row["log_index"],
                    "block_number": row["block_number"],
                    "dedupe_key": row["paircreated_dedupe_key"],
                    "proves_pool_creation_not_router_execution": True,
                }

        if _table_exists(conn, "pair_tokens"):
            for row in conn.execute(
                """
                SELECT chain, pool, token0, token1
                FROM pair_tokens
                WHERE lower(chain) = ?
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (clean_chain, clean_limit * 5),
            ).fetchall():
                token = _choose_candidate_token(row["token0"], row["token1"])
                candidate = _candidate_for(row["pool"], token, row["token0"], row["token1"])
                if candidate:
                    candidate["sources"].add("pair_tokens")

        if _table_exists(conn, "swaps"):
            for row in conn.execute(
                """
                SELECT chain, pool, token_in, token_out, COUNT(*) AS swaps
                FROM swaps
                WHERE lower(chain) = ? AND COALESCE(pool, '') != ''
                GROUP BY chain, pool, token_in, token_out
                ORDER BY swaps DESC
                LIMIT ?
                """,
                (clean_chain, clean_limit * 5),
            ).fetchall():
                token = row["token_out"] if not _is_infra(row["token_out"]) else row["token_in"]
                candidate = _candidate_for(row["pool"], token)
                if candidate:
                    candidate["sources"].add("swaps")

        for candidate in candidates.values():
            pool = str(candidate["pool"]).lower()
            token = str(candidate["token_address"]).lower()
            package_row = None
            if _table_exists(conn, "dex_event_proof_packages"):
                package_row = conn.execute(
                    """
                    SELECT id, status, proof_package_digest, proof_package_dedupe_key
                    FROM dex_event_proof_packages
                    WHERE lower(chain) = ? AND lower(subject_address) = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (clean_chain, pool),
                ).fetchone()
            if package_row:
                candidate["sources"].add("dex_event_proof_packages")
                candidate["proof_package_context"] = {
                    "proof_package_id": package_row["id"],
                    "status": package_row["status"],
                    "digest": package_row["proof_package_digest"],
                    "dedupe_key": package_row["proof_package_dedupe_key"],
                    "corroborates_existing_evidence": package_row["status"] == "accepted_for_future_proof_package_evidence_review",
                }

            swap_row = conn.execute(
                """
                SELECT COUNT(*) AS swap_rows,
                       COUNT(DISTINCT COALESCE(tx_hash, '')) AS txs,
                       COUNT(DISTINCT COALESCE(wallet, '')) AS wallets,
                       COUNT(DISTINCT COALESCE(router_addr, '')) AS routers,
                       COUNT(DISTINCT COALESCE(dex, '')) AS venues,
                       MIN(block_number) AS first_block,
                       MAX(block_number) AS last_block
                FROM swaps
                WHERE lower(chain) = ? AND lower(COALESCE(pool, '')) = ?
                """,
                (clean_chain, pool),
            ).fetchone() if _table_exists(conn, "swaps") else None
            raw_swap_rows = _sql_count(
                conn,
                "SELECT COUNT(*) FROM dex_raw_swap_events WHERE lower(chain) = ? AND lower(pair_address) = ?",
                (clean_chain, pool),
            )
            raw_repeatability = _raw_swap_repeatability(conn, pool)
            curated_rows = _sql_count(
                conn,
                "SELECT COUNT(*) FROM dex_trades_curated WHERE lower(chain) = ? AND lower(COALESCE(pool, '')) = ?",
                (clean_chain, pool),
            )
            token_transfer_rows = _sql_count(
                conn,
                "SELECT COUNT(*) FROM token_transfers WHERE lower(chain) = ? AND lower(COALESCE(token, '')) = ?",
                (clean_chain, token),
            )
            pool_transfer_rows = _sql_count(
                conn,
                """
                SELECT COUNT(*) FROM token_transfers
                WHERE lower(chain) = ? AND (lower(COALESCE(from_addr, '')) = ? OR lower(COALESCE(to_addr, '')) = ?)
                """,
                (clean_chain, pool, pool),
            )
            raw_pool_transfer_rows = _sql_count(
                conn,
                """
                SELECT COUNT(*) FROM erc20_transfer_events
                WHERE lower(chain) = ? AND (lower(COALESCE(from_address, '')) = ? OR lower(COALESCE(to_address, '')) = ?)
                """,
                (clean_chain, pool, pool),
            )
            transfer_evidence_bridge = _transfer_context_evidence_bridge(conn, pool, token)
            transfer_wallets = _sql_count(
                conn,
                """
                SELECT COUNT(DISTINCT wallet) FROM (
                    SELECT lower(from_addr) AS wallet FROM token_transfers WHERE lower(chain) = ? AND lower(COALESCE(token, '')) = ?
                    UNION
                    SELECT lower(to_addr) AS wallet FROM token_transfers WHERE lower(chain) = ? AND lower(COALESCE(token, '')) = ?
                )
                WHERE wallet IS NOT NULL AND wallet != '' AND wallet != ?
                """,
                (clean_chain, token, clean_chain, token, pool),
            )
            swap_metrics = dict(swap_row) if swap_row else {}
            local_swap_rows = int(swap_metrics.get("swap_rows") or 0)
            swap_wallets = int(swap_metrics.get("wallets") or 0)
            exact_swap_rows = int(raw_swap_rows + curated_rows)
            current_best_transfer_rows = max(token_transfer_rows, pool_transfer_rows)
            bridged_transfer_rows = current_best_transfer_rows + int(
                transfer_evidence_bridge.get("ready_pool_evidence_rows") or 0
            )
            bridged_transfer_wallets = max(
                transfer_wallets,
                int(transfer_evidence_bridge.get("unique_wallets") or 0),
            )
            context_windows = _block_windows(conn, pool, token)
            raw_windows = int(raw_repeatability.get("raw_independent_windows") or 0)
            windows = max(context_windows, raw_windows)
            token_identity_clear = bool(candidate.get("token_symbol")) and not _is_infra(token)
            route_proven = candidate.get("route_proof_status") == "source_backed_paircreated_evidence_accepted"
            pattern_candidates: list[str] = []
            if route_proven and raw_pool_transfer_rows >= 2:
                pattern_candidates.append("liquidity_seeding_context")
            if local_swap_rows > 0:
                pattern_candidates.append("local_swap_activity_context")
            if exact_swap_rows >= 10:
                pattern_candidates.append("exact_swap_series_available")
            if transfer_wallets >= 2:
                pattern_candidates.append("multi_wallet_transfer_context")
            if bool(raw_repeatability.get("raw_repeatability_from_events")):
                pattern_candidates.append("raw_swap_repeatability_context")
            elif windows >= 2:
                pattern_candidates.append("multi_window_repeatability_context")

            blockers: list[str] = []
            if not route_proven:
                blockers.append("route_pool_not_source_backed")
            if not token_identity_clear:
                blockers.append("token_identity_missing_or_infrastructure")
            if exact_swap_rows < 10:
                blockers.append("too_few_exact_swaps_min_10")
            if bridged_transfer_rows < 10:
                blockers.append("too_few_transfer_rows_min_10")
            if max(swap_wallets, bridged_transfer_wallets) < 2:
                blockers.append("too_few_wallets_or_clusters_min_2")
            if windows < 2:
                blockers.append("repeatability_missing_min_2_windows")
            if not pattern_candidates:
                blockers.append("no_explainable_manipulation_pattern")
            blockers.extend(
                [
                    "source_backed_scoring_not_ready",
                    "shadow_backtest_not_ready",
                    "policy_risk_gate_missing",
                    "client_opt_in_missing",
                ]
            )

            score = 0
            score += 25 if route_proven else 0
            score += 15 if token_identity_clear else 0
            score += min(20, exact_swap_rows * 2)
            score += min(10, bridged_transfer_rows)
            score += 10 if max(swap_wallets, bridged_transfer_wallets) >= 2 else 0
            score += 10 if windows >= 2 else 0
            score += 10 if pattern_candidates else 0
            usable = not blockers
            candidate.update({
                "sources": sorted(candidate["sources"]),
                "token_symbol": candidate.get("token_symbol") or "UNKNOWN",
                "token_is_infrastructure": _is_infra(token),
                "data_coverage": {
                    "local_swaps_context_rows": local_swap_rows,
                    "raw_swap_rows": raw_swap_rows,
                    "curated_dex_rows": curated_rows,
                    "exact_swap_rows": exact_swap_rows,
                    "raw_distinct_tx_hashes": raw_repeatability.get("raw_distinct_tx_hashes"),
                    "raw_distinct_blocks": raw_repeatability.get("raw_distinct_blocks"),
                    "token_transfer_rows": token_transfer_rows,
                    "pool_transfer_rows": pool_transfer_rows,
                    "raw_pool_transfer_rows": raw_pool_transfer_rows,
                    "transfer_context_evidence_bridge": transfer_evidence_bridge,
                    "current_best_transfer_rows_before_evidence_bridge": current_best_transfer_rows,
                    "transfer_context_evidence_rows_consumed_read_only": int(
                        transfer_evidence_bridge.get("ready_pool_evidence_rows") or 0
                    ),
                    "best_transfer_rows_after_evidence_bridge": bridged_transfer_rows,
                    "swap_wallets": swap_wallets,
                    "transfer_wallets": transfer_wallets,
                    "transfer_context_evidence_wallets": int(transfer_evidence_bridge.get("unique_wallets") or 0),
                    "best_transfer_wallets_after_evidence_bridge": bridged_transfer_wallets,
                    "context_block_windows": context_windows,
                    "raw_independent_windows": raw_windows,
                    "block_windows": windows,
                    "raw_repeatability_from_events": raw_repeatability.get("raw_repeatability_from_events"),
                    "raw_window_gap_blocks": raw_repeatability.get("raw_window_gap_blocks"),
                    "raw_windows": raw_repeatability.get("raw_windows"),
                    "raw_payload_digest_missing_rows": raw_repeatability.get("raw_payload_digest_missing_rows"),
                    "raw_event_dedupe_missing_rows": raw_repeatability.get("raw_event_dedupe_missing_rows"),
                    "raw_duplicate_event_dedupe_keys": raw_repeatability.get("raw_duplicate_event_dedupe_keys"),
                    "first_swap_block": swap_metrics.get("first_block"),
                    "last_swap_block": swap_metrics.get("last_block"),
                },
                "repeatability_status": (
                    "present_from_raw_events"
                    if bool(raw_repeatability.get("raw_repeatability_from_events"))
                    else "present"
                    if windows >= 2
                    else "missing"
                ),
                "manipulation_patterns": pattern_candidates,
                "confidence_score": int(score),
                "usable_for_manipulation_detection": bool(usable),
                "candidate_status": (
                    "usable_for_shadow_manipulation_detection"
                    if usable
                    else "research_lead_blocked"
                    if route_proven or pattern_candidates
                    else "blocked_unproven"
                ),
                "blockers": list(dict.fromkeys(blockers)),
                "next_data_needed": [
                    *("collect_exact_swap_events_for_pool" for _ in [1] if exact_swap_rows < 10),
                    *("collect_more_token_or_pool_transfers" for _ in [1] if bridged_transfer_rows < 10),
                    *("collect_second_time_window" for _ in [1] if windows < 2),
                    *("resolve_token_identity_or_exclude_infrastructure" for _ in [1] if not token_identity_clear),
                    "build_source_backed_scoring",
                    "run_shadow_backtest",
                    "define_policy_risk_gate_and_client_opt_in",
                    "run_shadow_backtest_only_after_reliability_gates_pass",
                ],
                "client_signal_ready": False,
                "trade_ready": False,
            })
    finally:
        conn.close()

    candidate_rows = sorted(
        candidates.values(),
        key=lambda item: (
            bool(item.get("usable_for_manipulation_detection")),
            int(item.get("confidence_score") or 0),
            int((item.get("data_coverage") or {}).get("exact_swap_rows") or 0),
        ),
        reverse=True,
    )[:clean_limit]
    usable_count = sum(1 for row in candidate_rows if row.get("usable_for_manipulation_detection"))
    research_count = sum(1 for row in candidate_rows if row.get("candidate_status") == "research_lead_blocked")
    overall_blockers = []
    if not candidate_rows:
        overall_blockers.append("no_local_candidates_found")
    if usable_count == 0:
        overall_blockers.append("no_candidate_passes_reliability_gates")
    if table_counts.get("dex_raw_swap_events", 0) == 0:
        overall_blockers.append("no_raw_swap_events")
    if table_counts.get("dex_trades_curated", 0) < 50:
        overall_blockers.append("curated_dex_history_too_small")

    return {
        "ok": True,
        "dry_run": True,
        "engine_status": "ready_read_only",
        "chain": clean_chain,
        "can_detect_reliable_manipulation_now": bool(usable_count > 0),
        "summary": {
            "can_detect_reliable_manipulation_now": bool(usable_count > 0),
            "usable_candidates": usable_count,
            "research_leads": research_count,
            "blocked_candidates": len(candidate_rows) - usable_count,
            "candidate_rows_returned": len(candidate_rows),
            "client_signal_ready": False,
            "trade_ready": False,
            "real_write_enabled": False,
        },
        "reliability_gates": {
            "route_or_pool_source_backed": "required",
            "token_identity_clear_non_infrastructure": "required",
            "min_exact_swap_rows": 10,
            "min_transfer_rows": 10,
            "min_wallets_or_clusters": 2,
            "min_time_windows": 2,
            "raw_swap_repeatability_can_satisfy_time_windows": True,
            "pattern_explainability": "required",
            "not_sufficient": ["PairCreated alone", "amount_usd alone", "external source alone", "single-window activity"],
        },
        "table_counts": table_counts,
        "candidates": candidate_rows,
        "blockers": list(dict.fromkeys(overall_blockers)),
        "plain_summary_fr": (
            "Non: la detection fiable n'est pas encore atteinte. La meilleure piste actuelle est UFLOKI en research-only: "
            "elle a une route/pool prouvee, des swaps raw repetes sur plusieurs fenetres et une corroboration de liquidite, "
            "mais il manque encore du contexte transfert suffisant, du scoring source-backed et un shadow/backtest."
        ),
        "next_safe_step": (
            "bounded_transfer_context_collection_for_top_research_leads"
            if candidate_rows
            else "collect_more_local_pair_and_transfer_data"
        ),
        **disabled,
    }


def get_manipulation_detection_source_backed_scoring_design(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only source-backed scoring design built from the reliability engine output."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    source_policy = (
        "admin-only read-only source-backed manipulation scoring design; composes the existing reliability "
        "engine output and does not persist scores, create mappings, create client signals, execute trades, "
        "create wallet orders or create client opt-ins."
    )
    disabled = {
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "design_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    reliability = get_manipulation_detection_reliability_engine(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
    )
    candidates = list(reliability.get("candidates") or [])
    matched_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_pool = str(candidate.get("pool") or "").strip().lower()
        candidate_token = str(candidate.get("token_address") or "").strip().lower()
        if clean_pool and candidate_pool != clean_pool:
            continue
        if clean_token and candidate_token != clean_token:
            continue
        matched_candidates.append(candidate)

    candidate = matched_candidates[0] if matched_candidates else None
    if not candidate:
        return {
            "ok": True,
            "dry_run": True,
            "design_status": "blocked",
            "chain": clean_chain,
            "pool_address": clean_pool or None,
            "token_address": clean_token or None,
            "reliability_engine_status": reliability.get("engine_status"),
            "summary": {
                "candidate_found": False,
                "source_backed_scoring_design_ready": False,
                "source_backed_scoring_live_ready": False,
                "client_signal_ready": False,
                "trade_ready": False,
                "real_write_enabled": False,
            },
            "blockers": list(dict.fromkeys([
                "candidate_not_found_in_reliability_engine",
                *(reliability.get("blockers") or []),
            ])),
            "next_safe_step": "collect_more_local_pair_swap_transfer_context_or_relax_filters",
            **disabled,
        }

    coverage = dict(candidate.get("data_coverage") or {})
    transfer_bridge = dict(coverage.get("transfer_context_evidence_bridge") or {})
    patterns = list(candidate.get("manipulation_patterns") or [])
    exact_swap_rows = int(coverage.get("exact_swap_rows") or 0)
    best_transfer_rows = int(coverage.get("best_transfer_rows_after_evidence_bridge") or 0)
    best_transfer_wallets = int(coverage.get("best_transfer_wallets_after_evidence_bridge") or 0)
    windows = int(coverage.get("block_windows") or 0)
    raw_missing_digest = int(coverage.get("raw_payload_digest_missing_rows") or 0)
    raw_missing_dedupe = int(coverage.get("raw_event_dedupe_missing_rows") or 0)
    raw_duplicate_dedupe = int(coverage.get("raw_duplicate_event_dedupe_keys") or 0)
    transfer_duplicate_dedupe = int(transfer_bridge.get("duplicate_event_dedupe_keys") or 0)

    gates = {
        "route_pool_source_backed": candidate.get("route_proof_status") == "source_backed_paircreated_evidence_accepted",
        "paircreated_evidence_bound": bool((candidate.get("route_proof") or {}).get("paircreated_evidence_id")),
        "proof_package_corroborated": bool((candidate.get("proof_package_context") or {}).get("corroborates_existing_evidence")),
        "token_identity_clear_non_infrastructure": bool(candidate.get("token_symbol")) and not bool(candidate.get("token_is_infrastructure")),
        "exact_swap_rows_min_10": exact_swap_rows >= 10,
        "raw_swap_integrity_bound": raw_missing_digest == 0 and raw_missing_dedupe == 0 and raw_duplicate_dedupe == 0,
        "transfer_context_bridge_ready": transfer_bridge.get("bridge_status") == "ready_read_only",
        "transfer_rows_min_10_after_bridge": best_transfer_rows >= 10,
        "transfer_evidence_dedupe_clean": transfer_duplicate_dedupe == 0,
        "wallet_cluster_min_2": best_transfer_wallets >= 2,
        "repeatability_min_2_windows": windows >= 2,
        "pattern_explainability_present": bool(patterns),
    }
    gate_blockers = [
        f"{name}_missing"
        for name, passed in gates.items()
        if not passed
    ]
    foundation_ready = all(gates.values())

    scoring_weights = {
        "route_pool_source_backed": 20,
        "paircreated_and_proof_package_bound": 15,
        "exact_swap_depth_and_integrity": 20,
        "transfer_context_depth": 15,
        "wallet_cluster_breadth": 10,
        "multi_window_repeatability": 10,
        "pattern_explainability": 10,
    }
    scoring_preview = {
        "score_name": "ufloki_source_backed_research_score_v0",
        "output_scope": "research_only_shadow_score_preview",
        "current_research_confidence_preview": int(candidate.get("confidence_score") or 0),
        "weights": scoring_weights,
        "features_from_existing_engine": {
            "route_proof_status": candidate.get("route_proof_status"),
            "exact_swap_rows": exact_swap_rows,
            "raw_distinct_tx_hashes": coverage.get("raw_distinct_tx_hashes"),
            "raw_distinct_blocks": coverage.get("raw_distinct_blocks"),
            "best_transfer_rows_after_evidence_bridge": best_transfer_rows,
            "best_transfer_wallets_after_evidence_bridge": best_transfer_wallets,
            "block_windows": windows,
            "patterns": patterns,
        },
        "forbidden_outputs": [
            "no persisted client score",
            "no client signal",
            "no trade",
            "no mapping",
            "no router evidence",
            "no opt-in",
        ],
    }
    blockers = list(dict.fromkeys([
        *gate_blockers,
        "shadow_backtest_not_ready",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))

    return {
        "ok": True,
        "dry_run": True,
        "design_status": "ready_but_disabled" if foundation_ready else "blocked",
        "chain": clean_chain,
        "pool_address": candidate.get("pool"),
        "token_address": candidate.get("token_address"),
        "token_symbol": candidate.get("token_symbol"),
        "reliability_engine_status": reliability.get("engine_status"),
        "source_evidence": {
            "route_proof": candidate.get("route_proof"),
            "proof_package_context": candidate.get("proof_package_context"),
            "transfer_context_evidence_bridge": transfer_bridge,
        },
        "source_backed_foundation_gates": gates,
        "scoring_design": scoring_preview,
        "summary": {
            "candidate_found": True,
            "source_backed_foundation_ready": foundation_ready,
            "source_backed_scoring_design_ready": foundation_ready,
            "source_backed_scoring_live_ready": False,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
            "real_write_enabled": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "source_backed_shadow_backtest_plan_read_only"
            if foundation_ready
            else "repair_missing_source_backed_scoring_gates"
        ),
        "plain_summary_fr": (
            "UFLOKI a maintenant assez de preuves locales pour dessiner un score research-only: route prouvee, "
            "swaps exacts, transferts bridges, wallets et repetition. Mais ce score n'est pas active cote client: "
            "il manque encore shadow/backtest, policy risk et opt-in client."
        ),
        **disabled,
    }


def get_manipulation_detection_source_backed_shadow_backtest_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only plan for testing source-backed manipulation scoring in shadow mode."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    source_policy = (
        "admin-only read-only source-backed shadow/backtest plan; composes the existing source-backed scoring "
        "design and reliability engine output. It does not run or persist a backtest, create client signals, "
        "execute trades, create wallet orders, create mappings, create labels or create client opt-ins."
    )
    disabled = {
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    scoring = get_manipulation_detection_source_backed_scoring_design(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
    )
    summary = dict(scoring.get("summary") or {})
    gates = dict(scoring.get("source_backed_foundation_gates") or {})
    scoring_design = dict(scoring.get("scoring_design") or {})
    features = dict(scoring_design.get("features_from_existing_engine") or {})
    source_evidence = dict(scoring.get("source_evidence") or {})
    foundation_ready = bool(summary.get("source_backed_foundation_ready"))

    exact_swap_rows = int(features.get("exact_swap_rows") or 0)
    transfer_rows = int(features.get("best_transfer_rows_after_evidence_bridge") or 0)
    transfer_wallets = int(features.get("best_transfer_wallets_after_evidence_bridge") or 0)
    windows = int(features.get("block_windows") or 0)
    raw_distinct_txs = int(features.get("raw_distinct_tx_hashes") or 0)
    raw_distinct_blocks = int(features.get("raw_distinct_blocks") or 0)
    patterns = list(features.get("patterns") or [])

    dataset_preview = {
        "candidate_scope": "single_source_backed_case_study",
        "chain": clean_chain,
        "pool_address": scoring.get("pool_address"),
        "token_address": scoring.get("token_address"),
        "token_symbol": scoring.get("token_symbol"),
        "source_proof_type": "historical_paircreated_plus_reviewed_transfer_and_raw_swap_evidence",
        "exact_swap_rows": exact_swap_rows,
        "raw_distinct_tx_hashes": raw_distinct_txs,
        "raw_distinct_blocks": raw_distinct_blocks,
        "transfer_rows_after_bridge": transfer_rows,
        "transfer_wallets_after_bridge": transfer_wallets,
        "independent_windows": windows,
        "patterns": patterns,
        "minimum_for_shadow_case_study": {
            "source_backed_foundation_ready": True,
            "exact_swap_rows": 10,
            "transfer_rows_after_bridge": 10,
            "transfer_wallets_after_bridge": 2,
            "independent_windows": 2,
            "pattern_explainability_present": True,
        },
        "not_enough_for_client_model": [
            "only_one_source_backed_case",
            "no negative controls yet",
            "no forward price/liquidity outcome table yet",
            "no policy/risk calibration yet",
        ],
    }
    shadow_backtest_contract = {
        "mode": "shadow_only_no_client_output",
        "purpose": "measure whether the research score would have identified an exploitable manipulation setup without trading",
        "entry_snapshot": [
            "source-backed route/pool proof",
            "raw Swap repeatability",
            "transfer context breadth",
            "wallet cluster breadth",
            "pattern explainability",
        ],
        "required_future_outcomes": [
            "post-snapshot price movement",
            "post-snapshot liquidity movement",
            "drawdown before move",
            "time-to-move",
            "false-positive comparison against clean tokens",
            "repeatability across more than one token",
        ],
        "metrics_to_compute_later": [
            "precision_proxy",
            "false_positive_rate",
            "max_adverse_excursion",
            "max_favorable_excursion",
            "time_to_signal_expiry",
            "liquidity_slippage_risk",
            "paper_trade_expected_value",
        ],
        "hard_stop_conditions": [
            "source evidence drift",
            "dedupe drift",
            "route/factory/pair mismatch",
            "token identity ambiguity",
            "insufficient liquidity context",
            "too few comparable candidates",
        ],
    }
    next_data_requirements = [
        {
            "requirement": "outcome_window_dataset",
            "why": "we need to know what happened after the evidence snapshot before calling the setup useful",
            "current_status": "missing",
            "write_allowed_now": False,
        },
        {
            "requirement": "negative_control_candidates",
            "why": "a reliable detector must reject normal pools, not only recognize one interesting case",
            "current_status": "missing",
            "write_allowed_now": False,
        },
        {
            "requirement": "multi_candidate_replay",
            "why": "UFLOKI alone can prove the lane works, not that the model generalizes",
            "current_status": "missing",
            "write_allowed_now": False,
        },
        {
            "requirement": "policy_risk_gate",
            "why": "even a good shadow score cannot become a client signal or trade without risk limits",
            "current_status": "missing",
            "write_allowed_now": False,
        },
    ]
    plan_fingerprint_payload = {
        "chain": clean_chain,
        "pool": scoring.get("pool_address"),
        "token": scoring.get("token_address"),
        "score_name": scoring_design.get("score_name"),
        "exact_swap_rows": exact_swap_rows,
        "transfer_rows": transfer_rows,
        "transfer_wallets": transfer_wallets,
        "windows": windows,
    }
    plan_digest = hashlib.sha256(
        json.dumps(plan_fingerprint_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    blockers = list(dict.fromkeys([
        *(scoring.get("blockers") or []),
        *([] if foundation_ready else ["source_backed_foundation_not_ready"]),
        "shadow_backtest_execution_not_built",
        "outcome_window_dataset_missing",
        "negative_controls_missing",
        "multi_candidate_validation_missing",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    if foundation_ready:
        plan_status = "ready_but_disabled"
        next_safe_step = "source_backed_shadow_backtest_outcome_dataset_schema_plan_read_only"
    else:
        plan_status = "blocked"
        next_safe_step = "repair_missing_source_backed_scoring_gates"

    return {
        "ok": True,
        "dry_run": True,
        "plan_status": plan_status,
        "chain": clean_chain,
        "pool_address": scoring.get("pool_address") or clean_pool or None,
        "token_address": scoring.get("token_address") or clean_token or None,
        "token_symbol": scoring.get("token_symbol"),
        "scoring_design_status": scoring.get("design_status"),
        "source_evidence": source_evidence,
        "source_backed_foundation_gates": gates,
        "dataset_preview": dataset_preview,
        "shadow_backtest_contract": shadow_backtest_contract,
        "next_data_requirements": next_data_requirements,
        "plan_digest": plan_digest,
        "summary": {
            "candidate_found": bool(summary.get("candidate_found")),
            "source_backed_foundation_ready": foundation_ready,
            "shadow_backtest_plan_ready": foundation_ready,
            "shadow_backtest_executable_now": False,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
            "real_write_enabled": False,
        },
        "blockers": blockers,
        "next_safe_step": next_safe_step,
        "plain_summary_fr": (
            "Le plan shadow/backtest est pret en lecture seule pour UFLOKI si la fondation source-backed reste valide. "
            "Il ne dit pas encore que la manipulation est rentable ou exploitable: il explique quelles mesures futures "
            "devront prouver le resultat avant tout signal client ou trade."
            if foundation_ready
            else "Le plan shadow/backtest reste bloque tant que la fondation source-backed n'est pas complete."
        ),
        **disabled,
    }


def get_manipulation_detection_source_backed_shadow_backtest_outcome_dataset_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only schema-plan for future source-backed shadow/backtest outcome windows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    target_table = "manipulation_shadow_backtest_outcome_windows"
    source_policy = (
        "admin-only read-only schema-plan for future manipulation shadow/backtest outcome windows. It composes "
        "the source-backed shadow/backtest plan and does not create the table, persist outcomes, create client "
        "signals, execute trades, create mappings, create labels or create client opt-ins."
    )
    disabled = {
        "would_create_table": False,
        "would_insert_outcome_row": False,
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "target_table": target_table,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    shadow_plan = get_manipulation_detection_source_backed_shadow_backtest_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
    )
    shadow_summary = dict(shadow_plan.get("summary") or {})
    shadow_ready = bool(shadow_summary.get("shadow_backtest_plan_ready"))
    plan_digest = str(shadow_plan.get("plan_digest") or "").strip()
    pool = str(shadow_plan.get("pool_address") or clean_pool or "").strip().lower()
    token = str(shadow_plan.get("token_address") or clean_token or "").strip().lower()
    token_symbol = str(shadow_plan.get("token_symbol") or "").strip().upper() or None
    table_exists = False
    existing_rows = 0
    try:
        conn = _get_db()
        try:
            table_exists = _table_exists(conn, target_table)
            if table_exists:
                existing_rows = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
        finally:
            conn.close()
    except Exception:
        table_exists = False
        existing_rows = 0

    schema_preview = [
        {"name": "id", "type": "INTEGER PRIMARY KEY AUTOINCREMENT", "purpose": "local outcome row id"},
        {"name": "chain", "type": "TEXT NOT NULL", "purpose": "chain scope, e.g. bsc"},
        {"name": "pool_address", "type": "TEXT NOT NULL", "purpose": "source-backed pool under test"},
        {"name": "token_address", "type": "TEXT NOT NULL", "purpose": "non-infrastructure token under test"},
        {"name": "token_symbol", "type": "TEXT", "purpose": "display symbol only, not proof"},
        {"name": "source_plan_digest", "type": "TEXT NOT NULL", "purpose": "digest of the read-only shadow/backtest plan"},
        {"name": "source_score_name", "type": "TEXT NOT NULL", "purpose": "score design name used for the shadow test"},
        {"name": "evidence_snapshot_json", "type": "TEXT NOT NULL", "purpose": "frozen evidence summary used as the simulated entry context"},
        {"name": "outcome_window_label", "type": "TEXT NOT NULL", "purpose": "window label such as plus_1h, plus_6h, plus_24h"},
        {"name": "snapshot_block_number", "type": "INTEGER", "purpose": "block at the simulated evidence snapshot"},
        {"name": "from_block", "type": "INTEGER NOT NULL", "purpose": "first outcome block"},
        {"name": "to_block", "type": "INTEGER NOT NULL", "purpose": "last outcome block"},
        {"name": "from_timestamp", "type": "INTEGER", "purpose": "first outcome timestamp"},
        {"name": "to_timestamp", "type": "INTEGER", "purpose": "last outcome timestamp"},
        {"name": "price_start", "type": "REAL", "purpose": "starting price/liquidity proxy"},
        {"name": "price_high", "type": "REAL", "purpose": "best observed price/liquidity proxy"},
        {"name": "price_low", "type": "REAL", "purpose": "worst observed price/liquidity proxy"},
        {"name": "price_end", "type": "REAL", "purpose": "ending price/liquidity proxy"},
        {"name": "liquidity_start", "type": "REAL", "purpose": "starting liquidity proxy"},
        {"name": "liquidity_end", "type": "REAL", "purpose": "ending liquidity proxy"},
        {"name": "max_favorable_move_pct", "type": "REAL", "purpose": "shadow upside measurement"},
        {"name": "max_adverse_move_pct", "type": "REAL", "purpose": "shadow drawdown measurement"},
        {"name": "time_to_peak_blocks", "type": "INTEGER", "purpose": "how fast the best move appeared"},
        {"name": "control_group_label", "type": "TEXT", "purpose": "negative-control cohort label if available"},
        {"name": "outcome_quality", "type": "TEXT NOT NULL", "purpose": "usable, partial, blocked or control_only"},
        {"name": "outcome_payload_json", "type": "TEXT NOT NULL", "purpose": "raw normalized outcome preview"},
        {"name": "outcome_digest", "type": "TEXT NOT NULL", "purpose": "hash of normalized outcome payload"},
        {"name": "outcome_dedupe_key", "type": "TEXT NOT NULL UNIQUE", "purpose": "no overwrite/no upsert guard"},
        {"name": "status", "type": "TEXT NOT NULL DEFAULT 'pending_admin_review'", "purpose": "future review status only"},
        {"name": "created_at", "type": "TEXT NOT NULL", "purpose": "future insertion timestamp"},
        {"name": "source_policy", "type": "TEXT NOT NULL", "purpose": "policy that produced the row"},
    ]
    indexes_preview = [
        "UNIQUE(outcome_dedupe_key)",
        "INDEX(chain, pool_address, token_address)",
        "INDEX(source_plan_digest)",
        "INDEX(status)",
        "INDEX(outcome_quality)",
        "INDEX(from_block, to_block)",
        "INDEX(token_symbol)",
    ]
    constraints_preview = [
        "dry_run_required_for_schema_plan",
        "source_shadow_backtest_plan_must_be_ready",
        "source_plan_digest_required",
        "pool_and_token_required",
        "outcome_dedupe_key_unique",
        "no_overwrite",
        "no_upsert",
        "no_client_signal",
        "no_trade",
        "no_mapping",
        "no_label",
        "no_opt_in",
    ]
    dedupe_formula = (
        "chain|pool_address|token_address|source_plan_digest|outcome_window_label|from_block|to_block"
    )
    blockers = list(dict.fromkeys([
        *(shadow_plan.get("blockers") or []),
        *([] if shadow_ready else ["source_shadow_backtest_plan_not_ready"]),
        *([] if plan_digest else ["source_plan_digest_missing"]),
        *([] if pool else ["pool_address_missing"]),
        *([] if token else ["token_address_missing"]),
        "schema_plan_only_no_table_created",
        "outcome_collection_not_built",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    plan_ready = bool(shadow_ready and plan_digest and pool and token)

    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready" if plan_ready else "blocked",
        "chain": clean_chain,
        "pool_address": pool or None,
        "token_address": token or None,
        "token_symbol": token_symbol,
        "target_table": target_table,
        "table_exists": table_exists,
        "existing_rows": existing_rows,
        "migration_required": not table_exists,
        "confirm_required": "CREATE_MANIPULATION_SHADOW_BACKTEST_OUTCOME_WINDOWS",
        "schema_preview": schema_preview,
        "indexes_preview": indexes_preview,
        "constraints_preview": constraints_preview,
        "dedupe_constraints": {
            "outcome_dedupe_key_formula": dedupe_formula,
            "duplicate_future_insert": "block",
            "overwrite": "blocked",
            "upsert": "blocked",
            "silent_success": "blocked",
        },
        "source_shadow_backtest_plan": {
            "plan_status": shadow_plan.get("plan_status"),
            "plan_digest": plan_digest or None,
            "summary": shadow_summary,
            "dataset_preview": shadow_plan.get("dataset_preview"),
            "next_data_requirements": shadow_plan.get("next_data_requirements"),
        },
        "blockers": blockers,
        "next_safe_step": (
            "confirmed_empty_ddl_migration_for_outcome_windows"
            if plan_ready and not table_exists
            else "outcome_window_collection_plan_read_only"
            if plan_ready
            else "repair_shadow_backtest_plan_gates"
        ),
        "plain_summary_fr": (
            "La table future servirait a stocker ce qui s'est passe apres le signal research UFLOKI: hausse, drawdown, "
            "liquidite, temps de reaction et controles negatifs. Elle ne creerait toujours pas de signal client ni trade."
        ),
        **disabled,
    }


def get_manipulation_detection_source_backed_outcome_window_data_collection_dry_run(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Read-only local outcome windows for the source-backed manipulation case."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    source_policy = (
        "admin-only read-only UFLOKI/source-backed outcome window collection dry-run. It reads local "
        "dex_raw_swap_events and source-backed shadow/backtest plan output. External corroboration is disabled "
        "unless explicitly allowed and confirmed; no outcomes are persisted, no table is created, no client "
        "signal, trade, mapping, label, wallet order or opt-in is created."
    )
    disabled = {
        "would_call_external": False,
        "would_insert_outcome_row": False,
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "collection_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    external_confirm = "ALLOW_READ_ONLY_OUTCOME_EXTERNAL_CORROBORATION"
    external_comparison = {
        "allow_external": bool(allow_external),
        "called": False,
        "status": "not_called_local_first",
        "required_confirm": external_confirm,
        "sources": ["geckoterminal", "dexscreener"],
        "reason": (
            "external corroboration remains disabled until explicitly confirmed"
            if allow_external and confirm != external_confirm
            else "local dex_raw_swap_events are evaluated first"
        ),
    }
    if allow_external and confirm == external_confirm:
        external_comparison.update({
            "status": "available_but_not_implemented_in_this_dry_run",
            "reason": "external calls are intentionally kept out of this local outcome pass",
        })

    shadow_plan = get_manipulation_detection_source_backed_shadow_backtest_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
    )
    shadow_summary = dict(shadow_plan.get("summary") or {})
    shadow_ready = bool(shadow_summary.get("shadow_backtest_plan_ready"))
    pool = str(shadow_plan.get("pool_address") or clean_pool or "").strip().lower()
    token = str(shadow_plan.get("token_address") or clean_token or "").strip().lower()
    token_symbol = str(shadow_plan.get("token_symbol") or "").strip().upper() or None
    plan_digest = str(shadow_plan.get("plan_digest") or "").strip()

    blockers = list(dict.fromkeys([
        *(shadow_plan.get("blockers") or []),
        *([] if shadow_ready else ["source_shadow_backtest_plan_not_ready"]),
        *([] if pool else ["pool_address_missing"]),
        *([] if token else ["token_address_missing"]),
        *([] if plan_digest else ["source_plan_digest_missing"]),
    ]))
    if allow_external and confirm != external_confirm:
        blockers.append("external_corroboration_confirm_required")

    stable_addresses = {
        "bsc": {
            "0x55d398326f99059ff775485246999027b3197955",  # USDT
            "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
            "0xe9e7cea3dedca5984780bafc599bd69add087d56",  # BUSD
            "0x8d0d000ee44948fc98c9b98a4fa4921476f08b0d",  # USD1
        }
    }

    def _dec(value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0"))
        except (InvalidOperation, ValueError):
            return Decimal(0)

    def _scale(decimals: int | None) -> Decimal:
        try:
            safe_decimals = int(decimals if decimals is not None else 18)
        except (TypeError, ValueError):
            safe_decimals = 18
        return Decimal(10) ** safe_decimals

    def _pct(value: Decimal | None) -> float | None:
        if value is None:
            return None
        return float(value.quantize(Decimal("0.0001")))

    raw_rows: list[dict[str, Any]] = []
    token0 = ""
    token1 = ""
    token0_symbol = None
    token1_symbol = None
    token0_decimals = 18
    token1_decimals = 18
    table_counts: dict[str, int] = {}
    try:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        try:
            for table in ("dex_raw_swap_events", "dex_paircreated_evidence", "dex_transfer_context_evidence"):
                table_counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0) if _table_exists(conn, table) else 0
            if not _table_exists(conn, "dex_raw_swap_events"):
                blockers.append("dex_raw_swap_events_table_missing")
            if _table_exists(conn, "dex_paircreated_evidence") and pool:
                evidence = conn.execute(
                    """
                    SELECT token0, token0_symbol, token1, token1_symbol
                    FROM dex_paircreated_evidence
                    WHERE lower(chain) = ? AND lower(pair_address) = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (clean_chain, pool),
                ).fetchone()
                if evidence:
                    token0 = str(evidence["token0"] or "").strip().lower()
                    token1 = str(evidence["token1"] or "").strip().lower()
                    token0_symbol = evidence["token0_symbol"]
                    token1_symbol = evidence["token1_symbol"]
            if not token0 or not token1:
                blockers.append("pair_tokens_missing_for_outcome")
            metadata_cache = _load_token_metadata_cache(conn)
            token0_meta = _token_metadata_for(clean_chain, token0, metadata_cache) if token0 else {}
            token1_meta = _token_metadata_for(clean_chain, token1, metadata_cache) if token1 else {}
            token0_symbol = token0_symbol or token0_meta.get("symbol")
            token1_symbol = token1_symbol or token1_meta.get("symbol")
            token0_decimals = int(token0_meta.get("decimals") or 18)
            token1_decimals = int(token1_meta.get("decimals") or 18)
            if _table_exists(conn, "dex_raw_swap_events") and pool:
                raw_rows = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT amount0_in, amount1_in, amount0_out, amount1_out,
                               tx_hash, log_index, block_number, block_timestamp,
                               payload_digest, event_dedupe_key
                        FROM dex_raw_swap_events
                        WHERE lower(chain) = ? AND lower(pair_address) = ?
                        ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
                        """,
                        (clean_chain, pool),
                    ).fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        blockers.append(f"local_outcome_query_error:{type(exc).__name__}")

    if len(raw_rows) < 10:
        blockers.append("too_few_local_raw_swaps_for_outcome_min_10")

    target_token = token or (token1 if token1 and token1 not in stable_addresses.get(clean_chain, set()) else token0)
    if target_token not in {token0, token1}:
        blockers.append("target_token_not_in_pair")
    quote_token = token0 if target_token == token1 else token1 if target_token == token0 else ""
    if quote_token and quote_token not in stable_addresses.get(clean_chain, set()):
        blockers.append("quote_token_not_known_stable_local_proxy")

    token0_scale = _scale(token0_decimals)
    token1_scale = _scale(token1_decimals)
    price_points: list[dict[str, Any]] = []
    missing_price_rows = 0
    for row in raw_rows:
        amount0_in = _dec(row.get("amount0_in")) / token0_scale
        amount1_in = _dec(row.get("amount1_in")) / token1_scale
        amount0_out = _dec(row.get("amount0_out")) / token0_scale
        amount1_out = _dec(row.get("amount1_out")) / token1_scale
        price: Decimal | None = None
        quote_volume = Decimal(0)
        side = "unknown"
        if target_token == token1 and quote_token == token0:
            if amount0_in > 0 and amount1_out > 0:
                price = amount0_in / amount1_out
                quote_volume = amount0_in
                side = "buy_target"
            elif amount1_in > 0 and amount0_out > 0:
                price = amount0_out / amount1_in
                quote_volume = amount0_out
                side = "sell_target"
        elif target_token == token0 and quote_token == token1:
            if amount1_in > 0 and amount0_out > 0:
                price = amount1_in / amount0_out
                quote_volume = amount1_in
                side = "buy_target"
            elif amount0_in > 0 and amount1_out > 0:
                price = amount1_out / amount0_in
                quote_volume = amount1_out
                side = "sell_target"
        if price is None or price <= 0:
            missing_price_rows += 1
            continue
        price_points.append({
            "block_number": int(row.get("block_number") or 0),
            "block_timestamp": int(row.get("block_timestamp") or 0),
            "tx_hash": row.get("tx_hash"),
            "log_index": row.get("log_index"),
            "price_quote_per_target": price,
            "quote_volume": quote_volume,
            "side": side,
        })

    if len(price_points) < 10:
        blockers.append("too_few_price_proxy_points_min_10")

    snapshot = None
    windows: list[dict[str, Any]] = []
    if len(price_points) >= 10:
        entry = price_points[9]
        raw_last_price_timestamp = max(int(point["block_timestamp"]) for point in price_points)
        snapshot = {
            "strategy": "first_10_local_raw_swap_price_points",
            "block_number": entry["block_number"],
            "block_timestamp": entry["block_timestamp"],
            "price_quote_per_target": float(entry["price_quote_per_target"]),
            "price_proxy": "quote_token_per_target_token_from_swap_amounts",
            "quote_token": quote_token,
            "target_token": target_token,
            "quote_symbol": token0_symbol if quote_token == token0 else token1_symbol,
            "target_symbol": token1_symbol if target_token == token1 else token0_symbol,
            "source_plan_digest": plan_digest or None,
        }
        window_defs = [
            ("plus_1h", 3600),
            ("plus_6h", 21600),
            ("plus_24h", 86400),
            ("plus_72h", 259200),
        ]
        for label, seconds in window_defs:
            start_ts = int(entry["block_timestamp"])
            end_ts = start_ts + seconds
            points = [point for point in price_points if start_ts <= int(point["block_timestamp"]) <= end_ts]
            if not points:
                windows.append({
                    "window_label": label,
                    "seconds": seconds,
                    "status": "blocked_no_local_price_points",
                    "price_points": 0,
                    "complete": False,
                    "blockers": ["no_local_price_points_in_window"],
                })
                continue
            start_price = points[0]["price_quote_per_target"]
            end_price = points[-1]["price_quote_per_target"]
            high_point = max(points, key=lambda point: point["price_quote_per_target"])
            low_point = min(points, key=lambda point: point["price_quote_per_target"])
            high_price = high_point["price_quote_per_target"]
            low_price = low_point["price_quote_per_target"]
            quote_volume = sum((point["quote_volume"] for point in points), Decimal(0))
            complete = raw_last_price_timestamp >= end_ts
            last_event_gap = max(0, end_ts - int(points[-1]["block_timestamp"]))
            has_activity_near_window_end = last_event_gap <= min(seconds, 3600)
            max_favorable = ((high_price - start_price) / start_price * Decimal(100)) if start_price > 0 else None
            max_adverse = ((low_price - start_price) / start_price * Decimal(100)) if start_price > 0 else None
            net_move = ((end_price - start_price) / start_price * Decimal(100)) if start_price > 0 else None
            window_blockers = []
            if len(points) < 2:
                window_blockers.append("single_price_point_only")
            if not complete:
                window_blockers.append("local_raw_data_does_not_cover_full_window")
            if complete and not has_activity_near_window_end:
                window_blockers.append("stale_end_price_proxy_no_recent_swap_near_window_end")
            windows.append({
                "window_label": label,
                "seconds": seconds,
                "status": "usable_local_proxy" if len(points) >= 2 else "partial_single_point",
                "complete": complete,
                "has_activity_near_window_end": has_activity_near_window_end,
                "last_event_gap_to_window_end_seconds": last_event_gap,
                "price_points": len(points),
                "distinct_tx_hashes": len({point["tx_hash"] for point in points if point.get("tx_hash")}),
                "first_block": points[0]["block_number"],
                "last_block": points[-1]["block_number"],
                "first_timestamp": points[0]["block_timestamp"],
                "last_timestamp": points[-1]["block_timestamp"],
                "price_start": float(start_price),
                "price_high": float(high_price),
                "price_low": float(low_price),
                "price_end": float(end_price),
                "quote_volume": float(quote_volume),
                "max_favorable_move_pct": _pct(max_favorable),
                "max_adverse_move_pct": _pct(max_adverse),
                "net_move_pct": _pct(net_move),
                "time_to_peak_seconds": int(high_point["block_timestamp"]) - start_ts,
                "time_to_peak_blocks": int(high_point["block_number"]) - int(entry["block_number"]),
                "blockers": window_blockers,
            })

    usable_windows = [row for row in windows if row.get("status") == "usable_local_proxy"]
    complete_usable_windows = [row for row in usable_windows if row.get("complete")]
    local_backtestable = bool(snapshot and len(complete_usable_windows) >= 2 and any(row["window_label"] == "plus_24h" for row in complete_usable_windows))
    if not local_backtestable:
        blockers.append("local_outcome_windows_not_backtestable_yet")
    stale_windows = [
        row for row in usable_windows
        if "stale_end_price_proxy_no_recent_swap_near_window_end" in (row.get("blockers") or [])
    ]
    if stale_windows:
        blockers.append("some_outcome_windows_have_stale_end_price_proxy")
    high_quality_backtestable = bool(local_backtestable and not stale_windows)
    timing_assessment = "blocked"
    if local_backtestable:
        first_day = next((row for row in usable_windows if row["window_label"] == "plus_24h"), None)
        first_hour = next((row for row in usable_windows if row["window_label"] == "plus_1h"), None)
        if first_hour and (first_hour.get("max_favorable_move_pct") or 0) > 20:
            timing_assessment = "early_move_visible_in_first_hour_local_proxy"
        elif first_day and (first_day.get("max_favorable_move_pct") or 0) > 20:
            timing_assessment = "move_visible_within_24h_local_proxy"
        else:
            timing_assessment = "outcome_measurable_but_no_large_local_move_threshold"

    return {
        "ok": True,
        "dry_run": True,
        "collection_status": (
            "ready_with_local_outcomes"
            if high_quality_backtestable
            else "partial_with_local_outcomes"
            if local_backtestable
            else "blocked"
        ),
        "chain": clean_chain,
        "pool_address": pool or None,
        "token_address": target_token or token or None,
        "token_symbol": token_symbol or (token1_symbol if target_token == token1 else token0_symbol),
        "quote_token": quote_token or None,
        "quote_symbol": token0_symbol if quote_token == token0 else token1_symbol if quote_token else None,
        "snapshot": snapshot,
        "outcome_windows": windows,
        "external_comparison": external_comparison,
        "local_data_quality": {
            "raw_swap_rows": len(raw_rows),
            "price_proxy_points": len(price_points),
            "missing_price_proxy_rows": missing_price_rows,
            "usable_windows": len(usable_windows),
            "complete_usable_windows": len(complete_usable_windows),
            "raw_first_timestamp": min((int(row.get("block_timestamp") or 0) for row in raw_rows), default=None),
            "raw_last_timestamp": max((int(row.get("block_timestamp") or 0) for row in raw_rows), default=None),
            "table_counts": table_counts,
        },
        "backtest_readiness": {
            "local_outcome_backtestable_now": local_backtestable,
            "high_quality_outcome_backtestable_now": high_quality_backtestable,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
            "timing_assessment": timing_assessment,
            "interpretation": (
                "local outcome proxy is measurable; use it for shadow/backtest only, not as client signal"
                if local_backtestable else "not enough local outcome coverage yet"
            ),
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "persist_outcome_windows_dry_run_first_or_add_negative_controls"
            if local_backtestable
            else "collect_more_outcome_swap_or_sync_windows"
        ),
        "plain_summary_fr": (
            "UFLOKI devient backtestable en local: les swaps raw permettent de mesurer des fenetres outcome "
            "sans ecrire en DB. Ce n'est toujours pas un signal client; il faut comparer avec des controles negatifs."
            if local_backtestable
            else "UFLOKI n'a pas encore assez de fenetres outcome locales pour backtester proprement."
        ),
        **disabled,
    }


def get_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context_dry_run(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_rpc: bool = False,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Read-only Sync/liquidity context checkpoint for UFLOKI outcome quality repair."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    rpc_confirm = "RUN_UFLOKI_OUTCOME_RESERVE_RPC_CHECK"
    source_policy = (
        "admin-only read-only UFLOKI outcome quality repair checkpoint. It reads local Swap outcome windows, "
        "local dex_raw_sync_events and dex_raw_liquidity_events. Historical reserve RPC checks are disabled "
        "unless explicitly confirmed. It creates no rows, mappings, labels, client signals, trades, wallet "
        "orders or opt-ins."
    )
    disabled = {
        "would_call_rpc": False,
        "would_call_external": False,
        "would_insert_outcome_row": False,
        "would_insert_sync_event": False,
        "would_insert_liquidity_event": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "repair_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    outcome = get_manipulation_detection_source_backed_outcome_window_data_collection_dry_run(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        allow_external=False,
        confirm=None,
    )
    pool = str(outcome.get("pool_address") or clean_pool or "").strip().lower()
    token = str(outcome.get("token_address") or clean_token or "").strip().lower()
    snapshot = dict(outcome.get("snapshot") or {})
    source_outcome_blockers = list(outcome.get("blockers") or [])
    outcome_windows = list(outcome.get("outcome_windows") or [])
    blockers = list(dict.fromkeys([
        *([] if outcome.get("collection_status") != "blocked" else ["source_outcome_collection_blocked"]),
        *([] if pool else ["pool_address_missing"]),
        *([] if token else ["token_address_missing"]),
        *([] if snapshot else ["outcome_snapshot_missing"]),
    ]))
    if allow_rpc and confirm != rpc_confirm:
        blockers.append("confirm_RUN_UFLOKI_OUTCOME_RESERVE_RPC_CHECK_required")

    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _to_json_value(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {key: _to_json_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_to_json_value(item) for item in value]
        return value

    def _nearest_sync(rows: list[dict[str, Any]], target_block: int | None) -> dict[str, Any] | None:
        if target_block is None or not rows:
            return None
        return min(
            rows,
            key=lambda row: abs(int(row.get("block_number") or 0) - target_block),
        )

    sync_rows: list[dict[str, Any]] = []
    liquidity_rows: list[dict[str, Any]] = []
    table_status: dict[str, dict[str, Any]] = {}
    try:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        try:
            for table in ("dex_raw_sync_events", "dex_raw_liquidity_events"):
                exists = _table_exists(conn, table)
                count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0) if exists else 0
                table_status[table] = {"exists": exists, "row_count": count}
                if not exists:
                    blockers.append(f"{table}_missing")
            if table_status.get("dex_raw_sync_events", {}).get("exists") and pool:
                sync_rows = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT id, checkpoint_id, chain, pair_address, reserve0, reserve1,
                               tx_hash, log_index, block_number, raw_log_json,
                               payload_digest, event_dedupe_key, status, created_at, source_policy
                        FROM dex_raw_sync_events
                        WHERE lower(chain) = ? AND lower(pair_address) = ?
                        ORDER BY block_number ASC, log_index ASC
                        """,
                        (clean_chain, pool),
                    ).fetchall()
                ]
            if table_status.get("dex_raw_liquidity_events", {}).get("exists") and pool:
                liquidity_rows = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT id, checkpoint_id, chain, pair_address, event_name, sender, recipient,
                               amount0, amount1, tx_hash, log_index, block_number,
                               payload_digest, event_dedupe_key, status, created_at, source_policy
                        FROM dex_raw_liquidity_events
                        WHERE lower(chain) = ? AND lower(pair_address) = ?
                        ORDER BY block_number ASC, log_index ASC
                        """,
                        (clean_chain, pool),
                    ).fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        blockers.append(f"local_sync_liquidity_query_error:{type(exc).__name__}")

    if not sync_rows:
        blockers.append("no_local_sync_reserve_rows_for_pool")
    if not liquidity_rows:
        blockers.append("no_local_liquidity_event_rows_for_pool")

    snapshot_block = _safe_int(snapshot.get("block_number"))
    window_assessments: list[dict[str, Any]] = []
    rpc_snapshots: list[dict[str, Any]] = []
    rpc_calls_performed = 0
    rpc_errors: list[dict[str, Any]] = []
    for window in outcome_windows:
        label = str(window.get("window_label") or "")
        start_block = _safe_int(window.get("first_block") or snapshot_block)
        end_block = _safe_int(window.get("last_block"))
        sync_start = _nearest_sync(sync_rows, start_block)
        sync_end = _nearest_sync(sync_rows, end_block)
        local_reserve_context_available = bool(sync_start and sync_end)
        rpc_start = None
        rpc_end = None
        if allow_rpc and confirm == rpc_confirm and pool and start_block and end_block:
            try:
                rpc_start = _to_json_value(_engine().get_pool_reserve_snapshot(clean_chain, pool, start_block))
                rpc_calls_performed += 1
            except Exception as exc:
                rpc_errors.append({"window_label": label, "target": "start", "error": type(exc).__name__})
            try:
                rpc_end = _to_json_value(_engine().get_pool_reserve_snapshot(clean_chain, pool, end_block))
                rpc_calls_performed += 1
            except Exception as exc:
                rpc_errors.append({"window_label": label, "target": "end", "error": type(exc).__name__})
            if rpc_start or rpc_end:
                rpc_snapshots.append({
                    "window_label": label,
                    "start_block": start_block,
                    "end_block": end_block,
                    "start_snapshot": rpc_start,
                    "end_snapshot": rpc_end,
                })
        needs_repair = bool(window.get("blockers"))
        window_blockers = []
        if needs_repair and not local_reserve_context_available:
            window_blockers.append("sync_reserve_context_needed_for_window")
        if needs_repair and not liquidity_rows:
            window_blockers.append("liquidity_event_context_needed_for_window")
        if allow_rpc and confirm == rpc_confirm and not (rpc_start and rpc_end):
            window_blockers.append("rpc_reserve_snapshot_incomplete_for_window")
        window_assessments.append({
            "window_label": label,
            "window_status": window.get("status"),
            "price_window_complete": window.get("complete"),
            "price_window_blockers": window.get("blockers") or [],
            "needs_quality_repair": needs_repair,
            "start_block": start_block,
            "end_block": end_block,
            "local_sync_start": sync_start,
            "local_sync_end": sync_end,
            "local_reserve_context_available": local_reserve_context_available,
            "local_liquidity_events_in_pool": len(liquidity_rows),
            "repair_blockers": window_blockers,
        })

    stale_or_incomplete_windows = [
        row for row in window_assessments
        if row.get("needs_quality_repair")
    ]
    locally_repairable_windows = [
        row for row in stale_or_incomplete_windows
        if row.get("local_reserve_context_available") and row.get("local_liquidity_events_in_pool")
    ]
    rpc_repair_attempted = bool(allow_rpc and confirm == rpc_confirm)
    rpc_repairable_windows = [
        row for row in rpc_snapshots
        if (row.get("start_snapshot") or {}).get("ok") and (row.get("end_snapshot") or {}).get("ok")
    ]
    can_repair_now = bool(stale_or_incomplete_windows and (
        len(locally_repairable_windows) == len(stale_or_incomplete_windows)
        or (rpc_repair_attempted and len(rpc_repairable_windows) >= len(stale_or_incomplete_windows))
    ))
    if stale_or_incomplete_windows and not can_repair_now:
        blockers.append("outcome_quality_not_repaired_yet")
    if rpc_errors:
        blockers.append("rpc_reserve_snapshot_errors")

    return {
        "ok": True,
        "dry_run": True,
        "repair_status": (
            "repair_context_ready_read_only"
            if can_repair_now
            else "needs_sync_liquidity_collection"
            if stale_or_incomplete_windows
            else "no_repair_needed"
        ),
        "chain": clean_chain,
        "pool_address": pool or None,
        "token_address": token or None,
        "token_symbol": outcome.get("token_symbol"),
        "quote_token": outcome.get("quote_token"),
        "quote_symbol": outcome.get("quote_symbol"),
        "source_outcome_status": outcome.get("collection_status"),
        "source_outcome_blockers": source_outcome_blockers,
        "snapshot": snapshot or None,
        "table_status": table_status,
        "local_context": {
            "sync_rows_for_pool": len(sync_rows),
            "liquidity_rows_for_pool": len(liquidity_rows),
            "sync_first_block": min((_safe_int(row.get("block_number")) or 0 for row in sync_rows), default=None),
            "sync_last_block": max((_safe_int(row.get("block_number")) or 0 for row in sync_rows), default=None),
            "liquidity_event_names": sorted({str(row.get("event_name") or "") for row in liquidity_rows if row.get("event_name")}),
        },
        "window_assessments": window_assessments,
        "rpc_context": {
            "allow_rpc": bool(allow_rpc),
            "called": rpc_repair_attempted,
            "required_confirm": rpc_confirm,
            "rpc_calls_performed": rpc_calls_performed,
            "snapshots": rpc_snapshots,
            "errors": rpc_errors,
            "policy": "historical getReserves calls only; no DB write and no signal/trade decision",
        },
        "quality_readiness": {
            "local_outcome_backtestable_now": bool((outcome.get("backtest_readiness") or {}).get("local_outcome_backtestable_now")),
            "high_quality_outcome_backtestable_now": False,
            "can_repair_stale_windows_now": can_repair_now,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
            "interpretation": (
                "reserve/liquidity context is available for the damaged windows, but still only for shadow analysis"
                if can_repair_now
                else "local outcome prices are measurable, but reserve/liquidity context is missing for quality repair"
            ),
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "rerun_shadow_backtest_with_repaired_outcome_context_read_only"
            if can_repair_now
            else "collect_bounded_sync_and_liquidity_events_for_outcome_windows"
        ),
        "plain_summary_fr": (
            "Les fenetres UFLOKI ont besoin de contexte Sync/liquidite. Les swaps disent ce qui s'est echange, "
            "mais les reserves/liquidite diraient si le prix de fin est fiable ou stale."
        ),
        **{
            **disabled,
            "would_call_rpc": bool(allow_rpc and confirm != rpc_confirm and stale_or_incomplete_windows),
        },
    }


def get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    max_window_blocks: int = 2_000,
) -> dict[str, Any]:
    """Read-only plan for bounded Sync/Mint/Burn collection around damaged UFLOKI outcome windows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_max_window_blocks = max(100, min(int(max_window_blocks or 2_000), 10_000))
    source_policy = (
        "admin-only read-only UFLOKI outcome Sync/liquidity collection plan. It plans bounded Sync, Mint and "
        "Burn contexts around damaged outcome windows only. It performs no provider calls, creates no tables, "
        "persists no events, creates no mappings, emits no client signals, executes no trades and creates no opt-ins."
    )
    disabled = {
        "would_call_rpc": False,
        "would_call_external": False,
        "would_create_table": False,
        "would_insert_sync_event": False,
        "would_insert_liquidity_event": False,
        "would_insert_outcome_row": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    repair = get_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context_dry_run(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        allow_rpc=False,
        confirm=None,
    )
    pool = str(repair.get("pool_address") or clean_pool or "").strip().lower()
    token = str(repair.get("token_address") or clean_token or "").strip().lower()
    snapshot = dict(repair.get("snapshot") or {})
    window_assessments = list(repair.get("window_assessments") or [])
    damaged_windows = [row for row in window_assessments if row.get("needs_quality_repair")]
    blockers = list(dict.fromkeys([
        *([] if repair.get("repair_status") != "blocked" else ["quality_repair_checkpoint_blocked"]),
        *([] if pool else ["pool_address_missing"]),
        *([] if token else ["token_address_missing"]),
        *([] if snapshot else ["outcome_snapshot_missing"]),
        *([] if damaged_windows else ["no_damaged_outcome_windows_to_collect"]),
    ]))

    event_specs = [
        {
            **spec,
            "topic_binding_status": "bound_from_uniswap_v2_generated_bindings",
            "source_reference": "zeta-chain generated UniswapV2Pair Go binding; compatible with Uniswap/Pancake V2 pair ABI",
        }
        for spec in _uniswap_v2_liquidity_event_topics()
    ]
    topic_binding_required = any(not spec.get("topic0") for spec in event_specs)

    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    snapshot_block = _safe_int(snapshot.get("block_number"))
    planned_filters: list[dict[str, Any]] = []
    reserve_rpc_boundary_plan: list[dict[str, Any]] = []
    for row in damaged_windows:
        label = str(row.get("window_label") or "")
        start_block = _safe_int(row.get("start_block")) or snapshot_block
        observed_end_block = _safe_int(row.get("end_block")) or start_block
        seconds = None
        if label == "plus_1h":
            seconds = 3_600
        elif label == "plus_6h":
            seconds = 21_600
        elif label == "plus_24h":
            seconds = 86_400
        elif label == "plus_72h":
            seconds = 259_200
        estimated_end_block = None
        if start_block is not None and seconds is not None:
            # BSC block time varies in local data; keep estimates bounded and only use them for planning.
            estimated_end_block = start_block + max(1, int(seconds / 3))
        target_end_block = estimated_end_block or observed_end_block
        if start_block is None or target_end_block is None:
            blockers.append(f"{label}_block_range_missing")
            continue
        endpoint_blocks = [
            ("window_start", start_block),
            ("observed_last_swap", observed_end_block),
            ("estimated_window_end", target_end_block),
        ]
        for role, block in endpoint_blocks:
            from_block = max(0, int(block) - safe_max_window_blocks // 2)
            to_block = int(block) + safe_max_window_blocks // 2
            for spec in event_specs:
                planned_filters.append({
                    "window_label": label,
                    "filter_role": role,
                    "chain": clean_chain,
                    "pair_address": pool or None,
                    "event_name": spec["event_name"],
                    "event_signature": spec["signature"],
                    "topic0": spec["topic0"],
                    "topic_binding_status": spec["topic_binding_status"],
                    "source_reference": spec["source_reference"],
                    "from_block": from_block,
                    "to_block": to_block,
                    "max_window_blocks": safe_max_window_blocks,
                    "target_table": spec["target_table"],
                    "future_dedupe_key_formula": "chain|event_name|pair_address|tx_hash|log_index",
                    "purpose": spec["purpose"],
                })
        reserve_rpc_boundary_plan.append({
            "window_label": label,
            "chain": clean_chain,
            "pair_address": pool or None,
            "start_block": start_block,
            "observed_last_swap_block": observed_end_block,
            "estimated_window_end_block": target_end_block,
            "method": "eth_call getReserves at historical block",
            "status": "planned_read_only_not_called",
            "purpose": "fallback boundary reserve snapshot if Sync logs remain unavailable",
        })

    if topic_binding_required:
        blockers.append("sync_mint_burn_full_topic0_binding_required_before_lookup")
    if not planned_filters:
        blockers.append("no_sync_liquidity_filters_planned")

    plan_ready = bool(dry_run and planned_filters and pool and token)
    lookup_executable_now = bool(plan_ready and not topic_binding_required)
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if plan_ready else "blocked",
        "chain": clean_chain,
        "pool_address": pool or None,
        "token_address": token or None,
        "token_symbol": repair.get("token_symbol"),
        "source_repair_status": repair.get("repair_status"),
        "source_outcome_status": repair.get("source_outcome_status"),
        "local_context": repair.get("local_context"),
        "damaged_windows": damaged_windows,
        "event_specs": event_specs,
        "planned_filter_count": len(planned_filters),
        "planned_filters": planned_filters[:100],
        "reserve_rpc_boundary_plan": reserve_rpc_boundary_plan,
        "collection_scope": {
            "pool_only": True,
            "events": ["Sync", "Mint", "Burn"],
            "max_window_blocks": safe_max_window_blocks,
            "unbounded_replay": False,
            "provider_calls_now": False,
        },
        "execution_readiness": {
            "lookup_executable_now": lookup_executable_now,
            "topic_binding_required": topic_binding_required,
            "requires_future_confirm": "RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP",
            "requires_no_persistence_first": True,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "bind_full_sync_mint_burn_event_topics_then_run_bounded_lookup_dry_run"
            if plan_ready and topic_binding_required
            else "run_bounded_sync_liquidity_lookup_dry_run"
            if lookup_executable_now
            else "repair_outcome_quality_checkpoint_first"
        ),
        "plain_summary_fr": (
            "Le plan cible seulement les fenetres UFLOKI abimees. Il prepare Sync pour les reserves et Mint/Burn "
            "pour la liquidite, mais aucun lookup ni aucune persistence n'est lance maintenant."
        ),
        **disabled,
    }


def get_manipulation_detection_source_backed_outcome_sync_mint_burn_topic_binding_checkpoint(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only checkpoint that exposes the bound Uniswap/Pancake V2 Sync/Mint/Burn topic0 values."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    source_policy = (
        "admin-only read-only topic binding checkpoint. It verifies the local full topic0 constants used for "
        "Uniswap/Pancake V2 Sync, Mint and Burn outcome context collection. It performs no provider calls, "
        "creates no tables, persists no events, creates no mappings, emits no client signals, executes no trades "
        "and creates no opt-ins."
    )
    disabled = {
        "would_call_rpc": False,
        "would_call_external": False,
        "would_create_table": False,
        "would_insert_sync_event": False,
        "would_insert_liquidity_event": False,
        "would_insert_outcome_row": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "checkpoint_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    event_topics = _uniswap_v2_liquidity_event_topics()
    topic_rows = []
    blockers = []
    for spec in event_topics:
        topic = str(spec.get("topic0") or "")
        valid = topic.startswith("0x") and len(topic) == 66
        if not valid:
            blockers.append(f"{spec.get('event_name')}_topic0_invalid")
        topic_rows.append({
            "event_name": spec["event_name"],
            "signature": spec["signature"],
            "topic0": topic,
            "topic0_valid": valid,
            "target_table": spec["target_table"],
            "source_reference": "zeta-chain generated UniswapV2Pair Go binding",
        })

    collection_plan = get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
    )
    readiness = dict(collection_plan.get("execution_readiness") or {})
    if readiness.get("topic_binding_required"):
        blockers.append("collection_plan_still_requires_topic_binding")
    return {
        "ok": True,
        "dry_run": True,
        "checkpoint_status": "ready" if not blockers else "blocked",
        "chain": clean_chain,
        "pool_address": collection_plan.get("pool_address") or clean_pool or None,
        "token_address": collection_plan.get("token_address") or clean_token or None,
        "token_symbol": collection_plan.get("token_symbol"),
        "event_topics": topic_rows,
        "source_references": [
            {
                "label": "Uniswap/Pancake V2 Pair event signatures",
                "url": "https://docs.quickswap.exchange/technical-reference/smart-contracts/v2/pair",
                "purpose": "confirms V2 Pair emits Mint, Burn, Swap and Sync events",
            },
            {
                "label": "Generated UniswapV2Pair Go binding",
                "url": "https://pkg.go.dev/github.com/zeta-chain/node/pkg/contracts/uniswap/v2-core/contracts/uniswapv2pair.sol",
                "purpose": "confirms full topic0 values for Sync, Mint and Burn",
            },
        ],
        "collection_plan_after_binding": {
            "plan_status": collection_plan.get("plan_status"),
            "planned_filter_count": collection_plan.get("planned_filter_count"),
            "damaged_windows": [row.get("window_label") for row in collection_plan.get("damaged_windows", [])],
            "lookup_executable_now": readiness.get("lookup_executable_now"),
            "topic_binding_required": readiness.get("topic_binding_required"),
            "requires_future_confirm": readiness.get("requires_future_confirm"),
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "run_bounded_sync_liquidity_lookup_dry_run"
            if not blockers and readiness.get("lookup_executable_now")
            else "repair_topic_binding_before_lookup"
        ),
        "plain_summary_fr": (
            "Les topic0 complets Sync, Mint et Burn sont lies pour preparer le lookup borne UFLOKI. "
            "Aucun lookup ni write n'est effectue dans ce checkpoint."
        ),
        **disabled,
    }


def run_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 27,
    max_logs_total: int = 1_000,
    timeout: int = 8,
    max_window_blocks: int = 2_000,
) -> dict[str, Any]:
    """Bounded SQD lookup for UFLOKI Sync/Mint/Burn context; parses logs in memory only."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_calls = max(1, min(int(max_sqd_calls or 27), 50))
    safe_logs_total = max(1, min(int(max_logs_total or 1_000), 5_000))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    safe_window_blocks = max(100, min(int(max_window_blocks or 2_000), 10_000))
    required_confirm = "RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP"
    source_policy = (
        "admin-only bounded read-only UFLOKI Sync/liquidity SQD lookup. It parses Sync, Mint and Burn logs "
        "in memory only. It persists no events, creates no mappings, emits no client signals, executes no trades "
        "and creates no opt-ins."
    )
    disabled = {
        "would_persist_sync_event": False,
        "would_persist_liquidity_event": False,
        "would_insert_outcome_row": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            **disabled,
        }

    plan = get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        max_window_blocks=safe_window_blocks,
    )
    readiness = dict(plan.get("execution_readiness") or {})
    planned_filters = list(plan.get("planned_filters") or [])
    blockers = list(plan.get("blockers") or [])
    if plan.get("plan_status") != "ready_but_disabled":
        blockers.append("collection_plan_not_ready")
    if not readiness.get("lookup_executable_now"):
        blockers.append("lookup_not_executable_now")
    if not planned_filters:
        blockers.append("no_planned_filters")
    if blockers:
        return {
            "ok": True,
            "dry_run": True,
            "lookup_status": "blocked",
            "chain": clean_chain,
            "pool_address": plan.get("pool_address") or clean_pool or None,
            "token_address": plan.get("token_address") or clean_token or None,
            "token_symbol": plan.get("token_symbol"),
            "planned_filter_count": len(planned_filters),
            "selected_filter_count": 0,
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "window_counts": {},
            "parsed_previews": [],
            "blockers": list(dict.fromkeys(blockers)),
            "can_repair_outcome_quality_now": False,
            "can_detect_reliable_manipulation_now": False,
            **disabled,
        }
    selected_filters = planned_filters[:safe_calls]
    if not allow_external:
        return {
            "ok": True,
            "dry_run": True,
            "lookup_status": "ready_but_external_disabled",
            "chain": clean_chain,
            "pool_address": plan.get("pool_address") or clean_pool or None,
            "token_address": plan.get("token_address") or clean_token or None,
            "token_symbol": plan.get("token_symbol"),
            "planned_filter_count": len(planned_filters),
            "selected_filter_count": len(selected_filters),
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "window_counts": {},
            "parsed_previews": [],
            "required_confirm": required_confirm,
            "blockers": ["external_lookup_disabled_until_confirmed"],
            "can_repair_outcome_quality_now": False,
            "can_detect_reliable_manipulation_now": False,
            "would_call_external": True,
            **disabled,
        }
    if confirm != required_confirm:
        return {
            "ok": False,
            "dry_run": True,
            "lookup_status": "blocked",
            "chain": clean_chain,
            "pool_address": plan.get("pool_address") or clean_pool or None,
            "token_address": plan.get("token_address") or clean_token or None,
            "token_symbol": plan.get("token_symbol"),
            "planned_filter_count": len(planned_filters),
            "selected_filter_count": len(selected_filters),
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "window_counts": {},
            "parsed_previews": [],
            "required_confirm": required_confirm,
            "blockers": ["confirm_required_for_external_read_only_lookup"],
            "can_repair_outcome_quality_now": False,
            "can_detect_reliable_manipulation_now": False,
            "would_call_external": True,
            **disabled,
        }

    def _increment(counter: dict[str, int], key: Any, amount: int = 1) -> None:
        label = str(key or "unknown")
        counter[label] = counter.get(label, 0) + amount

    def _topic_address(topics: Any, index: int) -> str | None:
        if not isinstance(topics, list) or len(topics) <= index:
            return None
        raw = str(topics[index] or "").lower()
        if raw.startswith("0x") and len(raw) >= 42:
            return "0x" + raw[-40:]
        return None

    def _log_int(value: Any) -> int | None:
        try:
            if isinstance(value, str) and value.startswith("0x"):
                return int(value, 16)
            return int(value)
        except (TypeError, ValueError):
            return None

    def _preview_log(row_filter: dict[str, Any], log: dict[str, Any]) -> dict[str, Any]:
        event_name = str(row_filter.get("event_name") or "unknown")
        words = _decode_uint_words(log.get("data"), 2)
        topics = log.get("topics") if isinstance(log.get("topics"), list) else []
        preview = {
            "window_label": row_filter.get("window_label"),
            "filter_role": row_filter.get("filter_role"),
            "event_name": event_name,
            "chain": row_filter.get("chain"),
            "pair_address": str(log.get("address") or row_filter.get("pair_address") or "").lower(),
            "block_number": _log_int(log.get("blockNumber")),
            "block_timestamp": _log_int(log.get("timestamp")),
            "tx_hash": log.get("transactionHash"),
            "log_index": _log_int(log.get("logIndex")),
            "topic0": topics[0] if topics else row_filter.get("topic0"),
            "event_dedupe_key": (
                f"{row_filter.get('chain')}|{event_name}|"
                f"{str(log.get('address') or row_filter.get('pair_address') or '').lower()}|"
                f"{log.get('transactionHash')}|{_log_int(log.get('logIndex'))}"
            ),
            "would_persist": False,
        }
        if event_name == "Sync":
            preview["reserve0"] = words[0] if len(words) >= 1 else None
            preview["reserve1"] = words[1] if len(words) >= 2 else None
        elif event_name in {"Mint", "Burn"}:
            preview["sender"] = _topic_address(topics, 1)
            preview["amount0"] = words[0] if len(words) >= 1 else None
            preview["amount1"] = words[1] if len(words) >= 2 else None
            if event_name == "Burn":
                preview["to"] = _topic_address(topics, 2)
        return preview

    event_counts: dict[str, int] = {}
    window_counts: dict[str, int] = {}
    endpoint_statuses: list[dict[str, Any]] = []
    parsed_previews: list[dict[str, Any]] = []
    total_logs_seen = 0
    calls = 0
    errors: list[str] = []
    sync_windows_seen: set[str] = set()
    for row_filter in selected_filters:
        if calls >= safe_calls or total_logs_seen >= safe_logs_total:
            break
        log_filter = {
            "address": row_filter.get("pair_address"),
            "fromBlock": hex(int(row_filter.get("from_block") or 0)),
            "toBlock": hex(int(row_filter.get("to_block") or 0)),
            "topics": [row_filter.get("topic0")],
        }
        logs, endpoint, error, key_source, request_preview = _engine()._sqd_portal_event_logs(
            clean_chain,
            log_filter,
            timeout=safe_timeout,
        )
        calls += 1
        endpoint_statuses.append({
            "window_label": row_filter.get("window_label"),
            "filter_role": row_filter.get("filter_role"),
            "event_name": row_filter.get("event_name"),
            "from_block": row_filter.get("from_block"),
            "to_block": row_filter.get("to_block"),
            "endpoint": endpoint,
            "api_key_source": key_source,
            "api_key_configured": bool((request_preview or {}).get("api_key_configured")),
            "log_count": len(logs),
            "error": error,
        })
        if error:
            errors.append(str(error))
            continue
        for log in logs:
            if total_logs_seen >= safe_logs_total:
                break
            total_logs_seen += 1
            _increment(event_counts, row_filter.get("event_name"))
            _increment(window_counts, row_filter.get("window_label"))
            if row_filter.get("event_name") == "Sync":
                words = _decode_uint_words(log.get("data"), 2)
                if len(words) >= 2:
                    sync_windows_seen.add(str(row_filter.get("window_label") or "unknown"))
            if len(parsed_previews) < clean_limit:
                parsed_previews.append(_preview_log(row_filter, log))

    damaged_window_labels = {str(row.get("window_label")) for row in plan.get("damaged_windows", [])}
    liquidity_events_seen = event_counts.get("Mint", 0) + event_counts.get("Burn", 0)
    all_damaged_windows_have_sync_context = bool(damaged_window_labels) and damaged_window_labels.issubset(sync_windows_seen)
    can_repair_candidate = bool(all_damaged_windows_have_sync_context and liquidity_events_seen > 0)
    lookup_status = (
        "completed_with_candidate_repair_context_no_persistence"
        if can_repair_candidate
        else "completed_with_partial_context_no_persistence"
        if total_logs_seen
        else "completed_no_events_no_persistence"
    )
    if errors and not total_logs_seen:
        lookup_status = "completed_with_errors_no_persistence"
    return {
        "ok": True,
        "dry_run": True,
        "lookup_status": lookup_status,
        "chain": clean_chain,
        "pool_address": plan.get("pool_address") or clean_pool or None,
        "token_address": plan.get("token_address") or clean_token or None,
        "token_symbol": plan.get("token_symbol"),
        "planned_filter_count": len(planned_filters),
        "selected_filter_count": len(selected_filters),
        "external_calls_performed": calls,
        "total_logs_seen": total_logs_seen,
        "event_counts": event_counts,
        "window_counts": window_counts,
        "endpoint_statuses": endpoint_statuses,
        "parsed_preview_count": len(parsed_previews),
        "parsed_previews": parsed_previews,
        "damaged_windows": list(damaged_window_labels),
        "sync_windows_with_context": sorted(sync_windows_seen),
        "liquidity_events_seen": liquidity_events_seen,
        "can_repair_outcome_quality_now": can_repair_candidate,
        "can_detect_reliable_manipulation_now": False,
        "blockers": (
            []
            if can_repair_candidate
            else ["sync_or_liquidity_context_still_incomplete_for_outcome_repair"]
            if total_logs_seen
            else ["no_sync_liquidity_logs_found_in_bounded_lookup"]
        ),
        "errors": list(dict.fromkeys(errors))[:10],
        "would_call_external": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    max_window_blocks: int = 2_000,
) -> dict[str, Any]:
    """Read-only schema-plan for future UFLOKI Sync/Mint/Burn evidence-only persistence."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_window_blocks = max(100, min(int(max_window_blocks or 2_000), 10_000))
    target_tables = ["dex_raw_sync_events", "dex_raw_liquidity_events"]
    source_policy = (
        "admin-only read-only UFLOKI Sync/liquidity evidence schema-plan. It selects the existing local DEX "
        "event-reader raw Sync and liquidity table shapes for future evidence-only persistence. It creates no "
        "tables, inserts no events, persists no evidence, creates no mappings, emits no client signals, executes "
        "no trades and creates no opt-ins."
    )
    disabled = {
        "would_call_external": False,
        "would_create_table": False,
        "would_insert_sync_event": False,
        "would_insert_liquidity_event": False,
        "would_persist_sync_event": False,
        "would_persist_liquidity_event": False,
        "would_insert_outcome_row": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "chain": clean_chain,
            "target_tables": target_tables,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    collection_plan = get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        max_window_blocks=safe_window_blocks,
    )
    lookup_preview = run_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        allow_external=False,
        confirm=None,
        max_sqd_calls=27,
        max_logs_total=1_000,
        timeout=8,
        max_window_blocks=safe_window_blocks,
    )
    raw_schema_plan = _engine().get_dex_local_event_reader_checkpoint_raw_schema_plan(
        chain=clean_chain,
        factory_address=None,
        dry_run=True,
    )
    raw_table_plans = dict(raw_schema_plan.get("table_plans") or {})
    selected_table_plans = {
        table: raw_table_plans.get(table)
        for table in target_tables
        if isinstance(raw_table_plans.get(table), dict)
    }
    missing_table_plans = [table for table in target_tables if table not in selected_table_plans]
    damaged_windows = [
        str(row.get("window_label") or "")
        for row in collection_plan.get("damaged_windows", [])
        if row.get("window_label")
    ]
    execution_readiness = dict(collection_plan.get("execution_readiness") or {})
    blockers = list(dict.fromkeys([
        *(collection_plan.get("blockers") or []),
        *(raw_schema_plan.get("blockers") or []),
        *([] if collection_plan.get("plan_status") == "ready_but_disabled" else ["sync_liquidity_collection_plan_not_ready"]),
        *([] if execution_readiness.get("lookup_executable_now") else ["sync_liquidity_lookup_not_executable"]),
        *([] if raw_schema_plan.get("plan_status") == "ready_read_only" else ["dex_local_event_reader_raw_schema_plan_not_ready"]),
        *[f"{table}_schema_plan_missing" for table in missing_table_plans],
    ]))
    tables_existing_now = sum(1 for spec in selected_table_plans.values() if spec.get("table_exists"))
    migrations_required = sum(1 for spec in selected_table_plans.values() if spec.get("migration_required"))
    sync_dedupe = "chain|Sync|pair_address|tx_hash|log_index"
    liquidity_dedupe = "chain|event_name|pair_address|tx_hash|log_index"
    plan_ready = not blockers and len(selected_table_plans) == len(target_tables)
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if plan_ready else "blocked",
        "chain": clean_chain,
        "pool_address": collection_plan.get("pool_address") or clean_pool or None,
        "token_address": collection_plan.get("token_address") or clean_token or None,
        "token_symbol": collection_plan.get("token_symbol"),
        "source_lookup": {
            "source_name": "SQD Portal",
            "lookup_endpoint": "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-lookup-dry-run",
            "lookup_status": lookup_preview.get("lookup_status"),
            "planned_filter_count": lookup_preview.get("planned_filter_count"),
            "selected_filter_count": lookup_preview.get("selected_filter_count"),
            "external_calls_performed": lookup_preview.get("external_calls_performed"),
            "required_confirm_for_future_lookup": "RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP",
            "last_live_lookup_not_persisted": True,
        },
        "target_tables": target_tables,
        "table_plans": selected_table_plans,
        "schema_preview": {
            table: spec.get("schema_preview")
            for table, spec in selected_table_plans.items()
        },
        "indexes_preview": {
            table: spec.get("indexes_preview")
            for table, spec in selected_table_plans.items()
        },
        "constraints_preview": {
            "eligible_events": ["Sync", "Mint", "Burn"],
            "eligible_windows": damaged_windows,
            "source": ["SQD Portal bounded lookup", "local DEX event-reader schema"],
            "guards": [
                "dry_run_required_for_schema_plan",
                "future_insert_requires_fresh_bounded_lookup",
                "future_insert_requires_payload_digest",
                "future_insert_requires_event_dedupe_key",
                "duplicate_future_insert_blocks",
                "no_overwrite",
                "no_upsert",
                "no_mapping",
                "no_client_signal",
                "no_trade",
                "no_opt_in",
            ],
        },
        "dedupe_constraints": {
            "dex_raw_sync_events": {
                "event_dedupe_key_formula": sync_dedupe,
                "duplicate_future_insert": "block",
                "overwrite": "blocked",
                "upsert": "blocked",
                "silent_success": "blocked",
            },
            "dex_raw_liquidity_events": {
                "event_dedupe_key_formula": liquidity_dedupe,
                "duplicate_future_insert": "block",
                "overwrite": "blocked",
                "upsert": "blocked",
                "silent_success": "blocked",
            },
        },
        "summary": {
            "target_table_count": len(target_tables),
            "tables_existing_now": tables_existing_now,
            "migrations_required": migrations_required,
            "events_supported": ["Sync", "Mint", "Burn"],
            "source_backed_scoring_ready": False,
            "mapping_ready_now": 0,
            "client_ready_signals": 0,
            "trade_ready": 0,
            "can_detect_reliable_manipulation_now": False,
        },
        "migration_required": bool(migrations_required),
        "confirm_required": "CREATE_DEX_LOCAL_EVENT_READER_CHECKPOINT_RAW_TABLES" if migrations_required else None,
        "blockers": blockers,
        "next_safe_step": (
            "confirmed_empty_ddl_migration_for_event_reader_raw_tables"
            if plan_ready and migrations_required
            else "ufloki_sync_liquidity_evidence_insert_dry_run_first"
            if plan_ready
            else "repair_sync_liquidity_schema_plan_blockers"
        ),
        "plain_summary_fr": (
            "Les logs Sync/Mint UFLOKI sont recuperables, mais cette etape ne cree aucune preuve. "
            "Elle prepare seulement ou reutilise les boites raw evidence-only qui pourront stocker les reserves "
            "et la liquidite plus tard."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def insert_manipulation_detection_source_backed_outcome_sync_liquidity_evidence(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_external: bool = False,
    lookup_confirm: str | None = None,
    confirm: str | None = None,
    expected_lookup_digest: str | None = None,
    max_sqd_calls: int = 27,
    max_logs_total: int = 1_000,
    timeout: int = 8,
    max_window_blocks: int = 2_000,
) -> dict[str, Any]:
    """Dry-run-first insert lane for UFLOKI Sync/Mint/Burn evidence-only rows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_calls = max(1, min(int(max_sqd_calls or 27), 50))
    safe_logs_total = max(1, min(int(max_logs_total or 1_000), 5_000))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    safe_window_blocks = max(100, min(int(max_window_blocks or 2_000), 10_000))
    lookup_confirm_token = "RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP"
    insert_confirm_token = "INSERT_UFLOKI_SYNC_LIQUIDITY_EVIDENCE"
    source_policy = (
        "admin-only dry-run-first UFLOKI Sync/liquidity evidence insert lane. It may perform a bounded SQD "
        "lookup when explicitly confirmed, then prepares raw evidence-only rows for dex_raw_sync_events and "
        "dex_raw_liquidity_events. It creates no mappings, emits no client signals, executes no trades and "
        "creates no opt-ins."
    )
    disabled = {
        "would_create_table": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_policy": source_policy,
    }

    schema_plan = get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        max_window_blocks=safe_window_blocks,
    )
    blockers = list(schema_plan.get("blockers") or [])
    if schema_plan.get("plan_status") != "ready_but_disabled":
        blockers.append("sync_liquidity_evidence_schema_plan_not_ready")
    if not allow_external:
        blockers.append("external_lookup_required_for_insert_preview")
    if allow_external and lookup_confirm != lookup_confirm_token:
        blockers.append("lookup_confirm_RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP_required")
    if not dry_run:
        if confirm != insert_confirm_token:
            blockers.append("confirm_INSERT_UFLOKI_SYNC_LIQUIDITY_EVIDENCE_required")
        if not expected_lookup_digest:
            blockers.append("expected_lookup_digest_required")

    planned_filters: list[dict[str, Any]] = []
    lookup_errors: list[str] = []
    endpoint_statuses: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    duplicate_keys: set[str] = set()
    if allow_external and lookup_confirm == lookup_confirm_token and not [
        blocker for blocker in blockers if blocker not in {"confirm_INSERT_UFLOKI_SYNC_LIQUIDITY_EVIDENCE_required", "expected_lookup_digest_required"}
    ]:
        collection_plan = get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan(
            chain=clean_chain,
            pool_address=clean_pool or None,
            token_address=clean_token or None,
            limit=clean_limit,
            dry_run=True,
            max_window_blocks=safe_window_blocks,
        )
        planned_filters = list(collection_plan.get("planned_filters") or [])[:safe_calls]
        total_logs_seen = 0
        for row_filter in planned_filters:
            if total_logs_seen >= safe_logs_total:
                break
            log_filter = {
                "address": row_filter.get("pair_address"),
                "fromBlock": hex(int(row_filter.get("from_block") or 0)),
                "toBlock": hex(int(row_filter.get("to_block") or 0)),
                "topics": [row_filter.get("topic0")],
            }
            logs, endpoint, error, key_source, request_preview = _engine()._sqd_portal_event_logs(
                clean_chain,
                log_filter,
                timeout=safe_timeout,
            )
            endpoint_statuses.append({
                "window_label": row_filter.get("window_label"),
                "filter_role": row_filter.get("filter_role"),
                "event_name": row_filter.get("event_name"),
                "from_block": row_filter.get("from_block"),
                "to_block": row_filter.get("to_block"),
                "endpoint": endpoint,
                "api_key_source": key_source,
                "api_key_configured": bool((request_preview or {}).get("api_key_configured")),
                "log_count": len(logs),
                "error": error,
            })
            if error:
                lookup_errors.append(str(error))
                continue
            for log in logs:
                if total_logs_seen >= safe_logs_total:
                    break
                total_logs_seen += 1
                row = _build_sync_liquidity_event_row(row_filter, log)
                key = str(row.get("event_dedupe_key") or "")
                if key in duplicate_keys:
                    row["row_status"] = "blocked"
                    row.setdefault("row_blockers", []).append("duplicate_within_lookup")
                duplicate_keys.add(key)
                candidate_rows.append(row)
    elif not planned_filters:
        total_logs_seen = 0
    else:
        total_logs_seen = 0

    eligible_rows = [row for row in candidate_rows if row.get("row_status") == "eligible"]
    sync_rows = [row for row in eligible_rows if row.get("target_table") == "dex_raw_sync_events"]
    liquidity_rows = [row for row in eligible_rows if row.get("target_table") == "dex_raw_liquidity_events"]
    lookup_digest_payload = [
        {
            "target_table": row.get("target_table"),
            "event_dedupe_key": row.get("event_dedupe_key"),
            "payload_digest": row.get("payload_digest"),
        }
        for row in eligible_rows
    ]
    lookup_digest = _sync_liquidity_payload_digest(lookup_digest_payload)
    existing_duplicate_keys: set[str] = set()
    table_counts_before: dict[str, int | None] = {}
    conn = _get_db()
    try:
        for table in ("dex_raw_sync_events", "dex_raw_liquidity_events"):
            if not _table_exists(conn, table):
                blockers.append(f"{table}_missing")
                table_counts_before[table] = None
                continue
            table_counts_before[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        for table, rows in (("dex_raw_sync_events", sync_rows), ("dex_raw_liquidity_events", liquidity_rows)):
            if not rows or table_counts_before.get(table) is None:
                continue
            placeholders = ",".join("?" for _ in rows)
            keys = [row["event_dedupe_key"] for row in rows]
            for (existing_key,) in conn.execute(
                f"SELECT event_dedupe_key FROM {table} WHERE event_dedupe_key IN ({placeholders})",
                keys,
            ).fetchall():
                existing_duplicate_keys.add(str(existing_key))
    finally:
        conn.close()
    duplicate_existing_count = len(existing_duplicate_keys)
    insertable_rows = [row for row in eligible_rows if row.get("event_dedupe_key") not in existing_duplicate_keys]
    insertable_sync_rows = [row for row in insertable_rows if row.get("target_table") == "dex_raw_sync_events"]
    insertable_liquidity_rows = [row for row in insertable_rows if row.get("target_table") == "dex_raw_liquidity_events"]
    duplicate_within_lookup_count = sum(
        1 for row in candidate_rows if "duplicate_within_lookup" in (row.get("row_blockers") or [])
    )
    blocked_candidate_rows = len([row for row in candidate_rows if row.get("row_status") != "eligible"])
    if allow_external and lookup_confirm == lookup_confirm_token and not candidate_rows:
        blockers.append("no_sync_liquidity_rows_from_lookup")
    if lookup_errors and not candidate_rows:
        blockers.append("sync_liquidity_lookup_failed")
    if eligible_rows and not insertable_rows and duplicate_existing_count:
        blockers.append("duplicate_sync_liquidity_evidence_exists")
    if not dry_run and lookup_digest != str(expected_lookup_digest or ""):
        blockers.append("expected_lookup_digest_mismatch")

    dry_run_status = "ready_for_insert" if insertable_rows and not [b for b in blockers if b not in {"confirm_INSERT_UFLOKI_SYNC_LIQUIDITY_EVIDENCE_required", "expected_lookup_digest_required"}] else "blocked"
    if dry_run:
        return {
            "ok": dry_run_status != "blocked",
            "dry_run": True,
            "insert_status": dry_run_status,
            "chain": clean_chain,
            "pool_address": schema_plan.get("pool_address") or clean_pool or None,
            "token_address": schema_plan.get("token_address") or clean_token or None,
            "token_symbol": schema_plan.get("token_symbol"),
            "target_tables": ["dex_raw_sync_events", "dex_raw_liquidity_events"],
            "schema_plan_status": schema_plan.get("plan_status"),
            "lookup_digest": lookup_digest,
            "expected_lookup_digest_required_for_real_insert": lookup_digest,
            "planned_filter_count": len(planned_filters) or schema_plan.get("source_lookup", {}).get("planned_filter_count"),
            "external_calls_performed": len(endpoint_statuses),
            "total_logs_seen": total_logs_seen,
            "candidate_rows": len(candidate_rows),
            "eligible_rows": len(eligible_rows),
            "blocked_candidate_rows": blocked_candidate_rows,
            "duplicate_within_lookup_count": duplicate_within_lookup_count,
            "duplicate_existing_count": duplicate_existing_count,
            "would_insert_sync_events": len(insertable_sync_rows),
            "would_insert_liquidity_events": len(insertable_liquidity_rows),
            "would_persist_sync_event": bool(insertable_sync_rows),
            "would_persist_liquidity_event": bool(insertable_liquidity_rows),
            "inserted_sync_events": 0,
            "inserted_liquidity_events": 0,
            "inserted": False,
            "preview_rows": [
                {
                    "target_table": row.get("target_table"),
                    "event_name": row.get("event_name"),
                    "window_label": row.get("window_label"),
                    "block_number": row.get("block_number"),
                    "tx_hash": row.get("tx_hash"),
                    "log_index": row.get("log_index"),
                    "event_dedupe_key": row.get("event_dedupe_key"),
                    "payload_digest": row.get("payload_digest"),
                    "row_status": "duplicate_existing" if row.get("event_dedupe_key") in existing_duplicate_keys else row.get("row_status"),
                    "row_blockers": row.get("row_blockers"),
                }
                for row in candidate_rows[:clean_limit]
            ],
            "endpoint_statuses": endpoint_statuses[:10],
            "lookup_errors": list(dict.fromkeys(lookup_errors))[:10],
            "table_counts_before": table_counts_before,
            "blockers": list(dict.fromkeys(blockers)),
            "can_detect_reliable_manipulation_now": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            **disabled,
        }

    blockers = list(dict.fromkeys(blockers))
    if blockers:
        return {
            "ok": False,
            "dry_run": False,
            "insert_status": "blocked",
            "chain": clean_chain,
            "pool_address": schema_plan.get("pool_address") or clean_pool or None,
            "token_address": schema_plan.get("token_address") or clean_token or None,
            "token_symbol": schema_plan.get("token_symbol"),
            "lookup_digest": lookup_digest,
            "expected_lookup_digest": expected_lookup_digest,
            "candidate_rows": len(candidate_rows),
            "eligible_rows": len(eligible_rows),
            "blocked_candidate_rows": blocked_candidate_rows,
            "duplicate_within_lookup_count": duplicate_within_lookup_count,
            "duplicate_existing_count": duplicate_existing_count,
            "inserted_sync_events": 0,
            "inserted_liquidity_events": 0,
            "inserted": False,
            "blockers": blockers,
            "can_detect_reliable_manipulation_now": False,
            "would_persist_sync_event": False,
            "would_persist_liquidity_event": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            **disabled,
        }

    created_at = datetime.now(timezone.utc).isoformat()
    sync_columns = [
        "checkpoint_id", "chain", "pair_address", "reserve0", "reserve1", "tx_hash", "log_index",
        "block_number", "raw_log_json", "payload_digest", "event_dedupe_key", "status", "created_at", "source_policy",
    ]
    liquidity_columns = [
        "checkpoint_id", "chain", "pair_address", "event_name", "sender", "recipient", "amount0", "amount1",
        "tx_hash", "log_index", "block_number", "raw_log_json", "payload_digest", "event_dedupe_key",
        "status", "created_at", "source_policy",
    ]

    def _values(row: dict[str, Any], columns: list[str]) -> tuple[Any, ...]:
        insert_values = dict(row.get("insert_values") or {})
        insert_values["created_at"] = created_at
        insert_values["source_policy"] = source_policy
        return tuple(insert_values.get(column) for column in columns)

    conn = _get_db()
    inserted_sync = 0
    inserted_liquidity = 0
    try:
        if insertable_sync_rows:
            placeholders = ",".join("?" for _ in sync_columns)
            conn.executemany(
                f"INSERT INTO dex_raw_sync_events ({','.join(sync_columns)}) VALUES ({placeholders})",
                [_values(row, sync_columns) for row in insertable_sync_rows],
            )
            inserted_sync = len(insertable_sync_rows)
        if insertable_liquidity_rows:
            placeholders = ",".join("?" for _ in liquidity_columns)
            conn.executemany(
                f"INSERT INTO dex_raw_liquidity_events ({','.join(liquidity_columns)}) VALUES ({placeholders})",
                [_values(row, liquidity_columns) for row in insertable_liquidity_rows],
            )
            inserted_liquidity = len(insertable_liquidity_rows)
        conn.commit()
        table_counts_after = {
            "dex_raw_sync_events": int(conn.execute("SELECT COUNT(*) FROM dex_raw_sync_events").fetchone()[0] or 0),
            "dex_raw_liquidity_events": int(conn.execute("SELECT COUNT(*) FROM dex_raw_liquidity_events").fetchone()[0] or 0),
        }
    finally:
        conn.close()
    writes = inserted_sync + inserted_liquidity
    return {
        "ok": True,
        "dry_run": False,
        "insert_status": "inserted" if writes else "blocked",
        "chain": clean_chain,
        "pool_address": schema_plan.get("pool_address") or clean_pool or None,
        "token_address": schema_plan.get("token_address") or clean_token or None,
        "token_symbol": schema_plan.get("token_symbol"),
        "lookup_digest": lookup_digest,
        "candidate_rows": len(candidate_rows),
        "eligible_rows": len(eligible_rows),
        "blocked_candidate_rows": blocked_candidate_rows,
        "duplicate_within_lookup_count": duplicate_within_lookup_count,
        "duplicate_existing_count": duplicate_existing_count,
        "inserted_sync_events": inserted_sync,
        "inserted_liquidity_events": inserted_liquidity,
        "inserted": bool(writes),
        "table_counts_before": table_counts_before,
        "table_counts_after": table_counts_after,
        "blockers": [],
        "can_detect_reliable_manipulation_now": False,
        "would_persist_sync_event": False,
        "would_persist_liquidity_event": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": writes,
        **disabled,
    }


def get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review_queue(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    status: str | None = "raw_observed",
    limit: int = 50,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only review queue for persisted UFLOKI Sync/Mint/Burn evidence-only rows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_status = str(status or "").strip()
    clean_limit = max(1, min(int(limit or 50), 100))
    source_policy = (
        "admin-only read-only UFLOKI Sync/liquidity evidence review queue. It validates local raw Sync/Mint/Burn "
        "rows against payload digests, source markers, dedupe keys, pool route and repair bridge readiness. It "
        "does not update status, create mappings, emit client signals, execute trades or create opt-ins."
    )
    disabled = {
        "would_update_status": False,
        "would_insert_outcome_row": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "queue_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    repair = get_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context_dry_run(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        allow_rpc=False,
        confirm=None,
    )
    pool = str(repair.get("pool_address") or clean_pool or "").strip().lower()
    token = str(repair.get("token_address") or clean_token or "").strip().lower()
    blockers = list(repair.get("blockers") or [])
    if not pool:
        blockers.append("pool_address_missing")

    table_status: dict[str, dict[str, Any]] = {}
    sync_rows: list[dict[str, Any]] = []
    liquidity_rows: list[dict[str, Any]] = []

    def _row_payload(row: dict[str, Any]) -> dict[str, Any] | None:
        try:
            payload = json.loads(str(row.get("raw_log_json") or ""))
            return payload if isinstance(payload, dict) else None
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def _row_bound_status(row: dict[str, Any], expected_event_name: str | None = None) -> dict[str, Any]:
        payload = _row_payload(row)
        payload_digest_bound = bool(payload) and _sync_liquidity_payload_digest(payload) == str(row.get("payload_digest") or "")
        source_bound = bool(payload) and str(payload.get("source") or "") == "SQD Portal"
        event_name = expected_event_name or str(row.get("event_name") or "")
        payload_event_name = str((payload or {}).get("event_name") or "")
        event_name_bound = bool(event_name) and payload_event_name == event_name
        pool_bound = str(row.get("pair_address") or "").strip().lower() == pool
        dedupe_expected = (
            f"{clean_chain}|{event_name}|{str(row.get('pair_address') or '').strip().lower()}|"
            f"{str(row.get('tx_hash') or '').strip().lower()}|{row.get('log_index')}"
        )
        dedupe_bound = str(row.get("event_dedupe_key") or "") == dedupe_expected
        return {
            "payload_json_valid": bool(payload),
            "payload_digest_bound": payload_digest_bound,
            "source_bound": source_bound,
            "event_name_bound": event_name_bound,
            "pool_bound": pool_bound,
            "dedupe_bound": dedupe_bound,
            "review_blockers": [
                *([] if payload else ["raw_log_json_invalid"]),
                *([] if payload_digest_bound else ["payload_digest_drift"]),
                *([] if source_bound else ["source_marker_missing_or_drift"]),
                *([] if event_name_bound else ["event_name_drift"]),
                *([] if pool_bound else ["pool_route_drift"]),
                *([] if dedupe_bound else ["event_dedupe_key_drift"]),
            ],
        }

    try:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        try:
            for table in ("dex_raw_sync_events", "dex_raw_liquidity_events"):
                exists = _table_exists(conn, table)
                row_count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0) if exists else 0
                duplicate_count = 0
                if exists:
                    duplicate_count = int(conn.execute(
                        f"""
                        SELECT COUNT(*) FROM (
                            SELECT event_dedupe_key
                            FROM {table}
                            GROUP BY event_dedupe_key
                            HAVING COUNT(*) > 1
                        )
                        """
                    ).fetchone()[0] or 0)
                table_status[table] = {
                    "exists": exists,
                    "row_count": row_count,
                    "duplicate_event_dedupe_keys": duplicate_count,
                }
                if not exists:
                    blockers.append(f"{table}_missing")
            if table_status.get("dex_raw_sync_events", {}).get("exists") and pool:
                params: list[Any] = [clean_chain, pool]
                status_sql = ""
                if clean_status:
                    status_sql = "AND status = ?"
                    params.append(clean_status)
                sync_rows = [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT id, checkpoint_id, chain, pair_address, reserve0, reserve1,
                               tx_hash, log_index, block_number, raw_log_json,
                               payload_digest, event_dedupe_key, status, created_at, source_policy
                        FROM dex_raw_sync_events
                        WHERE lower(chain) = ? AND lower(pair_address) = ?
                        {status_sql}
                        ORDER BY block_number ASC, log_index ASC
                        """,
                        tuple(params),
                    ).fetchall()
                ]
            if table_status.get("dex_raw_liquidity_events", {}).get("exists") and pool:
                params = [clean_chain, pool]
                status_sql = ""
                if clean_status:
                    status_sql = "AND status = ?"
                    params.append(clean_status)
                liquidity_rows = [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT id, checkpoint_id, chain, pair_address, event_name, sender, recipient,
                               amount0, amount1, tx_hash, log_index, block_number, raw_log_json,
                               payload_digest, event_dedupe_key, status, created_at, source_policy
                        FROM dex_raw_liquidity_events
                        WHERE lower(chain) = ? AND lower(pair_address) = ?
                        {status_sql}
                        ORDER BY block_number ASC, log_index ASC
                        """,
                        tuple(params),
                    ).fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        blockers.append(f"sync_liquidity_evidence_review_query_error:{type(exc).__name__}")

    sync_assessments = [{**row, **_row_bound_status(row, "Sync")} for row in sync_rows]
    liquidity_assessments = [{**row, **_row_bound_status(row, str(row.get("event_name") or ""))} for row in liquidity_rows]
    all_assessments = sync_assessments + liquidity_assessments
    invalid_rows = [row for row in all_assessments if row.get("review_blockers")]
    duplicate_count = sum(int(value.get("duplicate_event_dedupe_keys") or 0) for value in table_status.values())
    event_names = sorted({str(row.get("event_name") or "") for row in liquidity_rows if row.get("event_name")})
    invalid_liquidity_events = [name for name in event_names if name not in {"Mint", "Burn"}]

    if not sync_rows:
        blockers.append("no_sync_evidence_rows_for_pool")
    if not liquidity_rows:
        blockers.append("no_liquidity_evidence_rows_for_pool")
    if duplicate_count:
        blockers.append("duplicate_event_dedupe_keys")
    if invalid_rows:
        blockers.append("sync_liquidity_evidence_binding_drift")
    if invalid_liquidity_events:
        blockers.append("invalid_liquidity_event_name")

    repair_ready = repair.get("repair_status") == "repair_context_ready_read_only"
    if not repair_ready:
        blockers.append("repair_bridge_not_ready")
    blockers = list(dict.fromkeys(blockers))
    readiness = "ready_for_outcome_quality_repair_preview" if not blockers else "blocked"

    def _block_range(rows: list[dict[str, Any]]) -> dict[str, int | None]:
        blocks = []
        for row in rows:
            try:
                blocks.append(int(row.get("block_number")))
            except (TypeError, ValueError):
                continue
        return {
            "first_block": min(blocks) if blocks else None,
            "last_block": max(blocks) if blocks else None,
        }

    def _preview(row: dict[str, Any], table: str) -> dict[str, Any]:
        return {
            "table": table,
            "id": row.get("id"),
            "chain": row.get("chain"),
            "pair_address": row.get("pair_address"),
            "event_name": row.get("event_name") or "Sync",
            "block_number": row.get("block_number"),
            "tx_hash": row.get("tx_hash"),
            "log_index": row.get("log_index"),
            "payload_digest": row.get("payload_digest"),
            "event_dedupe_key": row.get("event_dedupe_key"),
            "status": row.get("status"),
            "payload_json_valid": row.get("payload_json_valid"),
            "payload_digest_bound": row.get("payload_digest_bound"),
            "source_bound": row.get("source_bound"),
            "event_name_bound": row.get("event_name_bound"),
            "pool_bound": row.get("pool_bound"),
            "dedupe_bound": row.get("dedupe_bound"),
            "review_blockers": row.get("review_blockers"),
        }

    summary = {
        "sync_rows": len(sync_rows),
        "liquidity_rows": len(liquidity_rows),
        "total_rows": len(sync_rows) + len(liquidity_rows),
        "duplicate_event_dedupe_keys": duplicate_count,
        "payload_digest_bound": len([row for row in all_assessments if row.get("payload_digest_bound")]),
        "source_bound": len([row for row in all_assessments if row.get("source_bound")]),
        "pool_bound": len([row for row in all_assessments if row.get("pool_bound")]),
        "dedupe_bound": len([row for row in all_assessments if row.get("dedupe_bound")]),
        "invalid_rows": len(invalid_rows),
        "sync_block_range": _block_range(sync_rows),
        "liquidity_block_range": _block_range(liquidity_rows),
        "liquidity_event_names": event_names,
        "status_filter": clean_status or None,
        "repair_bridge_status": repair.get("repair_status"),
        "can_repair_stale_windows_now": bool((repair.get("quality_readiness") or {}).get("can_repair_stale_windows_now")),
        "can_detect_reliable_manipulation_now": False,
    }
    return {
        "ok": True,
        "dry_run": True,
        "queue_status": "ready_but_disabled" if readiness != "blocked" else "blocked",
        "review_readiness": readiness,
        "chain": clean_chain,
        "pool_address": pool or None,
        "token_address": token or None,
        "token_symbol": repair.get("token_symbol"),
        "target_tables": ["dex_raw_sync_events", "dex_raw_liquidity_events"],
        "table_status": table_status,
        "summary": summary,
        "repair_bridge": {
            "repair_status": repair.get("repair_status"),
            "next_safe_step": repair.get("next_safe_step"),
            "quality_readiness": repair.get("quality_readiness"),
        },
        "rows": [
            *[_preview(row, "dex_raw_sync_events") for row in sync_assessments[:clean_limit]],
            *[_preview(row, "dex_raw_liquidity_events") for row in liquidity_assessments[: max(0, clean_limit - min(clean_limit, len(sync_assessments)))]],
        ],
        "blockers": blockers,
        "next_safe_step": (
            "outcome_quality_repair_preview_read_only"
            if readiness != "blocked"
            else "repair_sync_liquidity_evidence_blockers"
        ),
        "plain_summary_fr": (
            "Les preuves Sync/liquidite UFLOKI sont seulement du contexte brut: elles peuvent aider a verifier la "
            "qualite des fenetres de resultat, mais elles ne sont pas un signal ni un trade."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_outcome_quality_repair_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only preview that shows how reviewed Sync/liquidity rows can repair outcome windows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 50), 100))
    source_policy = (
        "admin-only read-only UFLOKI outcome quality repair preview. It consumes only local reviewed raw "
        "Sync/liquidity evidence and the local outcome quality checkpoint. It does not persist repaired outcomes, "
        "does not create scores, signals, mappings, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_insert_outcome_row": False,
        "would_persist_repaired_outcome": False,
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "repair_preview_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    review = get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review_queue(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        status="raw_observed",
        limit=clean_limit,
        dry_run=True,
    )
    repair = get_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context_dry_run(
        chain=clean_chain,
        pool_address=str(review.get("pool_address") or clean_pool or "") or None,
        token_address=str(review.get("token_address") or clean_token or "") or None,
        limit=clean_limit,
        dry_run=True,
        allow_rpc=False,
        confirm=None,
    )
    blockers = list(dict.fromkeys([
        *(review.get("blockers") or []),
        *(repair.get("blockers") or []),
        *([] if review.get("review_readiness") == "ready_for_outcome_quality_repair_preview" else ["sync_liquidity_review_not_ready"]),
        *([] if repair.get("repair_status") == "repair_context_ready_read_only" else ["repair_context_not_ready"]),
    ]))

    def _reserve_ratio(sync_row: dict[str, Any] | None) -> float | None:
        if not sync_row:
            return None
        try:
            reserve0 = Decimal(str(sync_row.get("reserve0") or "0"))
            reserve1 = Decimal(str(sync_row.get("reserve1") or "0"))
            if reserve0 <= 0 or reserve1 <= 0:
                return None
            return float((reserve0 / reserve1).quantize(Decimal("0.0000000001")))
        except (InvalidOperation, ValueError, TypeError):
            return None

    repaired_windows: list[dict[str, Any]] = []
    for window in list(repair.get("window_assessments") or []):
        price_blockers = list(window.get("price_window_blockers") or [])
        local_sync_start = dict(window.get("local_sync_start") or {})
        local_sync_end = dict(window.get("local_sync_end") or {})
        local_reserve_context_available = bool(window.get("local_reserve_context_available"))
        local_liquidity_events_in_pool = int(window.get("local_liquidity_events_in_pool") or 0)
        needs_repair = bool(window.get("needs_quality_repair"))
        can_repair_window = bool(needs_repair and local_reserve_context_available and local_liquidity_events_in_pool > 0)
        if not needs_repair:
            status = "already_usable_local_proxy"
        elif can_repair_window:
            status = "repairable_with_reviewed_sync_liquidity_context"
        else:
            status = "blocked_missing_repair_context"
        repaired_windows.append({
            "window_label": window.get("window_label"),
            "source_window_status": window.get("window_status"),
            "source_price_window_complete": window.get("price_window_complete"),
            "source_price_window_blockers": price_blockers,
            "needs_quality_repair": needs_repair,
            "repair_preview_status": status,
            "can_repair_window_now": can_repair_window or not needs_repair,
            "start_block": window.get("start_block"),
            "end_block": window.get("end_block"),
            "sync_start_block": local_sync_start.get("block_number"),
            "sync_end_block": local_sync_end.get("block_number"),
            "sync_start_reserve_ratio_raw": _reserve_ratio(local_sync_start),
            "sync_end_reserve_ratio_raw": _reserve_ratio(local_sync_end),
            "liquidity_events_in_pool": local_liquidity_events_in_pool,
            "repair_blockers": list(window.get("repair_blockers") or []),
            "interpretation": (
                "Sync reserve context can repair stale/incomplete outcome quality for shadow analysis"
                if can_repair_window else
                "Window was already usable in the local price proxy"
                if not needs_repair else
                "Window still lacks reserve/liquidity context"
            ),
        })

    repairable_windows = [row for row in repaired_windows if row.get("can_repair_window_now")]
    stale_or_damaged = [row for row in repaired_windows if row.get("needs_quality_repair")]
    damaged_repaired = [
        row for row in repaired_windows
        if row.get("needs_quality_repair") and row.get("repair_preview_status") == "repairable_with_reviewed_sync_liquidity_context"
    ]
    can_build_repaired_outcome_dataset = bool(
        repaired_windows
        and len(damaged_repaired) == len(stale_or_damaged)
        and review.get("review_readiness") == "ready_for_outcome_quality_repair_preview"
    )
    if not can_build_repaired_outcome_dataset:
        blockers.append("not_all_damaged_windows_repairable")
    blockers = list(dict.fromkeys(blockers))
    return {
        "ok": True,
        "dry_run": True,
        "repair_preview_status": "ready_but_disabled" if not blockers else "blocked",
        "chain": clean_chain,
        "pool_address": review.get("pool_address") or repair.get("pool_address") or clean_pool or None,
        "token_address": review.get("token_address") or repair.get("token_address") or clean_token or None,
        "token_symbol": review.get("token_symbol") or repair.get("token_symbol"),
        "source_review_status": review.get("queue_status"),
        "source_review_readiness": review.get("review_readiness"),
        "source_repair_status": repair.get("repair_status"),
        "review_summary": review.get("summary"),
        "repaired_outcome_windows": repaired_windows,
        "summary": {
            "total_windows": len(repaired_windows),
            "damaged_windows": len(stale_or_damaged),
            "damaged_windows_repairable": len(damaged_repaired),
            "all_damaged_windows_repairable": len(damaged_repaired) == len(stale_or_damaged),
            "repairable_or_already_usable_windows": len(repairable_windows),
            "can_build_repaired_outcome_dataset": can_build_repaired_outcome_dataset,
            "can_run_shadow_backtest_after_dataset_step": can_build_repaired_outcome_dataset,
            "can_detect_reliable_manipulation_now": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "repaired_outcome_dataset_schema_plan_read_only"
            if not blockers
            else "repair_remaining_outcome_quality_blockers"
        ),
        "plain_summary_fr": (
            "Les preuves Sync/liquidite revues peuvent reparer les fenetres outcome UFLOKI abimees. "
            "La prochaine etape reste un dataset/backtest shadow, pas un signal client."
            if not blockers else
            "Les fenetres outcome UFLOKI ne sont pas encore toutes reparables avec les preuves locales."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only schema-plan for a future repaired UFLOKI outcome dataset."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 50), 100))
    target_table = "manipulation_repaired_outcome_windows"
    source_policy = (
        "admin-only read-only schema-plan for future repaired UFLOKI outcome windows. It uses the local outcome "
        "quality repair preview and reviewed Sync/liquidity evidence. It creates no table, persists no outcome, "
        "runs no backtest, emits no client signal, executes no trade and creates no opt-in."
    )
    disabled = {
        "would_create_table": False,
        "would_insert_repaired_outcome_row": False,
        "would_insert_outcome_row": False,
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "target_table": target_table,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    repair_preview = get_manipulation_detection_source_backed_outcome_quality_repair_preview(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
    )
    summary = dict(repair_preview.get("summary") or {})
    repaired_windows = list(repair_preview.get("repaired_outcome_windows") or [])
    pool = str(repair_preview.get("pool_address") or clean_pool or "").strip().lower()
    token = str(repair_preview.get("token_address") or clean_token or "").strip().lower()
    token_symbol = str(repair_preview.get("token_symbol") or "").strip().upper() or None
    repair_preview_digest = _sync_liquidity_payload_digest({
        "policy_version": "ufloki_repaired_outcome_dataset_schema_plan_v1",
        "chain": clean_chain,
        "pool_address": pool,
        "token_address": token,
        "summary": summary,
        "windows": repaired_windows,
    })
    table_exists = False
    existing_rows = 0
    try:
        conn = _get_db()
        try:
            table_exists = _table_exists(conn, target_table)
            if table_exists:
                existing_rows = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
        finally:
            conn.close()
    except Exception:
        table_exists = False
        existing_rows = 0

    schema_preview = [
        {"name": "id", "type": "INTEGER PRIMARY KEY AUTOINCREMENT", "purpose": "local repaired outcome row id"},
        {"name": "chain", "type": "TEXT NOT NULL", "purpose": "chain scope, e.g. bsc"},
        {"name": "pool_address", "type": "TEXT NOT NULL", "purpose": "source-backed pool under test"},
        {"name": "token_address", "type": "TEXT NOT NULL", "purpose": "token under test"},
        {"name": "token_symbol", "type": "TEXT", "purpose": "display symbol only"},
        {"name": "repair_preview_digest", "type": "TEXT NOT NULL", "purpose": "digest of the read-only repair preview"},
        {"name": "outcome_window_label", "type": "TEXT NOT NULL", "purpose": "window label such as plus_1h, plus_6h, plus_24h, plus_72h"},
        {"name": "source_window_status", "type": "TEXT", "purpose": "original local outcome window status"},
        {"name": "repair_status", "type": "TEXT NOT NULL", "purpose": "already usable or repaired with Sync/liquidity context"},
        {"name": "start_block", "type": "INTEGER", "purpose": "window start block"},
        {"name": "end_block", "type": "INTEGER", "purpose": "window end block"},
        {"name": "sync_start_block", "type": "INTEGER", "purpose": "nearest Sync reserve block at window start"},
        {"name": "sync_end_block", "type": "INTEGER", "purpose": "nearest Sync reserve block at window end"},
        {"name": "sync_start_reserve_ratio_raw", "type": "REAL", "purpose": "raw reserve ratio preview at start"},
        {"name": "sync_end_reserve_ratio_raw", "type": "REAL", "purpose": "raw reserve ratio preview at end"},
        {"name": "liquidity_events_in_pool", "type": "INTEGER NOT NULL", "purpose": "Mint/Burn context count around the pool"},
        {"name": "source_price_window_blockers_json", "type": "TEXT NOT NULL", "purpose": "original local outcome quality blockers"},
        {"name": "repair_blockers_json", "type": "TEXT NOT NULL", "purpose": "remaining repair blockers, expected empty for ready rows"},
        {"name": "repaired_outcome_payload_json", "type": "TEXT NOT NULL", "purpose": "normalized repaired outcome payload"},
        {"name": "repaired_outcome_digest", "type": "TEXT NOT NULL", "purpose": "hash of normalized repaired outcome payload"},
        {"name": "repaired_outcome_dedupe_key", "type": "TEXT NOT NULL UNIQUE", "purpose": "future duplicate guard"},
        {"name": "status", "type": "TEXT NOT NULL DEFAULT 'pending_shadow_backtest_review'", "purpose": "future review status, not signal"},
        {"name": "created_at", "type": "TEXT NOT NULL", "purpose": "future insertion timestamp"},
        {"name": "source_policy", "type": "TEXT NOT NULL", "purpose": "policy that produced the row"},
    ]
    indexes_preview = [
        "UNIQUE(repaired_outcome_dedupe_key)",
        "INDEX(chain, pool_address, token_address)",
        "INDEX(repair_preview_digest)",
        "INDEX(outcome_window_label)",
        "INDEX(status)",
        "INDEX(start_block, end_block)",
    ]
    constraints_preview = [
        "dry_run_required_for_schema_plan",
        "source_repair_preview_must_be_ready",
        "all_damaged_windows_must_be_repairable",
        "repair_preview_digest_required",
        "no_overwrite",
        "no_upsert",
        "no_silent_success",
        "dataset_is_shadow_backtest_input_only",
        "no_client_signal",
        "no_trade",
        "no_mapping",
        "no_label",
        "no_opt_in",
    ]
    dedupe_formula = "chain|pool_address|token_address|repair_preview_digest|outcome_window_label|start_block|end_block"
    planned_rows_preview = []
    for row in repaired_windows[:clean_limit]:
        dedupe_key = "|".join(str(item or "") for item in [
            clean_chain,
            pool,
            token,
            repair_preview_digest,
            row.get("window_label"),
            row.get("start_block"),
            row.get("end_block"),
        ])
        payload = {
            "chain": clean_chain,
            "pool_address": pool,
            "token_address": token,
            "token_symbol": token_symbol,
            "repair_preview_digest": repair_preview_digest,
            "window": row,
        }
        planned_rows_preview.append({
            "outcome_window_label": row.get("window_label"),
            "repair_status": row.get("repair_preview_status"),
            "can_repair_window_now": row.get("can_repair_window_now"),
            "start_block": row.get("start_block"),
            "end_block": row.get("end_block"),
            "sync_start_block": row.get("sync_start_block"),
            "sync_end_block": row.get("sync_end_block"),
            "liquidity_events_in_pool": row.get("liquidity_events_in_pool"),
            "repaired_outcome_dedupe_key": dedupe_key,
            "repaired_outcome_digest": _sync_liquidity_payload_digest(payload),
            "would_insert": False,
        })

    ready = bool(
        repair_preview.get("repair_preview_status") == "ready_but_disabled"
        and summary.get("can_build_repaired_outcome_dataset")
        and planned_rows_preview
    )
    blockers = list(dict.fromkeys([
        *(repair_preview.get("blockers") or []),
        *([] if repair_preview.get("repair_preview_status") == "ready_but_disabled" else ["repair_preview_not_ready"]),
        *([] if summary.get("can_build_repaired_outcome_dataset") else ["repaired_outcome_dataset_not_buildable"]),
        *([] if planned_rows_preview else ["no_repaired_outcome_rows_planned"]),
        "schema_plan_only_no_table_created",
        "shadow_backtest_not_run",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready" if ready else "blocked",
        "chain": clean_chain,
        "pool_address": pool or None,
        "token_address": token or None,
        "token_symbol": token_symbol,
        "target_table": target_table,
        "table_exists": table_exists,
        "existing_rows": existing_rows,
        "migration_required": not table_exists,
        "confirm_required": "CREATE_MANIPULATION_REPAIRED_OUTCOME_WINDOWS",
        "repair_preview_digest": repair_preview_digest,
        "schema_preview": schema_preview,
        "indexes_preview": indexes_preview,
        "constraints_preview": constraints_preview,
        "dedupe_constraints": {
            "repaired_outcome_dedupe_key_formula": dedupe_formula,
            "duplicate_future_insert": "block",
            "overwrite": "blocked",
            "upsert": "blocked",
            "silent_success": "blocked",
        },
        "source_repair_preview": {
            "repair_preview_status": repair_preview.get("repair_preview_status"),
            "summary": summary,
            "source_review_readiness": repair_preview.get("source_review_readiness"),
            "source_repair_status": repair_preview.get("source_repair_status"),
        },
        "planned_repaired_outcome_rows": len(planned_rows_preview),
        "planned_rows_preview": planned_rows_preview,
        "blockers": blockers,
        "next_safe_step": (
            "confirmed_empty_ddl_migration_for_repaired_outcome_windows"
            if ready and not table_exists
            else "repaired_outcome_row_insert_dry_run_first"
            if ready
            else "repair_outcome_dataset_schema_plan_blockers"
        ),
        "plain_summary_fr": (
            "Cette future table stockerait les fenetres outcome UFLOKI reparees pour backtest shadow. "
            "Elle ne cree aucun signal client et ne lance aucun trade."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def create_manipulation_detection_source_backed_repaired_outcome_dataset_table(
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Confirmed DDL-only creation of the repaired outcome dataset table."""
    clean_chain = _normalize_chain(chain or "bsc")
    target_table = "manipulation_repaired_outcome_windows"
    required_confirm = "CREATE_MANIPULATION_REPAIRED_OUTCOME_WINDOWS"
    source_policy = (
        "admin-confirmed DDL-only repaired outcome dataset migration. It creates only the empty "
        "manipulation_repaired_outcome_windows table and indexes if absent; it inserts zero outcome rows, "
        "runs no backtest, persists no score, creates no mapping, emits no client signal, executes no trade "
        "and creates no opt-in."
    )
    disabled = {
        "would_insert_repaired_outcome_row": False,
        "would_insert_outcome_row": False,
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_policy": source_policy,
    }

    plan = get_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan(
        chain=clean_chain,
        dry_run=True,
        limit=10,
    )
    blockers: list[str] = []
    allowed_plan_blockers = {
        "schema_plan_only_no_table_created",
        "shadow_backtest_not_run",
        "client_signal_disabled",
        "trade_disabled",
    }
    plan_blockers = set(plan.get("blockers") or [])
    if plan.get("target_table") != target_table:
        blockers.append("repaired_outcome_dataset_schema_plan_target_mismatch")
    if plan.get("plan_status") != "ready":
        blockers.append("repaired_outcome_dataset_schema_plan_not_ready")
    if plan_blockers and not plan_blockers.issubset(allowed_plan_blockers):
        blockers.append("repaired_outcome_dataset_schema_plan_blocked_unexpectedly")
    if not dry_run and confirm != required_confirm:
        blockers.append("confirm_CREATE_MANIPULATION_REPAIRED_OUTCOME_WINDOWS_required")

    expected_columns = [
        "id",
        "chain",
        "pool_address",
        "token_address",
        "token_symbol",
        "repair_preview_digest",
        "outcome_window_label",
        "source_window_status",
        "repair_status",
        "start_block",
        "end_block",
        "sync_start_block",
        "sync_end_block",
        "sync_start_reserve_ratio_raw",
        "sync_end_reserve_ratio_raw",
        "liquidity_events_in_pool",
        "source_price_window_blockers_json",
        "repair_blockers_json",
        "repaired_outcome_payload_json",
        "repaired_outcome_digest",
        "repaired_outcome_dedupe_key",
        "status",
        "created_at",
        "source_policy",
    ]
    index_sql = [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_manipulation_repaired_outcome_dedupe ON manipulation_repaired_outcome_windows(repaired_outcome_dedupe_key)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_repaired_outcome_chain_pool_token ON manipulation_repaired_outcome_windows(chain, pool_address, token_address)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_repaired_outcome_repair_digest ON manipulation_repaired_outcome_windows(repair_preview_digest)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_repaired_outcome_window ON manipulation_repaired_outcome_windows(outcome_window_label)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_repaired_outcome_status ON manipulation_repaired_outcome_windows(status)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_repaired_outcome_blocks ON manipulation_repaired_outcome_windows(start_block, end_block)",
    ]

    conn = _get_db()
    try:
        table_exists = _table_exists(conn, target_table)
        row_count = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0) if table_exists else 0
        if table_exists:
            existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({target_table})").fetchall()}
            if any(column not in existing_columns for column in expected_columns):
                blockers.append("manipulation_repaired_outcome_windows_schema_drift_detected")
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
            "would_create_table": bool(migration_required and not blockers),
            "table_created": False,
            "indexes_created": [],
            "rows_inserted": 0,
            "row_count": row_count,
            "planned_repaired_outcome_rows": plan.get("planned_repaired_outcome_rows"),
            "repair_preview_digest": plan.get("repair_preview_digest"),
            "can_detect_reliable_manipulation_now": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": blockers,
            **disabled,
        }

    conn = _get_db()
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
            CREATE TABLE IF NOT EXISTS manipulation_repaired_outcome_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                pool_address TEXT NOT NULL,
                token_address TEXT NOT NULL,
                token_symbol TEXT,
                repair_preview_digest TEXT NOT NULL,
                outcome_window_label TEXT NOT NULL,
                source_window_status TEXT,
                repair_status TEXT NOT NULL,
                start_block INTEGER,
                end_block INTEGER,
                sync_start_block INTEGER,
                sync_end_block INTEGER,
                sync_start_reserve_ratio_raw REAL,
                sync_end_reserve_ratio_raw REAL,
                liquidity_events_in_pool INTEGER NOT NULL,
                source_price_window_blockers_json TEXT NOT NULL,
                repair_blockers_json TEXT NOT NULL,
                repaired_outcome_payload_json TEXT NOT NULL,
                repaired_outcome_digest TEXT NOT NULL,
                repaired_outcome_dedupe_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending_shadow_backtest_review',
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
        "would_create_table": False,
        "table_created": table_created,
        "indexes_created": created_indexes,
        "rows_inserted": 0,
        "row_count": row_count,
        "planned_repaired_outcome_rows": plan.get("planned_repaired_outcome_rows"),
        "repair_preview_digest": plan.get("repair_preview_digest"),
        "can_detect_reliable_manipulation_now": False,
        "would_write": False,
        "real_write_enabled": bool(table_created or created_indexes),
        "writes_performed": (1 if table_created else 0) + len(created_indexes),
        "blockers": [],
        **disabled,
    }


def insert_manipulation_detection_source_backed_repaired_outcome_dataset(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    confirm: str | None = None,
    expected_repair_preview_digest: str | None = None,
) -> dict[str, Any]:
    """Dry-run-first insert lane for repaired UFLOKI outcome rows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 50), 100))
    target_table = "manipulation_repaired_outcome_windows"
    required_confirm = "INSERT_MANIPULATION_REPAIRED_OUTCOME_WINDOWS"
    source_policy = (
        "admin-confirmed dry-run-first repaired outcome insert. It inserts only normalized repaired outcome rows "
        "into manipulation_repaired_outcome_windows after digest confirmation. It does not run a backtest, persist "
        "a score, create a mapping, emit a client signal, execute a trade or create an opt-in."
    )
    disabled = {
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_policy": source_policy,
    }

    plan = get_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
    )
    repair_preview = get_manipulation_detection_source_backed_outcome_quality_repair_preview(
        chain=clean_chain,
        pool_address=str(plan.get("pool_address") or clean_pool or "") or None,
        token_address=str(plan.get("token_address") or clean_token or "") or None,
        limit=clean_limit,
        dry_run=True,
    )
    pool = str(plan.get("pool_address") or repair_preview.get("pool_address") or clean_pool or "").strip().lower()
    token = str(plan.get("token_address") or repair_preview.get("token_address") or clean_token or "").strip().lower()
    token_symbol = str(plan.get("token_symbol") or repair_preview.get("token_symbol") or "").strip().upper() or None
    repair_preview_digest = str(plan.get("repair_preview_digest") or "").strip()
    blockers = list(dict.fromkeys([
        *(plan.get("blockers") or []),
        *(repair_preview.get("blockers") or []),
        *([] if plan.get("plan_status") == "ready" else ["repaired_outcome_dataset_schema_plan_not_ready"]),
        *([] if plan.get("table_exists") else ["manipulation_repaired_outcome_windows_missing"]),
        *([] if repair_preview.get("repair_preview_status") == "ready_but_disabled" else ["repair_preview_not_ready"]),
        *([] if repair_preview_digest else ["repair_preview_digest_missing"]),
    ]))
    allowed_plan_blockers = {
        "schema_plan_only_no_table_created",
        "shadow_backtest_not_run",
        "client_signal_disabled",
        "trade_disabled",
    }
    blockers = [blocker for blocker in blockers if blocker not in allowed_plan_blockers]
    if not dry_run:
        if confirm != required_confirm:
            blockers.append("confirm_INSERT_MANIPULATION_REPAIRED_OUTCOME_WINDOWS_required")
        if not expected_repair_preview_digest:
            blockers.append("expected_repair_preview_digest_required")
        elif str(expected_repair_preview_digest or "").strip() != repair_preview_digest:
            blockers.append("expected_repair_preview_digest_mismatch")

    repaired_windows = list(repair_preview.get("repaired_outcome_windows") or [])
    candidate_rows: list[dict[str, Any]] = []
    for window in repaired_windows:
        if not window.get("can_repair_window_now"):
            continue
        dedupe_key = "|".join(str(item or "") for item in [
            clean_chain,
            pool,
            token,
            repair_preview_digest,
            window.get("window_label"),
            window.get("start_block"),
            window.get("end_block"),
        ])
        payload = {
            "chain": clean_chain,
            "pool_address": pool,
            "token_address": token,
            "token_symbol": token_symbol,
            "repair_preview_digest": repair_preview_digest,
            "window": window,
        }
        payload_json = _sync_liquidity_canonical_json(payload)
        candidate_rows.append({
            "chain": clean_chain,
            "pool_address": pool,
            "token_address": token,
            "token_symbol": token_symbol,
            "repair_preview_digest": repair_preview_digest,
            "outcome_window_label": window.get("window_label"),
            "source_window_status": window.get("source_window_status"),
            "repair_status": window.get("repair_preview_status"),
            "start_block": window.get("start_block"),
            "end_block": window.get("end_block"),
            "sync_start_block": window.get("sync_start_block"),
            "sync_end_block": window.get("sync_end_block"),
            "sync_start_reserve_ratio_raw": window.get("sync_start_reserve_ratio_raw"),
            "sync_end_reserve_ratio_raw": window.get("sync_end_reserve_ratio_raw"),
            "liquidity_events_in_pool": int(window.get("liquidity_events_in_pool") or 0),
            "source_price_window_blockers_json": _sync_liquidity_canonical_json(window.get("source_price_window_blockers") or []),
            "repair_blockers_json": _sync_liquidity_canonical_json(window.get("repair_blockers") or []),
            "repaired_outcome_payload_json": payload_json,
            "repaired_outcome_digest": _sync_liquidity_payload_digest(payload),
            "repaired_outcome_dedupe_key": dedupe_key,
            "status": "pending_shadow_backtest_review",
        })
    if not candidate_rows:
        blockers.append("no_repaired_outcome_rows_to_insert")

    existing_duplicate_keys: set[str] = set()
    table_count_before: int | None = None
    conn = _get_db()
    try:
        if not _table_exists(conn, target_table):
            table_count_before = None
        else:
            table_count_before = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
            if candidate_rows:
                placeholders = ",".join("?" for _ in candidate_rows)
                keys = [str(row["repaired_outcome_dedupe_key"]) for row in candidate_rows]
                for (existing_key,) in conn.execute(
                    f"SELECT repaired_outcome_dedupe_key FROM {target_table} WHERE repaired_outcome_dedupe_key IN ({placeholders})",
                    keys,
                ).fetchall():
                    existing_duplicate_keys.add(str(existing_key))
    finally:
        conn.close()
    duplicate_existing_count = len(existing_duplicate_keys)
    insertable_rows = [
        row for row in candidate_rows
        if str(row.get("repaired_outcome_dedupe_key") or "") not in existing_duplicate_keys
    ]
    if candidate_rows and not insertable_rows and duplicate_existing_count:
        blockers.append("duplicate_repaired_outcome_rows_exist")
    blockers = list(dict.fromkeys(blockers))

    if dry_run or blockers:
        return {
            "ok": not blockers,
            "dry_run": bool(dry_run),
            "insert_status": "ready_for_insert" if not blockers else "blocked",
            "chain": clean_chain,
            "pool_address": pool or None,
            "token_address": token or None,
            "token_symbol": token_symbol,
            "target_table": target_table,
            "table_exists": bool(plan.get("table_exists")),
            "repair_preview_digest": repair_preview_digest or None,
            "expected_repair_preview_digest_required_for_real_insert": repair_preview_digest or None,
            "candidate_rows": len(candidate_rows),
            "duplicate_existing_count": duplicate_existing_count,
            "would_insert_repaired_outcome_rows": len(insertable_rows) if not blockers else 0,
            "would_insert_repaired_outcome_row": bool(insertable_rows and not blockers),
            "inserted_repaired_outcome_rows": 0,
            "inserted": False,
            "table_count_before": table_count_before,
            "preview_rows": [
                {
                    "outcome_window_label": row.get("outcome_window_label"),
                    "repair_status": row.get("repair_status"),
                    "start_block": row.get("start_block"),
                    "end_block": row.get("end_block"),
                    "repaired_outcome_dedupe_key": row.get("repaired_outcome_dedupe_key"),
                    "repaired_outcome_digest": row.get("repaired_outcome_digest"),
                    "row_status": "duplicate_existing"
                    if row.get("repaired_outcome_dedupe_key") in existing_duplicate_keys
                    else "insertable",
                }
                for row in candidate_rows[:clean_limit]
            ],
            "blockers": blockers,
            "can_detect_reliable_manipulation_now": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            **disabled,
        }

    created_at = datetime.now(timezone.utc).isoformat()
    columns = [
        "chain",
        "pool_address",
        "token_address",
        "token_symbol",
        "repair_preview_digest",
        "outcome_window_label",
        "source_window_status",
        "repair_status",
        "start_block",
        "end_block",
        "sync_start_block",
        "sync_end_block",
        "sync_start_reserve_ratio_raw",
        "sync_end_reserve_ratio_raw",
        "liquidity_events_in_pool",
        "source_price_window_blockers_json",
        "repair_blockers_json",
        "repaired_outcome_payload_json",
        "repaired_outcome_digest",
        "repaired_outcome_dedupe_key",
        "status",
        "created_at",
        "source_policy",
    ]

    def _values(row: dict[str, Any]) -> tuple[Any, ...]:
        payload = dict(row)
        payload["created_at"] = created_at
        payload["source_policy"] = source_policy
        return tuple(payload.get(column) for column in columns)

    conn = _get_db()
    try:
        placeholders = ",".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO {target_table} ({','.join(columns)}) VALUES ({placeholders})",
            [_values(row) for row in insertable_rows],
        )
        conn.commit()
        table_count_after = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
    finally:
        conn.close()
    inserted_count = len(insertable_rows)
    return {
        "ok": True,
        "dry_run": False,
        "insert_status": "inserted" if inserted_count else "blocked",
        "chain": clean_chain,
        "pool_address": pool or None,
        "token_address": token or None,
        "token_symbol": token_symbol,
        "target_table": target_table,
        "repair_preview_digest": repair_preview_digest or None,
        "candidate_rows": len(candidate_rows),
        "duplicate_existing_count": duplicate_existing_count,
        "inserted_repaired_outcome_rows": inserted_count,
        "inserted": bool(inserted_count),
        "table_count_before": table_count_before,
        "table_count_after": table_count_after,
        "blockers": [],
        "can_detect_reliable_manipulation_now": False,
        "would_insert_repaired_outcome_row": False,
        "would_insert_repaired_outcome_rows": 0,
        "would_write": False,
        "real_write_enabled": bool(inserted_count),
        "writes_performed": inserted_count,
        **disabled,
    }


def get_manipulation_detection_source_backed_repaired_outcome_dataset_review_queue(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    status: str | None = "pending_shadow_backtest_review",
    limit: int = 50,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only review queue for repaired UFLOKI outcome rows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_status = str(status or "").strip()
    clean_limit = max(1, min(int(limit or 50), 100))
    target_table = "manipulation_repaired_outcome_windows"
    source_policy = (
        "admin-only read-only repaired outcome review queue. It validates repaired outcome rows against payload "
        "digests, dedupe keys, repair preview digest, route, status and window coverage. It does not update "
        "status, run a backtest, persist a score, create a mapping, emit a client signal, execute a trade or "
        "create an opt-in."
    )
    disabled = {
        "would_update_status": False,
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "queue_status": "blocked",
            "target_table": target_table,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    schema_plan = get_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
    )
    expected_repair_digest = str(schema_plan.get("repair_preview_digest") or "").strip()
    pool = str(schema_plan.get("pool_address") or clean_pool or "").strip().lower()
    token = str(schema_plan.get("token_address") or clean_token or "").strip().lower()
    token_symbol = str(schema_plan.get("token_symbol") or "").strip().upper() or None
    blockers = []
    table_exists = False
    row_count_total = 0
    duplicate_dedupe_count = 0
    rows: list[dict[str, Any]] = []
    try:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        try:
            table_exists = _table_exists(conn, target_table)
            if not table_exists:
                blockers.append("manipulation_repaired_outcome_windows_missing")
            else:
                row_count_total = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
                duplicate_dedupe_count = int(conn.execute(
                    f"""
                    SELECT COUNT(*) FROM (
                        SELECT repaired_outcome_dedupe_key
                        FROM {target_table}
                        GROUP BY repaired_outcome_dedupe_key
                        HAVING COUNT(*) > 1
                    )
                    """
                ).fetchone()[0] or 0)
                params: list[Any] = [clean_chain]
                where = ["lower(chain) = ?"]
                if pool:
                    where.append("lower(pool_address) = ?")
                    params.append(pool)
                if token:
                    where.append("lower(token_address) = ?")
                    params.append(token)
                if clean_status:
                    where.append("status = ?")
                    params.append(clean_status)
                rows = [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT id, chain, pool_address, token_address, token_symbol, repair_preview_digest,
                               outcome_window_label, source_window_status, repair_status, start_block, end_block,
                               sync_start_block, sync_end_block, sync_start_reserve_ratio_raw,
                               sync_end_reserve_ratio_raw, liquidity_events_in_pool,
                               source_price_window_blockers_json, repair_blockers_json,
                               repaired_outcome_payload_json, repaired_outcome_digest,
                               repaired_outcome_dedupe_key, status, created_at, source_policy
                        FROM {target_table}
                        WHERE {' AND '.join(where)}
                        ORDER BY start_block ASC, id ASC
                        LIMIT ?
                        """,
                        tuple([*params, clean_limit]),
                    ).fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        blockers.append(f"repaired_outcome_review_query_error:{type(exc).__name__}")

    def _row_payload(row: dict[str, Any]) -> dict[str, Any] | None:
        try:
            payload = json.loads(str(row.get("repaired_outcome_payload_json") or ""))
            return payload if isinstance(payload, dict) else None
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    assessed_rows: list[dict[str, Any]] = []
    for row in rows:
        payload = _row_payload(row)
        payload_digest_bound = bool(payload) and _sync_liquidity_payload_digest(payload) == str(row.get("repaired_outcome_digest") or "")
        row_chain = str(row.get("chain") or "").strip().lower()
        row_pool = str(row.get("pool_address") or "").strip().lower()
        row_token = str(row.get("token_address") or "").strip().lower()
        dedupe_expected = "|".join(str(item or "") for item in [
            row_chain,
            row_pool,
            row_token,
            row.get("repair_preview_digest"),
            row.get("outcome_window_label"),
            row.get("start_block"),
            row.get("end_block"),
        ])
        repair_digest_bound = str(row.get("repair_preview_digest") or "") == expected_repair_digest
        route_bound = row_chain == clean_chain and (not pool or row_pool == pool) and (not token or row_token == token)
        dedupe_bound = str(row.get("repaired_outcome_dedupe_key") or "") == dedupe_expected
        status_bound = str(row.get("status") or "") == clean_status if clean_status else True
        repair_status = str(row.get("repair_status") or "")
        window_repair_bound = repair_status in {
            "already_usable_local_proxy",
            "repairable_with_reviewed_sync_liquidity_context",
        }
        repair_blockers = []
        try:
            repair_blockers = json.loads(str(row.get("repair_blockers_json") or "[]"))
            if not isinstance(repair_blockers, list):
                repair_blockers = ["repair_blockers_json_not_list"]
        except (TypeError, ValueError, json.JSONDecodeError):
            repair_blockers = ["repair_blockers_json_invalid"]
        row_blockers = [
            *([] if payload else ["repaired_outcome_payload_json_invalid"]),
            *([] if payload_digest_bound else ["repaired_outcome_digest_drift"]),
            *([] if repair_digest_bound else ["repair_preview_digest_drift"]),
            *([] if route_bound else ["route_drift"]),
            *([] if dedupe_bound else ["repaired_outcome_dedupe_key_drift"]),
            *([] if status_bound else ["status_filter_mismatch"]),
            *([] if window_repair_bound else ["repair_status_not_backtestable"]),
            *([] if not repair_blockers else ["repair_blockers_not_empty"]),
        ]
        assessed_rows.append({
            **row,
            "payload_json_valid": bool(payload),
            "payload_digest_bound": payload_digest_bound,
            "repair_preview_digest_bound": repair_digest_bound,
            "route_bound": route_bound,
            "dedupe_bound": dedupe_bound,
            "status_bound": status_bound,
            "window_repair_bound": window_repair_bound,
            "review_blockers": row_blockers,
        })

    invalid_rows = [row for row in assessed_rows if row.get("review_blockers")]
    required_windows = {"plus_1h", "plus_6h", "plus_24h", "plus_72h"}
    observed_windows = {str(row.get("outcome_window_label") or "") for row in assessed_rows}
    missing_windows = sorted(required_windows - observed_windows)
    if not rows:
        blockers.append("no_repaired_outcome_rows_for_review")
    if duplicate_dedupe_count:
        blockers.append("duplicate_repaired_outcome_dedupe_keys")
    if invalid_rows:
        blockers.append("repaired_outcome_binding_drift")
    if missing_windows:
        blockers.append("missing_repaired_outcome_windows")
    blockers = list(dict.fromkeys(blockers))
    review_ready = bool(not blockers and len(assessed_rows) >= 4)
    summary = {
        "total_rows_in_table": row_count_total,
        "review_rows": len(assessed_rows),
        "ready_rows": len([row for row in assessed_rows if not row.get("review_blockers")]),
        "invalid_rows": len(invalid_rows),
        "duplicate_repaired_outcome_dedupe_keys": duplicate_dedupe_count,
        "payload_digest_bound": len([row for row in assessed_rows if row.get("payload_digest_bound")]),
        "repair_preview_digest_bound": len([row for row in assessed_rows if row.get("repair_preview_digest_bound")]),
        "route_bound": len([row for row in assessed_rows if row.get("route_bound")]),
        "dedupe_bound": len([row for row in assessed_rows if row.get("dedupe_bound")]),
        "windows": sorted(observed_windows),
        "missing_windows": missing_windows,
        "ready_for_shadow_backtest_preview": review_ready,
        "can_detect_reliable_manipulation_now": False,
    }
    return {
        "ok": True,
        "dry_run": True,
        "queue_status": "ready_but_disabled" if review_ready else "blocked",
        "review_readiness": "ready_for_shadow_backtest_preview" if review_ready else "blocked",
        "chain": clean_chain,
        "pool_address": pool or None,
        "token_address": token or None,
        "token_symbol": token_symbol,
        "target_table": target_table,
        "table_exists": table_exists,
        "status_filter": clean_status or None,
        "expected_repair_preview_digest": expected_repair_digest or None,
        "summary": summary,
        "rows": [
            {
                "repaired_outcome_id": row.get("id"),
                "outcome_window_label": row.get("outcome_window_label"),
                "repair_status": row.get("repair_status"),
                "start_block": row.get("start_block"),
                "end_block": row.get("end_block"),
                "sync_start_block": row.get("sync_start_block"),
                "sync_end_block": row.get("sync_end_block"),
                "liquidity_events_in_pool": row.get("liquidity_events_in_pool"),
                "repaired_outcome_digest": row.get("repaired_outcome_digest"),
                "repaired_outcome_dedupe_key": row.get("repaired_outcome_dedupe_key"),
                "status": row.get("status"),
                "payload_json_valid": row.get("payload_json_valid"),
                "payload_digest_bound": row.get("payload_digest_bound"),
                "repair_preview_digest_bound": row.get("repair_preview_digest_bound"),
                "route_bound": row.get("route_bound"),
                "dedupe_bound": row.get("dedupe_bound"),
                "review_blockers": row.get("review_blockers"),
            }
            for row in assessed_rows[:clean_limit]
        ],
        "blockers": blockers,
        "next_safe_step": "shadow_backtest_preview_read_only" if review_ready else "repair_repaired_outcome_review_blockers",
        "plain_summary_fr": (
            "Les 4 outcomes repares UFLOKI sont propres pour lancer une preview de shadow backtest. "
            "Ce n'est toujours pas un verdict client ni un trade."
            if review_ready else
            "Les outcomes repares UFLOKI ne sont pas encore assez propres pour le shadow backtest."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_shadow_backtest_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only in-memory shadow backtest preview from reviewed repaired outcome rows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 50), 100))
    source_policy = (
        "admin-only read-only shadow backtest preview. It uses reviewed repaired outcome rows plus local raw "
        "Swap outcome metrics to estimate whether the UFLOKI source-backed detection would have been useful. "
        "It does not persist a backtest, create a score, create a client signal, execute a trade, create a "
        "mapping, create a label, create a wallet order or create an opt-in."
    )
    disabled = {
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "preview_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    review = get_manipulation_detection_source_backed_repaired_outcome_dataset_review_queue(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        status="pending_shadow_backtest_review",
        limit=clean_limit,
        dry_run=True,
    )
    outcome = get_manipulation_detection_source_backed_outcome_window_data_collection_dry_run(
        chain=clean_chain,
        pool_address=review.get("pool_address") or clean_pool or None,
        token_address=review.get("token_address") or clean_token or None,
        limit=clean_limit,
        dry_run=True,
        allow_external=False,
        confirm=None,
    )
    review_summary = dict(review.get("summary") or {})
    review_ready = review.get("review_readiness") == "ready_for_shadow_backtest_preview"
    outcome_rows = {
        str(row.get("window_label") or ""): row
        for row in list(outcome.get("outcome_windows") or [])
        if isinstance(row, dict)
    }

    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _pct_change(start: Any, end: Any) -> float | None:
        start_value = _float_or_none(start)
        end_value = _float_or_none(end)
        if start_value in (None, 0) or end_value is None:
            return None
        return round(((end_value - start_value) / start_value) * 100, 4)

    evaluated_windows: list[dict[str, Any]] = []
    for review_row in list(review.get("rows") or []):
        label = str(review_row.get("outcome_window_label") or "")
        outcome_row = outcome_rows.get(label, {})
        sync_start_ratio = _float_or_none(review_row.get("sync_start_reserve_ratio_raw"))
        sync_end_ratio = _float_or_none(review_row.get("sync_end_reserve_ratio_raw"))
        evaluated_windows.append({
            "window_label": label,
            "repaired_outcome_id": review_row.get("repaired_outcome_id"),
            "repair_status": review_row.get("repair_status"),
            "price_proxy_status": outcome_row.get("status"),
            "source_window_complete": outcome_row.get("complete"),
            "price_points": outcome_row.get("price_points"),
            "distinct_tx_hashes": outcome_row.get("distinct_tx_hashes"),
            "quote_volume": outcome_row.get("quote_volume"),
            "price_start": outcome_row.get("price_start"),
            "price_high": outcome_row.get("price_high"),
            "price_low": outcome_row.get("price_low"),
            "price_end": outcome_row.get("price_end"),
            "max_favorable_move_pct": outcome_row.get("max_favorable_move_pct"),
            "max_adverse_move_pct": outcome_row.get("max_adverse_move_pct"),
            "net_move_pct": outcome_row.get("net_move_pct"),
            "time_to_peak_seconds": outcome_row.get("time_to_peak_seconds"),
            "time_to_peak_blocks": outcome_row.get("time_to_peak_blocks"),
            "sync_start_reserve_ratio_raw": sync_start_ratio,
            "sync_end_reserve_ratio_raw": sync_end_ratio,
            "sync_reserve_ratio_change_pct": _pct_change(sync_start_ratio, sync_end_ratio),
            "liquidity_events_in_pool": review_row.get("liquidity_events_in_pool"),
            "review_blockers": review_row.get("review_blockers"),
            "outcome_blockers": outcome_row.get("blockers") or [],
        })

    favorable_values = [
        float(row["max_favorable_move_pct"])
        for row in evaluated_windows
        if row.get("max_favorable_move_pct") is not None
    ]
    adverse_values = [
        float(row["max_adverse_move_pct"])
        for row in evaluated_windows
        if row.get("max_adverse_move_pct") is not None
    ]
    net_values = [
        float(row["net_move_pct"])
        for row in evaluated_windows
        if row.get("net_move_pct") is not None
    ]
    max_favorable = round(max(favorable_values), 4) if favorable_values else None
    max_adverse = round(min(adverse_values), 4) if adverse_values else None
    last_net = round(net_values[-1], 4) if net_values else None
    windows_with_positive_favorable = len([value for value in favorable_values if value > 0])
    windows_with_negative_net = len([value for value in net_values if value < 0])
    if max_favorable is not None and max_favorable >= 25 and (max_adverse is None or max_adverse > -40):
        outcome_classification = "promising_but_unvalidated"
    elif max_favorable is not None and max_favorable <= 0 and windows_with_negative_net:
        outcome_classification = "negative_for_long_opportunity"
    else:
        outcome_classification = "inconclusive_needs_controls"

    preview_digest_payload = {
        "chain": clean_chain,
        "pool": review.get("pool_address") or clean_pool,
        "token": review.get("token_address") or clean_token,
        "review_readiness": review.get("review_readiness"),
        "evaluated_windows": [
            {
                "window_label": row.get("window_label"),
                "max_favorable_move_pct": row.get("max_favorable_move_pct"),
                "max_adverse_move_pct": row.get("max_adverse_move_pct"),
                "net_move_pct": row.get("net_move_pct"),
                "sync_reserve_ratio_change_pct": row.get("sync_reserve_ratio_change_pct"),
            }
            for row in evaluated_windows
        ],
    }
    preview_digest = _sync_liquidity_payload_digest(preview_digest_payload)
    blockers = list(dict.fromkeys([
        *(review.get("blockers") or []),
        *([] if review_ready else ["repaired_outcome_review_not_ready"]),
        *([] if evaluated_windows else ["no_repaired_outcome_windows_to_backtest"]),
        "negative_controls_missing",
        "multi_candidate_validation_missing",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    preview_ready = bool(review_ready and evaluated_windows)
    backtest_preview = {
        "mode": "shadow_preview_only_no_client_output",
        "entry_assumption": "source-backed detection snapshot existed before outcome windows",
        "window_count": len(evaluated_windows),
        "max_favorable_move_pct": max_favorable,
        "max_adverse_move_pct": max_adverse,
        "last_net_move_pct": last_net,
        "windows_with_positive_favorable_move": windows_with_positive_favorable,
        "windows_with_negative_net_move": windows_with_negative_net,
        "outcome_classification": outcome_classification if preview_ready else "blocked",
        "would_have_supported_long_client_signal": bool(preview_ready and outcome_classification == "promising_but_unvalidated"),
        "can_claim_detector_quality_now": False,
        "why_not_final": [
            "single token case only",
            "negative controls missing",
            "multi-candidate replay missing",
            "policy/risk gate missing",
            "client opt-in missing",
        ],
    }
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready_but_disabled" if preview_ready else "blocked",
        "chain": clean_chain,
        "pool_address": review.get("pool_address") or clean_pool or None,
        "token_address": review.get("token_address") or clean_token or None,
        "token_symbol": review.get("token_symbol"),
        "source_review": {
            "review_readiness": review.get("review_readiness"),
            "queue_status": review.get("queue_status"),
            "summary": review_summary,
        },
        "outcome_collection_status": outcome.get("collection_status"),
        "shadow_backtest_preview_digest": preview_digest,
        "evaluated_windows": evaluated_windows[:clean_limit],
        "backtest_preview": backtest_preview,
        "summary": {
            "repaired_outcome_rows_reviewed": review_summary.get("review_rows"),
            "ready_repaired_outcome_rows": review_summary.get("ready_rows"),
            "evaluated_windows": len(evaluated_windows),
            "shadow_backtest_preview_ready": preview_ready,
            "would_have_supported_long_client_signal": backtest_preview["would_have_supported_long_client_signal"],
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "negative_controls_and_multi_candidate_shadow_replay_read_only"
            if preview_ready else
            "repair_shadow_backtest_preview_blockers"
        ),
        "plain_summary_fr": (
            "La preview shadow backtest UFLOKI est calculable. Elle transforme la data reparee en mesure de resultat, "
            "mais elle ne valide pas encore un signal client: il manque les controles negatifs, plusieurs candidats et "
            "les gates de risque."
            if preview_ready else
            "La preview shadow backtest reste bloquee tant que les outcomes repares ne sont pas propres."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_shadow_replay_controls_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    min_swaps: int = 4,
) -> dict[str, Any]:
    """Read-only negative-control and multi-candidate shadow replay readiness preview."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    source_policy = (
        "admin-only read-only negative-control preview. It scans local swap tables for comparable pools and "
        "checks whether they can become controls for shadow replay. It does not persist control rows, run a "
        "multi-candidate backtest, create a score, create a client signal, create a mapping, execute a trade, "
        "create a wallet order or create an opt-in."
    )
    disabled = {
        "would_run_backtest": False,
        "would_persist_backtest": False,
        "would_create_negative_control_row": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "preview_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    source_preview = get_manipulation_detection_source_backed_shadow_backtest_preview(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=max(clean_limit, 4),
        dry_run=True,
    )
    source_pool = str(source_preview.get("pool_address") or clean_pool or "").strip().lower()
    source_ready = source_preview.get("preview_status") == "ready_but_disabled"
    blockers: list[str] = []
    candidate_rows: list[dict[str, Any]] = []
    local_swap_pool_count = 0
    swaps_table_exists = False
    pair_tokens_table_exists = False
    token_metadata_table_exists = False
    try:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        try:
            swaps_table_exists = _table_exists(conn, "swaps")
            pair_tokens_table_exists = _table_exists(conn, "pair_tokens")
            token_metadata_table_exists = _table_exists(conn, "token_metadata")
            if not swaps_table_exists:
                blockers.append("swaps_table_missing")
            else:
                local_swap_pool_count = int(conn.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT lower(pool) AS pool
                        FROM swaps
                        WHERE lower(chain) = ? AND pool IS NOT NULL AND pool != ''
                        GROUP BY lower(pool)
                    )
                    """,
                    (clean_chain,),
                ).fetchone()[0] or 0)
                rows = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT lower(chain) AS chain, lower(pool) AS pool, COALESCE(dex, '') AS dex,
                               COALESCE(token_identity_quality, '') AS token_identity_quality,
                               COALESCE(pair_rpc_source, '') AS pair_rpc_source,
                               COALESCE(venue_source, '') AS venue_source,
                               COALESCE(venue_confidence, 0) AS venue_confidence,
                               COUNT(*) AS swap_rows,
                               COUNT(DISTINCT tx_hash) AS distinct_tx_hashes,
                               COUNT(DISTINCT wallet) AS distinct_wallets,
                               MIN(block_number) AS first_block,
                               MAX(block_number) AS last_block,
                               SUM(COALESCE(amount_usd, 0)) AS amount_usd_sum,
                               GROUP_CONCAT(DISTINCT token_in) AS token_ins,
                               GROUP_CONCAT(DISTINCT token_out) AS token_outs
                        FROM swaps
                        WHERE lower(chain) = ? AND pool IS NOT NULL AND pool != ''
                              AND (? = '' OR lower(pool) != ?)
                        GROUP BY lower(chain), lower(pool)
                        ORDER BY swap_rows DESC, distinct_tx_hashes DESC, distinct_wallets DESC
                        LIMIT ?
                        """,
                        (clean_chain, source_pool, source_pool, max(clean_limit * 5, 25)),
                    ).fetchall()
                ]
                metadata_cache = _load_token_metadata_cache(conn) if token_metadata_table_exists else {}
                pair_token_rows = {}
                if pair_tokens_table_exists and rows:
                    pools = [str(row.get("pool") or "").lower() for row in rows if row.get("pool")]
                    placeholders = ",".join("?" for _ in pools)
                    if pools:
                        pair_token_rows = {
                            str(row["pool"] or "").lower(): dict(row)
                            for row in conn.execute(
                                f"""
                                SELECT lower(chain) AS chain, lower(pool) AS pool, lower(token0) AS token0,
                                       lower(token1) AS token1, rpc_source
                                FROM pair_tokens
                                WHERE lower(chain) = ? AND lower(pool) IN ({placeholders})
                                """,
                                tuple([clean_chain, *pools]),
                            ).fetchall()
                        }
                for row in rows:
                    pool = str(row.get("pool") or "").strip().lower()
                    token_addresses = []
                    pair_row = pair_token_rows.get(pool) or {}
                    if pair_row:
                        token_addresses = [str(pair_row.get("token0") or ""), str(pair_row.get("token1") or "")]
                    else:
                        token_addresses = [
                            token.strip().lower()
                            for token in (str(row.get("token_ins") or "") + "," + str(row.get("token_outs") or "")).split(",")
                            if token.strip()
                        ][:4]
                    token_symbols = []
                    for token in token_addresses[:4]:
                        meta = _token_metadata_for(clean_chain, token, metadata_cache) if metadata_cache else {}
                        token_symbols.append((meta.get("symbol") or token[:10]).upper())
                    swap_rows = int(row.get("swap_rows") or 0)
                    distinct_txs = int(row.get("distinct_tx_hashes") or 0)
                    distinct_wallets = int(row.get("distinct_wallets") or 0)
                    exact_direction = str(row.get("token_identity_quality") or "") == "exact_pair_log_direction"
                    venue_source = str(row.get("venue_source") or "")
                    dex_name = str(row.get("dex") or "")
                    route_source_backed = venue_source in {"source_backed_router_mapping", "known_router_address"} or (
                        "pancakeswap" in dex_name.lower() and "unknown" not in dex_name.lower()
                    )
                    has_activity = swap_rows >= safe_min_swaps and distinct_txs >= safe_min_swaps
                    if route_source_backed and exact_direction and has_activity:
                        control_status = "candidate_control_collectable"
                        row_blockers = ["control_repaired_outcome_dataset_missing"]
                    elif exact_direction and has_activity:
                        control_status = "route_repair_needed_before_control"
                        row_blockers = ["source_backed_route_missing", "control_repaired_outcome_dataset_missing"]
                    else:
                        control_status = "insufficient_for_control"
                        row_blockers = [
                            *([] if exact_direction else ["exact_pair_direction_missing"]),
                            *([] if has_activity else ["too_few_control_swaps"]),
                            "control_repaired_outcome_dataset_missing",
                        ]
                    candidate_rows.append({
                        "chain": clean_chain,
                        "pool_address": pool,
                        "dex": dex_name,
                        "token_identity_quality": row.get("token_identity_quality"),
                        "venue_source": venue_source,
                        "venue_confidence": row.get("venue_confidence"),
                        "pair_rpc_source": pair_row.get("rpc_source") or row.get("pair_rpc_source"),
                        "token_addresses": token_addresses[:4],
                        "token_symbols": token_symbols[:4],
                        "swap_rows": swap_rows,
                        "distinct_tx_hashes": distinct_txs,
                        "distinct_wallets": distinct_wallets,
                        "first_block": row.get("first_block"),
                        "last_block": row.get("last_block"),
                        "block_span": (
                            int(row.get("last_block") or 0) - int(row.get("first_block") or 0)
                            if row.get("first_block") is not None and row.get("last_block") is not None
                            else None
                        ),
                        "amount_usd_sum_research_only": row.get("amount_usd_sum"),
                        "route_source_backed": route_source_backed,
                        "exact_pair_direction": exact_direction,
                        "has_min_control_activity": has_activity,
                        "control_status": control_status,
                        "control_blockers": list(dict.fromkeys(row_blockers)),
                    })
        finally:
            conn.close()
    except Exception as exc:
        blockers.append(f"negative_control_query_error:{type(exc).__name__}")

    collectable = [row for row in candidate_rows if row.get("control_status") == "candidate_control_collectable"]
    route_repair_needed = [row for row in candidate_rows if row.get("control_status") == "route_repair_needed_before_control"]
    blockers = list(dict.fromkeys([
        *blockers,
        *([] if source_ready else ["source_shadow_backtest_preview_not_ready"]),
        *([] if candidate_rows else ["no_local_control_candidates_found"]),
        *([] if len(collectable) >= 3 else ["too_few_source_backed_control_candidates_min_3"]),
        "control_repaired_outcome_datasets_missing",
        "multi_candidate_replay_not_ready",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    replay_ready = bool(source_ready and len(collectable) >= 3)
    preview_digest = _sync_liquidity_payload_digest({
        "chain": clean_chain,
        "source_pool": source_pool,
        "source_preview_digest": source_preview.get("shadow_backtest_preview_digest"),
        "collectable_pools": [row.get("pool_address") for row in collectable[:clean_limit]],
        "min_swaps": safe_min_swaps,
    })
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready_but_disabled" if candidate_rows else "blocked",
        "chain": clean_chain,
        "source_case": {
            "pool_address": source_preview.get("pool_address") or clean_pool or None,
            "token_address": source_preview.get("token_address") or clean_token or None,
            "token_symbol": source_preview.get("token_symbol"),
            "shadow_backtest_preview_status": source_preview.get("preview_status"),
            "outcome_classification": (source_preview.get("backtest_preview") or {}).get("outcome_classification"),
            "would_have_supported_long_client_signal": (source_preview.get("backtest_preview") or {}).get("would_have_supported_long_client_signal"),
        },
        "control_scope": {
            "source": "local_swaps_table_research_only",
            "min_swaps": safe_min_swaps,
            "swaps_table_exists": swaps_table_exists,
            "pair_tokens_table_exists": pair_tokens_table_exists,
            "token_metadata_table_exists": token_metadata_table_exists,
            "local_swap_pool_count": local_swap_pool_count,
        },
        "negative_controls": candidate_rows[:clean_limit],
        "shadow_replay_preview_digest": preview_digest,
        "summary": {
            "local_control_candidates": len(candidate_rows),
            "candidate_control_collectable": len(collectable),
            "route_repair_needed": len(route_repair_needed),
            "negative_controls_ready_now": False,
            "multi_candidate_replay_ready_now": replay_ready and False,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "source_backed_control_outcome_collection_plan_read_only"
            if collectable else
            "route_source_repair_for_control_candidates_read_only"
        ),
        "plain_summary_fr": (
            "Core Equity trouve des candidats de controle locaux, mais ils ne sont pas encore au niveau source-backed "
            "UFLOKI. La prochaine etape est de reparer/prover leurs routes puis de collecter leurs outcomes, toujours "
            "sans signal ni trade."
            if candidate_rows else
            "Aucun controle local exploitable n'a ete trouve dans les tables actuelles."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_control_outcome_collection_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
) -> dict[str, Any]:
    """Read-only plan for collecting outcome windows on local negative-control candidates."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_controls = max(1, min(int(max_controls or 3), 10))
    source_policy = (
        "admin-only read-only control outcome collection plan. It uses local negative-control candidates and "
        "builds bounded future outcome windows. It does not call providers, persist control outcomes, create a "
        "score, create a mapping, emit a client signal, execute a trade, create a wallet order or create an opt-in."
    )
    disabled = {
        "would_call_provider": False,
        "would_collect_outcomes": False,
        "would_persist_control_outcome": False,
        "would_run_multi_candidate_replay": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    controls_preview = get_manipulation_detection_source_backed_shadow_replay_controls_preview(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
    )
    collectable_controls = [
        row for row in list(controls_preview.get("negative_controls") or [])
        if row.get("control_status") == "candidate_control_collectable"
    ][:safe_max_controls]
    block_offsets = {
        "plus_1h": 1200,
        "plus_6h": 7200,
        "plus_24h": 28800,
        "plus_72h": 86400,
    }
    planned_controls: list[dict[str, Any]] = []
    for control in collectable_controls:
        first_block = control.get("first_block")
        last_block = control.get("last_block")
        try:
            anchor_block = int(first_block)
        except (TypeError, ValueError):
            anchor_block = None
        try:
            observed_last_block = int(last_block)
        except (TypeError, ValueError):
            observed_last_block = None
        planned_windows = []
        for label, offset in block_offsets.items():
            expected_end = anchor_block + offset if anchor_block is not None else None
            local_coverage_status = (
                "local_swaps_cover_window"
                if expected_end is not None and observed_last_block is not None and observed_last_block >= expected_end
                else "needs_bounded_outcome_collection"
            )
            planned_windows.append({
                "window_label": label,
                "anchor_block": anchor_block,
                "expected_end_block": expected_end,
                "local_last_observed_block": observed_last_block,
                "local_coverage_status": local_coverage_status,
                "would_collect_now": False,
            })
        planned_controls.append({
            "chain": clean_chain,
            "pool_address": control.get("pool_address"),
            "dex": control.get("dex"),
            "token_symbols": control.get("token_symbols") or [],
            "token_addresses": control.get("token_addresses") or [],
            "swap_rows": control.get("swap_rows"),
            "distinct_tx_hashes": control.get("distinct_tx_hashes"),
            "distinct_wallets": control.get("distinct_wallets"),
            "route_source_backed": control.get("route_source_backed"),
            "exact_pair_direction": control.get("exact_pair_direction"),
            "control_status": control.get("control_status"),
            "outcome_collection_status": "planned_read_only",
            "planned_windows": planned_windows,
            "required_future_data": [
                "bounded raw Swap outcome rows for each planned window",
                "Sync reserve context for stale windows",
                "Mint/Burn liquidity context when present",
                "payload digest and dedupe per control/window",
                "review queue before multi-candidate replay",
            ],
        })

    plan_ready = bool(planned_controls)
    blockers = list(dict.fromkeys([
        *(controls_preview.get("blockers") or []),
        *([] if planned_controls else ["no_collectable_control_candidates"]),
        "control_outcomes_not_collected",
        "control_outcome_review_not_built",
        "multi_candidate_replay_not_ready",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    plan_digest = _sync_liquidity_payload_digest({
        "chain": clean_chain,
        "source_case": controls_preview.get("source_case"),
        "controls": [
            {
                "pool_address": row.get("pool_address"),
                "planned_windows": row.get("planned_windows"),
            }
            for row in planned_controls
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if plan_ready else "blocked",
        "chain": clean_chain,
        "source_case": controls_preview.get("source_case"),
        "control_source_preview": {
            "preview_status": controls_preview.get("preview_status"),
            "summary": controls_preview.get("summary"),
            "next_safe_step": controls_preview.get("next_safe_step"),
        },
        "control_outcome_plan_digest": plan_digest,
        "planned_control_count": len(planned_controls),
        "planned_controls": planned_controls,
        "window_policy": {
            "anchor": "first local swap block per control pool",
            "block_offsets": block_offsets,
            "provider_calls_allowed_now": False,
            "persistence_allowed_now": False,
        },
        "summary": {
            "collectable_controls_selected": len(planned_controls),
            "planned_outcome_windows": sum(len(row.get("planned_windows") or []) for row in planned_controls),
            "control_outcomes_ready_now": False,
            "multi_candidate_replay_ready_now": False,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "control_outcome_lookup_dry_run_read_only"
            if plan_ready else
            "repair_control_candidate_source_quality"
        ),
        "plain_summary_fr": (
            "Le plan de collecte outcome des controles est pret en lecture seule. Il selectionne les meilleurs "
            "controles locaux et prepare leurs fenetres, mais ne collecte rien et ne valide aucun signal."
            if plan_ready else
            "Aucun controle assez propre n'est disponible pour planifier des outcomes."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def run_manipulation_detection_source_backed_control_outcome_lookup_dry_run(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
) -> dict[str, Any]:
    """Read-only local outcome lookup for planned negative-control pools."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_controls = max(1, min(int(max_controls or 3), 10))
    source_policy = (
        "admin-only local-only control outcome lookup dry-run. It reads planned control pools from local swaps, "
        "computes in-memory outcome proxies and returns blockers. It does not call providers, persist outcomes, "
        "create scores, mappings, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_call_provider": False,
        "would_persist_control_outcome": False,
        "would_run_multi_candidate_replay": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    plan = get_manipulation_detection_source_backed_control_outcome_collection_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_controls=safe_max_controls,
    )
    quote_priority = [
        "0x55d398326f99059ff775485246999027b3197955",  # BSC USDT
        "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB
        "0xe9e7cea3dedca5984780bafc599bd69add087d56",  # BUSD
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
        "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3",  # DAI
    ]

    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _pct_change(start: float | None, end: float | None) -> float | None:
        if start in (None, 0) or end is None:
            return None
        return round(((end - start) / start) * 100, 4)

    def _price_from_swap(row: dict[str, Any], target: str, quote: str) -> float | None:
        token_in = str(row.get("token_in") or "").strip().lower()
        token_out = str(row.get("token_out") or "").strip().lower()
        amount_in = _float_or_none(row.get("amount_in"))
        amount_out = _float_or_none(row.get("amount_out"))
        if not target or not quote or amount_in in (None, 0) or amount_out in (None, 0):
            return None
        if token_in == quote and token_out == target:
            return amount_in / amount_out
        if token_in == target and token_out == quote:
            return amount_out / amount_in
        return None

    blockers = list(plan.get("blockers") or [])
    controls = list(plan.get("planned_controls") or [])
    assessed_controls: list[dict[str, Any]] = []
    lookup_errors: list[str] = []
    try:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        try:
            if not _table_exists(conn, "swaps"):
                blockers.append("swaps_table_missing")
            for control in controls:
                pool = str(control.get("pool_address") or "").strip().lower()
                token_addresses = [
                    str(token or "").strip().lower()
                    for token in list(control.get("token_addresses") or [])
                    if str(token or "").strip()
                ]
                quote = next((token for token in quote_priority if token in token_addresses), token_addresses[0] if token_addresses else "")
                target = next((token for token in token_addresses if token != quote), token_addresses[-1] if token_addresses else "")
                assessed_windows = []
                for window in list(control.get("planned_windows") or []):
                    anchor_block = window.get("anchor_block")
                    expected_end = window.get("expected_end_block")
                    try:
                        start_block = int(anchor_block)
                        end_block = int(expected_end)
                    except (TypeError, ValueError):
                        assessed_windows.append({
                            **window,
                            "lookup_status": "blocked",
                            "lookup_blockers": ["invalid_control_window_blocks"],
                        })
                        continue
                    rows = [
                        dict(row)
                        for row in conn.execute(
                            """
                            SELECT tx_hash, block_number, timestamp, wallet, token_in, token_out,
                                   amount_in, amount_out, amount_usd
                            FROM swaps
                            WHERE lower(chain) = ? AND lower(pool) = ?
                                  AND block_number >= ? AND block_number <= ?
                            ORDER BY block_number ASC, timestamp ASC, tx_hash ASC
                            LIMIT 500
                            """,
                            (clean_chain, pool, start_block, end_block),
                        ).fetchall()
                    ]
                    prices = [
                        price for price in (_price_from_swap(row, target, quote) for row in rows)
                        if price is not None and price > 0
                    ]
                    price_start = prices[0] if prices else None
                    price_end = prices[-1] if prices else None
                    price_high = max(prices) if prices else None
                    price_low = min(prices) if prices else None
                    max_favorable = _pct_change(price_start, price_high)
                    max_adverse = _pct_change(price_start, price_low)
                    net_move = _pct_change(price_start, price_end)
                    row_count = len(rows)
                    distinct_txs = len({str(row.get("tx_hash") or "") for row in rows if row.get("tx_hash")})
                    distinct_wallets = len({str(row.get("wallet") or "") for row in rows if row.get("wallet")})
                    first_block = min((int(row.get("block_number") or 0) for row in rows), default=None)
                    last_block = max((int(row.get("block_number") or 0) for row in rows), default=None)
                    lookup_blockers = [
                        *([] if row_count else ["no_local_swaps_in_control_window"]),
                        *([] if len(prices) >= 2 else ["too_few_price_proxy_points_min_2"]),
                    ]
                    assessed_windows.append({
                        **window,
                        "quote_token": quote or None,
                        "target_token": target or None,
                        "lookup_status": "local_proxy_ready" if not lookup_blockers else "blocked",
                        "local_swap_rows": row_count,
                        "distinct_tx_hashes": distinct_txs,
                        "distinct_wallets": distinct_wallets,
                        "first_observed_block": first_block,
                        "last_observed_block": last_block,
                        "amount_usd_sum_research_only": round(sum(_float_or_none(row.get("amount_usd")) or 0 for row in rows), 8),
                        "price_proxy_points": len(prices),
                        "price_start": price_start,
                        "price_high": price_high,
                        "price_low": price_low,
                        "price_end": price_end,
                        "max_favorable_move_pct": max_favorable,
                        "max_adverse_move_pct": max_adverse,
                        "net_move_pct": net_move,
                        "lookup_blockers": lookup_blockers,
                        "would_persist_control_outcome": False,
                    })
                ready_windows = len([row for row in assessed_windows if row.get("lookup_status") == "local_proxy_ready"])
                assessed_controls.append({
                    **control,
                    "quote_token": quote or None,
                    "target_token": target or None,
                    "lookup_status": "local_outcome_proxy_ready" if ready_windows else "blocked",
                    "ready_windows": ready_windows,
                    "blocked_windows": len(assessed_windows) - ready_windows,
                    "assessed_windows": assessed_windows,
                })
        finally:
            conn.close()
    except Exception as exc:
        lookup_errors.append(f"control_outcome_lookup_error:{type(exc).__name__}")

    ready_controls = [control for control in assessed_controls if control.get("ready_windows")]
    ready_windows_total = sum(int(control.get("ready_windows") or 0) for control in assessed_controls)
    blocked_windows_total = sum(int(control.get("blocked_windows") or 0) for control in assessed_controls)
    blockers = list(dict.fromkeys([
        *blockers,
        *lookup_errors,
        *([] if controls else ["no_planned_controls"]),
        *([] if ready_windows_total else ["no_control_outcome_windows_ready"]),
        "control_outcome_persistence_schema_missing",
        "control_outcome_review_not_built",
        "multi_candidate_replay_not_ready",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    lookup_digest = _sync_liquidity_payload_digest({
        "chain": clean_chain,
        "plan_digest": plan.get("control_outcome_plan_digest"),
        "controls": [
            {
                "pool_address": control.get("pool_address"),
                "ready_windows": control.get("ready_windows"),
                "windows": [
                    {
                        "window_label": window.get("window_label"),
                        "local_swap_rows": window.get("local_swap_rows"),
                        "price_proxy_points": window.get("price_proxy_points"),
                        "net_move_pct": window.get("net_move_pct"),
                    }
                    for window in list(control.get("assessed_windows") or [])
                ],
            }
            for control in assessed_controls
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "lookup_status": "ready_but_disabled" if ready_windows_total else "blocked",
        "chain": clean_chain,
        "control_outcome_plan_digest": plan.get("control_outcome_plan_digest"),
        "control_outcome_lookup_digest": lookup_digest,
        "source_case": plan.get("source_case"),
        "planned_control_count": len(controls),
        "assessed_control_count": len(assessed_controls),
        "assessed_controls": assessed_controls[:safe_max_controls],
        "summary": {
            "assessed_controls": len(assessed_controls),
            "controls_with_ready_windows": len(ready_controls),
            "ready_control_windows": ready_windows_total,
            "blocked_control_windows": blocked_windows_total,
            "control_outcomes_lookup_ready_now": bool(ready_windows_total),
            "control_outcomes_ready_now": False,
            "control_outcomes_persisted": False,
            "multi_candidate_replay_ready_now": False,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "control_outcome_persistence_schema_plan_read_only"
            if ready_windows_total else
            "repair_control_outcome_lookup_blockers"
        ),
        "plain_summary_fr": (
            "Les outcomes de controle sont mesurables localement en dry-run. Ils ne sont pas persistes et ne peuvent "
            "pas encore valider le detecteur tant qu'il manque schema/review et replay multi-candidat."
            if ready_windows_total else
            "Les outcomes de controle ne sont pas encore mesurables avec les donnees locales actuelles."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_control_outcome_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
) -> dict[str, Any]:
    """Read-only schema-plan for future persisted negative-control outcome windows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_controls = max(1, min(int(max_controls or 3), 10))
    target_table = "manipulation_control_outcome_windows"
    source_policy = (
        "admin-only read-only schema-plan for future negative-control outcome windows. It plans storage for "
        "reviewed local control outcomes only; it creates no table, persists no control outcome, creates no "
        "score, mapping, client signal, trade, wallet order or opt-in."
    )
    disabled = {
        "would_create_table": False,
        "would_insert_control_outcome": False,
        "would_persist_control_outcome": False,
        "would_run_multi_candidate_replay": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "target_table": target_table,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    lookup = run_manipulation_detection_source_backed_control_outcome_lookup_dry_run(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_controls=safe_max_controls,
    )
    ready_window_previews: list[dict[str, Any]] = []
    for control in list(lookup.get("assessed_controls") or []):
        for window in list(control.get("assessed_windows") or []):
            if window.get("lookup_status") != "local_proxy_ready":
                continue
            payload = {
                "chain": clean_chain,
                "source_case": lookup.get("source_case"),
                "control_pool_address": control.get("pool_address"),
                "control_dex": control.get("dex"),
                "token_symbols": control.get("token_symbols") or [],
                "token_addresses": control.get("token_addresses") or [],
                "quote_token": control.get("quote_token"),
                "target_token": control.get("target_token"),
                "window": window,
                "lookup_digest": lookup.get("control_outcome_lookup_digest"),
            }
            dedupe_key = "|".join(str(item or "") for item in [
                clean_chain,
                control.get("pool_address"),
                window.get("window_label"),
                window.get("anchor_block"),
                window.get("expected_end_block"),
                lookup.get("control_outcome_lookup_digest"),
            ])
            ready_window_previews.append({
                "chain": clean_chain,
                "control_pool_address": control.get("pool_address"),
                "control_dex": control.get("dex"),
                "token_symbols": control.get("token_symbols") or [],
                "token_addresses": control.get("token_addresses") or [],
                "quote_token": control.get("quote_token"),
                "target_token": control.get("target_token"),
                "outcome_window_label": window.get("window_label"),
                "anchor_block": window.get("anchor_block"),
                "expected_end_block": window.get("expected_end_block"),
                "local_swap_rows": window.get("local_swap_rows"),
                "price_proxy_points": window.get("price_proxy_points"),
                "max_favorable_move_pct": window.get("max_favorable_move_pct"),
                "max_adverse_move_pct": window.get("max_adverse_move_pct"),
                "net_move_pct": window.get("net_move_pct"),
                "control_outcome_payload_json": _sync_liquidity_canonical_json(payload),
                "control_outcome_digest": _sync_liquidity_payload_digest(payload),
                "control_outcome_dedupe_key": dedupe_key,
                "status": "pending_control_outcome_review",
            })

    table_exists = False
    try:
        conn = _get_db()
        try:
            table_exists = _table_exists(conn, target_table)
        finally:
            conn.close()
    except Exception:
        table_exists = False

    schema_preview = [
        {"name": "id", "type": "INTEGER PRIMARY KEY AUTOINCREMENT"},
        {"name": "chain", "type": "TEXT NOT NULL"},
        {"name": "source_case_pool_address", "type": "TEXT"},
        {"name": "source_case_token_symbol", "type": "TEXT"},
        {"name": "control_pool_address", "type": "TEXT NOT NULL"},
        {"name": "control_dex", "type": "TEXT"},
        {"name": "token_symbols_json", "type": "TEXT NOT NULL"},
        {"name": "token_addresses_json", "type": "TEXT NOT NULL"},
        {"name": "quote_token", "type": "TEXT"},
        {"name": "target_token", "type": "TEXT"},
        {"name": "outcome_window_label", "type": "TEXT NOT NULL"},
        {"name": "anchor_block", "type": "INTEGER"},
        {"name": "expected_end_block", "type": "INTEGER"},
        {"name": "local_swap_rows", "type": "INTEGER NOT NULL"},
        {"name": "price_proxy_points", "type": "INTEGER NOT NULL"},
        {"name": "max_favorable_move_pct", "type": "REAL"},
        {"name": "max_adverse_move_pct", "type": "REAL"},
        {"name": "net_move_pct", "type": "REAL"},
        {"name": "control_outcome_payload_json", "type": "TEXT NOT NULL"},
        {"name": "control_outcome_digest", "type": "TEXT NOT NULL"},
        {"name": "control_outcome_dedupe_key", "type": "TEXT NOT NULL UNIQUE"},
        {"name": "status", "type": "TEXT NOT NULL DEFAULT 'pending_control_outcome_review'"},
        {"name": "created_at", "type": "TEXT NOT NULL"},
        {"name": "source_policy", "type": "TEXT NOT NULL"},
    ]
    indexes_preview = [
        "UNIQUE(control_outcome_dedupe_key)",
        "INDEX(chain, control_pool_address)",
        "INDEX(outcome_window_label)",
        "INDEX(status)",
        "INDEX(control_outcome_digest)",
    ]
    constraints_preview = [
        "status in pending_control_outcome_review, accepted_for_multi_candidate_replay, needs_better_source, rejected",
        "no overwrite",
        "no upsert",
        "duplicate control_outcome_dedupe_key blocks future insert",
        "control outcomes are inputs for shadow replay only, not client signals",
    ]
    blockers = list(dict.fromkeys([
        *(lookup.get("blockers") or []),
        *([] if ready_window_previews else ["no_ready_control_outcome_windows_to_plan"]),
        "ddl_not_confirmed",
        "control_outcomes_not_persisted",
        "control_outcome_review_not_built",
        "multi_candidate_replay_not_ready",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready" if ready_window_previews else "blocked",
        "chain": clean_chain,
        "target_table": target_table,
        "table_exists": table_exists,
        "migration_required": not table_exists,
        "schema_preview": schema_preview,
        "indexes_preview": indexes_preview,
        "constraints_preview": constraints_preview,
        "dedupe_constraints": {
            "control_outcome_dedupe_key_formula": "chain|control_pool_address|window_label|anchor_block|expected_end_block|control_outcome_lookup_digest",
            "no_overwrite": True,
            "no_upsert": True,
        },
        "source_lookup": {
            "lookup_status": lookup.get("lookup_status"),
            "control_outcome_lookup_digest": lookup.get("control_outcome_lookup_digest"),
            "summary": lookup.get("summary"),
        },
        "planned_control_outcome_rows": len(ready_window_previews),
        "planned_rows_preview": ready_window_previews[:clean_limit],
        "summary": {
            "ready_control_outcome_rows": len(ready_window_previews),
            "control_outcomes_persisted": False,
            "multi_candidate_replay_ready_now": False,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "confirmed_empty_ddl_migration_for_control_outcome_windows"
            if ready_window_previews and not table_exists else
            "control_outcome_insert_dry_run_first"
            if ready_window_previews else
            "repair_control_outcome_lookup_blockers"
        ),
        "plain_summary_fr": (
            "Le schema des outcomes de controle est pret en lecture seule. Il prepare la boite pour stocker plus tard "
            "les fenetres mesurables, sans creer la table ni valider un signal."
            if ready_window_previews else
            "Aucune fenetre de controle assez propre n'est disponible pour planifier le schema."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def create_manipulation_detection_source_backed_control_outcome_table(
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Confirmed DDL-only creation of the negative-control outcome table."""
    clean_chain = _normalize_chain(chain or "bsc")
    target_table = "manipulation_control_outcome_windows"
    required_confirm = "CREATE_MANIPULATION_CONTROL_OUTCOME_WINDOWS"
    source_policy = (
        "admin-confirmed DDL-only control outcome migration. It creates only the empty "
        "manipulation_control_outcome_windows table and indexes if absent; it inserts zero control outcome rows, "
        "runs no replay, persists no score, creates no mapping, emits no client signal, executes no trade "
        "and creates no opt-in."
    )
    disabled = {
        "would_insert_control_outcome": False,
        "would_persist_control_outcome": False,
        "would_run_multi_candidate_replay": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_policy": source_policy,
    }

    plan = get_manipulation_detection_source_backed_control_outcome_schema_plan(
        chain=clean_chain,
        dry_run=True,
        limit=10,
        min_swaps=4,
        max_controls=3,
    )
    blockers: list[str] = []
    allowed_plan_blockers = {
        "control_repaired_outcome_datasets_missing",
        "control_outcomes_not_collected",
        "control_outcome_persistence_schema_missing",
        "ddl_not_confirmed",
        "control_outcomes_not_persisted",
        "control_outcome_review_not_built",
        "multi_candidate_replay_not_ready",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    }
    plan_blockers = set(plan.get("blockers") or [])
    if plan.get("target_table") != target_table:
        blockers.append("control_outcome_schema_plan_target_mismatch")
    if plan.get("plan_status") != "ready":
        blockers.append("control_outcome_schema_plan_not_ready")
    if plan_blockers and not plan_blockers.issubset(allowed_plan_blockers):
        blockers.append("control_outcome_schema_plan_blocked_unexpectedly")
    if not dry_run and confirm != required_confirm:
        blockers.append("confirm_CREATE_MANIPULATION_CONTROL_OUTCOME_WINDOWS_required")

    expected_columns = [
        "id",
        "chain",
        "source_case_pool_address",
        "source_case_token_symbol",
        "control_pool_address",
        "control_dex",
        "token_symbols_json",
        "token_addresses_json",
        "quote_token",
        "target_token",
        "outcome_window_label",
        "anchor_block",
        "expected_end_block",
        "local_swap_rows",
        "price_proxy_points",
        "max_favorable_move_pct",
        "max_adverse_move_pct",
        "net_move_pct",
        "control_outcome_payload_json",
        "control_outcome_digest",
        "control_outcome_dedupe_key",
        "status",
        "created_at",
        "source_policy",
    ]
    index_sql = [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_manipulation_control_outcome_dedupe ON manipulation_control_outcome_windows(control_outcome_dedupe_key)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_control_outcome_chain_pool ON manipulation_control_outcome_windows(chain, control_pool_address)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_control_outcome_window ON manipulation_control_outcome_windows(outcome_window_label)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_control_outcome_status ON manipulation_control_outcome_windows(status)",
        "CREATE INDEX IF NOT EXISTS idx_manipulation_control_outcome_digest ON manipulation_control_outcome_windows(control_outcome_digest)",
    ]

    conn = _get_db()
    try:
        table_exists = _table_exists(conn, target_table)
        row_count = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0) if table_exists else 0
        if table_exists:
            existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({target_table})").fetchall()}
            if any(column not in existing_columns for column in expected_columns):
                blockers.append("manipulation_control_outcome_windows_schema_drift_detected")
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
            "would_create_table": bool(migration_required and not blockers),
            "table_created": False,
            "indexes_created": [],
            "rows_inserted": 0,
            "row_count": row_count,
            "planned_control_outcome_rows": plan.get("planned_control_outcome_rows"),
            "control_outcome_lookup_digest": (plan.get("source_lookup") or {}).get("control_outcome_lookup_digest"),
            "can_detect_reliable_manipulation_now": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": blockers,
            **disabled,
        }

    conn = _get_db()
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
            CREATE TABLE IF NOT EXISTS manipulation_control_outcome_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                source_case_pool_address TEXT,
                source_case_token_symbol TEXT,
                control_pool_address TEXT NOT NULL,
                control_dex TEXT,
                token_symbols_json TEXT NOT NULL,
                token_addresses_json TEXT NOT NULL,
                quote_token TEXT,
                target_token TEXT,
                outcome_window_label TEXT NOT NULL,
                anchor_block INTEGER,
                expected_end_block INTEGER,
                local_swap_rows INTEGER NOT NULL,
                price_proxy_points INTEGER NOT NULL,
                max_favorable_move_pct REAL,
                max_adverse_move_pct REAL,
                net_move_pct REAL,
                control_outcome_payload_json TEXT NOT NULL,
                control_outcome_digest TEXT NOT NULL,
                control_outcome_dedupe_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending_control_outcome_review',
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
        "would_create_table": False,
        "table_created": table_created,
        "indexes_created": created_indexes,
        "rows_inserted": 0,
        "row_count": row_count,
        "planned_control_outcome_rows": plan.get("planned_control_outcome_rows"),
        "control_outcome_lookup_digest": (plan.get("source_lookup") or {}).get("control_outcome_lookup_digest"),
        "can_detect_reliable_manipulation_now": False,
        "would_write": False,
        "real_write_enabled": bool(table_created or created_indexes),
        "writes_performed": (1 if table_created else 0) + len(created_indexes),
        "blockers": [],
        **disabled,
    }


def insert_manipulation_detection_source_backed_control_outcome_windows(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    confirm: str | None = None,
    expected_control_outcome_lookup_digest: str | None = None,
    min_swaps: int = 4,
    max_controls: int = 3,
) -> dict[str, Any]:
    """Dry-run-first insert lane for source-backed negative-control outcome windows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_controls = max(1, min(int(max_controls or 3), 10))
    target_table = "manipulation_control_outcome_windows"
    required_confirm = "INSERT_MANIPULATION_CONTROL_OUTCOME_WINDOWS"
    source_policy = (
        "admin-confirmed dry-run-first control outcome insert. It inserts only locally measured negative-control "
        "outcome windows into manipulation_control_outcome_windows after lookup digest confirmation. It does not run "
        "multi-candidate replay, persist a score, create a mapping, emit a client signal, execute a trade or create an opt-in."
    )
    disabled = {
        "would_run_multi_candidate_replay": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_policy": source_policy,
    }

    plan = get_manipulation_detection_source_backed_control_outcome_schema_plan(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_controls=safe_max_controls,
    )
    lookup_digest = str((plan.get("source_lookup") or {}).get("control_outcome_lookup_digest") or "").strip()
    candidate_rows: list[dict[str, Any]] = []
    for row in list(plan.get("planned_rows_preview") or []):
        payload: dict[str, Any] = {}
        try:
            payload = json.loads(str(row.get("control_outcome_payload_json") or "{}"))
        except Exception:
            payload = {}
        source_case = payload.get("source_case") if isinstance(payload.get("source_case"), dict) else {}
        candidate_rows.append({
            "chain": clean_chain,
            "source_case_pool_address": source_case.get("pool_address"),
            "source_case_token_symbol": source_case.get("token_symbol"),
            "control_pool_address": row.get("control_pool_address"),
            "control_dex": row.get("control_dex"),
            "token_symbols_json": _sync_liquidity_canonical_json(row.get("token_symbols") or []),
            "token_addresses_json": _sync_liquidity_canonical_json(row.get("token_addresses") or []),
            "quote_token": row.get("quote_token"),
            "target_token": row.get("target_token"),
            "outcome_window_label": row.get("outcome_window_label"),
            "anchor_block": row.get("anchor_block"),
            "expected_end_block": row.get("expected_end_block"),
            "local_swap_rows": int(row.get("local_swap_rows") or 0),
            "price_proxy_points": int(row.get("price_proxy_points") or 0),
            "max_favorable_move_pct": row.get("max_favorable_move_pct"),
            "max_adverse_move_pct": row.get("max_adverse_move_pct"),
            "net_move_pct": row.get("net_move_pct"),
            "control_outcome_payload_json": row.get("control_outcome_payload_json"),
            "control_outcome_digest": row.get("control_outcome_digest"),
            "control_outcome_dedupe_key": row.get("control_outcome_dedupe_key"),
            "status": "pending_control_outcome_review",
        })

    blockers = list(dict.fromkeys([
        *(plan.get("blockers") or []),
        *([] if plan.get("plan_status") == "ready" else ["control_outcome_schema_plan_not_ready"]),
        *([] if plan.get("table_exists") else ["manipulation_control_outcome_windows_missing"]),
        *([] if lookup_digest else ["control_outcome_lookup_digest_missing"]),
        *([] if candidate_rows else ["no_control_outcome_rows_to_insert"]),
    ]))
    allowed_plan_blockers = {
        "control_repaired_outcome_datasets_missing",
        "control_outcomes_not_collected",
        "control_outcome_persistence_schema_missing",
        "ddl_not_confirmed",
        "control_outcomes_not_persisted",
        "control_outcome_review_not_built",
        "multi_candidate_replay_not_ready",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    }
    blockers = [blocker for blocker in blockers if blocker not in allowed_plan_blockers]
    if not dry_run:
        if confirm != required_confirm:
            blockers.append("confirm_INSERT_MANIPULATION_CONTROL_OUTCOME_WINDOWS_required")
        if not expected_control_outcome_lookup_digest:
            blockers.append("expected_control_outcome_lookup_digest_required")
        elif str(expected_control_outcome_lookup_digest or "").strip() != lookup_digest:
            blockers.append("expected_control_outcome_lookup_digest_mismatch")

    existing_duplicate_keys: set[str] = set()
    table_count_before: int | None = None
    conn = _get_db()
    try:
        if not _table_exists(conn, target_table):
            table_count_before = None
        else:
            table_count_before = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
            keys = [str(row.get("control_outcome_dedupe_key") or "") for row in candidate_rows if row.get("control_outcome_dedupe_key")]
            if keys:
                placeholders = ",".join("?" for _ in keys)
                for (existing_key,) in conn.execute(
                    f"SELECT control_outcome_dedupe_key FROM {target_table} WHERE control_outcome_dedupe_key IN ({placeholders})",
                    keys,
                ).fetchall():
                    existing_duplicate_keys.add(str(existing_key))
    finally:
        conn.close()
    duplicate_existing_count = len(existing_duplicate_keys)
    insertable_rows = [
        row for row in candidate_rows
        if str(row.get("control_outcome_dedupe_key") or "") not in existing_duplicate_keys
    ]
    if candidate_rows and not insertable_rows and duplicate_existing_count:
        blockers.append("duplicate_control_outcome_rows_exist")
    blockers = list(dict.fromkeys(blockers))

    if dry_run or blockers:
        return {
            "ok": not blockers,
            "dry_run": bool(dry_run),
            "insert_status": "ready_for_insert" if not blockers else "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "table_exists": bool(plan.get("table_exists")),
            "control_outcome_lookup_digest": lookup_digest or None,
            "expected_control_outcome_lookup_digest_required_for_real_insert": lookup_digest or None,
            "candidate_control_outcome_rows": len(candidate_rows),
            "duplicate_existing_count": duplicate_existing_count,
            "would_insert_control_outcome_rows": len(insertable_rows) if not blockers else 0,
            "would_insert_control_outcome": bool(insertable_rows and not blockers),
            "inserted_control_outcome_rows": 0,
            "inserted": False,
            "table_count_before": table_count_before,
            "preview_rows": [
                {
                    "control_pool_address": row.get("control_pool_address"),
                    "control_dex": row.get("control_dex"),
                    "outcome_window_label": row.get("outcome_window_label"),
                    "control_outcome_dedupe_key": row.get("control_outcome_dedupe_key"),
                    "control_outcome_digest": row.get("control_outcome_digest"),
                    "row_status": "duplicate_existing"
                    if row.get("control_outcome_dedupe_key") in existing_duplicate_keys
                    else "insertable",
                }
                for row in candidate_rows[:clean_limit]
            ],
            "blockers": blockers,
            "can_detect_reliable_manipulation_now": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            **disabled,
        }

    created_at = datetime.now(timezone.utc).isoformat()
    columns = [
        "chain",
        "source_case_pool_address",
        "source_case_token_symbol",
        "control_pool_address",
        "control_dex",
        "token_symbols_json",
        "token_addresses_json",
        "quote_token",
        "target_token",
        "outcome_window_label",
        "anchor_block",
        "expected_end_block",
        "local_swap_rows",
        "price_proxy_points",
        "max_favorable_move_pct",
        "max_adverse_move_pct",
        "net_move_pct",
        "control_outcome_payload_json",
        "control_outcome_digest",
        "control_outcome_dedupe_key",
        "status",
        "created_at",
        "source_policy",
    ]

    def _values(row: dict[str, Any]) -> tuple[Any, ...]:
        payload = dict(row)
        payload["created_at"] = created_at
        payload["source_policy"] = source_policy
        return tuple(payload.get(column) for column in columns)

    conn = _get_db()
    try:
        placeholders = ",".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO {target_table} ({','.join(columns)}) VALUES ({placeholders})",
            [_values(row) for row in insertable_rows],
        )
        conn.commit()
        table_count_after = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
    finally:
        conn.close()

    inserted_count = len(insertable_rows)
    return {
        "ok": True,
        "dry_run": False,
        "insert_status": "inserted" if inserted_count else "blocked",
        "chain": clean_chain,
        "target_table": target_table,
        "control_outcome_lookup_digest": lookup_digest or None,
        "candidate_control_outcome_rows": len(candidate_rows),
        "duplicate_existing_count": duplicate_existing_count,
        "inserted_control_outcome_rows": inserted_count,
        "inserted": bool(inserted_count),
        "table_count_before": table_count_before,
        "table_count_after": table_count_after,
        "blockers": [],
        "can_detect_reliable_manipulation_now": False,
        "would_insert_control_outcome": False,
        "would_insert_control_outcome_rows": 0,
        "would_write": False,
        "real_write_enabled": bool(inserted_count),
        "writes_performed": inserted_count,
        **disabled,
    }


def get_manipulation_detection_source_backed_control_outcome_review_queue(
    chain: str | None = "bsc",
    status: str | None = "pending_control_outcome_review",
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
) -> dict[str, Any]:
    """Read-only review queue for persisted negative-control outcome windows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_status = str(status or "").strip()
    status_filter = "" if clean_status.lower() == "all" else clean_status
    clean_limit = max(1, min(int(limit or 50), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_controls = max(1, min(int(max_controls or 3), 10))
    target_table = "manipulation_control_outcome_windows"
    source_policy = (
        "admin-only read-only control outcome review queue. It validates persisted negative-control windows "
        "against current lookup digest, payload digest, dedupe key, status and local outcome quality. It does not "
        "update status, run multi-candidate replay, persist a score, create a mapping, emit a client signal, "
        "execute a trade or create an opt-in."
    )
    disabled = {
        "would_update_status": False,
        "would_run_multi_candidate_replay": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "queue_status": "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    schema_plan = get_manipulation_detection_source_backed_control_outcome_schema_plan(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_controls=safe_max_controls,
    )
    lookup_digest = str((schema_plan.get("source_lookup") or {}).get("control_outcome_lookup_digest") or "").strip()
    expected_by_dedupe = {
        str(row.get("control_outcome_dedupe_key") or ""): row
        for row in list(schema_plan.get("planned_rows_preview") or [])
        if row.get("control_outcome_dedupe_key")
    }
    blockers: list[str] = []
    table_exists = False
    row_count_total = 0
    duplicate_dedupe_count = 0
    rows: list[dict[str, Any]] = []
    try:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        try:
            table_exists = _table_exists(conn, target_table)
            if not table_exists:
                blockers.append("manipulation_control_outcome_windows_missing")
            else:
                row_count_total = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
                duplicate_dedupe_count = int(conn.execute(
                    f"""
                    SELECT COUNT(*) FROM (
                        SELECT control_outcome_dedupe_key
                        FROM {target_table}
                        GROUP BY control_outcome_dedupe_key
                        HAVING COUNT(*) > 1
                    )
                    """
                ).fetchone()[0] or 0)
                params: list[Any] = [clean_chain]
                where = ["lower(chain) = ?"]
                if status_filter:
                    where.append("status = ?")
                    params.append(status_filter)
                rows = [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT id, chain, source_case_pool_address, source_case_token_symbol,
                               control_pool_address, control_dex, token_symbols_json, token_addresses_json,
                               quote_token, target_token, outcome_window_label, anchor_block,
                               expected_end_block, local_swap_rows, price_proxy_points,
                               max_favorable_move_pct, max_adverse_move_pct, net_move_pct,
                               control_outcome_payload_json, control_outcome_digest,
                               control_outcome_dedupe_key, status, created_at, source_policy
                        FROM {target_table}
                        WHERE {' AND '.join(where)}
                        ORDER BY control_pool_address ASC, outcome_window_label ASC, id ASC
                        LIMIT ?
                        """,
                        tuple([*params, clean_limit]),
                    ).fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        blockers.append(f"control_outcome_review_query_error:{type(exc).__name__}")

    def _row_payload(row: dict[str, Any]) -> dict[str, Any] | None:
        try:
            payload = json.loads(str(row.get("control_outcome_payload_json") or ""))
            return payload if isinstance(payload, dict) else None
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    assessed_rows: list[dict[str, Any]] = []
    for row in rows:
        payload = _row_payload(row)
        payload_digest_bound = bool(payload) and _sync_liquidity_payload_digest(payload) == str(row.get("control_outcome_digest") or "")
        row_chain = str(row.get("chain") or "").strip().lower()
        row_pool = str(row.get("control_pool_address") or "").strip().lower()
        row_window = str(row.get("outcome_window_label") or "").strip()
        dedupe_expected = "|".join(str(item or "") for item in [
            row_chain,
            row_pool,
            row_window,
            row.get("anchor_block"),
            row.get("expected_end_block"),
            lookup_digest,
        ])
        current_plan_row = expected_by_dedupe.get(str(row.get("control_outcome_dedupe_key") or ""))
        dedupe_bound = str(row.get("control_outcome_dedupe_key") or "") == dedupe_expected
        current_plan_bound = bool(current_plan_row)
        route_bound = row_chain == clean_chain and bool(row_pool)
        status_bound = str(row.get("status") or "") == status_filter if status_filter else True
        local_quality_bound = int(row.get("local_swap_rows") or 0) > 0 and int(row.get("price_proxy_points") or 0) > 1
        lookup_digest_bound = bool(lookup_digest) and str(row.get("control_outcome_dedupe_key") or "").endswith(lookup_digest)
        row_blockers = [
            *([] if payload else ["control_outcome_payload_json_invalid"]),
            *([] if payload_digest_bound else ["control_outcome_digest_drift"]),
            *([] if current_plan_bound else ["control_outcome_not_in_current_plan"]),
            *([] if dedupe_bound else ["control_outcome_dedupe_key_drift"]),
            *([] if lookup_digest_bound else ["control_outcome_lookup_digest_drift"]),
            *([] if route_bound else ["route_drift"]),
            *([] if status_bound else ["status_filter_mismatch"]),
            *([] if local_quality_bound else ["local_outcome_quality_too_weak"]),
        ]
        assessed_rows.append({
            **row,
            "payload_json_valid": bool(payload),
            "payload_digest_bound": payload_digest_bound,
            "current_plan_bound": current_plan_bound,
            "route_bound": route_bound,
            "dedupe_bound": dedupe_bound,
            "lookup_digest_bound": lookup_digest_bound,
            "status_bound": status_bound,
            "local_quality_bound": local_quality_bound,
            "review_blockers": row_blockers,
        })

    invalid_rows = [row for row in assessed_rows if row.get("review_blockers")]
    if not rows:
        blockers.append("no_control_outcome_rows_for_review")
    if duplicate_dedupe_count:
        blockers.append("duplicate_control_outcome_dedupe_keys")
    if invalid_rows:
        blockers.append("control_outcome_binding_drift")
    blockers = list(dict.fromkeys(blockers))
    ready_rows = [row for row in assessed_rows if not row.get("review_blockers")]
    review_ready = bool(not blockers and ready_rows)
    observed_control_pools = sorted({str(row.get("control_pool_address") or "") for row in assessed_rows if row.get("control_pool_address")})
    observed_windows = sorted({str(row.get("outcome_window_label") or "") for row in assessed_rows if row.get("outcome_window_label")})
    summary = {
        "total_rows_in_table": row_count_total,
        "review_rows": len(assessed_rows),
        "ready_rows": len(ready_rows),
        "invalid_rows": len(invalid_rows),
        "duplicate_control_outcome_dedupe_keys": duplicate_dedupe_count,
        "payload_digest_bound": len([row for row in assessed_rows if row.get("payload_digest_bound")]),
        "current_plan_bound": len([row for row in assessed_rows if row.get("current_plan_bound")]),
        "route_bound": len([row for row in assessed_rows if row.get("route_bound")]),
        "dedupe_bound": len([row for row in assessed_rows if row.get("dedupe_bound")]),
        "lookup_digest_bound": len([row for row in assessed_rows if row.get("lookup_digest_bound")]),
        "local_quality_bound": len([row for row in assessed_rows if row.get("local_quality_bound")]),
        "control_pools": observed_control_pools,
        "windows": observed_windows,
        "ready_for_multi_candidate_replay_preview": review_ready,
        "can_detect_reliable_manipulation_now": False,
    }
    return {
        "ok": True,
        "dry_run": True,
        "queue_status": "ready_but_disabled" if review_ready else "blocked",
        "review_readiness": "ready_for_multi_candidate_replay_preview" if review_ready else "blocked",
        "chain": clean_chain,
        "target_table": target_table,
        "table_exists": table_exists,
        "status_filter": status_filter or None,
        "control_outcome_lookup_digest": lookup_digest or None,
        "summary": summary,
        "rows": [
            {
                "control_outcome_id": row.get("id"),
                "source_case_pool_address": row.get("source_case_pool_address"),
                "source_case_token_symbol": row.get("source_case_token_symbol"),
                "control_pool_address": row.get("control_pool_address"),
                "control_dex": row.get("control_dex"),
                "outcome_window_label": row.get("outcome_window_label"),
                "anchor_block": row.get("anchor_block"),
                "expected_end_block": row.get("expected_end_block"),
                "local_swap_rows": row.get("local_swap_rows"),
                "price_proxy_points": row.get("price_proxy_points"),
                "max_favorable_move_pct": row.get("max_favorable_move_pct"),
                "max_adverse_move_pct": row.get("max_adverse_move_pct"),
                "net_move_pct": row.get("net_move_pct"),
                "control_outcome_digest": row.get("control_outcome_digest"),
                "control_outcome_dedupe_key": row.get("control_outcome_dedupe_key"),
                "status": row.get("status"),
                "payload_json_valid": row.get("payload_json_valid"),
                "payload_digest_bound": row.get("payload_digest_bound"),
                "current_plan_bound": row.get("current_plan_bound"),
                "route_bound": row.get("route_bound"),
                "dedupe_bound": row.get("dedupe_bound"),
                "lookup_digest_bound": row.get("lookup_digest_bound"),
                "local_quality_bound": row.get("local_quality_bound"),
                "review_blockers": row.get("review_blockers"),
            }
            for row in assessed_rows[:clean_limit]
        ],
        "blockers": blockers,
        "next_safe_step": "multi_candidate_shadow_replay_preview_read_only" if review_ready else "repair_control_outcome_review_blockers",
        "plain_summary_fr": (
            "Les outcomes de controle persistés sont propres pour une preview de replay multi-candidat. "
            "Ce n'est toujours pas un verdict client ni un trade."
            if review_ready else
            "Les outcomes de controle persistés ne sont pas encore assez propres pour le replay multi-candidat."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
) -> dict[str, Any]:
    """Read-only in-memory replay comparing the source case against reviewed controls."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 50), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_controls = max(1, min(int(max_controls or 3), 10))
    source_policy = (
        "admin-only read-only multi-candidate shadow replay preview. It compares the reviewed UFLOKI source case "
        "against reviewed control outcome windows in memory only. It does not persist a replay, create a score, "
        "emit a client signal, execute a trade, create a mapping, create a label, create a wallet order or create an opt-in."
    )
    disabled = {
        "would_run_real_backtest": False,
        "would_persist_replay": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "replay_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    source_preview = get_manipulation_detection_source_backed_shadow_backtest_preview(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=max(clean_limit, 4),
        dry_run=True,
    )
    control_review = get_manipulation_detection_source_backed_control_outcome_review_queue(
        chain=clean_chain,
        status="pending_control_outcome_review",
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_controls=safe_max_controls,
    )
    source_backtest = dict(source_preview.get("backtest_preview") or {})
    source_ready = source_preview.get("preview_status") == "ready_but_disabled"
    controls_ready = control_review.get("review_readiness") == "ready_for_multi_candidate_replay_preview"

    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _classify_case(max_favorable: float | None, max_adverse: float | None, last_net: float | None) -> str:
        if max_favorable is not None and max_favorable >= 25 and (max_adverse is None or max_adverse > -40):
            return "promising_but_unvalidated"
        if max_favorable is not None and max_favorable <= 0 and (last_net is not None and last_net < 0):
            return "negative_for_long_opportunity"
        if last_net is not None and last_net < 0 and (max_favorable is None or max_favorable < 10):
            return "weak_or_negative"
        return "inconclusive"

    control_groups: dict[str, list[dict[str, Any]]] = {}
    for row in list(control_review.get("rows") or []):
        pool = str(row.get("control_pool_address") or "").strip().lower()
        if not pool:
            continue
        control_groups.setdefault(pool, []).append(row)

    control_cases: list[dict[str, Any]] = []
    for pool, rows in sorted(control_groups.items()):
        favorable = [_float_or_none(row.get("max_favorable_move_pct")) for row in rows]
        adverse = [_float_or_none(row.get("max_adverse_move_pct")) for row in rows]
        nets = [_float_or_none(row.get("net_move_pct")) for row in rows]
        favorable_values = [value for value in favorable if value is not None]
        adverse_values = [value for value in adverse if value is not None]
        net_values = [value for value in nets if value is not None]
        max_favorable = round(max(favorable_values), 4) if favorable_values else None
        max_adverse = round(min(adverse_values), 4) if adverse_values else None
        last_net = round(net_values[-1], 4) if net_values else None
        classification = _classify_case(max_favorable, max_adverse, last_net)
        control_cases.append({
            "control_pool_address": pool,
            "control_dex": rows[0].get("control_dex"),
            "window_count": len(rows),
            "windows": sorted({str(row.get("outcome_window_label") or "") for row in rows}),
            "max_favorable_move_pct": max_favorable,
            "max_adverse_move_pct": max_adverse,
            "last_net_move_pct": last_net,
            "classification": classification,
            "would_have_supported_long_client_signal": bool(classification == "promising_but_unvalidated"),
        })

    source_case = {
        "pool_address": source_preview.get("pool_address") or clean_pool or None,
        "token_address": source_preview.get("token_address") or clean_token or None,
        "token_symbol": source_preview.get("token_symbol"),
        "window_count": source_backtest.get("window_count"),
        "max_favorable_move_pct": source_backtest.get("max_favorable_move_pct"),
        "max_adverse_move_pct": source_backtest.get("max_adverse_move_pct"),
        "last_net_move_pct": source_backtest.get("last_net_move_pct"),
        "classification": source_backtest.get("outcome_classification"),
        "would_have_supported_long_client_signal": bool(source_backtest.get("would_have_supported_long_client_signal")),
    }
    controls_with_long_support = len([case for case in control_cases if case.get("would_have_supported_long_client_signal")])
    controls_negative_or_weak = len([
        case for case in control_cases
        if case.get("classification") in {"negative_for_long_opportunity", "weak_or_negative"}
    ])
    source_class = str(source_case.get("classification") or "")
    if source_class == "negative_for_long_opportunity":
        replay_verdict = "reject_source_long_signal"
        replay_explanation = "UFLOKI is source-backed but the repaired outcome is negative for a long-style opportunity."
    elif source_case.get("would_have_supported_long_client_signal") and controls_with_long_support == 0:
        replay_verdict = "source_promising_but_needs_more_controls"
        replay_explanation = "The source case looks better than the current controls, but the sample is too small for a reliable detector claim."
    elif source_case.get("would_have_supported_long_client_signal") and controls_with_long_support:
        replay_verdict = "possible_false_positive_risk"
        replay_explanation = "At least one control also looks promising, so the current detector may not separate signal from background behavior."
    else:
        replay_verdict = "inconclusive_collect_more_cases"
        replay_explanation = "The current source/control comparison is not strong enough to support a client signal."

    replay_ready = bool(source_ready and controls_ready and control_cases)
    replay_digest = _sync_liquidity_payload_digest({
        "chain": clean_chain,
        "source_case": source_case,
        "control_cases": control_cases,
        "replay_verdict": replay_verdict,
    })
    blockers = list(dict.fromkeys([
        *(source_preview.get("blockers") or []),
        *(control_review.get("blockers") or []),
        *([] if source_ready else ["source_shadow_backtest_preview_not_ready"]),
        *([] if controls_ready else ["control_outcome_review_not_ready"]),
        *([] if control_cases else ["no_reviewed_control_cases"]),
        "multi_candidate_replay_not_persisted",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    allowed_source_blockers = {
        "negative_controls_missing",
        "multi_candidate_validation_missing",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    }
    blockers = [
        blocker for blocker in blockers
        if blocker not in allowed_source_blockers or blocker in {"policy_risk_gate_missing", "client_opt_in_missing", "client_signal_disabled", "trade_disabled"}
    ]
    return {
        "ok": True,
        "dry_run": True,
        "replay_status": "ready_but_disabled" if replay_ready else "blocked",
        "chain": clean_chain,
        "source_case": source_case,
        "control_cases": control_cases[:clean_limit],
        "multi_candidate_shadow_replay_digest": replay_digest,
        "replay_preview": {
            "mode": "in_memory_shadow_replay_only_no_client_output",
            "source_case_classification": source_case.get("classification"),
            "control_case_count": len(control_cases),
            "controls_with_long_support": controls_with_long_support,
            "controls_negative_or_weak": controls_negative_or_weak,
            "replay_verdict": replay_verdict if replay_ready else "blocked",
            "explanation": replay_explanation if replay_ready else "source_or_controls_not_ready",
            "would_have_supported_client_signal": False,
            "can_claim_detector_quality_now": False,
            "why_not_final": [
                "sample is still too small",
                "replay is not persisted",
                "policy/risk gate missing",
                "paper trading missing",
                "client opt-in missing",
            ],
        },
        "source_preview_summary": source_preview.get("summary"),
        "control_review_summary": control_review.get("summary"),
        "summary": {
            "source_ready": source_ready,
            "controls_ready": controls_ready,
            "control_cases_reviewed": len(control_cases),
            "reviewed_control_windows": (control_review.get("summary") or {}).get("review_rows"),
            "multi_candidate_replay_preview_ready": replay_ready,
            "replay_verdict": replay_verdict if replay_ready else "blocked",
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "multi_candidate_shadow_replay_policy_thresholds_read_only"
            if replay_ready else
            "repair_multi_candidate_shadow_replay_blockers"
        ),
        "plain_summary_fr": (
            "Le replay multi-candidat est calculable en memoire. Pour l'instant, il rejette surtout le long UFLOKI "
            "plutot que de creer un signal: c'est une protection contre les faux positifs."
            if replay_ready and replay_verdict == "reject_source_long_signal" else
            "Le replay multi-candidat est calculable en memoire, mais il reste trop petit pour un verdict client."
            if replay_ready else
            "Le replay multi-candidat reste bloque tant que la source ou les controles ne sont pas propres."
        ),
        "can_detect_reliable_manipulation_now": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_replay_policy_thresholds(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
    min_control_cases: int = 3,
    min_source_favorable_move_pct: float = 15.0,
    min_source_net_move_pct: float = 5.0,
    max_source_adverse_move_pct: float = -20.0,
) -> dict[str, Any]:
    """Read-only policy thresholds that convert replay output into a machine decision."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 50), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_controls = max(1, min(int(max_controls or 3), 10))
    safe_min_control_cases = max(1, min(int(min_control_cases or 3), 25))
    safe_min_favorable = float(min_source_favorable_move_pct)
    safe_min_net = float(min_source_net_move_pct)
    safe_max_adverse = float(max_source_adverse_move_pct)
    source_policy = (
        "admin-only read-only policy threshold preview. It consumes the existing source-backed multi-candidate "
        "shadow replay preview and turns it into an explainable machine decision. It does not persist replay "
        "results, create a live score, emit a client signal, execute a trade, create a mapping, create a label, "
        "create a wallet order or create an opt-in."
    )
    disabled = {
        "would_persist_policy_decision": False,
        "would_persist_replay": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "policy_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    replay = get_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_controls=safe_max_controls,
    )
    replay_preview = dict(replay.get("replay_preview") or {})
    source_case = dict(replay.get("source_case") or {})
    control_cases = list(replay.get("control_cases") or [])
    replay_ready = replay.get("replay_status") == "ready_but_disabled"
    replay_verdict = str(replay_preview.get("replay_verdict") or (replay.get("summary") or {}).get("replay_verdict") or "")

    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    source_favorable = _float_or_none(source_case.get("max_favorable_move_pct"))
    source_adverse = _float_or_none(source_case.get("max_adverse_move_pct"))
    source_net = _float_or_none(source_case.get("last_net_move_pct"))
    controls_with_long_support = int(replay_preview.get("controls_with_long_support") or 0)

    gates = [
        {
            "gate": "replay_ready",
            "passed": bool(replay_ready),
            "observed": replay.get("replay_status"),
            "required": "ready_but_disabled",
            "if_failed": "collect_more_data",
        },
        {
            "gate": "minimum_control_cases",
            "passed": len(control_cases) >= safe_min_control_cases,
            "observed": len(control_cases),
            "required": safe_min_control_cases,
            "if_failed": "collect_more_data",
        },
        {
            "gate": "source_favorable_move",
            "passed": source_favorable is not None and source_favorable >= safe_min_favorable,
            "observed": source_favorable,
            "required": f">={safe_min_favorable}",
            "if_failed": "reject_research_signal_candidate",
        },
        {
            "gate": "source_net_move",
            "passed": source_net is not None and source_net >= safe_min_net,
            "observed": source_net,
            "required": f">={safe_min_net}",
            "if_failed": "reject_research_signal_candidate",
        },
        {
            "gate": "source_adverse_move_limit",
            "passed": source_adverse is not None and source_adverse >= safe_max_adverse,
            "observed": source_adverse,
            "required": f">={safe_max_adverse}",
            "if_failed": "reject_research_signal_candidate",
        },
        {
            "gate": "control_false_positive_risk",
            "passed": controls_with_long_support == 0,
            "observed": controls_with_long_support,
            "required": 0,
            "if_failed": "collect_more_data",
        },
    ]
    failed_gates = [gate for gate in gates if not gate.get("passed")]
    reject_failures = [gate for gate in failed_gates if gate.get("if_failed") == "reject_research_signal_candidate"]
    collect_failures = [gate for gate in failed_gates if gate.get("if_failed") == "collect_more_data"]

    if not replay_ready or replay_verdict == "blocked":
        next_decision = "collect_more_data"
        decision_reason = "source_or_controls_not_ready"
    elif replay_verdict == "reject_source_long_signal" or reject_failures:
        next_decision = "reject_research_signal_candidate"
        decision_reason = "source_outcome_fails_policy_thresholds"
    elif not failed_gates and source_case.get("would_have_supported_long_client_signal"):
        next_decision = "accept_research_signal_candidate"
        decision_reason = "source_passes_research_thresholds_client_output_still_disabled"
    elif collect_failures:
        next_decision = "collect_more_data"
        decision_reason = "control_sample_or_false_positive_risk_not_resolved"
    elif replay_verdict == "source_promising_but_needs_more_controls":
        next_decision = "collect_more_data"
        decision_reason = "source_promising_but_more_controls_required"
    else:
        next_decision = "collect_more_data"
        decision_reason = "policy_conservative_default"

    policy_digest = _sync_liquidity_payload_digest({
        "chain": clean_chain,
        "replay_digest": replay.get("multi_candidate_shadow_replay_digest"),
        "thresholds": {
            "min_control_cases": safe_min_control_cases,
            "min_source_favorable_move_pct": safe_min_favorable,
            "min_source_net_move_pct": safe_min_net,
            "max_source_adverse_move_pct": safe_max_adverse,
        },
        "next_decision": next_decision,
    })
    blockers = list(dict.fromkeys([
        *(replay.get("blockers") or []),
        *([] if replay_ready else ["multi_candidate_replay_preview_not_ready"]),
        "policy_decision_not_persisted",
        "policy_risk_gate_missing",
        "client_opt_in_missing",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    return {
        "ok": True,
        "dry_run": True,
        "policy_status": "ready_but_disabled" if replay_ready else "blocked",
        "chain": clean_chain,
        "source_case": source_case,
        "control_case_count": len(control_cases),
        "replay_verdict": replay_verdict,
        "policy_thresholds": {
            "min_control_cases": safe_min_control_cases,
            "min_source_favorable_move_pct": safe_min_favorable,
            "min_source_net_move_pct": safe_min_net,
            "max_source_adverse_move_pct": safe_max_adverse,
            "max_controls_with_long_support": 0,
        },
        "policy_gate_results": gates,
        "failed_policy_gates": failed_gates,
        "machine_policy_decision": {
            "next_decision": next_decision,
            "decision_reason": decision_reason,
            "allowed_decisions": [
                "accept_research_signal_candidate",
                "reject_research_signal_candidate",
                "collect_more_data",
            ],
            "would_allow_client_signal": False,
            "would_allow_trade": False,
        },
        "policy_decision_digest": policy_digest,
        "replay_summary": replay.get("summary"),
        "blockers": blockers,
        "next_safe_step": (
            "collect_more_source_backed_cases_read_only"
            if next_decision in {"reject_research_signal_candidate", "collect_more_data"} else
            "policy_decision_audit_persistence_schema_plan_read_only"
        ),
        "plain_summary_fr": (
            "La policy transforme le replay en decision machine: rejet du candidat signal UFLOKI en long. "
            "Ce n'est pas un echec produit: c'est exactement le comportement attendu pour eviter les faux signaux."
            if next_decision == "reject_research_signal_candidate" else
            "La policy demande plus de donnees avant toute decision client."
        ),
        "can_detect_reliable_manipulation_now": False,
        "client_signal_ready": False,
        "trade_ready": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_case_control_expansion_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_candidates: int = 8,
) -> dict[str, Any]:
    """Read-only plan for expanding source-backed cases and comparable controls."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_candidates = max(1, min(int(max_candidates or 8), 25))
    source_policy = (
        "admin-only read-only case/control expansion plan. It reads local swaps, pair tokens and existing "
        "evidence tables to identify which pools could become source-backed cases or comparable controls. It "
        "does not call providers, scrape, persist evidence, create a score, emit a client signal, create a "
        "mapping, execute a trade, create a wallet order or create an opt-in."
    )
    disabled = {
        "would_call_provider": False,
        "would_scrape": False,
        "would_persist_evidence": False,
        "would_create_outcome_rows": False,
        "would_run_replay": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    policy = get_manipulation_detection_source_backed_replay_policy_thresholds(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=max(clean_limit, 10),
        dry_run=True,
        min_swaps=safe_min_swaps,
    )
    current_source_pool = str((policy.get("source_case") or {}).get("pool_address") or clean_pool or "").strip().lower()
    current_policy_decision = (policy.get("machine_policy_decision") or {}).get("next_decision")
    blockers: list[str] = []
    candidate_rows: list[dict[str, Any]] = []
    table_status: dict[str, Any] = {}

    try:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        try:
            tables = [
                "swaps",
                "pair_tokens",
                "dex_paircreated_evidence",
                "dex_mapping_review_queue",
                "dex_raw_swap_events",
                "dex_raw_sync_events",
                "dex_raw_liquidity_events",
                "dex_transfer_context_evidence",
                "manipulation_repaired_outcome_windows",
                "manipulation_control_outcome_windows",
            ]
            table_status = {table: _table_exists(conn, table) for table in tables}
            if not table_status.get("swaps"):
                blockers.append("swaps_table_missing")
            if table_status.get("swaps"):
                rows = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT lower(chain) AS chain, lower(pool) AS pool, COALESCE(dex, '') AS dex,
                               COALESCE(token_identity_quality, '') AS token_identity_quality,
                               COALESCE(pair_rpc_source, '') AS pair_rpc_source,
                               COALESCE(venue_source, '') AS venue_source,
                               COALESCE(venue_confidence, 0) AS venue_confidence,
                               COUNT(*) AS swap_rows,
                               COUNT(DISTINCT tx_hash) AS distinct_tx_hashes,
                               COUNT(DISTINCT wallet) AS distinct_wallets,
                               MIN(block_number) AS first_block,
                               MAX(block_number) AS last_block,
                               SUM(COALESCE(amount_usd, 0)) AS amount_usd_sum,
                               GROUP_CONCAT(DISTINCT token_in) AS token_ins,
                               GROUP_CONCAT(DISTINCT token_out) AS token_outs
                        FROM swaps
                        WHERE lower(chain) = ? AND pool IS NOT NULL AND pool != ''
                              AND (? = '' OR lower(pool) != ?)
                        GROUP BY lower(chain), lower(pool)
                        ORDER BY swap_rows DESC, distinct_tx_hashes DESC, distinct_wallets DESC
                        LIMIT ?
                        """,
                        (clean_chain, current_source_pool, current_source_pool, max(clean_limit * 3, 25)),
                    ).fetchall()
                ]
                pools = [str(row.get("pool") or "").lower() for row in rows if row.get("pool")]
                placeholders = ",".join("?" for _ in pools)
                pair_rows: dict[str, dict[str, Any]] = {}
                paircreated_counts: dict[str, int] = {}
                mapping_counts: dict[str, int] = {}
                raw_swap_counts: dict[str, int] = {}
                sync_counts: dict[str, int] = {}
                liquidity_counts: dict[str, int] = {}
                transfer_counts: dict[str, int] = {}
                repaired_outcome_counts: dict[str, int] = {}
                control_outcome_counts: dict[str, int] = {}
                if pools and table_status.get("pair_tokens"):
                    pair_rows = {
                        str(row["pool"] or "").lower(): dict(row)
                        for row in conn.execute(
                            f"""
                            SELECT lower(chain) AS chain, lower(pool) AS pool, lower(token0) AS token0,
                                   lower(token1) AS token1, rpc_source
                            FROM pair_tokens
                            WHERE lower(chain) = ? AND lower(pool) IN ({placeholders})
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }
                if pools and table_status.get("dex_paircreated_evidence"):
                    paircreated_counts = {
                        str(row["pair_address"] or "").lower(): int(row["count"] or 0)
                        for row in conn.execute(
                            f"""
                            SELECT lower(pair_address) AS pair_address, COUNT(*) AS count
                            FROM dex_paircreated_evidence
                            WHERE lower(chain) = ? AND lower(pair_address) IN ({placeholders})
                                  AND status IN ('accepted_for_future_mapping_review', 'accepted', 'pending_admin_review')
                            GROUP BY lower(pair_address)
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }
                if pools and table_status.get("dex_mapping_review_queue"):
                    mapping_counts = {
                        str(row["pair_address"] or "").lower(): int(row["count"] or 0)
                        for row in conn.execute(
                            f"""
                            SELECT lower(pair_address) AS pair_address, COUNT(*) AS count
                            FROM dex_mapping_review_queue
                            WHERE lower(chain) = ? AND lower(pair_address) IN ({placeholders})
                            GROUP BY lower(pair_address)
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }
                if pools and table_status.get("dex_raw_swap_events"):
                    raw_swap_counts = {
                        str(row["pair_address"] or "").lower(): int(row["count"] or 0)
                        for row in conn.execute(
                            f"""
                            SELECT lower(pair_address) AS pair_address, COUNT(*) AS count
                            FROM dex_raw_swap_events
                            WHERE lower(chain) = ? AND lower(pair_address) IN ({placeholders})
                            GROUP BY lower(pair_address)
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }
                if pools and table_status.get("dex_raw_sync_events"):
                    sync_counts = {
                        str(row["pair_address"] or "").lower(): int(row["count"] or 0)
                        for row in conn.execute(
                            f"""
                            SELECT lower(pair_address) AS pair_address, COUNT(*) AS count
                            FROM dex_raw_sync_events
                            WHERE lower(chain) = ? AND lower(pair_address) IN ({placeholders})
                            GROUP BY lower(pair_address)
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }
                if pools and table_status.get("dex_raw_liquidity_events"):
                    liquidity_counts = {
                        str(row["pair_address"] or "").lower(): int(row["count"] or 0)
                        for row in conn.execute(
                            f"""
                            SELECT lower(pair_address) AS pair_address, COUNT(*) AS count
                            FROM dex_raw_liquidity_events
                            WHERE lower(chain) = ? AND lower(pair_address) IN ({placeholders})
                            GROUP BY lower(pair_address)
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }
                if pools and table_status.get("dex_transfer_context_evidence"):
                    transfer_counts = {
                        str(row["pool_address"] or "").lower(): int(row["count"] or 0)
                        for row in conn.execute(
                            f"""
                            SELECT lower(pool_address) AS pool_address, COUNT(*) AS count
                            FROM dex_transfer_context_evidence
                            WHERE lower(chain) = ? AND lower(pool_address) IN ({placeholders})
                            GROUP BY lower(pool_address)
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }
                if pools and table_status.get("manipulation_repaired_outcome_windows"):
                    repaired_outcome_counts = {
                        str(row["pool_address"] or "").lower(): int(row["count"] or 0)
                        for row in conn.execute(
                            f"""
                            SELECT lower(pool_address) AS pool_address, COUNT(*) AS count
                            FROM manipulation_repaired_outcome_windows
                            WHERE lower(chain) = ? AND lower(pool_address) IN ({placeholders})
                            GROUP BY lower(pool_address)
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }
                if pools and table_status.get("manipulation_control_outcome_windows"):
                    control_outcome_counts = {
                        str(row["control_pool_address"] or "").lower(): int(row["count"] or 0)
                        for row in conn.execute(
                            f"""
                            SELECT lower(control_pool_address) AS control_pool_address, COUNT(*) AS count
                            FROM manipulation_control_outcome_windows
                            WHERE lower(chain) = ? AND lower(control_pool_address) IN ({placeholders})
                            GROUP BY lower(control_pool_address)
                            """,
                            tuple([clean_chain, *pools]),
                        ).fetchall()
                    }

                for row in rows:
                    pool = str(row.get("pool") or "").strip().lower()
                    pair_row = pair_rows.get(pool) or {}
                    token_addresses = [
                        str(pair_row.get("token0") or "").strip().lower(),
                        str(pair_row.get("token1") or "").strip().lower(),
                    ]
                    if not any(token_addresses):
                        token_addresses = [
                            token.strip().lower()
                            for token in (str(row.get("token_ins") or "") + "," + str(row.get("token_outs") or "")).split(",")
                            if token.strip()
                        ][:4]
                    swap_rows = int(row.get("swap_rows") or 0)
                    distinct_txs = int(row.get("distinct_tx_hashes") or 0)
                    distinct_wallets = int(row.get("distinct_wallets") or 0)
                    exact_direction = str(row.get("token_identity_quality") or "") == "exact_pair_log_direction"
                    venue_source = str(row.get("venue_source") or "")
                    dex_name = str(row.get("dex") or "")
                    paircreated_count = paircreated_counts.get(pool, 0)
                    mapping_count = mapping_counts.get(pool, 0)
                    route_source_backed = bool(
                        paircreated_count
                        or mapping_count
                        or venue_source in {"source_backed_router_mapping", "known_router_address"}
                        or ("pancakeswap" in dex_name.lower() and "unknown" not in dex_name.lower())
                    )
                    raw_swap_count = raw_swap_counts.get(pool, 0)
                    sync_count = sync_counts.get(pool, 0)
                    liquidity_count = liquidity_counts.get(pool, 0)
                    transfer_count = transfer_counts.get(pool, 0)
                    repaired_count = repaired_outcome_counts.get(pool, 0)
                    control_count = control_outcome_counts.get(pool, 0)
                    missing = [
                        *([] if route_source_backed else ["route_or_paircreated_source_proof"]),
                        *([] if exact_direction else ["exact_pair_direction"]),
                        *([] if swap_rows >= safe_min_swaps and distinct_txs >= safe_min_swaps else ["minimum_local_swaps"]),
                        *([] if raw_swap_count >= safe_min_swaps else ["raw_swap_event_rows"]),
                        *([] if sync_count else ["sync_reserve_context"]),
                        *([] if transfer_count else ["transfer_context"]),
                        *([] if repaired_count or control_count else ["outcome_windows"]),
                    ]
                    if route_source_backed and exact_direction and swap_rows >= safe_min_swaps:
                        candidate_status = "expansion_candidate"
                    elif exact_direction and swap_rows >= safe_min_swaps:
                        candidate_status = "route_repair_candidate"
                    else:
                        candidate_status = "research_only"
                    candidate_rows.append({
                        "chain": clean_chain,
                        "pool_address": pool,
                        "dex": dex_name,
                        "token_addresses": [token for token in token_addresses if token],
                        "swap_rows": swap_rows,
                        "distinct_tx_hashes": distinct_txs,
                        "distinct_wallets": distinct_wallets,
                        "first_block": row.get("first_block"),
                        "last_block": row.get("last_block"),
                        "route_source_backed": route_source_backed,
                        "route_sources": {
                            "venue_source": venue_source,
                            "venue_confidence": row.get("venue_confidence"),
                            "paircreated_evidence_rows": paircreated_count,
                            "mapping_review_rows": mapping_count,
                            "pair_rpc_source": pair_row.get("rpc_source") or row.get("pair_rpc_source"),
                        },
                        "data_coverage": {
                            "raw_swap_events": raw_swap_count,
                            "sync_events": sync_count,
                            "liquidity_events": liquidity_count,
                            "transfer_context_evidence": transfer_count,
                            "repaired_outcome_windows": repaired_count,
                            "control_outcome_windows": control_count,
                        },
                        "candidate_status": candidate_status,
                        "missing_for_source_backed_replay": missing,
                        "recommended_next_data_task": (
                            "outcome_collection_plan_read_only"
                            if not missing or missing == ["outcome_windows"] else
                            "paircreated_or_route_source_repair_read_only"
                            if "route_or_paircreated_source_proof" in missing else
                            "raw_swap_sync_transfer_collection_plan_read_only"
                        ),
                    })
        finally:
            conn.close()
    except Exception as exc:
        blockers.append(f"case_control_expansion_query_error:{type(exc).__name__}")

    status_rank = {"expansion_candidate": 0, "route_repair_candidate": 1, "research_only": 2}
    candidate_rows = sorted(
        candidate_rows,
        key=lambda row: (
            status_rank.get(str(row.get("candidate_status") or ""), 9),
            -int(row.get("swap_rows") or 0),
            -int(row.get("distinct_tx_hashes") or 0),
            -int(row.get("distinct_wallets") or 0),
        ),
    )
    expansion_candidates = [row for row in candidate_rows if row.get("candidate_status") == "expansion_candidate"]
    route_repair_candidates = [row for row in candidate_rows if row.get("candidate_status") == "route_repair_candidate"]
    plan_ready = bool(candidate_rows)
    expansion_digest = _sync_liquidity_payload_digest({
        "chain": clean_chain,
        "current_policy_decision": current_policy_decision,
        "current_source_pool": current_source_pool,
        "candidates": candidate_rows[:safe_max_candidates],
    })
    blockers = list(dict.fromkeys([
        *blockers,
        *([] if candidate_rows else ["no_local_candidate_pools_found"]),
        "more_source_backed_cases_required",
        "client_signal_disabled",
        "trade_disabled",
        "client_opt_in_missing",
    ]))
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if plan_ready else "blocked",
        "chain": clean_chain,
        "current_policy": {
            "policy_status": policy.get("policy_status"),
            "replay_verdict": policy.get("replay_verdict"),
            "next_decision": current_policy_decision,
            "decision_reason": (policy.get("machine_policy_decision") or {}).get("decision_reason"),
        },
        "table_status": table_status,
        "expansion_plan_digest": expansion_digest,
        "candidate_pools": candidate_rows[:safe_max_candidates],
        "summary": {
            "local_candidate_pools_reviewed": len(candidate_rows),
            "expansion_candidates": len(expansion_candidates),
            "route_repair_candidates": len(route_repair_candidates),
            "research_only_candidates": len(candidate_rows) - len(expansion_candidates) - len(route_repair_candidates),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "source_backed_outcome_collection_for_best_expansion_candidate_read_only"
            if expansion_candidates else
            "route_source_repair_for_best_candidates_read_only"
            if route_repair_candidates else
            "collect_more_local_swap_data_read_only"
        ),
        "plain_summary_fr": (
            "Le plan liste les prochains pools a transformer en cas source-backed ou controles comparables. "
            "Il sert a agrandir l'echantillon avant tout signal client."
            if plan_ready else
            "Aucun nouveau pool local assez propre n'est disponible pour agrandir l'echantillon."
        ),
        "can_detect_reliable_manipulation_now": False,
        "client_signal_ready": False,
        "trade_ready": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_candidates: int = 3,
    max_window_blocks: int = 5000,
) -> dict[str, Any]:
    """Read-only raw Swap/Sync/Transfer collection plan for the best expansion candidates."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_candidates = max(1, min(int(max_candidates or 3), 10))
    safe_max_window_blocks = max(100, min(int(max_window_blocks or 5000), 25000))
    swap_topic = SWAP_TOPIC.lower()
    transfer_topic = TRANSFER_TOPIC.lower()
    indexed_address_topic = getattr(_engine(), "_evm_indexed_address_topic", None)
    source_policy = (
        "admin-only read-only top expansion raw context collection plan. It consumes the source-backed "
        "case/control expansion plan and emits bounded future filters for Swap, Sync, Mint, Burn and ERC20 "
        "Transfer context. It does not call providers, scrape, persist evidence, create a score, emit a client "
        "signal, create a mapping, execute a trade, create a wallet order or create an opt-in."
    )
    disabled = {
        "would_call_provider": False,
        "would_scrape": False,
        "would_collect_raw_swaps": False,
        "would_collect_sync_liquidity": False,
        "would_collect_transfer_context": False,
        "would_persist_evidence": False,
        "would_create_outcome_rows": False,
        "would_run_replay": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    expansion = get_manipulation_detection_source_backed_case_control_expansion_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_candidates=max(safe_max_candidates * 3, safe_max_candidates),
    )
    candidates = [
        row for row in list(expansion.get("candidate_pools") or [])
        if row.get("candidate_status") == "expansion_candidate"
    ][:safe_max_candidates]

    def _valid_evm(value: str) -> bool:
        clean = str(value or "").strip().lower()
        return clean.startswith("0x") and len(clean) == 42

    def _topic_address(value: str) -> str | None:
        if not _valid_evm(value) or not callable(indexed_address_topic):
            return None
        return indexed_address_topic(value)

    def _bounded_ranges(first_block: Any, last_block: Any) -> list[dict[str, Any]]:
        try:
            first = int(first_block)
            last = int(last_block)
        except (TypeError, ValueError):
            return []
        if first < 0 or last < first:
            return []
        span = last - first + 1
        if span <= safe_max_window_blocks:
            return [{
                "range_id": "observed_activity",
                "from_block": first,
                "to_block": last,
                "block_span": span,
            }]
        head_to = first + safe_max_window_blocks - 1
        tail_from = max(first, last - safe_max_window_blocks + 1)
        return [
            {
                "range_id": "observed_activity_head",
                "from_block": first,
                "to_block": head_to,
                "block_span": head_to - first + 1,
            },
            {
                "range_id": "observed_activity_tail",
                "from_block": tail_from,
                "to_block": last,
                "block_span": last - tail_from + 1,
            },
        ]

    candidate_plans: list[dict[str, Any]] = []
    for candidate in candidates:
        pool = str(candidate.get("pool_address") or "").strip().lower()
        token_addresses = [
            str(token or "").strip().lower()
            for token in list(candidate.get("token_addresses") or [])
            if _valid_evm(str(token or ""))
        ][:4]
        ranges = _bounded_ranges(candidate.get("first_block"), candidate.get("last_block"))
        raw_swap_filters = [
            {
                "filter_type": "v2_swap",
                "range_id": item["range_id"],
                "chain": clean_chain,
                "address": pool,
                "topics": [swap_topic],
                "from_block": item["from_block"],
                "to_block": item["to_block"],
                "purpose": "collect exact Swap event rows for expansion candidate",
                "would_call_provider_now": False,
            }
            for item in ranges
            if _valid_evm(pool) and swap_topic
        ]
        sync_liquidity_filters = [
            {
                "filter_type": f"v2_{spec['event_name'].lower()}",
                "event_name": spec["event_name"],
                "range_id": item["range_id"],
                "chain": clean_chain,
                "address": pool,
                "topics": [spec["topic0"]],
                "from_block": item["from_block"],
                "to_block": item["to_block"],
                "purpose": "collect reserve/liquidity context for expansion candidate",
                "would_call_provider_now": False,
            }
            for item in ranges
            for spec in _uniswap_v2_liquidity_event_topics()
            if _valid_evm(pool) and spec.get("topic0")
        ]
        transfer_filters = []
        pool_topic = _topic_address(pool)
        if transfer_topic and pool_topic:
            for token in token_addresses:
                for item in ranges:
                    transfer_filters.append({
                        "filter_type": "erc20_transfer_in_to_pool",
                        "range_id": item["range_id"],
                        "chain": clean_chain,
                        "address": token,
                        "topics": [transfer_topic, None, pool_topic],
                        "from_block": item["from_block"],
                        "to_block": item["to_block"],
                        "purpose": "collect ERC20 transfers into candidate pool",
                        "would_call_provider_now": False,
                    })
                    transfer_filters.append({
                        "filter_type": "erc20_transfer_out_from_pool",
                        "range_id": item["range_id"],
                        "chain": clean_chain,
                        "address": token,
                        "topics": [transfer_topic, pool_topic, None],
                        "from_block": item["from_block"],
                        "to_block": item["to_block"],
                        "purpose": "collect ERC20 transfers out of candidate pool",
                        "would_call_provider_now": False,
                    })
        missing = list(candidate.get("missing_for_source_backed_replay") or [])
        candidate_plans.append({
            "chain": clean_chain,
            "pool_address": pool,
            "dex": candidate.get("dex"),
            "candidate_status": candidate.get("candidate_status"),
            "swap_rows": candidate.get("swap_rows"),
            "distinct_tx_hashes": candidate.get("distinct_tx_hashes"),
            "distinct_wallets": candidate.get("distinct_wallets"),
            "token_addresses": token_addresses,
            "route_source_backed": candidate.get("route_source_backed"),
            "existing_data_coverage": candidate.get("data_coverage") or {},
            "missing_for_source_backed_replay": missing,
            "block_ranges": ranges,
            "raw_swap_filters": raw_swap_filters,
            "sync_liquidity_filters": sync_liquidity_filters,
            "transfer_filters": transfer_filters,
            "future_outcome_windows_required": [
                "plus_1h",
                "plus_6h",
                "plus_24h",
                "plus_72h",
            ],
            "collection_readiness": (
                "ready_for_bounded_lookup_dry_run"
                if raw_swap_filters and sync_liquidity_filters and transfer_filters else
                "blocked"
            ),
            "collection_blockers": [
                *([] if ranges else ["invalid_or_missing_block_range"]),
                *([] if raw_swap_filters else ["raw_swap_filter_missing"]),
                *([] if sync_liquidity_filters else ["sync_liquidity_filters_missing"]),
                *([] if transfer_filters else ["transfer_filters_missing"]),
            ],
        })

    planned_raw_swap_filters = sum(len(row.get("raw_swap_filters") or []) for row in candidate_plans)
    planned_sync_liquidity_filters = sum(len(row.get("sync_liquidity_filters") or []) for row in candidate_plans)
    planned_transfer_filters = sum(len(row.get("transfer_filters") or []) for row in candidate_plans)
    ready_candidates = len([row for row in candidate_plans if row.get("collection_readiness") == "ready_for_bounded_lookup_dry_run"])
    blockers = list(dict.fromkeys([
        *(expansion.get("blockers") or []),
        *([] if candidates else ["no_expansion_candidates_available"]),
        *([] if ready_candidates else ["no_candidates_ready_for_raw_context_lookup"]),
        "bounded_lookup_not_executed",
        "evidence_not_persisted",
        "client_signal_disabled",
        "trade_disabled",
        "client_opt_in_missing",
    ]))
    plan_digest = _sync_liquidity_payload_digest({
        "chain": clean_chain,
        "expansion_digest": expansion.get("expansion_plan_digest"),
        "candidates": [
            {
                "pool_address": row.get("pool_address"),
                "block_ranges": row.get("block_ranges"),
                "raw_swap_filters": len(row.get("raw_swap_filters") or []),
                "sync_liquidity_filters": len(row.get("sync_liquidity_filters") or []),
                "transfer_filters": len(row.get("transfer_filters") or []),
            }
            for row in candidate_plans
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if ready_candidates else "blocked",
        "chain": clean_chain,
        "source_expansion_summary": expansion.get("summary"),
        "raw_context_collection_plan_digest": plan_digest,
        "max_window_blocks": safe_max_window_blocks,
        "event_topics": {
            "Swap": swap_topic,
            "Sync": UNISWAP_V2_SYNC_TOPIC,
            "Mint": UNISWAP_V2_MINT_TOPIC,
            "Burn": UNISWAP_V2_BURN_TOPIC,
            "ERC20 Transfer": transfer_topic,
        },
        "candidate_plans": candidate_plans,
        "summary": {
            "candidate_plans": len(candidate_plans),
            "ready_for_bounded_lookup_dry_run": ready_candidates,
            "planned_raw_swap_filters": planned_raw_swap_filters,
            "planned_sync_liquidity_filters": planned_sync_liquidity_filters,
            "planned_transfer_filters": planned_transfer_filters,
            "planned_total_filters": planned_raw_swap_filters + planned_sync_liquidity_filters + planned_transfer_filters,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "dedupe_policy": {
            "raw_swap": "chain|Swap|pair_address|tx_hash|log_index",
            "sync": "chain|Sync|pair_address|tx_hash|log_index",
            "liquidity": "chain|event_name|pair_address|tx_hash|log_index",
            "transfer": "chain|Transfer|token_address|tx_hash|log_index|from|to",
            "no_overwrite": True,
            "no_upsert": True,
        },
        "blockers": blockers,
        "next_safe_step": (
            "top_expansion_candidates_bounded_raw_context_lookup_dry_run"
            if ready_candidates else
            "repair_expansion_candidate_filter_inputs"
        ),
        "plain_summary_fr": (
            "Le plan de collecte brute est pret pour les meilleurs candidats. Il prepare les filtres Swap, "
            "Sync/Mint/Burn et Transfer, mais ne lance aucun provider et n'ecrit aucune evidence."
            if ready_candidates else
            "Aucun candidat d'expansion n'a encore assez d'informations pour preparer des filtres de collecte brute."
        ),
        "can_detect_reliable_manipulation_now": False,
        "client_signal_ready": False,
        "trade_ready": False,
        **disabled,
    }


def run_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    min_swaps: int = 4,
    max_candidates: int = 3,
    max_window_blocks: int = 5000,
    max_sqd_calls: int = 48,
    max_logs_total: int = 2000,
    max_logs_per_filter: int = 50,
    max_sqd_block_span: int = 1000,
    timeout: int = 8,
) -> dict[str, Any]:
    """Bounded SQD lookup for top expansion raw context; parses logs in memory only."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_candidates = max(1, min(int(max_candidates or 3), 10))
    safe_max_window_blocks = max(100, min(int(max_window_blocks or 5000), 25000))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 48), 100))
    safe_logs_total = max(1, min(int(max_logs_total or 2000), 10000))
    safe_logs_per_filter = max(1, min(int(max_logs_per_filter or 50), safe_logs_total))
    safe_sqd_block_span = max(1, min(int(max_sqd_block_span or 1000), safe_max_window_blocks))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    required_confirm = "RUN_TOP_EXPANSION_RAW_CONTEXT_LOOKUP"
    source_policy = (
        "admin-only bounded read-only top expansion raw context SQD lookup. It may call SQD only for the "
        "already planned Swap, Sync, Mint, Burn and ERC20 Transfer filters after explicit confirmation, parses "
        "logs in memory only, and persists no evidence, mapping, signal, trade, wallet order or opt-in."
    )
    disabled = {
        "would_collect_raw_swaps": False,
        "would_collect_sync_liquidity": False,
        "would_collect_transfer_context": False,
        "would_persist_raw_context": False,
        "would_persist_evidence": False,
        "would_create_outcome_rows": False,
        "would_run_replay": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
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
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            **disabled,
        }

    plan = get_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_candidates=safe_max_candidates,
        max_window_blocks=safe_max_window_blocks,
    )
    candidate_plans = [
        row for row in list(plan.get("candidate_plans") or [])
        if row.get("collection_readiness") == "ready_for_bounded_lookup_dry_run"
    ]
    planned_filters: list[dict[str, Any]] = []
    for candidate in candidate_plans:
        pool = str(candidate.get("pool_address") or "").lower()
        for family, event_name in (
            ("raw_swap_filters", "Swap"),
            ("sync_liquidity_filters", None),
            ("transfer_filters", "ERC20 Transfer"),
        ):
            for row_filter in list(candidate.get(family) or []):
                planned_filters.append({
                    **row_filter,
                    "pool_address": pool,
                    "candidate_pool_address": pool,
                    "event_name": row_filter.get("event_name") or event_name,
                    "filter_family": family,
                })
    blockers = [
        *([] if plan.get("plan_status") == "ready_but_disabled" else ["collection_plan_not_ready"]),
        *([] if candidate_plans else ["no_ready_candidate_plans"]),
        *([] if planned_filters else ["no_planned_filters"]),
    ]
    def _chunk_filter(row_filter: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            start = int(row_filter.get("from_block") or 0)
            end = int(row_filter.get("to_block") or 0)
        except (TypeError, ValueError):
            return []
        if end < start:
            return []
        chunks = []
        cursor = start
        chunk_index = 0
        while cursor <= end:
            chunk_end = min(end, cursor + safe_sqd_block_span - 1)
            chunks.append({
                **row_filter,
                "parent_from_block": start,
                "parent_to_block": end,
                "chunk_index": chunk_index,
                "from_block": cursor,
                "to_block": chunk_end,
            })
            cursor = chunk_end + 1
            chunk_index += 1
        return chunks

    planned_filter_chunks = [
        chunk
        for row_filter in planned_filters
        for chunk in _chunk_filter(row_filter)
    ]

    def _event_bucket(row_filter: dict[str, Any]) -> str:
        event_name = str(row_filter.get("event_name") or "").lower()
        if event_name == "swap":
            return "swap"
        if event_name == "sync":
            return "sync"
        if event_name == "erc20 transfer":
            return "transfer"
        if event_name in {"mint", "burn"}:
            return "liquidity"
        return event_name or "unknown"

    def _balanced_select(chunks: list[dict[str, Any]], limit_count: int) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        pools = []
        for item in chunks:
            pool = str(item.get("candidate_pool_address") or "")
            if pool and pool not in pools:
                pools.append(pool)
        for bucket in ["swap", "sync", "transfer", "liquidity"]:
            for pool in pools:
                for index, item in enumerate(chunks):
                    if index in seen_ids:
                        continue
                    if str(item.get("candidate_pool_address") or "") != pool:
                        continue
                    if _event_bucket(item) != bucket:
                        continue
                    selected.append(item)
                    seen_ids.add(index)
                    break
                    if len(selected) >= limit_count:
                        return selected
                if len(selected) >= limit_count:
                    return selected
        for index, item in enumerate(chunks):
            if len(selected) >= limit_count:
                break
            if index not in seen_ids:
                selected.append(item)
        return selected

    selected_filters = _balanced_select(planned_filter_chunks, safe_sqd_calls)
    if blockers:
        return {
            "ok": True,
            "dry_run": True,
            "lookup_status": "blocked",
            "chain": clean_chain,
            "raw_context_collection_plan_digest": plan.get("raw_context_collection_plan_digest"),
            "candidate_count": len(candidate_plans),
            "planned_filter_count": len(planned_filters),
            "planned_filter_chunk_count": len(planned_filter_chunks),
            "selected_filter_count": 0,
            "selection_strategy": "balanced_candidate_event_coverage",
            "max_logs_per_filter": safe_logs_per_filter,
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "candidate_event_counts": {},
            "parsed_previews": [],
            "blockers": list(dict.fromkeys(blockers + list(plan.get("blockers") or []))),
            "can_detect_reliable_manipulation_now": False,
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
            "raw_context_collection_plan_digest": plan.get("raw_context_collection_plan_digest"),
            "candidate_count": len(candidate_plans),
            "planned_filter_count": len(planned_filters),
            "planned_filter_chunk_count": len(planned_filter_chunks),
            "selected_filter_count": len(selected_filters),
            "selection_strategy": "balanced_candidate_event_coverage",
            "max_logs_per_filter": safe_logs_per_filter,
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "candidate_event_counts": {},
            "parsed_previews": [],
            "required_confirm": required_confirm,
            "blockers": ["allow_external_required_for_bounded_lookup"],
            "would_call_external": True,
            "can_detect_reliable_manipulation_now": False,
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
            "raw_context_collection_plan_digest": plan.get("raw_context_collection_plan_digest"),
            "candidate_count": len(candidate_plans),
            "planned_filter_count": len(planned_filters),
            "planned_filter_chunk_count": len(planned_filter_chunks),
            "selected_filter_count": len(selected_filters),
            "selection_strategy": "balanced_candidate_event_coverage",
            "max_logs_per_filter": safe_logs_per_filter,
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "event_counts": {},
            "candidate_event_counts": {},
            "parsed_previews": [],
            "required_confirm": required_confirm,
            "blockers": ["confirm_RUN_TOP_EXPANSION_RAW_CONTEXT_LOOKUP_required"],
            "would_call_external": True,
            "can_detect_reliable_manipulation_now": False,
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
            "candidate_pool_address": row_filter.get("candidate_pool_address"),
            "filter_family": row_filter.get("filter_family"),
            "filter_type": row_filter.get("filter_type"),
            "range_id": row_filter.get("range_id"),
            "event_name": event_name,
            "chain": row_filter.get("chain"),
            "address": str(log.get("address") or row_filter.get("address") or "").lower(),
            "block_number": _log_int(log.get("blockNumber")),
            "block_timestamp": _log_int(log.get("timestamp")),
            "tx_hash": str(log.get("transactionHash") or "").lower() or None,
            "log_index": _log_int(log.get("logIndex")),
            "topic0": topics[0] if topics else (row_filter.get("topics") or [None])[0],
            "data_digest": hashlib.sha256(str(log.get("data") or "0x").encode("utf-8")).hexdigest(),
            "event_dedupe_key": (
                f"{row_filter.get('chain')}|{event_name}|"
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
        elif event_name in {"Mint", "Burn"}:
            preview.update({
                "sender": _topic_address(topics, 1),
                "amount0": words[0] if len(words) > 0 else None,
                "amount1": words[1] if len(words) > 1 else None,
            })
            if event_name == "Burn":
                preview["to"] = _topic_address(topics, 2)
        elif event_name == "ERC20 Transfer":
            preview.update({
                "from": _topic_address(topics, 1),
                "to": _topic_address(topics, 2),
                "amount": words[0] if len(words) > 0 else None,
            })
        return preview

    event_counts: dict[str, int] = {}
    candidate_event_counts: dict[str, dict[str, int]] = {}
    endpoint_counts: dict[str, int] = {}
    key_sources: dict[str, int] = {}
    endpoint_statuses: list[dict[str, Any]] = []
    parsed_previews: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total_logs_seen = 0
    truncated = False
    per_filter_truncated = False

    for row_filter in selected_filters:
        if total_logs_seen >= safe_logs_total:
            truncated = True
            break
        topics = list(row_filter.get("topics") or [])
        log_filter = {
            "address": row_filter.get("address"),
            "fromBlock": hex(int(row_filter.get("from_block") or 0)),
            "toBlock": hex(int(row_filter.get("to_block") or 0)),
            "topics": topics,
        }
        logs, endpoint, error, key_source, request_preview = _engine()._sqd_portal_event_logs(
            clean_chain,
            log_filter,
            timeout=safe_timeout,
        )
        event_name = str(row_filter.get("event_name") or "unknown")
        candidate_pool = str(row_filter.get("candidate_pool_address") or "unknown").lower()
        if endpoint:
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1
        if key_source:
            key_sources[key_source] = key_sources.get(key_source, 0) + 1
        status = {
            "candidate_pool_address": candidate_pool,
            "filter_family": row_filter.get("filter_family"),
            "filter_type": row_filter.get("filter_type"),
            "event_name": event_name,
            "address": row_filter.get("address"),
            "from_block": row_filter.get("from_block"),
            "to_block": row_filter.get("to_block"),
            "parent_from_block": row_filter.get("parent_from_block"),
            "parent_to_block": row_filter.get("parent_to_block"),
            "chunk_index": row_filter.get("chunk_index"),
            "endpoint": endpoint,
            "api_key_source": key_source,
            "api_key_configured": bool((request_preview or {}).get("api_key_configured")),
            "log_count": len(logs),
            "error": error,
        }
        endpoint_statuses.append(status)
        if error:
            errors.append(status)
            continue
        remaining_logs = min(safe_logs_per_filter, max(0, safe_logs_total - total_logs_seen))
        selected_logs = logs[:remaining_logs]
        skipped_logs = max(0, len(logs) - len(selected_logs))
        if skipped_logs:
            truncated = True
            per_filter_truncated = True
            status["truncated_log_count"] = skipped_logs
        total_logs_seen += len(selected_logs)
        event_counts[event_name] = event_counts.get(event_name, 0) + len(selected_logs)
        by_candidate = candidate_event_counts.setdefault(candidate_pool, {})
        by_candidate[event_name] = by_candidate.get(event_name, 0) + len(selected_logs)
        for log in selected_logs:
            if len(parsed_previews) >= min(clean_limit, safe_logs_total):
                break
            parsed_previews.append(_preview(row_filter, log))
        if total_logs_seen >= safe_logs_total:
            truncated = True
            break

    lookup_digest = _sync_liquidity_payload_digest({
        "plan_digest": plan.get("raw_context_collection_plan_digest"),
        "selected_filters": [
            {
                "candidate_pool_address": row.get("candidate_pool_address"),
                "filter_type": row.get("filter_type"),
                "address": row.get("address"),
                "from_block": row.get("from_block"),
                "to_block": row.get("to_block"),
                "parent_from_block": row.get("parent_from_block"),
                "parent_to_block": row.get("parent_to_block"),
                "chunk_index": row.get("chunk_index"),
                "topics": row.get("topics"),
            }
            for row in selected_filters
        ],
        "event_counts": event_counts,
        "candidate_event_counts": candidate_event_counts,
    })
    partial = len(selected_filters) < len(planned_filter_chunks)
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
        "raw_context_collection_plan_digest": plan.get("raw_context_collection_plan_digest"),
        "raw_context_lookup_digest": lookup_digest,
        "candidate_count": len(candidate_plans),
        "planned_filter_count": len(planned_filters),
        "planned_filter_chunk_count": len(planned_filter_chunks),
        "selected_filter_count": len(selected_filters),
        "selection_strategy": "balanced_candidate_event_coverage",
        "max_logs_per_filter": safe_logs_per_filter,
        "external_calls_performed": len(endpoint_statuses),
        "total_logs_seen": total_logs_seen,
        "event_counts": event_counts,
        "candidate_event_counts": candidate_event_counts,
        "endpoint_counts": endpoint_counts,
        "api_key_sources_used": key_sources,
        "endpoint_statuses": endpoint_statuses[:safe_sqd_calls],
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
            "source_backed_replay_not_run",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "raw_context_evidence_only_schema_plan_read_only"
            if total_logs_seen and not errors else
            "repair_sqd_lookup_or_reduce_filters"
        ),
        "plain_summary_fr": (
            "Le lookup borne a recupere du contexte brut en memoire pour les meilleurs candidats. Rien n'est "
            "encore sauvegarde; cette data sert seulement a verifier si ces pistes peuvent devenir backtestables."
            if total_logs_seen else
            "Le lookup borne n'a pas encore recupere de logs exploitables. Les candidats restent des pistes de recherche."
        ),
        "would_call_external": True,
        "can_detect_reliable_manipulation_now": False,
        "client_signal_ready": False,
        "trade_ready": False,
        **disabled,
    }


def get_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_candidates: int = 3,
    max_window_blocks: int = 5000,
    max_sqd_calls: int = 9,
    max_logs_total: int = 450,
    max_logs_per_filter: int = 50,
    max_sqd_block_span: int = 1000,
) -> dict[str, Any]:
    """Read-only schema plan for future top expansion raw-context evidence persistence."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_candidates = max(1, min(int(max_candidates or 3), 10))
    safe_max_window_blocks = max(100, min(int(max_window_blocks or 5000), 25000))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 9), 100))
    safe_logs_total = max(1, min(int(max_logs_total or 450), 10000))
    safe_logs_per_filter = max(1, min(int(max_logs_per_filter or 50), safe_logs_total))
    safe_sqd_block_span = max(1, min(int(max_sqd_block_span or 1000), safe_max_window_blocks))
    source_policy = (
        "admin-only read-only schema plan for top expansion raw context evidence-only persistence. It reuses "
        "existing raw event tables, does not call SQD/RPC/providers, creates no tables, inserts no rows, creates "
        "no mapping/router evidence/label, emits no client signal, executes no trade and creates no opt-in."
    )
    disabled = {
        "would_call_external": False,
        "would_call_provider": False,
        "would_create_table": False,
        "would_insert_raw_context": False,
        "would_persist_evidence": False,
        "would_create_source_backed_score": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
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
            "plan_status": "blocked",
            "chain": clean_chain,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    lookup_preview = run_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        allow_external=False,
        confirm=None,
        min_swaps=safe_min_swaps,
        max_candidates=safe_max_candidates,
        max_window_blocks=safe_max_window_blocks,
        max_sqd_calls=safe_sqd_calls,
        max_logs_total=safe_logs_total,
        max_logs_per_filter=safe_logs_per_filter,
        max_sqd_block_span=safe_sqd_block_span,
    )
    target_tables = ["dex_raw_swap_events", "dex_raw_sync_events", "erc20_transfer_events"]
    optional_tables = ["dex_raw_liquidity_events"]
    table_plans: dict[str, dict[str, Any]] = {
        "dex_raw_swap_events": {
            "purpose": "exact Swap observations for expansion candidate repeatability and outcome replay",
            "event_names": ["Swap"],
            "schema_preview": [
                "id INTEGER PRIMARY KEY AUTOINCREMENT",
                "checkpoint_id INTEGER",
                "chain TEXT NOT NULL",
                "pair_address TEXT NOT NULL",
                "sender TEXT",
                "recipient TEXT",
                "amount0_in TEXT NOT NULL",
                "amount1_in TEXT NOT NULL",
                "amount0_out TEXT NOT NULL",
                "amount1_out TEXT NOT NULL",
                "tx_hash TEXT NOT NULL",
                "log_index INTEGER NOT NULL",
                "block_number INTEGER NOT NULL",
                "block_hash TEXT",
                "block_timestamp INTEGER",
                "event_topic TEXT NOT NULL",
                "raw_log_json TEXT NOT NULL",
                "payload_digest TEXT NOT NULL",
                "event_dedupe_key TEXT NOT NULL UNIQUE",
                "status TEXT NOT NULL DEFAULT 'raw_observed'",
                "created_at TEXT NOT NULL",
                "source_policy TEXT NOT NULL",
            ],
            "indexes_preview": [
                "UNIQUE INDEX dex_raw_swap_events_dedupe_uq ON event_dedupe_key",
                "INDEX dex_raw_swap_events_chain_pair_idx ON chain, pair_address",
                "INDEX dex_raw_swap_events_tx_log_idx ON tx_hash, log_index",
                "INDEX dex_raw_swap_events_block_idx ON block_number",
            ],
            "dedupe_key": "chain|Swap|pair_address|tx_hash|log_index",
        },
        "dex_raw_sync_events": {
            "purpose": "reserve/liquidity context for expansion candidate outcome quality",
            "event_names": ["Sync"],
            "schema_preview": [
                "id INTEGER PRIMARY KEY AUTOINCREMENT",
                "checkpoint_id INTEGER",
                "chain TEXT NOT NULL",
                "pair_address TEXT NOT NULL",
                "reserve0 TEXT NOT NULL",
                "reserve1 TEXT NOT NULL",
                "tx_hash TEXT NOT NULL",
                "log_index INTEGER NOT NULL",
                "block_number INTEGER NOT NULL",
                "raw_log_json TEXT NOT NULL",
                "payload_digest TEXT NOT NULL",
                "event_dedupe_key TEXT NOT NULL UNIQUE",
                "status TEXT NOT NULL DEFAULT 'raw_observed'",
                "created_at TEXT NOT NULL",
                "source_policy TEXT NOT NULL",
            ],
            "indexes_preview": [
                "UNIQUE INDEX dex_raw_sync_events_dedupe_uq ON event_dedupe_key",
                "INDEX dex_raw_sync_events_chain_pair_idx ON chain, pair_address",
                "INDEX dex_raw_sync_events_block_idx ON block_number",
            ],
            "dedupe_key": "chain|Sync|pair_address|tx_hash|log_index",
        },
        "erc20_transfer_events": {
            "purpose": "ERC20 Transfer observations into/out of pools for wallet/funding context",
            "event_names": ["ERC20 Transfer"],
            "schema_preview": [
                "id INTEGER PRIMARY KEY AUTOINCREMENT",
                "checkpoint_id INTEGER",
                "chain TEXT NOT NULL",
                "token_address TEXT NOT NULL",
                "from_address TEXT NOT NULL",
                "to_address TEXT NOT NULL",
                "value_raw TEXT NOT NULL",
                "tx_hash TEXT NOT NULL",
                "log_index INTEGER NOT NULL",
                "block_number INTEGER NOT NULL",
                "raw_log_json TEXT NOT NULL",
                "payload_digest TEXT NOT NULL",
                "event_dedupe_key TEXT NOT NULL UNIQUE",
                "status TEXT NOT NULL DEFAULT 'raw_observed'",
                "created_at TEXT NOT NULL",
                "source_policy TEXT NOT NULL",
            ],
            "indexes_preview": [
                "UNIQUE INDEX erc20_transfer_events_dedupe_uq ON event_dedupe_key",
                "INDEX erc20_transfer_events_chain_token_idx ON chain, token_address",
                "INDEX erc20_transfer_events_from_to_idx ON from_address, to_address",
                "INDEX erc20_transfer_events_tx_log_idx ON tx_hash, log_index",
            ],
            "dedupe_key": "chain|Transfer|token_address|tx_hash|log_index",
        },
        "dex_raw_liquidity_events": {
            "purpose": "optional Mint/Burn context if future expansion persistence includes liquidity add/remove",
            "event_names": ["Mint", "Burn"],
            "schema_preview": [
                "id INTEGER PRIMARY KEY AUTOINCREMENT",
                "checkpoint_id INTEGER",
                "chain TEXT NOT NULL",
                "pair_address TEXT NOT NULL",
                "event_name TEXT NOT NULL",
                "sender TEXT",
                "recipient TEXT",
                "amount0 TEXT NOT NULL",
                "amount1 TEXT NOT NULL",
                "tx_hash TEXT NOT NULL",
                "log_index INTEGER NOT NULL",
                "block_number INTEGER NOT NULL",
                "raw_log_json TEXT NOT NULL",
                "payload_digest TEXT NOT NULL",
                "event_dedupe_key TEXT NOT NULL UNIQUE",
                "status TEXT NOT NULL DEFAULT 'raw_observed'",
                "created_at TEXT NOT NULL",
                "source_policy TEXT NOT NULL",
            ],
            "indexes_preview": [
                "UNIQUE INDEX dex_raw_liquidity_events_dedupe_uq ON event_dedupe_key",
                "INDEX dex_raw_liquidity_events_chain_pair_event_idx ON chain, pair_address, event_name",
                "INDEX dex_raw_liquidity_events_tx_log_idx ON tx_hash, log_index",
            ],
            "dedupe_key": "chain|event_name|pair_address|tx_hash|log_index",
        },
    }
    conn = _get_db()
    try:
        for table_name, table_plan in table_plans.items():
            exists = _table_exists(conn, table_name)
            table_plan["table_exists"] = exists
            table_plan["migration_required"] = False
            table_plan["row_count"] = int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0] or 0) if exists else 0
    finally:
        conn.close()

    missing_required = [
        table_name for table_name in target_tables if not table_plans.get(table_name, {}).get("table_exists")
    ]
    blockers = list(dict.fromkeys([
        *([] if lookup_preview.get("lookup_status") == "ready_but_external_disabled" else ["lookup_preview_not_ready"]),
        *[f"{table_name}_missing" for table_name in missing_required],
        "external_lookup_not_executed",
        "raw_context_not_persisted",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    ready = not missing_required and lookup_preview.get("lookup_status") == "ready_but_external_disabled"
    plan_digest = _sync_liquidity_payload_digest({
        "chain": clean_chain,
        "lookup_plan_digest": lookup_preview.get("raw_context_collection_plan_digest"),
        "target_tables": target_tables,
        "selected_filter_count": lookup_preview.get("selected_filter_count"),
        "max_sqd_calls": safe_sqd_calls,
        "max_logs_total": safe_logs_total,
        "max_logs_per_filter": safe_logs_per_filter,
        "max_sqd_block_span": safe_sqd_block_span,
    })
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if ready else "blocked",
        "chain": clean_chain,
        "target_tables": target_tables,
        "optional_tables": optional_tables,
        "table_plans": table_plans,
        "schema_plan_digest": plan_digest,
        "lookup_preview": {
            "lookup_status": lookup_preview.get("lookup_status"),
            "candidate_count": lookup_preview.get("candidate_count"),
            "planned_filter_count": lookup_preview.get("planned_filter_count"),
            "planned_filter_chunk_count": lookup_preview.get("planned_filter_chunk_count"),
            "selected_filter_count": lookup_preview.get("selected_filter_count"),
            "selection_strategy": lookup_preview.get("selection_strategy"),
            "max_logs_per_filter": lookup_preview.get("max_logs_per_filter"),
            "required_confirm": lookup_preview.get("required_confirm"),
        },
        "future_insert_requirements": {
            "required_preview_confirm": "RUN_TOP_EXPANSION_RAW_CONTEXT_LOOKUP",
            "required_persist_confirm": "PERSIST_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE",
            "expected_raw_context_lookup_digest_required": True,
            "duplicate_event_dedupe_key_blocks": True,
            "no_overwrite": True,
            "no_upsert": True,
        },
        "summary": {
            "target_tables": len(target_tables),
            "target_tables_existing": sum(1 for table_name in target_tables if table_plans[table_name]["table_exists"]),
            "selected_filter_count": lookup_preview.get("selected_filter_count"),
            "candidate_count": lookup_preview.get("candidate_count"),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": blockers,
        "next_safe_step": (
            "top_expansion_raw_context_evidence_insert_dry_run_first"
            if ready else "repair_missing_raw_event_tables_or_lookup_plan"
        ),
        "plain_summary_fr": (
            "Le plan de persistence evidence-only est pret: les futurs samples Swap, Sync et Transfer iraient "
            "dans les tables raw existantes, avec dedupe strict. Rien n'est cree ou insere maintenant."
            if ready else
            "Le plan de persistence est bloque: une table raw requise ou le preview lookup manque."
        ),
        "can_detect_reliable_manipulation_now": False,
        "client_signal_ready": False,
        "trade_ready": False,
        **disabled,
    }


def insert_manipulation_detection_source_backed_top_expansion_raw_context_evidence(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_raw_context_lookup_digest: str | None = None,
    min_swaps: int = 4,
    max_candidates: int = 3,
    max_window_blocks: int = 5000,
    max_sqd_calls: int = 9,
    max_logs_total: int = 450,
    max_logs_per_filter: int = 50,
    max_sqd_block_span: int = 1000,
    timeout: int = 8,
) -> dict[str, Any]:
    """Dry-run-first persistence for top-expansion raw Swap/Sync/Transfer context only."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    clean_token = str(token_address or "").strip().lower()
    clean_limit = max(1, min(int(limit or 25), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 4), 50))
    safe_max_candidates = max(1, min(int(max_candidates or 3), 10))
    safe_max_window_blocks = max(100, min(int(max_window_blocks or 5000), 25000))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 9), 100))
    safe_logs_total = max(1, min(int(max_logs_total or 450), 10000))
    safe_logs_per_filter = max(1, min(int(max_logs_per_filter or 50), safe_logs_total))
    safe_sqd_block_span = max(1, min(int(max_sqd_block_span or 1000), safe_max_window_blocks))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    preview_confirm = "PREVIEW_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_INSERT"
    lookup_confirm = "RUN_TOP_EXPANSION_RAW_CONTEXT_LOOKUP"
    insert_confirm = "INSERT_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE"
    required_tables = ["dex_raw_swap_events", "dex_raw_sync_events", "erc20_transfer_events"]
    source_policy = (
        "admin-confirmed dry-run-first top expansion raw context persistence. It inserts only raw Swap, Sync "
        "and ERC20 Transfer observations into existing raw event tables. It creates no mapping, router evidence, "
        "label, client signal, trade, wallet order or opt-in."
    )
    disabled = {
        "would_create_source_backed_score": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_backed_scoring": False,
        "client_signal_ready": False,
        "trade_ready": False,
        "source_policy": source_policy,
    }
    blockers: list[str] = []
    if not allow_external:
        blockers.append("allow_external_required_for_insert_preview")
    if dry_run and allow_external and confirm not in {preview_confirm, lookup_confirm, insert_confirm}:
        blockers.append("confirm_PREVIEW_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_INSERT_required")
    if not dry_run:
        if confirm != insert_confirm:
            blockers.append("confirm_INSERT_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_required")
        if not str(expected_raw_context_lookup_digest or "").strip():
            blockers.append("expected_raw_context_lookup_digest_required")

    schema_plan = get_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_candidates=safe_max_candidates,
        max_window_blocks=safe_max_window_blocks,
        max_sqd_calls=safe_sqd_calls,
        max_logs_total=safe_logs_total,
        max_logs_per_filter=safe_logs_per_filter,
        max_sqd_block_span=safe_sqd_block_span,
    )
    if schema_plan.get("plan_status") != "ready_but_disabled":
        blockers.append("raw_context_evidence_schema_plan_not_ready")

    plan = get_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        token_address=clean_token or None,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        max_candidates=safe_max_candidates,
        max_window_blocks=safe_max_window_blocks,
    )
    candidate_plans = [
        row for row in list(plan.get("candidate_plans") or [])
        if row.get("collection_readiness") == "ready_for_bounded_lookup_dry_run"
    ]
    planned_filters: list[dict[str, Any]] = []
    for candidate in candidate_plans:
        pool = str(candidate.get("pool_address") or "").lower()
        for family, fallback_event in (
            ("raw_swap_filters", "Swap"),
            ("sync_liquidity_filters", None),
            ("transfer_filters", "ERC20 Transfer"),
        ):
            for row_filter in list(candidate.get(family) or []):
                planned_filters.append({
                    **row_filter,
                    "pool_address": pool,
                    "candidate_pool_address": pool,
                    "event_name": row_filter.get("event_name") or fallback_event,
                    "filter_family": family,
                })

    def _chunk_filter(row_filter: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            start = int(row_filter.get("from_block") or 0)
            end = int(row_filter.get("to_block") or 0)
        except (TypeError, ValueError):
            return []
        chunks = []
        cursor = start
        chunk_index = 0
        while cursor <= end:
            chunk_end = min(end, cursor + safe_sqd_block_span - 1)
            chunks.append({
                **row_filter,
                "parent_from_block": start,
                "parent_to_block": end,
                "chunk_index": chunk_index,
                "from_block": cursor,
                "to_block": chunk_end,
            })
            cursor = chunk_end + 1
            chunk_index += 1
        return chunks

    def _bucket(row_filter: dict[str, Any]) -> str:
        event_name = str(row_filter.get("event_name") or "").lower()
        if event_name == "swap":
            return "swap"
        if event_name == "sync":
            return "sync"
        if event_name == "erc20 transfer":
            return "transfer"
        if event_name in {"mint", "burn"}:
            return "liquidity"
        return event_name or "unknown"

    def _balanced_select(chunks: list[dict[str, Any]], limit_count: int) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        pools: list[str] = []
        for item in chunks:
            pool = str(item.get("candidate_pool_address") or "")
            if pool and pool not in pools:
                pools.append(pool)
        for bucket in ["swap", "sync", "transfer", "liquidity"]:
            for pool in pools:
                for index, item in enumerate(chunks):
                    if index in seen_ids:
                        continue
                    if str(item.get("candidate_pool_address") or "") != pool:
                        continue
                    if _bucket(item) != bucket:
                        continue
                    selected.append(item)
                    seen_ids.add(index)
                    if len(selected) >= limit_count:
                        return selected
                    break
        for index, item in enumerate(chunks):
            if len(selected) >= limit_count:
                break
            if index not in seen_ids:
                selected.append(item)
        return selected

    planned_filter_chunks = [
        chunk
        for row_filter in planned_filters
        for chunk in _chunk_filter(row_filter)
    ]
    selected_filters = _balanced_select(planned_filter_chunks, safe_sqd_calls)
    if plan.get("plan_status") != "ready_but_disabled":
        blockers.append("collection_plan_not_ready")
    if not candidate_plans:
        blockers.append("no_ready_candidate_plans")
    if not selected_filters:
        blockers.append("no_selected_filters")

    table_status: dict[str, dict[str, Any]] = {}
    conn = _get_db()
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

    if blockers:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "insert_status": "blocked",
            "chain": clean_chain,
            "candidate_count": len(candidate_plans),
            "planned_filter_count": len(planned_filters),
            "planned_filter_chunk_count": len(planned_filter_chunks),
            "selected_filter_count": len(selected_filters),
            "table_status": table_status,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "blockers": list(dict.fromkeys(blockers)),
            "would_call_external": False,
            "external_calls_performed": 0,
            "total_logs_seen": 0,
            "raw_event_candidates": 0,
            "clean_raw_event_candidates": 0,
            "would_insert_raw_context": False,
            "inserted": False,
            "rows_inserted": 0,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            **disabled,
        }

    call_results: list[dict[str, Any]] = []
    raw_candidates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    event_counts: dict[str, int] = {}
    candidate_event_counts: dict[str, dict[str, int]] = {}
    total_logs_seen = 0
    truncated = False

    for row_filter in selected_filters:
        if total_logs_seen >= safe_logs_total:
            truncated = True
            break
        log_filter = {
            "address": row_filter.get("address"),
            "fromBlock": hex(int(row_filter.get("from_block") or 0)),
            "toBlock": hex(int(row_filter.get("to_block") or 0)),
            "topics": list(row_filter.get("topics") or []),
        }
        logs, endpoint, error, key_source, request_preview = _engine()._sqd_portal_event_logs(
            clean_chain,
            log_filter,
            timeout=safe_timeout,
        )
        event_name = str(row_filter.get("event_name") or "unknown")
        candidate_pool = str(row_filter.get("candidate_pool_address") or "unknown").lower()
        call_status = {
            "candidate_pool_address": candidate_pool,
            "filter_family": row_filter.get("filter_family"),
            "filter_type": row_filter.get("filter_type"),
            "event_name": event_name,
            "address": row_filter.get("address"),
            "from_block": row_filter.get("from_block"),
            "to_block": row_filter.get("to_block"),
            "endpoint": endpoint,
            "api_key_source": key_source,
            "api_key_configured": bool((request_preview or {}).get("api_key_configured")),
            "log_count": len(logs),
            "error": error,
        }
        call_results.append(call_status)
        if error:
            errors.append(call_status)
            continue
        remaining_logs = min(safe_logs_per_filter, max(0, safe_logs_total - total_logs_seen))
        selected_logs = logs[:remaining_logs]
        total_logs_seen += len(selected_logs)
        event_counts[event_name] = event_counts.get(event_name, 0) + len(selected_logs)
        by_candidate = candidate_event_counts.setdefault(candidate_pool, {})
        by_candidate[event_name] = by_candidate.get(event_name, 0) + len(selected_logs)
        if len(logs) > len(selected_logs):
            truncated = True
            call_status["truncated_log_count"] = len(logs) - len(selected_logs)
        for log in selected_logs:
            raw_candidates.append(_build_top_expansion_raw_event_candidate(row_filter, log, source_policy))

    event_dedupe_keys = [
        str(row.get("event_dedupe_key") or "")
        for row in raw_candidates
        if row.get("event_dedupe_key") and row.get("row_status") == "eligible"
    ]
    raw_context_lookup_digest = _sync_liquidity_payload_digest({
        "plan_digest": plan.get("raw_context_collection_plan_digest"),
        "selected_filters": [
            {
                "candidate_pool_address": row.get("candidate_pool_address"),
                "filter_type": row.get("filter_type"),
                "address": row.get("address"),
                "from_block": row.get("from_block"),
                "to_block": row.get("to_block"),
                "parent_from_block": row.get("parent_from_block"),
                "parent_to_block": row.get("parent_to_block"),
                "chunk_index": row.get("chunk_index"),
                "topics": row.get("topics"),
            }
            for row in selected_filters
        ],
        "event_counts": event_counts,
        "candidate_event_counts": candidate_event_counts,
    })

    duplicate_keys: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    conn = _get_db()
    try:
        for candidate in raw_candidates:
            if candidate.get("row_status") != "eligible":
                continue
            table_name = str(candidate.get("target_table") or "")
            dedupe_key = str(candidate.get("event_dedupe_key") or "")
            if table_name not in required_tables or not dedupe_key:
                continue
            columns = set(table_status.get(table_name, {}).get("columns") or [])
            insert_columns = set((candidate.get("insert_values") or {}).keys())
            missing = sorted(insert_columns - columns)
            if missing:
                missing_columns.setdefault(table_name, [])
                missing_columns[table_name] = sorted(set(missing_columns[table_name] + missing))
                continue
            row = conn.execute(
                f"SELECT id FROM {table_name} WHERE event_dedupe_key = ? LIMIT 1",
                (dedupe_key,),
            ).fetchone()
            if row:
                duplicate_keys.append(dedupe_key)
    finally:
        conn.close()

    candidate_blockers = [
        blocker
        for candidate in raw_candidates
        for blocker in list(candidate.get("row_blockers") or [])
    ]
    if errors:
        blockers.append("sqd_lookup_errors_observed")
    if truncated:
        warnings.append("lookup_truncated_by_bounded_limits")
    if candidate_blockers:
        blockers.append("raw_candidate_parse_blockers")
    if missing_columns:
        blockers.append("raw_target_table_missing_columns")
    if duplicate_keys:
        blockers.append("duplicate_event_dedupe_key")
    if not raw_candidates:
        blockers.append("no_raw_context_logs_to_insert")
    if not event_dedupe_keys:
        blockers.append("no_clean_raw_context_candidates")
    if not dry_run and raw_context_lookup_digest != str(expected_raw_context_lookup_digest or "").strip():
        blockers.append("expected_raw_context_lookup_digest_mismatch")

    clean_candidates = [
        candidate for candidate in raw_candidates
        if candidate.get("row_status") == "eligible"
        and candidate.get("event_dedupe_key") not in duplicate_keys
        and not missing_columns.get(str(candidate.get("target_table") or ""))
    ]
    target_counts: dict[str, int] = {}
    for candidate in clean_candidates:
        table_name = str(candidate.get("target_table") or "")
        target_counts[table_name] = target_counts.get(table_name, 0) + 1
    blockers = list(dict.fromkeys(blockers))
    would_insert = bool(not blockers and clean_candidates)
    if dry_run or blockers:
        return {
            "ok": bool(not blockers),
            "dry_run": bool(dry_run),
            "insert_status": "ready_for_insert" if would_insert else "blocked",
            "chain": clean_chain,
            "candidate_count": len(candidate_plans),
            "planned_filter_count": len(planned_filters),
            "planned_filter_chunk_count": len(planned_filter_chunks),
            "selected_filter_count": len(selected_filters),
            "external_calls_performed": len(call_results),
            "total_logs_seen": total_logs_seen,
            "event_counts": event_counts,
            "candidate_event_counts": candidate_event_counts,
            "raw_event_candidates": len(raw_candidates),
            "clean_raw_event_candidates": len(clean_candidates),
            "target_insert_counts": target_counts,
            "raw_context_lookup_digest": raw_context_lookup_digest,
            "expected_raw_context_lookup_digest": expected_raw_context_lookup_digest,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "call_results": call_results,
            "raw_event_previews": [row.get("preview") for row in raw_candidates[:25]],
            "duplicate_event_dedupe_keys": duplicate_keys[:25],
            "missing_columns": missing_columns,
            "warnings": warnings,
            "blockers": blockers,
            "would_call_external": True,
            "would_insert_raw_context": would_insert,
            "would_insert_raw_context_count": len(clean_candidates) if would_insert else 0,
            "inserted": False,
            "rows_inserted": 0,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            **disabled,
        }

    conn = _get_db()
    try:
        for candidate in clean_candidates:
            table_name = str(candidate.get("target_table") or "")
            insert_values = dict(candidate.get("insert_values") or {})
            if table_name == "dex_raw_sync_events":
                insert_values["created_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                insert_values["source_policy"] = source_policy
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
        "candidate_count": len(candidate_plans),
        "selected_filter_count": len(selected_filters),
        "external_calls_performed": len(call_results),
        "total_logs_seen": total_logs_seen,
        "event_counts": event_counts,
        "candidate_event_counts": candidate_event_counts,
        "raw_event_candidates": len(raw_candidates),
        "clean_raw_event_candidates": len(clean_candidates),
        "target_insert_counts": target_counts,
        "raw_context_lookup_digest": raw_context_lookup_digest,
        "row_counts_after": row_counts_after,
        "warnings": warnings,
        "inserted": True,
        "rows_inserted": len(clean_candidates),
        "would_call_external": False,
        "would_insert_raw_context": False,
        "would_write": False,
        "real_write_enabled": True,
        "writes_performed": len(clean_candidates),
        "blockers": [],
        **disabled,
    }
