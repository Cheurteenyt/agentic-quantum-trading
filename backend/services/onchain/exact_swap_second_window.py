from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any


def _engine():
    from services import onchain_engine

    return onchain_engine


def _normalize_chain(value: str) -> str:
    return _engine()._normalize_chain(value)


def _get_db() -> sqlite3.Connection:
    return _engine()._get_db()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return _engine()._table_exists(conn, table_name)


def _overlaps(window: dict[str, int], existing: list[dict[str, int]]) -> bool:
    return any(
        int(window["from_block"]) <= int(item["to_block"])
        and int(window["to_block"]) >= int(item["from_block"])
        for item in existing
    )


def _add_window(
    windows: list[dict[str, Any]],
    seen: set[tuple[int, int]],
    existing_ranges: list[dict[str, int]],
    *,
    reason: str,
    from_block: int,
    to_block: int,
    max_span: int,
) -> None:
    clean_from = max(0, int(from_block))
    clean_to = max(clean_from, int(to_block))
    if clean_to - clean_from + 1 > max_span:
        clean_to = clean_from + max_span - 1
    candidate = {"from_block": clean_from, "to_block": clean_to}
    key = (clean_from, clean_to)
    if key in seen or _overlaps(candidate, existing_ranges):
        return
    seen.add(key)
    windows.append(
        {
            "reason": reason,
            "from_block": clean_from,
            "to_block": clean_to,
            "max_block_span": clean_to - clean_from + 1,
            "dry_run_only": True,
        }
    )


