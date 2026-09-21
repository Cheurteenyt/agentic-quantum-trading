from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from services.onchain.aster.aster_agent_decision_engine import (
    calculate_position_size,
    run_aster_agent_loop_test,
    should_enter_position,
    should_exit_position,
)
from services.onchain.aster.aster_perps_model import execution_fee_bps
from services.onchain.behavioral_evidence_bridge import (
    get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview,
)
from services.onchain.core.paths import DB_PATH


TABLE_NAME = "aster_paper_trading_ledger"
CREATE_CONFIRM = "CREATE_ASTER_PAPER_TRADING_LEDGER"
REPLAY_CONFIRM = "CONFIRM_ASTER_PAPER_REPLAY_INSERT"
WATCHLIST_REPLAY_CONFIRM = "CONFIRM_ASTER_WATCHLIST_REPLAY_INSERT"
FORWARD_PAPER_TRADE_CONFIRM = "CONFIRM_FORWARD_PAPER_TRADE"
FORWARD_SHORT_PAPER_TRADE_CONFIRM = "CONFIRM_FORWARD_SHORT_PAPER_TRADE"
STATEFUL_FORWARD_PAPER_TRADE_CONFIRM = "CONFIRM_STATEFUL_FORWARD_PAPER_TRADE"
ASTER_REST_BASE_URL = "https://fapi.asterdex.com"
ASTER_SPOT_BASE_URL = "https://api.asterdex.com"
EXTENDED_BACKTEST_SYMBOLS = [
    "LABUSDT",
    "ORDIUSDT",
    "1000SATSUSDT",
    "PEPEUSDT",
    "BONKUSDT",
    "WIFUSDT",
    "BOMEUSDT",
    "MEMEUSDT",
    "FLOKIUSDT",
    "SHIBUSDT",
    "DOGEUSDT",
    "SOLUSDT",
    "SUIUSDT",
    "SEIUSDT",
    "APTUSDT",
    "TIAUSDT",
    "INJUSDT",
    "NEARUSDT",
    "ARBUSDT",
    "OPUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "ADAUSDT",
    "XRPUSDT",
    "WLDUSDT",
    "JUPUSDT",
]
SELECTED_SHORT_FADE_FORWARD_SYMBOLS = [
    "1000SATSUSDT",
    "ORDIUSDT",
    "JUPUSDT",
    "ARBUSDT",
    "OPUSDT",
    "SEIUSDT",
    "WLDUSDT",
    "TIAUSDT",
]
HYBRID_SEED_SYMBOL_TO_TOKEN = {
    "LABUSDT": "0x7ec43cf65f1663f820427c62a5780b8f2e25593a",
    "BUSDT": "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
    "LONGUSDT": "0x9eca8dedb4882bd694aea786c0cbe770e70d52e3",
}
_trade_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_KLINE_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "3h": 10_800_000,
    "4h": 14_400_000,
    "5h": 18_000_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_symbols(value: str | list[str] | tuple[str, ...] | None, default: list[str]) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw = [str(item or "").strip().upper() for item in value]
    else:
        raw = [item.strip().upper() for item in str(value or "").replace(";", ",").split(",")]
    return [item for item in raw if item] or default


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,)).fetchone()
    return bool(row)


def _disabled() -> dict[str, Any]:
    return {
        "source_policy": "aster_paper_trading_sandbox_dry_run_first",
        "would_execute_trade": False,
        "would_send_transaction": False,
        "would_create_wallet_order": False,
        "would_create_client_signal": False,
        "would_create_client_opt_in": False,
        "would_create_label": False,
        "would_create_mapping": False,
        "would_write_business_db": False,
    }


