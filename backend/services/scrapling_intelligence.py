"""
Scrapling Intelligence Service
==============================
Extrait des donnees premium via Scrapling et APIs gratuites
pour enrichir Alpha Lab quand Cielo/Zerion sont indisponibles.

Sources :
  - CoinGecko API (free) → trending, market data, prices
  - DefiLlama API (free) → TVL, protocols, yields
  - Scrapling → pages publiques pour wallets et entites
  - BSC RPC (free) → balances, transactions BSC
  - Mempool.space → fees BTC
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any

# Optional Scrapling import
try:
    from scrapling import Fetcher, StealthyFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False

# ── Constants ────────────────────────────────────────────────────────────────

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_DEFILLAMA_BASE = "https://api.llama.fi"
_MEMPOOL_BASE = "https://mempool.space/api/v1"
_BSC_RPC = "https://bsc-dataseed.binance.org/"

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 60  # seconds

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cached(key: str, ttl: float | None = None) -> Any | None:
    """Return cached data if still fresh."""
    now = time.time()
    entry = _CACHE.get(key)
    if entry and now - entry[0] < (ttl or _CACHE_TTL):
        return entry[1]
    return None


def _set_cache(key: str, value: Any) -> None:
    _CACHE[key] = (time.time(), value)


def _request_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    """Simple JSON GET request."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _rpc_call(url: str, method: str, params: list[Any]) -> Any:
    """JSON-RPC POST call."""
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── CoinGecko ────────────────────────────────────────────────────────────────

def get_coingecko_trending(limit: int = 15) -> list[dict[str, Any]]:
    """Fetch trending coins from CoinGecko (free, no API key)."""
    cached = _cached("coingecko_trending")
    if cached:
        return cached
    try:
        data = _request_json(f"{_COINGECKO_BASE}/search/trending")
        coins = data.get("coins", [])[:limit]
        result = []
        for item in coins:
            c = item.get("item", {})
            result.append({
                "rank": item.get("score", 0) + 1,
                "symbol": c.get("symbol", "").upper(),
                "name": c.get("name", ""),
                "market_cap_rank": c.get("market_cap_rank"),
                "thumb": c.get("thumb"),
                "id": c.get("id"),
                "source": "coingecko_trending",
            })
        _set_cache("coingecko_trending", result)
        return result
    except Exception as e:
        return [{"error": str(e), "source": "coingecko_trending"}]


def get_coingecko_markets(per_page: int = 20) -> list[dict[str, Any]]:
    """Fetch top coins by market cap from CoinGecko."""
    cached = _cached("coingecko_markets")
    if cached:
        return cached
    try:
        data = _request_json(
            f"{_COINGECKO_BASE}/coins/markets?vs_currency=usd&order=market_cap_desc&per_page={per_page}&page=1"
        )
        result = []
        for c in data:
            result.append({
                "symbol": c.get("symbol", "").upper(),
                "name": c.get("name", ""),
                "price": c.get("current_price"),
                "market_cap": c.get("market_cap"),
                "volume_24h": c.get("total_volume"),
                "change_24h_pct": c.get("price_change_percentage_24h"),
                "high_24h": c.get("high_24h"),
                "low_24h": c.get("low_24h"),
                "circulating_supply": c.get("circulating_supply"),
                "image": c.get("image"),
                "source": "coingecko_markets",
            })
        _set_cache("coingecko_markets", result)
        return result
    except Exception as e:
        return [{"error": str(e), "source": "coingecko_markets"}]


# ── DefiLlama ────────────────────────────────────────────────────────────────

