#!/usr/bin/env python
"""LE COLLECTEUR DE TICKS fomo 24/7 — toutes les prices, tous les tokens.

La découverte du protocole : le WS fomo streame le topic `prices` pour
CHAQUE token visible — {priceUsd, timestamp} par mint, en continu, tous
les tokens SIMULTANÉMENT. Ce collecteur :
  1. capte chaque tick → fomo_ticks (mint, ts, priceUsd)
  2. agrège les ticks en bougies 1m → fomo_ohlcv (o/h/l/c/volume par mint)
  3. tourne 24/7 en service systemd — la donnée fomo au niveau Aster

La couverture : tous les tokens affichés par l'app (les mints garantis
fomo-natifs — le flux vient de la plateforme elle-même).

  .venv/bin/python scripts/fomo_tick_collector.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fomo_harvest import _connect_cdp  # noqa: E402

DB = ROOT / "data" / "fomo" / "fomo.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_ticks (
        mint TEXT NOT NULL, ts_s INTEGER NOT NULL, priceUsd REAL NOT NULL,
        captured_at REAL NOT NULL,
        PRIMARY KEY (mint, ts_s));
    CREATE TABLE IF NOT EXISTS fomo_ohlcv (
        asset TEXT NOT NULL, period TEXT NOT NULL, time INTEGER NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume REAL,
        captured_at REAL NOT NULL,
        PRIMARY KEY (asset, period, time));
    """)
    con.commit()
    ticks: dict[str, list] = {}
    n_frames = [0]
    last_tick_ref = [time.time()]

    def on_frame(f, con=con):
        p = f.payload if hasattr(f, "payload") else str(f)
        try:
            j = json.loads(p)
            if j.get("type") == "data" and j.get("topicType") == "prices":
                mint = j.get("topicId", "").split(":")[0]
                pay = j.get("payload", {})
                px = pay.get("priceUsd")
                ts = pay.get("timestamp")
                if mint and px and ts:
                    con.execute(
                        "INSERT OR IGNORE INTO fomo_ticks VALUES (?,?,?,?)",
                        (mint, int(ts), float(px), time.time()))
                    ticks.setdefault(mint, []).append((int(ts), float(px)))
                    n_frames[0] += 1
                    last_tick_ref[0] = time.time()
        except Exception:
            pass

    pw, browser = _connect_cdp()
    if browser is None:
        print("[ticks] le daemon fomo ne répond pas")
        con.close()
        return 1
    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()

        def attach_all():
            n = 0
            for page in ctx.pages:
                def on_ws(ws):
                    ws.on("framereceived", on_frame)
                try:
                    page.on("websocket", on_ws)
                    n += 1
                except Exception:
                    pass
            return n
        n_listeners = attach_all()
        # le RELOAD : les sockets des pages existantes sont vieux — le reload
        # recrée les connexions WS APRÈS l'attachement des listeners
        for page in ctx.pages:
            try:
                page.reload(timeout=15000)
            except Exception:
                pass
        print(f"[ticks] listeners sur {n_listeners} pages + reload — la collecte démarre")

        # le WATCHDOG : si les ticks s'arrêtent 5 min → reload (les sockets meurent)
        last_tick_ts = time.time()
        last_agg = 0
        while True:
            time.sleep(30)
            if time.time() - last_tick_ref[0] > 300:
                print("[ticks] WATCHDOG : plus de ticks depuis 5 min — reload des pages",
                      flush=True)
                for page in ctx.pages:
                    try:
                        page.reload(timeout=15000)
                    except Exception:
                        pass
                last_tick_ts = time.time()
            try:
                con.commit()
                # l'agrégation 1m : les ticks → les bougies o/h/l/c
                now_s = int(time.time())
                for mint, tks in list(ticks.items()):
                    buckets: dict[int, list] = {}
                    for ts, px in tks:
                        b = ts // 60 * 60
                        buckets.setdefault(b, []).append(px)
                    for b, prices in buckets.items():
                        if b <= last_agg or len(prices) < 2:
                            continue
                        con.execute(
                            "INSERT OR REPLACE INTO fomo_ohlcv VALUES (?,?,?,?,?,?,?,?,?)",
                            (mint, "1m", b * 1000, prices[0], max(prices),
                             min(prices), prices[-1], len(prices), time.time()))
                    last_agg = now_s // 60 * 60
                con.commit()
                n_candles = con.execute(
                    "SELECT COUNT(*) FROM fomo_ohlcv WHERE period='1m'").fetchone()[0]
                n_mints = con.execute(
                    "SELECT COUNT(DISTINCT asset) FROM fomo_ohlcv WHERE period='1m'"
                ).fetchone()[0]
                print(f"[ticks] {n_frames[0]} ticks | {len(ticks)} mints en cours | "
                      f"{n_candles} bougies 1m, {n_mints} tokens", flush=True)
            except Exception as e:
                print(f"[ticks] erreur d'agrégation : {e}", flush=True)
    finally:
        pw.stop()
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
