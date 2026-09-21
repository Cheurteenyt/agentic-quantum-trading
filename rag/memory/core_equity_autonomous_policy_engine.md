# Core Equity Autonomous Policy Engine - Read-Only Design

## Management Map Pointer

- Compact agent/control source of truth: `rag/memory/core_equity_management_map.md`.
- Use this file for the long-term policy-engine design. Use the management map first for current operator boundaries, allowed autonomy levels, and blocked surfaces.

## Purpose

Core Equity should not become a project where the owner or the client clicks through every review step.

The final product direction is automation-first:
- detect token-market opportunities automatically
- enrich and verify them automatically
- decide readiness automatically through policy gates
- prepare or execute allowed actions automatically when policy permits
- keep dangerous actions behind hard machine limits, audit logs, rollback plans, opt-in policy, and kill switches

The current admin-review pipeline is useful as a safety scaffold, but it is not the final operating model.

## Current State

Core Equity currently has a strong review-first rail:
- local radar can discover token-market leads from local traces
- `LAB` has passed through a long staged pipeline to a final label-write safety checkpoint
- each sensitive step checks dedupe, source/digest, JSON contract, parent chain, route, and disabled write flags
- real label, mapping, trade, wallet order, signal, and opt-in paths remain disabled

This proves the safety gates work, but it also shows the main product gap:
- too many steps assume human/admin validation
- too many surfaces are status-only
- discovery is still early
- the client-facing end state is not autonomous enough

## Product Reframe

Replace "human approves every step" with "policy engine evaluates every step".

The policy engine becomes the decision layer between:
- raw local observations
- source repair/enrichment
- candidate packets
- evidence packets
- label or mapping readiness
- client-facing automation eligibility
- any future execution action

Humans should configure the policy, review audit reports, and intervene only on incidents or policy changes.

## Final System Roles

### Data Engine

Role:
- collect local on-chain observations
- normalize swaps, transfers, pools, routers, wallets, sources, and provenance
- separate raw facts from inferred facts
- preserve exact evidence, digests, parent rows, and duplicate keys

Current focus:
- build trustworthy DEX trade facts from raw Swap logs
- repair token metadata, amount USD trust, and venue/router identity
- keep poisoned or ambiguous data visible for audit but blocked for decisions

The Data Engine must not decide trades. It only supplies evidence quality.

### Intelligence Engine

Role:
- detect candidate manipulation patterns
- compare wallets, token flows, pools, venues, source-backed routes, and timing
- produce a thesis packet, not an execution

Example outputs:
- possible accumulation before liquidity change
- suspicious pool activity cluster
- wallet group moving through DEX then CEX route
- token-market anomaly that deserves policy evaluation

The Intelligence Engine can be creative, but its outputs remain hypotheses until the Policy/Risk Engine accepts them.

### Policy/Risk Engine

Role:
- turn hypotheses into machine decisions
- replace repeated human accept/reject steps with deterministic gates
- enforce mode limits, source quality, parent-chain, dedupe, route, risk, and client policy

This is the authority layer. If the Trade Agent, Hermes, local Qwen, or any sidecar suggests an action, the Policy/Risk Engine can still block it.

### Trade Agent

Role:
- prepare trade plans only after policy allows a candidate to enter trading evaluation
- propose entry, invalidation, sizing, exit logic, and risk conditions
- run shadow or paper decisions before any real execution

The Trade Agent must not have unrestricted wallet authority.

It can only act through:
- explicit automation mode
- client policy and opt-in
- risk limits
- position size limits
- cooldown limits
- kill switch
- full audit trail

### Orchestrator Roles

Codex:
- keeps product direction, implementation quality, safety, and final validation
- edits Core Equity code/RAG when asked
- decides whether sidecar feedback is actionable

Spark/Rawls or Bacon:
- primary Core Equity sidecar review
- verifies flows, guards, tests, and disabled surfaces
- advisory only, no file or DB authority unless explicitly assigned in a future safe workflow

Hermes:
- research/lab/safe analyst by default
- useful for summaries, comparisons, report generation, prompt experiments, and external tool experiments outside Core Equity
- not a Core Equity operator unless a future explicit integration policy grants a narrow read-only role

Local Qwen models:
- local read-only code/design reviewer
- useful for focused snippets and sanity checks
- advisory only; outputs must be verified because local models can hallucinate line refs or over-warn

## Current Admin Reviews To Convert

These current human/admin decision patterns should become future automatic policy gates:
- `pending_admin_review` becomes `pending_policy_evaluation`
- decision preview becomes `policy_decision_preview`
- confirmed status-only apply becomes `policy_status_apply`
- `request_better_source` becomes `policy_source_repair_required`
- `reject` becomes `policy_rejected_with_reason`
- `accepted_for_future_*` becomes `policy_accepted_for_next_stage`

The existing queues can remain as audit containers, but the actor changes from human/admin to policy engine.

## Policy Gates

Every automatic progression must pass machine-checkable gates.

