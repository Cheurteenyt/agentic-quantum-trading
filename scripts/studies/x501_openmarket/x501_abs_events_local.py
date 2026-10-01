#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_abs_events_local.py — VAGUE 6 : LE BANC D'ÉVÉNEMENTS DE L'ABSORPTION
(le pattern absorption passe au banc en PROXY KLINES, AVANT les 2 runs ABS
de la plateforme — la suite logique de la vague 5, docs/30).

La vague 5 a fermé les FILTRES CONTINUS (12/12 cellules KILL) et laissé
ouverte une seule voie : la STRUCTURE ÉVÉNEMENTIELLE de la vague 2 —
mur / attaque / tenue / reprise à 4 conditions ordonnées, dont le champ
orderbook (maxBidAmount) n'a pas d'équivalent klines, et dont le juge
officiel reste le protocole A/B (docs/28, runs 3-4, N_MIN = 12). Ce banc
ne remplace PAS ce juge : il mesure, AVANT que le user dépense 2 backtests
de plateforme, (i) combien d'événements existent (le run ABS sera-t-il
DATA_ABSENTE par construction ?), (ii) quelle taille d'effet attendre,
(iii) si la STRUCTURE ajoute quelque chose face à la simple attaque —
la leçon du registre Aster : « la dynamique bat la moyenne ».

LA DISCIPLINE (pré-enregistrée le 01/10/2026, AVANT toute mesure — la
grille, les définitions, les seuils et le verdict sont gravés ci-dessous,
aucune cellule n'a été regardée avant l'écriture de ce fichier) :

  L'ÉVÉNEMENT (décision à l'OPEN de T, barres connues <= T-1 — convention
  temps stricte de la vague 5, doctrine _MK : entry == open(T)) :
    MUR      (T-3)  volume(T-3) >= 3 x SMA200(volume)  [proxy klines du mur
                    orderbook — LIMITE L1 : le carnet n'est pas dans les
                    klines, le run ABS plateforme reste LE juge du mur réel]
    ATTAQUE  (T-2)  vague taker directionnelle >= 2 x SMA100 de la même
                    série — LONG : taker_sell_quote(T-2) >= 2 x SMA100 ;
                    SHORT : miroir avec taker_buy_quote
    TENUE    (T-1)  l'extrême de l'attaque TIENT : LONG : low(T-1) >=
                    low(T-2) x (1 - 0,008) ; SHORT : high(T-1) <=
                    high(T-2) x (1 + 0,008)  [l'écrasement <= 0,8 %]
    REPRISE  (T-1)  le flux net bascule côté mur : LONG : EMA(D,6)(T-1) >= 0
                    ; SHORT : <= 0, avec D = 2*tbqv/qv - 1  [le déséquilibre
                    orderbook sumBids/sumAsks >= 1,2 n'a pas d'équivalent
                    klines — LIMITE L2 : D >= 0 est plus faible, le pool
                    local est une borne HAUTE des événements plateforme]

  LES 3 DÉFINITIONS IMBRIQUÉES (la question « la dynamique bat-elle la
  moyenne ? », posée AVANT la mesure) :
    E1 = ATTAQUE seule                      (la « moyenne » de référence)
    E2 = ATTAQUE + TENUE + REPRISE          (la structure sans le mur)
    E3 = MUR + ATTAQUE + TENUE + REPRISE    (l'ombre klines du pattern
                                             plateforme, vague 2)
    Nesting : E3 ⊆ E2 ⊆ E1 (contrôlé par la QA sur les données réelles).

  GRILLE PRÉ-DÉCLARÉE (TOUTES les cellules sont mesurées et rapportées) :
    3 définitions x 2 directions x 2 horizons {24, 72} barres = 12 cellules
    de panel + 4 cellules de PRIME DE STRUCTURE (E3 vs E1, par direction x
    horizon) + 1 projection sur le pool P1 + le focus BTC/ETH (les 2
    symboles des runs ABS).

  MESURE (le critère AUC du domaine, le même que la vague 5) :
    rendement de POSITION forward = open(T+H) - open(T) en bps, SIGNÉ par
    la direction (LONG : +fwd, SHORT : -fwd, doctrine _MK open -> open) ;
    AUC_événement = Mann-Whitney P(retour_événement > retour_non-événement)
    + 0,5 P(=) — le contraste direct « un event bat-il un non-event ? ».
    VERDICT MÉCANIQUE PAR CELLULE : IC 95 % (bootstrap 1 000 par journées
    UTC, seed 501) CONTIENT 0,5 et |AUC - 0,5| < 0,02 = KILL ; l'IC
    contient 0,5 sinon = INCONCLU ; l'IC EXCLUT 0,5, |AUC - 0,5| >= 0,05 et
    le sens confirme l'hypothèse (AUC > 0,5 : l'événement SURperforme) =
    CANDIDAT ; l'IC exclut 0,5 dans le sens opposé = CONTEXTE.

  LA PRIME DE STRUCTURE (la question clé du banc) : par direction x
  horizon, delta des médianes (E3 - E1) en bps, bootstrap 10 000 (seed 501,
  journées UTC) ; la question « la structure ajoute-t-elle quelque chose »
  reçoit un seuil PRÉ-DÉCLARÉ contre la bande de coûts du domaine :
    ABS_JUSTIFIÉ     IC exclut 0 ET delta >= +6 bps (la moitié de la bande
                     aller-retour taker 12,2 bps) ET n_E3 >= 12 (le N_MIN
                     du protocole ABS) -> les runs ABS plateforme passent en
                     TÊTE de file ;
    ABS_DÉPRIORISÉ   sinon -> la structure n'ajoute RIEN de mesurable en
                     proxy klines : les 2 runs ABS restent au protocole
                     (le juge ne change pas) mais passent DERRIÈRE les runs
                     RI/MK6 — économiser les backtests du user est la
                     discipline du banc (leçon vague 5).

  PROJECTION POOL P1 (CONTEXTE PAR NATURE, in-sample de la sélection) :
    une entrée du pool (T = t_in) est « matchée » si l'événement E3 de SA
    direction est actif à la décision (mur t_in-3, attaque t_in-2, tenue/
    reprise t_in-1) ; delta de R (matchés vs reste), bootstrap mécanique
    verdict_ab (10 000, seed 501) — jamais un argument de promotion.

  LES RÈGLES DE LECTURE PRÉ-DÉCLARÉES (avant tout chiffre) :
    - masse d'ex-aequo : les opens répétés des illiquides créent des
      rendements forward EXACTEMENT nuls ; chaque cellule rapporte
      part_zero (la part de zéros exacts de sa jambe événement) — une prime
      de structure dont une jambe a médiane 0,0 avec >= 50 % de zéros est
      marquée NON_INTERPRETABLE (la médiane est dans la masse des liens,
      le verdict reste ABS_DEPRIORISE : les conditions du JUSTIFIE ne sont
      simplement pas réunies) — le diagnostic « le proxy klines du mur
      sélectionne la plaine illiquide » fait partie des résultats du banc ;
    - la dichotomie AUC, elle, gère les liens par rangs moyens : les
      verdicts de panel restent interprétables quelle que soit la masse.

