from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"

JSON_OUT = BASE_DIR / "aster_workspace_file_audit_latest.json"
CSV_OUT = BASE_DIR / "aster_workspace_file_audit_latest.csv"
HTML_OUT = DOCS_DIR / "core-equity-aster-workspace-file-audit.html"

ACTIVE_CORE_SCRIPTS = {
    "backtest_strategy_discovery.py",
    "backtest_aster_v2.py",
    "backtest_priority_watchlist.py",
    "aster_promotion_ready_lanes_report.py",
    "aster_strategy_truth_report.py",
    "aster_promotion_truth_report.py",
    "aster_lane_promotion_scoring.py",
    "aster_candidate_validation_queue.py",
    "aster_volatile_crypto_discovery.py",
    "aster_asset_strategy_recommendations.py",
    "aster_api_capacity_probe.py",
    "aster_strategy_registry.py",
    "aster_microstructure_replay_validator.py",
    "aster_mark_index_replay_filter.py",
}

LEGACY_OR_ARCHIVE_SCRIPTS = {
    "monitor_shorts.py",
    "monitor_multi_strategy.py",
    "monitor_optimized_longs.py",
    "backtest_champion_lanes.py",
    "backtest_reality_checked.py",
    "aster_agent_foundation.py",
    "aster_agent_decision_engine.py",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text_sample(path: Path, limit: int = 700) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _category(path: Path) -> tuple[str, str]:
    name = path.name
    lower = name.lower()
    if path.is_dir():
        if name in {"archive", "data_sources", "research"}:
            return "source_directory", "keep_directory"
        if name == "__pycache__":
            return "runtime_cache", "ignore"
        return "directory", "review"
    if name in ACTIVE_CORE_SCRIPTS:
        return "active_core_script", "keep_root"
    if name in LEGACY_OR_ARCHIVE_SCRIPTS:
        return "legacy_or_research_script", "keep_but_do_not_prioritize"
    if path.suffix == ".py":
        sample = _read_text_sample(path)
        if len(sample) < 500 and "import *" in sample:
            return "compatibility_wrapper", "keep_root_wrapper"
        if name.startswith("dexscreener") or name.startswith("scrapling"):
            return "external_enrichment_legacy", "keep_if_used"
        return "support_script", "review_usage"
    if lower.endswith("_latest.json") or lower.endswith("_latest.csv"):
        return "generated_latest_artifact", "generated_do_not_edit"
    if lower.endswith("_heartbeat.json"):
        return "runner_heartbeat", "generated_do_not_edit"
    if lower.endswith(".csv") and lower.startswith("paper_trading_"):
        return "backtest_csv_artifact", "generated_do_not_edit"
    if lower.endswith(".json") and ("cache" in lower):
        return "public_data_cache", "generated_cache"
    if lower.endswith(".json"):
        return "json_artifact", "generated_or_snapshot"
    if lower.endswith(".md"):
        return "documentation", "keep_documentation"
    return "other", "review"


def _risk_note(path: Path, category: str, size: int) -> str:
    name = path.name.lower()
    notes: list[str] = []
    if size >= 5_000_000:
        notes.append("large_file")
    if "smoke" in name:
        notes.append("smoke_artifact")
    if "legacy_" in name:
        notes.append("legacy_snapshot")
    if category in {"generated_latest_artifact", "backtest_csv_artifact", "public_data_cache"}:
        notes.append("safe_to_regenerate")
    if category == "active_core_script":
        notes.append("do_not_move_without_import_update")
    return ",".join(notes)


def _row(path: Path) -> dict[str, Any]:
    stat = path.stat()
    category, action = _category(path)
    return {
        "name": path.name,
        "relative_path": str(path.relative_to(BASE_DIR)),
        "kind": "directory" if path.is_dir() else "file",
        "suffix": path.suffix,
        "size_bytes": stat.st_size if path.is_file() else None,
        "size_mb": round((stat.st_size / 1_000_000), 3) if path.is_file() else None,
        "last_write_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "category": category,
        "recommended_action": action,
        "risk_note": _risk_note(path, category, stat.st_size if path.is_file() else 0),
    }


def get_aster_workspace_file_audit_preview(dry_run: bool = True) -> dict[str, Any]:
    if not dry_run:
        return {"ok": False, "status": "blocked", "blockers": ["dry_run_required"]}
    rows = [_row(path) for path in sorted(BASE_DIR.iterdir(), key=lambda item: item.name.lower())]
    category_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or "unknown")
        action = str(row.get("recommended_action") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1
    heavy = sorted([row for row in rows if (row.get("size_bytes") or 0) >= 1_000_000], key=lambda row: row.get("size_bytes") or 0, reverse=True)
    scripts = [row for row in rows if str(row.get("suffix")) == ".py"]
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "classify_aster_workspace_files_without_moving_anything",
        "summary": {
            "items_total": len(rows),
            "python_scripts": len(scripts),
            "heavy_files_gt_1mb": len(heavy),
            "category_counts": category_counts,
            "action_counts": action_counts,
        },
        "rows": rows,
        "heavy_files": heavy[:50],
        "active_core_scripts": [row for row in rows if row.get("category") == "active_core_script"],
        "generated_artifacts": [row for row in rows if str(row.get("category") or "").endswith("artifact") or row.get("category") in {"backtest_csv_artifact", "runner_heartbeat"}],
        "safety": {
            "would_move_files": False,
            "would_delete_files": False,
            "would_write_db": False,
            "writes_are_report_artifacts_only": True,
        },
    }


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _table(rows: list[dict[str, Any]], limit: int = 160) -> str:
    headers = ["category", "action", "name", "size_mb", "risk"]
    body = []
    for row in rows[:limit]:
        cells = [row.get("category"), row.get("recommended_action"), row.get("name"), row.get("size_mb"), row.get("risk_note")]
        body.append("<tr>" + "".join(f"<td>{_cell(value)}</td>" for value in cells) + "</tr>")
    return "<table><thead><tr>" + "".join(f"<th>{_cell(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    counts = summary.get("category_counts") or {}
    count_html = "".join(f"<span><b>{_cell(key)}</b> {_cell(value)}</span>" for key, value in sorted(counts.items()))
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aster - Workspace file audit</title>
  <style>
    body {{ margin:0; background:#0b1017; color:#edf4ff; font-family:Verdana,Arial,sans-serif; }}
    main {{ max-width:1480px; margin:0 auto; padding:32px 28px 72px; }}
    .lead {{ color:#a7b7c9; max-width:980px; line-height:1.6; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    .card {{ background:#141d29; border:1px solid #28364a; border-radius:14px; padding:16px; }}
    .card span {{ display:block; color:#8ea1b8; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .card strong {{ display:block; margin-top:8px; font-size:24px; }}
    .counts {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0; }}
    .counts span {{ background:#172537; border:1px solid #30445f; border-radius:999px; padding:8px 12px; }}
    table {{ width:100%; border-collapse:collapse; margin-top:16px; background:#101822; border:1px solid #263548; }}
    th,td {{ padding:9px 10px; border-bottom:1px solid #263548; text-align:left; font-size:13px; }}
    th {{ background:#172131; color:#93a8c2; }}
    code {{ color:#ffd38a; }}
    .note {{ color:#a7b7c9; line-height:1.55; margin-top:18px; }}
  </style>
</head>
<body>
<main>
  <h1>Aster - Audit des fichiers de travail</h1>
  <p class="lead">Classification read-only du dossier Aster. Le but est de savoir ce qui est code actif, wrapper, artefact genere, cache, legacy ou fichier lourd. Aucun fichier n'est deplace ou supprime.</p>
  <div class="cards">
    <div class="card"><span>Total</span><strong>{_cell(summary.get("items_total"))}</strong></div>
    <div class="card"><span>Scripts Python</span><strong>{_cell(summary.get("python_scripts"))}</strong></div>
    <div class="card"><span>Fichiers &gt; 1MB</span><strong>{_cell(summary.get("heavy_files_gt_1mb"))}</strong></div>
    <div class="card"><span>Mode</span><strong>Read-only</strong></div>
  </div>
  <div class="counts">{count_html}</div>
  <h2>Scripts actifs</h2>
  {_table(payload.get("active_core_scripts") or [], 80)}
  <h2>Fichiers lourds</h2>
  {_table(payload.get("heavy_files") or [], 80)}
  <h2>Tous les fichiers</h2>
  {_table(payload.get("rows") or [], 240)}
  <p class="note">Regle: ne pas deplacer les artefacts <code>*_latest.json</code>, CSV progress ou caches tant que les runners les lisent en chemin fixe. On peut les auditer et documenter, mais les migrations doivent etre faites via wrappers ou mise a jour explicite des chemins.</p>
</main>
</body>
</html>"""


def _write_csv(rows: list[dict[str, Any]]) -> None:
    fields = ["category", "recommended_action", "name", "relative_path", "kind", "suffix", "size_bytes", "size_mb", "last_write_time", "risk_note"]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_aster_workspace_file_audit() -> dict[str, Any]:
    payload = get_aster_workspace_file_audit_preview(dry_run=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(list(payload.get("rows") or []))
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_aster_workspace_file_audit()
    summary = payload.get("summary") or {}
    print(
        f"[{payload.get('generated_at')}] items={summary.get('items_total')} "
        f"scripts={summary.get('python_scripts')} heavy={summary.get('heavy_files_gt_1mb')} "
        f"csv={CSV_OUT} html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
