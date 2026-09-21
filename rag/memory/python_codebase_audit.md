# Core Equity Python Codebase Audit

Last updated: 2026-05-23.

## 2026-05-23 - Python Folder Cleanup Before Aster Work

Purpose: clean the Python layout before extending the Aster data/API suite.

What changed:

- Added `rag/memory/python_file_structure_map.md` as the source-of-truth map for
  Python ownership and cleanup rules.
- Removed Python one-off patch scripts from `frontend/src/`; archived them under
  `scripts/archive/frontend_patches/`.
- Moved the real trading configuration implementation to
  `backend/config/trading.py`.
- Kept root `trading_config.py` as a compatibility wrapper so older imports do
  not break.
- Moved local Qwen review/benchmark implementations into `scripts/qwen/` while
  keeping root `scripts/*.py` compatibility wrappers for existing commands.
- Moved Tailscale ACL validation into `scripts/security/` while keeping the root
  wrapper used by existing docs.
- Cleaned Hermes/Cloudflare helper scripts so Cloudflare/Qwen credentials are
  read from environment variables instead of being hardcoded.
- Moved the MT5 bridge implementation into `integrations/mt5/bridge.py`, kept
  root `mt5_bridge.py` as a launcher, and moved MT5 settings to
  `configs/mt5/config.json`.
- Moved root backup/log/experiment/legacy artifacts into named folders.
- Archived empty placeholder root dirs `gateway/`, `tools/`, and `skills/`.
- Moved backend runtime log artifacts out of `backend/` into
  `logs/backend-runtime/`.
- Moved empty backend scratch DB artifacts into
  `tmp/cleanup-artifacts/backend-empty-dbs/`.
- Moved legacy `entity_labels.db` and `wallet_cache.db` out of
  `backend/services/` into `backend/data/legacy/`, preserving one-time fallback
  behavior.
- Added `integrations/README.md`, `integrations/mt5/README.md`, and
  `archives/README.md`.
- Added `PROJECT_STRUCTURE.md` as the top-level repository ownership map.
- Added local ownership maps for `backend/`, `backend/routers/`,
  `backend/services/`, `frontend/`, `frontend/src/`, `tests/`, `docs/`, and
  `agent/`.

Safety:

- No runtime endpoint behavior changed.
- No server launched.
- No package install.
- No DB write, provider/API call, label, mapping, signal, trade, wallet order or
  opt-in.

Next cleanup:

- Keep root launchers thin and side-effect-light.
- Continue shrinking `onchain_engine.py` one tested lane at a time.
- Put new Aster code under `backend/services/onchain/aster/`, not in the root
  facade.

## 2026-05-23 - Onchain Restructure Started For Aster Suite

Core Equity is preparing a cleaner Python structure before extending the Aster
data/API manipulation suite.

What changed:

- Added `backend/services/onchain/README.md` as the onchain package ownership
  map.
- Added `backend/services/onchain/REFACTOR_MAP.md` as the migration plan for
  the 99k-line `backend/services/onchain_engine.py` facade.
- Added `backend/services/onchain/aster/` as the reserved namespace for the
  Aster suite.
- Extracted official/static Aster reference anchors into
  `backend/services/onchain/aster/reference.py`.
- Kept compatibility re-exports in `services.onchain_engine`, including Aster
  constants and `_aster_dex_reference_addresses`.
- Updated `backend/services/SERVICE_CATALOG.md` so future agents know
  `onchain_engine.py` is now a legacy compatibility facade, not the place for
  new product lanes.

Validation:

- `py_compile` passed for `backend/services/onchain/aster/reference.py`,
  `backend/services/onchain/aster/__init__.py`, `backend/services/onchain_engine.py`,
  and `backend/routers/onchain.py`.
- Targeted Aster tests passed:
  - `test_aster_dex_fund_flow_radar_is_read_only_and_research_only`
  - `test_aster_dex_fund_flow_collection_is_dry_run_first_and_data_only`
  - `test_aster_dex_paginated_collection_runs_small_windows_data_only`
  - `test_aster_dex_flow_case_file_is_read_only_and_not_manipulation_proof`
  - `test_aster_cex_bridge_context_checks_binance_bitget_read_only`
  - `test_aster_source_wallet_token_flow_collection_is_bounded_and_data_only`

Safety:

- No runtime endpoint behavior changed.
- No DB write.
- No provider/API call.
- No label, mapping, signal, trade, wallet order or opt-in.

Next safe refactor:

