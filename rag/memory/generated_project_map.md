# Generated Project Map

Generated at: `2026-06-04T15:53:16.982740+00:00`

Purpose: give Core Equity RAG a compact operating map for long coding sessions.

## Guardrails

- Follow `Frontend -> API -> Router -> Service -> Data` before patching.
- Treat `label_candidates` as untrusted until strict admin promotion.
- Treat `label_candidate_evidence` as evidence bundles, not trusted labels.
- Treat `wallet_chain_state` as observed RPC/explorer state with source attribution.
- Treat `data_jobs` as the audit trail for automated ingestion/enrichment/corroboration.
- Any endpoint with `Depends(_require_data_admin)` requires `CORE_ADMIN_TOKEN`.

## Router Surface

### `backend/routers/__init__.py`
- No router endpoints detected.
### `backend/routers/agents.py`
- `POST /run` -> `run_agent` [ read] -> no direct service detected
- `GET /status` -> `?` [ read] -> no direct service detected
- `POST /stop` -> `stop_agent` [ read] -> no direct service detected
- `GET /signals` -> `?` [ read] -> no direct service detected
- `GET /signals/stats` -> `?` [ read] -> no direct service detected

### `backend/routers/alpha_lab.py`
- `GET /collectors/status` -> `_collectors_status` [ read] -> `get_alpha_sources`
- `GET /sources` -> `_sources_alias` [ read] -> `get_alpha_sources`
- `GET /prediction/markets` -> `_prediction_markets` [ read] -> no direct service detected
- `POST /simulate/prediction-copy` -> `_simulate_prediction_copy` [ read] -> `simulate_prediction_copy`
- `POST /simulate/manipulation` -> `_simulate_manipulation` [ read] -> `simulate_manipulation_strategy`
- `POST /events/dedupe` -> `_events_dedupe` [ read] -> `dedupe_alpha_events`
- `POST /risk/token` -> `_risk_token` [ read] -> `analyze_token_risk`
- `POST /usage/event` -> `_usage_event` [ read] -> no direct service detected
- `GET /usage/stats` -> `_usage_stats` [ read] -> no direct service detected
- `GET /wallet/probe/{wallet}` -> `_wallet_probe` [ read] -> no direct service detected
- `POST /wallet/verify` -> `_wallet_verify` [ read] -> no direct service detected
- `GET /wallet/ownership/{wallet}` -> `_wallet_ownership` [ read] -> no direct service detected
- `GET /wallet/copy-plan/{wallet}` -> `_wallet_copy_plan` [ read] -> no direct service detected
- `GET /wallet/copy-backtest/{wallet}` -> `_wallet_copy_backtest` [ read] -> no direct service detected
- `GET /wallet/automation-plan/{wallet}` -> `_wallet_automation_plan` [ read] -> `get_rpc_wallet_source`, `persist_wallet_analysis_rpc_snapshot`
- `GET /wallet/surface/{wallet}` -> `_wallet_surface` [ read] -> no direct service detected
- `GET /wallet/graph/{wallet}` -> `_wallet_graph` [ read] -> no direct service detected
- `GET /wallet/status` -> `_wallet_status` [ read] -> no direct service detected
- `GET /wallet/discovery` -> `_wallet_discovery` [ read] -> no direct service detected
- `GET /wallet/summary/{address}` -> `_wallet` [ read] -> no direct service detected
- `GET /intelligence` -> `_premium_intelligence` [ read] -> `get_premium_intelligence`
- `GET /premium/stats` -> `_premium_stats` [ read] -> `get_premium_alpha_stats`

### `backend/routers/arkham.py`
- `GET /scrapling/probe` -> `arkham_scrapling_probe` [ read] -> `get_scrapling_probe_service`
- `GET /status` -> `arkham_status` [ read] -> `get_stats`, `get_arkham_tracker`
- `GET /coverage` -> `arkham_coverage` [ read] -> no direct service detected
- `GET /source-backed-inventory` -> `arkham_source_backed_inventory` [ read] -> `get_arkham_source_backed_inventory`
- `GET /signals` -> `arkham_signals` [ read] -> `get_arkham_tracker`, `get_recent_signals`
- `GET /flows` -> `arkham_flows` [ read] -> `get_arkham_tracker`, `get_entity_flow_summary`
- `GET /smart-money` -> `arkham_smart_money` [ read] -> `get_arkham_tracker`, `get_smart_money_activity`
- `GET /search` -> `arkham_search` [ read] -> no direct service detected
- `GET /entity/{entity_slug}` -> `arkham_entity` [ read] -> `get_scrapling_probe_service`
- `GET /token/{symbol}` -> `arkham_token` [ read] -> `get_scrapling_probe_service`
- `GET /token/{symbol}/transfers` -> `arkham_token_transfers` [ read] -> `get_scrapling_probe_service`
- `GET /token/{symbol}/holders` -> `arkham_token_holders` [ read] -> `_safe_float`
- `GET /lookup/{address}` -> `arkham_lookup` [ read] -> no direct service detected
- `POST /scrape/full` -> `trigger_full_scrape` [ read] -> no direct service detected
- `POST /scrape/delta` -> `trigger_delta_scan` [ read] -> no direct service detected
- `GET /db/stats` -> `arkham_db_stats` [ read] -> `get_stats`
- `POST /db/reload` -> `arkham_db_reload` [ read] -> `get_stats`

### `backend/routers/chat.py`
- `POST /message` -> `send_message` [ read] -> no direct service detected
- `GET /history` -> `get_history` [ read] -> no direct service detected
- `GET /status` -> `chat_status` [ read] -> no direct service detected
- `DELETE /history` -> `clear_history` [ read] -> no direct service detected

### `backend/routers/desktop.py`
- `GET /status` -> `?` [ read] -> no direct service detected
- `POST /screenshot` -> `take_screenshot` [ read] -> no direct service detected
- `GET /screenshots` -> `list_screenshots` [ read] -> no direct service detected
- `GET /screenshots/latest` -> `latest_screenshot` [ read] -> no direct service detected
- `POST /mouse/click` -> `mouse_click` [ read] -> no direct service detected
- `POST /keyboard` -> `keyboard_input` [ read] -> no direct service detected
- `POST /launch/ninjatrader` -> `launch_ninjatrader` [ read] -> no direct service detected
- `POST /launch/ninjatrader/full` -> `launch_ninjatrider_full` [ read] -> no direct service detected
- `POST /launch/app` -> `launch_app` [ read] -> no direct service detected
- `POST /screenshot/analyze` -> `screenshot_and_analyze` [ read] -> no direct service detected
- `GET /tools` -> `list_tools` [ read] -> no direct service detected
- `POST /ninjatrader/indicator` -> `nt8_indicator` [ read] -> no direct service detected
- `POST /ninjatrader/switch` -> `nt8_switch` [ read] -> no direct service detected
- `POST /ninjatrader/snapshot` -> `nt8_snapshot` [ read] -> no direct service detected
- `POST /ninjatrader/refresh` -> `nt8_refresh` [ read] -> no direct service detected
- `POST /ninjatrader/zoom` -> `nt8_zoom` [ read] -> no direct service detected
- `POST /ninjatrader/login` -> `nt8_login` [ read] -> no direct service detected
- `POST /ninjatrader/move` -> `nt8_move` [ read] -> no direct service detected
- `POST /ninjatrader/resize` -> `nt8_resize` [ read] -> no direct service detected
- `POST /ninjatrader/timeframe` -> `nt8_timeframe` [ read] -> no direct service detected
- `GET /ninjatrader/data-box` -> `nt8_data_box` [ read] -> no direct service detected

### `backend/routers/entity.py`
- `GET /list` -> `entity_list` [ read] -> `get_entity_list`
- `GET /{slug}` -> `entity_detail` [ read] -> `get_entity_snapshot`, `analyze_entity`
- `GET /{slug}/portfolio` -> `entity_portfolio` [ read] -> `analyze_entity`
- `GET /{slug}/wallets` -> `entity_wallets` [ read] -> `get_entity_labels`
- `GET /{slug}/flows` -> `entity_flows` [ read] -> `analyze_entity`
- `GET /{slug}/history` -> `entity_history` [ read] -> `get_entity_snapshot`

### `backend/routers/intel.py`
- `POST /investigate` -> `launch_investigation` [ read] -> `get_web_agent`, `run`
- `POST /hunt/listings` -> `hunt_binance_listings` [ read] -> `get_specialized_agents`, `hunt_new_listings`, `get_aggregator`, `submit_signal`
- `POST /detective/whale` -> `investigate_whale` [ read] -> `get_specialized_agents`, `investigate_whale_movement`
- `POST /sentiment/scan` -> `scan_sentiment` [ read] -> `get_specialized_agents`
- `POST /sentiment/funding-spike` -> `investigate_funding_spike` [ read] -> `get_specialized_agents`
- `GET /investigations/active` -> `list_active_investigations` [ read] -> `get_web_agent`
- `GET /investigations/{inv_id}` -> `get_investigation_status` [ read] -> `get_web_agent`
- `GET /signals/recent` -> `get_recent_signals` [ read] -> `get_web_agent`, `list_active_investigations`
- `GET /status` -> `get_agents_status` [ read] -> `get_web_agent`, `get_aggregator`
- `POST /test/signal` -> `test_signal_broadcast` [ read] -> `get_aggregator`, `submit_signal`, `broadcast`

### `backend/routers/market.py`
- `GET /snapshot/{coin}` -> `get_snapshot` [ read] -> no direct service detected
- `GET /snapshots` -> `get_all_snapshots` [ read] -> no direct service detected
- `GET /mt5/price/{symbol}` -> `get_price` [ read] -> no direct service detected
- `GET /mt5/account` -> `get_account` [ read] -> no direct service detected
- `GET /mt5/positions` -> `get_positions` [ read] -> no direct service detected
- `GET /mt5/symbols` -> `get_symbols` [ read] -> no direct service detected
- `GET /mt5/health` -> `mt5_health` [ read] -> no direct service detected
- `GET /signals` -> `get_signals` [ read] -> no direct service detected
- `POST /ninjatrader` -> `receive_ninjatrader_data` [ read] -> no direct service detected
- `GET /ninjatrader` -> `get_ninjatrader_data` [ read] -> no direct service detected

### `backend/routers/news.py`
- `GET /gold` -> `get_gold_analysis` [ read] -> no direct service detected
- `GET /gold/bias` -> `get_gold_bias` [ read] -> no direct service detected
- `POST /gold/refresh` -> `refresh_gold_analysis` [ read] -> no direct service detected
- `GET /gold/latest` -> `get_latest_cached` [ read] -> no direct service detected
- `GET /search` -> `search_news` [ read] -> no direct service detected

