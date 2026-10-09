#!/usr/bin/env .venv/bin/python
"""Aster block trades — collecteur de gros prints (aggTrades fapi).

Le TAPE institutionnel : les 447k bougies 1h + CVD voient l'AGREGÉ, ce
collecteur voit l'INDIVIDU — les gros prints executes (aggTrades >= seuil).

Source  : GET https://fapi.asterdex.com/fapi/v1/aggTrades
          ?symbol=X&limit=1000[&startTime=ms]   (pagine en avant via
          startTime = dernier T + 1 ; fromId existe aussi mais le temps est
          plus robuste pour un cron)
Champs  : a=aggId, p=price, q=qty, T=ts_ms, m=is_buyer_maker
Semantique (verifiee, Binance-compatible) :
          m=false -> buyer est le taker  = ACHAT agressif
          m=true  -> seller est le taker = VENTE agressive

Perf (bench 02/10) :
  weight/page aggTrades ~20 (pas ~5) ; budget 2400/min => ~120 pages/min max.
  CURRENT seq+sleep0.2, 6 majors x15min : 2.24 s
  pool + parallel 6                         : 0.32 s (x7, meme n trades)
  BTC 6h 9 pages : 2.74 s nosleep vs 4.36 s sleep0.2
  BTC 24h 35 pages : ~24 s dont pause weight>=1500 (le vrai plafond backfill)
Defaut --workers 4 = parallel symboles + 1 HTTPS persistante / worker.
--workers 1 = chemin legacy exact (seq + sleep 0.2 page et inter-symbole).

Tables dans data/warehouse/klines.db :
  block_trades(...) INSERT OR IGNORE
  tape_1m(...) upsert
  block_meta(...)

Modes :
  --bootstrap        2-3 jours d'historique sur les 6 majeures (backfill)
  (defaut)           incremental : reprend depuis MAX(ts_ms) par symbole
  --since-hours N    force la fenetre
  --workers N        parallelisme symboles (1 = legacy)
  --symbols A,B      override de la liste
"""
from __future__ import annotations

import argparse
import http.client
import json
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import aster_rate

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
API_BASE = "https://fapi.asterdex.com"
HOST = "fapi.asterdex.com"
_SSL_CTX = ssl.create_default_context()

MAJOR_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]

MIN_THRESHOLD_USD = 50_000.0
CLUSTER_PRINT_USD = 100_000.0
CLUSTER_WINDOW_MS = 30 * 60 * 1000
CLUSTER_MIN_PRINTS = 3
BOOTSTRAP_DAYS = 3
MAX_PAGES_PER_SYMBOL = 1200
MAX_PAGES_INCREMENTAL = 12
WEIGHT_PAUSE = 1500
PAGE_LIMIT = 1000
SLEEP_BETWEEN_REQ = 0.20  # legacy only (--workers 1)
REQUEST_TIMEOUT = 20
USER_AGENT = "trading-agent-blocktrades/1.2"

SCHEMA = """
CREATE TABLE IF NOT EXISTS block_trades (
    symbol        TEXT NOT NULL,
    ts_ms         INTEGER NOT NULL,
    price         REAL NOT NULL,
    qty           REAL NOT NULL,
    notional_usd  REAL NOT NULL,
    is_buyer_maker INTEGER NOT NULL,
    agg_id        INTEGER,
    PRIMARY KEY (symbol, ts_ms, qty)
);
CREATE TABLE IF NOT EXISTS tape_1m (
    symbol       TEXT NOT NULL,
    minute_ts    INTEGER NOT NULL,
    last_price   REAL NOT NULL,
    n_trades     INTEGER NOT NULL,
    buy_notional REAL NOT NULL,
    sell_notional REAL NOT NULL,
    PRIMARY KEY (symbol, minute_ts)
);
CREATE TABLE IF NOT EXISTS block_meta (
    symbol        TEXT PRIMARY KEY,
    threshold_usd REAL NOT NULL,
    p99_usd       REAL NOT NULL,
    n_trades      INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_block_trades_ts ON block_trades (symbol, ts_ms);
"""


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