- Move Aster runtime functions only after dependency injection is planned for
  `_rpc_evm_chain`, `_get_db`, `_table_exists`, `_token_metadata_for`,
  `_onchain_table_counts` and `_label_ledger_guard_counts`.
- Do not move the full Aster runtime block with a naive import, because tests
  patch `services.onchain_engine._rpc_evm_chain` and
  `services.onchain_engine.run_aster_dex_fund_flow_collection`.

## Latest Action

Current cleanup status:
- `backend/services/onchain_engine.py` is still large but now below 100k lines: current line count is about `99285`.
- The active extraction folder is `backend/services/onchain/`.
- Added `backend/services/onchain/README.md` as the ownership map so new work does not recreate existing lanes.
- Existing extracted modules now cover raw Swap evidence, second-window exact Swap evidence, Transfer context evidence/bridge, manipulation reliability/source-backed scoring design, shadow/backtest planning, UFLOKI outcome-window dry-run collection, manipulation data usability, pure manipulation verdict helpers, readiness builders, and the full manipulation readiness gate.
- Latest extraction: moved `get_manipulation_detection_readiness` into `backend/services/onchain/manipulation_readiness.py`.
- `onchain_engine.py` now imports extracted helpers/functions and keeps the same public names for compatibility.
- Current post-extraction line count for `onchain_engine.py`: about `99285`.
- The next cleanup must continue the strangler pattern, not a big rewrite.

