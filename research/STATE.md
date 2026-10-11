# STATE — l'état de la recherche (≤ 3 Ko) · à lire EN PREMIER

Budget 3000 o contrôlé par `audit_check.py` (C4) — garder ce fichier COURT.
Généré : LEDGER par `lab_ledger.py sync-state`, Productivité par
`research_velocity.py --state`. Tout chiffre = sa commande de reproduction.

## Ledger & budget
<!-- LEDGER:BEGIN (généré par lab_ledger.py sync-state — ne pas éditer à la main) -->
- Ledger : **98** entrées (1 essais, dont 12 backfill hors budget, 81 superseded hors preuve) — FAIL 1 · superseded : PR-143
- Budget semaine 2026-W41 (effet policy : 2026-10-02) : **1/20** consommés (hors re-vérifications exemptées), reste 19
- Familles bloquantes hors reverify : aucune
- Familles raw historiques (re-verifies incluses) : aucune
- Seuil de preuve du prochain essai : |t| ≥ 3.80 (Bonferroni, N=343 dont 341 pré-ledger)
<!-- LEDGER:END -->

## Productivité (généré : `python scripts/research_velocity.py`)
- Semaine **2026-W41** : **17** lots · **17** tranchées · **0** candidats.
- Historique : 2026-W41 : 17·17·0 {'DISCOVERY_FAIL': 16, 'FAIL': 1}
- « Fini » hebdo = ≥ 1 lot journalisé ET ≥ 1 hypothèse tranchée.
- **Échéances dépassées : 8** sans verdict vivant (+2 non joignables) : `cusum-regime-shift`, `depth-imbalance`, `liq-echo` (+5) — détail : `python scripts/research_velocity.py`.
- Part recherche (7 j) : **41/211** (19 %) — objectif ≥ 50 % (R3-5).

## Verdicts qui comptent
- Pool OpenMarket v8 : edge NON établi — HOLDOUT-X **FAIL** 11/10 (48 symboles jamais vus, n=950, E[R] +0,064, IC95 [−0,038 ; +0,179], 3/6 fenêtres, champion apparié +0,073). Repro : `holdout_x_harness.py`
- premium-fade directionnel : CLOS (naked −9,6 bps ; le « 87 % WR » = backtest à coûts 0 bps).
- premium-fade-listing : KILL ex ante 04/10 (22,2 % de 80 770 trades toxiques > seuil 15 %) — mécanisme CONTEXTE (docs/20).
- vol_spike_meme re-costé au spread réel : PASS 04/10 (+0,0161 $/trade, 0 liq) — coût machine = TAKER_RT 28 bps.
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
