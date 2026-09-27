#!/usr/bin/env python3
"""Rattrapage frais OHLCV fomo via mobula — SANS navigateur, SANS systemd stop.

Le tick collector (WS browser fragile) perd des bougies entre ses reloads.
Ce top-up comble le récent sur 3 périodes (1 appel mobula chacune) :
  1m → 3 dernières heures, 15m → 48 dernières heures, 1h → 7 derniers jours.
Contrairement à fomo_ohlcv_backfill.py il ne stoppe PAS le collector 24/7 :
transactions courtes (commit par token) + busy_timeout=30000 (WAL) suffisent.

Usage :
  .venv/bin/python scripts/fomo_mobula_topup.py --all
  .venv/bin/python scripts/fomo_mobula_topup.py --all --loop 15
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fomo_ohlcv_backfill import (QUOTE_MINTS, call, fresh_jwt,  # noqa: E402
                                 rows_to_candles, token_list)

DB = ROOT / "data" / "fomo" / "fomo.db"
TOPUP = {"1m": 3 * 3600, "15m": 48 * 3600, "1h": 7 * 86400}  # s
RETRY_DELAYS = (2.0, 5.0, 10.0)  # sur « database is locked »


def upsert_token(con: sqlite3.Connection, jwt: str, mint: str) -> int:
    """3 appels (1m/15m/1h), bornés [from;to], INSERT OR REPLACE,
    UN SEUL commit par token (une transaction fantôme = tout perdu)."""
    now_ms = int(time.time() * 1000)
    total = 0
    for period, secs in TOPUP.items():
        frm = now_ms - secs * 1000
        candles = [c for c in rows_to_candles(
            call(jwt, mint, period, frm, now_ms)) if frm <= c[0] <= now_ms]
        if candles:
            con.executemany(
                "INSERT OR REPLACE INTO fomo_ohlcv VALUES (?,?,?,?,?,?,?,?,?)",
                [(mint, period, t, o, h, l, c, v, time.time())
                 for t, o, h, l, c, v in candles])
            total += len(candles)
        time.sleep(0.2)  # mobula : pas un free tier GT, mais restons doux
    con.commit()
    return total


def upsert_token_retry(con: sqlite3.Connection, jwt: str, mint: str):
    """Retry 3× (2s, 5s, 10s) si la DB est lockée (collector qui écrit).
    Retourne (bougies, erreur_résiduelle)."""
    last: Exception | None = None
    for i, delay in enumerate((0.0,) + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            return upsert_token(con, jwt, mint), None
        except sqlite3.OperationalError as e:
            last = e
            if "locked" not in str(e).lower():
                return 0, e
        except Exception as e:  # réseau/API (call() a déjà retryé 3×)
            return 0, e
    return 0, last


def one_pass(con: sqlite3.Connection, jwt: str, mints: list[str]) -> int:
    t0, tot, fails = time.time(), 0, []
    for i, mint in enumerate(mints):
        n, err = upsert_token_retry(con, jwt, mint)
        if err:
            fails.append((mint, str(err)))
            print(f"  [{i+1}/{len(mints)}] {mint[:10]}… : ÉCHEC {err}",
                  flush=True)
            continue
        tot += n
        print(f"  [{i+1}/{len(mints)}] {mint[:10]}… : +{n}", flush=True)
    print(f"[topup] passe : {tot} bougies upsertées en {time.time()-t0:.0f}s, "
          f"{len(fails)} échec(s) résiduel(s)", flush=True)
    for mint, err in fails:
        print(f"  FAILED {mint} : {err}", flush=True)
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="tous les mints connus (fomo_tokens + fomo_ohlcv)")
    ap.add_argument("--mints", type=str, default="",
                    help="mints séparés par des virgules")
    ap.add_argument("--loop", type=int, default=0, metavar="N",
                    help="répète la passe toutes les N minutes (défaut one-shot)")
    args = ap.parse_args()

    con = sqlite3.connect(DB, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    mints = (token_list(con) if args.all
             else [m.strip() for m in args.mints.split(",") if m.strip()
                   and not m.startswith("0x") and m not in QUOTE_MINTS])
    print(f"[topup] {len(mints)} mints × {list(TOPUP)} — JWT frais…", flush=True)
    jwt = fresh_jwt()
    if not jwt:
        print("ERREUR : aucun JWT frais dans le localStorage du daemon")
        return 1
    one_pass(con, jwt, mints)
    while args.loop > 0:
        print(f"[topup] sommeil {args.loop} min", flush=True)
        time.sleep(args.loop * 60)
        jwt = fresh_jwt() or jwt  # re-fraîchir (exp ~1h)
        one_pass(con, jwt, mints)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
