# Local Advisor Report

Generated: 2026-05-09T17:55:38

## Question

Core Equity next priority after exact swap auto cooldown: should data-readiness expose exact swap ingestion plan and cooldown state? Need read-only UX/control-plane improvement, no writes.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Exact Swap Cooldown Data Readiness

## Current Architecture Review

Based on the repository context, here's what I found regarding exact swap cooldown state exposure:

### Existing Data Model Components

| Component | Location | Purpose |
|----------|----------|---------|
| `wallet_chain_state` | `backend/data/onchain/onchain.db` | Tracks wallet metadata, activity tier, risk flags, data quality score |
| `onchain_engine.py` | `backend/services/onchain_engine.py` | RPC orchestration, storage, wallet enrichment |
| `onchain_quality.py` | `backend/services/onchain_quality.py` | Address quality classification helpers |
| `onchain_chains.py` | `backend/services/onchain_chains.py` | RPC URLs, chain aliases, token tracking |

### What's Missing for Exact Swap Cooldown

The current architecture tracks **wallet-level** state but lacks **exact swap ingestion plan** and **cooldown state** at the swap/transaction level. Specifically:

1. **No swap ingestion plan tracking** - The system doesn't record planned exact swap ingestion batches, their status, or when they're scheduled
2. **No cooldown state per swap** - There's no mechanism to track when exact swaps are in cooldown and when they can be re-ingested
3. **No read-only control-plane** - The `onchain.py` router has admin endpoints but none expose swap cooldown state or ingestion plans

### Recommended Architecture Additions

```
┌─────────────────────────────────────────────────────────────┐
│  Exact Swap Cooldown Data Readiness Layer                    │
├─────────────────────────────────────────────────────────────┤
│  1. New DB Table: swap_ingestion_plan                        │
│     - swap_hash, planned_batch_id, status, cooldown_until    │
│                                                              │
│  2. New DB Table: swap_cooldown_state                        │
│     - swap_hash, cooldown_reason, expires_at, read_only_flag │
│                                                              │
│  3. New Router Endpoint: swap_cooldown.py                     │
│     - GET /swap-cooldown/plan (read-only)                     │
│     - GET /swap-cooldown/state/{swap_hash} (read-only)       │
│                                                              │
│  4. Service: swap_cooldown_manager.py                         │
│     - Tracks cooldown timers                                  │
│     - Exposes ingestion plan via read-only API                │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Priority

1. **Data schema** - Add `swap_ingestion_plan` and `swap_cooldown_state` tables to `onchain.db`
2. **Service layer** - Implement `swap_cooldown_manager.py` for state tracking
3. **Control-plane API** - Add
