"""
Core Equity - Backend FastAPI
=============================
Services integres :
  - Collector Hyperliquid (WS -> snapshots + footprint/heatmap)
  - Aggr.trade (WS multi-exchanges : Binance, Bybit, OKX...)
  - External APIs (CoinGlass, Coinalyze, CounterFlow)
  - MT5 Bridge via HTTP (port 8765, Windows)
  - Desktop via windows-mcp (port 9000, Windows)
  - Arkham Intelligence (Firecrawl scraper + real-time tracker)

Port : 8000
WS  : ws://localhost:8000/ws
"""

import asyncio
import hmac
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

# ── Load .env file ──────────────────────────────────────────
def _parse_env_file(env_path: Path) -> int:
    """Parse .env file manually and set env vars. Returns count of keys set."""
    if not env_path.exists():
        return 0
    keys_set = 0
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val and not val.startswith("YOUR_") and val != "fc-YOUR_KEY_HERE":
                current = os.environ.get(key, "")
                if current != val:
                    os.environ[key] = val
                    keys_set += 1
    return keys_set


# ── Optional dotenv fallback ────────────────────────────────
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    _env_loaded = load_dotenv(dotenv_path=str(_env_path), override=True)
    print(f"[ENV] .env file: {_env_path} ({'exists' if _env_path.exists() else 'NOT FOUND'})")
    if _env_loaded:
        print("[ENV] .env loaded (dotenv)")
    else:
        print("[ENV] .env already loaded or empty (dotenv - no changes)")
except ImportError:
    _env_loaded = False

_manual_keys = _parse_env_file(Path(__file__).parent / ".env")
if _manual_keys > 0:
    print(f"[ENV] Manual override: {_manual_keys} additional keys set from .env")

# ── Entity DB ───────────────────────────────────────────────
_ENTITY_DB: list[dict[str, Any]] = []

def _build_entity_db():
    """Build the static entity database for search."""
    global _ENTITY_DB
    if _ENTITY_DB:
        return
    _ENTITY_DB = [
        {"id": "entity_bitcoin", "name": "Bitcoin", "label": "Bitcoin / BTC", "type": "token", "score": 100},
        {"id": "entity_ethereum", "name": "Ethereum", "label": "Ethereum / ETH", "type": "token", "score": 95},
        {"id": "entity_solana", "name": "Solana", "label": "Solana / SOL", "type": "token", "score": 85},
        {"id": "entity_blackrock", "name": "BlackRock", "label": "BlackRock", "type": "entity", "score": 100},
        {"id": "entity_binance", "name": "Binance", "label": "Binance", "type": "exchange", "score": 100},
    ]

# ── Service imports ────────────────────────────────────────
from services.collector import get_collector_state, get_market_snapshot, footprint_manager
from services.multi_exchange import aggregation_loop, get_aggr_state, state as aggr_state
from services.websocket_manager import manager as ws_manager
from services.arkham_scraper import get_arkham_scraper

MT5_URL = "http://host.docker.internal:8765"

# ── XAU price cache ─────────────────────────────────────────
_XAU_CACHE = {"data": {"price": 4679.0, "bid": 4679.0, "ask": 4679.0, "change_24h": 0.0, "source": "fallback"}, "ts": 0}
_XAU_CACHE_TTL = 30

_BINANCE_CACHE = {"data": {}, "ts": 0}
_BINANCE_CACHE_TTL = 15
_BACKGROUND_TASKS: list[asyncio.Task] = []

# Lazy import for smart_engine to avoid circular deps
def _get_smart_engine():
    from services.collector import smart_engine
    return smart_engine

try:
    import services.desktop as desktop
except Exception:
    desktop = None

# ── Router imports ─────────────────────────────────────────
from routers import market as market_router
from routers import intel as intel_router
from routers import news as news_router
from routers import chat as chat_router
from routers import vision as vision_router
from routers import agents as agents_router
from routers import desktop as desktop_router
from routers import alpha_lab as alpha_lab_router
from routers import entity as entity_router
from routers import onchain as onchain_router
try:
    from routers import arkham as arkham_router
    _HAS_ARKHAM_ROUTER = True
except Exception:
    _HAS_ARKHAM_ROUTER = False

# ── FastAPI App ────────────────────────────────────────────
app = FastAPI(
    title="Core Equity",
    version="1.0.0",
)

