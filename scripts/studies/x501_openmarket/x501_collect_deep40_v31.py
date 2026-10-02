#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501 v31 — COLLECTE DEEP 40 SYMBOLES « depuis le début de l'actif » (docs/37).

Étend la base deep v29/v30 de 9 -> 40 perps Binance USDT-M (univers harnais v8)
avec le volume taker dès l'origine, via CDN Binance Vision (sans rate-limit),
compléments API fapi blindés (pacing 0,42 s, backoffs progressifs).

Passes :
  A  Bybit API  : 12 symboles -> bb_kline_1h_deep (backward, planchers floor_v29)
  B  Binance Vision : 40 symboles -> bn_kline_1h_deep (mois + daily récents)
       puis complément API fapi sur les trous internes > 2 h
  C  Funding Binance : 40 symboles -> bn_funding_deep (ts en SECONDES, piège
       d'unité documenté v29) via Vision mensuels puis API forward depuis listing
  QA contiguïté : gaps > 2 h klines, NULL taker, cohérence cross-venue overlap

Incrémental (INSERT OR IGNORE / UPDATE WHERE NULL) — relançable sans doublon.
Usage : python3 x501_collect_deep40_v31.py [--bybit] [--vision] [--funding] [--qa] [--all]
"""
import io, json, os, sqlite3, sys, time, zipfile, urllib.request, urllib.error
import urllib.parse, concurrent.futures as cf

os.chdir(os.environ.get("X501_EXT_ROOT", "/home/z/my-project"))
DB = "scripts/x501_v21_results/om_v27.db"
FLOOR = "scripts/x501_v21_results/floor_v29.json"
LOG = "scripts/x501_v21_results/collect_deep40_v31.json"

SYMS_40 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
           "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT", "DOTUSDT",
           "LTCUSDT", "TRXUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
           "ATOMUSDT", "ETCUSDT", "BCHUSDT", "FILUSDT", "UNIUSDT",
           "AAVEUSDT", "HBARUSDT", "VETUSDT", "ICPUSDT", "FETUSDT",
           "INJUSDT", "LDOUSDT", "GALAUSDT", "IMXUSDT", "STXUSDT",
           "WLDUSDT", "SEIUSDT", "SUIUSDT", "TIAUSDT", "1000PEPEUSDT",
           "1000SHIBUSDT", "1000FLOKIUSDT", "JUPUSDT", "ORDIUSDT"]
BN_DEEP9 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT",
            "DOGEUSDT", "SOLUSDT", "AVAXUSDT"]
HDR = {"User-Agent": "Mozilla/5.0"}
PAUSE_BN = 0.42
BN_BACKOFF = [20, 40, 60, 90, 120]
MONTH_START = (2019, 8)          # mois de départ du scan Vision (BTC listing 2019-09)
B1H = 3600 * 1000

log = {"bybit": {}, "vision": {}, "api_compl": {}, "api_back": {}, "funding": {}, "qa": {}}


def get_json(url, timeout=20):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_retry(url, n=4, timeout=20):
    for i in range(n):
        try:
            return get_json(url, timeout)
        except Exception:
            if i == n - 1:
                return None
            time.sleep(1.5 * (i + 1))


def months_list():
    out, (y, m) = [], MONTH_START
    now = time.gmtime()
    while (y, m) <= (now.tm_year, now.tm_mon):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


# ============================== A : BYBIT ====================================
def bybit_page(sym, end_ms, limit=1000):
    u = ("https://api.bybit.com/v5/market/kline?" + urllib.parse.urlencode(
        {"category": "linear", "symbol": sym, "interval": "60",
         "end": int(end_ms), "limit": limit}))
    j = get_retry(u)
    if not j or j.get("retCode") != 0:
        return None
    return j["result"]["list"]


def collect_bybit(db, sym, floor_ms):
    cur = db.cursor()
    lo = cur.execute("SELECT MIN(ts) FROM bb_kline_1h_deep WHERE symbol=?",
                     (sym,)).fetchone()[0]
    if lo is not None and lo <= floor_ms + 86_400_000:
        return 0
    end = (lo if lo is not None else int(time.time() * 1000)) - 1
    added, fails = 0, 0
    while end > floor_ms:
        page = bybit_page(sym, end)
        if not page:
            if fails >= 5:
                break
            time.sleep(20 + 20 * fails)   # backoff réseau/rate-limit
            fails += 1
            continue
        fails = 0
        rows = [(sym, int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                 float(r[4]), float(r[5])) for r in page]
        cur.executemany("INSERT OR IGNORE INTO bb_kline_1h_deep VALUES(?,?,?,?,?,?,?)", rows)
        db.commit()
        added += len(rows)
        end = min(int(r[0]) for r in page) - 1
        time.sleep(0.14)
        if len(page) < 1000:
            break
    return added


def pass_bybit(db, syms):
    F = json.load(open(FLOOR))
    for sym in [s for s in syms if F.get(s, {}).get("kline1h_bybit")]:
        fl = F[sym]["kline1h_bybit"]
        n = collect_bybit(db, sym, fl)
        tot = db.execute("SELECT COUNT(*), MIN(ts) FROM bb_kline_1h_deep WHERE symbol=?",
                         (sym,)).fetchone()
        log["bybit"][sym] = dict(added=n, total=tot[0])
        print(f"BB {sym:14s} +{n:6d} -> {tot[0]:6d} barres "
              f"(depuis {time.strftime('%Y-%m-%d', time.gmtime(tot[1]/1000))})", flush=True)


# ====================== B : BINANCE VISION KLINES ============================
def vision_kline_rows(data):
    zf = zipfile.ZipFile(io.BytesIO(data))
    raw = zf.read(zf.namelist()[0]).decode()
    rows = []
    for line in raw.strip().split("\n"):
        p = line.split(",")
        if not p[0].rstrip(".").isdigit():
            continue
        rows.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]),
                     float(p[4]), float(p[5]), float(p[9])))
    return rows


def vision_kline_month(sym, ym):
    url = (f"https://data.binance.vision/data/futures/um/monthly/klines/"
           f"{sym}/1h/{sym}-1h-{ym}.zip")
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=30) as r:
            return ym, vision_kline_rows(r.read()), None
    except urllib.error.HTTPError as e:
        return ym, [], (404 if e.code == 404 else f"HTTP {e.code}")
    except Exception as e:
        return ym, [], str(e)[:60]


def vision_kline_day(sym, ymd):
    url = (f"https://data.binance.vision/data/futures/um/daily/klines/"
           f"{sym}/1h/{sym}-1h-{ymd}.zip")
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=30) as r:
            return ymd, vision_kline_rows(r.read()), None
    except urllib.error.HTTPError as e:
        return ymd, [], (404 if e.code == 404 else f"HTTP {e.code}")
    except Exception as e:
        return ymd, [], str(e)[:60]


def pass_vision(db, syms):
    cur = db.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(bn_kline_1h_deep)")]
    if "taker_buy" not in cols:
        cur.execute("ALTER TABLE bn_kline_1h_deep ADD COLUMN taker_buy REAL")
        db.commit()
        print("colonne taker_buy ajoutée", flush=True)
    months = months_list()
    import datetime as dt
    d0 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45)
    days = [(d0 + dt.timedelta(days=k)).strftime("%Y-%m-%d") for k in range(46)]
    for sym in syms:
        t0 = time.time()
        ins = 0
        first_ok = None
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(vision_kline_month, sym, ym): ym for ym in months}
            for fu in cf.as_completed(futs):
                ym, rows, err = fu.result()
                if err or not rows:
                    continue
                if first_ok is None or ym < first_ok:
                    first_ok = ym
                cur.executemany(
                    "INSERT OR IGNORE INTO bn_kline_1h_deep"
                    "(symbol, ts, open, high, low, close, volume, taker_buy) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    [(sym, *r) for r in rows])
                ins += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        db.commit()
        # complément daily Vision sur 46 derniers jours (mois courant sans zip)
        insd = 0
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(vision_kline_day, sym, ymd): ymd for ymd in days}
            for fu in cf.as_completed(futs):
                ymd, rows, err = fu.result()
                if err or not rows:
                    continue
                cur.executemany(
                    "INSERT OR IGNORE INTO bn_kline_1h_deep"
                    "(symbol, ts, open, high, low, close, volume, taker_buy) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    [(sym, *r) for r in rows])
                insd += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        db.commit()
        tot = cur.execute("SELECT COUNT(*), MIN(ts) FROM bn_kline_1h_deep WHERE symbol=?",
                          (sym,)).fetchone()
        log["vision"][sym] = dict(mois_zip=ins, mois_daily=insd, total=tot[0],
                                  premier_mois=first_ok,
                                  sec=round(time.time() - t0, 1))
        print(f"BN {sym:14s} zip+{ins:6d} daily+{insd:5d} -> {tot[0]:6d} "
              f"barres (1er mois {first_ok}, {time.time()-t0:.0f} s)", flush=True)


def pass_api_back(db, syms):
    """Backward API depuis MIN(ts) vers le plancher de listing (les mois
    antérieurs au premier zip Vision, ex. BTC 2019-09-08 -> 2019-12-31)."""
    cur = db.cursor()
    F = json.load(open(FLOOR))
    for sym in syms:
        fl = F.get(sym, {}).get("kline1h_binance")
        if not fl:
            continue
        lo = cur.execute("SELECT MIN(ts) FROM bn_kline_1h_deep WHERE symbol=?",
                         (sym,)).fetchone()[0]
        if lo is None or lo <= fl + 86_400_000:
            continue
        added, fails, end = 0, 0, lo - 1
        while end > fl:
            page = bn_api_page_full(sym, end)
            if page is None:
                if fails >= len(BN_BACKOFF):
                    break
                wait = BN_BACKOFF[fails]
                print(f"  back {sym}: pause {wait} s", flush=True)
                time.sleep(wait)
                fails += 1
                continue
            fails = 0
            rows = [(sym, int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                     float(r[4]), float(r[5]), float(r[9])) for r in page]
            cur.executemany(
                "INSERT OR IGNORE INTO bn_kline_1h_deep"
                "(symbol, ts, open, high, low, close, volume, taker_buy) "
                "VALUES(?,?,?,?,?,?,?,?)", rows)
            db.commit()
            added += len(rows)
            end = min(int(r[0]) for r in page) - 1
            time.sleep(PAUSE_BN)
            if len(page) < 1500:
                break
        lo2 = cur.execute("SELECT MIN(ts) FROM bn_kline_1h_deep WHERE symbol=?",
                          (sym,)).fetchone()[0]
        log["api_back"][sym] = dict(added=added, min_ts=lo2)
        print(f"BACK {sym:14s} +{added:6d} -> min "
              f"{time.strftime('%Y-%m-%d', time.gmtime(lo2/1000))} "
              f"(plancher {time.strftime('%Y-%m-%d', time.gmtime(fl/1000))})", flush=True)


def bn_api_page_full(sym, end_ms, limit=1500, fails=0):
    u = ("https://fapi.binance.com/fapi/v1/klines?" + urllib.parse.urlencode(
        {"symbol": sym, "interval": "1h", "endTime": int(end_ms), "limit": limit}))
    while True:
        try:
            req = urllib.request.Request(u, headers=HDR)
            j = json.loads(urllib.request.urlopen(req, timeout=20).read())
            return j if isinstance(j, list) else None
        except Exception:
            if fails >= len(BN_BACKOFF):
                return None
            time.sleep(BN_BACKOFF[fails])
            fails += 1


# ==================== B2 : COMPLÉMENT API SUR TROUS ==========================
def bn_api_page(sym, start_ms, end_ms, fails=0):
    u = ("https://fapi.binance.com/fapi/v1/klines?" + urllib.parse.urlencode(
        {"symbol": sym, "interval": "1h", "startTime": int(start_ms),
         "endTime": int(end_ms), "limit": 1000}))
    while True:
        try:
            req = urllib.request.Request(u, headers=HDR)
            j = json.loads(urllib.request.urlopen(req, timeout=20).read())
            return j if isinstance(j, list) else None
        except Exception:
            if fails >= len(BN_BACKOFF):
                return None
            wait = BN_BACKOFF[fails]
            print(f"  API {sym}: pause {wait} s", flush=True)
            time.sleep(wait)
            fails += 1


def pass_api_gaps(db, syms):
    cur = db.cursor()
    for sym in syms:
        ts = [r[0] for r in cur.execute(
            "SELECT ts FROM bn_kline_1h_deep WHERE symbol=? ORDER BY ts", (sym,))]
        if len(ts) < 2:
            continue
        gaps = [(a, b) for a, b in zip(ts, ts[1:]) if b - a > 2 * B1H]
        if not gaps:
            log["api_compl"][sym] = dict(trous=0)
            continue
        fixed = 0
        for a, b in gaps:
            page = bn_api_page(sym, a + 1, b - 1)
            time.sleep(PAUSE_BN)
            if not page:
                continue
            rows = [(sym, int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                     float(r[4]), float(r[5]), float(r[9])) for r in page]
            cur.executemany(
                "INSERT OR IGNORE INTO bn_kline_1h_deep"
                "(symbol, ts, open, high, low, close, volume, taker_buy) "
                "VALUES(?,?,?,?,?,?,?,?)", rows)
            db.commit()
            fixed += len(rows)
        log["api_compl"][sym] = dict(trous=len(gaps), comble=fixed)
        print(f"API {sym:14s} trous={len(gaps):4d} comblés={fixed:6d}", flush=True)


# ============================ C : FUNDING ====================================
def vision_funding_rows(data):
    zf = zipfile.ZipFile(io.BytesIO(data))
    raw = zf.read(zf.namelist()[0]).decode()
    rows = []
    for line in raw.strip().split("\n"):
        p = line.split(",")
        if not p[0].rstrip(".").isdigit():
            continue
        rows.append((int(p[0]), float(p[2])))   # calc_time (ms), last_funding_rate
    return rows


def vision_funding_month(sym, ym):
    url = (f"https://data.binance.vision/data/futures/um/monthly/fundingRate/"
           f"{sym}/{sym}-fundingRate-{ym}.zip")
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=30) as r:
            return ym, vision_funding_rows(r.read()), None
    except urllib.error.HTTPError as e:
        return ym, [], (404 if e.code == 404 else f"HTTP {e.code}")
    except Exception as e:
        return ym, [], str(e)[:60]


def bn_funding_page(sym, start_ms, fails=0):
    u = ("https://fapi.binance.com/fapi/v1/fundingRate?" + urllib.parse.urlencode(
        {"symbol": sym, "startTime": int(start_ms), "limit": 1000}))
    while True:
        try:
            req = urllib.request.Request(u, headers=HDR)
            return json.loads(urllib.request.urlopen(req, timeout=20).read())
        except Exception:
            if fails >= len(BN_BACKOFF):
                return None
            wait = BN_BACKOFF[fails]
            print(f"  FUND {sym}: pause {wait} s", flush=True)
            time.sleep(wait)
            fails += 1


def pass_funding(db, syms):
    cur = db.cursor()
    F = json.load(open(FLOOR))
    months = months_list()
    for sym in syms:
        t0 = time.time()
        # plancher = min(funding_binance connu, premier mois zip - 1 mois de marge)
        fl = F.get(sym, {}).get("funding_binance")
        fl = (fl or 0) // 1000        # secondes
        # Vision d'abord (mensuels)
        ins = 0
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(vision_funding_month, sym, ym): ym for ym in months}
            for fu in cf.as_completed(futs):
                ym, rows, err = fu.result()
                if err or not rows:
                    continue
                cur.executemany(
                    "INSERT OR IGNORE INTO bn_funding_deep(symbol, ts, rate) VALUES(?,?,?)",
                    [(sym, ts_ms // 1000, rate) for ts_ms, rate in rows])
                ins += len(rows)
        db.commit()
        # API forward depuis le plancher (complète les trous Vision + les plages sans zip)
        lo_s = cur.execute("SELECT MIN(ts) FROM bn_funding_deep WHERE symbol=?",
                           (sym,)).fetchone()[0]
        ins_api = 0
        if lo_s is not None:
            start_s = min(lo_s, fl) - 86400 if fl else lo_s - 86400
            if fl and start_s > fl:
                start_s = fl
            cursor_s = max(start_s, 0)
            while True:
                page = bn_funding_page(sym, cursor_s * 1000)
                time.sleep(PAUSE_BN)
                if not page:
                    break
                rows = [(r["symbol"], int(r["fundingTime"]) // 1000,
                         float(r["fundingRate"])) for r in page]
                cur.executemany(
                    "INSERT OR IGNORE INTO bn_funding_deep(symbol, ts, rate) VALUES(?,?,?)",
                    rows)
                db.commit()
                ins_api += len(rows)
                hi = max(int(r["fundingTime"]) // 1000 for r in page)
                if len(page) < 1000:
                    break
                cursor_s = hi + 1
        tot = cur.execute("SELECT COUNT(*), MIN(ts) FROM bn_funding_deep WHERE symbol=?",
                          (sym,)).fetchone()
        log["funding"][sym] = dict(vision=ins, api=ins_api, total=tot[0],
                                   sec=round(time.time() - t0, 1))
        print(f"FR {sym:14s} vis+{ins:5d} api+{ins_api:5d} -> {tot[0]:5d} "
              f"(depuis {time.strftime('%Y-%m-%d', time.gmtime(tot[1]))} "
              f"ts=s, {time.time()-t0:.0f} s)", flush=True)


# ================================ QA =========================================
def pass_qa(db):
    cur = db.cursor()
    cur2 = db.cursor()          # curseur séparé : l'itération externe ne doit
                                # jamais être réinitialisée par les requêtes internes
    qa = {"klines": {}, "funding": {}}
    # klines : gaps > 2 h + NULL taker
    for tab, pref in (("bn_kline_1h_deep", "bn"), ("bb_kline_1h_deep", "bb")):
        qa["klines"][pref] = {}
        syms = [r[0] for r in cur2.execute(
            f"SELECT DISTINCT symbol FROM {tab} ORDER BY symbol")]
        for sym in syms:
            ts = [r[0] for r in cur.execute(
                f"SELECT ts FROM {tab} WHERE symbol=? ORDER BY ts", (sym,))]
            n = len(ts)
            mx = max((b - a for a, b in zip(ts, ts[1:])), default=0)
            nulls = 0
            if pref == "bn":
                nulls = cur.execute(
                    f"SELECT COUNT(*) FROM {tab} WHERE symbol=? AND taker_buy IS NULL",
                    (sym,)).fetchone()[0]
            qa["klines"][pref][sym] = dict(
                n=n, gap_max_h=round(mx / B1H, 2), nulls_taker=nulls)
    # funding : gaps > 8 h + 120 s
    fsyms = [r[0] for r in cur2.execute(
        "SELECT DISTINCT symbol FROM bn_funding_deep ORDER BY symbol")]
    for sym in fsyms:
        ts = [r[0] for r in cur.execute(
            "SELECT ts FROM bn_funding_deep WHERE symbol=? ORDER BY ts", (sym,))]
        mx = max((b - a for a, b in zip(ts, ts[1:])), default=0)
        qa["funding"][sym] = dict(n=len(ts), gap_max_s=mx)
    # cross-venue : overlap Bybit/Binance 9 symboles
    cross = {}
    for sym in BN_DEEP9:
        rows = cur.execute(
            "SELECT a.ts, a.close, b.close FROM bb_kline_1h_deep a "
            "JOIN bn_kline_1h_deep b ON a.ts=b.ts WHERE a.symbol=? AND b.symbol=?",
            (sym, sym)).fetchall()
        if rows:
            devs = sorted(abs(c1 - c2) / c1 * 1e4 for _, c1, c2 in rows)
            cross[sym] = dict(n=len(rows), med=round(devs[len(devs)//2], 1),
                              p99=round(devs[int(0.99*len(devs))], 1))
    qa["cross_venue"] = cross
    log["qa"] = qa
    # impression condensée
    bad = []
    for pref in ("bn", "bb"):
        for sym, d in qa["klines"][pref].items():
            if d["gap_max_h"] > 2.02 or d["nulls_taker"]:
                bad.append((pref, sym, d))
    print(f"QA klines: {len(qa['klines']['bn'])} bn / {len(qa['klines']['bb'])} bb, "
          f"ANOMALIES={len(bad)}", flush=True)
    for b in bad:
        print("  ANOMALIE", b, flush=True)
    if cross:
        meds = sorted(v["med"] for v in cross.values())
        print(f"QA cross-venue: médiane {meds[len(meds)//2]} bps "
              f"(max med {meds[-1]})", flush=True)


# ================================ MAIN =======================================
def main():
    args = set(sys.argv[1:])
    do_all = "--all" in args
    # --syms "A,B,C" : sous-ensemble (fractionnement des passes longues)
    syms_sel = SYMS_40
    for a in args:
        if a.startswith("--syms="):
            syms_sel = [s.strip() for s in a.split("=", 1)[1].split(",") if s.strip()]
    db = sqlite3.connect(DB, timeout=60)
    cur = db.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS bb_kline_1h_deep (
        symbol TEXT NOT NULL, ts INTEGER NOT NULL, open REAL, high REAL, low REAL,
        close REAL, volume REAL, UNIQUE(symbol, ts))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bn_kline_1h_deep (
        symbol TEXT NOT NULL, ts INTEGER NOT NULL, open REAL, high REAL, low REAL,
        close REAL, volume REAL, UNIQUE(symbol, ts))""")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_bn_fund ON bn_funding_deep(symbol, ts)")
    db.commit()
    t0 = time.time()
    if do_all or "--bybit" in args:
        pass_bybit(db, syms_sel)
    if do_all or "--vision" in args:
        pass_vision(db, syms_sel)
    if do_all or "--api" in args:
        pass_api_gaps(db, syms_sel)
    if do_all or "--api-back" in args:
        pass_api_back(db, syms_sel)
    if do_all or "--funding" in args:
        pass_funding(db, syms_sel)
    if do_all or "--qa" in args:
        pass_qa(db)
    db.execute("INSERT INTO run_log(ts, symbol, layer, rows, note) VALUES(?,?,?,?,?)",
               (int(time.time()), "POOL", "collect_deep40_v31", 0,
                json.dumps({k: (sum(v.values()) if isinstance(v, dict) and
                                all(isinstance(x, (int, float)) for x in v.values()) else "ok")
                            for k, v in log.items()})))
    db.commit()
    json.dump(log, open(LOG, "w"), indent=1)
    print(f"OK {time.time()-t0:.0f} s -> {LOG}", flush=True)


if __name__ == "__main__":
    main()
