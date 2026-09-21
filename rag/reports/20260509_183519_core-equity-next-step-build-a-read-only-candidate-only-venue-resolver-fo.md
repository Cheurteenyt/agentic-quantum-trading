# Local Advisor Report

Generated: 2026-05-09T18:35:19

## Question

Core Equity next step: build a read-only/candidate-only venue resolver for unknown DEX routers. Current data: 25 unknown swaps, 20 unknown routers, 17 pools. Need guardrails before adding source-backed mappings. Suggest minimal implementation/test risks.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Core Equity: Read-Only Venue Resolver Implementation Plan

## Analysis of Request

The question asks for a **minimal implementation and test risk assessment** for building a read-only venue resolver for unknown DEX routers. This is a data architecture task that should be evaluated against existing Core Equity patterns.

## Key Context from Repository

1. **Current Data Baseline**: 25 unknown swaps, 20 unknown routers, 17 pools — this is a small, bounded dataset suitable for a minimal implementation.

2. **Existing Architecture Patterns**:
   - `backend/services/onchain_engine.py` — handles local RPC/on-chain orchestration
   - `backend/services/onchain_chains.py` — manages RPC URLs, chain aliases, token tracking
   - `backend/services/onchain_entities.py` — canonical entity aliases with high-confidence merging
   - `wallet_chain_state` table — tracks address kind, contract flag, activity tier, risk flags, data quality score

3. **Guardrails Already Established**:
   - Label promotion requires external confirmation
   - Admin token gates for mutation endpoints
   - Quality classification helpers in `onchain_quality.py`

## Recommended Minimal Implementation

### Architecture Approach

```
venue_resolver/
├── resolver.py          # Main resolver service
├── venue_cache.db       # SQLite cache for router→pool mappings
└── rules.py             # Guardrail rules (no external calls)
```

### Implementation Steps

**Step 1: Data Model (Minimal)**
- Store `router_id → pool_ids` mappings with source attribution
- Add `confidence_score` column (0.0-1.0) for candidate mappings
- Store `source_evidence` as text (transaction hash, pool address, or label source)

**Step 2: Resolver Logic**
- Read-only lookup: `get_router_venues(router_id)` returns pool list with metadata
- No external API calls; all data cached locally
- Use existing `onchain_chains.py` RPC patterns for consistency

**Step 3: Guardrails**
- Confidence threshold gate: only promote mappings with score ≥ 0.75
- Source attribution required: every mapping must have traceable evidence
- Batch validation: run against existing 17 pools to verify consistency

**Step 4: Testing**
- Unit tests: mock resolver with synthetic router→pool data
- Integration test: query against existing `wallet_chain_state` rows
- Regression test: ensure no existing label queries are affected

## Test Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Query performance on large cache | Low | Cache TTL; index on `router_id` |
| Source attribution ambiguity | Medium | Require explicit source field; log decisions |
| Conflicts with existing label system | Low | Keep resolver read-only; separate namespace |
| Data corruption of cache | Low | SQLite WAL mode; periodic integrity check |

## Verification Checklist

Before implementation, verify:
- [ ] Existing `wallet_chain_state` schema supports additional metadata columns
- [ ] Cache storage location doesn't conflict with `onchain.db`
- [ ] Resolver service doesn't require `CORE_ADMIN_TOKEN` (read-only by design)
- [ ] Source attribution format matches existing label ledger conventions

## Next Action

Implement the
