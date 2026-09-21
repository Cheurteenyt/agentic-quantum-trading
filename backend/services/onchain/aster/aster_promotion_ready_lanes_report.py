from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.aster_microstructure_replay_validator import (
    _decision as _micro_decision,
    _fetch_json as _micro_fetch_json,
    _trade_metrics as _micro_trade_metrics,
    get_aster_microstructure_replay_validator_preview,
)
from services.onchain.aster.aster_paper_trading_sandbox import (
    FORWARD_PAPER_TRADE_CONFIRM,
    _connect,
    _dedupe_forward_rows,
    _fetch_recent_trades_with_spot_fallback,
    _forward_signal_rows,
    _insert_ledger_rows,
    _replay_trades,
    _table_exists,
    get_aster_paper_trading_ledger_analytics,
)
from services.onchain.aster.aster_perps_model import (
    get_public_exchange_info_snapshot,
    get_public_funding_history_snapshot,
)


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"
CONSOLIDATED_JSON = BASE_DIR / "aster_research_consolidated_report_latest.json"
JSON_OUT = BASE_DIR / "aster_promotion_ready_lanes_latest.json"
HTML_OUT = DOCS_DIR / "core-equity-aster-promotion-ready-lanes.html"
FORWARD_CSV = BASE_DIR / "paper_trading_promotion_ready_forward_monitor.csv"
FORWARD_HEARTBEAT = BASE_DIR / "paper_trading_promotion_ready_forward_heartbeat.json"
STRICT_FORWARD_CSV = BASE_DIR / "paper_trading_strict_promotion_ready_forward_monitor.csv"
STRICT_FORWARD_HEARTBEAT = BASE_DIR / "paper_trading_strict_promotion_ready_forward_heartbeat.json"
STRICT_DIAGNOSTIC_JSON = BASE_DIR / "aster_promotion_ready_strict_forward_diagnostic_latest.json"
STRICT_LEDGER_POSTMORTEM_JSON = BASE_DIR / "aster_promotion_ready_strict_ledger_postmortem_latest.json"
PROMOTION_READY_EVENT_TYPE = "forward_promotion_ready_long"
STRICT_PROMOTION_READY_EVENT_TYPE = "forward_strict_promotion_ready_long"

FORWARD_HEADERS = [
    "timestamp",
    "mode",
    "lanes_count",
    "symbols",
    "rows_inserted",
    "deduped_rows",
    "would_insert_rows",
    "closed_in_cycle",
    "cycle_realized_pnl_usd",
    "cycle_win_rate",
    "open_positions_count",
    "open_unrealized_pnl_usd",
    "ledger_total_entries",
    "ledger_total_exits",
    "ledger_win_rate",
    "ledger_profit_factor",
    "ledger_net_pnl_usd",
    "ledger_max_drawdown_usd",
    "failed_lanes_count",
    "health_status",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _risk_params(risk_profile: Any) -> dict[str, Any]:
    profiles = {
        "micro_scalp_1_2": (-1.0, 2.0, 1.0, 0.5, 180),
        "tight_1p5_3": (-1.5, 3.0, 1.5, 0.75, 240),
        "scalp_2p5_5": (-2.5, 5.0, 2.5, 1.25, 360),
        "frequent_3_6": (-3.0, 6.0, 3.0, 1.5, 600),
        "balanced_4_8": (-4.0, 8.0, 4.0, 2.0, 600),
        "mid_5_10": (-5.0, 10.0, 5.0, 2.5, 600),
        "strict_6_12": (-6.0, 12.0, 6.0, 3.0, 600),
        "runner_5_15": (-5.0, 15.0, 7.5, 3.0, 900),
        "wide_8_16": (-8.0, 16.0, 8.0, 4.0, 800),
        "wide_10_20": (-10.0, 20.0, 10.0, 5.0, 1000),
    }
    sl, tp, trail_on, trail_dist, max_hold = profiles.get(str(risk_profile or ""), profiles["strict_6_12"])
    return {
        "stop_loss_pct": sl,
        "take_profit_pct": tp,
        "trailing_stop_activation_pct": trail_on,
        "trailing_stop_distance_pct": trail_dist,
        "max_holding_trades": max_hold,
    }


def _load_consolidated() -> dict[str, Any]:
    if not CONSOLIDATED_JSON.exists():
        return {"ok": False, "status": "missing_consolidated_report", "top_lanes": []}
    try:
        return json.loads(CONSOLIDATED_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "invalid_consolidated_report", "error": type(exc).__name__, "top_lanes": []}


def _lane_key(row: dict[str, Any]) -> str:
    strategy_profile_id = str(row.get("strategy_profile_id") or "").strip()
    if not strategy_profile_id:
        strategy_profile_id = "|".join(
            [
                str(row.get("strategy_profile_key") or ""),
                str(row.get("strategy_profile_family") or ""),
                str(row.get("trigger_reference") or ""),
                str(row.get("execution_model") or ""),
                str(row.get("best_tradable_leverage") or ""),
                str(row.get("output_tag") or ""),
            ]
        )
    return "|".join(
        [
            str(row.get("symbol") or "").upper(),
            str(row.get("interval") or ""),
            str(row.get("side") or "long").lower(),
            strategy_profile_id,
        ]
    )


def _lane_strategy_hash(row: dict[str, Any]) -> str:
    return hashlib.sha1(_lane_key(row).encode("utf-8")).hexdigest()[:10]


def _strategy_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_profile_id": row.get("strategy_profile_id"),
        "strategy_profile_key": row.get("strategy_profile_key"),
        "trigger_reference": row.get("trigger_reference"),
        "execution_model": row.get("execution_model"),
        "best_tradable_leverage": row.get("best_tradable_leverage"),
        "output_tag": row.get("output_tag"),
        "lane_key": _lane_key(row),
        "lane_strategy_hash": _lane_strategy_hash(row),
    }


def _candidate_score(row: dict[str, Any]) -> float:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = min(_float(row.get("profit_factor")), 50.0)
    wr = _float(row.get("win_rate"))
    closed = min(_int(row.get("closed_trades")), 100)
    dd = _float(row.get("max_drawdown_usd"))
    return (roi * 8) + (pf * 4) + (wr * 15) + closed - (dd * 0.25)


def _micro_lane_key(row: dict[str, Any]) -> str:
    return "|".join(str(row.get(part) or "") for part in ("symbol", "interval", "side"))


def _select_candidates(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    filtered = [
        row
        for row in rows
        if str(row.get("symbol") or "")
        and str(row.get("interval") or "")
        and str(row.get("side") or "long") in {"long", "short"}
        and _float(row.get("roi_pct_on_paper_balance")) > 0
        and _float(row.get("profit_factor")) >= 1.2
        and _int(row.get("closed_trades")) >= 6
    ]
    best: dict[str, dict[str, Any]] = {}
    for row in filtered:
        key = _lane_key(row)
        if key not in best or _candidate_score(row) > _candidate_score(best[key]):
            best[key] = row
    return sorted(best.values(), key=_candidate_score, reverse=True)[: max(1, min(int(limit or 20), 50))]


def _micro_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _micro_lane_key(row)
        out[key] = row
    return out


def _micro_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "microstructure_verdict": "not_checked",
            "micro_trade_count": None,
            "micro_quote_volume_usd": None,
            "micro_spread_bps": None,
            "micro_slippage_bps": None,
            "micro_max_gap_seconds": None,
            "micro_blockers": "",
            "micro_warnings": "",
        }
    trades = ((row.get("metrics") or {}).get("trades") or {}) if isinstance(row.get("metrics"), dict) else {}
    book = ((row.get("metrics") or {}).get("book") or {}) if isinstance(row.get("metrics"), dict) else {}
    return {
        "microstructure_verdict": row.get("verdict"),
        "micro_trade_count": trades.get("trade_count"),
        "micro_quote_volume_usd": trades.get("quote_volume_usd"),
        "micro_spread_bps": book.get("spread_bps"),
        "micro_slippage_bps": book.get("simulated_slippage_bps"),
        "micro_max_gap_seconds": trades.get("max_gap_seconds"),
        "micro_blockers": ",".join(row.get("blockers") or []),
        "micro_warnings": ",".join(row.get("warnings") or []),
    }


def _promotion_decision(row: dict[str, Any]) -> tuple[str, str]:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = _float(row.get("profit_factor"))
    wr = _float(row.get("win_rate"))
    closed = _int(row.get("closed_trades"))
    dd = _float(row.get("max_drawdown_usd"))
    mark = str(row.get("mark_index_verdict") or "not_checked")
    exchange = str(row.get("exchange_filter_verdict") or "not_checked")
    micro = str(row.get("microstructure_verdict") or "not_checked")

    if micro != "microstructure_ok":
        return "BLOCKED_MICROSTRUCTURE", f"Microstructure non validee: {micro}."
    if exchange == "blocked":
        return "BLOCKED_EXCHANGEINFO", "ExchangeInfo bloque la lane."
    if mark == "mark_index_rejected":
        return "BLOCKED_MARK_INDEX", "Mark/index rejete."
    if mark in {"mark_index_watch", "not_checked"} and roi >= 3 and pf >= 1.3 and wr >= 0.55 and closed >= 8 and dd <= 40:
        return "WATCH_MORE_DATA", f"Statistiques bonnes, mais mark/index non confirme: {mark}."
    if roi >= 3 and pf >= 1.3 and wr >= 0.55 and closed >= 8 and dd <= 40 and mark == "mark_index_confirmed":
        if exchange in {"ok", "warning", "not_checked"}:
            return "PROMOTION_READY", "ROI/PF/WR/trades corrects, mark/index confirme et microstructure remplissable."
    if roi > 0 and pf >= 1.2:
        return "WATCH_MORE_DATA", "Prometteur, mais pas encore assez propre pour promotion."
    return "REJECT_OR_DEPRIORITIZE", "Qualite statistique insuffisante."


