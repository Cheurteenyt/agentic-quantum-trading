from __future__ import annotations

import json
import argparse
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
JSON_OUT = BASE_DIR / "aster_microstructure_replay_validator_latest.json"
ASTER_FAPI_V3_BASE_URL = "https://fapi.asterdex.com"
USER_AGENT = "CoreEquityAsterMicrostructureReplayValidator/0.1"

DEFAULT_CHAMPIONS = [
    {"symbol": "LABUSDT", "interval": "5h", "side": "long"},
    {"symbol": "INTCUSDT", "interval": "30m", "side": "long"},
    {"symbol": "CRCLUSDT", "interval": "2h", "side": "long"},
]

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


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 6) -> float | None:
    num = _as_float(value)
    return round(num, digits) if num is not None else None


def _clean_symbol(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())[:32]


def _clean_interval(value: Any) -> str:
    clean = str(value or "1h").strip().lower()
    return clean if clean in INTERVAL_MS else "1h"


def _clean_side(value: Any) -> str:
    clean = str(value or "long").strip().lower()
    return clean if clean in {"long", "short"} else "long"


def _parse_champions(champions: Any, limit: int) -> list[dict[str, str]]:
    if champions is None or champions == "":
        raw: list[Any] = DEFAULT_CHAMPIONS
    elif isinstance(champions, str):
        raw = [item for item in champions.replace(";", ",").split(",") if item.strip()]
    elif isinstance(champions, list):
        raw = champions
    else:
        raw = [champions]

    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        if isinstance(item, dict):
            symbol = _clean_symbol(item.get("symbol"))
            interval = _clean_interval(item.get("interval"))
            side = _clean_side(item.get("side"))
        else:
            parts = str(item or "").replace("|", ":").split(":")
            symbol = _clean_symbol(parts[0] if parts else "")
            interval = _clean_interval(parts[1] if len(parts) > 1 else "1h")
            side = _clean_side(parts[2] if len(parts) > 2 else "long")
        key = (symbol, interval, side)
        if symbol and key not in seen:
            seen.add(key)
            out.append({"symbol": symbol, "interval": interval, "side": side})
        if len(out) >= limit:
            break
    return out or DEFAULT_CHAMPIONS[:limit]


def _url(path: str, params: dict[str, Any]) -> str:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    return f"{ASTER_FAPI_V3_BASE_URL}{path}?{query}"