Latest product/data patch:
- Added `get_manipulation_detection_source_backed_outcome_window_data_collection_dry_run` inside `backend/services/onchain/manipulation_reliability.py`.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-outcome-window-data-collection`.
- Product result: UFLOKI outcome windows are measurable in local raw Swap data but only partial quality; this is not a manipulation verdict and not a trade signal.
- Added `get_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context_dry_run` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-outcome-quality-repair-sync-liquidity-context`.
- Product result: the quality checkpoint shows the exact missing data: no local Sync rows and no local Mint/Burn liquidity rows for the UFLOKI pool.
- Added `get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-collection-plan`.
- Product result: the collection plan targets only damaged UFLOKI outcome windows with bounded Sync/Mint/Burn filters and blocks execution until full topic0 binding is verified.
- Added `get_manipulation_detection_source_backed_outcome_sync_mint_burn_topic_binding_checkpoint` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-mint-burn-topic-binding-checkpoint`.
- Product result: Sync/Mint/Burn topic binding is now complete, so the bounded lookup can be attempted later as dry-run/no-persistence.
- Added `get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review_queue` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/review`.
- Product result: persisted UFLOKI Sync/Mint evidence is now reviewed read-only with `194/194` payload/source/dedupe/pool bound rows and can move to outcome quality repair preview.
- Added `get_manipulation_detection_source_backed_outcome_quality_repair_preview` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-outcome-quality-repair-preview`.
- Product result: reviewed UFLOKI Sync/Mint context can repair all `3` damaged outcome windows in read-only mode, preparing a future repaired outcome dataset before shadow/backtest.
- Added `get_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset-schema-plan`.
- Product result: the future table `manipulation_repaired_outcome_windows` is planned read-only with `4` repaired/usable windows and no DDL/write.
- Added `create_manipulation_detection_source_backed_repaired_outcome_dataset_table` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/create`.
- Product result: DDL-only creation of the empty `manipulation_repaired_outcome_windows` table is implemented and validated; no repaired outcome rows are inserted.
- Added `insert_manipulation_detection_source_backed_repaired_outcome_dataset` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/insert`.
- Product result: dry-run-first repaired outcome insertion is implemented and validated; real confirmed mode inserts only `4` rows into `manipulation_repaired_outcome_windows` and blocks duplicates.
- Added `get_manipulation_detection_source_backed_repaired_outcome_dataset_review_queue` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/review`.
- Product result: the `4` repaired UFLOKI outcome rows are reviewed read-only and ready for a future shadow backtest preview; no score/signal/trade is created.
- Added `get_manipulation_detection_source_backed_shadow_backtest_preview` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-preview`.
- Product result: UFLOKI can now be evaluated in-memory against repaired outcome windows; current preview classifies the long-style outcome as `negative_for_long_opportunity` and still creates no score/signal/trade.
- Added `get_manipulation_detection_source_backed_shadow_replay_controls_preview` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-shadow-replay-controls-preview`.
- Product result: local negative-control candidates are discovered read-only for future multi-candidate replay; current live DB has `50` local candidates and `11` collectable candidates, but no control outcome datasets are persisted.
- Added `get_manipulation_detection_source_backed_control_outcome_collection_plan` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-collection-plan`.
- Product result: the first `3` collectable controls are selected read-only and `12` future outcome windows are planned; no provider call or control outcome persistence occurs.
- Added `run_manipulation_detection_source_backed_control_outcome_lookup_dry_run` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-lookup-dry-run`.
- Product result: the first `3` controls are assessed locally; `6` control windows are measurable in memory and `6` remain blocked, with no control outcome persistence.
- Added `get_manipulation_detection_source_backed_control_outcome_schema_plan` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-schema-plan`.
- Product result: future table `manipulation_control_outcome_windows` is planned read-only for the `6` measurable control windows; no DDL/write occurs.
- Added `create_manipulation_detection_source_backed_control_outcome_table` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/create`.
- Product result: table `manipulation_control_outcome_windows` now exists after confirmed DDL-only create, has `0` rows, second confirm is idempotent, and no signal/trade/mapping table changed.
- Added `insert_manipulation_detection_source_backed_control_outcome_windows` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/insert`.
- Product result: `6` source-backed control outcome windows are now persisted after dry-run-first confirmed insert; duplicate re-apply blocks and no signal/trade/mapping table changed.
- Added `get_manipulation_detection_source_backed_control_outcome_review_queue` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/review`.
- Product result: persisted control outcome rows review cleanly with `6/6` ready rows, payload/current-plan/dedupe/lookup-digest/local-quality bound, and the lane is ready for multi-candidate replay preview without any write.
- Added `get_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-multi-candidate-shadow-replay-preview`.
- Product result: UFLOKI is compared against the reviewed controls read-only; the current replay verdict is `reject_source_long_signal`, which is useful because the system is learning to reject weak opportunities instead of producing unsafe signals.
- Added `get_manipulation_detection_source_backed_replay_policy_thresholds` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-replay-policy-thresholds`.
- Product result: the policy layer converts replay output into a machine decision. Current live result is `reject_research_signal_candidate` because UFLOKI fails favorable move, net move, and adverse move thresholds. No client signal or trade is enabled.
- Added `get_manipulation_detection_source_backed_case_control_expansion_plan` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-case-control-expansion-plan`.
- Product result: the local data now yields `75` candidate pools, including `11` expansion candidates and `11` route-repair candidates. The best next data task is raw Swap/Sync/Transfer collection planning for the top route-backed pools, still no signal/trade.
- Added `get_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-collection-plan`.
- Product result: the top `3` expansion candidates now have a bounded raw-context collection plan with `6` Swap filters, `18` Sync/Mint/Burn filters, and `24` ERC20 Transfer filters. No provider call, evidence persistence, signal, mapping or trade is performed.
- Added `run_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-lookup-dry-run`.
- Product result: the bounded lookup can execute the planned filters with explicit confirm and parse logs in memory only. Dense SQD ranges are now chunked to `1000` blocks and the shared SQD helper keeps complete JSONL records under a response cap. The lookup now uses balanced candidate/event selection and live bounded smoke recovered `437` logs in memory: `150` Swap, `150` Sync, and `137` ERC20 Transfer across the top `3` pools. No evidence persistence, signal, mapping or trade is performed.
- Added `get_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence-schema-plan`.
- Product result: schema-plan is read-only and reuses existing raw tables (`dex_raw_swap_events`, `dex_raw_sync_events`, `erc20_transfer_events`) instead of creating a new duplicate lane/table. It requires future digest-bound insert and duplicate blocking, with no DDL/write now.
- Added `insert_manipulation_detection_source_backed_top_expansion_raw_context_evidence` in the same module.
- Added route `/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence/insert`.
- Product result: dry-run-first confirmed insert now persists only selected raw context rows for the top `3` expansion candidates. Live confirmed insert wrote `437` rows total: `150` Swap, `150` Sync, and `137` ERC20 Transfer rows. Duplicate re-preview blocks by `event_dedupe_key`. No mapping, signal, label, trade, wallet order or opt-in is created.
- Added `behavioral_evidence_bridge.py`.
- Added route `/api/onchain/rpc/manipulation-detection-behavioral-evidence-bridge`.
- Product result: the bridge is read-only and translates adaptive case-file outputs into `behavioral_cluster_proof` packages. Live smoke returned `3` proofs with max score `44`, so no strong behavioral candidate exists yet. This validates the wiring direction without weakening policy gates or enabling signal/trade.
- Validation passed: `py_compile`, targeted service tests, admin route tests, live service/route smokes, and DB counter checks.