def _csv_env(name: str, default: str) -> list[str]:
    values = [item.strip() for item in os.getenv(name, default).split(",")]
    return [item for item in values if item]


_ALLOWED_ORIGINS = _csv_env(
    "CORE_ALLOWED_ORIGINS",
    os.getenv(
        "HERMES_ALLOWED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173",
    ),
)
for _dev_origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
    if _dev_origin not in _ALLOWED_ORIGINS:
        _ALLOWED_ORIGINS.append(_dev_origin)

_ALLOWED_HOSTS = _csv_env(
    "CORE_ALLOWED_HOSTS",
    os.getenv("HERMES_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0"),
)
_ACCESS_TOKEN = (
    os.getenv("CORE_ACCESS_TOKEN", "").strip()
    or os.getenv("HERMES_ACCESS_TOKEN", "").strip()
)
_ADMIN_TOKEN = os.getenv("CORE_ADMIN_TOKEN", "").strip()
_LOCAL_AUTH_REQUIRED = (
    os.getenv("CORE_REQUIRE_LOCAL_AUTH", os.getenv("HERMES_REQUIRE_LOCAL_AUTH", "")).lower()
    in {"1", "true", "yes"}
)
_ALLOW_WSL_LOCAL_PROXY_BYPASS = (
    os.getenv("CORE_ALLOW_WSL_LOCAL_PROXY_BYPASS", "1").lower()
    not in {"0", "false", "no"}
)
try:
    _MAX_REQUEST_BODY_BYTES = max(64_000, int(os.getenv("CORE_MAX_REQUEST_BODY_BYTES", "1048576") or "1048576"))
except ValueError:
    _MAX_REQUEST_BODY_BYTES = 1_048_576
_PUBLIC_PATHS = {"/health", "/api/security/status", "/api/security/login", "/api/security/logout"}
_PROTECTED_NON_API_PATHS = {"/docs", "/redoc", "/openapi.json"}
_ADMIN_ONLY_PREFIXES = (
    "/api/desktop",
    "/api/vision",
    "/api/agents",
    "/api/chat",
    "/api/intel",
    "/api/arkham/scrapling",
    "/api/arkham/db",
    "/api/market/mt5",
    "/api/market/ninjatrader",
)
_ADMIN_ONLY_ROUTES = (
    ("GET", "/api/news/gold"),
    ("GET", "/api/news/gold/bias"),
    ("GET", "/api/news/search"),
)
_ADMIN_ONLY_MUTATIONS = (
    ("POST", "/api/arkham/scrape/full"),
    ("POST", "/api/arkham/scrape/delta"),
    ("POST", "/api/arkham/db/reload"),
    ("POST", "/api/opportunities/scan"),
    ("POST", "/api/news/gold/refresh"),
)
_ACCESS_COOKIE = "core_access"
_LEGACY_ACCESS_COOKIE = "hermes_access"
_SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self' http://127.0.0.1:* http://localhost:* ws://127.0.0.1:* ws://localhost:*; "
        "frame-src 'none'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    ),
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=()",
}

"""
Deprecated env names kept as fallback for existing local setups:
HERMES_ACCESS_TOKEN, HERMES_REQUIRE_LOCAL_AUTH, HERMES_ALLOWED_HOSTS,
HERMES_ALLOWED_ORIGINS.
"""

app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost"}
_WSL_NAT_NETWORK = ip_network("172.16.0.0/12")
_FORWARDED_CLIENT_HEADERS = (
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "cf-connecting-ip",
)


