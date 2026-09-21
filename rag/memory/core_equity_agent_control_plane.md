# Core Equity Agent Control Plane

Last updated: 2026-05-22.

Purpose:
- Provide a machine-readable operating map for Agent OS Lite.
- Replace vague prompts and useless blocked cycles with a clear state, task registry, safety gates and audit receipt format.
- Keep Core Equity autonomous progress focused on data quality, not labels, mappings, signals or trades.

This file is read-only policy/design. It does not authorize DB writes by itself.

Task graph:
- Use `rag/memory/core_equity_agent_task_graph.md` for the expanded task graph, task states, task contracts, budgets, stop conditions and audit requirements.

## Control Plane Snapshot

```yaml
control_plane_version: "lite-v1-read-only"
mode: "economic_safe"
operator: "Codex"
sidecars:
  allowed_review_only:
    - Qwen
    - Helmholtz
    - Spark/Rawls
    - Bacon
  lab_or_report_only:
    - Hermes
    - CrewAI
current_state:
  product_ready_for_reliable_manipulation_detection: false
  best_research_lead:
    chain: "bsc"
    token_lane: "UFLOKI"
    pool: "0xc722000a77d0ba1b464f38ef5aa3be638f97db61"
    factory: "0xca143ce32fe78f1f7019d7d551a6402fc5350c73"
  strong_data:
    paircreated_evidence_rows: 1
    dex_mapping_review_rows: 1
    raw_swap_events: 216
    raw_swap_repeatability_windows: 2
    transfer_lookup_unique_events_in_memory: 169
  latest_completed_lane:
    id: "transfer_context_reliability_bridge_integration"
    status: "ready_read_only"
    target_table: "dex_transfer_context_evidence"
    table_exists: true
    row_count: 169
    ready_for_reliability_bridge_preview: 169
    duplicate_event_dedupe_keys: 0
    payload_digest_bound: 169
    dedupe_bound: 169
    source_bound: 169
    transfer_topic_bound: 169
    projected_best_transfer_rows_if_bridged: 176
    best_transfer_rows_after_bridge: 176
    too_few_transfer_rows_min_10_present: false
    transfer_context_insert_digest: "5d9974a07f4d95bc10136666ed8e0531f0481125b97228c740190ed681f9e382"
    writes_performed: 0
  remaining_blockers:
    - "source-backed scoring not implemented"
    - "shadow/backtest not implemented"
    - "Policy/Risk Engine not authorizing client outputs"
    - "client opt-in absent"
always_disabled:
  - "cex_label_write"
  - "final_label_table_mutation"
  - "dex_router_evidence_write"
  - "dex_mapping_write"
  - "client_signal"
  - "wallet_order"
  - "trade_or_swap_or_perp"
  - "client_opt_in_or_consent_change"
  - "unrestricted_provider_or_scraping"
  - "Hermes_or_CrewAI_operator_mode"
```

## Runtime Preflight

Agent OS Lite must not be WSL-only.

Runtime discovery order:
1. Windows workspace:
   - project path: `D:\trading-agent`
   - preferred Python: `D:\trading-agent\.venv-win\Scripts\python.exe`
2. WSL workspace:
   - project path: `/mnt/d/trading-agent`
   - only if a WSL distro is installed and path exists
3. Docker/Qdrant:
   - optional
   - required only for tasks that explicitly need vector/RAG services

Hard preflight rule:
- If Windows workspace is available, WSL absence is degraded mode, not failure.
- If selected task is RAG/documentation-only, Python runtime absence is degraded mode, not failure.
- If selected task requires service calls and no Python runtime works, return `blocked_actionable`.
- Never use legacy `memory.md` as the source of truth.

## Allowed Task Registry

Agent OS Lite may select exactly one task per cycle.

```yaml
allowed_tasks:
  - id: "rag_summary_or_update"
    mode: "rag_only"
    writes_allowed: "rag_files_only_when_user_directed"
    purpose: "Keep operating state compact and current"
    forbidden: ["db_write", "runtime_endpoint", "label", "mapping", "signal", "trade", "opt_in"]

  - id: "code_audit_read_only"
    mode: "read_only"
    writes_allowed: false
    purpose: "Inspect code coherence and risks"
    forbidden: ["file_patch_without_user_task", "db_write", "runtime_endpoint", "label", "mapping", "signal", "trade", "opt_in"]

  - id: "x_research_intake_read_only"
    mode: "read_only"
    writes_allowed: false
    purpose: "Use X as lead discovery only"
    forbidden: ["post", "like", "follow", "dm", "scrape_loop", "db_write", "evidence_persistence", "signal", "trade"]

  - id: "schema_plan_read_only"
    mode: "read_only"
    writes_allowed: false
    purpose: "Define future storage/constraints without creating tables"
    required_flags: ["would_create_table=false", "would_write=false", "writes_performed=0"]

  - id: "confirmed_empty_ddl_migration"
    mode: "confirmed_data_infra_only"
    writes_allowed: "ddl_only_after_explicit_confirm"
    purpose: "Create an empty table/index set after schema-plan"
    required_confirm: true
    row_writes_allowed: false
    forbidden: ["row_insert", "label", "mapping", "signal", "trade", "opt_in"]

  - id: "bounded_external_lookup_dry_run"
    mode: "dry_run_external_bounded"
    writes_allowed: false
    purpose: "Check if missing raw data is recoverable"
    required_confirm: true
    budgets_required: ["max_calls", "max_logs", "timeout"]
    forbidden: ["persistence", "unbounded_scraping", "label", "mapping", "signal", "trade", "opt_in"]

  - id: "evidence_insert_dry_run"
    mode: "dry_run_first"
    writes_allowed: false
    purpose: "Preview future evidence-only insert"
    required_guards: ["expected_digest_or_dedupe", "duplicate_check", "exact_write_scope"]
    forbidden: ["business_write", "mapping", "signal", "trade", "opt_in"]

  - id: "reliability_review_read_only"
    mode: "read_only"
    writes_allowed: false
    purpose: "Recompute current manipulation readiness from local data"
    required_flags: ["can_detect_reliable_manipulation_now=false unless all policy gates exist"]

  - id: "shadow_backtest_design_read_only"
    mode: "read_only"
    writes_allowed: false
    purpose: "Design or preview backtest/shadow scoring without client output"
    forbidden: ["signal", "trade", "wallet_order", "opt_in"]
```

