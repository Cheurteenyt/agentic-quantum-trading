"""Alpha Lab token sellability probes.

Combines DexScreener, Honeypot.is and explorer scraping. Keep this module
isolated because it performs network calls and optional Scrapling browser fetches.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
import urllib.request
from typing import Any


_SELL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SELL_CACHE_TTL = 120

_CHAIN_EXPLORER: dict[str, str] = {
    "ethereum": "https://etherscan.io",
    "eth": "https://etherscan.io",
    "bsc": "https://bscscan.com",
    "bnb": "https://bscscan.com",
    "polygon": "https://polygonscan.com",
    "matic": "https://polygonscan.com",
    "arbitrum": "https://arbiscan.io",
    "arb": "https://arbiscan.io",
    "optimism": "https://optimistic.etherscan.io",
    "base": "https://basescan.org",
    "solana": "https://solscan.io",
    "sol": "https://solscan.io",
}

_HONEYPOT_API = "https://api.honeypot.is/v2/IsHoneypot"
_DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens/"
_HTTP_TIMEOUT = 10


def probe_token_sellability(token_address: str, chain: str = "ethereum") -> dict[str, Any]:
    """Multi-source sellability gate used by Alpha Lab token-risk scoring."""
    cache_key = f"{chain}:{token_address.lower()}"
    now = time.time()
    cached = _SELL_CACHE.get(cache_key)
    if cached and now - cached[0] < _SELL_CACHE_TTL:
        return cached[1]

    result: dict[str, Any] = {
        "token_address": token_address,
        "chain": chain,
        "dexscreener": None,
        "honeypot_api": None,
        "explorer_scrape": None,
        "consensus": "unknown",
        "overall_sellable": None,
        "sellability_confidence": 0.0,
        "auto_flags": [],
    }

    result["dexscreener"] = _fetch_dexscreener(token_address)
    result["honeypot_api"] = _fetch_honeypot_api(token_address, chain)

    hp = result["honeypot_api"] or {}
    api_ambiguous = hp.get("confidence", 0) < 0.75 or hp.get("error")
    if api_ambiguous:
        result["explorer_scrape"] = _scrape_explorer(token_address, chain)

    result["consensus"], result["overall_sellable"], result["sellability_confidence"] = (
        _compute_sellability_consensus(result)
    )
    result["auto_flags"] = _sellability_auto_flags(result)

    _SELL_CACHE[cache_key] = (now, result)
    return result


def _fetch_dexscreener(token_address: str) -> dict[str, Any]:
    url = _DEXSCREENER_API + urllib.parse.quote(token_address)
    try:
        data = _http_json(url)
        pairs = data.get("pairs") or []
        if not pairs:
            return {"ok": False, "reason": "no_pairs"}
        pairs.sort(key=lambda p: _float(p.get("liquidity", {}).get("usd"), 0), reverse=True)
        pair = pairs[0]
        liq = pair.get("liquidity") or {}
        vol = pair.get("volume") or {}
        txn = pair.get("txns", {}).get("h24") or {}
        liq_usd = _float_or_none(liq.get("usd"))
        vol_24h = _float_or_none(vol.get("h24"))
        buys_24h = _float(txn.get("buys"), 0)
        sells_24h = _float(txn.get("sells"), 0)
        flags: list[str] = []
        if liq_usd is not None and liq_usd < 10_000:
            flags.append("very_low_liquidity")
        if vol_24h and liq_usd and vol_24h > liq_usd * 8:
            flags.append("wash_volume_suspected")
        if sells_24h == 0 and buys_24h > 5:
            flags.append("zero_sells_many_buys")
        return {
            "ok": True,
            "liquidity_usd": liq_usd,
            "volume_24h": vol_24h,
            "buys_24h": buys_24h,
            "sells_24h": sells_24h,
            "price_usd": _float_or_none(pair.get("priceUsd")),
            "dex": pair.get("dexId"),
            "pair_address": pair.get("pairAddress"),
            "flags": flags,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def _fetch_honeypot_api(token_address: str, chain: str) -> dict[str, Any]:
    chain_id_map = {
        "ethereum": "1",
        "eth": "1",
        "bsc": "56",
        "bnb": "56",
        "polygon": "137",
        "matic": "137",
        "arbitrum": "42161",
        "arb": "42161",
        "base": "8453",
        "optimism": "10",
    }
    cid = chain_id_map.get(chain.lower(), "1")
    url = f"{_HONEYPOT_API}?address={urllib.parse.quote(token_address)}&chainID={cid}"
    try:
        data = _http_json(url)
        hp = data.get("honeypotResult") or {}
        sim = data.get("simulationResult") or {}
        token_info = data.get("token") or {}
        is_hp = bool(hp.get("isHoneypot"))
        sell_tax = _float_or_none(sim.get("sellTax"))
        buy_tax = _float_or_none(sim.get("buyTax"))
        flags: list[str] = []
        if is_hp:
            flags.append("honeypot_confirmed")
        if sell_tax is not None and sell_tax >= 50:
            flags.append("extreme_sell_tax")
        elif sell_tax is not None and sell_tax >= 20:
            flags.append("high_sell_tax")
        confidence = 0.90 if (sim.get("sellGas") or is_hp) else 0.55
        return {
            "ok": True,
            "is_honeypot": is_hp,
            "buy_tax_pct": buy_tax,
            "sell_tax_pct": sell_tax,
            "sell_gas": _float_or_none(sim.get("sellGas")),
            "holders": _float_or_none(token_info.get("totalHolders")),
            "flags": flags,
            "confidence": confidence,
            "raw_reason": hp.get("honeypotReason"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120], "confidence": 0.0}


def _scrape_explorer(token_address: str, chain: str) -> dict[str, Any]:
    """Scrapling-first explorer scrape, urllib fallback."""
    base = _CHAIN_EXPLORER.get(chain.lower(), "https://etherscan.io")
    url = f"{base}/token/{urllib.parse.quote(token_address)}"

    try:
        from scrapling.defaults import Fetcher, StealthyFetcher

        page = None
        try:
            page = Fetcher.get(url, timeout=_HTTP_TIMEOUT, stealthy_headers=True)
            if not page or page.status != 200:
                page = None
        except Exception:
            pass
        if page is None:
            page = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=_HTTP_TIMEOUT * 2)
        if page and page.status == 200:
            return _parse_with_scrapling(page, url)
    except ImportError:
        pass
    except Exception:
        pass

    html = _http_html(url)
    if not html:
        return {"ok": False, "reason": "fetch_failed", "source_url": url}
    return _parse_with_html(html, url)


def _parse_with_scrapling(page: Any, url: str) -> dict[str, Any]:
    page_text = (page.html or "").lower()
    sell_blocked = any(k in page_text for k in ("cannot sell", "sell disabled", "unable to sell"))
    honeypot_warn = any(k in page_text for k in ("honeypot", "unsellable", "scam", "rug"))
    verified = bool(page.css('[title*="Verified"], .contract-verified'))
    has_blacklist = "blacklist" in page_text
    has_freeze = "freeze" in page_text or "pausable" in page_text
    has_mint = "mint" in page_text
    match = re.search(r"sell\s+(?:tax|fee)[:\s]+(\d+(?:\.\d+)?)\s*%", page_text)
    confidence = 0.82 if (sell_blocked or honeypot_warn) else 0.58
    if verified:
        confidence += 0.08
    return {
        "ok": True,
        "method": "scrapling",
        "sell_blocked": sell_blocked,
        "honeypot_warn": honeypot_warn,
        "verified": verified,
        "has_blacklist": has_blacklist,
        "has_freeze": has_freeze,
        "has_mint": has_mint,
        "sell_tax_pct": float(match.group(1)) if match else None,
        "confidence": round(min(0.93, confidence), 2),
        "source_url": url,
    }


def _parse_with_html(html: str, url: str) -> dict[str, Any]:
    text = html.lower()
    sell_blocked = any(k in text for k in ("cannot sell", "unable to sell", "sell disabled"))
    honeypot_warn = any(k in text for k in ("honeypot", "unsellable", "trap contract"))
    verified = "verified contract" in text or "contract source code verified" in text
    match = re.search(r"sell\s+(?:tax|fee)[:\s]+(\d+(?:\.\d+)?)\s*%", text)
    confidence = 0.72 if (sell_blocked or honeypot_warn) else 0.40
    if verified:
        confidence += 0.06
    return {
        "ok": True,
        "method": "urllib",
        "sell_blocked": sell_blocked,
        "honeypot_warn": honeypot_warn,
        "verified": verified,
        "has_blacklist": "blacklist" in text,
        "has_freeze": "freeze" in text or "pausable" in text,
        "has_mint": "mint" in text,
        "sell_tax_pct": float(match.group(1)) if match else None,
        "confidence": round(min(0.78, confidence), 2),
        "source_url": url,
    }


def _compute_sellability_consensus(result: dict[str, Any]) -> tuple[str, bool | None, float]:
    hp = result.get("honeypot_api") or {}
    ds = result.get("dexscreener") or {}
    exp = result.get("explorer_scrape") or {}

    if hp.get("ok") and hp.get("confidence", 0) >= 0.6 and hp.get("is_honeypot"):
        return "honeypot", False, hp.get("confidence", 0.85)
    if exp.get("ok") and exp.get("sell_blocked"):
        return "sell_blocked", False, exp.get("confidence", 0.75)
    if "very_low_liquidity" in (ds.get("flags") or []):
        return "insufficient_liquidity", False, 0.80
    if hp.get("ok") and not hp.get("is_honeypot") and hp.get("confidence", 0) >= 0.6:
        return "sellable", True, hp.get("confidence", 0.70)
    if exp.get("ok") and not exp.get("sell_blocked") and not exp.get("honeypot_warn"):
        return "probably_sellable", True, exp.get("confidence", 0.55)
    if ds.get("ok") and ds.get("sells_24h", 0) > 0 and ds.get("liquidity_usd", 0) >= 10_000:
        return "market_evidence", True, 0.60
    return "unknown", None, 0.30


def _sellability_auto_flags(result: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    hp = result.get("honeypot_api") or {}
    ds = result.get("dexscreener") or {}
    exp = result.get("explorer_scrape") or {}

    if result.get("consensus") == "honeypot":
        flags.append({
            "code": "honeypot_confirmed",
            "severity": "critical",
            "points": 48,
            "detail": f"Honeypot.is confirmed ({hp.get('confidence', 0):.0%}). Sell simulation failed.",
        })
    if result.get("consensus") == "sell_blocked":
        flags.append({
            "code": "sell_blocked_on_chain",
            "severity": "critical",
            "points": 45,
            "detail": "Explorer shows sell is blocked.",
        })
    sell_tax = hp.get("sell_tax_pct") or exp.get("sell_tax_pct")
    if sell_tax is not None:
        if sell_tax >= 50:
            flags.append({
                "code": "extreme_sell_tax",
                "severity": "critical",
                "points": 35,
                "detail": f"Sell tax {sell_tax:.1f}% — profit unextractable.",
            })
        elif sell_tax >= 20:
            flags.append({
                "code": "high_sell_tax",
                "severity": "high",
                "points": 22,
                "detail": f"Sell tax {sell_tax:.1f}% — haircut exits in backtest.",
            })
    liq = ds.get("liquidity_usd")
    if liq is not None and liq < 10_000:
        flags.append({"code": "very_low_liquidity", "severity": "critical", "points": 30, "detail": f"DEX liquidity only ${liq:,.0f}."})
    if ds.get("ok") and ds.get("sells_24h", 1) == 0 and ds.get("buys_24h", 0) > 5:
        flags.append({
            "code": "zero_sells_many_buys",
            "severity": "high",
            "points": 25,
            "detail": "No sells in 24h despite active buying — buy-only token.",
        })
    if exp.get("has_blacklist"):
        flags.append({"code": "blacklist_function", "severity": "critical", "points": 35, "detail": "Blacklist function detected on explorer."})
    if exp.get("has_freeze"):
        flags.append({"code": "freeze_function", "severity": "critical", "points": 35, "detail": "Freeze/pause function detected on explorer."})
    return flags


def _http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "HermesAlphaLab/1.0"})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_html(url: str) -> str | None:
    """Scrapling-first HTML fetch, urllib fallback."""
    try:
        from scrapling.defaults import Fetcher

        page = Fetcher.get(url, timeout=_HTTP_TIMEOUT, stealthy_headers=True)
        if page and page.status == 200:
            return page.html
    except Exception:
        pass
    try:
        from scrapling.defaults import StealthyFetcher

        page = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=_HTTP_TIMEOUT * 2)
        if page and page.status == 200:
            return page.html
    except Exception:
        pass
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    result = _float(value, math.nan)
    return None if math.isnan(result) else result
