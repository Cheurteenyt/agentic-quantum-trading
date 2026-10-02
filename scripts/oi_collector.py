#!/usr/bin/env python3
"""Collecteur d'Open Interest Aster — 1 passe = 1 snapshot par symbole.

Aster ne fournit PAS d'historique d'OI (/futures/data/* : 404) : la serie
n'existe que si ON la construit, un snapshot a la fois. Endpoint public
read-only : GET /fapi/v1/openInterest?symbol=X (champ openInterest, time ms),
prix via /fapi/v1/ticker/price (1 appel global, map en memoire).

Stockage : klines.db:oi_history — schema REBUILD :
    symbol TEXT NOT NULL, open_interest REAL NOT NULL, price REAL,
    captured_at_ms INTEGER NOT NULL, PRIMARY KEY (symbol, captured_at_ms)

Passe BULK (P6) — bapi ticker/pair ~645 symboles / 1 appel (notional x2).
Table oi_history_bulk — JAMAIS mixee avec oi_history sans conversion x2.

Perf (bench 02/10, Aster live) — le goulot n'etait PAS le rate-limit OI :
  A  seq + sleep 0.3          30 sym : 14.26 s   (ancien defaut)
  B  urllib ThreadPool 8      30 sym :  0.70 s   (TLS/handshake par GET)
  C  http.client pool 8       30 sym :  0.04 s   (connexions reutilisees)
  D  pool 16                  100 sym :  1.17 s   weight_max 233/2400
  E  bulk bapi                645 sym :  0.36 s   (meilleur pour l'univers)
Correctness C vs urllib : max |dOI|/OI = 0.

Defaut : --workers 8 = pool de connexions HTTPS persistantes.
--workers 1 = ancien chemin exact (seq + sleep 0.3).
Garde poids >= 1500 -> pause fin de minute (aster_blocktrades).

Usage :
  .venv/bin/python scripts/oi_collector.py
  .venv/bin/python scripts/oi_collector.py --workers 1
  .venv/bin/python scripts/oi_collector.py --bulk-only
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

import aster_rate
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
BASE = "https://fapi.asterdex.com"
HOST = "fapi.asterdex.com"
BAPI_TICKER_URL = ("https://www.asterdex.com"
                   "/bapi/future/v1/public/future/aster/ticker/pair")
SLEEP_S = 0.3
COOLDOWN_429_S = 65.0
MAX_RETRIES_429 = 3
WEIGHT_PAUSE = 1500
USER_AGENT = "trading-agent-oi-collector/1.2 (pool)"
CROSS_DEFAULT = "BTCUSDT,ETHUSDT,SOLUSDT"
_SSL_CTX = ssl.create_default_context()

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS oi_history (
    symbol          TEXT    NOT NULL,
    open_interest   REAL    NOT NULL CHECK (open_interest >= 0),
    price           REAL,
    captured_at_ms  INTEGER NOT NULL CHECK (captured_at_ms > 0),
    PRIMARY KEY (symbol, captured_at_ms)
);
"""

CREATE_SQL_BULK = """
CREATE TABLE IF NOT EXISTS oi_history_bulk (
    symbol          TEXT    NOT NULL,
    open_interest   REAL    NOT NULL CHECK (open_interest >= 0),
    price           REAL,
    captured_at_ms  INTEGER NOT NULL CHECK (captured_at_ms > 0),
    PRIMARY KEY (symbol, captured_at_ms)
);
"""


def http_get(path: str, timeout: float = 15.0) -> tuple[object, int | None]:
    req = urllib.request.Request(
        BASE + path, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            weight = aster_rate.note_weight(
                getattr(resp, "headers", None), "oi_collector")
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return body, weight
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} sur {path}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"reseau indisponible sur {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"reponse non-JSON sur {path}") from exc


def _maybe_weight_pause(weight: int | None) -> None:
    if weight is not None and weight >= WEIGHT_PAUSE:
        pause = 60.0 - (time.time() % 60.0) + 0.5
        print(f"  ! poids={weight}>={WEIGHT_PAUSE} — pause {pause:.0f}s "
              f"(fin de minute)", flush=True)
        time.sleep(pause)


def http_get_retry(path: str, timeout: float = 15.0) -> object:
    for attempt in range(MAX_RETRIES_429):
        try:
            body, weight = http_get(path, timeout=timeout)
            _maybe_weight_pause(weight)
            return body
        except RuntimeError as exc:
            if "HTTP 429" in str(exc) and attempt < MAX_RETRIES_429 - 1:
                print(f"  ! 429 {path} — cooldown {COOLDOWN_429_S:.0f}s", flush=True)
                time.sleep(COOLDOWN_429_S)
                continue
            raise
    raise RuntimeError(f"429 persistant sur {path}")


