# Local Advisor Report

Generated: 2026-05-09T17:49:35

## Question

Core Equity exact swap auto-enrich lane is disabled by default and bounded. Next safety patch: add cooldown/last-run guard using data_jobs so auto loop cannot hammer RPC. What guardrails/tests should Codex implement?

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Swap Auto-Enrich Lane Guardrails

## Understanding the Problem

From the repository context, I can identify:

1. **Current Architecture**: The swap auto-enrich lane is a background process that enriches wallet data via RPC calls, currently bounded but disabled by default.

2. **The Issue**: Without proper guards, an auto-loop could "hammer RPC" endpoints, causing:
   - Rate limit exhaustion
   - Increased latency for other services
   - Potential service disruption
   - Unbounded resource consumption

3. **Proposed Solution**: Add cooldown/last-run guard using `data_jobs` to prevent auto-loop from hammering RPC.

## Guardrails & Tests Codex Should Implement

### 1. Data Jobs Guard Implementation

```python
# Recommended implementation pattern for data_jobs.py

from datetime import datetime, timedelta
import sqlite3
from typing import Optional

def get_last_run_time(job_name: str, db_path: str) -> Optional[datetime]:
    """Retrieve last execution timestamp for a data job."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT run_timestamp FROM data_job_runs "
        "WHERE job_name = ? "
        "ORDER BY run_timestamp DESC LIMIT 1",
        (job_name,)
    )
    row = cursor.fetchone()
    conn.close()
    return datetime.fromisoformat(row[0]) if row else None

def set_last_run_time(job_name: str, run_timestamp: datetime, db_path: str) -> None:
    """Record job execution timestamp with idempotent upsert."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO data_job_runs (job_name, run_timestamp) "
        "VALUES (?, ?) "
        "ON CONFLICT(job_name) DO UPDATE SET run_timestamp = ?",
        (job_name, run_timestamp, run_timestamp)
    )
    conn.commit()
    conn.close()

def is_job_cooldown_active(job_name: str, min_interval: timedelta, db_path: str) -> bool:
    """Check if job is currently in cooldown period."""
    last_run = get_last_run_time(job_name, db_path)
    if not last_run:
        return False
    return datetime.now() - last_run < min_interval
```

### 2. Required Database Schema

```sql
-- data_job_runs table (if not exists)
CREATE TABLE IF NOT EXISTS data_job_runs (
    job_name TEXT PRIMARY KEY,
    run_timestamp ISO8601 NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    rpc_calls_made INTEGER NOT NULL DEFAULT 0,
    errors_encountered INTEGER NOT NULL DEFAULT
