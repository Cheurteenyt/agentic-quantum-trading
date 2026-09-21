from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from services.label_ledger import DB_PATH as LABEL_DB_PATH
from services.label_ledger import _chain_key, _init_db
from services.onchain.core.paths import DB_PATH as ONCHAIN_DB_PATH

SCRAPLING_NORMALIZED_DIR = Path(__file__).resolve().parents[1] / "data" / "arkham" / "scrapling" / "normalized"


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _confidence_from_count(count: int) -> str:
    if count >= 20:
        return "medium"
    if count >= 3:
        return "low"
    return "watch"


def _relation_label(entity: str, relation_type: str) -> str:
    entity_name = entity or "Unknown"
    if relation_type == "direct_counterparty":
        return f"{entity_name}: recurring counterparty"
    if relation_type == "swap_counterparty":
        return f"{entity_name}: swap-adjacent wallet"
    return f"{entity_name}: related wallet"


def _insert_derived(
    conn: sqlite3.Connection,
    *,
    chain: str,
    address: str,
    entity: str,
    relation_type: str,
    evidence: list[dict[str, Any]],
    source: str,
) -> bool:
    address = str(address or "").strip().lower()
    chain = _chain_key(chain)
    if not address or not entity:
        return False
    if len(evidence) < 2:
        return False

    label = _relation_label(entity, relation_type)
    confidence = _confidence_from_count(len(evidence))
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO derived_labels (
            chain, address, derived_label, related_entity, relation_type, confidence,
            evidence_count, evidence_json, source, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chain, address, derived_label, relation_type) DO UPDATE SET
            confidence = excluded.confidence,
            evidence_count = excluded.evidence_count,
            evidence_json = excluded.evidence_json,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (
            chain,
            address,
            label,
            entity,
            relation_type,
            confidence,
            len(evidence),
            json.dumps(evidence[:50], ensure_ascii=False),
            source,
            now,
        ),
    )
    return True


def _load_seed_labels(conn: sqlite3.Connection, chain: str | None) -> dict[tuple[str, str], dict[str, Any]]:
    where = "WHERE confidence = 'high'"
    params: list[Any] = []
    if chain:
        where += " AND chain = ?"
        params.append(_chain_key(chain))
    rows = conn.execute(
        f"SELECT chain, address, label, entity, flags_json FROM labels {where}",
        params,
    ).fetchall()
    seeds: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        seed_chain, address, label, entity, flags_json = row
        try:
            flags = json.loads(flags_json or "[]")
        except Exception:
            flags = []
        seeds[(_chain_key(seed_chain), str(address).lower())] = {
            "chain": _chain_key(seed_chain),
            "address": str(address).lower(),
            "label": label,
            "entity": entity,
            "flags": flags,
        }
    return seeds


