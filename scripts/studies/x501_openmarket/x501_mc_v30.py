#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OPÉRATION x501 — v30 (MC) : RE-CHIFFREMENT sur le pool DEEP « depuis le
début de l'actif » (politique verrouillée docs/37).

Différences vs v20 (le noyau est INCHANGÉ) :
  - POOL = pool_v30_deep.pkl : trades du moteur x501_engine_deep_v30.py —
    klines Binance deep 1h depuis le LISTING de chaque actif (BTC 2019-09-08
    ->, ETH 2019-11-28 ->, ... SUI 2023-09-14 ->), grille BTC, flux ajoutés
    au fil des listings, warmup 60 j par actif depuis son propre premier bar.
  - La fenêtre de calibration passe de 23 mois (pire cas du cycle) à la
    TOTALITÉ de l'historique perp Binance (7,07 ans max) — la politique
    « toujours backtester depuis le début de l'actif » impose ce re-chiffrement.
  - Scénarios de coûts IDENTIQUES à v20 (mesure maker x501_maker_v27.py,
    52 728 tentatives / 708 j) : W0 0 / W4 maker d5 1,7 / W1 maker d2 2,0 /
    W2 taker réel 6,1 / W3 stress 8,2 bps par côté.
  - Audits : T2 pire cas absolu + T3 reproductibilité bit à bit (T0/T_cont de
    v20 portaient sur la médiane certifiée du pool v8 — non applicables ici,
    remplacés par le rapport au pool v8 dans la sortie JSON).

