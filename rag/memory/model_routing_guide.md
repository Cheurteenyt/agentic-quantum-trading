# Codex Model Routing Guide

This guide helps choose the right model/setup for each Core Equity prompt. It is not a benchmark; it is a practical routing policy for long coding sessions.

## Default Rule

Use the strongest Codex model for decisions, patches and risky architecture. Use the local Qwen model as a read-only advisor through RAG when the task benefits from cheap extra analysis.

## Recommended Routing

### Use GPT-5.5 High / XHigh

Use for:

- Security-sensitive auth, private client access, wallet connection or admin-token changes.
- Data architecture decisions around labels, RPC ingestion, Scrapling adapters and promotion rules.
- Large ambiguous refactors where several files interact.
- Debugging regressions where the root cause is unclear.
- Anything that could corrupt trusted labels, client data or trading/copy automation.

Pattern:

1. Ask Codex to inspect and patch.
2. Optionally run Qwen advisor with a narrow domain.
3. Codex decides what to trust.

### Use GPT-5.5 Medium / GPT-5.4 High

Use for:

- Normal backend/frontend patches with clear scope.
- UI polishing after the data contract is known.
- Adding tests, docs or small endpoints.
- Iterating on Alpha Lab presentation and copy.

Pattern:

1. Use `--domain frontend` or `--domain backend` RAG for context.
2. Patch small.
3. Build/compile.

### Use Local Qwen via ik_llama.cpp

Use for:

- Pre-analysis before Codex edits.
- Critique of a plan.
- Finding likely files and risks.
- Generating read-only reports in `rag/reports/`.
- Comparing options when token cost matters.

Do not use Qwen for:

- Applying edits.
- Final security decisions.
- Promotion of labels.
- Trading/copy execution logic.
- Secrets or client access policy.

Useful commands:

```powershell
# Data architecture advisor
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset priority-data --max-sources 4 --answer-tokens 900 --llm-timeout 90

# Candidate-label safety advisor
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset candidate-labels --max-sources 4 --answer-tokens 900 --llm-timeout 90

# Frontend Alpha Lab clarity advisor
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset frontend-alpha --max-sources 4 --answer-tokens 900 --llm-timeout 90

# Memory-only critique
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset critic --answer-tokens 700 --llm-timeout 60
```

## Domain Routing

- Data/RPC/labels question: use RAG `--domain data`.
- Alpha Lab/dashboard UI question: use RAG `--domain frontend`.
- Endpoint/service implementation question: use RAG `--domain backend`.
- Product state/security policy question: use RAG `--domain memory`.
- Cross-cutting unknown question: use RAG `--domain full`, then narrow.

## Practical Prompt Templates

For Codex:

```text
Inspect the data-domain RAG first, then patch only the minimal backend files. Verify with py_compile and update project_state if this changes architecture.
```

For Qwen advisor:

```text
Run local_advisor with --domain data and role critic. Give Codex verification steps only; no edits.
```

For long sessions:

```text
Use Qwen as scout/critic in parallel for read-only hypotheses. Codex keeps decisions and patches.
```

For RAG compression decisions:

```text
Run embedding_spectrum.py on the relevant domain first.
If the domain is tight_low_deff, summarized memory/context may help.
If the domain is middle_deff, keep hybrid retrieval and only change after evals.
If the domain is spread_high_deff, avoid centroid compression and keep multiple retrieved chunks.
```

## Anti-Patterns

- Do not use a cheap/local model to approve risky writes.
- Do not let Qwen edit through Continue.dev.
- Do not ask broad questions against `full` if a domain is obvious.
- Do not store secrets in RAG memory or reports.
- Do not treat RAG retrieval as proof that data is correct; it only finds code/context.
