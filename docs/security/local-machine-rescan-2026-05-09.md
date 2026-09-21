# Core Equity Local Machine Security Rescan — 2026-05-09

## Scope

Broad local security pass over:

- Core Equity FastAPI access gate.
- Tailscale/Windows portproxy exposure.
- Windows listening ports visible from this session.
- RAG/Qdrant exposure.
- Secret-like files in project folders.

## Fixed Immediately

### Qdrant/RAG was exposed on Tailscale

Finding:

- Docker published Qdrant as `0.0.0.0:6333->6333/tcp` and `[::]:6333->6333/tcp`.
- `http://100.114.51.121:6333/collections` returned the RAG collection list.
- Impact: any authorized Tailscale device could enumerate/read the local RAG vector store unless additionally firewalled.

Fix applied:

- Recreated `core-equity-qdrant` with `127.0.0.1:6333:6333`.
- Added `rag/docker-compose.qdrant.yml` with localhost-only binding.
- Updated `rag/scripts/start_qdrant_server.ps1` so future restarts also use `127.0.0.1:${Port}:6333`.
- Disabled Qdrant telemetry with `QDRANT__TELEMETRY_DISABLED=true`.

Validation:

- `http://127.0.0.1:6333/collections` returns collections.
- `http://100.114.51.121:6333/collections` is unreachable.
- `docker ps` shows `127.0.0.1:6333->6333/tcp`.
- Qdrant logs show `Telemetry reporting disabled`.

### Duplicate secret file `backend/env`

Finding:

- `backend/env` contained active API-key shaped values and duplicated old environment settings.
- The application only loads `backend/.env`, so `backend/env` was stale and unnecessary.

Fix applied:

- Deleted `backend/env`.
- Added `backend/env` and `backend/.env` to `.gitignore`.

### Public security status disclosed network map

Finding:

- `GET /api/security/status` is public and returned exact allowed hosts/origins.
- Impact is low, but it unnecessarily revealed the Tailscale/local topology.

Fix applied:

- Replaced exact lists with booleans: `allowed_origins_configured` and `allowed_hosts_configured`.
- Added regression coverage in `tests/test_private_access_security.py`.

## Needs Manual Admin Action

### Tailscale exposes Windows RPC/SMB services

Finding:

- `Test-NetConnection 100.114.51.121 -Port 135` returned open.
- `Test-NetConnection 100.114.51.121 -Port 445` returned open.
- Additional Windows service ports were also reachable on the Tailscale IP during local verification: `5040`, `5357`, `2179`, `2869`, and several dynamic RPC/system ports.
- `Get-SmbShare` shows default administrative shares: `ADMIN$`, `C$`, `D$`, and `IPC$`.
- `Tailscale-In` firewall rules are enabled on Domain/Private profiles and appear to be the broad allow rule exposing these services.

Impact:

- Any Tailscale device allowed into the tailnet may be able to probe Windows RPC/SMB surfaces.
- If Windows credentials are weak, reused, phished, or later compromised, administrative shares could become a direct path to local disk access.

Run this in **PowerShell as Administrator**:

```powershell
D:\trading-agent\scripts\harden_tailscale_surface.ps1 -TailscaleIp 100.114.51.121 -CorePort 8000
```

The script disables broad `Tailscale-In`, disables Windows file-sharing server binding on the Tailscale adapter, disables broad Hyper-V/WMI/RPC inbound management allow-rules, then re-adds the explicit Core Equity TCP 8000 allow-rule.

Then verify without admin:

```powershell
D:\trading-agent\scripts\check_tailscale_surface.ps1 -TailscaleIp 100.114.51.121 -CorePort 8000 -TimeoutMs 600
```

Expected:

- `135` closed.
- `445` closed.
- `6333` closed.
- Only `8000` should be open when the Core Equity site is intentionally shared.

Current pre-hardening check still fails with unexpected open ports: `135`, `445`, `2179`, `2869`, `5040`, `5357`, `49664`, `49665`, `49666`, `49669`, `49672`, `49684`, `49690`, `54235`.

After disabling SMB binding on the Tailscale adapter, `445` closed in the local self-test, but RPC/Hyper-V/system ports still appeared open when testing the host against its own Tailscale IP. `tailscale status` currently shows no separate client devices, so this cannot yet be validated from a true remote Tailscale client. Treat same-host results as suspicious but not authoritative; final validation must be run from a separate Tailscale client.

Add Tailscale ACLs before onboarding clients. See `docs/security/tailscale-acl-core-equity.md`.

### Windows firewall rule is too broad

Finding:

- Two firewall rules named `Core Equity Tailscale 8000` exist.
- Both allow inbound TCP `8000` with `LocalAddress=Any`, `RemoteAddress=Any`, `Profile=Any`.
- Because the current portproxy listens only on `100.114.51.121:8000`, the practical exposure is lower, but the firewall rule should still be scoped to the Tailscale IP.

Run this in **PowerShell as Administrator**:

```powershell
D:\trading-agent\scripts\harden_core_firewall.ps1 -TailscaleIp 100.114.51.121 -Port 8000
```

Verify:

```powershell
Get-NetFirewallRule -DisplayName "Core Equity Tailscale 8000" |
  Get-NetFirewallAddressFilter |
  Select-Object LocalAddress,RemoteAddress

Get-NetFirewallRule -DisplayName "Core Equity Tailscale 8000" |
  Get-NetFirewallPortFilter |
  Select-Object Protocol,LocalPort,RemotePort
```

Expected:

- One rule only.
- `LocalAddress` should be `100.114.51.121`.
- `LocalPort` should be `8000`.

## Runtime Auth Validation

Checked via non-local WSL address `172.18.216.150:8000`.

- Anonymous `/health`: `200`
- Anonymous `/api/market/prices`: `401`
- Client token `/api/market/prices`: `200`
- Client token `/api/desktop/status`: `403`
- Client token `/api/intel/status`: `403`
- Client token `/api/arkham/db/stats`: `403`
- Client token `/api/news/search?q=gold`: `403`
- Owner headers `/api/arkham/db/stats`: `200`

## Tests

Passing:

```text
python3 -m unittest tests.test_private_access_security -v
python3 -m py_compile backend/main.py tests/test_private_access_security.py
```

## Notes

- `127.0.0.1:8000` from Windows did not respond during this scan, while WSL `172.18.216.150:8000` did. The current portproxy config points to the correct WSL IP, but Windows loopback-to-WSL is not guaranteed. Tailscale exposure should be re-tested after the firewall rule is corrected.
- Qdrant has no API auth configured; keeping it localhost-only is mandatory.