Limites assumées (pré-enregistrées) :
  L1 le mur est un mur de VOLUME (klines), pas un mur de CARNET — le banc
     mesure l'ombre klines du pattern, le run ABS plateforme reste le seul
     juge de maxBidAmount ;
  L2 la reprise orderbook (déséquilibre >= 1,2) est remplacée par D >= 0,
     plus faible -> le pool local est une borne HAUTE des événements ;
  L3 le flux taker est Binance, pas openmarket — le MÉCANISME est testé ;
  L4 l'IC bootstrap rééchantillonne les journées sur un échantillon réduit
     déterministe de 50 000 points par cellule (25 000 événements + 25 000
     non-événements au stride) ; l'AUC ponctuelle est full-sample ;
  L5 les horizons sont en barres, pas en heures calendaires (gaps rares,
     comptés) ; les événements sans horizon valide sont exclus de l'AUC
     et comptés.

Reproduction :
  X501_DATA_DIR=<dir des {SYM}_1h.csv> python3 x501_abs_events_local.py
  (défaut : data/x501_1h du repo — même convention que x501_flux_local)
Sorties : abs_events_local.json (versionné, déterministe) + résumé console.
"""
import csv
import datetime
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("X501_DATA_DIR", HERE / "../../../data/x501_1h"))
POOL_CSV = HERE / "pool_P1_entrees.csv"
OUT_JSON = HERE / "abs_events_local.json"

# ---------------------- grille PRÉ-DÉCLARÉE (01/10/2026) ----------------------
HORIZONS = [24, 72]            # barres 1h, open(T) -> open(T+H), signé direction
MULT_MUR = 3.0                 # volume >= 3 x SMA200 (vague 2, inchangé)
MULT_ATTAQUE = 2.0             # vague taker >= 2 x SMA100 (vague 2, inchangé)
ECRASEMENT = 0.008             # tenue : 0,8 % (vague 2, inchangé)
SPAN_REPRISE = 6               # EMA du flux net D (vague 2, inchangé)
DEFS = ["E1_attaque", "E2_structure_sans_mur", "E3_complet"]
DIRECTIONS = {"LONG": 1, "SHORT": -1}

# ---------------------- verdict mécanique (critère domaine) -------------------
SEED = 501
N_BOOT_PANEL = 1_000           # IC bootstrap AUC, par journées UTC
N_BOOT_PREMIUM = 10_000        # IC bootstrap prime de structure
N_BOOT_POOL = 10_000           # mécanique verdict_ab (diff de médiane)
REDUCTION_BOOT = 50_000        # points max par cellule (25k events + 25k non)
REDUCTION_EVENT = 25_000       # stride événements
REDUCTION_NONEVENT = 25_000    # stride non-événements
REDUCTION_PREMIUM = 100_000    # stride par jambe pour la prime de structure
AUC_MORTE = 0.02               # |AUC-0,5| < 0,02 et IC contient 0,5 -> KILL
AUC_CANDIDAT = 0.05            # séparation minimale d'un CANDIDAT
PRIME_STRUCTURE_BPS = 6.0      # moitié de la bande aller-retour taker
N_MIN_ABS = 12                 # le N_MIN du protocole ABS (docs/28)
COUT_AR_TAKER_BPS = 12.2       # 2 x 6,1 — l'étalon d'exploitabilité
FOCUS_SYMS = ("BTCUSDT", "ETHUSDT")

MS_H = 3_600_000
MS_J = 86_400_000


# ------------------------------- utils ----------------------------------------
def sma(x, k):
    """SMA causale sur k barres incluses ; NaN tant que la fenêtre n'est
    pas pleine (sémantique ta.sma : la barre courante est incluse)."""
    n = len(x)
    out = np.full(n, np.nan)
    if n < k:
        return out
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[k - 1:] = (c[k:] - c[:-k]) / k
    return out


def ema(x, span):
    """EMA récursive (lambda = 2/(span+1)), renvoie y (y[0] = x[0])."""
    lam = 2.0 / (span + 1.0)
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = lam * x[i] + (1.0 - lam) * y[i - 1]
    return y


def rangs_moyens(x):
    """Rangs 1..n avec rangs moyens sur les ex-aequo (vectorisé, stable) —
    la mécanique de la vague 5, reprise à l'identique."""
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


