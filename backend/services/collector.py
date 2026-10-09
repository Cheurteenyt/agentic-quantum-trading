"""
Hyperliquid Data Collector — Service intégré FastAPI
=====================================================
Connecte au WebSocket Hyperliquid, collecte orderbook/trades/CVD/OI,
écrit les snapshots dans data/snapshots/.

Intégré comme asyncio.create_task dans le lifespan de FastAPI.
Plus besoin de processus séparé.
"""

import asyncio
import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger("collector")
    logger.setLevel(logging.INFO)

# Lazy import to avoid circular dependency
footprint_manager = None
smart_engine = None

def _get_footprint_manager():
    global footprint_manager
    if footprint_manager is None:
        from services.footprint import manager as fm
        footprint_manager = fm
    return footprint_manager

def _get_smart_engine():
    global smart_engine
    if smart_engine is None:
        from services.smart_engine import engine as se
        smart_engine = se
    return smart_engine


HL_WS_URL = "wss://api.hyperliquid.xyz/ws"
SNAPSHOT_DIR = Path("data/snapshots")
LOG_DIR = Path("data/logs")

SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# STATE SHARED WITH FASTAPI
# =========================================================

class CollectorState:
    """État du collector — accessible depuis les endpoints FastAPI."""

    def __init__(self):
        self.connected = False
        self.coins = []
        self.last_message_ts = 0
        self.message_count = 0
        self.errors = []
        self.started_at = 0
        self.markets = {}

    @property
    def status(self) -> dict:
        age = time.time() - self.last_message_ts if self.last_message_ts else None
        return {
            "connected": self.connected,
            "coins": self.coins,
            "message_count": self.message_count,
            "last_message_age_sec": round(age, 1) if age else None,
            "uptime_sec": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "recent_errors": self.errors[-5:],
        }


state = CollectorState()


# =========================================================
# MARKET STATE
# =========================================================

class MarketState:
    def __init__(self, coin: str):
        self.coin = coin
        self.orderbook = {"bids": [], "asks": [], "ts": 0}
        self.trades = deque(maxlen=500)
        self.liquidations = deque(maxlen=100)
        self.oi = {"value": 0.0, "ts": 0}
        self.cvd = 0.0
        self.last_price = 0.0
        self.updated_at = 0.0

    def _level_px_sz(self, level):
        try:
            if isinstance(level, dict):
                px = level.get("px", level.get("price", 0))
                sz = level.get("sz", level.get("size", 0))
                return float(px), float(sz)
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                return float(level[0]), float(level[1])
        except (TypeError, ValueError):
            pass
        return 0.0, 0.0

    def _spread(self) -> float:
        try:
            if not self.orderbook["bids"] or not self.orderbook["asks"]:
                return 0.0
            best_bid_px, _ = self._level_px_sz(self.orderbook["bids"][0])
            best_ask_px, _ = self._level_px_sz(self.orderbook["asks"][0])
            if best_bid_px > 0 and best_ask_px > 0:
                return round(best_ask_px - best_bid_px, 4)
        except Exception:
            pass
        return 0.0

    def _metrics(self) -> dict:
        if not self.trades:
            return {}
        recent = list(self.trades)[-100:]
        buy_vol = sum(float(t["sz"]) for t in recent if t.get("side") == "B")
        sell_vol = sum(float(t["sz"]) for t in recent if t.get("side") == "A")
        total = buy_vol + sell_vol
        ob_imb = 0.0
        try:
            bid_levels = self.orderbook.get("bids", [])[:5]
            ask_levels = self.orderbook.get("asks", [])[:5]
            bv = sum(self._level_px_sz(level)[1] for level in bid_levels)
            av = sum(self._level_px_sz(level)[1] for level in ask_levels)
            if bv + av > 0:
                ob_imb = round((bv - av) / (bv + av), 4)
        except Exception:
            pass
        return {
            "buy_vol_100": round(buy_vol, 4),
            "sell_vol_100": round(sell_vol, 4),
            "delta_100": round(buy_vol - sell_vol, 4),
            "buy_pct": round(buy_vol / total * 100, 1) if total > 0 else 0.0,
            "ob_imbalance_5": ob_imb,
            "liq_count": len(self.liquidations),
        }

    def snapshot(self) -> dict:
        now = time.time()
        best_bid = 0.0
        best_ask = 0.0
        try:
            if self.orderbook["bids"]:
                best_bid, _ = self._level_px_sz(self.orderbook["bids"][0])
            if self.orderbook["asks"]:
                best_ask, _ = self._level_px_sz(self.orderbook["asks"][0])
        except Exception:
            pass
        return {
            "coin": self.coin,
            "ts": now,
            "ts_human": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "px": self.last_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "cvd": round(self.cvd, 2),
            "oi": self.oi,
            "orderbook": {
                "bids": self.orderbook["bids"][:10],
                "asks": self.orderbook["asks"][:10],
                "spread": self._spread(),
            },
            "trades_recent": list(self.trades)[-20:],
            "liquidations_recent": list(self.liquidations)[-10:],
            "metrics": self._metrics(),
        }


