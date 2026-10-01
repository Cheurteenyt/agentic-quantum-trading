#!/usr/bin/env python3
"""
x501_collect_lsr_v11.py — collecte VAGUE 11 (LSR long/short account ratio +
klines 4h/1d, Bybit, outils gratuits) — le collecteur versionné du banc LSR
(x501_lsr_local.py, docs/36).

Paramètres de collecte GRAVÉS avant tout chiffre (doctrine docs/03, docs/26) :
- Sources publiques gratuites, un seul exchange : Bybit v5 (category=linear)
  — la sémantique d'exécution du domaine (Bybit VIP0 USDT-perp, docs/25).
- Panel : les 12 symboles om_v27 (manifeste docs/26, liste v17 reprise à
  l'identique) : BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, SUI, APT,
  1000PEPE (tous suffixés USDT).
- Série 1 : klines 4h (endpoint /v5/market/kline, interval=240, limit=1000,
  pagination par `end` décroissant) — cap collecteur 6 000 barres (~2,7 ans).
- Série 2 : klines 1d (interval=D, limit=1000, pagination `end`) — cap
  1 100 barres (~3 ans).
- Série 3 : LSR 4h (endpoint /v5/market/account-ratio, period=4h, limit=500,
  pagination par `cursor` — le paramètre `end` n'est pas supporté par cet
  endpoint, mesuré le 01/10/2026 : sonde retCode 10001 « param period err »
  sur `interval`, pagination cursor fonctionnelle, page 2 BTCUSDT 1d
  retombe au 2024-01-06) — cap collecteur 6 000 lignes.
- Série 4 : LSR 1d (period=1d, limit=500, pagination `cursor`) — cap 1 100
  lignes.
- SÉMANTIQUE TIMESTAMP LSR (mesurée par la sonde lsr_probe_v11, VERDICT
  gravé le 01/10/2026 03:15 UTC) : la ligne estampillée T couvre la
  fenêtre [T-P, T) et est PUBLIÉE FINALISÉE peu après T (la ligne 1h
  estampillée 03:00 est apparue à 03:04:44 avec une valeur jamais réécrite
  ; la ligne 02:00 est restée identique sur 9 passes à cheval sur la
  frontière) — CORRECTION DATÉE : la première note de collecte (02:47)
  supposait une publication partielle en place de la fenêtre en cours ;
  la sonde l'a réfuté (aucune ligne partielle exposée, sémantique END).
  RÈGLE ANTI-PARTIEL pré-enregistrée CONSERVÉE TELLE QUELLE : la collecte
  DROPE toute ligne LSR estampillée T > now − 3P (deux périodes de
  refroidissement après T) — sur-conservatrice sous la sémantique END
  mesurée, elle garantit a fortiori des lignes finalisées ; la barre
  kline en cours (open + P > now) est droppée (seul son open est stable,
  doctrine _MK).
- Alignement de grille : les lignes LSR 4h (resp. 1d) et les opens klines
  4h (resp. 1d) partagent la même grille UTC (00:00, 04:00, ...) —
  l'existence PILE exigée par l'étude (0 fill-forward).
- Sortie : JSONL brut par (symbole, série) dans X501_LSR_OUT (défaut :
  data/x501_lsr du repo, git-ignoré) + manifest.json (n points, oldest ts,
  cutoff appliqué, n lignes droppées). La re-collecte n'est PAS
  bit-compatible (data live) : la reproductibilité bit à bit porte sur
  l'ÉTUDE à data fixée (digest du JSON, QA R1), pas sur le flux.
- Politesse : 0,12 s entre appels, 3 retries exponentiels. Zéro secret :
  endpoints publics, aucun header authentifié.

Usage : python3 x501_collect_lsr_v11.py [SYM1,SYM2,...]
Env   : X501_LSR_OUT=<dir de sortie> (défaut data/x501_lsr du repo)
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
CAP_4H = 6_000          # barres/lignes 4h (~2,7 ans)
CAP_1D = 1_100          # barres/lignes 1d (~3 ans)
OUT = Path(os.environ.get("X501_LSR_OUT",
                          Path(__file__).resolve().parent.parent.parent.parent / "data" / "x501_lsr"))
PAUSE = 0.12
RETRIES = 3

MS_4H = 4 * 3_600_000
MS_1D = 86_400_000

os.makedirs(OUT, exist_ok=True)


def get(path, params):
    url = f"{BASE}{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    last = None
    for i in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "x501-study/11"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode())
            if d.get("retCode") != 0:
                raise RuntimeError(f"retCode={d.get('retCode')} {d.get('retMsg','')[:80]}")
            return d["result"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.8 * (2 ** i))
    raise RuntimeError(f"échec après {RETRIES} retries: {last} | {url[:120]}")


def cutoff_kline(now_ms, p_ms):
    """Barre droppée si EN COURS : open + P > now (l'open seul est stable)."""
    return now_ms - p_ms


def cutoff_lsr(now_ms, p_ms):
    """Ligne LSR droppée si T > now − 3P : fenêtre [T, T+P) finalisée à
    T+P puis refroidie deux périodes (règle anti-partiel pré-enregistrée,
    sonde lsr_probe_v11 : publication partielle en place mesurée)."""
    return now_ms - 3 * p_ms


def collect_klines(sym, interval, cap, p_ms):
    """Klines Bybit (interval '240' ou 'D'), limit=1000, pagination end
    décroissant, cap barres, barre en cours droppée."""
    path = OUT / f"{sym}_klines_{interval}.jsonl"
    now_ms = int(time.time() * 1000)
    cut = cutoff_kline(now_ms, p_ms)
    end = now_ms
    total, pages, oldest, n_drop = 0, 0, None, 0
    with open(path, "w") as f:
        while end > 0 and pages < 40:
            res = get("/v5/market/kline", {"category": "linear", "symbol": sym,
                                           "interval": interval, "limit": 1000,
                                           "end": end})
            rows = res.get("list", [])
            if not rows:
                break
            for r in rows:
                ts = int(r[0])
                if ts > cut:
                    n_drop += 1          # barre en cours
                    continue
                if total >= cap:
                    break
                f.write(json.dumps({"ts": ts, "o": r[1], "h": r[2], "l": r[3],
                                    "c": r[4], "v": r[5], "qv": r[6]}) + "\n")
                total += 1
                oldest = ts
            pages += 1
            page_oldest = int(rows[-1][0])
            if page_oldest >= end - p_ms:  # plus de progression
                break
            end = page_oldest - p_ms
            if total >= cap:
                break
            time.sleep(PAUSE)
    return total, oldest, n_drop


def collect_lsr(sym, period, cap, p_ms):
    """LSR Bybit (period '4h' ou '1d'), limit=500, pagination cursor, cap
    lignes, règle anti-partiel (T <= now − 3P)."""
    path = OUT / f"{sym}_lsr_{period}.jsonl"
    now_ms = int(time.time() * 1000)
    cut = cutoff_lsr(now_ms, p_ms)
    cursor = ""
    total, pages, oldest, n_drop = 0, 0, None, 0
    with open(path, "w") as f:
        while pages < 40:
            params = {"category": "linear", "symbol": sym,
                      "period": period, "limit": 500}
            if cursor:
                params["cursor"] = cursor
            res = get("/v5/market/account-ratio", params)
            rows = res.get("list", [])
            if not rows:
                break
            for r in rows:
                ts = int(r["timestamp"])
                if ts > cut:
                    n_drop += 1          # fenêtre non finalisée / refroidissement
                    continue
                if total >= cap:
                    break
                f.write(json.dumps({"ts": ts,
                                    "buyRatio": float(r["buyRatio"]),
                                    "sellRatio": float(r["sellRatio"])}) + "\n")
                total += 1
                oldest = ts
            pages += 1
            cursor = res.get("nextPageCursor", "")
            if not cursor or len(rows) < 500 or total >= cap:
                break
            time.sleep(PAUSE)
    return total, oldest, n_drop


def main():
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else SYMBOLS
    manifest = {"collecte_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "probe": "lsr_probe_v11 VERDICT 01/10 03:15 UTC : sémantique END "
                         "(ligne T = fenêtre [T-P, T), publiée finalisée ≤ ~5 min "
                         "après T, aucune ligne partielle exposée — correction de "
                         "la note 02:47 qui supposait une publication partielle en "
                         "place) -> règle anti-partiel T <= now-3P conservée "
                         "(sur-conservatrice sous END)",
                "symbols": {}}
    mpath = OUT / "manifest.json"
    if mpath.exists():
        manifest = json.loads(mpath.read_text())
    for sym in only:
        t0 = time.time()
        nk4, ok4, dk4 = collect_klines(sym, "240", CAP_4H, MS_4H)
        time.sleep(PAUSE)
        nk1, ok1, dk1 = collect_klines(sym, "D", CAP_1D, MS_1D)
        time.sleep(PAUSE)
        nl4, ol4, dl4 = collect_lsr(sym, "4h", CAP_4H, MS_4H)
        time.sleep(PAUSE)
        nl1, ol1, dl1 = collect_lsr(sym, "1d", CAP_1D, MS_1D)
        manifest["symbols"][sym] = {
            "klines_4h": {"n": nk4, "oldest_ts": ok4, "n_drop_encours": dk4},
            "klines_1d": {"n": nk1, "oldest_ts": ok1, "n_drop_encours": dk1},
            "lsr_4h": {"n": nl4, "oldest_ts": ol4, "n_drop_antipartiel": dl4},
            "lsr_1d": {"n": nl1, "oldest_ts": ol1, "n_drop_antipartiel": dl1},
            "seconds": round(time.time() - t0, 1)}
        mpath.write_text(json.dumps(manifest, indent=1))
        print(f"{sym}: k4h={nk4}(old {ok4}) k1d={nk1}(old {ok1}) "
              f"lsr4h={nl4}(old {ol4}) lsr1d={nl1}(old {ol1}) "
              f"[{manifest['symbols'][sym]['seconds']}s]", flush=True)
    print("COLLECTE TERMINÉE", flush=True)


if __name__ == "__main__":
    main()
