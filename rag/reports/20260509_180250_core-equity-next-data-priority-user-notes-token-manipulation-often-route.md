# Local Advisor Report

Generated: 2026-05-09T18:02:50

## Question

Core Equity next data priority: user notes token manipulation often routes through decentralized platforms/DEX venues like Aster/Binance ecosystem, but do not hardcode RAVE. We already ingest swaps with pools/token directions. Should we add venue/router attribution to swaps/readiness? Suggest safe schema/guardrails/tests.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Next Data Priority

## Summary

Based on the repository context, Core Equity currently has a robust label ingestion pipeline but lacks **venue/router attribution** for swaps. The question is whether to add this capability and how to do it safely.

---

## Current Architecture Analysis

### What Exists Now

| Component | Location | Purpose |
|----------|----------|---------|
| Swap ingestion | `backend/services/onchain_engine.py` | Ingests swaps with pool/token directions |
| Label ledger | `backend/services/label_ledger.py` | Builds deduped label ledger from Scrapling |
| Label expansion | `backend/services/label_expansion.py` | Derives low/medium confidence labels |
| Seed ingestion | `backend/services/seed_ingestion.py` | Ingests transactions around seed labels |

### Data Model (from `wallet_chain_state`)

The current `wallet_chain_state` table tracks:
- Address kind, contract flag, native USD value
- Activity tier, risk flags, data quality score
- Label source evidence, RPC source attribution

**Missing**: Venue/router attribution for swaps.

---

## Recommendation

### Yes — Add Venue/Router Attribution

**Rationale:**
1. **Alpha value**: DEX venues (Aster, Binance ecosystem) often route manipulation through their liquidity pools
2. **Coverage gap**: Current swap data lacks the "how" (venue) not just the "what" (token pair)
3. **Scalability**: Don't hardcode RAVE; build a generic venue attribution layer

---

## Safe Implementation Plan

### 1. Schema Extension

```sql
-- Add to wallet_chain_state or create swap_venue attribution table
ALTER TABLE wallet_chain_state 
ADD COLUMN venue_attribution TEXT,
ADD COLUMN router_signature TEXT,
ADD COLUMN venue_confidence_score REAL DEFAULT 0.5;
```

**Alternative (preferred for safety):** Create a dedicated swap attribution table to avoid schema coupling.

### 2. Guardrails

| Guardrail | Implementation |
|-----------|----------------|
| **Source attribution** | Always log venue detection source (e.g., `DEX_ROUTER_SIGNATURE`, `LIQUIDITY_POOL_METADATA`) |
| **Confidence thresholds** | Only promote venue attribution if confidence ≥ 0.7 |
| **Batch processing** | Process venue attribution in batches of 1000 to avoid memory spikes |
| **Reversible design** | Store venue data as optional metadata; never delete existing swap records |

### 3. Detection Strategy

```python
# Pseudocode for venue attribution
def detect_venue_swap(tx_hash, pool_address):
    # 1. Check known DEX router signatures
    if pool_address in KNOWN_DEX_ROUTERS:
        return {"venue": KNOWN_DEX_ROUTERS[pool_address], "confidence": 0.9}
    
    # 2. Analyze swap pattern against venue heuristics
    swap_pattern = analyze_swap_pattern(tx_hash)
    if swap_pattern.matches_aster_routing():
        return {"venue": "ASTER", "confidence": 0.75}
    
    # 3. Fallback to pool metadata if available
    pool_meta = fetch_pool_metadata(pool_address)
    if pool_meta.
