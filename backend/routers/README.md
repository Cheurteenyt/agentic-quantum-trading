# Backend Routers

HTTP/API boundary for Core Equity.

Rules:

- Keep routers thin: validation, auth/admin checks, request shaping, and service
  delegation.
- Put product logic in `backend/services/`.
- Large legacy routers such as `onchain.py`, `arkham.py`, and `alpha_lab.py`
  should be split only with targeted tests and compatibility in mind.
- Do not add DB write logic directly in routers unless the service contract
  explicitly owns the write and the route only delegates.

High-risk files:

- `onchain.py`: very large admin/RPC surface.
- `arkham.py`: large Arkham/entity API surface.
- `alpha_lab.py`: Alpha Lab product API surface.
