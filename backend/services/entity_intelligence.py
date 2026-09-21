"""
Entity Intelligence — On-chain entity analysis (Arkham replacement)
====================================================================
Calculates entity portfolios, flows, and metrics from blockchain data.
Uses wallet_analyzer for per-wallet analysis, aggregates at entity level.
Arkham/Scrapling/Firecrawl are ONLY used for label seeding, never for data.
"""
from __future__ import annotations
import json
import os
import shutil
import sqlite3
import time
from typing import Any

from services.wallet_analyzer import analyze_wallet_full
import concurrent.futures
import signal
import concurrent.futures

_SERVICE_DIR = os.path.dirname(__file__)
_DATA_DIR = os.path.abspath(os.path.join(_SERVICE_DIR, "..", "data", "entity"))
os.makedirs(_DATA_DIR, exist_ok=True)
_LEGACY_DB_PATH = os.path.abspath(os.path.join(_SERVICE_DIR, "..", "data", "legacy", "entity_labels.db"))
_DB_PATH = os.path.join(_DATA_DIR, "entity_labels.db")
if not os.path.exists(_DB_PATH) and os.path.exists(_LEGACY_DB_PATH):
    shutil.copy2(_LEGACY_DB_PATH, _DB_PATH)

# Seed data — known exchange wallets (extracted from arkham_scraper.py hardcoded data)
_EXCHANGE_SEED: dict[str, dict[str, Any]] = {
    "binance": {
        "name": "Binance",
        "type": "exchange",
        "category": "cex",
        "chains": ["eth", "bsc"],
        "wallets": {
            "eth": [
                "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE",
                "0xd93d01ce3156c64c6204fb11c712b601f33dcd37",
                "0x28C6c06298d514Db089934071355E5743bf21d60",
                "0x21a31Ee1afC51d94C2eFcCAa209116e2E88fCc9a",
                "0xDFd5293D8e347dFe59E172e2Cd0e4d8B1E40601d",
            ],
            "bsc": [
                "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE",
                "0xd93d01ce3156c64c6204fb11c712b601f33dcd37",
            ],
        },
    },
    "blackrock": {
        "name": "BlackRock",
        "type": "fund",
        "category": "etf_issuer",
        "chains": ["eth"],
        "wallets": {
            "eth": [
                "0x8fBFB3D47Bc61D80fBf787d2677F3A6a8d3F5b7E",
            ],
        },
    },
    "uniswap": {
        "name": "Uniswap",
        "type": "protocol",
        "category": "dex",
        "chains": ["eth"],
        "wallets": {
            "eth": [
                "0x1F98431c8aD98523631AE4a59f267346ea31F984",
            ],
        },
    },
}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_slug TEXT NOT NULL,
            entity_name TEXT,
            entity_type TEXT,
            wallet_address TEXT NOT NULL,
            chain TEXT NOT NULL,
            wallet_type TEXT DEFAULT 'unknown',
            source TEXT DEFAULT 'seed',
            confidence REAL DEFAULT 1.0,
            first_seen REAL,
            last_updated REAL,
            UNIQUE(entity_slug, wallet_address, chain)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_slug TEXT NOT NULL,
            ts REAL NOT NULL,
            net_worth_usd REAL,
            wallet_count INTEGER,
            token_count INTEGER,
            chains_json TEXT,
            holdings_json TEXT,
            flows_json TEXT,
            activity_json TEXT,
            source_quality TEXT DEFAULT 'internal',
            UNIQUE(entity_slug, ts)
        )
    """)
    conn.commit()
    conn.close()


def _seed_labels() -> None:
    """Seed exchange wallets from hardcoded data."""
    conn = _get_db()
    now = time.time()
    for slug, info in _EXCHANGE_SEED.items():
        for chain, addresses in info.get("wallets", {}).items():
            for addr in addresses:
                conn.execute(
                    """INSERT OR IGNORE INTO entity_labels
                       (entity_slug, entity_name, entity_type, wallet_address, chain, wallet_type, source, confidence, first_seen, last_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (slug, info["name"], info["type"], addr.lower(), chain, "hot_wallet", "seed", 1.0, now, now)
                )
    conn.commit()
    conn.close()


_init_db()
_seed_labels()