## Blocked Task Registry

```yaml
blocked_tasks:
  - id: "cex_label_write"
    reason: "not relevant to current manipulation data lane and irreversible without stricter policy"
  - id: "dex_mapping_write"
    reason: "mapping requires reviewed evidence and policy approval"
  - id: "dex_router_evidence_write"
    reason: "not allowed from X or unreviewed source context"
  - id: "client_signal"
    reason: "requires source-backed scoring, backtest, policy/risk and client opt-in"
  - id: "trade_execution"
    reason: "requires paper trading proof, risk engine, capital profile, opt-in and kill switch"
  - id: "wallet_order"
    reason: "same as trade execution"
  - id: "client_opt_in_creation"
    reason: "must be user/client explicit, never agent-created"
  - id: "unrestricted_browser_or_x_scraping"
    reason: "X is lead discovery only; no broad scraping or engagement automation"
  - id: "Hermes_or_CrewAI_operator"
    reason: "too broad; lab/report-only until separate policy"
  - id: "no_op_blocked_cycle_audit"
    reason: "blocked environment checks are not progress unless they include actionable repair"
```

## Next Best Task

```yaml
next_best_task:
  id: "ufloki_source_backed_scoring_design"
  type: "shadow_backtest_design_read_only"
  plain_language: "Define how UFLOKI evidence quality should be scored from source-backed proof, without creating a client score, signal, or trade."
  why_now: "The reliability engine now consumes Transfer evidence read-only and clears the transfer-count blocker; remaining blockers are scoring, backtest, policy and opt-in."
  endpoint_to_build_or_use_next: "/api/onchain/rpc/manipulation-detection-source-backed-scoring-design"
  target_table: "dex_transfer_context_evidence"
  expected_insert_set_digest: "5d9974a07f4d95bc10136666ed8e0531f0481125b97228c740190ed681f9e382"
  expected_result:
    reliability_transfer_rows_after_bridge: 176
    absent_blocker: "too_few_transfer_rows_min_10"
    remaining_blockers: ["source_backed_scoring_not_ready", "shadow_backtest_not_ready", "policy_risk_gate_missing", "client_opt_in_missing"]
    source_backed_scoring_ready: false
    backtest_ready: false
    can_detect_reliable_manipulation_now: false
    token_transfers_unchanged: 17060
    erc20_transfer_events_unchanged: 2
    raw_swap_events_unchanged: 216
  must_remain_false:
    - "would_insert_token_transfers"
    - "would_insert_erc20_transfer_events"
    - "would_create_mapping"
    - "would_create_client_signal"
    - "would_execute_trade"
    - "would_create_client_opt_in"
```

## Safety Guards

Every task result must expose or imply:
- `dry_run=true` unless explicitly confirmed for a narrow write.
- `would_write=false` for read-only tasks.
- `writes_performed=0` for read-only tasks.
- No forbidden `would_*` flag is true.
- No label/mapping/signal/trade/opt-in surface changed.
- If any write is allowed later, exact table scope and row count are known before execution.
- If external lookup is allowed, it must have budgets and a confirm token.
- If browser/X research is used, it is lead discovery only.

## Audit Receipt Format

Agent OS Lite must produce this receipt shape after every meaningful cycle:

```yaml
audit_receipt:
  cycle_id: "<stable timestamp or generated id>"
  task_id: "<one allowed task id>"
  task_type: "<registry type>"
  operator: "Codex or scheduled Codex runner"
  runtime:
    selected: "windows_project_venv | wsl | no_runtime_required | blocked"
    degraded: true_or_false
    preflight_blockers: []
  inputs:
    rag_files_read: []
    code_files_read: []
    endpoints_called: []
    external_sources_called: []
  outputs:
    status: "completed_read_only | ready_but_disabled | blocked_actionable | completed_confirmed_scope"
    summary: "<short human-readable result>"
    data_gained: []
    blockers: []
    next_safe_step: "<one next step>"
  safety:
    would_write: false
    writes_performed: 0
    forbidden_surface_changed: false
    mapping_created: false
    label_created: false
    client_signal_created: false
    trade_executed: false
    opt_in_changed: false
  audit_policy:
    write_audit_receipt_allowed: false_by_default
    no_op_cycle: false
```

Rules:
- Do not write an audit receipt for a useless no-op.
- If blocked, include `blocked_actionable` plus the next repair step.
- If a safe fallback runtime exists, use it before stopping.

## Simple Explanation For User

Where we are:
- Core Equity has one strong research case, UFLOKI.
- Raw Swap repeatability is now real.
- Missing Transfer context is recoverable.
- The system still cannot safely produce client signals or trades.

What the OS should do next:
- Define source-backed scoring in read-only mode.
- Keep DB writes, client scores, signals and trades blocked.
- Then build shadow/backtest.

What the OS must not do:
- invent candidates
- treat X posts as proof
- write mappings/labels/signals/trades
- let Hermes/CrewAI operate Core Equity
- stop uselessly because WSL is unavailable when Windows is usable
