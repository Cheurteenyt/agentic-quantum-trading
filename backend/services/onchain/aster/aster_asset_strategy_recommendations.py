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

VOLATILE_JSON = BASE_DIR / "aster_volatile_crypto_discovery_latest.json"
QUEUE_JSON = BASE_DIR / "aster_candidate_validation_queue_latest.json"
JSON_OUT = BASE_DIR / "aster_asset_strategy_recommendations_latest.json"
CSV_OUT = BASE_DIR / "aster_asset_strategy_recommendations_latest.csv"
HTML_OUT = DOCS_DIR / "core-equity-aster-asset-strategy-recommendations.html"

DISCOVERY_PATTERNS = [
    "paper_trading_strategy_discovery_*_v2.csv",
    "paper_trading_strategy_discovery_*_progress_v2.csv",
]

MEME_BASES = {
    "1000BONK",
    "1000FLOKI",
    "1000LUNC",
    "1000PEPE",
    "1000SATS",
    "ACT",
    "BOME",
    "BONK",
    "BRETT",
    "DOGE",
    "FLOKI",
    "MEME",
    "MEW",
    "MOG",
    "NEIRO",
    "PEPE",
    "PNUT",
    "POPCAT",
    "SHIB",
    "TOSHI",
    "TURBO",
    "WIF",
}
MAJOR_BASES = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "TON", "TRX"}
COMMODITY_BASES = {"XAU", "XAG", "CLU", "BZU"}
EQUITY_BASES = {
    "AAPL",
    "AMD",
    "AMZN",
    "COIN",
    "CRCL",
    "DRAM",
    "GOOGL",
    "INTC",
    "META",
    "MSFT",
    "MSTR",
    "MRVL",
    "NVDA",
    "QQQ",
    "RKLB",
    "SDNK",
    "TSLA",
}


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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_csv(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row, source_file=path.name) for row in csv.DictReader(handle)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _base(symbol: Any) -> str:
    clean = "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())
    for suffix in ("USDT", "USD1", "USDC"):
        if clean.endswith(suffix):
            return clean[: -len(suffix)]
    return clean


def _asset_category(symbol: str, volatility: dict[str, Any] | None) -> str:
    base = _base(symbol)
    if base in COMMODITY_BASES:
        return "commodity"
    if base in EQUITY_BASES:
        return "equity_synthetic"
    if base in MEME_BASES or base.startswith("1000"):
        return "memecoin"
    if base in MAJOR_BASES:
        return "major_crypto"
    if volatility and _float(volatility.get("volatility_score")) >= 65:
        return "volatile_altcoin"
    return "altcoin"


def _strategy_score(row: dict[str, Any]) -> float:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = min(_float(row.get("profit_factor")), 20.0)
    wr = _float(row.get("win_rate"))
    closed = _int(row.get("closed_trades"))
    dd = _float(row.get("max_drawdown_usd"))
    mark = str(row.get("mark_index_verdict") or "not_checked")
    ws = str(row.get("ws_quality_verdict") or "not_checked")
    exchange = str(row.get("exchange_filter_verdict") or "not_checked")
    score = roi * 1.2 + pf * 4.0 + wr * 22.0 + min(closed, 80) * 0.25 - dd * 0.16
    if mark == "mark_index_confirmed":
        score += 8
    elif mark == "mark_index_watch":
        score += 2
    elif mark == "mark_index_rejected":
        score -= 35
    if ws == "ws_forward_ready":
        score += 7
    elif ws == "ws_forward_risky":
        score -= 16
    if exchange == "ok":
        score += 4
    elif exchange == "blocked":
        score -= 30
    if closed < 8 or roi <= 0 or pf < 1.2:
        score -= 30
    return round(max(0.0, score), 3)


def _load_backtest_rows() -> list[dict[str, Any]]:
    seen_paths: set[Path] = set()
    rows: list[dict[str, Any]] = []
    for pattern in DISCOVERY_PATTERNS:
        for path in sorted(BASE_DIR.glob(pattern)):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            rows.extend(_read_csv(path))
    return rows


