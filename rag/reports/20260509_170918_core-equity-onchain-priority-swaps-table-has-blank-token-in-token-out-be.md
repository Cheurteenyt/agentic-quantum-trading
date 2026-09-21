# Local Advisor Report

Generated: 2026-05-09T17:09:18

## Question

Core Equity onchain priority: swaps table has blank token_in/token_out because ingest_block stores empty strings. Need safe next patch. Should we add UniswapV2 pair token0/token1 resolver plus bounded backfill? What guardrails?

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Swaps Table Blank Token Issue

## Understanding the Problem

Based on the repository context, I can identify the following relevant components:

1. **Data Architecture**: The system uses `backend/data/onchain/onchain.db` for storing blocks, transactions, swaps, and wallets
2. **On-chain Engine**: `backend/services/onchain_engine.py` handles RPC/on-chain orchestration and storage
3. **RPC State**: `wallet_chain_state` tracks wallet metadata including kind, contract flags, activity tier, and risk flags
4. **Label System**: Labels are stored in `backend/data/arkham/label_ledger.db` with confidence levels and source attribution

## What's Missing from Context

The provided context **does not contain**:

1. **The actual `swaps` table schema** - I cannot see the current column definitions for `token_in` and `token_out`
2. **The `ingest_block` function implementation** - I cannot see how it currently stores empty strings
3. **The source of swap data** - Whether this comes from Uniswap V2 events, mempool, or another source
4. **Current ingestion pipeline code** - The exact location where swap events are parsed and inserted

## Recommended Next Steps

To provide a safe, actionable patch, Codex needs to inspect:

```powershell
# 1. Find the swaps table schema
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What is the swaps table schema?" --domain data

# 2. Locate ingest_block implementation
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "Where is ingest_block implemented?" --domain backend

# 3. Find swap event parsing logic
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "How are Uniswap V2 swap events parsed?" --domain backend
```

## Proposed Solution Direction (Pending Verification)

Once the schema and code are verified, the patch would likely involve:

1. **Adding a resolver** that maps `token0`/`token1` from Uniswap V2 Pair contracts to canonical token names/addresses
2. **Bounded backfill** to fix historical rows without re-ingesting all blocks
3. **Guardrails** including:
   - Token address validation against known token registry
   - Fallback to contract address if name lookup fails
   - Logging of unresolved mappings for future resolution

---

**Please run the RAG queries above** so Codex can inspect the actual schema and `ingest_block` implementation before providing a precise patch.
