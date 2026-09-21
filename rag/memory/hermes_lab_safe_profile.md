# Hermes Lab Safe Profile - Core Equity

## Management Map Pointer

- Compact agent/control source of truth: `rag/memory/core_equity_management_map.md`.
- This file remains the detailed Hermes boundary. The management map decides the broader Core Equity role hierarchy.

This document defines how Hermes Agent may be used around Core Equity without becoming an operator on the project. Hermes is useful because it has broad tools and a self-improvement loop, but those same capabilities make it unsafe to connect directly to Core Equity writes or runtime surfaces.

## Current Hermes Audit

- Installed Hermes version: `v0.13.0`.
- Hermes home/config: `D:\hermes-home`.
- Hermes install: `D:\hermes-agent`.
- Local model default: `Qwen3.5-9B-UD-Q4_K_XL` through `http://127.0.0.1:8080/v1`.
- Cloud test provider available: `opencode-go` with model `qwen3.5-plus`.
- Gateway service: stopped.
- Scheduled Hermes jobs: zero.
- Active Hermes sessions: zero at audit time.
- Hermes terminal backend: local, sudo disabled.
- Enabled CLI toolsets at audit time: web, browser, terminal, file, code_execution, vision, image_gen, tts, skills, todo, memory, session_search, clarify, delegation, cronjob, messaging, computer_use.
- Disabled CLI toolsets at audit time: video, video_gen, moa, homeassistant, spotify, yuanbao.

## Core Equity Rule

Hermes is not a Core Equity execution agent. It may help think, compare, summarize, and test prompts, but it must not operate the product pipeline.

For Core Equity, Spark/Rawls remains the primary read-only verification sidecar because it already carries the project-specific gate context. Codex/GPT-5.5 keeps direction, safety validation, implementation, and final decisions.

## Hermes Safe Profile

Use this profile for anything related to Core Equity state, queues, RAG, token market, CEX/DEX routing, trading safety, or client consent.

Allowed:

- Read RAG-derived summaries included in the prompt.
- Read exported docs or reports explicitly prepared for Hermes.
- Produce short project-level reports.
- Compare two written plans or summaries.
- Surface risks, blockers, missing gates, and unclear wording.
- Recommend a next read-only step.
- Use `clarify` only when a toolset is needed.

Forbidden:

- No repository terminal access.
- No file writes.
- No direct DB reads or writes.
- No endpoint calls.
- No backend/frontend runtime launch.
- No migrations or schema changes.
- No status updates.
- No CEX labels.
- No DEX router evidence inserts.
- No DEX mappings.
- No trades, swaps, wallet orders, transaction signing, or order preparation.
- No client signals, client consent changes, or opt-ins.
- No provider calls for Core Equity market data.
- No scraping for Core Equity evidence.
- No cron, gateway, messaging, MCP, delegation, browser, terminal, file, or code execution against Core Equity.

Recommended command shape:

```powershell
powershell -ExecutionPolicy Bypass -File D:\hermes-agent\hermes-d.ps1 chat --ignore-rules --provider opencode-go --model qwen3.5-plus --toolsets clarify --max-turns 1 --source tool -Q -q "<RAG-only prompt>"
```

## Hermes Lab Profile

Use this profile only outside the Core Equity runtime and DB. It is for learning Hermes itself, testing tools, comparing models, exploring Nous/Hermes docs, and building non-production skills or prompts.

Allowed in the lab:

- Web and browser research about Hermes, Nous, local models, tooling, and agent architecture.
- Prompt experiments.
- Skill experiments in a separate sandbox or Hermes-owned directory.
- Local model comparison reports.
- Non-Core-Equity file experiments inside a dedicated lab folder.
- Reports about how Hermes tools behave.

Still forbidden in the lab:

- No Core Equity DB access.
- No Core Equity runtime launch.
- No Core Equity endpoint calls.
- No Core Equity repo file writes.
- No credentials in prompts, RAG, docs, reports, or logs.
- No background cron or gateway connected to Core Equity.
- No external provider or scraping path that claims to create Core Equity evidence.

Suggested lab boundary:

- Lab folder: `D:\hermes-lab`.
- Hermes install folder remains: `D:\hermes-agent`.
- Hermes home remains: `D:\hermes-home`.
- Core Equity project remains: `D:\trading-agent`, read-only from Hermes unless a separate future policy changes that.

## When To Use Which Agent

- Use Codex/GPT-5.5 for product direction, implementation, final validation, and safety decisions.
- Use Spark/Rawls for Core Equity verification sidecar work, especially queue gates, parent-chain checks, dedupe/source/JSON drift, and CEX/DEX safety.
- Use Hermes Safe for occasional read-only RAG summaries or external second-opinion reports.
- Use Hermes Lab for experimenting with Hermes capabilities outside the sensitive Core Equity path.

## Current Recommendation

Do not expand Hermes permissions for Core Equity yet. The next productive use is either:

- Continue Core Equity with Spark/Rawls on `final handoff target decision preview read-only`.
- Or run a Hermes Lab-only experiment that studies Hermes tools and self-improvement outside Core Equity.

Hermes should earn trust in the lab before any deeper project integration is considered.
