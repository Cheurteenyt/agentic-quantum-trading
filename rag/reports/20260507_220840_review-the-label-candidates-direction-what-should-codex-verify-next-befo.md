# Local Advisor Report

Generated: 2026-05-07T22:08:40

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
| Candidates are audit-only; not trusted until explicit promotion | `backend/services/label_ledger.py` |
| 519 candidates exist; 25 in strict promotion review queue | `rag/memory/project_state.md` |
| Promotion endpoint requires `CORE_ADMIN_TOKEN` and defaults `dry_run=true` | `rag/memory/project_state.md` |
| Candidates have `source_url`, `evidence_json`, `confidence`, `seen_count` fields | `backend/services/label_ledger.py` |
| Dry-run promotion review found 13 eligible over 30 candidates | `rag/memory/project_state.md` |
| Alpha Lab admin shows `score`, `confidence`, `evidence_count`, `blockers/reasons` | `rag/memory/project_state.md` |
| Dedupe key pattern: `chain + address + proposed_label + proposed_entity` | `backend/services/label_ledger.py` |

---

## 2. Hypotheses for Codex to Verify

| Hypothesis | Why It Matters |
|------------|----------------|
| **H1**: `source_url` is present for 100% of candidates (0% missing per audit) | Verify actual NULL count in DB; missing URLs = unverifiable claims |
| **H2**: `confidence >= 70` correlates with `evidence_json` item count | Higher evidence should enable safer auto-promotion |
| **H3**: `seen_count` is monotonically increasing per candidate | Detects stale candidates that need re-evaluation |
| **H4**: `blockers/reasons` are consistently tagged for low-confidence candidates | Enables rule-based auto-hold logic |
| **H5**: Duplicate candidates share identical `source_url` + `evidence_json` | Could enable bulk merge before review |

---

## 3. Concrete Next Checks (No Edits)

```sql
-- Check 1: Source URL completeness (audit claims 0% missing)
SELECT COUNT(*) as total, SUM(CASE WHEN source_url IS NULL THEN 1 ELSE 0 END) as missing
FROM label_candidates WHERE status = 'candidate';

-- Check 2: Evidence count vs confidence correlation
SELECT 
    AVG(confidence) as avg_confidence,
    COUNT(evidence_json) as evidence_count,
    MIN(evidence_json) as min_evidence
FROM label_candidates 
WHERE status = 'candidate' AND evidence_json IS NOT NULL
GROUP BY COUNT(evidence_json)
ORDER BY COUNT(evidence_json);

-- Check 3: Blockers distribution for held candidates
SELECT 
    proposed_label,
    COUNT(*) as total,
    SUM(CASE WHEN proposed_label = 'held' THEN 1 ELSE 0 END) as held_count
FROM label_candidates 
WHERE status = 'candidate' AND proposed_label IS NOT NULL
GROUP BY proposed_label;

-- Check 4: Duplicate detection by source_url + evidence hash
SELECT 
    source_url,
    SHA2(CONCAT(evidence_json, proposed_label), 256) as evidence_hash,
    COUNT(*) as duplicate_count
FROM label_candidates 
WHERE status = 'candidate'
GROUP BY source_url, evidence_hash
HAVING duplicate_count > 1
LIMIT 20;
```

---

## 4. Risks / False Positives / Non-Goals

| Category | Details |
|----------|---------|
| **False Positive Risk** | High `confidence` candidates may have outdated evidence not reflected in `evidence_json` |
| **Source URL Risk** | "0% missing" may mean empty strings `''` rather than actual URLs |
| **Non-Goal** | Do NOT auto-promote based solely on `confidence >= 70` without evidence review |
| **Non-Goal** | Do NOT merge duplicates without verifying `proposed_entity` matches |
| **Risk** | `seen_count DESC` ordering may surface stale candidates first |

---

## 5. Tiny Experiments Codex May Choose to Run

| Experiment | Expected Outcome |
|------------|------------------|
| **A**: Query candidates with `evidence_count >= 3` AND `confidence >= 75` AND `source_url IS NOT NULL` | Should yield a small, high-quality subset for manual review |
| **B**: Group duplicates by `evidence_hash` and propose single representative for review | Reduces review queue by potential 10-20% |
| **C**: Add `last_verified_at` timestamp to track review age | Identifies candidates older than 30 days needing re-evaluation |
| **D**: Extract `blockers` reasons and count frequency | May reveal common patterns enabling rule-based auto-hold |

---

## 6. Confidence and Missing Context

| Metric | Value |
|--------|-------|
| **Confidence in Facts** | High — directly from code and audit logs |
| **Confidence in Hypotheses** | Medium — requires SQL verification |
| **Missing Context** | Actual `blockers/reasons` content and distribution; exact duplicate merge logic |

---

## Summary

**Before promoting any candidate to trusted label, Codex should verify:**

1. **Evidence Quality**: `evidence_json` contains ≥3 items AND `source_url` is non-empty
2. **Source Traceability**: `source_url` points to verifiable external proof (not just internal logs)
3. **Dedupe Integrity**: Duplicate candidates merged by identical `evidence_hash` before review
4. **False Positive Guard**: `blockers/reasons` field populated for any candidate with `confidence < 80`

The current architecture is audit-first and safe. The next step is adding **evidence freshness tracking** and **duplicate consolidation** before the promotion review queue grows beyond 50 candidates.