TAPE_RETENTION_DAYS = 60
BLOCK_RETENTION_DAYS = 365
_last_prune_day = -1


def prune_daily(con: sqlite3.Connection) -> None:
    global _last_prune_day
    day = int(time.time() // 86400)
    if day == _last_prune_day:
        return
    _last_prune_day = day
    now_ms = int(time.time() * 1000)
    c_tape = now_ms - TAPE_RETENTION_DAYS * 86400 * 1000
    c_blk = now_ms - BLOCK_RETENTION_DAYS * 86400 * 1000
    try:
        n1 = con.execute("DELETE FROM tape_1m WHERE minute_ts < ?",
                         (c_tape,)).rowcount
        n2 = con.execute("DELETE FROM block_trades WHERE ts_ms < ?",
                         (c_blk,)).rowcount
        n3 = con.execute("DELETE FROM block_meta WHERE updated_at < ?",
                         (c_blk,)).rowcount
        con.commit()
    except sqlite3.Error as exc:
        _last_prune_day = -1
        log(f"prune ERR {exc}")
        return
    if n1 or n2 or n3:
        log(f"prune : tape_1m={n1} (> {TAPE_RETENTION_DAYS}j), "
            f"block_trades={n2}, block_meta={n3} (> {BLOCK_RETENTION_DAYS}j)")


def _weight_pause_if_needed(weight: int | None, symbol: str) -> None:
    if weight is not None and weight >= WEIGHT_PAUSE:
        pause = 60.0 - (time.time() % 60.0) + 0.5
        log(f"  {symbol} poids={weight}>={WEIGHT_PAUSE} : pause {pause:.0f}s "
            f"(fin de minute)")
        time.sleep(pause)


def http_get_json(url: str, retries: int = 3) -> tuple[list | dict, int | None]:
    """Legacy urllib path (workers=1)."""
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                weight = aster_rate.note_weight(
                    getattr(resp, "headers", None), "aster_blocktrades")
                return json.loads(resp.read().decode("utf-8")), weight
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                log("  429 rate limit, cooldown 65s")
                time.sleep(65.0)
                continue
            # D-03 (ronde 6) : le 418 (ban IP — doctrine aster_rate :
            # 2 min → 3 jours) n'est PAS retenté : marteler un serveur qui
            # a banni l'IP prolonge le ban, il tombe dans le raise. Et le
            # littéral `5` n'existe pas en code HTTP (typo pour 500) : le
            # 500 est désormais retenté comme 502/503.
            if exc.code in (500, 502, 503) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"GET failed {url}: {exc}") from exc
    raise RuntimeError(f"GET exhausted {url}")


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.execute("PRAGMA busy_timeout = 10000")
    con.executescript(SCHEMA)
    con.commit()
    return con


def active_symbols(con: sqlite3.Connection, max_symbols: int,
                   min_qv_usd: float) -> list[str]:
    cutoff = int(time.time() * 1000) - 3 * 86400 * 1000
    rows = con.execute(
        """SELECT symbol, SUM(quote_volume) qv FROM klines
           WHERE interval='1h' AND close_time > ? GROUP BY symbol""",
        (cutoff,),
    ).fetchall()
    active = [r[0] for r in sorted(rows, key=lambda r: -(r[1] or 0))
              if (r[1] or 0) >= min_qv_usd]
    seen, out = set(), []
    for sym in MAJOR_SYMBOLS + active:
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out[:max_symbols]


