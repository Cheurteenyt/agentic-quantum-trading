# Local Advisor Report

Generated: 2026-05-09T18:51:02

## Question

Core Equity next step: source evidence for unknown DEX routers. Add read-only public explorer metadata fetcher, no mapping writes. Need minimal guardrails/tests. Advise.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Core Equity Next Step Analysis

## Understanding the Request

The user is asking for architectural guidance on implementing a **read-only public explorer metadata fetcher** to source evidence for unknown DEX routers, with minimal guardrails and tests.

## Current Architecture Analysis

Based on the repository context, here's what exists and what's needed:

### Existing Relevant Components

| Component | Location | Relevance |
|----------|----------|-----------|
| Explorer API services | `backend/services/seed_ingestion.py` | Uses explorer APIs for transaction ingestion |
| Label ledger | `backend/data/arkham/label_ledger.db` | Stores label evidence |
| RPC state | `backend/data/onchain/wallet_chain_state` | Stores wallet metadata |
| Entities service | `backend/services/onchain_entities.py` | Handles canonical entity aliases |
| Coverage service | `backend/services/onchain_coverage.py` | Tracks labelled-vs-RPC coverage |

### What's Missing

The architecture lacks:
1. A dedicated **DEX router metadata store** (no explicit table/column references)
2. A **read-only explorer metadata fetcher** service
3. Evidence validation pipeline for unknown routers
4. Minimal test suite for new data sources

## Recommended Implementation

### 1. Database Schema Addition

Add to `wallet_chain_state` or create a new `dex_router_metadata` table:

```sql
-- If extending wallet_chain_state:
ALTER TABLE wallet_chain_state ADD COLUMN router_evidence TEXT;
ALTER TABLE wallet_chain_state ADD COLUMN router_source VARCHAR(255);
ALTER TABLE wallet_chain_state ADD COLUMN router_confidence INTEGER;

-- Or new table for router metadata:
CREATE TABLE dex_router_metadata (
    router_address VARCHAR(42) PRIMARY KEY,
    router_name VARCHAR(128),
    source_evidence TEXT,
    first_seen_block INTEGER,
    last_verified_block INTEGER,
    confidence_score INTEGER,
    source_attribution VARCHAR(128),
    verified_at TIMESTAMP
);
```

### 2. Service Implementation

Create `backend/services/explorer_metadata.py`:

```python
"""Read-only explorer metadata fetcher for DEX router evidence."""

import requests
from typing import Optional, Dict, Any
from datetime import datetime

class ExplorerMetadataFetcher:
    """Fetches and validates DEX router metadata from public explorers."""
    
    def __init__(self, base_url: str = "https://api.etherscan.io"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CoreEquity/1.0 ExplorerMetadataFetcher"
        })
    
    def fetch_router_metadata(
        self, 
        router_address: str, 
        chain_id: int
    ) -> Optional[Dict
