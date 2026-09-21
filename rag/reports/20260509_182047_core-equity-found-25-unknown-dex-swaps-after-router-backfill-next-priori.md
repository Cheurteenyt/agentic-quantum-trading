# Local Advisor Report

Generated: 2026-05-09T18:20:47

## Question

Core Equity found 25 Unknown DEX swaps after router backfill. Next priority: create read-only venue discovery report grouping unknown routers/pools before adding labels. Need guardrails/tests and avoid hardcoding rumors like RAVE/Aster.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# RAG Context Analysis

I've reviewed the provided repository context for Core Equity. Here's what I found regarding the question about unknown DEX swaps and venue discovery:

## What's Present in Context

1. **Backend services** that handle label ingestion, expansion, and on-chain data:
   - `backend/services/label_ledger.py` - builds deduped label ledger from Scrapling snapshots
   - `backend/services/label_expansion.py` - derives low/medium confidence labels
   - `backend/services/onchain_engine.py` - local RPC/on-chain engine for blocks, swaps, wallets

2. **Data architecture**:
   - `backend/data/arkham/scrapling/normalized/*.json` - normalized Arkham snapshots
   - `backend/data/onchain/onchain.db` - local on-chain database with wallet_chain_state

3. **Existing coverage metrics** tracked in `project_state.md`:
   - Labelled addresses (~649)
   - Label ledger rows (461 direct, 18 derived)
   - RPC wallet coverage per exchange/entity

## What's Missing

The context **does not contain**:

1. **The actual 25 unknown DEX swap records** - their source, router addresses, pool contracts, or swap details
2. **The router backfill process** - how these swaps were discovered and what "backfill" means in this context
3. **Existing venue discovery code** - any modules that already group routers/pools or create reports
4. **Label promotion logic** - how labels move from unknown to labeled status
5. **The specific "rumor" guardrails** mentioned (RAVE/Aster) - any existing filtering or confidence thresholds

## What Needs to Be Built

Based on the question, the following would need to be created:

1. **Read-only venue discovery report** that:
   - Groups unknown routers by similarity (address prefix, contract family, swap patterns)
   - Groups unknown pools by chain, token pairs, or volume clustering
   - Outputs a structured report without modifying production data

2. **Guardrails and tests** for:
   - Preventing hardcoded rumors from entering label pipelines
   - Ensuring unknown entities have minimum evidence before label consideration
   - Verifying router/pool grouping logic

3. **Integration points** with existing services:
   - `label_ledger.py` for feeding discovered entities
   - `onchain_engine.py` for RPC verification
   - `label_expansion.py` for potential future label derivation

## Recommendation

To proceed with engineering this feature, I would need access to:

1. The actual swap data records (or a sample)
2. Existing report generation code in the repository
3. The label promotion/conversion pipeline architecture
4. Any existing "rumor detection" or confidence scoring logic

Would you like me to help design the venue discovery report structure, or do you have access to the swap data that needs to be analyzed?
