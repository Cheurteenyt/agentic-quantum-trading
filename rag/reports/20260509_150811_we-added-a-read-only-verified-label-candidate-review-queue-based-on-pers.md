# Local Advisor Report

Generated: 2026-05-09T15:08:11

## Question

We added a read-only verified label candidate review queue based on persisted evidence bundles. Current issue: acquisition plan and corroboration queue still use strict promotion grading from raw candidate evidence_json, so Polymarket PUSD is ready in verified-review-queue but still appears blocked/wait-for-new-source elsewhere. What is the safest next backend change to align reports without auto-promoting trusted labels?

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Verified Review Queue vs Acquisition Plan Misalignment

## Understanding the Problem

Based on the repository context, I can identify the following architecture:

**Current Data Flow:**
1. **Verified Review Queue**: Uses persisted evidence bundles → feeds into label ledger
2. **Acquisition Plan & Corroboration Queue**: Uses strict promotion grading from raw candidate `evidence_json`

**The Issue:**
- Polymarket PUSD appears ready in verified-review-queue (via evidence bundles)
- But still blocked in acquisition plan/corroboration queues elsewhere
- This creates inconsistent coverage reporting across the platform

## What's Missing from Context

The provided context shows **service names and file locations** but lacks:

1. **Queue Architecture Details** - How evidence flows between queues
2. **Promotion Grading Logic** - The exact rules in `evidence_json` vs evidence bundles
3. **Label Ledger Schema** - How Polymarket PUSD status is tracked
4. **Coverage Report Generation** - Where the "blocked/wait-for-new-source" status is computed

## Safest Next Backend Change

Without full architectural context, the safest change would be:

```
backend/routers/arkham.py
```

**Recommended Action:**
Add a diagnostic endpoint to expose the current state of Polymarket PUSD across both data paths:

```python
# Pseudo-code for diagnostic endpoint
@router.get("/coverage/polymarket-pusd-audit")
async def audit_polymarket_pusd():
    # Query verified-review-queue state
    # Query acquisition-plan state  
    # Compare evidence sources and timestamps
    # Return discrepancy report
```

**Why this is safe:**
- Read-only diagnostic (no data mutation)
- Helps identify the root cause before changing promotion logic
- Preserves existing behavior while adding visibility

## Verification Needed

To confirm this approach, Codex should:

1. Inspect `backend/services/label_ledger.py` for how evidence bundles are processed
2. Check `backend/routers/arkham.py` for existing coverage matrix logic
3. Review database schema for any `polymarket_pusd` status columns
4. Trace the exact promotion grading rules in the acquisition plan service

---

**Summary:** The safest immediate change is a diagnostic audit endpoint in `backend/routers/arkham.py` to expose the misalignment. This preserves stability while providing the visibility needed to understand why Polymarket PUSD has different status across the two data paths.
