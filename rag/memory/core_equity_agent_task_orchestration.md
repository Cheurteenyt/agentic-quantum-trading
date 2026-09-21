# Core Equity Agent Task Orchestration - Read-Only Design

## Management Map Pointer

- Compact agent/control source of truth: `rag/memory/core_equity_management_map.md`.
- Use this orchestration file for detailed model/task notes. Use the management map first for who can operate Core Equity, who is only a sidecar, and which autonomy levels are allowed.

## Purpose

Core Equity should eventually run with agents that improve data quality, evaluate evidence, plan shadow decisions, and prepare trade policies without requiring the user to manually push every tiny step.

The goal is not to let a free-form agent control the project. The goal is to build a controlled agent operating system around the product:

- task contracts
- read-only first execution
- deterministic policy gates
- audit logs
- model-specific responsibilities
- hard disabled surfaces for labels, mappings, trades, client signals, wallet orders, and opt-ins

## Current Recommendation

Use Codex/Core Equity as the main operator, not Hermes.

Hermes should remain a lab/safe analyst for now because it has powerful toolsets such as terminal, files, browser, code execution, delegation, cron, and memory. That makes it useful for research, but too broad to connect directly to the sensitive Core Equity pipeline.

The practical setup should be:

- Codex/GPT-5.5: implementation, product direction, safety validation, final decisions.
- Core Equity Policy/Risk Engine: future machine authority that accepts, repairs, rejects, or blocks pipeline progression.
- Spark/Rawls/Bacon/Helmholtz: primary sidecar reviewers for Core Equity guardrails.
- Local Qwen: focused read-only snippet reviewer and cheap sanity-check sidecar.
- Hermes Safe: occasional RAG-only/report-only summaries.
- Hermes Lab: separate experiments outside Core Equity, never operating the repo, DB, runtime, or endpoints.

## Why Not Hermes As Main Operator Yet

Hermes is useful, but it should not own Core Equity execution yet.

Reasons:

- It has broad tools that are easy to misuse around a sensitive trading/data system.
- It does not automatically understand the project-specific safety contracts better than the repo itself.
- Core Equity needs deterministic policy gates, not a general-purpose agent deciding from vibes.
- Trading/label/mapping/client actions need auditability and rollback logic.
- The project already has a control-plane direction; Hermes should plug in only after roles are narrow and testable.

Hermes can still be valuable:

- summarize RAG state
- compare strategies
- critique prompts
- run lab-only tool experiments
- produce non-authoritative reports
- help test future agent workflows outside Core Equity

## Model Assignment

### Main Cloud/Frontier Operator

Use Codex/GPT-5.5 for:

- code changes
- architecture changes
- safety-critical decisions
- final validation
- DB/endpoint guard reasoning
- risk-policy design
- deciding whether sidecar feedback is actionable

This is the only AI layer currently allowed to modify Core Equity files under user direction.

### Local Qwen Default Reviewer

Use `qwen3-2507-fast` as the default local read-only reviewer.

Best for:

- focused snippets
- checking whether a guard is coherent
- checking read-only/write semantics
- catching obvious missing tests
- reviewing small service/router patches

Rules:

- pass concrete snippets, not broad abstract questions
- never trust line references without verification
- no repo writes
- no DB reads/writes
- no endpoint execution
- advisory only

### Local Qwen Code Reviewer

Use `qwen3-coder-fast` for code-specific second opinions.

Best for:

- patch review
- refactor risk review
- test-gap review
- comparing service/router behavior

Risk:

- can over-alert or invent line references if context is too abstract

### Local Fast Fallback

Use `qwen25-fast` when speed matters more than depth.

Best for:

- quick sanity checks
- small guard review
- short prompt-manager reports

### Local Deep/Experimental Models

Use MoE/deep profiles only on demand:

- `moe-fast`
- `moe-deep`
- `qwen35-a3b-fast`
- `qwen3-coder-kvq`

Best for:

- larger snippets
- architecture critique
- comparing multiple reports

Rules:

- do not keep always on by default
- benchmark before promoting a profile
- treat output as advisory
- strip/ignore reasoning tags

### New Model Installs

No new local model is required right now.

The current model set is enough for the next phase. The bottleneck is not model intelligence; it is data quality, source proof, route proof, repeatability, backtest, liquidity/slippage/MEV modeling, and risk-policy design.

Future model installs should be justified only if they improve one of these:

- longer grounded report review
- better code-review reliability on concrete snippets
- faster local sidecar latency on RTX 3070 8GB
- structured JSON/report generation without hallucinating facts

## Agent Roles

### 1. Data Agent

Mission:

- find missing local data
- plan bounded RPC collection
- validate raw swaps/transfers/pools
- keep collection scoped and auditable

Allowed now:

- read-only audits
- dry-run collection plans
- confirmed raw-data-only collection only when explicitly approved

Forbidden:

- labels
- mappings
- trades
- wallet orders
- client signals
- opt-ins

### 2. Evidence Agent

Mission:

- repair metadata
- repair source proof
- repair route proof
- identify when a candidate is source-backed vs context-only

Allowed now:

- read-only repair plans
- exact proof checklists
- source quality grading

Forbidden:

