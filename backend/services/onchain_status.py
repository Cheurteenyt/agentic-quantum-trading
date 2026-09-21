"""Read-only on-chain RPC/data status payloads."""

from __future__ import annotations

import sqlite3
from typing import Any


def get_rpc_status_from_db(
    db_path: str,
    chains: dict[str, dict[str, Any]],
    max_tx_per_block: int,
    auto_ingest_running: bool,
) -> dict[str, Any]:
    """Return read-only RPC configuration metadata without exposing secrets."""
    conn = sqlite3.connect(str(db_path))
    db_tables: list[dict[str, Any]] = []
    try:
        for table in ("blocks", "transactions", "swaps", "wallets", "wallet_chain_state"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            db_tables.append({"name": table, "rows": count})
        wallet_state_by_chain = {
            row[0]: row[1]
            for row in conn.execute("SELECT chain, COUNT(*) FROM wallet_chain_state GROUP BY chain").fetchall()
        }
    finally:
        conn.close()

    return {
        "ok": True,
        "chains": chains,
        "db_path": str(db_path),
        "db_tables": db_tables,
        "wallet_chain_state": wallet_state_by_chain,
        "max_tx_per_block": max_tx_per_block,
        "auto_ingest_running": auto_ingest_running,
    }
