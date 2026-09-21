from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.data_sources.ws_symbol_quality_report import (
    SNAPSHOT_FILE as WS_QUALITY_FILE,
    get_aster_ws_symbol_quality_report_preview,
)
from services.onchain.aster.research.aster_v2_runner import (
    PLAN_FILE as V2_PLAN_FILE,
    build_aster_v2_runner_plan,
)


BASE_DIR = Path(__file__).resolve().parents[1]
REFRESH_FILE = BASE_DIR / "aster_v2_ws_preflight_refresh_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _parse_symbols(value: str | list[str] | None) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        symbol = "".join(ch for ch in str(item or "").strip().upper() if ch.isalnum())[:32]
        if symbol and symbol not in seen:
            out.append(symbol)
            seen.add(symbol)
    return out


def _chunked(rows: list[str], size: int) -> list[list[str]]:
    safe_size = max(1, min(int(size or 5), 10))
    return [rows[index : index + safe_size] for index in range(0, len(rows), safe_size)]


def _v2_plan_symbols(mode: str) -> list[str]:
    payload = _load_json(V2_PLAN_FILE)
    if not payload:
        payload = build_aster_v2_runner_plan(write_snapshot=True)
    if mode == "needs_ws_validation":
        return _parse_symbols(payload.get("needs_ws_validation_symbols") or [])
    if mode == "backtest_ready":
        return _parse_symbols(payload.get("backtest_ready_symbols") or [])
    return _parse_symbols(payload.get("symbols") or [])


def _merge_ws_rows(existing: dict[str, Any], fresh_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_symbol: dict[str, dict[str, Any]] = {
        str(row.get("symbol") or "").upper(): row
        for row in existing.get("rows") or []
        if isinstance(row, dict) and row.get("symbol")
    }
    updated_symbols: list[str] = []
    for row in fresh_rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        by_symbol[symbol] = row
        updated_symbols.append(symbol)

    rows = sorted(
        by_symbol.values(),
        key=lambda item: int(item.get("ws_quality_score") or 0),
        reverse=True,
    )
    ready = [row for row in rows if row.get("ws_quality_verdict") == "ws_forward_ready"]
    watch = [row for row in rows if row.get("ws_quality_verdict") == "ws_forward_watch"]
    risky = [row for row in rows if row.get("ws_quality_verdict") == "ws_forward_risky"]
    return {
        **existing,
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source_policy": "public_ws_symbol_quality_preview_merged_for_aster_v2",
        "symbols": [row.get("symbol") for row in rows if row.get("symbol")],
        "summary": {
            "symbols_tested": len(rows),
            "ws_forward_ready": len(ready),
            "ws_forward_watch": len(watch),
            "ws_forward_risky": len(risky),
            "last_refresh_updated_symbols": len(set(updated_symbols)),
        },
        "recommended_forward_symbols": [
            row["symbol"]
            for row in rows
            if row.get("ws_quality_verdict") in {"ws_forward_ready", "ws_forward_watch"}
        ],
        "rows": rows,
        "failed_or_risky_rows": risky,
        "generated_at": _now(),
        "last_merge": {
            "updated_symbols": sorted(set(updated_symbols)),
            "updated_count": len(set(updated_symbols)),
        },
    }


def get_aster_v2_ws_preflight_refresh_preview(
    symbols: str | list[str] | None = None,
    selection_mode: str = "needs_ws_validation",
    max_symbols: int = 10,
    batch_size: int = 5,
    timeout_seconds: int = 8,
    interval: str = "1m",
    rate_limit_delay_ms: int = 300,
    write_snapshot: bool = False,
    regenerate_v2_plan: bool = True,
) -> dict[str, Any]:
    safe_max = max(1, min(int(max_symbols or 10), 30))
    safe_batch = max(1, min(int(batch_size or 5), 10))
    safe_timeout = max(1, min(int(timeout_seconds or 8), 15))
    safe_delay = max(0, min(int(rate_limit_delay_ms or 300), 2_000))
    clean_mode = str(selection_mode or "needs_ws_validation").strip().lower()
    if clean_mode not in {"needs_ws_validation", "all_v2", "backtest_ready"}:
        clean_mode = "needs_ws_validation"

    selected = _parse_symbols(symbols) if symbols else _v2_plan_symbols(clean_mode)
    selected = selected[:safe_max]
    existing = _load_json(WS_QUALITY_FILE)
    fresh_rows: list[dict[str, Any]] = []
    batch_reports: list[dict[str, Any]] = []

    for batch_index, batch in enumerate(_chunked(selected, safe_batch), start=1):
        if batch_index > 1 and safe_delay:
            time.sleep(safe_delay / 1000)
        report = get_aster_ws_symbol_quality_report_preview(
            symbols=batch,
            dry_run=True,
            timeout_seconds=safe_timeout,
            max_symbols=len(batch),
            interval=interval,
            rate_limit_delay_ms=safe_delay,
            write_snapshot=False,
        )
        rows = [row for row in report.get("rows") or [] if isinstance(row, dict)]
        fresh_rows.extend(rows)
        batch_reports.append(
            {
                "batch_index": batch_index,
                "symbols": batch,
                "status": report.get("status"),
                "summary": report.get("summary"),
            }
        )

    merged = _merge_ws_rows(existing, fresh_rows)
    refreshed_plan = None
    writes = 0
    if write_snapshot:
        WS_QUALITY_FILE.write_text(json.dumps(merged, indent=2, sort_keys=True, default=str), encoding="utf-8")
        writes += 1
        if regenerate_v2_plan:
            refreshed_plan = build_aster_v2_runner_plan(write_snapshot=True)
            writes += 1

    ready_count = int((merged.get("summary") or {}).get("ws_forward_ready") or 0)
    watch_count = int((merged.get("summary") or {}).get("ws_forward_watch") or 0)
    risky_count = int((merged.get("summary") or {}).get("ws_forward_risky") or 0)
    payload = {
        "ok": True,
        "status": "ready" if selected else "blocked_no_symbols_selected",
        "source_policy": "aster_v2_ws_preflight_refresh_merge",
        "generated_at": _now(),
        "selection_mode": clean_mode,
        "selected_symbols": selected,
        "symbols_tested_this_run": len(fresh_rows),
        "batch_reports": batch_reports,
        "merged_summary": merged.get("summary"),
        "refreshed_v2_preflight_summary": (refreshed_plan or {}).get("preflight_summary"),
        "recommended_next_action": (
            "run_aster_v2_strict_or_forward_candidates"
            if ready_count + watch_count > risky_count
            else "keep_refreshing_ws_or_exclude_risky_symbols"
        ),
        "safety": {
            "would_write_snapshot": bool(write_snapshot),
            "writes_performed": writes,
            "would_write_db": False,
            "would_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_signed_endpoint": False,
        },
    }
    if write_snapshot:
        REFRESH_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["refresh_path"] = str(REFRESH_FILE)
        payload["ws_quality_snapshot_path"] = str(WS_QUALITY_FILE)
        if refreshed_plan:
            payload["v2_plan_path"] = str(V2_PLAN_FILE)
    return payload