def init_db(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA busy_timeout = 10000")
    con.execute(CREATE_SQL)
    con.execute(CREATE_SQL_BULK)
    cols = {r[1] for r in con.execute("PRAGMA table_info(oi_history)").fetchall()}
    if "captured_at_ms" not in cols:
        raise RuntimeError(
            "oi_history a l'ANCIEN schema (captured_at, timestamps casses). "
            "La DROP puis laisse ce script la recreer : "
            "DROP TABLE oi_history;")


_BAPI_SESSION = None


def bapi_get(url: str, timeout: float = 15.0) -> object:
    global _BAPI_SESSION
    if _BAPI_SESSION is None:
        try:
            from curl_cffi import requests as cffi
        except ImportError as exc:
            raise RuntimeError(
                "curl_cffi absent du venv (uv pip install curl_cffi)") from exc
        _BAPI_SESSION = cffi.Session(impersonate="chrome131")
    try:
        resp = _BAPI_SESSION.get(url, timeout=timeout, headers={
            "Referer": "https://www.asterdex.com/en/trade/pro/futures/BTCUSDT",
            "Origin": "https://www.asterdex.com",
            "Accept": "application/json, text/plain, */*"})
        aster_rate.note_weight(dict(resp.headers), "oi_collector_bapi")
        return resp.json()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"bapi indisponible: {str(exc)[:80]}") from exc


def cross_check(bulk_map: dict, cross_syms: list[str], timeout: float) -> list:
    out = []
    for sym in cross_syms:
        if sym not in bulk_map:
            continue
        try:
            payload = http_get_retry(
                f"/fapi/v1/openInterest?symbol={sym}", timeout=timeout)
            fapi_oi = float(payload["openInterest"])
        except (RuntimeError, KeyError, TypeError, ValueError) as exc:
            print(f"  [cross] {sym} : fapi indisponible ({str(exc)[:60]})",
                  file=sys.stderr, flush=True)
            continue
        b_oi, px = bulk_map[sym]
        if fapi_oi <= 0 or px <= 0:
            continue
        ratio = b_oi / (fapi_oi * px)
        ecart = (ratio - 2.0) / 2.0 * 100.0
        out.append((sym, ratio, ecart))
        print(f"  [cross] {sym:<10} bulk={b_oi:>15,.0f}  fapi={fapi_oi:,.3f}"
              f"x{px:,.4f}  ratio={ratio:.4f}  ecart vs x2: {ecart:+.2f}%",
              flush=True)
    return out


def bulk_pass(con: sqlite3.Connection, timeout: float,
              cross_syms: list[str]) -> dict:
    now_ms = int(time.time() * 1000)
    j = bapi_get(BAPI_TICKER_URL, timeout)
    data = j.get("data") if isinstance(j, dict) else None
    if not isinstance(data, list) or not data:
        raise RuntimeError(
            f"bapi ticker/pair : enveloppe inattendue ({type(j).__name__})")
    rows, skipped = [], 0
    for x in data:
        try:
            sym = str(x["symbol"]).upper()
            oi = float(x["openInterest"])
            px = float(x["lastPrice"])
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if oi < 0:
            skipped += 1
            continue
        rows.append((sym, oi, px, now_ms))
    inserted = 0
    if rows:
        cur = con.executemany(
            "INSERT OR IGNORE INTO oi_history_bulk "
            "(symbol, open_interest, price, captured_at_ms) VALUES (?,?,?,?)",
            rows)
        con.commit()
        inserted = max(0, cur.rowcount)
    cross = cross_check({r[0]: (r[1], r[2]) for r in rows}, cross_syms, timeout)
    return {"syms": len(data), "rows": len(rows), "inserted": inserted,
            "skipped": skipped, "cross": cross}


def _parse_oi_payload(sym: str, payload: object, prices: dict, now_ms: int) -> tuple:
    if not isinstance(payload, dict):
        raise RuntimeError("payload non-dict")
    oi = float(payload["openInterest"])
    if oi < 0:
        raise RuntimeError(f"OI negatif ({oi})")
    cap_ms = int(payload.get("time") or now_ms)
    return (sym, oi, prices.get(sym), cap_ms)


def _fetch_one_oi_urllib(sym: str, prices: dict, now_ms: int,
                        timeout: float) -> tuple:
    payload = http_get_retry(
        f"/fapi/v1/openInterest?symbol={sym}", timeout=timeout)
    return _parse_oi_payload(sym, payload, prices, now_ms)


