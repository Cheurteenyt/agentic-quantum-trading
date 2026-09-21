from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
CONSOLIDATED_FILE = BASE_DIR / "aster_research_consolidated_report_latest.json"
PRIORITY_WATCHLIST_FILE = BASE_DIR / "aster_priority_watchlist_latest.json"
SNAPSHOT_FILE = BASE_DIR / "aster_dual_track_research_report_latest.json"

DEFAULT_PRESERVE_SYMBOLS = "LABUSDT,INTCUSDT,CRCLUSDT,MSFTUSDT,INJUSDT,ORDIUSDT,TIAUSDT,BOMEUSDT"


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


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _symbols(value: str | list[str] | None) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        symbol = "".join(ch for ch in str(item or "").strip().upper() if ch.isalnum())[:32]
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _lane_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("symbol") or "").upper(),
        str(row.get("side") or ""),
        str(row.get("interval") or ""),
        str(row.get("risk_profile") or ""),
        str(row.get("min_aster_score") or ""),
        str(row.get("min_window_volume_usd") or ""),
    )


def _compact_lane(row: dict[str, Any], track: str) -> dict[str, Any]:
    decision = str(row.get("decision_bucket") or "unknown")
    mark_index = str(row.get("mark_index_verdict") or "not_checked")
    if mark_index == "mark_index_rejected" or decision in {"mark_index_rejected", "rejected_or_manual_review"}:
        status = "review_or_blocked"
    elif decision.startswith("raw_"):
        status = "preserve_but_reality_check"
    elif decision in {"watch_accepted", "strict_ok_mark_index_confirmed", "strict_ok_mark_index_watch", "strict_ok_promotion_candidate", "strict_ok_review"}:
        status = "keep_monitoring"
    else:
        status = "research_candidate"
    return {
        "track": track,
        "symbol": str(row.get("symbol") or "").upper(),
        "side": row.get("side"),
        "interval": row.get("interval"),
        "output_tag": row.get("output_tag"),
        "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
        "win_rate": _float(row.get("win_rate")),
        "profit_factor": _float(row.get("profit_factor")),
        "closed_trades": _int(row.get("closed_trades")),
        "max_drawdown_usd": _float(row.get("max_drawdown_usd")),
        "research_score": _float(row.get("research_score")),
        "best_tradable_leverage": _float(row.get("best_tradable_leverage")),
        "decision_bucket": decision,
        "mark_index_verdict": mark_index,
        "lane_status": status,
        "track_reason": _track_reason(row, status),
    }


def _track_reason(row: dict[str, Any], status: str) -> str:
    symbol = str(row.get("symbol") or "").upper()
    roi = _float(row.get("roi_pct_on_paper_balance"))
    wr = _float(row.get("win_rate"))
    pf = _float(row.get("profit_factor"))
    if status == "preserve_but_reality_check":
        return f"{symbol} a deja produit un backtest fort, mais reste a verifier par data/reality check."
    if status == "review_or_blocked":
        return f"{symbol} conserve l'historique, mais ne doit pas etre promu sans review."
    if roi >= 5 or pf >= 3 or wr >= 0.75:
        return f"{symbol} garde un couple ROI/WR/PF interessant pour exploitation papier."
    return f"{symbol} reste utile comme reference historique du travail deja fait."


