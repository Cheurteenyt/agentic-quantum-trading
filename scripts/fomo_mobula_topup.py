#!/usr/bin/env python3
"""Rattrapage frais OHLCV fomo via mobula — SANS navigateur, SANS systemd stop.

Le tick collector (WS browser fragile) perd des bougies entre ses reloads.
Ce top-up comble le récent sur 3 périodes (1 appel mobula chacune) :
  1m → 3 dernières heures, 15m → 48 dernières heures, 1h → 7 derniers jours.
Contrairement à fomo_ohlcv_backfill.py il ne stoppe PAS le collector 24/7 :
transactions courtes (commit par token) + busy_timeout=30000 (WAL) suffisent.

ÉTAT 29/09 : les 16 « database is locked » de 19h47 venaient d'une TRANSACTION
FANTÔME — un commit/INSERT en échec « locked » sans rollback laissait la txn
ouverte, tenant le write-lock de fomo.db pendant les appels réseau (3,5 s/token)
des tokens suivants. Correction : rollback systématique sur TOUTE voie d'échec.
Dette documentée (docs/13) : fomo_ohlcv reste écrit dans fomo.db — 15+ lecteurs
(dont derek_watch.py) rendent une base dédiée cassante — mais writer BORNÉ
(commit par token, rollback anti-fantôme, busy_timeout 30 s, budget de passe).
L'état mort/vivant topup_dead a MIGRÉ vers data/fomo/fomo_mobula.db
(lecteur unique : ce script ; copie one-time ATTACH mode=ro, COUNT vérifié).

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
MOBULA_DB = ROOT / "data" / "fomo" / "fomo_mobula.db"  # base dédiée top-up
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
            con.rollback()  # ANTI-FANTÔME : une txn laissée ouverte tiendrait
            # le write-lock de fomo.db pendant les 3,5 s réseau du token suivant
            last = e
            if "locked" not in str(e).lower():
                return 0, e
        except Exception as e:  # réseau/API (call() a déjà retryé 3×)
            con.rollback()
            return 0, e
    con.rollback()
    return 0, last


DEAD_SKIP_S = 12 * 3600


def ensure_dead_db() -> sqlite3.Connection:
    """fomo_mobula.db : base dédiée du top-up (zéro autre lecteur/écrivain).
    DDL assuré ici (la règle) ; copie ONE-TIME de topup_dead depuis fomo.db
    via ATTACH mode=ro (source en lecture seule) si la destination est vide,
    COUNT source == COUNT destination vérifié avant de continuer."""
    MOBULA_DB.parent.mkdir(parents=True, exist_ok=True)
    dcon = sqlite3.connect(MOBULA_DB.as_uri(), uri=True, timeout=30)
    dcon.execute("PRAGMA busy_timeout=30000")
    dcon.execute("PRAGMA journal_mode=WAL")
    dcon.execute("""CREATE TABLE IF NOT EXISTS topup_dead (
        mint TEXT PRIMARY KEY, last_zero REAL)""")
    n_dst = dcon.execute("SELECT COUNT(*) FROM topup_dead").fetchone()[0]
    if n_dst == 0 and DB.exists():
        # ATTACH en mode=ro : la source fomo.db ne peut jamais être altérée
        dcon.execute("ATTACH DATABASE ? AS src", (DB.as_uri() + "?mode=ro",))
        try:
            n_src = dcon.execute(
                "SELECT COUNT(*) FROM src.topup_dead").fetchone()[0]
            if n_src:
                dcon.execute("INSERT OR REPLACE INTO topup_dead "
                             "SELECT mint, last_zero FROM src.topup_dead")
        except sqlite3.OperationalError:
            n_src = 0  # pas encore de table source (première installation)
        n_dst = dcon.execute("SELECT COUNT(*) FROM topup_dead").fetchone()[0]
        assert n_dst == n_src, f"copie topup_dead : {n_src} != {n_dst}"
        dcon.commit()  # commit AVANT le detach (sinon « database src is locked »)
        dcon.execute("DETACH DATABASE src")
        print(f"[topup] topup_dead migrée : {n_dst} ligne(s) fomo.db → "
              f"fomo_mobula.db (COUNT vérifié)", flush=True)
    dcon.commit()
    return dcon


def _dead_filter(dcon: sqlite3.Connection, mints: list[str]) -> list[str]:
    """Les tokens morts (0 bougie récoltée au dernier essai) sortent
    12 h — sinon ils re-déclenchent à chaque passe pour toujours."""
    rows = dict(dcon.execute("SELECT mint, last_zero FROM topup_dead"))
    now = time.time()
    keep, revive = [], []
    for m in mints:
        lz = rows.get(m)
        if lz and now - lz < DEAD_SKIP_S:
            continue
        keep.append(m)
        if lz:
            revive.append(m)
    if revive:
        dcon.executemany("DELETE FROM topup_dead WHERE mint=?",
                         [(m,) for m in revive])
    dcon.commit()  # les revivals survivent même à un kill du timer
    return keep


PASS_BUDGET_S = 480.0  # < TimeoutStartSec=600 : la passe rend la main AVANT le kill


def one_pass(con: sqlite3.Connection, dcon: sqlite3.Connection, jwt: str,
             mints: list[str], budget_s: float = PASS_BUDGET_S) -> int:
    t0, tot, fails = time.time(), 0, []
    con.rollback()  # on n'entre JAMAIS en passe avec une txn héritée ouverte
    mints = _dead_filter(dcon, mints)
    for i, mint in enumerate(mints):
        if i and time.time() - t0 > budget_s:
            print(f"[topup] budget {budget_s:.0f}s atteint — "
                  f"{len(mints) - i} mints restants pour la prochaine passe",
                  flush=True)
            break
        n, err = upsert_token_retry(con, jwt, mint)
        if err:
            fails.append((mint, str(err)))
            print(f"  [{i+1}/{len(mints)}] {mint[:10]}… : ÉCHEC {err}",
                  flush=True)
            continue
        # le marquage mort/vivant est commité PAR TOKEN : un kill du timer
        # (timeout systemd) ne repart pas de zéro à la passe suivante
        try:
            if n == 0:
                dcon.execute("INSERT OR REPLACE INTO topup_dead VALUES (?,?)",
                             (mint, time.time()))
            else:
                dcon.execute("DELETE FROM topup_dead WHERE mint=?", (mint,))
            dcon.commit()
        except sqlite3.OperationalError:
            dcon.rollback()  # anti-fantôme (base dédiée, mais même règle)
            raise
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
    dcon = ensure_dead_db()
    mints = (token_list(con) if args.all
             else [m.strip() for m in args.mints.split(",") if m.strip()
                   and not m.startswith("0x") and m not in QUOTE_MINTS])
    # le TOP-UP SÉLECTIF : sans ça, chaque passe re-récupère 690 mints ×
    # 3 périodes (~10 000 appels mobula/jour) pour des bougies déjà à jour.
    # On ne garde que les tokens PÉRIMÉS : 1m plus vieux que 40 min OU
    # 15m plus vieux que 3 h (les inactifs et les morts sortent seuls).
    if args.all:
        fresh = []
        now_ms = time.time() * 1000
        for mint in mints:
            last1m = con.execute(
                "SELECT MAX(time) FROM fomo_ohlcv WHERE asset=? AND period='1m'",
                (mint,)).fetchone()[0]
            last15 = con.execute(
                "SELECT MAX(time) FROM fomo_ohlcv WHERE asset=? AND period='15m'",
                (mint,)).fetchone()[0]
            stale1m = (not last1m) or (now_ms - last1m) > 40 * 60 * 1000
            stale15 = (not last15) or (now_ms - last15) > 3 * 60 * 60 * 1000
            if stale1m or stale15:
                fresh.append(mint)
        n_skipped = len(mints) - len(fresh)
        mints = fresh
        print(f"[topup] {n_skipped} mints à jour skippés, "
              f"{len(mints)} périmés à rattraper", flush=True)
    print(f"[topup] {len(mints)} mints × {list(TOPUP)} — JWT frais…", flush=True)
    jwt = fresh_jwt()
    if not jwt:
        print("ERREUR : aucun JWT frais dans le localStorage du daemon")
        return 1
    one_pass(con, dcon, jwt, mints)
    while args.loop > 0:
        print(f"[topup] sommeil {args.loop} min", flush=True)
        time.sleep(args.loop * 60)
        jwt = fresh_jwt() or jwt  # re-fraîchir (exp ~1h)
        one_pass(con, dcon, jwt, mints)
    con.close()
    dcon.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
