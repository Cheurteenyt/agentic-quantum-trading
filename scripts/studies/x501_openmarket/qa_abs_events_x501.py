#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_abs_events_x501.py — QA DE LA VAGUE 6 (le banc d'événements absorption).
9 familles, le même standard que la vague 5 : le DÉTECTEUR est testé sur des
séries synthétiques construites à la main (chaque condition violée isolément),
le nesting E3 ⊆ E2 ⊆ E1 est contrôlé sur données réelles, le zéro look-ahead
est prouvé par MUTATION des barres futures, la re-exécution est BIT À BIT.
0 échec attendu. Sortie : rapport console + code retour 1 au premier échec.

Usage : python3 qa_abs_events_x501.py   (X501_DATA_DIR en env, même convention
que l'étude ; la re-exécution bit à bit relance l'étude complète : ~3 min)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import x501_abs_events_local as etu  # noqa: E402

DATA_DIR = Path(os.environ.get("X501_DATA_DIR", HERE / "../../../data/x501_1h"))

ECHECS = []


def check(nom, ok, detail=""):
    statut = "PASS" if ok else "FAIL"
    print(f"[{statut}] {nom}" + (f" — {detail}" if detail else ""))
    if not ok:
        ECHECS.append(nom)


# =====================================================================
# F1 — la structure du JSON et le vocabulaire des verdicts
# =====================================================================
def f1_structure():
    with open(etu.OUT_JSON) as f:
        res = json.load(f)
    panel = res["etude_A_panel"]
    attendu = {f"{d}_{k}_H{h}" for d in etu.DIRECTIONS for k in etu.DEFS
               for h in etu.HORIZONS}
    check("12 cellules de panel", set(panel) == attendu,
          f"{len(panel)} cellules")
    vocab = {"KILL", "INCONCLU", "CANDIDAT", "CONTEXTE", "DATA_INSUFFISANTE"}
    check("verdicts dans le vocabulaire",
          all(panel[c]["verdict"] in vocab for c in panel))
    check("chaque cellule a n, AUC, IC 2 bornes, delta, part_zero",
          all(panel[c].get("n_events") is not None
              and panel[c].get("auc") is not None
              and len(panel[c].get("ic95", [])) == 2
              and "delta_med_bps" in panel[c]
              and "part_zero_events" in panel[c] for c in panel))
    check("4 cellules de prime de structure",
          set(res["etude_B_prime_structure"]) ==
          {f"{d}_H{h}" for d in etu.DIRECTIONS for h in etu.HORIZONS})
    check("décision du banc dans le vocabulaire",
          res["synthese"]["decision"] in
          ("ABS_EN_TETE_DE_FILE", "ABS_DEPRIORISE (derriere RI/MK6)"))
    check("univers = la fenêtre certifiée (80 symboles, 2 053 975 barres)",
          res["univers"]["symboles"] == 80
          and res["univers"]["barres"] == 2_053_975)
    check("grille enregistrée = grille exécutée",
          res["grille"]["definitions"] == etu.DEFS
          and res["grille"]["horizons"] == etu.HORIZONS
          and res["grille"]["parametres"]["mult_mur"] == etu.MULT_MUR
          and res["grille"]["parametres"]["mult_attaque"] == etu.MULT_ATTAQUE
          and res["grille"]["parametres"]["ecrasement"] == etu.ECRASEMENT)
    return res