def expand_labels_from_onchain(chain: str | None = None, min_evidence: int = 2, limit: int = 5000) -> dict[str, Any]:
    """Derive low/medium-confidence labels from local on-chain transactions/swaps."""
    _init_db()
    if not Path(ONCHAIN_DB_PATH).exists():
        return {"ok": False, "error": "onchain_db_missing", "db_path": str(ONCHAIN_DB_PATH)}

    min_evidence = max(2, int(min_evidence or 2))
    limit = max(100, min(int(limit or 5000), 50000))

    label_conn = sqlite3.connect(str(LABEL_DB_PATH))
    onchain_conn = sqlite3.connect(str(ONCHAIN_DB_PATH))
    try:
        seeds = _load_seed_labels(label_conn, chain)
        if not seeds:
            return {"ok": True, "seed_count": 0, "derived": 0, "message": "no_high_confidence_seed_labels"}

        evidence: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        chain_filter = _chain_key(chain) if chain else None
        tx_params: list[Any] = []
        tx_where = ""
        if chain_filter:
            if chain_filter == "ethereum":
                tx_where = "WHERE chain IN (?, ?)"
                tx_params.extend(["ethereum", "eth"])
            else:
                tx_where = "WHERE chain = ?"
                tx_params.append(chain_filter)

        for tx_hash, tx_chain, block_number, from_addr, to_addr, value, timestamp in onchain_conn.execute(
            f"""
            SELECT tx_hash, chain, block_number, from_addr, to_addr, value, timestamp
            FROM transactions
            {tx_where}
            ORDER BY block_number DESC
            LIMIT ?
            """,
            [*tx_params, limit],
        ).fetchall():
            normalized_chain = _chain_key(tx_chain)
            parties = [str(from_addr or "").lower(), str(to_addr or "").lower()]
            for side_idx, seed_addr in enumerate(parties):
                seed = seeds.get((normalized_chain, seed_addr))
                if not seed:
                    continue
                counterparty = parties[1 - side_idx]
                if not counterparty or counterparty == seed_addr:
                    continue
                key = (normalized_chain, counterparty, seed["entity"], "direct_counterparty")
                evidence[key].append({
                    "tx_hash": tx_hash,
                    "block_number": block_number,
                    "direction": "to_seed" if side_idx == 1 else "from_seed",
                    "seed_address": seed_addr,
                    "seed_label": seed["label"],
                    "value": value,
                    "timestamp": timestamp,
                })

        for tx_hash, swap_chain, block_number, wallet, dex, amount_usd, pool in onchain_conn.execute(
            """
            SELECT tx_hash, chain, block_number, wallet, dex, amount_usd, pool
            FROM swaps
            ORDER BY block_number DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall():
            normalized_chain = _chain_key(swap_chain)
            if chain_filter and normalized_chain != chain_filter:
                continue
            pool_key = (normalized_chain, str(pool or "").lower())
            wallet_addr = str(wallet or "").lower()
            seed = seeds.get(pool_key)
            if not seed or not wallet_addr or wallet_addr == seed["address"]:
                continue
            key = (normalized_chain, wallet_addr, seed["entity"], "swap_counterparty")
            evidence[key].append({
                "tx_hash": tx_hash,
                "block_number": block_number,
                "seed_address": seed["address"],
                "seed_label": seed["label"],
                "dex": dex,
                "amount_usd": amount_usd,
            })

        inserted = 0
        evidence_histogram = Counter()
        for (derived_chain, address, entity, relation_type), rows in evidence.items():
            if len(rows) < min_evidence:
                continue
            evidence_histogram[min(len(rows), 20)] += 1
            inserted += int(_insert_derived(
                label_conn,
                chain=derived_chain,
                address=address,
                entity=entity,
                relation_type=relation_type,
                evidence=rows,
                source="onchain_local_expansion",
            ))
        label_conn.commit()

        derived_total = label_conn.execute("SELECT COUNT(*) FROM derived_labels").fetchone()[0]
        top_entities = [
            {"entity": row[0] or "unknown", "derived_labels": row[1]}
            for row in label_conn.execute(
                "SELECT related_entity, COUNT(*) FROM derived_labels GROUP BY related_entity ORDER BY COUNT(*) DESC LIMIT 12"
            ).fetchall()
        ]
        return {
            "ok": True,
            "seed_count": len(seeds),
            "candidate_edges": len(evidence),
            "derived_inserted_or_updated": inserted,
            "derived_total": derived_total,
            "min_evidence": min_evidence,
            "top_entities": top_entities,
            "evidence_histogram": dict(evidence_histogram),
            "policy": "derived labels are never treated as high-confidence entity labels without external confirmation",
        }
    finally:
        label_conn.close()
        onchain_conn.close()


def expand_labels_from_scrapling_transfers(chain: str | None = None, min_evidence: int = 2) -> dict[str, Any]:
    """Derive relation labels from normalized Scrapling transfer/counterparty snapshots."""
    _init_db()
    min_evidence = max(2, int(min_evidence or 2))
    chain_filter = _chain_key(chain) if chain else None
    files = sorted(SCRAPLING_NORMALIZED_DIR.glob("*.json")) if SCRAPLING_NORMALIZED_DIR.exists() else []

    conn = sqlite3.connect(str(LABEL_DB_PATH))
    try:
        seeds = _load_seed_labels(conn, chain)
        seed_by_chain_addr = {(seed["chain"], seed["address"]): seed for seed in seeds.values()}
        evidence: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)

        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            generated_at = payload.get("generated_at")
            for transfer in payload.get("transfers") or []:
                if not isinstance(transfer, dict):
                    continue
                base_chain = _chain_key(str(transfer.get("chain") or transfer.get("from_chain") or transfer.get("to_chain") or "unknown"))
                from_addr = str(transfer.get("from") or "").strip().lower()
                to_addr = str(transfer.get("to") or "").strip().lower()
                parties = [
                    (_chain_key(str(transfer.get("from_chain") or base_chain)), from_addr, "from"),
                    (_chain_key(str(transfer.get("to_chain") or base_chain)), to_addr, "to"),
                ]
                for seed_chain, seed_addr, seed_side in parties:
                    if seed_chain == "unknown":
                        continue
                    if chain_filter and seed_chain != chain_filter:
                        continue
                    seed = seed_by_chain_addr.get((seed_chain, seed_addr))
                    if not seed:
                        continue
                    for counter_chain, counter_addr, counter_side in parties:
                        if counter_chain == "unknown":
                            continue
                        if counter_addr == seed_addr or not counter_addr:
                            continue
                        if chain_filter and counter_chain != chain_filter:
                            continue
                        key = (counter_chain, counter_addr, seed["entity"], "scrapling_transfer_counterparty")
                        evidence[key].append({
                            "file": path.name,
                            "generated_at": generated_at,
                            "seed_side": seed_side,
                            "counterparty_side": counter_side,
                            "seed_address": seed_addr,
                            "seed_label": seed["label"],
                            "value_usd": transfer.get("value_usd"),
                            "token": transfer.get("token_symbol"),
                            "tx_hash": transfer.get("tx_hash"),
                        })

            for counterparty in payload.get("counterparties") or []:
                if not isinstance(counterparty, dict):
                    continue
                address = str(counterparty.get("address") or "").strip().lower()
                counter_chain = _chain_key(str(counterparty.get("chain") or "unknown"))
                label = str(counterparty.get("label") or "")
                if not address or counter_chain == "unknown":
                    continue
                for seed in seeds.values():
                    if chain_filter and seed["chain"] != chain_filter:
                        continue
                    if seed["entity"] and seed["entity"].lower() in label.lower():
                        key = (counter_chain, address, seed["entity"], "scrapling_named_counterparty")
                        evidence[key].append({
                            "file": path.name,
                            "generated_at": generated_at,
                            "counterparty_label": label,
                            "value_usd": counterparty.get("value_usd"),
                        })

        inserted = 0
        evidence_histogram = Counter()
        for (derived_chain, address, entity, relation_type), rows in evidence.items():
            if len(rows) < min_evidence:
                continue
            evidence_histogram[min(len(rows), 20)] += 1
            inserted += int(_insert_derived(
                conn,
                chain=derived_chain,
                address=address,
                entity=entity,
                relation_type=relation_type,
                evidence=rows,
                source="scrapling_transfer_expansion",
            ))
        conn.commit()
        derived_total = conn.execute("SELECT COUNT(*) FROM derived_labels").fetchone()[0]
        top_entities = [
            {"entity": row[0] or "unknown", "derived_labels": row[1]}
            for row in conn.execute(
                "SELECT related_entity, COUNT(*) FROM derived_labels GROUP BY related_entity ORDER BY COUNT(*) DESC LIMIT 12"
            ).fetchall()
        ]
        return {
            "ok": True,
            "files_scanned": len(files),
            "seed_count": len(seeds),
            "candidate_edges": len(evidence),
            "derived_inserted_or_updated": inserted,
            "derived_total": derived_total,
            "min_evidence": min_evidence,
            "top_entities": top_entities,
            "evidence_histogram": dict(evidence_histogram),
            "policy": "scrapling-derived labels remain low/medium confidence until confirmed by labels or RPC",
        }
    finally:
        conn.close()


def expand_labels(chain: str | None = None, min_evidence: int = 2, limit: int = 5000) -> dict[str, Any]:
    rpc_result = expand_labels_from_onchain(chain=chain, min_evidence=min_evidence, limit=limit)
    scrapling_result = expand_labels_from_scrapling_transfers(chain=chain, min_evidence=min_evidence)
    return {
        "ok": bool(rpc_result.get("ok") and scrapling_result.get("ok")),
        "rpc": rpc_result,
        "scrapling": scrapling_result,
        "derived_total": max(int(rpc_result.get("derived_total") or 0), int(scrapling_result.get("derived_total") or 0)),
    }


__all__ = ["expand_labels", "expand_labels_from_onchain", "expand_labels_from_scrapling_transfers"]
