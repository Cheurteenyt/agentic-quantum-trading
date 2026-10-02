#!/usr/bin/env python
"""Fetch profond de klines Aster — pagination startTime jusqu'à N jours.

Le fetcher standard s'arrête tôt ; celui-ci pagination depuis `days` jours
en arrière jusqu'à maintenant, et remplit klines.db (INSERT OR IGNORE).

  .venv/bin/python scripts/fetch_deep_klines.py --days 365 --interval 1h
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
DB = ROOT / "data" / "warehouse" / "klines.db"
BASE = "https://fapi.asterdex.com/fapi/v3/klines"


def fetch_page(symbol: str, interval: str, start_ms: int, limit: int = 1500):
    url = f"{BASE}?symbol={symbol}&interval={interval}&startTime={start_ms}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "trading-agent/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--sleep", type=float, default=0.35)
    args = ap.parse_args()

    con = sqlite3.connect(DB, timeout=60)
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = [r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM klines WHERE interval = ?",
            (args.interval,)).fetchall()]
    snap = f"deep-{args.days}d-{datetime.now(timezone.utc):%Y%m%d}"
    now = time.time()
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - args.days * 86400 * 1000
    total = 0
    for sym in symbols:
        cursor = start_ms
        added = 0
        for _ in range(30):  # 30 pages × 1500 = 45000 bougies max
            try:
                page = fetch_page(sym, args.interval, cursor)
            except Exception as exc:  # noqa: BLE001
                print(f"[deep] {sym}: {str(exc)[:60]}", file=sys.stderr)
                break
            if not page:
                break
            for k in page:
                con.execute(
                    "INSERT OR IGNORE INTO klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sym, args.interval, int(k[0]), k[1], k[2], k[3], k[4],
                     k[5], int(k[6]), snap, "aster", now))
                added += 1
            last_close = int(page[-1][6])
            total += len(page)
            if last_close >= now_ms - 3600 * 1000 or len(page) < 1500:
                break
            cursor = last_close + 1
            time.sleep(args.sleep)
        con.commit()
        print(f"[deep] {sym}: page-scan fini, +{added} vues (doublons ignorés)",
              file=sys.stderr)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM klines WHERE interval = ?",
                    (args.interval,)).fetchone()[0]
    con.close()
    print(f"[deep] total klines {args.interval}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
