# STATE — l'état de la recherche (≤ 2 Ko) · à lire EN PREMIER

MAJ manuelle : 2026-10-05. Le bloc ci-dessous est GÉNÉRÉ : `python3 scripts/lab_ledger.py sync-state`
(audit_check F5 échoue s'il est périmé). Tout chiffre ici doit avoir sa commande de reproduction.

## Ledger & budget
<!-- LEDGER:BEGIN (généré par lab_ledger.py sync-state — ne pas éditer à la main) -->
- Ledger : **44** entrées (44 essais, dont 12 backfill hors budget) — PASS 6 · FAIL 28 · NUL 1 · SOUS_PUISSANT 3
- Budget semaine 2026-W41 (effet policy : 2026-10-02) : **4/20** consommés, reste 16
- Familles au plafond : aucune
- Seuil de preuve du prochain essai : |t| ≥ 3.26 (Bonferroni, N=45)
<!-- LEDGER:END -->

## Verdicts qui comptent
- Pool OpenMarket v8 : E[R] +0,093 R, IC95 [−0,027 ; +0,223] ; rien ne survit à Bonferroni (N=362) → edge NON établi.
  Repro : `python3 scripts/studies/x501_openmarket/x501_multiplicity_adapter.py`
- premium-fade directionnel : CLOS (naked −9,6 bps ; le « 87 % WR » = backtest à coûts 0 bps, non reproductible).
- premium-fade-listing : KILL ex ante 04/10 (22,2 % de 80 770 trades toxiques > seuil 15 %) — mécanisme gravé CONTEXTE (docs/20).
- vol_spike_meme re-costé au spread réel : PASS 04/10 (+0,0161 $/trade, 0 liq) — le coût machine = TAKER_RT 28 bps.
- corr_months zero-fill corrigé 05/10 — re-mesure : les verdicts de décorrélation tiennent (−0,055 / −0,650).
- « +24 %/26 j » survivants : 26 j = aucune info DD → verdict forward 90 j. Aster 13 mois : FORWARD-ONLY.
- File bugs : reports/aster/bug-hunt-0510/SYNTHESE.md (10 mineurs + 3 suspects).

## En attente (pré-enregistré)
Murs + depth 06-07/10 · OI quadrant H4/H5 07-08/10 · whaleflow + P3 08/10 · INV-N ~28/10 · H-CROWD-1 30/10
(double scellé) · INV-C ~mi-nov. Balayage hebdo = règle permanente (carte Ariad 04/10) ; le prize maker
(12-24 bps meme) attend l'extension du collecteur tape (décision user).

## Règles (modèle local Bonsai : docs/39 §4)
AVANT : `lab_ledger.py check …` (3 = doublon, 4 = STOP → file B) · APRÈS : `log …` puis `sync-state`.
Bonsai : affirmations CITÉES vérifiées par `bonsai_verify.py verify` ; jamais un chiffre, jamais un verdict.
Aucun ordre autonome · protocole, coûts, symboles intouchables en session.