def get_manipulation_detection_exact_swap_second_window_plan(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only plan for finding a second exact-Swap activity window."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 5), 25))
    max_window_span = 5_000
    source_policy = (
        "admin-only read-only UFLOKI/top-lead exact Swap second-window plan. It reads local collection plans, "
        "PairCreated evidence, swaps and dex_raw_swap_events only. It does not call RPC/SQD/indexers, scrape, "
        "persist raw events, create mappings, labels, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_call_rpc": False,
        "would_call_sqd": False,
        "would_persist_raw_swap": False,
        "would_insert_raw_swap": False,
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
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "plan_status": "blocked",
            "chain": clean_chain,
            "summary": {
                "target_leads": 0,
                "proposed_windows": 0,
                "repeatability_ready_now": 0,
            },
            "target_leads": [],
            "blockers": ["dry_run_required"],
            **disabled,
        }

    base_plan = _engine().get_manipulation_detection_exact_swap_collection_plan(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
    )
    base_leads = list(base_plan.get("target_leads") or [])
    rows: list[dict[str, Any]] = []
    global_blockers: list[str] = []

    conn = _get_db()
    conn.row_factory = sqlite3.Row
    try:
        raw_table_exists = _table_exists(conn, "dex_raw_swap_events")
        for lead in base_leads:
            pool = str(lead.get("pool") or "").strip().lower()
            if not pool:
                continue

            raw_summary = {
                "raw_swap_rows": 0,
                "distinct_tx_hashes": 0,
                "distinct_blocks": 0,
                "first_raw_swap_block": None,
                "last_raw_swap_block": None,
                "raw_block_span": 0,
            }
            raw_blocks: list[int] = []
            if raw_table_exists:
                summary_row = conn.execute(
                    """
                    SELECT COUNT(*) AS raw_swap_rows,
                           COUNT(DISTINCT tx_hash) AS distinct_tx_hashes,
                           COUNT(DISTINCT block_number) AS distinct_blocks,
                           MIN(block_number) AS first_raw_swap_block,
                           MAX(block_number) AS last_raw_swap_block
                    FROM dex_raw_swap_events
                    WHERE lower(chain) = ? AND lower(pair_address) = ?
                    """,
                    (clean_chain, pool),
                ).fetchone()
                if summary_row:
                    first_block = summary_row["first_raw_swap_block"]
                    last_block = summary_row["last_raw_swap_block"]
                    raw_summary.update(
                        {
                            "raw_swap_rows": int(summary_row["raw_swap_rows"] or 0),
                            "distinct_tx_hashes": int(summary_row["distinct_tx_hashes"] or 0),
                            "distinct_blocks": int(summary_row["distinct_blocks"] or 0),
                            "first_raw_swap_block": first_block,
                            "last_raw_swap_block": last_block,
                            "raw_block_span": (
                                int(last_block) - int(first_block) + 1
                                if first_block is not None and last_block is not None
                                else 0
                            ),
                        }
                    )
                raw_blocks = [
                    int(row["block_number"])
                    for row in conn.execute(
                        """
                        SELECT DISTINCT block_number
                        FROM dex_raw_swap_events
                        WHERE lower(chain) = ? AND lower(pair_address) = ? AND block_number IS NOT NULL
                        ORDER BY block_number ASC
                        """,
                        (clean_chain, pool),
                    ).fetchall()
                ]

            existing_ranges = [
                {
                    "from_block": int(window.get("from_block") or 0),
                    "to_block": int(window.get("to_block") or 0),
                }
                for window in (lead.get("planned_windows") or [])
                if window.get("from_block") is not None and window.get("to_block") is not None
            ]
            proposed_windows: list[dict[str, Any]] = []
            seen: set[tuple[int, int]] = set()

            first_raw = raw_summary["first_raw_swap_block"]
            last_raw = raw_summary["last_raw_swap_block"]
            containing_range = None
            if first_raw is not None and last_raw is not None:
                for item in existing_ranges:
                    if int(item["from_block"]) <= int(first_raw) <= int(item["to_block"]):
                        containing_range = item
                        break
                cluster_from = int(containing_range["from_block"]) if containing_range else int(first_raw)
                cluster_to = int(containing_range["to_block"]) if containing_range else int(last_raw)
                _add_window(
                    proposed_windows,
                    seen,
                    existing_ranges,
                    reason="pre_raw_cluster_adjacent_second_window",
                    from_block=max(0, cluster_from - max_window_span),
                    to_block=max(0, cluster_from - 1),
                    max_span=max_window_span,
                )
                _add_window(
                    proposed_windows,
                    seen,
                    existing_ranges,
                    reason="post_raw_cluster_adjacent_second_window",
                    from_block=cluster_to + 1,
                    to_block=cluster_to + max_window_span,
                    max_span=max_window_span,
                )
                _add_window(
                    proposed_windows,
                    seen,
                    existing_ranges,
                    reason="post_raw_cluster_followthrough_second_window",
                    from_block=cluster_to + max_window_span + 1,
                    to_block=cluster_to + (max_window_span * 2),
                    max_span=max_window_span,
                )

            paircreated_block = lead.get("paircreated_block_number")
            if paircreated_block is not None and first_raw is not None:
                try:
                    pair_block = int(paircreated_block)
                    first_raw_block = int(first_raw)
                    if first_raw_block - pair_block > max_window_span * 2:
                        midpoint = pair_block + ((first_raw_block - pair_block) // 2)
                        half_span = max_window_span // 2
                        _add_window(
                            proposed_windows,
                            seen,
                            existing_ranges,
                            reason="paircreated_to_first_raw_gap_midpoint_second_window",
                            from_block=midpoint - half_span,
                            to_block=midpoint + half_span - 1,
                            max_span=max_window_span,
                        )
                except (TypeError, ValueError):
                    pass

            independent_windows = 0
            previous_block: int | None = None
            for block in raw_blocks:
                if previous_block is None or block - previous_block > max_window_span:
                    independent_windows += 1
                previous_block = block
            minimum_exact_swaps_remaining = max(0, 10 - int(raw_summary["raw_swap_rows"] or 0))
            repeatability_ready = int(raw_summary["raw_swap_rows"] or 0) >= 10 and independent_windows >= 2
            blockers = list(
                dict.fromkeys(
                    [
                        *("no_raw_swap_rows_for_second_window_planning" for _ in [1] if int(raw_summary["raw_swap_rows"] or 0) <= 0),
                        *("minimum_exact_swaps_not_met" for _ in [1] if minimum_exact_swaps_remaining > 0),
                        *("second_independent_window_missing" for _ in [1] if independent_windows < 2),
                        *("no_additional_windows_proposed" for _ in [1] if not proposed_windows),
                        "lookup_not_executed",
                        "raw_swap_not_persisted",
                        "mapping_disabled",
                        "client_signal_disabled",
                        "trade_disabled",
                    ]
                )
            )
            planned_filters = [
                {
                    "chain": clean_chain,
                    "event_name": "Swap",
                    "event_topic": _engine().SWAP_TOPIC,
                    "address": pool,
                    "from_block": window["from_block"],
                    "to_block": window["to_block"],
                    "max_block_span": window["max_block_span"],
                    "reason": window["reason"],
                    "dry_run_only": True,
                }
                for window in proposed_windows
            ]
            rows.append(
                {
                    "chain": clean_chain,
                    "pool": pool,
                    "token_symbol": lead.get("token_symbol"),
                    "token_address": lead.get("token_address"),
                    "paircreated_evidence_id": lead.get("paircreated_evidence_id"),
                    "factory_address": lead.get("factory_address"),
                    "paircreated_block_number": lead.get("paircreated_block_number"),
                    "existing_plan_windows": existing_ranges,
                    "raw_swap_summary": raw_summary,
                    "raw_independent_windows_observed": independent_windows,
                    "repeatability_ready_now": bool(repeatability_ready),
                    "minimum_exact_swaps_required": 10,
                    "minimum_exact_swaps_remaining": minimum_exact_swaps_remaining,
                    "minimum_independent_windows_required": 2,
                    "minimum_independent_windows_remaining": max(0, 2 - independent_windows),
                    "proposed_windows": proposed_windows,
                    "planned_filters": planned_filters,
                    "plan_readiness": "ready_for_second_window_lookup_dry_run" if proposed_windows else "blocked",
                    "blockers": blockers,
                    "next_safe_step": (
                        "run_bounded_exact_swap_second_window_lookup_dry_run"
                        if proposed_windows
                        else "collect_more_local_anchors_before_second_window_lookup"
                    ),
                    **disabled,
                }
            )
    finally:
        conn.close()

    ready_rows = sum(1 for row in rows if row.get("plan_readiness") == "ready_for_second_window_lookup_dry_run")
    proposed_window_count = sum(len(row.get("proposed_windows") or []) for row in rows)
    if not rows:
        global_blockers.append("no_exact_swap_research_leads_found")
    if rows and ready_rows == 0:
        global_blockers.append("no_second_window_lookup_plan_ready")

    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_read_only" if ready_rows else "blocked",
        "chain": clean_chain,
        "summary": {
            "target_leads": len(rows),
            "ready_for_second_window_lookup_dry_run": ready_rows,
            "proposed_windows": proposed_window_count,
            "repeatability_ready_now": sum(1 for row in rows if row.get("repeatability_ready_now")),
            "client_signal_ready": False,
            "trade_ready": False,
            "real_write_enabled": False,
        },
        "source_collection_plan_snapshot": {
            "plan_status": base_plan.get("plan_status"),
            "summary": base_plan.get("summary") or {},
            "blockers": base_plan.get("blockers") or [],
        },
        "target_leads": rows,
        "blockers": list(dict.fromkeys(global_blockers)),
        "plain_summary_fr": (
            "UFLOKI a maintenant des raw swaps, mais ils viennent d'une seule fenetre. Ce plan propose des "
            "fenetres bornées autour du cluster pour chercher une deuxieme periode d'activite sans rien executer."
        ),
        "next_safe_step": (
            "bounded_exact_swap_second_window_lookup_dry_run"
            if ready_rows
            else "repair_second_window_anchors_read_only"
        ),
        **disabled,
    }


def run_manipulation_detection_exact_swap_second_window_sqd_lookup_dry_run(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 4,
    max_logs_total: int = 500,
    timeout: int = 8,
) -> dict[str, Any]:
    """Bounded SQD lookup for second-window exact Swap candidates, with no persistence."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 5), 25))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 4), 10))
    safe_logs_total = max(1, min(int(max_logs_total or 500), 5_000))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    required_confirm = "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP"
    external_confirmed = bool(allow_external and confirm == required_confirm)
    engine = _engine()
    sqd_endpoint = engine.SQD_PORTAL_DATASET_URLS.get(clean_chain)
    sqd_key, sqd_key_source = engine._sqd_portal_api_key()
    source_policy = (
        "admin-only bounded SQD dry-run for UFLOKI/top-lead second-window exact Swap candidates. It may call "
        "SQD only when allow_external=true and confirm matches. It parses logs in memory only and never "
        "persists raw swaps, evidence, mappings, labels, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_persist_raw_swap": False,
        "would_insert_raw_swap": False,
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
                "swap_logs_found": 0,
                "repeatability_ready_now": 0,
            },
            "rows": [],
            "blockers": ["dry_run_required"],
            "would_call_sqd": False,
            **disabled,
        }

    plan = get_manipulation_detection_exact_swap_second_window_plan(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
    )
    rows: list[dict[str, Any]] = []
    calls_planned = 0
    calls_performed = 0
    logs_found_total = 0
    parsed_logs_total = 0
    errors = 0
    rate_or_limit_errors = 0
    auth_or_key_errors = 0

    for lead in plan.get("target_leads") or []:
        if lead.get("plan_readiness") != "ready_for_second_window_lookup_dry_run":
            continue
        pool = str(lead.get("pool") or "").strip().lower()
        filter_results: list[dict[str, Any]] = []
        for planned_filter in lead.get("planned_filters") or []:
            if calls_planned >= safe_sqd_calls:
                filter_results.append(
                    {
                        "lookup_status": "not_called_sqd_budget_exhausted",
                        "planned_filter": planned_filter,
                        "logs_found": 0,
                        "parsed_logs_preview": [],
                        "blockers": ["sqd_call_budget_exhausted"],
                    }
                )
                continue
            calls_planned += 1
            log_filter = {
                "address": pool,
                "topics": [engine.SWAP_TOPIC],
                "fromBlock": hex(int(planned_filter.get("from_block") or 0)),
                "toBlock": hex(int(planned_filter.get("to_block") or 0)),
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
                remaining_logs = max(0, safe_logs_total - logs_found_total)
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
                        lookup_status = "swap_logs_found_read_only" if raw_logs else "no_swap_logs_found_read_only"

            parsed_logs: list[dict[str, Any]] = []
            for log in raw_logs:
                topics = [str(topic or "").strip().lower() for topic in (log.get("topics") or [])]
                data = str(log.get("data") or "0x")
                tx_hash = str(log.get("transactionHash") or log.get("transaction_hash") or "").strip().lower()
                log_index = engine._hex_to_int_or_none(log.get("logIndex")) or engine._hex_to_int_or_none(log.get("log_index"))
                parsed_logs.append(
                    {
                        "tx_hash": tx_hash or None,
                        "block_number": engine._hex_to_int_or_none(log.get("blockNumber")),
                        "block_hash": str(log.get("blockHash") or "").strip().lower() or None,
                        "timestamp": engine._hex_to_int_or_none(log.get("timestamp")),
                        "log_index": log_index,
                        "pair_address": str(log.get("address") or "").strip().lower() or None,
                        "topic0": topics[0] if topics else None,
                        "sender": engine._dex_event_reader_topic_address(topics[1] if len(topics) > 1 else None),
                        "recipient": engine._dex_event_reader_topic_address(topics[2] if len(topics) > 2 else None),
                        "amount0_in": engine._dex_event_reader_uint_word(data, 0),
                        "amount1_in": engine._dex_event_reader_uint_word(data, 1),
                        "amount0_out": engine._dex_event_reader_uint_word(data, 2),
                        "amount1_out": engine._dex_event_reader_uint_word(data, 3),
                        "event_dedupe_key": f"{clean_chain}|Swap|{pool}|{tx_hash}|{log_index}",
                        "payload_digest": hashlib.sha256(
                            json.dumps(dict(log), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
                        ).hexdigest(),
                        "raw_log_json": json.dumps(dict(log), sort_keys=True, separators=(",", ":"), default=str),
                        "raw_log_not_persisted": True,
                    }
                )
            logs_found_total += len(raw_logs)
            parsed_logs_total += len(parsed_logs)
            filter_results.append(
                {
                    "lookup_status": lookup_status,
                    "planned_filter": planned_filter,
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
                    "parsed_logs_preview": parsed_logs,
                    "would_persist_raw_swap": False,
                    "would_write": False,
                    "blockers": list(
                        dict.fromkeys(
                            [
                                *("external_indexer_disabled" for _ in [1] if not allow_external),
                                *("external_confirm_required" for _ in [1] if allow_external and not external_confirmed),
                                *("sqd_source_unavailable" for _ in [1] if external_confirmed and not sqd_endpoint),
                                *("sqd_warning_present" for _ in [1] if warning),
                                *("swap_logs_missing_in_window" for _ in [1] if not raw_logs),
                                "raw_swap_not_persisted",
                                "mapping_disabled",
                                "client_signal_disabled",
                                "trade_disabled",
                            ]
                        )
                    ),
                }
            )

        lead_logs = sum(int(item.get("logs_found") or 0) for item in filter_results)
        existing_raw_rows = int((lead.get("raw_swap_summary") or {}).get("raw_swap_rows") or 0)
        independent_window_found = any(int(item.get("logs_found") or 0) > 0 for item in filter_results)
        projected_exact_swaps = existing_raw_rows + lead_logs
        repeatability_ready = bool(projected_exact_swaps >= 10 and independent_window_found)
        rows.append(
            {
                "chain": clean_chain,
                "pool": pool,
                "token_symbol": lead.get("token_symbol"),
                "token_address": lead.get("token_address"),
                "paircreated_evidence_id": lead.get("paircreated_evidence_id"),
                "raw_swap_summary_before_lookup": lead.get("raw_swap_summary"),
                "filter_results": filter_results,
                "second_window_swap_logs_found": lead_logs,
                "projected_exact_swaps_if_persisted_later": projected_exact_swaps,
                "repeatability_ready_if_persisted_later": repeatability_ready,
                "usable_for_manipulation_now": False,
                "blockers": list(
                    dict.fromkeys(
                        [
                            *("second_window_logs_missing" for _ in [1] if not lead_logs),
                            *("projected_exact_swaps_still_below_min_10" for _ in [1] if projected_exact_swaps < 10),
                            "raw_swap_not_persisted",
                            "needs_review_before_future_persistence",
                            "client_signal_disabled",
                            "trade_disabled",
                        ]
                    )
                ),
                "next_safe_step": (
                    "second_window_raw_swap_persistence_schema_plan_read_only"
                    if lead_logs
                    else "expand_or_shift_second_window_plan_read_only"
                ),
                **disabled,
            }
        )

    lookup_status = (
        "second_window_swap_logs_found_read_only"
        if logs_found_total
        else "sqd_auth_or_key_required_read_only"
        if auth_or_key_errors
        else "sqd_rate_limited_or_provider_limited"
        if rate_or_limit_errors
        else "sqd_lookup_errors_read_only"
        if errors
        else "sqd_lookup_completed_no_second_window_swap_logs_read_only"
        if external_confirmed and rows
        else "blocked_missing_external_confirm"
        if allow_external and not external_confirmed
        else "sqd_lookup_planned_external_disabled"
        if rows
        else "blocked_no_second_window_plan_ready"
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
            "target_leads": len(rows),
            "sqd_calls_planned": calls_planned,
            "sqd_calls_performed": calls_performed,
            "sqd_call_budget": safe_sqd_calls,
            "second_window_swap_logs_found": logs_found_total,
            "parsed_logs_previewed": parsed_logs_total,
            "repeatability_ready_if_persisted_later": sum(1 for row in rows if row.get("repeatability_ready_if_persisted_later")),
            "usable_for_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
            "real_write_enabled": False,
        },
        "source_plan_snapshot": {
            "plan_status": plan.get("plan_status"),
            "summary": plan.get("summary") or {},
            "blockers": plan.get("blockers") or [],
        },
        "rows": rows,
        "blockers": list(
            dict.fromkeys(
                [
                    *("no_second_window_plan_ready" for _ in [1] if not rows),
                    *("external_indexer_disabled" for _ in [1] if rows and not allow_external),
                    *("external_confirm_required" for _ in [1] if rows and allow_external and not external_confirmed),
                    *("sqd_source_unavailable" for _ in [1] if rows and external_confirmed and not sqd_endpoint),
                    *("sqd_api_key_or_auth_required" for _ in [1] if auth_or_key_errors),
                    *("sqd_rate_or_limit_errors" for _ in [1] if rate_or_limit_errors),
                    *("sqd_errors" for _ in [1] if errors),
                    *("second_window_swap_logs_missing" for _ in [1] if rows and not logs_found_total),
                    "raw_swap_not_persisted",
                    "manipulation_detection_remains_unreliable",
                    "mapping_disabled",
                    "client_signal_disabled",
                    "trade_disabled",
                ]
            )
        ),
        "next_safe_step": (
            "second_window_raw_swap_persistence_schema_plan_read_only"
            if logs_found_total
            else "expand_or_shift_second_window_plan_read_only"
            if rows
            else "repair_second_window_plan_inputs"
        ),
        "would_call_sqd": bool(rows and not allow_external),
        **disabled,
    }


def get_manipulation_detection_second_window_raw_swap_evidence_schema_plan(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 4,
    max_logs_total: int = 500,
    timeout: int = 8,
) -> dict[str, Any]:
    """Read-only schema/persistence plan for second-window raw Swap evidence."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 5), 25))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 4), 10))
    safe_logs_total = max(1, min(int(max_logs_total or 500), 5_000))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    target_table = "dex_raw_swap_events"
    source_policy = (
        "admin-only read-only second-window raw Swap evidence schema-plan. It consumes the bounded second-window "
        "SQD dry-run preview, validates future rows and dedupe, but creates no table, persists no raw swaps, "
        "creates no mappings, labels, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_create_table": False,
        "would_insert_raw_swap": False,
        "would_persist_raw_swap": False,
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
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "plan_status": "blocked",
            "target_table": target_table,
            "summary": {
                "eligible_second_window_raw_swap_rows": 0,
                "blocked_second_window_raw_swap_rows": 0,
            },
            "future_rows_preview": [],
            "blockers": ["dry_run_required"],
            **disabled,
        }

    engine = _engine()
    lookup = run_manipulation_detection_exact_swap_second_window_sqd_lookup_dry_run(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        allow_external=allow_external,
        confirm=confirm,
        max_sqd_calls=safe_sqd_calls,
        max_logs_total=safe_logs_total,
        timeout=safe_timeout,
    )
    conn = _get_db()
    conn.row_factory = sqlite3.Row
    future_rows: list[dict[str, Any]] = []
    duplicate_count = 0
    table_exists = False
    raw_swap_count_before = 0
    try:
        table_exists = _table_exists(conn, target_table)
        raw_swap_count_before = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0] or 0) if table_exists else 0
        for lead in lookup.get("rows") or []:
            pool = str(lead.get("pool") or "").strip().lower()
            for filter_result in lead.get("filter_results") or []:
                window_reason = (filter_result.get("planned_filter") or {}).get("reason")
                for parsed in filter_result.get("parsed_logs_preview") or []:
                    tx_hash = str(parsed.get("tx_hash") or "").strip().lower()
                    log_index = parsed.get("log_index")
                    event_dedupe_key = str(parsed.get("event_dedupe_key") or "").strip()
                    row_blockers: list[str] = []
                    if not table_exists:
                        row_blockers.append("dex_raw_swap_events_table_missing")
                    if not engine._valid_evm_address(pool):
                        row_blockers.append("pair_address_invalid")
                    if parsed.get("topic0") != engine.SWAP_TOPIC:
                        row_blockers.append("swap_topic_mismatch")
                    if not tx_hash.startswith("0x"):
                        row_blockers.append("tx_hash_missing")
                    if log_index is None:
                        row_blockers.append("log_index_missing")
                    if parsed.get("block_number") is None:
                        row_blockers.append("block_number_missing")
                    if not parsed.get("raw_log_json"):
                        row_blockers.append("raw_log_json_missing")
                    if not event_dedupe_key:
                        row_blockers.append("event_dedupe_key_missing")
                    duplicate_exists = False
                    if table_exists and event_dedupe_key:
                        duplicate_exists = bool(
                            conn.execute(
                                "SELECT 1 FROM dex_raw_swap_events WHERE event_dedupe_key = ? LIMIT 1",
                                (event_dedupe_key,),
                            ).fetchone()
                        )
                    if duplicate_exists:
                        duplicate_count += 1
                        row_blockers.append("duplicate_raw_swap_event_exists")
                    future_rows.append(
                        {
                            "target_table": target_table,
                            "chain": clean_chain,
                            "pair_address": pool,
                            "window_reason": window_reason,
                            "sender": parsed.get("sender"),
                            "recipient": parsed.get("recipient"),
                            "amount0_in": parsed.get("amount0_in"),
                            "amount1_in": parsed.get("amount1_in"),
                            "amount0_out": parsed.get("amount0_out"),
                            "amount1_out": parsed.get("amount1_out"),
                            "tx_hash": tx_hash,
                            "log_index": log_index,
                            "block_number": parsed.get("block_number"),
                            "block_hash": parsed.get("block_hash"),
                            "block_timestamp": parsed.get("timestamp"),
                            "event_topic": parsed.get("topic0"),
                            "payload_digest": parsed.get("payload_digest"),
                            "raw_log_json": parsed.get("raw_log_json"),
                            "event_dedupe_key": event_dedupe_key,
                            "status": "raw_observed",
                            "source": "sqd_portal_stream_api",
                            "eligible_for_future_insert": not row_blockers,
                            "blockers": row_blockers,
                            "raw_log_not_persisted": True,
                        }
                    )
    finally:
        conn.close()

    eligible_rows = [row for row in future_rows if row.get("eligible_for_future_insert")]
    blocked_rows = [row for row in future_rows if not row.get("eligible_for_future_insert")]
    digest = (
        hashlib.sha256(
            json.dumps(
                [
                    {
                        "chain": row.get("chain"),
                        "event_dedupe_key": row.get("event_dedupe_key"),
                        "payload_digest": row.get("payload_digest"),
                        "target_table": row.get("target_table"),
                        "window_reason": row.get("window_reason"),
                    }
                    for row in eligible_rows
                ],
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        if eligible_rows
        else None
    )
    eligible_by_window: dict[str, int] = {}
    for row in eligible_rows:
        reason = str(row.get("window_reason") or "unknown_window")
        eligible_by_window[reason] = eligible_by_window.get(reason, 0) + 1

    schema_preview = {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "checkpoint_id": "INTEGER",
        "chain": "TEXT NOT NULL",
        "pair_address": "TEXT NOT NULL",
        "sender": "TEXT",
        "recipient": "TEXT",
        "amount0_in": "TEXT NOT NULL",
        "amount1_in": "TEXT NOT NULL",
        "amount0_out": "TEXT NOT NULL",
        "amount1_out": "TEXT NOT NULL",
        "tx_hash": "TEXT NOT NULL",
        "log_index": "INTEGER NOT NULL",
        "block_number": "INTEGER NOT NULL",
        "block_hash": "TEXT",
        "block_timestamp": "INTEGER",
        "event_topic": "TEXT NOT NULL",
        "raw_log_json": "TEXT NOT NULL",
        "payload_digest": "TEXT NOT NULL",
        "event_dedupe_key": "TEXT NOT NULL UNIQUE",
        "status": "TEXT NOT NULL",
        "created_at": "TEXT NOT NULL",
        "source_policy": "TEXT NOT NULL",
    }
    indexes_preview = [
        "UNIQUE INDEX dex_raw_swap_events_dedupe_uq ON event_dedupe_key",
        "INDEX dex_raw_swap_events_chain_pair_idx ON chain, pair_address",
        "INDEX dex_raw_swap_events_tx_log_idx ON tx_hash, log_index",
        "INDEX dex_raw_swap_events_block_idx ON block_number",
        "INDEX dex_raw_swap_events_status_idx ON status",
    ]
    constraints_preview = {
        "event_topic_must_equal": engine.SWAP_TOPIC,
        "dedupe_key": "chain|Swap|pair_address|tx_hash|log_index",
        "status_allowed": ["raw_observed", "accepted_for_future_exact_swap_review", "needs_repair", "rejected"],
        "no_duplicate_insert": True,
        "no_upsert": True,
        "no_mapping_from_raw_swap_alone": True,
        "no_client_signal_or_trade_from_raw_swap_alone": True,
    }
    global_blockers = list(
        dict.fromkeys(
            [
                *("lookup_has_no_second_window_swap_logs" for _ in [1] if not future_rows),
                *("external_indexer_disabled" for _ in [1] if not allow_external),
                *("external_confirm_required" for _ in [1] if allow_external and confirm != "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP"),
                *("dex_raw_swap_events_table_missing" for _ in [1] if not table_exists),
                *("no_eligible_second_window_raw_swap_rows" for _ in [1] if future_rows and not eligible_rows),
                *("duplicate_second_window_raw_swap_rows_present" for _ in [1] if duplicate_count),
                "read_only_schema_plan_no_persistence",
                "manipulation_detection_remains_unreliable_until_persistence_and_review",
                "mapping_disabled",
                "client_signal_disabled",
                "trade_disabled",
            ]
        )
    )
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_read_only" if eligible_rows else "blocked",
        "chain": clean_chain,
        "target_table": target_table,
        "table_exists": table_exists,
        "raw_swap_count_before": raw_swap_count_before,
        "schema_preview": schema_preview,
        "indexes_preview": indexes_preview,
        "constraints_preview": constraints_preview,
        "dedupe_constraints": {
            "second_window_raw_swap_insert_digest": digest,
            "row_dedupe_key": "event_dedupe_key",
            "duplicate_count": duplicate_count,
            "eligible_rows_must_match_expected_digest": True,
        },
        "lookup_snapshot": {
            "lookup_status": lookup.get("lookup_status"),
            "summary": lookup.get("summary"),
            "external_call_gate": lookup.get("external_call_gate"),
        },
        "summary": {
            "eligible_second_window_raw_swap_rows": len(eligible_rows),
            "blocked_second_window_raw_swap_rows": len(blocked_rows),
            "eligible_by_window": eligible_by_window,
            "second_window_swap_logs_found": int((lookup.get("summary") or {}).get("second_window_swap_logs_found") or 0),
            "repeatability_ready_if_persisted_later": int((lookup.get("summary") or {}).get("repeatability_ready_if_persisted_later") or 0),
            "would_insert_raw_swap": False,
            "would_write": False,
            "usable_for_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "future_rows_preview": future_rows,
        "blockers": global_blockers,
        "next_safe_step": (
            "second_window_raw_swap_evidence_insert_dry_run_first"
            if eligible_rows
            else "repair_or_expand_second_window_sqd_lookup"
        ),
        **disabled,
    }


def insert_manipulation_detection_second_window_raw_swap_evidence(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_second_window_raw_swap_insert_digest: str | None = None,
    max_sqd_calls: int = 4,
    max_logs_total: int = 500,
    timeout: int = 8,
) -> dict[str, Any]:
    """Dry-run-first data-only insert for second-window exact raw Swap logs."""
    engine = _engine()
    clean_chain = _normalize_chain(chain or "bsc")
    clean_limit = max(1, min(int(limit or 5), 25))
    safe_sqd_calls = max(1, min(int(max_sqd_calls or 4), 10))
    safe_logs_total = max(1, min(int(max_logs_total or 500), 5_000))
    safe_timeout = max(2, min(int(timeout or 8), 15))
    target_table = "dex_raw_swap_events"
    lookup_confirm = "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP"
    preview_confirm = "PREVIEW_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE_INSERT"
    insert_confirm = "INSERT_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE"
    source_policy = (
        "admin-only dry-run-first second-window raw Swap evidence insert. It may call SQD only when "
        "allow_external is true and confirmation is explicit. Confirmed writes are limited to "
        "dex_raw_swap_events raw observations; it creates no mappings, router evidence, labels, client "
        "signals, trades, wallet orders or opt-ins."
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
        blockers.append("allow_external_required_for_second_window_raw_swap_insert_preview")
    if dry_run and allow_external and not external_confirmed_for_preview:
        blockers.append("confirm_PREVIEW_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE_INSERT_required")
    if not dry_run:
        if confirm != insert_confirm:
            blockers.append("confirm_INSERT_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE_required")
        if not str(expected_second_window_raw_swap_insert_digest or "").strip():
            blockers.append("expected_second_window_raw_swap_insert_digest_required")
        if not allow_external:
            blockers.append("allow_external_required_for_confirmed_second_window_raw_swap_insert")

    if blockers:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "insert_status": "blocked",
            "chain": clean_chain,
            "target_table": target_table,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "expected_second_window_raw_swap_insert_digest": expected_second_window_raw_swap_insert_digest,
            "would_call_external": False,
            "external_calls_performed": 0,
            "would_insert_second_window_raw_swap": False,
            "inserted": False,
            "rows_inserted": 0,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
            "blockers": list(dict.fromkeys(blockers)),
            **disabled,
        }

    plan = get_manipulation_detection_second_window_raw_swap_evidence_schema_plan(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        allow_external=allow_external,
        confirm=lookup_confirm,
        max_sqd_calls=safe_sqd_calls,
        max_logs_total=safe_logs_total,
        timeout=safe_timeout,
    )
    plan_digest = str((plan.get("dedupe_constraints") or {}).get("second_window_raw_swap_insert_digest") or "")
    future_rows = list(plan.get("future_rows_preview") or [])
    eligible_rows = [row for row in future_rows if row.get("eligible_for_future_insert")]

    if plan.get("plan_status") != "ready_read_only":
        blockers.append("second_window_raw_swap_schema_plan_not_ready")
    if not eligible_rows:
        blockers.append("no_eligible_second_window_raw_swap_rows")
    if not plan_digest:
        blockers.append("second_window_raw_swap_insert_digest_missing")
    if not dry_run and plan_digest != str(expected_second_window_raw_swap_insert_digest or "").strip():
        blockers.append("expected_second_window_raw_swap_insert_digest_mismatch")

    conn = _get_db()
    conn.row_factory = sqlite3.Row
    duplicates: list[str] = []
    checkpoint_by_key: dict[str, int | None] = {}
    raw_swap_count_before = 0
    table_exists = False
    try:
        table_exists = _table_exists(conn, target_table)
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
                if _table_exists(conn, "dex_event_reader_checkpoints"):
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
                            clean_chain,
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
        blockers.append("duplicate_second_window_raw_swap_event_exists")
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
            "chain": clean_chain,
            "target_table": target_table,
            "table_exists": table_exists,
            "raw_swap_count_before": raw_swap_count_before,
            "eligible_second_window_raw_swap_rows": len(eligible_rows),
            "blocked_second_window_raw_swap_rows": int((plan.get("summary") or {}).get("blocked_second_window_raw_swap_rows") or 0),
            "second_window_raw_swap_insert_digest": plan_digest or None,
            "expected_second_window_raw_swap_insert_digest": expected_second_window_raw_swap_insert_digest,
            "required_preview_confirm": preview_confirm,
            "required_insert_confirm": insert_confirm,
            "external_calls_performed": external_calls_performed,
            "would_call_external": bool(allow_external),
            "would_insert_second_window_raw_swap": would_insert,
            "would_insert_second_window_raw_swap_count": len(clean_rows) if would_insert else 0,
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
    conn = _get_db()
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
        "chain": clean_chain,
        "target_table": target_table,
        "raw_swap_count_before": raw_swap_count_before,
        "raw_swap_count_after": raw_swap_count_after,
        "eligible_second_window_raw_swap_rows": len(eligible_rows),
        "second_window_raw_swap_insert_digest": plan_digest or None,
        "expected_second_window_raw_swap_insert_digest": expected_second_window_raw_swap_insert_digest,
        "external_calls_performed": external_calls_performed,
        "would_call_external": False,
        "would_insert_second_window_raw_swap": False,
        "inserted": True,
        "rows_inserted": len(clean_rows),
        "would_write": False,
        "real_write_enabled": True,
        "writes_performed": len(clean_rows),
        "blockers": [],
        **disabled,
    }


def _raw_swap_gap_windows(rows: list[sqlite3.Row], *, gap_blocks: int = 10_000) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    current: list[sqlite3.Row] = []
    previous_block: int | None = None

    for row in rows:
        block_number = int(row["block_number"] or 0)
        if current and previous_block is not None and block_number - previous_block > gap_blocks:
            windows.append(_raw_swap_window_summary(current, len(windows) + 1))
            current = []
        current.append(row)
        previous_block = block_number

    if current:
        windows.append(_raw_swap_window_summary(current, len(windows) + 1))
    return windows


def _raw_swap_window_summary(rows: list[sqlite3.Row], index: int) -> dict[str, Any]:
    blocks = [int(row["block_number"] or 0) for row in rows]
    timestamps = [int(row["block_timestamp"] or 0) for row in rows if row["block_timestamp"] is not None]
    tx_hashes = {str(row["tx_hash"] or "").lower() for row in rows if row["tx_hash"]}
    return {
        "window_index": index,
        "window_label": f"raw_activity_window_{index}",
        "raw_swap_rows": len(rows),
        "distinct_tx_hashes": len(tx_hashes),
        "distinct_blocks": len(set(blocks)),
        "first_block": min(blocks) if blocks else None,
        "last_block": max(blocks) if blocks else None,
        "block_span": (max(blocks) - min(blocks) + 1) if blocks else 0,
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "sample_tx_hashes": sorted(tx_hashes)[:5],
        "read_only": True,
    }


def get_manipulation_detection_raw_swap_repeatability_review(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only review of raw Swap repeatability without promoting to scoring."""
    clean_chain = _normalize_chain(chain or "bsc")
    clean_pool = str(pool_address or "").strip().lower()
    source_policy = (
        "admin-only read-only raw Swap repeatability review. It reads dex_raw_swap_events only, "
        "does not call providers or indexers, and does not create mappings, labels, client signals, "
        "trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_call_rpc": False,
        "would_call_sqd": False,
        "would_persist_raw_swap": False,
        "would_insert_raw_swap": False,
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
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "review_status": "blocked",
            "chain": clean_chain,
            "pool_address": clean_pool or None,
            "blockers": ["dry_run_required"],
            **disabled,
        }

    blockers: list[str] = []
    conn = _get_db()
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "dex_raw_swap_events"):
            return {
                "ok": True,
                "dry_run": True,
                "review_status": "blocked",
                "chain": clean_chain,
                "pool_address": clean_pool or None,
                "summary": {
                    "raw_swap_rows": 0,
                    "distinct_tx_hashes": 0,
                    "distinct_blocks": 0,
                    "independent_raw_activity_windows": 0,
                    "repeatability_from_raw_events": False,
                    "can_detect_reliable_manipulation_now": False,
                },
                "raw_activity_windows": [],
                "blockers": ["dex_raw_swap_events_table_missing"],
                **disabled,
            }

        if not clean_pool:
            top_row = conn.execute(
                """
                SELECT lower(pair_address) AS pair_address, COUNT(*) AS raw_swap_rows
                FROM dex_raw_swap_events
                WHERE lower(chain) = ?
                GROUP BY lower(pair_address)
                ORDER BY raw_swap_rows DESC
                LIMIT 1
                """,
                (clean_chain,),
            ).fetchone()
            clean_pool = str(top_row["pair_address"] or "").lower() if top_row else ""

        if not clean_pool:
            return {
                "ok": True,
                "dry_run": True,
                "review_status": "blocked",
                "chain": clean_chain,
                "pool_address": None,
                "summary": {
                    "raw_swap_rows": 0,
                    "distinct_tx_hashes": 0,
                    "distinct_blocks": 0,
                    "independent_raw_activity_windows": 0,
                    "repeatability_from_raw_events": False,
                    "can_detect_reliable_manipulation_now": False,
                },
                "raw_activity_windows": [],
                "blockers": ["no_raw_swap_pool_available"],
                **disabled,
            }

        rows = list(
            conn.execute(
                """
                SELECT id, chain, pair_address, sender, recipient, amount0_in, amount1_in,
                       amount0_out, amount1_out, tx_hash, log_index, block_number,
                       block_hash, block_timestamp, event_topic, payload_digest,
                       event_dedupe_key, status, created_at, source_policy
                FROM dex_raw_swap_events
                WHERE lower(chain) = ? AND lower(pair_address) = ?
                ORDER BY block_number ASC, tx_hash ASC, log_index ASC
                """,
                (clean_chain, clean_pool),
            )
        )
        total_raw_rows = len(rows)
        tx_hashes = {str(row["tx_hash"] or "").lower() for row in rows if row["tx_hash"]}
        blocks = [int(row["block_number"] or 0) for row in rows]
        timestamps = [int(row["block_timestamp"] or 0) for row in rows if row["block_timestamp"] is not None]
        topics = {str(row["event_topic"] or "").lower() for row in rows if row["event_topic"]}
        missing_digest_rows = sum(1 for row in rows if not str(row["payload_digest"] or "").strip())
        missing_dedupe_rows = sum(1 for row in rows if not str(row["event_dedupe_key"] or "").strip())
        duplicate_dedupe_rows = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT event_dedupe_key
                FROM dex_raw_swap_events
                WHERE lower(chain) = ? AND lower(pair_address) = ?
                GROUP BY event_dedupe_key
                HAVING COUNT(*) > 1
            )
            """,
            (clean_chain, clean_pool),
        ).fetchone()[0]
        source_batches = [
            {
                "source_policy": str(row["source_policy"] or ""),
                "raw_swap_rows": int(row["raw_swap_rows"] or 0),
                "first_block": int(row["first_block"]) if row["first_block"] is not None else None,
                "last_block": int(row["last_block"]) if row["last_block"] is not None else None,
            }
            for row in conn.execute(
                """
                SELECT source_policy, COUNT(*) AS raw_swap_rows,
                       MIN(block_number) AS first_block,
                       MAX(block_number) AS last_block
                FROM dex_raw_swap_events
                WHERE lower(chain) = ? AND lower(pair_address) = ?
                GROUP BY source_policy
                ORDER BY first_block ASC
                """,
                (clean_chain, clean_pool),
            )
        ]
    finally:
        conn.close()

    windows = _raw_swap_gap_windows(rows, gap_blocks=10_000)
    repeatability_from_raw_events = (
        total_raw_rows >= 10
        and len(tx_hashes) >= 10
        and len(set(blocks)) >= 10
        and len(windows) >= 2
        and missing_digest_rows == 0
        and missing_dedupe_rows == 0
        and int(duplicate_dedupe_rows or 0) == 0
    )
    if total_raw_rows < 10:
        blockers.append("too_few_raw_swap_rows_min_10")
    if len(tx_hashes) < 10:
        blockers.append("too_few_raw_swap_tx_hashes_min_10")
    if len(set(blocks)) < 10:
        blockers.append("too_few_raw_swap_blocks_min_10")
    if len(windows) < 2:
        blockers.append("repeatability_missing_min_2_raw_activity_windows")
    if missing_digest_rows:
        blockers.append("raw_swap_payload_digest_missing")
    if missing_dedupe_rows:
        blockers.append("raw_swap_dedupe_key_missing")
    if int(duplicate_dedupe_rows or 0):
        blockers.append("duplicate_raw_swap_dedupe_keys")

    downstream_blockers = [
        "transfer_context_not_scored_here",
        "source_backed_scoring_not_enabled",
        "backtest_not_run",
        "policy_engine_not_authorized_for_signal",
        "client_opt_in_missing",
    ]

    return {
        "ok": True,
        "dry_run": True,
        "review_status": "raw_repeatability_ready_read_only" if repeatability_from_raw_events else "blocked",
        "chain": clean_chain,
        "pool_address": clean_pool,
        "summary": {
            "raw_swap_rows": total_raw_rows,
            "distinct_tx_hashes": len(tx_hashes),
            "distinct_blocks": len(set(blocks)),
            "first_block": min(blocks) if blocks else None,
            "last_block": max(blocks) if blocks else None,
            "raw_block_span": (max(blocks) - min(blocks) + 1) if blocks else 0,
            "first_timestamp": min(timestamps) if timestamps else None,
            "last_timestamp": max(timestamps) if timestamps else None,
            "event_topics": sorted(topics),
            "payload_digest_present_rows": total_raw_rows - missing_digest_rows,
            "event_dedupe_key_present_rows": total_raw_rows - missing_dedupe_rows,
            "duplicate_event_dedupe_keys": int(duplicate_dedupe_rows or 0),
            "independent_raw_activity_windows": len(windows),
            "repeatability_from_raw_events": repeatability_from_raw_events,
            "can_detect_reliable_manipulation_now": False,
            "source_backed_scoring": False,
            "mapping_ready_now": 0,
        },
        "raw_activity_windows": windows,
        "source_batches": source_batches,
        "decision_explanation": {
            "what_is_now_stronger": (
                "UFLOKI now has repeated exact raw Swap observations across independent local activity windows."
            ),
            "what_is_not_proven_yet": (
                "This does not prove profitable manipulation by itself; transfers, source-backed scoring, "
                "repeatability scoring integration and backtest still need separate gates."
            ),
            "why_no_trade": (
                "Raw swaps are observation data only. There is no policy/risk approval, no client opt-in, "
                "no paper-trading proof and no execution permission."
            ),
        },
        "blockers": blockers,
        "remaining_before_product_signal": downstream_blockers,
        **disabled,
    }
