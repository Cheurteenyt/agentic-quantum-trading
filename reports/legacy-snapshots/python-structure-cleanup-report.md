# Python Structure Cleanup Report

Updated: 2026-05-23

## Status

The repository structure has been cleaned without advancing the Aster workstream and without launching runtime servers.
`backend/services/onchain_engine.py` is now accepted as a frozen legacy facade,
not a file we should keep micro-extracting forever before product work can
continue.

## Cleaned Areas

- Root runtime artifacts were moved into `archives/`, `logs/`, `reports/`, or `tmp/cleanup-artifacts/`.
- Frontend Python patch files were archived under `scripts/archive/frontend_patches/`.
- Qwen helper scripts now live under `scripts/qwen/` with compatibility wrappers kept at their old paths.
- Security helper scripts now live under `scripts/security/` with compatibility wrappers kept at their old paths.
- MT5 integration now lives under `integrations/mt5/`, with `mt5_bridge.py` kept as a lazy root launcher.
- Trading config now lives under `backend/config/trading.py`, with `trading_config.py` kept as a compatibility wrapper.
- Legacy backend service databases now live under `backend/data/legacy/` instead of `backend/services/`.
- Active top-level directories have README ownership maps.
- Onchain submodules have `backend/services/onchain/README.md` and `REFACTOR_MAP.md`.
- Aster now has a dedicated RAG rulebook:
  `rag/memory/aster_python_structure_rules.md`.

## Current Active Python Surfaces

The root now keeps only compatibility launchers and project metadata. Main active code surfaces are:

- `backend/routers/`: API routes.
- `backend/services/`: backend services and legacy service surfaces.
- `backend/services/onchain/`: modular Core Equity/onchain lanes.
- `backend/services/onchain_engine.py`: large legacy compatibility engine.
- `scripts/`: operator and local helper scripts.
- `integrations/`: external runtime integrations.
- `tests/`: regression tests.

## Remaining Large Legacy Files

These files are intentionally not split blindly because they are likely coupled to route contracts and tests:

- `backend/services/onchain_engine.py`
- `backend/routers/onchain.py`
- `backend/services/onchain/manipulation_reliability.py`
- `backend/services/onchain/cex_listing_prediction.py`
- `backend/services/onchain/behavioral_evidence_bridge.py`
- `backend/services/onchain/transfer_context_plan.py`

Future extraction should be contract-first:

1. Identify a narrow endpoint or function family.
2. Add or reuse tests for that exact contract.
3. Move implementation behind compatibility wrappers.
4. Compile and run targeted tests.
5. Update `backend/services/onchain/REFACTOR_MAP.md`.

## Guardrails

- Do not add new one-off files for a single token or experiment.
- Do not move large runtime modules without compatibility exports.
- Do not put runtime logs, scratch databases, reports, or generated caches in active source directories.
- Do not use Aster as a reason to change Core Equity runtime contracts yet.
- Do not add Aster runtime/product code to `backend/services/onchain_engine.py`.
  Start in `backend/services/onchain/aster/` and expose thin facade wrappers
  only when existing routes/tests require them.
- Do not continue line-count-only micro-extractions from `onchain_engine.py`.
  Extract touched families only.
- Keep data experiments documented in RAG before adding new execution lanes.

## Validation Snapshot

- Active Python compilation passed.
- RAG memory ingestion passed.
- `frontend/src` contains no Python files.
- `backend/services` contains no direct `.db`, `.log`, or `.txt` artifacts.
- No active `__pycache__` directories remain outside ignored runtime/archive areas.
- Active secret-pattern scan returned no matches.
