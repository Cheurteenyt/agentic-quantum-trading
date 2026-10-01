#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501 v30 — TOPUP VOLUME TAKER via Binance VISION (CDN officiel, sans rate-limit).

Remplace la variante API (throttlée ~11 s/page par Binance après nos 429/418).
data.binance.vision publie les mêmes klines fapi en zips mensuels ; colonne 9
= taker_buy_base_volume. On télécharge, on met à jour bn_kline_1h_deep.taker_buy
par mois, on vérifie. Reprise : les mois déjà complets (aucun NULL sur leur
plage) sont sautés.

Colonnes futures/um klines : open_time, open, high, low, close, volume,
close_time, quote_volume, count, taker_buy_base, taker_buy_quote, ignore.
"""
import io, json, os, sqlite3, time, urllib.request, zipfile, concurrent.futures as cf

os.chdir(os.environ.get("X501_EXT_ROOT", "/home/z/my-project"))  # data deep locale, hors git (docs/26/37)
DB = "scripts/x501_v21_results/om_v27.db"
LOG = "scripts/x501_v21_results/topup_tb_vision_v30.json"
FLOOR = json.load(open("scripts/x501_v21_results/floor_v29.json"))
SYMS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "BNBUSDT",
        "ADAUSDT", "DOGEUSDT", "SOLUSDT", "AVAXUSDT"]
NOW_MS = int(time.time() * 1000)
HDR = {"User-Agent": "Mozilla/5.0"}


def months_between(floor_ms, now_ms):
    d = time.gmtime(floor_ms / 1000)
    y, m = d.tm_year, d.tm_mon
    out = []
    while (y, m) <= (time.gmtime(now_ms / 1000).tm_year, time.gmtime(now_ms / 1000).tm_mon):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def fetch_month(sym, ym):
    url = (f"https://data.binance.vision/data/futures/um/monthly/klines/"
           f"{sym}/1h/{sym}-1h-{ym}.zip")
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        zf = zipfile.ZipFile(io.BytesIO(data))
        name = zf.namelist()[0]
        raw = zf.read(name).decode()
        rows = []
        for line in raw.strip().split("\n"):
            p = line.split(",")
            if not p[0].rstrip(".").isdigit():     # ligne d'en-tête éventuelle
                continue
            rows.append((int(p[0]), float(p[9])))
        return ym, rows, None
    except urllib.error.HTTPError as e:
        return ym, [], (404 if e.code == 404 else f"HTTP {e.code}")
    except Exception as e:
        return ym, [], str(e)[:60]


def fetch_day(sym, ymd):
    url = (f"https://data.binance.vision/data/futures/um/daily/klines/"
           f"{sym}/1h/{sym}-1h-{ymd}.zip")
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        zf = zipfile.ZipFile(io.BytesIO(data))
        name = zf.namelist()[0]
        raw = zf.read(name).decode()
        rows = []
        for line in raw.strip().split("\n"):
            p = line.split(",")
            if not p[0].rstrip(".").isdigit():
                continue
            rows.append((int(p[0]), float(p[9])))
        return ymd, rows, None
    except urllib.error.HTTPError as e:
        return ymd, [], (404 if e.code == 404 else f"HTTP {e.code}")
    except Exception as e:
        return ymd, [], str(e)[:60]


def daily_complement(cur, sym, db):
    """Passe quotidienne Vision : comble les ~45 derniers jours (le zip mensuel
    du mois écoulé n'est publié qu'après la fin du mois)."""
    import datetime as dt
    d0 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45)
    days = [(d0 + dt.timedelta(days=k)).strftime("%Y-%m-%d") for k in range(46)]
    upd = 0
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch_day, sym, ymd): ymd for ymd in days}
        for fu in cf.as_completed(futs):
            ymd, rows, err = fu.result()
            if err or not rows:
                continue
            cur.executemany(
                "UPDATE bn_kline_1h_deep SET taker_buy=? WHERE symbol=? AND ts=? "
                "AND taker_buy IS NULL", [(tb, sym, ts) for ts, tb in rows])
            upd += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    db.commit()
    return upd


def main():
    db = sqlite3.connect(DB, timeout=30)
    cur = db.cursor()
    log = {}
    for sym in SYMS:
        floor = FLOOR[sym]["kline1h_binance"]
        months = months_between(floor, NOW_MS)
        done = skipped = miss = upd = 0
        t0 = time.time()
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(fetch_month, sym, ym): ym for ym in months}
            for fu in cf.as_completed(futs):
                ym, rows, err = fu.result()
                if err == 404:
                    miss += 1
                    continue
                if err:
                    log.setdefault(sym, {}).setdefault("erreurs", []).append(f"{ym}:{err}")
                    continue
                # barres encore sans taker_buy uniquement
                cur.executemany(
                    "UPDATE bn_kline_1h_deep SET taker_buy=? WHERE symbol=? AND ts=? "
                    "AND taker_buy IS NULL", [(tb, sym, ts) for ts, tb in rows])
                upd += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                done += 1
        db.commit()
        nulls = cur.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=? "
                            "AND taker_buy IS NULL", (sym,)).fetchone()[0]
        log[sym] = dict(mois_ok=done, mois_404=miss, maj_rows=upd,
                        nulls_restants=nulls, sec=round(time.time() - t0, 1))
        print(f"{sym}: {done} mois, {miss} absents, maj={upd}, NULLS={nulls} "
              f"({time.time() - t0:.0f} s)", flush=True)
        if nulls:
            n_day = daily_complement(cur, sym, db)
            nulls = cur.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=? "
                                "AND taker_buy IS NULL", (sym,)).fetchone()[0]
            log[sym]["daily_vision"] = dict(maj_rows=n_day, nulls_restants=nulls)
            print(f"  {sym}: complément DAILY Vision maj={n_day} -> NULLS={nulls}", flush=True)
        if nulls:
            # complément : jours récents (mois courant) par l'API, pacing 0,42 s
            # blindé 418/429 : backoffs progressifs, sinon reporté (reprise possible)
            hi = cur.execute("SELECT MAX(ts) FROM bn_kline_1h_deep WHERE symbol=?",
                             (sym,)).fetchone()[0]
            import urllib.parse
            u = ("https://fapi.binance.com/fapi/v1/klines?" + urllib.parse.urlencode(
                {"symbol": sym, "interval": "1h", "startTime": hi - 40 * 3600_000,
                 "endTime": hi, "limit": 50}))
            j = None
            for wait in (5, 20, 60, 120):
                try:
                    req = urllib.request.Request(u, headers=HDR)
                    j = json.loads(urllib.request.urlopen(req, timeout=15).read())
                    break
                except Exception as e:
                    print(f"  {sym}: API indispo ({e}) -> attente {wait} s", flush=True)
                    time.sleep(wait)
                    j = None
            if j:
                cur.executemany("UPDATE bn_kline_1h_deep SET taker_buy=? WHERE symbol=? AND ts=?",
                                [(float(r[9]), sym, int(r[0])) for r in j])
                db.commit()
                nulls = cur.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=? "
                                    "AND taker_buy IS NULL", (sym,)).fetchone()[0]
                log[sym]["nulls_apres_api"] = nulls
                print(f"  {sym}: complément API -> NULLS={nulls}", flush=True)
                time.sleep(0.42)
            else:
                log[sym]["api_reporte"] = True
                print(f"  {sym}: complément API REPORTÉ (ban fapi) — Vision OK", flush=True)
    db.close()
    json.dump(log, open(LOG, "w"), indent=1)
    tot = sum(v.get("nulls_restants", 0) for v in log.values())
    print(f"TOTAL NULLS restants ≈ {tot} -> {LOG}")


if __name__ == "__main__":
    main()
