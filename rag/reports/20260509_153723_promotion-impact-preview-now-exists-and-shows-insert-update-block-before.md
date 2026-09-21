# Local Advisor Report

Generated: 2026-05-09T15:37:23

## Question

Promotion impact preview now exists and shows insert/update/block before trusted label writes. The real promote endpoint still can mutate labels with dry_run=false. What is the safest next backend guardrail before any real promotion: require explicit confirm token, create DB backup, write audit/job record, or all three? Pick minimal concrete step with tests and no auto-promotion.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Safest Backend Guardrail for Promotion Endpoint

## Understanding the Problem

The promotion endpoint currently has:
- A **preview** mode showing insert/update/block before trusted label writes
- A **real promote** endpoint that can still mutate labels with `dry_run=false`

The question asks for the **minimal concrete step** to add before any real promotion that ensures safety without auto-promotion.

## Evaluating the Options

| Option | Safety Benefit | Engineering Cost | Reversibility |
|-------|---------------|------------------|---------------|
| Require explicit confirm token | High - prevents accidental/compromised calls | Medium - needs token management | High - tokens expire |
| Create DB backup | Medium - protects against corruption | High - storage, restore complexity | Medium - backup bloat |
| Write audit/job record | Low - only logging | Low - simple append | High - always reversible |
| All three | Maximum safety | High cumulative cost | Varies |

## Architectural Analysis

Based on the repository context:

1. **The promotion flow** involves trusted label writes that affect the label ledger (`backend/data/arkham/label_ledger.db`)

2. **Safety hierarchy** for label mutations:
   - Preview → Confirm → Execute (atomic)
   - Audit trail → Rollback capability → Data integrity

3. **Minimal guardrail principle**: The safest *minimal* step should:
   - Prevent unauthorized/accidental execution
   - Be reversible if compromised
   - Not significantly alter the architecture
   - Work within existing patterns

## The Answer

**Require explicit confirm token** is the minimal concrete step.

### Reasoning:

1. **Directly addresses the vulnerability**: The endpoint can still mutate with `dry_run=false`. A confirm token adds an authentication gate before mutation.

2. **Engineering pattern already exists**: The codebase shows token gates for private client access (`backend/routers/onchain.py` mentions "protected label/RPC mutation endpoints").

3. **Minimal architectural change**: 
   - Generate a short-lived token per promotion job
   - Require token in request header for the actual promote call
   - Token expires after N seconds or after single use

4. **More effective than DB backup**: A backup protects against corruption but doesn't prevent unauthorized promotion. The token prevents the attack vector.

5. **Audit logging should accompany, not replace**: Write an audit record *when* the token-confirmed promotion succeeds, not as a pre-condition.

### Implementation Sketch:

```python
# Generate token on promotion request (preview phase)
def generate_promotion_token(job_id: str) -> str:
    # Short-lived, single-use HMAC token
    pass

# Require token for actual promotion
@app.post("/promote", dependencies=[RequirePromotionToken])
async def promote_labels(job_id: str, token: str = Header(...)):
    if not verify_token(job_id, token):
        raise HTTPException(401, "Invalid promotion token")
    # Execute promotion with dry_run=false
```

### Verification:

1. Token expires after 5 minutes max
2. Each token single-use (invalidate on success/failure)
3. Log token usage in audit table with timestamp, job_id, result
4. Test: call promote without token →
