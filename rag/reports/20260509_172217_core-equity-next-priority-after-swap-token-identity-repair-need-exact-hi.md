# Local Advisor Report

Generated: 2026-05-09T17:22:17

## Question

Core Equity next priority after swap token identity repair: need exact historical DEX/router swap ingestion for manipulation readiness. What minimal safe backend patch should Codex do next without bulk scanning or client execution?

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Next Priority After Swap Token Identity Repair

## Understanding the Current State

Based on the repository context, I can identify the following key elements:

### Current Architecture Summary
- **Backend Path**: `D:\trading-agent\backend`
- **Label Ledger**: 461 direct labels + 18 derived labels in `backend/data/arkham/label_ledger.db`
- **RPC State**: `wallet_chain_state` table with 267 rows across multiple chains
- **Coverage**: ~649 measured labelled addresses

### Current Data Ingestion Flow
```
Scrapling → Normalized Snapshots → Label Ledger → Seed Ingestion → On-chain Engine
```

### Key Services
- `label_ledger.py`: Builds deduped label ledger from Scrapling snapshots
- `label_expansion.py`: Derives low/medium confidence labels
- `seed_ingestion.py`: Ingests recent transactions around high-confidence seed labels
- `onchain_engine.py`: Local RPC/on-chain engine for blocks, swaps, wallets

## Identifying the Gap

The repository context shows:
1. ✅ Label ingestion from Arkham snapshots exists
2. ✅ Label expansion and derivation exists
3. ✅ Seed ingestion around high-confidence labels exists
4. ✅ On-chain RPC enrichment exists
5. ❓ **Historical DEX/router swap ingestion for manipulation readiness** — NOT explicitly documented

## What's Missing from Context

To provide a precise answer about the "minimal safe backend patch," I need to know:

1. **Current swap data coverage**: What historical depth of DEX/router swaps is currently stored in `onchain.db`?
2. **Manipulation detection requirements**: What specific manipulation patterns need historical swap data to detect?
3. **Existing swap ingestion code**: Is there partial swap ingestion that needs extension, or is this entirely new?
4. **Storage constraints**: What's the acceptable historical depth (e.g., last 30 days, 90 days, all time)?
5. **Performance budget**: Any constraints on query latency for manipulation detection?

## Recommended Next Step

**For Codex to proceed safely**, retrieve the following from RAG:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What swap data is currently stored in onchain.db and how is it queried?" --domain data

D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "How are DEX and router entities tracked for manipulation detection?" --domain backend
```

---

**Summary**: The repository context confirms robust label and RPC infrastructure but lacks explicit documentation of historical swap ingestion depth and manipulation detection requirements. Codex should first query RAG for current swap data coverage before designing the minimal patch for historical DEX/router swap ingestion.
