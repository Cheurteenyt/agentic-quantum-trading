#!/usr/bin/env python
"""LE COLLECTEUR OHLCV fomo — les bougies 1m des tokens, en temps réel.

Le protocole cracké le 26/09 : le WebSocket fomo.family streame des frames
`{"type":"ohlcv","period":"1m","asset":"<mint>","time":...,"open","high",
"low","close","volume"}` pour chaque token visible de l'app. L'app
s'abonne ELLE-MÊME aux tokens affichés — le collecteur capture simplement
ces frames et les stocke.

Chaque exécution collecte --minutes minutes de bougies 1m. Câblé au
nocturne (60 min/nuit), la série fomo_ohlcv construit la base de données
de prix IMPARTIALE qui rendra les backtests fomo possibles (l'UI n'expose
que les gains — nos séries sont la vérité).

  .venv/bin/python scripts/fomo_ohlcv_collector.py --minutes 60
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fomo_harvest import _connect_cdp  # noqa: E402

DB = ROOT / "data" / "fomo" / "fomo.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=60)
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_ohlcv (
        asset TEXT NOT NULL, period TEXT NOT NULL, time INTEGER NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume REAL,
        captured_at REAL NOT NULL,
        PRIMARY KEY (asset, period, time));
    """)
    con.commit()

    pw, browser = _connect_cdp()
    if browser is None:
        print("[ohlcv] le daemon fomo ne répond pas — collector avorté")
        con.close()
        return 1
    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        stored = 0
        assets = set()

        def store(asset: str, period: str, t: int, o, h, l, c, v):
            nonlocal stored
            con.execute(
                "INSERT OR IGNORE INTO fomo_ohlcv VALUES (?,?,?,?,?,?,?,?,?)",
                (asset, period, int(t), o, h, l, c, v, time.time()))
            stored += 1
            assets.add(asset[:12])

        def on_ws(ws):
            def on_frame(f):
                try:
                    payload = getattr(f, "payload", None)
                    if payload is None:
                        payload = str(f)
                    d = json.loads(payload) if isinstance(payload, str) else payload
                    if d.get("type") == "ohlcv":
                        store(d.get("asset", "?"), d.get("period", "?"),
                              d.get("time", 0), d.get("open"), d.get("high"),
                              d.get("low"), d.get("close"), d.get("volume"))
                except Exception:
                    pass
            ws.on("framereceived", on_frame)

        page.on("websocket", on_ws)
        page.goto("https://fomo.family", timeout=30000,
                  wait_until="domcontentloaded")
        time.sleep(10)
        # le flux ohlcv ne démarre que quand une vue TOKEN est ouverte :
        # cliquer le premier token visible de la liste (la sonde v3 l'a prouvé)
        try:
            page.mouse.wheel(0, 800)
            time.sleep(2)
            for b in page.query_selector_all("button, div[role], a")[:80]:
                t = (b.inner_text() or "").strip()
                if 3 < len(t) < 30 and "$" in t:
                    b.click(timeout=2000)
                    break
        except Exception:
            pass
        t0 = time.time()
        while time.time() - t0 < args.minutes * 60:
            time.sleep(10)
            con.commit()
            print(f"[ohlcv] {int(time.time()-t0)}s : {stored} bougies, "
                  f"{len(assets)} tokens", flush=True)
        con.commit()
        con.close()
        page.close()
        print(f"[ohlcv] terminé : {stored} bougies stockées, "
              f"{len(assets)} tokens")
        return 0
    finally:
        pw.stop()


if __name__ == "__main__":
    import json
    raise SystemExit(main())