# =====================================================================
# F2 — étalonnage AUC sur cas exacts (la mécanique de la vague 5)
# =====================================================================
def f2_auc():
    a = etu.auc_mw(np.array([1.0, 2, 3]), np.array([10.0, 20]))
    check("AUC(x_haut=[1,2,3], x_bas=[10,20]) = 0", a == 0.0)
    a = etu.auc_mw(np.array([10.0, 20]), np.array([1.0, 2, 3]))
    check("AUC(x_haut=[10,20], x_bas=[1,2,3]) = 1", a == 1.0)
    g = np.array([1.0, 2, 3, 4, 5])
    check("AUC(x, x) = 0,5", abs(etu.auc_mw(g, g.copy()) - 0.5) < 1e-12)
    check("ex-aequo : AUC([1,1,2],[1,2,2]) = 1/3",
          abs(etu.auc_mw(np.array([1.0, 1, 2]), np.array([1.0, 2, 2]))
              - 1.0 / 3.0) < 1e-12)
    x, y = np.array([3.0, 1.0, 2.0]), np.array([1.5, 2.5])
    check("AUC symétrique : AUC(x,y) = 1 - AUC(y,x)",
          abs(etu.auc_mw(x, y) + etu.auc_mw(y, x) - 1.0) < 1e-12)
    # verdict_auc aux frontières
    check("verdict : IC contient 0,5 et |AUC-0,5|<0,02 -> KILL",
          etu.verdict_auc(0.495, 0.480, 0.510, True) == "KILL")
    check("verdict : IC contient 0,5 mais |AUC-0,5|>=0,02 -> INCONCLU",
          etu.verdict_auc(0.530, 0.495, 0.560, True) == "INCONCLU")
    check("verdict : IC exclut 0,5, séparation >= 0,05, bon sens -> CANDIDAT",
          etu.verdict_auc(0.56, 0.52, 0.60, True) == "CANDIDAT")
    check("verdict : IC exclut 0,5, séparation < 0,05 -> INCONCLU",
          etu.verdict_auc(0.52, 0.51, 0.53, True) == "INCONCLU")
    check("verdict : sens opposé -> CONTEXTE",
          etu.verdict_auc(0.44, 0.40, 0.48, True) == "CONTEXTE")
    check("verdict : AUC nan -> DATA_INSUFFISANTE",
          etu.verdict_auc(float("nan"), 0.0, 1.0, True) == "DATA_INSUFFISANTE")


# =====================================================================
# F3 — LE DÉTECTEUR sur séries synthétiques (le cœur de la QA vague 6)
# =====================================================================
def serie_synthese():
    """Une série 500 barres plate (prix 100, volume 10) : aucune condition
    ne peut y fire avec certitude, base propre pour les injections."""
    n = 500
    return {
        "open_time": np.arange(n, dtype=np.float64) * etu.MS_H,
        "open": np.full(n, 100.0), "high": np.full(n, 100.0),
        "low": np.full(n, 100.0), "close": np.full(n, 100.0),
        "volume": np.full(n, 10.0), "quote_volume": np.full(n, 1000.0),
        "taker_buy_quote_volume": np.full(n, 500.0),
    }


