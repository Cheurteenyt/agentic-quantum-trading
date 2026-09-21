# Hermes Integration Policy - Core Equity

Last updated: 2026-05-15.

## Purpose

Hermes may be introduced into Core Equity only as a read-only analyst and review sidecar first. It can help summarize the project, compare queue states, surface blockers, and draft recommendations. It must not execute product decisions, perform writes, or bypass the existing admin-gated pipeline.

## Current Status

- Hermes Agent is installed separately on drive D: at `D:\hermes-agent`.
- Hermes data/config memory is isolated at `D:\hermes-home`.
- Hermes cache is isolated at `D:\hermes-cache`.
- The launcher is `D:\hermes-agent\hermes-d.ps1`.
- Hermes is not connected to Core Equity runtime writes, providers, scraping, gateways, background services, or database mutation paths.
- Hermes Lab/Safe profile is documented in `rag/memory/hermes_lab_safe_profile.md`.
- Active tool audit shows Hermes is powerful enough to be dangerous around Core Equity if not constrained: web, browser, terminal, file, code execution, skills, memory, delegation, cronjob, and messaging are enabled for CLI use.
- First read-only RAG summary test was attempted on 2026-05-15 and stopped before analysis because no Hermes provider/model was configured. This is not a Core Equity blocker; it means Hermes needs manual model/provider setup before it can produce reports.
- First successful read-only RAG summary was completed on 2026-05-15 through provider `opencode-go`, model `qwen3.5-plus`, using RAG-derived project context only. Hermes correctly identified the current token market stage, disabled write surfaces, and safest next read-only step without touching Core Equity runtime or DB state.

## Orchestration Model

- Codex/GPT-5.5 keeps product direction, final decisions, security validation, and implementation authority.
- Hermes may act as a non-binding analyst/reviewer only.
- RAG memory remains the source of project continuity and current state.
- Spark/Rawls may remain a separate read-only verification sidecar when explicitly requested.
- Spark/Rawls remains the primary sidecar for Core Equity queue/gate verification because it carries the active project context. Hermes is secondary and should be used only for read-only summaries, comparison, or lab experiments unless a separate future policy changes that.
- Any future Hermes output must be treated as advice until Codex validates it against current project state and safety gates.

## Hermes Safe And Lab Profiles

- Hermes Safe Profile: Core Equity-related Hermes use is RAG-only or exported-report-only, preferably with `--toolsets clarify`, one-shot mode, and no repo terminal, file writes, endpoints, DB access, runtime launch, provider/scraping, cron, gateway, browser, MCP, delegation, or messaging.
- Hermes Lab Profile: broader Hermes tool tests may happen only outside Core Equity, preferably in a dedicated lab folder such as `D:\hermes-lab`. Lab work may explore Hermes web/browser/tool behavior, skills, prompts, and model comparisons, but must not touch Core Equity DB, runtime, endpoints, repo writes, or credentials.
- If a Hermes task needs terminal, file, browser, cron, gateway, MCP, or delegation, classify it as Lab by default unless it is explicitly designed as a Core Equity read-only exported-report review.

## Allowed Hermes Roles

- Analyze and summarize RAG memory.
- Summarize docs and project notes.
- Review dry-run or read-only endpoint outputs.
- Compare review queue rows and highlight readiness/blockers.
- Explain CEX/DEX routing separation in human-readable terms.
- Recommend, non-bindingly, whether a row appears ready, needs better source, or should be rejected.
- Draft candidate next `/goal` proposals for human/Codex review.
- Produce read-only pipeline reports for Core Equity.

## Forbidden Hermes Roles

- No database writes.
- No migrations or schema changes.
- No status updates.
- No CEX label creation or promotion.
- No DEX router evidence insertion.
- No DEX venue mapping.
- No trade execution, swaps, wallet orders, or transaction signing.
- No client signals, consent changes, or opt-in creation.
- No provider calls, scraping, browser extraction, or external data collection unless a separate explicit goal allows it.
- No credential, secret, or token handling.
- No backend/frontend/runtime code changes as an autonomous action.
- No gateway/background service connection to Core Equity without a separate integration goal.

## Allowed Sources

- `rag/memory/*.md`.
- `rag/memory/generated_project_map.md`.
- Project docs and readmes.
- Admin read-only endpoints.
- Review queues and contract/schema endpoints only when called with `dry_run=true`.
- Local command outputs explicitly produced for audit by Codex/user.

## Forbidden Sources And Actions

- External providers by default.
- Scraping by default.
- Credentials, secrets, API keys, auth tokens, or private `.env` values.
- Direct SQLite mutation.
- Production-like writes.
- Any action that creates a label, DEX evidence, mapping, trade, wallet order, client signal, or opt-in.

## Required Guardrails

- `dry_run=true` is mandatory for endpoint-based Hermes review.
- Admin tokens remain controlled by Codex/user and must not be stored in Hermes memory.
- Hermes recommendations are non-binding and must be validated before any implementation.
- If Hermes suggests a write, migration, provider call, scraping, credential access, trade, wallet action, or client opt-in, stop and return to Codex/manual review.
- Future write permissions, if ever considered, require a separate explicit product/security design and are not enabled by this policy.
- Hermes must not use its enabled terminal/file/code/cron/delegation tools against Core Equity. Tool availability is not permission.

## First Safe Test

The first safe Hermes test was a read-only summary of the token market pipeline from RAG-derived context only. Expected output was met: a human-readable report of current stage, active gates, ready rows, disabled surfaces, and recommended next read-only step. Expected non-output was also met: no endpoint creation, no DB write, no provider call from Core Equity, no scraping, no label, no router evidence, no mapping, no trade, no wallet order, no client signal, and no opt-in.

If Hermes has no provider/model configured, stop and configure that separately before retrying. Do not add API keys or secrets to RAG, prompts, project docs, or shared logs.

## Core Equity Safety Reminder

The current Core Equity token-market path has intentionally built many gates before any real CEX/DEX action. Hermes must respect that structure. Its role is to make the gates easier to understand, not to skip them.
