from __future__ import annotations

import argparse
import csv
import html
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .aster_mark_index_replay_filter import get_aster_mark_index_replay_filter_preview
from .aster_microstructure_replay_validator import get_aster_microstructure_replay_validator_preview


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"

QUEUE_CSV = BASE_DIR / "aster_candidate_validation_queue_latest.csv"
JSON_OUT = BASE_DIR / "aster_queue_reality_pack_validator_latest.json"
CSV_OUT = BASE_DIR / "aster_queue_reality_pack_validator_latest.csv"
HTML_OUT = DOCS_DIR / "core-equity-aster-queue-reality-pack-validator.html"


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


def _read_queue(path: Path = QUEUE_CSV) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _lane_key(row: dict[str, Any]) -> tuple[str, ...]:
    strategy_profile_id = str(row.get("strategy_profile_id") or "").strip()
    strategy_profile_key = str(row.get("strategy_profile_key") or "").strip()
    return (
        str(row.get("symbol") or "").upper(),
        str(row.get("interval") or ""),
        str(row.get("side") or "long").lower(),
        str(row.get("trigger_reference") or ""),
        str(row.get("execution_model") or ""),
        str(row.get("best_tradable_leverage") or ""),
        str(row.get("output_tag") or ""),
        strategy_profile_id,
        strategy_profile_key,
    )


def _micro_lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol") or "").upper(),
        str(row.get("interval") or ""),
        str(row.get("side") or "long").lower(),
    )


def _select_lanes(rows: list[dict[str, Any]], *, top_n: int) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            _float(row.get("roi_pct_on_paper_balance")),
            _float(row.get("profit_factor")),
            _float(row.get("win_rate")),
            _int(row.get("closed_trades")),
        ),
        reverse=True,
    )
    seen: set[tuple[str, ...]] = set()
    selected: list[dict[str, Any]] = []
    for row in ranked:
        key = _lane_key(row)
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= top_n:
            break
    return selected