### Source Gates

Required:
- official or accepted source URL when a source-backed claim is needed
- source tier in allowed set
- evidence type present
- stable evidence digest
- source policy recorded
- no screenshots or aggregator-only proof for final claims

Typical thresholds:
- Tier 1 source required for final CEX label writes
- Tier 1 or Tier 2 source allowed for candidate/evidence review progression
- Tier 3 can only prioritize, never finalize

### Local Evidence Gates

Required:
- local observation count above minimum
- independent signal count above minimum
- infrastructure-token handling applied
- non-base token preference for discovery
- route-specific local evidence present

Example thresholds:
- at least 2 independent local signals for autonomous candidate packet
- at least 1 source-backed external/official proof before source-backed candidate promotion
- infrastructure tokens are fallback only unless policy explicitly targets them

### Dedupe And Drift Gates

Required:
- dedupe key stable
- no duplicate in same stage
- no silent upsert
- parent dedupe still bound
- source/digest still bound
- JSON contract still valid and bound
- route has not changed unexpectedly

Any drift blocks automation and routes to repair.

### Parent-Chain Gates

Required:
- every parent row still exists
- parent status is accepted by policy or already immutable
- parent source/digest matches child expectation
- no missing candidate/evidence/promotion/downstream ancestry

Missing parent blocks automation.

### CEX/DEX Route Gates

CEX:
- CEX market route must remain CEX-only
- CEX review is not a direct label write
- final label write requires label-specific policy gates

DEX:
- DEX route must remain DEX-only
- DEX router evidence is not a direct mapping write
- mapping write requires mapping-specific policy gates

Mixed, hybrid, aggregator, perp, or unclear:
- route to `policy_source_repair_required`
- no autonomous final action

### Risk Gates

Required before any real write:
- bounded blast radius
- max rows per run
- max writes per table per run
- rollback plan or reversible artifact where applicable
- audit log entry required
- kill switch checked
- dry-run/shadow result recorded before real mode

### Client Automation Gates

Client-facing automation requires a separate policy layer.

Before any client signal, wallet order, trade, or opt-in-based action:
- client policy exists
- client opt-in exists
- asset universe allowed
- max exposure defined
- max action frequency defined
- risk score under threshold
- manipulation/readiness gates pass
- emergency stop available
- full audit event generated

Without those, client automation remains blocked even if token-market labels/mappings are ready.

## Shadow Trading And Paper Trading

### Shadow Mode

Shadow mode means the system records what it would have done without changing client state.

Allowed:
- score opportunities
- propose candidate actions
- record hypothetical entries/exits
- compare predicted outcome vs actual market movement
- produce audit reports and performance metrics

Blocked:
- real trade
- wallet order
- client signal
- client opt-in mutation

Shadow mode is the first proof that the policy and intelligence layers can work without risking capital.

### Paper Trading

Paper trading means simulated positions with explicit virtual capital and portfolio rules.

Allowed:
- simulated fills
- simulated PnL
- simulated drawdown
- simulated exposure/risk reports
- strategy comparison

Blocked:
- real execution
- wallet signing
- client-facing advice
- automatic opt-in or policy mutation

Paper trading should start only after shadow predictions have enough history to measure quality.

### Real Trading

Real trading remains the last stage.

Required before real trading:
- source-backed and locally verified data
- enough backtest/shadow/paper evidence
- client policy and opt-in
- per-client risk limits
- asset universe allowlist
- max exposure
- max loss/day
- max trades/day
- cooldowns
- kill switch
- execution audit logs
- rollback/incident workflow

No single AI agent may bypass these requirements.

## Result Measurement

The system should measure quality before claiming profit potential.

Data quality metrics:
- exact Swap-log coverage
- curated DEX trade coverage
- token metadata completeness
- venue/router identity coverage
- amount USD quarantine rate
- source-backed candidate rate

Detection metrics:
- number of candidates detected
- number accepted by policy
- number blocked by source/dedupe/route/risk
- false-positive review rate
- repeatability across multiple tokens

Trading metrics in shadow/paper:
- hit rate
- average win/loss
- max drawdown
- time to invalidation
- slippage assumption error
- liquidity failure rate
- post-signal adverse movement
- profit factor

Client safety metrics:
- policy blocks triggered
- exposure prevented
- emergency stop activations
- rejected trades after drift
- opt-in/policy compliance

Profit is not a promise. The system must earn trust through measured shadow and paper results before any real execution.

## Self-Improvement Loop

Core Equity should become self-improving, but not self-mutating in unsafe ways.

Allowed self-improvement:
- compare predictions with outcomes
- tune thresholds in shadow mode
- rank data sources by usefulness
- discover recurring blockers
- propose new collection jobs
- propose policy threshold changes
- generate reports for Codex/product review

Blocked self-improvement:
- changing critical policy without review
- changing client risk limits automatically
- enabling real trades automatically
- writing labels/mappings from unreviewed model suggestions
- modifying wallet permissions
- creating opt-ins
- silently changing code

