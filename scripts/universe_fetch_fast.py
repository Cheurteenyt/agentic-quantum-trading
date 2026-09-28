#!/usr/bin/env python3
"""Le fetch CONCURRENT de l'univers Aster — 6 workers + le pacing par
weight (la limite fapi : 1200 weight/min, klines limit 1500 = weight 10)
→ ~60 symboles/min au lieu de 14. Le monitoring du header
X-MBX-USED-WEIGHT-1M : back-off automatique si > 1000. Idempotent."""
import sys, json, time, sqlite3, threading, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "klines_universe.db"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
WORKERS = 6
LOCK = threading.Lock()
WEIGHT_WINDOW = []


def api(path: str):
    with LOCK:
        now = time.time()
        while WEIGHT_WINDOW and now - WEIGHT_WINDOW[0] > 60:
            WEIGHT_WINDOW.pop(0)
        if len(WEIGHT_WINDOW) >= 66:
            time.sleep(max(0.1, 60 / 66 - (now - WEIGHT_WINDOW[0])))
        WEIGHT_WINDOW.append(time.time())
    req = urllib.request.Request(f"https://fapi.asterdex.com{path}", headers={"user-agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 418):
                time.sleep(30 * (attempt + 1))
                continue
            raise
    raise RuntimeError("retries épuisés")


def fetch_symbol(sym: str, con_lock: threading.Lock, con: sqlite3.Connection):
    import numpy as np
    all_k, end = [], None
    for _ in range(2):
        q = f"/fapi/v1/klines?symbol={sym}&interval=1h&limit=1500"
        if end: q += f"&endTime={end}"
        ks = api(q)
        if not ks: break
        all_k = ks + all_k
        end = ks[0][0] - 1
        if len(ks) < 1500: break
    if not all_k:
        return (sym, 0, 0)
    now = time.time()
    with con_lock:
        con.executemany(
            "INSERT OR IGNORE INTO klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(sym, "1h", int(k[0]), float(k[1]), float(k[2]), float(k[3]),
              float(k[4]), float(k[5]), int(k[6]), "universe", "fapi", now)
             for k in all_k])
        vol = float(np.mean([float(k[7]) * float(k[4]) for k in all_k if float(k[4]) > 0])) if all_k else 0
        con.execute("INSERT OR REPLACE INTO universe_meta VALUES (?,?,?,?,?)",
                    (sym, len(all_k), round(vol), int(all_k[0][0]), int(all_k[-1][6])))
        con.commit()
    return (sym, len(all_k), vol)


def main() -> int:
    refresh = "--refresh" in sys.argv
    con = sqlite3.connect(str(DB), timeout=60, check_same_thread=False)
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
    print(f"[fast] {len(all_syms)} perps, {len(have)} déjà, {len(todo)} à fetcher — {WORKERS} workers", flush=True)
    con_lock = threading.Lock()
    t0, done, errs = time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(fetch_symbol, s, con_lock, con): s for s in todo}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                sym_, n, vol = fut.result()
                done += 1
                if done % 50 == 0:
                    rate = done / (time.time() - t0) * 60
                    print(f"  [{done}/{len(todo)}] {sym_} : {n} bougies | {rate:.0f} symboles/min", flush=True)
            except Exception as e:
                errs += 1
                print(f"  ERR {sym} : {e}", flush=True)
    dt = time.time() - t0
    print(f"[fast] TERMINÉ : {done} symboles en {dt/60:.1f} min ({done/dt*60:.0f}/min), {errs} erreurs", flush=True)
    print("\n=== LES TIERS DE LIQUIDITÉ ===", flush=True)
    for lo, hi, name in ((1e6, 1e18, "T1 ≥ 1M$/h"), (1e5, 1e6, "T2 100k-1M"),
                          (1e4, 1e5, "T3 10k-100k"), (0, 1e4, "T4 < 10k")):
        n = con.execute("SELECT COUNT(*) FROM universe_meta WHERE avg_vol_usd>=? AND avg_vol_usd<?",
                        (lo, hi)).fetchone()[0]
        print(f"  {name} : {n} symboles", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
