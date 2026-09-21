from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any

from services.onchain.core.constants import TRANSFER_TOPIC


def _engine():
    from services import onchain_engine

    return onchain_engine


def _normalize_chain(value: str) -> str:
    return _engine()._normalize_chain(value)


def _get_db() -> sqlite3.Connection:
    return _engine()._get_db()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return _engine()._table_exists(conn, table_name)


def _indexed_address_topic(address: str | None) -> str | None:
    clean = str(address or "").strip().lower()
    if not clean.startswith("0x") or len(clean) != 42:
        return None
    return "0x" + clean[2:].rjust(64, "0")


def _chunk_window(first_block: int, last_block: int, *, max_span: int = 5_000) -> list[dict[str, int]]:
    chunks: list[dict[str, int]] = []
    start = int(first_block)
    end = int(last_block)
    while start <= end:
        chunk_end = min(end, start + max_span - 1)
        chunks.append(
            {
                "from_block": start,
                "to_block": chunk_end,
                "block_span": chunk_end - start + 1,
            }
        )
        start = chunk_end + 1
    return chunks


def get_manipulation_detection_transfer_context_collection_plan(
    chain: str | None = "bsc",
    limit: int = 3,
    max_windows: int = 8,
    max_receipt_samples: int = 12,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only plan for the next transfer-context collection around reliable raw Swap leads."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 3), 25))
    clean_max_windows = max(1, min(int(max_windows or 8), 20))
    clean_max_receipt_samples = max(1, min(int(max_receipt_samples or 12), 50))
    transfer_topic = TRANSFER_TOPIC.lower()
    source_policy = (
        "admin-only read-only manipulation transfer-context collection plan. It reads local reliability, "
        "PairCreated evidence, dex_raw_swap_events and transfer tables only. It does not call RPC/SQD/indexers, "
        "does not insert transfers, and does not create mappings, labels, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_call_rpc": False,
        "would_call_sqd": False,
        "would_fetch_receipts": False,
        "would_collect_transfer_logs": False,
        "would_insert_token_transfers": False,
        "would_insert_erc20_transfer_events": False,
        "would_persist_evidence": False,
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
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "plan_status": "blocked",
            "chain": clean_chain,
            "summary": {"target_leads": 0, "planned_transfer_windows": 0, "receipt_replay_samples": 0},
            "target_leads": [],
            "blockers": ["dry_run_required"],
            **disabled,
        }

    reliability = _engine().get_manipulation_detection_reliability_engine(
        chain=clean_chain,
        limit=max(clean_limit, 5),
        dry_run=True,
    )
    reliability_rows = list(reliability.get("candidates") or [])
    target_rows = [
        row
        for row in reliability_rows
        if "too_few_transfer_rows_min_10" in list(row.get("blockers") or [])
        and str(row.get("repeatability_status") or "") == "present_from_raw_events"
    ][:clean_limit]

    target_leads: list[dict[str, Any]] = []
    global_blockers: list[str] = []
    conn = _get_db()
    conn.row_factory = sqlite3.Row
    try:
        raw_table_exists = _table_exists(conn, "dex_raw_swap_events")
        transfer_table_exists = _table_exists(conn, "token_transfers")
        paircreated_table_exists = _table_exists(conn, "dex_paircreated_evidence")

        for row in target_rows:
            pool = str(row.get("pool") or "").strip().lower()
            token = str(row.get("token_address") or "").strip().lower()
            token0 = str(row.get("token0") or "").strip().lower()
            token1 = str(row.get("token1") or "").strip().lower()
            if not pool or not token:
                continue

            current_context = dict(row.get("data_coverage") or {})
            paircreated = None
            if paircreated_table_exists:
                paircreated = conn.execute(
                    """
                    SELECT id, factory_address, pair_address, token0, token1,
                           tx_hash, log_index, block_number, status
                    FROM dex_paircreated_evidence
                    WHERE lower(chain) = ? AND lower(pair_address) = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (clean_chain, pool),
                ).fetchone()

            raw_windows = list(current_context.get("raw_windows") or [])
            planned_windows: list[dict[str, Any]] = []
            if paircreated is not None and paircreated["block_number"] is not None:
                block = int(paircreated["block_number"])
                planned_windows.append(
                    {
                        "window_type": "paircreated_liquidity_transfer_context",
                        "from_block": max(0, block - 500),
                        "to_block": block + 1_500,
                        "block_span": 2_001,
                        "why": "capture initial token0/token1 transfers into the pool after creation",
                    }
                )

            for raw_window in raw_windows:
                first_block = raw_window.get("first_block")
                last_block = raw_window.get("last_block")
                if first_block is None or last_block is None:
                    continue
                for chunk in _chunk_window(int(first_block), int(last_block), max_span=5_000):
                    planned_windows.append(
                        {
                            "window_type": "raw_swap_window_transfer_context",
                            **chunk,
                            "why": "capture target-token Transfer logs around repeated raw Swap activity",
                        }
                    )
                    if len(planned_windows) >= clean_max_windows:
                        break
                if len(planned_windows) >= clean_max_windows:
                    break

            sample_rows = []
            if raw_table_exists:
                sample_rows = [
                    dict(item)
                    for item in conn.execute(
                        """
                        SELECT tx_hash, MIN(block_number) AS block_number, COUNT(*) AS raw_swap_logs
                        FROM dex_raw_swap_events
                        WHERE lower(chain) = ? AND lower(pair_address) = ?
                        GROUP BY tx_hash
                        ORDER BY block_number ASC, tx_hash ASC
                        LIMIT ?
                        """,
                        (clean_chain, pool, clean_max_receipt_samples),
                    )
                ]

            transfer_samples = []
            if transfer_table_exists:
                transfer_samples = [
                    dict(item)
                    for item in conn.execute(
                        """
                        SELECT tx_hash, log_index, block_number, timestamp, token, from_addr, to_addr, value_raw, source
                        FROM token_transfers
                        WHERE lower(chain) = ?
                          AND (
                            lower(COALESCE(token, '')) = ?
                            OR lower(COALESCE(from_addr, '')) = ?
                            OR lower(COALESCE(to_addr, '')) = ?
                          )
                        ORDER BY block_number DESC, log_index DESC
                        LIMIT 10
                        """,
                        (clean_chain, token, pool, pool),
                    )
                ]

            pool_topic = _indexed_address_topic(pool)
            token_filters: list[dict[str, Any]] = []
            seen_filters: set[tuple[str, str]] = set()
            for token_address, role in [(token, "target_token"), (token0, "pair_token0"), (token1, "pair_token1")]:
                if not token_address or not token_address.startswith("0x"):
                    continue
                is_target_token = token_address == token
                if is_target_token:
                    key = (token_address, "all_transfers")
                    if key not in seen_filters:
                        seen_filters.add(key)
                        token_filters.append(
                            {
                                "role": role,
                                "event_name": "ERC20 Transfer",
                                "address": token_address,
                                "topics": [transfer_topic],
                                "purpose": "target-token transfer context around UFLOKI reliability candidate",
                            }
                        )
                if pool_topic:
                    for direction, topics, purpose in [
                        ("inbound_to_pool", [transfer_topic, None, pool_topic], "pool inbound transfer context"),
                        ("outbound_from_pool", [transfer_topic, pool_topic, None], "pool outbound transfer context"),
                    ]:
                        key = (token_address, direction)
                        if key in seen_filters:
                            continue
                        seen_filters.add(key)
                        token_filters.append(
                            {
                                "role": f"{role}_{direction}",
                                "event_name": "ERC20 Transfer",
                                "address": token_address,
                                "topics": topics,
                                "purpose": purpose,
                            }
                        )

            current_best_transfer_rows = max(
                int(current_context.get("token_transfer_rows") or 0),
                int(current_context.get("pool_transfer_rows") or 0),
            )
            row_blockers = []
            if not raw_table_exists:
                row_blockers.append("dex_raw_swap_events_missing")
            if not transfer_topic:
                row_blockers.append("transfer_topic_missing")
            if not planned_windows:
                row_blockers.append("no_transfer_collection_windows")
            if current_best_transfer_rows >= 10:
                row_blockers.append("transfer_context_already_meets_min_10")

            target_leads.append(
                {
                    "chain": clean_chain,
                    "token_symbol": row.get("token_symbol"),
                    "token_address": token,
                    "pool_address": pool,
                    "token0": token0 or None,
                    "token1": token1 or None,
                    "route_proof_status": row.get("route_proof_status"),
                    "repeatability_status": row.get("repeatability_status"),
                    "current_transfer_context": {
                        "token_transfer_rows": current_context.get("token_transfer_rows"),
                        "pool_transfer_rows": current_context.get("pool_transfer_rows"),
                        "raw_pool_transfer_rows": current_context.get("raw_pool_transfer_rows"),
                        "transfer_wallets": current_context.get("transfer_wallets"),
                        "min_required_transfer_rows": 10,
                        "missing_to_min_transfer_rows": max(0, 10 - current_best_transfer_rows),
                    },
                    "planned_transfer_windows": planned_windows[:clean_max_windows],
                    "planned_transfer_filters": token_filters,
                    "receipt_replay_samples": sample_rows,
                    "local_transfer_samples": transfer_samples,
                    "future_collection_methods": [
                        "bounded_eth_getLogs_or_SQD_ERC20_Transfer_lookup",
                        "bounded_eth_getTransactionReceipt_replay_for_sample_raw_swap_txs",
                    ],
                    "future_confirm_required": "COLLECT_MANIPULATION_TRANSFER_CONTEXT",
                    "plan_readiness": "ready_but_disabled" if not row_blockers else "blocked",
                    "blockers": row_blockers,
                    **disabled,
                }
            )
    finally:
        conn.close()

    ready_rows = sum(1 for item in target_leads if item.get("plan_readiness") == "ready_but_disabled")
    if not target_rows:
        global_blockers.append("no_repeatable_reliability_lead_missing_transfer_context")
    if not ready_rows:
        global_blockers.append("no_transfer_context_collection_target_ready")

    planned_window_count = sum(len(item.get("planned_transfer_windows") or []) for item in target_leads)
    receipt_sample_count = sum(len(item.get("receipt_replay_samples") or []) for item in target_leads)
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if ready_rows else "blocked",
        "chain": clean_chain,
        "summary": {
            "target_leads": len(target_leads),
            "ready_transfer_collection_targets": ready_rows,
            "planned_transfer_windows": planned_window_count,
            "receipt_replay_samples": receipt_sample_count,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "reliability_snapshot": {
            "can_detect_reliable_manipulation_now": reliability.get("can_detect_reliable_manipulation_now"),
            "next_safe_step": reliability.get("next_safe_step"),
            "blockers": reliability.get("blockers"),
        },
        "target_leads": target_leads,
        "blockers": list(dict.fromkeys(global_blockers)),
        "next_safe_step": (
            "confirmed_bounded_transfer_context_lookup_dry_run"
            if ready_rows
            else "repair_reliability_leads_before_transfer_context_collection"
        ),
        **disabled,
    }


def run_manipulation_detection_transfer_context_lookup_dry_run(
    chain: str | None = "bsc",
    limit: int = 3,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 10,
    max_logs_total: int = 500,
    timeout: int = 8,
) -> dict[str, Any]:
    """Bounded SQD Transfer lookup from the local plan, with no persistence."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 3), 25))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 10), 50))
    safe_logs_total = max(1, min(int(max_logs_total or 500), 5_000))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    required_confirm = "RUN_MANIPULATION_TRANSFER_CONTEXT_LOOKUP"
    external_confirmed = bool(allow_external and confirm == required_confirm)
    engine = _engine()
    sqd_endpoint = engine.SQD_PORTAL_DATASET_URLS.get(clean_chain)
    sqd_key, sqd_key_source = engine._sqd_portal_api_key()
    source_policy = (
        "admin-only bounded Transfer context lookup dry-run. It may call SQD only when allow_external=true "
        "and confirm matches. It parses Transfer logs in memory only and never persists transfers, evidence, "
        "mappings, labels, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_insert_token_transfers": False,
        "would_insert_erc20_transfer_events": False,
        "would_persist_evidence": False,
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
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "lookup_status": "blocked",
            "chain": clean_chain,
            "summary": {
                "target_leads": 0,
                "sqd_calls_performed": 0,
                "transfer_logs_found": 0,
                "parsed_transfer_logs": 0,
            },
            "target_leads": [],
            "blockers": ["dry_run_required"],
            "would_call_sqd": False,
            **disabled,
        }

    plan = get_manipulation_detection_transfer_context_collection_plan(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
    )
    calls_planned = 0
    calls_performed = 0
    raw_logs_seen_total = 0
    unique_event_keys_total: set[str] = set()
    parsed_logs_total = 0
    errors = 0
    auth_or_key_errors = 0
    rate_or_limit_errors = 0
    target_leads: list[dict[str, Any]] = []

    for lead in plan.get("target_leads") or []:
        if lead.get("plan_readiness") != "ready_but_disabled":
            continue
        filter_results: list[dict[str, Any]] = []
        windows = list(lead.get("planned_transfer_windows") or [])
        filters = list(lead.get("planned_transfer_filters") or [])
        for window in windows:
            for transfer_filter in filters:
                if calls_planned >= safe_sqd_calls:
                    filter_results.append(
                        {
                            "lookup_status": "not_called_sqd_budget_exhausted",
                            "planned_window": window,
                            "planned_filter": transfer_filter,
                            "logs_found": 0,
                            "parsed_logs_preview": [],
                            "blockers": ["sqd_call_budget_exhausted"],
                        }
                    )
                    continue
                calls_planned += 1
                log_filter = {
                    "address": str(transfer_filter.get("address") or "").lower(),
                    "topics": list(transfer_filter.get("topics") or []),
                    "fromBlock": hex(int(window.get("from_block") or 0)),
                    "toBlock": hex(int(window.get("to_block") or 0)),
                }
                raw_logs: list[dict[str, Any]] = []
                warning: str | None = None
                request_endpoint: str | None = sqd_endpoint
                request_preview: dict[str, Any] = {}
                call_performed = False
                lookup_status = "not_called_external_disabled"

                if allow_external and not external_confirmed:
                    lookup_status = "not_called_confirm_required"
                elif external_confirmed and not sqd_endpoint:
                    lookup_status = "blocked_sqd_source_unavailable"
                    warning = "sqd_portal_dataset_not_configured_for_chain"
                elif external_confirmed:
                    remaining_logs = max(0, safe_logs_total - raw_logs_seen_total)
                    if remaining_logs <= 0:
                        lookup_status = "not_called_log_budget_exhausted"
                        warning = "max_logs_total_exhausted_before_call"
                    else:
                        raw_logs, request_endpoint, warning, _, request_preview = engine._sqd_portal_event_logs(
                            clean_chain,
                            log_filter,
                            timeout=safe_timeout,
                        )
                        call_performed = True
                        calls_performed += 1
                        raw_logs = raw_logs[:remaining_logs]
                        if warning:
                            lowered_warning = warning.lower()
                            if any(marker in lowered_warning for marker in ("401", "403", "auth", "key")):
                                auth_or_key_errors += 1
                                lookup_status = "sqd_auth_or_key_required_read_only"
                            elif any(marker in lowered_warning for marker in ("429", "rate", "limit")):
                                rate_or_limit_errors += 1
                                lookup_status = "sqd_rate_limited_or_provider_limited"
                            else:
                                errors += 1
                                lookup_status = "sqd_error_read_only"
                        else:
                            lookup_status = "transfer_logs_found_read_only" if raw_logs else "no_transfer_logs_found_read_only"

                parsed_logs: list[dict[str, Any]] = []
                for log in raw_logs:
                    topics = [str(topic or "").strip().lower() for topic in (log.get("topics") or [])]
                    tx_hash = str(log.get("transactionHash") or log.get("transaction_hash") or "").strip().lower()
                    log_index = engine._hex_to_int_or_none(log.get("logIndex")) or engine._hex_to_int_or_none(log.get("log_index"))
                    raw_json = json.dumps(dict(log), sort_keys=True, separators=(",", ":"), default=str)
                    parsed_logs.append(
                        {
                            "tx_hash": tx_hash or None,
                            "log_index": log_index,
                            "block_number": engine._hex_to_int_or_none(log.get("blockNumber")),
                            "block_hash": str(log.get("blockHash") or "").strip().lower() or None,
                            "timestamp": engine._hex_to_int_or_none(log.get("timestamp")),
                            "token_address": str(log.get("address") or "").strip().lower() or None,
                            "topic0": topics[0] if topics else None,
                            "from_address": engine._dex_event_reader_topic_address(topics[1] if len(topics) > 1 else None),
                            "to_address": engine._dex_event_reader_topic_address(topics[2] if len(topics) > 2 else None),
                            "value_raw": engine._dex_event_reader_uint_word(str(log.get("data") or "0x"), 0),
                            "event_dedupe_key": f"{clean_chain}|Transfer|{str(log.get('address') or '').strip().lower()}|{tx_hash}|{log_index}",
                            "payload_digest": hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
                            "raw_payload_json": raw_json,
                            "raw_log_not_persisted": True,
                        }
                    )
                raw_logs_seen_total += len(raw_logs)
                parsed_logs_total += len(parsed_logs)
                for parsed in parsed_logs:
                    key = str(parsed.get("event_dedupe_key") or "").strip()
                    if key:
                        unique_event_keys_total.add(key)
                filter_results.append(
                    {
                        "lookup_status": lookup_status,
                        "planned_window": window,
                        "planned_filter": transfer_filter,
                        "sqd_filter": log_filter,
                        "sqd_source": {
                            "source_type": "sqd_portal_stream_api",
                            "source_label": "sqd_portal",
                            "endpoint": request_endpoint,
                            "called": call_performed,
                            "warning": warning,
                            "api_key_configured": bool(sqd_key),
                            "api_key_source": sqd_key_source,
                            "request_preview": request_preview,
                            "max_items_parsed": len(raw_logs),
                        },
                        "logs_found": len(raw_logs),
                        "unique_event_dedupe_keys": list(
                            dict.fromkeys(
                                str(parsed.get("event_dedupe_key") or "").strip()
                                for parsed in parsed_logs
                                if str(parsed.get("event_dedupe_key") or "").strip()
                            )
                        ),
                        "parsed_logs": parsed_logs,
                        "parsed_logs_preview": parsed_logs[:25],
                        "would_insert_token_transfers": False,
                        "would_insert_erc20_transfer_events": False,
                        "would_write": False,
                        "blockers": list(
                            dict.fromkeys(
                                [
                                    *("external_indexer_disabled" for _ in [1] if not allow_external),
                                    *("external_confirm_required" for _ in [1] if allow_external and not external_confirmed),
                                    *("sqd_source_unavailable" for _ in [1] if external_confirmed and not sqd_endpoint),
                                    *("sqd_warning_present" for _ in [1] if warning),
                                    *("transfer_logs_missing_in_filter" for _ in [1] if not raw_logs),
                                    "transfer_logs_not_persisted",
                                    "mapping_disabled",
                                    "client_signal_disabled",
                                    "trade_disabled",
                                ]
                            )
                        ),
                    }
                )

        unique_lead_keys: set[str] = set()
        unique_lead_events: dict[str, dict[str, Any]] = {}
        raw_lead_logs = sum(int(item.get("logs_found") or 0) for item in filter_results)
        for item in filter_results:
            for key in item.get("unique_event_dedupe_keys") or []:
                clean_key = str(key or "").strip()
                if clean_key:
                    unique_lead_keys.add(clean_key)
            for parsed in item.get("parsed_logs_preview") or []:
                key = str(parsed.get("event_dedupe_key") or "").strip()
                if key:
                    unique_lead_events.setdefault(key, parsed)
        lead_logs = len(unique_lead_keys)
        current_context = dict(lead.get("current_transfer_context") or {})
        projected_best_transfer_rows = max(
            int(current_context.get("token_transfer_rows") or 0),
            int(current_context.get("pool_transfer_rows") or 0),
        ) + lead_logs
        target_leads.append(
            {
                "chain": clean_chain,
                "token_symbol": lead.get("token_symbol"),
                "token_address": lead.get("token_address"),
                "pool_address": lead.get("pool_address"),
                "repeatability_status": lead.get("repeatability_status"),
                "current_transfer_context": current_context,
                "filter_results": filter_results,
                "raw_transfer_logs_seen": raw_lead_logs,
                "unique_transfer_events_found": lead_logs,
                "duplicate_transfer_observations": max(0, raw_lead_logs - lead_logs),
                "unique_transfer_events_preview": list(unique_lead_events.values())[:25],
                "projected_best_transfer_rows_if_persisted_later": projected_best_transfer_rows,
                "transfer_min_ready_if_persisted_later": projected_best_transfer_rows >= 10,
                "can_detect_reliable_manipulation_now": False,
                "blockers": list(
                    dict.fromkeys(
                        [
                            *("transfer_logs_missing" for _ in [1] if not lead_logs),
                            *("projected_transfer_rows_still_below_min_10" for _ in [1] if projected_best_transfer_rows < 10),
                            "transfer_logs_not_persisted",
                            "needs_review_before_future_persistence",
                            "source_backed_scoring_disabled",
                            "client_signal_disabled",
                            "trade_disabled",
                        ]
                    )
                ),
                "next_safe_step": (
                    "transfer_context_evidence_persistence_schema_plan_read_only"
                    if lead_logs
                    else "expand_or_shift_transfer_context_plan_read_only"
                ),
                **disabled,
            }
        )

    lookup_status = (
        "transfer_logs_found_read_only"
        if unique_event_keys_total
        else "sqd_auth_or_key_required_read_only"
        if auth_or_key_errors
        else "sqd_rate_limited_or_provider_limited"
        if rate_or_limit_errors
        else "sqd_lookup_errors_read_only"
        if errors
        else "sqd_lookup_completed_no_transfer_logs_read_only"
        if external_confirmed and target_leads
        else "blocked_missing_external_confirm"
        if allow_external and not external_confirmed
        else "transfer_lookup_planned_external_disabled"
        if target_leads
        else "blocked_no_transfer_context_plan_ready"
    )
    return {
        "ok": True,
        "dry_run": True,
        "lookup_status": lookup_status,
        "chain": clean_chain,
        "sqd_endpoint": sqd_endpoint,
        "source_type": "sqd_portal_stream_api",
        "external_call_gate": {
            "allow_external": bool(allow_external),
            "required_confirm": required_confirm,
            "confirm_matched": external_confirmed,
            "calls_performed_only_when_confirmed": True,
        },
        "summary": {
            "target_leads": len(target_leads),
            "sqd_calls_planned": calls_planned,
            "sqd_calls_performed": calls_performed,
            "sqd_call_budget": safe_sqd_calls,
            "raw_transfer_logs_seen": raw_logs_seen_total,
            "unique_transfer_events_found": len(unique_event_keys_total),
            "duplicate_transfer_observations": max(0, raw_logs_seen_total - len(unique_event_keys_total)),
            "parsed_transfer_logs": parsed_logs_total,
            "max_logs_total": safe_logs_total,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "target_leads": target_leads,
        "blockers": list(
            dict.fromkeys(
                [
                    *("no_transfer_context_plan_ready" for _ in [1] if not target_leads),
                    *("external_confirm_required" for _ in [1] if allow_external and not external_confirmed),
                    *("external_indexer_disabled" for _ in [1] if target_leads and not allow_external),
                    *("sqd_api_key_or_auth_required" for _ in [1] if auth_or_key_errors),
                    *("sqd_rate_or_limit_errors" for _ in [1] if rate_or_limit_errors),
                    *("sqd_errors" for _ in [1] if errors),
                    *("no_transfer_logs_found" for _ in [1] if external_confirmed and target_leads and not unique_event_keys_total),
                    "transfer_logs_not_persisted",
                    "mapping_disabled",
                    "client_signal_disabled",
                    "trade_disabled",
                ]
            )
        ),
        "next_safe_step": (
            "transfer_context_evidence_persistence_schema_plan_read_only"
            if unique_event_keys_total
            else "try_more_transfer_windows_or_receipt_replay_samples"
            if external_confirmed
            else "rerun_with_allow_external_true_and_confirm_RUN_MANIPULATION_TRANSFER_CONTEXT_LOOKUP"
        ),
        "would_call_sqd": bool(target_leads and allow_external and not external_confirmed),
        **disabled,
    }


def get_manipulation_detection_transfer_context_evidence_schema_plan(
    chain: str | None = "bsc",
    limit: int = 1,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 10,
    max_logs_total: int = 200,
    timeout: int = 8,
) -> dict[str, Any]:
    """Read-only schema plan for future Transfer-context evidence persistence."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 1), 25))
    target_table = "dex_transfer_context_evidence"
    source_policy = (
        "admin-only read-only Transfer context evidence schema-plan. It may rerun the bounded SQD lookup "
        "only when explicitly confirmed, previews future evidence-only storage, and never creates tables, "
        "persists logs, updates token_transfers, creates mappings, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_create_table": False,
        "would_insert_transfer_context_evidence": False,
        "would_insert_token_transfers": False,
        "would_insert_erc20_transfer_events": False,
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
        "source_policy": source_policy,
    }
    schema_preview = [
        {"name": "id", "type": "INTEGER PRIMARY KEY AUTOINCREMENT"},
        {"name": "chain", "type": "TEXT NOT NULL"},
        {"name": "source_type", "type": "TEXT NOT NULL"},
        {"name": "source_label", "type": "TEXT NOT NULL"},
        {"name": "source_url", "type": "TEXT"},
        {"name": "token_symbol", "type": "TEXT"},
        {"name": "token_address", "type": "TEXT NOT NULL"},
        {"name": "pool_address", "type": "TEXT NOT NULL"},
        {"name": "tx_hash", "type": "TEXT NOT NULL"},
        {"name": "log_index", "type": "INTEGER NOT NULL"},
        {"name": "block_number", "type": "INTEGER NOT NULL"},
        {"name": "block_hash", "type": "TEXT"},
        {"name": "event_timestamp", "type": "INTEGER"},
        {"name": "from_address", "type": "TEXT"},
        {"name": "to_address", "type": "TEXT"},
        {"name": "value_raw", "type": "TEXT"},
        {"name": "event_topic", "type": "TEXT NOT NULL"},
        {"name": "event_dedupe_key", "type": "TEXT NOT NULL UNIQUE"},
        {"name": "payload_digest", "type": "TEXT NOT NULL"},
        {"name": "raw_payload_json", "type": "TEXT NOT NULL"},
        {"name": "lookup_context_json", "type": "TEXT NOT NULL"},
        {"name": "status", "type": "TEXT NOT NULL DEFAULT 'pending_admin_review'"},
        {"name": "created_at", "type": "TEXT NOT NULL"},
        {"name": "source_policy", "type": "TEXT NOT NULL"},
    ]
    indexes_preview = [
        "UNIQUE(event_dedupe_key)",
        "INDEX(chain, token_address)",
        "INDEX(chain, pool_address)",
        "INDEX(tx_hash, log_index)",
        "INDEX(block_number)",
        "INDEX(status)",
    ]
    constraints_preview = [
        "event_topic must be ERC20 Transfer",
        "status enum: pending_admin_review, accepted_for_future_transfer_context_scoring, needs_review, rejected",
        "duplicate event_dedupe_key must block",
        "no overwrite, no upsert, no silent success",
        "evidence-only rows must not populate token_transfers or erc20_transfer_events automatically",
        "Transfer context is not a DEX mapping, not a signal, and not a trade input until later policy gates pass",
    ]
    dedupe_constraints = {
        "dedupe_key_format": "chain|Transfer|token_address|tx_hash|log_index",
        "duplicate_policy": "block_duplicate_no_overwrite_no_upsert_no_silent_success",
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "plan_status": "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "table_exists": None,
            "migration_required": None,
            "schema_preview": schema_preview,
            "indexes_preview": indexes_preview,
            "constraints_preview": constraints_preview,
            "dedupe_constraints": dedupe_constraints,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    conn = _get_db()
    try:
        table_exists = _table_exists(conn, target_table)
    finally:
        conn.close()

    lookup = run_manipulation_detection_transfer_context_lookup_dry_run(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        allow_external=allow_external,
        confirm=confirm,
        max_sqd_calls=max_sqd_calls,
        max_logs_total=max_logs_total,
        timeout=timeout,
    )
    unique_event_keys: set[str] = set()
    preview_rows: list[dict[str, Any]] = []
    eligible_targets: list[dict[str, Any]] = []
    for lead in lookup.get("target_leads") or []:
        lead_keys: set[str] = set()
        for item in lead.get("filter_results") or []:
            for key in item.get("unique_event_dedupe_keys") or []:
                clean_key = str(key or "").strip()
                if clean_key:
                    unique_event_keys.add(clean_key)
                    lead_keys.add(clean_key)
        for parsed in lead.get("unique_transfer_events_preview") or []:
            if len(preview_rows) >= 25:
                break
            preview_rows.append(
                {
                    "chain": clean_chain,
                    "token_symbol": lead.get("token_symbol"),
                    "token_address": parsed.get("token_address") or lead.get("token_address"),
                    "pool_address": lead.get("pool_address"),
                    "tx_hash": parsed.get("tx_hash"),
                    "log_index": parsed.get("log_index"),
                    "block_number": parsed.get("block_number"),
                    "block_hash": parsed.get("block_hash"),
                    "event_timestamp": parsed.get("timestamp"),
                    "from_address": parsed.get("from_address"),
                    "to_address": parsed.get("to_address"),
                    "value_raw": parsed.get("value_raw"),
                    "event_topic": parsed.get("topic0"),
                    "event_dedupe_key": parsed.get("event_dedupe_key"),
                    "payload_digest": parsed.get("payload_digest"),
                    "raw_payload_json_required_later": True,
                    "status": "pending_admin_review",
                }
            )
        if lead_keys:
            eligible_targets.append(
                {
                    "chain": clean_chain,
                    "token_symbol": lead.get("token_symbol"),
                    "token_address": lead.get("token_address"),
                    "pool_address": lead.get("pool_address"),
                    "unique_transfer_events_found": len(lead_keys),
                    "raw_transfer_logs_seen": lead.get("raw_transfer_logs_seen"),
                    "duplicate_transfer_observations": lead.get("duplicate_transfer_observations"),
                    "projected_best_transfer_rows_if_persisted_later": lead.get(
                        "projected_best_transfer_rows_if_persisted_later"
                    ),
                    "transfer_min_ready_if_persisted_later": lead.get("transfer_min_ready_if_persisted_later"),
                    "future_insert_status": "pending_admin_review",
                    "blockers": [
                        "evidence_not_persisted",
                        "mapping_disabled",
                        "client_signal_disabled",
                        "trade_disabled",
                    ],
                }
            )

    insert_set_digest = hashlib.sha256(
        json.dumps(
            {
                "chain": clean_chain,
                "target_table": target_table,
                "source_type": lookup.get("source_type"),
                "event_dedupe_keys": sorted(unique_event_keys),
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    blockers = list(
        dict.fromkeys(
            [
                *("external_lookup_disabled_no_transfer_events_loaded" for _ in [1] if not allow_external),
                *(
                    "external_confirm_required_for_bounded_lookup"
                    for _ in [1]
                    if allow_external and confirm != "RUN_MANIPULATION_TRANSFER_CONTEXT_LOOKUP"
                ),
                *("no_unique_transfer_events_found" for _ in [1] if not unique_event_keys),
                "schema_plan_only_no_table_created",
                "evidence_not_persisted",
                "mapping_disabled",
                "client_signal_disabled",
                "trade_disabled",
            ]
        )
    )
    ready = bool(unique_event_keys)
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if ready else "blocked",
        "chain": clean_chain,
        "target_table": target_table,
        "table_exists": table_exists,
        "migration_required": not table_exists,
        "confirm_required": "CREATE_DEX_TRANSFER_CONTEXT_EVIDENCE_TABLE",
        "schema_preview": schema_preview,
        "indexes_preview": indexes_preview,
        "constraints_preview": constraints_preview,
        "dedupe_constraints": dedupe_constraints,
        "lookup_status": lookup.get("lookup_status"),
        "lookup_external_call_gate": lookup.get("external_call_gate"),
        "summary": {
            "eligible_targets": len(eligible_targets),
            "eligible_unique_transfer_events": len(unique_event_keys),
            "raw_transfer_logs_seen": (lookup.get("summary") or {}).get("raw_transfer_logs_seen"),
            "duplicate_transfer_observations": (lookup.get("summary") or {}).get("duplicate_transfer_observations"),
            "table_exists": table_exists,
            "migration_required": not table_exists,
            "source_backed_scoring": False,
            "mapping_ready_now": 0,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "insert_set_digest": insert_set_digest,
        "eligible_targets": eligible_targets,
        "preview_rows": preview_rows,
        "blockers": blockers,
        "next_safe_step": (
            "dex_transfer_context_evidence_confirmed_ddl_migration"
            if ready and not table_exists
            else "dex_transfer_context_evidence_insert_dry_run_first"
            if ready
            else "rerun_bounded_transfer_context_lookup_with_confirm_or_expand_windows"
        ),
        **disabled,
    }


def create_manipulation_detection_transfer_context_evidence_table(
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Confirmed DDL-only creation of the Transfer context evidence table."""
    clean_chain = _normalize_chain(chain or "bsc")
    target_table = "dex_transfer_context_evidence"
    required_confirm = "CREATE_DEX_TRANSFER_CONTEXT_EVIDENCE_TABLE"
    source_policy = (
        "admin-confirmed DDL-only Transfer context evidence table migration. It creates only the empty "
        "dex_transfer_context_evidence table and indexes if absent; it inserts zero rows, does not update "
        "token_transfers or erc20_transfer_events, and creates no DEX mapping, client signal, trade, wallet "
        "order or opt-in."
    )
    disabled = {
        "would_insert_transfer_context_evidence": False,
        "would_insert_token_transfers": False,
        "would_insert_erc20_transfer_events": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "source_policy": source_policy,
    }

    plan = get_manipulation_detection_transfer_context_evidence_schema_plan(
        chain=clean_chain,
        limit=1,
        dry_run=True,
        allow_external=False,
    )
    blockers: list[str] = []
    plan_blockers = set(plan.get("blockers") or [])
    allowed_plan_blockers = {
        "external_lookup_disabled_no_transfer_events_loaded",
        "no_unique_transfer_events_found",
        "schema_plan_only_no_table_created",
        "evidence_not_persisted",
        "mapping_disabled",
        "client_signal_disabled",
        "trade_disabled",
    }
    if plan.get("target_table") != target_table:
        blockers.append("transfer_context_evidence_schema_plan_target_mismatch")
    if plan.get("plan_status") not in {"ready_but_disabled", "blocked"}:
        blockers.append("transfer_context_evidence_schema_plan_not_available")
    if plan_blockers and not plan_blockers.issubset(allowed_plan_blockers):
        blockers.append("transfer_context_evidence_schema_plan_blocked_unexpectedly")
    if not dry_run and confirm != required_confirm:
        blockers.append("confirm_CREATE_DEX_TRANSFER_CONTEXT_EVIDENCE_TABLE_required")

    expected_columns = [
        "id",
        "chain",
        "source_type",
        "source_label",
        "source_url",
        "token_symbol",
        "token_address",
        "pool_address",
        "tx_hash",
        "log_index",
        "block_number",
        "block_hash",
        "event_timestamp",
        "from_address",
        "to_address",
        "value_raw",
        "event_topic",
        "event_dedupe_key",
        "payload_digest",
        "raw_payload_json",
        "lookup_context_json",
        "status",
        "created_at",
        "source_policy",
    ]
    index_sql = [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dex_transfer_context_evidence_event_dedupe ON dex_transfer_context_evidence(event_dedupe_key)",
        "CREATE INDEX IF NOT EXISTS idx_dex_transfer_context_evidence_chain_token ON dex_transfer_context_evidence(chain, token_address)",
        "CREATE INDEX IF NOT EXISTS idx_dex_transfer_context_evidence_chain_pool ON dex_transfer_context_evidence(chain, pool_address)",
        "CREATE INDEX IF NOT EXISTS idx_dex_transfer_context_evidence_tx_log ON dex_transfer_context_evidence(tx_hash, log_index)",
        "CREATE INDEX IF NOT EXISTS idx_dex_transfer_context_evidence_block ON dex_transfer_context_evidence(block_number)",
        "CREATE INDEX IF NOT EXISTS idx_dex_transfer_context_evidence_status ON dex_transfer_context_evidence(status)",
    ]

    conn = _get_db()
    try:
        table_exists = _table_exists(conn, target_table)
        row_count = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0) if table_exists else 0
        if table_exists:
            existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({target_table})").fetchall()}
            if any(column not in existing_columns for column in expected_columns):
                blockers.append("dex_transfer_context_evidence_schema_drift_detected")
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
            "source_backed_scoring": False,
            "mapping_ready_now": 0,
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
            CREATE TABLE IF NOT EXISTS dex_transfer_context_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_label TEXT NOT NULL,
                source_url TEXT,
                token_symbol TEXT,
                token_address TEXT NOT NULL,
                pool_address TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                log_index INTEGER NOT NULL,
                block_number INTEGER NOT NULL,
                block_hash TEXT,
                event_timestamp INTEGER,
                from_address TEXT,
                to_address TEXT,
                value_raw TEXT,
                event_topic TEXT NOT NULL,
                event_dedupe_key TEXT NOT NULL UNIQUE,
                payload_digest TEXT NOT NULL,
                raw_payload_json TEXT NOT NULL,
                lookup_context_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_admin_review',
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
        "source_backed_scoring": False,
        "mapping_ready_now": 0,
        "would_write": False,
        "real_write_enabled": bool(table_created or created_indexes),
        "writes_performed": (1 if table_created else 0) + len(created_indexes),
        "blockers": [],
        **disabled,
    }


def _transfer_context_evidence_rows_from_lookup(
    clean_chain: str,
    target_table: str,
    lookup: dict[str, Any],
) -> list[dict[str, Any]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    for lead in lookup.get("target_leads") or []:
        token_symbol = lead.get("token_symbol")
        pool_address = str(lead.get("pool_address") or "").strip().lower()
        for item in lead.get("filter_results") or []:
            sqd_source = dict(item.get("sqd_source") or {})
            planned_window = dict(item.get("planned_window") or {})
            planned_filter = dict(item.get("planned_filter") or {})
            lookup_context = {
                "lookup_status": item.get("lookup_status"),
                "planned_window": planned_window,
                "planned_filter": planned_filter,
                "sqd_filter": item.get("sqd_filter"),
                "sqd_source": sqd_source,
                "source_lookup_summary": {
                    "logs_found": item.get("logs_found"),
                    "called": sqd_source.get("called"),
                    "warning": sqd_source.get("warning"),
                },
            }
            parsed_items = list(item.get("parsed_logs") or item.get("parsed_logs_preview") or [])
            for parsed in parsed_items:
                dedupe_key = str(parsed.get("event_dedupe_key") or "").strip()
                if not dedupe_key or dedupe_key in rows_by_key:
                    continue
                raw_payload_json = str(parsed.get("raw_payload_json") or "").strip()
                if not raw_payload_json:
                    raw_payload_json = json.dumps(parsed, sort_keys=True, separators=(",", ":"), default=str)
                rows_by_key[dedupe_key] = {
                    "chain": clean_chain,
                    "source_type": "sqd_portal_stream_api",
                    "source_label": "sqd_portal",
                    "source_url": sqd_source.get("endpoint"),
                    "token_symbol": token_symbol,
                    "token_address": str(parsed.get("token_address") or lead.get("token_address") or "").strip().lower(),
                    "pool_address": pool_address,
                    "tx_hash": str(parsed.get("tx_hash") or "").strip().lower(),
                    "log_index": parsed.get("log_index"),
                    "block_number": parsed.get("block_number"),
                    "block_hash": parsed.get("block_hash"),
                    "event_timestamp": parsed.get("timestamp"),
                    "from_address": parsed.get("from_address"),
                    "to_address": parsed.get("to_address"),
                    "value_raw": parsed.get("value_raw"),
                    "event_topic": parsed.get("topic0"),
                    "event_dedupe_key": dedupe_key,
                    "payload_digest": parsed.get("payload_digest"),
                    "raw_payload_json": raw_payload_json,
                    "lookup_context_json": json.dumps(
                        lookup_context,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ),
                    "status": "pending_admin_review",
                    "target_table": target_table,
                }
    return list(rows_by_key.values())


def insert_manipulation_detection_transfer_context_evidence(
    chain: str | None = "bsc",
    limit: int = 1,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_transfer_context_insert_digest: str | None = None,
    max_sqd_calls: int = 10,
    max_logs_total: int = 200,
    timeout: int = 8,
) -> dict[str, Any]:
    """Dry-run-first evidence-only insert for UFLOKI Transfer context rows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 1), 25))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 10), 50))
    safe_logs_total = max(1, min(int(max_logs_total or 200), 5_000))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    target_table = "dex_transfer_context_evidence"
    lookup_confirm = "RUN_MANIPULATION_TRANSFER_CONTEXT_LOOKUP"
    preview_confirm = "PREVIEW_DEX_TRANSFER_CONTEXT_EVIDENCE_INSERT"
    insert_confirm = "INSERT_DEX_TRANSFER_CONTEXT_EVIDENCE"
    source_policy = (
        "admin-only dry-run-first Transfer context evidence insert. It may call SQD only with explicit "
        "preview/insert confirmation. Confirmed writes are limited to dex_transfer_context_evidence evidence-only "
        "rows; it never mutates token_transfers or erc20_transfer_events and creates no mapping, signal, trade, "
        "wallet order or opt-in."
    )
    disabled = {
        "would_insert_token_transfers": False,
        "would_insert_erc20_transfer_events": False,
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
        blockers.append("allow_external_required_for_transfer_context_evidence_insert_preview")
    if dry_run and allow_external and not external_confirmed_for_preview:
        blockers.append("confirm_PREVIEW_DEX_TRANSFER_CONTEXT_EVIDENCE_INSERT_required")
    if not dry_run:
        if confirm != insert_confirm:
            blockers.append("confirm_INSERT_DEX_TRANSFER_CONTEXT_EVIDENCE_required")
        if not str(expected_transfer_context_insert_digest or "").strip():
            blockers.append("expected_transfer_context_insert_digest_required")
        if not allow_external:
            blockers.append("allow_external_required_for_confirmed_transfer_context_evidence_insert")

    if blockers:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "insert_status": "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "expected_transfer_context_insert_digest": expected_transfer_context_insert_digest,
            "would_call_external": False,
            "external_calls_performed": 0,
            "would_insert_transfer_context_evidence": False,
            "would_insert_transfer_context_evidence_count": 0,
            "inserted": False,
            "rows_inserted": 0,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": list(dict.fromkeys(blockers)),
            **disabled,
        }

    lookup = run_manipulation_detection_transfer_context_lookup_dry_run(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        allow_external=allow_external,
        confirm=lookup_confirm,
        max_sqd_calls=safe_sqd_calls,
        max_logs_total=safe_logs_total,
        timeout=safe_timeout,
    )
    future_rows = _transfer_context_evidence_rows_from_lookup(clean_chain, target_table, lookup)
    event_keys = sorted(str(row.get("event_dedupe_key") or "") for row in future_rows if row.get("event_dedupe_key"))
    insert_digest = hashlib.sha256(
        json.dumps(
            {
                "chain": clean_chain,
                "target_table": target_table,
                "source_type": lookup.get("source_type"),
                "event_dedupe_keys": event_keys,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    if not future_rows:
        blockers.append("no_transfer_context_evidence_rows_available")
    if lookup.get("lookup_status") not in {"transfer_logs_found_read_only"}:
        blockers.append("transfer_context_lookup_not_ready")
    if not insert_digest:
        blockers.append("transfer_context_insert_digest_missing")
    if not dry_run and insert_digest != str(expected_transfer_context_insert_digest or "").strip():
        blockers.append("expected_transfer_context_insert_digest_mismatch")

    invalid_rows: list[str] = []
    for row in future_rows:
        missing = [
            field
            for field in (
                "chain",
                "source_type",
                "source_label",
                "token_address",
                "pool_address",
                "tx_hash",
                "log_index",
                "block_number",
                "event_topic",
                "event_dedupe_key",
                "payload_digest",
                "raw_payload_json",
                "lookup_context_json",
            )
            if row.get(field) in (None, "")
        ]
        if missing:
            invalid_rows.append(f"{row.get('event_dedupe_key') or 'missing_key'}:{','.join(missing)}")
    if invalid_rows:
        blockers.append("transfer_context_evidence_row_missing_required_fields")

    conn = _get_db()
    conn.row_factory = sqlite3.Row
    duplicates: list[str] = []
    table_exists = False
    row_count_before = 0
    try:
        table_exists = _table_exists(conn, target_table)
        if not table_exists:
            blockers.append("dex_transfer_context_evidence_table_missing")
        else:
            row_count_before = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
            for row in future_rows:
                dedupe_key = str(row.get("event_dedupe_key") or "")
                if dedupe_key and conn.execute(
                    "SELECT 1 FROM dex_transfer_context_evidence WHERE event_dedupe_key = ? LIMIT 1",
                    (dedupe_key,),
                ).fetchone():
                    duplicates.append(dedupe_key)
    finally:
        conn.close()

    if duplicates:
        blockers.append("duplicate_transfer_context_evidence_exists")
    blockers = list(dict.fromkeys(blockers))
    duplicate_set = set(duplicates)
    clean_rows = [row for row in future_rows if str(row.get("event_dedupe_key") or "") not in duplicate_set]
    would_insert = bool(table_exists and clean_rows and not blockers)
    external_calls_performed = int((lookup.get("summary") or {}).get("sqd_calls_performed") or 0)
    if dry_run or blockers:
        return {
            "ok": bool(not blockers),
            "dry_run": bool(dry_run),
            "insert_status": "ready_for_insert" if would_insert else "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "table_exists": table_exists,
            "row_count_before": row_count_before,
            "transfer_context_insert_digest": insert_digest or None,
            "expected_transfer_context_insert_digest": expected_transfer_context_insert_digest,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "external_calls_performed": external_calls_performed,
            "would_call_external": bool(allow_external),
            "eligible_transfer_context_rows": len(future_rows),
            "duplicate_event_dedupe_keys": duplicates[:25],
            "invalid_rows": invalid_rows[:25],
            "would_insert_transfer_context_evidence": would_insert,
            "would_insert_transfer_context_evidence_count": len(clean_rows) if would_insert else 0,
            "inserted": False,
            "rows_inserted": 0,
            "future_rows_preview": clean_rows[:25],
            "lookup_summary": lookup.get("summary"),
            "source_backed_scoring": False,
            "mapping_ready_now": 0,
            "can_detect_reliable_manipulation_now": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": blockers,
            **disabled,
        }

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _get_db()
    try:
        for row in clean_rows:
            conn.execute(
                """
                INSERT INTO dex_transfer_context_evidence (
                    chain, source_type, source_label, source_url, token_symbol,
                    token_address, pool_address, tx_hash, log_index, block_number,
                    block_hash, event_timestamp, from_address, to_address, value_raw,
                    event_topic, event_dedupe_key, payload_digest, raw_payload_json,
                    lookup_context_json, status, created_at, source_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("chain"),
                    row.get("source_type"),
                    row.get("source_label"),
                    row.get("source_url"),
                    row.get("token_symbol"),
                    row.get("token_address"),
                    row.get("pool_address"),
                    row.get("tx_hash"),
                    int(row.get("log_index")),
                    int(row.get("block_number")),
                    row.get("block_hash"),
                    row.get("event_timestamp"),
                    row.get("from_address"),
                    row.get("to_address"),
                    row.get("value_raw"),
                    row.get("event_topic"),
                    row.get("event_dedupe_key"),
                    row.get("payload_digest"),
                    row.get("raw_payload_json"),
                    row.get("lookup_context_json"),
                    "pending_admin_review",
                    created_at,
                    source_policy,
                ),
            )
        conn.commit()
        row_count_after = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0)
    finally:
        conn.close()

    return {
        "ok": True,
        "dry_run": False,
        "insert_status": "inserted",
        "chain": clean_chain,
        "target_table": target_table,
        "table_exists": True,
        "row_count_before": row_count_before,
        "row_count_after": row_count_after,
        "transfer_context_insert_digest": insert_digest or None,
        "expected_transfer_context_insert_digest": expected_transfer_context_insert_digest,
        "external_calls_performed": external_calls_performed,
        "would_call_external": False,
        "eligible_transfer_context_rows": len(future_rows),
        "would_insert_transfer_context_evidence": False,
        "would_insert_transfer_context_evidence_count": 0,
        "inserted": True,
        "rows_inserted": len(clean_rows),
        "source_backed_scoring": False,
        "mapping_ready_now": 0,
        "can_detect_reliable_manipulation_now": False,
        "would_write": False,
        "real_write_enabled": True,
        "writes_performed": len(clean_rows),
        "blockers": [],
        **disabled,
    }


