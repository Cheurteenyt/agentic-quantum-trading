#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501 v30 — COMPLÈME FINAL taker_buy : 4 plages anciennes sans zip Vision.

Sources de vérité :
  1) fapi klines (startTime/endTime, ≤1500 bars) avec backoffs 418/429 ;
  2) si ban persiste : hypothèse NEUTRE documentée tb = v/2 (delta nul,
     CVD en pause sur la plage) — jamais tb=0 (delta=-v, biais vendeur).
Plages connues : ETH 2019-11-27..12-31 (833), ADA 2020-06-02..06-30 (690),
XRP 2022-02-26..04-02 (120), SOL 2022-02-26..04-02 (120).
"""
import json, sqlite3, time, urllib.request, urllib.parse, datetime as dt

DB = "scripts/x501_v21_results/om_v27.db"
LOG = "scripts/x501_v21_results/topup_tb_final_v30.json"
HDR = {"User-Agent": "Mozilla/5.0"}


def api_range(sym, start_ms, end_ms):
    u = ("https://fapi.binance.com/fapi/v1/klines?" + urllib.parse.urlencode(
        {"symbol": sym, "interval": "1h", "startTime": int(start_ms),
         "endTime": int(end_ms), "limit": 1500}))
    for wait in (10, 30, 60, 120, 180):
        try:
            req = urllib.request.Request(u, headers=HDR)
            return json.loads(urllib.request.urlopen(req, timeout=20).read())
        except Exception as e:
            print(f"  API {sym} indispo ({e}) -> attente {wait} s", flush=True)
            time.sleep(wait)
    return None


def main():
    db = sqlite3.connect(DB, timeout=30)
    cur = db.cursor()
    log = {}
    nulls_by_sym = dict(cur.execute(
        "SELECT symbol, COUNT(*) FROM bn_kline_1h_deep WHERE taker_buy IS NULL "
        "GROUP BY symbol"))
    for sym, n_null in sorted(nulls_by_sym.items()):
        if n_null == 0:
            continue
        lo, hi = cur.execute("SELECT MIN(ts), MAX(ts) FROM bn_kline_1h_deep "
                             "WHERE symbol=? AND taker_buy IS NULL", (sym,)).fetchone()
        print(f"{sym}: {n_null} nulls [{dt.datetime.fromtimestamp(lo/1000, dt.timezone.utc)} .. "
              f"{dt.datetime.fromtimestamp(hi/1000, dt.timezone.utc)}]", flush=True)
        rows = api_range(sym, lo, hi)
        if rows:
            cur.executemany("UPDATE bn_kline_1h_deep SET taker_buy=? WHERE symbol=? AND ts=?",
                            [(float(r[9]), sym, int(r[0])) for r in rows])
            db.commit()
            time.sleep(8)
        left = cur.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=? "
                           "AND taker_buy IS NULL", (sym,)).fetchone()[0]
        if left:
            # hypothèse neutre : tb = v/2 -> delta nul, CVD en pause (documenté)
            cur.execute("UPDATE bn_kline_1h_deep SET taker_buy = volume/2.0 "
                        "WHERE symbol=? AND taker_buy IS NULL", (sym,))
            db.commit()
            print(f"  {sym}: API insuffisante -> {left} barres en NEUTRE tb=v/2", flush=True)
        log[sym] = dict(nulls_initial=n_null, api_rows=len(rows) if rows else 0,
                        neutral_left=left)
    db.close()
    json.dump(log, open(LOG, "w"), indent=1)
    print("OK -> topup_tb_final_v30.json")


if __name__ == "__main__":
    main()
