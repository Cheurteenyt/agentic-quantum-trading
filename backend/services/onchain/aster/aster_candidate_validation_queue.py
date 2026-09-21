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

JSON_OUT = BASE_DIR / "aster_candidate_validation_queue_latest.json"
CSV_OUT = BASE_DIR / "aster_candidate_validation_queue_latest.csv"
HTML_OUT = DOCS_DIR / "core-equity-aster-candidate-validation-queue.html"
MARK_INDEX_JSON = BASE_DIR / "aster_mark_index_replay_filter_latest.json"
MICROSTRUCTURE_JSON = BASE_DIR / "aster_microstructure_replay_validator_latest.json"

DISCOVERY_PATTERNS = [
    "paper_trading_strategy_discovery_*prod*_progress_v2.csv",
    "paper_trading_strategy_discovery_*prod*_v2.csv",
    "paper_trading_strategy_discovery_*validation*_v2.csv",
    "paper_trading_strategy_discovery_*watchlist*_v2.csv",
    "paper_trading_strategy_discovery_*exchangeinfo*_v2.csv",
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


def _read_csv(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row, source_file=path.name) for row in csv.DictReader(handle)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _mark_index_overlay() -> dict[tuple[str, str], dict[str, Any]]:
    payload = _load_json(MARK_INDEX_JSON)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        interval = str(row.get("interval") or "")
        if symbol and interval:
            out[(symbol, interval)] = row
    return out


def _microstructure_overlay() -> dict[tuple[str, str, str], dict[str, Any]]:
    payload = _load_json(MICROSTRUCTURE_JSON)
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        interval = str(row.get("interval") or "")
        side = str(row.get("side") or "long").lower()
        if symbol and interval:
            out[(symbol, interval, side)] = row
    return out


def _load_rows() -> list[dict[str, Any]]:
    seen_paths: set[Path] = set()
    rows: list[dict[str, Any]] = []
    for pattern in DISCOVERY_PATTERNS:
        for path in sorted(BASE_DIR.glob(pattern)):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            rows.extend(_read_csv(path))
    return rows


def _profile_key(row: dict[str, Any]) -> str:
    profile_id = str(row.get("strategy_profile_id") or "").strip()
    if profile_id:
        return profile_id
    return "|".join(
        [
            str(row.get("output_tag") or ""),
            str(row.get("symbol") or "").upper(),
            str(row.get("side") or "long").lower(),
            str(row.get("interval") or ""),
            str(row.get("search_mode") or ""),
            str(row.get("trigger_reference") or ""),
            str(row.get("execution_model") or ""),
            str(row.get("risk_profile") or ""),
            str(row.get("min_aster_score") or ""),
            str(row.get("min_window_volume_usd") or ""),
            str(row.get("stop_loss_pct") or ""),
            str(row.get("take_profit_pct") or ""),
            str(row.get("max_holding_trades") or ""),
        ]
    )


def _validation_target_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("symbol") or "").upper(),
            str(row.get("side") or "long").lower(),
            str(row.get("interval") or ""),
            str(row.get("trigger_reference") or ""),
            str(row.get("execution_model") or ""),
            str(row.get("output_tag") or ""),
        ]
    )


