from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
JSON_OUT = BASE_DIR / "aster_mark_index_replay_filter_latest.json"
ASTER_FAPI_V3_BASE_URL = "https://fapi.asterdex.com"
USER_AGENT = "CoreEquityAsterMarkIndexReplayFilter/0.1"

DEFAULT_SYMBOLS = ["LABUSDT", "INJUSDT", "BOMEUSDT", "TIAUSDT", "CRCLUSDT", "INTCUSDT"]
DEFAULT_INTERVALS = ["5h", "3h", "1h", "30m"]
INTERVAL_MS = {
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


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_csv(value: str | list[str] | None, default: list[str], limit: int) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or ",".join(default)).replace(";", ",").split(",")
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        clean = "".join(ch for ch in str(item or "").strip().upper() if ch.isalnum())
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
        if len(out) >= limit:
            break
    return out or default[:limit]


def _parse_intervals(value: str | list[str] | None, default: list[str], limit: int) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or ",".join(default)).replace(";", ",").split(",")
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        clean = str(item or "").strip().lower()
        if clean in INTERVAL_MS and clean not in seen:
            seen.add(clean)
            out.append(clean)
        if len(out) >= limit:
            break
    return out or default[:limit]


def _fetch_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=max(1, min(int(timeout_seconds or 10), 15))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "ok": True,
            "status": "ok",
            "http_status": int(response.status),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "payload": payload,
        }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": {403: "blocked_by_aster", 404: "not_found", 429: "rate_limited"}.get(exc.code, f"http_{exc.code}"),
            "http_status": int(exc.code),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "request_failed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": type(exc).__name__,
        }


def _url(path: str, params: dict[str, Any]) -> str:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    return f"{ASTER_FAPI_V3_BASE_URL}{path}?{query}"


def _aggregate_klines(rows: list[list[Any]], interval: str) -> list[list[Any]]:
    factor = {"3h": 3, "5h": 5}.get(interval)
    if not factor:
        return rows
    bucket_size_ms = factor * INTERVAL_MS["1h"]
    out: list[list[Any]] = []
    buckets: dict[int, list[list[Any]]] = {}
    for row in rows:
        bucket = _as_int(row[0]) // bucket_size_ms
        buckets.setdefault(bucket, []).append(row)
    for bucket_rows in [buckets[key] for key in sorted(buckets)]:
        if len(bucket_rows) < factor:
            continue
        out.append(
            [
                _as_int(bucket_rows[0][0]),
                bucket_rows[0][1],
                str(max(_as_float(row[2]) for row in bucket_rows)),
                str(min(_as_float(row[3]) for row in bucket_rows)),
                bucket_rows[-1][4],
                str(sum(_as_float(row[5]) for row in bucket_rows)),
                _as_int(bucket_rows[-1][6]),
                str(sum(_as_float(row[7]) for row in bucket_rows)),
                sum(_as_int(row[8]) for row in bucket_rows),
                str(sum(_as_float(row[9]) for row in bucket_rows)),
                str(sum(_as_float(row[10]) for row in bucket_rows)),
                "0",
            ]
        )
    return out


def _fetch_klines(symbol: str, interval: str, path: str, param_name: str, lookback_days: int, timeout_seconds: int) -> dict[str, Any]:
    synthetic = interval in {"3h", "5h"}
    query_interval = "1h" if synthetic else interval
    interval_ms = INTERVAL_MS.get(query_interval)
    if not interval_ms:
        return {"ok": False, "status": "unsupported_interval", "klines": []}
    expected = max(50, int((lookback_days * 86_400_000) / interval_ms) + 5)
    limit = max(50, min(expected, 1500))
    result = _fetch_json(_url(path, {param_name: symbol, "interval": query_interval, "limit": limit}), timeout_seconds)
    payload = result.get("payload")
    if not result.get("ok") or not isinstance(payload, list):
        return {**result, "klines": []}
    rows = [row for row in payload if isinstance(row, list) and len(row) >= 12]
    rows.sort(key=lambda row: _as_int(row[0]))
    if synthetic:
        rows = _aggregate_klines(rows, interval)
    return {**result, "klines": rows, "source_interval": query_interval, "synthetic_interval": synthetic}


