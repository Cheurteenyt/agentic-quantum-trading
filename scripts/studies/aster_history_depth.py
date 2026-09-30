#!/usr/bin/env python
"""T4 — Profondeur historique de l'API Aster fapi (la genèse de chaque marché).

Endpoints sondés : /fapi/v3/klines (paginé arrière par endTime, limit 1500),
/fapi/v3/fundingRate (paginé arrière, limit 1000), /fapi/v3/aggTrades
(pagination fromId), /fapi/v3/premiumIndex, /fapi/v3/openInterest,
/futures/data/* (absences attendues).

Pacing : 1 appel / 1.45 s (~41 req/min, weight ~410/min << 600).
AUCUNE boucle sur /ping ou /time. Read-only, aucune DB touchée.

Sortie : résumé JSON imprimé + reports/aster_history_depth_data.json.
"""
import json
import sys
import time
import datetime as dt
from collections import Counter

from curl_cffi import requests

B = "https://fapi.asterdex.com"
S = requests.Session(impersonate="chrome131")
PACE = 1.45  # secondes entre appels
MAX_WEIGHT = 600

STATS = {"calls": 0, "weight_peak": 0}
RES = {"generated_utc": dt.datetime.now(dt.UTC).isoformat()}


def log(*a):
    print(f"[{dt.datetime.now(dt.UTC).strftime('%H:%M:%S')}]", *a, flush=True)


def d(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M") if ms else None


def dd(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d") if ms else None


def get(path, params=None, retries=4):
    """GET avec pacing strict, retry sur 429/5xx, None sur 404."""
    for i in range(retries):
        try:
            r = S.get(B + path, params=params, timeout=30)
        except Exception as e:
            log("  net-err", e, "retry", i + 1)
            time.sleep(3 * (i + 1))
            continue
        STATS["calls"] += 1
        w = r.headers.get("x-mbx-used-weight-1m") or r.headers.get("X-MBX-USED-WEIGHT-1M")
        if w:
            STATS["weight_peak"] = max(STATS["weight_peak"], int(w))
        if r.status_code == 200:
            time.sleep(PACE)
            return r.json()
        if r.status_code in (429, 418):
            log("  !! rate-limit", r.status_code, "pause 25s")
            time.sleep(25)
            continue
        if r.status_code == 404:
            time.sleep(PACE)
            return None
        log("  !! http", r.status_code, str(r.text[:120]))
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"get failed: {path} {params}")


IV_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}


def klines_page(symbol, interval, end_time=None, limit=1500):
    p = {"symbol": symbol, "interval": interval, "limit": limit}
    if end_time:
        p["endTime"] = end_time
    return get("/fapi/v3/klines", p)


def klines_full(symbol, interval, max_pages=400):
    """Pagination arrière complète jusqu'à la genèse. Retour (meta, open_times)."""
    pages, times, end = [], [], None
    oldest_seen = None
    while len(pages) < max_pages:
        r = klines_page(symbol, interval, end)
        if not r:
            break
        pages.append(r)
        ot = [int(k[0]) for k in r]
        times = ot + times
        new_old = ot[0]
        if new_old == oldest_seen:
            log(f"  !! page muette {symbol} {interval}")
            break
        oldest_seen = new_old
        end = new_old - 1
        if len(r) < 1500:
            break
    gaps = []
    if len(times) > 1:
        step = IV_MS[interval]
        prev = times[0]
        for t in times[1:]:
            if t - prev != step:
                gaps.append((prev, t, (t - prev) / step))
            prev = t
    meta = {
        "symbol": symbol, "interval": interval,
        "candles": len(times), "pages": len(pages),
        "first_open": times[0] if times else None,
        "first_open_utc": dd(times[0]) if times else None,
        "last_open": times[-1] if times else None,
        "last_open_utc": dd(times[-1]) if times else None,
        "n_gaps": len(gaps),
        "gaps_top": [{"from": d(g[0]), "to": d(g[1]), "x": g[2]} for g in sorted(gaps, key=lambda g: -g[2])[:5]],
    }
    return meta, times, gaps


