# Local Advisor Report

Generated: 2026-05-09T16:48:04

## Question

Core Equity priority: after rpc_label_source_gap corroboration, 9 candidates still need_more_evidence mainly missing_source_url and strict_requires_entity_source_url. Suggest safest next code step, evidence-only, no trusted label promotion.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

## Analysis

Based on the repository context, I need to identify the safest next code step for the 9 candidates that still need more evidence after `rpc_label_source_gap` corroboration. These candidates are missing `source_url` and have `strict_requires_entity_source_url` requirements.

### Key Context from Repository:

1. **Label Architecture** (`backend/services/label_ledger.py`, `backend/services/label_expansion.py`):
   - Builds deduped label ledger from Scrapling normalized Arkham snapshots
   - Derives low/medium confidence labels from local on-chain data and Scrapling transfer surfaces

2. **RPC/On-Chain Engine** (`backend/services/onchain_engine.py`):
   - Handles RPC enrichment with `wallet_chain_state` tracking
   - Stores address kind, contract flag, native USD value, activity tier, risk flags, data quality score, label source evidence, and RPC source attribution

3. **Current State** (`project_state.md`):
   - Label ledger has 461 direct labels + 18 derived labels
   - `wallet_chain_state` has 267 rows across multiple chains
   - Quality classification helpers exist in `backend/services/onchain_quality.py`

4. **Agent Protocol** (`agent_improvement_protocol.md`):
   - No hidden autonomous modification
   - Must preserve chain/source separation
   - Keep raw data separate from intelligence
   - Avoid secret exposure

### Recommended Next Code Step:

**Implement a "source_url_fallback_enrichment" pass in `backend/services/label_expansion.py`** that:

1. **For each of the 9 candidates**, check if their entity has a canonical source URL in `backend/services/onchain_entities.py` (the canonical entity aliases file)

2. **If canonical URL exists**, backfill the `source_url` field in the label ledger with the canonical URL, marking it as "backfilled" evidence type

3. **If canonical URL missing**, query the RPC `wallet_chain_state` table for any existing source_url attribution for that wallet address, and if found, use it as fallback

4. **Only after source_url is populated**, attempt to find the Arkham page URL by:
   - Checking `backend/data/arkham/cache.json` for cached page URLs
   - If found, record the Arkham page as the primary source_url

5. **Do NOT promote any of these 9 candidates to high-confidence** — only use this to satisfy the `strict_requires_entity_source_url` requirement

### Why This Is Safest:

- **Evidence-only**: Uses existing canonical entity data and cached Arkham pages
- **No trusted label promotion**: Only backfills missing source_url, doesn't change confidence
- **Preserves separation**: Keeps raw source URLs separate from intelligence/labels
- **Reversible**: Can be rolled back without affecting label confidence
- **Uses existing infrastructure**: Leverages `onchain_entities.py` and `cache.json` that are already trusted

### Verification Steps for Codex:

```powershell
# 1. Check canonical entity coverage
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What canonical entity aliases exist?" --domain data

# 2. Verify cache