def stride_subsample(idx, cap, n_total):
    """Sous-échantillon déterministe au stride (le cap pré-déclaré)."""
    if len(idx) <= cap:
        return idx
    pas = len(idx) / float(cap)
    pos = np.floor(np.arange(cap) * pas).astype(np.int64)
    pos = np.minimum(pos, len(idx) - 1)
    return idx[pos]


def bootstrap_auc(ret, flag, jour_idx, iters, seed):
    """IC bootstrap de l'AUC d'événement : échantillon réduit déterministe
    (événements + non-événements, stride pré-déclaré), rééchantillonnage
    AVEC REMISE des journées (clusters 24h, limite L4) — la même mécanique
    que la vague 5 : chaque journée tirée reconstitue événements et
    non-événements ensemble."""
    ev = np.flatnonzero(flag)
    nev = np.flatnonzero(~flag)
    ev_r = stride_subsample(ev, REDUCTION_EVENT, len(flag))
    nev_r = stride_subsample(nev, REDUCTION_NONEVENT, len(flag))
    idx = np.concatenate([ev_r, nev_r])
    r = ret[idx]
    f = flag[idx]
    j = jour_idx[idx]
    jours = np.unique(j)
    pos_par_jour = {int(d): np.flatnonzero(j == d) for d in jours}
    rng = np.random.default_rng(seed)
    aucs = np.empty(iters)
    for b in range(iters):
        tirage = rng.integers(0, len(jours), len(jours))
        sel = np.concatenate([pos_par_jour[int(jours[k])] for k in tirage])
        f_b = f[sel]
        n_ev = int(f_b.sum())
        if n_ev == 0 or n_ev == len(f_b):
            aucs[b] = 0.5
            continue
        aucs[b] = auc_mw(r[sel][f_b], r[sel][~f_b])
    return float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))