def fetch_window_legacy(symbol: str, since_ms: int, until_ms: int,
                        max_pages: int = MAX_PAGES_PER_SYMBOL) -> list[dict]:
    """Chemin historique : urllib + sleep 0.2 entre pages."""
    trades: list[dict] = []
    cursor = since_ms
    for page in range(1, max_pages + 1):
        url = (f"{API_BASE}/fapi/v1/aggTrades?symbol={symbol}"
               f"&startTime={cursor}&limit={PAGE_LIMIT}")
        batch, weight = http_get_json(url)
        _weight_pause_if_needed(weight, symbol)
        if not isinstance(batch, list) or not batch:
            break
        trades.extend(batch)
        last_t = int(batch[-1]["T"])
        if last_t <= cursor:
            last_t = cursor + 1
        cursor = last_t + 1
        if cursor >= until_ms or len(batch) < PAGE_LIMIT:
            break
        if page == max_pages:
            log(f"  {symbol} TRONCATURE {max_pages} pages ({len(trades)} trades), "
                f"reprise au prochain tir")
            break
        time.sleep(SLEEP_BETWEEN_REQ)
    return trades


def fetch_window_pool(symbol: str, since_ms: int, until_ms: int,
                      max_pages: int = MAX_PAGES_PER_SYMBOL) -> list[dict]:
    """1 connexion HTTPS reutilisee pour toutes les pages du symbole.
    Pas de sleep fixe — uniquement pause weight >= 1500."""
    trades: list[dict] = []
    cursor = since_ms
    conn = http.client.HTTPSConnection(
        HOST, context=_SSL_CTX, timeout=REQUEST_TIMEOUT)
    try:
        for page in range(1, max_pages + 1):
            path = (f"/fapi/v1/aggTrades?symbol={symbol}"
                    f"&startTime={cursor}&limit={PAGE_LIMIT}")
            for attempt in range(1, 4):
                try:
                    conn.request("GET", path, headers={"User-Agent": USER_AGENT})
                    resp = conn.getresponse()
                    raw = resp.read()
                    w_hdr = resp.getheader("X-MBX-USED-WEIGHT-1M")
                    weight = None
                    if w_hdr is not None:
                        try:
                            weight = int(str(w_hdr).strip())
                            aster_rate.note_weight(
                                {"X-MBX-USED-WEIGHT-1M": w_hdr},
                                "aster_blocktrades",
                            )
                        except ValueError:
                            weight = None
                    if resp.status == 429:
                        log(f"  {symbol} 429, cooldown 65s")
                        time.sleep(65.0)
                        conn.close()
                        conn = http.client.HTTPSConnection(
                            HOST, context=_SSL_CTX, timeout=REQUEST_TIMEOUT)
                        continue
                    if resp.status != 200:
                        raise RuntimeError(
                            f"HTTP {resp.status} on {symbol} page {page}")
                    batch = json.loads(raw.decode("utf-8"))
                    _weight_pause_if_needed(weight, symbol)
                    if weight is not None and weight >= WEIGHT_PAUSE:
                        # reconnexion apres longue pause
                        conn.close()
                        conn = http.client.HTTPSConnection(
                            HOST, context=_SSL_CTX, timeout=REQUEST_TIMEOUT)
                    break
                except (OSError, json.JSONDecodeError) as exc:
                    if attempt >= 3:
                        raise RuntimeError(
                            f"GET pool failed {symbol}: {exc}") from exc
                    time.sleep(1.0 * attempt)
                    conn.close()
                    conn = http.client.HTTPSConnection(
                        HOST, context=_SSL_CTX, timeout=REQUEST_TIMEOUT)
            else:
                break

            if not isinstance(batch, list) or not batch:
                break
            trades.extend(batch)
            last_t = int(batch[-1]["T"])
            if last_t <= cursor:
                last_t = cursor + 1
            cursor = last_t + 1
            if cursor >= until_ms or len(batch) < PAGE_LIMIT:
                break
            if page == max_pages:
                log(f"  {symbol} TRONCATURE {max_pages} pages ({len(trades)} trades), "
                    f"reprise au prochain tir")
                break
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return trades


