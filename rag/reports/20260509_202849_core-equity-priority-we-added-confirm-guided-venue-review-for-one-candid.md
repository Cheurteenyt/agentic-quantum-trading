# Local Advisor Report

Generated: 2026-05-09T20:28:49

## Question

Core Equity priority: we added confirm_guided_venue_review for one candidate. Next, should we add batch guided venue review actions dry-run by default? Need safe automation for non-expert admin, no token exposure, no auto client execution, official-source gates only. Suggest fields/guardrails/tests.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Guided Venue Review Automation

## What's Missing from Context

The repository context provided does **not** contain specific information about:

1. **The existing `confirm_guided_venue_review` implementation** - I cannot see its current code, data flow, or how it's triggered
2. **The candidate entity** - No details about which wallet/address received this feature
3. **The "guided venue review" workflow** - The business logic, UI flow, and data requirements are not documented
4. **Current admin endpoints** - The existing API surface for venue review actions is not shown
5. **Database schema** - No tables, columns, or relationships related to venue reviews are visible
6. **Token handling patterns** - How admin tokens are currently stored, validated, and scoped

## What I Need to Provide

Based on the available context, I can provide **architectural guidance** aligned with Core Equity's patterns, but I cannot give specific implementation details without seeing the relevant code.

---

## Recommended Fields & Guardrails

### Database Schema Additions

```sql
-- Venue review action log (append-only audit trail)
CREATE TABLE venue_review_actions (
    id INTEGER PRIMARY KEY,
    entity_address TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('approve', 'reject', 'flag', 'review')),
    reviewer_id TEXT NOT NULL,  -- admin identifier
    review_token_hash TEXT NOT NULL,  -- hashed token for verification
    target_venue TEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP,
    UNIQUE(entity_address, action_type, reviewed_at)
);

-- Review queue with priority
CREATE TABLE venue_review_queue (
    id INTEGER PRIMARY KEY,
    entity_address TEXT NOT NULL,
    venue TEXT NOT NULL,
    priority INTEGER DEFAULT 1,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'escalated')),
    expires_at TIMESTAMP,
    assigned_to TEXT,
    source_verified INTEGER DEFAULT 1
