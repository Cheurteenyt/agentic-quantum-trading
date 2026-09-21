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

CONSOLIDATED_JSON = BASE_DIR / "aster_research_consolidated_report_latest.json"
PROMOTION_TRUTH_JSON = BASE_DIR / "aster_promotion_truth_report_latest.json"

JSON_OUT = BASE_DIR / "aster_lane_promotion_scoring_latest.json"
CSV_OUT = BASE_DIR / "aster_lane_promotion_scoring_latest.csv"
HTML_OUT = DOCS_DIR / "core-equity-aster-lane-promotion-scoring.html"


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


def _base_lane_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("symbol") or "").upper(),
            str(row.get("interval") or ""),
            str(row.get("side") or "long").lower(),
        ]
    )


def _has_strategy_identity(row: dict[str, Any]) -> bool:
    return any(
        str(row.get(key) or "").strip()
        for key in ("strategy_profile_id", "strategy_profile_key", "trigger_reference", "execution_model", "best_tradable_leverage", "output_tag")
    )


def _truth_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[_lane_key(row)] = row
    return out


def _score_and_blockers(row: dict[str, Any], truth: dict[str, Any] | None) -> tuple[float, list[str], str]:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = min(_float(row.get("profit_factor")), 25.0)
    wr = _float(row.get("win_rate"))
    closed = _int(row.get("closed_trades"))
    dd = _float(row.get("max_drawdown_usd"))
    leverage = _float(row.get("best_tradable_leverage"), 1.0)
    mark = str(row.get("mark_index_verdict") or "not_checked")
    exchange = str(row.get("exchange_filter_verdict") or "not_checked")
    ws = str(row.get("ws_quality_verdict") or "not_checked")
    quote_vol = _float(row.get("quote_volume_24h") or row.get("ws_quote_volume_24h"))
    truth_verdict = str((truth or {}).get("final_verdict") or "")

    blockers: list[str] = []
    score = 0.0
    score += max(min(roi, 30.0), -30.0) * 1.4
    score += min(pf, 10.0) * 5.0
    score += wr * 22.0
    score += min(closed, 60) * 0.45
    score -= min(dd, 80.0) * 0.28
    score += min(leverage, 10.0) * 0.7

    if closed < 8:
        blockers.append("sample_lt_8")
        score -= 18
    elif closed < 15:
        blockers.append("sample_lt_15")
        score -= 6
    if pf < 1.3:
        blockers.append("pf_lt_1_3")
        score -= 16
    if wr < 0.5:
        blockers.append("winrate_lt_50")
        score -= 12
    if roi <= 0:
        blockers.append("roi_non_positive")
        score -= 20
    if dd > 40:
        blockers.append("drawdown_gt_40")
        score -= 10
    if mark == "mark_index_rejected":
        blockers.append("mark_index_rejected")
        score -= 35
    elif mark in {"mark_index_watch", "not_checked"}:
        blockers.append(f"{mark}")
        score -= 4
    if exchange == "blocked":
        blockers.append("exchange_filter_blocked")
        score -= 35
    if ws in {"ws_forward_risky", "risky"}:
        blockers.append("ws_forward_risky")
        score -= 14
    elif ws in {"ws_forward_watch"}:
        blockers.append("ws_forward_watch")
        score -= 5
    if quote_vol and quote_vol < 50_000:
        blockers.append("low_quote_volume")
        score -= 12

    if truth_verdict == "PROMOTE_FORWARD_ONLY":
        score += 30
    elif truth_verdict.startswith("WATCH"):
        blockers.append("truth_watch")
        score += 8
    elif truth_verdict.startswith("REJECT"):
        blockers.append("truth_reject")
        score -= 24
    else:
        blockers.append("no_promotion_truth_match")
        score -= 10

    score = round(max(0.0, min(score, 100.0)), 3)
    if truth_verdict == "PROMOTE_FORWARD_ONLY" and score >= 70 and not any(b in blockers for b in ["exchange_filter_blocked", "mark_index_rejected"]):
        lifecycle = "PROMOTE_FORWARD_ONLY"
    elif score >= 70 and len([b for b in blockers if b.startswith("truth_") or b in {"no_promotion_truth_match"}]) == 0:
        lifecycle = "FORWARD_TESTING"
    elif score >= 55:
        lifecycle = "WATCH"
    elif score >= 40:
        lifecycle = "DISCOVERED"
    else:
        lifecycle = "REJECTED"
    return score, blockers, lifecycle


