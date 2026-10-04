"""Le dashboard web Core Equity — les membres se connectent avec Discord (OAuth2).

Le flow : /oauth2/login → Discord (identify + guilds.members.read) →
/oauth2/callback → échange du code → session signée (cookie HttpOnly) →
/moi /classement /serveur. Les tokens vivent dans data/dashboard_sessions.json
(chmod 600) pour survivre aux redémarrages ; les cookies sont signés HMAC avec
le client secret. Port 8606 (8080 = Bonsai, 8000 = backend) — le redirect URI
du portail doit rester synchronisé : http://localhost:8606/oauth2/callback.

Lancement : .venv/bin/python -m discord_bot.dashboard
           (service systemd : core-equity-dashboard.service)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.requests import Request

from discord_bot import stats
from discord_bot.config import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_GUILD_ID, ROOT

PORT = 8606
REDIRECT_URI = f"http://localhost:{PORT}/oauth2/callback"
API = "https://discord.com/api/v10"
CDN = "https://cdn.discordapp.com"
SCOPES = "identify guilds.members.read"
SESSIONS_PATH = ROOT / "data" / "dashboard_sessions.json"
DDB = ROOT / "data" / "warehouse" / "discord.db"
COOKIE = "ce_session"
SESSION_TTL = 7 * 24 * 3600
PROFILE_TTL = 300  # le cache du profil — 2 fetchs Discord par vue sinon, et un 429 déconnecterait

app = FastAPI(title="Core Equity", docs_url=None, redoc_url=None, openapi_url=None)

# ——— sessions : fichier JSON (uid → tokens + profil de login) ———

_sess_lock = threading.Lock()


def _sessions() -> dict:
    if not SESSIONS_PATH.exists():
        return {}
    try:
        return json.loads(SESSIONS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_sessions(s: dict) -> None:
    SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SESSIONS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(s))
    os.replace(tmp, SESSIONS_PATH)
    os.chmod(SESSIONS_PATH, 0o600)


# ——— le cookie signé HMAC (le secret OAuth2 sert de clé — rien de neuf à garder) ———


def _sign(payload: bytes) -> str:
    return hmac.new(DISCORD_CLIENT_SECRET.encode(), payload, hashlib.sha256).hexdigest()


def _make_cookie(uid: str) -> str:
    body = json.dumps({"uid": uid, "exp": int(time.time()) + SESSION_TTL})
    raw = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return f"{raw}.{_sign(raw.encode())}"


def _read_cookie(value: str) -> str | None:
    if not value or "." not in value:
        return None
    raw, sig = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(raw.encode()), sig):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (json.JSONDecodeError, ValueError):
        return None
    if body.get("exp", 0) < time.time():
        return None
    return str(body["uid"])


def _uid_of(request: Request) -> str | None:
    return _read_cookie(request.cookies.get(COOKIE, ""))


# ——— l'état anti-CSRF OAuth2 (mémoire, usage unique, 10 min) ———

_states: dict[str, float] = {}


def _state_new() -> str:
    s = secrets.token_urlsafe(24)
    _states[s] = time.time() + 600
    return s


def _state_take(s: str) -> bool:
    exp = _states.pop(s, 0)
    return bool(exp) and exp > time.time()


# ——— Discord : l'échange du code et les fetchs ———


async def _exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.post(f"{API}/oauth2/token", data={
            "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
        })
        r.raise_for_status()
        return r.json()


def _discord_get(path: str, token: str) -> dict:
    with httpx.Client(timeout=15) as cli:
        r = cli.get(f"{API}{path}", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


def _refresh(token: dict) -> dict:
    with httpx.Client(timeout=15) as cli:
        r = cli.post(f"{API}/oauth2/token", data={
            "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "refresh_token", "refresh_token": token["refresh_token"],
        })
        r.raise_for_status()
        return r.json()


def _session_profile(uid: str) -> dict | None:
    """Le profil à jour (rôles, arrivée) — cache 5 min, fallback périmé si
    Discord est en vrac (un 429 ou un timeout ne doit PAS déconnecter)."""
    with _sess_lock:
        s = _sessions().get(uid)
    if not s:
        return None
    prof = s.get("profile") or {}

    def _from_cache() -> dict:
        return {"user": {"id": uid, "global_name": prof.get("username", "?"),
                         "avatar": prof.get("avatar")},
                "member": {"roles": prof.get("roles", []),
                           "joined_at": prof.get("joined_at")}}

    if prof and time.time() - prof.get("cached_at", 0) < PROFILE_TTL:
        return _from_cache()

    tok = {"access_token": s["access_token"], "refresh_token": s["refresh_token"]}
    refreshed = False
    try:
        if s.get("expires_at", 0) < time.time() + 60:
            tok = _refresh(tok)
            refreshed = True
        user = _discord_get("/users/@me", tok["access_token"])
        member = _discord_get(f"/users/@me/guilds/{DISCORD_GUILD_ID}/member", tok["access_token"])
    except httpx.HTTPStatusError as e:
        # 401/403 = token mort, 400 = invalid_grant du refresh (Discord renvoie
        # 400 pas 401) → logout ; le reste (429, 5xx, timeout) = passager →
        # le cache périmé vaut mieux qu'une déconnexion
        if e.response.status_code in (400, 401, 403) or not prof:
            return None
        return _from_cache()
    except Exception:
        if prof:
            return _from_cache()
        return None
    new_prof = {"username": user.get("global_name") or user.get("username", "?"),
                "avatar": user.get("avatar"), "roles": member.get("roles", []),
                "joined_at": member.get("joined_at"), "cached_at": time.time()}
    with _sess_lock:
        all_s = _sessions()
        if uid in all_s:
            all_s[uid]["profile"] = new_prof
            if refreshed:
                all_s[uid].update(access_token=tok["access_token"],
                                  refresh_token=tok["refresh_token"],
                                  expires_at=int(time.time()) + tok.get("expires_in", 604800))
            _save_sessions(all_s)
    return {"user": user, "member": member}


# ——— les DB (lecture seule, sync → threadpool FastAPI) ———


def _ddb() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DDB}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _calls_tables_ready() -> bool:
    """d_calls n'existe qu'au premier call parsé par le bot — le dashboard
    (read-only) dégrade en page vide au lieu de 500."""
    con = _ddb()
    try:
        return bool(con.execute("SELECT 1 FROM sqlite_master WHERE name='d_calls'").fetchone())
    finally:
        con.close()


def _role_map() -> dict[str, sqlite3.Row]:
    con = _ddb()
    try:
        return {r["role_id"]: r for r in con.execute("SELECT * FROM d_roles")}
    finally:
        con.close()


# ——— le HTML (thème sombre Discord, zéro dépendance) ———

_CSS = """
body{background:#1e1f22;color:#dbdee1;font-family:'gg sans','Segoe UI',sans-serif;margin:0}
a{color:#00a8fc;text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px}
h1{color:#f2f3f5;font-size:26px}h2{color:#b5bac1;font-size:13px;text-transform:uppercase;letter-spacing:.6px;margin-top:34px}
.card{background:#313338;border-radius:10px;padding:22px;margin:14px 0}
.btn{display:inline-block;background:#5865f2;color:#fff;padding:12px 26px;border-radius:6px;font-weight:600}
.btn:hover{background:#4752c4;text-decoration:none}
.btn.grey{background:#4e5058}
.avatar{width:72px;height:72px;border-radius:50%;vertical-align:middle;margin-right:16px}
.chip{display:inline-block;padding:3px 11px;border-radius:5px;font-size:13px;margin:3px 4px 3px 0;color:#fff}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:8px 10px;border-bottom:1px solid #3f4147;text-align:left}
th{color:#b5bac1;font-size:12px;text-transform:uppercase}
.up{color:#23a55a}.down{color:#f23f43}.muted{color:#949ba4}
nav{background:#2b2d31;padding:12px 20px}nav a{margin-right:18px;color:#dbdee1;font-weight:500}
nav .brand{color:#5865f2;font-weight:700}
"""


def _page(title: str, body: str) -> HTMLResponse:
    nav = (f'<nav><span class="brand">Core Equity</span> — <a href="/moi">Moi</a>'
           f'<a href="/classement">Classement</a><a href="/serveur">Serveur</a>'
           f'<a href="/logout" style="float:right">Déconnexion</a></nav>')
    return HTMLResponse(f"<!doctype html><html lang=fr><head><meta charset=utf-8>"
                        f"<meta name=viewport content='width=device-width,initial-scale=1'>"
                        f"<title>{title} — Core Equity</title><style>{_CSS}</style></head>"
                        f"<body>{nav}<div class=wrap>{body}</div></body></html>")


def _avatar(uid: str, av: str | None, size: int = 72) -> str:
    if av:
        return f"{CDN}/avatars/{uid}/{av}.png?size={size}"
    return f"{CDN}/embed/avatars/{(int(uid) >> 22) % 6}.png"


def _login_page(msg: str = "") -> HTMLResponse:
    err = f"<div class=card style='border-left:3px solid #f23f43'>{msg}</div>" if msg else ""
    return _page("Connexion", f"""
        <h1>Core Equity</h1>
        <p class=muted>Le tableau de bord du serveur — tes calls, ton rang, le serveur en direct.</p>
        {err}
        <div class=card style=text-align:center>
            <a class=btn href="/oauth2/login">Se connecter avec Discord</a>
            <p class=muted style=margin-top:14px>identify + membership du serveur — rien d'autre.</p>
        </div>""")


# ——— les routes ———


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if _uid_of(request):
        return RedirectResponse("/moi", status_code=302)
    return _login_page()


@app.get("/oauth2/login")
def oauth_login():
    if not (DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET):
        return _login_page("Le dashboard n'est pas configuré (CLIENT_ID/SECRET manquants dans .env).")
    q = urlencode({"client_id": DISCORD_CLIENT_ID, "redirect_uri": REDIRECT_URI,
                   "response_type": "code", "scope": SCOPES, "state": _state_new()})
    return RedirectResponse(f"{API}/oauth2/authorize?{q}", status_code=302)


@app.get("/oauth2/callback")
async def oauth_callback(request: Request):
    p = request.query_params
    if p.get("error"):
        return _login_page(f"Connexion refusée ({p.get('error')}) — tu peux réessayer.")
    if not p.get("code") or not _state_take(p.get("state", "")):
        return _login_page("Session de connexion expirée — réessaie, ça arrive.")
    try:
        tok = await _exchange_code(p["code"])
    except Exception:
        return _login_page("L'échange du code a échoué — réessaie dans un instant.")
    try:
        user = _discord_get("/users/@me", tok["access_token"])
        member = _discord_get(f"/users/@me/guilds/{DISCORD_GUILD_ID}/member", tok["access_token"])
    except Exception:
        return _login_page("Tu n'es pas membre du serveur Core Equity (ou Discord a refusé le fetch).")
    uid = user["id"]
    with _sess_lock:
        s = _sessions()
        s[uid] = {"access_token": tok["access_token"], "refresh_token": tok["refresh_token"],
                  "expires_at": int(time.time()) + tok.get("expires_in", 604800),
                  "username": user.get("global_name") or user.get("username", "?"),
                  "logged_at": time.time(),
                  "profile": {"username": user.get("global_name") or user.get("username", "?"),
                              "avatar": user.get("avatar"), "roles": member.get("roles", []),
                              "joined_at": member.get("joined_at"), "cached_at": time.time()}}
        _save_sessions(s)
    resp = RedirectResponse("/moi", status_code=302)
    resp.set_cookie(COOKIE, _make_cookie(uid), max_age=SESSION_TTL,
                    httponly=True, samesite="lax", path="/")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/moi", response_class=HTMLResponse)
def moi(request: Request):
    uid = _uid_of(request)
    if not uid:
        return _login_page()
    prof = _session_profile(uid)
    if not prof:
        resp = RedirectResponse("/logout", status_code=302)
        resp.delete_cookie(COOKIE, path="/")
        return resp
    user, member = prof["user"], prof["member"]
    name = user.get("global_name") or user.get("username", "?")
    roles = []
    rmap = _role_map()
    for rid in member.get("roles", []):
        r = rmap.get(rid)
        color = (r["color"] if r and r["color"] else "#4e5058").lstrip("#")
        if color.isdigit():
            color = f"{int(color):06x}"
        roles.append(f'<span class=chip style="background:#{color}">'
                     f'{r["name"] if r else rid[:8]}</span>')
    con = _ddb()
    try:
        n_msg = con.execute("SELECT COUNT(*) FROM d_messages WHERE author_id=?",
                            (uid,)).fetchone()[0]
    finally:
        con.close()
    st = stats.user_stats(uid)
    calls = st["calls"]
    agg = {"n": st["n_scored"], "wr": st["wr"], "tot": st["tot_ret"]}
    joined = member.get("joined_at", "?")[:10]
    wr = f"{agg['wr'] * 100:.0f} %" if agg["n"] else "—"
    tot = f"{agg['tot']:+.1f} %" if agg["tot"] is not None else "—"
    lignes = "".join(
        f"<tr><td><b>{c['symbol']}</b></td>"
        f"<td class={'up' if c['direction'] == 'long' else 'down'}>{c['direction']}</td>"
        f"<td>{c['entry'] if c['entry'] else '—'}</td>"
        f"<td class=muted>{(c['posted_at'] or '?')[:16].replace('T', ' ')}</td>"
        f"<td>{c['ret_pct'] if c['scored'] else '<span class=muted>en cours</span>'}"
        f"{' %' if c['scored'] else ''} {'· ' + c['verdict'] if c['verdict'] else ''}</td></tr>"
        for c in calls) or "<tr><td colspan=5 class=muted>Aucun call — poste-le dans les salons de trading.</td></tr>"
    return _page("Moi", f"""
        <div class=card><img class=avatar src="{_avatar(uid, user.get('avatar'))}">
            <h1 style=display:inline>{name}</h1>
            <p class=muted>Membre depuis le {joined} · {n_msg} message(s) capturé(s)</p>
            <div>{''.join(roles) or '<span class=muted>aucun rôle</span>'}</div></div>
        <h2>Tes calls scorés</h2>
        <div class=card>{agg['n'] or 0} call(s) scoré(s) · WR {wr} · Σ ret {tot}</div>
        <table><tr><th>Symbole</th><th>Sens</th><th>Entrée</th><th>Posté</th><th>Ret</th></tr>{lignes}</table>""")


@app.get("/classement", response_class=HTMLResponse)
def classement():
    rows = stats.classement(limit=20)
    lignes = ""
    for i, r in enumerate(rows, 1):
        med = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}")
        lignes += (f"<tr><td>{med}</td><td><b>{r['author_name']}</b></td>"
                   f"<td>{r['n']}</td><td class=up>{r['wr'] * 100:.0f} %</td>"
                   f"<td class={'up' if (r['tot'] or 0) > 0 else 'down'}>{r['tot']:+.1f} %</td></tr>")
    if not lignes:
        lignes = "<tr><td colspan=5 class=muted>Pas encore 3 calls scorés par membre — ça vient.</td></tr>"
    return _page("Classement", f"""
        <h1>Classement des calls</h1>
        <p class=muted>Min. 3 calls scorés · Σ des rendements 24 h réels.</p>
        <table><tr><th>#</th><th>Membre</th><th>Calls</th><th>WR</th><th>Σ ret</th></tr>{lignes}</table>""")


@app.get("/serveur", response_class=HTMLResponse)
def serveur():
    s = stats.server_stats()
    n_membres, n_bots, n_roles = s["n_members"], s["n_bots"], s["n_roles"]
    m24, m7 = s["m24"], s["m7"]
    top = s["top_channels"]
    frais = s["newcomers"]
    topl = "".join(f"<tr><td>#{r['channel_name']}</td><td>{r['n']}</td></tr>" for r in top)
    fraisl = "".join(f"<tr><td>{r['user_name']}</td><td class=muted>{(r['joined_at'] or '?')[:10]}</td></tr>"
                     for r in frais)
    topl = "".join(f"<tr><td>#{r['channel_name']}</td><td>{r['n']}</td></tr>" for r in top)
    fraisl = "".join(f"<tr><td>{r['user_name']}</td><td class=muted>{(r['joined_at'] or '?')[:10]}</td></tr>"
                     for r in frais)
    return _page("Serveur", f"""
        <h1>Le serveur en direct</h1>
        <div class=card>{n_membres} membres humains · {n_bots} bots · {n_roles} rôles connus</div>
        <h2>La capture</h2>
        <div class=card>{m24} message(s) sur 24 h · {m7} sur 7 j</div>
        <h2>Top salons (7 j)</h2>
        <table><tr><th>Salon</th><th>Messages</th></tr>{topl}</table>
        <h2>Derniers arrivés</h2>
        <table><tr><th>Membre</th><th>Arrivé</th></tr>{fraisl}</table>""")


@app.get("/api/me")
def api_me(request: Request):
    uid = _uid_of(request)
    if not uid:
        return JSONResponse({"error": "non connecté"}, status_code=401)
    with _sess_lock:
        s = _sessions().get(uid, {})
    return JSONResponse({"uid": uid, "username": s.get("username")})


if __name__ == "__main__":
    import uvicorn
    errs = []
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        errs.append("DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET manquants dans .env")
    if not DISCORD_GUILD_ID:
        errs.append("DISCORD_GUILD_ID manquant dans .env")
    if errs:
        raise SystemExit("dashboard: " + " · ".join(errs))
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
