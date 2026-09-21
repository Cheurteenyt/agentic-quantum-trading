# Core Equity Tailscale ACL Hardening

## Why This Matters

Windows can expose RPC, SMB, Hyper-V and other local services on the Tailscale adapter if broad inbound rules are enabled. Local firewall hardening is necessary, but Tailscale ACLs are the stronger outer wall: clients should only be able to reach Core Equity on TCP `8000`.

## Current State

As of the 2026-05-09 scan:

- The tailnet currently shows only the Core Equity host itself.
- `Tailscale-In` was disabled locally.
- SMB server binding was disabled on the Tailscale adapter.
- Qdrant is localhost-only.
- The remaining self-test port results may be same-host false positives until verified from a separate Tailscale client.

## Recommended ACL Model

Use groups/tags in Tailscale admin rather than trusting every tailnet member.

Suggested roles:

- `group:core-clients`: users allowed to access the product.
- `tag:core-server`: Core Equity host.

Ready-to-copy policies:

- Immediate IP-only policy: `configs/tailscale/core-equity-acl-ip-only.hujson`
- Future tagged policy: `configs/tailscale/core-equity-acl-tagged.hujson`

Validate before pasting:

```powershell
python D:\trading-agent\scripts\validate_tailscale_acl.py D:\trading-agent\configs\tailscale\core-equity-acl-ip-only.hujson
python D:\trading-agent\scripts\validate_tailscale_acl.py D:\trading-agent\configs\tailscale\core-equity-acl-tagged.hujson
```

Minimal ACL idea:

```json
{
  "groups": {
    "group:core-clients": [
      "client@example.com"
    ]
  },
  "tagOwners": {
    "tag:core-server": [
      "autogroup:admin"
    ]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["group:core-clients"],
      "dst": ["tag:core-server:8000"]
    }
  ]
}
```

Replace `client@example.com` with the real Tailscale user email for each client.

## Important

Do not add a broad rule like:

```json
{"action": "accept", "src": ["*"], "dst": ["*:*"]}
```

That would allow clients to probe Windows services such as RPC/SMB if the host firewall ever regresses.

## Verification From A Client Device

After adding a client to Tailscale, run from that client:

```powershell
D:\trading-agent\scripts\check_tailscale_surface.ps1 -TailscaleIp 100.114.51.121 -CorePort 8000 -TimeoutMs 600
```

If the client does not have the repo, run simple checks:

```powershell
Test-NetConnection 100.114.51.121 -Port 8000
Test-NetConnection 100.114.51.121 -Port 445
Test-NetConnection 100.114.51.121 -Port 135
Test-NetConnection 100.114.51.121 -Port 6333
```

Expected:

- `8000`: open when Core Equity is intentionally shared.
- `445`: closed.
- `135`: closed.
- `6333`: closed.
