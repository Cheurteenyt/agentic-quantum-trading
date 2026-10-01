#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_oi_regime_x501.py — QA de la VAGUE 9 (banc OI en contexte de régime,
x501_oi_regime_local.py).

Ce que la QA prouve, dans l'ordre :
  S1  la discipline est gravée dans le script (en-tête, constantes, panel,
      la discrimination vague 8 (FLUX) / vague 9 (NIVEAU)) ;
  S2  la mécanique de rangs/AUC est exacte (cas construits à la main) ;
  S3  le bootstrap est déterministe (seed 501, bit à bit) ;
  S4  rolling_z est exact : amorçage NaN, cas à la main (L=3), std=0 -> NaN,
      contre-vérification contre la boucle naïve fenêtre au passé ;
  D1  le DÉTECTEUR est vivant : un NIVEAU d'OI planté corrélé à la magnitude
      du forward fait DÉCOLLER l'AUC de l'étude A (la plomberie voit
      l'information quand elle existe) ;
  D2  le cas nul ne décolle pas (pas de batterie triviale) ;
  L1  le ZÉRO LOOK-AHEAD est prouvé par MUTATION des snapshots OI futurs
      (multiplicative ET additive) : le score d'une décision passée ne
      bouge pas d'un bit ;
  L2  mutation des BARRES futures : les scores (qui ne lisent que l'OI)
      restent bit à bit — le forward ne contamine pas le score ;
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

Usage : python3 qa_oi_regime_x501.py   (envs : X501_OI_DIR, X501_DATA_DIR)
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ETUDE = HERE / "x501_oi_regime_local.py"
OI_DIR = Path(os.environ.get("X501_OI_DIR", HERE / "../../../data/x501_oi"))
DATA_DIR = Path(os.environ.get("X501_DATA_DIR", HERE / "../../../data/x501_1h"))
POOL_CSV = HERE / "pool_P1_entrees.csv"
JSON_ETUDE = HERE / "oi_regime_local.json"

# digest bit à bit gravé après le premier run de l'étude (re-exécution R1)
SHA256_ATTENDU = "bf0b77ac6a74d8be5127c81a4048f6b69288879f2123b6a9c50c3b8f548c54c2"

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
spec = importlib.util.spec_from_file_location("x501_oi_regime_local", ETUDE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

rng_global = np.random.default_rng(501)

print("S1 — discipline gravée dans le script")
src = ETUDE.read_text(encoding="utf-8")
chk("S1.1 en-tête pré-enregistrement daté", "pré-enregistrée le 01/10/2026" in src)
chk("S1.2 la discrimination vague 8 / vague 9 est gravée",
    "vague 8 : le FLUX du capital" in src and "vague 9 : le NIVEAU du capital" in src)
chk("S1.3 grille gravée (lookbacks z)", "LOOKBACKS_Z = [720, 2160]" in src)
chk("S1.4 horizons figés", "HORIZONS = [24, 72]" in src)
chk("S1.5 pool L figé", "POOL_L = 720" in src)
chk("S1.6 seed du domaine", "SEED = 501" in src)
chk("S1.7 seuils du critère inchangés",
    "AUC_MORTE = 0.02" in src and "AUC_CANDIDAT = 0.05" in src)
chk("S1.8 réduction bootstrap", "REDUCTION_BOOT = 50_000" in src)
chk("S1.9 étalon coûts", "COUT_AR_TAKER_BPS = 12.2" in src)
PANEL_12 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
            "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "APTUSDT", "1000PEPEUSDT"]
chk("S1.10 panel = 12 symboles v17 exacts", mod.SYMBOLS == PANEL_12)
chk("S1.11 l'hypothèse H_R1 est gravée", "H_R1" in src)
chk("S1.12 l'étude B est sans hypothèse (sens=0)",
    "sens_attendu = 0" in src or "sens=0" in src)
chk("S1.13 l'interdiction du snapshot simultané est gravée",
    "n'est JAMAIS lu" in src)
chk("S1.14 pas de fill-forward silencieux", "Aucun fill-forward" in src)
chk("S1.15 std de population (ddof=0) gravée", "ddof=0" in src)
chk("S1.16 les cas dégénérés sont pré-déclarés", "CAS DÉGÉNÉRÉS PRÉ-DÉCLARÉS" in src)

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

print("S4 — rolling_z exact (le noyau nouveau de la vague 9)")
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
# contre-vérification : boucle naïve fenêtre STRICTEMENT au passé
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
# convention temps : score[t] = z[t-1] -> la fenêtre du score à t est
# arr[t-L..t-1], jamais arr[t] — vérifié sur un cas construit
ot_t = np.arange(200, dtype=np.int64) * MS_H
arr_t = np.arange(200, dtype=np.float64)
s_full = np.full(200, np.nan)
s_full[1:] = mod.rolling_z(arr_t, 50)[:-1]
m_t = arr_t[99 - 50 + 1:100].mean() if False else arr_t[100 - 50:100].mean()
sd_t = arr_t[100 - 50:100].std(ddof=0)
chk("S4.7 score[100] lit arr[50..99] (le snapshot 100:00 n'est JAMAIS lu)",
    abs(s_full[100] - (arr_t[99] - m_t) / sd_t) < 1e-12,
    f"{s_full[100]} vs {(arr_t[99]-m_t)/sd_t}")
# OI <= 0 (artefact) : z reste calculable mais le snap NaN propage NaN
arr_neg = np.array([1.0, 2.0, 3.0, np.nan, 5.0, 6.0, 7.0, 8.0])
zneg = mod.rolling_z(arr_neg, 3)
chk("S4.8 snapshot absent (NaN) -> score NaN propagé",
    bool(np.all(np.isnan(zneg[3:6]))), f"{zneg}")


# ------------------ pipeline synthétique partagé (D1/L1/L2/L3/D2) --------------
def fabrique_panel_synth(z_influence_oi, seed=501, n=4800):
    """Un panel klines+OI synthétique où la MAGNITUDE du forward open->open
    H=24 est MONOTONEMENT croissante dans un champ latent z[t]
    (fwd_cible = 0,0010 + 0,0020 x z + bruit, toujours > 0 en moyenne :
    |fwd| croit avec z) — MONOTONE est la forme de H_R1 (plus de capital ->
    plus de cascades). Le NIVEAU d'OI porte z[t+1] DIRECTEMENT (OI[t] = base
    x (1 + ampl x z[t+1] x infl + bruit)) avec le décalage d'une barre de la
    vague 8 : le score lu à l'open de t (z du niveau calcule jusqu'a t-1)
    porte ainsi z[t], le MEME champ que le forward de t. (Une relation en U
    — |fwd| grand aux DEUX extrêmes du score signé — serait INVISIBLE pour
    une dichotomie médiane : c'est une limite structurelle du critère,
    gravée L8 dans l'étude ; H_R1 est monotone, le banc est fidèle.)"""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    fwd_cible = 0.0010 + 0.0020 * z + 0.0008 * rng.normal(size=n)
    ot = np.arange(n, dtype=np.int64) * MS_H + 1_700_000_000_000
    op = np.empty(n)
    for r in range(24):
        idx = np.arange(r, n, 24)
        vals = [100.0 * (1 + 0.01 * rng.normal())]
        for t in idx[1:]:
            vals.append(vals[-1] * (1.0 + fwd_cible[t - 24]))
        op[idx] = vals
    # OI : le NIVEAU porte le champ latent DIRECTEMENT avec le décalage
    # d'une barre (OI[t] porte z[t+1]) — la transposition exacte du détecteur
    # vague 8 : le score lu à l'open de t (z du niveau calcule jusqu'a t-1)
    # porte ainsi z[t], le MEME champ que le forward open->open de t.
    z_shift = np.append(z[1:], z[-1])
    oi_val = 1_000_000.0 * (1.0 + 0.05 * z_influence_oi * z_shift
                            + 0.01 * rng.normal(size=n))
    oi_ts = ot.copy()
    cl = op * (1.0 + 0.0002 * rng.normal(size=n))
    hi = np.maximum(op, cl) * (1 + np.abs(rng.normal(size=n)) * 0.0005)
    lo = np.minimum(op, cl) * (1 - np.abs(rng.normal(size=n)) * 0.0005)
    return ot, op, cl, hi, lo, oi_ts, oi_val, z


def score_z_depuis_oi(ot, op, oi_ts, oi_val, L=240, H=24, magnitude=True):
    """Le chemin EXACT du pipeline d'étude (snap -> rolling_z -> s_full -> fwd).
    L réduit à 240 pour le test (la plomberie est identique, l'amorçage plus court)."""
    arr = mod.snap_oi_sur_barres(ot, oi_ts, oi_val)
    n = len(ot)
    z = mod.rolling_z(arr, L)
    s_full = np.full(n, np.nan)
    s_full[1:] = z[:-1]
    fwd = np.full(n, np.nan)
    fwd[:n - H] = (op[H:] - op[:n - H]) / op[:n - H] * 1e4
    if magnitude:
        fwd = np.abs(fwd)
    return s_full, fwd


print("D1 — le détecteur est vivant (niveau d'OI planté corrélé à la magnitude)")
ot, op, cl, hi, lo, oi_ts, oi_val, z = fabrique_panel_synth(z_influence_oi=1.0)
s_full, fwd = score_z_depuis_oi(ot, op, oi_ts, oi_val)
s_full_sig, fwd_sig = score_z_depuis_oi(ot, op, oi_ts, oi_val, magnitude=False)
jours = (ot // 86_400_000).astype(np.int64)
r = mod.cellule_panel(s_full, fwd, jours, "test détecteur magnitude", +1)
chk("D1.1 AUC décolle sur |fwd| monotone (> 0,55)", r["auc"] > 0.55, f"auc={r['auc']:.4f}")
chk("D1.2 verdict CANDIDAT (étude A, sens +1)", r["verdict"] == "CANDIDAT", r["verdict"])
r_sig = mod.cellule_panel(s_full_sig, fwd_sig, jours, "test détecteur signé", 0)
chk("D1.3 la MÊME plomberie décolle sur fwd signé (étude B, AUC > 0,55)",
    r_sig["auc"] > 0.55, f"auc={r_sig['auc']:.4f}")
chk("D1.4 et le verdict reste CONTEXTE (sens=0 ne promeut jamais — redondance V1.5)",
    r_sig["verdict"] == "CONTEXTE", r_sig["verdict"])

print("D2 — le cas nul ne décolle pas (pas de batterie triviale)")
ot2, op2, cl2, hi2, lo2, oi_ts2, oi_val2, z2 = fabrique_panel_synth(z_influence_oi=0.0, seed=502)
s2_full, f2wd = score_z_depuis_oi(ot2, op2, oi_ts2, oi_val2)
jours2 = (ot2 // 86_400_000).astype(np.int64)
r2 = mod.cellule_panel(s2_full, f2wd, jours2, "test nul", +1)
chk("D2.1 AUC neutre (|AUC-0,5| < 0,02)", abs(r2["auc"] - 0.5) < 0.02, f"auc={r2['auc']:.4f}")
chk("D2.2 verdict KILL", r2["verdict"] == "KILL", r2["verdict"])

print("L1 — zéro look-ahead : mutation multiplicative + additive des snapshots futurs")
T0 = ot[len(ot) // 2]
masque_futur = oi_ts > T0
assert masque_futur.any() and (~masque_futur).any()
oi_val_mut = np.where(masque_futur, oi_val * 1.7 + 13.7, oi_val)
chk("L1.0 la mutation change réellement les valeurs",
    not np.allclose(oi_val_mut, oi_val))
s_mut, _ = score_z_depuis_oi(ot, op, oi_ts, oi_val_mut)
idx_pass = np.flatnonzero(ot <= T0) + 1
idx_pass = idx_pass[idx_pass < len(ot)]
idx_futur = np.flatnonzero(ot > T0 + MS_H)
same = np.array_equal(s_full[idx_pass], s_mut[idx_pass], equal_nan=True)
chk("L1.1 scores passés INCHANGÉS bit à bit (multiplicative + additive)", bool(same))
chk("L1.2 scores futurs changent (le test n'est pas vide)",
    not np.array_equal(s_full[idx_futur], s_mut[idx_futur], equal_nan=True))

print("L2 — mutation des BARRES futures : le score (qui ne lit que l'OI) est insensible")
op_mut = np.where(ot > T0, op * 0.83 + 7.7, op)
s_mut2, fwd_mut2 = score_z_depuis_oi(ot, op_mut, oi_ts, oi_val)
chk("L2.1 scores passés inchangés par la mutation des opens",
    bool(np.array_equal(s_full[idx_pass], s_mut2[idx_pass], equal_nan=True)))
chk("L2.2 les forwards FUTURS changent (le test n'est pas vide)",
    not np.array_equal(fwd[idx_futur], fwd_mut2[idx_futur], equal_nan=True))

print("L3 — le snapshot SIMULTANÉ (t:00) n'est JAMAIS lu par SA barre")
j_t0 = len(ot) // 3                    # barre de décision testée (dans le corps)
ts_t0 = ot[j_t0]                       # le snapshot pile à l'open de la barre j_t0
oi_val_sim = oi_val.copy()
oi_val_sim[oi_ts == ts_t0] *= 1.9      # muter UNIQUEMENT le snapshot simultané
s_mut3, _ = score_z_depuis_oi(ot, op, oi_ts, oi_val_sim)
# (a) la décision à l'open de j_t0 et TOUT le passé : inchangés bit à bit
idx_avant = np.arange(0, j_t0 + 1)     # s_full[t] pour t <= j_t0 : ne lit pas arr[j_t0]
chk("L3.1 la barre simultanée et tout le passé : scores inchangés bit à bit",
    bool(np.array_equal(s_full[idx_avant], s_mut3[idx_avant], equal_nan=True)))
# (b) les décisions POSTÉRIEURES (t > j_t0) LISSENT le snapshot devenu passé :
# elles doivent changer (sinon le test serait vide — le snapshot est bien dans
# les fenêtres roulantes des L barres suivantes)
idx_apres = np.arange(j_t0 + 1, min(j_t0 + 241, len(ot)))
chk("L3.2 les fenêtres postérieures voient le snapshot devenu passé (test non vide)",
    not np.array_equal(s_full[idx_apres], s_mut3[idx_apres], equal_nan=True))

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
        skip("R1.5-R1.8 (oi_regime_local.json absent — lancer l'étude d'abord)")
else:
    skip("R1 (X501_OI_DIR incomplet)")

# ------------------------------- résumé ----------------------------------------
print(f"\nQA OI REGIME — {n_checks} contrôles exécutés, {len(echecs)} échec(s), {n_skips} skip")
if echecs:
    print("ÉCHECS :", *echecs, sep="\n  - ")
    sys.exit(1)
print("PASS")
