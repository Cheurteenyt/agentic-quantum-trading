# Core Equity AI Agentic Research Watchlist

Last updated: 2026-05-22.

Purpose:
- Track useful public ideas from X/web research about agentic OS, multi-agent workflows, persistent memory, MCP, Hermes, governance and 24/7 automation.
- Use this as product inspiration only. Do not install new agent frameworks into Core Equity without a separate safety/design step.

## Current Research Verdict

The strongest pattern is not "one giant autonomous agent".
The stronger architecture is:
- persistent work graph
- deterministic policy gates
- small specialized agents
- durable memory with write filters
- tool allowlists
- audit receipts
- shadow/paper mode before real actions

This matches Core Equity's direction better than a free-form Hermes/CrewAI swarm.

## Useful Ideas From X Research

### Agent OS Stack

Repeated pattern:
- Memory
- Skills
- Tools/MCP
- Commands
- Multi-agent orchestration
- Hooks/lifecycle automation

Core Equity translation:
- `rag/memory` is durable memory.
- Prompt Manager chooses next safe task.
- Agent OS Lite should own the work graph and audit receipts.
- Codex remains final operator/validator.
- Hermes/Qwen/Helmholtz remain sidecars unless explicitly promoted later.

### Multi-Agent Workflow Roles

Common roles surfaced:
- Architect
- Engineer
- Reviewer
- Optimizer

Core Equity translation:
- Research Agent: finds leads and gaps.
- Data Agent: collects bounded raw data.
- Evidence Agent: grades proofs.
- Policy Agent: blocks unsafe actions.
- Backtest Agent: measures whether a detection would have worked.
- Trade Agent: future-only, blocked until policy/risk/paper trading pass.

### Persistent Memory Warning

Multiple discussions converge on the same warning:
- Memory is useful only if filtered.
- Passive logs make persistent agents worse.
- Skills/playbooks are often better than dumping everything into memory.

Core Equity translation:
- Keep `current_automation_state.md` compact.
- Keep project history separate.
- Store only durable decisions, data counts, blockers and next missions.
- Agent memory writes should be reviewed or schema-bound.

### Hermes Agent

Useful capabilities:
- persistent memory
- skills/workflows
- multi-agent profiles
- local/self-hosted use
- multiple execution backends
- messaging/cron style usage

Core Equity translation:
- Hermes can be useful as a lab/research operator.
- It should not directly write Core Equity DB, labels, mappings, signals or trades.
- Best near-term use: report-only research, documentation summarization, workflow experiments outside the sensitive runtime.

### Governance / Policy

The most important external idea is deterministic governance:
- zero-trust identity
- tool allowlists
- execution sandboxing
- policy enforcement before actions
- SRE/circuit breakers
- audit logs

Core Equity translation:
- Agent OS Lite should become a policy-governed control plane before any 24/7 autonomy.
- Every agent run needs: input scope, allowed tools, allowed tables, max calls, max writes, confirm token if needed, and audit result.
- Trade and client-facing outputs remain disabled until policy/risk/paper trading gates exist.

## Concrete Tools / Projects To Review Later

- Microsoft Agent Governance Toolkit:
  - Policy enforcement, zero-trust identity, execution sandboxing, SRE for autonomous agents.
  - Likely useful as a design reference before Core Equity 24/7 autonomy.
- jpicklyk/task-orchestrator:
  - Persistent work-item graph, dependency tracking, quality gates, actor attribution.
  - Directly relevant to replacing ad-hoc prompts with structured task state.
- leeovery/agentic-workflows:
  - Composable engineering workflows.
  - Useful as inspiration, not a dependency yet.
- AI-company / Claude Code team OS style projects:
  - Useful for seeing dashboards, agent templates and task walls.
  - Risk: too much generic agent theater if copied directly.
- Hermes Agent documentation:
  - Useful for persistent memory, skills and multi-agent profile ideas.
  - Keep separate from Core Equity operator permissions.

## Recommended Product Direction

Next Core Equity agentic step should be:
- build/read a local Agent Control Plane state file or table in read-only design first
- define task graph states: queued, running, blocked, review, done
- define allowed task types: data collection, evidence grading, RAG update, code review, backtest
- define forbidden task types: label write, mapping write, client signal, trade, opt-in
- add audit receipt format before any recurring autonomous run

Do not start with:
- broad 24/7 autonomous browser scraping
- arbitrary Hermes/CrewAI tool access
- direct social media ingestion into evidence
- auto-trading decisions

## Sources Checked

- X search queries:
  - `agentic OS AI agents`
  - `AI agent operating system MCP`
  - `local AI agents 24/7 automation`
  - `CrewAI agentic workflow production`
  - `Hermes agent NousResearch tool use`
  - `Codex Claude Code multi agent workflow`
  - `self improving AI agents RAG memory`
- Web references:
  - Microsoft Agent Governance Toolkit
  - jpicklyk/task-orchestrator
  - Hermes Agent documentation
  - Claude/agent workflow ecosystem references
