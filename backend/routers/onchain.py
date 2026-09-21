from __future__ import annotations
import hashlib
import json
import os
import time
import asyncio
import hmac
import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from services.core_equity_guards import confirm_required_detail, dry_run_raw_data_collection_payload
from services.label_expansion import expand_labels as expand_label_graph
from services.label_ledger import (
    corroborate_label_candidates,
    get_label_acquisition_plan,
    get_label_candidate_audit,
    get_label_candidate_evidence,
    get_label_candidate_evidence_scores,
    get_label_candidate_quality_report,
    get_label_candidate_review_dashboard,
    get_label_candidates,
    get_label_corroboration_queue,
    get_label_ledger_summary,
    get_verified_label_candidate_review_queue,
    plan_label_candidate_automation,
    preview_label_candidate_promotion_impact,
    promote_label_candidates,
    review_label_candidate_promotions,
    review_strict_label_candidate_promotions,
)
from services.onchain_engine import (
    acquire_label_sources_job,
    consolidate_label_candidate_duplicates_job,
    corroborate_label_candidates_job,
    enrich_labeled_wallets_rpc,
    enrich_priority_entities_rpc,
    enrich_priority_entity_chain_gaps_rpc,
    build_label_ledger_job,
    get_auto_enrich_status,
    get_data_jobs,
    get_manipulation_detection_readiness,
    get_onchain_data_readiness,
    get_exact_swap_ingestion_plan,
    get_swap_identity_readiness,
    get_token_transfer_coverage,
    get_token_transfer_cex_deposit_scan,
    get_cex_label_coverage_audit,
    get_cex_label_acquisition_plan,
    get_cex_label_promotion_review,
    get_cex_label_promotion_write_preview,
    get_cex_label_promotion_admin_queue,
    get_cex_label_promotion_stage,
    get_cex_label_promotion_backup,
    get_cex_label_promotion_backups,
    get_cex_label_promotion_final_check,
    get_cex_label_promotion_execution_envelope,
    get_cex_label_promotion_simulation_report,
    get_cex_label_promotion_dashboard,
    get_cex_label_promotion_blocker_audit,
    get_cex_label_source_quality_plan,
    get_cex_label_independent_source_queue,
    get_cex_label_independent_evidence_dry_run,
    get_cex_label_independent_evidence_persist_preview,
    get_cex_label_independent_evidence_persist_contract,
    insert_cex_label_independent_evidence,
    get_cex_label_independent_evidence_review_queue,
    get_cex_label_confidence_upgrade_preview,
    get_cex_label_confidence_upgrade_stage,
    get_cex_label_confidence_upgrade_backup_preview,
    get_cex_label_confidence_upgrade_backup,
    get_cex_label_confidence_upgrade_backups,
    get_cex_label_confidence_upgrade_final_check,
    get_cex_label_confidence_upgrade_execution_envelope,
    get_cex_label_confidence_upgrade_simulation_report,
    get_cex_label_confidence_upgrade_policy_gate,
    get_cex_label_confidence_upgrade_apply,
    get_cex_label_confidence_upgrade_prewrite_audit,
    get_cex_label_confidence_upgrade_controlled_write_review,
    get_cex_label_confidence_upgrade_sql_plan,
    get_cex_label_confidence_upgrade_rollback_smoke,
    get_cex_independent_evidence_queue_schema_plan,
    create_cex_independent_evidence_queue,
    get_cex_deposit_holder_snapshot_refresh_queue,
    refresh_cex_deposit_holder_snapshots,
    get_pre_pump_accumulation_scan,
    get_adaptive_accumulation_breakout_scan,
    get_adaptive_accumulation_backtest,
    get_adaptive_accumulation_strategy_matrix,
    get_adaptive_accumulator_wallet_profiles,
    get_adaptive_accumulator_cluster_scan,
    get_adaptive_accumulator_funder_graph_scan,
    get_adaptive_manipulation_case_file,
    create_manipulation_detection_cex_listing_ground_truth_dataset,
    get_manipulation_detection_cex_listing_exploratory_shadow_backtest_preview,
    get_manipulation_detection_cex_listing_feature_wiring_diagnostic_preview,
    get_manipulation_detection_cex_listing_negative_cohort_discovery_preview,
    get_manipulation_detection_cex_listing_ground_truth_dataset_plan_preview,
    get_manipulation_detection_cex_listing_probability_bridge_preview,
    get_manipulation_detection_cex_listing_ground_truth_seed_coherence_checkpoint,
    get_manipulation_detection_b_seed_bounded_raw_context_lookup_dry_run,
    get_manipulation_detection_documented_scam_negative_candidate_scope_expansion_preview,
    get_manipulation_detection_external_scam_negative_intake_preview,
    get_manipulation_detection_b_feature_backfill_replay_diagnostic_preview,
    get_manipulation_detection_b_cex_destination_wallet_reference_repair_preview,
    get_manipulation_detection_b_destination_holder_distribution_flow_check_preview,
    get_manipulation_detection_feature_backfill_orchestrator_preview,
    get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan,
    get_manipulation_detection_local_native_ground_truth_labeling_lookup_preview,
    get_manipulation_detection_local_native_ground_truth_discovery_preview,
    get_manipulation_detection_native_positive_candidate_replacement_discovery_preview,
    insert_manipulation_detection_b_seed_raw_context_evidence,
    insert_manipulation_detection_cex_listing_ground_truth_rows,
    get_manipulation_detection_behavioral_score_pump_backtest_preview,
    get_manipulation_detection_behavioral_evidence_bridge,
    get_manipulation_detection_honeypot_correlation_scan_preview,
    get_manipulation_detection_quiet_pool_scanner_plan_preview,
    get_manipulation_detection_stealth_accumulation_anomaly_scan_preview,
    get_manipulation_detection_stealth_funnel_diagnostic_preview,
    get_manipulation_detection_top_expansion_directional_intent_classifier_preview,
    get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview,
    get_manipulation_detection_top_expansion_behavioral_shadow_outcome_backtest_plan,
    get_manipulation_detection_top_expansion_behavioral_t0_shift_experiment_preview,
    get_manipulation_detection_top_expansion_behavioral_tradability_filter_preview,
    get_unknown_swap_attribution_audit,
    get_dex_router_source_map,
    get_dex_router_official_source_queue,
    get_dex_router_official_evidence_dry_run,
    get_dex_router_official_evidence_persist_preview,
    get_dex_router_official_evidence_queue_schema_plan,
    create_dex_router_official_evidence_queue,
    insert_dex_router_official_evidence,
    get_dex_router_official_evidence_review_queue,
    get_dex_router_venue_mapping_preview,
    get_dex_router_venue_mapping_final_check,
    get_dex_router_venue_mapping_execution_envelope,
    get_dex_router_venue_mapping_simulation_report,
    get_dex_router_venue_mapping_policy_gate,
    get_dex_router_venue_mapping_apply,
    get_dex_router_venue_mapping_prewrite_audit,
    get_dex_router_venue_mapping_controlled_write_review,
    get_dex_router_venue_mapping_sql_plan,
    get_dex_router_venue_mapping_final_safety_review,
    get_dex_router_venue_mapping_apply_confirmed_design,
    get_dex_router_venue_mapping_real_write_go_nogo,
    get_dex_router_venue_mapping_write_skeleton,
    get_dex_router_venue_mapping_transactional_write_design,
    get_dex_router_venue_mapping_transactional_write_report,
    get_dex_router_venue_mapping_confirmed_write_blueprint,
    get_dex_router_venue_mapping_multi_router_validation_scan,
    get_dex_router_venue_mapping_additional_router_evidence_plan,
    get_lab_venue_coverage_source_plan,
    get_token_venue_coverage_source_plan,
    get_token_manipulation_data_usability_audit,
    get_manipulation_detection_reliability_engine,
    get_manipulation_detection_source_backed_scoring_design,
    get_manipulation_detection_source_backed_shadow_backtest_plan,
    get_manipulation_detection_source_backed_shadow_backtest_outcome_dataset_schema_plan,
    get_manipulation_detection_source_backed_outcome_window_data_collection_dry_run,
    get_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context_dry_run,
    get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan,
    get_manipulation_detection_source_backed_outcome_sync_mint_burn_topic_binding_checkpoint,
    run_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run,
    get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan,
    insert_manipulation_detection_source_backed_outcome_sync_liquidity_evidence,
    get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review_queue,
    get_manipulation_detection_source_backed_outcome_quality_repair_preview,
    get_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan,
    create_manipulation_detection_source_backed_repaired_outcome_dataset_table,
    insert_manipulation_detection_source_backed_repaired_outcome_dataset,
    get_manipulation_detection_source_backed_repaired_outcome_dataset_review_queue,
    get_manipulation_detection_source_backed_shadow_backtest_preview,
    get_manipulation_detection_source_backed_shadow_replay_controls_preview,
    get_manipulation_detection_source_backed_control_outcome_collection_plan,
    run_manipulation_detection_source_backed_control_outcome_lookup_dry_run,
    get_manipulation_detection_source_backed_control_outcome_schema_plan,
    create_manipulation_detection_source_backed_control_outcome_table,
    insert_manipulation_detection_source_backed_control_outcome_windows,
    get_manipulation_detection_source_backed_control_outcome_review_queue,
    get_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview,
    get_manipulation_detection_source_backed_replay_policy_thresholds,
    get_manipulation_detection_source_backed_case_control_expansion_plan,
    get_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan,
    run_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run,
    get_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan,
    insert_manipulation_detection_source_backed_top_expansion_raw_context_evidence,
    get_manipulation_detection_exact_swap_collection_plan,
    get_manipulation_detection_second_window_raw_swap_evidence_schema_plan,
    get_manipulation_detection_exact_swap_second_window_plan,
    get_manipulation_detection_raw_swap_repeatability_review,
    get_manipulation_detection_transfer_context_collection_plan,
    get_manipulation_detection_transfer_context_evidence_schema_plan,
    create_manipulation_detection_transfer_context_evidence_table,
    get_manipulation_detection_transfer_context_evidence_review_queue,
    get_manipulation_detection_transfer_context_reliability_bridge_apply_contract,
    get_manipulation_detection_transfer_context_reliability_bridge_preview,
    insert_manipulation_detection_transfer_context_evidence,
    insert_manipulation_detection_second_window_raw_swap_evidence,
    run_manipulation_detection_transfer_context_lookup_dry_run,
    run_manipulation_detection_exact_swap_second_window_sqd_lookup_dry_run,
    run_manipulation_detection_exact_swap_sqd_lookup_dry_run,
    get_manipulation_detection_raw_swap_evidence_persistence_schema_plan,
    insert_manipulation_detection_raw_swap_evidence,
    get_amount_usd_normalization_and_token_identity_audit,
    get_amount_usd_recompute_plan,
    get_amount_usd_quarantine_gate,
    get_dex_trades_curated_schema_plan,
    get_dex_trades_raw_log_provenance_drilldown,
    get_dex_trades_bounded_receipt_replay_plan,
    get_dex_trades_receipt_parser_preview,
    get_dex_trades_mock_receipt_parser_test,
    get_dex_trade_raw_swap_provenance_schema_plan,
    create_dex_trade_raw_swap_provenance,
    get_dex_trade_raw_swap_provenance_replay_insert_plan,
    replay_and_insert_dex_trade_raw_swap_provenance,
    get_dex_trade_raw_swap_provenance_review,
    get_dex_trades_curated_from_raw_provenance_schema_plan,
    get_dex_trades_raw_provenance_amount_decode_preview,
    create_dex_trades_curated,
    insert_dex_trades_curated_from_raw_provenance,
    get_dex_trades_curated_review,
    get_dex_trades_curated_shadow_scoring_plan,
    get_dex_trades_curated_shadow_casefile,
    get_dex_trades_curated_unknown_route_repair_plan,
    get_dex_trades_curated_source_backed_backtest_preview,
    get_dex_trades_curated_source_backed_token_ranking,
    get_dex_trades_curated_source_backed_collection_plan,
    get_dex_trades_curated_source_backed_history_collection_plan,
    run_dex_trades_curated_source_backed_history_collection,
    get_dex_trades_curated_source_backed_transfer_context_plan,
    collect_token_transfer_context_from_receipts,
    get_dex_trades_curated_expansion_collection_plan,
    replay_and_insert_dex_trades_curated_expansion_raw_provenance,
    get_dex_trades_amount_decode_metadata_repair_plan,
    repair_dex_trades_amount_decode_token_metadata,
    apply_amount_usd_stablecoin_side_recompute,
    get_token_market_discovery_input_contract,
    get_token_market_local_candidate_discovery_radar,
    get_token_market_manual_candidate_intake_contract,
    get_token_metadata_enrichment_plan,
    enrich_token_metadata_from_local_observations,
    get_token_market_local_candidate_metadata_repair_plan,
    enrich_token_metadata_for_local_candidate_repair,
    get_token_market_discovery_candidate_schema,
    get_token_market_discovery_candidates_schema_plan,
    create_token_market_discovery_candidates,
    insert_token_market_manual_candidates,
    insert_token_market_discovery_candidate,
    get_token_market_discovery_candidate_review_queue,
    get_token_market_policy_engine_shadow_evaluation,
    get_token_market_router_exclusion_shadow_scoring,
    get_token_market_local_candidate_source_repair_plan,
    get_token_market_local_candidate_source_venue_evidence,
    get_token_market_local_candidate_official_source_proof_plan,
    get_token_market_local_universe_audit,
    get_token_market_data_coverage_expansion_plan,
    get_token_market_top_research_lead_drilldown,
    get_token_market_top_research_lead_source_venue_repair_plan,
    get_token_market_top_research_lead_source_venue_proof_acquisition_plan,
    get_token_market_top_research_lead_unknown_router_identity_drilldown,
    get_token_market_top_research_lead_router_source_route_repair_plan,
    get_token_market_top_research_lead_router_role_checkpoint,
    get_token_market_top_research_lead_route_trace_sample_plan,
    get_token_market_top_research_lead_bounded_route_trace_preview,
    run_token_market_top_research_lead_bounded_route_trace_execution,
    get_token_market_top_research_lead_trace_source_repair_plan,
    run_token_market_fresh_forward_bsc_collection_trace,
    get_token_market_recent_router_pool_evidence_review,
    get_token_market_metadata_aware_fresh_lead_ranking,
    get_token_market_recent_unknown_router_source_repair_plan,
    get_token_market_top_unknown_router_source_trace_plan,
    get_token_market_top_unknown_router_bounded_history_collection_plan,
    run_token_market_top_unknown_router_bounded_history_collection,
    get_token_market_top_research_lead_bounded_history_collection_plan,
    run_token_market_top_research_lead_bounded_history_collection,
    get_autonomous_alpha_detection_fusion_policy,
    get_label_quality_repair_policy,
    get_label_source_gap_repair_preview,
    stage_label_source_gap_repair_candidates,
    get_label_source_gap_candidate_review_queue,
    get_label_source_gap_candidate_corroboration_preview,
    get_label_source_gap_source_repair_plan,
    get_label_source_gap_weak_source_repair_queue,
    run_label_source_gap_weak_source_corroboration_dry_run,
    get_label_source_gap_source_replacement_intake_preview,
    get_label_source_gap_alternative_source_discovery_radar,
    get_label_source_gap_source_url_probe_contract,
    run_label_source_gap_source_url_probe_dry_run,
    get_label_source_gap_source_proof_grading_checkpoint,
    persist_label_source_gap_source_replacement_evidence,
    get_label_source_gap_second_source_checkpoint,
    get_label_source_gap_stronger_source_plan,
    get_label_source_gap_arkham_structured_source_intake_contract,
    get_label_source_gap_arkham_structured_source_acquisition_plan,
    get_label_source_gap_arkham_structured_manual_export_intake_preview,
    get_label_source_gap_arkham_scrapling_snapshot_research_plan,
    get_arkham_methodology_mirror,
    get_local_wallet_entity_graph_reconstruction_plan,
    get_adaptive_wallet_entity_graph_collection_contract,
    get_adaptive_wallet_entity_graph_collection_preview,
    run_adaptive_wallet_entity_graph_collection,
    get_label_source_gap_source_corroboration_contract,
    run_label_source_gap_source_corroboration_dry_run,
    persist_label_source_gap_verified_candidate_evidence,
    get_label_source_gap_source_application_preview,
    get_label_source_gap_local_observation_plan,
    get_label_source_gap_local_observation_refresh_preview,
    get_label_source_gap_local_observation_collection_plan,
    get_label_source_gap_local_observation_collection_contract,
    get_label_source_gap_local_observation_collection_preview,
    get_label_source_gap_local_observation_post_collection_review_contract,
    get_label_source_gap_local_observation_apply_preview,
    apply_label_source_gap_local_observations,
    collect_label_source_gap_local_observations,
    get_token_market_discovery_candidate_evidence_intake_preview,
    get_token_market_discovery_evidence_queue_schema_plan,
    create_token_market_discovery_evidence_queue,
    insert_token_market_discovery_evidence,
    get_token_market_discovery_evidence_review_queue,
    get_token_market_discovery_evidence_human_decision_preview,
    apply_token_market_discovery_evidence_human_decision,
    get_token_market_discovery_evidence_controlled_promotion_preview,
    get_token_market_discovery_evidence_controlled_promotion_insert_contract,
    get_token_market_controlled_promotion_queue_schema_plan,
    create_token_market_controlled_promotion_queue,
    insert_token_market_controlled_promotion,
    get_token_market_controlled_promotion_queue_review,
    get_token_market_controlled_promotion_decision_preview,
    apply_token_market_controlled_promotion_decision,
    get_token_market_controlled_promotion_downstream_insert_contract,
    get_token_market_downstream_promotion_queue_schema_plan,
    create_token_market_downstream_promotion_queue,
    insert_token_market_downstream_promotion,
    get_token_market_downstream_promotion_queue_review,
    get_token_market_downstream_promotion_decision_preview,
    apply_token_market_downstream_promotion_decision,
    get_token_market_downstream_business_insert_contract,
    get_token_market_downstream_business_handoff_queue_schema_plan,
    create_token_market_downstream_business_handoff_queue,
    insert_token_market_downstream_business_handoff,
    get_token_market_downstream_business_handoff_queue_review,
    get_token_market_downstream_business_handoff_decision_preview,
    apply_token_market_downstream_business_handoff_decision,
    get_token_market_downstream_business_handoff_business_insert_contract,
    get_token_market_business_insert_queue_schema_plan,
    create_token_market_business_insert_queue,
    insert_token_market_business_insert,
    get_token_market_business_insert_queue_review,
    get_token_market_business_insert_decision_preview,
    apply_token_market_business_insert_decision,
    get_token_market_business_execution_contract,
    get_token_market_business_execution_queue_schema_plan,
    create_token_market_business_execution_queue,
    insert_token_market_business_execution,
    get_token_market_business_execution_queue_review,
    get_token_market_business_execution_decision_preview,
    apply_token_market_business_execution_decision,
    get_token_market_business_apply_contract,
    get_token_market_business_apply_queue_schema_plan,
    create_token_market_business_apply_queue,
    insert_token_market_business_apply,
    get_token_market_business_apply_queue_review,
    get_token_market_business_apply_decision_preview,
    apply_token_market_business_apply_decision,
    get_token_market_business_post_apply_contract,
    get_token_market_post_apply_queue_schema_plan,
    create_token_market_post_apply_queue,
    insert_token_market_post_apply,
    get_token_market_post_apply_queue_review,
    get_token_market_post_apply_decision_preview,
    apply_token_market_post_apply_decision,
    get_token_market_post_apply_insert_contract,
    get_token_market_post_apply_insert_queue_schema_plan,
    create_token_market_post_apply_insert_queue,
    insert_token_market_post_apply_insert,
    get_token_market_post_apply_insert_queue_review,
    get_token_market_post_apply_insert_decision_preview,
    apply_token_market_post_apply_insert_decision,
    get_token_market_post_apply_execution_contract,
    get_token_market_post_apply_execution_queue_schema_plan,
    create_token_market_post_apply_execution_queue,
    insert_token_market_post_apply_execution,
    get_token_market_post_apply_execution_queue_review,
    get_token_market_post_apply_execution_decision_preview,
    apply_token_market_post_apply_execution_decision,
    get_token_market_post_apply_execution_apply_contract,
    get_token_market_post_apply_execution_apply_queue_schema_plan,
    create_token_market_post_apply_execution_apply_queue,
    insert_token_market_post_apply_execution_apply,
    get_token_market_post_apply_execution_apply_queue_review,
    get_token_market_post_apply_execution_apply_decision_preview,
    apply_token_market_post_apply_execution_apply_decision,
    get_token_market_final_apply_contract,
    get_token_market_final_apply_queue_schema_plan,
    create_token_market_final_apply_queue,
    insert_token_market_final_apply,
    get_token_market_final_apply_queue_review,
    get_token_market_final_apply_decision_preview,
    apply_token_market_final_apply_decision,
    get_token_market_final_target_execution_contract,
    get_token_market_final_target_execution_queue_schema_plan,
    create_token_market_final_target_execution_queue,
    insert_token_market_final_target_execution,
    get_token_market_final_target_execution_queue_review,
    get_token_market_final_target_execution_decision_preview,
    apply_token_market_final_target_execution_decision,
    get_token_market_final_target_execution_handoff_contract,
    get_token_market_final_handoff_queue_schema_plan,
    create_token_market_final_handoff_queue,
    insert_token_market_final_handoff,
    get_token_market_final_handoff_queue_review,
    get_token_market_final_handoff_decision_preview,
    apply_token_market_final_handoff_decision,
    get_token_market_final_handoff_target_contract,
    get_token_market_final_handoff_target_queue_schema_plan,
    create_token_market_final_handoff_target_queue,
    insert_token_market_final_handoff_target,
    get_token_market_final_handoff_target_queue_review,
    get_token_market_final_handoff_target_decision_preview,
    apply_token_market_final_handoff_target_decision,
    get_token_market_final_handoff_target_cex_review_handoff_contract,
    get_cex_market_evidence_review_queue_schema_plan,
    create_cex_market_evidence_review_queue,
    insert_cex_market_evidence_review,
    get_cex_market_evidence_review_queue_review,
    get_cex_market_evidence_review_decision_preview,
    apply_cex_market_evidence_review_decision,
    get_cex_market_evidence_review_label_candidate_handoff_contract,
    get_cex_label_candidate_review_queue_schema_plan,
    create_cex_label_candidate_review_queue,
    insert_cex_label_candidate_review,
    get_cex_label_candidate_review_queue_review,
    get_cex_label_candidate_review_decision_preview,
    apply_cex_label_candidate_review_decision,
    get_cex_label_creation_contract,
    get_cex_label_creation_queue_schema_plan,
    create_cex_label_creation_review_queue,
    insert_cex_label_creation_review,
    get_cex_label_creation_review_queue_review,
    get_cex_label_creation_review_decision_preview,
    apply_cex_label_creation_review_decision,
    get_cex_final_label_write_contract,
    get_cex_final_label_write_queue_schema_plan,
    create_cex_final_label_write_review_queue,
    insert_cex_final_label_write_review,
    get_cex_final_label_write_review_queue_review,
    get_cex_final_label_write_decision_preview,
    apply_cex_final_label_write_decision,
    get_cex_final_label_write_execution_contract,
    get_cex_final_label_execution_queue_schema_plan,
    create_cex_final_label_execution_review_queue,
    insert_cex_final_label_execution_review,
    get_cex_final_label_execution_review_queue_review,
    get_cex_final_label_execution_decision_preview,
    apply_cex_final_label_execution_decision,
    get_cex_final_label_write_safety_checkpoint,
    get_dex_router_venue_mapping_rollback_artifact_preview,
    get_dex_router_venue_mapping_rollback_artifact_schema_plan,
    create_dex_router_venue_mapping_rollback_artifact_storage,
    create_dex_router_venue_mapping_rollback_artifact,
    refresh_dex_router_venue_mapping_rollback_artifact,
    get_dex_router_venue_mapping_rollback_artifacts,
    get_unknown_router_source_gap_report,
    get_unknown_router_official_source_worklist,
    get_unknown_router_proof_dossiers,
    get_unknown_router_official_source_acquisition_queue,
    get_unknown_router_official_source_rule_checkpoint,
    get_unknown_router_official_source_search_scan,
    get_unknown_router_creator_identity_scan,
    get_unknown_router_creator_identity_acquisition_queue,
    get_unknown_router_creator_identity_evidence_scan,
    get_unknown_router_creator_identity_source_search_scan,
    get_unknown_router_interaction_fingerprints,
    get_unknown_router_method_selector_scan,
    get_unknown_router_selector_signature_resolution_scan,
    get_unknown_router_verified_contract_source_scan,
    get_unknown_router_proxy_implementation_scan,
    get_unknown_router_internal_call_trace_scan,
    get_unknown_router_internal_transaction_fallback_scan,
    get_token_market_recent_unknown_router_internal_transaction_fallback_scan,
    get_unknown_router_internal_counterparty_research_packages,
    get_unknown_router_internal_counterparty_research_packages_official_review,
    get_unknown_router_internal_counterparty_router_source_search_scan,
    get_unknown_router_public_identity_acquisition_scan,
    get_unknown_router_evidence_package,
    get_unknown_router_role_classification_checkpoint,
    get_unknown_router_role_exclusion_plan,
    get_unknown_dex_route_provenance_workbench,
    get_unknown_dex_route_provenance_dossier,
    get_unknown_dex_intermediary_path_repair_plan,
    run_unknown_dex_intermediary_bounded_trace_collection,
    run_unknown_dex_intermediary_internal_transaction_fallback,
    get_unknown_dex_traceability_candidate_selector,
    get_unknown_dex_local_transfer_path_workbench,
    get_unknown_dex_local_path_official_source_repair_plan,
    get_unknown_dex_local_path_official_source_search_scan,
    get_unknown_dex_local_path_explorer_identity_hint_scan,
    get_unknown_dex_local_path_pool_factory_inference_checkpoint,
    get_unknown_dex_factory_official_source_proof_checkpoint,
    get_unknown_dex_deployment_registry_paircreated_proof_checkpoint,
    get_unknown_dex_paircreated_log_replay_plan,
    get_unknown_dex_paircreated_bounded_replay_dry_run,
    get_unknown_dex_paircreated_provider_indexer_capability_audit,
    get_unknown_dex_paircreated_blockscout_indexer_bounded_lookup_dry_run,
    get_unknown_dex_paircreated_sqd_portal_bounded_lookup_dry_run,
    get_unknown_dex_paircreated_evidence_persistence_schema_plan,
    create_unknown_dex_paircreated_evidence,
    insert_unknown_dex_paircreated_evidence,
    get_unknown_dex_paircreated_evidence_review_queue,
    get_unknown_dex_paircreated_evidence_decision_preview,
    apply_unknown_dex_paircreated_evidence_decision,
    get_dex_mapping_review_contract,
    get_dex_mapping_review_queue_schema_plan,
    create_dex_mapping_review_queue,
    insert_dex_mapping_review_queue,
    get_dex_local_event_reader_proof_of_shape_plan,
    get_dex_local_event_reader_checkpoint_raw_schema_plan,
    create_dex_local_event_reader_checkpoint_raw_tables,
    get_dex_local_event_reader_run_contract,
    insert_dex_local_event_reader_run,
    get_dex_local_event_reader_execution_contract,
    get_unknown_dex_paircreated_archive_indexer_alternative_strategy,
    run_dex_local_event_reader_sqd_lookup_dry_run,
    persist_dex_local_event_reader_sqd_raw_events,
    get_dex_local_event_reader_proof_package_preview,
    insert_dex_local_event_reader_proof_package,
    get_dex_local_event_reader_proof_package_review_queue,
    get_dex_local_event_reader_proof_package_decision_preview,
    apply_dex_local_event_reader_proof_package_decision,
    get_dex_local_event_reader_proof_package_evidence_review_contract,
    get_dex_local_event_reader_proof_package_corroboration_review,
    get_unknown_dex_paircreated_local_creation_block_range_plan,
    get_unknown_dex_paircreated_reduced_range_replay_dry_run,
    get_unknown_dex_pool_code_existence_creation_block_probe,
    get_unknown_dex_pool_contract_creation_proof_source_gate,
    get_unknown_dex_pool_contract_creation_explorer_archive_lookup_dry_run,
    get_unknown_dex_paircreated_forward_local_indexer_plan,
    get_unknown_dex_venue_family_review,
    get_unknown_dex_family_context_scoring_plan,
    get_unknown_dex_family_context_collection_plan,
    run_unknown_dex_family_context_history_collection,
    get_unknown_dex_family_context_post_collection_audit,
    get_unknown_dex_family_context_candidate_repair_plan,
    get_unknown_dex_family_context_casefile,
    get_unknown_dex_family_context_route_source_repeatability_plan,
    get_unknown_dex_family_context_exact_route_source_proof_acquisition_plan,
    get_unknown_dex_family_context_bounded_official_source_lookup_plan,
    get_unknown_dex_family_context_source_acquisition_strategy_decision_preview,
    get_unknown_dex_family_context_manual_source_intake_preview,
    get_unknown_dex_family_context_bounded_official_source_lookup_gate,
    get_unknown_dex_family_context_bounded_official_source_lookup,
    get_unknown_dex_family_context_source_page_fetch_grading_checkpoint,
    get_unknown_dex_family_context_stronger_official_route_source_package_plan,
    get_unknown_dex_family_context_bounded_official_route_source_package_preview,
    run_dex_local_event_reader_execution_dry_run,
    get_core_equity_agent_control_plane,
    get_core_equity_agent_task_contract_preview,
    run_core_equity_codex_agent_runner_dry_run,
    get_core_equity_codex_runner_audit_log_preview,
    write_core_equity_codex_runner_audit_log,
    get_core_equity_codex_schedule_plan,
    get_core_equity_agent_os_lite_runtime_preflight,
    get_core_equity_agent_os_lite_cycle_preview,
    get_core_equity_agent_os_lite_state_snapshot,
    get_core_equity_agent_os_lite_task_queue_view,
    get_core_equity_agent_os_lite_schedule_activation_checklist,
    run_unknown_dex_traceability_candidate_internal_probe,
    get_dex_official_router_registry,
    get_dex_official_router_registry_source_freshness,
    get_aster_dex_fund_flow_radar,
    run_aster_dex_fund_flow_collection,
    run_aster_dex_paginated_fund_flow_collection,
    get_aster_dex_flow_case_file,
    get_aster_cex_bridge_context,
    run_aster_source_wallet_token_flow_collection,
    enrich_unknown_swap_attribution_targets,
    get_swap_venue_resolution_candidates,
    get_unknown_swap_router_code_fingerprints,
    get_unknown_swap_router_family_investigation,
    get_swap_venue_public_evidence,
    scan_swap_venue_public_evidence,
    get_swap_venue_mapping_drafts,
    corroborate_swap_venue_official_sources,
    get_source_backed_venue_mapping_admin_review_queue,
    confirm_guided_venue_review,
    confirm_guided_venue_reviews_batch,
    get_source_backed_venue_mappings,
    preview_source_backed_venue_mapping,
    upsert_source_backed_venue_mapping,
    get_rpc_entity_chain_gap_verification,
    get_rpc_entity_chain_gap_report,
    get_entity_flow_surface,
    get_rpc_entity_gap_report,
    get_rpc_entity_coverage,
    get_latest_block,
    get_rpc_status,
    get_rpc_wallet_source,
    get_rpc_wallet_quality_audit,
    get_rpc_label_source_gap_report,
    get_rpc_wallet_state_audit,
    get_rpc_wallet_state,
    backfill_rpc_wallet_source_attribution,
    backfill_rpc_wallet_label_sources,
    stage_rpc_label_source_gap_candidates,
    corroborate_rpc_label_source_gap_candidates,
    backfill_rpc_label_source_gap_candidate_urls,
    refresh_rpc_wallet_state_audit_targets,
    ingest_block,
    ingest_exact_swap_window_job,
    ingest_recent_blocks,
    run_readiness_gap_auto_fill,
    run_exact_swap_ingestion_plan_once,
    run_bounded_exact_swap_transfer_collection,
    start_auto_ingest,
    start_auto_enrich_priority,
    stop_auto_enrich_priority,
)
from services.onchain.aster.scrapling_label_enrichment_batch import get_scrapling_label_enrichment_preview
from services.onchain.aster.dexscreener_enrichment_layer import get_dexscreener_enrichment_preview
from services.onchain.aster.dexscreener_first_discovery_layer import get_dexscreener_first_discovery_preview
from services.onchain.aster.aster_agent_foundation import (
    get_aster_agent_foundation_test,
    get_aster_order_book_anomaly_detection_test,
)
from services.onchain.aster.aster_agent_decision_engine import run_aster_agent_loop_test
from services.onchain.aster.aster_mcp_market_data_adapter import (
    get_aster_mcp_market_data_adapter_preview,
    get_aster_perps_reality_check_preview,
)
from services.onchain.aster.aster_demo_testnet_probe import (
    get_aster_demo_order_intent_validator_preview,
    get_aster_demo_testnet_readiness_preview,
)
from services.onchain.aster.aster_data_source_validation import (
    get_aster_data_source_validation_preview,
    write_aster_data_source_validation_snapshot,
)
from services.onchain.aster.aster_public_universe_snapshot import get_aster_public_universe_snapshot_preview
from services.onchain.aster.aster_ws_market_stream_validation import get_aster_ws_market_stream_validation_preview
from services.onchain.aster.aster_ws_forward_monitor_preview import get_aster_ws_forward_monitor_preview
from services.onchain.aster.aster_ws_symbol_quality_report import get_aster_ws_symbol_quality_report_preview
from services.onchain.aster.research.aster_v2_ws_preflight_refresh import get_aster_v2_ws_preflight_refresh_preview
from services.onchain.aster.research.aster_v2_strict_vs_large_comparator import get_aster_v2_strict_vs_large_comparison_preview
from services.onchain.aster.research.runner_health_dashboard import get_aster_runner_health_dashboard_preview
from services.onchain.aster.aster_watchlist_priority_builder import get_aster_priority_watchlist_preview
from services.onchain.aster.aster_dual_track_research_report import get_aster_dual_track_research_report_preview
from services.onchain.aster.aster_exploitation_champions_validator import get_aster_exploitation_champions_validation_preview
from services.onchain.aster.aster_mcp_capability_audit import get_aster_mcp_capability_audit_preview
from services.onchain.aster.aster_mark_index_replay_filter import get_aster_mark_index_replay_filter_preview
from services.onchain.aster.aster_paper_trading_sandbox import (
    create_aster_paper_trading_ledger_table,
    get_aster_agent_command_center_preview,
    get_aster_api_resilience_test,
    get_aster_short_fade_universe_selection_preview,
    get_aster_volatile_universe_short_backtest_preview,
    get_aster_paper_trading_60d_kline_replay_preview,
    get_aster_paper_trading_focused_walkforward_preview,
    get_aster_paper_trading_focused_optimization_preview,
    get_aster_paper_trading_multi_timeframe_replay_preview,
    get_aster_optimized_long_forward_monitor_preview,
    get_aster_optimized_long_regime_diagnostic_preview,
    get_aster_optimized_long_stateful_monitor,
    get_aster_paper_trading_extended_backtest_preview,
    get_aster_paper_trading_final_alignment_test,
    get_aster_paper_trading_forward_monitor_preview,
    get_aster_paper_trading_forward_short_monitor_preview,
    get_aster_forward_reality_comparison_preview,
    get_aster_paper_trading_gate_calibration_preview,
    get_aster_paper_trading_hybrid_signal_test,
    get_aster_paper_trading_hybrid_signal_test_v2,
    get_aster_paper_trading_ledger_analytics,
    get_aster_paper_trading_replay_insert,
    get_aster_paper_trading_risk_recalibration_test,
    get_aster_paper_trading_run_preview,
    get_aster_paper_trading_schema_plan,
    get_aster_paper_trading_short_fade_backtest_preview,
    get_aster_paper_trading_short_extended_backtest_preview,
    get_aster_paper_trading_signal_cinematic_diagnostic,
    get_aster_paper_trading_strategy_report,
    get_aster_paper_trading_short_walkforward_preview,
    get_aster_paper_trading_short_time_stop_calibration_preview,
    get_aster_paper_trading_stateful_session_monitor,
    get_aster_paper_trading_watchlist_replay_insert,
    get_aster_selected_short_fade_forward_monitor_preview,
)
from services.onchain.behavioral_evidence_bridge import _score_raw_context_candidate as score_raw_context_candidate
from services.onchain.core.paths import DB_PATH
from services.seed_ingestion import ingest_seed_transactions
from services.wallet_analyzer import analyze_wallet_full

router = APIRouter()


def _require_data_admin(x_core_admin_token: str | None = Header(default=None)) -> None:
    token = os.getenv("CORE_ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=403, detail="CORE_ADMIN_TOKEN is not configured")
    if not hmac.compare_digest(str(x_core_admin_token or ""), token):
        raise HTTPException(status_code=403, detail="Core Equity admin token required")


def _is_sane_usd(value) -> bool:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        return False
    return 0 <= numeric < 1_000_000_000_000


def _trusted_tokens(tokens: list[dict]) -> list[dict]:
    rows = []
    for token in tokens:
        price = token.get("price_usd")
        value = token.get("value_usd")
        try:
            price_ok = not price or float(price) <= 1_000_000
        except (TypeError, ValueError):
            price_ok = False
        if price_ok and _is_sane_usd(value):
            rows.append(token)
    return rows


def _safe_chain_net_worth(chain_result: dict) -> float:
    native_value = chain_result.get("native_value_usd")
    display_value = sum(float(token.get("value_usd") or 0) for token in _trusted_tokens(chain_result.get("display_tokens") or []))
    net_worth = chain_result.get("net_worth_usd")
    if _is_sane_usd(net_worth):
        return float(net_worth or 0)
    return float(native_value or 0) + display_value


@router.get("/rpc/status")
async def rpc_status():
    return await asyncio.to_thread(get_rpc_status)


@router.get("/rpc/wallet-state")
async def rpc_wallet_state(limit: int = 100, entity: str | None = None, chain: str | None = None):
    return await asyncio.to_thread(get_rpc_wallet_state, limit, entity, chain)


@router.get("/rpc/wallet-source")
async def rpc_wallet_source(address: str, chain: str | None = None):
    return await asyncio.to_thread(get_rpc_wallet_source, address, chain)


@router.get("/rpc/wallet-quality-audit")
async def rpc_wallet_quality_audit(entity: str | None = None, chain: str | None = None, limit: int = 20):
    return await asyncio.to_thread(get_rpc_wallet_quality_audit, entity, chain, limit)


@router.get("/rpc/label-source-gaps")
async def rpc_label_source_gaps(entity: str | None = None, chain: str | None = None, limit: int = 50):
    return await asyncio.to_thread(get_rpc_label_source_gap_report, entity, chain, limit)


@router.get("/rpc/wallet-state-audit")
async def rpc_wallet_state_audit(
    entity: str | None = None,
    chain: str | None = None,
    stale_after_hours: int = 24,
    limit: int = 20,
):
    return await asyncio.to_thread(get_rpc_wallet_state_audit, entity, chain, stale_after_hours, limit)


@router.post("/rpc/backfill-wallet-source-attribution")
async def rpc_backfill_wallet_source_attribution(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 100,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit_max_500")
    return await asyncio.to_thread(
        backfill_rpc_wallet_source_attribution,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/backfill-wallet-label-sources")
async def rpc_backfill_wallet_label_sources(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 100,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit_max_500")
    return await asyncio.to_thread(
        backfill_rpc_wallet_label_sources,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/stage-label-source-gap-candidates")
async def rpc_stage_label_source_gap_candidates(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        stage_rpc_label_source_gap_candidates,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/corroborate-label-source-gap-candidates")
async def rpc_corroborate_label_source_gap_candidates(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    timeout: int = 12,
    allow_external: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if timeout > 20:
        raise HTTPException(status_code=400, detail="timeout_max_20")
    if not dry_run and confirm != "CORROBORATE_LABEL_SOURCE_GAP_CANDIDATES":
        raise HTTPException(
            status_code=400,
            detail="confirm_CORROBORATE_LABEL_SOURCE_GAP_CANDIDATES_required",
        )
    return await asyncio.to_thread(
        corroborate_rpc_label_source_gap_candidates,
        entity,
        chain,
        limit,
        dry_run,
        timeout,
        allow_external,
        confirm,
    )


@router.post("/rpc/backfill-label-source-gap-candidate-urls")
async def rpc_backfill_label_source_gap_candidate_urls(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        backfill_rpc_label_source_gap_candidate_urls,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/entity-coverage")
async def rpc_entity_coverage(entity: str | None = None, limit: int = 50, min_confidence: str = "medium"):
    return await asyncio.to_thread(get_rpc_entity_coverage, entity, limit, min_confidence)


@router.get("/rpc/entity-flow")
async def rpc_entity_flow(entity: str, limit: int = 25):
    return await asyncio.to_thread(get_entity_flow_surface, entity, limit)


@router.get("/rpc/entity-gaps")
async def rpc_entity_gaps(min_confidence: str = "medium"):
    return await asyncio.to_thread(get_rpc_entity_gap_report, min_confidence)


@router.get("/rpc/entity-chain-gaps")
async def rpc_entity_chain_gaps(min_confidence: str = "medium", limit: int = 50):
    return await asyncio.to_thread(get_rpc_entity_chain_gap_report, min_confidence, limit)


@router.get("/rpc/entity-chain-gap-verification")
async def rpc_entity_chain_gap_verification(
    min_confidence: str = "medium",
    limit: int = 50,
    stale_after_hours: int = 24,
):
    return await asyncio.to_thread(
        get_rpc_entity_chain_gap_verification,
        min_confidence,
        limit,
        stale_after_hours,
    )


@router.get("/rpc/data-readiness")
async def rpc_data_readiness(entity: str | None = None, min_confidence: str = "medium", limit: int = 12):
    return await asyncio.to_thread(get_onchain_data_readiness, entity, min_confidence, limit)


@router.get("/rpc/manipulation-readiness")
async def rpc_manipulation_readiness(entity: str | None = None, chain: str | None = None, limit: int = 12):
    return await asyncio.to_thread(get_manipulation_detection_readiness, entity, chain, limit)


@router.post("/rpc/auto-fill-gaps")
async def rpc_auto_fill_gaps(
    entity: str | None = None,
    chain: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    max_cycles: int = 3,
    max_pairs: int = 2,
    _: None = Depends(_require_data_admin),
):
    if max_cycles > 5:
        raise HTTPException(status_code=400, detail="max_cycles_max_5")
    if max_pairs > 5:
        raise HTTPException(status_code=400, detail="max_pairs_max_5")
    if not dry_run and confirm != "RUN_READYNESS_GAP_FILL":
        raise HTTPException(status_code=400, detail="confirm_RUN_READYNESS_GAP_FILL_required")
    return await asyncio.to_thread(
        run_readiness_gap_auto_fill,
        entity,
        chain,
        dry_run,
        confirm,
        max_cycles,
        max_pairs,
    )


@router.get("/rpc/pre-pump-accumulation-scan")
async def rpc_pre_pump_accumulation_scan(
    chain: str | None = None,
    token: str | None = None,
    limit: int = 10,
    pump_threshold_pct: float = 500.0,
    recent_window_hours: int = 24,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if pump_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="pump_threshold_pct_max_100000")
    if recent_window_hours > 72:
        raise HTTPException(status_code=400, detail="recent_window_hours_max_72")
    return await asyncio.to_thread(
        get_pre_pump_accumulation_scan,
        chain,
        token,
        limit,
        pump_threshold_pct,
        recent_window_hours,
    )


@router.get("/rpc/adaptive-accumulation-breakout-scan")
async def rpc_adaptive_accumulation_breakout_scan(
    chain: str | None = None,
    token: str | None = None,
    limit: int = 10,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if breakout_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="breakout_threshold_pct_max_100000")
    if baseline_swaps > 100:
        raise HTTPException(status_code=400, detail="baseline_swaps_max_100")
    if confirmation_swaps > 20:
        raise HTTPException(status_code=400, detail="confirmation_swaps_max_20")
    if pre_event_swaps > 200:
        raise HTTPException(status_code=400, detail="pre_event_swaps_max_200")
    return await asyncio.to_thread(
        get_adaptive_accumulation_breakout_scan,
        chain,
        token,
        limit,
        breakout_threshold_pct,
        baseline_swaps,
        confirmation_swaps,
        pre_event_swaps,
    )


@router.get("/rpc/adaptive-accumulation-backtest")
async def rpc_adaptive_accumulation_backtest(
    chain: str | None = None,
    token: str | None = None,
    initial_capital_usd: float = 100.0,
    limit: int = 10,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
    exit_after_swaps: int = 10,
    fee_bps: float = 100.0,
):
    if initial_capital_usd > 100_000:
        raise HTTPException(status_code=400, detail="initial_capital_usd_max_100000")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if breakout_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="breakout_threshold_pct_max_100000")
    if baseline_swaps > 100:
        raise HTTPException(status_code=400, detail="baseline_swaps_max_100")
    if confirmation_swaps > 20:
        raise HTTPException(status_code=400, detail="confirmation_swaps_max_20")
    if pre_event_swaps > 200:
        raise HTTPException(status_code=400, detail="pre_event_swaps_max_200")
    if exit_after_swaps > 100:
        raise HTTPException(status_code=400, detail="exit_after_swaps_max_100")
    if fee_bps > 1_000:
        raise HTTPException(status_code=400, detail="fee_bps_max_1000")
    return await asyncio.to_thread(
        get_adaptive_accumulation_backtest,
        chain,
        token,
        initial_capital_usd,
        limit,
        breakout_threshold_pct,
        baseline_swaps,
        confirmation_swaps,
        pre_event_swaps,
        exit_after_swaps,
        fee_bps,
    )


@router.get("/rpc/adaptive-accumulation-strategy-matrix")
async def rpc_adaptive_accumulation_strategy_matrix(
    chain: str | None = None,
    token: str | None = None,
    initial_capital_usd: float = 100.0,
    limit: int = 10,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
    exit_after_swaps_options: str = "3,10,20",
    delayed_entry_swaps: int = 3,
    fee_bps: float = 100.0,
):
    if initial_capital_usd > 100_000:
        raise HTTPException(status_code=400, detail="initial_capital_usd_max_100000")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if breakout_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="breakout_threshold_pct_max_100000")
    if baseline_swaps > 100:
        raise HTTPException(status_code=400, detail="baseline_swaps_max_100")
    if confirmation_swaps > 20:
        raise HTTPException(status_code=400, detail="confirmation_swaps_max_20")
    if pre_event_swaps > 200:
        raise HTTPException(status_code=400, detail="pre_event_swaps_max_200")
    if delayed_entry_swaps > 50:
        raise HTTPException(status_code=400, detail="delayed_entry_swaps_max_50")
    if fee_bps > 1_000:
        raise HTTPException(status_code=400, detail="fee_bps_max_1000")
    return await asyncio.to_thread(
        get_adaptive_accumulation_strategy_matrix,
        chain,
        token,
        initial_capital_usd,
        limit,
        breakout_threshold_pct,
        baseline_swaps,
        confirmation_swaps,
        pre_event_swaps,
        exit_after_swaps_options,
        delayed_entry_swaps,
        fee_bps,
    )


@router.get("/rpc/adaptive-accumulator-wallet-profiles")
async def rpc_adaptive_accumulator_wallet_profiles(
    chain: str | None = None,
    token: str | None = None,
    limit: int = 10,
    wallet_limit: int = 10,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
    fresh_wallet_hours: int = 72,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if wallet_limit > 50:
        raise HTTPException(status_code=400, detail="wallet_limit_max_50")
    if breakout_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="breakout_threshold_pct_max_100000")
    if baseline_swaps > 100:
        raise HTTPException(status_code=400, detail="baseline_swaps_max_100")
    if confirmation_swaps > 20:
        raise HTTPException(status_code=400, detail="confirmation_swaps_max_20")
    if pre_event_swaps > 200:
        raise HTTPException(status_code=400, detail="pre_event_swaps_max_200")
    if fresh_wallet_hours > 24 * 30:
        raise HTTPException(status_code=400, detail="fresh_wallet_hours_max_720")
    return await asyncio.to_thread(
        get_adaptive_accumulator_wallet_profiles,
        chain,
        token,
        limit,
        wallet_limit,
        breakout_threshold_pct,
        baseline_swaps,
        confirmation_swaps,
        pre_event_swaps,
        fresh_wallet_hours,
    )


@router.get("/rpc/adaptive-accumulator-cluster-scan")
async def rpc_adaptive_accumulator_cluster_scan(
    chain: str | None = None,
    token: str | None = None,
    limit: int = 10,
    wallet_limit: int = 10,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
    fresh_wallet_hours: int = 72,
    cluster_window_minutes: int = 60,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if wallet_limit > 50:
        raise HTTPException(status_code=400, detail="wallet_limit_max_50")
    if breakout_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="breakout_threshold_pct_max_100000")
    if baseline_swaps > 100:
        raise HTTPException(status_code=400, detail="baseline_swaps_max_100")
    if confirmation_swaps > 20:
        raise HTTPException(status_code=400, detail="confirmation_swaps_max_20")
    if pre_event_swaps > 200:
        raise HTTPException(status_code=400, detail="pre_event_swaps_max_200")
    if fresh_wallet_hours > 24 * 30:
        raise HTTPException(status_code=400, detail="fresh_wallet_hours_max_720")
    if cluster_window_minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="cluster_window_minutes_max_1440")
    return await asyncio.to_thread(
        get_adaptive_accumulator_cluster_scan,
        chain,
        token,
        limit,
        wallet_limit,
        breakout_threshold_pct,
        baseline_swaps,
        confirmation_swaps,
        pre_event_swaps,
        fresh_wallet_hours,
        cluster_window_minutes,
    )


@router.get("/rpc/adaptive-accumulator-funder-graph-scan")
async def rpc_adaptive_accumulator_funder_graph_scan(
    chain: str | None = None,
    token: str | None = None,
    limit: int = 10,
    wallet_limit: int = 10,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
    fresh_wallet_hours: int = 72,
    cluster_window_minutes: int = 60,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if wallet_limit > 50:
        raise HTTPException(status_code=400, detail="wallet_limit_max_50")
    if breakout_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="breakout_threshold_pct_max_100000")
    if baseline_swaps > 100:
        raise HTTPException(status_code=400, detail="baseline_swaps_max_100")
    if confirmation_swaps > 20:
        raise HTTPException(status_code=400, detail="confirmation_swaps_max_20")
    if pre_event_swaps > 200:
        raise HTTPException(status_code=400, detail="pre_event_swaps_max_200")
    if fresh_wallet_hours > 24 * 30:
        raise HTTPException(status_code=400, detail="fresh_wallet_hours_max_720")
    if cluster_window_minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="cluster_window_minutes_max_1440")
    return await asyncio.to_thread(
        get_adaptive_accumulator_funder_graph_scan,
        chain,
        token,
        limit,
        wallet_limit,
        breakout_threshold_pct,
        baseline_swaps,
        confirmation_swaps,
        pre_event_swaps,
        fresh_wallet_hours,
        cluster_window_minutes,
    )


@router.get("/rpc/adaptive-manipulation-case-file")
async def rpc_adaptive_manipulation_case_file(
    chain: str | None = None,
    token: str | None = None,
    initial_capital_usd: float = 100.0,
    limit: int = 10,
    wallet_limit: int = 10,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
    exit_after_swaps_options: str = "3,10,20",
    delayed_entry_swaps: int = 3,
    fee_bps: float = 100.0,
    fresh_wallet_hours: int = 72,
    cluster_window_minutes: int = 60,
):
    if initial_capital_usd > 100_000:
        raise HTTPException(status_code=400, detail="initial_capital_usd_max_100000")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if wallet_limit > 50:
        raise HTTPException(status_code=400, detail="wallet_limit_max_50")
    if breakout_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="breakout_threshold_pct_max_100000")
    if baseline_swaps > 100:
        raise HTTPException(status_code=400, detail="baseline_swaps_max_100")
    if confirmation_swaps > 20:
        raise HTTPException(status_code=400, detail="confirmation_swaps_max_20")
    if pre_event_swaps > 200:
        raise HTTPException(status_code=400, detail="pre_event_swaps_max_200")
    if delayed_entry_swaps > 50:
        raise HTTPException(status_code=400, detail="delayed_entry_swaps_max_50")
    if fee_bps > 1_000:
        raise HTTPException(status_code=400, detail="fee_bps_max_1000")
    if fresh_wallet_hours > 24 * 30:
        raise HTTPException(status_code=400, detail="fresh_wallet_hours_max_720")
    if cluster_window_minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="cluster_window_minutes_max_1440")
    return await asyncio.to_thread(
        get_adaptive_manipulation_case_file,
        chain,
        token,
        initial_capital_usd,
        limit,
        wallet_limit,
        breakout_threshold_pct,
        baseline_swaps,
        confirmation_swaps,
        pre_event_swaps,
        exit_after_swaps_options,
        delayed_entry_swaps,
        fee_bps,
        fresh_wallet_hours,
        cluster_window_minutes,
    )


@router.get("/rpc/manipulation-detection-behavioral-evidence-bridge")
@router.post("/rpc/manipulation-detection-behavioral-evidence-bridge")
async def rpc_manipulation_detection_behavioral_evidence_bridge(
    chain: str | None = "bsc",
    token: str | None = None,
    limit: int = 10,
    wallet_limit: int = 10,
    dry_run: bool = True,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
    fresh_wallet_hours: int = 72,
    cluster_window_minutes: int = 60,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if wallet_limit > 50:
        raise HTTPException(status_code=400, detail="wallet_limit_max_50")
    if breakout_threshold_pct > 100_000:
        raise HTTPException(status_code=400, detail="breakout_threshold_pct_max_100000")
    if baseline_swaps > 100:
        raise HTTPException(status_code=400, detail="baseline_swaps_max_100")
    if confirmation_swaps > 20:
        raise HTTPException(status_code=400, detail="confirmation_swaps_max_20")
    if pre_event_swaps > 200:
        raise HTTPException(status_code=400, detail="pre_event_swaps_max_200")
    if fresh_wallet_hours > 24 * 30:
        raise HTTPException(status_code=400, detail="fresh_wallet_hours_max_720")
    if cluster_window_minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="cluster_window_minutes_max_1440")
    return await asyncio.to_thread(
        get_manipulation_detection_behavioral_evidence_bridge,
        chain,
        token,
        limit,
        wallet_limit,
        dry_run,
        breakout_threshold_pct,
        baseline_swaps,
        confirmation_swaps,
        pre_event_swaps,
        fresh_wallet_hours,
        cluster_window_minutes,
    )


@router.get("/rpc/manipulation-detection-top-expansion-behavioral-anomaly-scoring-preview")
@router.post("/rpc/manipulation-detection-top-expansion-behavioral-anomaly-scoring-preview")
async def rpc_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview,
        chain,
        pool_address,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-top-expansion-behavioral-shadow-outcome-backtest-plan")
@router.post("/rpc/manipulation-detection-top-expansion-behavioral-shadow-outcome-backtest-plan")
async def rpc_manipulation_detection_top_expansion_behavioral_shadow_outcome_backtest_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    score_threshold: int = 75,
    entry_slippage_bps: int = 400,
    exit_slippage_bps: int = 400,
    mev_penalty_bps: int = 200,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if score_threshold > 100:
        raise HTTPException(status_code=400, detail="score_threshold_max_100")
    for name, value in {
        "entry_slippage_bps": entry_slippage_bps,
        "exit_slippage_bps": exit_slippage_bps,
        "mev_penalty_bps": mev_penalty_bps,
    }.items():
        if value > 5000:
            raise HTTPException(status_code=400, detail=f"{name}_max_5000")
    return await asyncio.to_thread(
        get_manipulation_detection_top_expansion_behavioral_shadow_outcome_backtest_plan,
        chain,
        pool_address,
        limit,
        dry_run,
        score_threshold,
        entry_slippage_bps,
        exit_slippage_bps,
        mev_penalty_bps,
    )


@router.get("/rpc/manipulation-detection-behavioral-score-pump-backtest-preview")
@router.post("/rpc/manipulation-detection-behavioral-score-pump-backtest-preview")
async def rpc_manipulation_detection_behavioral_score_pump_backtest_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 10,
    min_behavioral_score: int = 60,
    entry_score_threshold: int = 70,
    entry_slippage_bps: int = 400,
    exit_slippage_bps: int = 400,
    mev_penalty_bps: int = 200,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 10000:
        raise HTTPException(status_code=400, detail="min_swaps_max_10000")
    if min_behavioral_score > 100:
        raise HTTPException(status_code=400, detail="min_behavioral_score_max_100")
    if entry_score_threshold > 100:
        raise HTTPException(status_code=400, detail="entry_score_threshold_max_100")
    for name, value in {
        "entry_slippage_bps": entry_slippage_bps,
        "exit_slippage_bps": exit_slippage_bps,
        "mev_penalty_bps": mev_penalty_bps,
    }.items():
        if value > 5000:
            raise HTTPException(status_code=400, detail=f"{name}_max_5000")
    return await asyncio.to_thread(
        get_manipulation_detection_behavioral_score_pump_backtest_preview,
        chain,
        pool_address,
        limit,
        dry_run,
        min_swaps,
        min_behavioral_score,
        entry_score_threshold,
        entry_slippage_bps,
        exit_slippage_bps,
        mev_penalty_bps,
    )


@router.get("/rpc/manipulation-detection-honeypot-correlation-scan-preview")
@router.post("/rpc/manipulation-detection-honeypot-correlation-scan-preview")
async def rpc_manipulation_detection_honeypot_correlation_scan_preview(
    chain: str | None = "bsc",
    limit: int = 50,
    dry_run: bool = True,
    min_behavioral_score: int = 60,
    min_swaps: int = 10,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_behavioral_score > 100:
        raise HTTPException(status_code=400, detail="min_behavioral_score_max_100")
    if min_swaps > 10000:
        raise HTTPException(status_code=400, detail="min_swaps_max_10000")
    if timeout_seconds > 30:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_30")
    return await asyncio.to_thread(
        get_manipulation_detection_honeypot_correlation_scan_preview,
        chain,
        limit,
        dry_run,
        min_behavioral_score,
        min_swaps,
        use_honeypot,
        use_goplus,
        timeout_seconds,
    )


@router.get("/rpc/manipulation-detection-top-expansion-behavioral-tradability-filter-preview")
@router.post("/rpc/manipulation-detection-top-expansion-behavioral-tradability-filter-preview")
async def rpc_manipulation_detection_top_expansion_behavioral_tradability_filter_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    score_threshold: int = 75,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if score_threshold > 100:
        raise HTTPException(status_code=400, detail="score_threshold_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_top_expansion_behavioral_tradability_filter_preview,
        chain,
        pool_address,
        limit,
        dry_run,
        score_threshold,
    )


@router.get("/rpc/manipulation-detection-top-expansion-behavioral-t0-shift-experiment-preview")
@router.post("/rpc/manipulation-detection-top-expansion-behavioral-t0-shift-experiment-preview")
async def rpc_manipulation_detection_top_expansion_behavioral_t0_shift_experiment_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    strong_score_threshold: int = 75,
    thresholds: str | None = "40,50,60,70,82",
    entry_slippage_bps: int = 400,
    exit_slippage_bps: int = 400,
    mev_penalty_bps: int = 200,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if strong_score_threshold > 100:
        raise HTTPException(status_code=400, detail="strong_score_threshold_max_100")
    for name, value in {
        "entry_slippage_bps": entry_slippage_bps,
        "exit_slippage_bps": exit_slippage_bps,
        "mev_penalty_bps": mev_penalty_bps,
    }.items():
        if value > 5000:
            raise HTTPException(status_code=400, detail=f"{name}_max_5000")
    return await asyncio.to_thread(
        get_manipulation_detection_top_expansion_behavioral_t0_shift_experiment_preview,
        chain,
        pool_address,
        limit,
        dry_run,
        strong_score_threshold,
        thresholds,
        entry_slippage_bps,
        exit_slippage_bps,
        mev_penalty_bps,
    )


@router.get("/rpc/manipulation-detection-top-expansion-directional-intent-classifier-preview")
@router.post("/rpc/manipulation-detection-top-expansion-directional-intent-classifier-preview")
async def rpc_manipulation_detection_top_expansion_directional_intent_classifier_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    min_behavioral_score: int = 50,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if min_behavioral_score > 100:
        raise HTTPException(status_code=400, detail="min_behavioral_score_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_top_expansion_directional_intent_classifier_preview,
        chain,
        pool_address,
        limit,
        dry_run,
        min_behavioral_score,
    )


@router.get("/rpc/manipulation-detection-stealth-accumulation-anomaly-scan-preview")
@router.post("/rpc/manipulation-detection-stealth-accumulation-anomaly-scan-preview")
async def rpc_manipulation_detection_stealth_accumulation_anomaly_scan_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    max_pools: int = 50,
    max_circularity_pct: float = 30.0,
    min_hold_freeze_proxy_pct: float = 70.0,
    min_buy_flows: int = 3,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if max_pools > 200:
        raise HTTPException(status_code=400, detail="max_pools_max_200")
    return await asyncio.to_thread(
        get_manipulation_detection_stealth_accumulation_anomaly_scan_preview,
        chain,
        limit,
        dry_run,
        max_pools,
        max_circularity_pct,
        min_hold_freeze_proxy_pct,
        min_buy_flows,
    )


@router.get("/rpc/manipulation-detection-stealth-funnel-diagnostic-preview")
@router.post("/rpc/manipulation-detection-stealth-funnel-diagnostic-preview")
async def rpc_manipulation_detection_stealth_funnel_diagnostic_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    max_pools: int = 50,
    low_circularity_pct: float = 30.0,
    high_hold_freeze_proxy_pct: float = 50.0,
    min_buy_flows: int = 3,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if max_pools > 200:
        raise HTTPException(status_code=400, detail="max_pools_max_200")
    return await asyncio.to_thread(
        get_manipulation_detection_stealth_funnel_diagnostic_preview,
        chain,
        limit,
        dry_run,
        max_pools,
        low_circularity_pct,
        high_hold_freeze_proxy_pct,
        min_buy_flows,
    )


@router.get("/rpc/manipulation-detection-quiet-pool-scanner-plan-preview")
@router.post("/rpc/manipulation-detection-quiet-pool-scanner-plan-preview")
async def rpc_manipulation_detection_quiet_pool_scanner_plan_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    max_pools: int = 100,
    max_swap_rows: int = 50,
    min_transfer_rows: int = 1,
    min_pool_age_days: int = 7,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if max_pools > 500:
        raise HTTPException(status_code=400, detail="max_pools_max_500")
    return await asyncio.to_thread(
        get_manipulation_detection_quiet_pool_scanner_plan_preview,
        chain,
        limit,
        dry_run,
        max_pools,
        max_swap_rows,
        min_transfer_rows,
        min_pool_age_days,
    )


@router.get("/rpc/manipulation-detection-cex-listing-probability-bridge-preview")
@router.post("/rpc/manipulation-detection-cex-listing-probability-bridge-preview")
async def rpc_manipulation_detection_cex_listing_probability_bridge_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    min_behavioral_score: int = 50,
    cex_deposit_limit: int = 100,
    token_addresses: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_behavioral_score > 100:
        raise HTTPException(status_code=400, detail="min_behavioral_score_max_100")
    if cex_deposit_limit > 200:
        raise HTTPException(status_code=400, detail="cex_deposit_limit_max_200")
    return await asyncio.to_thread(
        get_manipulation_detection_cex_listing_probability_bridge_preview,
        chain,
        limit,
        dry_run,
        min_behavioral_score,
        cex_deposit_limit,
        token_addresses,
    )


@router.get("/rpc/manipulation-detection-cex-listing-negative-cohort-discovery-preview")
@router.post("/rpc/manipulation-detection-cex-listing-negative-cohort-discovery-preview")
async def rpc_manipulation_detection_cex_listing_negative_cohort_discovery_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    min_behavioral_score: int = 20,
    min_age_days: int = 90,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_behavioral_score > 100:
        raise HTTPException(status_code=400, detail="min_behavioral_score_max_100")
    if min_age_days > 3650:
        raise HTTPException(status_code=400, detail="min_age_days_max_3650")
    return await asyncio.to_thread(
        get_manipulation_detection_cex_listing_negative_cohort_discovery_preview,
        chain,
        limit,
        dry_run,
        min_behavioral_score,
        min_age_days,
    )


@router.get("/rpc/manipulation-detection-external-scam-negative-intake-preview")
@router.post("/rpc/manipulation-detection-external-scam-negative-intake-preview")
async def rpc_manipulation_detection_external_scam_negative_intake_preview(
    chain: str | None = "bsc",
    token_addresses: str | None = None,
    limit: int = 20,
    dry_run: bool = True,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if timeout_seconds > 30:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_30")
    return await asyncio.to_thread(
        get_manipulation_detection_external_scam_negative_intake_preview,
        chain,
        token_addresses,
        limit,
        dry_run,
        use_honeypot,
        use_goplus,
        timeout_seconds,
    )


@router.get("/rpc/manipulation-detection-documented-scam-negative-candidate-scope-expansion-preview")
@router.post("/rpc/manipulation-detection-documented-scam-negative-candidate-scope-expansion-preview")
async def rpc_manipulation_detection_documented_scam_negative_candidate_scope_expansion_preview(
    chain: str | None = "bsc",
    limit: int = 20,
    dry_run: bool = True,
    max_scan_rows: int = 500,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if max_scan_rows > 5000:
        raise HTTPException(status_code=400, detail="max_scan_rows_max_5000")
    if timeout_seconds > 30:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_30")
    return await asyncio.to_thread(
        get_manipulation_detection_documented_scam_negative_candidate_scope_expansion_preview,
        chain,
        limit,
        dry_run,
        max_scan_rows,
        use_honeypot,
        use_goplus,
        timeout_seconds,
    )


@router.get("/rpc/manipulation-detection-cex-listing-ground-truth-seed-coherence-checkpoint")
@router.post("/rpc/manipulation-detection-cex-listing-ground-truth-seed-coherence-checkpoint")
async def rpc_manipulation_detection_cex_listing_ground_truth_seed_coherence_checkpoint(
    chain: str | None = "bsc",
    dry_run: bool = True,
    negative_limit: int = 20,
    max_scan_rows: int = 500,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
    allow_exploratory_majority_context: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if negative_limit > 50:
        raise HTTPException(status_code=400, detail="negative_limit_max_50")
    if max_scan_rows > 5000:
        raise HTTPException(status_code=400, detail="max_scan_rows_max_5000")
    if timeout_seconds > 30:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_30")
    return await asyncio.to_thread(
        get_manipulation_detection_cex_listing_ground_truth_seed_coherence_checkpoint,
        chain,
        dry_run,
        negative_limit,
        max_scan_rows,
        use_honeypot,
        use_goplus,
        timeout_seconds,
        allow_exploratory_majority_context,
    )


@router.get("/rpc/manipulation-detection-cex-listing-exploratory-shadow-backtest-preview")
@router.post("/rpc/manipulation-detection-cex-listing-exploratory-shadow-backtest-preview")
async def rpc_manipulation_detection_cex_listing_exploratory_shadow_backtest_preview(
    chain: str | None = "bsc",
    dry_run: bool = True,
    score_threshold: int = 50,
    negative_limit: int = 20,
    max_scan_rows: int = 500,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if score_threshold > 100:
        raise HTTPException(status_code=400, detail="score_threshold_max_100")
    if negative_limit > 50:
        raise HTTPException(status_code=400, detail="negative_limit_max_50")
    if max_scan_rows > 5000:
        raise HTTPException(status_code=400, detail="max_scan_rows_max_5000")
    if timeout_seconds > 30:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_30")
    return await asyncio.to_thread(
        get_manipulation_detection_cex_listing_exploratory_shadow_backtest_preview,
        chain,
        dry_run,
        score_threshold,
        negative_limit,
        max_scan_rows,
        use_honeypot,
        use_goplus,
        timeout_seconds,
    )


@router.get("/rpc/manipulation-detection-cex-listing-feature-wiring-diagnostic-preview")
@router.post("/rpc/manipulation-detection-cex-listing-feature-wiring-diagnostic-preview")
async def rpc_manipulation_detection_cex_listing_feature_wiring_diagnostic_preview(
    chain: str | None = "bsc",
    dry_run: bool = True,
    cex_deposit_limit: int = 100,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if cex_deposit_limit > 200:
        raise HTTPException(status_code=400, detail="cex_deposit_limit_max_200")
    return await asyncio.to_thread(
        get_manipulation_detection_cex_listing_feature_wiring_diagnostic_preview,
        chain,
        dry_run,
        cex_deposit_limit,
    )


@router.get("/rpc/manipulation-detection-feature-backfill-orchestrator-preview")
@router.post("/rpc/manipulation-detection-feature-backfill-orchestrator-preview")
async def rpc_manipulation_detection_feature_backfill_orchestrator_preview(
    chain: str | None = "bsc",
    token_addresses: str | None = None,
    dry_run: bool = True,
    run_existing_previews: bool = True,
    cex_deposit_limit: int = 100,
    min_raw_swaps_for_feature_backfill: int = 50,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if cex_deposit_limit > 200:
        raise HTTPException(status_code=400, detail="cex_deposit_limit_max_200")
    if min_raw_swaps_for_feature_backfill > 10000:
        raise HTTPException(status_code=400, detail="min_raw_swaps_for_feature_backfill_max_10000")
    return await asyncio.to_thread(
        get_manipulation_detection_feature_backfill_orchestrator_preview,
        chain,
        token_addresses,
        dry_run,
        run_existing_previews,
        cex_deposit_limit,
        min_raw_swaps_for_feature_backfill,
    )


@router.get("/rpc/manipulation-detection-b-feature-backfill-replay-diagnostic-preview")
@router.post("/rpc/manipulation-detection-b-feature-backfill-replay-diagnostic-preview")
async def rpc_manipulation_detection_b_feature_backfill_replay_diagnostic_preview(
    chain: str | None = "bsc",
    token_address: str | None = "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    pool_address: str | None = "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
    dry_run: bool = True,
    sample_limit: int = 25,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if sample_limit > 100:
        raise HTTPException(status_code=400, detail="sample_limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_b_feature_backfill_replay_diagnostic_preview,
        chain,
        token_address,
        pool_address,
        dry_run,
        sample_limit,
    )


@router.get("/rpc/manipulation-detection-b-cex-destination-wallet-reference-repair-preview")
@router.post("/rpc/manipulation-detection-b-cex-destination-wallet-reference-repair-preview")
async def rpc_manipulation_detection_b_cex_destination_wallet_reference_repair_preview(
    chain: str | None = "bsc",
    token_address: str | None = "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    dry_run: bool = True,
    limit: int = 20,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_b_cex_destination_wallet_reference_repair_preview,
        chain,
        token_address,
        dry_run,
        limit,
    )


@router.get("/rpc/manipulation-detection-b-destination-holder-distribution-flow-check-preview")
@router.post("/rpc/manipulation-detection-b-destination-holder-distribution-flow-check-preview")
async def rpc_manipulation_detection_b_destination_holder_distribution_flow_check_preview(
    chain: str | None = "bsc",
    token_address: str | None = "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    pool_address: str | None = "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
    dry_run: bool = True,
    limit: int = 20,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_b_destination_holder_distribution_flow_check_preview,
        chain,
        token_address,
        pool_address,
        dry_run,
        limit,
    )


@router.get("/rpc/manipulation-detection-lab-b-targeted-raw-context-backfill-plan")
@router.post("/rpc/manipulation-detection-lab-b-targeted-raw-context-backfill-plan")
async def rpc_manipulation_detection_lab_b_targeted_raw_context_backfill_plan(
    chain: str | None = "bsc",
    token_addresses: str | None = None,
    dry_run: bool = True,
    block_padding: int = 50_000,
    max_window_blocks: int = 250_000,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_padding > 500_000:
        raise HTTPException(status_code=400, detail="block_padding_max_500000")
    if max_window_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_2000000")
    return await asyncio.to_thread(
        get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan,
        chain,
        token_addresses,
        dry_run,
        block_padding,
        max_window_blocks,
    )


@router.get("/rpc/manipulation-detection-b-seed-bounded-raw-context-lookup-dry-run")
@router.post("/rpc/manipulation-detection-b-seed-bounded-raw-context-lookup-dry-run")
async def rpc_manipulation_detection_b_seed_bounded_raw_context_lookup_dry_run(
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
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_padding > 500_000:
        raise HTTPException(status_code=400, detail="block_padding_max_500000")
    if max_window_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_2000000")
    if max_sqd_calls > 60:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_60")
    if max_sqd_block_span > 50_000:
        raise HTTPException(status_code=400, detail="max_sqd_block_span_max_50000")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if max_logs_per_filter > 1000:
        raise HTTPException(status_code=400, detail="max_logs_per_filter_max_1000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_manipulation_detection_b_seed_bounded_raw_context_lookup_dry_run,
        chain,
        token_address,
        pool_address,
        dry_run,
        allow_external,
        confirm,
        block_padding,
        max_window_blocks,
        max_sqd_calls,
        max_sqd_block_span,
        max_logs_total,
        max_logs_per_filter,
        timeout,
    )


@router.post("/rpc/manipulation-detection-b-seed-raw-context-evidence/insert")
async def rpc_insert_manipulation_detection_b_seed_raw_context_evidence(
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
    _: None = Depends(_require_data_admin),
):
    if allow_external and dry_run and confirm not in {
        "RUN_B_SEED_RAW_CONTEXT_LOOKUP",
        "PREVIEW_B_SEED_RAW_CONTEXT_EVIDENCE_INSERT",
        "INSERT_B_SEED_RAW_CONTEXT_EVIDENCE",
    }:
        raise HTTPException(status_code=400, detail="confirm_PREVIEW_B_SEED_RAW_CONTEXT_EVIDENCE_INSERT_required")
    if not dry_run and confirm != "INSERT_B_SEED_RAW_CONTEXT_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_B_SEED_RAW_CONTEXT_EVIDENCE_required")
    if not dry_run and not expected_raw_context_lookup_digest:
        raise HTTPException(status_code=400, detail="expected_raw_context_lookup_digest_required")
    if block_padding > 500_000:
        raise HTTPException(status_code=400, detail="block_padding_max_500000")
    if max_window_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_2000000")
    if max_sqd_calls > 60:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_60")
    if max_sqd_block_span > 50_000:
        raise HTTPException(status_code=400, detail="max_sqd_block_span_max_50000")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if max_logs_per_filter > 1000:
        raise HTTPException(status_code=400, detail="max_logs_per_filter_max_1000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        insert_manipulation_detection_b_seed_raw_context_evidence,
        chain,
        token_address,
        pool_address,
        dry_run,
        allow_external,
        confirm,
        expected_raw_context_lookup_digest,
        block_padding,
        max_window_blocks,
        max_sqd_calls,
        max_sqd_block_span,
        max_logs_total,
        max_logs_per_filter,
        timeout,
    )


@router.get("/rpc/manipulation-detection-local-native-ground-truth-discovery-preview")
@router.post("/rpc/manipulation-detection-local-native-ground-truth-discovery-preview")
async def rpc_manipulation_detection_local_native_ground_truth_discovery_preview(
    chain: str | None = "bsc",
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 5,
    min_transfers: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 10000:
        raise HTTPException(status_code=400, detail="min_swaps_max_10000")
    if min_transfers > 100000:
        raise HTTPException(status_code=400, detail="min_transfers_max_100000")
    return await asyncio.to_thread(
        get_manipulation_detection_local_native_ground_truth_discovery_preview,
        chain,
        limit,
        dry_run,
        min_swaps,
        min_transfers,
    )


@router.get("/rpc/manipulation-detection-native-positive-candidate-replacement-discovery-preview")
@router.post("/rpc/manipulation-detection-native-positive-candidate-replacement-discovery-preview")
async def rpc_manipulation_detection_native_positive_candidate_replacement_discovery_preview(
    chain: str | None = "bsc",
    limit: int = 20,
    dry_run: bool = True,
    min_swaps: int = 100,
    min_transfers: int = 200,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 10000:
        raise HTTPException(status_code=400, detail="min_swaps_max_10000")
    if min_transfers > 100000:
        raise HTTPException(status_code=400, detail="min_transfers_max_100000")
    return await asyncio.to_thread(
        get_manipulation_detection_native_positive_candidate_replacement_discovery_preview,
        chain,
        limit,
        dry_run,
        min_swaps,
        min_transfers,
    )


@router.get("/rpc/manipulation-detection-local-native-ground-truth-labeling-lookup-preview")
@router.post("/rpc/manipulation-detection-local-native-ground-truth-labeling-lookup-preview")
async def rpc_manipulation_detection_local_native_ground_truth_labeling_lookup_preview(
    chain: str | None = "bsc",
    limit: int = 20,
    dry_run: bool = True,
    min_swaps: int = 1,
    min_transfers: int = 5,
    use_coingecko: bool = True,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 10000:
        raise HTTPException(status_code=400, detail="min_swaps_max_10000")
    if min_transfers > 100000:
        raise HTTPException(status_code=400, detail="min_transfers_max_100000")
    if timeout_seconds > 30:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_30")
    return await asyncio.to_thread(
        get_manipulation_detection_local_native_ground_truth_labeling_lookup_preview,
        chain,
        limit,
        dry_run,
        min_swaps,
        min_transfers,
        use_coingecko,
        use_honeypot,
        use_goplus,
        timeout_seconds,
    )


@router.get("/rpc/manipulation-detection-cex-listing-ground-truth-dataset-plan-preview")
@router.post("/rpc/manipulation-detection-cex-listing-ground-truth-dataset-plan-preview")
async def rpc_manipulation_detection_cex_listing_ground_truth_dataset_plan_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    lookback_days: int = 365,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if lookback_days > 1095:
        raise HTTPException(status_code=400, detail="lookback_days_max_1095")
    return await asyncio.to_thread(
        get_manipulation_detection_cex_listing_ground_truth_dataset_plan_preview,
        chain,
        limit,
        dry_run,
        lookback_days,
    )


@router.post("/rpc/manipulation-detection-cex-listing-ground-truth-dataset/create")
async def rpc_create_manipulation_detection_cex_listing_ground_truth_dataset(
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_CEX_LISTING_GROUND_TRUTH_DATASET":
        raise HTTPException(status_code=400, detail="confirm_CREATE_CEX_LISTING_GROUND_TRUTH_DATASET_required")
    return await asyncio.to_thread(
        create_manipulation_detection_cex_listing_ground_truth_dataset,
        chain,
        dry_run,
        confirm,
    )


@router.post("/rpc/manipulation-detection-cex-listing-ground-truth-dataset/insert")
async def rpc_insert_manipulation_detection_cex_listing_ground_truth_rows(
    payload: Any = Body(default=None),
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    body = payload if isinstance(payload, dict) else {}
    rows = body.get("rows") if isinstance(body.get("rows"), list) else []
    expected_keys = body.get("expected_dedupe_keys")
    if not dry_run:
        if confirm != "INSERT_CEX_LISTING_GROUND_TRUTH_ROWS":
            raise HTTPException(status_code=400, detail="confirm_INSERT_CEX_LISTING_GROUND_TRUTH_ROWS_required")
        if not expected_keys:
            raise HTTPException(status_code=400, detail="expected_dedupe_keys_required")
    return await asyncio.to_thread(
        insert_manipulation_detection_cex_listing_ground_truth_rows,
        rows,
        chain,
        dry_run,
        confirm,
        expected_keys,
    )


@router.get("/rpc/swap-identity-readiness")
async def rpc_swap_identity_readiness(chain: str | None = None):
    return await asyncio.to_thread(get_swap_identity_readiness, chain)


@router.get("/rpc/token-transfer-coverage")
async def rpc_token_transfer_coverage(chain: str | None = None):
    return await asyncio.to_thread(get_token_transfer_coverage, chain)


@router.get("/rpc/token-transfer-cex-deposits")
async def rpc_token_transfer_cex_deposits(chain: str | None = None, limit: int = 50):
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(get_token_transfer_cex_deposit_scan, chain, limit)


@router.get("/rpc/cex-label-coverage")
async def rpc_cex_label_coverage(limit: int = 50):
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(get_cex_label_coverage_audit, limit)


@router.get("/rpc/cex-label-acquisition-plan")
async def rpc_cex_label_acquisition_plan(entities: str | None = "gate,mexc", limit: int = 50):
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(get_cex_label_acquisition_plan, entities, limit)


@router.get("/rpc/cex-label-promotion-review")
async def rpc_cex_label_promotion_review(entities: str | None = "gate,mexc", limit: int = 50):
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(get_cex_label_promotion_review, entities, limit)


@router.post("/rpc/cex-label-promotion-write-preview")
async def rpc_cex_label_promotion_write_preview(
    candidate_ids: str = "",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    clean_ids: list[int] = []
    for item in str(candidate_ids or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            clean_ids.append(int(item))
        except ValueError:
            raise HTTPException(status_code=400, detail="candidate_ids_must_be_comma_separated_integers")
    if len(clean_ids) > 50:
        raise HTTPException(status_code=400, detail="candidate_ids_limit_50")
    if not dry_run and confirm != "PROMOTE_STRICT_CEX_LABELS":
        raise HTTPException(status_code=400, detail="confirm_PROMOTE_STRICT_CEX_LABELS_required")
    return await asyncio.to_thread(get_cex_label_promotion_write_preview, clean_ids, dry_run, confirm)


@router.get("/rpc/cex-label-promotion-admin-queue")
async def rpc_cex_label_promotion_admin_queue(
    entities: str | None = "gate,mexc",
    limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(get_cex_label_promotion_admin_queue, entities, limit)


@router.post("/rpc/cex-label-promotion-stage")
async def rpc_cex_label_promotion_stage(
    candidate_id: str = "",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if "," in str(candidate_id or ""):
        raise HTTPException(status_code=400, detail="single_candidate_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not dry_run and confirm != "STAGE_STRICT_CEX_LABEL":
        raise HTTPException(status_code=400, detail="confirm_STAGE_STRICT_CEX_LABEL_required")
    return await asyncio.to_thread(get_cex_label_promotion_stage, candidate_id, dry_run, confirm)


@router.post("/rpc/cex-label-promotion-backup")
async def rpc_cex_label_promotion_backup(
    candidate_id: str = "",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if "," in str(candidate_id or ""):
        raise HTTPException(status_code=400, detail="single_candidate_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not dry_run and confirm != "CREATE_STRICT_CEX_LABEL_BACKUP":
        raise HTTPException(status_code=400, detail="confirm_CREATE_STRICT_CEX_LABEL_BACKUP_required")
    return await asyncio.to_thread(get_cex_label_promotion_backup, candidate_id, dry_run, confirm)


@router.get("/rpc/cex-label-promotion-backups")
async def rpc_cex_label_promotion_backups(
    candidate_id: str = "",
    limit: int = 20,
    _: None = Depends(_require_data_admin),
):
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(get_cex_label_promotion_backups, candidate_id, limit)


@router.get("/rpc/cex-label-promotion-final-check")
async def rpc_cex_label_promotion_final_check(
    candidate_id: str = "",
    _: None = Depends(_require_data_admin),
):
    if "," in str(candidate_id or ""):
        raise HTTPException(status_code=400, detail="single_candidate_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    return await asyncio.to_thread(get_cex_label_promotion_final_check, candidate_id)


@router.get("/rpc/cex-label-promotion-execution-envelope")
async def rpc_cex_label_promotion_execution_envelope(
    candidate_id: str = "",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if "," in str(candidate_id or ""):
        raise HTTPException(status_code=400, detail="single_candidate_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(get_cex_label_promotion_execution_envelope, candidate_id, dry_run)


@router.get("/rpc/cex-label-promotion-simulation-report")
async def rpc_cex_label_promotion_simulation_report(
    candidate_id: str = "",
    _: None = Depends(_require_data_admin),
):
    if "," in str(candidate_id or ""):
        raise HTTPException(status_code=400, detail="single_candidate_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    return await asyncio.to_thread(get_cex_label_promotion_simulation_report, candidate_id)


@router.get("/rpc/cex-label-promotion-dashboard")
async def rpc_cex_label_promotion_dashboard(
    entities: str | None = "gate,mexc",
    limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(get_cex_label_promotion_dashboard, entities, limit)


@router.get("/rpc/cex-label-promotion-blocker-audit")
async def rpc_cex_label_promotion_blocker_audit(
    entities: str | None = "gate,mexc",
    limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(get_cex_label_promotion_blocker_audit, entities, limit)


@router.get("/rpc/cex-label-source-quality-plan")
async def rpc_cex_label_source_quality_plan(
    entities: str | None = "gate,mexc",
    limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(get_cex_label_source_quality_plan, entities, limit)


@router.get("/rpc/cex-label-independent-source-queue")
async def rpc_cex_label_independent_source_queue(
    entities: str | None = "gate,mexc",
    limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(get_cex_label_independent_source_queue, entities, limit)


@router.post("/rpc/cex-label-independent-evidence-dry-run")
async def rpc_cex_label_independent_evidence_dry_run(
    candidate_id: str = "",
    evidence_type: str = "",
    source_url: str = "",
    notes: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not str(source_url or "").strip():
        raise HTTPException(status_code=400, detail="source_url_required")
    return await asyncio.to_thread(
        get_cex_label_independent_evidence_dry_run,
        candidate_id,
        evidence_type,
        source_url,
        notes,
        dry_run,
    )


@router.post("/rpc/cex-label-independent-evidence-persist-preview")
async def rpc_cex_label_independent_evidence_persist_preview(
    candidate_id: str = "",
    evidence_type: str = "",
    source_url: str = "",
    notes: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not str(source_url or "").strip():
        raise HTTPException(status_code=400, detail="source_url_required")
    return await asyncio.to_thread(
        get_cex_label_independent_evidence_persist_preview,
        candidate_id,
        evidence_type,
        source_url,
        notes,
        dry_run,
    )


@router.post("/rpc/cex-label-independent-evidence-persist-contract")
async def rpc_cex_label_independent_evidence_persist_contract(
    candidate_id: str = "",
    evidence_type: str = "",
    source_url: str = "",
    notes: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not str(source_url or "").strip():
        raise HTTPException(status_code=400, detail="source_url_required")
    return await asyncio.to_thread(
        get_cex_label_independent_evidence_persist_contract,
        candidate_id,
        evidence_type,
        source_url,
        notes,
        dry_run,
    )


@router.post("/rpc/cex-label-independent-evidence/insert")
async def rpc_cex_label_independent_evidence_insert(
    candidate_id: str = "",
    evidence_type: str = "",
    source_url: str = "",
    notes: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "INSERT_CEX_INDEPENDENT_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_CEX_INDEPENDENT_EVIDENCE_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not str(source_url or "").strip():
        raise HTTPException(status_code=400, detail="source_url_required")
    return await asyncio.to_thread(
        insert_cex_label_independent_evidence,
        candidate_id,
        evidence_type,
        source_url,
        notes,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-label-independent-evidence-review-queue")
async def rpc_cex_label_independent_evidence_review_queue(
    status: str | None = "pending_admin_review",
    limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(get_cex_label_independent_evidence_review_queue, status, limit)


@router.post("/rpc/cex-label-confidence-upgrade-preview")
async def rpc_cex_label_confidence_upgrade_preview(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_preview,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.post("/rpc/cex-label-confidence-upgrade-stage")
async def rpc_cex_label_confidence_upgrade_stage(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "STAGE_CEX_CONFIDENCE_UPGRADE":
        raise HTTPException(status_code=400, detail="confirm_STAGE_CEX_CONFIDENCE_UPGRADE_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_stage,
        evidence_id,
        target_confidence,
        dry_run,
        confirm,
    )


@router.post("/rpc/cex-label-confidence-upgrade-backup-preview")
async def rpc_cex_label_confidence_upgrade_backup_preview(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_backup_preview,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.post("/rpc/cex-label-confidence-upgrade-backup")
async def rpc_cex_label_confidence_upgrade_backup(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_CEX_CONFIDENCE_BACKUP":
        raise HTTPException(status_code=400, detail="confirm_CREATE_CEX_CONFIDENCE_BACKUP_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_backup,
        evidence_id,
        target_confidence,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-label-confidence-upgrade-backups")
async def rpc_cex_label_confidence_upgrade_backups(
    evidence_id: str = "",
    candidate_id: str = "",
    limit: int = 20,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    if not str(candidate_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="candidate_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_backups,
        evidence_id,
        candidate_id,
        limit,
    )


@router.get("/rpc/cex-label-confidence-upgrade-final-check")
async def rpc_cex_label_confidence_upgrade_final_check(
    evidence_id: str = "",
    target_confidence: str = "high",
    _: None = Depends(_require_data_admin),
):
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_final_check,
        evidence_id,
        target_confidence,
    )


@router.post("/rpc/cex-label-confidence-upgrade-execution-envelope")
async def rpc_cex_label_confidence_upgrade_execution_envelope(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_execution_envelope,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.post("/rpc/cex-label-confidence-upgrade-simulation-report")
async def rpc_cex_label_confidence_upgrade_simulation_report(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_simulation_report,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.post("/rpc/cex-label-confidence-upgrade-policy-gate")
async def rpc_cex_label_confidence_upgrade_policy_gate(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_policy_gate,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.post("/rpc/cex-label-confidence-upgrade-apply")
async def rpc_cex_label_confidence_upgrade_apply(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_apply,
        evidence_id,
        target_confidence,
        dry_run,
        confirm,
    )


@router.post("/rpc/cex-label-confidence-upgrade-prewrite-audit")
async def rpc_cex_label_confidence_upgrade_prewrite_audit(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_prewrite_audit,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.post("/rpc/cex-label-confidence-upgrade-controlled-write-review")
async def rpc_cex_label_confidence_upgrade_controlled_write_review(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_controlled_write_review,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.post("/rpc/cex-label-confidence-upgrade-sql-plan")
async def rpc_cex_label_confidence_upgrade_sql_plan(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_sql_plan,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.post("/rpc/cex-label-confidence-upgrade-rollback-smoke")
async def rpc_cex_label_confidence_upgrade_rollback_smoke(
    evidence_id: str = "",
    target_confidence: str = "high",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(evidence_id or "").strip().isdigit():
        raise HTTPException(status_code=400, detail="evidence_id_required")
    return await asyncio.to_thread(
        get_cex_label_confidence_upgrade_rollback_smoke,
        evidence_id,
        target_confidence,
        dry_run,
    )


@router.get("/rpc/cex-independent-evidence-queue-schema-plan")
async def rpc_cex_independent_evidence_queue_schema_plan(
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(get_cex_independent_evidence_queue_schema_plan, dry_run)


@router.post("/rpc/cex-independent-evidence-queue/create")
async def rpc_create_cex_independent_evidence_queue(
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE":
        raise HTTPException(status_code=400, detail="confirm_CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE_required")
    return await asyncio.to_thread(create_cex_independent_evidence_queue, dry_run, confirm)


@router.get("/rpc/cex-deposit-holder-snapshot-refresh-queue")
async def rpc_cex_deposit_holder_snapshot_refresh_queue(chain: str | None = None, limit: int = 20):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(get_cex_deposit_holder_snapshot_refresh_queue, chain, limit)


@router.post("/rpc/cex-deposit-holder-snapshots/refresh")
async def rpc_refresh_cex_deposit_holder_snapshots(
    chain: str | None = None,
    limit: int = 5,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if not dry_run and confirm != "REFRESH_CEX_DEPOSIT_HOLDER_SNAPSHOTS":
        raise HTTPException(status_code=400, detail="confirm_REFRESH_CEX_DEPOSIT_HOLDER_SNAPSHOTS_required")
    return await asyncio.to_thread(refresh_cex_deposit_holder_snapshots, chain, limit, dry_run)


@router.get("/rpc/swap-venue-resolution-candidates")
async def rpc_swap_venue_resolution_candidates(chain: str | None = None, limit: int = 20):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(get_swap_venue_resolution_candidates, chain, limit)


@router.get("/rpc/unknown-swap-attribution-audit")
async def rpc_unknown_swap_attribution_audit(chain: str | None = None, limit: int = 50):
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(get_unknown_swap_attribution_audit, chain, limit)


@router.get("/rpc/dex-router-source-map")
async def rpc_dex_router_source_map(
    chain: str | None = None,
    limit: int = 50,
    include_public_evidence: bool = False,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_dex_router_source_map,
        chain,
        limit,
        include_public_evidence,
    )


@router.get("/rpc/dex-router-official-source-queue")
async def rpc_dex_router_official_source_queue(
    chain: str | None = None,
    limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_dex_router_official_source_queue,
        chain,
        limit,
    )


@router.post("/rpc/dex-router-official-evidence-dry-run")
async def rpc_dex_router_official_evidence_dry_run(
    chain: str,
    router_address: str,
    evidence_type: str,
    source_url: str,
    notes: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_official_evidence_dry_run,
        chain,
        router_address,
        evidence_type,
        source_url,
        notes,
        dry_run,
    )


@router.post("/rpc/dex-router-official-evidence-persist-preview")
async def rpc_dex_router_official_evidence_persist_preview(
    chain: str,
    router_address: str,
    evidence_type: str,
    source_url: str,
    notes: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_official_evidence_persist_preview,
        chain,
        router_address,
        evidence_type,
        source_url,
        notes,
        dry_run,
    )


@router.get("/rpc/dex-router-official-evidence-queue-schema-plan")
async def rpc_dex_router_official_evidence_queue_schema_plan(
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_official_evidence_queue_schema_plan,
        dry_run,
    )


@router.post("/rpc/dex-router-official-evidence-queue/create")
async def rpc_create_dex_router_official_evidence_queue(
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_DEX_ROUTER_OFFICIAL_EVIDENCE_QUEUE":
        raise HTTPException(status_code=400, detail="confirm_CREATE_DEX_ROUTER_OFFICIAL_EVIDENCE_QUEUE_required")
    return await asyncio.to_thread(
        create_dex_router_official_evidence_queue,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-official-evidence/insert")
async def rpc_insert_dex_router_official_evidence(
    chain: str,
    router_address: str,
    evidence_type: str,
    source_url: str,
    notes: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "INSERT_DEX_ROUTER_OFFICIAL_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_DEX_ROUTER_OFFICIAL_EVIDENCE_required")
    return await asyncio.to_thread(
        insert_dex_router_official_evidence,
        chain,
        router_address,
        evidence_type,
        source_url,
        notes,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-router-official-evidence-review-queue")
async def rpc_dex_router_official_evidence_review_queue(
    status: str = "pending_admin_review",
    limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_dex_router_official_evidence_review_queue,
        status,
        limit,
    )


@router.post("/rpc/dex-router-venue-mapping-preview")
async def rpc_dex_router_venue_mapping_preview(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_preview,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping-final-check")
async def rpc_dex_router_venue_mapping_final_check(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_final_check,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping-execution-envelope")
async def rpc_dex_router_venue_mapping_execution_envelope(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_execution_envelope,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping-simulation-report")
async def rpc_dex_router_venue_mapping_simulation_report(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_simulation_report,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping-policy-gate")
async def rpc_dex_router_venue_mapping_policy_gate(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_policy_gate,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping-apply")
async def rpc_dex_router_venue_mapping_apply(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_apply,
        evidence_id,
        venue_name,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-venue-mapping-prewrite-audit")
async def rpc_dex_router_venue_mapping_prewrite_audit(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_prewrite_audit,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping-controlled-write-review")
async def rpc_dex_router_venue_mapping_controlled_write_review(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_controlled_write_review,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping-sql-plan")
async def rpc_dex_router_venue_mapping_sql_plan(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_sql_plan,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping-final-safety-review")
async def rpc_dex_router_venue_mapping_final_safety_review(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_final_safety_review,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping/apply-confirmed")
async def rpc_dex_router_venue_mapping_apply_confirmed(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_apply_confirmed_design,
        evidence_id,
        venue_name,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-venue-mapping-real-write-go-nogo")
async def rpc_dex_router_venue_mapping_real_write_go_nogo(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_real_write_go_nogo,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping/write-skeleton")
async def rpc_dex_router_venue_mapping_write_skeleton(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_write_skeleton,
        evidence_id,
        venue_name,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-venue-mapping/transactional-write-design")
async def rpc_dex_router_venue_mapping_transactional_write_design(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_transactional_write_design,
        evidence_id,
        venue_name,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-venue-mapping/transactional-write-report")
async def rpc_dex_router_venue_mapping_transactional_write_report(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_transactional_write_report,
        evidence_id,
        venue_name,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-venue-mapping/confirmed-write-blueprint")
async def rpc_dex_router_venue_mapping_confirmed_write_blueprint(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_confirmed_write_blueprint,
        evidence_id,
        venue_name,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-venue-mapping/multi-router-validation-scan")
async def rpc_dex_router_venue_mapping_multi_router_validation_scan(
    limit: int = 20,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_multi_router_validation_scan,
        limit,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping/additional-router-evidence-plan")
async def rpc_dex_router_venue_mapping_additional_router_evidence_plan(
    needed: int = 2,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if needed > 5:
        raise HTTPException(status_code=400, detail="needed_max_5")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_additional_router_evidence_plan,
        needed,
        dry_run,
    )


@router.post("/rpc/lab-venue-coverage-source-plan")
async def rpc_lab_venue_coverage_source_plan(
    dry_run: bool = True,
    include_user_observed: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_lab_venue_coverage_source_plan,
        dry_run,
        include_user_observed,
    )


@router.post("/rpc/token-venue-coverage-source-plan")
async def rpc_token_venue_coverage_source_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    dry_run: bool = True,
    include_user_observed: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(token_symbol or "").strip():
        raise HTTPException(status_code=400, detail="token_symbol_required")
    return await asyncio.to_thread(
        get_token_venue_coverage_source_plan,
        token_symbol,
        chain,
        dry_run,
        include_user_observed,
    )


@router.post("/rpc/token-market-discovery-input-contract")
async def rpc_token_market_discovery_input_contract(
    token_symbol: str | None = None,
    chain: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(token_symbol or "").strip():
        raise HTTPException(status_code=400, detail="token_symbol_required")
    return await asyncio.to_thread(
        get_token_market_discovery_input_contract,
        token_symbol,
        chain,
        dry_run,
    )


@router.post("/rpc/token-market-manual-candidate-intake-contract")
async def rpc_token_market_manual_candidate_intake_contract(
    payload: Any = Body(default=None),
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    candidates = payload.get("candidates") if isinstance(payload, dict) else payload
    return await asyncio.to_thread(
        get_token_market_manual_candidate_intake_contract,
        candidates,
        dry_run,
    )


@router.get("/rpc/token-market-local-candidate-discovery-radar")
@router.post("/rpc/token-market-local-candidate-discovery-radar")
async def rpc_token_market_local_candidate_discovery_radar(
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_local_candidate_discovery_radar,
        limit,
        dry_run,
    )


@router.get("/rpc/token-manipulation-data-usability-audit")
@router.post("/rpc/token-manipulation-data-usability-audit")
async def rpc_token_manipulation_data_usability_audit(
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_token_manipulation_data_usability_audit,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-reliability-engine")
@router.post("/rpc/manipulation-detection-reliability-engine")
async def rpc_manipulation_detection_reliability_engine(
    chain: str | None = "bsc",
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_reliability_engine,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-scoring-design")
@router.post("/rpc/manipulation-detection-source-backed-scoring-design")
async def rpc_manipulation_detection_source_backed_scoring_design(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_scoring_design,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-shadow-backtest-plan")
@router.post("/rpc/manipulation-detection-source-backed-shadow-backtest-plan")
async def rpc_manipulation_detection_source_backed_shadow_backtest_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_shadow_backtest_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-shadow-backtest-outcome-dataset-schema-plan")
@router.post("/rpc/manipulation-detection-source-backed-shadow-backtest-outcome-dataset-schema-plan")
async def rpc_manipulation_detection_source_backed_shadow_backtest_outcome_dataset_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_shadow_backtest_outcome_dataset_schema_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-outcome-window-data-collection")
@router.post("/rpc/manipulation-detection-source-backed-outcome-window-data-collection")
async def rpc_manipulation_detection_source_backed_outcome_window_data_collection(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_outcome_window_data_collection_dry_run,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        allow_external,
        confirm,
    )


@router.get("/rpc/manipulation-detection-source-backed-outcome-quality-repair-sync-liquidity-context")
@router.post("/rpc/manipulation-detection-source-backed-outcome-quality-repair-sync-liquidity-context")
async def rpc_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_rpc: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context_dry_run,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        allow_rpc,
        confirm,
    )


@router.get("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-collection-plan")
@router.post("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-collection-plan")
async def rpc_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    max_window_blocks: int = 2000,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_window_blocks > 10000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_10000")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        max_window_blocks,
    )


@router.get("/rpc/manipulation-detection-source-backed-outcome-sync-mint-burn-topic-binding-checkpoint")
@router.post("/rpc/manipulation-detection-source-backed-outcome-sync-mint-burn-topic-binding-checkpoint")
async def rpc_manipulation_detection_source_backed_outcome_sync_mint_burn_topic_binding_checkpoint(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_outcome_sync_mint_burn_topic_binding_checkpoint,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-lookup-dry-run")
@router.post("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-lookup-dry-run")
async def rpc_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 27,
    max_logs_total: int = 1000,
    timeout: int = 8,
    max_window_blocks: int = 2000,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_sqd_calls > 50:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_50")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if max_window_blocks > 10000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_10000")
    return await asyncio.to_thread(
        run_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        allow_external,
        confirm,
        max_sqd_calls,
        max_logs_total,
        timeout,
        max_window_blocks,
    )


@router.get("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence-schema-plan")
@router.post("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence-schema-plan")
async def rpc_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    max_window_blocks: int = 2000,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_window_blocks > 10000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_10000")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        max_window_blocks,
    )


@router.post("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/insert")
async def rpc_insert_manipulation_detection_source_backed_outcome_sync_liquidity_evidence(
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
    max_logs_total: int = 1000,
    timeout: int = 8,
    max_window_blocks: int = 2000,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_sqd_calls > 50:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_50")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if max_window_blocks > 10000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_10000")
    if not dry_run and confirm != "INSERT_UFLOKI_SYNC_LIQUIDITY_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_UFLOKI_SYNC_LIQUIDITY_EVIDENCE_required")
    return await asyncio.to_thread(
        insert_manipulation_detection_source_backed_outcome_sync_liquidity_evidence,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        allow_external,
        lookup_confirm,
        confirm,
        expected_lookup_digest,
        max_sqd_calls,
        max_logs_total,
        timeout,
        max_window_blocks,
    )


@router.get("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/review")
@router.post("/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/review")
async def rpc_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    status: str | None = "raw_observed",
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review_queue,
        chain,
        pool_address,
        token_address,
        status,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-outcome-quality-repair-preview")
@router.post("/rpc/manipulation-detection-source-backed-outcome-quality-repair-preview")
async def rpc_manipulation_detection_source_backed_outcome_quality_repair_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_outcome_quality_repair_preview,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-repaired-outcome-dataset-schema-plan")
@router.post("/rpc/manipulation-detection-source-backed-repaired-outcome-dataset-schema-plan")
async def rpc_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
    )


@router.post("/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/create")
async def rpc_create_manipulation_detection_source_backed_repaired_outcome_dataset(
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_MANIPULATION_REPAIRED_OUTCOME_WINDOWS":
        raise HTTPException(status_code=400, detail="confirm_CREATE_MANIPULATION_REPAIRED_OUTCOME_WINDOWS_required")
    return await asyncio.to_thread(
        create_manipulation_detection_source_backed_repaired_outcome_dataset_table,
        chain,
        dry_run,
        confirm,
    )


@router.post("/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/insert")
async def rpc_insert_manipulation_detection_source_backed_repaired_outcome_dataset(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    confirm: str | None = None,
    expected_repair_preview_digest: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if not dry_run and confirm != "INSERT_MANIPULATION_REPAIRED_OUTCOME_WINDOWS":
        raise HTTPException(status_code=400, detail="confirm_INSERT_MANIPULATION_REPAIRED_OUTCOME_WINDOWS_required")
    return await asyncio.to_thread(
        insert_manipulation_detection_source_backed_repaired_outcome_dataset,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        confirm,
        expected_repair_preview_digest,
    )


@router.get("/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/review")
@router.post("/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/review")
async def rpc_manipulation_detection_source_backed_repaired_outcome_dataset_review(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    status: str | None = "pending_shadow_backtest_review",
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_repaired_outcome_dataset_review_queue,
        chain,
        pool_address,
        token_address,
        status,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-shadow-backtest-preview")
@router.post("/rpc/manipulation-detection-source-backed-shadow-backtest-preview")
async def rpc_manipulation_detection_source_backed_shadow_backtest_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_shadow_backtest_preview,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-source-backed-shadow-replay-controls-preview")
@router.post("/rpc/manipulation-detection-source-backed-shadow-replay-controls-preview")
async def rpc_manipulation_detection_source_backed_shadow_replay_controls_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    min_swaps: int = 4,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_shadow_replay_controls_preview,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
    )


@router.get("/rpc/manipulation-detection-source-backed-control-outcome-collection-plan")
@router.post("/rpc/manipulation-detection-source-backed-control-outcome-collection-plan")
async def rpc_manipulation_detection_source_backed_control_outcome_collection_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_controls > 10:
        raise HTTPException(status_code=400, detail="max_controls_max_10")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_control_outcome_collection_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
        max_controls,
    )


@router.get("/rpc/manipulation-detection-source-backed-control-outcome-lookup-dry-run")
@router.post("/rpc/manipulation-detection-source-backed-control-outcome-lookup-dry-run")
async def rpc_manipulation_detection_source_backed_control_outcome_lookup_dry_run(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_controls > 10:
        raise HTTPException(status_code=400, detail="max_controls_max_10")
    return await asyncio.to_thread(
        run_manipulation_detection_source_backed_control_outcome_lookup_dry_run,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
        max_controls,
    )


@router.get("/rpc/manipulation-detection-source-backed-control-outcome-schema-plan")
@router.post("/rpc/manipulation-detection-source-backed-control-outcome-schema-plan")
async def rpc_manipulation_detection_source_backed_control_outcome_schema_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_controls > 10:
        raise HTTPException(status_code=400, detail="max_controls_max_10")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_control_outcome_schema_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
        max_controls,
    )


@router.post("/rpc/manipulation-detection-source-backed-control-outcome-windows/create")
async def rpc_create_manipulation_detection_source_backed_control_outcome_windows(
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_MANIPULATION_CONTROL_OUTCOME_WINDOWS":
        raise HTTPException(status_code=400, detail="confirm_CREATE_MANIPULATION_CONTROL_OUTCOME_WINDOWS_required")
    return await asyncio.to_thread(
        create_manipulation_detection_source_backed_control_outcome_table,
        chain,
        dry_run,
        confirm,
    )


@router.post("/rpc/manipulation-detection-source-backed-control-outcome-windows/insert")
async def rpc_insert_manipulation_detection_source_backed_control_outcome_windows(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    confirm: str | None = None,
    expected_control_outcome_lookup_digest: str | None = None,
    min_swaps: int = 4,
    max_controls: int = 3,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_controls > 10:
        raise HTTPException(status_code=400, detail="max_controls_max_10")
    if not dry_run and confirm != "INSERT_MANIPULATION_CONTROL_OUTCOME_WINDOWS":
        raise HTTPException(status_code=400, detail="confirm_INSERT_MANIPULATION_CONTROL_OUTCOME_WINDOWS_required")
    if not dry_run and not expected_control_outcome_lookup_digest:
        raise HTTPException(status_code=400, detail="expected_control_outcome_lookup_digest_required")
    return await asyncio.to_thread(
        insert_manipulation_detection_source_backed_control_outcome_windows,
        chain,
        limit,
        dry_run,
        confirm,
        expected_control_outcome_lookup_digest,
        min_swaps,
        max_controls,
    )


@router.get("/rpc/manipulation-detection-source-backed-control-outcome-windows/review")
@router.post("/rpc/manipulation-detection-source-backed-control-outcome-windows/review")
async def rpc_manipulation_detection_source_backed_control_outcome_review(
    chain: str | None = "bsc",
    status: str | None = "pending_control_outcome_review",
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_controls > 10:
        raise HTTPException(status_code=400, detail="max_controls_max_10")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_control_outcome_review_queue,
        chain,
        status,
        limit,
        dry_run,
        min_swaps,
        max_controls,
    )


@router.get("/rpc/manipulation-detection-source-backed-multi-candidate-shadow-replay-preview")
@router.post("/rpc/manipulation-detection-source-backed-multi-candidate-shadow-replay-preview")
async def rpc_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_controls: int = 3,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_controls > 10:
        raise HTTPException(status_code=400, detail="max_controls_max_10")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
        max_controls,
    )


@router.get("/rpc/manipulation-detection-source-backed-replay-policy-thresholds")
@router.post("/rpc/manipulation-detection-source-backed-replay-policy-thresholds")
async def rpc_manipulation_detection_source_backed_replay_policy_thresholds(
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
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_controls > 10:
        raise HTTPException(status_code=400, detail="max_controls_max_10")
    if min_control_cases > 25:
        raise HTTPException(status_code=400, detail="min_control_cases_max_25")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_replay_policy_thresholds,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
        max_controls,
        min_control_cases,
        min_source_favorable_move_pct,
        min_source_net_move_pct,
        max_source_adverse_move_pct,
    )


@router.get("/rpc/manipulation-detection-source-backed-case-control-expansion-plan")
@router.post("/rpc/manipulation-detection-source-backed-case-control-expansion-plan")
async def rpc_manipulation_detection_source_backed_case_control_expansion_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_candidates: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_candidates > 25:
        raise HTTPException(status_code=400, detail="max_candidates_max_25")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_case_control_expansion_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
        max_candidates,
    )


@router.get("/rpc/manipulation-detection-source-backed-top-expansion-raw-context-collection-plan")
@router.post("/rpc/manipulation-detection-source-backed-top-expansion-raw-context-collection-plan")
async def rpc_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    token_address: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    min_swaps: int = 4,
    max_candidates: int = 3,
    max_window_blocks: int = 5000,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_candidates > 10:
        raise HTTPException(status_code=400, detail="max_candidates_max_10")
    if max_window_blocks > 25000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_25000")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
        max_candidates,
        max_window_blocks,
    )


@router.get("/rpc/manipulation-detection-source-backed-top-expansion-raw-context-lookup-dry-run")
@router.post("/rpc/manipulation-detection-source-backed-top-expansion-raw-context-lookup-dry-run")
async def rpc_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run(
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
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if allow_external and confirm != "RUN_TOP_EXPANSION_RAW_CONTEXT_LOOKUP":
        raise HTTPException(status_code=400, detail="confirm_RUN_TOP_EXPANSION_RAW_CONTEXT_LOOKUP_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_candidates > 10:
        raise HTTPException(status_code=400, detail="max_candidates_max_10")
    if max_window_blocks > 25000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_25000")
    if max_sqd_calls > 100:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_100")
    if max_logs_total > 10000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_10000")
    if max_logs_per_filter > 1000:
        raise HTTPException(status_code=400, detail="max_logs_per_filter_max_1000")
    if max_sqd_block_span > 25000:
        raise HTTPException(status_code=400, detail="max_sqd_block_span_max_25000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        run_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        allow_external,
        confirm,
        min_swaps,
        max_candidates,
        max_window_blocks,
        max_sqd_calls,
        max_logs_total,
        max_logs_per_filter,
        max_sqd_block_span,
        timeout,
    )


@router.get("/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence-schema-plan")
@router.post("/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence-schema-plan")
async def rpc_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan(
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
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_candidates > 10:
        raise HTTPException(status_code=400, detail="max_candidates_max_10")
    if max_window_blocks > 25000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_25000")
    if max_sqd_calls > 100:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_100")
    if max_logs_total > 10000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_10000")
    if max_logs_per_filter > 1000:
        raise HTTPException(status_code=400, detail="max_logs_per_filter_max_1000")
    if max_sqd_block_span > 25000:
        raise HTTPException(status_code=400, detail="max_sqd_block_span_max_25000")
    return await asyncio.to_thread(
        get_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        min_swaps,
        max_candidates,
        max_window_blocks,
        max_sqd_calls,
        max_logs_total,
        max_logs_per_filter,
        max_sqd_block_span,
    )


@router.post("/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence/insert")
async def rpc_insert_manipulation_detection_source_backed_top_expansion_raw_context_evidence(
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
    _: None = Depends(_require_data_admin),
):
    if allow_external and dry_run and confirm not in {
        "RUN_TOP_EXPANSION_RAW_CONTEXT_LOOKUP",
        "PREVIEW_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_INSERT",
        "INSERT_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE",
    }:
        raise HTTPException(status_code=400, detail="confirm_PREVIEW_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_INSERT_required")
    if not dry_run and confirm != "INSERT_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_required")
    if not dry_run and not expected_raw_context_lookup_digest:
        raise HTTPException(status_code=400, detail="expected_raw_context_lookup_digest_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if min_swaps > 50:
        raise HTTPException(status_code=400, detail="min_swaps_max_50")
    if max_candidates > 10:
        raise HTTPException(status_code=400, detail="max_candidates_max_10")
    if max_window_blocks > 25000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_25000")
    if max_sqd_calls > 100:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_100")
    if max_logs_total > 10000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_10000")
    if max_logs_per_filter > 1000:
        raise HTTPException(status_code=400, detail="max_logs_per_filter_max_1000")
    if max_sqd_block_span > 25000:
        raise HTTPException(status_code=400, detail="max_sqd_block_span_max_25000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        insert_manipulation_detection_source_backed_top_expansion_raw_context_evidence,
        chain,
        pool_address,
        token_address,
        limit,
        dry_run,
        allow_external,
        confirm,
        expected_raw_context_lookup_digest,
        min_swaps,
        max_candidates,
        max_window_blocks,
        max_sqd_calls,
        max_logs_total,
        max_logs_per_filter,
        max_sqd_block_span,
        timeout,
    )


@router.get("/rpc/manipulation-detection-exact-swap-collection-plan")
@router.post("/rpc/manipulation-detection-exact-swap-collection-plan")
async def rpc_manipulation_detection_exact_swap_collection_plan(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_manipulation_detection_exact_swap_collection_plan,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-exact-swap-second-window-plan")
@router.post("/rpc/manipulation-detection-exact-swap-second-window-plan")
async def rpc_manipulation_detection_exact_swap_second_window_plan(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_manipulation_detection_exact_swap_second_window_plan,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-raw-swap-repeatability-review")
@router.post("/rpc/manipulation-detection-raw-swap-repeatability-review")
async def rpc_manipulation_detection_raw_swap_repeatability_review(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_manipulation_detection_raw_swap_repeatability_review,
        chain,
        pool_address,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-transfer-context-collection-plan")
@router.post("/rpc/manipulation-detection-transfer-context-collection-plan")
async def rpc_manipulation_detection_transfer_context_collection_plan(
    chain: str | None = "bsc",
    limit: int = 3,
    max_windows: int = 8,
    max_receipt_samples: int = 12,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_windows > 20:
        raise HTTPException(status_code=400, detail="max_windows_max_20")
    if max_receipt_samples > 50:
        raise HTTPException(status_code=400, detail="max_receipt_samples_max_50")
    return await asyncio.to_thread(
        get_manipulation_detection_transfer_context_collection_plan,
        chain,
        limit,
        max_windows,
        max_receipt_samples,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-transfer-context-lookup-dry-run")
@router.post("/rpc/manipulation-detection-transfer-context-lookup-dry-run")
async def rpc_manipulation_detection_transfer_context_lookup_dry_run(
    chain: str | None = "bsc",
    limit: int = 3,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 10,
    max_logs_total: int = 500,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if allow_external and confirm != "RUN_MANIPULATION_TRANSFER_CONTEXT_LOOKUP":
        raise HTTPException(status_code=400, detail="confirm_RUN_MANIPULATION_TRANSFER_CONTEXT_LOOKUP_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 50:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_50")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        run_manipulation_detection_transfer_context_lookup_dry_run,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.get("/rpc/manipulation-detection-transfer-context-evidence-schema-plan")
@router.post("/rpc/manipulation-detection-transfer-context-evidence-schema-plan")
async def rpc_manipulation_detection_transfer_context_evidence_schema_plan(
    chain: str | None = "bsc",
    limit: int = 1,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 10,
    max_logs_total: int = 200,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if allow_external and confirm != "RUN_MANIPULATION_TRANSFER_CONTEXT_LOOKUP":
        raise HTTPException(status_code=400, detail="confirm_RUN_MANIPULATION_TRANSFER_CONTEXT_LOOKUP_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 50:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_50")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_manipulation_detection_transfer_context_evidence_schema_plan,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.post("/rpc/manipulation-detection-transfer-context-evidence/create")
async def rpc_create_manipulation_detection_transfer_context_evidence_table(
    chain: str | None = "bsc",
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    result = await asyncio.to_thread(
        create_manipulation_detection_transfer_context_evidence_table,
        chain,
        dry_run,
        confirm,
    )
    if not result.get("ok") and result.get("blockers"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/rpc/manipulation-detection-transfer-context-evidence/insert")
async def rpc_insert_manipulation_detection_transfer_context_evidence(
    chain: str | None = "bsc",
    limit: int = 1,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_transfer_context_insert_digest: str | None = None,
    max_sqd_calls: int = 10,
    max_logs_total: int = 200,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 50:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_50")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if not dry_run and not expected_transfer_context_insert_digest:
        raise HTTPException(status_code=400, detail="expected_transfer_context_insert_digest_required")
    result = await asyncio.to_thread(
        insert_manipulation_detection_transfer_context_evidence,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        expected_transfer_context_insert_digest,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )
    if not result.get("ok") and result.get("blockers"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/rpc/manipulation-detection-transfer-context-evidence/review")
@router.post("/rpc/manipulation-detection-transfer-context-evidence/review")
async def rpc_manipulation_detection_transfer_context_evidence_review(
    chain: str | None = "bsc",
    status: str | None = "pending_admin_review",
    limit: int = 200,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit_max_500")
    return await asyncio.to_thread(
        get_manipulation_detection_transfer_context_evidence_review_queue,
        chain,
        status,
        limit,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-transfer-context-evidence/reliability-bridge-preview")
@router.post("/rpc/manipulation-detection-transfer-context-evidence/reliability-bridge-preview")
async def rpc_manipulation_detection_transfer_context_reliability_bridge_preview(
    chain: str | None = "bsc",
    status: str | None = "pending_admin_review",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_manipulation_detection_transfer_context_reliability_bridge_preview,
        chain,
        status,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-transfer-context-evidence/reliability-bridge-apply-contract")
@router.post("/rpc/manipulation-detection-transfer-context-evidence/reliability-bridge-apply-contract")
async def rpc_manipulation_detection_transfer_context_reliability_bridge_apply_contract(
    chain: str | None = "bsc",
    status: str | None = "pending_admin_review",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_manipulation_detection_transfer_context_reliability_bridge_apply_contract,
        chain,
        status,
        dry_run,
    )


@router.get("/rpc/manipulation-detection-exact-swap-second-window-sqd-lookup-dry-run")
@router.post("/rpc/manipulation-detection-exact-swap-second-window-sqd-lookup-dry-run")
async def rpc_manipulation_detection_exact_swap_second_window_sqd_lookup_dry_run(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 4,
    max_logs_total: int = 500,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if allow_external and confirm != "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP":
        raise HTTPException(status_code=400, detail="confirm_RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 10:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_10")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        run_manipulation_detection_exact_swap_second_window_sqd_lookup_dry_run,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.get("/rpc/manipulation-detection-second-window-raw-swap-evidence-schema-plan")
@router.post("/rpc/manipulation-detection-second-window-raw-swap-evidence-schema-plan")
async def rpc_manipulation_detection_second_window_raw_swap_evidence_schema_plan(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 4,
    max_logs_total: int = 500,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if allow_external and confirm != "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP":
        raise HTTPException(status_code=400, detail="confirm_RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 10:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_10")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_manipulation_detection_second_window_raw_swap_evidence_schema_plan,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.post("/rpc/manipulation-detection-second-window-raw-swap-evidence/insert")
async def rpc_insert_manipulation_detection_second_window_raw_swap_evidence(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_second_window_raw_swap_insert_digest: str | None = None,
    max_sqd_calls: int = 4,
    max_logs_total: int = 500,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    preview_confirms = {
        "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP",
        "PREVIEW_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE_INSERT",
        "INSERT_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE",
    }
    if dry_run and allow_external and confirm not in preview_confirms:
        raise HTTPException(status_code=400, detail="confirm_PREVIEW_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE_INSERT_required")
    if not dry_run and confirm != "INSERT_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_MANIPULATION_SECOND_WINDOW_RAW_SWAP_EVIDENCE_required")
    if not dry_run and not expected_second_window_raw_swap_insert_digest:
        raise HTTPException(status_code=400, detail="expected_second_window_raw_swap_insert_digest_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 10:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_10")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        insert_manipulation_detection_second_window_raw_swap_evidence,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        expected_second_window_raw_swap_insert_digest,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.get("/rpc/manipulation-detection-exact-swap-sqd-lookup-dry-run")
@router.post("/rpc/manipulation-detection-exact-swap-sqd-lookup-dry-run")
async def rpc_manipulation_detection_exact_swap_sqd_lookup_dry_run(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 2,
    max_logs_total: int = 500,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if allow_external and confirm != "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP":
        raise HTTPException(status_code=400, detail="confirm_RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 10:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_10")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        run_manipulation_detection_exact_swap_sqd_lookup_dry_run,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.get("/rpc/manipulation-detection-raw-swap-evidence-schema-plan")
@router.post("/rpc/manipulation-detection-raw-swap-evidence-schema-plan")
async def rpc_manipulation_detection_raw_swap_evidence_schema_plan(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 2,
    max_logs_total: int = 500,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if allow_external and confirm != "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP":
        raise HTTPException(status_code=400, detail="confirm_RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 10:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_10")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_manipulation_detection_raw_swap_evidence_persistence_schema_plan,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.post("/rpc/manipulation-detection-raw-swap-evidence/insert")
async def rpc_insert_manipulation_detection_raw_swap_evidence(
    chain: str | None = "bsc",
    limit: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_raw_swap_insert_digest: str | None = None,
    max_sqd_calls: int = 2,
    max_logs_total: int = 500,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if allow_external and dry_run and confirm not in {
        "RUN_MANIPULATION_EXACT_SWAP_SQD_LOOKUP",
        "PREVIEW_MANIPULATION_RAW_SWAP_EVIDENCE_INSERT",
        "INSERT_MANIPULATION_RAW_SWAP_EVIDENCE",
    }:
        raise HTTPException(status_code=400, detail="confirm_PREVIEW_MANIPULATION_RAW_SWAP_EVIDENCE_INSERT_required")
    if not dry_run and confirm != "INSERT_MANIPULATION_RAW_SWAP_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_MANIPULATION_RAW_SWAP_EVIDENCE_required")
    if not dry_run and not expected_raw_swap_insert_digest:
        raise HTTPException(status_code=400, detail="expected_raw_swap_insert_digest_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_sqd_calls > 10:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_10")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        insert_manipulation_detection_raw_swap_evidence,
        chain,
        limit,
        dry_run,
        allow_external,
        confirm,
        expected_raw_swap_insert_digest,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.get("/rpc/amount-usd-normalization-and-token-identity-audit")
@router.post("/rpc/amount-usd-normalization-and-token-identity-audit")
async def rpc_amount_usd_normalization_and_token_identity_audit(
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_amount_usd_normalization_and_token_identity_audit,
        limit,
        dry_run,
    )


@router.get("/rpc/amount-usd-recompute-plan")
@router.post("/rpc/amount-usd-recompute-plan")
async def rpc_amount_usd_recompute_plan(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_amount_usd_recompute_plan,
        limit,
        dry_run,
    )


@router.get("/rpc/amount-usd-quarantine-gate")
@router.post("/rpc/amount-usd-quarantine-gate")
async def rpc_amount_usd_quarantine_gate(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_amount_usd_quarantine_gate,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated-schema-plan")
@router.post("/rpc/dex-trades-curated-schema-plan")
async def rpc_dex_trades_curated_schema_plan(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_schema_plan,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-raw-log-provenance-drilldown")
@router.post("/rpc/dex-trades-raw-log-provenance-drilldown")
async def rpc_dex_trades_raw_log_provenance_drilldown(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_raw_log_provenance_drilldown,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-bounded-receipt-replay-plan")
@router.post("/rpc/dex-trades-bounded-receipt-replay-plan")
async def rpc_dex_trades_bounded_receipt_replay_plan(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_bounded_receipt_replay_plan,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-receipt-parser-preview")
@router.post("/rpc/dex-trades-receipt-parser-preview")
async def rpc_dex_trades_receipt_parser_preview(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_receipt_parser_preview,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-mock-receipt-parser-test")
@router.post("/rpc/dex-trades-mock-receipt-parser-test")
async def rpc_dex_trades_mock_receipt_parser_test(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_mock_receipt_parser_test,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trade-raw-swap-provenance-schema-plan")
@router.post("/rpc/dex-trade-raw-swap-provenance-schema-plan")
async def rpc_dex_trade_raw_swap_provenance_schema_plan(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trade_raw_swap_provenance_schema_plan,
        limit,
        dry_run,
    )


@router.post("/rpc/dex-trade-raw-swap-provenance/create")
async def rpc_create_dex_trade_raw_swap_provenance(
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    result = await asyncio.to_thread(
        create_dex_trade_raw_swap_provenance,
        dry_run,
        confirm,
    )
    if not result.get("ok") and result.get("blockers"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/rpc/dex-trade-raw-swap-provenance/replay-insert-plan")
@router.post("/rpc/dex-trade-raw-swap-provenance/replay-insert-plan")
async def rpc_dex_trade_raw_swap_provenance_replay_insert_plan(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trade_raw_swap_provenance_replay_insert_plan,
        limit,
        dry_run,
    )


@router.post("/rpc/dex-trade-raw-swap-provenance/replay-insert/apply")
async def rpc_dex_trade_raw_swap_provenance_replay_insert_apply(
    limit: int = 25,
    expected_receipt_count: int | None = None,
    expected_insert_count: int | None = None,
    expected_chain: str | None = None,
    expected_max_rpc_calls: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    result = await asyncio.to_thread(
        replay_and_insert_dex_trade_raw_swap_provenance,
        limit,
        expected_receipt_count,
        expected_insert_count,
        expected_chain,
        expected_max_rpc_calls,
        dry_run,
        confirm,
    )
    if not result.get("ok") and result.get("blockers"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/rpc/dex-trade-raw-swap-provenance/review")
@router.post("/rpc/dex-trade-raw-swap-provenance/review")
async def rpc_dex_trade_raw_swap_provenance_review(
    status: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trade_raw_swap_provenance_review,
        status,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated-from-raw-provenance-schema-plan")
@router.post("/rpc/dex-trades-curated-from-raw-provenance-schema-plan")
async def rpc_dex_trades_curated_from_raw_provenance_schema_plan(
    status: str | None = "matched",
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_from_raw_provenance_schema_plan,
        status,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-raw-provenance-amount-decode-preview")
@router.post("/rpc/dex-trades-raw-provenance-amount-decode-preview")
async def rpc_dex_trades_raw_provenance_amount_decode_preview(
    status: str | None = "matched",
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_raw_provenance_amount_decode_preview,
        status,
        limit,
        dry_run,
    )


@router.post("/rpc/dex-trades-curated/create")
async def rpc_dex_trades_curated_create(
    limit: int = 50,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    result = await asyncio.to_thread(
        create_dex_trades_curated,
        limit,
        dry_run,
        confirm,
    )
    if not result.get("ok") and result.get("blockers"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/rpc/dex-trades-curated/insert")
async def rpc_dex_trades_curated_insert(
    limit: int = 50,
    expected_insert_count: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    result = await asyncio.to_thread(
        insert_dex_trades_curated_from_raw_provenance,
        limit,
        expected_insert_count,
        dry_run,
        confirm,
    )
    if not result.get("ok") and result.get("blockers"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/rpc/dex-trades-curated/review")
@router.post("/rpc/dex-trades-curated/review")
async def rpc_dex_trades_curated_review(
    curation_status: str | None = "raw_provenance_decoded",
    token_symbol: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_review,
        curation_status,
        token_symbol,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated/shadow-scoring-plan")
@router.post("/rpc/dex-trades-curated/shadow-scoring-plan")
async def rpc_dex_trades_curated_shadow_scoring_plan(
    token_symbol: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_shadow_scoring_plan,
        token_symbol,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated/shadow-casefile")
@router.post("/rpc/dex-trades-curated/shadow-casefile")
async def rpc_dex_trades_curated_shadow_casefile(
    token_symbol: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_shadow_casefile,
        token_symbol,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated/unknown-route-repair-plan")
@router.post("/rpc/dex-trades-curated/unknown-route-repair-plan")
async def rpc_dex_trades_curated_unknown_route_repair_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_unknown_route_repair_plan,
        token_symbol,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated/source-backed-backtest-preview")
@router.post("/rpc/dex-trades-curated/source-backed-backtest-preview")
async def rpc_dex_trades_curated_source_backed_backtest_preview(
    token_symbol: str | None = None,
    chain: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_source_backed_backtest_preview,
        token_symbol,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated/source-backed-token-ranking")
@router.post("/rpc/dex-trades-curated/source-backed-token-ranking")
async def rpc_dex_trades_curated_source_backed_token_ranking(
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_source_backed_token_ranking,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated/source-backed-collection-plan")
@router.post("/rpc/dex-trades-curated/source-backed-collection-plan")
async def rpc_dex_trades_curated_source_backed_collection_plan(
    chain: str | None = None,
    limit: int = 25,
    max_tokens: int = 5,
    min_source_backed_rows: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_tokens > 10:
        raise HTTPException(status_code=400, detail="max_tokens_max_10")
    if min_source_backed_rows > 100:
        raise HTTPException(status_code=400, detail="min_source_backed_rows_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_source_backed_collection_plan,
        chain,
        limit,
        max_tokens,
        min_source_backed_rows,
        dry_run,
    )


@router.get("/rpc/dex-trades-curated/source-backed-history-collection-plan")
@router.post("/rpc/dex-trades-curated/source-backed-history-collection-plan")
async def rpc_dex_trades_curated_source_backed_history_collection_plan(
    chain: str | None = None,
    token_symbol: str | None = None,
    limit: int = 25,
    max_tokens: int = 3,
    window_radius_blocks: int = 2,
    max_blocks: int = 12,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_tokens > 10:
        raise HTTPException(status_code=400, detail="max_tokens_max_10")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 50:
        raise HTTPException(status_code=400, detail="max_blocks_max_50")
    return await asyncio.to_thread(
        get_dex_trades_curated_source_backed_history_collection_plan,
        chain,
        token_symbol,
        limit,
        max_tokens,
        window_radius_blocks,
        max_blocks,
        dry_run,
    )


@router.post("/rpc/dex-trades-curated/source-backed-history-collection/apply")
async def rpc_dex_trades_curated_source_backed_history_collection_apply(
    chain: str | None = None,
    token_symbol: str | None = None,
    limit: int = 25,
    max_tokens: int = 3,
    window_radius_blocks: int = 2,
    max_blocks: int = 12,
    dry_run: bool = True,
    confirm: str | None = None,
    max_receipts_per_block: int | None = None,
    max_seconds_per_block: float | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_tokens > 10:
        raise HTTPException(status_code=400, detail="max_tokens_max_10")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 50:
        raise HTTPException(status_code=400, detail="max_blocks_max_50")
    if max_receipts_per_block is not None and max_receipts_per_block > 500:
        raise HTTPException(status_code=400, detail="max_receipts_per_block_max_500")
    if max_seconds_per_block is not None and max_seconds_per_block > 120:
        raise HTTPException(status_code=400, detail="max_seconds_per_block_max_120")
    return await asyncio.to_thread(
        run_dex_trades_curated_source_backed_history_collection,
        chain,
        token_symbol,
        limit,
        max_tokens,
        window_radius_blocks,
        max_blocks,
        dry_run,
        confirm,
        max_receipts_per_block,
        max_seconds_per_block,
    )


@router.get("/rpc/dex-trades-curated/source-backed-transfer-context-plan")
@router.post("/rpc/dex-trades-curated/source-backed-transfer-context-plan")
async def rpc_dex_trades_curated_source_backed_transfer_context_plan(
    chain: str | None = None,
    limit: int = 25,
    max_tokens: int = 5,
    min_source_backed_rows: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_tokens > 10:
        raise HTTPException(status_code=400, detail="max_tokens_max_10")
    if min_source_backed_rows > 100:
        raise HTTPException(status_code=400, detail="min_source_backed_rows_max_100")
    return await asyncio.to_thread(
        get_dex_trades_curated_source_backed_transfer_context_plan,
        chain,
        limit,
        max_tokens,
        min_source_backed_rows,
        dry_run,
    )


@router.post("/rpc/dex-trades-curated/source-backed-transfer-context/apply")
async def rpc_dex_trades_curated_source_backed_transfer_context_apply(
    chain: str | None = None,
    limit: int = 25,
    max_tokens: int = 5,
    min_source_backed_rows: int = 5,
    expected_target_count: int | None = None,
    expected_chain: str | None = None,
    expected_max_rpc_calls: int | None = None,
    expected_min_token_transfers: int | None = None,
    expected_max_token_transfers: int | None = None,
    expected_transfer_context_repair_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_tokens > 10:
        raise HTTPException(status_code=400, detail="max_tokens_max_10")
    if min_source_backed_rows > 100:
        raise HTTPException(status_code=400, detail="min_source_backed_rows_max_100")
    return await asyncio.to_thread(
        collect_token_transfer_context_from_receipts,
        chain,
        limit,
        max_tokens,
        min_source_backed_rows,
        expected_target_count,
        expected_chain,
        expected_max_rpc_calls,
        expected_min_token_transfers,
        expected_max_token_transfers,
        expected_transfer_context_repair_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-trades-curated/expansion-collection-plan")
@router.post("/rpc/dex-trades-curated/expansion-collection-plan")
async def rpc_dex_trades_curated_expansion_collection_plan(
    token_symbol: str | None = None,
    limit: int = 25,
    max_tokens: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_tokens > 10:
        raise HTTPException(status_code=400, detail="max_tokens_max_10")
    return await asyncio.to_thread(
        get_dex_trades_curated_expansion_collection_plan,
        token_symbol,
        limit,
        max_tokens,
        dry_run,
    )


@router.post("/rpc/dex-trades-curated/expansion-replay/apply")
async def rpc_dex_trades_curated_expansion_replay_apply(
    token_symbol: str | None = None,
    limit: int = 25,
    max_tokens: int = 3,
    expected_target_count: int | None = None,
    expected_insert_count: int | None = None,
    expected_chain: str | None = None,
    expected_max_rpc_calls: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_tokens > 10:
        raise HTTPException(status_code=400, detail="max_tokens_max_10")
    result = await asyncio.to_thread(
        replay_and_insert_dex_trades_curated_expansion_raw_provenance,
        token_symbol,
        limit,
        max_tokens,
        expected_target_count,
        expected_insert_count,
        expected_chain,
        expected_max_rpc_calls,
        dry_run,
        confirm,
    )
    if not result.get("ok") and result.get("blockers"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/rpc/dex-trades-amount-decode-metadata-repair-plan")
@router.post("/rpc/dex-trades-amount-decode-metadata-repair-plan")
async def rpc_dex_trades_amount_decode_metadata_repair_plan(
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_trades_amount_decode_metadata_repair_plan,
        limit,
        dry_run,
    )


@router.post("/rpc/dex-trades-amount-decode-metadata-repair")
async def rpc_dex_trades_amount_decode_metadata_repair(
    limit: int = 50,
    expected_token_count: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    max_seconds: int = 45,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    if max_seconds > 180:
        raise HTTPException(status_code=400, detail="max_seconds_max_180")
    return await asyncio.to_thread(
        repair_dex_trades_amount_decode_token_metadata,
        limit,
        expected_token_count,
        dry_run,
        confirm,
        max_seconds,
    )


@router.post("/rpc/amount-usd-stablecoin-side-recompute/apply")
async def rpc_amount_usd_stablecoin_side_recompute_apply(
    limit: int = 25,
    expected_recompute_count: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    result = await asyncio.to_thread(
        apply_amount_usd_stablecoin_side_recompute,
        limit,
        expected_recompute_count,
        dry_run,
        confirm,
    )
    if not result.get("ok") and result.get("blockers"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/rpc/token-market-discovery-candidate-schema")
async def rpc_token_market_discovery_candidate_schema(
    token_symbol: str | None = None,
    chain: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(token_symbol or "").strip():
        raise HTTPException(status_code=400, detail="token_symbol_required")
    return await asyncio.to_thread(
        get_token_market_discovery_candidate_schema,
        token_symbol,
        chain,
        dry_run,
    )


@router.post("/rpc/token-market-discovery-candidates-schema-plan")
async def rpc_token_market_discovery_candidates_schema_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if not str(token_symbol or "").strip():
        raise HTTPException(status_code=400, detail="token_symbol_required")
    return await asyncio.to_thread(
        get_token_market_discovery_candidates_schema_plan,
        token_symbol,
        chain,
        dry_run,
    )


@router.post("/rpc/token-market-discovery-candidates/create")
async def rpc_create_token_market_discovery_candidates(
    token_symbol: str | None = None,
    chain: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not str(token_symbol or "").strip():
        raise HTTPException(status_code=400, detail="token_symbol_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_DISCOVERY_CANDIDATES_TABLE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_DISCOVERY_CANDIDATES_TABLE_required",
        )
    return await asyncio.to_thread(
        create_token_market_discovery_candidates,
        token_symbol,
        chain,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-manual-candidates/insert")
async def rpc_insert_token_market_manual_candidates(
    payload: Any = Body(default=None),
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    body = payload if isinstance(payload, dict) else {}
    candidates = body.get("candidates") if isinstance(body.get("candidates"), list) else []
    expected_keys = body.get("expected_manual_candidate_dedupe_keys")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_MANUAL_CANDIDATES":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_MANUAL_CANDIDATES_required",
        )
    if not dry_run and not expected_keys:
        raise HTTPException(
            status_code=400,
            detail="expected_manual_candidate_dedupe_keys_required",
        )
    return await asyncio.to_thread(
        insert_token_market_manual_candidates,
        candidates,
        expected_keys,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-discovery-candidates/insert")
async def rpc_insert_token_market_discovery_candidate(
    token_symbol: str | None = None,
    chain: str | None = None,
    market_type: str | None = None,
    venue_name: str | None = None,
    pair: str | None = None,
    base_asset: str | None = None,
    quote_asset: str | None = None,
    token_contract: str | None = None,
    pool_or_pair_address: str | None = None,
    router_or_factory_address: str | None = None,
    source_url: str | None = None,
    source_tier: str | None = None,
    evidence_type: str | None = None,
    observed_volume_24h: float | None = None,
    observed_liquidity: float | None = None,
    observed_at: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not str(token_symbol or "").strip():
        raise HTTPException(status_code=400, detail="token_symbol_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_DISCOVERY_CANDIDATE":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_DISCOVERY_CANDIDATE_required",
        )
    return await asyncio.to_thread(
        insert_token_market_discovery_candidate,
        token_symbol,
        chain,
        market_type,
        venue_name,
        pair,
        base_asset,
        quote_asset,
        token_contract,
        pool_or_pair_address,
        router_or_factory_address,
        source_url,
        source_tier,
        evidence_type,
        observed_volume_24h,
        observed_liquidity,
        observed_at,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-discovery-candidates/review-queue")
async def rpc_token_market_discovery_candidate_review_queue(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_discovery_candidate_review_queue,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-policy-engine/shadow-evaluation")
@router.post("/rpc/token-market-policy-engine/shadow-evaluation")
async def rpc_token_market_policy_engine_shadow_evaluation(
    limit: int = 3,
    include_radar: bool = True,
    include_candidates: bool = True,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_policy_engine_shadow_evaluation,
        limit,
        include_radar,
        include_candidates,
        dry_run,
    )


@router.get("/rpc/token-market-router-exclusion-shadow-scoring")
@router.post("/rpc/token-market-router-exclusion-shadow-scoring")
async def rpc_token_market_router_exclusion_shadow_scoring(
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_token_market_router_exclusion_shadow_scoring,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-local-candidate-source-repair-plan")
@router.post("/rpc/token-market-local-candidate-source-repair-plan")
async def rpc_token_market_local_candidate_source_repair_plan(
    limit: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_token_market_local_candidate_source_repair_plan,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-local-candidate-source-venue-evidence")
@router.post("/rpc/token-market-local-candidate-source-venue-evidence")
async def rpc_token_market_local_candidate_source_venue_evidence(
    limit: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_token_market_local_candidate_source_venue_evidence,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-local-candidate-official-source-proof-plan")
@router.post("/rpc/token-market-local-candidate-official-source-proof-plan")
async def rpc_token_market_local_candidate_official_source_proof_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_token_market_local_candidate_official_source_proof_plan,
        token_symbol,
        chain,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-local-universe-audit")
@router.post("/rpc/token-market-local-universe-audit")
async def rpc_token_market_local_universe_audit(
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(
        get_token_market_local_universe_audit,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-data-coverage-expansion-plan")
@router.post("/rpc/token-market-data-coverage-expansion-plan")
async def rpc_token_market_data_coverage_expansion_plan(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_token_market_data_coverage_expansion_plan,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-drilldown")
@router.post("/rpc/token-market-top-research-lead-drilldown")
async def rpc_token_market_top_research_lead_drilldown(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_drilldown,
        token_symbol,
        chain,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-source-venue-repair-plan")
@router.post("/rpc/token-market-top-research-lead-source-venue-repair-plan")
async def rpc_token_market_top_research_lead_source_venue_repair_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_source_venue_repair_plan,
        token_symbol,
        chain,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-source-venue-proof-acquisition-plan")
@router.post("/rpc/token-market-top-research-lead-source-venue-proof-acquisition-plan")
async def rpc_token_market_top_research_lead_source_venue_proof_acquisition_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_source_venue_proof_acquisition_plan,
        token_symbol,
        chain,
        token_address,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-unknown-router-identity-drilldown")
@router.post("/rpc/token-market-top-research-lead-unknown-router-identity-drilldown")
async def rpc_token_market_top_research_lead_unknown_router_identity_drilldown(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    router_limit: int = 20,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if router_limit > 50:
        raise HTTPException(status_code=400, detail="router_limit_max_50")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_unknown_router_identity_drilldown,
        token_symbol,
        chain,
        token_address,
        limit,
        router_limit,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-router-source-route-repair-plan")
@router.post("/rpc/token-market-top-research-lead-router-source-route-repair-plan")
async def rpc_token_market_top_research_lead_router_source_route_repair_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    router_limit: int = 20,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if router_limit > 50:
        raise HTTPException(status_code=400, detail="router_limit_max_50")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_router_source_route_repair_plan,
        token_symbol,
        chain,
        token_address,
        limit,
        router_limit,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-router-role-checkpoint")
@router.post("/rpc/token-market-top-research-lead-router-role-checkpoint")
async def rpc_token_market_top_research_lead_router_role_checkpoint(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    router_limit: int = 20,
    include_official: bool = False,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if router_limit > 50:
        raise HTTPException(status_code=400, detail="router_limit_max_50")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_router_role_checkpoint,
        token_symbol,
        chain,
        token_address,
        limit,
        router_limit,
        include_official,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-route-trace-sample-plan")
@router.post("/rpc/token-market-top-research-lead-route-trace-sample-plan")
async def rpc_token_market_top_research_lead_route_trace_sample_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    router_limit: int = 20,
    sample_limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if router_limit > 50:
        raise HTTPException(status_code=400, detail="router_limit_max_50")
    if sample_limit > 10:
        raise HTTPException(status_code=400, detail="sample_limit_max_10")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_route_trace_sample_plan,
        token_symbol,
        chain,
        token_address,
        limit,
        router_limit,
        sample_limit,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-bounded-route-trace-preview")
@router.post("/rpc/token-market-top-research-lead-bounded-route-trace-preview")
async def rpc_token_market_top_research_lead_bounded_route_trace_preview(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    router_limit: int = 20,
    sample_limit: int = 3,
    max_trace_calls: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if router_limit > 50:
        raise HTTPException(status_code=400, detail="router_limit_max_50")
    if sample_limit > 10:
        raise HTTPException(status_code=400, detail="sample_limit_max_10")
    if max_trace_calls > 25:
        raise HTTPException(status_code=400, detail="max_trace_calls_max_25")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_bounded_route_trace_preview,
        token_symbol,
        chain,
        token_address,
        limit,
        router_limit,
        sample_limit,
        max_trace_calls,
        dry_run,
    )


@router.get("/rpc/token-market-top-research-lead-bounded-route-trace-execution")
@router.post("/rpc/token-market-top-research-lead-bounded-route-trace-execution")
async def rpc_token_market_top_research_lead_bounded_route_trace_execution(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    router_limit: int = 20,
    sample_limit: int = 3,
    max_trace_calls: int = 5,
    max_calls_per_tx: int = 80,
    dry_run: bool = True,
    trace_enabled: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if router_limit > 50:
        raise HTTPException(status_code=400, detail="router_limit_max_50")
    if sample_limit > 10:
        raise HTTPException(status_code=400, detail="sample_limit_max_10")
    if max_trace_calls > 10:
        raise HTTPException(status_code=400, detail="max_trace_calls_max_10")
    if max_calls_per_tx > 200:
        raise HTTPException(status_code=400, detail="max_calls_per_tx_max_200")
    return await asyncio.to_thread(
        run_token_market_top_research_lead_bounded_route_trace_execution,
        token_symbol,
        chain,
        token_address,
        limit,
        router_limit,
        sample_limit,
        max_trace_calls,
        max_calls_per_tx,
        dry_run,
        trace_enabled,
        confirm,
    )


@router.get("/rpc/token-market-top-research-lead-trace-source-repair-plan")
@router.post("/rpc/token-market-top-research-lead-trace-source-repair-plan")
async def rpc_token_market_top_research_lead_trace_source_repair_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    router_limit: int = 20,
    sample_limit: int = 3,
    max_trace_calls: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if router_limit > 50:
        raise HTTPException(status_code=400, detail="router_limit_max_50")
    if sample_limit > 10:
        raise HTTPException(status_code=400, detail="sample_limit_max_10")
    if max_trace_calls > 25:
        raise HTTPException(status_code=400, detail="max_trace_calls_max_25")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_trace_source_repair_plan,
        token_symbol,
        chain,
        token_address,
        limit,
        router_limit,
        sample_limit,
        max_trace_calls,
        dry_run,
    )


@router.post("/rpc/token-market-fresh-forward-bsc-collection-trace")
async def rpc_token_market_fresh_forward_bsc_collection_trace(
    chain: str = "bsc",
    count: int = 1,
    confirmations: int = 2,
    max_receipts_per_block: int = 120,
    max_seconds_per_block: float = 45,
    max_trace_calls: int = 5,
    max_calls_per_tx: int = 80,
    dry_run: bool = True,
    trace_enabled: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if count > 5:
        raise HTTPException(status_code=400, detail="count_max_5")
    if confirmations > 20:
        raise HTTPException(status_code=400, detail="confirmations_max_20")
    if max_receipts_per_block > 200:
        raise HTTPException(status_code=400, detail="max_receipts_per_block_max_200")
    if max_seconds_per_block > 120:
        raise HTTPException(status_code=400, detail="max_seconds_per_block_max_120")
    if max_trace_calls > 10:
        raise HTTPException(status_code=400, detail="max_trace_calls_max_10")
    if max_calls_per_tx > 200:
        raise HTTPException(status_code=400, detail="max_calls_per_tx_max_200")
    return await asyncio.to_thread(
        run_token_market_fresh_forward_bsc_collection_trace,
        chain,
        count,
        confirmations,
        max_receipts_per_block,
        max_seconds_per_block,
        max_trace_calls,
        max_calls_per_tx,
        dry_run,
        trace_enabled,
        confirm,
    )


@router.get("/rpc/token-market-recent-router-pool-evidence-review")
@router.post("/rpc/token-market-recent-router-pool-evidence-review")
async def rpc_token_market_recent_router_pool_evidence_review(
    chain: str = "bsc",
    block_window: int = 50,
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 10_000:
        raise HTTPException(status_code=400, detail="block_window_max_10000")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_token_market_recent_router_pool_evidence_review,
        chain,
        block_window,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-metadata-aware-fresh-lead-ranking")
@router.post("/rpc/token-market-metadata-aware-fresh-lead-ranking")
async def rpc_token_market_metadata_aware_fresh_lead_ranking(
    chain: str = "bsc",
    block_window: int = 50,
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 10_000:
        raise HTTPException(status_code=400, detail="block_window_max_10000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_token_market_metadata_aware_fresh_lead_ranking,
        chain,
        block_window,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-recent-unknown-router-source-repair-plan")
@router.post("/rpc/token-market-recent-unknown-router-source-repair-plan")
async def rpc_token_market_recent_unknown_router_source_repair_plan(
    chain: str = "bsc",
    block_window: int = 10_000,
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 10_000:
        raise HTTPException(status_code=400, detail="block_window_max_10000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_token_market_recent_unknown_router_source_repair_plan,
        chain,
        block_window,
        limit,
        dry_run,
    )


@router.get("/rpc/token-market-top-unknown-router-source-trace-plan")
@router.post("/rpc/token-market-top-unknown-router-source-trace-plan")
async def rpc_token_market_top_unknown_router_source_trace_plan(
    chain: str = "bsc",
    block_window: int = 10_000,
    limit: int = 10,
    router_addr: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 10_000:
        raise HTTPException(status_code=400, detail="block_window_max_10000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_token_market_top_unknown_router_source_trace_plan,
        chain,
        block_window,
        limit,
        router_addr,
        dry_run,
    )


@router.get("/rpc/token-market-top-unknown-router-bounded-history-collection-plan")
@router.post("/rpc/token-market-top-unknown-router-bounded-history-collection-plan")
async def rpc_token_market_top_unknown_router_bounded_history_collection_plan(
    chain: str = "bsc",
    block_window: int = 10_000,
    limit: int = 10,
    router_addr: str | None = None,
    window_radius_blocks: int = 2,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 10_000:
        raise HTTPException(status_code=400, detail="block_window_max_10000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    return await asyncio.to_thread(
        get_token_market_top_unknown_router_bounded_history_collection_plan,
        chain,
        block_window,
        limit,
        router_addr,
        window_radius_blocks,
        dry_run,
    )


@router.post("/rpc/token-market-top-unknown-router-bounded-history-collection")
async def rpc_token_market_top_unknown_router_bounded_history_collection(
    chain: str = "bsc",
    block_window: int = 10_000,
    limit: int = 10,
    router_addr: str | None = None,
    window_radius_blocks: int = 2,
    dry_run: bool = True,
    confirm: str | None = None,
    max_receipts_per_block: int | None = None,
    max_seconds_per_block: float | None = None,
    _: None = Depends(_require_data_admin),
):
    if block_window > 10_000:
        raise HTTPException(status_code=400, detail="block_window_max_10000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_receipts_per_block is not None and max_receipts_per_block > 200:
        raise HTTPException(status_code=400, detail="max_receipts_per_block_max_200")
    if max_seconds_per_block is not None and max_seconds_per_block > 120:
        raise HTTPException(status_code=400, detail="max_seconds_per_block_max_120")
    return await asyncio.to_thread(
        run_token_market_top_unknown_router_bounded_history_collection,
        chain,
        block_window,
        limit,
        router_addr,
        window_radius_blocks,
        dry_run,
        confirm,
        max_receipts_per_block,
        max_seconds_per_block,
    )


@router.get("/rpc/token-market-top-research-lead-bounded-history-collection-plan")
@router.post("/rpc/token-market-top-research-lead-bounded-history-collection-plan")
async def rpc_token_market_top_research_lead_bounded_history_collection_plan(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    window_radius_blocks: int = 2,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    return await asyncio.to_thread(
        get_token_market_top_research_lead_bounded_history_collection_plan,
        token_symbol,
        chain,
        token_address,
        limit,
        window_radius_blocks,
        dry_run,
    )


@router.post("/rpc/token-market-top-research-lead-bounded-history-collection")
async def rpc_token_market_top_research_lead_bounded_history_collection(
    token_symbol: str | None = None,
    chain: str | None = None,
    token_address: str | None = None,
    limit: int = 3,
    window_radius_blocks: int = 2,
    dry_run: bool = True,
    confirm: str | None = None,
    max_receipts_per_block: int | None = None,
    max_seconds_per_block: float | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_receipts_per_block is not None and max_receipts_per_block > 200:
        raise HTTPException(status_code=400, detail="max_receipts_per_block_max_200")
    if max_seconds_per_block is not None and max_seconds_per_block > 120:
        raise HTTPException(status_code=400, detail="max_seconds_per_block_max_120")
    return await asyncio.to_thread(
        run_token_market_top_research_lead_bounded_history_collection,
        token_symbol,
        chain,
        token_address,
        limit,
        window_radius_blocks,
        dry_run,
        confirm,
        max_receipts_per_block,
        max_seconds_per_block,
    )


@router.get("/rpc/autonomous-alpha-detection-fusion-policy")
@router.post("/rpc/autonomous-alpha-detection-fusion-policy")
async def rpc_autonomous_alpha_detection_fusion_policy(
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_autonomous_alpha_detection_fusion_policy,
        limit,
        dry_run,
    )


@router.get("/rpc/label-quality-repair-policy")
@router.post("/rpc/label-quality-repair-policy")
async def rpc_label_quality_repair_policy(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_quality_repair_policy,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair-preview")
@router.post("/rpc/label-source-gap-repair-preview")
async def rpc_label_source_gap_repair_preview(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_repair_preview,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/label-source-gap-repair/stage")
async def rpc_stage_label_source_gap_repair_candidates(
    payload: Any = Body(default=None),
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    body = payload if isinstance(payload, dict) else {}
    if body.get("entity") is not None:
        entity = body.get("entity")
    if body.get("chain") is not None:
        chain = body.get("chain")
    if body.get("limit") is not None:
        try:
            limit = int(body.get("limit"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="limit_must_be_integer")
    if body.get("dry_run") is not None:
        dry_run = bool(body.get("dry_run"))
    if body.get("confirm") is not None:
        confirm = str(body.get("confirm"))
    expected_keys = body.get("expected_repair_preview_dedupe_keys")
    if expected_keys is None:
        expected_keys = body.get("expected_keys")
    if expected_keys is not None and not isinstance(expected_keys, list):
        raise HTTPException(status_code=400, detail="expected_repair_preview_dedupe_keys_must_be_list")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if not dry_run and confirm != "STAGE_LABEL_SOURCE_GAP_REPAIR_CANDIDATES":
        raise HTTPException(
            status_code=400,
            detail="confirm_STAGE_LABEL_SOURCE_GAP_REPAIR_CANDIDATES_required",
        )
    if not dry_run and not expected_keys:
        raise HTTPException(status_code=400, detail="expected_repair_preview_dedupe_keys_required")
    return await asyncio.to_thread(
        stage_label_source_gap_repair_candidates,
        entity,
        chain,
        limit,
        expected_keys,
        dry_run,
        confirm,
    )


@router.get("/rpc/label-source-gap-repair/candidate-review")
@router.post("/rpc/label-source-gap-repair/candidate-review")
async def rpc_label_source_gap_candidate_review_queue(
    entity: str | None = None,
    chain: str | None = None,
    status: str | None = "candidate",
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_candidate_review_queue,
        entity,
        chain,
        status,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/corroboration-preview")
@router.post("/rpc/label-source-gap-repair/corroboration-preview")
async def rpc_label_source_gap_candidate_corroboration_preview(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_candidate_corroboration_preview,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/source-repair-plan")
@router.post("/rpc/label-source-gap-repair/source-repair-plan")
async def rpc_label_source_gap_source_repair_plan(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_source_repair_plan,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/weak-source-repair-queue")
@router.post("/rpc/label-source-gap-repair/weak-source-repair-queue")
async def rpc_label_source_gap_weak_source_repair_queue(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_weak_source_repair_queue,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/label-source-gap-repair/weak-source-corroboration-dry-run")
async def rpc_label_source_gap_weak_source_corroboration_dry_run(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 8,
    dry_run: bool = True,
    allow_external: bool = False,
    timeout: int = 12,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 8:
        raise HTTPException(status_code=400, detail="limit_max_8")
    if timeout > 20:
        raise HTTPException(status_code=400, detail="timeout_max_20")
    return await asyncio.to_thread(
        run_label_source_gap_weak_source_corroboration_dry_run,
        entity,
        chain,
        limit,
        dry_run,
        allow_external,
        timeout,
    )


@router.post("/rpc/label-source-gap-repair/source-replacement-intake-preview")
async def rpc_label_source_gap_source_replacement_intake_preview(
    payload: Any = Body(default=None),
    dry_run: bool = True,
    limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 8:
        raise HTTPException(status_code=400, detail="limit_max_8")
    replacements = payload.get("replacements") if isinstance(payload, dict) else payload
    return await asyncio.to_thread(
        get_label_source_gap_source_replacement_intake_preview,
        replacements,
        dry_run,
        limit,
    )


@router.get("/rpc/label-source-gap-repair/alternative-source-discovery-radar")
@router.post("/rpc/label-source-gap-repair/alternative-source-discovery-radar")
async def rpc_label_source_gap_alternative_source_discovery_radar(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 8,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 8:
        raise HTTPException(status_code=400, detail="limit_max_8")
    return await asyncio.to_thread(
        get_label_source_gap_alternative_source_discovery_radar,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/source-url-probe-contract")
@router.post("/rpc/label-source-gap-repair/source-url-probe-contract")
async def rpc_label_source_gap_source_url_probe_contract(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 8,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 8:
        raise HTTPException(status_code=400, detail="limit_max_8")
    return await asyncio.to_thread(
        get_label_source_gap_source_url_probe_contract,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/label-source-gap-repair/source-url-probe-dry-run")
async def rpc_label_source_gap_source_url_probe_dry_run(
    entity: str | None = None,
    chain: str | None = None,
    candidate_id: int | None = None,
    source_name: str | None = None,
    max_urls: int = 3,
    dry_run: bool = True,
    allow_external: bool = False,
    timeout: int = 6,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_urls > 5:
        raise HTTPException(status_code=400, detail="max_urls_max_5")
    if timeout > 8:
        raise HTTPException(status_code=400, detail="timeout_max_8")
    return await asyncio.to_thread(
        run_label_source_gap_source_url_probe_dry_run,
        entity,
        chain,
        candidate_id,
        source_name,
        max_urls,
        dry_run,
        allow_external,
        timeout,
    )


@router.get("/rpc/label-source-gap-repair/source-proof-grading-checkpoint")
@router.post("/rpc/label-source-gap-repair/source-proof-grading-checkpoint")
async def rpc_label_source_gap_source_proof_grading_checkpoint(
    source_name: str | None = "oklink_address_page",
    max_urls: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    timeout: int = 6,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_urls > 5:
        raise HTTPException(status_code=400, detail="max_urls_max_5")
    if timeout > 8:
        raise HTTPException(status_code=400, detail="timeout_max_8")
    return await asyncio.to_thread(
        get_label_source_gap_source_proof_grading_checkpoint,
        source_name,
        max_urls,
        dry_run,
        allow_external,
        timeout,
    )


@router.post("/rpc/label-source-gap-repair/source-replacement-evidence/apply")
async def rpc_persist_label_source_gap_source_replacement_evidence(
    source_name: str | None = "oklink_address_page",
    max_urls: int = 5,
    dry_run: bool = True,
    allow_external: bool = False,
    timeout: int = 6,
    confirm: str | None = None,
    expected_source_replacement_dedupe_keys: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if max_urls > 5:
        raise HTTPException(status_code=400, detail="max_urls_max_5")
    if timeout > 8:
        raise HTTPException(status_code=400, detail="timeout_max_8")
    if not dry_run and confirm != "PERSIST_LABEL_SOURCE_GAP_SOURCE_REPLACEMENT_EVIDENCE":
        raise HTTPException(
            status_code=400,
            detail="confirm_PERSIST_LABEL_SOURCE_GAP_SOURCE_REPLACEMENT_EVIDENCE_required",
        )
    return await asyncio.to_thread(
        persist_label_source_gap_source_replacement_evidence,
        source_name,
        max_urls,
        dry_run,
        allow_external,
        timeout,
        confirm,
        expected_source_replacement_dedupe_keys,
    )


@router.get("/rpc/label-source-gap-repair/second-source-checkpoint")
@router.post("/rpc/label-source-gap-repair/second-source-checkpoint")
async def rpc_label_source_gap_second_source_checkpoint(
    source_names: str | None = None,
    max_candidates: int = 3,
    max_sources_per_candidate: int = 2,
    dry_run: bool = True,
    allow_external: bool = False,
    timeout: int = 6,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_candidates > 3:
        raise HTTPException(status_code=400, detail="max_candidates_max_3")
    if max_sources_per_candidate > 4:
        raise HTTPException(status_code=400, detail="max_sources_per_candidate_max_4")
    if timeout > 8:
        raise HTTPException(status_code=400, detail="timeout_max_8")
    return await asyncio.to_thread(
        get_label_source_gap_second_source_checkpoint,
        source_names,
        max_candidates,
        max_sources_per_candidate,
        dry_run,
        allow_external,
        timeout,
    )


@router.get("/rpc/label-source-gap-repair/stronger-source-plan")
@router.post("/rpc/label-source-gap-repair/stronger-source-plan")
async def rpc_label_source_gap_stronger_source_plan(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_label_source_gap_stronger_source_plan,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/arkham-structured-source-intake-contract")
@router.post("/rpc/label-source-gap-repair/arkham-structured-source-intake-contract")
async def rpc_label_source_gap_arkham_structured_source_intake_contract(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_label_source_gap_arkham_structured_source_intake_contract,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/arkham-structured-source-acquisition-plan")
@router.post("/rpc/label-source-gap-repair/arkham-structured-source-acquisition-plan")
async def rpc_label_source_gap_arkham_structured_source_acquisition_plan(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_label_source_gap_arkham_structured_source_acquisition_plan,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/arkham-structured-manual-export-intake-preview")
@router.post("/rpc/label-source-gap-repair/arkham-structured-manual-export-intake-preview")
async def rpc_label_source_gap_arkham_structured_manual_export_intake_preview(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    export_path: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(
        get_label_source_gap_arkham_structured_manual_export_intake_preview,
        entity,
        chain,
        limit,
        dry_run,
        export_path,
    )


@router.get("/rpc/label-source-gap-repair/arkham-scrapling-snapshot-research-plan")
@router.post("/rpc/label-source-gap-repair/arkham-scrapling-snapshot-research-plan")
async def rpc_label_source_gap_arkham_scrapling_snapshot_research_plan(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 3,
    snapshot_limit: int = 20,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if snapshot_limit > 50:
        raise HTTPException(status_code=400, detail="snapshot_limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_arkham_scrapling_snapshot_research_plan,
        entity,
        chain,
        limit,
        snapshot_limit,
        dry_run,
    )


@router.get("/rpc/arkham-methodology-mirror")
@router.post("/rpc/arkham-methodology-mirror")
async def rpc_arkham_methodology_mirror(
    entity: str | None = "Binance",
    snapshot_limit: int = 20,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if snapshot_limit > 50:
        raise HTTPException(status_code=400, detail="snapshot_limit_max_50")
    return await asyncio.to_thread(
        get_arkham_methodology_mirror,
        entity,
        snapshot_limit,
        dry_run,
    )


@router.get("/rpc/local-wallet-entity-graph-reconstruction-plan")
@router.post("/rpc/local-wallet-entity-graph-reconstruction-plan")
async def rpc_local_wallet_entity_graph_reconstruction_plan(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_local_wallet_entity_graph_reconstruction_plan,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/adaptive-wallet-entity-graph-collection-contract")
@router.post("/rpc/adaptive-wallet-entity-graph-collection-contract")
async def rpc_adaptive_wallet_entity_graph_collection_contract(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_adaptive_wallet_entity_graph_collection_contract,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/adaptive-wallet-entity-graph-collection-preview")
@router.post("/rpc/adaptive-wallet-entity-graph-collection-preview")
async def rpc_adaptive_wallet_entity_graph_collection_preview(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_adaptive_wallet_entity_graph_collection_preview,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/adaptive-wallet-entity-graph-collection")
async def rpc_adaptive_wallet_entity_graph_collection(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    allow_rpc: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if not dry_run and confirm != "COLLECT_ADAPTIVE_WALLET_ENTITY_GRAPH_DATA":
        raise HTTPException(status_code=400, detail="confirm_COLLECT_ADAPTIVE_WALLET_ENTITY_GRAPH_DATA_required")
    return await asyncio.to_thread(
        run_adaptive_wallet_entity_graph_collection,
        entity,
        chain,
        limit,
        dry_run,
        allow_rpc,
        confirm,
    )


@router.get("/rpc/label-source-gap-repair/source-corroboration-contract")
@router.post("/rpc/label-source-gap-repair/source-corroboration-contract")
async def rpc_label_source_gap_source_corroboration_contract(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_source_corroboration_contract,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/label-source-gap-repair/source-corroboration-dry-run")
async def rpc_label_source_gap_source_corroboration_dry_run(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 9,
    dry_run: bool = True,
    allow_external: bool = False,
    timeout: int = 12,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 9:
        raise HTTPException(status_code=400, detail="limit_max_9")
    if timeout > 20:
        raise HTTPException(status_code=400, detail="timeout_max_20")
    return await asyncio.to_thread(
        run_label_source_gap_source_corroboration_dry_run,
        entity,
        chain,
        limit,
        dry_run,
        allow_external,
        timeout,
    )


@router.post("/rpc/label-source-gap-repair/verified-evidence/apply")
async def rpc_persist_label_source_gap_verified_candidate_evidence(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 9,
    dry_run: bool = True,
    allow_external: bool = False,
    timeout: int = 12,
    confirm: str | None = None,
    expected_evidence_dedupe_keys: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 9:
        raise HTTPException(status_code=400, detail="limit_max_9")
    if timeout > 20:
        raise HTTPException(status_code=400, detail="timeout_max_20")
    if not dry_run and confirm != "PERSIST_LABEL_SOURCE_GAP_VERIFIED_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_PERSIST_LABEL_SOURCE_GAP_VERIFIED_EVIDENCE_required")
    return await asyncio.to_thread(
        persist_label_source_gap_verified_candidate_evidence,
        entity,
        chain,
        limit,
        dry_run,
        allow_external,
        timeout,
        confirm,
        expected_evidence_dedupe_keys,
    )


@router.get("/rpc/label-source-gap-repair/source-application-preview")
@router.post("/rpc/label-source-gap-repair/source-application-preview")
async def rpc_label_source_gap_source_application_preview(
    candidate_id: int | None = None,
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 9,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_label_source_gap_source_application_preview,
        candidate_id,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/local-observation-plan")
@router.post("/rpc/label-source-gap-repair/local-observation-plan")
async def rpc_label_source_gap_local_observation_plan(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_local_observation_plan,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/local-observation-refresh-preview")
@router.post("/rpc/label-source-gap-repair/local-observation-refresh-preview")
async def rpc_label_source_gap_local_observation_refresh_preview(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_local_observation_refresh_preview,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/local-observation-collection-plan")
@router.post("/rpc/label-source-gap-repair/local-observation-collection-plan")
async def rpc_label_source_gap_local_observation_collection_plan(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_local_observation_collection_plan,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/local-observation-collection-contract")
@router.post("/rpc/label-source-gap-repair/local-observation-collection-contract")
async def rpc_label_source_gap_local_observation_collection_contract(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_local_observation_collection_contract,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/label-source-gap-repair/local-observation-collection-preview")
@router.post("/rpc/label-source-gap-repair/local-observation-collection-preview")
async def rpc_label_source_gap_local_observation_collection_preview(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_rpc: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_local_observation_collection_preview,
        entity,
        chain,
        limit,
        dry_run,
        allow_rpc,
    )


@router.get("/rpc/label-source-gap-repair/local-observation-post-collection-review-contract")
@router.post("/rpc/label-source-gap-repair/local-observation-post-collection-review-contract")
async def rpc_label_source_gap_local_observation_post_collection_review_contract(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_local_observation_post_collection_review_contract,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/label-source-gap-repair/local-observation-collection/collect")
async def rpc_collect_label_source_gap_local_observations(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    allow_rpc: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if not dry_run and not allow_rpc:
        raise HTTPException(status_code=400, detail="allow_rpc_true_required")
    if not dry_run and confirm != "COLLECT_LABEL_SOURCE_GAP_LOCAL_OBSERVATIONS":
        raise HTTPException(status_code=400, detail="confirm_COLLECT_LABEL_SOURCE_GAP_LOCAL_OBSERVATIONS_required")
    return await asyncio.to_thread(
        collect_label_source_gap_local_observations,
        entity,
        chain,
        limit,
        dry_run,
        allow_rpc,
        confirm,
    )


@router.get("/rpc/label-source-gap-repair/local-observation-apply-preview")
@router.post("/rpc/label-source-gap-repair/local-observation-apply-preview")
async def rpc_label_source_gap_local_observation_apply_preview(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_label_source_gap_local_observation_apply_preview,
        entity,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/label-source-gap-repair/local-observation-apply")
async def rpc_apply_label_source_gap_local_observations(
    entity: str | None = None,
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if not dry_run and confirm != "APPLY_LABEL_SOURCE_GAP_LOCAL_OBSERVATIONS":
        raise HTTPException(status_code=400, detail="confirm_APPLY_LABEL_SOURCE_GAP_LOCAL_OBSERVATIONS_required")
    return await asyncio.to_thread(
        apply_label_source_gap_local_observations,
        entity,
        chain,
        limit,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-discovery-candidates/evidence-intake-preview")
async def rpc_token_market_discovery_candidate_evidence_intake_preview(
    candidate_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if candidate_id is None:
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_discovery_candidate_evidence_intake_preview,
        candidate_id,
        dry_run,
    )


@router.post("/rpc/token-market-discovery-evidence-queue-schema-plan")
async def rpc_token_market_discovery_evidence_queue_schema_plan(
    candidate_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if candidate_id is None:
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_discovery_evidence_queue_schema_plan,
        candidate_id,
        dry_run,
    )


@router.post("/rpc/token-market-discovery-evidence-queue/create")
async def rpc_create_token_market_discovery_evidence_queue(
    candidate_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if candidate_id is None:
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_DISCOVERY_EVIDENCE_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_DISCOVERY_EVIDENCE_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_discovery_evidence_queue,
        candidate_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-discovery-evidence/insert")
async def rpc_insert_token_market_discovery_evidence(
    candidate_id: int | None = None,
    expected_evidence_preview_digest: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if candidate_id is None:
        raise HTTPException(status_code=400, detail="candidate_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_DISCOVERY_EVIDENCE":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_DISCOVERY_EVIDENCE_required",
        )
    return await asyncio.to_thread(
        insert_token_market_discovery_evidence,
        candidate_id,
        expected_evidence_preview_digest,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-discovery-evidence/review-queue")
async def rpc_token_market_discovery_evidence_review_queue(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_discovery_evidence_review_queue,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-discovery-evidence/human-decision-preview")
async def rpc_token_market_discovery_evidence_human_decision_preview(
    evidence_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if evidence_id is None:
        raise HTTPException(status_code=400, detail="evidence_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if str(proposed_decision or "").strip().lower() not in {
        "accept_for_future_controlled_promotion",
        "request_better_source",
        "reject",
    }:
        raise HTTPException(status_code=400, detail="invalid_proposed_decision")
    return await asyncio.to_thread(
        get_token_market_discovery_evidence_human_decision_preview,
        evidence_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-discovery-evidence/human-decision/apply")
async def rpc_apply_token_market_discovery_evidence_human_decision(
    evidence_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if evidence_id is None:
        raise HTTPException(status_code=400, detail="evidence_id_required")
    if str(proposed_decision or "").strip().lower() not in {
        "accept_for_future_controlled_promotion",
        "request_better_source",
        "reject",
    }:
        raise HTTPException(status_code=400, detail="invalid_proposed_decision")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_DISCOVERY_EVIDENCE_HUMAN_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_DISCOVERY_EVIDENCE_HUMAN_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_discovery_evidence_human_decision,
        evidence_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-discovery-evidence/controlled-promotion-preview")
async def rpc_token_market_discovery_evidence_controlled_promotion_preview(
    evidence_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if evidence_id is None:
        raise HTTPException(status_code=400, detail="evidence_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_discovery_evidence_controlled_promotion_preview,
        evidence_id,
        dry_run,
    )


@router.post("/rpc/token-market-discovery-evidence/controlled-promotion-insert-contract")
async def rpc_token_market_discovery_evidence_controlled_promotion_insert_contract(
    evidence_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if evidence_id is None:
        raise HTTPException(status_code=400, detail="evidence_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_discovery_evidence_controlled_promotion_insert_contract,
        evidence_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-controlled-promotion-queue-schema-plan")
async def rpc_token_market_controlled_promotion_queue_schema_plan(
    evidence_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if evidence_id is None:
        raise HTTPException(status_code=400, detail="evidence_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_controlled_promotion_queue_schema_plan,
        evidence_id,
        dry_run,
    )


@router.post("/rpc/token-market-controlled-promotion-queue/create")
async def rpc_create_token_market_controlled_promotion_queue(
    evidence_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if evidence_id is None:
        raise HTTPException(status_code=400, detail="evidence_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_CONTROLLED_PROMOTION_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_CONTROLLED_PROMOTION_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_controlled_promotion_queue,
        evidence_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-controlled-promotion-queue/insert")
async def rpc_insert_token_market_controlled_promotion(
    evidence_id: int | None = None,
    expected_promotion_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if evidence_id is None:
        raise HTTPException(status_code=400, detail="evidence_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_CONTROLLED_PROMOTION":
        raise HTTPException(status_code=400, detail="confirm_INSERT_TOKEN_MARKET_CONTROLLED_PROMOTION_required")
    return await asyncio.to_thread(
        insert_token_market_controlled_promotion,
        evidence_id,
        expected_promotion_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-controlled-promotion-queue/review")
async def rpc_token_market_controlled_promotion_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_controlled_promotion_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-controlled-promotion-queue/decision-preview")
async def rpc_token_market_controlled_promotion_decision_preview(
    promotion_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if promotion_id is None:
        raise HTTPException(status_code=400, detail="promotion_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    allowed_decisions = {
        "accept_for_future_downstream_insert",
        "request_better_source",
        "reject",
    }
    if str(proposed_decision or "").strip().lower() not in allowed_decisions:
        raise HTTPException(status_code=400, detail="invalid_proposed_decision")
    return await asyncio.to_thread(
        get_token_market_controlled_promotion_decision_preview,
        promotion_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-controlled-promotion-queue/decision/apply")
async def rpc_apply_token_market_controlled_promotion_decision(
    promotion_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if promotion_id is None:
        raise HTTPException(status_code=400, detail="promotion_id_required")
    allowed_decisions = {
        "accept_for_future_downstream_insert",
        "request_better_source",
        "reject",
    }
    if str(proposed_decision or "").strip().lower() not in allowed_decisions:
        raise HTTPException(status_code=400, detail="invalid_proposed_decision")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_CONTROLLED_PROMOTION_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_CONTROLLED_PROMOTION_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_controlled_promotion_decision,
        promotion_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-controlled-promotion-queue/downstream-insert-contract")
async def rpc_token_market_controlled_promotion_downstream_insert_contract(
    promotion_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if promotion_id is None:
        raise HTTPException(status_code=400, detail="promotion_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_controlled_promotion_downstream_insert_contract,
        promotion_id,
        dry_run,
    )


@router.post("/rpc/token-market-downstream-promotion-queue-schema-plan")
async def rpc_token_market_downstream_promotion_queue_schema_plan(
    promotion_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if promotion_id is None:
        raise HTTPException(status_code=400, detail="promotion_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_downstream_promotion_queue_schema_plan,
        promotion_id,
        dry_run,
    )


@router.post("/rpc/token-market-downstream-promotion-queue/create")
async def rpc_token_market_downstream_promotion_queue_create(
    promotion_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if promotion_id is None:
        raise HTTPException(status_code=400, detail="promotion_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_DOWNSTREAM_PROMOTION_QUEUE":
        raise HTTPException(status_code=400, detail="confirm_CREATE_TOKEN_MARKET_DOWNSTREAM_PROMOTION_QUEUE_required")
    return await asyncio.to_thread(
        create_token_market_downstream_promotion_queue,
        promotion_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-downstream-promotion-queue/insert")
async def rpc_token_market_downstream_promotion_queue_insert(
    promotion_id: int | None = None,
    expected_downstream_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if promotion_id is None:
        raise HTTPException(status_code=400, detail="promotion_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_DOWNSTREAM_PROMOTION":
        raise HTTPException(status_code=400, detail="confirm_INSERT_TOKEN_MARKET_DOWNSTREAM_PROMOTION_required")
    return await asyncio.to_thread(
        insert_token_market_downstream_promotion,
        promotion_id,
        expected_downstream_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-downstream-promotion-queue/review")
async def rpc_token_market_downstream_promotion_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_downstream_promotion_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-downstream-promotion-queue/decision-preview")
async def rpc_token_market_downstream_promotion_decision_preview(
    downstream_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if downstream_id is None:
        raise HTTPException(status_code=400, detail="downstream_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_downstream_promotion_decision_preview,
        downstream_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-downstream-promotion-queue/decision/apply")
async def rpc_token_market_downstream_promotion_decision_apply(
    downstream_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if downstream_id is None:
        raise HTTPException(status_code=400, detail="downstream_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_DOWNSTREAM_PROMOTION_DECISION":
        raise HTTPException(status_code=400, detail="confirm_APPLY_TOKEN_MARKET_DOWNSTREAM_PROMOTION_DECISION_required")
    return await asyncio.to_thread(
        apply_token_market_downstream_promotion_decision,
        downstream_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-downstream-promotion-queue/business-insert-contract")
async def rpc_token_market_downstream_business_insert_contract(
    downstream_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if downstream_id is None:
        raise HTTPException(status_code=400, detail="downstream_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_downstream_business_insert_contract,
        downstream_id,
        dry_run,
    )


@router.post("/rpc/token-market-downstream-business-handoff-queue-schema-plan")
async def rpc_token_market_downstream_business_handoff_queue_schema_plan(
    downstream_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if downstream_id is None:
        raise HTTPException(status_code=400, detail="downstream_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_downstream_business_handoff_queue_schema_plan,
        downstream_id,
        dry_run,
    )


@router.post("/rpc/token-market-downstream-business-handoff-queue/create")
async def rpc_token_market_downstream_business_handoff_queue_create(
    downstream_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if downstream_id is None:
        raise HTTPException(status_code=400, detail="downstream_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_downstream_business_handoff_queue,
        downstream_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-downstream-business-handoff-queue/insert")
async def rpc_token_market_downstream_business_handoff_queue_insert(
    downstream_id: int | None = None,
    expected_business_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if downstream_id is None:
        raise HTTPException(status_code=400, detail="downstream_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_required",
        )
    return await asyncio.to_thread(
        insert_token_market_downstream_business_handoff,
        downstream_id,
        expected_business_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-downstream-business-handoff-queue/review")
async def rpc_token_market_downstream_business_handoff_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_downstream_business_handoff_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-downstream-business-handoff-queue/decision-preview")
async def rpc_token_market_downstream_business_handoff_queue_decision_preview(
    business_handoff_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_handoff_id is None:
        raise HTTPException(status_code=400, detail="business_handoff_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_downstream_business_handoff_decision_preview,
        business_handoff_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-downstream-business-handoff-queue/decision/apply")
async def rpc_token_market_downstream_business_handoff_queue_decision_apply(
    business_handoff_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_handoff_id is None:
        raise HTTPException(status_code=400, detail="business_handoff_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_downstream_business_handoff_decision,
        business_handoff_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-downstream-business-handoff-queue/business-insert-contract")
async def rpc_token_market_downstream_business_handoff_queue_business_insert_contract(
    business_handoff_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_handoff_id is None:
        raise HTTPException(status_code=400, detail="business_handoff_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_downstream_business_handoff_business_insert_contract,
        business_handoff_id,
        dry_run,
    )


@router.post("/rpc/token-market-business-insert-queue-schema-plan")
async def rpc_token_market_business_insert_queue_schema_plan(
    business_handoff_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_handoff_id is None:
        raise HTTPException(status_code=400, detail="business_handoff_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_insert_queue_schema_plan,
        business_handoff_id,
        dry_run,
    )


@router.post("/rpc/token-market-business-insert-queue/create")
async def rpc_token_market_business_insert_queue_create(
    business_handoff_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_handoff_id is None:
        raise HTTPException(status_code=400, detail="business_handoff_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_BUSINESS_INSERT_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_BUSINESS_INSERT_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_business_insert_queue,
        business_handoff_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-insert-queue/insert")
async def rpc_token_market_business_insert_queue_insert(
    business_handoff_id: int | None = None,
    expected_business_insert_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_handoff_id is None:
        raise HTTPException(status_code=400, detail="business_handoff_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_BUSINESS_INSERT":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_BUSINESS_INSERT_required",
        )
    return await asyncio.to_thread(
        insert_token_market_business_insert,
        business_handoff_id,
        expected_business_insert_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-insert-queue/review")
async def rpc_token_market_business_insert_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_insert_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-business-insert-queue/decision-preview")
async def rpc_token_market_business_insert_queue_decision_preview(
    business_insert_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_insert_id is None:
        raise HTTPException(status_code=400, detail="business_insert_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_insert_decision_preview,
        business_insert_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-business-insert-queue/decision/apply")
async def rpc_token_market_business_insert_queue_decision_apply(
    business_insert_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_insert_id is None:
        raise HTTPException(status_code=400, detail="business_insert_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_BUSINESS_INSERT_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_BUSINESS_INSERT_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_business_insert_decision,
        business_insert_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-insert-queue/business-execution-contract")
async def rpc_token_market_business_insert_queue_business_execution_contract(
    business_insert_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_insert_id is None:
        raise HTTPException(status_code=400, detail="business_insert_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_execution_contract,
        business_insert_id,
        dry_run,
    )


@router.post("/rpc/token-market-business-execution-queue-schema-plan")
async def rpc_token_market_business_execution_queue_schema_plan(
    business_insert_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_insert_id is None:
        raise HTTPException(status_code=400, detail="business_insert_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_execution_queue_schema_plan,
        business_insert_id,
        dry_run,
    )


@router.post("/rpc/token-market-business-execution-queue/create")
async def rpc_token_market_business_execution_queue_create(
    business_insert_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_insert_id is None:
        raise HTTPException(status_code=400, detail="business_insert_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_BUSINESS_EXECUTION_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_BUSINESS_EXECUTION_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_business_execution_queue,
        business_insert_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-execution-queue/insert")
async def rpc_token_market_business_execution_queue_insert(
    business_insert_id: int | None = None,
    expected_business_execution_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_insert_id is None:
        raise HTTPException(status_code=400, detail="business_insert_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_BUSINESS_EXECUTION":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_BUSINESS_EXECUTION_required",
        )
    return await asyncio.to_thread(
        insert_token_market_business_execution,
        business_insert_id,
        expected_business_execution_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-execution-queue/review")
async def rpc_token_market_business_execution_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_execution_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-business-execution-queue/decision-preview")
async def rpc_token_market_business_execution_queue_decision_preview(
    business_execution_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_execution_id is None:
        raise HTTPException(status_code=400, detail="business_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_execution_decision_preview,
        business_execution_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-business-execution-queue/decision/apply")
async def rpc_token_market_business_execution_queue_decision_apply(
    business_execution_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_execution_id is None:
        raise HTTPException(status_code=400, detail="business_execution_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_BUSINESS_EXECUTION_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_BUSINESS_EXECUTION_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_business_execution_decision,
        business_execution_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-execution-queue/business-apply-contract")
async def rpc_token_market_business_execution_queue_business_apply_contract(
    business_execution_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_execution_id is None:
        raise HTTPException(status_code=400, detail="business_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_apply_contract,
        business_execution_id,
        dry_run,
    )


@router.post("/rpc/token-market-business-apply-queue-schema-plan")
async def rpc_token_market_business_apply_queue_schema_plan(
    business_execution_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_execution_id is None:
        raise HTTPException(status_code=400, detail="business_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_apply_queue_schema_plan,
        business_execution_id,
        dry_run,
    )


@router.post("/rpc/token-market-business-apply-queue/create")
async def rpc_token_market_business_apply_queue_create(
    business_execution_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_execution_id is None:
        raise HTTPException(status_code=400, detail="business_execution_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_BUSINESS_APPLY_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_BUSINESS_APPLY_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_business_apply_queue,
        business_execution_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-apply-queue/insert")
async def rpc_token_market_business_apply_queue_insert(
    business_execution_id: int | None = None,
    expected_business_apply_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_execution_id is None:
        raise HTTPException(status_code=400, detail="business_execution_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_BUSINESS_APPLY":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_BUSINESS_APPLY_required",
        )
    return await asyncio.to_thread(
        insert_token_market_business_apply,
        business_execution_id,
        expected_business_apply_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-apply-queue/review")
async def rpc_token_market_business_apply_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_apply_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-business-apply-queue/decision-preview")
async def rpc_token_market_business_apply_queue_decision_preview(
    business_apply_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_apply_id is None:
        raise HTTPException(status_code=400, detail="business_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_apply_decision_preview,
        business_apply_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-business-apply-queue/decision/apply")
async def rpc_token_market_business_apply_queue_decision_apply(
    business_apply_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_apply_id is None:
        raise HTTPException(status_code=400, detail="business_apply_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_BUSINESS_APPLY_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_BUSINESS_APPLY_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_business_apply_decision,
        business_apply_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-business-apply-queue/post-apply-contract")
async def rpc_token_market_business_apply_queue_post_apply_contract(
    business_apply_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_apply_id is None:
        raise HTTPException(status_code=400, detail="business_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_business_post_apply_contract,
        business_apply_id,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-queue-schema-plan")
async def rpc_token_market_post_apply_queue_schema_plan(
    business_apply_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if business_apply_id is None:
        raise HTTPException(status_code=400, detail="business_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_queue_schema_plan,
        business_apply_id,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-queue/create")
async def rpc_token_market_post_apply_queue_create(
    business_apply_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_apply_id is None:
        raise HTTPException(status_code=400, detail="business_apply_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_POST_APPLY_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_POST_APPLY_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_post_apply_queue,
        business_apply_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-queue/insert")
async def rpc_token_market_post_apply_queue_insert(
    business_apply_id: int | None = None,
    expected_post_apply_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if business_apply_id is None:
        raise HTTPException(status_code=400, detail="business_apply_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_POST_APPLY":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_POST_APPLY_required",
        )
    return await asyncio.to_thread(
        insert_token_market_post_apply,
        business_apply_id,
        expected_post_apply_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-queue/review")
async def rpc_token_market_post_apply_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-queue/decision-preview")
async def rpc_token_market_post_apply_queue_decision_preview(
    post_apply_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_decision_preview,
        post_apply_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-queue/decision/apply")
async def rpc_token_market_post_apply_queue_decision_apply(
    post_apply_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_POST_APPLY_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_POST_APPLY_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_post_apply_decision,
        post_apply_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-queue/insert-contract")
async def rpc_token_market_post_apply_queue_insert_contract(
    post_apply_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_insert_contract,
        post_apply_id,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-insert-queue-schema-plan")
async def rpc_token_market_post_apply_insert_queue_schema_plan(
    post_apply_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_insert_queue_schema_plan,
        post_apply_id,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-insert-queue/create")
async def rpc_token_market_post_apply_insert_queue_create(
    post_apply_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_POST_APPLY_INSERT_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_POST_APPLY_INSERT_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_post_apply_insert_queue,
        post_apply_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-insert-queue/insert")
async def rpc_token_market_post_apply_insert_queue_insert(
    post_apply_id: int | None = None,
    expected_post_apply_insert_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_POST_APPLY_INSERT":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_POST_APPLY_INSERT_required",
        )
    return await asyncio.to_thread(
        insert_token_market_post_apply_insert,
        post_apply_id,
        expected_post_apply_insert_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-insert-queue/review")
async def rpc_token_market_post_apply_insert_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_insert_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-insert-queue/decision-preview")
async def rpc_token_market_post_apply_insert_queue_decision_preview(
    post_apply_insert_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_insert_id is None:
        raise HTTPException(status_code=400, detail="post_apply_insert_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_insert_decision_preview,
        post_apply_insert_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-insert-queue/decision/apply")
async def rpc_token_market_post_apply_insert_queue_decision_apply(
    post_apply_insert_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_insert_id is None:
        raise HTTPException(status_code=400, detail="post_apply_insert_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_POST_APPLY_INSERT_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_POST_APPLY_INSERT_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_post_apply_insert_decision,
        post_apply_insert_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-insert-queue/post-apply-execution-contract")
async def rpc_token_market_post_apply_insert_queue_post_apply_execution_contract(
    post_apply_insert_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_insert_id is None:
        raise HTTPException(status_code=400, detail="post_apply_insert_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_execution_contract,
        post_apply_insert_id,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-execution-queue-schema-plan")
async def rpc_token_market_post_apply_execution_queue_schema_plan(
    post_apply_insert_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_insert_id is None:
        raise HTTPException(status_code=400, detail="post_apply_insert_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_execution_queue_schema_plan,
        post_apply_insert_id,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-execution-queue/create")
async def rpc_token_market_post_apply_execution_queue_create(
    post_apply_insert_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_insert_id is None:
        raise HTTPException(status_code=400, detail="post_apply_insert_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_POST_APPLY_EXECUTION_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_POST_APPLY_EXECUTION_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_post_apply_execution_queue,
        post_apply_insert_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-execution-queue/insert")
async def rpc_token_market_post_apply_execution_queue_insert(
    post_apply_insert_id: int | None = None,
    expected_post_apply_execution_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_insert_id is None:
        raise HTTPException(status_code=400, detail="post_apply_insert_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_POST_APPLY_EXECUTION":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_POST_APPLY_EXECUTION_required",
        )
    return await asyncio.to_thread(
        insert_token_market_post_apply_execution,
        post_apply_insert_id,
        expected_post_apply_execution_dedupe_key,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-execution-queue/review")
async def rpc_token_market_post_apply_execution_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_execution_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-execution-queue/decision-preview")
async def rpc_token_market_post_apply_execution_queue_decision_preview(
    post_apply_execution_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_execution_decision_preview,
        post_apply_execution_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-execution-queue/decision/apply")
async def rpc_token_market_post_apply_execution_queue_decision_apply(
    post_apply_execution_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_POST_APPLY_EXECUTION_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_POST_APPLY_EXECUTION_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_post_apply_execution_decision,
        post_apply_execution_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-execution-queue/apply-contract")
async def rpc_token_market_post_apply_execution_queue_apply_contract(
    post_apply_execution_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_execution_apply_contract,
        post_apply_execution_id,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-execution-apply-queue-schema-plan")
async def rpc_token_market_post_apply_execution_apply_queue_schema_plan(
    post_apply_execution_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_execution_apply_queue_schema_plan,
        post_apply_execution_id,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-execution-apply-queue/create")
async def rpc_create_token_market_post_apply_execution_apply_queue(
    post_apply_execution_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_POST_APPLY_EXECUTION_APPLY_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_POST_APPLY_EXECUTION_APPLY_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_post_apply_execution_apply_queue,
        post_apply_execution_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-post-apply-execution-apply-queue/insert")
async def rpc_insert_token_market_post_apply_execution_apply(
    post_apply_execution_id: int | None = None,
    expected_post_apply_execution_apply_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_POST_APPLY_EXECUTION_APPLY":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_POST_APPLY_EXECUTION_APPLY_required",
        )
    return await asyncio.to_thread(
        insert_token_market_post_apply_execution_apply,
        post_apply_execution_id,
        expected_post_apply_execution_apply_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-post-apply-execution-apply-queue/review")
@router.post("/rpc/token-market-post-apply-execution-apply-queue/review")
async def rpc_token_market_post_apply_execution_apply_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_execution_apply_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-execution-apply-queue/decision-preview")
async def rpc_token_market_post_apply_execution_apply_queue_decision_preview(
    post_apply_execution_apply_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_post_apply_execution_apply_decision_preview,
        post_apply_execution_apply_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-post-apply-execution-apply-queue/decision/apply")
async def rpc_token_market_post_apply_execution_apply_queue_decision_apply(
    post_apply_execution_apply_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_apply_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_POST_APPLY_EXECUTION_APPLY_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_POST_APPLY_EXECUTION_APPLY_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_post_apply_execution_apply_decision,
        post_apply_execution_apply_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-post-apply-execution-apply-queue/final-apply-contract")
@router.post("/rpc/token-market-post-apply-execution-apply-queue/final-apply-contract")
async def rpc_token_market_post_apply_execution_apply_queue_final_apply_contract(
    post_apply_execution_apply_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_apply_contract,
        post_apply_execution_apply_id,
        dry_run,
    )


@router.get("/rpc/token-market-final-apply-queue-schema-plan")
@router.post("/rpc/token-market-final-apply-queue-schema-plan")
async def rpc_token_market_final_apply_queue_schema_plan(
    post_apply_execution_apply_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_apply_queue_schema_plan,
        post_apply_execution_apply_id,
        dry_run,
    )


@router.post("/rpc/token-market-final-apply-queue/create")
async def rpc_create_token_market_final_apply_queue(
    post_apply_execution_apply_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_apply_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_FINAL_APPLY_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_FINAL_APPLY_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_final_apply_queue,
        post_apply_execution_apply_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-final-apply-queue/insert")
async def rpc_insert_token_market_final_apply(
    post_apply_execution_apply_id: int | None = None,
    expected_final_apply_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if post_apply_execution_apply_id is None:
        raise HTTPException(status_code=400, detail="post_apply_execution_apply_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_FINAL_APPLY":
        raise HTTPException(status_code=400, detail="confirm_INSERT_TOKEN_MARKET_FINAL_APPLY_required")
    return await asyncio.to_thread(
        insert_token_market_final_apply,
        post_apply_execution_apply_id,
        expected_final_apply_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-final-apply-queue/review")
@router.post("/rpc/token-market-final-apply-queue/review")
async def rpc_token_market_final_apply_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_apply_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-final-apply-queue/decision-preview")
async def rpc_token_market_final_apply_queue_decision_preview(
    final_apply_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_apply_id is None:
        raise HTTPException(status_code=400, detail="final_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_apply_decision_preview,
        final_apply_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-final-apply-queue/decision/apply")
async def rpc_token_market_final_apply_queue_decision_apply(
    final_apply_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_apply_id is None:
        raise HTTPException(status_code=400, detail="final_apply_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_FINAL_APPLY_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_FINAL_APPLY_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_final_apply_decision,
        final_apply_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-final-apply-queue/final-target-execution-contract")
@router.post("/rpc/token-market-final-apply-queue/final-target-execution-contract")
async def rpc_token_market_final_apply_queue_final_target_execution_contract(
    final_apply_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_apply_id is None:
        raise HTTPException(status_code=400, detail="final_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_target_execution_contract,
        final_apply_id,
        dry_run,
    )


@router.get("/rpc/token-market-final-target-execution-queue-schema-plan")
@router.post("/rpc/token-market-final-target-execution-queue-schema-plan")
async def rpc_token_market_final_target_execution_queue_schema_plan(
    final_apply_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_apply_id is None:
        raise HTTPException(status_code=400, detail="final_apply_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_target_execution_queue_schema_plan,
        final_apply_id,
        dry_run,
    )


@router.post("/rpc/token-market-final-target-execution-queue/create")
async def rpc_create_token_market_final_target_execution_queue(
    final_apply_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_apply_id is None:
        raise HTTPException(status_code=400, detail="final_apply_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_FINAL_TARGET_EXECUTION_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_FINAL_TARGET_EXECUTION_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_final_target_execution_queue,
        final_apply_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-final-target-execution-queue/insert")
async def rpc_insert_token_market_final_target_execution(
    final_apply_id: int | None = None,
    expected_final_target_execution_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_apply_id is None:
        raise HTTPException(status_code=400, detail="final_apply_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_FINAL_TARGET_EXECUTION":
        raise HTTPException(status_code=400, detail="confirm_INSERT_TOKEN_MARKET_FINAL_TARGET_EXECUTION_required")
    return await asyncio.to_thread(
        insert_token_market_final_target_execution,
        final_apply_id,
        expected_final_target_execution_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-final-target-execution-queue/review")
@router.post("/rpc/token-market-final-target-execution-queue/review")
async def rpc_token_market_final_target_execution_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_target_execution_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-final-target-execution-queue/decision-preview")
async def rpc_token_market_final_target_execution_queue_decision_preview(
    final_target_execution_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_target_execution_id is None:
        raise HTTPException(status_code=400, detail="final_target_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_target_execution_decision_preview,
        final_target_execution_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-final-target-execution-queue/decision/apply")
async def rpc_token_market_final_target_execution_queue_decision_apply(
    final_target_execution_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_target_execution_id is None:
        raise HTTPException(status_code=400, detail="final_target_execution_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_FINAL_TARGET_EXECUTION_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_FINAL_TARGET_EXECUTION_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_final_target_execution_decision,
        final_target_execution_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-final-target-execution-queue/handoff-contract")
@router.post("/rpc/token-market-final-target-execution-queue/handoff-contract")
async def rpc_token_market_final_target_execution_queue_handoff_contract(
    final_target_execution_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_target_execution_id is None:
        raise HTTPException(status_code=400, detail="final_target_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_target_execution_handoff_contract,
        final_target_execution_id,
        dry_run,
    )


@router.get("/rpc/token-market-final-handoff-queue-schema-plan")
@router.post("/rpc/token-market-final-handoff-queue-schema-plan")
async def rpc_token_market_final_handoff_queue_schema_plan(
    final_target_execution_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_target_execution_id is None:
        raise HTTPException(status_code=400, detail="final_target_execution_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_handoff_queue_schema_plan,
        final_target_execution_id,
        dry_run,
    )


@router.post("/rpc/token-market-final-handoff-queue/create")
async def rpc_create_token_market_final_handoff_queue(
    final_target_execution_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_target_execution_id is None:
        raise HTTPException(status_code=400, detail="final_target_execution_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_FINAL_HANDOFF_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_FINAL_HANDOFF_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_final_handoff_queue,
        final_target_execution_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-final-handoff-queue/insert")
async def rpc_insert_token_market_final_handoff(
    final_target_execution_id: int | None = None,
    expected_handoff_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_target_execution_id is None:
        raise HTTPException(status_code=400, detail="final_target_execution_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_FINAL_HANDOFF":
        raise HTTPException(status_code=400, detail="confirm_INSERT_TOKEN_MARKET_FINAL_HANDOFF_required")
    return await asyncio.to_thread(
        insert_token_market_final_handoff,
        final_target_execution_id,
        expected_handoff_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-final-handoff-queue/review")
@router.post("/rpc/token-market-final-handoff-queue/review")
async def rpc_token_market_final_handoff_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_handoff_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-final-handoff-queue/decision-preview")
async def rpc_token_market_final_handoff_queue_decision_preview(
    final_handoff_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_handoff_decision_preview,
        final_handoff_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-final-handoff-queue/decision/apply")
async def rpc_token_market_final_handoff_queue_decision_apply(
    final_handoff_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_FINAL_HANDOFF_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_FINAL_HANDOFF_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_final_handoff_decision,
        final_handoff_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-final-handoff-queue/target-contract")
@router.post("/rpc/token-market-final-handoff-queue/target-contract")
async def rpc_token_market_final_handoff_queue_target_contract(
    final_handoff_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_handoff_target_contract,
        final_handoff_id,
        dry_run,
    )


@router.get("/rpc/token-market-final-handoff-target-queue-schema-plan")
@router.post("/rpc/token-market-final-handoff-target-queue-schema-plan")
async def rpc_token_market_final_handoff_target_queue_schema_plan(
    final_handoff_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_handoff_target_queue_schema_plan,
        final_handoff_id,
        dry_run,
    )


@router.post("/rpc/token-market-final-handoff-target-queue/create")
async def rpc_create_token_market_final_handoff_target_queue(
    final_handoff_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_id_required")
    if not dry_run and confirm != "CREATE_TOKEN_MARKET_FINAL_HANDOFF_TARGET_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_TOKEN_MARKET_FINAL_HANDOFF_TARGET_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_token_market_final_handoff_target_queue,
        final_handoff_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/token-market-final-handoff-target-queue/insert")
async def rpc_insert_token_market_final_handoff_target(
    final_handoff_id: int | None = None,
    expected_target_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_id_required")
    if not dry_run and confirm != "INSERT_TOKEN_MARKET_FINAL_HANDOFF_TARGET":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_TOKEN_MARKET_FINAL_HANDOFF_TARGET_required",
        )
    return await asyncio.to_thread(
        insert_token_market_final_handoff_target,
        final_handoff_id,
        expected_target_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-final-handoff-target-queue/review")
@router.post("/rpc/token-market-final-handoff-target-queue/review")
async def rpc_token_market_final_handoff_target_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_handoff_target_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/token-market-final-handoff-target-queue/decision-preview")
async def rpc_token_market_final_handoff_target_queue_decision_preview(
    final_handoff_target_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_target_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_target_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_handoff_target_decision_preview,
        final_handoff_target_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/token-market-final-handoff-target-queue/decision/apply")
async def rpc_token_market_final_handoff_target_queue_decision_apply(
    final_handoff_target_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_target_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_target_id_required")
    if not dry_run and confirm != "APPLY_TOKEN_MARKET_FINAL_HANDOFF_TARGET_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_TOKEN_MARKET_FINAL_HANDOFF_TARGET_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_token_market_final_handoff_target_decision,
        final_handoff_target_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/token-market-final-handoff-target-queue/cex-review-handoff-contract")
@router.post("/rpc/token-market-final-handoff-target-queue/cex-review-handoff-contract")
async def rpc_token_market_final_handoff_target_queue_cex_review_handoff_contract(
    final_handoff_target_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_target_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_target_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_token_market_final_handoff_target_cex_review_handoff_contract,
        final_handoff_target_id,
        dry_run,
    )


@router.get("/rpc/cex-market-evidence-review-queue-schema-plan")
@router.post("/rpc/cex-market-evidence-review-queue-schema-plan")
async def rpc_cex_market_evidence_review_queue_schema_plan(
    final_handoff_target_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_target_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_target_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_market_evidence_review_queue_schema_plan,
        final_handoff_target_id,
        dry_run,
    )


@router.post("/rpc/cex-market-evidence-review-queue/create")
async def rpc_create_cex_market_evidence_review_queue(
    final_handoff_target_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_target_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_target_id_required")
    if not dry_run and confirm != "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_cex_market_evidence_review_queue,
        final_handoff_target_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/cex-market-evidence-review-queue/insert")
async def rpc_insert_cex_market_evidence_review(
    final_handoff_target_id: int | None = None,
    expected_cex_review_handoff_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if final_handoff_target_id is None:
        raise HTTPException(status_code=400, detail="final_handoff_target_id_required")
    if not dry_run and confirm != "INSERT_CEX_MARKET_EVIDENCE_REVIEW":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_CEX_MARKET_EVIDENCE_REVIEW_required",
        )
    if not dry_run and not expected_cex_review_handoff_dedupe_key:
        raise HTTPException(
            status_code=400,
            detail="expected_cex_review_handoff_dedupe_key_required",
        )
    return await asyncio.to_thread(
        insert_cex_market_evidence_review,
        final_handoff_target_id,
        expected_cex_review_handoff_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-market-evidence-review-queue/review")
@router.post("/rpc/cex-market-evidence-review-queue/review")
async def rpc_cex_market_evidence_review_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_market_evidence_review_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/cex-market-evidence-review-queue/decision-preview")
async def rpc_cex_market_evidence_review_queue_decision_preview(
    cex_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_review_id is None:
        raise HTTPException(status_code=400, detail="cex_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_market_evidence_review_decision_preview,
        cex_review_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/cex-market-evidence-review-queue/decision/apply")
async def rpc_cex_market_evidence_review_queue_decision_apply(
    cex_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_review_id is None:
        raise HTTPException(status_code=400, detail="cex_review_id_required")
    if not dry_run and confirm != "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_cex_market_evidence_review_decision,
        cex_review_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-market-evidence-review-queue/label-candidate-handoff-contract")
@router.post("/rpc/cex-market-evidence-review-queue/label-candidate-handoff-contract")
async def rpc_cex_market_evidence_review_queue_label_candidate_handoff_contract(
    cex_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_review_id is None:
        raise HTTPException(status_code=400, detail="cex_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_market_evidence_review_label_candidate_handoff_contract,
        cex_review_id,
        dry_run,
    )


@router.get("/rpc/cex-label-candidate-review-queue-schema-plan")
@router.post("/rpc/cex-label-candidate-review-queue-schema-plan")
async def rpc_cex_label_candidate_review_queue_schema_plan(
    cex_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_review_id is None:
        raise HTTPException(status_code=400, detail="cex_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_label_candidate_review_queue_schema_plan,
        cex_review_id,
        dry_run,
    )


@router.post("/rpc/cex-label-candidate-review-queue/create")
async def rpc_create_cex_label_candidate_review_queue(
    cex_review_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_review_id is None:
        raise HTTPException(status_code=400, detail="cex_review_id_required")
    if not dry_run and confirm != "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_cex_label_candidate_review_queue,
        cex_review_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/cex-label-candidate-review-queue/insert")
async def rpc_insert_cex_label_candidate_review(
    cex_review_id: int | None = None,
    expected_label_candidate_handoff_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_review_id is None:
        raise HTTPException(status_code=400, detail="cex_review_id_required")
    if not dry_run and confirm != "INSERT_CEX_LABEL_CANDIDATE_REVIEW":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_CEX_LABEL_CANDIDATE_REVIEW_required",
        )
    if not dry_run and not expected_label_candidate_handoff_dedupe_key:
        raise HTTPException(
            status_code=400,
            detail="expected_label_candidate_handoff_dedupe_key_required",
        )
    return await asyncio.to_thread(
        insert_cex_label_candidate_review,
        cex_review_id,
        expected_label_candidate_handoff_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-label-candidate-review-queue/review")
@router.post("/rpc/cex-label-candidate-review-queue/review")
async def rpc_cex_label_candidate_review_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_label_candidate_review_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/cex-label-candidate-review-queue/decision-preview")
async def rpc_cex_label_candidate_review_queue_decision_preview(
    cex_label_candidate_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_label_candidate_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_candidate_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_label_candidate_review_decision_preview,
        cex_label_candidate_review_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/cex-label-candidate-review-queue/decision/apply")
async def rpc_cex_label_candidate_review_queue_decision_apply(
    cex_label_candidate_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_label_candidate_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_candidate_review_id_required")
    if not dry_run and confirm != "APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_cex_label_candidate_review_decision,
        cex_label_candidate_review_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-label-candidate-review-queue/label-creation-contract")
@router.post("/rpc/cex-label-candidate-review-queue/label-creation-contract")
async def rpc_cex_label_candidate_review_queue_label_creation_contract(
    cex_label_candidate_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_label_candidate_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_candidate_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_label_creation_contract,
        cex_label_candidate_review_id,
        dry_run,
    )


@router.get("/rpc/cex-label-creation-queue-schema-plan")
@router.post("/rpc/cex-label-creation-queue-schema-plan")
async def rpc_cex_label_creation_queue_schema_plan(
    cex_label_candidate_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_label_candidate_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_candidate_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_label_creation_queue_schema_plan,
        cex_label_candidate_review_id,
        dry_run,
    )


@router.post("/rpc/cex-label-creation-review-queue/create")
async def rpc_create_cex_label_creation_review_queue(
    cex_label_candidate_review_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_label_candidate_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_candidate_review_id_required")
    if not dry_run and confirm != "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_cex_label_creation_review_queue,
        cex_label_candidate_review_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/cex-label-creation-review-queue/insert")
async def rpc_insert_cex_label_creation_review(
    cex_label_candidate_review_id: int | None = None,
    expected_label_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_label_candidate_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_candidate_review_id_required")
    if not dry_run and confirm != "INSERT_CEX_LABEL_CREATION_REVIEW":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_CEX_LABEL_CREATION_REVIEW_required",
        )
    if not dry_run and not expected_label_dedupe_key:
        raise HTTPException(status_code=400, detail="expected_label_dedupe_key_required")
    return await asyncio.to_thread(
        insert_cex_label_creation_review,
        cex_label_candidate_review_id,
        expected_label_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-label-creation-review-queue/review")
@router.post("/rpc/cex-label-creation-review-queue/review")
async def rpc_cex_label_creation_review_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_label_creation_review_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/cex-label-creation-review-queue/decision-preview")
async def rpc_cex_label_creation_review_queue_decision_preview(
    cex_label_creation_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_label_creation_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_creation_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_label_creation_review_decision_preview,
        cex_label_creation_review_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/cex-label-creation-review-queue/decision/apply")
async def rpc_cex_label_creation_review_queue_decision_apply(
    cex_label_creation_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_label_creation_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_creation_review_id_required")
    if not dry_run and confirm != "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_CEX_LABEL_CREATION_REVIEW_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_cex_label_creation_review_decision,
        cex_label_creation_review_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-label-creation-review-queue/final-label-write-contract")
@router.post("/rpc/cex-label-creation-review-queue/final-label-write-contract")
async def rpc_cex_label_creation_review_queue_final_label_write_contract(
    cex_label_creation_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_label_creation_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_creation_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_write_contract,
        cex_label_creation_review_id,
        dry_run,
    )


@router.get("/rpc/cex-final-label-write-queue-schema-plan")
@router.post("/rpc/cex-final-label-write-queue-schema-plan")
async def rpc_cex_final_label_write_queue_schema_plan(
    cex_label_creation_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_label_creation_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_creation_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_write_queue_schema_plan,
        cex_label_creation_review_id,
        dry_run,
    )


@router.post("/rpc/cex-final-label-write-queue/create")
async def rpc_create_cex_final_label_write_review_queue(
    cex_label_creation_review_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_label_creation_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_creation_review_id_required")
    if not dry_run and confirm != "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_cex_final_label_write_review_queue,
        cex_label_creation_review_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/cex-final-label-write-queue/insert")
async def rpc_insert_cex_final_label_write_review(
    cex_label_creation_review_id: int | None = None,
    expected_final_label_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_label_creation_review_id is None:
        raise HTTPException(status_code=400, detail="cex_label_creation_review_id_required")
    if not dry_run and confirm != "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_CEX_FINAL_LABEL_WRITE_REVIEW_required",
        )
    if not dry_run and not str(expected_final_label_dedupe_key or "").strip():
        raise HTTPException(status_code=400, detail="expected_final_label_dedupe_key_required")
    return await asyncio.to_thread(
        insert_cex_final_label_write_review,
        cex_label_creation_review_id,
        expected_final_label_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-final-label-write-queue/review")
@router.post("/rpc/cex-final-label-write-queue/review")
async def rpc_cex_final_label_write_review_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_write_review_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/cex-final-label-write-queue/decision-preview")
async def rpc_cex_final_label_write_queue_decision_preview(
    cex_final_label_write_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_write_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_write_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_write_decision_preview,
        cex_final_label_write_review_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/cex-final-label-write-queue/decision/apply")
async def rpc_cex_final_label_write_queue_decision_apply(
    cex_final_label_write_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_write_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_write_review_id_required")
    if not dry_run and confirm != "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_cex_final_label_write_decision,
        cex_final_label_write_review_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-final-label-write-queue/execution-contract")
@router.post("/rpc/cex-final-label-write-queue/execution-contract")
async def rpc_cex_final_label_write_queue_execution_contract(
    cex_final_label_write_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_write_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_write_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_write_execution_contract,
        cex_final_label_write_review_id,
        dry_run,
    )


@router.get("/rpc/cex-final-label-execution-queue-schema-plan")
@router.post("/rpc/cex-final-label-execution-queue-schema-plan")
async def rpc_cex_final_label_execution_queue_schema_plan(
    cex_final_label_write_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_write_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_write_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_execution_queue_schema_plan,
        cex_final_label_write_review_id,
        dry_run,
    )


@router.post("/rpc/cex-final-label-execution-queue/create")
async def rpc_create_cex_final_label_execution_review_queue(
    cex_final_label_write_review_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_write_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_write_review_id_required")
    if not dry_run and confirm != "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE_required",
        )
    return await asyncio.to_thread(
        create_cex_final_label_execution_review_queue,
        cex_final_label_write_review_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/cex-final-label-execution-queue/insert")
async def rpc_insert_cex_final_label_execution_review(
    cex_final_label_write_review_id: int | None = None,
    expected_final_label_execution_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_write_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_write_review_id_required")
    if not dry_run and confirm != "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW":
        raise HTTPException(
            status_code=400,
            detail="confirm_INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW_required",
        )
    if not dry_run and not str(expected_final_label_execution_dedupe_key or "").strip():
        raise HTTPException(status_code=400, detail="expected_final_label_execution_dedupe_key_required")
    return await asyncio.to_thread(
        insert_cex_final_label_execution_review,
        cex_final_label_write_review_id,
        expected_final_label_execution_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-final-label-execution-queue/review")
@router.post("/rpc/cex-final-label-execution-queue/review")
async def rpc_cex_final_label_execution_review_queue_review(
    status: str | None = "pending_admin_review",
    token_symbol: str | None = None,
    market_type: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_execution_review_queue_review,
        status,
        token_symbol,
        market_type,
        limit,
        dry_run,
    )


@router.post("/rpc/cex-final-label-execution-queue/decision-preview")
async def rpc_cex_final_label_execution_queue_decision_preview(
    cex_final_label_execution_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_execution_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_execution_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_execution_decision_preview,
        cex_final_label_execution_review_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/cex-final-label-execution-queue/decision/apply")
async def rpc_cex_final_label_execution_queue_decision_apply(
    cex_final_label_execution_review_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_execution_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_execution_review_id_required")
    if not dry_run and confirm != "APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_cex_final_label_execution_decision,
        cex_final_label_execution_review_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/cex-final-label-execution-queue/final-label-write-safety-checkpoint")
@router.post("/rpc/cex-final-label-execution-queue/final-label-write-safety-checkpoint")
async def rpc_cex_final_label_execution_queue_final_label_write_safety_checkpoint(
    cex_final_label_execution_review_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if cex_final_label_execution_review_id is None:
        raise HTTPException(status_code=400, detail="cex_final_label_execution_review_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_cex_final_label_write_safety_checkpoint,
        cex_final_label_execution_review_id,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping/rollback-artifact-preview")
async def rpc_dex_router_venue_mapping_rollback_artifact_preview(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_rollback_artifact_preview,
        evidence_id,
        venue_name,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping/rollback-artifact-schema-plan")
async def rpc_dex_router_venue_mapping_rollback_artifact_schema_plan(
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_rollback_artifact_schema_plan,
        dry_run,
    )


@router.post("/rpc/dex-router-venue-mapping/rollback-artifact-storage/create")
async def rpc_create_dex_router_venue_mapping_rollback_artifact_storage(
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT_STORAGE":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT_STORAGE_required",
        )
    return await asyncio.to_thread(
        create_dex_router_venue_mapping_rollback_artifact_storage,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-venue-mapping/rollback-artifact/create")
async def rpc_create_dex_router_venue_mapping_rollback_artifact(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT_required",
        )
    return await asyncio.to_thread(
        create_dex_router_venue_mapping_rollback_artifact,
        evidence_id,
        venue_name,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-router-venue-mapping/rollback-artifact/refresh")
async def rpc_refresh_dex_router_venue_mapping_rollback_artifact(
    evidence_id: int,
    venue_name: str,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "REFRESH_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT":
        raise HTTPException(
            status_code=400,
            detail="confirm_REFRESH_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT_required",
        )
    return await asyncio.to_thread(
        refresh_dex_router_venue_mapping_rollback_artifact,
        evidence_id,
        venue_name,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-router-venue-mapping/rollback-artifacts")
async def rpc_dex_router_venue_mapping_rollback_artifacts(
    evidence_id: int,
    venue_name: str,
    limit: int = 20,
    _: None = Depends(_require_data_admin),
):
    return await asyncio.to_thread(
        get_dex_router_venue_mapping_rollback_artifacts,
        evidence_id,
        venue_name,
        limit,
    )


@router.get("/rpc/unknown-router-source-gap-report")
async def rpc_unknown_router_source_gap_report(
    chain: str | None = None,
    limit: int = 10,
    timeout: int = 6,
    include_public_evidence: bool = True,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_source_gap_report,
        chain,
        limit,
        timeout,
        include_public_evidence,
    )


@router.get("/rpc/unknown-router-official-source-worklist")
async def rpc_unknown_router_official_source_worklist(
    chain: str | None = None,
    limit: int = 10,
    timeout: int = 6,
    include_public_evidence: bool = True,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_official_source_worklist,
        chain,
        limit,
        timeout,
        include_public_evidence,
    )


@router.get("/rpc/unknown-router-proof-dossiers")
async def rpc_unknown_router_proof_dossiers(
    chain: str | None = None,
    limit: int = 10,
    timeout: int = 6,
    include_public_evidence: bool = True,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_proof_dossiers,
        chain,
        limit,
        timeout,
        include_public_evidence,
    )


@router.get("/rpc/unknown-router-official-source-acquisition-queue")
async def rpc_unknown_router_official_source_acquisition_queue(
    chain: str | None = None,
    limit: int = 10,
    timeout: int = 6,
    include_public_evidence: bool = True,
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_official_source_acquisition_queue,
        chain,
        limit,
        timeout,
        include_public_evidence,
    )


@router.get("/rpc/unknown-router-official-source-search-scan")
async def rpc_unknown_router_official_source_search_scan(
    chain: str | None = None,
    limit: int = 6,
    timeout: int = 6,
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_official_source_search_scan,
        chain,
        limit,
        timeout,
    )


@router.get("/rpc/unknown-router-official-source-rule-checkpoint")
@router.post("/rpc/unknown-router-official-source-rule-checkpoint")
async def rpc_unknown_router_official_source_rule_checkpoint(
    chain: str | None = "bsc",
    router_addr: str | None = None,
    proposed_venue: str | None = None,
    limit: int = 50,
    timeout: int = 6,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_official_source_rule_checkpoint,
        chain,
        router_addr,
        proposed_venue,
        limit,
        timeout,
        dry_run,
    )


@router.get("/rpc/unknown-router-creator-identity-scan")
async def rpc_unknown_router_creator_identity_scan(
    chain: str | None = None,
    limit: int = 8,
    timeout: int = 6,
):
    if limit > 20:
        raise HTTPException(status_code=400, detail="limit_max_20")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_creator_identity_scan,
        chain,
        limit,
        timeout,
    )


@router.get("/rpc/unknown-router-creator-identity-acquisition-queue")
async def rpc_unknown_router_creator_identity_acquisition_queue(
    chain: str | None = None,
    limit: int = 8,
    timeout: int = 6,
    include_public_evidence: bool = True,
):
    if limit > 20:
        raise HTTPException(status_code=400, detail="limit_max_20")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_creator_identity_acquisition_queue,
        chain,
        limit,
        timeout,
        include_public_evidence,
    )


@router.get("/rpc/unknown-router-creator-identity-evidence-scan")
async def rpc_unknown_router_creator_identity_evidence_scan(
    chain: str | None = None,
    limit: int = 6,
    timeout: int = 6,
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_creator_identity_evidence_scan,
        chain,
        limit,
        timeout,
    )


@router.get("/rpc/unknown-router-creator-identity-source-search-scan")
async def rpc_unknown_router_creator_identity_source_search_scan(
    chain: str | None = None,
    limit: int = 4,
    timeout: int = 6,
):
    if limit > 8:
        raise HTTPException(status_code=400, detail="limit_max_8")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_creator_identity_source_search_scan,
        chain,
        limit,
        timeout,
    )


@router.get("/rpc/unknown-router-interaction-fingerprints")
async def rpc_unknown_router_interaction_fingerprints(
    chain: str | None = None,
    limit: int = 8,
):
    if limit > 20:
        raise HTTPException(status_code=400, detail="limit_max_20")
    return await asyncio.to_thread(
        get_unknown_router_interaction_fingerprints,
        chain,
        limit,
    )


@router.get("/rpc/unknown-router-method-selector-scan")
async def rpc_unknown_router_method_selector_scan(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 5,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 10:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_10")
    return await asyncio.to_thread(
        get_unknown_router_method_selector_scan,
        chain,
        limit,
        tx_limit_per_router,
    )


@router.get("/rpc/unknown-router-selector-signature-resolution-scan")
async def rpc_unknown_router_selector_signature_resolution_scan(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 5,
    timeout: int = 6,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 10:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_selector_signature_resolution_scan,
        chain,
        limit,
        tx_limit_per_router,
        timeout,
    )


@router.get("/rpc/unknown-router-verified-contract-source-scan")
async def rpc_unknown_router_verified_contract_source_scan(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 5,
    timeout: int = 6,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 10:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_verified_contract_source_scan,
        chain,
        limit,
        tx_limit_per_router,
        timeout,
    )


@router.get("/rpc/unknown-router-proxy-implementation-scan")
async def rpc_unknown_router_proxy_implementation_scan(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 5,
    timeout: int = 6,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 10:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_proxy_implementation_scan,
        chain,
        limit,
        tx_limit_per_router,
        timeout,
    )


@router.get("/rpc/unknown-router-internal-call-trace-scan")
async def rpc_unknown_router_internal_call_trace_scan(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 3,
    max_calls_per_tx: int = 80,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    if max_calls_per_tx > 200:
        raise HTTPException(status_code=400, detail="max_calls_per_tx_max_200")
    return await asyncio.to_thread(
        get_unknown_router_internal_call_trace_scan,
        chain,
        limit,
        tx_limit_per_router,
        max_calls_per_tx,
    )


@router.get("/rpc/unknown-router-internal-transaction-fallback-scan")
async def rpc_unknown_router_internal_transaction_fallback_scan(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 3,
    timeout: int = 6,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_internal_transaction_fallback_scan,
        chain,
        limit,
        tx_limit_per_router,
        timeout,
    )


@router.get("/rpc/token-market-recent-unknown-router-internal-transaction-fallback-scan")
async def rpc_token_market_recent_unknown_router_internal_transaction_fallback_scan(
    chain: str = "bsc",
    block_window: int = 2_000,
    limit: int = 6,
    timeout: int = 6,
    external_fetch: bool = False,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 10_000:
        raise HTTPException(status_code=400, detail="block_window_max_10000")
    if limit > 20:
        raise HTTPException(status_code=400, detail="limit_max_20")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_token_market_recent_unknown_router_internal_transaction_fallback_scan,
        chain,
        block_window,
        limit,
        timeout,
        external_fetch,
        dry_run,
    )


@router.get("/rpc/unknown-router-internal-counterparty-research-packages")
async def rpc_unknown_router_internal_counterparty_research_packages(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 3,
    counterparties_per_router: int = 5,
    timeout: int = 6,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    if counterparties_per_router > 10:
        raise HTTPException(status_code=400, detail="counterparties_per_router_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_internal_counterparty_research_packages,
        chain,
        limit,
        tx_limit_per_router,
        counterparties_per_router,
        timeout,
    )


@router.get("/rpc/unknown-router-internal-counterparty-research-packages-official-review")
async def rpc_unknown_router_internal_counterparty_research_packages_official_review(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 3,
    counterparties_per_router: int = 5,
    timeout: int = 6,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    if counterparties_per_router > 10:
        raise HTTPException(status_code=400, detail="counterparties_per_router_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_internal_counterparty_research_packages_official_review,
        chain,
        limit,
        tx_limit_per_router,
        counterparties_per_router,
        timeout,
    )


@router.get("/rpc/unknown-router-internal-counterparty-router-source-search-scan")
async def rpc_unknown_router_internal_counterparty_router_source_search_scan(
    chain: str | None = None,
    limit: int = 6,
    tx_limit_per_router: int = 3,
    counterparties_per_router: int = 5,
    timeout: int = 6,
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    if counterparties_per_router > 10:
        raise HTTPException(status_code=400, detail="counterparties_per_router_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_internal_counterparty_router_source_search_scan,
        chain,
        limit,
        tx_limit_per_router,
        counterparties_per_router,
        timeout,
    )


@router.get("/rpc/unknown-router-public-identity-acquisition-scan")
async def rpc_unknown_router_public_identity_acquisition_scan(
    chain: str | None = None,
    limit: int = 6,
    timeout: int = 6,
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_router_public_identity_acquisition_scan,
        chain,
        limit,
        timeout,
    )


@router.get("/rpc/unknown-router-evidence-package")
async def rpc_unknown_router_evidence_package(
    chain: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    include_live_scans: bool = False,
    timeout: int = 6,
    tx_limit_per_router: int = 2,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    return await asyncio.to_thread(
        get_unknown_router_evidence_package,
        chain,
        limit,
        dry_run,
        include_live_scans,
        timeout,
        tx_limit_per_router,
    )


@router.get("/rpc/unknown-router-role-classification-checkpoint")
async def rpc_unknown_router_role_classification_checkpoint(
    chain: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    include_live_scans: bool = False,
    timeout: int = 6,
    tx_limit_per_router: int = 2,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    return await asyncio.to_thread(
        get_unknown_router_role_classification_checkpoint,
        chain,
        limit,
        dry_run,
        include_live_scans,
        timeout,
        tx_limit_per_router,
    )


@router.get("/rpc/unknown-router-role-exclusion-plan")
async def rpc_unknown_router_role_exclusion_plan(
    chain: str | None = None,
    limit: int = 5,
    dry_run: bool = True,
    include_live_scans: bool = False,
    timeout: int = 6,
    tx_limit_per_router: int = 2,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    return await asyncio.to_thread(
        get_unknown_router_role_exclusion_plan,
        chain,
        limit,
        dry_run,
        include_live_scans,
        timeout,
        tx_limit_per_router,
    )


@router.get("/rpc/unknown-dex-route-provenance-workbench")
@router.post("/rpc/unknown-dex-route-provenance-workbench")
async def rpc_unknown_dex_route_provenance_workbench(
    chain: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    include_live_scans: bool = False,
    include_code_fingerprints: bool = False,
    timeout: int = 6,
    tx_limit_per_router: int = 2,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if tx_limit_per_router > 6:
        raise HTTPException(status_code=400, detail="tx_limit_per_router_max_6")
    return await asyncio.to_thread(
        get_unknown_dex_route_provenance_workbench,
        chain,
        limit,
        dry_run,
        include_live_scans,
        include_code_fingerprints,
        timeout,
        tx_limit_per_router,
    )


@router.get("/rpc/unknown-dex-route-provenance-dossier")
@router.post("/rpc/unknown-dex-route-provenance-dossier")
async def rpc_unknown_dex_route_provenance_dossier(
    chain: str | None = "bsc",
    router_addr: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    include_live_scans: bool = False,
    include_code_fingerprints: bool = False,
    tx_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_limit > 25:
        raise HTTPException(status_code=400, detail="tx_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_route_provenance_dossier,
        chain,
        router_addr,
        limit,
        dry_run,
        include_live_scans,
        include_code_fingerprints,
        tx_limit,
    )


@router.get("/rpc/unknown-dex-intermediary-path-repair-plan")
@router.post("/rpc/unknown-dex-intermediary-path-repair-plan")
async def rpc_unknown_dex_intermediary_path_repair_plan(
    chain: str | None = "bsc",
    router_addr: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    include_live_scans: bool = False,
    include_code_fingerprints: bool = False,
    tx_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_limit > 25:
        raise HTTPException(status_code=400, detail="tx_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_intermediary_path_repair_plan,
        chain,
        router_addr,
        limit,
        dry_run,
        include_live_scans,
        include_code_fingerprints,
        tx_limit,
    )


@router.get("/rpc/unknown-dex-intermediary-bounded-trace-collection")
@router.post("/rpc/unknown-dex-intermediary-bounded-trace-collection")
async def rpc_unknown_dex_intermediary_bounded_trace_collection(
    chain: str | None = "bsc",
    router_addr: str | None = None,
    limit: int = 10,
    tx_limit: int = 8,
    max_trace_calls: int = 3,
    max_calls_per_tx: int = 80,
    dry_run: bool = True,
    trace_enabled: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_limit > 25:
        raise HTTPException(status_code=400, detail="tx_limit_max_25")
    if max_trace_calls > 10:
        raise HTTPException(status_code=400, detail="max_trace_calls_max_10")
    if max_calls_per_tx > 200:
        raise HTTPException(status_code=400, detail="max_calls_per_tx_max_200")
    return await asyncio.to_thread(
        run_unknown_dex_intermediary_bounded_trace_collection,
        chain,
        router_addr,
        limit,
        tx_limit,
        max_trace_calls,
        max_calls_per_tx,
        dry_run,
        trace_enabled,
        confirm,
    )


@router.get("/rpc/unknown-dex-intermediary-internal-transaction-fallback")
@router.post("/rpc/unknown-dex-intermediary-internal-transaction-fallback")
async def rpc_unknown_dex_intermediary_internal_transaction_fallback(
    chain: str | None = "bsc",
    router_addr: str | None = None,
    limit: int = 10,
    tx_limit: int = 8,
    max_external_calls: int = 3,
    timeout: int = 6,
    dry_run: bool = True,
    external_fetch: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_limit > 25:
        raise HTTPException(status_code=400, detail="tx_limit_max_25")
    if max_external_calls > 10:
        raise HTTPException(status_code=400, detail="max_external_calls_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        run_unknown_dex_intermediary_internal_transaction_fallback,
        chain,
        router_addr,
        limit,
        tx_limit,
        max_external_calls,
        timeout,
        dry_run,
        external_fetch,
        confirm,
    )


@router.get("/rpc/unknown-dex-traceability-candidate-selector")
@router.post("/rpc/unknown-dex-traceability-candidate-selector")
async def rpc_unknown_dex_traceability_candidate_selector(
    chain: str | None = "bsc",
    block_window: int = 10_000,
    limit: int = 8,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_traceability_candidate_selector,
        chain,
        block_window,
        limit,
        dry_run,
    )


@router.get("/rpc/unknown-dex-local-transfer-path-workbench")
@router.post("/rpc/unknown-dex-local-transfer-path-workbench")
async def rpc_unknown_dex_local_transfer_path_workbench(
    chain: str | None = "bsc",
    block_window: int = 10_000,
    limit: int = 8,
    tx_transfer_limit: int = 80,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    return await asyncio.to_thread(
        get_unknown_dex_local_transfer_path_workbench,
        chain,
        block_window,
        limit,
        tx_transfer_limit,
        dry_run,
    )


@router.get("/rpc/unknown-dex-local-path-official-source-repair-plan")
@router.post("/rpc/unknown-dex-local-path-official-source-repair-plan")
async def rpc_unknown_dex_local_path_official_source_repair_plan(
    chain: str | None = "bsc",
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    return await asyncio.to_thread(
        get_unknown_dex_local_path_official_source_repair_plan,
        chain,
        block_window,
        limit,
        tx_transfer_limit,
        dry_run,
    )


@router.get("/rpc/unknown-dex-local-path-official-source-search-scan")
@router.post("/rpc/unknown-dex-local-path-official-source-search-scan")
async def rpc_unknown_dex_local_path_official_source_search_scan(
    chain: str | None = "bsc",
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_targets: int = 4,
    queries_per_target: int = 2,
    max_results_per_query: int = 3,
    timeout: int = 6,
    dry_run: bool = True,
    allow_external: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_targets > 12:
        raise HTTPException(status_code=400, detail="max_targets_max_12")
    if queries_per_target > 4:
        raise HTTPException(status_code=400, detail="queries_per_target_max_4")
    if max_results_per_query > 5:
        raise HTTPException(status_code=400, detail="max_results_per_query_max_5")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_local_path_official_source_search_scan,
        chain,
        block_window,
        limit,
        tx_transfer_limit,
        max_targets,
        queries_per_target,
        max_results_per_query,
        timeout,
        dry_run,
        allow_external,
    )


@router.get("/rpc/unknown-dex-local-path-explorer-identity-hint-scan")
@router.post("/rpc/unknown-dex-local-path-explorer-identity-hint-scan")
async def rpc_unknown_dex_local_path_explorer_identity_hint_scan(
    chain: str | None = "bsc",
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_targets: int = 4,
    timeout: int = 6,
    dry_run: bool = True,
    allow_external: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_targets > 12:
        raise HTTPException(status_code=400, detail="max_targets_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_local_path_explorer_identity_hint_scan,
        chain,
        block_window,
        limit,
        tx_transfer_limit,
        max_targets,
        timeout,
        dry_run,
        allow_external,
    )


@router.get("/rpc/unknown-dex-local-path-pool-factory-inference-checkpoint")
@router.post("/rpc/unknown-dex-local-path-pool-factory-inference-checkpoint")
async def rpc_unknown_dex_local_path_pool_factory_inference_checkpoint(
    chain: str | None = "bsc",
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_local_path_pool_factory_inference_checkpoint,
        chain,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        timeout,
        dry_run,
        allow_rpc,
    )


@router.get("/rpc/unknown-dex-factory-official-source-proof-checkpoint")
@router.post("/rpc/unknown-dex-factory-official-source-proof-checkpoint")
async def rpc_unknown_dex_factory_official_source_proof_checkpoint(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    queries_per_factory: int = 3,
    max_results_per_query: int = 3,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    allow_external: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if queries_per_factory > 5:
        raise HTTPException(status_code=400, detail="queries_per_factory_max_5")
    if max_results_per_query > 5:
        raise HTTPException(status_code=400, detail="max_results_per_query_max_5")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_factory_official_source_proof_checkpoint,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        queries_per_factory,
        max_results_per_query,
        timeout,
        dry_run,
        allow_rpc,
        allow_external,
    )


@router.get("/rpc/unknown-dex-deployment-registry-paircreated-proof-checkpoint")
@router.post("/rpc/unknown-dex-deployment-registry-paircreated-proof-checkpoint")
async def rpc_unknown_dex_deployment_registry_paircreated_proof_checkpoint(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_deployment_registry_paircreated_proof_checkpoint,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        timeout,
        dry_run,
        allow_rpc,
    )


@router.get("/rpc/unknown-dex-paircreated-log-replay-plan")
@router.post("/rpc/unknown-dex-paircreated-log-replay-plan")
async def rpc_unknown_dex_paircreated_log_replay_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_log_replay_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        timeout,
        dry_run,
        allow_rpc,
    )


@router.get("/rpc/unknown-dex-paircreated-bounded-replay-dry-run")
@router.post("/rpc/unknown-dex-paircreated-bounded-replay-dry-run")
async def rpc_unknown_dex_paircreated_bounded_replay_dry_run(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    log_chunk_blocks: int = 5_000,
    max_log_chunks_per_candidate: int = 1,
    max_rpc_calls: int = 12,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if log_chunk_blocks > 50_000:
        raise HTTPException(status_code=400, detail="log_chunk_blocks_max_50000")
    if max_log_chunks_per_candidate > 10:
        raise HTTPException(status_code=400, detail="max_log_chunks_per_candidate_max_10")
    if max_rpc_calls > 50:
        raise HTTPException(status_code=400, detail="max_rpc_calls_max_50")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_bounded_replay_dry_run,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        log_chunk_blocks,
        max_log_chunks_per_candidate,
        max_rpc_calls,
        timeout,
        dry_run,
        allow_rpc,
    )


@router.get("/rpc/unknown-dex-paircreated-provider-indexer-capability-audit")
@router.post("/rpc/unknown-dex-paircreated-provider-indexer-capability-audit")
async def rpc_unknown_dex_paircreated_provider_indexer_capability_audit(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    log_chunk_blocks: int = 5_000,
    max_rpc_providers: int = 4,
    max_rpc_calls: int = 32,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    allow_external: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if log_chunk_blocks > 50_000:
        raise HTTPException(status_code=400, detail="log_chunk_blocks_max_50000")
    if max_rpc_providers > 8:
        raise HTTPException(status_code=400, detail="max_rpc_providers_max_8")
    if max_rpc_calls > 100:
        raise HTTPException(status_code=400, detail="max_rpc_calls_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_provider_indexer_capability_audit,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        log_chunk_blocks,
        max_rpc_providers,
        max_rpc_calls,
        timeout,
        dry_run,
        allow_rpc,
        allow_external,
    )


@router.get("/rpc/unknown-dex-paircreated-blockscout-indexer-bounded-lookup-dry-run")
@router.post("/rpc/unknown-dex-paircreated-blockscout-indexer-bounded-lookup-dry-run")
async def rpc_unknown_dex_paircreated_blockscout_indexer_bounded_lookup_dry_run(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    allow_rpc_preflight: bool = True,
    max_indexer_calls: int = 4,
    timeout: int = 6,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if max_indexer_calls > 12:
        raise HTTPException(status_code=400, detail="max_indexer_calls_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_blockscout_indexer_bounded_lookup_dry_run,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        allow_rpc_preflight,
        max_indexer_calls,
        timeout,
        dry_run,
        allow_external,
        confirm,
    )


@router.get("/rpc/unknown-dex-paircreated-sqd-portal-bounded-lookup-dry-run")
@router.post("/rpc/unknown-dex-paircreated-sqd-portal-bounded-lookup-dry-run")
async def rpc_unknown_dex_paircreated_sqd_portal_bounded_lookup_dry_run(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    allow_rpc_preflight: bool = True,
    max_indexer_calls: int = 4,
    timeout: int = 6,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if max_indexer_calls > 12:
        raise HTTPException(status_code=400, detail="max_indexer_calls_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_sqd_portal_bounded_lookup_dry_run,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        allow_rpc_preflight,
        max_indexer_calls,
        timeout,
        dry_run,
        allow_external,
        confirm,
    )


@router.get("/rpc/unknown-dex-paircreated-evidence-persistence-schema-plan")
@router.post("/rpc/unknown-dex-paircreated-evidence-persistence-schema-plan")
async def rpc_unknown_dex_paircreated_evidence_persistence_schema_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    allow_rpc_preflight: bool = True,
    max_indexer_calls: int = 4,
    timeout: int = 6,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if max_indexer_calls > 12:
        raise HTTPException(status_code=400, detail="max_indexer_calls_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_evidence_persistence_schema_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        allow_rpc_preflight,
        max_indexer_calls,
        timeout,
        dry_run,
        allow_external,
        confirm,
    )


@router.post("/rpc/unknown-dex-paircreated-evidence/create")
@router.post("/rpc/unknown-dex-paircreated-evidence-persistence/create")
async def rpc_create_unknown_dex_paircreated_evidence(
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    return await asyncio.to_thread(
        create_unknown_dex_paircreated_evidence,
        dry_run,
        confirm,
    )


@router.post("/rpc/unknown-dex-paircreated-evidence/insert")
@router.post("/rpc/unknown-dex-paircreated-evidence-persistence/insert")
async def rpc_insert_unknown_dex_paircreated_evidence(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    allow_rpc_preflight: bool = True,
    max_indexer_calls: int = 4,
    timeout: int = 6,
    expected_paircreated_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    allow_external: bool = False,
    source_confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if max_indexer_calls > 12:
        raise HTTPException(status_code=400, detail="max_indexer_calls_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if not dry_run and confirm != "INSERT_DEX_PAIRCREATED_EVIDENCE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_DEX_PAIRCREATED_EVIDENCE_required")
    return await asyncio.to_thread(
        insert_unknown_dex_paircreated_evidence,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        allow_rpc_preflight,
        max_indexer_calls,
        timeout,
        expected_paircreated_dedupe_key,
        dry_run,
        confirm,
        allow_external,
        source_confirm,
    )


@router.get("/rpc/unknown-dex-paircreated-evidence/review")
@router.post("/rpc/unknown-dex-paircreated-evidence/review")
@router.get("/rpc/unknown-dex-paircreated-evidence-review-queue")
@router.post("/rpc/unknown-dex-paircreated-evidence-review-queue")
async def rpc_unknown_dex_paircreated_evidence_review_queue(
    status: str | None = "pending_admin_review",
    pair_address: str | None = None,
    factory_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_evidence_review_queue,
        status,
        pair_address,
        factory_address,
        limit,
        dry_run,
    )


@router.post("/rpc/unknown-dex-paircreated-evidence/decision-preview")
@router.post("/rpc/unknown-dex-paircreated-evidence-review-queue/decision-preview")
async def rpc_unknown_dex_paircreated_evidence_decision_preview(
    paircreated_evidence_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if paircreated_evidence_id is None:
        raise HTTPException(status_code=400, detail="paircreated_evidence_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_evidence_decision_preview,
        paircreated_evidence_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/unknown-dex-paircreated-evidence/decision/apply")
@router.post("/rpc/unknown-dex-paircreated-evidence-review-queue/decision/apply")
async def rpc_unknown_dex_paircreated_evidence_decision_apply(
    paircreated_evidence_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if paircreated_evidence_id is None:
        raise HTTPException(status_code=400, detail="paircreated_evidence_id_required")
    if not dry_run and confirm != "APPLY_DEX_PAIRCREATED_EVIDENCE_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_DEX_PAIRCREATED_EVIDENCE_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_unknown_dex_paircreated_evidence_decision,
        paircreated_evidence_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-mapping-review-contract")
@router.post("/rpc/dex-mapping-review-contract")
async def rpc_dex_mapping_review_contract(
    paircreated_evidence_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if paircreated_evidence_id is None:
        raise HTTPException(status_code=400, detail="paircreated_evidence_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_mapping_review_contract,
        paircreated_evidence_id,
        dry_run,
    )


@router.get("/rpc/dex-mapping-review-queue-schema-plan")
@router.post("/rpc/dex-mapping-review-queue-schema-plan")
async def rpc_dex_mapping_review_queue_schema_plan(
    paircreated_evidence_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if paircreated_evidence_id is None:
        raise HTTPException(status_code=400, detail="paircreated_evidence_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_mapping_review_queue_schema_plan,
        paircreated_evidence_id,
        dry_run,
    )


@router.post("/rpc/dex-mapping-review-queue/create")
async def rpc_create_dex_mapping_review_queue(
    paircreated_evidence_id: int | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if paircreated_evidence_id is None:
        raise HTTPException(status_code=400, detail="paircreated_evidence_id_required")
    if not dry_run and confirm != "CREATE_DEX_MAPPING_REVIEW_QUEUE":
        raise HTTPException(status_code=400, detail="confirm_CREATE_DEX_MAPPING_REVIEW_QUEUE_required")
    return await asyncio.to_thread(
        create_dex_mapping_review_queue,
        paircreated_evidence_id,
        dry_run,
        confirm,
    )


@router.post("/rpc/dex-mapping-review-queue/insert")
async def rpc_insert_dex_mapping_review_queue(
    paircreated_evidence_id: int | None = None,
    expected_mapping_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if paircreated_evidence_id is None:
        raise HTTPException(status_code=400, detail="paircreated_evidence_id_required")
    if not dry_run and not expected_mapping_dedupe_key:
        raise HTTPException(status_code=400, detail="expected_mapping_dedupe_key_required")
    if not dry_run and confirm != "INSERT_DEX_MAPPING_REVIEW":
        raise HTTPException(status_code=400, detail="confirm_INSERT_DEX_MAPPING_REVIEW_required")
    return await asyncio.to_thread(
        insert_dex_mapping_review_queue,
        paircreated_evidence_id,
        expected_mapping_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-local-event-reader-proof-of-shape-plan")
@router.post("/rpc/dex-local-event-reader-proof-of-shape-plan")
async def rpc_dex_local_event_reader_proof_of_shape_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_local_event_reader_proof_of_shape_plan,
        chain,
        factory_address,
        dry_run,
    )


@router.get("/rpc/dex-local-event-reader-checkpoint-raw-schema-plan")
@router.post("/rpc/dex-local-event-reader-checkpoint-raw-schema-plan")
async def rpc_dex_local_event_reader_checkpoint_raw_schema_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_local_event_reader_checkpoint_raw_schema_plan,
        chain,
        factory_address,
        dry_run,
    )


@router.post("/rpc/dex-local-event-reader-checkpoint-raw/create")
async def rpc_create_dex_local_event_reader_checkpoint_raw_tables(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_DEX_LOCAL_EVENT_READER_CHECKPOINT_RAW_TABLES":
        raise HTTPException(
            status_code=400,
            detail="confirm_CREATE_DEX_LOCAL_EVENT_READER_CHECKPOINT_RAW_TABLES_required",
        )
    return await asyncio.to_thread(
        create_dex_local_event_reader_checkpoint_raw_tables,
        chain,
        factory_address,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-local-event-reader-run-contract")
@router.post("/rpc/dex-local-event-reader-run-contract")
async def rpc_dex_local_event_reader_run_contract(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    dex_mapping_review_id: int | None = None,
    from_block: int | None = None,
    to_block: int | None = None,
    event_names: str | None = None,
    max_block_span: int = 1_000,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_block_span > 5_000:
        raise HTTPException(status_code=400, detail="max_block_span_too_large")
    return await asyncio.to_thread(
        get_dex_local_event_reader_run_contract,
        chain,
        factory_address,
        dex_mapping_review_id,
        from_block,
        to_block,
        event_names,
        max_block_span,
        dry_run,
    )


@router.post("/rpc/dex-local-event-reader-run/insert")
async def rpc_insert_dex_local_event_reader_run(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    dex_mapping_review_id: int | None = None,
    from_block: int | None = None,
    to_block: int | None = None,
    event_names: str | None = None,
    max_block_span: int = 1_000,
    expected_run_dedupe_key: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if max_block_span > 5_000:
        raise HTTPException(status_code=400, detail="max_block_span_too_large")
    if not dry_run and confirm != "INSERT_DEX_LOCAL_EVENT_READER_RUN":
        raise HTTPException(status_code=400, detail="confirm_INSERT_DEX_LOCAL_EVENT_READER_RUN_required")
    return await asyncio.to_thread(
        insert_dex_local_event_reader_run,
        chain,
        factory_address,
        dex_mapping_review_id,
        from_block,
        to_block,
        event_names,
        max_block_span,
        expected_run_dedupe_key,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-local-event-reader-run/execution-contract")
@router.post("/rpc/dex-local-event-reader-run/execution-contract")
async def rpc_dex_local_event_reader_execution_contract(
    event_reader_run_id: int | None = None,
    dry_run: bool = True,
    max_rpc_calls: int = 25,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_rpc_calls > 100:
        raise HTTPException(status_code=400, detail="max_rpc_calls_too_large")
    return await asyncio.to_thread(
        get_dex_local_event_reader_execution_contract,
        event_reader_run_id,
        dry_run,
        max_rpc_calls,
    )


@router.get("/rpc/dex-local-event-reader-run/execution-dry-run")
@router.post("/rpc/dex-local-event-reader-run/execution-dry-run")
async def rpc_dex_local_event_reader_execution_dry_run(
    event_reader_run_id: int | None = None,
    dry_run: bool = True,
    allow_rpc: bool = False,
    max_rpc_calls: int = 16,
    max_logs_total: int = 2_000,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_rpc_calls > 100:
        raise HTTPException(status_code=400, detail="max_rpc_calls_too_large")
    if max_logs_total > 20_000:
        raise HTTPException(status_code=400, detail="max_logs_total_too_large")
    return await asyncio.to_thread(
        run_dex_local_event_reader_execution_dry_run,
        event_reader_run_id,
        dry_run,
        allow_rpc,
        max_rpc_calls,
        max_logs_total,
    )


@router.get("/rpc/dex-local-event-reader-run/sqd-lookup-dry-run")
@router.post("/rpc/dex-local-event-reader-run/sqd-lookup-dry-run")
async def rpc_dex_local_event_reader_sqd_lookup_dry_run(
    event_reader_run_id: int | None = None,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    max_sqd_calls: int = 24,
    max_logs_total: int = 2_000,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if allow_external and confirm != "RUN_DEX_LOCAL_EVENT_READER_SQD_LOOKUP":
        raise HTTPException(status_code=400, detail="confirm_RUN_DEX_LOCAL_EVENT_READER_SQD_LOOKUP_required")
    if max_sqd_calls > 100:
        raise HTTPException(status_code=400, detail="max_sqd_calls_too_large")
    if max_logs_total > 20_000:
        raise HTTPException(status_code=400, detail="max_logs_total_too_large")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        run_dex_local_event_reader_sqd_lookup_dry_run,
        event_reader_run_id,
        dry_run,
        allow_external,
        confirm,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.get("/rpc/dex-local-event-reader-run/sqd-raw-event-persistence")
@router.post("/rpc/dex-local-event-reader-run/sqd-raw-event-persistence")
async def rpc_dex_local_event_reader_sqd_raw_event_persistence(
    event_reader_run_id: int | None = None,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    expected_persistence_dedupe_digest: str | None = None,
    max_sqd_calls: int = 24,
    max_logs_total: int = 2_000,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if max_sqd_calls > 100:
        raise HTTPException(status_code=400, detail="max_sqd_calls_too_large")
    if max_logs_total > 20_000:
        raise HTTPException(status_code=400, detail="max_logs_total_too_large")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if not dry_run and confirm != "PERSIST_DEX_LOCAL_EVENT_READER_SQD_RAW_EVENTS":
        raise HTTPException(status_code=400, detail="confirm_PERSIST_DEX_LOCAL_EVENT_READER_SQD_RAW_EVENTS_required")
    return await asyncio.to_thread(
        persist_dex_local_event_reader_sqd_raw_events,
        event_reader_run_id,
        dry_run,
        allow_external,
        confirm,
        expected_persistence_dedupe_digest,
        max_sqd_calls,
        max_logs_total,
        timeout,
    )


@router.get("/rpc/dex-local-event-reader-run/proof-package-preview")
@router.post("/rpc/dex-local-event-reader-run/proof-package-preview")
async def rpc_dex_local_event_reader_proof_package_preview(
    event_reader_run_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_local_event_reader_proof_package_preview,
        event_reader_run_id,
        dry_run,
    )


@router.get("/rpc/dex-local-event-reader-run/proof-package/insert")
@router.post("/rpc/dex-local-event-reader-run/proof-package/insert")
async def rpc_dex_local_event_reader_proof_package_insert(
    event_reader_run_id: int | None = None,
    expected_proof_package_digest: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "INSERT_DEX_LOCAL_EVENT_READER_PROOF_PACKAGE":
        raise HTTPException(status_code=400, detail="confirm_INSERT_DEX_LOCAL_EVENT_READER_PROOF_PACKAGE_required")
    return await asyncio.to_thread(
        insert_dex_local_event_reader_proof_package,
        event_reader_run_id,
        expected_proof_package_digest,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-event-proof-packages/review")
@router.post("/rpc/dex-event-proof-packages/review")
async def rpc_dex_event_proof_package_review_queue(
    status: str | None = "pending_admin_review",
    limit: int = 50,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_dex_local_event_reader_proof_package_review_queue,
        status,
        limit,
        dry_run,
    )


@router.get("/rpc/dex-event-proof-packages/decision-preview")
@router.post("/rpc/dex-event-proof-packages/decision-preview")
async def rpc_dex_event_proof_package_decision_preview(
    proof_package_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_local_event_reader_proof_package_decision_preview,
        proof_package_id,
        proposed_decision,
        dry_run,
    )


@router.post("/rpc/dex-event-proof-packages/decision/apply")
async def rpc_dex_event_proof_package_decision_apply(
    proof_package_id: int | None = None,
    proposed_decision: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if proof_package_id is None:
        raise HTTPException(status_code=400, detail="proof_package_id_required")
    if not dry_run and confirm != "APPLY_DEX_EVENT_PROOF_PACKAGE_DECISION":
        raise HTTPException(
            status_code=400,
            detail="confirm_APPLY_DEX_EVENT_PROOF_PACKAGE_DECISION_required",
        )
    return await asyncio.to_thread(
        apply_dex_local_event_reader_proof_package_decision,
        proof_package_id,
        proposed_decision,
        dry_run,
        confirm,
    )


@router.get("/rpc/dex-event-proof-packages/evidence-review-contract")
@router.post("/rpc/dex-event-proof-packages/evidence-review-contract")
async def rpc_dex_event_proof_package_evidence_review_contract(
    proof_package_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if proof_package_id is None:
        raise HTTPException(status_code=400, detail="proof_package_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_local_event_reader_proof_package_evidence_review_contract,
        proof_package_id,
        dry_run,
    )


@router.get("/rpc/dex-event-proof-packages/corroboration-review")
@router.post("/rpc/dex-event-proof-packages/corroboration-review")
async def rpc_dex_event_proof_package_corroboration_review(
    proof_package_id: int | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if proof_package_id is None:
        raise HTTPException(status_code=400, detail="proof_package_id_required")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_dex_local_event_reader_proof_package_corroboration_review,
        proof_package_id,
        dry_run,
    )


@router.get("/rpc/unknown-dex-paircreated-archive-indexer-alternative-strategy")
@router.post("/rpc/unknown-dex-paircreated-archive-indexer-alternative-strategy")
async def rpc_unknown_dex_paircreated_archive_indexer_alternative_strategy(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc_preflight: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_archive_indexer_alternative_strategy,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        timeout,
        dry_run,
        allow_rpc_preflight,
    )


@router.get("/rpc/unknown-dex-paircreated-local-creation-block-range-plan")
@router.post("/rpc/unknown-dex-paircreated-local-creation-block-range-plan")
async def rpc_unknown_dex_paircreated_local_creation_block_range_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    creation_lookback_blocks: int = 250_000,
    max_future_replay_range_blocks: int = 250_000,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc_preflight: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if creation_lookback_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="creation_lookback_blocks_max_2000000")
    if max_future_replay_range_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_future_replay_range_blocks_max_2000000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_local_creation_block_range_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        creation_lookback_blocks,
        max_future_replay_range_blocks,
        timeout,
        dry_run,
        allow_rpc_preflight,
    )


@router.get("/rpc/unknown-dex-paircreated-reduced-range-replay-dry-run")
@router.post("/rpc/unknown-dex-paircreated-reduced-range-replay-dry-run")
async def rpc_unknown_dex_paircreated_reduced_range_replay_dry_run(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    creation_lookback_blocks: int = 250_000,
    max_future_replay_range_blocks: int = 250_000,
    log_chunk_blocks: int = 50_000,
    max_log_chunks_per_candidate: int = 5,
    max_rpc_calls: int = 32,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    allow_rpc_preflight: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if creation_lookback_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="creation_lookback_blocks_max_2000000")
    if max_future_replay_range_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_future_replay_range_blocks_max_2000000")
    if log_chunk_blocks > 250_000:
        raise HTTPException(status_code=400, detail="log_chunk_blocks_max_250000")
    if max_log_chunks_per_candidate > 100:
        raise HTTPException(status_code=400, detail="max_log_chunks_per_candidate_max_100")
    if max_rpc_calls > 200:
        raise HTTPException(status_code=400, detail="max_rpc_calls_max_200")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_reduced_range_replay_dry_run,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        creation_lookback_blocks,
        max_future_replay_range_blocks,
        log_chunk_blocks,
        max_log_chunks_per_candidate,
        max_rpc_calls,
        timeout,
        dry_run,
        allow_rpc,
        allow_rpc_preflight,
    )


@router.get("/rpc/unknown-dex-pool-code-existence-creation-block-probe")
@router.post("/rpc/unknown-dex-pool-code-existence-creation-block-probe")
async def rpc_unknown_dex_pool_code_existence_creation_block_probe(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    creation_lookback_blocks: int = 250_000,
    max_future_replay_range_blocks: int = 250_000,
    max_binary_search_steps_per_candidate: int = 24,
    max_rpc_calls: int = 64,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    allow_rpc_preflight: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if creation_lookback_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="creation_lookback_blocks_max_2000000")
    if max_future_replay_range_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_future_replay_range_blocks_max_2000000")
    if max_binary_search_steps_per_candidate > 32:
        raise HTTPException(status_code=400, detail="max_binary_search_steps_per_candidate_max_32")
    if max_rpc_calls > 200:
        raise HTTPException(status_code=400, detail="max_rpc_calls_max_200")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_pool_code_existence_creation_block_probe,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        creation_lookback_blocks,
        max_future_replay_range_blocks,
        max_binary_search_steps_per_candidate,
        max_rpc_calls,
        timeout,
        dry_run,
        allow_rpc,
        allow_rpc_preflight,
    )


@router.get("/rpc/unknown-dex-pool-contract-creation-proof-source-gate")
@router.post("/rpc/unknown-dex-pool-contract-creation-proof-source-gate")
async def rpc_unknown_dex_pool_contract_creation_proof_source_gate(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    creation_lookback_blocks: int = 250_000,
    max_future_replay_range_blocks: int = 250_000,
    timeout: int = 6,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if creation_lookback_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="creation_lookback_blocks_max_2000000")
    if max_future_replay_range_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_future_replay_range_blocks_max_2000000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_pool_contract_creation_proof_source_gate,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        creation_lookback_blocks,
        max_future_replay_range_blocks,
        timeout,
        dry_run,
    )


@router.get("/rpc/unknown-dex-pool-contract-creation-explorer-archive-lookup-dry-run")
@router.post("/rpc/unknown-dex-pool-contract-creation-explorer-archive-lookup-dry-run")
async def rpc_unknown_dex_pool_contract_creation_explorer_archive_lookup_dry_run(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    creation_lookback_blocks: int = 250_000,
    max_future_replay_range_blocks: int = 250_000,
    max_source_calls: int = 2,
    timeout: int = 6,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if creation_lookback_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="creation_lookback_blocks_max_2000000")
    if max_future_replay_range_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_future_replay_range_blocks_max_2000000")
    if max_source_calls > 4:
        raise HTTPException(status_code=400, detail="max_source_calls_max_4")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_pool_contract_creation_explorer_archive_lookup_dry_run,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        creation_lookback_blocks,
        max_future_replay_range_blocks,
        max_source_calls,
        timeout,
        dry_run,
        allow_external,
        confirm,
    )


@router.get("/rpc/unknown-dex-paircreated-forward-local-indexer-plan")
@router.post("/rpc/unknown-dex-paircreated-forward-local-indexer-plan")
async def rpc_unknown_dex_paircreated_forward_local_indexer_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    lookback_blocks: int = 500_000,
    creation_lookback_blocks: int = 250_000,
    max_future_replay_range_blocks: int = 250_000,
    forward_block_window: int = 5_000,
    poll_interval_seconds: int = 60,
    timeout: int = 6,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if lookback_blocks > 5_000_000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_5000000")
    if creation_lookback_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="creation_lookback_blocks_max_2000000")
    if max_future_replay_range_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_future_replay_range_blocks_max_2000000")
    if forward_block_window > 100_000:
        raise HTTPException(status_code=400, detail="forward_block_window_max_100000")
    if poll_interval_seconds > 3_600:
        raise HTTPException(status_code=400, detail="poll_interval_seconds_max_3600")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_paircreated_forward_local_indexer_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        lookback_blocks,
        creation_lookback_blocks,
        max_future_replay_range_blocks,
        forward_block_window,
        poll_interval_seconds,
        timeout,
        dry_run,
    )


@router.get("/rpc/unknown-dex-venue-family-review")
@router.post("/rpc/unknown-dex-venue-family-review")
async def rpc_unknown_dex_venue_family_review(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_venue_family_review,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        timeout,
        dry_run,
        allow_rpc,
    )


@router.get("/rpc/unknown-dex-family-context-scoring-plan")
@router.post("/rpc/unknown-dex-family-context-scoring-plan")
async def rpc_unknown_dex_family_context_scoring_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_scoring_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        timeout,
        dry_run,
        allow_rpc,
    )


@router.get("/rpc/unknown-dex-family-context-collection-plan")
@router.post("/rpc/unknown-dex-family-context-collection-plan")
async def rpc_unknown_dex_family_context_collection_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_collection_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        allow_rpc,
    )


@router.post("/rpc/unknown-dex-family-context-history-collection")
async def rpc_unknown_dex_family_context_history_collection(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    confirm: str | None = None,
    allow_rpc: bool = False,
    max_receipts_per_block: int | None = None,
    max_seconds_per_block: float | None = None,
    _: None = Depends(_require_data_admin),
):
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if max_receipts_per_block is not None and max_receipts_per_block > 200:
        raise HTTPException(status_code=400, detail="max_receipts_per_block_max_200")
    if max_seconds_per_block is not None and max_seconds_per_block > 120:
        raise HTTPException(status_code=400, detail="max_seconds_per_block_max_120")
    return await asyncio.to_thread(
        run_unknown_dex_family_context_history_collection,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        confirm,
        allow_rpc,
        max_receipts_per_block,
        max_seconds_per_block,
    )


@router.get("/rpc/unknown-dex-family-context-post-collection-audit")
@router.post("/rpc/unknown-dex-family-context-post-collection-audit")
async def rpc_unknown_dex_family_context_post_collection_audit(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    allow_rpc: bool = False,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_post_collection_audit,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        allow_rpc,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-candidate-repair-plan")
@router.post("/rpc/unknown-dex-family-context-candidate-repair-plan")
async def rpc_unknown_dex_family_context_candidate_repair_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_candidate_repair_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-casefile")
@router.post("/rpc/unknown-dex-family-context-casefile")
async def rpc_unknown_dex_family_context_casefile(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_casefile,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-route-source-repeatability-plan")
@router.post("/rpc/unknown-dex-family-context-route-source-repeatability-plan")
async def rpc_unknown_dex_family_context_route_source_repeatability_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_route_source_repeatability_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-exact-route-source-proof-acquisition-plan")
@router.post("/rpc/unknown-dex-family-context-exact-route-source-proof-acquisition-plan")
async def rpc_unknown_dex_family_context_exact_route_source_proof_acquisition_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_exact_route_source_proof_acquisition_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-bounded-official-source-lookup-plan")
@router.post("/rpc/unknown-dex-family-context-bounded-official-source-lookup-plan")
async def rpc_unknown_dex_family_context_bounded_official_source_lookup_plan(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_bounded_official_source_lookup_plan,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-source-acquisition-strategy-decision-preview")
@router.post("/rpc/unknown-dex-family-context-source-acquisition-strategy-decision-preview")
async def rpc_unknown_dex_family_context_source_acquisition_strategy_decision_preview(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    proposed_strategy: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_source_acquisition_strategy_decision_preview,
        chain,
        factory_address,
        proposed_strategy,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-manual-source-intake-preview")
@router.post("/rpc/unknown-dex-family-context-manual-source-intake-preview")
async def rpc_unknown_dex_family_context_manual_source_intake_preview(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    manual_sources: list[dict[str, Any]] | None = Body(default=None),
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_manual_source_intake_preview,
        chain,
        factory_address,
        manual_sources,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-bounded-official-source-lookup-gate")
@router.post("/rpc/unknown-dex-family-context-bounded-official-source-lookup-gate")
async def rpc_unknown_dex_family_context_bounded_official_source_lookup_gate(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_bounded_official_source_lookup_gate,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
    )


@router.get("/rpc/unknown-dex-family-context-bounded-official-source-lookup")
@router.post("/rpc/unknown-dex-family-context-bounded-official-source-lookup")
async def rpc_unknown_dex_family_context_bounded_official_source_lookup(
    chain: str | None = "bsc",
    factory_address: str | None = None,
    block_window: int = 10_000,
    limit: int = 5,
    tx_transfer_limit: int = 80,
    max_pools: int = 4,
    window_radius_blocks: int = 3,
    max_blocks: int = 30,
    timeout: int = 6,
    dry_run: bool = True,
    candidate_limit: int = 8,
    max_targets: int = 3,
    max_results_per_query: int = 3,
    allow_external: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if tx_transfer_limit > 200:
        raise HTTPException(status_code=400, detail="tx_transfer_limit_max_200")
    if max_pools > 12:
        raise HTTPException(status_code=400, detail="max_pools_max_12")
    if window_radius_blocks > 25:
        raise HTTPException(status_code=400, detail="window_radius_blocks_max_25")
    if max_blocks > 100:
        raise HTTPException(status_code=400, detail="max_blocks_max_100")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if candidate_limit > 25:
        raise HTTPException(status_code=400, detail="candidate_limit_max_25")
    if max_targets > 8:
        raise HTTPException(status_code=400, detail="max_targets_max_8")
    if max_results_per_query > 5:
        raise HTTPException(status_code=400, detail="max_results_per_query_max_5")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_bounded_official_source_lookup,
        chain,
        factory_address,
        block_window,
        limit,
        tx_transfer_limit,
        max_pools,
        window_radius_blocks,
        max_blocks,
        timeout,
        dry_run,
        candidate_limit,
        max_targets,
        max_results_per_query,
        allow_external,
        confirm,
    )


@router.get("/rpc/unknown-dex-family-context-source-page-fetch-grading-checkpoint")
@router.post("/rpc/unknown-dex-family-context-source-page-fetch-grading-checkpoint")
async def rpc_unknown_dex_family_context_source_page_fetch_grading_checkpoint(
    source_url: str | None = None,
    expected_address: str | None = None,
    expected_chain: str | None = "bsc",
    expected_token_symbol: str | None = None,
    expected_route_role: str | None = None,
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    timeout: int = 6,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_source_page_fetch_grading_checkpoint,
        source_url,
        expected_address,
        expected_chain,
        expected_token_symbol,
        expected_route_role,
        dry_run,
        allow_external,
        confirm,
        timeout,
    )


@router.get("/rpc/unknown-dex-family-context-stronger-official-route-source-package-plan")
@router.post("/rpc/unknown-dex-family-context-stronger-official-route-source-package-plan")
async def rpc_unknown_dex_family_context_stronger_official_route_source_package_plan(
    source_url: str | None = None,
    expected_address: str | None = None,
    expected_chain: str | None = "bsc",
    expected_token_symbol: str | None = None,
    current_grade_status: str | None = None,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_stronger_official_route_source_package_plan,
        source_url,
        expected_address,
        expected_chain,
        expected_token_symbol,
        current_grade_status,
        dry_run,
    )


@router.get("/rpc/unknown-dex-family-context-bounded-official-route-source-package-preview")
@router.post("/rpc/unknown-dex-family-context-bounded-official-route-source-package-preview")
async def rpc_unknown_dex_family_context_bounded_official_route_source_package_preview(
    source_url: str | None = None,
    expected_address: str | None = None,
    expected_chain: str | None = "bsc",
    expected_token_symbol: str | None = None,
    current_grade_status: str | None = None,
    manual_sources: list[dict[str, Any]] | None = Body(default=None),
    dry_run: bool = True,
    allow_external: bool = False,
    confirm: str | None = None,
    timeout: int = 6,
    max_results_per_query: int = 3,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if max_results_per_query > 5:
        raise HTTPException(status_code=400, detail="max_results_per_query_max_5")
    return await asyncio.to_thread(
        get_unknown_dex_family_context_bounded_official_route_source_package_preview,
        source_url,
        expected_address,
        expected_chain,
        expected_token_symbol,
        current_grade_status,
        manual_sources,
        dry_run,
        allow_external,
        confirm,
        timeout,
        max_results_per_query,
    )


@router.get("/rpc/core-equity-agent-control-plane")
@router.post("/rpc/core-equity-agent-control-plane")
async def rpc_core_equity_agent_control_plane(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    return await asyncio.to_thread(
        get_core_equity_agent_control_plane,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
    )


@router.get("/rpc/core-equity-agent-task-contract-preview")
@router.post("/rpc/core-equity-agent-task-contract-preview")
async def rpc_core_equity_agent_task_contract_preview(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    max_tasks: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if max_tasks > 20:
        raise HTTPException(status_code=400, detail="max_tasks_max_20")
    return await asyncio.to_thread(
        get_core_equity_agent_task_contract_preview,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
        max_tasks,
    )


@router.get("/rpc/core-equity-codex-agent-runner-dry-run")
@router.post("/rpc/core-equity-codex-agent-runner-dry-run")
async def rpc_core_equity_codex_agent_runner_dry_run(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    max_tasks: int = 8,
    task_id: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if max_tasks > 20:
        raise HTTPException(status_code=400, detail="max_tasks_max_20")
    return await asyncio.to_thread(
        run_core_equity_codex_agent_runner_dry_run,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
        max_tasks,
        task_id,
    )


@router.get("/rpc/core-equity-codex-runner-audit-log-preview")
@router.post("/rpc/core-equity-codex-runner-audit-log-preview")
async def rpc_core_equity_codex_runner_audit_log_preview(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    max_tasks: int = 8,
    task_id: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if max_tasks > 20:
        raise HTTPException(status_code=400, detail="max_tasks_max_20")
    return await asyncio.to_thread(
        get_core_equity_codex_runner_audit_log_preview,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
        max_tasks,
        task_id,
    )


@router.post("/rpc/core-equity-codex-runner-audit-log/write")
async def rpc_core_equity_codex_runner_audit_log_write(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    max_tasks: int = 8,
    task_id: str | None = None,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if max_tasks > 20:
        raise HTTPException(status_code=400, detail="max_tasks_max_20")
    return await asyncio.to_thread(
        write_core_equity_codex_runner_audit_log,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
        max_tasks,
        task_id,
        confirm,
    )


@router.get("/rpc/core-equity-codex-schedule-plan")
@router.post("/rpc/core-equity-codex-schedule-plan")
async def rpc_core_equity_codex_schedule_plan(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    max_tasks: int = 8,
    task_id: str | None = None,
    cadence_minutes: int = 60,
    max_cycles_per_day: int = 6,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if max_tasks > 20:
        raise HTTPException(status_code=400, detail="max_tasks_max_20")
    if cadence_minutes < 15 or cadence_minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="cadence_minutes_range_15_1440")
    if max_cycles_per_day > 24:
        raise HTTPException(status_code=400, detail="max_cycles_per_day_max_24")
    return await asyncio.to_thread(
        get_core_equity_codex_schedule_plan,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
        max_tasks,
        task_id,
        cadence_minutes,
        max_cycles_per_day,
    )


@router.get("/rpc/core-equity-agent-os-lite/state-snapshot")
@router.post("/rpc/core-equity-agent-os-lite/state-snapshot")
async def rpc_core_equity_agent_os_lite_state_snapshot(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    return await asyncio.to_thread(
        get_core_equity_agent_os_lite_state_snapshot,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
    )


@router.get("/rpc/core-equity-agent-os-lite/runtime-preflight")
@router.post("/rpc/core-equity-agent-os-lite/runtime-preflight")
async def rpc_core_equity_agent_os_lite_runtime_preflight(
    dry_run: bool = True,
    event_reader_run_id: int | None = 1,
    require_qdrant: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(
        get_core_equity_agent_os_lite_runtime_preflight,
        dry_run,
        event_reader_run_id,
        require_qdrant,
    )


@router.get("/rpc/core-equity-agent-os-lite/cycle-preview")
@router.post("/rpc/core-equity-agent-os-lite/cycle-preview")
async def rpc_core_equity_agent_os_lite_cycle_preview(
    dry_run: bool = True,
    event_reader_run_id: int | None = 1,
    max_rpc_calls: int = 25,
    require_qdrant: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_rpc_calls > 100:
        raise HTTPException(status_code=400, detail="max_rpc_calls_max_100")
    return await asyncio.to_thread(
        get_core_equity_agent_os_lite_cycle_preview,
        dry_run,
        event_reader_run_id,
        max_rpc_calls,
        require_qdrant,
    )


@router.get("/rpc/core-equity-agent-os-lite/task-queue")
@router.post("/rpc/core-equity-agent-os-lite/task-queue")
async def rpc_core_equity_agent_os_lite_task_queue(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    max_tasks: int = 8,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if max_tasks > 20:
        raise HTTPException(status_code=400, detail="max_tasks_max_20")
    return await asyncio.to_thread(
        get_core_equity_agent_os_lite_task_queue_view,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
        max_tasks,
    )


@router.get("/rpc/core-equity-agent-os-lite/schedule-activation-checklist")
@router.post("/rpc/core-equity-agent-os-lite/schedule-activation-checklist")
async def rpc_core_equity_agent_os_lite_schedule_activation_checklist(
    chain: str | None = "bsc",
    focus: str | None = "unknown_dex_data_quality",
    limit: int = 5,
    dry_run: bool = True,
    allow_live_checks: bool = False,
    max_tasks: int = 8,
    cadence_minutes: int = 60,
    max_cycles_per_day: int = 6,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 12:
        raise HTTPException(status_code=400, detail="limit_max_12")
    if max_tasks > 20:
        raise HTTPException(status_code=400, detail="max_tasks_max_20")
    if cadence_minutes < 15 or cadence_minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="cadence_minutes_range_15_1440")
    if max_cycles_per_day > 24:
        raise HTTPException(status_code=400, detail="max_cycles_per_day_max_24")
    return await asyncio.to_thread(
        get_core_equity_agent_os_lite_schedule_activation_checklist,
        chain,
        focus,
        limit,
        dry_run,
        allow_live_checks,
        max_tasks,
        cadence_minutes,
        max_cycles_per_day,
    )


@router.get("/rpc/unknown-dex-traceability-candidate-internal-probe")
@router.post("/rpc/unknown-dex-traceability-candidate-internal-probe")
async def rpc_unknown_dex_traceability_candidate_internal_probe(
    chain: str | None = "bsc",
    block_window: int = 10_000,
    limit: int = 8,
    max_external_calls: int = 3,
    timeout: int = 6,
    dry_run: bool = True,
    external_fetch: bool = False,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if block_window > 50_000:
        raise HTTPException(status_code=400, detail="block_window_max_50000")
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_external_calls > 10:
        raise HTTPException(status_code=400, detail="max_external_calls_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        run_unknown_dex_traceability_candidate_internal_probe,
        chain,
        block_window,
        limit,
        max_external_calls,
        timeout,
        dry_run,
        external_fetch,
        confirm,
    )


@router.get("/rpc/dex-official-router-registry")
async def rpc_dex_official_router_registry(
    chain: str | None = None,
    limit: int = 100,
    dry_run: bool = True,
    compare_unknowns: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit_max_500")
    return await asyncio.to_thread(
        get_dex_official_router_registry,
        chain,
        limit,
        dry_run,
        compare_unknowns,
    )


@router.get("/rpc/dex-official-router-registry/source-freshness")
async def rpc_dex_official_router_registry_source_freshness(
    chain: str | None = None,
    limit: int = 100,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit_max_500")
    return await asyncio.to_thread(
        get_dex_official_router_registry_source_freshness,
        chain,
        limit,
        dry_run,
    )


@router.get("/rpc/aster-dex-fund-flow-radar")
async def rpc_aster_dex_fund_flow_radar(
    chain: str | None = None,
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_aster_dex_fund_flow_radar,
        chain,
        limit,
        dry_run,
    )


@router.post("/rpc/aster-dex-fund-flow-collection")
async def rpc_aster_dex_fund_flow_collection(
    chain: str | None = None,
    lookback_blocks: int = 2000,
    confirmations: int = 12,
    max_addresses: int = 5,
    max_logs_per_address: int = 100,
    max_tokens_per_chain: int = 25,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if lookback_blocks > 50000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_50000")
    if confirmations > 200:
        raise HTTPException(status_code=400, detail="confirmations_max_200")
    if max_addresses > 10:
        raise HTTPException(status_code=400, detail="max_addresses_max_10")
    if max_logs_per_address > 500:
        raise HTTPException(status_code=400, detail="max_logs_per_address_max_500")
    if max_tokens_per_chain > 100:
        raise HTTPException(status_code=400, detail="max_tokens_per_chain_max_100")
    return await asyncio.to_thread(
        run_aster_dex_fund_flow_collection,
        chain,
        lookback_blocks,
        confirmations,
        max_addresses,
        max_logs_per_address,
        max_tokens_per_chain,
        dry_run,
        confirm,
    )


@router.post("/rpc/aster-dex-paginated-fund-flow-collection")
async def rpc_aster_dex_paginated_fund_flow_collection(
    chain: str = "bsc",
    pages: int = 5,
    page_size_blocks: int = 100,
    confirmations: int = 12,
    max_addresses: int = 1,
    max_logs_per_address: int = 50,
    max_tokens_per_chain: int = 25,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if pages > 20:
        raise HTTPException(status_code=400, detail="pages_max_20")
    if page_size_blocks > 500:
        raise HTTPException(status_code=400, detail="page_size_blocks_max_500")
    if confirmations > 200:
        raise HTTPException(status_code=400, detail="confirmations_max_200")
    if max_addresses > 5:
        raise HTTPException(status_code=400, detail="max_addresses_max_5")
    if max_logs_per_address > 200:
        raise HTTPException(status_code=400, detail="max_logs_per_address_max_200")
    if max_tokens_per_chain > 100:
        raise HTTPException(status_code=400, detail="max_tokens_per_chain_max_100")
    return await asyncio.to_thread(
        run_aster_dex_paginated_fund_flow_collection,
        chain,
        pages,
        page_size_blocks,
        confirmations,
        max_addresses,
        max_logs_per_address,
        max_tokens_per_chain,
        dry_run,
        confirm,
    )


@router.get("/rpc/aster-dex-flow-case-file")
async def rpc_aster_dex_flow_case_file(
    chain: str | None = "bsc",
    tx_hash: str | None = None,
    limit: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        get_aster_dex_flow_case_file,
        chain,
        tx_hash,
        limit,
        dry_run,
    )


@router.get("/rpc/aster-cex-bridge-context")
async def rpc_aster_cex_bridge_context(
    chain: str | None = "bsc",
    source_wallet: str | None = None,
    tx_hash: str | None = None,
    limit: int = 20,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(
        get_aster_cex_bridge_context,
        chain,
        source_wallet,
        tx_hash,
        limit,
        dry_run,
    )


@router.get("/rpc/aster-agent-foundation-test")
@router.post("/rpc/aster-agent-foundation-test")
async def rpc_aster_agent_foundation_test(
    symbol: str | None = "BTCUSDT",
    pool_address: str | None = None,
    chain: str | None = "bsc",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_swaps: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if max_swaps > 10:
        raise HTTPException(status_code=400, detail="max_swaps_max_10")
    return await asyncio.to_thread(
        get_aster_agent_foundation_test,
        symbol,
        pool_address,
        chain,
        dry_run,
        timeout_seconds,
        max_swaps,
    )


@router.get("/rpc/aster-order-book-anomaly-detection-test")
@router.post("/rpc/aster-order-book-anomaly-detection-test")
async def rpc_aster_order_book_anomaly_detection_test(
    symbols: str | None = "BTCUSDT",
    token_addresses: str | None = None,
    chain: str | None = "bsc",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 5,
    max_snapshots_per_symbol: int = 1,
    snapshot_interval_ms: int = 0,
    depth_limit: int = 100,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if max_symbols > 5:
        raise HTTPException(status_code=400, detail="max_symbols_max_5")
    if max_snapshots_per_symbol > 10:
        raise HTTPException(status_code=400, detail="max_snapshots_per_symbol_max_10")
    if snapshot_interval_ms > 30_000:
        raise HTTPException(status_code=400, detail="snapshot_interval_ms_max_30000")
    if depth_limit > 100:
        raise HTTPException(status_code=400, detail="depth_limit_max_100")
    return await asyncio.to_thread(
        get_aster_order_book_anomaly_detection_test,
        symbols,
        token_addresses,
        chain,
        dry_run,
        timeout_seconds,
        max_symbols,
        max_snapshots_per_symbol,
        snapshot_interval_ms,
        depth_limit,
    )


@router.get("/rpc/aster-agent-loop-test")
@router.post("/rpc/aster-agent-loop-test")
async def rpc_aster_agent_loop_test(
    wallet_address: str | None = None,
    symbols: str | None = "BTCUSDT",
    token_addresses: str | None = None,
    dry_run: bool = True,
    max_cycles: int = 1,
    timeout_seconds: int = 8,
    wallet_balance_usd: float | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_cycles > 3:
        raise HTTPException(status_code=400, detail="max_cycles_max_3")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    return await asyncio.to_thread(
        run_aster_agent_loop_test,
        wallet_address,
        symbols,
        token_addresses,
        dry_run,
        max_cycles,
        timeout_seconds,
        wallet_balance_usd,
    )


@router.get("/rpc/aster-api-resilience-test")
@router.post("/rpc/aster-api-resilience-test")
async def rpc_aster_api_resilience_test(
    symbol: str | None = "BTCUSDT",
    dry_run: bool = True,
    request_count: int = 5,
    max_events: int = 100,
    timeout_seconds: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if request_count > 10:
        raise HTTPException(status_code=400, detail="request_count_max_10")
    if max_events > 1000:
        raise HTTPException(status_code=400, detail="max_events_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    return await asyncio.to_thread(
        get_aster_api_resilience_test,
        symbol,
        dry_run,
        request_count,
        max_events,
        timeout_seconds,
    )


@router.get("/rpc/aster-mcp-market-data-adapter-preview")
@router.post("/rpc/aster-mcp-market-data-adapter-preview")
async def rpc_aster_mcp_market_data_adapter_preview(
    symbols: str | None = "BTCUSDT,INJUSDT,LABUSDT",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 5,
    kline_interval: str = "1h",
    kline_limit: int = 50,
    funding_limit: int = 20,
    depth_limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if max_symbols > 10:
        raise HTTPException(status_code=400, detail="max_symbols_max_10")
    if kline_limit > 1000:
        raise HTTPException(status_code=400, detail="kline_limit_max_1000")
    if funding_limit > 1000:
        raise HTTPException(status_code=400, detail="funding_limit_max_1000")
    if depth_limit > 100:
        raise HTTPException(status_code=400, detail="depth_limit_max_100")
    return await asyncio.to_thread(
        get_aster_mcp_market_data_adapter_preview,
        symbols,
        dry_run,
        timeout_seconds,
        max_symbols,
        kline_interval,
        kline_limit,
        funding_limit,
        depth_limit,
    )


@router.get("/rpc/aster-perps-reality-check-preview")
@router.post("/rpc/aster-perps-reality-check-preview")
async def rpc_aster_perps_reality_check_preview(
    symbols: str | None = "LABUSDT,INJUSDT,BOMEUSDT,TIAUSDT,INTCUSDT,CRCLUSDT,MSFTUSDT",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 8,
    kline_interval: str = "1h",
    kline_limit: int = 50,
    funding_limit: int = 20,
    depth_limit: int = 50,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if max_symbols > 10:
        raise HTTPException(status_code=400, detail="max_symbols_max_10")
    if kline_limit > 1000:
        raise HTTPException(status_code=400, detail="kline_limit_max_1000")
    if funding_limit > 1000:
        raise HTTPException(status_code=400, detail="funding_limit_max_1000")
    if depth_limit > 100:
        raise HTTPException(status_code=400, detail="depth_limit_max_100")
    return await asyncio.to_thread(
        get_aster_perps_reality_check_preview,
        symbols,
        dry_run,
        timeout_seconds,
        max_symbols,
        kline_interval,
        kline_limit,
        funding_limit,
        depth_limit,
    )


@router.get("/rpc/aster-data-source-validation-preview")
@router.post("/rpc/aster-data-source-validation-preview")
async def rpc_aster_data_source_validation_preview(
    symbols: str | None = "LABUSDT,INJUSDT,BTCUSDT",
    dry_run: bool = True,
    write_snapshot: bool = False,
    timeout_seconds: int = 8,
    max_symbols: int = 3,
    interval: str = "1h",
    sample_limit: int = 20,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if max_symbols > 5:
        raise HTTPException(status_code=400, detail="max_symbols_max_5")
    if sample_limit > 1000:
        raise HTTPException(status_code=400, detail="sample_limit_max_1000")
    if write_snapshot:
        return await asyncio.to_thread(
            write_aster_data_source_validation_snapshot,
            symbols,
            timeout_seconds,
            max_symbols,
            interval,
            sample_limit,
        )
    return await asyncio.to_thread(get_aster_data_source_validation_preview, symbols, dry_run, timeout_seconds, max_symbols, interval, sample_limit)


@router.get("/rpc/aster-mcp-capability-audit-preview")
@router.post("/rpc/aster-mcp-capability-audit-preview")
async def rpc_aster_mcp_capability_audit_preview(
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(get_aster_mcp_capability_audit_preview, dry_run)


@router.get("/rpc/aster-public-universe-snapshot-preview")
@router.post("/rpc/aster-public-universe-snapshot-preview")
async def rpc_aster_public_universe_snapshot_preview(
    dry_run: bool = True,
    timeout_seconds: int = 8,
    top_n: int = 30,
    write_snapshot: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if top_n > 100:
        raise HTTPException(status_code=400, detail="top_n_max_100")
    return await asyncio.to_thread(
        get_aster_public_universe_snapshot_preview,
        dry_run,
        timeout_seconds,
        top_n,
        None,
        write_snapshot,
    )


@router.get("/rpc/aster-ws-market-stream-validation-preview")
@router.post("/rpc/aster-ws-market-stream-validation-preview")
async def rpc_aster_ws_market_stream_validation_preview(
    streams: str | None = "btcusdt@aggTrade,btcusdt@kline_1m,btcusdt@depth5@500ms,!markPrice@arr@1s",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_streams: int = 4,
    max_payload_bytes: int = 1_000_000,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if max_streams > 8:
        raise HTTPException(status_code=400, detail="max_streams_max_8")
    if max_payload_bytes > 2_000_000:
        raise HTTPException(status_code=400, detail="max_payload_bytes_max_2000000")
    return await asyncio.to_thread(
        get_aster_ws_market_stream_validation_preview,
        streams,
        dry_run,
        timeout_seconds,
        max_streams,
        max_payload_bytes,
    )


@router.get("/rpc/aster-ws-forward-monitor-preview")
@router.post("/rpc/aster-ws-forward-monitor-preview")
async def rpc_aster_ws_forward_monitor_preview(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    dry_run: bool = True,
    timeout_seconds: int = 8,
    use_combined_stream: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_ws_forward_monitor_preview,
        symbol,
        interval,
        dry_run,
        timeout_seconds,
        use_combined_stream,
    )


@router.get("/rpc/aster-ws-symbol-quality-report-preview")
@router.post("/rpc/aster-ws-symbol-quality-report-preview")
async def rpc_aster_ws_symbol_quality_report_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 5,
    interval: str = "1m",
    rate_limit_delay_ms: int = 300,
    write_snapshot: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if max_symbols > 10:
        raise HTTPException(status_code=400, detail="max_symbols_max_10")
    if rate_limit_delay_ms > 2000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_max_2000")
    return await asyncio.to_thread(
        get_aster_ws_symbol_quality_report_preview,
        symbols,
        dry_run,
        timeout_seconds,
        max_symbols,
        interval,
        rate_limit_delay_ms,
        write_snapshot,
    )


@router.get("/rpc/aster-v2-ws-preflight-refresh-preview")
@router.post("/rpc/aster-v2-ws-preflight-refresh-preview")
async def rpc_aster_v2_ws_preflight_refresh_preview(
    symbols: str | None = None,
    selection_mode: str = "needs_ws_validation",
    max_symbols: int = 10,
    batch_size: int = 5,
    timeout_seconds: int = 8,
    interval: str = "1m",
    rate_limit_delay_ms: int = 300,
    write_snapshot: bool = False,
    regenerate_v2_plan: bool = True,
    _: None = Depends(_require_data_admin),
):
    if max_symbols > 30:
        raise HTTPException(status_code=400, detail="max_symbols_max_30")
    if batch_size > 10:
        raise HTTPException(status_code=400, detail="batch_size_max_10")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms > 2000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_max_2000")
    return await asyncio.to_thread(
        get_aster_v2_ws_preflight_refresh_preview,
        symbols,
        selection_mode,
        max_symbols,
        batch_size,
        timeout_seconds,
        interval,
        rate_limit_delay_ms,
        write_snapshot,
        regenerate_v2_plan,
    )


@router.get("/rpc/aster-v2-strict-vs-large-comparison-preview")
@router.post("/rpc/aster-v2-strict-vs-large-comparison-preview")
async def rpc_aster_v2_strict_vs_large_comparison_preview(
    strict_output_tag: str = "aster_v2_strict",
    large_output_tag: str = "aster_v2",
    max_rows_per_file: int = 50000,
    top_n: int = 25,
    min_closed_trades: int = 6,
    write_snapshot: bool = True,
    _: None = Depends(_require_data_admin),
):
    if max_rows_per_file > 100000:
        raise HTTPException(status_code=400, detail="max_rows_per_file_max_100000")
    if top_n > 100:
        raise HTTPException(status_code=400, detail="top_n_max_100")
    return await asyncio.to_thread(
        get_aster_v2_strict_vs_large_comparison_preview,
        strict_output_tag,
        large_output_tag,
        max_rows_per_file,
        top_n,
        min_closed_trades,
        write_snapshot,
    )


@router.get("/rpc/aster-runner-health-dashboard-preview")
@router.post("/rpc/aster-runner-health-dashboard-preview")
async def rpc_aster_runner_health_dashboard_preview(
    expected_tags: str | None = None,
    max_rows_per_csv: int = 5000,
    top_n: int = 5,
    write_snapshot: bool = True,
    _: None = Depends(_require_data_admin),
):
    if max_rows_per_csv > 25000:
        raise HTTPException(status_code=400, detail="max_rows_per_csv_max_25000")
    if top_n > 25:
        raise HTTPException(status_code=400, detail="top_n_max_25")
    return await asyncio.to_thread(
        get_aster_runner_health_dashboard_preview,
        expected_tags,
        max_rows_per_csv,
        top_n,
        write_snapshot,
    )


@router.get("/rpc/aster-priority-watchlist-preview")
@router.post("/rpc/aster-priority-watchlist-preview")
async def rpc_aster_priority_watchlist_preview(
    dry_run: bool = True,
    max_candidates: int = 80,
    top_n: int = 25,
    exclude_symbols: str | None = "LABUSDT,INJUSDT,CRCLUSDT,MSFTUSDT,INTCUSDT",
    write_snapshot: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_candidates > 300:
        raise HTTPException(status_code=400, detail="max_candidates_max_300")
    if top_n > 100:
        raise HTTPException(status_code=400, detail="top_n_max_100")
    return await asyncio.to_thread(
        get_aster_priority_watchlist_preview,
        dry_run,
        max_candidates,
        top_n,
        exclude_symbols,
        write_snapshot,
    )


@router.get("/rpc/aster-dual-track-research-report-preview")
@router.post("/rpc/aster-dual-track-research-report-preview")
async def rpc_aster_dual_track_research_report_preview(
    dry_run: bool = True,
    exploitation_top_n: int = 12,
    exploration_top_n: int = 12,
    preserve_symbols: str | None = "LABUSDT,INTCUSDT,CRCLUSDT,MSFTUSDT,INJUSDT,ORDIUSDT,TIAUSDT,BOMEUSDT",
    write_snapshot: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if exploitation_top_n > 50:
        raise HTTPException(status_code=400, detail="exploitation_top_n_max_50")
    if exploration_top_n > 50:
        raise HTTPException(status_code=400, detail="exploration_top_n_max_50")
    return await asyncio.to_thread(
        get_aster_dual_track_research_report_preview,
        dry_run,
        exploitation_top_n,
        exploration_top_n,
        preserve_symbols,
        write_snapshot,
    )


@router.get("/rpc/aster-exploitation-champions-validation-preview")
@router.post("/rpc/aster-exploitation-champions-validation-preview")
async def rpc_aster_exploitation_champions_validation_preview(
    dry_run: bool = True,
    max_champions: int = 8,
    symbols: str | None = None,
    lookback_days: int = 30,
    timeout_seconds: int = 8,
    rate_limit_delay_ms: int = 250,
    write_snapshot: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_champions > 10:
        raise HTTPException(status_code=400, detail="max_champions_max_10")
    if lookback_days > 60:
        raise HTTPException(status_code=400, detail="lookback_days_max_60")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms > 2000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_max_2000")
    return await asyncio.to_thread(
        get_aster_exploitation_champions_validation_preview,
        dry_run,
        max_champions,
        symbols,
        lookback_days,
        timeout_seconds,
        rate_limit_delay_ms,
        write_snapshot,
    )


@router.get("/rpc/aster-mark-index-replay-filter-preview")
@router.post("/rpc/aster-mark-index-replay-filter-preview")
async def rpc_aster_mark_index_replay_filter_preview(
    symbols: str | None = "LABUSDT,INJUSDT,BOMEUSDT,TIAUSDT,CRCLUSDT,INTCUSDT",
    intervals: str | None = "5h,3h,1h,30m",
    dry_run: bool = True,
    lookback_days: int = 30,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 250,
    min_aligned_klines: int = 30,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if lookback_days > 60:
        raise HTTPException(status_code=400, detail="lookback_days_max_60")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms > 2_000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_max_2000")
    return await asyncio.to_thread(
        get_aster_mark_index_replay_filter_preview,
        symbols,
        intervals,
        dry_run,
        lookback_days,
        timeout_seconds,
        rate_limit_delay_ms,
        min_aligned_klines,
    )


@router.get("/rpc/aster-paper-trading-schema-plan")
@router.post("/rpc/aster-paper-trading-schema-plan")
async def rpc_aster_paper_trading_schema_plan(
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    return await asyncio.to_thread(get_aster_paper_trading_schema_plan, dry_run)


@router.post("/rpc/aster-paper-trading-ledger/create")
async def rpc_create_aster_paper_trading_ledger(
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "CREATE_ASTER_PAPER_TRADING_LEDGER":
        raise HTTPException(status_code=400, detail="confirm_CREATE_ASTER_PAPER_TRADING_LEDGER_required")
    return await asyncio.to_thread(create_aster_paper_trading_ledger_table, dry_run, confirm)


@router.get("/rpc/aster-paper-trading-run-preview")
@router.post("/rpc/aster-paper-trading-run-preview")
async def rpc_aster_paper_trading_run_preview(
    symbols: str | None = "BTCUSDT",
    token_addresses: str | None = None,
    dry_run: bool = True,
    timeout_seconds: int = 8,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    return await asyncio.to_thread(
        get_aster_paper_trading_run_preview,
        symbols,
        token_addresses,
        dry_run,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
    )


@router.post("/rpc/aster-paper-trading-replay-insert")
async def rpc_aster_paper_trading_replay_insert(
    symbol: str | None = "BTCUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    max_events: int = 100,
    timeout_seconds: int = 8,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    _: None = Depends(_require_data_admin),
):
    if max_events > 1000:
        raise HTTPException(status_code=400, detail="max_events_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if not dry_run and confirm != "CONFIRM_ASTER_PAPER_REPLAY_INSERT":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_ASTER_PAPER_REPLAY_INSERT_required")
    return await asyncio.to_thread(
        get_aster_paper_trading_replay_insert,
        symbol,
        dry_run,
        confirm,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
    )


@router.get("/rpc/aster-paper-trading-ledger-analytics")
@router.post("/rpc/aster-paper-trading-ledger-analytics")
async def rpc_aster_paper_trading_ledger_analytics(
    run_id: str | None = None,
    symbol: str | None = None,
    since_timestamp: str | None = None,
    initial_balance_usd: float = 1000.0,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    return await asyncio.to_thread(
        get_aster_paper_trading_ledger_analytics,
        run_id,
        symbol,
        since_timestamp,
        initial_balance_usd,
        dry_run,
    )


@router.post("/rpc/aster-paper-trading-watchlist-replay-insert")
async def rpc_aster_paper_trading_watchlist_replay_insert(
    symbols: str | None = "SOLUSDT,DOGEUSDT,PEPEUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    max_events: int = 100,
    timeout_seconds: int = 8,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 500,
    _: None = Depends(_require_data_admin),
):
    if len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 10:
        raise HTTPException(status_code=400, detail="symbols_max_10")
    if max_events > 1000:
        raise HTTPException(status_code=400, detail="max_events_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    if not dry_run and confirm != "CONFIRM_ASTER_WATCHLIST_REPLAY_INSERT":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_ASTER_WATCHLIST_REPLAY_INSERT_required")
    return await asyncio.to_thread(
        get_aster_paper_trading_watchlist_replay_insert,
        symbols,
        dry_run,
        confirm,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-paper-trading-strategy-report")
@router.post("/rpc/aster-paper-trading-strategy-report")
async def rpc_aster_paper_trading_strategy_report(
    run_id_prefix: str | None = None,
    initial_balance_usd: float = 1000.0,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    return await asyncio.to_thread(
        get_aster_paper_trading_strategy_report,
        run_id_prefix,
        initial_balance_usd,
        dry_run,
    )


@router.get("/rpc/aster-paper-trading-gate-calibration-preview")
@router.post("/rpc/aster-paper-trading-gate-calibration-preview")
async def rpc_aster_paper_trading_gate_calibration_preview(
    symbols: str | None = "LABUSDT,ORDIUSDT,1000SATSUSDT,PEPEUSDT,DOGEUSDT",
    dry_run: bool = True,
    max_events: int = 2000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 10:
        raise HTTPException(status_code=400, detail="symbols_max_10")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_paper_trading_gate_calibration_preview,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
    )


@router.get("/rpc/aster-paper-trading-extended-backtest-preview")
@router.post("/rpc/aster-paper-trading-extended-backtest-preview")
async def rpc_aster_paper_trading_extended_backtest_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    max_events: int = 5000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 30:
        raise HTTPException(status_code=400, detail="symbols_max_30")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_paper_trading_extended_backtest_preview,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
    )


@router.get("/rpc/aster-paper-trading-signal-cinematic-diagnostic")
@router.post("/rpc/aster-paper-trading-signal-cinematic-diagnostic")
async def rpc_aster_paper_trading_signal_cinematic_diagnostic(
    symbols: str | None = "ARBUSDT,1000SATSUSDT",
    dry_run: bool = True,
    max_events: int = 5000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 10:
        raise HTTPException(status_code=400, detail="symbols_max_10")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_paper_trading_signal_cinematic_diagnostic,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
    )


@router.get("/rpc/aster-paper-trading-risk-recalibration-test")
@router.post("/rpc/aster-paper-trading-risk-recalibration-test")
async def rpc_aster_paper_trading_risk_recalibration_test(
    symbols: str | None = "1000SATSUSDT,ORDIUSDT,ARBUSDT",
    dry_run: bool = True,
    max_events: int = 5000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    stop_loss_pct: float = -25.0,
    take_profit_pct: float = 15.0,
    trailing_stop_activation_pct: float = 10.0,
    trailing_stop_distance_pct: float = 5.0,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 10:
        raise HTTPException(status_code=400, detail="symbols_max_10")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_paper_trading_risk_recalibration_test,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        stop_loss_pct,
        take_profit_pct,
        trailing_stop_activation_pct,
        trailing_stop_distance_pct,
    )


@router.get("/rpc/aster-paper-trading-hybrid-signal-test")
@router.post("/rpc/aster-paper-trading-hybrid-signal-test")
async def rpc_aster_paper_trading_hybrid_signal_test(
    symbols: str | None = "LABUSDT,ORDIUSDT,1000SATSUSDT",
    dry_run: bool = True,
    max_events: int = 2000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    min_aster_score: float = 70.0,
    min_behavioral_score: float | None = None,
    stop_loss_pct: float = -15.0,
    take_profit_pct: float = 50.0,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 10:
        raise HTTPException(status_code=400, detail="symbols_max_10")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_paper_trading_hybrid_signal_test,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        min_aster_score,
        min_behavioral_score,
        stop_loss_pct,
        take_profit_pct,
    )


@router.get("/rpc/aster-paper-trading-hybrid-signal-test-v2")
@router.post("/rpc/aster-paper-trading-hybrid-signal-test-v2")
async def rpc_aster_paper_trading_hybrid_signal_test_v2(
    symbols: str | None = None,
    dry_run: bool = True,
    max_events: int = 5000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    min_aster_score: float = 70.0,
    min_behavioral_score: float | None = None,
    stop_loss_pct: float = -15.0,
    take_profit_pct: float = 50.0,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 10:
        raise HTTPException(status_code=400, detail="symbols_max_10")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_paper_trading_hybrid_signal_test_v2,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        min_aster_score,
        min_behavioral_score,
        stop_loss_pct,
        take_profit_pct,
    )


@router.get("/rpc/aster-paper-trading-final-alignment-test")
@router.post("/rpc/aster-paper-trading-final-alignment-test")
async def rpc_aster_paper_trading_final_alignment_test(
    dry_run: bool = True,
    max_events: int = 2000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    min_aster_score: float = 70.0,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_paper_trading_final_alignment_test,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        min_aster_score,
    )


@router.get("/rpc/aster-paper-trading-short-fade-backtest-preview")
@router.post("/rpc/aster-paper-trading-short-fade-backtest-preview")
async def rpc_aster_paper_trading_short_fade_backtest_preview(
    symbols: str | None = "1000SATSUSDT,ORDIUSDT,WIFUSDT,PEPEUSDT",
    dry_run: bool = True,
    max_events: int = 5000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_paper_trading_short_fade_backtest_preview,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
    )


@router.get("/rpc/aster-paper-trading-60d-kline-replay-preview")
@router.post("/rpc/aster-paper-trading-60d-kline-replay-preview")
async def rpc_aster_paper_trading_60d_kline_replay_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    lookback_days: int = 60,
    interval: str = "1h",
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 12:
        raise HTTPException(status_code=400, detail="symbols_max_12")
    if lookback_days > 60:
        raise HTTPException(status_code=400, detail="lookback_days_max_60")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_60d_kline_replay_preview,
        symbols,
        True,
        lookback_days,
        interval,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-paper-trading-multi-timeframe-replay-preview")
@router.post("/rpc/aster-paper-trading-multi-timeframe-replay-preview")
async def rpc_aster_paper_trading_multi_timeframe_replay_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    lookback_days: int = 60,
    intervals: str | None = "1h,30m,15m,5m",
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 8:
        raise HTTPException(status_code=400, detail="symbols_max_8")
    if lookback_days > 60:
        raise HTTPException(status_code=400, detail="lookback_days_max_60")
    if intervals and len([item for item in str(intervals or "").replace(";", ",").split(",") if item.strip()]) > 8:
        raise HTTPException(status_code=400, detail="intervals_max_8")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_multi_timeframe_replay_preview,
        symbols,
        True,
        lookback_days,
        intervals,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-paper-trading-focused-walkforward-preview")
@router.post("/rpc/aster-paper-trading-focused-walkforward-preview")
async def rpc_aster_paper_trading_focused_walkforward_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    lookback_days: int = 60,
    intervals: str | None = "15m,30m,1h,2h,3h,4h",
    windows: int = 3,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 8:
        raise HTTPException(status_code=400, detail="symbols_max_8")
    if lookback_days > 60:
        raise HTTPException(status_code=400, detail="lookback_days_max_60")
    if intervals and len([item for item in str(intervals or "").replace(";", ",").split(",") if item.strip()]) > 8:
        raise HTTPException(status_code=400, detail="intervals_max_8")
    if windows < 2 or windows > 6:
        raise HTTPException(status_code=400, detail="windows_range_2_6")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_focused_walkforward_preview,
        symbols,
        True,
        lookback_days,
        intervals,
        windows,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-paper-trading-focused-optimization-preview")
@router.post("/rpc/aster-paper-trading-focused-optimization-preview")
async def rpc_aster_paper_trading_focused_optimization_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    lookback_days: int = 60,
    intervals: str | None = "15m,30m,1h",
    windows: int = 3,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    min_closed_trades: int = 12,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if lookback_days > 60:
        raise HTTPException(status_code=400, detail="lookback_days_max_60")
    if intervals and len([item for item in str(intervals or "").replace(";", ",").split(",") if item.strip()]) > 4:
        raise HTTPException(status_code=400, detail="intervals_max_4")
    if windows < 2 or windows > 6:
        raise HTTPException(status_code=400, detail="windows_range_2_6")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if min_closed_trades < 1 or min_closed_trades > 100:
        raise HTTPException(status_code=400, detail="min_closed_trades_range_1_100")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_focused_optimization_preview,
        symbols,
        True,
        lookback_days,
        intervals,
        windows,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        min_closed_trades,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-paper-trading-short-extended-backtest-preview")
@router.post("/rpc/aster-paper-trading-short-extended-backtest-preview")
async def rpc_aster_paper_trading_short_extended_backtest_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    max_events: int = 1000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 30:
        raise HTTPException(status_code=400, detail="symbols_max_30")
    if max_events > 1000:
        raise HTTPException(status_code=400, detail="max_events_max_1000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_short_extended_backtest_preview,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-volatile-universe-short-backtest-preview")
@router.post("/rpc/aster-volatile-universe-short-backtest-preview")
async def rpc_aster_volatile_universe_short_backtest_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    max_symbols: int = 30,
    max_events: int = 1000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    min_quote_volume_usd: float = 100000.0,
    min_abs_price_change_pct: float = 5.0,
    rate_limit_delay_ms: int = 300,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 1000.0,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 40:
        raise HTTPException(status_code=400, detail="symbols_max_40")
    if max_symbols > 40:
        raise HTTPException(status_code=400, detail="max_symbols_max_40")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_volatile_universe_short_backtest_preview,
        symbols,
        True,
        max_symbols,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        min_quote_volume_usd,
        min_abs_price_change_pct,
        rate_limit_delay_ms,
        min_aster_score,
        min_window_volume_usd,
    )


@router.get("/rpc/aster-short-fade-universe-selection-preview")
@router.post("/rpc/aster-short-fade-universe-selection-preview")
async def rpc_aster_short_fade_universe_selection_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    max_symbols: int = 30,
    max_events: int = 1000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    rate_limit_delay_ms: int = 300,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 1000.0,
    min_closed_trades: int = 2,
    min_win_rate: float = 0.60,
    max_recommendations: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 40:
        raise HTTPException(status_code=400, detail="symbols_max_40")
    if max_symbols > 40:
        raise HTTPException(status_code=400, detail="max_symbols_max_40")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_short_fade_universe_selection_preview,
        symbols,
        True,
        max_symbols,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        rate_limit_delay_ms,
        min_aster_score,
        min_window_volume_usd,
        min_closed_trades,
        min_win_rate,
        max_recommendations,
    )


@router.get("/rpc/aster-paper-trading-short-time-stop-walkforward-preview")
@router.post("/rpc/aster-paper-trading-short-time-stop-walkforward-preview")
async def rpc_aster_paper_trading_short_time_stop_walkforward_preview(
    symbols: str | None = "1000SATSUSDT,ORDIUSDT,WIFUSDT",
    dry_run: bool = True,
    max_events: int = 1000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    max_holding_trades: int = 200,
    max_holding_seconds: float | None = None,
    rate_limit_delay_ms: int = 300,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 1000.0,
    short_stop_loss_pct: float = 15.0,
    short_take_profit_pct: float = -25.0,
    trailing_stop_activation_pct: float = 10.0,
    trailing_stop_distance_pct: float = 5.0,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 30:
        raise HTTPException(status_code=400, detail="symbols_max_30")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if max_holding_trades > 10_000:
        raise HTTPException(status_code=400, detail="max_holding_trades_max_10000")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_short_walkforward_preview,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        max_holding_trades,
        max_holding_seconds,
        rate_limit_delay_ms,
        min_aster_score,
        min_window_volume_usd,
        short_stop_loss_pct,
        short_take_profit_pct,
        trailing_stop_activation_pct,
        trailing_stop_distance_pct,
    )


@router.get("/rpc/aster-paper-trading-short-time-stop-calibration-preview")
@router.post("/rpc/aster-paper-trading-short-time-stop-calibration-preview")
async def rpc_aster_paper_trading_short_time_stop_calibration_preview(
    symbols: str | None = "1000SATSUSDT,ORDIUSDT,WIFUSDT",
    dry_run: bool = True,
    max_events: int = 2000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    max_holding_trades_values: str | None = "100,200,300,400,500,1000,None",
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if max_events > 5000:
        raise HTTPException(status_code=400, detail="max_events_max_5000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_short_time_stop_calibration_preview,
        symbols,
        dry_run,
        max_events,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        max_holding_trades_values,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-paper-trading-forward-monitor-preview")
@router.post("/rpc/aster-paper-trading-forward-monitor-preview")
async def rpc_aster_paper_trading_forward_monitor_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 200,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 8:
        raise HTTPException(status_code=400, detail="symbols_max_8")
    if not dry_run and confirm != "CONFIRM_FORWARD_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_FORWARD_PAPER_TRADE_required")
    if forward_window_trades > 1000:
        raise HTTPException(status_code=400, detail="forward_window_trades_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_forward_monitor_preview,
        symbols,
        dry_run,
        confirm,
        forward_window_trades,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-optimized-long-forward-monitor-preview")
@router.post("/rpc/aster-optimized-long-forward-monitor-preview")
async def rpc_aster_optimized_long_forward_monitor_preview(
    symbols: str | None = "INJUSDT,NEARUSDT,TIAUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if not dry_run and confirm != "CONFIRM_FORWARD_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_FORWARD_PAPER_TRADE_required")
    if forward_window_trades > 1000:
        raise HTTPException(status_code=400, detail="forward_window_trades_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_optimized_long_forward_monitor_preview,
        symbols,
        dry_run,
        confirm,
        forward_window_trades,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-optimized-long-stateful-monitor")
@router.post("/rpc/aster-optimized-long-stateful-monitor")
async def rpc_aster_optimized_long_stateful_monitor(
    symbols: str | None = "INJUSDT,NEARUSDT,TIAUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    allowed_entry_utc_hours: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if not dry_run and confirm != "CONFIRM_FORWARD_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_FORWARD_PAPER_TRADE_required")
    if forward_window_trades > 1000:
        raise HTTPException(status_code=400, detail="forward_window_trades_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_optimized_long_stateful_monitor,
        symbols,
        dry_run,
        confirm,
        forward_window_trades,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
        allowed_entry_utc_hours,
    )


@router.get("/rpc/aster-optimized-long-regime-diagnostic-preview")
@router.post("/rpc/aster-optimized-long-regime-diagnostic-preview")
async def rpc_aster_optimized_long_regime_diagnostic_preview(
    min_closed_trades_per_hour: int = 2,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if min_closed_trades_per_hour < 1 or min_closed_trades_per_hour > 20:
        raise HTTPException(status_code=400, detail="min_closed_trades_per_hour_range_1_20")
    return await asyncio.to_thread(
        get_aster_optimized_long_regime_diagnostic_preview,
        min_closed_trades_per_hour,
        dry_run,
    )


@router.get("/rpc/aster-paper-trading-forward-short-monitor-preview")
@router.post("/rpc/aster-paper-trading-forward-short-monitor-preview")
async def rpc_aster_paper_trading_forward_short_monitor_preview(
    symbols: str | None = "LABUSDT,ORDIUSDT,1000SATSUSDT,PEPEUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 200,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 4:
        raise HTTPException(status_code=400, detail="symbols_max_4")
    if not dry_run and confirm != "CONFIRM_FORWARD_SHORT_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_FORWARD_SHORT_PAPER_TRADE_required")
    if forward_window_trades > 1000:
        raise HTTPException(status_code=400, detail="forward_window_trades_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_forward_short_monitor_preview,
        symbols,
        dry_run,
        confirm,
        forward_window_trades,
        timeout_seconds,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-paper-trading-stateful-session-monitor")
@router.post("/rpc/aster-paper-trading-stateful-session-monitor")
async def rpc_aster_paper_trading_stateful_session_monitor(
    symbols: str | None = "LABUSDT,ORDIUSDT,1000SATSUSDT,PEPEUSDT,1000BONKUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 200,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1000.0,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if not dry_run and confirm != "CONFIRM_STATEFUL_FORWARD_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_STATEFUL_FORWARD_PAPER_TRADE_required")
    if forward_window_trades > 1000:
        raise HTTPException(status_code=400, detail="forward_window_trades_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_paper_trading_stateful_session_monitor,
        symbols,
        dry_run,
        confirm,
        forward_window_trades,
        timeout_seconds,
        wallet_balance_usd,
        rate_limit_delay_ms,
    )


@router.post("/rpc/aster-agent-command-center-preview")
async def rpc_aster_agent_command_center_preview(
    symbols: str | None = "LABUSDT,ORDIUSDT,1000SATSUSDT,WIFUSDT",
    staging_mode: bool = False,
    dry_run: bool = True,
    timeout_seconds: int = 5,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required_for_command_center_preview")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    return await asyncio.to_thread(
        get_aster_agent_command_center_preview,
        symbols,
        staging_mode,
        True,
        timeout_seconds,
    )


@router.get("/rpc/aster-demo-testnet-readiness-preview")
@router.post("/rpc/aster-demo-testnet-readiness-preview")
async def rpc_aster_demo_testnet_readiness_preview(
    symbol: str | None = "BTCUSDT",
    dry_run: bool = True,
    timeout_seconds: int = 10,
    include_signed_readonly_probe: bool = False,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_demo_testnet_readiness_preview,
        symbol,
        True,
        timeout_seconds,
        include_signed_readonly_probe,
    )


@router.get("/rpc/aster-demo-order-intent-validator-preview")
@router.post("/rpc/aster-demo-order-intent-validator-preview")
async def rpc_aster_demo_order_intent_validator_preview(
    symbols: str | None = "LABUSDT,INJUSDT,TIAUSDT,INTCUSDT",
    side: str = "BUY",
    position_size_usd: float = 50.0,
    dry_run: bool = True,
    timeout_seconds: int = 10,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 10:
        raise HTTPException(status_code=400, detail="symbols_max_10")
    if side.upper() not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="side_must_be_BUY_or_SELL")
    if position_size_usd > 1000:
        raise HTTPException(status_code=400, detail="position_size_usd_max_1000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    return await asyncio.to_thread(
        get_aster_demo_order_intent_validator_preview,
        symbols,
        side,
        position_size_usd,
        True,
        timeout_seconds,
    )


@router.get("/rpc/aster-forward-reality-comparison-preview")
@router.post("/rpc/aster-forward-reality-comparison-preview")
async def rpc_aster_forward_reality_comparison_preview(
    symbols: str | None = "LABUSDT,INJUSDT,TIAUSDT,INTCUSDT,MSFTUSDT,CRCLUSDT",
    dry_run: bool = True,
    max_events: int = 1000,
    timeout_seconds: int = 10,
    max_ledger_rows: int = 200,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 12:
        raise HTTPException(status_code=400, detail="symbols_max_12")
    if max_events > 1000:
        raise HTTPException(status_code=400, detail="max_events_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if max_ledger_rows > 1000:
        raise HTTPException(status_code=400, detail="max_ledger_rows_max_1000")
    return await asyncio.to_thread(
        get_aster_forward_reality_comparison_preview,
        symbols,
        True,
        max_events,
        timeout_seconds,
        max_ledger_rows,
    )


@router.get("/rpc/aster-selected-short-fade-forward-monitor-preview")
@router.post("/rpc/aster-selected-short-fade-forward-monitor-preview")
async def rpc_aster_selected_short_fade_forward_monitor_preview(
    symbols: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1000.0,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 10:
        raise HTTPException(status_code=400, detail="symbols_max_10")
    if not dry_run and confirm != "CONFIRM_STATEFUL_FORWARD_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_STATEFUL_FORWARD_PAPER_TRADE_required")
    if forward_window_trades > 1000:
        raise HTTPException(status_code=400, detail="forward_window_trades_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    return await asyncio.to_thread(
        get_aster_selected_short_fade_forward_monitor_preview,
        symbols,
        dry_run,
        confirm,
        forward_window_trades,
        timeout_seconds,
        wallet_balance_usd,
        rate_limit_delay_ms,
    )


@router.get("/rpc/aster-paper-trading-executor-confirm")
@router.post("/rpc/aster-paper-trading-executor-confirm")
async def rpc_aster_paper_trading_executor_confirm(
    symbols: str | None = "LABUSDT,ORDIUSDT,1000SATSUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 200,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1000.0,
    rate_limit_delay_ms: int = 300,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if forward_window_trades > 1000:
        raise HTTPException(status_code=400, detail="forward_window_trades_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms < 0 or rate_limit_delay_ms > 5000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_range_0_5000")
    if dry_run:
        return await asyncio.to_thread(
            get_aster_paper_trading_stateful_session_monitor,
            symbols,
            True,
            None,
            forward_window_trades,
            timeout_seconds,
            wallet_balance_usd,
            rate_limit_delay_ms,
        )
    if confirm != "CONFIRM_STATEFUL_FORWARD_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_STATEFUL_FORWARD_PAPER_TRADE_required")

    execution = await asyncio.to_thread(
        get_aster_paper_trading_stateful_session_monitor,
        symbols,
        False,
        confirm,
        forward_window_trades,
        timeout_seconds,
        wallet_balance_usd,
        rate_limit_delay_ms,
    )
    run_ids = [item for item in (execution.get("session_run_ids") or []) if item]
    analytics_by_run_id = []
    totals = {
        "entries": 0,
        "exits": 0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "max_drawdown": 0.0,
        "weighted_wins": 0.0,
    }
    for run_id in run_ids:
        metrics = await asyncio.to_thread(
            get_aster_paper_trading_ledger_analytics,
            run_id,
            None,
            None,
            wallet_balance_usd,
            True,
        )
        analytics_by_run_id.append({"run_id": run_id, "metrics": metrics})
        exits = int(metrics.get("total_exits") or 0)
        totals["entries"] += int(metrics.get("total_entries") or 0)
        totals["exits"] += exits
        totals["gross_profit"] += float(metrics.get("gross_profit_usd") or 0.0)
        totals["gross_loss"] += float(metrics.get("gross_loss_usd") or 0.0)
        totals["net_pnl"] += float(metrics.get("net_pnl_usd") or 0.0)
        totals["max_drawdown"] = max(totals["max_drawdown"], float(metrics.get("max_drawdown_usd") or 0.0))
        if metrics.get("win_rate") is not None:
            totals["weighted_wins"] += float(metrics.get("win_rate") or 0.0) * exits
    win_rate = round(totals["weighted_wins"] / totals["exits"], 6) if totals["exits"] else None
    profit_factor = round(totals["gross_profit"] / totals["gross_loss"], 6) if totals["gross_loss"] else (None if totals["gross_profit"] <= 0 else "unbounded_no_losses")
    edge_confirmed = bool(
        win_rate is not None
        and isinstance(profit_factor, float)
        and win_rate >= 0.55
        and profit_factor >= 1.3
    )
    return {
        "ok": bool(execution.get("ok")),
        "dry_run": False,
        "execution_status": execution.get("stateful_status"),
        "run_ids": run_ids,
        "persisted_trades": execution.get("rows_inserted", 0),
        "session_metrics": {
            "total_entries": totals["entries"],
            "total_exits": totals["exits"],
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_usd": round(totals["max_drawdown"], 6),
            "net_pnl_usd": round(totals["net_pnl"], 6),
            "analytics_by_run_id": analytics_by_run_id,
        },
        "short_strategy_validation": "edge_confirmed" if edge_confirmed else "needs_calibration",
        "execution_preview": execution,
        "would_execute_trade": False,
        "would_send_transaction": False,
        "would_create_wallet_order": False,
    }


@router.get("/rpc/aster-paper-trading-optimizer-and-executor")
@router.post("/rpc/aster-paper-trading-optimizer-and-executor")
async def rpc_aster_paper_trading_optimizer_and_executor(
    symbols: str | None = "WIFUSDT,PEPEUSDT,ORDIUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    max_events: int = 1000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1000.0,
    _: None = Depends(_require_data_admin),
):
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if max_events > 1000:
        raise HTTPException(status_code=400, detail="max_events_max_1000")
    if timeout_seconds > 15:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_15")
    if not dry_run and confirm != "CONFIRM_STATEFUL_FORWARD_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_STATEFUL_FORWARD_PAPER_TRADE_required")

    previous_metrics = await asyncio.to_thread(get_aster_paper_trading_ledger_analytics, None, None, None, wallet_balance_usd, True)
    candidates = [
        {"name": "baseline", "sl": 15.0, "tp": -25.0, "ta": 10.0, "td": 5.0},
        {"name": "fast_take_profit", "sl": 12.0, "tp": -10.0, "ta": 5.0, "td": 3.0},
        {"name": "balanced_fast", "sl": 15.0, "tp": -15.0, "ta": 8.0, "td": 4.0},
        {"name": "aggressive_exit", "sl": 10.0, "tp": -8.0, "ta": 4.0, "td": 2.0},
    ]
    optimization_runs = []
    best = None
    for params in candidates:
        result = await asyncio.to_thread(
            get_aster_paper_trading_short_extended_backtest_preview,
            symbols,
            True,
            max_events,
            timeout_seconds,
            wallet_balance_usd,
            6.0,
            10.0,
            20,
            100,
            70.0,
            1000.0,
            params["sl"],
            params["tp"],
            params["ta"],
            params["td"],
        )
        stats = result.get("global_stats_short") or {}
        closed = int(stats.get("closed_trades") or 0)
        wr = float(stats.get("win_rate") or 0.0)
        pf = stats.get("profit_factor")
        pf_eval = float(pf) if isinstance(pf, (int, float)) else (999.0 if stats.get("profit_factor_status") == "unbounded_no_losses" and closed else 0.0)
        score = (pf_eval * 1000.0) + (closed * 10.0) + wr
        row = {"params": params, "stats": stats, "verdict": result.get("verdict_statistique"), "selection_score": round(score, 6)}
        optimization_runs.append(row)
        if closed > 0 and wr > 0.5 and pf_eval >= 1.3 and (best is None or score > best["selection_score"]):
            best = row

    if best is None:
        return {
            "ok": True,
            "dry_run": dry_run,
            "status": "insufficient_edge_for_calibration",
            "previous_metrics": previous_metrics,
            "optimization_runs": optimization_runs,
            "execution_skipped": True,
            "would_execute_trade": False,
            "would_send_transaction": False,
            "would_create_wallet_order": False,
        }

    p = best["params"]
    execution = await asyncio.to_thread(
        get_aster_paper_trading_stateful_session_monitor,
        symbols,
        bool(dry_run),
        None if dry_run else confirm,
        800,
        10,
        wallet_balance_usd,
        300,
        70.0,
        1000.0,
        -25.0,
        15.0,
        p["sl"],
        p["tp"],
        p["ta"],
        p["td"],
    )
    new_metrics = []
    for run_id in execution.get("session_run_ids") or []:
        new_metrics.append(
            {
                "run_id": run_id,
                "metrics": await asyncio.to_thread(get_aster_paper_trading_ledger_analytics, run_id, None, None, wallet_balance_usd, True),
            }
        )
    closed = sum(int((item.get("metrics") or {}).get("total_exits") or 0) for item in new_metrics)
    wins = sum(float((item.get("metrics") or {}).get("win_rate") or 0.0) * int((item.get("metrics") or {}).get("total_exits") or 0) for item in new_metrics)
    gross_profit = sum(float((item.get("metrics") or {}).get("gross_profit_usd") or 0.0) for item in new_metrics)
    gross_loss = sum(float((item.get("metrics") or {}).get("gross_loss_usd") or 0.0) for item in new_metrics)
    win_rate = round(wins / closed, 6) if closed else None
    profit_factor = round(gross_profit / gross_loss, 6) if gross_loss else (None if gross_profit <= 0 else "unbounded_no_losses")
    edge_confirmed = bool(win_rate is not None and isinstance(profit_factor, float) and win_rate >= 0.55 and profit_factor >= 1.3)
    return {
        "ok": True,
        "dry_run": dry_run,
        "status": "executed" if not dry_run else "preview_ready",
        "optimized_params_used": p,
        "previous_metrics": previous_metrics,
        "new_metrics": {"runs": new_metrics, "win_rate": win_rate, "profit_factor": profit_factor},
        "validation_status": "edge_confirmed" if edge_confirmed else "needs_more_closed_trades_or_calibration",
        "execution": execution,
        "optimization_runs": optimization_runs,
        "would_execute_trade": False,
        "would_send_transaction": False,
        "would_create_wallet_order": False,
    }


@router.get("/rpc/aster-paper-trading-optimizer-executor-confirm")
@router.post("/rpc/aster-paper-trading-optimizer-executor-confirm")
async def rpc_aster_paper_trading_optimizer_executor_confirm(
    symbols: str | None = "WIFUSDT,PEPEUSDT,ORDIUSDT",
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1000.0,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if confirm != "CONFIRM_STATEFUL_FORWARD_PAPER_TRADE":
        raise HTTPException(status_code=400, detail="confirm_CONFIRM_STATEFUL_FORWARD_PAPER_TRADE_required")
    if symbols and len([item for item in str(symbols or "").replace(";", ",").split(",") if item.strip()]) > 5:
        raise HTTPException(status_code=400, detail="symbols_max_5")
    if forward_window_trades > 1000:
        raise HTTPException(status_code=400, detail="forward_window_trades_max_1000")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")

    before = await asyncio.to_thread(get_aster_paper_trading_ledger_analytics, None, None, None, wallet_balance_usd, True)
    if not before.get("ok"):
        return {
            "ok": False,
            "execution_status": "blocked",
            "blockers": ["ledger_table_missing"],
            "ledger_analytics": before,
            "persisted_trades": 0,
            "would_execute_trade": False,
            "would_send_transaction": False,
            "would_create_wallet_order": False,
        }

    execution = await asyncio.to_thread(
        get_aster_paper_trading_stateful_session_monitor,
        symbols,
        False,
        "CONFIRM_STATEFUL_FORWARD_PAPER_TRADE",
        forward_window_trades,
        timeout_seconds,
        wallet_balance_usd,
        300,
        70.0,
        1000.0,
        -25.0,
        15.0,
        10.0,
        -8.0,
        4.0,
        2.0,
    )
    if not execution.get("ok"):
        return {
            "ok": False,
            "execution_status": execution.get("stateful_status") or "error",
            "persisted_trades": execution.get("rows_inserted", 0),
            "session_metrics": None,
            "short_strategy_validation": "needs_calibration",
            "execution_preview": execution,
            "would_execute_trade": False,
            "would_send_transaction": False,
            "would_create_wallet_order": False,
        }

    totals = {
        "entries": 0,
        "exits": 0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "max_drawdown": 0.0,
        "weighted_wins": 0.0,
    }
    analytics_by_run_id = []
    for run_id in execution.get("session_run_ids") or []:
        metrics = await asyncio.to_thread(get_aster_paper_trading_ledger_analytics, run_id, None, None, wallet_balance_usd, True)
        analytics_by_run_id.append({"run_id": run_id, "metrics": metrics})
        exits = int(metrics.get("total_exits") or 0)
        totals["entries"] += int(metrics.get("total_entries") or 0)
        totals["exits"] += exits
        totals["gross_profit"] += float(metrics.get("gross_profit_usd") or 0.0)
        totals["gross_loss"] += float(metrics.get("gross_loss_usd") or 0.0)
        totals["net_pnl"] += float(metrics.get("net_pnl_usd") or 0.0)
        totals["max_drawdown"] = max(totals["max_drawdown"], float(metrics.get("max_drawdown_usd") or 0.0))
        if metrics.get("win_rate") is not None:
            totals["weighted_wins"] += float(metrics.get("win_rate") or 0.0) * exits

    win_rate = round(totals["weighted_wins"] / totals["exits"], 6) if totals["exits"] else None
    profit_factor = round(totals["gross_profit"] / totals["gross_loss"], 6) if totals["gross_loss"] else (None if totals["gross_profit"] <= 0 else "unbounded_no_losses")
    edge_confirmed = bool(win_rate is not None and isinstance(profit_factor, float) and win_rate >= 0.55 and profit_factor >= 1.3)
    return {
        "ok": True,
        "execution_status": execution.get("stateful_status") or "inserted",
        "persisted_trades": execution.get("rows_inserted", 0),
        "optimized_params_used": {
            "stop_loss_pct": 10.0,
            "take_profit_pct": -8.0,
            "trailing_stop_activation_pct": 4.0,
            "trailing_stop_distance_pct": 2.0,
            "max_holding_trades": 600,
        },
        "session_metrics": {
            "total_entries": totals["entries"],
            "total_exits": totals["exits"],
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": round(totals["max_drawdown"], 6),
            "net_pnl": round(totals["net_pnl"], 6),
            "analytics_by_run_id": analytics_by_run_id,
        },
        "short_strategy_validation": "edge_confirmed" if edge_confirmed else "needs_calibration",
        "execution_preview": execution,
        "would_execute_trade": False,
        "would_send_transaction": False,
        "would_create_wallet_order": False,
        "would_create_client_signal": False,
    }


@router.get("/rpc/scrapling-label-enrichment-preview")
@router.post("/rpc/scrapling-label-enrichment-preview")
async def rpc_scrapling_label_enrichment_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    min_behavioral_score: int = 60,
    max_snapshot_files: int = 100,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if max_snapshot_files > 500:
        raise HTTPException(status_code=400, detail="max_snapshot_files_max_500")
    return await asyncio.to_thread(
        get_scrapling_label_enrichment_preview,
        chain,
        limit,
        min_behavioral_score,
        max_snapshot_files,
        dry_run,
    )


@router.get("/rpc/dexscreener-enrichment-preview")
@router.post("/rpc/dexscreener-enrichment-preview")
async def rpc_dexscreener_enrichment_preview(
    chain: str | None = "bsc",
    limit: int = 20,
    min_behavioral_score: int = 60,
    timeout_seconds: int = 10,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 20:
        raise HTTPException(status_code=400, detail="limit_max_20")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    return await asyncio.to_thread(
        get_dexscreener_enrichment_preview,
        chain,
        limit,
        min_behavioral_score,
        timeout_seconds,
        dry_run,
    )


def _summary_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "mean": None, "median": None}
    ordered = sorted(values)
    count = len(ordered)
    mid = count // 2
    median = ordered[mid] if count % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "min": round(ordered[0], 6),
        "max": round(ordered[-1], 6),
        "mean": round(sum(ordered) / count, 6),
        "median": round(median, 6),
    }


def _ratio_distribution(values: list[float]) -> dict[str, int]:
    return {
        "zero": sum(1 for value in values if value <= 0),
        "gt_0_to_lt_1": sum(1 for value in values if 0 < value < 1),
        "gte_1_to_lt_3": sum(1 for value in values if 1 <= value < 3),
        "gte_3_to_lt_10": sum(1 for value in values if 3 <= value < 10),
        "gte_10": sum(1 for value in values if value >= 10),
    }


def _dexscreener_watchlist_status(row: dict[str, Any]) -> str:
    composite = _score_diag_float(row.get("composite_score"))
    ratio = _score_diag_float(row.get("volume_liquidity_ratio"))
    behavioral = row.get("behavioral_score")
    if composite >= 70:
        return "suspicious"
    if behavioral is None and ratio >= 3.5:
        return "watchlist"
    return "normal"


@router.get("/rpc/dexscreener-enrichment-batch-preview")
@router.post("/rpc/dexscreener-enrichment-batch-preview")
async def rpc_dexscreener_enrichment_batch_preview(
    chain: str | None = "bsc",
    limit: int = 50,
    min_behavioral_score: int = 40,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 200,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms > 2_000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_max_2000")
    preview = await asyncio.to_thread(
        get_dexscreener_enrichment_preview,
        chain,
        limit,
        min_behavioral_score,
        timeout_seconds,
        dry_run,
    )
    rows = [row for row in preview.get("enrichment_rows", []) if isinstance(row, dict)]
    composite_scores = [float(row.get("composite_score") or 0) for row in rows]
    volume_liquidity_ratios = [float(row.get("volume_liquidity_ratio") or 0) for row in rows]
    top_rows = sorted(rows, key=lambda row: float(row.get("composite_score") or 0), reverse=True)[:5]
    watchlist_rows = [
        {**row, "watchlist_status": _dexscreener_watchlist_status(row)}
        for row in rows
        if _dexscreener_watchlist_status(row) == "watchlist"
    ]
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready" if rows else "blocked",
        "source_policy": "dexscreener_batch_preview_aggregates_existing_preview_only",
        "chain": chain or "bsc",
        "requested_limit": limit,
        "requested_min_behavioral_score": min_behavioral_score,
        "rate_limit_delay_ms": rate_limit_delay_ms,
        "rate_limit_note": "the existing preview function owns individual DexScreener calls; this endpoint only aggregates its result",
        "base_preview_status": preview.get("preview_status"),
        "candidates_checked": preview.get("candidates_checked"),
        "http_calls_attempted": preview.get("http_calls_attempted"),
        "stats": {
            "composite_score": _summary_stats(composite_scores),
            "volume_liquidity_ratio": _summary_stats(volume_liquidity_ratios),
            "suspicious_count": sum(1 for row in rows if row.get("is_suspicious")),
            "watchlist_count": len(watchlist_rows),
            "volume_liquidity_ratio_distribution": _ratio_distribution(volume_liquidity_ratios),
        },
        "top_5_by_composite_score": top_rows,
        "watchlist_candidates": sorted(
            watchlist_rows,
            key=lambda row: float(row.get("volume_liquidity_ratio") or 0),
            reverse=True,
        )[:5],
        "status_counts": {
            status: sum(1 for row in rows if row.get("dexscreener_status") == status)
            for status in sorted({str(row.get("dexscreener_status") or "unknown") for row in rows})
        },
        "blockers": preview.get("blockers") or [],
        "would_write": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "writes_performed": 0,
    }


@router.get("/rpc/dexscreener-first-discovery-preview")
@router.post("/rpc/dexscreener-first-discovery-preview")
async def rpc_dexscreener_first_discovery_preview(
    chain: str | None = "bsc",
    limit: int = 30,
    min_liquidity_usd: float = 10_000,
    min_volume_liquidity_ratio: float = 3,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 30:
        raise HTTPException(status_code=400, detail="limit_max_30")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms > 2_000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_max_2000")
    return await asyncio.to_thread(
        get_dexscreener_first_discovery_preview,
        chain,
        limit,
        min_liquidity_usd,
        min_volume_liquidity_ratio,
        timeout_seconds,
        rate_limit_delay_ms,
        dry_run,
    )


def _score_diag_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _score_diag_address(value: Any) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean.startswith("0x") and len(clean) == 42 else ""


def _score_composition_from_dexscreener_row(row: dict[str, Any]) -> dict[str, Any]:
    behavioral = row.get("behavioral_score")
    behavioral_value = _score_diag_float(behavioral)
    ratio = _score_diag_float(row.get("volume_liquidity_ratio"))
    buy_sell = _score_diag_float(row.get("buy_sell_ratio"))
    behavioral_contribution = behavioral_value * 0.4 if behavioral is not None else 0.0
    ratio_contribution = ratio * 15.0
    buy_sell_contribution = buy_sell * 10.0
    diagnostic_formula_score = behavioral_contribution + ratio_contribution + buy_sell_contribution
    actual_composite = _score_diag_float(row.get("composite_score"))
    reasons: list[str] = []
    if actual_composite < 70:
        reasons.append("composite_score_below_70")
    if behavioral is None and ratio < 5:
        reasons.append("external_only_volume_liquidity_ratio_below_5")
    if behavioral is not None and actual_composite < 70:
        reasons.append("local_behavioral_refinement_not_strong_enough")
    behavioral_needed = max(0.0, (70.0 - ratio_contribution - buy_sell_contribution) / 0.4)
    formula_ratio_needed = max(0.0, (70.0 - behavioral_contribution - buy_sell_contribution) / 15.0)
    suspicious_threshold = (
        f"volume_liquidity_ratio >= 5.0 OR behavioral_score >= {round(behavioral_needed, 2)}"
        if behavioral is None
        else f"behavioral_score >= {round(behavioral_needed, 2)} OR volume_liquidity_ratio >= {round(formula_ratio_needed, 6)}"
    )
    return {
        "watchlist_status": row.get("watchlist_status") or "normal",
        "reason_for_watchlist": row.get("reason_for_watchlist"),
        "threshold_to_reach_suspicious": suspicious_threshold,
        "behavioral_score_local": {
            "value": behavioral,
            "source": "local_behavioral_score_pump_backtest_preview" if behavioral is not None else None,
            "status": row.get("local_behavioral_status") if behavioral is not None else "not_indexed_locally",
        },
        "volume_liquidity_ratio": {
            "value": round(ratio, 6),
            "contribution_to_composite": round(ratio_contribution, 6),
        },
        "buy_sell_ratio": {
            "value": round(buy_sell, 6),
            "contribution_to_composite": round(buy_sell_contribution, 6),
        },
        "composite_breakdown": {
            "formula": "(behavioral * 0.4) + (volume_liquidity_ratio * 15) + (buy_sell_ratio * 10)",
            "behavioral_component": round(behavioral_contribution, 6),
            "volume_liquidity_component": round(ratio_contribution, 6),
            "buy_sell_component": round(buy_sell_contribution, 6),
            "diagnostic_formula_score": round(diagnostic_formula_score, 6),
            "actual_preview_composite_score": row.get("composite_score"),
            "note": "When behavioral_score is null, the first-discovery preview currently uses volume_liquidity_ratio * 15 as the external-only fallback score; buy/sell contribution is shown for calibration diagnostics.",
        },
        "suspicious_explanation": {
            "is_suspicious": bool(row.get("is_suspicious")),
            "criteria": [
                "actual composite_score >= 70",
                "OR behavioral_score is null and volume_liquidity_ratio >= 5",
            ],
            "failed_criteria": reasons,
        },
        "suggested_adjustment": {
            "behavioral_required_at_current_market_metrics": round(behavioral_needed, 2),
            "volume_liquidity_ratio_required_by_diagnostic_formula": round(formula_ratio_needed, 6),
            "volume_liquidity_ratio_required_without_behavioral_score": 5.0 if behavioral is None else None,
            "threshold_to_reach_suspicious": suspicious_threshold,
            "plain_summary": (
                f"Pour atteindre suspicious, il faudrait environ behavioral >= {round(behavioral_needed, 2)} "
                f"ou volume_liquidity_ratio >= {round(5.0 if behavioral is None else formula_ratio_needed, 6)}."
            ),
        },
    }


@router.get("/rpc/dexscreener-score-composition-diagnostic-preview")
@router.post("/rpc/dexscreener-score-composition-diagnostic-preview")
async def rpc_dexscreener_score_composition_diagnostic_preview(
    token_address: str | None = None,
    chain: str | None = "bsc",
    limit: int = 30,
    min_liquidity_usd: float = 10_000,
    min_volume_liquidity_ratio: float = 3,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 30:
        raise HTTPException(status_code=400, detail="limit_max_30")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms > 2_000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_max_2000")
    clean_token = _score_diag_address(token_address)
    preview = await asyncio.to_thread(
        get_dexscreener_first_discovery_preview,
        chain,
        limit,
        min_liquidity_usd,
        min_volume_liquidity_ratio,
        timeout_seconds,
        rate_limit_delay_ms,
        dry_run,
    )
    rows = [row for row in preview.get("top_10_by_composite_score", []) if isinstance(row, dict)]
    selected = None
    selection_mode = "top_1_by_composite_score"
    if clean_token:
        selection_mode = "explicit_token_address"
        for row in preview.get("discovery_rows", []) or []:
            if isinstance(row, dict) and _score_diag_address(row.get("token_address")) == clean_token:
                selected = row
                break
    elif rows:
        selected = rows[0]
    if not selected:
        return {
            "ok": True,
            "dry_run": True,
            "preview_status": "blocked",
            "selection_mode": selection_mode,
            "token_address": clean_token or None,
            "blockers": ["token_not_found_in_dexscreener_first_discovery_preview" if clean_token else "no_dexscreener_first_discovery_candidates"],
            "base_preview_status": preview.get("preview_status"),
            "would_write": False,
            "would_create_label": False,
            "would_create_mapping": False,
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_create_client_opt_in": False,
            "writes_performed": 0,
        }
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready",
        "selection_mode": selection_mode,
        "chain": chain or "bsc",
        "token_address": selected.get("token_address"),
        "token_symbol": selected.get("token_symbol"),
        "dex_pair_address": selected.get("dex_pair_address"),
        "dex_id": selected.get("dex_id"),
        "dexscreener_raw_metrics": {
            "volume_24h_usd": selected.get("volume_24h_usd"),
            "liquidity_usd": selected.get("liquidity_usd"),
            "txns_24h_buys": selected.get("txns_24h_buys"),
            "txns_24h_sells": selected.get("txns_24h_sells"),
            "price_change_24h_pct": selected.get("price_change_24h_pct"),
        },
        **_score_composition_from_dexscreener_row(selected),
        "base_preview_status": preview.get("preview_status"),
        "base_discovery_source": preview.get("discovery_source"),
        "would_write": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "writes_performed": 0,
    }


def _dexscreener_calibration_token(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_address": row.get("token_address"),
        "token_symbol": row.get("token_symbol"),
        "behavioral_score": row.get("behavioral_score"),
        "volume_24h_usd": row.get("volume_24h_usd"),
        "liquidity_usd": row.get("liquidity_usd"),
        "volume_liquidity_ratio": row.get("volume_liquidity_ratio"),
        "composite_score": row.get("composite_score"),
        "watchlist_status": row.get("watchlist_status") or _dexscreener_watchlist_status(row),
    }


def _dexscreener_suggest_watchlist_threshold(rows: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = [2.0, 2.5, 3.0, 3.5, 4.0]
    best = thresholds[-1]
    best_count = 0
    for threshold in thresholds:
        count = sum(
            1
            for row in rows
            if row.get("behavioral_score") is None and _score_diag_float(row.get("volume_liquidity_ratio")) >= threshold
        )
        if 2 <= count <= 8:
            best = threshold
            best_count = count
            break
        if count > best_count:
            best = threshold
            best_count = count
    return {
        "watchlist": f"{best:.1f}",
        "suspicious_external": "5.0",
        "reason": f"captures {best_count} outliers without flooding watchlist",
    }


@router.get("/rpc/dexscreener-threshold-calibration-preview")
@router.post("/rpc/dexscreener-threshold-calibration-preview")
async def rpc_dexscreener_threshold_calibration_preview(
    chain: str | None = "bsc",
    limit: int = 30,
    min_behavioral_score: int = 30,
    min_liquidity_usd: float = 10_000,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 30:
        raise HTTPException(status_code=400, detail="limit_max_30")
    if timeout_seconds > 10:
        raise HTTPException(status_code=400, detail="timeout_seconds_max_10")
    if rate_limit_delay_ms > 2_000:
        raise HTTPException(status_code=400, detail="rate_limit_delay_ms_max_2000")
    preview = await asyncio.to_thread(
        get_dexscreener_first_discovery_preview,
        chain,
        limit,
        min_liquidity_usd,
        2.0,
        timeout_seconds,
        rate_limit_delay_ms,
        dry_run,
    )
    rows = [
        row
        for row in (preview.get("discovery_rows") or [])
        if isinstance(row, dict)
        and (row.get("behavioral_score") is None or _score_diag_float(row.get("behavioral_score")) >= min_behavioral_score)
    ][:limit]
    matrix: dict[str, Any] = {}
    thresholds = [2.0, 2.5, 3.0, 3.5, 4.0]
    for threshold in thresholds:
        watchlist_rows = [
            row
            for row in rows
            if row.get("behavioral_score") is None and _score_diag_float(row.get("volume_liquidity_ratio")) >= threshold
        ]
        suspicious_rows = [
            row
            for row in rows
            if _score_diag_float(row.get("composite_score")) >= 70
            or (row.get("behavioral_score") is None and _score_diag_float(row.get("volume_liquidity_ratio")) >= 5.0)
        ]
        matrix[f"watchlist_{threshold:.1f}"] = {
            "count": len(watchlist_rows),
            "tokens": [
                _dexscreener_calibration_token(row)
                for row in sorted(
                    watchlist_rows,
                    key=lambda item: _score_diag_float(item.get("volume_liquidity_ratio")),
                    reverse=True,
                )[:10]
            ],
            "suspicious_count": len(suspicious_rows),
            "suspicious_tokens": [
                _dexscreener_calibration_token(row)
                for row in sorted(
                    suspicious_rows,
                    key=lambda item: _score_diag_float(item.get("composite_score")),
                    reverse=True,
                )[:10]
            ],
        }
    ratios = [
        {
            "token_address": row.get("token_address"),
            "token_symbol": row.get("token_symbol"),
            "behavioral_score": row.get("behavioral_score"),
            "volume_liquidity_ratio": row.get("volume_liquidity_ratio"),
            "liquidity_usd": row.get("liquidity_usd"),
            "volume_24h_usd": row.get("volume_24h_usd"),
        }
        for row in rows
    ]
    status = "ready" if len(rows) >= 10 else "insufficient_sample"
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": status,
        "chain": chain or "bsc",
        "candidate_universe": "dexscreener_first_discovery_preview_with_ratio_floor_2_0",
        "requested_limit": limit,
        "min_behavioral_score_for_indexed_tokens": min_behavioral_score,
        "sample_size": len(rows),
        "base_preview_status": preview.get("preview_status"),
        "base_discovery_source": preview.get("discovery_source"),
        "http_calls_attempted": preview.get("http_calls_attempted"),
        "http_call_status_counts": preview.get("http_call_status_counts"),
        "calibration_matrix": matrix,
        "suggested_thresholds": _dexscreener_suggest_watchlist_threshold(rows) if len(rows) >= 10 else {
            "watchlist": "insufficient_sample",
            "suspicious_external": "5.0",
            "reason": f"only {len(rows)} tokens responded; need at least 10 before calibrating watchlist threshold",
        },
        "raw_ratios_collected": ratios,
        "blockers": [] if len(rows) >= 10 else ["insufficient_sample_min_10_tokens"],
        "would_write": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "writes_performed": 0,
    }


def _local_candidate_first_seen(row: dict[str, Any]) -> int | None:
    timestamps = [
        int(point.get("block_timestamp") or 0)
        for point in (row.get("score_curve_sample") or [])
        if isinstance(point, dict) and int(point.get("block_timestamp") or 0) > 0
    ]
    return min(timestamps) if timestamps else None


def _local_liquidity_hint(chain: str, token: str, pool: str) -> dict[str, Any]:
    if not DB_PATH.exists():
        return {"liquidity_usd": None, "likely_microcap": None, "source": "db_missing"}
    conn = sqlite3.connect(DB_PATH)
    try:
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='token_market_discovery_candidates'"
        ).fetchone()[0]
        if not exists:
            return {"liquidity_usd": None, "likely_microcap": None, "source": "table_missing"}
        result = conn.execute(
            """
            SELECT observed_liquidity
            FROM token_market_discovery_candidates
            WHERE lower(COALESCE(chain, ''))=?
              AND (
                lower(COALESCE(token_contract, ''))=?
                OR lower(COALESCE(pool_or_pair_address, ''))=?
              )
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (chain, token, pool),
        ).fetchone()
    finally:
        conn.close()
    liquidity = _score_diag_float(result[0]) if result and result[0] is not None else None
    return {
        "liquidity_usd": liquidity,
        "likely_microcap": bool(liquidity < 50_000) if liquidity is not None else None,
        "source": "token_market_discovery_candidates.observed_liquidity" if liquidity is not None else "not_available",
    }


def _local_funnel_recommendation(matrix: dict[str, int]) -> dict[str, Any]:
    for threshold in (30, 20, 40, 50, 60):
        count = matrix.get(f"threshold_{threshold}", 0)
        if 10 <= count <= 30:
            return {
                "recommended_threshold": threshold,
                "reason": f"threshold_{threshold} gives {count} candidates, inside the 10-30 target range",
            }
    if matrix.get("threshold_20", 0) < 5:
        return {
            "recommended_threshold": "élargir la source de candidats",
            "reason": "even threshold_20 gives fewer than 5 local behavioral candidates",
        }
    best_threshold = max((20, 30, 40, 50, 60), key=lambda value: matrix.get(f"threshold_{value}", 0))
    return {
        "recommended_threshold": best_threshold,
        "reason": f"no threshold is in the 10-30 range; threshold_{best_threshold} gives the widest local funnel",
    }


@router.get("/rpc/local-behavioral-candidate-funnel-expansion-preview")
@router.post("/rpc/local-behavioral-candidate-funnel-expansion-preview")
async def rpc_local_behavioral_candidate_funnel_expansion_preview(
    chain: str | None = "bsc",
    limit: int = 50,
    min_swaps: int = 1,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if min_swaps > 10_000:
        raise HTTPException(status_code=400, detail="min_swaps_max_10000")
    clean_chain = str(chain or "bsc").strip().lower()
    preview = await asyncio.to_thread(
        get_manipulation_detection_behavioral_score_pump_backtest_preview,
        clean_chain,
        None,
        limit,
        True,
        min_swaps,
        1,
        70,
        400,
        400,
        200,
    )
    rows = [row for row in (preview.get("candidate_backtests") or []) if isinstance(row, dict)]
    if not rows:
        return {
            "ok": True,
            "dry_run": True,
            "preview_status": "local_behavioral_table_empty",
            "source": "computed_local_behavioral_score_pump_backtest_preview",
            "suggestion": "élargir la source de candidats ou collecter plus de raw swap/sync/transfer context locally",
            "matrix": {f"threshold_{threshold}": 0 for threshold in [20, 30, 40, 50, 60]},
            "blockers": preview.get("blockers") or ["no_local_behavioral_candidates"],
            "would_write": False,
            "would_create_label": False,
            "would_create_mapping": False,
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_create_client_opt_in": False,
            "writes_performed": 0,
        }
    matrix = {
        f"threshold_{threshold}": sum(
            1 for row in rows if _score_diag_float(row.get("final_behavioral_score")) >= threshold
        )
        for threshold in [20, 30, 40, 50, 60]
    }
    recommendation = _local_funnel_recommendation(matrix)
    selected_threshold = recommendation.get("recommended_threshold")
    if not isinstance(selected_threshold, int):
        selected_threshold = 20
    eligible = [
        row
        for row in rows
        if _score_diag_float(row.get("final_behavioral_score")) >= selected_threshold
    ]
    eligible.sort(key=lambda row: _score_diag_float(row.get("final_behavioral_score")), reverse=True)
    top_tokens = []
    for row in eligible[:10]:
        token = _score_diag_address(row.get("target_token"))
        pool = _score_diag_address(row.get("pool_address"))
        top_tokens.append({
            "token_address": token or None,
            "token_symbol": row.get("target_symbol"),
            "behavioral_score": row.get("final_behavioral_score"),
            "pool_address": pool or None,
            "first_seen": _local_candidate_first_seen(row),
            **_local_liquidity_hint(clean_chain, token, pool),
        })
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready",
        "source": "computed_local_behavioral_score_pump_backtest_preview",
        "chain": clean_chain,
        "limit": limit,
        "min_swaps": min_swaps,
        "matrix": matrix,
        "recommended_threshold": recommendation,
        "top_10_tokens_at_recommended_threshold": top_tokens,
        "base_preview_status": preview.get("preview_status"),
        "base_blockers": preview.get("blockers") or [],
        "would_call_dexscreener": False,
        "would_call_scrapling": False,
        "would_call_rpc": False,
        "would_write": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "writes_performed": 0,
    }


def _parse_token_addresses(token_addresses: list[str] | None, token_addresses_csv: str | None) -> list[str]:
    raw_values = list(token_addresses or [])
    if token_addresses_csv:
        raw_values.extend(part.strip() for part in token_addresses_csv.split(","))
    clean: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        token = _score_diag_address(value)
        if token and token not in seen:
            seen.add(token)
            clean.append(token)
    return clean[:20]


def _parse_token_inputs(token_addresses: list[str] | None, token_addresses_csv: str | None) -> list[dict[str, Any]]:
    raw_values = list(token_addresses or [])
    if token_addresses_csv:
        raw_values.extend(part.strip() for part in token_addresses_csv.split(","))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in raw_values[:20]:
        token = _score_diag_address(value)
        key = token or str(value or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"input": value, "token_address": token or None, "valid": bool(token)})
    return rows


def _table_exists_readonly(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0])


def _token_local_pools(conn: sqlite3.Connection, chain: str, token: str) -> list[str]:
    if not _table_exists_readonly(conn, "pair_tokens"):
        return []
    rows = conn.execute(
        """
        SELECT lower(pool) AS pool
        FROM pair_tokens
        WHERE lower(chain)=?
          AND (lower(token0)=? OR lower(token1)=?)
        ORDER BY COALESCE(observed_at, 0) DESC
        LIMIT 10
        """,
        (chain, token, token),
    ).fetchall()
    return [_score_diag_address(row["pool"]) for row in rows if _score_diag_address(row["pool"])]


def _legacy_transfer_count(conn: sqlite3.Connection, chain: str, token: str) -> int:
    if not _table_exists_readonly(conn, "token_transfers"):
        return 0
    return int(conn.execute(
        "SELECT COUNT(*) FROM token_transfers WHERE lower(chain)=? AND lower(token)=?",
        (chain, token),
    ).fetchone()[0] or 0)


def _score_token_from_local_raw(conn: sqlite3.Connection, chain: str, token: str) -> dict[str, Any]:
    pools = _token_local_pools(conn, chain, token)
    legacy_transfers = _legacy_transfer_count(conn, chain, token)
    if not pools:
        return {
            "token_address": token,
            "behavioral_score": None,
            "raw_data_status": "raw_data_missing_locally" if legacy_transfers == 0 else "pool_context_missing_locally",
            "recommendation": "trigger_bounded_raw_lookup_first",
            "raw_counts": {"pools": 0, "swap_rows": 0, "sync_rows": 0, "erc20_transfer_rows": 0, "token_transfers_rows": legacy_transfers},
        }
    best: dict[str, Any] | None = None
    total_swaps = 0
    total_syncs = 0
    total_erc20 = 0
    for pool in pools:
        swap_rows = conn.execute(
            """
            SELECT *
            FROM dex_raw_swap_events
            WHERE lower(chain)=? AND lower(pair_address)=?
            ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
            LIMIT 2000
            """,
            (chain, pool),
        ).fetchall() if _table_exists_readonly(conn, "dex_raw_swap_events") else []
        sync_rows = conn.execute(
            """
            SELECT *
            FROM dex_raw_sync_events
            WHERE lower(chain)=? AND lower(pair_address)=?
            ORDER BY block_number ASC, log_index ASC
            LIMIT 2000
            """,
            (chain, pool),
        ).fetchall() if _table_exists_readonly(conn, "dex_raw_sync_events") else []
        transfer_rows = conn.execute(
            """
            SELECT *
            FROM erc20_transfer_events
            WHERE lower(chain)=? AND lower(token_address)=?
            ORDER BY block_number ASC, log_index ASC
            LIMIT 4000
            """,
            (chain, token),
        ).fetchall() if _table_exists_readonly(conn, "erc20_transfer_events") else []
        total_swaps += len(swap_rows)
        total_syncs += len(sync_rows)
        total_erc20 = max(total_erc20, len(transfer_rows))
        if not swap_rows and not sync_rows and not transfer_rows:
            continue
        score = score_raw_context_candidate(conn, chain, pool, swap_rows, sync_rows, transfer_rows)
        if best is None or _score_diag_float(score.get("behavioral_anomaly_score")) > _score_diag_float(best.get("behavioral_anomaly_score")):
            best = score
    if best is None:
        return {
            "token_address": token,
            "behavioral_score": None,
            "raw_data_status": "raw_data_missing_locally",
            "recommendation": "trigger_bounded_raw_lookup_first",
            "raw_counts": {"pools": len(pools), "swap_rows": total_swaps, "sync_rows": total_syncs, "erc20_transfer_rows": total_erc20, "token_transfers_rows": legacy_transfers},
        }
    return {
        "token_address": token,
        "behavioral_score": best.get("behavioral_anomaly_score"),
        "behavioral_tier": best.get("behavioral_anomaly_tier"),
        "pool_address": best.get("pool_address"),
        "raw_data_status": "raw_data_present_locally",
        "recommendation": best.get("next_safe_step") or "review_behavioral_score_before_any_action",
        "score_factors": best.get("score_factors"),
        "raw_counts": {
            **(best.get("raw_context_counts") or {}),
            "candidate_pools": len(pools),
            "token_transfers_rows": legacy_transfers,
        },
        "blockers": best.get("blockers") or [],
    }


def get_on_demand_behavioral_scoring_preview(
    chain: str | None = "bsc",
    token_addresses: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "preview_status": "blocked",
            "blockers": ["dry_run_required"],
            "scoring_rows": [],
            "would_write": False,
            "writes_performed": 0,
        }
    clean_chain = str(chain or "bsc").strip().lower()
    tokens = [_score_diag_address(token) for token in (token_addresses or [])]
    tokens = [token for token in tokens if token][:20]
    if not tokens:
        return {
            "ok": True,
            "dry_run": True,
            "preview_status": "blocked",
            "blockers": ["token_addresses_required"],
            "scoring_rows": [],
            "would_call_rpc": False,
            "would_call_sqd": False,
            "would_backfill": False,
            "would_write": False,
            "writes_performed": 0,
        }
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = [_score_token_from_local_raw(conn, clean_chain, token) for token in tokens]
    finally:
        conn.close()
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready",
        "chain": clean_chain,
        "tokens_requested": len(tokens),
        "tokens_scored": sum(1 for row in rows if row.get("behavioral_score") is not None),
        "tokens_missing_raw_data": sum(1 for row in rows if row.get("raw_data_status") != "raw_data_present_locally"),
        "scoring_rows": rows,
        "would_call_rpc": False,
        "would_call_sqd": False,
        "would_backfill": False,
        "would_call_dexscreener": False,
        "would_call_scrapling": False,
        "would_write": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "writes_performed": 0,
    }


@router.get("/rpc/on-demand-behavioral-scoring-preview")
@router.post("/rpc/on-demand-behavioral-scoring-preview")
async def rpc_on_demand_behavioral_scoring_preview(
    token_addresses: list[str] | None = Body(default=None),
    token_addresses_csv: str | None = None,
    chain: str | None = "bsc",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    clean_chain = str(chain or "bsc").strip().lower()
    tokens = _parse_token_addresses(token_addresses, token_addresses_csv)
    return await asyncio.to_thread(get_on_demand_behavioral_scoring_preview, clean_chain, tokens, dry_run)


def _bounded_lookup_plan_preview(chain: str, token: str) -> tuple[dict[str, Any] | None, str | None]:
    planner = globals().get("get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan")
    if not callable(planner):
        return None, "planner_function_missing"
    try:
        plan = planner(chain, [token], True, 50_000, 250_000)
    except Exception as exc:  # Preview must stay non-blocking for a bad token.
        return None, f"planner_error:{type(exc).__name__}"
    token_plan = (plan.get("tokens") or [{}])[0] if isinstance(plan, dict) else {}
    return {
        "planner": "get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan",
        "plan_status": plan.get("plan_status"),
        "plan_readiness": token_plan.get("plan_readiness"),
        "current_local_context": token_plan.get("current_local_context"),
        "pool_context": token_plan.get("pool_context"),
        "planned_filters": token_plan.get("planned_filters"),
        "blockers": token_plan.get("blockers") or plan.get("blockers") or [],
        "next_safe_step": token_plan.get("next_safe_step") or plan.get("next_safe_step"),
        "bounds": {
            "block_padding": plan.get("block_padding"),
            "max_window_blocks": plan.get("max_window_blocks"),
        },
        "would_call_rpc": plan.get("would_call_rpc", False),
        "would_call_sqd": plan.get("would_call_sqd", False),
        "would_write": plan.get("would_write", False),
        "writes_performed": plan.get("writes_performed", 0),
    }, None


@router.get("/rpc/behavioral-funnel-intake-and-backfill-plan-preview")
@router.post("/rpc/behavioral-funnel-intake-and-backfill-plan-preview")
async def rpc_behavioral_funnel_intake_and_backfill_plan_preview(
    token_addresses: list[str] | None = Body(default=None),
    token_addresses_csv: str | None = None,
    chain: str | None = "bsc",
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    clean_chain = str(chain or "bsc").strip().lower()
    inputs = _parse_token_inputs(token_addresses, token_addresses_csv)
    valid_tokens = [row["token_address"] for row in inputs if row.get("valid") and row.get("token_address")]
    scoring = await asyncio.to_thread(get_on_demand_behavioral_scoring_preview, clean_chain, valid_tokens, True)
    by_token = {
        str(row.get("token_address")).lower(): row
        for row in (scoring.get("scoring_rows") or [])
        if isinstance(row, dict) and row.get("token_address")
    }
    rows: list[dict[str, Any]] = []
    for item in inputs:
        token = item.get("token_address")
        if not item.get("valid") or not token:
            rows.append({
                "token_address": None,
                "input": item.get("input"),
                "behavioral_score": None,
                "raw_status": "invalid_token_address",
                "lookup_plan_preview": None,
                "error": "invalid_token_address",
                "next_action": "provide_valid_bsc_token_address",
            })
            continue
        score_row = by_token.get(str(token).lower()) or {}
        score = score_row.get("behavioral_score")
        if score is not None:
            rows.append({
                "token_address": token,
                "behavioral_score": score,
                "raw_status": "ready",
                "raw_data_status": score_row.get("raw_data_status"),
                "behavioral_tier": score_row.get("behavioral_tier"),
                "pool_address": score_row.get("pool_address"),
                "lookup_plan_preview": None,
                "next_action": "enrich_with_dexscreener",
            })
            continue
        plan_preview, error = _bounded_lookup_plan_preview(clean_chain, str(token))
        rows.append({
            "token_address": token,
            "behavioral_score": None,
            "raw_status": "missing_locally",
            "raw_data_status": score_row.get("raw_data_status") or "raw_data_missing_locally",
            "lookup_plan_preview": plan_preview,
            "error": error,
            "next_action": "confirm_bounded_lookup_first" if plan_preview else "repair_or_add_lookup_planner_first",
        })
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready" if rows else "blocked",
        "chain": clean_chain,
        "tokens_requested": len(inputs),
        "tokens_ready_for_composite_scoring": sum(1 for row in rows if row.get("raw_status") == "ready"),
        "tokens_requiring_lookup_plan": sum(1 for row in rows if row.get("raw_status") == "missing_locally"),
        "tokens_invalid": sum(1 for row in rows if row.get("raw_status") == "invalid_token_address"),
        "intake_rows": rows,
        "blockers": [] if rows else ["token_addresses_required"],
        "would_call_rpc": False,
        "would_call_sqd": False,
        "would_backfill": False,
        "would_scrape": False,
        "would_write": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "writes_performed": 0,
    }


BOUNDED_RAW_CONTEXT_COLLECTION_CONFIRM = "CONFIRM_BOUNDED_RAW_CONTEXT_COLLECTION"


def _bounded_raw_plan_digest(plan: dict[str, Any], bounds: dict[str, Any]) -> str:
    payload = {
        "planner": "get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan",
        "bounds": bounds,
        "plan_status": plan.get("plan_status"),
        "tokens": plan.get("tokens") or [],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _raw_context_dedupe_snapshot(chain: str, token: str, pool: str) -> set[str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        keys: set[str] = set()
        queries = [
            ("dex_raw_swap_events", "pair_address", pool),
            ("dex_raw_sync_events", "pair_address", pool),
            ("erc20_transfer_events", "token_address", token),
        ]
        for table_name, column_name, value in queries:
            if not _table_exists_readonly(conn, table_name):
                continue
            try:
                rows = conn.execute(
                    f"SELECT event_dedupe_key FROM {table_name} "
                    f"WHERE lower(chain)=? AND lower({column_name})=? AND event_dedupe_key IS NOT NULL",
                    (chain, value),
                ).fetchall()
            except sqlite3.Error:
                continue
            keys.update(str(row[0]) for row in rows if row and row[0])
        return keys
    finally:
        conn.close()


def _ready_raw_context_plan_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for token_plan in plan.get("tokens") or []:
        token = _score_diag_address(token_plan.get("token_address"))
        filters = token_plan.get("planned_filters") or {}
        swap_filter = filters.get("swap_logs") or {}
        transfer_filter = filters.get("transfer_logs") or {}
        pair_addresses = [
            _score_diag_address(pair)
            for pair in (swap_filter.get("pair_addresses") or [])
            if _score_diag_address(pair)
        ]
        from_block = swap_filter.get("from_block") or transfer_filter.get("from_block")
        to_block = swap_filter.get("to_block") or transfer_filter.get("to_block")
        ready = (
            token_plan.get("plan_readiness") == "ready_for_bounded_raw_lookup_dry_run"
            and bool(token)
            and bool(pair_addresses)
            and from_block is not None
            and to_block is not None
        )
        rows.append({
            "token_address": token,
            "pool_address": pair_addresses[0] if pair_addresses else None,
            "plan_readiness": token_plan.get("plan_readiness"),
            "ready_for_collection": ready,
            "from_block": from_block,
            "to_block": to_block,
            "blockers": token_plan.get("blockers") or ([] if ready else ["bounded_lookup_plan_not_ready"]),
        })
    return rows


@router.get("/rpc/confirm-bounded-raw-context-collection")
@router.post("/rpc/confirm-bounded-raw-context-collection")
async def rpc_confirm_bounded_raw_context_collection(
    token_addresses: list[str] | None = Body(default=None),
    raw_context_lookup_digests: dict[str, str] | None = Body(default=None),
    token_addresses_csv: str | None = None,
    chain: str | None = "bsc",
    plan_digest: str | None = None,
    expected_raw_context_lookup_digest: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    block_padding: int = 50_000,
    max_window_blocks: int = 250_000,
    max_sqd_calls: int = 9,
    max_sqd_block_span: int = 25_000,
    max_logs_total: int = 180,
    max_logs_per_filter: int = 20,
    timeout: int = 8,
    _: None = Depends(_require_data_admin),
):
    if block_padding > 500_000:
        raise HTTPException(status_code=400, detail="block_padding_max_500000")
    if max_window_blocks > 2_000_000:
        raise HTTPException(status_code=400, detail="max_window_blocks_max_2000000")
    if max_sqd_calls > 60:
        raise HTTPException(status_code=400, detail="max_sqd_calls_max_60")
    if max_sqd_block_span > 50_000:
        raise HTTPException(status_code=400, detail="max_sqd_block_span_max_50000")
    if max_logs_total > 5000:
        raise HTTPException(status_code=400, detail="max_logs_total_max_5000")
    if max_logs_per_filter > 1000:
        raise HTTPException(status_code=400, detail="max_logs_per_filter_max_1000")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")

    clean_chain = str(chain or "bsc").strip().lower()
    inputs = _parse_token_inputs(token_addresses, token_addresses_csv)
    tokens = [row["token_address"] for row in inputs if row.get("valid") and row.get("token_address")]
    blockers: list[str] = []
    if not tokens:
        blockers.append("token_addresses_required_to_replay_bounded_plan")
    invalid_inputs = [row for row in inputs if not row.get("valid")]
    plan = await asyncio.to_thread(
        get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan,
        clean_chain,
        tokens,
        True,
        block_padding,
        max_window_blocks,
    ) if tokens else {"tokens": [], "plan_status": "blocked"}
    bounds = {
        "block_padding": block_padding,
        "max_window_blocks": max_window_blocks,
        "max_sqd_calls": max_sqd_calls,
        "max_sqd_block_span": max_sqd_block_span,
        "max_logs_total": max_logs_total,
        "max_logs_per_filter": max_logs_per_filter,
    }
    computed_plan_digest = _bounded_raw_plan_digest(plan, bounds)
    if plan_digest and str(plan_digest).strip() != computed_plan_digest:
        blockers.append("plan_digest_mismatch")
    plan_rows = _ready_raw_context_plan_rows(plan)
    ready_rows = [row for row in plan_rows if row.get("ready_for_collection")]
    if not ready_rows:
        blockers.append("no_tokens_ready_for_bounded_raw_collection")
    if dry_run or confirm != BOUNDED_RAW_CONTEXT_COLLECTION_CONFIRM:
        blockers.append("confirm_CONFIRM_BOUNDED_RAW_CONTEXT_COLLECTION_required")
        return {
            "ok": True,
            "dry_run": bool(dry_run),
            "status": "blocked",
            "chain": clean_chain,
            "plan_digest": computed_plan_digest,
            "provided_plan_digest": plan_digest,
            "bounds_verified": not any(blocker == "plan_digest_mismatch" for blocker in blockers),
            "invalid_inputs": invalid_inputs,
            "plan_rows": plan_rows,
            "blockers": list(dict.fromkeys(blockers)),
            "tokens_processed": 0,
            "logs_collected": 0,
            "rows_inserted": 0,
            "dedupe_keys_used": [],
            "next_action": "confirm_bounded_collection_with_raw_lookup_digest",
            "would_call_sqd": False,
            "would_call_rpc": False,
            "would_write": False,
            "writes_performed": 0,
            "would_create_label": False,
            "would_create_mapping": False,
            "would_create_client_signal": False,
            "would_execute_trade": False,
        }
    if blockers:
        return {
            "ok": False,
            "dry_run": False,
            "status": "blocked",
            "chain": clean_chain,
            "plan_digest": computed_plan_digest,
            "provided_plan_digest": plan_digest,
            "bounds_verified": False,
            "invalid_inputs": invalid_inputs,
            "plan_rows": plan_rows,
            "blockers": list(dict.fromkeys(blockers)),
            "tokens_processed": 0,
            "logs_collected": 0,
            "rows_inserted": 0,
            "dedupe_keys_used": [],
            "next_action": "repair_or_regenerate_lookup_plan_preview",
            "would_write": False,
            "writes_performed": 0,
        }

    results: list[dict[str, Any]] = []
    totals = {"tokens_processed": 0, "logs_collected": 0, "rows_inserted": 0}
    dedupe_keys_used: list[str] = []
    digest_map = {str(k).lower(): str(v) for k, v in (raw_context_lookup_digests or {}).items()}
    for row in ready_rows:
        token = str(row.get("token_address") or "").lower()
        pool = str(row.get("pool_address") or "").lower()
        expected_digest = digest_map.get(token) or (expected_raw_context_lookup_digest if len(ready_rows) == 1 else None)
        if not expected_digest:
            results.append({**row, "collection_status": "blocked", "blockers": ["expected_raw_context_lookup_digest_required"]})
            continue
        before_keys = _raw_context_dedupe_snapshot(clean_chain, token, pool)
        try:
            result = await asyncio.to_thread(
                insert_manipulation_detection_b_seed_raw_context_evidence,
                clean_chain,
                token,
                pool,
                False,
                True,
                "INSERT_B_SEED_RAW_CONTEXT_EVIDENCE",
                expected_digest,
                block_padding,
                max_window_blocks,
                max_sqd_calls,
                max_sqd_block_span,
                max_logs_total,
                max_logs_per_filter,
                timeout,
            )
        except Exception as exc:
            results.append({**row, "collection_status": "error", "error": type(exc).__name__, "blockers": ["sqd_or_insert_error"]})
            continue
        after_keys = _raw_context_dedupe_snapshot(clean_chain, token, pool)
        inserted_keys = sorted(after_keys - before_keys)
        dedupe_keys_used.extend(inserted_keys)
        totals["tokens_processed"] += 1
        totals["logs_collected"] += int(result.get("total_logs_seen") or 0)
        totals["rows_inserted"] += int(result.get("rows_inserted") or 0)
        results.append({
            **row,
            "collection_status": result.get("insert_status"),
            "logs_collected": result.get("total_logs_seen"),
            "rows_inserted": result.get("rows_inserted"),
            "dedupe_keys_used": inserted_keys[:50],
            "blockers": result.get("blockers") or [],
            "raw_context_lookup_digest": result.get("raw_context_lookup_digest"),
        })
    return {
        "ok": True,
        "dry_run": False,
        "status": "completed",
        "chain": clean_chain,
        "plan_digest": computed_plan_digest,
        "bounds_verified": True,
        "tokens_processed": totals["tokens_processed"],
        "logs_collected": totals["logs_collected"],
        "rows_inserted": totals["rows_inserted"],
        "dedupe_keys_used": dedupe_keys_used[:100],
        "token_results": results,
        "next_action": "re-run-on-demand-scoring",
        "would_write": False,
        "writes_performed": totals["rows_inserted"],
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
    }


@router.post("/rpc/aster-source-wallet-token-flow-collection")
async def rpc_aster_source_wallet_token_flow_collection(
    chain: str | None = "bsc",
    source_wallet: str | None = None,
    tx_hash: str | None = None,
    lookback_blocks: int = 1000,
    forward_blocks: int = 1000,
    page_size_blocks: int = 1000,
    max_tokens_per_chain: int = 25,
    max_logs_per_direction: int = 100,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if lookback_blocks > 25000:
        raise HTTPException(status_code=400, detail="lookback_blocks_max_25000")
    if forward_blocks > 25000:
        raise HTTPException(status_code=400, detail="forward_blocks_max_25000")
    if page_size_blocks > 5000:
        raise HTTPException(status_code=400, detail="page_size_blocks_max_5000")
    if max_tokens_per_chain > 100:
        raise HTTPException(status_code=400, detail="max_tokens_per_chain_max_100")
    if max_logs_per_direction > 500:
        raise HTTPException(status_code=400, detail="max_logs_per_direction_max_500")
    return await asyncio.to_thread(
        run_aster_source_wallet_token_flow_collection,
        chain,
        source_wallet,
        tx_hash,
        lookback_blocks,
        forward_blocks,
        page_size_blocks,
        max_tokens_per_chain,
        max_logs_per_direction,
        dry_run,
        confirm,
    )


@router.post("/rpc/unknown-swap-attribution/enrich")
async def rpc_unknown_swap_attribution_enrich(
    chain: str | None = None,
    limit: int = 20,
    include_tokens: bool = False,
    dry_run: bool = True,
    confirm: str | None = None,
    refresh_after_hours: int = 12,
    force_refresh: bool = False,
    _: None = Depends(_require_data_admin),
):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(
        enrich_unknown_swap_attribution_targets,
        chain,
        limit,
        include_tokens,
        dry_run,
        confirm,
        refresh_after_hours,
        force_refresh,
    )


@router.get("/rpc/swap-router-code-fingerprints")
async def rpc_swap_router_code_fingerprints(chain: str | None = None, limit: int = 20):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    return await asyncio.to_thread(get_unknown_swap_router_code_fingerprints, chain, limit)


@router.get("/rpc/swap-router-family-investigation")
async def rpc_swap_router_family_investigation(chain: str | None = None, limit: int = 20, timeout: int = 6):
    if limit > 50:
        raise HTTPException(status_code=400, detail="limit_max_50")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(get_unknown_swap_router_family_investigation, chain, limit, timeout)


@router.get("/rpc/swap-venue-public-evidence")
async def rpc_swap_venue_public_evidence(chain: str, router_addr: str, timeout: int = 8):
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(get_swap_venue_public_evidence, chain, router_addr, timeout)


@router.get("/rpc/swap-venue-public-evidence-scan")
async def rpc_swap_venue_public_evidence_scan(chain: str | None = None, limit: int = 5, timeout: int = 6):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(scan_swap_venue_public_evidence, chain, limit, timeout)


@router.get("/rpc/swap-venue-mapping-drafts")
async def rpc_swap_venue_mapping_drafts(chain: str | None = None, limit: int = 5, timeout: int = 6):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(get_swap_venue_mapping_drafts, chain, limit, timeout)


@router.get("/rpc/swap-venue-official-source-corroboration")
async def rpc_swap_venue_official_source_corroboration(chain: str | None = None, limit: int = 5, timeout: int = 6):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(corroborate_swap_venue_official_sources, chain, limit, timeout)


@router.get("/rpc/source-backed-venue-mapping/admin-review-queue")
async def rpc_source_backed_venue_mapping_admin_review_queue(
    chain: str | None = None,
    limit: int = 5,
    timeout: int = 6,
    include_counterparty_source_search: bool = True,
    _: None = Depends(_require_data_admin),
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    return await asyncio.to_thread(
        get_source_backed_venue_mapping_admin_review_queue,
        chain,
        limit,
        timeout,
        include_counterparty_source_search,
    )


@router.get("/rpc/source-backed-venue-mappings")
async def rpc_source_backed_venue_mappings(chain: str | None = None, limit: int = 50):
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(get_source_backed_venue_mappings, chain, limit)


@router.get("/rpc/source-backed-venue-mapping/preview")
async def rpc_source_backed_venue_mapping_preview(
    chain: str,
    router_addr: str,
    venue: str,
    source_url: str,
    confidence: float = 0.85,
):
    return await asyncio.to_thread(
        preview_source_backed_venue_mapping,
        chain,
        router_addr,
        venue,
        source_url,
        confidence,
    )


@router.post("/rpc/source-backed-venue-mapping")
async def rpc_source_backed_venue_mapping(
    chain: str,
    router_addr: str,
    venue: str,
    source_url: str,
    confidence: float = 0.85,
    dry_run: bool = True,
    confirm: str | None = None,
    evidence: dict[str, Any] | None = Body(default=None),
    _: None = Depends(_require_data_admin),
):
    return await asyncio.to_thread(
        upsert_source_backed_venue_mapping,
        chain,
        router_addr,
        venue,
        source_url,
        evidence,
        confidence,
        dry_run,
        confirm,
    )


@router.post("/rpc/source-backed-venue-mapping/confirm-guided-review")
async def rpc_confirm_guided_venue_review(
    candidate_id: str,
    dry_run: bool = True,
    confirm: str | None = None,
    limit: int = 10,
    timeout: int = 6,
    _: None = Depends(_require_data_admin),
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if not dry_run and confirm != "UPSERT_SOURCE_BACKED_VENUE_MAPPING":
        raise HTTPException(status_code=400, detail="confirm_UPSERT_SOURCE_BACKED_VENUE_MAPPING_required")
    return await asyncio.to_thread(
        confirm_guided_venue_review,
        candidate_id,
        dry_run,
        confirm,
        limit,
        timeout,
    )


@router.post("/rpc/source-backed-venue-mapping/confirm-guided-reviews")
async def rpc_confirm_guided_venue_reviews(
    candidate_ids: str | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    limit: int = 5,
    timeout: int = 6,
    _: None = Depends(_require_data_admin),
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if not dry_run and limit > 5:
        raise HTTPException(status_code=400, detail="real_write_limit_max_5")
    if timeout > 15:
        raise HTTPException(status_code=400, detail="timeout_max_15")
    if not dry_run and confirm != "UPSERT_SOURCE_BACKED_VENUE_MAPPING":
        raise HTTPException(status_code=400, detail="confirm_UPSERT_SOURCE_BACKED_VENUE_MAPPING_required")
    ids = [item.strip() for item in str(candidate_ids or "").split(",") if item.strip()]
    return await asyncio.to_thread(
        confirm_guided_venue_reviews_batch,
        ids or None,
        dry_run,
        confirm,
        limit,
        timeout,
    )


@router.get("/rpc/exact-swap-ingestion-plan")
async def rpc_exact_swap_ingestion_plan(max_chains: int = 5):
    if max_chains > 5:
        raise HTTPException(status_code=400, detail="max_chains_max_5")
    return await asyncio.to_thread(get_exact_swap_ingestion_plan, max_chains)


@router.post("/rpc/bounded-exact-swap-transfer-collection")
async def rpc_bounded_exact_swap_transfer_collection(
    max_chains: int = 1,
    count_per_chain: int = 1,
    confirmations: int = 12,
    dry_run: bool = True,
    confirm: str | None = None,
    max_receipts_per_block: int | None = None,
    max_seconds_per_block: float | None = None,
    _: None = Depends(_require_data_admin),
):
    if max_chains > 3:
        raise HTTPException(status_code=400, detail="max_chains_max_3")
    if count_per_chain > 3:
        raise HTTPException(status_code=400, detail="count_per_chain_max_3")
    if confirmations > 50:
        raise HTTPException(status_code=400, detail="confirmations_max_50")
    if max_receipts_per_block is not None and max_receipts_per_block > 200:
        raise HTTPException(status_code=400, detail="max_receipts_per_block_max_200")
    if max_seconds_per_block is not None and max_seconds_per_block > 120:
        raise HTTPException(status_code=400, detail="max_seconds_per_block_max_120")
    return await asyncio.to_thread(
        run_bounded_exact_swap_transfer_collection,
        max_chains,
        count_per_chain,
        confirmations,
        dry_run,
        confirm,
        max_receipts_per_block,
        max_seconds_per_block,
    )


@router.get("/rpc/token-metadata-enrichment-plan")
@router.post("/rpc/token-metadata-enrichment-plan")
async def rpc_token_metadata_enrichment_plan(
    limit: int = 25,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit_max_100")
    return await asyncio.to_thread(get_token_metadata_enrichment_plan, limit, dry_run)


@router.post("/rpc/token-metadata-enrichment")
async def rpc_token_metadata_enrichment(
    limit: int = 5,
    dry_run: bool = True,
    confirm: str | None = None,
    max_seconds: int = 45,
    _: None = Depends(_require_data_admin),
):
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if max_seconds > 180:
        raise HTTPException(status_code=400, detail="max_seconds_max_180")
    return await asyncio.to_thread(
        enrich_token_metadata_from_local_observations,
        limit,
        dry_run,
        confirm,
        max_seconds,
    )


@router.get("/rpc/token-market-local-candidate-metadata-repair-plan")
@router.post("/rpc/token-market-local-candidate-metadata-repair-plan")
async def rpc_token_market_local_candidate_metadata_repair_plan(
    limit: int = 5,
    dry_run: bool = True,
    _: None = Depends(_require_data_admin),
):
    if not dry_run:
        raise HTTPException(status_code=400, detail="dry_run_required")
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    return await asyncio.to_thread(get_token_market_local_candidate_metadata_repair_plan, limit, dry_run)


@router.post("/rpc/token-market-local-candidate-metadata-repair")
async def rpc_token_market_local_candidate_metadata_repair(
    limit: int = 5,
    dry_run: bool = True,
    confirm: str | None = None,
    max_seconds: int = 45,
    _: None = Depends(_require_data_admin),
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if max_seconds > 180:
        raise HTTPException(status_code=400, detail="max_seconds_max_180")
    return await asyncio.to_thread(
        enrich_token_metadata_for_local_candidate_repair,
        limit,
        dry_run,
        confirm,
        max_seconds,
    )


@router.get("/rpc/data-jobs")
async def rpc_data_jobs(limit: int = 20, job_type: str | None = None):
    return await asyncio.to_thread(get_data_jobs, limit, job_type)


@router.get("/rpc/auto-enrich/status")
async def rpc_auto_enrich_status():
    return get_auto_enrich_status()


@router.post("/rpc/enrich-labels")
async def enrich_labelled_wallets_rpc(
    chain: str | None = None,
    limit: int = 25,
    entity: str | None = None,
    include_tokens: bool = True,
    min_confidence: str = "high",
    missing_only: bool = False,
    refresh_missing_attribution: bool = False,
    refresh_stale_hours: int | None = None,
    refresh_quality_below: int | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit > 200:
        raise HTTPException(status_code=400, detail="limit_max_200")
    return await asyncio.to_thread(
        enrich_labeled_wallets_rpc,
        chain,
        limit,
        entity,
        include_tokens,
        min_confidence,
        missing_only,
        refresh_missing_attribution,
        refresh_stale_hours,
        refresh_quality_below,
    )


@router.post("/rpc/refresh-wallet-state-audit-targets")
async def refresh_wallet_state_audit_targets_rpc(
    limit_per_target: int = 5,
    max_targets: int = 5,
    include_tokens: bool = False,
    min_confidence: str = "medium",
    stale_after_hours: int = 24,
    quality_below: int = 50,
    entity: str | None = None,
    chain: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if limit_per_target > 50 or max_targets > 20:
        raise HTTPException(status_code=400, detail="limit_per_target_max_50_max_targets_max_20")
    return await asyncio.to_thread(
        refresh_rpc_wallet_state_audit_targets,
        limit_per_target,
        max_targets,
        include_tokens,
        min_confidence,
        stale_after_hours,
        quality_below,
        entity,
        chain,
    )


@router.post("/rpc/enrich-priority")
async def enrich_priority_rpc(
    limit_per_entity: int = 15,
    max_entities: int = 6,
    include_tokens: bool = True,
    min_confidence: str = "medium",
    _: None = Depends(_require_data_admin),
):
    if limit_per_entity > 50 or max_entities > 20:
        raise HTTPException(status_code=400, detail="limit_per_entity_max_50_max_entities_max_20")
    return await asyncio.to_thread(
        enrich_priority_entities_rpc,
        limit_per_entity,
        max_entities,
        min_confidence,
        include_tokens,
    )


@router.post("/rpc/enrich-chain-gaps")
async def enrich_priority_chain_gaps_rpc(
    limit_per_pair: int = 8,
    max_pairs: int = 8,
    include_tokens: bool = True,
    min_confidence: str = "medium",
    _: None = Depends(_require_data_admin),
):
    if limit_per_pair > 50 or max_pairs > 30:
        raise HTTPException(status_code=400, detail="limit_per_pair_max_50_max_pairs_max_30")
    return await asyncio.to_thread(
        enrich_priority_entity_chain_gaps_rpc,
        limit_per_pair,
        max_pairs,
        min_confidence,
        include_tokens,
    )


@router.post("/rpc/auto-enrich/start")
async def start_priority_auto_enrich(
    interval_seconds: int | None = None,
    limit_per_entity: int | None = None,
    max_entities: int | None = None,
    include_tokens: bool | None = None,
    min_confidence: str | None = None,
    mode: str | None = None,
    _: None = Depends(_require_data_admin),
):
    return await asyncio.to_thread(
        start_auto_enrich_priority,
        interval_seconds,
        limit_per_entity,
        max_entities,
        min_confidence,
        include_tokens,
        mode,
    )


@router.post("/rpc/auto-enrich/stop")
async def stop_priority_auto_enrich(_: None = Depends(_require_data_admin)):
    return await asyncio.to_thread(stop_auto_enrich_priority)


@router.get("/labels/ledger")
async def label_ledger_status():
    return await asyncio.to_thread(get_label_ledger_summary)


@router.get("/labels/candidates")
async def label_candidates(limit: int = 50, entity: str | None = None, chain: str | None = None):
    return await asyncio.to_thread(get_label_candidates, limit, entity, chain)


@router.get("/labels/candidates/audit")
async def label_candidates_audit():
    return await asyncio.to_thread(get_label_candidate_audit)


@router.get("/labels/candidates/quality-report")
async def label_candidates_quality_report(limit: int = 50):
    return await asyncio.to_thread(get_label_candidate_quality_report, limit)


@router.get("/labels/candidates/review-dashboard")
async def label_candidates_review_dashboard(limit: int = 25):
    return await asyncio.to_thread(get_label_candidate_review_dashboard, limit)


@router.get("/labels/candidates/promotion-impact")
async def label_candidates_promotion_impact(candidate_ids: str, min_score: int = 90):
    clean_ids = []
    for item in str(candidate_ids or "").replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            clean_ids.append(int(item))
        except ValueError:
            raise HTTPException(status_code=400, detail="candidate_ids_must_be_comma_separated_integers")
    if len(clean_ids) > 50:
        raise HTTPException(status_code=400, detail="candidate_ids_limit_50")
    return await asyncio.to_thread(preview_label_candidate_promotion_impact, clean_ids, min_score)


@router.post("/labels/candidates/consolidate-duplicates")
async def label_candidates_consolidate_duplicates(
    limit: int = 50,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if not dry_run and confirm != "MERGE_EXACT_DUPLICATES":
        raise HTTPException(status_code=400, detail="confirm_MERGE_EXACT_DUPLICATES_required")
    if not dry_run and limit > 25:
        raise HTTPException(status_code=400, detail="real_merge_limit_max_25")
    return await asyncio.to_thread(consolidate_label_candidate_duplicates_job, limit, dry_run)


@router.get("/labels/candidates/promotion-review")
async def label_candidates_promotion_review(limit: int = 25, min_score: int = 70):
    return await asyncio.to_thread(review_label_candidate_promotions, limit, min_score)


@router.get("/labels/candidates/strict-promotion-review")
async def label_candidates_strict_promotion_review(limit: int = 50):
    return await asyncio.to_thread(review_strict_label_candidate_promotions, limit)


@router.get("/labels/candidates/automation-plan")
async def label_candidates_automation_plan(limit: int = 100):
    return await asyncio.to_thread(plan_label_candidate_automation, limit)


@router.get("/labels/candidates/corroborate")
async def label_candidates_corroborate(
    limit: int = 25,
    entity: str | None = None,
    chain: str | None = None,
    timeout: int = 12,
):
    return await asyncio.to_thread(corroborate_label_candidates, limit, entity, chain, timeout, False)


@router.post("/labels/candidates/corroborate")
async def label_candidates_corroborate_persist(
    limit: int = 25,
    entity: str | None = None,
    chain: str | None = None,
    timeout: int = 12,
    _: None = Depends(_require_data_admin),
):
    return await asyncio.to_thread(corroborate_label_candidates, limit, entity, chain, timeout, True)


@router.post("/labels/candidates/corroborate-job")
async def label_candidates_corroborate_job(
    limit: int = 5,
    entity: str | None = None,
    chain: str | None = None,
    timeout: int = 12,
    include_manual_review: bool = False,
    _: None = Depends(_require_data_admin),
):
    if limit > 25:
        raise HTTPException(status_code=400, detail="limit_max_25")
    if timeout > 20:
        raise HTTPException(status_code=400, detail="timeout_max_20")
    return await asyncio.to_thread(
        corroborate_label_candidates_job,
        limit,
        entity,
        chain,
        timeout,
        include_manual_review,
    )


@router.get("/labels/candidates/evidence")
async def label_candidates_evidence(candidate_id: int | None = None, limit: int = 50):
    return await asyncio.to_thread(get_label_candidate_evidence, candidate_id, limit)


@router.get("/labels/candidates/evidence-scores")
async def label_candidates_evidence_scores(
    limit: int = 50,
    entity: str | None = None,
    chain: str | None = None,
    max_bundles_per_candidate: int = 10,
):
    return await asyncio.to_thread(
        get_label_candidate_evidence_scores,
        limit,
        entity,
        chain,
        max_bundles_per_candidate,
    )


@router.get("/labels/candidates/verified-review-queue")
async def label_candidates_verified_review_queue(
    limit: int = 50,
    entity: str | None = None,
    chain: str | None = None,
    max_bundles_per_candidate: int = 10,
):
    return await asyncio.to_thread(
        get_verified_label_candidate_review_queue,
        limit,
        entity,
        chain,
        max_bundles_per_candidate,
    )


@router.get("/labels/candidates/corroboration-queue")
async def label_candidates_corroboration_queue(
    limit: int = 50,
    entity: str | None = None,
    chain: str | None = None,
    include_manual_review: bool = False,
):
    return await asyncio.to_thread(get_label_corroboration_queue, limit, entity, chain, include_manual_review)


@router.get("/labels/acquisition-plan")
async def label_acquisition_plan(limit: int = 50, min_trusted_per_entity: int = 100):
    return await asyncio.to_thread(get_label_acquisition_plan, limit, min_trusted_per_entity)


@router.post("/labels/acquire-sources")
async def label_acquire_sources(
    limit: int = 3,
    min_trusted_per_entity: int = 100,
    timeout_ms: int = 30000,
    max_xhr: int = 60,
    _: None = Depends(_require_data_admin),
):
    if limit > 10:
        raise HTTPException(status_code=400, detail="limit_max_10")
    if timeout_ms > 60000 or max_xhr > 100:
        raise HTTPException(status_code=400, detail="timeout_max_60000_max_xhr_100")
    return await asyncio.to_thread(
        acquire_label_sources_job,
        limit,
        min_trusted_per_entity,
        timeout_ms,
        max_xhr,
    )


@router.post("/labels/candidates/promote")
async def label_candidates_promote(
    candidate_ids: str,
    min_score: int = 90,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    ids = [int(part.strip()) for part in candidate_ids.split(",") if part.strip().isdigit()]
    if len(ids) > 50:
        raise HTTPException(status_code=400, detail="candidate_ids_max_50")
    if not dry_run and confirm != "PROMOTE_TRUSTED_LABELS":
        raise HTTPException(status_code=400, detail="confirm_PROMOTE_TRUSTED_LABELS_required")
    if not dry_run and len(ids) > 10:
        raise HTTPException(status_code=400, detail="real_promote_candidate_ids_max_10")
    return await asyncio.to_thread(promote_label_candidates, ids, min_score, dry_run, confirm)


@router.post("/labels/build")
async def build_labels(limit_files: int | None = None, _: None = Depends(_require_data_admin)):
    return await asyncio.to_thread(build_label_ledger_job, limit_files)


@router.post("/labels/expand")
async def expand_labels(
    chain: str | None = None,
    min_evidence: int = 2,
    limit: int = 5000,
    _: None = Depends(_require_data_admin),
):
    return await asyncio.to_thread(expand_label_graph, chain, min_evidence, limit)


@router.post("/labels/ingest-seeds")
async def ingest_label_seeds(
    chain: str | None = None,
    seed_limit: int = 10,
    tx_per_seed: int = 25,
    expand_after: bool = True,
    _: None = Depends(_require_data_admin),
):
    if seed_limit > 50 or tx_per_seed > 100:
        raise HTTPException(status_code=400, detail="seed_limit_max_50_tx_per_seed_max_100")
    return await asyncio.to_thread(ingest_seed_transactions, chain, seed_limit, tx_per_seed, 0.22, expand_after)


@router.get("/latest-block/{chain}")
async def latest_block(chain: str):
    return {"ok": True, "chain": chain, "latest_block": await asyncio.to_thread(get_latest_block, chain)}


@router.get("/wallet/{address}")
async def wallet_analyzer(address: str):
    """Analyze wallet with Net Worth across BSC + ETH."""
    async def _analyze_chain(chain: str):
        return await asyncio.to_thread(analyze_wallet_full, address, chain)
    
    # Parallel analysis
    bsc_task = _analyze_chain("bsc")
    eth_task = _analyze_chain("eth")
    bsc, eth = await asyncio.gather(bsc_task, eth_task)
    
    bsc_net_worth = _safe_chain_net_worth(bsc)
    eth_net_worth = _safe_chain_net_worth(eth)
    total_net_worth = bsc_net_worth + eth_net_worth
    
    total_tx = (bsc.get("tx_count") or 0) + (eth.get("tx_count") or 0)
    
    # Multi-chain intelligence aggregation
    activity_bsc = bsc.get("activity") or {}
    activity_eth = eth.get("activity") or {}
    
    # Pick earliest first_seen
    first_seen = None
    last_seen = None
    total_active_days = 0
    for act in [activity_bsc, activity_eth]:
        if act.get("first_seen"):
            ts = time.mktime(time.strptime(act["first_seen"], "%Y-%m-%d"))
            if first_seen is None or ts < first_seen:
                first_seen = ts
        if act.get("last_seen"):
            ts = time.mktime(time.strptime(act["last_seen"], "%Y-%m-%d"))
            if last_seen is None or ts > last_seen:
                last_seen = ts
        total_active_days += act.get("active_days", 0)
    
    raw_tokens = (bsc.get("tokens") or []) + (eth.get("tokens") or [])
    raw_display = (bsc.get("display_tokens") or []) + (eth.get("display_tokens") or [])
    all_tokens = _trusted_tokens(raw_tokens)
    all_display = _trusted_tokens(raw_display)
    excluded_marks = max(0, len(raw_tokens) - len(all_tokens)) + max(0, len(raw_display) - len(all_display))
    
    # Recalculate concentration with all tokens
    from services.wallet_analyzer import compute_token_concentration, compute_risk_score, compute_smart_label
    concentration = compute_token_concentration(all_tokens)
    activity_agg = {
        "first_seen": time.strftime("%Y-%m-%d", time.gmtime(first_seen)) if first_seen else None,
        "last_seen": time.strftime("%Y-%m-%d", time.gmtime(last_seen)) if last_seen else None,
        "tx_count": total_tx,
        "active_days": total_active_days,
        "tx_per_day": round(total_tx / max(1, (last_seen - first_seen) / 86400), 2) if first_seen and last_seen else 0.0,
    }
    risk = compute_risk_score(all_tokens, concentration, activity_agg)
    label = compute_smart_label(total_tx, total_net_worth if total_net_worth > 0 else None, len(all_tokens), activity_agg, concentration)
    
    chains = []
    if bsc.get("native_balance", 0) > 0 or bsc.get("tx_count", 0) > 0:
        chains.append({
            "chain": "bsc",
            "balance": bsc.get("native_balance"),
            "tx_count": bsc.get("tx_count"),
            "unit": "BNB",
            "net_worth_usd": round(bsc_net_worth, 2),
            "token_count": bsc.get("token_count", 0),
            "tokens_with_value": bsc.get("tokens_with_value", 0),
            "top_holdings": bsc.get("top_holdings", []),
        })
    if eth.get("native_balance", 0) > 0 or eth.get("tx_count", 0) > 0:
        chains.append({
            "chain": "eth",
            "balance": eth.get("native_balance"),
            "tx_count": eth.get("tx_count"),
            "unit": "ETH",
            "net_worth_usd": round(eth_net_worth, 2),
            "token_count": eth.get("token_count", 0),
            "tokens_with_value": eth.get("tokens_with_value", 0),
            "top_holdings": eth.get("top_holdings", []),
        })
    chains.sort(
        key=lambda item: (
            float(item.get("net_worth_usd") or 0),
            int(item.get("tx_count") or 0),
            int(item.get("token_count") or 0),
        ),
        reverse=True,
    )
    primary_chain = chains[0]["chain"] if chains else None
    
    # Aggregate label reasons from both chains
    all_label_reasons = []
    seen_reasons = set()
    for lr in [(bsc.get("label_reasons") or []), (eth.get("label_reasons") or [])]:
        for r in lr:
            if r not in seen_reasons:
                seen_reasons.add(r)
                all_label_reasons.append(r)
    if not all_label_reasons:
        all_label_reasons = ["regular wallet activity"]

    return {
        "ok": True,
        "wallet": address.lower(),
        "chain": primary_chain,
        "primary_chain": primary_chain,
        "summary": {
            "total_usd": round(total_net_worth, 2) if total_net_worth > 0 else None,
            "tx_count": total_tx,
            "chains": len(chains),
            "tokens": len(all_tokens),
            "tokens_with_value": len(all_display),
        },
        "data_sources": {
            "chains": {
                "bsc": bsc.get("data_sources"),
                "eth": eth.get("data_sources"),
            },
            "policy": "chain-scoped balances and markets; never price one chain with another chain pair",
        },
        "net_worth_usd": round(total_net_worth, 2) if total_net_worth > 0 else None,
        "tx_count": total_tx,
        "chains": chains,
        "tokens": all_tokens,
        "display_tokens": all_display,
        "top_holdings": sorted(all_display, key=lambda x: x.get("value_usd") or 0, reverse=True)[:5],
        "wallet_label": label,
        "label_reasons": all_label_reasons,
        "token_count": len(all_tokens),
        "tokens_with_value": len(all_display),
        "data_quality": {
            "trusted_tokens": len(all_tokens),
            "trusted_display_tokens": len(all_display),
            "excluded_marks": excluded_marks,
            "notes": ["cross_chain_dex_cache_guard", "rpc_contract_proof", "field_level_source_trace", "impossible_usd_marks_filtered"],
        },
        "activity": activity_agg,
        "flow": {
            "inflow_eth": round((bsc.get("flow", {}).get("inflow_eth") or 0) + (eth.get("flow", {}).get("inflow_eth") or 0), 6),
            "outflow_eth": round((bsc.get("flow", {}).get("outflow_eth") or 0) + (eth.get("flow", {}).get("outflow_eth") or 0), 6),
            "net_flow_eth": round((bsc.get("flow", {}).get("net_flow_eth") or 0) + (eth.get("flow", {}).get("net_flow_eth") or 0), 6),
        },
        "concentration": concentration,
        "risk_score": risk,
    }

LEGACY_INGEST_SINGLE_BLOCK_CONFIRM = "INGEST_ONCHAIN_SINGLE_BLOCK"
LEGACY_INGEST_RECENT_BLOCKS_CONFIRM = "INGEST_ONCHAIN_RECENT_BLOCKS"
LEGACY_INGEST_EXACT_SWAP_WINDOW_CONFIRM = "INGEST_EXACT_SWAP_WINDOW"
LEGACY_INGEST_EXACT_SWAP_PROGRESSIVE_CONFIRM = "INGEST_EXACT_SWAP_PROGRESSIVE"


def _legacy_ingest_dry_run_payload(
    *,
    ingest_type: str,
    confirm_required: str,
    params: dict,
) -> dict:
    return dry_run_raw_data_collection_payload(
        status_key="ingest_status",
        status="ready_but_disabled",
        action_type=ingest_type,
        confirm_required=confirm_required,
        params=params,
        would_call_rpc=True,
        would_collect_raw_data=True,
        would_update_wallet_aggregates=ingest_type in {"single_block", "recent_blocks"},
        source_policy=(
            "legacy ingest route is dry-run-first; real raw-data ingestion requires explicit confirm and admin token. "
            "It must not create labels, mappings, trades, client signals or opt-ins."
        ),
    )


@router.post("/ingest/recent/{chain}")
async def ingest_recent(
    chain: str,
    count: int = 3,
    confirmations: int = 3,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if count > 20:
        raise HTTPException(status_code=400, detail="count_max_20")
    if confirmations > 50:
        raise HTTPException(status_code=400, detail="confirmations_max_50")
    if dry_run:
        return _legacy_ingest_dry_run_payload(
            ingest_type="recent_blocks",
            confirm_required=LEGACY_INGEST_RECENT_BLOCKS_CONFIRM,
            params={"chain": chain, "count": count, "confirmations": confirmations},
        )
    if confirm != LEGACY_INGEST_RECENT_BLOCKS_CONFIRM:
        raise HTTPException(status_code=400, detail=confirm_required_detail(LEGACY_INGEST_RECENT_BLOCKS_CONFIRM))
    return await asyncio.to_thread(ingest_recent_blocks, chain, count, confirmations)


@router.post("/ingest/exact-swap-window/{chain}")
async def ingest_exact_swap_window(
    chain: str,
    count: int = 3,
    confirmations: int = 3,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if count > 20:
        raise HTTPException(status_code=400, detail="count_max_20")
    if confirmations > 50:
        raise HTTPException(status_code=400, detail="confirmations_max_50")
    if dry_run:
        return _legacy_ingest_dry_run_payload(
            ingest_type="exact_swap_window",
            confirm_required=LEGACY_INGEST_EXACT_SWAP_WINDOW_CONFIRM,
            params={"chain": chain, "count": count, "confirmations": confirmations},
        )
    if confirm != LEGACY_INGEST_EXACT_SWAP_WINDOW_CONFIRM:
        raise HTTPException(status_code=400, detail=confirm_required_detail(LEGACY_INGEST_EXACT_SWAP_WINDOW_CONFIRM))
    return await asyncio.to_thread(ingest_exact_swap_window_job, chain, count, confirmations)


@router.post("/ingest/exact-swap-progressive")
async def ingest_exact_swap_progressive(
    max_chains: int = 2,
    count_per_chain: int = 1,
    confirmations: int = 12,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if max_chains > 5:
        raise HTTPException(status_code=400, detail="max_chains_max_5")
    if count_per_chain > 5:
        raise HTTPException(status_code=400, detail="count_per_chain_max_5")
    if confirmations > 50:
        raise HTTPException(status_code=400, detail="confirmations_max_50")
    if dry_run:
        return _legacy_ingest_dry_run_payload(
            ingest_type="exact_swap_progressive",
            confirm_required=LEGACY_INGEST_EXACT_SWAP_PROGRESSIVE_CONFIRM,
            params={"max_chains": max_chains, "count_per_chain": count_per_chain, "confirmations": confirmations},
        )
    if confirm != LEGACY_INGEST_EXACT_SWAP_PROGRESSIVE_CONFIRM:
        raise HTTPException(status_code=400, detail=confirm_required_detail(LEGACY_INGEST_EXACT_SWAP_PROGRESSIVE_CONFIRM))
    return await asyncio.to_thread(run_exact_swap_ingestion_plan_once, max_chains, count_per_chain, confirmations)


@router.post("/ingest/{chain}/{block_number}")
async def ingest_single(
    chain: str,
    block_number: int,
    dry_run: bool = True,
    confirm: str | None = None,
    _: None = Depends(_require_data_admin),
):
    if dry_run:
        return _legacy_ingest_dry_run_payload(
            ingest_type="single_block",
            confirm_required=LEGACY_INGEST_SINGLE_BLOCK_CONFIRM,
            params={"chain": chain, "block_number": block_number},
        )
    if confirm != LEGACY_INGEST_SINGLE_BLOCK_CONFIRM:
        raise HTTPException(status_code=400, detail=confirm_required_detail(LEGACY_INGEST_SINGLE_BLOCK_CONFIRM))
    return await asyncio.to_thread(ingest_block, chain, block_number)

@router.post("/auto-ingest/start")
async def auto_ingest_start(chain: str = "bsc", _: None = Depends(_require_data_admin)):
    if os.getenv("HERMES_ENABLE_AUTO_INGEST") != "1":
        raise HTTPException(
            status_code=403,
            detail="auto_ingest_disabled_set_HERMES_ENABLE_AUTO_INGEST_1",
        )
    start_auto_ingest(chain)
    return {"ok": True, "chain": chain, "status": "started"}
