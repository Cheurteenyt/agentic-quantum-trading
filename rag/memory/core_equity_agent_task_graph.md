# Core Equity Agent Task Graph

Last updated: 2026-05-22.

Purpose:
- Define the read-only task graph and task contract registry for Agent OS Lite v2.
- Give future agents a concrete work queue model without allowing autonomous writes.
- Keep Core Equity focused on data quality, evidence quality, shadow evaluation and policy gates before any client/trade action.

This is RAG/design only. It creates no runtime endpoint, DB table, migration, label, mapping, signal, trade, wallet order or opt-in.

## Task Graph Model

Task states:
- `queued`: task is known but not selected.
- `selected`: one task chosen for the current cycle.
- `running`: task is being executed by Codex or a future runner.
- `blocked`: task cannot proceed; must include actionable blocker.
- `review`: task produced an output that needs validation.
- `done`: task met validation and safety criteria.
- `superseded`: task is no longer current because project state moved on.

State transition rules:
- `queued -> selected`: only if task is allowlisted and not blocked.
- `selected -> running`: only after runtime preflight passes or task is RAG-only.
- `running -> review`: task output exists and schema is present.
- `review -> done`: safety flags pass and validation criteria are met.
- `review -> blocked`: output schema invalid, forbidden flag true, missing source/digest/dedupe, or runtime/data blocker appears.
- `blocked -> queued`: only after repair task is defined.
- `done -> queued`: only for a new downstream task, never the same duplicate run.

One-cycle rule:
- One Agent OS Lite cycle may select and run at most one task.
- A cycle must stop after producing a result, blocker, or audit receipt.
- A cycle must not chain into mapping/signal/trade/client action.

## Current Task Graph

```yaml
graph_version: "agent-task-graph-v1-read-only"
current_focus: "UFLOKI manipulation data quality"
nodes:
  - id: "T0_refresh_rag_control_state"
    state: "done"
    contract: "rag_control_state_refresh"
    output: "core_equity_agent_control_plane.md"

  - id: "T1_transfer_context_evidence_schema_plan"
    state: "done"
    contract: "schema_plan_read_only"
    output:
      target_table: "dex_transfer_context_evidence"
      eligible_unique_transfer_events: 169
      migration_required: false
      writes_performed: 0

  - id: "T2_transfer_context_evidence_empty_ddl"
    state: "done"
    contract: "confirmed_empty_ddl_migration"
    priority: 1
    depends_on: ["T1_transfer_context_evidence_schema_plan"]
    output:
      target_table: "dex_transfer_context_evidence"
      table_exists: true
      row_count: 0
      rows_inserted: 0
      writes_performed: 7
    next: ["T3_transfer_context_evidence_insert_dry_run"]

  - id: "T3_transfer_context_evidence_insert_dry_run"
    state: "done"
    contract: "evidence_insert_dry_run"
    priority: 2
    depends_on: ["T2_transfer_context_evidence_empty_ddl"]
    output:
      insert_status: "inserted"
      eligible_transfer_context_rows: 169
      transfer_context_insert_digest: "5d9974a07f4d95bc10136666ed8e0531f0481125b97228c740190ed681f9e382"
      external_calls_performed: 6
      rows_inserted: 169
      row_count_after: 169
      duplicate_reapply_blocked: true
      writes_performed: 169
    next: ["T4_transfer_context_evidence_review_read_only"]

  - id: "T4_transfer_context_evidence_review_read_only"
    state: "done"
    contract: "evidence_review_read_only"
    priority: 3
    depends_on: ["T3_transfer_context_evidence_insert_dry_run"]
    output:
      queue_status: "ready_but_disabled"
      total_transfer_context_evidence: 169
      ready_for_reliability_bridge_preview: 169
      duplicate_event_dedupe_keys: 0
      payload_digest_bound: 169
      dedupe_bound: 169
      source_bound: 169
      transfer_topic_bound: 169
      projected_best_transfer_rows_if_bridged: 176
      writes_performed: 0
    next: ["T5_transfer_context_evidence_reliability_bridge_preview"]

  - id: "T5_transfer_context_evidence_reliability_bridge_preview"
    state: "done"
    contract: "reliability_review_read_only"
    priority: 4
    depends_on: ["T4_transfer_context_evidence_review_read_only"]
    output:
      bridge_status: "ready_but_disabled"
      reviewed_evidence_rows: 169
      current_best_transfer_rows: 7
      projected_best_transfer_rows: 176
      would_clear_too_few_transfer_rows_min_10: true
      can_detect_reliable_manipulation_now: false
      writes_performed: 0
    next: ["T6_transfer_context_reliability_bridge_apply_contract_schema_read_only"]

  - id: "T6_transfer_context_reliability_bridge_apply_contract_schema_read_only"
    state: "done"
    contract: "schema_plan_read_only"
    priority: 5
    depends_on: ["T5_transfer_context_evidence_reliability_bridge_preview"]
    output:
      contract_status: "ready_but_disabled"
      required_future_confirm: "APPLY_UFLOKI_TRANSFER_CONTEXT_RELIABILITY_BRIDGE"
      reviewed_evidence_rows: 169
      current_best_transfer_rows: 7
      projected_best_transfer_rows: 176
      would_apply_reliability_bridge: false
      writes_performed: 0
    next: ["T7_transfer_context_reliability_bridge_integration_read_only"]

  - id: "T7_transfer_context_reliability_bridge_integration_read_only"
    state: "done"
    contract: "reliability_review_read_only"
    priority: 6
    depends_on: ["T6_transfer_context_reliability_bridge_apply_contract_schema_read_only"]
    output:
      bridge_status: "ready_read_only"
      current_best_transfer_rows_before_bridge: 7
      evidence_rows_consumed_read_only: 169
      best_transfer_rows_after_bridge: 176
      too_few_transfer_rows_min_10_present: false
      can_detect_reliable_manipulation_now: false
      writes_performed: 0
    next: ["T8_source_backed_scoring_design_read_only"]

  - id: "T8_source_backed_scoring_design_read_only"
    state: "queued"
    contract: "shadow_backtest_design_read_only"
    priority: 7
    depends_on: ["T7_transfer_context_reliability_bridge_integration_read_only"]
    next: ["T9_shadow_backtest_plan_read_only"]

  - id: "T9_shadow_backtest_plan_read_only"
    state: "queued"
    contract: "shadow_backtest_design_read_only"
    priority: 8
    depends_on: ["T8_source_backed_scoring_design_read_only"]
    next: []
```

