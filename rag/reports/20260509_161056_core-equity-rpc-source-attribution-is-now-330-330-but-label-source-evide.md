# Local Advisor Report

Generated: 2026-05-09T16:10:56

## Question

Core Equity: RPC source_attribution is now 330/330 but label source evidence is only 3/330. What is the safest next data/RPC action to increase public label-source evidence without blind ingestion or trusted-label risk? Short plan only.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: RPC Source Attribution vs Label Source Evidence

## Understanding the Metrics

Based on the repository context, I can identify these key metrics:

| Metric | Current Value | Meaning |
|--------|---------------|---------|
| RPC Source Attribution | 330/330 | All RPC calls successfully attributed to source chains |
| Label Source Evidence | 3/330 | Only 3 labels have documented source evidence out of 330 total |

## Root Cause Analysis

The gap exists because:

1. **RPC attribution** is handled by `wallet_chain_state` tracking in `onchain_engine.py` and `backend/services/onchain_chains.py` — this is working well (65/65 Uniswap, 60/60 Bitget, etc.)

2. **Label source evidence** is tracked in the `label_ledger.db` but lacks provenance documentation — the ledger stores labels but doesn't track *where* each label originated (Scrapling, Arkham cache, derived, seed ingestion, etc.)

3. The architecture separates:
   - **Data layer**: Raw label storage (`label_ledger.db`)
   - **Intelligence layer**: Label derivation and expansion (`label_ledger.py`, `label_expansion.py`)
   - **Coverage layer**: RPC attribution (`wallet_chain_state`)

The intelligence layer is not feeding provenance metadata back to the data layer.

## Safest Next Action Plan

### Phase 1: Add Source Provenance Column (Low Risk)

```sql
-- Add provenance tracking to label_ledger.db
ALTER TABLE labels ADD COLUMN source_provenance TEXT;
ALTER TABLE labels ADD COLUMN provenance_timestamp DATETIME;
ALTER TABLE labels ADD COLUMN provenance_source TEXT;
```

**Why this is safe:**
- No data ingestion changes
- No RPC behavior changes
- No label confidence changes
- Fully reversible

### Phase 2: Backfill Provenance from Existing Sources

Map existing labels to their sources:

| Source | How to Identify | Confidence |
|--------|-----------------|------------|
| Scrapling | Check `backend/data/arkham/scrapling/normalized/` for matching entity IDs | High |
| Arkham Cache | Match against `backend/data/arkham/cache.json` | High |
| Derived | Check `label_ledger.db` for `derived_label=1` flag | Medium |
| Seed Ingestion | Match transaction hashes in `onchain.db` | High |

### Phase 3: Add Provenance Capture to Label Expansion Service

Modify `backend/services/label_expansion.py` to record provenance when creating derived labels:

```python
# Pseudo-code for provenance capture
def record_provenance(label, source_type, source_id):
    provenance = {
        'source_type': source_type,  # 'scrapling', 'cache', 'derived', 'seed'
        'source_id': source_id,
        'timestamp': datetime.utcnow(),
        'verification_hash': hash(label + source_id)
    }
    # Store in new provenance table or as JSON in label record
```

### Phase 4: Add Source Attribution to Coverage Report

Update `backend/routers/arkham.py` to include provenance breakdown:

```python
# Add to existing coverage report
def generate_coverage_report():
    provenance_breakdown = query_provenance_distribution()
    report['label_source_evidence'] = provenance_breakdown
```

## Expected Outcome

| Metric | Before | After (Target) |
|--------|--------|----------------|
| Label Source Evidence | 3/330 | 300+/330 |
| Provenance Coverage | 0% | 100% |
| Source Diversity | Unknown | Tracked |

## Verification Steps

1. Run `backend/routers/arkham.py` coverage endpoint — verify provenance breakdown appears
2. Query `label_ledger.db` — verify all labels have `source_provenance` populated
3. Check `backend/services/label_expansion.py` — verify provenance is recorded on new derivations
4. Run Arkham coverage report —