def _fetch_json(path: str, params: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    request = urllib.request.Request(_url(path, params), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=max(1, min(int(timeout_seconds or 10), 15))) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = {
                key: response.headers.get(key)
                for key in ("x-mbx-used-weight-1m", "x-mbx-used-weight", "retry-after")
                if response.headers.get(key) is not None
            }
        return {
            "ok": True,
            "status": "ok",
            "http_status": int(response.status),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "payload": payload,
            "rate_limit_headers": headers,
        }
    except urllib.error.HTTPError as exc:
        status = {403: "blocked_by_aster", 404: "not_found", 418: "ip_auto_banned", 429: "rate_limited"}.get(
            int(exc.code),
            f"http_{int(exc.code)}",
        )
        return {
            "ok": False,
            "status": status,
            "http_status": int(exc.code),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "retry_after": exc.headers.get("retry-after"),
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "status": "request_failed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": type(exc).__name__,
        }


def _trade_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    parsed: list[dict[str, float]] = []
    for row in rows:
        price = _as_float(row.get("p"))
        qty = _as_float(row.get("q"))
        ts = _as_int(row.get("T"))
        if price is None or qty is None or ts is None:
            continue
        parsed.append({"price": price, "qty": qty, "ts": float(ts), "quote": price * qty})
    parsed.sort(key=lambda row: row["ts"])
    if not parsed:
        return {"trade_count": 0, "quote_volume_usd": 0.0, "status": "empty"}

    gaps = [(parsed[index]["ts"] - parsed[index - 1]["ts"]) / 1000 for index in range(1, len(parsed))]
    prices = [row["price"] for row in parsed]
    quotes = [row["quote"] for row in parsed]
    window_seconds = max(0.0, (parsed[-1]["ts"] - parsed[0]["ts"]) / 1000)
    price_change_bps = ((prices[-1] - prices[0]) / prices[0] * 10_000) if prices[0] else 0.0

    def pctl(values: list[float], q: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
        return ordered[index]

    return {
        "trade_count": len(parsed),
        "coverage_start": datetime.fromtimestamp(parsed[0]["ts"] / 1000, timezone.utc).isoformat(),
        "coverage_end": datetime.fromtimestamp(parsed[-1]["ts"] / 1000, timezone.utc).isoformat(),
        "window_seconds": round(window_seconds, 3),
        "quote_volume_usd": round(sum(quotes), 4),
        "avg_trade_notional_usd": round(statistics.mean(quotes), 6) if quotes else None,
        "median_trade_notional_usd": round(statistics.median(quotes), 6) if quotes else None,
        "min_price": min(prices),
        "max_price": max(prices),
        "first_price": prices[0],
        "last_price": prices[-1],
        "price_change_bps": round(price_change_bps, 6),
        "max_gap_seconds": round(max(gaps), 3) if gaps else None,
        "p95_gap_seconds": round(pctl(gaps, 0.95), 3) if gaps else None,
        "avg_gap_seconds": round(statistics.mean(gaps), 3) if gaps else None,
    }


def _book_metrics(payload: Any, side: str, position_notional_usd: float) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "missing_order_book"}
    bids = payload.get("bids") if isinstance(payload.get("bids"), list) else []
    asks = payload.get("asks") if isinstance(payload.get("asks"), list) else []
    best_bid = _as_float((bids[0] or [None])[0]) if bids else None
    best_ask = _as_float((asks[0] or [None])[0]) if asks else None
    if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
        return {"status": "missing_best_bid_ask"}
    mid = (best_bid + best_ask) / 2
    spread_bps = (best_ask - best_bid) / mid * 10_000 if mid else None
    top10_bid_depth = sum(((_as_float(row[0]) or 0.0) * (_as_float(row[1]) or 0.0)) for row in bids[:10])
    top10_ask_depth = sum(((_as_float(row[0]) or 0.0) * (_as_float(row[1]) or 0.0)) for row in asks[:10])

    book_side = asks if side == "long" else bids
    remaining = max(1.0, float(position_notional_usd or 100.0))
    filled_quote = 0.0
    filled_qty = 0.0
    levels_used = 0
    for level in book_side:
        price = _as_float(level[0] if len(level) > 0 else None)
        qty = _as_float(level[1] if len(level) > 1 else None)
        if price is None or qty is None or price <= 0 or qty <= 0:
            continue
        level_quote = price * qty
        take_quote = min(remaining, level_quote)
        filled_quote += take_quote
        filled_qty += take_quote / price
        remaining -= take_quote
        levels_used += 1
        if remaining <= 1e-9:
            break
    fillable = remaining <= 1e-6 and filled_qty > 0
    vwap = filled_quote / filled_qty if filled_qty else None
    if vwap is None:
        slippage_bps = None
    elif side == "long":
        slippage_bps = (vwap - mid) / mid * 10_000
    else:
        slippage_bps = (mid - vwap) / mid * 10_000
    return {
        "status": "ok",
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid,
        "spread_bps": _round(spread_bps, 6),
        "top10_bid_depth_usd": round(top10_bid_depth, 4),
        "top10_ask_depth_usd": round(top10_ask_depth, 4),
        "top10_depth_usd": round(top10_bid_depth + top10_ask_depth, 4),
        "position_notional_usd": round(max(1.0, float(position_notional_usd or 100.0)), 4),
        "fillable_at_book_depth": fillable,
        "simulated_fill_vwap": _round(vwap, 10),
        "simulated_slippage_bps": _round(slippage_bps, 6),
        "levels_used_for_fill": levels_used,
        "unfilled_notional_usd": round(max(0.0, remaining), 6),
    }


def _decision(
    trade: dict[str, Any],
    book: dict[str, Any],
    *,
    min_trades: int,
    min_quote_volume_usd: float,
    max_spread_bps: float,
    max_slippage_bps: float,
    max_gap_seconds: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    trade_count = _as_int(trade.get("trade_count")) or 0
    quote_volume = _as_float(trade.get("quote_volume_usd")) or 0.0
    spread = _as_float(book.get("spread_bps"))
    slippage = _as_float(book.get("simulated_slippage_bps"))
    max_gap = _as_float(trade.get("max_gap_seconds"))
    p95_gap = _as_float(trade.get("p95_gap_seconds"))
    depth = _as_float(book.get("top10_depth_usd")) or 0.0
    position = _as_float(book.get("position_notional_usd")) or 100.0

    if trade_count < min_trades:
        blockers.append("not_enough_trades")
    if quote_volume < min_quote_volume_usd:
        blockers.append("thin_liquidity")
    if book.get("status") != "ok" or not book.get("fillable_at_book_depth"):
        blockers.append("thin_liquidity")
    if spread is not None and spread > max_spread_bps:
        blockers.append("wide_spread")
    if slippage is not None and slippage > max_slippage_bps:
        blockers.append("excessive_slippage")
    if max_gap is not None and max_gap > max_gap_seconds:
        blockers.append("gap_risk")
    if p95_gap is not None and p95_gap > max_gap_seconds / 2:
        warnings.append("elevated_p95_trade_gap")
    if depth and depth < position * 20:
        warnings.append("shallow_top10_depth_vs_position")

    if "not_enough_trades" in blockers:
        verdict = "not_enough_trades"
    elif "thin_liquidity" in blockers or "wide_spread" in blockers or "excessive_slippage" in blockers:
        verdict = "thin_liquidity"
    elif "gap_risk" in blockers:
        verdict = "gap_risk"
    else:
        verdict = "microstructure_ok"
    return {"verdict": verdict, "blockers": sorted(set(blockers)), "warnings": sorted(set(warnings))}


def _fetch_trades(symbol: str, interval: str, validation_bars: int, trade_limit: int, timeout_seconds: int) -> dict[str, Any]:
    interval_ms = INTERVAL_MS.get(interval, INTERVAL_MS["1h"])
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (interval_ms * max(1, min(int(validation_bars or 3), 24)))
    limit = max(10, min(int(trade_limit or 500), 1000))
    result = _fetch_json(
        "/fapi/v3/aggTrades",
        {"symbol": symbol, "startTime": start_ms, "endTime": now_ms, "limit": limit},
        timeout_seconds,
    )
    payload = result.get("payload")
    if result.get("ok") and isinstance(payload, list):
        return {**result, "source": "aggTrades", "trades": payload, "start_time_ms": start_ms, "end_time_ms": now_ms}

    fallback = _fetch_json("/fapi/v3/historicalTrades", {"symbol": symbol, "limit": limit}, timeout_seconds)
    fallback_payload = fallback.get("payload")
    if fallback.get("ok") and isinstance(fallback_payload, list):
        return {**fallback, "source": "historicalTrades", "trades": fallback_payload, "start_time_ms": None, "end_time_ms": now_ms}
    return {**result, "source": "aggTrades", "fallback_status": fallback.get("status"), "trades": []}


def get_aster_microstructure_replay_validator_preview(
    champions: Any = None,
    dry_run: bool = True,
    position_notional_usd: float = 100.0,
    validation_bars: int = 3,
    trade_limit: int = 500,
    depth_limit: int = 50,
    timeout_seconds: int = 10,
    rate_limit_delay_ms: int = 250,
    min_trades: int = 80,
    min_quote_volume_usd: float = 25_000.0,
    max_spread_bps: float = 20.0,
    max_slippage_bps: float = 15.0,
    max_gap_seconds: float = 120.0,
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
    safe_champions = _parse_champions(champions, 20)
    timeout = max(1, min(int(timeout_seconds or 10), 15))
    delay = max(0, min(int(rate_limit_delay_ms or 250), 2_000)) / 1000
    safe_notional = max(5.0, min(float(position_notional_usd or 100.0), 10_000.0))
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, champion in enumerate(safe_champions):
        if index and delay:
            time.sleep(delay)
        symbol = champion["symbol"]
        interval = champion["interval"]
        side = champion["side"]
        trades_result = _fetch_trades(symbol, interval, validation_bars, trade_limit, timeout)
        depth_result = _fetch_json(
            "/fapi/v3/depth",
            {"symbol": symbol, "limit": max(5, min(int(depth_limit or 50), 100))},
            timeout,
        )
        if not trades_result.get("ok") or not depth_result.get("ok"):
            failures.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "side": side,
                    "trades_status": trades_result.get("status"),
                    "depth_status": depth_result.get("status"),
                }
            )
        trade = _trade_metrics(trades_result.get("trades") or [])
        book = _book_metrics(depth_result.get("payload"), side, safe_notional)
        decision = _decision(
            trade,
            book,
            min_trades=max(1, int(min_trades or 80)),
            min_quote_volume_usd=max(0.0, float(min_quote_volume_usd or 0)),
            max_spread_bps=max(0.1, float(max_spread_bps or 20)),
            max_slippage_bps=max(0.1, float(max_slippage_bps or 15)),
            max_gap_seconds=max(1.0, float(max_gap_seconds or 120)),
        )
        rows.append(
            {
                "symbol": symbol,
                "interval": interval,
                "side": side,
                "trade_source": trades_result.get("source"),
                "trade_fetch_status": trades_result.get("status"),
                "depth_fetch_status": depth_result.get("status"),
                "trade_latency_ms": trades_result.get("latency_ms"),
                "depth_latency_ms": depth_result.get("latency_ms"),
                "validation_bars": max(1, min(int(validation_bars or 3), 24)),
                "trade_limit": max(10, min(int(trade_limit or 500), 1000)),
                "metrics": {"trades": trade, "book": book},
                **decision,
            }
        )

    summary = {
        "microstructure_ok": sum(1 for row in rows if row.get("verdict") == "microstructure_ok"),
        "thin_liquidity": sum(1 for row in rows if row.get("verdict") == "thin_liquidity"),
        "gap_risk": sum(1 for row in rows if row.get("verdict") == "gap_risk"),
        "not_enough_trades": sum(1 for row in rows if row.get("verdict") == "not_enough_trades"),
        "fetch_failures": len(failures),
    }
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "read_only_public_aggTrades_depth_fillability_check_for_backtest_champions",
        "champions_tested": len(rows),
        "summary": summary,
        "thresholds": {
            "position_notional_usd": safe_notional,
            "min_trades": max(1, int(min_trades or 80)),
            "min_quote_volume_usd": max(0.0, float(min_quote_volume_usd or 0)),
            "max_spread_bps": max(0.1, float(max_spread_bps or 20)),
            "max_slippage_bps": max(0.1, float(max_slippage_bps or 15)),
            "max_gap_seconds": max(1.0, float(max_gap_seconds or 120)),
        },
        "rows": rows,
        "failures": failures,
        "next_action": "promote_only_microstructure_ok_lanes_or_reduce_size_for_thin_liquidity",
        "safety": {
            "would_write": False,
            "writes_performed": 0,
            "would_call_signed_endpoint": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "source_policy": "public_aster_rest_read_only",
        },
    }