def _best_backtest_by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    seen_profiles: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        profile = str(row.get("strategy_profile_id") or row.get("strategy_profile_key") or "")
        if profile and profile in seen_profiles:
            continue
        if profile:
            seen_profiles.add(profile)
        row["asset_strategy_score"] = _strategy_score(row)
        current = best.get(symbol)
        if current is None or _float(row.get("asset_strategy_score")) > _float(current.get("asset_strategy_score")):
            best[symbol] = row
    return best


def _volatility_map() -> dict[str, dict[str, Any]]:
    payload = _load_json(VOLATILE_JSON)
    rows = []
    for section in ("top_volatile_crypto", "backtest_candidates", "top_by_abs_price_change"):
        rows.extend([row for row in payload.get(section) or [] if isinstance(row, dict)])
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol not in best or _float(row.get("volatility_score")) > _float(best[symbol].get("volatility_score")):
            best[symbol] = row
    return best


def _queue_map() -> dict[str, dict[str, Any]]:
    payload = _load_json(QUEUE_JSON)
    rows = []
    for section in ("next_validation_queue", "top_by_symbol", "rows"):
        rows.extend([row for row in payload.get(section) or [] if isinstance(row, dict)])
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol not in best or _float(row.get("validation_score")) > _float(best[symbol].get("validation_score")):
            best[symbol] = row
    return best


def _recommendation(category: str, symbol: str, volatility: dict[str, Any] | None, best: dict[str, Any] | None) -> dict[str, Any]:
    vol_score = _float((volatility or {}).get("volatility_score"))
    move = _float((volatility or {}).get("price_change_pct_24h"))
    roi = _float((best or {}).get("roi_pct_on_paper_balance"))
    pf = _float((best or {}).get("profit_factor"))
    interval = str((best or {}).get("interval") or "")
    reasons: list[str] = []

    if category == "memecoin":
        family = "memecoin_volatility_breakout_plus_fade_review"
        runner = "volatile_crypto_discovery"
        timeframes = "15m,30m,1h,2h"
        risk = "small_size_only_high_volatility"
        reasons.append("memecoin_detected")
        if move < -20:
            reasons.append("large_negative_move_test_short_fade_and_bounce")
        elif move > 20:
            reasons.append("large_positive_move_test_breakout_but_watch_top_fishing")
    elif category == "volatile_altcoin":
        family = "volatile_altcoin_momentum"
        runner = "volatile_crypto_discovery"
        timeframes = "30m,1h,2h,3h"
        risk = "medium_risk_reality_checks_required"
        reasons.append("high_24h_volatility_score")
    elif category == "major_crypto":
        family = "liquid_crypto_momentum_or_mean_reversion"
        runner = "core_prod_mark_bbo"
        timeframes = "30m,1h,2h,4h"
        risk = "lower_spread_but_lower_edge"
        reasons.append("major_liquid_crypto")
    elif category == "commodity":
        family = "slow_trend_macro_commodity"
        runner = "macro_equity_prod_mark_bbo"
        timeframes = "2h,3h,4h,5h,6h"
        risk = "avoid_low_tf_noise"
        reasons.append("commodity_needs_slow_timeframes")
    elif category == "equity_synthetic":
        family = "slow_trend_equity_synthetic"
        runner = "macro_equity_prod_mark_bbo"
        timeframes = "2h,3h,4h,5h,6h"
        risk = "thin_market_and_session_gap_review"
        reasons.append("equity_synthetic_needs_mark_ws_gap_checks")
    else:
        family = "altcoin_discovery"
        runner = "aster_v2_prod"
        timeframes = "30m,1h,2h,3h"
        risk = "standard_research"
        reasons.append("generic_altcoin")

    if best:
        if roi > 10 and pf > 1.5:
            reasons.append(f"existing_backtest_promising_{interval}")
        elif roi <= 0 or pf < 1.2:
            reasons.append("existing_backtest_weak_rework_needed")
    if vol_score >= 80:
        reasons.append("extreme_current_volatility")

    return {
        "recommended_strategy_family": family,
        "recommended_runner_tag": runner,
        "recommended_timeframes": timeframes,
        "risk_note": risk,
        "recommendation_reason": ",".join(reasons),
    }


