# Core Equity Client Onboarding — Private Tailscale Access

## Goal

Give a client private access to Core Equity without exposing your Windows machine, RAG/Qdrant, SMB, RPC, Hyper-V, local AI servers, or admin endpoints.

## Access Model

Each client needs two separate gates:

- Tailscale network access to `100.114.51.121:8000` only.
- Core Equity login through `CORE_ACCESS_TOKEN`.

Clients must never receive:

- `CORE_ADMIN_TOKEN`
- API keys
- RPC credentials
- `.env`
- direct Qdrant access

## Step 1 — Apply Tailscale ACL

Use the immediate IP-only policy first:

```text
D:\trading-agent\configs\tailscale\core-equity-acl-ip-only.hujson
```

Paste it in:

```text
Tailscale admin console > Access controls
```

Replace:

```text
client@example.com
```

with the real Tailscale login email for the client.

The important rule is:

```json
{
  "action": "accept",
  "src": ["group:core-clients"],
  "dst": ["100.114.51.121:8000"]
}
```

That means clients can only reach Core Equity on port `8000`.

## Step 2 — Invite Client To Tailnet

In Tailscale admin:

```text
Users > Invite users
```

Use the same email that you added in `group:core-clients`.

## Step 3 — Verify From Client Machine

From the client computer, test:

```powershell
Test-NetConnection 100.114.51.121 -Port 8000
Test-NetConnection 100.114.51.121 -Port 445
Test-NetConnection 100.114.51.121 -Port 135
Test-NetConnection 100.114.51.121 -Port 6333
Test-NetConnection 100.114.51.121 -Port 8080
```

Expected:

- `8000`: `TcpTestSucceeded: True` when Core Equity is shared.
- `445`: `False`
- `135`: `False`
- `6333`: `False`
- `8080`: `False`

If the client has this repo locally, they can run:

```powershell
D:\trading-agent\scripts\check_tailscale_surface.ps1 -TailscaleIp 100.114.51.121 -CorePort 8000 -TimeoutMs 600
```

## Step 4 — Client URL

The client opens:

```text
http://100.114.51.121:8000
```

Then they log in with the client token only:

```text
CORE_ACCESS_TOKEN
```

Do not put the token in the URL.

Core Equity intentionally rejects URL-token login such as:

```text
http://100.114.51.121:8000?access_token=...
```

Reason: URL secrets can leak through browser history, screenshots, referrers, logs, and copy/paste. Clients should enter the token on the login screen; the backend then stores access in an httpOnly session cookie.

## Step 5 — Owner/Admin Verification

From your machine, verify:

```powershell
tailscale status
netsh interface portproxy show v4tov4
D:\trading-agent\scripts\check_tailscale_surface.ps1 -TailscaleIp 100.114.51.121 -CorePort 8000 -TimeoutMs 600
```

Same-host checks can show false positives on Windows RPC ports. The authoritative check is the one from a separate client device.

If a future reverse proxy is added, keep remote clients authenticated. The backend localhost bypass only applies to direct localhost requests and rejects forwarded traffic, but the safest production/private-sharing setting is still:

```text
CORE_REQUIRE_LOCAL_AUTH=true
```

## Future Cleaner Version

After the first working client, migrate to the tagged policy:

```text
D:\trading-agent\configs\tailscale\core-equity-acl-tagged.hujson
```

Then tag the server:

```powershell
tailscale set --advertise-tags=tag:core-server
```

The client rule becomes:

```json
{
  "action": "accept",
  "src": ["group:core-clients"],
  "dst": ["tag:core-server:8000"]
}
```

This is easier to maintain if the Tailscale IP changes later.
