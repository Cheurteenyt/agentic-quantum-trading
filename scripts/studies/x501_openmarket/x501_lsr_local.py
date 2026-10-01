#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_lsr_local.py — VAGUE 11 : LE BANC DU LSR (long/short account ratio
Bybit, la dernière source premium du filtre RI non falsifiée — docs/27
vague 1 « LSR top traders contrarian », docs/26 « le LSR 4h (8 jours) ne
permet aucun test de gate »). LA SOURCE A CHANGÉ D'ÉCHELLE : le collecteur
versionné x501_collect_lsr_v11.py (Bybit v5 public, pagination cursor) livre
72 000 lignes LSR 4h + 13 200 lignes LSR 1d sur les 12 symboles om_v27,
fenêtre commune 2024-01-04 -> 2026-10-01 (~2,74 ans) — le LSR passe de 8 j
intestables à un panel profond falsifiable.

LA DISCRIMINATION AVEC LES VAGUES PRÉCÉDENTES (pré-enregistrée le 01/10/2026,
AVANT toute mesure — aucune cellule n'a été regardée avant l'écriture de ce
fichier) :
  vague 5 : le funding (prix du positionnement payé) -> KILL ;
  vague 8 : le FLUX du CAPITAL (ΔOI) -> 10/10 KILL ;
  vague 9 : le NIVEAU du CAPITAL (z-score OI) -> magnitude REFUSÉE + direction KILL ;
  vague 10 : la FORME en U du régime capital -> U non établi, le côté bas
             de la purge = 2 premiers CANDIDATS marginaux du domaine ;
  vague 11 : le POSITIONNEMENT DE LA FOULE (fraction de comptes long) —
             l'hypothèse contrarian du filtre RI (la foule longue pré-cède
             la baisse) et son miroir le flux du positionnement (la
             BASCULE de la foule), la seule famille premium restée sans
             banc faute de profondeur.

