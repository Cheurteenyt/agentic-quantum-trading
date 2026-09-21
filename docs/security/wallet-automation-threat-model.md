# Core Equity Wallet Automation Threat Model

Date: 2026-05-09

## Security Position

Core Equity must stay read-only for connected client wallets until a separate, audited execution system exists.

Current invariant:

- No private keys, seed phrases or mnemonics are collected.
- No raw wallet signatures are persisted.
- Browser wallet access is limited to account discovery, chain/balance reads and a human-readable ownership proof.
- Alpha Lab copy-plan/backtest/automation-plan endpoints return analysis only.
- Backend wallet decision responses must keep `execution_enabled: false`.

## Primary Drain Risks

1. Malicious or compromised frontend code asks the wallet to sign a transaction, typed-data permit, approval or batch call.
2. XSS injects wallet-drainer JavaScript into the app.
3. A future automation patch accidentally adds transaction execution to a client-facing path.
4. A client is tricked into signing an ambiguous message that can be replayed as authorization elsewhere.
5. A browser extension or wallet provider is compromised outside Core Equity's control.

## Current Controls

- Frontend wallet RPC calls go through `safeWalletRequest`.
- Dangerous methods are blocked client-side: `eth_sendTransaction`, transaction signing, typed-data signing, batch calls, chain switching, asset watching and Solana transaction signing.
- Static regression tests fail if page code uses raw `provider.request` or dangerous transaction/approval methods.
- Static regression tests fail if external `target="_blank"` links miss `rel="noopener noreferrer"`.
- Ownership proof uses `personal_sign` only with a strict Core Equity message format containing address, network and fresh timestamp.
- Server-side EVM recovery is required; verification fails closed if recovery is unavailable.
- Wallet ownership sessions are httpOnly, scoped to `/api/alpha`, short-lived and read-only.
- Security headers add CSP, `frame-src 'none'`, `frame-ancestors 'none'`, `object-src 'none'`, `nosniff`, `no-referrer` and restrictive Permissions-Policy.
- CSP no longer allows blanket `ws:`/`wss:` connections; localhost websocket development endpoints are explicit.
- SPA static-file serving resolves paths and blocks traversal before returning `FileResponse`.
- Client-accessible Alpha simulation/risk endpoints enforce bounded payload size and item counts.
- Global API mutations reject oversized request bodies before reaching route handlers.
- API mutation route inventory is regression-tested: every mutation must be admin-gated, locally admin-gated or explicitly client-allowlisted.

## Non-Guarantees

Core Equity cannot guarantee safety against:

- A zero-day in the client browser, wallet extension or operating system.
- A malicious wallet extension installed by the client.
- A user signing a dangerous prompt on another website.

The product can reduce blast radius by never requesting transaction authority, making every wallet prompt human-readable, and requiring future execution to live behind a separate audited consent and policy layer.

## Future Execution Gate

Before any real automation can exist, implement all of the following:

- Separate execution service from the analysis UI.
- Simulation-first policy engine with max loss, max allowance, token denylist and chain allowlist.
- Explicit per-strategy client consent, not global wallet approval.
- No unlimited approvals.
- Hardware-wallet friendly flow.
- Pre-sign transaction preview with destination, token, value, calldata classifier and explorer links.
- Server-side risk verdict and local client confirmation must both match.
- Emergency kill switch and per-client revocation.
