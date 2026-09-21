# Local Advisor Report

Generated: 2026-05-10T19:57:25

## Question

Critique en lecture seule ce prochain incrément: ajouter dans readiness_contract un gap_closure_plan ordonné qui regroupe automation_data_gaps par étape admin/read-only/dry-run, sans exécution client. Quels champs et garde-fous manquent ? Réponse courte.

## Sources

- `backend/services/onchain_engine.py`
- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Readiness Contract Critique

## Analysis

Based on the retrieved context from `backend/services/onchain_engine.py`, here is the critique:

---

## 1. Useful Facts (with source paths)

**Current `readiness_contract` structure:**
```python
readiness_contract = {
    "version": "manipulation-readiness-v1",
    "requirements": readiness_requirements,
    "failed_requirements": failed_requirements,
    "failed_count": len(failed_requirements),
    "passed_count": len(readiness_requirements) - len(failed_requirements),
    "total_count": len(readiness_requirements),
    "execution_enabled": False,
    "client_copy_trading_allowed": False,
    ...
}
```

**Existing action() signature:**
```python
def action(
    action_id: str,
    priority: int,
    title_fr: str,
    reason: str,
    method: str,
    endpoint: str,
    admin_required: bool,
    confirm_required: str | None = None,
    dry_run_default: bool | None = None,
    env_required: str | None = None,
) -> dict[str, Any]:
```

**Existing gap-related fields observed:**
- `automation_data_gaps` — tracked per requirement row
- `automation_scope` — currently `"analysis_only_until_all_requirements_pass"`
- Source policy explicitly states `"no RPC calls, labels, swaps or wallet rows are changed"`

---

## 2. Missing Fields & Guardrails

### Fields Missing

| Field | Why Needed |
|-------|------------|
| `gap_closure_plan: list[dict]` | Ordered plan grouping gaps by admin/read-only/dry-run stage |
| `plan_version: str` | Track plan evolution; enables rollback comparison |
| `plan_generated_at: datetime` | Audit trail for plan freshness |
| `gap_stage: Literal["admin", "read-only", "dry-run"]` | Explicit stage tagging per gap item |
| `gap_priority: int` | Order execution within stage |
| `gap_dependency: str | None` | Express ordering between gap items |
| `expected_output: str` | Contract for what each stage should produce |
| `verification_hash: str` | Cryptographic fingerprint of plan for integrity |

### Guardrails Missing

| Guardrail | Why Needed |
|-----------|------------|
| `max_gap_items_per_stage: int` | Prevents unbounded plan growth |
| `stage_ordering_constraint: bool` | Enforces admin → read-only → dry-run sequence |
| `gap_id_uniqueness: bool` | Prevents duplicate gap entries |
| `plan_validity_window: timedelta` | Auto-expire stale plans |
| `gap_replay_safe: bool` | Ensure re-running gaps is idempotent |
| `admin_override_requires_confirmation: bool` | Prevents silent plan changes |

---

## 3. Concrete Next Checks

1. **Verify `automation_data_gaps` schema** — Check if gaps are already tagged with stage metadata or if they need enrichment.

2. **Confirm `action()` can return gap-plan items** — The current signature doesn't include `gap_stage` or `gap_dependency` fields; may need extension.

3. **Check for existing plan-versioning** — Search for `plan_version` usage in `onchain_engine.py` and related services.

4. **Audit gap ordering logic** — Verify if gaps are currently sorted by priority or if explicit dependency tracking exists.

5. **Review admin/read-only boundaries** — Confirm what operations are considered "read-only" vs "admin" in the current policy.

---

## 4. Risks / False Positives / Non-Goals

| Category | Details |
|----------|---------|
| **Risk** | Adding `gap_closure_plan` without versioning may cause plan drift over time |
| **False Positive** | Existing `dry_run_default` may partially address ordering needs |
| **Non-Goal** | This critique does not address *executing* the plan — only its structure |

---

## 5. Tiny Experiments Codex May Choose

```python
# 1. Inspect current gap structure
gaps = [g for r in readiness_requirements if r.get("automation_data_gaps")]
print(gaps[:3])

# 2. Check action() return shape for gap fields
action = action(
    "test_gap_plan",
    1,
    "Test gap plan",
    "Test reason",
    "GET",
    "/test",
    False,
)
print(action.keys())

# 3. Verify plan ordering constraint exists
# Search for: stage_ordering, gap_dependency, plan_version
```

---

## 6. Confidence & Missing Context

**Confidence:** 85% — The `action()` signature and `readiness_contract` structure are clearly visible; gap-plan specifics require deeper inspection.

**Missing Context Needed:**
- Full `automation_data_gaps` schema definition
- Existing stage-tagging conventions (if any)
- Whether `gap_closure_plan` is a new concept or an extension of existing plan structures
