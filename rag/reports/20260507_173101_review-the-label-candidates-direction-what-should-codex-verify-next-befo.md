# Local Advisor Report

Generated: 2026-05-07T17:31:01

## Question

Review the label_candidates direction. What should Codex verify next before promoting any candidate into a trusted label? Focus on evidence, source URLs, dedupe keys, and false positives.

## Sources

- `backend/services/label_ledger.py`
- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`

## Advisor Output

# Review: Label Candidates Direction

## 1. Useful Facts (with source paths)

| Fact | Source |
|------|--------|
| `label_candidates` table stores every observed label proposal with `status = 'candidate'` before promotion | `backend/services/label_ledger.py` (Source 2) |
| Dedupe key `_candidate_source_key()` uses: source, source_url, file, label, entity, wallet_type — truncated to 500 chars | `backend/services/label_ledger.py` (Source 1) |
| Source tracking includes `source`, `source_url`, `evidence_json`, `first_seen_at`, `last_seen_at`, `seen_count` | `backend/services/label_ledger.py` (Source 2, Source 4) |
| `source_key` is UNIQUE with (chain, address, source_key) — prevents duplicate candidate rows | `backend/services/label_ledger.py` (Source 4) |
| Candidates are audit-only; not trusted until promoted by explicit verified rules | `backend/services/label_ledger.py` (Source 3) |
| Evidence is stored as JSON and merged via `_merge_unique()` to avoid duplication | `backend/services/label_ledger.py` (Source 4) |
| `seen_count` increments on each sighting of same source_key — signals repeated evidence | `backend/services/label_ledger.py` (Source 2, Source 4) |

---

## 2. Hypotheses for Codex to Verify

| Hypothesis | Why It Matters |
|------------|----------------|
| **H1**: `source_key` may collide if `source_url` is missing or generic (e.g., "unknown") | Would merge distinct evidence sources into one candidate row, hiding source diversity |
| **H2**: `evidence_json` may accumulate duplicates over time if `_merge_unique()` isn't idempotent | Could bloat storage and make evidence review harder |
| **H3**: `seen_count` alone doesn't indicate *quality* of evidence — only frequency | High seen_count could mean spam/repeated scraping, not strong evidence |
| **H4**: Source URLs may be stale or broken, making external verification impossible | Candidates can't be audited if source is unreachable |
| **H5**: No explicit "false positive" flag exists for candidates that were disproven | Disproved candidates remain in database, polluting future analysis |

---

## 3. Concrete Next Checks (No Edits)

```bash
# 1. Check for missing source_url in candidates
D:\trading-agent\.venv-rag\Scripts\python.exe -c "
import sqlite3, json
conn = sqlite3.connect('D:/trading-agent/backend/data/arkham/label_ledger.db')
cands = conn.execute(
    \"\"\"SELECT source, source_url, COUNT(*) 
           FROM label_candidates 
           WHERE status = 'candidate' 
           GROUP BY source, source_url 
           HAVING source_url IS NULL OR source_url = '' 
           LIMIT 20\"\"\"
).fetchall()
for row in cands:
    print(f'Source: {row[0]}, URL: {row[1]}, Count: {row[2]}')
conn.close()
"
```

```bash
# 2. Check for duplicate source_keys with different evidence
D:\trading-agent\.venv-rag\Scripts\python.exe -c "
import sqlite3
conn = sqlite3.connect('D:/trading-agent/backend/data/arkham/label_ledger.db')
dups = conn.execute(
    \"\"\"SELECT source_key, COUNT(*) as cnt, 
           MIN(evidence_json) as first_evidence,
           MAX(evidence_json) as last_evidence
           FROM label_candidates 
           WHERE status = 'candidate'
           GROUP BY source_key
           HAVING COUNT(*) > 1
           LIMIT 20\"\"\"
).fetchall()
for row in dups:
    print(f'Source Key: {row[0]}, Count: {row[1]}')
    print(f'  First: {row[2][:100]}...')
    print(f'  Last:  {row[3][:100]}...')
