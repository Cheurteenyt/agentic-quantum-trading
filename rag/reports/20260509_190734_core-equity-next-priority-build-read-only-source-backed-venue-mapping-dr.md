# Local Advisor Report

Generated: 2026-05-09T19:07:34

## Question

Core Equity next priority: build read-only source-backed venue mapping drafts from public evidence scan. It should suggest proposed venue/source_url/impact but never write. Need guardrails/tests.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# RAG Context Analysis: Core Equity Venue Mapping Draft

## Assessment

The provided repository context is **insufficient** to answer the specific question about building "read-only source-backed venue mapping drafts from public evidence scan."

## What's Missing

The context contains information about:

1. **Labeling architecture** (`label_ledger.py`, `label_expansion.py`, `label_ledger.db`)
2. **On-chain engine** (`onchain_engine.py`, `wallet_chain_state`)
3. **Arkham coverage** (`arkham.py`, Scrapling snapshots)
4. **Entity coverage** (`onchain_entities.py`, `onchain_chains.py`)
5. **RPC state tracking** (`onchain_coverage.py`, `onchain_quality.py`)

However, it lacks specific details about:

| Missing Information | Why It Matters |
|---------------------|----------------|
| **Venue mapping data model** | How are venues (DEXes, CEXes, bridges) structured in the database? |
| **Source URL schema** | What fields store source evidence (Arkham pages, explorer URLs, API sources)? |
| **Impact scoring** | How is "impact" computed for venue mappings? |
| **Public evidence scan** | What constitutes "public evidence" and how is it scraped/ingested? |
| **Draft vs. published state** | How are "drafts" distinguished from committed mappings? |
| **Guardrails architecture** | What tests exist for venue mapping correctness? |
| **Source attribution model** | How is evidence linked to venue entries? |

## What Can Be Inferred

From the existing architecture, I can reasonably infer:

1. **Source URLs** are likely stored in `wallet_chain_state` or a related table with columns like `source_url`, `source_type`, `evidence_score`
2. **Impact** is probably computed from activity metrics (transaction count, volume, label coverage)
3. **Guardrails** likely exist in `backend/services/onchain_quality.py` or similar quality modules
4. **Tests** would be in `backend/tests/` or `backend/services/test_*.py`

## Recommendation

To properly answer this question, the following context should be retrieved:

```powershell
# 1. Inspect venue mapping data model
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What tables store venue mappings and their source evidence?" --domain data

# 2. Find impact computation logic
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "How is venue impact scored?" --domain backend

# 3. Check existing tests for venue/source validation
D:\trading