# =========================================================
# MESSAGE HANDLERS
# =========================================================

def handle_l2_book(coin: str, data: dict):
    s = state.markets[coin]
    levels = data.get("levels", [])
    bids = []
    asks = []
    if isinstance(levels, list):
        if len(levels) > 0 and isinstance(levels[0], list):
            bids = levels[0]
        if len(levels) > 1 and isinstance(levels[1], list):
            asks = levels[1]
    s.orderbook = {"bids": bids, "asks": asks, "ts": data.get("time", int(time.time() * 1000))}
    try:
        if bids and asks:
            bb, _ = s._level_px_sz(bids[0])
            ba, _ = s._level_px_sz(asks[0])
            if bb > 0 and ba > 0:
                s.last_price = round((bb + ba) / 2, 4)
    except Exception:
        pass
    s.updated_at = time.time()

    # Feed footprint heatmap + imbalance
    ts = data.get("time", int(time.time() * 1000)) / 1000.0
    try:
        _get_footprint_manager().process_orderbook(coin, bids, asks, ts)
    except Exception:
        pass


def handle_trades(coin: str, data: list):
    s = state.markets[coin]
    for t in data:
        try:
            sz = float(t.get("sz", 0))
            side = t.get("side", "")
            px = float(t.get("px", 0))
            ts_ms = t.get("time", int(time.time() * 1000))
        except (TypeError, ValueError):
            continue
        s.cvd += sz if side == "B" else -sz
        s.trades.append({"ts": ts_ms, "px": px, "sz": sz, "side": side})
        if px > 0:
            s.last_price = px

        # 1. Feed footprint engine
        # R9 : le global footprint_manager n'est initialisé que par
        # _get_footprint_manager() (appelé uniquement depuis handle_l2_book) —
        # or trades est souscrit AVANT l2Book et à chaque reconnexion : tout
        # trade arrivant avant le premier l2Book levait AttributeError (None)
        # avalé par l'except — la footprint perdait ces trades en silence.
        # Le sibling _get_smart_engine() ci-dessous fait déjà le lazy-init.
        try:
            _get_footprint_manager().process_trade(coin, px, sz, side, ts_ms / 1000.0)
        except Exception:
            pass
        
        # 2. Feed Smart Engine (Real-time anomaly detection)
        try:
            _get_smart_engine().on_trade(coin, px, sz, side, ts_ms / 1000.0)
        except Exception:
            pass

    s.updated_at = time.time()


def handle_active_asset_ctx(coin: str, data: dict):
    s = state.markets[coin]
    try:
        ctx = data.get("ctx", {})
        s.oi = {"value": float(ctx.get("openInterest", 0)), "ts": int(time.time() * 1000)}
    except (TypeError, ValueError):
        pass
    s.updated_at = time.time()


