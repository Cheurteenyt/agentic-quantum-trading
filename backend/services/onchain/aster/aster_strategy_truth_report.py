from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"
DB_PATH = ROOT_DIR / "backend" / "data" / "onchain" / "onchain.db"
JSON_OUT = BASE_DIR / "aster_strategy_truth_report_latest.json"
HTML_OUT = DOCS_DIR / "core-equity-aster-strategy-truth-report.html"


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


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if abs(denominator) <= 1e-9:
        return None
    return numerator / denominator


def _truth_verdict(row: dict[str, Any]) -> tuple[str, str]:
    exits = _int(row.get("total_exits"))
    entries = _int(row.get("total_entries"))
    net = _float(row.get("net_pnl_usd"))
    latent = _float(row.get("latent_pnl_usd"))
    total = _float(row.get("total_pnl_including_latent_usd"))
    pf = row.get("profit_factor")
    pf_value = _float(pf, 0.0) if pf is not None else 0.0
    wr = _float(row.get("win_rate"))
    danger = row.get("latent_danger_ratio")
    danger_value = _float(danger, 999.0) if danger is not None else 999.0

    if exits < 3:
        return "INSUFFICIENT_SAMPLE", "Moins de 3 sorties fermees."
    if net > 0 and total < 0:
        return "RISKY_PROFIT", "PnL realise positif mais positions ouvertes trop negatives."
    if net > 8 and (danger_value > 2.0 or latent < -50):
        return "RISKY_PROFIT", "PnL realise fort, mais latent ouvert disproportionne."
    if exits >= 8 and total > 0 and pf_value >= 1.3 and wr >= 0.5 and danger_value <= 1.0:
        return "PROMOTE", "PnL total positif, PF/WR corrects, risque latent contenu."
    if exits >= 5 and total > 0 and pf_value >= 1.1:
        return "WATCH", "Prometteur mais pas encore assez robuste."
    if net <= 0 and total <= 0:
        return "STOP_OR_REWORK", "PnL realise et total non convaincants."
    if entries > exits + 3:
        return "OPEN_RISK_REVIEW", "Trop de positions ouvertes par rapport aux sorties."
    return "WATCH", "Resultat mixte a surveiller."


def _recommended_action(row: dict[str, Any]) -> str:
    verdict = str(row.get("truth_verdict") or "")
    event_type = str(row.get("event_type") or "")
    latent = _float(row.get("latent_pnl_usd"))
    net = _float(row.get("net_pnl_usd"))
    exits = _int(row.get("total_exits"))
    open_count = _int(row.get("open_positions_count"))
    if verdict == "PROMOTE":
        return "continuer_forward_paper_et_augmenter_sample"
    if verdict == "RISKY_PROFIT" and latent < 0:
        return "geler_nouvelles_entrees_et_forcer_time_stop_des_positions_ouvertes"
    if verdict == "RISKY_PROFIT" and latent >= 0:
        return "continuer_mais_ajouter_cap_latent_et_sortie_forcee"
    if verdict == "STOP_OR_REWORK":
        return "stopper_runner_ou_reduire_aux_tests_read_only"
    if verdict == "INSUFFICIENT_SAMPLE" and open_count > 0:
        return "laisser_cloturer_ou_forcer_sortie_si_age_position_depasse_limite"
    if verdict == "INSUFFICIENT_SAMPLE":
        return "collecter_plus_de_sorties_avant_decision"
    if exits >= 5 and net > 0:
        return "watch_jusqua_20_exits_sans_augmenter_risque"
    if "promotion_ready" in event_type:
        return "continuer_strict_uniquement_et_garder_normal_en_observation"
    return "watch_sans_nouvelle_allocation"


