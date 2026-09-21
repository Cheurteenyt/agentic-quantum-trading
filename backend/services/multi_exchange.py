"""
Multi-Exchange Data Aggregator
==============================
Connecte directement aux APIs publiques des exchanges (Binance, Bybit, OKX, Hyperliquid).
Pas de scraping, pas de risque de blocage. Data brute et fiable.

Endpoints couverts :
  - Funding Rates (sentiment marché)
  - Open Interest (levier global)
  - Liquidations (volatilité forcée)
  - Nouveaux Listings (opportunités Binance)
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path

try:
    import aiohttp
except ImportError:
    aiohttp = None

SNAPSHOT_DIR = Path("data/snapshots")
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


class ExchangeAggregatorState:
    """État global de l'agrégateur."""
    def __init__(self):
        self.last_update = 0
        self.funding_data = {}  # {symbol: {binance: ..., bybit: ...}}
        self.oi_data = {}
        self.listings = []
        self.errors = []
        self.binance_api_base = "https://fapi.binance.com"
        self.bybit_api_base = "https://api.bybit.com"
        self.okx_api_base = "https://www.okx.com"


state = ExchangeAggregatorState()


def _safe_float(value, default: float = 0.0) -> float:
    """Parse exchange numeric fields that may arrive as empty strings."""
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


# =========================================================
# BINANCE (Futures)
# =========================================================

async def fetch_binance_funding():
    """GET /fapi/v1/premiumIndex — Funding rates toutes les 8h."""
    if not aiohttp: return {}
    url = f"{state.binance_api_base}/fapi/v1/premiumIndex"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Parse et retourne juste les symbols pertinents
                    result = {}
                    for item in data:
                        sym = item.get("symbol", "")
                        if "USDT" in sym:
                            result[sym] = {
                                "rate": _safe_float(item.get("lastFundingRate")),
                                "next_time": item.get("nextFundingTime", 0),
                                "price": _safe_float(item.get("markPrice")),
                                "exchange": "binance"
                            }
                    return result
    except Exception as e:
        state.errors.append(f"Binance funding: {e}")
    return {}


async def fetch_binance_oi(symbol: str = "BTCUSDT"):
    """GET /fapi/v1/openInterest — OI actuel d'un symbole."""
    if not aiohttp: return {}
    url = f"{state.binance_api_base}/fapi/v1/openInterest?symbol={symbol}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"symbol": symbol, "oi": _safe_float(data.get("openInterest")), "exchange": "binance"}
    except Exception as e:
        state.errors.append(f"Binance OI: {e}")
    return {}


async def fetch_binance_liquidations(symbol: str = "BTCUSDT", limit: int = 5):
    """GET /fapi/v1/allForceOrders — Dernières liquidations."""
    if not aiohttp: return []
    url = f"{state.binance_api_base}/fapi/v1/allForceOrders?symbol={symbol}&limit={limit}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data[:limit]
    except Exception as e:
        state.errors.append(f"Binance Liq: {e}")
    return []


async def fetch_binance_new_listings(limit: int = 10):
    """
    Binance n'a pas d'endpoint direct "new listings" public sans auth parfois,
    mais on peut scraper la page d'annonce ou utiliser l'endpoint ticker pour détecter
    les nouveaux symbols récents.
    Ici on utilise une astuce : on regarde les top gagnants du 24h (souvent les nouveaux listés).
    """
    if not aiohttp: return []
    url = f"{state.binance_api_base}/fapi/v1/ticker/24hr"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Trie par % de changement (gagnants = souvent volatiles/nouveaux)
                    data.sort(key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)
                    return [{"symbol": d["symbol"], "change%": d["priceChangePercent"], "volume": d["volume"]} for d in data[:limit]]
    except Exception as e:
        state.errors.append(f"Binance Listings/Gainers: {e}")
    return []


# =========================================================
# BYBIT (Unified)
# =========================================================

async def fetch_bybit_funding():
    """GET /v5/market/tickers — Funding rates."""
    if not aiohttp: return {}
    url = f"{state.bybit_api_base}/v5/market/tickers?category=linear"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    resp_data = await resp.json()
                    if resp_data.get("retCode") == 0:
                        result = {}
                        for item in resp_data["result"]["list"]:
                            sym = item.get("symbol", "")
                            if "USDT" in sym:
                                result[sym] = {
                                    "funding_rate": _safe_float(item.get("fundingRate")),
                                    "next_funding": item.get("nextFundingTime", ""),
                                    "price": _safe_float(item.get("lastPrice")),
                                    "oi": _safe_float(item.get("openInterest")),
                                    "exchange": "bybit"
                                }
                        return result
    except Exception as e:
        state.errors.append(f"Bybit funding: {e}")
    return {}


# =========================================================
# ORCHESTRATOR
# =========================================================

async def run_aggregation_cycle():
    """Cycle unique : fetch toutes les données, détecte anomalies."""
    print(f"[AGGR] Fetching data cycle at {datetime.now().strftime('%H:%M:%S')}")
    start = time.time()

    # 1. Funding Rates Multi-Exchange
    binance_funding = await fetch_binance_funding()
    bybit_funding = await fetch_bybit_funding()

    # Merge
    all_funding = {}
    for sym, data in binance_funding.items():
        if sym not in all_funding: all_funding[sym] = {}
        all_funding[sym]["binance"] = data

    for sym, data in bybit_funding.items():
        if sym not in all_funding: all_funding[sym] = {}
        all_funding[sym]["bybit"] = data

    state.funding_data = all_funding

    # 2. OI Checks (BTC/ETH/SOL/XAU)
    symbols_to_check = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT"]
    oi_results = {}
    for sym in symbols_to_check:
        oi = await fetch_binance_oi(sym)
        oi_results[sym] = oi

    state.oi_data = oi_results

    # 3. Top Volatility / New Listings candidates
    listings = await fetch_binance_new_listings()
    state.listings = listings

    # 4. Liquidation Check
    liqs = await fetch_binance_liquidations()

    state.last_update = time.time()

    # Sauvegarde snapshot
    snapshot = {
        "ts": state.last_update,
        "funding_summary": {k: {"binance": v.get("binance", {}).get("rate"),
                                  "bybit": v.get("bybit", {}).get("funding_rate")}
                            for k, v in all_funding.items() if "BTC" in k or "ETH" in k},
        "oi_data": oi_results,
        "top_gainers": listings[:5],
        "recent_liquidations": liqs[:5]
    }

    path = SNAPSHOT_DIR / "multi_exchange_latest.json"
    try:
        import json
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    except Exception:
        pass

    duration = time.time() - start
    print(f"[AGGR] Cycle complete in {duration:.2f}s. Errors: {len(state.errors)}")


async def aggregation_loop(interval: float = 60.0):
    """Loop principale."""
    while True:
        try:
            await run_aggregation_cycle()
        except Exception as e:
            state.errors.append(f"Loop error: {e}")
        await asyncio.sleep(interval)


def get_aggr_state() -> dict:
    return {
        "last_update": state.last_update,
        "errors": state.errors[-5:],
        "funding_data_count": len(state.funding_data),
        "oi_data": state.oi_data,
        "top_gainers": state.listings[:5] if state.listings else [],
    }