def verdict_auc(auc, ic_bas, ic_haut, sens_confirme):
    """Verdict mécanique (le même que la vague 5, au bit près)."""
    if np.isnan(auc):
        return "DATA_INSUFFISANTE"
    contient = ic_bas <= 0.5 <= ic_haut
    if contient and abs(auc - 0.5) < AUC_MORTE:
        return "KILL"
    if contient:
        return "INCONCLU"
    if abs(auc - 0.5) >= AUC_CANDIDAT and auc > 0.5 and sens_confirme:
        return "CANDIDAT"
    if auc > 0.5:
        return "INCONCLU"
    return "CONTEXTE"


def bootstrap_mediane_delta(a, b, jour_a, jour_b, iters, seed):
    """IC bootstrap du delta de médianes (a - b) par journées UTC — la
    mécanique pré-déclarée pour la prime de structure (E3 vs E1)."""
    rng = np.random.default_rng(seed)
    ja = np.unique(jour_a)
    jb = np.unique(jour_b)
    pos_a = {int(d): np.flatnonzero(jour_a == d) for d in ja}
    pos_b = {int(d): np.flatnonzero(jour_b == d) for d in jb}
    deltas = np.empty(iters)
    for k in range(iters):
        ta = ja[rng.integers(0, len(ja), len(ja))]
        tb = jb[rng.integers(0, len(jb), len(jb))]
        sa = a[np.concatenate([pos_a[int(d)] for d in ta])] if len(ta) else a[:0]
        sb = b[np.concatenate([pos_b[int(d)] for d in tb])] if len(tb) else b[:0]
        ma = float(np.median(sa)) if len(sa) else 0.0
        mb = float(np.median(sb)) if len(sb) else 0.0
        deltas[k] = ma - mb
    return (float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5)),
            float(np.mean(deltas > 0)))


def bootstrap_verdict_pool(r_m, r_s, iters, seed):
    """P(bootstrap méd_matchés > méd_reste) — la mécanique verdict_ab
    (10 000 rééchantillonnages avec remise, seed 501), pour la projection
    CONTEXTE sur le pool P1."""
    rng = np.random.default_rng(seed)
    m = np.asarray(r_m, dtype=float)
    s = np.asarray(r_s, dtype=float)
    if len(m) == 0 or len(s) == 0:
        return float("nan")
    comptes = 0
    for _ in range(iters):
        dm = float(np.median(m[rng.integers(0, len(m), len(m))]))
        ds = float(np.median(s[rng.integers(0, len(s), len(s))]))
        if dm > ds:
            comptes += 1
    return comptes / float(iters)


def load_klines(sym):
    """Charge {sym}_1h.csv -> dict de float64 (mêmes colonnes que la vague 5)."""
    p = DATA_DIR / f"{sym}_1h.csv"
    if not p.exists():
        return None
    cols = {k: [] for k in ("open_time", "open", "high", "low", "volume",
                            "quote_volume", "taker_buy_quote_volume")}
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            for k in cols:
                cols[k].append(float(row[k]))
    return {k: np.asarray(v, dtype=np.float64) for k, v in cols.items()}


