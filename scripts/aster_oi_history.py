#!/usr/bin/env python
"""Historique d'Open Interest Aster — construit maison (endpoint inexistant).

Aster ne fournit PAS d'historique d'OI (/futures/data/* : 404) : ce script
le construit. Chaque invocation = un snapshot (OI + prix) de l'univers
suivi, stocké dans klines.db:oi_history. Le diff avec le snapshot
précédent donne la VÉLOCITÉ d'OI et les divergences prix/OI :

  OI↑ prix↑  = des positions fraîches poussent la hausse (tendance réelle)
  OI↑ prix↓  = des shorts s'empilent (carburant à squeeze)
  OI↓ prix↑  = short squeeze en cours (capitulation des vendeurs)
  OI↓ prix↓  = liquidation des longs / désengagement

Usage :
  .venv/bin/python scripts/aster_oi_history.py        # un snapshot
  .venv/bin/python scripts/aster_oi_history.py --top 8  # rapport des movers
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "warehouse" / "klines.db"
BASE = "https://fapi.asterdex.com"


def _get(path: str) -> dict | list:
    req = urllib.request.Request(BASE + path,
                                 headers={"User-Agent": "trading-agent/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def snapshot() -> list[dict]:
    from scripts.x_aster_pulse import _universe

    symbols = [t + "USDT" for t in _universe()]
    prices = {p["symbol"]: float(p["price"])
              for p in _get("/fapi/v1/ticker/price") if isinstance(p, dict)}
    out: list[dict] = []
    for sym in symbols:
        try:
            oi = _get(f"/fapi/v1/openInterest?symbol={sym}")
            out.append({"symbol": sym,
                        "oi": float(oi.get("openInterest", 0)),
                        "price": prices.get(sym)})
        except Exception as exc:  # noqa: BLE001 — un symbole mort ne bloque pas
            print(f"[oi] {sym}: {str(exc)[:50]}", file=sys.stderr)
        time.sleep(0.25)
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Snapshot OI Aster (historique maison)")
    ap.add_argument("--top", type=int, default=8,
                    help="affiche les N plus gros movers d'OI")
    args = ap.parse_args()

    rows = snapshot()
    if not rows:
        print("[oi] aucun snapshot", file=sys.stderr)
        return 1
    now = time.time()
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS oi_history (
        symbol TEXT NOT NULL, open_interest REAL, price REAL,
        captured_at REAL NOT NULL, PRIMARY KEY (symbol, captured_at))""")
    movers: list[dict] = []
    for r in rows:
        prev = con.execute(
            "SELECT open_interest, price FROM oi_history WHERE symbol = ? "
            "AND captured_at < ? ORDER BY captured_at DESC LIMIT 1",
            (r["symbol"], now)).fetchone()
        con.execute("INSERT OR IGNORE INTO oi_history VALUES (?,?,?,?)",
                    (r["symbol"], r["oi"], r["price"], now))
        if prev and prev[0]:
            d_oi = (r["oi"] - prev[0]) / prev[0] * 100
            d_px = ((r["price"] - prev[1]) / prev[1] * 100
                    if (r["price"] and prev[1]) else None)
            movers.append({"symbol": r["symbol"], "d_oi": d_oi, "d_px": d_px,
                           "oi": r["oi"], "price": r["price"]})
    con.commit()
    con.close()

    movers.sort(key=lambda m: -abs(m["d_oi"]))
    print(f"[oi] snapshot {len(rows)} symboles — {len(movers)} avec historique")
    for m in movers[:args.top]:
        dpx = f"{m['d_px']:+.2f} %" if m["d_px"] is not None else "?"
        flag = ""
        if m["d_px"] is not None:
            if m["d_oi"] > 0 and m["d_px"] > 0:
                flag = " ← hausse portée par des positions fraîches"
            elif m["d_oi"] > 0 and m["d_px"] <= 0:
                flag = " ← shorts s'empilent (carburant squeeze)"
            elif m["d_oi"] < 0 and m["d_px"] > 0:
                flag = " ← squeeze en cours (shorts capitulent)"
            elif m["d_oi"] < 0 and m["d_px"] <= 0:
                flag = " ← désengagement / longs capitulent"
        print(f"[oi]   {m['symbol']}: OI {m['d_oi']:+.2f} % "
              f"(={m['oi']:,.0f}), prix {dpx}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
