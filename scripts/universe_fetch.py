#!/usr/bin/env python3
"""Le fetch de l'univers complet Aster (555+ symboles jamais testés) —
side-DB klines_universe.db, 1h × ~3000 bougies, le profil de liquidité
par tiers. Idempotent (les symboles présents skippés sauf --refresh)."""
import sys, json, time, sqlite3, urllib.request
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "klines_universe.db"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
SLEEP = 0.35


def api(path: str):
    req = urllib.request.Request(f"https://fapi.asterdex.com{path}", headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> int:
    refresh = "--refresh" in sys.argv
    con = sqlite3.connect(str(DB), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("""CREATE TABLE IF NOT EXISTS klines (
        symbol TEXT, interval TEXT, open_time INTEGER, open REAL, high REAL,
        low REAL, close REAL, volume REAL, close_time INTEGER,
        snapshot_id TEXT, source TEXT, fetched_at REAL,
        PRIMARY KEY (symbol, interval, open_time))""")
    con.execute("""CREATE TABLE IF NOT EXISTS universe_meta (
        symbol TEXT PRIMARY KEY, n_candles INTEGER, avg_vol_usd REAL,
        first_ts INTEGER, last_ts INTEGER)""")
    con.commit()

    info = api("/fapi/v1/exchangeInfo")
    all_syms = sorted(s["symbol"] for s in info["symbols"]
                      if s.get("quoteAsset") == "USDT"
                      and s.get("status", "TRADING") in ("TRADING", ""))
    have = {r[0] for r in con.execute("SELECT DISTINCT symbol FROM klines")}
    todo = [s for s in all_syms if refresh or s not in have]
    print(f"[univers] {len(all_syms)} perps USDT, {len(have)} déjà, {len(todo)} à fetcher", flush=True)

    t0 = time.time()
    done = 0
    for i, sym in enumerate(todo):
        try:
            all_k = []
            end = None
            for _ in range(2):
                q = f"/fapi/v1/klines?symbol={sym}&interval=1h&limit=1500"
                if end: q += f"&endTime={end}"
                ks = api(q)
                if not ks: break
                all_k = ks + all_k
                end = ks[0][0] - 1
                if len(ks) < 1500: break
                time.sleep(SLEEP)
            if not all_k: continue
            now = time.time()
            con.executemany(
                "INSERT OR IGNORE INTO klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(sym, "1h", int(k[0]), float(k[1]), float(k[2]), float(k[3]),
                  float(k[4]), float(k[5]), int(k[6]), "universe", "fapi", now)
                 for k in all_k])
            n = len(all_k)
            vol = np.mean([float(k[7]) * float(k[4]) for k in all_k if float(k[4]) > 0]) if all_k else 0
            con.execute("INSERT OR REPLACE INTO universe_meta VALUES (?,?,?,?,?)",
                        (sym, n, round(vol), int(all_k[0][0]), int(all_k[-1][6])))
            con.commit()
            done += 1
            if done % 50 == 0:
                print(f"  [{done}/{len(todo)}] {sym} : {n} bougies", flush=True)
        except Exception as e:
            print(f"  ERR {sym} : {e}", flush=True)
        time.sleep(SLEEP)
    print(f"[univers] TERMINÉ : {done} symboles en {(time.time()-t0)/60:.0f} min", flush=True)
    # les tiers
    print("\n=== LES TIERS DE LIQUIDITÉ ===", flush=True)
    for lo, hi, name in ((1e6, 1e18, "T1 ≥ 1M$/h"), (1e5, 1e6, "T2 100k-1M"),
                          (1e4, 1e5, "T3 10k-100k"), (0, 1e4, "T4 < 10k")):
        n = con.execute("SELECT COUNT(*) FROM universe_meta WHERE avg_vol_usd>=? AND avg_vol_usd<?",
                        (lo, hi)).fetchone()[0]
        print(f"  {name} : {n} symboles", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
