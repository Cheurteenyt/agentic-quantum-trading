from __future__ import annotations

import json
import sqlite3
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from services.onchain.aster.dexscreener_enrichment_layer import (
    _as_float,
    _as_int,
    _clean_address,
    _market_metrics,
    _score,
)
from services.onchain.behavioral_evidence_bridge import (
    get_manipulation_detection_behavioral_score_pump_backtest_preview,
)
from services.onchain.core.paths import DB_PATH


DEXSCREENER_CHAIN_URL = "https://api.dexscreener.com/tokens/v1/{chain}"
DEXSCREENER_TOKENS_URL = "https://api.dexscreener.com/tokens/v1/{chain}/{tokens}"
COMMON_BSC_QUOTES = {
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB
    "0x55d398326f99059ff775485246999027b3197955",  # USDT
    "0xe9e7cea3dedca5984780bafc599bd69add087d56",  # BUSD
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
}


def _disabled() -> dict[str, Any]:
    return {
        "source_policy": "dexscreener_external_first_preview_only",
        "would_call_dexscreener": True,
        "would_scrape": False,
        "would_call_scrapling": False,
        "would_call_rpc": False,
        "would_persist_evidence": False,
        "would_apply_label_source": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "writes_performed": 0,
    }


def _http_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "CoreEquity/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"status": "ok", "url": url, "payload": payload}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"status": "not_found", "url": url, "http_status": 404}
        if exc.code == 429:
            return {"status": "rate_limited", "url": url, "http_status": 429}
        return {"status": "http_error", "url": url, "http_status": exc.code}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "request_failed", "url": url, "error": type(exc).__name__}


def _pairs_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        pairs = payload.get("pairs") or payload.get("data") or payload.get("tokens")
        if isinstance(pairs, list):
            return [row for row in pairs if isinstance(row, dict)]
    return []


def _known_pair_tokens(chain: str, limit: int) -> list[str]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "pair_tokens" not in tables:
            return []
        columns = {row[1] for row in conn.execute("PRAGMA table_info(pair_tokens)").fetchall()}
        if not {"chain", "token0", "token1"}.issubset(columns):
            return []
        rows = conn.execute(
            """
            SELECT lower(token0), lower(token1), MAX(COALESCE(observed_at, 0)) AS last_seen
            FROM pair_tokens
            WHERE lower(chain)=?
            GROUP BY lower(token0), lower(token1)
            ORDER BY last_seen DESC
            LIMIT 300
            """,
            (chain,),
        ).fetchall()
    finally:
        conn.close()
    tokens: list[str] = []
    seen: set[str] = set()
    for token0, token1, _last_seen in rows:
        for token in (_clean_address(token0), _clean_address(token1)):
            if not token or token in COMMON_BSC_QUOTES or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= limit:
                return tokens
    return tokens


def _behavioral_scores(chain: str) -> dict[str, dict[str, Any]]:
    preview = get_manipulation_detection_behavioral_score_pump_backtest_preview(
        chain=chain,
        limit=100,
        min_behavioral_score=1,
        dry_run=True,
    )
    scores: dict[str, dict[str, Any]] = {}
    for row in preview.get("candidate_backtests") or []:
        token = _clean_address(row.get("target_token"))
        if not token:
            continue
        score = _as_int(row.get("final_behavioral_score"))
        previous = scores.get(token, {})
        if score >= _as_int(previous.get("behavioral_score")):
            scores[token] = {
                "behavioral_score": score,
                "pool_address": _clean_address(row.get("pool_address")) or None,
                "token_symbol": row.get("target_symbol"),
                "quote_token": _clean_address(row.get("quote_token")) or None,
                "quote_symbol": row.get("quote_symbol"),
            }
    return scores


def _token_from_pair(pair: dict[str, Any]) -> tuple[str, str | None]:
    base = pair.get("baseToken") or {}
    token = _clean_address(base.get("address"))
    symbol = base.get("symbol")
    if token in COMMON_BSC_QUOTES:
        quote = pair.get("quoteToken") or {}
        token = _clean_address(quote.get("address"))
        symbol = quote.get("symbol")
    return token, symbol