async def subscribe_coin(ws, coin: str):
    subs = [
        {"method": "subscribe", "subscription": {"type": "trades", "coin": coin}},
        {"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}},
        {"method": "subscribe", "subscription": {"type": "activeAssetCtx", "coin": coin}},
    ]
    for sub in subs:
        await ws.send(json.dumps(sub))
        await asyncio.sleep(0.6)


async def process_message(msg: dict):
    ch = msg.get("channel", "")
    data = msg.get("data", {})
    state.last_message_ts = time.time()
    state.message_count += 1

    if ch == "l2Book":
        coin = data.get("coin", "")
        if coin in state.markets:
            handle_l2_book(coin, data)
    elif ch == "trades":
        if isinstance(data, list) and data:
            coin = data[0].get("coin", "")
            if coin in state.markets:
                handle_trades(coin, data)
    elif ch == "activeAssetCtx":
        coin = data.get("coin", "")
        if coin in state.markets:
            handle_active_asset_ctx(coin, data)
    elif ch == "subscriptionResponse":
        sub = data.get("subscription", {})
        logger.info(f"Confirmed: {sub.get('type')} / {sub.get('coin')}")
    elif ch == "error":
        state.errors.append(str(data))
        logger.error(f"Server error: {data}")


# =========================================================
# COLLECTOR LOOP
# =========================================================

async def run_collector(coins: list[str]):
    state.coins = coins
    state.started_at = time.time()

    for coin in coins:
        state.markets[coin] = MarketState(coin)

    delay = 1.0
    logger.info(f"Collector starting for: {', '.join(coins)}")

    while True:
        try:
            async with websockets.connect(
                HL_WS_URL,
                ping_interval=30,
                ping_timeout=15,
                max_size=10 * 1024 * 1024,
            ) as ws:
                state.connected = True
                logger.info("Connected to Hyperliquid WebSocket")
                delay = 1.0
                await asyncio.sleep(0.3)
                for coin in coins:
                    await subscribe_coin(ws, coin)
                    await asyncio.sleep(0.5)

                async for raw in ws:
                    try:
                        payload = json.loads(raw)
                        await process_message(payload)
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.error(f"Message error: {e}")

        except ConnectionClosedOK:
            logger.warning("Connection closed OK — retrying")
        except ConnectionClosedError:
            logger.error("Connection closed with error — retrying")
        except Exception as e:
            state.errors.append(f"{type(e).__name__}: {e}")
            logger.error(f"Collector error: {e}")
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 30)
            continue

        state.connected = False
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 30)


# =========================================================
# SNAPSHOT LOOP
# =========================================================

async def snapshot_loop(coins: list[str], interval: float = 5.0):
    while True:
        await asyncio.sleep(interval)
        for coin in coins:
            if coin not in state.markets or state.markets[coin].updated_at == 0:
                continue
            path = SNAPSHOT_DIR / f"{coin.lower()}_latest.json"
            try:
                # R9 : write_text tronque puis écrit (non atomique) — un
                # read_text concurrent tombant dans la fenêtre de troncature
                # levait JSONDecodeError => HTTP 500 intermittent sur
                # /api/market/snapshot/{coin}. tmp + os.replace : atomique.
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(
                    json.dumps(state.markets[coin].snapshot(), indent=2),
                    encoding="utf-8",
                )
                os.replace(tmp, path)
            except Exception as e:
                logger.error(f"Snapshot error: {e}")


# =========================================================
# FACTORY — appelé depuis main.py lifespan
# =========================================================

def create_collector_tasks(coins: list[str] | None = None) -> list[asyncio.Task]:
    """Retourne les tasks à lancer dans le lifespan de FastAPI."""
    if coins is None:
        coins = ["BTC"]
    return [
        asyncio.create_task(run_collector(coins)),
        asyncio.create_task(snapshot_loop(coins)),
    ]


def get_collector_state() -> dict:
    """Retourne l'état courant du collector pour l'endpoint /api/services/status."""
    return state.status


def get_market_snapshot(coin: str) -> dict | None:
    """Retourne le snapshot d'une coin spécifique."""
    if coin.upper() in state.markets:
        return state.markets[coin.upper()].snapshot()
    return None