def _schema_sql() -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    symbol TEXT,
    token_address TEXT,
    event_type TEXT NOT NULL,
    state TEXT,
    decision_reason TEXT,
    aster_score REAL,
    behavioral_score REAL,
    entry_price REAL,
    current_price REAL,
    size_usd REAL,
    fees_usd REAL,
    slippage_usd REAL,
    pnl_unrealized_usd REAL,
    pnl_realized_usd REAL,
    max_drawdown_usd REAL,
    raw_payload_json TEXT NOT NULL
);
""".strip()


def get_aster_paper_trading_schema_plan(dry_run: bool = True) -> dict[str, Any]:
    disabled = _disabled()
    with _connect() as conn:
        exists = _table_exists(conn)
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "plan_status": "ready_read_only",
        "target_table": TABLE_NAME,
        "table_exists": exists,
        "migration_required": not exists,
        "schema_preview": _schema_sql(),
        "indexes_preview": [
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_run_id ON {TABLE_NAME}(run_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_symbol_created ON {TABLE_NAME}(symbol, created_at)",
        ],
        "confirm_required": CREATE_CONFIRM if not exists else None,
        "would_create_table": False,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def create_aster_paper_trading_ledger_table(
    dry_run: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    disabled = _disabled()
    plan = get_aster_paper_trading_schema_plan(True)
    blockers: list[str] = []
    if not dry_run and confirm != CREATE_CONFIRM:
        blockers.append("confirm_CREATE_ASTER_PAPER_TRADING_LEDGER_required")
    if plan.get("plan_status") != "ready_read_only":
        blockers.append("schema_plan_not_ready")
    if dry_run or blockers:
        return {
            "ok": not blockers,
            "dry_run": dry_run,
            "create_status": "blocked" if blockers else "dry_run_only_no_table_created",
            "blockers": blockers,
            "target_table": TABLE_NAME,
            "confirm_required": CREATE_CONFIRM,
            "would_create_table": bool(not dry_run and not blockers),
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    with _connect() as conn:
        existed_before = _table_exists(conn)
        conn.execute(_schema_sql())
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_run_id ON {TABLE_NAME}(run_id)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_symbol_created ON {TABLE_NAME}(symbol, created_at)")
        conn.commit()
        row_count = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    return {
        "ok": True,
        "dry_run": False,
        "create_status": "already_exists" if existed_before else "created",
        "target_table": TABLE_NAME,
        "rows_inserted": 0,
        "row_count": row_count,
        "would_create_table": False,
        "would_write": True,
        "writes_performed": 1 if not existed_before else 0,
        **disabled,
    }


def _ledger_rows_from_agent(agent: dict[str, Any], run_id: str, fee_bps: float, slippage_bps: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for decision in agent.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        size = _as_float(decision.get("position_size_usd"))
        current_price = _as_float(decision.get("current_price"))
        fee = round(size * fee_bps / 10_000, 6) if size else 0.0
        slip = round(size * slippage_bps / 10_000, 6) if size else 0.0
        event_type = "entry_simulated" if decision.get("should_enter") else "decision_rejected"
        rows.append(
            {
                "run_id": run_id,
                "created_at": _now(),
                "symbol": decision.get("symbol") or decision.get("token"),
                "token_address": decision.get("token_address"),
                "event_type": event_type,
                "state": decision.get("state"),
                "decision_reason": decision.get("reason") or decision.get("monitor_status"),
                "aster_score": _as_float(decision.get("aster_score")),
                "behavioral_score": decision.get("behavioral_score"),
                "entry_price": current_price if event_type == "entry_simulated" else None,
                "current_price": current_price or None,
                "size_usd": size,
                "fees_usd": fee,
                "slippage_usd": slip,
                "pnl_unrealized_usd": round(-fee - slip, 6) if size else 0.0,
                "pnl_realized_usd": 0.0,
                "max_drawdown_usd": round(fee + slip, 6) if size else 0.0,
                "raw_payload_json": json.dumps(decision, sort_keys=True),
            }
        )
    return rows


def _report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    entries = [row for row in rows if row.get("event_type") == "entry_simulated"]
    rejected = [row for row in rows if row.get("event_type") == "decision_rejected"]
    pnl_realized = sum(_as_float(row.get("pnl_realized_usd")) for row in rows)
    pnl_unrealized = sum(_as_float(row.get("pnl_unrealized_usd")) for row in rows)
    exposure = sum(_as_float(row.get("size_usd")) for row in entries)
    max_drawdown = max([_as_float(row.get("max_drawdown_usd")) for row in rows] or [0.0])
    wins = sum(1 for row in rows if _as_float(row.get("pnl_realized_usd")) > 0)
    closed = sum(1 for row in rows if _as_float(row.get("pnl_realized_usd")) != 0)
    return {
        "simulated_trade_count": len(entries),
        "rejected_decision_count": len(rejected),
        "win_rate": round(wins / closed, 6) if closed else None,
        "pnl_total_usd": round(pnl_realized + pnl_unrealized, 6),
        "pnl_realized_usd": round(pnl_realized, 6),
        "pnl_unrealized_usd": round(pnl_unrealized, 6),
        "max_drawdown_usd": round(max_drawdown, 6),
        "current_exposure_usd": round(exposure, 6),
        "why_no_entry": [row.get("decision_reason") for row in rejected] or [],
    }


def _fetch_trades_url(url: str, timeout_seconds: int) -> dict[str, Any]:
    safe_timeout = max(1, min(_as_int(timeout_seconds, 15), 15))
    request = urllib.request.Request(url, headers={"User-Agent": "CoreEquityAsterPaperReplay/1.0"})
    retries_triggered = 0
    last_error: str | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=safe_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, list):
                return {"ok": False, "fetch_status": "invalid_response", "url": url, "trades": [], "retries_triggered": retries_triggered}
            trades = [trade for trade in payload if isinstance(trade, dict)]
            trades.sort(key=lambda row: (_as_int(row.get("time")), _as_int(row.get("id"))))
            return {"ok": True, "fetch_status": "ready", "url": url, "trades": trades, "retries_triggered": retries_triggered}
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                return {"ok": False, "fetch_status": "blocked_by_aster", "http_status": exc.code, "retry_after": 60, "url": url, "trades": [], "retries_triggered": retries_triggered}
            if exc.code == 404:
                return {"ok": False, "fetch_status": "not_found", "http_status": exc.code, "url": url, "trades": [], "retries_triggered": retries_triggered}
            if exc.code == 429 or exc.code >= 500:
                if attempt < 3:
                    retries_triggered += 1
                    time.sleep(min(4.0, (2**attempt) * 0.5))
                    continue
                status = "rate_limited" if exc.code == 429 else "server_error"
                return {"ok": False, "fetch_status": status, "http_status": exc.code, "url": url, "trades": [], "retries_triggered": retries_triggered}
            return {"ok": False, "fetch_status": "http_error", "http_status": exc.code, "url": url, "trades": [], "retries_triggered": retries_triggered}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            if attempt < 3:
                retries_triggered += 1
                time.sleep(min(4.0, (2**attempt) * 0.5))
                continue
            return {"ok": False, "fetch_status": "request_failed", "error": last_error, "url": url, "trades": [], "retries_triggered": retries_triggered}
    return {"ok": False, "fetch_status": "request_failed", "error": last_error, "url": url, "trades": [], "retries_triggered": retries_triggered}


def _fetch_recent_trades(symbol: str, max_events: int, timeout_seconds: int) -> dict[str, Any]:
    safe_symbol = str(symbol or "BTCUSDT").strip().upper() or "BTCUSDT"
    safe_limit = max(1, min(_as_int(max_events, 100), 5000))
    cache_key = f"{safe_symbol}:{safe_limit}"
    cached = _trade_cache.get(cache_key)
    now_ts = time.time()
    if cached and now_ts - cached[0] <= 15:
        return {
            "ok": True,
            "fetch_status": "ready",
            "cache_hit": True,
            "cache_ttl_seconds": 15,
            "symbol": safe_symbol,
            "effective_limit": safe_limit,
            "trades": list(cached[1])[:safe_limit],
            "retries_triggered": 0,
        }
    query = urllib.parse.urlencode({"symbol": safe_symbol, "limit": safe_limit})
    url = f"{ASTER_REST_BASE_URL}/fapi/v1/trades?{query}"
    result = _fetch_trades_url(url, timeout_seconds)
    if not result.get("ok") and safe_limit > 1000:
        retry_query = urllib.parse.urlencode({"symbol": safe_symbol, "limit": 1000})
        retry = _fetch_trades_url(f"{ASTER_REST_BASE_URL}/fapi/v1/trades?{retry_query}", timeout_seconds)
        retry["requested_limit"] = safe_limit
        retry["effective_limit"] = 1000
        retry["limit_fallback_reason"] = result.get("fetch_status")
        result = retry
    result["trades"] = (result.get("trades") or [])[:safe_limit]
    result["cache_hit"] = False
    result["symbol"] = safe_symbol
    if result.get("ok"):
        _trade_cache[cache_key] = (now_ts, list(result.get("trades") or []))
    return result


def _fetch_recent_trades_with_spot_fallback(symbol: str, max_events: int, timeout_seconds: int) -> dict[str, Any]:
    safe_symbol = str(symbol or "").strip().upper()
    safe_limit = max(1, min(_as_int(max_events, 2_000), 5000))
    attempts: list[dict[str, Any]] = []
    futures = _fetch_recent_trades(safe_symbol, safe_limit, timeout_seconds)
    attempts.append({k: futures.get(k) for k in ("ok", "fetch_status", "http_status", "url", "error")})
    if futures.get("ok"):
        return {**futures, "market_type": "futures", "attempts": attempts}
    for path in ("/api/v1/trades", "/api/v3/trades"):
        query = urllib.parse.urlencode({"symbol": safe_symbol, "limit": safe_limit})
        result = _fetch_trades_url(f"{ASTER_SPOT_BASE_URL}{path}?{query}", timeout_seconds)
        attempts.append({k: result.get(k) for k in ("ok", "fetch_status", "http_status", "url", "error")})
        if not result.get("ok") and safe_limit > 1000 and result.get("http_status") == 400:
            retry_query = urllib.parse.urlencode({"symbol": safe_symbol, "limit": 1000})
            retry = _fetch_trades_url(f"{ASTER_SPOT_BASE_URL}{path}?{retry_query}", timeout_seconds)
            retry["requested_limit"] = safe_limit
            retry["effective_limit"] = 1000
            retry["limit_fallback_reason"] = "http_400"
            attempts.append({k: retry.get(k) for k in ("ok", "fetch_status", "http_status", "url", "error")})
            result = retry
        if result.get("ok"):
            return {**result, "trades": (result.get("trades") or [])[:safe_limit], "market_type": "spot", "attempts": attempts}
    return {"ok": False, "fetch_status": "all_markets_failed", "market_type": None, "attempts": attempts, "trades": []}


def _fetch_klines_url(url: str, timeout_seconds: int) -> dict[str, Any]:
    result = _fetch_json_url(url, timeout_seconds)
    if not result.get("ok"):
        return {**result, "klines": []}
    payload = result.get("payload")
    if not isinstance(payload, list):
        return {**result, "ok": False, "fetch_status": "invalid_response", "klines": []}
    klines = [row for row in payload if isinstance(row, list) and len(row) >= 12]
    klines.sort(key=lambda row: _as_int(row[0]))
    return {**result, "fetch_status": "ready", "klines": klines}


def _aggregate_klines(klines: list[list[Any]], interval: str) -> list[list[Any]]:
    factor = {"3h": 3, "5h": 5}.get(interval)
    if not factor:
        return klines
    aggregated: list[list[Any]] = []
    bucket_ms = factor * _KLINE_INTERVAL_MS["1h"]
    buckets: dict[int, list[list[Any]]] = {}
    for row in sorted(klines, key=lambda item: _as_int(item[0])):
        open_time = _as_int(row[0])
        bucket_start = (open_time // bucket_ms) * bucket_ms
        buckets.setdefault(bucket_start, []).append(row)
    for bucket_start in sorted(buckets):
        chunk = sorted(buckets[bucket_start], key=lambda item: _as_int(item[0]))
        if len(chunk) < factor:
            continue
        open_time = _as_int(chunk[0][0])
        close_time = _as_int(chunk[-1][6])
        open_price = chunk[0][1]
        close_price = chunk[-1][4]
        high_price = str(max(_as_float(row[2]) for row in chunk))
        low_price = str(min(_as_float(row[3]) for row in chunk))
        base_volume = str(sum(_as_float(row[5]) for row in chunk))
        quote_volume = str(sum(_as_float(row[7]) for row in chunk))
        trade_count = sum(_as_int(row[8]) for row in chunk)
        taker_buy_base = str(sum(_as_float(row[9]) for row in chunk))
        taker_buy_quote = str(sum(_as_float(row[10]) for row in chunk))
        aggregated.append(
            [
                open_time,
                open_price,
                high_price,
                low_price,
                close_price,
                base_volume,
                close_time,
                quote_volume,
                trade_count,
                taker_buy_base,
                taker_buy_quote,
                "0",
            ]
        )
    return aggregated


def _fetch_klines_with_spot_fallback(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    timeout_seconds: int,
    max_pages: int = 10,
) -> dict[str, Any]:
    safe_symbol = str(symbol or "").strip().upper()
    safe_interval = str(interval or "1h").strip()
    interval_ms = _KLINE_INTERVAL_MS.get(safe_interval)
    if not interval_ms:
        return {"ok": False, "fetch_status": "unsupported_interval", "klines": [], "attempts": []}
    synthetic_interval = safe_interval in {"3h", "5h"}
    query_interval = "1h" if synthetic_interval else safe_interval
    query_interval_ms = _KLINE_INTERVAL_MS.get(query_interval, interval_ms)
    attempts: list[dict[str, Any]] = []
    markets = [
        ("futures", ASTER_REST_BASE_URL, "/fapi/v1/klines"),
        ("spot", ASTER_SPOT_BASE_URL, "/api/v3/klines"),
        ("spot", ASTER_SPOT_BASE_URL, "/api/v1/klines"),
    ]
    for market_type, base_url, path in markets:
        cursor = max(0, _as_int(start_ms))
        all_klines: list[list[Any]] = []
        seen_open_times: set[int] = set()
        pages_used = 0
        market_failed = False
        while cursor < end_ms and pages_used < max(1, min(_as_int(max_pages, 10), 20)):
            query = urllib.parse.urlencode(
                {
                    "symbol": safe_symbol,
                    "interval": query_interval,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": 1500,
                }
            )
            result = _fetch_klines_url(f"{base_url}{path}?{query}", timeout_seconds)
            attempts.append(
                {
                    "market_type": market_type,
                    "ok": bool(result.get("ok")),
                    "fetch_status": result.get("fetch_status"),
                    "http_status": result.get("http_status"),
                    "url": result.get("url"),
                    "rows": len(result.get("klines") or []),
                }
            )
            if not result.get("ok"):
                market_failed = True
                break
            rows = result.get("klines") or []
            if not rows:
                break
            for row in rows:
                open_time = _as_int(row[0])
                if open_time not in seen_open_times:
                    seen_open_times.add(open_time)
                    all_klines.append(row)
            pages_used += 1
            next_cursor = _as_int(rows[-1][0]) + query_interval_ms
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            if len(rows) < 1500:
                break
            time.sleep(0.1)
        if all_klines and not market_failed:
            if synthetic_interval:
                all_klines = _aggregate_klines(all_klines, safe_interval)
            all_klines.sort(key=lambda row: _as_int(row[0]))
            return {
                "ok": True,
                "fetch_status": "ready",
                "market_type": market_type,
                "symbol": safe_symbol,
                "interval": safe_interval,
                "source_interval": query_interval,
                "synthetic_interval": synthetic_interval,
                "klines": all_klines,
                "pages_used": pages_used,
                "attempts": attempts,
            }
    return {"ok": False, "fetch_status": "all_markets_failed", "market_type": None, "klines": [], "attempts": attempts}


def _fetch_futures_reference_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    timeout_seconds: int,
    path: str,
    param_name: str = "symbol",
    max_pages: int = 10,
) -> dict[str, Any]:
    safe_symbol = str(symbol or "").strip().upper()
    safe_interval = str(interval or "1h").strip()
    interval_ms = _KLINE_INTERVAL_MS.get(safe_interval)
    if not interval_ms:
        return {"ok": False, "fetch_status": "unsupported_interval", "klines": [], "attempts": []}
    synthetic_interval = safe_interval in {"3h", "5h"}
    query_interval = "1h" if synthetic_interval else safe_interval
    query_interval_ms = _KLINE_INTERVAL_MS.get(query_interval, interval_ms)
    cursor = max(0, _as_int(start_ms))
    all_klines: list[list[Any]] = []
    seen_open_times: set[int] = set()
    attempts: list[dict[str, Any]] = []
    pages_used = 0
    while cursor < end_ms and pages_used < max(1, min(_as_int(max_pages, 10), 20)):
        query = urllib.parse.urlencode(
            {
                param_name: safe_symbol,
                "interval": query_interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            }
        )
        result = _fetch_klines_url(f"{ASTER_REST_BASE_URL}{path}?{query}", timeout_seconds)
        attempts.append({"ok": bool(result.get("ok")), "fetch_status": result.get("fetch_status"), "http_status": result.get("http_status"), "rows": len(result.get("klines") or [])})
        if not result.get("ok"):
            break
        rows = result.get("klines") or []
        if not rows:
            break
        for row in rows:
            open_time = _as_int(row[0])
            if open_time not in seen_open_times:
                seen_open_times.add(open_time)
                all_klines.append(row)
        pages_used += 1
        next_cursor = _as_int(rows[-1][0]) + query_interval_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(rows) < 1500:
            break
        time.sleep(0.1)
    if synthetic_interval:
        all_klines = _aggregate_klines(all_klines, safe_interval)
    all_klines.sort(key=lambda row: _as_int(row[0]))
    return {
        "ok": bool(all_klines),
        "fetch_status": "ready" if all_klines else "empty_or_failed",
        "market_type": "futures",
        "symbol": safe_symbol,
        "interval": safe_interval,
        "source_interval": query_interval,
        "synthetic_interval": synthetic_interval,
        "klines": all_klines,
        "pages_used": pages_used,
        "attempts": attempts,
    }


def _apply_mark_price_reference(trades: list[dict[str, Any]], mark_klines: list[list[Any]]) -> tuple[list[dict[str, Any]], int]:
    mark_by_time = {_as_int(row[0]): _as_float(row[4]) for row in mark_klines if isinstance(row, list) and len(row) > 4}
    out: list[dict[str, Any]] = []
    applied = 0
    for trade in trades:
        open_time = _as_int(trade.get("time"))
        mark_price = mark_by_time.get(open_time)
        if mark_price and mark_price > 0:
            row = {**trade, "last_price": trade.get("price"), "price": str(mark_price), "mark_price": str(mark_price), "trigger_reference": "mark_price"}
            applied += 1
        else:
            row = {**trade, "trigger_reference": "last_price_fallback_missing_mark"}
        out.append(row)
    return out, applied


def _kline_to_proxy_trade(kline: list[Any], symbol: str, index: int) -> dict[str, Any]:
    open_time = _as_int(kline[0])
    close_price = _as_float(kline[4])
    base_volume = _as_float(kline[5])
    quote_volume = _as_float(kline[7])
    taker_buy_quote = _as_float(kline[10])
    is_buyer_maker = taker_buy_quote < (quote_volume / 2) if quote_volume > 0 else False
    return {
        "id": f"kline-{symbol}-{open_time}-{index}",
        "time": open_time,
        "price": str(close_price),
        "qty": str(base_volume),
        "quoteQty": str(quote_volume),
        "isBuyerMaker": is_buyer_maker,
        "source": "aster_kline_proxy",
        "open": kline[1],
        "high": kline[2],
        "low": kline[3],
        "close": kline[4],
        "close_time": kline[6],
        "trade_count": kline[8],
    }


def _fetch_json_url(url: str, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "CoreEquityPaperTrading/1.0"})
    try:
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=max(1, min(_as_int(timeout_seconds, 10), 15))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "ok": True,
            "http_status": 200,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "payload": payload,
            "url": url,
        }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "http_status": exc.code, "fetch_status": f"http_{exc.code}", "error": str(exc), "url": url}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "fetch_status": "request_failed", "error": str(exc), "url": url}


def _fetch_aster_futures_symbols(timeout_seconds: int) -> dict[str, Any]:
    result = _fetch_json_url(f"{ASTER_REST_BASE_URL}/fapi/v1/exchangeInfo", timeout_seconds)
    if not result.get("ok"):
        return {**result, "symbols": []}
    payload = result.get("payload")
    rows = payload.get("symbols") if isinstance(payload, dict) else []
    symbols = []
    for row in rows or []:
        symbol = str(row.get("symbol") or "").upper()
        quote = str(row.get("quoteAsset") or row.get("quote") or "").upper()
        status = str(row.get("status") or "").upper()
        if symbol.endswith("USDT") and (not quote or quote == "USDT") and status not in {"BREAK", "CLOSE", "CLOSED"}:
            symbols.append(symbol)
    return {**result, "symbols": sorted(set(symbols))}


def _fetch_aster_24h_tickers(timeout_seconds: int) -> dict[str, Any]:
    result = _fetch_json_url(f"{ASTER_REST_BASE_URL}/fapi/v1/ticker/24hr", timeout_seconds)
    if not result.get("ok"):
        return {**result, "tickers": []}
    payload = result.get("payload")
    rows = payload if isinstance(payload, list) else []
    return {**result, "tickers": rows}


def _discover_aster_volatile_universe(
    max_symbols: int,
    timeout_seconds: int,
    min_quote_volume_usd: float,
    min_abs_price_change_pct: float,
) -> dict[str, Any]:
    exchange = _fetch_aster_futures_symbols(timeout_seconds)
    tickers = _fetch_aster_24h_tickers(timeout_seconds)
    if not exchange.get("ok") or not tickers.get("ok"):
        return {
            "ok": False,
            "discovery_status": "api_failed",
            "exchange_status": exchange.get("fetch_status") or exchange.get("http_status"),
            "ticker_status": tickers.get("fetch_status") or tickers.get("http_status"),
            "candidates": [],
        }
    tradable = set(exchange.get("symbols") or [])
    candidates: list[dict[str, Any]] = []
    for row in tickers.get("tickers") or []:
        symbol = str(row.get("symbol") or "").upper()
        if symbol not in tradable:
            continue
        quote_volume = _as_float(row.get("quoteVolume") or row.get("volume") or row.get("turnover"))
        change_pct = _as_float(row.get("priceChangePercent"))
        trade_count = _as_int(row.get("count") or row.get("tradeCount") or row.get("numTrades"))
        if quote_volume < _as_float(min_quote_volume_usd) or abs(change_pct) < _as_float(min_abs_price_change_pct):
            continue
        candidates.append(
            {
                "symbol": symbol,
                "quote_volume_usd": round(quote_volume, 3),
                "price_change_pct": round(change_pct, 6),
                "abs_price_change_pct": round(abs(change_pct), 6),
                "trade_count": trade_count,
                "volatility_rank_score": round(abs(change_pct) * 10 + min(100.0, quote_volume / 100_000) + min(50.0, trade_count / 1000), 6),
            }
        )
    candidates.sort(key=lambda item: (item["volatility_rank_score"], item["quote_volume_usd"]), reverse=True)
    return {
        "ok": True,
        "discovery_status": "ready",
        "tradable_usdt_symbols": len(tradable),
        "ticker_rows": len(tickers.get("tickers") or []),
        "candidates": candidates[: max(1, min(_as_int(max_symbols, 30), 50))],
    }


def _trade_price(trade: dict[str, Any]) -> float:
    return _as_float(trade.get("price"))


def _trade_notional(trade: dict[str, Any]) -> float:
    quote = _as_float(trade.get("quoteQty"))
    if quote > 0:
        return quote
    return _trade_price(trade) * _as_float(trade.get("qty"))


def get_aster_api_resilience_test(
    symbol: str | None = "BTCUSDT",
    dry_run: bool = True,
    request_count: int = 5,
    max_events: int = 100,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    disabled = _disabled()
    safe_symbol = str(symbol or "BTCUSDT").strip().upper() or "BTCUSDT"
    safe_count = max(1, min(_as_int(request_count, 5), 10))
    safe_events = max(1, min(_as_int(max_events, 100), 1000))
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    cache_hits = 0
    retries_triggered = 0
    blocks_encountered = 0
    for _ in range(safe_count):
        started = time.perf_counter()
        result = _fetch_recent_trades(safe_symbol, safe_events, timeout_seconds)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        if result.get("cache_hit"):
            cache_hits += 1
        retries_triggered += _as_int(result.get("retries_triggered"))
        if result.get("fetch_status") == "blocked_by_aster":
            blocks_encountered += 1
        results.append(
            {
                "ok": bool(result.get("ok")),
                "fetch_status": result.get("fetch_status"),
                "http_status": result.get("http_status"),
                "cache_hit": bool(result.get("cache_hit")),
                "retries_triggered": _as_int(result.get("retries_triggered")),
                "latency_ms": round(elapsed_ms, 3),
                "trades": len(result.get("trades") or []),
                "retry_after": result.get("retry_after"),
            }
        )
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "symbol": safe_symbol,
        "request_count": safe_count,
        "cache_hits": cache_hits,
        "retries_triggered": retries_triggered,
        "blocks_encountered": blocks_encountered,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "results": results,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def _aster_score_proxy(window: list[dict[str, Any]]) -> dict[str, Any]:
    notionals = [_trade_notional(trade) for trade in window]
    volume = sum(notionals)
    buys = sum(1 for trade in window if not bool(trade.get("isBuyerMaker")))
    sells = max(0, len(window) - buys)
    buy_sell_ratio = buys / max(1, sells)
    largest_share = (max(notionals) / volume) if volume > 0 and notionals else 0.0
    sizes = [round(_as_float(trade.get("qty")), 8) for trade in window]
    repeated_sizes = len(sizes) - len(set(sizes))
    repetition_ratio = repeated_sizes / max(1, len(sizes))
    imbalance_component = min(35.0, abs(buy_sell_ratio - 1.0) * 18.0)
    concentration_component = min(30.0, largest_share * 120.0)
    volume_component = min(20.0, volume / 25_000.0)
    repetition_component = min(15.0, repetition_ratio * 45.0)
    score = min(100.0, imbalance_component + concentration_component + volume_component + repetition_component)
    return {
        "aster_score": round(score, 2),
        "window_volume_usd": round(volume, 6),
        "window_buy_count": buys,
        "window_sell_count": sells,
        "buy_sell_ratio": round(buy_sell_ratio, 6),
        "largest_trade_share": round(largest_share, 6),
        "repetition_ratio": round(repetition_ratio, 6),
    }


def _replay_row(
    run_id: str,
    symbol: str,
    state: str,
    reason: str,
    score: dict[str, Any],
    price: float,
    size_usd: float,
    fees_usd: float,
    slippage_usd: float,
    pnl_unrealized: float,
    pnl_realized: float,
    max_drawdown: float,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": _now(),
        "symbol": symbol,
        "token_address": None,
        "event_type": "historical_replay",
        "state": state,
        "decision_reason": reason,
        "aster_score": _as_float(score.get("aster_score")),
        "behavioral_score": None,
        "entry_price": price if state == "executing_entry" else None,
        "current_price": price or None,
        "size_usd": round(size_usd, 6),
        "fees_usd": round(fees_usd, 6),
        "slippage_usd": round(slippage_usd, 6),
        "pnl_unrealized_usd": round(pnl_unrealized, 6),
        "pnl_realized_usd": round(pnl_realized, 6),
        "max_drawdown_usd": round(max_drawdown, 6),
        "raw_payload_json": json.dumps({**payload, "score_proxy": score}, sort_keys=True),
    }


def _replay_trades(
    trades: list[dict[str, Any]],
    run_id: str,
    symbol: str,
    wallet_balance_usd: float,
    fee_bps: float,
    slippage_bps: float,
    window_size: int,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 50_000.0,
    behavioral_score: float | None = None,
    min_behavioral_score: float | None = None,
    stop_loss_pct: float = -25.0,
    take_profit_pct: float = 15.0,
    trailing_stop_activation_pct: float = 10.0,
    trailing_stop_distance_pct: float = 5.0,
    max_holding_trades: int = 200,
    max_holding_seconds: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    balance = max(0.0, _as_float(wallet_balance_usd))
    peak_equity = balance
    max_drawdown = 0.0
    position: dict[str, Any] | None = None
    closed_pnls: list[float] = []
    safe_window = max(5, min(_as_int(window_size, 20), 100))
    for idx, trade in enumerate(trades):
        price = _trade_price(trade)
        if price <= 0:
            continue
        window = trades[max(0, idx - safe_window + 1) : idx + 1]
        score = _aster_score_proxy(window)
        volume_proxy = score.get("window_volume_usd", 0.0)
        payload = {
            "trade_index": idx,
            "trade_id": trade.get("id"),
            "trade_time": trade.get("time"),
            "source": "aster_recent_trades",
            "behavioral_score": behavioral_score,
            "min_behavioral_score": min_behavioral_score,
        }
        if position:
            entry = _as_float(position.get("entry_price"))
            size = _as_float(position.get("size_usd"))
            peak_price = max(_as_float(position.get("peak_price")), price)
            position["peak_price"] = peak_price
            pnl_unrealized = ((price - entry) / entry * size) if entry > 0 else 0.0
            equity = balance + pnl_unrealized
            peak_equity = max(peak_equity, equity)
            max_drawdown = max(max_drawdown, peak_equity - equity)
            should_exit, exit_reason = should_exit_position(entry, price, stop_loss_pct, take_profit_pct)
            trailing_activation = 1 + (_as_float(trailing_stop_activation_pct) / 100)
            trailing_distance = 1 - (max(0.0, _as_float(trailing_stop_distance_pct)) / 100)
            trailing_active = entry > 0 and peak_price / entry >= trailing_activation
            if not should_exit and trailing_active and price <= peak_price * trailing_distance:
                should_exit = True
                exit_reason = "trailing_stop_triggered"
            entry_index = _as_int(position.get("entry_trade_index"))
            trades_held = idx - entry_index
            entry_time = position.get("entry_timestamp")
            current_time = _trade_time_seconds(trade.get("time"))
            seconds_held = None
            if entry_time is not None and current_time is not None:
                seconds_held = max(0.0, current_time - _as_float(entry_time))
            time_stop_by_trades = _as_int(max_holding_trades, 0) > 0 and trades_held >= _as_int(max_holding_trades)
            time_stop_by_seconds = max_holding_seconds is not None and seconds_held is not None and seconds_held >= _as_float(max_holding_seconds)
            if not should_exit and (time_stop_by_trades or time_stop_by_seconds):
                should_exit = True
                exit_reason = "time_stop_triggered"
            if should_exit:
                fees = size * fee_bps / 10_000
                slippage = size * slippage_bps / 10_000
                pnl_realized = pnl_unrealized - fees - slippage
                balance += pnl_realized
                closed_pnls.append(pnl_realized)
                rows.append(_replay_row(run_id, symbol, "executing_exit", exit_reason, score, price, size, fees, slippage, 0.0, pnl_realized, max_drawdown, {**payload, "action": "exit", "peak_price": peak_price, "trailing_active": trailing_active, "trades_held": trades_held, "seconds_held": seconds_held}))
                position = None
            else:
                rows.append(_replay_row(run_id, symbol, "monitoring", "mark_to_market_holding", score, price, size, 0.0, 0.0, pnl_unrealized, 0.0, max_drawdown, {**payload, "action": "mark_to_market", "peak_price": peak_price, "trailing_active": trailing_active, "trades_held": trades_held, "seconds_held": seconds_held}))
            continue
        behavioral_gate_failed = (
            min_behavioral_score is not None
            and (behavioral_score is None or _as_float(behavioral_score) < _as_float(min_behavioral_score))
        )
        enter = False if behavioral_gate_failed else should_enter_position(
            _as_float(score.get("aster_score")),
            None,
            _as_float(volume_proxy),
            min_aster_score=min_aster_score,
            min_volume_usd=min_window_volume_usd,
        )
        if enter:
            size = calculate_position_size(balance, 5.0, _as_float(score.get("aster_score")))
            fees = size * fee_bps / 10_000
            slippage = size * slippage_bps / 10_000
            balance -= fees + slippage
            position = {
                "entry_price": price,
                "size_usd": size,
                "peak_price": price,
                "entry_trade_index": idx,
                "entry_timestamp": _trade_time_seconds(trade.get("time")),
            }
            rows.append(_replay_row(run_id, symbol, "executing_entry", "entry_rules_passed", score, price, size, fees, slippage, -fees - slippage, 0.0, max_drawdown, {**payload, "action": "entry", "peak_price": price, "trailing_active": False}))
        else:
            rejection_reason = "behavioral_score_below_threshold" if behavioral_gate_failed else "entry_rules_not_met"
            rows.append(_replay_row(run_id, symbol, "deciding", rejection_reason, score, price, 0.0, 0.0, 0.0, 0.0, 0.0, max_drawdown, {**payload, "action": "decision_rejected"}))
    if position and trades:
        price = _trade_price(trades[-1])
        entry = _as_float(position.get("entry_price"))
        size = _as_float(position.get("size_usd"))
        pnl_unrealized = ((price - entry) / entry * size) if entry > 0 else 0.0
    else:
        pnl_unrealized = 0.0
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    entries = sum(1 for row in rows if json.loads(row["raw_payload_json"]).get("action") == "entry")
    realized_pnl = balance - max(0.0, _as_float(wallet_balance_usd))
    report = {
        "simulated_trade_count": entries,
        "closed_trade_count": len(closed_pnls),
        "win_rate": round(wins / len(closed_pnls), 6) if closed_pnls else None,
        "pnl_total_usd": round(realized_pnl, 6),
        "pnl_realized_usd": round(realized_pnl, 6),
        "open_unrealized_pnl_usd": round(pnl_unrealized, 6),
        "pnl_total_including_unrealized_usd": round(realized_pnl + pnl_unrealized, 6),
        "max_drawdown_usd": round(max_drawdown, 6),
        "final_balance_usd": round(balance, 6),
        "final_balance_including_unrealized_usd": round(balance + pnl_unrealized, 6),
    }
    return rows, report


def _replay_trades_short(
    trades: list[dict[str, Any]],
    run_id: str,
    symbol: str,
    wallet_balance_usd: float,
    fee_bps: float,
    slippage_bps: float,
    window_size: int,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 1_000.0,
    stop_loss_pct: float = 15.0,
    take_profit_pct: float = -25.0,
    trailing_stop_activation_pct: float = 10.0,
    trailing_stop_distance_pct: float = 5.0,
    max_holding_trades: int = 200,
    max_holding_seconds: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    balance = max(0.0, _as_float(wallet_balance_usd))
    initial_balance = balance
    peak_equity = balance
    max_drawdown = 0.0
    position: dict[str, Any] | None = None
    closed_pnls: list[float] = []
    safe_window = max(5, min(_as_int(window_size, 20), 100))
    for idx, trade in enumerate(trades):
        price = _trade_price(trade)
        if price <= 0:
            continue
        window = trades[max(0, idx - safe_window + 1) : idx + 1]
        score = _aster_score_proxy(window)
        volume_proxy = _as_float(score.get("window_volume_usd"))
        payload = {
            "trade_index": idx,
            "trade_id": trade.get("id"),
            "trade_time": trade.get("time"),
            "source": "aster_recent_trades",
            "side": "short",
        }
        if position:
            entry = _as_float(position.get("entry_price"))
            size = _as_float(position.get("size_usd"))
            trough_price = min(_as_float(position.get("trough_price")), price)
            position["trough_price"] = trough_price
            pnl_unrealized = ((entry - price) / entry * size) if entry > 0 else 0.0
            equity = balance + pnl_unrealized
            peak_equity = max(peak_equity, equity)
            max_drawdown = max(max_drawdown, peak_equity - equity)

            stop_price = entry * (1 + max(0.0, _as_float(stop_loss_pct)) / 100) if entry > 0 else 0.0
            take_profit_price = entry * (1 + min(0.0, _as_float(take_profit_pct)) / 100) if entry > 0 else 0.0
            should_exit = False
            exit_reason = "holding_short"
            if entry > 0 and price >= stop_price:
                should_exit = True
                exit_reason = "short_stop_loss_triggered"
            elif entry > 0 and price <= take_profit_price:
                should_exit = True
                exit_reason = "short_take_profit_triggered"

            activation_price = entry * (1 - max(0.0, _as_float(trailing_stop_activation_pct)) / 100) if entry > 0 else 0.0
            trailing_active = entry > 0 and trough_price <= activation_price
            trailing_exit_price = trough_price * (1 + max(0.0, _as_float(trailing_stop_distance_pct)) / 100)
            if not should_exit and trailing_active and price >= trailing_exit_price:
                should_exit = True
                exit_reason = "short_trailing_stop_triggered"
            entry_index = _as_int(position.get("entry_trade_index"))
            trades_held = idx - entry_index
            entry_time = position.get("entry_timestamp")
            current_time = _trade_time_seconds(trade.get("time"))
            seconds_held = None
            if entry_time is not None and current_time is not None:
                seconds_held = max(0.0, current_time - _as_float(entry_time))
            time_stop_by_trades = _as_int(max_holding_trades, 0) > 0 and trades_held >= _as_int(max_holding_trades)
            time_stop_by_seconds = max_holding_seconds is not None and seconds_held is not None and seconds_held >= _as_float(max_holding_seconds)
            if not should_exit and (time_stop_by_trades or time_stop_by_seconds):
                should_exit = True
                exit_reason = "time_stop_triggered"

            if should_exit:
                fees = size * fee_bps / 10_000
                slippage = size * slippage_bps / 10_000
                pnl_realized = pnl_unrealized - fees - slippage
                balance += pnl_realized
                closed_pnls.append(pnl_realized)
                rows.append(
                    _replay_row(
                        run_id,
                        symbol,
                        "executing_exit",
                        exit_reason,
                        score,
                        price,
                        size,
                        fees,
                        slippage,
                        0.0,
                        pnl_realized,
                        max_drawdown,
                        {
                            **payload,
                            "action": "exit",
                            "entry_price": entry,
                            "trough_price": trough_price,
                            "trailing_active": trailing_active,
                            "trailing_exit_price": trailing_exit_price,
                            "trades_held": trades_held,
                            "seconds_held": seconds_held,
                        },
                    )
                )
                position = None
            else:
                rows.append(
                    _replay_row(
                        run_id,
                        symbol,
                        "monitoring",
                        "mark_to_market_short_holding",
                        score,
                        price,
                        size,
                        0.0,
                        0.0,
                        pnl_unrealized,
                        0.0,
                        max_drawdown,
                        {
                            **payload,
                            "action": "mark_to_market",
                            "entry_price": entry,
                            "trough_price": trough_price,
                            "trailing_active": trailing_active,
                            "trailing_exit_price": trailing_exit_price,
                            "trades_held": trades_held,
                            "seconds_held": seconds_held,
                        },
                    )
                )
            continue

        enter = _as_float(score.get("aster_score")) >= _as_float(min_aster_score) and volume_proxy >= _as_float(min_window_volume_usd)
        if enter:
            size = calculate_position_size(balance, 5.0, _as_float(score.get("aster_score")))
            fees = size * fee_bps / 10_000
            slippage = size * slippage_bps / 10_000
            balance -= fees + slippage
            position = {
                "entry_price": price,
                "size_usd": size,
                "trough_price": price,
                "entry_trade_index": idx,
                "entry_timestamp": _trade_time_seconds(trade.get("time")),
            }
            rows.append(
                _replay_row(
                    run_id,
                    symbol,
                    "executing_entry",
                    "short_entry_rules_passed",
                    score,
                    price,
                    size,
                    fees,
                    slippage,
                    -fees - slippage,
                    0.0,
                    max_drawdown,
                    {**payload, "action": "entry", "entry_price": price, "trough_price": price, "trailing_active": False},
                )
            )
        else:
            rows.append(
                _replay_row(
                    run_id,
                    symbol,
                    "deciding",
                    "short_entry_rules_not_met",
                    score,
                    price,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    max_drawdown,
                    {**payload, "action": "decision_rejected"},
                )
            )
    if position and trades:
        price = _trade_price(trades[-1])
        entry = _as_float(position.get("entry_price"))
        size = _as_float(position.get("size_usd"))
        pnl_unrealized = ((entry - price) / entry * size) if entry > 0 else 0.0
    else:
        pnl_unrealized = 0.0
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    entries = sum(1 for row in rows if json.loads(row["raw_payload_json"]).get("action") == "entry")
    realized_pnl = balance - initial_balance
    report = {
        "simulated_trade_count": entries,
        "closed_trade_count": len(closed_pnls),
        "win_rate": round(wins / len(closed_pnls), 6) if closed_pnls else None,
        "pnl_total_usd": round(realized_pnl, 6),
        "pnl_realized_usd": round(realized_pnl, 6),
        "open_unrealized_pnl_usd": round(pnl_unrealized, 6),
        "pnl_total_including_unrealized_usd": round(realized_pnl + pnl_unrealized, 6),
        "max_drawdown_usd": round(max_drawdown, 6),
        "final_balance_usd": round(balance, 6),
        "final_balance_including_unrealized_usd": round(balance + pnl_unrealized, 6),
    }
    return rows, report


def _short_replay_trade_diagnostics(rows: list[dict[str, Any]], initial_balance_usd: float) -> dict[str, Any]:
    closed: list[dict[str, Any]] = []
    losing: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    equity = _as_float(initial_balance_usd)
    for row in rows:
        try:
            payload = json.loads(row.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        action = payload.get("action")
        trade_time = _trade_time_seconds(payload.get("trade_time"))
        price = _as_float(row.get("current_price"))
        if action == "entry":
            current = {
                "symbol": row.get("symbol"),
                "entry_price": _as_float(row.get("entry_price") or row.get("current_price")),
                "entry_score": _as_float(row.get("aster_score")),
                "entry_time": trade_time,
                "entry_index": _as_int(payload.get("trade_index")),
                "prices": [price] if price > 0 else [],
                "unrealized": [_as_float(row.get("pnl_unrealized_usd"))],
            }
        elif current and action == "mark_to_market":
            if price > 0:
                current["prices"].append(price)
            current["unrealized"].append(_as_float(row.get("pnl_unrealized_usd")))
        elif current and action == "exit":
            if price > 0:
                current["prices"].append(price)
            exit_unrealized = _as_float(row.get("pnl_realized_usd")) + _as_float(row.get("fees_usd")) + _as_float(row.get("slippage_usd"))
            current["unrealized"].append(exit_unrealized)
            pnl = _as_float(row.get("pnl_realized_usd"))
            prices = current.get("prices") or []
            entry_price = _as_float(current.get("entry_price"))
            min_price = min(prices) if prices else price
            max_price = max(prices) if prices else price
            unrealized_path = current.get("unrealized") or [0.0]
            min_unrealized = min(unrealized_path)
            size = _as_float(row.get("size_usd"))
            mfe_pct = ((entry_price - min_price) / entry_price * 100) if entry_price > 0 else None
            mfe_usd = ((entry_price - min_price) / entry_price * size) if entry_price > 0 else None
            mae_pct = ((max_price - entry_price) / entry_price * 100) if entry_price > 0 else None
            duration = None
            if current.get("entry_time") is not None and trade_time is not None:
                duration = max(0.0, trade_time - _as_float(current.get("entry_time")))
            entry_index = _as_int(current.get("entry_index"))
            exit_index = _as_int(payload.get("trade_index"))
            trades_to_exit = max(0, exit_index - entry_index)
            immediate_adverse = bool(len(prices) > 1 and prices[1] > entry_price)
            equity += pnl
            detail = {
                "symbol": current.get("symbol"),
                "exit_reason": row.get("decision_reason"),
                "entry_score": round(_as_float(current.get("entry_score")), 6),
                "pnl_realized_usd": round(pnl, 6),
                "max_adverse_excursion_usd": round(min_unrealized, 6),
                "max_adverse_excursion_pct": round(_as_float(mae_pct), 6) if mae_pct is not None else None,
                "mfe_usd": round(_as_float(mfe_usd), 6) if mfe_usd is not None else None,
                "mfe_pct": round(_as_float(mfe_pct), 6) if mfe_pct is not None else None,
                "immediate_adverse_after_entry": immediate_adverse,
                "trades_to_exit": trades_to_exit,
                "time_in_position_seconds": round(duration, 3) if duration is not None else None,
                "price_action_during_position": {
                    "entry": round(entry_price, 12),
                    "exit": round(price, 12),
                    "min": round(min_price, 12),
                    "max": round(max_price, 12),
                    "volatility_pct": round(((max_price - min_price) / entry_price * 100), 6) if entry_price > 0 else None,
                },
            }
            closed.append(detail)
            equity_curve.append({"symbol": current.get("symbol"), "exit_index": exit_index, "equity_usd": round(equity, 6)})
            if pnl < 0:
                losing.append(detail)
            current = None
    wins = [row for row in closed if _as_float(row.get("pnl_realized_usd")) > 0]
    losses = [row for row in closed if _as_float(row.get("pnl_realized_usd")) < 0]
    gross_profit = sum(_as_float(row.get("pnl_realized_usd")) for row in wins)
    gross_loss = abs(sum(_as_float(row.get("pnl_realized_usd")) for row in losses))
    durations = [_as_float(row.get("time_in_position_seconds")) for row in closed if row.get("time_in_position_seconds") is not None]
    stop_losses = [row for row in closed if row.get("exit_reason") == "short_stop_loss_triggered"]
    immediate_adverse = [row for row in closed if row.get("immediate_adverse_after_entry")]
    return {
        "closed_trades": closed,
        "losing_trades": losing,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed), 6) if closed else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "avg_trade_duration": round(sum(durations) / len(durations), 3) if durations else None,
        "stop_loss_hit_rate": round(len(stop_losses) / len(closed), 6) if closed else None,
        "immediate_adverse_ratio": round(len(immediate_adverse) / len(closed), 6) if closed else None,
        "short_equity_curve": equity_curve,
    }


def _short_open_positions_detail(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current: dict[str, Any] | None = None
    for row in rows:
        try:
            payload = json.loads(row.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        action = payload.get("action")
        price = _as_float(row.get("current_price"))
        if action == "entry":
            current = {
                "symbol": row.get("symbol"),
                "entry_price": _as_float(row.get("entry_price") or row.get("current_price")),
                "last_price": price,
                "size_usd": _as_float(row.get("size_usd")),
                "entry_score": _as_float(row.get("aster_score")),
                "entry_index": _as_int(payload.get("trade_index")),
                "last_index": _as_int(payload.get("trade_index")),
                "trough_price": _as_float(payload.get("trough_price") or price),
                "trailing_active": bool(payload.get("trailing_active")),
                "pnl_unrealized_usd": _as_float(row.get("pnl_unrealized_usd")),
            }
        elif current and action == "mark_to_market":
            entry = _as_float(current.get("entry_price"))
            size = _as_float(current.get("size_usd"))
            trough_price = min(_as_float(current.get("trough_price") or entry), _as_float(payload.get("trough_price") or price or entry))
            pnl_unrealized = _as_float(row.get("pnl_unrealized_usd"))
            current.update(
                {
                    "last_price": price,
                    "last_index": _as_int(payload.get("trade_index")),
                    "trough_price": trough_price,
                    "trailing_active": bool(payload.get("trailing_active")),
                    "pnl_unrealized_usd": pnl_unrealized,
                    "pnl_unrealized_pct": round((pnl_unrealized / size * 100), 6) if size > 0 else None,
                }
            )
        elif current and action == "exit":
            current = None
    if not current:
        return []
    entry = _as_float(current.get("entry_price"))
    last_price = _as_float(current.get("last_price"))
    size = _as_float(current.get("size_usd"))
    if "pnl_unrealized_pct" not in current:
        pnl = ((entry - last_price) / entry * size) if entry > 0 else 0.0
        current["pnl_unrealized_usd"] = round(pnl, 6)
        current["pnl_unrealized_pct"] = round((pnl / size * 100), 6) if size > 0 else None
    current["entry_price"] = round(entry, 12)
    current["last_price"] = round(last_price, 12)
    current["size_usd"] = round(size, 6)
    current["entry_score"] = round(_as_float(current.get("entry_score")), 6)
    current["trough_price"] = round(_as_float(current.get("trough_price")), 12)
    current["trades_open"] = max(0, _as_int(current.get("last_index")) - _as_int(current.get("entry_index")))
    current["pnl_unrealized_usd"] = round(_as_float(current.get("pnl_unrealized_usd")), 6)
    return [current]


def _short_cinematic_verdict(closed_trades: list[dict[str, Any]], diag: dict[str, Any]) -> str:
    if not closed_trades:
        return "insufficient_closed_trades"
    win_rate = _as_float(diag.get("win_rate"))
    stop_loss_hit_rate = _as_float(diag.get("stop_loss_hit_rate"))
    immediate_adverse_ratio = _as_float(diag.get("immediate_adverse_ratio"))
    if win_rate >= 0.55:
        return "short_fade_validated"
    if immediate_adverse_ratio >= 0.60 and stop_loss_hit_rate >= 0.50:
        return "short_squeeze_risk"
    if stop_loss_hit_rate >= 0.60:
        return "short_fade_invalidated"
    return "mixed_or_insufficient_short_pattern"


def get_aster_paper_trading_60d_kline_replay_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    lookback_days: int = 60,
    interval: str = "1h",
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    disabled = _disabled()
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "replay_status": "blocked",
            "blockers": ["dry_run_required_kline_replay_is_read_only"],
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    default_symbols = ["TIAUSDT", "SEIUSDT", "JUPUSDT", "WLDUSDT", *SELECTED_SHORT_FADE_FORWARD_SYMBOLS]
    clean_symbols = list(dict.fromkeys(_parse_symbols(symbols, default_symbols)))[:12]
    safe_days = max(1, min(_as_int(lookback_days, 60), 60))
    safe_interval = str(interval or "1h").strip()
    interval_ms = _KLINE_INTERVAL_MS.get(safe_interval)
    if not interval_ms:
        return {
            "ok": False,
            "dry_run": True,
            "replay_status": "blocked",
            "blockers": ["unsupported_interval"],
            "supported_intervals": sorted(_KLINE_INTERVAL_MS),
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    expected_candles = int((safe_days * 86_400_000) / interval_ms)
    if expected_candles > 15_000:
        return {
            "ok": False,
            "dry_run": True,
            "replay_status": "blocked",
            "blockers": ["interval_too_granular_for_preview"],
            "expected_candles_per_symbol": expected_candles,
            "recommendation": "use_interval_15m_or_higher_for_60d_preview",
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    safe_timeout = max(1, min(_as_int(timeout_seconds, 15), 15))
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - safe_days * 86_400_000
    max_pages = max(1, min(20, (expected_candles // 1500) + 2))
    results: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    totals = {
        "long_entries": 0,
        "long_closed": 0,
        "long_wins": 0,
        "long_pnl": 0.0,
        "long_gross_profit": 0.0,
        "long_gross_loss": 0.0,
        "short_entries": 0,
        "short_closed": 0,
        "short_wins": 0,
        "short_pnl": 0.0,
        "short_gross_profit": 0.0,
        "short_gross_loss": 0.0,
        "short_max_dd": 0.0,
        "long_max_dd": 0.0,
    }

    for index, symbol in enumerate(clean_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        fetched = _fetch_klines_with_spot_fallback(symbol, safe_interval, start_ms, end_ms, safe_timeout, max_pages=max_pages)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        klines = fetched.get("klines") or []
        trades = [_kline_to_proxy_trade(row, symbol, idx) for idx, row in enumerate(klines)]
        if len(trades) < max(50, window_size * 3):
            failed_symbols.append({"symbol": symbol, "fetch_status": "insufficient_kline_history", "kline_count": len(trades)})
            continue

        long_rows, long_report = _replay_trades(
            trades,
            f"kline-60d-long-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=75.0,
            min_window_volume_usd=5_000.0,
            stop_loss_pct=-6.0,
            take_profit_pct=10.0,
            trailing_stop_activation_pct=6.0,
            trailing_stop_distance_pct=3.0,
            max_holding_trades=600,
        )
        short_rows, short_report = _replay_trades_short(
            trades,
            f"kline-60d-short-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=70.0,
            min_window_volume_usd=1_000.0,
            stop_loss_pct=8.0,
            take_profit_pct=-6.0,
            trailing_stop_activation_pct=4.0,
            trailing_stop_distance_pct=2.0,
            max_holding_trades=600,
        )
        long_diag = _replay_trade_diagnostics(long_rows)
        short_diag = _short_replay_trade_diagnostics(short_rows, wallet_balance_usd)
        long_closed = long_diag.get("closed_trades") or []
        short_closed = short_diag.get("closed_trades") or []
        long_wins = [row for row in long_closed if _as_float(row.get("pnl_realized_usd")) > 0]
        long_losses = [row for row in long_closed if _as_float(row.get("pnl_realized_usd")) < 0]
        short_wins = [row for row in short_closed if _as_float(row.get("pnl_realized_usd")) > 0]
        short_losses = [row for row in short_closed if _as_float(row.get("pnl_realized_usd")) < 0]
        long_gross_profit = sum(_as_float(row.get("pnl_realized_usd")) for row in long_wins)
        long_gross_loss = abs(sum(_as_float(row.get("pnl_realized_usd")) for row in long_losses))
        short_gross_profit = sum(_as_float(row.get("pnl_realized_usd")) for row in short_wins)
        short_gross_loss = abs(sum(_as_float(row.get("pnl_realized_usd")) for row in short_losses))
        totals["long_entries"] += _as_int(long_report.get("simulated_trade_count"))
        totals["long_closed"] += len(long_closed)
        totals["long_wins"] += len(long_wins)
        totals["long_pnl"] += _as_float(long_report.get("pnl_total_usd"))
        totals["long_gross_profit"] += long_gross_profit
        totals["long_gross_loss"] += long_gross_loss
        totals["long_max_dd"] = max(totals["long_max_dd"], _as_float(long_report.get("max_drawdown_usd")))
        totals["short_entries"] += _as_int(short_report.get("simulated_trade_count"))
        totals["short_closed"] += len(short_closed)
        totals["short_wins"] += len(short_wins)
        totals["short_pnl"] += _as_float(short_report.get("pnl_total_usd"))
        totals["short_gross_profit"] += short_gross_profit
        totals["short_gross_loss"] += short_gross_loss
        totals["short_max_dd"] = max(totals["short_max_dd"], _as_float(short_report.get("max_drawdown_usd")))
        times = [_trade_time_seconds(row.get("time")) for row in trades]
        times = [ts for ts in times if ts is not None]
        results[symbol] = {
            "market_type": fetched.get("market_type"),
            "interval": safe_interval,
            "klines": len(klines),
            "coverage_start": datetime.fromtimestamp(min(times), timezone.utc).isoformat() if times else None,
            "coverage_end": datetime.fromtimestamp(max(times), timezone.utc).isoformat() if times else None,
            "coverage_days": round((max(times) - min(times)) / 86_400, 3) if len(times) >= 2 else None,
            "long_high_volume_breakout_75": {
                "entries": long_report.get("simulated_trade_count"),
                "closed_trades": len(long_closed),
                "win_rate": round(len(long_wins) / len(long_closed), 6) if long_closed else None,
                "profit_factor": round(long_gross_profit / long_gross_loss, 6) if long_gross_loss else None,
                "pnl_total_usd": long_report.get("pnl_total_usd"),
                "max_drawdown_usd": long_report.get("max_drawdown_usd"),
                "avg_mfe_pct": long_diag.get("avg_mfe_pct"),
            },
            "short_fade_optimized": {
                "entries": short_report.get("simulated_trade_count"),
                "closed_trades": len(short_closed),
                "win_rate": short_diag.get("win_rate"),
                "profit_factor": short_diag.get("profit_factor"),
                "pnl_total_usd": short_report.get("pnl_total_usd"),
                "max_drawdown_usd": short_report.get("max_drawdown_usd"),
                "stop_loss_hit_rate": short_diag.get("stop_loss_hit_rate"),
            },
        }

    long_wr = round(totals["long_wins"] / totals["long_closed"], 6) if totals["long_closed"] else None
    short_wr = round(totals["short_wins"] / totals["short_closed"], 6) if totals["short_closed"] else None
    long_pf = round(totals["long_gross_profit"] / totals["long_gross_loss"], 6) if totals["long_gross_loss"] else None
    short_pf = round(totals["short_gross_profit"] / totals["short_gross_loss"], 6) if totals["short_gross_loss"] else None
    return {
        "ok": True,
        "dry_run": True,
        "replay_status": "ready",
        "methodology": "60d_kline_proxy_replay_not_tick_level_trade_replay",
        "lookback_days_requested": safe_days,
        "interval": safe_interval,
        "symbols": clean_symbols,
        "long_params": {"min_aster_score": 75.0, "min_window_volume_usd": 5_000.0, "stop_loss_pct": -6.0, "take_profit_pct": 10.0, "trailing": "6pct_activation_3pct_distance"},
        "short_params": {"min_aster_score": 70.0, "min_window_volume_usd": 1_000.0, "stop_loss_pct": 8.0, "take_profit_pct": -6.0, "trailing": "4pct_activation_2pct_distance"},
        "results_by_symbol": results,
        "global_report": {
            "long": {
                "entries": totals["long_entries"],
                "closed_trades": totals["long_closed"],
                "win_rate": long_wr,
                "profit_factor": long_pf,
                "pnl_total_usd": round(totals["long_pnl"], 6),
                "max_drawdown_usd": round(totals["long_max_dd"], 6),
            },
            "short": {
                "entries": totals["short_entries"],
                "closed_trades": totals["short_closed"],
                "win_rate": short_wr,
                "profit_factor": short_pf,
                "pnl_total_usd": round(totals["short_pnl"], 6),
                "max_drawdown_usd": round(totals["short_max_dd"], 6),
            },
            "delta_short_vs_long_pnl_usd": round(totals["short_pnl"] - totals["long_pnl"], 6),
        },
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_multi_timeframe_replay_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    lookback_days: int = 60,
    intervals: str | list[str] | None = None,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    disabled = _disabled()
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "replay_status": "blocked",
            "blockers": ["dry_run_required_multi_timeframe_replay_is_read_only"],
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    clean_symbols = _parse_symbols(symbols, ["TIAUSDT", "JUPUSDT", "ARBUSDT", "1000SATSUSDT", "ORDIUSDT", "WLDUSDT"])[:8]
    if isinstance(intervals, (list, tuple)):
        clean_intervals = [str(item or "").strip() for item in intervals if str(item or "").strip()]
    else:
        clean_intervals = [item.strip() for item in str(intervals or "1h,30m,15m,5m").replace(";", ",").split(",") if item.strip()]
    clean_intervals = [item for item in clean_intervals if item in _KLINE_INTERVAL_MS][:8] or ["1h", "30m", "15m", "5m"]
    results_by_timeframe: dict[str, Any] = {}
    symbol_matrix: dict[str, dict[str, Any]] = {symbol: {} for symbol in clean_symbols}
    failed_timeframes: list[dict[str, Any]] = []

    for interval in clean_intervals:
        result = get_aster_paper_trading_60d_kline_replay_preview(
            symbols=clean_symbols,
            dry_run=True,
            lookback_days=lookback_days,
            interval=interval,
            timeout_seconds=timeout_seconds,
            wallet_balance_usd=wallet_balance_usd,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            window_size=window_size,
            rate_limit_delay_ms=rate_limit_delay_ms,
        )
        if not result.get("ok"):
            failed_timeframes.append({"interval": interval, "status": result.get("replay_status"), "blockers": result.get("blockers")})
            continue
        results_by_timeframe[interval] = {
            "global_report": result.get("global_report"),
            "failed_symbols": result.get("failed_symbols"),
        }
        for symbol, row in (result.get("results_by_symbol") or {}).items():
            symbol_matrix.setdefault(symbol, {})[interval] = {
                "coverage_days": row.get("coverage_days"),
                "klines": row.get("klines"),
                "long_pnl_usd": (row.get("long_high_volume_breakout_75") or {}).get("pnl_total_usd"),
                "long_win_rate": (row.get("long_high_volume_breakout_75") or {}).get("win_rate"),
                "long_profit_factor": (row.get("long_high_volume_breakout_75") or {}).get("profit_factor"),
                "long_closed_trades": (row.get("long_high_volume_breakout_75") or {}).get("closed_trades"),
                "short_pnl_usd": (row.get("short_fade_optimized") or {}).get("pnl_total_usd"),
                "short_win_rate": (row.get("short_fade_optimized") or {}).get("win_rate"),
                "short_profit_factor": (row.get("short_fade_optimized") or {}).get("profit_factor"),
                "short_closed_trades": (row.get("short_fade_optimized") or {}).get("closed_trades"),
            }

    recommendations: list[dict[str, Any]] = []
    for symbol, matrix in symbol_matrix.items():
        long_rows = [row for row in matrix.values() if row.get("long_pnl_usd") is not None]
        short_rows = [row for row in matrix.values() if row.get("short_pnl_usd") is not None]
        long_positive = [row for row in long_rows if _as_float(row.get("long_pnl_usd")) > 0]
        short_positive = [row for row in short_rows if _as_float(row.get("short_pnl_usd")) > 0]
        long_score = sum(_as_float(row.get("long_pnl_usd")) for row in long_rows)
        short_score = sum(_as_float(row.get("short_pnl_usd")) for row in short_rows)
        best_side = "long" if long_score >= short_score else "short"
        positive_rows = long_positive if best_side == "long" else short_positive
        robust_count = len(positive_rows)
        recommendations.append(
            {
                "symbol": symbol,
                "recommended_side": best_side,
                "positive_timeframes": robust_count,
                "long_total_pnl_usd": round(long_score, 6),
                "short_total_pnl_usd": round(short_score, 6),
                "robustness_status": "robust" if robust_count >= 3 else "promising" if robust_count >= 2 else "weak",
            }
        )
    recommendations.sort(
        key=lambda row: (
            row.get("robustness_status") == "robust",
            row.get("positive_timeframes") or 0,
            max(_as_float(row.get("long_total_pnl_usd")), _as_float(row.get("short_total_pnl_usd"))),
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "dry_run": True,
        "replay_status": "ready",
        "methodology": "multi_timeframe_60d_kline_proxy_replay",
        "symbols": clean_symbols,
        "intervals": clean_intervals,
        "results_by_timeframe": results_by_timeframe,
        "symbol_matrix": symbol_matrix,
        "recommendations": recommendations,
        "failed_timeframes": failed_timeframes,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def _focused_walkforward_lanes() -> list[dict[str, Any]]:
    return [
        {
            "lane_id": "tia_long_strict_breakout",
            "symbol": "TIAUSDT",
            "side": "long",
            "min_aster_score": 80.0,
            "min_window_volume_usd": 5_000.0,
            "stop_loss_pct": -6.0,
            "take_profit_pct": 12.0,
            "trailing_stop_activation_pct": 6.0,
            "trailing_stop_distance_pct": 3.0,
            "max_holding_trades": 600,
        },
        {
            "lane_id": "inj_long_strict_breakout",
            "symbol": "INJUSDT",
            "side": "long",
            "min_aster_score": 80.0,
            "min_window_volume_usd": 5_000.0,
            "stop_loss_pct": -6.0,
            "take_profit_pct": 12.0,
            "trailing_stop_activation_pct": 6.0,
            "trailing_stop_distance_pct": 3.0,
            "max_holding_trades": 600,
        },
        {
            "lane_id": "inj_long_frequent_breakout",
            "symbol": "INJUSDT",
            "side": "long",
            "min_aster_score": 70.0,
            "min_window_volume_usd": 5_000.0,
            "stop_loss_pct": -3.0,
            "take_profit_pct": 6.0,
            "trailing_stop_activation_pct": 3.0,
            "trailing_stop_distance_pct": 1.5,
            "max_holding_trades": 600,
        },
        {
            "lane_id": "near_long_balanced_breakout",
            "symbol": "NEARUSDT",
            "side": "long",
            "min_aster_score": 75.0,
            "min_window_volume_usd": 5_000.0,
            "stop_loss_pct": -4.0,
            "take_profit_pct": 8.0,
            "trailing_stop_activation_pct": 4.0,
            "trailing_stop_distance_pct": 2.0,
            "max_holding_trades": 600,
        },
        {
            "lane_id": "bome_long_strict_breakout",
            "symbol": "BOMEUSDT",
            "side": "long",
            "min_aster_score": 80.0,
            "min_window_volume_usd": 5_000.0,
            "stop_loss_pct": -6.0,
            "take_profit_pct": 12.0,
            "trailing_stop_activation_pct": 6.0,
            "trailing_stop_distance_pct": 3.0,
            "max_holding_trades": 600,
        },
        {
            "lane_id": "sats_short_fade_control",
            "symbol": "1000SATSUSDT",
            "side": "short",
            "min_aster_score": 70.0,
            "min_window_volume_usd": 1_000.0,
            "stop_loss_pct": 8.0,
            "take_profit_pct": -6.0,
            "trailing_stop_activation_pct": 4.0,
            "trailing_stop_distance_pct": 2.0,
            "max_holding_trades": 600,
        },
    ]


def _closed_trade_stats(rows: list[dict[str, Any]], report: dict[str, Any], wallet_balance_usd: float) -> dict[str, Any]:
    closed = [row for row in rows if _as_float(row.get("pnl_realized_usd")) != 0]
    entries = []
    for row in rows:
        try:
            payload = json.loads(row.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict) and payload.get("action") == "entry":
            entries.append(row)
    wins = [row for row in closed if _as_float(row.get("pnl_realized_usd")) > 0]
    losses = [row for row in closed if _as_float(row.get("pnl_realized_usd")) < 0]
    gross_profit = sum(_as_float(row.get("pnl_realized_usd")) for row in wins)
    gross_loss = abs(sum(_as_float(row.get("pnl_realized_usd")) for row in losses))
    pnl = _as_float(report.get("pnl_total_usd"))
    open_unrealized = _as_float(report.get("open_unrealized_pnl_usd"))
    pnl_with_unrealized = _as_float(report.get("pnl_total_including_unrealized_usd"))
    avg_position_size = sum(_as_float(row.get("size_usd")) for row in entries) / len(entries) if entries else 0.0
    return {
        "entries": _as_int(report.get("simulated_trade_count")),
        "closed_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed), 6) if closed else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "gross_profit_usd": round(gross_profit, 6),
        "gross_loss_usd": round(gross_loss, 6),
        "pnl_total_usd": round(pnl, 6),
        "pnl_realized_usd": round(_as_float(report.get("pnl_realized_usd", pnl)), 6),
        "open_unrealized_pnl_usd": round(open_unrealized, 6),
        "pnl_total_including_unrealized_usd": round(pnl_with_unrealized, 6),
        "roi_pct_on_paper_balance": round((pnl / wallet_balance_usd) * 100, 6) if wallet_balance_usd > 0 else None,
        "max_drawdown_usd": report.get("max_drawdown_usd"),
        "avg_position_size_usd": round(avg_position_size, 6),
        "position_size_usd": round(avg_position_size, 6) if avg_position_size > 0 else None,
    }


def _walkforward_verdict(total: dict[str, Any], windows: list[dict[str, Any]]) -> str:
    closed = _as_int(total.get("closed_trades"))
    pnl = _as_float(total.get("pnl_total_usd"))
    win_rate = _as_float(total.get("win_rate"))
    profit_factor = _as_float(total.get("profit_factor"))
    positive_windows = sum(1 for row in windows if _as_float(row.get("pnl_total_usd")) > 0)
    tested_windows = sum(1 for row in windows if row.get("status") == "ready")
    if closed < 8 or tested_windows < 2:
        return "insufficient_sample"
    if pnl > 0 and win_rate >= 0.55 and profit_factor >= 1.3 and positive_windows >= max(2, tested_windows - 1):
        return "robust_candidate"
    if pnl > 0 and win_rate >= 0.50 and profit_factor >= 1.0 and positive_windows >= 2:
        return "promising_but_needs_tick_replay"
    if pnl > 0:
        return "fragile_positive"
    return "invalidated_or_overfit_risk"


def _aggregate_ready_window_stats(windows: list[dict[str, Any]]) -> dict[str, Any]:
    ready = [row for row in windows if row.get("status") == "ready"]
    closed = sum(_as_int(row.get("closed_trades")) for row in ready)
    wins = sum(_as_int(row.get("wins")) for row in ready)
    gross_profit = sum(_as_float(row.get("gross_profit_usd")) for row in ready)
    gross_loss = sum(_as_float(row.get("gross_loss_usd")) for row in ready)
    pnl = sum(_as_float(row.get("pnl_total_usd")) for row in ready)
    return {
        "windows": len(ready),
        "closed_trades": closed,
        "wins": wins,
        "win_rate": round(wins / closed, 6) if closed else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "pnl_total_usd": round(pnl, 6),
        "positive_windows": sum(1 for row in ready if _as_float(row.get("pnl_total_usd")) > 0),
    }


def get_aster_paper_trading_focused_walkforward_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    lookback_days: int = 60,
    intervals: str | list[str] | None = None,
    windows: int = 3,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    disabled = _disabled()
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "replay_status": "blocked",
            "blockers": ["dry_run_required_focused_walkforward_is_read_only"],
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    requested_symbols = set(_parse_symbols(symbols, [])) if symbols else set()
    lanes = [lane for lane in _focused_walkforward_lanes() if not requested_symbols or lane["symbol"] in requested_symbols]
    if isinstance(intervals, (list, tuple)):
        clean_intervals = [str(item or "").strip() for item in intervals if str(item or "").strip()]
    else:
        clean_intervals = [item.strip() for item in str(intervals or "15m,30m,1h,2h,3h,4h").replace(";", ",").split(",") if item.strip()]
    clean_intervals = [item for item in clean_intervals if item in _KLINE_INTERVAL_MS][:8] or ["15m", "30m", "1h"]
    safe_days = max(1, min(_as_int(lookback_days, 60), 60))
    safe_windows = max(2, min(_as_int(windows, 3), 6))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    safe_timeout = max(1, min(_as_int(timeout_seconds, 15), 15))
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - safe_days * 86_400_000
    results: dict[str, Any] = {}
    failed_fetches: list[dict[str, Any]] = []
    fetch_index = 0

    for lane in lanes:
        lane_key = lane["lane_id"]
        symbol = lane["symbol"]
        side = lane["side"]
        interval_results: dict[str, Any] = {}
        for interval in clean_intervals:
            interval_ms = _KLINE_INTERVAL_MS.get(interval)
            if not interval_ms:
                continue
            expected_candles = int((safe_days * 86_400_000) / interval_ms)
            if expected_candles > 15_000:
                interval_results[interval] = {"status": "blocked_interval_too_granular", "expected_candles": expected_candles}
                continue
            if fetch_index > 0 and safe_delay:
                time.sleep(safe_delay)
            fetch_index += 1
            max_pages = max(1, min(20, (expected_candles // 1500) + 2))
            fetched = _fetch_klines_with_spot_fallback(symbol, interval, start_ms, end_ms, safe_timeout, max_pages=max_pages)
            if not fetched.get("ok"):
                failed_fetches.append({"lane_id": lane_key, "symbol": symbol, "interval": interval, "fetch_status": fetched.get("fetch_status")})
                interval_results[interval] = {"status": "fetch_failed", "fetch_status": fetched.get("fetch_status")}
                continue
            trades = [_kline_to_proxy_trade(row, symbol, idx) for idx, row in enumerate(fetched.get("klines") or [])]
            if len(trades) < max(60, window_size * safe_windows * 2):
                interval_results[interval] = {"status": "insufficient_history", "events": len(trades)}
                continue
            chunk_size = max(1, len(trades) // safe_windows)
            window_rows: list[dict[str, Any]] = []
            total = {
                "entries": 0,
                "closed_trades": 0,
                "wins": 0,
                "losses": 0,
                "gross_profit_usd": 0.0,
                "gross_loss_usd": 0.0,
                "pnl_total_usd": 0.0,
                "open_unrealized_pnl_usd": 0.0,
                "max_drawdown_usd": 0.0,
                "position_size_weighted_usd": 0.0,
            }
            for window_index in range(safe_windows):
                start = window_index * chunk_size
                end = len(trades) if window_index == safe_windows - 1 else (window_index + 1) * chunk_size
                window_trades = trades[start:end]
                if len(window_trades) < max(40, window_size * 2):
                    window_rows.append({"window": window_index + 1, "status": "insufficient_window_history", "events": len(window_trades)})
                    continue
                if side == "short":
                    rows, report = _replay_trades_short(
                        window_trades,
                        f"walkforward-{lane_key}-{interval}-{window_index}-{uuid.uuid4()}",
                        symbol,
                        wallet_balance_usd,
                        fee_bps,
                        slippage_bps,
                        window_size,
                        min_aster_score=_as_float(lane.get("min_aster_score")),
                        min_window_volume_usd=_as_float(lane.get("min_window_volume_usd")),
                        stop_loss_pct=_as_float(lane.get("stop_loss_pct")),
                        take_profit_pct=_as_float(lane.get("take_profit_pct")),
                        trailing_stop_activation_pct=_as_float(lane.get("trailing_stop_activation_pct")),
                        trailing_stop_distance_pct=_as_float(lane.get("trailing_stop_distance_pct")),
                        max_holding_trades=_as_int(lane.get("max_holding_trades"), 600),
                    )
                else:
                    rows, report = _replay_trades(
                        window_trades,
                        f"walkforward-{lane_key}-{interval}-{window_index}-{uuid.uuid4()}",
                        symbol,
                        wallet_balance_usd,
                        fee_bps,
                        slippage_bps,
                        window_size,
                        min_aster_score=_as_float(lane.get("min_aster_score")),
                        min_window_volume_usd=_as_float(lane.get("min_window_volume_usd")),
                        stop_loss_pct=_as_float(lane.get("stop_loss_pct")),
                        take_profit_pct=_as_float(lane.get("take_profit_pct")),
                        trailing_stop_activation_pct=_as_float(lane.get("trailing_stop_activation_pct")),
                        trailing_stop_distance_pct=_as_float(lane.get("trailing_stop_distance_pct")),
                        max_holding_trades=_as_int(lane.get("max_holding_trades"), 600),
                    )
                stats = _closed_trade_stats(rows, report, wallet_balance_usd)
                total["entries"] += _as_int(stats.get("entries"))
                total["closed_trades"] += _as_int(stats.get("closed_trades"))
                total["wins"] += _as_int(stats.get("wins"))
                total["losses"] += _as_int(stats.get("losses"))
                total["gross_profit_usd"] += _as_float(stats.get("gross_profit_usd"))
                total["gross_loss_usd"] += _as_float(stats.get("gross_loss_usd"))
                total["pnl_total_usd"] += _as_float(stats.get("pnl_total_usd"))
                total["open_unrealized_pnl_usd"] += _as_float(stats.get("open_unrealized_pnl_usd"))
                total["max_drawdown_usd"] = max(_as_float(total.get("max_drawdown_usd")), _as_float(stats.get("max_drawdown_usd")))
                total["position_size_weighted_usd"] += _as_float(stats.get("avg_position_size_usd")) * _as_int(stats.get("entries"))
                window_rows.append({"window": window_index + 1, "status": "ready", **stats})
            total_stats = {
                **total,
                "win_rate": round(_as_int(total.get("wins")) / _as_int(total.get("closed_trades")), 6) if _as_int(total.get("closed_trades")) else None,
                "profit_factor": round(_as_float(total.get("gross_profit_usd")) / _as_float(total.get("gross_loss_usd")), 6) if _as_float(total.get("gross_loss_usd")) else None,
                "pnl_total_usd": round(_as_float(total.get("pnl_total_usd")), 6),
                "pnl_realized_usd": round(_as_float(total.get("pnl_total_usd")), 6),
                "open_unrealized_pnl_usd": round(_as_float(total.get("open_unrealized_pnl_usd")), 6),
                "pnl_total_including_unrealized_usd": round(_as_float(total.get("pnl_total_usd")) + _as_float(total.get("open_unrealized_pnl_usd")), 6),
                "roi_pct_on_paper_balance": round((_as_float(total.get("pnl_total_usd")) / wallet_balance_usd) * 100, 6) if wallet_balance_usd > 0 else None,
                "avg_position_size_usd": round(_as_float(total.get("position_size_weighted_usd")) / _as_int(total.get("entries")), 6) if _as_int(total.get("entries")) else None,
                "position_size_usd": round(_as_float(total.get("position_size_weighted_usd")) / _as_int(total.get("entries")), 6) if _as_int(total.get("entries")) else None,
                "positive_windows": sum(1 for row in window_rows if _as_float(row.get("pnl_total_usd")) > 0),
            }
            interval_results[interval] = {
                "status": "ready",
                "market_type": fetched.get("market_type"),
                "events": len(trades),
                "coverage_windows": safe_windows,
                "lane_params": {key: lane.get(key) for key in ("side", "min_aster_score", "min_window_volume_usd", "stop_loss_pct", "take_profit_pct", "trailing_stop_activation_pct", "trailing_stop_distance_pct", "max_holding_trades")},
                "windows": window_rows,
                "total": total_stats,
                "verdict": _walkforward_verdict(total_stats, window_rows),
            }
        results[lane_key] = {"symbol": symbol, "side": side, "intervals": interval_results}

    ranked: list[dict[str, Any]] = []
    for lane_id, lane_result in results.items():
        for interval, row in (lane_result.get("intervals") or {}).items():
            total = row.get("total") or {}
            if row.get("status") != "ready":
                continue
            ranked.append(
                {
                    "lane_id": lane_id,
                    "symbol": lane_result.get("symbol"),
                    "side": lane_result.get("side"),
                    "interval": interval,
                    "verdict": row.get("verdict"),
                    "closed_trades": total.get("closed_trades"),
                    "win_rate": total.get("win_rate"),
                    "profit_factor": total.get("profit_factor"),
                    "pnl_total_usd": total.get("pnl_total_usd"),
                    "roi_pct_on_paper_balance": total.get("roi_pct_on_paper_balance"),
                    "positive_windows": total.get("positive_windows"),
                }
            )
    ranked.sort(
        key=lambda row: (
            row.get("verdict") == "robust_candidate",
            _as_float(row.get("roi_pct_on_paper_balance")),
            _as_float(row.get("profit_factor")),
            _as_int(row.get("closed_trades")),
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "dry_run": True,
        "replay_status": "ready",
        "methodology": "focused_60d_kline_walkforward_proxy_replay",
        "lookback_days": safe_days,
        "windows": safe_windows,
        "intervals": clean_intervals,
        "lane_count": len(lanes),
        "results_by_lane": results,
        "ranked_candidates": ranked[:20],
        "recommendation": ranked[0] if ranked else None,
        "interpretation_warning": "kline_proxy_replay_not_tick_level_execution; summed timeframe results are research diagnostics, not a live portfolio allocation",
        "failed_fetches": failed_fetches,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_focused_optimization_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    lookback_days: int = 60,
    intervals: str | list[str] | None = None,
    windows: int = 3,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float | None = None,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    min_closed_trades: int = 12,
    rate_limit_delay_ms: int = 300,
    search_mode: str = "standard",
    trigger_reference: str = "last_price",
    execution_model: str = "taker_market",
) -> dict[str, Any]:
    disabled = _disabled()
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "optimization_status": "blocked",
            "blockers": ["dry_run_required_focused_optimization_is_read_only"],
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    clean_symbols = _parse_symbols(symbols, ["INJUSDT", "NEARUSDT", "TIAUSDT"])[:30]
    if isinstance(intervals, (list, tuple)):
        clean_intervals = [str(item or "").strip() for item in intervals if str(item or "").strip()]
    else:
        clean_intervals = [item.strip() for item in str(intervals or "15m,30m,1h").replace(";", ",").split(",") if item.strip()]
    clean_intervals = [item for item in clean_intervals if item in _KLINE_INTERVAL_MS][:4] or ["15m"]
    clean_search_mode = str(search_mode or "standard").strip().lower()
    if clean_search_mode not in {"standard", "exploration", "deep"}:
        clean_search_mode = "standard"
    clean_trigger_reference = str(trigger_reference or "last_price").strip().lower()
    if clean_trigger_reference not in {"last_price", "mark_price"}:
        clean_trigger_reference = "last_price"
    clean_execution_model = str(execution_model or "taker_market").strip().lower()
    if clean_execution_model not in {"taker_market", "maker_post_only", "bbo_limit"}:
        clean_execution_model = "taker_market"
    score_values = [65.0, 70.0, 75.0, 80.0, 85.0]
    volume_values = [3_000.0, 5_000.0, 10_000.0]
    risk_profiles = [
        {"risk_profile": "scalp_2p5_5", "stop_loss_pct": -2.5, "take_profit_pct": 5.0, "trailing_stop_activation_pct": 2.5, "trailing_stop_distance_pct": 1.25, "max_holding_trades": 360},
        {"risk_profile": "frequent_3_6", "stop_loss_pct": -3.0, "take_profit_pct": 6.0, "trailing_stop_activation_pct": 3.0, "trailing_stop_distance_pct": 1.5, "max_holding_trades": 600},
        {"risk_profile": "balanced_4_8", "stop_loss_pct": -4.0, "take_profit_pct": 8.0, "trailing_stop_activation_pct": 4.0, "trailing_stop_distance_pct": 2.0, "max_holding_trades": 600},
        {"risk_profile": "mid_5_10", "stop_loss_pct": -5.0, "take_profit_pct": 10.0, "trailing_stop_activation_pct": 5.0, "trailing_stop_distance_pct": 2.5, "max_holding_trades": 600},
        {"risk_profile": "strict_6_12", "stop_loss_pct": -6.0, "take_profit_pct": 12.0, "trailing_stop_activation_pct": 6.0, "trailing_stop_distance_pct": 3.0, "max_holding_trades": 600},
        {"risk_profile": "wide_8_16", "stop_loss_pct": -8.0, "take_profit_pct": 16.0, "trailing_stop_activation_pct": 8.0, "trailing_stop_distance_pct": 4.0, "max_holding_trades": 800},
    ]
    window_size_values = [max(5, min(_as_int(window_size, 20), 120))]
    if clean_search_mode in {"exploration", "deep"}:
        score_values = [55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0]
        volume_values = [500.0, 1_000.0, 3_000.0, 5_000.0, 10_000.0, 25_000.0]
        risk_profiles = [
            {"risk_profile": "micro_scalp_1_2", "stop_loss_pct": -1.0, "take_profit_pct": 2.0, "trailing_stop_activation_pct": 1.0, "trailing_stop_distance_pct": 0.5, "max_holding_trades": 180},
            {"risk_profile": "tight_1p5_3", "stop_loss_pct": -1.5, "take_profit_pct": 3.0, "trailing_stop_activation_pct": 1.5, "trailing_stop_distance_pct": 0.75, "max_holding_trades": 240},
            *risk_profiles,
            {"risk_profile": "runner_5_15", "stop_loss_pct": -5.0, "take_profit_pct": 15.0, "trailing_stop_activation_pct": 7.5, "trailing_stop_distance_pct": 3.0, "max_holding_trades": 900},
            {"risk_profile": "wide_10_20", "stop_loss_pct": -10.0, "take_profit_pct": 20.0, "trailing_stop_activation_pct": 10.0, "trailing_stop_distance_pct": 5.0, "max_holding_trades": 1000},
        ]
        window_size_values = [10, 20, 40]
    if clean_search_mode == "deep":
        window_size_values = [8, 10, 20, 40, 60]
    safe_days = max(1, min(_as_int(lookback_days, 60), 60))
    safe_windows = max(2, min(_as_int(windows, 3), 6))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 15), 15))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    safe_min_closed = max(1, min(_as_int(min_closed_trades, 12), 100))
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - safe_days * 86_400_000
    ranked: list[dict[str, Any]] = []
    failed_fetches: list[dict[str, Any]] = []
    tested_combinations = 0
    fetch_index = 0

    for symbol in clean_symbols:
        symbol_fee_bps = execution_fee_bps(symbol, clean_execution_model) if fee_bps is None else _as_float(fee_bps)
        if clean_execution_model == "maker_post_only":
            execution_slippage_bps = 0.0
            fill_model = "maker_cost_only_no_queue_fill_simulation"
        elif clean_execution_model == "bbo_limit":
            execution_slippage_bps = max(0.0, _as_float(slippage_bps) * 0.5)
            fill_model = "bbo_limit_cost_proxy_no_queue_fill_simulation"
        else:
            execution_slippage_bps = _as_float(slippage_bps)
            fill_model = "taker_market_immediate_fill_proxy"
        for interval in clean_intervals:
            interval_ms = _KLINE_INTERVAL_MS.get(interval)
            if not interval_ms:
                continue
            expected_candles = int((safe_days * 86_400_000) / interval_ms)
            if expected_candles > 15_000:
                failed_fetches.append({"symbol": symbol, "interval": interval, "fetch_status": "interval_too_granular", "expected_candles": expected_candles})
                continue
            if fetch_index > 0 and safe_delay:
                time.sleep(safe_delay)
            fetch_index += 1
            max_pages = max(1, min(20, (expected_candles // 1500) + 2))
            fetched = _fetch_klines_with_spot_fallback(symbol, interval, start_ms, end_ms, safe_timeout, max_pages=max_pages)
            if not fetched.get("ok"):
                failed_fetches.append({"symbol": symbol, "interval": interval, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
                continue
            trades = [_kline_to_proxy_trade(row, symbol, idx) for idx, row in enumerate(fetched.get("klines") or [])]
            mark_reference_applied = 0
            if clean_trigger_reference == "mark_price" and fetched.get("market_type") == "futures":
                mark = _fetch_futures_reference_klines(
                    symbol,
                    interval,
                    start_ms,
                    end_ms,
                    safe_timeout,
                    "/fapi/v3/markPriceKlines",
                    "symbol",
                    max_pages=max_pages,
                )
                if mark.get("ok"):
                    trades, mark_reference_applied = _apply_mark_price_reference(trades, mark.get("klines") or [])
                    if mark_reference_applied < len(trades):
                        failed_fetches.append(
                            {
                                "symbol": symbol,
                                "interval": interval,
                                "fetch_status": "mark_price_reference_partial",
                                "mark_reference_applied": mark_reference_applied,
                                "events": len(trades),
                                "attempts": mark.get("attempts"),
                            }
                        )
                        continue
                else:
                    failed_fetches.append({"symbol": symbol, "interval": interval, "fetch_status": "mark_price_reference_unavailable", "attempts": mark.get("attempts")})
                    continue
            elif clean_trigger_reference == "mark_price":
                failed_fetches.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "fetch_status": "mark_price_requires_futures_reference",
                        "market_type": fetched.get("market_type"),
                        "attempts": fetched.get("attempts"),
                    }
                )
                continue
            min_window_size = min(window_size_values)
            if len(trades) < max(60, min_window_size * safe_windows * 2):
                failed_fetches.append({"symbol": symbol, "interval": interval, "fetch_status": "insufficient_kline_history", "events": len(trades)})
                continue
            chunk_size = max(1, len(trades) // safe_windows)
            split_trades = [
                trades[index * chunk_size : (len(trades) if index == safe_windows - 1 else (index + 1) * chunk_size)]
                for index in range(safe_windows)
            ]
            for active_window_size in window_size_values:
                for score in score_values:
                    for volume in volume_values:
                        for risk in risk_profiles:
                            tested_combinations += 1
                            total = {
                                "entries": 0,
                                "closed_trades": 0,
                                "wins": 0,
                                "losses": 0,
                                "gross_profit_usd": 0.0,
                                "gross_loss_usd": 0.0,
                                "pnl_total_usd": 0.0,
                                "open_unrealized_pnl_usd": 0.0,
                                "max_drawdown_usd": 0.0,
                                "position_size_weighted_usd": 0.0,
                            }
                            window_rows: list[dict[str, Any]] = []
                            for window_index, window_trades in enumerate(split_trades):
                                if len(window_trades) < max(40, active_window_size * 2):
                                    window_rows.append({"window": window_index + 1, "status": "insufficient_window_history", "events": len(window_trades)})
                                    continue
                                rows, report = _replay_trades(
                                    window_trades,
                                    f"focused-opt-{symbol}-{interval}-{uuid.uuid4()}",
                                    symbol,
                                    wallet_balance_usd,
                                    symbol_fee_bps,
                                    execution_slippage_bps,
                                    active_window_size,
                                    min_aster_score=score,
                                    min_window_volume_usd=volume,
                                    stop_loss_pct=_as_float(risk.get("stop_loss_pct")),
                                    take_profit_pct=_as_float(risk.get("take_profit_pct")),
                                    trailing_stop_activation_pct=_as_float(risk.get("trailing_stop_activation_pct")),
                                    trailing_stop_distance_pct=_as_float(risk.get("trailing_stop_distance_pct")),
                                    max_holding_trades=_as_int(risk.get("max_holding_trades"), 600),
                                )
                                stats = _closed_trade_stats(rows, report, wallet_balance_usd)
                                for key in ("entries", "closed_trades", "wins", "losses"):
                                    total[key] += _as_int(stats.get(key))
                                total["gross_profit_usd"] += _as_float(stats.get("gross_profit_usd"))
                                total["gross_loss_usd"] += _as_float(stats.get("gross_loss_usd"))
                                total["pnl_total_usd"] += _as_float(stats.get("pnl_total_usd"))
                                total["open_unrealized_pnl_usd"] += _as_float(stats.get("open_unrealized_pnl_usd"))
                                total["max_drawdown_usd"] = max(_as_float(total.get("max_drawdown_usd")), _as_float(stats.get("max_drawdown_usd")))
                                total["position_size_weighted_usd"] += _as_float(stats.get("avg_position_size_usd")) * _as_int(stats.get("entries"))
                                window_rows.append({"window": window_index + 1, "status": "ready", **stats})
                            closed = _as_int(total.get("closed_trades"))
                            gross_loss = _as_float(total.get("gross_loss_usd"))
                            total_stats = {
                                **total,
                                "win_rate": round(_as_int(total.get("wins")) / closed, 6) if closed else None,
                                "profit_factor": round(_as_float(total.get("gross_profit_usd")) / gross_loss, 6) if gross_loss else None,
                                "pnl_total_usd": round(_as_float(total.get("pnl_total_usd")), 6),
                                "pnl_realized_usd": round(_as_float(total.get("pnl_total_usd")), 6),
                                "open_unrealized_pnl_usd": round(_as_float(total.get("open_unrealized_pnl_usd")), 6),
                                "pnl_total_including_unrealized_usd": round(_as_float(total.get("pnl_total_usd")) + _as_float(total.get("open_unrealized_pnl_usd")), 6),
                                "roi_pct_on_paper_balance": round((_as_float(total.get("pnl_total_usd")) / wallet_balance_usd) * 100, 6) if wallet_balance_usd > 0 else None,
                                "avg_position_size_usd": round(_as_float(total.get("position_size_weighted_usd")) / _as_int(total.get("entries")), 6) if _as_int(total.get("entries")) else None,
                                "position_size_usd": round(_as_float(total.get("position_size_weighted_usd")) / _as_int(total.get("entries")), 6) if _as_int(total.get("entries")) else None,
                                "positive_windows": sum(1 for row in window_rows if _as_float(row.get("pnl_total_usd")) > 0),
                            }
                            verdict = _walkforward_verdict(total_stats, window_rows)
                            ready_windows = [row for row in window_rows if row.get("status") == "ready"]
                            validation_count = max(1, len(ready_windows) // 3) if ready_windows else 0
                            train_rows = ready_windows[:-validation_count] if validation_count else []
                            validation_rows = ready_windows[-validation_count:] if validation_count else []
                            train_stats = _aggregate_ready_window_stats(train_rows)
                            validation_stats = _aggregate_ready_window_stats(validation_rows)
                            train_pass = (
                                _as_int(train_stats.get("closed_trades")) >= max(1, safe_min_closed // 2)
                                and _as_float(train_stats.get("pnl_total_usd")) > 0
                                and _as_float(train_stats.get("profit_factor")) >= 1.1
                            )
                            validation_pass = (
                                _as_int(validation_stats.get("closed_trades")) >= max(1, safe_min_closed // 3)
                                and _as_float(validation_stats.get("pnl_total_usd")) > 0
                                and _as_float(validation_stats.get("profit_factor")) >= 1.0
                            )
                            if (
                                closed >= safe_min_closed
                                and _as_float(total_stats.get("pnl_total_usd")) > 0
                                and _as_int(total_stats.get("positive_windows")) >= max(2, safe_windows - 1)
                                and _as_float(total_stats.get("profit_factor")) >= 1.3
                                and train_pass
                                and validation_pass
                            ):
                                ranked.append(
                                    {
                                        "symbol": symbol,
                                        "side": "long",
                                        "interval": interval,
                                        "search_mode": clean_search_mode,
                                        "trigger_reference": clean_trigger_reference,
                                        "execution_model": clean_execution_model,
                                        "fill_model": fill_model,
                                        "mark_reference_applied": mark_reference_applied,
                                        "verdict": verdict,
                                        "train_validation_split": "earliest_windows_train_latest_windows_validation",
                                        "train_stats": train_stats,
                                        "validation_stats": validation_stats,
                                        "score_window_size": active_window_size,
                                        "fee_bps_applied": symbol_fee_bps,
                                        "slippage_bps_applied": execution_slippage_bps,
                                        "min_aster_score": score,
                                        "min_window_volume_usd": volume,
                                        "risk_profile": risk.get("risk_profile"),
                                        "stop_loss_pct": risk.get("stop_loss_pct"),
                                        "take_profit_pct": risk.get("take_profit_pct"),
                                        "trailing_stop_activation_pct": risk.get("trailing_stop_activation_pct"),
                                        "trailing_stop_distance_pct": risk.get("trailing_stop_distance_pct"),
                                        "max_holding_trades": risk.get("max_holding_trades"),
                                        **total_stats,
                                    }
                                )

    ranked.sort(
        key=lambda row: (
            row.get("verdict") == "robust_candidate",
            _as_float(row.get("roi_pct_on_paper_balance")),
            _as_float(row.get("profit_factor")),
            _as_int(row.get("closed_trades")),
        ),
        reverse=True,
    )
    best_by_symbol: dict[str, dict[str, Any]] = {}
    for row in ranked:
        best_by_symbol.setdefault(str(row.get("symbol")), row)
    return {
        "ok": True,
        "dry_run": True,
        "optimization_status": "ready",
        "methodology": "focused_long_parameter_optimization_60d_walkforward_kline_proxy_with_latest_window_validation",
        "search_mode": clean_search_mode,
        "symbols": clean_symbols,
        "intervals": clean_intervals,
        "lookback_days": safe_days,
        "windows": safe_windows,
        "trigger_reference": clean_trigger_reference,
        "execution_model": clean_execution_model,
        "tested_combinations": tested_combinations,
        "accepted_candidates": len(ranked),
        "parameter_space": {
            "scores": score_values,
            "volumes_usd": volume_values,
            "risk_profiles": [risk.get("risk_profile") for risk in risk_profiles],
            "score_window_sizes": window_size_values,
            "min_closed_trades": safe_min_closed,
            "fee_model": "Aster official fee by symbol and execution model when fee_bps is omitted",
            "execution_model": clean_execution_model,
            "fill_model": fill_model if clean_symbols else None,
            "fee_bps_override": fee_bps,
            "slippage_bps_input": slippage_bps,
        },
        "ranked_candidates": ranked[:25],
        "best_by_symbol": best_by_symbol,
        "recommendation": ranked[0] if ranked else None,
        "failed_fetches": failed_fetches,
        "interpretation_warning": "optimization_is_research_only; kline_proxy_replay_not_tick_level_execution; validate_top_lanes_in_forward_paper_before_any_live_decision",
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_short_fade_backtest_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 5_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["1000SATSUSDT", "ORDIUSDT", "WIFUSDT", "PEPEUSDT"])[:5]
    safe_events = max(1, min(_as_int(max_events, 5_000), 5000))
    results: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    all_short_closed: list[dict[str, Any]] = []
    all_short_losing: list[dict[str, Any]] = []
    all_open_positions: list[dict[str, Any]] = []
    short_equity_curve: list[dict[str, Any]] = []
    short_totals = {"entries": 0, "closed": 0, "wins": 0, "pnl": 0.0, "max_dd": 0.0, "duration_sum": 0.0, "duration_count": 0, "gross_profit": 0.0, "gross_loss": 0.0}
    long_totals = {"entries": 0, "closed": 0, "wins": 0, "pnl": 0.0}

    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        short_rows, short_report = _replay_trades_short(
            trades,
            f"short-fade-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=70.0,
            min_window_volume_usd=1_000.0,
        )
        long_rows, long_report = _replay_trades(
            trades,
            f"short-fade-long-baseline-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=70.0,
            min_window_volume_usd=1_000.0,
            stop_loss_pct=-15.0,
            take_profit_pct=50.0,
            trailing_stop_activation_pct=10_000.0,
            trailing_stop_distance_pct=5.0,
        )
        short_diag = _short_replay_trade_diagnostics(short_rows, wallet_balance_usd)
        open_positions = _short_open_positions_detail(short_rows)
        long_diag = _replay_trade_diagnostics(long_rows)
        short_closed = short_diag.get("closed_trades") or []
        long_closed = long_diag.get("closed_trades") or []
        all_short_closed.extend(short_closed)
        all_short_losing.extend(short_diag.get("losing_trades") or [])
        all_open_positions.extend(open_positions)
        for point in short_diag.get("short_equity_curve") or []:
            short_equity_curve.append({**point, "symbol": symbol})

        short_entries = _as_int(short_report.get("simulated_trade_count"))
        short_closed_count = len(short_closed)
        short_wins = sum(1 for row in short_closed if _as_float(row.get("pnl_realized_usd")) > 0)
        short_totals["entries"] += short_entries
        short_totals["closed"] += short_closed_count
        short_totals["wins"] += short_wins
        short_totals["pnl"] += _as_float(short_report.get("pnl_total_usd"))
        short_totals["max_dd"] = max(short_totals["max_dd"], _as_float(short_report.get("max_drawdown_usd")))
        short_totals["gross_profit"] += sum(_as_float(row.get("pnl_realized_usd")) for row in short_closed if _as_float(row.get("pnl_realized_usd")) > 0)
        short_totals["gross_loss"] += abs(sum(_as_float(row.get("pnl_realized_usd")) for row in short_closed if _as_float(row.get("pnl_realized_usd")) < 0))
        duration = short_diag.get("avg_trade_duration")
        if duration is not None and short_closed_count:
            short_totals["duration_sum"] += _as_float(duration) * short_closed_count
            short_totals["duration_count"] += short_closed_count

        long_closed_count = len(long_closed)
        long_totals["entries"] += _as_int(long_report.get("simulated_trade_count"))
        long_totals["closed"] += long_closed_count
        long_totals["wins"] += sum(1 for row in long_closed if _as_float(row.get("pnl_realized_usd")) > 0)
        long_totals["pnl"] += _as_float(long_report.get("pnl_total_usd"))

        short_win_rate = short_diag.get("win_rate")
        long_win_rate = round(long_totals["wins"] / long_totals["closed"], 6) if long_totals["closed"] else None
        results[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(trades),
            "short_fade": {
                "entries": short_entries,
                "closed_trades": short_closed_count,
                "win_rate": short_win_rate,
                "profit_factor": short_diag.get("profit_factor"),
                "max_drawdown_usd": short_report.get("max_drawdown_usd"),
                "pnl_total_usd": short_report.get("pnl_total_usd"),
                "avg_trade_duration": short_diag.get("avg_trade_duration"),
                "short_equity_curve": short_diag.get("short_equity_curve"),
                "open_positions_detail": open_positions,
                "losing_trades_detail": short_diag.get("losing_trades"),
                "cinematic_verdict": _short_cinematic_verdict(short_closed, short_diag),
            },
            "long_baseline": {
                "entries": long_report.get("simulated_trade_count"),
                "closed_trades": long_report.get("closed_trade_count"),
                "win_rate": long_report.get("win_rate"),
                "pnl_total_usd": long_report.get("pnl_total_usd"),
                "max_drawdown_usd": long_report.get("max_drawdown_usd"),
            },
            "delta_vs_long": {
                "delta_pnl_usd": round(_as_float(short_report.get("pnl_total_usd")) - _as_float(long_report.get("pnl_total_usd")), 6),
                "delta_win_rate": round(_as_float(short_win_rate) - _as_float(long_report.get("win_rate")), 6)
                if short_win_rate is not None and long_report.get("win_rate") is not None else None,
            },
        }

    global_short_win_rate = round(short_totals["wins"] / short_totals["closed"], 6) if short_totals["closed"] else None
    global_long_win_rate = round(long_totals["wins"] / long_totals["closed"], 6) if long_totals["closed"] else None
    global_short_diag = {
        "win_rate": global_short_win_rate,
        "stop_loss_hit_rate": round(
            sum(1 for row in all_short_closed if row.get("exit_reason") == "short_stop_loss_triggered") / len(all_short_closed),
            6,
        ) if all_short_closed else None,
        "immediate_adverse_ratio": round(
            sum(1 for row in all_short_closed if row.get("immediate_adverse_after_entry")) / len(all_short_closed),
            6,
        ) if all_short_closed else None,
    }
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "backtest_status": "ready",
        "symbols": clean_symbols,
        "thresholds": {
            "min_aster_score": 70.0,
            "min_window_volume_usd": 1_000.0,
            "short_stop_loss_pct": 15.0,
            "short_take_profit_pct": -25.0,
            "short_trailing_activation_pct": 10.0,
            "short_trailing_distance_pct": 5.0,
        },
        "results_by_symbol": results,
        "global_report": {
            "entries": short_totals["entries"],
            "closed_trades": short_totals["closed"],
            "win_rate": global_short_win_rate,
            "profit_factor": round(short_totals["gross_profit"] / short_totals["gross_loss"], 6) if short_totals["gross_loss"] else None,
            "max_drawdown_usd": round(short_totals["max_dd"], 6),
            "pnl_total_usd": round(short_totals["pnl"], 6),
            "avg_trade_duration": round(short_totals["duration_sum"] / short_totals["duration_count"], 3) if short_totals["duration_count"] else None,
            "short_equity_curve": short_equity_curve,
            "open_positions_detail": all_open_positions,
            "open_positions_count": len(all_open_positions),
            "open_positions_unrealized_pnl_usd": round(sum(_as_float(row.get("pnl_unrealized_usd")) for row in all_open_positions), 6),
            "losing_trades_detail": all_short_losing,
            "cinematic_verdict": _short_cinematic_verdict(all_short_closed, global_short_diag),
        },
        "long_baseline_global": {
            "entries": long_totals["entries"],
            "closed_trades": long_totals["closed"],
            "win_rate": global_long_win_rate,
            "pnl_total_usd": round(long_totals["pnl"], 6),
        },
        "delta_vs_long_global": {
            "delta_pnl_usd": round(short_totals["pnl"] - long_totals["pnl"], 6),
            "delta_win_rate": round(global_short_win_rate - global_long_win_rate, 6)
            if global_short_win_rate is not None and global_long_win_rate is not None else None,
        },
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_short_extended_backtest_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 1_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 1_000.0,
    short_stop_loss_pct: float = 15.0,
    short_take_profit_pct: float = -25.0,
    trailing_stop_activation_pct: float = 10.0,
    trailing_stop_distance_pct: float = 5.0,
) -> dict[str, Any]:
    disabled = _disabled()
    default_symbols = EXTENDED_BACKTEST_SYMBOLS[:30]
    clean_symbols = _parse_symbols(symbols, default_symbols)[:30]
    safe_events = max(1, min(_as_int(max_events, 1_000), 1000))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    symbol_comparison: list[dict[str, Any]] = []
    failed_symbols: list[dict[str, Any]] = []
    open_positions: list[dict[str, Any]] = []
    short_totals = {
        "entries": 0,
        "closed": 0,
        "wins": 0,
        "pnl": 0.0,
        "max_dd": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "duration_sum": 0.0,
        "duration_count": 0,
        "stop_loss_count": 0,
    }

    for index, symbol in enumerate(clean_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        short_rows, short_report = _replay_trades_short(
            trades,
            f"short-extended-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=min_aster_score,
            min_window_volume_usd=min_window_volume_usd,
            stop_loss_pct=short_stop_loss_pct,
            take_profit_pct=short_take_profit_pct,
            trailing_stop_activation_pct=trailing_stop_activation_pct,
            trailing_stop_distance_pct=trailing_stop_distance_pct,
        )
        long_rows, long_report = _replay_trades(
            trades,
            f"short-extended-long-baseline-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=min_aster_score,
            min_window_volume_usd=min_window_volume_usd,
            stop_loss_pct=-15.0,
            take_profit_pct=50.0,
            trailing_stop_activation_pct=10_000.0,
            trailing_stop_distance_pct=5.0,
        )
        short_diag = _short_replay_trade_diagnostics(short_rows, wallet_balance_usd)
        long_diag = _replay_trade_diagnostics(long_rows)
        short_closed = short_diag.get("closed_trades") or []
        long_closed = long_diag.get("closed_trades") or []
        symbol_open = _short_open_positions_detail(short_rows)
        open_positions.extend(symbol_open)
        gross_profit = sum(_as_float(row.get("pnl_realized_usd")) for row in short_closed if _as_float(row.get("pnl_realized_usd")) > 0)
        gross_loss = abs(sum(_as_float(row.get("pnl_realized_usd")) for row in short_closed if _as_float(row.get("pnl_realized_usd")) < 0))
        stop_loss_count = sum(1 for row in short_closed if row.get("exit_reason") == "short_stop_loss_triggered")
        short_closed_count = len(short_closed)
        short_wins = sum(1 for row in short_closed if _as_float(row.get("pnl_realized_usd")) > 0)
        short_totals["entries"] += _as_int(short_report.get("simulated_trade_count"))
        short_totals["closed"] += short_closed_count
        short_totals["wins"] += short_wins
        short_totals["pnl"] += _as_float(short_report.get("pnl_total_usd"))
        short_totals["max_dd"] = max(short_totals["max_dd"], _as_float(short_report.get("max_drawdown_usd")))
        short_totals["gross_profit"] += gross_profit
        short_totals["gross_loss"] += gross_loss
        short_totals["stop_loss_count"] += stop_loss_count
        duration = short_diag.get("avg_trade_duration")
        if duration is not None and short_closed_count:
            short_totals["duration_sum"] += _as_float(duration) * short_closed_count
            short_totals["duration_count"] += short_closed_count

        long_wins = sum(1 for row in long_closed if _as_float(row.get("pnl_realized_usd")) > 0)
        short_pf = round(gross_profit / gross_loss, 6) if gross_loss else None
        symbol_comparison.append(
            {
                "symbol": symbol,
                "market_type": fetched.get("market_type"),
                "fetched_events": len(trades),
                "short": {
                    "entries": short_report.get("simulated_trade_count"),
                    "closed_trades": short_closed_count,
                    "win_rate": short_diag.get("win_rate"),
                    "pnl_total_usd": short_report.get("pnl_total_usd"),
                    "max_drawdown_usd": short_report.get("max_drawdown_usd"),
                    "profit_factor": short_pf,
                    "profit_factor_status": "unbounded_no_losses" if gross_profit > 0 and gross_loss == 0 else None,
                    "avg_trade_duration": short_diag.get("avg_trade_duration"),
                    "stop_loss_hit_rate": round(stop_loss_count / short_closed_count, 6) if short_closed_count else None,
                    "open_positions_detail": symbol_open,
                },
                "long": {
                    "entries": long_report.get("simulated_trade_count"),
                    "closed_trades": long_report.get("closed_trade_count"),
                    "win_rate": round(long_wins / len(long_closed), 6) if long_closed else None,
                    "pnl_total_usd": long_report.get("pnl_total_usd"),
                    "max_drawdown_usd": long_report.get("max_drawdown_usd"),
                },
                "delta_short_vs_long": {
                    "delta_pnl_usd": round(_as_float(short_report.get("pnl_total_usd")) - _as_float(long_report.get("pnl_total_usd")), 6),
                    "delta_win_rate": round(_as_float(short_diag.get("win_rate")) - round(long_wins / len(long_closed), 6), 6)
                    if short_diag.get("win_rate") is not None and long_closed else None,
                },
            }
        )

    closed_total = _as_int(short_totals["closed"])
    win_rate = round(short_totals["wins"] / closed_total, 6) if closed_total else None
    profit_factor = round(short_totals["gross_profit"] / short_totals["gross_loss"], 6) if short_totals["gross_loss"] else None
    pf_for_verdict = profit_factor if profit_factor is not None else (999.0 if short_totals["gross_profit"] > 0 and closed_total else 0.0)
    max_drawdown_pct = round(short_totals["max_dd"] / max(1.0, _as_float(wallet_balance_usd)) * 100, 6)
    if closed_total < 5:
        verdict = "insufficient_sample"
    elif _as_float(win_rate) >= 0.55 and pf_for_verdict >= 1.3 and max_drawdown_pct <= 15:
        verdict = "edge_robust"
    elif _as_float(win_rate) < 0.45 or pf_for_verdict < 1.0:
        verdict = "no_edge"
    elif _as_float(win_rate) >= 0.50 and pf_for_verdict >= 1.0:
        verdict = "edge_fragile"
    else:
        verdict = "no_edge"

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "backtest_status": "ready",
        "symbols_requested": clean_symbols,
        "symbols_tested": len(symbol_comparison),
        "failed_symbols": failed_symbols,
        "thresholds": {
            "min_aster_score": _as_float(min_aster_score),
            "min_window_volume_usd": _as_float(min_window_volume_usd),
            "short_stop_loss_pct": _as_float(short_stop_loss_pct),
            "short_take_profit_pct": _as_float(short_take_profit_pct),
            "trailing_stop_activation_pct": _as_float(trailing_stop_activation_pct),
            "trailing_stop_distance_pct": _as_float(trailing_stop_distance_pct),
            "max_events_per_symbol": safe_events,
            "rate_limit_delay_ms": int(safe_delay * 1000),
        },
        "symbol_comparison": symbol_comparison,
        "global_stats_short": {
            "entries": short_totals["entries"],
            "closed_trades": closed_total,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "profit_factor_status": "unbounded_no_losses" if profit_factor is None and short_totals["gross_profit"] > 0 and closed_total else None,
            "max_drawdown_usd": round(short_totals["max_dd"], 6),
            "max_drawdown_pct": max_drawdown_pct,
            "pnl_total_usd": round(short_totals["pnl"], 6),
            "avg_trade_duration": round(short_totals["duration_sum"] / short_totals["duration_count"], 3) if short_totals["duration_count"] else None,
            "stop_loss_hit_rate": round(short_totals["stop_loss_count"] / closed_total, 6) if closed_total else None,
            "open_positions_count": len(open_positions),
            "open_positions_unrealized_pnl_usd": round(sum(_as_float(row.get("pnl_unrealized_usd")) for row in open_positions), 6),
            "open_positions_detail": open_positions,
        },
        "verdict_statistique": verdict,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_volatile_universe_short_backtest_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_symbols: int = 30,
    max_events: int = 1000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    min_quote_volume_usd: float = 100_000.0,
    min_abs_price_change_pct: float = 5.0,
    rate_limit_delay_ms: int = 300,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 1_000.0,
) -> dict[str, Any]:
    disabled = _disabled()
    safe_max_symbols = max(1, min(_as_int(max_symbols, 30), 40))
    safe_events = max(100, min(_as_int(max_events, 1000), 5000))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 15), 15))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    if symbols:
        selected_symbols = _parse_symbols(symbols, [])[:safe_max_symbols]
        discovery = {"ok": True, "discovery_status": "manual_symbols", "candidates": [{"symbol": s} for s in selected_symbols]}
    else:
        discovery = _discover_aster_volatile_universe(
            safe_max_symbols,
            safe_timeout,
            min_quote_volume_usd,
            min_abs_price_change_pct,
        )
        selected_symbols = [row["symbol"] for row in discovery.get("candidates") or []]
    parameter_grid = [
        {"name": "fast_4_6_trail_2_1", "tp": -4.0, "sl": 6.0, "ta": 2.0, "td": 1.0},
        {"name": "balanced_6_8_trail_4_2", "tp": -6.0, "sl": 8.0, "ta": 4.0, "td": 2.0},
        {"name": "current_8_10_trail_4_2", "tp": -8.0, "sl": 10.0, "ta": 4.0, "td": 2.0},
        {"name": "wide_10_12_trail_6_3", "tp": -10.0, "sl": 12.0, "ta": 6.0, "td": 3.0},
    ]
    scenario_totals: dict[str, dict[str, Any]] = {
        params["name"]: {
            "entries": 0,
            "closed": 0,
            "wins": 0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "pnl": 0.0,
            "max_drawdown": 0.0,
            "symbols_with_closed": 0,
        }
        for params in parameter_grid
    }
    symbol_results: list[dict[str, Any]] = []
    failed_symbols: list[dict[str, Any]] = []
    for index, symbol in enumerate(selected_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        scenarios: dict[str, Any] = {}
        for params in parameter_grid:
            rows, report = _replay_trades_short(
                trades,
                f"volatile-short-{params['name']}-{uuid.uuid4()}-{symbol}",
                symbol,
                wallet_balance_usd,
                6.0,
                10.0,
                20,
                min_aster_score=min_aster_score,
                min_window_volume_usd=min_window_volume_usd,
                stop_loss_pct=params["sl"],
                take_profit_pct=params["tp"],
                trailing_stop_activation_pct=params["ta"],
                trailing_stop_distance_pct=params["td"],
                max_holding_trades=600,
            )
            diag = _short_replay_trade_diagnostics(rows, wallet_balance_usd)
            summary = _short_summary_from_rows(rows, report, wallet_balance_usd)
            closed_rows = diag.get("closed_trades") or []
            closed = _as_int(summary.get("closed_trades"))
            win_rate = summary.get("win_rate")
            pnl = _as_float(summary.get("pnl_total_usd"))
            gross_profit = sum(
                _as_float(row.get("pnl_realized_usd"))
                for row in closed_rows
                if _as_float(row.get("pnl_realized_usd")) > 0
            )
            gross_loss = abs(
                sum(
                    _as_float(row.get("pnl_realized_usd"))
                    for row in closed_rows
                    if _as_float(row.get("pnl_realized_usd")) < 0
                )
            )
            totals = scenario_totals[params["name"]]
            totals["entries"] += _as_int(summary.get("entries"))
            totals["closed"] += closed
            totals["wins"] += round(_as_float(win_rate) * closed) if win_rate is not None else 0
            totals["gross_profit"] += gross_profit
            totals["gross_loss"] += gross_loss
            totals["pnl"] += pnl
            totals["max_drawdown"] = max(_as_float(totals["max_drawdown"]), _as_float(summary.get("max_drawdown_usd")))
            totals["symbols_with_closed"] += 1 if closed else 0
            scenarios[params["name"]] = {
                "params": params,
                "entries": summary.get("entries"),
                "closed_trades": closed,
                "win_rate": win_rate,
                "profit_factor": summary.get("profit_factor"),
                "profit_factor_status": summary.get("profit_factor_status"),
                "pnl_total_usd": summary.get("pnl_total_usd"),
                "max_drawdown_usd": summary.get("max_drawdown_usd"),
                "avg_trade_duration": summary.get("avg_trade_duration"),
                "stop_loss_hit_rate": summary.get("stop_loss_hit_rate"),
                "time_stop_hit_rate": summary.get("time_stop_hit_rate"),
                "open_positions_count": summary.get("open_positions_count"),
                "open_positions_unrealized_pnl_usd": summary.get("open_positions_unrealized_pnl_usd"),
            }
        symbol_results.append(
            {
                "symbol": symbol,
                "market_type": fetched.get("market_type"),
                "fetched_events": len(trades),
                "scenarios": scenarios,
            }
        )

    aggregate_by_params: dict[str, Any] = {}
    best_name = None
    best_score = None
    for params in parameter_grid:
        name = params["name"]
        totals = scenario_totals[name]
        closed = _as_int(totals["closed"])
        win_rate = round(_as_float(totals["wins"]) / closed, 6) if closed else None
        profit_factor: float | str | None
        if _as_float(totals["gross_loss"]) > 0:
            profit_factor = round(_as_float(totals["gross_profit"]) / _as_float(totals["gross_loss"]), 6)
            pf_eval = _as_float(profit_factor)
        elif _as_float(totals["gross_profit"]) > 0:
            profit_factor = "unbounded_no_losses"
            pf_eval = 999.0
        else:
            profit_factor = None
            pf_eval = 0.0
        pnl = round(_as_float(totals["pnl"]), 6)
        score = (pf_eval * 10.0) + (_as_float(win_rate) * 100.0 if win_rate is not None else 0.0) + min(50.0, closed) + pnl
        aggregate_by_params[name] = {
            "params": params,
            "entries": totals["entries"],
            "closed_trades": closed,
            "symbols_with_closed_trades": totals["symbols_with_closed"],
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "pnl_total_usd": pnl,
            "max_drawdown_usd": round(_as_float(totals["max_drawdown"]), 6),
            "selection_score": round(score, 6),
            "robustness_status": (
                "candidate_robust"
                if closed >= 50 and win_rate is not None and win_rate >= 0.55 and pf_eval >= 1.3
                else "promising_needs_more_trades"
                if closed >= 10 and win_rate is not None and win_rate >= 0.55 and pf_eval >= 1.3
                else "not_validated"
            ),
        }
        if best_score is None or score > best_score:
            best_score = score
            best_name = name
    best = aggregate_by_params.get(str(best_name)) if best_name else None
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "preview_status": "ready" if selected_symbols else "no_volatile_symbols_found",
        "discovery": discovery,
        "selected_symbols": selected_symbols,
        "entry_filters": {
            "min_aster_score": min_aster_score,
            "min_window_volume_usd": min_window_volume_usd,
        },
        "symbol_results": symbol_results,
        "aggregate_by_params": aggregate_by_params,
        "best_parameter_set": best,
        "verdict": (
            "robust_short_edge_candidate"
            if best and best.get("robustness_status") == "candidate_robust"
            else "promising_but_needs_more_closed_trades"
            if best and best.get("robustness_status") == "promising_needs_more_trades"
            else "no_conclusive_edge"
        ),
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_short_fade_universe_selection_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_symbols: int = 30,
    max_events: int = 1000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    rate_limit_delay_ms: int = 300,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 1_000.0,
    min_closed_trades: int = 2,
    min_win_rate: float = 0.60,
    max_recommendations: int = 10,
) -> dict[str, Any]:
    disabled = _disabled()
    base = get_aster_volatile_universe_short_backtest_preview(
        symbols=symbols,
        dry_run=True,
        max_symbols=max_symbols,
        max_events=max_events,
        timeout_seconds=timeout_seconds,
        wallet_balance_usd=wallet_balance_usd,
        rate_limit_delay_ms=rate_limit_delay_ms,
        min_aster_score=min_aster_score,
        min_window_volume_usd=min_window_volume_usd,
    )
    selected: list[dict[str, Any]] = []
    watchlist: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in base.get("symbol_results") or []:
        scenarios = row.get("scenarios") or {}
        best_name = None
        best_score: float | None = None
        best_data: dict[str, Any] = {}
        for name, scenario in scenarios.items():
            closed = _as_int(scenario.get("closed_trades"))
            win_rate = scenario.get("win_rate")
            pnl = _as_float(scenario.get("pnl_total_usd"))
            drawdown = _as_float(scenario.get("max_drawdown_usd"))
            score = pnl + (closed * 1.5) + ((_as_float(win_rate) * 10.0) if win_rate is not None else 0.0) - (drawdown * 0.25)
            if best_score is None or score > best_score:
                best_name = name
                best_score = score
                best_data = scenario
        closed = _as_int(best_data.get("closed_trades"))
        entries = _as_int(best_data.get("entries"))
        win_rate = best_data.get("win_rate")
        pnl = _as_float(best_data.get("pnl_total_usd"))
        drawdown = _as_float(best_data.get("max_drawdown_usd"))
        record = {
            "symbol": row.get("symbol"),
            "market_type": row.get("market_type"),
            "fetched_events": row.get("fetched_events"),
            "best_scenario": best_name,
            "entries": entries,
            "closed_trades": closed,
            "win_rate": win_rate,
            "profit_factor": best_data.get("profit_factor"),
            "profit_factor_status": best_data.get("profit_factor_status"),
            "pnl_total_usd": round(pnl, 6),
            "max_drawdown_usd": best_data.get("max_drawdown_usd"),
            "open_positions_count": best_data.get("open_positions_count"),
            "selection_score": round(_as_float(best_score), 6),
        }
        if closed >= max(1, _as_int(min_closed_trades)) and pnl > 0 and win_rate is not None and _as_float(win_rate) >= _as_float(min_win_rate):
            record["selection_status"] = "selected_forward_candidate"
            selected.append(record)
        elif entries > 0 and pnl > 0:
            record["selection_status"] = "watchlist_needs_more_closed_trades"
            watchlist.append(record)
        else:
            record["selection_status"] = "rejected_negative_or_no_signal"
            rejected.append(record)
    selected = sorted(selected, key=lambda item: _as_float(item.get("selection_score")), reverse=True)
    watchlist = sorted(watchlist, key=lambda item: _as_float(item.get("selection_score")), reverse=True)
    rejected = sorted(rejected, key=lambda item: _as_float(item.get("selection_score")), reverse=True)
    recommended = selected[: max(1, min(_as_int(max_recommendations, 10), 20))]
    recommended_symbols = [str(item.get("symbol")) for item in recommended if item.get("symbol")]
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "selection_status": "ready",
        "source_backtest_verdict": base.get("verdict"),
        "recommended_forward_symbols": recommended_symbols,
        "recommended_symbols_csv": ",".join(recommended_symbols),
        "selected_candidates": recommended,
        "watchlist_candidates": watchlist[:10],
        "rejected_candidates": rejected[:10],
        "selection_rules": {
            "min_closed_trades": max(1, _as_int(min_closed_trades)),
            "min_win_rate": _as_float(min_win_rate),
            "pnl_required": "> 0",
            "max_recommendations": max(1, min(_as_int(max_recommendations, 10), 20)),
        },
        "backtest_summary": {
            "selected_symbols": base.get("selected_symbols"),
            "failed_symbols": base.get("failed_symbols"),
            "best_parameter_set": base.get("best_parameter_set"),
            "aggregate_by_params": base.get("aggregate_by_params"),
        },
        "next_action": "use_recommended_symbols_in_forward_stateful_monitor",
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def _short_summary_from_rows(rows: list[dict[str, Any]], report: dict[str, Any], wallet_balance_usd: float) -> dict[str, Any]:
    diag = _short_replay_trade_diagnostics(rows, wallet_balance_usd)
    closed = diag.get("closed_trades") or []
    wins = [row for row in closed if _as_float(row.get("pnl_realized_usd")) > 0]
    losses = [row for row in closed if _as_float(row.get("pnl_realized_usd")) < 0]
    gross_profit = sum(_as_float(row.get("pnl_realized_usd")) for row in wins)
    gross_loss = abs(sum(_as_float(row.get("pnl_realized_usd")) for row in losses))
    stop_losses = [row for row in closed if row.get("exit_reason") == "short_stop_loss_triggered"]
    time_stops = [row for row in closed if row.get("exit_reason") == "time_stop_triggered"]
    profit_factor = round(gross_profit / gross_loss, 6) if gross_loss else None
    return {
        "entries": report.get("simulated_trade_count"),
        "closed_trades": len(closed),
        "win_rate": diag.get("win_rate"),
        "profit_factor": profit_factor,
        "profit_factor_for_eval": profit_factor if profit_factor is not None else (999.0 if gross_profit > 0 and closed else None),
        "profit_factor_status": "unbounded_no_losses" if profit_factor is None and gross_profit > 0 and closed else None,
        "pnl_total_usd": report.get("pnl_total_usd"),
        "max_drawdown_usd": report.get("max_drawdown_usd"),
        "avg_trade_duration": diag.get("avg_trade_duration"),
        "stop_loss_hit_rate": round(len(stop_losses) / len(closed), 6) if closed else None,
        "time_stop_hit_rate": round(len(time_stops) / len(closed), 6) if closed else None,
        "open_positions_count": len(_short_open_positions_detail(rows)),
        "open_positions_unrealized_pnl_usd": round(sum(_as_float(row.get("pnl_unrealized_usd")) for row in _short_open_positions_detail(rows)), 6),
    }


def _aggregate_short_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    entries = sum(_as_int(row.get("entries")) for row in summaries)
    closed = sum(_as_int(row.get("closed_trades")) for row in summaries)
    pnl = sum(_as_float(row.get("pnl_total_usd")) for row in summaries)
    max_dd = max([_as_float(row.get("max_drawdown_usd")) for row in summaries] or [0.0])
    wins = 0
    gross_profit = 0.0
    gross_loss_proxy = 0.0
    duration_sum = 0.0
    duration_count = 0
    stop_sum = 0.0
    stop_count = 0
    time_stop_sum = 0.0
    time_stop_count = 0
    for row in summaries:
        row_closed = _as_int(row.get("closed_trades"))
        if row.get("win_rate") is not None and row_closed:
            wins += round(_as_float(row.get("win_rate")) * row_closed)
        if row.get("avg_trade_duration") is not None and row_closed:
            duration_sum += _as_float(row.get("avg_trade_duration")) * row_closed
            duration_count += row_closed
        if row.get("stop_loss_hit_rate") is not None and row_closed:
            stop_sum += _as_float(row.get("stop_loss_hit_rate")) * row_closed
            stop_count += row_closed
        if row.get("time_stop_hit_rate") is not None and row_closed:
            time_stop_sum += _as_float(row.get("time_stop_hit_rate")) * row_closed
            time_stop_count += row_closed
        pf_eval = row.get("profit_factor_for_eval")
        row_pnl = _as_float(row.get("pnl_total_usd"))
        if pf_eval is not None and row_pnl > 0:
            gross_profit += row_pnl
        elif row_pnl < 0:
            gross_loss_proxy += abs(row_pnl)
    profit_factor = round(gross_profit / gross_loss_proxy, 6) if gross_loss_proxy else None
    return {
        "entries": entries,
        "closed_trades": closed,
        "win_rate": round(wins / closed, 6) if closed else None,
        "profit_factor": profit_factor,
        "profit_factor_for_eval": profit_factor if profit_factor is not None else (999.0 if gross_profit > 0 and closed else None),
        "profit_factor_status": "unbounded_no_losses" if profit_factor is None and gross_profit > 0 and closed else None,
        "pnl_total_usd": round(pnl, 6),
        "max_drawdown_usd": round(max_dd, 6),
        "avg_trade_duration": round(duration_sum / duration_count, 3) if duration_count else None,
        "stop_loss_hit_rate": round(stop_sum / stop_count, 6) if stop_count else None,
        "time_stop_hit_rate": round(time_stop_sum / time_stop_count, 6) if time_stop_count else None,
        "open_positions_count": sum(_as_int(row.get("open_positions_count")) for row in summaries),
        "open_positions_unrealized_pnl_usd": round(sum(_as_float(row.get("open_positions_unrealized_pnl_usd")) for row in summaries), 6),
    }


def _split_trades_three_windows(trades: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    total = len(trades)
    if total <= 0:
        return [("window_1", []), ("window_2", []), ("window_3", [])]
    first = total // 3
    second = (total * 2) // 3
    return [
        ("window_1", trades[:first]),
        ("window_2", trades[first:second]),
        ("window_3", trades[second:]),
    ]


def get_aster_paper_trading_short_walkforward_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 1_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    max_holding_trades: int = 200,
    max_holding_seconds: float | None = None,
    rate_limit_delay_ms: int = 300,
    min_aster_score: float = 70.0,
    min_window_volume_usd: float = 1_000.0,
    short_stop_loss_pct: float = 15.0,
    short_take_profit_pct: float = -25.0,
    trailing_stop_activation_pct: float = 10.0,
    trailing_stop_distance_pct: float = 5.0,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["1000SATSUSDT", "ORDIUSDT", "WIFUSDT"])[:30]
    safe_events = max(1, min(_as_int(max_events, 1_000), 5000))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    safe_holding_trades = max(1, min(_as_int(max_holding_trades, 200), 10_000))
    safe_min_score = max(0.0, min(_as_float(min_aster_score), 100.0))
    safe_min_volume = max(0.0, _as_float(min_window_volume_usd))
    safe_stop_loss = max(0.1, min(_as_float(short_stop_loss_pct), 100.0))
    safe_take_profit = min(-0.1, max(_as_float(short_take_profit_pct), -100.0))
    safe_trailing_activation = max(0.1, min(_as_float(trailing_stop_activation_pct), 100.0))
    safe_trailing_distance = max(0.1, min(_as_float(trailing_stop_distance_pct), 100.0))
    results_with_time_stop: dict[str, Any] = {}
    walkforward_results: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    baseline_summaries: list[dict[str, Any]] = []
    time_stop_summaries: list[dict[str, Any]] = []
    window_aggregate: dict[str, list[dict[str, Any]]] = {"window_1": [], "window_2": [], "window_3": []}

    for index, symbol in enumerate(clean_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        baseline_rows, baseline_report = _replay_trades_short(
            trades,
            f"short-walkforward-baseline-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=safe_min_score,
            min_window_volume_usd=safe_min_volume,
            stop_loss_pct=safe_stop_loss,
            take_profit_pct=safe_take_profit,
            trailing_stop_activation_pct=safe_trailing_activation,
            trailing_stop_distance_pct=safe_trailing_distance,
            max_holding_trades=0,
            max_holding_seconds=None,
        )
        time_rows, time_report = _replay_trades_short(
            trades,
            f"short-walkforward-timestop-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=safe_min_score,
            min_window_volume_usd=safe_min_volume,
            stop_loss_pct=safe_stop_loss,
            take_profit_pct=safe_take_profit,
            trailing_stop_activation_pct=safe_trailing_activation,
            trailing_stop_distance_pct=safe_trailing_distance,
            max_holding_trades=safe_holding_trades,
            max_holding_seconds=max_holding_seconds,
        )
        baseline_summary = _short_summary_from_rows(baseline_rows, baseline_report, wallet_balance_usd)
        time_summary = _short_summary_from_rows(time_rows, time_report, wallet_balance_usd)
        baseline_summaries.append(baseline_summary)
        time_stop_summaries.append(time_summary)
        results_with_time_stop[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(trades),
            "without_time_stop": baseline_summary,
            "with_time_stop": time_summary,
            "delta": {
                "pnl_total_usd": round(_as_float(time_summary.get("pnl_total_usd")) - _as_float(baseline_summary.get("pnl_total_usd")), 6),
                "open_positions_count": _as_int(time_summary.get("open_positions_count")) - _as_int(baseline_summary.get("open_positions_count")),
                "open_positions_unrealized_pnl_usd": round(_as_float(time_summary.get("open_positions_unrealized_pnl_usd")) - _as_float(baseline_summary.get("open_positions_unrealized_pnl_usd")), 6),
            },
        }

        symbol_windows: dict[str, Any] = {}
        for window_name, window_trades in _split_trades_three_windows(trades):
            rows, report = _replay_trades_short(
                window_trades,
                f"short-walkforward-{window_name}-{uuid.uuid4()}-{symbol}",
                symbol,
                wallet_balance_usd,
                fee_bps,
                slippage_bps,
                window_size,
                min_aster_score=safe_min_score,
                min_window_volume_usd=safe_min_volume,
                stop_loss_pct=safe_stop_loss,
                take_profit_pct=safe_take_profit,
                trailing_stop_activation_pct=safe_trailing_activation,
                trailing_stop_distance_pct=safe_trailing_distance,
                max_holding_trades=safe_holding_trades,
                max_holding_seconds=max_holding_seconds,
            )
            summary = _short_summary_from_rows(rows, report, wallet_balance_usd)
            summary["trade_count"] = len(window_trades)
            symbol_windows[window_name] = summary
            window_aggregate[window_name].append(summary)
        walkforward_results[symbol] = symbol_windows

    baseline_global = _aggregate_short_summaries(baseline_summaries)
    time_stop_global = _aggregate_short_summaries(time_stop_summaries)
    aggregate_windows = {name: _aggregate_short_summaries(rows) for name, rows in window_aggregate.items()}
    window_win_rates = [_as_float(row.get("win_rate")) for row in aggregate_windows.values() if row.get("win_rate") is not None]
    window_pfs = [
        _as_float(row.get("profit_factor_for_eval"))
        for row in aggregate_windows.values()
        if row.get("profit_factor_for_eval") is not None and _as_int(row.get("closed_trades")) > 0
    ]
    win_rate_spread = round(max(window_win_rates) - min(window_win_rates), 6) if len(window_win_rates) >= 2 else None
    min_pf = min(window_pfs) if window_pfs else None
    if not time_stop_summaries or _as_int(time_stop_global.get("closed_trades")) < 5:
        robustness_verdict = "insufficient_sample"
    elif win_rate_spread is not None and win_rate_spread < 0.15 and min_pf is not None and min_pf > 1.2 and len(window_pfs) == 3:
        robustness_verdict = "robust"
    else:
        robustness_verdict = "fragile"

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "preview_status": "ready",
        "symbols": clean_symbols,
        "params": {
            "max_events": safe_events,
            "max_holding_trades": safe_holding_trades,
            "max_holding_seconds": max_holding_seconds,
            "min_aster_score": safe_min_score,
            "min_window_volume_usd": safe_min_volume,
            "short_stop_loss_pct": safe_stop_loss,
            "short_take_profit_pct": safe_take_profit,
            "trailing_stop_activation_pct": safe_trailing_activation,
            "trailing_stop_distance_pct": safe_trailing_distance,
        },
        "results_with_time_stop": {
            "by_symbol": results_with_time_stop,
            "without_time_stop_global": baseline_global,
            "with_time_stop_global": time_stop_global,
            "delta_global": {
                "pnl_total_usd": round(_as_float(time_stop_global.get("pnl_total_usd")) - _as_float(baseline_global.get("pnl_total_usd")), 6),
                "open_positions_count": _as_int(time_stop_global.get("open_positions_count")) - _as_int(baseline_global.get("open_positions_count")),
                "open_positions_unrealized_pnl_usd": round(_as_float(time_stop_global.get("open_positions_unrealized_pnl_usd")) - _as_float(baseline_global.get("open_positions_unrealized_pnl_usd")), 6),
            },
        },
        "walkforward_results": {
            "by_symbol": walkforward_results,
            "aggregate_windows": aggregate_windows,
            "win_rate_spread": win_rate_spread,
            "min_profit_factor_for_eval": min_pf,
        },
        "robustness_verdict": robustness_verdict,
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def _parse_holding_values(value: str | list[Any] | tuple[Any, ...] | None) -> list[int | None]:
    raw_values: list[Any]
    if isinstance(value, (list, tuple)):
        raw_values = list(value)
    elif value is None:
        raw_values = [100, 200, 300, 400, 500, 1000, None]
    else:
        raw_values = [item.strip() for item in str(value).replace(";", ",").split(",")]
    parsed: list[int | None] = []
    for item in raw_values:
        token = str(item).strip().lower()
        if token in {"", "none", "null", "no_time_stop", "off"}:
            parsed.append(None)
            continue
        numeric = _as_int(token, 0)
        if numeric > 0:
            parsed.append(max(1, min(numeric, 10_000)))
    deduped: list[int | None] = []
    for item in parsed or [100, 200, 300, 400, 500, 1000, None]:
        if item not in deduped:
            deduped.append(item)
    return deduped[:12]


def _holding_key(value: int | None) -> str:
    return "no_time_stop" if value is None else f"max_holding_{value}"


def _calibration_recommendations(global_by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not global_by_key:
        return {
            "best_pnl_value": None,
            "best_sharpe_value": None,
            "best_balanced_value": None,
            "recommended_value": None,
            "verdict": "no_good_calibration",
            "reason": "no_calibration_rows",
        }
    max_pnl = max(_as_float(row.get("pnl_total_usd")) for row in global_by_key.values())
    best_pnl_key = max(global_by_key, key=lambda key: _as_float(global_by_key[key].get("pnl_total_usd")))
    best_pf_key = max(global_by_key, key=lambda key: _as_float(global_by_key[key].get("profit_factor_for_eval")))
    balanced: list[tuple[str, dict[str, Any]]] = []
    for key, row in global_by_key.items():
        win_rate = row.get("win_rate")
        time_stop_rate = row.get("time_stop_hit_rate")
        pnl = _as_float(row.get("pnl_total_usd"))
        if win_rate is None or time_stop_rate is None:
            continue
        if _as_float(win_rate) >= 0.70 and _as_float(time_stop_rate) <= 0.40 and pnl >= max_pnl * 0.80:
            balanced.append((key, row))
    best_balanced_key = None
    if balanced:
        best_balanced_key = max(
            balanced,
            key=lambda item: (
                _as_float(item[1].get("pnl_total_usd")),
                -_as_float(item[1].get("open_positions_count")),
                _as_float(item[1].get("profit_factor_for_eval")),
            ),
        )[0]
    recommended = best_balanced_key or best_pnl_key
    return {
        "best_pnl_value": best_pnl_key,
        "best_sharpe_value": best_pf_key,
        "best_balanced_value": best_balanced_key,
        "recommended_value": recommended,
        "verdict": "calibration_found" if best_balanced_key else "no_good_calibration",
        "reason": (
            "balanced_value_preserves_win_rate_limits_time_stop_and_keeps_80pct_of_max_pnl"
            if best_balanced_key
            else "no_value_met_win_rate_70_time_stop_40_and_80pct_pnl_constraints"
        ),
    }


def get_aster_paper_trading_short_time_stop_calibration_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 2_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    max_holding_trades_values: str | list[Any] | None = None,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["1000SATSUSDT", "ORDIUSDT", "WIFUSDT"])[:5]
    holding_values = _parse_holding_values(max_holding_trades_values)
    safe_events = max(1, min(_as_int(max_events, 2_000), 5000))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    calibration_matrix: dict[str, dict[str, Any]] = {}
    summaries_by_key: dict[str, list[dict[str, Any]]] = {_holding_key(value): [] for value in holding_values}
    failed_symbols: list[dict[str, Any]] = []

    for index, symbol in enumerate(clean_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        symbol_rows: dict[str, Any] = {}
        for holding_value in holding_values:
            key = _holding_key(holding_value)
            rows, report = _replay_trades_short(
                trades,
                f"short-timestop-calibration-{key}-{uuid.uuid4()}-{symbol}",
                symbol,
                wallet_balance_usd,
                fee_bps,
                slippage_bps,
                window_size,
                min_aster_score=70.0,
                min_window_volume_usd=1_000.0,
                max_holding_trades=0 if holding_value is None else holding_value,
                max_holding_seconds=None,
            )
            summary = _short_summary_from_rows(rows, report, wallet_balance_usd)
            compact = {
                "entries": summary.get("entries"),
                "closed_trades": summary.get("closed_trades"),
                "win_rate": summary.get("win_rate"),
                "profit_factor": summary.get("profit_factor"),
                "profit_factor_for_eval": summary.get("profit_factor_for_eval"),
                "profit_factor_status": summary.get("profit_factor_status"),
                "pnl_total_usd": summary.get("pnl_total_usd"),
                "time_stop_hit_rate": summary.get("time_stop_hit_rate"),
                "open_positions_count": summary.get("open_positions_count"),
                "pnl_latent_open_usd": summary.get("open_positions_unrealized_pnl_usd"),
            }
            symbol_rows[key] = compact
            summaries_by_key[key].append(summary)
        calibration_matrix[symbol] = symbol_rows

    global_by_key = {key: _aggregate_short_summaries(rows) for key, rows in summaries_by_key.items()}
    recommendations = _calibration_recommendations(global_by_key)
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "calibration_status": "ready",
        "symbols": clean_symbols,
        "holding_values_tested": [_holding_key(value) for value in holding_values],
        "params": {
            "max_events": safe_events,
            "min_aster_score": 70.0,
            "min_window_volume_usd": 1_000.0,
            "rate_limit_delay_ms": int(safe_delay * 1000),
        },
        "calibration_matrix": calibration_matrix,
        "global_by_value": global_by_key,
        "recommendations": recommendations,
        "verdict_global": recommendations.get("verdict"),
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_gate_calibration_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 2_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["LABUSDT", "ORDIUSDT", "1000SATSUSDT", "PEPEUSDT", "DOGEUSDT"])[:10]
    safe_events = max(1, min(_as_int(max_events, 2_000), 5000))
    min_score = 70.0
    min_volume = 1_000.0
    results: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    total_entries = 0
    total_exits = 0
    total_wins = 0
    total_pnl = 0.0
    max_drawdown = 0.0
    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        run_id = f"calibration-{uuid.uuid4()}-{symbol}"
        rows, report = _replay_trades(
            fetched.get("trades") or [],
            run_id,
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=min_score,
            min_window_volume_usd=min_volume,
        )
        closed = _as_int(report.get("closed_trade_count"))
        wins = 0
        for row in rows:
            if json.loads(row["raw_payload_json"]).get("action") == "exit" and _as_float(row.get("pnl_realized_usd")) > 0:
                wins += 1
        total_entries += _as_int(report.get("simulated_trade_count"))
        total_exits += closed
        total_wins += wins
        total_pnl += _as_float(report.get("pnl_total_usd"))
        max_drawdown = max(max_drawdown, _as_float(report.get("max_drawdown_usd")))
        results[symbol] = {
            "market_type": fetched.get("market_type"),
            "source_url": fetched.get("url"),
            "fetched_events": len(fetched.get("trades") or []),
            "attempts": fetched.get("attempts"),
            "entries": report.get("simulated_trade_count"),
            "exits": closed,
            "win_rate": report.get("win_rate"),
            "pnl_usd": report.get("pnl_total_usd"),
            "max_drawdown_usd": report.get("max_drawdown_usd"),
            "final_balance_usd": report.get("final_balance_usd"),
            "would_insert_rows": len(rows),
        }
    global_report = {
        "symbols_requested": len(clean_symbols),
        "symbols_succeeded": len(results),
        "symbols_failed": len(failed_symbols),
        "total_entries": total_entries,
        "total_exits": total_exits,
        "win_rate_global": round(total_wins / total_exits, 6) if total_exits else None,
        "pnl_total_usd": round(total_pnl, 6),
        "max_drawdown_usd": round(max_drawdown, 6),
    }
    return {
        "ok": True,
        "dry_run": dry_run,
        "calibration_status": "ready",
        "symbols": clean_symbols,
        "optimal_thresholds": {"min_aster_score": min_score, "min_window_volume_usd": min_volume},
        "max_events_cap": 5000,
        "calibration_results": results,
        "global_report": global_report,
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def _trade_time_seconds(value: Any) -> float | None:
    numeric = _as_float(value)
    if numeric <= 0:
        return None
    return numeric / 1000 if numeric > 10_000_000_000 else numeric


def _replay_trade_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed: list[dict[str, Any]] = []
    losing: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in rows:
        try:
            payload = json.loads(row.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        action = payload.get("action")
        trade_time = _trade_time_seconds(payload.get("trade_time"))
        price = _as_float(row.get("current_price"))
        if action == "entry":
            current = {
                "symbol": row.get("symbol"),
                "entry_price": _as_float(row.get("entry_price") or row.get("current_price")),
                "entry_score": _as_float(row.get("aster_score")),
                "entry_time": trade_time,
                "entry_index": _as_int(payload.get("trade_index")),
                "prices": [price] if price > 0 else [],
                "unrealized": [_as_float(row.get("pnl_unrealized_usd"))],
            }
        elif current and action == "mark_to_market":
            if price > 0:
                current["prices"].append(price)
            current["unrealized"].append(_as_float(row.get("pnl_unrealized_usd")))
        elif current and action == "exit":
            if price > 0:
                current["prices"].append(price)
            exit_unrealized = _as_float(row.get("pnl_realized_usd")) + _as_float(row.get("fees_usd")) + _as_float(row.get("slippage_usd"))
            current["unrealized"].append(exit_unrealized)
            pnl = _as_float(row.get("pnl_realized_usd"))
            prices = current.get("prices") or []
            entry_price = _as_float(current.get("entry_price"))
            min_price = min(prices) if prices else price
            max_price = max(prices) if prices else price
            unrealized_path = current.get("unrealized") or [0.0]
            min_unrealized = min(unrealized_path)
            size = _as_float(row.get("size_usd"))
            mfe_pct = ((max_price - entry_price) / entry_price * 100) if entry_price > 0 else None
            mfe_usd = ((max_price - entry_price) / entry_price * size) if entry_price > 0 else None
            duration = None
            if current.get("entry_time") is not None and trade_time is not None:
                duration = max(0.0, trade_time - _as_float(current.get("entry_time")))
            entry_index = _as_int(current.get("entry_index"))
            exit_index = _as_int(payload.get("trade_index"))
            trades_to_exit = max(0, exit_index - entry_index)
            immediate_drawdown = bool(len(prices) > 1 and prices[1] < entry_price)
            detail = {
                "symbol": current.get("symbol"),
                "exit_reason": row.get("decision_reason"),
                "entry_score": round(_as_float(current.get("entry_score")), 6),
                "pnl_realized_usd": round(pnl, 6),
                "max_adverse_excursion_usd": round(min_unrealized, 6),
                "max_adverse_excursion_pct": round(((min_price - entry_price) / entry_price * 100), 6) if entry_price > 0 else None,
                "mfe_usd": round(_as_float(mfe_usd), 6) if mfe_usd is not None else None,
                "mfe_pct": round(_as_float(mfe_pct), 6) if mfe_pct is not None else None,
                "immediate_drawdown_after_entry": immediate_drawdown,
                "trades_to_exit": trades_to_exit,
                "time_in_position_seconds": round(duration, 3) if duration is not None else None,
                "price_action_during_position": {
                    "entry": round(entry_price, 12),
                    "exit": round(price, 12),
                    "min": round(min_price, 12),
                    "max": round(max_price, 12),
                    "volatility_pct": round(((max_price - min_price) / entry_price * 100), 6) if entry_price > 0 else None,
                },
            }
            closed.append(detail)
            if pnl < 0:
                losing.append(detail)
            current = None
    wins = [row for row in closed if _as_float(row.get("pnl_realized_usd")) > 0]
    losses = [row for row in closed if _as_float(row.get("pnl_realized_usd")) < 0]
    gross_profit = sum(_as_float(row.get("pnl_realized_usd")) for row in wins)
    gross_loss = abs(sum(_as_float(row.get("pnl_realized_usd")) for row in losses))
    durations = [_as_float(row.get("time_in_position_seconds")) for row in closed if row.get("time_in_position_seconds") is not None]
    stop_losses = [row for row in closed if row.get("exit_reason") == "stop_loss_triggered"]
    immediate_drawdowns = [row for row in closed if row.get("immediate_drawdown_after_entry")]
    stop_trade_counts = [_as_int(row.get("trades_to_exit")) for row in stop_losses]
    mfe_values = [_as_float(row.get("mfe_pct")) for row in closed if row.get("mfe_pct") is not None]
    return {
        "closed_trades": closed,
        "losing_trades": losing,
        "wins": len(wins),
        "losses": len(losses),
        "avg_win": round(gross_profit / len(wins), 6) if wins else None,
        "avg_loss": round(-(gross_loss / len(losses)), 6) if losses else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "avg_time_in_position": round(sum(durations) / len(durations), 3) if durations else None,
        "stop_loss_hit_rate": round(len(stop_losses) / len(closed), 6) if closed else None,
        "immediate_drawdown_ratio": round(len(immediate_drawdowns) / len(closed), 6) if closed else None,
        "avg_time_to_stop_trades": round(sum(stop_trade_counts) / len(stop_trade_counts), 3) if stop_trade_counts else None,
        "avg_mfe_pct": round(sum(mfe_values) / len(mfe_values), 6) if mfe_values else None,
    }


def _cinematic_verdict(closed_trades: list[dict[str, Any]], diag: dict[str, Any]) -> str:
    if not closed_trades:
        return "insufficient_closed_trades"
    immediate_ratio = _as_float(diag.get("immediate_drawdown_ratio"))
    avg_mfe = _as_float(diag.get("avg_mfe_pct"))
    avg_time_to_stop = _as_float(diag.get("avg_time_to_stop_trades"))
    stop_loss_hit_rate = _as_float(diag.get("stop_loss_hit_rate"))
    if immediate_ratio >= 0.60 and stop_loss_hit_rate >= 0.60:
        return "top_fishing_signal"
    if avg_mfe > 1.0 and stop_loss_hit_rate >= 0.50:
        return "volatility_whipsaw"
    if stop_loss_hit_rate >= 0.50 and avg_time_to_stop >= 20:
        return "slow_bleed"
    return "mixed_or_insufficient_pattern"


def get_aster_paper_trading_signal_cinematic_diagnostic(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 5_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["ARBUSDT", "1000SATSUSDT"])[:10]
    safe_events = max(1, min(_as_int(max_events, 5_000), 5000))
    results: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    all_closed: list[dict[str, Any]] = []
    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        rows, report = _replay_trades(
            fetched.get("trades") or [],
            f"cinematic-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=70.0,
            min_window_volume_usd=1_000.0,
        )
        diag = _replay_trade_diagnostics(rows)
        closed = diag.get("closed_trades") or []
        all_closed.extend(closed)
        results[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(fetched.get("trades") or []),
            "entries": report.get("simulated_trade_count"),
            "closed_trades": report.get("closed_trade_count"),
            "pnl_total_usd": report.get("pnl_total_usd"),
            "immediate_drawdown_ratio": diag.get("immediate_drawdown_ratio"),
            "avg_time_to_stop_trades": diag.get("avg_time_to_stop_trades"),
            "avg_mfe_pct": diag.get("avg_mfe_pct"),
            "stop_loss_hit_rate": diag.get("stop_loss_hit_rate"),
            "verdict": _cinematic_verdict(closed, diag),
            "closed_trade_cinematics": closed,
        }
    aggregate_diag = {
        "closed_trades": all_closed,
        "immediate_drawdown_ratio": round(sum(1 for row in all_closed if row.get("immediate_drawdown_after_entry")) / len(all_closed), 6) if all_closed else None,
        "stop_loss_hit_rate": round(sum(1 for row in all_closed if row.get("exit_reason") == "stop_loss_triggered") / len(all_closed), 6) if all_closed else None,
        "avg_mfe_pct": round(sum(_as_float(row.get("mfe_pct")) for row in all_closed) / len(all_closed), 6) if all_closed else None,
        "avg_time_to_stop_trades": round(
            sum(_as_int(row.get("trades_to_exit")) for row in all_closed if row.get("exit_reason") == "stop_loss_triggered")
            / max(1, sum(1 for row in all_closed if row.get("exit_reason") == "stop_loss_triggered")),
            3,
        ) if all_closed else None,
    }
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "diagnostic_status": "ready",
        "symbols": clean_symbols,
        "thresholds": {"min_aster_score": 70.0, "min_window_volume_usd": 1_000.0},
        "results": results,
        "global_cinematic_report": {
            "closed_trade_count": len(all_closed),
            "immediate_drawdown_ratio": aggregate_diag["immediate_drawdown_ratio"],
            "avg_time_to_stop_trades": aggregate_diag["avg_time_to_stop_trades"],
            "avg_mfe_pct": aggregate_diag["avg_mfe_pct"],
            "stop_loss_hit_rate": aggregate_diag["stop_loss_hit_rate"],
            "verdict": _cinematic_verdict(all_closed, aggregate_diag),
        },
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def _risk_replay_summary(rows: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    diag = _replay_trade_diagnostics(rows)
    closed = diag.get("closed_trades") or []
    return {
        "entries": report.get("simulated_trade_count"),
        "closed_trades": report.get("closed_trade_count"),
        "win_rate": report.get("win_rate"),
        "pnl_total_usd": report.get("pnl_total_usd"),
        "max_drawdown_usd": report.get("max_drawdown_usd"),
        "final_balance_usd": report.get("final_balance_usd"),
        "avg_trade_duration_seconds": diag.get("avg_time_in_position"),
        "avg_mfe_pct": diag.get("avg_mfe_pct"),
        "immediate_drawdown_ratio": diag.get("immediate_drawdown_ratio"),
        "stop_loss_hit_rate": diag.get("stop_loss_hit_rate"),
        "trailing_stop_exit_count": sum(1 for row in closed if row.get("exit_reason") == "trailing_stop_triggered"),
        "take_profit_exit_count": sum(1 for row in closed if row.get("exit_reason") == "take_profit_triggered"),
        "cinematic_verdict": _cinematic_verdict(closed, diag),
    }


def get_aster_paper_trading_risk_recalibration_test(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 5_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    stop_loss_pct: float = -25.0,
    take_profit_pct: float = 15.0,
    trailing_stop_activation_pct: float = 10.0,
    trailing_stop_distance_pct: float = 5.0,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["1000SATSUSDT", "ORDIUSDT", "ARBUSDT"])[:10]
    safe_events = max(1, min(_as_int(max_events, 5_000), 5000))
    results: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    baseline_totals = {"entries": 0, "closed": 0, "pnl": 0.0, "wins": 0, "duration_sum": 0.0, "duration_count": 0}
    recalibrated_totals = {"entries": 0, "closed": 0, "pnl": 0.0, "wins": 0, "duration_sum": 0.0, "duration_count": 0}

    def _accumulate(target: dict[str, Any], summary: dict[str, Any]) -> None:
        target["entries"] += _as_int(summary.get("entries"))
        closed = _as_int(summary.get("closed_trades"))
        target["closed"] += closed
        target["pnl"] += _as_float(summary.get("pnl_total_usd"))
        win_rate = summary.get("win_rate")
        if win_rate is not None:
            target["wins"] += round(_as_float(win_rate) * closed)
        duration = summary.get("avg_trade_duration_seconds")
        if duration is not None and closed:
            target["duration_sum"] += _as_float(duration) * closed
            target["duration_count"] += closed

    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        baseline_rows, baseline_report = _replay_trades(
            trades,
            f"risk-baseline-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=70.0,
            min_window_volume_usd=1_000.0,
            stop_loss_pct=-15.0,
            take_profit_pct=50.0,
            trailing_stop_activation_pct=10_000.0,
            trailing_stop_distance_pct=5.0,
        )
        recalibrated_rows, recalibrated_report = _replay_trades(
            trades,
            f"risk-recalibrated-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=70.0,
            min_window_volume_usd=1_000.0,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_activation_pct=trailing_stop_activation_pct,
            trailing_stop_distance_pct=trailing_stop_distance_pct,
        )
        baseline_summary = _risk_replay_summary(baseline_rows, baseline_report)
        recalibrated_summary = _risk_replay_summary(recalibrated_rows, recalibrated_report)
        _accumulate(baseline_totals, baseline_summary)
        _accumulate(recalibrated_totals, recalibrated_summary)
        results[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(trades),
            "baseline_legacy": baseline_summary,
            "recalibrated": recalibrated_summary,
            "delta_pnl_usd": round(_as_float(recalibrated_summary.get("pnl_total_usd")) - _as_float(baseline_summary.get("pnl_total_usd")), 6),
        }

    def _global(target: dict[str, Any]) -> dict[str, Any]:
        return {
            "entries": target["entries"],
            "closed_trades": target["closed"],
            "win_rate": round(target["wins"] / target["closed"], 6) if target["closed"] else None,
            "pnl_total_usd": round(target["pnl"], 6),
            "avg_trade_duration_seconds": round(target["duration_sum"] / target["duration_count"], 3) if target["duration_count"] else None,
        }

    baseline_global = _global(baseline_totals)
    recalibrated_global = _global(recalibrated_totals)
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "test_status": "ready",
        "symbols": clean_symbols,
        "baseline_params": {"stop_loss_pct": -15.0, "take_profit_pct": 50.0, "trailing_stop": "disabled"},
        "recalibrated_params": {
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "trailing_stop_activation_pct": trailing_stop_activation_pct,
            "trailing_stop_distance_pct": trailing_stop_distance_pct,
        },
        "results": results,
        "global_report": {
            "baseline": baseline_global,
            "recalibrated": recalibrated_global,
            "delta_pnl_usd": round(_as_float(recalibrated_global.get("pnl_total_usd")) - _as_float(baseline_global.get("pnl_total_usd")), 6),
            "verdict": "risk_recalibration_improved" if _as_float(recalibrated_global.get("pnl_total_usd")) > _as_float(baseline_global.get("pnl_total_usd")) else "risk_recalibration_not_improved",
        },
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


HYBRID_BEHAVIORAL_SCORE_MOCKS = {
    "LABUSDT": 75.0,
    "ORDIUSDT": 30.0,
    "1000SATSUSDT": 45.0,
}


def get_aster_paper_trading_hybrid_signal_test(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 2_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    min_aster_score: float = 70.0,
    min_behavioral_score: float | None = None,
    stop_loss_pct: float = -15.0,
    take_profit_pct: float = 50.0,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["LABUSDT", "ORDIUSDT", "1000SATSUSDT"])[:10]
    safe_events = max(1, min(_as_int(max_events, 2_000), 5000))
    scenario_thresholds: list[float | None] = [None, 40.0, 60.0, 80.0]
    if min_behavioral_score is not None and _as_float(min_behavioral_score) not in [40.0, 60.0, 80.0]:
        scenario_thresholds.append(_as_float(min_behavioral_score))
    results: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    scenario_totals: dict[str, dict[str, Any]] = {
        ("aster_only" if threshold is None else f"behavioral_{int(threshold)}"): {
            "entries": 0,
            "closed": 0,
            "wins": 0,
            "pnl": 0.0,
            "duration_sum": 0.0,
            "duration_count": 0,
        }
        for threshold in scenario_thresholds
    }

    def _scenario_key(threshold: float | None) -> str:
        return "aster_only" if threshold is None else f"behavioral_{int(threshold)}"

    def _accumulate(target: dict[str, Any], summary: dict[str, Any]) -> None:
        closed = _as_int(summary.get("closed_trades"))
        target["entries"] += _as_int(summary.get("entries"))
        target["closed"] += closed
        target["pnl"] += _as_float(summary.get("pnl_total_usd"))
        if summary.get("win_rate") is not None:
            target["wins"] += round(_as_float(summary.get("win_rate")) * closed)
        if summary.get("avg_trade_duration_seconds") is not None and closed:
            target["duration_sum"] += _as_float(summary.get("avg_trade_duration_seconds")) * closed
            target["duration_count"] += closed

    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        behavioral_score = HYBRID_BEHAVIORAL_SCORE_MOCKS.get(symbol)
        symbol_scenarios: dict[str, Any] = {}
        for threshold in scenario_thresholds:
            rows, report = _replay_trades(
                trades,
                f"hybrid-{_scenario_key(threshold)}-{uuid.uuid4()}-{symbol}",
                symbol,
                wallet_balance_usd,
                fee_bps,
                slippage_bps,
                window_size,
                min_aster_score=min_aster_score,
                min_window_volume_usd=1_000.0,
                behavioral_score=behavioral_score,
                min_behavioral_score=threshold,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                trailing_stop_activation_pct=10_000.0,
                trailing_stop_distance_pct=5.0,
            )
            summary = _risk_replay_summary(rows, report)
            key = _scenario_key(threshold)
            _accumulate(scenario_totals[key], summary)
            symbol_scenarios[key] = {
                "min_behavioral_score": threshold,
                "behavioral_score_mock": behavioral_score,
                **summary,
            }
        results[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(trades),
            "behavioral_score_source": "mock_fixed_for_hybrid_test",
            "behavioral_score_mock": behavioral_score,
            "scenarios": symbol_scenarios,
        }

    def _global(total: dict[str, Any]) -> dict[str, Any]:
        return {
            "entries_count": total["entries"],
            "closed_trades": total["closed"],
            "win_rate": round(total["wins"] / total["closed"], 6) if total["closed"] else None,
            "pnl_total_usd": round(total["pnl"], 6),
            "avg_trade_duration_seconds": round(total["duration_sum"] / total["duration_count"], 3) if total["duration_count"] else None,
        }

    global_scenarios = {key: _global(total) for key, total in scenario_totals.items()}
    baseline_pnl = _as_float(global_scenarios.get("aster_only", {}).get("pnl_total_usd"))
    best_key = max(global_scenarios, key=lambda key: _as_float(global_scenarios[key].get("pnl_total_usd"))) if global_scenarios else None
    tradable_keys = [key for key, value in global_scenarios.items() if _as_int(value.get("entries_count")) > 0]
    best_tradable_key = max(tradable_keys, key=lambda key: _as_float(global_scenarios[key].get("pnl_total_usd"))) if tradable_keys else None
    best_pnl = _as_float(global_scenarios.get(best_key or "", {}).get("pnl_total_usd"))
    best_tradable_pnl = _as_float(global_scenarios.get(best_tradable_key or "", {}).get("pnl_total_usd"))
    best_tradable_closed = _as_int(global_scenarios.get(best_tradable_key or "", {}).get("closed_trades"))
    best_tradable_win_rate = global_scenarios.get(best_tradable_key or "", {}).get("win_rate")
    if best_tradable_key and best_tradable_pnl > baseline_pnl and best_tradable_pnl > 0 and best_tradable_closed > 0:
        verdict = "hybrid_filter_profitable_improvement"
    elif best_tradable_key and best_tradable_pnl > baseline_pnl:
        verdict = "hybrid_filter_reduced_loss_not_profit_validated"
    elif best_key and _as_int(global_scenarios.get(best_key, {}).get("entries_count")) == 0 and best_pnl >= baseline_pnl:
        verdict = "hybrid_filter_skips_trades_not_profit_validated"
    else:
        verdict = "hybrid_filter_not_improved"
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "test_status": "ready",
        "symbols": clean_symbols,
        "mock_behavioral_scores": HYBRID_BEHAVIORAL_SCORE_MOCKS,
        "params": {
            "min_aster_score": min_aster_score,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "max_events": safe_events,
            "min_window_volume_usd": 1_000.0,
        },
        "results": results,
        "global_scenarios": global_scenarios,
        "global_report": {
            "best_scenario_including_skip": best_key,
            "best_tradable_scenario": best_tradable_key,
            "best_pnl_total_usd": round(best_pnl, 6),
            "best_tradable_pnl_total_usd": round(best_tradable_pnl, 6),
            "best_tradable_win_rate": best_tradable_win_rate,
            "baseline_pnl_total_usd": round(baseline_pnl, 6),
            "delta_vs_aster_only_usd": round(best_tradable_pnl - baseline_pnl, 6),
            "verdict": verdict,
        },
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def _symbol_from_behavioral_candidate(candidate: dict[str, Any]) -> str | None:
    symbol = str(candidate.get("target_symbol") or "").strip().upper()
    if not symbol or symbol in {"NONE", "NULL", "UNKNOWN"}:
        return None
    clean = "".join(ch for ch in symbol if ch.isalnum())
    if not clean:
        return None
    return clean if clean.endswith("USDT") else f"{clean}USDT"


def _local_behavioral_symbol_universe(limit: int = 10) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    universe: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    try:
        scoring = get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
            chain="bsc",
            limit=10,
            dry_run=True,
        )
        for row in scoring.get("candidates") or []:
            score = _as_float(row.get("behavioral_anomaly_score"))
            if score < 60:
                continue
            symbol = _symbol_from_behavioral_candidate(row)
            if not symbol:
                continue
            universe[symbol] = {
                "symbol": symbol,
                "token_address": row.get("target_token"),
                "behavioral_score": score,
                "behavioral_score_source": "local_top_expansion_scoring",
                "pool_address": row.get("pool_address"),
            }
    except Exception as exc:  # Defensive: this preview must never block the whole Aster test.
        errors.append({"stage": "local_behavioral_universe", "error": str(exc)})
    for symbol, token in HYBRID_SEED_SYMBOL_TO_TOKEN.items():
        universe.setdefault(symbol, {
            "symbol": symbol,
            "token_address": token,
            "behavioral_score": None,
            "behavioral_score_source": "seed_pending_local_lookup",
            "pool_address": None,
        })
    return list(universe.values())[: max(1, min(_as_int(limit, 10), 10))], errors


def _local_behavioral_score_for_token(token_address: str | None) -> tuple[float | None, str, dict[str, Any] | None]:
    token = str(token_address or "").strip().lower()
    if not token.startswith("0x"):
        return None, "token_address_missing", None
    try:
        scoring = get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
            chain="bsc",
            limit=10,
            dry_run=True,
            token_addresses=[token],
        )
        candidates = scoring.get("candidates") or []
        if not candidates:
            return None, "not_found_locally", None
        best = max(candidates, key=lambda row: _as_float(row.get("behavioral_anomaly_score")))
        return _as_float(best.get("behavioral_anomaly_score")), "local_explicit_token_scoring", best
    except Exception as exc:  # Defensive: one bad token must not block the batch.
        return None, f"scoring_failed:{exc}", None


def _closed_pnls_from_rows(rows: list[dict[str, Any]]) -> list[float]:
    pnls: list[float] = []
    for row in rows:
        try:
            payload = json.loads(row.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if payload.get("action") == "exit":
            pnls.append(_as_float(row.get("pnl_realized_usd")))
    return pnls


def _sharpe_proxy(pnls: list[float]) -> float | None:
    if len(pnls) < 2:
        return None
    mean = sum(pnls) / len(pnls)
    variance = sum((pnl - mean) ** 2 for pnl in pnls) / len(pnls)
    volatility = variance ** 0.5
    return round(mean / volatility, 6) if volatility > 0 else None


def get_aster_paper_trading_hybrid_signal_test_v2(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 5_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    min_aster_score: float = 70.0,
    min_behavioral_score: float | None = None,
    stop_loss_pct: float = -15.0,
    take_profit_pct: float = 50.0,
) -> dict[str, Any]:
    disabled = _disabled()
    discovery_errors: list[dict[str, Any]] = []
    if symbols:
        clean_symbols = _parse_symbols(symbols, [])[:10]
        universe = [
            {
                "symbol": symbol,
                "token_address": HYBRID_SEED_SYMBOL_TO_TOKEN.get(symbol),
                "behavioral_score": None,
                "behavioral_score_source": "explicit_symbol_pending_lookup",
                "pool_address": None,
            }
            for symbol in clean_symbols
        ]
    else:
        universe, discovery_errors = _local_behavioral_symbol_universe(10)
        clean_symbols = [row["symbol"] for row in universe]
    safe_events = max(1, min(_as_int(max_events, 5_000), 5000))
    scenario_thresholds: list[float | None] = [None, 40.0, 60.0, 80.0]
    if min_behavioral_score is not None and _as_float(min_behavioral_score) not in [40.0, 60.0, 80.0]:
        scenario_thresholds.append(_as_float(min_behavioral_score))

    def _scenario_key(threshold: float | None) -> str:
        return "aster_only" if threshold is None else f"behavioral_{int(threshold)}"

    aggregate: dict[str, dict[str, Any]] = {
        _scenario_key(threshold): {"entries": 0, "closed": 0, "wins": 0, "pnl": 0.0, "pnls": [], "duration_sum": 0.0, "duration_count": 0}
        for threshold in scenario_thresholds
    }
    results_by_symbol: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    for item in universe:
        symbol = item["symbol"]
        token_address = item.get("token_address")
        behavioral_score, behavioral_source, scoring_candidate = _local_behavioral_score_for_token(token_address)
        if behavioral_score is None and item.get("behavioral_score") is not None:
            behavioral_score = _as_float(item.get("behavioral_score"))
            behavioral_source = item.get("behavioral_score_source") or "local_universe_cache"
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "token_address": token_address, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        scenarios: dict[str, Any] = {}
        for threshold in scenario_thresholds:
            rows, report = _replay_trades(
                trades,
                f"hybrid-v2-{_scenario_key(threshold)}-{uuid.uuid4()}-{symbol}",
                symbol,
                wallet_balance_usd,
                fee_bps,
                slippage_bps,
                window_size,
                min_aster_score=min_aster_score,
                min_window_volume_usd=1_000.0,
                behavioral_score=behavioral_score,
                min_behavioral_score=threshold,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                trailing_stop_activation_pct=10_000.0,
                trailing_stop_distance_pct=5.0,
            )
            summary = _risk_replay_summary(rows, report)
            pnls = _closed_pnls_from_rows(rows)
            key = _scenario_key(threshold)
            aggregate[key]["entries"] += _as_int(summary.get("entries"))
            aggregate[key]["closed"] += _as_int(summary.get("closed_trades"))
            aggregate[key]["pnl"] += _as_float(summary.get("pnl_total_usd"))
            aggregate[key]["pnls"].extend(pnls)
            aggregate[key]["wins"] += sum(1 for pnl in pnls if pnl > 0)
            if summary.get("avg_trade_duration_seconds") is not None and _as_int(summary.get("closed_trades")):
                aggregate[key]["duration_sum"] += _as_float(summary.get("avg_trade_duration_seconds")) * _as_int(summary.get("closed_trades"))
                aggregate[key]["duration_count"] += _as_int(summary.get("closed_trades"))
            scenarios[key] = {
                "min_behavioral_score": threshold,
                "behavioral_score": behavioral_score,
                **summary,
                "closed_pnl_samples": pnls[:10],
            }
        results_by_symbol[symbol] = {
            "symbol": symbol,
            "token_address": token_address,
            "pool_address": item.get("pool_address") or (scoring_candidate or {}).get("pool_address"),
            "behavioral_score": behavioral_score,
            "behavioral_score_source": behavioral_source,
            "market_type": fetched.get("market_type"),
            "fetched_events": len(trades),
            "attempts": fetched.get("attempts"),
            "scenarios": scenarios,
        }

    aggregate_by_threshold: dict[str, Any] = {}
    for key, total in aggregate.items():
        aggregate_by_threshold[key] = {
            "entries_count": total["entries"],
            "closed_trades": total["closed"],
            "win_rate": round(total["wins"] / total["closed"], 6) if total["closed"] else None,
            "pnl_total_usd": round(total["pnl"], 6),
            "avg_trade_duration_seconds": round(total["duration_sum"] / total["duration_count"], 3) if total["duration_count"] else None,
            "sharpe_proxy": _sharpe_proxy(total["pnls"]),
            "closed_pnl_samples": total["pnls"][:10],
        }
    total_entries_by_threshold = {key: value["entries_count"] for key, value in aggregate_by_threshold.items()}
    pnl_by_threshold = {key: value["pnl_total_usd"] for key, value in aggregate_by_threshold.items()}
    sharpe_candidates = {
        key: value["sharpe_proxy"]
        for key, value in aggregate_by_threshold.items()
        if key != "aster_only" and value.get("sharpe_proxy") is not None
    }
    pnl_candidates = {key: value for key, value in aggregate_by_threshold.items() if key != "aster_only"}
    best_by_sharpe = max(sharpe_candidates, key=lambda key: _as_float(sharpe_candidates[key])) if sharpe_candidates else None
    best_by_pnl = max(pnl_candidates, key=lambda key: _as_float(pnl_candidates[key].get("pnl_total_usd"))) if pnl_candidates else None
    best_overall_by_pnl = max(aggregate_by_threshold, key=lambda key: _as_float(aggregate_by_threshold[key].get("pnl_total_usd"))) if aggregate_by_threshold else None
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "test_status": "ready",
        "symbols": clean_symbols,
        "params": {
            "min_aster_score": min_aster_score,
            "min_behavioral_score": min_behavioral_score,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "max_events": safe_events,
            "min_window_volume_usd": 1_000.0,
        },
        "results_by_symbol": results_by_symbol,
        "aggregate_by_threshold": aggregate_by_threshold,
        "total_entries_by_threshold": total_entries_by_threshold,
        "pnl_by_threshold": pnl_by_threshold,
        "best_hybrid_threshold_recommendation": {
            "best_threshold_by_sharpe": best_by_sharpe,
            "best_threshold_by_pnl": best_by_pnl,
            "best_overall_by_pnl": best_overall_by_pnl,
            "recommendation": (
                "insufficient_closed_trades_for_sharpe"
                if best_by_sharpe is None else
                f"review_{best_by_sharpe}_with_more_closed_trades"
            ),
        },
        "discovery_errors": discovery_errors,
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_final_alignment_test(
    dry_run: bool = True,
    max_events: int = 2_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    min_aster_score: float = 70.0,
) -> dict[str, Any]:
    disabled = _disabled()
    safe_events = max(1, min(_as_int(max_events, 2_000), 5000))
    universe, discovery_errors = _local_behavioral_symbol_universe(10)
    behavioral_by_symbol = {row["symbol"]: row for row in universe if _as_float(row.get("behavioral_score")) >= 60}
    for symbol, token in HYBRID_SEED_SYMBOL_TO_TOKEN.items():
        if symbol not in behavioral_by_symbol:
            score, source, candidate = _local_behavioral_score_for_token(token)
            behavioral_by_symbol[symbol] = {
                "symbol": symbol,
                "token_address": token,
                "behavioral_score": score,
                "behavioral_score_source": source,
                "pool_address": (candidate or {}).get("pool_address"),
            }
    candidate_symbols = list(dict.fromkeys([*EXTENDED_BACKTEST_SYMBOLS, *behavioral_by_symbol.keys()]))[:40]
    aligned: list[dict[str, Any]] = []
    non_aligned: list[dict[str, Any]] = []
    fetch_cache: dict[str, dict[str, Any]] = {}
    for symbol in candidate_symbols:
        behavior = behavioral_by_symbol.get(symbol)
        if not behavior or _as_float(behavior.get("behavioral_score")) < 60:
            if behavior:
                non_aligned.append({**behavior, "alignment_status": "behavioral_score_below_60"})
            continue
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        fetch_cache[symbol] = fetched
        if fetched.get("ok"):
            aligned.append({
                **behavior,
                "alignment_status": "aligned",
                "market_type": fetched.get("market_type"),
                "fetched_events": len(fetched.get("trades") or []),
                "attempts": fetched.get("attempts"),
            })
        else:
            non_aligned.append({
                **behavior,
                "alignment_status": "not_found_on_aster",
                "fetch_status": fetched.get("fetch_status"),
                "attempts": fetched.get("attempts"),
            })
    if not aligned:
        return {
            "ok": True,
            "dry_run": bool(dry_run),
            "alignment_status": "blocked",
            "verdict": "no_alignment_possible",
            "aligned_tokens": [],
            "non_aligned_tokens": non_aligned,
            "backfill_plan_preview": {
                "would_backfill": False,
                "recommended_next_step": "choose_targeted_tokens_from_Aster_with_market_presence_then_plan_bounded_raw_context_lookup",
                "reason": "No token currently has both local behavioral_score>=60 and Aster market trades.",
            },
            "discovery_errors": discovery_errors,
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }

    results: dict[str, Any] = {}
    totals = {
        "aster_entries": 0,
        "hybrid_entries": 0,
        "aster_closed": 0,
        "hybrid_closed": 0,
        "aster_wins": 0,
        "hybrid_wins": 0,
        "aster_pnl": 0.0,
        "hybrid_pnl": 0.0,
        "aster_drawdown": 0.0,
        "hybrid_drawdown": 0.0,
    }
    for item in aligned:
        symbol = item["symbol"]
        trades = fetch_cache.get(symbol, {}).get("trades") or []
        behavioral_score = _as_float(item.get("behavioral_score"))
        aster_rows, aster_report = _replay_trades(
            trades,
            f"alignment-aster-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=min_aster_score,
            min_window_volume_usd=1_000.0,
            behavioral_score=behavioral_score,
            min_behavioral_score=None,
            stop_loss_pct=-15.0,
            take_profit_pct=50.0,
            trailing_stop_activation_pct=10_000.0,
            trailing_stop_distance_pct=5.0,
        )
        hybrid_rows, hybrid_report = _replay_trades(
            trades,
            f"alignment-hybrid60-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=min_aster_score,
            min_window_volume_usd=1_000.0,
            behavioral_score=behavioral_score,
            min_behavioral_score=60.0,
            stop_loss_pct=-15.0,
            take_profit_pct=50.0,
            trailing_stop_activation_pct=10_000.0,
            trailing_stop_distance_pct=5.0,
        )
        aster_summary = _risk_replay_summary(aster_rows, aster_report)
        hybrid_summary = _risk_replay_summary(hybrid_rows, hybrid_report)
        aster_pnls = _closed_pnls_from_rows(aster_rows)
        hybrid_pnls = _closed_pnls_from_rows(hybrid_rows)
        totals["aster_entries"] += _as_int(aster_summary.get("entries"))
        totals["hybrid_entries"] += _as_int(hybrid_summary.get("entries"))
        totals["aster_closed"] += _as_int(aster_summary.get("closed_trades"))
        totals["hybrid_closed"] += _as_int(hybrid_summary.get("closed_trades"))
        totals["aster_wins"] += sum(1 for pnl in aster_pnls if pnl > 0)
        totals["hybrid_wins"] += sum(1 for pnl in hybrid_pnls if pnl > 0)
        totals["aster_pnl"] += _as_float(aster_summary.get("pnl_total_usd"))
        totals["hybrid_pnl"] += _as_float(hybrid_summary.get("pnl_total_usd"))
        totals["aster_drawdown"] = max(totals["aster_drawdown"], _as_float(aster_summary.get("max_drawdown_usd")))
        totals["hybrid_drawdown"] = max(totals["hybrid_drawdown"], _as_float(hybrid_summary.get("max_drawdown_usd")))
        results[symbol] = {
            "token_address": item.get("token_address"),
            "behavioral_score": behavioral_score,
            "market_type": item.get("market_type"),
            "fetched_events": item.get("fetched_events"),
            "aster_only": aster_summary,
            "hybrid_60": hybrid_summary,
            "delta_pnl_usd": round(_as_float(hybrid_summary.get("pnl_total_usd")) - _as_float(aster_summary.get("pnl_total_usd")), 6),
            "delta_max_drawdown_usd": round(_as_float(hybrid_summary.get("max_drawdown_usd")) - _as_float(aster_summary.get("max_drawdown_usd")), 6),
        }
    pnl_delta = totals["hybrid_pnl"] - totals["aster_pnl"]
    drawdown_delta = totals["hybrid_drawdown"] - totals["aster_drawdown"]
    pnl_improvement_ratio = (pnl_delta / abs(totals["aster_pnl"])) if totals["aster_pnl"] < 0 else 0.0
    drawdown_reduction_ratio = ((totals["aster_drawdown"] - totals["hybrid_drawdown"]) / totals["aster_drawdown"]) if totals["aster_drawdown"] > 0 else 0.0
    if drawdown_reduction_ratio >= 0.15 or pnl_improvement_ratio >= 0.20:
        verdict = "hybrid_validated"
    elif totals["hybrid_entries"] == 0 and totals["aster_entries"] > 0:
        verdict = "hybrid_invalidated"
    elif abs(pnl_improvement_ratio) < 0.10 and abs(drawdown_reduction_ratio) < 0.10:
        verdict = "hybrid_neutral"
    else:
        verdict = "hybrid_invalidated" if pnl_delta < 0 else "hybrid_neutral"
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "alignment_status": "ready",
        "verdict": verdict,
        "aligned_tokens": aligned,
        "non_aligned_tokens": non_aligned,
        "results_by_symbol": results,
        "comparison": {
            "aster_only": {
                "entries": totals["aster_entries"],
                "closed_trades": totals["aster_closed"],
                "win_rate": round(totals["aster_wins"] / totals["aster_closed"], 6) if totals["aster_closed"] else None,
                "pnl_total_usd": round(totals["aster_pnl"], 6),
                "max_drawdown_usd": round(totals["aster_drawdown"], 6),
            },
            "hybrid_60": {
                "entries": totals["hybrid_entries"],
                "closed_trades": totals["hybrid_closed"],
                "win_rate": round(totals["hybrid_wins"] / totals["hybrid_closed"], 6) if totals["hybrid_closed"] else None,
                "pnl_total_usd": round(totals["hybrid_pnl"], 6),
                "max_drawdown_usd": round(totals["hybrid_drawdown"], 6),
            },
            "delta_pnl_usd": round(pnl_delta, 6),
            "delta_max_drawdown_usd": round(drawdown_delta, 6),
            "pnl_improvement_ratio": round(pnl_improvement_ratio, 6),
            "drawdown_reduction_ratio": round(drawdown_reduction_ratio, 6),
            "win_rate_diff": None if not totals["aster_closed"] or not totals["hybrid_closed"] else round((totals["hybrid_wins"] / totals["hybrid_closed"]) - (totals["aster_wins"] / totals["aster_closed"]), 6),
        },
        "discovery_errors": discovery_errors,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_extended_backtest_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 5_000,
    timeout_seconds: int = 15,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, EXTENDED_BACKTEST_SYMBOLS)[:30]
    safe_events = max(1, min(_as_int(max_events, 5_000), 5000))
    min_score = 70.0
    min_volume = 1_000.0
    results: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    totals = {"entries": 0, "exits": 0, "wins": 0, "pnl": 0.0, "max_drawdown": 0.0}
    all_closed: list[dict[str, Any]] = []
    all_losing: list[dict[str, Any]] = []
    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        rows, report = _replay_trades(
            fetched.get("trades") or [],
            f"extended-{uuid.uuid4()}-{symbol}",
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=min_score,
            min_window_volume_usd=min_volume,
        )
        diag = _replay_trade_diagnostics(rows)
        entries = _as_int(report.get("simulated_trade_count"))
        exits = _as_int(report.get("closed_trade_count"))
        totals["entries"] += entries
        totals["exits"] += exits
        totals["wins"] += _as_int(diag.get("wins"))
        totals["pnl"] += _as_float(report.get("pnl_total_usd"))
        totals["max_drawdown"] = max(totals["max_drawdown"], _as_float(report.get("max_drawdown_usd")))
        for closed in diag.get("closed_trades") or []:
            all_closed.append(closed)
        for loss in diag.get("losing_trades") or []:
            all_losing.append(loss)
        results[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(fetched.get("trades") or []),
            "entries": entries,
            "exits": exits,
            "win_rate": report.get("win_rate"),
            "pnl_usd": report.get("pnl_total_usd"),
            "max_drawdown_usd": report.get("max_drawdown_usd"),
            "avg_win": diag.get("avg_win"),
            "avg_loss": diag.get("avg_loss"),
            "profit_factor": diag.get("profit_factor"),
            "avg_time_in_position": diag.get("avg_time_in_position"),
            "stop_loss_hit_rate": diag.get("stop_loss_hit_rate"),
            "losing_trades": diag.get("losing_trades"),
            "would_insert_rows": len(rows),
        }
    ranked_with_symbols = sorted(results.items(), key=lambda item: _as_float(item[1].get("pnl_usd")), reverse=True)
    gross_profit = 0.0
    gross_loss = 0.0
    durations: list[float] = []
    stop_loss_count = 0
    for closed in all_closed:
        pnl = _as_float(closed.get("pnl_realized_usd"))
        if pnl > 0:
            gross_profit += pnl
        elif pnl < 0:
            gross_loss += abs(pnl)
        if closed.get("exit_reason") == "stop_loss_triggered":
            stop_loss_count += 1
        if closed.get("time_in_position_seconds") is not None:
            durations.append(_as_float(closed.get("time_in_position_seconds")))
    global_stats = {
        "total_trades": totals["exits"],
        "total_entries": totals["entries"],
        "win_rate": round(totals["wins"] / totals["exits"], 6) if totals["exits"] else None,
        "avg_win": round(gross_profit / totals["wins"], 6) if totals["wins"] else None,
        "avg_loss": round(-(gross_loss / max(1, len(all_losing))), 6) if all_losing else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "avg_time_in_position": round(sum(durations) / len(durations), 3) if durations else None,
        "stop_loss_hit_rate": round(stop_loss_count / len(all_closed), 6) if all_closed else None,
        "pnl_total_usd": round(totals["pnl"], 6),
        "max_drawdown_usd": round(totals["max_drawdown"], 6),
        "best_performing_assets": [{"symbol": symbol, "pnl_usd": data.get("pnl_usd")} for symbol, data in ranked_with_symbols[:3]],
        "worst_performing_assets": [{"symbol": symbol, "pnl_usd": data.get("pnl_usd")} for symbol, data in ranked_with_symbols[-3:]],
    }
    return {
        "ok": True,
        "dry_run": dry_run,
        "backtest_status": "ready",
        "symbols": clean_symbols,
        "thresholds": {"min_aster_score": min_score, "min_window_volume_usd": min_volume},
        "max_events_cap": 5000,
        "backtest_results": results,
        "losing_trades_detail": all_losing,
        "global_report": global_stats,
        "failed_symbols": failed_symbols,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def _ledger_insert_columns() -> list[str]:
    return [
        "run_id",
        "created_at",
        "symbol",
        "token_address",
        "event_type",
        "state",
        "decision_reason",
        "aster_score",
        "behavioral_score",
        "entry_price",
        "current_price",
        "size_usd",
        "fees_usd",
        "slippage_usd",
        "pnl_unrealized_usd",
        "pnl_realized_usd",
        "max_drawdown_usd",
        "raw_payload_json",
    ]


def _insert_ledger_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = _ledger_insert_columns()
    conn.executemany(
        f"INSERT INTO {TABLE_NAME} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [tuple(row.get(column) for column in columns) for row in rows],
    )
    return len(rows)


def _forward_signal_rows(rows: list[dict[str, Any]], event_type: str = "forward_paper_trade") -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        action = payload.get("action")
        if action not in {"entry", "exit"}:
            continue
        signal = dict(row)
        signal["event_type"] = event_type
        stable_id = _forward_idempotency_id(row, payload)
        signal["raw_payload_json"] = json.dumps({**payload, "event_type": event_type, "idempotency_trade_id": stable_id}, sort_keys=True)
        signals.append(signal)
    return signals


def _forward_open_positions_detail(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current: dict[str, Any] | None = None
    for row in rows:
        try:
            payload = json.loads(row.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        action = payload.get("action")
        price = _as_float(row.get("current_price"))
        if action == "entry":
            current = {
                "symbol": row.get("symbol"),
                "entry_price": _as_float(row.get("entry_price") or row.get("current_price")),
                "last_price": price,
                "size_usd": _as_float(row.get("size_usd")),
                "entry_score": _as_float(row.get("aster_score")),
                "entry_index": _as_int(payload.get("trade_index")),
                "last_index": _as_int(payload.get("trade_index")),
                "peak_price": _as_float(payload.get("peak_price") or price),
                "trailing_active": bool(payload.get("trailing_active")),
                "pnl_unrealized_usd": _as_float(row.get("pnl_unrealized_usd")),
            }
        elif current and action == "mark_to_market":
            current.update(
                {
                    "last_price": price,
                    "last_index": _as_int(payload.get("trade_index")),
                    "peak_price": _as_float(payload.get("peak_price") or current.get("peak_price") or price),
                    "trailing_active": bool(payload.get("trailing_active")),
                    "pnl_unrealized_usd": _as_float(row.get("pnl_unrealized_usd")),
                }
            )
        elif current and action == "exit":
            current = None
    if not current:
        return []
    size = _as_float(current.get("size_usd"))
    current["entry_price"] = round(_as_float(current.get("entry_price")), 12)
    current["last_price"] = round(_as_float(current.get("last_price")), 12)
    current["size_usd"] = round(size, 6)
    current["entry_score"] = round(_as_float(current.get("entry_score")), 6)
    current["trades_open"] = max(0, _as_int(current.get("last_index")) - _as_int(current.get("entry_index")))
    current["pnl_unrealized_usd"] = round(_as_float(current.get("pnl_unrealized_usd")), 6)
    current["pnl_unrealized_pct"] = round(_as_float(current.get("pnl_unrealized_usd")) / size * 100, 6) if size > 0 else None
    return [current]


def _forward_idempotency_id(row: dict[str, Any], payload: dict[str, Any]) -> str:
    trade_id = str(payload.get("idempotency_trade_id") or payload.get("trade_id") or "").strip()
    if trade_id:
        return trade_id
    seed = {
        "symbol": str(row.get("symbol") or "").upper(),
        "action": payload.get("action"),
        "side": payload.get("side"),
        "trade_index": payload.get("trade_index"),
        "trade_time": payload.get("trade_time"),
        "entry_price": row.get("entry_price"),
        "current_price": row.get("current_price"),
        "state": row.get("state"),
    }
    return hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]


def _existing_forward_trade_keys(conn: sqlite3.Connection, symbols: list[str], event_type: str = "forward_paper_trade") -> set[tuple[str, str, str]]:
    if not symbols or not _table_exists(conn):
        return set()
    placeholders = ",".join("?" for _ in symbols)
    rows = conn.execute(
        f"SELECT symbol, raw_payload_json FROM {TABLE_NAME} WHERE event_type = ? AND UPPER(symbol) IN ({placeholders})",
        [event_type, *symbols],
    ).fetchall()
    keys: set[tuple[str, str, str]] = set()
    for row in rows:
        try:
            payload = json.loads(row["raw_payload_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        action = str(payload.get("action") or "")
        trade_id = _forward_idempotency_id(dict(row), payload)
        if action and trade_id:
            keys.add((str(row["symbol"] or "").upper(), action, trade_id))
    return keys


def _dedupe_forward_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]], symbols: list[str], event_type: str = "forward_paper_trade") -> list[dict[str, Any]]:
    existing = _existing_forward_trade_keys(conn, symbols, event_type)
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        try:
            payload = json.loads(row.get("raw_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        stable_id = _forward_idempotency_id(row, payload)
        key = (
            str(row.get("symbol") or "").upper(),
            str(payload.get("action") or ""),
            stable_id,
        )
        if not all(key) or key in existing or key in seen:
            continue
        payload["idempotency_trade_id"] = stable_id
        row["raw_payload_json"] = json.dumps(payload, sort_keys=True)
        seen.add(key)
        unique.append(row)
    return unique


def get_aster_paper_trading_forward_monitor_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 200,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, EXTENDED_BACKTEST_SYMBOLS[:8])[:8]
    safe_events = max(20, min(_as_int(forward_window_trades, 200), 1_000))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 10))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    scan_at = _now()
    if not dry_run and confirm != FORWARD_PAPER_TRADE_CONFIRM:
        return {"ok": False, "dry_run": False, "forward_status": "blocked", "blockers": ["confirm_CONFIRM_FORWARD_PAPER_TRADE_required"], "would_write": False, "writes_performed": 0, **disabled}

    symbol_reports: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    all_signals: list[dict[str, Any]] = []
    open_positions: list[dict[str, Any]] = []
    closed_pnls: list[float] = []
    total_pnl = 0.0

    for index, symbol in enumerate(clean_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        run_id = f"forward-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{symbol}"
        rows, report = _replay_trades(
            fetched.get("trades") or [],
            run_id,
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=75.0,
            min_window_volume_usd=1_000.0,
            stop_loss_pct=-25.0,
            take_profit_pct=15.0,
            trailing_stop_activation_pct=10.0,
            trailing_stop_distance_pct=5.0,
            max_holding_trades=600,
            max_holding_seconds=None,
        )
        diag = _replay_trade_diagnostics(rows)
        signals = _forward_signal_rows(rows)
        symbol_open = _forward_open_positions_detail(rows)
        all_signals.extend(signals)
        open_positions.extend(symbol_open)
        closed = diag.get("closed_trades") or []
        closed_pnls.extend(_as_float(row.get("pnl_realized_usd")) for row in closed)
        total_pnl += _as_float(report.get("pnl_total_usd"))
        symbol_reports[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(fetched.get("trades") or []),
            "run_id": run_id,
            "entries": report.get("simulated_trade_count"),
            "closed_trades": report.get("closed_trade_count"),
            "win_rate": report.get("win_rate"),
            "pnl_total_usd": report.get("pnl_total_usd"),
            "max_drawdown_usd": report.get("max_drawdown_usd"),
            "open_positions": symbol_open,
            "signals_count": len(signals),
        }

    failed_ratio = len(failed_symbols) / max(1, len(clean_symbols))
    health_status = "api_degraded" if failed_ratio > 0.5 else ("active" if all_signals or open_positions else "no_signals")
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    rows_to_insert = all_signals
    session_run_ids = sorted({str(row.get("run_id") or "") for row in rows_to_insert if row.get("run_id")})
    inserted = 0
    deduped = 0
    if not dry_run:
        with _connect() as conn:
            if not _table_exists(conn):
                return {"ok": False, "dry_run": False, "forward_status": "blocked", "blockers": ["paper_trading_ledger_table_missing_create_first"], "would_write": False, "writes_performed": 0, **disabled}
            unique_rows = _dedupe_forward_rows(conn, rows_to_insert, clean_symbols)
            deduped = len(rows_to_insert) - len(unique_rows)
            inserted = _insert_ledger_rows(conn, unique_rows)
            conn.commit()

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "forward_status": "ready_dry_run_no_insert" if dry_run else "inserted",
        "health_status": health_status,
        "last_scan_at": scan_at,
        "symbols": clean_symbols,
        "locked_params": {
            "max_holding_trades": 600,
            "min_aster_score": 75.0,
            "min_window_volume_usd": 1_000.0,
            "stop_loss_pct": -25.0,
            "take_profit_pct": 15.0,
            "trailing_stop_activation_pct": 10.0,
            "trailing_stop_distance_pct": 5.0,
            "forward_window_trades": safe_events,
        },
        "symbol_reports": symbol_reports,
        "open_positions": open_positions,
        "recent_signals": [
            {
                "symbol": row.get("symbol"),
                "state": row.get("state"),
                "decision_reason": row.get("decision_reason"),
                "aster_score": row.get("aster_score"),
                "current_price": row.get("current_price"),
                "pnl_realized_usd": row.get("pnl_realized_usd"),
            }
            for row in all_signals[-20:]
        ],
        "forward_portfolio_pnl": round(total_pnl, 6),
        "win_rate_forward": round(wins / len(closed_pnls), 6) if closed_pnls else None,
        "failed_symbols": failed_symbols,
        "would_insert_rows": 0 if not dry_run else len(rows_to_insert),
        "rows_inserted": inserted,
        "dedupe_keys_used": ["event_type", "symbol", "action", "trade_id_in_raw_payload_json"],
        "deduped_rows": deduped,
        "would_write": not dry_run,
        "writes_performed": inserted,
        **disabled,
    }


def _optimized_long_profiles() -> dict[str, dict[str, Any]]:
    return {
        "INJUSDT": {
            "strategy_id": "inj_long_15m_75_3k_sl6_tp12",
            "min_aster_score": 75.0,
            "min_window_volume_usd": 3_000.0,
            "stop_loss_pct": -6.0,
            "take_profit_pct": 12.0,
            "trailing_stop_activation_pct": 6.0,
            "trailing_stop_distance_pct": 3.0,
            "max_holding_trades": 600,
        },
        "NEARUSDT": {
            "strategy_id": "near_long_15m_70_10k_sl6_tp12",
            "min_aster_score": 70.0,
            "min_window_volume_usd": 10_000.0,
            "stop_loss_pct": -6.0,
            "take_profit_pct": 12.0,
            "trailing_stop_activation_pct": 6.0,
            "trailing_stop_distance_pct": 3.0,
            "max_holding_trades": 600,
        },
        "TIAUSDT": {
            "strategy_id": "tia_long_1h_80_3k_sl6_tp12",
            "min_aster_score": 80.0,
            "min_window_volume_usd": 3_000.0,
            "stop_loss_pct": -6.0,
            "take_profit_pct": 12.0,
            "trailing_stop_activation_pct": 6.0,
            "trailing_stop_distance_pct": 3.0,
            "max_holding_trades": 600,
        },
        "JUPUSDT": {
            "strategy_id": "jup_long_1h_75_5k_sl6_tp12",
            "min_aster_score": 75.0,
            "min_window_volume_usd": 5_000.0,
            "stop_loss_pct": -6.0,
            "take_profit_pct": 12.0,
            "trailing_stop_activation_pct": 6.0,
            "trailing_stop_distance_pct": 3.0,
            "max_holding_trades": 600,
        },
        "BOMEUSDT": {
            "strategy_id": "bome_long_1h_80_5k_sl6_tp12",
            "min_aster_score": 80.0,
            "min_window_volume_usd": 5_000.0,
            "stop_loss_pct": -6.0,
            "take_profit_pct": 12.0,
            "trailing_stop_activation_pct": 6.0,
            "trailing_stop_distance_pct": 3.0,
            "max_holding_trades": 600,
        },
    }


def _parse_utc_hours(value: str | list[int] | tuple[int, ...] | None) -> set[int] | None:
    if value is None:
        return None
    raw_items = value if isinstance(value, (list, tuple)) else str(value).replace(";", ",").split(",")
    hours: set[int] = set()
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        if "-" in text:
            left, right = text.split("-", 1)
            start = max(0, min(23, int(float(left))))
            end = max(0, min(23, int(float(right))))
            if start <= end:
                hours.update(range(start, end + 1))
            else:
                hours.update(range(start, 24))
                hours.update(range(0, end + 1))
            continue
        hours.add(max(0, min(23, int(float(text)))))
    return hours or None


def _trade_utc_hour(trade_time: Any) -> int | None:
    seconds = _trade_time_seconds(trade_time)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).hour
    except (OSError, OverflowError, ValueError):
        return None


def _profit_factor_from_pnls(pnls: list[float]) -> float | None:
    gains = sum(pnl for pnl in pnls if pnl > 0)
    losses = abs(sum(pnl for pnl in pnls if pnl < 0))
    if losses <= 0:
        return round(gains, 6) if gains > 0 else None
    return round(gains / losses, 6)


def get_aster_optimized_long_regime_diagnostic_preview(
    min_closed_trades_per_hour: int = 2,
    dry_run: bool = True,
) -> dict[str, Any]:
    disabled = _disabled()
    safe_min = max(1, min(_as_int(min_closed_trades_per_hour, 2), 20))
    with _connect() as conn:
        if not _table_exists(conn):
            return {"ok": False, "dry_run": dry_run, "diagnostic_status": "blocked", "blockers": ["paper_trading_ledger_table_missing"], "would_write": False, "writes_performed": 0, **disabled}
        rows = conn.execute(
            f"""
            SELECT * FROM {TABLE_NAME}
            WHERE event_type IN (?, ?)
            ORDER BY id ASC
            """,
            [OPTIMIZED_LONG_REPLAY_EVENT_TYPE, OPTIMIZED_LONG_STATEFUL_EVENT_TYPE],
        ).fetchall()

    open_by_symbol: dict[str, dict[str, Any]] = {}
    closed: list[dict[str, Any]] = []
    for row in rows:
        payload = _stateful_payload(row)
        action = str(payload.get("action") or "")
        symbol = str(row["symbol"] or "").upper()
        if action == "entry":
            entry_hour = _trade_utc_hour(payload.get("trade_time"))
            open_by_symbol[symbol] = {
                "symbol": symbol,
                "entry_hour_utc": entry_hour,
                "entry_time": payload.get("trade_time"),
                "entry_price": _as_float(row["entry_price"] or row["current_price"]),
                "entry_score": _as_float(row["aster_score"]),
                "size_usd": _as_float(row["size_usd"]),
                "run_id": row["run_id"],
            }
        elif action == "exit":
            entry = open_by_symbol.pop(symbol, None)
            pnl = _as_float(row["pnl_realized_usd"])
            closed.append({
                "symbol": symbol,
                "entry_hour_utc": (entry or {}).get("entry_hour_utc"),
                "exit_hour_utc": _trade_utc_hour(payload.get("trade_time")),
                "pnl_realized_usd": round(pnl, 6),
                "exit_reason": row["decision_reason"],
                "entry_score": (entry or {}).get("entry_score"),
                "run_id": row["run_id"],
            })

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        pnls = [_as_float(item.get("pnl_realized_usd")) for item in items]
        wins = sum(1 for pnl in pnls if pnl > 0)
        return {
            "closed_trades": len(items),
            "win_rate": round(wins / len(items), 6) if items else None,
            "profit_factor": _profit_factor_from_pnls(pnls),
            "net_pnl_usd": round(sum(pnls), 6),
            "avg_pnl_usd": round(sum(pnls) / len(pnls), 6) if pnls else None,
        }

    by_hour: dict[str, list[dict[str, Any]]] = {}
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for trade in closed:
        hour = trade.get("entry_hour_utc")
        by_hour.setdefault("unknown" if hour is None else f"{int(hour):02d}", []).append(trade)
        by_symbol.setdefault(str(trade.get("symbol") or "UNKNOWN"), []).append(trade)

    hourly = {hour: summarize(items) for hour, items in sorted(by_hour.items())}
    symbol_summary = {symbol: summarize(items) for symbol, items in sorted(by_symbol.items())}
    eligible_hours = [
        int(hour)
        for hour, stats in hourly.items()
        if hour != "unknown"
        and _as_int(stats.get("closed_trades")) >= safe_min
        and _as_float(stats.get("net_pnl_usd")) > 0
        and _as_float(stats.get("win_rate")) >= 0.55
        and (_as_float(stats.get("profit_factor")) >= 1.3 or stats.get("profit_factor") is None)
    ]
    global_stats = summarize(closed)
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "diagnostic_status": "ready" if closed else "insufficient_closed_trades",
        "strategy_family": "optimized_long_breakout_forward",
        "global_stats": global_stats,
        "hourly_entry_stats_utc": hourly,
        "symbol_stats": symbol_summary,
        "closed_trades_preview": closed[-20:],
        "open_positions_count": len(open_by_symbol),
        "suggested_allowed_entry_utc_hours": sorted(eligible_hours),
        "suggestion_status": "usable" if eligible_hours else "insufficient_sample_or_no_profitable_hour_cluster",
        "min_closed_trades_per_hour": safe_min,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


OPTIMIZED_LONG_REPLAY_EVENT_TYPE = "forward_optimized_long_replay"
OPTIMIZED_LONG_STATEFUL_EVENT_TYPE = "forward_optimized_long_stateful"


def _safe_event_type(value: Any, default: str) -> str:
    text = str(value or "").strip().lower()
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text)
    return safe[:80] or default


def _optimized_long_event_types(event_type: str | None = None) -> tuple[str, ...]:
    if event_type:
        return (_safe_event_type(event_type, OPTIMIZED_LONG_STATEFUL_EVENT_TYPE),)
    return (OPTIMIZED_LONG_REPLAY_EVENT_TYPE, OPTIMIZED_LONG_STATEFUL_EVENT_TYPE)


def _load_optimized_long_open_positions(
    conn: sqlite3.Connection,
    symbols: list[str],
    event_type: str | None = None,
) -> dict[str, dict[str, Any]]:
    if not symbols or not _table_exists(conn):
        return {}
    event_types = _optimized_long_event_types(event_type)
    event_placeholders = ",".join("?" for _ in event_types)
    symbol_placeholders = ",".join("?" for _ in symbols)
    rows = conn.execute(
        f"SELECT * FROM {TABLE_NAME} WHERE event_type IN ({event_placeholders}) AND UPPER(symbol) IN ({symbol_placeholders}) ORDER BY id ASC",
        [*event_types, *symbols],
    ).fetchall()
    positions: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row["symbol"] or "").upper()
        payload = _stateful_payload(row)
        action = str(payload.get("action") or "")
        state = str(row["state"] or "")
        if action == "exit" or state == "executing_exit":
            positions.pop(symbol, None)
            continue
        if action not in {"entry", "mark_to_market"} and state not in {"executing_entry", "monitoring"}:
            continue
        previous = positions.get(symbol, {})
        entry_price = _as_float(row["entry_price"]) or _as_float(previous.get("entry_price")) or _as_float(payload.get("entry_price"))
        current_price = _as_float(row["current_price"]) or _as_float(previous.get("current_price")) or entry_price
        trade_id = payload.get("trade_id") or payload.get("idempotency_trade_id") or previous.get("last_trade_id")
        trade_index = _as_int(payload.get("trade_index"), _as_int(previous.get("last_known_trade_index"), -1))
        peak_price = max(_as_float(previous.get("peak_price") or entry_price), _as_float(payload.get("peak_price") or current_price or entry_price))
        positions[symbol] = {
            "symbol": symbol,
            "side": "long",
            "strategy_id": payload.get("strategy_id") or previous.get("strategy_id"),
            "entry_price": entry_price,
            "current_price": current_price,
            "size_usd": _as_float(row["size_usd"]) or _as_float(previous.get("size_usd")),
            "entry_trade_id": previous.get("entry_trade_id") or trade_id,
            "entry_created_at": previous.get("entry_created_at") or row["created_at"],
            "last_trade_id": trade_id,
            "last_processed_trade_id": payload.get("last_processed_trade_id") or trade_id,
            "last_known_trade_index": trade_index,
            "peak_price": peak_price,
            "entry_score": _as_float(row["aster_score"]) or _as_float(previous.get("entry_score")),
            "trades_held": _as_int(payload.get("trades_held"), _as_int(previous.get("trades_held"), 0)),
            "pnl_unrealized_usd": _as_float(row["pnl_unrealized_usd"]) if action == "mark_to_market" or state == "monitoring" else _as_float(previous.get("pnl_unrealized_usd")),
        }
    return positions


def _optimized_long_last_processed_trade_ids(
    conn: sqlite3.Connection,
    symbols: list[str],
    event_type: str | None = None,
) -> dict[str, str]:
    if not symbols or not _table_exists(conn):
        return {}
    event_types = _optimized_long_event_types(event_type)
    event_placeholders = ",".join("?" for _ in event_types)
    symbol_placeholders = ",".join("?" for _ in symbols)
    rows = conn.execute(
        f"SELECT symbol, raw_payload_json FROM {TABLE_NAME} WHERE event_type IN ({event_placeholders}) AND UPPER(symbol) IN ({symbol_placeholders}) ORDER BY id ASC",
        [*event_types, *symbols],
    ).fetchall()
    last_by_symbol: dict[str, str] = {}
    for row in rows:
        symbol = str(row["symbol"] or "").upper()
        payload = _stateful_payload(row)
        trade_id = str(payload.get("last_processed_trade_id") or payload.get("idempotency_trade_id") or payload.get("trade_id") or "")
        if symbol and trade_id and (symbol not in last_by_symbol or _trade_id_lte(last_by_symbol[symbol], trade_id)):
            last_by_symbol[symbol] = trade_id
    return last_by_symbol


def get_aster_optimized_long_forward_monitor_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    disabled = _disabled()
    profiles = _optimized_long_profiles()
    clean_symbols = [symbol for symbol in _parse_symbols(symbols, list(profiles))[:5] if symbol in profiles]
    if not clean_symbols:
        clean_symbols = list(profiles)
    safe_events = max(20, min(_as_int(forward_window_trades, 800), 1_000))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 10))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    scan_at = _now()
    event_type = "forward_optimized_long_replay"
    if not dry_run and confirm != FORWARD_PAPER_TRADE_CONFIRM:
        return {"ok": False, "dry_run": False, "forward_long_status": "blocked", "blockers": ["confirm_CONFIRM_FORWARD_PAPER_TRADE_required"], "would_write": False, "writes_performed": 0, **disabled}

    symbol_reports: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    all_signals: list[dict[str, Any]] = []
    open_positions: list[dict[str, Any]] = []
    closed_pnls: list[float] = []
    total_pnl = 0.0

    for index, symbol in enumerate(clean_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        profile = profiles[symbol]
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        run_id = f"forward-long-opt-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{symbol}"
        rows, report = _replay_trades(
            fetched.get("trades") or [],
            run_id,
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=_as_float(profile.get("min_aster_score")),
            min_window_volume_usd=_as_float(profile.get("min_window_volume_usd")),
            stop_loss_pct=_as_float(profile.get("stop_loss_pct")),
            take_profit_pct=_as_float(profile.get("take_profit_pct")),
            trailing_stop_activation_pct=_as_float(profile.get("trailing_stop_activation_pct")),
            trailing_stop_distance_pct=_as_float(profile.get("trailing_stop_distance_pct")),
            max_holding_trades=_as_int(profile.get("max_holding_trades"), 600),
        )
        signals = _forward_signal_rows(rows, event_type=event_type)
        enriched_signals: list[dict[str, Any]] = []
        for row in signals:
            try:
                payload = json.loads(row.get("raw_payload_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            row = dict(row)
            row["raw_payload_json"] = json.dumps(
                {
                    **payload,
                    "strategy_id": profile.get("strategy_id"),
                    "side": "long",
                    "optimized_forward_profile": True,
                    "profile_params": profile,
                },
                sort_keys=True,
            )
            enriched_signals.append(row)
        diag = _replay_trade_diagnostics(rows)
        symbol_open = _forward_open_positions_detail(rows)
        for position in symbol_open:
            position["strategy_id"] = profile.get("strategy_id")
            position["side"] = "long"
        all_signals.extend(enriched_signals)
        open_positions.extend(symbol_open)
        closed = diag.get("closed_trades") or []
        closed_pnls.extend(_as_float(row.get("pnl_realized_usd")) for row in closed)
        total_pnl += _as_float(report.get("pnl_total_usd"))
        symbol_reports[symbol] = {
            "strategy_id": profile.get("strategy_id"),
            "market_type": fetched.get("market_type"),
            "fetched_events": len(fetched.get("trades") or []),
            "run_id": run_id,
            "locked_params": profile,
            "entries": report.get("simulated_trade_count"),
            "closed_trades": report.get("closed_trade_count"),
            "win_rate": report.get("win_rate"),
            "pnl_total_usd": report.get("pnl_total_usd"),
            "max_drawdown_usd": report.get("max_drawdown_usd"),
            "open_positions": symbol_open,
            "signals_count": len(enriched_signals),
        }

    failed_ratio = len(failed_symbols) / max(1, len(clean_symbols))
    health_status = "api_degraded" if failed_ratio > 0.5 else ("active" if all_signals or open_positions else "no_signals")
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    inserted = 0
    deduped = 0
    if not dry_run:
        with _connect() as conn:
            if not _table_exists(conn):
                return {"ok": False, "dry_run": False, "forward_long_status": "blocked", "blockers": ["paper_trading_ledger_table_missing_create_first"], "would_write": False, "writes_performed": 0, **disabled}
            unique_rows = _dedupe_forward_rows(conn, all_signals, clean_symbols, event_type=event_type)
            deduped = len(all_signals) - len(unique_rows)
            inserted = _insert_ledger_rows(conn, unique_rows)
            conn.commit()

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "forward_long_status": "ready_dry_run_no_insert" if dry_run else "inserted",
        "health_status": health_status,
        "last_scan_at": scan_at,
        "symbols": clean_symbols,
        "strategy_family": "optimized_long_breakout_forward",
        "event_type": event_type,
        "symbol_reports": symbol_reports,
        "open_positions": open_positions,
        "recent_signals": [
            {
                "symbol": row.get("symbol"),
                "state": row.get("state"),
                "decision_reason": row.get("decision_reason"),
                "aster_score": row.get("aster_score"),
                "current_price": row.get("current_price"),
                "pnl_realized_usd": row.get("pnl_realized_usd"),
            }
            for row in all_signals[-20:]
        ],
        "forward_portfolio_pnl": round(total_pnl, 6),
        "win_rate_forward": round(wins / len(closed_pnls), 6) if closed_pnls else None,
        "failed_symbols": failed_symbols,
        "would_insert_rows": 0 if not dry_run else len(all_signals),
        "rows_inserted": inserted,
        "deduped_rows": deduped,
        "dedupe_keys_used": ["event_type", "symbol", "action", "trade_id_in_raw_payload_json"],
        "would_write": not dry_run,
        "writes_performed": inserted,
        **disabled,
    }


def get_aster_optimized_long_stateful_monitor(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
    allowed_entry_utc_hours: str | list[int] | None = None,
    event_type_override: str | None = None,
    max_holding_trades_override: int | None = None,
    max_holding_trades_by_symbol: dict[str, int] | None = None,
) -> dict[str, Any]:
    disabled = _disabled()
    profiles = _optimized_long_profiles()
    clean_symbols = [symbol for symbol in _parse_symbols(symbols, list(profiles))[:5] if symbol in profiles] or list(profiles)
    safe_events = max(20, min(_as_int(forward_window_trades, 800), 1_000))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 10))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    allowed_hours = _parse_utc_hours(allowed_entry_utc_hours)
    effective_event_type = _safe_event_type(event_type_override, OPTIMIZED_LONG_STATEFUL_EVENT_TYPE)
    safe_max_holding_override = None
    if max_holding_trades_override is not None:
        safe_max_holding_override = max(20, min(_as_int(max_holding_trades_override, 600), 2_000))
    safe_max_holding_by_symbol = {
        str(symbol or "").strip().upper(): max(20, min(_as_int(value, 600), 2_000))
        for symbol, value in (max_holding_trades_by_symbol or {}).items()
        if str(symbol or "").strip()
    }
    session_run_id = f"long-stateful-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{uuid.uuid4().hex[:8]}"
    if not dry_run and confirm != FORWARD_PAPER_TRADE_CONFIRM:
        return {"ok": False, "dry_run": False, "stateful_long_status": "blocked", "blockers": ["confirm_CONFIRM_FORWARD_PAPER_TRADE_required"], "would_write": False, "writes_performed": 0, **disabled}

    with _connect() as conn:
        table_exists = _table_exists(conn)
        open_positions = _load_optimized_long_open_positions(conn, clean_symbols, event_type=effective_event_type) if table_exists else {}
        last_processed_by_symbol = _optimized_long_last_processed_trade_ids(conn, clean_symbols, event_type=effective_event_type) if table_exists else {}

    rows_to_insert: list[dict[str, Any]] = []
    active_positions = dict(open_positions)
    failed_symbols: list[dict[str, Any]] = []
    symbol_reports: dict[str, Any] = {}
    closed_pnls: list[float] = []
    realized_pnl = 0.0
    scan_at = _now()

    for symbol_index, symbol in enumerate(clean_symbols):
        if symbol_index > 0 and safe_delay:
            time.sleep(safe_delay)
        profile = dict(profiles[symbol])
        if safe_max_holding_override is not None:
            profile["max_holding_trades"] = safe_max_holding_override
            profile["profile_override_reason"] = "strategy_max_holding_trades_override"
        if symbol in safe_max_holding_by_symbol:
            profile["max_holding_trades"] = safe_max_holding_by_symbol[symbol]
            profile["profile_override_reason"] = "strategy_symbol_max_holding_trades_override"
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        position = active_positions.get(symbol)
        last_processed = str((position or {}).get("last_processed_trade_id") or last_processed_by_symbol.get(symbol) or "")
        indexed_new_trades = [
            (idx, trade)
            for idx, trade in enumerate(trades)
            if not _trade_id_lte(trade.get("id"), last_processed)
        ]
        entries = 0
        exits = 0
        marks = 0
        latest_mark: dict[str, Any] | None = None

        for idx, trade in indexed_new_trades:
            price = _trade_price(trade)
            if price <= 0:
                continue
            trade_id = str(trade.get("id") or "")
            window = trades[max(0, idx - max(5, min(_as_int(window_size, 20), 100)) + 1) : idx + 1]
            score = _aster_score_proxy(window)
            payload_base = {
                "trade_index": idx,
                "trade_id": trade_id,
                "last_processed_trade_id": trade_id,
                "trade_time": trade.get("time"),
                "session_run_id": session_run_id,
                "strategy_id": profile.get("strategy_id"),
                "side": "long",
                "source": "optimized_long_stateful_monitor",
                "strategy_namespace_event_type": effective_event_type,
                "profile_params": profile,
            }
            position = active_positions.get(symbol)
            if position:
                entry = _as_float(position.get("entry_price"))
                size = _as_float(position.get("size_usd"))
                peak_price = max(_as_float(position.get("peak_price") or entry), price)
                pnl_unrealized = ((price - entry) / entry * size) if entry > 0 else 0.0
                should_exit, exit_reason = should_exit_position(
                    entry,
                    price,
                    _as_float(profile.get("stop_loss_pct")),
                    _as_float(profile.get("take_profit_pct")),
                )
                trailing_active = entry > 0 and peak_price / entry >= 1 + max(0.0, _as_float(profile.get("trailing_stop_activation_pct"))) / 100
                if not should_exit and trailing_active and price <= peak_price * (1 - max(0.0, _as_float(profile.get("trailing_stop_distance_pct"))) / 100):
                    should_exit = True
                    exit_reason = "trailing_stop_triggered"
                entry_trade_id = str(position.get("entry_trade_id") or "")
                entry_indexes = [trade_idx for trade_idx, item in enumerate(trades) if str(item.get("id") or "") == entry_trade_id]
                trades_held = max(0, idx - entry_indexes[0]) if entry_indexes else _as_int(position.get("trades_held"), 0) + 1
                if not should_exit and trades_held >= _as_int(profile.get("max_holding_trades"), 600):
                    should_exit = True
                    exit_reason = "time_stop_triggered"
                if should_exit:
                    fees = size * fee_bps / 10_000
                    slippage = size * slippage_bps / 10_000
                    pnl_realized = pnl_unrealized - fees - slippage
                    rows_to_insert.append(
                        _stateful_row(
                            session_run_id,
                            symbol,
                            effective_event_type,
                            "executing_exit",
                            exit_reason,
                            score,
                            price,
                            size,
                            0.0,
                            pnl_realized,
                            {**payload_base, "action": "exit", "entry_price": entry, "peak_price": peak_price, "trades_held": trades_held},
                            fee_bps=fee_bps,
                            slippage_bps=slippage_bps,
                        )
                    )
                    active_positions.pop(symbol, None)
                    closed_pnls.append(pnl_realized)
                    realized_pnl += pnl_realized
                    exits += 1
                    latest_mark = None
                    continue
                position.update({
                    "current_price": price,
                    "last_trade_id": trade_id,
                    "last_processed_trade_id": trade_id,
                    "last_known_trade_index": idx,
                    "peak_price": peak_price,
                    "trades_held": trades_held,
                    "pnl_unrealized_usd": round(pnl_unrealized, 6),
                })
                latest_mark = _stateful_row(
                    session_run_id,
                    symbol,
                    effective_event_type,
                    "monitoring",
                    "mark_to_market_holding",
                    score,
                    price,
                    size,
                    pnl_unrealized,
                    0.0,
                    {**payload_base, "action": "mark_to_market", "entry_price": entry, "peak_price": peak_price, "trailing_active": trailing_active, "trades_held": trades_held},
                )
                continue

            enter = should_enter_position(
                _as_float(score.get("aster_score")),
                None,
                _as_float(score.get("window_volume_usd")),
                min_aster_score=_as_float(profile.get("min_aster_score")),
                min_volume_usd=_as_float(profile.get("min_window_volume_usd")),
            )
            entry_hour = _trade_utc_hour(trade.get("time"))
            if enter and allowed_hours is not None and entry_hour not in allowed_hours:
                enter = False
            if enter:
                size = calculate_position_size(wallet_balance_usd, 5.0, _as_float(score.get("aster_score")))
                fees = size * fee_bps / 10_000
                slippage = size * slippage_bps / 10_000
                rows_to_insert.append(
                    _stateful_row(
                        session_run_id,
                        symbol,
                        effective_event_type,
                        "executing_entry",
                        "entry_rules_passed",
                        score,
                        price,
                        size,
                        -fees - slippage,
                        0.0,
                        {**payload_base, "action": "entry", "entry_price": price, "peak_price": price, "trades_held": 0, "entry_hour_utc": entry_hour, "allowed_entry_utc_hours": sorted(allowed_hours) if allowed_hours is not None else None},
                        fee_bps=fee_bps,
                        slippage_bps=slippage_bps,
                    )
                )
                active_positions[symbol] = {
                    "symbol": symbol,
                    "side": "long",
                    "strategy_id": profile.get("strategy_id"),
                    "entry_price": price,
                    "current_price": price,
                    "size_usd": size,
                    "entry_trade_id": trade_id,
                    "last_trade_id": trade_id,
                    "last_processed_trade_id": trade_id,
                    "last_known_trade_index": idx,
                    "peak_price": price,
                    "entry_score": _as_float(score.get("aster_score")),
                    "trades_held": 0,
                }
                entries += 1
        if latest_mark is not None:
            rows_to_insert.append(latest_mark)
            marks += 1
        active = active_positions.get(symbol)
        symbol_reports[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(trades),
            "new_trades_replayed": len(indexed_new_trades),
            "last_processed_trade_id_before_cycle": last_processed or None,
            "entries": entries,
            "exits": exits,
            "mark_to_market_rows": marks,
            "has_active_position": bool(active),
            "active_position": active,
            "entry_hour_filter_active": allowed_hours is not None,
        }

    inserted = 0
    deduped = 0
    if not dry_run:
        with _connect() as conn:
            if not _table_exists(conn):
                return {"ok": False, "dry_run": False, "stateful_long_status": "blocked", "blockers": ["paper_trading_ledger_table_missing_create_first"], "would_write": False, "writes_performed": 0, **disabled}
            unique_rows = _dedupe_forward_rows(conn, rows_to_insert, clean_symbols, event_type=effective_event_type)
            deduped = len(rows_to_insert) - len(unique_rows)
            inserted = _insert_ledger_rows(conn, unique_rows)
            conn.commit()

    failed_ratio = len(failed_symbols) / max(1, len(clean_symbols))
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "stateful_long_status": "ready_dry_run_no_insert" if dry_run else "inserted",
        "health_status": "api_degraded" if failed_ratio > 0.5 else "active",
        "last_scan_at": scan_at,
        "session_run_id": session_run_id,
        "symbols": clean_symbols,
        "event_type": effective_event_type,
        "strategy_namespace_event_type": effective_event_type,
        "max_holding_trades_override": safe_max_holding_override,
        "max_holding_trades_by_symbol": safe_max_holding_by_symbol,
        "allowed_entry_utc_hours": sorted(allowed_hours) if allowed_hours is not None else None,
        "loaded_open_positions": open_positions,
        "active_positions": list(active_positions.values()),
        "closed_in_session": len(closed_pnls),
        "realized_pnl_session": round(realized_pnl, 6),
        "session_win_rate": round(wins / len(closed_pnls), 6) if closed_pnls else None,
        "symbol_reports": symbol_reports,
        "failed_symbols": failed_symbols,
        "would_insert_rows": 0 if not dry_run else len(rows_to_insert),
        "rows_inserted": inserted,
        "deduped_rows": deduped,
        "dedupe_keys_used": ["event_type", "symbol", "action", "trade_id_in_raw_payload_json"],
        "would_write": not dry_run,
        "writes_performed": inserted,
        **disabled,
    }


def get_aster_paper_trading_forward_short_monitor_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 200,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["LABUSDT", "ORDIUSDT", "1000SATSUSDT", "PEPEUSDT"])[:4]
    safe_events = max(20, min(_as_int(forward_window_trades, 200), 1_000))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 10))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    scan_at = _now()
    if not dry_run and confirm != FORWARD_SHORT_PAPER_TRADE_CONFIRM:
        return {"ok": False, "dry_run": False, "forward_short_status": "blocked", "blockers": ["confirm_CONFIRM_FORWARD_SHORT_PAPER_TRADE_required"], "would_write": False, "writes_performed": 0, **disabled}

    symbol_reports: dict[str, Any] = {}
    failed_symbols: list[dict[str, Any]] = []
    all_signals: list[dict[str, Any]] = []
    open_short_positions: list[dict[str, Any]] = []
    closed_pnls: list[float] = []
    realized_pnl = 0.0

    for index, symbol in enumerate(clean_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        run_id = f"forward-short-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{symbol}"
        rows, report = _replay_trades_short(
            fetched.get("trades") or [],
            run_id,
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
            min_aster_score=75.0,
            min_window_volume_usd=1_000.0,
            stop_loss_pct=15.0,
            take_profit_pct=-25.0,
            trailing_stop_activation_pct=10.0,
            trailing_stop_distance_pct=5.0,
            max_holding_trades=600,
            max_holding_seconds=None,
        )
        diag = _short_replay_trade_diagnostics(rows, wallet_balance_usd)
        signals = _forward_signal_rows(rows, "forward_short_replay")
        symbol_open = _short_open_positions_detail(rows)
        all_signals.extend(signals)
        open_short_positions.extend(symbol_open)
        closed = diag.get("closed_trades") or []
        symbol_realized = sum(_as_float(row.get("pnl_realized_usd")) for row in closed)
        closed_pnls.extend(_as_float(row.get("pnl_realized_usd")) for row in closed)
        realized_pnl += symbol_realized
        symbol_reports[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(fetched.get("trades") or []),
            "run_id": run_id,
            "entries": report.get("simulated_trade_count"),
            "closed_trades": report.get("closed_trade_count"),
            "win_rate": report.get("win_rate"),
            "forward_pnl_usd": round(symbol_realized, 6),
            "pnl_total_with_open_usd": report.get("pnl_total_usd"),
            "max_drawdown_usd": report.get("max_drawdown_usd"),
            "open_short_positions": symbol_open,
            "signals_count": len(signals),
        }

    failed_ratio = len(failed_symbols) / max(1, len(clean_symbols))
    health_status = "api_degraded" if failed_ratio > 0.5 else ("active" if all_signals or open_short_positions else "no_signals")
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    inserted = 0
    deduped = 0
    if not dry_run:
        with _connect() as conn:
            if not _table_exists(conn):
                return {"ok": False, "dry_run": False, "forward_short_status": "blocked", "blockers": ["paper_trading_ledger_table_missing_create_first"], "would_write": False, "writes_performed": 0, **disabled}
            unique_rows = _dedupe_forward_rows(conn, all_signals, clean_symbols, "forward_short_replay")
            deduped = len(all_signals) - len(unique_rows)
            inserted = _insert_ledger_rows(conn, unique_rows)
            conn.commit()

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "forward_short_status": "ready_dry_run_no_insert" if dry_run else "inserted",
        "health_status": health_status,
        "last_scan_at": scan_at,
        "symbols": clean_symbols,
        "locked_params": {
            "side": "short",
            "max_holding_trades": 600,
            "min_aster_score": 75.0,
            "min_window_volume_usd": 1_000.0,
            "stop_loss_pct": 15.0,
            "take_profit_pct": -25.0,
            "trailing_stop_activation_pct": 10.0,
            "trailing_stop_distance_pct": 5.0,
            "forward_window_trades": safe_events,
        },
        "symbol_reports": symbol_reports,
        "open_short_positions": open_short_positions,
        "recent_signals": [
            {
                "symbol": row.get("symbol"),
                "state": row.get("state"),
                "decision_reason": row.get("decision_reason"),
                "aster_score": row.get("aster_score"),
                "current_price": row.get("current_price"),
                "pnl_realized_usd": row.get("pnl_realized_usd"),
            }
            for row in all_signals[-20:]
        ],
        "forward_pnl_usd": round(realized_pnl, 6),
        "win_rate_forward": round(wins / len(closed_pnls), 6) if closed_pnls else None,
        "failed_symbols": failed_symbols,
        "would_insert_rows": 0 if not dry_run else len(all_signals),
        "rows_inserted": inserted,
        "dedupe_keys_used": ["event_type", "symbol", "action", "trade_id_in_raw_payload_json"],
        "deduped_rows": deduped,
        "would_write": not dry_run,
        "writes_performed": inserted,
        **disabled,
    }


def _stateful_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    try:
        raw = row["raw_payload_json"] if isinstance(row, sqlite3.Row) else row.get("raw_payload_json")
        return json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _stateful_side(row: sqlite3.Row | dict[str, Any], payload: dict[str, Any]) -> str:
    event_type = str(row["event_type"] if isinstance(row, sqlite3.Row) else row.get("event_type") or "")
    if "short" in event_type or payload.get("side") == "short":
        return "short"
    return "long"


def _load_stateful_open_positions(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    if not _table_exists(conn):
        return {}
    event_types = (
        "forward_long_replay",
        "forward_short_replay",
        "forward_long_exit_pending",
        "forward_short_exit_pending",
        "forward_paper_trade",
        "forward_long_entry",
        "forward_short_entry",
        "forward_long_exit",
        "forward_short_exit",
    )
    placeholders = ",".join("?" for _ in event_types)
    rows = conn.execute(
        f"SELECT * FROM {TABLE_NAME} WHERE event_type IN ({placeholders}) ORDER BY id ASC",
        list(event_types),
    ).fetchall()
    positions: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row["symbol"] or "").upper()
        if not symbol:
            continue
        payload = _stateful_payload(row)
        action = str(payload.get("action") or "")
        state = str(row["state"] or "")
        event_type = str(row["event_type"] or "")
        if action == "exit" or state == "executing_exit" or event_type.endswith("_exit"):
            positions.pop(symbol, None)
            continue
        if action not in {"entry", "mark_to_market"} and state not in {"executing_entry", "monitoring"}:
            continue
        previous = positions.get(symbol, {})
        side = _stateful_side(row, payload)
        entry_price = _as_float(row["entry_price"]) or _as_float(previous.get("entry_price")) or _as_float(payload.get("entry_price"))
        current_price = _as_float(row["current_price"])
        size_usd = _as_float(row["size_usd"]) or _as_float(previous.get("size_usd"))
        trade_id = payload.get("trade_id") or payload.get("idempotency_trade_id") or previous.get("last_trade_id")
        trade_index = _as_int(payload.get("trade_index"), _as_int(previous.get("last_trade_index"), -1))
        peak_price = max(_as_float(previous.get("peak_price") or entry_price), _as_float(payload.get("peak_price") or current_price or entry_price))
        trough_price = min(
            _as_float(previous.get("trough_price") or entry_price) or entry_price,
            _as_float(payload.get("trough_price") or current_price or entry_price) or entry_price,
        )
        positions[symbol] = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "current_price": current_price,
            "size_usd": size_usd,
            "entry_trade_id": previous.get("entry_trade_id") or trade_id,
            "entry_created_at": previous.get("entry_created_at") or row["created_at"],
            "last_trade_id": trade_id,
            "last_processed_trade_id": payload.get("last_processed_trade_id") or trade_id,
            "last_known_trade_index": trade_index,
            "peak_price": peak_price,
            "trough_price": trough_price,
            "entry_score": _as_float(row["aster_score"]) or _as_float(previous.get("entry_score")),
        }
    return positions


def _stateful_seen_trade_keys(conn: sqlite3.Connection, symbols: list[str]) -> set[tuple[str, str]]:
    if not symbols or not _table_exists(conn):
        return set()
    event_types = ("forward_long_entry", "forward_short_entry", "forward_long_exit", "forward_short_exit")
    symbol_placeholders = ",".join("?" for _ in symbols)
    event_placeholders = ",".join("?" for _ in event_types)
    rows = conn.execute(
        f"SELECT symbol, raw_payload_json FROM {TABLE_NAME} WHERE event_type IN ({event_placeholders}) AND UPPER(symbol) IN ({symbol_placeholders})",
        [*event_types, *symbols],
    ).fetchall()
    keys: set[tuple[str, str]] = set()
    for row in rows:
        payload = _stateful_payload(row)
        trade_id = str(payload.get("trade_id") or payload.get("idempotency_trade_id") or "")
        symbol = str(row["symbol"] or "").upper()
        if symbol and trade_id:
            keys.add((symbol, trade_id))
    return keys


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _trade_id_sort_value(trade_id: Any) -> tuple[int, int | str]:
    text = str(trade_id or "").strip()
    if text.isdigit():
        return (1, int(text))
    return (0, text)


def _trade_id_lte(left: Any, right: Any) -> bool:
    if not str(left or "").strip() or not str(right or "").strip():
        return False
    return _trade_id_sort_value(left) <= _trade_id_sort_value(right)


def _filter_already_processed_events(trades: list[dict[str, Any]], last_processed_trade_id: Any) -> list[dict[str, Any]]:
    if not str(last_processed_trade_id or "").strip():
        return trades
    return [
        trade
        for trade in trades
        if not _trade_id_lte(trade.get("id"), last_processed_trade_id)
    ]


def _stateful_last_processed_trade_ids(conn: sqlite3.Connection, symbols: list[str]) -> dict[str, str]:
    if not symbols or not _table_exists(conn):
        return {}
    event_types = ("forward_long_entry", "forward_short_entry", "forward_long_exit", "forward_short_exit")
    symbol_placeholders = ",".join("?" for _ in symbols)
    event_placeholders = ",".join("?" for _ in event_types)
    rows = conn.execute(
        f"SELECT symbol, raw_payload_json FROM {TABLE_NAME} WHERE event_type IN ({event_placeholders}) AND UPPER(symbol) IN ({symbol_placeholders}) ORDER BY id ASC",
        [*event_types, *symbols],
    ).fetchall()
    last_by_symbol: dict[str, str] = {}
    for row in rows:
        symbol = str(row["symbol"] or "").upper()
        payload = _stateful_payload(row)
        trade_id = str(
            payload.get("last_processed_trade_id")
            or payload.get("idempotency_trade_id")
            or payload.get("trade_id")
            or ""
        )
        if symbol and trade_id and (
            symbol not in last_by_symbol or _trade_id_lte(last_by_symbol[symbol], trade_id)
        ):
            last_by_symbol[symbol] = trade_id
    return last_by_symbol


def _stateful_row(
    run_id: str,
    symbol: str,
    event_type: str,
    state: str,
    reason: str,
    score: dict[str, Any],
    price: float,
    size_usd: float,
    pnl_unrealized: float,
    pnl_realized: float,
    payload: dict[str, Any],
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
) -> dict[str, Any]:
    fees = size_usd * _as_float(fee_bps) / 10_000 if state in {"executing_entry", "executing_exit"} else 0.0
    slippage = size_usd * _as_float(slippage_bps) / 10_000 if state in {"executing_entry", "executing_exit"} else 0.0
    return {
        "run_id": run_id,
        "created_at": _now(),
        "symbol": symbol,
        "token_address": None,
        "event_type": event_type,
        "state": state,
        "decision_reason": reason,
        "aster_score": _as_float(score.get("aster_score")),
        "behavioral_score": None,
        "entry_price": price if state == "executing_entry" else None,
        "current_price": price,
        "size_usd": round(size_usd, 6),
        "fees_usd": round(fees, 6),
        "slippage_usd": round(slippage, 6),
        "pnl_unrealized_usd": round(pnl_unrealized, 6),
        "pnl_realized_usd": round(pnl_realized, 6),
        "max_drawdown_usd": 0.0,
        "raw_payload_json": json.dumps({**payload, "score_proxy": score}, sort_keys=True),
    }


def get_aster_paper_trading_stateful_session_monitor(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 200,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1_000.0,
    rate_limit_delay_ms: int = 300,
    min_aster_score: float = 75.0,
    min_window_volume_usd: float = 1_000.0,
    long_stop_loss_pct: float = -25.0,
    long_take_profit_pct: float = 15.0,
    short_stop_loss_pct: float = 15.0,
    short_take_profit_pct: float = -25.0,
    trailing_stop_activation_pct: float = 10.0,
    trailing_stop_distance_pct: float = 5.0,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["LABUSDT", "ORDIUSDT", "1000SATSUSDT", "PEPEUSDT", "1000BONKUSDT"])[:10]
    safe_events = max(20, min(_as_int(forward_window_trades, 200), 1_000))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 10))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 300), 5_000)) / 1000
    session_run_id = f"session-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{uuid.uuid4().hex[:8]}"
    if not dry_run and confirm != STATEFUL_FORWARD_PAPER_TRADE_CONFIRM:
        return {"ok": False, "dry_run": False, "stateful_status": "blocked", "blockers": ["confirm_CONFIRM_STATEFUL_FORWARD_PAPER_TRADE_required"], "would_write": False, "writes_performed": 0, **disabled}

    with _connect() as conn:
        table_exists = _table_exists(conn)
        open_positions = _load_stateful_open_positions(conn) if table_exists else {}
        seen_keys = _stateful_seen_trade_keys(conn, clean_symbols) if table_exists else set()
        last_processed_by_symbol = _stateful_last_processed_trade_ids(conn, clean_symbols) if table_exists else {}

    target_symbols = list(dict.fromkeys([*clean_symbols, *open_positions.keys()]))
    failed_symbols: list[dict[str, Any]] = []
    active_positions = dict(open_positions)
    rows_to_insert: list[dict[str, Any]] = []
    closed_pnls: list[float] = []
    realized_pnl_session = 0.0
    symbol_reports: dict[str, Any] = {}
    scan_at = _now()

    for index, symbol in enumerate(target_symbols):
        if index > 0 and safe_delay:
            time.sleep(safe_delay)
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "attempts": fetched.get("attempts")})
            continue
        trades = fetched.get("trades") or []
        position = active_positions.get(symbol)
        last_trade_id = str((position or {}).get("last_processed_trade_id") or (position or {}).get("last_trade_id") or last_processed_by_symbol.get(symbol) or "")
        last_index = _as_int((position or {}).get("last_known_trade_index"), -1)
        start_idx = 0
        if last_trade_id:
            matched = [idx for idx, trade in enumerate(trades) if str(trade.get("id") or "") == last_trade_id]
            if matched:
                start_idx = matched[-1] + 1
            elif last_index >= 0:
                start_idx = min(len(trades), last_index + 1)
        new_trades = _filter_already_processed_events(trades[start_idx:], last_trade_id)
        entries = 0
        exits = 0
        for local_idx, trade in enumerate(new_trades, start=start_idx):
            price = _trade_price(trade)
            if price <= 0:
                continue
            trade_id = str(trade.get("id") or "")
            window = trades[max(0, local_idx - 19) : local_idx + 1]
            score = _aster_score_proxy(window)
            run_id = session_run_id
            payload = {
                "action": "mark_to_market",
                "trade_id": trade_id,
                "last_processed_trade_id": trade_id,
                "session_run_id": session_run_id,
                "trade_index": local_idx,
                "trade_time": trade.get("time"),
                "source": "stateful_session_monitor",
            }
            position = active_positions.get(symbol)
            if position:
                side = str(position.get("side") or "long")
                entry = _as_float(position.get("entry_price"))
                size = _as_float(position.get("size_usd"))
                if side == "short":
                    pnl_unrealized = ((entry - price) / entry * size) if entry > 0 else 0.0
                    should_exit = False
                    exit_reason = "holding_short"
                    trough = min(_as_float(position.get("trough_price") or entry), price)
                    position["trough_price"] = trough
                    if entry > 0 and price >= entry * (1 + max(0.0, _as_float(short_stop_loss_pct)) / 100):
                        should_exit, exit_reason = True, "short_stop_loss_triggered"
                    elif entry > 0 and price <= entry * (1 + min(0.0, _as_float(short_take_profit_pct)) / 100):
                        should_exit, exit_reason = True, "short_take_profit_triggered"
                    trailing_active = entry > 0 and trough <= entry * (1 - max(0.0, _as_float(trailing_stop_activation_pct)) / 100)
                    if not should_exit and trailing_active and price >= trough * (1 + max(0.0, _as_float(trailing_stop_distance_pct)) / 100):
                        should_exit, exit_reason = True, "short_trailing_stop_triggered"
                    exit_event = "forward_short_exit"
                else:
                    peak = max(_as_float(position.get("peak_price") or entry), price)
                    position["peak_price"] = peak
                    pnl_unrealized = ((price - entry) / entry * size) if entry > 0 else 0.0
                    should_exit, exit_reason = should_exit_position(entry, price, long_stop_loss_pct, long_take_profit_pct)
                    trailing_active = entry > 0 and peak / entry >= 1 + max(0.0, _as_float(trailing_stop_activation_pct)) / 100
                    if not should_exit and trailing_active and price <= peak * (1 - max(0.0, _as_float(trailing_stop_distance_pct)) / 100):
                        should_exit, exit_reason = True, "trailing_stop_triggered"
                    exit_event = "forward_long_exit"
                if should_exit and (symbol, trade_id) not in seen_keys:
                    fees = size * 6.0 / 10_000
                    slippage = size * 10.0 / 10_000
                    pnl_realized = pnl_unrealized - fees - slippage
                    rows_to_insert.append(
                        _stateful_row(
                            run_id,
                            symbol,
                            exit_event,
                            "executing_exit",
                            exit_reason,
                            score,
                            price,
                            size,
                            0.0,
                            pnl_realized,
                            {**payload, "action": "exit", "side": side, "entry_price": entry},
                            fee_bps=6.0,
                            slippage_bps=10.0,
                        )
                    )
                    seen_keys.add((symbol, trade_id))
                    active_positions.pop(symbol, None)
                    closed_pnls.append(pnl_realized)
                    realized_pnl_session += pnl_realized
                    exits += 1
                else:
                    position["current_price"] = price
                    position["last_trade_id"] = trade_id
                    position["last_processed_trade_id"] = trade_id
                    position["last_known_trade_index"] = local_idx
                    position["pnl_unrealized_usd"] = round(pnl_unrealized, 6)
                continue

            enter_long = should_enter_position(_as_float(score.get("aster_score")), None, _as_float(score.get("window_volume_usd")), min_aster_score=min_aster_score, min_volume_usd=min_window_volume_usd)
            enter_short = _as_float(score.get("aster_score")) >= _as_float(min_aster_score) and _as_float(score.get("window_volume_usd")) >= _as_float(min_window_volume_usd)
            if (enter_long or enter_short) and (symbol, trade_id) not in seen_keys:
                side = "short" if enter_short else "long"
                size = calculate_position_size(wallet_balance_usd, 5.0, _as_float(score.get("aster_score")))
                event_type = "forward_short_entry" if side == "short" else "forward_long_entry"
                fees = size * 6.0 / 10_000
                slippage = size * 10.0 / 10_000
                rows_to_insert.append(
                    _stateful_row(
                        run_id,
                        symbol,
                        event_type,
                        "executing_entry",
                        f"{side}_entry_rules_passed",
                        score,
                        price,
                        size,
                        -fees - slippage,
                        0.0,
                        {**payload, "action": "entry", "side": side, "entry_price": price},
                        fee_bps=6.0,
                        slippage_bps=10.0,
                    )
                )
                seen_keys.add((symbol, trade_id))
                active_positions[symbol] = {
                    "symbol": symbol,
                    "side": side,
                    "entry_price": price,
                    "current_price": price,
                    "size_usd": size,
                    "entry_trade_id": trade_id,
                    "last_trade_id": trade_id,
                    "last_processed_trade_id": trade_id,
                    "last_known_trade_index": local_idx,
                    "peak_price": price,
                    "trough_price": price,
                    "entry_score": _as_float(score.get("aster_score")),
                }
                entries += 1
        symbol_reports[symbol] = {
            "market_type": fetched.get("market_type"),
            "fetched_events": len(trades),
            "new_trades_replayed": len(new_trades),
            "last_processed_trade_id_before_cycle": last_trade_id or None,
            "entries": entries,
            "exits": exits,
            "has_active_position": symbol in active_positions,
        }

    session_run_ids = sorted({str(row.get("run_id") or "") for row in rows_to_insert if row.get("run_id")})
    inserted = 0
    if not dry_run:
        with _connect() as conn:
            if not _table_exists(conn):
                return {"ok": False, "dry_run": False, "stateful_status": "blocked", "blockers": ["paper_trading_ledger_table_missing_create_first"], "would_write": False, "writes_performed": 0, **disabled}
            inserted = _insert_ledger_rows(conn, rows_to_insert)
            conn.commit()

    failed_ratio = len(failed_symbols) / max(1, len(target_symbols))
    wins = sum(1 for pnl in closed_pnls if pnl > 0)
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "stateful_status": "ready_dry_run_no_insert" if dry_run else "inserted",
        "health_status": "degraded" if failed_ratio > 0.5 else "active",
        "last_scan_at": scan_at,
        "session_run_id": session_run_id,
        "symbols": target_symbols,
        "loaded_open_positions": open_positions,
        "active_positions": list(active_positions.values()),
        "closed_in_session": len(closed_pnls),
        "realized_pnl_session": round(realized_pnl_session, 6),
        "session_win_rate": round(wins / len(closed_pnls), 6) if closed_pnls else None,
        "session_run_ids": session_run_ids,
        "symbol_reports": symbol_reports,
        "failed_symbols": failed_symbols,
        "would_insert_rows": 0 if not dry_run else len(rows_to_insert),
        "rows_inserted": inserted,
        "dedupe_keys_used": ["event_type", "symbol", "trade_id_in_raw_payload_json"],
        "would_write": not dry_run,
        "writes_performed": inserted,
        **disabled,
    }


def get_aster_selected_short_fade_forward_monitor_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    forward_window_trades: int = 800,
    timeout_seconds: int = 10,
    wallet_balance_usd: float = 1_000.0,
    rate_limit_delay_ms: int = 300,
) -> dict[str, Any]:
    disabled = _disabled()
    selected_symbols = _parse_symbols(symbols, SELECTED_SHORT_FADE_FORWARD_SYMBOLS)[:10]
    if not dry_run and confirm != STATEFUL_FORWARD_PAPER_TRADE_CONFIRM:
        return {
            "ok": False,
            "dry_run": False,
            "selected_forward_status": "blocked",
            "blockers": ["confirm_CONFIRM_STATEFUL_FORWARD_PAPER_TRADE_required"],
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    monitor = get_aster_paper_trading_stateful_session_monitor(
        symbols=selected_symbols,
        dry_run=dry_run,
        confirm=confirm,
        forward_window_trades=forward_window_trades,
        timeout_seconds=timeout_seconds,
        wallet_balance_usd=wallet_balance_usd,
        rate_limit_delay_ms=rate_limit_delay_ms,
        min_aster_score=70.0,
        min_window_volume_usd=1_000.0,
        short_stop_loss_pct=8.0,
        short_take_profit_pct=-6.0,
        trailing_stop_activation_pct=4.0,
        trailing_stop_distance_pct=2.0,
    )
    active = monitor.get("active_positions") or []
    short_active = [row for row in active if str(row.get("side") or "").lower() == "short"]
    return {
        "ok": bool(monitor.get("ok")),
        "dry_run": bool(dry_run),
        "selected_forward_status": monitor.get("stateful_status"),
        "selected_symbols": selected_symbols,
        "operational_params": {
            "min_aster_score": 70.0,
            "min_window_volume_usd": 1_000.0,
            "short_stop_loss_pct": 8.0,
            "short_take_profit_pct": -6.0,
            "trailing_stop_activation_pct": 4.0,
            "trailing_stop_distance_pct": 2.0,
            "forward_window_trades": max(20, min(_as_int(forward_window_trades, 800), 1_000)),
        },
        "active_short_positions": short_active,
        "active_short_positions_count": len(short_active),
        "closed_in_session": monitor.get("closed_in_session"),
        "realized_pnl_session": monitor.get("realized_pnl_session"),
        "session_win_rate": monitor.get("session_win_rate"),
        "rows_inserted": monitor.get("rows_inserted"),
        "would_insert_rows": monitor.get("would_insert_rows"),
        "health_status": monitor.get("health_status"),
        "execution_preview": monitor,
        "next_action": "repeat_selected_forward_monitor_until_total_exits_reaches_10",
        "would_write": not dry_run,
        "writes_performed": _as_int(monitor.get("writes_performed")),
        **disabled,
    }


def _payload_action(row: sqlite3.Row | dict[str, Any]) -> str | None:
    try:
        payload = json.loads(row["raw_payload_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload.get("action")


def _position_dashboard_row(position: dict[str, Any], timeout_seconds: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    symbol = str(position.get("symbol") or "").upper()
    side = str(position.get("side") or "long")
    entry = _as_float(position.get("entry_price"))
    size = _as_float(position.get("size_usd"))
    fetched = _fetch_recent_trades(symbol, 1, timeout_seconds) if symbol else {"ok": False, "fetch_status": "missing_symbol", "trades": []}
    trades = fetched.get("trades") or []
    latest_trade = trades[-1] if trades else {}
    current = _trade_price(latest_trade) or _as_float(position.get("current_price")) or entry
    if side == "short":
        pnl = ((entry - current) / entry * size) if entry > 0 else 0.0
        stop_price = entry * 1.15 if entry > 0 else 0.0
        stop_distance_pct = ((stop_price - current) / current * 100) if current > 0 else None
    else:
        pnl = ((current - entry) / entry * size) if entry > 0 else 0.0
        stop_price = entry * 0.75 if entry > 0 else 0.0
        stop_distance_pct = ((current - stop_price) / current * 100) if current > 0 else None
    opened_at = _parse_dt(position.get("entry_created_at"))
    time_held = None
    if opened_at:
        time_held = max(0.0, (datetime.now(timezone.utc) - opened_at.astimezone(timezone.utc)).total_seconds())
    latest_trade_id = str(latest_trade.get("id") or "")
    last_processed = str(position.get("last_processed_trade_id") or position.get("last_trade_id") or "")
    gap = None
    if latest_trade_id and last_processed and not _trade_id_lte(latest_trade_id, last_processed):
        gap = {"symbol": symbol, "last_processed_trade_id": last_processed, "latest_trade_id": latest_trade_id}
    return (
        {
            "symbol": symbol,
            "side": side,
            "entry_price": round(entry, 10),
            "current_price": round(current, 10),
            "size_usd": round(size, 6),
            "unrealized_pnl": round(pnl, 6),
            "time_held_seconds": round(time_held, 3) if time_held is not None else None,
            "stop_distance_pct": round(stop_distance_pct, 6) if stop_distance_pct is not None else None,
            "entry_trade_id": position.get("entry_trade_id"),
            "last_processed_trade_id": last_processed or None,
        },
        gap,
    )


def get_aster_agent_command_center_preview(
    symbols: str | list[str] | None = None,
    staging_mode: bool = False,
    dry_run: bool = True,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["LABUSDT", "ORDIUSDT", "1000SATSUSDT", "WIFUSDT"])[:5]
    safe_timeout = max(1, min(_as_int(timeout_seconds, 5), 10))
    staging_cycle = None
    if staging_mode:
        staging_cycle = get_aster_paper_trading_stateful_session_monitor(
            clean_symbols,
            True,
            None,
            50,
            safe_timeout,
            1_000.0,
            300,
        )

    analytics = get_aster_paper_trading_ledger_analytics(dry_run=True)
    open_positions: list[dict[str, Any]] = []
    recent_exits: list[dict[str, Any]] = []
    unprocessed_gaps: list[dict[str, Any]] = []
    last_cycle_at = None
    last_closed_pnls: list[float] = []
    gross_profit = 0.0
    gross_loss = 0.0
    api_failures = 0
    api_checks = 0

    with _connect() as conn:
        if _table_exists(conn):
            positions = _load_stateful_open_positions(conn)
            for position in positions.values():
                row, gap = _position_dashboard_row(position, safe_timeout)
                open_positions.append(row)
                if gap:
                    unprocessed_gaps.append(gap)
                api_checks += 1
            rows = conn.execute(
                f"SELECT * FROM {TABLE_NAME} WHERE event_type IN ('forward_long_exit','forward_short_exit') ORDER BY id DESC LIMIT 30"
            ).fetchall()
            for idx, row in enumerate(rows):
                payload = _stateful_payload(row)
                pnl = _as_float(row["pnl_realized_usd"])
                if idx < 10:
                    recent_exits.append(
                        {
                            "created_at": row["created_at"],
                            "run_id": row["run_id"],
                            "symbol": row["symbol"],
                            "realized_pnl": round(pnl, 6),
                            "exit_reason": row["decision_reason"],
                            "trade_id": payload.get("trade_id") or payload.get("idempotency_trade_id"),
                            "last_processed_trade_id": payload.get("last_processed_trade_id"),
                        }
                    )
                last_closed_pnls.append(pnl)
                if pnl > 0:
                    gross_profit += pnl
                elif pnl < 0:
                    gross_loss += abs(pnl)
            last = conn.execute(f"SELECT created_at FROM {TABLE_NAME} ORDER BY id DESC LIMIT 1").fetchone()
            last_cycle_at = last["created_at"] if last else None

    if staging_cycle:
        api_failures = len(staging_cycle.get("failed_symbols") or [])
        api_checks = max(api_checks, len(staging_cycle.get("symbols") or clean_symbols))

    wins = sum(1 for pnl in last_closed_pnls if pnl > 0)
    profit_factor = round(gross_profit / gross_loss, 6) if gross_loss else (None if gross_profit <= 0 else "unbounded_no_losses")
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "command_center_status": "ready",
        "open_positions": open_positions,
        "recent_exits": recent_exits,
        "performance": {
            "sample_closed_trades": len(last_closed_pnls),
            "win_rate": round(wins / len(last_closed_pnls), 6) if last_closed_pnls else None,
            "net_pnl": round(sum(last_closed_pnls), 6),
            "profit_factor": profit_factor,
            "ledger_totals": {
                "total_entries": analytics.get("total_entries"),
                "total_exits": analytics.get("total_exits"),
                "net_pnl_usd": analytics.get("net_pnl_usd"),
                "max_drawdown_usd": analytics.get("max_drawdown_usd"),
            },
        },
        "system_health": {
            "api_status": "degraded" if api_checks and api_failures / max(1, api_checks) > 0.5 else "active",
            "last_cycle_at": last_cycle_at,
            "unprocessed_gaps": unprocessed_gaps,
            "staging_mode_active": bool(staging_mode),
            "staging_cycle_status": (staging_cycle or {}).get("stateful_status"),
        },
        "staging_cycle_preview": staging_cycle,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_forward_reality_comparison_preview(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    max_events: int = 1000,
    timeout_seconds: int = 10,
    max_ledger_rows: int = 200,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(
        symbols,
        ["LABUSDT", "INJUSDT", "TIAUSDT", "INTCUSDT", "MSFTUSDT", "CRCLUSDT"],
    )[:12]
    safe_events = max(20, min(_as_int(max_events, 1000), 1000))
    safe_timeout = max(1, min(_as_int(timeout_seconds, 10), 10))
    safe_rows = max(10, min(_as_int(max_ledger_rows, 200), 1000))
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "comparison_status": "blocked",
            "blockers": ["dry_run_required_forward_reality_comparison_is_read_only"],
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }

    with _connect() as conn:
        table_exists = _table_exists(conn)
        ledger_rows: list[sqlite3.Row] = []
        open_positions = _load_stateful_open_positions(conn) if table_exists else {}
        if table_exists and clean_symbols:
            placeholders = ",".join("?" for _ in clean_symbols)
            ledger_rows = conn.execute(
                f"""
                SELECT *
                FROM {TABLE_NAME}
                WHERE UPPER(symbol) IN ({placeholders})
                  AND event_type LIKE 'forward_%'
                ORDER BY id DESC
                LIMIT ?
                """,
                [*clean_symbols, safe_rows],
            ).fetchall()

    rows_by_symbol: dict[str, list[sqlite3.Row]] = {symbol: [] for symbol in clean_symbols}
    for row in ledger_rows:
        symbol = str(row["symbol"] or "").upper()
        if symbol in rows_by_symbol:
            rows_by_symbol[symbol].append(row)

    market_by_symbol: dict[str, dict[str, Any]] = {}
    symbol_reports: list[dict[str, Any]] = []
    matched_trade_rows = 0
    checked_trade_rows = 0
    failed_symbols: list[dict[str, Any]] = []

    for symbol in clean_symbols:
        fetched = _fetch_recent_trades_with_spot_fallback(symbol, safe_events, safe_timeout)
        trades = fetched.get("trades") or []
        trade_by_id = {str(trade.get("id") or ""): trade for trade in trades if str(trade.get("id") or "")}
        latest_trade_id = str((trades[-1] if trades else {}).get("id") or "")
        if not fetched.get("ok"):
            failed_symbols.append(
                {
                    "symbol": symbol,
                    "fetch_status": fetched.get("fetch_status"),
                    "attempts": fetched.get("attempts"),
                }
            )

        validations: list[dict[str, Any]] = []
        entries = 0
        exits = 0
        for row in rows_by_symbol.get(symbol, [])[:25]:
            payload = _stateful_payload(row)
            action = str(payload.get("action") or "")
            if action == "entry":
                entries += 1
            elif action == "exit":
                exits += 1
            trade_id = str(payload.get("trade_id") or payload.get("idempotency_trade_id") or "")
            if not trade_id:
                continue
            checked_trade_rows += 1
            trade = trade_by_id.get(trade_id)
            ledger_price = _as_float(row["current_price"])
            market_price = _trade_price(trade or {})
            price_delta_pct = None
            if trade and ledger_price > 0 and market_price > 0:
                matched_trade_rows += 1
                price_delta_pct = ((ledger_price - market_price) / market_price) * 100
            validations.append(
                {
                    "created_at": row["created_at"],
                    "event_type": row["event_type"],
                    "action": action or None,
                    "trade_id": trade_id,
                    "seen_in_recent_market_window": bool(trade),
                    "ledger_price": round(ledger_price, 10) if ledger_price else None,
                    "market_price": round(market_price, 10) if market_price else None,
                    "price_delta_pct": round(price_delta_pct, 8) if price_delta_pct is not None else None,
                }
            )

        active = open_positions.get(symbol)
        market_by_symbol[symbol] = {
            "ok": bool(fetched.get("ok")),
            "fetch_status": fetched.get("fetch_status"),
            "market_type": fetched.get("market_type"),
            "recent_trades": len(trades),
            "latest_trade_id": latest_trade_id or None,
            "cache_hit": bool(fetched.get("cache_hit")),
            "ledger_forward_rows_checked": len(rows_by_symbol.get(symbol, [])),
            "ledger_entries_sample": entries,
            "ledger_exits_sample": exits,
            "active_position_loaded": bool(active),
            "active_position_side": (active or {}).get("side"),
            "last_processed_trade_id": (active or {}).get("last_processed_trade_id"),
            "recent_trade_validations": validations,
        }
        if not fetched.get("ok"):
            verdict = "market_fetch_failed_not_strategy_filter"
        elif len(trades) < 20:
            verdict = "not_enough_recent_trades"
        elif not rows_by_symbol.get(symbol) and not active:
            verdict = "no_forward_ledger_rows_for_symbol"
        elif validations and not any(row.get("seen_in_recent_market_window") for row in validations):
            verdict = "ledger_trade_ids_outside_recent_window"
        else:
            verdict = "forward_market_alignment_ok"
        symbol_reports.append({"symbol": symbol, "verdict": verdict, **market_by_symbol[symbol]})

    staging = get_aster_paper_trading_stateful_session_monitor(
        clean_symbols,
        True,
        None,
        min(safe_events, 200),
        safe_timeout,
        1_000.0,
        0,
    )
    dropped_by_api = [row["symbol"] for row in symbol_reports if row["verdict"] == "market_fetch_failed_not_strategy_filter"]
    no_ledger = [row["symbol"] for row in symbol_reports if row["verdict"] == "no_forward_ledger_rows_for_symbol"]
    alignment_ratio = matched_trade_rows / checked_trade_rows if checked_trade_rows else None
    if dropped_by_api:
        global_verdict = "api_or_market_availability_issue"
    elif alignment_ratio is not None and alignment_ratio < 0.5:
        global_verdict = "ledger_rows_need_wider_market_window_or_demo_validation"
    elif no_ledger:
        global_verdict = "some_symbols_not_yet_forward_tested"
    else:
        global_verdict = "forward_reality_check_ok"

    return {
        "ok": True,
        "dry_run": True,
        "comparison_status": "ready",
        "symbols_requested": clean_symbols,
        "global_verdict": global_verdict,
        "alignment_summary": {
            "checked_trade_rows": checked_trade_rows,
            "matched_trade_rows_in_recent_window": matched_trade_rows,
            "recent_window_alignment_ratio": round(alignment_ratio, 6) if alignment_ratio is not None else None,
            "symbols_failed_market_fetch": dropped_by_api,
            "symbols_without_forward_rows": no_ledger,
        },
        "symbol_reports": symbol_reports,
        "staging_forward_preview": {
            "stateful_status": staging.get("stateful_status"),
            "health_status": staging.get("health_status"),
            "would_insert_rows": staging.get("would_insert_rows"),
            "symbol_reports": staging.get("symbol_reports"),
            "failed_symbols": staging.get("failed_symbols"),
        },
        "demo_account_recommendation": {
            "use_demo_or_testnet_next": True,
            "why": "Compare the same symbols against real Aster order acceptance, fills, margin, and rejections before real capital.",
            "blocked_until": "testnet_or_demo_access_and_read_only_credentials_are_configured",
        },
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_ledger_analytics(
    run_id: str | None = None,
    symbol: str | None = None,
    since_timestamp: str | None = None,
    initial_balance_usd: float = 1_000.0,
    dry_run: bool = True,
    event_type: str | None = None,
) -> dict[str, Any]:
    disabled = _disabled()
    where: list[str] = []
    params: list[Any] = []
    if run_id:
        where.append("run_id = ?")
        params.append(str(run_id))
    if symbol:
        where.append("UPPER(symbol) = ?")
        params.append(str(symbol).strip().upper())
    if since_timestamp:
        where.append("created_at >= ?")
        params.append(str(since_timestamp))
    if event_type:
        where.append("event_type = ?")
        params.append(_safe_event_type(event_type, str(event_type)))
    query = f"SELECT * FROM {TABLE_NAME}"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at ASC, id ASC"
    with _connect() as conn:
        if not _table_exists(conn):
            return {"ok": False, "dry_run": dry_run, "analytics_status": "blocked", "blockers": ["paper_trading_ledger_table_missing"], "would_write": False, "writes_performed": 0, **disabled}
        rows = conn.execute(query, params).fetchall()
    entries = []
    exits = []
    balance = max(0.0, _as_float(initial_balance_usd))
    equity_curve: list[dict[str, Any]] = []
    gross_profit = 0.0
    gross_loss = 0.0
    max_drawdown = 0.0
    net_pnl = 0.0
    for row in rows:
        action = _payload_action(row)
        state = row["state"]
        if action == "entry" or state == "executing_entry" or row["event_type"] == "entry_simulated":
            entries.append(row)
        if action == "exit" or state == "executing_exit":
            pnl = _as_float(row["pnl_realized_usd"])
            exits.append(row)
            net_pnl += pnl
            if pnl > 0:
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)
            balance += pnl
            equity_curve.append({"created_at": row["created_at"], "run_id": row["run_id"], "symbol": row["symbol"], "balance_usd": round(balance, 6), "pnl_realized_usd": round(pnl, 6)})
        max_drawdown = max(max_drawdown, _as_float(row["max_drawdown_usd"]))
    wins = sum(1 for row in exits if _as_float(row["pnl_realized_usd"]) > 0)
    return {
        "ok": True,
        "dry_run": dry_run,
        "analytics_status": "ready",
        "filters": {"run_id": run_id, "symbol": symbol, "since_timestamp": since_timestamp, "event_type": event_type},
        "row_count": len(rows),
        "total_entries": len(entries),
        "total_exits": len(exits),
        "win_rate": round(wins / len(exits), 6) if exits else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "gross_profit_usd": round(gross_profit, 6),
        "gross_loss_usd": round(gross_loss, 6),
        "max_drawdown_usd": round(max_drawdown, 6),
        "net_pnl_usd": round(net_pnl, 6),
        "initial_balance_usd": round(max(0.0, _as_float(initial_balance_usd)), 6),
        "final_balance_usd": round(balance, 6),
        "equity_curve": equity_curve,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_replay_insert(
    symbol: str | None = "BTCUSDT",
    dry_run: bool = True,
    confirm: str | None = None,
    max_events: int = 100,
    timeout_seconds: int = 8,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
) -> dict[str, Any]:
    disabled = _disabled()
    safe_symbol = str(symbol or "BTCUSDT").strip().upper() or "BTCUSDT"
    safe_events = max(1, min(_as_int(max_events, 100), 1000))
    run_id = f"replay-{uuid.uuid4()}"
    if not dry_run and confirm != REPLAY_CONFIRM:
        return {"ok": False, "dry_run": False, "replay_status": "blocked", "blockers": ["confirm_CONFIRM_ASTER_PAPER_REPLAY_INSERT_required"], "would_write": False, "writes_performed": 0, **disabled}
    fetched = _fetch_recent_trades(safe_symbol, safe_events, timeout_seconds)
    if not fetched.get("ok"):
        return {"ok": False, "dry_run": dry_run, "replay_status": "blocked", "blockers": [f"aster_fetch_{fetched.get('fetch_status')}"], "fetch": fetched, "would_write": False, "writes_performed": 0, **disabled}
    rows, report = _replay_trades(
        fetched.get("trades") or [],
        run_id,
        safe_symbol,
        wallet_balance_usd,
        fee_bps,
        slippage_bps,
        window_size,
    )
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "replay_status": "ready_dry_run_no_insert",
            "run_id": run_id,
            "symbol": safe_symbol,
            "fetched_events": len(fetched.get("trades") or []),
            "would_insert_rows": len(rows),
            "ledger_rows_preview": rows[:20],
            "report": report,
            "max_events_cap": 1000,
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    with _connect() as conn:
        if not _table_exists(conn):
            return {"ok": False, "dry_run": False, "replay_status": "blocked", "blockers": ["paper_trading_ledger_table_missing_create_first"], "would_write": False, "writes_performed": 0, **disabled}
        inserted = _insert_ledger_rows(conn, rows)
        conn.commit()
    return {
        "ok": True,
        "dry_run": False,
        "replay_status": "inserted",
        "run_id": run_id,
        "symbol": safe_symbol,
        "fetched_events": len(fetched.get("trades") or []),
        "rows_inserted": inserted,
        "dedupe_keys_used": ["run_id", "event_type", "trade_id_in_raw_payload_json"],
        "next_action": "re-run-on-demand-scoring",
        "report": report,
        "would_write": True,
        "writes_performed": inserted,
        **disabled,
    }


def get_aster_paper_trading_watchlist_replay_insert(
    symbols: str | list[str] | None = None,
    dry_run: bool = True,
    confirm: str | None = None,
    max_events: int = 100,
    timeout_seconds: int = 8,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
    window_size: int = 20,
    rate_limit_delay_ms: int = 500,
) -> dict[str, Any]:
    disabled = _disabled()
    clean_symbols = _parse_symbols(symbols, ["SOLUSDT", "DOGEUSDT", "PEPEUSDT"])[:10]
    safe_events = max(1, min(_as_int(max_events, 100), 1000))
    safe_delay = max(0, min(_as_int(rate_limit_delay_ms, 500), 5_000)) / 1000
    if not dry_run and confirm != WATCHLIST_REPLAY_CONFIRM:
        return {"ok": False, "dry_run": False, "watchlist_status": "blocked", "blockers": ["confirm_CONFIRM_ASTER_WATCHLIST_REPLAY_INSERT_required"], "would_write": False, "writes_performed": 0, **disabled}
    all_rows: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    failed_symbols: list[dict[str, Any]] = []
    for index, symbol in enumerate(clean_symbols):
        if index:
            time.sleep(safe_delay)
        fetched = _fetch_recent_trades(symbol, safe_events, timeout_seconds)
        if not fetched.get("ok"):
            failed_symbols.append({"symbol": symbol, "fetch_status": fetched.get("fetch_status"), "http_status": fetched.get("http_status"), "error": fetched.get("error")})
            continue
        run_id = f"watchlist-{uuid.uuid4()}-{symbol}"
        rows, report = _replay_trades(
            fetched.get("trades") or [],
            run_id,
            symbol,
            wallet_balance_usd,
            fee_bps,
            slippage_bps,
            window_size,
        )
        all_rows.extend(rows)
        reports.append({"symbol": symbol, "run_id": run_id, "fetched_events": len(fetched.get("trades") or []), "would_insert_rows": len(rows), "report": report})
    global_report = {
        "symbols_requested": len(clean_symbols),
        "symbols_succeeded": len(reports),
        "symbols_failed": len(failed_symbols),
        "simulated_trade_count": sum(_as_int(item["report"].get("simulated_trade_count")) for item in reports),
        "closed_trade_count": sum(_as_int(item["report"].get("closed_trade_count")) for item in reports),
        "pnl_total_usd": round(sum(_as_float(item["report"].get("pnl_total_usd")) for item in reports), 6),
        "max_drawdown_usd": round(max([_as_float(item["report"].get("max_drawdown_usd")) for item in reports] or [0.0]), 6),
        "final_balance_usd_sum": round(sum(_as_float(item["report"].get("final_balance_usd")) for item in reports), 6),
    }
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "watchlist_status": "ready_dry_run_no_insert",
            "symbols": clean_symbols,
            "reports": reports,
            "failed_symbols": failed_symbols,
            "global_watchlist_report": global_report,
            "would_insert_rows": len(all_rows),
            "ledger_rows_preview": all_rows[:20],
            "would_write": False,
            "writes_performed": 0,
            **disabled,
        }
    with _connect() as conn:
        if not _table_exists(conn):
            return {"ok": False, "dry_run": False, "watchlist_status": "blocked", "blockers": ["paper_trading_ledger_table_missing_create_first"], "would_write": False, "writes_performed": 0, **disabled}
        inserted = _insert_ledger_rows(conn, all_rows)
        conn.commit()
    return {
        "ok": True,
        "dry_run": False,
        "watchlist_status": "inserted",
        "symbols": clean_symbols,
        "reports": reports,
        "failed_symbols": failed_symbols,
        "global_watchlist_report": global_report,
        "rows_inserted": inserted,
        "would_write": True,
        "writes_performed": inserted,
        **disabled,
    }


def get_aster_paper_trading_strategy_report(
    run_id_prefix: str | None = None,
    initial_balance_usd: float = 1_000.0,
    dry_run: bool = True,
) -> dict[str, Any]:
    disabled = _disabled()
    where: list[str] = []
    params: list[Any] = []
    if run_id_prefix:
        where.append("run_id LIKE ?")
        params.append(f"{str(run_id_prefix)}%")
    query = f"SELECT * FROM {TABLE_NAME}"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at ASC, id ASC"
    with _connect() as conn:
        if not _table_exists(conn):
            return {"ok": False, "dry_run": dry_run, "report_status": "blocked", "blockers": ["paper_trading_ledger_table_missing"], "would_write": False, "writes_performed": 0, **disabled}
        rows = conn.execute(query, params).fetchall()
    by_symbol: dict[str, dict[str, Any]] = {}
    portfolio_pnl = 0.0
    portfolio_wins = 0
    portfolio_closed = 0
    portfolio_drawdown = 0.0
    for row in rows:
        symbol = str(row["symbol"] or "UNKNOWN").upper()
        bucket = by_symbol.setdefault(
            symbol,
            {
                "symbol": symbol,
                "entries": 0,
                "exits": 0,
                "wins": 0,
                "net_pnl_usd": 0.0,
                "max_drawdown_usd": 0.0,
                "row_count": 0,
            },
        )
        bucket["row_count"] += 1
        action = _payload_action(row)
        state = row["state"]
        if action == "entry" or state == "executing_entry" or row["event_type"] == "entry_simulated":
            bucket["entries"] += 1
        if action == "exit" or state == "executing_exit":
            pnl = _as_float(row["pnl_realized_usd"])
            bucket["exits"] += 1
            bucket["net_pnl_usd"] += pnl
            portfolio_pnl += pnl
            portfolio_closed += 1
            if pnl > 0:
                bucket["wins"] += 1
                portfolio_wins += 1
        drawdown = _as_float(row["max_drawdown_usd"])
        bucket["max_drawdown_usd"] = max(bucket["max_drawdown_usd"], drawdown)
        portfolio_drawdown = max(portfolio_drawdown, drawdown)
    symbol_reports = []
    for bucket in by_symbol.values():
        exits = _as_int(bucket.get("exits"))
        symbol_reports.append(
            {
                "symbol": bucket["symbol"],
                "net_pnl_usd": round(_as_float(bucket.get("net_pnl_usd")), 6),
                "win_rate": round(_as_int(bucket.get("wins")) / exits, 6) if exits else None,
                "max_drawdown_usd": round(_as_float(bucket.get("max_drawdown_usd")), 6),
                "closed_trades": exits,
                "entries": _as_int(bucket.get("entries")),
                "ledger_rows": _as_int(bucket.get("row_count")),
            }
        )
    symbol_reports.sort(key=lambda item: (item["net_pnl_usd"], item["closed_trades"], item["entries"]), reverse=True)
    best = max(symbol_reports, key=lambda item: item["net_pnl_usd"], default=None)
    worst = min(symbol_reports, key=lambda item: item["net_pnl_usd"], default=None)
    most_traded = max(symbol_reports, key=lambda item: item["closed_trades"] + item["entries"], default=None)
    portfolio = {
        "symbols_count": len(symbol_reports),
        "ledger_rows": len(rows),
        "pnl_total_usd": round(portfolio_pnl, 6),
        "max_drawdown_usd": round(portfolio_drawdown, 6),
        "win_rate": round(portfolio_wins / portfolio_closed, 6) if portfolio_closed else None,
        "closed_trades": portfolio_closed,
        "initial_balance_usd": round(max(0.0, _as_float(initial_balance_usd)), 6),
        "final_balance_usd": round(max(0.0, _as_float(initial_balance_usd)) + portfolio_pnl, 6),
    }
    executive_summary = {
        "status": "no_closed_trades_yet" if portfolio_closed == 0 else "ready",
        "headline": (
            "No closed paper trades yet; strategy has produced observations but no realized PnL."
            if portfolio_closed == 0
            else f"Portfolio realized PnL is {portfolio['pnl_total_usd']} USD across {portfolio_closed} closed paper trades."
        ),
        "best_performing_asset": best,
        "worst_performing_asset": worst,
        "most_traded_asset": most_traded,
        "portfolio": portfolio,
    }
    return {
        "ok": True,
        "dry_run": dry_run,
        "report_status": "ready",
        "filters": {"run_id_prefix": run_id_prefix},
        "executive_summary": executive_summary,
        "performance_by_symbol": symbol_reports,
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }


def get_aster_paper_trading_run_preview(
    symbols: str | list[str] | None = "BTCUSDT",
    token_addresses: str | list[str] | None = None,
    dry_run: bool = True,
    timeout_seconds: int = 8,
    wallet_balance_usd: float = 1_000.0,
    fee_bps: float = 6.0,
    slippage_bps: float = 10.0,
) -> dict[str, Any]:
    disabled = _disabled()
    if not dry_run:
        return {"ok": False, "dry_run": False, "run_status": "blocked", "blockers": ["dry_run_required_for_paper_run_preview"], "would_write": False, "writes_performed": 0, **disabled}
    run_id = f"paper-{uuid.uuid4()}"
    agent = run_aster_agent_loop_test(
        wallet_address=None,
        symbols=symbols,
        token_addresses=token_addresses,
        dry_run=True,
        max_cycles=1,
        timeout_seconds=timeout_seconds,
        wallet_balance_usd=wallet_balance_usd,
    )
    rows = _ledger_rows_from_agent(agent, run_id, fee_bps, slippage_bps)
    return {
        "ok": True,
        "dry_run": True,
        "run_status": "ready",
        "run_id": run_id,
        "target_table": TABLE_NAME,
        "agent_state": agent.get("current_state"),
        "agent_status": agent.get("agent_status"),
        "ledger_rows_preview": rows,
        "report": _report(rows),
        "would_insert_rows": len(rows),
        "would_write": False,
        "writes_performed": 0,
        **disabled,
    }
