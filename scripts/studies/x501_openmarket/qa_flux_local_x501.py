#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_flux_local_x501.py — QA de la vague 5 (x501_flux_local.py).

Contrôles mécaniques, indépendants du run principal :
  QA-01  structure de la grille : 6 cellules A + 6 cellules B + 2 cellules C
  QA-02  verdicts complets et ordonnés (KILL/INCONCLU/CANDIDAT/CONTEXTE)
  QA-03  AUC Mann-Whitney : séparations parfaites et nulles bien étalonnées
  QA-04  TEST D'ALTÉRATION (le contrôle décisif) : en décalant le score
         d'une barre vers l'AVANT (look-ahead), l'AUC doit S'ÉCARTER
         nettement de 0,5 — la plomberie détecte un vrai signal quand il
         existe ; le KILL du panel est donc réel et non un bug de plomberie
  QA-05  convention temps stricte : le score à t est insensible aux barres
         postérieures à t (mutation des barres futures = score inchangé)
  QA-06  convention funding : le score à t est la moyenne des K derniers
         paiements de timestamp <= t (recalcul indépendant sur BTC)
  QA-07  pool P1 : 469 entrées, tous les t_in sont des opens exacts, R dans
         les bornes plausibles, 40 symboles couverts
  QA-08  AUC par symbole (anti-dilution du pooling) : sur 8 symboles
         liquides, la moyenne des AUC individuelles reste ~0,5 (le KILL n'est
         pas un artefact de pooling cross-sectionnel)
  QA-09  reproductibilité bit à bit : re-exécution complète de l'étude,
         JSON identique à l'octet près
Usage : X501_DATA_DIR=<dir> python3 qa_flux_local_x501.py [--quick]
  (--quick saute QA-09, la re-exécution complète)
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(__import__("os").environ.get(
    "X501_DATA_DIR", HERE / "../../../data/x501_1h"))
ETUDE = HERE / "x501_flux_local.py"
JSON_ETUDE = HERE / "flux_local.json"
POOL_CSV = HERE / "pool_P1_entrees.csv"
MS_H = 3_600_000

ECHECS = []


def check(nom, ok, detail=""):
    statut = "PASS" if ok else "ECHEC"
    print(f"  [{statut}] {nom}" + (f" — {detail}" if detail else ""))
    if not ok:
        ECHECS.append(nom)
    return ok


def load_klines(sym):
    p = DATA_DIR / f"{sym}_1h.csv"
    cols = ("open_time", "open", "close", "quote_volume", "taker_buy_quote_volume")
    buf = {c: [] for c in cols}
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            for c in cols:
                buf[c].append(float(row[c]))
    return {c: np.asarray(v, dtype=np.float64) for c, v in buf.items()}


def ema(x, span):
    lam = 2.0 / (span + 1.0)
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = lam * x[i] + (1.0 - lam) * y[i - 1]
    return y


def auc_mw(x_haut, x_bas):
    x = np.concatenate([x_haut, x_bas])
    n1 = len(x_haut)
    ordre = np.argsort(x, kind="mergesort")
    sx = x[ordre]
    r = np.arange(1.0, len(x) + 1.0)
    if np.any(np.diff(sx) == 0):
        i = 0
        while i < len(x):
            j = i
            while j + 1 < len(x) and sx[j + 1] == sx[i]:
                j += 1
            if j > i:
                r[i:j + 1] = (i + j) / 2.0 + 1.0
            i = j + 1
    out = np.empty(len(x))
    out[ordre] = r
    r1 = out[:n1].sum()
    return (r1 - n1 * (n1 + 1) / 2.0) / (n1 * (len(x) - n1))


def score_flux(kl, lb):
    """Score flux STRICT (barres clôturées) : s[t] = EMA(D)[t-1]."""
    qv, tb = kl["quote_volume"], kl["taker_buy_quote_volume"]
    with np.errstate(invalid="ignore", divide="ignore"):
        D = np.where(qv > 0, 2.0 * tb / qv - 1.0, 0.0)
    e = ema(D, lb)
    s = np.empty(len(e))
    s[0] = np.nan
    s[1:] = e[:-1]
    return s, D


def fwd_open(kl, h):
    op, n = kl["open"], len(kl["open"])
    ret = np.full(n, np.nan)
    ret[:n - h] = (op[h:] - op[:n - h]) / op[:n - h] * 1e4
    return ret