Already completed no-behavior-change extractions:
- Created `backend/services/onchain/raw_swap_evidence.py`.
- Created `backend/services/onchain/__init__.py`.
- Moved the raw Swap evidence insert implementation out of `backend/services/onchain_engine.py`.
- Kept `services.onchain_engine.insert_manipulation_detection_raw_swap_evidence` compatible through re-export.
- Added `.ignore` so future `rg` audits do not count `tmp/`, venvs, node modules or built frontend assets as project Python/source.

Validation:
- `py_compile` passed for `onchain_engine.py`, `raw_swap_evidence.py`, and `routers/onchain.py`.
- Targeted raw Swap insert test passed.
- Service dry-run still returns `8` eligible rows, `would_insert_raw_swap=true`, `writes_performed=0`.
- Route import smoke still exposes `/rpc/manipulation-detection-raw-swap-evidence/insert`.
- `onchain_engine.py` dropped from about 102275 physical lines to about 102027 physical lines.

Safety result:
- No DB write.
- No mapping.
- No router evidence.
- No label.
- No client signal.
- No trade.
- No opt-in.

## Simple Verdict

Yes, it is time to manage `backend/services/onchain_engine.py`.

The project is not blocked by having many Python files. It is blocked by two monoliths:
- `backend/services/onchain_engine.py`: about 102k physical lines, 721 top-level functions, no classes.
- `tests/test_onchain_entity_chain_gaps.py`: about 35k lines.

Plain meaning:
- Core Equity logic is real, but too much product logic lives in one file.
- Continuing to add features directly inside `onchain_engine.py` increases risk.
- The safe move is not to delete code or do a big refactor.
- The safe move is to extract stable lanes one by one behind compatibility wrappers.

## Current Python Shape

Project Python files audited outside temporary/venv archives:
- about 80 project Python files.

Largest project files:
- `backend/services/onchain_engine.py`: about 102k lines.
- `tests/test_onchain_entity_chain_gaps.py`: about 35k lines.
- `backend/routers/onchain.py`: about 11.6k lines.
- `tests/test_onchain_admin_auth.py`: about 6.3k lines.
- `tests/test_cex_market_evidence_review_queue_schema_plan.py`: about 4.4k lines.
- `backend/routers/arkham.py`: about 3.4k lines.
- `backend/services/label_ledger.py`: about 3k lines.

Temporary archive warning:
- `tmp/venv-archive-*` contains huge third-party Python files and should not be counted as project source.
- `.gitignore` already ignores `tmp/`, but audits must explicitly exclude it.

## Onchain Engine Shape

`onchain_engine.py` currently contains these broad regions:
- Lines 1-9999: bootstrap, DB helpers, early scans, CEX deposit/funder scans.
- Lines 10000-19999: manipulation, router source, raw swap/provenance, curated trade lanes.
- Lines 20000-29999: token-market and source repair lanes.
- Lines 30000-39999: label source gaps, wallet/entity graph, local observations.
- Lines 40000-49999: token-market discovery evidence and admin review flow.
- Lines 50000-59999: token-market final handoff flow.
- Lines 60000-69999: CEX market evidence and label candidate/creation flow.
- Lines 70000-79999: Unknown DEX, PairCreated/SQD, mapping review contract.
- Lines 80000-89999: DEX event reader, raw events, family context.
- Lines 90000-99999: Agent OS Lite, proof packages, manipulation casefiles.
- Lines 100000+: readiness, ingestion, auto loops, RPC status, wallet analysis tail.

Largest functions include:
- `get_manipulation_detection_readiness`: about 1500 lines.
- `get_token_transfer_cex_deposit_scan`: about 960 lines.
- `get_unknown_dex_family_context_post_collection_audit`: about 600 lines.
- `get_token_market_local_candidate_source_venue_evidence`: about 550 lines.
- `get_token_manipulation_data_usability_audit`: about 526 lines.
- `get_local_wallet_entity_graph_reconstruction_plan`: about 526 lines.
- `get_manipulation_detection_reliability_engine`: about 467 lines.
- `get_core_equity_agent_control_plane`: about 463 lines.
- `get_onchain_data_readiness`: about 457 lines.

## Immediate Risks

Main risks:
- Too many unrelated product lanes in one file.
- Harder reviews because any small patch lands in a 100k-line file.
- Higher chance of duplicated helper logic.
- Router imports too many service functions directly.
- Tests also became a monolith, so targeted validation is harder to navigate.