def get_manipulation_detection_transfer_context_evidence_review_queue(
    chain: str | None = "bsc",
    status: str | None = "pending_admin_review",
    limit: int = 200,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only review queue for persisted UFLOKI Transfer context evidence rows."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_status = str(status or "").strip() or None
    clean_limit = max(1, min(int(limit or 200), 500))
    target_table = "dex_transfer_context_evidence"
    engine = _engine()
    transfer_topic = TRANSFER_TOPIC.lower()
    source_policy = (
        "admin-only read-only Transfer context evidence review queue. It validates persisted evidence-only "
        "rows in dex_transfer_context_evidence and previews a future reliability bridge; it does not update "
        "statuses, token_transfers, erc20_transfer_events, mappings, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_update_status": False,
        "would_insert_transfer_context_evidence": False,
        "would_insert_token_transfers": False,
        "would_insert_erc20_transfer_events": False,
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
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "queue_status": "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "summary": {
                "total_transfer_context_evidence": 0,
                "returned_rows": 0,
                "ready_for_reliability_bridge_preview": 0,
                "blocked": 0,
            },
            "rows": [],
            "reliability_bridge": {
                "bridge_status": "blocked",
                "can_detect_reliable_manipulation_now": False,
            },
            "blockers": ["dry_run_required"],
            **disabled,
        }

    conn = _get_db()
    conn.row_factory = sqlite3.Row
    table_exists = False
    total_rows = 0
    duplicate_count = 0
    status_counts: dict[str, int] = {}
    fetched_rows: list[sqlite3.Row] = []
    try:
        table_exists = _table_exists(conn, target_table)
        if table_exists:
            total_rows = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {target_table} WHERE lower(chain) = ?",
                    (clean_chain,),
                ).fetchone()[0]
                or 0
            )
            duplicate_count = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM (
                        SELECT event_dedupe_key
                        FROM {target_table}
                        WHERE lower(chain) = ?
                        GROUP BY event_dedupe_key
                        HAVING COUNT(*) > 1
                    )
                    """,
                    (clean_chain,),
                ).fetchone()[0]
                or 0
            )
            status_counts = {
                str(row[0]): int(row[1] or 0)
                for row in conn.execute(
                    f"SELECT status, COUNT(*) FROM {target_table} WHERE lower(chain) = ? GROUP BY status",
                    (clean_chain,),
                ).fetchall()
            }
            params: list[Any] = [clean_chain]
            where_status = ""
            if clean_status:
                where_status = "AND status = ?"
                params.append(clean_status)
            params.append(clean_limit)
            fetched_rows = list(
                conn.execute(
                    f"""
                    SELECT *
                    FROM {target_table}
                    WHERE lower(chain) = ?
                    {where_status}
                    ORDER BY block_number ASC, tx_hash ASC, log_index ASC, id ASC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
            )
    finally:
        conn.close()

    if not table_exists:
        return {
            "ok": True,
            "dry_run": True,
            "queue_status": "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "table_exists": False,
            "summary": {
                "total_transfer_context_evidence": 0,
                "returned_rows": 0,
                "ready_for_reliability_bridge_preview": 0,
                "blocked": 0,
            },
            "rows": [],
            "reliability_bridge": {
                "bridge_status": "blocked",
                "can_detect_reliable_manipulation_now": False,
            },
            "blockers": ["dex_transfer_context_evidence_table_missing"],
            **disabled,
        }

    review_rows: list[dict[str, Any]] = []
    ready_count = 0
    payload_bound_count = 0
    dedupe_bound_count = 0
    source_bound_count = 0
    topic_bound_count = 0
    status_ready_count = 0
    pool_addresses: set[str] = set()
    token_addresses: set[str] = set()
    tx_hashes: set[str] = set()
    block_numbers: set[int] = set()
    wallets: set[str] = set()

    for item in fetched_rows:
        row = dict(item)
        row_blockers: list[str] = []
        raw_payload_json = str(row.get("raw_payload_json") or "")
        lookup_context_json = str(row.get("lookup_context_json") or "")
        raw_payload: dict[str, Any] | None = None
        lookup_context: dict[str, Any] | None = None
        raw_payload_json_valid = False
        lookup_context_json_valid = False
        try:
            raw_payload = json.loads(raw_payload_json)
            raw_payload_json_valid = isinstance(raw_payload, dict)
        except Exception:
            row_blockers.append("raw_payload_json_invalid")
        try:
            lookup_context = json.loads(lookup_context_json)
            lookup_context_json_valid = isinstance(lookup_context, dict)
        except Exception:
            row_blockers.append("lookup_context_json_invalid")

        current_payload_digest = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest() if raw_payload_json else None
        payload_digest_bound = bool(row.get("payload_digest") and row.get("payload_digest") == current_payload_digest)
        if not payload_digest_bound:
            row_blockers.append("payload_digest_not_bound")

        row_chain = str(row.get("chain") or "").strip().lower()
        token_address = str(row.get("token_address") or "").strip().lower()
        pool_address = str(row.get("pool_address") or "").strip().lower()
        tx_hash = str(row.get("tx_hash") or "").strip().lower()
        log_index = row.get("log_index")
        expected_dedupe_key = f"{row_chain}|Transfer|{token_address}|{tx_hash}|{log_index}"
        dedupe_bound = bool(row.get("event_dedupe_key") and str(row.get("event_dedupe_key")) == expected_dedupe_key)
        if not dedupe_bound:
            row_blockers.append("event_dedupe_key_not_bound")

        event_topic_bound = bool(str(row.get("event_topic") or "").strip().lower() == transfer_topic)
        raw_topic_bound = False
        if isinstance(raw_payload, dict):
            topics = [str(topic or "").strip().lower() for topic in raw_payload.get("topics") or []]
            raw_topic_bound = bool(topics and topics[0] == transfer_topic)
        if not event_topic_bound or not raw_topic_bound:
            row_blockers.append("transfer_topic_not_bound")

        source_bound = bool(
            str(row.get("source_type") or "") == "sqd_portal_stream_api"
            and str(row.get("source_label") or "") == "sqd_portal"
            and str(row.get("source_url") or "").startswith("https://portal.sqd.dev/")
        )
        lookup_source_bound = False
        if isinstance(lookup_context, dict):
            sqd_source = dict(lookup_context.get("sqd_source") or {})
            lookup_source_bound = bool(
                lookup_context.get("lookup_status") == "transfer_logs_found_read_only"
                and sqd_source.get("called") is True
                and str(sqd_source.get("source_type") or row.get("source_type") or "") in {"", "sqd_portal_stream_api"}
            )
        if not source_bound or not lookup_source_bound:
            row_blockers.append("source_context_not_bound")

        if str(row.get("status") or "") != "pending_admin_review":
            row_blockers.append("status_not_pending_admin_review")
        else:
            status_ready_count += 1

        for field in ("chain", "token_address", "pool_address", "tx_hash", "log_index", "block_number", "event_topic", "event_dedupe_key", "payload_digest"):
            if row.get(field) in (None, ""):
                row_blockers.append(f"{field}_missing")

        review_readiness = (
            "ready_for_transfer_context_reliability_bridge_preview"
            if not row_blockers
            else "blocked"
        )
        if review_readiness != "blocked":
            ready_count += 1
        if payload_digest_bound:
            payload_bound_count += 1
        if dedupe_bound:
            dedupe_bound_count += 1
        if source_bound and lookup_source_bound:
            source_bound_count += 1
        if event_topic_bound and raw_topic_bound:
            topic_bound_count += 1

        if pool_address:
            pool_addresses.add(pool_address)
        if token_address:
            token_addresses.add(token_address)
        if tx_hash:
            tx_hashes.add(tx_hash)
        if row.get("block_number") is not None:
            block_numbers.add(int(row.get("block_number")))
        for address_field in ("from_address", "to_address"):
            address = str(row.get(address_field) or "").strip().lower()
            if address:
                wallets.add(address)

        review_rows.append(
            {
                "transfer_context_evidence_id": row.get("id"),
                "chain": row.get("chain"),
                "source_type": row.get("source_type"),
                "source_label": row.get("source_label"),
                "source_url": row.get("source_url"),
                "token_symbol": row.get("token_symbol"),
                "token_address": row.get("token_address"),
                "pool_address": row.get("pool_address"),
                "tx_hash": row.get("tx_hash"),
                "log_index": row.get("log_index"),
                "block_number": row.get("block_number"),
                "block_hash": row.get("block_hash"),
                "event_timestamp": row.get("event_timestamp"),
                "from_address": row.get("from_address"),
                "to_address": row.get("to_address"),
                "value_raw": row.get("value_raw"),
                "event_topic": row.get("event_topic"),
                "event_dedupe_key": row.get("event_dedupe_key"),
                "expected_event_dedupe_key": expected_dedupe_key,
                "dedupe_bound": dedupe_bound,
                "payload_digest": row.get("payload_digest"),
                "current_payload_digest": current_payload_digest,
                "payload_digest_bound": payload_digest_bound,
                "raw_payload_json_valid": raw_payload_json_valid,
                "lookup_context_json_valid": lookup_context_json_valid,
                "source_bound": source_bound,
                "lookup_source_bound": lookup_source_bound,
                "transfer_topic_bound": bool(event_topic_bound and raw_topic_bound),
                "status": row.get("status"),
                "review_readiness": review_readiness,
                "review_blockers": list(dict.fromkeys(row_blockers)),
                "would_update_status": False,
                "would_insert_token_transfers": False,
                "would_insert_erc20_transfer_events": False,
                "would_create_mapping": False,
                "would_create_client_signal": False,
                "would_execute_trade": False,
                "would_write": False,
            }
        )

    reliability = engine.get_manipulation_detection_reliability_engine(chain=clean_chain, limit=5, dry_run=True)
    reliability_rows = list(reliability.get("candidates") or [])
    matched_reliability = None
    if pool_addresses:
        lower_pools = {value.lower() for value in pool_addresses}
        for candidate in reliability_rows:
            if str(candidate.get("pool") or candidate.get("pool_address") or "").strip().lower() in lower_pools:
                matched_reliability = candidate
                break
    data_coverage = dict((matched_reliability or {}).get("data_coverage") or {})
    current_best_transfer_rows = max(
        int(data_coverage.get("token_transfer_rows") or 0),
        int(data_coverage.get("pool_transfer_rows") or 0),
    )
    projected_best_transfer_rows = current_best_transfer_rows + ready_count
    reliability_blockers = list((matched_reliability or {}).get("blockers") or [])
    reliability_bridge_status = (
        "ready_for_reliability_bridge_preview"
        if ready_count == total_rows and duplicate_count == 0 and ready_count > 0
        else "blocked"
    )
    global_blockers = list(
        dict.fromkeys(
            [
                *("no_transfer_context_evidence_rows" for _ in [1] if not total_rows),
                *("duplicate_event_dedupe_keys_present" for _ in [1] if duplicate_count),
                *("some_transfer_context_evidence_rows_blocked" for _ in [1] if ready_count != total_rows),
                "reliability_engine_does_not_consume_evidence_table_yet",
                "can_detect_reliable_manipulation_now_false",
                "mapping_disabled",
                "client_signal_disabled",
                "trade_disabled",
            ]
        )
    )

    return {
        "ok": True,
        "dry_run": True,
        "queue_status": "ready_but_disabled" if ready_count and ready_count == total_rows and not duplicate_count else "blocked",
        "chain": clean_chain,
        "status_filter": clean_status,
        "target_table": target_table,
        "table_exists": table_exists,
        "summary": {
            "total_transfer_context_evidence": total_rows,
            "returned_rows": len(review_rows),
            "status_counts": status_counts,
            "pending_admin_review": status_counts.get("pending_admin_review", 0),
            "ready_for_reliability_bridge_preview": ready_count,
            "blocked": len(review_rows) - ready_count,
            "duplicate_event_dedupe_keys": duplicate_count,
            "payload_digest_bound": payload_bound_count,
            "dedupe_bound": dedupe_bound_count,
            "source_bound": source_bound_count,
            "transfer_topic_bound": topic_bound_count,
            "status_pending_admin_review": status_ready_count,
            "unique_tx_hashes": len(tx_hashes),
            "unique_blocks": len(block_numbers),
            "unique_wallets": len(wallets),
            "unique_tokens": len(token_addresses),
            "unique_pools": len(pool_addresses),
            "can_detect_reliable_manipulation_now": False,
        },
        "reliability_bridge": {
            "bridge_status": reliability_bridge_status,
            "bridge_target": "manipulation_reliability_transfer_context_evidence_bridge",
            "reliability_engine_status": reliability.get("engine_status"),
            "reliability_engine_current_blockers": reliability_blockers,
            "reliability_engine_consumes_dex_transfer_context_evidence_now": False,
            "current_best_transfer_rows_seen_by_reliability": current_best_transfer_rows,
            "evidence_rows_ready_for_future_bridge": ready_count,
            "projected_best_transfer_rows_if_bridged": projected_best_transfer_rows,
            "target_blocker_to_clear": "too_few_transfer_rows_min_10",
            "can_detect_reliable_manipulation_now": False,
            "next_safe_step": "transfer_context_evidence_reliability_bridge_preview_read_only",
        },
        "rows": review_rows,
        "blockers": global_blockers,
        **disabled,
    }


