"""
Alpha Lab service.

This module is intentionally independent from the Arkham explorer layer. It
normalizes external alpha/proof sources, deduplicates events, and runs
counterfactual simulations without polluting entity or wallet labels.
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.alpha_simulation import (
    ManipulationEvent,
    ManipulationInput,
    ManipulationResult,
    PredictionCopyInput,
    PredictionCopyResult,
    PredictionTrade,
    simulate_manipulation_strategy as _simulate_manipulation_strategy,
    simulate_prediction_copy,
)
from services.alpha_risk_models import RiskFlag, SellabilityProbe, TokenRiskResult
from services.alpha_risk import analyze_token_risk as _analyze_token_risk
from services.alpha_sellability import probe_token_sellability


@dataclass(frozen=True)
class AlphaSource:
    id: str
    name: str
    category: str
    public_data: bool
    requires_api_key: bool
    useful_for: list[str]
    dedupe_hint: str
    docs_url: str
    status: str = "planned"


ALPHA_SOURCES: tuple[AlphaSource, ...] = (
    AlphaSource(
        id="polymarket",
        name="Polymarket",
        category="prediction_market",
        public_data=True,
        requires_api_key=False,
        useful_for=[
            "market discovery",
            "orderbook snapshots",
            "trade history",
            "wallet positions",
            "copy-trading backtests",
        ],
        dedupe_hint="market_id/token_id + user/wallet + tx/order/trade timestamp",
        docs_url="https://docs.polymarket.com/market-data/overview",
    ),
    AlphaSource(
        id="kalshi",
        name="Kalshi",
        category="prediction_market",
        public_data=True,
        requires_api_key=False,
        useful_for=[
            "regulated prediction markets",
            "market prices",
            "historical trades",
            "cross-venue probability comparison",
        ],
        dedupe_hint="ticker + trade_id/timestamp + side + price",
        docs_url="https://docs.kalshi.com/api-reference/market/get-markets",
    ),
    AlphaSource(
        id="zerion",
        name="Zerion API",
        category="wallet_intel",
        public_data=False,
        requires_api_key=True,
        useful_for=[
            "wallet portfolio",
            "transactions",
            "DeFi positions",
            "wallet PnL",
            "multi-chain enrichment",
        ],
        dedupe_hint="chain + tx_hash + operation id",
        docs_url="https://developers.zerion.io/api-reference/wallets/get-wallet-portfolio",
    ),
    AlphaSource(
        id="cielo",
        name="Cielo API",
        category="wallet_intel",
        public_data=False,
        requires_api_key=True,
        useful_for=[
            "wallet feed",
            "token PnL",
            "wallet tags",
            "related wallets",
            "new trade detection",
        ],
        dedupe_hint="chain + tx_hash + index + wallet",
        docs_url="https://developer.cielo.finance/reference/getfeed",
    ),
    AlphaSource(
        id="arkham_local",
        name="Hermes Arkham Mirror",
        category="entity_intel",
        public_data=False,
        requires_api_key=False,
        useful_for=[
            "entity labels",
            "counterparties",
            "exchange/fund attribution",
            "transfer surface",
        ],
        dedupe_hint="chain + tx_hash + log_index + normalized entity label",
        docs_url="local:/api/arkham",
        status="active",
    ),
    AlphaSource(
        id="scrapling_arkham",
        name="Scrapling Arkham Probe",
        category="public_page_probe",
        public_data=True,
        requires_api_key=False,
        useful_for=[
            "public Arkham page snapshots",
            "missing UI-only fields",
            "XHR endpoint discovery",
            "visual/data parity checks",
        ],
        dedupe_hint="target kind + slug + captured XHR category + normalized object key",
        docs_url="local:/api/arkham/scrapling/probe",
        status="active",
    ),
)


def get_alpha_sources() -> dict[str, Any]:
    return {
        "sources": [asdict(source) for source in ALPHA_SOURCES],
        "rules": {
            "principle": "Use official APIs first; scrape only public pages when no API exists and never mix raw source data into Arkham labels.",
            "dedupe_levels": [
                "source event key",
                "strong semantic key",
                "weak similarity fingerprint",
                "human-review queue for conflicts",
            ],
            "merge_policy": "Never overwrite a higher-confidence label or PnL value with a weaker source.",
        },
    }


def get_alpha_strategy() -> dict[str, Any]:
    return {
        "product": "Counterfactual Alpha Engine",
        "goal": "Show whether a wallet, market participant, or manipulation signal would have been profitable if copied with realistic delay, slippage, and liquidity limits.",
        "layers": [
            {
                "name": "Proof intake",
                "purpose": "Collect market trades, wallet transactions, tags, related wallets, and token events as immutable source proofs.",
            },
            {
                "name": "Dedupe and identity graph",
                "purpose": "Merge only by strong keys, then connect wallets/entities by evidence instead of assumptions.",
            },
            {
                "name": "Detection",
                "purpose": "Rank manipulation or copy opportunities by multi-source evidence, freshness, repeatability, liquidity, and sellability.",
            },
            {
                "name": "Profit integrity guard",
                "purpose": "Reject fake profits caused by frozen tokens, honeypots, blacklist functions, high sell tax, missing sell proofs, or insufficient liquidity.",
            },
            {
                "name": "Counterfactual simulation",
                "purpose": "Backtest what 100 EUR/USD would have done after detection with configured delay, slippage, fees, and exit rules.",
            },
            {
                "name": "Operator UI",
                "purpose": "No notification spam: active dashboard first, alert only when a strict proof threshold is crossed.",
            },
        ],
        "first_implementation_path": [
            "Polymarket market/trade adapter",
            "Cielo wallet feed + PnL adapter when key is available",
            "Zerion portfolio enrichment when key is available",
            "Kalshi probability comparator",
            "Token risk guard: freeze/blacklist/honeypot/tax/liquidity checks before any PnL is trusted",
            "Entity graph and simulation UI",
        ],
    }


def dedupe_alpha_events(raw_events: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}

    for raw in raw_events:
        event = normalize_alpha_event(raw)
        normalized.append(event)
        key = event["semantic_key"]
        if key not in by_key:
            by_key[key] = event
            continue

        existing = by_key[key]
        existing["duplicate_count"] += 1
        existing_sources = set(existing.get("sources", []))
        existing_sources.add(event["source"])
        existing["sources"] = sorted(existing_sources)
        existing["raw_refs"].append(event["source_event_id"])
        existing["confidence"] = max(existing["confidence"], event["confidence"])
        existing["last_seen_at"] = _utc_now()

    unique_events = list(by_key.values())
    return {
        "input_count": len(raw_events),
        "unique_count": len(unique_events),
        "duplicate_count": len(raw_events) - len(unique_events),
        "duplicate_ratio": _safe_ratio(len(raw_events) - len(unique_events), len(raw_events)),
        "events": unique_events,
        "sample_normalized": normalized[:5],
    }


def normalize_alpha_event(raw: dict[str, Any]) -> dict[str, Any]:
    source = str(raw.get("source") or raw.get("provider") or "unknown").lower()
    event_type = str(raw.get("type") or raw.get("event_type") or raw.get("tx_type") or "event").lower()
    source_event_id = _pick_first(
        raw,
        [
            "id",
            "event_id",
            "trade_id",
            "order_id",
            "tx_hash",
            "transaction_hash",
            "hash",
        ],
    )
    source_event_id = str(source_event_id or _hash_payload(raw))

    semantic_key = _semantic_key(source, event_type, raw)
    return {
        "source": source,
        "sources": [source],
        "event_type": event_type,
        "source_event_id": source_event_id,
        "tx_hash": raw.get("tx_hash") or raw.get("transaction_hash") or raw.get("hash"),
        "semantic_key": semantic_key,
        "fingerprint": _hash_payload(raw),
        "timestamp": _normalize_ts(raw.get("timestamp") or raw.get("time") or raw.get("created_at")),
        "actor": raw.get("actor") or raw.get("user") or raw.get("wallet") or raw.get("address"),
        "wallet_label": raw.get("wallet_label") or raw.get("label"),
        "asset": raw.get("asset") or raw.get("token") or raw.get("symbol") or raw.get("ticker"),
        "chain": raw.get("chain") or raw.get("network"),
        "from": raw.get("from"),
        "to": raw.get("to"),
        "dex": raw.get("dex"),
        "amount_usd": _float_or_none(raw.get("amount_usd") or raw.get("value_usd") or raw.get("usd")),
        "first_interaction": raw.get("first_interaction") if raw.get("first_interaction") is not None else raw.get("new_trade"),
        "confidence": _confidence(raw),
        "duplicate_count": 1,
        "raw_refs": [source_event_id],
        "first_seen_at": _utc_now(),
        "last_seen_at": _utc_now(),
    }


def simulate_manipulation_strategy(payload: dict[str, Any]) -> dict[str, Any]:
    return _simulate_manipulation_strategy(payload, risk_analyzer=analyze_token_risk)


def analyze_token_risk(payload: dict[str, Any]) -> dict[str, Any]:
    return _analyze_token_risk(payload, sellability_probe=probe_token_sellability)


def _dedupe_risk_flags(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one risk flag per code so repeated probes do not inflate risk.

    When the same code appears multiple times, keep the strongest severity and
    the highest point value. Details are merged so we do not lose evidence.
    """
    severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    deduped: dict[str, dict[str, Any]] = {}

    for item in flags:
        code = str(item.get("code") or "unknown")
        current = dict(item)
        if code not in deduped:
            deduped[code] = current
            continue

        existing = deduped[code]
        existing_rank = severity_rank.get(str(existing.get("severity", "")).lower(), -1)
        current_rank = severity_rank.get(str(current.get("severity", "")).lower(), -1)

        if current_rank > existing_rank:
            existing["severity"] = current.get("severity", existing.get("severity"))
        existing["points"] = max(int(existing.get("points", 0)), int(current.get("points", 0)))

        existing_detail = str(existing.get("detail") or "")
        current_detail = str(current.get("detail") or "")
        if current_detail and current_detail not in existing_detail:
            existing["detail"] = f"{existing_detail} | {current_detail}" if existing_detail else current_detail

    return list(deduped.values())


