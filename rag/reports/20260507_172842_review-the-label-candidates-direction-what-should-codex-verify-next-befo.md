# Local Advisor Report

Generated: 2026-05-07T17:28:42

## Question

Review the label_candidates direction. What should Codex verify next before promoting any candidate into a trusted label? Focus on evidence, source URLs, dedupe keys, and false positives.

## Sources

- `backend/services/label_ledger.py`
- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`

## Advisor Output

You are Core Equity's local coding RAG assistant.
Answer only from the provided repository context.
If the context is insufficient, say exactly what is missing.
Always cite source paths inline.
Prefer concise, actionable engineering guidance.

Question:
Review the label_candidates direction. What should Codex verify next before promoting any candidate into a trusted label? Focus on evidence, source URLs, dedupe keys, and false positives.

Repository context:
[Source 1] backend/services/label_ledger.py
""",
        (
            chain,
            address,
            row.get("label"),
            row.get("entity"),
            row.get("wallet_type"),
            row.get("confidence") or "medium",
            json.dumps(flags, ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False),
            json.dumps([source], ensure_ascii=False),
            str(row.get("generated_at") or now),
            str(row.get("generated_at") or now),
            now,
        ),
    )
    return True


def _candidate_source_key(row: dict[str, Any]) -> str:
    parts = [
        row.get("source") or "unknown",
        row.get("source_url") or "",
        row.get("file") or "",
        row.get("label") or "",
        row.get("entity") or "",
        row.get("wallet_type") or "",
    ]
    return "|".join(str(part).strip().lower() for part in parts if str(part or "").strip())[:500] or "unknown"


def _stage_label_candidate(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    """Track every observed label proposal without promoting it to trusted intelligence."""
    address = str(row.get("address") or "").strip().lower()
    if not address:
        return False
    chain = _chain_ke

---

[Source 2] backend/services/label_ledger.py
AND address = ? AND source_key = ?",
        (chain, address, source_key),
    ).fetchone()
    if existing:
        candidate_id, old_evidence, seen_count = existing
        conn.execute(
            """
            UPDATE label_candidates
            SET proposed_label = ?, proposed_entity = ?, proposed_wallet_type = ?, confidence = ?,
                source_url = ?, evidence_json = ?, last_seen_at = ?, seen_count = ?
            WHERE id = ?
            """,
            (
                row.get("label"),
                row.get("entity"),
                row.get("wallet_type"),
                row.get("confidence") or "low",
                row.get("source_url"),
                json.dumps(_merge_unique(_json_list(old_evidence), evidence), ensure_ascii=False),
                now,
                int(seen_count or 0) + 1,
                candidate_id,
            ),
        )
        return False

    conn.execute(
        """
        INSERT INTO label_candidates (
            chain, address, proposed_label, proposed_entity, proposed_wallet_type,
            confidence, status, source, source_key, source_url, evidence_json,
            first_seen_at, last_seen_at, seen_count

---

[Source 3] backend/services/label_ledger.py
def get_label_candidates(limit: int = 50, entity: str | None = None, chain: str | None = None) -> dict[str, Any]:
    _init_db()
    where = ["status = 'candidate'"]
    params: list[Any] = []
    if entity:
        where.append("LOWER(proposed_entity) LIKE ?")
        params.append(f"%{entity.lower()}%")
    if chain:
        where.append("chain = ?")
        params.append(_chain_key(chain))
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            f"""
            SELECT chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                   confidence, source, source_url, evidence_json, first_seen_at, last_seen_at, seen_count
            FROM label_candidates
            WHERE {' AND '.join(where)}
            ORDER BY seen_count DESC, last_seen_at DESC
            LIMIT ?
            """,
            [*params, max(1, min(int(limit or 50), 200))],
        ).fetchall()
    finally:
        conn.close()
    return {
        "ok": True,
        "source_policy": "candidate rows are audit-only and are not trusted labels until promoted by explicit verified rules",
        "rows": [
            {
                "chain": row[0],

---

[Source 4] backend/services/label_ledger.py
status TEXT NOT NULL DEFAULT 'candidate',
                source TEXT NOT NULL,
                source_key TEXT NOT NULL,
                source_url TEXT,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                seen_count INTEGER NOT NULL DEFAULT 1,
                UNIQUE (chain, address, source_key)
            );
            CREATE INDEX IF NOT EXISTS idx_label_candidates_status ON label_candidates(status);
            CREATE INDEX IF NOT EXISTS idx_label_candidates_entity ON label_candidates(proposed_entity);
            CREATE INDEX IF NOT EXISTS idx_label_candidates_chain ON label_candidates(chain);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _merge_unique(left: list[Any], right: list[Any]) -> list[Any]:
    seen: set[str] = set()


Durable project memory:
[Memory: project_state.md]
# Core Equity Project State

Last updated: 2026-05-07

## Mission

Core Equity is a private local-first crypto intelligence platform inspired by Arkham, focused on:

- Arkham-style entity/token/wallet intelligence.
- On-chain data coverage through RPC, explorer APIs, Scrapling snapshots, Cielo, Zerion and curated labels.
- Alpha Lab wallet analysis, copy-simulation, manipulation detection and premium client workflows.
- Private client access through a local machine/tunnel model with strict token gates.
- Long coding sessions supported by local RAG, Continue.dev, Codex and Qwen via ik_llama.cpp.

## Current Data Architecture

Primary backend path: `D:\trading-agent\backend`

Important services:

- `backend/services/label_ledger.py`: builds a deduped label ledger from Scrapling normalized Arkham snapshots.
- `backend/services/label_expansion.py`: derives low/medium confidence labels from local on-chain data and Scrapling transfer surfaces.
- `backend/services/seed_ingestion.py`: ingests recent transactions around high-confidence seed labels via explorer APIs.
- `backend/services/onchain_engine.py`: local RPC/on-chain engine for ETH/BSC recent blocks, swaps, wallets, balances and labelled-wallet RPC state.
- `backend/routers/arkham.py`: Arkham coverage report, chain coverage matrix, acquisition plan and data source ledger.
- `backend/routers/onchain.py`: on-chain/admin endpoints, wallet analyzer endpoint and protected label/RPC mutation endpoints.

Important local data:

- `backend/data/arkham/scrapling/normalized/*.json`: normalized Scrapling snapshots from Arkham pages.
- `backend/data/arkham/cache.json`: Arkham/cache holder and address data.
- `backend/data/arkham/label_ledger.db`: high-confidence and derived label ledger.
- `backend/data/onchain/onchain.db`: local on-chain blocks, transactions, swaps, wallets and `wallet_chain_state` RPC enrichment rows.

## Current Coverage Baseline

Most recent known baseline:

- Local labelled addresses: about 649 measured in coverage.
- Label ledger rows: 461 direct labels.
- Derived labels: 18 after initial seed-focused ETH ingestion.
- Labelled-wallet RPC state: started with 6 enriched wallets, then entity-filter enrichment.
- Current entity RPC enrichment examples: Binance 27 RPC wallets, PancakeSwap 20, OKX 12, BlackRock 6, Bitget 4, Polymarket 3, Uniswap 1.
- Latest RPC status sample: `wallet_chain_state` has 73 rows across arbitrum 4, base 4, bsc 16, eth 44 and polygon 5.
- `wallet_chain_state` now tracks address kind, contract flag, native USD value, activity tier, risk flags and data quality score.
- `backend/services/onchain_quality.py` owns address quality classification helpers. Keep `onchain_engine.py` focused on storage/RPC orchestration and move pure helpers out gradually.
- `backend/services/onchain_chains.py` owns RPC URLs, fallbacks, chain aliases, token tracking constants and source labels.
- `backend/services/onchain_coverage.py` owns labelled-vs-RPC entity coverage summaries.
- `backend/services/onchain_entities.py` owns canonical entity aliases for coverage/enrichment. Current aliases intentionally merge only high-confidence naming variants such as `Coinbase`/`Coinbase Prime`, `Binance`/`Binance Wallet`, and `OKX`/`Dex Router (OKX)`; do not use it to invent missing labels.
- `backend/services/onchain_flows.py` owns local transaction flow and counterparty summaries; `onchain_engine.py` keeps the public wrapper for router compatibility.
- `backend/services/onchain_status.py` owns read-only RPC/database status payload assembly.
- `backend/services/SERVICE_CATALOG.md` is the source of truth for current service categories and safe cleanup rules.
- Alpha Lab modules are product-core, not cleanup targets: `alpha_lab.py` owns simulations/risk/sellability and `alpha_wallets.py` owns Cielo/Zerion wallet intelligence, discovery, PnL and copy previews.
- `backend/services/alpha_simulation.py` owns prediction copy and manipulation counterfactual simulation models/engines. `alpha_lab.py` keeps public route-compatible wrappers and injects `analyze_token_risk` for manipulation simulations.
- `backend/services/alpha_risk_models.py` owns Alpha Lab token-risk Pydantic models. The risk/sellability engine still lives in `alpha_lab.py` until the network probes are extracted safely.
- `backend/services/alpha_risk.py` owns pure token-risk scoring. `alpha_lab.py` keeps the public `analyze_token_risk` wrapper and injects `probe_token_sellability` so DexScreener/Honeypot/Scrapling network probes stay isolated.
- `backend/services/alpha_sellability.py` owns DexScreener, Honeypot.is and Scrapling/urllib explorer sellability probes. `alpha_lab.py` re-exports `probe_token_sellability` for router/service compatibility.
- Arkham/Scrapling modules are data-source and normalization assets, not cleanup targets yet: `arkham_scraper.py` and `scrapling_probe.py` should be reduced by extraction only after RPC replacements are verified.
- `entity_intelligence.py` now stores its active DB in `backend/data/entity/entity_labels.db`, with one-time copy fallback from the legacy `services/entity_labels.db`.
- `wallet_analyzer.py` now stores its active DB in `backend/data/wallets/wallet_cache.db`, with one-time copy fallback from the legacy `services/wallet_cache.db`.
- Entity flow surface exists via local transactions only: `/api/onchain/rpc/entity-flow?entity=...`. Values are chain-scoped stored transaction units and must not be treated as normalized USD yet.
- Entity coverage, wallet state and flow surface now share canonical entity aliases, so queries for `Coinbase` include `Coinbase Prime`, and `Binance` includes `Binance Wallet`.
- Priority entity gap reporting exists via `/api/onchain/rpc/entity-gaps`. It classifies entities as `missing_labels`, `needs_rpc_enrichment`, `partial_rpc`, `weak_quality`, or `usable_seed`, using only local labels + RPC state.
- Priority RPC enrichment exists via admin endpoint `POST /api/onchain/rpc/enrich-priority`. It reads the entity-gap report, skips `missing_labels`, prioritizes not-yet-RPC-enriched wallets, and caps work by `limit_per_entity` and `max_entities`.
- Priority enrichment and label-ledger rebuild jobs are audited in the `data_jobs` table and exposed via `GET /api/onchain/rpc/data-jobs`. Alpha Lab localhost admin shows recent job results, including label rows observed/inserted.
- Label candidates now have a dedicated audit-only table in `backend/data/arkham/label_ledger.db`. `label_ledger.build_label_ledger()` stages every observed source proposal into `label_candidates` before trusted label upsert. Candidates are exposed read-only via `GET /api/onchain/labels/candidates` and must not be treated as high-confidence labels until verified/promotion rules are explicit.
- Automatic priority enrichment starts on backend startup when `CORE_AUTO_ENRICH_ENABLED=true` (default true). Before each priority RPC pass it rebuilds the verified local label ledger when `CORE_AUTO_LABEL_BUILD_ENABLED=true` (default true), then enriches labelled priority entities only. It is controlled by `CORE_AUTO_ENRICH_INTERVAL_SECONDS`, `CORE_AUTO_ENRICH_LIMIT_PER_ENTITY`, `CORE_AUTO_ENRICH_MAX_ENTITIES`, `CORE_AUTO_ENRICH_MIN_CONFIDENCE`, `CORE_AUTO_ENRICH_INCLUDE_TOKENS`, `CORE_AUTO_LABEL_BUILD_ENABLED`, and `CORE_AUTO_LABEL_BUILD_LIMIT_FILES`. Admin endpoints `POST /api/onchain/rpc/auto-enrich/start` and `/stop` control it at runtime.
- Verified manual public-label seeds live in `backend/data/arkham/manual/verified_entity_labels.json` and are ingested by `label_ledger.build_label_ledger()`. This file is for traceable public explorer labels only; every row must include source URL/evidence.
- RPC EVM support now covers Ethereum, BSC, Polygon, Base and Arbitrum, plus Solana status only.
- Arkham public reference: about 3.1B labelled addresses.
- Current conclusion: local coverage is partial. Do not run bulk ingestion yet.

Key policy:

- Labels-first before RPC scale.
- Chain-scoped data only. Never merge ETH/BSC/Solana data without explicit chain/source.
- Derived labels are not high-confidence labels until confirmed externally.
- Every row must have source, confidence and deterministic dedupe key. Candidate labels are audit-only by default.

## Security Model

Client read access:

- `CORE_ACCESS_TOKEN`

Admin mutation access:

- `CORE_ADMIN_TOKEN`

Admin-only endpoints include:

- `POST /api/onchain/labels/build`
- `POST /api/onchain/labels/expand`
- `POST /api/onchain/labels/ingest-seeds`
- `GET /api/onchain/labels/candidates` (read-only candidate audit)
- `POST /api/onchain/rpc/enrich-labels`
- `POST /api/onchain/rpc/enrich-priority`
- `GET /api/onchain/rpc/data-jobs`
- `POST /api/onchain/rpc/auto-enrich/start`
- `POST /api/onchain/rpc/auto-enrich/stop`
- `POST /api/onchain/ingest/recent/{chain}`
- `POST /api/onchain/ingest/{chain}/{block_number}`
- `POST /api/onchain/auto-ingest/start`

Alpha Lab admin data ops are visible only on `localhost` or `127.0.0.1`.

## RAG Setup

RAG path: `D:\tradi

---

[Memory: agent_improvement_protocol.md]
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


---

[Memory: rag_operating_playbook.md]
# RAG Operating Playbook

## Daily Commands

Health:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py health
```

Re-index:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\ingest_repo.py
```

Evaluate retrieval quality:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\eval_rag.py
```

Ask with local LLM:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\ask_repo.py "Where is Arkham coverage computed?"
```

Prompt-only for Codex/Continue:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\ask_repo.py "Where is label expansion implemented?" --prompt-only
```

## When To Update Memory

Update `rag/memory/project_state.md` after:

- New durable backend data model.
- New admin/security decision.
- New external data source.
- New RAG/Continue/local model config.
- Major debugging conclusion that should not be rediscovered.

## Retrieval Queries That Should Work Well

- `Where is Arkham coverage computed?`
- `How are labels built and expanded?`
- `Which endpoints require CORE_ADMIN_TOKEN?`
- `How does seed-focused ingestion work?`
- `What is the current data coverage gap versus Arkham?`
- `Where should I patch Alpha Lab wallet analysis?`

## RTX 3070 8GB Settings

Stable defaults:

- Embedding model: `BAAI/bge-small-en-v1.5`
- Chunk size: `512`
- Chunk overlap: `80`
- Embedding batch size: `32`
- Qwen GGUF: Q4_K_M or equivalent 9B quant.
- Context: `12288` if stable; reduce to `8192` if VRAM pressure appears.
- GPU layers: about `30`; reduce if ik_llama.cpp reports memory pressure.
- Parallel: `1` for stability during long sessions.

## Qdrant Mode Guidance

Current mode is Qdrant server at `http://127.0.0.1:6333`, backed by Docker container `core-equity-qdrant`.

Local mode is still acceptable for one process, but server mode is preferred for this project.

Use Qdrant server when:

- Codex, Continue.dev and local Qwen query RAG concurrently.
- Long sessions keep lock files open.
- You see Qdrant local lock/contention issues.

Server flow:

```powershell
D:\trading-agent\rag\scripts\start_qdrant_server.ps1
```

Then set in `rag/config/rag.yaml`:

```yaml
storage:
  qdrant_mode: server
```

Then re-index.

## RAG Evaluation

Golden questions live in `rag/evals/golden_questions.yaml`.

Run the eval after:

- RAG memory changes.
- Chunking or embedding changes.
- Qdrant mode changes.
- Major file moves or architecture changes.

Default target is `85%` pass rate. Treat a drop as a regression before trusting long coding sessions.

## Security Rules

Never index:

- `.env`
- API keys
- wallet private keys
- browser/session cookies
- generated logs with secrets
- raw client credentials

RAG memory should describe secret names, never values.


Additional role instructions:

You are the LOCAL READ-ONLY ADVISOR for Core Equity.
You are Codex's subordinate assistant, not an autonomous coding agent.
Codex is smarter, has authority, and is the only agent allowed to decide, patch and verify.
You are running beside Codex to save tokens and surface useful hypotheses.
Your current specialized role is: data — Focus on labels, RPC coverage, dedupe, chain/source separation and Arkham-like data quality.
Your context mode is: rag.
You do not have direct repository write access.
Treat retrieved snippets as partial evidence, not the whole codebase.
You must never claim you modified files.
You must not provide bulk rewrite instructions.
You must not suggest unsafe data ingestion, secret exposure, or admin bypasses.
You must label every recommendation as one of: VERIFY, LOW-RISK, or DO-NOT-DO.

Return a concise engineering report with exactly these sections:

1. Useful facts, with source paths
2. Hypotheses for Codex to verify
3. Concrete next checks, no edits
4. Risks / false positives / non-goals
5. Tiny experiments Codex may choose to run
6. Confidence and missing context

If the retrieved context is insufficient, say what context should be retrieved next.
