from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
ARKHAM_DIR = BACKEND_DIR / "data" / "arkham"
SCRAPLING_DIR = ARKHAM_DIR / "scrapling"
SCRAPLING_NORMALIZED_DIR = SCRAPLING_DIR / "normalized"
MANUAL_LABELS_PATH = ARKHAM_DIR / "manual" / "verified_entity_labels.json"
CACHE_PATH = ARKHAM_DIR / "cache.json"
LABEL_LEDGER_DB_PATH = ARKHAM_DIR / "label_ledger.db"

PUBLIC_SOURCE_MARKERS = ("etherscan", "blockscout", "zerion", "cielo")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _safe_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iso_from_mtime(path: Path | None) -> str | None:
    if not path:
        return None
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"
    except Exception:
        return None


def _scan_files(root: Path, pattern: str = "*.json", limit: int = 20) -> dict[str, Any]:
    files = sorted(root.glob(pattern)) if root.exists() else []
    files = [path for path in files if path.is_file()]
    latest = max(files, key=lambda path: path.stat().st_mtime, default=None)
    return {
        "path": str(root),
        "exists": root.exists(),
        "file_count": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "latest_file": latest.name if latest else None,
        "latest_modified_at": _iso_from_mtime(latest),
        "samples": [path.name for path in files[: max(0, min(int(limit or 20), 100))]],
    }


def _cache_summary(path: Path) -> dict[str, Any]:
    payload = _safe_json(path)
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "modified_at": _iso_from_mtime(path) if path.exists() else None,
        "ok": isinstance(payload, dict),
        "counts": {},
    }
    if not isinstance(payload, dict):
        return summary

    for key in (
        "entities",
        "addresses",
        "entities_search_cache",
        "holders_cache",
        "exchange_wallets",
        "token_detail_cache",
    ):
        value = payload.get(key)
        if isinstance(value, dict):
            summary["counts"][key] = len(value)
        elif isinstance(value, list):
            summary["counts"][key] = len(value)
        elif value is not None:
            summary["counts"][key] = 1
        else:
            summary["counts"][key] = 0
    summary["metadata"] = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return summary


def _manual_label_summary(path: Path, limit: int) -> dict[str, Any]:
    payload = _safe_json(path)
    labels = payload.get("labels") if isinstance(payload, dict) else []
    if not isinstance(labels, list):
        labels = []

    by_entity: Counter[str] = Counter()
    by_chain: Counter[str] = Counter()
    for row in labels:
        if not isinstance(row, dict):
            continue
        by_entity[str(row.get("entity") or "unknown")] += 1
        by_chain[str(row.get("chain") or "unknown")] += 1

    limit = max(0, min(int(limit or 20), 100))
    return {
        "path": str(path),
        "exists": path.exists(),
        "generated_at": payload.get("generated_at") if isinstance(payload, dict) else None,
        "policy": payload.get("policy") if isinstance(payload, dict) else None,
        "labels": len(labels),
        "by_entity": [{"entity": key, "labels": count} for key, count in by_entity.most_common(limit)],
        "by_chain": [{"chain": key, "labels": count} for key, count in by_chain.most_common(limit)],
        "samples": labels[:limit],
    }


def _source_name(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("source") or "unknown").strip().lower() or "unknown"
    return str(entry or "unknown").strip().lower() or "unknown"


