#!/usr/bin/env python3
"""Collecteur klines Aster 24/7 via WebSocket @kline_1h / @kline_15m (docs/24).

Tue la staleness 24 h des klines REST : la bougie FERMEE (flag x=true) est
poussee en temps reel et ecrite dans klines.db (table klines, meme schema
que fetch_klines). Le nocturne fetch_klines REST RESTE le backfill qui
repare toute bougie manquee (meme PRIMARY KEY, pas de suppression).

Univers : les 36 symboles 1h de l'unite nocturne (trading-agent-nightly,
lignes fetch_klines --symbols, reprises exactement) + le bloc 15m
(15 symboles) = 51 streams combines dans UNE connexion (< 200 streams).

Limite serveur 10 messages entrants/s PAR connexion — deux parades :
  (a) compteur de debit : > 8 msg/s sur DEUX fenetres de 10 s consecutives
      -> les symboles les moins actifs passent en POLLING nocturne-only
      (streams retires puis reconnexion sur la liste reduite), et loggue ;
      un pic transitoire d'UNE fenetre (frontiere horaire : les 51 bougies
      fermees + updates tombent en meme temps, mesure 8,3/s le 30/09 a
      03:01 alors que le steady state est a 1-2,5/s) n'arme PAS la
      demotion ;
  (b) on n'ecrit QUE la bougie fermee (k.x=true) — les updates
      intermediaires (250 ms, l'essentiel du debit) sont ignorees :
      au plus 2 ecritures/symbole/h en 1h + 4/h en 15m.

Frame combined-stream : {"stream":"btcusdt@kline_1h","data":{"e":"kline",
"s":"BTCUSDT","k":{"t":open_ms,"T":close_ms,"i":"1h","o","h","l","c",
"v","q","V","x":false}}}.

snapshot_id : forme identique a fetch_klines (aster-{SYM}-{itv}-{lo}-{hi}-
{n}), calcule par lot au flush ; source = "aster_klines_ws" (provenance
transport distinguee du REST aster_public_klines_fapi_v3).

Ping/pong RFC 6455 automatique (lib websockets) ; reconnexion programmee
a 23 h (< limite serveur 24 h) ; backoff exp 2->60 s ; commit PAR BATCH
(un seul commit, txn jamais ouverte au repos — regle anti-txn-fantome).

    python scripts/aster_klines_ws.py            # boucle infinie (systemd)
    python scripts/aster_klines_ws.py --test 15  # ecoute 15 s et quitte
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
WS_BASE = "wss://fstream.asterdex.com/stream?streams="

# Source de verite : trading-agent-nightly.service (lignes fetch_klines).
UNIVERSE_1H = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT",
    "ADAUSDT", "ARBUSDT", "ASTERUSDT", "AVAXUSDT", "BOMEUSDT", "CATEUSDT",
    "DOGSUSDT", "FARTCOINUSDT", "GOOGLUSDT", "HUSDT", "HYPEUSDT",
    "LABUSDT", "LINKUSDT", "LTCUSDT", "MEMEUSDT", "MOODENGUSDT",
    "NEIROUSDT", "NOTUSDT", "NVDAUSDT", "PENGUUSDT", "PNUTUSDT",
    "PONSUSDT", "PORTALUSDT", "TRUMPUSDT", "TURBOUSDT", "WIFUSDT",
    "DRAMUSDT", "PIEVERSEUSDT", "VIRTUALUSDT", "MELANIAUSDT",
)  # 36
UNIVERSE_15M = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ASTERUSDT", "XRPUSDT", "DRAMUSDT",
    "PIEVERSEUSDT", "VIRTUALUSDT", "MELANIAUSDT", "BNBUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
)  # 15

FLUSH_INTERVAL_S = 5        # commit par batch (pattern markprice)
MAX_CONN_S = 23 * 3600      # reconnexion programmee sous la limite 24 h
RATE_WINDOW_S = 10.0        # fenetre du compteur de debit
RATE_LIMIT_PER_S = 8.0      # parade (a) : seuil < limite dure 10 msg/s
DEMOTE_CHECK_S = 10.0
DEMOTE_ARM_WINDOWS = 2      # fenetres consecutives > seuil avant demotion
DEMOTE_MIN_GAP_S = 60.0     # pas plus d'une demotion / minute
KEEP_MIN_SYMBOLS = 4        # on ne demote jamais tout
LOG_INTERVAL_S = 60
SOURCE_WS = "aster_klines_ws"

INSERT = """INSERT OR REPLACE INTO klines
    (symbol, interval, open_time, open, high, low, close, volume,
     taker_buy_volume, quote_volume, close_time, snapshot_id, source,
     fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""


def initial_active() -> dict[str, set[str]]:
    """symbole -> {intervalles} : 36 x 1h + 15 x 15m (le 15m est un
    sous-ensemble des 1h -> union, jamais ecrasement)."""
    active = {s: {"1h"} for s in UNIVERSE_1H}
    for s in UNIVERSE_15M:
        active[s] = active.get(s, set()) | {"15m"}
    return active


def build_url(active: dict[str, set[str]]) -> str:
    """URL combined-stream de la connexion (streams en minuscules)."""
    streams = [f"{s.lower()}@kline_{itv}"
               for s, itvs in sorted(active.items()) for itv in sorted(itvs)]
    return WS_BASE + "/".join(streams)


def parse_frame(raw: str | bytes) -> list[dict]:
    """Frame (combined-stream ou nue) -> lignes kline normalisees.
    Renvoie TOUTES les klines (flag closed inclus) ; le filtre x=true est
    fait par le runtime (parade b). Les CHECK de la table (prix > 0,
    volume >= 0, high >= low) sont verifies ici : une ligne invalide est
    ecartee plutot que de faire perdre tout le batch au flush."""
    try:
        msg = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(msg, dict):
        msg = msg.get("data") or msg  # combined-stream : data = payload
    if not isinstance(msg, dict) or msg.get("e") not in (None, "kline"):
        return []
    k = msg.get("k") or {}
    try:
        row = {
            "symbol": str(msg["s"]).upper(),
            "interval": str(k["i"]),
            "open_time": int(k["t"]),
            "close_time": int(k["T"]),
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "quote_volume": float(k.get("q") or 0.0),
            "taker_buy_volume": float(k.get("V") or 0.0),
            "closed": bool(k["x"]),
        }
    except (KeyError, ValueError, TypeError):
        return []
    if (row["open_time"] <= 0 or row["open"] <= 0 or row["high"] <= 0
            or row["low"] <= 0 or row["close"] <= 0 or row["volume"] < 0
            or row["high"] < row["low"]):
        return []
    return [row]


def snapshot_id_rows(sym: str, itv: str, open_times) -> str:
    """Forme identique a fetch_klines.snapshot_id_for_rows (lot en memoire)."""
    ts = list(open_times)
    return f"aster-{sym}-{itv}-{min(ts)}-{max(ts)}-{len(ts)}"


def store(buffer: dict) -> int:
    """Flush par batch : UNE connexion, UN commit, close. snapshot_id
    calcule par groupe (symbol, interval) sur le lot, source = WS."""
    if not buffer:
        return 0
    groups: dict[tuple[str, str], list] = {}
    for (sym, itv, open_time), r in buffer.items():
        groups.setdefault((sym, itv), []).append((open_time, r))
    now = time.time()
    lines = []
    for (sym, itv), items in groups.items():
        snap = snapshot_id_rows(sym, itv, (t for t, _ in items))
        for t, r in items:
            lines.append((sym, itv, t, r["open"], r["high"], r["low"],
                          r["close"], r["volume"], r["taker_buy_volume"],
                          r["quote_volume"], r["close_time"], snap,
                          SOURCE_WS, now))
    con = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.executemany(INSERT, lines)
        con.commit()
        return len(lines)
    finally:
        con.close()


def plan_demotion(symbols, counts: dict[str, int],
                  window_s: float = RATE_WINDOW_S,
                  limit_per_s: float = RATE_LIMIT_PER_S,
                  keep_min: int = KEEP_MIN_SYMBOLS) -> tuple[set[str], float]:
    """Parade (a), pure fonction (testable) : quels symboles passent en
    polling nocturne-only ? On retire les MOINS actifs d'abord jusqu'a
    debit projete < limite, sans jamais descendre sous keep_min."""
    symbols = list(symbols)
    total = sum(counts.get(s, 0) for s in symbols)
    projected = total / window_s
    demote: set[str] = set()
    for s in sorted(symbols, key=lambda x: counts.get(x, 0)):
        if projected < limit_per_s or len(symbols) - len(demote) <= keep_min:
            break
        demote.add(s)
        projected -= counts.get(s, 0) / window_s
    return demote, projected


async def listen(duration_s: float | None = None) -> None:
    import websockets

    active = initial_active()
    deadline_test = time.time() + duration_s if duration_s else None
    backoff = 2
    while True:
        url = build_url(active)
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                print(f"[klines-ws] connecte : {len(active)} symboles / "
                      f"{sum(len(v) for v in active.values())} streams",
                      flush=True)
                backoff = 2
                conn_deadline = time.time() + MAX_CONN_S  # 24 h serveur
                buffer: dict = {}
                ts: deque = deque()           # arrivees (fenetre 10 s)
                counts: dict[str, int] = {}   # msgs/symbole du check courant
                last_check = last_flush = last_log = time.time()
                last_demote = 0.0
                over_windows = 0
                n_frames = n_closed = n_stored = 0
                async for raw in ws:
                    now = time.time()
                    n_frames += 1
                    ts.append(now)
                    for r in parse_frame(raw):
                        counts[r["symbol"]] = counts.get(r["symbol"], 0) + 1
                        if r["closed"]:  # parade (b) : bougie fermee seule
                            buffer[(r["symbol"], r["interval"],
                                    r["open_time"])] = r
                            n_closed += 1
                    while ts and now - ts[0] > RATE_WINDOW_S:
                        ts.popleft()
                    if buffer and now - last_flush >= FLUSH_INTERVAL_S:
                        n_stored += store(buffer)
                        buffer = {}
                        last_flush = now
                    # parade (a) : controle du debit 10 msg/s / connexion
                    # (armee sur 2 fenetres consecutives : un pic transitoire
                    # de frontiere horaire ne demere rien)
                    if now - last_check >= DEMOTE_CHECK_S:
                        rate = len(ts) / RATE_WINDOW_S
                        if rate > RATE_LIMIT_PER_S:
                            over_windows += 1
                        else:
                            over_windows = 0
                        if (over_windows >= DEMOTE_ARM_WINDOWS
                                and now - last_demote >= DEMOTE_MIN_GAP_S):
                            demote, projected = plan_demotion(active, counts)
                            if demote:
                                for s in demote:
                                    active.pop(s, None)
                                last_demote = now
                                over_windows = 0
                                print(f"[klines-ws] debit soutenu "
                                      f"{rate:.1f} msg/s > "
                                      f"{RATE_LIMIT_PER_S:.0f} : "
                                      f"{len(demote)} symboles -> polling "
                                      f"nocturne-only (projete "
                                      f"{projected:.1f}/s) : "
                                      f"{', '.join(sorted(demote))}",
                                      flush=True)
                                store(buffer)  # jamais de recu non stocke
                                buffer = {}
                                break  # reconnect applique la liste reduite
                        elif over_windows == 1:
                            print(f"[klines-ws] debit {rate:.1f} msg/s > "
                                  f"{RATE_LIMIT_PER_S:.0f} (fenetre 1/"
                                  f"{DEMOTE_ARM_WINDOWS} — pic transitoire ?, "
                                  f"demotion armee)", flush=True)
                        last_check = now
                        counts = {}
                    if now - last_log >= LOG_INTERVAL_S:
                        print(f"[klines-ws] {n_frames / (now - last_log):.1f}"
                              f" frame/s | debit 10s "
                              f"{len(ts) / RATE_WINDOW_S:.1f}/s | "
                              f"{len(active)} symboles | {n_closed} fermes "
                              f"/ {n_stored} ecrits (60 s)", flush=True)
                        n_frames = n_closed = n_stored = 0
                        last_log = now
                    if now > conn_deadline:
                        store(buffer)
                        print("[klines-ws] reconnexion programmee 23 h",
                              flush=True)
                        break
                    if deadline_test and now > deadline_test:
                        store(buffer)
                        print(f"[klines-ws] fenetre de test : {n_stored} "
                              f"bougies ecrites, {len(buffer)} en buffer",
                              flush=True)
                        return
                if deadline_test:
                    return  # break propre de la reconnexion 24 h en test
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[klines-ws] deconnexion : {type(exc).__name__} — "
                  f"reconnexion dans {backoff}s", flush=True)
            if deadline_test and time.time() > deadline_test - backoff:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


def main() -> int:
    ap = argparse.ArgumentParser(description="Collecteur klines WS Aster")
    ap.add_argument("--test", type=int, default=0, metavar="SECONDES",
                    help="ecoute limitee (debug) puis quitte")
    args = ap.parse_args()
    try:
        asyncio.run(listen(args.test or None))
    except KeyboardInterrupt:
        print("[klines-ws] arret manuel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