def get_entity_labels(entity_slug: str | None = None) -> list[dict[str, Any]]:
    """Get all labels for an entity."""
    conn = _get_db()
    if entity_slug:
        rows = conn.execute(
            "SELECT * FROM entity_labels WHERE entity_slug = ? ORDER BY chain, wallet_address",
            (entity_slug.lower(),)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM entity_labels ORDER BY entity_slug, chain, wallet_address").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_entity_list() -> list[dict[str, Any]]:
    """Get list of all tracked entities."""
    conn = _get_db()
    rows = conn.execute(
        """SELECT entity_slug, entity_name, entity_type, COUNT(DISTINCT wallet_address) as wallet_count,
                  COUNT(DISTINCT chain) as chain_count
           FROM entity_labels GROUP BY entity_slug ORDER BY entity_slug"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def analyze_entity(entity_slug: str, max_wallets: int = 10) -> dict[str, Any]:
    """
    Analyze an entity by aggregating wallet_analyzer results for all its wallets.
    This is the CORE function — replaces Arkham data with on-chain computation.
    """
    labels = get_entity_labels(entity_slug)
    if not labels:
        return {"ok": False, "error": f"Entity '{entity_slug}' not found"}

    entity_info = _EXCHANGE_SEED.get(entity_slug.lower(), {})
    entity_name = entity_info.get("name", entity_slug.title())
    entity_type = entity_info.get("type", "unknown")

    # Analyze each wallet (limit to avoid RPC overload)
    wallets_analyzed = []
    total_net_worth = 0.0
    all_tokens: list[dict] = []
    all_chains: set[str] = set()
    total_tx = 0
    total_inflow = 0.0
    total_outflow = 0.0

    def _analyze_wallet(addr: str, chain: str, timeout: float = 12.0):
        """Run wallet analysis with hard timeout."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(analyze_wallet_full, addr, chain)
            try:
                return fut.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                return {"ok": False, "error": "timeout"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

    for label in labels[:max_wallets]:
        addr = label["wallet_address"]
        chain = label["chain"]
        try:
            result = _analyze_wallet(addr, chain, timeout=12.0)
            if result.get("ok"):
                wallets_analyzed.append({
                    "address": addr,
                    "chain": chain,
                    "net_worth_usd": result.get("net_worth_usd"),
                    "tx_count": result.get("tx_count"),
                    "label": result.get("wallet_label"),
                    "token_count": result.get("tokens_with_value", 0),
                    "top_holdings": result.get("top_holdings", [])[:3],
                })
                if result.get("net_worth_usd"):
                    total_net_worth += result["net_worth_usd"]
                if result.get("tokens"):
                    all_tokens.extend(result["tokens"])
                all_chains.add(chain)
                total_tx += result.get("tx_count", 0)
                if result.get("flow"):
                    total_inflow += result["flow"].get("inflow_eth", 0)
                    total_outflow += result["flow"].get("outflow_eth", 0)
        except Exception:
            continue

    # Aggregate token holdings across all wallets
    token_agg: dict[str, dict] = {}
    for t in all_tokens:
        sym = t.get("symbol", "UNKNOWN")
        if sym not in token_agg:
            token_agg[sym] = {
                "symbol": sym,
                "total_value": 0.0,
                "total_balance": 0.0,
                "price_usd": t.get("price_usd"),
                "confidence": t.get("confidence"),
            }
        token_agg[sym]["total_value"] += (t.get("value_usd") or 0)
        token_agg[sym]["total_balance"] += t.get("balance", 0)

    top_holdings = sorted(
        [{"symbol": k, "value_usd": round(v["total_value"], 2), "balance": round(v["total_balance"], 4),
          "price_usd": v["price_usd"], "confidence": v["confidence"]} for k, v in token_agg.items()],
        key=lambda x: x["value_usd"],
        reverse=True,
    )[:10]

    # Quality / Coverage analysis
    wallets_known = len(labels)
    wallets_analyzed_count = len(wallets_analyzed)
    wallets_failed = wallets_known - wallets_analyzed_count
    coverage_pct = round((wallets_analyzed_count / max(1, wallets_known)) * 100, 1)

    # Source breakdown
    seed_count = sum(1 for l in labels if l.get("source") == "seed")
    inferred_count = sum(1 for l in labels if l.get("source") == "blockchain_inferred")
    manual_count = sum(1 for l in labels if l.get("source") == "manual")
    source_breakdown = {
        "seed": seed_count,
        "inferred": inferred_count,
        "manual": manual_count,
        "other": wallets_known - seed_count - inferred_count - manual_count,
    }

    # Warnings
    warnings: list[str] = []
    if wallets_analyzed_count < wallets_known:
        warnings.append(f"only {wallets_analyzed_count}/{wallets_known} wallets analyzed")
    if wallets_analyzed_count < 3:
        warnings.append("low wallet sample size")
    if seed_count == wallets_known:
        warnings.append("all labels from hardcoded seed — verify independently")
    medium_conf_tokens = [t for t in top_holdings if t.get("confidence") == "medium"]
    if len(medium_conf_tokens) > len(top_holdings) * 0.3:
        warnings.append("significant holdings from medium-confidence tokens")

    # Confidence level
    if coverage_pct >= 95 and not warnings:
        confidence_level = "high"
    elif coverage_pct >= 60 and len(warnings) <= 1:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    # Coverage label
    coverage = "full" if wallets_analyzed_count == wallets_known else "partial"

    result = {
        "ok": True,
        "entity": {
            "slug": entity_slug.lower(),
            "name": entity_name,
            "type": entity_type,
            "wallets_known": wallets_known,
            "wallets_analyzed": wallets_analyzed_count,
            "wallets_failed": wallets_failed,
            "chains": sorted(all_chains),
        },
        "portfolio": {
            "net_worth_usd": round(total_net_worth, 2) if total_net_worth > 0 else None,
            "token_count": len(token_agg),
            "tx_count": total_tx,
            "top_holdings": top_holdings,
        },
        "flows": {
            "inflow_eth": round(total_inflow, 6),
            "outflow_eth": round(total_outflow, 6),
            "net_flow_eth": round(total_inflow - total_outflow, 6),
        },
        "wallets": wallets_analyzed,
        "quality": {
            "coverage_pct": coverage_pct,
            "coverage_label": coverage,
            "confidence_level": confidence_level,
            "warnings": warnings,
            "source_breakdown": source_breakdown,
            "last_snapshot_ts": time.time(),
        },
        "source": "internal_onchain",
        "ts": time.time(),
    }

    # Save snapshot
    _save_snapshot(entity_slug, result)
    return result


def _save_snapshot(entity_slug: str, data: dict[str, Any]) -> None:
    """Save entity snapshot to DB."""
    conn = _get_db()
    conn.execute(
        """INSERT OR REPLACE INTO entity_snapshots
           (entity_slug, ts, net_worth_usd, wallet_count, token_count, chains_json, holdings_json, flows_json, activity_json, source_quality)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entity_slug.lower(),
            data.get("ts", time.time()),
            data["portfolio"].get("net_worth_usd"),
            data["entity"].get("wallets_analyzed", 0),
            data["portfolio"].get("token_count", 0),
            json.dumps(data["entity"].get("chains", [])),
            json.dumps(data["portfolio"].get("top_holdings", [])),
            json.dumps(data.get("flows", {})),
            json.dumps({"tx_count": data["portfolio"].get("tx_count", 0)}),
            data.get("source", "internal"),
        )
    )
    conn.commit()
    conn.close()


def get_entity_snapshot(entity_slug: str) -> dict[str, Any] | None:
    """Get latest cached snapshot for an entity."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM entity_snapshots WHERE entity_slug = ? ORDER BY ts DESC LIMIT 1",
        (entity_slug.lower(),)
    ).fetchone()
    conn.close()
    if row:
        return {
            "entity_slug": row["entity_slug"],
            "ts": row["ts"],
            "net_worth_usd": row["net_worth_usd"],
            "wallet_count": row["wallet_count"],
            "token_count": row["token_count"],
            "chains": json.loads(row["chains_json"]) if row["chains_json"] else [],
            "holdings": json.loads(row["holdings_json"]) if row["holdings_json"] else [],
            "flows": json.loads(row["flows_json"]) if row["flows_json"] else {},
            "source_quality": row["source_quality"],
        }
    return None


__all__ = [
    "get_entity_labels",
    "get_entity_list",
    "analyze_entity",
    "get_entity_snapshot",
]
