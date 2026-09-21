# Core Equity Codex Security Rescan - 2026-05-09

## Scope

Focused Codex Security pass over private client exposure surfaces:

- FastAPI access gate, admin routes, websocket auth and cookies
- Alpha Lab wallet/session/usage telemetry
- Built frontend assets served by `backend/static`
- Scratch files and temporary browser profiles under `tmp`
- Tailscale/private-sharing assumptions already documented in the ACL guide

## Validated Findings Fixed

### 1. Alpha Lab usage telemetry could persist sensitive client-provided fields

Status: fixed

Risk:

`POST /api/alpha/usage/event` is intentionally client-accessible after `CORE_ACCESS_TOKEN`. It privacy-minimized the top-level wallet field, but the free-form `extra` object could still store accidental tokens, signatures, private keys, cookies, or other sensitive data if the frontend or a client sent them. It also accepted unbounded nested values.

Fix:

- Added recursive usage-event sanitization.
- Redacts keys matching token/secret/signature/private/seed/mnemonic/password/auth/cookie/key.
- Bounds string length, object width, list length and nesting depth.
- Stores a hash of the client host instead of the raw IP/host.
- Switched Alpha Lab admin token comparison to `hmac.compare_digest`.

Validation:

- Added regression test: `test_usage_event_extra_redacts_sensitive_fields`.
- Confirmed raw secret-like values do not survive in stored event output.

### 2. Stale built frontend bundles remained publicly served

Status: fixed

Risk:

`frontend/vite.config.ts` built into `backend/static`, but Vite did not empty the outDir because it is outside the frontend project root. This left many old `index-*.js` bundles publicly reachable under `/assets`. Some stale bundles still contained old security behavior such as URL-token auto-login logic. Even if `index.html` referenced the newest bundle, stale public artifacts are a bad security and debugging surface.

Fix:

- Set `build.emptyOutDir = true`.
- Rebuilt the frontend.
- Confirmed `backend/static/assets` now contains only the current JS/CSS bundle and current orb asset.

Validation:

- Secret/pattern scan of current `backend/static` returned no active API keys and no old auto-login pattern.
- `npm run build` passes.

### 3. Scratch test files and browser profiles contained API-key remnants

Status: fixed

Risk:

Ignored `tmp` files contained old Cielo/Zerion test keys and temporary browser profile logs contained API-key prefixes from historical backend logs. These were not served by the app and are ignored by `.gitignore`, but they are still unnecessary local secret residue.

Fix:

- Replaced hardcoded Cielo/Zerion keys in archived scratch scripts with placeholders.
- Redacted known secret prefixes in temporary conversation logs.
- Removed disposable browser profile directories under `tmp`.

Validation:

- Re-scanned `tmp` for Firecrawl, Zerion, Cielo and Gemini key patterns: no remaining matches.

### 4. Alpha Lab automation-plan used GET for a cache-writing RPC snapshot

Status: fixed

Risk:

`GET /api/alpha/wallet/automation-plan/{wallet}` is a client-facing decision endpoint protected by the client session cookie. It also persisted a bounded RPC wallet snapshot by default. Because browsers can trigger GET requests cross-site, this created an unnecessary CSRF-style write surface and could let a navigation or embedded request consume RPC/cache work for the active client wallet session.

Fix:

- The snapshot write now requires an explicit client intent header: `x-core-client-action: persist-rpc-snapshot`.
- Requests without that header still receive the read-only automation plan, but the persistence side effect is blocked.
- The frontend sends the header only from the intended Alpha Lab automation-plan fetch.

Validation:

- Added regression test: `test_explicit_client_write_header_is_required_for_persistence`.
- Confirmed the endpoint returns `403` for persistence attempts without the explicit write header.

### 5. Onchain admin token comparison was not constant-time

Status: fixed

Risk:

`backend/routers/onchain.py` compared `x-core-admin-token` with `CORE_ADMIN_TOKEN` using a normal string comparison. This is low risk on a local/Tailscale app, but admin-token checks should use constant-time comparison because those endpoints control label ingestion, RPC enrichment and data jobs.

Fix:

- Switched `_require_data_admin` to `hmac.compare_digest`.

Validation:

- Existing onchain admin auth regression tests pass.

### 6. Wallet-drainer blast-radius controls needed stricter browser guardrails

Status: fixed

Risk:

