#!/usr/bin/env python
"""LE COLLECTEUR D'HISTORIQUE FUNDING — la série de positioning d'Aster.

Trouvé par l'audit Ariad du 25/09 : la table funding_history était un
dataset ORPHELIN — un seed de 100 records/symbole (20/08 → 22/09) que
personne n'alimentait plus (le seul INSERT vivait dans un script
archivé ; le refresh nocturne écrit un JSON d'agrégats, pas la table).
Or cette série conditionne tous les indicateurs de positioning :
cascade × funding, vélocité de funding, confluence multi-lentilles.

Ce collecteur :
  1. BACKFILL paginé : /fapi/v3/fundingRate?symbol=X&startTime=T&limit=1000
     en avançant le startTime jusqu'à épuisement (les memecoins fundant
     à l'heure, une année = ~9 pages/symbole)
  2. INCRÉMENTAL nocturne : il ne reprend que depuis le max connu
  3. upsert INSERT OR IGNORE — PK (symbol, funding_time), idempotent

  .venv/bin/python scripts/funding_history_collector.py            # incrémental
  .venv/bin/python scripts/funding_history_collector.py --backfill # depuis 0
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
KDB = ROOT / "data" / "warehouse" / "klines.db"
API = "https://fapi.asterdex.com/fapi/v3/fundingRate"
PAGE = 1000
MAX_PAGES = 40
SLEEP_S = 0.15


def fetch_page(symbol: str, start_ms: int) -> list[dict]:
    url = f"{API}?symbol={symbol}&limit={PAGE}&startTime={start_ms}"
    req = urllib.request.Request(url, headers={"User-Agent": "trading-agent/1.0"})
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                rows = json.load(r)
            return rows if isinstance(rows, list) else []
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.0 + attempt)
    return []


def collect_symbol(con: sqlite3.Connection, symbol: str,
                   backfill: bool) -> int:
    row = con.execute(
        "SELECT MAX(funding_time) FROM funding_history WHERE symbol=?",
        (symbol,)).fetchone()
    last = row[0] if row and row[0] else None
    if backfill:
        start = 0
    elif last:
        start = int(last) + 1
    else:
        start = 0
    added = 0
    now_ms = int(time.time() * 1000)
    for _ in range(MAX_PAGES):
        rows = fetch_page(symbol, start)
        if not rows:
            break
        payload = []
        for r in rows:
            try:
                payload.append((symbol, int(r["fundingTime"]),
                                float(r["fundingRate"]), time.time()))
            except (TypeError, ValueError, KeyError):
                continue
        if payload:
            before = con.total_changes
            con.executemany(
                "INSERT OR IGNORE INTO funding_history VALUES (?,?,?,?)",
                payload)
            added += con.total_changes - before
        newest = max(int(r["fundingTime"]) for r in rows)
        if newest + 1 <= start or newest >= now_ms - 3600 * 1000:
            break                      # page suivante vide ou déjà au présent
        start = newest + 1
        time.sleep(SLEEP_S)
    con.commit()
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true",
                    help="repart de 0 (sinon incrémental depuis le max connu)")
    ap.add_argument("--symbols", default="",
                    help="liste csv ; défaut = tous les symboles 1h + connus")
    args = ap.parse_args()

    con = sqlite3.connect(KDB)
    con.execute("""CREATE TABLE IF NOT EXISTS funding_history (
        symbol      TEXT    NOT NULL,
        funding_time INTEGER NOT NULL,
        rate        REAL    NOT NULL,
        fetched_at  REAL    NOT NULL,
        PRIMARY KEY (symbol, funding_time))""")
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        known = {r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM funding_history")}
        have_klines = {r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM klines WHERE interval='1h'")}
        symbols = sorted(known | have_klines)

    total = 0
    t0 = time.time()
    for sym in symbols:
        try:
            n = collect_symbol(con, sym, args.backfill)
            total += n
            if n:
                print(f"[funding-collector] {sym}: +{n} records")
        except Exception as e:
            print(f"[funding-collector] {sym}: ERREUR {e}")
        time.sleep(SLEEP_S)
    con.close()
    print(f"[funding-collector] {len(symbols)} symboles, +{total} records "
          f"en {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
