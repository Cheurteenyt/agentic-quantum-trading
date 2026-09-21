# Local Advisor Report

Generated: 2026-05-07T17:15:35

## Question

Analyse Core Equity en lecture seule: quelles sont les 5 prochaines actions les plus utiles pour augmenter la couverture data RPC Arkham-like sans perdre les labels, sans doublons, et sans ouvrir de risque securite client ?

## Sources

- `backend/routers/arkham.py`
- `backend/services/arkham_scraper.py`
- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`

## Advisor Output

# Analysis: Next 5 Actions to Increase RPC Arkham-like Coverage

## 1. Most Relevant Facts from Context

**Current Coverage Baseline:**
- Local labelled addresses: ~649 (Arkham public: ~3.1B)
- RPC `wallet_chain_state`: 73 rows across 5 chains (ETH 44, BSC 16, ARB 4, BASE 4, POL 5)
- Label ledger: 461 direct + 18 derived labels
- Priority enrichment is already running via `CORE_AUTO_ENRICH_ENABLED=true`

**Arkham-like Value Requirements (from `backend/routers/arkham.py`):**
```
RPC gives raw facts; Arkham-like value requires:
- Labels
- Attribution  
- Chain-scoped source quality first
```

**Current Gaps Identified:**
- `low_label_coverage` (+45 priority score)
- `low_flow_history` (+25 priority score)
- `low_holder_coverage` (+18 priority score)

**Safe RPC Status (from `arkham.py`):**
```
safe_now: ["ethereum_recent_blocks", "bsc_recent_blocks"]
not_safe_yet: ["full historical archive", "cross-chain clustering", "token manipulation alerts"]
```

---

## 2. Useful Hypotheses to Verify

| Hypothesis | Expected Impact |
|-----------|-----------------|
| **Hypothesis 1:** Seed-focused ingestion with label-first filtering will increase `labelled_addresses` to ≥1000 threshold for "strong" coverage tier | Verify by running `backend/services/seed_ingestion.py` with `label_filter_min=0.8` |
| **Hypothesis 2:** Entity alias canonicalization in `onchain_entities.py` will reduce duplicate wallet rows by ~15% | Check `wallet_chain_state` for duplicate `address_kind` + `entity_name` combinations |
| **Hypothesis 3:** Priority enrichment with `limit_per_entity=50` will bring `wallet_rows` to ≥100,000 for "useful" tier | Monitor `data_jobs` table after next auto-enrich cycle |
| **Hypothesis 4:** Adding `base` and `arbitrum` to safe RPC list will increase chain diversity without security risk | Test via `backend/routers/onchain.py` ingestion endpoints |
| **Hypothesis 5:** Label-ledger rebuild with `CORE_AUTO_LABEL_BUILD_ENABLED=true` will improve coverage matrix completeness | Check `chain_coverage_matrix` output after rebuild |

---

## 3. Files and Endpoints Worth Inspecting Next

**Priority Files:**
```
1. backend/services/seed_ingestion.py    # Label-first ingestion logic
2. backend/services/onchain_entities.py  # Canonical alias handling
3. backend/routers/arkham.py             # Coverage tier computation
4. backend/data/onchain/wallet_chain_state  # Current RPC state
5. backend/data/arkham/manual/verified_entity_labels.json  # Traceable seeds
```

**Key Endpoints:**
```
GET  /api/onchain/rpc/entity-gaps        # Current gap classification
POST /api/onchain/rpc/enrich-priority   # Priority enrichment control
GET  /api/onchain/rpc/data-jobs         # Audit trail for enrichment jobs
```

---

## 4. Risks and Non-Goals

**Risks:**
- **Bulk ingestion risk:** Avoid "full historical archive" until coverage tier reaches "useful"
- **Cross-chain clustering:** Not safe yet without confidence scoring
- **Token manipulation alerts:** Needs holder/flow baselines first

**Non-Goals:**
- Not merging ETH/BSC/Solana data without explicit chain/source separation
- Not treating derived labels as high-confidence until external confirmation
- Not exposing admin endpoints to non-localhost

---

## 5. Small Next Experiments

**Experiment 1 (Coverage Tier Push):**
```bash
# Run seed-focused ingestion with label filter
python backend/services/seed_ingestion.py \
  --chain ethereum \
  --label-filter-min 0.8 \
  --limit 10000
```
*Expected: Push `labelled_addresses` toward 1000 threshold*

**Experiment 2 (Alias Dedupe Check):**
```bash
# Query for duplicate entity coverage
curl "http://localhost:8000/api/onchain/rpc/entity-gaps?entity=Binance"
```
*Expected: Identify if `Binance` + `Binance Wallet` are being counted separately*

**Experiment 3 (Priority Enrichment Audit):**
```bash
# Check current enrichment job history
curl "http://localhost:8000/api/onchain/rpc/data-jobs?limit=10"
```
*Expected: Verify `limit_per_entity` and `max_entities` are being respected*

---

## 6. Confidence

| Aspect | Confidence |
|--------|------------|
| Coverage tier thresholds are correct | 95% - Directly from `arkham.py` |
| Seed-focused ingestion is safe path | 90% - Aligned with "safe_now" list |
| Alias canonicalization will help | 85% - Inferred from `onchain_entities.py` design |
| Priority enrichment is active | 95% - Confirmed by `CORE_AUTO_ENRICH_ENABLED=true` |

---

## Summary

The **most useful next action** is to run **seed-focused ingestion with label-first filtering** (Experiment 1) because:
1. It directly addresses the `low_label_coverage` gap (+45 priority score)
2. It uses the "safe_now" RPC pattern already validated
3. It targets the "strong" coverage tier threshold (labelled ≥1000)
4. It preserves the labels-first philosophy already embedded in the codebase
