from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
UNIVERSE_FILE = BASE_DIR / "aster_public_universe_snapshot_latest.json"
WS_QUALITY_FILE = BASE_DIR / "aster_ws_symbol_quality_report_latest.json"
MARK_INDEX_FILE = BASE_DIR / "aster_mark_index_replay_filter_latest.json"
CONSOLIDATED_FILE = BASE_DIR / "aster_research_consolidated_report_latest.json"
SNAPSHOT_FILE = BASE_DIR / "aster_priority_watchlist_latest.json"


DEFAULT_EXCLUDE = "LABUSDT,INJUSDT,CRCLUSDT,MSFTUSDT,INTCUSDT"


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


def _parse_symbols(value: str | list[str] | None) -> set[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    return {
        "".join(ch for ch in str(item or "").strip().upper() if ch.isalnum())[:32]
        for item in raw
        if str(item or "").strip()
    }


def _merge_universe_rows(payload: dict[str, Any], max_candidates: int) -> dict[str, dict[str, Any]]:
    buckets = [
        payload.get("top_by_abs_price_change") or [],
        payload.get("top_by_quote_volume") or [],
        payload.get("top_by_funding_abs") or [],
        payload.get("top_clean_research_universe") or [],
        payload.get("rows_sample") or [],
    ]
    rows: dict[str, dict[str, Any]] = {}
    for bucket in buckets:
        for row in bucket:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            existing = rows.get(symbol, {})
            rows[symbol] = {**existing, **row}
            if len(rows) >= max_candidates * 3:
                break
    return rows


def _ws_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("symbol") or "").upper(): row
        for row in payload.get("rows") or []
        if isinstance(row, dict) and row.get("symbol")
    }


def _mark_index_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    rank = {"mark_index_confirmed": 3, "mark_index_watch": 2, "mark_index_rejected": -5}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        current = best.get(symbol)
        verdict = str(row.get("verdict") or "")
        if current is None or rank.get(verdict, 0) > rank.get(str(current.get("verdict") or ""), 0):
            best[symbol] = row
    return best


