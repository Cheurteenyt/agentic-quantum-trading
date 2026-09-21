# Agent Improvement Protocol

This project can use AI-agent self-improvement, but only as a controlled engineering loop.

## Non-Negotiable Rule

No hidden autonomous modification.

An agent may analyze, propose, patch and test, but it must not silently rewrite project behavior, security policy, data ingestion scope or production-facing logic.

## Safe Improvement Loop

1. Observe

   Collect facts from code, tests, logs, coverage metrics and RAG memory.

2. Diagnose

   State the concrete issue, affected files and risk.

3. Propose

   Produce a small scoped improvement with expected impact and rollback path.

4. Patch

   Modify only the minimal files required.

5. Verify

   Run the narrowest relevant tests first. For this repo, prefer:

   - `python -m py_compile` for changed backend files.
   - Direct service calls with WSL venv.
   - `npm run build` for frontend changes.
   - RAG re-index after RAG/memory/code architecture changes.

6. Record

   Update `rag/memory/project_state.md` or a more specific memory file when a durable decision is made.

## What Agents May Improve Automatically

Agents may propose or patch:

- Documentation and RAG memory.
- Small source-trace improvements.
- Safer defaults.
- Tests for already-fixed bugs.
- Type definitions and UI state rendering.
- Data coverage visibility.
- Explicit admin gates around mutation endpoints.

## What Requires Extra Caution

Agents must pause or keep changes very small for:

- Authentication, authorization and token handling.
- Private tunnel/client access behavior.
- Data ingestion volume increases.
- Trading/copy-trading execution.
- Wallet signing or transaction submission.
- Anything that could leak API keys or client data.

## What Is Forbidden

- Running background daemons without explicit request.
- Bulk chain backfills without a bounded plan.
- Turning derived labels into high-confidence labels without external confirmation.
- Giving clients access to admin endpoints.
- Writing secrets into code, docs or RAG memory.
- Auto-executing trades or copy actions.

## Evaluation Checklist

Before accepting an agent improvement, answer:

- Did it reduce ambiguity or risk?
- Did it preserve chain/source separation?
- Did it keep raw data separate from intelligence?
- Did it avoid secret exposure?
- Is the test result recorded?
- Is the change reversible?

## Recommended Agent Roles

Codex:

- Best for repository edits, architectural patches, security-sensitive changes and final verification.

Local Qwen through Continue.dev:

- Best for local code search, summarization, draft refactors, UI copy, exploratory questions and low-risk suggestions.
- Must run as a read-only advisor when used in parallel with Codex.
- Should write reports into `rag/reports/` via `rag/scripts/local_advisor.py`, not patch repository files.
- Codex reviews advisor reports, decides what is valid, then performs scoped edits and verification.
- Recommended roles: `data`, `security`, `critic`, `planner`, `frontend`, `scout`.
- Recommended daily mode: `--context-mode rag --max-sources 4`, which limits Qwen to a few retrieved snippets plus durable memory.
- Use `--context-mode memory` for higher isolation and `--context-mode task-only` when Qwen should only critique a Codex-written brief.

RAG:

- Best for recovering project state, file locations, decisions, endpoints and known pitfalls.

Future multi-agent mode:

- Use one agent for backend/data, one for frontend/UI, one for security/review.
- Never let multiple agents write the same files at the same time.
