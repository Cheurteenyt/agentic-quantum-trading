# Local Advisor Report

Generated: 2026-05-09T19:35:22

## Question

Core Equity priority: implement read-only official protocol source corroboration for DEX venue mapping drafts. Current example: verified component AllowanceHolder should propose 0x Protocol but require official protocol source before admin mapping. Need guardrails/tests, no auto writes.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Priority Implementation

## Summary

The repository context describes **Core Equity** — a private crypto intelligence platform with Arkham-style entity/token/wallet intelligence, on-chain data coverage, and Alpha Lab wallet analysis. The architecture includes:

- **Backend services** (`label_ledger.py`, `label_expansion.py`, `onchain_engine.py`, `seed_ingestion.py`)
- **RPC/on-chain engine** tracking wallet states across multiple chains (ETH, BSC, Arbitrum, Base, Polygon)
- **Label system** with high-confidence and derived labels, entity aliases, and coverage tracking
- **RAG infrastructure** for local AI assistance with Codex (decision-maker) and Qwen (advisor)
- **Admin endpoints** with `CORE_ADMIN_TOKEN` gates for protected label/RPC mutations

## Key Architecture Patterns

1. **Local-first design** — WSL-based venv, SQLite databases, local RPC orchestration
2. **Read-heavy AI workflow** — Qwen as scout/critic, Codex as patcher/verifier
3. **Domain-specific RAG routing** — `--domain data`, `--domain backend`, `--domain frontend`
4. **Quality gates** — `onchain_quality.py` for address classification, `onchain_entities.py` for canonical naming

## Recommended Next Steps

Based on the architecture, the following actions would be most valuable:

```powershell
# 1. Health check before major changes
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py health --domain data

# 2. Verify label ledger state
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What are the current label ledger metrics?" --domain data

# 3. Check RPC coverage baseline
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What is the current RPC wallet coverage across chains?" --domain data

# 4. Evaluate embedding geometry for label data
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\embedding_spectrum.py --domain data --max-chunks 160 --
