#!/usr/bin/env python3
"""Collecteur d'Open Interest Aster — 1 passe = 1 snapshot par symbole.

Aster ne fournit PAS d'historique d'OI (/futures/data/* : 404) : la serie
n'existe que si ON la construit, un snapshot a la fois. Endpoint public
read-only : GET /fapi/v1/openInterest?symbol=X (champ openInterest, time ms),
prix via /fapi/v1/ticker/price (1 appel global, map en memoire).

Stockage : klines.db:oi_history — schema REBUILD (l'ancienne table, 184 lignes
a timestamps casses, a ete DROPpee) :
    symbol TEXT NOT NULL, open_interest REAL NOT NULL, price REAL,
    captured_at_ms INTEGER NOT NULL, PRIMARY KEY (symbol, captured_at_ms)

Passe BULK (P6, 30/09) — l'API INTERNE de l'UI (docs/24) :
bapi/future/v1/public/future/aster/ticker/pair = ~642 symboles en 1 appel
(curl_cffi chrome131, pas d'auth, pas de Cloudflare). UNITE VERIFIEE 30/09
sur BTC/ETH/SOL : l'OI bulk est un NOTIONAL USDT x2 (double face), PAS les
unites base de fapi (ratio bulk/(fapi_oi x px) = 2,0000) → table dediee
oi_history_bulk (jamais mixee avec oi_history) + validation croisee logguee
a chaque passe (ratio attendu ~2, une derive = changement de convention bapi).
Le header de poids est ABSENT sur bapi : note_weight l'avale (None) — bapi ne
semble pas compter sur le budget fapi 2 400/min.

Discipline :
  - INSERT OR IGNORE : un re-run dans la meme ms ne duplique pas ;
  - busy_timeout + commit explicite par passe (un lot = une transaction) ;
  - sleep entre appels, cooldown 65s sur HTTP 429 ;
  - un seul ecrivain klines.db a la fois (pas de backfill en parallele).

Usage :
  .venv/bin/python scripts/oi_collector.py               # 1 passe, tous les symboles 1h
  .venv/bin/python scripts/oi_collector.py --symbols BTCUSDT,ETHUSDT
  .venv/bin/python scripts/oi_collector.py --loop 4 --every 900   # 4 passes / 15 min
  .venv/bin/python scripts/oi_collector.py --bulk-only   # passe bulk bapi seule (~642 syms)
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
BASE = "https://fapi.asterdex.com"
BAPI_TICKER_URL = ("https://www.asterdex.com"
                   "/bapi/future/v1/public/future/aster/ticker/pair")
SLEEP_S = 0.3
COOLDOWN_429_S = 65.0
MAX_RETRIES_429 = 3
USER_AGENT = "trading-agent-oi-collector/1.0 (stdlib urllib)"
CROSS_DEFAULT = "BTCUSDT,ETHUSDT,SOLUSDT"

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


def http_get(path: str, timeout: float = 15.0) -> object:
    req = urllib.request.Request(
        BASE + path, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            aster_rate.note_weight(getattr(resp, "headers", None), "oi_collector")
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} sur {path}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"reseau indisponible sur {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"reponse non-JSON sur {path}") from exc


def http_get_retry(path: str, timeout: float = 15.0) -> object:
    for attempt in range(MAX_RETRIES_429):
        try:
            return http_get(path, timeout=timeout)
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


_BAPI_SESSION = None  # session curl_cffi paresseuse (chrome131)


def bapi_get(url: str, timeout: float = 15.0) -> object:
    """GET sur l'API INTERNE de l'UI (www.asterdex.com/bapi/...) : curl_cffi
    impersonate=chrome131 est REQUIS (pattern aster_ui_replay, docs/24) —
    pas d'auth, pas de Cloudflare, mais un client TLS non-imite peut etre
    defie. note_weight sur la reponse : header X-MBX-USED-WEIGHT-1M absent
    sur bapi → note_weight l'avale (None, rien n'est enregistre)."""
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
    """Validation croisee independante : pour les majors communes, comparer
    l'OI bulk (notional x2) au produit fapi OI (unites base) x prix bulk.
    Ratio ~2,000 attendu (verifie 30/09 sur BTC/ETH/SOL) — une derive signale
    un changement de convention cote bapi avant que les donnees soient mixees."""
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
    """1 passe BULK = ~642 symboles en 1 appel bapi ticker/pair → oi_history_bulk
    (unites notional x2, voir l'en-tete). 1 commit."""
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
        con.commit()  # un lot = une transaction, commit explicite
        inserted = max(0, cur.rowcount)
    cross = cross_check({r[0]: (r[1], r[2]) for r in rows}, cross_syms, timeout)
    return {"syms": len(data), "rows": len(rows), "inserted": inserted,
            "skipped": skipped, "cross": cross}


def snapshot_pass(
    con: sqlite3.Connection, symbols: list[str], timeout: float,
) -> dict:
    """1 passe = 1 snapshot OI + prix par symbole, 1 commit."""
    now_ms = int(time.time() * 1000)
    prices: dict[str, float] = {}
    try:
        raw = http_get_retry("/fapi/v1/ticker/price", timeout=timeout)
        if isinstance(raw, list):
            prices = {p["symbol"]: float(p["price"])
                      for p in raw if isinstance(p, dict) and p.get("price")}
    except RuntimeError as exc:
        print(f"  ! ticker/price global : {exc} — prix seront NULL", file=sys.stderr,
              flush=True)

    inserted, failed = 0, []
    rows: list[tuple] = []
    for i, sym in enumerate(symbols):
        if i:
            time.sleep(SLEEP_S)
        try:
            payload = http_get_retry(
                f"/fapi/v1/openInterest?symbol={sym}", timeout=timeout)
            oi = float(payload["openInterest"])
            cap_ms = int(payload.get("time") or now_ms)
        except (RuntimeError, KeyError, TypeError, ValueError) as exc:
            failed.append(sym)
            print(f"  ! {sym} : {str(exc)[:80]}", file=sys.stderr, flush=True)
            continue
        if oi < 0:
            failed.append(sym)
            print(f"  ! {sym} : OI negatif ({oi})", file=sys.stderr, flush=True)
            continue
        rows.append((sym, oi, prices.get(sym), cap_ms))

    if rows:
        cur = con.executemany(
            "INSERT OR IGNORE INTO oi_history "
            "(symbol, open_interest, price, captured_at_ms) VALUES (?,?,?,?)",
            rows)
        con.commit()  # un lot = une transaction, commit explicite
        inserted = max(0, cur.rowcount)
    return {"captured": len(rows), "inserted": inserted, "failed": failed,
            "ts_max": max((r[3] for r in rows), default=0)}


def sim_symbols_1h(con: sqlite3.Connection) -> list[str]:
    """Univers du sim : tous les symboles 1h du warehouse."""
    return [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval = '1h' "
        "ORDER BY symbol").fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Snapshot OI Aster -> klines.db:oi_history (+ bulk bapi -> oi_history_bulk)")
    ap.add_argument("--symbols", default="", help="CSV (defaut : univers 1h du sim).")
    ap.add_argument("--loop", type=int, default=1,
                    help="Nombre de passes (0 = infini, Ctrl-C pour stopper).")
    ap.add_argument("--every", type=int, default=900,
                    help="Secondes entre passes en mode --loop (defaut 900 = 15 min).")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--skip-bulk", action="store_true",
                    help="Ne pas faire la passe bulk bapi (oi_history_bulk).")
    ap.add_argument("--bulk-only", action="store_true",
                    help="Passe bulk bapi UNIQUEMENT (pas la boucle fapi par symbole).")
    ap.add_argument("--cross-syms", default=CROSS_DEFAULT,
                    help="CSV des majors pour la validation croisee bulk vs fapi "
                         "(vide = desactivee).")
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
        print(f"=== OI collector — {len(symbols)} symbole(s) fapi, "
              f"bulk={'off' if args.skip_bulk else ('seul' if args.bulk_only else 'on')}, "
              f"loop={args.loop or 'infini'}, every={args.every}s ===", flush=True)

        pas = 0
        while True:
            pas += 1
            t0 = time.time()
            res = {"captured": 0, "failed": []}
            if not args.bulk_only:
                res = snapshot_pass(con, symbols, args.timeout)
                total = con.execute("SELECT COUNT(*) FROM oi_history").fetchone()[0]
                syms_h = con.execute("SELECT COUNT(DISTINCT symbol) FROM oi_history"
                                     ).fetchone()[0]
                print(f"[pass {pas}] capture={res['captured']}/{len(symbols)} "
                      f"echecs={len(res['failed'])} "
                      f"{', '.join(res['failed'][:5]) if res['failed'] else '-'} | "
                      f"table: {total} snapshots, {syms_h} symboles "
                      f"({time.time() - t0:.1f}s)", flush=True)
                for sym, oi, px, ms in con.execute(
                        "SELECT symbol, open_interest, price, MAX(captured_at_ms) "
                        "FROM oi_history GROUP BY symbol "
                        "ORDER BY open_interest DESC LIMIT 6"):
                    print(f"    {sym:<14} OI={oi:>16,.0f}  px={px if px is not None else '?'}",
                          flush=True)
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
