# Local Advisor Report

Generated: 2026-05-09T16:17:33

## Question

Core Equity: remaining wallet_chain_state label-source gaps are legacy Binance hot_wallet rows, one Uniswap row, and one client wallet without label. Should the next safe priority create candidates for corroboration, skip client unlabeled wallets, or enrich trusted ledger sources? Short recommendation only.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

## Analysis

Based on the repository context, I can identify the remaining wallet label-source gaps:

1. **Legacy Binance hot_wallet rows** - These are older, established label sources
2. **One Uniswap row** - A single entity that needs verification
3. **One client wallet without label** - Unidentified/unlabeled

## Recommendation

**Create candidates for corroboration** for the next safe priority.

### Reasoning:

1. The **Binance hot_wallet rows** are legacy and likely already well-documented in the label ledger (`backend/data/arkham/label_ledger.db`). These don't need immediate action.

2. The **single Uniswap row** is the highest priority for corroboration because:
   - It's a single point of failure (one row)
   - Uniswap entities should have strong on-chain evidence
   - It's small enough to verify quickly against `wallet_chain_state` RPC data

3. The **unlabeled client wallet** should be **skipped** in the next priority because:
   - Without a label source, there's no external corroboration path
   - Enriching it requires either finding its source first or waiting for label discovery
   - The `onchain_engine.py` service already tracks such wallets but can't independently validate them

4. **Trusted ledger sources** should be prioritized for the Uniswap row specifically, as the architecture shows `label_ledger.py` and `label_expansion.py` already handle trusted source ingestion.

### Action Plan:

```
1. Inspect the Uniswap row in wallet_chain_state (227 ETH rows)
2. Cross-reference against Arkham normalized snapshots
3. Verify against label_ledger.db for existing evidence
4. Only then create corroboration candidates
```

The Uniswap row is the smallest, most verifiable gap with clear external sources available.
