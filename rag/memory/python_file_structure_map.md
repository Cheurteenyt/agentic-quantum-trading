# Python File Structure Map

Last updated: 2026-05-23.

Purpose: keep Trading Agent clean before adding the Aster data/API suite.

## Current Ownership

- `backend/main.py`: FastAPI application composition.
- `backend/routers/`: HTTP/API surfaces only.
- `backend/services/`: backend service logic and compatibility facades.
- `backend/services/onchain_engine.py`: legacy compatibility facade for the large on-chain engine. Treat it as frozen for new product work; add only thin compatibility wrappers when routers/tests still require the legacy import surface.
- `backend/services/onchain/`: Core Equity on-chain product lanes, evidence lanes, manipulation reliability, CEX/listing research, and transfer/raw evidence modules.
- `backend/services/onchain/core/`: small shared on-chain primitives. Use
  `constants.py` for stable event topics/chains, `paths.py` for default
  on-chain DB/cache/backup paths, `json.py` for JSON/coercion/env helpers,
  `addresses.py` for EVM address validation, and `collections.py` for small
  deterministic helpers, and `numbers.py` for small numeric helpers instead of
  importing `onchain_engine.py` for those values.
- `backend/services/onchain/events/`: pure event/result parsing helpers. Use
  `abi.py` for ERC20 ABI result decoding and `parsers.py` for Swap, ERC20
  Transfer, uint word, hex int, and call-result address parsing instead of
  importing `onchain_engine.py`.
- `backend/services/onchain/dex/`: DEX evidence and event-reader helpers. Use
  `event_reader.py` for local event-reader log previews, topic-address decoding,
  uint word decoding and raw-event candidate construction instead of adding more
  helper code to `onchain_engine.py`. Use `paircreated.py` for bounded
  PairCreated, Blockscout and SQD lookup helpers that do not persist evidence.
  Use `mapping_review.py` for mapping review contract/schema/create/insert
  builders; keep DB patchability through facade injection.
- `backend/services/onchain/aster/`: mandatory home for the next Aster data/API
  suite. New Aster work starts here, follows
  `rag/memory/aster_python_structure_rules.md`, and exposes compatibility
  wrappers from `services.onchain_engine` only if needed.
- `backend/services/onchain/aster/scrapling_label_enrichment_batch.py`:
  strictly read-only `local_snapshots_only` enrichment preview over existing
  normalized Scrapling snapshots. It must not scrape, call external APIs,
  persist evidence, apply labels, create mappings, emit signals, or trade.
- `backend/services/onchain/aster/dexscreener_enrichment_layer.py`: read-only
  DexScreener single-source market enrichment preview for local behavioral
  candidates. It may call DexScreener only for the requested preview and must
  not fall back to Scrapling/RPC, persist evidence, apply labels, create
  mappings, emit signals, or trade.
- `backend/config/`: Python backend configuration objects.
- `agent/`: local agent/OS control helpers.
- `rag/scripts/`: RAG ingestion/query/evaluation scripts.
- `scripts/`: developer utilities and local review/benchmark scripts.
- `scripts/qwen/`: local Qwen sidecar review and benchmark scripts.
- `scripts/security/`: security/access-control validators.
- `scripts/archive/`: old one-off scripts retained only for traceability.
- `tests/`: regression tests. Large on-chain tests can remain here until a later test split.
- `integrations/`: future home for external runtime bridges such as MT5, browser, CEX, and data-provider adapters.
- `integrations/mt5/`: MT5 HTTP bridge implementation.
- `configs/mt5/`: MT5 bridge configuration.
- `archives/`: historical non-runtime artifacts and backups.
- `PROJECT_STRUCTURE.md`: human-readable top-level ownership map.
- `docs/python-structure-cleanup-report.md`: current cleanup report, remaining
  large legacy surfaces, and safe future extraction rules.
- `hermes-cloudflare/`: separate Hermes/Cloudflare sidecar plugin area. Keep it
  isolated from backend runtime services.

## Cleanup Decisions Already Applied

- Frontend source no longer owns Python scripts. Old `patch_alpha.py` and `patch_alpha2.py` were archived under `scripts/archive/frontend_patches/`.
- Trading configuration moved to `backend/config/trading.py`.
- Root `trading_config.py` is now only a compatibility wrapper.
- Local Qwen review scripts moved into `scripts/qwen/`; root `scripts/*.py`
  wrappers remain for compatibility with existing commands and RAG playbooks.
- Tailscale ACL validation moved into `scripts/security/`; root wrapper remains
  for compatibility with security docs.
- Hermes/Cloudflare helper scripts no longer hardcode provider credentials; they
  read Cloudflare/Qwen credentials from environment variables.
- MT5 bridge implementation moved to `integrations/mt5/bridge.py`; root
  `mt5_bridge.py` remains a compatibility launcher for `start_all.bat`.
