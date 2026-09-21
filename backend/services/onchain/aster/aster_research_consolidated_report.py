from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"
JSON_OUT = BASE_DIR / "aster_research_consolidated_report_latest.json"
HTML_OUT = DOCS_DIR / "core-equity-aster-research-consolidated-report.html"

DISCOVERY_GLOB = "paper_trading_strategy_discovery_*_v2.csv"
REALITY_FILE = BASE_DIR / "paper_trading_reality_checked_backtest.csv"
MARK_INDEX_FILE = BASE_DIR / "aster_mark_index_replay_filter_latest.json"
SOURCE_VALIDATION_FILE = BASE_DIR / "aster_data_source_validation_latest.json"
PUBLIC_UNIVERSE_FILE = BASE_DIR / "aster_public_universe_snapshot_latest.json"
WS_QUALITY_FILE = BASE_DIR / "aster_ws_symbol_quality_report_latest.json"
PRIORITY_WATCHLIST_FILE = BASE_DIR / "aster_priority_watchlist_latest.json"
DUAL_TRACK_FILE = BASE_DIR / "aster_dual_track_research_report_latest.json"
EXPLOITATION_CHAMPIONS_FILE = BASE_DIR / "aster_exploitation_champions_latest.json"
ASTER_V2_PLAN_FILE = BASE_DIR / "aster_v2_runner_plan_latest.json"
ASTER_V2_COMPARISON_FILE = BASE_DIR / "aster_v2_strict_vs_large_comparison_latest.json"
RUNNER_HEALTH_FILE = BASE_DIR / "aster_runner_health_dashboard_latest.json"
MONITOR_FILES = [
    BASE_DIR / "paper_trading_multi_strategy_stateful_monitor.csv",
    BASE_DIR / "paper_trading_optimized_long_stateful_monitor.csv",
]


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