def _mark_overlay(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if isinstance(row, dict):
            symbol = str(row.get("symbol") or "").upper()
            interval = str(row.get("interval") or "")
            if symbol and interval:
                out[(symbol, interval)] = row
    return out


def _micro_overlay(payload: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if isinstance(row, dict):
            symbol = str(row.get("symbol") or "").upper()
            interval = str(row.get("interval") or "")
            side = str(row.get("side") or "long").lower()
            if symbol and interval:
                out[(symbol, interval, side)] = row
    return out


def _decision(row: dict[str, Any], mark: dict[str, Any], micro: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    mark_verdict = str(mark.get("verdict") or row.get("mark_index_verdict") or "not_checked")
    micro_verdict = str(micro.get("verdict") or row.get("microstructure_verdict") or "not_checked")
    if mark_verdict == "mark_index_rejected":
        blockers.append("mark_index_rejected")
    elif mark_verdict in {"not_checked", ""}:
        blockers.append("mark_index_missing")
    if micro_verdict in {"thin_liquidity", "gap_risk", "not_enough_trades"}:
        blockers.append(f"microstructure_{micro_verdict}")
    elif micro_verdict in {"not_checked", ""}:
        blockers.append("microstructure_missing")
    if not blockers:
        return ("validation_passed_watch" if mark_verdict == "mark_index_watch" else "validation_passed_clean", [])
    if "mark_index_rejected" in blockers or any(b.startswith("microstructure_") and b != "microstructure_missing" for b in blockers):
        return "validation_rejected_or_rework", blockers
    return "validation_incomplete", blockers


def _compact_row(row: dict[str, Any], mark: dict[str, Any], micro: dict[str, Any]) -> dict[str, Any]:
    status, blockers = _decision(row, mark, micro)
    trade_metrics = (micro.get("metrics") or {}).get("trades") or {}
    book_metrics = (micro.get("metrics") or {}).get("book") or {}
    return {
        "validation_status": status,
        "validation_blockers": ",".join(blockers),
        "symbol": str(row.get("symbol") or "").upper(),
        "interval": row.get("interval"),
        "side": str(row.get("side") or "long").lower(),
        "output_tag": row.get("output_tag"),
        "strategy_profile_id": row.get("strategy_profile_id"),
        "strategy_profile_key": row.get("strategy_profile_key"),
        "search_mode": row.get("search_mode"),
        "trigger_reference": row.get("trigger_reference"),
        "execution_model": row.get("execution_model"),
        "risk_profile": row.get("risk_profile"),
        "best_tradable_leverage": _float(row.get("best_tradable_leverage")),
        "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
        "win_rate": _float(row.get("win_rate")),
        "profit_factor": _float(row.get("profit_factor")),
        "closed_trades": _int(row.get("closed_trades")),
        "mark_index_verdict": mark.get("verdict") or row.get("mark_index_verdict") or "not_checked",
        "mark_index_blockers": ",".join(mark.get("blockers") or []),
        "mark_index_warnings": ",".join(mark.get("warnings") or []),
        "microstructure_verdict": micro.get("verdict") or row.get("microstructure_verdict") or "not_checked",
        "microstructure_blockers": ",".join(micro.get("blockers") or []),
        "microstructure_warnings": ",".join(micro.get("warnings") or []),
        "trade_count": _int(trade_metrics.get("trade_count")),
        "quote_volume_usd": _float(trade_metrics.get("quote_volume_usd")),
        "spread_bps": _float(book_metrics.get("spread_bps")),
        "simulated_slippage_bps": _float(book_metrics.get("simulated_slippage_bps")),
        "top10_depth_usd": _float(book_metrics.get("top10_depth_usd")),
        "next_action": (
            "candidate_for_forward_watch"
            if status.startswith("validation_passed")
            else "rework_or_collect_more_reality_validation"
        ),
    }


def _write_csv(rows: list[dict[str, Any]], path: Path = CSV_OUT) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_html(payload: dict[str, Any], path: Path = HTML_OUT) -> None:
    rows = payload.get("rows") or []
    body = "\n".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(row.get(col, '')))}</td>"
            for col in [
                "validation_status",
                "symbol",
                "interval",
                "trigger_reference",
                "execution_model",
                "roi_pct_on_paper_balance",
                "win_rate",
                "profit_factor",
                "mark_index_verdict",
                "microstructure_verdict",
                "next_action",
            ]
        )
        + "</tr>"
        for row in rows
    )
    path.write_text(
        f"""<!doctype html>
<html lang=\"fr\"><head><meta charset=\"utf-8\" />
<title>Core Equity - Aster Queue Reality Pack</title>
<style>
body{{margin:0;background:#0d1117;color:#edf2f7;font-family:Segoe UI,Arial,sans-serif;line-height:1.5}}
main{{max-width:1280px;margin:0 auto;padding:34px 22px 60px}}
h1{{font-size:38px;margin:0 0 10px}} p{{color:#aab4c0}}
table{{width:100%;border-collapse:collapse;margin-top:18px}} th,td{{border-bottom:1px solid #2b3545;padding:10px;text-align:left;font-size:13px}}
th{{background:#111923;color:#f2c979}} .card{{background:#151b24;border:1px solid #2b3545;border-radius:18px;padding:18px;margin-top:16px}}
code{{background:#090d12;padding:2px 6px;border-radius:6px}}
</style></head><body><main>
<h1>Aster Queue Reality Pack Validator</h1>
<p>Validation read-only des meilleurs candidats de <code>aster_candidate_validation_queue_latest.csv</code>.</p>
<div class=\"card\"><p>Genere le {html.escape(str(payload.get('generated_at')))}. Summary: {html.escape(json.dumps(payload.get('summary'), ensure_ascii=False))}</p></div>
<table><thead><tr><th>Status</th><th>Symbol</th><th>TF</th><th>Trigger</th><th>Execution</th><th>ROI</th><th>WR</th><th>PF</th><th>Mark/Index</th><th>Microstructure</th><th>Next</th></tr></thead><tbody>
{body}
</tbody></table></main></body></html>""",
        encoding="utf-8",
    )


