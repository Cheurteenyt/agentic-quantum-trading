# Local Advisor Report

Generated: 2026-05-10T00:41:35

## Question

Core Equity priority: design a read-only proof dossier for unknown routers using router hints, creator/deployer hints, official source rules, and blockers. It must rank evidence quality and never write labels/mappings/candidates/swaps/execution. Suggest statuses and fields.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/model_routing_guide.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`

## Advisor Output

# Read-Only Proof Dossier Design for Unknown Routers

## Architectural Analysis

Based on the repository context, here is the design for a read-only proof dossier system that ranks evidence quality without writing labels, mappings, candidates, swaps, or execution logic.

---

## 1. Evidence Sources & Hints Architecture

### Router Hints (Primary Evidence)
```
Source: backend/services/onchain_entities.py, backend/routers/onchain.py
Location: wallet_chain_state table, RPC enrichment rows
```

**Design:**
- Router hints are extracted from `wallet_chain_state` RPC enrichment rows
- Each hint includes: `router_contract`, `hint_source` (RPC/explorer), `confidence_score`, `timestamp`
- Read-only extraction via `GET /api/onchain/routers/hints/{router_id}` endpoint
- Never modifies `wallet_chain_state`; only queries existing `address_kind`, `contract_flag`, `activity_tier` fields

### Creator/Deployer Hints (Secondary Evidence)
```
Source: backend/services/label_ledger.py, backend/data/arkham/label_ledger.db
Location: High-confidence label ledger rows with source attribution
```

**Design:**
- Creator hints derived from label source evidence in `label_ledger.db`
- Extracts `creator_address`, `deploy_block`, `source_url/evidence` from existing label rows
- Uses `label_source_evidence` field already present in `wallet_chain_state`
- Read-only aggregation via `GET /api/onchain/routers/creator/{address}` endpoint

### Official Source Rules (Tertiary Evidence)
```
Source: backend/services/onchain_coverage.py, backend/routers/arkham.py
Location: Coverage matrix, acquisition plan, source ledger
```

**Design:**
- Official source rules stored in `acquisition_plan` endpoint output
- Rules include: `source_priority`, `evidence_requirement`, `promotion_threshold`
- Read-only retrieval via `GET /api/onchain/rpc/acquisition-plan` endpoint
- Already controlled by `CORE_AUTO_LABEL_BUILD_ENABLED` flag

### Blockers (Exclusion Criteria)
```
Source: backend/services/onchain_quality.py, backend/services/onchain_entities.py
Location: Address quality classification helpers, entity aliases
```

**Design:**
- Blockers include: `risk_flags`, `data_quality_score`, `entity_alias_conflicts`
- Read from existing `risk_flags` and `data_quality_score` fields in `wallet_chain_state`
- Entity alias conflicts checked against `onchain_entities` canonical mappings
- Never writes to blocker lists; only queries existing flags

---

## 2. Evidence Quality Ranking System

### Ranking Algorithm (Read-Only)

```
Evidence Score = (Router_Hint_Score × 0.4) + (Creator_Hint_Score × 0.3) + (Source_Rule_Score × 0.2) - (Blocker_Penalty × 0.1)
```

**Component Scores:**
- `Router_Hint_Score`: Based on `activity_tier` and `contract_flag` from `wallet_chain_state`
- `Creator_Hint_Score`: Based on `label_source_evidence` presence and source URL count
- `Source_Rule_Score`: Based on `acquisition_plan` priority