LA DISCIPLINE (gravée AVANT tout chiffre) :

  GRILLE PRÉ-DÉCLARÉE (TOUTES les cellules sont mesurées et rapportées,
  même celles qui déçoivent) — 13 cellules :
    ÉTUDE A — CONTRARIAN NIVEAU (l'hypothèse du filtre RI, docs/27, testée
      sur le LSR Bybit TOUS COMPTES — la seule source LSR profonde gratuite,
      famille adjacente, limite L1) :
      score = z_L(buyRatio), z-score roulant du NIVEAU de la fraction de
      comptes longs, std de population (ddof=0), fenêtre STRICTEMENT au
      passé ; L ∈ {180, 540} barres 4h (30 j, 90 j — transposition exacte
      des lookbacks vague 9) ; cible = fwd_H SIGNÉ (open->open, doctrine
      _MK) ; H ∈ {6, 18} barres 4h (24 h, 72 h — les horizons du domaine) ;
      sens_attendu = −1 (foule longue -> baisse attendue, AUC < 0,5
      confirmé). 4 cellules.
    ÉTUDE B — FLUX DU POSITIONNEMENT (la bascule, discrimination avec la
      vague 8 qui mesurait le flux du CAPITAL ΔOI) :
      score = buyRatio[t-1] - buyRatio[t-1-L_delta] (variation du niveau
      sur L_delta barres 4h, les comptes qui basculent), L_delta ∈ {6, 42}
      barres 4h (1 j, 7 j) ; cible = fwd_H SIGNÉ, H ∈ {6, 18} ;
      sens_attendu = −1 (bascule long de la foule -> reversal). 4 cellules.
    ÉTUDE C — RÉPLICATION 1d (la profondeur séculaire du même endpoint,
      1 100 lignes/symbol) :
      score = z_L(buyRatio 1d), L ∈ {30, 90} barres 1d (30 j, 90 j) ;
      cible = fwd_H SIGNÉ, H ∈ {1, 3} barres 1d (24 h, 72 h) ;
      sens_attendu = −1. 4 cellules. (Sur ce panel le bootstrap par
      journées = par barres — 1 barre/jour — l'IC ne corrige aucune
      autocorrélation, limite L8.)
    ÉTUDE D — POOL P1 EN CONTEXTE (CONTEXTE par nature, jamais promotion) :
      les 469 entrées certifiées rejouées avec z_180(buyRatio 4h) au t_in ;
      la ligne consommée = la dernière estampillée T avec T + P <= t_in
      (searchsorted sur la série LSR, aucune exigence de pile avec une
      open kline — la série LSR EST la grille) ; split médian, R haut vs
      bas, bootstrap diff de médianes 10 000, seed 501. In-sample de la
      sélection + cross-exchange (L4) : le statut CONTEXTE est figé, le
      gate P >= 0,70 ne fait que mesurer la force du contraste.

  CONVENTION TEMPS STRICTE (transposée des vagues 8/9/10) : la ligne LSR
  estampillée T couvre une fenêtre de P et n'est JAMAIS lue avant T+P —
  à l'open de la barre t, la dernière ligne connue est t-P ; la ligne
  estampillée pile à l'open de décision n'est JAMAIS lue (le shift
  s_full[1:] = score[:-1] grave la règle au bit près, mécanique vague 9).
  SÉMANTIQUE D'ESTAMPILLAGE (mesurée par la sonde scripts/lsr_probe_v11,
  8 passes programmées (9 prélèvements, double instance au lancement) à cheval sur la frontière 03:00 UTC du 01/10/2026 ; VERDICT
  gravé 03:15 UTC AVANT le commit, la mécanique d'analyse inchangée) :
  la sonde TRANCHE en faveur de l'interprétation END — la ligne
  estampillée T couvre [T-P, T) et est publiée FINALISÉE ≤ ~4,7 min après
  T (la ligne 1h 03:00 apparue à 03:04:44, la ligne 02:00 jamais réécrite
  sur 9 passes) ; aucune ligne partielle n'est exposée par l'endpoint.
  La règle de consommation (barre t lit la ligne t-P) lit donc des
  fenêtres closes à t-P avec une période entière de marge — conservative,
  zéro look-ahead impossible ; sous l'interprétation START elle aurait
  lu [t-P, t) close à t — la règle était SÛRE SOUS LES DEUX CAS, la
  mesure tranche le lag déclaratif (une période, pas deux).
  Klines connues à l'open de t : indices <= t-1. Forward = open(t+H) -
  open(t) en bps.

  CAS DÉGÉNÉRÉS PRÉ-DÉCLARÉS : std_L = 0 (fenêtre plate) -> score NaN ->
  décision invalidée, comptée ; amorçage L-1 barres -> NaN, compté (les
  invalidées de la famille A sont comptées à L=540, la plus longue ; les
  cellules B/C portent leur amorçage dans leur n) ; ligne LSR absente pile
  sur une open kline -> NaN, comptée (0 attendu, audit de collecte) ;
  buyRatio hors (0, 1) -> invalidé, compté (0 attendu).

  VERDICT MÉCANIQUE PAR CELLULE (critère AUC du domaine, inchangé,
  copié bit à bit de la vague 9) :
  KILL si IC 95 % contient 0,5 et |AUC-0,5| < 0,02 ; INCONCLU si l'IC
  contient 0,5 ; CANDIDAT si l'IC EXCLUT 0,5 ET |AUC-0,5| >= 0,05 ET le
  sens CONFIRME l'hypothèse pré-déclarée (études A/B/C, sens -1) ;
  CONTEXTE si l'IC exclut 0,5 mais le sens s'y OPPOSE. IC = bootstrap
  1 000 par journées UTC, seed 501, réduction 50 000 — la mécanique
  exacte des vagues 5/8/9/10.

  BANDES DE COÛTS (rappel docs/26) : taker 6,1 bps/côté, maker 2 bps/côté ;
  l'étalon d'exploitabilité = 12,2 bps A/R taker. Un delta sans AUC n'est
  pas un plan (leçon vague 7) : les deltas médianes sont DESCRIPTIFS.

  PANEL : les 12 symboles om_v27, LSR ET klines du MÊME exchange (Bybit v5,
  linear) — zéro cross-exchange dans le panel (le pool D croise, lui,
  des entrées Binance avec le LSR Bybit, limite L4 assumée). La fenêtre
  d'étude = la fenêtre KLINE commune par symbole ; le z-score roulant
  reste STRICTEMENT dans cette fenêtre (l'amorçage consomme L-1 barres
  par symbole, invalidées comptées — discipline vague 9 transposée).