def _compact(
    row: dict[str, Any],
    mark_index: dict[tuple[str, str], dict[str, Any]],
    microstructure: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper()
    side = str(row.get("side") or "long").lower()
    interval = str(row.get("interval") or "")
    trigger_reference = row.get("trigger_reference") or row.get("assumed_trigger_reference")
    execution_model = row.get("execution_model") or row.get("assumed_execution_model")
    mark_overlay = mark_index.get((symbol, interval)) or {}
    micro_overlay = microstructure.get((symbol, interval, side)) or {}
    overlay_mark = mark_overlay.get("verdict")
    return {
        "strategy_profile_id": row.get("strategy_profile_id") or _profile_key(row),
        "strategy_profile_family": row.get("strategy_profile_family"),
        "strategy_profile_key": row.get("strategy_profile_key"),
        "output_tag": row.get("output_tag"),
        "source_file": row.get("source_file"),
        "symbol": symbol,
        "side": side,
        "interval": interval,
        "search_mode": row.get("search_mode"),
        "trigger_reference": trigger_reference,
        "execution_model": execution_model,
        "risk_profile": row.get("risk_profile"),
        "min_aster_score": _float(row.get("min_aster_score")),
        "min_window_volume_usd": _float(row.get("min_window_volume_usd")),
        "stop_loss_pct": _float(row.get("stop_loss_pct")),
        "take_profit_pct": _float(row.get("take_profit_pct")),
        "trailing_stop_activation_pct": _float(row.get("trailing_stop_activation_pct")),
        "trailing_stop_distance_pct": _float(row.get("trailing_stop_distance_pct")),
        "max_holding_trades": _int(row.get("max_holding_trades")),
        "closed_trades": _int(row.get("closed_trades")),
        "entries": _int(row.get("entries")),
        "win_rate": _float(row.get("win_rate")),
        "profit_factor": _float(row.get("profit_factor")),
        "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
        "pnl_total_usd": _float(row.get("pnl_total_usd")),
        "max_drawdown_usd": _float(row.get("max_drawdown_usd")),
        "best_tradable_leverage": _float(row.get("best_tradable_leverage"), 1.0),
        "funding_status": row.get("funding_status"),
        "funding_avg_bps_per_8h": row.get("funding_avg_bps_per_8h"),
        "funding_cost_usd_estimate": row.get("funding_cost_usd_estimate"),
        "mark_index_verdict": overlay_mark or row.get("mark_index_verdict") or "not_checked",
        "mark_index_source": "latest_replay_filter" if overlay_mark else "csv",
        "mark_index_warnings": ",".join(mark_overlay.get("warnings") or []) if mark_overlay else row.get("mark_index_warnings"),
        "mark_index_blockers": ",".join(mark_overlay.get("blockers") or []) if mark_overlay else row.get("mark_index_blockers"),
        "ws_quality_verdict": row.get("ws_quality_verdict") or "not_checked",
        "ws_quality_score": row.get("ws_quality_score"),
        "exchange_filter_verdict": row.get("exchange_filter_verdict") or "not_checked",
        "exchange_filter_warnings": row.get("exchange_filter_warnings"),
        "exchange_filter_blockers": row.get("exchange_filter_blockers"),
        "market_take_bound": row.get("market_take_bound"),
        "min_notional": row.get("min_notional"),
        "microstructure_verdict": micro_overlay.get("verdict") or "not_checked",
        "microstructure_blockers": ",".join(micro_overlay.get("blockers") or []) if micro_overlay else "",
        "microstructure_warnings": ",".join(micro_overlay.get("warnings") or []) if micro_overlay else "",
    }


def _quality_score(row: dict[str, Any]) -> float:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = min(_float(row.get("profit_factor")), 25.0)
    wr = _float(row.get("win_rate"))
    closed = _int(row.get("closed_trades"))
    dd = _float(row.get("max_drawdown_usd"))
    leverage = _float(row.get("best_tradable_leverage"), 1.0)
    mark = str(row.get("mark_index_verdict") or "not_checked")
    ws = str(row.get("ws_quality_verdict") or "not_checked")
    exchange = str(row.get("exchange_filter_verdict") or "not_checked")
    micro = str(row.get("microstructure_verdict") or "not_checked")

    score = 0.0
    score += max(min(roi, 50.0), -30.0) * 1.15
    score += min(pf, 12.0) * 4.2
    score += wr * 24.0
    score += min(closed, 80) * 0.32
    score -= min(dd, 100.0) * 0.18
    score += min(leverage, 10.0) * 0.4

    if mark == "mark_index_confirmed":
        score += 8
    elif mark == "mark_index_watch":
        score += 2
    elif mark == "mark_index_rejected":
        score -= 35

    if ws == "ws_forward_ready":
        score += 8
    elif ws == "ws_forward_watch":
        score += 2
    elif ws in {"ws_forward_risky", "risky"}:
        score -= 18

    if exchange == "ok":
        score += 5
    elif exchange == "warning":
        score += 1
    elif exchange == "blocked":
        score -= 35
    if micro == "microstructure_ok":
        score += 8
    elif micro in {"gap_risk", "thin_liquidity", "not_enough_trades"}:
        score -= 18

    return round(max(0.0, min(score, 100.0)), 3)


def _action(row: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    closed = _int(row.get("closed_trades"))
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = _float(row.get("profit_factor"))
    wr = _float(row.get("win_rate"))
    mark = str(row.get("mark_index_verdict") or "not_checked")
    ws = str(row.get("ws_quality_verdict") or "not_checked")
    exchange = str(row.get("exchange_filter_verdict") or "not_checked")
    micro = str(row.get("microstructure_verdict") or "not_checked")

    if closed < 8:
        blockers.append("sample_lt_8")
    if roi <= 0:
        blockers.append("roi_non_positive")
    if pf < 1.3:
        blockers.append("pf_lt_1_3")
    if wr < 0.5:
        blockers.append("winrate_lt_50")
    if exchange == "blocked":
        blockers.append("exchange_filter_blocked")
    if mark == "mark_index_rejected":
        blockers.append("mark_index_rejected")
    if ws in {"ws_forward_risky", "risky"}:
        blockers.append("ws_forward_risky")
    if micro in {"gap_risk", "thin_liquidity", "not_enough_trades"}:
        blockers.append(f"microstructure_{micro}")

    hard_blockers = {
        "sample_lt_8",
        "roi_non_positive",
        "pf_lt_1_3",
        "winrate_lt_50",
        "exchange_filter_blocked",
        "mark_index_rejected",
        "ws_forward_risky",
        "microstructure_gap_risk",
        "microstructure_thin_liquidity",
        "microstructure_not_enough_trades",
    }
    if any(blocker in hard_blockers for blocker in blockers):
        return "reject_or_rework", blockers

    if mark == "not_checked":
        return "validate_mark_index_first", blockers
    if ws == "not_checked":
        return "validate_ws_quality_first", blockers
    if micro == "not_checked":
        return "microstructure_review_required", blockers
    if mark == "mark_index_watch":
        return "microstructure_review_required", blockers
    if ws == "ws_forward_watch":
        return "ws_watch_forward_small_only", blockers
    if exchange == "warning":
        return "exchange_warning_review", blockers
    if closed >= 20 and roi >= 10 and pf >= 1.5 and mark == "mark_index_confirmed" and ws == "ws_forward_ready":
        return "ready_for_strict_forward_candidate", blockers
    return "keep_collecting_backtest", blockers


def _dedupe_best(
    rows: list[dict[str, Any]],
    mark_index: dict[tuple[str, str], dict[str, Any]],
    microstructure: dict[tuple[str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for source in rows:
        row = _compact(source, mark_index, microstructure)
        if not row.get("symbol"):
            continue
        row["validation_score"] = _quality_score(row)
        action, blockers = _action(row)
        row["next_validation_action"] = action
        row["validation_blockers"] = ",".join(blockers)
        key = _profile_key(row)
        existing = best.get(key)
        if existing is None or _float(row.get("validation_score")) > _float(existing.get("validation_score")):
            best[key] = row
    return sorted(best.values(), key=lambda item: (_float(item.get("validation_score")), _float(item.get("roi_pct_on_paper_balance"))), reverse=True)


def _best_by_symbol(rows: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol not in best or _float(row.get("validation_score")) > _float(best[symbol].get("validation_score")):
            best[symbol] = row
    return sorted(best.values(), key=lambda item: _float(item.get("validation_score")), reverse=True)[:limit]


def _best_by_validation_target(rows: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _validation_target_key(row)
        if not key:
            continue
        existing = best.get(key)
        if existing is None or _float(row.get("validation_score")) > _float(existing.get("validation_score")):
            best[key] = row
    return sorted(best.values(), key=lambda item: _float(item.get("validation_score")), reverse=True)[:limit]


def get_aster_candidate_validation_queue_preview(dry_run: bool = True, top_n: int = 80) -> dict[str, Any]:
    if not dry_run:
        return {"ok": False, "status": "blocked", "blockers": ["dry_run_required"]}

    source_rows = _load_rows()
    mark_index = _mark_index_overlay()
    microstructure = _microstructure_overlay()
    rows = _dedupe_best(source_rows, mark_index, microstructure)
    clean_rows = rows[: max(1, min(_int(top_n, 80), 500))]
    target_rows = _best_by_validation_target(rows, 200)
    action_counts: dict[str, int] = {}
    for row in target_rows:
        action = str(row.get("next_validation_action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1

    queue = [row for row in target_rows if row.get("next_validation_action") not in {"reject_or_rework"}]
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "read_discovery_csvs_dedupe_strategy_profiles_rank_next_validation_action",
        "summary": {
            "source_rows_read": len(source_rows),
            "mark_index_overlay_rows": len(mark_index),
            "microstructure_overlay_rows": len(microstructure),
            "strategy_profiles_ranked": len(rows),
            "validation_targets_ranked": len(target_rows),
            "rows_returned": len(clean_rows),
            "action_counts": action_counts,
            "top_actionable": queue[0].get("symbol") if queue else None,
            "top_actionable_action": queue[0].get("next_validation_action") if queue else None,
        },
        "next_validation_queue": queue[:30],
        "top_by_symbol": _best_by_symbol(clean_rows, 40),
        "rows": clean_rows,
        "safety": {
            "would_write_db": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "local_artifacts_only": True,
        },
    }


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _pct(value: Any) -> str:
    return f"{_float(value) * 100:.2f}%"


def _table(rows: list[dict[str, Any]], limit: int = 60) -> str:
    headers = [
        "action",
        "score",
        "symbol",
        "side",
        "tf",
        "roi",
        "wr",
        "pf",
        "trades",
        "mark",
        "micro",
        "ws",
        "xinfo",
        "tag",
    ]
    body = []
    for row in rows[:limit]:
        cells = [
            row.get("next_validation_action"),
            row.get("validation_score"),
            row.get("symbol"),
            row.get("side"),
            row.get("interval"),
            row.get("roi_pct_on_paper_balance"),
            _pct(row.get("win_rate")),
            row.get("profit_factor"),
            row.get("closed_trades"),
            row.get("mark_index_verdict"),
            row.get("microstructure_verdict"),
            row.get("ws_quality_verdict"),
            row.get("exchange_filter_verdict"),
            row.get("output_tag"),
        ]
        body.append("<tr>" + "".join(f"<td>{_cell(value)}</td>" for value in cells) + "</tr>")
    return "<table><thead><tr>" + "".join(f"<th>{_cell(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    counts = summary.get("action_counts") or {}
    count_html = "".join(f"<span><b>{_cell(key)}</b> {_cell(value)}</span>" for key, value in sorted(counts.items()))
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aster - Candidate validation queue</title>
  <style>
    body {{ margin:0; background:#0d1117; color:#e7edf7; font-family:Verdana,Arial,sans-serif; }}
    main {{ max-width:1480px; margin:0 auto; padding:32px 28px 70px; }}
    h1 {{ margin:0 0 8px; font-size:30px; }}
    .lead {{ color:#a9b7c8; max-width:980px; line-height:1.6; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    .card {{ background:#151b24; border:1px solid #263142; border-radius:14px; padding:16px; }}
    .card span {{ display:block; color:#8fa1b8; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .card strong {{ display:block; margin-top:8px; font-size:24px; }}
    .counts {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0; }}
    .counts span {{ background:#172233; border:1px solid #2c3d55; border-radius:999px; padding:8px 12px; color:#c9d7e8; }}
    table {{ width:100%; border-collapse:collapse; margin-top:16px; background:#111821; border:1px solid #273447; }}
    th,td {{ padding:9px 10px; border-bottom:1px solid #253244; text-align:left; font-size:13px; }}
    th {{ color:#91a7c2; background:#17202c; position:sticky; top:0; }}
    .note {{ margin-top:22px; color:#a9b7c8; line-height:1.55; }}
    code {{ color:#ffcf8a; }}
    a {{ color:#8ad6ff; }}
  </style>
</head>
<body>
<main>
  <h1>Aster - File de validation des candidats</h1>
  <p class="lead">Ce rapport lit les CSV de discovery V2, deduplique les strategies par profil complet, puis transforme les backtests en actions: valider mark/index, valider WS, revue microstructure, forward strict ou rejet. Il ne lance aucun backtest et ne trade pas.</p>
  <div class="cards">
    <div class="card"><span>Lignes lues</span><strong>{_cell(summary.get("source_rows_read"))}</strong></div>
    <div class="card"><span>Profils classes</span><strong>{_cell(summary.get("strategy_profiles_ranked"))}</strong></div>
    <div class="card"><span>Top actionable</span><strong>{_cell(summary.get("top_actionable"))}</strong></div>
    <div class="card"><span>Action</span><strong>{_cell(summary.get("top_actionable_action"))}</strong></div>
  </div>
  <div class="counts">{count_html}</div>
  <h2>Queue prioritaire</h2>
  {_table(payload.get("next_validation_queue") or [], 50)}
  <h2>Meilleur profil par symbole</h2>
  {_table(payload.get("top_by_symbol") or [], 40)}
  <p class="note">Lecture: <code>validate_mark_index_first</code> et <code>validate_ws_quality_first</code> ne sont pas des validations de profit. Ce sont des controles de realisme. Une lane rentable mais non validee reste une piste, pas une strategie promouvable.</p>
</main>
</body>
</html>"""


def _write_csv(rows: list[dict[str, Any]]) -> None:
    fields = [
        "next_validation_action",
        "validation_score",
        "validation_blockers",
        "symbol",
        "side",
        "interval",
        "output_tag",
        "search_mode",
        "trigger_reference",
        "execution_model",
        "risk_profile",
        "roi_pct_on_paper_balance",
        "win_rate",
        "profit_factor",
        "closed_trades",
        "max_drawdown_usd",
        "mark_index_verdict",
        "mark_index_source",
        "microstructure_verdict",
        "ws_quality_verdict",
        "exchange_filter_verdict",
        "strategy_profile_id",
        "strategy_profile_family",
        "strategy_profile_key",
        "best_tradable_leverage",
        "source_file",
    ]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_aster_candidate_validation_queue(top_n: int = 120) -> dict[str, Any]:
    payload = get_aster_candidate_validation_queue_preview(dry_run=True, top_n=top_n)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(list(payload.get("next_validation_queue") or []))
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_aster_candidate_validation_queue()
    summary = payload.get("summary") or {}
    print(
        f"[{payload.get('generated_at')}] profiles={summary.get('strategy_profiles_ranked')} "
        f"top={summary.get('top_actionable')} action={summary.get('top_actionable_action')} "
        f"csv={CSV_OUT} html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
