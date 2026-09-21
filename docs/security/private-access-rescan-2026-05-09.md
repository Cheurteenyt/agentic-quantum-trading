# Core Equity Private Access Security Rescan — 2026-05-09

## Scope

Targeted rescan after adding `CORE_ADMIN_TOKEN` to verify that a Tailscale client with only `CORE_ACCESS_TOKEN` cannot reach owner-only controls, local agents, local PC control, live scraping/AI-credit routes, or internal data maintenance routes.

## Result

No active client-token bypass remains in the checked surfaces.

## Findings Fixed In This Pass

### Localhost auth bypass could become unsafe behind a local reverse proxy

`CORE_REQUIRE_LOCAL_AUTH=false` is convenient for local development, but a future local reverse proxy can make remote traffic appear as `127.0.0.1`. If the bypass only checks the socket client IP, a tunnel/proxy could accidentally skip authentication.

Fix:

- Local bypass now requires both the socket client and the HTTP `Host` header to be direct localhost (`127.0.0.1`, `localhost`, or `::1`).
- Requests with forwarding headers (`Forwarded`, `X-Forwarded-*`, `X-Real-IP`, `CF-Connecting-IP`) never receive the localhost bypass.
- The same logic now protects the websocket endpoint `/ws`.
- Frontend URL-token login was removed. `?access_token=...` is stripped and rejected client-side instead of being used for login.

### Client token could still reach Intel/live-credit surfaces

`/api/intel/*` launches web-agent investigations and specialized agents. Some news GET routes also triggered Firecrawl/Gemini live work instead of cache-only reads. These are not safe client surfaces because they can consume API credits, trigger background work, or expose internal operational state.

Fix:

- Added `/api/intel/*` to the central owner-only prefix guard.
- Added `/api/arkham/scrapling/*` and `/api/arkham/db/*` to owner-only routes.
- Added exact owner-only live news routes: `GET /api/news/gold`, `GET /api/news/gold/bias`, and `GET /api/news/search`.
- Kept `GET /api/news/gold/latest` client-accessible because it is cache-only.

## Runtime Verification

Checked through the non-local WSL/Tailscale-facing address, not localhost.

- Anonymous `GET /api/intel/status`: `401`
- Client token `GET /api/intel/status`: `403`
- Owner headers `GET /api/intel/status`: reached handler, then returned `500` from Intel internals. This confirms auth passed; the `500` is a separate application reliability issue.
- Client token `GET /api/news/search?q=gold`: `403`
- Client token `GET /api/news/gold/latest`: `404` when no cache exists, not an auth bypass.
- Client token `GET /api/arkham/db/stats`: `403`
- Client token `GET /api/market/prices`: `200`

## Regression Tests

Passing:

```text
python3 -m unittest tests.test_private_access_security -v
python3 -m unittest tests.test_private_access_security tests.test_onchain_admin_auth tests.test_onchain_entity_chain_gaps -v
python3 -m unittest tests.test_private_access_security tests.test_alpha_wallet_verify -v
npm run build
```

## Remaining Notes

- `CORE_ADMIN_TOKEN` must stay different from `CORE_ACCESS_TOKEN` and `CORE_CLIENT_SESSION_SECRET`.
- Owner scripts that call owner-only endpoints need both `x-core-token` and `x-core-admin-token`.
- The Intel `500` after owner auth should be treated as a normal backend bug, not an auth bypass.
