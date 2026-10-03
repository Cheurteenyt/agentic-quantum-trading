# STATE — l'état de la recherche (≤ 2 Ko) · à lire EN PREMIER

MAJ manuelle : 2026-10-03 · HEAD 42b6728. Le bloc ci-dessous est GÉNÉRÉ : `python3 scripts/lab_ledger.py sync-state`
(audit_check F5 échoue s'il est périmé). Tout chiffre ici doit avoir sa commande de reproduction.

## Ledger & budget
<!-- LEDGER:BEGIN (généré par lab_ledger.py sync-state — ne pas éditer à la main) -->
- Ledger : **28** entrées (28 essais, dont 12 backfill hors budget) — PASS 2 · FAIL 22 · NUL 1 · SOUS_PUISSANT 3
- Budget semaine 2026-W40 (effet policy : 2026-10-02) : **16/20** consommés, reste 4
- Familles au plafond : aster-institutions 5/5
- Seuil de preuve du prochain essai : |t| ≥ 3.13 (Bonferroni, N=29)
<!-- LEDGER:END -->

## Verdicts qui comptent
- Pool OpenMarket v8 : E[R] +0,093 R, IC95 blocs-mois [−0,027 ; +0,223] ; aucun test ne survit à Bonferroni
  (N=362, t ≥ 3,64) → edge NON établi. Repro : `python3 scripts/studies/x501_openmarket/x501_multiplicity_adapter.py`
- premium-fade directionnel : CLOS (naked −9,6 bps ; le « 87 % WR » = backtest à coûts 0 bps, non reproductible).
- « +24 %/26 j @ DD 3,4 % » (survivants, docs/20 l.291) : 26 jours = aucune information sur le DD → verdict forward 90 j.
- Aster 13 mois : rétrospectif ≈ 0 essai « payable » → FORWARD-ONLY. Base deep 7 ans : rétrospectif possible sous ledger.
- « Edge détectable ≥ 0,25 R » = illustration sur le pool OpenMarket (26 trades/fenêtre), PAS une mesure Aster.

## En attente (pré-enregistré)
H4/H5 re-tir 07-08/10 · INV-N ~28/10 · H-CROWD-1 30/10 (double scellé : hypothèse + amendements) · INV-C ~mi-nov ·
INV-J (depth) · premium-fade-listing lun 06/10 : d'abord mesurer, SANS rendements, la part de trades que le filtre
|Δindex_15m| ≤ 0,5 % écarte (KILL > 15 % : prévisible sur des listings volatils).

## Règles (modèle local Bonsai : docs/39 §4)
AVANT : `lab_ledger.py check …` (3 = doublon, 4 = STOP → file B) · APRÈS : `lab_ledger.py log …` puis `sync-state`.
Bonsai : appels sans état, ≤ 2-3 k jetons, affirmations CITÉES, vérifiées par `bonsai_verify.py verify` ; jamais un chiffre,
jamais un verdict. Aucun ordre autonome · protocole, coûts, symboles intouchables en session.
