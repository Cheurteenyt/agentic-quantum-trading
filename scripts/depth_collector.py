#!/usr/bin/env python
"""Capteur de profondeur Aster 24/7 — fondations de la heatmap maison.

MMT ne couvrira jamais Aster (docs/17-mmt-m5.md) : leur heatmap order-book
est donc reconstruite chez nous. Toutes les POLL_SEC secondes, on échantillonne
le carnet (500 niveaux) de chaque symbole, on agrège les quantités par bacs de
prix (~0.1 % du mid) et on stocke dans data/warehouse/depth.db.

Le rendu (heatmap temps × prix, PDF vectoriel) est fait par
scripts/depth_heatmap.py dans la campagne nocturne.

Service : systemd user `aster-depth-collector.service` (Restart=always).
Stdlib uniquement — même discipline que liq_collector.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import sys
import threading
import time
import urllib.request

import aster_rate  # le compteur X-MBX-USED-WEIGHT-1M (audit docs/24)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "depth.db"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "ASTERUSDT", "PONSUSDT", "CATEUSDT",
           "MEMEUSDT", "WIFUSDT", "TURBOUSDT", "BOMEUSDT", "MOODENGUSDT",
           "FARTCOINUSDT", "PNUTUSDT", "NEIROUSDT", "DOGSUSDT", "TRUMPUSDT"]
DEPTH_URL = "https://fapi.asterdex.com/fapi/v1/depth"
POLL_SEC = 30
BIN_FRAC = 0.0001         # largeur de bac = 0.01 % du mid
RETENTION_DAYS = 30
STALL_LIMIT_SEC = 300     # 5 min sans write = stall (cadence normale ~30s ; pire
                          # cas réseau = 15 symboles x timeout 15s = 225s < 300)

_running = True
_last_progress = time.time()   # dernier write réussi OU prune finie (wall clock,
                               # volontairement : avance au réveil de suspend)
_in_prune = False

DEPTH_DDL = """
CREATE TABLE IF NOT EXISTS depth_bins (
    symbol    TEXT    NOT NULL,
    ts        INTEGER NOT NULL,
    side      TEXT    NOT NULL,
    bin_price REAL    NOT NULL,
    qty       REAL    NOT NULL,
    PRIMARY KEY (symbol, ts, side, bin_price)
);
CREATE TABLE IF NOT EXISTS depth_meta (
    symbol TEXT    NOT NULL,
    ts     INTEGER NOT NULL,
    mid    REAL    NOT NULL,
    PRIMARY KEY (symbol, ts)
);
"""

_running = True


def _stop(signum, frame):  # noqa: ARG001
    global _running
    _running = False


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30)
    con.executescript(DEPTH_DDL)
    return con


def bin_levels(levels: list[list[str]], grid: float) -> dict[float, float]:
    """Agrège [(prix, qty)...] dans des bacs centrés sur la grille."""
    bins: dict[float, float] = {}
    for price_s, qty_s in levels:
        price, qty = float(price_s), float(qty_s)
        if price <= 0 or qty <= 0:
            continue
        b = round(price / grid) * grid
        bins[b] = bins.get(b, 0.0) + qty
    return bins


def snapshot_symbol(con: sqlite3.Connection, symbol: str) -> bool:
    url = f"{DEPTH_URL}?symbol={symbol}&limit=500"
    req = urllib.request.Request(url, headers={"User-Agent": "trading-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            aster_rate.note_weight(getattr(resp, "headers", None), "depth_collector")
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001 — le capteur ne doit jamais mourir sur un tick
        print(f"[warn] {symbol}: {exc}", file=sys.stderr, flush=True)
        return False
    bids, asks = data.get("bids") or [], data.get("asks") or []
    if not bids or not asks:
        return False
    mid = (float(bids[0][0]) + float(asks[0][0])) / 2.0
    grid = mid * BIN_FRAC
    ts = int(time.time())
    rows = []
    for side, levels in (("bid", bids), ("ask", asks)):
        for b, qty in bin_levels(levels, grid).items():
            rows.append((symbol, ts, side, b, qty))
    con.executemany(
        "INSERT OR REPLACE INTO depth_bins (symbol, ts, side, bin_price, qty) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    con.execute("INSERT OR REPLACE INTO depth_meta (symbol, ts, mid) VALUES (?, ?, ?)", (symbol, ts, mid))
    con.commit()
    global _last_progress
    _last_progress = time.time()
    return True


def _stalled(now: float | None = None) -> bool:
    """True si aucune écriture réussie depuis STALL_LIMIT_SEC (hors prune)."""
    if _in_prune:
        return False
    now = time.time() if now is None else now
    return (now - _last_progress) > STALL_LIMIT_SEC


def _watchdog() -> None:
    """Chien de garde dans un thread : le process qui n'écrit plus doit EXIT.

    Couvre les modes d'échec silencieux que Restart=always ne voit jamais :
    - getaddrinfo pendant (la résolution DNS n'est PAS couverte par le
      timeout=15 d'urlopen, seul le socket l'est) ;
    - socket morte / réveil de suspend (S3) avec état stale ;
    - toute boucle vivante mais muette.
    os._exit(1) car sys.exit ne tuerait que ce thread ; Restart=always refait
    un process propre.
    """
    while _running:
        time.sleep(20)
        if _stalled():
            age = time.time() - _last_progress
            print(
                f"[watchdog] aucun write réussi depuis >{STALL_LIMIT_SEC}s "
                f"(dernier progrès il y a {age:.0f}s) -> exit(1), systemd relance",
                file=sys.stderr,
                flush=True,
            )
            os._exit(1)


def prune_old(con: sqlite3.Connection) -> int:
    global _in_prune, _last_progress
    _in_prune = True  # le DELETE + l'index scannent des millions de lignes : pas de kill
    try:
        # l'index ts : sans lui le DELETE quotidien = un scan complet qui
        # triplerait en semaines (54 M → 192 M lignes) — créé une fois (17 s),
        # no-op ensuite ; la page libérée par le DELETE est réutilisée : le
        # fichier plafonne sans VACUUM
        con.execute("CREATE INDEX IF NOT EXISTS idx_depth_bins_ts ON depth_bins(ts)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_depth_meta_ts ON depth_meta(ts)")
        cutoff = int(time.time()) - RETENTION_DAYS * 86400
        cur = con.execute("DELETE FROM depth_bins WHERE ts < ?", (cutoff,))
        con.execute("DELETE FROM depth_meta WHERE ts < ?", (cutoff,))
        con.commit()
    finally:
        _in_prune = False
        _last_progress = time.time()
    return cur.rowcount


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    con = connect()
    print(f"[depth-collector] démarré : {SYMBOLS} toutes les {POLL_SEC}s -> {DB_PATH}", flush=True)
    global _last_progress
    _last_progress = time.time()
    threading.Thread(target=_watchdog, name="watchdog", daemon=True).start()
    last_prune_day = -1
    while _running:
        started = time.time()
        for symbol in SYMBOLS:
            if not _running:
                break
            snapshot_symbol(con, symbol)
        day = int(started // 86400)
        if day != last_prune_day:
            removed = prune_old(con)
            last_prune_day = day
            if removed:
                print(f"[prune] {removed} lignes > {RETENTION_DAYS}j supprimées", flush=True)
        elapsed = time.time() - started
        rest = max(1.0, POLL_SEC - elapsed)
        # dormir par petites tranches pour réagir aux signaux d'arrêt
        for _ in range(int(rest * 4)):
            if not _running:
                break
            time.sleep(0.25)
    con.close()
    print("[depth-collector] arrêt propre", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