def get_aster_lane_promotion_scoring_preview(dry_run: bool = True, top_n: int = 120) -> dict[str, Any]:
    if not dry_run:
        return {"ok": False, "status": "blocked", "blockers": ["dry_run_required"]}

    consolidated = _load(CONSOLIDATED_JSON)
    promotion_truth = _load(PROMOTION_TRUTH_JSON)
    top_lanes = list(consolidated.get("top_lanes") or [])
    truth_by_lane = _truth_map(list(promotion_truth.get("rows") or []))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source in top_lanes:
        key = _lane_key(source)
        if not key or key in seen:
            continue
        seen.add(key)
        truth = truth_by_lane.get(key)
        score, blockers, lifecycle = _score_and_blockers(source, truth)
        rows.append(
            {
                "lane_key": key,
                "symbol": str(source.get("symbol") or "").upper(),
                "interval": source.get("interval"),
                "side": source.get("side") or "long",
                "risk_profile": source.get("risk_profile"),
                "promotion_score": score,
                "lifecycle": lifecycle,
                "promotion_blockers": ",".join(blockers),
                "strategy_profile_id": source.get("strategy_profile_id"),
                "trigger_reference": source.get("trigger_reference"),
                "execution_model": source.get("execution_model"),
                "roi_pct_on_paper_balance": source.get("roi_pct_on_paper_balance"),
                "win_rate": source.get("win_rate"),
                "profit_factor": source.get("profit_factor"),
                "closed_trades": source.get("closed_trades"),
                "max_drawdown_usd": source.get("max_drawdown_usd"),
                "best_tradable_leverage": source.get("best_tradable_leverage"),
                "quote_volume_24h": source.get("quote_volume_24h") or source.get("ws_quote_volume_24h"),
                "mark_index_verdict": source.get("mark_index_verdict"),
                "exchange_filter_verdict": source.get("exchange_filter_verdict"),
                "ws_quality_verdict": source.get("ws_quality_verdict"),
                "promotion_truth_verdict": (truth or {}).get("final_verdict"),
                "promotion_truth_reason": (truth or {}).get("final_reason"),
                "source": source.get("source"),
            }
        )

    rows.sort(key=lambda row: (_float(row.get("promotion_score")), _float(row.get("roi_pct_on_paper_balance"))), reverse=True)
    clean_rows = rows[: max(1, min(_int(top_n, 120), 500))]
    counts: dict[str, int] = {}
    for row in clean_rows:
        lifecycle = str(row.get("lifecycle") or "UNKNOWN")
        counts[lifecycle] = counts.get(lifecycle, 0) + 1
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "rank_consolidated_backtest_lanes_with_robustness_blockers_and_promotion_truth_overlay",
        "source_generated_at": {
            "consolidated": consolidated.get("generated_at"),
            "promotion_truth": promotion_truth.get("generated_at"),
        },
        "summary": {
            "lanes_scored": len(clean_rows),
            "lifecycle_counts": counts,
            "top_lane": clean_rows[0].get("lane_key") if clean_rows else None,
            "top_score": clean_rows[0].get("promotion_score") if clean_rows else None,
        },
        "rows": clean_rows,
        "top_promote_or_forward": [row for row in clean_rows if row.get("lifecycle") in {"PROMOTE_FORWARD_ONLY", "FORWARD_TESTING"}],
        "watch": [row for row in clean_rows if row.get("lifecycle") == "WATCH"],
        "rejected": [row for row in clean_rows if row.get("lifecycle") == "REJECTED"],
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
    if value in (None, ""):
        return ""
    return f"{_float(value) * 100:.2f}%"