def _dedupe_lanes(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = _lane_key(row)
        if not key[0]:
            continue
        if key not in best or _float(row.get("research_score")) > _float(best[key].get("research_score")):
            best[key] = row
    return sorted(best.values(), key=lambda row: _float(row.get("research_score")), reverse=True)[:limit]


def _best_symbol_map(consolidated: dict[str, Any]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    rows = [*(consolidated.get("best_by_symbol") or []), *(consolidated.get("top_lanes") or [])]
    for row in rows:
        symbol = str((row or {}).get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol not in best or _float(row.get("research_score")) > _float(best[symbol].get("research_score")):
            best[symbol] = row
    return best


def _build_exploitation(consolidated: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
    # Start from best_by_symbol so one dominant asset (currently LAB) cannot
    # crowd out every other historical result in the exploitation view.
    rows = [*(consolidated.get("best_by_symbol") or [])]
    rows.extend(_dedupe_lanes(consolidated.get("top_lanes") or [], max(top_n * 3, top_n)))
    compact = [_compact_lane(row, "exploitation") for row in rows]
    by_symbol: dict[str, dict[str, Any]] = {}
    for row in compact:
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        if symbol not in by_symbol or _float(row.get("research_score")) > _float(by_symbol[symbol].get("research_score")):
            by_symbol[symbol] = row
    return sorted(by_symbol.values(), key=lambda row: _float(row.get("research_score")), reverse=True)[:top_n]


def _build_preserve_track(consolidated: dict[str, Any], preserve_symbols: list[str]) -> list[dict[str, Any]]:
    best_by_symbol = _best_symbol_map(consolidated)
    rows = []
    for symbol in preserve_symbols:
        source = best_by_symbol.get(symbol)
        if source:
            rows.append(_compact_lane(source, "preserve_history"))
        else:
            rows.append(
                {
                    "track": "preserve_history",
                    "symbol": symbol,
                    "lane_status": "missing_from_current_consolidated_snapshot",
                    "track_reason": "Symbole mentionne dans les travaux precedents mais absent du dernier rapport consolide.",
                }
            )
    return rows


def _build_exploration(priority: dict[str, Any], exploitation_symbols: set[str], top_n: int) -> list[dict[str, Any]]:
    rows = [*(priority.get("priority_watchlist") or []), *(priority.get("candidate_watchlist") or [])]
    out = []
    for row in rows:
        symbol = str((row or {}).get("symbol") or "").upper()
        if not symbol or symbol in exploitation_symbols:
            continue
        out.append(
            {
                "track": "exploration",
                "symbol": symbol,
                "priority_score": _float(row.get("priority_score")),
                "priority_status": row.get("priority_status"),
                "quote_volume_24h": _float(row.get("quote_volume_24h")),
                "price_change_pct_24h": _float(row.get("price_change_pct_24h")),
                "spread_bps": _float(row.get("spread_bps")),
                "ws_quality_verdict": row.get("ws_quality_verdict"),
                "mark_index_verdict": row.get("mark_index_verdict"),
                "reasons": row.get("reasons") or [],
                "track_reason": "Nouveau candidat issu de l'univers Aster public, a tester sans remplacer les champions historiques.",
            }
        )
    return sorted(out, key=lambda row: _float(row.get("priority_score")), reverse=True)[:top_n]


def get_aster_dual_track_research_report_preview(
    dry_run: bool = True,
    exploitation_top_n: int = 12,
    exploration_top_n: int = 12,
    preserve_symbols: str | list[str] | None = DEFAULT_PRESERVE_SYMBOLS,
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
    safe_exploitation_n = max(1, min(int(exploitation_top_n or 12), 50))
    safe_exploration_n = max(1, min(int(exploration_top_n or 12), 50))
    consolidated = _load_json(CONSOLIDATED_FILE)
    priority = _load_json(PRIORITY_WATCHLIST_FILE)
    exploitation = _build_exploitation(consolidated, safe_exploitation_n)
    exploitation_symbols = {str(row.get("symbol") or "").upper() for row in exploitation if row.get("symbol")}
    exploration = _build_exploration(priority, exploitation_symbols, safe_exploration_n)
    preserve = _build_preserve_track(consolidated, _symbols(preserve_symbols))
    payload = {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "source_policy": "local_snapshots_only_dual_track_research",
        "generated_at": _now(),
        "inputs": {
            "consolidated_report": str(CONSOLIDATED_FILE),
            "priority_watchlist": str(PRIORITY_WATCHLIST_FILE),
            "preserve_symbols": _symbols(preserve_symbols),
        },
        "summary": {
            "exploitation_count": len(exploitation),
            "exploration_count": len(exploration),
            "preserve_history_count": len(preserve),
            "recommended_exploitation_symbols": [row.get("symbol") for row in exploitation[:8]],
            "recommended_exploration_symbols": [row.get("symbol") for row in exploration[:8]],
        },
        "exploitation_track": exploitation,
        "exploration_track": exploration,
        "preserve_history_track": preserve,
        "operating_plan": {
            "principle": "Ne pas abandonner les anciens backtests: une piste exploite les champions, une autre explore les symboles moins testes.",
            "exploitation_use": "Continuer les runners/analyses sur les champions historiques et verifier leurs garde-fous data.",
            "exploration_use": "Lancer des discovery runs separes sur les nouveaux symboles Aster pour eviter le biais LAB/INJ/CRCL/MSFT/INTC.",
            "promotion_rule": "Un symbole exploration ne remplace un champion que s'il obtient assez de trades fermes, ROI positif, PF > 1.3, drawdown acceptable, puis reality check.",
        },
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
