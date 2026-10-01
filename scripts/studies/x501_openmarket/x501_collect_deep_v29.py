#!/usr/bin/env python3
"""x501 — COLLECTE DEEP v29 : extension klines 1h vers les planchers de listing.
Objectif: backtest 6 ans (9 symboles « anciens » via Binance) + fenêtre commune
3,42 ans (pool 12 via Bybit) + funding Binance topup vers plancher.

Tables (om_v27.db):
  bb_kline_1h_deep (symbol TEXT, ts INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL, UNIQUE(symbol,ts))
  bn_kline_1h_deep (idem)
  bn_funding_deep  (existe déjà — topup: symbol, ts, fundingRate, UNIQUE(symbol,ts) si déjà indexée)
Incrémental: INSERT OR IGNORE, reprise sans doublon. run_log.
"""
import sqlite3, json, time, datetime as dt, urllib.request, urllib.parse, sys, os

DB = "scripts/x501_v21_results/om_v27.db"
HDR = {"User-Agent": "Mozilla/5.0"}
PAUSE = 0.14
PAUSE_BN = 0.42      # Binance: weight 10/page -> ~140 req/min < budget 2400 w/min
BN_BACKOFF = [20, 40, 60, 90, 120]  # attentes sur 429/418
DAY_MS = 86_400_000
NOW_MS = int(time.time() * 1000)
LOG = "scripts/x501_v21_results/collect_deep_v29.json"

SYM12 = ["1000PEPEUSDT", "ADAUSDT", "APTUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT",
         "DOGEUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT"]
BN_DEEP = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT",
           "DOGEUSDT", "SOLUSDT", "AVAXUSDT"]  # les 9 « anciens »

FLOOR = json.load(open("scripts/x501_v21_results/floor_v29.json"))

def get(url, timeout=15):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def get_retry(url, n=4):
    for i in range(n):
        try:
            return get(url)
        except Exception:
            if i == n - 1:
                return None
            time.sleep(1.5 * (i + 1))

def ensure_schema(db):
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS bb_kline_1h_deep (
        symbol TEXT NOT NULL, ts INTEGER NOT NULL, open REAL, high REAL, low REAL,
        close REAL, volume REAL, UNIQUE(symbol, ts))""")
    c.execute("""CREATE TABLE IF NOT EXISTS bn_kline_1h_deep (
        symbol TEXT NOT NULL, ts INTEGER NOT NULL, open REAL, high REAL, low REAL,
        close REAL, volume REAL, UNIQUE(symbol, ts))""")
    # funding: garantir UNIQUE pour reprise
    try:
        c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_bn_fund ON bn_funding_deep(symbol, ts)""")
    except Exception as e:
        print("funding index:", e)
    db.commit()

def bybit_page(sym, end_ms, limit=1000):
    u = ("https://api.bybit.com/v5/market/kline?" + urllib.parse.urlencode(
        {"category": "linear", "symbol": sym, "interval": "60",
         "end": int(end_ms), "limit": limit}))
    j = get_retry(u)
    if not j or j.get("retCode") != 0:
        return None
    return j["result"]["list"]  # reverse-chrono

def bn_page(sym, end_ms, limit=1500):
    u = ("https://fapi.binance.com/fapi/v1/klines?" + urllib.parse.urlencode(
        {"symbol": sym, "interval": "1h", "endTime": int(end_ms), "limit": limit}))
    j = get_retry(u)
    return j if isinstance(j, list) else None

def collect_bybit(db, sym, floor_ms):
    """Pages backward jusqu'au plancher. Retour nb lignes ajoutées."""
    cur = db.cursor()
    have_lo = cur.execute("SELECT MIN(ts) FROM bb_kline_1h_deep WHERE symbol=?", (sym,)).fetchone()[0]
    if have_lo is not None and have_lo <= floor_ms + DAY_MS:
        return 0  # déjà complet
    start_from = have_lo if have_lo is not None else NOW_MS
    added, end = 0, start_from - 1
    while end > floor_ms:
        page = bybit_page(sym, end)
        if not page:
            break
        rows = [(sym, int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                 float(r[4]), float(r[5])) for r in page]
        cur.executemany("INSERT OR IGNORE INTO bb_kline_1h_deep VALUES(?,?,?,?,?,?,?)", rows)
        db.commit()
        added += len(rows)
        end = min(int(r[0]) for r in page) - 1
        time.sleep(PAUSE)
        if len(page) < 1000:
            break
    return added

def collect_binance(db, sym, floor_ms):
    cur = db.cursor()
    have_lo = cur.execute("SELECT MIN(ts) FROM bn_kline_1h_deep WHERE symbol=?", (sym,)).fetchone()[0]
    if have_lo is not None and have_lo <= floor_ms + DAY_MS:
        return 0
    start_from = have_lo if have_lo is not None else NOW_MS
    added, end = 0, start_from - 1
    fails = 0
    while end > floor_ms:
        page = bn_page(sym, end)
        if page is None:  # rate-limit / réseau -> backoff et reprise MÊME fenêtre
            if fails >= len(BN_BACKOFF):
                print(f"  {sym}: abandon après {len(BN_BACKOFF)} backoffs", flush=True)
                break
            wait = BN_BACKOFF[fails]
            print(f"  {sym}: pause {wait}s (end={end})", flush=True)
            time.sleep(wait)
            fails += 1
            continue
        fails = 0
        rows = [(sym, int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                 float(r[4]), float(r[5])) for r in page]
        cur.executemany("INSERT OR IGNORE INTO bn_kline_1h_deep VALUES(?,?,?,?,?,?,?)", rows)
        db.commit()
        added += len(rows)
        end = min(int(r[0]) for r in page) - 1
        time.sleep(PAUSE_BN)
        if len(page) < 1500:
            break
    return added