def klines_genesis_probe(symbol, interval, window_days=30):
    """Sonde la genèse par sauts exponentiels puis bisection (PAS de crawl complet)."""
    now_ms = int(time.time() * 1000)
    iv = IV_MS[interval]
    good, empty = None, None  # (days_back, oldest_open_of_window)
    days = window_days
    probes = 0
    while True:
        r = klines_page(symbol, interval, now_ms - days * 86_400_000)
        probes += 1
        if r:
            good = (days, int(r[0][0]))
            days *= 3
            if days > 4000:  # > 11 ans : impossible
                break
        else:
            empty = days
            break
    while empty and good and empty - good[0] > 1:
        mid = (good[0] + empty) // 2
        r = klines_page(symbol, interval, now_ms - mid * 86_400_000)
        probes += 1
        if r:
            good = (mid, int(r[0][0]))
        else:
            empty = mid
    genesis = good[1] if good else None
    # confirmation : une page juste avant la genèse doit être vide
    confirm_empty = None
    if genesis:
        r = klines_page(symbol, interval, genesis - 1)
        probes += 1
        confirm_empty = (r == [])
    meta = {
        "symbol": symbol, "interval": interval,
        "genesis_open_utc": dd(genesis),
        "genesis_open": genesis,
        "span_days": round((now_ms - genesis) / 86_400_000, 1) if genesis else None,
        "est_candles": round((now_ms - genesis) / iv) if genesis else 0,
        "confirm_empty_before_genesis": confirm_empty,
        "probes": probes,
    }
    return meta


