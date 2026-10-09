#!/usr/bin/env python3
"""Collecteur premium Aster 24/7 via WebSocket !markPrice@arr @1s (30/09).

Remplace le REST aster_premium_collector (timer 15 min) : le flux pousse
TOUS les symboles chaque seconde (1 msg/s, sous la limite dure 10/s), la
fraîcheur passe de 15 min à 1 s. Même table premium_history (klines.db),
même schéma, nouveau transport. Throttle 1 échantillon/symbole/minute
(la prime oscille lentement — suffisant pour les études).

Frame (V3 « WebSocket Market Streams », vérifié sur les 1ers frames) :
  e=markPriceUpdate  E=event time ms  s=symbole
  p=mark price  i=index price  P=estimated settle (ignoré)
  r=funding rate  T=next funding time ms

Ping/pong : la lib websockets répond automatiquement aux pings serveur
(RFC 6455, le serveur ping ~5 min, exige le pong sous 15 min) ;
ping_interval=20 garde aussi le NAT vivant. Connexion max 24 h →
reconnexion programmée à 23 h. Commit PAR BATCH, jamais de txn ouverte
au repos (la règle anti-txn-fantôme).

    python scripts/aster_markprice_ws.py            # boucle infinie (systemd)
    python scripts/aster_markprice_ws.py --test 15  # écoute 15 s et quitte
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
WS_URL = "wss://fstream.asterdex.com/ws/!markPrice@arr"
SAMPLE_INTERVAL_S = 60     # 1 échantillon/symbole/minute (le throttle)
FLUSH_INTERVAL_S = 5       # commit par batch, la connexion DB vit < 1 s
MAX_CONN_S = 23 * 3600     # reconnexion programmée sous la limite serveur 24 h
LOG_INTERVAL_S = 60

INSERT = """INSERT OR REPLACE INTO premium_history
    (symbol, mark_price, index_price, premium_pct, last_funding_rate,
     next_funding_time_ms, captured_at_ms) VALUES (?,?,?,?,?,?,?)"""

# La rétention (audit 30/09) : premium_history > 30 j. Unité VÉRIFIÉE au
# PRAGMA + sonde (30/09) : captured_at_ms en MILLISECONDES (last=1790728677164).
PREMIUM_RETENTION_DAYS = 30
_last_prune_day = -1


def prune_daily() -> int:
    """Le prune 1×/j de premium_history (appelé au flush, la date en mémoire).
    -1 = déjà prune aujourd'hui ou DB occupée (re-tente au flush suivant).
    Cutoff en MS (×1000) — le piège d'unité du projet."""
    global _last_prune_day
    day = int(time.time() // 86400)
    if day == _last_prune_day:
        return -1
    _last_prune_day = day
    cutoff_ms = int((time.time() - PREMIUM_RETENTION_DAYS * 86400) * 1000)
    try:
        con = sqlite3.connect(str(DB_PATH), timeout=30)
        try:
            con.execute("PRAGMA busy_timeout=30000")
            cur = con.execute(
                "DELETE FROM premium_history WHERE captured_at_ms < ?",
                (cutoff_ms,))
            con.commit()
            return cur.rowcount
        finally:
            con.close()
    except Exception as exc:
        _last_prune_day = -1
        print(f"[markprice-ws] prune err : {exc}", flush=True)
        return -1


def load_symbols() -> frozenset[str]:
    """LA liste du parc (source de vérité : aster_premium_collector)."""
    from aster_premium_collector import SYMS
    return frozenset(SYMS)


def parse_frame(raw: str | bytes) -> list[dict]:
    """Frame -> lignes normalisées. /ws/!markPrice@arr pousse un tableau
    nu ; le format combined-stream ({"data": [...]}) est géré aussi."""
    try:
        msg = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(msg, dict):
        msg = msg.get("data") or []
    if not isinstance(msg, list):
        return []
    out: list[dict] = []
    now_ms = int(time.time() * 1000)
    for d in msg:
        try:
            mark, idx = float(d["p"]), float(d["i"])
            # D-08 (ronde 6) : un index manquant/nul produisait une prime
            # FICTIVE 0.0 — indistinguishable d'une vraie prime nulle dans
            # premium_history (le consommateur crowding_composite absorbe le
            # faux zéro). On saute la row, comme une frame corrompue.
            if not idx:
                continue
            out.append({
                "symbol": str(d["s"]),
                "mark": mark,
                "idx": idx,
                "prem": round((mark / idx - 1) * 100, 6),
                "rate": float(d["r"]),
                "next_funding_ms": int(d["T"]),
                "captured_at_ms": now_ms,
            })
        except (KeyError, ValueError, TypeError):
            continue
    return out


def select_samples(rows: list[dict], last_write: dict[str, float],
                   now_s: float | None = None,
                   interval_s: int = SAMPLE_INTERVAL_S) -> list[dict]:
    """Le throttle 1/min/symbole — fonction pure d'état (testable)."""
    now_s = time.time() if now_s is None else now_s
    keep = []
    for r in rows:
        if now_s - last_write.get(r["symbol"], 0.0) >= interval_s:
            last_write[r["symbol"]] = now_s
            keep.append(r)
    return keep


def store(samples: list[dict]) -> int:
    """Flush par batch : connexion courte, UN commit, close. 0 txn ouverte
    au repos (le write-lock ne survit jamais à l'appel réseau suivant)."""
    if not samples:
        return 0
    con = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.executemany(INSERT, [
            (s["symbol"], s["mark"], s["idx"], s["prem"],
             s["rate"], s["next_funding_ms"], s["captured_at_ms"])
            for s in samples])
        con.commit()
        return len(samples)
    finally:
        con.close()


async def listen(duration_s: float | None = None) -> None:
    import websockets

    symbols = load_symbols()
    deadline_test = time.time() + duration_s if duration_s else None
    backoff = 2
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20) as ws:
                print(f"[markprice-ws] connecté : {WS_URL}", flush=True)
                backoff = 2
                conn_deadline = time.time() + MAX_CONN_S  # 24 h serveur
                last_write: dict[str, float] = {}
                buffer: list[dict] = []
                last_flush = last_log = time.time()
                n_frames = n_stored = 0
                async for raw in ws:
                    n_frames += 1
                    rows = [r for r in parse_frame(raw)
                            if r["symbol"] in symbols]
                    buffer.extend(select_samples(rows, last_write))
                    now = time.time()
                    if buffer and now - last_flush >= FLUSH_INTERVAL_S:
                        n_stored += store(buffer)
                        buffer = []
                        last_flush = now
                    removed = prune_daily()  # 1×/j (check date interne)
                    if removed >= 0:
                        print(f"[markprice-ws] prune : {removed} lignes "
                              f"premium_history > {PREMIUM_RETENTION_DAYS}j",
                              flush=True)
                    if now - last_log >= LOG_INTERVAL_S:
                        print(f"[markprice-ws] {n_frames / (now - last_log):.1f}"
                              f" frame/s | {len(last_write)} symboles | "
                              f"{n_stored} échantillons écrits (60 s)",
                              flush=True)
                        n_frames = n_stored = 0
                        last_log = now
                    if now > conn_deadline:
                        store(buffer)  # jamais de donnée reçue non stockée
                        print("[markprice-ws] reconnexion programmée 24 h",
                              flush=True)
                        break
                    if deadline_test and now > deadline_test:
                        store(buffer)
                        print(f"[markprice-ws] fenêtre de test : "
                              f"{len(last_write)} symboles échantillonnés",
                              flush=True)
                        return
                if deadline_test:
                    return  # break propre de la reconnexion 24 h en test
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[markprice-ws] déconnexion : {type(exc).__name__} — "
                  f"reconnexion dans {backoff}s", flush=True)
            if deadline_test and time.time() > deadline_test - backoff:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


def main() -> int:
    ap = argparse.ArgumentParser(description="Collecteur premium WS Aster")
    ap.add_argument("--test", type=int, default=0, metavar="SECONDES",
                    help="écoute limitée (debug) puis quitte")
    args = ap.parse_args()
    try:
        asyncio.run(listen(args.test or None))
    except KeyboardInterrupt:
        print("[markprice-ws] arrêt manuel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
