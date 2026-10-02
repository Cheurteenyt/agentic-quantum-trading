#!/usr/bin/env python3
"""Fetcher de l'univers macro/synthétique Aster (28/09) — étude 1.

27 perps macro + équités synthétiques (SPX, or, pétrole, NVDA, TSLA...)
-> SIDE-DB data/warehouse/klines_macro.db (JAMAIS klines.db), même schéma.
Source : https://fapi.asterdex.com/fapi/v1/klines (public, sans auth).
2 appels max par symbole (limit 1500 x2 = ~125 j de 1h) + import des
historiques plus vieux déjà présents dans klines.db (lecture seule :
NVDA 1 an, GOOGL 6 mois, XAG, AMZN).

Discipline identique à scripts/fetch_klines.py :
  - rate limit entre appels, timeouts partout, pas d'`except: pass`.
  - PRIMARY KEY (symbol, interval, open_time) : re-fetch idempotent.
  - open_time en MILLISECONDES (leçon ts_ms : unité vérifiée).
Stdlib pure (urllib, sqlite3).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASTER_BASE = "https://fapi.asterdex.com"
DB_MACRO = ROOT / "data" / "warehouse" / "klines_macro.db"
DB_MAIN = ROOT / "data" / "warehouse" / "klines.db"
SOURCE_API = "aster_public_klines_macro_2026-09-28"
SNAP = "macro_universe_2026-09-28"
INTERVAL = "1h"
LIMIT = 1500
MAX_CALLS_PER_SYMBOL = 2
SLEEP_S = 0.35
TIMEOUT = 20.0
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

# 27 symboles macro/synthétiques Aster (exchangeInfo 28/09) :
#   matières premières (8) : or, argent, WTI, Brent, gaz, cuivre, platine, palladium
#   indices (5) : SPX (S&P500), SPY, QQQ, TQQQ, IWM
#   équités synthétiques (14) : les 11 citées + NFLX, PLTR, AMZN
# CLOUSDT listé par le user mais sonde prix 0.057$ = token low-cap, pas une
# matière première -> exclu du périmètre macro, noté dans le rapport.
SYMBOLS: list[str] = [
    "XAUUSDT", "XAGUSDT", "CLUSDT", "BZUSDT", "NATGASUSDT",
    "XCUUSDT", "XPTUSDT", "XPDUSDT",
    "SPXUSDT", "SPYUSDT", "QQQUSDT", "TQQQUSDT", "IWMUSDT",
    "NVDAUSDT", "AAPLUSDT", "TSLAUSDT", "MSFTUSDT", "METAUSDT",
    "GOOGLUSDT", "AMZNUSDT", "MSTRUSDT", "COINUSDT", "HOODUSDT",
    "ORCLUSDT", "CRCLUSDT", "NFLXUSDT", "PLTRUSDT",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS klines (
    symbol      TEXT    NOT NULL,
    interval    TEXT    NOT NULL,
    open_time   INTEGER NOT NULL,
    open        REAL    NOT NULL CHECK (open  > 0),
    high        REAL    NOT NULL CHECK (high  > 0),
    low         REAL    NOT NULL CHECK (low   > 0),
    close       REAL    NOT NULL CHECK (close > 0),
    volume      REAL    NOT NULL CHECK (volume >= 0),
    close_time  INTEGER NOT NULL,
    snapshot_id TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    fetched_at  REAL    NOT NULL, taker_buy_volume REAL, quote_volume REAL,
    CHECK (high >= low),
    CHECK (open_time > 0),
    PRIMARY KEY (symbol, interval, open_time)
);
CREATE TABLE IF NOT EXISTS premium_history (
    symbol TEXT, mark_price REAL, index_price REAL, premium_pct REAL,
    last_funding_rate REAL, next_funding_time_ms INTEGER,
    captured_at_ms INTEGER, PRIMARY KEY (symbol, captured_at_ms));
"""


def get_json(url: str) -> list | dict:
    req = urllib.request.Request(url, headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def fetch_symbol(symbol: str, con: sqlite3.Connection, now_ms: int) -> int:
    """2 appels max, du plus récent vers le plus ancien. Retourne n lignes insérées."""
    end_ms = now_ms
    fetched_min = None
    n = 0
    for call_i in range(MAX_CALLS_PER_SYMBOL):
        url = (f"{ASTER_BASE}/fapi/v1/klines?symbol={symbol}"
               f"&interval={INTERVAL}&limit={LIMIT}&endTime={end_ms}")
        try:
            rows = get_json(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  ERR API {symbol} call{call_i}: {e}")
            break
        if not isinstance(rows, list) or not rows:
            break
        batch = []
        for k in rows:
            o_t = int(k[0])
            o, h, l, c = (float(k[1]), float(k[2]), float(k[3]), float(k[4]))
            v, c_t = float(k[5]), int(k[6])
            qv = float(k[7]) if k[7] is not None else v * c
            tbv = float(k[9]) if k[9] is not None else None
            if o <= 0 or h <= 0 or l <= 0 or c <= 0 or h < l or v < 0:
                print(f"  SKIP barre invalide {symbol} {o_t}")
                continue
            batch.append((symbol, INTERVAL, o_t, o, h, l, c, v, c_t,
                          SNAP, SOURCE_API, float(now_ms) / 1000.0, tbv, qv))
        con.executemany("INSERT OR IGNORE INTO klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        batch)
        con.commit()
        n += len(batch)
        first_t = min(int(k[0]) for k in rows)
        fetched_min = first_t if fetched_min is None else min(fetched_min, first_t)
        if len(rows) < LIMIT:  # historique API épuisé
            break
        end_ms = first_t - 3_600_000  # barre précédente
        time.sleep(SLEEP_S)
    # import des historiques plus vieux déjà en base principale (lecture seule)
    if fetched_min is not None:
        try:
            src = sqlite3.connect(f"file:{DB_MAIN}?mode=ro", uri=True, timeout=60)
            old = src.execute(
                "SELECT symbol, interval, open_time, open, high, low, close, volume,"
                " close_time, snapshot_id, source, fetched_at, taker_buy_volume,"
                " quote_volume FROM klines WHERE symbol=? AND interval=? AND open_time<?",
                (symbol, INTERVAL, fetched_min)).fetchall()
            src.close()
        except sqlite3.Error as e:
            print(f"  ERR import {symbol}: {e}")
            old = []
        if old:
            con.executemany("INSERT OR IGNORE INTO klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            old)
            con.commit()
            n += len(old)
    return n


def main() -> int:
    now_ms = int(time.time() * 1000)
    con = sqlite3.connect(str(DB_MACRO), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(SCHEMA)
    print(f"=== fetch macro universe : {len(SYMBOLS)} symboles -> {DB_MACRO.name} ===")
    for sym in SYMBOLS:
        n = fetch_symbol(sym, con, now_ms)
        r = con.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM klines"
                        " WHERE symbol=? AND interval=?", (sym, INTERVAL)).fetchone()
        days = (r[2] - r[1]) / 86_400_000 if r[0] and r[1] else 0.0
        print(f"  {sym:12s} +{n:5d}  total={r[0]:5d}  {days:6.1f} j")
        time.sleep(SLEEP_S)
    con.close()
    print("=== fin fetch ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