Current selected next task:
- `T8_source_backed_scoring_design_read_only`

Plain meaning:
- The next useful thing is not another vague prompt.
- The empty evidence box now exists.
- The 169 Transfer evidence rows are now persisted as evidence-only rows.
- The review says all 169 rows are bound and ready for a future reliability bridge.
- The bridge preview says the transfer-count blocker can be cleared later.
- The bridge apply contract is ready.
- The reliability engine now consumes reviewed Transfer evidence read-only.
- The next useful thing is source-backed scoring design, not a signal or trade.

## Task Contract Template

Every task must conform to this shape:

```yaml
task_contract:
  task_id: "<stable id>"
  agent_role: "Data Agent | Evidence Agent | Policy Agent | Backtest Agent | RAG Agent | Codex Operator"
  mode: "rag_only | read_only | dry_run_first | confirmed_data_infra_only | confirmed_data_only"
  state: "queued | selected | running | blocked | review | done | superseded"
  purpose: "<one sentence>"
  input_sources:
    rag_files: []
    code_files: []
    local_tables: []
    endpoints: []
    external_sources: []
  allowed_reads: []
  allowed_writes: []
  forbidden_actions: []
  budgets:
    max_runtime_seconds: 0
    max_external_calls: 0
    max_rows_written: 0
    max_files_changed: 0
  gates:
    dry_run_required: true
    confirm_required: false
    expected_digest_required: false
    duplicate_check_required: true
    admin_token_required: false
  expected_outputs: []
  validation: []
  stop_conditions: []
  audit_receipt_required: "never_for_noop | preview_only | after_confirmed_useful_cycle"
```

## Allowed Task Contracts

### 1. `rag_control_state_refresh`