Not a current blocker:
- Existing behavior can still work.
- The code is not automatically bad because it is large.
- A big-bang rewrite would be more dangerous than the current monolith.

## Safe Refactor Strategy

Do not start by moving everything.

Use a strangler pattern:
1. Create small domain modules.
2. Move one stable lane at a time.
3. Keep compatibility exports in `onchain_engine.py`.
4. Keep router imports working.
5. Run targeted tests after every extraction.
6. Update RAG after every successful extraction.

Recommended extraction order:
1. Raw event/data lanes:
   - exact Swap SQD lookup
   - raw Swap evidence schema-plan
   - raw Swap evidence insert
   - DEX local event reader raw persistence
2. Manipulation reliability/readiness:
   - manipulation data usability audit
   - reliability engine
   - readiness gate
3. DEX proof/mapping preparation:
   - PairCreated evidence lanes
   - DEX mapping review contract/schema/insert
4. Token-market admin review legacy lanes:
   - only after data lanes stabilize
5. Agent OS Lite:
   - separate after core data modules are stable

## Proposed Target Layout

Future service layout:

```text
backend/services/onchain_engine.py
  compatibility facade only

backend/services/onchain/
  __init__.py
  db.py
  constants.py
  guards.py
  sqd.py
  raw_events.py
  manipulation.py
  dex_paircreated.py
  dex_mapping.py
  event_reader.py
  token_market.py
  agent_os.py
```

Rules:
- `onchain_engine.py` should re-export moved functions during transition.
- Routers should not be changed first unless necessary.
- No runtime behavior change during extraction.
- No DB schema change during extraction.
- No label, mapping, signal, trade or opt-in change.

## First Productive Refactor Mission

Best first extraction:
- Move the new manipulation raw Swap evidence insert lane into a new module.

Why:
- It is fresh, small, tested, and data-only.
- It has clear boundaries:
  - SQD preview input
  - `dex_raw_swap_events` output
  - digest/duplicate guards
  - no mapping/signal/trade
- It reduces future growth inside `onchain_engine.py`.

Do not move the whole manipulation engine yet.

## Validation Required

For every extraction:
- `py_compile` target modules and router.
- Run the targeted unit test.
- Run one service smoke if the function is pure service-level.
- Verify no DB write unless the mission explicitly allows data-only write.
- Verify `would_create_mapping=false`.
- Verify `would_create_client_signal=false`.
- Verify `would_execute_trade=false`.
- Verify RAG state is updated only after a successful extraction.

Status:
- Completed.

## 2026-05-22 - Manipulation Reliability Extraction Completed

What changed:
- Extracted the manipulation reliability engine into `backend/services/onchain/manipulation_reliability.py`.
- `backend/services/onchain_engine.py` now re-exports `get_manipulation_detection_reliability_engine` for route compatibility.
- No route behavior changed.
- No DB write was performed.
- No label, mapping, client signal, trade, wallet order, or opt-in was created.

Simple product meaning:
- The codebase is becoming easier to control without changing the product logic.
- The reliability check still says Core Equity cannot detect manipulation with enough confidence yet.
- Main blockers remain data quality: no raw swap events, too little curated DEX history, and no candidate passing reliability gates.

Validation:
- `py_compile` passed for `onchain_engine.py`, `manipulation_reliability.py`, and `routers/onchain.py`.
- Service smoke passed for `get_manipulation_detection_reliability_engine(chain="bsc", dry_run=True)`.
- Targeted unittest passed: `test_token_manipulation_data_usability_audit_blocks_thin_data`.
- Route import smoke passed for manipulation reliability and raw swap evidence insert routes.

## 2026-05-22 - Manipulation Data Usability Extraction Completed

What changed:
- Extracted the token manipulation data usability audit into `backend/services/onchain/manipulation_data_usability.py`.
- `backend/services/onchain_engine.py` now re-exports `get_token_manipulation_data_usability_audit` for route compatibility.
- Existing tests that patch `services.onchain_engine` still work because the extracted module calls back through controlled engine proxies.
- No route behavior changed.
- No DB write was performed.
- No label, mapping, client signal, trade, wallet order, or opt-in was created.

Simple product meaning:
- Core Equity now has a cleaner separation between data-usability diagnosis and the main on-chain engine.
- The product answer remains conservative: current data is useful for research, not reliable manipulation detection.
- Current live blockers include low swap count, short swap history, zero source-backed candidates, Unknown DEX/router attribution, token identity gaps, amount USD normalization risk, and weak label-source coverage.