Noyau : simulate_ratchet v12 bit à bit, N_PATHS=12 000, 36 mois, ratchet=None.
Sortie : scripts/x501_v21_results/mc_v30.json
"""
import json
import os
import pickle
import sys
import time

EXT_ROOT = os.environ.get("X501_EXT_ROOT", "/home/z/my-project")  # noyau v10/v11/v12 + pool deep : data locale, hors git (docs/26/37)
sys.path.insert(0, f"{EXT_ROOT}/scripts")
import x501_mc_v12 as v12                                             # noqa: E402
import x501_mc_v10 as v10                                             # noqa: E402
from x501_mc_v11 import G4, LEGS                                      # noqa: E402
import numpy as np                                                    # noqa: E402
import datetime as dtm                                                # noqa: E402

OUT = f"{EXT_ROOT}/scripts/x501_v21_results"
POOL = f"{OUT}/pool_v30_deep.pkl"
POOL_V8 = f"{EXT_ROOT}/scripts/x501_v8_results/pool_v8_P1.pkl"

SCEN = [
    ("W0_reference_deep",      0.0),
    ("W4_maker_d5",            1.7),
    ("W1_maker_d2_central",    2.0),
    ("W2_taker_reel",          6.1),
    ("W3_stress",              8.2),
]

ERAS = [(2019, 2020), (2021, 2021), (2022, 2022), (2023, 2023),
        (2024, 2024), (2025, 2025), (2026, 2026)]


def dist_bps(t):
    qty0 = sum(leg[2] for leg in t["legs"])
    risk = t.get("risk_usd", t.get("risk"))
    if qty0 <= 0 or t["entry"] <= 0 or not risk:
        return None
    return risk / (qty0 * t["entry"]) * 1e4


def apply_costs(trades, bps):
    out = []
    for t in trades:
        c = dict(t)
        db = dist_bps(t)
        if db and db > 0:
            c["R"] = t["R"] - (2.0 * bps) / db
        out.append(c)
    return out


def er_by_side(trades):
    s = [t["R"] for t in trades if t["side"] == -1]
    l = [t["R"] for t in trades if t["side"] == 1]
    return (float(np.mean(s)) if s else None, float(np.mean(l)) if l else None)


def era_stats(trades):
    """E[R], n et somme R par ère de marché (année d'entrée du trade)."""
    out = {}
    for a, b in ERAS:
        sel = [t for t in trades
               if a <= dtm.datetime.fromtimestamp(t["t_in"] / 1000,
                                                  dtm.timezone.utc).year <= b]
        rs = [t["R"] for t in sel]
        out[f"{a}" if a == b else f"{a}-{b}"] = {
            "n": len(sel),
            "ER": round(float(np.mean(rs)), 4) if rs else None,
            "somme_R": round(float(np.sum(rs)), 2) if rs else 0.0,
            "WR_pct": round(100.0 * sum(1 for r in rs if r > 0) / len(rs), 1) if rs else None,
        }
    return out


def main():
    with open(POOL, "rb") as f:
        trades = pickle.load(f)["trades"]
    # mapping jambes v8 : main = BTC/ETH, sat = alts (LEGS = main-A1/A3/A4,
    # sat-A4/A3 ; A2 hors jambes, comme dans le pool officiel v8)
    PREM = {"BTCUSDT", "ETHUSDT"}
    for t in trades:
        t["pool"] = "main" if t["key"].split(":")[1] in PREM else "sat"
    er_s0, er_l0 = er_by_side(trades)
    print(f"Pool DEEP v30 : {len(trades)} trades (short {sum(1 for t in trades if t['side']==-1)}, "
          f"long {sum(1 for t in trades if t['side']==1)}) | E[R] short {er_s0:.3f} long {er_l0:.3f}")

    try:
        with open(POOL_V8, "rb") as f:
            v8 = pickle.load(f)["trades"]
        ref_v8 = {"n_trades_v8_23mois": len(v8),
                  "ER_v8": round(float(np.mean([t["R"] for t in v8])), 4),
                  "ER_v30": round(float(np.mean([t["R"] for t in trades])), 4),
                  "ratio_ER": round(float(np.mean([t["R"] for t in trades])) /
                                    float(np.mean([t["R"] for t in v8])), 3)}
    except Exception:
        ref_v8 = {"note": "pool v8 non disponible"}

    results = {"ts": time.time(),
               "pool": "pool_v30_deep.pkl (depuis le listing de chaque actif, politique docs/37)",
               "noyau": "simulate_ratchet v12 bit à bit, N_PATHS=12000, 36 mois, seed=7, cad_mult=3",
               "couts": "identiques v20 (maker_v27 : taker 6,1 / d2 2,0 / d5 1,7 / stress 8,2 bps/côté)",
               "ref_pool_v8": ref_v8,
               "eras": era_stats(trades),
               "scenarios": {}, "audits": {}}

    for (name, bps) in SCEN:
        tr = apply_costs(trades, bps)
        legs_all, months = v10.make_legs(tr)
        blocks5 = [legs_all[k] for k in LEGS]
        r = v12.simulate_ratchet(blocks5, G4, label=name, seed=7, cad_mult=3, ratchet=None)
        er_s, er_l = er_by_side(tr)
        results["scenarios"][name] = {
            "bps_per_side": bps, "n_trades": len(tr),
            "ER_short": round(er_s, 4), "ER_long": round(er_l, 4),
            "mois_pool": len(months),
            "eq12_med": r["eq12_med"], "eq12_p25": r["eq12_p25"], "eq12_p75": r["eq12_p75"],
            "ruptures_n": r["ruptures_n"], "maxdd_med": r["maxdd_med"],
            "maxdd_p90": r["maxdd_p90"], "maxdd_max": r["maxdd_max"],
            "jalon_250_p12": r["jalon_250_p12"], "jalon_500_p12": r["jalon_500_p12"],
            "jalon_1250_p12": r["jalon_1250_p12"],
            "jalon_50100_p12": r.get("jalon_50100_p12", None),
            "jalon_50100_p36": r.get("jalon_50100_p36", None),
        }
        s = results["scenarios"][name]
        print(f"[{name:24}] bps={bps:4} | E[R]s {er_s0:.3f}->{er_s:.3f} | "
              f"méd12 {s['eq12_med']:.1f}$ [{s['eq12_p25']:.0f};{s['eq12_p75']:.0f}] | "
              f"DDméd {s['maxdd_med']:.2f}% max {s['maxdd_max']:.2f}% | rupt {s['ruptures_n']} | "
              f"P250 {s['jalon_250_p12']:.1f}% P500 {s['jalon_500_p12']:.1f}% "
              f"P1250 {s['jalon_1250_p12']:.1f}% P50100@12m {s['jalon_50100_p12']:.2f}%", flush=True)

    # ---- AUDITS --------------------------------------------------------------
    # T2 : pire cas absolu (le coupe-circuit doit rester inviolé)
    worst = [[-1.5] * 5 for _ in range(30)]
    r = v12.simulate_ratchet([worst] * 5, G4, label="pire-cas-v30", seed=1, cad_mult=3, ratchet=None)
    ok2 = r["ruptures_n"] == 0 and r["maxdd_max"] <= 25.0 + 1e-6
    results["audits"]["T2_pire_cas"] = {"ok": ok2, "rupt": r["ruptures_n"], "maxdd": r["maxdd_max"]}
    print(f"T2 : ruptures={r['ruptures_n']} maxDD={r['maxdd_max']:.6f}% -> {'OK' if ok2 else 'ECHEC'}")

    # T3 : reproductibilité bit à bit sur W4
    tr = apply_costs(trades, 1.7)
    legs_all, _ = v10.make_legs(tr)
    blocks5 = [legs_all[k] for k in LEGS]
    ra = v12.simulate_ratchet(blocks5, G4, label="repro", seed=7, cad_mult=3, ratchet=None)
    rb = v12.simulate_ratchet(blocks5, G4, label="repro", seed=7, cad_mult=3, ratchet=None)
    d3 = v10.same({"m": ra["eq12_med"]}, {"m": rb["eq12_med"]})
    ok3 = (not d3) and abs(ra["eq12_med"] - results["scenarios"]["W4_maker_d5"]["eq12_med"]) < 1e-9
    results["audits"]["T3_repro_W4"] = {"ok": ok3, "diffs": d3[:3]}
    print(f"T3 repro W4 : {'OK bit à bit' if ok3 else d3[:3]}")

    with open(f"{OUT}/mc_v30.json", "w") as f:
        json.dump(results, f, indent=1)
    print("OK -> mc_v30.json")


if __name__ == "__main__":
    main()