def fetch_window(symbol: str, since_ms: int, until_ms: int,
                 max_pages: int = MAX_PAGES_PER_SYMBOL,
                 use_pool: bool = True) -> list[dict]:
    if use_pool:
        return fetch_window_pool(symbol, since_ms, until_ms, max_pages)
    return fetch_window_legacy(symbol, since_ms, until_ms, max_pages)


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def persist_symbol(con: sqlite3.Connection, symbol: str, trades: list[dict],
                   since_ms: int) -> tuple[int, float, float]:
    now = int(time.time() * 1000)
    notionals = sorted(float(t["p"]) * float(t["q"]) for t in trades)
    p99 = percentile(notionals, 0.99)
    threshold = max(MIN_THRESHOLD_USD, p99)

    blocks, minute_acc = [], {}
    for t in trades:
        price, qty = float(t["p"]), float(t["q"])
        notional = price * qty
        ts = int(t["T"])
        minute = ts // 60_000 * 60_000
        acc = minute_acc.setdefault(minute, [price, 0, 0.0, 0.0])
        acc[0] = price
        acc[1] += 1
        if t["m"]:
            acc[3] += notional
        else:
            acc[2] += notional
        if notional >= threshold:
            blocks.append(
                (symbol, ts, price, qty, notional, 1 if t["m"] else 0, int(t["a"])))

    con.execute("BEGIN IMMEDIATE")
    for minute, (px, n, buy, sell) in minute_acc.items():
        con.execute(
            """INSERT INTO tape_1m (symbol, minute_ts, last_price, n_trades,
               buy_notional, sell_notional) VALUES (?,?,?,?,?,?)
               ON CONFLICT(symbol, minute_ts) DO UPDATE SET
                 last_price=excluded.last_price, n_trades=excluded.n_trades,
                 buy_notional=excluded.buy_notional,
                 sell_notional=excluded.sell_notional""",
            (symbol, minute, px, n, buy, sell),
        )
    for row in blocks:
        con.execute(
            """INSERT OR IGNORE INTO block_trades
               (symbol, ts_ms, price, qty, notional_usd, is_buyer_maker, agg_id)
               VALUES (?,?,?,?,?,?,?)""",
            row,
        )
    con.execute(
        """INSERT INTO block_meta (symbol, threshold_usd, p99_usd, n_trades, updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(symbol) DO UPDATE SET threshold_usd=excluded.threshold_usd,
             p99_usd=excluded.p99_usd, n_trades=excluded.n_trades,
             updated_at=excluded.updated_at""",
        (symbol, threshold, p99, len(trades), now),
    )
    con.commit()
    return len(blocks), threshold, p99


def last_ts(con: sqlite3.Connection, symbol: str) -> int:
    row = con.execute(
        "SELECT MAX(minute_ts) FROM tape_1m WHERE symbol=?", (symbol,)
    ).fetchone()
    if row and row[0]:
        return int(row[0])
    row = con.execute(
        "SELECT MAX(ts_ms) FROM block_trades WHERE symbol=?", (symbol,)
    ).fetchone()
    return int(row[0]) if row and row[0] else 0


def _process_one(symbol: str, since: int, now: int, max_pages: int,
                 use_pool: bool, db_path: Path) -> tuple[str, int, int, float, float, float]:
    """Fetch + persist pour 1 symbole (thread-safe : 1 sqlite connect / thread)."""
    t0 = time.time()
    trades = fetch_window(symbol, since, now, max_pages=max_pages, use_pool=use_pool)
    con = sqlite3.connect(db_path, timeout=30.0)
    try:
        con.execute("PRAGMA busy_timeout = 10000")
        n_blocks, thr, p99 = persist_symbol(con, symbol, trades, since)
    finally:
        con.close()
    return symbol, len(trades), n_blocks, thr, p99, time.time() - t0


