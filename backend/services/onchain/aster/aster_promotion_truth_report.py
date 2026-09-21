from __future__ import annotations

import html
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"

PROMOTION_JSON = BASE_DIR / "aster_promotion_ready_lanes_latest.json"
TRUTH_JSON = BASE_DIR / "aster_strategy_truth_report_latest.json"
STRICT_DIAGNOSTIC_JSON = BASE_DIR / "aster_promotion_ready_strict_forward_diagnostic_latest.json"
STRICT_POSTMORTEM_JSON = BASE_DIR / "aster_promotion_ready_strict_ledger_postmortem_latest.json"
ENTRY_MICRO_JSON = BASE_DIR / "aster_entry_microstructure_diagnostic_latest.json"

JSON_OUT = BASE_DIR / "aster_promotion_truth_report_latest.json"
HTML_OUT = DOCS_DIR / "core-equity-aster-promotion-truth-report.html"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "status": "missing", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"ok": False, "status": "not_dict", "path": str(path)}
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "invalid_json", "path": str(path), "error": type(exc).__name__}


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


def _has_strategy_identity(row: dict[str, Any]) -> bool:
    return any(
        str(row.get(key) or "").strip()
        for key in ("strategy_profile_id", "strategy_profile_key", "trigger_reference", "execution_model", "best_tradable_leverage", "output_tag")
    )


def _base_lane_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("symbol") or "").upper(),
            str(row.get("interval") or ""),
            str(row.get("side") or "long").lower(),
        ]
    )


def _truth_rank(row: dict[str, Any]) -> tuple[int, float, float]:
    return (
        {"PROMOTE": 5, "WATCH": 4, "OPEN_RISK_REVIEW": 3, "INSUFFICIENT_SAMPLE": 2, "STOP_OR_REWORK": 1}.get(
            str(row.get("truth_verdict") or ""), 0
        ),
        _float(row.get("total_pnl_including_latent_usd")),
        _float(row.get("profit_factor")),
    )


