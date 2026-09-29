#!/usr/bin/env python3
"""Daemon WebSocket fomo v2 — le collecteur temps réel SANS navigateur.

Protocole (cracké 2026-09-29) :
  wss://prod-api.fomo.family/ws + Origin/User-Agent navigateur (sinon fermeture muette)
  serveur → {"type":"challenge"}  client → {"type":"challengeResponse","jwt":<privy JWT>}
  subscribe/unsubscribe : {"type":..., "topicType":..., "topicId":...}
  plafond : ~80 topics/session ; pacing 0.05 s sinon rate-limit

ARCHITECTURE v2 :
  - trading_activity/<uuid-user-logué> = le FLUX GLOBAL des swaps de toute la
    plateforme (payload : handle, userId, type buy/sell, ticker, tokenAddress,
    usdAmount, marketCap, price, equity du trader)
  - ws_swaps : les colonnes typées + le flag top_trader (les 8 meilleurs)
  - ws_traders : le mapping handle→userId auto-appris depuis le flux
  - PRICES : le hot set LRU — les tokens actifs vus dans le flux s'abonnent
    automatiquement, les froids sont désabonnés (budget 78 topics)
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
from collections import OrderedDict
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

# le budget des topics prices (le trading_activity = 1 de plus, la marge serveur)
MAX_PRICE_TOPICS = 78
SEED_MINTS = 40
PACING = 0.05
SUMMARY_EVERY = 600


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
    log(f"le JWT rafraîchi (exp dans {jwt_exp(jwt)-int(time.time())}s)")
    return jwt


def load_config():
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if "user_uuid" not in cfg:
        raise RuntimeError("ws_config.json sans user_uuid — lancer --discover-uuid")
    con = sqlite3.connect(DB_TICKS)
    mints = [r[0] for r in con.execute(
        "SELECT DISTINCT mint FROM fomo_tokens WHERE mint IS NOT NULL "
        "ORDER BY resolved_at DESC LIMIT ?", (SEED_MINTS,))]
    con.close()
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
    con.execute("""CREATE TABLE IF NOT EXISTS ws_traders (
        user_id TEXT PRIMARY KEY, handle TEXT, display_name TEXT,
        equity_last REAL, first_seen INTEGER, last_seen INTEGER)""")
    # la migration v2 : les colonnes typées de ws_swaps
    cols = {r[1] for r in con.execute("PRAGMA table_info(ws_swaps)")}
    for name, decl in [
            ("handle", "TEXT"), ("ticker", "TEXT"), ("token_addr", "TEXT"),
            ("network_id", "TEXT"), ("usd_amount", "REAL"), ("market_cap", "REAL"),
            ("price", "REAL"), ("trader_equity", "REAL"), ("is_dev", "INTEGER"),
            ("top_trader", "INTEGER DEFAULT 0")]:
        if name not in cols:
            con.execute(f"ALTER TABLE ws_swaps ADD COLUMN {name} {decl}")
    # les index d'exploitation (les sorties des top traders = LA requête chaude)
    for idx, on in [("idx_ws_type", "type, captured_at"),
                    ("idx_ws_handle", "handle, captured_at"),
                    ("idx_ws_token", "token_addr, captured_at"),
                    ("idx_ws_top", "top_trader, type, captured_at")]:
        con.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON ws_swaps({on})")
    con.commit(); con.close()


TOP_HANDLES = {"unipcs", "pointfarmcap", "DumbCrayonEater", "Salem1299534",
               "The__Solstice", "theveeman", "AvgJoesCrypto", "frankdegods"}


class Writer:
    """Les batchs d'écriture — les connexions persistantes WAL."""

    def __init__(self):
        self.tick_q, self.swap_q, self.trader_q = [], [], {}
        self.last_flush = time.time()
        self.n_ticks, self.n_swaps, self.n_top, self.n_sells_top = 0, 0, 0, 0
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
        handle = payload.get("userHandle") or ""
        is_top = 1 if handle in TOP_HANDLES else 0
        ptype = payload.get("type") or ""
        self.swap_q.append((
            sid, payload.get("tradeId"), ptype, payload.get("userId"),
            payload.get("createdAt"), json.dumps(payload), int(time.time()),
            handle, payload.get("ticker"), payload.get("tokenAddress"),
            str(payload.get("networkId") or ""), payload.get("usdAmount"),
            payload.get("marketCap"), payload.get("price"),
            payload.get("equity"), 1 if payload.get("isDev") else 0, is_top))
        if handle:
            uid = payload.get("userId")
            if uid:
                self.trader_q[uid] = (uid, handle, payload.get("displayName"),
                                      payload.get("equity"), int(time.time()))
        if is_top:
            self.n_top += 1
            if ptype == "swap_sell":
                self.n_sells_top += 1

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
                "INSERT OR IGNORE INTO ws_swaps VALUES (?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?)", self.swap_q)
            self.con_swaps.commit()
            self.n_swaps += len(self.swap_q); self.swap_q = []
        if self.trader_q:
            self.con_swaps.executemany(
                "INSERT INTO ws_traders VALUES (?,?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET handle=excluded.handle, "
                "display_name=excluded.display_name, equity_last=excluded.equity_last, "
                "last_seen=excluded.last_seen",
                list(self.trader_q.values()))
            self.con_swaps.commit()
            self.trader_q = {}
        self.last_flush = now


