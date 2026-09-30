#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_verdict_ab.py — LE MOTEUR DE VERDICT DES BACKTESTS A/B PRÉ-ENREGISTRÉS
(docs/28). OpenMarket x501 — stdlib pure, portable, bit-à-bit reproductible.

Il lit deux exports CSV du testeur kScript (format « trades » : colonnes
entree_utc,sortie_utc,sens,qty,entree_px,sortie_px_moy,stop_initial,
risque_usd,pnl_usd_net,R,sorties) et applique les critères PRÉ-ENREGISTRÉS
du 01/10/2026 (figés AVANT tout run, identiques à docs/28) :

  DATA_ABSENTE  n_B >= 97 % de n_A -> le filtre n'a rien filtré (fail-open,
                data premium absente) — ce n'est PAS « aucun effet ».
  PROMOTION     n_B >= N_MIN ET P(bootstrap médiane B > A) >= 0,70
                ET (méd_B - méd_A) >= +0,10 R ET maxDD_B <= maxDD_A + 2,0 R
  KILL          P <= 0,40 ET n_B >= 10 (l'anti-signal est réel)
  INCONCLU      tout le reste -> renvoyé au forward / fenêtre élargie,
                JAMAIS de promotion sur n_B < N_MIN.

Usage :
  python3 x501_verdict_ab.py CONTROLE.csv TRAITEMENT.csv --label "RI-BTC"
  python3 x501_verdict_ab.py signature.csv signature_ri.csv --n-min 20
  python3 x501_verdict_ab.py signature.csv absorption.csv --n-min 12

Le bootstrap (10 000 rééchantillonnages, seed 501) est déterministe :
deux exécutions sur les mêmes CSV donnent le même verdict au bit près.
Sortie : rapport français + verdict. Code retour 0 = rapport produit."""
import argparse
import csv
import math
import random
import statistics
import sys
from pathlib import Path

# ---------------- SEUILS PRÉ-ENREGISTRÉS (figés le 01/10/2026, docs/28) ------
DATE_PRE_ENREGISTREMENT = "2026-10-01"
SEED_BOOTSTRAP = 501
N_BOOTSTRAP = 10_000
P_PROMOTION = 0.70          # P(méd_B > méd_A) minimale
P_KILL = 0.40               # P(méd_B > méd_A) maximale pour un KILL
DELTA_R_MIN = 0.10          # gain médian minimal en R
DD_TOLERANCE_R = 2.0        # dégradation max du drawdown (en R)
N_KILL_MIN = 10             # n_B minimal pour oser un KILL
FILTRE_TRANSPARENT = 0.97   # n_B >= 97 % de n_A = le filtre n'a rien filtré

COLONNES_ATTENDUES = {"entree_utc", "sortie_utc", "sens", "R", "pnl_usd_net"}


def lire_csv(chemin):
    """Lit un export trades kScript, renvoie la liste des R (float) + n."""
    p = Path(chemin)
    if not p.exists():
        sys.exit(f"ERREUR : fichier introuvable {p}")
    lignes = []
    with p.open(newline="", encoding="utf-8") as f:
        lecteur = csv.DictReader(f)
        cols = set(lecteur.fieldnames or [])
        manquantes = COLONNES_ATTENDUES - cols
        if manquantes:
            sys.exit(f"ERREUR : {p.name} — colonnes absentes {sorted(manquantes)}")
        for row in lecteur:
            brut = (row.get("R") or "").strip()
            if not brut:
                continue  # trade encore ouvert (sortie vide) -> ignoré
            try:
                r = float(brut)
            except ValueError:
                continue
            lignes.append(r)
    return lignes


def stats_side(nom, rs):
    """Statistiques d'une jambe : n, médiane, moyenne, WR, somme R, maxDD R."""
    n = len(rs)
    if n == 0:
        return {"nom": nom, "n": 0, "med": float("nan"), "moy": float("nan"),
                "wr": float("nan"), "somme": 0.0, "dd": float("nan")}
    eq, pic, dd = 0.0, 0.0, 0.0
    for r in rs:
        eq += r
        pic = max(pic, eq)
        dd = max(dd, pic - eq)
    return {
        "nom": nom, "n": n,
        "med": statistics.median(rs),
        "moy": statistics.fmean(rs),
        "wr": 100.0 * sum(1 for r in rs if r > 0) / n,
        "somme": sum(rs), "dd": dd,
    }


def welch_t(a, b):
    """t de Welch (descriptif ; le verdict, lui, repose sur le bootstrap)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan"), float("nan")
    va = statistics.variance(a)
    vb = statistics.variance(b)
    den = math.sqrt(va / na + vb / nb)
    if den == 0:
        return float("nan"), float("nan")
    t = (statistics.fmean(b) - statistics.fmean(a)) / den
    num = (va / na + vb / nb) ** 2
    ddl = num / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return t, ddl


def bootstrap_p(a, b):
    """P(médiane_B > médiane_A) par bootstrap déterministe (seed figée)."""
    rng = random.Random(SEED_BOOTSTRAP)
    la, lb = len(a), len(b)
    gagne = 0
    for _ in range(N_BOOTSTRAP):
        ma = statistics.median(a[rng.randrange(la)] for _ in range(la))
        mb = statistics.median(b[rng.randrange(lb)] for _ in range(lb))
        if mb > ma:
            gagne += 1
    return gagne / N_BOOTSTRAP


def main():
    ap = argparse.ArgumentParser(description="Verdict A/B pré-enregistré x501")
    ap.add_argument("controle", help="CSV kScript du bras A (contrôle)")
    ap.add_argument("traitement", help="CSV kScript du bras B (traitement)")
    ap.add_argument("--label", default="A/B", help="nom du test (ex. RI-BTC)")
    ap.add_argument("--n-min", type=int, default=20,
                    help="N_MIN pré-enregistré (20 pour RI, 12 pour absorption)")
    ap.add_argument("--demo", action="store_true",
                    help="étiquette DEMO (plomberie, pas un verdict)")
    args = ap.parse_args()

    ra = lire_csv(args.controle)
    rb = lire_csv(args.traitement)
    sa = stats_side("A contrôle", ra)
    sb = stats_side("B traitement", rb)

    etiquette = args.label + (" [DEMO — plomberie, pas un verdict]" if args.demo else "")
    print("=" * 74)
    print(f"VERDICT A/B x501 — {etiquette}")
    print(f"A = {args.controle}")
    print(f"B = {args.traitement}")
    print(f"Seuils pré-enregistrés le {DATE_PRE_ENREGISTREMENT} (docs/28), N_MIN={args.n_min}")
    print("=" * 74)

    if sa["n"] == 0 or sb["n"] == 0:
        print(f"VERDICT : INCONCLU (jambe vide : n_A={sa['n']}, n_B={sb['n']})")
        return

    p_boot = bootstrap_p(ra, rb)
    t, ddl = welch_t(ra, rb)
    delta_med = sb["med"] - sa["med"]

    print(f"{'métrique':<24}{'A (contrôle)':>18}{'B (traitement)':>18}")
    print("-" * 60)
    print(f"{'n trades clôturés':<24}{sa['n']:>18}{sb['n']:>18}")
    print(f"{'médiane (R)':<24}{sa['med']:>18.3f}{sb['med']:>18.3f}")
    print(f"{'moyenne (R)':<24}{sa['moy']:>18.3f}{sb['moy']:>18.3f}")
    print(f"{'win rate (%)':<24}{sa['wr']:>18.1f}{sb['wr']:>18.1f}")
    print(f"{'somme R':<24}{sa['somme']:>18.2f}{sb['somme']:>18.2f}")
    print(f"{'maxDD (R)':<24}{sa['dd']:>18.2f}{sb['dd']:>18.2f}")
    print("-" * 60)
    print(f"delta médiane (B - A) : {delta_med:+.3f} R")
    print(f"bootstrap P(méd_B > méd_A) : {p_boot:.4f}  ({N_BOOTSTRAP} rééchantillonnages, seed {SEED_BOOTSTRAP})")
    print(f"Welch t (descriptif) : {t:.3f} sur ~{ddl:.1f} ddl")

    # ----- application des critères pré-enregistrés (ordre impératif) --------
    if sa["n"] > 0 and sb["n"] >= math.ceil(FILTRE_TRANSPARENT * sa["n"]):
        verdict = "DATA_ABSENTE"
        motif = (f"n_B ({sb['n']}) >= 97 % de n_A ({sa['n']}) : le filtre n'a "
                 f"rien filtré (fail-open pré-enregistré — data premium absente "
                 f"ou composantes < 3/5) ; vérifier l'observe avant de conclure.")
    elif delta_med >= DELTA_R_MIN and p_boot >= P_PROMOTION and \
            sb["dd"] <= sa["dd"] + DD_TOLERANCE_R and sb["n"] >= args.n_min:
        verdict = "PROMOTION"
        motif = (f"delta médiane {delta_med:+.3f} R >= {DELTA_R_MIN:.2f}, "
                 f"P = {p_boot:.4f} >= {P_PROMOTION:.2f}, "
                 f"maxDD {sb['dd']:.2f} R <= {sa['dd']:.2f} + {DD_TOLERANCE_R:.1f} R, "
                 f"n_B = {sb['n']} >= N_MIN = {args.n_min}")
    elif p_boot <= P_KILL and sb["n"] >= N_KILL_MIN:
        verdict = "KILL"
        motif = (f"P = {p_boot:.4f} <= {P_KILL:.2f} avec n_B = {sb['n']} >= "
                 f"{N_KILL_MIN} : le traitement est un anti-signal ou un bruit "
                 f"coûteux — entrée NUL au registre docs/20 avec ces chiffres.")
    else:
        verdict = "INCONCLU"
        motifs = []
        if sb["n"] < args.n_min:
            motifs.append(f"n_B = {sb['n']} < N_MIN = {args.n_min} (élargir la fenêtre, "
                          f"JAMAIS de promotion en dessous)")
        if p_boot < P_PROMOTION:
            motifs.append(f"P = {p_boot:.4f} < {P_PROMOTION:.2f}")
        if delta_med < DELTA_R_MIN:
            motifs.append(f"delta médiane {delta_med:+.3f} R < {DELTA_R_MIN:.2f}")
        motif = " ; ".join(motifs) if motifs else "critères non remplis"

    print("=" * 74)
    print(f"VERDICT : {verdict}")
    print(f"motif   : {motif}")
    print(f"Prochaine étape (docs/28) : {PROMOTES.get(verdict, '?')}")
    print("=" * 74)


PROMOTES = {
    "PROMOTION": "entrée CANDIDAT au registre docs/20 + câblage au paper forward",
    "KILL": "entrée NUL au registre docs/20 avec les chiffres, le script reste archivé",
    "INCONCLU": "rester en observation — élargir la fenêtre, le forward juge",
    "DATA_ABSENTE": "réparer la data (observe x501_observe_regime.ks) puis re-run",
}


if __name__ == "__main__":
    main()