def _overuse_counts(payload: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for section in ("top_lanes", "best_by_symbol"):
        for row in payload.get(section) or []:
            symbol = str((row or {}).get("symbol") or "").upper()
            if symbol:
                counts[symbol] += 1
    return counts


def _score_candidate(
    symbol: str,
    row: dict[str, Any],
    ws: dict[str, Any] | None,
    mark: dict[str, Any] | None,
    overuse_count: int,
    exclude: set[str],
) -> dict[str, Any]:
    flags = list(row.get("data_flags") or [])
    quote_volume = _float(row.get("quote_volume_24h"))
    spread = _float(row.get("spread_bps"))
    change_abs = abs(_float(row.get("price_change_pct_24h")))
    funding_abs = abs(_float(row.get("last_funding_rate")))
    premium_abs = abs(_float(row.get("premium_bps")))
    score = 0.0
    reasons: list[str] = []
    blockers: list[str] = []

    if symbol in exclude:
        blockers.append("explicitly_excluded_or_overused_focus_symbol")
    if row.get("status") != "TRADING":
        blockers.append("not_trading")
    if "wide_spread" in flags:
        blockers.append("wide_spread")
    if "low_24h_quote_volume" in flags:
        blockers.append("low_24h_quote_volume")

    score += min(30.0, quote_volume / 1_000_000)
    if quote_volume >= 250_000:
        reasons.append("sufficient_volume")
    score += min(22.0, change_abs * 0.7)
    if change_abs >= 10:
        reasons.append("large_24h_move")
    if spread and spread <= 10:
        score += 14
        reasons.append("tight_spread")
    elif spread and spread <= 30:
        score += 6
        reasons.append("acceptable_spread")
    score += min(10.0, funding_abs * 50_000)
    if funding_abs >= 0.0005:
        reasons.append("funding_dislocation")
    score += min(8.0, premium_abs / 5)
    if premium_abs >= 15:
        reasons.append("mark_index_premium_interest")

    ws_verdict = str((ws or {}).get("ws_quality_verdict") or "not_checked")
    ws_score = _float((ws or {}).get("ws_quality_score"))
    if ws_verdict == "ws_forward_ready":
        score += 18
        reasons.append("ws_forward_ready")
    elif ws_verdict == "ws_forward_watch":
        score += 9
        reasons.append("ws_forward_watch")
    elif ws_verdict == "ws_forward_risky":
        score -= 12
        blockers.append("ws_forward_risky")

    mark_verdict = str((mark or {}).get("verdict") or "not_checked")
    if mark_verdict == "mark_index_confirmed":
        score += 10
        reasons.append("mark_index_confirmed")
    elif mark_verdict == "mark_index_watch":
        score += 4
        reasons.append("mark_index_watch")
    elif mark_verdict == "mark_index_rejected":
        score -= 18
        blockers.append("mark_index_rejected")

    if overuse_count:
        score -= min(20, overuse_count * 5)
        reasons.append(f"overuse_penalty_{overuse_count}")

    score = round(max(0.0, min(100.0, score)), 6)
    status = "blocked" if blockers else "priority" if score >= 45 else "candidate" if score >= 25 else "low_priority"
    return {
        "symbol": symbol,
        "priority_score": score,
        "priority_status": status,
        "reasons": reasons,
        "blockers": blockers,
        "quote_volume_24h": quote_volume,
        "price_change_pct_24h": _float(row.get("price_change_pct_24h")),
        "spread_bps": spread,
        "last_funding_rate": _float(row.get("last_funding_rate")),
        "premium_bps": _float(row.get("premium_bps")),
        "ws_quality_score": ws_score if ws else None,
        "ws_quality_verdict": ws_verdict,
        "mark_index_verdict": mark_verdict,
        "overuse_count": overuse_count,
        "data_flags": flags,
    }


def get_aster_priority_watchlist_preview(
    dry_run: bool = True,
    max_candidates: int = 80,
    top_n: int = 25,
    exclude_symbols: str | list[str] | None = DEFAULT_EXCLUDE,
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

    safe_max = max(10, min(int(max_candidates or 80), 300))
    safe_top = max(1, min(int(top_n or 25), 100))
    exclude = _parse_symbols(exclude_symbols)
    universe = _load_json(UNIVERSE_FILE)
    ws_quality = _load_json(WS_QUALITY_FILE)
    mark_index = _load_json(MARK_INDEX_FILE)
    consolidated = _load_json(CONSOLIDATED_FILE)
    rows = _merge_universe_rows(universe, safe_max)
    ws_by_symbol = _ws_map(ws_quality)
    mark_by_symbol = _mark_index_map(mark_index)
    overuse = _overuse_counts(consolidated)

    scored = [
        _score_candidate(
            symbol,
            row,
            ws_by_symbol.get(symbol),
            mark_by_symbol.get(symbol),
            overuse.get(symbol, 0),
            exclude,
        )
        for symbol, row in rows.items()
    ]
    scored_sorted = sorted(scored, key=lambda row: row["priority_score"], reverse=True)
    priority = [row for row in scored_sorted if row["priority_status"] == "priority"][:safe_top]
    candidates = [row for row in scored_sorted if row["priority_status"] == "candidate"][:safe_top]
    blocked = [row for row in scored_sorted if row["priority_status"] == "blocked"][:safe_top]
    payload = {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source_policy": "local_snapshots_only_priority_watchlist",
        "generated_at": _now(),
        "inputs": {
            "universe_snapshot": str(UNIVERSE_FILE),
            "ws_quality_snapshot": str(WS_QUALITY_FILE),
            "mark_index_snapshot": str(MARK_INDEX_FILE),
            "consolidated_report": str(CONSOLIDATED_FILE),
            "exclude_symbols": sorted(exclude),
        },
        "summary": {
            "symbols_scored": len(scored),
            "priority_count": len([row for row in scored if row["priority_status"] == "priority"]),
            "candidate_count": len([row for row in scored if row["priority_status"] == "candidate"]),
            "blocked_count": len([row for row in scored if row["priority_status"] == "blocked"]),
            "low_priority_count": len([row for row in scored if row["priority_status"] == "low_priority"]),
        },
        "recommended_symbols": [row["symbol"] for row in priority],
        "priority_watchlist": priority,
        "candidate_watchlist": candidates,
        "blocked_or_excluded": blocked,
        "top_scored_sample": scored_sorted[:safe_top],
        "safety": {
            "would_write": bool(write_snapshot),
            "writes_performed": 0,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_external_api": False,
            "would_call_trade_endpoint": False,
            "would_store_credentials": False,
        },
    }
    if write_snapshot:
        SNAPSHOT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["snapshot_path"] = str(SNAPSHOT_FILE)
        payload["safety"]["writes_performed"] = 1
    return payload
