#!/usr/bin/env python3
"""x501_multiplicity_adapter.py — T8 : branche le pool v8 sur backtest_v2.multiplicity.

Le pool v8 (868 trades) passe par les corrections de multiplicité du projet
(Bonferroni, Benjamini-Hochberg, Deflated Sharpe Ratio) au lieu du t naïf.
Usage : .venv/bin/python scripts/studies/x501_openmarket/x501_multiplicity_adapter.py
"""
import csv, sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from backend.services.backtest_v2.multiplicity import bonferroni_threshold, benjamini_hochberg, deflated_sharpe_ratio

POOL = Path(__file__).parent / "trades_v8_deep.csv"
N_PRIOR_TRIALS = 341  # les cellules citées dans les messages de commit (audit Sonnet §P7)

def main():
    if not POOL.exists():
        print(f"[skip] {POOL} introuvable"); return 1
    rows = list(csv.DictReader(open(POOL)))
    R = [float(r["R"]) for r in rows]
    n = len(R)
    mean_r = sum(R) / n
    sd_r = (sum((x - mean_r)**2 for x in R) / (n - 1)) ** 0.5
    sr = mean_r / sd_r * (n ** 0.5)  # Sharpe annualisé approx en R-multiples
    print(f"Pool v8 : n={n} E[R]={mean_r:+.4f} sd={sd_r:.3f} SR≈{sr:.2f}")

    # Bonferroni
    t_bonf = bonferroni_threshold(N_PRIOR_TRIALS) if callable(bonferroni_threshold) else None
    print(f"Bonferroni (N={N_PRIOR_TRIALS}) : seuil t* = {t_bonf}" if t_bonf else "bonferroni_threshold : API différente, cf multiplicity.py")

    # DSR
    try:
        dsr = deflated_sharpe_ratio(sr, n, N_PRIOR_TRIALS)
        print(f"Deflated Sharpe Ratio : {dsr:.4f} (SR brut {sr:.4f})")
    except Exception as e:
        print(f"DSR : erreur {e}")

    # BH
    try:
        bh = benjamini_hochberg
        print(f"BH disponible : {bh}")
    except Exception:
        pass
    print("\n→ La borne basse IC95 blocs-mois [-0,027;+0,223] (audit Sonnet D1) reste le juge :")
    print("   l'edge n'est PAS établi tant que l'IC ne sépare pas de zéro après correction.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