- final venue mapping writes
- DEX router evidence writes
- CEX labels
- client-facing outputs

### 3. Intelligence Agent

Mission:

- turn clean data into hypotheses
- detect manipulation-like patterns
- propose scoring features
- run shadow/backtest plans

Allowed later:

- read-only scoring
- shadow simulations
- backtest reports

Forbidden now:

- client signals
- trades
- performance claims

### 4. Policy/Risk Agent

Mission:

- replace repeated human admin review with deterministic gates
- accept, repair, reject, or block candidate progression
- enforce source, parent-chain, dedupe, route, drift, risk, and client-policy rules

This is the future authority layer.

It can eventually allow:

- administrative status transitions
- candidate review-row insertion
- source-backed knowledge writes

It must block:

- uncertain labels
- uncertain mappings
- unsafe trades
- missing client opt-in
- missing liquidity/risk model

### 5. Trade Agent

Mission:

- create trade plans only after Policy/Risk allows trading evaluation
- propose entry, invalidation, sizing, take-profit, trailing stop, cooldown, and exit logic

Allowed later:

- shadow trade plans
- paper trading plans
- risk-reviewed execution proposals

Forbidden now:

- real trades
- wallet orders
- perps/spot execution
- client signals
- auto opt-ins

### 6. RAG/Memory Agent

Mission:

- update durable project state after validated milestones
- keep simple status understandable
- generate next-goal prompts
- prevent project amnesia

Allowed now:

- RAG memory updates
- prompt-manager outputs
- reports

Forbidden:

- runtime actions
- DB writes
- code changes unless Codex performs them directly

## Automation Levels

### Level 0 - Current Interactive Mode

The user says "continue" or gives a `/goal`.

Codex:

- chooses the next safe step
- patches if needed
- tests
- updates RAG
- explains simply

This is current mode.

### Level 1 - Prompt Manager Mode

A read-only prompt manager produces:

- where we are
- next safe task
- guardrails
- validation checklist
- disabled surfaces

No runtime actions. No DB. No writes except optional RAG updates by Codex.

### Level 2 - Agent Control Plane Shadow Mode

Core Equity reads diagnostics and recommends the next agent job.

The system can say:

- collect more raw data
- repair metadata
- repair route/source proof
- run post-collection audit
- run shadow scoring plan

It still does not execute automatically.

### Level 3 - Controlled Agent Runner

Future local runner.

It should execute only allowlisted tasks with contracts:

- task id
- allowed files/tables/endpoints
- dry-run required
- confirmation policy
- max runtime
- expected output schema
- forbidden actions
- audit log

No free-form "agent do whatever".

### Level 4 - Autonomous Administrative Progression

The Policy/Risk Engine may apply status-only transitions or insert review/intention rows if deterministic gates pass.

Still forbidden:

- labels
- mappings
- client signals
- trades
- opt-ins

### Level 5 - Autonomous Knowledge Writes

Only after enough proof quality:

- source-backed labels
- source-backed mappings
- curated evidence writes

Still no trades unless client/risk mode is active.

### Level 6 - Shadow/Paper Trade Automation

The Trade Agent can simulate decisions:

- shadow mode first
- paper trading second
- compare outcome against holdout data
- record false positives/false negatives
- improve policies from measured results

No real money.

### Level 7 - Real Controlled Execution

Only after:

- explicit client opt-in
- risk profile
- wallet/order permissions
- kill switch
- max loss rules
- max leverage rules
- liquidity/slippage checks
- paper trading proof
- full audit trail

## How Tasks Should Be Set Up

Every automated task should be a contract, not a vague prompt.

Required fields:

- `task_id`
- `agent_role`
- `input_sources`
- `allowed_actions`
- `forbidden_actions`
- `dry_run_default`
- `confirm_required`
- `expected_outputs`
- `success_criteria`
- `failure_blockers`
- `sidecar_review_required`
- `writes_allowed`
- `audit_log_required`

Example:

```text
task_id: unknown_dex_candidate_route_source_repair
agent_role: Evidence Agent
input_sources: post-collection audit + candidate repair plan
allowed_actions: read local diagnostics, produce repair rows
forbidden_actions: DB writes, mappings, labels, trades, client signals
dry_run_default: true
expected_outputs: route_source_repair_rows, blockers, next_safe_step
writes_allowed: false
```

## Practical Next Build

The next practical build should not be Hermes automation yet.

Build this instead:

1. Extend the existing Core Equity control plane into a task registry view.
2. Each recommended job should expose:
   - who should run it
   - why it matters
   - what it reads
   - what it cannot do
   - expected validation
   - current blocker
3. Add a read-only "agent task contract preview" endpoint.
4. Later add a local runner that can execute only read-only or data-only allowlisted jobs.

This gives us agent automation without turning the project into chaos.

## Final Position

Do not choose between Hermes and Codex as if one must control everything.

Use:

- Codex as the builder/operator under user direction
- Core Equity Policy/Risk Engine as the future deterministic authority
- Qwen as cheap local focused reviewer
- Spark/Rawls/Bacon/Helmholtz as primary guard reviewers
- Hermes as lab/safe analyst until it earns a narrow role

The product becomes autonomous through contracts and policy gates, not through one big unrestricted agent.
