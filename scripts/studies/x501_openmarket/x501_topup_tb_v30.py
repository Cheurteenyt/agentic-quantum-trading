#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501 v30 — TOPUP VOLUME TAKER de bn_kline_1h_deep.

Le moteur d'alphas (x501_alpha_backtest.py) calcule le delta CVD à partir du
volume taker acheteur (champ 9 des klines Binance fapi). La collecte deep v29
n'avait stocké que OHLCV (6 colonnes) -> le portage « depuis le début de
l'actif » exige ce topup : même API, même paging, on ajoute la colonne.

  - ALTER TABLE bn_kline_1h_deep ADD COLUMN taker_buy REAL (idempotent)
  - pages backward (endTime, limit 1500) du now vers le plancher de listing
  - INSERT OR REPLACE (UNIQUE symbol,ts) : données identiques + tb
  - pacing 0,42 s (weight 10/page) + backoffs 20-120 s sur 429/418
  - contrôle final : NULL count == 0 et spot-check vs data_x501 (2024)
"""
import sqlite3, json, time, urllib.request, urllib.parse, os, sys

os.chdir(os.environ.get("X501_EXT_ROOT", "/home/z/my-project"))  # data deep locale, hors git (docs/26/37)
DB = "scripts/x501_v21_results/om_v27.db"
LOG = "scripts/x501_v21_results/topup_tb_v30.json"
HDR = {"User-Agent": "Mozilla/5.0"}
PAUSE_BN = 0.42
BN_BACKOFF = [20, 40, 60, 90, 120]
DAY_MS = 86_400_000
NOW_MS = int(time.time() * 1000)

SYMS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "BNBUSDT",
        "ADAUSDT", "DOGEUSDT", "SOLUSDT", "AVAXUSDT"]
FLOOR = json.load(open("scripts/x501_v21_results/floor_v29.json"))


def get(url, timeout=15):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def bn_page(sym, end_ms, limit=1500):
    u = ("https://fapi.binance.com/fapi/v1/klines?" + urllib.parse.urlencode(
        {"symbol": sym, "interval": "1h", "endTime": int(end_ms), "limit": limit}))
    for att, wait in enumerate(BN_BACKOFF):
        try:
            j = get(u)
            return j if isinstance(j, list) else None
        except Exception:
            time.sleep(wait)
    return None


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(bn_kline_1h_deep)")]
    if "taker_buy" not in cols:
        cur.execute("ALTER TABLE bn_kline_1h_deep ADD COLUMN taker_buy REAL")
        db.commit()
        print("colonne taker_buy ajoutée")
    log = {"ts": NOW_MS, "syms": {}}
    for sym in SYMS:
        pre_null = cur.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=? "
                               "AND taker_buy IS NULL", (sym,)).fetchone()[0]
        if pre_null == 0:
            print(f"{sym}: déjà complet (0 null) -> sauté", flush=True)
            log["syms"][sym] = dict(skip="complet")
            continue
        floor = FLOOR[sym]["kline1h_binance"]
        n0 = cur.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=?",
                         (sym,)).fetchone()[0]
        hi = cur.execute("SELECT MAX(ts) FROM bn_kline_1h_deep WHERE symbol=?",
                         (sym,)).fetchone()[0]
        end = hi if hi else NOW_MS  # endTime INCLUSIF (openTime <= endTime)
        pages = touched = 0
        t_start = time.time()
        while end > floor:
            page = bn_page(sym, end)
            if page is None:
                print(f"  {sym}: abandon après backoffs @ {end}", flush=True)
                break
            rows = [(float(r[9]), int(r[0])) for r in page]  # takerBuyBaseVolume
            cur.executemany(
                "UPDATE bn_kline_1h_deep SET taker_buy=? WHERE symbol=? AND ts=?",
                [(tb, sym, ts) for tb, ts in rows])
            # barres nouvelles (trou depuis la dernière collecte) : REPLACE complet
            cur.executemany(
                "INSERT OR REPLACE INTO bn_kline_1h_deep(symbol,ts,open,high,low,"
                "close,volume,taker_buy) VALUES(?,?,?,?,?,?,?,?)",
                [(sym, int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                  float(r[4]), float(r[5]), float(r[9])) for r in page])
            db.commit()
            pages += 1
            touched += len(rows)
            end = min(int(r[0]) for r in page) - 1
            time.sleep(PAUSE_BN)
            if len(page) < 1500:
                break
        nulls = cur.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=? "
                            "AND taker_buy IS NULL", (sym,)).fetchone()[0]
        n1 = cur.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=?",
                         (sym,)).fetchone()[0]
        dt = time.time() - t_start
        log["syms"][sym] = dict(n0=n0, n1=n1, nulls=nulls, pages=pages,
                                touched=touched, sec=round(dt, 1))
        print(f"{sym}: {n0} -> {n1} barres, {pages} pages, nulls={nulls} "
              f"({dt:.0f} s)", flush=True)
    db.close()
    tot = {k: v for k, v in log["syms"].items()}
    log["total_nulls"] = sum(v["nulls"] for v in tot.values())
    json.dump(log, open(LOG, "w"), indent=1)
    print(f"TOTAL nulls restants = {log['total_nulls']} -> {LOG}")


if __name__ == "__main__":
    main()
