#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_oi_local.py — VAGUE 8 : LE BANC DE TEST LOCAL DE L'OPEN INTEREST 1h
(la dernière grande matière première gratuite jamais lue comme signal —
docs/26 : « l'entrepôt reste la matière première des prochains bancs,
OI 1h en tête »).

L'OPEN INTEREST (le capital total affiché sur le perp) n'a été testé dans le
domaine qu'une seule fois, en événement CONTRARIEN : le gate « flush OI »
(ΔOI 6h <= -4,5 %, docs/25 falsification n°2) — +0,1/+0,2 bps dédupliqué,
KILL. L'hypothèse INVERSE — l'OI comme TÉMOIN DE CONTINUATION (le capital qui
finance la tendance) — n'a JAMAIS été mesurée : c'est la question de la
vague 8, pré-enregistrée ici AVANT toute mesure, conformément à la règle
docs/26 (« tout re-test exige un pré-enregistrement explicite d'une hypothèse
nouvelle au registre, pas un re-run de curiosité »).

LA DISCIPLINE (pré-enregistrée le 01/10/2026, AVANT toute mesure — les
conventions et la grille ci-dessous sont gravées, aucune cellule n'a été
regardée avant l'écriture de ce fichier) :

  GRILLE PRÉ-DÉCLARÉE (TOUTES les cellules sont mesurées et rapportées,
  même celles qui déçoivent — aucun choix post-hoc de lookback) :
    A. CAPITAL BRUT : score = ΔOI%_L = 100 x (OI[t-1] / OI[t-1-L] - 1),
       L dans {24, 72, 168} barres 1h, horizon forward H dans {24, 72}
       barres (open -> open, doctrine _MK). Dichotomie à la médiane
       (convention vague 5). H_OI1 : l'expansion du capital annonce la
       HAUSSE (AUC > 0,5 attendu).
    B. MOUVEMENT FINANCÉ (quadrant OI x prix) : score = signe(r_L) x ΔOI%_L
       avec r_L = close[t-1]/close[t-1-L] - 1 — positif quand le mouvement
       récent est financé dans son sens (OI↑ avec prix↑, OI↓ avec prix↓),
       négatif quand il ne l'est pas. Cible ALIGNÉE : fwd x signe(r_L).
       L dans {24, 72} x H dans {24, 72} = 4 cellules. H_OI2 : le mouvement
       financé CONTINUE (AUC > 0,5 attendu) — c'est l'hypothèse raffinée
       du quadrant, la seule que la théorie du levier distingue.
    C. POOL P1 : les 469 entrées certifiées rejouées avec ΔOI%_24h au t_in
       (snapshot <= t_in - 1h) — split médian, R haut vs bas. CONTEXTE par
       nature (in-sample de la sélection), jamais promotion.
  Total : 10 cellules de panel + 1 cellule de pool. TOUTES rapportées.

  CONVENTION TEMPS STRICTE (zéro look-ahead, transposée de la correction
  v27 docs/26) : le timestamp d'un snapshot OI marque l'OUVERTURE de sa
  fenêtre horaire (état mesuré à hh:00). À l'open de la barre t, le dernier
  snapshot CONNU est celui de t-1h — le snapshot t:00 paraît SIMULTANÉMENT
  à l'open et n'est JAMAIS lu. Les décisions exigent l'existence PILE des
  snapshots aux timestamps requis (aucun fill-forward silencieux : une
  absence de snapshot invalide la décision, comptée et rapportée).
  Klines connues à l'open de t : indices <= t-1. Forward = open(t+H) -
  open(t) en bps, en BARRES (gaps rares comptés et rapportés).

  VERDICT MÉCANIQUE PAR CELLULE (critère AUC du domaine, inchangé vague 5 :
  KILL si IC 95 % contient 0,5 et |AUC-0,5| < 0,02 ; INCONCLU si l'IC
  contient 0,5 ; CANDIDAT si l'IC EXCLUT 0,5 ET |AUC-0,5| >= 0,05 ET le sens
  confirme l'hypothèse pré-déclarée ; CONTEXTE si l'IC exclut 0,5 mais le
  sens s'y OPPOSE. L'IC = bootstrap 1 000 par journées UTC, seed 501,
  réduction 50 000 — la mécanique exacte de x501_flux_local.py).

  BANDES DE COÛTS (rappel docs/26) : taker 6,1 bps/côté, maker 2 bps/côté ;
  l'étalon d'exploitabilité d'un filtre = 12,2 bps aller-retour taker. Un
  delta sans AUC n'est pas un plan (leçon vague 7) : les deltas médianes
  rapportés ici sont DESCRIPTIFS, le verdict appartient à l'AUC.

  PANEL : les 12 symboles om_v27 (manifeste docs/26, liste v17 à
  l'identique) — BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, SUI, APT,
  1000PEPE (USDT). Klines 1h ET OI 1h du MÊME exchange (Bybit v5, catégorie
  linear) : la sémantique d'exécution du domaine (Bybit VIP0, docs/25),
  zéro cross-exchange dans le panel. La profondeur OI réelle Bybit (mesurée
  à la collecte : ~4,4 ans disponibles) dépasse largement la fenêtre
  klines collectée (~740 j) : la fenêtre d'étude = la fenêtre KLINE commune,
  l'OI excédentaire reste disponible pour les bancs futurs.

Limites assumées (pré-enregistrées) :
  L1 l'OI Bybit est le capital Bybit, pas le capital global cross-exchange —
     le banc mesure le MÉCANISME (le capital affiché d'un perps liquide a-t-il
     un pouvoir de continuation), pas le marché total ;
  L2 l'étude C croise des entrées pool (data Binance, vague 4) avec l'OI
     Bybit — cross-exchange assumé (arbitrage à la seconde), CONTEXTE par
     nature, JAMAIS promotion ;
  L3 l'IC bootstrap rééchantillonne les JOURNÉES (clusters 24 h) et évalue
     l'AUC sur un échantillon réduit déterministe de 50 000 points par
     cellule (contrainte CPU ; l'AUC ponctuelle est full-sample) ;
  L4 l'étude C n'est évaluable que sur les entrées dont le symbole appartient
     au panel 12 (n utilisé et n hors rapportés) ;
  L5 les horizons sont en barres, pas en heures calendaires (gaps rares,
     comptés) — cohérent avec la doctrine _MK des entrées à l'open ;
  L6 la dichotomie à la médiane mesure la séparation HAUT/BAS, pas la forme
     monotone de la relation (L4 vague 5) — les déciles restent descriptifs
     et ne sont pas rapportés dans ce banc.

Reproduction :
  X501_OI_DIR=<dir des {SYM}_klines.jsonl et {SYM}_oi.jsonl> \\
      python3 x501_oi_local.py
  (défaut : data/x501_oi du repo — collecte re-exécutable depuis les
  endpoints publics Bybit v5 listés dans docs/33, fenêtres exactes gravées
  dans le manifest de collecte)
Sorties : oi_local.json (versionné, déterministe) + résumé console.
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
OUT_JSON = HERE / "oi_local.json"

# ---------------------- grille PRÉ-DÉCLARÉE (01/10/2026) ----------------------
LOOKBACKS_CAPITAL = [24, 72, 168]     # barres 1h (étude A)
LOOKBACKS_FINANCE = [24, 72]          # barres 1h (étude B)
HORIZONS = [24, 72]                   # barres 1h (open -> open)
POOL_L = 24                           # L du ΔOI% projeté sur le pool

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
    Mécanique exacte de la vague 5 (x501_flux_local.py) : bornes de blocs +
    np.repeat, identique à l'octet près à la boucle Python de référence."""
    n = len(x)
    ordre = np.argsort(x, kind="mergesort")
    sx = x[ordre]
    fin = np.append(np.flatnonzero(np.diff(sx) != 0.0), n - 1)  # fin de bloc
    deb = np.append(0, fin[:-1] + 1)                             # début de bloc
    moyennes = (deb + fin) / 2.0 + 1.0                            # rang moyen
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
    (clusters 24h, limite L3), évaluation sur l'échantillon réduit — la
    dichotomie (flag) et la valeur (fwd) sont portées par les MÊMES points,
    chaque journée tirée reconstitue haut+bas ensemble. Mécanique exacte
    de la vague 5."""
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
    ts, n_dbl = np.unique(a[:, 0], return_counts=True)
    n_dup = int((n_dbl - 1).sum())
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
    """Snapshot OI aligné PILE sur chaque barre kline (dict par timestamp) :
    arr[j] = OI au ts de la barre j, NaN si le snapshot n'existe pas pile.
    Aucun fill-forward : une absence invalide les décisions qui la lisent."""
    n = len(ot)
    arr = np.full(n, np.nan)
    idx = np.searchsorted(oi_ts, ot)
    ok = (idx < len(oi_ts)) & (oi_ts[np.minimum(idx, len(oi_ts) - 1)] == ot)
    arr[ok] = oi_val[idx[ok]]
    return arr


# ------------------------------ cellules --------------------------------------
def cellule_panel(score, fwd, jours, hypothese, sens_attendu):
    """Une cellule de panel : AUC full-sample, IC bootstrap par journées,
    verdict mécanique (critère du domaine) — mécanique exacte vague 5."""
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
        confirme = (auc > 0.5) if sens_attendu > 0 else (auc < 0.5)
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
    fam_a = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_CAPITAL for h in HORIZONS}
    fam_b = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_FINANCE for h in HORIZONS}
    n_bars_tot, n_dup_k, n_dup_o = 0, 0, 0
    n_snap_absents, n_barres_invalidees = 0, 0
    fen_t0, fen_t1 = None, None
    audit_syms = {}
    oi_profondeurs = {}

    for sym in SYMBOLS:
        kl = load_klines_bybit(sym)
        oi = load_oi_bybit(sym)
        if kl is None or oi is None:
            raise SystemExit(f"data manquante pour {sym} dans {OI_DIR}")
        ot, op, cl = kl["ts"], kl["o"], kl["c"]
        n = len(ot)
        n_bars_tot += n
        n_dup_k += kl["n_dup"]
        n_dup_o += oi["n_dup"]
        fen_t0 = ot[0] if fen_t0 is None else min(fen_t0, ot[0])
        fen_t1 = ot[-1] if fen_t1 is None else max(fen_t1, ot[-1])
        oi_profondeurs[sym] = int(oi["ts"][0])
        gaps_k = int((np.diff(ot) != MS_H).sum())
        gaps_o = int((np.diff(oi["ts"]) != MS_H).sum())
        # le chevauchement éventuel de la collecte OI (fin de fenêtre) ne
        # compte pas comme gap : on n'audite que l'intérieur de la fenêtre kline
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
        def delta_oi(lb):
            """ΔOI%_L à la barre j : OI[j] / OI[j-L] (les 2 snapshots PILE)."""
            d = np.full(n, np.nan)
            if lb < n:
                with np.errstate(invalid="ignore", divide="ignore"):
                    d[lb:] = 100.0 * (arr_oi[lb:] / arr_oi[:n - lb] - 1.0)
            return d

        for lb in LOOKBACKS_CAPITAL:
            d = delta_oi(lb)
            s_full = np.full(n, np.nan)
            s_full[1:] = d[:-1]
            if lb == 24:  # comptage figé au L du pool (sinon cumul trompeur)
                n_barres_invalidees += int((np.isnan(d[:-1]) & np.isfinite(fwd[24][1:])).sum())
            for h in HORIZONS:
                c = fam_a[(lb, h)]
                ok = np.isfinite(s_full) & np.isfinite(fwd[h])
                c["s"].append(s_full[ok]); c["f"].append(fwd[h][ok]); c["j"].append(jours[ok])
        for lb in LOOKBACKS_FINANCE:
            d = delta_oi(lb)
            rl = np.full(n, np.nan)
            if lb < n:
                rl[lb:] = cl[lb:] / cl[:n - lb] - 1.0
            sg = np.sign(rl)
            s2_full = np.full(n, np.nan)
            s2_full[1:] = sg[:-1] * d[:-1]
            for h in HORIZONS:
                c = fam_b[(lb, h)]
                f2 = fwd[h] * sg  # cible alignée momentum (0 si r_L == 0)
                ok = np.isfinite(s2_full) & np.isfinite(f2)
                c["s"].append(s2_full[ok]); c["f"].append(f2[ok]); c["j"].append(jours[ok])

    # ---------------- verdict des 10 cellules de panel -------------------------
    res_a, res_b, verdicts = {}, {}, []
    for lb in LOOKBACKS_CAPITAL:
        for h in HORIZONS:
            c = fam_a[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "continuation du capital (H_OI1)", +1)
            res_a[f"L{lb}_H{h}"] = r
            verdicts.append(r["verdict"])
    for lb in LOOKBACKS_FINANCE:
        for h in HORIZONS:
            c = fam_b[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "continuation financée (H_OI2)", +1)
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
                ot, op = kl["ts"], kl["o"]
                arr = snap_oi_sur_barres(ot, oi["ts"], oi["oi"])
                d = np.full(len(ot), np.nan)
                with np.errstate(invalid="ignore", divide="ignore"):
                    d[POOL_L:] = 100.0 * (arr[POOL_L:] / arr[:len(ot) - POOL_L] - 1.0)
                s_full = np.full(len(ot), np.nan)
                s_full[1:] = d[:-1]  # le snapshot t_in:00 n'est JAMAIS lu
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
    med = float(np.median(s))
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
        "nom": f"delta_oi_L{POOL_L}", "n": int(ok.sum()), "n_hors_panel": n_hors_panel,
        "mediane_split": med, "n_haut": int(haut.sum()), "n_bas": int((~haut).sum()),
        "R_med_haut": float(np.median(R[haut])), "R_med_bas": float(np.median(R[~haut])),
        "R_moy_haut": float(R[haut].mean()), "R_moy_bas": float(R[~haut].mean()),
        "WR_haut": 100.0 * float((R[haut] > 0).mean()), "WR_bas": 100.0 * float((R[~haut] > 0).mean()),
        "delta_med_R": float(np.median(R[haut]) - np.median(R[~haut])),
        "ic95_delta_med": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
        "P_delta_sup_0": p_sup,
        "statut": "CONTEXTE (in-sample du pool + cross-exchange L2, jamais promotion)",
    }

    # ------------------------------ sorties -------------------------------------
    compte = {v: verdicts.count(v) for v in sorted(set(verdicts))}
    out = {
        "outils": "x501_oi_local.py — vague 8 : banc de test local de l'open interest 1h",
        "grille_pre_declaree": {
            "date": "2026-10-01", "capital_lookbacks_barres": LOOKBACKS_CAPITAL,
            "finance_lookbacks_barres": LOOKBACKS_FINANCE, "horizons_barres": HORIZONS,
            "hypothese_A": "expansion du capital -> hausse (H_OI1, AUC>0,5 attendu)",
            "hypothese_B": "mouvement financé -> continuation (H_OI2, AUC>0,5 attendu)",
            "criterion": f"AUC IC95 exclut 0,5 et |AUC-0,5|>={AUC_CANDIDAT} = CANDIDAT ; "
                         f"IC contient 0,5 et |AUC-0,5|<{AUC_MORTE} = KILL ; sinon INCONCLU",
            "panel": SYMBOLS, "pool_L": POOL_L,
        },
        "fenetre": {
            "oi_dir": OI_DIR.name, "n_symboles": len(SYMBOLS),
            "n_barres_1h": n_bars_tot, "t0": int(fen_t0), "t1": int(fen_t1),
            "dup_klines": n_dup_k, "dup_oi": n_dup_o,
            "snap_absents": n_snap_absents,
            "decisions_invalidees_A": n_barres_invalidees,
            "oi_profondeur_min_ts": min(oi_profondeurs.values()),
            "cout_ar_taker_bps": COUT_AR_TAKER_BPS,
        },
        "audit_par_symbole": audit_syms,
        "etude_A_capital_brut": res_a, "etude_B_mouvement_finance": res_b,
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
    print(f"OI LOCAL — {len(SYMBOLS)} symboles, {n_bars_tot} barres 1h, "
          f"doublons k={n_dup_k} o={n_dup_o}, snap absents {n_snap_absents}")
    print(f"  fenêtre : {fen_t0} -> {fen_t1}")
    print("\nÉTUDE A — capital brut ΔOI% (H_OI1 : continuation, AUC>0,5 attendu)")
    for k, r in res_a.items():
        print(f"  {k:>9}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.1f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print("\nÉTUDE B — mouvement financé (H_OI2 : continuation, AUC>0,5 attendu)")
    for k, r in res_b.items():
        print(f"  {k:>9}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.1f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print(f"\nRésumé verdicts panel : {compte}")
    print(f"\nÉTUDE C — pool P1 (CONTEXTE, in-sample + cross-exchange L2)")
    print(f"  n {cC['n']} (hors panel {cC['n_hors_panel']})  "
          f"R méd haut {cC['R_med_haut']:+.3f} vs bas {cC['R_med_bas']:+.3f}  "
          f"delta {cC['delta_med_R']:+.3f}  P(delta>0) {cC['P_delta_sup_0']:.4f}")
    print(f"\nJSON -> {OUT_JSON}")
    print(f"SHA-256 : {digest}")


if __name__ == "__main__":
    main()
