# Local Advisor Report

Generated: 2026-05-09T19:13:14

## Question

Core Equity next priority: strengthen DEX venue evidence with read-only explorer API contract metadata (contract name/source verified) when API key exists. Existing HTML probe found 0x Allowance Holder. Need guardrails/tests; no mapping writes.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# RAG Context Analysis

I've reviewed the provided repository context for Core Equity. Here's what I found regarding the question about strengthening DEX venue evidence:

## What's Present in Context

1. **Current Architecture** (`project_state.md`):
   - Backend services: `label_ledger.py`, `label_expansion.py`, `seed_ingestion.py`, `onchain_engine.py`
   - Data stores: Arkham scraped snapshots, label ledger DB, onchain DB with `wallet_chain_state`
   - Coverage: ~649 labelled addresses, 461 direct labels, RPC enrichment for major venues (Uniswap, Binance, Coinbase, etc.)

2. **RAG Operations** (`rag_operating_playbook.md`):
   - Commands for health checks, re-indexing, domain-specific queries
   - Domain routing: `--domain data`, `--domain backend`, `--domain frontend`

3. **Model Routing** (`model_routing_guide.md`):
   - Guidance on when to use GPT-5.5 vs local Qwen advisor
   - Recommended presets: `priority-data`, `candidate-labels`, `frontend-alpha`

## What's Missing

The context **does not contain**:

1. **DEX venue evidence implementation details** - No code showing how DEX contract metadata (contract name, source verification status) is currently extracted or stored
2. **Read-only explorer API contract metadata** - No documentation of which explorer APIs are used for contract metadata
3. **API key handling** - No details on how API keys are stored, gated, or validated
4. **HTML probe implementation** - The "0x Allowance Holder" probe mentioned in the question isn't implemented in the provided context
5. **Guardrails/tests** - No existing test suite for DEX metadata extraction
6. **Mapping write architecture** - The question mentions "no mapping writes" but the data model for this isn't shown

## What You Need to Proceed

To answer the question about the "next priority" implementation, I need:

1. **DEX metadata extraction code** - Where contract name/source verification is currently parsed
2. **Explorer API specifications** - Which APIs (CoinGecko, Etherscan, Blockscout) and their rate limits
3. **API key storage location** - Configuration files or environment variables
4. **Existing tests** - Any unit/integration tests for metadata extraction
5. **Database schema** - How contract metadata is stored in `onchain.db` or related stores

---

**Recommendation**: Run `rag_tool.py ask "Where is DEX contract metadata extracted?" --domain data` to surface any existing DEX metadata code, then inspect `backend/services/onchain_engine.py` and `backend/services/seed_ingestion.py` directly for contract metadata handling.
