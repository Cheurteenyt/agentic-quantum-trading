#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_oi_ushape_x501.py — QA de la VAGUE 10 (banc de la forme en U de H_R1,
x501_oi_ushape_local.py).

Ce que la QA prouve, dans l'ordre :
  S1  la discipline est gravée dans le script (en-tête, constantes, panel,
      la discrimination vague 9 (MONOTONE) / vague 10 (FORME en U), le
      centre pré-déclaré à 0, la composition du verdict U) ;
  S2  la mécanique de rangs/AUC est exacte (cas construits à la main) ;
  S3  le bootstrap est déterministe (seed 501, bit à bit) ;
  S4  rolling_z est exact : amorçage NaN, cas à la main (L=3), std=0 -> NaN,
      contre-vérification contre la boucle naïve, convention temps ;
  S5  le score |z| et la sélection A2 : u = |s_full| cas à la main, le
      sous-échantillon A2 garde EXACTEMENT les scores < 0 ;
  S6  la COMPOSITION du verdict U tranchant sur les 5 branches (U VIVANT,
      KILL-U, NON ÉTABLI x3) ;
  D1  le DÉTECTEUR du U est vivant : une magnitude plantée en U dans le
      forward (les DEUX extrêmes de z) fait décoller A1 CANDIDAT (+1) ET
      A2 CANDIDAT (-1) — la composition conclut U VIVANT (la plomberie
      voit un U quand il existe) ;
  D2  le détecteur MONOTONE est REFUSÉ par la composition : une magnitude
      plantée monotone (croissante en z, strictement positive) fait
      décoller A2 dans le sens OPPOSÉ (AUC > 0,5 hors IC -> CONTEXTE) —
      la composition conclut KILL-U même si A1 décolle : le discriminant
      du côté bas refuse un U inexistant (la leçon anti double-dip) ;
  D3  le cas nul ne décolle pas (pas de batterie triviale) ;
  L1  le ZÉRO LOOK-AHEAD est prouvé par MUTATION des snapshots OI futurs
      (multiplicative ET additive) : les scores u_full ET s_full d'une
      décision passée ne bougent pas d'un bit ;
  L2  mutation des BARRES futures : les scores (qui ne lisent que l'OI)
      restent bit à bit ;
  L3  le snapshot SIMULTANÉ (t:00) n'est JAMAIS lu : le muter ne change
      aucun score d'aucune barre ;
  V1  les 4 branches du verdict mécanique tranchent exactement + la branche
      sens=0 (étude B) ne produit JAMAIS CANDIDAT, même sur séparation forte ;
  P1  le pool P1 conserve sa convention (469 entrées, t_in = open exact ;
      entry = open x (1 + side x 2 bps) re-vérifiée si data_x501 dispo) ;
  R1  sur data réelle : audit de collecte (dédup, gaps, snapshots absents,
      OI > 0) et RE-EXÉCUTION BIT À BIT de l'étude complète (digest).
Sans X501_OI_DIR, les blocs data (P1-entry, R1) sont sautés et comptés
comme tels (la QA reste PASS si 0 échec sur les contrôles exécutés).

Usage : python3 qa_oi_ushape_x501.py   (envs : X501_OI_DIR, X501_DATA_DIR)
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ETUDE = HERE / "x501_oi_ushape_local.py"
OI_DIR = Path(os.environ.get("X501_OI_DIR", HERE / "../../../data/x501_oi"))
DATA_DIR = Path(os.environ.get("X501_DATA_DIR", HERE / "../../../data/x501_1h"))
POOL_CSV = HERE / "pool_P1_entrees.csv"
JSON_ETUDE = HERE / "oi_ushape_local.json"

# digest bit à bit gravé après le premier run de l'étude (re-exécution R1)
SHA256_ATTENDU = "3f9fb7781eaeb4014f30f24c00dd36d36646137c7b19f67163e30dd502746020"

MS_H = 3_600_000

echecs = []
n_checks = 0
n_skips = 0


def chk(nom, cond, detail=""):
    global n_checks
    n_checks += 1
    if cond:
        print(f"  ok  {nom}")
    else:
        echecs.append(nom)
        print(f"  ECHEC {nom} {detail}")


def skip(nom):
    global n_skips
    n_skips += 1
    print(f"  SKIP {nom}")


# chargement du module d'étude (import par chemin)
spec = importlib.util.spec_from_file_location("x501_oi_ushape_local", ETUDE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

rng_global = np.random.default_rng(501)

print("S1 — discipline gravée dans le script")
src = ETUDE.read_text(encoding="utf-8")
chk("S1.1 en-tête pré-enregistrement daté", "pré-enregistrée le 01/10/2026" in src)
chk("S1.2 la discrimination vague 9 / vague 10 est gravée",
    "vague 9 : le NIVEAU du capital z_L(OI) testé MONOTONE" in src
    and "vague 10 : la FORME" in src)
chk("S1.3 grille gravée (lookbacks z)", "LOOKBACKS_Z = [720, 2160]" in src)
chk("S1.4 horizons figés", "HORIZONS = [24, 72]" in src)
chk("S1.5 pool L figé (hérité vague 9)", "POOL_L = 720" in src)
chk("S1.6 quantile strate extrême pré-déclaré", "POOL_Q_EXTR = 0.80" in src)
chk("S1.7 seed du domaine", "SEED = 501" in src)
chk("S1.8 seuils du critère inchangés",
    "AUC_MORTE = 0.02" in src and "AUC_CANDIDAT = 0.05" in src)
chk("S1.9 réduction bootstrap", "REDUCTION_BOOT = 50_000" in src)
chk("S1.10 étalon coûts", "COUT_AR_TAKER_BPS = 12.2" in src)
PANEL_12 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
            "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "APTUSDT", "1000PEPEUSDT"]
chk("S1.11 panel = 12 symboles v17 exacts", mod.SYMBOLS == PANEL_12)
chk("S1.12 le centre du U est pré-déclaré à 0 (limite L3)",
    "centre PRÉ-DÉCLARÉ" in src and "L3" in src)
chk("S1.13 la composition du verdict U est gravée",
    "COMPOSITION DU VERDICT U" in src and "composition_u" in src)
chk("S1.14 la règle A1 ET A2 est gravée",
    "A1 est CANDIDAT (sens +1) ET" in src)
chk("S1.15 l'interdiction du snapshot simultané est gravée",
    "n'est JAMAIS lu" in src)
chk("S1.16 pas de fill-forward silencieux", "Aucun fill-forward" in src)
chk("S1.17 std de population (ddof=0) gravée", "ddof=0" in src)
chk("S1.18 les cas dégénérés sont pré-déclarés", "CAS DÉGÉNÉRÉS PRÉ-DÉCLARÉS" in src)

print("S2 — mécanique de rangs / AUC exacte")
x = np.array([3.0, 1.0, 1.0, 2.0])
chk("S2.1 rangs moyens ex-aequo", np.allclose(mod.rangs_moyens(x), [4, 1.5, 1.5, 3]))
chk("S2.2 AUC séparation parfaite", mod.auc_mw(np.array([5., 6., 7.]), np.array([1., 2.])) == 1.0)
chk("S2.3 AUC anti-correlation", mod.auc_mw(np.array([1., 2.]), np.array([5., 6., 7.])) == 0.0)
chk("S2.4 cas mixte (1 paire gagnée sur 4 = 0,25)",
    abs(mod.auc_mw(np.array([1., 2.]), np.array([1.5, 2.5])) - 0.25) < 1e-12)
chk("S2.5 ex-aequo inter-groupes (P(=) comptée demi = 0,125)",
    abs(mod.auc_mw(np.array([1., 2.]), np.array([2., 3.])) - 0.125) < 1e-12)


def rangs_naifs(x):
    out = np.empty(len(x))
    for i, v in enumerate(x):
        out[i] = 1 + (x < v).sum() + 0.5 * ((x == v).sum() - 1)
    return out


xg = rng_global.normal(size=500)
xg[np.arange(0, 500, 7)] = 0.0  # blocs d'ex-aequo massifs
chk("S2.6 rangs_moyens == boucle naïve (500 pts, ex-aequo)",
    np.allclose(mod.rangs_moyens(xg), rangs_naifs(xg)))
a_, b_ = xg[:200] + 0.3, xg[200:]
ref_paires = (a_[:, None] > b_[None, :]).mean() + 0.5 * (a_[:, None] == b_[None, :]).mean()
chk("S2.7 AUC == comptage exact de paires (broadcasting)",
    abs(mod.auc_mw(a_, b_) - ref_paires) < 1e-12)

print("S3 — bootstrap déterministe (seed 501)")
f = rng_global.normal(size=4000)
fl = rng_global.random(4000) > 0.5
j = (np.arange(4000) // 24)
b1 = mod.bootstrap_flags(f, fl, j, 50, 501)
b2 = mod.bootstrap_flags(f, fl, j, 50, 501)
chk("S3.1 même seed -> bit à bit", bool(np.array_equal(b1, b2)))
b3 = mod.bootstrap_flags(f, fl, j, 50, 502)
chk("S3.2 autre seed -> différent", not np.array_equal(b1, b3))
chk("S3.3 borne AUC [0,1]", float(b1.min()) >= 0.0 and float(b1.max()) <= 1.0)

print("S4 — rolling_z exact (noyau hérité de la vague 9)")
arr_c = np.full(40, 7.7)
zc = mod.rolling_z(arr_c, 10)
chk("S4.1 fenêtre plate -> std=0 -> NaN partout après amorçage",
    bool(np.all(np.isnan(zc[9:]))), f"{zc[9:12]}")
chk("S4.2 amorçage : les L-1 premières valeurs sont NaN",
    bool(np.all(np.isnan(zc[:9]))))
arr4 = np.array([1.0, 2.0, 3.0, 4.0])
z4 = mod.rolling_z(arr4, 3)
sd23 = np.sqrt(2.0 / 3.0)   # std population de [1,2,3]
chk("S4.3 cas à la main L=3 : z[2] = (3-2)/sqrt(2/3)",
    abs(z4[2] - 1.0 / sd23) < 1e-12, f"{z4[2]} vs {1.0/sd23}")
chk("S4.4 cas à la main L=3 : z[3] = (4-3)/sqrt(2/3)",
    abs(z4[3] - 1.0 / sd23) < 1e-12, f"{z4[3]}")
chk("S4.5 z[0..1] NaN (amorçage)", bool(np.all(np.isnan(z4[:2]))))
rngz = np.random.default_rng(501)
arrz = rngz.normal(size=600) * np.exp(rngz.normal(size=600) * 0.001) + 1.0
Lz = 90
zz = mod.rolling_z(arrz, Lz)
ok_nan = all(np.isnan(zz[k]) for k in range(Lz - 1))
n_ok, n_bad = 0, 0
for t in range(Lz - 1, 600):
    fen = arrz[t - Lz + 1:t + 1]
    m, sd = fen.mean(), fen.std(ddof=0)
    attendu = (arrz[t] - m) / sd if sd > 0 else np.nan
    if np.isnan(attendu):
        n_ok += 1 if np.isnan(zz[t]) else 0
    elif abs(zz[t] - attendu) < 1e-9:
        n_ok += 1
    else:
        n_bad += 1
chk("S4.6 rolling_z == boucle naïve (600 pts, L=90, ddof=0)", ok_nan and n_bad == 0,
    f"bad={n_bad}")
ot_t = np.arange(200, dtype=np.int64) * MS_H
arr_t = np.arange(200, dtype=np.float64)
s_full_t = np.full(200, np.nan)
s_full_t[1:] = mod.rolling_z(arr_t, 50)[:-1]
m_t = arr_t[100 - 50:100].mean()
sd_t = arr_t[100 - 50:100].std(ddof=0)
chk("S4.7 score[100] lit arr[50..99] (le snapshot 100:00 n'est JAMAIS lu)",
    abs(s_full_t[100] - (arr_t[99] - m_t) / sd_t) < 1e-12,
    f"{s_full_t[100]} vs {(arr_t[99]-m_t)/sd_t}")
arr_neg = np.array([1.0, 2.0, 3.0, np.nan, 5.0, 6.0, 7.0, 8.0])
zneg = mod.rolling_z(arr_neg, 3)
chk("S4.8 snapshot absent (NaN) -> score NaN propagé",
    bool(np.all(np.isnan(zneg[3:6]))), f"{zneg}")

print("S5 — le score |z| et la sélection A2 (le noyau NOUVEAU de la vague 10)")
s_demo = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
chk("S5.1 u = |s_full| cas à la main",
    np.array_equal(np.abs(s_demo), [2.0, 1.0, 0.0, 1.0, 2.0]))
fwd_demo = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
jours_demo = np.arange(5)
# le sous-échantillon A2 garde EXACTEMENT les scores strictement < 0
ok_a2 = (s_demo < 0) & np.isfinite(s_demo) & np.isfinite(fwd_demo)
chk("S5.2 la sélection A2 garde EXACTEMENT z < 0 (0 et positifs exclus)",
    ok_a2.tolist() == [True, True, False, False, False])
r_a2_demo = mod.cellule_panel(s_demo[ok_a2], np.abs(fwd_demo[ok_a2]),
                              jours_demo[ok_a2], "demo", -1)
# médiane de [−2, −1] = −1,5 (recalculée à la main — bug de cas corrigé)
chk("S5.3 la médiane de la cellule A2 est recalculée DANS le sous-échantillon",
    abs(r_a2_demo["mediane_score"] - (-1.5)) < 1e-12, f"{r_a2_demo['mediane_score']}")
# la dichotomie A2 : flag = z > médiane-négative (proche de 0). Cas U planté :
# le z TRÈS négatif (−2) porte |fwd| = 50 GRAND, le z proche de 0 (−1) porte
# |fwd| = 40 plus petit -> AUC(flag vs non-flag) = 0,0 (sens −1 confirmé)
# (premier jet du cas faux : |fwd| croissant avec z plantait un MONOTONE,
# AUC 1,0 — recalculé à la main, leçon des cas exacts vague 8)
fwd_u = np.array([50.0, 40.0, 30.0, 20.0, 10.0])
chk("S5.4 AUC A2 cas à la main (U planté : z très négatif = |fwd| grand -> AUC 0,0)",
    mod.auc_mw(np.abs(fwd_u[ok_a2][s_demo[ok_a2] > -1.5]),
               np.abs(fwd_u[ok_a2][s_demo[ok_a2] <= -1.5])) == 0.0)
# et le MIROIR monotone dans le même sous-échantillon : |fwd| croissant avec z
# -> l'AUC sort > 0,5 (le banc distingue les deux formes dans le même score)
chk("S5.5 AUC A2 miroir monotone (z très négatif = |fwd| petit -> AUC 1,0)",
    mod.auc_mw(np.abs(fwd_demo[ok_a2][s_demo[ok_a2] > -1.5]),
               np.abs(fwd_demo[ok_a2][s_demo[ok_a2] <= -1.5])) == 1.0)

print("S6 — la COMPOSITION du verdict U tranchant sur toutes les branches")
chk("S6.1 A1 CANDIDAT + A2 CANDIDAT(-1) -> U VIVANT",
    mod.composition_u("CANDIDAT", "CANDIDAT", 0.44) == "U VIVANT")
chk("S6.2 A1 CANDIDAT + A2 KILL -> U NON ÉTABLI (côté bas plat = monotone unilatéral)",
    mod.composition_u("CANDIDAT", "KILL", 0.51) == "U NON ÉTABLI")
chk("S6.3 A1 CANDIDAT + A2 CONTEXTE (AUC>0,5 hors IC) -> KILL-U (monotone par le côté bas)",
    mod.composition_u("CANDIDAT", "CONTEXTE", 0.55).startswith("KILL-U"))
chk("S6.4 A1 INCONCLU + A2 CANDIDAT -> U NON ÉTABLI (le gate 0,05 de A1 est exigé)",
    mod.composition_u("INCONCLU", "CANDIDAT", 0.44) == "U NON ÉTABLI")
chk("S6.5 A1 CANDIDAT + A2 CONTEXTE (AUC<0,5, cas théorique) -> U NON ÉTABLI",
    mod.composition_u("CANDIDAT", "CONTEXTE", 0.45) == "U NON ÉTABLI")
chk("S6.6 A1 KILL + A2 KILL -> U NON ÉTABLI",
    mod.composition_u("KILL", "KILL", 0.50) == "U NON ÉTABLI")
chk("S6.7 A1 CONTEXTE (sens opposé) + A2 CANDIDAT -> U NON ÉTABLI",
    mod.composition_u("CONTEXTE", "CANDIDAT", 0.44) == "U NON ÉTABLI")


# ------------------ pipeline synthétique partagé (D1/D2/D3/L1/L2/L3) -----------
def fabrique_panel(forme, seed=501, n=4800):
    """Un panel klines+OI synthétique où la MAGNITUDE du forward open->open
    H=24 est plantée selon la FORME pré-déclarée :
      "u"        : fwd_cible = 0,0008 + 0,0020 x |z| + bruit (toujours > 0)
                   — les DEUX extrêmes de z portent des grands mouvements,
                   le centre est calme : la forme en U de la vague 10 ;
      "monotone" : fwd_cible = 0,0030 + 0,0010 x z + bruit (STRICTEMENT
                   positif sur tout le support : z >= -4 -> 0,0030-0,0040
                   reste ~0, aucun rebond parasite du |.|) — la forme
                   monotone H_R1 de la vague 9 ;
      "nul"      : fwd_cible = 0,0010 + bruit, indépendant de z.
    Le NIVEAU d'OI porte z[t+1] DIRECTEMENT (OI[t] = base x (1 + ampl x
    z_shift[t] + bruit), z_shift[t] = z[t+1]) avec le décalage d'une barre
    de la vague 8 : le score lu à l'open de t (z du niveau calculé jusqu'à
    t-1) porte ainsi z[t], le MEME champ que le forward de t."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    infl = 0.0 if forme == "nul" else 1.0
    if forme == "u":
        fwd_cible = 0.0008 + 0.0020 * np.abs(z) + 0.0008 * rng.normal(size=n)
    elif forme == "monotone":
        fwd_cible = 0.0030 + 0.0010 * z + 0.0004 * rng.normal(size=n)
    else:
        fwd_cible = 0.0010 + 0.0008 * rng.normal(size=n)
    ot = np.arange(n, dtype=np.int64) * MS_H + 1_700_000_000_000
    op = np.empty(n)
    for r in range(24):
        idx = np.arange(r, n, 24)
        vals = [100.0 * (1 + 0.01 * rng.normal())]
        for t in idx[1:]:
            vals.append(vals[-1] * (1.0 + fwd_cible[t - 24]))
        op[idx] = vals
    z_shift = np.append(z[1:], z[-1])
    oi_val = 1_000_000.0 * (1.0 + 0.05 * infl * z_shift
                            + 0.01 * rng.normal(size=n))
    oi_ts = ot.copy()
    cl = op * (1.0 + 0.0002 * rng.normal(size=n))
    hi = np.maximum(op, cl) * (1 + np.abs(rng.normal(size=n)) * 0.0005)
    lo = np.minimum(op, cl) * (1 - np.abs(rng.normal(size=n)) * 0.0005)
    return ot, op, cl, hi, lo, oi_ts, oi_val, z


def scores_depuis_oi(ot, op, oi_ts, oi_val, L=240, H=24):
    """Le chemin EXACT du pipeline d'étude : snap -> rolling_z -> s_full
    (signé, convention temps stricte) -> u_full = |s_full| -> fwd. Le fwd
    est retourné SIGNÉ (les études appliquent |.| ou non). L réduit à 240
    pour le test (la plomberie est identique, l'amorçage plus court)."""
    arr = mod.snap_oi_sur_barres(ot, oi_ts, oi_val)
    n = len(ot)
    z = mod.rolling_z(arr, L)
    s_full = np.full(n, np.nan)
    s_full[1:] = z[:-1]
    u_full = np.abs(s_full)
    fwd = np.full(n, np.nan)
    fwd[:n - H] = (op[H:] - op[:n - H]) / op[:n - H] * 1e4
    return s_full, u_full, fwd


def cellules_u(s_full, u_full, fwd, jours):
    """Les DEUX cellules du banc U sur un panel synthétique (A1 joint,
    A2 côté bas) + la composition pré-déclarée."""
    ok = np.isfinite(u_full) & np.isfinite(fwd)
    r_a1 = mod.cellule_panel(u_full[ok], np.abs(fwd[ok]), jours[ok],
                             "test U joint", +1)
    ok2 = ok & (s_full < 0)
    r_a2 = mod.cellule_panel(s_full[ok2], np.abs(fwd[ok2]), jours[ok2],
                             "test côté bas", -1)
    compo = mod.composition_u(r_a1["verdict"], r_a2["verdict"], r_a2["auc"])
    return r_a1, r_a2, compo


print("D1 — le détecteur du U est vivant (magnitude plantée en U dans le forward)")
ot, op, cl, hi, lo, oi_ts, oi_val, z = fabrique_panel("u")
s_full, u_full, fwd = scores_depuis_oi(ot, op, oi_ts, oi_val)
jours = (ot // 86_400_000).astype(np.int64)
r_a1, r_a2, compo = cellules_u(s_full, u_full, fwd, jours)
chk("D1.1 A1 (joint) décolle CANDIDAT (sens +1, |AUC-0,5| >= 0,05)",
    r_a1["verdict"] == "CANDIDAT" and r_a1["auc"] > 0.55, f"auc={r_a1['auc']:.4f} v={r_a1['verdict']}")
chk("D1.2 A2 (côté bas) décolle CANDIDAT (sens -1, AUC < 0,45)",
    r_a2["verdict"] == "CANDIDAT" and r_a2["auc"] < 0.45, f"auc={r_a2['auc']:.4f} v={r_a2['verdict']}")
chk("D1.3 la composition conclut U VIVANT (les deux branches exigées)",
    compo == "U VIVANT", compo)

print("D2 — le détecteur MONOTONE est refusé par la composition (anti double-dip)")
ot_m, op_m, cl_m, hi_m, lo_m, oi_ts_m, oi_val_m, z_m = fabrique_panel("monotone", seed=502)
s_m, u_m, fwd_m = scores_depuis_oi(ot_m, op_m, oi_ts_m, oi_val_m)
jours_m = (ot_m // 86_400_000).astype(np.int64)
r_a1m, r_a2m, compo_m = cellules_u(s_m, u_m, fwd_m, jours_m)
chk("D2.1 A2 (côté bas) sort dans le sens MONOTONE (AUC > 0,55, opposé au U)",
    r_a2m["auc"] > 0.55, f"auc={r_a2m['auc']:.4f} v={r_a2m['verdict']}")
chk("D2.2 la composition conclut KILL-U (contradiction frontale par le côté bas)",
    compo_m.startswith("KILL-U"), compo_m)

print("D3 — le cas nul ne décolle pas (pas de batterie triviale)")
ot_n, op_n, cl_n, hi_n, lo_n, oi_ts_n, oi_val_n, z_n = fabrique_panel("nul", seed=503)
s_n, u_n, fwd_n = scores_depuis_oi(ot_n, op_n, oi_ts_n, oi_val_n)
jours_n = (ot_n // 86_400_000).astype(np.int64)
r_a1n, r_a2n, compo_n = cellules_u(s_n, u_n, fwd_n, jours_n)
chk("D3.1 A1 neutre (|AUC-0,5| < 0,02)", abs(r_a1n["auc"] - 0.5) < 0.02,
    f"auc={r_a1n['auc']:.4f}")
chk("D3.2 A2 neutre (|AUC-0,5| < 0,02)", abs(r_a2n["auc"] - 0.5) < 0.02,
    f"auc={r_a2n['auc']:.4f}")
chk("D3.3 les deux verdicts KILL et composition NON ÉTABLI",
    r_a1n["verdict"] == "KILL" and r_a2n["verdict"] == "KILL"
    and compo_n == "U NON ÉTABLI", f"{r_a1n['verdict']}/{r_a2n['verdict']}/{compo_n}")

print("L1 — zéro look-ahead : mutation multiplicative + additive des snapshots futurs")
T0 = ot[len(ot) // 2]
masque_futur = oi_ts > T0
assert masque_futur.any() and (~masque_futur).any()
oi_val_mut = np.where(masque_futur, oi_val * 1.7 + 13.7, oi_val)
chk("L1.0 la mutation change réellement les valeurs",
    not np.allclose(oi_val_mut, oi_val))
s_mut, u_mut, _ = scores_depuis_oi(ot, op, oi_ts, oi_val_mut)
idx_pass = np.flatnonzero(ot <= T0) + 1
idx_pass = idx_pass[idx_pass < len(ot)]
idx_futur = np.flatnonzero(ot > T0 + MS_H)
chk("L1.1 scores SIGNÉS passés INCHANGÉS bit à bit (multiplicative + additive)",
    bool(np.array_equal(s_full[idx_pass], s_mut[idx_pass], equal_nan=True)))
chk("L1.2 scores |z| passés INCHANGÉS bit à bit (|.| de valeurs identiques)",
    bool(np.array_equal(u_full[idx_pass], u_mut[idx_pass], equal_nan=True)))
chk("L1.3 scores futurs changent (le test n'est pas vide)",
    not np.array_equal(u_full[idx_futur], u_mut[idx_futur], equal_nan=True))

print("L2 — mutation des BARRES futures : le score (qui ne lit que l'OI) est insensible")
op_mut = np.where(ot > T0, op * 0.83 + 7.7, op)
s_mut2, u_mut2, fwd_mut2 = scores_depuis_oi(ot, op_mut, oi_ts, oi_val)
chk("L2.1 scores passés inchangés par la mutation des opens",
    bool(np.array_equal(u_full[idx_pass], u_mut2[idx_pass], equal_nan=True)))
chk("L2.2 les forwards FUTURS changent (le test n'est pas vide)",
    not np.array_equal(fwd[idx_futur], fwd_mut2[idx_futur], equal_nan=True))

print("L3 — le snapshot SIMULTANÉ (t:00) n'est JAMAIS lu par SA barre")
j_t0 = len(ot) // 3
ts_t0 = ot[j_t0]
oi_val_sim = oi_val.copy()
oi_val_sim[oi_ts == ts_t0] *= 1.9
s_mut3, u_mut3, _ = scores_depuis_oi(ot, op, oi_ts, oi_val_sim)
idx_avant = np.arange(0, j_t0 + 1)
chk("L3.1 la barre simultanée et tout le passé : scores inchangés bit à bit",
    bool(np.array_equal(u_full[idx_avant], u_mut3[idx_avant], equal_nan=True)))
idx_apres = np.arange(j_t0 + 1, min(j_t0 + 241, len(ot)))
chk("L3.2 les fenêtres postérieures voient le snapshot devenu passé (test non vide)",
    not np.array_equal(u_full[idx_apres], u_mut3[idx_apres], equal_nan=True))

print("V1 — les 4 branches du verdict tranchent exactement + le sens=0 ne promeut jamais")
rngv = np.random.default_rng(501)
n_v, n_j = 8_000, 300
sv = rngv.normal(size=n_v)
fv = 0.05 * rngv.normal(size=n_v)
jv = (np.arange(n_v) // (n_v // n_j))
r_kill = mod.cellule_panel(sv, fv, jv, "v kill", +1)
chk("V1.1 KILL sur bruit pur", r_kill["verdict"] == "KILL", f"{r_kill['verdict']} auc={r_kill['auc']:.4f}")
fv_c = 0.05 * rngv.normal(size=n_v) + 0.9 * (sv - sv.mean())
r_cand = mod.cellule_panel(sv, fv_c, jv, "v candidat", +1)
chk("V1.2 CANDIDAT sur séparation forte (sens +1)", r_cand["verdict"] == "CANDIDAT", f"{r_cand['verdict']}")
r_ctx = mod.cellule_panel(sv, -fv_c, jv, "v contexte", +1)
chk("V1.3 CONTEXTE quand le sens s'oppose", r_ctx["verdict"] == "CONTEXTE", f"{r_ctx['verdict']}")
n_p = 600
sv_p = rngv.normal(size=n_p)
fv_p = 0.05 * rngv.normal(size=n_p) + 0.006 * (sv_p - sv_p.mean())
jv_p = (np.arange(n_p) // 24)
r_inc = mod.cellule_panel(sv_p, fv_p, jv_p, "v inconclu", +1)
chk("V1.4 INCONCLU : IC contient 0,5 sans être mort",
    r_inc["verdict"] == "INCONCLU", f"{r_inc['verdict']} ic={r_inc['ic95']}")
chk("V1.5 sens=0 : séparation forte -> CONTEXTE, JAMAIS CANDIDAT",
    mod.cellule_panel(sv, fv_c, jv, "v sens0", 0)["verdict"] == "CONTEXTE")

print("P1 — le pool P1 conserve sa convention")
if POOL_CSV.exists():
    import csv as _csv
    rows_pool = list(_csv.DictReader(open(POOL_CSV, newline="")))
    chk("P1.1 469 entrées certifiées", len(rows_pool) == 469, f"n={len(rows_pool)}")
    chk("P1.2 colonnes exactes", list(rows_pool[0].keys()) ==
        ["sym", "t_in", "side", "entry", "stop", "dist_bps", "R", "alpha", "risk_usd"])
    if DATA_DIR.exists() and (DATA_DIR / "BTCUSDT_1h.csv").exists():
        cache_op = {}
        n_ok, n_tot = 0, 0
        for row in rows_pool:
            sym = row["sym"]
            if sym not in cache_op:
                p = DATA_DIR / f"{sym}_1h.csv"
                if not p.exists():
                    cache_op[sym] = None
                else:
                    import csv as _c2
                    with open(p, newline="") as fh:
                        rd = _c2.reader(fh)
                        next(rd)
                        cache_op[sym] = {int(float(r[0])): float(r[1]) for r in rd}
            opens = cache_op[sym]
            if opens is None:
                continue
            t_in = int(row["t_in"])
            side = float(row["side"])
            entry = float(row["entry"])
            if t_in in opens:
                n_tot += 1
                attendu = opens[t_in] * (1.0 + side * 2.0e-4)
                if abs(entry - attendu) <= 1e-9 * max(1.0, abs(attendu)):
                    n_ok += 1
        if n_tot == 469:
            chk("P1.3 entry = open x (1 + side x 2 bps) vérifiée 469/469", n_ok == 469, f"{n_ok}/{n_tot}")
        else:
            skip(f"P1.3 convention entry (data_x501 partielle : {n_tot}/469)")
    else:
        skip("P1.3 convention entry (X501_DATA_DIR absent)")
else:
    skip("P1.1/P1.2 (pool absent)")

print("R1 — data réelle : audit de collecte + re-exécution bit à bit")
have_data = OI_DIR.exists() and all((OI_DIR / f"{s}_{k}.jsonl").exists()
                                    for s in PANEL_12 for k in ("klines", "oi"))
if have_data:
    tot_dup_k, tot_dup_o, tot_gaps_k, tot_snap_abs = 0, 0, 0, 0
    ok_oi_positif = True
    ts_min_panel = min(mod.load_klines_bybit(s)["ts"][0] for s in PANEL_12)
    n_zero_hors_fen = 0
    for sym in PANEL_12:
        kl = mod.load_klines_bybit(sym)
        oi = mod.load_oi_bybit(sym)
        tot_dup_k += kl["n_dup"]
        tot_dup_o += oi["n_dup"]
        tot_gaps_k += int((np.diff(kl["ts"]) != MS_H).sum())
        arr = mod.snap_oi_sur_barres(kl["ts"], oi["ts"], oi["oi"])
        tot_snap_abs += int(np.isnan(arr).sum())
        m_fen = oi["ts"] >= ts_min_panel
        if not np.all(oi["oi"][m_fen] > 0):
            ok_oi_positif = False
        n_zero_hors_fen += int((oi["oi"][~m_fen] <= 0).sum())
    n_bars = sum(mod.load_klines_bybit(s)["ts"].size for s in PANEL_12)
    chk("R1.1 gaps klines < 0,1 % des barres", tot_gaps_k * 1000 < n_bars,
        f"gaps={tot_gaps_k}/{n_bars}")
    chk("R1.2 snapshots OI absents sur la fenêtre = 0", tot_snap_abs == 0, f"n={tot_snap_abs}")
    chk("R1.3 OI > 0 dans la fenêtre d'étude", ok_oi_positif)
    print(f"  note : {n_zero_hors_fen} snapshot(s) OI<=0 HORS fenêtre d'étude "
          f"(artefact(s) de collecte pré-listing, hors banc)")
    chk("R1.4 fenêtre d'étude >= 700 jours",
        (mod.load_klines_bybit("BTCUSDT")["ts"][-1] - mod.load_klines_bybit("BTCUSDT")["ts"][0]) >= 700 * 86_400_000)
    if JSON_ETUDE.exists():
        blob_avant = JSON_ETUDE.read_bytes()
        if SHA256_ATTENDU != "GRAVE_APRES_PREMIER_RUN":
            d_avant = json.loads(blob_avant)
            chk("R1.5 digest interne == digest gravé",
                d_avant.get("digest_sha256") == SHA256_ATTENDU)
        env = dict(os.environ, X501_OI_DIR=str(OI_DIR))
        res = subprocess.run([sys.executable, str(ETUDE)], env=env,
                             capture_output=True, text=True, timeout=1800)
        chk("R1.6 l'étude re-s'exécute sans erreur", res.returncode == 0, res.stderr[-300:])
        blob_apres = JSON_ETUDE.read_bytes()
        chk("R1.7 re-exécution BIT À BIT du JSON", blob_apres == blob_avant)
        if SHA256_ATTENDU != "GRAVE_APRES_PREMIER_RUN":
            import hashlib as _hl
            d_apres = json.loads(blob_apres)
            d_apres.pop("digest_sha256", None)
            recalcul = _hl.sha256(json.dumps(d_apres, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            chk("R1.8 SHA-256 du JSON == gravé (contenu sans digest)",
                recalcul == SHA256_ATTENDU, f"{recalcul[:16]} vs {SHA256_ATTENDU[:16]}")
    else:
        skip("R1.5-R1.8 (oi_ushape_local.json absent — lancer l'étude d'abord)")
else:
    skip("R1 (X501_OI_DIR incomplet)")

# ------------------------------- résumé ----------------------------------------
print(f"\nQA OI USHAPE — {n_checks} contrôles exécutés, {len(echecs)} échec(s), {n_skips} skip")
if echecs:
    print("ÉCHECS :", *echecs, sep="\n  - ")
    sys.exit(1)
print("PASS")
