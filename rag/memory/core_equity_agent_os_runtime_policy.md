# Core Equity Agent OS Runtime Policy

Last updated: 2026-05-22.

## Purpose

This file fixes a bad automation pattern:

- stopping the cycle only because WSL is unavailable
- reading a legacy `memory.md` instead of the Core Equity RAG source of truth
- writing a useless "cycle stopped" report without choosing a useful next action

Plain meaning: Agent OS Lite must be runtime-aware. It should not confuse a local environment issue with product safety.

## Source Of Truth

Agent OS Lite must read current state from:

1. `rag/memory/core_equity_operating_map.md`
2. `rag/memory/core_equity_management_map.md`
3. `rag/memory/current_automation_state.md`
4. `rag/memory/project_state.md` only for history

Do not use `memory.md` as the automation source of truth unless a future explicit migration creates that file as a generated alias.

## Runtime Discovery Order

Before a cycle, Agent OS Lite must discover available runtimes in this order:

1. Windows workspace:
   - project path: `D:\trading-agent`
   - Python: `D:\trading-agent\.venv-win\Scripts\python.exe`
   - status: primary fallback when WSL is unavailable
2. WSL workspace:
   - project path: `/mnt/d/trading-agent`
   - use only if `wsl.exe -l -q` returns a distro and `/mnt/d/trading-agent` exists
3. Docker/Qdrant:
   - optional for RAG/index availability
   - absence is degraded mode unless the selected task explicitly requires it

WSL unavailable is not a fatal Core Equity blocker if the Windows workspace and Windows Python are available.

## Hard Stop Conditions

Stop the cycle only if:

- neither `D:\trading-agent` nor `/mnt/d/trading-agent` is available
- no usable Python runtime exists for a task that requires direct service execution
- the selected task would write outside its allowed scope
- output schema is invalid
- any forbidden `would_*` flag is true
- label/mapping/trade/client-signal/opt-in path appears unexpectedly
- credentials/secrets are requested

Do not stop merely because:

- WSL is unavailable
- Docker is not running, unless the selected task requires Qdrant/RAG server
- a preferred runtime is down but a safe fallback runtime exists

## No-Op Cycle Rule

Agent OS Lite must not produce an empty "cycle stopped" report as if it were progress.

If the cycle cannot run the selected task, it must return:

- `cycle_status=blocked_actionable`
- the exact failed preflight
- the safe fallback runtime or why none exists
- the next repair step
- no audit write unless explicitly useful and confirmed

If a fallback runtime exists, it must continue with the fallback instead of stopping.

## Current Preferred Behavior

For the current project state, the best Agent OS Lite cycle is:

- select one safe data-quality task
- prefer the current local DEX event-reader lane when it is the freshest blocker
- use Windows Python direct service calls if WSL is not available
- keep the cycle read-only unless a separate confirmed data-only write is explicitly allowed

Current freshest safe task:

- use the Agent Control Plane `next_best_task`
- current task: `ufloki_source_backed_scoring_design`
- next possible product step: define source-backed scoring in read-only mode, with no DB mutation and no signal/trade

## Runtime Preflight Endpoint

The runtime policy is now also enforced in code through:

- `/api/onchain/rpc/core-equity-agent-os-lite/runtime-preflight?event_reader_run_id=1&dry_run=true`

Expected behavior:

- select `windows_project_venv` when `D:\trading-agent\.venv-win\Scripts\python.exe` is available
- treat WSL absence as degraded, not fatal
- read project RAG source-of-truth files, not automation-local `memory.md`
- expose the current safe task from the Agent Control Plane
- report `blocked_actionable` only when no safe runtime/task exists
- keep all writes disabled

## Cycle Preview Endpoint

Agent OS Lite can now preview one safe cycle in code through:

- `/api/onchain/rpc/core-equity-agent-os-lite/cycle-preview?event_reader_run_id=1&dry_run=true`

Expected behavior:

- run runtime preflight
- select exactly one safe task
- current task comes from `core_equity_agent_control_plane.md`
- validate the task contract and safety flags
- describe the selected data-quality/read-only task without unsafe writes
- stop before execution
- keep `would_write=false` and `writes_performed=0`

## Stable Local Runner

External or recurring Agent OS cycles should invoke the stable local runner instead of reimplementing runtime checks:

- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\core_equity_agent_os_lite_cycle.ps1 -EventReaderRunId 1 -MaxRpcCalls 25`

Expected behavior:

- discover usable Python by actually executing candidates
- prefer `D:\trading-agent\.venv-win\Scripts\python.exe`
- fall back to project/system Python only if needed
- call the official runtime preflight and cycle preview services directly
- read `rag/memory` source-of-truth files
- never use legacy `memory.md`
- return JSON with `preflight_status`, `cycle_preview_status`, selected runtime, selected task, blockers and safety flags
- keep `would_write=false` and `writes_performed=0`

If a separate automation reports that `.venv-win` is broken while this runner returns `ready_degraded` or `ready_read_only`, treat that automation as stale or misconfigured.

Latest data result:

- `/api/onchain/rpc/dex-local-event-reader-run/execution-dry-run?event_reader_run_id=1&dry_run=true&allow_rpc=true`
- attempted all 24 planned calls with no persistence
- recovered 0 logs because public BSC RPC providers block or prune the needed historical ranges
- the follow-up SQD/indexer dry-run is now implemented through `/api/onchain/rpc/dex-local-event-reader-run/sqd-lookup-dry-run`
- SQD completed all 24 planned calls with explicit confirm, recovered 3 logs in memory only, and still wrote nothing
- the SQD raw-event persistence lane is now implemented through `/api/onchain/rpc/dex-local-event-reader-run/sqd-raw-event-persistence`
- confirmed preview completed all 24 planned SQD calls again and prepared 3 clean raw event candidates: 1 future raw PairCreated row and 2 future ERC20 Transfer rows
- persistence digest for a future confirmed raw insert is `1ccd64297695376b72fa2942de6f800ac08c9a489f33379612cd2c0146540850`
- wrong expected digest blocks real persistence with `writes_performed=0`
- earlier event-reader raw persistence inserted exactly 3 non-Swap rows: `dex_raw_paircreated_events=1`, `erc20_transfer_events=2`; this is historical context and does not override the current `dex_raw_swap_events=216`
- duplicate persistence is blocked by `checkpoint_already_has_raw_events`
- proof-package preview is now implemented through `/api/onchain/rpc/dex-local-event-reader-run/proof-package-preview`
- proof-package preview is `ready_read_only`, binds payload digests, and returns `proof_package_digest=886be39bf64af8da77c84a006cdb903c5174369be63e388420635fc4529b3873`
- proof-package insert is now implemented through `/api/onchain/rpc/dex-local-event-reader-run/proof-package/insert`
- confirmed proof-package insert created `proof_package_id=1` with status `pending_admin_review`
- duplicate proof-package insert is blocked by `proof_package_duplicate_exists`
- proof-package review queue is now implemented through `/api/onchain/rpc/dex-event-proof-packages/review`
- proof-package review returns `proof_package_id=1` as `ready_for_proof_package_decision_preview` with digest/dedupe/raw references bound
- proof-package decision preview is now implemented through `/api/onchain/rpc/dex-event-proof-packages/decision-preview`
- accept preview for `proof_package_id=1` returns `decision_allowed=true`, future status `accepted_for_future_proof_package_evidence_review`, and no write
- proof-package status-only apply is now implemented through `/api/onchain/rpc/dex-event-proof-packages/decision/apply`
- confirmed apply moved `proof_package_id=1` to `accepted_for_future_proof_package_evidence_review` with exactly one status write
- second apply is blocked because the package is no longer pending
- proof-package evidence review contract is now implemented through `/api/onchain/rpc/dex-event-proof-packages/evidence-review-contract`
- the contract detects that `proof_package_id=1` corroborates existing PairCreated evidence `id=1`, so the next safe action is corroboration review, not duplicate evidence insertion
- proof-package corroboration review is now implemented through `/api/onchain/rpc/dex-event-proof-packages/corroboration-review`
- the review reports `strong_same_paircreated_event_plus_transfer_context`, with raw refs bound and 2 transfer context rows
- manipulation detection reliability engine is now implemented through `/api/onchain/rpc/manipulation-detection-reliability-engine`
- current reliability verdict is `can_detect_reliable_manipulation_now=false`; best lead is UFLOKI, raw Swap repeatability is present, and the remaining immediate data blocker is Transfer context not being consumed by reliability
- manipulation exact Swap collection plan is now implemented through `/api/onchain/rpc/manipulation-detection-exact-swap-collection-plan`
- current exact Swap plan is read-only and identifies 2 executable UFLOKI windows: `98567156-98568656` and `99066916-99067916`
- STAR/ODY/ETHEREUM/BUN are visible as blocked hints only because PairCreated evidence is missing
- manipulation exact Swap SQD lookup dry-run is now implemented through `/api/onchain/rpc/manipulation-detection-exact-swap-sqd-lookup-dry-run`
- exact raw Swap evidence is now persisted: `dex_raw_swap_events=216`, with `156` distinct txs, `156` distinct blocks, and `2` independent raw activity windows
- raw Swap repeatability is now consumed by the reliability engine as `repeatability_status=present_from_raw_events`
- Transfer context evidence is now persisted in `dex_transfer_context_evidence=169`, reviewed as clean, and duplicate-safe
- latest bridge preview reports `bridge_status=ready_but_disabled`, current best Transfer rows `7`, projected best Transfer rows `176`, and `would_clear_too_few_transfer_rows_min_10=true`
- latest bridge apply contract reports `contract_status=ready_but_disabled`, required future confirm `APPLY_UFLOKI_TRANSFER_CONTEXT_RELIABILITY_BRIDGE`, and applies nothing
- reliability engine bridge integration is now active read-only: UFLOKI best Transfer rows are `176` and `too_few_transfer_rows_min_10` is absent
- next safe data move is source-backed scoring design read-only, not mapping/signals/trading

Still disabled:

- additional raw event persistence unless separately confirmed with expected digest
- additional proof-package persistence unless separately confirmed
- PairCreated evidence promotion
- DEX mapping
- CEX label
- client signal
- trade
- wallet order
- opt-in

## Automation Prompt Requirements

Future automation prompts must include:

- "Use runtime discovery; WSL failure alone is not fatal."
- "Use `D:\trading-agent` + `.venv-win` if WSL is unavailable."
- "Read Core Equity RAG source-of-truth files, not legacy `memory.md`."
- "Run at most one allowlisted task."
- "Do not write audit for a useless no-op cycle."
- "Return a useful next safe action even when blocked."

This makes the automation behave more like an operating layer and less like a fragile script.