def _pool_fetch_oi(symbols: list[str], prices: dict, now_ms: int,
                   workers: int, timeout: float) -> tuple[list[tuple], list[str]]:
    """N connexions HTTPS reutilisees — evite le handshake TLS par symbole.

    Chaque worker possede SA connexion (http.client n'est pas thread-safe).
    """
    nconn = max(1, min(workers, len(symbols)))
    # repartition equitable
    chunks: list[list[str]] = [[] for _ in range(nconn)]
    for i, sym in enumerate(symbols):
        chunks[i % nconn].append(sym)
    chunks = [c for c in chunks if c]

    rows: list[tuple] = []
    failed: list[str] = []

    def worker(chunk: list[str]) -> tuple[list[tuple], list[str], int | None]:
        local_rows: list[tuple] = []
        local_fail: list[str] = []
        last_w: int | None = None
        conn = http.client.HTTPSConnection(
            HOST, context=_SSL_CTX, timeout=timeout)
        try:
            for sym in chunk:
                for attempt in range(MAX_RETRIES_429):
                    try:
                        conn.request(
                            "GET",
                            f"/fapi/v1/openInterest?symbol={sym}",
                            headers={"User-Agent": USER_AGENT},
                        )
                        resp = conn.getresponse()
                        raw = resp.read()
                        w_hdr = resp.getheader("X-MBX-USED-WEIGHT-1M")
                        if w_hdr is not None:
                            try:
                                last_w = int(str(w_hdr).strip())
                                aster_rate.note_weight(
                                    {"X-MBX-USED-WEIGHT-1M": w_hdr},
                                    "oi_collector",
                                )
                            except ValueError:
                                pass
                        if resp.status == 429:
                            if attempt < MAX_RETRIES_429 - 1:
                                time.sleep(COOLDOWN_429_S)
                                # reconnexion propre apres cooldown
                                conn.close()
                                conn = http.client.HTTPSConnection(
                                    HOST, context=_SSL_CTX, timeout=timeout)
                                continue
                            raise RuntimeError(f"HTTP 429 sur {sym}")
                        if resp.status != 200:
                            raise RuntimeError(f"HTTP {resp.status} sur {sym}")
                        payload = json.loads(raw.decode("utf-8", errors="replace"))
                        local_rows.append(
                            _parse_oi_payload(sym, payload, prices, now_ms))
                        break
                    except (RuntimeError, KeyError, TypeError, ValueError,
                            json.JSONDecodeError, OSError) as exc:
                        if attempt >= MAX_RETRIES_429 - 1:
                            local_fail.append(sym)
                            print(f"  ! {sym} : {str(exc)[:80]}",
                                  file=sys.stderr, flush=True)
                        elif "429" in str(exc):
                            time.sleep(COOLDOWN_429_S)
                            conn.close()
                            conn = http.client.HTTPSConnection(
                                HOST, context=_SSL_CTX, timeout=timeout)
                        else:
                            local_fail.append(sym)
                            print(f"  ! {sym} : {str(exc)[:80]}",
                                  file=sys.stderr, flush=True)
                            break
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return local_rows, local_fail, last_w

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futs = [pool.submit(worker, ch) for ch in chunks]
        max_w: int | None = None
        for fut in as_completed(futs):
            lr, lf, lw = fut.result()
            rows.extend(lr)
            failed.extend(lf)
            if lw is not None:
                max_w = lw if max_w is None else max(max_w, lw)
        _maybe_weight_pause(max_w)
    return rows, failed


