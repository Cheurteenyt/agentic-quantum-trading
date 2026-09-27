#!/usr/bin/env python3
"""Backfill du CVD (taker buy volume) + quote volume dans klines.db.

Contexte : l'API klines Aster fapi renvoie 12 champs dont takerBuyBaseVolume
et quoteVolume ; le collecteur historique n'en stockait que 8. Le schema est
etendu (fetch_klines.py v2) : ce script RE-FETCH les klines 1h de tous les
symboles presents et UPDATE les lignes existantes (join symbol+interval+
open_time). Les bougies absentes du warehouse ne sont PAS inserees ici —
c'est le role du collecteur standard.

Discipline :
  - lecture seule en mode --check (defaut) ;
  - un seul ecrivain klines.db pendant la passe (pas de collecteur en parrallele) ;
  - sleep entre chaque appel (rate limit API), cooldown 65s sur HTTP 429 ;
  - commit par page (un lot = une transaction, jamais de transaction fantome) ;
  - coverage = taker_buy_volume IS NOT NULL (0.0 legitime sur bougie vide).

Usage :
  .venv/bin/python scripts/backfill_taker_volume.py --check
  .venv/bin/python scripts/backfill_taker_volume.py --run --symbols BTCUSDT,ETHUSDT
  .venv/bin/python scripts/backfill_taker_volume.py --run          # tout le 1h
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import fetch_klines as fk  # noqa: E402

DB_PATH = fk.DB_PATH
DEFAULT_SLEEP_S = 0.75       # rate limit : poids 5/appel x1.33/s, tres en dessous
COOLDOWN_429_S = 65.0
MAX_RETRIES_429 = 3


def one(con: sqlite3.Connection, sql: str, params: tuple = ()) -> object:
    return con.execute(sql, params).fetchone()


INTERVAL = '1h'  # écrasé par --interval


def sim_symbols_1h(con: sqlite3.Connection) -> list[tuple[str, int, int]]:
    """(symbol, min_open_time, max_open_time) de toutes les series 1h du sim."""
    rows = con.execute(
        "SELECT symbol, MIN(open_time), MAX(open_time) FROM klines "
        f"WHERE interval = '{INTERVAL}' GROUP BY symbol ORDER BY symbol"
    ).fetchall()
    return [(r[0], int(r[1]), int(r[2])) for r in rows]


def fetch_page_with_429_retry(
    symbol: str, start_time: int, limit: int, timeout: float,
) -> list:
    """fetch_klines avec cooldown 65s sur HTTP 429 (max 3 essais)."""
    for attempt in range(MAX_RETRIES_429):
        try:
            return fk.fetch_klines(
                symbol, interval=INTERVAL, limit=limit,
                start_time=start_time, timeout=timeout,
            )
        except fk.AsterFetchError as exc:
            if "HTTP 429" in str(exc) and attempt < MAX_RETRIES_429 - 1:
                print(f"  ! 429 {symbol} — cooldown {COOLDOWN_429_S:.0f}s", flush=True)
                time.sleep(COOLDOWN_429_S)
                continue
            raise
    return []


def backfill_symbol(
    con: sqlite3.Connection, symbol: str, min_ts: int, max_ts: int,
    sleep_s: float, timeout: float, dry_run: bool,
) -> dict:
    """Re-fetch 1h de min_ts -> max_ts et UPDATE taker/quote sur les lignes
    existantes. Retourne des compteurs."""
    step = fk.interval_ms(INTERVAL)
    lim = fk.MAX_LIMIT
    start_time = min_ts
    requests = 0
    fetched = 0
    updated = 0
    now = time.time()
    while start_time <= max_ts:
        if requests:
            time.sleep(sleep_s)
        page = fetch_page_with_429_retry(symbol, start_time, lim, timeout)
        requests += 1
        if not page:
            break
        parsed = [fk.parse_kline_row(r, i) for i, r in enumerate(page)]
        fetched += len(parsed)
        updates = [
            (p[7], p[8], now, symbol, p[0])
            for p in parsed if min_ts <= p[0] <= max_ts
        ]
        if not dry_run:
            cur = con.executemany(
                "UPDATE klines SET taker_buy_volume = ?, quote_volume = ?, "
                f"fetched_at = ? WHERE symbol = ? AND interval = '{INTERVAL}' "
                "AND open_time = ?",
                updates,
            )
            con.commit()
            updated += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        else:
            updated += len(updates)
        last_open = max(p[0] for p in parsed)
        if len(page) < lim and last_open >= max_ts:
            break
        start_time = last_open + step
        if len(page) < lim:
            # fin d'historique renvoyee par l'API avant d'atteindre max_ts :
            # la suite (s'il en reste) sera couverte par le collecteur standard.
            break
    # coverage residuelle (lignes sans taker)
    remaining = one(
        con, f"SELECT COUNT(*) FROM klines WHERE symbol = ? AND interval = '{INTERVAL}' "
             "AND taker_buy_volume IS NULL", (symbol,))[0]
    return {"requests": requests, "fetched": fetched, "updated": updated,
            "remaining_null": int(remaining)}


def run(symbols: list[str] | None, sleep_s: float, timeout: float, dry_run: bool) -> int:
    con = fk.init_db(DB_PATH)
    try:
        series = sim_symbols_1h(con)
        if symbols:
            wanted = {s.strip().upper() for s in symbols}
            series = [s for s in series if s[0] in wanted]
        total_rows = one(con, f"SELECT COUNT(*) FROM klines WHERE interval='{INTERVAL}'")[0]
        print(f"=== Backfill CVD {INTERVAL} — {len(series)} symbole(s), {total_rows} bougies ===",
              flush=True)
        print(f"  base : {DB_PATH} | sleep {sleep_s}s | dry_run={dry_run}", flush=True)

        sum_upd = 0
        for i, (sym, lo, hi) in enumerate(series, 1):
            try:
                res = backfill_symbol(con, sym, lo, hi, sleep_s, timeout, dry_run)
            except (fk.AsterFetchError, fk.KlineParseError, sqlite3.Error) as exc:
                print(f"  ! {sym} : ECHEC {exc}", flush=True)
                continue
            sum_upd += res["updated"]
            n_rows = one(con, "SELECT COUNT(*) FROM klines WHERE symbol=? AND "
                              "interval='1h'", (sym,))[0]
            cov = 100.0 * (n_rows - res["remaining_null"]) / n_rows if n_rows else 0.0
            print(f"  [{i:>2}/{len(series)}] {sym:<14} req={res['requests']:<3} "
                  f"maj={res['updated']:<6} couverture={cov:5.1f}% "
                  f"(NULL restants: {res['remaining_null']})", flush=True)

        left = one(con, "SELECT COUNT(*) FROM klines WHERE interval='{INTERVAL}' AND "
                        "taker_buy_volume IS NULL")[0]
        done = total_rows - left
        pct = 100.0 * done / total_rows if total_rows else 0.0
        print(f"=== RESULTAT : {done}/{total_rows} bougies 1h avec taker "
              f"({pct:.1f}%), NULL restants {left} ===", flush=True)
        return 0 if not left else 1
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill taker/quote volume (CVD) 1h.")
    ap.add_argument("--check", action="store_true",
                    help="Defaut : dry-run, compte sans ecrire.")
    ap.add_argument("--run", action="store_true", help="Execute les UPDATE.")
    ap.add_argument("--symbols", default="", help="Restreindre (CSV).")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_S)
    ap.add_argument("--timeout", type=float, default=fk.DEFAULT_TIMEOUT)
    ap.add_argument("--interval", default="1h", choices=["1m", "5m", "15m", "1h"])
    args = ap.parse_args()
    global INTERVAL                     # sinon l'assignation est LOCALE
    INTERVAL = args.interval
    syms = [s for s in args.symbols.split(",") if s.strip()] or None
    return run(syms, args.sleep, args.timeout, dry_run=not args.run)


if __name__ == "__main__":
    sys.exit(main())
