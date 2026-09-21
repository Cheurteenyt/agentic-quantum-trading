"""Local on-chain flow summaries.

This module keeps transaction/counterparty aggregation isolated from the larger
RPC engine so we can improve flow normalization without touching ingestion code.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from services.onchain_entities import canonical_entity_name, entity_in_clause


def get_entity_flow_surface_from_db(db_path: str, entity: str, limit: int = 25) -> dict[str, Any]:
    """Summarize local transaction flow for labelled wallets already in wallet_chain_state."""
    entity_name = canonical_entity_name(entity)
    if not entity_name:
        return {"ok": False, "error": "entity_required"}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        entity_clause, entity_params = entity_in_clause("entity", entity_name)
        wallet_rows = conn.execute(
            """
            SELECT chain, address, label, confidence, address_kind
            FROM wallet_chain_state
            WHERE {entity_clause}
            """.format(entity_clause=entity_clause),
            entity_params,
        ).fetchall()
        wallets = {(row["chain"], row["address"]) for row in wallet_rows}
        if not wallets:
            return {
                "ok": True,
                "entity": entity_name,
                "wallets": 0,
                "summary": {"inflow": 0, "outflow": 0, "net_flow": 0, "tx_count": 0},
                "counterparties": [],
                "transfers": [],
                "source_policy": "local transactions table only; no external flow backfill",
            }

        wallet_addresses = {address for _, address in wallets}
        placeholders = ",".join("?" for _ in wallet_addresses)
        tx_rows = conn.execute(
            f"""
            SELECT chain, tx_hash, from_addr, to_addr, value, timestamp
            FROM transactions
            WHERE from_addr IN ({placeholders}) OR to_addr IN ({placeholders})
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            [*wallet_addresses, *wallet_addresses, max(1, min(int(limit or 25) * 10, 1000))],
        ).fetchall()

        inflow = 0.0
        outflow = 0.0
        transfers = []
        counterparties: dict[tuple[str, str], dict[str, Any]] = {}
        for tx in tx_rows:
            chain = tx["chain"]
            from_addr = (tx["from_addr"] or "").lower()
            to_addr = (tx["to_addr"] or "").lower()
            value = float(tx["value"] or 0)
            from_entity = from_addr in wallet_addresses
            to_entity = to_addr in wallet_addresses
            if from_entity and to_entity:
                direction = "internal"
                counterparty = to_addr if from_addr in wallet_addresses else from_addr
            elif to_entity:
                direction = "inflow"
                counterparty = from_addr
                inflow += value
            elif from_entity:
                direction = "outflow"
                counterparty = to_addr
                outflow += value
            else:
                continue
            if counterparty:
                key = (chain, counterparty)
                cp = counterparties.setdefault(
                    key,
                    {"chain": chain, "address": counterparty, "inflow": 0.0, "outflow": 0.0, "tx_count": 0},
                )
                cp["tx_count"] += 1
                if direction == "inflow":
                    cp["inflow"] += value
                elif direction == "outflow":
                    cp["outflow"] += value
            if len(transfers) < limit:
                transfers.append(
                    {
                        "chain": chain,
                        "tx_hash": tx["tx_hash"],
                        "from": from_addr,
                        "to": to_addr,
                        "direction": direction,
                        "value_native": value,
                        "timestamp": tx["timestamp"],
                    }
                )

        cp_rows = sorted(
            counterparties.values(),
            key=lambda item: (item["tx_count"], item["inflow"] + item["outflow"]),
            reverse=True,
        )[: max(1, min(int(limit or 25), 100))]
        for cp in cp_rows:
            cp["net_flow"] = round(cp["inflow"] - cp["outflow"], 8)
            cp["inflow"] = round(cp["inflow"], 8)
            cp["outflow"] = round(cp["outflow"], 8)
        return {
            "ok": True,
            "entity": entity_name,
            "wallets": len(wallets),
            "summary": {
                "inflow": round(inflow, 8),
                "outflow": round(outflow, 8),
                "net_flow": round(inflow - outflow, 8),
                "tx_count": len(tx_rows),
            },
            "counterparties": cp_rows,
            "transfers": transfers,
            "source_policy": "local transactions table only; chain-scoped values are native/token units from stored ingestion",
        }
    finally:
        conn.close()