Validation:
- `py_compile` passed for `onchain_engine.py`, `manipulation_data_usability.py`, `manipulation_reliability.py`, and `routers/onchain.py`.
- Targeted unittest passed: `test_token_manipulation_data_usability_audit_blocks_thin_data`.
- Service smoke passed for `get_token_manipulation_data_usability_audit(limit=5, dry_run=True)`.
- Route import smoke passed for token manipulation data usability and manipulation reliability routes.

## Current Recommendation

Next mission should be one of these, depending on priority:

```text
OPTION A - produit/data:
MISSION DIRECTE: Continue Core Equity en mode economique, priorite UFLOKI source-backed shadow/backtest plan read-only.

OPTION B - cleanup:
MISSION DIRECTE: Continue Core Equity en mode economique, priorite onchain_engine readiness gap auto-fill extraction no-behavior-change.
```

## 2026-05-22 - Pure Manipulation Verdict Helpers Extraction Completed

What changed:
- Added `backend/services/onchain/manipulation_verdicts.py`.
- Moved pure helpers:
  - `_build_manipulation_research_verdict`
  - `_build_holder_flow_evidence_verdict`
- `backend/services/onchain_engine.py` now imports these helpers, preserving the existing public names used by tests and callers.

Validation:
- `py_compile` passed for `onchain_engine.py`, `manipulation_verdicts.py`, and `routers/onchain.py`.
- Targeted tests passed:
  - `test_manipulation_research_verdict_scores_cex_holder_supply_case`
  - `test_holder_flow_evidence_verdict_blocks_missing_snapshot_and_reviews_concentration`
- Route smoke for source-backed scoring design still returns `ready_but_disabled`, `would_write=false`, `writes_performed=0`.
- DB counters stayed unchanged.

Safety result:
- No DB write.
- No endpoint behavior change.
- No mapping.
- No label.
- No client signal.
- No trade.
- No opt-in.

Product meaning:
- This does not make Core Equity detect manipulation yet.
- It makes the codebase safer by removing a tested pure piece from the monolith and giving future manipulation-readiness work a cleaner module boundary.

## 2026-05-22 - Manipulation Readiness Builder Helpers Extraction Completed

What changed:
- Extended `backend/services/onchain/manipulation_verdicts.py` with pure readiness helpers:
  - `_readiness_gate`
  - `_minimum_readiness_requirement`
  - `_maximum_readiness_requirement`
- Replaced the nested helper definitions inside `get_manipulation_detection_readiness`.
- `backend/services/onchain_engine.py` remains the public compatibility facade.

Validation:
- `py_compile` passed for `onchain_engine.py`, `manipulation_verdicts.py`, and `routers/onchain.py`.
- Targeted tests passed:
  - `test_manipulation_detection_readiness_blocks_shallow_history_read_only`
  - `test_manipulation_research_verdict_scores_cex_holder_supply_case`
  - `test_holder_flow_evidence_verdict_blocks_missing_snapshot_and_reviews_concentration`
- Service smoke passed for `get_manipulation_detection_readiness(entity="Binance", limit=5)`.
- Route smoke passed for `/rpc/manipulation-readiness`.
- DB counters stayed unchanged.

Safety result:
- No DB write.
- No endpoint behavior change.
- No mapping.
- No label.
- No client signal.
- No trade.
- No opt-in.

Product meaning:
- This is code-quality progress, not manipulation verdict progress.
- The readiness gate still says `not_ready_for_manipulation_detection`, which is correct.
- The next engineering step is to validate the full readiness extraction and then decide whether to move `run_readiness_gap_auto_fill` or return to product/data work.

## 2026-05-22 - Full Manipulation Readiness Extraction Completed

What changed:
- Added `backend/services/onchain/manipulation_readiness.py`.
- Moved the full read-only `get_manipulation_detection_readiness` gate out of `backend/services/onchain_engine.py`.
- Kept `backend/services/onchain_engine.py` as the compatibility facade by importing and re-exporting the same public function name.
- Kept route behavior unchanged for `/api/onchain/rpc/manipulation-readiness`.
- Added controlled local proxies inside the new module for legacy engine helpers used by the readiness gate.

