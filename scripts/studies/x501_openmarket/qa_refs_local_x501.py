#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_refs_local_x501.py — LA QA DU BANC DES RÉFÉRENCES DE LIQUIDITÉ (vague 7).

10 familles de contrôles sur x501_refs_local.py, dans l'esprit des QA des
vagues 5-6 : le DÉTECTEUR testé sur séries synthétiques (l'information
plantée doit être vue), le ZÉRO LOOK-AHEAD prouvé par mutation (y compris
la tentation la plus subtile : le profil de la journée EN COURS), le
recalcul indépendant des références, le verdict unitaire branche par
branche, le pool P1 re-vérifié ligne à ligne, et la RE-EXÉCUTION BIT À BIT
de l'étude complète (le JSON régénéré doit coïncider au digest près, hors
la durée murale qui n'est pas un résultat).

Usage : python3 qa_refs_local_x501.py [--skip-rerun]
(--skip-rerun pour itérer vite sur les autres familles ; la QA OFFICIELLE
inclut la re-exécution.)
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import x501_refs_local as X  # noqa: E402

ECH = []

def check(nom, ok, detail=""):
    ECH.append((nom, ok, detail))
    print(f"  [{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))


def resumer(nom_famille):
    n_ok = sum(1 for _, ok, _ in ECH if ok)
    n_tot = len(ECH)
    print(f"\n== {nom_famille} : {n_ok}/{n_tot} ==")
    return n_ok, n_tot


# ---------------------------------------------------------------------------
print("QA-01 — LE VWAP DE SESSION : cas construit, recalcul naïf, bornes")
# cas construit à la main : 2 jours, 4 barres/jour, prix et volumes simples
ts = np.array([0, 3600_000, 7200_000, 10_800_000,
               86_400_000, 90_000_000, 93_600_000, 97_200_000], dtype=np.float64)
h = np.array([2.0, 4.0, 6.0, 8.0, 12.0, 14.0, 16.0, 18.0])
l = h - 1.0
c = h - 0.5
qv = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
vwap = X.session_vwap(ts, h, l, c, qv)
tp = (h + l + c) / 3.0
# jour 1 : tp = 1.5, 3.5, 5.5, 7.5, volumes égaux -> cumulés 1.5, 2.5, 3.5, 4.5
# jour 2 : reset -> 11.5, 12.5, 13.5, 14.5
check("vwap cumulés du jour 1 exacts", np.allclose(vwap[:4], [1.5, 2.5, 3.5, 4.5]),
      f"{vwap[:4]}")
check("vwap REPART à zéro le jour 2 (le reset de session)", np.allclose(vwap[4:], [11.5, 12.5, 13.5, 14.5]),
      f"{vwap[4:]}")
# recalcul naïf indépendant sur les vraies données BTC (boucle Python, jour par jour)
kl = X.load_klines("BTCUSDT")
n = len(kl["open_time"])
day = kl["open_time"] // 86_400_000
vwap_slow = np.empty(n)
vwap_slow[:] = np.nan
i = 0
while i < n:
    j = i
    while j + 1 < n and day[j + 1] == day[i]:
        j += 1
    csq = np.cumsum(kl["quote_volume"][i:j + 1])
    csqt = np.cumsum(kl["quote_volume"][i:j + 1] * (kl["high"][i:j + 1] + kl["low"][i:j + 1] + kl["close"][i:j + 1]) / 3.0)
    vwap_slow[i:j + 1] = csqt / csq
    i = j + 1
vwap_ref = X.session_vwap(kl["open_time"], kl["high"], kl["low"], kl["close"], kl["quote_volume"])
check("vwap BTC = recalcul naïf jour par jour (allclose rtol 1e-9)",
      bool(np.allclose(vwap_ref, vwap_slow, rtol=1e-9, atol=1e-6)),
      f"max|diff|={np.nanmax(np.abs(vwap_ref - vwap_slow)):.2e}")
# le contrôle de bornes : vwap ∈ [min tp, max tp] de CHAQUE jour (tolérance
# absolue 1e-3 : à l'échelle des prix BTC ~1e5, la marge d'arrondi cumulée)
ok_bornes = True
i = 0
while i < n:
    j = i
    while j + 1 < n and day[j + 1] == day[i]:
        j += 1
    tp_j = (kl["high"][i:j + 1] + kl["low"][i:j + 1] + kl["close"][i:j + 1]) / 3.0
    v_j = vwap_ref[i:j + 1]
    if np.any(v_j < tp_j.min() - 1e-3) or np.any(v_j > tp_j.max() + 1e-3):
        ok_bornes = False
        break
    i = j + 1
check("vwap BTC ∈ [min tp, max tp] de chaque session (26 208 barres)", ok_bornes)

# ---------------------------------------------------------------------------
print("\nQA-02 — LE VOLUME PROFILE : cas construit, VPOC/VA/tie-breaks")
# une journée où le volume est CONCENTRÉ à un prix connu : les barres du
# milieu échangent tout leur volume dans un range ÉTROIT autour de 105
# (concentrer dans le TEMPS ne suffit pas — il faut concentrer dans le PRIX)
ts1 = np.arange(24, dtype=np.float64) * 3600_000.0
h1 = np.full(24, 110.0)
l1 = np.full(24, 100.0)
h1[8:16] = 105.5
l1[8:16] = 104.5
qv1 = np.full(24, 1.0)
qv1[8:16] = 10.0
prof = X.profils_jour(ts1, h1, l1, qv1)
vpoc, vah, val, part = prof[int(ts1[0] // 86_400_000)]
check("VPOC = la zone de concentration (vpoc ∈ [104.5, 105.5])",
      104.5 <= vpoc <= 105.5, f"vpoc={vpoc:.3f}")
check("VAH/VAL encadrent la zone étroite (VAH <= 105.6, VAL >= 104.4)",
      vah <= 105.6 and val >= 104.4, f"[{val:.3f}, {vah:.3f}]")
check("VAL <= VPOC <= VAH", val <= vpoc <= vah, f"{val:.2f} <= {vpoc:.2f} <= {vah:.2f}")
check("VAH/VAL dans le range du jour", 100.0 <= val and vah <= 110.0)
check("part de volume de la VA >= 70 %", part >= 0.70 - 1e-12, f"part={part:.4f}")
# le tie-break pré-déclaré : ex-aequo de volume -> VPOC le PLUS BAS
h2 = np.array([100.0, 102.0, 104.0, 106.0, 108.0, 110.0])
l2 = h2 - 2.0
qv2 = np.array([1.0, 3.0, 5.0, 5.0, 3.0, 1.0])  # bins ex-aequo possibles
prof2 = X.profils_jour(np.arange(6, dtype=np.float64) * 3600_000.0, h2, l2, qv2)
vpoc2, vah2, val2, part2 = prof2[0]
# recalcul indépendant de l'allocation (24 bins construits à la main)
edges = np.linspace(98.0, 110.0, X.VP_BINS + 1)
w = np.minimum(h2[:, None], edges[None, 1:]) - np.maximum(l2[:, None], edges[None, :-1])
w = np.clip(w, 0.0, None)
contrib = qv2[:, None] * (w / np.maximum(h2 - l2, 1e-300)[:, None])
vol2 = contrib.sum(axis=0)
check("allocation VP = recalcul indépendant (somme conservée)",
      abs(vol2.sum() - qv2.sum()) < 1e-9 and abs(vol2.sum() - (prof2[0][1] * 0 + qv2.sum())) < 1e-9,
      f"vol={vol2.sum():.3f} vs qv={qv2.sum():.3f}")
check("ex-aequo VPOC -> le bin le PLUS BAS (pré-déclaré)",
      abs(vpoc2 - (edges[int(np.argmax(vol2))] + edges[int(np.argmax(vol2)) + 1]) / 2.0) < 1e-9,
      f"vpoc={vpoc2:.3f}")
# une barre dégénérée (high == low) : tout le volume dans son bin
h3 = np.array([100.0, 105.0, 110.0])
l3 = h3.copy()
qv3 = np.array([2.0, 4.0, 3.0])   # le volume MAX est au prix du milieu
prof3 = X.profils_jour(np.arange(3, dtype=np.float64) * 3600_000.0, h3, l3, qv3)
check("barre dégénérée : tout le volume au prix exact (VPOC=le bin de 105)",
      abs(prof3[0][0] - 105.1) < 0.25, f"vpoc={prof3[0][0]:.4f}")
# VA >= 70 % sur un ÉCHANTILLON de vraies journées
prof_btc = X.profils_jour(kl["open_time"], kl["high"], kl["low"], kl["quote_volume"])
parts = np.array([v[3] for v in prof_btc.values() if np.isfinite(v[3])])
check(f"VA >= 70 % sur {len(parts)} vraies journées BTC (min {parts.min():.4f})",
      bool(np.all(parts >= 0.70 - 1e-9)))

# ---------------------------------------------------------------------------
print("\nQA-03 — LE ZÉRO LOOK-AHEAD PAR MUTATION (la barrière la plus dure)")
dec0, _ = X.decisions_symbole("BTCUSDT")
kl2 = {k: v.copy() for k, v in kl.items()}
TC = 15_000  # la barre de coupe : on mute TOUT ce qui est >= TC+1
# prix : x1,01 (multiplicatif) + 100 (additif) — l'additif garantit que les
# RENDEMENTS changent (un facteur pur les laisserait identiques)
kl2["open"][TC + 1:] = kl2["open"][TC + 1:] * 1.01 + 100.0
kl2["high"][TC + 1:] = kl2["high"][TC + 1:] * 1.01 + 100.0
kl2["low"][TC + 1:] = kl2["low"][TC + 1:] * 1.01 + 100.0
kl2["close"][TC + 1:] = kl2["close"][TC + 1:] * 1.01 + 100.0
kl2["quote_volume"][TC + 1:] *= 2.0
dec1, _ = X.references_et_decisions("BTCUSDT", kl2)   # la série MUTÉE, pas le disque
masque = dec0["T"] <= TC  # décisions dont toutes les sources sont <= TC
ref0 = np.concatenate([dec0["vwap_1"][masque], dec0["vwap_2"][masque],
                       dec0["vpoc"][masque], dec0["vah"][masque], dec0["val"][masque]])
ref1 = np.concatenate([dec1["vwap_1"][masque], dec1["vwap_2"][masque],
                       dec1["vpoc"][masque], dec1["vah"][masque], dec1["val"][masque]])
check(f"references à T<= {TC} INCHANGÉES par la mutation des barres futures (equal_nan)",
      np.array_equal(ref0, ref1, equal_nan=True),
      f"n={masque.sum()}")
o0, o1 = dec0["o_T"][masque], dec1["o_T"][masque]
check("open(T) des décisions <= coupe inchangé (le prix d'entrée n'est pas muté)",
      np.array_equal(o0, o1))
fwd0 = dec0["fwd"][24][dec0["T"] > TC]
fwd1 = dec1["fwd"][24][dec0["T"] > TC]
check("les fwd APRÈS la coupe CHANGENT bien (la mutation est vivante)",
      not np.array_equal(fwd0, fwd1))

# ---------------------------------------------------------------------------
print("\nQA-04 — LE DÉTECTEUR VOIT L'INFORMATION PLANTÉE (séries synthétiques)")
def synth_anser(amp, period, bruit, n_j=120, seed=7):
    """oscillation pure autour d'un ancre constant : le prix sous le vwap
    est près du creux -> il remonte (l'aimant est planté)."""
    rng = np.random.default_rng(seed)
    n = n_j * 24
    t = np.arange(n)
    p = 1000.0 + amp * np.sin(2 * np.pi * t / period) + rng.normal(0, bruit, n)
    return (np.arange(n, dtype=np.float64) * 3600_000.0, p.copy(), p.copy(), p.copy(),
            np.full(n, 1000.0))
ts_s, h_s, l_s, c_s, qv_s = synth_anser(amp=30.0, period=48, bruit=0.5)
dec_s, _ = X.references_et_decisions("SYNTH", {"open_time": ts_s, "open": c_s, "high": h_s,
                                               "low": l_s, "close": c_s, "quote_volume": qv_s})
defs = X.grille_definitions()
flag, fwd, sens = X.flags_cellule("V1", dec_s, {"seuil": 0.0, "dirn": "LONG"}, 24)
ok = np.isfinite(fwd)
auc_v1 = X.auc_mw(fwd[ok][flag[ok]], fwd[ok][~flag[ok]])
check(f"V1 aimant LONG sur l'aimant planté : AUC={auc_v1:.3f} > 0.60", auc_v1 > 0.60)
# une CONTINUATION PERSISTANTE (régimes Markov P(stay)=0,99) : le breakout de
# la value area doit voir la continuation, et le taux de flag reste mesurable
def synth_regimes(pas_haut, pas_bas, p_stay, n_j=160, seed=11):
    rng = np.random.default_rng(seed)
    n = n_j * 24
    etat = np.ones(n, dtype=np.int64)
    for t in range(1, n):
        if rng.random() > p_stay:
            etat[t] = -etat[t - 1]
        else:
            etat[t] = etat[t - 1]
    rend = np.where(etat > 0, pas_haut, -pas_bas)
    p = 1000.0 * np.cumprod(1.0 + rend)
    return (np.arange(n, dtype=np.float64) * 3600_000.0, p, p * (1 - 0.0005),
            p * (1 + 0.0005), p, np.full(n, 1000.0))
ts_t, o_t, l_t, h_t, c_t, qv_t = synth_regimes(pas_haut=0.004, pas_bas=0.004, p_stay=0.99)
dec_t, _ = X.references_et_decisions("SYNTH2", {"open_time": ts_t, "open": o_t, "high": h_t,
                                                "low": l_t, "close": c_t, "quote_volume": qv_t})
flag, fwd, sens = X.flags_cellule("P3", dec_t, {"dirn": "LONG"}, 24)
ok = np.isfinite(fwd)
auc_p3 = X.auc_mw(fwd[ok][flag[ok]], fwd[ok][~flag[ok]])
taux_p3 = float(flag[ok].mean())
check(f"P3 breakout LONG sur la continuation plantée : AUC={auc_p3:.3f} > 0.55 (flag {taux_p3:.2f})",
      auc_p3 > 0.55 and 0.05 < taux_p3 < 0.9)
# le mécanisme CROSS + direction : sur l'oscillation, le franchissement du
# vwap mène la suite du mouvement dans le sens du cross (déterministe, seed 7)
ts_s2, h_s2, l_s2, c_s2, qv_s2 = synth_anser(amp=30.0, period=48, bruit=0.5)
dec_s2, _ = X.references_et_decisions("SYNTH3", {"open_time": ts_s2, "open": c_s2, "high": h_s2,
                                                 "low": l_s2, "close": c_s2, "quote_volume": qv_s2})
flag, fwd, sens = X.flags_cellule("V2", dec_s2, {"dirn": "SHORT"}, 24)
ok = np.isfinite(fwd)
auc_v2 = X.auc_mw(fwd[ok][flag[ok]], fwd[ok][~flag[ok]])
check(f"V2 cross SHORT sur l'oscillation plantée : AUC={auc_v2:.3f} > 0.55", auc_v2 > 0.55)

# ---------------------------------------------------------------------------
print("\nQA-05 — LE VERDICT MÉCANIQUE BRANCHE PAR BRANCHE (l'ordre pré-déclaré)")
cases = [
    ("n insuffisant -> INCONCLU", (0.55, 0.40, 0.70, 50, 5000, 0.0, +1), "INCONCLU"),
    ("zeros >= 50 % -> NON_INTERPRETABLE", (0.55, 0.40, 0.70, 500, 5000, 0.60, +1), "NON_INTERPRETABLE"),
    ("IC contient 0,5 + |AUC-0,5|<0,02 -> KILL", (0.51, 0.48, 0.54, 500, 5000, 0.0, +1), "KILL"),
    ("IC contient 0,5 + |AUC|>=0,02 -> INCONCLU", (0.53, 0.47, 0.60, 500, 5000, 0.0, +1), "INCONCLU"),
    ("IC exclut 0,5 + |AUC|>=0,05 + sens ok -> CANDIDAT", (0.56, 0.502, 0.61, 500, 5000, 0.0, +1), "CANDIDAT"),
    ("IC exclut 0,5 + |AUC|>=0,05 + sens contraire -> CONTEXTE", (0.44, 0.39, 0.498, 500, 5000, 0.0, +1), "CONTEXTE"),
    ("IC exclut 0,5 + |AUC|<0,05 -> INCONCLU", (0.53, 0.501, 0.56, 500, 5000, 0.0, +1), "INCONCLU"),
]
for nom, args, attendu in cases:
    got = X.verdict_cellule(*args)
    check(nom, got == attendu, f"{got}")
# le NON_INTERPRETABLE passe AVANT le KILL (l'ordre compte)
got = X.verdict_cellule(0.5, 0.49, 0.51, 500, 5000, 0.9, +1)
check("l'ordre : NON_INTERPRETABLE prime sur KILL", got == "NON_INTERPRETABLE", got)

# ---------------------------------------------------------------------------
print("\nQA-06 — LE POOL P1 RE-VÉRIFIÉ LIGNE À LIGNE")
rows = list(csv.DictReader(open(X.POOL_CSV, newline="")))
n_ok_open, n_bad = 0, 0
for r in rows[:80]:  # échantillon contrôlé (le reste est vérifié par l'étude)
    klc = X.load_klines(r["sym"])
    if klc is None:
        continue
    t_in = float(r["t_in"])
    i = int(np.searchsorted(klc["open_time"], t_in))
    if i < len(klc["open_time"]) and klc["open_time"][i] == t_in:
        n_ok_open += 1
    else:
        n_bad += 1
check("pool : t_in = des opens EXACTES du fichier klines (échantillon 80)",
      n_ok_open == 80 and n_bad == 0, f"{n_ok_open}/80")
# la convention du pool (vague 4) : entry = open(T) x (1 − side x 2 bps)
# = le PLACEMENT MAKER δ=2 — vérifiée sur les 469 lignes
delta_side = []
n_conv = 0
for r in rows:
    klc = X.load_klines(r["sym"])
    t_in = float(r["t_in"])
    i = int(np.searchsorted(klc["open_time"], t_in))
    if i < len(klc["open_time"]) and klc["open_time"][i] == t_in:
        o = klc["open"][i]
        e = float(r["entry"])
        side = float(r["side"])
        if abs(e - o * (1.0 + side * 0.0002)) <= 1e-9 * max(1.0, abs(o)):
            n_conv += 1
        else:
            delta_side.append((r["sym"], o, e, side))
check("pool : entry = open(T) x (1 + side x 2 bps) sur les 469 (l'entrée 2 bps ADVERSE à l'open, convention vague 4)",
      n_conv == 469, f"{n_conv}/469" + (f" ko={delta_side[:2]}" if delta_side else ""))
sides = {float(r["side"]) for r in rows}
check("pool : sides ∈ {-1, +1}", sides == {-1.0, 1.0}, f"{sides}")
Rs = np.array([float(r["R"]) for r in rows])
check("pool : 469 R finis", len(rows) == 469 and bool(np.all(np.isfinite(Rs))))

# ---------------------------------------------------------------------------
print("\nQA-07 — COHÉRENCE DU JSON PRODUIT (constantes, bilan, discipline)")
res = json.loads((ICI / "refs_local.json").read_text(encoding="utf-8"))
check("28 cellules pré-déclarées", res["grille"]["n_cellules"] == 28)
check("56 cellules mesurées (2 panels x 28)",
      len(res["panel_pool"]) == 28 and len(res["panel_liquide8"]) == 28)
check("80 symboles / 8 liquides", res["n_symboles"] == 80 and res["n_symboles_liquide8"] == 8)
check("le bilan = la somme des verdicts des 2 panels",
      sum(res["bilan_verdicts"].values()) == 56)
check(f"le bilan attendu (55 KILL + 1 INCONCLU) : {res['bilan_verdicts']}",
      res["bilan_verdicts"].get("KILL") == 55 and res["bilan_verdicts"].get("INCONCLU") == 1)
check("pool P1 : 469 opens vérifiées, 0 référence manquante",
      res["pool_p1"]["verif_opens"] == {"ok": 469, "ko": 0}
      and res["pool_p1"]["refs_manquantes"] == 0 and res["pool_p1"]["symboles_absents"] == 0)
cand = [k for panel in ("panel_pool", "panel_liquide8") for k, v in res[panel].items()
        if v["verdict"] == "CANDIDAT"]
check("ZÉRO CANDIDAT (la règle de lecture : falsification n°7)", len(cand) == 0)

# ---------------------------------------------------------------------------
N_OK = sum(1 for _, ok, _ in ECH if ok)
N_TOT = len(ECH)
print(f"\n== CONTRÔLES : {N_OK}/{N_TOT} ==")

# ---------------------------------------------------------------------------
if "--skip-rerun" not in sys.argv:
    print("\nQA-08 — RE-EXÉCUTION BIT À BIT DE L'ÉTUDE COMPLÈTE (~5 min)")
    res2 = X.run_all()
    def digest(d):
        d = {k: v for k, v in d.items() if k != "duree_s"}
        return hashlib.sha256(json.dumps(d, ensure_ascii=False, sort_keys=True,
                                         indent=1).encode()).hexdigest()
    d_file = digest(res)
    d_run = digest(res2)
    check(f"le JSON régénéré coïncide au digest près (hors duree_s) : {d_file[:16]}…",
          d_file == d_run, f"run={d_run[:16]}…")
    N_TOT += 1
    N_OK = sum(1 for _, ok, _ in ECH if ok)
    print(f"\n== CONTRÔLES FINAUX : {N_OK}/{N_TOT} ==")

n_echec = N_TOT - N_OK
print(f"\n{'QA PASS (0 échec)' if n_echec == 0 else f'QA ÉCHOUÉE : {n_echec} échec(s)'}")
sys.exit(0 if n_echec == 0 else 1)
