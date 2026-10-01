#!/usr/bin/env python3
"""x501 — probe PLANCHER de données par symbole (v29, réponse « backtest 6 ans ou max ? »).
Détermine la date la plus ancienne disponible pour:
  - kline 1h Bybit  (v5/market/kline, fenêtre 1 j, bisection)
  - kline 1h Binance(fapi klines,      fenêtre 1 j, bisection)
  - OI 1d Bybit     (v5/market/open-interest, interval=1d, bisection)
  - funding Binance (fapi/fundingRate, start=0 limit=1 -> premier funding = listing effectif)
Sortie: scripts/x501_v21_results/floor_v29.json
Aucune écriture DB. GET only. Pause 0.12 s entre appels.
"""
import json, time, datetime as dt, urllib.request, urllib.parse, sys

SYM = ["1000PEPEUSDT", "ADAUSDT", "APTUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT",
       "DOGEUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT"]
HDR = {"User-Agent": "Mozilla/5.0"}
PAUSE = 0.12
DAY_MS = 86_400_000
OUT = "scripts/x501_v21_results/floor_v29.json"

def get(url, timeout=12):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def get_retry(url, n=3):
    for i in range(n):
        try:
            return get(url)
        except Exception as e:
            if i == n - 1:
                return None
            time.sleep(1.5 * (i + 1))

def bybit_kline(sym, start_ms, end_ms, limit=1):
    u = ("https://api.bybit.com/v5/market/kline?" + urllib.parse.urlencode(
        {"category": "linear", "symbol": sym, "interval": "60",
         "start": int(start_ms), "end": int(end_ms), "limit": limit}))
    j = get_retry(u)
    if not j or j.get("retCode") != 0:
        return None
    return j["result"]["list"]  # [[ts,o,h,l,c,v],...] reverse-chrono

def bn_kline(sym, start_ms, end_ms, limit=1):
    u = ("https://fapi.binance.com/fapi/v1/klines?" + urllib.parse.urlencode(
        {"symbol": sym, "interval": "1h", "startTime": int(start_ms),
         "endTime": int(end_ms), "limit": limit}))
    j = get_retry(u)
    return j if isinstance(j, list) else None

def bybit_oi1d(sym, start_ms, end_ms, limit=1):
    u = ("https://api.bybit.com/v5/market/open-interest?" + urllib.parse.urlencode(
        {"category": "linear", "symbol": sym, "intervalTime": "1d",
         "startTime": int(start_ms), "endTime": int(end_ms), "limit": limit}))
    j = get_retry(u)
    if not j or j.get("retCode") != 0:
        return None
    return j["result"]["list"]

def bn_funding_first(sym, start_ms, end_ms, limit=1):
    u = ("https://fapi.binance.com/fapi/v1/fundingRate?" + urllib.parse.urlencode(
        {"symbol": sym, "startTime": int(start_ms), "endTime": int(end_ms), "limit": limit}))
    j = get_retry(u)
    return j if isinstance(j, list) else None

def floor_bisect(probe_fn, sym, y_lo=2017, y_hi=None):
    """Premier jour [X, X+1j] non vide. Bisection sur X (ms). Retour ts ms ou None."""
    lo = int(dt.datetime(y_lo, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    if y_hi is None:
        hi = int(time.time() * 1000) - DAY_MS  # hier : garanti non futur
    else:
        hi = int(dt.datetime(y_hi, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    if probe_fn(sym, lo, lo + DAY_MS) is None or len(probe_fn(sym, lo, lo + DAY_MS) or []) == 0:
        # pas de données avant 2017 -> plancher > lo
        pass
    else:
        return lo
    # bisection: invariant f(lo)==False (vide), f(hi)==True (non vide)
    f = lambda x: (probe_fn(sym, x, x + DAY_MS) or []) != []
    if not f(hi):
        return None
    while hi - lo > DAY_MS:
        mid = (lo + hi) // 2 // DAY_MS * DAY_MS
        if f(mid):
            hi = mid
        else:
            lo = mid
        time.sleep(PAUSE)
    return hi

def main():
    res = {}
    for sym in SYM:
        d = {}
        t0 = time.time()
        # --- kline 1h Bybit : bisection (coarse 30 j puis fin 1 j)
        fl = floor_bisect(lambda s, a, b: bybit_kline(s, a, b, 1), sym)
        d["kline1h_bybit"] = fl
        # --- kline 1h Binance
        fb = floor_bisect(lambda s, a, b: bn_kline(s, a, b, 1), sym)
        d["kline1h_binance"] = fb
        # --- OI 1d Bybit
        fo = floor_bisect(lambda s, a, b: bybit_oi1d(s, a, b, 1), sym)
        d["oi1d_bybit"] = fo
        # --- funding Binance : même bisection (fenêtre 1 j, 1er point)
        ff = floor_bisect(lambda s, a, b: bn_funding_first(s, a, b, 1), sym)
        d["funding_binance"] = ff
        res[sym] = d
        fmt = lambda x: dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).strftime("%Y-%m-%d") if x else "None"
        print(f"{sym:14s} kBB={fmt(fl)} kBN={fmt(fb)} OI={fmt(fo)} FR={fmt(d['funding_binance'])} ({time.time()-t0:.0f}s)", flush=True)
        time.sleep(PAUSE)
        with open(OUT, "w") as f:  # sauvegarde incrémentale
            json.dump(res, f, indent=1)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print("OK ->", OUT)

if __name__ == "__main__":
    main()