Validation:
- `py_compile` passed for `onchain_engine.py`, `manipulation_readiness.py`, `manipulation_verdicts.py`, and `routers/onchain.py`.
- Targeted tests passed:
  - `test_manipulation_detection_readiness_blocks_shallow_history_read_only`
  - `test_manipulation_research_verdict_scores_cex_holder_supply_case`
  - `test_holder_flow_evidence_verdict_blocks_missing_snapshot_and_reviews_concentration`
  - `test_readiness_gap_auto_fill_is_dry_run_and_traceable_by_default`
  - `test_readiness_gap_auto_fill_real_mode_requires_confirm`
  - `test_readiness_gap_auto_fill_passes_bounded_dry_run_to_service`
  - `test_readiness_gap_auto_fill_rejects_unbounded_runs`
- Route smoke passed for manipulation readiness and bounded auto-fill dry-run.
- DB counters stayed unchanged.

Safety result:
- No DB write.
- No endpoint behavior change intended.
- No mapping.
- No label.
- No client signal.
- No trade.
- No opt-in.

Codebase impact:
- `backend/services/onchain_engine.py` is now about `99285` lines.
- `backend/services/onchain/manipulation_readiness.py` is about `1465` lines.
- `backend/services/onchain/manipulation_verdicts.py` is about `391` lines.

Product meaning:
- This is structural cleanup, not a new manipulation verdict.
- The readiness route still correctly returns `not_ready_for_manipulation_detection` with execution disabled.
- The codebase is safer to extend because the manipulation readiness logic now has a dedicated module boundary.

Current recommendation:
- If engineering cleanup remains priority, move `run_readiness_gap_auto_fill` into a small orchestration module next.
- If product progress is priority, switch to UFLOKI source-backed shadow/backtest read-only instead of continuing extraction.

## 2026-05-22 - Source-Backed Shadow/Backtest Plan Endpoint Added

What changed:
- Extended `backend/services/onchain/manipulation_reliability.py` with `get_manipulation_detection_source_backed_shadow_backtest_plan`.
- Added router endpoint `/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-plan`.
- Re-exported the function through `backend/services/onchain_engine.py` for compatibility.

Validation:
- `py_compile` passed for the service, facade, router and targeted tests.
- Targeted tests passed:
  - `test_source_backed_shadow_backtest_plan_is_read_only_and_disabled`
  - `test_source_backed_shadow_backtest_plan_requires_admin_token`
  - `test_source_backed_shadow_backtest_plan_passes_to_service`
- Service and route smokes returned `plan_status=ready_but_disabled`, `shadow_backtest_plan_ready=true`, `shadow_backtest_executable_now=false`, `would_run_backtest=false`, `would_write=false`, and `writes_performed=0`.
- DB counters stayed unchanged.

Product meaning:
- This is product-validation progress, not trading progress.
- Core Equity can now explain how UFLOKI should be tested in shadow mode before any client signal.
- The next product step is an outcome dataset schema-plan, not a trade.

## 2026-05-22 - Shadow/Backtest Outcome Dataset Schema-Plan Added

What changed:
- Extended `backend/services/onchain/manipulation_reliability.py` with `get_manipulation_detection_source_backed_shadow_backtest_outcome_dataset_schema_plan`.
- Added router endpoint `/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-outcome-dataset-schema-plan`.
- Re-exported the function through `backend/services/onchain_engine.py` for compatibility.
- Checked existing code first: the legacy curated DEX backtest preview remains separate and was not duplicated or modified.

Validation:
- `py_compile` passed for the service, facade, router and targeted tests.
- Targeted tests passed:
  - `test_source_backed_shadow_backtest_outcome_schema_plan_creates_no_table`
  - `test_source_backed_shadow_backtest_plan_is_read_only_and_disabled`
  - `test_source_backed_shadow_backtest_outcome_schema_plan_requires_admin_token`
  - `test_source_backed_shadow_backtest_outcome_schema_plan_passes_to_service`
- Service and route smokes returned `plan_status=ready`, `migration_required=true`, `would_create_table=false`, `would_write=false`, and `writes_performed=0`.
- DB counters stayed unchanged and `manipulation_shadow_backtest_outcome_windows` was not created.

Product meaning:
- The next product data box is defined, but not created.
- It will later hold outcome windows needed to test whether source-backed manipulation evidence would have been useful.

## 2026-05-22 - UFLOKI Sync/Liquidity Lookup Dry-Run Added

What changed:
- Extended `backend/services/onchain/manipulation_reliability.py` with `run_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run`.
- Added router endpoint `/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-lookup-dry-run`.
- Re-exported the function through `backend/services/onchain_engine.py` for compatibility.
- The function reuses the existing Sync/Mint/Burn collection plan and SQD event-log helper; it does not create a separate discovery lane.

