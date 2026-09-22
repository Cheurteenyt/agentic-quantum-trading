#!/usr/bin/env python3
"""Capteur de liquidations Aster — flux WebSocket !forceOrder@arr.

Les cascades de liquidations sont un des rares phenomenes REELLEMENT
structurels des marches perps : elles indiquent ou se trouvent les stops,
et leurs extremes marquent des climats de panique. Ce capteur ecoute le
flux public read-only (compatible avec la politique du projet, voir
working-map legacy) et stocke chaque evenement dans le warehouse.

Aucun trade. Aucune decision. Juste la donnee qui s'accumule pour les
backtests futurs (la serie doit vivre des semaines avant d'etre exploitable).

    python scripts/liq_collector.py            # boucle infinie (systemd)
    python scripts/liq_collector.py --test 20  # ecoute 20 s et quitte
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
DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
WS_URL = "wss://fstream.asterdex.com/ws/!forceOrder@arr"

SCHEMA = """
CREATE TABLE IF NOT EXISTS liq_events (
    symbol     TEXT    NOT NULL,
    side       TEXT    NOT NULL,
    qty        REAL    NOT NULL,
    price      REAL    NOT NULL,
    event_time INTEGER NOT NULL,
    notional   REAL    NOT NULL,
    source     TEXT    NOT NULL,
    captured_at REAL   NOT NULL,
    PRIMARY KEY (symbol, side, event_time, price, qty)
);
"""


def _now_s() -> float:
    return time.time()


def _store(events: list[dict]) -> int:
    con = sqlite3.connect(str(DB_PATH))
    con.executescript(SCHEMA)
    n = 0
    for ev in events:
        try:
            order = ev.get("o", {})
            qty = float(order.get("q", 0) or 0)
            price = float(order.get("ap", 0) or order.get("p", 0) or 0)
            if qty <= 0 or price <= 0:
                continue
            con.execute(
                "INSERT OR IGNORE INTO liq_events VALUES (?,?,?,?,?,?,?,?)",
                (
                    order.get("s", "?"), order.get("S", "?"), qty, price,
                    int(order.get("T", 0)), qty * price, "ws_forceOrder",
                    _now_s(),
                ),
            )
            n += 1
        except (KeyError, ValueError):
            continue
    con.commit()
    con.close()
    return n


async def listen(duration_s: float | None = None) -> None:
    import websockets

    deadline = time.time() + duration_s if duration_s else None
    backoff = 2
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20) as ws:
                print(f"[liq] connecte : {WS_URL}", flush=True)
                backoff = 2
                buffer: list[dict] = []
                last_flush = time.time()
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        ev = msg.get("data") or msg
                        if ev.get("e") == "forceOrder":
                            buffer.append(ev)
                    except (ValueError, TypeError):
                        continue
                    if time.time() - last_flush >= 5 and buffer:
                        n = _store(buffer)
                        buffer = []
                        last_flush = time.time()
                        if n:
                            print(f"[liq] {n} evenements stockes", flush=True)
                    if deadline and time.time() > deadline:
                        if buffer:
                            _store(buffer)
                        print("[liq] fin de la fenetre de test", flush=True)
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[liq] deconnexion : {type(exc).__name__} — reconnexion"
                  f" dans {backoff}s", flush=True)
            if deadline and time.time() > deadline - backoff:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


def main() -> int:
    ap = argparse.ArgumentParser(description="Capteur de liquidations Aster")
    ap.add_argument("--test", type=int, default=0, metavar="SECONDES",
                    help="ecoute limitee (debug) puis quitte")
    args = ap.parse_args()
    try:
        asyncio.run(listen(args.test or None))
    except KeyboardInterrupt:
        print("[liq] arret manuel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
