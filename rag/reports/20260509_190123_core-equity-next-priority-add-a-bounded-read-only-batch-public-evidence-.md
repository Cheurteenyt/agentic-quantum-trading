# Local Advisor Report

Generated: 2026-05-09T19:01:23

## Question

Core Equity next priority: add a bounded read-only batch public evidence scan for top unknown DEX routers. Existing single-router probe extracts explorer hints and never maps. Need minimal guardrails/tests, avoid rate limit and no writes.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

## Analysis

The question asks about **Core Equity's next priority**: implementing a **bounded read-only batch public evidence scan** for top unknown DEX routers. This is a data engineering task, not a code implementation task.

Let me analyze what's needed:

### What the question is asking:
1. **Feature**: Batch scan public evidence for top unknown DEX routers
2. **Constraints**: Read-only, bounded, minimal guardrails/tests, avoid rate limits, no writes
3. **Current state**: Single-router probe extracts explorer hints but never maps

### What's missing from context:
The repository context shows:
- Backend services for labels, on-chain data, Arkham coverage
- RPC state tracking (`wallet_chain_state`)
- Label ledger and coverage metrics
- No explicit mention of DEX router mapping or batch scanning infrastructure

### What needs to be determined:
1. **Source of "top unknown DEX routers"** - Where does the list come from?
2. **What constitutes "public evidence scan"** - Explorer APIs? On-chain patterns?
3. **Bounded implementation** - Rate limiting, batch size, timeout handling
4. **Existing infrastructure** - Is there a single-router probe already?

---

## Answer

**The repository context is insufficient to answer this question with engineering precision.**

### What's missing:

1. **DEX Router Identification Source**
   - No context showing how "top unknown DEX routers" are identified
   - Need to know if this comes from Arkham data, on-chain analysis, or external feeds

2. **Existing Single-Router Probe Implementation**
   - The question mentions "Existing single-router probe extracts explorer hints"
   - No code path or service is shown that implements this probe
   - Cannot verify if this is in `backend/services/` or `backend/routers/`

3. **"Public Evidence Scan" Definition**
   - Unclear what "public evidence" means in this context
   - Is this explorer API calls, on-chain transaction patterns, or swap event analysis?

4. **Bounded Scan Architecture**
   - No information about existing rate limit handling, batch processing, or timeout patterns
   - Cannot determine if `onchain_engine.py` or similar services already have bounded patterns

5. **Mapping Output**
   - The goal is to "never maps" → needs mapping
   - Unclear what the mapping output should be (labels, coverage, RPC state?)

### What Codex should inspect next:

```powershell
# Check for any existing router-related code
D:\trading-agent\backend\search "router" --domain backend

# Inspect onchain_engine.py for existing bounded patterns
D:\trading-agent\backend\search "rate.limit" --domain backend

# Check Arkham router coverage
D:\trading-agent