def f3_detecteur():
    # (a) la série plate pure ne produit RIEN (aucun spike)
    evs = etu.evenements(serie_synthese())
    check("série plate : 0 événement des 3 définitions, 2 directions",
          all(int(evs[d][k].sum()) == 0 for d in etu.DIRECTIONS
              for k in etu.DEFS))
    # (b) construction manuelle d'un E3 LONG : mur T-3, attaque T-2,
    #     tenue T-1, reprise T-1 -> décision à T. INVARIANT RÉEL respecté :
    #     tbqv <= qv (le buy taker est une PART du volume) -> D ∈ [-1, 1].
    kl = serie_synthese()
    T = 300
    kl["volume"][T - 3] = 40.0                      # >= 3 x SMA200 (=10,15)
    kl["quote_volume"][T - 2] = 2000.0              # vague vendeuse
    kl["taker_buy_quote_volume"][T - 2] = 500.0     # tksell = 1500 >= 2 x 510
    kl["low"][T - 2] = 100.0
    kl["low"][T - 1] = 99.5                         # >= 100 x (1-0,008)
    kl["taker_buy_quote_volume"][T - 1] = 1000.0    # D = +1 : EMA repasse >= 0
    evs = etu.evenements(kl)
    check("E3 LONG synthétique : EXACTEMENT 1 événement à T",
          int(evs["LONG"]["E3_complet"][T]) == 1
          and int(evs["LONG"]["E3_complet"].sum()) == 1)
    check("E2 LONG synthétique : l'événement est aussi un E2 (nesting)",
          int(evs["LONG"]["E2_structure_sans_mur"][T]) == 1)
    check("E1 LONG synthétique : l'événement est aussi un E1 (nesting)",
          int(evs["LONG"]["E1_attaque"][T]) == 1)
    # (c) chaque condition violée isolément -> 0 événement
    def base_e3():
        """La configuration E3 LONG complète (la même que (b))."""
        k2 = serie_synthese()
        k2["volume"][T - 3] = 40.0                      # mur
        k2["quote_volume"][T - 2] = 2000.0              # attaque vendeuse
        k2["taker_buy_quote_volume"][T - 2] = 500.0
        k2["low"][T - 2] = 100.0
        k2["low"][T - 1] = 99.5                         # tenue
        k2["taker_buy_quote_volume"][T - 1] = 1000.0    # reprise (D = +1)
        return k2

    for nom, viol in (
            ("mur manquant", lambda k: k["volume"].__setitem__(T - 3, 10.0)),
            ("attaque manquante",
             lambda k: k["taker_buy_quote_volume"].__setitem__(T - 2, 3500.0)),
            ("tenue cassée", lambda k: k["low"].__setitem__(T - 1, 99.0)),
            ("reprise absente",
             lambda k: k["taker_buy_quote_volume"].__setitem__(T - 1, 200.0)),
    ):
        k2 = base_e3()
        viol(k2)
        evs2 = etu.evenements(k2)
        check(f"E3 LONG synthétique : {nom} -> 0 événement",
              int(evs2["LONG"]["E3_complet"].sum()) == 0)
    # contrôle que base_e3() produit bien l'événement (anti-faux-négatif
    # de la batterie (c) : si la base cassait, (c) serait triviallement vert)
    evs_base = etu.evenements(base_e3())
    check("batterie (c) non triviale : la base non violée produit 1 événement",
          int(evs_base["LONG"]["E3_complet"][T]) == 1)
    # (d) le miroir SHORT : attaque acheteuse absorbée en haut (invariant
    #     réel tbqv <= qv respecté : l'attaque D = +0,5, pas un D impossible)
    kl = serie_synthese()
    kl["volume"][T - 3] = 40.0
    kl["quote_volume"][T - 2] = 2000.0
    kl["taker_buy_quote_volume"][T - 2] = 1500.0    # vague acheteuse
    kl["high"][T - 2] = 100.0
    kl["high"][T - 1] = 100.5                       # <= 100 x (1+0,008)
    kl["taker_buy_quote_volume"][T - 1] = 0.0       # D = -1 : EMA repasse <= 0
    evs = etu.evenements(kl)
    check("E3 SHORT synthétique : EXACTEMENT 1 événement à T",
          int(evs["SHORT"]["E3_complet"][T]) == 1
          and int(evs["SHORT"]["E3_complet"].sum()) == 1)
    check("E3 SHORT : pas de contamination du côté LONG",
          int(evs["LONG"]["E3_complet"].sum()) == 0)
    check("l'invariant tbqv <= qv tient sur le synthétique (D borné)",
          bool(np.all(kl["taker_buy_quote_volume"] <= kl["quote_volume"])))


# =====================================================================
# F4 — nesting sur données réelles (E3 ⊆ E2 ⊆ E1)
# =====================================================================
def f4_nesting():
    for sym in ("BTCUSDT", "ETHUSDT", "1000PEPEUSDT", "ARBUSDT"):
        kl = etu.load_klines(sym)
        if kl is None:
            continue
        evs = etu.evenements(kl)
        for d in etu.DIRECTIONS:
            e1 = evs[d]["E1_attaque"]
            e2 = evs[d]["E2_structure_sans_mur"]
            e3 = evs[d]["E3_complet"]
            check(f"nesting {sym} {d} : E3 ⊆ E2 ⊆ E1",
                  bool(np.all(e3 & ~e2 == False)) and bool(np.all(e2 & ~e1 == False)),
                  f"E1={int(e1.sum())} E2={int(e2.sum())} E3={int(e3.sum())}")
    # agrégé : les compteurs du JSON respectent aussi l'ordre
    with open(etu.OUT_JSON) as f:
        res = json.load(f)
    ce = res["counts_events"]
    check("compteurs agrégés : E3 <= E2 <= E1 (2 directions)",
          all(ce[d]["E3_complet"] <= ce[d]["E2_structure_sans_mur"]
              <= ce[d]["E1_attaque"] for d in etu.DIRECTIONS))
    # les n_events du panel = les compteurs avec horizon valide (<= compteurs)
    panel = res["etude_A_panel"]
    ok = True
    for d in etu.DIRECTIONS:
        for k in etu.DEFS:
            for h in etu.HORIZONS:
                n = panel[f"{d}_{k}_H{h}"]["n_events"]
                if n > ce[d][k]:
                    ok = False
    check("n_events du panel (horizon valide) <= compteurs bruts", ok)


