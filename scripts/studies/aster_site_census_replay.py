#!/usr/bin/env python3
"""REJOUI DU CENSUS ASTERDEX (nuit 30/09) — suite de aster_site_census.py.
Lit reports/aster_site_census_capture.json, compare aux flux DÉJÀ connus
(reports/aster_ui_capture.json du 30/09 matin + la famille documentée
docs/24 : fapi v1/v3 + les bapi découverts), et ne rejoue en curl_cffi
chrome131 QUE les NOUVEAUX chemins REST (méthode/corps POST préservés) +
teste les sockets WS nouvelles (websockets.sync — curl_cffi 0.16 est une
impasse sur le WS aster). Verdict par flux : 200/4xx + forme JSON.
Sortie : reports/aster_site_census_replay.json + stdout."""
import json, sys
from pathlib import Path
from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[2]
CAP = ROOT / "reports" / "aster_site_census_capture.json"
PREV = ROOT / "reports" / "aster_ui_capture.json"
OUT = ROOT / "reports" / "aster_site_census_replay.json"

DOC_REST = ("/fapi/v1/klines", "/fapi/v3/klines", "/fapi/v1/depth",
            "/fapi/v3/depth", "/fapi/v1/openInterest", "/fapi/v1/aggTrades",
            "/fapi/v1/premiumIndex", "/fapi/v1/fundingRate",
            "/fapi/v3/premiumIndex", "/fapi/v3/fundingRate",
            "/fapi/v1/ticker", "/fapi/v1/assetIndex", "/fapi/v1/time")
SKIP = ("/bapi/composite/v1/public/common/config/getLanguageMapByKey",
        "static.asterdexfx.com", "static2.asterdexfx.com",
        "feapi.asterdex.com", "auth.privy.io", "walletconnect",
        "nodereal.io", "ninicoin.io", "bscrpc.com", "ankr.com",
        "space.id", "cloudfront.net", "google", "fonts.")
KNOWN_WS = ("wss://fstream5.asterdex.com", "wss://sstream.asterdex.com",
            "wss://nbstream.binance.com")


def path_of(url: str) -> str:
    return url.split("?")[0].replace("https://www.asterdex.com", "")


def classify(url: str) -> str:
    p = path_of(url)
    if any(p == d or p.startswith(d) for d in DOC_REST):
        return "DOC"
    return "NON-DOC"


def shape(body: str) -> str:
    try:
        j = json.loads(body)
        if isinstance(j, list):
            return f"list[{len(j)}] item_keys={sorted(j[0].keys())[:12] if j and isinstance(j[0], dict) else '-'}"
        if isinstance(j, dict):
            k = list(j.keys())
            if set(k) <= {"code", "msg", "message", "messageDetail", "data",
                          "success"} and "data" in j:
                d = j["data"]
                if isinstance(d, dict):
                    return f"enveloppe data_keys={sorted(d.keys())[:16]}"
                if isinstance(d, list):
                    return (f"enveloppe data=list[{len(d)}] item_keys="
                            f"{sorted(d[0].keys())[:16] if d and isinstance(d[0], dict) else '-'}")
                return f"enveloppe data={str(d)[:80]}"
            return f"keys={k[:14]}"
    except Exception:
        return f"non-JSON ({len(body)}B)"
    return "?"