conn.close()
"
```

```bash
# 3. Check evidence diversity per candidate
D:\trading-agent\.venv-rag\Scripts\python.exe -c "
import sqlite3, json
conn = sqlite3.connect('D:/trading-agent/backend/data/arkham/label_ledger.db')
# Find candidates with high seen_count but single evidence source
high_seen = conn.execute(
    \"\"\"SELECT proposed_label, proposed_entity, seen_count, 
           JSON_LENGTH(evidence_json) as ev_count
           FROM label_candidates 
           WHERE status = 'candidate' AND seen_count > 10
           ORDER BY seen_count DESC
           LIMIT 20\"\"\"
).fetchall()
for row in high_seen:
    ev = json.loads(row[3]) if row[3] else []
    unique_urls = set(e.get('url', '') for e in ev if isinstance(e, dict))
    print(f'Label: {row[0]}, Entity: {row[1]}, Seen: {row[2]}, Ev: {row[3]}, Unique URLs: {len(unique_urls)}')
conn.close()
"
```

```bash
# 4. Check for broken source URLs
D:\trading-agent\.venv-rag\Scripts\python.exe -c "
import requests, sqlite3
conn = sqlite3.connect('D:/trading-agent/backend/data/arkham/label_ledger.db')
urls = conn.execute(
    \"\"\"SELECT DISTINCT source_url 
           FROM label_candidates 
           WHERE source_url IS NOT NULL AND source_url != ''
           LIMIT 500\"\"\"
).fetchall()
broken = 0
for url, in urls:
    try:
        r = requests.head(url, timeout=5, allow_redirects=False)
        if r.status_code >= 400:
            broken += 1
    except:
        broken += 1
print(f'Total checked: {len(urls)}, Broken: {broken}')
conn.close()
"
```

---

## 4. Risks / False Positives / Non-Goals

| Category | Details |
|----------|---------|
| **Risks** | - Checking 500+ URLs may timeout if network is slow<br>- Some sources may be intentionally private (e.g., internal reports)<br>- `source_url` may be a generic summary page, not the raw evidence |
| **False Positives** | - High `seen_count` could mean spam sources that scrape the same page repeatedly<br>- Duplicate evidence from different scrapes of same source counts as multiple "sources" |
| **Non-Goals** | - Not verifying each candidate's label correctness (that's promotion)<br>- Not fixing broken URLs (audit-only until promotion)<br>- Not deduping by content similarity (too expensive) |

---

## 5. Tiny Experiments Codex May Choose to Run

```python
# Add to label_ledger.py — audit function only
def _audit_candidate_quality(conn: sqlite3.Connection) -> dict:
    """Return metrics on candidate quality before promotion decisions."""
    rows = conn.execute(
        """
        SELECT 
            COUNT(*) as total_candidates,
            SUM(CASE WHEN source_url IS NULL THEN 1 ELSE 0 END) as no_url,
            SUM(CASE WHEN seen_count > 50 THEN 1 ELSE 0 END) as high_seen,
            SUM(CASE WHEN JSON_LENGTH(evidence_json) > 5 THEN 1 ELSE 0 END) as rich_evidence
        FROM label_candidates
        WHERE status = 'candidate'
        """
    ).fetchone()
    return {
        "total": rows[0],
        "no_source_url": rows[1],
        "high_seen_count": rows[2],
        "rich_evidence": rows[3],
        "recommendation": "Review candidates with no_source_url before promotion"
    }
```

---

## 6. Confidence and Missing Context

| Metric | Value |
|--------|-------|
| **Confidence** | High — Code clearly shows candidate workflow; gaps are in evidence quality, not structure |
| **Missing Context** | - Actual sample of `evidence_json` content (to verify structure)<br>- How many candidates exist vs. trusted labels<br>- Current promotion rate (how many candidates become trusted) |

---

## Summary

**What Codex should verify next:**

1. **Source URL quality** — Check how many candidates have missing or broken source URLs
2. **Evidence diversity** — Verify that high `seen_count` candidates have multiple distinct evidence sources, not just repeated scrapes
3. **Evidence structure** — Inspect actual `evidence_json` content to ensure it contains verifiable URLs and not just metadata
4. **False positive patterns** — Look for candidates with high `seen_count` but low evidence quality (single source, no URL, minimal evidence)

**Priority recommendation:** Run the audit query first to quantify the scale of the issue before any cleanup or promotion policy changes.