```yaml
task_id: "rag_control_state_refresh"
agent_role: "RAG Agent"
mode: "rag_only"
purpose: "Keep the control plane and prompt manager current."
allowed_reads:
  - "rag/memory/*.md"
allowed_writes:
  - "rag/memory/*.md only under user-directed RAG/design tasks"
forbidden_actions:
  - "runtime_endpoint"
  - "db_write"
  - "migration"
  - "label"
  - "mapping"
  - "signal"
  - "trade"
  - "opt_in"
budgets:
  max_files_changed: 8
gates:
  dry_run_required: false
  confirm_required: false
validation:
  - "read order updated"
  - "next task not stale"
  - "disabled surfaces preserved"
audit_receipt_required: "preview_only"
```

### 2. `x_research_intake_read_only`

```yaml
task_id: "x_research_intake_read_only"
agent_role: "Research Agent"
mode: "read_only"
purpose: "Use X/Twitter as a lead radar, not as proof."
allowed_reads:
  - "dedicated Brave Core Equity research profile"
  - "public/logged-in X pages"
allowed_writes:
  - "rag/memory/x_research_watchlist.md only if summarizing durable research patterns"
forbidden_actions:
  - "post"
  - "like"
  - "follow"
  - "dm"
  - "scrape_loop"
  - "db_write"
  - "evidence_persistence"
  - "mapping"
  - "signal"
  - "trade"
  - "opt_in"
budgets:
  max_external_calls: 20
  max_runtime_seconds: 300
validation:
  - "leads classified as research-only"
  - "no X post treated as evidence"
  - "next on-chain verification step proposed"
audit_receipt_required: "preview_only"
```

### 3. `schema_plan_read_only`

```yaml
task_id: "schema_plan_read_only"
agent_role: "Data Agent"
mode: "read_only"
purpose: "Describe future storage before any DDL or insert."
allowed_reads:
  - "local service state"
  - "RAG current state"
allowed_writes: []
forbidden_actions:
  - "DDL"
  - "row_insert"
  - "db_write"
  - "mapping"
  - "signal"
  - "trade"
  - "opt_in"
gates:
  dry_run_required: true
validation:
  - "schema_preview visible"
  - "indexes_preview visible"
  - "dedupe policy visible"
  - "would_create_table=false"
  - "would_write=false"
  - "writes_performed=0"
audit_receipt_required: "preview_only"
```

### 4. `confirmed_empty_ddl_migration`

```yaml
task_id: "confirmed_empty_ddl_migration"
agent_role: "Codex Operator"
mode: "confirmed_data_infra_only"
purpose: "Create an empty table and indexes after a schema-plan."
allowed_reads:
  - "schema-plan output"
  - "target table existence"
allowed_writes:
  - "DDL for exactly one target table"
  - "indexes for exactly one target table"
forbidden_actions:
  - "row_insert"
  - "business_table_mutation"
  - "label"
  - "mapping"
  - "signal"
  - "trade"
  - "opt_in"
gates:
  dry_run_required: "default"
  confirm_required: true
  duplicate_check_required: true
budgets:
  max_rows_written: 0
validation:
  - "dry-run creates nothing"
  - "confirm creates table + indexes only"
  - "second confirm idempotent"
  - "row count = 0"
  - "business DB unchanged"
audit_receipt_required: "after_confirmed_useful_cycle"
```

### 5. `bounded_external_lookup_dry_run`

```yaml
task_id: "bounded_external_lookup_dry_run"
agent_role: "Data Agent"
mode: "dry_run_first"
purpose: "Test whether missing raw data is recoverable."
allowed_reads:
  - "local plan"
  - "bounded external/indexer source when confirmed"
allowed_writes: []
forbidden_actions:
  - "persistence"
  - "unbounded_scraping"
  - "mapping"
  - "signal"
  - "trade"
  - "opt_in"
gates:
  dry_run_required: true
  confirm_required: true
budgets:
  max_external_calls: "must be explicit"
  max_runtime_seconds: "must be explicit"
  max_rows_written: 0
validation:
  - "calls performed <= budget"
  - "parsed in memory only"
  - "would_write=false"
  - "writes_performed=0"
audit_receipt_required: "preview_only"
```

### 6. `evidence_insert_dry_run`

