#!/usr/bin/env python
"""Memecoin Pulse — une page de faits par memecoin perp Aster, chaque nuit.

Croise les couches propriétaires du projet pour chaque memecoin listé sur
Aster : funding annualisé, collectionnabilité (spread top-10, seuil legacy
20 bps), liquidations 24h, vélocité X (mentions) et calls du registre 24h.
Un memecoin à spread 257 bps n'est pas tradable : on le dit au lieu de
scorer du vent (leçon du carry intra-Aster).

Usage :
  .venv/bin/python scripts/memecoin_pulse.py            # rapport + console
  .venv/bin/python scripts/memecoin_pulse.py --json     # pour la campagne
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"
X_DB = ROOT / "data" / "warehouse" / "x_posts.db"
REPORTS = ROOT / "reports"

MEMECOINS = [
    "MEMEUSDT", "BOMEUSDT", "WIFUSDT", "PNUTUSDT", "MOODENGUSDT",
    "NEIROUSDT", "TURBOUSDT", "PENGUUSDT", "NOTUSDT", "DOGSUSDT",
    "TRUMPUSDT", "FARTCOINUSDT", "CATEUSDT", "1000PEPEUSDT",
    "1000BONKUSDT", "1000FLOKIUSDT", "DRAMUSDT", "PIEVERSEUSDT",
]
DEPTH_URL = "https://fapi.asterdex.com/fapi/v1/depth"
SPREAD_BPS_LIMIT = 20.0  # seuil legacy microstructure


def spread_bps(symbol: str) -> float | None:
    try:
        req = urllib.request.Request(f"{DEPTH_URL}?symbol={symbol}&limit=10",
                                     headers={"User-Agent": "trading-agent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.load(resp)
        bid, ask = float(d["bids"][0][0]), float(d["asks"][0][0])
        mid = (bid + ask) / 2.0
        return (ask - bid) / mid * 10000.0
    except Exception:  # noqa: BLE001
        return None


FUNDING_CACHE = ROOT / "backend" / "services" / "onchain" / "aster" / "aster_public_funding_history_cache.json"


def funding_row(symbol: str) -> tuple[float | None, float | None]:
    """(dernier taux %, annualisé %) — source : cache funding Aster (nuit)."""
    try:
        cache = json.loads(FUNDING_CACHE.read_text())
        entry = cache.get("symbols", {}).get(symbol) or {}
        rate = entry.get("data", {}).get("latest_funding_rate")
        if rate is None:
            return None, None
        r = float(rate) * 100.0
        return r, r * 3 * 365
    except Exception:  # noqa: BLE001
        return None, None


def liq_24h(symbol: str) -> tuple[int, float]:
    con = sqlite3.connect(f"file:{KLINES_DB}?mode=ro", uri=True, timeout=60)
    try:
        cutoff = time.time() - 86400
        rows = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(notional), 0) FROM liq_events "
            "WHERE symbol = ? AND event_time >= ?",
            (symbol, cutoff),
        ).fetchone()
        return int(rows[0]), float(rows[1])
    except Exception:  # noqa: BLE001
        return 0, 0.0
    finally:
        con.close()


def calls_24h(symbol: str) -> int:
    base = symbol[:-4]
    try:
        con = sqlite3.connect(f"file:{X_DB}?mode=ro", uri=True, timeout=60)
        cutoff = time.time() - 86400
        (n,) = con.execute(
            "SELECT COUNT(*) FROM x_calls c JOIN x_call_scores s ON s.call_id = c.call_id "
            "WHERE c.symbol = ? AND CAST(strftime('%s', s.posted_at) AS INTEGER) >= ?",
            (base, cutoff),
        ).fetchone()
        return int(n)
    except Exception:  # noqa: BLE001
        return 0
    finally:
        con.close()


def mentions_today(symbol: str) -> int | None:
    base = symbol[:-4]
    try:
        con = sqlite3.connect(f"file:{X_DB}?mode=ro", uri=True, timeout=60)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        (n,) = con.execute(
            "SELECT COALESCE(SUM(n), 0) FROM x_mentions WHERE symbol = ? AND day = ?",
            (base, today),
        ).fetchone()
        return int(n)
    except Exception:  # noqa: BLE001
        return None
    finally:
        con.close()


def collect() -> list[dict]:
    rows = []
    for sym in MEMECOINS:
        sp = spread_bps(sym)
        fr, fr_ann = funding_row(sym)
        nliq, notional = liq_24h(sym)
        rows.append({
            "symbol": sym,
            "spread_bps": round(sp, 1) if sp is not None else None,
            "collectionnable": sp is not None and sp < SPREAD_BPS_LIMIT,
            "funding_pct": round(fr, 4) if fr is not None else None,
            "funding_annual_pct": round(fr_ann, 1) if fr_ann is not None else None,
            "liq_24h": nliq,
            "liq_notional_24h": round(notional, 0),
            "calls_24h": calls_24h(sym),
            "mentions_x": mentions_today(sym),
        })
    return rows


def write_report(rows: list[dict]) -> Path:
    now = datetime.now(tz=timezone.utc)
    lines = [
        f"# Memecoin Pulse — {now:%d/%m/%Y %H:%M} UTC",
        "",
        "Perps memecoin Aster × X.com. Spread = top-10 carnet (seuil legacy 20 bps :",
        "au-delà, un call existe mais n'est PAS collectionnable). Funding annualisé",
        "du dernier règlement. Mentions = registre X. Frais et slippage non inclus.",
        "",
        "| Symbole | Spread bps | Tradable | Funding % (ann.) | Liq 24h | Notional $ | Calls 24h | Mentions X |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        flag = "OUI" if r["collectionnable"] else "**non**"
        fr = f"{r['funding_pct']:+.4f} ({r['funding_annual_pct']:+.1f})" if r["funding_pct"] is not None else "—"
        lines.append(
            f"| {r['symbol'][:-4]} | {r['spread_bps'] if r['spread_bps'] is not None else '—'} | {flag} | {fr} | "
            f"{r['liq_24h']} | {r['liq_notional_24h']:,.0f} | {r['calls_24h']} | {r['mentions_x'] if r['mentions_x'] is not None else '—'} |"
        )
    tradables = [r for r in rows if r["collectionnable"]]
    lines += [
        "",
        f"**Collectionnables : {len(tradables)}/{len(rows)}.**",
        "Rappel : ceci décrit le terrain, ça ne dit pas d'acheter. Règle",
        "pré-enregistrée inchangée (N ≥ 10, win rate ≥ 55 %) avant tout verdict.",
    ]
    out = REPORTS / f"memecoin-pulse-{now:%Y%m%d}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Memecoin Pulse — faits par memecoin perp Aster")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    rows = collect()
    if args.json:
        print(json.dumps(rows, indent=1))
    else:
        out = write_report(rows)
        print(f"[pulse] {out}")
        for r in rows:
            tr = "OUI" if r["collectionnable"] else "non"
            print(f"  {r['symbol']:<14} spread={r['spread_bps']} tradable={tr:<3} "
                  f"funding={r['funding_annual_pct']}%  liq24h={r['liq_24h']}  "
                  f"calls24h={r['calls_24h']}  mentions={r['mentions_x']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
