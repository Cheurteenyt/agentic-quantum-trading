# DEX Local Event Reader Plan

Last updated: 2026-05-21.

This is a read-only product/data architecture plan. It creates no endpoint, no table, no DB write, no mapping, no signal, and no trade.

## Simple Meaning

Core Equity has proven one old PancakeSwap V2 pool with SQD PairCreated evidence, but the data path is still too fragile.

The next stronger product move is not another manual review box. The next stronger move is to build our own local event reader pattern:
- read official factory events
- read pool events
- read ERC20 transfers
- checkpoint every range
- retry safely
- store proof packages later only after explicit schema/DDL/insert goals

Plain meaning: we need a local data engine that stops missing important DEX events.

## Why This Matters

Current state:
- `paircreated_evidence_id=1` exists and is accepted for future mapping review.
- `dex_mapping_review_id=1` exists as a pending review fiche.
- This is still not a DEX mapping.
- The 3 other old pools remain research-only.
- Free public RPCs are weak for old BSC logs.
- SQD found 1 historical PairCreated proof, proving that indexer-style event reading is useful.

The product needs more than one proof:
- many pools
- many swaps
- many transfer paths
- repeatable route behavior
- liquidity/slippage context
- backtestable windows

## Design Goal

Create a future Core Equity DEX local event reader that can collect and verify:
- `PairCreated`
- `Swap`
- `Sync`
- `Mint`
- `Burn`
- ERC20 `Transfer`
- block, transaction and receipt context
- route/factory/pair proof packages

The event reader should be append-only, checkpointed, retryable and bounded.

## Inspirations To Adapt

These are design inspirations, not dependencies to blindly copy:
- `web3-ethereum-defi` event reader pattern: historical event reads, chunking, retries, restart checkpoints.
- Uniswap V2 subgraph model: `Factory`, `Pair`, `Token`, `Transaction`, `Swap`, `Mint`, `Burn`.
- Substreams/Subsquid style: stream events into a structured sink with deterministic cursors.

Core Equity should keep its own safety rules and proof gates.

## Future Components

### Event Reader

Responsibilities:
- choose a chain and official factory
- read logs in bounded block ranges
- parse event payloads
- compute deterministic digests
- emit read-only previews first
- later write only to raw event tables after explicit DDL/insert goals

It must not decide mappings, signals, or trades.

### Checkpoint Manager

Responsibilities:
- track `chain`, `source`, `factory`, `from_block`, `to_block`, `last_success_block`
- record failed ranges and provider errors
- prevent unbounded replays
- make repeated runs idempotent

### Proof Builder

Responsibilities:
- bind factory address, pair address, token0, token1, tx hash, log index, block number and payload digest
- distinguish current-state proof from historical event proof
- reject symbol-only, explorer-tag-only and current-state-only proof

### Data Quality Scorer

Responsibilities:
- mark proof quality as `raw_observed`, `candidate_correlated`, `source_backed`, or `blocked`
- explain missing fields
- never unlock mapping/trading alone

## Future Tables To Consider

Do not create these in this plan.

Potential raw/event tables:
- `dex_event_reader_checkpoints`
- `dex_raw_paircreated_events`
- `dex_raw_swap_events`
- `dex_raw_sync_events`
- `dex_raw_liquidity_events`
- `erc20_transfer_events`
- `dex_event_reader_runs`
- `dex_event_proof_packages`

Potential review tables:
- `dex_paircreated_evidence` already exists.
- `dex_mapping_review_queue` already exists.
- future raw events should flow into evidence/review only through separate confirmed goals.

## Event Schema Preview

PairCreated minimum fields:
- `chain`
- `factory_address`
- `pair_address`
- `token0`
- `token1`
- `tx_hash`
- `log_index`
- `block_number`
- `block_timestamp`
- `event_topic`
- `raw_log_json`
- `payload_digest`
- `source_name`
- `source_policy`

Swap minimum fields:
- `chain`
- `pair_address`
- `sender`
- `recipient`
- `amount0_in`
- `amount1_in`
- `amount0_out`
- `amount1_out`
- `tx_hash`
- `log_index`
- `block_number`
- `raw_log_json`
- `payload_digest`

Transfer minimum fields:
- `chain`
- `token_address`
- `from_address`
- `to_address`
- `value_raw`
- `tx_hash`
- `log_index`
- `block_number`
- `raw_log_json`
- `payload_digest`

## Source Strategy

Preferred order:
1. local DB first
2. configured RPC for recent/future bounded windows
3. SQD/Subsquid-style public historical lookup when available
4. archive/indexer provider only after explicit decision
5. manual source-backed package only for proof repair

Do not loop on already-failed old public BSC RPC paths unless a new source or smaller verified range is available.

## How This Helps Manipulation Detection

A stronger event reader gives Core Equity:
- more exact swaps
- more transfer context around pools
- better pool creation history
- repeatability windows
- token movement before and after swaps
- wallet/funding paths around candidate events
- enough structure for shadow scoring and backtests

This moves us toward the final product because manipulation detection needs repeated, explainable behavior, not one-off labels.

## Compatibility With Current Lane

Current lane:
- `paircreated_evidence_id=1`
- `dex_mapping_review_id=1`
- status: pending mapping review

The local event reader should not bypass that lane.

It should feed future evidence packages, and those packages must still pass:
- dedupe gate
- digest gate
- factory/pair gate
- source gate
- route safety gate
- review/policy gate

## Still Disabled

Always disabled from this plan:
- DEX mapping creation
- DEX router evidence writes
- CEX labels
- client signals
- trades/swaps/orders
- wallet actions
- client opt-ins
- unrestricted scraping/providers
- autonomous agents modifying Core Equity without policy

## Recommended Next Micro-Step

Next executable step should be read-only:

`DEX local event reader proof-of-shape plan read-only`

It should inspect existing local tables and propose the smallest event reader skeleton shape:
- chains/factories to start with
- block range policy
- event topics
- checkpoint fields
- raw output preview
- no DB write
- no new endpoint write behavior

Only after that should Core Equity consider a confirmed DDL-only table for checkpoints/raw events.
