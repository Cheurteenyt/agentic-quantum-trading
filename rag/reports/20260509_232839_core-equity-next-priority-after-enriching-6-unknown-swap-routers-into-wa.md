# Local Advisor Report

Generated: 2026-05-09T23:28:39

## Question

Core Equity next priority: after enriching 6 unknown swap routers into wallet_chain_state, router label-source rows are still 0/31. Suggest the safest read-only evidence gap report before any mapping or label promotion. No edits.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Core Equity Evidence Gap Report

## Analysis

Based on the repository context, here is the safest read-only evidence gap report before any mapping or label promotion:

---

## 1. Useful Facts (with sources)

| Fact | Source |
|------|--------|
| `wallet_chain_state` currently has 267 rows across 5 chains (eth: 227, bsc: 18, polygon: 6, base: 12, arbitrum: 4) | Source 3 |
| Router label-source rows are 0/31 — meaning 31 router entities exist but have zero label-source attribution | Source 1 (inferred from "router label-source rows are still 0/31") |
| 6 unknown swap routers were recently enriched into `wallet_chain_state` | Source 1 |
| Admin endpoints require `CORE_ADMIN_TOKEN` for mutations; read-only gap reports remain accessible without admin credentials | Source 1 |
| Evidence bundles are persisted with `label_candidate_corroboration` logged in `data_jobs` | Source 1 |
| `CORE_AUTO_CORROBORATE_LIMIT` is clamped to `<=25` and timeout to `<=20` | Source 1 |
| Alpha Lab's `Recent Data Jobs` provides read-only audit trail for label builds and RPC enrichment | Source 1 |
| Chain-gap RPC enrichment tracks `wallets_updated` (RPC attempt count) vs `net_rpc_wallets_added` (actual gap reduction) | Source 1 |
| `CORE_AUTO_SOURCE_ACQUIRE_ENABLED=true` (default) runs bounded source acquisition when no gaps remain | Source 2 |
| Priority RPC enrichment exists via a dedicated endpoint | Source 3 |
| `wallet_chain_state` tracks: address kind, contract flag, native USD value, activity tier, risk flags, data quality score, label source evidence, RPC source attribution | Source 4 |

---

## 2. Hypotheses for Codex to Verify

1. **Router label-source gap is an evidence attribution issue, not a data absence** — The 6 routers exist in `wallet_chain_state` but lack source attribution in the label-source dimension.

2. **The gap report endpoint exists and is read-only** — Based on Source 1, gap reports are accessible without admin credentials, making them safe to query.

3. **Router entities may be missing source-backed evidence bundles** — Unlike the 6 enriched wallets, routers may not have corresponding evidence bundles in the persisted bundles store.

4. **The 0/31 ratio suggests a systematic mapping gap** — All 31 router entities exist but none have label-source attribution, indicating a batch-level evidence gap.

---

## 3. Concrete Next Checks (No Edits)

```powershell
# 1. Query router-specific gap report (read-only, no admin needed)
curl "http://localhost:8000/api/onchain/rpc/entity-gaps?entity_type=router&min_confidence=medium"

# 2. Check persisted evidence bundles for router-related sources
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What evidence bundles exist for swap routers?" --