def _merge(candidates: list[dict[str, Any]], micro_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = _micro_map(micro_rows)
    merged: list[dict[str, Any]] = []
    for row in candidates:
        key = _lane_key(row)
        compact = {
            "symbol": row.get("symbol"),
            "interval": row.get("interval"),
            "side": row.get("side"),
            "risk_profile": row.get("risk_profile"),
            "strategy_profile_id": row.get("strategy_profile_id"),
            "strategy_profile_key": row.get("strategy_profile_key"),
            "strategy_profile_family": row.get("strategy_profile_family"),
            "trigger_reference": row.get("trigger_reference"),
            "execution_model": row.get("execution_model"),
            "best_tradable_leverage": _float(row.get("best_tradable_leverage")),
            "output_tag": row.get("output_tag"),
            "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
            "profit_factor": _float(row.get("profit_factor")),
            "win_rate": _float(row.get("win_rate")),
            "closed_trades": _int(row.get("closed_trades")),
            "max_drawdown_usd": _float(row.get("max_drawdown_usd")),
            "mark_index_verdict": row.get("mark_index_verdict"),
            "exchange_filter_verdict": row.get("exchange_filter_verdict"),
            "quality_verdict": row.get("quality_verdict"),
            "source": row.get("source"),
            **_micro_summary(by_key.get(_micro_lane_key(row))),
        }
        decision, reason = _promotion_decision(compact)
        compact["promotion_decision"] = decision
        compact["promotion_reason"] = reason
        merged.append(compact)
    rank = {"PROMOTION_READY": 4, "WATCH_MORE_DATA": 3, "BLOCKED_MICROSTRUCTURE": 2, "BLOCKED_EXCHANGEINFO": 1, "BLOCKED_MARK_INDEX": 1}
    return sorted(
        merged,
        key=lambda row: (
            rank.get(str(row.get("promotion_decision")), 0),
            _float(row.get("roi_pct_on_paper_balance")),
            _float(row.get("profit_factor")),
        ),
        reverse=True,
    )


def get_aster_promotion_ready_lanes_report_preview(
    top_n: int = 20,
    dry_run: bool = True,
    position_notional_usd: float = 100.0,
    validation_bars: int = 3,
    trade_limit: int = 500,
) -> dict[str, Any]:
    if not dry_run:
        return {
            "ok": False,
            "status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write_db": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }
    consolidated = _load_consolidated()
    rows = consolidated.get("top_lanes") or []
    candidates = _select_candidates(rows, top_n)
    champions = [
        {"symbol": row.get("symbol"), "interval": row.get("interval"), "side": row.get("side") or "long"}
        for row in candidates
    ]
    micro = get_aster_microstructure_replay_validator_preview(
        champions=champions,
        dry_run=True,
        position_notional_usd=position_notional_usd,
        validation_bars=validation_bars,
        trade_limit=trade_limit,
    )
    promotion_rows = _merge(candidates, micro.get("rows") or [])
    counts: dict[str, int] = {}
    for row in promotion_rows:
        decision = str(row.get("promotion_decision") or "unknown")
        counts[decision] = counts.get(decision, 0) + 1
    payload = {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "source_report_generated_at": consolidated.get("generated_at"),
        "methodology": "select_top_consolidated_lanes_then_require_public_microstructure_fillability_before_forward_promotion",
        "top_n_requested": max(1, min(int(top_n or 20), 50)),
        "candidates_tested": len(promotion_rows),
        "summary_counts": counts,
        "microstructure_summary": micro.get("summary"),
        "promotion_ready": [row for row in promotion_rows if row.get("promotion_decision") == "PROMOTION_READY"],
        "watch": [row for row in promotion_rows if row.get("promotion_decision") == "WATCH_MORE_DATA"],
        "blocked": [row for row in promotion_rows if str(row.get("promotion_decision") or "").startswith("BLOCKED")],
        "rows": promotion_rows,
        "next_action": "run_forward_only_for_PROMOTION_READY_or_review_microstructure_blockers_before_more_backtests",
        "safety": {
            "would_write_db": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_signed_endpoint": False,
            "public_endpoints_only": True,
        },
    }
    return payload


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _table(rows: list[dict[str, Any]], limit: int = 30) -> str:
    if not rows:
        return "<p>Aucune lane.</p>"
    columns = [
        ("promotion_decision", "Decision"),
        ("symbol", "Symbol"),
        ("side", "Side"),
        ("interval", "TF"),
        ("roi_pct_on_paper_balance", "ROI %"),
        ("profit_factor", "PF"),
        ("win_rate", "WR"),
        ("closed_trades", "Trades"),
        ("max_drawdown_usd", "DD $"),
        ("microstructure_verdict", "Micro"),
        ("micro_trade_count", "Trades reels"),
        ("micro_quote_volume_usd", "Vol quote"),
        ("micro_spread_bps", "Spread bps"),
        ("micro_slippage_bps", "Slip bps"),
        ("micro_max_gap_seconds", "Max gap s"),
        ("mark_index_verdict", "Mark/Index"),
        ("exchange_filter_verdict", "XInfo"),
        ("promotion_reason", "Raison"),
    ]
    header = "".join(f"<th>{_cell(label)}</th>" for _, label in columns)
    body = []
    for row in rows[:limit]:
        body.append("<tr>" + "".join(f"<td>{_cell(row.get(key))}</td>" for key, _ in columns) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _render_html(payload: dict[str, Any]) -> str:
    counts = payload.get("summary_counts") or {}
    generated = _cell(payload.get("generated_at"))
    cards = "".join(f"<div class='metric'><b>{_cell(k)}</b><span>{_cell(v)}</span></div>" for k, v in counts.items())
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <title>Aster Promotion Ready Lanes</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, Segoe UI, Arial; margin: 0; background: #f7f3ea; color: #171510; }}
    header {{ padding: 36px 44px; background: #171510; color: #fff7e6; }}
    main {{ padding: 28px 44px 60px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 18px 0; }}
    .metric, section {{ background: white; border: 1px solid #e0d6c2; border-radius: 18px; padding: 18px; box-shadow: 0 8px 24px rgba(40,32,16,.06); }}
    .metric b {{ display: block; font-size: 12px; color: #806a3b; text-transform: uppercase; }}
    .metric span {{ font-size: 30px; font-weight: 800; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #eadfcb; text-align: left; vertical-align: top; }}
    th {{ background: #fff4d9; color: #4e3f1e; position: sticky; top: 0; }}
    code {{ background: #fff4d9; padding: 2px 5px; border-radius: 6px; }}
  </style>
</head>
<body>
<header>
  <h1>Aster Promotion Ready Lanes</h1>
  <p>Filtre final read-only: backtest consolide + microstructure publique avant promotion forward.</p>
  <p>Genere: <code>{generated}</code></p>
</header>
<main>
  <div class="grid">{cards}</div>
  <section><h2>Promotion ready</h2>{_table(payload.get("promotion_ready") or [])}</section>
  <section><h2>Watch</h2>{_table(payload.get("watch") or [])}</section>
  <section><h2>Bloquees</h2>{_table(payload.get("blocked") or [])}</section>
  <section><h2>Toutes les lanes testees</h2>{_table(payload.get("rows") or [], 50)}</section>
</main>
</body>
</html>"""


def write_aster_promotion_ready_lanes_report(**kwargs: Any) -> dict[str, Any]:
    payload = get_aster_promotion_ready_lanes_report_preview(**kwargs)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def _load_latest_promotion_ready() -> dict[str, Any]:
    if not JSON_OUT.exists():
        return {"ok": False, "status": "missing_promotion_ready_snapshot", "promotion_ready": [], "rows": [], "path": str(JSON_OUT)}
    try:
        return json.loads(JSON_OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "status": "invalid_promotion_ready_snapshot", "promotion_ready": [], "rows": [], "path": str(JSON_OUT)}


def _ensure_forward_csv(path: Path = FORWARD_CSV) -> None:
    if path.exists():
        try:
            with path.open("r", newline="", encoding="utf-8") as handle:
                first = next(csv.reader(handle), [])
            if first == FORWARD_HEADERS:
                return
            legacy = path.with_name(
                f"{path.stem}.legacy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{path.suffix}"
            )
            path.replace(legacy)
        except (OSError, StopIteration):
            pass
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(FORWARD_HEADERS)


def _write_forward_row(row: dict[str, Any], path: Path = FORWARD_CSV) -> None:
    _ensure_forward_csv(path)
    with path.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow([row.get(key) for key in FORWARD_HEADERS])


def _write_forward_heartbeat(payload: dict[str, Any]) -> None:
    FORWARD_HEARTBEAT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _write_strict_forward_heartbeat(payload: dict[str, Any]) -> None:
    STRICT_FORWARD_HEARTBEAT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _lane_event_type(row: dict[str, Any]) -> str:
    symbol = "".join(ch for ch in str(row.get("symbol") or "").lower() if ch.isalnum())[:24]
    interval = "".join(ch for ch in str(row.get("interval") or "").lower() if ch.isalnum())[:8]
    side = "".join(ch for ch in str(row.get("side") or "long").lower() if ch.isalnum())[:8]
    return f"{PROMOTION_READY_EVENT_TYPE}_{symbol}_{interval}_{side}_{_lane_strategy_hash(row)}"


def _strict_lane_event_type(row: dict[str, Any]) -> str:
    symbol = "".join(ch for ch in str(row.get("symbol") or "").lower() if ch.isalnum())[:24]
    interval = "".join(ch for ch in str(row.get("interval") or "").lower() if ch.isalnum())[:8]
    side = "".join(ch for ch in str(row.get("side") or "long").lower() if ch.isalnum())[:8]
    return f"{STRICT_PROMOTION_READY_EVENT_TYPE}_{symbol}_{interval}_{side}_{_lane_strategy_hash(row)}"


def _fetch_entry_window_trades(symbol: str, entry_time_ms: int, window_seconds: int, limit: int, timeout_seconds: int) -> dict[str, Any]:
    half_ms = max(5, min(_int(window_seconds, 120), 3_600)) * 500
    start_ms = max(0, int(entry_time_ms) - half_ms)
    end_ms = int(entry_time_ms) + half_ms
    result = _micro_fetch_json(
        "/fapi/v3/aggTrades",
        {"symbol": symbol, "startTime": start_ms, "endTime": end_ms, "limit": max(10, min(_int(limit, 500), 1000))},
        timeout_seconds,
    )
    payload = result.get("payload")
    if result.get("ok") and isinstance(payload, list):
        return {**result, "trades": payload, "start_time_ms": start_ms, "end_time_ms": end_ms}
    return {**result, "trades": [], "start_time_ms": start_ms, "end_time_ms": end_ms}


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(row.get("raw_payload_json") or "{}")
        return payload if isinstance(payload, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _closed_trade_pairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_entry: dict[str, Any] | None = None
    pairs: list[dict[str, Any]] = []
    for row in rows:
        state = str(row.get("state") or "")
        payload = _payload(row)
        action = str(payload.get("action") or "")
        if state == "executing_entry" or action == "entry":
            current_entry = row
            continue
        if state == "executing_exit" and current_entry is not None:
            entry_payload = _payload(current_entry)
            exit_payload = payload
            pairs.append(
                {
                    "entry_trade_id": entry_payload.get("trade_id"),
                    "entry_time": entry_payload.get("trade_time"),
                    "entry_price": current_entry.get("entry_price") or current_entry.get("current_price"),
                    "entry_score": current_entry.get("aster_score"),
                    "window_volume_usd": (entry_payload.get("score_proxy") or {}).get("window_volume_usd"),
                    "exit_trade_id": exit_payload.get("trade_id"),
                    "exit_time": exit_payload.get("trade_time"),
                    "exit_price": row.get("current_price"),
                    "pnl_realized_usd": _float(row.get("pnl_realized_usd")),
                    "exit_reason": exit_payload.get("exit_reason") or row.get("decision_reason"),
                    "entry_payload": entry_payload,
                    "exit_payload": exit_payload,
                }
            )
            current_entry = None
    return pairs


def _ledger_promotion_pairs(limit_pairs: int, event_prefix: str = PROMOTION_READY_EVENT_TYPE) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    with _connect() as conn:
        if not _table_exists(conn):
            return []
        conn.row_factory = None
        cur = conn.execute(
            """
            select event_type, symbol, state, entry_price, current_price, aster_score,
                   pnl_unrealized_usd, pnl_realized_usd, raw_payload_json, created_at
            from aster_paper_trading_ledger
            where event_type like ?
            order by event_type asc, created_at asc, rowid asc
            """,
            (f"{event_prefix}%",),
        )
        rows = [
            {
                "event_type": row[0],
                "symbol": row[1],
                "state": row[2],
                "entry_price": row[3],
                "current_price": row[4],
                "aster_score": row[5],
                "pnl_unrealized_usd": row[6],
                "pnl_realized_usd": row[7],
                "raw_payload_json": row[8],
                "created_at": row[9],
            }
            for row in cur.fetchall()
        ]
    current_by_type: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_type = str(row.get("event_type") or "")
        payload = _payload(row)
        action = str(payload.get("action") or "")
        state = str(row.get("state") or "")
        if state == "executing_entry" or action == "entry":
            current_by_type[event_type] = row
            continue
        if state == "executing_exit" and event_type in current_by_type:
            entry = current_by_type.pop(event_type)
            entry_payload = _payload(entry)
            exit_payload = payload
            pairs.append(
                {
                    "event_type": event_type,
                    "symbol": row.get("symbol"),
                    "interval": entry_payload.get("interval"),
                    "side": entry_payload.get("side"),
                    "risk_profile": entry_payload.get("risk_profile"),
                    "entry_trade_id": entry_payload.get("trade_id"),
                    "entry_time": entry_payload.get("trade_time"),
                    "entry_price": entry.get("entry_price") or entry.get("current_price"),
                    "entry_score": entry.get("aster_score"),
                    "window_volume_usd": (entry_payload.get("score_proxy") or {}).get("window_volume_usd"),
                    "exit_trade_id": exit_payload.get("trade_id"),
                    "exit_time": exit_payload.get("trade_time"),
                    "exit_price": row.get("current_price"),
                    "pnl_realized_usd": _float(row.get("pnl_realized_usd")),
                    "exit_reason": exit_payload.get("exit_reason") or row.get("decision_reason"),
                    "created_at": row.get("created_at"),
                    "strategy_profile_id": entry_payload.get("strategy_profile_id"),
                    "strategy_profile_key": entry_payload.get("strategy_profile_key"),
                    "trigger_reference": entry_payload.get("trigger_reference"),
                    "execution_model": entry_payload.get("execution_model"),
                    "best_tradable_leverage": entry_payload.get("best_tradable_leverage"),
                    "lane_key": entry_payload.get("lane_key"),
                    "lane_strategy_hash": entry_payload.get("lane_strategy_hash"),
                    "entry_payload": entry_payload,
                    "exit_payload": exit_payload,
                }
            )
    return pairs[-max(1, min(_int(limit_pairs, 60), 200)) :]


def _event_prefix_analytics(prefix: str) -> dict[str, Any]:
    with _connect() as conn:
        if not _table_exists(conn):
            return {"total_entries": 0, "total_exits": 0, "net_pnl_usd": 0.0, "win_rate": None, "profit_factor": None}
        row = conn.execute(
            """
            select
                sum(case when state='executing_entry' then 1 else 0 end) as entries,
                sum(case when state='executing_exit' then 1 else 0 end) as exits,
                sum(case when state='executing_exit' then coalesce(pnl_realized_usd,0) else 0 end) as net_pnl,
                sum(case when state='executing_exit' and pnl_realized_usd>0 then pnl_realized_usd else 0 end) as gross_win,
                abs(sum(case when state='executing_exit' and pnl_realized_usd<0 then pnl_realized_usd else 0 end)) as gross_loss,
                avg(case when state='executing_exit' and pnl_realized_usd>0 then 1.0 when state='executing_exit' then 0.0 end) as win_rate
            from aster_paper_trading_ledger
            where event_type like ?
            """,
            (f"{prefix}%",),
        ).fetchone()
    entries = _int(row[0] if row else 0)
    exits = _int(row[1] if row else 0)
    net_pnl = _float(row[2] if row else 0.0)
    gross_win = _float(row[3] if row else 0.0)
    gross_loss = _float(row[4] if row else 0.0)
    return {
        "total_entries": entries,
        "total_exits": exits,
        "net_pnl_usd": round(net_pnl, 6),
        "win_rate": round(_float(row[5]), 6) if row and row[5] is not None else None,
        "profit_factor": round(gross_win / gross_loss, 6) if gross_loss > 0 else None,
    }


def _strict_pass(
    *,
    lane: dict[str, Any],
    entry_check: dict[str, Any],
    current_micro: dict[str, Any],
    funding: dict[str, Any],
    exchange: dict[str, Any],
    max_funding_bps_for_long: float,
) -> tuple[bool, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if entry_check.get("verdict") != "microstructure_ok":
        blockers.append(f"entry_tape_{entry_check.get('verdict') or 'unknown'}")
    if _int(entry_check.get("trade_count")) < 50:
        blockers.append("entry_tape_too_few_trades_lt_50")
    if _float(entry_check.get("quote_volume_usd")) < 20_000:
        blockers.append("entry_tape_quote_volume_lt_20k")
    if _float(entry_check.get("max_gap_seconds")) > 30:
        blockers.append("entry_tape_gap_gt_30s")

    if current_micro.get("microstructure_verdict") != "microstructure_ok":
        blockers.append(f"current_book_{current_micro.get('microstructure_verdict') or 'unknown'}")
    if _float(current_micro.get("micro_spread_bps"), 999.0) > 8:
        warnings.append("current_spread_gt_8bps")
    if _float(current_micro.get("micro_slippage_bps"), 999.0) > 8:
        warnings.append("current_slippage_gt_8bps")

    latest_funding_bps = _float(funding.get("latest_funding_bps_per_8h"), _float(funding.get("avg_funding_bps_per_8h")))
    if str(lane.get("side") or "long") == "long" and latest_funding_bps > max_funding_bps_for_long:
        blockers.append("long_funding_too_expensive")
    if funding.get("status") not in {"ok", "missing"}:
        warnings.append(f"funding_status_{funding.get('status')}")

    if str(exchange.get("exchange_info_status") or "") != "ok":
        blockers.append(f"exchange_info_{exchange.get('exchange_info_status') or 'missing'}")
    if str(lane.get("mark_index_verdict") or "not_checked") == "mark_index_rejected":
        blockers.append("mark_index_rejected")
    return not blockers, blockers, warnings


def _strict_entry_check_for_signal(
    signal: dict[str, Any],
    *,
    lane: dict[str, Any],
    current_micro: dict[str, Any],
    funding: dict[str, Any],
    exchange: dict[str, Any],
    entry_window_seconds: int,
    trade_limit: int,
    timeout_seconds: int,
    max_funding_bps_for_long: float,
) -> dict[str, Any]:
    payload = _payload(signal)
    if str(payload.get("action") or "") != "entry":
        return {"pass": True, "blockers": [], "warnings": [], "entry_micro": None}
    symbol = str(lane.get("symbol") or "").upper()
    entry_time = _int(payload.get("trade_time"))
    if entry_time <= 0:
        entry_check = {"verdict": "not_enough_trades", "blockers": ["missing_entry_timestamp"]}
    else:
        window = _fetch_entry_window_trades(symbol, entry_time, entry_window_seconds, trade_limit, timeout_seconds)
        metrics = _micro_trade_metrics(window.get("trades") or [])
        pseudo_book = {
            "status": "ok",
            "fillable_at_book_depth": True,
            "spread_bps": 0.0,
            "simulated_slippage_bps": 0.0,
            "top10_depth_usd": 999_999.0,
            "position_notional_usd": 100.0,
        }
        decision = _micro_decision(
            metrics,
            pseudo_book,
            min_trades=30,
            min_quote_volume_usd=5_000.0,
            max_spread_bps=10_000.0,
            max_slippage_bps=10_000.0,
            max_gap_seconds=60.0,
        )
        entry_check = {
            "trade_count": metrics.get("trade_count"),
            "quote_volume_usd": metrics.get("quote_volume_usd"),
            "max_gap_seconds": metrics.get("max_gap_seconds"),
            "p95_gap_seconds": metrics.get("p95_gap_seconds"),
            **decision,
        }
    passed, blockers, warnings = _strict_pass(
        lane=lane,
        entry_check=entry_check,
        current_micro=current_micro,
        funding=funding,
        exchange=exchange,
        max_funding_bps_for_long=max_funding_bps_for_long,
    )
    return {"pass": passed, "blockers": blockers, "warnings": warnings, "entry_micro": entry_check}


def _forward_lane_rows(
    lane: dict[str, Any],
    *,
    forward_window_trades: int,
    timeout_seconds: int,
    wallet_balance_usd: float,
    fee_bps: float,
    slippage_bps: float,
    window_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    symbol = str(lane.get("symbol") or "").upper()
    risk = _risk_params(lane.get("risk_profile"))
    fetched = _fetch_recent_trades_with_spot_fallback(symbol, forward_window_trades, timeout_seconds)
    if not fetched.get("ok"):
        return [], {
            "symbol": symbol,
            "interval": lane.get("interval"),
            "status": "fetch_failed",
            "fetch_status": fetched.get("fetch_status"),
            "attempts": fetched.get("attempts"),
        }
    run_id = f"promotion-ready-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{symbol}-{lane.get('interval')}"
    rows, report = _replay_trades(
        fetched.get("trades") or [],
        run_id,
        symbol,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        min_aster_score=70.0,
        min_window_volume_usd=3_000.0,
        stop_loss_pct=_float(risk.get("stop_loss_pct")),
        take_profit_pct=_float(risk.get("take_profit_pct")),
        trailing_stop_activation_pct=_float(risk.get("trailing_stop_activation_pct")),
        trailing_stop_distance_pct=_float(risk.get("trailing_stop_distance_pct")),
        max_holding_trades=_int(risk.get("max_holding_trades"), 600),
    )
    event_type = _lane_event_type(lane)
    signals = _forward_signal_rows(rows, event_type=event_type)
    enriched: list[dict[str, Any]] = []
    for signal in signals:
        try:
            payload = json.loads(signal.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        signal = dict(signal)
        signal["raw_payload_json"] = json.dumps(
            {
                **payload,
                "source": "promotion_ready_forward_monitor",
                "promotion_ready_lane": True,
                "symbol": symbol,
                "interval": lane.get("interval"),
                "side": lane.get("side"),
                "risk_profile": lane.get("risk_profile"),
                **_strategy_payload(lane),
                "promotion_snapshot": {
                    "roi_pct_on_paper_balance": lane.get("roi_pct_on_paper_balance"),
                    "profit_factor": lane.get("profit_factor"),
                    "win_rate": lane.get("win_rate"),
                    "microstructure_verdict": lane.get("microstructure_verdict"),
                },
                "risk_params": risk,
            },
            sort_keys=True,
        )
        enriched.append(signal)
    open_rows = [row for row in rows if row.get("state") == "monitoring" and row.get("decision_reason") == "mark_to_market_holding"]
    latest_open = open_rows[-1] if open_rows else None
    closed = [row for row in rows if row.get("state") == "executing_exit"]
    pnls = [_float(row.get("pnl_realized_usd")) for row in closed]
    open_unrealized = _float(latest_open.get("pnl_unrealized_usd")) if latest_open else 0.0
    return enriched, {
        "symbol": symbol,
        "interval": lane.get("interval"),
        "side": lane.get("side"),
        "event_type": event_type,
        "status": "ok",
        "fetched_events": len(fetched.get("trades") or []),
        "signals_count": len(enriched),
        "closed_count": len(closed),
        "open_count": 1 if latest_open else 0,
        "cycle_realized_pnl_usd": round(sum(pnls), 6),
        "cycle_win_rate": round(sum(1 for pnl in pnls if pnl > 0) / len(pnls), 6) if pnls else None,
        "open_unrealized_pnl_usd": round(open_unrealized, 6),
        "risk_params": risk,
    }


def _strict_forward_lane_rows(
    lane: dict[str, Any],
    *,
    forward_window_trades: int,
    timeout_seconds: int,
    wallet_balance_usd: float,
    fee_bps: float,
    slippage_bps: float,
    window_size: int,
    current_micro: dict[str, Any],
    funding: dict[str, Any],
    exchange: dict[str, Any],
    entry_window_seconds: int,
    trade_limit: int,
    max_funding_bps_for_long: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    symbol = str(lane.get("symbol") or "").upper()
    risk = _risk_params(lane.get("risk_profile"))
    fetched = _fetch_recent_trades_with_spot_fallback(symbol, forward_window_trades, timeout_seconds)
    if not fetched.get("ok"):
        return [], {
            "symbol": symbol,
            "interval": lane.get("interval"),
            "status": "fetch_failed",
            "fetch_status": fetched.get("fetch_status"),
            "attempts": fetched.get("attempts"),
        }
    run_id = f"strict-promotion-ready-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{symbol}-{lane.get('interval')}"
    rows, _report = _replay_trades(
        fetched.get("trades") or [],
        run_id,
        symbol,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
        min_aster_score=70.0,
        min_window_volume_usd=3_000.0,
        stop_loss_pct=_float(risk.get("stop_loss_pct")),
        take_profit_pct=_float(risk.get("take_profit_pct")),
        trailing_stop_activation_pct=_float(risk.get("trailing_stop_activation_pct")),
        trailing_stop_distance_pct=_float(risk.get("trailing_stop_distance_pct")),
        max_holding_trades=_int(risk.get("max_holding_trades"), 600),
    )
    event_type = _strict_lane_event_type(lane)
    signals = _forward_signal_rows(rows, event_type=event_type)
    enriched: list[dict[str, Any]] = []
    rejected_entries = 0
    strict_checks: list[dict[str, Any]] = []
    for signal in signals:
        check = _strict_entry_check_for_signal(
            signal,
            lane=lane,
            current_micro=current_micro,
            funding=funding,
            exchange=exchange,
            entry_window_seconds=entry_window_seconds,
            trade_limit=trade_limit,
            timeout_seconds=timeout_seconds,
            max_funding_bps_for_long=max_funding_bps_for_long,
        )
        strict_checks.append(check)
        if not check.get("pass"):
            rejected_entries += 1
            continue
        payload = _payload(signal)
        signal = dict(signal)
        signal["raw_payload_json"] = json.dumps(
            {
                **payload,
                "source": "strict_promotion_ready_forward_monitor",
                "promotion_ready_lane": True,
                "strict_promotion_ready": True,
                "strict_entry_check": check,
                "symbol": symbol,
                "interval": lane.get("interval"),
                "side": lane.get("side"),
                "risk_profile": lane.get("risk_profile"),
                **_strategy_payload(lane),
                "promotion_snapshot": {
                    "roi_pct_on_paper_balance": lane.get("roi_pct_on_paper_balance"),
                    "profit_factor": lane.get("profit_factor"),
                    "win_rate": lane.get("win_rate"),
                    "microstructure_verdict": lane.get("microstructure_verdict"),
                },
                "risk_params": risk,
            },
            sort_keys=True,
        )
        enriched.append(signal)
    open_rows = [row for row in rows if row.get("state") == "monitoring" and row.get("decision_reason") == "mark_to_market_holding"]
    latest_open = open_rows[-1] if open_rows else None
    closed = [row for row in rows if row.get("state") == "executing_exit"]
    kept_closed = [signal for signal in enriched if signal.get("state") == "executing_exit"]
    pnls = [_float(row.get("pnl_realized_usd")) for row in kept_closed]
    open_unrealized = _float(latest_open.get("pnl_unrealized_usd")) if latest_open else 0.0
    return enriched, {
        "symbol": symbol,
        "interval": lane.get("interval"),
        "side": lane.get("side"),
        "event_type": event_type,
        "status": "ok",
        "fetched_events": len(fetched.get("trades") or []),
        "raw_signals_count": len(signals),
        "signals_count": len(enriched),
        "strict_rejected_entries": rejected_entries,
        "closed_count": len(kept_closed),
        "raw_closed_count": len(closed),
        "open_count": 1 if latest_open else 0,
        "cycle_realized_pnl_usd": round(sum(pnls), 6),
        "cycle_win_rate": round(sum(1 for pnl in pnls if pnl > 0) / len(pnls), 6) if pnls else None,
        "open_unrealized_pnl_usd": round(open_unrealized, 6),
        "risk_params": risk,
        "strict_checks_summary": {
            "checked": len(strict_checks),
            "passed": sum(1 for item in strict_checks if item.get("pass")),
            "rejected": sum(1 for item in strict_checks if not item.get("pass")),
        },
    }


def get_aster_promotion_ready_forward_cycle(
    dry_run: bool = True,
    persist: bool = False,
    confirm: str | None = None,
    forward_window_trades: int = 1_000,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
) -> dict[str, Any]:
    if persist and confirm != FORWARD_PAPER_TRADE_CONFIRM:
        return {
            "ok": False,
            "status": "blocked",
            "blockers": ["confirm_CONFIRM_FORWARD_PAPER_TRADE_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }
    snapshot = _load_latest_promotion_ready()
    lanes = list(snapshot.get("promotion_ready") or [])
    safe_events = max(50, min(_int(forward_window_trades, 1_000), 1_000))
    safe_timeout = max(1, min(_int(timeout_seconds, 10), 10))
    safe_delay = max(0, min(_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    all_rows: list[dict[str, Any]] = []
    lane_reports: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for index, lane in enumerate(lanes):
        if index and safe_delay:
            time.sleep(safe_delay)
        rows, report = _forward_lane_rows(
            lane,
            forward_window_trades=safe_events,
            timeout_seconds=safe_timeout,
            wallet_balance_usd=wallet_balance_usd,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            window_size=window_size,
        )
        lane_reports.append(report)
        if report.get("status") != "ok":
            failed.append(report)
        all_rows.extend(rows)

    inserted = 0
    deduped = 0
    if persist:
        symbols = sorted({str(lane.get("symbol") or "").upper() for lane in lanes if lane.get("symbol")})
        with _connect() as conn:
            if not _table_exists(conn):
                return {
                    "ok": False,
                    "status": "blocked",
                    "blockers": ["paper_trading_ledger_table_missing_create_first"],
                    "would_write": False,
                    "writes_performed": 0,
                    "would_execute_trade": False,
                }
            unique_rows = []
            for event_type in sorted({str(row.get("event_type") or "") for row in all_rows if row.get("event_type")}):
                event_rows = [row for row in all_rows if row.get("event_type") == event_type]
                unique_rows.extend(_dedupe_forward_rows(conn, event_rows, symbols, event_type=event_type))
            deduped = len(all_rows) - len(unique_rows)
            inserted = _insert_ledger_rows(conn, unique_rows)
            conn.commit()

    analytics = get_aster_paper_trading_ledger_analytics(dry_run=True)
    local_analytics = _event_prefix_analytics(PROMOTION_READY_EVENT_TYPE)
    closed_count = sum(_int(report.get("closed_count")) for report in lane_reports)
    cycle_pnl = sum(_float(report.get("cycle_realized_pnl_usd")) for report in lane_reports)
    open_count = sum(_int(report.get("open_count")) for report in lane_reports)
    open_unrealized = sum(_float(report.get("open_unrealized_pnl_usd")) for report in lane_reports)
    row = {
        "timestamp": _now(),
        "mode": "persist" if persist else "dry_run",
        "lanes_count": len(lanes),
        "symbols": ",".join(sorted({str(lane.get("symbol") or "") for lane in lanes})),
        "rows_inserted": inserted,
        "deduped_rows": deduped,
        "would_insert_rows": 0 if persist else len(all_rows),
        "closed_in_cycle": closed_count,
        "cycle_realized_pnl_usd": round(cycle_pnl, 6),
        "cycle_win_rate": None,
        "open_positions_count": open_count,
        "open_unrealized_pnl_usd": round(open_unrealized, 6),
        "ledger_total_entries": analytics.get("total_entries"),
        "ledger_total_exits": analytics.get("total_exits"),
        "ledger_win_rate": analytics.get("win_rate"),
        "ledger_profit_factor": analytics.get("profit_factor"),
        "ledger_net_pnl_usd": analytics.get("net_pnl_usd"),
        "ledger_max_drawdown_usd": analytics.get("max_drawdown_usd"),
        "local_total_entries": local_analytics.get("total_entries"),
        "local_total_exits": local_analytics.get("total_exits"),
        "local_net_pnl_usd": local_analytics.get("net_pnl_usd"),
        "local_win_rate": local_analytics.get("win_rate"),
        "local_profit_factor": local_analytics.get("profit_factor"),
        "failed_lanes_count": len(failed),
        "health_status": "api_degraded" if len(failed) > len(lanes) / 2 else ("active" if all_rows or open_count else "no_signals"),
    }
    _write_forward_row(row)
    heartbeat = {**row, "ok": True, "lane_reports": lane_reports, "csv_path": str(FORWARD_CSV)}
    _write_forward_heartbeat(heartbeat)
    return {
        "ok": True,
        "status": "ready",
        "dry_run": not persist,
        "persist": bool(persist),
        "forward_summary": row,
        "lane_reports": lane_reports,
        "failed_lanes": failed,
        "analytics": analytics,
        "csv_path": str(FORWARD_CSV),
        "heartbeat_path": str(FORWARD_HEARTBEAT),
        "would_write": bool(persist),
        "writes_performed": inserted,
        "would_execute_trade": False,
        "would_send_wallet_transaction": False,
    }


def get_aster_strict_promotion_ready_forward_cycle(
    dry_run: bool = True,
    persist: bool = False,
    confirm: str | None = None,
    forward_window_trades: int = 1_000,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    entry_window_seconds: int = 180,
    trade_limit: int = 500,
    max_funding_bps_for_long: float = 3.0,
) -> dict[str, Any]:
    if persist and confirm != FORWARD_PAPER_TRADE_CONFIRM:
        return {
            "ok": False,
            "status": "blocked",
            "blockers": ["confirm_CONFIRM_FORWARD_PAPER_TRADE_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }
    snapshot = _load_latest_promotion_ready()
    lanes = list(snapshot.get("promotion_ready") or [])
    symbols = sorted({str(lane.get("symbol") or "").upper() for lane in lanes if lane.get("symbol")})
    safe_events = max(50, min(_int(forward_window_trades, 1_000), 1_000))
    safe_timeout = max(1, min(_int(timeout_seconds, 10), 10))
    safe_delay = max(0, min(_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    exchange_snapshot = get_public_exchange_info_snapshot(symbols, timeout_seconds=safe_timeout) if symbols else {}
    funding_snapshot = get_public_funding_history_snapshot(symbols, limit=24, timeout_seconds=safe_timeout) if symbols else {}
    micro_snapshot = get_aster_microstructure_replay_validator_preview(
        champions=[{"symbol": lane.get("symbol"), "interval": lane.get("interval"), "side": lane.get("side") or "long"} for lane in lanes],
        dry_run=True,
        position_notional_usd=100.0,
        trade_limit=500,
        timeout_seconds=safe_timeout,
    )
    micro_by_key = _micro_map(list(micro_snapshot.get("rows") or []))
    all_rows: list[dict[str, Any]] = []
    lane_reports: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for index, lane in enumerate(lanes):
        if index and safe_delay:
            time.sleep(safe_delay)
        symbol = str(lane.get("symbol") or "").upper()
        lane_key = "|".join([symbol, str(lane.get("interval") or ""), str(lane.get("side") or "long")])
        rows, report = _strict_forward_lane_rows(
            lane,
            forward_window_trades=safe_events,
            timeout_seconds=safe_timeout,
            wallet_balance_usd=wallet_balance_usd,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            window_size=window_size,
            current_micro=_micro_summary(micro_by_key.get(lane_key)),
            funding=funding_snapshot.get(symbol) or {},
            exchange=exchange_snapshot.get(symbol) or {},
            entry_window_seconds=entry_window_seconds,
            trade_limit=trade_limit,
            max_funding_bps_for_long=max_funding_bps_for_long,
        )
        lane_reports.append(report)
        if report.get("status") != "ok":
            failed.append(report)
        all_rows.extend(rows)

    inserted = 0
    deduped = 0
    if persist:
        with _connect() as conn:
            if not _table_exists(conn):
                return {
                    "ok": False,
                    "status": "blocked",
                    "blockers": ["paper_trading_ledger_table_missing_create_first"],
                    "would_write": False,
                    "writes_performed": 0,
                    "would_execute_trade": False,
                }
            unique_rows = []
            for event_type in sorted({str(row.get("event_type") or "") for row in all_rows if row.get("event_type")}):
                event_rows = [row for row in all_rows if row.get("event_type") == event_type]
                unique_rows.extend(_dedupe_forward_rows(conn, event_rows, symbols, event_type=event_type))
            deduped = len(all_rows) - len(unique_rows)
            inserted = _insert_ledger_rows(conn, unique_rows)
            conn.commit()

    analytics = get_aster_paper_trading_ledger_analytics(dry_run=True)
    local_analytics = _event_prefix_analytics(STRICT_PROMOTION_READY_EVENT_TYPE)
    closed_count = sum(_int(report.get("closed_count")) for report in lane_reports)
    cycle_pnl = sum(_float(report.get("cycle_realized_pnl_usd")) for report in lane_reports)
    open_count = sum(_int(report.get("open_count")) for report in lane_reports)
    open_unrealized = sum(_float(report.get("open_unrealized_pnl_usd")) for report in lane_reports)
    rejected_entries = sum(_int(report.get("strict_rejected_entries")) for report in lane_reports)
    row = {
        "timestamp": _now(),
        "mode": "persist" if persist else "dry_run",
        "lanes_count": len(lanes),
        "symbols": ",".join(symbols),
        "rows_inserted": inserted,
        "deduped_rows": deduped,
        "would_insert_rows": 0 if persist else len(all_rows),
        "closed_in_cycle": closed_count,
        "cycle_realized_pnl_usd": round(cycle_pnl, 6),
        "cycle_win_rate": None,
        "open_positions_count": open_count,
        "open_unrealized_pnl_usd": round(open_unrealized, 6),
        "ledger_total_entries": analytics.get("total_entries"),
        "ledger_total_exits": analytics.get("total_exits"),
        "ledger_win_rate": analytics.get("win_rate"),
        "ledger_profit_factor": analytics.get("profit_factor"),
        "ledger_net_pnl_usd": analytics.get("net_pnl_usd"),
        "ledger_max_drawdown_usd": analytics.get("max_drawdown_usd"),
        "local_total_entries": local_analytics.get("total_entries"),
        "local_total_exits": local_analytics.get("total_exits"),
        "local_net_pnl_usd": local_analytics.get("net_pnl_usd"),
        "local_win_rate": local_analytics.get("win_rate"),
        "local_profit_factor": local_analytics.get("profit_factor"),
        "failed_lanes_count": len(failed),
        "health_status": "api_degraded" if len(failed) > len(lanes) / 2 else ("active" if all_rows or open_count or rejected_entries else "no_signals"),
    }
    _write_forward_row(row, STRICT_FORWARD_CSV)
    heartbeat = {**row, "ok": True, "lane_reports": lane_reports, "strict_rejected_entries": rejected_entries, "csv_path": str(STRICT_FORWARD_CSV)}
    _write_strict_forward_heartbeat(heartbeat)
    return {
        "ok": True,
        "status": "ready",
        "dry_run": not persist,
        "persist": bool(persist),
        "strict_forward_summary": row,
        "lane_reports": lane_reports,
        "failed_lanes": failed,
        "analytics": analytics,
        "csv_path": str(STRICT_FORWARD_CSV),
        "heartbeat_path": str(STRICT_FORWARD_HEARTBEAT),
        "would_write": bool(persist),
        "writes_performed": inserted,
        "would_execute_trade": False,
        "would_send_wallet_transaction": False,
    }


def get_aster_entry_microstructure_diagnostic_preview(
    dry_run: bool = True,
    forward_window_trades: int = 1_000,
    entry_window_seconds: int = 180,
    timeout_seconds: int = 10,
    trade_limit: int = 500,
    min_trades: int = 30,
    min_quote_volume_usd: float = 5_000.0,
    max_gap_seconds: float = 60.0,
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
    snapshot = _load_latest_promotion_ready()
    lanes = list(snapshot.get("promotion_ready") or [])
    checked_entries: list[dict[str, Any]] = []
    failed_lanes: list[dict[str, Any]] = []
    safe_events = max(50, min(_int(forward_window_trades, 1_000), 1_000))
    safe_timeout = max(1, min(_int(timeout_seconds, 10), 10))
    for lane in lanes:
        symbol = str(lane.get("symbol") or "").upper()
        risk = _risk_params(lane.get("risk_profile"))
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        if not fetched.get("ok"):
            failed_lanes.append({"symbol": symbol, "interval": lane.get("interval"), "fetch_status": fetched.get("fetch_status")})
            continue
        rows, _report = _replay_trades(
            fetched.get("trades") or [],
            f"entry-micro-{symbol}-{lane.get('interval')}",
            symbol,
            1_000.0,
            6.0,
            10.0,
            20,
            min_aster_score=70.0,
            min_window_volume_usd=3_000.0,
            stop_loss_pct=_float(risk.get("stop_loss_pct")),
            take_profit_pct=_float(risk.get("take_profit_pct")),
            trailing_stop_activation_pct=_float(risk.get("trailing_stop_activation_pct")),
            trailing_stop_distance_pct=_float(risk.get("trailing_stop_distance_pct")),
            max_holding_trades=_int(risk.get("max_holding_trades"), 600),
        )
        entries = [row for row in rows if row.get("state") == "executing_entry"]
        for entry in entries[:20]:
            try:
                payload = json.loads(entry.get("raw_payload_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            entry_time = _int(payload.get("trade_time"))
            if entry_time <= 0:
                checked_entries.append(
                    {
                        "symbol": symbol,
                        "interval": lane.get("interval"),
                        "entry_trade_id": payload.get("trade_id"),
                        "verdict": "not_enough_trades",
                        "blockers": ["missing_entry_timestamp"],
                    }
                )
                continue
            window = _fetch_entry_window_trades(symbol, entry_time, entry_window_seconds, trade_limit, safe_timeout)
            trade_metrics = _micro_trade_metrics(window.get("trades") or [])
            pseudo_book = {
                "status": "ok",
                "fillable_at_book_depth": True,
                "spread_bps": 0.0,
                "simulated_slippage_bps": 0.0,
                "top10_depth_usd": 999_999.0,
                "position_notional_usd": 100.0,
            }
            decision = _micro_decision(
                trade_metrics,
                pseudo_book,
                min_trades=max(1, _int(min_trades, 30)),
                min_quote_volume_usd=max(0.0, float(min_quote_volume_usd or 0)),
                max_spread_bps=10_000.0,
                max_slippage_bps=10_000.0,
                max_gap_seconds=max(1.0, float(max_gap_seconds or 60)),
            )
            checked_entries.append(
                {
                    "symbol": symbol,
                    "interval": lane.get("interval"),
                    "side": lane.get("side"),
                    "risk_profile": lane.get("risk_profile"),
                    **_strategy_payload(lane),
                    "entry_trade_id": payload.get("trade_id"),
                    "entry_time": payload.get("trade_time"),
                    "entry_price": entry.get("entry_price") or entry.get("current_price"),
                    "entry_score": entry.get("aster_score"),
                    "fetch_status": window.get("status"),
                    "window_seconds": entry_window_seconds,
                    "trade_count": trade_metrics.get("trade_count"),
                    "quote_volume_usd": trade_metrics.get("quote_volume_usd"),
                    "max_gap_seconds": trade_metrics.get("max_gap_seconds"),
                    "p95_gap_seconds": trade_metrics.get("p95_gap_seconds"),
                    **decision,
                    "method_limit": "historical_order_book_depth_not_available_publicly_so_this_validates_trade_tape_liquidity_at_entry_only",
                }
            )
    counts: dict[str, int] = {}
    for row in checked_entries:
        verdict = str(row.get("verdict") or "unknown")
        counts[verdict] = counts.get(verdict, 0) + 1
    passed = counts.get("microstructure_ok", 0)
    total = len(checked_entries)
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "replay_promotion_ready_lanes_then_validate_public_aggTrades_tape_around_each_entry_timestamp",
        "method_limit": "Aster public API does not expose historical depth snapshots here; spread/slippage at historical entry is approximated by tape liquidity only.",
        "lanes_checked": len(lanes),
        "entries_checked": total,
        "summary_counts": counts,
        "entry_pass_rate": round(passed / total, 6) if total else None,
        "rows": checked_entries,
        "failed_lanes": failed_lanes,
        "safety": {
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "public_endpoints_only": True,
        },
    }


def get_aster_promotion_ready_strict_forward_diagnostic_preview(
    dry_run: bool = True,
    forward_window_trades: int = 1_000,
    entry_window_seconds: int = 180,
    timeout_seconds: int = 10,
    trade_limit: int = 500,
    max_funding_bps_for_long: float = 3.0,
) -> dict[str, Any]:
    """Read-only attribution: do stricter entry filters explain weak forward PnL?"""
    if not dry_run:
        return {
            "ok": False,
            "status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }
    snapshot = _load_latest_promotion_ready()
    lanes = list(snapshot.get("promotion_ready") or [])
    symbols = sorted({str(lane.get("symbol") or "").upper() for lane in lanes if lane.get("symbol")})
    safe_events = max(50, min(_int(forward_window_trades, 1_000), 1_000))
    safe_timeout = max(1, min(_int(timeout_seconds, 10), 10))
    exchange_snapshot = get_public_exchange_info_snapshot(symbols, timeout_seconds=safe_timeout) if symbols else {}
    funding_snapshot = get_public_funding_history_snapshot(symbols, limit=24, timeout_seconds=safe_timeout) if symbols else {}
    current_micro = get_aster_microstructure_replay_validator_preview(
        champions=[
            {
                "symbol": lane.get("symbol"),
                "interval": lane.get("interval"),
                "side": lane.get("side") or "long",
            }
            for lane in lanes
        ],
        dry_run=True,
        position_notional_usd=100.0,
        trade_limit=500,
        timeout_seconds=safe_timeout,
    )
    micro_by_key = _micro_map(list(current_micro.get("rows") or []))

    lane_results: list[dict[str, Any]] = []
    failed_lanes: list[dict[str, Any]] = []
    for lane in lanes:
        symbol = str(lane.get("symbol") or "").upper()
        interval = str(lane.get("interval") or "")
        risk = _risk_params(lane.get("risk_profile"))
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        if not fetched.get("ok"):
            failed_lanes.append({"symbol": symbol, "interval": interval, "fetch_status": fetched.get("fetch_status")})
            continue
        rows, report = _replay_trades(
            fetched.get("trades") or [],
            f"strict-forward-diagnostic-{symbol}-{interval}",
            symbol,
            1_000.0,
            6.0,
            10.0,
            20,
            min_aster_score=70.0,
            min_window_volume_usd=3_000.0,
            stop_loss_pct=_float(risk.get("stop_loss_pct")),
            take_profit_pct=_float(risk.get("take_profit_pct")),
            trailing_stop_activation_pct=_float(risk.get("trailing_stop_activation_pct")),
            trailing_stop_distance_pct=_float(risk.get("trailing_stop_distance_pct")),
            max_holding_trades=_int(risk.get("max_holding_trades"), 600),
        )
        pairs = _closed_trade_pairs(rows)
        entry_checks: dict[str, dict[str, Any]] = {}
        strict_pairs: list[dict[str, Any]] = []
        rejected_pairs: list[dict[str, Any]] = []
        lane_key = "|".join([symbol, interval, str(lane.get("side") or "long")])
        current_micro_summary = _micro_summary(micro_by_key.get(lane_key))
        for pair in pairs:
            entry_time = _int(pair.get("entry_time"))
            entry_id = str(pair.get("entry_trade_id") or "")
            if entry_time <= 0:
                entry_check = {"verdict": "not_enough_trades", "blockers": ["missing_entry_timestamp"]}
            else:
                window = _fetch_entry_window_trades(symbol, entry_time, entry_window_seconds, trade_limit, safe_timeout)
                metrics = _micro_trade_metrics(window.get("trades") or [])
                pseudo_book = {
                    "status": "ok",
                    "fillable_at_book_depth": True,
                    "spread_bps": 0.0,
                    "simulated_slippage_bps": 0.0,
                    "top10_depth_usd": 999_999.0,
                    "position_notional_usd": 100.0,
                }
                decision = _micro_decision(
                    metrics,
                    pseudo_book,
                    min_trades=30,
                    min_quote_volume_usd=5_000.0,
                    max_spread_bps=10_000.0,
                    max_slippage_bps=10_000.0,
                    max_gap_seconds=60.0,
                )
                entry_check = {
                    "trade_count": metrics.get("trade_count"),
                    "quote_volume_usd": metrics.get("quote_volume_usd"),
                    "max_gap_seconds": metrics.get("max_gap_seconds"),
                    "p95_gap_seconds": metrics.get("p95_gap_seconds"),
                    **decision,
                }
            passed, blockers, warnings = _strict_pass(
                lane=lane,
                entry_check=entry_check,
                current_micro=current_micro_summary,
                funding=funding_snapshot.get(symbol) or {},
                exchange=exchange_snapshot.get(symbol) or {},
                max_funding_bps_for_long=max_funding_bps_for_long,
            )
            row = {
                **pair,
                "strict_filter_pass": passed,
                "strict_blockers": blockers,
                "strict_warnings": warnings,
                "entry_micro": entry_check,
            }
            entry_checks[entry_id] = entry_check
            if passed:
                strict_pairs.append(row)
            else:
                rejected_pairs.append(row)

        baseline_pnl = sum(_float(pair.get("pnl_realized_usd")) for pair in pairs)
        strict_pnl = sum(_float(pair.get("pnl_realized_usd")) for pair in strict_pairs)
        rejected_pnl = sum(_float(pair.get("pnl_realized_usd")) for pair in rejected_pairs)
        baseline_wr = round(sum(1 for pair in pairs if _float(pair.get("pnl_realized_usd")) > 0) / len(pairs), 6) if pairs else None
        strict_wr = round(sum(1 for pair in strict_pairs if _float(pair.get("pnl_realized_usd")) > 0) / len(strict_pairs), 6) if strict_pairs else None
        lane_results.append(
            {
                "symbol": symbol,
                "interval": interval,
                "side": lane.get("side"),
                "risk_profile": lane.get("risk_profile"),
                "strategy_profile_id": lane.get("strategy_profile_id"),
                "strategy_profile_key": lane.get("strategy_profile_key"),
                "trigger_reference": lane.get("trigger_reference"),
                "execution_model": lane.get("execution_model"),
                "best_tradable_leverage": lane.get("best_tradable_leverage"),
                "lane_key": _lane_key(lane),
                "lane_strategy_hash": _lane_strategy_hash(lane),
                "market_type": fetched.get("market_type"),
                "closed_pairs": len(pairs),
                "strict_pairs": len(strict_pairs),
                "rejected_pairs": len(rejected_pairs),
                "baseline_pnl_usd": round(baseline_pnl, 6),
                "baseline_win_rate": baseline_wr,
                "strict_filtered_pnl_usd": round(strict_pnl, 6),
                "strict_filtered_win_rate": strict_wr,
                "rejected_pnl_usd": round(rejected_pnl, 6),
                "delta_pnl_usd": round(strict_pnl - baseline_pnl, 6),
                "current_microstructure": current_micro_summary,
                "funding": funding_snapshot.get(symbol) or {},
                "exchange_info": exchange_snapshot.get(symbol) or {},
                "top_rejected_examples": rejected_pairs[:5],
                "top_strict_examples": strict_pairs[:5],
            }
        )

    total_baseline = sum(_float(row.get("baseline_pnl_usd")) for row in lane_results)
    total_strict = sum(_float(row.get("strict_filtered_pnl_usd")) for row in lane_results)
    total_closed = sum(_int(row.get("closed_pairs")) for row in lane_results)
    total_strict_pairs = sum(_int(row.get("strict_pairs")) for row in lane_results)
    strict_improves = total_strict > total_baseline and total_strict_pairs > 0
    verdict = (
        "strict_filter_promising"
        if strict_improves and total_strict >= 0
        else "strict_filter_reduces_damage"
        if strict_improves
        else "strict_filter_not_enough_signal"
        if total_strict_pairs == 0
        else "strict_filter_not_helpful"
    )
    payload = {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "promotion_ready_forward_replay_then_attribute_closed_trades_to_strict_entry_filters",
        "method_limit": "This is attribution, not a full re-simulation after skipped entries; it answers whether losing closed trades would have been blocked by stricter guards.",
        "strict_filters": {
            "entry_tape_min_trades": 50,
            "entry_tape_min_quote_volume_usd": 20_000,
            "entry_tape_max_gap_seconds": 30,
            "current_spread_warning_bps": 8,
            "current_slippage_warning_bps": 8,
            "max_funding_bps_for_long": max_funding_bps_for_long,
        },
        "summary": {
            "lanes_checked": len(lane_results),
            "closed_pairs": total_closed,
            "strict_pairs": total_strict_pairs,
            "baseline_pnl_usd": round(total_baseline, 6),
            "strict_filtered_pnl_usd": round(total_strict, 6),
            "delta_pnl_usd": round(total_strict - total_baseline, 6),
            "verdict": verdict,
        },
        "lane_results": lane_results,
        "failed_lanes": failed_lanes,
        "safety": {
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "public_endpoints_only": True,
        },
    }
    return payload


def get_aster_promotion_ready_strict_ledger_postmortem_preview(
    dry_run: bool = True,
    limit_pairs: int = 60,
    entry_window_seconds: int = 180,
    timeout_seconds: int = 10,
    trade_limit: int = 500,
    max_funding_bps_for_long: float = 3.0,
) -> dict[str, Any]:
    """Read-only postmortem on persisted promotion-ready closed trades."""
    if not dry_run:
        return {
            "ok": False,
            "status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
        }
    pairs = _ledger_promotion_pairs(limit_pairs, event_prefix=STRICT_PROMOTION_READY_EVENT_TYPE)
    symbols = sorted({str(pair.get("symbol") or "").upper() for pair in pairs if pair.get("symbol")})
    exchange_snapshot = get_public_exchange_info_snapshot(symbols, timeout_seconds=timeout_seconds) if symbols else {}
    funding_snapshot = get_public_funding_history_snapshot(symbols, limit=24, timeout_seconds=timeout_seconds) if symbols else {}
    champion_rows = [
        {
            "symbol": pair.get("symbol"),
            "interval": pair.get("interval"),
            "side": pair.get("side") or "long",
        }
        for pair in pairs
    ]
    current_micro = get_aster_microstructure_replay_validator_preview(
        champions=champion_rows,
        dry_run=True,
        position_notional_usd=100.0,
        trade_limit=500,
        timeout_seconds=timeout_seconds,
    )
    micro_by_key = _micro_map(list(current_micro.get("rows") or []))
    strict_pairs: list[dict[str, Any]] = []
    rejected_pairs: list[dict[str, Any]] = []
    for index, pair in enumerate(pairs):
        symbol = str(pair.get("symbol") or "").upper()
        lane = {
            "symbol": symbol,
            "interval": pair.get("interval"),
            "side": pair.get("side") or "long",
            "risk_profile": pair.get("risk_profile"),
            "mark_index_verdict": "not_checked",
        }
        entry_time = _int(pair.get("entry_time"))
        if entry_time <= 0:
            entry_check = {"verdict": "not_enough_trades", "blockers": ["missing_entry_timestamp"]}
        else:
            window = _fetch_entry_window_trades(symbol, entry_time, entry_window_seconds, trade_limit, timeout_seconds)
            metrics = _micro_trade_metrics(window.get("trades") or [])
            pseudo_book = {
                "status": "ok",
                "fillable_at_book_depth": True,
                "spread_bps": 0.0,
                "simulated_slippage_bps": 0.0,
                "top10_depth_usd": 999_999.0,
                "position_notional_usd": 100.0,
            }
            decision = _micro_decision(
                metrics,
                pseudo_book,
                min_trades=30,
                min_quote_volume_usd=5_000.0,
                max_spread_bps=10_000.0,
                max_slippage_bps=10_000.0,
                max_gap_seconds=60.0,
            )
            entry_check = {
                "trade_count": metrics.get("trade_count"),
                "quote_volume_usd": metrics.get("quote_volume_usd"),
                "max_gap_seconds": metrics.get("max_gap_seconds"),
                "p95_gap_seconds": metrics.get("p95_gap_seconds"),
                **decision,
            }
        lane_key = "|".join([symbol, str(pair.get("interval") or ""), str(pair.get("side") or "long")])
        passed, blockers, warnings = _strict_pass(
            lane=lane,
            entry_check=entry_check,
            current_micro=_micro_summary(micro_by_key.get(lane_key)),
            funding=funding_snapshot.get(symbol) or {},
            exchange=exchange_snapshot.get(symbol) or {},
            max_funding_bps_for_long=max_funding_bps_for_long,
        )
        row = {
            **pair,
            "strict_filter_pass": passed,
            "strict_blockers": blockers,
            "strict_warnings": warnings,
            "entry_micro": entry_check,
        }
        if passed:
            strict_pairs.append(row)
        else:
            rejected_pairs.append(row)
        if index and index % 8 == 0:
            time.sleep(0.2)

    baseline_pnl = sum(_float(pair.get("pnl_realized_usd")) for pair in pairs)
    strict_pnl = sum(_float(pair.get("pnl_realized_usd")) for pair in strict_pairs)
    rejected_pnl = sum(_float(pair.get("pnl_realized_usd")) for pair in rejected_pairs)
    baseline_wr = round(sum(1 for pair in pairs if _float(pair.get("pnl_realized_usd")) > 0) / len(pairs), 6) if pairs else None
    strict_wr = round(sum(1 for pair in strict_pairs if _float(pair.get("pnl_realized_usd")) > 0) / len(strict_pairs), 6) if strict_pairs else None
    blocker_counts: dict[str, int] = {}
    for pair in rejected_pairs:
        for blocker in pair.get("strict_blockers") or []:
            blocker_counts[str(blocker)] = blocker_counts.get(str(blocker), 0) + 1
    verdict = (
        "strict_filter_promising"
        if strict_pairs and strict_pnl > baseline_pnl and strict_pnl >= 0
        else "strict_filter_reduces_damage"
        if strict_pairs and strict_pnl > baseline_pnl
        else "strict_filter_not_enough_signal"
        if not strict_pairs
        else "strict_filter_not_helpful"
    )
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "persisted_promotion_ready_ledger_postmortem_with_strict_entry_filters",
        "method_limit": "This is a postmortem attribution test over persisted paper exits, not a full alternate execution path.",
        "summary": {
            "closed_pairs_checked": len(pairs),
            "strict_pairs": len(strict_pairs),
            "rejected_pairs": len(rejected_pairs),
            "baseline_pnl_usd": round(baseline_pnl, 6),
            "strict_filtered_pnl_usd": round(strict_pnl, 6),
            "rejected_pnl_usd": round(rejected_pnl, 6),
            "delta_pnl_usd": round(strict_pnl - baseline_pnl, 6),
            "baseline_win_rate": baseline_wr,
            "strict_win_rate": strict_wr,
            "blocker_counts": blocker_counts,
            "verdict": verdict,
        },
        "strict_examples": strict_pairs[:10],
        "rejected_examples": rejected_pairs[:10],
        "safety": {
            "would_write": False,
            "writes_performed": 0,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "public_endpoints_only": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aster promotion-ready report and forward monitor.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--forward-cycle", action="store_true", help="Run one rolling forward cycle on PROMOTION_READY lanes.")
    actions.add_argument("--entry-micro-diagnostic", action="store_true", help="Validate aggTrades tape liquidity around replay entry timestamps.")
    actions.add_argument("--strict-forward-diagnostic", action="store_true", help="Attribute forward PnL to stricter entry guards without writing.")
    actions.add_argument("--strict-ledger-postmortem", action="store_true", help="Postmortem persisted promotion-ready ledger exits with stricter entry guards.")
    actions.add_argument("--strict-forward-cycle", action="store_true", help="Run strict rolling forward cycle on PROMOTION_READY lanes.")
    parser.add_argument("--persist", action="store_true", help="Persist paper rows into the paper ledger; no real trade.")
    parser.add_argument("--run-forever", action="store_true", help="Repeat forward cycles until CTRL+C.")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=int, default=300)
    parser.add_argument("--forward-window-trades", type=int, default=1000)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--limit-pairs", type=int, default=60)
    args = parser.parse_args()
    if args.strict_ledger_postmortem:
        payload = get_aster_promotion_ready_strict_ledger_postmortem_preview(limit_pairs=args.limit_pairs)
        STRICT_LEDGER_POSTMORTEM_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        summary = payload.get("summary") or {}
        print(
            f"[{payload['generated_at']}] verdict={summary.get('verdict')} "
            f"closed={summary.get('closed_pairs_checked')} strict={summary.get('strict_pairs')} "
            f"baseline_pnl={summary.get('baseline_pnl_usd')} strict_pnl={summary.get('strict_filtered_pnl_usd')} "
            f"json={STRICT_LEDGER_POSTMORTEM_JSON}"
        )
        return
    if args.strict_forward_diagnostic:
        payload = get_aster_promotion_ready_strict_forward_diagnostic_preview(forward_window_trades=args.forward_window_trades)
        STRICT_DIAGNOSTIC_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        summary = payload.get("summary") or {}
        print(
            f"[{payload['generated_at']}] verdict={summary.get('verdict')} "
            f"closed={summary.get('closed_pairs')} strict={summary.get('strict_pairs')} "
            f"baseline_pnl={summary.get('baseline_pnl_usd')} strict_pnl={summary.get('strict_filtered_pnl_usd')} "
            f"json={STRICT_DIAGNOSTIC_JSON}"
        )
        return
    if args.strict_forward_cycle:
        cycles = None if args.run_forever else max(1, min(_int(args.cycles, 1), 288))
        index = 0
        while cycles is None or index < cycles:
            result = get_aster_strict_promotion_ready_forward_cycle(
                persist=bool(args.persist),
                confirm=FORWARD_PAPER_TRADE_CONFIRM if args.persist else None,
                forward_window_trades=args.forward_window_trades,
            )
            summary = result.get("strict_forward_summary") or {}
            rejected = sum(_int(report.get("strict_rejected_entries")) for report in result.get("lane_reports") or [])
            print(
                f"[{summary.get('timestamp')}] strict mode={'persist' if args.persist else 'dry_run'} "
                f"inserted={summary.get('rows_inserted')} exits={summary.get('closed_in_cycle')} "
                f"cycle_pnl={summary.get('cycle_realized_pnl_usd')} strict_pnl={summary.get('local_net_pnl_usd')} "
                f"global_pnl={summary.get('ledger_net_pnl_usd')} rejected={rejected} "
                f"active={summary.get('open_positions_count')} health={summary.get('health_status')}"
            )
            index += 1
            if cycles is None or index < cycles:
                time.sleep(max(1, _int(args.sleep_seconds, 300)))
        return
    if args.entry_micro_diagnostic:
        payload = get_aster_entry_microstructure_diagnostic_preview(forward_window_trades=args.forward_window_trades)
        out = BASE_DIR / "aster_entry_microstructure_diagnostic_latest.json"
        out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        print(f"[{payload['generated_at']}] entries={payload['entries_checked']} counts={payload['summary_counts']} json={out}")
        return
    if args.forward_cycle:
        cycles = None if args.run_forever else max(1, min(_int(args.cycles, 1), 288))
        index = 0
        while cycles is None or index < cycles:
            result = get_aster_promotion_ready_forward_cycle(
                persist=bool(args.persist),
                confirm=FORWARD_PAPER_TRADE_CONFIRM if args.persist else None,
                forward_window_trades=args.forward_window_trades,
            )
            row = result.get("forward_summary") or {}
            print(
                f"[{row.get('timestamp')}] mode={row.get('mode')} lanes={row.get('lanes_count')} "
                f"inserted={row.get('rows_inserted')} exits={row.get('ledger_total_exits')} "
                f"cycle_pnl={row.get('cycle_realized_pnl_usd')} promo_pnl={row.get('local_net_pnl_usd')} "
                f"global_pnl={row.get('ledger_net_pnl_usd')} active={row.get('open_positions_count')} "
                f"latent={row.get('open_unrealized_pnl_usd')} health={row.get('health_status')}"
            )
            index += 1
            if cycles is None or index < cycles:
                time.sleep(max(30, _int(args.sleep_seconds, 300)))
        return

    payload = write_aster_promotion_ready_lanes_report(top_n=args.top_n)
    print(f"[{payload['generated_at']}] candidates={payload['candidates_tested']} counts={payload['summary_counts']} html={HTML_OUT}")


if __name__ == "__main__":
    main()
