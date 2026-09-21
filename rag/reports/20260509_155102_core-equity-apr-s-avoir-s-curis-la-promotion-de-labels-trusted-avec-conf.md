# Local Advisor Report

Generated: 2026-05-09T15:51:02

## Question

Core Equity: après avoir sécurisé la promotion de labels trusted avec confirm, backup et audit, quelle est la prochaine priorité data/RPC la plus rentable et la moins risquée? Réponds en plan court, sans proposer de modifier directement les fichiers.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

Based on the repository context, here is the short-term plan for the next profitable, low-risk data/RPC priority:

### Analysis

**Current State:**
- Label promotion pipeline is secured (confirm, backup, audit) per `project_state.md`
- RPC coverage is active with `wallet_chain_state` tracking 267 rows across 5 chains
- Entity RPC enrichment shows high completion rates (e.g., Uniswap 65/65, Coinbase 2/2)
- `onchain_engine.py` handles storage/RPC orchestration; `onchain_entities.py` manages canonical aliases

**Next Priority:**
The most profitable, low-risk extension is **RPC source attribution enrichment** for the existing `wallet_chain_state` table.

### Short-Term Plan

**1. Enrich RPC Source Attribution**
- Add `rpc_source_attribution` column to `wallet_chain_state` (if not present)
- Track which RPC provider contributed each wallet's data (Alchemy, Infura, public RPCs)
- Enables quality scoring per source, reducing blind reliance on single providers

**2. Source Quality Scoring**
- Use existing `onchain_quality.py` helpers to score RPC reliability
- Flag wallets where multiple RPCs agree vs. single-source data
- Lower risk: reads existing quality logic; no new ingestion

**3. Coverage Gap Analysis**
- Query `onchain_coverage.py` logic to find chains with <80% label coverage
- Prioritize RPC fallbacks for under-covered chains (e.g., Arbitrum, Polygon)
- Low risk: analytical only; no schema changes required

**4. Entity Alias Verification**
- Use `onchain_entities.py` to verify canonical names for top 50 labelled wallets
- Resolve naming variants (e.g., "Coinbase Prime" → "Coinbase")
- Improves downstream label matching without changing ingestion

**5. Incremental Verification**
- Run `py_compile` on modified backend files
- Query `wallet_chain_state` directly via WSL venv to confirm new columns
- Use `rag_tool.py ask --domain data` to verify architecture alignment

### Why This Is Low Risk
- Operates on existing `wallet_chain_state` schema (minimal changes)
- Leverages existing quality and coverage services
- No new data ingestion or label promotion logic
- Improves data provenance without altering core ingestion

### Verification Steps
1. Confirm `wallet_chain_state` schema via direct DB query
2. Test RPC attribution logic against existing 267 rows
3. Validate coverage gaps using `onchain_coverage.py` helpers
4. Ensure no impact to existing label promotion pipeline

This plan extends the existing data architecture without introducing new ingestion risks or altering the trusted label promotion flow.
