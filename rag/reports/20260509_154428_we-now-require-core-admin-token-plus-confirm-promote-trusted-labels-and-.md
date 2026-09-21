# Local Advisor Report

Generated: 2026-05-09T15:44:28

## Question

We now require CORE_ADMIN_TOKEN plus confirm=PROMOTE_TRUSTED_LABELS and max 10 IDs for dry_run=false trusted-label promotion. Next guardrail before any real promotion: automatic DB backup before write, append promotion audit table, or both? Pick the safest minimal implementation that fits current local SQLite label_ledger architecture, with tests and no auto-promotion.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Trusted Label Promotion Guardrails

## Current Architecture Review

Based on the repository context, here's what exists for label management:

### Existing Components
| Component | Location | Purpose |
|----------|----------|---------|
| Label Ledger | `backend/data/arkham/label_ledger.db` | High-confidence and derived label storage |
| Label Expansion | `backend/services/label_expansion.py` | Derives low/medium confidence labels |
| Seed Ingestion | `backend/services/seed_ingestion.py` | Ingests transactions around seed labels |
| On-chain Engine | `backend/services/onchain_engine.py` | RPC orchestration and storage |

### Current Gaps for Trusted Promotion

The architecture lacks:
1. **Pre-write database backup mechanism**
2. **Promotion audit trail table**
3. **Trusted label promotion endpoint** with admin gates
4. **Dry-run validation** before actual promotion

## Recommended Implementation

### Option: Combined Approach (Safest Minimal)

```
┌─────────────────────────────────────────────────────────────┐
│                    Trusted Label Promotion                    │
├─────────────────────────────────────────────────────────────┤
│  1. Automatic SQLite Backup (before any write)               │
│  2. Append to promotion_audit table (immutable log)          │
│  3. No auto-promotion - requires explicit admin call         │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Details

**1. Database Backup (Pre-Write)**
```python
# In promotion service, before any INSERT/UPDATE
import sqlite3

def backup_database(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    backup_path = f"{db_path}.backup.{int(time.time())}"
    shutil.copy2(db_path, backup_path)
    return backup_path
```

**2. Promotion Audit Table**
```sql
CREATE TABLE IF NOT EXISTS promotion_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    promoted_label TEXT NOT NULL,
    promoted_by TEXT NOT NULL,
    confidence_score REAL,
    source_evidence TEXT,
    dry_run BOOLEAN DEFAULT FALSE,
    status TEXT NOT NULL,
    backup_file TEXT
);
```

**3. Admin Endpoint Requirements**
- Requires `CORE_ADMIN_TOKEN` header
- Requires `confirm=PROMOTE_TRUSTED_LABELS` query param
- Accepts max 10 IDs in single request
- `dry_run=false` triggers actual promotion after backup+audit

## Verification Checklist

Before implementation, verify:
- [ ] Current `label_ledger.py` schema (check for existing audit table)
- [ ] Existing admin token handling pattern in `onchain.py` routers
- [ ] Current backup strategy (if any) in `onchain_engine.py`
- [ ] Test coverage for label mutation endpoints

## Confidence: HIGH

The combined approach is safest because:
1. **Backup** provides rollback capability
2. **Audit table** creates forensic trail
3. **No auto-promotion** preserves current manual control
4. **Minimal changes** to existing architecture

---

**Next Steps for Codex:**
