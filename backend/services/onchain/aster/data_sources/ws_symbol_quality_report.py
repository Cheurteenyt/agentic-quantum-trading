from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.data_sources.public_universe_snapshot import SNAPSHOT_FILE as UNIVERSE_SNAPSHOT_FILE
from services.onchain.aster.data_sources.ws_forward_monitor_preview import get_aster_ws_forward_monitor_preview


BASE_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_FILE = BASE_DIR / "aster_ws_symbol_quality_report_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_symbols(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace(";", ",").split(",")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        symbol = "".join(ch for ch in str(item or "").strip().upper() if ch.isalnum())[:32]
        if symbol and symbol not in seen:
            out.append(symbol)
            seen.add(symbol)
    return out


def _load_universe_symbols(limit: int) -> list[str]:
    if not UNIVERSE_SNAPSHOT_FILE.exists():
        return []
    try:
        payload = json.loads(UNIVERSE_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("top_clean_research_universe") or payload.get("top_by_quote_volume") or []
    out: list[str] = []
    for row in rows:
        symbol = str((row or {}).get("symbol") or "").upper()
        if symbol and symbol not in out:
            out.append(symbol)
        if len(out) >= limit:
            break
    return out


def _score_row(row: dict[str, Any]) -> dict[str, Any]:
    ws_summary = row.get("ws_summary") or {}
    consistency = row.get("consistency") or {}
    rest = row.get("rest_snapshot") or {}
    depth = ((row.get("ws_snapshot") or {}).get("depth") or {})
    score = 100
    risks: list[str] = []
    warnings: list[str] = []

    streams_expected = int(ws_summary.get("streams_expected") or 4)
    streams_received = int(ws_summary.get("streams_received") or 0)
    if streams_received < streams_expected:
        risks.append("missing_ws_stream")
        score -= 25

    latency = float(ws_summary.get("latency_ms") or 0)
    if latency > 8_000:
        risks.append("high_ws_latency")
        score -= 20
    elif latency > 4_000:
        warnings.append("moderate_ws_latency")
        score -= 8

    price_delta = consistency.get("ws_trade_vs_rest_last_price_bps")
    if price_delta is None:
        warnings.append("missing_trade_rest_consistency")
        score -= 7
    elif abs(float(price_delta)) > 25:
        risks.append("large_trade_rest_divergence")
        score -= 18
    elif abs(float(price_delta)) > 10:
        warnings.append("moderate_trade_rest_divergence")
        score -= 7

    mark_delta = consistency.get("ws_mark_vs_rest_mark_bps")
    if mark_delta is None:
        warnings.append("missing_mark_rest_consistency")
        score -= 7
    elif abs(float(mark_delta)) > 10:
        risks.append("large_mark_rest_divergence")
        score -= 18
    elif abs(float(mark_delta)) > 3:
        warnings.append("moderate_mark_rest_divergence")
        score -= 7

    spread = depth.get("spread_bps")
    if spread is None:
        warnings.append("missing_ws_spread")
        score -= 7
    elif float(spread) > 30:
        risks.append("wide_ws_spread")
        score -= 20
    elif float(spread) > 10:
        warnings.append("moderate_ws_spread")
        score -= 8

    quote_volume = rest.get("quote_volume_24h")
    if quote_volume is None:
        warnings.append("missing_quote_volume")
        score -= 5
    elif float(quote_volume) < 50_000:
        risks.append("low_quote_volume")
        score -= 18
    elif float(quote_volume) < 250_000:
        warnings.append("moderate_quote_volume")
        score -= 8

    score = max(0, min(100, score))
    verdict = "ws_forward_ready" if score >= 80 and not risks else "ws_forward_watch" if score >= 60 else "ws_forward_risky"
    return {
        "ws_quality_score": score,
        "ws_quality_verdict": verdict,
        "ws_quality_risks": risks,
        "ws_quality_warnings": warnings,
    }


def get_aster_ws_symbol_quality_report_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    timeout_seconds: int = 8,
    max_symbols: int = 5,
    interval: str = "1m",
    rate_limit_delay_ms: int = 300,
    write_snapshot: bool = False,
) -> dict[str, Any]:
    if not dry_run:
        return {
            "ok": False,
            "status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }

    safe_max = max(1, min(int(max_symbols or 5), 10))
    safe_timeout = max(1, min(int(timeout_seconds or 8), 15))
    safe_delay = max(0, min(int(rate_limit_delay_ms or 300), 2_000))
    selected = _parse_symbols(symbols)[:safe_max] if symbols else _load_universe_symbols(safe_max)
    selected = selected or ["BTCUSDT", "LABUSDT", "INJUSDT"][:safe_max]

    rows: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for index, symbol in enumerate(selected):
        if index and safe_delay:
            time.sleep(safe_delay / 1000)
        monitor = get_aster_ws_forward_monitor_preview(
            symbol=symbol,
            interval=interval,
            dry_run=True,
            timeout_seconds=safe_timeout,
            use_combined_stream=True,
        )
        row = {
            "symbol": symbol,
            "health_status": monitor.get("health_status"),
            "ws_summary": monitor.get("ws_summary"),
            "consistency": monitor.get("consistency"),
            "rest_snapshot": monitor.get("rest_snapshot"),
            "ws_snapshot": monitor.get("ws_snapshot"),
            "stream_rows": monitor.get("stream_rows"),
        }
        row.update(_score_row(row))
        rows.append(row)
        if row["ws_quality_verdict"] == "ws_forward_risky":
            failed.append(row)

    ready = [row for row in rows if row.get("ws_quality_verdict") == "ws_forward_ready"]
    watch = [row for row in rows if row.get("ws_quality_verdict") == "ws_forward_watch"]
    risky = [row for row in rows if row.get("ws_quality_verdict") == "ws_forward_risky"]
    payload = {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source_policy": "public_ws_symbol_quality_preview",
        "symbols": selected,
        "summary": {
            "symbols_tested": len(rows),
            "ws_forward_ready": len(ready),
            "ws_forward_watch": len(watch),
            "ws_forward_risky": len(risky),
        },
        "recommended_forward_symbols": [
            row["symbol"]
            for row in sorted(rows, key=lambda item: int(item.get("ws_quality_score") or 0), reverse=True)
            if row.get("ws_quality_verdict") in {"ws_forward_ready", "ws_forward_watch"}
        ],
        "rows": sorted(rows, key=lambda item: int(item.get("ws_quality_score") or 0), reverse=True),
        "failed_or_risky_rows": failed,
        "safety": {
            "would_write": bool(write_snapshot),
            "writes_performed": 0,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_trade_endpoint": False,
            "would_store_credentials": False,
        },
        "generated_at": _now(),
    }
    if write_snapshot:
        SNAPSHOT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["snapshot_path"] = str(SNAPSHOT_FILE)
        payload["safety"]["writes_performed"] = 1
    return payload
