#!/usr/bin/env python
"""Snapshot nocturne du flux Aster : Open Interest + delta taker 30m.

Proxy natif du « net positioning » (indicateur phare du catalogue MMT) :
Aster n'expose pas les ratios long/short de Binance, mais l'Open Interest
(fapi/v1/openInterest) + le delta taker de la dernière bougie 30m fermée
donnent la même lecture : la foule se renforce-t-elle quand le prix monte ?
Accumulation dans flow_snapshots (klines.db) pour backtest futur.

Usage :
  .venv/bin/python scripts/flow_snapshot.py --record
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aster_absorption import bars_from_klines, fetch_klines  # noqa: E402

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
OI_URL = "https://fapi.asterdex.com/fapi/v1/openInterest"

FLOW_SNAP_DDL = """
CREATE TABLE IF NOT EXISTS flow_snapshots (
    symbol          TEXT    NOT NULL,
    ts              INTEGER NOT NULL,
    oi              REAL    NOT NULL,
    taker_delta_30m REAL    NOT NULL,
    captured_at     REAL    NOT NULL,
    PRIMARY KEY (symbol, ts)
);
"""


def fetch_oi(symbol: str) -> float:
    req = urllib.request.Request(f"{OI_URL}?symbol={symbol}", headers={"User-Agent": "trading-agent/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return float(json.load(resp)["openInterest"])


def last_closed_delta_30m(symbol: str) -> float:
    """Delta taker (buy - sell) de la dernière bougie 30m FERMÉE."""
    klines = fetch_klines(symbol, "30m", limit=3)
    bars = bars_from_klines(klines)
    # la dernière ligne peut être en formation : on garde la bougie dont la close-time est passée
    closed = [b for b, k in zip(bars, klines) if int(k[6]) < int(time.time() * 1000)]
    if not closed:
        return 0.0
    b = closed[-1]
    return b["buy"] - b["sell"]


def record(rows: list[dict], db_path: Path | str = DB_PATH) -> int:
    if not rows:
        return 0
    con = sqlite3.connect(db_path, timeout=60)
    try:
        con.execute(FLOW_SNAP_DDL)
        cur = con.executemany(
            "INSERT OR IGNORE INTO flow_snapshots (symbol, ts, oi, taker_delta_30m, captured_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [(r["symbol"], r["ts"], r["oi"], r["taker_delta_30m"], r["captured_at"]) for r in rows],
        )
        con.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    finally:
        con.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Snapshot OI + delta taker (proxy positioning Aster)")
    p.add_argument("--symbol", default="BTCUSDT,ETHUSDT,SOLUSDT,ASTERUSDT")
    p.add_argument("--record", action="store_true")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    now = int(time.time())
    rows = []
    for sym in [s.strip().upper() for s in args.symbol.split(",") if s.strip()]:
        try:
            oi = fetch_oi(sym)
            delta = last_closed_delta_30m(sym)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] {sym}: {exc}", file=sys.stderr)
            continue
        rows.append({"symbol": sym, "ts": now, "oi": oi, "taker_delta_30m": round(delta, 4),
                     "captured_at": time.time()})
    if args.record:
        inserted = record(rows, args.db)
        print(f"[record] {inserted} snapshots -> {args.db}")
    if args.json:
        print(json.dumps(rows, indent=1))
    else:
        print(f"{'SYMBOLE':<12} {'OI':>14} {'DELTA 30m':>14}")
        for r in rows:
            print(f"{r['symbol']:<12} {r['oi']:>14.3f} {r['taker_delta_30m']:>14.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