def _ledger_summary(path: Path, limit: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "modified_at": _iso_from_mtime(path) if path.exists() else None,
        "ok": False,
        "tables": [],
        "labels": 0,
        "derived_labels": 0,
        "label_candidates": 0,
        "label_candidate_evidence": 0,
        "strict_source_labels": 0,
        "legacy_or_unverified_labels": 0,
        "candidate_sources": [],
        "top_entities": [],
        "blockers": [],
    }
    if not path.exists():
        report["blockers"].append("label_ledger_missing")
        return report

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
    except Exception as exc:
        report["blockers"].append(f"label_ledger_open_failed:{exc}")
        return report

    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for table in tables:
            try:
                count = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except Exception:
                count = 0
            report["tables"].append({"name": table, "rows": count})
            if table in report:
                report[table] = count

        if "labels" in tables:
            trusted = 0
            legacy = 0
            entity_counts: Counter[str] = Counter()
            for sources_json, entity in conn.execute("SELECT sources_json, entity FROM labels").fetchall():
                entity_counts[str(entity or "unknown")] += 1
                try:
                    sources = json.loads(sources_json or "[]")
                except Exception:
                    sources = []
                source_names = {_source_name(source) for source in sources} or {"unknown"}
                source_text = " ".join(source_names)
                is_strict = (
                    any(name.startswith("candidate_promotion:") for name in source_names)
                    or "manual_verified" in source_text
                    or any(marker in source_text for marker in PUBLIC_SOURCE_MARKERS)
                )
                if is_strict:
                    trusted += 1
                else:
                    legacy += 1
            report["strict_source_labels"] = trusted
            report["legacy_or_unverified_labels"] = legacy
            report["top_entities"] = [
                {"entity": key, "labels": count}
                for key, count in entity_counts.most_common(max(0, min(int(limit or 20), 100)))
            ]

        if "label_candidates" in tables:
            report["candidate_sources"] = [
                {"source": row[0] or "unknown", "candidates": int(row[1] or 0)}
                for row in conn.execute(
                    """
                    SELECT source, COUNT(*)
                    FROM label_candidates
                    GROUP BY source
                    ORDER BY COUNT(*) DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(limit or 20), 100)),),
                ).fetchall()
            ]
        report["ok"] = True
        return report
    finally:
        conn.close()


def _source_layers(ledger: dict[str, Any], manual: dict[str, Any], cache: dict[str, Any]) -> list[dict[str, Any]]:
    strict_labels = int(ledger.get("strict_source_labels") or 0)
    manual_labels = int(manual.get("labels") or 0)
    candidates = int(ledger.get("label_candidates") or 0)
    candidate_evidence = int(ledger.get("label_candidate_evidence") or 0)
    cache_addresses = int((cache.get("counts") or {}).get("addresses") or 0)

    return [
        {
            "layer": "label_ledger",
            "role": "source_backed_registry",
            "usable_for_core_equity": strict_labels > 0,
            "trust_level": "trusted_when_strict_source_labels",
            "observed": {
                "strict_source_labels": strict_labels,
                "legacy_or_unverified_labels": int(ledger.get("legacy_or_unverified_labels") or 0),
                "label_candidates": candidates,
                "label_candidate_evidence": candidate_evidence,
            },
            "policy": "Use strict source labels and candidate evidence as the main local identity registry.",
        },
        {
            "layer": "manual_verified_labels",
            "role": "public_source_seed",
            "usable_for_core_equity": manual_labels > 0,
            "trust_level": "trusted_seed",
            "observed": {"manual_verified_labels": manual_labels},
            "policy": "Manual public-source labels can seed the ledger, but still do not imply labels/trades by themselves.",
        },
        {
            "layer": "scrapling_normalized_snapshots",
            "role": "arkham_ui_observed_hint",
            "usable_for_core_equity": False,
            "trust_level": "hint_only_until_corroborated",
            "policy": "Useful to find entities and addresses, not enough for final labels without public-source corroboration.",
        },
        {
            "layer": "arkham_cache_json",
            "role": "legacy_cache_hint",
            "usable_for_core_equity": False,
            "trust_level": "hint_only",
            "observed": {"cached_addresses": cache_addresses},
            "policy": "Do not treat old cache rows as proof unless rebound to source/digest/public corroboration.",
        },
        {
            "layer": "arkham_scraper",
            "role": "external_collector",
            "usable_for_core_equity": False,
            "trust_level": "disabled_by_default",
            "policy": "Can collect later only under an explicit bounded acquisition goal; never as autonomous operator.",
        },
        {
            "layer": "arkham_tracker",
            "role": "live_signal_layer",
            "usable_for_core_equity": False,
            "trust_level": "disabled_for_label_or_trade_decisions",
            "policy": "Signals may help research later, but cannot create labels, mappings, trades, or client actions.",
        },
    ]


def get_arkham_source_backed_inventory(limit: int = 20, dry_run: bool = True) -> dict[str, Any]:
    """Read-only inventory of Arkham-related local data and proof readiness."""
    limit = max(1, min(int(limit or 20), 100))
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "inventory_status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write": False,
            "writes_performed": 0,
            "source_policy": "read-only inventory only; rerun with dry_run=true",
        }

    normalized = _scan_files(SCRAPLING_NORMALIZED_DIR, "*.json", limit=limit)
    scrapling_raw = _scan_files(SCRAPLING_DIR, "*.json", limit=limit)
    cache = _cache_summary(CACHE_PATH)
    manual = _manual_label_summary(MANUAL_LABELS_PATH, limit=limit)
    ledger = _ledger_summary(LABEL_LEDGER_DB_PATH, limit=limit)

    blockers: list[str] = []
    if not ledger.get("exists"):
        blockers.append("label_ledger_missing")
    if not manual.get("exists"):
        blockers.append("manual_verified_labels_missing")
    if not normalized.get("exists"):
        blockers.append("scrapling_normalized_missing")

    strict_labels = int(ledger.get("strict_source_labels") or 0)
    candidate_evidence = int(ledger.get("label_candidate_evidence") or 0)
    status = "ready_for_source_backed_planning" if strict_labels or candidate_evidence else "needs_source_backed_seed"

    return {
        "ok": True,
        "dry_run": True,
        "inventory_status": status,
        "observed_at": _utc_now(),
        "summary": {
            "strict_source_labels": strict_labels,
            "legacy_or_unverified_labels": int(ledger.get("legacy_or_unverified_labels") or 0),
            "label_candidates": int(ledger.get("label_candidates") or 0),
            "label_candidate_evidence": candidate_evidence,
            "manual_verified_labels": int(manual.get("labels") or 0),
            "normalized_snapshots": int(normalized.get("file_count") or 0),
            "raw_scrapling_snapshots": int(scrapling_raw.get("file_count") or 0),
            "arkham_cache_addresses": int((cache.get("counts") or {}).get("addresses") or 0),
        },
        "artifacts": {
            "label_ledger": ledger,
            "manual_verified_labels": manual,
            "scrapling_normalized": normalized,
            "scrapling_raw": scrapling_raw,
            "arkham_cache": cache,
        },
        "source_layers": _source_layers(ledger, manual, cache),
        "core_equity_usage": {
            "preferred": "label_ledger strict_source_labels plus persisted candidate evidence",
            "allowed_as_hints": ["scrapling_normalized_snapshots", "arkham_cache_json"],
            "disabled_by_default": ["arkham_scraper", "arkham_tracker", "external_provider_calls"],
            "next_safe_step": "Build a source-backed evidence intake that imports only corroborated rows, not labels.",
        },
        "would_call_external_provider": False,
        "would_scrape": False,
        "would_create_label_candidate": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_execute_trade": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "blockers": blockers,
        "source_policy": (
            "Read-only Arkham inventory. Local source-backed ledger is preferred; "
            "Scrapling/cache are hints only; scraper/tracker remain disabled for Core Equity writes."
        ),
    }


__all__ = ["get_arkham_source_backed_inventory"]
