#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_flux_local.py — VAGUE 5 : LE BANC DE TEST LOCAL DES FLUX DORMANTS
(le flux taker natif des klines + le funding multi-années deviennent des
signaux MESURÉS, avec la grille PRÉ-DÉCLARÉE et le critère AUC du domaine).

Deux séries massives, gratuites et natives, n'ont JAMAIS servi de signal dans
le domaine — c'est le pouvoir dormant exactement pointé par le diagnostic
« tu as des outils puissants gratuits et tu n'exploites aucun pouvoir » :
  (i)  le FLUX TAKER natif des klines Binance 1h (taker_buy_quote_volume :
       la quote agressive côté acheteur, à chaque barre, 80 symboles x 1 092 j)
       — le proxy HISTORIQUE de l'absorption que la vague 2 exploite en live
       via l'orderbook kScript ;
  (ii) le FUNDING Binance 8h multi-années (3 285 paiements par symbole)
       — le thermomètre du positionnement (crowding long/short).

LA DISCIPLINE (pré-enregistrée le 01/10/2026, AVANT toute mesure — les
conventions et la grille ci-dessous sont gravées, aucune cellule n'a été
regardée avant l'écriture de ce fichier) :

  GRILLE PRÉ-DÉCLARÉE (TOUTES les cellules sont mesurées et rapportées,
  même celles qui déçoivent — aucun choix post-hoc de lookback) :
    A. FLUX TAKER : D = 2*tbqv/qv - 1 (agression nette acheteur de la barre),
       score = EMA(D, L) sur les barres CLOTURÉES, L dans {6, 24, 72} barres 1h,
       horizon forward H dans {24, 72} barres (open -> open, doctrine _MK).
    B. FUNDING : score = moyenne des K derniers paiements 8h, K dans
       {9, 21, 90} (= 3/7/30 j), horizon H dans {24, 72} barres 1h.
    C. POOL P1 : les 469 entrées certifiées rejouées avec le score A (L=24)
       et le score B (K=21) au t_in — split médian, R haut vs bas.
  Total : 12 cellules de panel + 2 cellules de pool. TOUTES rapportées.

  HYPOTHÈSES PRÉ-DÉCLARÉES (le sens est gravé AVANT la mesure) :
    H_A : l'agression taker persistante CONTINUE (AUC > 0,5 attendu) —
          c'est le mécanisme absorption/continuation de la vague 2 ;
    H_B : le funding extrême est CONTRARIAN (AUC < 0,5 attendu) —
          crowding long payé cher -> sous-performance forward.

  CONVENTION TEMPS STRICTE (zéro look-ahead) : à l'open de la barre t, les
  barres connues sont celles d'indice <= t-1 (clôture à t-1h) ; les paiements
  de funding connus sont ceux de timestamp <= t (un paiement est connu quand
  il est effectif). Le forward d'une cellule = open(t+H) - open(t) en bps,
  en BARRES (les rares gaps sont comptés et rapportés, l'horizon reste en
  barres). Le pool est évalué à t_in exactement comme le panel (barres
  clôturées <= t_in), cohérent avec la doctrine entry == open(t_in).

  VERDICT MÉCANIQUE PAR CELLULE (critère AUC du domaine, celui qui a exigé
  AUC >= 0,60 sur 60 j frais pour le ML — le même seuil, appliqué AVANT
  toute dépense de runs kScript) :
    KILL       l'IC 95 % (bootstrap 1 000 par journées UTC, seed 501)
               CONTIENT 0,5 et |AUC - 0,5| < 0,02 -> aucun pouvoir, cellule
               morte ; une famille dont TOUTES les cellules tombent est close
               au registre (falsification, la question ne sera pas re-posée).
    INCONCLU   l'IC contient 0,5 -> renvoyé au forward, pas de conclusion.
    CANDIDAT   l'IC EXCLUT 0,5 ET |AUC - 0,5| >= 0,05 ET le sens CONFIRME
               l'hypothèse pré-déclarée -> pré-enregistrable au registre
               docs/20 (statut CANDIDAT, re-test 60 j frais exigé, JAMAIS de
               promotion directe depuis ce banc).
    CONTEXTE   l'IC exclut 0,5 mais le sens OPPOSE l'hypothèse pré-déclarée
               -> hint post-hoc, statut CONTEXTE (convention registre 27/09 :
               pré-enregistrement obligatoire avant tout re-test).

  ÉTUDE C — CONTEXTE PAR NATURE : le pool P1 est l'échantillon qui a SÉLECTIONNÉ
  les alphas, tout effet y est in-sample de la sélection ; les chiffres de C
  servent à SIZE le filtre sur le plan réel (combien d'entrées seraient
  filtrées, delta de R), jamais à promouvoir. Le bootstrap de C réutilise la
  mécanique du moteur x501_verdict_ab.py (10 000, seed 501, diff de médiane).

  BANDES DE COÛTS (rappel docs/26) : taker 6,1 bps/côté, maker 2 bps/côté —
  un filtre n'est exploitable que si l'écart qu'il crée dépasse le coût de
  l'exécution qu'il déclenche ; les deltas de C sont lus contre 12,2 bps
  aller-retour taker.

Limites assumées (pré-enregistrées) :
  L1 le flux taker des klines est le flux BINANCE, pas celui d'openmarket —
     le banc mesure le MÉCANISME (l'absorption a-t-elle un pouvoir de
     continuation sur perps USDT 1h), pas le symbole de trading exact ;
  L2 le funding Binance est le thermomètre de positionnement Binance, la
     cross-exchange divergence (Bybit 66 j) est trop courte pour conclure ;
  L3 l'IC bootstrap rééchantillonne les JOURNÉES (clusters de 24 barres) et
     évalue l'AUC sur un échantillon réduit déterministe de 50 000 points
     par cellule (contrainte CPU ; l'AUC ponctuelle, elle, est full-sample) ;
  L4 l'AUC de dichotomie à la médiane mesure la séparation HAUT/BAS, pas la
     forme monotone de la relation (les déciles de C et de B donnent la
     forme, à lire comme descriptif) ;
  L5 les 2 horizons {24, 72} barres sont en barres, pas en heures calendaires
     (gaps rares, comptés) — cohérent avec la doctrine _MK des entrées à
     l'open.

Reproduction :
  X501_DATA_DIR=<dir des {SYM}_1h.csv et {SYM}_funding.csv> \\
      python3 x501_flux_local.py
  (défaut : data/x501_1h du repo — même convention que x501_fill_maker_surface)
Sorties : flux_local.json (versionné, déterministe) + résumé console.
"""
import csv
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("X501_DATA_DIR", HERE / "../../../data/x501_1h"))
POOL_CSV = HERE / "pool_P1_entrees.csv"
OUT_JSON = HERE / "flux_local.json"

# ---------------------- grille PRÉ-DÉCLARÉE (01/10/2026) ----------------------
LOOKBACKS_FLUX = [6, 24, 72]          # barres 1h
LOOKBACKS_FUND = [9, 21, 90]          # paiements 8h (3/7/30 j)
HORIZONS = [24, 72]                   # barres 1h (open -> open)
POOL_SCORE_A = 24                     # L du score A projeté sur le pool
POOL_SCORE_B = 21                     # K du score B projeté sur le pool

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


# ------------------------------- utils ----------------------------------------
def ema(x, span):
    """EMA récursive (lambda = 2/(span+1)), renvoie y (y[0] = x[0])."""
    lam = 2.0 / (span + 1.0)
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = lam * x[i] + (1.0 - lam) * y[i - 1]
    return y


def rangs_moyens(x):
    """Rangs 1..n avec rangs moyens sur les ex-aequo (vectorisé, stable).

    Les opens répétés des symboles illiquides créent des rendements forward
    ÉGAUX bit à bit : des milliers de blocs d'ex-aequo — la boucle Python
    pure est catastrophique (192 s profilées) ; bornes de blocs + np.repeat
    donnent le même résultat à l'octet près en O(n)."""
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
    chaque journée tirée reconstitue haut+bas ensemble."""
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
def load_klines(sym):
    p = DATA_DIR / f"{sym}_1h.csv"
    if not p.exists():
        return None
    # colonnes du format Binance : 0 open_time, 1 open, 4 close,
    # 7 quote_volume, 10 taker_buy_quote_volume (csv.reader = 3x plus
    # rapide que DictReader sur 2 M lignes, mêmes floats parsés)
    cols = ("open_time", "open", "close", "quote_volume", "taker_buy_quote_volume")
    idx = (0, 1, 4, 7, 10)
    buf = {c: [] for c in cols}
    with open(p, newline="") as f:
        rd = csv.reader(f)
        next(rd)  # en-tête
        for row in rd:
            for c, i in zip(cols, idx):
                buf[c].append(float(row[i]))
    return {c: np.asarray(v, dtype=np.float64) for c, v in buf.items()}


def load_funding(sym):
    p = DATA_DIR / f"{sym}_funding.csv"
    if not p.exists():
        return None
    t, r = [], []
    with open(p, newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            t.append(float(row[0]))
            r.append(float(row[1]))
    return np.asarray(t), np.asarray(r)


# ------------------------------ études ----------------------------------------
def cellule_panel(score, fwd, jours, hypothese, sens_attendu):
    """Une cellule de panel : AUC full-sample, IC bootstrap par journées,
    verdict mécanique (critère du domaine)."""
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


def main():
    syms = sorted(p.name[:-7] for p in DATA_DIR.glob("*_1h.csv"))
    if not syms:
        raise SystemExit(f"aucune kline dans {DATA_DIR} (X501_DATA_DIR ?)")
    fam_a = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_FLUX for h in HORIZONS}
    fam_b = {(k, h): {"s": [], "f": [], "j": []} for k in LOOKBACKS_FUND for h in HORIZONS}
    n_gaps, n_bars_tot, fen_t0, fen_t1 = 0, 0, None, None

    for sym in syms:
        kl = load_klines(sym)
        fd = load_funding(sym)
        if kl is None or fd is None:
            continue
        ot, op, qv, tb = kl["open_time"], kl["open"], kl["quote_volume"], kl["taker_buy_quote_volume"]
        n = len(ot)
        n_bars_tot += n
        fen_t0 = ot[0] if fen_t0 is None else min(fen_t0, ot[0])
        fen_t1 = ot[-1] if fen_t1 is None else max(fen_t1, ot[-1])
        if n > 1:
            n_gaps += int((np.diff(ot) != MS_H).sum())
        # flux taker : D de chaque barre (connu à sa CLÔTURE = ot + 1h)
        with np.errstate(invalid="ignore", divide="ignore"):
            D = np.where(qv > 0, 2.0 * tb / qv - 1.0, np.nan)
        fwd = {}
        for h in HORIZONS:
            ret = np.full(n, np.nan)
            if n > h:
                ret[:n - h] = (op[h:] - op[:n - h]) / op[:n - h] * 1e4
            fwd[h] = ret
        jours = (ot // MS_J).astype(np.int64)
        # ÉTUDE A — score A(t) = EMA(D)[t-1] (barres clôturées <= t)
        for lb in LOOKBACKS_FLUX:
            e = ema(np.nan_to_num(D, nan=0.0), lb)  # barre sans volume = pas
            # d'information : D=0 injecté, l'EMA décroît vers la neutralité
            s_full = np.full(n, np.nan)
            s_full[1:] = e[:-1]
            for h in HORIZONS:
                c = fam_a[(lb, h)]
                ok = np.isfinite(s_full) & np.isfinite(fwd[h])
                c["s"].append(s_full[ok]); c["f"].append(fwd[h][ok]); c["j"].append(jours[ok])
        # ÉTUDE B — funding : moyennes glissantes K sur les paiements <= t
        ft, fr = fd
        pref = np.concatenate([[0.0], np.cumsum(fr)])
        slots = {}
        for k in LOOKBACKS_FUND:
            m = np.full(len(ft), np.nan)
            m[k - 1:] = (pref[k:] - pref[:len(fr) - k + 1]) / k
            slots[k] = (ft, m)
        for k in LOOKBACKS_FUND:
            fts, mv = slots[k]
            idx = np.searchsorted(fts, ot, side="right") - 1
            ok_idx = idx >= 0
            s_full = np.full(n, np.nan)
            s_full[ok_idx] = mv[idx[ok_idx]]
            for h in HORIZONS:
                c = fam_b[(k, h)]
                ok = np.isfinite(s_full) & np.isfinite(fwd[h])
                c["s"].append(s_full[ok]); c["f"].append(fwd[h][ok]); c["j"].append(jours[ok])

    # ---------------- verdict des 12 cellules de panel -------------------------
    res_a, res_b = {}, {}
    boots_a, boots_b = [], []  # (cellule, verdict) pour le comptage
    for lb in LOOKBACKS_FLUX:
        for h in HORIZONS:
            c = fam_a[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "continuation (H_A)", +1)
            res_a[f"L{lb}_H{h}"] = r
            boots_a.append(r["verdict"])
    for k in LOOKBACKS_FUND:
        for h in HORIZONS:
            c = fam_b[(k, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "contrarian (H_B)", -1)
            res_b[f"K{k}_H{h}"] = r
            boots_b.append(r["verdict"])

    # ------------------------- ÉTUDE C — pool P1 --------------------------------
    pool = []
    with open(POOL_CSV, newline="") as f:
        for row in csv.DictReader(f):
            pool.append((row["sym"], int(row["t_in"]), float(row["R"]), row["alpha"]))
    cache = {}
    def serie(sym):
        if sym not in cache:
            kl, fd = load_klines(sym), load_funding(sym)
            if kl is None or fd is None:
                cache[sym] = None
            else:
                ot = kl["open_time"]
                qv, tb = kl["quote_volume"], kl["taker_buy_quote_volume"]
                with np.errstate(invalid="ignore", divide="ignore"):
                    D = np.where(qv > 0, 2.0 * tb / qv - 1.0, np.nan)
                e24 = ema(np.nan_to_num(D, nan=0.0), POOL_SCORE_A)
                sA = np.full(len(ot), np.nan)
                sA[1:] = e24[:-1]
                ft, fr = fd
                pref = np.concatenate([[0.0], np.cumsum(fr)])
                mv = np.full(len(ft), np.nan)
                mv[POOL_SCORE_B - 1:] = (pref[POOL_SCORE_B:] - pref[:len(fr) - POOL_SCORE_B + 1]) / POOL_SCORE_B
                idx_f = np.searchsorted(ft, ot, side="right") - 1
                sB = np.full(len(ot), np.nan)
                okf = idx_f >= 0
                sB[okf] = mv[idx_f[okf]]
                cache[sym] = (ot, sA, sB)
        return cache[sym]

    rows = []
    for sym, t_in, R, alpha in pool:
        sc = serie(sym)
        if sc is None:
            continue
        ot, sA, sB = sc
        i = int(np.searchsorted(ot, t_in, side="left"))
        if i >= len(ot) or ot[i] != t_in:
            continue  # t_in doit être un open exact (doctrine _MK)
        rows.append((sA[i], sB[i], R, alpha))
    n_pool = len(rows)
    sA_pool = np.array([r[0] for r in rows])
    sB_pool = np.array([r[1] for r in rows])
    R_pool = np.array([r[2] for r in rows])
    alpha_pool = np.array([r[3] for r in rows])

    def etude_c(scores, nom):
        ok = np.isfinite(scores)
        s, R = scores[ok], R_pool[ok]
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
        return {
            "nom": nom, "n": int(ok.sum()), "n_hors": int((~ok).sum()),
            "mediane_split": med, "n_haut": int(haut.sum()), "n_bas": int((~haut).sum()),
            "R_med_haut": float(np.median(R[haut])), "R_med_bas": float(np.median(R[~haut])),
            "R_moy_haut": float(R[haut].mean()), "R_moy_bas": float(R[~haut].mean()),
            "WR_haut": 100.0 * float((R[haut] > 0).mean()), "WR_bas": 100.0 * float((R[~haut] > 0).mean()),
            "delta_med_R": float(np.median(R[haut]) - np.median(R[~haut])),
            "ic95_delta_med": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
            "P_delta_sup_0": p_sup,
            "statut": "CONTEXTE (in-sample du pool, jamais promotion)",
        }

    cA = etude_c(sA_pool, f"flux_EMA_L{POOL_SCORE_A}")
    cB = etude_c(sB_pool, f"funding_K{POOL_SCORE_B}")

    # ------------------------------ sorties -------------------------------------
    compte_a = {v: boots_a.count(v) for v in sorted(set(boots_a))}
    compte_b = {v: boots_b.count(v) for v in sorted(set(boots_b))}
    out = {
        "outils": "x501_flux_local.py — vague 5 : banc de test local des flux dormants",
        "grille_pre_declaree": {
            "date": "2026-10-01", "flux_lookbacks_barres": LOOKBACKS_FLUX,
            "funding_lookbacks_paiements": LOOKBACKS_FUND, "horizons_barres": HORIZONS,
            "hypothese_A": "continuation (AUC>0,5 attendu)",
            "hypothese_B": "contrarian (AUC<0,5 attendu)",
            "criterion": f"AUC IC95 exclut 0,5 et |AUC-0,5|>={AUC_CANDIDAT} = CANDIDAT ; "
                         f"IC contient 0,5 et |AUC-0,5|<{AUC_MORTE} = KILL ; sinon INCONCLU",
        },
        "fenetre": {
            "data_dir": str(DATA_DIR), "n_symboles": len(syms), "n_symboles_2_series": None,
            "n_barres_1h": n_bars_tot, "t0": fen_t0, "t1": fen_t1,
            "gaps_1h": n_gaps, "cout_ar_taker_bps": COUT_AR_TAKER_BPS,
        },
        "etude_A_flux_taker": res_a, "etude_B_funding": res_b,
        "resume_verdicts": {"A": compte_a, "B": compte_b},
        "etude_C_pool_P1": {"n_pool_utilise": n_pool, "score_A": cA, "score_B": cB},
    }
    # complétion : n_symboles avec les 2 séries
    out["fenetre"]["n_symboles_2_series"] = len(cache) if cache else None
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    # ------------------------------ console -------------------------------------
    print(f"FLUX LOCAL — {len(syms)} symboles, {n_bars_tot} barres 1h, gaps {n_gaps}")
    print(f"  fenêtre : {fen_t0} -> {fen_t1}")
    print("\nÉTUDE A — flux taker (H_A : continuation, AUC>0,5 attendu)")
    for k, r in res_a.items():
        print(f"  {k:>9}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.1f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print("\nÉTUDE B — funding (H_B : contrarian, AUC<0,5 attendu)")
    for k, r in res_b.items():
        print(f"  {k:>9}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.1f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print("\nÉTUDE C — pool P1 (CONTEXTE, in-sample de la sélection)")
    for c in (cA, cB):
        print(f"  {c['nom']}: n {c['n']}  R méd haut {c['R_med_haut']:+.3f} vs bas {c['R_med_bas']:+.3f}"
              f"  delta {c['delta_med_R']:+.3f}  P(delta>0) {c['P_delta_sup_0']:.4f}")
    print(f"\nJSON -> {OUT_JSON}")


if __name__ == "__main__":
    main()