def snapshot_pass(
    con: sqlite3.Connection, symbols: list[str], timeout: float,
    workers: int = 1,
) -> dict:
    """1 passe = 1 snapshot OI + prix par symbole, 1 commit.

    workers=1 : chemin historique (seq + sleep 0.3 s) — urllib.
    workers>1 : pool de connexions HTTPS persistantes (http.client).
    """
    now_ms = int(time.time() * 1000)
    prices: dict[str, float] = {}
    try:
        raw = http_get_retry("/fapi/v1/ticker/price", timeout=timeout)
        if isinstance(raw, list):
            prices = {p["symbol"]: float(p["price"])
                      for p in raw if isinstance(p, dict) and p.get("price")}
    except RuntimeError as exc:
        print(f"  ! ticker/price global : {exc} — prix seront NULL",
              file=sys.stderr, flush=True)

    inserted, failed = 0, []
    rows: list[tuple] = []

    if workers <= 1:
        for i, sym in enumerate(symbols):
            if i:
                time.sleep(SLEEP_S)
            try:
                rows.append(_fetch_one_oi_urllib(sym, prices, now_ms, timeout))
            except (RuntimeError, KeyError, TypeError, ValueError) as exc:
                failed.append(sym)
                print(f"  ! {sym} : {str(exc)[:80]}", file=sys.stderr, flush=True)
    else:
        rows, failed = _pool_fetch_oi(
            symbols, prices, now_ms, workers, timeout)

    if rows:
        cur = con.executemany(
            "INSERT OR IGNORE INTO oi_history "
            "(symbol, open_interest, price, captured_at_ms) VALUES (?,?,?,?)",
            rows)
        con.commit()
        inserted = max(0, cur.rowcount)
    return {"captured": len(rows), "inserted": inserted, "failed": failed,
            "ts_max": max((r[3] for r in rows), default=0),
            "workers": workers}


def sim_symbols_1h(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval = '1h' "
        "ORDER BY symbol").fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Snapshot OI Aster -> klines.db:oi_history (+ bulk bapi)")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--loop", type=int, default=1)
    ap.add_argument("--every", type=int, default=900)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--workers", type=int, default=8,
                    help="1=legacy seq+sleep; >=2=HTTPS connection pool (defaut 8)")
    ap.add_argument("--skip-bulk", action="store_true")
    ap.add_argument("--bulk-only", action="store_true")
    ap.add_argument("--cross-syms", default=CROSS_DEFAULT)
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    try:
        init_db(con)
        symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
                   or sim_symbols_1h(con))
        cross_syms = [s.strip().upper() for s in args.cross_syms.split(",")
                      if s.strip()]
        if not symbols and not args.bulk_only:
            print("aucun symbole (klines.db 1h vide ?)", file=sys.stderr)
            return 1
        workers = max(1, int(args.workers))
        if symbols:
            workers = min(workers, len(symbols))
        print(f"=== OI collector — {len(symbols)} symbole(s) fapi "
              f"workers={workers}, "
              f"bulk={'off' if args.skip_bulk else ('seul' if args.bulk_only else 'on')}, "
              f"loop={args.loop or 'infini'}, every={args.every}s ===", flush=True)

        pas = 0
        while True:
            pas += 1
            t0 = time.time()
            res = {"captured": 0, "failed": []}
            if not args.bulk_only:
                res = snapshot_pass(con, symbols, args.timeout, workers=workers)
                total = con.execute("SELECT COUNT(*) FROM oi_history").fetchone()[0]
                syms_h = con.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM oi_history").fetchone()[0]
                print(f"[pass {pas}] capture={res['captured']}/{len(symbols)} "
                      f"echecs={len(res['failed'])} "
                      f"{', '.join(res['failed'][:5]) if res['failed'] else '-'} | "
                      f"table: {total} snapshots, {syms_h} symboles "
                      f"({time.time() - t0:.1f}s, workers={res.get('workers', workers)})",
                      flush=True)
                for sym, oi, px, ms in con.execute(
                        "SELECT symbol, open_interest, price, MAX(captured_at_ms) "
                        "FROM oi_history GROUP BY symbol "
                        "ORDER BY open_interest DESC LIMIT 6"):
                    print(f"    {sym:<14} OI={oi:>16,.0f}  "
                          f"px={px if px is not None else '?'}", flush=True)
            if not args.skip_bulk:
                try:
                    bulk = bulk_pass(con, args.timeout, cross_syms)
                    total_b = con.execute(
                        "SELECT COUNT(*) FROM oi_history_bulk").fetchone()[0]
                    syms_b = con.execute(
                        "SELECT COUNT(DISTINCT symbol) FROM oi_history_bulk"
                    ).fetchone()[0]
                    print(f"[bulk {pas}] {bulk['syms']} syms recus, "
                          f"{bulk['rows']} rows (+{bulk['inserted']} nouveaux), "
                          f"echecs={bulk['skipped']} | table: {total_b} snapshots, "
                          f"{syms_b} symboles (notional x2)", flush=True)
                except RuntimeError as exc:
                    print(f"  ! passe bulk : {exc}", file=sys.stderr, flush=True)
            if args.loop and pas >= args.loop:
                return 0
            time.sleep(max(1, args.every))
    except KeyboardInterrupt:
        print("interrompu (Ctrl-C) — dernier commit deja en base", flush=True)
        return 0
    finally:
        con.commit()
        con.close()


if __name__ == "__main__":
    sys.exit(main())
