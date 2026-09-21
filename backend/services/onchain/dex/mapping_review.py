"""Read-only DEX mapping review contract helpers.

The large ``services.onchain_engine`` module remains the compatibility facade.
These helpers receive DB/table dependencies from the facade so existing tests
that patch facade-level DB behavior keep working.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from services.onchain.core.addresses import _is_evm_address
from services.onchain.core.constants import PAIR_CREATED_TOPIC

GetDb = Callable[[], sqlite3.Connection]
TableExists = Callable[[sqlite3.Connection, str], bool]


def build_dex_mapping_review_contract(
    paircreated_evidence_id: int | None,
    dry_run: bool,
    *,
    get_db: GetDb,
    table_exists: TableExists,
    official_venue_source_rules: dict[str, Any],
) -> dict[str, Any]:
    """Build the read-only future mapping-review contract from accepted PairCreated evidence."""
    blockers: list[str] = [] if dry_run else ["dry_run_required"]
    if paircreated_evidence_id is None:
        blockers.append("paircreated_evidence_id_required")

    evidence: dict[str, Any] | None = None
    conn = get_db()
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "dex_paircreated_evidence"):
            blockers.append("dex_paircreated_evidence_table_missing")
        elif paircreated_evidence_id is not None:
            row = conn.execute(
                "SELECT * FROM dex_paircreated_evidence WHERE id = ? LIMIT 1",
                (paircreated_evidence_id,),
            ).fetchone()
            if row is None:
                blockers.append("paircreated_evidence_missing")
            else:
                evidence = dict(row)
    finally:
        conn.close()

    source_status = evidence.get("status") if evidence else None
    chain = str((evidence or {}).get("chain") or "").strip().lower()
    official_venue = str((evidence or {}).get("official_venue") or "").strip()
    venue_key = re.sub(r"[^a-z0-9]+", "_", official_venue.lower()).strip("_") if official_venue else None
    factory = str((evidence or {}).get("factory_address") or "").strip().lower()
    pair = str((evidence or {}).get("pair_address") or "").strip().lower()
    tx_hash = str((evidence or {}).get("tx_hash") or "").strip().lower()
    log_index = (evidence or {}).get("log_index")
    block_number = (evidence or {}).get("block_number")
    token0 = str((evidence or {}).get("token0") or "").strip().lower()
    token1 = str((evidence or {}).get("token1") or "").strip().lower()
    current_paircreated_dedupe_key = (
        f"{chain}|{factory}|{tx_hash}|{log_index}|{pair}"
        if all([chain, factory, tx_hash, pair]) and log_index is not None
        else None
    )
    stored_paircreated_dedupe_key = str((evidence or {}).get("paircreated_dedupe_key") or "").strip()
    paircreated_dedupe_bound = bool(
        current_paircreated_dedupe_key and stored_paircreated_dedupe_key == current_paircreated_dedupe_key
    )

    raw_payload = None
    payload_json_valid = False
    current_payload_digest = None
    payload_digest_bound = False
    try:
        raw_payload = json.loads((evidence or {}).get("raw_payload_json") or "")
        payload_json_valid = isinstance(raw_payload, dict)
    except (TypeError, json.JSONDecodeError):
        raw_payload = None
    if payload_json_valid:
        current_payload_digest = hashlib.sha256(
            json.dumps(raw_payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        payload_digest_bound = bool(
            (evidence or {}).get("evidence_payload_digest")
            and (evidence or {}).get("evidence_payload_digest") == current_payload_digest
        )

    venue_rules = official_venue_source_rules.get(official_venue) or {}
    official_factory_addresses = {
        str(addr).lower()
        for addr in ((venue_rules.get("official_factory_addresses") or {}).get(chain) or [])
    }
    official_factory_bound = bool(factory and factory in official_factory_addresses)
    paircreated_topic_bound = str((evidence or {}).get("paircreated_event_topic") or "").strip().lower() == PAIR_CREATED_TOPIC

    required_fields = [
        "paircreated_evidence_id",
        "chain",
        "official_venue",
        "factory_address",
        "pair_address",
        "token0",
        "token1",
        "tx_hash",
        "log_index",
        "block_number",
        "paircreated_event_topic",
        "paircreated_dedupe_key",
        "evidence_payload_digest",
        "raw_payload_json",
        "source_type",
        "source_url",
        "source_tier",
        "status",
    ]
    if evidence:
        for field in required_fields:
            if field == "paircreated_evidence_id":
                continue
            if evidence.get(field) in (None, ""):
                blockers.append(f"{field}_required")
        if source_status != "accepted_for_future_mapping_review":
            blockers.append("paircreated_evidence_not_accepted_for_mapping_review")
        if not paircreated_dedupe_bound:
            blockers.append("paircreated_dedupe_key_not_bound")
        if not payload_json_valid:
            blockers.append("raw_payload_json_invalid")
        if not payload_digest_bound:
            blockers.append("evidence_payload_digest_not_bound")
        if not official_factory_bound:
            blockers.append("official_factory_not_bound")
        if not paircreated_topic_bound:
            blockers.append("paircreated_event_topic_not_bound")
        if not _is_evm_address(factory):
            blockers.append("factory_address_invalid")
        if not _is_evm_address(pair):
            blockers.append("pair_address_invalid")
        if not _is_evm_address(token0):
            blockers.append("token0_invalid")
        if not _is_evm_address(token1):
            blockers.append("token1_invalid")

    mapping_dedupe_key = (
        f"{chain}|{venue_key}|{factory}|{pair}|{paircreated_evidence_id}"
        if evidence and chain and venue_key and factory and pair and paircreated_evidence_id is not None
        else None
    )
    proposed_mapping = {
        "chain": chain or None,
        "venue_family": official_venue or None,
        "venue_key": venue_key,
        "factory_address": factory or None,
        "pair_address": pair or None,
        "token0": token0 or None,
        "token0_symbol": (evidence or {}).get("token0_symbol"),
        "token1": token1 or None,
        "token1_symbol": (evidence or {}).get("token1_symbol"),
        "proof_type": "historical_paircreated_event",
        "source_type": (evidence or {}).get("source_type"),
        "future_status": "pending_mapping_review",
        "mapping_dedupe_key": mapping_dedupe_key,
        "confidence": "paircreated_evidence_accepted_pending_mapping_review" if evidence else None,
    }
    schema_preview = {
        "target_table": "dex_mapping_review_queue",
        "would_create_table": False,
        "fields": [
            "id",
            "paircreated_evidence_id",
            "chain",
            "venue_family",
            "factory_address",
            "pair_address",
            "token0",
            "token1",
            "proof_type",
            "source_type",
            "source_url",
            "mapping_dedupe_key",
            "status",
            "created_at",
            "source_policy",
        ],
        "status_default": "pending_mapping_review",
    }
    source_evidence = {
        "source_status": source_status,
        "source_type": (evidence or {}).get("source_type"),
        "source_label": (evidence or {}).get("source_label"),
        "source_url": (evidence or {}).get("source_url"),
        "source_tier": (evidence or {}).get("source_tier"),
        "paircreated_dedupe_key": stored_paircreated_dedupe_key or None,
        "current_paircreated_dedupe_key": current_paircreated_dedupe_key,
        "paircreated_dedupe_bound": paircreated_dedupe_bound,
        "evidence_payload_digest": (evidence or {}).get("evidence_payload_digest"),
        "current_evidence_payload_digest": current_payload_digest,
        "payload_json_valid": payload_json_valid,
        "payload_digest_bound": payload_digest_bound,
        "official_factory_bound": official_factory_bound,
        "paircreated_event_topic_bound": paircreated_topic_bound,
    }
    route_safety = {
        "paircreated_event_proves_pool_created_by_factory": bool(
            official_factory_bound and paircreated_topic_bound and pair and factory
        ),
        "paircreated_event_does_not_prove_router_execution": True,
        "mapping_requires_separate_review_queue": True,
        "mapping_requires_future_decision_and_confirm": True,
        "no_client_signal_route": True,
        "no_trade_route": True,
        "three_unmatched_pools_remain_research_only": True,
    }
    eligible_for_mapping_review = not blockers
    disabled_runtime_surfaces = [
        "dex_mapping_write",
        "dex_router_evidence_write",
        "client_signal",
        "trade_execution",
        "wallet_order",
        "client_opt_in",
        "external_provider_lookup",
        "scraping",
    ]

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "contract_status": "ready_but_disabled" if not blockers else "blocked",
        "paircreated_evidence_id": paircreated_evidence_id,
        "source_status": source_status,
        "proposed_mapping": proposed_mapping,
        "schema_preview": schema_preview,
        "required_fields": required_fields,
        "mapping_dedupe_key": mapping_dedupe_key,
        "source_evidence": source_evidence,
        "factory_address": factory or None,
        "pair_address": pair or None,
        "token0": token0 or None,
        "token1": token1 or None,
        "tx_hash": tx_hash or None,
        "log_index": log_index,
        "block_number": block_number,
        "route_safety": route_safety,
        "known_unmatched_research_only_pools": 3,
        "eligible_for_mapping_review": eligible_for_mapping_review,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "disabled_runtime_surfaces": disabled_runtime_surfaces,
        "source_backed_scoring": False,
        "mapping_ready_now": 0,
        "blockers": list(dict.fromkeys(blockers)),
        "would_create_mapping_review_row": False,
        "would_persist_paircreated_evidence": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": (
            "admin-only read-only DEX mapping review contract from accepted PairCreated evidence; no DB writes, "
            "no table creation, no mapping review row, no DEX mapping, no router evidence, no labels, "
            "no client signals, no trades, no wallet orders and no opt-ins"
        ),
    }


def build_dex_mapping_review_queue_schema_plan(
    paircreated_evidence_id: int | None,
    dry_run: bool,
    *,
    get_contract: Callable[[int | None, bool], dict[str, Any]],
    get_db: GetDb,
    table_exists: TableExists,
) -> dict[str, Any]:
    """Build the read-only schema plan for a future DEX mapping review queue."""
    contract = get_contract(paircreated_evidence_id, True)
    blockers: list[str] = list(contract.get("blockers") or [])
    if paircreated_evidence_id is None:
        blockers.append("paircreated_evidence_id_required")
    if not dry_run:
        blockers.append("dry_run_required")
    if contract.get("contract_status") != "ready_but_disabled":
        blockers.append("dex_mapping_review_contract_not_ready")

    target_table = "dex_mapping_review_queue"
    conn = get_db()
    try:
        exists = table_exists(conn, target_table)
    finally:
        conn.close()

    schema_preview = [
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "paircreated_evidence_id INTEGER NOT NULL",
        "chain TEXT NOT NULL",
        "venue_family TEXT NOT NULL",
        "venue_key TEXT NOT NULL",
        "factory_address TEXT NOT NULL",
        "pair_address TEXT NOT NULL",
        "token0 TEXT NOT NULL",
        "token0_symbol TEXT",
        "token1 TEXT NOT NULL",
        "token1_symbol TEXT",
        "proof_type TEXT NOT NULL",
        "source_type TEXT NOT NULL",
        "source_label TEXT",
        "source_url TEXT NOT NULL",
        "source_tier TEXT NOT NULL",
        "tx_hash TEXT NOT NULL",
        "log_index INTEGER NOT NULL",
        "block_number INTEGER NOT NULL",
        "paircreated_dedupe_key TEXT NOT NULL",
        "evidence_payload_digest TEXT NOT NULL",
        "mapping_dedupe_key TEXT NOT NULL UNIQUE",
        "mapping_contract_json TEXT NOT NULL",
        "status TEXT NOT NULL DEFAULT 'pending_mapping_review'",
        "created_at TEXT NOT NULL",
        "source_policy TEXT NOT NULL",
    ]
    indexes_preview = [
        "UNIQUE INDEX dex_mapping_review_queue_mapping_dedupe_uq ON mapping_dedupe_key",
        "INDEX dex_mapping_review_queue_paircreated_evidence_id_idx ON paircreated_evidence_id",
        "INDEX dex_mapping_review_queue_chain_venue_idx ON chain, venue_key",
        "INDEX dex_mapping_review_queue_chain_factory_idx ON chain, factory_address",
        "INDEX dex_mapping_review_queue_chain_pair_idx ON chain, pair_address",
        "INDEX dex_mapping_review_queue_token0_idx ON token0",
        "INDEX dex_mapping_review_queue_token1_idx ON token1",
        "INDEX dex_mapping_review_queue_tx_log_idx ON tx_hash, log_index",
        "INDEX dex_mapping_review_queue_status_idx ON status",
        "INDEX dex_mapping_review_queue_source_type_idx ON source_type",
    ]
    constraints_preview = {
        "status": [
            "pending_mapping_review",
            "accepted_for_future_mapping_decision",
            "needs_better_source",
            "rejected",
        ],
        "proof_type": ["historical_paircreated_event"],
        "source_type": [
            "sqd_portal_stream_api",
            "archive_rpc",
            "manual_source_backed_creation_package",
        ],
        "guards": [
            "paircreated_evidence_status_must_be_accepted_for_future_mapping_review",
            "paircreated_dedupe_must_remain_bound",
            "payload_digest_must_remain_bound",
            "official_factory_must_remain_bound",
            "paircreated_topic_must_remain_bound",
            "duplicate_mapping_dedupe_key_blocks_no_overwrite_no_upsert",
            "mapping_review_row_is_not_a_dex_mapping",
            "paircreated_event_does_not_prove_router_execution",
            "no_scoring_signal_trade_or_client_opt_in_route",
        ],
    }
    dedupe_constraints = {
        "source": "use_dex_mapping_review_contract_mapping_dedupe_key",
        "target_column": "mapping_dedupe_key",
        "mapping_dedupe_key": contract.get("mapping_dedupe_key"),
        "future_refusals": [
            "contract_blocked",
            "source_status_drift",
            "paircreated_dedupe_mismatch",
            "payload_digest_drift",
            "official_factory_drift",
            "paircreated_topic_drift",
            "duplicate_mapping_dedupe_key",
        ],
        "future_policy": "duplicate_blocks_no_overwrite_no_upsert_no_silent_success",
    }
    blockers = list(dict.fromkeys(blockers))
    ready = not blockers

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "plan_status": "ready_read_only" if ready else "blocked",
        "paircreated_evidence_id": paircreated_evidence_id,
        "target_table": target_table,
        "table_exists": exists,
        "migration_required": not exists,
        "schema_preview": schema_preview,
        "indexes_preview": indexes_preview,
        "constraints_preview": constraints_preview,
        "dedupe_constraints": dedupe_constraints,
        "mapping_dedupe_key": contract.get("mapping_dedupe_key"),
        "source_status": contract.get("source_status"),
        "contract_status": contract.get("contract_status"),
        "proposed_mapping": contract.get("proposed_mapping"),
        "source_evidence": contract.get("source_evidence"),
        "route_safety": contract.get("route_safety"),
        "known_unmatched_research_only_pools": 3,
        "source_backed_scoring": False,
        "mapping_ready_now": 0,
        "confirm_required": "CREATE_DEX_MAPPING_REVIEW_QUEUE" if not exists else None,
        "would_create_table": False,
        "would_create_mapping_review_row": False,
        "would_persist_paircreated_evidence": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "blockers": blockers,
        "source_policy": (
            "admin-only read-only DEX mapping review queue schema plan. It describes a future empty "
            "review table from an accepted PairCreated proof, but creates no table, no row, no DEX mapping, "
            "no router evidence, no label, no scoring, no client signal, no trade, no wallet order and no opt-in."
        ),
    }


def create_dex_mapping_review_queue_with_deps(
    paircreated_evidence_id: int | None,
    dry_run: bool,
    confirm: str | None,
    *,
    get_schema_plan: Callable[[int | None, bool], dict[str, Any]],
    get_db: GetDb,
    table_exists: TableExists,
) -> dict[str, Any]:
    """Create the empty mapping-review queue table through the facade-supplied DB hooks."""
    target_table = "dex_mapping_review_queue"
    plan = get_schema_plan(paircreated_evidence_id, True)
    blockers: list[str] = list(plan.get("blockers") or [])
    if paircreated_evidence_id is None:
        blockers.append("paircreated_evidence_id_required")
    if plan.get("plan_status") != "ready_read_only":
        blockers.append("dex_mapping_review_queue_schema_plan_not_ready")
    if not dry_run and confirm != "CREATE_DEX_MAPPING_REVIEW_QUEUE":
        blockers.append("confirm_CREATE_DEX_MAPPING_REVIEW_QUEUE_required")

    expected_columns = [
        "id",
        "paircreated_evidence_id",
        "chain",
        "venue_family",
        "venue_key",
        "factory_address",
        "pair_address",
        "token0",
        "token0_symbol",
        "token1",
        "token1_symbol",
        "proof_type",
        "source_type",
        "source_label",
        "source_url",
        "source_tier",
        "tx_hash",
        "log_index",
        "block_number",
        "paircreated_dedupe_key",
        "evidence_payload_digest",
        "mapping_dedupe_key",
        "mapping_contract_json",
        "status",
        "created_at",
        "source_policy",
    ]
    index_sql = [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_mapping_dedupe ON dex_mapping_review_queue(mapping_dedupe_key)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_paircreated_evidence_id ON dex_mapping_review_queue(paircreated_evidence_id)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_chain_venue ON dex_mapping_review_queue(chain, venue_key)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_chain_factory ON dex_mapping_review_queue(chain, factory_address)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_chain_pair ON dex_mapping_review_queue(chain, pair_address)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_token0 ON dex_mapping_review_queue(token0)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_token1 ON dex_mapping_review_queue(token1)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_tx_log ON dex_mapping_review_queue(tx_hash, log_index)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_status ON dex_mapping_review_queue(status)",
        "CREATE INDEX IF NOT EXISTS idx_dex_mapping_review_queue_source_type ON dex_mapping_review_queue(source_type)",
    ]

    conn = get_db()
    try:
        exists = table_exists(conn, target_table)
        row_count = (
            int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
            if exists else 0
        )
        if exists:
            existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({target_table})").fetchall()}
            if any(column not in existing_columns for column in expected_columns):
                blockers.append("schema_drift_detected")
    finally:
        conn.close()

    blockers = list(dict.fromkeys(blockers))
    migration_required = not exists
    if dry_run or blockers:
        return {
            "ok": not blockers,
            "dry_run": bool(dry_run),
            "create_status": "ready_but_disabled" if not blockers else "blocked",
            "paircreated_evidence_id": paircreated_evidence_id,
            "target_table": target_table,
            "table_exists": exists,
            "migration_required": migration_required,
            "confirm_required": "CREATE_DEX_MAPPING_REVIEW_QUEUE",
            "source_status": plan.get("source_status"),
            "mapping_dedupe_key": plan.get("mapping_dedupe_key"),
            "would_create_table": bool(migration_required and not blockers),
            "table_created": False,
            "indexes_created": [],
            "rows_inserted": 0,
            "row_count": row_count,
            "source_backed_scoring": False,
            "mapping_ready_now": 0,
            "known_unmatched_research_only_pools": 3,
            "would_create_mapping_review_row": False,
            "would_persist_paircreated_evidence": False,
            "would_create_mapping": False,
            "would_create_dex_router_evidence": False,
            "would_create_cex_label": False,
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_create_wallet_order": False,
            "would_create_client_opt_in": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": blockers,
            "source_policy": (
                "admin-only dry-run DEX mapping review queue DDL preview; no rows, no mappings, "
                "no router evidence, no labels, no scoring, no client signals, no trades, "
                "no wallet orders and no opt-ins"
            ),
        }

    conn = get_db()
    try:
        before_exists = table_exists(conn, target_table)
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
            CREATE TABLE IF NOT EXISTS dex_mapping_review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paircreated_evidence_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                venue_family TEXT NOT NULL,
                venue_key TEXT NOT NULL,
                factory_address TEXT NOT NULL,
                pair_address TEXT NOT NULL,
                token0 TEXT NOT NULL,
                token0_symbol TEXT,
                token1 TEXT NOT NULL,
                token1_symbol TEXT,
                proof_type TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_label TEXT,
                source_url TEXT NOT NULL,
                source_tier TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                log_index INTEGER NOT NULL,
                block_number INTEGER NOT NULL,
                paircreated_dedupe_key TEXT NOT NULL,
                evidence_payload_digest TEXT NOT NULL,
                mapping_dedupe_key TEXT NOT NULL UNIQUE,
                mapping_contract_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_mapping_review',
                created_at TEXT NOT NULL,
                source_policy TEXT NOT NULL
            )
            """
        )
        for sql in index_sql:
            conn.execute(sql)
        conn.commit()
        after_exists = table_exists(conn, target_table)
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
        "paircreated_evidence_id": paircreated_evidence_id,
        "target_table": target_table,
        "table_exists": after_exists,
        "migration_required": False,
        "confirm_required": "CREATE_DEX_MAPPING_REVIEW_QUEUE",
        "source_status": plan.get("source_status"),
        "mapping_dedupe_key": plan.get("mapping_dedupe_key"),
        "would_create_table": False,
        "table_created": table_created,
        "indexes_created": created_indexes,
        "rows_inserted": 0,
        "row_count": row_count,
        "source_backed_scoring": False,
        "mapping_ready_now": 0,
        "known_unmatched_research_only_pools": 3,
        "would_create_mapping_review_row": False,
        "would_persist_paircreated_evidence": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": (1 if table_created else 0) + len(created_indexes),
        "blockers": [],
        "source_policy": (
            "admin-confirmed DDL-only DEX mapping review queue migration; created table/indexes if absent, "
            f"inserted zero rows and current row_count={row_count}; no DEX mapping, no router evidence, "
            "no labels, no scoring, no client signals, no trades, no wallet orders and no opt-ins"
        ),
    }


