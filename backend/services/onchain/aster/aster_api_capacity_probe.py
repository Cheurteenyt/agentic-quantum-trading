from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
JSON_OUT = BASE_DIR / "aster_api_capacity_probe_latest.json"
ASTER_FAPI_V3_BASE_URL = "https://fapi.asterdex.com"
USER_AGENT = "CoreEquityAsterApiCapacityProbe/0.1"

SAFE_ENDPOINTS = [
    ("ping", "/fapi/v3/ping", {}),
    ("time", "/fapi/v3/time", {}),
    ("book_ticker", "/fapi/v3/ticker/bookTicker", {"symbol": "{symbol}"}),
    ("ticker_24h", "/fapi/v3/ticker/24hr", {"symbol": "{symbol}"}),
    ("depth_5", "/fapi/v3/depth", {"symbol": "{symbol}", "limit": 5}),
    ("trades_50", "/fapi/v3/trades", {"symbol": "{symbol}", "limit": 50}),
    ("klines_50", "/fapi/v3/klines", {"symbol": "{symbol}", "interval": "15m", "limit": 50}),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_symbol(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())[:32]


def _parse_symbols(value: str | None, limit: int) -> list[str]:
    rows = str(value or "BTCUSDT,LABUSDT,INJUSDT").replace(";", ",").split(",")
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = _clean_symbol(row)
        if symbol and symbol not in seen:
            out.append(symbol)
            seen.add(symbol)
        if len(out) >= limit:
            break
    return out or ["BTCUSDT"]


def _url(path: str, params: dict[str, Any], symbol: str) -> str:
    clean_params = {
        key: (symbol if value == "{symbol}" else value)
        for key, value in params.items()
        if value is not None
    }
    query = urllib.parse.urlencode(clean_params)
    return f"{ASTER_FAPI_V3_BASE_URL}{path}" + (f"?{query}" if query else "")


def _request_once(endpoint_name: str, url: str, timeout_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=max(1, min(int(timeout_seconds or 8), 15))) as response:
            response.read()
            headers = {
                key: response.headers.get(key)
                for key in ("x-mbx-used-weight-1m", "x-mbx-used-weight", "retry-after")
                if response.headers.get(key) is not None
            }
            return {
                "ok": True,
                "endpoint": endpoint_name,
                "status": "ok",
                "http_status": int(response.status),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "rate_limit_headers": headers,
            }
    except urllib.error.HTTPError as exc:
        status = {
            403: "blocked_by_aster",
            418: "ip_auto_banned",
            429: "rate_limited",
            503: "server_busy",
        }.get(int(exc.code), f"http_{exc.code}")
        return {
            "ok": False,
            "endpoint": endpoint_name,
            "status": status,
            "http_status": int(exc.code),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "retry_after": exc.headers.get("retry-after"),
            "rate_limit_headers": {
                key: exc.headers.get(key)
                for key in ("x-mbx-used-weight-1m", "x-mbx-used-weight", "retry-after")
                if exc.headers.get(key) is not None
            },
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "endpoint": endpoint_name,
            "status": "request_failed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": type(exc).__name__,
        }


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        out[status] = out.get(status, 0) + 1
    return out


def _latency_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row.get("latency_ms") or 0.0) for row in rows if row.get("latency_ms") is not None]
    if not values:
        return {"count": 0, "avg_ms": None, "p95_ms": None, "max_ms": None}
    sorted_values = sorted(values)
    p95_index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * 0.95)))
    return {
        "count": len(values),
        "avg_ms": round(statistics.fmean(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(sorted_values[p95_index], 3),
        "max_ms": round(max(values), 3),
    }


def _recommendation(rows: list[dict[str, Any]], max_parallel: int) -> dict[str, Any]:
    counts = _status_counts(rows)
    total = max(1, len(rows))
    fail_count = total - counts.get("ok", 0)
    hard_blocks = counts.get("ip_auto_banned", 0) + counts.get("blocked_by_aster", 0)
    rate_limited = counts.get("rate_limited", 0)
    latency = _latency_stats(rows)
    p95 = float(latency.get("p95_ms") or 0.0)

    if hard_blocks:
        return {
            "capacity_status": "danger_stop",
            "recommended_parallel_runners": 1,
            "recommended_sleep_seconds": 2400,
            "reason": "Aster returned 403/418 style blocking; stop adding terminals.",
        }
    if rate_limited:
        return {
            "capacity_status": "rate_limited_reduce",
            "recommended_parallel_runners": max(1, min(3, int(max_parallel or 1))),
            "recommended_sleep_seconds": 2400,
            "reason": "429 observed; reduce parallelism and increase sleep interval.",
        }
    if fail_count / total >= 0.15:
        return {
            "capacity_status": "unstable_reduce",
            "recommended_parallel_runners": max(1, min(3, int(max_parallel or 1))),
            "recommended_sleep_seconds": 1800,
            "reason": "Request failures above 15%; API or network is unstable.",
        }
    if p95 >= 2500:
        return {
            "capacity_status": "slow_hold",
            "recommended_parallel_runners": max(1, min(4, int(max_parallel or 1))),
            "recommended_sleep_seconds": 1800,
            "reason": "High p95 latency; keep current runner count.",
        }
    return {
        "capacity_status": "safe_to_expand_carefully",
        "recommended_parallel_runners": min(6, max(4, int(max_parallel or 1) + 1)),
        "recommended_sleep_seconds": 1200,
        "reason": "No rate-limit/blocking and latency acceptable; one extra exploration runner is reasonable.",
    }


def get_aster_api_capacity_probe_preview(
    *,
    symbols: str | None = None,
    requests: int = 28,
    max_parallel: int = 4,
    timeout_seconds: int = 8,
    write_snapshot: bool = True,
) -> dict[str, Any]:
    safe_requests = max(4, min(int(requests or 28), 140))
    safe_parallel = max(1, min(int(max_parallel or 4), 10))
    safe_timeout = max(1, min(int(timeout_seconds or 8), 15))
    selected_symbols = _parse_symbols(symbols, limit=8)

    jobs: list[tuple[str, str]] = []
    index = 0
    while len(jobs) < safe_requests:
        endpoint_name, path, params = SAFE_ENDPOINTS[index % len(SAFE_ENDPOINTS)]
        symbol = selected_symbols[index % len(selected_symbols)]
        jobs.append((endpoint_name, _url(path, params, symbol)))
        index += 1

    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=safe_parallel) as pool:
        futures = [pool.submit(_request_once, name, url, safe_timeout) for name, url in jobs]
        for future in as_completed(futures):
            rows.append(future.result())

    rows.sort(key=lambda row: (str(row.get("endpoint") or ""), float(row.get("latency_ms") or 0.0)))
    status_counts = _status_counts(rows)
    payload = {
        "ok": True,
        "generated_at": _now(),
        "mode": "read_only_api_capacity_probe",
        "symbols": selected_symbols,
        "requests_planned": safe_requests,
        "requests_completed": len(rows),
        "max_parallel": safe_parallel,
        "timeout_seconds": safe_timeout,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "status_counts": status_counts,
        "latency": _latency_stats(rows),
        "rate_limit_headers_seen": [row.get("rate_limit_headers") for row in rows if row.get("rate_limit_headers")],
        "recommendation": _recommendation(rows, safe_parallel),
        "sample_rows": rows[: min(len(rows), 40)],
        "would_trade": False,
        "would_write_db": False,
        "would_call_signed_endpoint": False,
        "writes_performed": 0,
    }
    if write_snapshot:
        JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        payload["snapshot_path"] = str(JSON_OUT)
        payload["writes_performed"] = 1
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Aster public API capacity probe.")
    parser.add_argument("--symbols", default="BTCUSDT,LABUSDT,INJUSDT")
    parser.add_argument("--requests", type=int, default=28)
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=int, default=8)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    payload = get_aster_api_capacity_probe_preview(
        symbols=args.symbols,
        requests=args.requests,
        max_parallel=args.max_parallel,
        timeout_seconds=args.timeout_seconds,
        write_snapshot=not args.no_write,
    )
    rec = payload.get("recommendation") or {}
    print(
        f"aster_api_capacity status={rec.get('capacity_status')} "
        f"requests={payload.get('requests_completed')} "
        f"parallel={payload.get('max_parallel')} "
        f"latency_p95={payload.get('latency', {}).get('p95_ms')}ms "
        f"statuses={payload.get('status_counts')} "
        f"recommended_runners={rec.get('recommended_parallel_runners')}"
    )
    if payload.get("snapshot_path"):
        print(f"json={payload.get('snapshot_path')}")


if __name__ == "__main__":
    main()
