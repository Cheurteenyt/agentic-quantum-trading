#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonde de convention temporelle LSR Bybit (vague 11) — mesurée, pas supposée.

Question pré-enregistrée : la ligne LSR estampillée T couvre-t-elle la
fenêtre [T, T+P) PUBLIÉE PROGRESSIVEMENT (partielle, réécrite en place),
ou n'est-elle publiée qu'à la clôture de sa fenêtre ?
Le probe prélevé à 02:31 UTC (avant la frontière 03:00) a DÉJÀ montré une
ligne 1h estampillée 02:00 EXISTANTE à 02:31 — soit une fenêtre en cours
(publiée partiellement), soit un décalage de publication. Test : la valeur
de la ligne 02:00 change-t-elle entre 02:35 (fenêtre en cours) et 03:05
(fenêtre close) ? Si OUI -> partielle confirmée, mesurée, gravée au
manifeste ; la règle de consommation pré-enregistrée devient : la ligne T
n'est JAMAIS lue avant T+P + marge de collecte (2 périodes de refroidissement).
8 passes, 8 min d'intervalle (~1 h), 2 symboles, 3 périodes (1h, 4h, 1d).
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.bybit.com"
OUT = Path(os.environ.get("X501_EXT_ROOT", "/home/z/my-project") + "/scripts/lsr_probe_v11.jsonl")
SYMS = ["BTCUSDT", "ETHUSDT"]
PERIODS = ["1h", "4h", "1d"]
N_PASSES = 8
GAP_S = 480

OUT.parent.mkdir(parents=True, exist_ok=True)


def get(path, params):
    url = f"{BASE}{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "x501-probe/11"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"probe fetch failed: {last}")


def main():
    for p in range(N_PASSES):
        t_fetch = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rec = {"pass": p, "fetch_utc": t_fetch, "rows": []}
        for sym in SYMS:
            for per in PERIODS:
                d = get("/v5/market/account-ratio",
                        {"category": "linear", "symbol": sym,
                         "period": per, "limit": 8})
                for row in d.get("result", {}).get("list", []):
                    rec["rows"].append({
                        "symbol": sym, "period": per,
                        "ts": int(row["timestamp"]),
                        "buyRatio": row.get("buyRatio"),
                        "sellRatio": row.get("sellRatio"),
                    })
        with open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")
        n = len(rec["rows"])
        print(f"[pass {p}] {t_fetch} rows={n}", flush=True)
        if p < N_PASSES - 1:
            time.sleep(GAP_S)
    print("probe done", flush=True)


if __name__ == "__main__":
    main()