def get_aster_asset_strategy_recommendations_preview(dry_run: bool = True, top_n: int = 120) -> dict[str, Any]:
    if not dry_run:
        return {"ok": False, "status": "blocked", "blockers": ["dry_run_required"]}

    volatility = _volatility_map()
    queue = _queue_map()
    best = _best_backtest_by_symbol(_load_backtest_rows())
    symbols = sorted(set(volatility) | set(queue) | set(best))
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        vol = volatility.get(symbol)
        backtest = best.get(symbol)
        queued = queue.get(symbol)
        category = _asset_category(symbol, vol)
        rec = _recommendation(category, symbol, vol, backtest)
        rows.append(
            {
                "symbol": symbol,
                "base_asset": _base(symbol),
                "asset_category": category,
                "is_memecoin": category == "memecoin",
                "volatility_score": (vol or {}).get("volatility_score"),
                "price_change_pct_24h": (vol or {}).get("price_change_pct_24h"),
                "quote_volume_24h": (vol or {}).get("quote_volume_24h"),
                "best_strategy_score": (backtest or {}).get("asset_strategy_score"),
                "best_strategy_profile_id": (backtest or {}).get("strategy_profile_id") or (backtest or {}).get("strategy_profile_key"),
                "best_output_tag": (backtest or {}).get("output_tag"),
                "best_interval": (backtest or {}).get("interval"),
                "best_side": (backtest or {}).get("side"),
                "best_roi_pct": (backtest or {}).get("roi_pct_on_paper_balance"),
                "best_win_rate": (backtest or {}).get("win_rate"),
                "best_profit_factor": (backtest or {}).get("profit_factor"),
                "best_closed_trades": (backtest or {}).get("closed_trades"),
                "next_validation_action": (queued or {}).get("next_validation_action"),
                "validation_score": (queued or {}).get("validation_score"),
                **rec,
            }
        )
    rows.sort(
        key=lambda row: (
            1 if row.get("is_memecoin") else 0,
            _float(row.get("volatility_score")),
            _float(row.get("best_strategy_score")),
        ),
        reverse=True,
    )
    selected = rows[: max(1, min(_int(top_n, 120), 500))]
    counts: dict[str, int] = {}
    for row in selected:
        category = str(row.get("asset_category") or "unknown")
        counts[category] = counts.get(category, 0) + 1
    memecoin_symbols = [row["symbol"] for row in selected if row.get("is_memecoin")]
    volatile_symbols = [row["symbol"] for row in selected if row.get("recommended_runner_tag") == "volatile_crypto_discovery"]
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "classify_assets_merge_volatility_backtests_validation_queue_recommend_next_strategy_family",
        "summary": {
            "symbols_ranked": len(rows),
            "rows_returned": len(selected),
            "category_counts": counts,
            "memecoin_symbols": len(memecoin_symbols),
            "volatile_runner_symbols": len(volatile_symbols),
        },
        "memecoin_symbols_csv": ",".join(memecoin_symbols[:40]),
        "volatile_runner_symbols_csv": ",".join(volatile_symbols[:40]),
        "rows": selected,
        "memecoins": [row for row in selected if row.get("is_memecoin")],
        "safety": {
            "would_write_db": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "local_artifacts_only": True,
        },
    }


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _table(rows: list[dict[str, Any]], limit: int = 80) -> str:
    headers = [
        "category",
        "symbol",
        "vol",
        "24h",
        "best tag",
        "tf",
        "roi",
        "wr",
        "pf",
        "validation",
        "recommended strategy",
        "timeframes",
    ]
    body = []
    for row in rows[:limit]:
        cells = [
            row.get("asset_category"),
            row.get("symbol"),
            row.get("volatility_score"),
            row.get("price_change_pct_24h"),
            row.get("best_output_tag"),
            row.get("best_interval"),
            row.get("best_roi_pct"),
            row.get("best_win_rate"),
            row.get("best_profit_factor"),
            row.get("next_validation_action"),
            row.get("recommended_strategy_family"),
            row.get("recommended_timeframes"),
        ]
        body.append("<tr>" + "".join(f"<td>{_cell(value)}</td>" for value in cells) + "</tr>")
    return "<table><thead><tr>" + "".join(f"<th>{_cell(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    counts = summary.get("category_counts") or {}
    count_html = "".join(f"<span><b>{_cell(key)}</b> {_cell(value)}</span>" for key, value in sorted(counts.items()))
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aster - Asset strategy recommendations</title>
  <style>
    body {{ margin:0; background:#0b1017; color:#edf4ff; font-family:Verdana,Arial,sans-serif; }}
    main {{ max-width:1500px; margin:0 auto; padding:32px 28px 72px; }}
    h1 {{ margin:0 0 8px; }}
    .lead {{ color:#a7b7c9; max-width:1040px; line-height:1.6; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    .card {{ background:#141d29; border:1px solid #28364a; border-radius:14px; padding:16px; }}
    .card span {{ display:block; color:#8ea1b8; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .card strong {{ display:block; margin-top:8px; font-size:24px; }}
    .counts {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0; }}
    .counts span {{ background:#172537; border:1px solid #30445f; border-radius:999px; padding:8px 12px; }}
    table {{ width:100%; border-collapse:collapse; margin-top:16px; background:#101822; border:1px solid #263548; }}
    th,td {{ padding:9px 10px; border-bottom:1px solid #263548; text-align:left; font-size:13px; }}
    th {{ background:#172131; color:#93a8c2; }}
    code {{ color:#ffd38a; word-break:break-all; }}
    .note {{ color:#a7b7c9; line-height:1.55; margin-top:18px; }}
  </style>
</head>
<body>
<main>
  <h1>Aster - Recommandations strategie par actif</h1>
  <p class="lead">Ce rapport relie les resultats de backtest, la volatilite Aster, les memecoins et la queue de validation. Objectif: savoir quelle strategie tester selon l'actif, au lieu de lancer la meme grille partout.</p>
  <div class="cards">
    <div class="card"><span>Symboles classes</span><strong>{_cell(summary.get("symbols_ranked"))}</strong></div>
    <div class="card"><span>Memecoins</span><strong>{_cell(summary.get("memecoin_symbols"))}</strong></div>
    <div class="card"><span>Volatile runner</span><strong>{_cell(summary.get("volatile_runner_symbols"))}</strong></div>
    <div class="card"><span>Rows</span><strong>{_cell(summary.get("rows_returned"))}</strong></div>
  </div>
  <div class="counts">{count_html}</div>
  <h2>Memecoin symbols CSV</h2>
  <p><code>{_cell(payload.get("memecoin_symbols_csv"))}</code></p>
  <h2>Volatile runner symbols CSV</h2>
  <p><code>{_cell(payload.get("volatile_runner_symbols_csv"))}</code></p>
  <h2>Recommandations</h2>
  {_table(payload.get("rows") or [], 120)}
  <p class="note">Lecture: la recommandation ne valide pas une strategie. Elle indique quel runner et quelles timeframes sont logiques pour cet actif. La preuve reste la validation mark/index, WS, microstructure et forward paper.</p>
</main>
</body>
</html>"""


def _write_csv(rows: list[dict[str, Any]]) -> None:
    fields = [
        "symbol",
        "base_asset",
        "asset_category",
        "is_memecoin",
        "volatility_score",
        "price_change_pct_24h",
        "quote_volume_24h",
        "best_strategy_score",
        "best_output_tag",
        "best_interval",
        "best_side",
        "best_roi_pct",
        "best_win_rate",
        "best_profit_factor",
        "best_closed_trades",
        "next_validation_action",
        "validation_score",
        "recommended_strategy_family",
        "recommended_runner_tag",
        "recommended_timeframes",
        "risk_note",
        "recommendation_reason",
        "best_strategy_profile_id",
    ]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_aster_asset_strategy_recommendations(top_n: int = 150) -> dict[str, Any]:
    payload = get_aster_asset_strategy_recommendations_preview(dry_run=True, top_n=top_n)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(list(payload.get("rows") or []))
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_aster_asset_strategy_recommendations()
    summary = payload.get("summary") or {}
    print(
        f"[{payload.get('generated_at')}] symbols={summary.get('symbols_ranked')} "
        f"memecoins={summary.get('memecoin_symbols')} volatile={summary.get('volatile_runner_symbols')} "
        f"csv={CSV_OUT} html={HTML_OUT}"
    )
    if payload.get("memecoin_symbols_csv"):
        print(f"memecoins={payload.get('memecoin_symbols_csv')}")


if __name__ == "__main__":
    main()