def _strip_port(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("[") and "]" in host:
        return host[1:].split("]", 1)[0]
    if host.count(":") <= 1:
        return host.rsplit(":", 1)[0]
    return host


def _has_forwarded_client_headers(headers: Any) -> bool:
    return any(headers.get(header) for header in _FORWARDED_CLIENT_HEADERS)


def _is_wsl_local_proxy_host(client_host: str) -> bool:
    try:
        return ip_address(client_host) in _WSL_NAT_NETWORK
    except ValueError:
        return False


def _is_local_connection(client_host: str, headers: Any) -> bool:
    """Bypass auth for local admin access only, including the Windows->WSL dev proxy."""
    host_header = _strip_port(headers.get("host", ""))
    if host_header not in _LOCAL_CLIENT_HOSTS:
        return False
    if _has_forwarded_client_headers(headers):
        return False
    if client_host in _LOCAL_CLIENT_HOSTS:
        return True
    return _ALLOW_WSL_LOCAL_PROXY_BYPASS and _is_wsl_local_proxy_host(client_host)


def _is_local_client(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return _is_local_connection(host, request.headers)


def _request_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (
        request.headers.get("x-core-token", "").strip()
        or request.headers.get("x-hermes-token", "").strip()
        or request.cookies.get(_ACCESS_COOKIE, "").strip()
        or request.cookies.get(_LEGACY_ACCESS_COOKIE, "").strip()
    )


def _is_authenticated_request(request: Request) -> bool:
    if not _ACCESS_TOKEN:
        return True
    if _is_local_client(request) and not _LOCAL_AUTH_REQUIRED:
        return True
    return hmac.compare_digest(_request_token(request), _ACCESS_TOKEN)


def _is_admin_request(request: Request) -> bool:
    if not _ADMIN_TOKEN:
        return False
    token = request.headers.get("x-core-admin-token", "").strip()
    return hmac.compare_digest(token, _ADMIN_TOKEN)


def _requires_admin_access(method: str, path: str) -> bool:
    method = method.upper()
    if any(path == prefix or path.startswith(prefix + "/") for prefix in _ADMIN_ONLY_PREFIXES):
        return True
    return (method, path) in _ADMIN_ONLY_ROUTES or (method, path) in _ADMIN_ONLY_MUTATIONS


def _cookie_secure(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


def _set_access_cookie(response: JSONResponse, request: Request) -> None:
    response.set_cookie(
        _ACCESS_COOKIE,
        _ACCESS_TOKEN,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        max_age=60 * 60 * 12,
    )


def _with_security_headers(response):
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


@app.middleware("http")
async def private_access_gate(request: Request, call_next):
    """Optional shared-token gate for exposing the local site through a private tunnel."""
    path = request.url.path
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > _MAX_REQUEST_BODY_BYTES:
                    return _with_security_headers(
                        JSONResponse({"detail": "Request body too large"}, status_code=413)
                    )
            except ValueError:
                return _with_security_headers(
                    JSONResponse({"detail": "Invalid content-length"}, status_code=400)
                )
    if request.method == "OPTIONS":
        origin = request.headers.get("origin", "")
        response = PlainTextResponse("", status_code=204)
        if origin in _ALLOWED_ORIGINS:
            response.headers["access-control-allow-origin"] = origin
            response.headers["access-control-allow-credentials"] = "true"
            response.headers["access-control-allow-methods"] = "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT"
            response.headers["access-control-allow-headers"] = request.headers.get(
                "access-control-request-headers",
                "authorization,content-type,x-core-token,x-hermes-token",
            )
            response.headers["vary"] = "Origin"
        return _with_security_headers(response)

    async def pass_through():
        return _with_security_headers(await call_next(request))

    if not _ACCESS_TOKEN or path in _PUBLIC_PATHS:
        return await pass_through()
    if path in _PROTECTED_NON_API_PATHS or path.startswith(("/docs/", "/redoc/")):
        if _is_authenticated_request(request):
            return await pass_through()
        return _with_security_headers(JSONResponse({"detail": "Core Equity access token required"}, status_code=401))
    # Keep the React shell reachable so clients get a clean login screen.
    # Data, trading controls and RPC-backed APIs stay protected below.
    if not path.startswith("/api/"):
        return await pass_through()
    if _is_authenticated_request(request):
        if _requires_admin_access(request.method, path) and not _is_admin_request(request):
            detail = "CORE_ADMIN_TOKEN is not configured" if not _ADMIN_TOKEN else "Core Equity admin token required"
            return _with_security_headers(JSONResponse({"detail": detail}, status_code=403))
        return await pass_through()

    return _with_security_headers(JSONResponse({"detail": "Core Equity access token required"}, status_code=401))

# Start background collector on startup
@app.on_event("startup")
async def startup_event():
    print("[BOOT] Starting background collector...")
    from services.collector import run_collector, snapshot_loop
    _BACKGROUND_TASKS.append(asyncio.create_task(run_collector(["BTC", "ETH"])))
    _BACKGROUND_TASKS.append(asyncio.create_task(snapshot_loop(["BTC", "ETH"])))
    print("[BOOT] Collector tasks started")

    if not any(task.get_name() == "multi_exchange_aggregation" for task in _BACKGROUND_TASKS):
        _BACKGROUND_TASKS.append(
            asyncio.create_task(
                aggregation_loop(interval=60.0),
                name="multi_exchange_aggregation",
            )
        )
        print("[BOOT] Multi-exchange aggregation started")
    
    # Broadcast loop - send market data to all WS clients every 2s
    async def _broadcast_loop():
        from services.collector import state as collector_state
        while True:
            await asyncio.sleep(2)
            if not collector_state.markets:
                continue
            xau_data = _fetch_xau_price()
            payload = {
                "type": "market_update",
                "ts": time.time(),
                "hyperliquid": {
                    coin: {
                        "px": m.last_price,
                        "bid": m.orderbook["bids"][0].get("px", m.last_price) if m.orderbook.get("bids") and len(m.orderbook["bids"]) > 0 else m.last_price,
                        "ask": m.orderbook["asks"][0].get("px", m.last_price) if m.orderbook.get("asks") and len(m.orderbook["asks"]) > 0 else m.last_price,
                        "change_24h": 0.0,
                    }
                    for coin, m in collector_state.markets.items()
                    if m.last_price > 0
                },
                "xauusd": xau_data,
            }
            try:
                await ws_manager.broadcast(payload)
            except Exception:
                pass
    
    _BACKGROUND_TASKS.append(asyncio.create_task(_broadcast_loop(), name="market_broadcast_loop"))

    if os.getenv("CORE_AUTO_ENRICH_ENABLED", "true").lower() in {"1", "true", "yes"}:
        from services.onchain_engine import start_auto_enrich_priority
        status = await asyncio.to_thread(start_auto_enrich_priority)
        print(f"[BOOT] Auto enrich priority started: {status.get('config')}")

# ── Mount routers ──────────────────────────────────────────
app.include_router(market_router.router, prefix="/api/market", tags=["market"])
app.include_router(intel_router.router, prefix="/api/intel", tags=["intel"])
app.include_router(news_router.router, prefix="/api/news", tags=["news"])
app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
app.include_router(vision_router.router, prefix="/api/vision", tags=["vision"])
app.include_router(agents_router.router, prefix="/api/agents", tags=["agents"])
app.include_router(desktop_router.router, prefix="/api/desktop", tags=["desktop"])
app.include_router(onchain_router.router, prefix='/api/onchain', tags=['onchain'])
app.include_router(entity_router.router, prefix='/api/entity', tags=['entity'])
app.include_router(alpha_lab_router.router, prefix='/api/alpha', tags=["alpha"])

if _HAS_ARKHAM_ROUTER:
    app.include_router(arkham_router.router, prefix="/api/arkham", tags=["arkham"])

if _HAS_ARKHAM_ROUTER:
    app.include_router(arkham_router.router, prefix="/api/arkham", tags=["arkham"])

# =========================================================
# ORDER FLOW — Footprint, Heatmap, Imbalance
# =========================================================

@app.get("/api/market/footprint/{coin}", tags=["orderflow"])
async def get_footprint(coin: str, count: int = 50):
    """Footprint bars — volume par price level, delta, POC, stacked imbalances."""
    return footprint_manager.get_footprint(coin.upper(), count)

@app.get("/api/market/heatmap/{coin}", tags=["orderflow"])
async def get_heatmap(coin: str, resolution: float = 5.0):
    """Orderbook Heatmap — historique de liquidite price x time."""
    return footprint_manager.get_heatmap(coin.upper(), resolution)

@app.get("/api/market/imbalance/{coin}", tags=["orderflow"])
async def get_imbalance(coin: str, window: int = 50):
    """Liquidity Imbalance — ratio bid/ask depth en temps reel."""
    return footprint_manager.get_imbalance(coin.upper(), window)

# =========================================================
# MULTI-EXCHANGE DATA
# =========================================================

@app.get("/api/market/multi-exchange", tags=["multi-exchange"])
async def get_multi_exchange_status():
    """Statut et donnees de l'agregateur multi-exchanges."""
    return get_aggr_state()

@app.get("/api/market/funding/{symbol}", tags=["multi-exchange"])
async def get_funding(symbol: str):
    """Funding rate specifique d'un symbole."""
    sym_data = aggr_state.funding_data.get(symbol.upper(), {})
    if not sym_data:
        return {"error": "No data", "available_symbols": list(aggr_state.funding_data.keys())[:10]}
    return {"symbol": symbol, "data": sym_data}


def _fetch_xau_price() -> dict:
    """Fetch XAU/USD price from Yahoo Finance COMEX Gold Futures."""
    global _XAU_CACHE
    now = time.time()
    if now - _XAU_CACHE["ts"] < _XAU_CACHE_TTL:
        return _XAU_CACHE["data"]
    import urllib.request, json
    result = {"price": 4679.0, "bid": 4679.0, "ask": 4679.0, "change_24h": 0.0, "source": "fallback"}
    try:
        req = urllib.request.Request("https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=5d", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        result_data = data["chart"]["result"][0]
        meta = result_data["meta"]
        price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
        prev_close = meta.get("chartPreviousClose")
        change_24h = 0.0
        if price and prev_close and prev_close > 0:
            change_24h = round((price - prev_close) / prev_close * 100, 2)
        if price:
            result = {"price": price, "bid": price, "ask": price, "change_24h": change_24h, "source": "yahoo_finance_gold_futures"}
    except Exception:
        pass
    _XAU_CACHE = {"data": result, "ts": now}
    return result

    _XAU_CACHE = {"data": result, "ts": now}
    return result


def _fetch_binance_prices() -> dict[str, dict[str, float]]:
    """Fetch BTC, ETH live prices from Binance public API."""
    global _BINANCE_CACHE
    now = time.time()
    if now - _BINANCE_CACHE["ts"] < _BINANCE_CACHE_TTL:
        return _BINANCE_CACHE["data"]
    
    import urllib.request, json
    result: dict[str, dict[str, float]] = {}
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]:
        try:
            req = urllib.request.Request(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}")
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            coin = symbol.replace("USDT", "").lower()
            result[coin] = {
                "price": float(data["lastPrice"]),
                "change_24h": float(data["priceChangePercent"]),
                "high_24h": float(data.get("highPrice", 0)),
                "low_24h": float(data.get("lowPrice", 0)),
                "volume_24h": float(data.get("volume", 0)),
            }
        except Exception:
            continue
    _BINANCE_CACHE = {"data": result, "ts": now}
    return result

@app.get("/api/market/prices", tags=["market"])
async def get_prices():
    """Get current prices for BTC, ETH, XAU from live sources."""
    binance = _fetch_binance_prices()
    xau_data = _fetch_xau_price()
    
    btc = binance.get("btc", {"price": 78407.5, "change_24h": 0.0})
    eth = binance.get("eth", {"price": 2359.75, "change_24h": 0.0})
    
    return {
        "btc": {"price": btc["price"], "change_24h": btc["change_24h"]},
        "eth": {"price": eth["price"], "change_24h": eth["change_24h"]},
        "xau": xau_data,
        "source": "binance+scrape" if binance else "fallback",
    }

# =========================================================
# ENTITY SEARCH — Token/Address/Entity lookup
# =========================================================

@app.get("/api/search", tags=["search"])
async def search_entities(q: str, limit: int = 10):
    """
    Search tokens, addresses, entities.
    
    Detects automatically:
    - 0x... addresses → on-chain lookup
    - Token symbols → CoinGecko + local data
    - Entity names → Arkham DB + static data
    
    Returns matching entities sorted by relevance.
    """
    if not q or len(q) < 1:
        return {"results": []}

    q_stripped = q.strip()
    q_lower = q_stripped.lower()
    _build_entity_db()

    results = []

    # ── 1) Address detection (0x...) ──
    if q_stripped.startswith("0x") and len(q_stripped) >= 40:
        try:
            scraper = get_arkham_scraper()
            if scraper:
                addr_data = scraper.lookup_address(q_stripped, "ethereum")
                if addr_data:
                    results.append({
                        "id": f"addr_{q_stripped[:10]}",
                        "type": "address",
                        "name": addr_data.get("label", q_stripped[:10] + "..."),
                        "label": addr_data.get("label", f"Address {q_stripped[:10]}..."),
                        "address": q_stripped,
                        "balance": addr_data.get("balance_eth", "?"),
                        "source": "etherscan",
                        "score": 100,
                    })
        except Exception:
            pass

    # ── 2) Local entity DB search ──
    for entity in _ENTITY_DB:
        score = 0
        name = entity.get("name", "").lower()
        label = entity.get("label", "").lower()
        eid = entity.get("id", "").lower()

        if name == q_lower:
            score = 100
        elif name.startswith(q_lower):
            score = 80
        elif q_lower in label:
            score = 60
        elif q_lower in name:
            score = 50
        elif q_lower in eid:
            score = 30

        if score > 0:
            results.append({**entity, "score": score})

    # ── 3) CoinGecko token search (free, no API key) ──
    if not (q_stripped.startswith("0x") and len(q_stripped) >= 40):
        try:
            scraper = get_arkham_scraper()
            if scraper:
                cg_results = await scraper.search_coingecko(q_stripped)
                for coin in (cg_results or [])[:5]:
                    results.append({
                        "id": f"cg_{coin.get('id', '')}",
                        "type": "token",
                        "name": coin.get("symbol", "").upper(),
                        "label": coin.get("name", ""),
                        "price": coin.get("market_cap_rank", ""),
                        "source": "coingecko",
                        "score": 70,
                    })
        except Exception:
            pass

    # ── Deduplicate: 1 result per base name ──
    # Priority: token > entity > arkham_entity > address > funding > gainer
    TYPE_PRIORITY = {"arkham_entity": 0, "entity": 1, "arkham_label": 2, "address": 3, "token": 4, "funding": 5, "gainer": 6}
    seen_names = {}
    deduped = []
    for r in results:
        # Normalize name for dedup: "BTC", "btc", "bitcoin" → "btc"
        base = r.get("name", "").lower().replace("usdt", "").replace("usd", "").replace("/usd", "").strip()
        if not base:
            base = r.get("id", "").lower()
        # For funding entities like "BTCUSDT" → base = "btc"
        if base in ("btc", "eth", "sol", "xau"):
            # Group all variants of the same token together
            pass
        if base in seen_names:
            existing = seen_names[base]
            existing_priority = TYPE_PRIORITY.get(existing.get("type", ""), 99)
            new_priority = TYPE_PRIORITY.get(r.get("type", ""), 99)
            existing_score = existing.get("score", 0)
            new_score = r.get("score", 0)
            # Keep the one with higher priority type, or higher score if same type
            if new_priority < existing_priority or (new_priority == existing_priority and new_score > existing_score):
                deduped.remove(existing)
                deduped.append(r)
                seen_names[base] = r
        else:
            deduped.append(r)
            seen_names[base] = r

    deduped.sort(key=lambda x: x["score"], reverse=True)
    return {"results": deduped[:limit], "total": len(deduped)}


# NOTE: /api/arkham/search is now handled by the arkham router
# (download/backend/routers/arkham.py) — removed duplicate from main.py



# NOTE: /api/entity/* handled by routers/entity.py
# Legacy route removed — use /api/arkham/lookup/{address}



# =========================================================
# SMART SIGNALS
# =========================================================

@app.get("/api/market/signals", tags=["smart"])
async def get_smart_signals(strength: str = None):
    """Signaux detectes par le Smart Engine."""
    return {"signals": smart_engine.get_signals(strength=strength)}

@app.get("/api/market/smart-stats/{coin}", tags=["smart"])
async def get_smart_stats(coin: str):
    """Stats intelligentes pour un coin."""
    engine = _get_smart_engine()
    if engine is None:
        return {"coin": coin, "status": "not_available", "note": "Smart engine not initialized"}
    return engine.get_stats(coin.upper())


def _funding_opportunities(limit: int = 20, type: str | None = None, direction: str | None = None, min_confidence: float = 0) -> list[dict[str, Any]]:
    """Build lightweight dashboard opportunities from live multi-exchange funding state."""
    opportunities: list[dict[str, Any]] = []
    now = int(time.time())
    for symbol, exchanges in (aggr_state.funding_data or {}).items():
        if not isinstance(exchanges, dict):
            continue
        binance_rate = None
        bybit_rate = None
        if isinstance(exchanges.get("binance"), dict):
            binance_rate = exchanges["binance"].get("rate")
        if isinstance(exchanges.get("bybit"), dict):
            bybit_rate = exchanges["bybit"].get("funding_rate")

        rates = [float(rate) for rate in (binance_rate, bybit_rate) if rate is not None]
        if not rates:
            continue
        avg_rate = sum(rates) / len(rates)
        abs_rate = abs(avg_rate)
        opp_direction = "short" if avg_rate > 0 else "long"
        confidence = min(1.0, abs_rate / 0.001)
        if confidence < min_confidence:
            continue
        if direction and direction.lower() != opp_direction:
            continue
        opportunity_type = "funding_squeeze_short" if avg_rate > 0 else "funding_squeeze_long"
        if type and type.lower() not in {opportunity_type, "funding", "funding_squeeze"}:
            continue
        severity = "critical" if abs_rate >= 0.0015 else "high" if abs_rate >= 0.0008 else "medium" if abs_rate >= 0.00035 else "low"
        opportunities.append(
            {
                "type": opportunity_type,
                "symbol": symbol,
                "severity": severity,
                "timestamp": now,
                "confidence": round(confidence, 4),
                "direction": opp_direction,
                "details": {
                    "avg_funding": avg_rate,
                    "binance_funding": binance_rate,
                    "bybit_funding": bybit_rate,
                    "source": "multi_exchange_funding_state",
                },
            }
        )

    opportunities.sort(
        key=lambda row: (
            {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(row.get("severity")), 0),
            abs(float(row.get("details", {}).get("avg_funding") or 0)),
        ),
        reverse=True,
    )
    return opportunities[: max(1, min(int(limit or 20), 100))]


# =========================================================
# OPPORTUNITIES — Asymmetric trading setups
# =========================================================

@app.get("/api/opportunities", tags=["opportunities"])
async def get_opportunities(limit: int = 20, type: str = None, direction: str = None, min_confidence: float = 0):
    """Opportunites detectees — funding squeeze, OI divergence, arbitrage, flow, unlocks."""
    rows = _funding_opportunities(limit, type, direction, min_confidence)
    return {"opportunities": rows, "count": len(rows), "source": "multi_exchange_funding_state"}


@app.get("/api/market/opportunities", tags=["opportunities"])
async def get_market_opportunities(limit: int = 20, type: str = None, direction: str = None, min_confidence: float = 0):
    """Compatibility alias for dashboard market widgets."""
    return await get_opportunities(limit, type, direction, min_confidence)


@app.get("/api/opportunities/stats", tags=["opportunities"])
async def get_opportunity_stats():
    """Stats du moteur d'opportunites."""
    rows = _funding_opportunities(limit=100)
    return {
        "ok": True,
        "opportunities": len(rows),
        "funding_symbols": len(aggr_state.funding_data or {}),
        "critical": sum(1 for row in rows if row.get("severity") == "critical"),
        "high": sum(1 for row in rows if row.get("severity") == "high"),
        "source": "multi_exchange_funding_state",
    }

@app.post("/api/opportunities/scan", tags=["opportunities"])
async def trigger_manual_scan():
    """Declenche un scan manuel (Arkham + Firecrawl + funding)."""
    return {
        "status": "live_state_only",
        "ts": time.time(),
        "note": "Legacy OpportunityEngine is not configured; opportunities are derived from live multi-exchange funding state.",
    }

# =========================================================
# SERVICES — Monitoring global
# =========================================================

@app.get("/api/services/status", tags=["services"])
async def services_status():
    """Statut de tous les services."""
    import aiohttp

    result = {
        "hyperliquid_collector": get_collector_state(),
        "multi_exchange_aggregator": get_aggr_state(),
        "mt5_bridge": None,
        "desktop_mcp": None,
    }

    # Verifie MT5 Bridge
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=2)
        ) as session:
            async with session.get(f"{MT5_URL}/health") as r:
                result["mt5_bridge"] = await r.json()
    except Exception as e:
        result["mt5_bridge"] = {"status": "unreachable", "error": str(e)}

    # Verifie MCP Desktop — safe call
    try:
        if hasattr(desktop, 'get_status'):
            result["desktop_mcp"] = desktop.get_status()
        else:
            result["desktop_mcp"] = {"status": "method_not_available"}
    except Exception:
        result["desktop_mcp"] = {"status": "unknown"}

    return result


@app.get("/api/services/collector/{coin}", tags=["services"])
async def collector_coin(coin: str):
    """Snapshot live d'une coin depuis le collector integre."""
    snap = get_market_snapshot(coin.upper())
    if snap is None:
        return {"status": "no_data", "coin": coin}
    return snap

# =========================================================
# WEBSOCKET ENDPOINT
# =========================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if _ACCESS_TOKEN:
        token = ""
        auth = ws.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        token = (
            token
            or ws.cookies.get(_ACCESS_COOKIE, "").strip()
            or ws.cookies.get(_LEGACY_ACCESS_COOKIE, "").strip()
        )
        host = ws.client.host if ws.client else ""
        local_bypass = _is_local_connection(host, ws.headers) and not _LOCAL_AUTH_REQUIRED
        if not hmac.compare_digest(token, _ACCESS_TOKEN) and not local_bypass:
            await ws.close(code=1008)
            return

    await ws_manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await ws.send_json({"type": "pong", "ts": time.time()})

                elif msg_type == "chat_message":
                    await ws.send_json({
                        "type": "chat_ack",
                        "content": f"Message recu: {msg.get('content', '')}",
                    })

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)

# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():
    return {
        "status":  "ok",
        "service": "Core Equity",
        "ws_clients": ws_manager.get_active_count(),
    }


@app.get("/api/security/status", tags=["security"])
def security_status(request: Request):
    return {
        "access_gate": "enabled" if _ACCESS_TOKEN else "local-open",
        "authenticated": _is_authenticated_request(request),
        "local_auth_required": _LOCAL_AUTH_REQUIRED,
        "allowed_origins_configured": bool(_ALLOWED_ORIGINS),
        "allowed_hosts_configured": bool(_ALLOWED_HOSTS),
        "note": "Set CORE_ACCESS_TOKEN before exposing the site through a private tunnel.",
    }


@app.post("/api/security/login", tags=["security"])
async def security_login(payload: dict[str, Any], request: Request):
    if not _ACCESS_TOKEN:
        return {"ok": True, "access_gate": "local-open"}
    token = str(payload.get("token") or "").strip()
    if not hmac.compare_digest(token, _ACCESS_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid Core Equity access token")
    response = JSONResponse({"ok": True, "access_gate": "enabled"})
    _set_access_cookie(response, request)
    return response


@app.post("/api/security/logout", tags=["security"])
async def security_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(_ACCESS_COOKIE)
    response.delete_cookie(_LEGACY_ACCESS_COOKIE)
    return response


@app.get("/api/env/status", tags=["debug"])
def env_status():
    """
    Check which important variables are configured without exposing values.
    This endpoint is still behind the normal Core Equity access gate.
    """
    keys_to_check = [
        "FIRECRAWL_API_KEY", "GEMINI_API_KEY", "NT8_PASSWORD",
        "ETHERSCAN_API_KEY", "BSCSCAN_API_KEY",
        "MT5_BRIDGE_HOST", "MT5_BRIDGE_PORT",
    ]
    result = {}
    for key in keys_to_check:
        val = os.getenv(key, "")
        if val and not val.startswith("YOUR_") and val != "fc-YOUR_KEY_HERE":
            result[key] = "SET"
        else:
            result[key] = "NOT SET"
    result["_env_file_exists"] = (Path(__file__).parent / ".env").exists()
    return result


# =========================================================
# FRONTEND SPA
# =========================================================

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    brand_icons_dir = STATIC_DIR / "brand-icons"

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if brand_icons_dir.exists():
        app.mount("/brand-icons", StaticFiles(directory=brand_icons_dir), name="brand-icons")

    def _safe_static_file(full_path: str) -> Path | None:
        try:
            static_root = STATIC_DIR.resolve()
            requested_file = (STATIC_DIR / full_path).resolve()
        except Exception:
            return None
        if not requested_file.is_relative_to(static_root):
            return None
        if not requested_file.is_file():
            return None
        return requested_file

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """Serve the built React app from uvicorn without stealing API routes."""
        if full_path.startswith(("api/", "ws")) or full_path in {"api", "health", "ws"}:
            raise HTTPException(status_code=404, detail="Not Found")

        requested_file = _safe_static_file(full_path) if full_path else None
        if requested_file:
            return FileResponse(requested_file)

        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

        raise HTTPException(status_code=404, detail="Frontend build not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
