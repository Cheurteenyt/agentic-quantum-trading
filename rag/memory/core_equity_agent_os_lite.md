# Core Equity Agent OS Lite

## Management Map Pointer

- Compact agent/control source of truth: `rag/memory/core_equity_management_map.md`.
- Machine-readable control snapshot and task registry: `rag/memory/core_equity_agent_control_plane.md`.
- Detailed task graph and task contracts: `rag/memory/core_equity_agent_task_graph.md`.
- Runtime/preflight source of truth: `rag/memory/core_equity_agent_os_runtime_policy.md`.
- Use this file for Agent OS Lite detail, but use the management map and control plane first for role boundaries, autonomy levels, task lifecycle, allowed tasks, blocked tasks, next best task and disabled surfaces.

## Decision

It is time to build an agentic operating layer, but not a broad unrestricted "AI OS".

The right next shape is **Core Equity Agent OS Lite**:

- Codex-operated
- policy-gated
- task-contract based
- audit-first
- data-improvement focused
- no autonomous trading yet
- no label or mapping writes by default
- no Hermes/CrewAI as Core Equity operators

This is the bridge between the current manual project and a future 24/7 system.

## Why Now

Core Equity now has enough primitives to justify an agentic control layer:

- a control plane that chooses useful next data jobs
- task contract preview
- one-task Codex runner dry-run
- audit-log preview
- confirmed audit-only write
- schedule plan read-only
- paused automation card

That means the next work is not "let an agent do anything".

The next work is to make a small operating layer that decides:

- what task is allowed now
- why this task matters
- what it can read
- what it can write
- what must remain disabled
- how the result is audited
- when the loop must stop

## What Agent OS Lite Is

Agent OS Lite is a control surface for bounded Core Equity agent cycles.

Each cycle should:

1. Read the current control-plane state.
2. Select exactly one allowlisted task.
3. Execute the task in read-only or explicitly authorized data-only mode.
4. Validate output schema and safety flags.
5. Write an audit receipt if allowed.
6. Stop.

No free-form background agent should be allowed to roam the repo, DB, runtime, browser, wallet, or trading surfaces.

## Runtime Preflight Rule

Agent OS Lite must not stop just because WSL is unavailable.

Runtime discovery order:

1. Windows workspace `D:\trading-agent` with `.venv-win\Scripts\python.exe`.
2. WSL workspace `/mnt/d/trading-agent` only if a WSL distro is actually available.
3. Docker/Qdrant only when the selected task requires RAG server/index access.

WSL failure alone is a degraded runtime condition, not a product blocker.

The cycle stops only if no safe runtime exists for the selected task, or if safety/write guards fail.

Agent OS Lite must read RAG source-of-truth files from `rag/memory`, not a legacy `memory.md`.

No-op cycle rule:

- Do not write an audit receipt for a useless blocked cycle.
- If blocked, return `cycle_status=blocked_actionable`, the failed preflight, available fallback runtimes, and the next repair step.
- If a safe fallback exists, use it instead of stopping.

## What It Is Not

Agent OS Lite is not:

- an unrestricted autonomous OS
- a Hermes/CrewAI takeover
- a self-modifying code system
- a trading bot
- a client signal system
- a label writer
- a mapping writer
- a wallet/order executor
- a scraper farm

## Roles

### Codex Operator

Codex remains the operator for Core Equity automation.

Allowed:

- select a bounded task
- execute allowlisted service calls
- validate safety flags
- write audit receipts when confirmed
- update RAG after meaningful milestones

Forbidden:

- free-form DB writes
- labels
- mappings
- trades
- wallet orders
- client signals
- opt-ins

### Policy Engine

The Policy Engine is the deterministic authority.

It should decide:

- task allowed or blocked
- data-only write allowed or blocked
- source proof strong enough or weak
- candidate ready for shadow scoring or not
- trade/client actions blocked until future opt-in and risk policy

It should not use vibes or LLM judgment as final authority.

### Sidecar Reviewers

