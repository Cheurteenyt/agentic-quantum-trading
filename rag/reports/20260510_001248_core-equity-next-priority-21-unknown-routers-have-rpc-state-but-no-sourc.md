# Local Advisor Report

Generated: 2026-05-10T00:12:48

## Question

Core Equity next priority: 21 unknown routers have RPC state but no source evidence; Transit BSC is blocked because official docs do not list exact chain/address. Suggest safest read-only official-source review queue design before any admin mapping. No edits.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/generated_project_map.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Core Equity Next Priority Analysis

## Summary

Based on the repository context, the two priorities are:

1. **21 unknown routers** - Routers with RPC state but no source evidence
2. **Transit BSC** - Blocked because official docs don't list exact chain/address

---

## Detailed Analysis

### Priority 1: 21 Unknown Routers

**What's happening:**
- These routers have RPC state populated but lack source attribution
- They appear in `wallet_chain_state` but cannot be traced to Arkham labels, RPC observations, or trusted sources
- This creates a gap in the data provenance chain

**Verification from context:**
- Source 1 confirms `wallet_chain_state` tracks "source attribution" and "label source evidence"
- Source 1 shows the audit tracks "missing attribution" as a quality metric
- Source 3 mentions `wallet_chain_state` has "risk flags" and "data quality score"

**Safest read-only review queue design:**

```
┌─────────────────────────────────────────────────────────────┐
│  Router Unknown Audit Queue (Read-Only)                      │
├─────────────────────────────────────────────────────────────┤
│ 1. Query: /api/onchain/rpc/wallet-state-audit                │
│    - Filter: rows with missing_source_attribution=true       │
│    - Limit: 21 (the unknown routers)                          │
│    - Read-only, no mutations                                  │
├─────────────────────────────────────────────────────────────┤
│ 2. For each router, call:                                    │
│    GET /api/onchain/rpc/wallet-source?address=<addr>         │
│    - Verifies if any source chain exists                     │
│    - Returns attribution chain if found                      │
├─────────────────────────────────────────────────────────────┤
│ 3. Cross-reference with:                                    │
│    GET /api/onchain/rpc/entity-gaps                         │
│    - Check if these routers appear as "needs_rpc_enrichment" │
│    - No edits, just classification                           │
├─────────────────────────────────────────────────────────────┤
│ 4. Validate against coverage metrics:                        │
│    GET /api/onchain/rpc/entity-coverage                      │
│    - Check strict_labelled_wallets count                     │
│    - Verify these 21 are in legacy_or_unverified             │
└─────────────────────────────────────────────────────────────┘
```

**Key endpoints to use (all read-only):**
- `/api/onchain/rpc/wallet-state-audit` - Audit with missing attribution filter
- `/api/onchain/rpc/wallet-source` - Source chain verification
- `/api/onchain/rpc/entity-gaps` - Gap classification
- `/api/onchain/rpc/entity-coverage` - Coverage metrics
- `/api/onchain/labels/candidates/evidence` - Evidence bundles

---

### Priority 2: Transit BSC Blocked

**What's happening:**
- Official documentation doesn't list the exact chain ID and address for Transit BSC
- This blocks proper source attribution and label promotion
- The system requires exact chain/address for trusted source recognition

**
