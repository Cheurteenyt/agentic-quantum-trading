# Local Advisor Report

Generated: 2026-05-10T18:57:34

## Question

Core Equity priority data review: inspect current RAG context and project memory. Give Codex the next 5 verification steps to improve Arkham-like label/RPC coverage, with candidate-label safety, dedupe, chain/source separation, and no unsafe bulk ingestion.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/model_routing_guide.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`

## Advisor Output

# Next 5 Verification Steps for Arkham-like Label/RPC Coverage

## 1. Inspect Current Label Acquisition Pipeline

**What to check:**
- `backend/services/label_ledger.py` — verify the dedupe logic and how it handles source attribution
- `backend/routers/arkham.py` — check the acquisition plan endpoint `/api/onchain/labels/acquisition-plan`
- `backend/data/arkham/scrapling/normalized/` — inspect sample normalized snapshots for source URL/evidence presence

**Verification command:**
```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "How are labels built and expanded?" --domain data
```

**Expected finding:** Labels should have source URL/evidence per `project_state.md`. If missing, the pipeline needs source tracking before promotion.

---

## 2. Audit Candidate-Label Safety Before Promotion

**What to check:**
- `backend/services/label_expansion.py` — verify confidence thresholds and promotion rules
- `CORE_AUTO_ENRICH_MIN_CONFIDENCE` env var — ensure it's set conservatively (e.g., 0.75+)
- `backend/data/arkham/manual/verified_entity_labels.json` — confirm every row has source URL/evidence

**Verification command:**
```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset candidate-labels --max-sources 4 --answer-tokens 900 --llm-timeout 90
```

**Expected finding:** Low/medium confidence labels should remain in a candidate pool with manual review gates before becoming high-confidence.

---

## 3. Verify Chain/Source Separation in RPC Enrichment

**What to check:**
- `backend/services/onchain_chains.py` — verify RPC URL, fallback, and chain alias mappings
- `wallet_chain_state` table schema — ensure each row has `chain_id`, `rpc_source`, and `label_source` columns
- `backend/services/onchain_coverage.py` — check coverage summaries per chain

**Verification command:**
```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "Where is Arkham coverage computed?" --domain data
```

**Expected finding:** Each entity should have explicit chain attribution (e.g., Uniswap 65/65 on Ethereum mainnet separately from Base). Bulk cross-chain ingestion must be gated.

---

## 4. Confirm No Unsafe Bulk Ingestion Is Active

**What to check:**
- `CORE_AUTO_ENRICH_INTERVAL_SECONDS` — should be high (e.g., 3600+) or disabled
- `CORE_AUTO_ENRICH_MAX_ENTITIES` — should have a low cap (e.g., 1000) for incremental passes
- `backend/services/seed_ingestion.py` — verify it only ingests "recent transactions around high-confidence seed labels"

**Verification command:**
```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "Where is label expansion implemented?" --domain data --prompt-only
```

**Expected finding:** Bulk ingestion should be disabled by default; only targeted, seed-driven passes should run.

---

## 5. Validate Label/RPC Coverage Metrics Are Accurate

**What to check:**
- `/api/onchain/labels/acquisition-plan` — verify it reports current coverage gaps
- `backend/services/onchain_coverage.py` — check coverage summaries match `project_state.md` baseline
- `wallet_chain_state` row count per chain — should match reported numbers (e.g., eth 227, base 12)

**Verification command:**
```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What are the current coverage baselines?" --domain data
```

**Expected finding:** Coverage metrics should be derived from actual `wallet_chain_state` rows, not hardcoded estimates.

---

## Summary

| Step | Focus | Key File/Endpoint |
|------|-------|-------------------|
| 1 | Label acquisition pipeline | `label_ledger.py`, `arkham.py` |
| 2 | Candidate-label safety | `label_expansion.py`, env vars |
| 3 | Chain/source separation | `onchain_chains.py`, `wallet_chain_state` |
| 4 | Bulk ingestion guardrails | `seed_ingestion.py`, env caps |
| 5 | Coverage metric accuracy | `onchain_coverage.py`, acquisition-plan |

**Next action for Codex:** Run each verification command, compare findings against `project_state.md` baseline, then patch only the minimal files needed to close gaps.