class HotSet:
    """Le LRU des topics prices : subscribe le chaud, unsubscribe le froid."""

    def __init__(self, seed_mints):
        self.lru = OrderedDict()
        self.chain = lambda m: CHAIN_EVM if m.startswith("0x") else CHAIN_SOL
        for m in seed_mints:
            self.lru[m] = None
        self.pending = list(self.lru.keys())

    def touch(self, mint):
        if mint in self.lru:
            self.lru.move_to_end(mint)
            return None
        evicted = None
        if len(self.lru) >= MAX_PRICE_TOPICS:
            evicted, _ = self.lru.popitem(last=False)
        self.lru[mint] = None
        self.pending.append(mint)
        return evicted

    def topic(self, mint):
        return f"{mint}:{self.chain(mint)}"


async def session(user_uuid, seed_mints, writer, run_until_ts=None):
    jwt = read_jwt()
    hot = HotSet(seed_mints)
    log(f"connexion {WSS} …")
    async with websockets.connect(WSS, additional_headers=HEADERS,
                                  max_size=10*1024*1024, ping_interval=20) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        if json.loads(raw).get("type") != "challenge":
            raise RuntimeError(f"pas de challenge : {raw[:100]}")
        await ws.send(json.dumps({"type": "challengeResponse", "jwt": jwt}))
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        if json.loads(raw).get("type") != "challengeAccepted":
            raise RuntimeError(f"auth refusée : {raw[:150]}")
        log("auth acceptée")

        await ws.send(json.dumps({"type": "subscribe", "topicType": "trading_activity",
                                  "topicId": user_uuid}))
        await asyncio.sleep(PACING)
        for m in list(hot.lru.keys()):
            await ws.send(json.dumps({"type": "subscribe", "topicType": "prices",
                                      "topicId": hot.topic(m)}))
            await asyncio.sleep(PACING)
        log(f"subscribe : le feed swaps + {len(hot.lru)} topics prices")

        n_recv, t0, last_summary = 0, time.time(), time.time()
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
                    p = m.get("payload", {})
                    writer.add_swap(p)
                    # la découverte : le token trade → le prix en direct
                    addr = p.get("tokenAddress")
                    if addr and addr not in hot.lru:
                        ev = hot.touch(addr)
                        if ev:
                            await ws.send(json.dumps(
                                {"type": "unsubscribe", "topicType": "prices",
                                 "topicId": hot.topic(ev)}))
                            await asyncio.sleep(PACING)
                        while hot.pending:
                            nm = hot.pending.pop(0)
                            await ws.send(json.dumps(
                                {"type": "subscribe", "topicType": "prices",
                                 "topicId": hot.topic(nm)}))
                            await asyncio.sleep(PACING)
            elif t in ("error", "challengeRejected"):
                raise RuntimeError(f"le serveur : {raw[:160]}")
            n_recv += 1
            writer.flush()
            if time.time() - last_summary > SUMMARY_EVERY:
                writer.flush()
                log(f"résumé 10 min : {n_recv} msgs | ticks={writer.n_ticks} "
                    f"swaps={writer.n_swaps} (top={writer.n_top}, "
                    f"sorties_top={writer.n_sells_top}) | topics prices={len(hot.lru)}")
                last_summary = time.time()
            if run_until_ts and time.time() > run_until_ts:
                writer.flush()
                return n_recv, time.time() - t0


async def daemon_loop(user_uuid, seed_mints, writer, run_until_ts=None):
    backoff = 5
    while True:
        try:
            n, dur = await session(user_uuid, seed_mints, writer, run_until_ts)
            if run_until_ts:
                return n, dur
        except Exception as e:
            log(f"session perdue : {str(e)[:120]} → reconnexion dans {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)
        else:
            backoff = 5


async def discover_uuid():
    """L'UUID du user logué = lu dans les SUBSCRIBE du navigateur au reload."""
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
    log(f"daemon v2 : user={user_uuid[:8]}…, {len(mints)} mints seed, "
        f"budget {MAX_PRICE_TOPICS} topics, once={once is not None}")
    writer = Writer()
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    if once:
        n, dur = await daemon_loop(user_uuid, mints, writer, run_until_ts=once)
        log(f"TEST TERMINÉ : {n} messages en {dur:.0f}s → {writer.n_ticks} ticks, "
            f"{writer.n_swaps} swaps (top={writer.n_top}, sorties_top={writer.n_sells_top})")
    else:
        await daemon_loop(user_uuid, mints, writer)


if __name__ == "__main__":
    asyncio.run(main())
