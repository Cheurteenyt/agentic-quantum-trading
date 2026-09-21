# Local Advisor Report

Generated: 2026-05-09T23:56:01

## Question

Core Equity priority: all 21 unknown swap routers now have wallet_chain_state but 0 source-backed router evidence. Suggest the safest next read-only/source-backed lane before any label promotion or venue mapping. No edits.

## Sources

- `rag/memory/generated_project_map.md`
- `backend/routers/onchain.py`
- `backend/routers/arkham.py`
- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Swap Router Priority Lane

## Current Situation

Based on the repository context, I can identify the following state:

### Known Facts (from retrieved context):

1. **Wallet Chain State Coverage**: The system has `wallet_chain_state` for 21 unknown swap routers across multiple chains (ethereum 227 rows, bsc 18, arbitrum 4, base 12, polygon 6) [Source 4].

2. **Source-Backed Evidence Gap**: The context explicitly states "0 source-backed router evidence" for these 21 routers, meaning they lack the Arkham-style label evidence bundles that would qualify them for label promotion.

3. **Data Architecture**: The system follows a `Frontend -> API -> Router -> Service -> Data` pattern [Source 1], with `wallet_chain_state` being "observed RPC/explorer state with source attribution" [Source 1].

4. **Safe RPC Ingestion**: The system currently considers `ethereum_recent_blocks` and `bsc_recent_blocks` as "safe now" for RPC ingestion [Source 3].

5. **Not Yet Safe**: The system explicitly lists "full historical archive ingestion" and "cross-chain wallet clustering without confidence scoring" as not yet safe [Source 3].

## What's Missing from Context

To provide a complete answer, I need the following information:

1. **The 21 Router Names**: The context mentions "21 unknown swap routers" but doesn't list their specific identifiers or addresses.

2. **Current Evidence Scores**: I need to know what evidence scores these routers currently have to determine what threshold would qualify them for the next lane.

3. **Label Candidate Pipeline**: The exact flow from `label_candidates` → `label_candidate_evidence` → promotion, including what constitutes "strict admin promotion" criteria.

4. **Source Attribution Details**: What specific RPC/explorer sources are currently attributing data to these 21 routers' `wallet_chain_state` entries.

5. **Recent Data Jobs**: The `data_jobs` audit trail would show what ingestion/enrichment/corroboration has recently occurred for these routers.

6. **Chain Coverage Matrix**: The Arkham-style coverage matrix would show which chains these routers operate on and their coverage depth.

## Safest Next Read-Only Lane (Based on Available Context)

Given the constraints, the safest next step before any label promotion or venue mapping would be:

**RPC Source Quality Verification** — specifically:

1. **Verify chain-scoped source attribution** for each of the 21 routers' `wallet_chain_state` entries to ensure no cross-chain price contamination [Source 1, Source 4].

2. **Run recent-block-only corroboration** using the already-approved `ethereum_recent_blocks` and `bsc_recent_blocks` ingestion pattern [Source 3].

3. **Build minimal evidence bundles** that document:
   - Which RPC source reported the router activity
   - Which explorer API confirmed the wallet addresses
   - The time window of observed activity
   - The data quality score already assigned

4. **Use the Arkham-style coverage report** from `backend/routers/arkham.py` to understand current chain coverage and identify gaps [Source 3].

This approach respects the system's existing safety
