from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"
CONSOLIDATED_JSON = BASE_DIR / "aster_research_consolidated_report_latest.json"
JSON_OUT = BASE_DIR / "aster_research_actions_latest.json"
MD_OUT = DOCS_DIR / "aster-research-actions.md"


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


def _lane_id(row: dict[str, Any]) -> str:
    return f"{row.get('symbol')} {row.get('side')} {row.get('interval')} {row.get('risk_profile')}"


def _action_for(row: dict[str, Any]) -> tuple[str, str]:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    wr = _float(row.get("win_rate"))
    pf = _float(row.get("profit_factor"))
    closed = _int(row.get("closed_trades"))
    dd = _float(row.get("max_drawdown_usd"))
    quality = row.get("quality_verdict")
    bucket = row.get("decision_bucket")
    mark_index = row.get("mark_index_verdict")

    if mark_index == "mark_index_rejected":
        return "STOP_OR_DEPRIORITIZE", "Mark/index rejete: divergence reference persistante ou risque perps trop eleve."
    if mark_index == "mark_index_confirmed" and roi >= 3 and pf >= 1.3 and closed >= 8 and dd <= 35:
        if quality == "backtest_quality_ok":
            return "PROMOTE_TO_FORWARD", "Reality check OK et mark/index confirme."
        return "NEEDS_REALITY_CHECK", "Mark/index confirme, mais il faut encore le reality check complet."
    if mark_index == "mark_index_watch" and roi >= 3 and pf >= 1.3 and closed >= 8 and dd <= 35:
        return "KEEP_RUNNING_WATCH", "Mark/index watch: continuer, review manuelle avant promotion."
    if quality == "backtest_quality_ok" and roi >= 5 and pf >= 1.5 and closed >= 8 and dd <= 30:
        return "PROMOTE_TO_FORWARD", "Reality check OK, ROI/PF/trades/drawdown acceptables."
    if quality == "backtest_quality_watch" and roi >= 3 and pf >= 1.3 and closed >= 8 and dd <= 35:
        return "KEEP_RUNNING_WATCH", "Reality check watch: continuer, mais ne pas promouvoir sans plus de confirmations."
    if str(bucket or "").startswith("raw_champion") and roi >= 8 and pf >= 1.5 and closed >= 8 and dd <= 35:
        return "NEEDS_REALITY_CHECK", "Backtest brut fort, mais pas encore qualifie par Aster reality check."
    if roi >= 3 and pf >= 1.3 and wr >= 0.55 and closed >= 8:
        return "KEEP_RUNNING", "Backtest exploitable, continuer a collecter avant decision."
    if closed < 8 and roi > 0:
        return "EXPLORE_MORE", "Trop peu de trades fermes pour conclure."
    return "STOP_OR_DEPRIORITIZE", "ROI/PF/trades insuffisants ou risque trop eleve."


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    action, reason = _action_for(row)
    return {
        "action": action,
        "reason": reason,
        "lane": _lane_id(row),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "interval": row.get("interval"),
        "risk_profile": row.get("risk_profile"),
        "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
        "win_rate": _float(row.get("win_rate")),
        "profit_factor": _float(row.get("profit_factor")),
        "closed_trades": _int(row.get("closed_trades")),
        "max_drawdown_usd": _float(row.get("max_drawdown_usd")),
        "best_tradable_leverage": _float(row.get("best_tradable_leverage")),
        "quality_score": row.get("quality_score"),
        "quality_verdict": row.get("quality_verdict"),
        "mark_index_verdict": row.get("mark_index_verdict"),
        "mark_index_p95_last_index_bps": row.get("mark_index_p95_last_index_bps"),
        "decision_bucket": row.get("decision_bucket"),
        "source": row.get("source"),
    }


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for action in actions:
        key = "|".join(
            str(action.get(part) or "")
            for part in ("action", "symbol", "side", "interval")
        )
        current = best.get(key)
        if current is None:
            best[key] = action
            continue
        if _float(action.get("roi_pct_on_paper_balance")) > _float(current.get("roi_pct_on_paper_balance")):
            best[key] = action
    return sorted(
        best.values(),
        key=lambda row: (
            _float(row.get("roi_pct_on_paper_balance")),
            _float(row.get("profit_factor")),
            _int(row.get("closed_trades")),
        ),
        reverse=True,
    )


