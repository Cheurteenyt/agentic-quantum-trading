# Local Advisor Report

Generated: 2026-05-09T18:13:17

## Question

Core Equity next patch: backfill legacy swap router/venue attribution from existing transactions table, bounded and audited. No broad RPC, no labels. What guardrails/tests?

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Core Equity Next Patch: Guardrails & Tests

Based on the repository context, here are the guardrails and tests for the backfill patch:

## Guardrails

| Guardrail | Implementation | Source |
|-----------|---------------|--------|
| **Bounded scope** | Limit to existing `transactions` table rows only; no new RPC calls | `backend/services/onchain_engine.py` |
| **No label creation** | Patch must not touch label promotion logic | `backend/services/label_ledger.py` |
| **Audit trail** | Log each attributed row with source hash | `backend/routers/onchain.py` |
| **No broad RPC** | Use only stored transaction metadata; no new explorer API calls | `backend/services/seed_ingestion.py` |

## Required Tests

```python
# 1. Row count guardrail
def test_backfill_bounded():
    """Verify patch only touches existing transaction rows."""
    # Expected: no new RPC calls, no label table mutations
    pass

# 2. Attribution correctness
def test_attribution_accuracy():
    """Verify legacy swap router/venue attribution matches existing data."""
    # Expected: 100% match on known venue IDs
    pass

# 3. Audit log completeness
def test_audit_trail():
    """Verify each attributed row has source hash logged."""
    # Expected: every row has `source_hash` in audit table
    pass

# 4. No label pollution
def test_no_label_changes():
    """Verify label ledger remains untouched."""
    # Expected: label_ledger.db row count unchanged
    pass
```

## Verification Steps

1. Run `py_compile` on modified backend files
2. Execute bounded-backfill test against `onchain.db`
3. Confirm `wallet_chain_state` row count unchanged
4. Verify audit log entries match attributed rows

---

**Missing context**: The exact schema of `transactions` table and existing venue attribution columns are not specified in the provided memory. Codex should inspect `backend/data/onchain/onchain.db` schema before implementing the patch.
