from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_FILE = BASE_DIR / "aster_runner_health_dashboard_latest.json"
V2_PLAN_FILE = BASE_DIR / "aster_v2_runner_plan_latest.json"

DEFAULT_EXPECTED_TAGS = [
    "aster_v2_strict",
    "aster_v2",
    "macro_equity_explore",
    "core_explore_fresh",
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


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_tags(value: str | list[str] | None) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tag = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(item or "").strip().lower()).strip("._-")
        if tag and tag not in seen:
            out.append(tag)
            seen.add(tag)
    return out


def _csv_path(tag: str) -> Path:
    return BASE_DIR / f"paper_trading_strategy_discovery_{tag}_v2.csv"


def _json_path(tag: str) -> Path:
    return BASE_DIR / f"paper_trading_strategy_discovery_{tag}_latest.json"


def _read_tail(path: Path, max_rows: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            rows = [dict(row) for row in csv.DictReader(handle) if row]
    except OSError:
        return []
    return rows[-max(1, min(max_rows, 25_000)) :]


def _score(row: dict[str, Any]) -> float:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = min(_float(row.get("profit_factor")), 50.0)
    wr = _float(row.get("win_rate"))
    closed = min(_int(row.get("closed_trades")), 80)
    drawdown = abs(_float(row.get("max_drawdown_usd")))
    positives = _int(row.get("positive_windows"))
    return round(max(0.0, roi) * 2.0 + pf * 2.0 + wr * 10.0 + closed * 0.5 + positives * 2.0 - drawdown * 0.25, 6)


def _compact(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": row.get("side"),
        "interval": row.get("interval"),
        "search_mode": row.get("search_mode"),
        "risk_profile": row.get("risk_profile"),
        "closed_trades": _int(row.get("closed_trades")),
        "win_rate": _float(row.get("win_rate")),
        "profit_factor": _float(row.get("profit_factor")),
        "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
        "max_drawdown_usd": _float(row.get("max_drawdown_usd")),
        "best_tradable_leverage": _float(row.get("best_tradable_leverage")),
        "verdict": row.get("verdict"),
        "score": _score(row),
        "timestamp": row.get("timestamp"),
    }


def _top_unique(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol not in best or _score(row) > _score(best[symbol]):
            best[symbol] = row
    return [item for item in [_compact(row) for row in sorted(best.values(), key=_score, reverse=True)[:limit]] if item]


def _tag_status(tag: str, max_rows: int, top_n: int) -> dict[str, Any]:
    csv_file = _csv_path(tag)
    json_file = _json_path(tag)
    tag_heartbeat_file = BASE_DIR / f"paper_trading_strategy_discovery_{tag}_heartbeat.json"
    rows = _read_tail(csv_file, max_rows=max_rows)
    latest = _load_json(json_file)
    stat = csv_file.stat() if csv_file.exists() else None
    best = _compact(sorted(rows, key=_score, reverse=True)[0]) if rows else None
    heartbeat_payload = _load_json(tag_heartbeat_file) or _load_json(BASE_DIR / "paper_trading_strategy_discovery_heartbeat.json")
    heartbeat_matches = tag == str(heartbeat_payload.get("output_tag") or "")
    heartbeat = heartbeat_payload if heartbeat_matches else {}
    active_hint = bool(heartbeat and heartbeat.get("output_tag") == tag)
    return {
        "tag": tag,
        "csv_exists": csv_file.exists(),
        "json_exists": json_file.exists(),
        "csv_path": str(csv_file),
        "json_path": str(json_file),
        "csv_rows_tail_read": len(rows),
        "csv_size_bytes": stat.st_size if stat else 0,
        "last_write_time_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
        "latest_json_timestamp": latest.get("timestamp") or latest.get("finished_at"),
        "heartbeat_active": active_hint,
        "heartbeat_path": str(tag_heartbeat_file),
        "heartbeat_cycle": heartbeat.get("cycle"),
        "heartbeat_phase": heartbeat.get("phase"),
        "heartbeat_current_batch": heartbeat.get("current_batch"),
        "heartbeat_total_batches": heartbeat.get("total_batches"),
        "heartbeat_last_progress_at": heartbeat.get("last_progress_at") or heartbeat.get("last_cycle_at"),
        "heartbeat_batch_id": heartbeat.get("batch_id"),
        "heartbeat_best": heartbeat.get("best"),
        "heartbeat_batch_best": heartbeat.get("batch_best"),
        "best_row": best,
        "top_unique_symbols": _top_unique(rows, top_n),
        "health_status": (
            "active_heartbeat"
            if active_hint
            else "has_recent_artifacts"
            if rows
            else "missing_csv"
        ),
    }


def get_aster_runner_health_dashboard_preview(
    expected_tags: str | list[str] | None = None,
    max_rows_per_csv: int = 5000,
    top_n: int = 5,
    write_snapshot: bool = True,
) -> dict[str, Any]:
    tags = _parse_tags(expected_tags) or DEFAULT_EXPECTED_TAGS
    rows = [_tag_status(tag, max_rows=max_rows_per_csv, top_n=top_n) for tag in tags]
    missing = [row["tag"] for row in rows if not row["csv_exists"]]
    active = [row["tag"] for row in rows if row["heartbeat_active"]]
    with_rows = [row["tag"] for row in rows if row["csv_rows_tail_read"] > 0]
    plan = _load_json(V2_PLAN_FILE)
    payload = {
        "ok": True,
        "status": "ready",
        "source_policy": "local_runner_artifacts_only",
        "generated_at": _now(),
        "summary": {
            "expected_tags": len(tags),
            "tags_with_csv": len(with_rows),
            "missing_csv": len(missing),
            "active_heartbeat_tags": len(active),
            "v2_backtest_ready": (plan.get("preflight_summary") or {}).get("backtest_ready"),
            "v2_needs_ws_validation": (plan.get("preflight_summary") or {}).get("needs_ws_validation"),
        },
        "missing_tags": missing,
        "active_tags": active,
        "runner_rows": rows,
        "recommended_next_action": (
            "wait_for_first_cycles"
            if missing
            else "run_strict_vs_large_comparator"
        ),
        "safety": {
            "would_write_snapshot": bool(write_snapshot),
            "writes_performed": 0,
            "would_write_db": False,
            "would_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_external_api": False,
        },
    }
    if write_snapshot:
        SNAPSHOT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["snapshot_path"] = str(SNAPSHOT_FILE)
        payload["safety"]["writes_performed"] = 1
    return payload
