from __future__ import annotations

from typing import Any

from services.onchain.core.json import _coerce_int, _json_list
from services.onchain.manipulation_verdicts import (
    _build_holder_flow_evidence_verdict,
    _build_manipulation_research_verdict,
    _maximum_readiness_requirement,
    _minimum_readiness_requirement,
    _readiness_gate,
)


def _engine():
    from services import onchain_engine

    return onchain_engine


def _init_db() -> None:
    return _engine()._init_db()


def _normalize_chain(value: str) -> str:
    return _engine()._normalize_chain(value)


def _get_db():
    return _engine()._get_db()


def entity_in_clause(*args: Any, **kwargs: Any):
    return _engine().entity_in_clause(*args, **kwargs)


def get_onchain_data_readiness(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_onchain_data_readiness(*args, **kwargs)


def get_rpc_wallet_state_audit(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_rpc_wallet_state_audit(*args, **kwargs)


def get_token_transfer_cex_deposit_scan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_token_transfer_cex_deposit_scan(*args, **kwargs)


def get_manipulation_detection_readiness(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    """Read-only gate for whether manipulation detection can be trusted yet."""
    _init_db()
    safe_limit = _coerce_int(limit, 12, 1, 50)
    requested_chain = _normalize_chain(chain or "") if chain else None
    readiness = get_onchain_data_readiness(entity=entity, limit=safe_limit)
    wallet_audit = get_rpc_wallet_state_audit(entity=entity, chain=requested_chain, stale_after_hours=24, limit=safe_limit)
    cex_token_deposits = get_token_transfer_cex_deposit_scan(chain=requested_chain, limit=safe_limit)

    where: list[str] = []
    params: list[Any] = []
    wallet_where: list[str] = []
    wallet_params: list[Any] = []
    if requested_chain:
        where.append("chain = ?")
        params.append(requested_chain)
        wallet_where.append("chain = ?")
        wallet_params.append(requested_chain)
    if entity:
        clause, clause_params = entity_in_clause("entity", entity)
        wallet_where.append(clause)
        wallet_params.extend(clause_params)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    wallet_where_sql = f"WHERE {' AND '.join(wallet_where)}" if wallet_where else ""

    conn = _get_db()
    try:
        swap_totals = conn.execute(
            f"""
            SELECT
                COUNT(*),
                COUNT(DISTINCT wallet),
                COUNT(DISTINCT CASE WHEN COALESCE(token_in, '') != '' THEN LOWER(token_in) END),
                COUNT(DISTINCT CASE WHEN COALESCE(token_out, '') != '' THEN LOWER(token_out) END),
                MIN(timestamp),
                MAX(timestamp),
                MIN(block_number),
                MAX(block_number),
                SUM(COALESCE(amount_usd, 0)),
                SUM(CASE WHEN token_identity_quality = 'exact_pair_log_direction' THEN 1 ELSE 0 END),
                SUM(CASE WHEN token_identity_quality = 'legacy_inferred_pair_tokens' THEN 1 ELSE 0 END)
            FROM swaps
            {where_sql}
            """,
            params,
        ).fetchone()
        wallet_totals = conn.execute(
            f"""
            SELECT
                COUNT(*),
                SUM(CASE WHEN json_array_length(COALESCE(token_balances_json, '[]')) > 0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN COALESCE(tx_count, 0) > 0 THEN 1 ELSE 0 END),
                COUNT(DISTINCT chain),
                COUNT(DISTINCT COALESCE(entity, ''))
            FROM wallet_chain_state
            {wallet_where_sql}
            """,
            wallet_params,
        ).fetchone()
        risk_rows = [
            {
                "entity": row[0] or "unknown",
                "chain": row[1],
                "wallets": int(row[2] or 0),
                "avg_quality": round(float(row[3] or 0), 2),
                "risk_flags": _json_list(row[4]),
            }
            for row in conn.execute(
                f"""
                SELECT COALESCE(entity, 'unknown'), chain, COUNT(*), AVG(COALESCE(data_quality_score, 0)),
                       MAX(risk_flags_json)
                FROM wallet_chain_state
                {wallet_where_sql}
                GROUP BY COALESCE(entity, 'unknown'), chain
                ORDER BY COUNT(*) DESC
                LIMIT ?
                """,
                [*wallet_params, safe_limit],
            ).fetchall()
        ]
    finally:
        conn.close()

    from services.label_ledger import get_label_candidate_evidence_scores

    evidence_scores = get_label_candidate_evidence_scores(limit=50, entity=entity, chain=chain)
    scored_rows = list(evidence_scores.get("rows") or [])
    strict_review_candidates = [
        row for row in scored_rows if row.get("decision") == "strict_review_candidate"
    ]
    collect_more_evidence = [
        row for row in scored_rows if row.get("decision") == "collect_more_evidence"
    ]

    swap_count = int(swap_totals[0] or 0)
    swap_wallets = int(swap_totals[1] or 0)
    token_in_count = int(swap_totals[2] or 0)
    token_out_count = int(swap_totals[3] or 0)
    distinct_swap_tokens = max(token_in_count, token_out_count)
    first_swap_ts = int(swap_totals[4] or 0)
    last_swap_ts = int(swap_totals[5] or 0)
    exact_swap_token_rows = int(swap_totals[9] or 0)
    inferred_swap_token_rows = int(swap_totals[10] or 0)
    history_days = round(max(0, last_swap_ts - first_swap_ts) / 86400, 2) if first_swap_ts and last_swap_ts else 0.0
    wallet_rows = int(wallet_totals[0] or 0)
    token_balance_wallets = int(wallet_totals[1] or 0)
    active_wallet_rows = int(wallet_totals[2] or 0)
    chains_observed = int(wallet_totals[3] or 0)

    readiness_summary = readiness.get("summary", {}) or {}
    strict_label_pct = float(readiness_summary.get("strict_label_pct") or 0)
    rpc_coverage_pct = float(readiness_summary.get("rpc_coverage_pct") or 0)
    venue_mapping_drafts = int(readiness_summary.get("venue_mapping_drafts") or 0)
    venue_skipped_drafts = int(readiness_summary.get("venue_skipped_drafts") or 0)
    venue_admin_review_ready = int(readiness_summary.get("venue_admin_review_ready") or 0)
    token_transfer_rows = int(readiness_summary.get("token_transfer_rows") or 0)
    token_transfer_history_days = float(readiness_summary.get("token_transfer_history_days") or 0)
    cex_token_deposit_summary = cex_token_deposits.get("summary", {}) or {}
    cex_token_deposit_rows = int(cex_token_deposit_summary.get("deposits") or 0)
    cex_token_source_backed_targets = int(cex_token_deposit_summary.get("source_backed_target_wallets") or 0)
    cex_token_target_wallets = int(cex_token_deposit_summary.get("target_exchange_wallets") or 0)
    cex_token_source_backed_depositors = int(cex_token_deposit_summary.get("source_backed_depositors") or 0)
    cex_token_fresh_like_depositors = int(cex_token_deposit_summary.get("fresh_like_depositors") or 0)
    cex_token_missing_state_depositors = int(cex_token_deposit_summary.get("missing_state_depositors") or 0)
    cex_token_funding_edges = int(cex_token_deposit_summary.get("funding_edges") or 0)
    cex_token_fresh_like_with_funding = int(cex_token_deposit_summary.get("fresh_like_depositors_with_funding") or 0)
    cex_token_fresh_like_without_funding = int(cex_token_deposit_summary.get("fresh_like_depositors_without_funding") or 0)
    cex_token_unknown_funders = int(cex_token_deposit_summary.get("unknown_funders") or 0)
    cex_token_exchange_like_funders = int(cex_token_deposit_summary.get("exchange_like_funders") or 0)
    cex_token_shared_funders = int(cex_token_deposit_summary.get("shared_funders") or 0)
    cex_token_shared_unknown_funders = int(cex_token_deposit_summary.get("shared_unknown_funders") or 0)
    cex_token_shared_exchange_like_funders = int(cex_token_deposit_summary.get("shared_exchange_like_funders") or 0)
    cex_token_coordination_score = int(cex_token_deposit_summary.get("coordination_score") or 0)
    cex_token_coordination_tier = str(cex_token_deposit_summary.get("coordination_tier") or "insufficient_evidence")
    cex_token_max_deposits_1h = int(cex_token_deposit_summary.get("max_deposits_1h") or 0)
    cex_token_max_deposits_6h = int(cex_token_deposit_summary.get("max_deposits_6h") or 0)
    cex_token_max_deposits_24h = int(cex_token_deposit_summary.get("max_deposits_24h") or 0)
    cex_token_deposit_span_minutes = float(cex_token_deposit_summary.get("deposit_span_minutes") or 0)
    cex_token_swap_rows_around_deposits = int(cex_token_deposit_summary.get("swap_rows_around_deposits") or 0)
    cex_token_swap_rows_after_24h = int(cex_token_deposit_summary.get("swap_rows_after_24h") or 0)
    cex_token_swap_tokens_without_local_swaps = int(cex_token_deposit_summary.get("swap_tokens_without_local_swaps") or 0)
    cex_token_price_proxy_tokens = int(cex_token_deposit_summary.get("price_proxy_tokens") or 0)
    cex_token_price_proxy_before_after_tokens = int(cex_token_deposit_summary.get("price_proxy_before_after_tokens") or 0)
    cex_token_price_proxy_max_change_pct = float(cex_token_deposit_summary.get("price_proxy_max_change_pct") or 0)
    cex_token_holder_flow_tokens = int(cex_token_deposit_summary.get("holder_flow_tokens") or 0)
    cex_token_holder_flow_high_cex_share_tokens = int(cex_token_deposit_summary.get("holder_flow_high_cex_share_tokens") or 0)
    cex_token_holder_flow_high_fresh_like_share_tokens = int(cex_token_deposit_summary.get("holder_flow_high_fresh_like_share_tokens") or 0)
    cex_token_holder_flow_high_top_holder_concentration_tokens = int(cex_token_deposit_summary.get("holder_flow_high_top_holder_concentration_tokens") or 0)
    cex_token_holder_flow_high_supply_share_tokens = int(cex_token_deposit_summary.get("holder_flow_high_supply_share_tokens") or 0)
    cex_token_holder_flow_max_cex_share_pct = float(cex_token_deposit_summary.get("holder_flow_max_cex_share_pct") or 0)
    cex_token_holder_flow_max_top3_depositor_share_pct = float(cex_token_deposit_summary.get("holder_flow_max_top3_depositor_share_pct") or 0)
    cex_token_holder_flow_max_fresh_like_share_pct = float(cex_token_deposit_summary.get("holder_flow_max_fresh_like_share_pct") or 0)
    cex_token_holder_flow_max_top_holder_share_pct = float(cex_token_deposit_summary.get("holder_flow_max_top_holder_share_pct") or 0)
    cex_token_holder_flow_max_top10_holder_share_pct = float(cex_token_deposit_summary.get("holder_flow_max_top10_holder_share_pct") or 0)
    cex_token_holder_flow_max_supply_share_pct = float(cex_token_deposit_summary.get("holder_flow_max_supply_share_pct") or 0)
    cex_token_holder_supply_snapshot_tokens = int(cex_token_deposit_summary.get("holder_supply_snapshot_tokens") or 0)
    counterparty_router_source_rows = int(readiness_summary.get("counterparty_router_source_search_rows") or 0)
    counterparty_router_context_rows = int(readiness_summary.get("counterparty_router_context_rows") or 0)
    counterparty_router_exact_sources = int(readiness_summary.get("counterparty_router_exact_sources") or 0)
    counterparty_router_admin_ready = int(readiness_summary.get("counterparty_router_admin_review_ready") or 0)
    unknown_router_contracts = int(readiness_summary.get("unknown_router_contracts") or 0)
    unknown_router_repeated_code_groups = int(readiness_summary.get("unknown_router_repeated_code_groups") or 0)
    router_source_unknown_routers = int(readiness_summary.get("unknown_router_source_unknown_routers") or 0)
    router_source_missing_state = int(readiness_summary.get("unknown_router_source_missing_state") or 0)
    router_source_missing_label_sources = int(readiness_summary.get("unknown_router_source_missing_label_sources") or 0)
    router_source_with_label_sources = int(readiness_summary.get("unknown_router_source_with_label_sources") or 0)
    router_proof_dossiers = int(readiness_summary.get("unknown_router_proof_dossiers") or 0)
    router_proof_research_ready = int(readiness_summary.get("unknown_router_proof_research_ready") or 0)
    router_proof_official_review_possible = int(readiness_summary.get("unknown_router_proof_official_review_possible") or 0)
    router_proof_insufficient_identity = int(readiness_summary.get("unknown_router_proof_insufficient_identity") or 0)
    router_proof_conflicts = int(readiness_summary.get("unknown_router_proof_conflicts") or 0)
    router_creator_identity_rows = int(readiness_summary.get("unknown_router_creator_identity_rows") or 0)
    router_creator_groups = int(readiness_summary.get("unknown_router_creator_groups") or 0)
    router_creator_address_only_rows = int(readiness_summary.get("unknown_router_creator_address_only_rows") or 0)
    router_creator_candidate_venue_hints = int(readiness_summary.get("unknown_router_creator_candidate_venue_hints") or 0)
    router_creator_probe_required = int(readiness_summary.get("unknown_router_creator_identity_probe_required") or 0)
    unknown_venue_swaps = int(
        (readiness.get("venue_discovery", {}).get("summary") or {}).get("unknown_venue_swaps") or 0
    )
    traceability_pct = float(wallet_audit.get("traceability_pct") or 0)
    audit_total_wallets = int(wallet_audit.get("total_wallets") or 0)
    audit_missing_label_sources = int(wallet_audit.get("missing_label_sources") or 0)
    label_source_pct = (
        round(((audit_total_wallets - audit_missing_label_sources) / audit_total_wallets) * 100, 2)
        if audit_total_wallets
        else 0
    )

    blockers: list[str] = []
    next_actions: list[str] = []
    if strict_label_pct < 20:
        blockers.append("strict_label_coverage_too_low")
        next_actions.append("Convert legacy labels into source-backed candidates and verified evidence before using entity labels as signal truth.")
    if traceability_pct < 95:
        blockers.append("wallet_source_traceability_incomplete")
        next_actions.append("Repair wallet_chain_state source attribution before signal generation.")
    if label_source_pct < 95:
        blockers.append("wallet_label_source_evidence_incomplete")
        next_actions.append("Continue label-source gap corroboration until wallet label sources are near-complete.")
    if swap_count < 1_000:
        blockers.append("swap_history_too_shallow")
        next_actions.append("Ingest historical DEX/router transfer windows per target chain/token before manipulation baselines.")
    if distinct_swap_tokens < 20 or exact_swap_token_rows < 100:
        blockers.append("token_flow_surface_too_narrow")
        next_actions.append("Track exact token_in/token_out identities and holder deltas for target tokens, not only entity wallets.")
    if token_transfer_rows < 500:
        blockers.append("token_transfer_history_too_shallow")
        next_actions.append("Ingest ERC20/BEP20 Transfer logs so CEX token deposits and holder-flow changes can be confirmed from RPC data.")
    if history_days < 14:
        blockers.append("insufficient_time_history")
        next_actions.append("Build at least 14-30 days of comparable flow/swap/holder history before alert thresholds.")
    if token_transfer_rows and token_transfer_history_days < 14:
        blockers.append("token_transfer_time_window_too_short")
        next_actions.append("Extend Transfer-log ingestion to at least 14-30 days before trusting token-deposit manipulation evidence.")
    if cex_token_deposit_rows and cex_token_source_backed_targets < cex_token_target_wallets:
        blockers.append("cex_token_deposit_targets_need_source_backing")
        next_actions.append("Attach source-backed exchange labels to CEX deposit targets before using deposit flows as manipulation evidence.")
    if cex_token_missing_state_depositors:
        blockers.append("cex_token_deposit_depositor_wallet_state_missing")
        next_actions.append("Enrich CEX token deposit sender wallets before treating exchange deposits as manipulation evidence.")
    if cex_token_fresh_like_depositors:
        blockers.append("cex_token_fresh_like_depositors_need_funding_graph")
        next_actions.append("Expand funding graphs for fresh-like CEX token depositors before any client automation.")
    if cex_token_fresh_like_without_funding:
        blockers.append("cex_token_fresh_like_depositors_missing_funding_edges")
        next_actions.append("Backfill native transaction history around fresh-like CEX token depositors until funding edges are visible.")
    if cex_token_unknown_funders:
        blockers.append("cex_token_deposit_funders_need_source_backing")
        next_actions.append("Resolve upstream funder identity/source evidence before treating CEX token deposits as coordinated manipulation.")
    if cex_token_shared_unknown_funders:
        blockers.append("cex_token_shared_unknown_funder_to_multiple_depositors")
        next_actions.append("Prioritize shared unknown funders that finance multiple CEX token depositors; this is a coordination hint, not identity proof.")
    if cex_token_exchange_like_funders:
        blockers.append("cex_token_exchange_like_funders_false_positive_risk")
        next_actions.append("Separate normal CEX withdrawal funding from coordinated gas fan-out before client automation.")
    if cex_token_shared_exchange_like_funders:
        blockers.append("cex_token_shared_exchange_like_funder_false_positive_risk")
        next_actions.append("Treat shared CEX-like funders as high false-positive risk unless downstream token-deposit timing is corroborated.")
    if cex_token_coordination_score >= 50:
        blockers.append("cex_token_coordination_signal_requires_human_review")
        next_actions.append("Review CEX token-deposit coordination evidence before any client-facing automation or copy signal.")
    if cex_token_max_deposits_6h >= 2:
        blockers.append("cex_token_temporal_cluster_requires_review")
        next_actions.append("Corroborate clustered CEX token deposits against pre/post price movement before client-facing automation.")
    if cex_token_deposit_rows and not cex_token_swap_rows_around_deposits:
        blockers.append("cex_token_swap_corroboration_missing")
        next_actions.append("Backfill exact local swaps around CEX token deposits before treating the event as market manipulation.")
    if cex_token_swap_tokens_without_local_swaps:
        blockers.append("cex_token_deposit_tokens_missing_swap_context")
        next_actions.append("Add swap/venue coverage for deposited tokens before client-facing automation.")
    if cex_token_deposit_rows and not cex_token_price_proxy_before_after_tokens:
        blockers.append("cex_token_price_proxy_before_after_missing")
        next_actions.append("Backfill local swaps before and after CEX deposit clusters before using price-movement features.")
    if cex_token_deposit_rows and not cex_token_holder_supply_snapshot_tokens:
        blockers.append("cex_token_holder_supply_snapshot_missing")
        next_actions.append("Backfill true holder/supply snapshots for deposited tokens before estimating market impact or unlock/team risk.")
    if cex_token_holder_flow_high_cex_share_tokens:
        blockers.append("cex_token_holder_flow_high_observed_flow_share_needs_review")
        next_actions.append("Review tokens where CEX deposits dominate observed transfer flow; this is a concentration hint until true holders are indexed.")
    if cex_token_holder_flow_high_fresh_like_share_tokens:
        blockers.append("cex_token_holder_flow_high_fresh_like_share_needs_review")
        next_actions.append("Review tokens where fresh-like wallets carry most CEX deposit value; corroborate with holders/supply before client automation.")
    if cex_token_holder_flow_high_top_holder_concentration_tokens:
        blockers.append("cex_token_top_holder_concentration_needs_review")
        next_actions.append("Review top-holder concentration before treating token movement as tradable signal; concentrated supply can be team/treasury risk.")
    if cex_token_holder_flow_high_supply_share_tokens:
        blockers.append("cex_token_deposit_supply_share_needs_review")
        next_actions.append("Review CEX deposit share versus estimated supply; large supply movements to exchanges are distribution-risk evidence, not a buy signal.")
    if len(strict_review_candidates) < 10:
        blockers.append("not_enough_verified_candidate_evidence")
        next_actions.append("Grow strict review candidates from public evidence before trusting labels in manipulation scoring.")
    if unknown_venue_swaps:
        blockers.append("venue_identity_debt_blocks_manipulation_signals")
        next_actions.append("Resolve unknown DEX/router venues before using venue-level manipulation patterns.")
    if router_source_missing_state:
        blockers.append("unknown_router_rpc_state_blocks_manipulation_signals")
        next_actions.append("Enrich missing unknown router RPC state before scoring venue/router behavior.")
    if router_source_missing_label_sources:
        blockers.append("unknown_router_source_evidence_blocks_manipulation_signals")
        next_actions.append("Attach official/source-backed router evidence before using routers as manipulation features.")
    if router_proof_conflicts:
        blockers.append("unknown_router_proof_conflicts_block_manipulation_signals")
        next_actions.append("Resolve official chain/address conflicts before router-level manipulation features.")
    if router_proof_insufficient_identity:
        blockers.append("unknown_router_identity_gaps_block_manipulation_signals")
        next_actions.append("Acquire stronger router identity evidence before protocol/venue-level behavior scoring.")
    if router_proof_research_ready and not router_proof_official_review_possible:
        blockers.append("unknown_router_official_sources_missing_for_research_ready_dossiers")
        next_actions.append("Collect exact official chain+router sources for research-ready proof dossiers before signal upgrades.")
    if router_creator_address_only_rows:
        blockers.append("unknown_router_creator_identity_only_blocks_manipulation_signals")
        next_actions.append("Resolve creator/deployer identity before using unknown routers as venue/protocol features.")
    if router_creator_probe_required:
        blockers.append("unknown_router_creator_identity_probe_required_blocks_manipulation_signals")
        next_actions.append("Run detailed creator/deployer identity acquisition before venue/protocol manipulation scoring.")
    if unknown_router_repeated_code_groups:
        blockers.append("unknown_router_code_families_block_manipulation_signals")
        next_actions.append("Investigate repeated unknown router bytecode families before venue-level manipulation scoring.")
    if venue_skipped_drafts:
        blockers.append("technical_component_venue_candidates_need_review")
        next_actions.append("Review skipped venue candidates so proxy/component contracts do not pollute venue signals.")
    if venue_mapping_drafts and venue_admin_review_ready < venue_mapping_drafts:
        blockers.append("venue_drafts_not_fully_admin_review_ready")
        next_actions.append("Corroborate all venue drafts with official protocol sources before source-backed mapping writes.")
    if counterparty_router_context_rows and counterparty_router_exact_sources < counterparty_router_context_rows:
        blockers.append("counterparty_router_exact_sources_missing_for_manipulation_signals")
        next_actions.append("Find exact official router sources for counterparty-derived venue contexts before using them in manipulation features.")

    signal_score = max(
        0,
        min(
            100,
            round(
                (strict_label_pct * 0.20)
                + (rpc_coverage_pct * 0.15)
                + (traceability_pct * 0.15)
                + (label_source_pct * 0.15)
                + min(15, swap_count / 100)
                + min(10, history_days / 3)
                + min(10, len(strict_review_candidates) * 2),
                2,
            ),
        ),
    )
    if unknown_venue_swaps:
        signal_score = max(0, round(signal_score - min(15, unknown_venue_swaps / 5), 2))
    if venue_skipped_drafts:
        signal_score = max(0, round(signal_score - min(10, venue_skipped_drafts * 2), 2))
    if unknown_router_repeated_code_groups:
        signal_score = max(0, round(signal_score - min(6, unknown_router_repeated_code_groups * 2), 2))
    if router_source_missing_state:
        signal_score = max(0, round(signal_score - min(8, router_source_missing_state / 2), 2))
    if router_source_missing_label_sources:
        signal_score = max(0, round(signal_score - min(8, router_source_missing_label_sources), 2))
    if router_proof_conflicts:
        signal_score = max(0, round(signal_score - min(6, router_proof_conflicts * 3), 2))
    if router_proof_insufficient_identity:
        signal_score = max(0, round(signal_score - min(6, router_proof_insufficient_identity * 2), 2))
    if router_proof_research_ready and not router_proof_official_review_possible:
        signal_score = max(0, round(signal_score - min(5, router_proof_research_ready), 2))
    if router_creator_address_only_rows:
        signal_score = max(0, round(signal_score - min(5, router_creator_address_only_rows), 2))
    if router_creator_probe_required:
        signal_score = max(0, round(signal_score - min(5, router_creator_probe_required), 2))
    if counterparty_router_context_rows and counterparty_router_exact_sources < counterparty_router_context_rows:
        signal_score = max(0, round(signal_score - min(8, counterparty_router_context_rows - counterparty_router_exact_sources), 2))
    if token_transfer_rows < 500:
        signal_score = max(0, round(signal_score - min(8, (500 - token_transfer_rows) / 100), 2))
    if not blockers and signal_score >= 80:
        status = "research_ready_for_watchlist_signals"
    elif signal_score >= 45:
        status = "watch_only_not_client_trade_ready"
    else:
        status = "not_ready_for_manipulation_detection"

    foundation_blockers = [
        blocker for blocker in [
            "strict_label_coverage_too_low" if strict_label_pct < 20 else "",
            "wallet_source_traceability_incomplete" if traceability_pct < 95 else "",
            "wallet_label_source_evidence_incomplete" if label_source_pct < 95 else "",
        ] if blocker
    ]
    history_blockers = [
        blocker for blocker in [
            "swap_history_too_shallow" if swap_count < 1_000 else "",
            "token_flow_surface_too_narrow" if exact_swap_token_rows < 100 else "",
            "token_transfer_history_too_shallow" if token_transfer_rows < 500 else "",
            "insufficient_time_history" if history_days < 14 else "",
            "token_transfer_time_window_too_short" if token_transfer_rows and token_transfer_history_days < 14 else "",
        ] if blocker
    ]
    venue_blockers = [
        blocker for blocker in [
            "venue_identity_debt_blocks_manipulation_signals" if unknown_venue_swaps else "",
            "unknown_router_source_evidence_blocks_manipulation_signals" if router_source_missing_label_sources else "",
            "unknown_router_identity_gaps_block_manipulation_signals" if router_proof_insufficient_identity else "",
            "counterparty_router_exact_sources_missing_for_manipulation_signals"
            if counterparty_router_context_rows and counterparty_router_exact_sources < counterparty_router_context_rows else "",
        ] if blocker
    ]
    signal_blockers = [
        blocker for blocker in [
            "not_enough_verified_candidate_evidence" if len(strict_review_candidates) < 10 else "",
            "unknown_router_proof_conflicts_block_manipulation_signals" if router_proof_conflicts else "",
            "unknown_router_code_families_block_manipulation_signals" if unknown_router_repeated_code_groups else "",
        ] if blocker
    ]
    maturity_gates = [
        _readiness_gate(
            "foundation_traceable_labels",
            min(strict_label_pct / 20 * 100, traceability_pct, label_source_pct),
            100,
            foundation_blockers,
        ),
        _readiness_gate(
            "exact_swap_history",
            min((swap_count / 1_000) * 100, (exact_swap_token_rows / 100) * 100, (history_days / 14) * 100),
            100,
            history_blockers,
        ),
        _readiness_gate(
            "venue_router_attribution",
            100 if not venue_blockers else max(0, 100 - (len(venue_blockers) * 25)),
            100,
            venue_blockers,
        ),
        _readiness_gate(
            "signal_evidence_quality",
            min((len(strict_review_candidates) / 10) * 100, 100),
            100,
            signal_blockers,
        ),
    ]
    passed_gates = sum(1 for item in maturity_gates if item["passed"])
    client_maturity_stage = (
        "client_automation_research_ready"
        if status == "research_ready_for_watchlist_signals" and passed_gates == len(maturity_gates)
        else "internal_watchlist_only"
        if signal_score >= 45
        else "data_foundation_building"
    )
    client_maturity = {
        "stage": client_maturity_stage,
        "passed_gates": passed_gates,
        "total_gates": len(maturity_gates),
        "gates": maturity_gates,
        "client_copy_trading_allowed": False,
        "client_alerts_allowed": status == "research_ready_for_watchlist_signals" and passed_gates == len(maturity_gates),
        "profit_guarantee_allowed": False,
        "plain_summary_fr": (
            "Les donnees sont utilisables pour de la recherche interne, mais pas encore pour automatiser un client."
            if client_maturity_stage != "client_automation_research_ready"
            else "Les garde-fous data minimaux sont passes pour des signaux watchlist; l'execution reste desactivee."
        ),
    }

    readiness_requirements = [
        _minimum_readiness_requirement(
            "strict_label_coverage",
            "Labels strictement sources",
            strict_label_pct,
            20,
            "pct",
            "grow_strict_label_evidence",
        ),
        _minimum_readiness_requirement(
            "wallet_label_sources",
            "Sources de labels sur les wallets RPC",
            label_source_pct,
            95,
            "pct",
            "inspect_label_source_gaps",
        ),
        _minimum_readiness_requirement(
            "wallet_source_traceability",
            "Tracabilite des snapshots RPC",
            traceability_pct,
            95,
            "pct",
            "inspect_entity_coverage",
        ),
        _minimum_readiness_requirement(
            "swap_rows",
            "Swaps locaux utilisables",
            swap_count,
            1_000,
            "rows",
            "run_bounded_exact_swap_ingestion",
        ),
        _minimum_readiness_requirement(
            "exact_swap_rows",
            "Swaps exacts token_in/token_out",
            exact_swap_token_rows,
            100,
            "rows",
            "run_bounded_exact_swap_ingestion",
        ),
        _minimum_readiness_requirement(
            "token_transfer_rows",
            "Transferts ERC20/BEP20 observes",
            token_transfer_rows,
            500,
            "rows",
            "run_bounded_exact_swap_ingestion",
        ),
        _minimum_readiness_requirement(
            "swap_history_days",
            "Historique de swaps comparable",
            history_days,
            14,
            "days",
            "plan_exact_swap_ingestion",
        ),
        _minimum_readiness_requirement(
            "distinct_swap_tokens",
            "Surface multi-token observee",
            distinct_swap_tokens,
            20,
            "tokens",
            "inspect_swap_identity_readiness",
        ),
        _minimum_readiness_requirement(
            "strict_review_candidates",
            "Candidats labels prets a verifier",
            len(strict_review_candidates),
            10,
            "candidates",
            "review_verified_label_candidates",
        ),
        _maximum_readiness_requirement(
            "unknown_venue_swaps",
            "Swaps sans venue/router fiable",
            unknown_venue_swaps,
            0,
            "rows",
            "inspect_unknown_router_source_gaps",
        ),
    ]
    failed_requirements = [row for row in readiness_requirements if not row["passed"]]
    readiness_contract = {
        "version": "manipulation-readiness-v1",
        "requirements": readiness_requirements,
        "failed_requirements": failed_requirements,
        "failed_count": len(failed_requirements),
        "passed_count": len(readiness_requirements) - len(failed_requirements),
        "total_count": len(readiness_requirements),
        "execution_enabled": False,
        "client_copy_trading_allowed": False,
        "profit_guarantee_allowed": False,
        "automation_scope": "analysis_only_until_all_requirements_pass",
        "plain_summary_fr": (
            "Le signal reste en recherche: les manques exacts sont listes par seuil, sans execution client."
            if failed_requirements
            else "Les seuils data minimaux sont atteints pour une watchlist; l'execution reste desactivee."
        ),
        "source_policy": (
            "read-only readiness contract computed from local labels, wallet_chain_state and swaps; "
            "no RPC calls, labels, swaps or wallet rows are changed"
        ),
    }

    def action(
        action_id: str,
        priority: int,
        title_fr: str,
        reason: str,
        method: str,
        endpoint: str,
        admin_required: bool,
        confirm_required: str | None = None,
        dry_run_default: bool | None = None,
        env_required: str | None = None,
    ) -> dict[str, Any]:
        is_read_only = method.upper() == "GET"
        source_policy = (
            "read_only_no_mutation"
            if is_read_only and not admin_required
            else "admin_read_only"
            if is_read_only
            else "admin_guarded_mutation"
        )
        return {
            "id": action_id,
            "priority": priority,
            "title_fr": title_fr,
            "reason": reason,
            "method": method,
            "endpoint": endpoint,
            "admin_required": admin_required,
            "confirm_required": confirm_required,
            "dry_run_default": dry_run_default,
            "dry_run": bool(dry_run_default),
            "env_required": env_required,
            "source_policy": source_policy,
            "execution_enabled": False,
            "client_safe": False,
        }

    maturity_action_plan: list[dict[str, Any]] = []
    if len(strict_review_candidates) < 10:
        maturity_action_plan.append(action(
            "review_verified_label_candidates",
            30,
            "Lister les labels prets a review",
            "Prepare la promotion admin, mais ne modifie aucun label.",
            "GET",
            "/api/onchain/labels/candidates/verified-review-queue",
            False,
            None,
            None,
        ))
    if traceability_pct < 95:
        maturity_action_plan.append(action(
            "inspect_entity_coverage",
            5,
            "Mesurer la couverture labels/RPC par entite",
            "Montre les snapshots RPC sans tracabilite suffisante avant toute automatisation.",
            "GET",
            "/api/onchain/rpc/entity-coverage",
            False,
            None,
            None,
        ))
    if strict_label_pct < 20:
        maturity_action_plan.append(action(
            "inspect_entity_coverage",
            5,
            "Mesurer la couverture labels/RPC par entité",
            "Montre où les labels stricts et les wallets RPC manquent avant toute automatisation.",
            "GET",
            "/api/onchain/rpc/entity-coverage",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "grow_strict_label_evidence",
            10,
            "Augmenter les labels strictement sourcés",
            "Les labels non sourcés créent trop de faux positifs pour des signaux client.",
            "POST",
            "/api/onchain/labels/acquire-sources",
            True,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "corroborate_label_candidates",
            20,
            "Corroborer les candidats labels avec preuves",
            "Transforme les sources récupérées en preuves vérifiables sans promotion automatique.",
            "POST",
            "/api/onchain/labels/candidates/corroborate-job",
            True,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "review_verified_label_candidates",
            30,
            "Lister les labels prêts à review",
            "Prépare la promotion admin, mais ne modifie aucun label.",
            "GET",
            "/api/onchain/labels/candidates/verified-review-queue",
            False,
            None,
            None,
        ))
    if label_source_pct < 95:
        maturity_action_plan.append(action(
            "inspect_label_source_gaps",
            15,
            "Voir les wallets sans sources de label",
            "Identifie précisément quelles lignes empêchent la traçabilité à 95%+.",
            "GET",
            "/api/onchain/rpc/label-source-gaps",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "stage_label_source_gap_candidates",
            25,
            "Préparer les candidats pour combler les sources manquantes",
            "Crée une file de candidats source-gap en dry-run par défaut.",
            "POST",
            "/api/onchain/rpc/stage-label-source-gap-candidates",
            True,
            None,
            True,
        ))
        maturity_action_plan.append(action(
            "corroborate_label_source_gap_candidates",
            35,
            "Corroborer les sources manquantes",
            "Ajoute des preuves candidat-only avant toute promotion de label.",
            "POST",
            "/api/onchain/rpc/corroborate-label-source-gap-candidates",
            True,
            None,
            True,
        ))
    if swap_count < 1_000 or exact_swap_token_rows < 100 or token_transfer_rows < 500 or history_days < 14 or distinct_swap_tokens < 20:
        maturity_action_plan.append(action(
            "inspect_swap_identity_readiness",
            38,
            "Mesurer la profondeur swap/token actuelle",
            "Explique combien de swaps exacts, tokens et jours d'historique sont utilisables.",
            "GET",
            "/api/onchain/rpc/swap-identity-readiness",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "scan_pre_pump_accumulation",
            39,
            "Scanner les accumulations avant pump",
            "Compare 24h/3j/7j avant le move pour repérer les wallets entrés avant une hausse extrême.",
            "GET",
            "/api/onchain/rpc/pre-pump-accumulation-scan",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "scan_adaptive_breakout_accumulation",
            39,
            "Scanner les breakouts adaptatifs",
            "Détecte d'abord l'événement de breakout via rolling median, puis inspecte les wallets accumulateurs juste avant.",
            "GET",
            "/api/onchain/rpc/adaptive-accumulation-breakout-scan",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "backtest_adaptive_accumulation_signal",
            39,
            "Backtester le signal adaptatif",
            "Simule une entrée après confirmation breakout et une sortie après N swaps, sans exécution réelle.",
            "GET",
            "/api/onchain/rpc/adaptive-accumulation-backtest",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "compare_adaptive_strategy_timings",
            39,
            "Comparer les timings de stratégie",
            "Compare entrée au breakout, entrée après confirmation et entrée retardée pour éviter les signaux seulement gagnants en théorie.",
            "GET",
            "/api/onchain/rpc/adaptive-accumulation-strategy-matrix",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "profile_adaptive_accumulator_wallets",
            39,
            "Profiler les wallets accumulateurs",
            "Ajoute fresh-wallet, funding source, buy/sell history et flags de risque autour des wallets entrés avant breakout.",
            "GET",
            "/api/onchain/rpc/adaptive-accumulator-wallet-profiles",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "scan_adaptive_accumulator_clusters",
            39,
            "Scanner les clusters d'accumulateurs",
            "Regroupe les wallets par funder partagé, burst de fresh wallets et ventes post-event pour repérer des comportements coordonnés.",
            "GET",
            "/api/onchain/rpc/adaptive-accumulator-cluster-scan",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "scan_adaptive_accumulator_funders",
            39,
            "Analyser les funders des clusters",
            "Classe les funders partagés pour distinguer hub CEX probable, entité connue ou funder inconnu à explorer.",
            "GET",
            "/api/onchain/rpc/adaptive-accumulator-funder-graph-scan",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "build_adaptive_manipulation_case_file",
            39,
            "Assembler un dossier manipulation lisible",
            "Regroupe timing, backtest, wallets, clusters et funders en un dossier recherche sans exécution client.",
            "GET",
            "/api/onchain/rpc/adaptive-manipulation-case-file",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "plan_exact_swap_ingestion",
            40,
            "Planifier l’ingestion de swaps exacts",
            "Choisit les chains à enrichir sans écrire de données; les receipts capturent aussi les Transfer logs ERC20/BEP20.",
            "GET",
            "/api/onchain/rpc/exact-swap-ingestion-plan",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "run_bounded_exact_swap_ingestion",
            50,
            "Ingestion bornée de swaps et transferts token",
            "Augmente l’historique token_in/token_out et Transfer logs indispensable aux signaux manipulation.",
            "POST",
            "/api/onchain/ingest/exact-swap-progressive",
            True,
            None,
            None,
            "CORE_AUTO_EXACT_SWAP_INGEST_ENABLED optional for background mode",
        ))
    if unknown_venue_swaps or router_source_missing_label_sources or router_proof_insufficient_identity:
        maturity_action_plan.append(action(
            "inspect_swap_venue_resolution_candidates",
            55,
            "Lister les candidats de résolution venue/router",
            "Prépare l'attribution DEX sans écrire de mapping.",
            "GET",
            "/api/onchain/rpc/swap-venue-resolution-candidates",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "inspect_unknown_router_source_gaps",
            60,
            "Inspecter les routers/venues inconnus",
            "Montre les routers qui bloquent l’attribution DEX fiable.",
            "GET",
            "/api/onchain/rpc/unknown-router-source-gap-report",
            False,
            None,
            None,
        ))
        maturity_action_plan.append(action(
            "prepare_source_backed_mapping_review_queue",
            70,
            "Préparer la review admin venue/router",
            "Centralise les mappings source-backed prêts ou bloqués avant confirmation.",
            "GET",
            "/api/onchain/rpc/source-backed-venue-mapping/admin-review-queue",
            True,
            None,
            None,
            "CORE_AUTO_MAPPING_REVIEW_QUEUE_ENABLED optional for background mode",
        ))
    if venue_mapping_drafts or counterparty_router_context_rows:
        maturity_action_plan.append(action(
            "corroborate_venue_official_sources",
            80,
            "Corroborer les venues via sources officielles",
            "Évite de mapper un router sur une venue à partir d’un simple indice technique.",
            "GET",
            "/api/onchain/rpc/swap-venue-official-source-corroboration",
            False,
            None,
            None,
        ))
    maturity_action_plan = sorted(
        {item["id"]: item for item in maturity_action_plan}.values(),
        key=lambda item: int(item.get("priority") or 999),
    )
    action_by_id = {str(item.get("id")): item for item in maturity_action_plan}
    next_safe_actions: list[dict[str, Any]] = []
    seen_action_ids: set[str] = set()
    for requirement in failed_requirements:
        action_id = str(requirement.get("recommended_action_id") or "")
        action_row = action_by_id.get(action_id)
        if not action_row or action_id in seen_action_ids:
            continue
        seen_action_ids.add(action_id)
        client_visible = (
            action_row.get("method") == "GET"
            and action_row.get("admin_required") is False
        )
        next_safe_actions.append({
            "requirement_id": requirement.get("id"),
            "requirement_label_fr": requirement.get("label_fr"),
            "gap": requirement.get("missing", requirement.get("excess", 0)),
            "gap_unit": requirement.get("unit"),
            "action_id": action_row.get("id"),
            "priority": action_row.get("priority"),
            "title_fr": action_row.get("title_fr"),
            "reason": action_row.get("reason"),
            "method": action_row.get("method"),
            "endpoint": action_row.get("endpoint"),
            "admin_required": action_row.get("admin_required"),
            "dry_run": action_row.get("dry_run"),
            "source_policy": action_row.get("source_policy"),
            "execution_enabled": False,
            "client_safe": False,
            "client_visible": client_visible,
            "write_guarded": not client_visible,
            "action": action_row,
        })
    readiness_contract["next_safe_actions"] = next_safe_actions
    readiness_contract["client_visible_actions"] = [
        item for item in next_safe_actions
        if item.get("action", {}).get("method") == "GET"
        and not item.get("action", {}).get("admin_required")
    ][:4]
    data_gap_meta = {
        "strict_label_coverage": {
            "severity": "critical",
            "category": "identity",
            "data_source": "label_ledger.labels + label_candidate_evidence",
            "why_it_matters_fr": "Sans labels strictement sources, un wallet peut etre attribue a la mauvaise entite.",
        },
        "wallet_label_sources": {
            "severity": "high",
            "category": "identity",
            "data_source": "wallet_chain_state.label_sources_json",
            "why_it_matters_fr": "Les wallets enrichis doivent garder la preuve de leur label pour eviter les faux positifs.",
        },
        "wallet_source_traceability": {
            "severity": "high",
            "category": "rpc_traceability",
            "data_source": "wallet_chain_state.source_attribution_json",
            "why_it_matters_fr": "Chaque snapshot RPC doit dire d'ou il vient avant de servir a une decision client.",
        },
        "swap_rows": {
            "severity": "critical",
            "category": "market_flow",
            "data_source": "swaps",
            "why_it_matters_fr": "Il faut assez de swaps pour separer manipulation probable et bruit normal du marche.",
        },
        "exact_swap_rows": {
            "severity": "critical",
            "category": "market_flow",
            "data_source": "swaps.token_in/token_out",
            "why_it_matters_fr": "Sans direction token exacte, on ne sait pas si le wallet accumule ou distribue vraiment.",
        },
        "token_transfer_rows": {
            "severity": "critical",
            "category": "market_flow",
            "data_source": "token_transfers",
            "why_it_matters_fr": "Sans Transfer logs ERC20/BEP20, on ne peut pas confirmer les depots token vers CEX ni les mouvements holder.",
        },
        "swap_history_days": {
            "severity": "critical",
            "category": "history",
            "data_source": "swaps.timestamp",
            "why_it_matters_fr": "Une fenetre trop courte cree des backtests trompeurs et surestime les signaux.",
        },
        "distinct_swap_tokens": {
            "severity": "high",
            "category": "coverage",
            "data_source": "swaps.token_in/token_out",
            "why_it_matters_fr": "La detection doit couvrir plusieurs tokens, pas seulement quelques cas faciles.",
        },
        "strict_review_candidates": {
            "severity": "medium",
            "category": "evidence_review",
            "data_source": "label_candidate_evidence",
            "why_it_matters_fr": "Il faut assez de candidats verifiables pour transformer la collecte en labels fiables.",
        },
        "unknown_venue_swaps": {
            "severity": "critical",
            "category": "venue_attribution",
            "data_source": "swaps.venue + source_backed_venue_mappings",
            "why_it_matters_fr": "Un swap sans venue/router fiable peut confondre DEX, router technique ou flux suspect.",
        },
    }
    action_by_requirement = {
        str(item.get("requirement_id")): item for item in next_safe_actions
    }
    automation_data_gaps: list[dict[str, Any]] = []
    for requirement in failed_requirements:
        req_id = str(requirement.get("id") or "")
        meta = data_gap_meta.get(req_id, {})
        action_item = action_by_requirement.get(req_id)
        automation_data_gaps.append({
            "id": req_id,
            "label_fr": requirement.get("label_fr"),
            "category": meta.get("category", "unknown"),
            "severity": meta.get("severity", "medium"),
            "current": requirement.get("current"),
            "target": requirement.get("target"),
            "gap": requirement.get("missing", requirement.get("excess", 0)),
            "unit": requirement.get("unit"),
            "direction": requirement.get("direction"),
            "data_source": meta.get("data_source", "local_onchain_db"),
            "why_it_matters_fr": meta.get("why_it_matters_fr", "Ce manque bloque une automatisation client fiable."),
            "next_action_id": requirement.get("recommended_action_id"),
            "next_action": action_item,
            "client_automation_blocker": True,
        })
    readiness_contract["automation_data_gaps"] = automation_data_gaps
    readiness_contract["missing_data_summary"] = {
        "total_gaps": len(automation_data_gaps),
        "critical_gaps": sum(1 for item in automation_data_gaps if item.get("severity") == "critical"),
        "high_gaps": sum(1 for item in automation_data_gaps if item.get("severity") == "high"),
        "medium_gaps": sum(1 for item in automation_data_gaps if item.get("severity") == "medium"),
        "top_categories": sorted({str(item.get("category")) for item in automation_data_gaps}),
        "client_automation_ready": not automation_data_gaps,
    }
    phase_meta = {
        "identity": {
            "order": 1,
            "phase": "identity_foundation",
            "title_fr": "Verifier les identites et labels sources",
        },
        "evidence_review": {
            "order": 2,
            "phase": "evidence_review",
            "title_fr": "Transformer les candidats en preuves reviewables",
        },
        "rpc_traceability": {
            "order": 3,
            "phase": "rpc_traceability",
            "title_fr": "Rendre chaque wallet RPC tracable",
        },
        "market_flow": {
            "order": 4,
            "phase": "exact_market_flow",
            "title_fr": "Construire les swaps exacts token_in/token_out",
        },
        "history": {
            "order": 5,
            "phase": "history_depth",
            "title_fr": "Allonger la fenetre historique",
        },
        "coverage": {
            "order": 6,
            "phase": "token_surface",
            "title_fr": "Elargir la surface multi-token",
        },
        "venue_attribution": {
            "order": 7,
            "phase": "venue_router_attribution",
            "title_fr": "Attribuer venues et routers avec sources",
        },
    }
    severity_order = {"critical": 0, "high": 1, "medium": 2}
    closure_steps: list[dict[str, Any]] = []
    for gap in sorted(
        automation_data_gaps,
        key=lambda item: (
            int(phase_meta.get(str(item.get("category")), {}).get("order", 99)),
            severity_order.get(str(item.get("severity")), 9),
            str(item.get("id")),
        ),
    ):
        category = str(gap.get("category") or "unknown")
        phase = phase_meta.get(category, {
            "order": 99,
            "phase": category,
            "title_fr": "Verifier le gap data",
        })
        action_item = gap.get("next_action") or {}
        closure_steps.append({
            "phase": phase.get("phase"),
            "phase_order": phase.get("order"),
            "phase_title_fr": phase.get("title_fr"),
            "gap_id": gap.get("id"),
            "gap_label_fr": gap.get("label_fr"),
            "severity": gap.get("severity"),
            "category": category,
            "gap": gap.get("gap"),
            "unit": gap.get("unit"),
            "data_source": gap.get("data_source"),
            "why_it_matters_fr": gap.get("why_it_matters_fr"),
            "action_id": gap.get("next_action_id"),
            "method": action_item.get("method"),
            "endpoint": action_item.get("endpoint"),
            "admin_required": bool(action_item.get("admin_required")),
            "dry_run": bool(action_item.get("dry_run")),
            "client_visible": bool(action_item.get("client_visible")),
            "execution_enabled": False,
            "client_safe": False,
            "status": "blocked_until_gap_closed",
        })
    readiness_contract["gap_closure_plan"] = {
        "mode": "admin_data_improvement_only",
        "client_execution_enabled": False,
        "copy_trading_enabled": False,
        "profit_guarantee_allowed": False,
        "steps": closure_steps,
        "next_step": closure_steps[0] if closure_steps else None,
        "source_policy": (
            "ordered from readiness gaps; read-only diagnostics are client-visible, "
            "mutations remain admin-gated and execution stays disabled"
        ),
    }
    first_client_action = (
        readiness_contract["client_visible_actions"][0]
        if readiness_contract["client_visible_actions"]
        else None
    )
    first_admin_action = next_safe_actions[0] if next_safe_actions else None
    readiness_contract["automation_decision"] = {
        "status": "blocked_for_clients" if failed_requirements else "watchlist_research_only",
        "client_mode": "read_only_research",
        "admin_mode": "data_improvement_only",
        "client_can_see": [
            "readiness_score",
            "historical_simulation_outputs",
            "read_only_diagnostics",
        ],
        "client_cannot_do": [
            "copy_trade_execution",
            "profit_guarantee",
            "admin_data_mutations",
        ],
        "first_client_diagnostic": first_client_action,
        "first_admin_action": first_admin_action,
        "required_before_client_automation": [
            item.get("label_fr") for item in failed_requirements[:5]
        ],
        "plain_summary_fr": (
            "Mode client: lecture seule. Les actions proposees servent a ameliorer la data, pas a executer un trade."
            if failed_requirements
            else "Mode watchlist recherche uniquement: les seuils minimaux sont passes, mais l'execution client reste coupee."
        ),
    }
    manipulation_research_verdict = _build_manipulation_research_verdict({
        "token_transfer_rows": token_transfer_rows,
        "token_transfer_history_days": token_transfer_history_days,
        "cex_token_deposit_rows": cex_token_deposit_rows,
        "cex_token_deposit_targets": cex_token_target_wallets,
        "cex_token_source_backed_targets": cex_token_source_backed_targets,
        "cex_token_fresh_like_depositors": cex_token_fresh_like_depositors,
        "cex_token_shared_funders": cex_token_shared_funders,
        "cex_token_shared_unknown_funders": cex_token_shared_unknown_funders,
        "cex_token_max_deposits_6h": cex_token_max_deposits_6h,
        "cex_token_max_deposits_24h": cex_token_max_deposits_24h,
        "cex_token_swap_rows_around_deposits": cex_token_swap_rows_around_deposits,
        "cex_token_swap_rows_after_24h": cex_token_swap_rows_after_24h,
        "cex_token_price_proxy_before_after_tokens": cex_token_price_proxy_before_after_tokens,
        "cex_token_price_proxy_max_change_pct": cex_token_price_proxy_max_change_pct,
        "cex_token_holder_supply_snapshot_tokens": cex_token_holder_supply_snapshot_tokens,
        "cex_token_holder_flow_high_cex_share_tokens": cex_token_holder_flow_high_cex_share_tokens,
        "cex_token_holder_flow_high_fresh_like_share_tokens": cex_token_holder_flow_high_fresh_like_share_tokens,
        "cex_token_holder_flow_high_top_holder_concentration_tokens": cex_token_holder_flow_high_top_holder_concentration_tokens,
        "cex_token_holder_flow_high_supply_share_tokens": cex_token_holder_flow_high_supply_share_tokens,
        "cex_token_holder_flow_max_supply_share_pct": cex_token_holder_flow_max_supply_share_pct,
        "cex_token_coordination_score": cex_token_coordination_score,
    })
    holder_flow_evidence_verdict = _build_holder_flow_evidence_verdict({
        "cex_token_holder_flow_tokens": cex_token_holder_flow_tokens,
        "cex_token_holder_supply_snapshot_tokens": cex_token_holder_supply_snapshot_tokens,
        "cex_token_holder_flow_max_cex_share_pct": cex_token_holder_flow_max_cex_share_pct,
        "cex_token_holder_flow_max_fresh_like_share_pct": cex_token_holder_flow_max_fresh_like_share_pct,
        "cex_token_holder_flow_max_top_holder_share_pct": cex_token_holder_flow_max_top_holder_share_pct,
        "cex_token_holder_flow_max_top10_holder_share_pct": cex_token_holder_flow_max_top10_holder_share_pct,
        "cex_token_holder_flow_max_supply_share_pct": cex_token_holder_flow_max_supply_share_pct,
    })
    readiness_contract["manipulation_research_verdict"] = manipulation_research_verdict
    readiness_contract["evidence_verdicts"] = {
        "cex_token_holder_flow": holder_flow_evidence_verdict,
    }

    return {
        "ok": True,
        "entity": entity,
        "chain": requested_chain or chain,
        "status": status,
        "signal_readiness_score": signal_score,
        "manipulation_research_verdict": manipulation_research_verdict,
        "evidence_verdicts": readiness_contract["evidence_verdicts"],
        "client_maturity": client_maturity,
        "readiness_contract": readiness_contract,
        "maturity_action_plan": maturity_action_plan,
        "execution_enabled": False,
        "client_profit_claim_allowed": False,
        "safe_for": [
            "data_quality_dashboard",
            "manual_research",
            "watch_only_labelling",
        ],
        "not_safe_for": [
            "client_trade_execution",
            "profit_guarantee",
            "automated_manipulation_alerts",
        ],
        "summary": {
            "strict_label_pct": strict_label_pct,
            "rpc_coverage_pct": rpc_coverage_pct,
            "wallet_traceability_pct": traceability_pct,
            "wallet_label_source_pct": label_source_pct,
            "wallet_rows": wallet_rows,
            "token_balance_wallets": token_balance_wallets,
            "active_wallet_rows": active_wallet_rows,
            "chains_observed": chains_observed,
            "swap_count": swap_count,
            "swap_wallets": swap_wallets,
            "distinct_swap_tokens": distinct_swap_tokens,
            "exact_swap_token_rows": exact_swap_token_rows,
            "legacy_inferred_swap_token_rows": inferred_swap_token_rows,
            "swap_history_days": history_days,
            "token_transfer_rows": token_transfer_rows,
            "token_transfer_history_days": token_transfer_history_days,
            "cex_token_deposit_rows": cex_token_deposit_rows,
            "cex_token_deposit_targets": cex_token_target_wallets,
            "cex_token_source_backed_targets": cex_token_source_backed_targets,
            "cex_token_source_backed_depositors": cex_token_source_backed_depositors,
            "cex_token_fresh_like_depositors": cex_token_fresh_like_depositors,
            "cex_token_missing_state_depositors": cex_token_missing_state_depositors,
            "cex_token_funding_edges": cex_token_funding_edges,
            "cex_token_fresh_like_with_funding": cex_token_fresh_like_with_funding,
            "cex_token_fresh_like_without_funding": cex_token_fresh_like_without_funding,
            "cex_token_unknown_funders": cex_token_unknown_funders,
            "cex_token_exchange_like_funders": cex_token_exchange_like_funders,
            "cex_token_shared_funders": cex_token_shared_funders,
            "cex_token_shared_unknown_funders": cex_token_shared_unknown_funders,
            "cex_token_shared_exchange_like_funders": cex_token_shared_exchange_like_funders,
            "cex_token_coordination_score": cex_token_coordination_score,
            "cex_token_coordination_tier": cex_token_coordination_tier,
            "cex_token_max_deposits_1h": cex_token_max_deposits_1h,
            "cex_token_max_deposits_6h": cex_token_max_deposits_6h,
            "cex_token_max_deposits_24h": cex_token_max_deposits_24h,
            "cex_token_deposit_span_minutes": cex_token_deposit_span_minutes,
            "cex_token_swap_rows_around_deposits": cex_token_swap_rows_around_deposits,
            "cex_token_swap_rows_after_24h": cex_token_swap_rows_after_24h,
            "cex_token_swap_tokens_without_local_swaps": cex_token_swap_tokens_without_local_swaps,
            "cex_token_price_proxy_tokens": cex_token_price_proxy_tokens,
            "cex_token_price_proxy_before_after_tokens": cex_token_price_proxy_before_after_tokens,
            "cex_token_price_proxy_max_change_pct": cex_token_price_proxy_max_change_pct,
            "cex_token_holder_flow_tokens": cex_token_holder_flow_tokens,
            "cex_token_holder_flow_high_cex_share_tokens": cex_token_holder_flow_high_cex_share_tokens,
            "cex_token_holder_flow_high_fresh_like_share_tokens": cex_token_holder_flow_high_fresh_like_share_tokens,
            "cex_token_holder_flow_high_top_holder_concentration_tokens": cex_token_holder_flow_high_top_holder_concentration_tokens,
            "cex_token_holder_flow_high_supply_share_tokens": cex_token_holder_flow_high_supply_share_tokens,
            "cex_token_holder_flow_max_cex_share_pct": cex_token_holder_flow_max_cex_share_pct,
            "cex_token_holder_flow_max_top3_depositor_share_pct": cex_token_holder_flow_max_top3_depositor_share_pct,
            "cex_token_holder_flow_max_fresh_like_share_pct": cex_token_holder_flow_max_fresh_like_share_pct,
            "cex_token_holder_flow_max_top_holder_share_pct": cex_token_holder_flow_max_top_holder_share_pct,
            "cex_token_holder_flow_max_top10_holder_share_pct": cex_token_holder_flow_max_top10_holder_share_pct,
            "cex_token_holder_flow_max_supply_share_pct": cex_token_holder_flow_max_supply_share_pct,
            "cex_token_holder_supply_snapshot_tokens": cex_token_holder_supply_snapshot_tokens,
            "first_swap_timestamp": first_swap_ts or None,
            "last_swap_timestamp": last_swap_ts or None,
            "strict_review_candidates": len(strict_review_candidates),
            "collect_more_evidence_candidates": len(collect_more_evidence),
            "unknown_venue_swaps": unknown_venue_swaps,
            "venue_mapping_drafts": venue_mapping_drafts,
            "venue_skipped_drafts": venue_skipped_drafts,
            "venue_admin_review_ready": venue_admin_review_ready,
            "counterparty_router_source_search_rows": counterparty_router_source_rows,
            "counterparty_router_context_rows": counterparty_router_context_rows,
            "counterparty_router_exact_sources": counterparty_router_exact_sources,
            "counterparty_router_admin_review_ready": counterparty_router_admin_ready,
            "unknown_router_source_unknown_routers": router_source_unknown_routers,
            "unknown_router_source_missing_state": router_source_missing_state,
            "unknown_router_source_missing_label_sources": router_source_missing_label_sources,
            "unknown_router_source_with_label_sources": router_source_with_label_sources,
            "unknown_router_proof_dossiers": router_proof_dossiers,
            "unknown_router_proof_research_ready": router_proof_research_ready,
            "unknown_router_proof_official_review_possible": router_proof_official_review_possible,
            "unknown_router_proof_insufficient_identity": router_proof_insufficient_identity,
            "unknown_router_proof_conflicts": router_proof_conflicts,
            "unknown_router_creator_identity_rows": router_creator_identity_rows,
            "unknown_router_creator_groups": router_creator_groups,
            "unknown_router_creator_address_only_rows": router_creator_address_only_rows,
            "unknown_router_creator_candidate_venue_hints": router_creator_candidate_venue_hints,
            "unknown_router_creator_identity_probe_required": router_creator_probe_required,
            "unknown_router_contracts": unknown_router_contracts,
            "unknown_router_repeated_code_groups": unknown_router_repeated_code_groups,
        },
        "blockers": blockers,
        "next_actions": next_actions,
        "risk_surface_sample": risk_rows,
        "evidence_lanes": {
            "token_transfer_coverage": {
                "summary": (readiness.get("token_transfer_coverage", {}) or {}).get("summary", {}),
                "by_chain": [
                    {
                        "chain": row.get("chain"),
                        "token_transfer_rows": row.get("token_transfer_rows"),
                        "distinct_tokens": row.get("distinct_tokens"),
                        "from_wallets": row.get("from_wallets"),
                        "to_wallets": row.get("to_wallets"),
                        "history_days": row.get("history_days"),
                    }
                    for row in (readiness.get("token_transfer_coverage", {}) or {}).get("by_chain", [])[:safe_limit]
                ],
                "blockers": (readiness.get("token_transfer_coverage", {}) or {}).get("blockers", []),
                "source_policy": (readiness.get("token_transfer_coverage", {}) or {}).get("source_policy"),
            },
            "cex_token_deposit_scan": {
                "summary": cex_token_deposit_summary,
                "aggregates": cex_token_deposits.get("aggregates", {}),
                "funding_graph": cex_token_deposits.get("funding_graph", {}),
                "temporal_profile": cex_token_deposits.get("temporal_profile", {}),
                "swap_corroboration": cex_token_deposits.get("swap_corroboration", {}),
                "price_proxy_profile": cex_token_deposits.get("price_proxy_profile", {}),
                "holder_flow_profile": cex_token_deposits.get("holder_flow_profile", {}),
                "holder_snapshot_refresh_queue": cex_token_deposits.get("holder_snapshot_refresh_queue", []),
                "rows": [
                    {
                        "chain": row.get("chain"),
                        "tx_hash": row.get("tx_hash"),
                        "timestamp": row.get("timestamp"),
                        "token": row.get("token"),
                        "token_symbol": row.get("token_symbol"),
                        "token_decimals": row.get("token_decimals"),
                        "value_raw": row.get("value_raw"),
                        "value_display": row.get("value_display"),
                        "value_display_source": row.get("value_display_source"),
                        "from_addr": row.get("from_addr"),
                        "to_addr": row.get("to_addr"),
                        "depositor_label": row.get("depositor_label"),
                        "depositor_entity": row.get("depositor_entity"),
                        "depositor_tx_count": row.get("depositor_tx_count"),
                        "depositor_has_wallet_state": row.get("depositor_has_wallet_state"),
                        "depositor_source_backed": row.get("depositor_source_backed"),
                        "depositor_known": row.get("depositor_known"),
                        "depositor_fresh_like": row.get("depositor_fresh_like"),
                        "target_entity": row.get("target_entity"),
                        "target_label": row.get("target_label"),
                        "target_source_backed": row.get("target_source_backed"),
                        "proof_status": row.get("proof_status"),
                    }
                    for row in cex_token_deposits.get("rows", [])[:safe_limit]
                ],
                "blockers": cex_token_deposits.get("blockers", []),
                "source_policy": cex_token_deposits.get("source_policy"),
            },
            "venue_mapping_drafts": [
                {
                    "candidate_id": row.get("candidate_id"),
                    "chain": row.get("chain"),
                    "router_addr": row.get("router_addr"),
                    "proposed_venue": row.get("proposed_venue"),
                    "blockers": row.get("blockers", []),
                }
                for row in readiness.get("venue_mapping_drafts", {}).get("drafts", [])[:safe_limit]
            ],
            "venue_skipped_drafts": [
                {
                    "candidate_id": row.get("candidate_id"),
                    "chain": row.get("chain"),
                    "router_addr": row.get("router_addr"),
                    "router_name_hints": row.get("router_name_hints", []),
                    "reason": row.get("reason"),
                }
                for row in readiness.get("venue_mapping_drafts", {}).get("skipped_drafts", [])[:safe_limit]
            ],
            "venue_official_review_ready": [
                {
                    "candidate_id": row.get("candidate_id"),
                    "chain": row.get("chain"),
                    "router_addr": row.get("router_addr"),
                    "proposed_venue": row.get("proposed_venue"),
                    "ready_for_admin_review": row.get("ready_for_admin_review"),
                    "blockers": row.get("blockers", []),
                }
                for row in readiness.get("venue_official_review", {}).get("rows", [])[:safe_limit]
            ],
            "counterparty_router_source_search": [
                {
                    "candidate_id": row.get("candidate_id"),
                    "chain": row.get("chain"),
                    "router_addr": row.get("router_addr"),
                    "exact_router_source_found": row.get("exact_router_source_found"),
                    "ready_for_admin_review": row.get("ready_for_admin_review"),
                    "review_status": row.get("review_status"),
                    "blockers": row.get("blockers", []),
                }
                for row in readiness.get("counterparty_router_source_search", {}).get("rows", [])[:safe_limit]
            ],
            "router_code_fingerprints": [
                {
                    "candidate_id": row.get("candidate_id"),
                    "chain": row.get("chain"),
                    "router_addr": row.get("router_addr"),
                    "code_kind": row.get("code_kind"),
                    "code_hash": row.get("code_hash"),
                    "code_size": row.get("code_size"),
                    "swap_rows": row.get("swap_rows"),
                    "mapping_policy": row.get("mapping_policy"),
                }
                for row in readiness.get("router_code_fingerprints", {}).get("rows", [])[:safe_limit]
            ],
            "router_repeated_code_groups": [
                {
                    "group_id": row.get("group_id"),
                    "chain": row.get("chain"),
                    "code_hash": row.get("code_hash"),
                    "router_count": row.get("router_count"),
                    "swap_rows": row.get("swap_rows"),
                    "routers": row.get("routers", [])[:5],
                }
                for row in readiness.get("router_code_fingerprints", {}).get("repeated_code_groups", [])[:safe_limit]
            ],
            "router_source_gaps": [
                {
                    "chain": row.get("chain"),
                    "router_addr": row.get("router_addr"),
                    "unknown_swaps": row.get("unknown_swaps"),
                    "has_state": row.get("has_state"),
                    "has_label_sources": row.get("has_label_sources"),
                    "evidence_status": row.get("evidence_status"),
                    "blocked_mutations": row.get("blocked_mutations", []),
                }
                for row in readiness.get("router_source_gaps", {}).get("rows", [])[:safe_limit]
            ],
            "router_proof_dossiers": [
                {
                    "candidate_id": row.get("candidate_id"),
                    "chain": row.get("chain"),
                    "router_addr": row.get("router_addr"),
                    "proof_status": (row.get("proof_dossier") or {}).get("proof_status"),
                    "proof_score": (row.get("proof_dossier") or {}).get("proof_score"),
                    "can_promote_or_map": (row.get("proof_dossier") or {}).get("can_promote_or_map"),
                    "next_action": row.get("next_action"),
                }
                for row in readiness.get("router_proof_dossiers", {}).get("rows", [])[:safe_limit]
            ],
            "router_creator_identity": [
                {
                    "candidate_id": row.get("candidate_id"),
                    "chain": row.get("chain"),
                    "router_addr": row.get("router_addr"),
                    "creator_address": row.get("creator_address"),
                    "identity_status": row.get("identity_status"),
                    "candidate_venue_hint": row.get("candidate_venue_hint"),
                    "next_action": row.get("next_action"),
                }
                for row in readiness.get("router_creator_identity", {}).get("rows", [])[:safe_limit]
            ],
            "strict_review_candidates": [
                {
                    "id": row.get("id"),
                    "entity": row.get("entity"),
                    "chain": row.get("chain"),
                    "address": row.get("address"),
                    "score": row.get("historical_evidence_score"),
                    "sources": row.get("unique_sources", []),
                }
                for row in strict_review_candidates[:safe_limit]
            ],
            "needs_more_evidence": [
                {
                    "id": row.get("id"),
                    "entity": row.get("entity"),
                    "chain": row.get("chain"),
                    "address": row.get("address"),
                    "score": row.get("historical_evidence_score"),
                    "decision": row.get("decision"),
                    "sources": row.get("unique_sources", []),
                }
                for row in collect_more_evidence[:safe_limit]
            ],
        },
        "source_policy": (
            "read-only manipulation readiness gate from wallet_chain_state, swaps, label evidence and data readiness; "
            "no RPC calls, labels, candidates or wallet rows are changed"
        ),
    }