def main() -> int:
    cap = json.loads(CAP.read_text())
    known = set()
    if PREV.exists():
        prev = json.loads(PREV.read_text())
        known = {path_of(r["url"]) for r in prev.get("requests", [])}
    print(f"flux déjà vus (sonde du matin) : {len(known)} chemins")

    rows, seen_new = [], set()
    for r in cap["requests"]:
        p = path_of(r["url"])
        if any(s in r["url"] for s in SKIP):
            continue
        if p in known or p in seen_new:
            continue
        seen_new.add(p)
        rows.append(r)
    print(f"=== REJOUI {len(rows)} chemins NOUVEAUX (non vus ce matin) ===\n")
    results = []
    s = cffi.Session(impersonate="chrome131", timeout=15)
    for r in rows:
        url, m = r["url"], r["method"]
        kw = {"headers": {"Referer": "https://www.asterdex.com/en",
                          "Origin": "https://www.asterdex.com",
                          "Accept": "application/json, text/plain, */*"}}
        if m == "POST" and r.get("post"):
            kw["data"] = r["post"].encode()
            kw["headers"]["Content-Type"] = "application/json"  # sinon 400 illegal parameter
        cls = classify(url)
        try:
            resp = s.request(m, url, **kw)
            status, body = resp.status_code, resp.text
        except Exception as e:
            status, body = -1, f"ERR {str(e)[:80]}"
        row = {"class": cls, "status": status, "browser_status": r.get("status"),
               "method": m, "url": url[:220], "phases": r.get("phases", []),
               "shape": shape(body) if status == 200 else body[:150]}
        results.append(row)
        tag = "NOUVEAU" if cls == "NON-DOC" else "doc"
        print(f"  [{tag:7s}] {m:4s} {status} (UI:{r.get('status')}) {url[:125]}")
        print(f"           {row['shape'][:170]}")

    # === WS nouvelles sockets ===
    new_ws = sorted({f["url"] for f in cap["frames"] if f["dir"] == "open"
                     and not any(f["url"].startswith(k) for k in KNOWN_WS)})
    ws_out = []
    # + les NOUVEAUX streams découverts dans les souscriptions de l'UI
    NEW_STREAMS = ["!markPriceTicker@arr", "!sfFundingRate@arr",
                   "!sf24hQuoteChangex@arr", "!sf24hrMiniTicker@arr",
                   "!notification@arr", "announcement", "btcusdt@aggSnap",
                   "iBTCUSD@kline_1m"]
    try:
        from websockets.sync.client import connect as ws_connect
        UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/131.0.0.0 Safari/537.36")
        for url in new_ws:
            try:
                ws = ws_connect(url, open_timeout=10, additional_headers={
                    "Origin": "https://www.asterdex.com", "User-Agent": UA})
                got, seen = 0, {}
                t0 = 0
                import time
                t0 = time.monotonic()
                while got < 6 and time.monotonic() - t0 < 10:
                    try:
                        msg = ws.recv(timeout=4)
                    except Exception:
                        break
                    got += 1
                    try:
                        j = json.loads(str(msg))
                        key = str(j.get("stream") or j.get("method") or
                                  j.get("e") or f"ARR[{len(j)}]")[:50]
                    except Exception:
                        key = "RAW:" + str(msg)[:40]
                    seen[key] = seen.get(key, 0) + 1
                ws.close()
                ws_out.append({"url": url, "recv": seen})
                print(f"  WS OK {url} → {seen}")
            except Exception as e:
                ws_out.append({"url": url, "error": str(e)[:120]})
                print(f"  WS ERR {url} : {str(e)[:110]}")

        # les nouveaux streams sur fstream5 (websockets.sync, pas curl_cffi)
        try:
            ws = ws_connect("wss://fstream5.asterdex.com/plain/stream",
                            open_timeout=10, additional_headers={
                                "Origin": "https://www.asterdex.com",
                                "User-Agent": UA})
            ws.send(json.dumps({"method": "SUBSCRIBE", "params": NEW_STREAMS, "id": 1}))
            import time as _t
            seen, got, t0 = {}, 0, _t.monotonic()
            while got < 14 and _t.monotonic() - t0 < 12:
                try:
                    msg = ws.recv(timeout=4)
                except Exception:
                    break
                got += 1
                try:
                    j = json.loads(str(msg))
                    key = str(j.get("stream") or j.get("result") or "?")[:44]
                    d = j.get("data")
                    if isinstance(d, list) and d:
                        key += f" list[{len(d)}]"
                    elif isinstance(d, dict):
                        key += ":" + str(d.get("e", ""))
                except Exception:
                    key = "RAW:" + str(msg)[:40]
                seen[key] = seen.get(key, 0) + 1
            ws.close()
            ws_out.append({"url": "fstream5:NEW_STREAMS", "streams": NEW_STREAMS,
                           "recv": seen})
            print(f"  WS OK fstream5 NOUVEAUX streams → {seen}")
        except Exception as e:
            ws_out.append({"url": "fstream5:NEW_STREAMS", "error": str(e)[:120]})
            print(f"  WS ERR fstream5 NOUVEAUX : {str(e)[:110]}")
    except ImportError as e:
        print("websockets absent:", e)

    OUT.write_text(json.dumps({"rest": results, "ws": ws_out},
                              ensure_ascii=False, indent=1))
    n_ok = sum(1 for r in results if r["status"] == 200)
    n_nd = sum(1 for r in results if r["class"] == "NON-DOC" and r["status"] == 200)
    print(f"\nbilan REST : {n_ok}/{len(results)} rejoués 200 dont "
          f"{n_nd} NOUVEAUX non-documentés → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