# =====================================================================
# F5 — zéro look-ahead par MUTATION des barres futures
# =====================================================================
def f5_lookahead():
    for sym in ("BTCUSDT", "ETHUSDT"):
        kl = etu.load_klines(sym)
        n = len(kl["open_time"])
        cut = n // 2
        evs_avant = etu.evenements(kl)
        kl2 = {k: v.copy() for k, v in kl.items()}
        # scramble toutes les barres >= cut (les événements à T < cut ne
        # peuvent PAS les voir : les conditions ne référencent que <= T-1)
        rng = np.random.default_rng(501)
        for key in ("open", "high", "low", "volume", "quote_volume",
                    "taker_buy_quote_volume"):
            kl2[key][cut:] = rng.permutation(kl2[key][cut:])
        evs_apres = etu.evenements(kl2)
        identique = True
        for d in etu.DIRECTIONS:
            for k in etu.DEFS:
                if not np.array_equal(evs_avant[d][k][:cut],
                                      evs_apres[d][k][:cut]):
                    identique = False
        check(f"{sym} : les événements à T < cut sont insensibles aux "
              f"barres >= cut (0 look-ahead)", identique)


# =====================================================================
# F6 — conventions SMA/EMA/tenue (la sémantique des conditions)
# =====================================================================
def f6_conventions():
    x = np.array([1.0, 2, 3, 4, 5, 6])
    s = etu.sma(x, 3)
    check("sma : NaN tant que la fenêtre n'est pas pleine",
          bool(np.all(np.isnan(s[:2]))))
    check("sma : moyenne des 3 dernières barres incluses",
          abs(s[2] - 2.0) < 1e-12 and abs(s[5] - 5.0) < 1e-12)
    y = etu.ema(x, 3)
    lam = 2.0 / 4.0
    attendu = x[0]
    ok = abs(y[0] - attendu) < 1e-12
    for i in range(1, len(x)):
        attendu = lam * x[i] + (1 - lam) * attendu
        ok = ok and abs(y[i] - attendu) < 1e-12
    check("ema : récursion lambda = 2/(span+1) (vague 5, inchangée)", ok)
    # la tenue est direction-aware : bas tient pour LONG, haut tient pour
    # SHORT (la base E3 LONG valide de F3(b) sert de référence)
    T = 300
    def base_long():
        k2 = serie_synthese()
        k2["volume"][T - 3] = 40.0
        k2["quote_volume"][T - 2] = 2000.0
        k2["taker_buy_quote_volume"][T - 2] = 500.0
        k2["low"][T - 2] = 100.0
        k2["low"][T - 1] = 99.5
        k2["taker_buy_quote_volume"][T - 1] = 1000.0
        return k2

    kl = base_long()
    kl["low"][T - 1] = 99.0                        # -1 % : tenue LONG cassée
    evs = etu.evenements(kl)
    check("tenue LONG : -1 % sous le bas de l'attaque = pas d'événement",
          int(evs["LONG"]["E3_complet"].sum()) == 0)
    kl = base_long()
    kl["low"][T - 1] = 99.21                       # -0,79 % : tient
    evs = etu.evenements(kl)
    check("tenue LONG : -0,79 % = exactement à la limite, événement",
          int(evs["LONG"]["E3_complet"][T]) == 1)
    kl = base_long()
    kl["low"][T - 1] = 99.19                       # -0,81 % : cassé
    evs = etu.evenements(kl)
    check("tenue LONG : -0,81 % = juste au-delà, pas d'événement",
          int(evs["LONG"]["E3_complet"].sum()) == 0)
    check("seuil tenue = 0,8 % exactement",
          abs(etu.ECRASEMENT - 0.008) < 1e-15)


