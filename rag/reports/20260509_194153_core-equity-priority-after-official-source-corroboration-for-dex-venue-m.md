# Local Advisor Report

Generated: 2026-05-09T19:41:53

## Question

Core Equity priority: after official source corroboration for DEX venue mapping drafts, add a read-only admin review package/suggested payload. It must not write mappings, must keep manual review, and should help source-backed venue mapping confirmation. What fields and guardrails?

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Read-Only Admin Review Package Design

## Architectural Decisions

Based on the repository context, Core Equity already has a mature backend with `backend/routers/onchain.py` handling admin endpoints and `backend/services/label_ledger.py` managing label data. The architecture separates data ingestion from review, which aligns with the requirement to preserve manual review.

## Proposed Schema

### Review Payload Fields

```
{
  "review_id": "uuid",
  "source_name": "string",           // e.g., "Arkham", "Scrapling", "Explorer API"
  "source_evidence": "string",       // URL, snapshot hash, or excerpt
  "venue_name": "string",            // DEX/CEX name being validated
  "venue_mapping_draft": "object",   // Existing draft from source corroboration
  "suggested_status": "string",      // "pending", "approved", "rejected"
  "confidence_score": 0.0-1.0,       // Source-backed confidence
  "requires_manual_review": true,   // Flag for admin attention
  "auto_approved_if": "string",     // Optional auto-approve rule (e.g., "score > 0.85")
  "reviewer_notes": "string|null",  // Optional guidance for reviewers
  "created_at": "timestamp",
  "expires_at": "timestamp"         // Optional TTL for stale drafts
}
```

### Database Table

```sql
CREATE TABLE venue_review_queue (
    review_id PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_evidence TEXT NOT NULL,
    venue_name TEXT NOT NULL,
    venue_mapping_draft JSON NOT NULL,
    suggested_status TEXT DEFAULT 'pending',
    confidence_score REAL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    requires_manual_review BOOLEAN DEFAULT true,
    auto_approved_if TEXT,
    reviewer_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    UNIQUE(source_name, venue_name, created_at
