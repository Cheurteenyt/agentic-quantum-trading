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
EXIT_THRESHOLD = 2  # ≥ 2 top traders distincts vendent le même token = consensus
STALE_TIMEOUT = 600  # le serveur muet > 10 min = session reconstruite


class SignalEngine:
    """La détection temps réel DANS le daemon (latence < 2 s) :
    la sortie consensus = ≥ N top traders distincts vendent le même token
    dans la fenêtre glissante de 30 min. Idempotent par (token, bucket)."""

    def __init__(self):
        self.sells = []  # [(ts, addr, handle)]
        self.emitted = set()

    def on_top_sell(self, addr, handle, ticker):
        """Retourne le set des handles si un consensus vient de se former."""
        now = time.time()
        self.sells.append((now, addr, handle))
        cutoff = now - 30 * 60
        self.sells = [s for s in self.sells if s[0] > cutoff and s[1] == addr]
        handles = {h for _, _, h in self.sells}
        if len(handles) >= EXIT_THRESHOLD:
            bucket = int(now // (30 * 60))
            key = (addr, bucket)
            if key not in self.emitted:
                self.emitted.add(key)
                if len(self.emitted) > 300:
                    self.emitted = set(list(self.emitted)[-200:])
                return handles
        return None
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
         '    lg = None\n'
         '    for port in ("9223", "9222"):\n'
         '        try:\n'
         '            lg = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=8000)\n'
         '            break\n'
         '        except Exception:\n'
         '            continue\n'
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


def load_top_handles():
    """Les top traders : la config ws_config.json override le défaut codé."""
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    return set(cfg.get("top_handles", TOP_HANDLES)) or TOP_HANDLES


def ensure_dbs():
    con = sqlite3.connect(DB_TICKS, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_ticks (
        mint TEXT, ts_s REAL, priceUsd REAL, captured_at INTEGER)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ticks_mint_ts ON fomo_ticks(mint, ts_s)")
    # les tokens près de graduer (topic pre_graduated_tokens) : le DDL au
    # démarrage — inline dans le flush, il n'a jamais pu s'exécuter
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_pre_graduated (
        mint TEXT, symbol TEXT, name TEXT, market_cap REAL, priceUSD REAL,
        token_created_at TEXT, change24 REAL, captured_at INTEGER,
        PRIMARY KEY (mint, captured_at))""")
    # la MC NATIVE par tick échantillonné (le topic trending/pre_graduated
    # porte marketCap + priceUSD + info.circulatingSupply + holders à
    # l'instant t) : la chart calibrera prix × supply dessus — fin de la
    # MC dérivée ±4-10 % (supply de bonding curve ≠ constante)
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_mc_samples (
        mint TEXT, captured_at INTEGER, market_cap REAL, price_usd REAL,
        supply REAL, holders INTEGER, symbol TEXT,
        PRIMARY KEY (mint, captured_at))""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_mcsample_mint "
                "ON fomo_mc_samples(mint, captured_at DESC)")
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
    con.execute("""CREATE TABLE IF NOT EXISTS ws_theses (
        thesis_id TEXT PRIMARY KEY, trade_id TEXT, user_id TEXT, handle TEXT,
        display_name TEXT, ticker TEXT, token_addr TEXT, network_id TEXT,
        comment TEXT, price_at_creation REAL, mc_at_creation REAL,
        usd_value REAL, token_amount REAL, pnl_unrealized REAL,
        pnl_pct_unrealized REAL, pnl_realized REAL, closed_at TEXT,
        equity REAL, is_dev INTEGER, top_trader INTEGER DEFAULT 0,
        num_replies INTEGER, num_likes INTEGER, parent_id TEXT,
        created_at TEXT, raw TEXT, captured_at INTEGER)""")
    for idx, on in [("idx_th_handle", "handle, captured_at"),
                    ("idx_th_token", "token_addr, captured_at"),
                    ("idx_th_top", "top_trader, captured_at")]:
        con.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON ws_theses({on})")
    con.execute("""CREATE TABLE IF NOT EXISTS ws_events (
        event_id TEXT, event_type TEXT, raw TEXT, captured_at INTEGER,
        PRIMARY KEY (event_id, event_type))""")
    con.execute("""CREATE TABLE IF NOT EXISTS ws_token_details (
        mint TEXT, captured_at INTEGER, change5m REAL, change1h REAL, change24h REAL,
        buys5min INTEGER, buys1h INTEGER, buys24h INTEGER,
        sells5min INTEGER, sells1h INTEGER, sells24h INTEGER,
        volumeBuy5minUSD REAL, volumeBuy1hUSD REAL, volumeBuy24hUSD REAL,
        volumeSell5minUSD REAL, volumeSell1hUSD REAL, volumeSell24hUSD REAL,
        server_ts INTEGER, PRIMARY KEY (mint, captured_at))""")
    con.execute("""CREATE INDEX IF NOT EXISTS idx_tdetail_mint
                   ON ws_token_details(mint, captured_at DESC)""")
    con.execute("""CREATE TABLE IF NOT EXISTS ws_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, started_at INTEGER,
        ended_at INTEGER, n_msgs INTEGER)""")
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
    """Les batchs d'écriture — les connexions persistantes WAL + l'agrégation 1m."""

    def __init__(self):
        self.tick_q, self.swap_q, self.thesis_q, self.event_q = [], [], [], []
        self.tdetail_q, self.ohlcv_q = [], []
        self.universe_q = []
        self.pregrad_q = []
        # les échantillons MC NATIFS (la MC serveur + la supply à l'instant t)
        # + l'état du rate-limiter : mint → (dernier ts, dernière MC)
        self.mc_q = []
        self.last_mc = {}
        self.trader_q = {}
        self.n_new_tokens = 0
        # la dédup : le dernier prix par topic (les frames identiques = ~40 %
        # du flux, zéro information → zéro écriture)
        self.last_px = {}
        # les buffers de bougie 1m : mint → [minute_ts_ms, open, high, low, close]
        # + le volume plateforme : (addr, minute_ts_ms) → la somme des usdAmount
        self.candles = {}
        self.swap_vol = {}
        self.last_minute = int(time.time()) // 60
        self.last_flush = time.time()
        self.n_ticks, self.n_swaps, self.n_top, self.n_sells_top = 0, 0, 0, 0
        self.n_candles, self.n_theses, self.n_events = 0, 0, 0
        self.n_tdetail, self.n_ohlcv, self.n_mc = 0, 0, 0
        self.n_dedup, self.n_errors = 0, 0
        self.unknown_types = set()
        self.con_ticks = sqlite3.connect(DB_TICKS, timeout=30)
        self.con_swaps = sqlite3.connect(DB_SWAPS, timeout=30)

    def add_event(self, p):
        """Le dispatch par type : les swaps, les thèses, et le parking
        des types inconnus (la découverte automatique du flux)."""
        t = p.get("type", "")
        if t in ("swap_buy", "swap_sell"):
            self.add_swap(p)
        elif t == "thesis":
            self.add_thesis(p)
        else:
            eid = p.get("id") or json.dumps(p, sort_keys=True)[:64]
            self.event_q.append((eid, t or "?", json.dumps(p), int(time.time())))
            self.unknown_types.add(t or "?")
            self.n_events += 1

    def add_price(self, topic_id, payload):
        mint = topic_id.rsplit(":", 1)[0]
        ts = payload.get("timestamp") or int(time.time())
        px = payload.get("priceUsd")
        if mint and px is not None:
            px = float(px)
            if self.last_px.get(topic_id) == px:
                self.n_dedup += 1
                return
            self.last_px[topic_id] = px
            self.tick_q.append((mint, float(ts), px, int(time.time())))
            # la bougie 1m en cours
            minute = int(float(ts)) // 60 * 60 * 1000
            c = self.candles.get(mint)
            if c is None or c[0] != minute:
                self.candles[mint] = [minute, px, px, px, px]
            else:
                c[2] = max(c[2], px)
                c[3] = min(c[3], px)
                c[4] = px

    def add_thesis(self, p):
        """Une thèse postée avec un achat : le texte, le MC à la publication,
        le PnL live de l'auteur, les likes/réponses."""
        c = p.get("comment") or {}
        at = p.get("authorTrade") or {}
        handle = p.get("userHandle") or ""
        self.thesis_q.append((
            c.get("id") or p.get("id"), p.get("tradeId"), p.get("userId"), handle,
            p.get("displayName"), p.get("ticker"), p.get("tokenAddress"),
            str(p.get("networkId") or ""), c.get("comment"),
            c.get("priceUsdAtCreation"), c.get("marketCapAtCreation"),
            at.get("usdValue"), at.get("humanTokenAmount"),
            at.get("unrealizedPnlUsd"), at.get("percentageUnrealizedPnl"),
            at.get("realizedPnlUsd"), at.get("closedAt"),
            p.get("equity"), 1 if p.get("isDev") else 0,
            1 if handle in TOP_HANDLES else 0,
            p.get("numReplies"), (c.get("reactions", {}).get("counts") or {}).get("likeCount"),
            c.get("parentId"), c.get("createdAt") or p.get("createdAt"),
            json.dumps(p), int(time.time())))

    @staticmethod
    def _f(v):
        """float ou None (les payloads sévissent en strings)."""
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _mc_sample(self, mint, sym, tk, now):
        """Un échantillon MC natif dans fomo_mc_samples : 1/min/mint ou
        ΔMC ≥ 0,5 % (le firehose update intégral = ~2,5 M lignes/jour)."""
        mc = self._f(tk.get("marketCap"))
        if mc is None:
            return
        last_t, last_mc = self.last_mc.get(mint, (0, None))
        if now - last_t >= 60 or (last_mc and abs(mc - last_mc)
                                  / max(last_mc, 1e-9) >= 0.005):
            self.last_mc[mint] = (now, mc)
            info = (tk.get("token") or {}).get("info") or {}
            self.mc_q.append((mint, now, mc, self._f(tk.get("priceUSD")),
                              self._f(info.get("circulatingSupply")),
                              tk.get("holders"), sym))

    def add_trending(self, payload):
        """Le snapshot trending_tokens : l'upsert de l'univers (le mint,
        le symbole, la MC, le prix) + la découverte des nouveaux tokens.
        Les kind=update (1 token, ~33/s) alimentent aussi les ÉCHANTILLONS
        MC NATIFS (marketCap/priceUSD/circulatingSupply/holders à l'instant
        t) — la correction de la MC dérivée prix × supply constante."""
        kind = payload.get("kind")
        if kind == "snapshot":
            toks = payload.get("tokens", [])
        elif kind == "update":
            u = payload.get("update") or {}
            toks = [u] if u else []
        else:
            return
        now = int(time.time())
        for tk in toks:
            tok = tk.get("token") or {}
            mint, sym = tok.get("address"), tok.get("symbol")
            if not mint or not sym:
                continue
            if kind == "snapshot":
                self.universe_q.append((mint, sym, tok.get("name"),
                                        tk.get("marketCap"), tk.get("priceUSD"),
                                        tk.get("change24"), now))
            self._mc_sample(mint, sym, tk, now)

    def add_pre_graduated(self, payload):
        """Les tokens sur le point de graduer : le mint, l'âge, la MC, le
        prix — l'ETA de graduation = le signal d'entrée le plus rentable
        (+ les échantillons MC natifs : la supply de bonding curve bouge)."""
        if payload.get("kind") != "snapshot":
            return
        now = int(time.time())
        for tk in payload.get("tokens", []):
            tok = tk.get("token") or {}
            mint = tok.get("address")
            if not mint:
                continue
            self.pregrad_q.append((mint, tok.get("symbol"), tok.get("name"),
                                   tk.get("marketCap"), tk.get("priceUSD"),
                                   tk.get("createdAt"), tk.get("change24"),
                                   now))
            self._mc_sample(mint, tok.get("symbol"), tk, now)

    def add_token_details(self, topic_id, payload):
        """La pression par token : les changes %, les nb de buys/sells,
        les volumes achat/vente USD — le sentiment quantifié en direct."""
        mint = topic_id.rsplit(":", 1)[0]
        if not mint:
            return
        self.tdetail_q.append((mint, payload.get("change5m"), payload.get("change1h"),
                               payload.get("change24h"),
                               payload.get("buys5min"), payload.get("buys1h"), payload.get("buys24h"),
                               payload.get("sells5min"), payload.get("sells1h"), payload.get("sells24h"),
                               payload.get("volumeBuy5minUSD"), payload.get("volumeBuy1hUSD"),
                               payload.get("volumeBuy24hUSD"),
                               payload.get("volumeSell5minUSD"), payload.get("volumeSell1hUSD"),
                               payload.get("volumeSell24hUSD"),
                               payload.get("timestamp"), int(time.time())))

    def add_ohlcv(self, p):
        """Les bougies 30s de l'app AVEC le vrai volume DEX."""
        asset = p.get("asset")
        t = p.get("time")
        if not asset or not t:
            return
        self.ohlcv_q.append((asset, p.get("period", "30s"), t,
                             p.get("open"), p.get("high"), p.get("low"), p.get("close"),
                             p.get("volume"), int(time.time())))

    def _acc_volume(self, addr, created, usd):
        """Le volume plateforme : la somme des usdAmount par (token, minute)."""
        if not addr or usd is None:
            return
        try:
            minute = int(time.mktime(time.strptime(
                created[:19], "%Y-%m-%dT%H:%M:%S"))) // 60 * 60 * 1000
            self.swap_vol[(addr, minute)] = \
                self.swap_vol.get((addr, minute), 0.0) + float(usd)
        except Exception:
            pass

    def _track_trader(self, payload, handle):
        """Le mapping handle→userId auto-appris depuis le flux."""
        uid = payload.get("userId")
        if not handle or not uid:
            return
        now_s = int(time.time())
        self.trader_q[uid] = (uid, handle, payload.get("displayName"),
                              payload.get("equity"), now_s, now_s)

    def _swap_row(self, payload):
        """Le tuple typé pour ws_swaps (17 colonnes)."""
        handle = payload.get("userHandle") or ""
        return (
            payload.get("id"), payload.get("tradeId"), payload.get("type") or "",
            payload.get("userId"), payload.get("createdAt") or "",
            json.dumps(payload), int(time.time()),
            handle, payload.get("ticker"), payload.get("tokenAddress"),
            str(payload.get("networkId") or ""), payload.get("usdAmount"),
            payload.get("marketCap"), payload.get("price"),
            payload.get("equity"), 1 if payload.get("isDev") else 0,
            1 if handle in TOP_HANDLES else 0)

    def add_swap(self, payload):
        sid = payload.get("id")
        if not sid:
            return
        handle = payload.get("userHandle") or ""
        is_top = 1 if handle in TOP_HANDLES else 0
        ptype = payload.get("type") or ""
        addr = payload.get("tokenAddress")
        created = payload.get("createdAt") or ""
        self._acc_volume(addr, created, payload.get("usdAmount"))
        self.swap_q.append(self._swap_row(payload))
        self._track_trader(payload, handle)
        if is_top:
            self.n_top += 1
            if ptype == "swap_sell":
                self.n_sells_top += 1

    def _roll_candles(self):
        """Écrit les bougies 1m closes (et injecte le volume plateforme)."""
        now_minute = int(time.time()) // 60
        rows = []
        for mint in list(self.candles):
            c = self.candles[mint]
            if c[0] // 60000 < now_minute:  # la minute est close
                vol = self.swap_vol.get((mint, c[0]), 0.0)
                rows.append((mint, "1m", c[0], c[1], c[2], c[3], c[4], vol,
                             time.time()))
                del self.candles[mint]
        # purge des volumes anciens (> 10 min)
        cutoff = (now_minute - 10) * 60 * 1000
        for key in [k for k in self.swap_vol if k[1] < cutoff]:
            del self.swap_vol[key]
        if rows:
            self.con_ticks.executemany(
                "INSERT OR REPLACE INTO fomo_ohlcv VALUES (?,?,?,?,?,?,?,?,?)", rows)
            self.con_ticks.commit()
            self.n_candles += len(rows)

    def write_exit_signal(self, addr, ticker, handles):
        """Le signal exit_consensus écrit immédiatement (+ le journal)."""
        bucket = int(time.time() // (30 * 60))
        key = f"exit_consensus_rt|{addr}|{bucket}"
        try:
            self.con_swaps.execute(
                "INSERT OR IGNORE INTO ws_signals VALUES (?,?,?,?,?,?,?)",
                (key, "exit_consensus_rt", addr, ticker,
                 json.dumps({"handles": handles, "window_min": 30, "latency": "realtime"}),
                 int(time.time()), int(time.time())))
            self.con_swaps.commit()
        except Exception as e:
            log(f"signal write err : {str(e)[:80]}")
            return
        log(f"⚡⚡ SORTIE CONSENSUS {ticker} : {', '.join(handles)} "
            f"vendent dans la fenêtre 30 min")

    def log_session_start(self):
        """Le journal des sessions : la visibilité des gaps de collecte."""
        try:
            self.con_swaps.execute(
                "INSERT INTO ws_sessions (started_at) VALUES (?)", (int(time.time()),))
            self.con_swaps.commit()
            self._session_row = self.con_swaps.execute(
                "SELECT last_insert_rowid()").fetchone()[0]
        except Exception:
            self._session_row = None

    def log_session_end(self, n_msgs):
        if not getattr(self, "_session_row", None):
            return
        try:
            self.con_swaps.execute(
                "UPDATE ws_sessions SET ended_at=?, n_msgs=? WHERE id=?",
                (int(time.time()), n_msgs, self._session_row))
            self.con_swaps.commit()
        except Exception:
            pass
        self._session_row = None

    def flush(self):
        now = time.time()
        if now - self.last_flush < 2:
            return
        try:
            self._flush_locked()
        except sqlite3.OperationalError as e:
            # la DB verrouillée/occupée : les queues restent en mémoire,
            # le flush suivant re-tentera — la session ne meurt JAMAIS d'un flush
            log(f"flush différé ({str(e)[:80]})")
        except Exception as e:
            self.n_errors += 1
            log(f"flush err (#{self.n_errors}) : {str(e)[:100]}")
        self.last_flush = now

    def _flush_locked(self):
        self._roll_candles()
        if self.tick_q:
            self.con_ticks.executemany(
                "INSERT OR REPLACE INTO fomo_ticks VALUES (?,?,?,?)", self.tick_q)
            self.con_ticks.commit()
            self.n_ticks += len(self.tick_q); self.tick_q = []
        if self.ohlcv_q:
            self.con_ticks.executemany(
                "INSERT OR REPLACE INTO fomo_ohlcv VALUES (?,?,?,?,?,?,?,?,?)", self.ohlcv_q)
            self.con_ticks.commit()
            self.n_ohlcv += len(self.ohlcv_q); self.ohlcv_q = []
        if self.universe_q:
            con_u = self.con_ticks
            con_u.execute("PRAGMA busy_timeout=30000")
            new_m = 0
            for row in self.universe_q:
                exists = con_u.execute(
                    "SELECT 1 FROM fomo_tokens WHERE mint=?", (row[0],)).fetchone()
                con_u.execute(
                    "INSERT OR REPLACE INTO fomo_tokens (ticker, mint, resolved_at) "
                    "VALUES (?,?,?)", (row[1], row[0], row[6]))
                if not exists:
                    new_m += 1
                    try:
                        mc_f = float(row[3]) if row[3] else 0
                        log(f"🆕 token découvert : {row[1]} ({row[0][:10]}…, "
                            f"MC ${mc_f:,.0f})")
                    except Exception:
                        log(f"🆕 token découvert : {row[1]}")
            con_u.commit()  # JAMAIS close() : con_ticks est partagé (510f57f)
            self.n_new_tokens += new_m
            self.universe_q = []
        if self.pregrad_q:
            try:
                self.con_ticks.executemany(
                    "INSERT OR REPLACE INTO fomo_pre_graduated VALUES (?,?,?,?,?,?,?,?)",
                    self.pregrad_q)
                self.con_ticks.commit()
                self.pregrad_q = []
            except sqlite3.Error as e:
                # l'échec n'est plus avalé : log + queue conservée pour le retry
                log(f"pregrad : {len(self.pregrad_q)} frames différées "
                    f"({str(e)[:80]})")
        if self.mc_q:
            self.con_ticks.executemany(
                "INSERT OR IGNORE INTO fomo_mc_samples (mint, captured_at, "
                "market_cap, price_usd, supply, holders, symbol) "
                "VALUES (?,?,?,?,?,?,?)", self.mc_q)
            self.con_ticks.commit()
            self.n_mc += len(self.mc_q); self.mc_q = []
        if self.tdetail_q:
            self.con_swaps.executemany(
                "INSERT OR REPLACE INTO ws_token_details VALUES (?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?)", self.tdetail_q)
            self.con_swaps.commit()
            self.n_tdetail += len(self.tdetail_q); self.tdetail_q = []
        if self.swap_q:
            self.con_swaps.executemany(
                "INSERT OR IGNORE INTO ws_swaps VALUES (?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?)", self.swap_q)
            self.con_swaps.commit()
            self.n_swaps += len(self.swap_q); self.swap_q = []
        if self.thesis_q:
            self.con_swaps.executemany(
                "INSERT OR IGNORE INTO ws_theses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,"
                "?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self.thesis_q)
            self.con_swaps.commit()
            self.n_theses += len(self.thesis_q); self.thesis_q = []
        if self.event_q:
            self.con_swaps.executemany(
                "INSERT OR IGNORE INTO ws_events VALUES (?,?,?,?)", self.event_q)
            self.con_swaps.commit()
            self.event_q = []
        if self.trader_q:
            self.con_swaps.executemany(
                "INSERT INTO ws_traders (user_id, handle, display_name, "
                "equity_last, first_seen, last_seen) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET handle=excluded.handle, "
                "display_name=excluded.display_name, equity_last=excluded.equity_last, "
                "last_seen=excluded.last_seen",
                list(self.trader_q.values()))
            self.con_swaps.commit()
            self.trader_q = {}


class HotSet:
    """Les topics prices : les ÉPINGLÉS (les tokens des top traders — jamais
    évincés, la série prix de leurs positions = critique) + le LRU du reste."""

    def __init__(self, seed_mints):
        self.pinned = set()
        self.lru = OrderedDict()
        self.chain = lambda m: CHAIN_EVM if m.startswith("0x") else CHAIN_SOL
        for m in seed_mints:
            self.lru[m] = None
        self.pending = list(self.lru.keys())

    def touch(self, mint):
        """Le flux trade un token : le replacer en LRU (ou l'ajouter si la place).
        Retourne (nouveau_topic | None, évincé | None)."""
        if mint in self.pinned or mint in self.lru:
            if mint in self.lru:
                self.lru.move_to_end(mint)
            return None, None
        evicted = None
        if len(self.lru) + len(self.pinned) >= MAX_PRICE_TOPICS:
            if self.lru:
                evicted, _ = self.lru.popitem(last=False)
            else:
                return None, None  # tout est épinglé — le budget est saturé
        self.lru[mint] = None
        self.pending.append(mint)
        return mint, evicted

    def pin(self, mint):
        """Épingler un token top-trader : le sortir du LRU, jamais évincé."""
        if mint in self.pinned:
            return None
        new = None
        if mint in self.lru:
            del self.lru[mint]
        elif len(self.lru) + len(self.pinned) < MAX_PRICE_TOPICS:
            new = mint
        self.pinned.add(mint)
        self.pending.append(mint)
        return new

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
        # le snapshot global des tokens trending (toutes les chains) : la
        # découverte automatique des nouveaux tokens + leurs métadonnées
        await ws.send(json.dumps({"type": "subscribe", "topicType": "trending_tokens",
                                  "topicId": "1,56,143,4663,5042,8453,1399811149"}))
        await asyncio.sleep(PACING)
        # les tokens PRÈS DE GRADUER (la bonding quasi-complète) : le flux
        # natif du prédicteur de graduation — le trade ×9 du projet
        await ws.send(json.dumps({"type": "subscribe", "topicType": "pre_graduated_tokens",
                                  "topicId": "1,56,143,4663,5042,8453,1399811149"}))
        await asyncio.sleep(PACING)
        for m in list(hot.lru.keys()):
            await ws.send(json.dumps({"type": "subscribe", "topicType": "prices",
                                      "topicId": hot.topic(m)}))
            await asyncio.sleep(PACING)
        log(f"subscribe : le feed swaps + {len(hot.lru)} topics prices")

        n_recv, t0, last_summary = 0, time.time(), time.time()
        signals = SignalEngine()
        writer.log_session_start()
        # la boucle recv avec le watchdog : le serveur muet > STALE_TIMEOUT s
        # = la session reconstruite (un feed mort ne déclenche pas ping)
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=STALE_TIMEOUT)
            except asyncio.TimeoutError:
                raise RuntimeError(f"silence du serveur > {STALE_TIMEOUT}s — session reconstruite")
            try:
                m = json.loads(raw)
            except Exception:
                continue
            try:
                t = m.get("type")
                if t == "data":
                    tt = m.get("topicType", "")
                    if tt == "prices":
                        writer.add_price(m.get("topicId", ""), m.get("payload", {}))
                    elif tt == "trending_tokens":
                        writer.add_trending(m.get("payload", {}))
                    elif tt == "pre_graduated_tokens":
                        writer.add_pre_graduated(m.get("payload", {}))
                    elif tt == "token_details":
                        writer.add_token_details(m.get("topicId", ""), m.get("payload", {}))
                    elif tt == "ohlcv":
                        writer.add_ohlcv(m.get("payload", {}))
                    elif tt == "trading_activity":
                        p = m.get("payload", {})
                        writer.add_event(p)
                        addr = p.get("tokenAddress")
                        # un top trader trade un token → ÉPINGLER sa série prix
                        # + la PRESSION (token_details) + le VOLUME (ohlcv)
                        if addr and (p.get("userHandle") or "") in TOP_HANDLES:
                            new = hot.pin(addr)
                            if new:
                                for ttype in ("prices", "token_details", "ohlcv"):
                                    await ws.send(json.dumps(
                                        {"type": "subscribe", "topicType": ttype,
                                         "topicId": hot.topic(new)}))
                                    await asyncio.sleep(PACING)
                            # la sortie consensus, en DIRECT (< 2 s)
                            if p.get("type") == "swap_sell":
                                handles = signals.on_top_sell(addr, p.get("userHandle"),
                                                              p.get("ticker"))
                                if handles:
                                    writer.write_exit_signal(
                                        addr, p.get("ticker"), sorted(handles))
                        # la découverte : le token trade → le prix en direct
                        elif addr and addr not in hot.lru and addr not in hot.pinned:
                            new, ev = hot.touch(addr)
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
            except websockets.exceptions.ConnectionClosed:
                raise
            except Exception as e:
                # une anomalie de payload ne tue JAMAIS la session
                writer.n_errors += 1
                log(f"msg handler err (#{writer.n_errors}) : {str(e)[:100]}")
            writer.flush()
            if time.time() - last_summary > SUMMARY_EVERY:
                writer.flush()
                log(f"résumé 10 min : {n_recv} msgs | ticks={writer.n_ticks} "
                    f"(dédup={writer.n_dedup}) bougies1m={writer.n_candles} "
                    f"swaps={writer.n_swaps} (top={writer.n_top}, "
                    f"sorties_top={writer.n_sells_top}) "
                    f"mc_samples={writer.n_mc} "
                    f"thèses={writer.n_theses} types_inconnus={writer.n_events} "
                    f"{sorted(writer.unknown_types) if writer.unknown_types else ''} "
                    f"errs={writer.n_errors} "
                    f"| topics={len(hot.lru)}+{len(hot.pinned)}épinglés")
                last_summary = time.time()
            if run_until_ts and time.time() > run_until_ts:
                writer.flush()
                return n_recv, time.time() - t0


async def daemon_loop(user_uuid, seed_mints, writer, run_until_ts=None):
    backoff = 5
    while True:
        try:
            n, dur = await session(user_uuid, seed_mints, writer, run_until_ts)
            writer.log_session_end(n)
            if run_until_ts:
                return n, dur
        except Exception as e:
            writer.log_session_end(-1)
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
    global TOP_HANDLES
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
    TOP_HANDLES = load_top_handles()
    log(f"daemon v3.1 : user={user_uuid[:8]}…, {len(mints)} mints seed, "
        f"budget {MAX_PRICE_TOPICS} topics, {len(TOP_HANDLES)} top traders, "
        f"once={once is not None}")
    writer = Writer()
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    if once:
        n, dur = await daemon_loop(user_uuid, mints, writer, run_until_ts=once)
        log(f"TEST TERMINÉ : {n} messages en {dur:.0f}s → {writer.n_ticks} ticks, "
            f"{writer.n_swaps} swaps (top={writer.n_top}, sorties_top={writer.n_sells_top}), "
            f"{writer.n_theses} thèses, {writer.n_events} types inconnus "
            f"{sorted(writer.unknown_types) if writer.unknown_types else ''}")
    else:
        await daemon_loop(user_uuid, mints, writer)


if __name__ == "__main__":
    asyncio.run(main())