def funding_full(symbol, window_days=30, max_windows=90):
    """Pagination FENÊTRÉE startTime+endTime (obligatoire sur Aster).

    Piège vérifié le 2026-09-30 : la pagination endTime-seule (style klines)
    saute des années — le serveur sert un bloc récent + un bloc ancien sans le
    milieu, ALORS que startTime+endTime restitue l'historique continu.
    On recule fenêtre par fenêtre jusqu'à la première fenêtre vide.
    """
    now = int(time.time() * 1000)
    rows, end, done = [], now, False
    for _ in range(max_windows):
        start = end - window_days * 86_400_000
        r = get("/fapi/v3/fundingRate", {"symbol": symbol, "startTime": start, "endTime": end, "limit": 1000})
        if r:
            rows = [(int(x["fundingTime"]), x["fundingRate"]) for x in r] + rows
        elif rows:
            done = True  # première fenêtre vide après des données = genèse atteinte
        if done or end < 1_600_000_000_000:
            break
        end = start - 1
    diffs = Counter()
    for a, b in zip(rows, rows[1:]):
        diffs[(b[0] - a[0]) // 3_600_000] += 1
    iv_h = diffs.most_common(1)[0][0] if diffs else None
    big_gaps = []
    if iv_h:
        thr = max(2, iv_h * 2) * 3_600_000
        for a, b in zip(rows, rows[1:]):
            diff = b[0] - a[0]
            if diff > thr:
                big_gaps.append((d(a[0]), d(b[0]), round(diff / 3_600_000, 1)))
    meta = {
        "symbol": symbol, "events": len(rows),
        "first_utc": dd(rows[0][0]) if rows else None,
        "first_open": rows[0][0] if rows else None,
        "last_utc": dd(rows[-1][0]) if rows else None,
        "median_interval_h": iv_h,
        "interval_mix": {f"{k}h": v for k, v in sorted(diffs.items())},
        "big_gaps": [{"from": g[0], "to": g[1], "h": g[2]} for g in sorted(big_gaps, key=lambda g: -g[2])[:5]],
    }
    return meta


def agg_probe(symbol, mid_probes=(0.25, 0.5, 0.75)):
    latest = get("/fapi/v3/aggTrades", {"symbol": symbol, "limit": 1000})
    if not latest:
        return {"symbol": symbol, "error": "no trades"}
    a_max, t_max = int(latest[-1]["a"]), int(latest[-1]["T"])
    first = get("/fapi/v3/aggTrades", {"symbol": symbol, "fromId": 1, "limit": 1000})
    out = {"symbol": symbol, "max_id": a_max, "newest_utc": d(t_max)}
    if first and int(first[0]["a"]) <= 3:  # tape accessible depuis l'origine
        a_first, t_first = int(first[0]["a"]), int(first[0]["T"])
        out["tape_from_genesis"] = True
        out["first_id"] = a_first
        out["first_utc"] = d(t_first)
        # contiguïté près de la genèse : fromId=1001 doit tomber pile sur 1001
        nxt = get("/fapi/v3/aggTrades", {"symbol": symbol, "fromId": first[-1]["a"] + 1, "limit": 2})
        out["contiguous_after_first_page"] = bool(nxt) and int(nxt[0]["a"]) == int(first[-1]["a"]) + 1
    else:
        out["tape_from_genesis"] = False
        out["lowest_accessible_utc"] = d(int(first[0]["T"])) if first else None
    # sondes au milieu du tape (accès aléatoire => backfill partiel possible)
    out["mid"] = []
    for f in mid_probes:
        fid = max(1, int(a_max * f))
        r = get("/fapi/v3/aggTrades", {"symbol": symbol, "fromId": fid, "limit": 2})
        out["mid"].append({"frac": f, "served_utc": d(int(r[0]["T"])) if r else None})
    return out


def main():
    log("=== T4 aster_history_depth — pacing", PACE, "s ===")

    # ---- 0. exchangeInfo : onboardDate par symbole ----
    e = get("/fapi/v3/exchangeInfo")
    onboard = {x["symbol"]: x.get("onboardDate") for x in e.get("symbols", [])}
    RES["n_symbols"] = len(onboard)
    log("exchangeInfo:", len(onboard), "symboles")

    # ---- 1. KLINES : crawls complets ----
    RES["klines_full"] = {}
    for sym, iv in [("BTCUSDT", "1h"), ("BTCUSDT", "15m"),
                    ("ETHUSDT", "1h"), ("SOLUSDT", "1h"), ("ASTERUSDT", "1h"),
                    ("ASTERUSDT", "15m"), ("TRUMPUSDT", "1h"),
                    ("AIW3USDT", "1h"), ("QNTUSDT", "1h"), ("XDPUSDT", "1h")]:
        log(f"--- klines full {sym} {iv} ---")
        meta, times, gaps = klines_full(sym, iv)
        RES["klines_full"][f"{sym}_{iv}"] = meta
        log("   ", json.dumps(meta, ensure_ascii=False))

    # ---- 2. KLINES : sondes de genèse 5m/1m sur BTC (PAS de crawl) ----
    RES["klines_probe"] = {}
    for iv in ("5m", "1m"):
        log(f"--- klines genèse-probe BTCUSDT {iv} ---")
        RES["klines_probe"][f"BTCUSDT_{iv}"] = klines_genesis_probe("BTCUSDT", iv)
        log("   ", json.dumps(RES["klines_probe"][f"BTCUSDT_{iv}"], ensure_ascii=False))

    # ---- 3. FUNDING ----
    RES["funding"] = {}
    for sym in ("BTCUSDT", "ASTERUSDT", "ETHUSDT"):
        log(f"--- funding full {sym} ---")
        RES["funding"][sym] = funding_full(sym)
        log("   ", json.dumps(RES["funding"][sym], ensure_ascii=False))

    # ---- 4. AGGTRADES ----
    RES["aggtrades"] = {}
    for sym in ("BTCUSDT", "ASTERUSDT", "ETHUSDT", "XDPUSDT"):
        log(f"--- aggTrades {sym} ---")
        RES["aggtrades"][sym] = agg_probe(sym)
        log("   ", json.dumps(RES["aggtrades"][sym], ensure_ascii=False))

    # ---- 5. ABSENCES : premiumIndex / openInterest / futures/data ----
    RES["absences"] = {}
    r = get("/fapi/v3/premiumIndex", {"symbol": "BTCUSDT", "startTime": 0})
    RES["absences"]["premiumIndex_with_startTime"] = (
        "IGNORED (snapshot seul)" if isinstance(r, dict) and "time" in r else str(r)[:80])
    r = get("/fapi/v3/openInterest", {"symbol": "BTCUSDT", "startTime": 0})
    RES["absences"]["openInterest_with_startTime"] = (
        "IGNORED (snapshot seul)" if isinstance(r, dict) and "openInterest" in r else str(r)[:80])
    for path in ("/futures/data/openInterestHist?symbol=BTCUSDT&period=15m",
                 "/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=15m",
                 "/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=15m"):
        r = get(path)
        RES["absences"][path.split("?")[0].split("/")[-1]] = "404 (absent)" if r is None else f"PRESENT: {str(r)[:60]}"
    log("absences:", json.dumps(RES["absences"], ensure_ascii=False))

    # ---- 6. onboardDate des sondés ----
    RES["onboard"] = {s: dd(o) for s, o in onboard.items()
                      if s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ASTERUSDT", "TRUMPUSDT",
                               "AIW3USDT", "QNTUSDT", "XDPUSDT", "SKHXUSDT", "SMSNUSDT")}

    RES["stats"] = STATS
    out = "reports/aster_history_depth_data.json"
    with open(out, "w") as f:
        json.dump(RES, f, indent=1, ensure_ascii=False)
    log("=== FIN ===", STATS["calls"], "appels, weight peak", STATS["weight_peak"], "->", out)


if __name__ == "__main__":
    sys.exit(main())