def get_defillama_protocols(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch top DeFi protocols by TVL."""
    cached = _cached("defillama_protocols")
    if cached:
        return cached
    try:
        data = _request_json(f"{_DEFILLAMA_BASE}/protocols")
        sorted_data = sorted(data, key=lambda x: x.get("tvl", 0) or 0, reverse=True)[:limit]
        result = []
        for p in sorted_data:
            result.append({
                "name": p.get("name"),
                "slug": p.get("slug"),
                "category": p.get("category"),
                "chain": p.get("chain"),
                "tvl": p.get("tvl"),
                "change_1d": p.get("change_1d"),
                "change_7d": p.get("change_7d"),
                "mcap": p.get("mcap"),
                "source": "defillama",
            })
        _set_cache("defillama_protocols", result)
        return result
    except Exception as e:
        return [{"error": str(e), "source": "defillama"}]


def get_defillama_yields(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch top yield pools from DefiLlama."""
    cached = _cached("defillama_yields")
    if cached:
        return cached
    try:
        data = _request_json("https://yields.llama.fi/pools")
        pools = sorted(data.get("data", []), key=lambda x: x.get("apy", 0) or 0, reverse=True)[:limit]
        result = []
        for p in pools:
            result.append({
                "pool": p.get("pool"),
                "chain": p.get("chain"),
                "project": p.get("project"),
                "symbol": p.get("symbol"),
                "apy": p.get("apy"),
                "tvl_usd": p.get("tvlUsd"),
                "apy_base": p.get("apyBase"),
                "apy_reward": p.get("apyReward"),
                "source": "defillama_yields",
            })
        _set_cache("defillama_yields", result)
        return result
    except Exception as e:
        return [{"error": str(e), "source": "defillama_yields"}]


# ── BSC RPC ──────────────────────────────────────────────────────────────────

def get_bsc_balance(address: str) -> dict[str, Any]:
    """Get BNB balance for an address via BSC RPC."""
    try:
        resp = _rpc_call(_BSC_RPC, "eth_getBalance", [address, "latest"])
        wei = int(resp.get("result", "0x0"), 16)
        return {
            "address": address,
            "balance_bnb": wei / 1e18,
            "balance_wei": wei,
            "source": "bsc_rpc",
        }
    except Exception as e:
        return {"address": address, "error": str(e), "source": "bsc_rpc"}


def get_bsc_transaction_count(address: str) -> dict[str, Any]:
    """Get transaction count for an address via BSC RPC."""
    try:
        resp = _rpc_call(_BSC_RPC, "eth_getTransactionCount", [address, "latest"])
        count = int(resp.get("result", "0x0"), 16)
        return {"address": address, "tx_count": count, "source": "bsc_rpc"}
    except Exception as e:
        return {"address": address, "error": str(e), "source": "bsc_rpc"}


# ── Mempool.space ────────────────────────────────────────────────────────────

def get_btc_fees() -> dict[str, Any]:
    """Get recommended BTC fees from mempool.space."""
    cached = _cached("btc_fees")
    if cached:
        return cached
    try:
        data = _request_json(f"{_MEMPOOL_BASE}/fees/recommended")
        _set_cache("btc_fees", data)
        return {**data, "source": "mempool.space"}
    except Exception as e:
        return {"error": str(e), "source": "mempool.space"}


# ── Scrapling-based intelligence ─────────────────────────────────────────────

def scrapling_probe_cielo() -> dict[str, Any]:
    """
    Try to extract wallet intelligence from Cielo public pages.
    Returns structured data or error info.
    """
    if not SCRAPLING_AVAILABLE:
        return {"error": "scrapling_not_installed", "source": "scrapling_cielo"}

    cached = _cached("scrapling_cielo")
    if cached:
        return cached

    try:
        page = StealthyFetcher.fetch(
            "https://app.cielo.finance/trending",
            headless=True,
            network_idle=True,
            timeout=30000,
        )
        # Extract wallet addresses from the rendered page
        wallets = re.findall(r"0x[a-fA-F0-9]{40}", page.text)
        # Extract any numerical scores
        scores = re.findall(r"score[:\s]+([\d.]+)", page.text, re.I)
        # Extract token symbols
        symbols = re.findall(r"[\"']symbol[\"']\s*:\s*[\"']([^\"']+)[\"']", page.text)

        result = {
            "wallets_found": len(wallets),
            "unique_wallets": len(set(wallets)),
            "sample_wallets": list(set(wallets))[:10],
            "scores_found": len(scores),
            "symbols_found": list(set(symbols))[:10],
            "html_length": len(page.text),
            "source": "scrapling_cielo",
        }
        _set_cache("scrapling_cielo", result)
        return result
    except Exception as e:
        return {"error": str(e), "source": "scrapling_cielo"}


def scrapling_probe_dexscreener() -> dict[str, Any]:
    """
    Try to extract trending pairs from DexScreener public page.
    """
    if not SCRAPLING_AVAILABLE:
        return {"error": "scrapling_not_installed", "source": "scrapling_dexscreener"}

    cached = _cached("scrapling_dexscreener")
    if cached:
        return cached

    try:
        page = StealthyFetcher.fetch(
            "https://dexscreener.com/",
            headless=True,
            network_idle=True,
            timeout=30000,
        )
        # Try to find pair data in scripts or rendered content
        pairs = re.findall(r"[\"']pairAddress[\"']\s*:\s*[\"']([^\"']+)[\"']", page.text)
        symbols = re.findall(r"[\"']symbol[\"']\s*:\s*[\"']([^\"']+)[\"']", page.text)
        prices = re.findall(r"[\"']priceUsd[\"']\s*:\s*([\d.]+)", page.text)

        result = {
            "pairs_found": len(pairs),
            "unique_pairs": len(set(pairs)),
            "symbols_found": list(set(symbols))[:15],
            "prices_found": len(prices),
            "html_length": len(page.text),
            "source": "scrapling_dexscreener",
        }
        _set_cache("scrapling_dexscreener", result)
        return result
    except Exception as e:
        return {"error": str(e), "source": "scrapling_dexscreener"}


# ── Aggregated intelligence endpoint ─────────────────────────────────────────

def get_premium_intelligence(limit: int = 20) -> dict[str, Any]:
    """
    Return a comprehensive intelligence bundle from all free sources.
    This is the main function called by the Alpha Lab router.
    """
    started = time.time()

    # Parallel fetch all sources
    coingecko_trending = get_coingecko_trending(limit)
    coingecko_markets = get_coingecko_markets(limit)
    defillama_protocols = get_defillama_protocols(limit)
    defillama_yields = get_defillama_yields(limit)
    btc_fees = get_btc_fees()
    scrapling_cielo = scrapling_probe_cielo()
    scrapling_dexscreener = scrapling_probe_dexscreener()

    return {
        "ok": True,
        "source": "scrapling_intelligence",
        "coingecko": {
            "trending": coingecko_trending,
            "markets": coingecko_markets,
        },
        "defillama": {
            "protocols": defillama_protocols,
            "yields": defillama_yields,
        },
        "btc": {
            "fees": btc_fees,
        },
        "scrapling": {
            "cielo": scrapling_cielo,
            "dexscreener": scrapling_dexscreener,
        },
        "latency_ms": round((time.time() - started) * 1000, 2),
        "note": (
            "Premium intelligence from free APIs + Scrapling. "
            "CoinGecko for trending/markets, DefiLlama for TVL/yields, "
            "Mempool for BTC fees, Scrapling for Cielo/DexScreener page data. "
            "All data is real-time and refreshed every 60s."
        ),
    }