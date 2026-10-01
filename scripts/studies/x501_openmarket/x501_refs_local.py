#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_refs_local.py — VAGUE 7 : LE BANC DES RÉFÉRENCES DE LIQUIDITÉ
(VWAP de session + Volume Profile de la veille — les 2 derniers pouvoirs
d'analyse RÉELS, les briques payantes de TradingView, dormants 0 script).

Après les vagues 5 (filtres continus : 12/12 KILL) et 6 (structure
événementielle de l'absorption : prime réfutée 0/4), il reste DEUX pouvoirs
d'analyse réels jamais mesurés — `vwap` et `volume profile` (famille analyse
3/5 dans docs/27). Ce sont EXACTEMENT les briques que TradingView facture et
que tout manuel institutionnel cite : le VWAP ancré session (« benchmark »
d'exécution) et le profil de volume journalier (VPOC / VAH / VAL, la « value
area »). Le domaine les a toujours ignorés. Ce banc les mesure AVANT tout
run plateforme, comme les vagues 5-6 : dépenser des CPU-minutes locales au
lieu des backtests du user.

ltf() et minBid/minAskAmount ne sont PAS banc-testés ici et pour une seule
raison pré-déclarée : aucune data locale équivalente (ltf = TF inférieur non
collecté ; minBid/minAsk = L1 du carnet, absent des klines) — ils restent
documentés comme tels dans docs/27. Le langage et la visu restent de la
dette de style, sans edge (décision vague 1).

LA DISCIPLINE (pré-enregistrée le 01/10/2026, AVANT toute mesure — la
grille, les définitions, les seuils, les tie-breaks et le verdict sont
gravés ci-dessous ; aucune cellule n'a été regardée avant l'écriture de ce
fichier) :

  CONVENTION TEMPS STRICTE (les vagues 5-6) — décision à l'OPEN de T avec
  les barres <= T-1 seulement (open(T) lui-même est connu : c'est le prix
  d'entrée). Rendement forward = open(T+H) − open(T) en bps, SIGNÉ par la
  direction (LONG : +fwd, SHORT : −fwd, doctrine _MK open -> open).

  LE VWAP DE SESSION (l'ancrage 00h UTC, la convention TradingView) :
    vwap(k) = cum(qv × tp) / cum(qv) depuis le DÉBUT de la journée UTC de
    la barre k, avec tp = (high+low+close)/3 (la moyenne typique). Évalué
    à T-1, il ne lit que la session en cours de T-1 : causal à open(T).
    LIMITE L0 pré-déclarée : le vwap plateforme peut ancrer autrement
    (semaine, mois, ancrage manuel) — ici UNE seule ancre, la session UTC,
    pré-déclarée ; un CANDIDAT sur cette ancre serait re-testé sur les
    autres ancres AVANT promotion.

  LE VOLUME PROFILE DE LA VEILLE (le profil COMPLET du jour D-1, où
  D = journée de T, connu à l'open de T) :
    chaque barre 1h du jour D-1 répartit son quote_volume UNIFORMÉMENT sur
    [low, high] ; les 24 barres s'accumulent sur VP_BINS = 48 bins
    réguliers couvrant [min low, max high] du jour ;
    VPOC = le bin de volume maximal (ex-aequo -> le bin le PLUS BAS) ;
    VALUE AREA = expansion gourmande depuis le VPOC, on prend le voisin
    (dessus/dessous) de plus grand volume (ex-aequo -> le DESSOUS) jusqu'à
    couvrir >= 70 % du volume du jour ; VAH = bord supérieur du bin VA le
    plus haut, VAL = bord inférieur du bin VA le plus bas.
    LIMITE L1 pré-déclarée : l'allocation uniforme depuis du 1h est une
    OMBRE du profil fin (tape/carnet) — le banc teste l'INFORMATION du
    niveau, pas la précision du niveau ; un CANDIDAT serait re-testé sur
    le profil plateforme (la granularité native) AVANT promotion.

  LA GRILLE PRÉ-DÉCLARÉE (28 cellules — TOUTES mesurées et rapportées,
  y compris les hypothèses opposées ; personne ne choisit après coup) :
    V1 AIMANT (l'hypothèse mean-reversion : le VWAP « benchmark
        institutionnel » ramène le prix) — flag LONG si
        d = (close(T-1) − vwap(T-1)) / vwap(T-1) <= −s ; flag SHORT si
        d >= +s ; seuils s ∈ {0, 0,5 %, 1 %} × H ∈ {24,72} = 12 cellules.
        Sens attendu : AUC > 0,5.
    V2 CROSS (l'hypothèse continuation, la doctrine breakout) — flag LONG
        si close(T-2) < vwap(T-2) <= close(T-1) (franchit le VWAP par le
        haut) ; SHORT miroir ; × H{24,72} = 4 cellules.
        Sens attendu : AUC > 0,5.
    P1 VPOC AIMANT — flag LONG si open(T) < vpoc(D-1) ; SHORT si
        open(T) > vpoc(D-1) ; × H{24,72} = 4 cellules.
        Sens attendu : AUC > 0,5 (le retour au point de contrôle).
    P2 VA REJET (mean-reversion à la value area) — flag LONG si
        close(T-1) < VAL(D-1) ; SHORT si close(T-1) > VAH(D-1) ;
        × H{24,72} = 4 cellules. Sens attendu : AUC > 0,5.
    P3 VA BREAKOUT (l'hypothèse opposée, POSÉE AVANT) — flag LONG si
        close(T-1) > VAH(D-1) ; SHORT si close(T-1) < VAL(D-1) ;
        × H{24,72} = 4 cellules. Sens attendu : AUC > 0,5.
    NB : P2 et P3 conditionnent les MÊMES événements (close sous VAL /
    sur VAH) avec des attentes OPPOSÉES — les deux verdicts sortent
    ensemble, le litige est tranché par la donnée et pas par le goût.

  ROBUSTESSE PRÉ-DÉCLARÉE :
    (i)  la MÊME grille sur le panel LIQUIDE8 = BTC, ETH, BNB, SOL, XRP,
         DOGE, ADA, LINK (contre la plaine illiquide qui domine les
         ex-aequo — leçon vague 6) ;
    (ii) focus BTC/ETH sur les cellules cœur (V1 s=0, P2, P3 — les
         symboles des runs plateforme) ;
    (iii) AUC par symbole LIQUIDE8 (point estimate, sans boot) sur les
         cellules cœur (anti-dilution, la vague 5).

  RÈGLE D'EX-AEQUO PRÉ-DÉCLARÉE (la vague 6) : si >= 50 % des rendements
  forward du sous-ensemble flaggé sont EXACTEMENT nuls (les opens répétés
  des microcaps), la cellule est marquée NON_INTERPRETABLE — la médiane
  est dans la masse des liens, l'AUC lit le carnotet des illiquides et
  pas le signal.

  CRITÈRE AUC DU DOMAINE (inchangé, vagues 5-6) : Mann-Whitney flag vs
  complément, IC 95 % bootstrap 1 000 par journées UTC (clusters 24h,
  seed 501, réduction 50 k points) ; KILL si l'IC contient 0,5 ET
  |AUC−0,5| < 0,02 ; CANDIDAT si l'IC exclut 0,5, |AUC−0,5| >= 0,05 et le
  sens pré-déclaré est confirmé ; sinon INCONCLU (n_flag ou n_comp < 100
  = INCONCLU sans boot).

  LE POOL P1 EN CONTEXTE (jamais un argument de promotion — le juge
  reste le protocole A/B docs/28) : deux filtres pré-déclarés sur les
  469 entrées —
    F1 « payer le prix étendu » : l'entrée est du MAUVAIS côté du vwap de
        session (LONG au-dessus, SHORT en dessous) ;
    F2 hors value area : l'entrée est au-dessus de VAH (LONG) ou sous
        VAL (SHORT) du profil de la veille.
    CONVENTION PRÉ-DÉCLARÉE du prix d'entrée : les flags sont évalués sur
    open(T), l'open de la barre d'entrée (la doctrine _MK). La colonne
    `entry` du pool vaut entry = open(T) x (1 + side x 2 bps) — l'entrée
    est 2 bps ADVERSE à l'open (la convention du pool vague 4, re-vérifiée
    469/469 par la QA) ; injecter ce décalage dans un filtre de référence
    de liquidité ajouterait un bruit latéral de 2 bps sans objet.
    Verdict : delta R médian (flag vs complément), bootstrap verdict_ab
    10 000 rééchantillonnages seed 501 ; les références absentes (jour de
    veille manquant, vwap dégénéré) sortent du filtre et sont comptées.

  LA RÈGLE DE LECTURE PRÉ-DÉCLARÉE (avant tout chiffre) :
    — si la grille entière KILL -> falsification n°7 du domaine, vwap et
      volume profile passent de « dormants » à « mesurés et fermés »
      (docs/26), la famille analyse de docs/27 est CLOSE (chaque pouvoir
      est exploité, mesuré, refusé par design, sans data locale, ou de la
      dette de style), et le registre docs/20 reçoit l'entrée ;
    — si une cellule CANDIDAT -> le run correspondant est pré-enregistré
      au protocole docs/28 AVANT tout run plateforme (grille A/B on/off,
      N_MIN inchangé), et CE SEULEMENT LÀ un kScript peut brancher le
      pouvoir (défaut OFF = la référence MC v20 reste bit-à-bit).

Reproduction : python3 x501_refs_local.py  ->  refs_local.json
               (déterministe : seed 501, aucune source d'aléa hors le
               bootstrap seedé ; re-exécution bit à bit attendue)
"""

import csv
import hashlib
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path

import numpy as np

# ------------------------------ constantes ------------------------------------
SEED = 501
N_BOOT_PANEL = 1_000                  # IC bootstrap AUC, par journées UTC
N_BOOT_POOL = 10_000                  # mécanique verdict_ab (diff de médiane)
REDUCTION_BOOT = 50_000               # points max par cellule pour le boot
AUC_MORTE = 0.02                      # |AUC−0,5| < seuil + IC contient 0,5 = KILL
AUC_CANDIDAT = 0.05                   # |AUC−0,5| >= seuil + IC exclut 0,5
HORIZONS = (24, 72)                   # barres 1h (la grille des vagues 5-6)
VP_BINS = 48                          # bins du profil journalier
VA_FRAC = 0.70                        # la value area (convention Market Profile)
SEUILS_D = (0.0, 0.005, 0.01)         # seuils de distance au VWAP (V1)
LIQUIDE8 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
            "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")
N_MIN_FLAG = 100                      # sous un n, INCONCLU sans boot

ICI = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("X501_DATA_DIR", "/home/z/my-project/scripts/data_x501"))
POOL_CSV = ICI / "pool_P1_entrees.csv"
OUT_JSON = ICI / "refs_local.json"


# --------------------------- machinerie de mesure -----------------------------
# (rangs_moyens / auc_mw / bootstrap_flags : le code des vagues 5-6, éprouvé
# par 27 + 62 contrôles QA — repris À L'IDENTIQUE pour la reproductibilité)
def rangs_moyens(x):
    """Rangs 1..n avec rangs moyens sur les ex-aequo (vectorisé, stable).

    Les opens répétés des symboles illiquides créent des rendements forward
    ÉGAUX bit à bit : des milliers de blocs d'ex-aequo — la boucle Python
    pure est catastrophique ; bornes de blocs + np.repeat donnent le même
    résultat à l'octet près en O(n)."""
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
    chaque journée tirée reconstitue flag+complément ensemble."""
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


def verdict_cellule(auc, lo, hi, n_flag, n_comp, part_zeros, sens_attendu):
    """Le verdict mécanique du domaine (pré-déclaré, dans cet ordre) :
    1. n insuffisant            -> INCONCLU (jamais de verdict sur du vide)
    2. ex-aequo massifs         -> NON_INTERPRETABLE (>= 50 % de zéros)
    3. IC contient 0,5 et |AUC−0,5| < 0,02     -> KILL
    4. IC contient 0,5                         -> INCONCLU
    5. |AUC−0,5| >= 0,05 et sens confirmé      -> CANDIDAT
    6. |AUC−0,5| >= 0,05, sens contraire       -> CONTEXTE
    7. sinon                                   -> INCONCLU"""
    if n_flag < N_MIN_FLAG or n_comp < N_MIN_FLAG:
        return "INCONCLU"
    if part_zeros >= 0.50:
        return "NON_INTERPRETABLE"
    contient = (lo <= 0.5 <= hi) if np.isfinite(lo) else True
    if contient and abs(auc - 0.5) < AUC_MORTE:
        return "KILL"
    if contient:
        return "INCONCLU"
    if abs(auc - 0.5) >= AUC_CANDIDAT:
        confirme = (auc > 0.5) if sens_attendu > 0 else (auc < 0.5)
        return "CANDIDAT" if confirme else "CONTEXTE"
    return "INCONCLU"


def cellule_evenement(fwd, flag, jours, hypothese, sens_attendu):
    """Une cellule d'événement : AUC flag vs complément, IC bootstrap par
    journées, verdict mécanique (critère du domaine, règle d'ex-aequo)."""
    ok = np.isfinite(fwd) & np.isfinite(flag.astype(float))
    f, fl, j = fwd[ok], flag[ok], jours[ok]
    n_flag = int(fl.sum())
    n_comp = int((~fl).sum())
    if n_flag == 0 or n_comp == 0:
        return {"n": int(len(f)), "n_flag": n_flag, "n_comp": n_comp,
                "auc": float("nan"), "ic95": [float("nan"), float("nan")],
                "part_zeros": float("nan"), "fwd_bps_flag": float("nan"),
                "fwd_bps_comp": float("nan"), "delta_bps": float("nan"),
                "hypothese": hypothese, "verdict": "INCONCLU"}
    f_flag, f_comp = f[fl], f[~fl]
    auc = auc_mw(f_flag, f_comp)
    part_zeros = float(np.mean(f_flag == 0.0))
    lo, hi = float("nan"), float("nan")
    if n_flag >= N_MIN_FLAG and n_comp >= N_MIN_FLAG:
        boots = bootstrap_flags(f, fl, j, N_BOOT_PANEL, SEED)
        lo, hi = float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))
    return {"n": int(len(f)), "n_flag": n_flag, "n_comp": n_comp,
            "auc": float(auc), "ic95": [lo, hi],
            "part_zeros": part_zeros,
            "fwd_bps_flag": float(np.median(f_flag)) if n_flag else float("nan"),
            "fwd_bps_comp": float(np.median(f_comp)) if n_comp else float("nan"),
            "delta_bps": float(np.median(f_flag) - np.median(f_comp)) if (n_flag and n_comp) else float("nan"),
            "hypothese": hypothese,
            "verdict": verdict_cellule(auc, lo, hi, n_flag, n_comp, part_zeros, sens_attendu)}


def bootstrap_verdict_pool(r_flag, r_comp, iters, seed):
    """P(bootstrap méd_flag > méd_comp) — la mécanique verdict_ab
    (10 000 rééchantillonnages avec remise, seed 501), CONTEXTE."""
    rng = np.random.default_rng(seed)
    m = np.asarray(r_flag, dtype=float)
    s = np.asarray(r_comp, dtype=float)
    if len(m) == 0 or len(s) == 0:
        return float("nan")
    comptes = 0
    for _ in range(iters):
        dm = float(np.median(m[rng.integers(0, len(m), len(m))]))
        ds = float(np.median(s[rng.integers(0, len(s), len(s))]))
        if dm > ds:
            comptes += 1
    return comptes / float(iters)


# ------------------------------ références ------------------------------------
def session_vwap(ts, high, low, close, qv):
    """VWAP ancré 00h UTC de la journée de CHAQUE barre (convention
    TradingView : tp = (h+l+c)/3, pondération quote_volume, reset journalier).
    vwap(k) ne lit que les barres de la journée de k jusqu'à k incluse —
    évalué à T-1 il est donc causal à open(T). Vectorisé par cumsums avec
    base de groupe (le cumul reprend à zéro à chaque frontière de journée)."""
    tp = (high + low + close) / 3.0
    day = ts // 86_400_000
    new_day = np.r_[True, day[1:] != day[:-1]]
    starts = np.flatnonzero(new_day)
    grp = np.cumsum(new_day) - 1
    gstart = starts[grp]
    cs_q = np.cumsum(qv)
    cs_qt = np.cumsum(qv * tp)
    base_q = np.where(gstart > 0, cs_q[np.maximum(gstart - 1, 0)] * (gstart > 0), 0.0)
    base_qt = np.where(gstart > 0, cs_qt[np.maximum(gstart - 1, 0)] * (gstart > 0), 0.0)
    den = cs_q - base_q
    num = cs_qt - base_qt
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)


def profils_jour(ts, high, low, qv):
    """Le volume profile de CHAQUE journée UTC complète -> dict
    jour -> (vpoc, vah, val, part_va). Pré-déclaré : allocation uniforme de
    chaque barre sur [low, high] (barre dégénérée : tout dans son bin),
    VP_BINS bins, VPOC = argmax (ex-aequo -> le bin le plus bas), value
    area = expansion gourmande (ex-aequo -> le DESSOUS), 70 % du volume."""
    day = ts // 86_400_000
    new_day = np.r_[True, day[1:] != day[:-1]]
    starts = np.flatnonzero(new_day).tolist() + [len(ts)]
    out = {}
    for i in range(len(starts) - 1):
        a, b = starts[i], starts[i + 1]
        d = int(day[a])
        h, l, v = high[a:b], low[a:b], qv[a:b]
        lo, hi = float(l.min()), float(h.max())
        tot = float(v.sum())
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo or tot <= 0:
            out[d] = (np.nan, np.nan, np.nan, np.nan)
            continue
        edges = np.linspace(lo, hi, VP_BINS + 1)
        w = np.minimum(h[:, None], edges[None, 1:]) - np.maximum(l[:, None], edges[None, :-1])
        w = np.clip(w, 0.0, None)
        rng_bar = np.maximum(h - l, 1e-300)
        contrib = v[:, None] * (w / rng_bar[:, None])
        deg = (h - l) <= 0
        if deg.any():
            bidx = np.clip(np.searchsorted(edges, h[deg], side="right") - 1, 0, VP_BINS - 1)
            contrib[np.flatnonzero(deg), bidx] += v[deg]
        vol = contrib.sum(axis=0)
        vpoc_i = int(np.argmax(vol))            # ex-aequo -> le bin le plus bas
        lo_i = hi_i = vpoc_i
        va = float(vol[vpoc_i])
        cible = VA_FRAC * tot
        while va < cible and (lo_i > 0 or hi_i < VP_BINS - 1):
            v_dn = float(vol[lo_i - 1]) if lo_i > 0 else -1.0
            v_up = float(vol[hi_i + 1]) if hi_i < VP_BINS - 1 else -1.0
            if v_dn >= v_up:                     # ex-aequo -> le DESSOUS
                lo_i -= 1
                va += float(vol[lo_i])
            else:
                hi_i += 1
                va += float(vol[hi_i])
        out[d] = ((float(edges[vpoc_i]) + float(edges[vpoc_i + 1])) / 2.0,
                  float(edges[hi_i + 1]), float(edges[lo_i]), va / tot)
    return out


# ------------------------------ chargement ------------------------------------
def load_klines(sym):
    """Charge {sym}_1h.csv -> dict de float64 (format Binance : colonnes
    0 open_time, 1 open, 2 high, 3 low, 4 close, 7 quote_volume)."""
    p = DATA_DIR / f"{sym}_1h.csv"
    if not p.exists():
        return None
    cols = ("open_time", "open", "high", "low", "close", "quote_volume")
    idx = (0, 1, 2, 3, 4, 7)
    buf = {c: [] for c in cols}
    with open(p, newline="") as f:
        rd = csv.reader(f)
        next(rd)  # en-tête
        for row in rd:
            for c, i in zip(cols, idx):
                buf[c].append(float(row[i]))
    return {c: np.asarray(v, dtype=np.float64) for c, v in buf.items()}


def references_et_decisions(sym, kl):
    """(dec, cache) pour UN symbole : les décisions T (2 <= T <= n-1-H_max)
    avec les références de la veille + le vwap de session, les rendements
    forward signés, ET le cache (kl, vwap, prof, day) réutilisé par le pool
    P1 (une seule lecture et un seul profil par symbole, pour toute l'étude)."""
    ts, o, h, l, c, qv = (kl["open_time"], kl["open"], kl["high"],
                          kl["low"], kl["close"], kl["quote_volume"])
    n = len(ts)
    vwap = session_vwap(ts, h, l, c, qv)
    prof = profils_jour(ts, h, l, qv)
    day = ts // 86_400_000
    # veille par décision T : le profil du jour day[T] - 1 (recherche
    # vectorisée — les journées sont contiguës, searchsorted + test d'existence)
    jours_p = np.array(sorted(prof.keys()), dtype=np.int64)
    vpoc_d = np.array([prof[int(d)][0] for d in jours_p])
    vah_d = np.array([prof[int(d)][1] for d in jours_p])
    val_d = np.array([prof[int(d)][2] for d in jours_p])
    veille = day - 1
    pos = np.clip(np.searchsorted(jours_p, veille), 0, len(jours_p) - 1)
    existe = jours_p[pos] == veille
    vpoc_p = np.where(existe, vpoc_d[pos], np.nan)
    vah_p = np.where(existe, vah_d[pos], np.nan)
    val_p = np.where(existe, val_d[pos], np.nan)
    T_max = n - 1 - max(HORIZONS)
    if T_max < 2:
        return None, (kl, vwap, prof, day)
    T = np.arange(2, T_max + 1)
    fwd = {H: (o[T + H] - o[T]) / o[T] * 1e4 for H in HORIZONS}
    jour = day[T]
    dec = {"sym": sym, "T": T, "fwd": fwd, "jour": jour,
           "o_T": o[T], "c_1": c[T - 1], "c_2": c[T - 2],
           "vwap_1": vwap[T - 1], "vwap_2": vwap[T - 2],
           "vpoc": vpoc_p[T], "vah": vah_p[T], "val": val_p[T]}
    return dec, (kl, vwap, prof, day)


def decisions_symbole(sym):
    """Compat : (dec, cache) — voir references_et_decisions."""
    kl = load_klines(sym)
    if kl is None:
        return None, None
    return references_et_decisions(sym, kl)


def d_score(dec):
    """La distance pré-déclarée au vwap de session, à T-1 :
    d = (close(T-1) − vwap(T-1)) / vwap(T-1)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return (dec["c_1"] - dec["vwap_1"]) / dec["vwap_1"]


# --------------------------- la grille pré-déclarée ---------------------------
def flags_cellule(nom, dec, d, H):
    """Renvoie (flag, fwd_signe, sens_attendu) pour une cellule de la
    grille — TOUTES les cellules sont définies ICI, une seule fois, dans
    l'ordre du pré-enregistrement (V1 12, V2 4, P1 4, P2 4, P3 4).

    Rigueur : les décisions dont la référence est ABSENTE (veille manquante,
    vwap dégénéré) sortent des DEUX classes — leur fwd est passé à NaN (la
    cellule filtre isfinite) et le flag est forcé False ; elles ne peuvent
    ni être comptées, ni polluer le complément."""
    dirn = d["dirn"]
    fwd_brut = dec["fwd"][H] if dirn == "LONG" else -dec["fwd"][H]
    sens = +1
    if nom == "V1":                            # l'aimant vwap (mean-reversion)
        seuil = d["seuil"]
        dist = d_score(dec)
        with np.errstate(invalid="ignore"):
            ok_ref = np.isfinite(dec["vwap_1"]) & np.isfinite(dist)
            if dirn == "LONG":
                flag = ok_ref & (dist <= -seuil)
            else:
                flag = ok_ref & (dist >= seuil)
        fwd = np.where(ok_ref, fwd_brut, np.nan)
        return flag, fwd, sens
    if nom == "V2":                            # le cross vwap (continuation)
        with np.errstate(invalid="ignore"):
            ok_ref = np.isfinite(dec["vwap_1"]) & np.isfinite(dec["vwap_2"])
            croise_haut = ok_ref & (dec["c_2"] < dec["vwap_2"]) & (dec["c_1"] >= dec["vwap_1"])
            croise_bas = ok_ref & (dec["c_2"] > dec["vwap_2"]) & (dec["c_1"] <= dec["vwap_1"])
        flag = croise_haut if dirn == "LONG" else croise_bas
        fwd = np.where(ok_ref, fwd_brut, np.nan)
        return flag, fwd, sens
    if nom in ("P1", "P2", "P3"):              # les cellules volume profile
        with np.errstate(invalid="ignore"):
            ok_ref = (np.isfinite(dec["vpoc"]) & np.isfinite(dec["vah"])
                      & np.isfinite(dec["val"]))
            if nom == "P1":                    # l'aimant vpoc
                flag = (ok_ref & (dec["o_T"] < dec["vpoc"])) if dirn == "LONG" \
                    else (ok_ref & (dec["o_T"] > dec["vpoc"]))
            elif nom == "P2":                  # le rejet de la value area
                flag = (ok_ref & (dec["c_1"] < dec["val"])) if dirn == "LONG" \
                    else (ok_ref & (dec["c_1"] > dec["vah"]))
            else:                              # P3 : le breakout (hypothèse opposée)
                flag = (ok_ref & (dec["c_1"] > dec["vah"])) if dirn == "LONG" \
                    else (ok_ref & (dec["c_1"] < dec["val"]))
        fwd = np.where(ok_ref, fwd_brut, np.nan)
        return flag, fwd, sens
    raise ValueError(f"cellule inconnue {nom}")


def grille_definitions():
    """Les 28 cellules, dans l'ordre du pré-enregistrement."""
    defs = []
    for s in SEUILS_D:
        for dirn in ("LONG", "SHORT"):
            for H in HORIZONS:
                defs.append(("V1", {"seuil": s, "dirn": dirn}, H,
                             f"V1 aimant s={s:.3f} {dirn} H{H}"))
    for dirn in ("LONG", "SHORT"):
        for H in HORIZONS:
            defs.append(("V2", {"dirn": dirn}, H, f"V2 cross {dirn} H{H}"))
    for dirn in ("LONG", "SHORT"):
        for H in HORIZONS:
            defs.append(("P1", {"dirn": dirn}, H, f"P1 vpoc {dirn} H{H}"))
    for dirn in ("LONG", "SHORT"):
        for H in HORIZONS:
            defs.append(("P2", {"dirn": dirn}, H, f"P2 va-rejet {dirn} H{H}"))
    for dirn in ("LONG", "SHORT"):
        for H in HORIZONS:
            defs.append(("P3", {"dirn": dirn}, H, f"P3 va-breakout {dirn} H{H}"))
    return defs


def run_focus(decs_par_sym, defs_coeur):
    """Focus BTC/ETH + AUC par symbole LIQUIDE8 (point estimates, sans boot)
    sur les cellules cœur — les robustesses (ii) et (iii) pré-déclarées."""
    res = {"focus": {}, "par_symbole": {}}
    for sym, dec in decs_par_sym:
        for nom, d, H, nom_long in defs_coeur:
            flag, fwd, sens = flags_cellule(nom, dec, d, H)
            ok = np.isfinite(fwd) & np.isfinite(flag.astype(float))
            f, fl = fwd[ok], flag[ok]
            if sym in ("BTCUSDT", "ETHUSDT"):
                n_flag = int(fl.sum())
                auc = auc_mw(f[fl], f[~fl]) if (n_flag and n_flag < len(f)) else float("nan")
                lo = hi = float("nan")
                if n_flag >= N_MIN_FLAG and (len(f) - n_flag) >= N_MIN_FLAG:
                    boots = bootstrap_flags(f, fl, dec["jour"][ok], N_BOOT_PANEL, SEED)
                    lo, hi = float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))
                res["focus"][f"{sym}|{nom_long}"] = {
                    "n": int(len(f)), "n_flag": n_flag, "auc": float(auc),
                    "ic95": [lo, hi],
                    "fwd_bps_flag": float(np.median(f[fl])) if n_flag else float("nan"),
                    "part_zeros": float(np.mean(f[fl] == 0.0)) if n_flag else float("nan"),
                    "verdict": verdict_cellule(auc, lo, hi, n_flag,
                                               len(f) - n_flag,
                                               float(np.mean(f[fl] == 0.0)) if n_flag else 1.0,
                                               sens)}
            if sym in LIQUIDE8:
                n_flag = int(fl.sum())
                auc = auc_mw(f[fl], f[~fl]) if (n_flag and n_flag < len(f)) else float("nan")
                res["par_symbole"][f"{sym}|{nom_long}"] = {
                    "n": int(len(f)), "n_flag": n_flag, "auc": float(auc)}
    return res


# --------------------------- le pool P1 en contexte ---------------------------
def pool_contexte(cache):
    """Les 2 filtres pré-déclarés sur les 469 entrées (F1 mauvais côté
    vwap, F2 hors value area de la veille). CONTEXTE — le juge reste le
    protocole A/B docs/28. Le cache (kl, vwap, prof, day) est celui déjà
    construit par run_all : une seule lecture et un seul profil par
    symbole pour toute l'étude. Les flags sont évalués sur open(T) (la
    doctrine _MK) : la colonne `entry` du pool vaut open x (1 + side x
    2 bps) (l'entrée 2 bps adverse, convention vague 4), et injecter ce
    décalage dans un filtre de référence ajouterait un bruit de 2 bps."""
    rows = list(csv.DictReader(open(POOL_CSV, newline="")))
    f1_r, f1_c, f2_r, f2_c = [], [], [], []
    n_ref_manquante = 0
    n_absent = 0
    verif_opens = {"ok": 0, "ko": 0}
    for r in rows:
        sym = r["sym"]
        if sym not in cache:
            n_absent += 1
            continue
        kl, vwap, prof, day = cache[sym]
        t_in = float(r["t_in"])
        i = int(np.searchsorted(kl["open_time"], t_in))
        if i >= len(kl["open_time"]) or kl["open_time"][i] != t_in or i < 1:
            verif_opens["ko"] += 1
            continue
        verif_opens["ok"] += 1
        side = float(r["side"])
        R = float(r["R"])
        o_T = kl["open"][i]                    # le prix d'entrée de la doctrine _MK
        with np.errstate(invalid="ignore", divide="ignore"):
            d = (o_T - vwap[i - 1]) / vwap[i - 1]
        if np.isfinite(d):
            mauvais = (d > 0) if side == 1 else (d < 0)
            (f1_r if mauvais else f1_c).append(R)
        else:
            n_ref_manquante += 1
        p = prof.get(int(day[i]) - 1)
        if p is not None and np.isfinite(p[1]):
            hors_va = (o_T > p[1]) if side == 1 else (o_T < p[2])
            (f2_r if hors_va else f2_c).append(R)
        else:
            n_ref_manquante += 1
    def filtre(r_flag, r_comp, nom):
        r_flag = np.asarray(r_flag, dtype=float)
        r_comp = np.asarray(r_comp, dtype=float)
        if len(r_flag) == 0 or len(r_comp) == 0:
            return {"filtre": nom, "n_flag": int(len(r_flag)), "n_comp": int(len(r_comp)),
                    "R_med_flag": float("nan"), "R_med_comp": float("nan"),
                    "delta_R": float("nan"), "P_boot": float("nan"),
                    "verdict": "INCONCLU"}
        dm = float(np.median(r_flag))
        dc = float(np.median(r_comp))
        P = bootstrap_verdict_pool(r_flag, r_comp, N_BOOT_POOL, SEED)
        return {"filtre": nom, "n_flag": int(len(r_flag)), "n_comp": int(len(r_comp)),
                "R_med_flag": dm, "R_med_comp": dc, "delta_R": dm - dc,
                "P_boot": P, "verdict": "CONTEXTE"}
    out = {"n_pool": len(rows), "verif_opens": verif_opens,
           "refs_manquantes": n_ref_manquante, "symboles_absents": n_absent,
           "F1_mauvais_cote_vwap": filtre(f1_r, f1_c, "F1 mauvais côté vwap session"),
           "F2_hors_value_area": filtre(f2_r, f2_c, "F2 hors value area veille")}
    return out


# --------------------------------- main ---------------------------------------
def _cellule_worker(payload):
    """Le worker du pool de cellules : (fwd, flag, jours, nom, sens) ->
    la cellule complète (AUC + boot + verdict). Chaque cellule porte SA
    seed (SEED en constante) : le résultat est identique quel que soit le
    worker qui l'exécute — le parallélisme ne touche pas au bit."""
    fwd, flag, jours, nom_long, sens = payload
    return cellule_evenement(fwd, flag, jours, nom_long, sens)


def run_panel(decs, defs, label):
    """Un panel = la grille complète sur un ensemble de symboles (pool
    entier ou LIQUIDE8). Chaque cellule : AUC flag vs complément sur les
    décisions PONDÉRÉES par symbole (le pool), IC bootstrap par journées.
    Les boots (le coût dominant) sont répartis sur min(2, cpu) workers —
    même partition, même seed par cellule, résultat bit à bit identique."""
    payloads = []
    for nom, d, H, nom_long in defs:
        f_all, fl_all, j_all = [], [], []
        for dec in decs:
            flag, fwd, sens = flags_cellule(nom, dec, d, H)
            ok = np.isfinite(fwd)
            f_all.append(fwd[ok])
            fl_all.append(flag[ok])
            j_all.append(dec["jour"][ok])
        payloads.append((np.concatenate(f_all), np.concatenate(fl_all),
                         np.concatenate(j_all), nom_long, sens))
    n_proc = min(2, multiprocessing.cpu_count())
    if n_proc > 1 and len(payloads) > 1:
        try:
            with multiprocessing.Pool(n_proc) as pool:
                cells = pool.map(_cellule_worker, payloads)
        except Exception:                     # environnement sans fork : séquentiel
            cells = [_cellule_worker(p) for p in payloads]
    else:
        cells = [_cellule_worker(p) for p in payloads]
    res = {}
    for (nom, d, H, nom_long), cell in zip(defs, cells):
        cell["famille"] = nom
        cell["panel"] = label
        res[nom_long] = cell
    return res


def run_all():
    t0 = time.time()
    syms = sorted(p.name[:-7] for p in DATA_DIR.glob("*_1h.csv"))
    decs = []
    cache = {}
    for sym in syms:
        kl = load_klines(sym)
        if kl is None or len(kl["open_time"]) < 200:
            continue
        dec, ref = references_et_decisions(sym, kl)
        if dec is not None:
            decs.append(dec)
        cache[sym] = ref
    defs = grille_definitions()
    decs_l8 = [d for d in decs if d["sym"] in LIQUIDE8]
    res = {
        "etude": "x501_refs_local.py — VAGUE 7 : le banc des références de "
                 "liquidité (vwap session + volume profile veille)",
        "discipline": "pré-enregistrée dans l'en-tête du script AVANT toute "
                      "mesure (grille, seuils, tie-breaks, verdicts) — seed "
                      f"{SEED}, {N_BOOT_PANEL} boot AUC / {N_BOOT_POOL} boot pool",
        "data_dir": str(DATA_DIR),
        "n_symboles": len(decs),
        "n_symboles_liquide8": len(decs_l8),
        "n_decisions": int(sum(len(d["T"]) for d in decs)),
        "grille": {
            "V1": "aimant vwap (mean-reversion) : flag LONG d<=−s / SHORT d>=+s, "
                  f"s ∈ {SEUILS_D}",
            "V2": "cross vwap (continuation)",
            "P1": "aimant vpoc de la veille",
            "P2": "rejet value area (mean-reversion)",
            "P3": "breakout value area (hypothèse opposée)",
            "n_cellules": len(defs),
        },
        "panel_pool": run_panel(decs, defs, "POOL80"),
    }
    res["panel_liquide8"] = run_panel(decs_l8, defs, "LIQUIDE8")
    defs_coeur = [d for d in defs if d[0] in ("V1", "P2", "P3")
                  and (d[0] != "V1" or d[1]["seuil"] == 0.0)]
    par_sym = sorted([(d["sym"], d) for d in decs if d["sym"] in LIQUIDE8])
    res["robustesse"] = run_focus(par_sym, defs_coeur)
    res["pool_p1"] = pool_contexte(cache)
    # le bilan mécanique des verdicts
    bilan = {}
    for panel in ("panel_pool", "panel_liquide8"):
        for k, v in res[panel].items():
            bilan[v["verdict"]] = bilan.get(v["verdict"], 0) + 1
    res["bilan_verdicts"] = bilan
    res["duree_s"] = round(time.time() - t0, 1)
    return res


def main():
    res = run_all()
    payload = json.dumps(res, ensure_ascii=False, sort_keys=True, indent=1)
    OUT_JSON.write_text(payload, encoding="utf-8")
    print(f"[refs_local] {res['n_symboles']} symboles, "
          f"{res['n_decisions']} décisions, {res['duree_s']} s")
    print(f"[refs_local] verdicts : {res['bilan_verdicts']}")
    print(f"[refs_local] pool P1 : F1 delta_R={res['pool_p1']['F1_mauvais_cote_vwap']['delta_R']:.3f} "
          f"P={res['pool_p1']['F1_mauvais_cote_vwap']['P_boot']:.4f} | "
          f"F2 delta_R={res['pool_p1']['F2_hors_value_area']['delta_R']:.3f} "
          f"P={res['pool_p1']['F2_hors_value_area']['P_boot']:.4f}")
    cand = [(k, v["verdict"]) for panel in ("panel_pool", "panel_liquide8")
            for k, v in res[panel].items() if v["verdict"] == "CANDIDAT"]
    print(f"[refs_local] CANDIDATS : {cand if cand else 'aucun'}")
    print(f"[refs_local] écrit : {OUT_JSON} ({len(payload)} octets)")


if __name__ == "__main__":
    main()
