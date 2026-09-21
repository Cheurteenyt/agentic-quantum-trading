from __future__ import annotations

import json
import sqlite3
import time
from typing import Any


def _engine():
    from services import onchain_engine

    return onchain_engine


def insert_manipulation_detection_raw_swap_evidence(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_raw_swap_insert_digest: str | None = None,
    max_sqd_calls: int = 2,
    max_logs_total: int = 500,
    timeout: int = 8,
) -> dict[str, Any]:
    """Dry-run-first data-only insert for exact raw Swap logs."""
    engine = _engine()
    requested_chain = engine._normalize_chain(chain or "bsc")
    safe_limit = max(1, min(int(limit or 5), 25))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 2), 10))
    safe_logs_total = max(1, min(int(max_logs_total or 500), 5_000))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    target_table = "dex_raw_swap_events"
    lookup_confirm = "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP"
    preview_confirm = "PREVIEW_MANIPULATION_RAW_SWAP_EVIDENCE_INSERT"
    insert_confirm = "INSERT_MANIPULATION_RAW_SWAP_EVIDENCE"
    source_policy = (
        "admin-only dry-run-first exact raw Swap evidence insert. It may call SQD only when allow_external is "
        "true and confirmation is explicit. Confirmed writes are limited to dex_raw_swap_events raw observations; "
        "it creates no mappings, router evidence, labels, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_persist_paircreated_evidence": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_policy": source_policy,
    }
    external_confirmed_for_preview = bool(
        allow_external and confirm in {lookup_confirm, preview_confirm, insert_confirm}
    )
    blockers: list[str] = []
    if not allow_external:
        blockers.append("allow_external_required_for_sqd_raw_swap_insert_preview")
    if dry_run and allow_external and not external_confirmed_for_preview:
        blockers.append("confirm_PREVIEW_MANIPULATION_RAW_SWAP_EVIDENCE_INSERT_required")
    if not dry_run:
        if confirm != insert_confirm:
            blockers.append("confirm_INSERT_MANIPULATION_RAW_SWAP_EVIDENCE_required")
        if not str(expected_raw_swap_insert_digest or "").strip():
            blockers.append("expected_raw_swap_insert_digest_required")
        if not allow_external:
            blockers.append("allow_external_required_for_confirmed_raw_swap_insert")

    if blockers:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "insert_status": "blocked",
            "chain": requested_chain,
            "target_table": target_table,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "expected_raw_swap_insert_digest": expected_raw_swap_insert_digest,
            "would_call_external": False,
            "external_calls_performed": 0,
            "would_insert_raw_swap": False,
            "inserted": False,
            "rows_inserted": 0,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": list(dict.fromkeys(blockers)),
            **disabled,
        }

    plan = engine.get_manipulation_detection_raw_swap_evidence_persistence_schema_plan(
        chain=requested_chain,
        limit=safe_limit,
        dry_run=True,
        allow_external=allow_external,
        confirm=lookup_confirm,
        max_sqd_calls=safe_sqd_calls,
        max_logs_total=safe_logs_total,
        timeout=safe_timeout,
    )
    plan_digest = str((plan.get("dedupe_constraints") or {}).get("future_insert_dedupe_digest") or "")
    future_rows = list(plan.get("future_rows_preview") or [])
    eligible_rows = [row for row in future_rows if row.get("eligible_for_future_insert")]

    if plan.get("plan_status") != "ready_read_only":
        blockers.append("raw_swap_schema_plan_not_ready")
    if not eligible_rows:
        blockers.append("no_eligible_raw_swap_rows")
    if not plan_digest:
        blockers.append("raw_swap_insert_digest_missing")
    if not dry_run and plan_digest != str(expected_raw_swap_insert_digest or "").strip():
        blockers.append("expected_raw_swap_insert_digest_mismatch")

    conn = engine._get_db()
    conn.row_factory = sqlite3.Row
    duplicates: list[str] = []
    checkpoint_by_key: dict[str, int | None] = {}
    raw_swap_count_before = 0
    table_exists = False
    try:
        table_exists = engine._table_exists(conn, target_table)
        if not table_exists:
            blockers.append("dex_raw_swap_events_table_missing")
        else:
            raw_swap_count_before = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
            for row in eligible_rows:
                dedupe_key = str(row.get("event_dedupe_key") or "")
                if not dedupe_key:
                    blockers.append("event_dedupe_key_missing")
                    continue
                if conn.execute(
                    "SELECT 1 FROM dex_raw_swap_events WHERE event_dedupe_key = ? LIMIT 1",
                    (dedupe_key,),
                ).fetchone():
                    duplicates.append(dedupe_key)
                    continue
                checkpoint_id = None
                if engine._table_exists(conn, "dex_event_reader_checkpoints"):
                    checkpoint_row = conn.execute(
                        """
                        SELECT id
                        FROM dex_event_reader_checkpoints
                        WHERE lower(chain) = ?
                          AND lower(event_name) = 'swap'
                          AND lower(contract_address) = ?
                          AND from_block <= ?
                          AND to_block >= ?
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (
                            requested_chain,
                            str(row.get("pair_address") or "").strip().lower(),
                            int(row.get("block_number") or 0),
                            int(row.get("block_number") or 0),
                        ),
                    ).fetchone()
                    if checkpoint_row:
                        checkpoint_id = int(checkpoint_row["id"])
                checkpoint_by_key[dedupe_key] = checkpoint_id
    finally:
        conn.close()

    if duplicates:
        blockers.append("duplicate_raw_swap_event_exists")
    blockers = list(dict.fromkeys(blockers))
    duplicate_set = set(duplicates)
    clean_rows = [
        row for row in eligible_rows
        if str(row.get("event_dedupe_key") or "") not in duplicate_set
    ]
    would_insert = bool(not blockers and clean_rows)
    external_calls_performed = int(((plan.get("lookup_snapshot") or {}).get("summary") or {}).get("sqd_calls_performed") or 0)
    if dry_run or blockers:
        return {
            "ok": bool(not blockers),
            "dry_run": bool(dry_run),
            "insert_status": "ready_for_insert" if would_insert else "blocked",
            "chain": requested_chain,
            "target_table": target_table,
            "table_exists": table_exists,
            "raw_swap_count_before": raw_swap_count_before,
            "eligible_raw_swap_rows": len(eligible_rows),
            "blocked_raw_swap_rows": int((plan.get("summary") or {}).get("blocked_raw_swap_rows") or 0),
            "raw_swap_insert_digest": plan_digest or None,
            "expected_raw_swap_insert_digest": expected_raw_swap_insert_digest,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "external_calls_performed": external_calls_performed,
            "would_call_external": bool(allow_external),
            "would_insert_raw_swap": would_insert,
            "would_insert_raw_swap_count": len(clean_rows) if would_insert else 0,
            "inserted": False,
            "rows_inserted": 0,
            "duplicate_event_dedupe_keys": duplicates[:25],
            "future_rows_preview": clean_rows[:25],
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": blockers,
            **disabled,
        }

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = engine._get_db()
    try:
        for row in clean_rows:
            dedupe_key = str(row.get("event_dedupe_key") or "")
            raw_log_json = str(row.get("raw_log_json") or "").strip()
            if not raw_log_json:
                raw_log_json = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
            conn.execute(
                """
                INSERT INTO dex_raw_swap_events (
                    checkpoint_id, chain, pair_address, sender, recipient,
                    amount0_in, amount1_in, amount0_out, amount1_out,
                    tx_hash, log_index, block_number, block_hash, block_timestamp,
                    event_topic, raw_log_json, payload_digest, event_dedupe_key,
                    status, created_at, source_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_by_key.get(dedupe_key),
                    row.get("chain"),
                    row.get("pair_address"),
                    row.get("sender"),
                    row.get("recipient"),
                    str(row.get("amount0_in")),
                    str(row.get("amount1_in")),
                    str(row.get("amount0_out")),
                    str(row.get("amount1_out")),
                    row.get("tx_hash"),
                    int(row.get("log_index")),
                    int(row.get("block_number")),
                    row.get("block_hash"),
                    row.get("block_timestamp"),
                    row.get("event_topic"),
                    raw_log_json,
                    row.get("payload_digest"),
                    dedupe_key,
                    "raw_observed",
                    created_at,
                    source_policy,
                ),
            )
        conn.commit()
        raw_swap_count_after = int(conn.execute("SELECT COUNT(*) FROM dex_raw_swap_events").fetchone()[0] or 0)
    finally:
        conn.close()

    return {
        "ok": True,
        "dry_run": False,
        "insert_status": "inserted",
        "chain": requested_chain,
        "target_table": target_table,
        "raw_swap_count_before": raw_swap_count_before,
        "raw_swap_count_after": raw_swap_count_after,
        "eligible_raw_swap_rows": len(eligible_rows),
        "raw_swap_insert_digest": plan_digest or None,
        "expected_raw_swap_insert_digest": expected_raw_swap_insert_digest,
        "external_calls_performed": external_calls_performed,
        "would_call_external": False,
        "would_insert_raw_swap": False,
        "inserted": True,
        "rows_inserted": len(clean_rows),
        "would_write": False,
        "real_write_enabled": True,
        "writes_performed": len(clean_rows),
        "blockers": [],
        **disabled,
    }