Safe loop:
1. Observe result.
2. Score prediction quality.
3. Identify which data or policy gate failed.
4. Propose improvement.
5. Test in shadow/backtest.
6. Promote only if metrics improve and safety gates still pass.

## Automatic Decision Replacements

### Accept

Human version:
- `accept_for_future_*`

Policy version:
- `policy_accepted_for_next_stage`

Allowed only if:
- all source, dedupe, parent, JSON, route, and risk gates pass
- no blocker is present
- action is inside the current automation mode

### Request Better Source

Human version:
- `request_better_source`

Policy version:
- `policy_source_repair_required`

Triggered by:
- missing official source
- weak source tier
- missing digest
- source/digest drift
- unknown symbol
- route unclear
- local-only evidence when source-backed evidence is required

### Reject

Human version:
- `reject`

Policy version:
- `policy_rejected_with_reason`

Triggered by:
- duplicate
- route contradiction
- source contradiction
- known blocked token/entity
- parent chain broken
- policy threshold failed repeatedly

## Automation Modes

### Mode 0 - Current Admin Scaffold

Current state:
- admin review everywhere
- many read-only contracts
- confirmed status-only steps
- no final label/mapping/trade/client writes

Purpose:
- prove the safety chain
- collect contracts and gates
- prevent accidental writes

### Mode 1 - Shadow Policy Engine

Next target:
- policy engine reads the same queue state and produces automatic decisions
- no DB writes
- no status updates
- no labels
- no mappings
- no trades
- no opt-ins

Output:
- `policy_decision=accept|repair|reject`
- `policy_confidence`
- `policy_reasons`
- `failed_gates`
- `next_action`
- `would_advance=true/false`

This mode proves the policy can replace human review without changing state.

### Mode 2 - Autonomous Administrative Progression

Future target:
- policy engine can apply status-only transitions
- policy engine can insert review/intention rows
- still no final labels, mappings, trades, wallet orders, signals, or opt-ins

Hard limits:
- only explicitly allowed tables
- max rows per run
- duplicate blocks
- no upsert
- all changes audited
- rollback metadata available

### Mode 3 - Autonomous Knowledge Writes

Future target:
- policy engine can write labels or mappings only when strict policy gates pass

Examples:
- CEX label write after Tier 1 source, stable digest, parent chain, dedupe, route, and shadow history pass
- DEX mapping write after official router evidence, chain validation, duplicate checks, rollback plan, and route separation pass

Hard limits:
- no trade execution
- no client action
- no wallet order
- every write is audited
- kill switch must be active

### Mode 4 - Autonomous Client Automation

Future target:
- client-facing automation can run only under explicit client policy and opt-in.

Allowed only if:
- client opt-in/policy exists
- manipulation/readiness gates pass
- risk limits pass
- action size/frequency limits pass
- stop-loss/kill-switch rules exist where relevant
- full audit log is written

Without this layer, no client trade, wallet order, signal, or opt-in mutation may run.

## Actions That Can Become Fully Automatic

Near-term:
- local radar scoring
- infrastructure-token filtering
- source-repair planning
- candidate packet generation
- evidence packet generation
- dedupe/drift checks
- parent-chain checks
- route classification
- read-only policy decision previews

Mid-term:
- status-only progression
- review/intention row insertion
- source repair queue creation
- evidence intake queueing
- blocked/rejected state assignment with reasons

Later:
- CEX label writes
- DEX router evidence writes
- DEX mapping writes

Only with strict policy, audit, rollback, and shadow-mode proof.

Client automation:
- signals, trades, wallet orders, or opt-in driven actions only after separate client policy/opt-in design.

## Actions Still Blocked Until Separate Policy Exists

Blocked:
- real client trade
- wallet order
- swap execution
- copy trading
- client signal as investment advice
- opt-in creation or mutation
- client policy mutation

Condition to unblock:
- explicit client automation policy table/design
- explicit client opt-in model
- risk limits
- audit logs
- kill switch
- shadow-mode history

## Audit And Rollback Requirements

Every autonomous write must record:
- policy version
- input row IDs
- source URLs and digests
- dedupe keys
- parent-chain status
- decision
- reasons
- confidence/score
- mode
- timestamp
- before/after row snapshot where applicable
- rollback reference where applicable

No autonomous write can silently succeed if duplicate, drift, or parent mismatch exists.

## Core Product Direction

The target is not "more admin review".

The target is:
- autonomous discovery
- autonomous verification
- autonomous decisioning
- autonomous safe progression
- autonomous client operation only after policy/opt-in/risk layers exist

The current review-first pipeline should now be treated as the training wheels for the policy engine.

## Recommended Next Step

Build the policy engine in shadow mode first.

Next goal:
- create a read-only policy decision engine for token-market radar/candidate progression
- input: current radar leads and existing review rows
- output: accept/repair/reject decisions with reasons
- no DB writes
- no status updates
- no labels
- no mappings
- no trades
- no opt-ins
