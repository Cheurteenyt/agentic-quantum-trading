# Local Advisor Report

Generated: 2026-05-08T18:38:19

## Question

We now persist label_candidate_evidence bundles from Blockscout/Etherscan corroboration. Codex plans to add a historical evidence score endpoint that aggregates bundles by candidate, without promoting labels. Critique the plan and give concrete checks before implementation.

## Sources

- `backend/services/label_ledger.py`
- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Critique of Historical Evidence Score Endpoint Plan

## 1. Useful Facts (with source paths)

| Fact | Source |
|------|--------|
| Label candidates are stored in `label_candidates` table with `evidence_json`, `seen_count`, `source_key` columns | Source 1 |
| Candidates are read-only by default; promotion requires explicit admin action with `min_score >= 90` | Source 1, Source 2 |
| Current candidate count is ~519, with 25 in strict promotion review queue | Source 2 |
| Evidence bundles include `evidence`, `file`, and `tags` fields from Blockscout/Etherscan corroboration | Source 1 |
| Existing endpoints: `GET /api/onchain/labels/candidates/audit` and `GET /api/onchain/labels/candidates/quality-report` are read-only | Source 2, Source 3 |
| Admin endpoints require `CORE_ADMIN_TOKEN` and follow strict gating | Source 2, Source 3 |

---

## 2. Hypotheses for Codex to Verify

1. **Query complexity risk**: Aggregating bundles by candidate without filtering could produce O(n²) joins if evidence is denormalized per candidate.

2. **Historical scope ambiguity**: "Historical" could mean:
   - All-time aggregate per candidate
   - Time-bounded (e.g., last 30 days)
   - Per-chain historical tracking

3. **Score aggregation method**: The plan mentions "aggregates bundles" but doesn't specify:
   - Weighting scheme (evidence vs file vs tags)
   - Deduplication of duplicate sources
   - Decay over time

4. **API surface collision**: The endpoint name `historical-evidence-score` could conflict with existing `quality-report` or `audit` endpoints that already expose candidate metadata.

---

## 3. Concrete Checks Before Implementation

### A. Schema Verification

```bash
# Check current label_candidates schema
sqlite3 backend/data/arkham/label_ledger.db ".schema label_candidates"
```

Expected columns to verify:
- `id`, `chain`, `address`, `source_key` (primary/unique constraints)
- `evidence_json`, `seen_count`
- Any existing `score` or `timestamp` columns

### B. Data Volume Check

```bash
# Count candidates and evidence bundle size
sqlite3 backend/data/arkham/label_ledger.db "SELECT COUNT(*), AVG(length(evidence_json)) FROM label_candidates WHERE evidence_json IS NOT NULL;"
```

If average evidence JSON > 5KB, aggregation queries may need pagination or streaming.

### C. Existing Endpoint Audit

Check `backend/routers/onchain.py` and `backend/services/label_ledger.py` for:
- Any existing `/candidates/aggregate` or `/candidates/score` endpoints
- How `quality-report` computes its metrics (to avoid duplication)

### D. Admin Token Gate Verification

Verify that new endpoint follows existing pattern:
```python
# Expected pattern from Source 2
if not request.headers.get("X-Admin-Token") == os.getenv("CORE_ADMIN_TOKEN"):
    return {"ok": False, "error": "admin_required"}, 401
```

### E. Historical Data Growth Projection

```bash
# Check if evidence bundles grow over time
sqlite3 backend/data/arkham/label_ledger.db "SELECT source_key, MAX(seen_timestamp) as last_seen, COUNT(*) as bundle_count FROM label_candidates GROUP BY source_key ORDER BY bundle_count DESC LIMIT 10;"
```

---

## 4. Risks / False Positives / Non-Goals

| Risk | Mitigation |
|------|------------|
| **Query timeout** if aggregating 500+ candidates with large evidence bundles | Add `limit` param, paginate, or pre-aggregate nightly |
| **Score inflation** if duplicate sources counted multiple times | Deduplicate by `source_key` before aggregation |
| **Historical bloat** if old candidates never pruned | Add TTL or max-historical-depth param |
| **API surface creep** | Keep endpoint read-only; no mutation |
| **False positive**: Treating "historical" as "more trustworthy" | Add `historical_depth` param to control lookback window |

---

## 5. Tiny Experiments Codex May Choose to Run

### Experiment 1: Score Function Prototype

```python
def aggregate_evidence_score(candidates: list[dict], max_depth: int = 30) -> dict:
    """
    Aggregates evidence bundles by candidate without promoting labels.
    Returns historical score summary for audit endpoint.
    """
    # Group by candidate key
    grouped = _group_by_candidate(candidates, max_depth)
    
    # Compute weighted score per candidate
    scored = []
    for candidate_key, bundles in grouped.items():
        score = _compute_evidence_score(bundles)  # Weight: evidence=1.0, file=0.7, tags=0.3
        scored.append({
            "candidate": candidate_key,
            "evidence_count": len(bundles),
            "unique_sources": len(_unique_sources(bundles)),
            "score": round(score, 2),
            "max_depth": max_depth
        })
    
    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"ok": True, "count": len(scored), "rows": scored[:100]}
```

### Experiment 2: Backfill Test

Run aggregation on a small subset (e.g., 50 candidates) and measure:
- Query execution time
- Memory footprint
- Output size vs. expected

### Experiment 3: Historical Depth Comparison

Compare scores with `max_depth=7` vs `max_depth=30` to see if older evidence materially changes ranking.

---

## 6. Confidence and Missing Context

**Confidence**: 85% — The plan is consistent with existing architecture (read-only, admin-gated, audit-focused). The main unknowns are data volume and query performance.

**Missing Context**:
1. Current average size of `evidence_json` per candidate
2. Whether `seen_timestamp` or similar exists for time-bounded queries
3. Existing query patterns in `label_ledger.py` for reference
4. Whether `quality-report` already computes any aggregate scores

---

## Summary Recommendation

The plan is **LOW-RISK** and aligns with existing patterns. Before implementation:

1. Verify average evidence JSON size to estimate query complexity
2. Confirm `quality-report` doesn't already compute similar aggregates
3. Add `max_depth` param to control historical lookback
4. Keep endpoint read-only with admin token gate
5. Pre-aggregate nightly if evidence bundles grow large
