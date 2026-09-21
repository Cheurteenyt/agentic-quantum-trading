# Local Advisor Report

Generated: 2026-05-09T15:24:42

## Question

We fixed persisted evidence gates. Current candidate DB has thousands of open candidates, many duplicate groups, only a few verified-review-ready rows, and acquisition/corroboration are read-only/admin guarded. What is the safest next priority: improve review observability, dedupe more, add promotion audit trail, or improve evidence acquisition targeting? Give a concrete backend next step with no trusted-label auto-promotion.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Safest Next Priority for Candidate DB

## Current Situation (from context)

The repository shows a **labeling/coverage engine** with:
- `label_ledger.py` and `label_expansion.py` building label ledgers from Scrapling snapshots
- `seed_ingestion.py` ingesting transactions around high-confidence seed labels
- `onchain_engine.py` handling RPC/on-chain data with `wallet_chain_state` tracking
- Quality classification in `onchain_quality.py` and coverage in `onchain_coverage.py`
- Entity aliases in `onchain_entities.py` for canonical naming

**Key observation**: The architecture already separates **raw data** (Snapshots, RPC) from **intelligence** (labels, coverage). Labels are derived with confidence levels; high-confidence seeds drive ingestion.

## Evaluating the Four Options

| Option | Engineering Fit | Risk | Alignment |
|-------|-----------------|------|-----------|
| **Improve review observability** | ✅ Low-risk; fits "no trusted-label auto-promotion" | Minimal | ✅ Observability is prerequisite to safe gates |
| **Dedupe more** | ⚠️ Could corrupt label integrity | Medium | ❌ Dedupe risks merging distinct entities |
| **Add promotion audit trail** | ✅ Good, but requires observability first | Low | ✅ But needs context from observability |
| **Improve evidence acquisition targeting** | ⚠️ Touches ingestion; higher risk | Medium-High | ⚠️ Requires stable foundation first |

## Recommended Next Step

**Priority: Improve review observability**

### Concrete Backend Next Step

```python
# Add to backend/services/onchain_coverage.py or new module
# backend/services/label_review.py

from typing import Dict, List, Optional
from datetime import datetime
import sqlite3

class LabelReviewTracker:
    """Tracks review activity without modifying label confidence."""
    
    def __init__(self, db_path: str = "backend/data/label_review.db"):
        self.db_path = db_path
    
    def init_table(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label_name TEXT NOT NULL,
                reviewer_role TEXT NOT NULL,
                action TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def log_review(self, label_name: str, reviewer_role: str, 
                   action: str, metadata: Optional[str] = None) -> None:
        """Log review activity without changing label state."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO review_log (label_name, reviewer_role, action, metadata)
            VALUES (?, ?, ?, ?)
        """, (label_name, reviewer_role, action, metadata))
        conn.commit()
        conn.close()
    
    def get_review_stats(self, days: int = 30) -> Dict:
        """Return review statistics for dashboard/observability."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT reviewer_role,