Limites assumées (pré-enregistrées) :
  L1 le LSR Bybit account-ratio est la fraction de COMPTES longs (1 compte
     = 1 voix, indépendamment de la taille), pas un ratio notionnel ni le
     « top traders » Binance cité dans le filtre RI (docs/27) — le banc
     teste la FAMILLE du signal (positionnement de la foule) sur la seule
     source profonde gratuite, pas l'instrument exact du filtre ;
  L2 publication finalisée peu après T (sonde v11 : sémantique END, δ ≤
     ~4,7 min mesuré au 1h) — en backtest la ligne [t-2P, t-P) est lue à
     l'open t (une période entière de marge, conservative) ; le délai de
     publication live exact sera mesuré par le papier v11 ;
  L3 la sémantique d'estampillage est TRANCHÉE par la sonde (END, cf.
     convention temps) — la règle de consommation était sûre sous les deux
     cas, la mesure ne change que le lag déclaratif ;
  L4 le pool D croise des entrées pool (data Binance) avec le LSR Bybit —
     cross-exchange assumé (arbitrage à la seconde), CONTEXTE par nature ;
  L5 horizons en barres (gaps rares comptés) — doctrine _MK ;
  L6 la dichotomie à la médiane mesure la séparation HAUT/BAS, pas la
     forme de la relation (leçon vague 5) ; la FORME EN U du LSR n'est
     PAS testée ici — toute extension exigerait un pré-enregistrement
     ultérieur (leçon vague 10) ;
  L7 le z-score est relatif à la fenêtre kline (~2,74 ans), pas séculaire ;
  L8 panel 1d : le rééchantillonnage bootstrap par journées = par barres
     (1 barre/jour), l'IC ne corrige aucune autocorrélation sur ce panel ;
  L9 le buyRatio compte des COMPTES : une foule de petits comptes longs et
     un seul gros short donnent un LSR long — la leçon des squeezes ; le
     signal est testé tel quel (c'est lui que le endpoint livre gratuitement).

Reproduction :
  X501_LSR_DIR=<dir des {SYM}_klines_240.jsonl, {SYM}_klines_D.jsonl,
               {SYM}_lsr_4h.jsonl, {SYM}_lsr_1d.jsonl> \
      python3 x501_lsr_local.py
  (défaut : data/x501_lsr du repo ; la collecte est re-exécutable avec
  x501_collect_lsr_v11.py — collecteur versionné vague 11, inchangé)
Sorties : lsr_local.json (versionné, déterministe) + résumé console.
"""
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LSR_DIR = Path(os.environ.get("X501_LSR_DIR", HERE / "../../../data/x501_lsr"))
POOL_CSV = HERE / "pool_P1_entrees.csv"
OUT_JSON = HERE / "lsr_local.json"

# ---------------------- grille PRÉ-DÉCLARÉE (01/10/2026) ----------------------
LOOKBACKS_Z_4H = [180, 540]           # barres 4h (30 j, 90 j) — étude A
DELTAS_L_4H = [6, 42]                 # barres 4h (1 j, 7 j) — étude B (flux)
HORIZONS_4H = [6, 18]                 # barres 4h (24 h, 72 h) — études A et B
LOOKBACKS_Z_1D = [30, 90]             # barres 1d (30 j, 90 j) — étude C
HORIZONS_1D = [1, 3]                  # barres 1d (24 h, 72 h) — étude C
POOL_L = 180                          # L du z-score projeté sur le pool (4h)

# ---------------------- verdict mécanique (critère domaine) -------------------
SEED = 501
N_BOOT_PANEL = 1_000                  # IC bootstrap AUC, par journées UTC
N_BOOT_POOL = 10_000                  # mécanique verdict_ab (diff de médiane)
REDUCTION_BOOT = 50_000               # points max par cellule pour le boot
AUC_MORTE = 0.02                      # |AUC-0,5| < 0,02 et IC contient 0,5 -> KILL
AUC_CANDIDAT = 0.05                   # séparation minimale d'un CANDIDAT
COUT_AR_TAKER_BPS = 12.2              # 2 x 6,1 — l'étalon d'exploitabilité

MS_4H = 4 * 3_600_000
MS_1D = 86_400_000

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "APTUSDT", "1000PEPEUSDT"]


# ------------------------------- utils ----------------------------------------
def rangs_moyens(x):
    """Rangs 1..n avec rangs moyens sur les ex-aequo (vectorisé, stable).
    Mécanique exacte des vagues 5/8/9/10 : bornes de blocs + np.repeat."""
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
    exacte des vagues 5/8/9/10."""
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
    les lignes <= (t-P)). NaN d'amorçage sur les L-1 premières barres ;
    std=0 -> NaN (décision invalidée, comptée par l'appelant).
    Sommes cumulées float64 — O(n) par cellule. CAS DÉGÉNÉRÉ (pré-déclaré,
    leçon vague 9) : std -> 0 (fenêtre plate) : les erreurs d'arrondi float64
    de var = s2/L - m^2 laissent un résidu ~1e-14 qui produirait z = +-inf ;
    le score est donc forcé à NaN quand sd <= 1e-6 x max(1, |m|) (seuil
    RELATIF d'échelle : une fenêtre dont la dispersion relative est < 1e-6
    est indistinguable d'une constante aux erreurs float près) — une fenêtre
    plate n'informe pas le régime, la décision est invalidée (comptée)."""
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


def delta_niveaux(arr, Ld):
    """Variation du niveau sur Ld barres : d[j] = arr[j] - arr[j-Ld],
    NaN d'amorçage sur les Ld premières barres (pré-déclaré)."""
    n = len(arr)
    d = np.full(n, np.nan)
    if Ld >= n:
        return d
    d[Ld:] = arr[Ld:] - arr[:n - Ld]
    return d


# ------------------------------- chargement -----------------------------------
def load_klines(sym, tag):
    """Klines Bybit depuis le JSONL de collecte (ts,o,h,l,c,v,qv).
    Déduplication par ts (index unique, leçon audit v27) + tri asc.
    tag = '240' (4h) ou 'D' (1d)."""
    p = LSR_DIR / f"{sym}_klines_{tag}.jsonl"
    if not p.exists():
        return None
    rows = []
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            rows.append((int(r["ts"]), float(r["o"])))
    a = np.asarray(rows, dtype=np.float64)
    n_dup = len(a) - len(np.unique(a[:, 0]))
    uniq_idx = np.unique(a[:, 0], return_index=True)[1]
    a = a[uniq_idx]
    order = np.argsort(a[:, 0], kind="mergesort")
    a = a[order]
    return {"ts": a[:, 0].astype(np.int64), "o": a[:, 1], "n_dup": n_dup}


def load_lsr(sym, tag):
    """LSR Bybit depuis le JSONL de collecte (ts, buyRatio, sellRatio).
    Dédup + tri asc. Contrôle de domaine : 0 < buyRatio < 1 (sinon NaN,
    compté par l'appelant)."""
    p = LSR_DIR / f"{sym}_lsr_{tag}.jsonl"
    if not p.exists():
        return None
    t, v = [], []
    n_hors_domaine = 0
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            b = float(r["buyRatio"])
            if not (0.0 < b < 1.0):
                n_hors_domaine += 1
                continue
            t.append(int(r["ts"]))
            v.append(b)
    ts = np.asarray(t, dtype=np.int64)
    val = np.asarray(v, dtype=np.float64)
    uniq_idx = np.unique(ts, return_index=True)[1]
    n_dup = len(ts) - len(uniq_idx)
    ts, val = ts[uniq_idx], val[uniq_idx]
    order = np.argsort(ts, kind="mergesort")
    return {"ts": ts[order], "buy": val[order], "n_dup": n_dup,
            "n_hors_domaine": n_hors_domaine}


def snap_lsr_sur_barres(ot, lsr_ts, lsr_val):
    """Ligne LSR alignée PILE sur chaque open kline : arr[j] = buyRatio de la
    ligne estampillée pile au ts de la barre j, NaN si absente pile.
    Aucun fill-forward. ATTENTION sémantique : la ligne estampillée à l'open
    de la barre j couvre une fenêtre COMMENÇANT à j — le shift
    s_full[1:] = score[:-1] de l'appelant garantit qu'elle n'est JAMAIS lue
    par sa propre barre (la barre t lit la ligne estampillée t-P)."""
    n = len(ot)
    arr = np.full(n, np.nan)
    idx = np.searchsorted(lsr_ts, ot)
    ok = (idx < len(lsr_ts)) & (lsr_ts[np.minimum(idx, len(lsr_ts) - 1)] == ot)
    arr[ok] = lsr_val[idx[ok]]
    return arr


# ------------------------------ cellules --------------------------------------
def cellule_panel(score, fwd, jours, hypothese, sens_attendu):
    """Une cellule de panel : AUC full-sample, IC bootstrap par journées,
    verdict mécanique (critère du domaine, copie bit à bit vague 9) —
    sens_attendu ∈ {+1,-1,0} ; 0 = aucune hypothèse directionnelle
    pré-déclarée -> toute séparation est CONTEXTE (jamais CANDIDAT)."""
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
    fam_a = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_Z_4H for h in HORIZONS_4H}
    fam_b = {(ld, h): {"s": [], "f": [], "j": []} for ld in DELTAS_L_4H for h in HORIZONS_4H}
    fam_c = {(lb, h): {"s": [], "f": [], "j": []} for lb in LOOKBACKS_Z_1D for h in HORIZONS_1D}
    n_bars_tot, n_dup_k, n_dup_l = 0, 0, 0
    n_snap_absents = 0
    n_hors_domaine = 0
    n_invalidees_amorcage = 0     # barres avec z NaN pour cause d'amorçage (L=540)
    n_invalidees_std0 = 0         # barres avec z NaN pour cause de std=0 (L=540)
    fen_t0, fen_t1 = None, None
    audit_syms = {}

    for sym in SYMBOLS:
        kl4 = load_klines(sym, "240")
        kl1 = load_klines(sym, "D")
        ls4 = load_lsr(sym, "4h")
        ls1 = load_lsr(sym, "1d")
        if kl4 is None or kl1 is None or ls4 is None or ls1 is None:
            raise SystemExit(f"data manquante pour {sym} dans {LSR_DIR}")
        ot, op = kl4["ts"], kl4["o"]
        n = len(ot)
        n_bars_tot += n
        n_dup_k += kl4["n_dup"] + kl1["n_dup"]
        n_dup_l += ls4["n_dup"] + ls1["n_dup"]
        n_hors_domaine += ls4["n_hors_domaine"] + ls1["n_hors_domaine"]
        fen_t0 = ot[0] if fen_t0 is None else min(fen_t0, ot[0])
        fen_t1 = ot[-1] if fen_t1 is None else max(fen_t1, ot[-1])
        gaps_k = int((np.diff(ot) != MS_4H).sum())
        in_win = ls4["ts"] >= ot[0]
        gaps_l_in = int((np.diff(ls4["ts"][in_win]) != MS_4H).sum())
        arr_lsr = snap_lsr_sur_barres(ot, ls4["ts"], ls4["buy"])
        n_snap_absents += int(np.isnan(arr_lsr).sum())
        jours4 = (ot // MS_1D).astype(np.int64)
        fwd4 = {}
        for h in HORIZONS_4H:
            ret = np.full(n, np.nan)
            if n > h:
                ret[:n - h] = (op[h:] - op[:n - h]) / op[:n - h] * 1e4
            fwd4[h] = ret
        audit_syms[sym] = {"n_klines_4h": n, "n_lsr_4h": len(ls4["ts"]),
                           "gaps_klines_4h": gaps_k, "gaps_lsr_4h_in_win": gaps_l_in,
                           "n_snap_absents": int(np.isnan(arr_lsr).sum()),
                           "n_lsr_hors_domaine": ls4["n_hors_domaine"] + ls1["n_hors_domaine"]}

        # ---- ÉTUDE A — contrarian niveau (4h) ----
        zs = {lb: rolling_z(arr_lsr, lb) for lb in LOOKBACKS_Z_4H}
        # comptage figé au L le plus long (540) — sinon cumul trompeur (leçon vague 8)
        z540 = zs[540]
        n_invalidees_amorcage += int(np.isnan(z540[:540 - 1]).sum())
        n_invalidees_std0 += int((np.isnan(z540[540 - 1:]) &
                                  np.isfinite(arr_lsr[540 - 1:])).sum())
        for lb in LOOKBACKS_Z_4H:
            z = zs[lb]
            s_full = np.full(n, np.nan)
            s_full[1:] = z[:-1]          # la ligne t-P… la ligne pile à t n'est JAMAIS lue
            for h in HORIZONS_4H:
                ok = np.isfinite(s_full) & np.isfinite(fwd4[h])
                ca = fam_a[(lb, h)]
                ca["s"].append(s_full[ok])
                ca["f"].append(fwd4[h][ok])          # fwd SIGNÉ, sens -1
                ca["j"].append(jours4[ok])

        # ---- ÉTUDE B — flux du positionnement (4h) ----
        for ld in DELTAS_L_4H:
            d = delta_niveaux(arr_lsr, ld)
            s_full = np.full(n, np.nan)
            s_full[1:] = d[:-1]          # la ligne pile à t n'est JAMAIS lue
            for h in HORIZONS_4H:
                ok = np.isfinite(s_full) & np.isfinite(fwd4[h])
                cb = fam_b[(ld, h)]
                cb["s"].append(s_full[ok])
                cb["f"].append(fwd4[h][ok])          # fwd SIGNÉ, sens -1
                cb["j"].append(jours4[ok])

        # ---- ÉTUDE C — réplication 1d ----
        ot1, op1 = kl1["ts"], kl1["o"]
        n1 = len(ot1)
        arr1 = snap_lsr_sur_barres(ot1, ls1["ts"], ls1["buy"])
        n_snap_absents += int(np.isnan(arr1).sum())
        jours1 = (ot1 // MS_1D).astype(np.int64)
        fwd1 = {}
        for h in HORIZONS_1D:
            ret = np.full(n1, np.nan)
            if n1 > h:
                ret[:n1 - h] = (op1[h:] - op1[:n1 - h]) / op1[:n1 - h] * 1e4
            fwd1[h] = ret
        for lb in LOOKBACKS_Z_1D:
            z = rolling_z(arr1, lb)
            s_full = np.full(n1, np.nan)
            s_full[1:] = z[:-1]
            for h in HORIZONS_1D:
                ok = np.isfinite(s_full) & np.isfinite(fwd1[h])
                cc = fam_c[(lb, h)]
                cc["s"].append(s_full[ok])
                cc["f"].append(fwd1[h][ok])          # fwd SIGNÉ, sens -1
                cc["j"].append(jours1[ok])

    # ---------------- verdict des 12 cellules de panel -------------------------
    res_a, res_b, res_c, verdicts = {}, {}, {}, []
    for lb in LOOKBACKS_Z_4H:
        for h in HORIZONS_4H:
            c = fam_a[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "contrarian niveau : foule longue -> baisse (hypothèse RI, docs/27)", -1)
            res_a[f"L{lb}_H{h}"] = r
            verdicts.append(r["verdict"])
    for ld in DELTAS_L_4H:
        for h in HORIZONS_4H:
            c = fam_b[(ld, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "flux du positionnement : bascule long -> reversal (miroir flux vague 8)", -1)
            res_b[f"D{ld}_H{h}"] = r
            verdicts.append(r["verdict"])
    for lb in LOOKBACKS_Z_1D:
        for h in HORIZONS_1D:
            c = fam_c[(lb, h)]
            s = np.concatenate(c["s"]); f = np.concatenate(c["f"]); j = np.concatenate(c["j"])
            r = cellule_panel(s, f, j, "réplication 1d du contrarian niveau (profondeur séculaire)", -1)
            res_c[f"L{lb}_H{h}"] = r
            verdicts.append(r["verdict"])

    # ------------------------- ÉTUDE D — pool P1 --------------------------------
    pool = []
    with open(POOL_CSV, newline="") as f:
        for row in csv.DictReader(f):
            pool.append((row["sym"], int(row["t_in"]), float(row["R"])))
    cache = {}

    def serie_pool(sym):
        """z_180(buyRatio 4h) évalué sur la SÉRIE LSR (la grille = les lignes) ;
        la ligne consommée pour t_in = la dernière estampillée T avec
        T + P <= t_in — searchsorted sur lsr_ts, zéro look-ahead."""
        if sym not in cache:
            ls = load_lsr(sym, "4h") if sym in SYMBOLS else None
            if ls is None:
                cache[sym] = None
            else:
                z = rolling_z(ls["buy"], POOL_L)
                cache[sym] = (ls["ts"], z)
        return cache[sym]

    rows = []
    n_hors_panel = 0
    n_hors_fenetre = 0
    n_score_nan = 0
    for sym, t_in, R in pool:
        sc = serie_pool(sym)
        if sc is None:
            n_hors_panel += 1
            continue
        lts, z = sc
        # dernière ligne T avec T + P <= t_in  <=>  T <= t_in - P
        idx = int(np.searchsorted(lts, t_in - MS_4H, side="right")) - 1
        if idx < 0:
            n_hors_fenetre += 1
            continue
        s_val = z[idx]
        if not np.isfinite(s_val):
            n_score_nan += 1
            continue
        rows.append((float(s_val), R))
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
    cD = {
        "nom": f"z_lsr_L{POOL_L}", "n": int(ok.sum()),
        "n_hors_panel": n_hors_panel, "n_hors_fenetre": n_hors_fenetre,
        "n_score_nan": n_score_nan,
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
        "outils": "x501_lsr_local.py — vague 11 : banc du LSR (long/short account ratio Bybit)",
        "grille_pre_declaree": {
            "date": "2026-10-01",
            "lookbacks_z_4h_barres": LOOKBACKS_Z_4H,
            "deltas_l_4h_barres": DELTAS_L_4H,
            "horizons_4h_barres": HORIZONS_4H,
            "lookbacks_z_1d_barres": LOOKBACKS_Z_1D,
            "horizons_1d_barres": HORIZONS_1D,
            "pool_L": POOL_L,
            "hypothese_A": "contrarian niveau : foule longue -> baisse (sens -1, hypothèse RI docs/27)",
            "hypothese_B": "flux du positionnement : bascule long -> reversal (sens -1, miroir flux vague 8)",
            "hypothese_C": "réplication 1d du contrarian niveau (sens -1)",
            "criterion": f"AUC IC95 exclut 0,5 et |AUC-0,5|>={AUC_CANDIDAT} = CANDIDAT ; "
                         f"IC contient 0,5 et |AUC-0,5|<{AUC_MORTE} = KILL ; sinon INCONCLU",
            "panel": SYMBOLS,
        },
        "fenetre": {
            "lsr_dir": LSR_DIR.name, "n_symboles": len(SYMBOLS),
            "n_barres_4h": n_bars_tot, "t0": int(fen_t0), "t1": int(fen_t1),
            "dup_klines": n_dup_k, "dup_lsr": n_dup_l,
            "lsr_hors_domaine": n_hors_domaine,
            "snap_absents": n_snap_absents,
            "invalidees_amorcage_L540": n_invalidees_amorcage,
            "invalidees_std0_L540": n_invalidees_std0,
            "cout_ar_taker_bps": COUT_AR_TAKER_BPS,
        },
        "audit_par_symbole": audit_syms,
        "etude_A_contrarian_niveau_4h": res_a,
        "etude_B_flux_positionnement_4h": res_b,
        "etude_C_replication_1d": res_c,
        "resume_verdicts_panel": compte,
        "etude_D_pool_P1": cD,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    digest = hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    out["digest_sha256"] = digest
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    # ------------------------------ console -------------------------------------
    print(f"LSR BANC — {len(SYMBOLS)} symboles, {n_bars_tot} barres 4h, "
          f"doublons k={n_dup_k} l={n_dup_l}, snap absents {n_snap_absents}, "
          f"LSR hors domaine {n_hors_domaine}")
    print(f"  invalidées : amorçage L540 {n_invalidees_amorcage}, std0 L540 {n_invalidees_std0}")
    print(f"  fenêtre : {fen_t0} -> {fen_t1}")
    print("\nÉTUDE A — CONTRARIAN NIVEAU z_L(buyRatio) -> fwd signé (sens -1 : foule longue = baisse attendue)")
    for k, r in res_a.items():
        print(f"  {k:>10}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.2f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print("\nÉTUDE B — FLUX DU POSITIONNEMENT Δ buyRatio -> fwd signé (sens -1 : bascule long = reversal)")
    for k, r in res_b.items():
        print(f"  {k:>10}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.2f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print("\nÉTUDE C — RÉPLICATION 1d z_L(buyRatio 1d) -> fwd signé (sens -1)")
    for k, r in res_c.items():
        print(f"  {k:>10}: AUC {r['auc']:.4f}  IC [{r['ic95'][0]:.4f}, {r['ic95'][1]:.4f}]"
              f"  delta {r['delta_bps']:+.2f} bps  n {r['n']:>7}  -> {r['verdict']}")
    print(f"\nRésumé verdicts panel : {compte}")
    print(f"\nÉTUDE D — pool P1 (CONTEXTE, in-sample + cross-exchange L4)")
    print(f"  n {cD['n']} (hors panel {cD['n_hors_panel']}, hors fenêtre {cD['n_hors_fenetre']}, "
          f"score NaN {cD['n_score_nan']})  "
          f"R méd haut {cD['R_med_haut']:+.3f} vs bas {cD['R_med_bas']:+.3f}  "
          f"delta {cD['delta_med_R']:+.3f}  P(delta>0) {cD['P_delta_sup_0']:.4f}")
    print(f"\nJSON -> {OUT_JSON}")
    print(f"SHA-256 : {digest}")


if __name__ == "__main__":
    main()
