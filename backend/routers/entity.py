from __future__ import annotations
import asyncio
import time
from fastapi import APIRouter, HTTPException
from services.entity_intelligence import (
    get_entity_list,
    get_entity_labels,
    analyze_entity,
    get_entity_snapshot,
)

router = APIRouter(tags=["entity"])

_RESERVED_SLUGS = {"list", "search", "portfolio", "wallets", "flows", "history"}


def _check_slug(slug: str) -> str:
    if slug.lower() in _RESERVED_SLUGS:
        raise HTTPException(400, f"'{slug}' is a reserved endpoint name.")
    return slug.lower()


def _build_honest_quality(entity: dict, quality: dict) -> dict:
    wallets_known = entity.get("wallets_known", 0)
    wallets_analyzed = entity.get("wallets_analyzed", 0)
    source_breakdown = quality.get("source_breakdown", {})
    warnings = quality.get("warnings", [])
    coverage_pct = quality.get("coverage_pct", 0.0)
    is_partial = wallets_analyzed < wallets_known or coverage_pct < 95
    seed_count = source_breakdown.get("seed", 0)
    seed_pct = seed_count / max(1, wallets_known)
    conf_level = quality.get("confidence_level", "low")
    if seed_pct > 0.5:
        conf_level = "low"
    elif seed_pct > 0.2 and conf_level == "high":
        conf_level = "medium"
    notes = []
    if is_partial:
        notes.append(f"Only {wallets_analyzed}/{wallets_known} wallets observed")
    if seed_pct > 0:
        notes.append(f"{int(seed_pct * 100)}% labels from static seed — verify independently")
    if warnings:
        notes.extend(warnings)
    if not notes:
        notes.append("Internal on-chain verified")
    return {
        "coverage_pct": round(coverage_pct, 1),
        "confidence_level": conf_level,
        "source_breakdown": {
            "internal_onchain": wallets_analyzed,
            "static_seed": seed_count,
            "inferred": source_breakdown.get("inferred", 0),
            "manual": source_breakdown.get("manual", 0),
            "other": source_breakdown.get("other", 0),
        },
        "reliability_notes": notes,
        "is_partial": is_partial,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }


def _entity_from_snapshot(snapshot: dict) -> dict:
    """Build response from cached snapshot (fast)."""
    slug = snapshot.get("entity_slug", "unknown")
    honest_quality = {
        "coverage_pct": 0,
        "confidence_level": "low",
        "source_breakdown": {"internal_onchain": 0, "static_seed": 0, "inferred": 0, "manual": 0, "other": 0},
        "reliability_notes": ["Cached snapshot — data may be stale"],
        "is_partial": True,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(snapshot.get("ts", 0))),
    }
    return {
        "ok": True,
        "entity": {
            "name": slug.title(),
            "type": "entity",
            "category": "entity",
            "chains": snapshot.get("chains", []),
            "badges": ["cached"],
            "tags": [],
            "source": "internal_onchain_cache",
        },
        "wallets_count": snapshot.get("wallet_count", 0),
        "wallets": [],
        "flow": {
            "inflow": snapshot.get("flows", {}).get("inflow_eth", 0),
            "outflow": snapshot.get("flows", {}).get("outflow_eth", 0),
            "net_flow": snapshot.get("flows", {}).get("net_flow_eth", 0),
            "tx_count": 0,
        },
        "intelligence": {
            "coverage": {
                "observed_wallets": snapshot.get("wallet_count", 0),
                "observed_tokens": snapshot.get("token_count", 0),
                "snapshots_scanned": snapshot.get("wallet_count", 0),
                "coverage_label": "Cached Snapshot",
                "coverage_note": "Data from cached snapshot — may be stale",
            },
            "observed_holdings": snapshot.get("holdings", []),
            "wallets": [],
            "recent_activity": [],
            "counterparties": [],
            "top_tags": [],
            "chains": [{"chain": c} for c in snapshot.get("chains", [])],
        },
        "profile": {
            "description": f"{slug.title()} tracked via on-chain intelligence.",
            "badges": ["cached_snapshot"],
        },
        "quality": honest_quality,
        "source": "internal_onchain_cache",
        "source_quality": {
            "primary_source": "cached_external",
            "confidence": "low",
            "is_partial": True,
            "warnings": ["Cached snapshot — data may be stale"],
        },
    }