Spark/Rawls/Bacon/Helmholtz/Qwen can review.

Allowed:

- read-only critique
- code review
- guardrail review
- report quality review

Forbidden:

- deciding final product action
- DB writes
- runtime operation
- labels/mappings/trades/signals/opt-ins

### Hermes / CrewAI

Hermes and CrewAI can be lab/report-only tools later.

Allowed:

- RAG-only summaries
- strategy reports
- lab-only orchestration experiments
- comparisons outside sensitive Core Equity execution

Forbidden:

- Core Equity operator role
- writing RAG/DB/runtime state
- starting production jobs
- labels/mappings/trades/signals/opt-ins

## Operating Modes

### Mode A - Manual Safe

User says "continue".

Codex performs one scoped step, validates, updates RAG.

This is the current safe mode.

### Mode B - Paused Schedule

A schedule exists as a paused card.

Nothing runs until explicitly enabled.

Purpose:

- inspect cadence
- inspect prompt
- inspect stop conditions
- verify no dangerous action is listed

### Mode C - Audit-Only Recurring

Future mode.

The schedule can run one cycle and write one audit receipt.

Allowed:

- read-only task execution
- audit-only `data_jobs` write

Still forbidden:

- raw data collection unless a separate task policy allows it
- labels
- mappings
- trades
- client signals
- opt-ins

### Mode D - Data-Only Recurring

Future mode.

Some collection tasks may write raw data only after bounded policy approval.

Allowed examples:

- exact block windows
- exact transfer windows
- token metadata repair
- provenance rows

Forbidden:

- business decisions
- labels
- mappings
- client outputs
- trades

### Mode E - Shadow Intelligence

Future mode.

The system simulates decisions and records whether they would have helped.

Allowed:

- shadow scoring
- paper evaluation
- false positive/false negative tracking
- policy improvement proposals

Forbidden:

- real client signals
- real trades

### Mode F - Real Controlled Trading

Not current.

Requires:

- client opt-in
- risk profile
- capital profile
- max daily loss
- max drawdown
- max leverage
- liquidity/slippage/MEV checks
- kill switch
- paper trading proof
- audit trail

## First OS Components To Build

### 1. Agent State Snapshot

Simple output:

- current data quality
- current best task
- last audit job
- active blockers
- what is still disabled

### 2. Task Queue View

Not a DB queue at first.

A read-only ranking of tasks:

- data repair
- route proof
- source proof
- metadata repair
- backtest/shadow readiness

### 3. Cycle Policy Gate

Before any cycle:

- task must be allowlisted
- output schema expected
- write scope known
- stop conditions known
- audit required

### 4. Audit Receipt Ledger

Already started through `data_jobs`.

Need to keep:

- one audit per unique cycle result
- duplicate blocking
- safety result
- next safe step

### 5. Schedule Control

Future schedule should start paused.

It must expose:

- cadence
- max cycles/day
- max task/runtime budget
- stop conditions
- disabled surfaces

## Product Direction

The agentic OS should first improve data quality, not chase trades.

Best next data goals:

- turn context-only candidates into source-backed candidates
- improve route/source proof for unknown DEX paths
- repair token metadata and identity gaps
- collect bounded exact raw data where it directly improves a candidate
- build repeatability and backtest readiness

Only after that should intelligence/trading layers become meaningful.

## Current Status

Core Equity is not "done".

But it has moved from manual prompts toward a safe agentic foundation:

- it can select a task
- run one task safely
- audit the task
- block duplicate audit writes
- describe a future schedule
- keep labels/mappings/trades/signals disabled

The next useful milestone is not a full OS. It is Agent OS Lite v1:

- state snapshot
- task queue view
- schedule card still paused
- audit receipts
- no business writes

Current correction:
- the Agent Control Plane is now the first source for `current_state`, `allowed_tasks`, `blocked_tasks`, `next_best_task`, `safety_guards`, and `audit_receipt_format`.
- Agent OS Lite should not generate prompts from stale historical recommendations when the control plane has a newer next task.