### `backend/routers/onchain.py`
- `GET /rpc/status` -> `rpc_status` [ read] -> `get_rpc_status`
- `GET /rpc/wallet-state` -> `rpc_wallet_state` [ read] -> `get_rpc_wallet_state`
- `GET /rpc/wallet-source` -> `rpc_wallet_source` [ read] -> `get_rpc_wallet_source`
- `GET /rpc/wallet-quality-audit` -> `rpc_wallet_quality_audit` [ read] -> `get_rpc_wallet_quality_audit`
- `GET /rpc/label-source-gaps` -> `rpc_label_source_gaps` [ read] -> `get_rpc_label_source_gap_report`
- `GET /rpc/wallet-state-audit` -> `rpc_wallet_state_audit` [ read] -> `get_rpc_wallet_state_audit`
- `POST /rpc/backfill-wallet-source-attribution` -> `rpc_backfill_wallet_source_attribution` [ admin] -> `backfill_rpc_wallet_source_attribution`
- `POST /rpc/backfill-wallet-label-sources` -> `rpc_backfill_wallet_label_sources` [ admin] -> `backfill_rpc_wallet_label_sources`
- `POST /rpc/stage-label-source-gap-candidates` -> `rpc_stage_label_source_gap_candidates` [ admin] -> `stage_rpc_label_source_gap_candidates`
- `POST /rpc/corroborate-label-source-gap-candidates` -> `rpc_corroborate_label_source_gap_candidates` [ admin] -> `corroborate_rpc_label_source_gap_candidates`
- `POST /rpc/backfill-label-source-gap-candidate-urls` -> `rpc_backfill_label_source_gap_candidate_urls` [ admin] -> `backfill_rpc_label_source_gap_candidate_urls`
- `GET /rpc/entity-coverage` -> `rpc_entity_coverage` [ read] -> `get_rpc_entity_coverage`
- `GET /rpc/entity-flow` -> `rpc_entity_flow` [ read] -> `get_entity_flow_surface`
- `GET /rpc/entity-gaps` -> `rpc_entity_gaps` [ read] -> `get_rpc_entity_gap_report`
- `GET /rpc/entity-chain-gaps` -> `rpc_entity_chain_gaps` [ read] -> `get_rpc_entity_chain_gap_report`
- `GET /rpc/entity-chain-gap-verification` -> `rpc_entity_chain_gap_verification` [ read] -> `get_rpc_entity_chain_gap_verification`
- `GET /rpc/data-readiness` -> `rpc_data_readiness` [ read] -> `get_onchain_data_readiness`
- `GET /rpc/manipulation-readiness` -> `rpc_manipulation_readiness` [ read] -> no direct service detected
- `POST /rpc/auto-fill-gaps` -> `rpc_auto_fill_gaps` [ admin] -> `run_readiness_gap_auto_fill`
- `GET /rpc/pre-pump-accumulation-scan` -> `rpc_pre_pump_accumulation_scan` [ read] -> `get_pre_pump_accumulation_scan`
- `GET /rpc/adaptive-accumulation-breakout-scan` -> `rpc_adaptive_accumulation_breakout_scan` [ read] -> `get_adaptive_accumulation_breakout_scan`
- `GET /rpc/adaptive-accumulation-backtest` -> `rpc_adaptive_accumulation_backtest` [ read] -> `get_adaptive_accumulation_backtest`
- `GET /rpc/adaptive-accumulation-strategy-matrix` -> `rpc_adaptive_accumulation_strategy_matrix` [ read] -> `get_adaptive_accumulation_strategy_matrix`
- `GET /rpc/adaptive-accumulator-wallet-profiles` -> `rpc_adaptive_accumulator_wallet_profiles` [ read] -> `get_adaptive_accumulator_wallet_profiles`
- `GET /rpc/adaptive-accumulator-cluster-scan` -> `rpc_adaptive_accumulator_cluster_scan` [ read] -> `get_adaptive_accumulator_cluster_scan`
- `GET /rpc/adaptive-accumulator-funder-graph-scan` -> `rpc_adaptive_accumulator_funder_graph_scan` [ read] -> `get_adaptive_accumulator_funder_graph_scan`
- `GET /rpc/adaptive-manipulation-case-file` -> `rpc_adaptive_manipulation_case_file` [ read] -> `get_adaptive_manipulation_case_file`
- `GET /rpc/manipulation-detection-behavioral-evidence-bridge` -> `rpc_manipulation_detection_behavioral_evidence_bridge` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-behavioral-evidence-bridge` -> `rpc_manipulation_detection_behavioral_evidence_bridge` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-top-expansion-behavioral-anomaly-scoring-preview` -> `rpc_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-top-expansion-behavioral-anomaly-scoring-preview` -> `rpc_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-top-expansion-behavioral-shadow-outcome-backtest-plan` -> `rpc_manipulation_detection_top_expansion_behavioral_shadow_outcome_backtest_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-top-expansion-behavioral-shadow-outcome-backtest-plan` -> `rpc_manipulation_detection_top_expansion_behavioral_shadow_outcome_backtest_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-behavioral-score-pump-backtest-preview` -> `rpc_manipulation_detection_behavioral_score_pump_backtest_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-behavioral-score-pump-backtest-preview` -> `rpc_manipulation_detection_behavioral_score_pump_backtest_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-honeypot-correlation-scan-preview` -> `rpc_manipulation_detection_honeypot_correlation_scan_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-honeypot-correlation-scan-preview` -> `rpc_manipulation_detection_honeypot_correlation_scan_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-top-expansion-behavioral-tradability-filter-preview` -> `rpc_manipulation_detection_top_expansion_behavioral_tradability_filter_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-top-expansion-behavioral-tradability-filter-preview` -> `rpc_manipulation_detection_top_expansion_behavioral_tradability_filter_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-top-expansion-behavioral-t0-shift-experiment-preview` -> `rpc_manipulation_detection_top_expansion_behavioral_t0_shift_experiment_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-top-expansion-behavioral-t0-shift-experiment-preview` -> `rpc_manipulation_detection_top_expansion_behavioral_t0_shift_experiment_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-top-expansion-directional-intent-classifier-preview` -> `rpc_manipulation_detection_top_expansion_directional_intent_classifier_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-top-expansion-directional-intent-classifier-preview` -> `rpc_manipulation_detection_top_expansion_directional_intent_classifier_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-stealth-accumulation-anomaly-scan-preview` -> `rpc_manipulation_detection_stealth_accumulation_anomaly_scan_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-stealth-accumulation-anomaly-scan-preview` -> `rpc_manipulation_detection_stealth_accumulation_anomaly_scan_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-stealth-funnel-diagnostic-preview` -> `rpc_manipulation_detection_stealth_funnel_diagnostic_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-stealth-funnel-diagnostic-preview` -> `rpc_manipulation_detection_stealth_funnel_diagnostic_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-quiet-pool-scanner-plan-preview` -> `rpc_manipulation_detection_quiet_pool_scanner_plan_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-quiet-pool-scanner-plan-preview` -> `rpc_manipulation_detection_quiet_pool_scanner_plan_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-cex-listing-probability-bridge-preview` -> `rpc_manipulation_detection_cex_listing_probability_bridge_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-cex-listing-probability-bridge-preview` -> `rpc_manipulation_detection_cex_listing_probability_bridge_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-cex-listing-negative-cohort-discovery-preview` -> `rpc_manipulation_detection_cex_listing_negative_cohort_discovery_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-cex-listing-negative-cohort-discovery-preview` -> `rpc_manipulation_detection_cex_listing_negative_cohort_discovery_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-external-scam-negative-intake-preview` -> `rpc_manipulation_detection_external_scam_negative_intake_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-external-scam-negative-intake-preview` -> `rpc_manipulation_detection_external_scam_negative_intake_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-documented-scam-negative-candidate-scope-expansion-preview` -> `rpc_manipulation_detection_documented_scam_negative_candidate_scope_expansion_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-documented-scam-negative-candidate-scope-expansion-preview` -> `rpc_manipulation_detection_documented_scam_negative_candidate_scope_expansion_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-cex-listing-ground-truth-seed-coherence-checkpoint` -> `rpc_manipulation_detection_cex_listing_ground_truth_seed_coherence_checkpoint` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-cex-listing-ground-truth-seed-coherence-checkpoint` -> `rpc_manipulation_detection_cex_listing_ground_truth_seed_coherence_checkpoint` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-cex-listing-exploratory-shadow-backtest-preview` -> `rpc_manipulation_detection_cex_listing_exploratory_shadow_backtest_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-cex-listing-exploratory-shadow-backtest-preview` -> `rpc_manipulation_detection_cex_listing_exploratory_shadow_backtest_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-cex-listing-feature-wiring-diagnostic-preview` -> `rpc_manipulation_detection_cex_listing_feature_wiring_diagnostic_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-cex-listing-feature-wiring-diagnostic-preview` -> `rpc_manipulation_detection_cex_listing_feature_wiring_diagnostic_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-feature-backfill-orchestrator-preview` -> `rpc_manipulation_detection_feature_backfill_orchestrator_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-feature-backfill-orchestrator-preview` -> `rpc_manipulation_detection_feature_backfill_orchestrator_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-b-feature-backfill-replay-diagnostic-preview` -> `rpc_manipulation_detection_b_feature_backfill_replay_diagnostic_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-b-feature-backfill-replay-diagnostic-preview` -> `rpc_manipulation_detection_b_feature_backfill_replay_diagnostic_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-b-cex-destination-wallet-reference-repair-preview` -> `rpc_manipulation_detection_b_cex_destination_wallet_reference_repair_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-b-cex-destination-wallet-reference-repair-preview` -> `rpc_manipulation_detection_b_cex_destination_wallet_reference_repair_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-b-destination-holder-distribution-flow-check-preview` -> `rpc_manipulation_detection_b_destination_holder_distribution_flow_check_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-b-destination-holder-distribution-flow-check-preview` -> `rpc_manipulation_detection_b_destination_holder_distribution_flow_check_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-lab-b-targeted-raw-context-backfill-plan` -> `rpc_manipulation_detection_lab_b_targeted_raw_context_backfill_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-lab-b-targeted-raw-context-backfill-plan` -> `rpc_manipulation_detection_lab_b_targeted_raw_context_backfill_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-b-seed-bounded-raw-context-lookup-dry-run` -> `rpc_manipulation_detection_b_seed_bounded_raw_context_lookup_dry_run` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-b-seed-bounded-raw-context-lookup-dry-run` -> `rpc_manipulation_detection_b_seed_bounded_raw_context_lookup_dry_run` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-b-seed-raw-context-evidence/insert` -> `rpc_insert_manipulation_detection_b_seed_raw_context_evidence` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-local-native-ground-truth-discovery-preview` -> `rpc_manipulation_detection_local_native_ground_truth_discovery_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-local-native-ground-truth-discovery-preview` -> `rpc_manipulation_detection_local_native_ground_truth_discovery_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-native-positive-candidate-replacement-discovery-preview` -> `rpc_manipulation_detection_native_positive_candidate_replacement_discovery_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-native-positive-candidate-replacement-discovery-preview` -> `rpc_manipulation_detection_native_positive_candidate_replacement_discovery_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-local-native-ground-truth-labeling-lookup-preview` -> `rpc_manipulation_detection_local_native_ground_truth_labeling_lookup_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-local-native-ground-truth-labeling-lookup-preview` -> `rpc_manipulation_detection_local_native_ground_truth_labeling_lookup_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-cex-listing-ground-truth-dataset-plan-preview` -> `rpc_manipulation_detection_cex_listing_ground_truth_dataset_plan_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-cex-listing-ground-truth-dataset-plan-preview` -> `rpc_manipulation_detection_cex_listing_ground_truth_dataset_plan_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-cex-listing-ground-truth-dataset/create` -> `rpc_create_manipulation_detection_cex_listing_ground_truth_dataset` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-cex-listing-ground-truth-dataset/insert` -> `rpc_insert_manipulation_detection_cex_listing_ground_truth_rows` [ admin] -> no direct service detected
- `GET /rpc/swap-identity-readiness` -> `rpc_swap_identity_readiness` [ read] -> `get_swap_identity_readiness`
- `GET /rpc/token-transfer-coverage` -> `rpc_token_transfer_coverage` [ read] -> `get_token_transfer_coverage`
- `GET /rpc/token-transfer-cex-deposits` -> `rpc_token_transfer_cex_deposits` [ read] -> `get_token_transfer_cex_deposit_scan`
- `GET /rpc/cex-label-coverage` -> `rpc_cex_label_coverage` [ read] -> `get_cex_label_coverage_audit`
- `GET /rpc/cex-label-acquisition-plan` -> `rpc_cex_label_acquisition_plan` [ read] -> `get_cex_label_acquisition_plan`
- `GET /rpc/cex-label-promotion-review` -> `rpc_cex_label_promotion_review` [ read] -> `get_cex_label_promotion_review`
- `POST /rpc/cex-label-promotion-write-preview` -> `rpc_cex_label_promotion_write_preview` [ admin] -> `get_cex_label_promotion_write_preview`
- `GET /rpc/cex-label-promotion-admin-queue` -> `rpc_cex_label_promotion_admin_queue` [ admin] -> `get_cex_label_promotion_admin_queue`
- `POST /rpc/cex-label-promotion-stage` -> `rpc_cex_label_promotion_stage` [ admin] -> `get_cex_label_promotion_stage`
- `POST /rpc/cex-label-promotion-backup` -> `rpc_cex_label_promotion_backup` [ admin] -> `get_cex_label_promotion_backup`
- `GET /rpc/cex-label-promotion-backups` -> `rpc_cex_label_promotion_backups` [ admin] -> `get_cex_label_promotion_backups`
- `GET /rpc/cex-label-promotion-final-check` -> `rpc_cex_label_promotion_final_check` [ admin] -> `get_cex_label_promotion_final_check`
- `GET /rpc/cex-label-promotion-execution-envelope` -> `rpc_cex_label_promotion_execution_envelope` [ admin] -> `get_cex_label_promotion_execution_envelope`
- `GET /rpc/cex-label-promotion-simulation-report` -> `rpc_cex_label_promotion_simulation_report` [ admin] -> `get_cex_label_promotion_simulation_report`
- `GET /rpc/cex-label-promotion-dashboard` -> `rpc_cex_label_promotion_dashboard` [ admin] -> `get_cex_label_promotion_dashboard`
- `GET /rpc/cex-label-promotion-blocker-audit` -> `rpc_cex_label_promotion_blocker_audit` [ admin] -> `get_cex_label_promotion_blocker_audit`
- `GET /rpc/cex-label-source-quality-plan` -> `rpc_cex_label_source_quality_plan` [ admin] -> `get_cex_label_source_quality_plan`
- `GET /rpc/cex-label-independent-source-queue` -> `rpc_cex_label_independent_source_queue` [ admin] -> `get_cex_label_independent_source_queue`
- `POST /rpc/cex-label-independent-evidence-dry-run` -> `rpc_cex_label_independent_evidence_dry_run` [ admin] -> `get_cex_label_independent_evidence_dry_run`
- `POST /rpc/cex-label-independent-evidence-persist-preview` -> `rpc_cex_label_independent_evidence_persist_preview` [ admin] -> `get_cex_label_independent_evidence_persist_preview`
- `POST /rpc/cex-label-independent-evidence-persist-contract` -> `rpc_cex_label_independent_evidence_persist_contract` [ admin] -> `get_cex_label_independent_evidence_persist_contract`
- `POST /rpc/cex-label-independent-evidence/insert` -> `rpc_cex_label_independent_evidence_insert` [ admin] -> `insert_cex_label_independent_evidence`
- `GET /rpc/cex-label-independent-evidence-review-queue` -> `rpc_cex_label_independent_evidence_review_queue` [ admin] -> `get_cex_label_independent_evidence_review_queue`
- `POST /rpc/cex-label-confidence-upgrade-preview` -> `rpc_cex_label_confidence_upgrade_preview` [ admin] -> `get_cex_label_confidence_upgrade_preview`
- `POST /rpc/cex-label-confidence-upgrade-stage` -> `rpc_cex_label_confidence_upgrade_stage` [ admin] -> `get_cex_label_confidence_upgrade_stage`
- `POST /rpc/cex-label-confidence-upgrade-backup-preview` -> `rpc_cex_label_confidence_upgrade_backup_preview` [ admin] -> `get_cex_label_confidence_upgrade_backup_preview`
- `POST /rpc/cex-label-confidence-upgrade-backup` -> `rpc_cex_label_confidence_upgrade_backup` [ admin] -> `get_cex_label_confidence_upgrade_backup`
- `GET /rpc/cex-label-confidence-upgrade-backups` -> `rpc_cex_label_confidence_upgrade_backups` [ admin] -> `get_cex_label_confidence_upgrade_backups`
- `GET /rpc/cex-label-confidence-upgrade-final-check` -> `rpc_cex_label_confidence_upgrade_final_check` [ admin] -> `get_cex_label_confidence_upgrade_final_check`
- `POST /rpc/cex-label-confidence-upgrade-execution-envelope` -> `rpc_cex_label_confidence_upgrade_execution_envelope` [ admin] -> `get_cex_label_confidence_upgrade_execution_envelope`
- `POST /rpc/cex-label-confidence-upgrade-simulation-report` -> `rpc_cex_label_confidence_upgrade_simulation_report` [ admin] -> `get_cex_label_confidence_upgrade_simulation_report`
- `POST /rpc/cex-label-confidence-upgrade-policy-gate` -> `rpc_cex_label_confidence_upgrade_policy_gate` [ admin] -> `get_cex_label_confidence_upgrade_policy_gate`
- `POST /rpc/cex-label-confidence-upgrade-apply` -> `rpc_cex_label_confidence_upgrade_apply` [ admin] -> `get_cex_label_confidence_upgrade_apply`
- `POST /rpc/cex-label-confidence-upgrade-prewrite-audit` -> `rpc_cex_label_confidence_upgrade_prewrite_audit` [ admin] -> `get_cex_label_confidence_upgrade_prewrite_audit`
- `POST /rpc/cex-label-confidence-upgrade-controlled-write-review` -> `rpc_cex_label_confidence_upgrade_controlled_write_review` [ admin] -> `get_cex_label_confidence_upgrade_controlled_write_review`
- `POST /rpc/cex-label-confidence-upgrade-sql-plan` -> `rpc_cex_label_confidence_upgrade_sql_plan` [ admin] -> `get_cex_label_confidence_upgrade_sql_plan`
- `POST /rpc/cex-label-confidence-upgrade-rollback-smoke` -> `rpc_cex_label_confidence_upgrade_rollback_smoke` [ admin] -> `get_cex_label_confidence_upgrade_rollback_smoke`
- `GET /rpc/cex-independent-evidence-queue-schema-plan` -> `rpc_cex_independent_evidence_queue_schema_plan` [ admin] -> `get_cex_independent_evidence_queue_schema_plan`
- `POST /rpc/cex-independent-evidence-queue/create` -> `rpc_create_cex_independent_evidence_queue` [ admin] -> `create_cex_independent_evidence_queue`
- `GET /rpc/cex-deposit-holder-snapshot-refresh-queue` -> `rpc_cex_deposit_holder_snapshot_refresh_queue` [ read] -> `get_cex_deposit_holder_snapshot_refresh_queue`
- `POST /rpc/cex-deposit-holder-snapshots/refresh` -> `rpc_refresh_cex_deposit_holder_snapshots` [ admin] -> `refresh_cex_deposit_holder_snapshots`
- `GET /rpc/swap-venue-resolution-candidates` -> `rpc_swap_venue_resolution_candidates` [ read] -> `get_swap_venue_resolution_candidates`
- `GET /rpc/unknown-swap-attribution-audit` -> `rpc_unknown_swap_attribution_audit` [ read] -> `get_unknown_swap_attribution_audit`
- `GET /rpc/dex-router-source-map` -> `rpc_dex_router_source_map` [ admin] -> `get_dex_router_source_map`
- `GET /rpc/dex-router-official-source-queue` -> `rpc_dex_router_official_source_queue` [ admin] -> `get_dex_router_official_source_queue`
- `POST /rpc/dex-router-official-evidence-dry-run` -> `rpc_dex_router_official_evidence_dry_run` [ admin] -> `get_dex_router_official_evidence_dry_run`
- `POST /rpc/dex-router-official-evidence-persist-preview` -> `rpc_dex_router_official_evidence_persist_preview` [ admin] -> `get_dex_router_official_evidence_persist_preview`
- `GET /rpc/dex-router-official-evidence-queue-schema-plan` -> `rpc_dex_router_official_evidence_queue_schema_plan` [ admin] -> `get_dex_router_official_evidence_queue_schema_plan`
- `POST /rpc/dex-router-official-evidence-queue/create` -> `rpc_create_dex_router_official_evidence_queue` [ admin] -> `create_dex_router_official_evidence_queue`
- `POST /rpc/dex-router-official-evidence/insert` -> `rpc_insert_dex_router_official_evidence` [ admin] -> `insert_dex_router_official_evidence`
- `GET /rpc/dex-router-official-evidence-review-queue` -> `rpc_dex_router_official_evidence_review_queue` [ admin] -> `get_dex_router_official_evidence_review_queue`
- `POST /rpc/dex-router-venue-mapping-preview` -> `rpc_dex_router_venue_mapping_preview` [ admin] -> `get_dex_router_venue_mapping_preview`
- `POST /rpc/dex-router-venue-mapping-final-check` -> `rpc_dex_router_venue_mapping_final_check` [ admin] -> `get_dex_router_venue_mapping_final_check`
- `POST /rpc/dex-router-venue-mapping-execution-envelope` -> `rpc_dex_router_venue_mapping_execution_envelope` [ admin] -> `get_dex_router_venue_mapping_execution_envelope`
- `POST /rpc/dex-router-venue-mapping-simulation-report` -> `rpc_dex_router_venue_mapping_simulation_report` [ admin] -> `get_dex_router_venue_mapping_simulation_report`
- `POST /rpc/dex-router-venue-mapping-policy-gate` -> `rpc_dex_router_venue_mapping_policy_gate` [ admin] -> `get_dex_router_venue_mapping_policy_gate`
- `POST /rpc/dex-router-venue-mapping-apply` -> `rpc_dex_router_venue_mapping_apply` [ admin] -> `get_dex_router_venue_mapping_apply`
- `POST /rpc/dex-router-venue-mapping-prewrite-audit` -> `rpc_dex_router_venue_mapping_prewrite_audit` [ admin] -> `get_dex_router_venue_mapping_prewrite_audit`
- `POST /rpc/dex-router-venue-mapping-controlled-write-review` -> `rpc_dex_router_venue_mapping_controlled_write_review` [ admin] -> `get_dex_router_venue_mapping_controlled_write_review`
- `POST /rpc/dex-router-venue-mapping-sql-plan` -> `rpc_dex_router_venue_mapping_sql_plan` [ admin] -> `get_dex_router_venue_mapping_sql_plan`
- `POST /rpc/dex-router-venue-mapping-final-safety-review` -> `rpc_dex_router_venue_mapping_final_safety_review` [ admin] -> `get_dex_router_venue_mapping_final_safety_review`
- `POST /rpc/dex-router-venue-mapping/apply-confirmed` -> `rpc_dex_router_venue_mapping_apply_confirmed` [ admin] -> `get_dex_router_venue_mapping_apply_confirmed_design`
- `POST /rpc/dex-router-venue-mapping-real-write-go-nogo` -> `rpc_dex_router_venue_mapping_real_write_go_nogo` [ admin] -> `get_dex_router_venue_mapping_real_write_go_nogo`
- `POST /rpc/dex-router-venue-mapping/write-skeleton` -> `rpc_dex_router_venue_mapping_write_skeleton` [ admin] -> `get_dex_router_venue_mapping_write_skeleton`
- `POST /rpc/dex-router-venue-mapping/transactional-write-design` -> `rpc_dex_router_venue_mapping_transactional_write_design` [ admin] -> `get_dex_router_venue_mapping_transactional_write_design`
- `POST /rpc/dex-router-venue-mapping/transactional-write-report` -> `rpc_dex_router_venue_mapping_transactional_write_report` [ admin] -> `get_dex_router_venue_mapping_transactional_write_report`
- `POST /rpc/dex-router-venue-mapping/confirmed-write-blueprint` -> `rpc_dex_router_venue_mapping_confirmed_write_blueprint` [ admin] -> `get_dex_router_venue_mapping_confirmed_write_blueprint`
- `POST /rpc/dex-router-venue-mapping/multi-router-validation-scan` -> `rpc_dex_router_venue_mapping_multi_router_validation_scan` [ admin] -> `get_dex_router_venue_mapping_multi_router_validation_scan`
- `POST /rpc/dex-router-venue-mapping/additional-router-evidence-plan` -> `rpc_dex_router_venue_mapping_additional_router_evidence_plan` [ admin] -> `get_dex_router_venue_mapping_additional_router_evidence_plan`
- `POST /rpc/lab-venue-coverage-source-plan` -> `rpc_lab_venue_coverage_source_plan` [ admin] -> `get_lab_venue_coverage_source_plan`
- `POST /rpc/token-venue-coverage-source-plan` -> `rpc_token_venue_coverage_source_plan` [ admin] -> `get_token_venue_coverage_source_plan`
- `POST /rpc/token-market-discovery-input-contract` -> `rpc_token_market_discovery_input_contract` [ admin] -> `get_token_market_discovery_input_contract`
- `POST /rpc/token-market-manual-candidate-intake-contract` -> `rpc_token_market_manual_candidate_intake_contract` [ admin] -> `get_token_market_manual_candidate_intake_contract`
- `GET /rpc/token-market-local-candidate-discovery-radar` -> `rpc_token_market_local_candidate_discovery_radar` [ admin] -> `get_token_market_local_candidate_discovery_radar`
- `POST /rpc/token-market-local-candidate-discovery-radar` -> `rpc_token_market_local_candidate_discovery_radar` [ admin] -> `get_token_market_local_candidate_discovery_radar`
- `GET /rpc/token-manipulation-data-usability-audit` -> `rpc_token_manipulation_data_usability_audit` [ admin] -> no direct service detected
- `POST /rpc/token-manipulation-data-usability-audit` -> `rpc_token_manipulation_data_usability_audit` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-reliability-engine` -> `rpc_manipulation_detection_reliability_engine` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-reliability-engine` -> `rpc_manipulation_detection_reliability_engine` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-scoring-design` -> `rpc_manipulation_detection_source_backed_scoring_design` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-scoring-design` -> `rpc_manipulation_detection_source_backed_scoring_design` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-shadow-backtest-plan` -> `rpc_manipulation_detection_source_backed_shadow_backtest_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-shadow-backtest-plan` -> `rpc_manipulation_detection_source_backed_shadow_backtest_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-shadow-backtest-outcome-dataset-schema-plan` -> `rpc_manipulation_detection_source_backed_shadow_backtest_outcome_dataset_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-shadow-backtest-outcome-dataset-schema-plan` -> `rpc_manipulation_detection_source_backed_shadow_backtest_outcome_dataset_schema_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-outcome-window-data-collection` -> `rpc_manipulation_detection_source_backed_outcome_window_data_collection` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-window-data-collection` -> `rpc_manipulation_detection_source_backed_outcome_window_data_collection` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-outcome-quality-repair-sync-liquidity-context` -> `rpc_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-quality-repair-sync-liquidity-context` -> `rpc_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-collection-plan` -> `rpc_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-collection-plan` -> `rpc_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-outcome-sync-mint-burn-topic-binding-checkpoint` -> `rpc_manipulation_detection_source_backed_outcome_sync_mint_burn_topic_binding_checkpoint` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-sync-mint-burn-topic-binding-checkpoint` -> `rpc_manipulation_detection_source_backed_outcome_sync_mint_burn_topic_binding_checkpoint` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-lookup-dry-run` -> `rpc_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-lookup-dry-run` -> `rpc_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence-schema-plan` -> `rpc_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence-schema-plan` -> `rpc_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/insert` -> `rpc_insert_manipulation_detection_source_backed_outcome_sync_liquidity_evidence` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/review` -> `rpc_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/review` -> `rpc_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-outcome-quality-repair-preview` -> `rpc_manipulation_detection_source_backed_outcome_quality_repair_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-outcome-quality-repair-preview` -> `rpc_manipulation_detection_source_backed_outcome_quality_repair_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-repaired-outcome-dataset-schema-plan` -> `rpc_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-repaired-outcome-dataset-schema-plan` -> `rpc_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-repaired-outcome-dataset/create` -> `rpc_create_manipulation_detection_source_backed_repaired_outcome_dataset` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-repaired-outcome-dataset/insert` -> `rpc_insert_manipulation_detection_source_backed_repaired_outcome_dataset` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-repaired-outcome-dataset/review` -> `rpc_manipulation_detection_source_backed_repaired_outcome_dataset_review` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-repaired-outcome-dataset/review` -> `rpc_manipulation_detection_source_backed_repaired_outcome_dataset_review` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-shadow-backtest-preview` -> `rpc_manipulation_detection_source_backed_shadow_backtest_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-shadow-backtest-preview` -> `rpc_manipulation_detection_source_backed_shadow_backtest_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-shadow-replay-controls-preview` -> `rpc_manipulation_detection_source_backed_shadow_replay_controls_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-shadow-replay-controls-preview` -> `rpc_manipulation_detection_source_backed_shadow_replay_controls_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-control-outcome-collection-plan` -> `rpc_manipulation_detection_source_backed_control_outcome_collection_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-control-outcome-collection-plan` -> `rpc_manipulation_detection_source_backed_control_outcome_collection_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-control-outcome-lookup-dry-run` -> `rpc_manipulation_detection_source_backed_control_outcome_lookup_dry_run` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-control-outcome-lookup-dry-run` -> `rpc_manipulation_detection_source_backed_control_outcome_lookup_dry_run` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-control-outcome-schema-plan` -> `rpc_manipulation_detection_source_backed_control_outcome_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-control-outcome-schema-plan` -> `rpc_manipulation_detection_source_backed_control_outcome_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-control-outcome-windows/create` -> `rpc_create_manipulation_detection_source_backed_control_outcome_windows` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-control-outcome-windows/insert` -> `rpc_insert_manipulation_detection_source_backed_control_outcome_windows` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-control-outcome-windows/review` -> `rpc_manipulation_detection_source_backed_control_outcome_review` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-control-outcome-windows/review` -> `rpc_manipulation_detection_source_backed_control_outcome_review` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-multi-candidate-shadow-replay-preview` -> `rpc_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-multi-candidate-shadow-replay-preview` -> `rpc_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-replay-policy-thresholds` -> `rpc_manipulation_detection_source_backed_replay_policy_thresholds` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-replay-policy-thresholds` -> `rpc_manipulation_detection_source_backed_replay_policy_thresholds` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-case-control-expansion-plan` -> `rpc_manipulation_detection_source_backed_case_control_expansion_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-case-control-expansion-plan` -> `rpc_manipulation_detection_source_backed_case_control_expansion_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-top-expansion-raw-context-collection-plan` -> `rpc_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-top-expansion-raw-context-collection-plan` -> `rpc_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-top-expansion-raw-context-lookup-dry-run` -> `rpc_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-top-expansion-raw-context-lookup-dry-run` -> `rpc_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence-schema-plan` -> `rpc_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence-schema-plan` -> `rpc_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence/insert` -> `rpc_insert_manipulation_detection_source_backed_top_expansion_raw_context_evidence` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-exact-swap-collection-plan` -> `rpc_manipulation_detection_exact_swap_collection_plan` [ admin] -> `get_manipulation_detection_exact_swap_collection_plan`
- `POST /rpc/manipulation-detection-exact-swap-collection-plan` -> `rpc_manipulation_detection_exact_swap_collection_plan` [ admin] -> `get_manipulation_detection_exact_swap_collection_plan`
- `GET /rpc/manipulation-detection-exact-swap-second-window-plan` -> `rpc_manipulation_detection_exact_swap_second_window_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-exact-swap-second-window-plan` -> `rpc_manipulation_detection_exact_swap_second_window_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-raw-swap-repeatability-review` -> `rpc_manipulation_detection_raw_swap_repeatability_review` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-raw-swap-repeatability-review` -> `rpc_manipulation_detection_raw_swap_repeatability_review` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-transfer-context-collection-plan` -> `rpc_manipulation_detection_transfer_context_collection_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-transfer-context-collection-plan` -> `rpc_manipulation_detection_transfer_context_collection_plan` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-transfer-context-lookup-dry-run` -> `rpc_manipulation_detection_transfer_context_lookup_dry_run` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-transfer-context-lookup-dry-run` -> `rpc_manipulation_detection_transfer_context_lookup_dry_run` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-transfer-context-evidence-schema-plan` -> `rpc_manipulation_detection_transfer_context_evidence_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-transfer-context-evidence-schema-plan` -> `rpc_manipulation_detection_transfer_context_evidence_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-transfer-context-evidence/create` -> `rpc_create_manipulation_detection_transfer_context_evidence_table` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-transfer-context-evidence/insert` -> `rpc_insert_manipulation_detection_transfer_context_evidence` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-transfer-context-evidence/review` -> `rpc_manipulation_detection_transfer_context_evidence_review` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-transfer-context-evidence/review` -> `rpc_manipulation_detection_transfer_context_evidence_review` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-transfer-context-evidence/reliability-bridge-preview` -> `rpc_manipulation_detection_transfer_context_reliability_bridge_preview` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-transfer-context-evidence/reliability-bridge-preview` -> `rpc_manipulation_detection_transfer_context_reliability_bridge_preview` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-transfer-context-evidence/reliability-bridge-apply-contract` -> `rpc_manipulation_detection_transfer_context_reliability_bridge_apply_contract` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-transfer-context-evidence/reliability-bridge-apply-contract` -> `rpc_manipulation_detection_transfer_context_reliability_bridge_apply_contract` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-exact-swap-second-window-sqd-lookup-dry-run` -> `rpc_manipulation_detection_exact_swap_second_window_sqd_lookup_dry_run` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-exact-swap-second-window-sqd-lookup-dry-run` -> `rpc_manipulation_detection_exact_swap_second_window_sqd_lookup_dry_run` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-second-window-raw-swap-evidence-schema-plan` -> `rpc_manipulation_detection_second_window_raw_swap_evidence_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-second-window-raw-swap-evidence-schema-plan` -> `rpc_manipulation_detection_second_window_raw_swap_evidence_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/manipulation-detection-second-window-raw-swap-evidence/insert` -> `rpc_insert_manipulation_detection_second_window_raw_swap_evidence` [ admin] -> no direct service detected
- `GET /rpc/manipulation-detection-exact-swap-sqd-lookup-dry-run` -> `rpc_manipulation_detection_exact_swap_sqd_lookup_dry_run` [ admin] -> `run_manipulation_detection_exact_swap_sqd_lookup_dry_run`
- `POST /rpc/manipulation-detection-exact-swap-sqd-lookup-dry-run` -> `rpc_manipulation_detection_exact_swap_sqd_lookup_dry_run` [ admin] -> `run_manipulation_detection_exact_swap_sqd_lookup_dry_run`
- `GET /rpc/manipulation-detection-raw-swap-evidence-schema-plan` -> `rpc_manipulation_detection_raw_swap_evidence_schema_plan` [ admin] -> `get_manipulation_detection_raw_swap_evidence_persistence_schema_plan`
- `POST /rpc/manipulation-detection-raw-swap-evidence-schema-plan` -> `rpc_manipulation_detection_raw_swap_evidence_schema_plan` [ admin] -> `get_manipulation_detection_raw_swap_evidence_persistence_schema_plan`
- `POST /rpc/manipulation-detection-raw-swap-evidence/insert` -> `rpc_insert_manipulation_detection_raw_swap_evidence` [ admin] -> no direct service detected
- `GET /rpc/amount-usd-normalization-and-token-identity-audit` -> `rpc_amount_usd_normalization_and_token_identity_audit` [ admin] -> `get_amount_usd_normalization_and_token_identity_audit`
- `POST /rpc/amount-usd-normalization-and-token-identity-audit` -> `rpc_amount_usd_normalization_and_token_identity_audit` [ admin] -> `get_amount_usd_normalization_and_token_identity_audit`
- `GET /rpc/amount-usd-recompute-plan` -> `rpc_amount_usd_recompute_plan` [ admin] -> `get_amount_usd_recompute_plan`
- `POST /rpc/amount-usd-recompute-plan` -> `rpc_amount_usd_recompute_plan` [ admin] -> `get_amount_usd_recompute_plan`
- `GET /rpc/amount-usd-quarantine-gate` -> `rpc_amount_usd_quarantine_gate` [ admin] -> `get_amount_usd_quarantine_gate`
- `POST /rpc/amount-usd-quarantine-gate` -> `rpc_amount_usd_quarantine_gate` [ admin] -> `get_amount_usd_quarantine_gate`
- `GET /rpc/dex-trades-curated-schema-plan` -> `rpc_dex_trades_curated_schema_plan` [ admin] -> `get_dex_trades_curated_schema_plan`
- `POST /rpc/dex-trades-curated-schema-plan` -> `rpc_dex_trades_curated_schema_plan` [ admin] -> `get_dex_trades_curated_schema_plan`
- `GET /rpc/dex-trades-raw-log-provenance-drilldown` -> `rpc_dex_trades_raw_log_provenance_drilldown` [ admin] -> `get_dex_trades_raw_log_provenance_drilldown`
- `POST /rpc/dex-trades-raw-log-provenance-drilldown` -> `rpc_dex_trades_raw_log_provenance_drilldown` [ admin] -> `get_dex_trades_raw_log_provenance_drilldown`
- `GET /rpc/dex-trades-bounded-receipt-replay-plan` -> `rpc_dex_trades_bounded_receipt_replay_plan` [ admin] -> `get_dex_trades_bounded_receipt_replay_plan`
- `POST /rpc/dex-trades-bounded-receipt-replay-plan` -> `rpc_dex_trades_bounded_receipt_replay_plan` [ admin] -> `get_dex_trades_bounded_receipt_replay_plan`
- `GET /rpc/dex-trades-receipt-parser-preview` -> `rpc_dex_trades_receipt_parser_preview` [ admin] -> `get_dex_trades_receipt_parser_preview`
- `POST /rpc/dex-trades-receipt-parser-preview` -> `rpc_dex_trades_receipt_parser_preview` [ admin] -> `get_dex_trades_receipt_parser_preview`
- `GET /rpc/dex-trades-mock-receipt-parser-test` -> `rpc_dex_trades_mock_receipt_parser_test` [ admin] -> `get_dex_trades_mock_receipt_parser_test`
- `POST /rpc/dex-trades-mock-receipt-parser-test` -> `rpc_dex_trades_mock_receipt_parser_test` [ admin] -> `get_dex_trades_mock_receipt_parser_test`
- `GET /rpc/dex-trade-raw-swap-provenance-schema-plan` -> `rpc_dex_trade_raw_swap_provenance_schema_plan` [ admin] -> `get_dex_trade_raw_swap_provenance_schema_plan`
- `POST /rpc/dex-trade-raw-swap-provenance-schema-plan` -> `rpc_dex_trade_raw_swap_provenance_schema_plan` [ admin] -> `get_dex_trade_raw_swap_provenance_schema_plan`
- `POST /rpc/dex-trade-raw-swap-provenance/create` -> `rpc_create_dex_trade_raw_swap_provenance` [ admin] -> `create_dex_trade_raw_swap_provenance`
- `GET /rpc/dex-trade-raw-swap-provenance/replay-insert-plan` -> `rpc_dex_trade_raw_swap_provenance_replay_insert_plan` [ admin] -> `get_dex_trade_raw_swap_provenance_replay_insert_plan`
- `POST /rpc/dex-trade-raw-swap-provenance/replay-insert-plan` -> `rpc_dex_trade_raw_swap_provenance_replay_insert_plan` [ admin] -> `get_dex_trade_raw_swap_provenance_replay_insert_plan`
- `POST /rpc/dex-trade-raw-swap-provenance/replay-insert/apply` -> `rpc_dex_trade_raw_swap_provenance_replay_insert_apply` [ admin] -> `replay_and_insert_dex_trade_raw_swap_provenance`
- `GET /rpc/dex-trade-raw-swap-provenance/review` -> `rpc_dex_trade_raw_swap_provenance_review` [ admin] -> `get_dex_trade_raw_swap_provenance_review`
- `POST /rpc/dex-trade-raw-swap-provenance/review` -> `rpc_dex_trade_raw_swap_provenance_review` [ admin] -> `get_dex_trade_raw_swap_provenance_review`
- `GET /rpc/dex-trades-curated-from-raw-provenance-schema-plan` -> `rpc_dex_trades_curated_from_raw_provenance_schema_plan` [ admin] -> `get_dex_trades_curated_from_raw_provenance_schema_plan`
- `POST /rpc/dex-trades-curated-from-raw-provenance-schema-plan` -> `rpc_dex_trades_curated_from_raw_provenance_schema_plan` [ admin] -> `get_dex_trades_curated_from_raw_provenance_schema_plan`
- `GET /rpc/dex-trades-raw-provenance-amount-decode-preview` -> `rpc_dex_trades_raw_provenance_amount_decode_preview` [ admin] -> `get_dex_trades_raw_provenance_amount_decode_preview`
- `POST /rpc/dex-trades-raw-provenance-amount-decode-preview` -> `rpc_dex_trades_raw_provenance_amount_decode_preview` [ admin] -> `get_dex_trades_raw_provenance_amount_decode_preview`
- `POST /rpc/dex-trades-curated/create` -> `rpc_dex_trades_curated_create` [ admin] -> `create_dex_trades_curated`
- `POST /rpc/dex-trades-curated/insert` -> `rpc_dex_trades_curated_insert` [ admin] -> `insert_dex_trades_curated_from_raw_provenance`
- `GET /rpc/dex-trades-curated/review` -> `rpc_dex_trades_curated_review` [ admin] -> `get_dex_trades_curated_review`
- `POST /rpc/dex-trades-curated/review` -> `rpc_dex_trades_curated_review` [ admin] -> `get_dex_trades_curated_review`
- `GET /rpc/dex-trades-curated/shadow-scoring-plan` -> `rpc_dex_trades_curated_shadow_scoring_plan` [ admin] -> `get_dex_trades_curated_shadow_scoring_plan`
- `POST /rpc/dex-trades-curated/shadow-scoring-plan` -> `rpc_dex_trades_curated_shadow_scoring_plan` [ admin] -> `get_dex_trades_curated_shadow_scoring_plan`
- `GET /rpc/dex-trades-curated/shadow-casefile` -> `rpc_dex_trades_curated_shadow_casefile` [ admin] -> `get_dex_trades_curated_shadow_casefile`
- `POST /rpc/dex-trades-curated/shadow-casefile` -> `rpc_dex_trades_curated_shadow_casefile` [ admin] -> `get_dex_trades_curated_shadow_casefile`
- `GET /rpc/dex-trades-curated/unknown-route-repair-plan` -> `rpc_dex_trades_curated_unknown_route_repair_plan` [ admin] -> `get_dex_trades_curated_unknown_route_repair_plan`
- `POST /rpc/dex-trades-curated/unknown-route-repair-plan` -> `rpc_dex_trades_curated_unknown_route_repair_plan` [ admin] -> `get_dex_trades_curated_unknown_route_repair_plan`
- `GET /rpc/dex-trades-curated/source-backed-backtest-preview` -> `rpc_dex_trades_curated_source_backed_backtest_preview` [ admin] -> `get_dex_trades_curated_source_backed_backtest_preview`
- `POST /rpc/dex-trades-curated/source-backed-backtest-preview` -> `rpc_dex_trades_curated_source_backed_backtest_preview` [ admin] -> `get_dex_trades_curated_source_backed_backtest_preview`
- `GET /rpc/dex-trades-curated/source-backed-token-ranking` -> `rpc_dex_trades_curated_source_backed_token_ranking` [ admin] -> `get_dex_trades_curated_source_backed_token_ranking`
- `POST /rpc/dex-trades-curated/source-backed-token-ranking` -> `rpc_dex_trades_curated_source_backed_token_ranking` [ admin] -> `get_dex_trades_curated_source_backed_token_ranking`
- `GET /rpc/dex-trades-curated/source-backed-collection-plan` -> `rpc_dex_trades_curated_source_backed_collection_plan` [ admin] -> `get_dex_trades_curated_source_backed_collection_plan`
- `POST /rpc/dex-trades-curated/source-backed-collection-plan` -> `rpc_dex_trades_curated_source_backed_collection_plan` [ admin] -> `get_dex_trades_curated_source_backed_collection_plan`
- `GET /rpc/dex-trades-curated/source-backed-history-collection-plan` -> `rpc_dex_trades_curated_source_backed_history_collection_plan` [ admin] -> `get_dex_trades_curated_source_backed_history_collection_plan`
- `POST /rpc/dex-trades-curated/source-backed-history-collection-plan` -> `rpc_dex_trades_curated_source_backed_history_collection_plan` [ admin] -> `get_dex_trades_curated_source_backed_history_collection_plan`
- `POST /rpc/dex-trades-curated/source-backed-history-collection/apply` -> `rpc_dex_trades_curated_source_backed_history_collection_apply` [ admin] -> `run_dex_trades_curated_source_backed_history_collection`
- `GET /rpc/dex-trades-curated/source-backed-transfer-context-plan` -> `rpc_dex_trades_curated_source_backed_transfer_context_plan` [ admin] -> `get_dex_trades_curated_source_backed_transfer_context_plan`
- `POST /rpc/dex-trades-curated/source-backed-transfer-context-plan` -> `rpc_dex_trades_curated_source_backed_transfer_context_plan` [ admin] -> `get_dex_trades_curated_source_backed_transfer_context_plan`
- `POST /rpc/dex-trades-curated/source-backed-transfer-context/apply` -> `rpc_dex_trades_curated_source_backed_transfer_context_apply` [ admin] -> `collect_token_transfer_context_from_receipts`
- `GET /rpc/dex-trades-curated/expansion-collection-plan` -> `rpc_dex_trades_curated_expansion_collection_plan` [ admin] -> `get_dex_trades_curated_expansion_collection_plan`
- `POST /rpc/dex-trades-curated/expansion-collection-plan` -> `rpc_dex_trades_curated_expansion_collection_plan` [ admin] -> `get_dex_trades_curated_expansion_collection_plan`
- `POST /rpc/dex-trades-curated/expansion-replay/apply` -> `rpc_dex_trades_curated_expansion_replay_apply` [ admin] -> `replay_and_insert_dex_trades_curated_expansion_raw_provenance`
- `GET /rpc/dex-trades-amount-decode-metadata-repair-plan` -> `rpc_dex_trades_amount_decode_metadata_repair_plan` [ admin] -> `get_dex_trades_amount_decode_metadata_repair_plan`
- `POST /rpc/dex-trades-amount-decode-metadata-repair-plan` -> `rpc_dex_trades_amount_decode_metadata_repair_plan` [ admin] -> `get_dex_trades_amount_decode_metadata_repair_plan`
- `POST /rpc/dex-trades-amount-decode-metadata-repair` -> `rpc_dex_trades_amount_decode_metadata_repair` [ admin] -> `repair_dex_trades_amount_decode_token_metadata`
- `POST /rpc/amount-usd-stablecoin-side-recompute/apply` -> `rpc_amount_usd_stablecoin_side_recompute_apply` [ admin] -> `apply_amount_usd_stablecoin_side_recompute`
- `POST /rpc/token-market-discovery-candidate-schema` -> `rpc_token_market_discovery_candidate_schema` [ admin] -> `get_token_market_discovery_candidate_schema`
- `POST /rpc/token-market-discovery-candidates-schema-plan` -> `rpc_token_market_discovery_candidates_schema_plan` [ admin] -> `get_token_market_discovery_candidates_schema_plan`
- `POST /rpc/token-market-discovery-candidates/create` -> `rpc_create_token_market_discovery_candidates` [ admin] -> `create_token_market_discovery_candidates`
- `POST /rpc/token-market-manual-candidates/insert` -> `rpc_insert_token_market_manual_candidates` [ admin] -> `insert_token_market_manual_candidates`
- `POST /rpc/token-market-discovery-candidates/insert` -> `rpc_insert_token_market_discovery_candidate` [ admin] -> `insert_token_market_discovery_candidate`
- `POST /rpc/token-market-discovery-candidates/review-queue` -> `rpc_token_market_discovery_candidate_review_queue` [ admin] -> `get_token_market_discovery_candidate_review_queue`
- `GET /rpc/token-market-policy-engine/shadow-evaluation` -> `rpc_token_market_policy_engine_shadow_evaluation` [ admin] -> `get_token_market_policy_engine_shadow_evaluation`
- `POST /rpc/token-market-policy-engine/shadow-evaluation` -> `rpc_token_market_policy_engine_shadow_evaluation` [ admin] -> `get_token_market_policy_engine_shadow_evaluation`
- `GET /rpc/token-market-router-exclusion-shadow-scoring` -> `rpc_token_market_router_exclusion_shadow_scoring` [ admin] -> `get_token_market_router_exclusion_shadow_scoring`
- `POST /rpc/token-market-router-exclusion-shadow-scoring` -> `rpc_token_market_router_exclusion_shadow_scoring` [ admin] -> `get_token_market_router_exclusion_shadow_scoring`
- `GET /rpc/token-market-local-candidate-source-repair-plan` -> `rpc_token_market_local_candidate_source_repair_plan` [ admin] -> `get_token_market_local_candidate_source_repair_plan`
- `POST /rpc/token-market-local-candidate-source-repair-plan` -> `rpc_token_market_local_candidate_source_repair_plan` [ admin] -> `get_token_market_local_candidate_source_repair_plan`
- `GET /rpc/token-market-local-candidate-source-venue-evidence` -> `rpc_token_market_local_candidate_source_venue_evidence` [ admin] -> `get_token_market_local_candidate_source_venue_evidence`
- `POST /rpc/token-market-local-candidate-source-venue-evidence` -> `rpc_token_market_local_candidate_source_venue_evidence` [ admin] -> `get_token_market_local_candidate_source_venue_evidence`
- `GET /rpc/token-market-local-candidate-official-source-proof-plan` -> `rpc_token_market_local_candidate_official_source_proof_plan` [ admin] -> `get_token_market_local_candidate_official_source_proof_plan`
- `POST /rpc/token-market-local-candidate-official-source-proof-plan` -> `rpc_token_market_local_candidate_official_source_proof_plan` [ admin] -> `get_token_market_local_candidate_official_source_proof_plan`
- `GET /rpc/token-market-local-universe-audit` -> `rpc_token_market_local_universe_audit` [ admin] -> `get_token_market_local_universe_audit`
- `POST /rpc/token-market-local-universe-audit` -> `rpc_token_market_local_universe_audit` [ admin] -> `get_token_market_local_universe_audit`
- `GET /rpc/token-market-data-coverage-expansion-plan` -> `rpc_token_market_data_coverage_expansion_plan` [ admin] -> `get_token_market_data_coverage_expansion_plan`
- `POST /rpc/token-market-data-coverage-expansion-plan` -> `rpc_token_market_data_coverage_expansion_plan` [ admin] -> `get_token_market_data_coverage_expansion_plan`
- `GET /rpc/token-market-top-research-lead-drilldown` -> `rpc_token_market_top_research_lead_drilldown` [ admin] -> `get_token_market_top_research_lead_drilldown`
- `POST /rpc/token-market-top-research-lead-drilldown` -> `rpc_token_market_top_research_lead_drilldown` [ admin] -> `get_token_market_top_research_lead_drilldown`
- `GET /rpc/token-market-top-research-lead-source-venue-repair-plan` -> `rpc_token_market_top_research_lead_source_venue_repair_plan` [ admin] -> `get_token_market_top_research_lead_source_venue_repair_plan`
- `POST /rpc/token-market-top-research-lead-source-venue-repair-plan` -> `rpc_token_market_top_research_lead_source_venue_repair_plan` [ admin] -> `get_token_market_top_research_lead_source_venue_repair_plan`
- `GET /rpc/token-market-top-research-lead-source-venue-proof-acquisition-plan` -> `rpc_token_market_top_research_lead_source_venue_proof_acquisition_plan` [ admin] -> `get_token_market_top_research_lead_source_venue_proof_acquisition_plan`
- `POST /rpc/token-market-top-research-lead-source-venue-proof-acquisition-plan` -> `rpc_token_market_top_research_lead_source_venue_proof_acquisition_plan` [ admin] -> `get_token_market_top_research_lead_source_venue_proof_acquisition_plan`
- `GET /rpc/token-market-top-research-lead-unknown-router-identity-drilldown` -> `rpc_token_market_top_research_lead_unknown_router_identity_drilldown` [ admin] -> `get_token_market_top_research_lead_unknown_router_identity_drilldown`
- `POST /rpc/token-market-top-research-lead-unknown-router-identity-drilldown` -> `rpc_token_market_top_research_lead_unknown_router_identity_drilldown` [ admin] -> `get_token_market_top_research_lead_unknown_router_identity_drilldown`
- `GET /rpc/token-market-top-research-lead-router-source-route-repair-plan` -> `rpc_token_market_top_research_lead_router_source_route_repair_plan` [ admin] -> `get_token_market_top_research_lead_router_source_route_repair_plan`
- `POST /rpc/token-market-top-research-lead-router-source-route-repair-plan` -> `rpc_token_market_top_research_lead_router_source_route_repair_plan` [ admin] -> `get_token_market_top_research_lead_router_source_route_repair_plan`
- `GET /rpc/token-market-top-research-lead-router-role-checkpoint` -> `rpc_token_market_top_research_lead_router_role_checkpoint` [ admin] -> `get_token_market_top_research_lead_router_role_checkpoint`
- `POST /rpc/token-market-top-research-lead-router-role-checkpoint` -> `rpc_token_market_top_research_lead_router_role_checkpoint` [ admin] -> `get_token_market_top_research_lead_router_role_checkpoint`
- `GET /rpc/token-market-top-research-lead-route-trace-sample-plan` -> `rpc_token_market_top_research_lead_route_trace_sample_plan` [ admin] -> `get_token_market_top_research_lead_route_trace_sample_plan`
- `POST /rpc/token-market-top-research-lead-route-trace-sample-plan` -> `rpc_token_market_top_research_lead_route_trace_sample_plan` [ admin] -> `get_token_market_top_research_lead_route_trace_sample_plan`
- `GET /rpc/token-market-top-research-lead-bounded-route-trace-preview` -> `rpc_token_market_top_research_lead_bounded_route_trace_preview` [ admin] -> `get_token_market_top_research_lead_bounded_route_trace_preview`
- `POST /rpc/token-market-top-research-lead-bounded-route-trace-preview` -> `rpc_token_market_top_research_lead_bounded_route_trace_preview` [ admin] -> `get_token_market_top_research_lead_bounded_route_trace_preview`
- `GET /rpc/token-market-top-research-lead-bounded-route-trace-execution` -> `rpc_token_market_top_research_lead_bounded_route_trace_execution` [ admin] -> `run_token_market_top_research_lead_bounded_route_trace_execution`
- `POST /rpc/token-market-top-research-lead-bounded-route-trace-execution` -> `rpc_token_market_top_research_lead_bounded_route_trace_execution` [ admin] -> `run_token_market_top_research_lead_bounded_route_trace_execution`
- `GET /rpc/token-market-top-research-lead-trace-source-repair-plan` -> `rpc_token_market_top_research_lead_trace_source_repair_plan` [ admin] -> `get_token_market_top_research_lead_trace_source_repair_plan`
- `POST /rpc/token-market-top-research-lead-trace-source-repair-plan` -> `rpc_token_market_top_research_lead_trace_source_repair_plan` [ admin] -> `get_token_market_top_research_lead_trace_source_repair_plan`
- `POST /rpc/token-market-fresh-forward-bsc-collection-trace` -> `rpc_token_market_fresh_forward_bsc_collection_trace` [ admin] -> `run_token_market_fresh_forward_bsc_collection_trace`
- `GET /rpc/token-market-recent-router-pool-evidence-review` -> `rpc_token_market_recent_router_pool_evidence_review` [ admin] -> `get_token_market_recent_router_pool_evidence_review`
- `POST /rpc/token-market-recent-router-pool-evidence-review` -> `rpc_token_market_recent_router_pool_evidence_review` [ admin] -> `get_token_market_recent_router_pool_evidence_review`
- `GET /rpc/token-market-metadata-aware-fresh-lead-ranking` -> `rpc_token_market_metadata_aware_fresh_lead_ranking` [ admin] -> `get_token_market_metadata_aware_fresh_lead_ranking`
- `POST /rpc/token-market-metadata-aware-fresh-lead-ranking` -> `rpc_token_market_metadata_aware_fresh_lead_ranking` [ admin] -> `get_token_market_metadata_aware_fresh_lead_ranking`
- `GET /rpc/token-market-recent-unknown-router-source-repair-plan` -> `rpc_token_market_recent_unknown_router_source_repair_plan` [ admin] -> `get_token_market_recent_unknown_router_source_repair_plan`
- `POST /rpc/token-market-recent-unknown-router-source-repair-plan` -> `rpc_token_market_recent_unknown_router_source_repair_plan` [ admin] -> `get_token_market_recent_unknown_router_source_repair_plan`
- `GET /rpc/token-market-top-unknown-router-source-trace-plan` -> `rpc_token_market_top_unknown_router_source_trace_plan` [ admin] -> `get_token_market_top_unknown_router_source_trace_plan`
- `POST /rpc/token-market-top-unknown-router-source-trace-plan` -> `rpc_token_market_top_unknown_router_source_trace_plan` [ admin] -> `get_token_market_top_unknown_router_source_trace_plan`
- `GET /rpc/token-market-top-unknown-router-bounded-history-collection-plan` -> `rpc_token_market_top_unknown_router_bounded_history_collection_plan` [ admin] -> `get_token_market_top_unknown_router_bounded_history_collection_plan`
- `POST /rpc/token-market-top-unknown-router-bounded-history-collection-plan` -> `rpc_token_market_top_unknown_router_bounded_history_collection_plan` [ admin] -> `get_token_market_top_unknown_router_bounded_history_collection_plan`
- `POST /rpc/token-market-top-unknown-router-bounded-history-collection` -> `rpc_token_market_top_unknown_router_bounded_history_collection` [ admin] -> `run_token_market_top_unknown_router_bounded_history_collection`
- `GET /rpc/token-market-top-research-lead-bounded-history-collection-plan` -> `rpc_token_market_top_research_lead_bounded_history_collection_plan` [ admin] -> `get_token_market_top_research_lead_bounded_history_collection_plan`
- `POST /rpc/token-market-top-research-lead-bounded-history-collection-plan` -> `rpc_token_market_top_research_lead_bounded_history_collection_plan` [ admin] -> `get_token_market_top_research_lead_bounded_history_collection_plan`
- `POST /rpc/token-market-top-research-lead-bounded-history-collection` -> `rpc_token_market_top_research_lead_bounded_history_collection` [ admin] -> `run_token_market_top_research_lead_bounded_history_collection`
- `GET /rpc/autonomous-alpha-detection-fusion-policy` -> `rpc_autonomous_alpha_detection_fusion_policy` [ admin] -> `get_autonomous_alpha_detection_fusion_policy`
- `POST /rpc/autonomous-alpha-detection-fusion-policy` -> `rpc_autonomous_alpha_detection_fusion_policy` [ admin] -> `get_autonomous_alpha_detection_fusion_policy`
- `GET /rpc/label-quality-repair-policy` -> `rpc_label_quality_repair_policy` [ admin] -> `get_label_quality_repair_policy`
- `POST /rpc/label-quality-repair-policy` -> `rpc_label_quality_repair_policy` [ admin] -> `get_label_quality_repair_policy`
- `GET /rpc/label-source-gap-repair-preview` -> `rpc_label_source_gap_repair_preview` [ admin] -> `get_label_source_gap_repair_preview`
- `POST /rpc/label-source-gap-repair-preview` -> `rpc_label_source_gap_repair_preview` [ admin] -> `get_label_source_gap_repair_preview`
- `POST /rpc/label-source-gap-repair/stage` -> `rpc_stage_label_source_gap_repair_candidates` [ admin] -> `stage_label_source_gap_repair_candidates`
- `GET /rpc/label-source-gap-repair/candidate-review` -> `rpc_label_source_gap_candidate_review_queue` [ admin] -> `get_label_source_gap_candidate_review_queue`
- `POST /rpc/label-source-gap-repair/candidate-review` -> `rpc_label_source_gap_candidate_review_queue` [ admin] -> `get_label_source_gap_candidate_review_queue`
- `GET /rpc/label-source-gap-repair/corroboration-preview` -> `rpc_label_source_gap_candidate_corroboration_preview` [ admin] -> `get_label_source_gap_candidate_corroboration_preview`
- `POST /rpc/label-source-gap-repair/corroboration-preview` -> `rpc_label_source_gap_candidate_corroboration_preview` [ admin] -> `get_label_source_gap_candidate_corroboration_preview`
- `GET /rpc/label-source-gap-repair/source-repair-plan` -> `rpc_label_source_gap_source_repair_plan` [ admin] -> `get_label_source_gap_source_repair_plan`
- `POST /rpc/label-source-gap-repair/source-repair-plan` -> `rpc_label_source_gap_source_repair_plan` [ admin] -> `get_label_source_gap_source_repair_plan`
- `GET /rpc/label-source-gap-repair/weak-source-repair-queue` -> `rpc_label_source_gap_weak_source_repair_queue` [ admin] -> `get_label_source_gap_weak_source_repair_queue`
- `POST /rpc/label-source-gap-repair/weak-source-repair-queue` -> `rpc_label_source_gap_weak_source_repair_queue` [ admin] -> `get_label_source_gap_weak_source_repair_queue`
- `POST /rpc/label-source-gap-repair/weak-source-corroboration-dry-run` -> `rpc_label_source_gap_weak_source_corroboration_dry_run` [ admin] -> `run_label_source_gap_weak_source_corroboration_dry_run`
- `POST /rpc/label-source-gap-repair/source-replacement-intake-preview` -> `rpc_label_source_gap_source_replacement_intake_preview` [ admin] -> `get_label_source_gap_source_replacement_intake_preview`
- `GET /rpc/label-source-gap-repair/alternative-source-discovery-radar` -> `rpc_label_source_gap_alternative_source_discovery_radar` [ admin] -> `get_label_source_gap_alternative_source_discovery_radar`
- `POST /rpc/label-source-gap-repair/alternative-source-discovery-radar` -> `rpc_label_source_gap_alternative_source_discovery_radar` [ admin] -> `get_label_source_gap_alternative_source_discovery_radar`
- `GET /rpc/label-source-gap-repair/source-url-probe-contract` -> `rpc_label_source_gap_source_url_probe_contract` [ admin] -> `get_label_source_gap_source_url_probe_contract`
- `POST /rpc/label-source-gap-repair/source-url-probe-contract` -> `rpc_label_source_gap_source_url_probe_contract` [ admin] -> `get_label_source_gap_source_url_probe_contract`
- `POST /rpc/label-source-gap-repair/source-url-probe-dry-run` -> `rpc_label_source_gap_source_url_probe_dry_run` [ admin] -> `run_label_source_gap_source_url_probe_dry_run`
- `GET /rpc/label-source-gap-repair/source-proof-grading-checkpoint` -> `rpc_label_source_gap_source_proof_grading_checkpoint` [ admin] -> `get_label_source_gap_source_proof_grading_checkpoint`
- `POST /rpc/label-source-gap-repair/source-proof-grading-checkpoint` -> `rpc_label_source_gap_source_proof_grading_checkpoint` [ admin] -> `get_label_source_gap_source_proof_grading_checkpoint`
- `POST /rpc/label-source-gap-repair/source-replacement-evidence/apply` -> `rpc_persist_label_source_gap_source_replacement_evidence` [ admin] -> `persist_label_source_gap_source_replacement_evidence`
- `GET /rpc/label-source-gap-repair/second-source-checkpoint` -> `rpc_label_source_gap_second_source_checkpoint` [ admin] -> `get_label_source_gap_second_source_checkpoint`
- `POST /rpc/label-source-gap-repair/second-source-checkpoint` -> `rpc_label_source_gap_second_source_checkpoint` [ admin] -> `get_label_source_gap_second_source_checkpoint`
- `GET /rpc/label-source-gap-repair/stronger-source-plan` -> `rpc_label_source_gap_stronger_source_plan` [ admin] -> `get_label_source_gap_stronger_source_plan`
- `POST /rpc/label-source-gap-repair/stronger-source-plan` -> `rpc_label_source_gap_stronger_source_plan` [ admin] -> `get_label_source_gap_stronger_source_plan`
- `GET /rpc/label-source-gap-repair/arkham-structured-source-intake-contract` -> `rpc_label_source_gap_arkham_structured_source_intake_contract` [ admin] -> `get_label_source_gap_arkham_structured_source_intake_contract`
- `POST /rpc/label-source-gap-repair/arkham-structured-source-intake-contract` -> `rpc_label_source_gap_arkham_structured_source_intake_contract` [ admin] -> `get_label_source_gap_arkham_structured_source_intake_contract`
- `GET /rpc/label-source-gap-repair/arkham-structured-source-acquisition-plan` -> `rpc_label_source_gap_arkham_structured_source_acquisition_plan` [ admin] -> `get_label_source_gap_arkham_structured_source_acquisition_plan`
- `POST /rpc/label-source-gap-repair/arkham-structured-source-acquisition-plan` -> `rpc_label_source_gap_arkham_structured_source_acquisition_plan` [ admin] -> `get_label_source_gap_arkham_structured_source_acquisition_plan`
- `GET /rpc/label-source-gap-repair/arkham-structured-manual-export-intake-preview` -> `rpc_label_source_gap_arkham_structured_manual_export_intake_preview` [ admin] -> `get_label_source_gap_arkham_structured_manual_export_intake_preview`
- `POST /rpc/label-source-gap-repair/arkham-structured-manual-export-intake-preview` -> `rpc_label_source_gap_arkham_structured_manual_export_intake_preview` [ admin] -> `get_label_source_gap_arkham_structured_manual_export_intake_preview`
- `GET /rpc/label-source-gap-repair/arkham-scrapling-snapshot-research-plan` -> `rpc_label_source_gap_arkham_scrapling_snapshot_research_plan` [ admin] -> `get_label_source_gap_arkham_scrapling_snapshot_research_plan`
- `POST /rpc/label-source-gap-repair/arkham-scrapling-snapshot-research-plan` -> `rpc_label_source_gap_arkham_scrapling_snapshot_research_plan` [ admin] -> `get_label_source_gap_arkham_scrapling_snapshot_research_plan`
- `GET /rpc/arkham-methodology-mirror` -> `rpc_arkham_methodology_mirror` [ admin] -> `get_arkham_methodology_mirror`
- `POST /rpc/arkham-methodology-mirror` -> `rpc_arkham_methodology_mirror` [ admin] -> `get_arkham_methodology_mirror`
- `GET /rpc/local-wallet-entity-graph-reconstruction-plan` -> `rpc_local_wallet_entity_graph_reconstruction_plan` [ admin] -> `get_local_wallet_entity_graph_reconstruction_plan`
- `POST /rpc/local-wallet-entity-graph-reconstruction-plan` -> `rpc_local_wallet_entity_graph_reconstruction_plan` [ admin] -> `get_local_wallet_entity_graph_reconstruction_plan`
- `GET /rpc/adaptive-wallet-entity-graph-collection-contract` -> `rpc_adaptive_wallet_entity_graph_collection_contract` [ admin] -> `get_adaptive_wallet_entity_graph_collection_contract`
- `POST /rpc/adaptive-wallet-entity-graph-collection-contract` -> `rpc_adaptive_wallet_entity_graph_collection_contract` [ admin] -> `get_adaptive_wallet_entity_graph_collection_contract`
- `GET /rpc/adaptive-wallet-entity-graph-collection-preview` -> `rpc_adaptive_wallet_entity_graph_collection_preview` [ admin] -> `get_adaptive_wallet_entity_graph_collection_preview`
- `POST /rpc/adaptive-wallet-entity-graph-collection-preview` -> `rpc_adaptive_wallet_entity_graph_collection_preview` [ admin] -> `get_adaptive_wallet_entity_graph_collection_preview`
- `POST /rpc/adaptive-wallet-entity-graph-collection` -> `rpc_adaptive_wallet_entity_graph_collection` [ admin] -> `run_adaptive_wallet_entity_graph_collection`
- `GET /rpc/label-source-gap-repair/source-corroboration-contract` -> `rpc_label_source_gap_source_corroboration_contract` [ admin] -> `get_label_source_gap_source_corroboration_contract`
- `POST /rpc/label-source-gap-repair/source-corroboration-contract` -> `rpc_label_source_gap_source_corroboration_contract` [ admin] -> `get_label_source_gap_source_corroboration_contract`
- `POST /rpc/label-source-gap-repair/source-corroboration-dry-run` -> `rpc_label_source_gap_source_corroboration_dry_run` [ admin] -> `run_label_source_gap_source_corroboration_dry_run`
- `POST /rpc/label-source-gap-repair/verified-evidence/apply` -> `rpc_persist_label_source_gap_verified_candidate_evidence` [ admin] -> `persist_label_source_gap_verified_candidate_evidence`
- `GET /rpc/label-source-gap-repair/source-application-preview` -> `rpc_label_source_gap_source_application_preview` [ admin] -> `get_label_source_gap_source_application_preview`
- `POST /rpc/label-source-gap-repair/source-application-preview` -> `rpc_label_source_gap_source_application_preview` [ admin] -> `get_label_source_gap_source_application_preview`
- `GET /rpc/label-source-gap-repair/local-observation-plan` -> `rpc_label_source_gap_local_observation_plan` [ admin] -> `get_label_source_gap_local_observation_plan`
- `POST /rpc/label-source-gap-repair/local-observation-plan` -> `rpc_label_source_gap_local_observation_plan` [ admin] -> `get_label_source_gap_local_observation_plan`
- `GET /rpc/label-source-gap-repair/local-observation-refresh-preview` -> `rpc_label_source_gap_local_observation_refresh_preview` [ admin] -> `get_label_source_gap_local_observation_refresh_preview`
- `POST /rpc/label-source-gap-repair/local-observation-refresh-preview` -> `rpc_label_source_gap_local_observation_refresh_preview` [ admin] -> `get_label_source_gap_local_observation_refresh_preview`
- `GET /rpc/label-source-gap-repair/local-observation-collection-plan` -> `rpc_label_source_gap_local_observation_collection_plan` [ admin] -> `get_label_source_gap_local_observation_collection_plan`
- `POST /rpc/label-source-gap-repair/local-observation-collection-plan` -> `rpc_label_source_gap_local_observation_collection_plan` [ admin] -> `get_label_source_gap_local_observation_collection_plan`
- `GET /rpc/label-source-gap-repair/local-observation-collection-contract` -> `rpc_label_source_gap_local_observation_collection_contract` [ admin] -> `get_label_source_gap_local_observation_collection_contract`
- `POST /rpc/label-source-gap-repair/local-observation-collection-contract` -> `rpc_label_source_gap_local_observation_collection_contract` [ admin] -> `get_label_source_gap_local_observation_collection_contract`
- `GET /rpc/label-source-gap-repair/local-observation-collection-preview` -> `rpc_label_source_gap_local_observation_collection_preview` [ admin] -> `get_label_source_gap_local_observation_collection_preview`
- `POST /rpc/label-source-gap-repair/local-observation-collection-preview` -> `rpc_label_source_gap_local_observation_collection_preview` [ admin] -> `get_label_source_gap_local_observation_collection_preview`
- `GET /rpc/label-source-gap-repair/local-observation-post-collection-review-contract` -> `rpc_label_source_gap_local_observation_post_collection_review_contract` [ admin] -> `get_label_source_gap_local_observation_post_collection_review_contract`
- `POST /rpc/label-source-gap-repair/local-observation-post-collection-review-contract` -> `rpc_label_source_gap_local_observation_post_collection_review_contract` [ admin] -> `get_label_source_gap_local_observation_post_collection_review_contract`
- `POST /rpc/label-source-gap-repair/local-observation-collection/collect` -> `rpc_collect_label_source_gap_local_observations` [ admin] -> `collect_label_source_gap_local_observations`
- `GET /rpc/label-source-gap-repair/local-observation-apply-preview` -> `rpc_label_source_gap_local_observation_apply_preview` [ admin] -> `get_label_source_gap_local_observation_apply_preview`
- `POST /rpc/label-source-gap-repair/local-observation-apply-preview` -> `rpc_label_source_gap_local_observation_apply_preview` [ admin] -> `get_label_source_gap_local_observation_apply_preview`
- `POST /rpc/label-source-gap-repair/local-observation-apply` -> `rpc_apply_label_source_gap_local_observations` [ admin] -> `apply_label_source_gap_local_observations`
- `POST /rpc/token-market-discovery-candidates/evidence-intake-preview` -> `rpc_token_market_discovery_candidate_evidence_intake_preview` [ admin] -> `get_token_market_discovery_candidate_evidence_intake_preview`
- `POST /rpc/token-market-discovery-evidence-queue-schema-plan` -> `rpc_token_market_discovery_evidence_queue_schema_plan` [ admin] -> `get_token_market_discovery_evidence_queue_schema_plan`
- `POST /rpc/token-market-discovery-evidence-queue/create` -> `rpc_create_token_market_discovery_evidence_queue` [ admin] -> `create_token_market_discovery_evidence_queue`
- `POST /rpc/token-market-discovery-evidence/insert` -> `rpc_insert_token_market_discovery_evidence` [ admin] -> `insert_token_market_discovery_evidence`
- `POST /rpc/token-market-discovery-evidence/review-queue` -> `rpc_token_market_discovery_evidence_review_queue` [ admin] -> `get_token_market_discovery_evidence_review_queue`
- `POST /rpc/token-market-discovery-evidence/human-decision-preview` -> `rpc_token_market_discovery_evidence_human_decision_preview` [ admin] -> `get_token_market_discovery_evidence_human_decision_preview`
- `POST /rpc/token-market-discovery-evidence/human-decision/apply` -> `rpc_apply_token_market_discovery_evidence_human_decision` [ admin] -> `apply_token_market_discovery_evidence_human_decision`
- `POST /rpc/token-market-discovery-evidence/controlled-promotion-preview` -> `rpc_token_market_discovery_evidence_controlled_promotion_preview` [ admin] -> `get_token_market_discovery_evidence_controlled_promotion_preview`
- `POST /rpc/token-market-discovery-evidence/controlled-promotion-insert-contract` -> `rpc_token_market_discovery_evidence_controlled_promotion_insert_contract` [ admin] -> `get_token_market_discovery_evidence_controlled_promotion_insert_contract`
- `POST /rpc/token-market-controlled-promotion-queue-schema-plan` -> `rpc_token_market_controlled_promotion_queue_schema_plan` [ admin] -> `get_token_market_controlled_promotion_queue_schema_plan`
- `POST /rpc/token-market-controlled-promotion-queue/create` -> `rpc_create_token_market_controlled_promotion_queue` [ admin] -> `create_token_market_controlled_promotion_queue`
- `POST /rpc/token-market-controlled-promotion-queue/insert` -> `rpc_insert_token_market_controlled_promotion` [ admin] -> `insert_token_market_controlled_promotion`
- `POST /rpc/token-market-controlled-promotion-queue/review` -> `rpc_token_market_controlled_promotion_queue_review` [ admin] -> `get_token_market_controlled_promotion_queue_review`
- `POST /rpc/token-market-controlled-promotion-queue/decision-preview` -> `rpc_token_market_controlled_promotion_decision_preview` [ admin] -> `get_token_market_controlled_promotion_decision_preview`
- `POST /rpc/token-market-controlled-promotion-queue/decision/apply` -> `rpc_apply_token_market_controlled_promotion_decision` [ admin] -> `apply_token_market_controlled_promotion_decision`
- `POST /rpc/token-market-controlled-promotion-queue/downstream-insert-contract` -> `rpc_token_market_controlled_promotion_downstream_insert_contract` [ admin] -> `get_token_market_controlled_promotion_downstream_insert_contract`
- `POST /rpc/token-market-downstream-promotion-queue-schema-plan` -> `rpc_token_market_downstream_promotion_queue_schema_plan` [ admin] -> `get_token_market_downstream_promotion_queue_schema_plan`
- `POST /rpc/token-market-downstream-promotion-queue/create` -> `rpc_token_market_downstream_promotion_queue_create` [ admin] -> `create_token_market_downstream_promotion_queue`
- `POST /rpc/token-market-downstream-promotion-queue/insert` -> `rpc_token_market_downstream_promotion_queue_insert` [ admin] -> `insert_token_market_downstream_promotion`
- `POST /rpc/token-market-downstream-promotion-queue/review` -> `rpc_token_market_downstream_promotion_queue_review` [ admin] -> `get_token_market_downstream_promotion_queue_review`
- `POST /rpc/token-market-downstream-promotion-queue/decision-preview` -> `rpc_token_market_downstream_promotion_decision_preview` [ admin] -> `get_token_market_downstream_promotion_decision_preview`
- `POST /rpc/token-market-downstream-promotion-queue/decision/apply` -> `rpc_token_market_downstream_promotion_decision_apply` [ admin] -> `apply_token_market_downstream_promotion_decision`
- `POST /rpc/token-market-downstream-promotion-queue/business-insert-contract` -> `rpc_token_market_downstream_business_insert_contract` [ admin] -> `get_token_market_downstream_business_insert_contract`
- `POST /rpc/token-market-downstream-business-handoff-queue-schema-plan` -> `rpc_token_market_downstream_business_handoff_queue_schema_plan` [ admin] -> `get_token_market_downstream_business_handoff_queue_schema_plan`
- `POST /rpc/token-market-downstream-business-handoff-queue/create` -> `rpc_token_market_downstream_business_handoff_queue_create` [ admin] -> `create_token_market_downstream_business_handoff_queue`
- `POST /rpc/token-market-downstream-business-handoff-queue/insert` -> `rpc_token_market_downstream_business_handoff_queue_insert` [ admin] -> `insert_token_market_downstream_business_handoff`
- `POST /rpc/token-market-downstream-business-handoff-queue/review` -> `rpc_token_market_downstream_business_handoff_queue_review` [ admin] -> `get_token_market_downstream_business_handoff_queue_review`
- `POST /rpc/token-market-downstream-business-handoff-queue/decision-preview` -> `rpc_token_market_downstream_business_handoff_queue_decision_preview` [ admin] -> `get_token_market_downstream_business_handoff_decision_preview`
- `POST /rpc/token-market-downstream-business-handoff-queue/decision/apply` -> `rpc_token_market_downstream_business_handoff_queue_decision_apply` [ admin] -> `apply_token_market_downstream_business_handoff_decision`
- `POST /rpc/token-market-downstream-business-handoff-queue/business-insert-contract` -> `rpc_token_market_downstream_business_handoff_queue_business_insert_contract` [ admin] -> `get_token_market_downstream_business_handoff_business_insert_contract`
- `POST /rpc/token-market-business-insert-queue-schema-plan` -> `rpc_token_market_business_insert_queue_schema_plan` [ admin] -> `get_token_market_business_insert_queue_schema_plan`
- `POST /rpc/token-market-business-insert-queue/create` -> `rpc_token_market_business_insert_queue_create` [ admin] -> `create_token_market_business_insert_queue`
- `POST /rpc/token-market-business-insert-queue/insert` -> `rpc_token_market_business_insert_queue_insert` [ admin] -> `insert_token_market_business_insert`
- `POST /rpc/token-market-business-insert-queue/review` -> `rpc_token_market_business_insert_queue_review` [ admin] -> `get_token_market_business_insert_queue_review`
- `POST /rpc/token-market-business-insert-queue/decision-preview` -> `rpc_token_market_business_insert_queue_decision_preview` [ admin] -> `get_token_market_business_insert_decision_preview`
- `POST /rpc/token-market-business-insert-queue/decision/apply` -> `rpc_token_market_business_insert_queue_decision_apply` [ admin] -> `apply_token_market_business_insert_decision`
- `POST /rpc/token-market-business-insert-queue/business-execution-contract` -> `rpc_token_market_business_insert_queue_business_execution_contract` [ admin] -> `get_token_market_business_execution_contract`
- `POST /rpc/token-market-business-execution-queue-schema-plan` -> `rpc_token_market_business_execution_queue_schema_plan` [ admin] -> `get_token_market_business_execution_queue_schema_plan`
- `POST /rpc/token-market-business-execution-queue/create` -> `rpc_token_market_business_execution_queue_create` [ admin] -> `create_token_market_business_execution_queue`
- `POST /rpc/token-market-business-execution-queue/insert` -> `rpc_token_market_business_execution_queue_insert` [ admin] -> `insert_token_market_business_execution`
- `POST /rpc/token-market-business-execution-queue/review` -> `rpc_token_market_business_execution_queue_review` [ admin] -> `get_token_market_business_execution_queue_review`
- `POST /rpc/token-market-business-execution-queue/decision-preview` -> `rpc_token_market_business_execution_queue_decision_preview` [ admin] -> `get_token_market_business_execution_decision_preview`
- `POST /rpc/token-market-business-execution-queue/decision/apply` -> `rpc_token_market_business_execution_queue_decision_apply` [ admin] -> `apply_token_market_business_execution_decision`
- `POST /rpc/token-market-business-execution-queue/business-apply-contract` -> `rpc_token_market_business_execution_queue_business_apply_contract` [ admin] -> `get_token_market_business_apply_contract`
- `POST /rpc/token-market-business-apply-queue-schema-plan` -> `rpc_token_market_business_apply_queue_schema_plan` [ admin] -> `get_token_market_business_apply_queue_schema_plan`
- `POST /rpc/token-market-business-apply-queue/create` -> `rpc_token_market_business_apply_queue_create` [ admin] -> `create_token_market_business_apply_queue`
- `POST /rpc/token-market-business-apply-queue/insert` -> `rpc_token_market_business_apply_queue_insert` [ admin] -> `insert_token_market_business_apply`
- `POST /rpc/token-market-business-apply-queue/review` -> `rpc_token_market_business_apply_queue_review` [ admin] -> `get_token_market_business_apply_queue_review`
- `POST /rpc/token-market-business-apply-queue/decision-preview` -> `rpc_token_market_business_apply_queue_decision_preview` [ admin] -> `get_token_market_business_apply_decision_preview`
- `POST /rpc/token-market-business-apply-queue/decision/apply` -> `rpc_token_market_business_apply_queue_decision_apply` [ admin] -> `apply_token_market_business_apply_decision`
- `POST /rpc/token-market-business-apply-queue/post-apply-contract` -> `rpc_token_market_business_apply_queue_post_apply_contract` [ admin] -> `get_token_market_business_post_apply_contract`
- `POST /rpc/token-market-post-apply-queue-schema-plan` -> `rpc_token_market_post_apply_queue_schema_plan` [ admin] -> `get_token_market_post_apply_queue_schema_plan`
- `POST /rpc/token-market-post-apply-queue/create` -> `rpc_token_market_post_apply_queue_create` [ admin] -> `create_token_market_post_apply_queue`
- `POST /rpc/token-market-post-apply-queue/insert` -> `rpc_token_market_post_apply_queue_insert` [ admin] -> `insert_token_market_post_apply`
- `POST /rpc/token-market-post-apply-queue/review` -> `rpc_token_market_post_apply_queue_review` [ admin] -> `get_token_market_post_apply_queue_review`
- `POST /rpc/token-market-post-apply-queue/decision-preview` -> `rpc_token_market_post_apply_queue_decision_preview` [ admin] -> `get_token_market_post_apply_decision_preview`
- `POST /rpc/token-market-post-apply-queue/decision/apply` -> `rpc_token_market_post_apply_queue_decision_apply` [ admin] -> `apply_token_market_post_apply_decision`
- `POST /rpc/token-market-post-apply-queue/insert-contract` -> `rpc_token_market_post_apply_queue_insert_contract` [ admin] -> `get_token_market_post_apply_insert_contract`
- `POST /rpc/token-market-post-apply-insert-queue-schema-plan` -> `rpc_token_market_post_apply_insert_queue_schema_plan` [ admin] -> `get_token_market_post_apply_insert_queue_schema_plan`
- `POST /rpc/token-market-post-apply-insert-queue/create` -> `rpc_token_market_post_apply_insert_queue_create` [ admin] -> `create_token_market_post_apply_insert_queue`
- `POST /rpc/token-market-post-apply-insert-queue/insert` -> `rpc_token_market_post_apply_insert_queue_insert` [ admin] -> `insert_token_market_post_apply_insert`
- `POST /rpc/token-market-post-apply-insert-queue/review` -> `rpc_token_market_post_apply_insert_queue_review` [ admin] -> `get_token_market_post_apply_insert_queue_review`
- `POST /rpc/token-market-post-apply-insert-queue/decision-preview` -> `rpc_token_market_post_apply_insert_queue_decision_preview` [ admin] -> `get_token_market_post_apply_insert_decision_preview`
- `POST /rpc/token-market-post-apply-insert-queue/decision/apply` -> `rpc_token_market_post_apply_insert_queue_decision_apply` [ admin] -> `apply_token_market_post_apply_insert_decision`
- `POST /rpc/token-market-post-apply-insert-queue/post-apply-execution-contract` -> `rpc_token_market_post_apply_insert_queue_post_apply_execution_contract` [ admin] -> `get_token_market_post_apply_execution_contract`
- `POST /rpc/token-market-post-apply-execution-queue-schema-plan` -> `rpc_token_market_post_apply_execution_queue_schema_plan` [ admin] -> `get_token_market_post_apply_execution_queue_schema_plan`
- `POST /rpc/token-market-post-apply-execution-queue/create` -> `rpc_token_market_post_apply_execution_queue_create` [ admin] -> `create_token_market_post_apply_execution_queue`
- `POST /rpc/token-market-post-apply-execution-queue/insert` -> `rpc_token_market_post_apply_execution_queue_insert` [ admin] -> `insert_token_market_post_apply_execution`
- `POST /rpc/token-market-post-apply-execution-queue/review` -> `rpc_token_market_post_apply_execution_queue_review` [ admin] -> `get_token_market_post_apply_execution_queue_review`
- `POST /rpc/token-market-post-apply-execution-queue/decision-preview` -> `rpc_token_market_post_apply_execution_queue_decision_preview` [ admin] -> `get_token_market_post_apply_execution_decision_preview`
- `POST /rpc/token-market-post-apply-execution-queue/decision/apply` -> `rpc_token_market_post_apply_execution_queue_decision_apply` [ admin] -> `apply_token_market_post_apply_execution_decision`
- `POST /rpc/token-market-post-apply-execution-queue/apply-contract` -> `rpc_token_market_post_apply_execution_queue_apply_contract` [ admin] -> `get_token_market_post_apply_execution_apply_contract`
- `POST /rpc/token-market-post-apply-execution-apply-queue-schema-plan` -> `rpc_token_market_post_apply_execution_apply_queue_schema_plan` [ admin] -> `get_token_market_post_apply_execution_apply_queue_schema_plan`
- `POST /rpc/token-market-post-apply-execution-apply-queue/create` -> `rpc_create_token_market_post_apply_execution_apply_queue` [ admin] -> `create_token_market_post_apply_execution_apply_queue`
- `POST /rpc/token-market-post-apply-execution-apply-queue/insert` -> `rpc_insert_token_market_post_apply_execution_apply` [ admin] -> `insert_token_market_post_apply_execution_apply`
- `GET /rpc/token-market-post-apply-execution-apply-queue/review` -> `rpc_token_market_post_apply_execution_apply_queue_review` [ admin] -> `get_token_market_post_apply_execution_apply_queue_review`
- `POST /rpc/token-market-post-apply-execution-apply-queue/review` -> `rpc_token_market_post_apply_execution_apply_queue_review` [ admin] -> `get_token_market_post_apply_execution_apply_queue_review`
- `POST /rpc/token-market-post-apply-execution-apply-queue/decision-preview` -> `rpc_token_market_post_apply_execution_apply_queue_decision_preview` [ admin] -> `get_token_market_post_apply_execution_apply_decision_preview`
- `POST /rpc/token-market-post-apply-execution-apply-queue/decision/apply` -> `rpc_token_market_post_apply_execution_apply_queue_decision_apply` [ admin] -> `apply_token_market_post_apply_execution_apply_decision`
- `GET /rpc/token-market-post-apply-execution-apply-queue/final-apply-contract` -> `rpc_token_market_post_apply_execution_apply_queue_final_apply_contract` [ admin] -> `get_token_market_final_apply_contract`
- `POST /rpc/token-market-post-apply-execution-apply-queue/final-apply-contract` -> `rpc_token_market_post_apply_execution_apply_queue_final_apply_contract` [ admin] -> `get_token_market_final_apply_contract`
- `GET /rpc/token-market-final-apply-queue-schema-plan` -> `rpc_token_market_final_apply_queue_schema_plan` [ admin] -> `get_token_market_final_apply_queue_schema_plan`
- `POST /rpc/token-market-final-apply-queue-schema-plan` -> `rpc_token_market_final_apply_queue_schema_plan` [ admin] -> `get_token_market_final_apply_queue_schema_plan`
- `POST /rpc/token-market-final-apply-queue/create` -> `rpc_create_token_market_final_apply_queue` [ admin] -> `create_token_market_final_apply_queue`
- `POST /rpc/token-market-final-apply-queue/insert` -> `rpc_insert_token_market_final_apply` [ admin] -> `insert_token_market_final_apply`
- `GET /rpc/token-market-final-apply-queue/review` -> `rpc_token_market_final_apply_queue_review` [ admin] -> `get_token_market_final_apply_queue_review`
- `POST /rpc/token-market-final-apply-queue/review` -> `rpc_token_market_final_apply_queue_review` [ admin] -> `get_token_market_final_apply_queue_review`
- `POST /rpc/token-market-final-apply-queue/decision-preview` -> `rpc_token_market_final_apply_queue_decision_preview` [ admin] -> `get_token_market_final_apply_decision_preview`
- `POST /rpc/token-market-final-apply-queue/decision/apply` -> `rpc_token_market_final_apply_queue_decision_apply` [ admin] -> `apply_token_market_final_apply_decision`
- `GET /rpc/token-market-final-apply-queue/final-target-execution-contract` -> `rpc_token_market_final_apply_queue_final_target_execution_contract` [ admin] -> `get_token_market_final_target_execution_contract`
- `POST /rpc/token-market-final-apply-queue/final-target-execution-contract` -> `rpc_token_market_final_apply_queue_final_target_execution_contract` [ admin] -> `get_token_market_final_target_execution_contract`
- `GET /rpc/token-market-final-target-execution-queue-schema-plan` -> `rpc_token_market_final_target_execution_queue_schema_plan` [ admin] -> `get_token_market_final_target_execution_queue_schema_plan`
- `POST /rpc/token-market-final-target-execution-queue-schema-plan` -> `rpc_token_market_final_target_execution_queue_schema_plan` [ admin] -> `get_token_market_final_target_execution_queue_schema_plan`
- `POST /rpc/token-market-final-target-execution-queue/create` -> `rpc_create_token_market_final_target_execution_queue` [ admin] -> `create_token_market_final_target_execution_queue`
- `POST /rpc/token-market-final-target-execution-queue/insert` -> `rpc_insert_token_market_final_target_execution` [ admin] -> `insert_token_market_final_target_execution`
- `GET /rpc/token-market-final-target-execution-queue/review` -> `rpc_token_market_final_target_execution_queue_review` [ admin] -> `get_token_market_final_target_execution_queue_review`
- `POST /rpc/token-market-final-target-execution-queue/review` -> `rpc_token_market_final_target_execution_queue_review` [ admin] -> `get_token_market_final_target_execution_queue_review`
- `POST /rpc/token-market-final-target-execution-queue/decision-preview` -> `rpc_token_market_final_target_execution_queue_decision_preview` [ admin] -> `get_token_market_final_target_execution_decision_preview`
- `POST /rpc/token-market-final-target-execution-queue/decision/apply` -> `rpc_token_market_final_target_execution_queue_decision_apply` [ admin] -> `apply_token_market_final_target_execution_decision`
- `GET /rpc/token-market-final-target-execution-queue/handoff-contract` -> `rpc_token_market_final_target_execution_queue_handoff_contract` [ admin] -> `get_token_market_final_target_execution_handoff_contract`
- `POST /rpc/token-market-final-target-execution-queue/handoff-contract` -> `rpc_token_market_final_target_execution_queue_handoff_contract` [ admin] -> `get_token_market_final_target_execution_handoff_contract`
- `GET /rpc/token-market-final-handoff-queue-schema-plan` -> `rpc_token_market_final_handoff_queue_schema_plan` [ admin] -> `get_token_market_final_handoff_queue_schema_plan`
- `POST /rpc/token-market-final-handoff-queue-schema-plan` -> `rpc_token_market_final_handoff_queue_schema_plan` [ admin] -> `get_token_market_final_handoff_queue_schema_plan`
- `POST /rpc/token-market-final-handoff-queue/create` -> `rpc_create_token_market_final_handoff_queue` [ admin] -> `create_token_market_final_handoff_queue`
- `POST /rpc/token-market-final-handoff-queue/insert` -> `rpc_insert_token_market_final_handoff` [ admin] -> `insert_token_market_final_handoff`
- `GET /rpc/token-market-final-handoff-queue/review` -> `rpc_token_market_final_handoff_queue_review` [ admin] -> `get_token_market_final_handoff_queue_review`
- `POST /rpc/token-market-final-handoff-queue/review` -> `rpc_token_market_final_handoff_queue_review` [ admin] -> `get_token_market_final_handoff_queue_review`
- `POST /rpc/token-market-final-handoff-queue/decision-preview` -> `rpc_token_market_final_handoff_queue_decision_preview` [ admin] -> `get_token_market_final_handoff_decision_preview`
- `POST /rpc/token-market-final-handoff-queue/decision/apply` -> `rpc_token_market_final_handoff_queue_decision_apply` [ admin] -> `apply_token_market_final_handoff_decision`
- `GET /rpc/token-market-final-handoff-queue/target-contract` -> `rpc_token_market_final_handoff_queue_target_contract` [ admin] -> `get_token_market_final_handoff_target_contract`
- `POST /rpc/token-market-final-handoff-queue/target-contract` -> `rpc_token_market_final_handoff_queue_target_contract` [ admin] -> `get_token_market_final_handoff_target_contract`
- `GET /rpc/token-market-final-handoff-target-queue-schema-plan` -> `rpc_token_market_final_handoff_target_queue_schema_plan` [ admin] -> `get_token_market_final_handoff_target_queue_schema_plan`
- `POST /rpc/token-market-final-handoff-target-queue-schema-plan` -> `rpc_token_market_final_handoff_target_queue_schema_plan` [ admin] -> `get_token_market_final_handoff_target_queue_schema_plan`
- `POST /rpc/token-market-final-handoff-target-queue/create` -> `rpc_create_token_market_final_handoff_target_queue` [ admin] -> `create_token_market_final_handoff_target_queue`
- `POST /rpc/token-market-final-handoff-target-queue/insert` -> `rpc_insert_token_market_final_handoff_target` [ admin] -> `insert_token_market_final_handoff_target`
- `GET /rpc/token-market-final-handoff-target-queue/review` -> `rpc_token_market_final_handoff_target_queue_review` [ admin] -> `get_token_market_final_handoff_target_queue_review`
- `POST /rpc/token-market-final-handoff-target-queue/review` -> `rpc_token_market_final_handoff_target_queue_review` [ admin] -> `get_token_market_final_handoff_target_queue_review`
- `POST /rpc/token-market-final-handoff-target-queue/decision-preview` -> `rpc_token_market_final_handoff_target_queue_decision_preview` [ admin] -> `get_token_market_final_handoff_target_decision_preview`
- `POST /rpc/token-market-final-handoff-target-queue/decision/apply` -> `rpc_token_market_final_handoff_target_queue_decision_apply` [ admin] -> `apply_token_market_final_handoff_target_decision`
- `GET /rpc/token-market-final-handoff-target-queue/cex-review-handoff-contract` -> `rpc_token_market_final_handoff_target_queue_cex_review_handoff_contract` [ admin] -> `get_token_market_final_handoff_target_cex_review_handoff_contract`
- `POST /rpc/token-market-final-handoff-target-queue/cex-review-handoff-contract` -> `rpc_token_market_final_handoff_target_queue_cex_review_handoff_contract` [ admin] -> `get_token_market_final_handoff_target_cex_review_handoff_contract`
- `GET /rpc/cex-market-evidence-review-queue-schema-plan` -> `rpc_cex_market_evidence_review_queue_schema_plan` [ admin] -> `get_cex_market_evidence_review_queue_schema_plan`
- `POST /rpc/cex-market-evidence-review-queue-schema-plan` -> `rpc_cex_market_evidence_review_queue_schema_plan` [ admin] -> `get_cex_market_evidence_review_queue_schema_plan`
- `POST /rpc/cex-market-evidence-review-queue/create` -> `rpc_create_cex_market_evidence_review_queue` [ admin] -> `create_cex_market_evidence_review_queue`
- `POST /rpc/cex-market-evidence-review-queue/insert` -> `rpc_insert_cex_market_evidence_review` [ admin] -> `insert_cex_market_evidence_review`
- `GET /rpc/cex-market-evidence-review-queue/review` -> `rpc_cex_market_evidence_review_queue_review` [ admin] -> `get_cex_market_evidence_review_queue_review`
- `POST /rpc/cex-market-evidence-review-queue/review` -> `rpc_cex_market_evidence_review_queue_review` [ admin] -> `get_cex_market_evidence_review_queue_review`
- `POST /rpc/cex-market-evidence-review-queue/decision-preview` -> `rpc_cex_market_evidence_review_queue_decision_preview` [ admin] -> `get_cex_market_evidence_review_decision_preview`
- `POST /rpc/cex-market-evidence-review-queue/decision/apply` -> `rpc_cex_market_evidence_review_queue_decision_apply` [ admin] -> `apply_cex_market_evidence_review_decision`
- `GET /rpc/cex-market-evidence-review-queue/label-candidate-handoff-contract` -> `rpc_cex_market_evidence_review_queue_label_candidate_handoff_contract` [ admin] -> `get_cex_market_evidence_review_label_candidate_handoff_contract`
- `POST /rpc/cex-market-evidence-review-queue/label-candidate-handoff-contract` -> `rpc_cex_market_evidence_review_queue_label_candidate_handoff_contract` [ admin] -> `get_cex_market_evidence_review_label_candidate_handoff_contract`
- `GET /rpc/cex-label-candidate-review-queue-schema-plan` -> `rpc_cex_label_candidate_review_queue_schema_plan` [ admin] -> `get_cex_label_candidate_review_queue_schema_plan`
- `POST /rpc/cex-label-candidate-review-queue-schema-plan` -> `rpc_cex_label_candidate_review_queue_schema_plan` [ admin] -> `get_cex_label_candidate_review_queue_schema_plan`
- `POST /rpc/cex-label-candidate-review-queue/create` -> `rpc_create_cex_label_candidate_review_queue` [ admin] -> `create_cex_label_candidate_review_queue`
- `POST /rpc/cex-label-candidate-review-queue/insert` -> `rpc_insert_cex_label_candidate_review` [ admin] -> `insert_cex_label_candidate_review`
- `GET /rpc/cex-label-candidate-review-queue/review` -> `rpc_cex_label_candidate_review_queue_review` [ admin] -> `get_cex_label_candidate_review_queue_review`
- `POST /rpc/cex-label-candidate-review-queue/review` -> `rpc_cex_label_candidate_review_queue_review` [ admin] -> `get_cex_label_candidate_review_queue_review`
- `POST /rpc/cex-label-candidate-review-queue/decision-preview` -> `rpc_cex_label_candidate_review_queue_decision_preview` [ admin] -> `get_cex_label_candidate_review_decision_preview`
- `POST /rpc/cex-label-candidate-review-queue/decision/apply` -> `rpc_cex_label_candidate_review_queue_decision_apply` [ admin] -> `apply_cex_label_candidate_review_decision`
- `GET /rpc/cex-label-candidate-review-queue/label-creation-contract` -> `rpc_cex_label_candidate_review_queue_label_creation_contract` [ admin] -> `get_cex_label_creation_contract`
- `POST /rpc/cex-label-candidate-review-queue/label-creation-contract` -> `rpc_cex_label_candidate_review_queue_label_creation_contract` [ admin] -> `get_cex_label_creation_contract`
- `GET /rpc/cex-label-creation-queue-schema-plan` -> `rpc_cex_label_creation_queue_schema_plan` [ admin] -> `get_cex_label_creation_queue_schema_plan`
- `POST /rpc/cex-label-creation-queue-schema-plan` -> `rpc_cex_label_creation_queue_schema_plan` [ admin] -> `get_cex_label_creation_queue_schema_plan`
- `POST /rpc/cex-label-creation-review-queue/create` -> `rpc_create_cex_label_creation_review_queue` [ admin] -> `create_cex_label_creation_review_queue`
- `POST /rpc/cex-label-creation-review-queue/insert` -> `rpc_insert_cex_label_creation_review` [ admin] -> `insert_cex_label_creation_review`
- `GET /rpc/cex-label-creation-review-queue/review` -> `rpc_cex_label_creation_review_queue_review` [ admin] -> `get_cex_label_creation_review_queue_review`
- `POST /rpc/cex-label-creation-review-queue/review` -> `rpc_cex_label_creation_review_queue_review` [ admin] -> `get_cex_label_creation_review_queue_review`
- `POST /rpc/cex-label-creation-review-queue/decision-preview` -> `rpc_cex_label_creation_review_queue_decision_preview` [ admin] -> `get_cex_label_creation_review_decision_preview`
- `POST /rpc/cex-label-creation-review-queue/decision/apply` -> `rpc_cex_label_creation_review_queue_decision_apply` [ admin] -> `apply_cex_label_creation_review_decision`
- `GET /rpc/cex-label-creation-review-queue/final-label-write-contract` -> `rpc_cex_label_creation_review_queue_final_label_write_contract` [ admin] -> `get_cex_final_label_write_contract`
- `POST /rpc/cex-label-creation-review-queue/final-label-write-contract` -> `rpc_cex_label_creation_review_queue_final_label_write_contract` [ admin] -> `get_cex_final_label_write_contract`
- `GET /rpc/cex-final-label-write-queue-schema-plan` -> `rpc_cex_final_label_write_queue_schema_plan` [ admin] -> `get_cex_final_label_write_queue_schema_plan`
- `POST /rpc/cex-final-label-write-queue-schema-plan` -> `rpc_cex_final_label_write_queue_schema_plan` [ admin] -> `get_cex_final_label_write_queue_schema_plan`
- `POST /rpc/cex-final-label-write-queue/create` -> `rpc_create_cex_final_label_write_review_queue` [ admin] -> `create_cex_final_label_write_review_queue`
- `POST /rpc/cex-final-label-write-queue/insert` -> `rpc_insert_cex_final_label_write_review` [ admin] -> `insert_cex_final_label_write_review`
- `GET /rpc/cex-final-label-write-queue/review` -> `rpc_cex_final_label_write_review_queue_review` [ admin] -> `get_cex_final_label_write_review_queue_review`
- `POST /rpc/cex-final-label-write-queue/review` -> `rpc_cex_final_label_write_review_queue_review` [ admin] -> `get_cex_final_label_write_review_queue_review`
- `POST /rpc/cex-final-label-write-queue/decision-preview` -> `rpc_cex_final_label_write_queue_decision_preview` [ admin] -> `get_cex_final_label_write_decision_preview`
- `POST /rpc/cex-final-label-write-queue/decision/apply` -> `rpc_cex_final_label_write_queue_decision_apply` [ admin] -> `apply_cex_final_label_write_decision`
- `GET /rpc/cex-final-label-write-queue/execution-contract` -> `rpc_cex_final_label_write_queue_execution_contract` [ admin] -> `get_cex_final_label_write_execution_contract`
- `POST /rpc/cex-final-label-write-queue/execution-contract` -> `rpc_cex_final_label_write_queue_execution_contract` [ admin] -> `get_cex_final_label_write_execution_contract`
- `GET /rpc/cex-final-label-execution-queue-schema-plan` -> `rpc_cex_final_label_execution_queue_schema_plan` [ admin] -> `get_cex_final_label_execution_queue_schema_plan`
- `POST /rpc/cex-final-label-execution-queue-schema-plan` -> `rpc_cex_final_label_execution_queue_schema_plan` [ admin] -> `get_cex_final_label_execution_queue_schema_plan`
- `POST /rpc/cex-final-label-execution-queue/create` -> `rpc_create_cex_final_label_execution_review_queue` [ admin] -> `create_cex_final_label_execution_review_queue`
- `POST /rpc/cex-final-label-execution-queue/insert` -> `rpc_insert_cex_final_label_execution_review` [ admin] -> `insert_cex_final_label_execution_review`
- `GET /rpc/cex-final-label-execution-queue/review` -> `rpc_cex_final_label_execution_review_queue_review` [ admin] -> `get_cex_final_label_execution_review_queue_review`
- `POST /rpc/cex-final-label-execution-queue/review` -> `rpc_cex_final_label_execution_review_queue_review` [ admin] -> `get_cex_final_label_execution_review_queue_review`
- `POST /rpc/cex-final-label-execution-queue/decision-preview` -> `rpc_cex_final_label_execution_queue_decision_preview` [ admin] -> `get_cex_final_label_execution_decision_preview`
- `POST /rpc/cex-final-label-execution-queue/decision/apply` -> `rpc_cex_final_label_execution_queue_decision_apply` [ admin] -> `apply_cex_final_label_execution_decision`
- `GET /rpc/cex-final-label-execution-queue/final-label-write-safety-checkpoint` -> `rpc_cex_final_label_execution_queue_final_label_write_safety_checkpoint` [ admin] -> `get_cex_final_label_write_safety_checkpoint`
- `POST /rpc/cex-final-label-execution-queue/final-label-write-safety-checkpoint` -> `rpc_cex_final_label_execution_queue_final_label_write_safety_checkpoint` [ admin] -> `get_cex_final_label_write_safety_checkpoint`
- `POST /rpc/dex-router-venue-mapping/rollback-artifact-preview` -> `rpc_dex_router_venue_mapping_rollback_artifact_preview` [ admin] -> `get_dex_router_venue_mapping_rollback_artifact_preview`
- `POST /rpc/dex-router-venue-mapping/rollback-artifact-schema-plan` -> `rpc_dex_router_venue_mapping_rollback_artifact_schema_plan` [ admin] -> `get_dex_router_venue_mapping_rollback_artifact_schema_plan`
- `POST /rpc/dex-router-venue-mapping/rollback-artifact-storage/create` -> `rpc_create_dex_router_venue_mapping_rollback_artifact_storage` [ admin] -> `create_dex_router_venue_mapping_rollback_artifact_storage`
- `POST /rpc/dex-router-venue-mapping/rollback-artifact/create` -> `rpc_create_dex_router_venue_mapping_rollback_artifact` [ admin] -> `create_dex_router_venue_mapping_rollback_artifact`
- `POST /rpc/dex-router-venue-mapping/rollback-artifact/refresh` -> `rpc_refresh_dex_router_venue_mapping_rollback_artifact` [ admin] -> `refresh_dex_router_venue_mapping_rollback_artifact`
- `GET /rpc/dex-router-venue-mapping/rollback-artifacts` -> `rpc_dex_router_venue_mapping_rollback_artifacts` [ admin] -> `get_dex_router_venue_mapping_rollback_artifacts`
- `GET /rpc/unknown-router-source-gap-report` -> `rpc_unknown_router_source_gap_report` [ read] -> `get_unknown_router_source_gap_report`
- `GET /rpc/unknown-router-official-source-worklist` -> `rpc_unknown_router_official_source_worklist` [ read] -> `get_unknown_router_official_source_worklist`
- `GET /rpc/unknown-router-proof-dossiers` -> `rpc_unknown_router_proof_dossiers` [ read] -> `get_unknown_router_proof_dossiers`
- `GET /rpc/unknown-router-official-source-acquisition-queue` -> `rpc_unknown_router_official_source_acquisition_queue` [ read] -> `get_unknown_router_official_source_acquisition_queue`
- `GET /rpc/unknown-router-official-source-search-scan` -> `rpc_unknown_router_official_source_search_scan` [ read] -> `get_unknown_router_official_source_search_scan`
- `GET /rpc/unknown-router-official-source-rule-checkpoint` -> `rpc_unknown_router_official_source_rule_checkpoint` [ admin] -> `get_unknown_router_official_source_rule_checkpoint`
- `POST /rpc/unknown-router-official-source-rule-checkpoint` -> `rpc_unknown_router_official_source_rule_checkpoint` [ admin] -> `get_unknown_router_official_source_rule_checkpoint`
- `GET /rpc/unknown-router-creator-identity-scan` -> `rpc_unknown_router_creator_identity_scan` [ read] -> `get_unknown_router_creator_identity_scan`
- `GET /rpc/unknown-router-creator-identity-acquisition-queue` -> `rpc_unknown_router_creator_identity_acquisition_queue` [ read] -> `get_unknown_router_creator_identity_acquisition_queue`
- `GET /rpc/unknown-router-creator-identity-evidence-scan` -> `rpc_unknown_router_creator_identity_evidence_scan` [ read] -> `get_unknown_router_creator_identity_evidence_scan`
- `GET /rpc/unknown-router-creator-identity-source-search-scan` -> `rpc_unknown_router_creator_identity_source_search_scan` [ read] -> `get_unknown_router_creator_identity_source_search_scan`
- `GET /rpc/unknown-router-interaction-fingerprints` -> `rpc_unknown_router_interaction_fingerprints` [ read] -> `get_unknown_router_interaction_fingerprints`
- `GET /rpc/unknown-router-method-selector-scan` -> `rpc_unknown_router_method_selector_scan` [ read] -> `get_unknown_router_method_selector_scan`
- `GET /rpc/unknown-router-selector-signature-resolution-scan` -> `rpc_unknown_router_selector_signature_resolution_scan` [ read] -> `get_unknown_router_selector_signature_resolution_scan`
- `GET /rpc/unknown-router-verified-contract-source-scan` -> `rpc_unknown_router_verified_contract_source_scan` [ read] -> `get_unknown_router_verified_contract_source_scan`
- `GET /rpc/unknown-router-proxy-implementation-scan` -> `rpc_unknown_router_proxy_implementation_scan` [ read] -> `get_unknown_router_proxy_implementation_scan`
- `GET /rpc/unknown-router-internal-call-trace-scan` -> `rpc_unknown_router_internal_call_trace_scan` [ read] -> `get_unknown_router_internal_call_trace_scan`
- `GET /rpc/unknown-router-internal-transaction-fallback-scan` -> `rpc_unknown_router_internal_transaction_fallback_scan` [ read] -> `get_unknown_router_internal_transaction_fallback_scan`
- `GET /rpc/token-market-recent-unknown-router-internal-transaction-fallback-scan` -> `rpc_token_market_recent_unknown_router_internal_transaction_fallback_scan` [ admin] -> `get_token_market_recent_unknown_router_internal_transaction_fallback_scan`
- `GET /rpc/unknown-router-internal-counterparty-research-packages` -> `rpc_unknown_router_internal_counterparty_research_packages` [ read] -> `get_unknown_router_internal_counterparty_research_packages`
- `GET /rpc/unknown-router-internal-counterparty-research-packages-official-review` -> `rpc_unknown_router_internal_counterparty_research_packages_official_review` [ read] -> `get_unknown_router_internal_counterparty_research_packages_official_review`
- `GET /rpc/unknown-router-internal-counterparty-router-source-search-scan` -> `rpc_unknown_router_internal_counterparty_router_source_search_scan` [ read] -> `get_unknown_router_internal_counterparty_router_source_search_scan`
- `GET /rpc/unknown-router-public-identity-acquisition-scan` -> `rpc_unknown_router_public_identity_acquisition_scan` [ read] -> `get_unknown_router_public_identity_acquisition_scan`
- `GET /rpc/unknown-router-evidence-package` -> `rpc_unknown_router_evidence_package` [ admin] -> `get_unknown_router_evidence_package`
- `GET /rpc/unknown-router-role-classification-checkpoint` -> `rpc_unknown_router_role_classification_checkpoint` [ admin] -> `get_unknown_router_role_classification_checkpoint`
- `GET /rpc/unknown-router-role-exclusion-plan` -> `rpc_unknown_router_role_exclusion_plan` [ admin] -> `get_unknown_router_role_exclusion_plan`
- `GET /rpc/unknown-dex-route-provenance-workbench` -> `rpc_unknown_dex_route_provenance_workbench` [ admin] -> `get_unknown_dex_route_provenance_workbench`
- `POST /rpc/unknown-dex-route-provenance-workbench` -> `rpc_unknown_dex_route_provenance_workbench` [ admin] -> `get_unknown_dex_route_provenance_workbench`
- `GET /rpc/unknown-dex-route-provenance-dossier` -> `rpc_unknown_dex_route_provenance_dossier` [ admin] -> `get_unknown_dex_route_provenance_dossier`
- `POST /rpc/unknown-dex-route-provenance-dossier` -> `rpc_unknown_dex_route_provenance_dossier` [ admin] -> `get_unknown_dex_route_provenance_dossier`
- `GET /rpc/unknown-dex-intermediary-path-repair-plan` -> `rpc_unknown_dex_intermediary_path_repair_plan` [ admin] -> `get_unknown_dex_intermediary_path_repair_plan`
- `POST /rpc/unknown-dex-intermediary-path-repair-plan` -> `rpc_unknown_dex_intermediary_path_repair_plan` [ admin] -> `get_unknown_dex_intermediary_path_repair_plan`
- `GET /rpc/unknown-dex-intermediary-bounded-trace-collection` -> `rpc_unknown_dex_intermediary_bounded_trace_collection` [ admin] -> `run_unknown_dex_intermediary_bounded_trace_collection`
- `POST /rpc/unknown-dex-intermediary-bounded-trace-collection` -> `rpc_unknown_dex_intermediary_bounded_trace_collection` [ admin] -> `run_unknown_dex_intermediary_bounded_trace_collection`
- `GET /rpc/unknown-dex-intermediary-internal-transaction-fallback` -> `rpc_unknown_dex_intermediary_internal_transaction_fallback` [ admin] -> `run_unknown_dex_intermediary_internal_transaction_fallback`
- `POST /rpc/unknown-dex-intermediary-internal-transaction-fallback` -> `rpc_unknown_dex_intermediary_internal_transaction_fallback` [ admin] -> `run_unknown_dex_intermediary_internal_transaction_fallback`
- `GET /rpc/unknown-dex-traceability-candidate-selector` -> `rpc_unknown_dex_traceability_candidate_selector` [ admin] -> `get_unknown_dex_traceability_candidate_selector`
- `POST /rpc/unknown-dex-traceability-candidate-selector` -> `rpc_unknown_dex_traceability_candidate_selector` [ admin] -> `get_unknown_dex_traceability_candidate_selector`
- `GET /rpc/unknown-dex-local-transfer-path-workbench` -> `rpc_unknown_dex_local_transfer_path_workbench` [ admin] -> `get_unknown_dex_local_transfer_path_workbench`
- `POST /rpc/unknown-dex-local-transfer-path-workbench` -> `rpc_unknown_dex_local_transfer_path_workbench` [ admin] -> `get_unknown_dex_local_transfer_path_workbench`
- `GET /rpc/unknown-dex-local-path-official-source-repair-plan` -> `rpc_unknown_dex_local_path_official_source_repair_plan` [ admin] -> `get_unknown_dex_local_path_official_source_repair_plan`
- `POST /rpc/unknown-dex-local-path-official-source-repair-plan` -> `rpc_unknown_dex_local_path_official_source_repair_plan` [ admin] -> `get_unknown_dex_local_path_official_source_repair_plan`
- `GET /rpc/unknown-dex-local-path-official-source-search-scan` -> `rpc_unknown_dex_local_path_official_source_search_scan` [ admin] -> `get_unknown_dex_local_path_official_source_search_scan`
- `POST /rpc/unknown-dex-local-path-official-source-search-scan` -> `rpc_unknown_dex_local_path_official_source_search_scan` [ admin] -> `get_unknown_dex_local_path_official_source_search_scan`
- `GET /rpc/unknown-dex-local-path-explorer-identity-hint-scan` -> `rpc_unknown_dex_local_path_explorer_identity_hint_scan` [ admin] -> `get_unknown_dex_local_path_explorer_identity_hint_scan`
- `POST /rpc/unknown-dex-local-path-explorer-identity-hint-scan` -> `rpc_unknown_dex_local_path_explorer_identity_hint_scan` [ admin] -> `get_unknown_dex_local_path_explorer_identity_hint_scan`
- `GET /rpc/unknown-dex-local-path-pool-factory-inference-checkpoint` -> `rpc_unknown_dex_local_path_pool_factory_inference_checkpoint` [ admin] -> `get_unknown_dex_local_path_pool_factory_inference_checkpoint`
- `POST /rpc/unknown-dex-local-path-pool-factory-inference-checkpoint` -> `rpc_unknown_dex_local_path_pool_factory_inference_checkpoint` [ admin] -> `get_unknown_dex_local_path_pool_factory_inference_checkpoint`
- `GET /rpc/unknown-dex-factory-official-source-proof-checkpoint` -> `rpc_unknown_dex_factory_official_source_proof_checkpoint` [ admin] -> `get_unknown_dex_factory_official_source_proof_checkpoint`
- `POST /rpc/unknown-dex-factory-official-source-proof-checkpoint` -> `rpc_unknown_dex_factory_official_source_proof_checkpoint` [ admin] -> `get_unknown_dex_factory_official_source_proof_checkpoint`
- `GET /rpc/unknown-dex-deployment-registry-paircreated-proof-checkpoint` -> `rpc_unknown_dex_deployment_registry_paircreated_proof_checkpoint` [ admin] -> `get_unknown_dex_deployment_registry_paircreated_proof_checkpoint`
- `POST /rpc/unknown-dex-deployment-registry-paircreated-proof-checkpoint` -> `rpc_unknown_dex_deployment_registry_paircreated_proof_checkpoint` [ admin] -> `get_unknown_dex_deployment_registry_paircreated_proof_checkpoint`
- `GET /rpc/unknown-dex-paircreated-log-replay-plan` -> `rpc_unknown_dex_paircreated_log_replay_plan` [ admin] -> `get_unknown_dex_paircreated_log_replay_plan`
- `POST /rpc/unknown-dex-paircreated-log-replay-plan` -> `rpc_unknown_dex_paircreated_log_replay_plan` [ admin] -> `get_unknown_dex_paircreated_log_replay_plan`
- `GET /rpc/unknown-dex-paircreated-bounded-replay-dry-run` -> `rpc_unknown_dex_paircreated_bounded_replay_dry_run` [ admin] -> `get_unknown_dex_paircreated_bounded_replay_dry_run`
- `POST /rpc/unknown-dex-paircreated-bounded-replay-dry-run` -> `rpc_unknown_dex_paircreated_bounded_replay_dry_run` [ admin] -> `get_unknown_dex_paircreated_bounded_replay_dry_run`
- `GET /rpc/unknown-dex-paircreated-provider-indexer-capability-audit` -> `rpc_unknown_dex_paircreated_provider_indexer_capability_audit` [ admin] -> `get_unknown_dex_paircreated_provider_indexer_capability_audit`
- `POST /rpc/unknown-dex-paircreated-provider-indexer-capability-audit` -> `rpc_unknown_dex_paircreated_provider_indexer_capability_audit` [ admin] -> `get_unknown_dex_paircreated_provider_indexer_capability_audit`
- `GET /rpc/unknown-dex-paircreated-blockscout-indexer-bounded-lookup-dry-run` -> `rpc_unknown_dex_paircreated_blockscout_indexer_bounded_lookup_dry_run` [ admin] -> `get_unknown_dex_paircreated_blockscout_indexer_bounded_lookup_dry_run`
- `POST /rpc/unknown-dex-paircreated-blockscout-indexer-bounded-lookup-dry-run` -> `rpc_unknown_dex_paircreated_blockscout_indexer_bounded_lookup_dry_run` [ admin] -> `get_unknown_dex_paircreated_blockscout_indexer_bounded_lookup_dry_run`
- `GET /rpc/unknown-dex-paircreated-sqd-portal-bounded-lookup-dry-run` -> `rpc_unknown_dex_paircreated_sqd_portal_bounded_lookup_dry_run` [ admin] -> `get_unknown_dex_paircreated_sqd_portal_bounded_lookup_dry_run`
- `POST /rpc/unknown-dex-paircreated-sqd-portal-bounded-lookup-dry-run` -> `rpc_unknown_dex_paircreated_sqd_portal_bounded_lookup_dry_run` [ admin] -> `get_unknown_dex_paircreated_sqd_portal_bounded_lookup_dry_run`
- `GET /rpc/unknown-dex-paircreated-evidence-persistence-schema-plan` -> `rpc_unknown_dex_paircreated_evidence_persistence_schema_plan` [ admin] -> `get_unknown_dex_paircreated_evidence_persistence_schema_plan`
- `POST /rpc/unknown-dex-paircreated-evidence-persistence-schema-plan` -> `rpc_unknown_dex_paircreated_evidence_persistence_schema_plan` [ admin] -> `get_unknown_dex_paircreated_evidence_persistence_schema_plan`
- `POST /rpc/unknown-dex-paircreated-evidence/create` -> `rpc_create_unknown_dex_paircreated_evidence` [ admin] -> `create_unknown_dex_paircreated_evidence`
- `POST /rpc/unknown-dex-paircreated-evidence-persistence/create` -> `rpc_create_unknown_dex_paircreated_evidence` [ admin] -> `create_unknown_dex_paircreated_evidence`
- `POST /rpc/unknown-dex-paircreated-evidence/insert` -> `rpc_insert_unknown_dex_paircreated_evidence` [ admin] -> `insert_unknown_dex_paircreated_evidence`
- `POST /rpc/unknown-dex-paircreated-evidence-persistence/insert` -> `rpc_insert_unknown_dex_paircreated_evidence` [ admin] -> `insert_unknown_dex_paircreated_evidence`
- `GET /rpc/unknown-dex-paircreated-evidence/review` -> `?` [ read] -> no direct service detected
- `POST /rpc/unknown-dex-paircreated-evidence/review` -> `?` [ read] -> no direct service detected
- `GET /rpc/unknown-dex-paircreated-evidence-review-queue` -> `rpc_unknown_dex_paircreated_evidence_review_queue` [ admin] -> `get_unknown_dex_paircreated_evidence_review_queue`
- `POST /rpc/unknown-dex-paircreated-evidence-review-queue` -> `rpc_unknown_dex_paircreated_evidence_review_queue` [ admin] -> `get_unknown_dex_paircreated_evidence_review_queue`
- `POST /rpc/unknown-dex-paircreated-evidence/decision-preview` -> `rpc_unknown_dex_paircreated_evidence_decision_preview` [ admin] -> `get_unknown_dex_paircreated_evidence_decision_preview`
- `POST /rpc/unknown-dex-paircreated-evidence-review-queue/decision-preview` -> `rpc_unknown_dex_paircreated_evidence_decision_preview` [ admin] -> `get_unknown_dex_paircreated_evidence_decision_preview`
- `POST /rpc/unknown-dex-paircreated-evidence/decision/apply` -> `rpc_unknown_dex_paircreated_evidence_decision_apply` [ admin] -> `apply_unknown_dex_paircreated_evidence_decision`
- `POST /rpc/unknown-dex-paircreated-evidence-review-queue/decision/apply` -> `rpc_unknown_dex_paircreated_evidence_decision_apply` [ admin] -> `apply_unknown_dex_paircreated_evidence_decision`
- `GET /rpc/dex-mapping-review-contract` -> `rpc_dex_mapping_review_contract` [ admin] -> `get_dex_mapping_review_contract`
- `POST /rpc/dex-mapping-review-contract` -> `rpc_dex_mapping_review_contract` [ admin] -> `get_dex_mapping_review_contract`
- `GET /rpc/dex-mapping-review-queue-schema-plan` -> `rpc_dex_mapping_review_queue_schema_plan` [ admin] -> `get_dex_mapping_review_queue_schema_plan`
- `POST /rpc/dex-mapping-review-queue-schema-plan` -> `rpc_dex_mapping_review_queue_schema_plan` [ admin] -> `get_dex_mapping_review_queue_schema_plan`
- `POST /rpc/dex-mapping-review-queue/create` -> `rpc_create_dex_mapping_review_queue` [ admin] -> `create_dex_mapping_review_queue`
- `POST /rpc/dex-mapping-review-queue/insert` -> `rpc_insert_dex_mapping_review_queue` [ admin] -> `insert_dex_mapping_review_queue`
- `GET /rpc/dex-local-event-reader-proof-of-shape-plan` -> `rpc_dex_local_event_reader_proof_of_shape_plan` [ admin] -> `get_dex_local_event_reader_proof_of_shape_plan`
- `POST /rpc/dex-local-event-reader-proof-of-shape-plan` -> `rpc_dex_local_event_reader_proof_of_shape_plan` [ admin] -> `get_dex_local_event_reader_proof_of_shape_plan`
- `GET /rpc/dex-local-event-reader-checkpoint-raw-schema-plan` -> `rpc_dex_local_event_reader_checkpoint_raw_schema_plan` [ admin] -> `get_dex_local_event_reader_checkpoint_raw_schema_plan`
- `POST /rpc/dex-local-event-reader-checkpoint-raw-schema-plan` -> `rpc_dex_local_event_reader_checkpoint_raw_schema_plan` [ admin] -> `get_dex_local_event_reader_checkpoint_raw_schema_plan`
- `POST /rpc/dex-local-event-reader-checkpoint-raw/create` -> `rpc_create_dex_local_event_reader_checkpoint_raw_tables` [ admin] -> `create_dex_local_event_reader_checkpoint_raw_tables`
- `GET /rpc/dex-local-event-reader-run-contract` -> `rpc_dex_local_event_reader_run_contract` [ admin] -> `get_dex_local_event_reader_run_contract`
- `POST /rpc/dex-local-event-reader-run-contract` -> `rpc_dex_local_event_reader_run_contract` [ admin] -> `get_dex_local_event_reader_run_contract`
- `POST /rpc/dex-local-event-reader-run/insert` -> `rpc_insert_dex_local_event_reader_run` [ admin] -> `insert_dex_local_event_reader_run`
- `GET /rpc/dex-local-event-reader-run/execution-contract` -> `rpc_dex_local_event_reader_execution_contract` [ admin] -> `get_dex_local_event_reader_execution_contract`
- `POST /rpc/dex-local-event-reader-run/execution-contract` -> `rpc_dex_local_event_reader_execution_contract` [ admin] -> `get_dex_local_event_reader_execution_contract`
- `GET /rpc/dex-local-event-reader-run/execution-dry-run` -> `rpc_dex_local_event_reader_execution_dry_run` [ admin] -> `run_dex_local_event_reader_execution_dry_run`
- `POST /rpc/dex-local-event-reader-run/execution-dry-run` -> `rpc_dex_local_event_reader_execution_dry_run` [ admin] -> `run_dex_local_event_reader_execution_dry_run`
- `GET /rpc/dex-local-event-reader-run/sqd-lookup-dry-run` -> `rpc_dex_local_event_reader_sqd_lookup_dry_run` [ admin] -> `run_dex_local_event_reader_sqd_lookup_dry_run`
- `POST /rpc/dex-local-event-reader-run/sqd-lookup-dry-run` -> `rpc_dex_local_event_reader_sqd_lookup_dry_run` [ admin] -> `run_dex_local_event_reader_sqd_lookup_dry_run`
- `GET /rpc/dex-local-event-reader-run/sqd-raw-event-persistence` -> `rpc_dex_local_event_reader_sqd_raw_event_persistence` [ admin] -> `persist_dex_local_event_reader_sqd_raw_events`
- `POST /rpc/dex-local-event-reader-run/sqd-raw-event-persistence` -> `rpc_dex_local_event_reader_sqd_raw_event_persistence` [ admin] -> `persist_dex_local_event_reader_sqd_raw_events`
- `GET /rpc/dex-local-event-reader-run/proof-package-preview` -> `rpc_dex_local_event_reader_proof_package_preview` [ admin] -> `get_dex_local_event_reader_proof_package_preview`
- `POST /rpc/dex-local-event-reader-run/proof-package-preview` -> `rpc_dex_local_event_reader_proof_package_preview` [ admin] -> `get_dex_local_event_reader_proof_package_preview`
- `GET /rpc/dex-local-event-reader-run/proof-package/insert` -> `rpc_dex_local_event_reader_proof_package_insert` [ admin] -> `insert_dex_local_event_reader_proof_package`
- `POST /rpc/dex-local-event-reader-run/proof-package/insert` -> `rpc_dex_local_event_reader_proof_package_insert` [ admin] -> `insert_dex_local_event_reader_proof_package`
- `GET /rpc/dex-event-proof-packages/review` -> `rpc_dex_event_proof_package_review_queue` [ admin] -> `get_dex_local_event_reader_proof_package_review_queue`
- `POST /rpc/dex-event-proof-packages/review` -> `rpc_dex_event_proof_package_review_queue` [ admin] -> `get_dex_local_event_reader_proof_package_review_queue`
- `GET /rpc/dex-event-proof-packages/decision-preview` -> `rpc_dex_event_proof_package_decision_preview` [ admin] -> `get_dex_local_event_reader_proof_package_decision_preview`
- `POST /rpc/dex-event-proof-packages/decision-preview` -> `rpc_dex_event_proof_package_decision_preview` [ admin] -> `get_dex_local_event_reader_proof_package_decision_preview`
- `POST /rpc/dex-event-proof-packages/decision/apply` -> `rpc_dex_event_proof_package_decision_apply` [ admin] -> `apply_dex_local_event_reader_proof_package_decision`
- `GET /rpc/dex-event-proof-packages/evidence-review-contract` -> `rpc_dex_event_proof_package_evidence_review_contract` [ admin] -> `get_dex_local_event_reader_proof_package_evidence_review_contract`
- `POST /rpc/dex-event-proof-packages/evidence-review-contract` -> `rpc_dex_event_proof_package_evidence_review_contract` [ admin] -> `get_dex_local_event_reader_proof_package_evidence_review_contract`
- `GET /rpc/dex-event-proof-packages/corroboration-review` -> `rpc_dex_event_proof_package_corroboration_review` [ admin] -> `get_dex_local_event_reader_proof_package_corroboration_review`
- `POST /rpc/dex-event-proof-packages/corroboration-review` -> `rpc_dex_event_proof_package_corroboration_review` [ admin] -> `get_dex_local_event_reader_proof_package_corroboration_review`
- `GET /rpc/unknown-dex-paircreated-archive-indexer-alternative-strategy` -> `rpc_unknown_dex_paircreated_archive_indexer_alternative_strategy` [ admin] -> `get_unknown_dex_paircreated_archive_indexer_alternative_strategy`
- `POST /rpc/unknown-dex-paircreated-archive-indexer-alternative-strategy` -> `rpc_unknown_dex_paircreated_archive_indexer_alternative_strategy` [ admin] -> `get_unknown_dex_paircreated_archive_indexer_alternative_strategy`
- `GET /rpc/unknown-dex-paircreated-local-creation-block-range-plan` -> `rpc_unknown_dex_paircreated_local_creation_block_range_plan` [ admin] -> `get_unknown_dex_paircreated_local_creation_block_range_plan`
- `POST /rpc/unknown-dex-paircreated-local-creation-block-range-plan` -> `rpc_unknown_dex_paircreated_local_creation_block_range_plan` [ admin] -> `get_unknown_dex_paircreated_local_creation_block_range_plan`
- `GET /rpc/unknown-dex-paircreated-reduced-range-replay-dry-run` -> `rpc_unknown_dex_paircreated_reduced_range_replay_dry_run` [ admin] -> `get_unknown_dex_paircreated_reduced_range_replay_dry_run`
- `POST /rpc/unknown-dex-paircreated-reduced-range-replay-dry-run` -> `rpc_unknown_dex_paircreated_reduced_range_replay_dry_run` [ admin] -> `get_unknown_dex_paircreated_reduced_range_replay_dry_run`
- `GET /rpc/unknown-dex-pool-code-existence-creation-block-probe` -> `rpc_unknown_dex_pool_code_existence_creation_block_probe` [ admin] -> `get_unknown_dex_pool_code_existence_creation_block_probe`
- `POST /rpc/unknown-dex-pool-code-existence-creation-block-probe` -> `rpc_unknown_dex_pool_code_existence_creation_block_probe` [ admin] -> `get_unknown_dex_pool_code_existence_creation_block_probe`
- `GET /rpc/unknown-dex-pool-contract-creation-proof-source-gate` -> `rpc_unknown_dex_pool_contract_creation_proof_source_gate` [ admin] -> `get_unknown_dex_pool_contract_creation_proof_source_gate`
- `POST /rpc/unknown-dex-pool-contract-creation-proof-source-gate` -> `rpc_unknown_dex_pool_contract_creation_proof_source_gate` [ admin] -> `get_unknown_dex_pool_contract_creation_proof_source_gate`
- `GET /rpc/unknown-dex-pool-contract-creation-explorer-archive-lookup-dry-run` -> `rpc_unknown_dex_pool_contract_creation_explorer_archive_lookup_dry_run` [ admin] -> `get_unknown_dex_pool_contract_creation_explorer_archive_lookup_dry_run`
- `POST /rpc/unknown-dex-pool-contract-creation-explorer-archive-lookup-dry-run` -> `rpc_unknown_dex_pool_contract_creation_explorer_archive_lookup_dry_run` [ admin] -> `get_unknown_dex_pool_contract_creation_explorer_archive_lookup_dry_run`
- `GET /rpc/unknown-dex-paircreated-forward-local-indexer-plan` -> `rpc_unknown_dex_paircreated_forward_local_indexer_plan` [ admin] -> `get_unknown_dex_paircreated_forward_local_indexer_plan`
- `POST /rpc/unknown-dex-paircreated-forward-local-indexer-plan` -> `rpc_unknown_dex_paircreated_forward_local_indexer_plan` [ admin] -> `get_unknown_dex_paircreated_forward_local_indexer_plan`
- `GET /rpc/unknown-dex-venue-family-review` -> `rpc_unknown_dex_venue_family_review` [ admin] -> `get_unknown_dex_venue_family_review`
- `POST /rpc/unknown-dex-venue-family-review` -> `rpc_unknown_dex_venue_family_review` [ admin] -> `get_unknown_dex_venue_family_review`
- `GET /rpc/unknown-dex-family-context-scoring-plan` -> `rpc_unknown_dex_family_context_scoring_plan` [ admin] -> `get_unknown_dex_family_context_scoring_plan`
- `POST /rpc/unknown-dex-family-context-scoring-plan` -> `rpc_unknown_dex_family_context_scoring_plan` [ admin] -> `get_unknown_dex_family_context_scoring_plan`
- `GET /rpc/unknown-dex-family-context-collection-plan` -> `rpc_unknown_dex_family_context_collection_plan` [ admin] -> `get_unknown_dex_family_context_collection_plan`
- `POST /rpc/unknown-dex-family-context-collection-plan` -> `rpc_unknown_dex_family_context_collection_plan` [ admin] -> `get_unknown_dex_family_context_collection_plan`
- `POST /rpc/unknown-dex-family-context-history-collection` -> `rpc_unknown_dex_family_context_history_collection` [ admin] -> `run_unknown_dex_family_context_history_collection`
- `GET /rpc/unknown-dex-family-context-post-collection-audit` -> `rpc_unknown_dex_family_context_post_collection_audit` [ admin] -> `get_unknown_dex_family_context_post_collection_audit`
- `POST /rpc/unknown-dex-family-context-post-collection-audit` -> `rpc_unknown_dex_family_context_post_collection_audit` [ admin] -> `get_unknown_dex_family_context_post_collection_audit`
- `GET /rpc/unknown-dex-family-context-candidate-repair-plan` -> `rpc_unknown_dex_family_context_candidate_repair_plan` [ admin] -> `get_unknown_dex_family_context_candidate_repair_plan`
- `POST /rpc/unknown-dex-family-context-candidate-repair-plan` -> `rpc_unknown_dex_family_context_candidate_repair_plan` [ admin] -> `get_unknown_dex_family_context_candidate_repair_plan`
- `GET /rpc/unknown-dex-family-context-casefile` -> `rpc_unknown_dex_family_context_casefile` [ admin] -> `get_unknown_dex_family_context_casefile`
- `POST /rpc/unknown-dex-family-context-casefile` -> `rpc_unknown_dex_family_context_casefile` [ admin] -> `get_unknown_dex_family_context_casefile`
- `GET /rpc/unknown-dex-family-context-route-source-repeatability-plan` -> `rpc_unknown_dex_family_context_route_source_repeatability_plan` [ admin] -> `get_unknown_dex_family_context_route_source_repeatability_plan`
- `POST /rpc/unknown-dex-family-context-route-source-repeatability-plan` -> `rpc_unknown_dex_family_context_route_source_repeatability_plan` [ admin] -> `get_unknown_dex_family_context_route_source_repeatability_plan`
- `GET /rpc/unknown-dex-family-context-exact-route-source-proof-acquisition-plan` -> `rpc_unknown_dex_family_context_exact_route_source_proof_acquisition_plan` [ admin] -> `get_unknown_dex_family_context_exact_route_source_proof_acquisition_plan`
- `POST /rpc/unknown-dex-family-context-exact-route-source-proof-acquisition-plan` -> `rpc_unknown_dex_family_context_exact_route_source_proof_acquisition_plan` [ admin] -> `get_unknown_dex_family_context_exact_route_source_proof_acquisition_plan`
- `GET /rpc/unknown-dex-family-context-bounded-official-source-lookup-plan` -> `rpc_unknown_dex_family_context_bounded_official_source_lookup_plan` [ admin] -> `get_unknown_dex_family_context_bounded_official_source_lookup_plan`
- `POST /rpc/unknown-dex-family-context-bounded-official-source-lookup-plan` -> `rpc_unknown_dex_family_context_bounded_official_source_lookup_plan` [ admin] -> `get_unknown_dex_family_context_bounded_official_source_lookup_plan`
- `GET /rpc/unknown-dex-family-context-source-acquisition-strategy-decision-preview` -> `rpc_unknown_dex_family_context_source_acquisition_strategy_decision_preview` [ admin] -> `get_unknown_dex_family_context_source_acquisition_strategy_decision_preview`
- `POST /rpc/unknown-dex-family-context-source-acquisition-strategy-decision-preview` -> `rpc_unknown_dex_family_context_source_acquisition_strategy_decision_preview` [ admin] -> `get_unknown_dex_family_context_source_acquisition_strategy_decision_preview`
- `GET /rpc/unknown-dex-family-context-manual-source-intake-preview` -> `rpc_unknown_dex_family_context_manual_source_intake_preview` [ admin] -> `get_unknown_dex_family_context_manual_source_intake_preview`
- `POST /rpc/unknown-dex-family-context-manual-source-intake-preview` -> `rpc_unknown_dex_family_context_manual_source_intake_preview` [ admin] -> `get_unknown_dex_family_context_manual_source_intake_preview`
- `GET /rpc/unknown-dex-family-context-bounded-official-source-lookup-gate` -> `rpc_unknown_dex_family_context_bounded_official_source_lookup_gate` [ admin] -> `get_unknown_dex_family_context_bounded_official_source_lookup_gate`
- `POST /rpc/unknown-dex-family-context-bounded-official-source-lookup-gate` -> `rpc_unknown_dex_family_context_bounded_official_source_lookup_gate` [ admin] -> `get_unknown_dex_family_context_bounded_official_source_lookup_gate`
- `GET /rpc/unknown-dex-family-context-bounded-official-source-lookup` -> `rpc_unknown_dex_family_context_bounded_official_source_lookup` [ admin] -> `get_unknown_dex_family_context_bounded_official_source_lookup`
- `POST /rpc/unknown-dex-family-context-bounded-official-source-lookup` -> `rpc_unknown_dex_family_context_bounded_official_source_lookup` [ admin] -> `get_unknown_dex_family_context_bounded_official_source_lookup`
- `GET /rpc/unknown-dex-family-context-source-page-fetch-grading-checkpoint` -> `rpc_unknown_dex_family_context_source_page_fetch_grading_checkpoint` [ admin] -> `get_unknown_dex_family_context_source_page_fetch_grading_checkpoint`
- `POST /rpc/unknown-dex-family-context-source-page-fetch-grading-checkpoint` -> `rpc_unknown_dex_family_context_source_page_fetch_grading_checkpoint` [ admin] -> `get_unknown_dex_family_context_source_page_fetch_grading_checkpoint`
- `GET /rpc/unknown-dex-family-context-stronger-official-route-source-package-plan` -> `rpc_unknown_dex_family_context_stronger_official_route_source_package_plan` [ admin] -> `get_unknown_dex_family_context_stronger_official_route_source_package_plan`
- `POST /rpc/unknown-dex-family-context-stronger-official-route-source-package-plan` -> `rpc_unknown_dex_family_context_stronger_official_route_source_package_plan` [ admin] -> `get_unknown_dex_family_context_stronger_official_route_source_package_plan`
- `GET /rpc/unknown-dex-family-context-bounded-official-route-source-package-preview` -> `rpc_unknown_dex_family_context_bounded_official_route_source_package_preview` [ admin] -> `get_unknown_dex_family_context_bounded_official_route_source_package_preview`
- `POST /rpc/unknown-dex-family-context-bounded-official-route-source-package-preview` -> `rpc_unknown_dex_family_context_bounded_official_route_source_package_preview` [ admin] -> `get_unknown_dex_family_context_bounded_official_route_source_package_preview`
- `GET /rpc/core-equity-agent-control-plane` -> `rpc_core_equity_agent_control_plane` [ admin] -> `get_core_equity_agent_control_plane`
- `POST /rpc/core-equity-agent-control-plane` -> `rpc_core_equity_agent_control_plane` [ admin] -> `get_core_equity_agent_control_plane`
- `GET /rpc/core-equity-agent-task-contract-preview` -> `rpc_core_equity_agent_task_contract_preview` [ admin] -> `get_core_equity_agent_task_contract_preview`
- `POST /rpc/core-equity-agent-task-contract-preview` -> `rpc_core_equity_agent_task_contract_preview` [ admin] -> `get_core_equity_agent_task_contract_preview`
- `GET /rpc/core-equity-codex-agent-runner-dry-run` -> `rpc_core_equity_codex_agent_runner_dry_run` [ admin] -> `run_core_equity_codex_agent_runner_dry_run`
- `POST /rpc/core-equity-codex-agent-runner-dry-run` -> `rpc_core_equity_codex_agent_runner_dry_run` [ admin] -> `run_core_equity_codex_agent_runner_dry_run`
- `GET /rpc/core-equity-codex-runner-audit-log-preview` -> `rpc_core_equity_codex_runner_audit_log_preview` [ admin] -> `get_core_equity_codex_runner_audit_log_preview`
- `POST /rpc/core-equity-codex-runner-audit-log-preview` -> `rpc_core_equity_codex_runner_audit_log_preview` [ admin] -> `get_core_equity_codex_runner_audit_log_preview`
- `POST /rpc/core-equity-codex-runner-audit-log/write` -> `rpc_core_equity_codex_runner_audit_log_write` [ admin] -> `write_core_equity_codex_runner_audit_log`
- `GET /rpc/core-equity-codex-schedule-plan` -> `rpc_core_equity_codex_schedule_plan` [ admin] -> `get_core_equity_codex_schedule_plan`
- `POST /rpc/core-equity-codex-schedule-plan` -> `rpc_core_equity_codex_schedule_plan` [ admin] -> `get_core_equity_codex_schedule_plan`
- `GET /rpc/core-equity-agent-os-lite/state-snapshot` -> `rpc_core_equity_agent_os_lite_state_snapshot` [ admin] -> `get_core_equity_agent_os_lite_state_snapshot`
- `POST /rpc/core-equity-agent-os-lite/state-snapshot` -> `rpc_core_equity_agent_os_lite_state_snapshot` [ admin] -> `get_core_equity_agent_os_lite_state_snapshot`
- `GET /rpc/core-equity-agent-os-lite/runtime-preflight` -> `rpc_core_equity_agent_os_lite_runtime_preflight` [ admin] -> `get_core_equity_agent_os_lite_runtime_preflight`
- `POST /rpc/core-equity-agent-os-lite/runtime-preflight` -> `rpc_core_equity_agent_os_lite_runtime_preflight` [ admin] -> `get_core_equity_agent_os_lite_runtime_preflight`
- `GET /rpc/core-equity-agent-os-lite/cycle-preview` -> `rpc_core_equity_agent_os_lite_cycle_preview` [ admin] -> `get_core_equity_agent_os_lite_cycle_preview`
- `POST /rpc/core-equity-agent-os-lite/cycle-preview` -> `rpc_core_equity_agent_os_lite_cycle_preview` [ admin] -> `get_core_equity_agent_os_lite_cycle_preview`
- `GET /rpc/core-equity-agent-os-lite/task-queue` -> `rpc_core_equity_agent_os_lite_task_queue` [ admin] -> `get_core_equity_agent_os_lite_task_queue_view`
- `POST /rpc/core-equity-agent-os-lite/task-queue` -> `rpc_core_equity_agent_os_lite_task_queue` [ admin] -> `get_core_equity_agent_os_lite_task_queue_view`
- `GET /rpc/core-equity-agent-os-lite/schedule-activation-checklist` -> `rpc_core_equity_agent_os_lite_schedule_activation_checklist` [ admin] -> `get_core_equity_agent_os_lite_schedule_activation_checklist`
- `POST /rpc/core-equity-agent-os-lite/schedule-activation-checklist` -> `rpc_core_equity_agent_os_lite_schedule_activation_checklist` [ admin] -> `get_core_equity_agent_os_lite_schedule_activation_checklist`
- `GET /rpc/unknown-dex-traceability-candidate-internal-probe` -> `rpc_unknown_dex_traceability_candidate_internal_probe` [ admin] -> `run_unknown_dex_traceability_candidate_internal_probe`
- `POST /rpc/unknown-dex-traceability-candidate-internal-probe` -> `rpc_unknown_dex_traceability_candidate_internal_probe` [ admin] -> `run_unknown_dex_traceability_candidate_internal_probe`
- `GET /rpc/dex-official-router-registry` -> `rpc_dex_official_router_registry` [ admin] -> `get_dex_official_router_registry`
- `GET /rpc/dex-official-router-registry/source-freshness` -> `rpc_dex_official_router_registry_source_freshness` [ admin] -> `get_dex_official_router_registry_source_freshness`
- `GET /rpc/aster-dex-fund-flow-radar` -> `rpc_aster_dex_fund_flow_radar` [ admin] -> `get_aster_dex_fund_flow_radar`
- `POST /rpc/aster-dex-fund-flow-collection` -> `rpc_aster_dex_fund_flow_collection` [ admin] -> `run_aster_dex_fund_flow_collection`
- `POST /rpc/aster-dex-paginated-fund-flow-collection` -> `rpc_aster_dex_paginated_fund_flow_collection` [ admin] -> `run_aster_dex_paginated_fund_flow_collection`
- `GET /rpc/aster-dex-flow-case-file` -> `rpc_aster_dex_flow_case_file` [ admin] -> `get_aster_dex_flow_case_file`
- `GET /rpc/aster-cex-bridge-context` -> `rpc_aster_cex_bridge_context` [ admin] -> `get_aster_cex_bridge_context`
- `GET /rpc/aster-agent-foundation-test` -> `rpc_aster_agent_foundation_test` [ admin] -> no direct service detected
- `POST /rpc/aster-agent-foundation-test` -> `rpc_aster_agent_foundation_test` [ admin] -> no direct service detected
- `GET /rpc/aster-order-book-anomaly-detection-test` -> `rpc_aster_order_book_anomaly_detection_test` [ admin] -> no direct service detected
- `POST /rpc/aster-order-book-anomaly-detection-test` -> `rpc_aster_order_book_anomaly_detection_test` [ admin] -> no direct service detected
- `GET /rpc/aster-agent-loop-test` -> `rpc_aster_agent_loop_test` [ admin] -> no direct service detected
- `POST /rpc/aster-agent-loop-test` -> `rpc_aster_agent_loop_test` [ admin] -> no direct service detected
- `GET /rpc/aster-api-resilience-test` -> `rpc_aster_api_resilience_test` [ admin] -> no direct service detected
- `POST /rpc/aster-api-resilience-test` -> `rpc_aster_api_resilience_test` [ admin] -> no direct service detected
- `GET /rpc/aster-mcp-market-data-adapter-preview` -> `rpc_aster_mcp_market_data_adapter_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-mcp-market-data-adapter-preview` -> `rpc_aster_mcp_market_data_adapter_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-perps-reality-check-preview` -> `rpc_aster_perps_reality_check_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-perps-reality-check-preview` -> `rpc_aster_perps_reality_check_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-data-source-validation-preview` -> `rpc_aster_data_source_validation_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-data-source-validation-preview` -> `rpc_aster_data_source_validation_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-mcp-capability-audit-preview` -> `rpc_aster_mcp_capability_audit_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-mcp-capability-audit-preview` -> `rpc_aster_mcp_capability_audit_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-public-universe-snapshot-preview` -> `rpc_aster_public_universe_snapshot_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-public-universe-snapshot-preview` -> `rpc_aster_public_universe_snapshot_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-ws-market-stream-validation-preview` -> `rpc_aster_ws_market_stream_validation_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-ws-market-stream-validation-preview` -> `rpc_aster_ws_market_stream_validation_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-ws-forward-monitor-preview` -> `rpc_aster_ws_forward_monitor_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-ws-forward-monitor-preview` -> `rpc_aster_ws_forward_monitor_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-ws-symbol-quality-report-preview` -> `rpc_aster_ws_symbol_quality_report_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-ws-symbol-quality-report-preview` -> `rpc_aster_ws_symbol_quality_report_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-v2-ws-preflight-refresh-preview` -> `rpc_aster_v2_ws_preflight_refresh_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-v2-ws-preflight-refresh-preview` -> `rpc_aster_v2_ws_preflight_refresh_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-v2-strict-vs-large-comparison-preview` -> `rpc_aster_v2_strict_vs_large_comparison_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-v2-strict-vs-large-comparison-preview` -> `rpc_aster_v2_strict_vs_large_comparison_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-runner-health-dashboard-preview` -> `rpc_aster_runner_health_dashboard_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-runner-health-dashboard-preview` -> `rpc_aster_runner_health_dashboard_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-priority-watchlist-preview` -> `rpc_aster_priority_watchlist_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-priority-watchlist-preview` -> `rpc_aster_priority_watchlist_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-dual-track-research-report-preview` -> `rpc_aster_dual_track_research_report_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-dual-track-research-report-preview` -> `rpc_aster_dual_track_research_report_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-exploitation-champions-validation-preview` -> `rpc_aster_exploitation_champions_validation_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-exploitation-champions-validation-preview` -> `rpc_aster_exploitation_champions_validation_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-mark-index-replay-filter-preview` -> `rpc_aster_mark_index_replay_filter_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-mark-index-replay-filter-preview` -> `rpc_aster_mark_index_replay_filter_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-schema-plan` -> `rpc_aster_paper_trading_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-schema-plan` -> `rpc_aster_paper_trading_schema_plan` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-ledger/create` -> `rpc_create_aster_paper_trading_ledger` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-run-preview` -> `rpc_aster_paper_trading_run_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-run-preview` -> `rpc_aster_paper_trading_run_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-replay-insert` -> `rpc_aster_paper_trading_replay_insert` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-ledger-analytics` -> `rpc_aster_paper_trading_ledger_analytics` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-ledger-analytics` -> `rpc_aster_paper_trading_ledger_analytics` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-watchlist-replay-insert` -> `rpc_aster_paper_trading_watchlist_replay_insert` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-strategy-report` -> `rpc_aster_paper_trading_strategy_report` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-strategy-report` -> `rpc_aster_paper_trading_strategy_report` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-gate-calibration-preview` -> `rpc_aster_paper_trading_gate_calibration_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-gate-calibration-preview` -> `rpc_aster_paper_trading_gate_calibration_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-extended-backtest-preview` -> `rpc_aster_paper_trading_extended_backtest_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-extended-backtest-preview` -> `rpc_aster_paper_trading_extended_backtest_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-signal-cinematic-diagnostic` -> `rpc_aster_paper_trading_signal_cinematic_diagnostic` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-signal-cinematic-diagnostic` -> `rpc_aster_paper_trading_signal_cinematic_diagnostic` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-risk-recalibration-test` -> `rpc_aster_paper_trading_risk_recalibration_test` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-risk-recalibration-test` -> `rpc_aster_paper_trading_risk_recalibration_test` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-hybrid-signal-test` -> `rpc_aster_paper_trading_hybrid_signal_test` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-hybrid-signal-test` -> `rpc_aster_paper_trading_hybrid_signal_test` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-hybrid-signal-test-v2` -> `rpc_aster_paper_trading_hybrid_signal_test_v2` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-hybrid-signal-test-v2` -> `rpc_aster_paper_trading_hybrid_signal_test_v2` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-final-alignment-test` -> `rpc_aster_paper_trading_final_alignment_test` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-final-alignment-test` -> `rpc_aster_paper_trading_final_alignment_test` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-short-fade-backtest-preview` -> `rpc_aster_paper_trading_short_fade_backtest_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-short-fade-backtest-preview` -> `rpc_aster_paper_trading_short_fade_backtest_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-60d-kline-replay-preview` -> `rpc_aster_paper_trading_60d_kline_replay_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-60d-kline-replay-preview` -> `rpc_aster_paper_trading_60d_kline_replay_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-multi-timeframe-replay-preview` -> `rpc_aster_paper_trading_multi_timeframe_replay_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-multi-timeframe-replay-preview` -> `rpc_aster_paper_trading_multi_timeframe_replay_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-focused-walkforward-preview` -> `rpc_aster_paper_trading_focused_walkforward_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-focused-walkforward-preview` -> `rpc_aster_paper_trading_focused_walkforward_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-focused-optimization-preview` -> `rpc_aster_paper_trading_focused_optimization_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-focused-optimization-preview` -> `rpc_aster_paper_trading_focused_optimization_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-short-extended-backtest-preview` -> `rpc_aster_paper_trading_short_extended_backtest_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-short-extended-backtest-preview` -> `rpc_aster_paper_trading_short_extended_backtest_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-volatile-universe-short-backtest-preview` -> `rpc_aster_volatile_universe_short_backtest_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-volatile-universe-short-backtest-preview` -> `rpc_aster_volatile_universe_short_backtest_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-short-fade-universe-selection-preview` -> `rpc_aster_short_fade_universe_selection_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-short-fade-universe-selection-preview` -> `rpc_aster_short_fade_universe_selection_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-short-time-stop-walkforward-preview` -> `rpc_aster_paper_trading_short_time_stop_walkforward_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-short-time-stop-walkforward-preview` -> `rpc_aster_paper_trading_short_time_stop_walkforward_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-short-time-stop-calibration-preview` -> `rpc_aster_paper_trading_short_time_stop_calibration_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-short-time-stop-calibration-preview` -> `rpc_aster_paper_trading_short_time_stop_calibration_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-forward-monitor-preview` -> `rpc_aster_paper_trading_forward_monitor_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-forward-monitor-preview` -> `rpc_aster_paper_trading_forward_monitor_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-optimized-long-forward-monitor-preview` -> `rpc_aster_optimized_long_forward_monitor_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-optimized-long-forward-monitor-preview` -> `rpc_aster_optimized_long_forward_monitor_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-optimized-long-stateful-monitor` -> `rpc_aster_optimized_long_stateful_monitor` [ admin] -> no direct service detected
- `POST /rpc/aster-optimized-long-stateful-monitor` -> `rpc_aster_optimized_long_stateful_monitor` [ admin] -> no direct service detected
- `GET /rpc/aster-optimized-long-regime-diagnostic-preview` -> `rpc_aster_optimized_long_regime_diagnostic_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-optimized-long-regime-diagnostic-preview` -> `rpc_aster_optimized_long_regime_diagnostic_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-forward-short-monitor-preview` -> `rpc_aster_paper_trading_forward_short_monitor_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-forward-short-monitor-preview` -> `rpc_aster_paper_trading_forward_short_monitor_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-stateful-session-monitor` -> `rpc_aster_paper_trading_stateful_session_monitor` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-stateful-session-monitor` -> `rpc_aster_paper_trading_stateful_session_monitor` [ admin] -> no direct service detected
- `POST /rpc/aster-agent-command-center-preview` -> `rpc_aster_agent_command_center_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-demo-testnet-readiness-preview` -> `rpc_aster_demo_testnet_readiness_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-demo-testnet-readiness-preview` -> `rpc_aster_demo_testnet_readiness_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-demo-order-intent-validator-preview` -> `rpc_aster_demo_order_intent_validator_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-demo-order-intent-validator-preview` -> `rpc_aster_demo_order_intent_validator_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-forward-reality-comparison-preview` -> `rpc_aster_forward_reality_comparison_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-forward-reality-comparison-preview` -> `rpc_aster_forward_reality_comparison_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-selected-short-fade-forward-monitor-preview` -> `rpc_aster_selected_short_fade_forward_monitor_preview` [ admin] -> no direct service detected
- `POST /rpc/aster-selected-short-fade-forward-monitor-preview` -> `rpc_aster_selected_short_fade_forward_monitor_preview` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-executor-confirm` -> `rpc_aster_paper_trading_executor_confirm` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-executor-confirm` -> `rpc_aster_paper_trading_executor_confirm` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-optimizer-and-executor` -> `rpc_aster_paper_trading_optimizer_and_executor` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-optimizer-and-executor` -> `rpc_aster_paper_trading_optimizer_and_executor` [ admin] -> no direct service detected
- `GET /rpc/aster-paper-trading-optimizer-executor-confirm` -> `rpc_aster_paper_trading_optimizer_executor_confirm` [ admin] -> no direct service detected
- `POST /rpc/aster-paper-trading-optimizer-executor-confirm` -> `rpc_aster_paper_trading_optimizer_executor_confirm` [ admin] -> no direct service detected
- `GET /rpc/scrapling-label-enrichment-preview` -> `rpc_scrapling_label_enrichment_preview` [ admin] -> no direct service detected
- `POST /rpc/scrapling-label-enrichment-preview` -> `rpc_scrapling_label_enrichment_preview` [ admin] -> no direct service detected
- `GET /rpc/dexscreener-enrichment-preview` -> `rpc_dexscreener_enrichment_preview` [ admin] -> no direct service detected
- `POST /rpc/dexscreener-enrichment-preview` -> `rpc_dexscreener_enrichment_preview` [ admin] -> no direct service detected
- `GET /rpc/dexscreener-enrichment-batch-preview` -> `rpc_dexscreener_enrichment_batch_preview` [ admin] -> no direct service detected
- `POST /rpc/dexscreener-enrichment-batch-preview` -> `rpc_dexscreener_enrichment_batch_preview` [ admin] -> no direct service detected
- `GET /rpc/dexscreener-first-discovery-preview` -> `rpc_dexscreener_first_discovery_preview` [ admin] -> no direct service detected
- `POST /rpc/dexscreener-first-discovery-preview` -> `rpc_dexscreener_first_discovery_preview` [ admin] -> no direct service detected
- `GET /rpc/dexscreener-score-composition-diagnostic-preview` -> `rpc_dexscreener_score_composition_diagnostic_preview` [ admin] -> no direct service detected
- `POST /rpc/dexscreener-score-composition-diagnostic-preview` -> `rpc_dexscreener_score_composition_diagnostic_preview` [ admin] -> no direct service detected
- `GET /rpc/dexscreener-threshold-calibration-preview` -> `rpc_dexscreener_threshold_calibration_preview` [ admin] -> no direct service detected
- `POST /rpc/dexscreener-threshold-calibration-preview` -> `rpc_dexscreener_threshold_calibration_preview` [ admin] -> no direct service detected
- `GET /rpc/local-behavioral-candidate-funnel-expansion-preview` -> `rpc_local_behavioral_candidate_funnel_expansion_preview` [ admin] -> no direct service detected
- `POST /rpc/local-behavioral-candidate-funnel-expansion-preview` -> `rpc_local_behavioral_candidate_funnel_expansion_preview` [ admin] -> no direct service detected
- `GET /rpc/on-demand-behavioral-scoring-preview` -> `rpc_on_demand_behavioral_scoring_preview` [ admin] -> no direct service detected
- `POST /rpc/on-demand-behavioral-scoring-preview` -> `rpc_on_demand_behavioral_scoring_preview` [ admin] -> no direct service detected
- `GET /rpc/behavioral-funnel-intake-and-backfill-plan-preview` -> `rpc_behavioral_funnel_intake_and_backfill_plan_preview` [ admin] -> no direct service detected
- `POST /rpc/behavioral-funnel-intake-and-backfill-plan-preview` -> `rpc_behavioral_funnel_intake_and_backfill_plan_preview` [ admin] -> no direct service detected
- `GET /rpc/confirm-bounded-raw-context-collection` -> `rpc_confirm_bounded_raw_context_collection` [ admin] -> no direct service detected
- `POST /rpc/confirm-bounded-raw-context-collection` -> `rpc_confirm_bounded_raw_context_collection` [ admin] -> no direct service detected
- `POST /rpc/aster-source-wallet-token-flow-collection` -> `rpc_aster_source_wallet_token_flow_collection` [ admin] -> `run_aster_source_wallet_token_flow_collection`
- `POST /rpc/unknown-swap-attribution/enrich` -> `rpc_unknown_swap_attribution_enrich` [ admin] -> `enrich_unknown_swap_attribution_targets`
- `GET /rpc/swap-router-code-fingerprints` -> `rpc_swap_router_code_fingerprints` [ read] -> `get_unknown_swap_router_code_fingerprints`
- `GET /rpc/swap-router-family-investigation` -> `rpc_swap_router_family_investigation` [ read] -> `get_unknown_swap_router_family_investigation`
- `GET /rpc/swap-venue-public-evidence` -> `rpc_swap_venue_public_evidence` [ read] -> `get_swap_venue_public_evidence`
- `GET /rpc/swap-venue-public-evidence-scan` -> `rpc_swap_venue_public_evidence_scan` [ read] -> `scan_swap_venue_public_evidence`
- `GET /rpc/swap-venue-mapping-drafts` -> `rpc_swap_venue_mapping_drafts` [ read] -> `get_swap_venue_mapping_drafts`
- `GET /rpc/swap-venue-official-source-corroboration` -> `rpc_swap_venue_official_source_corroboration` [ read] -> `corroborate_swap_venue_official_sources`
- `GET /rpc/source-backed-venue-mapping/admin-review-queue` -> `rpc_source_backed_venue_mapping_admin_review_queue` [ admin] -> `get_source_backed_venue_mapping_admin_review_queue`
- `GET /rpc/source-backed-venue-mappings` -> `rpc_source_backed_venue_mappings` [ read] -> `get_source_backed_venue_mappings`
- `GET /rpc/source-backed-venue-mapping/preview` -> `rpc_source_backed_venue_mapping_preview` [ read] -> `preview_source_backed_venue_mapping`
- `POST /rpc/source-backed-venue-mapping` -> `rpc_source_backed_venue_mapping` [ admin] -> `upsert_source_backed_venue_mapping`
- `POST /rpc/source-backed-venue-mapping/confirm-guided-review` -> `rpc_confirm_guided_venue_review` [ admin] -> `confirm_guided_venue_review`
- `POST /rpc/source-backed-venue-mapping/confirm-guided-reviews` -> `rpc_confirm_guided_venue_reviews` [ admin] -> `confirm_guided_venue_reviews_batch`
- `GET /rpc/exact-swap-ingestion-plan` -> `rpc_exact_swap_ingestion_plan` [ read] -> `get_exact_swap_ingestion_plan`
- `POST /rpc/bounded-exact-swap-transfer-collection` -> `rpc_bounded_exact_swap_transfer_collection` [ admin] -> `run_bounded_exact_swap_transfer_collection`
- `GET /rpc/token-metadata-enrichment-plan` -> `rpc_token_metadata_enrichment_plan` [ admin] -> `get_token_metadata_enrichment_plan`
- `POST /rpc/token-metadata-enrichment-plan` -> `rpc_token_metadata_enrichment_plan` [ admin] -> `get_token_metadata_enrichment_plan`
- `POST /rpc/token-metadata-enrichment` -> `rpc_token_metadata_enrichment` [ admin] -> `enrich_token_metadata_from_local_observations`
- `GET /rpc/token-market-local-candidate-metadata-repair-plan` -> `rpc_token_market_local_candidate_metadata_repair_plan` [ admin] -> `get_token_market_local_candidate_metadata_repair_plan`
- `POST /rpc/token-market-local-candidate-metadata-repair-plan` -> `rpc_token_market_local_candidate_metadata_repair_plan` [ admin] -> `get_token_market_local_candidate_metadata_repair_plan`
- `POST /rpc/token-market-local-candidate-metadata-repair` -> `rpc_token_market_local_candidate_metadata_repair` [ admin] -> `enrich_token_metadata_for_local_candidate_repair`
- `GET /rpc/data-jobs` -> `rpc_data_jobs` [ read] -> `get_data_jobs`
- `GET /rpc/auto-enrich/status` -> `rpc_auto_enrich_status` [ read] -> `get_auto_enrich_status`
- `POST /rpc/enrich-labels` -> `enrich_labelled_wallets_rpc` [ admin] -> `enrich_labeled_wallets_rpc`
- `POST /rpc/refresh-wallet-state-audit-targets` -> `refresh_wallet_state_audit_targets_rpc` [ admin] -> `refresh_rpc_wallet_state_audit_targets`
- `POST /rpc/enrich-priority` -> `enrich_priority_rpc` [ admin] -> `enrich_priority_entities_rpc`
- `POST /rpc/enrich-chain-gaps` -> `enrich_priority_chain_gaps_rpc` [ admin] -> `enrich_priority_entity_chain_gaps_rpc`
- `POST /rpc/auto-enrich/start` -> `start_priority_auto_enrich` [ admin] -> `start_auto_enrich_priority`
- `POST /rpc/auto-enrich/stop` -> `stop_priority_auto_enrich` [ admin] -> `stop_auto_enrich_priority`
- `GET /labels/ledger` -> `label_ledger_status` [ read] -> `get_label_ledger_summary`
- `GET /labels/candidates` -> `label_candidates` [ read] -> `get_label_candidates`
- `GET /labels/candidates/audit` -> `label_candidates_audit` [ read] -> `get_label_candidate_audit`
- `GET /labels/candidates/quality-report` -> `label_candidates_quality_report` [ read] -> `get_label_candidate_quality_report`
- `GET /labels/candidates/review-dashboard` -> `label_candidates_review_dashboard` [ read] -> `get_label_candidate_review_dashboard`
- `GET /labels/candidates/promotion-impact` -> `label_candidates_promotion_impact` [ read] -> `preview_label_candidate_promotion_impact`
- `POST /labels/candidates/consolidate-duplicates` -> `label_candidates_consolidate_duplicates` [ admin] -> `consolidate_label_candidate_duplicates_job`
- `GET /labels/candidates/promotion-review` -> `label_candidates_promotion_review` [ read] -> `review_label_candidate_promotions`
- `GET /labels/candidates/strict-promotion-review` -> `label_candidates_strict_promotion_review` [ read] -> `review_strict_label_candidate_promotions`
- `GET /labels/candidates/automation-plan` -> `label_candidates_automation_plan` [ read] -> `plan_label_candidate_automation`
- `GET /labels/candidates/corroborate` -> `label_candidates_corroborate` [ read] -> `corroborate_label_candidates`
- `POST /labels/candidates/corroborate` -> `label_candidates_corroborate_persist` [ admin] -> `corroborate_label_candidates`
- `POST /labels/candidates/corroborate-job` -> `label_candidates_corroborate_job` [ admin] -> `corroborate_label_candidates_job`
- `GET /labels/candidates/evidence` -> `label_candidates_evidence` [ read] -> `get_label_candidate_evidence`
- `GET /labels/candidates/evidence-scores` -> `label_candidates_evidence_scores` [ read] -> `get_label_candidate_evidence_scores`
- `GET /labels/candidates/verified-review-queue` -> `label_candidates_verified_review_queue` [ read] -> `get_verified_label_candidate_review_queue`
- `GET /labels/candidates/corroboration-queue` -> `label_candidates_corroboration_queue` [ read] -> `get_label_corroboration_queue`
- `GET /labels/acquisition-plan` -> `label_acquisition_plan` [ read] -> `get_label_acquisition_plan`
- `POST /labels/acquire-sources` -> `label_acquire_sources` [ admin] -> `acquire_label_sources_job`
- `POST /labels/candidates/promote` -> `label_candidates_promote` [ admin] -> `promote_label_candidates`
- `POST /labels/build` -> `build_labels` [ admin] -> `build_label_ledger_job`
- `POST /labels/expand` -> `expand_labels` [ admin] -> no direct service detected
- `POST /labels/ingest-seeds` -> `ingest_label_seeds` [ admin] -> `ingest_seed_transactions`
- `GET /latest-block/{chain}` -> `latest_block` [ read] -> `get_latest_block`
- `GET /wallet/{address}` -> `wallet_analyzer` [ read] -> `analyze_wallet_full`, `compute_token_concentration`, `compute_risk_score`, `compute_smart_label`
- `POST /ingest/recent/{chain}` -> `ingest_recent` [ admin] -> `ingest_recent_blocks`, `confirm_required_detail`
- `POST /ingest/exact-swap-window/{chain}` -> `ingest_exact_swap_window` [ admin] -> `ingest_exact_swap_window_job`, `confirm_required_detail`
- `POST /ingest/exact-swap-progressive` -> `ingest_exact_swap_progressive` [ admin] -> `run_exact_swap_ingestion_plan_once`, `confirm_required_detail`
- `POST /ingest/{chain}/{block_number}` -> `ingest_single` [ admin] -> `ingest_block`, `confirm_required_detail`
- `POST /auto-ingest/start` -> `auto_ingest_start` [ admin] -> `start_auto_ingest`

### `backend/routers/vision.py`
- `POST /analyze` -> `analyze_chart` [ read] -> no direct service detected
- `GET /latest` -> `latest_analysis` [ read] -> no direct service detected
- `GET /history` -> `analysis_history` [ read] -> no direct service detected
- `POST /auto-scan` -> `auto_scan` [ read] -> no direct service detected
- `GET /test` -> `test_gemini` [ read] -> no direct service detected
- `POST /agent` -> `vision_agent` [ read] -> no direct service detected
- `POST /autoscan/start` -> `start_autoscan` [ read] -> no direct service detected
- `POST /autoscan/stop` -> `stop_autoscan` [ read] -> no direct service detected
- `GET /autoscan/status` -> `autoscan_status` [ read] -> no direct service detected

## Endpoint Groups

### `agent`
- POST /agent (backend/routers/vision.py:vision_agent)

### `analyze`
- POST /analyze (backend/routers/vision.py:analyze_chart)

### `auto-ingest`
- POST /auto-ingest/start (backend/routers/onchain.py:auto_ingest_start)

### `auto-scan`
- POST /auto-scan (backend/routers/vision.py:auto_scan)

### `autoscan`
- POST /autoscan/start (backend/routers/vision.py:start_autoscan)
- POST /autoscan/stop (backend/routers/vision.py:stop_autoscan)
- GET /autoscan/status (backend/routers/vision.py:autoscan_status)

### `collectors`
- GET /collectors/status (backend/routers/alpha_lab.py:_collectors_status)

### `coverage`
- GET /coverage (backend/routers/arkham.py:arkham_coverage)

### `db`
- GET /db/stats (backend/routers/arkham.py:arkham_db_stats)
- POST /db/reload (backend/routers/arkham.py:arkham_db_reload)

### `detective`
- POST /detective/whale (backend/routers/intel.py:investigate_whale)

### `entity`
- GET /entity/{entity_slug} (backend/routers/arkham.py:arkham_entity)

### `events`
- POST /events/dedupe (backend/routers/alpha_lab.py:_events_dedupe)

### `flows`
- GET /flows (backend/routers/arkham.py:arkham_flows)

### `gold`
- GET /gold (backend/routers/news.py:get_gold_analysis)
- GET /gold/bias (backend/routers/news.py:get_gold_bias)
- POST /gold/refresh (backend/routers/news.py:refresh_gold_analysis)
- GET /gold/latest (backend/routers/news.py:get_latest_cached)

### `history`
- GET /history (backend/routers/chat.py:get_history)
- DELETE /history (backend/routers/chat.py:clear_history)
- GET /history (backend/routers/vision.py:analysis_history)

### `hunt`
- POST /hunt/listings (backend/routers/intel.py:hunt_binance_listings)

### `ingest`
- POST /ingest/recent/{chain} (backend/routers/onchain.py:ingest_recent)
- POST /ingest/exact-swap-window/{chain} (backend/routers/onchain.py:ingest_exact_swap_window)
- POST /ingest/exact-swap-progressive (backend/routers/onchain.py:ingest_exact_swap_progressive)
- POST /ingest/{chain}/{block_number} (backend/routers/onchain.py:ingest_single)

### `intelligence`
- GET /intelligence (backend/routers/alpha_lab.py:_premium_intelligence)

### `investigate`
- POST /investigate (backend/routers/intel.py:launch_investigation)

### `investigations`
- GET /investigations/active (backend/routers/intel.py:list_active_investigations)
- GET /investigations/{inv_id} (backend/routers/intel.py:get_investigation_status)

### `keyboard`
- POST /keyboard (backend/routers/desktop.py:keyboard_input)

### `labels`
- GET /labels/ledger (backend/routers/onchain.py:label_ledger_status)
- GET /labels/candidates (backend/routers/onchain.py:label_candidates)
- GET /labels/candidates/audit (backend/routers/onchain.py:label_candidates_audit)
- GET /labels/candidates/quality-report (backend/routers/onchain.py:label_candidates_quality_report)
- GET /labels/candidates/review-dashboard (backend/routers/onchain.py:label_candidates_review_dashboard)
- GET /labels/candidates/promotion-impact (backend/routers/onchain.py:label_candidates_promotion_impact)
- POST /labels/candidates/consolidate-duplicates (backend/routers/onchain.py:label_candidates_consolidate_duplicates)
- GET /labels/candidates/promotion-review (backend/routers/onchain.py:label_candidates_promotion_review)
- GET /labels/candidates/strict-promotion-review (backend/routers/onchain.py:label_candidates_strict_promotion_review)
- GET /labels/candidates/automation-plan (backend/routers/onchain.py:label_candidates_automation_plan)
- GET /labels/candidates/corroborate (backend/routers/onchain.py:label_candidates_corroborate)
- POST /labels/candidates/corroborate (backend/routers/onchain.py:label_candidates_corroborate_persist)
- POST /labels/candidates/corroborate-job (backend/routers/onchain.py:label_candidates_corroborate_job)
- GET /labels/candidates/evidence (backend/routers/onchain.py:label_candidates_evidence)
- GET /labels/candidates/evidence-scores (backend/routers/onchain.py:label_candidates_evidence_scores)
- GET /labels/candidates/verified-review-queue (backend/routers/onchain.py:label_candidates_verified_review_queue)
- GET /labels/candidates/corroboration-queue (backend/routers/onchain.py:label_candidates_corroboration_queue)
- GET /labels/acquisition-plan (backend/routers/onchain.py:label_acquisition_plan)
- POST /labels/acquire-sources (backend/routers/onchain.py:label_acquire_sources)
- POST /labels/candidates/promote (backend/routers/onchain.py:label_candidates_promote)
- ... 3 more

### `latest`
- GET /latest (backend/routers/vision.py:latest_analysis)

### `latest-block`
- GET /latest-block/{chain} (backend/routers/onchain.py:latest_block)

### `launch`
- POST /launch/ninjatrader (backend/routers/desktop.py:launch_ninjatrader)
- POST /launch/ninjatrader/full (backend/routers/desktop.py:launch_ninjatrider_full)
- POST /launch/app (backend/routers/desktop.py:launch_app)

### `list`
- GET /list (backend/routers/entity.py:entity_list)

### `lookup`
- GET /lookup/{address} (backend/routers/arkham.py:arkham_lookup)

### `message`
- POST /message (backend/routers/chat.py:send_message)

### `mouse`
- POST /mouse/click (backend/routers/desktop.py:mouse_click)

### `mt5`
- GET /mt5/price/{symbol} (backend/routers/market.py:get_price)
- GET /mt5/account (backend/routers/market.py:get_account)
- GET /mt5/positions (backend/routers/market.py:get_positions)
- GET /mt5/symbols (backend/routers/market.py:get_symbols)
- GET /mt5/health (backend/routers/market.py:mt5_health)

### `ninjatrader`
- POST /ninjatrader/indicator (backend/routers/desktop.py:nt8_indicator)
- POST /ninjatrader/switch (backend/routers/desktop.py:nt8_switch)
- POST /ninjatrader/snapshot (backend/routers/desktop.py:nt8_snapshot)
- POST /ninjatrader/refresh (backend/routers/desktop.py:nt8_refresh)
- POST /ninjatrader/zoom (backend/routers/desktop.py:nt8_zoom)
- POST /ninjatrader/login (backend/routers/desktop.py:nt8_login)
- POST /ninjatrader/move (backend/routers/desktop.py:nt8_move)
- POST /ninjatrader/resize (backend/routers/desktop.py:nt8_resize)
- POST /ninjatrader/timeframe (backend/routers/desktop.py:nt8_timeframe)
- GET /ninjatrader/data-box (backend/routers/desktop.py:nt8_data_box)
- POST /ninjatrader (backend/routers/market.py:receive_ninjatrader_data)
- GET /ninjatrader (backend/routers/market.py:get_ninjatrader_data)

### `prediction`
- GET /prediction/markets (backend/routers/alpha_lab.py:_prediction_markets)

### `premium`
- GET /premium/stats (backend/routers/alpha_lab.py:_premium_stats)

### `risk`
- POST /risk/token (backend/routers/alpha_lab.py:_risk_token)

### `rpc`
- GET /rpc/status (backend/routers/onchain.py:rpc_status)
- GET /rpc/wallet-state (backend/routers/onchain.py:rpc_wallet_state)
- GET /rpc/wallet-source (backend/routers/onchain.py:rpc_wallet_source)
- GET /rpc/wallet-quality-audit (backend/routers/onchain.py:rpc_wallet_quality_audit)
- GET /rpc/label-source-gaps (backend/routers/onchain.py:rpc_label_source_gaps)
- GET /rpc/wallet-state-audit (backend/routers/onchain.py:rpc_wallet_state_audit)
- POST /rpc/backfill-wallet-source-attribution (backend/routers/onchain.py:rpc_backfill_wallet_source_attribution)
- POST /rpc/backfill-wallet-label-sources (backend/routers/onchain.py:rpc_backfill_wallet_label_sources)
- POST /rpc/stage-label-source-gap-candidates (backend/routers/onchain.py:rpc_stage_label_source_gap_candidates)
- POST /rpc/corroborate-label-source-gap-candidates (backend/routers/onchain.py:rpc_corroborate_label_source_gap_candidates)
- POST /rpc/backfill-label-source-gap-candidate-urls (backend/routers/onchain.py:rpc_backfill_label_source_gap_candidate_urls)
- GET /rpc/entity-coverage (backend/routers/onchain.py:rpc_entity_coverage)
- GET /rpc/entity-flow (backend/routers/onchain.py:rpc_entity_flow)
- GET /rpc/entity-gaps (backend/routers/onchain.py:rpc_entity_gaps)
- GET /rpc/entity-chain-gaps (backend/routers/onchain.py:rpc_entity_chain_gaps)
- GET /rpc/entity-chain-gap-verification (backend/routers/onchain.py:rpc_entity_chain_gap_verification)
- GET /rpc/data-readiness (backend/routers/onchain.py:rpc_data_readiness)
- GET /rpc/manipulation-readiness (backend/routers/onchain.py:rpc_manipulation_readiness)
- POST /rpc/auto-fill-gaps (backend/routers/onchain.py:rpc_auto_fill_gaps)
- GET /rpc/pre-pump-accumulation-scan (backend/routers/onchain.py:rpc_pre_pump_accumulation_scan)
- ... 936 more

### `run`
- POST /run (backend/routers/agents.py:run_agent)

### `scrape`
- POST /scrape/full (backend/routers/arkham.py:trigger_full_scrape)
- POST /scrape/delta (backend/routers/arkham.py:trigger_delta_scan)

### `scrapling`
- GET /scrapling/probe (backend/routers/arkham.py:arkham_scrapling_probe)

### `screenshot`
- POST /screenshot (backend/routers/desktop.py:take_screenshot)
- POST /screenshot/analyze (backend/routers/desktop.py:screenshot_and_analyze)

### `screenshots`
- GET /screenshots (backend/routers/desktop.py:list_screenshots)
- GET /screenshots/latest (backend/routers/desktop.py:latest_screenshot)

### `search`
- GET /search (backend/routers/arkham.py:arkham_search)
- GET /search (backend/routers/news.py:search_news)

### `sentiment`
- POST /sentiment/scan (backend/routers/intel.py:scan_sentiment)
- POST /sentiment/funding-spike (backend/routers/intel.py:investigate_funding_spike)

### `signals`
- GET /signals (backend/routers/agents.py:?)
- GET /signals/stats (backend/routers/agents.py:?)
- GET /signals (backend/routers/arkham.py:arkham_signals)
- GET /signals/recent (backend/routers/intel.py:get_recent_signals)
- GET /signals (backend/routers/market.py:get_signals)

### `simulate`
- POST /simulate/prediction-copy (backend/routers/alpha_lab.py:_simulate_prediction_copy)
- POST /simulate/manipulation (backend/routers/alpha_lab.py:_simulate_manipulation)

### `smart-money`
- GET /smart-money (backend/routers/arkham.py:arkham_smart_money)

### `snapshot`
- GET /snapshot/{coin} (backend/routers/market.py:get_snapshot)

### `snapshots`
- GET /snapshots (backend/routers/market.py:get_all_snapshots)

### `source-backed-inventory`
- GET /source-backed-inventory (backend/routers/arkham.py:arkham_source_backed_inventory)

### `sources`
- GET /sources (backend/routers/alpha_lab.py:_sources_alias)

### `status`
- GET /status (backend/routers/agents.py:?)
- GET /status (backend/routers/arkham.py:arkham_status)
- GET /status (backend/routers/chat.py:chat_status)
- GET /status (backend/routers/desktop.py:?)
- GET /status (backend/routers/intel.py:get_agents_status)

### `stop`
- POST /stop (backend/routers/agents.py:stop_agent)

### `test`
- POST /test/signal (backend/routers/intel.py:test_signal_broadcast)
- GET /test (backend/routers/vision.py:test_gemini)

### `token`
- GET /token/{symbol} (backend/routers/arkham.py:arkham_token)
- GET /token/{symbol}/transfers (backend/routers/arkham.py:arkham_token_transfers)
- GET /token/{symbol}/holders (backend/routers/arkham.py:arkham_token_holders)

### `tools`
- GET /tools (backend/routers/desktop.py:list_tools)

### `usage`
- POST /usage/event (backend/routers/alpha_lab.py:_usage_event)
- GET /usage/stats (backend/routers/alpha_lab.py:_usage_stats)

### `wallet`
- GET /wallet/probe/{wallet} (backend/routers/alpha_lab.py:_wallet_probe)
- POST /wallet/verify (backend/routers/alpha_lab.py:_wallet_verify)
- GET /wallet/ownership/{wallet} (backend/routers/alpha_lab.py:_wallet_ownership)
- GET /wallet/copy-plan/{wallet} (backend/routers/alpha_lab.py:_wallet_copy_plan)
- GET /wallet/copy-backtest/{wallet} (backend/routers/alpha_lab.py:_wallet_copy_backtest)
- GET /wallet/automation-plan/{wallet} (backend/routers/alpha_lab.py:_wallet_automation_plan)
- GET /wallet/surface/{wallet} (backend/routers/alpha_lab.py:_wallet_surface)
- GET /wallet/graph/{wallet} (backend/routers/alpha_lab.py:_wallet_graph)
- GET /wallet/status (backend/routers/alpha_lab.py:_wallet_status)
- GET /wallet/discovery (backend/routers/alpha_lab.py:_wallet_discovery)
- GET /wallet/summary/{address} (backend/routers/alpha_lab.py:_wallet)
- GET /wallet/{address} (backend/routers/onchain.py:wallet_analyzer)

### `{slug}`
- GET /{slug} (backend/routers/entity.py:entity_detail)
- GET /{slug}/portfolio (backend/routers/entity.py:entity_portfolio)
- GET /{slug}/wallets (backend/routers/entity.py:entity_wallets)
- GET /{slug}/flows (backend/routers/entity.py:entity_flows)
- GET /{slug}/history (backend/routers/entity.py:entity_history)

## Frontend API Calls

- `/access_token` <- `frontend/src/App.tsx`
- `/alpha/collectors/status` <- `frontend/src/pages/AlphaLab.tsx`
- `/alpha/risk/token` <- `frontend/src/pages/AlphaLab.tsx`
- `/alpha/simulate/prediction-copy` <- `frontend/src/pages/AlphaLab.tsx`
- `/alpha/usage/event` <- `frontend/src/pages/AlphaLab.tsx`
- `/alpha/usage/stats?limit=500` <- `frontend/src/pages/AlphaLab.tsx`
- `/api/market/prices` <- `frontend/src/components/layout/TopBar.tsx`
- `/arkham/coverage` <- `frontend/src/pages/AlphaLab.tsx`
- `/content-type` <- `frontend/src/services/api.ts`
- `/market/mt5/account` <- `frontend/src/services/marketService.ts`
- `/market/mt5/positions` <- `frontend/src/services/marketService.ts`
- `/market/snapshot` <- `frontend/src/services/marketService.ts`
- `/market/symbols` <- `frontend/src/services/marketService.ts`
- `/onchain/labels/acquisition-plan?limit=12&min_trusted_per_entity=100` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/labels/candidates/automation-plan?limit=100` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/labels/candidates/corroboration-queue?limit=12` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/labels/candidates/evidence-scores?limit=12&max_bundles_per_candidate=8` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/labels/candidates/promotion-review?limit=30&min_score=70` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/labels/candidates/quality-report?limit=25` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/labels/candidates/strict-promotion-review?limit=50` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/adaptive-manipulation-case-file?limit=3&wallet_limit=5&breakout_threshold_pct=500&baseline_swaps=12&confirmation_swaps=3&pre_event_swaps=20&exit_after_swaps_options=3,10,20` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/auto-enrich/status` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/data-jobs?limit=8` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/data-readiness?limit=12&min_confidence=medium` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/entity-chain-gap-verification?min_confidence=medium&limit=12&stale_after_hours=24` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/entity-chain-gaps?min_confidence=medium&limit=12` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/entity-coverage?limit=80&min_confidence=medium` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/entity-gaps?min_confidence=medium` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/manipulation-readiness?limit=12` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/status` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/wallet-quality-audit?limit=8` <- `frontend/src/pages/AlphaLab.tsx`
- `/onchain/rpc/wallet-state-audit?limit=8&stale_after_hours=24` <- `frontend/src/pages/AlphaLab.tsx`
- `/security/login` <- `frontend/src/App.tsx`
- `/security/status` <- `frontend/src/App.tsx`
- `/wallet` <- `frontend/src/pages/AlphaLab.tsx`