- MT5 config moved from root `config.json` to `configs/mt5/config.json`.
- Root backup/log/experiment/legacy artifacts were moved to named folders:
  `archives/backups/`, `logs/`, `reports/experiments/`,
  `archives/root-artifacts/`, and `tmp/cleanup-artifacts/`.
- Empty root placeholder dirs `gateway/`, `tools/`, and `skills/` were moved
  under `archives/root-artifacts/empty-dirs/`.
- Added README ownership notes for `configs/`, `data/`, `reports/`, and `logs/`.
- Added README ownership notes for `backend/`, `frontend/`, `tests/`, `docs/`,
  and `agent/`.
- Added local README ownership notes for `backend/routers/`,
  `backend/services/`, and `frontend/src/`.
- Moved backend runtime logs to `logs/backend-runtime/`.
- Moved empty backend scratch DB artifacts to
  `tmp/cleanup-artifacts/backend-empty-dbs/`.
- Moved legacy service DB fallbacks from `backend/services/` to
  `backend/data/legacy/`, while preserving fallback paths in code.
- Aster static references moved into `backend/services/onchain/aster/reference.py`.
- Added `docs/python-structure-cleanup-report.md` to preserve the cleanup
  snapshot and prevent future one-off file drift.
- Extracted stable on-chain constants/default paths into
  `backend/services/onchain/core/`, while keeping `services.onchain_engine`
  compatibility aliases for tests and routers.
- Extracted JSON/coercion/env, EVM address validation, and deterministic
  collection helpers into `backend/services/onchain/core/`.
- Extracted small numeric helpers into `backend/services/onchain/core/numbers.py`.
- Extracted ERC20 ABI result decoders into `backend/services/onchain/events/abi.py`.
- Extracted pure EVM parser helpers into
  `backend/services/onchain/events/parsers.py`, while keeping
  `services.onchain_engine` compatibility aliases for existing callers.
- Extracted pure DEX local event-reader helpers into
  `backend/services/onchain/dex/event_reader.py`, while keeping
  `services.onchain_engine` compatibility aliases for existing callers.
- Extracted bounded PairCreated/Blockscout/SQD lookup helpers into
  `backend/services/onchain/dex/paircreated.py`, while keeping
  `services.onchain_engine` compatibility aliases for existing callers.
- Extracted DEX mapping review contract/schema-plan/create/insert builders into
  `backend/services/onchain/dex/mapping_review.py`, while keeping
  `services.onchain_engine` compatibility wrappers that inject `_get_db` and
  `_table_exists` for tests.
- Moved public Blockscout/SQD endpoint maps into
  `backend/services/onchain/core/constants.py` and nullable hex-int parsing into
  `backend/services/onchain/events/parsers.py`.
- Added `rag/memory/aster_python_structure_rules.md` to freeze
  `onchain_engine.py` as a legacy facade for Aster work and define clean module
  ownership before the Aster suite starts.
- Added the Scrapling local snapshot enrichment batch under
  `backend/services/onchain/aster/`, plus an admin preview endpoint, without
  adding new Aster logic to `onchain_engine.py`.
- Added the DexScreener market enrichment preview under
  `backend/services/onchain/aster/`, plus an admin preview endpoint, without
  adding new Aster logic to `onchain_engine.py`.
- Added `/api/onchain/rpc/dexscreener-enrichment-batch-preview` as a router-only
  aggregate endpoint. It reuses the DexScreener preview function and computes
  stats/top-5 only; no new module logic, DB writes, labels, mappings, signals,
  trades, or opt-ins.

## Next Cleanup Rules

- Do not put real integration code in root launchers. Keep wrappers at root only
  when an existing script such as `start_all.bat` depends on the old command.
- Do not split `onchain_engine.py` with a big-bang refactor.
- Stop micro-extracting `onchain_engine.py` just to reduce line count. It is
  clean enough to serve as a frozen compatibility facade; future extraction
  should happen only for the family being touched by a real product/data task.
- Do not add Aster runtime code directly to `onchain_engine.py`; use
  `backend/services/onchain/aster/` and the Aster RAG rules.
- Do not import `services.onchain_engine` only for stable constants or default
  paths; use `services.onchain.core.constants` or `services.onchain.core.paths`.
- Do not import `services.onchain_engine` only for JSON/coercion/env helpers,
  address validation, or deterministic collection helpers; use
  `services.onchain.core.*`.
- Do not import `services.onchain_engine` only for numeric helpers or ABI result
  decoders; use `services.onchain.core.numbers` or
  `services.onchain.events.abi`.
- Do not import `services.onchain_engine` only for pure log/result parsing; use
  `services.onchain.events.parsers`.
- Prefer small packages with explicit README/ownership notes over ambiguous root scripts.
- Do not add new Qwen/helper review scripts directly under `scripts/`; put them
  under `scripts/qwen/` unless they are generic utilities.
- Do not add security validators directly under `scripts/`; put them under
  `scripts/security/`.
- Do not hardcode API keys or account tokens in sidecar scripts.