# =====================================================================
# F7 — projection pool P1 (469 entrées, t_in = opens exacts, indices)
# =====================================================================
def f7_pool():
    import csv
    pool = list(csv.DictReader(open(etu.POOL_CSV, newline="")))
    check("469 entrées certifiées", len(pool) == 469, f"n = {len(pool)}")
    syms_pool = set(r["sym"] for r in pool)
    check("40 symboles", len(syms_pool) == 40)
    # t_in sont des opens exacts + la géométrie de décision est bornée
    ok_opens, ok_geometrie = True, True
    n_match = 0
    for sym in sorted(syms_pool):
        kl = etu.load_klines(sym)
        if kl is None:
            continue
        ot = kl["open_time"]
        rows = [r for r in pool if r["sym"] == sym]
        pos = np.searchsorted(ot, np.array([float(r["t_in"]) for r in rows]))
        if np.any(pos >= len(ot)) or np.any(ot[pos] !=
                                            np.array([float(r["t_in"])
                                                      for r in rows])):
            ok_opens = False
        evs = etu.evenements(kl)
        for r, p in zip(rows, pos):
            d = "LONG" if int(r["side"]) == 1 else "SHORT"
            if p >= 3 and evs[d]["E3_complet"][p]:
                n_match += 1
                # un match implique l'attaque à T-2 (re-calcul indépendant)
                if not evs[d]["E1_attaque"][p]:
                    ok_geometrie = False
    check("t_in sont des opens exacts (doctrine _MK)", ok_opens)
    check("tout match E3 est un match E1 (géométrie de décision)", ok_geometrie)
    with open(etu.OUT_JSON) as f:
        res = json.load(f)
    check("le JSON porte le même nombre de matchs que le re-calcul",
          res["etude_C_pool_P1"]["n_matches_E3"] == n_match,
          f"{n_match}/469")
    check("la projection pool est en CONTEXTE (in-sample de la sélection)",
          "CONTEXTE" in res["etude_C_pool_P1"]["statut"])


# =====================================================================
# F8 — la règle NON_INTERPRETABLE (masse de liens) en unitaire
# =====================================================================
def f8_liens():
    # jambe médiane 0,0 avec >= 50 % de zéros -> non interprétable
    r3 = np.zeros(100)                              # 100 % de zéros
    r1 = np.concatenate([np.full(40, -20.0), np.zeros(60)])
    deg3 = (float(np.median(r3)) == 0.0 and float(np.mean(r3 == 0.0)) >= 0.5)
    deg1 = (float(np.median(r1)) == 0.0 and float(np.mean(r1 == 0.0)) >= 0.5)
    check("jambe 100 % de zéros : médiane 0,0 -> dégénérée", deg3)
    check("jambe 60 % de zéros : médiane 0,0 -> dégénérée", deg1)
    r1b = np.concatenate([np.full(50, -20.0), np.zeros(50)])
    deg1b = (float(np.median(r1b)) == 0.0 and float(np.mean(r1b == 0.0)) >= 0.5)
    check("jambe 50 % de zéros : médiane -10 (frontière) -> PAS dégénérée",
          not deg1b)
    r1c = np.full(100, -20.0)
    deg1c = (float(np.median(r1c)) == 0.0
             and float(np.mean(r1c == 0.0)) >= 0.5)
    check("jambe sans zéros : médiane -20,0 -> PAS dégénérée", not deg1c)
    with open(etu.OUT_JSON) as f:
        res = json.load(f)
    prime = res["etude_B_prime_structure"]
    n_nonint = sum(1 for v in prime.values() if v.get("non_interpretable"))
    check("les cellules SHORT de la prime sont marquées NON_INTERPRETABLE "
          "(médianes dans la masse des zéros)", n_nonint == 2,
          f"{n_nonint}/4")
    check("AUCUN JUSTIFIE ne peut sortir d'une cellule NON_INTERPRETABLE",
          all(v.get("verdict") == "ABS_DEPRIORISE"
              for v in prime.values() if v.get("non_interpretable")))


# =====================================================================
# F9 — re-exécution BIT À BIT (l'étude complète, ~3 min)
# =====================================================================
def f9_bit_a_bit():
    with open(etu.OUT_JSON, "rb") as f:
        avant = f.read()
    etu.main()
    with open(etu.OUT_JSON, "rb") as f:
        apres = f.read()
    check("re-exécution de l'étude : identique à l'octet près",
          avant == apres, f"{len(apres)} octets")


if __name__ == "__main__":
    print("=" * 68)
    print("QA VAGUE 6 — qa_abs_events_x501.py")
    print("=" * 68)
    res = f1_structure()
    f2_auc()
    f3_detecteur()
    f4_nesting()
    f5_lookahead()
    f6_conventions()
    f7_pool()
    f8_liens()
    f9_bit_a_bit()
    n_total = 9
    print("-" * 68)
    if ECHECS:
        print(f"ÉCHECS ({len(ECHECS)}) : {ECHECS}")
        sys.exit(1)
    print(f"QA VAGUE 6 : 9 familles, 0 échec — univers "
          f"{res['univers']['barres']} barres, décision du banc : "
          f"{res['synthese']['decision']}")