def _read_csv(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(dict(row))
                if limit and len(rows) >= limit:
                    break
    except OSError:
        return []
    return rows


def _score(row: dict[str, Any]) -> float:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = min(_float(row.get("profit_factor")), 50.0)
    wr = _float(row.get("win_rate"))
    closed = min(_int(row.get("closed_trades")), 80)
    dd = _float(row.get("max_drawdown_usd"))
    quality = _float(row.get("quality_score"), 70.0)
    return (roi * 10.0) + (pf * 3.0) + (wr * 12.0) + closed + (quality * 0.35) - (dd * 0.2)


def _signature(row: dict[str, Any]) -> str:
    return "|".join(str(row.get(key) or "") for key in ("symbol", "side", "interval", "risk_profile", "min_aster_score", "min_window_volume_usd"))


def _compact(row: dict[str, Any], source: str) -> dict[str, Any]:
    quality = row.get("quality_score")
    return {
        "source": source,
        "timestamp": row.get("timestamp"),
        "output_tag": row.get("output_tag"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "interval": row.get("interval"),
        "risk_profile": row.get("risk_profile"),
        "min_aster_score": _float(row.get("min_aster_score")),
        "min_window_volume_usd": _float(row.get("min_window_volume_usd")),
        "closed_trades": _int(row.get("closed_trades")),
        "win_rate": _float(row.get("win_rate")),
        "profit_factor": _float(row.get("profit_factor")),
        "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
        "max_drawdown_usd": _float(row.get("max_drawdown_usd")),
        "best_tradable_leverage": _float(row.get("best_tradable_leverage"), 0.0),
        "effective_fee_bps": _float(row.get("effective_fee_bps")) if row.get("effective_fee_bps") not in (None, "") else None,
        "round_trip_fee_usd_estimate": _float(row.get("round_trip_fee_usd_estimate")) if row.get("round_trip_fee_usd_estimate") not in (None, "") else None,
        "assumed_margin_mode": row.get("assumed_margin_mode"),
        "assumed_asset_mode": row.get("assumed_asset_mode"),
        "assumed_position_mode": row.get("assumed_position_mode"),
        "assumed_execution_model": row.get("assumed_execution_model"),
        "assumed_trigger_reference": row.get("assumed_trigger_reference"),
        "quality_score": _float(quality, 0.0) if quality not in (None, "") else None,
        "quality_verdict": row.get("quality_verdict"),
        "quality_risks": row.get("quality_risks"),
        "quality_warnings": row.get("quality_warnings"),
        "premium_bps": _float(row.get("premium_bps")),
        "spread_bps": _float(row.get("spread_bps")),
        "quote_volume_24h": _float(row.get("quote_volume_24h")),
        "trigger_protect": _float(row.get("trigger_protect")) if row.get("trigger_protect") not in (None, "") else None,
        "market_take_bound": _float(row.get("market_take_bound")) if row.get("market_take_bound") not in (None, "") else None,
        "exchange_info_status": row.get("exchange_info_status"),
        "symbol_status": row.get("symbol_status"),
        "percent_price_up": _float(row.get("percent_price_up")) if row.get("percent_price_up") not in (None, "") else None,
        "percent_price_down": _float(row.get("percent_price_down")) if row.get("percent_price_down") not in (None, "") else None,
        "tick_size": row.get("tick_size"),
        "step_size": row.get("step_size"),
        "market_step_size": row.get("market_step_size"),
        "liquidation_fee_rate": _float(row.get("liquidation_fee_rate")) if row.get("liquidation_fee_rate") not in (None, "") else None,
        "exchange_filter_verdict": row.get("exchange_filter_verdict"),
        "exchange_filter_warnings": row.get("exchange_filter_warnings"),
        "exchange_filter_blockers": row.get("exchange_filter_blockers"),
        "min_notional": _float(row.get("min_notional")) if row.get("min_notional") not in (None, "") else None,
        "order_types": row.get("order_types"),
        "time_in_force": row.get("time_in_force"),
        "mark_index_verdict": row.get("mark_index_verdict"),
        "mark_index_p95_last_index_bps": _float(row.get("mark_index_p95_last_index_bps")) if row.get("mark_index_p95_last_index_bps") not in (None, "") else None,
        "mark_index_avg_last_index_bps": _float(row.get("mark_index_avg_last_index_bps")) if row.get("mark_index_avg_last_index_bps") not in (None, "") else None,
        "mark_index_warnings": row.get("mark_index_warnings"),
        "mark_index_blockers": row.get("mark_index_blockers"),
        "ws_quality_verdict": row.get("ws_quality_verdict"),
        "ws_quality_score": _float(row.get("ws_quality_score")) if row.get("ws_quality_score") not in (None, "") else None,
        "ws_quality_risks": row.get("ws_quality_risks"),
        "ws_quality_warnings": row.get("ws_quality_warnings"),
        "ws_quote_volume_24h": _float(row.get("ws_quote_volume_24h")) if row.get("ws_quote_volume_24h") not in (None, "") else None,
        "ws_spread_bps": _float(row.get("ws_spread_bps")) if row.get("ws_spread_bps") not in (None, "") else None,
        "ws_latency_ms": _float(row.get("ws_latency_ms")) if row.get("ws_latency_ms") not in (None, "") else None,
        "research_score": 0.0,
    }


def _load_discovery_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(BASE_DIR.glob(DISCOVERY_GLOB)):
        if "smoke" in path.name:
            continue
        for row in _read_csv(path):
            compact = _compact(row, path.name)
            compact["research_score"] = round(_score(compact), 6)
            rows.append(compact)
    return rows


def _load_reality_rows() -> list[dict[str, Any]]:
    rows = []
    for row in _read_csv(REALITY_FILE):
        compact = _compact(row, REALITY_FILE.name)
        compact["research_score"] = round(_score(compact), 6)
        rows.append(compact)
    return rows


def _dedupe_best(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        sig = _signature(row)
        if not sig:
            continue
        if sig not in best or _float(row.get("research_score")) > _float(best[sig].get("research_score")):
            best[sig] = row
    return sorted(best.values(), key=lambda row: _float(row.get("research_score")), reverse=True)[:limit]


def _best_by_symbol(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        if symbol not in best or _float(row.get("research_score")) > _float(best[symbol].get("research_score")):
            best[symbol] = row
    return sorted(best.values(), key=lambda row: _float(row.get("research_score")), reverse=True)[:limit]


def _timeframe_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        interval = str(row.get("interval") or "")
        if interval:
            buckets[interval].append(row)
    out = []
    for interval, items in buckets.items():
        out.append(
            {
                "interval": interval,
                "rows": len(items),
                "avg_roi": round(sum(_float(row.get("roi_pct_on_paper_balance")) for row in items) / len(items), 6),
                "avg_win_rate": round(sum(_float(row.get("win_rate")) for row in items) / len(items), 6),
                "best_symbol": max(items, key=lambda row: _float(row.get("research_score"))).get("symbol"),
                "best_roi": max(_float(row.get("roi_pct_on_paper_balance")) for row in items),
            }
        )
    return sorted(out, key=lambda row: _float(row.get("avg_roi")), reverse=True)


def _monitor_summary() -> list[dict[str, Any]]:
    out = []
    for path in MONITOR_FILES:
        rows = _read_csv(path)
        if not rows:
            continue
        last = rows[-1]
        out.append(
            {
                "file": path.name,
                "rows": len(rows),
                "last_timestamp": last.get("timestamp") or last.get("last_scan_at") or last.get("cycle_at"),
                "last_pnl": _float(last.get("pnl") or last.get("net_pnl_usd") or last.get("pnl_total_usd")),
                "last_win_rate": _float(last.get("wr") or last.get("win_rate")),
                "last_active": _int(last.get("active") or last.get("active_positions") or last.get("active_positions_count")),
                "last_latent": _float(last.get("latent") or last.get("latent_pnl_usd") or last.get("unrealized_pnl_usd")),
            }
        )
    return out


def _status_count(rows: list[dict[str, Any]], key: str, value: str) -> int:
    return sum(1 for row in rows if str(row.get(key) or "") == value)


def _current_state(
    combined: list[dict[str, Any]],
    source_validation: dict[str, Any],
    ws_quality: dict[str, Any],
    aster_v2_plan: dict[str, Any],
    runner_health: dict[str, Any],
) -> dict[str, Any]:
    ws_summary = ws_quality.get("summary") or {}
    v2_summary = aster_v2_plan.get("preflight_summary") or {}
    health_summary = runner_health.get("summary") or {}
    return {
        "research_phase": "validation_realism_before_next_strategy_expansion",
        "core_conclusion": "les meilleurs ROI existent, mais ils doivent rester sous garde-fous exchangeInfo, WS, mark/index, funding et sessions",
        "combined_rows": len(combined),
        "exchange_info_ready_rows": sum(1 for row in combined if row.get("exchange_info_status") == "ok"),
        "exchange_info_pipeline_status": "wired_but_legacy_rows_need_rerun",
        "exchange_filter_warning_rows": _status_count(combined, "exchange_filter_verdict", "warning"),
        "exchange_filter_blocked_rows": _status_count(combined, "exchange_filter_verdict", "blocked"),
        "mark_index_confirmed_rows": _status_count(combined, "mark_index_verdict", "mark_index_confirmed"),
        "mark_index_watch_rows": _status_count(combined, "mark_index_verdict", "mark_index_watch"),
        "mark_index_rejected_rows": _status_count(combined, "mark_index_verdict", "mark_index_rejected"),
        "ws_forward_ready": ws_summary.get("ws_forward_ready"),
        "ws_forward_watch": ws_summary.get("ws_forward_watch"),
        "ws_forward_risky": ws_summary.get("ws_forward_risky"),
        "v2_backtest_ready": v2_summary.get("backtest_ready"),
        "v2_needs_ws_validation": v2_summary.get("needs_ws_validation"),
        "active_heartbeat_tags": health_summary.get("active_heartbeat_tags"),
        "source_validation_status": source_validation.get("status"),
        "next_decision": "promote_only_lanes_that_survive_reality_filters_and_forward_monitoring",
    }


def _load_mark_index_rows() -> dict[tuple[str, str], dict[str, Any]]:
    if not MARK_INDEX_FILE.exists():
        return {}
    try:
        payload = json.loads(MARK_INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        symbol = str(row.get("symbol") or "").upper()
        interval = str(row.get("interval") or "")
        if symbol and interval:
            out[(symbol, interval)] = row
    return out


def _load_source_validation() -> dict[str, Any]:
    if not SOURCE_VALIDATION_FILE.exists():
        return {
            "status": "missing_snapshot",
            "summary": {},
            "endpoint_health": {},
            "rows": [],
            "snapshot_path": str(SOURCE_VALIDATION_FILE),
        }
    try:
        payload = json.loads(SOURCE_VALIDATION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_snapshot",
            "summary": {},
            "endpoint_health": {},
            "rows": [],
            "snapshot_path": str(SOURCE_VALIDATION_FILE),
        }
    payload["status"] = "loaded"
    payload["snapshot_path"] = str(SOURCE_VALIDATION_FILE)
    return payload


def _load_json_snapshot(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing_snapshot", "label": label, "snapshot_path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "invalid_snapshot", "label": label, "snapshot_path": str(path)}
    payload["status"] = "loaded"
    payload["label"] = label
    payload["snapshot_path"] = str(path)
    return payload


def _attach_mark_index(rows: list[dict[str, Any]], mark_index: dict[tuple[str, str], dict[str, Any]]) -> None:
    for row in rows:
        key = (str(row.get("symbol") or "").upper(), str(row.get("interval") or ""))
        verdict = mark_index.get(key)
        if not verdict:
            row["mark_index_verdict"] = "not_checked"
            continue
        row["mark_index_verdict"] = verdict.get("verdict")
        row["mark_index_p95_last_index_bps"] = verdict.get("p95_last_index_close_bps")
        row["mark_index_avg_last_index_bps"] = verdict.get("avg_last_index_close_bps")
        row["mark_index_warnings"] = ",".join(verdict.get("warnings") or [])
        row["mark_index_blockers"] = ",".join(verdict.get("blockers") or [])


def _risk_bucket(row: dict[str, Any]) -> str:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    dd = _float(row.get("max_drawdown_usd"))
    quality = row.get("quality_verdict")
    risks = str(row.get("quality_risks") or "")
    mark_index = str(row.get("mark_index_verdict") or "not_checked")
    if mark_index == "mark_index_rejected":
        return "mark_index_rejected"
    if quality in (None, ""):
        if mark_index == "mark_index_confirmed" and roi > 3 and dd < 35:
            return "raw_mark_index_confirmed_needs_reality_check"
        if mark_index == "mark_index_watch" and roi > 3 and dd < 35:
            return "raw_mark_index_watch_needs_review"
        if roi > 8 and dd < 30:
            return "raw_champion_needs_reality_check"
        return "raw_research_needs_reality_check"
    if mark_index == "mark_index_confirmed" and quality == "backtest_quality_ok" and roi > 5 and dd < 30 and not risks:
        return "strict_ok_mark_index_confirmed"
    if mark_index == "mark_index_watch" and quality == "backtest_quality_ok":
        return "strict_ok_mark_index_watch"
    if quality == "backtest_quality_ok" and roi > 5 and dd < 30 and not risks:
        return "strict_ok_promotion_candidate"
    if quality == "backtest_quality_ok":
        return "strict_ok_review"
    if quality == "backtest_quality_watch":
        return "watch_accepted"
    if risks:
        return "rejected_or_manual_review"
    if roi <= 0 or dd > 60:
        return "deprioritize"
    return "research_candidate"


def build_report() -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    discovery = _load_discovery_rows()
    reality = _load_reality_rows()
    combined = [*discovery, *reality]
    mark_index = _load_mark_index_rows()
    source_validation = _load_source_validation()
    public_universe = _load_json_snapshot(PUBLIC_UNIVERSE_FILE, "public_universe")
    ws_quality = _load_json_snapshot(WS_QUALITY_FILE, "ws_quality")
    priority_watchlist = _load_json_snapshot(PRIORITY_WATCHLIST_FILE, "priority_watchlist")
    dual_track = _load_json_snapshot(DUAL_TRACK_FILE, "dual_track")
    exploitation_champions = _load_json_snapshot(EXPLOITATION_CHAMPIONS_FILE, "exploitation_champions")
    aster_v2_plan = _load_json_snapshot(ASTER_V2_PLAN_FILE, "aster_v2_plan")
    aster_v2_comparison = _load_json_snapshot(ASTER_V2_COMPARISON_FILE, "aster_v2_strict_vs_large_comparison")
    runner_health = _load_json_snapshot(RUNNER_HEALTH_FILE, "runner_health")
    _attach_mark_index(combined, mark_index)
    for row in combined:
        row["decision_bucket"] = _risk_bucket(row)
    unique_top = _dedupe_best(combined, 50)
    best_symbols = _best_by_symbol(combined, 30)
    all_mark_index_confirmed = sorted(
        [row for row in combined if row.get("mark_index_verdict") == "mark_index_confirmed"],
        key=lambda row: _float(row.get("research_score")),
        reverse=True,
    )
    all_mark_index_watch = sorted(
        [row for row in combined if row.get("mark_index_verdict") == "mark_index_watch"],
        key=lambda row: _float(row.get("research_score")),
        reverse=True,
    )
    all_mark_index_rejected = sorted(
        [row for row in combined if row.get("mark_index_verdict") == "mark_index_rejected"],
        key=lambda row: _float(row.get("research_score")),
        reverse=True,
    )
    payload = {
        "ok": True,
        "generated_at": generated_at,
        "source_counts": {
            "discovery_rows": len(discovery),
            "reality_checked_rows": len(reality),
            "combined_rows": len(combined),
            "mark_index_rows": len(mark_index),
        },
        "current_state": _current_state(combined, source_validation, ws_quality, aster_v2_plan, runner_health),
        "executive_summary": {
            "best_lane": unique_top[0] if unique_top else None,
            "best_symbols": best_symbols[:10],
            "mark_index_confirmed": _dedupe_best(all_mark_index_confirmed, 15),
            "mark_index_watch": _dedupe_best(all_mark_index_watch, 15),
            "mark_index_rejected": _dedupe_best(all_mark_index_rejected, 15),
            "strict_ok": [row for row in unique_top if row.get("decision_bucket") in {"strict_ok_mark_index_confirmed", "strict_ok_mark_index_watch", "strict_ok_promotion_candidate", "strict_ok_review"}][:10],
            "watch_accepted": [row for row in unique_top if row.get("decision_bucket") == "watch_accepted"][:10],
            "raw_needs_reality_check": [row for row in unique_top if str(row.get("decision_bucket") or "").startswith("raw_")][:15],
            "rejected_or_manual_review": [row for row in unique_top if row.get("decision_bucket") in {"rejected_or_manual_review", "mark_index_rejected"}][:10],
            "deprioritize": [row for row in unique_top if row.get("decision_bucket") == "deprioritize"][:10],
        },
        "top_lanes": unique_top,
        "best_by_symbol": best_symbols,
        "timeframe_summary": _timeframe_summary(combined),
        "monitor_summary": _monitor_summary(),
        "source_validation": source_validation,
        "public_universe": public_universe,
        "ws_quality": ws_quality,
        "priority_watchlist": priority_watchlist,
        "dual_track": dual_track,
        "exploitation_champions": exploitation_champions,
        "aster_v2_plan": aster_v2_plan,
        "aster_v2_strict_vs_large_comparison": aster_v2_comparison,
        "runner_health": runner_health,
        "methodology": {
            "research_score": "roi*10 + capped_pf*3 + win_rate*12 + capped_closed_trades + quality*0.35 - drawdown*0.2",
            "caveat": "Backtest/paper results only. No live trading authorization.",
        },
    }
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def _fmt(value: Any, digits: int = 2) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def _table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], limit: int = 20) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for key, label in columns)
    body_rows = []
    for row in rows[:limit]:
        cells = []
        for key, _label in columns:
            value = row.get(key)
            cells.append(f"<td>{_fmt(value, 2)}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    if not body_rows:
        body_rows.append(f"<tr><td colspan=\"{len(columns)}\">Aucune donnee.</td></tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _source_validation_table(payload: dict[str, Any]) -> str:
    health = payload.get("endpoint_health") or {}
    rows = [
        {"endpoint": endpoint, **(data if isinstance(data, dict) else {})}
        for endpoint, data in sorted(health.items())
    ]
    return _table(
        rows,
        [
            ("endpoint", "Endpoint"),
            ("status", "Statut"),
            ("ok_count", "OK"),
            ("total", "Total"),
        ],
        30,
    )


def _public_universe_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("top_by_abs_price_change") or []:
        rows.append(
            {
                "symbol": row.get("symbol"),
                "quote_volume_24h": row.get("quote_volume_24h"),
                "price_change_pct_24h": row.get("price_change_pct_24h"),
                "spread_bps": row.get("spread_bps"),
                "flags": ",".join(row.get("data_flags") or []),
            }
        )
    return rows


def _ws_quality_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("rows") or []:
        summary = row.get("ws_summary") or {}
        consistency = row.get("consistency") or {}
        rows.append(
            {
                "symbol": row.get("symbol"),
                "score": row.get("ws_quality_score"),
                "verdict": row.get("ws_quality_verdict"),
                "streams": f"{summary.get('streams_received')}/{summary.get('streams_expected')}",
                "latency_ms": summary.get("latency_ms"),
                "trade_rest_bps": consistency.get("ws_trade_vs_rest_last_price_bps"),
                "mark_rest_bps": consistency.get("ws_mark_vs_rest_mark_bps"),
                "risks": ",".join(row.get("ws_quality_risks") or []),
                "warnings": ",".join(row.get("ws_quality_warnings") or []),
            }
        )
    return rows


def _priority_watchlist_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("priority_watchlist") or []:
        rows.append(
            {
                "symbol": row.get("symbol"),
                "priority_score": row.get("priority_score"),
                "quote_volume_24h": row.get("quote_volume_24h"),
                "price_change_pct_24h": row.get("price_change_pct_24h"),
                "spread_bps": row.get("spread_bps"),
                "ws_quality_verdict": row.get("ws_quality_verdict"),
                "mark_index_verdict": row.get("mark_index_verdict"),
                "reasons": ",".join(row.get("reasons") or []),
            }
        )
    return rows


def _dual_track_lane_rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get(key) or []:
        rows.append(
            {
                "symbol": row.get("symbol"),
                "track": row.get("track"),
                "interval": row.get("interval"),
                "roi_pct_on_paper_balance": row.get("roi_pct_on_paper_balance"),
                "win_rate": row.get("win_rate"),
                "profit_factor": row.get("profit_factor"),
                "closed_trades": row.get("closed_trades"),
                "priority_score": row.get("priority_score"),
                "lane_status": row.get("lane_status") or row.get("priority_status"),
                "mark_index_verdict": row.get("mark_index_verdict"),
                "track_reason": row.get("track_reason"),
            }
        )
    return rows


def _exploitation_champion_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("rows") or []:
        rows.append(
            {
                "symbol": row.get("symbol"),
                "interval": row.get("interval"),
                "historical_roi_pct": row.get("historical_roi_pct"),
                "historical_win_rate": row.get("historical_win_rate"),
                "historical_profit_factor": row.get("historical_profit_factor"),
                "historical_closed_trades": row.get("historical_closed_trades"),
                "best_tradable_leverage": row.get("best_tradable_leverage"),
                "reality_quality_score": row.get("reality_quality_score"),
                "reality_quality_verdict": row.get("reality_quality_verdict"),
                "mark_index_verdict": row.get("mark_index_verdict"),
                "validation_score": row.get("validation_score"),
                "champion_decision": row.get("champion_decision"),
                "next_action": row.get("next_action"),
            }
        )
    return rows


def _aster_v2_preflight_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("preflight_rows") or []:
        rows.append(
            {
                "symbol": row.get("symbol"),
                "lane": row.get("lane"),
                "preflight_status": row.get("preflight_status"),
                "quote_volume_24h": row.get("quote_volume_24h"),
                "spread_bps": row.get("spread_bps"),
                "price_change_pct_24h": row.get("price_change_pct_24h"),
                "ws_quality_verdict": row.get("ws_quality_verdict"),
                "ws_quality_score": row.get("ws_quality_score"),
                "warnings": ",".join(row.get("warnings") or []),
                "blockers": ",".join(row.get("blockers") or []),
            }
        )
    return rows


def _aster_v2_bucket_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    buckets = ((payload.get("lanes") or {}).get("exploration_buckets") or {})
    rows = []
    for name, symbols in buckets.items():
        rows.append(
            {
                "bucket": name,
                "count": len(symbols or []),
                "symbols": ", ".join(symbols or []),
            }
        )
    return rows


def _aster_v2_comparison_rows(payload: dict[str, Any], section: str) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get(section) or []:
        strict = row.get("strict") or {}
        large = row.get("large") or {}
        rows.append(
            {
                "symbol": row.get("symbol") or strict.get("symbol") or large.get("symbol"),
                "strict_roi": strict.get("roi_pct_on_paper_balance"),
                "large_roi": large.get("roi_pct_on_paper_balance"),
                "delta_roi_pct": row.get("delta_roi_pct"),
                "strict_pf": strict.get("profit_factor"),
                "large_pf": large.get("profit_factor"),
                "delta_score": row.get("delta_score"),
                "strict_interval": strict.get("interval"),
                "large_interval": large.get("interval"),
            }
        )
    return rows


def _aster_v2_not_strict_ready_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("large_symbols_not_strict_ready") or []:
        large = row.get("large_best") or {}
        preflight = row.get("preflight") or {}
        rows.append(
            {
                "symbol": row.get("symbol"),
                "large_roi": large.get("roi_pct_on_paper_balance"),
                "large_pf": large.get("profit_factor"),
                "large_wr": large.get("win_rate"),
                "preflight": preflight.get("preflight_status"),
                "ws": preflight.get("ws_quality_verdict"),
                "ws_score": preflight.get("ws_quality_score"),
                "warnings": ",".join(preflight.get("warnings") or []),
            }
        )
    return rows


def _runner_health_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("runner_rows") or []:
        best = row.get("best_row") or {}
        rows.append(
            {
                "tag": row.get("tag"),
                "health_status": row.get("health_status"),
                "phase": row.get("heartbeat_phase"),
                "progress": f"{row.get('heartbeat_current_batch') or '-'}/{row.get('heartbeat_total_batches') or '-'}",
                "csv_exists": row.get("csv_exists"),
                "rows": row.get("csv_rows_tail_read"),
                "last_write": row.get("last_write_time_utc"),
                "last_progress": row.get("heartbeat_last_progress_at"),
                "best_symbol": best.get("symbol"),
                "best_interval": best.get("interval"),
                "best_roi": best.get("roi_pct_on_paper_balance"),
                "best_wr": best.get("win_rate"),
                "best_pf": best.get("profit_factor"),
            }
        )
    return rows


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("executive_summary") or {}
    current_state = payload.get("current_state") or {}
    best = summary.get("best_lane") or {}
    counts = payload.get("source_counts") or {}
    source_validation = payload.get("source_validation") or {}
    source_summary = source_validation.get("summary") or {}
    public_universe = payload.get("public_universe") or {}
    universe_summary = public_universe.get("summary") or {}
    ws_quality = payload.get("ws_quality") or {}
    ws_summary = ws_quality.get("summary") or {}
    priority_watchlist = payload.get("priority_watchlist") or {}
    priority_summary = priority_watchlist.get("summary") or {}
    dual_track = payload.get("dual_track") or {}
    dual_track_summary = dual_track.get("summary") or {}
    exploitation_champions = payload.get("exploitation_champions") or {}
    exploitation_summary = exploitation_champions.get("summary") or {}
    aster_v2_plan = payload.get("aster_v2_plan") or {}
    v2_summary = aster_v2_plan.get("preflight_summary") or {}
    aster_v2_comparison = payload.get("aster_v2_strict_vs_large_comparison") or {}
    v2_comparison_summary = aster_v2_comparison.get("summary") or {}
    runner_health = payload.get("runner_health") or {}
    runner_health_summary = runner_health.get("summary") or {}
    columns = [
        ("symbol", "Symbole"),
        ("interval", "TF"),
        ("roi_pct_on_paper_balance", "ROI %"),
        ("win_rate", "WR"),
        ("profit_factor", "PF"),
        ("closed_trades", "Trades"),
        ("max_drawdown_usd", "DD $"),
        ("best_tradable_leverage", "Lev."),
        ("effective_fee_bps", "Fee bps"),
        ("quality_score", "Quality"),
        ("quality_verdict", "Verdict"),
        ("trigger_protect", "TrigProt"),
        ("market_take_bound", "TakeBound"),
        ("exchange_filter_verdict", "XInfo"),
        ("min_notional", "MinNot"),
        ("mark_index_verdict", "Mark/Index"),
        ("mark_index_p95_last_index_bps", "P95 LI bps"),
        ("ws_quality_verdict", "WS"),
        ("ws_quality_score", "WS score"),
        ("decision_bucket", "Decision"),
    ]
    tf_columns = [
        ("interval", "TF"),
        ("rows", "Rows"),
        ("avg_roi", "Avg ROI"),
        ("avg_win_rate", "Avg WR"),
        ("best_symbol", "Best"),
        ("best_roi", "Best ROI"),
    ]
    monitor_columns = [
        ("file", "Fichier"),
        ("rows", "Rows"),
        ("last_timestamp", "Dernier"),
        ("last_pnl", "PnL"),
        ("last_win_rate", "WR"),
        ("last_active", "Active"),
        ("last_latent", "Latent"),
    ]
    universe_columns = [
        ("symbol", "Symbole"),
        ("price_change_pct_24h", "Change 24h %"),
        ("quote_volume_24h", "Vol 24h"),
        ("spread_bps", "Spread bps"),
        ("flags", "Flags"),
    ]
    ws_quality_columns = [
        ("symbol", "Symbole"),
        ("score", "Score"),
        ("verdict", "Verdict"),
        ("streams", "Streams"),
        ("latency_ms", "Latence"),
        ("trade_rest_bps", "Trade/REST bps"),
        ("mark_rest_bps", "Mark/REST bps"),
        ("risks", "Risks"),
        ("warnings", "Warnings"),
    ]
    priority_columns = [
        ("symbol", "Symbole"),
        ("priority_score", "Score"),
        ("quote_volume_24h", "Vol 24h"),
        ("price_change_pct_24h", "Change 24h %"),
        ("spread_bps", "Spread"),
        ("ws_quality_verdict", "WS"),
        ("mark_index_verdict", "Mark/Index"),
        ("reasons", "Raisons"),
    ]
    dual_track_columns = [
        ("symbol", "Symbole"),
        ("track", "Piste"),
        ("interval", "TF"),
        ("roi_pct_on_paper_balance", "ROI %"),
        ("win_rate", "WR"),
        ("profit_factor", "PF"),
        ("closed_trades", "Trades"),
        ("priority_score", "Priority"),
        ("lane_status", "Statut"),
        ("mark_index_verdict", "Mark/Index"),
        ("track_reason", "Pourquoi"),
    ]
    exploitation_champion_columns = [
        ("symbol", "Symbole"),
        ("interval", "TF"),
        ("historical_roi_pct", "ROI hist %"),
        ("historical_win_rate", "WR hist"),
        ("historical_profit_factor", "PF hist"),
        ("historical_closed_trades", "Trades"),
        ("best_tradable_leverage", "Lev."),
        ("reality_quality_score", "Quality"),
        ("reality_quality_verdict", "Reality"),
        ("mark_index_verdict", "Mark/Index"),
        ("validation_score", "Validation"),
        ("champion_decision", "Decision"),
        ("next_action", "Next"),
    ]
    v2_preflight_columns = [
        ("symbol", "Symbole"),
        ("lane", "Lane"),
        ("preflight_status", "Preflight"),
        ("quote_volume_24h", "Vol 24h"),
        ("spread_bps", "Spread"),
        ("price_change_pct_24h", "Change 24h %"),
        ("ws_quality_verdict", "WS"),
        ("ws_quality_score", "WS score"),
        ("warnings", "Warnings"),
        ("blockers", "Blockers"),
    ]
    v2_bucket_columns = [
        ("bucket", "Bucket"),
        ("count", "Count"),
        ("symbols", "Symboles"),
    ]
    v2_comparison_columns = [
        ("symbol", "Symbole"),
        ("strict_roi", "Strict ROI"),
        ("large_roi", "Large ROI"),
        ("delta_roi_pct", "Delta ROI"),
        ("strict_pf", "Strict PF"),
        ("large_pf", "Large PF"),
        ("delta_score", "Delta score"),
        ("strict_interval", "Strict TF"),
        ("large_interval", "Large TF"),
    ]
    v2_not_ready_columns = [
        ("symbol", "Symbole"),
        ("large_roi", "Large ROI"),
        ("large_pf", "Large PF"),
        ("large_wr", "Large WR"),
        ("preflight", "Preflight"),
        ("ws", "WS"),
        ("ws_score", "WS score"),
        ("warnings", "Warnings"),
    ]
    runner_health_columns = [
        ("tag", "Tag"),
        ("health_status", "Health"),
        ("phase", "Phase"),
        ("progress", "Progress"),
        ("csv_exists", "CSV"),
        ("rows", "Rows"),
        ("last_write", "Last write"),
        ("last_progress", "Last progress"),
        ("best_symbol", "Best"),
        ("best_interval", "TF"),
        ("best_roi", "ROI"),
        ("best_wr", "WR"),
        ("best_pf", "PF"),
    ]
    status_cards = [
        ("Phase", current_state.get("research_phase"), "On ne cherche pas juste plus de ROI: on verifie d'abord si les ROI sont executables."),
        ("Conclusion", current_state.get("core_conclusion"), "Les champions existent, mais les garde-fous decident de leur valeur reelle."),
        ("ExchangeInfo", f"{current_state.get('exchange_info_pipeline_status')} | historique {current_state.get('exchange_info_ready_rows')}/{current_state.get('combined_rows')}", "Le code est branche; les grands CSV historiques doivent etre relances pour remplir ces colonnes."),
        ("WS / Forward", f"ready {current_state.get('ws_forward_ready')} | watch {current_state.get('ws_forward_watch')} | risky {current_state.get('ws_forward_risky')}", "Le WS sert a separer les lanes exploitables des lanes purement historiques."),
        ("Mark/Index", f"confirmed {current_state.get('mark_index_confirmed_rows')} | watch {current_state.get('mark_index_watch_rows')} | rejected {current_state.get('mark_index_rejected_rows')}", "On evite les lanes dont le last price diverge trop du mark/index."),
        ("Decision", current_state.get("next_decision"), "Promouvoir seulement ce qui survit aux filtres, pas ce qui a juste un joli backtest."),
    ]
    status_html = "".join(
        f"<div class=\"note\"><b>{html.escape(str(title))}</b><p>{html.escape(str(value or '-'))}</p><small>{html.escape(str(text))}</small></div>"
        for title, value, text in status_cards
    )
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Aster - Rapport Consolide</title>
  <style>
    :root {{ --bg:#0f1512; --panel:#f8f1df; --ink:#1a211b; --muted:#667269; --line:#d8cbb6; --green:#117a4a; --amber:#9b6b00; --red:#a43b31; }}
    body {{ margin:0; background:linear-gradient(135deg,#101914,#253229); color:var(--ink); font-family: ui-sans-serif, Segoe UI, sans-serif; }}
    .page {{ width:min(1220px,calc(100% - 32px)); margin:0 auto; padding:32px 0 64px; }}
    .hero,.card {{ background:var(--panel); border:1px solid var(--line); border-radius:22px; box-shadow:0 18px 42px rgba(0,0,0,.22); }}
    .hero {{ padding:30px; margin-bottom:18px; display:grid; grid-template-columns:1.5fr .8fr; gap:20px; }}
    h1 {{ margin:0 0 8px; font-size:36px; letter-spacing:-.03em; }}
    h2 {{ margin:0 0 14px; font-size:22px; }}
    p {{ color:var(--muted); line-height:1.55; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:18px 0; }}
    .metric {{ background:#fffaf0; border:1px solid var(--line); border-radius:16px; padding:16px; }}
    .metric strong {{ display:block; font-size:24px; }}
    .notes {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
    .note {{ background:#fffaf0; border:1px solid var(--line); border-radius:16px; padding:16px; }}
    .note b {{ display:block; color:#243026; margin-bottom:6px; }}
    .note p {{ margin:0 0 8px; color:#1a211b; font-weight:700; }}
    .note small {{ color:var(--muted); line-height:1.45; display:block; }}
    .card {{ padding:22px; margin:16px 0; overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:9px 10px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
    th {{ color:#3c493f; background:#efe4cf; position:sticky; top:0; }}
    .tag {{ display:inline-block; padding:4px 9px; border-radius:999px; background:#e4f3ea; color:var(--green); font-weight:700; }}
    .warn {{ background:#fff0c2; color:var(--amber); }}
    .risk {{ background:#f6ddd8; color:var(--red); }}
    code {{ background:#efe4cf; padding:2px 5px; border-radius:6px; }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div>
        <div class="tag">Rapport consolide Aster</div>
        <h1>Backtests, reality check et runners H24</h1>
        <p>Generation: {html.escape(str(payload.get("generated_at")))}. Ce rapport consolide les CSV Aster sans relancer de trade ni backtest live. Il sert a prioriser les lanes, pas a autoriser du trading reel.</p>
      </div>
      <div>
        <p><strong>Meilleure lane actuelle</strong></p>
        <p>{html.escape(str(best.get("symbol") or "-"))} {html.escape(str(best.get("interval") or ""))}<br />ROI {_fmt(best.get("roi_pct_on_paper_balance"))}% | WR {_fmt(best.get("win_rate"))} | PF {_fmt(best.get("profit_factor"))}</p>
      </div>
    </section>
    <section class="grid">
      <div class="metric"><span>Discovery rows</span><strong>{counts.get("discovery_rows", 0)}</strong></div>
      <div class="metric"><span>Reality rows</span><strong>{counts.get("reality_checked_rows", 0)}</strong></div>
      <div class="metric"><span>Combined rows</span><strong>{counts.get("combined_rows", 0)}</strong></div>
      <div class="metric"><span>Top lanes</span><strong>{len(payload.get("top_lanes") or [])}</strong></div>
    </section>
    <section class="card">
      <h2>Ou on en est</h2>
      <p>Le projet Aster a change de nature: on n'est plus dans une simple chasse au meilleur ROI. On a maintenant un pipeline de recherche qui conserve les anciens champions, explore de nouveaux actifs, puis ajoute progressivement les contraintes reelles d'Aster.</p>
      <div class="notes">{status_html}</div>
    </section>
    <section class="card">
      <h2>Ce qui a vraiment avance</h2>
      <p><strong>Avant:</strong> les backtests etaient surtout des replays kline avec frais approximatifs. <strong>Maintenant:</strong> les nouveaux CSV V2 portent les frais officiels, le funding public, la qualite WS, les controles mark/index et les contraintes <code>exchangeInfo</code> comme <code>marketTakeBound</code>, <code>PERCENT_PRICE</code>, <code>tickSize</code>, <code>stepSize</code> et <code>minNotional</code>.</p>
      <p>La consequence est importante: une lane rentable n'est plus automatiquement interessante. Elle doit etre classee selon son statut de realisme: exploitable, watch, a revalider, ou recherche seulement.</p>
    </section>
    <section class="card"><h2>Top lanes consolidees</h2>{_table(payload.get("top_lanes") or [], columns, 30)}</section>
    <section class="card"><h2>Mark/index confirme</h2>{_table(summary.get("mark_index_confirmed") or [], columns, 15)}</section>
    <section class="card"><h2>Mark/index watch</h2>{_table(summary.get("mark_index_watch") or [], columns, 15)}</section>
    <section class="card"><h2>Mark/index rejete</h2>{_table(summary.get("mark_index_rejected") or [], columns, 15)}</section>
    <section class="card"><h2>Strict OK</h2>{_table(summary.get("strict_ok") or [], columns, 15)}</section>
    <section class="card"><h2>Watch accepted</h2>{_table(summary.get("watch_accepted") or [], columns, 15)}</section>
    <section class="card"><h2>Brut a verifier par reality check</h2>{_table(summary.get("raw_needs_reality_check") or [], columns, 15)}</section>
    <section class="card"><h2>Rejete ou review manuelle</h2>{_table(summary.get("rejected_or_manual_review") or [], columns, 15)}</section>
    <section class="card"><h2>Meilleur par symbole</h2>{_table(payload.get("best_by_symbol") or [], columns, 30)}</section>
    <section class="card"><h2>Resume par timeframe</h2>{_table(payload.get("timeframe_summary") or [], tf_columns, 20)}</section>
    <section class="card"><h2>Runners forward / monitors</h2>{_table(payload.get("monitor_summary") or [], monitor_columns, 20)}</section>
    <section class="card">
      <h2>Validation des sources Aster</h2>
      <p>Snapshot: <code>{html.escape(str(source_validation.get("status") or "unknown"))}</code> | probes {_fmt(source_summary.get("endpoint_probes"), 0)} | usable {_fmt(source_summary.get("usable_for_backtest"), 0)} | failed {_fmt(source_summary.get("failed_or_schema_mismatch"), 0)}</p>
      {_source_validation_table(source_validation)}
    </section>
    <section class="card">
      <h2>Univers public Aster</h2>
      <p>Snapshot: <code>{html.escape(str(public_universe.get("status") or "unknown"))}</code> | total {_fmt(universe_summary.get("symbols_total"), 0)} | trading {_fmt(universe_summary.get("symbols_trading"), 0)} | usable {_fmt(universe_summary.get("symbols_usable_for_research"), 0)}</p>
      {_table(_public_universe_rows(public_universe), universe_columns, 15)}
    </section>
    <section class="card">
      <h2>Qualite WebSocket forward</h2>
      <p>Snapshot: <code>{html.escape(str(ws_quality.get("status") or "unknown"))}</code> | tested {_fmt(ws_summary.get("symbols_tested"), 0)} | ready {_fmt(ws_summary.get("ws_forward_ready"), 0)} | watch {_fmt(ws_summary.get("ws_forward_watch"), 0)} | risky {_fmt(ws_summary.get("ws_forward_risky"), 0)}</p>
      {_table(_ws_quality_rows(ws_quality), ws_quality_columns, 15)}
    </section>
    <section class="card">
      <h2>Watchlist priorisee</h2>
      <p>Snapshot: <code>{html.escape(str(priority_watchlist.get("status") or "unknown"))}</code> | scored {_fmt(priority_summary.get("symbols_scored"), 0)} | priority {_fmt(priority_summary.get("priority_count"), 0)} | blocked {_fmt(priority_summary.get("blocked_count"), 0)}</p>
      {_table(_priority_watchlist_rows(priority_watchlist), priority_columns, 20)}
    </section>
    <section class="card">
      <h2>Double piste: exploiter sans oublier, explorer sans remplacer trop vite</h2>
      <p>Snapshot: <code>{html.escape(str(dual_track.get("status") or "unknown"))}</code> | exploitation {_fmt(dual_track_summary.get("exploitation_count"), 0)} | exploration {_fmt(dual_track_summary.get("exploration_count"), 0)} | historique preserve {_fmt(dual_track_summary.get("preserve_history_count"), 0)}</p>
      <p>Cette section evite le piege inverse: ne pas rester bloque sur LAB/INTC/CRCL/MSFT, mais ne pas effacer leurs resultats. Les nouveaux symboles doivent battre les champions historiques avant d'etre promus.</p>
      <h3>Piste exploitation</h3>
      {_table(_dual_track_lane_rows(dual_track, "exploitation_track"), dual_track_columns, 15)}
      <h3>Piste exploration</h3>
      {_table(_dual_track_lane_rows(dual_track, "exploration_track"), dual_track_columns, 15)}
      <h3>A ne pas oublier</h3>
      {_table(_dual_track_lane_rows(dual_track, "preserve_history_track"), dual_track_columns, 15)}
    </section>
    <section class="card">
      <h2>Champions historiques revalides</h2>
      <p>Snapshot: <code>{html.escape(str(exploitation_champions.get("status") or "unknown"))}</code> | checked {_fmt(exploitation_summary.get("champions_checked"), 0)} | promote {_fmt(exploitation_summary.get("promote_to_forward_candidate"), 0)} | keep {_fmt(exploitation_summary.get("keep_testing"), 0)} | review {_fmt(exploitation_summary.get("needs_reality_check"), 0)} | reject {_fmt(exploitation_summary.get("reject_or_manual_review"), 0)}</p>
      <p>Cette table reprend les anciens meilleurs backtests et les passe dans les garde-fous actuels: qualite perps publique, mark/index, drawdown et robustesse minimale. Elle ne relance pas un trade reel.</p>
      {_table(_exploitation_champion_rows(exploitation_champions), exploitation_champion_columns, 20)}
    </section>
    <section class="card">
      <h2>Aster v2 runner plan & preflight</h2>
      <p>Snapshot: <code>{html.escape(str(aster_v2_plan.get("status") or "unknown"))}</code> | ready {_fmt(v2_summary.get("backtest_ready"), 0)} | needs WS {_fmt(v2_summary.get("needs_ws_validation"), 0)} | needs universe refresh {_fmt(v2_summary.get("needs_universe_refresh"), 0)} | blocked {_fmt(v2_summary.get("blocked_data_quality"), 0)} | runnable {_fmt(v2_summary.get("runnable_symbols"), 0)}</p>
      <p>Cette section montre si le nouveau runner utilise vraiment l'univers Aster et la qualite WS. Le plan v2 melange maintenant champions historiques, review, crypto liquide, commodities et equities. Un symbole <code>needs_ws_validation</code> peut etre backteste en exploration, mais il n'est pas encore propre pour du forward strict.</p>
      <h3>Buckets exploration</h3>
      {_table(_aster_v2_bucket_rows(aster_v2_plan), v2_bucket_columns, 10)}
      <h3>Preflight symboles</h3>
      {_table(_aster_v2_preflight_rows(aster_v2_plan), v2_preflight_columns, 25)}
    </section>
    <section class="card">
      <h2>Aster v2 strict vs large</h2>
      <p>Snapshot: <code>{html.escape(str(aster_v2_comparison.get("comparison_status") or aster_v2_comparison.get("status") or "unknown"))}</code> | strict rows {_fmt(v2_comparison_summary.get("strict_rows"), 0)} | large rows {_fmt(v2_comparison_summary.get("large_rows"), 0)} | common lanes {_fmt(v2_comparison_summary.get("common_lanes"), 0)} | strict improved {_fmt(v2_comparison_summary.get("strict_improved_lanes"), 0)} | strict degraded {_fmt(v2_comparison_summary.get("strict_degraded_lanes"), 0)}</p>
      <p>Cette section compare le runner strict filtre WS/universe contre le runner large exploration. Si le statut indique <code>blocked_missing_strict_csv</code>, il faut laisser le terminal strict finir au moins un cycle.</p>
      <h3>Strict ameliore</h3>
      {_table(_aster_v2_comparison_rows(aster_v2_comparison, "strict_improved"), v2_comparison_columns, 15)}
      <h3>Strict degrade</h3>
      {_table(_aster_v2_comparison_rows(aster_v2_comparison, "strict_degraded"), v2_comparison_columns, 15)}
      <h3>Large non strict-ready</h3>
      {_table(_aster_v2_not_strict_ready_rows(aster_v2_comparison), v2_not_ready_columns, 15)}
    </section>
    <section class="card">
      <h2>Runner health dashboard</h2>
      <p>Snapshot: <code>{html.escape(str(runner_health.get("status") or "unknown"))}</code> | expected {_fmt(runner_health_summary.get("expected_tags"), 0)} | with CSV {_fmt(runner_health_summary.get("tags_with_csv"), 0)} | missing {_fmt(runner_health_summary.get("missing_csv"), 0)} | active heartbeat {_fmt(runner_health_summary.get("active_heartbeat_tags"), 0)}</p>
      <p>Cette section repond a la question simple: est-ce que les terminaux lancés ecrivent vraiment leurs fichiers attendus ? Si un tag est <code>missing_csv</code>, le cycle n'a pas encore fini ou le terminal a ete lance avec un autre output-tag.</p>
      {_table(_runner_health_rows(runner_health), runner_health_columns, 20)}
    </section>
    <section class="card">
      <h2>Methode</h2>
      <p>Score interne: <code>{html.escape(str((payload.get("methodology") or {}).get("research_score")))}</code></p>
      <p>Depuis le 2026-05-31, les nouveaux CSV discovery v2 integrent le funding public Aster par symbole via <code>/fapi/v3/fundingRate</code>: colonnes <code>funding_source</code>, <code>funding_status</code>, <code>funding_avg_bps_per_8h</code> et <code>funding_cost_usd_estimate</code>. Si Aster rate-limit ou bloque, le fallback proxy reste visible au lieu d'etre silencieux.</p>
      <p>Les nouveaux replays discovery utilisent aussi les frais taker officiels par symbole quand aucun override n'est fourni: <code>USDT=4 bps</code>, <code>USD1=0.5 bps</code>. Les anciens CSV generes avec l'ancien proxy <code>6 bps</code> restent conserves mais doivent etre lus comme historiques.</p>
      <p>La priorite WebSocket est maintenant branchee au workflow: le runner v2 peut rafraichir le preflight WS avant de construire son univers, et les nouveaux CSV v2 exposent <code>ws_quality_verdict</code>, <code>ws_quality_score</code>, <code>ws_spread_bps</code>, <code>ws_latency_ms</code> et les risques/warnings WS. Une lane rentable mais <code>ws_forward_risky</code> doit rester en recherche, pas en forward paper prioritaire.</p>
      <p>L'audit officiel Aster ajoute une prochaine validation importante: les meilleurs backtests kline 60j devront etre repasses sur <code>aggTrades</code>/<code>historicalTrades</code> pour verifier la microstructure. Les endpoints user stream, strategy orders, chase/BBO et MMP restent documentes mais bloques tant qu'aucune policy credentials read-only/testnet n'existe.</p>
      <p>Separation stricte a garder: le fallback <code>Spot V3</code> n'a ni funding, ni liquidation, ni leverage; une lane rentable via spot doit etre analysee comme <code>market_type=spot</code>. Les stock perps/equities doivent rester <code>needs_session_filter</code> tant que les horaires New York, off-hours et jours feries ne sont pas modelises.</p>
      <p>Le modele perps est plus realiste qu'au depart, mais pas encore complet: Aster documente l'<code>open_loss</code> dans le cout d'ouverture et l'ADL via quantile utilisateur. Ces deux risques doivent rester visibles comme limitations sur les lanes a levier eleve.</p>
      <p>Donnees Aster encore utiles a brancher plus tard: <code>!bookTicker</code> pour le spread all-symbol en WebSocket, <code>!forceOrder@arr</code> pour les regimes de liquidation, et les champs publics <code>fundingInfo</code>/<code>indexreferences</code> comme risques explicites. Les produits <code>Shield</code> et <code>1001x</code> restent separes du moteur Aster Pro perps.</p>
      <p>Les marches macro ne doivent pas etre lus comme crypto 24/7: forex Shield a des fermetures weekend/UTC, stocks ont les sessions New York, et XAU/XAG peuvent fermer pendant les jours feries US. Les lanes macro/equities restent donc <code>needs_session_model</code> jusqu'a implementation d'un filtre horaire.</p>
      <p>Smoke public supplementaire: <code>/ticker/bookTicker</code> sans symbole retourne 448 lignes, <code>/fundingInfo</code> sans symbole retourne 602 lignes, et <code>/indexreferences?symbol=BTCUSDT</code> retourne 8 references. Les trades historiques/aggTrades excluent insurance fund et ADL: la microstructure future restera <code>orderbook-only</code>.</p>
      <p>RPC/Aster Code existent aussi: <code>tapi.asterdex.com/info</code> peut lire balance/open orders/fills par adresse mais reste privacy-aware, et Aster Code gere Agent/API Wallet + Builder. Ces surfaces sont utiles pour une future verification de notre propre wallet, pas pour enrichir les backtests de marche.</p>
      <p>Deposit/withdraw public assets ont ete probes: BNB Chain/EVM/spot retourne 53 assets deposit et 53 assets withdraw, avec fee estimate ASTER disponible. C'est utile pour wallet setup uniquement; les endpoints signes de retrait/transfert restent exclus.</p>
      <p><code>exchangeInfo</code> public a ete probe: 453 symboles, tous avec <code>PRICE_FILTER</code>, <code>LOT_SIZE</code>, <code>MARKET_LOT_SIZE</code>, <code>MIN_NOTIONAL</code> et <code>PERCENT_PRICE</code>. Les bornes varient fortement: <code>LABUSDT/WIFUSDT</code> ont <code>marketTakeBound=0.10</code>, alors que <code>INTCUSDT/MSFTUSDT/CRCLUSDT</code> sont a <code>0.02</code>. Les nouveaux CSV V2 exposent maintenant ces bornes avec <code>exchange_filter_verdict</code>, warnings et blockers.</p>
      <p>Derniere passe documentaire: <code>exchangeInfo</code> expose aussi 33 assets de marge et des rate limits publics (<code>REQUEST_WEIGHT=2400/min</code>, <code>ORDERS=1200/min</code>, <code>ORDERS=300/10s</code>). Les endpoints signes restants (<code>income</code>, <code>leverageBracket</code>, <code>adlQuantile</code>, <code>commissionRate</code>, MMP, strategy orders, sub-account, migrate assets) sont maintenant classes comme future policy read-only/testnet, pas comme data manquante pour backtest public.</p>
      <p>Les error codes Futures V3 ajoutent des flags operationnels importants: <code>NO_TRADING_WINDOW</code> pour equities/macro, <code>MAX_LEVERAGE_RATIO</code> pour lanes x10/x20, rejets tick/step/min-notional, et timeouts avec statut inconnu. Les changelogs recents documentent aussi <code>STP</code>, <code>OTO/OCO/OTOCO</code> et Aster Chain, mais ces surfaces restent hors execution actuelle.</p>
      <p>Garde-fou: ces resultats restent du backtest/paper trading. Aucun ordre reel, aucun wallet, aucun signal client.</p>
    </section>
  </main>
</body>
</html>"""


def main() -> None:
    payload = build_report()
    best = (payload.get("executive_summary") or {}).get("best_lane") or {}
    print(
        f"[{payload['generated_at']}] combined={payload['source_counts']['combined_rows']} "
        f"best={best.get('symbol')} {best.get('interval')} roi={best.get('roi_pct_on_paper_balance')} "
        f"html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
