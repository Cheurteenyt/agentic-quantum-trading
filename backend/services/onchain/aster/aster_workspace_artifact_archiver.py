from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"
ARCHIVE_DIR = BASE_DIR / "archive" / "research_artifacts"

CONFIRM_TOKEN = "CONFIRM_ASTER_ARCHIVE_LEGACY_ARTIFACTS"

JSON_OUT = BASE_DIR / "aster_workspace_artifact_archive_plan_latest.json"
CSV_OUT = BASE_DIR / "aster_workspace_artifact_archive_plan_latest.csv"
HTML_OUT = DOCS_DIR / "core-equity-aster-workspace-artifact-archive-plan.html"

ACTIVE_TAG_HINTS = {
    "core_prod_mark_bbo",
    "aster_v2_prod",
    "macro_equity_prod_mark_bbo",
    "priority_watchlist_prod",
    "focused_candidate_validation",
    "memecoin_volatile_strategy_search",
    "strict_promotion_ready_forward",
    "promotion_ready_forward",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _archive_reason(path: Path) -> str | None:
    name = path.name
    lower = name.lower()
    if path.is_dir():
        return None
    if any(tag in lower for tag in ACTIVE_TAG_HINTS):
        return None
    if ".legacy_" in lower:
        return "legacy_schema_snapshot"
    if lower.startswith("paper_trading_strategy_discovery_smoke_"):
        return "smoke_test_artifact"
    if lower in {
        "paper_trading_monitor.csv",
        "paper_trading_directional_strategy_monitor.csv",
        "paper_trading_multi_strategy_monitor.csv",
        "paper_trading_optimized_long_monitor.csv",
        "paper_trading_strategy_monitor.csv",
        "paper_trading_strategy_rotation_latest.json",
        "paper_trading_champion_lanes_backtest.csv",
        "paper_trading_champion_lanes_backtest_latest.json",
    }:
        return "legacy_monitor_or_old_champion_artifact"
    return None


def _destination(path: Path) -> Path:
    target = ARCHIVE_DIR / path.name
    if not target.exists():
        return target
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return ARCHIVE_DIR / f"{path.stem}.archived_{stamp}{path.suffix}"


def _candidate_row(path: Path) -> dict[str, Any]:
    stat = path.stat()
    dest = _destination(path)
    reason = _archive_reason(path)
    return {
        "name": path.name,
        "source_path": str(path),
        "destination_path": str(dest),
        "reason": reason,
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / 1_000_000, 3),
        "last_write_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "would_move": bool(reason),
    }


def _candidate_rows() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(BASE_DIR.iterdir(), key=lambda item: item.name.lower()):
        reason = _archive_reason(path)
        if reason:
            rows.append(_candidate_row(path))
    return rows


def get_aster_workspace_artifact_archive_plan_preview(
    dry_run: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    candidates = _candidate_rows()
    should_move = bool(not dry_run and confirm == CONFIRM_TOKEN)
    moved: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    if not dry_run and confirm != CONFIRM_TOKEN:
        return {
            "ok": False,
            "status": "blocked_confirm_required",
            "dry_run": False,
            "confirm_required": CONFIRM_TOKEN,
            "candidates": candidates,
            "would_move_count": len(candidates),
            "moved_count": 0,
            "safety": _safety(False),
        }

    if should_move:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        for row in candidates:
            source = Path(str(row.get("source_path")))
            dest = Path(str(row.get("destination_path")))
            try:
                if not source.exists() or not source.is_file():
                    failed.append({**row, "error": "source_missing_or_not_file"})
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(dest))
                moved.append({**row, "moved": True})
            except OSError as exc:
                failed.append({**row, "error": type(exc).__name__})

    return {
        "ok": True,
        "status": "archived" if should_move else "preview",
        "dry_run": bool(dry_run),
        "generated_at": _now(),
        "methodology": "move_only_legacy_smoke_and_old_monitor_artifacts_to_existing_archive_folder",
        "archive_dir": str(ARCHIVE_DIR),
        "summary": {
            "candidates": len(candidates),
            "moved_count": len(moved),
            "failed_count": len(failed),
            "active_tags_protected": sorted(ACTIVE_TAG_HINTS),
        },
        "candidates": candidates,
        "moved": moved,
        "failed": failed,
        "safety": _safety(should_move),
    }


