# Local Advisor Report

Generated: 2026-05-10T00:49:10

## Question

Core Equity priority: should unknown-router proof dossier counts be integrated into data-readiness and manipulation-readiness? Suggest read-only summary fields, blockers, and evidence lanes. No edits.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/model_routing_guide.md`
- `backend/services/label_ledger.py`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`

## Advisor Output

# Analysis: Unknown-Router Dossier Counts Integration

## Current Architecture Review

Based on the repository context, here's what exists for label evidence and promotion:

### Existing Evidence Model

**Evidence Storage:**
- `evidence_bundles` field stores proof for labels (Source 3)
- `label_candidate_evidence` table stores candidate evidence bundles (Source 1)
- Evidence scores are aggregated with source deduplication (Source 1)

**Promotion Blockers:**
- `promotion_blockers` field tracks what prevents high-confidence status (Source 3)
- Manual review blockers include `"signer_candidate_requires_manual_review"` and `"strict_protocol_requires_manual_review"` (Source 3)
- Scrapling-only candidates are blocked even with repeated observations (Source 1)

**Current Promotion Path:**
```
Candidate → Evidence Bundles → Blocker Check → Manual Review → High-Confidence Label
```

## Integration Recommendation

### 1. Read-Only Summary Fields

Add these computed fields to the label ledger query (read-only, no edits):

```python
# Proposed additions to label_ledger.py query output
"unknown_router_dossier_count": int,  # Total unique router observations
"unknown_router_evidence_score": float,  # Aggregated evidence strength (0-100)
"unknown_router_source_diversity": int,  # Number of distinct sources
"unknown_router_recency_score": float,  # How recent the observations are
"unknown_router_corroboration_ratio": float,  # Verified vs total observations
```

### 2. Blockers for Unknown-Router Proof

Add these to the `promotion_blockers` validation:

```python
# Proposed blocker checks
unknown_router_blockers = [
    "unknown_router_insufficient_dossiers",  # < 3 unique router observations
    "unknown_router_low_source_diversity",   # < 2 source types
    "unknown_router_stale_evidence",        # No recent observations (30+ days)
    "unknown_router_single_source",         # All evidence from one source
]
```

### 3. Evidence Lanes Architecture

**Lane 1: Raw Dossier Collection** (Read-Only)
- Collects unknown router observations from all sources
- Stores in `label_candidate_evidence` without promotion
- Uses existing `GET /api/onchain/labels/candidates/corroborate` endpoint

**Lane 2: Corroboration Queue** (Read-Only Summary)
- Aggregates dossiers by label and source
- Computes summary metrics for each lane
- No persistence beyond aggregation window

**Lane 3: Promotion Gate** (Read-Only Verification)
- Validates dossier counts against thresholds
- Checks source diversity and recency
- Outputs verification report to `data_jobs` audit (existing)

## Verification Steps for Codex

1. **Check existing evidence aggregation:**
   ```
   Inspect: backend/services/label_ledger.py line ~100-150
   Verify: evidence_bundles aggregation logic
   ```

2. **Verify dossier counting mechanism:**
   ```
   Check: How unique router observations are deduped
   Check: Whether source URLs are preserved for diversity calculation
   ```

3. **Confirm audit trail:**
