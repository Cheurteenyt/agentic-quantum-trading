# STATE — l'état de la recherche (≤ 2 Ko) · à lire EN PREMIER

MAJ manuelle : 2026-10-05. Le bloc ci-dessous est GÉNÉRÉ : `python3 scripts/lab_ledger.py sync-state`
(audit_check F5 échoue s'il est périmé). Tout chiffre ici doit avoir sa commande de reproduction.

## Ledger & budget
<!-- LEDGER:BEGIN (généré par lab_ledger.py sync-state — ne pas éditer à la main) -->
- Ledger : **30** entrées (30 essais, dont 12 backfill hors budget) — PASS 3 · FAIL 23 · NUL 1 · SOUS_PUISSANT 3
- Budget semaine 2026-W40 (effet policy : 2026-10-02) : **18/20** consommés, reste 2
- Familles au plafond : aster-institutions 5/5
- Seuil de preuve du prochain essai : |t| ≥ 3.15 (Bonferroni, N=31)
<!-- LEDGER:END -->

## Verdicts qui comptent
- Pool OpenMarket v8 : E[R] +0,093 R, IC95 blocs-mois [−0,027 ; +0,223] ; aucun test ne survit à Bonferroni
  (N=362, t ≥ 3,64) → edge NON établi. Repro : `python3 scripts/studies/x501_openmarket/x501_multiplicity_adapter.py`
- premium-fade directionnel : CLOS (naked −9,6 bps ; le « 87 % WR » = backtest à coûts 0 bps, non reproductible).
- premium-fade-listing : **KILL ex ante 04/10** (22,2 % des 80 770 trades toxiques > seuil 15 %, discriminateur Δindex
  concordant FO/exact) — mécanisme directionnel gravé CONTEXTE (inverse −20,61 vs +4,61 bps ; gradient d'âge 9,4/6,0/3,8).
- vol_spike_meme re-costé au spread RÉEL : **PASS 04/10** (esp +0,0138 → +0,0161 $/trade, 0 liq ; TAKER_RT 28 bps couvrait
  la médiane mesurée). Correction de référentiel : le coût machine = 28 bps RT, PAS les 8 du backtest premium-fade.
- corr_months zero-fill CORRIGÉ le 05/10 (corr +1,00 lue +0,42) — re-mesure : vol_spike×majors −0,055, ×meme −0,650 :
  les verdicts de décorrélation tiennent. File des 10 mineurs + 3 suspects : reports/aster/bug-hunt-0510/SYNTHESE.md.
- « +24 %/26 j @ DD 3,4 % » (survivants, docs/20 l.291) : 26 jours = aucune information sur le DD → verdict forward 90 j.
- Aster 13 mois : rétrospectif ≈ 0 essai « payable » → FORWARD-ONLY. Base deep 7 ans : rétrospectif possible sous ledger.
- « Edge détectable ≥ 0,25 R » = illustration sur le pool OpenMarket (26 trades/fenêtre), PAS une mesure Aster.

## En attente (pré-enregistré)
H4/H5 re-tir 07-08/10 · INV-N ~28/10 · H-CROWD-1 30/10 (double scellé : hypothèse + amendements) · INV-C ~mi-nov ·
INV-J (depth) · whaleflow + P3 le 08/10 · le balayage hebdo W41 en vol (harnais 21 cellules × 586 syms, backtest_indicators
réparé de 3 crashs pd.NA). DÉCIDÉ par le user (la dé-limitation, carte Ariad 04/10) : 1 balayage systématique/semaine,
les familles closes rouvertes COMME COUCHES DE SIZING. La question maker : fill 100 %/sélection adverse 1-2 bps mesurés
sur majors — le prize (12-24 bps meme) attend l'extension du collecteur tape (décision user).

## Règles (modèle local Bonsai : docs/39 §4)
AVANT : `lab_ledger.py check …` (3 = doublon, 4 = STOP → file B) · APRÈS : `lab_ledger.py log …` puis `sync-state`.
Bonsai : appels sans état, ≤ 2-3 k jetons, affirmations CITÉES, vérifiées par `bonsai_verify.py verify` ; jamais un chiffre,
jamais un verdict. Aucun ordre autonome · protocole, coûts, symboles intouchables en session.
