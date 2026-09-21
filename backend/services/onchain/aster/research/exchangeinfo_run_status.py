from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_FILE = BASE_DIR / "aster_exchangeinfo_run_status_latest.json"
DEFAULT_TAGS = [
    "core_exchangeinfo",
    "macro_equity_exchangeinfo",
    "equities_explore_exchangeinfo",
    "aster_v2_exchangeinfo",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle) if row]
    except OSError:
        return []


def _tag_path(tag: str, suffix: str) -> Path:
    return BASE_DIR / f"paper_trading_strategy_discovery_{tag}_{suffix}"


def _best_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return max(rows, key=lambda row: _float(row.get("roi_pct_on_paper_balance"), -999999.0))


def _compact_best(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "symbol": row.get("symbol"),
        "interval": row.get("interval"),
        "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
        "win_rate": _float(row.get("win_rate")),
        "profit_factor": _float(row.get("profit_factor")),
        "exchange_info_status": row.get("exchange_info_status"),
        "exchange_filter_verdict": row.get("exchange_filter_verdict"),
        "market_take_bound": row.get("market_take_bound"),
        "trigger_protect": row.get("trigger_protect"),
    }


def get_aster_exchangeinfo_run_status_preview(
    tags: list[str] | None = None,
    *,
    write_snapshot: bool = True,
) -> dict[str, Any]:
    clean_tags = tags or DEFAULT_TAGS
    rows = []
    for tag in clean_tags:
        csv_path = _tag_path(tag, "v2.csv")
        heartbeat_path = _tag_path(tag, "heartbeat.json")
        csv_rows = _read_csv(csv_path)
        heartbeat = _load_json(heartbeat_path)
        csv_stat = csv_path.stat() if csv_path.exists() else None
        rows.append(
            {
                "tag": tag,
                "csv_exists": csv_path.exists(),
                "csv_rows": len(csv_rows),
                "csv_size_bytes": csv_stat.st_size if csv_stat else 0,
                "csv_last_write_utc": datetime.fromtimestamp(csv_stat.st_mtime, timezone.utc).isoformat() if csv_stat else None,
                "heartbeat_phase": heartbeat.get("phase"),
                "heartbeat_progress": f"{heartbeat.get('current_batch') or '-'}/{heartbeat.get('total_batches') or '-'}",
                "heartbeat_last_progress_at": heartbeat.get("last_progress_at") or heartbeat.get("last_run_at"),
                "candidates_so_far": heartbeat.get("candidates_so_far") or heartbeat.get("total_candidates"),
                "failures_so_far": heartbeat.get("failures_so_far"),
                "best_row": _compact_best(_best_row(csv_rows)),
                "status": "csv_ready" if csv_rows else ("running_waiting_for_cycle_end" if heartbeat else "missing"),
            }
        )
    ready = [row["tag"] for row in rows if row["status"] == "csv_ready"]
    running = [row["tag"] for row in rows if row["status"] == "running_waiting_for_cycle_end"]
    payload = {
        "ok": True,
        "status": "ready",
        "generated_at": _now(),
        "source_policy": "local_artifacts_only",
        "summary": {
            "tags_total": len(rows),
            "csv_ready": len(ready),
            "running_waiting_for_cycle_end": len(running),
            "missing": len(rows) - len(ready) - len(running),
        },
        "ready_tags": ready,
        "running_tags": running,
        "rows": rows,
        "recommended_next_action": "wait_for_csv_ready" if running and not ready else "analyze_exchangeinfo_csv",
        "safety": {
            "would_call_external_api": False,
            "would_trade": False,
            "would_write_db": False,
            "would_write_snapshot": bool(write_snapshot),
        },
    }
    if write_snapshot:
        SNAPSHOT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["snapshot_path"] = str(SNAPSHOT_FILE)
    return payload


if __name__ == "__main__":
    print(json.dumps(get_aster_exchangeinfo_run_status_preview(), indent=2, sort_keys=True, default=str))
