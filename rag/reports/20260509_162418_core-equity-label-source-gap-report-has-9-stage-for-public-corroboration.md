# Local Advisor Report

Generated: 2026-05-09T16:24:18

## Question

Core Equity: label-source gap report has 9 stage_for_public_corroboration rows and 2 skip_unlabelled_observation rows. Should next step stage those 9 as label_candidates only, admin-gated and audited, with no trusted promotion? Give concise implementation cautions.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Label-Source Gap Report Rows

## Understanding the Question

The question asks about handling **9 `stage_for_public_corroboration` rows** and **2 `skip_unlabelled_observation` rows** from a label-source gap report. It asks whether to stage the 9 rows as **label_candidates only**, with **admin-gated and audited** access, and **no trusted promotion**.

## What's Missing from Context

The repository context provided does **not** contain:

1. **The label-source gap report schema** - I don't see the database table structure, column definitions, or the exact meaning of these status values.

2. **The gap report generation logic** - The code that produces these 9 and 2 rows is not in the retrieved context.

3. **Existing label promotion policies** - The current workflow for how labels move from candidate → trusted is not documented in the provided snippets.

4. **The `stage_for_public_corroboration` and `skip_unlabelled_observation` status definitions** - These appear to be business logic states that need to be understood in context.

5. **Any existing admin-gating or audit mechanisms** - The context mentions these concepts exist but doesn't show their implementation.

## What I Can Infer (with caveats)

From the project state:
- The system has a **label ledger** with "direct labels" and "derived labels"
- There's a **label expansion** service that derives low/medium confidence labels
- Labels have **confidence levels** and **source attribution**
- The system tracks **label source evidence** in `wallet_chain_state`

## What Needs to Be Retrieved

To answer this question properly, the following context should be retrieved:

```powershell
# 1. Find the gap report generation code
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "Where is label-source gap report generated?" --domain backend

# 2. Find the status enum/constant definitions
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "What are the label status values?" --domain backend

# 3. Find existing label promotion workflow
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "How do labels get promoted to trusted?" --domain backend

# 4. Find admin-gating implementation
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "Where is admin-gating implemented for label endpoints?" --domain backend
```

## Recommendation

**The context is insufficient** to provide a definitive implementation answer. The gap report schema, status definitions, and existing promotion workflow need to be retrieved from the backend codebase before making engineering decisions about how to handle these 9 and 2 rows.

The question requires understanding:
- What makes a row `stage_for_public_corroboration` vs `skip_unlabelled_observation`
- What "public corroboration" means in this system
- Whether admin-gating already exists for label candidates
- How audits are currently
