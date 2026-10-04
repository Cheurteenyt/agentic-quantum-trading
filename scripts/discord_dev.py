#!/usr/bin/env python
"""Le gestionnaire Discord Developer — l'état complet de l'app et ses opérations.

Gère ce qui est accessible par l'API (token du bot) : les commandes globales
vs guilde, les webhooks, les métadonnées de l'app, l'URL d'invitation. Les
réglages portail uniquement (intents, bot public, secret, redirects) passent
par le navigateur dédié — voir docs/discord/portail-oauth2.md.

Usage :
  python scripts/discord_dev.py status         # l'audit complet
  python scripts/discord_dev.py sync-global    # aligne les globales sur la guilde
  python scripts/discord_dev.py webhooks       # les webhooks du serveur
  python scripts/discord_dev.py invite         # l'URL d'invitation actuelle

curl en subprocess (httpx/urllib déclenchent Cloudflare 1010/40333 — le curl
nu passe ; ne jamais spoof d'UA navigateur sur l'API Discord).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://discord.com/api/v10"


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in (ROOT / ".env").read_text().splitlines():
        if "=" in raw and not raw.strip().startswith("#"):
            k, _, v = raw.strip().partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    out.update({k: v for k, v in os.environ.items() if k.startswith("DISCORD_")})
    return out


def api(method: str, path: str, tok: str, payload: dict | None = None):
    cmd = ["curl", "-s", "-X", method, "-H", f"Authorization: Bot {tok}"]
    if payload is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(payload)]
    r = subprocess.run(cmd + [f"{API}{path}"], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"_raw": r.stdout[:200], "_err": r.stderr[:200]}


DROP_GUILD_SCOPED = {"id", "version", "application_id", "guild_id"}


def app_id(e: dict) -> str:
    return e.get("DISCORD_CLIENT_ID") or e.get("DISCORD_APPLICATION_ID") or ""


def cmd_status(e: dict) -> int:
    tok = e["DISCORD_BOT_TOKEN"]
    aid = app_id(e)
    gid = e["DISCORD_GUILD_ID"]
    print("=== L'APP ===")
    a = api("GET", "/applications/@me", tok)
    print(f"  {a.get('name')} (id {a.get('id')})")
    print(f"  description : {(a.get('description') or 'VIDE')[:70]}")
    print(f"  tags : {a.get('tags')}")
    print(f"  install_params : {a.get('install_params')}")
    print("\n=== COMMANDES ===")
    g = api("GET", f"/applications/{aid}/commands", tok)
    d = api("GET", f"/applications/{aid}/guilds/{gid}/commands", tok)
    ng, nd = (len(g), len(d)) if isinstance(g, list) and isinstance(d, list) else (-1, -1)
    print(f"  globales : {ng}   guilde : {nd}")
    if ng != nd:
        print("  ⚠ DÉSALIGNÉ — `sync-global` pour mettre les globales = la guilde")
    if isinstance(d, list) and nd:
        names = {c["name"] for c in d}
        ghosts = {c["name"] for c in g} - names if isinstance(g, list) else set()
        if ghosts:
            print(f"  fantômes globales : {sorted(ghosts)[:8]}{'…' if len(ghosts) > 8 else ''}")
    print("\n=== WEBHOOKS DU SERVEUR ===")
    w = api("GET", f"/guilds/{gid}/webhooks", tok)
    if isinstance(w, list):
        print(f"  {len(w)} webhook(s)")
        for x in w:
            print(f"    #{x.get('channel_id')} | {x.get('name')} | par {(x.get('user') or {}).get('username','?')}"
                  f" | app: {x.get('application_id') or '—'}")
    else:
        print(" ", w)
    return 0


def cmd_sync_global(e: dict) -> int:
    tok = e["DISCORD_BOT_TOKEN"]
    aid = app_id(e)
    gid = e["DISCORD_GUILD_ID"]
    guild_cmds = api("GET", f"/applications/{aid}/guilds/{gid}/commands", tok)
    if not isinstance(guild_cmds, list):
        print("ERREUR fetch guilde:", guild_cmds)
        return 1
    payload = [{k: v for k, v in c.items() if k not in DROP_GUILD_SCOPED} for c in guild_cmds]
    res = api("PUT", f"/applications/{aid}/commands", tok, payload)
    if isinstance(res, list):
        print(f"globales = {len(res)} commandes (alignées sur la guilde)")
        return 0
    print("ERREUR PUT:", res)
    return 1


def cmd_webhooks(e: dict) -> int:
    w = api("GET", f"/guilds/{e['DISCORD_GUILD_ID']}/webhooks", e["DISCORD_BOT_TOKEN"])
    print(json.dumps(w, indent=2, ensure_ascii=False) if isinstance(w, list) else w)
    return 0


def cmd_invite(e: dict) -> int:
    aid = app_id(e)
    perms = "1099780140054"
    print(f"https://discord.com/oauth2/authorize?client_id={aid}"
          f"&permissions={perms}&scope=bot%20applications.commands")


def main() -> int:
    e = env()
    if not e.get("DISCORD_BOT_TOKEN"):
        print("DISCORD_BOT_TOKEN absent du .env")
        return 1
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    actions = {"status": cmd_status, "sync-global": cmd_sync_global,
               "webhooks": cmd_webhooks, "invite": cmd_invite}
    if action not in actions:
        print(__doc__)
        return 1
    return actions[action](e)


if __name__ == "__main__":
    raise SystemExit(main())