def bn_funding_page(sym, start_ms, limit=1000):
    u = ("https://fapi.binance.com/fapi/v1/fundingRate?" + urllib.parse.urlencode(
        {"symbol": sym, "startTime": int(start_ms), "limit": limit}))
    j = get_retry(u)
    return j if isinstance(j, list) else None

def topup_funding(db, sym, floor_ms):
    """Complète bn_funding_deep vers le plancher + répare les coutures (TS EN SECONDES)."""
    cur = db.cursor()
    ts_all = [r[0] for r in cur.execute(
        "SELECT ts FROM bn_funding_deep WHERE symbol=? ORDER BY ts", (sym,))]
    if not ts_all:
        return 0
    have_lo = ts_all[0]
    floor_s = floor_ms // 1000
    added = 0
    # (a) extension vers le plancher
    if have_lo > floor_s + 2 * 86_400:
        start = floor_s
        ceiling = have_lo
        while start < ceiling:
            page = bn_funding_page(sym, start * 1000)
            if page is None:
                time.sleep(45)
                page = bn_funding_page(sym, start * 1000)
                if page is None:
                    break
            rows = [(r["symbol"], int(r["fundingTime"]) // 1000, float(r["fundingRate"])) for r in page]
            cur.executemany("INSERT OR IGNORE INTO bn_funding_deep(symbol, ts, rate) VALUES(?,?,?)", rows)
            db.commit()
            added += len(rows)
            hi = max(int(r["fundingTime"]) // 1000 for r in page)
            if len(page) < 1000:
                break
            start = hi + 1
            time.sleep(PAUSE_BN)
    # (b) réparation des coutures: tout trou > 8 h + marge dans [min, max]
    ts_all = [r[0] for r in cur.execute(
        "SELECT ts FROM bn_funding_deep WHERE symbol=? ORDER BY ts", (sym,))]
    gaps = 0
    for a, b in zip(ts_all, ts_all[1:]):
        if b - a > 28_800 + 120:
            page = bn_funding_page(sym, (a + 1) * 1000)
            if page:
                rows = [(r["symbol"], int(r["fundingTime"]) // 1000, float(r["fundingRate"]))
                        for r in page if int(r["fundingTime"]) // 1000 < b]
                cur.executemany("INSERT OR IGNORE INTO bn_funding_deep(symbol, ts, rate) VALUES(?,?,?)", rows)
                db.commit()
                gaps += len(rows)
            time.sleep(PAUSE_BN)
    return added + gaps

def main():
    db = sqlite3.connect(DB)
    ensure_schema(db)
    stats = {"bybit": {}, "binance": {}, "funding": {}}
    # ---- Bybit deep : 12 symboles jusqu'au plancher kline1h_bybit
    for sym in SYM12:
        fl = FLOOR[sym]["kline1h_bybit"]
        if not fl:
            continue
        n = collect_bybit(db, sym, fl)
        stats["bybit"][sym] = n
        tot = db.execute("SELECT COUNT(*), MIN(ts) FROM bb_kline_1h_deep WHERE symbol=?", (sym,)).fetchone()
        print(f"BB {sym:14s} +{n:6d} -> total {tot[0]:6d} depuis {dt.datetime.fromtimestamp(tot[1]/1000, dt.timezone.utc).strftime('%Y-%m-%d')}", flush=True)
    # ---- Binance deep : 9 symboles jusqu'au plancher kline1h_binance
    for sym in BN_DEEP:
        fl = FLOOR[sym]["kline1h_binance"]
        if not fl:
            continue
        n = collect_binance(db, sym, fl)
        stats["binance"][sym] = n
        tot = db.execute("SELECT COUNT(*), MIN(ts) FROM bn_kline_1h_deep WHERE symbol=?", (sym,)).fetchone()
        print(f"BN {sym:14s} +{n:6d} -> total {tot[0]:6d} depuis {dt.datetime.fromtimestamp(tot[1]/1000, dt.timezone.utc).strftime('%Y-%m-%d')}", flush=True)
    # ---- Funding topup : 9 symboles vers plancher funding_binance
    for sym in BN_DEEP:
        fl = FLOOR[sym]["funding_binance"]
        if not fl:
            continue
        n = topup_funding(db, sym, fl)
        stats["funding"][sym] = n
        tot = db.execute("SELECT COUNT(*), MIN(ts) FROM bn_funding_deep WHERE symbol=?", (sym,)).fetchone()
        print(f"FR {sym:14s} +{n:5d} -> total {tot[0]:5d} depuis {dt.datetime.fromtimestamp(tot[1], dt.timezone.utc).strftime('%Y-%m-%d')} (ts=s)", flush=True)
    # ---- run_log (schéma: ts INT, symbol TEXT, layer TEXT, rows INT, note TEXT)
    db.execute("INSERT INTO run_log(ts, symbol, layer, rows, note) VALUES(?,?,?,?,?)",
               (int(time.time()), "POOL", "collect_deep_v29",
                sum(stats["bybit"].values()) + sum(stats["binance"].values()) + sum(stats["funding"].values()),
                json.dumps({k: sum(v.values()) for k, v in stats.items()})))
    db.commit()
    json.dump(stats, open(LOG, "w"), indent=1)
    print("OK ->", LOG)

if __name__ == "__main__":
    main()
