#!/usr/bin/env python3
"""Daemon WebSocket fomo — le collecteur temps réel SANS navigateur.

Protocole cracké (2026-09-29) :
  wss://prod-api.fomo.family/ws + headers Origin/User-Agent navigateur
  serveur → {"type":"challenge"}   client → {"type":"challengeResponse","jwt":<privy JWT>}
  puis subscribe : {"type":"subscribe","topicType":..., "topicId":...}
  topics : trading_activity/<uuid-user-logué> = le flux global des swaps
           prices/<mint>:<chain> = les prix par token (chain 1399811149 Solana, 4663 EVM)

Le JWT : cache fichier + refresh via CDP (le localStorage du login window :9223).
L'UUID user : config data/fomo/ws_config.json (--discover-uuid = la résolution auto).
Stockage : fomo_ticks (prix) + fomo_swaps.db ws_swaps (swaps temps réel).
"""
import asyncio
import base64
import fcntl
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
WSS = "wss://prod-api.fomo.family/ws"
HEADERS = {"Origin": "https://fomo.family",
           "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"}
DB_TICKS = ROOT / "data" / "fomo" / "fomo.db"
DB_SWAPS = ROOT / "data" / "fomo" / "fomo_swaps.db"
JWT_CACHE = ROOT / "data" / "fomo" / "ws_jwt_cache.txt"
CONFIG = ROOT / "data" / "fomo" / "ws_config.json"
LOCK = ROOT / "data" / "fomo" / ".ws_daemon.lock"
CHAIN_SOL, CHAIN_EVM = "1399811149", "4663"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def jwt_exp(jwt):
    try:
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p)).get("exp", 0)
    except Exception:
        return 0


def read_jwt():
    """Le JWT du cache, refresh CDP si périmé (< 10 min)."""
    if JWT_CACHE.exists():
        jwt = JWT_CACHE.read_text().strip().strip('"')
        if jwt_exp(jwt) > time.time() + 600:
            return jwt
    log("le JWT cache absent/périmé → refresh via CDP")
    r = subprocess.run(
        [sys.executable, "-c",
         'import sys; sys.path.insert(0, r"' + str(ROOT) + '");\n'
         'from patchright.sync_api import sync_playwright\n'
         'pw = sync_playwright().start()\n'
         'try:\n'
         '    lg = pw.chromium.connect_over_cdp("http://127.0.0.1:9223", timeout=8000)\n'
         '    cx = lg.contexts[0] if lg.contexts else lg\n'
         '    pg = next((p for p in cx.pages if "fomo.family" in (p.url or "")), None)\n'
         '    print((pg.evaluate("() => localStorage.getItem(\'privy:token\')") or "").strip().strip(chr(34)))\n'
         'finally:\n'
         '    pw.stop()\n'],
        capture_output=True, text=True, timeout=90)
    jwt = r.stdout.strip().strip('"')
    if len(jwt) < 100:
        raise RuntimeError(f"le JWT illisible via CDP : {r.stdout[:80]} {r.stderr[:120]}")
    JWT_CACHE.write_text(jwt)
    log(f"le JWT rafraîchi ({len(jwt)} chars, exp dans {jwt_exp(jwt)-int(time.time())}s)")
    return jwt


def load_config():
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if "user_uuid" not in cfg:
        raise RuntimeError("ws_config.json sans user_uuid — lancer --discover-uuid")
    con = sqlite3.connect(DB_TICKS)
    mints = [r[0] for r in con.execute(
        "SELECT DISTINCT mint FROM fomo_tokens WHERE mint IS NOT NULL "
        "ORDER BY resolved_at DESC LIMIT 40")]
    con.close()
    if "So11111111111111111111111111111111111111112" not in mints:
        mints.append("So11111111111111111111111111111111111111112")
    return cfg["user_uuid"], mints


