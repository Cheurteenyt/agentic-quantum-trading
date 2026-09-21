# Backend Services

Business/service logic for Core Equity.

Use `SERVICE_CATALOG.md` for the detailed service inventory.

Rules:

- `onchain_engine.py` is a legacy compatibility facade. Prefer adding or moving
  logic into `services/onchain/`.
- Keep compatibility wrappers when routers/tests import old public names.
- Do not place `.db`, logs, scratch outputs or one-off scripts in this folder.
  Legacy DB fallbacks belong in `backend/data/legacy/`.
- Domain-specific external adapters belong in `integrations/` unless they are
  tightly coupled to backend service contracts.

Known cleanup priorities:

- Keep shrinking `onchain_engine.py` with the strangler pattern.
- Keep route logic out of services and product logic out of routers.
- Split tests only after service compatibility surfaces are stable.
