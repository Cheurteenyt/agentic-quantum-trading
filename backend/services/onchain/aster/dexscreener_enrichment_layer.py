from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from services.onchain.behavioral_evidence_bridge import (
    get_manipulation_detection_behavioral_score_pump_backtest_preview,
)


DEXSCREENER_URL = "https://api.dexscreener.com/tokens/v1/{chain}/{token}"
def _clean_address(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if clean.startswith("0x") and len(clean) == 42:
        return clean
    return ""


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _behavioral_candidates(chain: str, limit: int, min_behavioral_score: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    preview = get_manipulation_detection_behavioral_score_pump_backtest_preview(
        chain=chain,
        limit=limit,
        min_behavioral_score=min_behavioral_score,
        dry_run=True,
    )
    for row in preview.get("candidate_backtests") or []:
        score = _as_int(row.get("final_behavioral_score"))
        if score < min_behavioral_score:
            continue
        candidates.append(
            {
                "chain": chain,
                "pool_address": _clean_address(row.get("pool_address")) or None,
                "token_address": _clean_address(row.get("target_token")) or None,
                "token_symbol": row.get("target_symbol"),
                "quote_token": _clean_address(row.get("quote_token")) or None,
                "quote_symbol": row.get("quote_symbol"),
                "behavioral_score": score,
                "token_status": "resolved" if _clean_address(row.get("target_token")) else "token_missing",
            }
        )
    return candidates[:limit]


def _dexscreener_token_request(chain: str, token: str, timeout_seconds: int) -> dict[str, Any]:
    url = DEXSCREENER_URL.format(chain=chain, token=token)
    req = urllib.request.Request(url, headers={"User-Agent": "CoreEquity/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
        return {"status": "ok", "url": url, "payload": payload}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"status": "not_found", "url": url, "http_status": 404}
        if exc.code == 429:
            return {"status": "rate_limited", "url": url, "http_status": 429}
        return {"status": "http_error", "url": url, "http_status": exc.code}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "request_failed", "url": url, "error": type(exc).__name__}


def _select_pair(payload: Any, pool: str) -> dict[str, Any] | None:
    pairs = payload if isinstance(payload, list) else (payload or {}).get("pairs") if isinstance(payload, dict) else []
    if not isinstance(pairs, list):
        return None
    clean_pool = _clean_address(pool)
    for pair in pairs:
        if isinstance(pair, dict) and _clean_address(pair.get("pairAddress")) == clean_pool:
            return pair
    ranked = [pair for pair in pairs if isinstance(pair, dict)]
    ranked.sort(key=lambda row: _as_float((row.get("liquidity") or {}).get("usd")), reverse=True)
    return ranked[0] if ranked else None


def _market_metrics(pair: dict[str, Any] | None) -> dict[str, Any]:
    if not pair:
        return {
            "market_status": "pair_not_found",
            "volume_24h_usd": 0.0,
            "liquidity_usd": 0.0,
            "txns_24h_buys": 0,
            "txns_24h_sells": 0,
            "price_change_24h_pct": 0.0,
        }
    txns = ((pair.get("txns") or {}).get("h24") or {})
    return {
        "market_status": "found",
        "dex_pair_address": _clean_address(pair.get("pairAddress")) or None,
        "dex_id": pair.get("dexId"),
        "volume_24h_usd": _as_float((pair.get("volume") or {}).get("h24")),
        "liquidity_usd": _as_float((pair.get("liquidity") or {}).get("usd")),
        "txns_24h_buys": _as_int(txns.get("buys")),
        "txns_24h_sells": _as_int(txns.get("sells")),
        "price_change_24h_pct": _as_float((pair.get("priceChange") or {}).get("h24")),
    }


def _score(candidate: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    behavioral = _as_float(candidate.get("behavioral_score"))
    volume = _as_float(metrics.get("volume_24h_usd"))
    liquidity = _as_float(metrics.get("liquidity_usd"))
    buys = _as_float(metrics.get("txns_24h_buys"))
    sells = _as_float(metrics.get("txns_24h_sells"))
    volume_liquidity_ratio = volume / liquidity if liquidity > 0 else 0.0
    buy_sell_ratio = buys / max(1.0, sells)
    composite = (behavioral * 0.4) + min(30.0, volume_liquidity_ratio * 5.0) + min(30.0, buy_sell_ratio * 10.0)
    return {
        "volume_liquidity_ratio": round(volume_liquidity_ratio, 6),
        "buy_sell_ratio": round(buy_sell_ratio, 6),
        "composite_score": round(composite, 2),
        "is_suspicious": bool(composite >= 70 and volume_liquidity_ratio >= 3),
    }


def get_dexscreener_enrichment_preview(
    chain: str | None = "bsc",
    limit: int = 20,
    min_behavioral_score: int = 60,
    timeout_seconds: int = 10,
    dry_run: bool = True,
) -> dict[str, Any]:
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 20), 20))
    safe_min_score = max(1, min(int(min_behavioral_score or 60), 100))
    safe_timeout = max(1, min(int(timeout_seconds or 10), 10))
    disabled = {
        "source_policy": "dexscreener_single_source_preview_only",
        "would_call_dexscreener": True,
        "would_scrape": False,
        "would_call_scrapling": False,
        "would_call_rpc": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "writes_performed": 0,
    }
    if not dry_run:
        return {"ok": False, "dry_run": False, "preview_status": "blocked", "blockers": ["dry_run_required"], "enrichment_rows": [], **disabled}
    candidates = _behavioral_candidates(clean_chain, clean_limit, safe_min_score)
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        token = _clean_address(candidate.get("token_address"))
        if not token:
            rows.append({**candidate, "dexscreener_status": "token_missing", "composite_score": 0, "is_suspicious": False})
            continue
        response = _dexscreener_token_request(clean_chain, token, safe_timeout)
        pair = _select_pair(response.get("payload"), candidate.get("pool_address"))
        metrics = _market_metrics(pair) if response.get("status") == "ok" else _market_metrics(None)
        rows.append({**candidate, "dexscreener_status": response.get("status"), "request_url": response.get("url"), **metrics, **_score(candidate, metrics)})
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready" if rows else "blocked",
        "chain": clean_chain,
        "min_behavioral_score": safe_min_score,
        "candidates_checked": len(candidates),
        "http_calls_attempted": sum(1 for row in rows if row.get("token_address")),
        "suspicious_count": sum(1 for row in rows if row.get("is_suspicious")),
        "enrichment_rows": rows,
        "blockers": [] if rows else ["no_local_behavioral_candidates_above_threshold"],
        **disabled,
    }