def ensure_dbs():
    con = sqlite3.connect(DB_TICKS, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_ticks (
        mint TEXT, ts_s REAL, priceUsd REAL, captured_at INTEGER)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ticks_mint_ts ON fomo_ticks(mint, ts_s)")
    con.commit(); con.close()
    con = sqlite3.connect(DB_SWAPS, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    con.execute("""CREATE TABLE IF NOT EXISTS ws_swaps (
        swap_id TEXT PRIMARY KEY, trade_id TEXT, type TEXT, user_id TEXT,
        created_at TEXT, raw TEXT, captured_at INTEGER)""")
    con.commit(); con.close()


class Writer:
    """Les batches d'écriture — connexions persistantes, OR REPLACE sur le PK ticks."""

    def __init__(self):
        self.tick_q, self.swap_q = [], []
        self.last_flush = time.time()
        self.n_ticks, self.n_swaps = 0, 0
        self.con_ticks = sqlite3.connect(DB_TICKS, timeout=30)
        self.con_swaps = sqlite3.connect(DB_SWAPS, timeout=30)

    def add_price(self, topic_id, payload):
        mint = topic_id.rsplit(":", 1)[0]
        ts = payload.get("timestamp") or int(time.time())
        px = payload.get("priceUsd")
        if mint and px is not None:
            self.tick_q.append((mint, float(ts), float(px), int(time.time())))

    def add_swap(self, payload):
        sid = payload.get("id")
        if not sid:
            return
        self.swap_q.append((sid, payload.get("tradeId"), payload.get("type"),
                            payload.get("userId"), payload.get("createdAt"),
                            json.dumps(payload), int(time.time())))

    def flush(self):
        now = time.time()
        if now - self.last_flush < 2:
            return
        if self.tick_q:
            self.con_ticks.executemany(
                "INSERT OR REPLACE INTO fomo_ticks VALUES (?,?,?,?)", self.tick_q)
            self.con_ticks.commit()
            self.n_ticks += len(self.tick_q); self.tick_q = []
        if self.swap_q:
            self.con_swaps.executemany(
                "INSERT OR IGNORE INTO ws_swaps VALUES (?,?,?,?,?,?,?)", self.swap_q)
            self.con_swaps.commit()
            self.n_swaps += len(self.swap_q); self.swap_q = []
        self.last_flush = now


async def run_session(user_uuid, mints, writer, run_until_ts=None):
    jwt = read_jwt()
    log(f"connexion {WSS} …")
    async with websockets.connect(WSS, additional_headers=HEADERS,
                                  max_size=10*1024*1024, ping_interval=20) as ws:
        # auth
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        if json.loads(raw).get("type") != "challenge":
            raise RuntimeError(f"pas de challenge : {raw[:100]}")
        await ws.send(json.dumps({"type": "challengeResponse", "jwt": jwt}))
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        if json.loads(raw).get("type") != "challengeAccepted":
            raise RuntimeError(f"auth refusée : {raw[:150]}")
        log("auth acceptée")

        # subscribe : le feed global des swaps + les prix (pacing anti-rate-limit)
        await ws.send(json.dumps({"type": "subscribe", "topicType": "trading_activity",
                                  "topicId": user_uuid}))
        await asyncio.sleep(0.4)
        for m in mints:
            chain = CHAIN_EVM if m.startswith("0x") else CHAIN_SOL
            await ws.send(json.dumps({"type": "subscribe", "topicType": "prices",
                                      "topicId": f"{m}:{chain}"}))
            await asyncio.sleep(0.25)
        log(f"subscribe : trading_activity + {len(mints)} topics prices (pacing 0.25s)")

        n_recv, t0 = 0, time.time()
        async for raw in ws:
            try:
                m = json.loads(raw)
            except Exception:
                continue
            t = m.get("type")
            if t == "data":
                tt = m.get("topicType", "")
                if tt == "prices":
                    writer.add_price(m.get("topicId", ""), m.get("payload", {}))
                elif tt == "trading_activity":
                    writer.add_swap(m.get("payload", {}))
            elif t in ("error", "challengeRejected"):
                raise RuntimeError(f"le serveur : {raw[:150]}")
            n_recv += 1
            writer.flush()
            if run_until_ts and time.time() > run_until_ts:
                writer.flush()
                return n_recv, time.time() - t0
            if n_recv % 5000 == 0:
                writer.flush()
                log(f"  {n_recv} messages reçus, {writer.n_ticks} ticks, {writer.n_swaps} swaps")


async def daemon_loop(user_uuid, mints, writer, run_until_ts=None):
    backoff = 5
    while True:
        try:
            n, dur = await run_session(user_uuid, mints, writer, run_until_ts)
            if run_until_ts:
                return n, dur
        except Exception as e:
            log(f"session perdue : {str(e)[:120]} → reconnexion dans {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)
            # le JWT peut expirer pendant l'attente → read_jwt le raffraîchit
        else:
            backoff = 5


async def discover_uuid():
    """L'UUID du user logué = lu dans les SENT du navigateur au reload."""
    import urllib.request
    ver = json.loads(urllib.request.urlopen("http://127.0.0.1:9223/json/version").read())
    burl = ver["webSocketDebuggerUrl"]
    found = {}

    async def main():
        ws = await websockets.connect(burl, max_size=50*1024*1024)
        mid = 0
        reload_done = False

        async def send(method, params=None, sid=None):
            nonlocal mid
            mid += 1
            msg = {"id": mid, "method": method, "params": params or {}}
            if sid:
                msg["sessionId"] = sid
            await ws.send(json.dumps(msg))

        async def reader():
            nonlocal reload_done
            async for raw in ws:
                m = json.loads(raw)
                meth, p = m.get("method", ""), m.get("params", {})
                sid = m.get("sessionId", "")
                if meth == "Target.attachedToTarget":
                    ti = p["targetInfo"]
                    await send("Network.enable", {}, p["sessionId"])
                    await send("Target.setAutoAttach",
                               {"autoAttach": True, "waitForDebuggerOnStart": False,
                                "flatten": True}, p["sessionId"])
                    if ti["type"] == "page" and "fomo.family" in ti["url"] and not reload_done:
                        reload_done = True
                        await asyncio.sleep(1)
                        await send("Page.reload", {}, p["sessionId"])
                elif meth == "Network.webSocketFrameSent":
                    d = p.get("response", {}).get("payloadData", "")
                    if '"trading_activity"' in d and '"subscribe"' in d:
                        obj = json.loads(d)
                        found[obj.get("topicId")] = True
                        print(f"  topic du user : {obj.get('topicId')}", flush=True)

        rd = asyncio.create_task(reader())
        await send("Target.setAutoAttach",
                   {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
        await asyncio.sleep(25)
        rd.cancel()
        if found:
            CONFIG.write_text(json.dumps({"user_uuid": list(found)[0]}))
            print(f"config écrite : {CONFIG}", flush=True)
        os._exit(0)

    await main()
    os._exit(0 if found else 1)


async def main():
    ap = sys.argv[1:] if len(sys.argv) > 1 else []
    if "--discover-uuid" in ap:
        return await discover_uuid()
    once = None
    if "--once" in ap:
        once = time.time() + int(ap[ap.index("--once") + 1])

    lk = open(LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("déjà en cours — stop")
        return
    ensure_dbs()
    user_uuid, mints = load_config()
    log(f"daemon : user={user_uuid[:8]}…, {len(mints)} mints, once={once is not None}")
    writer = Writer()

    # le SIGTERM = l'arrêt net (le flush perdu <2s = acceptable ; évite les orphelins)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    if once:
        n, dur = await daemon_loop(user_uuid, mints, writer, run_until_ts=once)
        log(f"TEST TERMINÉ : {n} messages en {dur:.0f}s → {writer.n_ticks} ticks, "
            f"{writer.n_swaps} swaps")
    else:
        await daemon_loop(user_uuid, mints, writer)


if __name__ == "__main__":
    asyncio.run(main())
