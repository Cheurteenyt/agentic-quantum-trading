"""
Alpha wallet intelligence adapters.

These adapters are deliberately conservative: if an API key is missing or an
upstream response is ambiguous, the output says so instead of fabricating PnL.
"""

from __future__ import annotations

import base64
import json
import os
import re   # PR-174 : utilisé ligne ~1211, jamais importé
import time
import urllib.parse
import urllib.request
from typing import Any

from services.alpha_lab import analyze_token_risk, dedupe_alpha_events


CIELO_BASE_URL = "https://feed-api.cielo.finance/api"
ZERION_BASE_URL = "https://api.zerion.io/v1"
USER_AGENT = "HermesAlphaLab/0.1"
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_CACHE_TTL_SECONDS = 45

_CACHE: dict[str, tuple[float, Any]] = {}


def get_wallet_provider_status() -> dict[str, Any]:
    key = _cielo_key_validated()
    return {
        "providers": [
            {
                "id": "cielo",
                "name": "Cielo Wallet API",
                "configured": bool(key),
                "status": "ready" if key else ("invalid_key" if _cielo_key() else "missing_key"),
                "auth": "X-API-KEY",
                "capabilities": ["feed", "wallet tags", "token pnl", "portfolio", "fresh trades"],
            },
            {
                "id": "zerion",
                "name": "Zerion API",
                "configured": bool(_zerion_auth_header()),
                "status": "ready" if _zerion_auth_header() else "missing_key",
                "auth": "Authorization: Basic",
                "capabilities": ["wallet pnl", "portfolio", "positions", "transactions"],
            },
            {
                "id": "scrapling_arkham",
                "name": "Scrapling Arkham Probe",
                "configured": True,
                "status": "active",
                "auth": "none",
                "capabilities": ["public Arkham snapshots", "label parity", "transfer surface"],
            },
        ],
        "required_env": ["CIELO_API_KEY", "ZERION_API_KEY"],
        "policy": "Wallet PnL is only trusted when realized sells or provider PnL evidence exists.",
    }


