#!/usr/bin/env python3
"""Le collecteur premiumIndex (28/09) — la couche funding-forecast :
mark vs index (la prime), le taux courant, le next funding time.
La prime extrême = la foule surpaye (contrarian) ; la trajectoire de la
prime = la PRÉVISION du prochain funding 8h à l'avance."""
import sys, json, time, sqlite3, urllib.request
from pathlib import Path

import aster_rate  # le compteur X-MBX-USED-WEIGHT-1M (audit docs/24)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.portfolio_sim import MAJORS

DB = ROOT / "data" / "warehouse" / "klines.db"
SYMS = MAJORS + ["NEIROUSDT", "1000PEPEUSDT", "DOGSUSDT", "TRUMPUSDT",
                 "FARTCOINUSDT", "PNUTUSDT", "MOODENGUSDT", "DRAMUSDT",
                 "PIEVERSEUSDT", "VIRTUALUSDT", "MELANIAUSDT", "ASTERUSDT"]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def main() -> int:
    con = sqlite3.connect(str(DB), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("""CREATE TABLE IF NOT EXISTS premium_history (
        symbol TEXT, mark_price REAL, index_price REAL, premium_pct REAL,
        last_funding_rate REAL, next_funding_time_ms INTEGER,
        captured_at_ms INTEGER, PRIMARY KEY (symbol, captured_at_ms))""")
    n_ok, n_err = 0, 0
    now_ms = int(time.time() * 1000)
    for sym in SYMS:
        try:
            req = urllib.request.Request(
                f"https://fapi.asterdex.com/fapi/v1/premiumIndex?symbol={sym}",
                headers={"user-agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                aster_rate.note_weight(getattr(r, "headers", None), "aster_premium")
                d = json.load(r)
            mark, idx = float(d["markPrice"]), float(d["indexPrice"])
            prem = (mark / idx - 1) * 100 if idx else 0.0
            con.execute("INSERT OR IGNORE INTO premium_history VALUES (?,?,?,?,?,?,?)",
                        (sym, mark, idx, round(prem, 6),
                         float(d["lastFundingRate"]),
                         int(d["nextFundingTime"]), now_ms))
            con.commit()
            n_ok += 1
        except Exception as e:
            n_err += 1
            print(f"  ERR {sym} : {e}")
            continue
    # le top des primes (la foule surpaye = contrarian)
    hot = con.execute("""SELECT symbol, premium_pct FROM premium_history
                         WHERE captured_at_ms=? ORDER BY ABS(premium_pct) DESC LIMIT 5""",
                      (now_ms,)).fetchall()
    print(f"[premium] {n_ok} OK / {n_err} err | primes extrêmes : " +
          ", ".join(f"{s} {p:+.3f} %" for s, p in hot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