def build_action_report() -> dict[str, Any]:
    if not CONSOLIDATED_JSON.exists():
        raise FileNotFoundError(f"Missing consolidated report: {CONSOLIDATED_JSON}")
    consolidated = json.loads(CONSOLIDATED_JSON.read_text(encoding="utf-8"))
    rows = consolidated.get("top_lanes") or []
    raw_actions = [_compact(row) for row in rows]
    actions = _dedupe_actions(raw_actions)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in actions:
        grouped[str(action.get("action"))].append(action)

    priority_order = [
        "PROMOTE_TO_FORWARD",
        "KEEP_RUNNING_WATCH",
        "NEEDS_REALITY_CHECK",
        "KEEP_RUNNING",
        "EXPLORE_MORE",
        "STOP_OR_DEPRIORITIZE",
    ]
    payload = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report_generated_at": consolidated.get("generated_at"),
        "source_counts": consolidated.get("source_counts"),
        "raw_action_rows": len(raw_actions),
        "deduped_action_rows": len(actions),
        "summary_counts": {key: len(grouped.get(key) or []) for key in priority_order},
        "priority_order": priority_order,
        "actions_by_type": {key: grouped.get(key, []) for key in priority_order},
        "next_steps": _next_steps(grouped),
        "safety": {
            "would_trade": False,
            "would_write_db": False,
            "would_send_wallet_transaction": False,
        },
    }
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    MD_OUT.write_text(_render_md(payload), encoding="utf-8")
    return payload


def _next_steps(grouped: dict[str, list[dict[str, Any]]]) -> list[str]:
    steps: list[str] = []
    if grouped.get("PROMOTE_TO_FORWARD"):
        steps.append("Prendre les 1-3 lanes PROMOTE_TO_FORWARD et les lancer en paper forward dedie.")
    if grouped.get("KEEP_RUNNING_WATCH"):
        steps.append("Laisser tourner les lanes WATCH jusqu'a plus de lignes reality-checked ou plus de trades fermes.")
    if grouped.get("NEEDS_REALITY_CHECK"):
        steps.append("Verifier les champions bruts via le runner core_reality_watch avant promotion.")
    if not steps:
        steps.append("Continuer la collecte; aucun candidat n'est encore assez qualifie pour promotion.")
    steps.append("Regenerer le rapport consolide avant chaque decision importante.")
    return steps


def _line(row: dict[str, Any]) -> str:
    return (
        f"| {row.get('symbol')} | {row.get('side')} | {row.get('interval')} | "
        f"{row.get('roi_pct_on_paper_balance'):.2f} | {row.get('win_rate'):.2f} | "
        f"{row.get('profit_factor'):.2f} | {row.get('closed_trades')} | "
        f"{row.get('max_drawdown_usd'):.2f} | {row.get('quality_score') or '-'} | "
        f"{row.get('quality_verdict') or '-'} | {row.get('mark_index_verdict') or '-'} | {row.get('reason')} |"
    )


def _section(title: str, rows: list[dict[str, Any]], limit: int = 10) -> str:
    if not rows:
        return f"## {title}\n\nAucun candidat.\n"
    header = "| Symbol | Side | TF | ROI % | WR | PF | Trades | DD $ | Quality | Verdict | Mark/Index | Raison |\n"
    sep = "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|\n"
    body = "\n".join(_line(row) for row in rows[:limit])
    return f"## {title}\n\n{header}{sep}{body}\n"


def _render_md(payload: dict[str, Any]) -> str:
    grouped = payload.get("actions_by_type") or {}
    counts = payload.get("summary_counts") or {}
    steps = "\n".join(f"- {step}" for step in payload.get("next_steps") or [])
    parts = [
        "# Aster Research Actions",
        "",
        f"Generated at: `{payload.get('generated_at')}`",
        f"Source report: `{payload.get('source_report_generated_at')}`",
        "",
        "## Resume",
        "",
        "\n".join(f"- `{key}`: {value}" for key, value in counts.items()),
        "",
        "## Prochaines etapes",
        "",
        steps,
        "",
    ]
    for key in payload.get("priority_order") or []:
        title = key.replace("_", " ").title()
        parts.append(_section(title, grouped.get(key) or []))
    parts.append("## Safety\n\n- Aucun trade reel.\n- Aucun wallet.\n- Aucun write DB.\n")
    return "\n".join(parts)


def main() -> None:
    payload = build_action_report()
    print(f"[{payload['generated_at']}] actions={payload['summary_counts']} md={MD_OUT}")


if __name__ == "__main__":
    main()