def insert_dex_mapping_review_queue_with_deps(
    paircreated_evidence_id: int | None,
    expected_mapping_dedupe_key: str | None,
    dry_run: bool,
    confirm: str | None,
    *,
    get_contract: Callable[[int | None, bool], dict[str, Any]],
    get_db: GetDb,
    table_exists: TableExists,
) -> dict[str, Any]:
    """Insert one mapping-review intent row through the facade-supplied DB hooks."""
    target_table = "dex_mapping_review_queue"
    contract = get_contract(paircreated_evidence_id, True)
    blockers: list[str] = list(contract.get("blockers") or [])
    if paircreated_evidence_id is None:
        blockers.append("paircreated_evidence_id_required")
    if contract.get("contract_status") != "ready_but_disabled":
        blockers.append("dex_mapping_review_contract_not_ready")

    clean_expected_key = str(expected_mapping_dedupe_key or "").strip()
    mapping_dedupe_key = str(contract.get("mapping_dedupe_key") or "").strip()
    if not dry_run and not clean_expected_key:
        blockers.append("expected_mapping_dedupe_key_required")
    if clean_expected_key and mapping_dedupe_key and clean_expected_key != mapping_dedupe_key:
        blockers.append("expected_mapping_dedupe_key_mismatch")

    conn = get_db()
    try:
        table_ready = table_exists(conn, target_table)
        existing_row = None
        row_count = 0
        if table_ready:
            row_count = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
            if mapping_dedupe_key:
                existing_row = conn.execute(
                    "SELECT id FROM dex_mapping_review_queue WHERE mapping_dedupe_key = ? LIMIT 1",
                    (mapping_dedupe_key,),
                ).fetchone()
    finally:
        conn.close()

    if not table_ready:
        blockers.append("dex_mapping_review_queue_table_missing")
    dedupe_status = "duplicate" if existing_row else "new"
    if existing_row:
        blockers.append("duplicate_mapping_dedupe_key")
    if not dry_run and confirm != "INSERT_DEX_MAPPING_REVIEW":
        blockers.append("confirm_INSERT_DEX_MAPPING_REVIEW_required")

    source_evidence = dict(contract.get("source_evidence") or {})
    proposed_mapping = dict(contract.get("proposed_mapping") or {})
    would_insert = bool(table_ready and mapping_dedupe_key and not blockers)
    if dry_run or blockers:
        return {
            "ok": not blockers,
            "dry_run": bool(dry_run),
            "insert_status": "ready_for_insert" if would_insert else "blocked",
            "target_table": target_table,
            "table_exists": table_ready,
            "paircreated_evidence_id": paircreated_evidence_id,
            "dex_mapping_review_id": None,
            "source_status": contract.get("source_status"),
            "mapping_dedupe_key": mapping_dedupe_key or clean_expected_key or None,
            "expected_mapping_dedupe_key": clean_expected_key or None,
            "dedupe_status": dedupe_status,
            "proposed_mapping": proposed_mapping,
            "source_evidence": source_evidence,
            "route_safety": contract.get("route_safety"),
            "would_insert": would_insert,
            "inserted": False,
            "row_count": row_count,
            "rows_inserted": 0,
            "known_unmatched_research_only_pools": 3,
            "source_backed_scoring": False,
            "mapping_ready_now": 0,
            "would_create_mapping_review_row": False,
            "would_persist_paircreated_evidence": False,
            "would_create_mapping": False,
            "would_create_dex_router_evidence": False,
            "would_create_cex_label": False,
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_create_wallet_order": False,
            "would_create_client_opt_in": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": list(dict.fromkeys(blockers)),
            "source_policy": (
                "admin-only dry-run DEX mapping review row insert preview; no row is inserted in dry-run, "
                "no DEX mapping, no router evidence, no labels, no scoring, no client signals, no trades, "
                "no wallet orders and no opt-ins"
            ),
        }

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    mapping_contract_json = json.dumps(contract, sort_keys=True, separators=(",", ":"), default=str)
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO dex_mapping_review_queue (
                paircreated_evidence_id, chain, venue_family, venue_key, factory_address, pair_address,
                token0, token0_symbol, token1, token1_symbol, proof_type, source_type, source_label,
                source_url, source_tier, tx_hash, log_index, block_number, paircreated_dedupe_key,
                evidence_payload_digest, mapping_dedupe_key, mapping_contract_json, status, created_at,
                source_policy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paircreated_evidence_id,
                proposed_mapping.get("chain"),
                proposed_mapping.get("venue_family"),
                proposed_mapping.get("venue_key"),
                proposed_mapping.get("factory_address"),
                proposed_mapping.get("pair_address"),
                proposed_mapping.get("token0"),
                proposed_mapping.get("token0_symbol"),
                proposed_mapping.get("token1"),
                proposed_mapping.get("token1_symbol"),
                proposed_mapping.get("proof_type"),
                proposed_mapping.get("source_type"),
                source_evidence.get("source_label"),
                source_evidence.get("source_url"),
                source_evidence.get("source_tier"),
                contract.get("tx_hash"),
                contract.get("log_index"),
                contract.get("block_number"),
                source_evidence.get("paircreated_dedupe_key"),
                source_evidence.get("evidence_payload_digest"),
                mapping_dedupe_key,
                mapping_contract_json,
                "pending_mapping_review",
                created_at,
                (
                    "admin-confirmed DEX mapping review intent row; not a DEX mapping, not router evidence, "
                    "not source-backed scoring, not a client signal and not a trade trigger"
                ),
            ),
        )
        conn.commit()
        mapping_review_id = int(cursor.lastrowid)
        row_count_after = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
    finally:
        conn.close()

    return {
        "ok": True,
        "dry_run": False,
        "insert_status": "inserted",
        "target_table": target_table,
        "table_exists": True,
        "paircreated_evidence_id": paircreated_evidence_id,
        "dex_mapping_review_id": mapping_review_id,
        "source_status": contract.get("source_status"),
        "mapping_dedupe_key": mapping_dedupe_key,
        "expected_mapping_dedupe_key": clean_expected_key,
        "dedupe_status": "inserted",
        "proposed_mapping": proposed_mapping,
        "source_evidence": source_evidence,
        "route_safety": contract.get("route_safety"),
        "would_insert": False,
        "inserted": True,
        "row_count": row_count_after,
        "rows_inserted": 1,
        "known_unmatched_research_only_pools": 3,
        "source_backed_scoring": False,
        "mapping_ready_now": 0,
        "would_create_mapping_review_row": False,
        "would_persist_paircreated_evidence": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 1,
        "blockers": [],
        "source_policy": (
            "admin-confirmed DEX mapping review intent insert; wrote one review row, no DEX mapping, "
            "no router evidence, no labels, no scoring, no client signals, no trades, no wallet orders and no opt-ins"
        ),
    }