def _semantic_key(source: str, event_type: str, raw: dict[str, Any]) -> str:
    chain = str(raw.get("chain") or raw.get("network") or "").lower()
    tx_hash = raw.get("tx_hash") or raw.get("transaction_hash") or raw.get("hash")
    log_index = raw.get("log_index") if raw.get("log_index") is not None else raw.get("index")
    if tx_hash:
        return f"tx:{chain}:{str(tx_hash).lower()}:{log_index or 0}"

    market_id = raw.get("market_id") or raw.get("condition_id") or raw.get("ticker")
    actor = raw.get("actor") or raw.get("user") or raw.get("wallet") or raw.get("address")
    side = raw.get("side") or raw.get("action")
    price = raw.get("price") or raw.get("fill_price")
    size = raw.get("size") or raw.get("size_usd") or raw.get("amount")
    timestamp = _normalize_ts(raw.get("timestamp") or raw.get("time") or raw.get("created_at"))
    if market_id and (actor or side or price):
        compact = "|".join(
            str(part).lower()
            for part in [source, event_type, market_id, actor, side, price, size, timestamp]
        )
        return f"market:{sha256(compact.encode('utf-8')).hexdigest()[:24]}"

    return f"payload:{_hash_payload(raw)}"


def _pick_first(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _hash_payload(raw: dict[str, Any]) -> str:
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _normalize_ts(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        # Accept both seconds and milliseconds.
        ts = float(value) / 1000.0 if float(value) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _confidence(raw: dict[str, Any]) -> float:
    if "confidence" in raw:
        return min(1.0, max(0.0, _float(raw.get("confidence"), 0.5)))

    score = 0.35
    if raw.get("tx_hash") or raw.get("transaction_hash"):
        score += 0.35
    if raw.get("market_id") or raw.get("ticker"):
        score += 0.15
    if raw.get("wallet") or raw.get("address") or raw.get("actor"):
        score += 0.1
    if raw.get("price") or raw.get("amount") or raw.get("size_usd"):
        score += 0.05
    return min(1.0, round(score, 3))


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


def _percent(value: Any) -> float | None:
    result = _float_or_none(value)
    if result is None:
        return None
    if 0 < result <= 1:
        return result * 100
    return result


def _boolish(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "enabled", "active"}:
        return True
    if text in {"false", "no", "n", "0", "disabled", "inactive"}:
        return False
    return None


def _safe_ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def _bounded_probability(value: float) -> float:
    return min(0.99, max(0.0, value))


def _apply_probability_cost(price: float, side: str, slippage_bps: float, fee_bps: float) -> float:
    cost = (slippage_bps + fee_bps) / 10_000.0
    if side in {"sell", "short"}:
        return max(0.01, min(0.99, price - cost))
    return max(0.01, min(0.99, price + cost))