def get_aster_queue_reality_pack_validator_preview(
    top_n: int = 12,
    dry_run: bool = True,
    lookback_days: int = 30,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 300,
    position_notional_usd: float = 100.0,
    write_snapshot: bool = False,
) -> dict[str, Any]:
    if not dry_run:
        return {"ok": False, "status": "blocked", "blockers": ["dry_run_required"], "would_execute_trade": False}
    queue_rows = _read_queue()
    selected = _select_lanes(queue_rows, top_n=max(1, min(int(top_n or 12), 20)))
    symbols = sorted({row["symbol"] for row in selected if row.get("symbol")})
    intervals = sorted({row["interval"] for row in selected if row.get("interval")})
    champions = ",".join(f"{row['symbol']}:{row['interval']}:{row.get('side') or 'long'}" for row in selected)
    mark_payload = get_aster_mark_index_replay_filter_preview(
        symbols=symbols,
        intervals=intervals,
        dry_run=True,
        lookback_days=lookback_days,
        timeout_seconds=timeout_seconds,
        rate_limit_delay_ms=rate_limit_delay_ms,
    )
    time.sleep(max(0, min(int(rate_limit_delay_ms or 300), 2_000)) / 1000)
    micro_payload = get_aster_microstructure_replay_validator_preview(
        champions=champions,
        dry_run=True,
        position_notional_usd=position_notional_usd,
        timeout_seconds=timeout_seconds,
        rate_limit_delay_ms=rate_limit_delay_ms,
    )
    marks = _mark_overlay(mark_payload)
    micros = _micro_overlay(micro_payload)
    rows = [
        _compact_row(
            row,
            marks.get((str(row.get("symbol") or "").upper(), str(row.get("interval") or ""))) or {},
            micros.get(_micro_lane_key(row)) or {},
        )
        for row in selected
    ]
    summary = {
        "selected_lanes": len(rows),
        "validation_passed_clean": sum(1 for row in rows if row["validation_status"] == "validation_passed_clean"),
        "validation_passed_watch": sum(1 for row in rows if row["validation_status"] == "validation_passed_watch"),
        "validation_incomplete": sum(1 for row in rows if row["validation_status"] == "validation_incomplete"),
        "validation_rejected_or_rework": sum(1 for row in rows if row["validation_status"] == "validation_rejected_or_rework"),
    }
    payload = {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "take_top_candidate_validation_queue_lanes_and_refresh_public_mark_index_plus_microstructure_validation",
        "queue_source": str(QUEUE_CSV),
        "summary": summary,
        "mark_index_summary": mark_payload.get("summary"),
        "microstructure_summary": micro_payload.get("summary"),
        "rows": rows,
        "safety": {
            "would_write": bool(write_snapshot),
            "writes_performed": 0,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "source_policy": "public_aster_rest_read_only",
        },
    }
    if write_snapshot:
        JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        _write_csv(rows)
        _write_html(payload)
        payload["safety"]["writes_performed"] = 3
        payload["outputs"] = {"json": str(JSON_OUT), "csv": str(CSV_OUT), "html": str(HTML_OUT)}
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate top Aster candidate queue lanes with mark/index and microstructure.")
    parser.add_argument("--top-n", type=int, default=12)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=10)
    parser.add_argument("--rate-limit-delay-ms", type=int, default=300)
    parser.add_argument("--position-notional-usd", type=float, default=100.0)
    parser.add_argument("--write-snapshot", action="store_true")
    args = parser.parse_args()
    payload = get_aster_queue_reality_pack_validator_preview(**vars(args))
    print(f"[{payload.get('generated_at')}] status={payload.get('status')} summary={payload.get('summary')} outputs={payload.get('outputs')}")


if __name__ == "__main__":
    main()
