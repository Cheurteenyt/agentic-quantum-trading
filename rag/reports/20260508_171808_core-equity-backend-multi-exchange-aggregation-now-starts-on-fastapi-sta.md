# Local Advisor Report

Generated: 2026-05-08T17:18:08

## Question

Core Equity: backend multi-exchange aggregation now starts on FastAPI startup and populates funding opportunities. Suggest the next highest-impact data reliability priority for Arkham-like RPC/on-chain coverage. Do not propose editing files, only analysis.

## Sources

- `backend/routers/arkham.py`
- `backend/services/arkham_scraper.py`
- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Next Highest-Impact Data Reliability Priority

## 1. Useful Facts (from retrieved context)

| Fact | Source |
|------|--------|
| Arkham-like coverage currently tracks labelled addresses, assets, RPC transactions, and holder rows | Source 1 |
| Current coverage tiers: "strong" requires labelled≥1000, assets≥50, tx_rows≥100000, holders≥1000 | Source 1 |
| RPC ingestion gate currently allows only "ethereum_recent_blocks" and "bsc_recent_blocks" as safe | Source 2 |
| Not-yet-safe items include "full historical archive ingestion" and "cross-chain wallet clustering without confidence scoring" | Source 2 |
| Current labelled address count is approximately 649 (from project_state.md) | Memory |
| Entity-chain gap enrichment is the current auto-enrichment default | Memory |
| Coverage metrics are chain-scoped and stored in `wallet_chain_state` | Memory |

## 2. Hypotheses for Codex to Verify

**Hypothesis 1**: The highest-impact reliability gap is **labelled-wallet RPC coverage per chain**, not raw transaction volume.

**Reasoning**: 
- The coverage matrix (Source 1) shows Arkham-like value depends on "labels, attribution, and chain-scoped source quality first"
- Current auto-enrichment focuses on `entity-chain-gaps` (Memory), meaning the system already recognizes chain coverage as the bottleneck
- The RPC gate explicitly allows only recent blocks, implying historical labelled-wallet coverage is incomplete

**Hypothesis 2**: The next priority is **per-chain labelled-wallet RPC state completeness** before expanding to cross-chain clustering.

**Reasoning**:
- Cross-chain clustering is explicitly marked "not_safe_yet" (Source 2)
- The system already has entity-chain gap planning working (Memory)
- Adding cross-chain logic without per-chain RPC completeness would compound reliability issues

## 3. Concrete Next Checks (No Edits)

```powershell
# 1. Inspect current per-chain labelled-wallet coverage
curl "http://localhost:8000/api/onchain/rpc/entity-chain-gaps" | jq '.missing_pairs | length'

# 2. Check wallet_chain_state rows per chain
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\backend\services\onchain_chains.py --report-per-chain

# 3. Verify labelled address distribution across chains
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\backend\services\onchain_coverage.py --domain data --prompt-only
```

## 4. Risks / False Positives / Non-Goals

| Category | Details |
|----------|---------|
| **Risk** | Focusing on historical archive first would violate the "not_safe_yet" guidance (Source 2) |
| **False Positive** | Raw transaction counts (tx_rows) may inflate "strong" tier without meaningful labelled attribution |
| **Non-Goal** | This is not about increasing RPC call volume; it's about per-chain labelled-wallet completeness |

## 5. Tiny Experiments Codex May Choose to Run

```python
# Pseudo-code for verification query
def verify_chain_rpc_completeness():
    """Check if each labelled entity has RPC state on its primary chains"""
    labelled_entities = get_labelled_entities(min_confidence=0.8)
    primary_chains = {"ethereum", "bsc", "arbitrum"}  # From Source 2 coverage_chains
    
    incomplete = []
    for entity, primary_chain in labelled_entities.items():
        rpc_state = query_wallet_chain_state(entity, primary_chain)
        if not rpc_state or len(rpc_state) < expected_min:
            incomplete.append((entity, primary_chain))
    
    return incomplete
```

## 6. Confidence and Missing Context

**Confidence**: 7/10 — The analysis is constrained by limited visibility into the exact `wallet_chain_state` schema and current per-chain row counts.

**Missing Context**:
- Exact current row counts per chain in `wallet_chain_state` (Source 1 shows schema but not live counts)
- Which entities have the largest per-chain RPC gaps
- Current historical archive depth (if any)

---

## Final Answer

**The next highest-impact data reliability priority is: Per-chain labelled-wallet RPC state completeness.**

This priority:
1. Directly addresses the "not_safe_yet" item: "cross-chain wallet clustering without confidence scoring" (Source 2)
2. Builds on the existing entity-chain gap infrastructure already working in production (Memory)
3. Respects the RPC ingestion gate that prioritizes chain-scoped quality over volume (Source 2)
4. Ensures Arkham-like value metrics (labels, attribution) have the required chain-scoped foundation (Source 2)

The system should complete per-chain RPC coverage for existing labelled entities before attempting cross-chain clustering or historical archive ingestion.