Wallet connection support is intentionally read-only today, but future Alpha Lab automation work makes accidental wallet-drainer primitives a critical regression risk. Direct page-level wallet provider calls, blanket websocket CSP sources, embeddable iframes, unsafe external links, or static-file traversal would all increase the blast radius of XSS or future automation bugs.

Fix:

- Added `frontend/src/services/walletSafety.ts` as the single wallet RPC wrapper.
- Allowlisted only account discovery, chain/balance reads and the strict human-readable `personal_sign` ownership proof.
- Blocked transaction signing, typed-data signing, batch calls, chain switching, asset watching and Solana transaction signing.
- Removed raw signature state from the dashboard wallet model.
- Tightened CSP: no blanket `ws:`/`wss:`, `frame-src 'none'`, `frame-ancestors 'none'`, `object-src 'none'`, `no-referrer`, `nosniff`, and restrictive Permissions-Policy.
- Hardened SPA static-file serving with path resolution and traversal blocking.
- Added wallet automation threat model: `docs/security/wallet-automation-threat-model.md`.

Validation:

- Added `tests/test_wallet_client_safety.py`.
- Added CSP/path traversal assertions in `tests/test_private_access_security.py`.
- Regression tests fail if future TS/TSX page code reintroduces raw wallet provider requests, transaction/approval methods, stored signatures, unsafe external links, broad websocket CSP, or static path traversal.

### 7. Client-accessible Alpha simulation endpoints accepted unbounded payloads

Status: fixed

Risk:

`POST /api/alpha/simulate/prediction-copy`, `/simulate/manipulation`, `/events/dedupe`, and `/risk/token` are intentionally client-accessible after private site authentication. They accepted arbitrary JSON sizes and unbounded event/trade lists, which could let a malicious or buggy client consume CPU/memory and degrade the local Core Equity service.

Fix:

- Added bounded client payload checks in `backend/routers/alpha_lab.py`.
- Enforced a max serialized payload size and max simulation item count.
- Added a global API mutation body-size guard in `backend/main.py` using `CORE_MAX_REQUEST_BODY_BYTES` with a safe default of 1 MiB.

Validation:

- Added regression tests for oversized Alpha simulation lists and oversized HTTP mutation bodies.

### 8. Future API mutation routes needed a regression tripwire

Status: fixed

Risk:

The project is moving quickly and has many routers. A future `POST`, `PUT`, `PATCH`, or `DELETE` route could accidentally become client-accessible even though it launches a job, mutates labels/RPC state, controls local tools, or consumes paid/external resources.

Fix:

- Added a route inventory regression test that walks `main.app.routes`.
- Every API mutation must now be one of:
  - globally admin-gated by `CORE_ADMIN_TOKEN`;
  - locally gated by `_require_data_admin` / `_require_alpha_admin`;
  - explicitly allowlisted as a reviewed client endpoint.

Validation:

- Current route inventory passes with no unreviewed API mutations.

## Tests

Passing:

```text
python3 -m unittest tests.test_alpha_wallet_verify tests.test_private_access_security -v
npm run build
```

Additional pass:

```text
python3 -m unittest tests.test_alpha_wallet_verify tests.test_private_access_security tests.test_onchain_admin_auth -v
python3 -m py_compile backend/routers/alpha_lab.py backend/routers/onchain.py tests/test_alpha_wallet_verify.py
npm run build
```

Wallet hardening pass:

```text
python3 -m unittest tests.test_wallet_client_safety tests.test_private_access_security tests.test_alpha_wallet_verify tests.test_onchain_admin_auth -v
python3 -m py_compile backend/main.py tests/test_private_access_security.py tests/test_wallet_client_safety.py
npm run build
```

Admin/data endpoint pass:

```text
python3 -m unittest tests.test_alpha_wallet_verify tests.test_private_access_security tests.test_onchain_admin_auth tests.test_wallet_client_safety -v
python3 -m py_compile backend/main.py backend/routers/alpha_lab.py tests/test_alpha_wallet_verify.py tests/test_private_access_security.py tests/test_wallet_client_safety.py
npm run build
```

## Remaining Notes

- `backend/.env` intentionally still contains real secrets and must stay local-only.
- `tmp/` is ignored, but should not be used for long-term storage of browser profiles or API experiments.
- The current frontend bundle still contains the literal string `access_token` only for rejection/removal of URL tokens, not for login.
- Same-host Tailscale port scans can still show Windows false positives; the authoritative exposure test is from another Tailscale client.
