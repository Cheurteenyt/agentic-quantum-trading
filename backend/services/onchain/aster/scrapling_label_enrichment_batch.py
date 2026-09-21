from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from services.onchain.core.paths import ARKHAM_CACHE_PATH
from services.onchain.behavioral_evidence_bridge import (
    get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview,
)


ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
SCRAPLING_NORMALIZED_DIR = ARKHAM_CACHE_PATH.parent / "scrapling" / "normalized"


def _clean_address(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if clean.startswith("0x") and len(clean) == 42:
        return clean
    return ""


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _extract_addresses(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.update(match.group(0).lower() for match in ADDRESS_RE.finditer(value))
    elif isinstance(value, dict):
        for item in value.values():
            found.update(_extract_addresses(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_extract_addresses(item))
    return found


def _entity_name(payload: dict[str, Any]) -> str | None:
    for key in ("entity", "profile"):
        section = payload.get(key)
        if isinstance(section, dict):
            name = section.get("name") or section.get("label") or section.get("id") or section.get("slug")
            if name:
                return str(name)
    target = payload.get("target")
    return str(target) if target else None


def _entity_type(payload: dict[str, Any]) -> str | None:
    for key in ("entity", "profile"):
        section = payload.get(key)
        if isinstance(section, dict) and section.get("type"):
            return str(section["type"])
    return None


def _label_from_context(payload: dict[str, Any], address: str) -> str | None:
    entity = _entity_name(payload)
    entity_type = _entity_type(payload)
    for node in _walk(payload):
        if address not in _extract_addresses(node):
            continue
        for key in ("label", "name", "entity", "owner", "title"):
            value = node.get(key)
            if isinstance(value, str) and value.strip() and not _clean_address(value):
                return value.strip()
    if entity and entity_type:
        return f"{entity} {entity_type}"
    return entity


def _snapshot_matches(snapshot_path: Path, payload: dict[str, Any], digest: str, targets: set[str]) -> list[dict[str, Any]]:
    all_addresses = _extract_addresses(payload)
    entity = _entity_name(payload)
    entity_type = _entity_type(payload)
    rows: list[dict[str, Any]] = []
    for address in sorted(targets & all_addresses):
        rows.append(
            {
                "address": address,
                "label_status": "found_in_local_snapshot",
                "label": _label_from_context(payload, address),
                "entity": entity,
                "entity_type": entity_type,
                "source_file": str(snapshot_path),
                "snapshot_sha256": digest,
                "source_policy": "local_snapshots_only",
            }
        )
    return rows


def _addresses_from_candidate_payload(value: Any) -> set[str]:
    addresses = _extract_addresses(value)
    return {address for address in addresses if address != "0x0000000000000000000000000000000000000000"}


def _collect_behavioral_candidate_addresses(
    chain: str,
    limit: int,
    min_behavioral_score: int,
) -> tuple[set[str], list[dict[str, Any]], list[str]]:
    scoring = get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
        chain=chain,
        limit=min(limit, 10),
        dry_run=True,
    )
    blockers = list(scoring.get("blockers") or [])
    candidates: list[dict[str, Any]] = []
    targets: set[str] = set()
    for row in scoring.get("candidates") or []:
        score = _as_int(row.get("behavioral_anomaly_score"))
        if score <= min_behavioral_score:
            continue
        candidate_addresses = _addresses_from_candidate_payload(row)
        targets.update(candidate_addresses)
        candidates.append(
            {
                "chain": row.get("chain"),
                "pool_address": row.get("pool_address"),
                "behavioral_anomaly_score": score,
                "address_count_from_candidate_payload": len(candidate_addresses),
            }
        )
    if not targets and not blockers:
        blockers.append("no_behavioral_candidates_above_threshold")
    return targets, candidates, blockers


def _read_snapshots(snapshot_dir: Path, max_files: int) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    snapshots: list[dict[str, Any]] = []
    if not snapshot_dir.exists():
        return [], ["local_scrapling_normalized_dir_missing"]
    files = sorted(path for path in snapshot_dir.glob("*.json") if path.is_file())[:max_files]
    if not files:
        return [], ["no_local_scrapling_normalized_snapshots"]
    for path in files:
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict):
                snapshots.append({"path": path, "payload": payload, "digest": _sha256_bytes(raw)})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            blockers.append(f"snapshot_read_failed:{path.name}:{type(exc).__name__}")
    return snapshots, blockers


def get_scrapling_label_enrichment_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    min_behavioral_score: int = 60,
    max_snapshot_files: int = 100,
    dry_run: bool = True,
    snapshot_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Preview labels from existing Scrapling normalized snapshots only."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_min_score = max(1, min(int(min_behavioral_score or 60), 100))
    safe_max_files = max(1, min(int(max_snapshot_files or 100), 500))
    normalized_dir = Path(snapshot_dir) if snapshot_dir is not None else SCRAPLING_NORMALIZED_DIR
    disabled = {
        "source_policy": "local_snapshots_only",
        "would_scrape": False,
        "would_call_external": False,
        "would_persist_evidence": False,
        "would_apply_label_source": False,
        "would_create_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_write": False,
        "writes_performed": 0,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "preview_status": "blocked",
            "blockers": ["dry_run_required"],
            "enrichment_rows": [],
            **disabled,
        }

    targets, candidates, target_blockers = _collect_behavioral_candidate_addresses(
        clean_chain,
        clean_limit,
        safe_min_score,
    )
    snapshots, snapshot_blockers = _read_snapshots(normalized_dir, safe_max_files)
    matches: dict[str, list[dict[str, Any]]] = {address: [] for address in targets}
    for snapshot in snapshots:
        for row in _snapshot_matches(snapshot["path"], snapshot["payload"], snapshot["digest"], targets):
            matches.setdefault(row["address"], []).append(row)

    rows: list[dict[str, Any]] = []
    for address in sorted(targets):
        found = matches.get(address) or []
        if found:
            best = found[0]
            rows.append({**best, "local_snapshot_matches": len(found)})
        else:
            rows.append(
                {
                    "address": address,
                    "label_status": "not_found_in_local_snapshots",
                    "label": None,
                    "entity": None,
                    "entity_type": None,
                    "source_file": None,
                    "snapshot_sha256": None,
                    "source_policy": "local_snapshots_only",
                    "local_snapshot_matches": 0,
                }
            )
    blockers = list(dict.fromkeys([*target_blockers, *snapshot_blockers]))
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready" if rows else "blocked",
        "chain": clean_chain,
        "min_behavioral_score": safe_min_score,
        "snapshot_dir": str(normalized_dir),
        "snapshots_read": len(snapshots),
        "target_addresses": len(targets),
        "matches_found": sum(1 for row in rows if row["label_status"] == "found_in_local_snapshot"),
        "candidates": candidates,
        "enrichment_rows": rows,
        "blockers": blockers,
        **disabled,
    }