def _aligned_metrics(last_rows: list[list[Any]], mark_rows: list[list[Any]], index_rows: list[list[Any]]) -> dict[str, Any]:
    last_by_time = {_as_int(row[0]): row for row in last_rows}
    mark_by_time = {_as_int(row[0]): row for row in mark_rows}
    index_by_time = {_as_int(row[0]): row for row in index_rows}
    times = sorted(set(last_by_time) & set(mark_by_time) & set(index_by_time))
    if not times:
        return {"aligned_count": 0, "status": "no_overlap"}

    last_mark_bps: list[float] = []
    last_index_bps: list[float] = []
    mark_index_bps: list[float] = []
    sign_agree_last_mark = 0
    sign_agree_last_index = 0
    return_count = 0
    prev: tuple[float, float, float] | None = None
    for ts in times:
        last_close = _as_float(last_by_time[ts][4])
        mark_close = _as_float(mark_by_time[ts][4])
        index_close = _as_float(index_by_time[ts][4])
        if mark_close:
            last_mark_bps.append(abs(last_close - mark_close) / mark_close * 10_000)
        if index_close:
            last_index_bps.append(abs(last_close - index_close) / index_close * 10_000)
        if index_close:
            mark_index_bps.append(abs(mark_close - index_close) / index_close * 10_000)
        if prev and prev[0] and prev[1] and prev[2]:
            last_ret = (last_close - prev[0]) / prev[0]
            mark_ret = (mark_close - prev[1]) / prev[1]
            index_ret = (index_close - prev[2]) / prev[2]
            sign_agree_last_mark += int(last_ret * mark_ret >= 0)
            sign_agree_last_index += int(last_ret * index_ret >= 0)
            return_count += 1
        prev = (last_close, mark_close, index_close)

    def avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 6) if values else None

    def pctl(values: list[float], q: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
        return round(ordered[index], 6)

    return {
        "aligned_count": len(times),
        "coverage_start": datetime.fromtimestamp(times[0] / 1000, timezone.utc).isoformat(),
        "coverage_end": datetime.fromtimestamp(times[-1] / 1000, timezone.utc).isoformat(),
        "avg_last_mark_close_bps": avg(last_mark_bps),
        "p95_last_mark_close_bps": pctl(last_mark_bps, 0.95),
        "max_last_mark_close_bps": round(max(last_mark_bps), 6) if last_mark_bps else None,
        "avg_last_index_close_bps": avg(last_index_bps),
        "p95_last_index_close_bps": pctl(last_index_bps, 0.95),
        "max_last_index_close_bps": round(max(last_index_bps), 6) if last_index_bps else None,
        "avg_mark_index_close_bps": avg(mark_index_bps),
        "p95_mark_index_close_bps": pctl(mark_index_bps, 0.95),
        "max_mark_index_close_bps": round(max(mark_index_bps), 6) if mark_index_bps else None,
        "last_mark_return_sign_agreement": round(sign_agree_last_mark / return_count, 6) if return_count else None,
        "last_index_return_sign_agreement": round(sign_agree_last_index / return_count, 6) if return_count else None,
    }


def _verdict(metrics: dict[str, Any], min_aligned: int) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    aligned = _as_int(metrics.get("aligned_count"))
    max_lm = _as_float(metrics.get("max_last_mark_close_bps"))
    max_li = _as_float(metrics.get("max_last_index_close_bps"))
    p95_lm = _as_float(metrics.get("p95_last_mark_close_bps"))
    p95_li = _as_float(metrics.get("p95_last_index_close_bps"))
    avg_lm = _as_float(metrics.get("avg_last_mark_close_bps"))
    avg_li = _as_float(metrics.get("avg_last_index_close_bps"))
    agree = min(_as_float(metrics.get("last_mark_return_sign_agreement")), _as_float(metrics.get("last_index_return_sign_agreement")))
    if aligned < min_aligned:
        blockers.append("insufficient_mark_index_overlap")
    if p95_lm > 100 or p95_li > 175:
        blockers.append("persistent_last_vs_mark_or_index_divergence")
    if max_lm > 100 or max_li > 150:
        warnings.append("single_candle_extreme_last_vs_reference_divergence")
    if avg_lm > 25 or avg_li > 40:
        warnings.append("elevated_average_last_vs_reference_divergence")
    if agree and agree < 0.70:
        warnings.append("weak_return_direction_agreement")
    if blockers:
        verdict = "mark_index_rejected"
    elif warnings:
        verdict = "mark_index_watch"
    else:
        verdict = "mark_index_confirmed"
    return {"verdict": verdict, "blockers": blockers, "warnings": warnings}


def get_aster_mark_index_replay_filter_preview(
    symbols: str | list[str] | None = None,
    intervals: str | list[str] | None = None,
    dry_run: bool = True,
    lookback_days: int = 30,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 250,
    min_aligned_klines: int = 30,
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
    clean_symbols = _parse_csv(symbols, DEFAULT_SYMBOLS, 12)
    clean_intervals = _parse_intervals(intervals, DEFAULT_INTERVALS, 8)
    safe_days = max(1, min(int(lookback_days or 30), 60))
    delay = max(0, min(int(rate_limit_delay_ms or 250), 2_000)) / 1000
    timeout = max(1, min(int(timeout_seconds or 10), 15))
    rows: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for symbol_index, symbol in enumerate(clean_symbols):
        for interval_index, interval in enumerate(clean_intervals):
            if (symbol_index or interval_index) and delay:
                time.sleep(delay)
            last = _fetch_klines(symbol, interval, "/fapi/v3/klines", "symbol", safe_days, timeout)
            mark = _fetch_klines(symbol, interval, "/fapi/v3/markPriceKlines", "symbol", safe_days, timeout)
            index = _fetch_klines(symbol, interval, "/fapi/v3/indexPriceKlines", "pair", safe_days, timeout)
            statuses = {"last": last.get("status"), "mark": mark.get("status"), "index": index.get("status")}
            if not (last.get("ok") and mark.get("ok") and index.get("ok")):
                failed.append({"symbol": symbol, "interval": interval, "statuses": statuses})
                continue
            metrics = _aligned_metrics(last.get("klines") or [], mark.get("klines") or [], index.get("klines") or [])
            decision = _verdict(metrics, max(5, min(int(min_aligned_klines or 30), 300)))
            rows.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "lookback_days_requested": safe_days,
                    "fetch_statuses": statuses,
                    "last_klines": len(last.get("klines") or []),
                    "mark_klines": len(mark.get("klines") or []),
                    "index_klines": len(index.get("klines") or []),
                    **metrics,
                    **decision,
                }
            )
    summary = {
        "confirmed": sum(1 for row in rows if row.get("verdict") == "mark_index_confirmed"),
        "watch": sum(1 for row in rows if row.get("verdict") == "mark_index_watch"),
        "rejected": sum(1 for row in rows if row.get("verdict") == "mark_index_rejected"),
        "failed_fetches": len(failed),
    }
    payload = {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "generated_at": _now(),
        "methodology": "compare_last_price_klines_against_public_mark_and_index_klines_before_promoting_backtest_lanes",
        "symbols": clean_symbols,
        "intervals": clean_intervals,
        "summary": summary,
        "rows": rows,
        "failed": failed,
        "next_action": "promote_only_lanes_with_mark_index_confirmed_or_watch_plus_manual_review",
        "safety": {
            "would_write": False,
            "writes_performed": 0,
            "would_call_signed_endpoint": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
        },
    }
    return payload


def write_aster_mark_index_replay_filter_snapshot(**kwargs: Any) -> dict[str, Any]:
    payload = get_aster_mark_index_replay_filter_preview(**kwargs)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_aster_mark_index_replay_filter_snapshot()
    print(f"[{payload['generated_at']}] rows={len(payload['rows'])} summary={payload['summary']} json={JSON_OUT}")


if __name__ == "__main__":
    main()
