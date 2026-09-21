# Local Advisor Report

Generated: 2026-05-09T16:30:25

## Question

Core Equity: 9 rpc_label_source_gap candidates were staged, labels unchanged. Next step is evidence-only public corroboration. What cautions should we follow before running/adapting corroboration? Concise.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity RPC Label Source Gap & Corroboration Cautions

## Understanding the Current State

From the repository context, I can identify:

1. **Label Architecture** (`backend/services/label_ledger.py`, `label_expansion.py`):
   - Labels are built from Scrapling normalized Arkham snapshots
   - Labels have confidence levels (high-confidence, derived/low-medium confidence)
   - Label ledger stored in `backend/data/arkham/label_ledger.db`

2. **RPC/On-Chain Architecture** (`backend/services/onchain_engine.py`):
   - Tracks `wallet_chain_state` with 267 rows across multiple chains
   - Maintains `wallet_chain_state` with attributes including: label source evidence, RPC source attribution, data quality score, risk flags

3. **Coverage Baseline**:
   - About 649 measured labelled addresses
   - 461 direct labels, 18 derived labels after seed-focused ETH ingestion
   - Multiple entity RPC enrichments (Uniswap 65/65, Bitget 60/60, etc.)

## What's Missing for a Complete Answer

The repository context **does not contain specific information about**:

1. **The exact "9 rpc_label_source_gap candidates"** - I cannot identify which specific candidates these are, their source, or what "staged" means in this context.

2. **The specific "evidence-only public corroboration" process** - The exact methodology, sources, and validation criteria for this corroboration step are not documented in the retrieved context.

3. **Existing caution protocols** - Any documented cautions, gates, or review processes that should be followed before running or adapting corroboration are not present in the context.

## What I Can Infer (With Low Confidence)

Based on general Core Equity architecture patterns:

- **Label promotion** typically requires external confirmation before moving derived labels to high-confidence status
- The architecture suggests a **multi-source verification model** (Arkham + RPC + explorer APIs + Scrapling)
- The `onchain_quality.py` service suggests quality gates exist for address classification

## Request for Additional Context

To provide a precise answer about the cautions for corroboration, I need:

1. **Documentation of the corroboration workflow** - Is this in a separate service, router, or service module?
2. **The "staged" state definition** - What does it mean for candidates to be "staged" with "labels unchanged"?
3. **Evidence-only public corroboration specifics** - What sources, methods, or thresholds apply?
4. **Any existing gates or review processes** for label promotion or corroboration adaptation

## Recommendation

Please provide additional context from:
- `backend/services/*corroboration*.py` (if exists)
- `backend/routers/*corroboration*.py` (if exists)
- Documentation about label promotion workflows
- Any existing tests or specs for the corroboration process

Without this context, any specific cautions I provide would be speculative rather than derived from the actual Core Equity codebase and architecture.