def run(args: argparse.Namespace) -> None:
    con = connect_db()
    prune_daily(con)
    symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
               if args.symbols else active_symbols(con, args.max_symbols, args.min_qv))
    now = int(time.time() * 1000)
    workers = max(1, int(args.workers))
    use_pool = workers > 1 or args.pool
    # bootstrap : borner le parallelisme pour ne pas bruler 2400 weight
    if args.bootstrap and workers > 3:
        log(f"bootstrap : workers {workers} -> 3 (garde weight)")
        workers = 3
    workers = min(workers, max(1, len(symbols)))
    log(f"mode={'bootstrap' if args.bootstrap else 'incremental'} "
        f"workers={workers} pool={use_pool} "
        f"symbols={len(symbols)}: {','.join(symbols[:8])}"
        f"{'...' if len(symbols) > 8 else ''}")

    # precompute since per symbol (needs DB read)
    jobs: list[tuple[str, int, int]] = []
    for sym in symbols:
        if args.bootstrap:
            since = now - int(args.days * 86400 * 1000)
        elif args.since_hours is not None:
            since = now - int(args.since_hours * 3600 * 1000)
        else:
            lt = last_ts(con, sym)
            since = lt + 1 if lt else now - int(args.days * 86400 * 1000)
        max_pages = (MAX_PAGES_PER_SYMBOL if args.bootstrap
                     else MAX_PAGES_INCREMENTAL)
        jobs.append((sym, since, max_pages))
    con.close()

    totals: dict[str, tuple[int, int, float]] = {}

    if workers <= 1:
        con = connect_db()
        try:
            for sym, since, max_pages in jobs:
                try:
                    t0 = time.time()
                    trades = fetch_window(
                        sym, since, now, max_pages=max_pages, use_pool=use_pool)
                    n_blocks, thr, p99 = persist_symbol(con, sym, trades, since)
                    totals[sym] = (len(trades), n_blocks, thr)
                    log(f"  {sym:14s} trades={len(trades):7d} "
                        f"prints>=${thr:,.0f}: {n_blocks:4d} "
                        f"(p99=${p99:,.0f}) {time.time()-t0:.1f}s")
                except Exception as exc:
                    log(f"  {sym:14s} ERROR {type(exc).__name__}: {exc}")
                if not use_pool:
                    time.sleep(SLEEP_BETWEEN_REQ)
        finally:
            con.close()
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(
                    _process_one, sym, since, now, max_pages, True, DB_PATH
                ): sym
                for sym, since, max_pages in jobs
            }
            for fut in as_completed(futs):
                sym = futs[fut]
                try:
                    s, n_tr, n_bl, thr, p99, dt = fut.result()
                    totals[s] = (n_tr, n_bl, thr)
                    log(f"  {s:14s} trades={n_tr:7d} prints>=${thr:,.0f}: "
                        f"{n_bl:4d} (p99=${p99:,.0f}) {dt:.1f}s")
                except Exception as exc:
                    log(f"  {sym:14s} ERROR {type(exc).__name__}: {exc}")

    nb = sum(v[1] for v in totals.values())
    log(f"done: {sum(v[0] for v in totals.values())} trades, {nb} nouveaux prints")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Aster big prints collector (aggTrades)")
    ap.add_argument("--bootstrap", action="store_true",
                    help="backfill 2-3 jours, 6 majeures")
    ap.add_argument("--days", type=float, default=BOOTSTRAP_DAYS)
    ap.add_argument("--since-hours", type=float, default=None)
    ap.add_argument("--symbols", default=None, help="liste CSV, override")
    ap.add_argument("--max-symbols", type=int, default=20)
    ap.add_argument("--min-qv", type=float, default=50_000.0,
                    help="qv 3j min $ (actifs)")
    ap.add_argument("--workers", type=int, default=4,
                    help="parallelisme symboles (1=legacy seq+sleep0.2 ; defaut 4)")
    ap.add_argument("--pool", action="store_true",
                    help="force pool HTTPS meme si workers=1")
    args = ap.parse_args()
    if args.bootstrap and not args.symbols:
        args.symbols = ",".join(MAJOR_SYMBOLS)
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
