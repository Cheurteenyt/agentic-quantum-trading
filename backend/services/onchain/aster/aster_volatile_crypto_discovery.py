from __future__ import annotations

import csv
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.onchain.aster.data_sources.public_universe_snapshot import get_aster_public_universe_snapshot_preview


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"

JSON_OUT = BASE_DIR / "aster_volatile_crypto_discovery_latest.json"
CSV_OUT = BASE_DIR / "aster_volatile_crypto_discovery_latest.csv"
HTML_OUT = DOCS_DIR / "core-equity-aster-volatile-crypto-discovery.html"

NON_CRYPTO_BASES = {
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
    "MRVL",
    "MSTR",
    "NVDA",
    "QQQ",
    "RKLB",
    "SDNK",
    "TSLA",
    "XAG",
    "XAU",
    "CLU",
    "BZU",
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


def _base_asset(row: dict[str, Any]) -> str:
    base = str(row.get("base_asset") or "").upper()
    if base:
        return base
    symbol = str(row.get("symbol") or "").upper()
    for suffix in ("USDT", "USD1", "USDC"):
        if symbol.endswith(suffix):
            return symbol[: -len(suffix)]
    return symbol


def _is_crypto(row: dict[str, Any]) -> bool:
    symbol = str(row.get("symbol") or "").upper()
    quote = str(row.get("quote_asset") or "").upper()
    base = _base_asset(row)
    if not symbol.endswith(("USDT", "USD1", "USDC")):
        return False
    if quote and quote not in {"USDT", "USD1", "USDC"}:
        return False
    return base not in NON_CRYPTO_BASES


def _log_score(value: float, scale: float) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, math.log10(value) / scale)


def _volatility_score(row: dict[str, Any]) -> float:
    abs_change = abs(_float(row.get("price_change_pct_24h")))
    quote_volume = _float(row.get("quote_volume_24h"))
    trade_count = _float(row.get("trade_count_24h"))
    spread_bps = _float(row.get("spread_bps"), 999.0)
    premium_bps = abs(_float(row.get("premium_bps")))
    funding_rate = abs(_float(row.get("last_funding_rate")))

    score = 0.0
    score += min(abs_change / 25.0, 1.0) * 42.0
    score += _log_score(quote_volume, 8.0) * 24.0
    score += _log_score(trade_count, 6.0) * 12.0
    score += min(premium_bps / 80.0, 1.0) * 8.0
    score += min(funding_rate / 0.0015, 1.0) * 8.0
    if spread_bps <= 5:
        score += 8.0
    elif spread_bps <= 15:
        score += 4.0
    elif spread_bps > 50:
        score -= 18.0
    elif spread_bps > 30:
        score -= 8.0
    return round(max(0.0, min(score, 100.0)), 3)


def _verdict(row: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    abs_change = abs(_float(row.get("price_change_pct_24h")))
    quote_volume = _float(row.get("quote_volume_24h"))
    spread_bps = _float(row.get("spread_bps"), 999.0)
    score = _float(row.get("volatility_score"))

    if quote_volume < 50_000:
        reasons.append("low_quote_volume")
    if spread_bps > 50:
        reasons.append("wide_spread")
    if abs_change < 5:
        reasons.append("low_24h_move")

    if quote_volume < 50_000 or spread_bps > 50:
        return "avoid_thin_or_wide", reasons
    if abs_change >= 20 and quote_volume >= 250_000:
        return "extreme_volatility_candidate", reasons
    if score >= 65 and abs_change >= 8:
        return "volatile_backtest_candidate", reasons
    if score >= 50 and abs_change >= 5:
        return "watchlist_candidate", reasons
    return "normal", reasons


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "symbol": row.get("symbol"),
        "base_asset": _base_asset(row),
        "quote_asset": row.get("quote_asset"),
        "quote_volume_24h": _float(row.get("quote_volume_24h")),
        "trade_count_24h": _int(row.get("trade_count_24h")),
        "price_change_pct_24h": _float(row.get("price_change_pct_24h")),
        "abs_price_change_pct_24h": abs(_float(row.get("price_change_pct_24h"))),
        "last_price": row.get("last_price"),
        "spread_bps": row.get("spread_bps"),
        "premium_bps": row.get("premium_bps"),
        "last_funding_rate": row.get("last_funding_rate"),
        "market_take_bound": row.get("market_take_bound"),
        "min_notional": row.get("min_notional"),
        "data_flags": ",".join(row.get("data_flags") or []),
    }
    out["volatility_score"] = _volatility_score(out)
    verdict, reasons = _verdict(out)
    out["volatility_verdict"] = verdict
    out["volatility_reasons"] = ",".join(reasons)
    return out


