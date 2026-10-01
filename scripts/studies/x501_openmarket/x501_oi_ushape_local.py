#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_oi_ushape_local.py — VAGUE 10 : LE BANC DE LA FORME EN U DE H_R1
(la case explicitement laissée ouverte par la vague 9 — docs/34, limite L8 :
« la dichotomie médiane ne capte que le monotone — une extension exigerait
un pré-enregistrement ultérieur »).

LA DISCRIMINATION AVEC LA VAGUE 9 (pré-enregistrée le 01/10/2026, AVANT
toute mesure — aucune cellule n'a été regardée avant l'écriture de ce
fichier) :
  vague 9 : le NIVEAU du capital z_L(OI) testé MONOTONE (dichotomie
            médiane du score SIGNÉ) -> H_R1 REFUSÉE en marginal (3 KILL +
            1 INCONCLU), conditionnel vivant dans le pool (delta +0,469,
            P = 0,8192) ;
  vague 10 : la FORME. La théorie du levier a une formulation concurrente
            NON monotone, pré-enregistrée ICI : la volatilité est maximale
            aux DEUX EXTRÊMES du régime (capital très haut -> cascades de
            liquidations ; capital très bas -> re-pricing volatil
            post-purge / compression d'OI), le centre (régime normal) est
            calme — la forme en U. Le banc vague 9 était STRUCTURELLEMENT
            aveugle à cette forme (L8 vague 9) : un U laisse la dichotomie
            du score signé quasi muette car les deux côtés se compensent
            dans les rangs.

LA DISCIPLINE (gravée AVANT tout chiffre) :

  GRILLE PRÉ-DÉCLARÉE (TOUTES les cellules sont mesurées et rapportées,
  même celles qui déçoivent) :
    A1. LE U (test JOINT des deux extrêmes) :
        score = |z_L(OI[t-1])| — la distance au centre, centre PRÉ-DÉCLARÉ
        à 0 : le z-score roulant est centré sur sa fenêtre par
        construction, 0 en est le centre naturel (limite L3).
        cible = |fwd_H| (magnitude open->open, doctrine _MK), sens +1.
        Hypothèse U : |fwd| croit quand |z| croit (les deux extrêmes
        sortent du centre calme).
        L dans {720, 2160} x H dans {24, 72} = 4 cellules.
    A2. LE CÔTÉ BAS SEUL (le DISCRIMINANT du U) :
        sous-échantillon z_L(OI[t-1]) < 0 (score SIGNÉ), cible = |fwd_H|,
        sens ATTENDU = -1 : le U prédit que les z TRÈS négatifs
        (l'extrême bas) ont |fwd| GRAND -> AUC < 0,5 pour le score
        croissant. Le monotone H_R1 prédit l'OPPOSÉ (AUC > 0,5).
        L dans {720, 2160} x H dans {24, 72} = 4 cellules.
    B. MIROIR DIRECTIONNEL (test de cohérence, leçon vague 9) :
        score = |z_L(OI[t-1])|, cible = fwd_H SIGNÉ, sens_attendu = 0 —
        la magnitude ne finance pas une direction ; toute séparation
        éventuelle est CONTEXTE par définition (jamais CANDIDAT). 4
        cellules.
    C. POOL P1 (le conditionnel vivant de la vague 9, en strates |z|) :
        les 469 entrées certifiées rejouées, score = |z_720(OI)| au t_in
        (snapshot <= t_in - 1h), strates PRÉ-DÉCLARÉES : EXTRÊMES = |z|
        au-dessus du quantile 80 % du pool, CENTRE = le reste ; bootstrap
        diff de médianes 10 000 (R extrêmes vs R centre, P(delta>0)).
        Hypothèse U : delta > 0. CONTEXTE par nature (in-sample de la
        sélection + cross-exchange L5), jamais promotion. L figé à 720
        (vague 9, le 2160 consommerait ~25 % de la fenêtre kline).
  Total : 12 cellules de panel + 1 cellule de pool. TOUTES rapportées.

  COMPOSITION DU VERDICT U (pré-déclarée, la règle de falsification —
  une LECTURE des verdicts mécaniques, elle ne les remplace pas) :
    le U est VIVANT sur (L,H) seulement si A1 est CANDIDAT (sens +1) ET
    A2 est CANDIDAT (sens -1) sur la MÊME cellule — les deux branches
    sont exigées, l'une sans l'autre est compatible avec un monotone
    asymétrique ;
    le U est KILL-U (contradiction frontale) si A2 sort avec l'AUC > 0,5
    HORS de l'IC (le côté bas va dans le sens MONOTONE : les z très
    négatifs sont calmes — cellule_panel renvoie alors CONTEXTE pour un
    sens_attendu = -1) ;
    sinon le U n'est pas ÉTABLI (plat / INCONCLU / A1 seul).

  CONVENTION TEMPS STRICTE (identique vagues 8/9, transposée bit à bit) :
  le snapshot hh:00 marque l'OUVERTURE de sa fenêtre ; à l'open de t, le
  dernier snapshot CONNU est (t-1):00 ; le snapshot t:00 n'est JAMAIS lu ;
  existence PILE exigée (0 fill-forward, une absence invalide la décision,
  comptée et rapportée). Le |z| lu à l'open de t est la valeur absolue du
  z-score n'agrégant QUE les snapshots <= (t-1):00 (la transformation est
  ponctuelle : |z| appliqué APRÈS le décalage d'une barre). Klines connues
  à l'open de t : indices <= t-1. Forward = open(t+H) - open(t) en bps.

  CAS DÉGÉNÉRÉS PRÉ-DÉCLARÉS : std_L = 0 (fenêtre plate) -> z NaN ->
  décision invalidée, comptée ; OI <= 0 (artefact pré-listing, note QA
  vague 8) -> NaN, compté ; amorçage L-1 barres -> NaN, compté ;
  sous-échantillon A2 (z < 0) : n réduit environ de moitié, le gate
  n >= 100 par côté est INCHANGÉ (hérité) ; ex-aequo gérés par la
  mécanique rangs moyens du domaine (aucune règle nouvelle).

  VERDICT MÉCANIQUE PAR CELLULE (critère AUC du domaine, INCHANGÉ) :
  KILL si IC 95 % contient 0,5 et |AUC-0,5| < 0,02 ; INCONCLU si l'IC
  contient 0,5 ; CANDIDAT si l'IC EXCLUT 0,5 ET |AUC-0,5| >= 0,05 ET le
  sens CONFIRME l'hypothèse pré-déclarée (A1 : +1 ; A2 : -1) ; CONTEXTE
  si l'IC exclut 0,5 mais le sens s'y OPPOSE ou si sens_attendu = 0
  (étude B/C). IC = bootstrap 1 000 par journées UTC, seed 501,
  réduction 50 000 — la mécanique exacte des vagues 5/8/9.

  BANDES DE COÛTS (rappel docs/26) : taker 6,1 bps/côté, maker 2 bps/côté ;
  l'étalon d'exploitabilité = 12,2 bps A/R taker. Un delta sans AUC n'est
  pas un plan (leçon vague 7) : les deltas médianes sont DESCRIPTIFS.

  PANEL : les 12 symboles om_v27 (manifeste docs/26, liste v17 à
  l'identique, INCHANGÉ vague 9), klines 1h ET OI 1h du MÊME exchange
  (Bybit v5, linear) — zéro cross-exchange dans le panel. La fenêtre
  d'étude = la fenêtre KLINE commune ; le z-score roulant (L <= 2160 h)
  reste STRICTEMENT dans cette fenêtre — l'OI pré-2024 N'ENTRE PAS dans
  les statistiques du banc.

Limites assumées (pré-enregistrées) :
  L1 marginal vs conditionnel : le U peut être absent en marginal et
     présent en conditionnel (leçon vague 6 à l'envers) — les DEUX sont
     mesurés et rapportés, aucune promotion croisée ;
  L2 |fwd| open->open n'est pas la volatilité intrabar (L7 vague 9,
     transposée) — c'est la grandeur que le plan x501 capture réellement
     (entrées à l'open, doctrine _MK) ;
  L3 le centre du U est PRÉ-DÉCLARÉ à 0 (le centre naturel du z-score
     standardisé) ; un centre décalé (ex : z = +0,5) serait partiellement
     manqué par |z| — assumé : le z-score est centré par construction ;
  L4 la dichotomie médiane de |z| met ~50 % des barres côté « extrêmes »
     (et non les 40 % des quintiles Q1∪Q5) — la mécanique STANDARD du
     domaine (dichotomie à la médiane) inchangée, aucune règle nouvelle ;
  L5 cross-exchange du pool (data Binance × OI Bybit, arbitrage à la
     seconde — L4 vague 9 transposée), CONTEXTE par nature ;
  L6 l'OI Bybit est le capital Bybit, pas le capital global (L2 vague 9) ;
  L7 l'IC bootstrap rééchantillonne les JOURNÉES (clusters 24 h) et
     évalue l'AUC sur un échantillon réduit déterministe de 50 000 points
     (l'AUC ponctuelle est full-sample) (L3 vague 9) ;
  L8 horizons en barres (gaps rares comptés) — doctrine _MK (L5 vague 9).

Reproduction :
  X501_OI_DIR=<dir des {SYM}_klines.jsonl et {SYM}_oi.jsonl> \
      python3 x501_oi_ushape_local.py
  (défaut : data/x501_oi du repo ; la collecte est re-exécutable avec
  x501_collect_oi_v8.py — collecteur versionné vague 8, inchangé)
Sorties : oi_ushape_local.json (versionné, déterministe) + résumé console.
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
OUT_JSON = HERE / "oi_ushape_local.json"

# ---------------------- grille PRÉ-DÉCLARÉE (01/10/2026) ----------------------
LOOKBACKS_Z = [720, 2160]             # barres 1h (A1/A2/B : 30 j, 90 j)
HORIZONS = [24, 72]                   # barres 1h (open -> open)
POOL_L = 720                          # L du z-score projeté sur le pool (vague 9)
POOL_Q_EXTR = 0.80                    # quantile |z| au-dessus duquel = EXTRÊME

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
    Mécanique exacte des vagues 5/8/9 : bornes de blocs + np.repeat."""
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
    (clusters 24h, limite L7), évaluation sur l'échantillon réduit. Mécanique
    exacte des vagues 5/8/9."""
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
    Sommes cumulées float64 — O(n) par cellule. CAS DÉGÉNÉRÉ (pré-déclaré,
    bug réel corrigé vague 9) : std -> 0 (fenêtre plate) : les erreurs
    d'arrondi float64 de var = s2/L - m^2 laissent un résidu ~1e-14 qui
    produirait z = +-inf ; le score est forcé à NaN quand
    sd <= 1e-6 x max(1, |m|) (seuil RELATIF d'échelle) — une fenêtre plate
    n'informe pas le régime, la décision est invalidée (comptée)."""
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
    est CONTEXTE (jamais CANDIDAT). Mécanique exacte des vagues 5/8/9."""
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


def composition_u(v_a1, v_a2, auc_a2):
    """Lecture de composition PRÉ-DÉCLARÉE (l'en-tête gravé) — elle ne
    remplace jamais les verdicts mécaniques des cellules :
      U VIVANT  = A1 CANDIDAT (sens +1) ET A2 CANDIDAT (sens -1) — les
                  deux branches exigées sur la MÊME cellule ;
      KILL-U    = A2 sort avec l'AUC > 0,5 HORS de l'IC (cellule_panel
                  renvoie CONTEXTE pour un sens_attendu = -1) : le côté
                  bas va dans le sens MONOTONE — contradiction frontale
                  du U ;
      sinon     = U NON ÉTABLI (plat / INCONCLU / A1 seul asymétrique)."""
    if v_a1 == "CANDIDAT" and v_a2 == "CANDIDAT":
        return "U VIVANT"
    if v_a2 == "CONTEXTE" and auc_a2 > 0.5:
        return "KILL-U (monotone par le côté bas)"
    return "U NON ÉTABLI"


# ------------------------------- études ----------------------------------------
def main():
    fam_a1 = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_Z for h in HORIZONS}
    fam_a2 = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_Z for h in HORIZONS}
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
            u_full = np.abs(s_full)      # score A1/B : distance au centre 0
            for h in HORIZONS:
                # A1 — le U : |z| -> |fwd|, sens +1 (les deux extrêmes)
                ok = np.isfinite(u_full) & np.isfinite(fwd[h])
                ca = fam_a1[(lb, h)]
                ca["s"].append(u_full[ok])
                ca["f"].append(np.abs(fwd[h][ok]))   # MAGNITUDE
                ca["j"].append(jours[ok])
                # A2 — le côté bas seul : z signé < 0 -> |fwd|, sens -1
                ok2 = ok & (s_full < 0)
                cb = fam_a2[(lb, h)]
                cb["s"].append(s_full[ok2])
                cb["f"].append(np.abs(fwd[h][ok2]))
                cb["j"].append(jours[ok2])
                # B — miroir directionnel : |z| -> fwd signé, sens = 0
                cbis = fam_b[(lb, h)]
                cbis["s"].append(u_full[ok])
                cbis["f"].append(fwd[h][ok])         # SIGNÉ
                cbis["j"].append(jours[ok])

    # ---------------- verdict des 12 cellules de panel -------------------------
    res_a1, res_a2, res_b, verdicts = {}, {}, {}, []
    for lb in LOOKBACKS_Z:
        for h in HORIZONS:
            c = fam_a1[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "U : |z| haut -> |fwd| haut (les DEUX extrêmes)", +1)
            res_a1[f"L{lb}_H{h}"] = r
            verdicts.append(r["verdict"])
    for lb in LOOKBACKS_Z:
        for h in HORIZONS:
            c = fam_a2[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "côté bas du U : z très négatif -> |fwd| grand (sens -1)", -1)
            res_a2[f"L{lb}_H{h}"] = r
            verdicts.append(r["verdict"])
    for lb in LOOKBACKS_Z:
        for h in HORIZONS:
            c = fam_b[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "magnitude -> direction (aucune hypothèse, sens=0)", 0)
            res_b[f"L{lb}_H{h}"] = r
            verdicts.append(r["verdict"])

    # ---------------- composition du verdict U (pré-déclarée) ------------------
    compo = {}
    for lb in LOOKBACKS_Z:
        for h in HORIZONS:
            k = f"L{lb}_H{h}"
            compo[k] = composition_u(res_a1[k]["verdict"], res_a2[k]["verdict"],
                                     res_a2[k]["auc"])

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
    sP = np.asarray([r[0] for r in rows], dtype=np.float64)
    R_pool = np.asarray([r[1] for r in rows], dtype=np.float64)

    ok = np.isfinite(sP)
    u = np.abs(sP[ok])                 # distance au centre 0 (pré-déclarée)
    R = R_pool[ok]
    q80 = float(np.quantile(u, POOL_Q_EXTR)) if len(u) else float("nan")
    extr = u >= q80                    # EXTRÊMES = |z| >= quantile 80 %
    rng = np.random.default_rng(SEED)
    boots = np.empty(N_BOOT_POOL)
    hi_idx = np.flatnonzero(extr)
    lo_idx = np.flatnonzero(~extr)
    for b in range(N_BOOT_POOL):
        h = R[rng.choice(hi_idx, size=len(hi_idx), replace=True)]
        l = R[rng.choice(lo_idx, size=len(lo_idx), replace=True)]
        boots[b] = float(np.median(h) - np.median(l))
    p_sup = float((boots > 0).mean())
    cC = {
        "nom": f"u_oi_L{POOL_L}_quantile{POOL_Q_EXTR}", "n": int(ok.sum()),
        "n_hors_panel": n_hors_panel,
        "quantile_u": q80, "n_extr": int(extr.sum()), "n_centre": int((~extr).sum()),
        "R_med_extr": float(np.median(R[extr])) if extr.any() else float("nan"),
        "R_med_centre": float(np.median(R[~extr])) if (~extr).any() else float("nan"),
        "R_moy_extr": float(R[extr].mean()) if extr.any() else float("nan"),
        "R_moy_centre": float(R[~extr].mean()) if (~extr).any() else float("nan"),
        "WR_extr": 100.0 * float((R[extr] > 0).mean()) if extr.any() else float("nan"),
        "WR_centre": 100.0 * float((R[~extr] > 0).mean()) if (~extr).any() else float("nan"),
        "delta_med_R": float(np.median(R[extr]) - np.median(R[~extr])) if extr.any() and (~extr).any() else float("nan"),
        "ic95_delta_med": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
        "P_delta_sup_0": p_sup,
        "hypothese": "U : les entrées aux extrêmes |z| font mieux que le centre (delta > 0)",
        "statut": "CONTEXTE (in-sample du pool + cross-exchange L5, jamais promotion)",
    }

    # ------------------------------ sorties -------------------------------------
    compte = {v: verdicts.count(v) for v in sorted(set(verdicts))}
    out = {
        "outils": "x501_oi_ushape_local.py — vague 10 : banc de la forme en U de H_R1",
        "grille_pre_declaree": {
            "date": "2026-10-01", "lookbacks_z_barres": LOOKBACKS_Z,
            "horizons_barres": HORIZONS, "pool_L": POOL_L,
            "pool_quantile_extr": POOL_Q_EXTR,
            "hypothese_A1": "U : |z_L| haut -> |fwd| plus grand (les DEUX extrêmes sortent du centre calme, centre pré-déclaré à 0, sens +1)",
            "hypothese_A2": "côté bas seul (discriminant) : z très négatif -> |fwd| grand (sens -1) — le monotone H_R1 prédit l'opposé",
            "hypothese_B": "magnitude -> direction : AUCUNE hypothèse pré-déclarée (sens=0, toute séparation = CONTEXTE)",
            "hypothese_C": "U : les entrées du pool aux extrêmes |z_720| font mieux que le centre (delta > 0)",
            "composition_U": "U VIVANT = A1 CANDIDAT(+1) ET A2 CANDIDAT(-1) même cellule ; KILL-U = A2 AUC>0,5 hors IC ; sinon NON ÉTABLI",
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
        "etude_A1_u_joint": res_a1, "etude_A2_cote_bas": res_a2,
        "etude_B_miroir_direction": res_b,
        "resume_verdicts_panel": compte,
        "composition_u": compo,
        "etude_C_pool_P1": cC,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    digest = hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    out["digest_sha256"] = digest
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    # ------------------------------ console -------------------------------------
    print(f"OI USHAPE — {len(SYMBOLS)} symboles, {n_bars_tot} barres 1h, "
          f"doublons k={n_dup_k} o={n_dup_o}, snap absents {n_snap_absents}")
    print(f"  invalidées : amorçage L720 {n_invalidees_amorcage}, std0 L720 {n_invalidees_std0}")
    print(f"  fenêtre : {fen_t0} -> {fen_t1}")
    print("\nÉTUDE A1 — LE U : |z_L(OI)| -> |fwd| (les DEUX extrêmes, centre pré-déclaré à 0, sens +1)")
    for k, r in res_a1.items():
        print(f"  {k:>10}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.2f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print("\nÉTUDE A2 — LE CÔTÉ BAS SEUL (discriminant) : z<0 -> |fwd|, sens -1 attendu")
    for k, r in res_a2.items():
        print(f"  {k:>10}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.2f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print("\nCOMPOSITION DU VERDICT U (pré-déclarée : A1 CANDIDAT ET A2 CANDIDAT(-1) requis)")
    for k, v in compo.items():
        print(f"  {k:>10}: {v}")
    print("\nÉTUDE B — MIROIR DIRECTIONNEL : |z_L(OI)| -> fwd signé (aucune hypothèse, sens=0)")
    for k, r in res_b.items():
        print(f"  {k:>10}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.2f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print(f"\nRésumé verdicts panel : {compte}")
    print(f"\nÉTUDE C — pool P1 en strates |z| (CONTEXTE, in-sample + cross-exchange L5)")
    print(f"  n {cC['n']} (hors panel {cC['n_hors_panel']})  q80(|z|) {cC['quantile_u']:.4f}"
          f"  n_extr {cC['n_extr']} vs n_centre {cC['n_centre']}")
    print(f"  R méd extr {cC['R_med_extr']:+.3f} vs centre {cC['R_med_centre']:+.3f}  "
          f"delta {cC['delta_med_R']:+.3f}  P(delta>0) {cC['P_delta_sup_0']:.4f}")
    print(f"\nJSON -> {OUT_JSON}")
    print(f"SHA-256 : {digest}")


if __name__ == "__main__":
    main()
