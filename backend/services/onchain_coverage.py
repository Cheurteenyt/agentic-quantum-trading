"""Local labelled-vs-RPC coverage summaries."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from services.onchain_chains import normalize_chain
from services.onchain_entities import canonical_entity_name, entity_in_clause
from services.onchain_quality import confidence_allows


EVM_COVERAGE_CHAINS = {"eth", "bsc", "polygon", "base", "arbitrum"}
DEFAULT_PRIORITY_ENTITIES = (
    "Binance",
    "OKX",
    "Coinbase",
    "Kraken",
    "BlackRock",
    "PancakeSwap",
    "Uniswap",
    "Polymarket",
    "Bitget",
    "KuCoin",
)


STRICT_SOURCE_BUCKETS = {"manual_verified", "candidate_promotion", "external_public"}
LEGACY_SOURCE_BUCKETS = {"legacy_scrapling", "legacy_local_seed", "unknown"}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _source_names(value: Any) -> list[str]:
    names: list[str] = []
    for item in _json_list(value):
        if isinstance(item, dict):
            name = str(item.get("source") or "unknown").strip()
        else:
            name = str(item or "unknown").strip()
        if name and name not in names:
            names.append(name)
    return names or ["unknown"]


def _source_bucket(source_names: list[str]) -> str:
    lowered = " ".join(source_names).lower()
    if any(name.startswith("candidate_promotion:") for name in source_names):
        return "candidate_promotion"
    if "manual_verified" in lowered:
        return "manual_verified"
    if any(public in lowered for public in ("etherscan", "blockscout", "zerion", "cielo")):
        return "external_public"
    if "scrapling" in lowered:
        return "legacy_scrapling"
    if "entity_labels_legacy" in lowered:
        return "legacy_local_seed"
    return "unknown"


def _new_coverage_entry(entity: str) -> dict[str, Any]:
    return {
        "entity": entity,
        "labelled_wallets": 0,
        "strict_labelled_wallets": 0,
        "legacy_or_unverified_labelled_wallets": 0,
        "labelled_by_chain": {},
        "strict_labelled_by_chain": {},
        "legacy_labelled_by_chain": {},
        "confidence_breakdown": {},
        "label_source_breakdown": {},
        "sample_labels": [],
    }


def get_rpc_entity_coverage_from_dbs(
    db_path: str,
    label_ledger_path: str,
    entity_labels_path: str,
    entity: str | None = None,
    limit: int = 50,
    min_confidence: str = "medium",
) -> dict[str, Any]:
    """Summarize labelled-vs-RPC-enriched coverage by entity."""
    label_rows: list[dict[str, Any]] = []
    if label_ledger_path and Path(label_ledger_path).exists():
        label_conn = sqlite3.connect(str(label_ledger_path))
        try:
            params: list[Any] = []
            where = "WHERE address LIKE '0x%'"
            if entity:
                clause, clause_params = entity_in_clause("entity", entity)
                where += f" AND {clause}"
                params.extend(clause_params)
            label_rows = label_conn.execute(
                f"""
                SELECT chain, address, label, entity, confidence, sources_json
                FROM labels
                {where}
                """,
                params,
            ).fetchall()
            label_rows = [
                {
                    "chain": row[0],
                    "address": row[1],
                    "label": row[2],
                    "entity": row[3],
                    "confidence": row[4],
                    "source_names": _source_names(row[5]),
                }
                for row in label_rows
            ]
        finally:
            label_conn.close()

    if entity_labels_path and Path(entity_labels_path).exists():
        entity_conn = sqlite3.connect(str(entity_labels_path))
        try:
            params = []
            where = "WHERE wallet_address LIKE '0x%'"
            if entity:
                clause, clause_params = entity_in_clause("entity_name", entity)
                where += f" AND {clause}"
                params.extend(clause_params)
            rows = entity_conn.execute(
                f"""
                SELECT chain, wallet_address, wallet_type, entity_name, confidence
                FROM entity_labels
                {where}
                """,
                params,
            ).fetchall()
            for row in rows:
                label = f"{row[3]}: {row[2]}" if row[3] and row[2] else row[3] or row[2]
                confidence = "high" if float(row[4] or 0) >= 0.9 else "medium"
                label_rows.append(
                    {
                        "chain": row[0],
                        "address": row[1],
                        "label": label,
                        "entity": row[3],
                        "confidence": confidence,
                        "source_names": ["entity_labels_legacy"],
                    }
                )
        finally:
            entity_conn.close()

    labelled: dict[str, dict[str, Any]] = {}
    seen_labels: set[tuple[str, str, str]] = set()
    for row in label_rows:
        chain = row.get("chain")
        address = row.get("address")
        label = row.get("label")
        row_entity = row.get("entity")
        confidence = row.get("confidence")
        normalized_chain = normalize_chain(chain)
        if normalized_chain not in EVM_COVERAGE_CHAINS:
            continue
        if not confidence_allows(confidence, min_confidence):
            continue
        wallet = str(address or "").lower()
        key = canonical_entity_name(row_entity) or "Unknown"
        dedupe_key = (key.lower(), normalized_chain, wallet)
        if dedupe_key in seen_labels:
            continue
        seen_labels.add(dedupe_key)
        entry = labelled.setdefault(key, _new_coverage_entry(key))
        source_names = row.get("source_names") or ["unknown"]
        bucket = _source_bucket(source_names)
        entry["labelled_wallets"] += 1
        entry["labelled_by_chain"][normalized_chain] = entry["labelled_by_chain"].get(normalized_chain, 0) + 1
        entry["confidence_breakdown"][confidence] = entry["confidence_breakdown"].get(confidence, 0) + 1
        entry["label_source_breakdown"][bucket] = entry["label_source_breakdown"].get(bucket, 0) + 1
        if bucket in STRICT_SOURCE_BUCKETS:
            entry["strict_labelled_wallets"] += 1
            entry["strict_labelled_by_chain"][normalized_chain] = (
                entry["strict_labelled_by_chain"].get(normalized_chain, 0) + 1
            )
        else:
            entry["legacy_or_unverified_labelled_wallets"] += 1
            entry["legacy_labelled_by_chain"][normalized_chain] = (
                entry["legacy_labelled_by_chain"].get(normalized_chain, 0) + 1
            )
        if len(entry["sample_labels"]) < 5:
            entry["sample_labels"].append(
                {
                    "chain": normalized_chain,
                    "address": wallet,
                    "label": label,
                    "confidence": confidence,
                    "source_bucket": bucket,
                    "source_names": source_names,
                }
            )

    state_params: list[Any] = []
    state_where = ""
    if entity:
        clause, clause_params = entity_in_clause("entity", entity)
        state_where = f"WHERE {clause}"
        state_params.extend(clause_params)
    conn = sqlite3.connect(str(db_path))
    try:
        state_rows = conn.execute(
            f"""
            SELECT entity, chain, COUNT(*) AS wallet_count,
                   SUM(native_balance) AS native_balance,
                   SUM(tx_count) AS tx_count,
                   MAX(observed_at) AS last_observed_at,
                   SUM(native_value_usd) AS native_value_usd,
                   SUM(CASE WHEN is_contract = 1 THEN 1 ELSE 0 END) AS contract_count,
                   SUM(CASE WHEN activity_tier = 'fresh' THEN 1 ELSE 0 END) AS fresh_count,
                   SUM(CASE WHEN activity_tier IN ('high_activity', 'hyper_active') THEN 1 ELSE 0 END) AS high_activity_count,
                   AVG(data_quality_score) AS avg_quality_score
            FROM wallet_chain_state
            {state_where}
            GROUP BY entity, chain
            """,
            state_params,
        ).fetchall()
    finally:
        conn.close()

    coverage = labelled
    for (
        row_entity,
        chain,
        wallet_count,
        native_balance,
        tx_count,
        last_observed_at,
        native_value_usd,
        contract_count,
        fresh_count,
        high_activity_count,
        avg_quality_score,
    ) in state_rows:
        key = canonical_entity_name(row_entity) or "Unknown"
        entry = coverage.setdefault(
            key,
            _new_coverage_entry(key),
        )
        rpc_by_chain = entry.setdefault("rpc_by_chain", {})
        rpc_by_chain[chain] = {
            "wallets": int(wallet_count or 0),
            "native_balance": float(native_balance or 0),
            "tx_count": int(tx_count or 0),
            "last_observed_at": int(last_observed_at or 0),
            "native_value_usd": float(native_value_usd or 0),
            "contracts": int(contract_count or 0),
            "fresh_wallets": int(fresh_count or 0),
            "high_activity_wallets": int(high_activity_count or 0),
            "avg_quality_score": round(float(avg_quality_score or 0), 2),
        }

    rows = []
    for entry in coverage.values():
        rpc_by_chain = entry.get("rpc_by_chain", {})
        rpc_wallets = sum(int(item.get("wallets") or 0) for item in rpc_by_chain.values())
        rpc_tx_count = sum(int(item.get("tx_count") or 0) for item in rpc_by_chain.values())
        rpc_native_value_usd = sum(float(item.get("native_value_usd") or 0) for item in rpc_by_chain.values())
        contract_count = sum(int(item.get("contracts") or 0) for item in rpc_by_chain.values())
        fresh_count = sum(int(item.get("fresh_wallets") or 0) for item in rpc_by_chain.values())
        high_activity_count = sum(int(item.get("high_activity_wallets") or 0) for item in rpc_by_chain.values())
        quality_scores = [
            float(item.get("avg_quality_score") or 0)
            for item in rpc_by_chain.values()
            if item.get("wallets")
        ]
        labelled_wallets = int(entry.get("labelled_wallets") or 0)
        strict_labelled_wallets = int(entry.get("strict_labelled_wallets") or 0)
        legacy_labelled_wallets = int(entry.get("legacy_or_unverified_labelled_wallets") or 0)
        entry["rpc_wallets"] = rpc_wallets
        entry["rpc_tx_count"] = rpc_tx_count
        entry["rpc_native_value_usd"] = round(rpc_native_value_usd, 2)
        entry["contract_wallets"] = contract_count
        entry["fresh_wallets"] = fresh_count
        entry["high_activity_wallets"] = high_activity_count
        entry["avg_quality_score"] = round(sum(quality_scores) / max(len(quality_scores), 1), 2) if quality_scores else 0
        entry["rpc_coverage_pct"] = round((rpc_wallets / labelled_wallets) * 100, 2) if labelled_wallets else 0.0
        entry["strict_rpc_coverage_pct"] = (
            round((rpc_wallets / strict_labelled_wallets) * 100, 2) if strict_labelled_wallets else 0.0
        )
        if strict_labelled_wallets:
            entry["label_quality_status"] = "strict_seeded"
        elif legacy_labelled_wallets:
            entry["label_quality_status"] = "legacy_or_unverified_only"
        elif rpc_wallets:
            entry["label_quality_status"] = "rpc_only"
        else:
            entry["label_quality_status"] = "missing_labels"
        rows.append(entry)
    rows.sort(key=lambda item: (item.get("rpc_wallets", 0), item.get("labelled_wallets", 0)), reverse=True)
    source_totals: dict[str, int] = {}
    chain_totals: dict[str, dict[str, int]] = {}
    quality_scores: list[float] = []
    for row in rows:
        for bucket, count in (row.get("label_source_breakdown") or {}).items():
            source_totals[bucket] = source_totals.get(bucket, 0) + int(count or 0)
        for chain, count in (row.get("labelled_by_chain") or {}).items():
            chain_totals.setdefault(chain, {"labelled_wallets": 0, "rpc_wallets": 0})
            chain_totals[chain]["labelled_wallets"] += int(count or 0)
        for chain, rpc_row in (row.get("rpc_by_chain") or {}).items():
            chain_totals.setdefault(chain, {"labelled_wallets": 0, "rpc_wallets": 0})
            chain_totals[chain]["rpc_wallets"] += int((rpc_row or {}).get("wallets") or 0)
        if row.get("rpc_wallets"):
            quality_scores.append(float(row.get("avg_quality_score") or 0))

    labelled_total = sum(int(row.get("labelled_wallets") or 0) for row in rows)
    strict_total = sum(int(row.get("strict_labelled_wallets") or 0) for row in rows)
    rpc_total = sum(int(row.get("rpc_wallets") or 0) for row in rows)
    summary = {
        "coverage_entity_rows": len(rows),
        "labelled_wallets": labelled_total,
        "strict_labelled_wallets": strict_total,
        "legacy_or_unverified_labelled_wallets": sum(
            int(row.get("legacy_or_unverified_labelled_wallets") or 0) for row in rows
        ),
        "rpc_wallets": rpc_total,
        "rpc_tx_count": sum(int(row.get("rpc_tx_count") or 0) for row in rows),
        "rpc_native_value_usd": round(sum(float(row.get("rpc_native_value_usd") or 0) for row in rows), 2),
        "contract_wallets": sum(int(row.get("contract_wallets") or 0) for row in rows),
        "fresh_wallets": sum(int(row.get("fresh_wallets") or 0) for row in rows),
        "high_activity_wallets": sum(int(row.get("high_activity_wallets") or 0) for row in rows),
        "strict_label_pct": round((strict_total / labelled_total) * 100, 2) if labelled_total else 0.0,
        "rpc_coverage_pct": round((rpc_total / labelled_total) * 100, 2) if labelled_total else 0.0,
        "avg_quality_score": round(sum(quality_scores) / max(len(quality_scores), 1), 2) if quality_scores else 0,
        "label_source_breakdown": source_totals,
        "chain_totals": chain_totals,
    }
    rows = rows[: max(1, min(int(limit or 50), 200))]
    summary["displayed_rows"] = len(rows)
    return {
        "ok": True,
        "entity": entity,
        "min_confidence": min_confidence,
        "total_entities": len(coverage),
        "summary": summary,
        "rows": rows,
        "source_policy": (
            "labels from local ledger; rpc_wallets from direct chain RPC state table; "
            "strict_labelled_wallets count only manual, candidate-promoted, or external-public sources"
        ),
    }


def get_entity_gap_report_from_dbs(
    db_path: str,
    label_ledger_path: str,
    entity_labels_path: str,
    priority_entities: list[str] | None = None,
    min_confidence: str = "medium",
) -> dict[str, Any]:
    """Explain which priority entities need labels, RPC enrichment, or quality review."""
    requested = priority_entities or list(DEFAULT_PRIORITY_ENTITIES)
    coverage = get_rpc_entity_coverage_from_dbs(
        db_path,
        label_ledger_path,
        entity_labels_path,
        limit=200,
        min_confidence=min_confidence,
    )
    rows_by_entity = {
        canonical_entity_name(row.get("entity")).lower(): row
        for row in coverage.get("rows", [])
        if row.get("entity")
    }
    gaps: list[dict[str, Any]] = []
    for index, entity in enumerate(requested, start=1):
        canonical = canonical_entity_name(entity) or entity
        row = rows_by_entity.get(canonical.lower(), {})
        labelled = int(row.get("labelled_wallets") or 0)
        strict_labelled = int(row.get("strict_labelled_wallets") or 0)
        legacy_labelled = int(row.get("legacy_or_unverified_labelled_wallets") or 0)
        rpc_wallets = int(row.get("rpc_wallets") or 0)
        rpc_pct = float(row.get("rpc_coverage_pct") or 0.0)
        quality = float(row.get("avg_quality_score") or 0.0)
        if labelled <= 0:
            status = "missing_labels"
            action = "Find a reliable label source before RPC enrichment."
            score = 100
        elif strict_labelled <= 0:
            status = "needs_strict_source"
            action = "Collect or promote strict source-backed labels before trusting this entity."
            score = 95
        elif rpc_wallets <= 0:
            status = "needs_rpc_enrichment"
            action = "Run targeted enrich-labels for this entity."
            score = 90
        elif rpc_wallets < labelled:
            status = "partial_rpc"
            action = "Continue targeted RPC enrichment; avoid bulk ingestion."
            score = max(20, round(100 - rpc_pct, 2))
        elif quality < 45:
            status = "weak_quality"
            action = "Review confidence/source mix before trusting this surface."
            score = 55
        else:
            status = "usable_seed"
            action = "Use as a measured seed; still not Arkham-scale."
            score = 10
        gaps.append(
            {
                "rank": index,
                "entity": canonical,
                "status": status,
                "priority_score": score,
                "labelled_wallets": labelled,
                "strict_labelled_wallets": strict_labelled,
                "legacy_or_unverified_labelled_wallets": legacy_labelled,
                "rpc_wallets": rpc_wallets,
                "rpc_coverage_pct": rpc_pct,
                "strict_rpc_coverage_pct": row.get("strict_rpc_coverage_pct") or 0.0,
                "avg_quality_score": quality,
                "label_quality_status": row.get("label_quality_status"),
                "label_source_breakdown": row.get("label_source_breakdown") or {},
                "labelled_by_chain": row.get("labelled_by_chain") or {},
                "strict_labelled_by_chain": row.get("strict_labelled_by_chain") or {},
                "legacy_labelled_by_chain": row.get("legacy_labelled_by_chain") or {},
                "rpc_by_chain": row.get("rpc_by_chain") or {},
                "sample_labels": row.get("sample_labels") or [],
                "next_action": action,
            }
        )
    gaps.sort(key=lambda item: (item["priority_score"], -item["rank"]), reverse=True)
    return {
        "ok": True,
        "min_confidence": min_confidence,
        "priority_entities": requested,
        "rows": gaps,
        "source_policy": "gap report from local labels + RPC state only; missing labels require external confirmation",
    }
