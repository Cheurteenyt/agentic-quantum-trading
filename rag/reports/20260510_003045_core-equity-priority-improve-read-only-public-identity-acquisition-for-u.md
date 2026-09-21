# Local Advisor Report

Generated: 2026-05-10T00:30:45

## Question

Core Equity priority: improve read-only public identity acquisition for unknown swap routers that have RPC state but no candidate venue hint. It must not write labels, candidates, mappings, swaps, or execution settings. Suggest safe outputs and blockers only.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Core Equity Read-Only Public Identity Acquisition Analysis

## 1. Useful Facts (with source paths)

**Current Architecture:**
- `wallet_chain_state` table tracks RPC enrichment with fields: address kind, contract flag, native USD value, activity tier, risk flags, data quality score, label source evidence, RPC source attribution [Source 3]
- Entity RPC enrichment examples show complete coverage (e.g., Uniswap 65/65, Binance 58/58) [Source 3]
- `wallet_chain_state` has 267 rows across multiple chains [Source 3]

**Existing Read-Only Endpoints:**
- `GET /api/onchain/rpc/entity-gaps` - Classifies entities as `missing_labels`, `needs_rpc_enrichment`, `partial_rpc`, `weak_quality`, or `usable_seed` using only local labels + RPC state [Source 3]
- `GET /api/onchain/rpc/entity-chain-gaps` - Returns entity/chain RPC gaps [Source 3]
- `GET /api/market/multi-exchange` - Reports funding symbols and RPC wallet state [Source 3]

**Label Architecture:**
- Label ledger built from Scrapling normalized Arkham snapshots via `backend/services/label_ledger.py` [Source 3]
- Label expansion derives low/medium confidence labels via `backend/services/label_expansion.py` [Source 3]
- Verified manual public-label seeds live in `backend/data/arkham/manual/verified_entity_labels.json` [Source 3]

**Current Coverage Baseline:**
- About 649 measured labelled addresses [Source 3]
- 461 direct labels, 18 derived labels after seed-focused ETH ingestion [Source 3]

---

## 2. Hypotheses for Codex to Verify

**Hypothesis 1:** The `entity-gaps` endpoint already provides the read-only identity assessment needed for unknown swap routers with RPC state but no venue hint.

**Hypothesis 2:** The `wallet_chain_state` table already contains the "RPC state" dimension needed to rank unknown entities by data quality score and activity tier.

**Hypothesis 3:** The `label_ledger.db` contains the "candidate venue hint" dimension, but unknown routers lack this because they haven't been discovered by Scrapling/Arkham yet.

**Hypothesis 4:** The architecture supports adding a "public identity score" field to `wallet_chain_state` that combines label coverage, RPC activity, and venue hint presence without writing any labels or mappings.

---

## 3. Concrete Next Checks (No Edits)

**Check 1 - Entity Gaps Output:**
```bash
curl -s "http://localhost:8000/api/onchain/rpc/entity-gaps?min_confidence=high" | jq '.[] | {entity, status, rpc_coverage, label_coverage}'
```
Verify that unknown swap routers appear with `needs_rpc_enrichment` or `weak_quality` status.

**Check 2 - Wallet Chain State Schema:**
```bash
sqlite3 backend/data/onchain/onchain.db "PRAGMA table_info(wallet_chain_state);"
```
Confirm presence of: `data_quality_score`, `activity_tier