def get_manipulation_detection_transfer_context_reliability_bridge_preview(
    chain: str | None = "bsc",
    status: str | None = "pending_admin_review",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only preview of how reviewed Transfer evidence would affect reliability gates."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_status = str(status or "").strip() or "pending_admin_review"
    target_table = "dex_transfer_context_evidence"
    source_policy = (
        "admin-only read-only reliability bridge preview. It reads dex_transfer_context_evidence and the "
        "manipulation reliability engine, then projects whether reviewed Transfer context evidence would clear "
        "the current data-volume blocker. It does not update reliability, token_transfers, erc20_transfer_events, "
        "mappings, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_update_reliability_engine": False,
        "would_mutate_token_transfers": False,
        "would_mutate_erc20_transfer_events": False,
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
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "bridge_status": "blocked",
            "preview_status": "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    review = get_manipulation_detection_transfer_context_evidence_review_queue(
        chain=clean_chain,
        status=clean_status,
        limit=500,
        dry_run=True,
    )
    review_summary = dict(review.get("summary") or {})
    review_bridge = dict(review.get("reliability_bridge") or {})
    reliability = _engine().get_manipulation_detection_reliability_engine(
        chain=clean_chain,
        limit=5,
        dry_run=True,
    )
    reliability_rows = list(reliability.get("candidates") or [])
    review_rows = list(review.get("rows") or [])
    review_pools = {
        str(row.get("pool_address") or "").strip().lower()
        for row in review_rows
        if row.get("pool_address")
    }
    matched_candidate: dict[str, Any] | None = None
    if review_pools:
        for candidate in reliability_rows:
            candidate_pool = str(candidate.get("pool") or candidate.get("pool_address") or "").strip().lower()
            if candidate_pool in review_pools:
                matched_candidate = dict(candidate)
                break
    if matched_candidate is None and reliability_rows:
        matched_candidate = dict(reliability_rows[0])

    data_coverage = dict((matched_candidate or {}).get("data_coverage") or {})
    current_best_transfer_rows = max(
        int(data_coverage.get("token_transfer_rows") or 0),
        int(data_coverage.get("pool_transfer_rows") or 0),
    )
    ready_evidence_rows = int(review_summary.get("ready_for_reliability_bridge_preview") or 0)
    total_evidence_rows = int(review_summary.get("total_transfer_context_evidence") or 0)
    blocked_evidence_rows = int(review_summary.get("blocked") or 0)
    duplicate_count = int(review_summary.get("duplicate_event_dedupe_keys") or 0)
    projected_best_transfer_rows = current_best_transfer_rows + ready_evidence_rows
    reliability_blockers = list((matched_candidate or {}).get("blockers") or [])
    would_clear_transfer_volume_blocker = (
        "too_few_transfer_rows_min_10" in reliability_blockers
        and projected_best_transfer_rows >= 10
    )
    evidence_ready = bool(
        review.get("queue_status") == "ready_but_disabled"
        and total_evidence_rows > 0
        and ready_evidence_rows == total_evidence_rows
        and blocked_evidence_rows == 0
        and duplicate_count == 0
    )
    bridge_status = "ready_but_disabled" if evidence_ready else "blocked"

    blockers = list(
        dict.fromkeys(
            [
                *list(review.get("blockers") or []),
                *("no_reviewed_transfer_context_evidence" for _ in [1] if not total_evidence_rows),
                *("transfer_context_evidence_not_fully_ready" for _ in [1] if total_evidence_rows and not evidence_ready),
                "reliability_bridge_not_applied",
                "source_backed_scoring_disabled",
                "backtest_disabled",
                "policy_risk_gate_missing",
                "client_signal_disabled",
                "trade_disabled",
            ]
        )
    )

    return {
        "ok": True,
        "dry_run": True,
        "bridge_status": bridge_status,
        "preview_status": bridge_status,
        "chain": clean_chain,
        "status_filter": clean_status,
        "target_table": target_table,
        "review_queue_status": review.get("queue_status"),
        "current_reliability": {
            "engine_status": reliability.get("engine_status"),
            "candidate": matched_candidate,
            "candidate_pool": (matched_candidate or {}).get("pool")
            or (matched_candidate or {}).get("pool_address"),
            "candidate_token": (matched_candidate or {}).get("token_symbol")
            or (matched_candidate or {}).get("token"),
            "repeatability_status": (matched_candidate or {}).get("repeatability_status"),
            "blockers": reliability_blockers,
            "data_coverage": data_coverage,
            "can_detect_reliable_manipulation_now": False,
        },
        "reviewed_evidence": {
            "total_transfer_context_evidence": total_evidence_rows,
            "ready_for_reliability_bridge_preview": ready_evidence_rows,
            "blocked": blocked_evidence_rows,
            "duplicate_event_dedupe_keys": duplicate_count,
            "payload_digest_bound": review_summary.get("payload_digest_bound", 0),
            "dedupe_bound": review_summary.get("dedupe_bound", 0),
            "source_bound": review_summary.get("source_bound", 0),
            "transfer_topic_bound": review_summary.get("transfer_topic_bound", 0),
            "unique_tx_hashes": review_summary.get("unique_tx_hashes", 0),
            "unique_blocks": review_summary.get("unique_blocks", 0),
            "unique_wallets": review_summary.get("unique_wallets", 0),
            "unique_tokens": review_summary.get("unique_tokens", 0),
            "unique_pools": review_summary.get("unique_pools", 0),
        },
        "projected_reliability_if_bridged": {
            "current_best_transfer_rows": current_best_transfer_rows,
            "reviewed_evidence_rows": ready_evidence_rows,
            "projected_best_transfer_rows": projected_best_transfer_rows,
            "target_blocker_to_clear": "too_few_transfer_rows_min_10",
            "would_clear_too_few_transfer_rows_min_10": would_clear_transfer_volume_blocker,
            "repeatability_status": (matched_candidate or {}).get("repeatability_status"),
            "source_backed_scoring": False,
            "mapping_ready_now": 0,
            "can_detect_reliable_manipulation_now": False,
            "reliability_engine_consumes_dex_transfer_context_evidence_now": False,
            "next_safe_step": "transfer_context_reliability_bridge_apply_contract_schema_read_only",
        },
        "evidence_rows_preview": review_rows[:10],
        "reliability_bridge_from_review": review_bridge,
        "blockers": blockers,
        **disabled,
    }


def get_manipulation_detection_transfer_context_reliability_bridge_apply_contract(
    chain: str | None = "bsc",
    status: str | None = "pending_admin_review",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only contract for a future reliability bridge apply path."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_status = str(status or "").strip() or "pending_admin_review"
    target_table = "dex_transfer_context_evidence"
    source_policy = (
        "admin-only read-only reliability bridge apply contract. It defines how a future reliability-engine "
        "read model could consume reviewed Transfer context evidence. It does not apply the bridge, does not "
        "mutate reliability outputs, and does not write token_transfers, erc20_transfer_events, mappings, "
        "signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_apply_reliability_bridge": False,
        "would_update_reliability_engine": False,
        "would_mutate_token_transfers": False,
        "would_mutate_erc20_transfer_events": False,
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
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "contract_status": "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    preview = get_manipulation_detection_transfer_context_reliability_bridge_preview(
        chain=clean_chain,
        status=clean_status,
        dry_run=True,
    )
    reviewed = dict(preview.get("reviewed_evidence") or {})
    projected = dict(preview.get("projected_reliability_if_bridged") or {})
    current_reliability = dict(preview.get("current_reliability") or {})
    candidate = dict(current_reliability.get("candidate") or {})
    total_rows = int(reviewed.get("total_transfer_context_evidence") or 0)
    ready_rows = int(reviewed.get("ready_for_reliability_bridge_preview") or 0)
    projected_rows = int(projected.get("projected_best_transfer_rows") or 0)
    current_rows = int(projected.get("current_best_transfer_rows") or 0)
    candidate_pool = str(current_reliability.get("candidate_pool") or candidate.get("pool") or "").strip().lower()
    candidate_token = str(
        candidate.get("token_address")
        or candidate.get("token")
        or current_reliability.get("candidate_token")
        or ""
    ).strip().lower()
    bridge_dedupe_key = (
        f"{clean_chain}|transfer_context_reliability_bridge|{candidate_pool}|{candidate_token}|"
        f"rows:{ready_rows}|projected:{projected_rows}"
    )
    required_fields = [
        "chain",
        "source_type",
        "source_label",
        "source_url",
        "token_address",
        "pool_address",
        "tx_hash",
        "log_index",
        "block_number",
        "from_address",
        "to_address",
        "value_raw",
        "event_topic",
        "event_dedupe_key",
        "payload_digest",
        "raw_payload_json",
        "lookup_context_json",
        "status",
    ]
    schema_preview = {
        "consumer": "manipulation_detection_reliability_engine",
        "source_table": target_table,
        "read_model": "group reviewed Transfer evidence by chain, pool_address and token_address",
        "candidate_join_key": ["chain", "pool_address", "token_address"],
        "volume_metric": "best_transfer_rows = max(existing token/pool transfer rows, reviewed evidence rows)",
        "minimum_transfer_rows_gate": 10,
        "does_not_create_table": True,
        "does_not_insert_rows": True,
        "does_not_mutate_business_tables": True,
    }
    contract_ready = bool(
        preview.get("bridge_status") == "ready_but_disabled"
        and total_rows > 0
        and ready_rows == total_rows
        and projected.get("would_clear_too_few_transfer_rows_min_10") is True
    )
    blockers = list(
        dict.fromkeys(
            [
                *list(preview.get("blockers") or []),
                *("bridge_preview_not_ready" for _ in [1] if preview.get("bridge_status") != "ready_but_disabled"),
                *("reviewed_evidence_rows_missing" for _ in [1] if not total_rows),
                *("reviewed_evidence_rows_not_all_ready" for _ in [1] if total_rows and ready_rows != total_rows),
                *(
                    "transfer_count_blocker_would_not_clear"
                    for _ in [1]
                    if projected.get("would_clear_too_few_transfer_rows_min_10") is not True
                ),
                "future_confirm_required_before_any_bridge_apply",
                "source_backed_scoring_disabled",
                "shadow_backtest_disabled",
                "policy_risk_gate_missing",
                "client_signal_disabled",
                "trade_disabled",
            ]
        )
    )
    return {
        "ok": True,
        "dry_run": True,
        "contract_status": "ready_but_disabled" if contract_ready else "blocked",
        "chain": clean_chain,
        "status_filter": clean_status,
        "target_table": target_table,
        "bridge_target": "manipulation_detection_reliability_engine_transfer_context_read_model",
        "required_future_confirm": "APPLY_UFLOKI_TRANSFER_CONTEXT_RELIABILITY_BRIDGE",
        "bridge_dedupe_key": bridge_dedupe_key,
        "current_reliability": current_reliability,
        "reviewed_evidence": reviewed,
        "projected_reliability_if_bridged": projected,
        "apply_contract": {
            "allowed_future_effect": "reliability engine may count reviewed evidence rows for transfer-context coverage",
            "forbidden_future_effects": [
                "no token_transfers insert",
                "no erc20_transfer_events insert",
                "no DEX mapping",
                "no DEX router evidence",
                "no CEX label",
                "no client signal",
                "no trade",
                "no wallet order",
                "no client opt-in",
            ],
            "required_preconditions": [
                "bridge preview ready_but_disabled",
                "all reviewed evidence rows ready",
                "duplicate event_dedupe_key count is zero",
                "payload digest, event dedupe, SQD source and Transfer topic remain bound",
                "candidate pool/token still match the reliability candidate",
                "projected rows clear too_few_transfer_rows_min_10",
                "explicit future confirm before any real bridge apply",
            ],
            "current_rows_seen_by_reliability": current_rows,
            "reviewed_rows_available": ready_rows,
            "projected_rows_after_future_bridge": projected_rows,
            "would_clear_too_few_transfer_rows_min_10": projected.get("would_clear_too_few_transfer_rows_min_10"),
            "can_detect_reliable_manipulation_now": False,
        },
        "schema_preview": schema_preview,
        "required_fields": required_fields,
        "blockers": blockers,
        **disabled,
    }
