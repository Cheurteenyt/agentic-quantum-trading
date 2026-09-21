# Local Advisor Report

Generated: 2026-05-09T19:21:00

## Question

Core Equity next priority: add no-key Blockscout address metadata fallback to DEX venue public evidence when Etherscan API key is missing. Need read-only guardrails/tests.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Next Priority

Based on the repository context, I can identify the following:

## Current Architecture State

**Label & Coverage System:**
- `backend/services/label_ledger.py` builds a deduped label ledger from Scrapling normalized Arkham snapshots
- `backend/services/label_expansion.py` derives low/medium confidence labels from local on-chain data and Scrapling transfer surfaces
- Label ledger currently has 461 direct labels with 18 derived labels after seed-focused ETH ingestion
- Coverage baseline shows ~649 measured labeled addresses

**RPC & On-Chain Engine:**
- `backend/services/onchain_engine.py` handles local RPC/on-chain engine for ETH/BSC recent blocks, swaps, wallets, balances and labelled-wallet RPC state
- `wallet_chain_state` table tracks 267 rows across multiple chains (eth 227, bsc 18, base 12, arbitrum 4, polygon 6)
- Each row includes address kind, contract flag, native USD value, activity tier, risk flags, data quality score, label source evidence, and RPC source attribution

**Arkham Coverage:**
- `backend/routers/arkham.py` handles Arkham coverage report, chain coverage matrix, acquisition plan and data source ledger
- Current baseline shows about 649 measured labeled addresses with 461 direct label ledger rows

## What's Missing From Context

To fully address the "no-key Blockscout address metadata fallback" priority, I need:

1. **Current Etherscan API key usage patterns** - How is the API key currently stored, rate-limited, and used for address metadata?

2. **Blockscout API structure** - The exact response schema for address metadata endpoints that would be used as a fallback

3. **Existing metadata storage schema** - Where and how is address metadata currently stored in `wallet_chain_state` or related tables

4. **Rate limiting and caching strategy** - How the system currently handles API quotas and caching for Etherscan

5. **Test infrastructure** - Existing test patterns for API fallback logic and read-only guardrails

6. **Configuration patterns** - How API keys are configured and whether a similar pattern exists for optional fallback keys

## Recommended Next Steps for Codex

1. Inspect `backend/services/onchain_engine.py` for existing