def _entity_from_fresh(result: dict, slug: str) -> dict:
    """Build response from fresh analysis."""
    entity = result.get("entity", {})
    portfolio = result.get("portfolio", {})
    flows = result.get("flows", {})
    quality = result.get("quality", {})
    wallets = result.get("wallets", [])
    observed_holdings = []
    for h in portfolio.get("top_holdings", []):
        observed_holdings.append({
            "symbol": h.get("symbol"),
            "value_usd": h.get("value_usd"),
            "balance": h.get("balance"),
            "price_usd": h.get("price_usd"),
            "confidence": h.get("confidence"),
        })
    wallet_list = []
    for w in wallets:
        wallet_list.append({
            "address": w.get("address"),
            "chain": w.get("chain"),
            "label": w.get("label"),
            "type": w.get("label", "unknown"),
            "tags": [{"name": w.get("label", ""), "type": "onchain"}],
        })
    honest_quality = _build_honest_quality(entity, quality)
    coverage_label = "Observed Coverage"
    if honest_quality["is_partial"]:
        coverage_label = "Partial Coverage"
    if honest_quality["confidence_level"] == "low":
        coverage_label = "Partial / Seed Data"
    return {
        "ok": True,
        "entity": {
            "name": entity.get("name"),
            "type": entity.get("type"),
            "category": entity.get("type"),
            "chains": entity.get("chains", []),
            "badges": [entity.get("type", ""), "onchain_verified"],
            "tags": [entity.get("type", "")],
            "source": "internal_onchain",
        },
        "wallets_count": entity.get("wallets_known", 0),
        "wallets": wallet_list,
        "flow": {
            "inflow": flows.get("inflow_eth", 0),
            "outflow": flows.get("outflow_eth", 0),
            "net_flow": flows.get("net_flow_eth", 0),
            "tx_count": portfolio.get("tx_count", 0),
        },
        "intelligence": {
            "coverage": {
                "observed_wallets": entity.get("wallets_analyzed", 0),
                "observed_tokens": portfolio.get("token_count", 0),
                "snapshots_scanned": entity.get("wallets_analyzed", 0),
                "coverage_label": coverage_label,
                "coverage_note": "; ".join(honest_quality["reliability_notes"]),
            },
            "observed_holdings": observed_holdings,
            "wallets": wallet_list,
            "recent_activity": [],
            "counterparties": [],
            "top_tags": [],
            "chains": [{"chain": c} for c in entity.get("chains", [])],
        },
        "profile": {
            "description": f"{entity.get('name', slug)} is a {entity.get('type', 'entity')} tracked via on-chain intelligence.",
            "badges": ["internal_tracking"],
        },
        "quality": honest_quality,
        "source": "internal_onchain",
    }


@router.get("/list")
async def entity_list():
    return await asyncio.to_thread(get_entity_list)


@router.get("/{slug}")
async def entity_detail(slug: str):
    """Get entity analysis. Returns cached snapshot immediately if available,
    otherwise runs fresh analysis with 1 wallet (fast) + background refresh."""
    slug = _check_slug(slug)

    # Always try snapshot first for instant response
    snapshot = await asyncio.to_thread(get_entity_snapshot, slug)
    if snapshot:
        return _entity_from_snapshot(snapshot)

    # No snapshot — run fast analysis (1 wallet only, 25s timeout)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(analyze_entity, slug, max_wallets=1),
            timeout=25.0,
        )
        if result.get("ok"):
            return _entity_from_fresh(result, slug)
    except asyncio.TimeoutError:
        pass

    # Fallback: no data at all
    return {
        "ok": False,
        "error": f"Entity '{slug}' not found or analysis timed out",
        "quality": {
            "coverage_pct": 0,
            "confidence_level": "low",
            "source_breakdown": {"internal_onchain": 0, "static_seed": 0, "inferred": 0, "manual": 0, "other": 0},
            "reliability_notes": ["No data available"],
            "is_partial": True,
            "last_updated": None,
        },
    }


@router.get("/{slug}/portfolio")
async def entity_portfolio(slug: str):
    slug = _check_slug(slug)
    result = await asyncio.to_thread(analyze_entity, slug, max_wallets=1)
    if result.get("ok"):
        return {
            "ok": True,
            "entity": result["entity"],
            "portfolio": result["portfolio"],
            "coverage": result.get("coverage"),
        }
    return result


@router.get("/{slug}/wallets")
async def entity_wallets(slug: str):
    slug = _check_slug(slug)
    labels = await asyncio.to_thread(get_entity_labels, slug)
    return {
        "ok": True,
        "entity_slug": slug,
        "wallet_count": len(labels),
        "wallets": [{"address": l["wallet_address"], "chain": l["chain"], "type": l["wallet_type"]} for l in labels],
    }


@router.get("/{slug}/flows")
async def entity_flows(slug: str):
    slug = _check_slug(slug)
    result = await asyncio.to_thread(analyze_entity, slug, max_wallets=1)
    if result.get("ok"):
        return {
            "ok": True,
            "entity": result["entity"],
            "flows": result["flows"],
        }
    return result


@router.get("/{slug}/history")
async def entity_history(slug: str):
    slug = _check_slug(slug)
    snapshot = await asyncio.to_thread(get_entity_snapshot, slug)
    if snapshot:
        return {"ok": True, "snapshot": snapshot}
    return {"ok": False, "error": "No snapshot available"}