def _table(rows: list[dict[str, Any]], limit: int = 80) -> str:
    if not rows:
        return "<p class='muted'>Aucune lane dans cette categorie.</p>"
    body = []
    for row in rows[:limit]:
        klass = str(row.get("lifecycle") or "").lower()
        body.append(
            "<tr class='%s'>"
            "<td><b>%s</b><br><code>%s</code></td>"
            "<td>%s</td><td>%s</td><td>%s / %s / %s</td>"
            "<td>%s</td><td>%s</td><td>%s</td>"
            "</tr>"
            % (
                _cell(klass),
                _cell(row.get("lifecycle")),
                _cell(row.get("lane_key")),
                _cell(row.get("promotion_score")),
                _cell(row.get("roi_pct_on_paper_balance")),
                _pct(row.get("win_rate")),
                _cell(row.get("profit_factor")),
                _cell(row.get("closed_trades")),
                _cell(row.get("promotion_truth_verdict")),
                _cell(row.get("promotion_blockers")),
                _cell(row.get("source")),
            )
        )
    return (
        "<table><thead><tr><th>Lifecycle / lane</th><th>Score</th><th>ROI</th><th>WR / PF / trades</th>"
        "<th>Truth</th><th>Blockers</th><th>Source</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    counts = summary.get("lifecycle_counts") or {}
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Core Equity - Aster Lane Promotion Scoring</title>
  <style>
    :root {{ --bg:#10120d; --panel:#f8f2df; --line:#dac9a7; --ink:#182018; --muted:#637064; --green:#147a4c; --amber:#9d6900; --red:#a94032; --blue:#235f92; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:radial-gradient(circle at 10% 0%,rgba(20,122,76,.22),transparent 34%),linear-gradient(135deg,#10120d,#273229); color:var(--ink); font-family:"Segoe UI","Aptos",sans-serif; line-height:1.55; }}
    main {{ width:min(1480px,calc(100% - 32px)); margin:0 auto; padding:34px 0 72px; }}
    .hero,.card {{ background:var(--panel); border:1px solid var(--line); border-radius:24px; box-shadow:0 20px 46px rgba(0,0,0,.22); }}
    .hero {{ padding:32px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(34px,5vw,62px); letter-spacing:-.055em; line-height:1; }}
    h2 {{ margin:0 0 14px; font-size:24px; }}
    p {{ color:var(--muted); }}
    a {{ color:var(--blue); font-weight:800; text-decoration:none; }}
    code {{ background:#eadcc1; border:1px solid #ddc9a7; padding:2px 6px; border-radius:7px; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    .nav a {{ padding:8px 11px; border:1px solid var(--line); border-radius:999px; background:#fff8e8; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-top:18px; }}
    .metric {{ background:#fff8e8; border:1px solid var(--line); border-radius:18px; padding:15px; }}
    .metric strong {{ display:block; font-size:30px; }}
    .card {{ margin-top:20px; padding:22px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:10px 11px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ background:#efe2c5; text-transform:uppercase; font-size:11px; letter-spacing:.065em; }}
    tr.promote_forward_only td:first-child, tr.forward_testing td:first-child {{ color:var(--green); font-weight:900; }}
    tr.watch td:first-child, tr.discovered td:first-child {{ color:var(--amber); font-weight:900; }}
    tr.rejected td:first-child {{ color:var(--red); font-weight:900; }}
    .muted {{ color:var(--muted); }}
    @media (max-width:980px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <h1>Aster Lane Promotion Scoring</h1>
    <p>Classement robuste des anciennes lanes de backtest: score, blockers, lifecycle et overlay promotion-truth.</p>
    <p class="muted">Genere le {_cell(payload.get('generated_at'))}. Read-only, local artifacts only.</p>
    <nav class="nav">
      <a href="core-equity-aster-documentation-hub.html">Hub</a>
      <a href="core-equity-aster-promotion-truth-report.html">Promotion truth</a>
      <a href="core-equity-aster-strategy-truth-report.html">Strategy truth</a>
    </nav>
    <div class="grid">
      <div class="metric"><span>Lanes scorees</span><strong>{_cell(summary.get('lanes_scored'))}</strong></div>
      <div class="metric"><span>Top lane</span><strong>{_cell(summary.get('top_lane'))}</strong></div>
      <div class="metric"><span>Top score</span><strong>{_cell(summary.get('top_score'))}</strong></div>
      <div class="metric"><span>Promote/forward</span><strong>{_cell(counts.get('PROMOTE_FORWARD_ONLY', 0) + counts.get('FORWARD_TESTING', 0))}</strong></div>
    </div>
  </section>

  <section class="card"><h2>Promote / Forward testing</h2>{_table(payload.get('top_promote_or_forward') or [])}</section>
  <section class="card"><h2>Watch</h2>{_table(payload.get('watch') or [])}</section>
  <section class="card"><h2>Rejected</h2>{_table(payload.get('rejected') or [], 120)}</section>
  <section class="card"><h2>Table complete</h2>{_table(payload.get('rows') or [], 160)}</section>
</main>
</body>
</html>"""


def _write_csv(rows: list[dict[str, Any]]) -> None:
    headers = [
        "lane_key",
        "symbol",
        "interval",
        "side",
        "promotion_score",
        "lifecycle",
        "promotion_blockers",
        "strategy_profile_id",
        "trigger_reference",
        "execution_model",
        "roi_pct_on_paper_balance",
        "win_rate",
        "profit_factor",
        "closed_trades",
        "max_drawdown_usd",
        "best_tradable_leverage",
        "promotion_truth_verdict",
        "source",
    ]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_aster_lane_promotion_scoring(top_n: int = 120) -> dict[str, Any]:
    payload = get_aster_lane_promotion_scoring_preview(dry_run=True, top_n=top_n)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    _write_csv(list(payload.get("rows") or []))
    return payload


def main() -> None:
    payload = write_aster_lane_promotion_scoring()
    summary = payload.get("summary") or {}
    print(
        f"[{payload['generated_at']}] lanes={summary.get('lanes_scored')} "
        f"top={summary.get('top_lane')} score={summary.get('top_score')} "
        f"csv={CSV_OUT} html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
