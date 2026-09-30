#!/usr/bin/env python3
"""REJOUI ASTER (RE, 30/09) — suite de aster_ui_probe : lit
reports/aster_ui_capture.json, classe chaque flux documenté (docs/24 :
fapi v1/v3 klines/depth/openInterest/aggTrades/premiumIndex/fundingRate +
WS @depth20@100ms, !markPrice@arr, @aggTrade, @kline) vs NON documenté, puis
rejoue les XHR en PYTHON PUR curl_cffi impersonate="chrome131" (mêmes
methodes/corps POST) + tente les sockets WS fstream5/sstream SANS navigateur
(SUBSCRIBE + lecture de frames). Verdict par flux : 200/4xx + forme JSON.
Sortie : reports/aster_ui_replay.json + stdout."""
import json, sys, time
from pathlib import Path
from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[2]
CAP = ROOT / "reports" / "aster_ui_capture.json"
OUT = ROOT / "reports" / "aster_ui_replay.json"
UA_BROWSER = None  # curl_cffi impersonate gère le UA

DOC_REST = ("/fapi/v1/klines", "/fapi/v3/klines", "/fapi/v1/depth",
            "/fapi/v3/depth", "/fapi/v1/openInterest", "/fapi/v1/aggTrades",
            "/fapi/v1/premiumIndex", "/fapi/v1/fundingRate",
            "/fapi/v3/premiumIndex", "/fapi/v3/fundingRate")
DOC_WS = ("@depth20@100ms", "!markPrice@arr", "@aggTrade", "@kline_")
SKIP = ("/bapi/composite/v1/public/common/config/getLanguageMapByKey",
        "/bapi/composite/v1/public/composite/ae/announcement",
        "static.asterdexfx.com", "static2.asterdexfx.com", "feapi.asterdex.com",
        "auth.privy.io", "nodereal.io", "ninicoin.io", "bscrpc.com",
        "ankr.com", "walletconnect.com", "space.id", "cloudfront.net")


def classify(url: str) -> str:
    path = url.split("?")[0].replace("https://www.asterdex.com", "")
    return "DOC" if any(path == d or path.startswith(d) for d in DOC_REST) else "NON-DOC"


def shape(body: str) -> str:
    try:
        j = json.loads(body)
        if isinstance(j, list):
            return f"list[{len(j)}] item_keys={sorted(j[0].keys())[:12] if j and isinstance(j[0], dict) else '-'}"
        if isinstance(j, dict):
            k = list(j.keys())
            if set(k) <= {"code", "msg", "message", "messageDetail", "data", "success"}:
                d = j.get("data")
                if isinstance(d, dict):
                    return f"enveloppe data_keys={sorted(d.keys())[:14]}"
                if isinstance(d, list):
                    return f"enveloppe data=list[{len(d)}] item_keys={sorted(d[0].keys())[:14] if d and isinstance(d[0], dict) else '-'}"
            return f"keys={k[:14]}"
    except Exception:
        return f"non-JSON ({len(body)}B)"
    return "?"


def main() -> int:
    cap = json.loads(CAP.read_text())
    reqs = [r for r in cap["requests"]
            if not any(s in r["url"] for s in SKIP)]
    print(f"=== REJOUI REST chrome131 — {len(reqs)} candidats (hors bruit) ===\n")
    results = []
    s = cffi.Session(impersonate="chrome131", timeout=15)
    for r in reqs:
        url, m = r["url"], r["method"]
        kw = {"headers": {"Referer": "https://www.asterdex.com/en/trade/pro/futures/BTCUSDT",
                          "Origin": "https://www.asterdex.com",
                          "Accept": "application/json, text/plain, */*"}}
        if m == "POST" and r.get("post"):
            kw["data"] = r["post"].encode()
        cls = classify(url)
        try:
            resp = s.request(m, url, **kw)
            body = resp.text
            status = resp.status_code
        except Exception as e:
            status, body = -1, f"ERR {str(e)[:80]}"
        row = {"class": cls, "status": status, "browser_status": r.get("status"),
               "method": m, "url": url[:180], "shape": shape(body) if status == 200 else body[:120]}
        results.append(row)
        print(f"  [{cls:7s}] {m:4s} {status} (UI:{r.get('status')}) {url[:120]}")
        if status == 200:
            print(f"           {row['shape'][:160]}")
        else:
            print(f"           {body[:110]}")

    # === REJOUI WS SANS NAVIGATEUR ===
    # curl_cffi 0.16 ws_connect/recv() HANG sur ce serveur (handshake OK, 0
    # frame, recv bloquant sans timeout) → websockets.sync (dispo en venv).
    print("\n=== REJOUI WS sans navigateur (websockets.sync, SUBSCRIBE) ===")
    from websockets.sync.client import connect as ws_connect
    UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/131.0.0.0 Safari/537.36")
    ws_tests = [("wss://fstream5.asterdex.com/plain/stream",
                 ["!assetIndex@arr", "!sfpriceIndex@arr", "!miniTicker@arr", "!tradingMode@arr"]),
                ("wss://sstream.asterdex.com/stream", ["!miniTicker@arr"])]
    ws_out = []
    for url, streams in ws_tests:
        try:
            ws = ws_connect(url, open_timeout=10, additional_headers={
                "Origin": "https://www.asterdex.com", "User-Agent": UA})
            ws.send(json.dumps({"method": "SUBSCRIBE", "params": streams, "id": 1}))
            got, seen = 0, {}
            t0 = time.monotonic()
            while got < 10 and time.monotonic() - t0 < 12:
                try:
                    msg = ws.recv(timeout=4)
                except Exception:
                    break
                got += 1
                try:
                    j = json.loads(str(msg))
                    key = str(j.get("stream") or j.get("result") or "?")
                    if isinstance(j.get("data"), dict):
                        key += ":" + str(j["data"].get("e", ""))
                    seen[key] = seen.get(key, 0) + 1
                except Exception:
                    seen["RAW"] = seen.get("RAW", 0) + 1
            ws.close()
            ws_out.append({"url": url, "streams": streams, "recv": seen})
            print(f"  OK {url} → {seen}")
        except Exception as e:
            ws_out.append({"url": url, "streams": streams, "error": str(e)[:120]})
            print(f"  ERR {url} : {str(e)[:110]}")

    OUT.write_text(json.dumps({"rest": results, "ws": ws_out}, ensure_ascii=False, indent=1))
    n_ok = sum(1 for r in results if r["status"] == 200)
    n_nd = sum(1 for r in results if r["class"] == "NON-DOC" and r["status"] == 200)
    print(f"\nbilan REST: {n_ok}/{len(results)} rejoués 200 dont {n_nd} NON-documentés → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
