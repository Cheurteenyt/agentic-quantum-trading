# Core Equity Management Map

Last updated: 2026-05-22.

This file is the short source-of-truth map for agent/control management.
Use it with `core_equity_operating_map.md`.

## Purpose

Core Equity needs an agentic management layer, but not an uncontrolled agent OS.

The management goal is:
- let the project improve data quality automatically
- keep every task bounded and auditable
- replace repeated human validation with deterministic policy gates over time
- keep labels, mappings, trades, wallet orders, client signals, and opt-ins blocked until explicit policy allows them

Plain meaning: agents may help the project move faster, but they do not get freedom to touch dangerous surfaces.

Runtime policy:
- Use `rag/memory/core_equity_agent_control_plane.md` for the current machine-readable control snapshot, task registry, blocked registry, next best task and audit receipt shape.
- Use `rag/memory/core_equity_agent_task_graph.md` for detailed task states, task contracts, budgets, stop conditions and audit receipt requirements.
- Use `rag/memory/core_equity_agent_os_runtime_policy.md` for Agent OS Lite environment/preflight rules.
- WSL unavailable is not a fatal blocker when `D:\trading-agent` and `.venv-win` are available.
- The automation must not read legacy `memory.md` as its source of truth.
- A blocked no-op cycle is not progress and should not create an audit receipt unless explicitly confirmed as useful.

## Control Hierarchy

### 1. Codex Operator

Codex is the primary Core Equity operator under user direction.

Codex may:
- edit code or RAG when the user asks
- run bounded validations
- execute read-only service checks
- run explicitly confirmed data-only tasks
- integrate sidecar feedback
- decide whether a patch is safe enough to keep

Codex must not:
- bypass policy gates
- create labels, mappings, trades, client signals, wallet orders, or opt-ins unless a separate explicit goal allows exactly that narrow action
- treat sidecar output as final truth without validation

### 2. Agent OS Lite

Agent OS Lite is the future bounded automation surface.

One cycle means:
1. read current state
2. choose exactly one allowlisted task
3. execute it in dry-run/read-only or explicitly allowed data-only mode
4. validate output schema and safety flags
5. write an audit receipt only if allowed
6. stop

Before step 1, Agent OS Lite must perform runtime discovery:
- prefer the current Windows workspace when it is available
- use WSL only when available
- use Docker/Qdrant only for tasks that require it
- continue with a safe fallback instead of stopping on a missing preferred runtime

Agent OS Lite is not a free-roaming agent.

### 3. Policy/Risk Engine

The Policy/Risk Engine is the future deterministic authority.

It should decide:
- whether data is strong enough
- whether a candidate remains research-only
- whether source proof is strong or weak
- whether a route is mapping-safe
- whether a signal is client-safe
- whether paper/real trading is blocked
- whether client opt-in and capital policy are satisfied

The Policy/Risk Engine must use explicit gates, not LLM intuition.

### 4. Prompt Manager

The Prompt Manager is read-only.

It produces:
- where we are in simple language
- what is ready
- what is blocked
- the safest next mission prompt
- required guardrails and validations

It must not operate runtime, DB, endpoints, providers, scraping, labels, mappings, trades, client signals, or opt-ins.

Operational note:
- prefer `MISSION DIRECTE:` over `/goal`
- if the slash command fails, Codex should continue from the current recommended mission in `current_automation_state.md`

### 5. Sidecar Reviewers

Sidecars are advisors, not operators.

Allowed sidecars:
- Spark/Rawls/Bacon/Helmholtz for guardrail and code review
- local Qwen for focused read-only snippet review
- Hermes Safe for RAG-only/report-only summaries
- Hermes Lab and CrewAI only in separated lab contexts, outside Core Equity runtime/DB/repo writes

Sidecars must not:
- decide final product direction
- execute Core Equity writes
- operate the DB/runtime/endpoints
- create labels, mappings, trades, signals, opt-ins, migrations, or wallet actions

### 6. Future Trade Agent

The Trade Agent is future-only.

It may eventually:
- propose position logic
- manage shadow/paper positions
- manage real positions only after policy, opt-in, and risk gates

It must never bypass:
- capital profile
- max loss
- max drawdown
- leverage limits
- liquidity/slippage checks
- stop/invalidation
- kill switch
- client consent/opt-in

## Autonomy Levels

### Level 0 - Manual Codex Work

Current default.

Codex works after user instruction, validates, and reports.

### Level 1 - Prompt Manager

Read-only.

Generates the next best mission prompt from RAG.

### Level 2 - Agent OS Lite Dry-Run

Allowed direction.

Runs one read-only allowlisted task, validates, stops.

### Level 3 - Audit-Only Cycle

Allowed only with explicit confirmation.

Runs one safe task and writes only an audit receipt.

### Level 4 - Data-Only Improvement Cycle

Future.

May write bounded raw/curated data rows only when:
- task contract allows it
- confirm/policy allows it
- safety flags pass
- duplicate guards pass
- audit is written

Still no labels, mappings, trades, signals, or opt-ins.

### Level 5 - Shadow/Paper Intelligence

Future.

May simulate decisions and measure outcomes.

No real client action.

### Level 6 - Real Execution

Not current.

Requires:
- source-backed data
- proven backtests
- paper trading results
- Policy/Risk Engine
- client capital profile
- explicit opt-in
- kill switch
- full audit trail

## Task Lifecycle

Every managed task should move through:
- proposed
- contract preview
- dry-run
- validation
- audit preview
- confirmed audit or explicit data-only write
- post-run review
- RAG update if meaningful

A task must be blocked if:
- output schema is invalid
- `would_write` is true when read-only is required
- forbidden `would_*` flag is true
- duplicate guard fails
- source proof is weak
- route proof drifts
- parent chain is missing
- client/trade/opt-in path appears
- sidecar asks for runtime/write authority

## What Can Become Automatic First

Good automation candidates:
- read-only data quality audits
- route-source repair planning
- repeatability collection planning
- metadata gap scans
- curated DEX fact review
- Unknown DEX casefile generation
- shadow scoring previews
- audit receipt writing for already-validated safe cycles

These are valuable because they improve the system without touching clients or execution.

## What Must Stay Blocked

Blocked until separate explicit policy:
- CEX label creation
- DEX router evidence insertion
- DEX venue mapping
- final label table mutation
- client signals
- trade execution
- wallet orders
- swaps
- perps
- opt-ins or consent changes
- unrestricted scraping/providers
- unrestricted 24/7 agents
- Hermes/CrewAI operating Core Equity

## Current Best Management Path

Near-term:
- keep Codex as operator
- use Prompt Manager for next-goal clarity
- use Agent OS Lite for one-task dry-run cycles
- use Qwen/Helmholtz/Spark as reviewers only
- focus automation on data quality and evidence repair

Next useful managed task:
- use the Agent Control Plane current `next_best_task`.
- current next task is the UFLOKI Transfer context evidence-only confirmed DDL migration: create the empty `dex_transfer_context_evidence` table only, with zero Transfer rows inserted.
- after that, the next lane should be Transfer evidence insert dry-run-first, then reliability review.

Do not move to trade automation until data quality, policy, shadow/paper results, and client opt-in are all ready.