def _discovery_row(pair: dict[str, Any], min_liquidity: float, min_ratio: float) -> dict[str, Any] | None:
    token, symbol = _token_from_pair(pair)
    if not token:
        return None
    metrics = _market_metrics(pair)
    liquidity = _as_float(metrics.get("liquidity_usd"))
    volume = _as_float(metrics.get("volume_24h_usd"))
    ratio = volume / liquidity if liquidity > 0 else 0.0
    if liquidity < min_liquidity or ratio < min_ratio:
        return None
    return {
        "chain": pair.get("chainId") or "bsc",
        "token_address": token,
        "token_symbol": symbol,
        "dex_pair_address": metrics.get("dex_pair_address"),
        "dex_id": metrics.get("dex_id"),
        **metrics,
        "volume_liquidity_ratio": round(ratio, 6),
    }


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "mean": None, "median": None}
    return {
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "mean": round(sum(values) / len(values), 6),
        "median": round(statistics.median(values), 6),
    }


def _ratio_distribution(values: list[float]) -> dict[str, int]:
    return {
        "lt_3": sum(1 for value in values if value < 3),
        "gte_3_to_lt_5": sum(1 for value in values if 3 <= value < 5),
        "gte_5_to_lt_10": sum(1 for value in values if 5 <= value < 10),
        "gte_10": sum(1 for value in values if value >= 10),
    }


def _watchlist_status(score: Any, composite: float, ratio: float) -> tuple[str, str | None]:
    if composite >= 70:
        return "suspicious", "composite_score_gte_70"
    if score is None and ratio >= 3.5:
        return "watchlist", "external_only_with_moderate_volume_ratio"
    return "normal", None


def _enrich_rows(rows: list[dict[str, Any]], chain: str) -> list[dict[str, Any]]:
    scores = _behavioral_scores(chain)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        token = _clean_address(row.get("token_address"))
        score_context = scores.get(token)
        ratio = _as_float(row.get("volume_liquidity_ratio"))
        if score_context:
            scoring = _score({"behavioral_score": score_context.get("behavioral_score")}, row)
            composite = _as_float(scoring.get("composite_score"))
            buy_sell_ratio = scoring.get("buy_sell_ratio")
            score = score_context.get("behavioral_score")
        else:
            composite = round(ratio * 15.0, 2)
            buys = _as_float(row.get("txns_24h_buys"))
            sells = _as_float(row.get("txns_24h_sells"))
            buy_sell_ratio = round(buys / max(1.0, sells), 6)
            score = None
        watchlist_status, watchlist_reason = _watchlist_status(score, composite, ratio)
        enriched.append(
            {
                **row,
                "behavioral_score": score,
                "local_behavioral_status": "found" if score_context else "not_found",
                "pool_address": (score_context or {}).get("pool_address"),
                "quote_token": (score_context or {}).get("quote_token"),
                "quote_symbol": (score_context or {}).get("quote_symbol"),
                "buy_sell_ratio": buy_sell_ratio,
                "composite_score": composite,
                "is_suspicious": bool(composite >= 70 or (score is None and ratio >= 5)),
                "watchlist_status": watchlist_status,
                "reason_for_watchlist": watchlist_reason,
            }
        )
    return enriched