def _query_event_rows() -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        aggregate_rows = con.execute(
            """
            select
                event_type,
                min(created_at) as first_at,
                max(created_at) as last_at,
                count(*) as rows_count,
                sum(case when state='executing_entry' then 1 else 0 end) as entries,
                sum(case when state='executing_exit' then 1 else 0 end) as exits,
                sum(case when state='executing_exit' then coalesce(pnl_realized_usd,0) else 0 end) as net_pnl,
                sum(case when state='executing_exit' and pnl_realized_usd>0 then pnl_realized_usd else 0 end) as gross_win,
                abs(sum(case when state='executing_exit' and pnl_realized_usd<0 then pnl_realized_usd else 0 end)) as gross_loss,
                avg(case when state='executing_exit' and pnl_realized_usd>0 then 1.0 when state='executing_exit' then 0.0 end) as win_rate,
                count(distinct symbol) as symbols_count,
                group_concat(distinct symbol) as symbols
            from aster_paper_trading_ledger
            group by event_type
            having entries > 0 or exits > 0
            order by net_pnl desc
            """
        ).fetchall()
        position_rows = con.execute(
            """
            select id, event_type, symbol, state, decision_reason, entry_price, current_price,
                   size_usd, pnl_unrealized_usd, pnl_realized_usd, raw_payload_json, created_at
            from aster_paper_trading_ledger
            order by event_type asc, symbol asc, id asc
            """
        ).fetchall()
    finally:
        con.close()
    open_positions = _open_positions_by_event(position_rows)
    out: list[dict[str, Any]] = []
    for row in aggregate_rows:
        net = _float(row["net_pnl"])
        positions = open_positions.get(str(row["event_type"]) or "", [])
        latent = sum(_float(position.get("pnl_unrealized_usd")) for position in positions)
        gross_loss = _float(row["gross_loss"])
        gross_win = _float(row["gross_win"])
        danger = abs(latent) / max(abs(net), 1.0)
        item = {
            "event_type": row["event_type"],
            "first_at": row["first_at"],
            "last_at": row["last_at"],
            "rows": _int(row["rows_count"]),
            "total_entries": _int(row["entries"]),
            "total_exits": _int(row["exits"]),
            "net_pnl_usd": round(net, 6),
            "latent_pnl_usd": round(latent, 6),
            "total_pnl_including_latent_usd": round(net + latent, 6),
            "gross_win_usd": round(gross_win, 6),
            "gross_loss_usd": round(gross_loss, 6),
            "profit_factor": round(gross_win / gross_loss, 6) if gross_loss > 0 else None,
            "win_rate": round(_float(row["win_rate"]), 6) if row["win_rate"] is not None else None,
            "open_positions_count": len(positions),
            "open_positions": positions[:20],
            "max_abs_open_latent_usd": round(max((_float(position.get("pnl_unrealized_usd")) for position in positions), key=abs, default=0.0), 6),
            "latent_danger_ratio": round(danger, 6),
            "symbols_count": _int(row["symbols_count"]),
            "symbols": row["symbols"],
        }
        verdict, reason = _truth_verdict(item)
        item["truth_verdict"] = verdict
        item["truth_reason"] = reason
        item["recommended_action"] = _recommended_action(item)
        out.append(item)
    return out