def evenements(kl):
    """Les flags E1/E2/E3 par direction aux décisions T (décision à l'open
    de T, conditions sur T-3/T-2/T-1 — strictement causal)."""
    vol, qv, tbqv = kl["volume"], kl["quote_volume"], kl["taker_buy_quote_volume"]
    tksell = qv - tbqv                       # la quote agressive vendeuse
    sma200_vol = sma(vol, 200)
    sma100_sell = sma(tksell, 100)
    sma100_buy = sma(tbqv, 100)
    D = 2.0 * tbqv / np.maximum(qv, 1e-12) - 1.0
    emaD = ema(D, SPAN_REPRISE)
    n = len(vol)
    T = np.arange(n)
    mur = vol >= MULT_MUR * sma200_vol
    att_long = tksell >= MULT_ATTAQUE * sma100_sell
    att_short = tbqv >= MULT_ATTAQUE * sma100_buy
    # les conditions décalées au point de décision T (mur T-3, attaque T-2,
    # tenue/reprise T-1) ; np.nan comparé = False, les débuts sont exclus
    mur_T = np.zeros(n, dtype=bool); mur_T[3:] = mur[:-3]
    attL_T = np.zeros(n, dtype=bool); attL_T[2:] = att_long[:-2]
    attS_T = np.zeros(n, dtype=bool); attS_T[2:] = att_short[:-2]
    lo, hi = kl["low"], kl["high"]
    tenueL_T = np.zeros(n, dtype=bool)
    tenueL_T[2:] = lo[1:-1] >= lo[:-2] * (1.0 - ECRASEMENT)
    tenueS_T = np.zeros(n, dtype=bool)
    tenueS_T[2:] = hi[1:-1] <= hi[:-2] * (1.0 + ECRASEMENT)
    repL_T = np.zeros(n, dtype=bool)
    repL_T[1:] = emaD[:-1] >= 0.0
    repS_T = np.zeros(n, dtype=bool)
    repS_T[1:] = emaD[:-1] <= 0.0
    out = {}
    for d, s in DIRECTIONS.items():
        att = attL_T if s == 1 else attS_T
        tenue = tenueL_T if s == 1 else tenueS_T
        rep = repL_T if s == 1 else repS_T
        out[d] = {
            "E1_attaque": att,
            "E2_structure_sans_mur": att & tenue & rep,
            "E3_complet": mur_T & att & tenue & rep,
        }
    return out


# ------------------------------- étude ----------------------------------------
def cellule(ret, flag, jours, hypothese):
    """Une cellule de panel : AUC d'événement full-sample + IC bootstrap
    réduit + verdict mécanique. L'hypothèse pré-déclarée est toujours
    « l'événement SURperforme » (AUC > 0,5) : le rendement est déjà signé
    par la direction."""
    ev = np.flatnonzero(flag)
    nev = np.flatnonzero(~flag)
    n_full = int(flag.sum())            # tous les événements (avec/sans fwd)
    n_valid = len(flag)                 # points avec horizon valide
    if len(ev) == 0 or len(nev) == 0:
        return {"n_events": n_full, "n_points": n_valid, "auc": None,
                "verdict": "DATA_INSUFFISANTE"}
    auc = float(auc_mw(ret[ev], ret[nev]))
    ic_bas, ic_haut = bootstrap_auc(ret, flag, jours, N_BOOT_PANEL, SEED)
    v = verdict_auc(auc, ic_bas, ic_haut, sens_confirme=True)
    return {
        "n_events": n_full, "n_points": n_valid,
        "auc": auc, "ic95": [ic_bas, ic_haut],
        "med_event_bps": float(np.median(ret[ev])),
        "med_nonevent_bps": float(np.median(ret[nev])),
        "delta_med_bps": float(np.median(ret[ev]) - np.median(ret[nev])),
        "part_zero_events": float(np.mean(ret[ev] == 0.0)),
        "verdict": v,
    }