def write_aster_microstructure_replay_validator_snapshot(**kwargs: Any) -> dict[str, Any]:
    payload = get_aster_microstructure_replay_validator_preview(**kwargs)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Aster microstructure validator for champion lanes.")
    parser.add_argument(
        "--champions",
        default=None,
        help="Comma-separated SYMBOL:interval:side list, for example LABUSDT:5h:long,INTCUSDT:30m:long.",
    )
    parser.add_argument("--position-notional-usd", type=float, default=100.0)
    parser.add_argument("--validation-bars", type=int, default=3)
    parser.add_argument("--trade-limit", type=int, default=500)
    parser.add_argument("--min-trades", type=int, default=80)
    parser.add_argument("--min-quote-volume-usd", type=float, default=25_000.0)
    parser.add_argument("--max-spread-bps", type=float, default=20.0)
    parser.add_argument("--max-slippage-bps", type=float, default=15.0)
    parser.add_argument("--max-gap-seconds", type=float, default=120.0)
    args = parser.parse_args()
    payload = write_aster_microstructure_replay_validator_snapshot(
        champions=args.champions,
        position_notional_usd=args.position_notional_usd,
        validation_bars=args.validation_bars,
        trade_limit=args.trade_limit,
        min_trades=args.min_trades,
        min_quote_volume_usd=args.min_quote_volume_usd,
        max_spread_bps=args.max_spread_bps,
        max_slippage_bps=args.max_slippage_bps,
        max_gap_seconds=args.max_gap_seconds,
    )
    print(
        f"[{payload['generated_at']}] tested={payload['champions_tested']} "
        f"summary={payload['summary']} json={JSON_OUT}"
    )


if __name__ == "__main__":
    main()