def get_aster_volatile_crypto_discovery_preview(
    dry_run: bool = True,
    timeout_seconds: int = 8,
    top_n: int = 50,
) -> dict[str, Any]:
    if not dry_run:
        return {"ok": False, "status": "blocked", "blockers": ["dry_run_required"]}

    safe_top = max(1, min(int(top_n or 50), 150))
    universe = get_aster_public_universe_snapshot_preview(
        dry_run=True,
        timeout_seconds=max(1, min(int(timeout_seconds or 8), 15)),
        top_n=min(safe_top, 100),
        write_snapshot=False,
    )
    if not universe.get("ok"):
        return {
            "ok": False,
            "status": "universe_fetch_failed",
            "source_status": universe.get("status"),
            "dry_run": True,
            "would_execute_trade": False,
            "would_write_db": False,
        }

    source_rows = list(universe.get("all_research_universe") or [])
    crypto_rows = [_enrich(row) for row in source_rows if _is_crypto(row)]
    crypto_rows.sort(key=lambda row: (_float(row.get("volatility_score")), _float(row.get("abs_price_change_pct_24h"))), reverse=True)
    candidates = [
        row
        for row in crypto_rows
        if row.get("volatility_verdict") in {"extreme_volatility_candidate", "volatile_backtest_candidate", "watchlist_candidate"}
    ]
    verdict_counts: dict[str, int] = {}
    for row in crypto_rows:
        verdict = str(row.get("volatility_verdict") or "unknown")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    candidate_symbols = [str(row.get("symbol") or "") for row in candidates[:safe_top] if row.get("symbol")]
    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "official_public_aster_universe_rank_crypto_symbols_by_24h_move_volume_spread_premium_funding",
        "summary": {
            "source_symbols": len(source_rows),
            "crypto_symbols_ranked": len(crypto_rows),
            "candidate_symbols": len(candidates),
            "verdict_counts": verdict_counts,
            "top_symbol": crypto_rows[0].get("symbol") if crypto_rows else None,
            "top_score": crypto_rows[0].get("volatility_score") if crypto_rows else None,
        },
        "candidate_symbols_csv": ",".join(candidate_symbols),
        "top_volatile_crypto": crypto_rows[:safe_top],
        "backtest_candidates": candidates[:safe_top],
        "top_by_abs_price_change": sorted(
            crypto_rows,
            key=lambda row: _float(row.get("abs_price_change_pct_24h")),
            reverse=True,
        )[:safe_top],
        "safety": {
            "would_write_db": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "would_call_trade_endpoint": False,
            "public_rest_only": True,
        },
    }


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _table(rows: list[dict[str, Any]], limit: int = 60) -> str:
    headers = ["verdict", "score", "symbol", "24h move", "volume", "trades", "spread", "premium", "funding", "reasons"]
    body: list[str] = []
    for row in rows[:limit]:
        cells = [
            row.get("volatility_verdict"),
            row.get("volatility_score"),
            row.get("symbol"),
            row.get("price_change_pct_24h"),
            row.get("quote_volume_24h"),
            row.get("trade_count_24h"),
            row.get("spread_bps"),
            row.get("premium_bps"),
            row.get("last_funding_rate"),
            row.get("volatility_reasons"),
        ]
        body.append("<tr>" + "".join(f"<td>{_cell(value)}</td>" for value in cells) + "</tr>")
    return "<table><thead><tr>" + "".join(f"<th>{_cell(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    counts = summary.get("verdict_counts") or {}
    counts_html = "".join(f"<span><b>{_cell(key)}</b> {_cell(value)}</span>" for key, value in sorted(counts.items()))
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aster - Radar cryptos volatiles</title>
  <style>
    body {{ margin:0; background:#0b1017; color:#eef4ff; font-family:Verdana,Arial,sans-serif; }}
    main {{ max-width:1480px; margin:0 auto; padding:32px 28px 72px; }}
    h1 {{ margin:0 0 8px; }}
    .lead {{ color:#a9b8ca; max-width:980px; line-height:1.6; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    .card {{ background:#141d29; border:1px solid #283649; border-radius:14px; padding:16px; }}
    .card span {{ display:block; color:#8ea0b6; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .card strong {{ display:block; margin-top:8px; font-size:24px; }}
    .counts {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0; }}
    .counts span {{ background:#172537; border:1px solid #30445f; border-radius:999px; padding:8px 12px; }}
    table {{ width:100%; border-collapse:collapse; margin-top:16px; background:#101822; border:1px solid #27364a; }}
    th,td {{ padding:9px 10px; border-bottom:1px solid #263548; text-align:left; font-size:13px; }}
    th {{ background:#172131; color:#93a8c2; }}
    code {{ color:#ffd38a; word-break:break-all; }}
    .note {{ color:#a9b8ca; line-height:1.55; margin-top:18px; }}
  </style>
</head>
<body>
<main>
  <h1>Aster - Radar cryptos volatiles</h1>
  <p class="lead">Classement read-only des paires crypto Aster selon mouvement 24h, volume, nombre de trades, spread, premium mark/index et funding. Ce rapport sert a nourrir les backtests avec des actifs qui bougent vraiment.</p>
  <div class="cards">
    <div class="card"><span>Cryptos classees</span><strong>{_cell(summary.get("crypto_symbols_ranked"))}</strong></div>
    <div class="card"><span>Candidats</span><strong>{_cell(summary.get("candidate_symbols"))}</strong></div>
    <div class="card"><span>Top symbole</span><strong>{_cell(summary.get("top_symbol"))}</strong></div>
    <div class="card"><span>Top score</span><strong>{_cell(summary.get("top_score"))}</strong></div>
  </div>
  <div class="counts">{counts_html}</div>
  <h2>Liste CSV pour backtest</h2>
  <p><code>{_cell(payload.get("candidate_symbols_csv"))}</code></p>
  <h2>Candidats backtest</h2>
  {_table(payload.get("backtest_candidates") or [], 80)}
  <h2>Top volatilite brute</h2>
  {_table(payload.get("top_by_abs_price_change") or [], 50)}
  <p class="note">Garde-fou: volatil ne veut pas dire profitable. Une crypto volatile devient seulement une cible de discovery; elle doit ensuite passer la queue de validation, mark/index, WS et microstructure.</p>
</main>
</body>
</html>"""


def _write_csv(rows: list[dict[str, Any]]) -> None:
    fields = [
        "volatility_verdict",
        "volatility_score",
        "symbol",
        "base_asset",
        "quote_asset",
        "price_change_pct_24h",
        "abs_price_change_pct_24h",
        "quote_volume_24h",
        "trade_count_24h",
        "spread_bps",
        "premium_bps",
        "last_funding_rate",
        "market_take_bound",
        "min_notional",
        "volatility_reasons",
        "data_flags",
    ]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_aster_volatile_crypto_discovery(top_n: int = 80) -> dict[str, Any]:
    payload = get_aster_volatile_crypto_discovery_preview(dry_run=True, top_n=top_n)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(list(payload.get("backtest_candidates") or []))
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_aster_volatile_crypto_discovery()
    summary = payload.get("summary") or {}
    print(
        f"[{payload.get('generated_at')}] cryptos={summary.get('crypto_symbols_ranked')} "
        f"candidates={summary.get('candidate_symbols')} top={summary.get('top_symbol')} "
        f"csv={CSV_OUT} html={HTML_OUT}"
    )
    if payload.get("candidate_symbols_csv"):
        print(f"symbols={payload.get('candidate_symbols_csv')}")


if __name__ == "__main__":
    main()