## Service Function Index

- `backend/services/alpha_lab.py`: `_apply_probability_cost`, `_boolish`, `_bounded_probability`, `_confidence`, `_dedupe_risk_flags`, `_float`, `_float_or_none`, `_hash_payload`, `_normalize_ts`, `_percent`, `_pick_first`, `_safe_ratio`, `_semantic_key`, `_utc_now`, `analyze_token_risk`, `dedupe_alpha_events`, `get_alpha_sources`, `get_alpha_strategy`, ... +2
- `backend/services/alpha_premium_data.py`: `_cached`, `_cielo_feed`, `_cielo_key`, `_compute_cielo_stats`, `_etherscan_balance`, `_etherscan_key`, `_etherscan_token_holdings`, `_gini_coefficient`, `_request`, `_set_cache`, `_zerion_auth`, `_zerion_portfolio`, `get_premium_alpha_stats`
- `backend/services/alpha_risk.py`: `_build_source_trace`, `_missing_token_proofs`, `flag`
- `backend/services/alpha_sellability.py`: `_compute_sellability_consensus`, `_fetch_dexscreener`, `_fetch_honeypot_api`, `_http_html`, `_http_json`, `_parse_with_html`, `_parse_with_scrapling`, `_scrape_explorer`, `_sellability_auto_flags`, `probe_token_sellability`
- `backend/services/alpha_simulation.py`: `check_max_trade_pct`, `check_ranges`, `simulate_prediction_copy`
- `backend/services/arkham_source_registry.py`: `_cache_summary`, `_iso_from_mtime`, `_ledger_summary`, `_manual_label_summary`, `_safe_json`, `_scan_files`, `_source_layers`, `_source_name`, `get_arkham_source_backed_inventory`
- `backend/services/arkham_tracker.py`: `__init__`, `_check_flow_anomaly`, `_forward_signal`, `_track_entity_flow`, `add_inflow`, `add_outflow`, `analyze_movement`, `backtest_tracker`, `direction`, `eth_transaction_listener`, `get_all_entities`, `get_arkham_tracker`, `get_entity`, `get_entity_flow_summary`, `get_exchange_flow_signals`, `get_recent_signals`, `get_smart_money_activity`, `get_stats`, ... +9
- `backend/services/collector.py`: `_get_footprint_manager`, `_get_smart_engine`, `_level_px_sz`, `_metrics`, `_spread`, `create_collector_tasks`, `get_collector_state`, `get_market_snapshot`, `handle_active_asset_ctx`, `handle_l2_book`, `handle_trades`, `process_message`, `run_collector`, `snapshot`, `snapshot_loop`, `status`, `subscribe_coin`
- `backend/services/core_equity_guards.py`: `confirm_required_detail`, `disabled_runtime_surfaces`, `dry_run_raw_data_collection_payload`
- `backend/services/entity_intelligence.py`: `_analyze_wallet`, `_get_db`, `_init_db`, `_save_snapshot`, `_seed_labels`, `analyze_entity`, `get_entity_labels`, `get_entity_list`, `get_entity_snapshot`
- `backend/services/footprint.py`: `_parse_level`, `add_trade`, `capture`, `delta`, `finalize`, `flush`, `get_bars`, `get_footprint`, `get_heatmap`, `get_imbalance`, `get_latest_bar`, `get_or_create`, `imbalance`, `process_orderbook`, `process_trade`, `total_volume`, `update`
- `backend/services/intel_aggregator.py`: `_batch_loop`, `_cleanup_loop`, `_emit_signal`, `_get_signature`, `get_aggregator`, `is_similar_to`, `run_loop`, `set_broadcast_callback`, `start`, `start_aggregator`, `start_auto_scan`, `stop`, `stop_aggregator`, `stop_auto_scan`, `submit_signal`
- `backend/services/label_expansion.py`: `_confidence_from_count`, `_insert_derived`, `_load_seed_labels`, `_relation_label`, `expand_labels`, `expand_labels_from_onchain`, `expand_labels_from_scrapling_transfers`
- `backend/services/label_ledger.py`: `_address_is_valid_for_chain`, `_apply_persisted_evidence_gate`, `_backup_label_ledger_db`, `_blockscout_address_url`, `_candidate_evidence_score_map`, `_candidate_source_key`, `_candidate_with_persisted_evidence`, `_chain_key`, `_confidence_rank`, `_corroborate_candidate`, `_entity_source_slug`, `_etherscan_activity_evidence`, `_etherscan_api_key`, `_etherscan_get`, `_evidence_source_key`, `_explorer_address_url`, `_explorer_html_evidence`, `_http_text`, ... +38
- `backend/services/multi_exchange.py`: `_safe_float`, `aggregation_loop`, `fetch_binance_funding`, `fetch_binance_liquidations`, `fetch_binance_new_listings`, `fetch_binance_oi`, `fetch_bybit_funding`, `get_aggr_state`, `run_aggregation_cycle`
- `backend/services/onchain_chains.py`: `evm_rpc_url`, `evm_rpc_urls`, `normalize_chain`, `rpc_source_label`
- `backend/services/onchain_coverage.py`: `_new_coverage_entry`, `_source_bucket`, `_source_names`, `get_entity_gap_report_from_dbs`, `get_rpc_entity_coverage_from_dbs`
- `backend/services/onchain_engine.py`: `_abi_function_signatures`, `_add_counterparty`, `_address_stat`, `_admin_review_queue_item`, `_aggregate_by`, `_amount_usd_scoreable_sql`, `_analyze_wallet_inner`, `_api_evidence_creator_address`, `_append_flow`, `_arkham_holders_chain`, `_aster_collection_token_addresses`, `_auto_enrich_loop`, `_auto_ingest_loop`, `_backup_onchain_db`, `_block_timestamp`, `_blockscout_address_hash`, `_blockscout_address_metadata`, `_blockscout_address_name`, ... +742
- `backend/services/onchain_entities.py`: `_clean`, `canonical_entity_name`, `entity_aliases`, `entity_in_clause`, `entity_matches`
- `backend/services/onchain_flows.py`: `get_entity_flow_surface_from_db`
- `backend/services/onchain_quality.py`: `activity_tier`, `address_kind`, `confidence_allows`, `data_quality_score`, `risk_flags`
- `backend/services/onchain_status.py`: `get_rpc_status_from_db`
- `backend/services/scrapling_intelligence.py`: `_request_json`, `_rpc_call`, `get_bsc_balance`, `get_bsc_transaction_count`, `get_btc_fees`, `get_coingecko_markets`, `get_coingecko_trending`, `get_defillama_protocols`, `get_defillama_yields`, `get_premium_intelligence`, `scrapling_probe_cielo`, `scrapling_probe_dexscreener`
- `backend/services/scrapling_probe.py`: `_build_probe_url`, `_capture_arkham_page`, `_categorize_xhr`, `_clean_text`, `_derive_token_flows`, `_derive_wallet_flags`, `_display_party_label`, `_downsample_balance_history`, `_entity_transfer_matches_target`, `_extract_page_summary`, `_extract_party_identity`, `_extract_texts`, `_history_bucket_label`, `_interesting_score`, `_json_safe`, `_load_normalized_snapshot`, `_load_scrapling`, `_matches_token_identifier`, ... +29
- `backend/services/seed_ingestion.py`: `_api_key`, `_ensure_onchain_schema`, `_fetch_seed_token_transfers`, `_fetch_seed_transactions`, `_load_seed_addresses`, `_upsert_wallet`, `ingest_seed_transactions`
- `backend/services/smart_engine.py`: `_add_signal`, `_detect_cascade`, `get_signals`, `on_trade`
- `backend/services/wallet_analyzer.py`: `_address_topic`, `_covalent_balances`, `_covalent_transactions`, `_decode_abi_string`, `_etherscan_balance_native`, `_etherscan_call`, `_etherscan_proxy_eth_call`, `_etherscan_tokenbalance`, `_etherscan_tokentx`, `_etherscan_txcount_native`, `_etherscan_txlist`, `_etherscan_url`, `_first_env`, `_get_cached_token_meta`, `_get_cached_wallet_token`, `_get_coingecko_price`, `_get_dexscreener_data`, `_get_token_age_days`, ... +19
- `backend/services/web_agent.py`: `_poll_agent_result`, `_save_investigation`, `cleanup_old`, `get_investigation_status`, `get_specialized_agents`, `get_web_agent`, `hunt_new_listings`, `init_web_agent`, `investigate_funding_spike`, `investigate_new_token`, `investigate_token_listing`, `investigate_whale_movement`, `list_active_investigations`, `run`, `scan_sentiment`
- `backend/services/websocket_manager.py`: `agent_progress`, `broadcast`, `connect`, `disconnect`, `get_active_count`, `intel_signal`, `list_connections`, `market_update`, `send_to_client`, `system_alert`
