from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services.label_expansion import expand_labels
from services.label_ledger import DB_PATH as LABEL_DB_PATH
from services.label_ledger import _chain_key, _init_db as init_label_db
from services.onchain.core.paths import DB_PATH as ONCHAIN_DB_PATH

ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"
CHAIN_IDS = {
    "ethereum": "1",
    "eth": "1",
    "bsc": "56",
    "base": "8453",
    "arbitrum": "42161",
    "polygon": "137",
    "optimism": "10",
}


def _api_key(chain: str) -> str:
    if _chain_key(chain) == "bsc":
        return os.getenv("BSCSCAN_API_KEY", "").strip() or os.getenv("ETHERSCAN_API_KEY", "").strip()
    return os.getenv("ETHERSCAN_API_KEY", "").strip()


def _ensure_onchain_schema() -> None:
    ONCHAIN_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ONCHAIN_DB_PATH))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS blocks (
                chain TEXT,
                block_number INTEGER,
                block_hash TEXT,
                timestamp INTEGER,
                tx_count INTEGER,
                PRIMARY KEY (chain, block_number)
            );
            CREATE TABLE IF NOT EXISTS transactions (
                tx_hash TEXT PRIMARY KEY,
                chain TEXT,
                block_number INTEGER,
                from_addr TEXT,
                to_addr TEXT,
                value REAL,
                timestamp INTEGER
            );
            CREATE TABLE IF NOT EXISTS wallets (
                wallet TEXT PRIMARY KEY,
                chain TEXT,
                first_seen INTEGER,
                last_seen INTEGER,
                total_tx INTEGER DEFAULT 0,
                total_swaps INTEGER DEFAULT 0,
                total_volume REAL DEFAULT 0,
                native_balance REAL DEFAULT 0,
                labels TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _etherscan_get(params: dict[str, Any]) -> dict[str, Any]:
    url = f"{ETHERSCAN_V2_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "CoreEquity/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _fetch_seed_transactions(chain: str, address: str, page: int = 1, offset: int = 25) -> list[dict[str, Any]]:
    chain = _chain_key(chain)
    chain_id = CHAIN_IDS.get(chain)
    key = _api_key(chain)
    if not chain_id or not key:
        return []
    payload = _etherscan_get({
        "chainid": chain_id,
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": page,
        "offset": max(1, min(offset, 100)),
        "sort": "desc",
        "apikey": key,
    })
    result = payload.get("result")
    return result if isinstance(result, list) else []


def _fetch_seed_token_transfers(chain: str, address: str, page: int = 1, offset: int = 25) -> list[dict[str, Any]]:
    chain = _chain_key(chain)
    chain_id = CHAIN_IDS.get(chain)
    key = _api_key(chain)
    if not chain_id or not key:
        return []
    payload = _etherscan_get({
        "chainid": chain_id,
        "module": "account",
        "action": "tokentx",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": page,
        "offset": max(1, min(offset, 100)),
        "sort": "desc",
        "apikey": key,
    })
    result = payload.get("result")
    return result if isinstance(result, list) else []


def _load_seed_addresses(chain: str | None, limit: int) -> list[dict[str, Any]]:
    init_label_db()
    conn = sqlite3.connect(str(LABEL_DB_PATH))
    try:
        params: list[Any] = []
        where = "WHERE confidence = 'high'"
        if chain:
            where += " AND chain = ?"
            params.append(_chain_key(chain))
        rows = conn.execute(
            f"""
            SELECT chain, address, label, entity
            FROM labels
            {where}
            ORDER BY entity, label
            LIMIT ?
            """,
            [*params, max(1, min(limit, 200))],
        ).fetchall()
        return [
            {"chain": row[0], "address": row[1], "label": row[2], "entity": row[3]}
            for row in rows
            if str(row[1] or "").startswith("0x")
        ]
    finally:
        conn.close()


def _upsert_wallet(conn: sqlite3.Connection, chain: str, address: str, timestamp: int, label: str = "") -> None:
    address = str(address or "").lower()
    if not address:
        return
    row = conn.execute("SELECT first_seen, last_seen, total_tx, labels FROM wallets WHERE wallet = ?", (address,)).fetchone()
    if row:
        first_seen = min(int(row[0] or timestamp), timestamp)
        last_seen = max(int(row[1] or timestamp), timestamp)
        labels = row[3] or label
        conn.execute(
            "UPDATE wallets SET first_seen = ?, last_seen = ?, total_tx = total_tx + 1, labels = ? WHERE wallet = ?",
            (first_seen, last_seen, labels, address),
        )
    else:
        conn.execute(
            "INSERT INTO wallets (wallet, chain, first_seen, last_seen, total_tx, labels) VALUES (?, ?, ?, ?, 1, ?)",
            (address, chain, timestamp, timestamp, label),
        )


def ingest_seed_transactions(
    chain: str | None = None,
    seed_limit: int = 10,
    tx_per_seed: int = 25,
    sleep_seconds: float = 0.22,
    expand_after: bool = True,
) -> dict[str, Any]:
    """Fetch recent transactions around high-confidence labels via explorer API."""
    _ensure_onchain_schema()
    seed_limit = max(1, min(int(seed_limit or 10), 50))
    tx_per_seed = max(1, min(int(tx_per_seed or 25), 100))
    seeds = _load_seed_addresses(chain, seed_limit)
    conn = sqlite3.connect(str(ONCHAIN_DB_PATH))
    tx_seen = 0
    tx_inserted = 0
    wallets_seen: set[tuple[str, str]] = set()
    errors: list[dict[str, str]] = []
    try:
        for seed in seeds:
            seed_chain = _chain_key(seed["chain"])
            try:
                txs = [
                    *_fetch_seed_transactions(seed_chain, seed["address"], offset=tx_per_seed),
                    *_fetch_seed_token_transfers(seed_chain, seed["address"], offset=tx_per_seed),
                ]
            except Exception as exc:
                errors.append({"address": seed["address"], "chain": seed_chain, "error": str(exc)[:180]})
                continue
            time.sleep(max(0.0, min(float(sleep_seconds or 0), 2.0)))
            for tx in txs:
                tx_seen += 1
                tx_hash = str(tx.get("hash") or "").lower()
                from_addr = str(tx.get("from") or "").lower()
                to_addr = str(tx.get("to") or "").lower()
                block_number = int(tx.get("blockNumber") or 0)
                timestamp = int(tx.get("timeStamp") or 0)
                value = int(tx.get("value") or 0) / 1e18
                if tx.get("tokenDecimal"):
                    try:
                        value = int(tx.get("value") or 0) / (10 ** int(tx.get("tokenDecimal") or 18))
                    except Exception:
                        value = 0.0
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO transactions (tx_hash, chain, block_number, from_addr, to_addr, value, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tx_hash, seed_chain, block_number, from_addr, to_addr, value, timestamp),
                )
                if conn.total_changes > before:
                    tx_inserted += 1
                _upsert_wallet(conn, seed_chain, from_addr, timestamp)
                _upsert_wallet(conn, seed_chain, to_addr, timestamp)
                wallets_seen.add((seed_chain, from_addr))
                wallets_seen.add((seed_chain, to_addr))
        conn.commit()
    finally:
        conn.close()

    expansion = expand_labels(chain=chain, min_evidence=2, limit=50000) if expand_after else None
    return {
        "ok": True,
        "chain": _chain_key(chain) if chain else "all",
        "seeds_scanned": len(seeds),
        "tx_seen": tx_seen,
        "tx_inserted": tx_inserted,
        "wallets_seen": len([item for item in wallets_seen if item[1]]),
        "errors": errors[:10],
        "expansion": expansion,
        "policy": "seed-focused explorer ingestion; not a full historical backfill",
    }


__all__ = ["ingest_seed_transactions"]
