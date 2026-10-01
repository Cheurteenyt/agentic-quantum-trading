#!/usr/bin/env python3
"""
x501_collect_oi_v8.py — collecte VAGUE 8 (OI 1h + klines 1h, Bybit, outils
gratuits) — le collecteur versionné du banc OI (x501_oi_local.py, docs/33).

Paramètres de collecte GRAVÉS avant tout chiffre (doctrine docs/03, docs/26) :
- Sources publiques gratuites, un seul exchange : Bybit v5 (category=linear)
  — la sémantique d'exécution du domaine (Bybit VIP0 USDT-perp, docs/25).
- Panel : les 12 symboles om_v27 (manifeste docs/26, liste v17 reprise à
  l'identique) : BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, SUI, APT,
  1000PEPE (tous suffixés USDT).
- Série 1 : klines 1h (endpoint /v5/market/kline, interval=60, limit=1000,
  pagination par `end` décroissant) — cible 740 jours.
- Série 2 : open interest 1h (endpoint /v5/market/open-interest,
  intervalTime=1h, limit=200, pagination par `cursor` — le paramètre `end`
  est IGNORÉ par cet endpoint, mesuré le 01/10/2026) — cap collecteur
  200 pages x 200 points = 40 000 points par symbole (~4,5 ans sur les
  majeures ; la profondeur réelle Bybit est supérieure, le cap suffit à la
  fenêtre d'étude de 740 jours).
- Sémantique timestamp (correction v27, docs/26) : le ts marque l'OUVERTURE
  de la fenêtre horaire (snapshot quasi instantané à hh:00 pour l'OI,
  début de barre pour la kline) — l'étude n'utilise JAMAIS le snapshot
  simultané à l'open de décision.
- Sortie : JSONL brut par (symbole, série) dans X501_OI_OUT (défaut :
  data/x501_oi du repo, git-ignoré) + manifest.json (n points, oldest ts,
  secondes). La re-collecte n'est PAS bit-compatible (data live) : la
  reproductibilité bit à bit porte sur l'ÉTUDE à data fixée (digest du
  JSON, QA R1), pas sur le flux.
- Politesse : 0,12 s entre appels, 3 retries exponentiels. Zéro secret :
  endpoints publics, aucun header authentifié.

Usage : python3 x501_collect_oi_v8.py [SYM1,SYM2,...]
Env   : X501_OI_OUT=<dir de sortie> (défaut data/x501_oi du repo)
"""
import json
import time
import urllib.request
import os
import sys
from pathlib import Path

BASE = "https://api.bybit.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "APTUSDT", "1000PEPEUSDT"]
TARGET_DAYS = 740
OUT = Path(os.environ.get("X501_OI_OUT",
                          Path(__file__).resolve().parent.parent.parent / "data" / "x501_oi"))
PAUSE = 0.12
RETRIES = 3

os.makedirs(OUT, exist_ok=True)


def get(path, params):
    url = f"{BASE}{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    last = None
    for i in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "x501-study/8"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode())
            if d.get("retCode") != 0:
                raise RuntimeError(f"retCode={d.get('retCode')} {d.get('retMsg','')[:80]}")
            return d["result"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.8 * (2 ** i))
    raise RuntimeError(f"échec après {RETRIES} retries: {last} | {url[:120]}")


def collect_klines(sym):
    """Klines 1h Bybit, limit=1000, pagination end décroissant."""
    path = OUT / f"{sym}_klines.jsonl"
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - TARGET_DAYS * 86_400_000
    end = now_ms
    total, pages, oldest = 0, 0, None
    with open(path, "w") as f:
        while end > start_ms and pages < 40:
            res = get("/v5/market/kline", {"category": "linear", "symbol": sym,
                                           "interval": "60", "limit": 1000, "end": end})
            rows = res.get("list", [])
            if not rows:
                break
            for r in rows:
                f.write(json.dumps({"ts": int(r[0]), "o": r[1], "h": r[2], "l": r[3],
                                    "c": r[4], "v": r[5], "qv": r[6]}) + "\n")
            total += len(rows)
            pages += 1
            oldest = int(rows[-1][0])
            if oldest >= end - 3_600_000:  # plus de progression
                break
            end = oldest - 3_600_000
            time.sleep(PAUSE)
    return total, oldest


def collect_oi(sym):
    """OI 1h Bybit, limit=200, pagination cursor (end ignoré), cap 200 pages."""
    path = OUT / f"{sym}_oi.jsonl"
    cursor = ""
    total, pages, oldest = 0, 0, None
    with open(path, "w") as f:
        while pages < 200:
            params = {"category": "linear", "symbol": sym,
                      "intervalTime": "1h", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            res = get("/v5/market/open-interest", params)
            rows = res.get("list", [])
            if not rows:
                break
            for r in rows:
                f.write(json.dumps({"ts": int(r["timestamp"]),
                                    "oi": float(r["openInterest"])}) + "\n")
            total += len(rows)
            pages += 1
            oldest = int(rows[-1]["timestamp"])
            cursor = res.get("nextPageCursor", "")
            if not cursor or len(rows) < 200:
                break
            time.sleep(PAUSE)
    return total, oldest


def main():
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else SYMBOLS
    manifest = {}
    mpath = OUT / "manifest.json"
    if mpath.exists():
        manifest = json.loads(mpath.read_text())
    for sym in only:
        t0 = time.time()
        nk, ok = collect_klines(sym)
        time.sleep(PAUSE)
        no, oo = collect_oi(sym)
        manifest[sym] = {"klines": {"n": nk, "oldest_ts": ok},
                         "oi": {"n": no, "oldest_ts": oo},
                         "seconds": round(time.time() - t0, 1)}
        mpath.write_text(json.dumps(manifest, indent=1))
        print(f"{sym}: klines={nk} (oldest {ok}) oi={no} (oldest {oo}) "
              f"[{manifest[sym]['seconds']}s]", flush=True)
    print("COLLECTE TERMINÉE", flush=True)


if __name__ == "__main__":
    main()