def get_wallet_intelligence(
    wallet: str,
    *,
    source: str = "all",
    timeframe: str = "30d",
    limit: int = 25,
    chains: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    started = time.time()
    wallet = (wallet or "").strip()
    source = (source or "all").lower()
    limit = max(1, min(int(limit or 25), 100))

    if not wallet:
        return {"ok": False, "error": "wallet is required", "providers": [], "summary": {}, "events": [], "pnl": []}

    providers: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    pnl: list[dict[str, Any]] = []

    if source in {"all", "cielo"}:
        if _cielo_key_validated():
            cielo = _safe_provider("cielo", lambda: _cielo_wallet_intel(wallet, timeframe=timeframe, limit=limit, chains=chains, use_cache=use_cache))
            providers.append(cielo["status"])
            events.extend(cielo.get("events", []))
            pnl.extend(cielo.get("pnl", []))
        else:
            providers.append({
                "provider": "cielo",
                "ok": False,
                "status": "invalid_key" if _cielo_key() else "missing_key",
                "latency_ms": 0,
                "error": "CIELO_API_KEY rejected by upstream (403)" if _cielo_key() else "CIELO_API_KEY not set",
            })

    if source in {"all", "zerion"}:
        zerion = _safe_provider("zerion", lambda: _zerion_wallet_intel(wallet, use_cache=use_cache))
        providers.append(zerion["status"])
        pnl.extend(zerion.get("pnl", []))

    deduped = dedupe_alpha_events(events)
    unique_events = deduped.get("events", [])
    summary = _summarize_wallet(wallet, unique_events, pnl)

    return {
        "ok": any(provider.get("ok") for provider in providers),
        "wallet": wallet,
        "source": source,
        "timeframe": timeframe,
        "providers": providers,
        "summary": summary,
        "events": unique_events[:limit],
        "pnl": pnl[:50],
        "dedupe": {
            "input_count": deduped.get("input_count", 0),
            "unique_count": deduped.get("unique_count", 0),
            "duplicate_count": deduped.get("duplicate_count", 0),
            "duplicate_ratio": deduped.get("duplicate_ratio", 0),
        },
        "latency_ms": round((time.time() - started) * 1000, 2),
    }


def get_wallet_feed(
    wallet: str | None = None,
    *,
    limit: int = 25,
    chains: str | None = None,
    tx_types: str | None = "swap",
    tokens: str | None = None,
    min_usd: float | None = None,
    new_trades: bool | None = None,
    include_market_cap: bool = False,
    use_cache: bool = True,
) -> dict[str, Any]:
    if not _cielo_key_validated():
        return _missing_key_response("cielo", "CIELO_API_KEY")

    params: dict[str, str] = {"limit": str(max(1, min(int(limit or 25), 100)))}
    if wallet:
        params["wallet"] = wallet
    if chains:
        params["chains"] = chains
    if tx_types:
        params["txTypes"] = tx_types
    if tokens:
        params["tokens"] = tokens
    if min_usd is not None:
        params["minUSD"] = str(min_usd)
    if new_trades is not None:
        params["newTrades"] = "true" if new_trades else "false"
    if include_market_cap:
        params["includeMarketCap"] = "true"

    payload = _request_json(
        f"{CIELO_BASE_URL}/v1/feed?{urllib.parse.urlencode(params)}",
        headers={"X-API-KEY": _cielo_key() or ""},
        use_cache=use_cache,
    )
    rows = _extract_items(payload)
    events = [_normalize_cielo_event(row) for row in rows if isinstance(row, dict)]
    deduped = dedupe_alpha_events(events)
    return {
        "ok": True,
        "provider": "cielo",
        "count": len(events),
        "events": deduped.get("events", []),
        "dedupe": {
            "input_count": deduped.get("input_count", 0),
            "unique_count": deduped.get("unique_count", 0),
            "duplicate_count": deduped.get("duplicate_count", 0),
        },
        "raw_status": payload.get("status") if isinstance(payload, dict) else None,
    }


def get_wallet_discovery(
    *,
    limit: int = 25,
    feed_limit: int = 50,
    chains: str | None = None,
    tx_types: str | None = "swap",
    tokens: str | None = None,
    min_usd: float | None = 1000,
    new_trades: bool | None = True,
    use_cache: bool = True,
) -> dict[str, Any]:
    started = time.time()
    feed_limit = max(1, min(int(feed_limit or 50), 100))
    limit = max(1, min(int(limit or 25), 100))
    feed = get_wallet_feed(
        None,
        limit=feed_limit,
        chains=chains,
        tx_types=tx_types,
        tokens=tokens,
        min_usd=min_usd,
        new_trades=new_trades,
        include_market_cap=False,
        use_cache=use_cache,
    )
    events = feed.get("events", [])
    wallets: dict[str, dict[str, Any]] = {}

    for event in events:
        wallet = str(event.get("actor") or event.get("wallet") or "").strip()
        if not wallet:
            continue
        row = wallets.setdefault(wallet, {
            "wallet": wallet,
            "label": event.get("wallet_label"),
            "events": 0,
            "swaps": 0,
            "chains": set(),
            "assets": set(),
            "flow_usd": 0.0,
            "first_interactions": 0,
            "last_seen": None,
            "latest_asset": None,
            "latest_tx": None,
            "latest_chain": None,
            "score": 0.0,
            "copy_status": "needs_pnl_probe",
        })
        row["events"] += 1
        if str(event.get("event_type")).lower() == "swap":
            row["swaps"] += 1
        if event.get("chain"):
            row["chains"].add(str(event["chain"]))
        if event.get("asset"):
            row["assets"].add(str(event["asset"]))
            row["latest_asset"] = event["asset"]
        row["flow_usd"] += _first_number(event.get("amount_usd")) or 0.0
        if event.get("first_interaction") is True:
            row["first_interactions"] += 1
        if event.get("timestamp") and (not row["last_seen"] or str(event["timestamp"]) > str(row["last_seen"])):
            row["last_seen"] = event["timestamp"]
            row["latest_tx"] = event.get("source_event_id")
            row["latest_chain"] = event.get("chain")

    candidates = []
    for row in wallets.values():
        candidate_chains = sorted(row["chains"])
        assets = sorted(row["assets"])
        flow = float(row["flow_usd"])
        score = (
            min(45.0, flow / 10_000.0)
            + row["events"] * 4
            + row["first_interactions"] * 12
            + len(assets) * 3
            + len(candidate_chains) * 2
        )
        candidates.append({
            "wallet": row["wallet"],
            "label": row["label"],
            "score": round(score, 3),
            "events": row["events"],
            "swaps": row["swaps"],
            "chains": candidate_chains,
            "assets": assets,
            "flow_usd": round(flow, 4),
            "first_interactions": row["first_interactions"],
            "last_seen": row["last_seen"],
            "latest_asset": row["latest_asset"],
            "latest_tx": row["latest_tx"],
            "latest_chain": row["latest_chain"],
            "copy_status": row["copy_status"],
            "next_step": "Run wallet intelligence before any copy/backtest decision.",
        })

    candidates.sort(key=lambda item: (item["score"], item["flow_usd"], item["events"]), reverse=True)
    return {
        "ok": bool(feed.get("ok")),
        "provider": "cielo",
        "count": len(candidates[:limit]),
        "candidates": candidates[:limit],
        "feed": {
            "events": len(events),
            "dedupe": feed.get("dedupe", {}),
            "min_usd": min_usd,
            "new_trades": new_trades,
            "tx_types": tx_types,
            "chains": chains,
        },
        "latency_ms": round((time.time() - started) * 1000, 2),
        "note": "Discovery ranks wallets from recent feed events only. PnL and sellability checks must run before copy simulation.",
    }


def probe_wallet_candidate(
    wallet: str,
    *,
    source: str = "all",
    timeframe: str = "30d",
    limit: int = 25,
    chains: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    started = time.time()
    intel = get_wallet_intelligence(
        wallet,
        source=source,
        timeframe=timeframe,
        limit=limit,
        chains=chains,
        use_cache=use_cache,
    )
    summary = intel.get("summary", {}) if isinstance(intel.get("summary"), dict) else {}
    pnl_summary = summary.get("pnl", {}) if isinstance(summary.get("pnl"), dict) else {}
    providers = intel.get("providers", []) if isinstance(intel.get("providers"), list) else []
    ok_providers = [provider for provider in providers if provider.get("ok")]
    unstable_providers = [
        f"{provider.get('provider')}: {provider.get('error') or provider.get('status')}"
        for provider in providers
        if not provider.get("ok")
    ]
    pnl_rows = [row for row in intel.get("pnl", []) if isinstance(row, dict)]
    blocked_rows = [row for row in pnl_rows if row.get("block_trade")]
    suspicious_rows = [
        row for row in pnl_rows
        if row.get("profit_integrity") in {"not_trustworthy", "unrealized_or_unproven", "provider_unavailable"}
    ]
    events = [event for event in intel.get("events", []) if isinstance(event, dict)]
    asset_focus = _summarize_asset_focus(events)
    suspicious_focus = [item for item in asset_focus if _looks_suspicious_asset(item.get("asset"))]

    observed_flow = _first_number(summary.get("observed_flow_usd")) or 0.0
    trusted_realized = _first_number(pnl_summary.get("trusted_realized_usd")) or 0.0
    total_pnl = _first_number(pnl_summary.get("total_pnl_usd")) or 0.0
    first_interactions = int(summary.get("first_interactions") or 0)
    event_count = int(summary.get("events") or 0)
    swap_count = int(summary.get("swaps") or 0)

    status = "insufficient_data"
    status_label = "Insufficient Data"
    confidence = "low"
    reasons: list[str] = []
    requirements: list[str] = []

    if not ok_providers:
        reasons.append("No provider returned usable wallet data yet.")
    elif blocked_rows:
        status = "blocked"
        status_label = "Blocked"
        confidence = "high"
        reasons.append("At least one token row is blocked by the fake-profit or sellability guard.")
    elif suspicious_rows or suspicious_focus:
        status = "review"
        status_label = "Needs Proof"
        confidence = "low"
        reasons.append("Wallet has suspicious or incomplete profit evidence, so copy mode stays disabled.")
    elif trusted_realized > 0 and observed_flow > 0 and swap_count >= 3:
        status = "candidate"
        status_label = "Copy Candidate"
        confidence = "high" if len(ok_providers) >= 2 else "medium"
        reasons.append("Trusted realized PnL exists and recent wallet flow is large enough to score.")
    elif event_count >= 5 and first_interactions >= 2:
        status = "watch"
        status_label = "Watchlist"
        confidence = "medium"
        reasons.append("Fresh trade activity is visible, but realized proof is still limited.")
    elif suspicious_rows or total_pnl > 0:
        status = "review"
        status_label = "Needs Review"
        confidence = "low"
        reasons.append("PnL exists, but it is still untrusted or incomplete.")
    else:
        reasons.append("Not enough realized wallet evidence for a copy verdict.")

    if first_interactions > 0:
        reasons.append(f"{first_interactions} first-interaction trades detected in the recent window.")
    if asset_focus:
        reasons.append(f"Recent focus: {', '.join(item['asset'] for item in asset_focus[:3])}.")
    if unstable_providers:
        reasons.append(f"Provider instability: {', '.join(unstable_providers[:2])}.")

    if blocked_rows:
        requirements.append("Do not enable copy automation until blocked assets are cleared by sell proofs and liquidity checks.")
    if trusted_realized <= 0:
        requirements.append("Need trusted realized PnL before any copy automation can be considered.")
    if suspicious_rows:
        requirements.append("Need token-level sell proofs on suspicious PnL rows.")
    if suspicious_focus:
        requirements.append("Investigate suspicious traded assets before using this wallet as a copy signal.")
    if len(ok_providers) < len(providers):
        requirements.append("Retry when unstable providers recover to reduce blind spots.")
    if first_interactions > 0:
        requirements.append("Need repeatability across multiple sessions, not just one burst of fresh trades.")

    copy_preview = _build_wallet_copy_preview(
        status=status,
        observed_flow=observed_flow,
        trusted_realized=trusted_realized,
        first_interactions=first_interactions,
        provider_count=len(ok_providers),
        capital=100.0,
    )
    worst_risk_score = max((_first_number(row.get("risk_score")) or 0.0 for row in pnl_rows), default=0.0)
    suspicious_assets = sorted({
        str(row.get("token"))
        for row in blocked_rows + suspicious_rows
        if row.get("token")
    })

    return {
        "ok": bool(intel.get("ok")),
        "wallet": wallet,
        "status": status,
        "status_label": status_label,
        "confidence": confidence,
        "reasons": reasons[:5],
        "requirements": requirements[:5],
        "provider_health": {
            "ok": len(ok_providers),
            "total": len(providers),
            "unstable": unstable_providers[:5],
        },
        "risk_summary": {
            "blocked_rows": len(blocked_rows),
            "untrusted_rows": int(pnl_summary.get("untrusted_rows") or len(suspicious_rows)),
            "worst_risk_score": round(worst_risk_score, 2),
            "suspicious_assets": sorted(set(suspicious_assets + [str(item.get("asset")) for item in suspicious_focus]))[:8],
        },
        "asset_focus": asset_focus[:8],
        "copy_preview": copy_preview,
        "intel": intel,
        "latency_ms": round((time.time() - started) * 1000, 2),
        "note": "Copy preview is a conservative proxy from trusted realized PnL versus observed flow. It is not a fill-accurate backtest.",
    }


def get_wallet_surface(
    wallet: str,
    *,
    limit: int = 40,
    chains: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    started = time.time()
    wallet = (wallet or "").strip()
    if not wallet:
        return {"ok": False, "error": "wallet is required", "wallet": wallet, "summary": {}, "counterparties": [], "venues": [], "activity": []}

    feed = get_wallet_feed(
        wallet,
        limit=max(5, min(int(limit or 40), 100)),
        chains=chains,
        tx_types="swap,transfer",
        use_cache=use_cache,
    )
    events = [event for event in feed.get("events", []) if isinstance(event, dict)]
    wallet_lower = wallet.lower()

    summary = {
        "events": len(events),
        "swaps": 0,
        "transfers": 0,
        "inflow_usd": 0.0,
        "outflow_usd": 0.0,
        "swap_usd": 0.0,
        "net_transfer_usd": 0.0,
        "counterparties": 0,
        "venues": 0,
    }
    counterparties: dict[str, dict[str, Any]] = {}
    venues: dict[str, dict[str, Any]] = {}
    activity: list[dict[str, Any]] = []

    def touch_counterparty(
        *,
        key: str,
        label: str,
        address: str | None,
        chain: str | None,
        direction: str,
        amount_usd: float,
        asset: str | None,
        tx_hash: str | None,
        timestamp: str | None,
        dex: str | None = None,
        kind: str = "address",
    ) -> None:
        row = counterparties.setdefault(key, {
            "key": key,
            "label": label,
            "address": address,
            "kind": kind,
            "chains": set(),
            "assets": set(),
            "events": 0,
            "inflow_usd": 0.0,
            "outflow_usd": 0.0,
            "swap_usd": 0.0,
            "latest_tx": None,
            "latest_chain": None,
            "last_seen": None,
            "dex": dex,
        })
        row["events"] += 1
        if chain:
            row["chains"].add(str(chain))
        if asset:
            row["assets"].add(str(asset))
        if direction == "inflow":
            row["inflow_usd"] += amount_usd
        elif direction == "outflow":
            row["outflow_usd"] += amount_usd
        elif direction == "swap":
            row["swap_usd"] += amount_usd
        if timestamp and (not row["last_seen"] or str(timestamp) > str(row["last_seen"])):
            row["last_seen"] = timestamp
            row["latest_tx"] = tx_hash
            row["latest_chain"] = chain

    for event in events:
        event_type = str(event.get("event_type") or "").lower()
        chain = str(event.get("chain") or "")
        amount_usd = _first_number(event.get("amount_usd")) or 0.0
        asset = str(event.get("asset") or "") or None
        tx_hash = str(event.get("tx_hash") or event.get("source_event_id") or "") or None
        timestamp = str(event.get("timestamp") or "") or None
        dex = str(event.get("dex") or "") or None
        from_addr = str(event.get("from") or "") or None
        to_addr = str(event.get("to") or "") or None

        direction = "unknown"
        counterparty_label = None
        counterparty_address = None
        counterparty_kind = "address"

        if event_type == "swap":
            summary["swaps"] += 1
            summary["swap_usd"] += amount_usd
            venue_name = dex or "unknown venue"
            venue_key = f"venue:{venue_name.lower()}"
            venue = venues.setdefault(venue_key, {
                "name": venue_name,
                "events": 0,
                "amount_usd": 0.0,
                "chains": set(),
                "assets": set(),
                "latest_tx": None,
                "latest_chain": None,
                "last_seen": None,
            })
            venue["events"] += 1
            venue["amount_usd"] += amount_usd
            if chain:
                venue["chains"].add(chain)
            if asset:
                venue["assets"].add(asset)
            if timestamp and (not venue["last_seen"] or str(timestamp) > str(venue["last_seen"])):
                venue["last_seen"] = timestamp
                venue["latest_tx"] = tx_hash
                venue["latest_chain"] = chain

            direction = "swap"
            counterparty_label = venue_name
            counterparty_address = None
            counterparty_kind = "venue"
            touch_counterparty(
                key=venue_key,
                label=venue_name,
                address=None,
                chain=chain or None,
                direction="swap",
                amount_usd=amount_usd,
                asset=asset,
                tx_hash=tx_hash,
                timestamp=timestamp,
                dex=venue_name,
                kind="venue",
            )
        elif event_type == "transfer":
            summary["transfers"] += 1
            from_lower = (from_addr or "").lower()
            to_lower = (to_addr or "").lower()
            if from_lower == wallet_lower and to_addr and to_lower != wallet_lower:
                direction = "outflow"
                counterparty_address = to_addr
            elif to_lower == wallet_lower and from_addr and from_lower != wallet_lower:
                direction = "inflow"
                counterparty_address = from_addr
            else:
                direction = "internal"
                counterparty_address = to_addr or from_addr

            if direction == "inflow":
                summary["inflow_usd"] += amount_usd
            elif direction == "outflow":
                summary["outflow_usd"] += amount_usd

            if counterparty_address:
                counterparty_label = _short_wallet(counterparty_address)
                touch_counterparty(
                    key=f"address:{counterparty_address.lower()}",
                    label=counterparty_label,
                    address=counterparty_address,
                    chain=chain or None,
                    direction=direction,
                    amount_usd=amount_usd,
                    asset=asset,
                    tx_hash=tx_hash,
                    timestamp=timestamp,
                )

        activity.append({
            "event_type": event_type,
            "direction": direction,
            "chain": chain or None,
            "asset": asset,
            "amount_usd": round(amount_usd, 4),
            "timestamp": timestamp,
            "tx_hash": tx_hash,
            "counterparty": {
                "label": counterparty_label,
                "address": counterparty_address,
                "kind": counterparty_kind,
            },
            "dex": dex,
        })

    summary["net_transfer_usd"] = round(summary["inflow_usd"] - summary["outflow_usd"], 4)
    summary["counterparties"] = len(counterparties)
    summary["venues"] = len(venues)

    ranked_counterparties = sorted(
        counterparties.values(),
        key=lambda item: (item["swap_usd"] + item["inflow_usd"] + item["outflow_usd"], item["events"]),
        reverse=True,
    )
    ranked_venues = sorted(
        venues.values(),
        key=lambda item: (item["amount_usd"], item["events"]),
        reverse=True,
    )
    activity.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)

    return {
        "ok": bool(feed.get("ok")),
        "wallet": wallet,
        "summary": summary,
        "counterparties": [{
            "label": item["label"],
            "address": item["address"],
            "kind": item["kind"],
            "chains": sorted(item["chains"]),
            "assets": sorted(item["assets"]),
            "events": item["events"],
            "inflow_usd": round(item["inflow_usd"], 4),
            "outflow_usd": round(item["outflow_usd"], 4),
            "swap_usd": round(item["swap_usd"], 4),
            "net_usd": round(item["inflow_usd"] - item["outflow_usd"], 4),
            "latest_tx": item["latest_tx"],
            "latest_chain": item["latest_chain"],
            "last_seen": item["last_seen"],
            "dex": item.get("dex"),
        } for item in ranked_counterparties[:12]],
        "venues": [{
            "name": item["name"],
            "events": item["events"],
            "amount_usd": round(item["amount_usd"], 4),
            "chains": sorted(item["chains"]),
            "assets": sorted(item["assets"]),
            "latest_tx": item["latest_tx"],
            "latest_chain": item["latest_chain"],
            "last_seen": item["last_seen"],
        } for item in ranked_venues[:8]],
        "activity": activity[:12],
        "latency_ms": round((time.time() - started) * 1000, 2),
        "note": "Surface is derived from the current wallet feed sample. Transfers use direct from/to counterparties; swaps use venues until a deeper router/pool graph is available.",
    }


def get_wallet_identity_graph(
    wallet: str,
    *,
    limit: int = 40,
    chains: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    started = time.time()
    surface = get_wallet_surface(wallet, limit=limit, chains=chains, use_cache=use_cache)
    wallet = str(surface.get("wallet") or wallet or "").strip()
    root_id = f"wallet:{wallet.lower()}"

    nodes: dict[str, dict[str, Any]] = {
        root_id: {
            "id": root_id,
            "label": _short_wallet(wallet),
            "kind": "wallet",
            "address": wallet,
            "score": 100,
        }
    }
    edges: list[dict[str, Any]] = []
    asset_edges: dict[tuple[str, str], dict[str, Any]] = {}

    def edge_weight(amount_usd: float, events: int) -> float:
        amount = max(float(amount_usd or 0.0), 0.0)
        return round(min(100.0, (amount ** 0.33) + (events * 6)), 2)

    def add_asset_touch(source_id: str, asset: str, chain: str | None, amount_usd: float, events: int) -> None:
        clean_asset = str(asset or "").strip()
        if not clean_asset:
            return
        asset_id = f"asset:{str(chain or 'unknown').lower()}:{clean_asset.lower()}"
        nodes.setdefault(asset_id, {
            "id": asset_id,
            "label": clean_asset.upper(),
            "kind": "asset",
            "chain": chain,
            "score": 25,
        })
        key = (source_id, asset_id)
        row = asset_edges.setdefault(key, {
            "source": source_id,
            "target": asset_id,
            "kind": "asset_touch",
            "weight": 0.0,
            "amount_usd": 0.0,
            "events": 0,
            "confidence": 0.6,
            "evidence": [],
        })
        row["amount_usd"] += max(float(amount_usd or 0.0), 0.0)
        row["events"] += max(int(events or 0), 1)
        row["weight"] = edge_weight(row["amount_usd"], row["events"])

    for item in surface.get("counterparties", []) or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "address")
        address = str(item.get("address") or "").strip()
        label = str(item.get("label") or address or "unknown").strip()
        node_id = f"address:{address.lower()}" if address else f"venue:{label.lower()}"
        amount_usd = (
            float(item.get("inflow_usd") or 0.0)
            + float(item.get("outflow_usd") or 0.0)
            + float(item.get("swap_usd") or 0.0)
        )
        events = int(item.get("events") or 0)
        chain = item.get("latest_chain") or ((item.get("chains") or [None])[0] if isinstance(item.get("chains"), list) else None)

        nodes.setdefault(node_id, {
            "id": node_id,
            "label": label,
            "kind": kind,
            "address": address or None,
            "chain": chain,
            "score": edge_weight(amount_usd, events),
        })
        edges.append({
            "source": root_id,
            "target": node_id,
            "kind": "swap_venue" if kind == "venue" else "transfer_counterparty",
            "weight": edge_weight(amount_usd, events),
            "amount_usd": round(amount_usd, 4),
            "events": events,
            "confidence": 0.75 if kind == "venue" else 0.85,
            "latest_tx": item.get("latest_tx"),
            "latest_chain": chain,
            "direction": "mixed",
            "evidence": [value for value in [item.get("latest_tx"), item.get("last_seen")] if value],
        })

        for asset in item.get("assets") or []:
            add_asset_touch(node_id, asset, chain, amount_usd, events)

    for venue in surface.get("venues", []) or []:
        if not isinstance(venue, dict):
            continue
        label = str(venue.get("name") or "unknown venue").strip()
        node_id = f"venue:{label.lower()}"
        amount_usd = float(venue.get("amount_usd") or 0.0)
        events = int(venue.get("events") or 0)
        chain = venue.get("latest_chain") or ((venue.get("chains") or [None])[0] if isinstance(venue.get("chains"), list) else None)
        nodes.setdefault(node_id, {
            "id": node_id,
            "label": label,
            "kind": "venue",
            "address": None,
            "chain": chain,
            "score": edge_weight(amount_usd, events),
        })
        if not any(edge["source"] == root_id and edge["target"] == node_id for edge in edges):
            edges.append({
                "source": root_id,
                "target": node_id,
                "kind": "swap_venue",
                "weight": edge_weight(amount_usd, events),
                "amount_usd": round(amount_usd, 4),
                "events": events,
                "confidence": 0.75,
                "latest_tx": venue.get("latest_tx"),
                "latest_chain": chain,
                "direction": "swap",
                "evidence": [value for value in [venue.get("latest_tx"), venue.get("last_seen")] if value],
            })
        for asset in venue.get("assets") or []:
            add_asset_touch(node_id, asset, chain, amount_usd, events)

    edges.extend(asset_edges.values())
    edges.sort(key=lambda edge: (float(edge.get("weight") or 0.0), float(edge.get("amount_usd") or 0.0)), reverse=True)

    return {
        "ok": bool(surface.get("ok")),
        "wallet": wallet,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "direct_counterparties": len(surface.get("counterparties") or []),
            "venues": len(surface.get("venues") or []),
            "assets": len([node for node in nodes.values() if node.get("kind") == "asset"]),
            "evidence_grade": "sampled",
        },
        "nodes": list(nodes.values()),
        "edges": edges[:40],
        "surface": surface,
        "latency_ms": round((time.time() - started) * 1000, 2),
        "note": "Evidence graph only: shared venues/assets/flows are clues, not proof of common ownership.",
    }


def get_wallet_pnl(
    wallet: str,
    *,
    source: str = "all",
    timeframe: str = "30d",
    chains: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    source = (source or "all").lower()
    providers: list[dict[str, Any]] = []
    pnl: list[dict[str, Any]] = []

    if source in {"all", "cielo"}:
        cielo = _safe_provider("cielo", lambda: {"pnl": _cielo_token_pnl(wallet, timeframe=timeframe, chains=chains, use_cache=use_cache)})
        providers.append(cielo["status"])
        pnl.extend(cielo.get("pnl", []))

    if source in {"all", "zerion"}:
        zerion = _safe_provider("zerion", lambda: {"pnl": [_zerion_pnl(wallet, use_cache=use_cache)]})
        providers.append(zerion["status"])
        pnl.extend(zerion.get("pnl", []))

    return {
        "ok": any(provider.get("ok") for provider in providers),
        "wallet": wallet,
        "source": source,
        "timeframe": timeframe,
        "providers": providers,
        "pnl": pnl,
        "summary": _summarize_pnl(pnl),
    }


def _cielo_wallet_intel(wallet: str, *, timeframe: str, limit: int, chains: str | None, use_cache: bool) -> dict[str, Any]:
    if not _cielo_key():
        raise MissingProviderKey("CIELO_API_KEY")
    feed = get_wallet_feed(wallet, limit=limit, chains=chains, tx_types="swap,transfer", use_cache=use_cache)
    try:
        pnl = _cielo_token_pnl(wallet, timeframe=timeframe, chains=chains, use_cache=use_cache)
    except Exception as exc:
        pnl = [{
            "provider": "cielo",
            "status": "unavailable",
            "token": "token_pnl",
            "realized_usd": 0,
            "unrealized_usd": 0,
            "total_pnl_usd": 0,
            "profit_integrity": "provider_unavailable",
            "risk_score": 0,
            "block_trade": False,
            "note": str(exc)[:180],
        }]
    return {"events": feed.get("events", []), "pnl": pnl}


def _zerion_wallet_intel(wallet: str, *, use_cache: bool) -> dict[str, Any]:
    if not _zerion_auth_header():
        raise MissingProviderKey("ZERION_API_KEY")
    return {"events": [], "pnl": [_zerion_pnl(wallet, use_cache=use_cache)]}


def _cielo_token_pnl(wallet: str, *, timeframe: str, chains: str | None, use_cache: bool) -> list[dict[str, Any]]:
    if not _cielo_key():
        raise MissingProviderKey("CIELO_API_KEY")

    params: dict[str, str] = {"timeframe": timeframe}
    if chains:
        params["chain"] = chains
    url = f"{CIELO_BASE_URL}/v1/{urllib.parse.quote(wallet)}/pnl/tokens?{urllib.parse.urlencode(params)}"
    payload = _request_json(url, headers={"X-API-KEY": _cielo_key() or ""}, use_cache=use_cache)
    rows = _extract_items(payload)
    if isinstance(payload, dict) and payload.get("status") == 202:
        return [{"provider": "cielo", "status": "pending", "note": "PnL is not ready yet; retry later."}]
    return [_normalize_pnl_row(row, provider="cielo") for row in rows if isinstance(row, dict)]


def _zerion_pnl(wallet: str, *, use_cache: bool) -> dict[str, Any]:
    header = _zerion_auth_header()
    if not header:
        raise MissingProviderKey("ZERION_API_KEY")
    payload = _request_json(
        f"{ZERION_BASE_URL}/wallets/{urllib.parse.quote(wallet)}/pnl",
        headers={"Authorization": header},
        use_cache=use_cache,
    )
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    attributes = data.get("attributes", {}) if isinstance(data, dict) else {}
    return _normalize_zerion_pnl(attributes, wallet=wallet)


def _normalize_cielo_event(row: dict[str, Any]) -> dict[str, Any]:
    tx_hash = row.get("tx_hash") or row.get("hash")
    chain = row.get("chain") or row.get("network")
    wallet = row.get("actor") or row.get("wallet") or row.get("address")
    event_type = row.get("tx_type") or row.get("event_type") or "wallet_event"
    return {
        "source": "cielo",
        "type": event_type,
        "event_type": event_type,
        "tx_hash": tx_hash,
        "source_event_id": tx_hash,
        "chain": chain,
        "index": row.get("index") or row.get("log_index") or 0,
        "timestamp": row.get("timestamp"),
        "actor": wallet,
        "wallet": wallet,
        "wallet_label": row.get("wallet_label"),
        "asset": row.get("token0_symbol") or row.get("token1_symbol") or row.get("symbol") or row.get("name"),
        "amount_usd": _first_number(row.get("amount_usd"), row.get("token0_amount_usd"), row.get("token1_amount_usd")),
        "dex": row.get("dex"),
        "from": row.get("from"),
        "to": row.get("to"),
        "first_interaction": row.get("first_interaction"),
        "raw": _compact_raw(row),
    }


def _normalize_pnl_row(row: dict[str, Any], *, provider: str) -> dict[str, Any]:
    token = row.get("token_symbol") or row.get("symbol") or row.get("token") or row.get("name")
    realized = _first_number(row.get("realized_pnl_usd"), row.get("realized_usd"), row.get("realized_pnl"), row.get("total_realized_pnl_usd"))
    unrealized = _first_number(row.get("unrealized_pnl_usd"), row.get("unrealized_usd"), row.get("unrealized_pnl"), row.get("total_unrealized_pnl_usd"))
    total = _first_number(row.get("total_pnl_usd"), row.get("pnl_usd"), row.get("pnl"), None)
    if total is None:
        total = (realized or 0.0) + (unrealized or 0.0)
    risk = analyze_token_risk({
        "token": token,
        "chain": row.get("chain"),
        "token_address": row.get("token_address") or row.get("address") or row.get("contract_address"),
        "source_policy": f"wallet_pnl_provider:{provider}; token risk must remain traceable before any copy decision",
        "realized_usd": realized,
        "unrealized_usd": unrealized,
        "sell_count": row.get("sell_count") or row.get("sells"),
        "buy_count": row.get("buy_count") or row.get("buys"),
        "liquidity_usd": row.get("liquidity_usd"),
        "sell_tax_pct": row.get("sell_tax_pct"),
        "can_sell": row.get("can_sell"),
    })
    return {
        "provider": provider,
        "status": "ok",
        "token": token or "unknown",
        "chain": row.get("chain"),
        "token_address": row.get("token_address") or row.get("address") or row.get("contract_address"),
        "realized_usd": realized,
        "unrealized_usd": unrealized,
        "total_pnl_usd": total,
        "roi_pct": _first_number(row.get("roi_pct"), row.get("roi"), row.get("pnl_percentage")),
        "buy_count": row.get("buy_count") or row.get("buys"),
        "sell_count": row.get("sell_count") or row.get("sells"),
        "profit_integrity": risk["profit_integrity"],
        "risk_score": risk["risk_score"],
        "block_trade": risk["block_trade"],
        "flags": risk.get("flags", []),
        "missing_proofs": risk.get("missing_proofs", []),
        "source_policy": risk.get("source_policy"),
        "source_trace": risk.get("source_trace", {}),
        "raw": _compact_raw(row),
    }


def _normalize_zerion_pnl(attributes: dict[str, Any], *, wallet: str) -> dict[str, Any]:
    realized = _first_number(attributes.get("realized_gain"), attributes.get("realized_pnl"), attributes.get("realized_gain_usd"))
    unrealized = _first_number(attributes.get("unrealized_gain"), attributes.get("unrealized_pnl"), attributes.get("unrealized_gain_usd"))
    net_invested = _first_number(attributes.get("net_invested"), attributes.get("net_invested_usd"))
    total = _first_number(attributes.get("total_gain"), attributes.get("total_pnl"))
    if total is None:
        total = (realized or 0.0) + (unrealized or 0.0)
    return {
        "provider": "zerion",
        "status": "ok",
        "wallet": wallet,
        "token": "portfolio",
        "realized_usd": realized,
        "unrealized_usd": unrealized,
        "total_pnl_usd": total,
        "net_invested_usd": net_invested,
        "profit_integrity": "provider_portfolio_pnl",
        "risk_score": 0,
        "block_trade": False,
        "raw": _compact_raw(attributes),
    }


def _summarize_wallet(wallet: str, events: list[dict[str, Any]], pnl: list[dict[str, Any]]) -> dict[str, Any]:
    chains = sorted({str(event.get("chain")) for event in events if event.get("chain")})
    total_flow = sum(_first_number(event.get("amount_usd")) or 0.0 for event in events)
    first_interactions = sum(1 for event in events if event.get("raw", {}).get("first_interaction") is True)
    swaps = sum(1 for event in events if str(event.get("event_type") or event.get("type")).lower() == "swap")
    pnl_summary = _summarize_pnl(pnl)
    return {
        "wallet": wallet,
        "events": len(events),
        "swaps": swaps,
        "chains": chains,
        "first_interactions": first_interactions,
        "observed_flow_usd": round(total_flow, 4),
        "pnl": pnl_summary,
        "copy_ready": pnl_summary.get("trusted_realized_usd", 0) != 0 and first_interactions > 0,
    }


def _summarize_pnl(pnl: list[dict[str, Any]]) -> dict[str, Any]:
    realized = sum(_first_number(row.get("realized_usd")) or 0.0 for row in pnl)
    unrealized = sum(_first_number(row.get("unrealized_usd")) or 0.0 for row in pnl)
    total = sum(_first_number(row.get("total_pnl_usd")) or 0.0 for row in pnl)
    blocked = sum(1 for row in pnl if row.get("block_trade"))
    untrusted = sum(1 for row in pnl if row.get("profit_integrity") in {"not_trustworthy", "unrealized_or_unproven", "provider_unavailable"})
    return {
        "rows": len(pnl),
        "realized_usd": round(realized, 4),
        "unrealized_usd": round(unrealized, 4),
        "total_pnl_usd": round(total, 4),
        "trusted_realized_usd": round(realized if blocked == 0 and untrusted == 0 else 0.0, 4),
        "blocked_rows": blocked,
        "untrusted_rows": untrusted,
    }


def _build_wallet_copy_preview(
    *,
    status: str,
    observed_flow: float,
    trusted_realized: float,
    first_interactions: int,
    provider_count: int,
    capital: float,
) -> dict[str, Any]:
    if status == "blocked":
        return {
            "mode": "blocked",
            "capital": capital,
            "estimated_value": capital,
            "pnl": 0.0,
            "roi_pct": 0.0,
            "basis": "risk_block",
            "note": "Blocked because fake-profit or sellability risk is already detected.",
        }
    if status == "review":
        return {
            "mode": "needs_profit_proof",
            "capital": capital,
            "estimated_value": capital,
            "pnl": 0.0,
            "roi_pct": 0.0,
            "basis": "profit_integrity_review",
            "note": "Wallet has incomplete sell/PnL proof or suspicious traded assets. Simulation is disabled until verified.",
        }
    if trusted_realized <= 0 or observed_flow <= 0:
        return {
            "mode": "insufficient_data",
            "capital": capital,
            "estimated_value": capital,
            "pnl": 0.0,
            "roi_pct": 0.0,
            "basis": "no_trusted_realized",
            "note": "No trusted realized PnL yet. Keep this wallet on watchlist mode only.",
        }

    base_roi = trusted_realized / max(observed_flow, 1.0)
    base_roi = max(-0.95, min(1.25, base_roi))
    provider_penalty = 0.18 if provider_count <= 1 else 0.10
    freshness_penalty = min(0.18, first_interactions * 0.02)
    effective_roi = base_roi * max(0.35, 1.0 - provider_penalty - freshness_penalty)
    estimated_value = max(0.0, capital * (1.0 + effective_roi))
    pnl = estimated_value - capital
    return {
        "mode": "proxy_from_trusted_realized",
        "capital": round(capital, 2),
        "estimated_value": round(estimated_value, 2),
        "pnl": round(pnl, 2),
        "roi_pct": round(effective_roi * 100, 2),
        "basis": "trusted_realized_vs_observed_flow",
        "note": "Proxy only: trusted realized PnL / observed flow, haircut by provider coverage and fresh-trade concentration.",
    }


def _summarize_asset_focus(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    focus: dict[str, dict[str, Any]] = {}
    for event in events:
        asset = str(event.get("asset") or event.get("chain") or "unknown")
        chain = str(event.get("chain") or "unknown")
        key = f"{chain}:{asset}"
        row = focus.setdefault(key, {
            "asset": asset,
            "chain": chain,
            "events": 0,
            "amount_usd": 0.0,
        })
        row["events"] += 1
        row["amount_usd"] += _first_number(event.get("amount_usd")) or 0.0

    ranked = sorted(
        focus.values(),
        key=lambda item: (item["amount_usd"], item["events"]),
        reverse=True,
    )
    return [{
        "asset": item["asset"],
        "chain": item["chain"],
        "events": item["events"],
        "amount_usd": round(item["amount_usd"], 4),
    } for item in ranked]


def _looks_suspicious_asset(asset: Any) -> bool:
    symbol = str(asset or "").strip().lower()
    if not symbol:
        return False
    suspicious_terms = (
        "scam",
        "honeypot",
        "rug",
        "fake",
        "airdrop",
        "claim",
        "reward",
    )
    return any(term in symbol for term in suspicious_terms)


def _safe_provider(provider: str, fn: Any) -> dict[str, Any]:
    started = time.time()
    try:
        result = fn()
        return {
            **result,
            "status": {
                "provider": provider,
                "ok": True,
                "status": "ok",
                "latency_ms": round((time.time() - started) * 1000, 2),
                "error": None,
            },
        }
    except MissingProviderKey as exc:
        return {
            "events": [],
            "pnl": [],
            "status": {
                "provider": provider,
                "ok": False,
                "status": "missing_key",
                "latency_ms": round((time.time() - started) * 1000, 2),
                "error": str(exc),
            },
        }
    except Exception as exc:
        return {
            "events": [],
            "pnl": [],
            "status": {
                "provider": provider,
                "ok": False,
                "status": "error",
                "latency_ms": round((time.time() - started) * 1000, 2),
                "error": str(exc)[:240],
            },
        }


def _request_json(url: str, *, headers: dict[str, str], use_cache: bool) -> Any:
    cache_key = url + "|" + "|".join(sorted(headers.keys()))
    now = time.time()
    cached = _CACHE.get(cache_key)
    if use_cache and cached and now - cached[0] <= DEFAULT_CACHE_TTL_SECONDS:
        return cached[1]

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            **headers,
        },
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        text = response.read().decode("utf-8", errors="ignore")
        # Scrapling may wrap JSON in HTML - extract raw JSON
        if text.startswith("{"):
            payload = json.loads(text)
        elif text.startswith("<"):
            # Look for JSON inside HTML body
            m = re.search(r"<body>\s*<p>(\{.*?\})</p>\s*</body>", text, re.DOTALL)
            if m:
                payload = json.loads(m.group(1))
            else:
                payload = {}
        else:
            payload = json.loads(text)
    _CACHE[cache_key] = (now, payload)
    return payload


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    # Cielo response: {status: "ok", data: {items: [...]}}
    data = payload.get("data", payload)
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return items
    if isinstance(data, list):
        return data
    for key in ["items", "tokens", "result", "portfolio", "positions", "data"]:
        value = (data if isinstance(data, dict) else payload).get(key)
        if isinstance(value, list):
            return value
    return []


def _missing_key_response(provider: str, env_key: str) -> dict[str, Any]:
    return {
        "ok": False,
        "provider": provider,
        "status": "missing_key",
        "required_env": env_key,
        "events": [],
        "pnl": [],
    }


def _cielo_key() -> str | None:
    value = os.getenv("CIELO_API_KEY") or os.getenv("CIELO_KEY")
    return value.strip() if value else None


def _cielo_key_validated() -> str | None:
    """Return Cielo key if set. Always try to use it - let the API decide."""
    key = _cielo_key()
    if not key:
        return None
    return key


def _zerion_auth_header() -> str | None:
    encoded = os.getenv("ZERION_BASIC_AUTH")
    if encoded:
        return encoded if encoded.lower().startswith("basic ") else f"Basic {encoded}"
    key = os.getenv("ZERION_API_KEY")
    if not key:
        return None
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _compact_raw(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "wallet", "wallet_label", "tx_hash", "tx_type", "chain", "timestamp", "dex",
        "amount_usd", "token0_symbol", "token1_symbol", "first_interaction",
        "symbol", "name", "realized_pnl_usd", "unrealized_pnl_usd", "roi",
    ]
    return {key: row.get(key) for key in keys if key in row}


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _short_wallet(value: str) -> str:
    value = str(value or "")
    if len(value) <= 14:
        return value
    return f"{value[:6]}...{value[-4:]}"


class MissingProviderKey(RuntimeError):
    pass

