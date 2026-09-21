# Local Advisor Report

Generated: 2026-05-09T15:18:11

## Question

Potential issue: after merging persisted evidence bundles into strict promotion grading, candidates with weak evidence bundles may pass strict promotion because _strict_promotion_grade only sees evidence items and verified source markers, not the persisted evidence decision/score. Should explicit promotion require verified-review-ready when persisted bundles exist? Critique the safest rule.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Strict Promotion Grade vs Persisted Evidence Bundles

## Understanding the Architecture

From the repository context, I can identify the relevant components:

1. **Evidence Bundles**: Stored in `backend/data/arkham/scrapling/normalized/*.json` and processed through services like `label_ledger.py` and `label_expansion.py`

2. **Promotion Grading**: The `_strict_promotion_grade` function evaluates candidates based on:
   - Evidence items
   - Verified source markers
   - **Missing**: Persisted evidence decision/score

3. **Data Model**: The `wallet_chain_state` table (267 rows across multiple chains) tracks:
   - Address kind, contract flag, native USD value
   - Activity tier, risk flags, data quality score
   - Label source evidence, RPC source attribution

## The Issue Analysis

### Current Behavior
```
_strict_promotion_grade(candidate) → evaluates:
  • evidence_items (raw items)
  • verified_source_markers (source attribution)
  • ❌ NOT: persisted_evidence_decision/score
```

### The Gap
When evidence bundles are persisted, the system stores:
- A **decision** (whether evidence was sufficient for a label/promotion)
- A **score** (quality/weight of the evidence)

But `_strict_promotion_grade` ignores these persisted values and only examines the raw evidence items and source markers. This means:

1. **Weak bundles can pass**: A bundle with low confidence scores but many items could satisfy `_strict_promotion_grade`'s item-count thresholds

2. **Decision context is lost**: The persisted decision (e.g., "this bundle was borderline but accepted due to source diversity") is not considered

3. **Inconsistent strictness**: The same evidence might be rejected during bundle creation but accepted during promotion because the decision/score context is ignored

## Safest Rule Critique

### Proposed Rule
> "Explicit promotion should require `verified-review-ready` flag when persisted evidence bundles exist"

### Critique

**Strengths:**
- ✅ Simple gate: check a flag that was already computed during bundle processing
- ✅ Preserves existing evidence evaluation (doesn't re-score)
- ✅ Prevents weak bundles from bypassing review entirely

**Weaknesses:**
- ❌ **Binary limitation**: A bundle could be `verified-review-ready` but still have weak individual evidence items
- ❌ **No score consideration**: The actual evidence score is still ignored
- ❌ **Flag provenance unclear**: We don't know what criteria set `verified-review-ready`

### Better Rule (Safest)

```
IF persisted_evidence_bundle EXISTS for candidate:
    promotion_grade = persisted_decision_score + evidence_item_count_weight
    require: persisted_decision_score ≥ MIN_STRICT_SCORE
ELSE:
    promotion_grade = _strict_promotion_grade(candidate)
```

**Why this is safer:**
1. Uses the **already-computed decision score** that was intended to be used
2. Only applies strict promotion logic when no persisted decision exists
3. Maintains chain/source separation (decision was made at bundle time)
4. Minimal change to existing architecture

## Verification Steps for Codex

1. Find where `_strict_promotion_grade` is implemented
2. Check how `
