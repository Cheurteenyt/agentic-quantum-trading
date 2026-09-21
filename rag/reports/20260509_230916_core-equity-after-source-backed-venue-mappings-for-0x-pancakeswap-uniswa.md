# Local Advisor Report

Generated: 2026-05-09T23:09:16

## Question

Core Equity: after source-backed venue mappings for 0x/PancakeSwap/Uniswap/OKX and exact swap rows=23, unknown venue swaps=31. Critique the next safest data priority for Arkham-like manipulation detection. Do not suggest file edits, only analysis.

## Sources

- `backend/routers/arkham.py`
- `backend/services/arkham_tracker.py`
- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Critique: Next Safest Data Priority for Arkham-like Manipulation Detection

## 1. Useful Facts (with source paths)

| Fact | Source |
|------|--------|
| Current `wallet_chain_state` has 267 rows across 5 chains (eth=227, bsc=18, arbitrum=4, base=12, polygon=6) | Memory: project_state.md |
| Label ledger has 461 direct labels + 18 derived labels after initial ETH ingestion | Memory: project_state.md |
| RPC ingestion gate currently allows only "ethereum_recent_blocks" and "bsc_recent_blocks" as safe | Source 3 (backend/routers/arkham.py) |
| Manipulation detection requires "holder/flow baselines" which are not yet safe | Source 3 (backend/routers/arkham.py) |
| `wallet_chain_state` tracks: address kind, contract flag, native USD value, activity tier, risk flags, data quality score, label source evidence, RPC source attribution | Memory: project_state.md |
| Exact swap rows = 23, unknown venue swaps = 31 (from question context) | Question |
| Arkham-like value requires "labels, attribution, and chain-scoped source quality first" | Source 3 (backend/routers/arkham.py) |

## 2. Hypotheses for Codex to Verify

1. **Hypothesis A**: The 31 unknown venue swaps are concentrated in chains with minimal RPC coverage (arbitrum=4, base=12 rows). This suggests unknown swaps may be misattributed to "unknown" venue rather than properly mapped.

2. **Hypothesis B**: Manipulation detection requires at minimum: (a) holder concentration metrics per token, (b) flow velocity baselines per venue, and (c) label confidence propagation from high-confidence entities. These are explicitly listed as "not_safe_yet" in the RPC gate.

3. **Hypothesis C**: The current 227 ETH rows dominate coverage but lack the label-source evidence needed for manipulation attribution. The `label_source_evidence` and `rpc_source_attribution` columns exist but may not be populated for swap-level events.

4. **Hypothesis D**: The 18 derived labels are seed-focused and may not have propagated to swap-level events, creating a gap between entity intelligence and on-chain event attribution.

## 3. Concrete Next Checks (No Edits)

```
1. Query wallet_chain_state for swap-related rows:
   SELECT chain, count(*), sum(data_quality_score) 
   FROM wallet_chain_state 
   WHERE chain IN ('arbitrum','base') 
   GROUP BY chain;

2. Check unknown venue swap distribution:
   - Find which 31 unknown swaps have associated wallet_chain_state entries
   - Verify if those wallets have label_source_evidence populated

3. Verify label propagation depth:
   - Count how many of the 461 labels have associated swap events
   - Check if derived labels (18) have any swap attribution

4. Inspect RPC ingestion timestamps:
   - Compare last ingestion time for eth vs arbitrum/base
   - Unknown swaps may be from stale or incomplete ingestion
```

## 4. Risks / False Positives / Non-goals

| Risk | Description |
|------|-------------|
| **False Positive**: Unknown venue swaps may be legitimate cross-chain bridges, not manipulation | Need to verify bridge contract addresses before flagging |
| **Data Quality**: The 227 ETH rows may have higher quality than 4 arbitrum rows, biasing manipulation scores | Must normalize by chain quality score |
| **Non-Goal**: Manipulation detection cannot work without holder/flow baselines | This is explicitly "not_safe_yet" per source 3 |
| **Attribution Gap**: Derived labels may not have propagated to swap-level events | Requires checking label expansion pipeline |

## 5. Tiny Experiments Codex May Choose to Run

1. **Swap Attribution Audit**: For the 31 unknown venue swaps, trace each to a wallet_chain_state row and check if that wallet has any high-confidence label. If