def main():
    syms = sorted(p.stem.replace("_1h", "") for p in DATA_DIR.glob("*_1h.csv"))
    print(f"VAGUE 6 — banc d'événements absorption (proxy klines) : "
          f"{len(syms)} symboles depuis {DATA_DIR}")
    # accumulation par (direction, horizon) : rendements de position, flags
    # des 3 définitions, journées UTC de la décision
    acc = {(d, h): {"ret": [], "jours": [], "flags": {k: [] for k in DEFS}}
           for d in DIRECTIONS for h in HORIZONS}
    t_min, t_max = None, None
    total_barres = 0
    ev_counts = {d: {k: 0 for k in DEFS} for d in DIRECTIONS}
    ev_counts_annee = {}                 # E3 par année de décision
    focus_counts = {}
    for sym in syms:
        kl = load_klines(sym)
        if kl is None:
            continue
        n = len(kl["open_time"])
        total_barres += n
        if t_min is None or kl["open_time"][0] < t_min:
            t_min = kl["open_time"][0]
        if t_max is None or kl["open_time"][-1] > t_max:
            t_max = kl["open_time"][-1]
        evs = evenements(kl)
        jours_sym = (kl["open_time"] // MS_J).astype(np.int64)
        if sym in FOCUS_SYMS:
            focus_counts[sym] = {d: {k: int(evs[d][k].sum()) for k in DEFS}
                                 for d in DIRECTIONS}
        # E3 complet, les deux directions, par ANNÉE UTC de la décision
        for d in DIRECTIONS:
            for i in np.flatnonzero(evs[d]["E3_complet"]):
                an = datetime.datetime.fromtimestamp(
                    kl["open_time"][i] / 1000.0, datetime.timezone.utc).year
                ev_counts_annee[str(an)] = ev_counts_annee.get(str(an), 0) + 1
        for d, s in DIRECTIONS.items():
            for k in DEFS:
                ev_counts[d][k] += int(evs[d][k].sum())
            for h in HORIZONS:
                if n <= h + 1:
                    continue
                op = kl["open_time"]
                o = kl["open"]
                fwd = np.full(n, np.nan)
                fwd[:n - h] = (o[h:] - o[:n - h]) / np.maximum(o[:n - h], 1e-12) * 1e4
                valide = ~np.isnan(fwd)
                a = acc[(d, h)]
                a["ret"].append(s * fwd[valide])
                a["jours"].append(jours_sym[valide])
                for k in DEFS:
                    a["flags"][k].append(evs[d][k][valide])
    # ---------------- 12 cellules de panel ----------------
    etude_A = {}
    for d in DIRECTIONS:
        for h in HORIZONS:
            a = acc[(d, h)]
            ret = np.concatenate(a["ret"])
            jours = np.concatenate(a["jours"])
            for k in DEFS:
                flag = np.concatenate(a["flags"][k])
                cle = f"{d}_{k}_H{h}"
                c = cellule(ret, flag, jours, "surperformance")
                etude_A[cle] = c
                print(f"  {cle:44s} n={c['n_events']:7d} "
                      f"AUC={c.get('auc', float('nan')):.4f} "
                      f"IC=[{c['ic95'][0]:.4f},{c['ic95'][1]:.4f}] "
                      f"Δ={c.get('delta_med_bps', float('nan')):+7.1f} bps "
                      f"-> {c['verdict']}")
    # ---------------- prime de structure (E3 vs E1) ----------------
    etude_B = {}
    for d in DIRECTIONS:
        for h in HORIZONS:
            a = acc[(d, h)]
            ret = np.concatenate(a["ret"])
            jours = np.concatenate(a["jours"])
            f1 = np.concatenate(a["flags"]["E1_attaque"])
            f3 = np.concatenate(a["flags"]["E3_complet"])
            i1 = np.flatnonzero(f1)
            i3 = np.flatnonzero(f3)
            r1 = ret[stride_subsample(i1, REDUCTION_PREMIUM, len(ret))]
            r3 = ret[stride_subsample(i3, REDUCTION_PREMIUM, len(ret))]
            j1 = jours[stride_subsample(i1, REDUCTION_PREMIUM, len(ret))]
            j3 = jours[stride_subsample(i3, REDUCTION_PREMIUM, len(ret))]
            if len(r1) == 0 or len(r3) == 0:
                etude_B[f"{d}_H{h}"] = {"verdict": "DATA_INSUFFISANTE"}
                continue
            ic_b, ic_h, p = bootstrap_mediane_delta(
                r3, r1, j3, j1, N_BOOT_PREMIUM, SEED)
            delta = float(np.median(r3) - np.median(r1))
            justifie = (ic_b > 0.0 and delta >= PRIME_STRUCTURE_BPS
                        and len(i3) >= N_MIN_ABS)
            # règle de lecture pré-déclarée : une jambe dont la médiane est
            # 0,0 avec >= 50 % de zéros exacts = la médiane est dans la
            # masse des liens -> la cellule n'est PAS interprétable
            deg3 = (float(np.median(r3)) == 0.0
                    and float(np.mean(r3 == 0.0)) >= 0.5)
            deg1 = (float(np.median(r1)) == 0.0
                    and float(np.mean(r1 == 0.0)) >= 0.5)
            etude_B[f"{d}_H{h}"] = {
                "n_E1": int(len(i1)), "n_E3": int(len(i3)),
                "med_E1_bps": float(np.median(r1)),
                "med_E3_bps": float(np.median(r3)),
                "part_zero_E1": float(np.mean(r1 == 0.0)),
                "part_zero_E3": float(np.mean(r3 == 0.0)),
                "delta_bps": delta, "ic95": [ic_b, ic_h],
                "p_delta_sup0": p,
                "non_interpretable": bool(deg3 or deg1),
                "verdict": "ABS_JUSTIFIE" if justifie else "ABS_DEPRIORISE",
            }
            print(f"  PRIME {d}_H{h}: n_E3={len(i3)} Δ={delta:+.1f} bps "
                  f"IC=[{ic_b:+.1f},{ic_h:+.1f}] P={p:.3f} "
                  f"{'[NON_INTERPRETABLE] ' if (deg3 or deg1) else ''}-> "
                  f"{etude_B[f'{d}_H{h}']['verdict']}")
    # ---------------- projection pool P1 (CONTEXTE) ----------------
    pool = list(csv.DictReader(open(POOL_CSV, newline="")))
    opidx = {}
    for sym in set(r["sym"] for r in pool):
        kl = load_klines(sym)
        if kl is not None:
            opidx[sym] = (kl["open_time"], evenements(kl))
    r_match, r_reste, n_match = [], [], 0
    for r in pool:
        rec = opidx.get(r["sym"])
        if rec is None:
            continue
        ot, evs = rec
        pos = np.searchsorted(ot, float(r["t_in"]))
        if pos >= len(ot) or ot[pos] != float(r["t_in"]):
            continue
        d = "LONG" if int(r["side"]) == 1 else "SHORT"
        if evs[d]["E3_complet"][pos]:
            r_match.append(float(r["R"]))
            n_match += 1
        else:
            r_reste.append(float(r["R"]))
    p_pool = bootstrap_verdict_pool(r_match, r_reste, N_BOOT_POOL, SEED)
    d_pool = (float(np.median(r_match)) - float(np.median(r_reste))
              if r_match and r_reste else None)
    etude_C = {
        "n_pool": len(pool), "n_matches_E3": n_match,
        "med_R_matches": float(np.median(r_match)) if r_match else None,
        "med_R_reste": float(np.median(r_reste)) if r_reste else None,
        "delta_R": d_pool, "p_boot_delta_sup0": p_pool,
        "statut": "CONTEXTE (in-sample de la sélection)",
    }
    print(f"  POOL P1 : {n_match}/{len(pool)} entrées matchées E3, "
          f"ΔR={d_pool}, P={p_pool}")
    # ---------------- synthèse verdict du banc ----------------
    justifie_n = sum(1 for v in etude_B.values() if v.get("verdict") == "ABS_JUSTIFIE")
    synthese = {
        "prime_structure_justifiee": f"{justifie_n}/4 cellules",
        "regle_predeclaree": f"IC exclut 0 ET delta >= +{PRIME_STRUCTURE_BPS} bps "
                             f"ET n_E3 >= {N_MIN_ABS}",
        "decision": ("ABS_EN_TETE_DE_FILE" if justifie_n > 0
                     else "ABS_DEPRIORISE (derriere RI/MK6)"),
    }
    out = {
        "etude": "VAGUE 6 — banc d'événements absorption (proxy klines)",
        "date_pre_enregistrement": "2026-10-01",
        "univers": {"symboles": len(syms), "barres": total_barres,
                    "t_min_ms": t_min, "t_max_ms": t_max},
        "grille": {"definitions": DEFS, "directions": list(DIRECTIONS),
                   "horizons": HORIZONS,
                   "parametres": {"mult_mur": MULT_MUR, "mult_attaque": MULT_ATTAQUE,
                                  "ecrasement": ECRASEMENT, "span_reprise": SPAN_REPRISE}},
        "counts_events": ev_counts,
        "focus_btc_eth": focus_counts,
        "E3_par_annee_utc": dict(sorted(ev_counts_annee.items())),
        "etude_A_panel": etude_A,
        "etude_B_prime_structure": etude_B,
        "etude_C_pool_P1": etude_C,
        "synthese": synthese,
        "cout_ar_taker_bps": COUT_AR_TAKER_BPS,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True, ensure_ascii=True)
    print(f"-> {OUT_JSON.name} ({OUT_JSON.stat().st_size} octets) | décision : "
          f"{synthese['decision']}")


if __name__ == "__main__":
    main()
