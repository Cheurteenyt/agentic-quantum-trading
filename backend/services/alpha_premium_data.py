"""
Alpha Premium Data Service
==========================
Agrège Cielo + Zerion + Etherscan pour produire des métriques premium
style Arkham Intelligence.

Métriques:
  - on_chain_value_usd   → total portfolio tracked
  - asset_flow_24h       → volume DEX 24h
  - smart_money_score    → score algorithmique 0-100
  - top_tokens           → tokens les plus tradés
  - dex_distribution     → volume par DEX
  - chain_breakdown      → répartition par chaîne
  - first_interaction_rate → % nouveaux wallets
  - wallet_velocity      → volume moyen/wallet
  - concentration_index  → Gini du volume
  - labelled_wallets     → wallets avec label
  - active_wallets_24h   → wallets actifs récents
"""

from __future__ import annotations

import base64
import json
import math
import os
import time
import urllib.parse
import urllib.request
from typing import Any

CIELO_BASE = "https://feed-api.cielo.finance/api"
ZERION_BASE = "https://api.zerion.io/v1"
ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"

_USER_AGENT = "HermesAlphaLab/0.1"
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 60


def _cached(key: str, ttl: float = 60) -> Any | None:
    entry = _CACHE.get(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    return None


def _set_cache(key: str, value: Any) -> None:
    _CACHE[key] = (time.time(), value)


def _request(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": _USER_AGENT, **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        text = body.decode("utf-8", errors="ignore")
        if text.startswith("{"):
            return json.loads(text)
        elif text.startswith("<"):
            import re
            m = re.search(r"<body>\\s*<p>(\\{.*?\\})</p>\\s*</body>", text, re.DOTALL)
            return json.loads(m.group(1)) if m else {}
        return json.loads(text)


def _cielo_key() -> str | None:
    return (os.getenv("CIELO_API_KEY") or os.getenv("CIELO_KEY") or "").strip() or None


def _zerion_auth() -> str | None:
    key = os.getenv("ZERION_API_KEY")
    if not key:
        return None
    return f"Basic {base64.b64encode(f'{key}:'.encode()).decode('ascii')}"


def _etherscan_key() -> str | None:
    return os.getenv("ETHERSCAN_API_KEY", "").strip() or None


# ── CIELO AGGREGATES ─────────────────────────────────────────────────────────

def _cielo_feed(limit: int = 100, tx_types: str = "swap", min_usd: float | None = None) -> list[dict]:
    key = _cielo_key()
    if not key:
        return []
    cache_key = f"cielo_{limit}_{tx_types}_{min_usd}"
    cached = _cached(cache_key)
    if cached:
        return cached
    params = {"limit": str(limit), "txTypes": tx_types}
    if min_usd:
        params["minUSD"] = str(min_usd)
    try:
        data = _request(f"{CIELO_BASE}/v1/feed?{urllib.parse.urlencode(params)}", headers={"X-API-KEY": key})
        items = data.get("data", {}).get("items", [])
        _set_cache(cache_key, items)
        return items
    except Exception:
        return []


def _compute_cielo_stats(items: list[dict]) -> dict[str, Any]:
    if not items:
        return {"ok": False, "error": "no_cielo_data"}

    wallets: dict[str, dict[str, Any]] = {}
    tokens: dict[str, dict[str, Any]] = {}
    dexes: dict[str, float] = {}
    chains: dict[str, int] = {}
    total_volume = 0.0
    first_interactions = 0
    labelled = 0

    for item in items:
        w = item.get("wallet", "").lower()
        if not w:
            continue

        vol = item.get("token0_amount_usd", 0.0) or item.get("amount_usd", 0.0) or 0.0
        total_volume += vol

        if w not in wallets:
            wallets[w] = {"volume": 0.0, "events": 0, "tokens": set(), "chains": set()}
        wallets[w]["volume"] += vol
        wallets[w]["events"] += 1
        wallets[w]["tokens"].add(item.get("token0_symbol", ""))
        wallets[w]["tokens"].add(item.get("token1_symbol", ""))
        wallets[w]["chains"].add(item.get("chain", "unknown"))

        if item.get("first_interaction"):
            first_interactions += 1
        if item.get("wallet_label") and item["wallet_label"] != w[:10] + "...":
            labelled += 1

        t0 = item.get("token0_symbol", "")
        if t0:
            if t0 not in tokens:
                tokens[t0] = {"volume": 0.0, "events": 0, "address": item.get("token0_address", "")}
            tokens[t0]["volume"] += vol
            tokens[t0]["events"] += 1

        dex = item.get("dex", "unknown")
        dexes[dex] = dexes.get(dex, 0.0) + vol

        chain = item.get("chain", "unknown")
        chains[chain] = chains.get(chain, 0) + 1

    # Sort and rank
    top_wallets = sorted(wallets.items(), key=lambda x: x[1]["volume"], reverse=True)[:10]
    top_tokens = sorted(tokens.items(), key=lambda x: x[1]["volume"], reverse=True)[:10]
    dex_rank = sorted(dexes.items(), key=lambda x: x[1], reverse=True)
    chain_rank = sorted(chains.items(), key=lambda x: x[1], reverse=True)

    # Gini concentration
    volumes = sorted([w["volume"] for w in wallets.values()])
    gini = _gini_coefficient(volumes) if volumes else 0.0

    # Smart money score
    smart_wallets = [
        {
            "wallet": w,
            "volume": info["volume"],
            "events": info["events"],
            "tokens": list(info["tokens"]),
            "chains": list(info["chains"]),
            "score": round(min(100, info["volume"] / 1000 + info["events"] * 5), 1),
        }
        for w, info in sorted(wallets.items(), key=lambda x: x[1]["volume"], reverse=True)[:20]
    ]

    return {
        "ok": True,
        "wallets_tracked": len(wallets),
        "labelled_wallets": labelled,
        "total_volume_24h": round(total_volume, 2),
        "first_interaction_rate": round(first_interactions / len(items) * 100, 1) if items else 0,
        "wallet_velocity": round(total_volume / len(wallets), 2) if wallets else 0,
        "concentration_index": round(gini, 2),
        "top_wallets": top_wallets,
        "top_tokens": [
            {"symbol": sym, "volume": round(info["volume"], 2), "events": info["events"], "address": info["address"]}
            for sym, info in top_tokens
        ],
        "dex_distribution": [
            {"name": name, "volume": round(vol, 2), "share_pct": round(vol / total_volume * 100, 1)}
            for name, vol in dex_rank
        ],
        "chain_breakdown": [
            {"chain": chain, "events": count, "share_pct": round(count / len(items) * 100, 1)}
            for chain, count in chain_rank
        ],
        "smart_money": smart_wallets,
    }


# ── ZERION AGGREGATES ────────────────────────────────────────────────────────

def _zerion_portfolio(wallet: str) -> dict[str, Any] | None:
    auth = _zerion_auth()
    if not auth:
        return None
    cache_key = f"zerion_{wallet}"
    cached = _cached(cache_key)
    if cached:
        return cached
    try:
        data = _request(f"{ZERION_BASE}/wallets/{wallet}/portfolio?currency=usd", headers={"Authorization": auth})
        attrs = data.get("data", {}).get("attributes", {})
        result = {
            "total_positions": attrs.get("total", {}).get("positions", 0),
            "distribution_by_type": attrs.get("positions_distribution_by_type", {}),
            "distribution_by_chain": attrs.get("positions_distribution_by_chain", {}),
            "change_1d_pct": attrs.get("changes", {}).get("percent_1d", 0),
            "change_1d_usd": attrs.get("changes", {}).get("absolute_1d", 0),
        }
        _set_cache(cache_key, result)
        return result
    except Exception:
        return None


# ── ETHERSCAN AGGREGATES ─────────────────────────────────────────────────────

def _etherscan_balance(wallet: str) -> float | None:
    key = _etherscan_key()
    if not key:
        return None
    cache_key = f"eth_bal_{wallet}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached
    try:
        url = f"{ETHERSCAN_V2}?chainid=1&module=account&action=balance&address={wallet}&tag=latest&apikey={key}"
        data = _request(url)
        bal = int(data.get("result", "0")) / 1e18
        _set_cache(cache_key, bal)
        return bal
    except Exception:
        return None


def _etherscan_token_holdings(wallet: str) -> list[dict]:
    key = _etherscan_key()
    if not key:
        return []
    cache_key = f"eth_tok_{wallet}"
    cached = _cached(cache_key)
    if cached:
        return cached
    try:
        url = f"{ETHERSCAN_V2}?chainid=1&module=account&action=tokentx&address={wallet}&startblock=0&endblock=99999999&sort=desc&apikey={key}"
        data = _request(url)
        txs = data.get("result", [])[:50]
        seen = {}
        for tx in txs:
            sym = tx.get("tokenSymbol", "")
            if sym and sym not in seen:
                seen[sym] = {
                    "symbol": sym,
                    "name": tx.get("tokenName", ""),
                    "contract": tx.get("contractAddress", ""),
                }
        result = list(seen.values())[:15]
        _set_cache(cache_key, result)
        return result
    except Exception:
        return []


# ── UTILS ────────────────────────────────────────────────────────────────────

def _gini_coefficient(values: list[float]) -> float:
    """Compute Gini coefficient for concentration measurement."""
    if not values or len(values) < 2:
        return 0.0
    n = len(values)
    index = sum((2 * i - n - 1) * v for i, v in enumerate(sorted(values), 1))
    return index / (n * sum(values)) if sum(values) > 0 else 0.0


# ── MAIN AGGREGATOR ──────────────────────────────────────────────────────────

def get_premium_alpha_stats(wallet: str | None = None, feed_limit: int = 100) -> dict[str, Any]:
    """
    Aggregate Cielo + Zerion + Etherscan into Arkham-style premium metrics.
    """
    started = time.time()

    # 1. Cielo global feed
    cielo_items = _cielo_feed(limit=feed_limit)
    cielo_stats = _compute_cielo_stats(cielo_items) if cielo_items else {"ok": False}

    # 2. Zerion portfolio for specific wallet
    zerion_stats = None
    if wallet:
        zerion_stats = _zerion_portfolio(wallet)

    # 3. Etherscan on-chain data
    eth_balance = _etherscan_balance(wallet) if wallet else None
    eth_tokens = _etherscan_token_holdings(wallet) if wallet else []

    # 4. Compute composite smart money score
    composite_score = 0.0
    if cielo_stats.get("ok"):
        composite_score += min(50, cielo_stats.get("wallet_velocity", 0) / 100)
        composite_score += min(30, (100 - cielo_stats.get("concentration_index", 0)) * 0.3)
        composite_score += min(20, cielo_stats.get("first_interaction_rate", 0) * 0.2)

    return {
        "ok": True,
        "wallet": wallet,
        "timestamp": time.time(),
        "latency_ms": round((time.time() - started) * 1000, 2),
        "premium": {
            "on_chain_value_usd": zerion_stats.get("total_positions") if zerion_stats else None,
            "asset_flow_24h": cielo_stats.get("total_volume_24h") if cielo_stats.get("ok") else None,
            "wallets_tracked": cielo_stats.get("wallets_tracked") if cielo_stats.get("ok") else 0,
            "labelled_wallets": cielo_stats.get("labelled_wallets") if cielo_stats.get("ok") else 0,
            "smart_money_score": round(composite_score, 1),
            "first_interaction_rate_pct": cielo_stats.get("first_interaction_rate") if cielo_stats.get("ok") else 0,
            "concentration_index": cielo_stats.get("concentration_index") if cielo_stats.get("ok") else 0,
            "wallet_velocity": cielo_stats.get("wallet_velocity") if cielo_stats.get("ok") else 0,
        },
        "cielo": cielo_stats if cielo_stats.get("ok") else {"error": "cielo_unavailable"},
        "zerion": zerion_stats if zerion_stats else {"error": "zerion_unavailable"},
        "etherscan": {
            "eth_balance": eth_balance,
            "token_holdings": eth_tokens,
            "token_count": len(eth_tokens),
        },
    }