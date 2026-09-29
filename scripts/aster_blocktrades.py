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

Tables dans data/warehouse/klines.db :
  block_trades(symbol, ts_ms, price, qty, notional_usd, is_buyer_maker,
               agg_id, PK(symbol, ts_ms, qty))          INSERT OR IGNORE
  tape_1m(symbol, minute_ts, last_price, n_trades, buy_notional,
          sell_notional, PK(symbol, minute_ts))         upsert (drift study)
  block_meta(symbol, threshold_usd, p99_usd, n_trades, updated_at)

Modes :
  --bootstrap        2-3 jours d'historique sur les 6 majeures (backfill)
  (defaut)           incrémental : reprend depuis MAX(ts_ms) par symbole
  --since-hours N    force la fenêtre (ex cron 15 min)
  --symbols A,B      override de la liste

Un symbole en erreur n'arrete jamais la passe (isolation try/except),
busy_timeout + COMMIT explicite par symbole.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request

import aster_rate  # le compteur X-MBX-USED-WEIGHT-1M (audit docs/24)
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
API_BASE = "https://fapi.asterdex.com"

MAJOR_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]

MIN_THRESHOLD_USD = 50_000.0        # plancher mission
CLUSTER_PRINT_USD = 100_000.0       # seuil des clusters d'analyse
CLUSTER_WINDOW_MS = 30 * 60 * 1000
CLUSTER_MIN_PRINTS = 3
BOOTSTRAP_DAYS = 3
MAX_PAGES_PER_SYMBOL = 1200         # garde-fou (1200 * 1000 trades)
PAGE_LIMIT = 1000
SLEEP_BETWEEN_REQ = 0.20            # aggTrades weight ~5, IP limit large
REQUEST_TIMEOUT = 20

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


def http_get_json(url: str, retries: int = 3) -> list | dict:
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "trading-agent-blocktrades/1.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                aster_rate.note_weight(getattr(resp, "headers", None), "aster_blocktrades")
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:                       # cooldown prudent
                log(f"  429 rate limit, cooldown 65s")
                time.sleep(65.0)
                continue
            if exc.code in (418, 5, 502, 503) and attempt < retries:
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


def active_symbols(con: sqlite3.Connection, max_symbols: int, min_qv_usd: float) -> list[str]:
    """Les 6 majeures + symboles actifs (qv 1h sur 3j), meme esprit que
    la liste de refresh_aster_cache mais filtrée sur l'activité réelle."""
    cutoff = int(time.time() * 1000) - 3 * 86400 * 1000
    rows = con.execute(
        """SELECT symbol, SUM(quote_volume) qv FROM klines
           WHERE interval='1h' AND close_time > ? GROUP BY symbol""",
        (cutoff,),
    ).fetchall()
    active = [r[0] for r in sorted(rows, key=lambda r: -(r[1] or 0)) if (r[1] or 0) >= min_qv_usd]
    seen, out = set(), []
    for sym in MAJOR_SYMBOLS + active:
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out[:max_symbols]


def fetch_window(symbol: str, since_ms: int, until_ms: int) -> list[dict]:
    """Pagine aggTrades en avant par startTime = dernier T + 1."""
    trades: list[dict] = []
    cursor = since_ms
    for _ in range(MAX_PAGES_PER_SYMBOL):
        url = (f"{API_BASE}/fapi/v1/aggTrades?symbol={symbol}"
               f"&startTime={cursor}&limit={PAGE_LIMIT}")
        batch = http_get_json(url)
        if not isinstance(batch, list) or not batch:
            break
        trades.extend(batch)
        last_t = int(batch[-1]["T"])
        if last_t <= cursor:
            last_t = cursor + 1
        cursor = last_t + 1
        if cursor >= until_ms or len(batch) < PAGE_LIMIT:
            break
        time.sleep(SLEEP_BETWEEN_REQ)
    return trades


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def persist_symbol(con: sqlite3.Connection, symbol: str, trades: list[dict],
                   since_ms: int) -> tuple[int, float, float]:
    """Filtre + insert les prints >= seuil adaptatif. Commit = 1 transaction."""
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
        if t["m"]:                       # buyer maker -> vente agressive
            acc[3] += notional
        else:                            # buyer taker -> achat agressif
            acc[2] += notional
        if notional >= threshold:
            blocks.append((symbol, ts, price, qty, notional, 1 if t["m"] else 0, int(t["a"])))

    con.execute("BEGIN IMMEDIATE")
    for minute, (px, n, buy, sell) in minute_acc.items():
        con.execute(
            """INSERT INTO tape_1m (symbol, minute_ts, last_price, n_trades,
               buy_notional, sell_notional) VALUES (?,?,?,?,?,?)
               ON CONFLICT(symbol, minute_ts) DO UPDATE SET
                 last_price=excluded.last_price, n_trades=excluded.n_trades,
                 buy_notional=excluded.buy_notional, sell_notional=excluded.sell_notional""",
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
        "SELECT MAX(ts_ms) FROM block_trades WHERE symbol=?", (symbol,)
    ).fetchone()
    return int(row[0]) if row and row[0] else 0


def run(args: argparse.Namespace) -> None:
    con = connect_db()
    symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
               if args.symbols else active_symbols(con, args.max_symbols, args.min_qv))
    now = int(time.time() * 1000)
    log(f"mode={'bootstrap' if args.bootstrap else 'incremental'} "
        f"symbols={len(symbols)}: {','.join(symbols[:8])}{'...' if len(symbols) > 8 else ''}")

    totals = {}
    for sym in symbols:
        try:
            if args.bootstrap:
                since = now - args.days * 86400 * 1000
            elif args.since_hours is not None:
                since = now - int(args.since_hours * 3600 * 1000)
            else:
                lt = last_ts(con, sym)
                since = lt + 1 if lt else now - args.days * 86400 * 1000
            t0 = time.time()
            trades = fetch_window(sym, since, now)
            n_blocks, thr, p99 = persist_symbol(con, sym, trades, since)
            totals[sym] = (len(trades), n_blocks, thr)
            log(f"  {sym:14s} trades={len(trades):7d} prints>=${thr:,.0f}: {n_blocks:4d} "
                f"(p99=${p99:,.0f}) {time.time()-t0:.1f}s")
        except Exception as exc:  # un symbole en erreur n'arrete pas la passe
            log(f"  {sym:14s} ERROR {type(exc).__name__}: {exc}")
        time.sleep(SLEEP_BETWEEN_REQ)
    con.close()
    nb = sum(v[1] for v in totals.values())
    log(f"done: {sum(v[0] for v in totals.values())} trades, {nb} nouveaux prints")


def main() -> int:
    ap = argparse.ArgumentParser(description="Aster big prints collector (aggTrades)")
    ap.add_argument("--bootstrap", action="store_true", help="backfill 2-3 jours, 6 majeures")
    ap.add_argument("--days", type=float, default=BOOTSTRAP_DAYS)
    ap.add_argument("--since-hours", type=float, default=None)
    ap.add_argument("--symbols", default=None, help="liste CSV, override")
    ap.add_argument("--max-symbols", type=int, default=20)
    ap.add_argument("--min-qv", type=float, default=50_000.0, help="qv 3j min $ (actifs)")
    args = ap.parse_args()
    if args.bootstrap and not args.symbols:
        args.symbols = ",".join(MAJOR_SYMBOLS)
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