```yaml
task_id: "evidence_insert_dry_run"
agent_role: "Evidence Agent"
mode: "dry_run_first"
purpose: "Preview future evidence-only persistence."
allowed_reads:
  - "schema-plan"
  - "lookup result or replay result"
  - "target table duplicate state"
allowed_writes: []
forbidden_actions:
  - "business_table_mutation"
  - "mapping"
  - "signal"
  - "trade"
  - "opt_in"
gates:
  dry_run_required: true
  expected_digest_required: true
  duplicate_check_required: true
validation:
  - "eligible rows visible"
  - "blocked rows visible"
  - "expected digest/dedupe visible"
  - "would_write=false in dry-run"
  - "writes_performed=0 in dry-run"
audit_receipt_required: "preview_only"
```

### 7. `reliability_review_read_only`

```yaml
task_id: "reliability_review_read_only"
agent_role: "Policy Agent"
mode: "read_only"
purpose: "Recompute manipulation readiness from local evidence."
allowed_reads:
  - "local DB"
  - "RAG current state"
allowed_writes: []
forbidden_actions:
  - "status_update"
  - "mapping"
  - "signal"
  - "trade"
  - "opt_in"
gates:
  dry_run_required: true
validation:
  - "can_detect_reliable_manipulation_now shown"
  - "blockers shown"
  - "research-only vs usable clearly separated"
  - "no client/trade action enabled"
audit_receipt_required: "preview_only"
```

### 8. `shadow_backtest_design_read_only`

```yaml
task_id: "shadow_backtest_design_read_only"
agent_role: "Backtest Agent"
mode: "read_only"
purpose: "Define how Core Equity will measure detection quality before client use."
allowed_reads:
  - "local evidence summaries"
  - "RAG strategy docs"
allowed_writes:
  - "RAG/design files only when user-directed"
forbidden_actions:
  - "client_signal"
  - "trade"
  - "wallet_order"
  - "opt_in"
validation:
  - "metrics defined"
  - "false positive/false negative handling defined"
  - "no ROI promise"
  - "no real trade path"
audit_receipt_required: "preview_only"
```

## Blocked Contracts

Blocked until separate explicit policy:
- `cex_label_write`
- `dex_mapping_write`
- `dex_router_evidence_write`
- `client_signal_emit`
- `trade_execution`
- `wallet_order_execution`
- `client_opt_in_creation`
- `unrestricted_x_scraping`
- `Hermes_or_CrewAI_core_operator`
- `no_op_environment_audit`

## Current Next Data Task

```yaml
selected_next_task:
  graph_node: "T8_source_backed_scoring_design_read_only"
  contract: "shadow_backtest_design_read_only"
  target_table: "dex_transfer_context_evidence"
  current_table_state: "exists_with_reviewed_bridge_ready_rows"
  current_row_count: 169
  expected_transfer_context_insert_digest: "5d9974a07f4d95bc10136666ed8e0531f0481125b97228c740190ed681f9e382"
  bridge_preview:
    bridge_status: "ready_but_disabled"
    current_best_transfer_rows: 7
    projected_best_transfer_rows: 176
    would_clear_too_few_transfer_rows_min_10: true
  bridge_apply_contract:
    contract_status: "ready_but_disabled"
    required_future_confirm: "APPLY_UFLOKI_TRANSFER_CONTEXT_RELIABILITY_BRIDGE"
  reliability_bridge_integration:
    bridge_status: "ready_read_only"
    best_transfer_rows_after_bridge: 176
    too_few_transfer_rows_min_10_present: false
  why: "The reliability bridge is integrated read-only; now define source-backed scoring while keeping client signals and trades blocked."
  must_not_do:
    - "promote evidence into token_transfers"
    - "mutate token_transfers"
    - "mutate erc20_transfer_events"
    - "create mapping"
    - "create signal"
    - "trade"
    - "opt-in"
```

## Audit Receipt Requirements

Every meaningful Agent OS Lite cycle must report:
- task id
- contract id
- selected runtime or no-runtime-needed
- input files/endpoints/sources
- output status
- data gained
- blockers
- safety flags
- next safe task
- whether audit write is allowed

No-op rule:
- A blocked cycle with no useful output must not write an audit receipt.
- It must return a repair instruction instead.

## Product Meaning

This task graph is the bridge between:
- today's interactive Codex workflow
- tomorrow's 24/7 autonomous data-improvement loop

It deliberately avoids:
- agent chaos
- social-media scraping as truth
- automatic client signals
- automatic trading
- Hermes/CrewAI takeover

The first autonomous value should be boring and powerful:
- better data
- better evidence
- better repeatability
- better backtests
- better policies
