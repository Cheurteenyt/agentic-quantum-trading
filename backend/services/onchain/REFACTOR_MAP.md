# Onchain Refactor Map

Last updated: 2026-05-23

Purpose: guide the cleanup of `backend/services/onchain_engine.py` without
losing behavior, breaking imports, or repeating existing lanes.

## Current Situation

- `backend/services/onchain_engine.py` is approximately 99k lines and exposes
  hundreds of public functions.
- `backend/routers/onchain.py` imports most on-chain functions from
  `services.onchain_engine`.
- Multiple tests patch `services.onchain_engine._get_db`, so the facade must
  remain stable during migration.
- Several newer lanes are already correctly split into
  `backend/services/onchain/*.py`.
- Strategic decision after the first cleanup: do not keep extracting tiny
  helpers just to reduce the line count. `onchain_engine.py` is now treated as
  a frozen legacy facade. Future extraction should be tied to the product lane
  being actively touched.

## Non-Negotiable Compatibility Rules

- Keep `services.onchain_engine` as the compatibility facade.
- Do not bulk-update router imports until moved functions have tests.
- Do not move DB helpers without checking tests that patch `_get_db`.
- Do not mix refactor and product behavior changes.
- Do not rename public endpoint functions without compatibility aliases.
- Do not add provider calls, DB writes, labels, mappings, signals or trades as
  part of structure cleanup.

## Natural Module Boundaries Observed

### 1. Core / DB / RPC

Approximate current area: top of `onchain_engine.py`.

Owns:

- DB paths and `_get_db`
- JSON/coercion helpers
- RPC wrappers
- receipt/block helpers
- low-level token metadata helpers
- raw event parsers

Target:

- `backend/services/onchain/core/constants.py` (started)
- `backend/services/onchain/core/paths.py` (started)
- `backend/services/onchain/core/json.py` (started)
- `backend/services/onchain/core/addresses.py` (started)
- `backend/services/onchain/core/collections.py` (started)
- `backend/services/onchain/core/numbers.py` (started)
- `backend/services/onchain/core/db.py`
- `backend/services/onchain/rpc/evm.py`
- `backend/services/onchain/events/abi.py` (started)
- `backend/services/onchain/events/parsers.py` (started)

Move priority: high, but only after tests that patch `_get_db` are adjusted or
the facade delegates cleanly. Stable constants/default paths can move first,
while `services.onchain_engine` keeps patchable aliases.

### 2. CEX Labels / Source Quality

Approximate current area: label coverage, source quality, confidence upgrade,
independent evidence and final label write queues.

Owns:

- CEX label coverage audits
- CEX label acquisition plans
- independent source evidence
- confidence upgrades
- final label write queues

Target:

- `backend/services/onchain/labels/cex_coverage.py`
- `backend/services/onchain/labels/independent_evidence.py`
- `backend/services/onchain/labels/confidence_upgrade.py`
- `backend/services/onchain/labels/final_write.py`

Move priority: medium. Label write lanes are safety-sensitive, so move only
after read-only label planning lanes.

### 3. Behavioral / Manipulation Research

Current split already exists:

- `behavioral_evidence_bridge.py`
- `cex_listing_prediction.py`
- `manipulation_reliability.py`
- `transfer_context_plan.py`
- `raw_swap_evidence.py`
- `exact_swap_second_window.py`

Remaining monolith areas:

- adaptive accumulation scans
- wallet profiles
- cluster scan
- funder graph scan
- adaptive manipulation case file

Target:

- `backend/services/onchain/manipulation/accumulation.py`
- `backend/services/onchain/manipulation/funder_graph.py`
- `backend/services/onchain/manipulation/casefiles.py`

Move priority: high. These are central to the next anomaly taxonomy suite.

### 4. DEX Route / PairCreated / Event Reader

Approximate current areas:

- unknown router source proof
- DEX router official evidence
- DEX mapping review
- PairCreated SQD/archive/indexer lookups
- local event reader run/proof packages

Target:

- `backend/services/onchain/dex/router_sources.py`
- `backend/services/onchain/dex/paircreated.py`
- `backend/services/onchain/dex/mapping_review.py`
- `backend/services/onchain/dex/event_reader.py`

Move priority: high after behavioral extraction, because this area is required
for future reliable data collection.

### 5. Token Market Handoff Queues

Approximate current area: token market candidate discovery, evidence queues,
controlled promotion, downstream business handoffs and final target queues.

Target:

- `backend/services/onchain/token_market/discovery.py`
- `backend/services/onchain/token_market/review_queues.py`
- `backend/services/onchain/token_market/handoff.py`

Move priority: medium-low. It is large, but not the immediate blocker for the
Aster/manipulation suite.

### 6. Aster Suite

Current monolith area:

- `_aster_dex_reference_addresses`
- `_aster_collection_token_addresses`
- `get_aster_dex_fund_flow_radar`
- `run_aster_dex_fund_flow_collection`
- `run_aster_dex_paginated_fund_flow_collection`
- `get_aster_dex_flow_case_file`
- `get_aster_cex_bridge_context`
- `run_aster_source_wallet_token_flow_collection`

Target:

- `backend/services/onchain/aster/reference.py`
- `backend/services/onchain/aster/fund_flow.py`
- `backend/services/onchain/aster/casefiles.py`
- `backend/services/onchain/aster/cex_bridge.py`

Move priority: product-triggered only. The next suite will connect to Aster
data/API, but existing Aster functions should move only when the active task
needs that exact family. New Aster lanes should start clean in
`backend/services/onchain/aster/`.

Clean-start rule:

- New Aster work starts in `backend/services/onchain/aster/`, not in the
  facade.
- Use `rag/memory/aster_python_structure_rules.md` for module ownership.
- `services.onchain_engine` may keep compatibility wrappers only when an
  existing route/test still depends on the legacy import path.

## Recommended Batch Order

### Batch 0 - Done by this map

- Add package documentation and refactor boundaries.
- Do not move code yet.

### Batch 0.5 - Core primitive extraction

Status: started.

Moved:

- stable EVM chain/event constants to `onchain/core/constants.py`
- bounded public indexer endpoint maps to `onchain/core/constants.py`
- default DB/cache/backup paths to `onchain/core/paths.py`
- JSON/coercion/env helpers to `onchain/core/json.py`
- EVM address validation to `onchain/core/addresses.py`
- deterministic de-duplication to `onchain/core/collections.py`
- numeric helpers to `onchain/core/numbers.py`
- ERC20 ABI result decoders to `onchain/events/abi.py`
- pure EVM parser helpers to `onchain/events/parsers.py`
- pure DEX local event-reader helpers to `onchain/dex/event_reader.py`
- bounded PairCreated/Blockscout/SQD lookup helpers to `onchain/dex/paircreated.py`
- DEX mapping review contract, queue schema-plan, DDL-only create and
  dry-run-first insert builders to `onchain/dex/mapping_review.py`

Compatibility:

- `services.onchain_engine` still exposes the same public names for tests/routes.
- extracted modules should not import the facade only for constants, default
  paths, JSON/coercion/env helpers, address helpers, collection helpers, pure
  event parsing helpers, DEX local event-reader helper primitives, bounded
  PairCreated/indexer helper primitives, or DEX mapping review
  contract/schema/create/insert builders.

### Batch 1 - Aster clean-start / touched-family extraction

Goal: start new Aster product/data work under `onchain/aster/*`. Move
Aster-specific functions out of `onchain_engine.py` only when that function
family is touched by the active task, while keeping compatibility imports.

Why first:

- It is a self-contained future suite.
- It prevents new Aster code from being added to the 99k-line facade.

Validation:

- `py_compile` on moved modules and facade.
- targeted tests importing `services.onchain_engine`.
- route import smoke if routes expose Aster endpoints.

### Batch 2 - Behavioral legacy extraction

Goal: move adaptive accumulation/wallet profile/funder graph/casefile functions
to `onchain/manipulation/*`.

Why:

- This is the engine we need for the anomaly taxonomy.
- It reduces the part of the monolith that Qwen identified as the "detective".

Validation:

- tests around funder graph and onchain entity chain gaps.
- import compatibility from `services.onchain_engine`.

### Batch 3 - DEX PairCreated/Event Reader extraction

Goal: move PairCreated, DEX mapping review and event reader lanes to
`onchain/dex/*`.

Why:

- These lanes are evidence/data infrastructure, not generic engine code.

Status: started. Pure event-reader helper primitives now live in
`onchain/dex/event_reader.py`; bounded PairCreated/Blockscout/SQD helper
primitives now live in `onchain/dex/paircreated.py`; mapping-review
contract/schema/create/insert builders now live in
`onchain/dex/mapping_review.py`.
`services.onchain_engine` keeps compatibility aliases for existing router/test
callers and injects patchable DB helpers.

Validation:

- admin route tests for DEX evidence/mapping/event-reader endpoints.
- dry-run/idempotence tests for DDL/write lanes.

### Batch 4 - Label/CEX source reference extraction

Goal: move label source quality and CEX label evidence lanes to
`onchain/labels/*`.

Why:

- This is the missing reference layer for CEX-style hypotheses.

Validation:

- label promotion tests.
- CEX market evidence review queue tests.

## Naming Rules Going Forward

- Preview/read-only functions should end with `_preview`, `_plan`, `_audit`, or
  `_review_queue` when applicable.
- Confirmed writes should start with `create_`, `insert_`, `apply_`, `persist_`,
  or `run_` only when the behavior is explicit.
- Aster-specific public functions should start with `get_aster_` or `run_aster_`
  and live under `onchain/aster`.
- Do not create new generic names like `helper.py`, `utils.py` or `new_engine.py`.