Validation:
- `py_compile` passed for the service module, facade, router, and targeted tests.
- Targeted tests passed:
  - `test_outcome_sync_liquidity_lookup_parses_logs_without_persistence`
  - `test_outcome_sync_liquidity_lookup_requires_admin_token`
  - `test_outcome_sync_liquidity_lookup_passes_to_service`
- Live confirmed dry-run parsed `315` SQD logs in memory only: `255` Sync and `60` Mint.
- No DB row was written and no mapping/signal/trade/opt-in was created.

Product meaning:
- This is data progress: UFLOKI missing outcome-quality context is recoverable from SQD.
- It is still not a manipulation verdict, not a client signal, and not a trade.
- Next safe task is an evidence-only schema-plan for storing this context later.

## 2026-05-22 - UFLOKI Sync/Liquidity Evidence Schema-Plan Added

What changed:
- Extended `backend/services/onchain/manipulation_reliability.py` with `get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan`.
- Added router endpoint `/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence-schema-plan`.
- Re-exported the function through `backend/services/onchain_engine.py` for compatibility.
- The function composes the existing local event-reader raw schema plan and selects only `dex_raw_sync_events` and `dex_raw_liquidity_events`.

Validation:
- `py_compile` passed for the service module, facade, router, and targeted tests.
- Targeted tests passed:
  - `test_outcome_sync_liquidity_evidence_schema_plan_reuses_raw_event_tables_read_only`
  - `test_outcome_sync_liquidity_lookup_parses_logs_without_persistence`
  - `test_outcome_sync_liquidity_evidence_schema_plan_requires_admin_token`
  - `test_outcome_sync_liquidity_evidence_schema_plan_passes_to_service`
- Service and route smokes returned `plan_status=ready_but_disabled`, `migration_required=false`, `would_create_table=false`, `would_write=false`, and `writes_performed=0`.
- DB counters stayed unchanged.

Product meaning:
- No new table is needed; the raw evidence boxes already exist and are empty.
- The next product/data task can be an insert dry-run-first for the recovered Sync/Mint context.

## 2026-05-22 - UFLOKI Sync/Liquidity Evidence Insert Dry-Run-First Added

What changed:
- Extended `backend/services/onchain/manipulation_reliability.py` with `insert_manipulation_detection_source_backed_outcome_sync_liquidity_evidence`.
- Added router endpoint `/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/insert`.
- Re-exported the function through `backend/services/onchain_engine.py` for compatibility.
- Added shared helpers for canonical raw payload JSON, payload digest and event row shaping for Sync/Mint/Burn evidence rows.

Validation:
- `py_compile` passed for the service module, facade, router, and targeted tests.
- Targeted tests passed:
  - `test_outcome_sync_liquidity_evidence_insert_dry_run_prepares_rows_without_writing`
  - `test_outcome_sync_liquidity_evidence_insert_requires_admin_token`
  - `test_outcome_sync_liquidity_evidence_insert_passes_to_service`
- Live dry-run performed a bounded SQD lookup and returned `insert_status=ready_for_insert`.
- Prepared `194` eligible rows: `159` Sync and `35` liquidity rows.
- DB counters stayed unchanged: no Sync or liquidity row was inserted.

Product meaning:
- This is the last dry-run before persisting UFLOKI Sync/Mint evidence-only rows.
- It still creates no mapping, no signal, no trade, no wallet order and no opt-in.

## 2026-05-22 - UFLOKI Sync/Liquidity Confirmed Insert Validated

What changed:
- Added duplicate blocker `duplicate_sync_liquidity_evidence_exists` to the insert lane so repeated real applies fail explicitly.
- Added a targeted confirmed-insert unit test that verifies only raw Sync/liquidity tables are written and duplicate re-apply is blocked.

Validation:
- `py_compile` passed for the service module, facade, router, and targeted tests.
- Targeted tests passed:
  - `test_outcome_sync_liquidity_evidence_confirmed_insert_writes_only_raw_tables_once`
  - `test_outcome_sync_liquidity_evidence_insert_dry_run_prepares_rows_without_writing`
  - `test_outcome_sync_liquidity_evidence_insert_passes_to_service`
- Live confirmed insert wrote `159` Sync rows and `35` liquidity rows.
- Duplicate second live apply returned blocker `duplicate_sync_liquidity_evidence_exists` and wrote `0` rows.
- Outcome repair checkpoint now returns `repair_context_ready_read_only`.

Safety result:
- No mapping was created.
- No client signal was emitted.
- No trade or wallet order was executed.
- No client opt-in was created.
