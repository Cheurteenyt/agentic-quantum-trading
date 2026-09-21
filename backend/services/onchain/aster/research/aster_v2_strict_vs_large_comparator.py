from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
PLAN_FILE = BASE_DIR / "aster_v2_runner_plan_latest.json"
SNAPSHOT_FILE = BASE_DIR / "aster_v2_strict_vs_large_comparison_latest.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_path(tag: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(tag or "").strip().lower()).strip("._-")
    return BASE_DIR / f"paper_trading_strategy_discovery_{safe or 'aster_v2'}_v2.csv"


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


def _read_rows(path: Path, max_rows: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row:
                    rows.append(row)
    except OSError:
        return []
    return rows[-max(1, min(int(max_rows or 5000), 100_000)) :]


def _lane_key(row: dict[str, Any]) -> str:
    parts = [
        row.get("symbol"),
        row.get("side"),
        row.get("interval"),
        row.get("search_mode"),
        row.get("score_window_size"),
        row.get("risk_profile"),
        row.get("min_aster_score"),
        row.get("min_window_volume_usd"),
        row.get("stop_loss_pct"),
        row.get("take_profit_pct"),
        row.get("trailing_stop_activation_pct"),
        row.get("trailing_stop_distance_pct"),
        row.get("max_holding_trades"),
    ]
    return "|".join(str(part or "").upper() for part in parts)


def _score(row: dict[str, Any]) -> float:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    wr = _float(row.get("win_rate"))
    pf = _float(row.get("profit_factor"))
    closed = _int(row.get("closed_trades"))
    drawdown = abs(_float(row.get("max_drawdown_usd")))
    positives = _int(row.get("positive_windows"))
    return round(
        max(0.0, roi) * 2.0
        + min(25.0, max(0.0, pf))
        + wr * 12.0
        + min(10.0, closed / 2.0)
        + positives * 2.0
        - min(20.0, drawdown / 2.0),
        6,
    )


def _compact(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": row.get("side"),
        "interval": row.get("interval"),
        "search_mode": row.get("search_mode"),
        "risk_profile": row.get("risk_profile"),
        "min_aster_score": _float(row.get("min_aster_score")),
        "min_window_volume_usd": _float(row.get("min_window_volume_usd")),
        "closed_trades": _int(row.get("closed_trades")),
        "win_rate": _float(row.get("win_rate")),
        "profit_factor": _float(row.get("profit_factor")),
        "pnl_total_usd": _float(row.get("pnl_total_usd")),
        "roi_pct_on_paper_balance": _float(row.get("roi_pct_on_paper_balance")),
        "max_drawdown_usd": _float(row.get("max_drawdown_usd")),
        "best_tradable_leverage": _float(row.get("best_tradable_leverage")),
        "verdict": row.get("verdict"),
        "selection_score": _float(row.get("selection_score"), _score(row)),
        "computed_score": _score(row),
        "output_tag": row.get("output_tag"),
        "timestamp": row.get("timestamp"),
    }


def _best_by_lane(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _lane_key(row)
        if not key.strip("|"):
            continue
        current = best.get(key)
        if current is None or _score(row) > _score(current):
            best[key] = row
    return best


def _best_by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        current = best.get(symbol)
        if current is None or _score(row) > _score(current):
            best[symbol] = row
    return best


def _preflight_map() -> dict[str, dict[str, Any]]:
    plan = _load_json(PLAN_FILE)
    return {
        str(row.get("symbol") or "").upper(): row
        for row in plan.get("preflight_rows") or []
        if isinstance(row, dict) and row.get("symbol")
    }


def _top(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [
        item
        for item in [_compact(row) for row in sorted(rows, key=_score, reverse=True)[: max(1, min(limit, 100))]]
        if item
    ]


def get_aster_v2_strict_vs_large_comparison_preview(
    strict_output_tag: str = "aster_v2_strict",
    large_output_tag: str = "aster_v2",
    max_rows_per_file: int = 50_000,
    top_n: int = 25,
    min_closed_trades: int = 6,
    write_snapshot: bool = True,
) -> dict[str, Any]:
    strict_path = _artifact_path(strict_output_tag)
    large_path = _artifact_path(large_output_tag)
    strict_rows = _read_rows(strict_path, max_rows_per_file)
    large_rows = _read_rows(large_path, max_rows_per_file)
    preflight = _preflight_map()

    strict_best_lane = _best_by_lane(strict_rows)
    large_best_lane = _best_by_lane(large_rows)
    strict_best_symbol = _best_by_symbol(strict_rows)
    large_best_symbol = _best_by_symbol(large_rows)

    common_keys = sorted(set(strict_best_lane) & set(large_best_lane))
    strict_improved = []
    strict_degraded = []
    for key in common_keys:
        strict = strict_best_lane[key]
        large = large_best_lane[key]
        delta_roi = _float(strict.get("roi_pct_on_paper_balance")) - _float(large.get("roi_pct_on_paper_balance"))
        delta_score = _score(strict) - _score(large)
        row = {
            "lane_key": key,
            "symbol": str(strict.get("symbol") or "").upper(),
            "strict": _compact(strict),
            "large": _compact(large),
            "delta_roi_pct": round(delta_roi, 6),
            "delta_score": round(delta_score, 6),
        }
        if delta_roi >= 0 or delta_score >= 0:
            strict_improved.append(row)
        else:
            strict_degraded.append(row)

    strict_only_symbols = sorted(set(strict_best_symbol) - set(large_best_symbol))
    large_only_symbols = sorted(set(large_best_symbol) - set(strict_best_symbol))
    strict_ready_symbols = {
        symbol
        for symbol, row in preflight.items()
        if row.get("preflight_status") == "backtest_ready"
    }
    risky_large_symbols = [
        symbol
        for symbol in sorted(set(large_best_symbol) - strict_ready_symbols)
        if symbol in preflight
    ]

    strict_closed = [row for row in strict_rows if _int(row.get("closed_trades")) >= min_closed_trades]
    large_closed = [row for row in large_rows if _int(row.get("closed_trades")) >= min_closed_trades]
    payload = {
        "ok": bool(strict_rows or large_rows),
        "status": (
            "ready"
            if strict_rows and large_rows
            else "blocked_missing_strict_csv"
            if not strict_rows and large_rows
            else "blocked_missing_large_csv"
            if strict_rows and not large_rows
            else "blocked_missing_both_csv"
        ),
        "comparison_status": (
            "ready"
            if strict_rows and large_rows
            else "blocked_missing_strict_csv"
            if not strict_rows and large_rows
            else "blocked_missing_large_csv"
            if strict_rows and not large_rows
            else "blocked_missing_both_csv"
        ),
        "source_policy": "local_csv_only_aster_v2_strict_vs_large",
        "generated_at": _now(),
        "inputs": {
            "strict_output_tag": strict_output_tag,
            "large_output_tag": large_output_tag,
            "strict_csv": str(strict_path),
            "large_csv": str(large_path),
            "max_rows_per_file": max_rows_per_file,
            "min_closed_trades": min_closed_trades,
        },
        "summary": {
            "strict_rows": len(strict_rows),
            "large_rows": len(large_rows),
            "strict_rows_with_min_closed": len(strict_closed),
            "large_rows_with_min_closed": len(large_closed),
            "common_lanes": len(common_keys),
            "strict_improved_lanes": len(strict_improved),
            "strict_degraded_lanes": len(strict_degraded),
            "strict_only_symbols": len(strict_only_symbols),
            "large_only_symbols": len(large_only_symbols),
            "large_symbols_not_strict_ready": len(risky_large_symbols),
        },
        "top_strict": _top(strict_closed or strict_rows, top_n),
        "top_large": _top(large_closed or large_rows, top_n),
        "strict_improved": sorted(strict_improved, key=lambda row: row["delta_score"], reverse=True)[:top_n],
        "strict_degraded": sorted(strict_degraded, key=lambda row: row["delta_score"])[:top_n],
        "strict_only_symbols": strict_only_symbols[:top_n],
        "large_only_symbols": large_only_symbols[:top_n],
        "large_symbols_not_strict_ready": [
            {
                "symbol": symbol,
                "large_best": _compact(large_best_symbol.get(symbol)),
                "preflight": preflight.get(symbol),
            }
            for symbol in risky_large_symbols[:top_n]
        ],
        "interpretation": {
            "strict_use": "Use strict results for cleaner forward/reality candidates.",
            "large_use": "Use large results as discovery only, especially when symbols are not strict-ready.",
            "missing_strict_csv": "If strict_rows is 0, let the aster_v2_strict terminal finish at least one cycle.",
        },
        "safety": {
            "would_write_snapshot": bool(write_snapshot),
            "writes_performed": 0,
            "would_write_db": False,
            "would_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_external_api": False,
        },
    }
    if write_snapshot:
        SNAPSHOT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["snapshot_path"] = str(SNAPSHOT_FILE)
        payload["safety"]["writes_performed"] = 1
    return payload
