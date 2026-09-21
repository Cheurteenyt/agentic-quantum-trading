# Local Advisor Report

Generated: 2026-05-09T17:32:41

## Question

Core Equity next patch: exact swap ingestion works for one BSC block. Need automate progressive safe multi-chain ingestion without bulk scan or client execution. What should Codex implement next?

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Core Equity Next Patch Analysis

## Current Situation

Based on the repository context, Core Equity has:

1. **Working single-block swap ingestion** - The `onchain_engine.py` service successfully processes one BSC block with swap data
2. **Multi-chain architecture** - Already supports ETH, BSC, and other chains via `wallet_chain_state` tracking
3. **Label-ledger pipeline** - Built around `label_ledger.py`, `label_expansion.py`, and `seed_ingestion.py` services
4. **RPC-based data model** - Uses `wallet_chain_state` with entity attribution and quality scoring

## What's Missing for Progressive Multi-Chain Ingestion

The architecture lacks a **bounded, progressive ingestion loop** that can:
- Process multiple blocks across chains without bulk scanning
- Maintain safety guarantees per the Agent Improvement Protocol
- Avoid client execution while staying RPC-first

## Recommended Implementation

### 1. Create `backend/services/progressive_ingestion.py`

```python
"""
Progressive multi-chain swap ingestion.
Bounded, RPC-only, no bulk scans.
"""
```

**Key design decisions:**

| Concern | Solution |
|---------|----------|
| **Bounded scope** | Process N blocks per chain per run (configurable, default 10) |
| **Safety** | Per-chain rate limits via `onchain_chains.py` RPC config |
| **No bulk scan** | Use explorer APIs for recent blocks only (already in `seed_ingestion.py`) |
| **No client execution** | Pure RPC + explorer API calls; verify via `onchain_quality.py` |

### 2. Add Progress Tracking to `wallet_chain_state`

Extend the existing `wallet_chain_state` model with:
- `ingestion_batch_id` - Groups progressive runs
- `block_range` - Tracks which blocks were processed
- `source_attribution` - Links to explorer API calls

### 3. Verification Steps for Codex

```powershell
# 1. Verify current ingestion pattern
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "How are recent blocks ingested?" --domain data

# 2. Check seed_ingestion.py for existing bounded patterns
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What limits seed_ingestion.py uses?" --domain backend

# 3. Verify RPC config exists
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "Where are RPC URLs configured?" --domain backend
```

### 4. Expected Architecture Impact

- **Minimal**: Reuses existing `onchain_chains.py` RPC patterns
- **Safe**: Follows Agent Improvement Protocol (bounded, reversible)
- **Consistent**: Extends `wallet_chain_state` model already in use

## Confidence: HIGH

The architecture already supports this pattern through `seed_ingestion.py`'s bounded approach. The next patch should simply generalize that pattern to progressive multi-chain swap ingestion without bulk scans.
