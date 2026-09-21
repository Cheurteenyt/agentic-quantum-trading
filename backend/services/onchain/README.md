# Onchain Services

This package is the target home for Core Equity on-chain intelligence.

`backend/services/onchain_engine.py` is still the public compatibility facade used
by routers and many tests. Do not delete it or bulk-rename imports. Treat it as
a frozen legacy facade for new product work.

## Current Rule

New Core Equity on-chain code should live in this package, not in
`backend/services/onchain_engine.py`. For Aster specifically, follow
`rag/memory/aster_python_structure_rules.md` and start under
`backend/services/onchain/aster/`.

Existing code should be moved here only in small batches with:

- a compatibility import kept in `services.onchain_engine`
- targeted tests for the moved public functions
- no endpoint behavior change
- no DB write behavior change
- no provider/API side effect change

## Current Submodules

- `behavioral_evidence_bridge.py`: behavioral anomaly scoring, intent checks,
  pump backtest preview, stealth/quiet-pool probes and honeypot correlation.
- `cex_listing_prediction.py`: CEX listing hypothesis, seed datasets, native
  candidate discovery, B/LAB feature repair diagnostics and external scam
  negative intake.
- `manipulation_reliability.py`: UFLOKI/source-backed reliability, outcome
  repair, control windows, shadow replay and policy thresholds.
- `transfer_context_plan.py`: Transfer context evidence schema, lookup, insert,
  review and reliability bridge.
- `raw_swap_evidence.py`: raw Swap evidence persistence.
- `exact_swap_second_window.py`: second-window raw Swap repeatability.
- `manipulation_readiness.py`: readiness overview for manipulation detection.
- `manipulation_data_usability.py`: data usability audit.
- `manipulation_verdicts.py`: shared verdict helpers.
- `core/constants.py`: stable EVM chain and event topic constants used by the
  facade and extracted modules, plus bounded public indexer endpoint maps.
- `core/paths.py`: default on-chain filesystem paths used by small services
  without importing the large facade.
- `core/json.py`: JSON parsing, integer coercion and environment flag helpers.
- `core/addresses.py`: EVM address validation.
- `core/collections.py`: small deterministic collection helpers.
- `core/numbers.py`: median, float coercion and decimal amount formatting.
- `dex/event_reader.py`: pure local DEX event-reader helpers for log previews,
  topic-address decoding, uint word decoding and raw-event candidate payloads.
- `dex/mapping_review.py`: DEX mapping review contract, queue schema-plan,
  DDL-only creation and dry-run-first insert builders. The facade injects DB
  helpers so tests remain patchable.
- `dex/paircreated.py`: bounded no-persistence PairCreated/Blockscout/SQD
  lookup helpers and PairCreated log decoding.
- `aster/scrapling_label_enrichment_batch.py`: read-only
  `local_snapshots_only` Scrapling normalized snapshot enrichment preview for
  behavioral candidate addresses.
- `aster/dexscreener_enrichment_layer.py`: read-only DexScreener single-source
  market enrichment preview and composite score for local behavioral
  candidates.
- `events/abi.py`: small ABI result decoders for ERC20 metadata calls.
- `events/parsers.py`: pure EVM log/result parsers for Swap, ERC20 Transfer,
  uint words, nullable hex ints and call-result addresses.

## Target Domains

These domains are the intended future structure. They should be created and
filled gradually, not by a single bulk move.

- `core`: DB paths, event constants, SQLite helpers, JSON coercion, caching and
  shared guards.
- `rpc`: EVM/SOL RPC wrappers, receipts, balances, block utilities.
- `events`: Swap/Transfer/Sync/PairCreated parsers and raw event normalization.
- `labels`: CEX labels, source quality, independent evidence and label writes.
- `dex`: DEX route/source proof, PairCreated proof, router mapping and local
  event reader.
- `token_market`: token market candidate discovery, review queues and handoff
  contracts.
- `manipulation`: source-backed reliability, behavioral scoring, taxonomy and
  shadow/backtest lanes.
- `aster`: future Aster data/API integration and Aster-specific manipulation
  context. New Aster lanes must start here; the legacy facade may expose thin
  wrappers only for existing route/test compatibility.

## Migration Discipline

Preferred pattern:

1. Extract pure helpers first.
2. Extract read-only lanes next.
3. Extract DDL/write lanes only after tests cover dry-run, confirm and
   idempotence.
4. Keep `services.onchain_engine` exporting the same public names until routers
   and tests have moved.
5. Update `backend/services/SERVICE_CATALOG.md` and RAG after each batch.

Do not continue line-count-only micro-extractions from `onchain_engine.py`.
Extract a family only when it is part of the current product/data task.

## Extracted Core Primitives

Do not import `services.onchain_engine` only to read stable constants or default
paths. Use:

- `services.onchain.core.constants` for `SUPPORTED_EVM_CHAINS`, event topics and
  small EVM constants.
- `services.onchain.core.paths` for default on-chain DB/cache/backup paths.
- `services.onchain.core.json` for JSON/coercion/env helpers.
- `services.onchain.core.addresses` and `services.onchain.core.collections` for
  small pure helpers.
- `services.onchain.core.numbers` for small numeric helpers.
- `services.onchain.events.abi` for pure ABI result decoders.
- `services.onchain.events.parsers` for pure EVM log/result parsing.

`services.onchain_engine` still re-exports these names as mutable compatibility
aliases because several legacy tests patch the facade directly.
