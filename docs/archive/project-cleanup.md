# Project Cleanup Notes

Date: 2026-05-06

## What changed

The repository root had many one-off patch, debug, screenshot, HTML, and probe files from live debugging.
They were moved, not deleted, to:

```text
D:\trading-agent\tmp\root-junk-archive-20260506-183837
```

Backend debug logs, one-off test scripts, a stale `main.py.bak`, and an accidental nested `D:`-style folder were moved, not deleted, to:

```text
D:\trading-agent\tmp\backend-junk-archive-20260506-191217
```

Duplicate or broken Python environments were moved, not deleted, to:

```text
D:\trading-agent\tmp\venv-archive-20260506-214225
```

Active Python environments kept:
- `D:\trading-agent\.venv.wsl` for WSL backend/runtime
- `D:\trading-agent\.venv-win` for Windows backend utilities
- `D:\trading-agent\.venv-rag` for LlamaIndex/RAG/Continue tooling

## Why

The root should stay readable:
- application code in `backend\`, `frontend\`, `gateway\`, `agent\`
- project docs in `docs\`
- RAG system in `rag\`
- operational scripts in `scripts\`

Scratch files should stay under `tmp\` or `logs\`.

## Gitignore policy

The `.gitignore` now excludes common root scratch files:
- `_*.py`, `_*.js`, `_*.html`, `_*.png`
- `fix_*.py`, `patch_*.py`, `test_*.py`
- screenshots, vision dumps, conversation exports
- backend uvicorn logs, `.bak` files, and one-off backend test scripts
- duplicate or partial Python environments should be archived under `tmp\`, not kept at root
- `tmp\`, `logs\`, `graphify-out\`

## Restore

If one archived file is needed later, move it back manually from the archive folder.