def get_dexscreener_first_discovery_preview(
    chain: str | None = "bsc",
    limit: int = 30,
    min_liquidity_usd: float = 10_000,
    min_volume_liquidity_ratio: float = 3,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
    dry_run: bool = True,
) -> dict[str, Any]:
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 30), 30))
    safe_timeout = max(1, min(int(timeout_seconds or 10), 10))
    safe_delay = max(0, min(int(rate_limit_delay_ms or 300), 2_000))
    min_liquidity = max(0.0, float(min_liquidity_usd or 10_000))
    min_ratio = max(0.0, float(min_volume_liquidity_ratio or 3))
    disabled = _disabled()
    if not dry_run:
        return {"ok": False, "dry_run": False, "preview_status": "blocked", "blockers": ["dry_run_required"], "discovery_rows": [], **disabled}

    calls: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    chain_url = DEXSCREENER_CHAIN_URL.format(chain=clean_chain)
    chain_response = _http_json(chain_url, safe_timeout)
    calls.append({k: chain_response.get(k) for k in ("status", "url", "http_status", "error") if chain_response.get(k) is not None})
    for pair in _pairs_from_payload(chain_response.get("payload")):
        row = _discovery_row(pair, min_liquidity, min_ratio)
        token = _clean_address((row or {}).get("token_address"))
        if row and token not in seen_tokens:
            seen_tokens.add(token)
            candidates.append(row)
            if len(candidates) >= clean_limit:
                break

    fallback_tokens: list[str] = []
    if not candidates and chain_response.get("status") != "rate_limited":
        fallback_tokens = _known_pair_tokens(clean_chain, clean_limit)
        for index in range(0, len(fallback_tokens), 10):
            chunk = fallback_tokens[index : index + 10]
            if index:
                time.sleep(safe_delay / 1000)
            encoded = urllib.parse.quote(",".join(chunk), safe=",")
            url = DEXSCREENER_TOKENS_URL.format(chain=clean_chain, tokens=encoded)
            response = _http_json(url, safe_timeout)
            calls.append({k: response.get(k) for k in ("status", "url", "http_status", "error") if response.get(k) is not None})
            if response.get("status") == "rate_limited":
                break
            if response.get("status") != "ok":
                continue
            for pair in _pairs_from_payload(response.get("payload")):
                row = _discovery_row(pair, min_liquidity, min_ratio)
                token = _clean_address((row or {}).get("token_address"))
                if row and token not in seen_tokens:
                    seen_tokens.add(token)
                    candidates.append(row)
                    if len(candidates) >= clean_limit:
                        break
            if len(candidates) >= clean_limit:
                break

    enriched = _enrich_rows(candidates[:clean_limit], clean_chain)
    enriched.sort(key=lambda row: _as_float(row.get("composite_score")), reverse=True)
    scores = [_as_float(row.get("composite_score")) for row in enriched]
    ratios = [_as_float(row.get("volume_liquidity_ratio")) for row in enriched]
    status_counts = {
        status: sum(1 for call in calls if call.get("status") == status)
        for status in sorted({str(call.get("status") or "unknown") for call in calls})
    }
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready" if enriched else "blocked",
        "chain": clean_chain,
        "discovery_source": "dexscreener_chain_endpoint" if chain_response.get("status") == "ok" and not fallback_tokens else "local_pair_tokens_iterated_through_dexscreener",
        "chain_endpoint_status": chain_response.get("status"),
        "known_pair_tokens_checked": len(fallback_tokens),
        "http_calls_attempted": len(calls),
        "http_call_status_counts": status_counts,
        "partial_results": bool(status_counts.get("rate_limited")),
        "filters": {
            "max_tokens": clean_limit,
            "liquidity_usd_min": min_liquidity,
            "volume_liquidity_ratio_min": min_ratio,
            "timeout_seconds": safe_timeout,
            "rate_limit_delay_ms": safe_delay,
        },
        "stats": {
            "discovered_tokens": len(enriched),
            "suspicious_count": sum(1 for row in enriched if row.get("is_suspicious")),
            "watchlist_count": sum(1 for row in enriched if row.get("watchlist_status") == "watchlist"),
            "composite_score": _stats(scores),
            "volume_liquidity_ratio": _stats(ratios),
            "volume_liquidity_ratio_distribution": _ratio_distribution(ratios),
        },
        "top_10_by_composite_score": enriched[:10],
        "watchlist_candidates": sorted(
            [row for row in enriched if row.get("watchlist_status") == "watchlist"],
            key=lambda row: _as_float(row.get("volume_liquidity_ratio")),
            reverse=True,
        )[:5],
        "discovery_rows": enriched,
        "blockers": [] if enriched else ["no_dexscreener_candidates_passed_external_market_filters"],
        **disabled,
    }