def _payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    try:
        raw = row["raw_payload_json"] if isinstance(row, sqlite3.Row) else row.get("raw_payload_json")
        payload = json.loads(raw or "{}")
        return payload if isinstance(payload, dict) else {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _position_key(row: sqlite3.Row | dict[str, Any], payload: dict[str, Any]) -> tuple[str, str]:
    event_type = str(row["event_type"] if isinstance(row, sqlite3.Row) else row.get("event_type") or "")
    symbol = str(row["symbol"] if isinstance(row, sqlite3.Row) else row.get("symbol") or "")
    return event_type, symbol.upper()


def _position_snapshot(row: sqlite3.Row | dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"] if isinstance(row, sqlite3.Row) else row.get("id"),
        "symbol": row["symbol"] if isinstance(row, sqlite3.Row) else row.get("symbol"),
        "state": row["state"] if isinstance(row, sqlite3.Row) else row.get("state"),
        "decision_reason": row["decision_reason"] if isinstance(row, sqlite3.Row) else row.get("decision_reason"),
        "entry_price": _float(row["entry_price"] if isinstance(row, sqlite3.Row) else row.get("entry_price")),
        "current_price": _float(row["current_price"] if isinstance(row, sqlite3.Row) else row.get("current_price")),
        "size_usd": _float(row["size_usd"] if isinstance(row, sqlite3.Row) else row.get("size_usd")),
        "pnl_unrealized_usd": round(_float(row["pnl_unrealized_usd"] if isinstance(row, sqlite3.Row) else row.get("pnl_unrealized_usd")), 6),
        "created_at": row["created_at"] if isinstance(row, sqlite3.Row) else row.get("created_at"),
        "trade_id": payload.get("trade_id"),
        "action": payload.get("action"),
        "trades_held": payload.get("trades_held"),
        "source": payload.get("source"),
    }


def _open_positions_by_event(rows: list[sqlite3.Row]) -> dict[str, list[dict[str, Any]]]:
    """Approximate active paper positions from the latest state per event_type+symbol.

    The ledger contains many historical entry/mark rows. Summing them overstates
    risk, so this keeps only the latest unmatched position per event_type+symbol.
    """
    active: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        payload = _payload(row)
        action = str(payload.get("action") or "")
        state = str(row["state"] or "")
        key = _position_key(row, payload)
        if action == "exit" or state == "executing_exit":
            active.pop(key, None)
            continue
        if action in {"entry", "mark_to_market"} or state in {"executing_entry", "monitoring"}:
            active[key] = _position_snapshot(row, payload)
    by_event: dict[str, list[dict[str, Any]]] = {}
    for (event_type, _symbol), position in active.items():
        by_event.setdefault(event_type, []).append(position)
    return by_event


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        verdict = str(row.get("truth_verdict") or "UNKNOWN")
        counts[verdict] = counts.get(verdict, 0) + 1
    return {
        "strategies": len(rows),
        "verdict_counts": counts,
        "global_net_pnl_usd": round(sum(_float(row.get("net_pnl_usd")) for row in rows), 6),
        "global_latent_pnl_usd": round(sum(_float(row.get("latent_pnl_usd")) for row in rows), 6),
        "global_total_pnl_usd": round(sum(_float(row.get("total_pnl_including_latent_usd")) for row in rows), 6),
        "promote_count": counts.get("PROMOTE", 0),
        "risky_profit_count": counts.get("RISKY_PROFIT", 0),
        "stop_or_rework_count": counts.get("STOP_OR_REWORK", 0),
        "interpretation_warning": (
            "Les totaux globaux additionnent des event_type qui peuvent se chevaucher; "
            "ils servent au diagnostic, pas a simuler un portefeuille reel unique."
        ),
        "open_position_method": "latest_unmatched_state_per_event_type_and_symbol",
    }


def get_aster_strategy_truth_report_preview(dry_run: bool = True) -> dict[str, Any]:
    rows = _query_event_rows()
    ranked = sorted(
        rows,
        key=lambda row: (
            {"PROMOTE": 5, "WATCH": 4, "RISKY_PROFIT": 3, "OPEN_RISK_REVIEW": 2, "INSUFFICIENT_SAMPLE": 1, "STOP_OR_REWORK": 0}.get(
                str(row.get("truth_verdict")), 0
            ),
            _float(row.get("total_pnl_including_latent_usd")),
            _float(row.get("net_pnl_usd")),
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "status": "ready",
        "dry_run": bool(dry_run),
        "generated_at": _now(),
        "methodology": "paper_ledger_truth_report_realized_plus_latent_risk_by_event_type",
        "summary": _summary(ranked),
        "rows": ranked,
        "top_promote": [row for row in ranked if row.get("truth_verdict") == "PROMOTE"][:10],
        "risky_profit": [row for row in ranked if row.get("truth_verdict") == "RISKY_PROFIT"][:10],
        "stop_or_rework": [row for row in ranked if row.get("truth_verdict") == "STOP_OR_REWORK"][:10],
        "safety": {
            "would_write_db": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
        },
    }


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _usd(value: Any) -> str:
    return f"{_float(value):+.6f} USD"


def _pct(value: Any) -> str:
    if value in (None, ""):
        return ""
    return f"{_float(value) * 100:.2f}%"


def _table(rows: list[dict[str, Any]], limit: int = 80) -> str:
    headers = [
        "truth_verdict",
        "event_type",
        "net_pnl_usd",
        "latent_pnl_usd",
        "total_pnl_including_latent_usd",
        "total_exits",
        "open_positions_count",
        "win_rate",
        "profit_factor",
        "latent_danger_ratio",
        "symbols",
        "recommended_action",
        "truth_reason",
    ]
    body = []
    for row in rows[:limit]:
        klass = str(row.get("truth_verdict") or "").lower()
        body.append("<tr class='%s'>%s</tr>" % (html.escape(klass), "".join(f"<td>{_cell(row.get(key))}</td>" for key in headers)))
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
        "".join(f"<th>{html.escape(key)}</th>" for key in headers),
        "".join(body),
    )


def _decision_table(rows: list[dict[str, Any]], limit: int = 80) -> str:
    if not rows:
        return "<p class='muted'>Aucune ligne dans cette categorie.</p>"
    body = []
    for row in rows[:limit]:
        verdict = str(row.get("truth_verdict") or "")
        klass = verdict.lower()
        body.append(
            "<tr class='%s'>"
            "<td><b>%s</b><br><code>%s</code></td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s / %s / %s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "</tr>"
            % (
                html.escape(klass),
                _cell(verdict),
                _cell(row.get("event_type")),
                _cell(row.get("symbols")),
                _usd(row.get("net_pnl_usd")),
                _usd(row.get("latent_pnl_usd")),
                _usd(row.get("total_pnl_including_latent_usd")),
                _cell(row.get("total_entries")),
                _cell(row.get("total_exits")),
                _cell(row.get("open_positions_count")),
                _pct(row.get("win_rate")),
                _cell(row.get("profit_factor")),
                _cell(row.get("truth_reason")),
            )
        )
    return (
        "<table><thead><tr>"
        "<th>Verdict / lane</th><th>Symboles</th><th>Net realise</th><th>Latent</th><th>Total</th>"
        "<th>Entries / exits / open</th><th>WR</th><th>PF</th><th>Lecture</th>"
        "</tr></thead><tbody>%s</tbody></table>" % "".join(body)
    )


def _filter_verdict(rows: list[dict[str, Any]], *verdicts: str) -> list[dict[str, Any]]:
    wanted = {verdict.upper() for verdict in verdicts}
    return [row for row in rows if str(row.get("truth_verdict") or "").upper() in wanted]


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    rows = payload.get("rows") or []
    promote_rows = payload.get("top_promote") or _filter_verdict(rows, "PROMOTE")
    watch_rows = _filter_verdict(rows, "WATCH", "OPEN_RISK_REVIEW")
    insufficient_rows = _filter_verdict(rows, "INSUFFICIENT_SAMPLE")
    stop_rows = payload.get("stop_or_rework") or _filter_verdict(rows, "STOP_OR_REWORK")
    risky_rows = payload.get("risky_profit") or _filter_verdict(rows, "RISKY_PROFIT")
    first_promote = promote_rows[0] if promote_rows else {}
    verdict_counts = summary.get("verdict_counts") or {}
    watch_count = verdict_counts.get("WATCH", 0)
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Core Equity - Aster Strategy Truth Report</title>
  <style>
    :root {{
      --bg:#07100d; --card:#101c17; --line:#294238; --text:#edf7f1; --muted:#9bb5aa;
      --good:#54d98c; --warn:#ffd166; --bad:#ff6b6b; --blue:#7cc7ff;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; font-family:"Segoe UI","Aptos",sans-serif;
      background:radial-gradient(circle at top left,rgba(84,217,140,.16),transparent 34%),
                 radial-gradient(circle at 92% 12%,rgba(124,199,255,.11),transparent 30%),var(--bg);
      color:var(--text); line-height:1.55;
    }}
    header {{ padding:44px 56px 30px; border-bottom:1px solid var(--line); }}
    main {{ max-width:1480px; margin:0 auto; padding:30px 56px 68px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(32px,4vw,54px); letter-spacing:-.055em; line-height:1.04; }}
    h2 {{ margin:0 0 16px; font-size:23px; letter-spacing:-.02em; }}
    p {{ margin:0 0 12px; color:var(--muted); }}
    a {{ color:#a8d9ff; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    code {{ background:#08110d; border:1px solid #20372e; border-radius:7px; padding:2px 6px; color:#c8ffdd; }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1.3fr) minmax(330px,.7fr); gap:18px; align-items:stretch; }}
    .card {{ background:rgba(16,28,23,.94); border:1px solid var(--line); border-radius:22px; padding:22px; box-shadow:0 18px 50px rgba(0,0,0,.24); }}
    .section {{ margin-top:22px; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }}
    .kpis {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .kpi {{ background:linear-gradient(180deg,#0d1a14,#09130f); border:1px solid #20372e; border-radius:18px; padding:15px; }}
    .kpi strong {{ display:block; font-size:28px; letter-spacing:-.035em; line-height:1.05; }}
    .kpi span {{ display:block; color:var(--muted); font-size:12px; margin-top:5px; }}
    table {{ width:100%; border-collapse:collapse; overflow:hidden; border-radius:14px; font-size:13px; }}
    th,td {{ padding:10px 11px; border-bottom:1px solid #233b32; text-align:left; vertical-align:top; }}
    th {{ background:#0c1913; color:#d9ffe7; text-transform:uppercase; font-size:11px; letter-spacing:.065em; }}
    tr:last-child td {{ border-bottom:0; }}
    tr.promote td:first-child {{ color:var(--good); font-weight:900; }}
    tr.watch td:first-child, tr.open_risk_review td:first-child, tr.insufficient_sample td:first-child, tr.risky_profit td:first-child {{ color:var(--warn); font-weight:900; }}
    tr.stop_or_rework td:first-child {{ color:var(--bad); font-weight:900; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    .nav a {{ display:inline-flex; padding:8px 11px; border:1px solid var(--line); border-radius:999px; background:#0b1712; font-size:13px; font-weight:800; }}
    .callout {{ border-left:4px solid var(--warn); background:rgba(255,209,102,.08); border-radius:14px; padding:14px 16px; margin-top:14px; }}
    .callout.good {{ border-left-color:var(--good); background:rgba(84,217,140,.08); }}
    .callout.bad {{ border-left-color:var(--bad); background:rgba(255,107,107,.08); }}
    .good {{ color:var(--good); }} .warn {{ color:var(--warn); }} .bad {{ color:var(--bad); }}
    .muted {{ color:var(--muted); }}
    .footer {{ margin-top:28px; font-size:13px; color:var(--muted); }}
    @media (max-width:980px) {{ header,main {{ padding-left:22px; padding-right:22px; }} .hero,.grid {{ grid-template-columns:1fr; }} .kpis {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Aster Strategy Truth Report</h1>
    <p>Rapport de verite du ledger forward paper: PnL realise + risque latent ouvert, groupe par <code>event_type</code>.</p>
    <p class="muted">Genere le {_cell(payload.get('generated_at'))}. Source JSON: <code>aster_strategy_truth_report_latest.json</code>.</p>
    <nav class="nav" aria-label="Navigation documentation Aster">
      <a href="core-equity-aster-documentation-hub.html">Hub Aster</a>
      <a href="core-equity-aster-current-state.html">Etat actuel</a>
      <a href="core-equity-aster-promotion-ready-lanes.html">Promotion lanes</a>
      <a href="core-equity-aster-research-consolidated-report.html">Research consolidated</a>
      <a href="core-equity-null-results-report.html">Null results</a>
    </nav>
  </header>
  <main>
    <section class="hero">
      <div class="card">
        <h2>Verdict honnete</h2>
        <p>
          Le ledger ne dit pas "pret pour le reel". Il dit: <b>{_cell(summary.get('promote_count'))} lanes meritent
          de continuer en forward paper</b>, plusieurs lanes doivent etre stoppees, et le total global reste fragile
          si le latent ouvert absorbe le PnL realise.
        </p>
        <div class="callout">
          <p><b>Regle:</b> une lane est interessante seulement si elle combine PnL positif, PF correct,
          sample suffisant et latent contenu. Un bon symbole seul ne suffit pas.</p>
        </div>
      </div>
      <div class="card">
        <h2>Resume chiffres</h2>
        <div class="kpis">
          <div class="kpi"><strong>{_cell(summary.get('strategies'))}</strong><span>event types analyses</span></div>
          <div class="kpi"><strong class="good">{_cell(summary.get('promote_count'))}</strong><span>PROMOTE</span></div>
          <div class="kpi"><strong class="bad">{_cell(summary.get('stop_or_rework_count'))}</strong><span>STOP_OR_REWORK</span></div>
          <div class="kpi"><strong class="warn">{_cell(watch_count)}</strong><span>WATCH</span></div>
          <div class="kpi"><strong>{_usd(summary.get('global_net_pnl_usd'))}</strong><span>PnL realise global diagnostic</span></div>
          <div class="kpi"><strong class="bad">{_usd(summary.get('global_latent_pnl_usd'))}</strong><span>PnL latent global diagnostic</span></div>
          <div class="kpi"><strong class="warn">{_usd(summary.get('global_total_pnl_usd'))}</strong><span>realise + latent global</span></div>
          <div class="kpi"><strong>0</strong><span>ordre reel / wallet trade</span></div>
        </div>
      </div>
    </section>

    <section class="grid section">
      <div class="card">
        <h2>Meilleure lane actuelle</h2>
        <p><code>{_cell(first_promote.get('event_type'))}</code></p>
        <p>Symboles: <b>{_cell(first_promote.get('symbols'))}</b>.</p>
        <p>Total realise + latent: <b>{_usd(first_promote.get('total_pnl_including_latent_usd'))}</b>, exits: <b>{_cell(first_promote.get('total_exits'))}</b>, PF: <b>{_cell(first_promote.get('profit_factor'))}</b>.</p>
      </div>
      <div class="card">
        <h2>Limites de preuve</h2>
        <p>{_cell(summary.get('interpretation_warning'))}</p>
        <p>Methode latent: <code>{_cell(summary.get('open_position_method'))}</code>.</p>
        <p>Ce rapport reste paper-trading only: aucun signal client, aucun ordre wallet.</p>
      </div>
    </section>

    <section class="card section"><h2>Lanes PROMOTE: a garder, mais pas encore reel</h2>{_decision_table(promote_rows, 20)}</section>
    <section class="card section"><h2>WATCH / OPEN_RISK_REVIEW: prometteur, pas promouvable</h2>{_decision_table(watch_rows, 30)}</section>
    <section class="card section"><h2>INSUFFICIENT_SAMPLE: archive utile, pas preuve</h2>{_decision_table(insufficient_rows, 30)}</section>
    <section class="card section"><h2>STOP_OR_REWORK: a ne plus laisser tourner en priorite</h2>{_decision_table(stop_rows, 40)}</section>
    <section class="card section"><h2>RISKY_PROFIT: PnL positif mais risque ouvert dangereux</h2>{_decision_table(risky_rows, 20)}</section>
    <section class="card section"><h2>Table complete source</h2>{_table(rows, 120)}</section>
    <p class="footer">Garde-fou final: ce rapport est une documentation paper-trading. Il ne cree aucun signal client, n'autorise aucun trade reel et ne remplace pas une validation demo/mainnet avec execution controlee.</p>
  </main>
</body>
</html>"""


def write_aster_strategy_truth_report() -> dict[str, Any]:
    payload = get_aster_strategy_truth_report_preview(dry_run=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_aster_strategy_truth_report()
    summary = payload.get("summary") or {}
    print(
        f"[{payload['generated_at']}] strategies={summary.get('strategies')} "
        f"promote={summary.get('promote_count')} risky={summary.get('risky_profit_count')} "
        f"net={summary.get('global_net_pnl_usd')} latent={summary.get('global_latent_pnl_usd')} "
        f"html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
