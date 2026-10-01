#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_oi_regime_local.py — VAGUE 9 : LE BANC DE L'OI EN CONTEXTE DE RÉGIME
(la case explicitement laissée ouverte par la vague 8 — docs/33 « NON FERMÉ :
l'OI 1j pré-2024 en contexte de régime » — la dernière cellule falsifiable
localement du registre docs/27 côté data gratuite).

LA DISCRIMINATION AVEC LA VAGUE 8 (pré-enregistrée le 01/10/2026, AVANT toute
mesure — aucune cellule n'a été regardée avant l'écriture de ce fichier) :
  vague 8 : le FLUX du capital (ΔOI%_L) comme signal DIRECTIONNEL de
            continuation → 10/10 KILL ;
  vague 9 : le NIVEAU du capital (z-score roulant de l'OI) comme
            CONDITIONNEUR de la distribution des rendements futurs —
            PAS de direction. La théorie du levier pré-dit une asymétrie de
            MAGNITUDE (OI haut = plus de positions à financer = cascades plus
            grandes dans les DEUX sens), elle ne pré-dit AUCUNE direction.

LA DISCIPLINE (gravée AVANT tout chiffre) :

  GRILLE PRÉ-DÉCLARÉE (TOUTES les cellules sont mesurées et rapportées,
  même celles qui déçoivent) :
    A. MAGNITUDE (H_R1, la seule hypothèse que la théorie du levier pré-dit) :
       score = z_L(OI) = (OI[t-1] - mean_L(OI)) / std_L(OI) — z-score roulant
       du NIVEAU, fenêtre L barres 1h, std de population (ddof=0) —
       cible = |fwd_H| (magnitude du rendement open->open, doctrine _MK).
       L dans {720, 2160} (30 j, 90 j) x H dans {24, 72} = 4 cellules.
       H_R1 : capital haut -> grands mouvements (AUC > 0,5 attendu).
    B. NIVEAU, TEST DIRECTIONNEL PAR DÉFAUT (aucune théorie pré-déclarée) :
       score = z_L(OI[t-1]) identique, cible = fwd_H SIGNÉ, sens_attendu = 0
       — toute séparation éventuelle est CONTEXTE par définition (un delta
       sans hypothèse pré-déclarée n'est jamais une promotion, leçon vague 7).
       L dans {720, 2160} x H dans {24, 72} = 4 cellules.
    C. POOL P1 : les 469 entrées certifiées rejouées avec z_720(OI) au t_in
       (snapshot <= t_in - 1h), split médian du score, R haut vs bas,
       bootstrap diff de médianes 10 000. CONTEXTE par nature (in-sample de
       la sélection), jamais promotion. L figé à 720 (le 2160 consommerait
       ~25 % de la fenêtre kline 749 j — pré-déclaré).
  Total : 8 cellules de panel + 1 cellule de pool. TOUTES rapportées.

  CONVENTION TEMPS STRICTE (identique vague 8, transposée de la correction
  v27 docs/26) : le snapshot hh:00 marque l'OUVERTURE de sa fenêtre ; à
  l'open de t, le dernier snapshot CONNU est (t-1):00 ; le snapshot t:00
  n'est JAMAIS lu ; existence PILE exigée (0 fill-forward, une absence
  invalide la décision, comptée et rapportée). Le z-score à la barre t
  n'agrège donc QUE les snapshots <= (t-1):00 (fenêtre roulante arrondie
  au passé). Klines connues à l'open de t : indices <= t-1. Forward =
  open(t+H) - open(t) en bps.

  CAS DÉGÉNÉRÉS PRÉ-DÉCLARÉS : std_L = 0 (fenêtre plate) -> score NaN ->
  décision invalidée, comptée ; OI <= 0 (artefact pré-listing, note QA
  vague 8) -> score NaN, compté ; amorçage L-1 barres -> NaN, compté.

  VERDICT MÉCANIQUE PAR CELLULE (critère AUC du domaine, inchangé) :
  KILL si IC 95 % contient 0,5 et |AUC-0,5| < 0,02 ; INCONCLU si l'IC
  contient 0,5 ; CANDIDAT si l'IC EXCLUT 0,5 ET |AUC-0,5| >= 0,05 ET le
  sens CONFIRME l'hypothèse pré-déclarée (étude A seulement, sens +1) ;
  CONTEXTE si l'IC exclut 0,5 mais le sens s'y OPPOSE ou si sens_attendu
  = 0 (étude B/C). IC = bootstrap 1 000 par journées UTC, seed 501,
  réduction 50 000 — la mécanique exacte des vagues 5/8.

  BANDES DE COÛTS (rappel docs/26) : taker 6,1 bps/côté, maker 2 bps/côté ;
  l'étalon d'exploitabilité = 12,2 bps A/R taker. Un delta sans AUC n'est
  pas un plan (leçon vague 7) : les deltas médianes sont DESCRIPTIFS.

  PANEL : les 12 symboles om_v27 (manifeste docs/26, liste v17 à
  l'identique), klines 1h ET OI 1h du MÊME exchange (Bybit v5, linear) —
  zéro cross-exchange dans le panel. La profondeur OI Bybit (~4,5 ans)
  dépasse la fenêtre kline (~749 j) : la fenêtre d'étude = la fenêtre KLINE
  commune ; le z-score roulant (L <= 2160 h) reste STRICTEMENT dans cette
  fenêtre — l'OI pré-2024 N'ENTRE PAS dans les statistiques du banc (la
  case « pré-2024 » ne peut être fermée qu'en contexte, limite L1 ci-
  dessous) : ce que le banc ferme, c'est le MÉCANISME du régime sur la
  fenêtre complète des klines.

Limites assumées (pré-enregistrées) :
  L1 le z-score est relatif à la fenêtre kline (749 j), pas à l'historique
     OI complet (~4,5 ans) — le « régime » est donc in-fenêtre ; un niveau
     absolu de 2022-2023 comparé à 2026 exigerait des klines alignées qui
     n'existent pas localement (data Binance x501 = 1 092 j mais OI Bybit
     seulement depuis 2022-03 sur BTC/ETH) — ASSUMÉ : le banc mesure le
     mécanisme, pas le niveau absolu séculaire ;
  L2 l'OI Bybit est le capital Bybit, pas le capital global (limite L1
     vague 8 inchangée) ;
  L3 l'IC bootstrap rééchantillonne les JOURNÉES (clusters 24 h) et évalue
     l'AUC sur un échantillon réduit déterministe de 50 000 points (l'AUC
     ponctuelle est full-sample) ;
  L4 l'étude C croise des entrées pool (data Binance) avec l'OI Bybit —
     cross-exchange assumé (arbitrage à la seconde), CONTEXTE par nature ;
  L5 horizons en barres (gaps rares comptés) — doctrine _MK ;
  L6 la dichotomie à la médiane mesure la séparation HAUT/BAS, pas la
     forme monotone de la relation (L4 vague 5) ;
  L7 |fwd| (étude A) n'est pas la volatilité réalisée intrabar (high-low) :
     c'est la magnitude du rendement open->open — la grandeur que le plan
     x501 capture réellement (entrées à l'open, doctrine _MK) ;
  L8 la dichotomie médiane + AUC Mann-Whitney ne capte que la forme
     MONOTONE de H_R1 (plus de capital -> plus de grands mouvements, sa
     formulation théorique) ; une forme en U (|fwd| grand aux DEUX extrêmes
     du z-score) serait invisible pour ce critère — une extension en
     dichotomie |z| exigerait un pré-enregistrement ultérieur (règle
     docs/26 : tout re-test exige un pré-enregistrement explicite).

Reproduction :
  X501_OI_DIR=<dir des {SYM}_klines.jsonl et {SYM}_oi.jsonl> \
      python3 x501_oi_regime_local.py
  (défaut : data/x501_oi du repo ; la collecte est re-exécutable avec
  x501_collect_oi_v8.py — collecteur versionné vague 8, inchangé)
Sorties : oi_regime_local.json (versionné, déterministe) + résumé console.
"""
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OI_DIR = Path(os.environ.get("X501_OI_DIR", HERE / "../../../data/x501_oi"))
POOL_CSV = HERE / "pool_P1_entrees.csv"
OUT_JSON = HERE / "oi_regime_local.json"

# ---------------------- grille PRÉ-DÉCLARÉE (01/10/2026) ----------------------
LOOKBACKS_Z = [720, 2160]             # barres 1h (études A et B : 30 j, 90 j)
HORIZONS = [24, 72]                   # barres 1h (open -> open)
POOL_L = 720                          # L du z-score projeté sur le pool

# ---------------------- verdict mécanique (critère domaine) -------------------
SEED = 501
N_BOOT_PANEL = 1_000                  # IC bootstrap AUC, par journées UTC
N_BOOT_POOL = 10_000                  # mécanique verdict_ab (diff de médiane)
REDUCTION_BOOT = 50_000               # points max par cellule pour le boot
AUC_MORTE = 0.02                      # |AUC-0,5| < 0,02 et IC contient 0,5 -> KILL
AUC_CANDIDAT = 0.05                   # séparation minimale d'un CANDIDAT
COUT_AR_TAKER_BPS = 12.2              # 2 x 6,1 — l'étalon d'exploitabilité

MS_H = 3_600_000
MS_J = 86_400_000

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "APTUSDT", "1000PEPEUSDT"]


# ------------------------------- utils ----------------------------------------
def rangs_moyens(x):
    """Rangs 1..n avec rangs moyens sur les ex-aequo (vectorisé, stable).
    Mécanique exacte des vagues 5/8 : bornes de blocs + np.repeat."""
    n = len(x)
    ordre = np.argsort(x, kind="mergesort")
    sx = x[ordre]
    fin = np.append(np.flatnonzero(np.diff(sx) != 0.0), n - 1)
    deb = np.append(0, fin[:-1] + 1)
    moyennes = (deb + fin) / 2.0 + 1.0
    r = np.repeat(moyennes, fin - deb + 1)
    out = np.empty(n)
    out[ordre] = r
    return out


def auc_mw(x_haut, x_bas):
    """AUC Mann-Whitney = P(x_haut > x_bas) + 0,5 P(=). Rangs moyens."""
    n1, n2 = len(x_haut), len(x_bas)
    if n1 == 0 or n2 == 0:
        return float("nan")
    x = np.concatenate([x_haut, x_bas])
    r = rangs_moyens(x)
    r1 = r[:n1].sum()
    u = r1 - n1 * (n1 + 1) / 2.0
    return u / (n1 * n2)


def bootstrap_flags(fwd, flag, jour_idx, iters, seed):
    """IC bootstrap de l'AUC : rééchantillonnage AVEC REMISE des journées
    (clusters 24h, limite L3), évaluation sur l'échantillon réduit. Mécanique
    exacte des vagues 5/8."""
    rng = np.random.default_rng(seed)
    order = np.argsort(jour_idx, kind="mergesort")
    fwd, flag, ji = fwd[order], flag[order], jour_idx[order]
    uniq, starts = np.unique(ji, return_index=True)
    counts = np.diff(np.append(starts, len(ji)))
    starts = np.asarray(starts)
    n_tir = min(len(fwd), REDUCTION_BOOT)
    if n_tir < len(fwd):
        sel = np.sort(rng.choice(len(fwd), size=n_tir, replace=False))
        fwd, flag, ji = fwd[sel], flag[sel], ji[sel]
        uniq, starts = np.unique(ji, return_index=True)
        counts = np.diff(np.append(starts, len(ji)))
        starts = np.asarray(starts)
    out = np.empty(iters)
    for b in range(iters):
        tir = rng.integers(0, len(uniq), size=len(uniq))
        lens = counts[tir]
        total = int(lens.sum())
        deb = np.cumsum(lens) - lens
        idx = np.repeat(starts[tir], lens) + (np.arange(total) - np.repeat(deb, lens))
        f = fwd[idx]
        g = flag[idx]
        out[b] = auc_mw(f[g], f[~g])
    return out


def rolling_z(arr, L):
    """z-score roulant du NIVEAU : z[j] = (arr[j] - mean(arr[j-L+1..j]))
    / std(arr[j-L+1..j]), std de population (ddof=0), fenêtre STRICTEMENT
    dans le passé (inclut j, exclusivité temporelle garantie par le
    décalage s_full[1:] = z[:-1] — le score à l'open de t n'agrège que
    les snapshots <= (t-1):00). NaN d'amorçage sur les L-1 premières
    barres ; std=0 -> NaN (décision invalidée, comptée par l'appelant).
    Sommes cumulées float64 — O(n) par cellule. CAS DÉGÉNÉRÉ (pré-déclaré) :
    std -> 0 (fenêtre plate) : les erreurs d'arrondi float64 de var = s2/L - m^2
    laissent un résidu ~1e-14 qui produirait z = +-inf ; le score est donc
    forcé à NaN quand sd <= 1e-6 x max(1, |m|) (seuil RELATIF d'échelle :
    une fenêtre dont la dispersion relative est < 1e-6 est indistinguable
    d'une constante aux erreurs float près) —
    une fenêtre plate n'informe pas le régime, la décision est invalidée
    (comptée par l'appelant)."""
    n = len(arr)
    z = np.full(n, np.nan)
    if L > n:
        return z
    c1 = np.concatenate(([0.0], np.cumsum(arr, dtype=np.float64)))
    c2 = np.concatenate(([0.0], np.cumsum(arr * arr, dtype=np.float64)))
    s = c1[L:] - c1[:n - L + 1]
    s2 = c2[L:] - c2[:n - L + 1]
    m = s / L
    var = s2 / L - m * m
    np.maximum(var, 0.0, out=var)     # garde anti-négatif (erreur float)
    sd = np.sqrt(var)
    plat = sd <= 1e-6 * np.maximum(1.0, np.abs(m))   # fenêtre plate -> NaN
    sd = np.where(plat, np.nan, sd)
    with np.errstate(invalid="ignore", divide="ignore"):
        zz = (arr[L - 1:] - m) / sd
    z[L - 1:] = zz
    return z


# ------------------------------- chargement -----------------------------------
def load_klines_bybit(sym):
    """Klines 1h Bybit depuis le JSONL de collecte (ts,o,h,l,c,v,qv).
    Déduplication par ts (index unique, leçon audit v27) + tri asc."""
    p = OI_DIR / f"{sym}_klines.jsonl"
    if not p.exists():
        return None
    rows = []
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            rows.append((int(r["ts"]), float(r["o"]), float(r["h"]),
                         float(r["l"]), float(r["c"])))
    a = np.asarray(rows, dtype=np.float64)
    n_dup = len(a) - len(np.unique(a[:, 0]))
    uniq_idx = np.unique(a[:, 0], return_index=True)[1]
    a = a[uniq_idx]
    order = np.argsort(a[:, 0], kind="mergesort")
    a = a[order]
    return {"ts": a[:, 0].astype(np.int64), "o": a[:, 1], "h": a[:, 2],
            "l": a[:, 3], "c": a[:, 4], "n_dup": n_dup}


def load_oi_bybit(sym):
    """OI 1h Bybit depuis le JSONL de collecte (ts, oi). Dédup + tri asc."""
    p = OI_DIR / f"{sym}_oi.jsonl"
    if not p.exists():
        return None
    t, v = [], []
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            t.append(int(r["ts"]))
            v.append(float(r["oi"]))
    ts = np.asarray(t, dtype=np.int64)
    val = np.asarray(v, dtype=np.float64)
    uniq_idx = np.unique(ts, return_index=True)[1]
    n_dup = len(ts) - len(uniq_idx)
    ts, val = ts[uniq_idx], val[uniq_idx]
    order = np.argsort(ts, kind="mergesort")
    return {"ts": ts[order], "oi": val[order], "n_dup": n_dup}


def snap_oi_sur_barres(ot, oi_ts, oi_val):
    """Snapshot OI aligné PILE sur chaque barre kline : arr[j] = OI au ts de
    la barre j, NaN si le snapshot n'existe pas pile. Aucun fill-forward."""
    n = len(ot)
    arr = np.full(n, np.nan)
    idx = np.searchsorted(oi_ts, ot)
    ok = (idx < len(oi_ts)) & (oi_ts[np.minimum(idx, len(oi_ts) - 1)] == ot)
    arr[ok] = oi_val[idx[ok]]
    return arr


# ------------------------------ cellules --------------------------------------
def cellule_panel(score, fwd, jours, hypothese, sens_attendu):
    """Une cellule de panel : AUC full-sample, IC bootstrap par journées,
    verdict mécanique (critère du domaine) — sens_attendu ∈ {+1,-1,0} ;
    0 = aucune hypothèse directionnelle pré-déclarée -> toute séparation
    est CONTEXTE (jamais CANDIDAT)."""
    ok = np.isfinite(score) & np.isfinite(fwd)
    s, f, j = score[ok], fwd[ok], jours[ok]
    med = float(np.median(s))
    flag_fin = s > med
    n_haut, n_bas = int(flag_fin.sum()), int((~flag_fin).sum())
    auc = auc_mw(f[flag_fin], f[~flag_fin])
    lo, hi = float("nan"), float("nan")
    if n_haut >= 100 and n_bas >= 100:
        boots = bootstrap_flags(f, flag_fin, j, N_BOOT_PANEL, SEED)
        lo, hi = float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))
    contient = (lo <= 0.5 <= hi) if np.isfinite(lo) else True
    if contient and abs(auc - 0.5) < AUC_MORTE and n_haut >= 100 and n_bas >= 100:
        verdict = "KILL"
    elif contient:
        verdict = "INCONCLU"
    elif abs(auc - 0.5) >= AUC_CANDIDAT:
        if sens_attendu > 0:
            confirme = auc > 0.5
        elif sens_attendu < 0:
            confirme = auc < 0.5
        else:
            confirme = False          # pas d'hypothèse pré-déclarée
        verdict = "CANDIDAT" if confirme else "CONTEXTE"
    else:
        verdict = "INCONCLU"
    return {
        "n": int(len(s)), "n_haut": n_haut, "n_bas": n_bas,
        "mediane_score": med, "auc": auc,
        "ic95": [lo, hi],
        "fwd_bps_haut": float(np.median(f[flag_fin])),
        "fwd_bps_bas": float(np.median(f[~flag_fin])),
        "delta_bps": float(np.median(f[flag_fin]) - np.median(f[~flag_fin])),
        "hypothese": hypothese, "verdict": verdict,
    }


# ------------------------------- études ----------------------------------------
def main():
    fam_a = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_Z for h in HORIZONS}
    fam_b = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_Z for h in HORIZONS}
    n_bars_tot, n_dup_k, n_dup_o = 0, 0, 0
    n_snap_absents = 0
    n_invalidees_amorcage = 0     # barres avec z NaN pour cause d'amorçage (L=720)
    n_invalidees_std0 = 0         # barres avec z NaN pour cause de std=0 (L=720)
    fen_t0, fen_t1 = None, None
    audit_syms = {}
    oi_profondeurs = {}

    for sym in SYMBOLS:
        kl = load_klines_bybit(sym)
        oi = load_oi_bybit(sym)
        if kl is None or oi is None:
            raise SystemExit(f"data manquante pour {sym} dans {OI_DIR}")
        ot, op = kl["ts"], kl["o"]
        n = len(ot)
        n_bars_tot += n
        n_dup_k += kl["n_dup"]
        n_dup_o += oi["n_dup"]
        fen_t0 = ot[0] if fen_t0 is None else min(fen_t0, ot[0])
        fen_t1 = ot[-1] if fen_t1 is None else max(fen_t1, ot[-1])
        oi_profondeurs[sym] = int(oi["ts"][0])
        gaps_k = int((np.diff(ot) != MS_H).sum())
        in_win = oi["ts"] >= ot[0]
        gaps_o_in = int((np.diff(oi["ts"][in_win]) != MS_H).sum())
        arr_oi = snap_oi_sur_barres(ot, oi["ts"], oi["oi"])
        n_snap_absents += int(np.isnan(arr_oi).sum())
        jours = (ot // MS_J).astype(np.int64)
        fwd = {}
        for h in HORIZONS:
            ret = np.full(n, np.nan)
            if n > h:
                ret[:n - h] = (op[h:] - op[:n - h]) / op[:n - h] * 1e4
            fwd[h] = ret
        audit_syms[sym] = {"n_klines": n, "n_oi": len(oi["ts"]),
                           "gaps_klines": gaps_k, "gaps_oi_in_win": gaps_o_in,
                           "n_snap_absents": int(np.isnan(arr_oi).sum())}

        # z-scores roulants du NIVEAU (fenêtre au passé, cf. rolling_z)
        zs = {lb: rolling_z(arr_oi, lb) for lb in LOOKBACKS_Z}
        # comptage figé au L du pool (sinon cumul trompeur — leçon vague 8)
        z720 = zs[720]
        n_invalidees_amorcage += int((np.isnan(z720[:720 - 1])).sum())
        n_invalidees_std0 += int((np.isnan(z720[720 - 1:]) &
                                  np.isfinite(arr_oi[720 - 1:])).sum())

        for lb in LOOKBACKS_Z:
            z = zs[lb]
            s_full = np.full(n, np.nan)
            s_full[1:] = z[:-1]          # le snapshot t:00 n'est JAMAIS lu
            for h in HORIZONS:
                ok = np.isfinite(s_full) & np.isfinite(fwd[h])
                ca = fam_a[(lb, h)]
                ca["s"].append(s_full[ok])
                ca["f"].append(np.abs(fwd[h][ok]))   # étude A : MAGNITUDE
                ca["j"].append(jours[ok])
                cb = fam_b[(lb, h)]
                cb["s"].append(s_full[ok])
                cb["f"].append(fwd[h][ok])           # étude B : SIGNÉ
                cb["j"].append(jours[ok])

    # ---------------- verdict des 8 cellules de panel -------------------------
    res_a, res_b, verdicts = {}, {}, []
    for lb in LOOKBACKS_Z:
        for h in HORIZONS:
            c = fam_a[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "capital haut -> grands mouvements (H_R1)", +1)
            res_a[f"L{lb}_H{h}"] = r
            verdicts.append(r["verdict"])
    for lb in LOOKBACKS_Z:
        for h in HORIZONS:
            c = fam_b[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "niveau du capital -> direction (aucune hypothèse, sens=0)", 0)
            res_b[f"L{lb}_H{h}"] = r
            verdicts.append(r["verdict"])

    # ------------------------- ÉTUDE C — pool P1 --------------------------------
    pool = []
    with open(POOL_CSV, newline="") as f:
        for row in csv.DictReader(f):
            pool.append((row["sym"], int(row["t_in"]), float(row["R"])))
    cache = {}

    def serie(sym):
        if sym not in cache:
            kl, oi = load_klines_bybit(sym), load_oi_bybit(sym)
            if kl is None or oi is None:
                cache[sym] = None
            else:
                ot = kl["ts"]
                arr = snap_oi_sur_barres(ot, oi["ts"], oi["oi"])
                z = rolling_z(arr, POOL_L)
                s_full = np.full(len(ot), np.nan)
                s_full[1:] = z[:-1]      # le snapshot t_in:00 n'est JAMAIS lu
                cache[sym] = (ot, s_full)
        return cache[sym]

    rows = []
    n_hors_panel = 0
    for sym, t_in, R in pool:
        sc = serie(sym) if sym in SYMBOLS else None
        if sc is None:
            n_hors_panel += 1
            continue
        ot, s_full = sc
        i = int(np.searchsorted(ot, t_in, side="left"))
        if i >= len(ot) or ot[i] != t_in:
            n_hors_panel += 1
            continue  # t_in doit être un open exact (doctrine _MK)
        rows.append((s_full[i], R))
    n_pool = len(rows)
    sP = np.asarray([r[0] for r in rows], dtype=np.float64)
    R_pool = np.asarray([r[1] for r in rows], dtype=np.float64)

    ok = np.isfinite(sP)
    s, R = sP[ok], R_pool[ok]
    med = float(np.median(s)) if len(s) else float("nan")
    haut = s > med
    rng = np.random.default_rng(SEED)
    boots = np.empty(N_BOOT_POOL)
    hi_idx = np.flatnonzero(haut)
    lo_idx = np.flatnonzero(~haut)
    for b in range(N_BOOT_POOL):
        h = R[rng.choice(hi_idx, size=len(hi_idx), replace=True)]
        l = R[rng.choice(lo_idx, size=len(lo_idx), replace=True)]
        boots[b] = float(np.median(h) - np.median(l))
    p_sup = float((boots > 0).mean())
    cC = {
        "nom": f"z_oi_L{POOL_L}", "n": int(ok.sum()), "n_hors_panel": n_hors_panel,
        "mediane_split": med, "n_haut": int(haut.sum()), "n_bas": int((~haut).sum()),
        "R_med_haut": float(np.median(R[haut])) if haut.any() else float("nan"),
        "R_med_bas": float(np.median(R[~haut])) if (~haut).any() else float("nan"),
        "R_moy_haut": float(R[haut].mean()) if haut.any() else float("nan"),
        "R_moy_bas": float(R[~haut].mean()) if (~haut).any() else float("nan"),
        "WR_haut": 100.0 * float((R[haut] > 0).mean()) if haut.any() else float("nan"),
        "WR_bas": 100.0 * float((R[~haut] > 0).mean()) if (~haut).any() else float("nan"),
        "delta_med_R": float(np.median(R[haut]) - np.median(R[~haut])) if haut.any() and (~haut).any() else float("nan"),
        "ic95_delta_med": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
        "P_delta_sup_0": p_sup,
        "statut": "CONTEXTE (in-sample du pool + cross-exchange L4, jamais promotion)",
    }

    # ------------------------------ sorties -------------------------------------
    compte = {v: verdicts.count(v) for v in sorted(set(verdicts))}
    out = {
        "outils": "x501_oi_regime_local.py — vague 9 : banc de l'OI en contexte de régime",
        "grille_pre_declaree": {
            "date": "2026-10-01", "lookbacks_z_barres": LOOKBACKS_Z,
            "horizons_barres": HORIZONS, "pool_L": POOL_L,
            "hypothese_A": "capital haut -> |fwd| plus grand (H_R1, AUC>0,5 attendu, théorie du levier)",
            "hypothese_B": "niveau du capital -> direction : AUCUNE hypothèse pré-déclarée (sens=0, toute séparation = CONTEXTE)",
            "criterion": f"AUC IC95 exclut 0,5 et |AUC-0,5|>={AUC_CANDIDAT} = CANDIDAT ; "
                         f"IC contient 0,5 et |AUC-0,5|<{AUC_MORTE} = KILL ; sinon INCONCLU",
            "panel": SYMBOLS,
        },
        "fenetre": {
            "oi_dir": OI_DIR.name, "n_symboles": len(SYMBOLS),
            "n_barres_1h": n_bars_tot, "t0": int(fen_t0), "t1": int(fen_t1),
            "dup_klines": n_dup_k, "dup_oi": n_dup_o,
            "snap_absents": n_snap_absents,
            "invalidees_amorcage_L720": n_invalidees_amorcage,
            "invalidees_std0_L720": n_invalidees_std0,
            "oi_profondeur_min_ts": min(oi_profondeurs.values()),
            "cout_ar_taker_bps": COUT_AR_TAKER_BPS,
        },
        "audit_par_symbole": audit_syms,
        "etude_A_magnitude": res_a, "etude_B_niveau_direction": res_b,
        "resume_verdicts_panel": compte,
        "etude_C_pool_P1": cC,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    digest = hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    out["digest_sha256"] = digest
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    # ------------------------------ console -------------------------------------
    print(f"OI REGIME — {len(SYMBOLS)} symboles, {n_bars_tot} barres 1h, "
          f"doublons k={n_dup_k} o={n_dup_o}, snap absents {n_snap_absents}")
    print(f"  invalidées : amorçage L720 {n_invalidees_amorcage}, std0 L720 {n_invalidees_std0}")
    print(f"  fenêtre : {fen_t0} -> {fen_t1}")
    print("\nÉTUDE A — MAGNITUDE z_L(OI) -> |fwd| (H_R1 : capital haut = grands mouvements, AUC>0,5 attendu)")
    for k, r in res_a.items():
        print(f"  {k:>10}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.2f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print("\nÉTUDE B — NIVEAU z_L(OI) -> fwd signé (aucune hypothèse pré-déclarée, sens=0)")
    for k, r in res_b.items():
        print(f"  {k:>10}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.2f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print(f"\nRésumé verdicts panel : {compte}")
    print(f"\nÉTUDE C — pool P1 (CONTEXTE, in-sample + cross-exchange L4)")
    print(f"  n {cC['n']} (hors panel {cC['n_hors_panel']})  "
          f"R méd haut {cC['R_med_haut']:+.3f} vs bas {cC['R_med_bas']:+.3f}  "
          f"delta {cC['delta_med_R']:+.3f}  P(delta>0) {cC['P_delta_sup_0']:.4f}")
    print(f"\nJSON -> {OUT_JSON}")
    print(f"SHA-256 : {digest}")


if __name__ == "__main__":
    main()
