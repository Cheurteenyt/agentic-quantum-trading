# Local Advisor Report

Generated: 2026-05-10T01:10:24

## Question

Core Equity priority: design a read-only public identity acquisition scan for unknown router source acquisition queue. It should compare lightweight no-public-evidence queue vs detailed public-evidence queue, report which rows become research-ready, and write nothing. Suggest safe fields/blockers.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# RAG Context Assessment

After reviewing the provided repository context, I can confirm the following about Core Equity's architecture:

## What Is Present in Context

| Area | Status | Key Details |
|------|--------|-------------|
| **Label Ledger** | ✅ Documented | Built from Scrapling normalized Arkham snapshots; high-confidence labels are trusted write lane |
| **RPC/On-Chain Engine** | ✅ Documented | `onchain_engine.py` handles blocks, transactions, swaps, wallets; tracks `wallet_chain_state` |
| **Admin Endpoints** | ✅ Documented | `onchain.py` router with protected mutation endpoints requiring `CORE_ADMIN_TOKEN` |
| **Data Architecture** | ✅ Documented | Arkham snapshots, label ledger DB, on-chain DB with entity/chain coverage |
| **AI Agent Protocol** | ✅ Documented | Codex = decision/patch authority; Qwen = read-only advisor via RAG |
| **RAG Operations** | ✅ Documented | Health checks, re-indexing, domain routing, embedding spectrum analysis |

## What Is Missing for This Specific Request

The requested feature involves:
1. **Read-only public identity acquisition scan** for unknown router source acquisition queue
2. **Comparison** between lightweight no-public-evidence queue vs detailed public-evidence queue
3. **Research-ready row identification**
4. **Field/blocker analysis**

### Missing Context:

1. **Acquisition Queue Schema** — The context mentions "acquisition queue" but does not show:
   - Table/column definitions for the queue
   - How "unknown router source" is identified
   - Existing queue processing logic

2. **Evidence Classification Logic** — We need to know:
   - What constitutes "lightweight no-public-evidence" vs "detailed public-evidence"
   - Where evidence metadata is stored
   - How evidence depth is scored

3. **Research-Ready Criteria** — The context mentions "research-ready" labels but doesn't define:
   - The decision matrix for when a row qualifies
   - What "public evidence" means in this context

4. **Router Source Identification** — "Unknown router source" is mentioned but:
   - How router sources are tracked is not documented
   - What makes a router source "unknown" vs "known"

5. **Existing Comparison Patterns** — The architecture shows coverage comparison (`onchain_coverage.py`) but not evidence-depth comparison patterns.

## Recommended Next Steps for Codex

To implement this feature, Codex should:

1. **Inspect the acquisition queue schema** — Search for queue-related models, tables, or data structures
2. **Find evidence storage patterns** — Look for how label evidence is captured and scored
3. **Review existing admin endpoints** — Check `onchain.py` for similar read-only analysis patterns
4. **Examine label promotion logic** — Understand current evidence requirements before adding new criteria

---

**Summary**: The repository context is sufficient for understanding Core Equity's architecture, AI agent protocol, and RAG operations. However, the specific feature request touches acquisition queue internals and evidence classification that are not documented in the provided context. Codex needs to inspect the queue schema, evidence storage, and existing admin endpoint patterns before implementing this feature.
