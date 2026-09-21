# Local Advisor Report

Generated: 2026-05-09T16:02:20

## Question

Core Equity: après le premier backfill RPC source_attribution (105/330 traceable, Binance 23/76), quelle prochaine action data/RPC est prioritaire, sûre et rentable? Réponds en plan court, lecture seule, sans modifier les fichiers.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

## Analysis

Based on the repository context, I can see this is Core Equity's data architecture with RPC source attribution tracking. Let me analyze the current state and identify the next priority action.

### Current State Summary

**RPC Source Attribution Status:**
- Total traceable: 330 addresses
- Traceable (source_attribution): 105/330 (31.8%)
- Binance specifically: 23/76 traceable (30.3%)

**Architecture Components:**
- `backend/services/onchain_engine.py` - RPC/on-chain engine for wallet enrichment
- `wallet_chain_state` table - tracks RPC enrichment with source attribution
- `backend/routers/arkham.py` - handles Arkham coverage reporting and data source ledger

### Next Priority Action

**Action:** Implement **RPC Source Attribution Completion Pipeline** for Binance and remaining high-volume exchanges

**Rationale:**
1. **Data Gap:** Only 30% of Binance addresses have source attribution (23/76). This is the largest gap among known exchanges.
2. **Architecture Fit:** The existing `wallet_chain_state` table already supports source attribution columns; we just need to populate them.
3. **Business Value:** Complete attribution enables accurate coverage metrics and client reporting.

**Implementation Steps:**

```python
# 1. Extend onchain_engine.py RPC enrichment to include source attribution pass
# 2. Query Binance RPC for remaining 53 addresses with missing attribution
# 3. Match addresses to known Binance wallet patterns (hot wallet, custodial, bridge)
# 4. Update wallet_chain_state.source_attribution column for each match
# 5. Verify by re-running arkham.py coverage report
```

**Verification Command:**
```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\backend\routers\arkham.py --source-ledger
```

This completes the immediate data gap identified in the first backfill while leveraging existing architecture components.
