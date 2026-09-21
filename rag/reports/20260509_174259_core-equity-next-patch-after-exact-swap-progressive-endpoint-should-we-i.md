# Local Advisor Report

Generated: 2026-05-09T17:42:59

## Question

Core Equity next patch after exact-swap-progressive endpoint: should we integrate it into auto-enrich idle loop? Need safe bounded automation, no labels, no client execution. Give concrete guardrails and tests.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Next Patch After Exact-Swap-Progressive Endpoint

## Context Assessment

The provided repository context contains:
- Project state documentation (data architecture, coverage baselines, RPC status)
- Agent improvement protocol and RAG operating playbook
- Model routing guidance for Codex/Qwen workflows

**What's missing:** Any specific mention of an "exact-swap-progressive endpoint" or its associated patch.

## What I Need From You

To provide concrete guardrails and tests for integrating this endpoint into the auto-enrich idle loop, please provide:

1. **The endpoint specification** - What does "exact-swap-progressive" compute? What are its inputs/outputs?

2. **The existing patch** - What code changes were made for this endpoint? (file paths, function names, data contracts)

3. **The auto-enrich idle loop** - Where is this implemented? What is its current architecture?

4. **The integration question** - Specifically: what does "safe bounded automation" mean in this context? What are the constraints?

## What I Can Infer From Existing Architecture

Based on the repository context, I can reasonably infer:

- The backend uses FastAPI with services in `backend/services/` and routers in `backend/routers/`
- Data storage uses SQLite databases (`label_ledger.db`, `onchain.db`, `wallet_chain_state`)
- The "idle loop" likely refers to periodic background enrichment of wallet/entity data
- "Safe bounded automation" suggests limiting: batch sizes, frequency, resource usage, and rollback capability
- The architecture emphasizes separation between raw data and intelligence/derived labels

## Request

Please provide the missing context about the exact-swap-progressive endpoint patch. Once I have:
- The endpoint's purpose and data contract
- The existing implementation location
- The specific integration question

I can then provide concrete engineering guidance on:
- Safe integration into the auto-enrich idle loop
- Bounded automation guardrails
- Test strategy (unit, integration, regression)
- How to preserve the existing architecture principles (data/intelligence separation, admin gates, etc.)