def _safety(would_move: bool) -> dict[str, Any]:
    return {
        "would_delete_files": False,
        "would_move_files": bool(would_move),
        "would_write_db": False,
        "would_execute_trade": False,
        "active_runner_artifacts_protected": True,
        "archive_only": True,
    }


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _table(rows: list[dict[str, Any]], limit: int = 120) -> str:
    headers = ["reason", "name", "size_mb", "destination"]
    body = []
    for row in rows[:limit]:
        cells = [row.get("reason"), row.get("name"), row.get("size_mb"), row.get("destination_path")]
        body.append("<tr>" + "".join(f"<td>{_cell(value)}</td>" for value in cells) + "</tr>")
    return "<table><thead><tr>" + "".join(f"<th>{_cell(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aster - Plan d'archivage artefacts</title>
  <style>
    body {{ margin:0; background:#0b1017; color:#edf4ff; font-family:Verdana,Arial,sans-serif; }}
    main {{ max-width:1480px; margin:0 auto; padding:32px 28px 72px; }}
    .lead {{ color:#a7b7c9; max-width:980px; line-height:1.6; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    .card {{ background:#141d29; border:1px solid #28364a; border-radius:14px; padding:16px; }}
    .card span {{ display:block; color:#8ea1b8; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .card strong {{ display:block; margin-top:8px; font-size:24px; }}
    table {{ width:100%; border-collapse:collapse; margin-top:16px; background:#101822; border:1px solid #263548; }}
    th,td {{ padding:9px 10px; border-bottom:1px solid #263548; text-align:left; font-size:13px; }}
    th {{ background:#172131; color:#93a8c2; }}
    code {{ color:#ffd38a; }}
  </style>
</head>
<body>
<main>
  <h1>Aster - Plan d'archivage artefacts</h1>
  <p class="lead">Archive uniquement les artefacts smoke, snapshots legacy et anciens moniteurs. Les artefacts actifs des runners recents sont proteges.</p>
  <div class="cards">
    <div class="card"><span>Status</span><strong>{_cell(payload.get("status"))}</strong></div>
    <div class="card"><span>Candidats</span><strong>{_cell(summary.get("candidates"))}</strong></div>
    <div class="card"><span>Moved</span><strong>{_cell(summary.get("moved_count"))}</strong></div>
    <div class="card"><span>Failed</span><strong>{_cell(summary.get("failed_count"))}</strong></div>
  </div>
  <h2>Candidats</h2>
  {_table(payload.get("candidates") or [], 160)}
</main>
</body>
</html>"""


def _write_csv(rows: list[dict[str, Any]]) -> None:
    fields = ["reason", "name", "size_bytes", "size_mb", "last_write_time", "source_path", "destination_path", "would_move"]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_aster_workspace_artifact_archive_plan(dry_run: bool = True, confirm: str | None = None) -> dict[str, Any]:
    payload = get_aster_workspace_artifact_archive_plan_preview(dry_run=dry_run, confirm=confirm)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(list(payload.get("candidates") or []))
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive safe legacy Aster artifacts.")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()
    dry_run = args.confirm != CONFIRM_TOKEN
    payload = write_aster_workspace_artifact_archive_plan(dry_run=dry_run, confirm=args.confirm)
    summary = payload.get("summary") or {}
    print(
        f"[{payload.get('generated_at')}] status={payload.get('status')} "
        f"candidates={summary.get('candidates')} moved={summary.get('moved_count')} "
        f"failed={summary.get('failed_count')} html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