def main():
    quick = "--quick" in sys.argv
    print(f"X501_DATA_DIR = {DATA_DIR}")
    res = json.loads(JSON_ETUDE.read_text())

    print("\nQA-01 structure de la grille")
    check("6 cellules A", set(res["etude_A_flux_taker"]) ==
          {f"L{lb}_H{h}" for lb in (6, 24, 72) for h in (24, 72)})
    check("6 cellules B", set(res["etude_B_funding"]) ==
          {f"K{k}_H{h}" for k in (9, 21, 90) for h in (24, 72)})
    check("2 cellules C", set(res["etude_C_pool_P1"]) == {"n_pool_utilise", "score_A", "score_B"})

    print("\nQA-02 verdicts complets")
    verds = [r["verdict"] for r in res["etude_A_flux_taker"].values()] + \
            [r["verdict"] for r in res["etude_B_funding"].values()]
    check("12 verdicts dans le vocabulaire", all(v in ("KILL", "INCONCLU", "CANDIDAT", "CONTEXTE") for v in verds))
    check("chaque cellule a n, AUC, IC 2 bornes, delta",
          all(len(r["ic95"]) == 2 and r["n"] > 0 and np.isfinite(r["auc"]) for r in
              list(res["etude_A_flux_taker"].values()) + list(res["etude_B_funding"].values())))

    print("\nQA-03 étalonnage AUC Mann-Whitney (cas exacts)")
    rng = np.random.default_rng(501)
    check("AUC(x_haut=[1,2,3], x_bas=[10,20]) = 0", auc_mw(np.array([1.0, 2, 3]), np.array([10.0, 20])) == 0.0)
    check("AUC(x_haut=[10,20], x_bas=[1,2,3]) = 1", auc_mw(np.array([10.0, 20]), np.array([1.0, 2, 3])) == 1.0)
    g = rng.normal(size=2000)
    check("AUC(x, x) = 0,5", abs(auc_mw(g, g.copy()) - 0.5) < 1e-12)
    check("ex-aequo : AUC([1,1,2],[1,2,2]) = 1/3",
          abs(auc_mw(np.array([1.0, 1, 2]), np.array([1.0, 2, 2])) - 1.0 / 3.0) < 1e-12)
    a = rng.normal(size=2000)
    b = rng.normal(size=2000)
    check("AUC symétrique : AUC(x,y) = 1 - AUC(y,x)",
          abs((auc_mw(a, b) + auc_mw(b, a)) - 1.0) < 1e-12)

    print("\nQA-04 TEST D'ALTÉRATION (look-ahead) — la plomberie doit voir un signal s'il existe")
    for sym in ("BTCUSDT", "ETHUSDT"):
        kl = load_klines(sym)
        s_strict, D = score_flux(kl, 24)
        f24 = fwd_open(kl, 24)
        ok = np.isfinite(s_strict) & np.isfinite(f24)
        auc_strict = auc_mw(f24[ok][s_strict[ok] > np.median(s_strict[ok])],
                            f24[ok][s_strict[ok] <= np.median(s_strict[ok])])
        s_look = np.empty(len(D))  # triche : score AUSSI au temps t (look-ahead)
        s_look[:] = ema(D, 24)
        ok2 = np.isfinite(s_look) & np.isfinite(f24)
        auc_look = auc_mw(f24[ok2][s_look[ok2] > np.median(s_look[ok2])],
                          f24[ok2][s_look[ok2] <= np.median(s_look[ok2])])
        ret_intra = (kl["close"] - kl["open"]) / kl["open"] * 1e4  # même barre
        ok3 = np.isfinite(s_look) & np.isfinite(ret_intra)
        auc_intra = auc_mw(ret_intra[ok3][s_look[ok3] > np.median(s_look[ok3])],
                           ret_intra[ok3][s_look[ok3] <= np.median(s_look[ok3])])
        check(f"{sym} strict ~0,5 (KILL réel)", abs(auc_strict - 0.5) < 0.02,
              f"AUC {auc_strict:.4f}")
        check(f"{sym} look-ahead DÉCOLLE de 0,5", auc_look - 0.5 >= 0.01,
              f"AUC {auc_look:.4f} (vs strict {auc_strict:.4f})")
        check(f"{sym} flux intrabar détecté", auc_intra - 0.5 >= 0.03,
              f"AUC(D[t] vs ret_intra[t]) {auc_intra:.4f}")

    print("\nQA-05 convention temps stricte (zéro look-ahead)")
    kl = load_klines("BTCUSDT")
    s, _ = score_flux(kl, 24)
    t = 20_000  # barre de test en zone pleine (26 208 barres)
    s_avant = s[t]
    kl2 = dict(kl)
    kl2["quote_volume"] = kl["quote_volume"].copy()
    kl2["quote_volume"][t + 10] = kl["quote_volume"][t + 10] * 3.0  # mutation future
    kl2["taker_buy_quote_volume"] = kl["taker_buy_quote_volume"].copy()
    kl2["taker_buy_quote_volume"][t + 10] = kl2["taker_buy_quote_volume"][t + 10] * 0.2
    s_apres, _ = score_flux(kl2, 24)
    check("score[t] insensible aux barres > t", s_avant == s_apres[t])

    print("\nQA-06 convention funding (recalcul indépendant sur BTC)")
    ft, fr = [], []
    with open(DATA_DIR / "BTCUSDT_funding.csv", newline="") as f:
        for row in csv.DictReader(f):
            ft.append(float(row["funding_time"]))
            fr.append(float(row["funding_rate"]))
    ft, fr = np.asarray(ft), np.asarray(fr)
    K = 21
    ot = kl["open_time"]
    t_test = ot[20_000]
    idx = int(np.searchsorted(ft, t_test, side="right") - 1)
    manuel = float(np.mean(fr[idx - K + 1: idx + 1]))
    pref = np.concatenate([[0.0], np.cumsum(fr)])
    mec = (pref[idx + 1] - pref[idx + 1 - K]) / K
    check("moyenne des K derniers paiements <= t", abs(manuel - mec) < 1e-15,
          f"manuel {manuel:.8f} = mécanique {mec:.8f}")
    check("paiement effectif connu à sa date", ft[idx] <= t_test < ft[min(idx + 1, len(ft) - 1)])

    print("\nQA-07 pool P1")
    pool = list(csv.DictReader(open(POOL_CSV, newline="")))
    check("469 entrées", len(pool) == 469, f"n = {len(pool)}")
    syms_pool = {r["sym"] for r in pool}
    check("40 symboles", len(syms_pool) == 40)
    ot_btc = load_klines("BTCUSDT")["open_time"]
    t_in_btc = [int(r["t_in"]) for r in pool if r["sym"] == "BTCUSDT"]
    idxs = np.searchsorted(ot_btc, t_in_btc, side="left")
    check("t_in sont des opens exacts (doctrine _MK)",
          all(i < len(ot_btc) and ot_btc[i] == t for i, t in zip(idxs, t_in_btc)),
          f"{len(t_in_btc)} entrées BTC")
    R_all = [float(r["R"]) for r in pool]
    check("R bornes réelles du pool certifié (>= -2.0 gap stop, <= 8.0)",
          all(-2.0 <= r <= 8.0 for r in R_all),
          f"min {min(R_all):.3f}, max {max(R_all):.3f}")

    print("\nQA-08 AUC par symbole (anti-dilution du pooling)")
    for lb in (6, 24, 72):
        aucs = []
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                    "DOGEUSDT", "ADAUSDT", "LINKUSDT"):
            kl8 = load_klines(sym)
            s8, _ = score_flux(kl8, lb)
            f8 = fwd_open(kl8, 24)
            ok8 = np.isfinite(s8) & np.isfinite(f8)
            med = np.median(s8[ok8])
            aucs.append(auc_mw(f8[ok8][s8[ok8] > med], f8[ok8][s8[ok8] <= med]))
        m = float(np.mean(aucs))
        check(f"moyenne AUC individuelle L{lb}_H24 ~ 0,5", abs(m - 0.5) < 0.02,
              f"moyenne {m:.4f} sur 8 symboles")

    print("\nQA-09 reproductibilité bit à bit")
    if quick:
        print("  [--quick] sautée")
    else:
        import shutil
        tmp = HERE / "flux_local_qa_copy.json"
        shutil.copy(JSON_ETUDE, tmp)
        subprocess.run([sys.executable, str(ETUDE)], check=True,
                       capture_output=True,
                       env={"X501_DATA_DIR": str(DATA_DIR), "PATH": "/usr/bin:/bin"})
        a = tmp.read_bytes()
        b = JSON_ETUDE.read_bytes()
        tmp.unlink()
        check("re-run identique à l'octet près", a == b, f"{len(b)} octets")

    print(f"\nBILAN : {len(ECHECS)} échec(s)" + (f" -> {ECHECS}" if ECHECS else ""))
    return 1 if ECHECS else 0


if __name__ == "__main__":
    sys.exit(main())
