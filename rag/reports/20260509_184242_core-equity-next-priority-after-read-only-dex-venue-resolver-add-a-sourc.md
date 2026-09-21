# Local Advisor Report

Generated: 2026-05-09T18:42:42

## Question

Core Equity next priority after read-only DEX venue resolver: add a source-backed venue mapping ledger/admin preview. Need guardrails so no rumor/hardcoded venue pollutes data, no client signal upgrade, auditable backups/tests. Suggest minimal path.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Architectural Recommendation: Venue Mapping Ledger

## Analysis

Based on the repository context, here's the minimal path to implement a source-backed venue mapping ledger with guardrails:

---

## 1. Data Model Design

```
venue_mapping_ledger/
├── venues.db (SQLite)
└── sources.db (SQLite)
```

**venues table:**
| Column | Type | Description |
|--------|------|-------------|
| venue_id | TEXT PK | e.g., "uniswap_v3", "binance" |
| venue_name | TEXT | Human-readable name |
| source_of_truth | TEXT | Primary data source |
| last_verified | TIMESTAMP | Audit trail |
| verification_hash | TEXT | Integrity check |

**source_evidence table:**
| Column | Type | Description |
|--------|------|-------------|
| evidence_id | INTEGER PK |
| venue_id | TEXT FK |
| source_type | TEXT | "rpc", "explorer", "snapshot" |
| source_url | TEXT | Reference |
| verification_date | TIMESTAMP |
| hash | TEXT | Data fingerprint |

---

## 2. Implementation Path

### Phase 1: Ledger Structure (Days 1-2)

```python
# backend/services/venue_ledger.py
import sqlite3
import hashlib
from datetime import datetime
from typing import Optional
from pathlib import Path

class VenueLedger:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()
    
    def _init_schema(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues (
                venue_id TEXT PRIMARY KEY,
                venue_name TEXT NOT NULL,
                source_of_truth TEXT NOT NULL,
                last_verified TIMESTAMP,
                verification_hash TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS source_evidence (
                evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT,
                verification_date TIMESTAMP NOT NULL,
                hash TEXT NOT NULL,
                FOREIGN KEY (venue_id) REFERENCES venues(venue_id)
            )
        """)
        self.conn.commit()
```

### Phase 2: Source-Backed Ingestion Guardrails (Days 3-4)

```python
# backend/services/venue_ingestion.py
import hashlib
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class VenueSource:
    venue_id: str
    source_type: str  # "rpc", "explorer_api", "scraping"
    source_url: str
    data_hash: str  # SHA-256 of raw source snapshot
    verification_date: str

class VenueIngestion:
    def __init__(self, ledger: VenueLedger):
        self.ledger = ledger
    
    def compute_source_hash(self, source_data: bytes) -> str:
        """Deterministic hash for source immutability verification."""
        return hashlib.sha256(source
