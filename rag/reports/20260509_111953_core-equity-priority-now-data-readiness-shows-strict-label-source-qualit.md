# Local Advisor Report

Generated: 2026-05-09T11:19:53

## Question

Core Equity priority now: data-readiness shows strict label/source quality blockers. Suggest one small safe backend patch to improve automatic data reliability without trusted auto-promotion.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

## Analysis

**Problem:** Data-readiness shows strict label/source quality blockers. Need one small safe backend patch to improve automatic data reliability without trusted auto-promotion.

**Current Architecture Review:**
- `label_ledger.py`: builds deduped label ledger from Scrapling snapshots
- `label_expansion.py`: derives low/medium confidence labels from on-chain data
- `onchain_engine.py`: local RPC/on-chain engine with `wallet_chain_state` tracking
- `onchain_entities.py`: canonical entity aliases for coverage/enrichment
- `onchain_quality.py`: address quality classification helpers

**Identified Gap:** The architecture separates label derivation from quality validation. Labels flow through:
1. Scrapling → normalized snapshots → label ledger (high-confidence)
2. On-chain data → label expansion (low/medium confidence)
3. Entity alias matching in `onchain_entities.py`

**Quality Blocker:** The system lacks a **source attribution validation layer** that verifies label provenance before it enters the ledger. This means:
- Derived labels may propagate unverified source claims
- Entity aliases may mismatch without source verification
- No automated check that a label's source actually supports its confidence level

---

## Recommended Patch

**Add a lightweight source-validation gate in `label_ledger.py` that runs before ledger insertion.**

### Implementation

```python
# In backend/services/label_ledger.py, add before ledger write:

def validate_label_source(label_row: dict, ledger: sqlite3.Connection) -> bool:
    """
    Verify label source attribution matches stored evidence.
    Returns True if source validation passes, False otherwise.
    """
    label_source = label_row.get('source')
    evidence_count = label_row.get('evidence_count', 0)
    confidence = label_row.get('confidence', 0)
    
    if not label_source or evidence_count < 1:
        return False
    
    # Validate source exists in known sources registry
    known_sources = ledger.execute(
        "SELECT name FROM sources WHERE active = 1"
    ).fetchall()
    source_names = [row[0] for row in known_sources]
    
    if label_source not in source_names:
        return False
    
    # Validate evidence count matches confidence level
    min_evidence = {
        'high': 3,
        'medium': 1,
        'low': 1
    }.get(confidence, 1)
    
    return evidence_count >= min_evidence

# Wrap ledger insertion with validation:
def insert_with_validation(label_row: dict, ledger: sqlite3.Connection) -> None:
    if not validate_label_source(label_row, ledger):
        # Log but don't block - allows manual review path
        logger.warning(
            f"Source validation failed for label: {label_row.get('label')}, "
            f"source: {label_row.get('source')}"
        )
        return
    ledger.execute(
        "INSERT OR REPLACE INTO labels (...) VALUES (...)"
    )
```

### Why This Is Safe

1. **No auto-promotion** - Labels still require existing confidence thresholds; this only validates source attribution
2. **Backwards compatible** - Existing labels pass if they have valid source/evidence data