def _lane_event_truth(rows: list[dict[str, Any]], lane: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if not _has_strategy_identity(lane):
        return None, "identity_missing"
    symbol = str(lane.get("symbol") or "").upper()
    interval = str(lane.get("interval") or "").lower()
    side = str(lane.get("side") or "long").lower()
    symbol_lower = symbol.lower()
    strategy_hash = _lane_strategy_hash(lane)
    strategy_token = f"{symbol_lower}_{interval}_{side}_{strategy_hash}"
    strategy_matches = [
        row
        for row in rows
        if strategy_token and strategy_token in str(row.get("event_type") or "").lower()
    ]
    if strategy_matches:
        return sorted(strategy_matches, key=_truth_rank, reverse=True)[0], "exact_strategy_lane"
    return None, "not_found"


def _symbol_event_truth(rows: list[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    symbol_upper = symbol.upper()
    matches = [
        row
        for row in rows
        if symbol_upper in {part.strip().upper() for part in str(row.get("symbols") or "").split(",")}
    ]
    if not matches:
        return None
    return sorted(matches, key=_truth_rank, reverse=True)[0]


def _strict_by_lane(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _lane_key(row)
        out[key] = row
    return out


def _entry_micro_by_lane(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _lane_key(row)
        out.setdefault(key, []).append(row)
    return out


def _strict_postmortem_summary(data: dict[str, Any]) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "strict_postmortem_verdict": summary.get("verdict"),
        "strict_pairs": summary.get("strict_pairs"),
        "strict_win_rate": summary.get("strict_win_rate"),
        "strict_filtered_pnl_usd": summary.get("strict_filtered_pnl_usd"),
        "baseline_pnl_usd": summary.get("baseline_pnl_usd"),
        "delta_pnl_usd": summary.get("delta_pnl_usd"),
    }


def _final_verdict(row: dict[str, Any]) -> tuple[str, str]:
    promotion = str(row.get("promotion_decision") or "")
    truth = str(row.get("truth_verdict") or "")
    truth_scope = str(row.get("truth_match_scope") or "")
    micro = str(row.get("microstructure_verdict") or "")
    strict_pnl = row.get("strict_filtered_pnl_usd")
    strict_pairs = _int(row.get("strict_pairs"))
    truth_total = _float(row.get("truth_total_pnl_usd"))
    truth_pf = _float(row.get("truth_profit_factor"))
    truth_exits = _int(row.get("truth_total_exits"))
    blockers = [str(row.get("micro_blockers") or ""), str(row.get("strict_blockers") or "")]

    if promotion != "PROMOTION_READY":
        return "REJECT_PRE_FORWARD", "La lane ne passe pas le filtre promotion-ready initial."
    if micro != "microstructure_ok":
        return "REJECT_MICROSTRUCTURE", "Microstructure publique insuffisante."
    if truth == "PROMOTE" and truth_scope in {"exact_strategy_lane", "exact_side_lane", "legacy_exact_lane"} and truth_total > 0 and truth_pf >= 1.3 and truth_exits >= 8:
        return "PROMOTE_FORWARD_ONLY", "Backtest, microstructure et forward truth sont alignes."
    if truth == "PROMOTE" and truth_scope not in {"exact_strategy_lane", "exact_side_lane", "legacy_exact_lane"}:
        return "WATCH_MORE_FORWARD", "Truth positif trouve sur le symbole, mais pas sur la meme lane interval/side."
    if strict_pairs > 0 and strict_pnl is not None and _float(strict_pnl) > 0:
        return "WATCH_STRICT_FORWARD", "Le filtre strict semble ameliorer la qualite, mais il manque un truth event directement promu."
    if any(blocker.strip() for blocker in blockers):
        return "WATCH_BLOCKERS", "Des blockers restent presents malgre la promotion initiale."
    return "WATCH_MORE_FORWARD", "Promotion initiale OK, mais le forward truth n'est pas encore assez conclusif."


def _merge_reports() -> dict[str, Any]:
    promotion = _load(PROMOTION_JSON)
    truth = _load(TRUTH_JSON)
    strict_diag = _load(STRICT_DIAGNOSTIC_JSON)
    strict_postmortem = _load(STRICT_POSTMORTEM_JSON)
    entry_micro = _load(ENTRY_MICRO_JSON)

    promotion_rows = list(promotion.get("rows") or [])
    truth_rows = list(truth.get("rows") or [])
    strict_rows = _strict_by_lane(list(strict_diag.get("lane_results") or []))
    micro_rows = _entry_micro_by_lane(list(entry_micro.get("rows") or []))
    postmortem = _strict_postmortem_summary(strict_postmortem)

    rows: list[dict[str, Any]] = []
    for source in promotion_rows:
        key = _lane_key(source)
        symbol = str(source.get("symbol") or "").upper()
        strict = strict_rows.get(key) or {}
        micro_entries = micro_rows.get(key) or []
        truth_match, truth_scope = _lane_event_truth(truth_rows, source)
        truth_match = truth_match or {}
        entry_ok = sum(1 for item in micro_entries if item.get("verdict") == "microstructure_ok")
        entry_total = len(micro_entries)
        merged = {
            "lane_key": key,
            "symbol": symbol,
            "interval": source.get("interval"),
            "side": source.get("side") or "long",
            "risk_profile": source.get("risk_profile"),
            "backtest_roi_pct": source.get("roi_pct_on_paper_balance"),
            "backtest_win_rate": source.get("win_rate"),
            "backtest_profit_factor": source.get("profit_factor"),
            "backtest_closed_trades": source.get("closed_trades"),
            "backtest_max_drawdown_usd": source.get("max_drawdown_usd"),
            "mark_index_verdict": source.get("mark_index_verdict"),
            "exchange_filter_verdict": source.get("exchange_filter_verdict"),
            "promotion_decision": source.get("promotion_decision"),
            "promotion_reason": source.get("promotion_reason"),
            "microstructure_verdict": source.get("microstructure_verdict"),
            "micro_trade_count": source.get("micro_trade_count"),
            "micro_quote_volume_usd": source.get("micro_quote_volume_usd"),
            "micro_spread_bps": source.get("micro_spread_bps"),
            "micro_slippage_bps": source.get("micro_slippage_bps"),
            "strategy_profile_id": source.get("strategy_profile_id"),
            "trigger_reference": source.get("trigger_reference"),
            "execution_model": source.get("execution_model"),
            "best_tradable_leverage": source.get("best_tradable_leverage"),
            "micro_blockers": source.get("micro_blockers"),
            "entry_micro_checks": entry_total,
            "entry_micro_ok": entry_ok,
            "strict_filtered_pnl_usd": strict.get("strict_filtered_pnl_usd"),
            "strict_filtered_win_rate": strict.get("strict_filtered_win_rate"),
            "strict_pairs": strict.get("strict_pairs"),
            "baseline_pnl_usd": strict.get("baseline_pnl_usd"),
            "delta_pnl_usd": strict.get("delta_pnl_usd"),
            "strict_blockers": ",".join(sorted({b for item in (strict.get("rejected_pairs") or []) for b in item.get("strict_blockers", [])}))
            if isinstance(strict.get("rejected_pairs"), list)
            else "",
            "truth_event_type": truth_match.get("event_type"),
            "truth_match_scope": truth_scope,
            "truth_verdict": truth_match.get("truth_verdict"),
            "truth_total_pnl_usd": truth_match.get("total_pnl_including_latent_usd"),
            "truth_net_pnl_usd": truth_match.get("net_pnl_usd"),
            "truth_latent_pnl_usd": truth_match.get("latent_pnl_usd"),
            "truth_total_exits": truth_match.get("total_exits"),
            "truth_win_rate": truth_match.get("win_rate"),
            "truth_profit_factor": truth_match.get("profit_factor"),
        }
        verdict, reason = _final_verdict(merged)
        merged["final_verdict"] = verdict
        merged["final_reason"] = reason
        rows.append(merged)

    rank = {
        "PROMOTE_FORWARD_ONLY": 5,
        "WATCH_STRICT_FORWARD": 4,
        "WATCH_MORE_FORWARD": 3,
        "WATCH_BLOCKERS": 2,
        "REJECT_MICROSTRUCTURE": 1,
        "REJECT_PRE_FORWARD": 0,
    }
    rows.sort(
        key=lambda row: (
            rank.get(str(row.get("final_verdict")), 0),
            _float(row.get("truth_total_pnl_usd")),
            _float(row.get("backtest_roi_pct")),
        ),
        reverse=True,
    )
    counts: dict[str, int] = {}
    for row in rows:
        verdict = str(row.get("final_verdict") or "UNKNOWN")
        counts[verdict] = counts.get(verdict, 0) + 1
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "merge_promotion_ready_microstructure_strict_forward_postmortem_and_strategy_truth_by_lane",
        "source_files": {
            "promotion_ready": str(PROMOTION_JSON),
            "strategy_truth": str(TRUTH_JSON),
            "strict_forward_diagnostic": str(STRICT_DIAGNOSTIC_JSON),
            "strict_postmortem": str(STRICT_POSTMORTEM_JSON),
            "entry_microstructure": str(ENTRY_MICRO_JSON),
        },
        "source_generated_at": {
            "promotion_ready": promotion.get("generated_at"),
            "strategy_truth": truth.get("generated_at"),
            "strict_forward_diagnostic": strict_diag.get("generated_at"),
            "strict_postmortem": strict_postmortem.get("generated_at"),
            "entry_microstructure": entry_micro.get("generated_at"),
        },
        "summary": {
            "lanes": len(rows),
            "verdict_counts": counts,
            "promote_forward_only": counts.get("PROMOTE_FORWARD_ONLY", 0),
            "watch_total": sum(count for verdict, count in counts.items() if verdict.startswith("WATCH")),
            "reject_total": sum(count for verdict, count in counts.items() if verdict.startswith("REJECT")),
            **postmortem,
        },
        "rows": rows,
        "promote": [row for row in rows if row.get("final_verdict") == "PROMOTE_FORWARD_ONLY"],
        "watch": [row for row in rows if str(row.get("final_verdict") or "").startswith("WATCH")],
        "reject": [row for row in rows if str(row.get("final_verdict") or "").startswith("REJECT")],
        "safety": {
            "would_write_db": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "public_or_local_artifacts_only": True,
        },
    }


def get_aster_promotion_truth_report_preview(dry_run: bool = True) -> dict[str, Any]:
    if not dry_run:
        return {"ok": False, "status": "blocked", "blockers": ["dry_run_required"]}
    return _merge_reports()


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _usd(value: Any) -> str:
    return f"{_float(value):+.6f}"


def _pct(value: Any) -> str:
    if value in (None, ""):
        return ""
    return f"{_float(value) * 100:.2f}%"


def _table(rows: list[dict[str, Any]], limit: int = 100) -> str:
    if not rows:
        return "<p class='muted'>Aucune lane dans cette categorie.</p>"
    body = []
    for row in rows[:limit]:
        klass = str(row.get("final_verdict") or "").lower()
        body.append(
            "<tr class='%s'>"
            "<td><b>%s</b><br><code>%s</code></td>"
            "<td>%s %s %s</td>"
            "<td>%s%% / %s / %s</td>"
            "<td>%s<br>%s trades, %s USD vol</td>"
            "<td>%s<br>%s exits, PF %s<br><small>%s</small></td>"
            "<td>%s<br>%s</td>"
            "</tr>"
            % (
                _cell(klass),
                _cell(row.get("final_verdict")),
                _cell(row.get("lane_key")),
                _cell(row.get("symbol")),
                _cell(row.get("interval")),
                _cell(row.get("side")),
                _cell(row.get("backtest_roi_pct")),
                _pct(row.get("backtest_win_rate")),
                _cell(row.get("backtest_profit_factor")),
                _cell(row.get("microstructure_verdict")),
                _cell(row.get("micro_trade_count")),
                _cell(row.get("micro_quote_volume_usd")),
                _cell(row.get("truth_verdict")),
                _cell(row.get("truth_total_exits")),
                _cell(row.get("truth_profit_factor")),
                _cell(row.get("truth_match_scope")),
                _cell(row.get("final_reason")),
                _cell(row.get("truth_event_type")),
            )
        )
    return (
        "<table><thead><tr><th>Verdict</th><th>Lane</th><th>Backtest ROI / WR / PF</th>"
        "<th>Microstructure</th><th>Truth forward</th><th>Raison</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Core Equity - Aster Promotion Truth</title>
  <style>
    :root {{ --bg:#0b1014; --panel:#141c24; --line:#2b3a49; --text:#f1f6fb; --muted:#aab7c4; --green:#58d68d; --amber:#f4c76b; --red:#ff7474; --blue:#75b7ff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--text); background:radial-gradient(circle at 8% 0%,rgba(117,183,255,.16),transparent 34%),radial-gradient(circle at 100% 8%,rgba(88,214,141,.12),transparent 32%),var(--bg); font-family:"Segoe UI","Aptos",sans-serif; line-height:1.55; }}
    header {{ padding:44px 56px 30px; border-bottom:1px solid var(--line); }}
    main {{ max-width:1480px; margin:0 auto; padding:30px 56px 68px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(32px,4vw,54px); letter-spacing:-.055em; line-height:1.04; }}
    h2 {{ margin:0 0 16px; font-size:23px; }}
    p {{ margin:0 0 12px; color:var(--muted); }}
    a {{ color:#a8d9ff; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    code {{ background:#091018; border:1px solid #213142; border-radius:7px; padding:2px 6px; color:#dcecff; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }}
    .card {{ background:rgba(20,28,36,.94); border:1px solid var(--line); border-radius:22px; padding:22px; box-shadow:0 18px 50px rgba(0,0,0,.22); }}
    .section {{ margin-top:22px; }}
    .kpis {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .kpi {{ background:#101821; border:1px solid var(--line); border-radius:18px; padding:15px; }}
    .kpi strong {{ display:block; font-size:28px; letter-spacing:-.035em; }}
    .kpi span {{ display:block; color:var(--muted); font-size:12px; margin-top:5px; }}
    table {{ width:100%; border-collapse:collapse; border-radius:14px; overflow:hidden; font-size:13px; }}
    th,td {{ padding:10px 11px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ background:#101820; color:#dceaff; text-transform:uppercase; font-size:11px; letter-spacing:.065em; }}
    tr:last-child td {{ border-bottom:0; }}
    tr.promote_forward_only td:first-child {{ color:var(--green); font-weight:900; }}
    tr.watch_strict_forward td:first-child, tr.watch_more_forward td:first-child, tr.watch_blockers td:first-child {{ color:var(--amber); font-weight:900; }}
    tr.reject_microstructure td:first-child, tr.reject_pre_forward td:first-child {{ color:var(--red); font-weight:900; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    .nav a {{ display:inline-flex; padding:8px 11px; border:1px solid var(--line); border-radius:999px; background:#101820; font-size:13px; font-weight:800; }}
    .muted {{ color:var(--muted); }}
    .green {{ color:var(--green); }} .amber {{ color:var(--amber); }} .red {{ color:var(--red); }} .blue {{ color:var(--blue); }}
    @media (max-width:980px) {{ header,main {{ padding-left:22px; padding-right:22px; }} .grid,.kpis {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Aster Promotion Truth Report</h1>
    <p>Rapport strict qui croise promotion-ready, microstructure, diagnostics strict forward et strategy truth.</p>
    <p class="muted">Genere le {_cell(payload.get('generated_at'))}. Read-only: aucun trade, aucun wallet, aucun write DB.</p>
    <nav class="nav">
      <a href="core-equity-aster-documentation-hub.html">Hub Aster</a>
      <a href="core-equity-aster-strategy-truth-report.html">Strategy truth</a>
      <a href="core-equity-aster-current-state.html">Etat actuel</a>
      <a href="core-equity-aster-promotion-ready-lanes.html">Promotion lanes source</a>
    </nav>
  </header>
  <main>
    <section class="card">
      <h2>Resume final</h2>
      <div class="kpis">
        <div class="kpi"><strong>{_cell(summary.get('lanes'))}</strong><span>lanes croisees</span></div>
        <div class="kpi"><strong class="green">{_cell(summary.get('promote_forward_only'))}</strong><span>promote forward-only</span></div>
        <div class="kpi"><strong class="amber">{_cell(summary.get('watch_total'))}</strong><span>watch</span></div>
        <div class="kpi"><strong class="red">{_cell(summary.get('reject_total'))}</strong><span>reject</span></div>
      </div>
      <p class="muted" style="margin-top:12px">Le rapport ne promeut une lane que si le backtest, la microstructure et le forward truth sont coherents. Sinon elle reste watch ou reject.</p>
    </section>

    <section class="grid section">
      <div class="card">
        <h2>Postmortem strict</h2>
        <p>Verdict: <b>{_cell(summary.get('strict_postmortem_verdict'))}</b></p>
        <p>Strict pairs: <b>{_cell(summary.get('strict_pairs'))}</b>, strict win-rate: <b>{_pct(summary.get('strict_win_rate'))}</b>.</p>
        <p>Strict filtered PnL: <b>{_usd(summary.get('strict_filtered_pnl_usd'))} USD</b>, baseline: <b>{_usd(summary.get('baseline_pnl_usd'))} USD</b>, delta: <b>{_usd(summary.get('delta_pnl_usd'))} USD</b>.</p>
      </div>
      <div class="card">
        <h2>Garde-fou</h2>
        <p>Ce rapport est une couche de decision read-only. Il ne remplace pas un compte demo ou une execution reelle.</p>
        <p>Une lane <code>PROMOTE_FORWARD_ONLY</code> signifie: continuer le paper/forward surveille, pas trader en reel.</p>
      </div>
    </section>

    <section class="card section"><h2>PROMOTE_FORWARD_ONLY</h2>{_table(payload.get('promote') or [])}</section>
    <section class="card section"><h2>WATCH</h2>{_table(payload.get('watch') or [])}</section>
    <section class="card section"><h2>REJECT</h2>{_table(payload.get('reject') or [])}</section>
    <section class="card section"><h2>Table complete</h2>{_table(payload.get('rows') or [], 200)}</section>
  </main>
</body>
</html>"""


def write_aster_promotion_truth_report() -> dict[str, Any]:
    payload = get_aster_promotion_truth_report_preview(dry_run=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_aster_promotion_truth_report()
    summary = payload.get("summary") or {}
    print(
        f"[{payload['generated_at']}] lanes={summary.get('lanes')} "
        f"promote={summary.get('promote_forward_only')} watch={summary.get('watch_total')} "
        f"reject={summary.get('reject_total')} html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
