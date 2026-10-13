# STATE — l'état de la recherche (≤ 3 Ko) · à lire EN PREMIER

Budget 3000 o, `audit_check.py` (C4) — garder COURT. LEDGER : `lab_ledger.py sync-state` ;
Productivité : `research_velocity.py --state`. Tout chiffre = sa commande de reproduction.

## Ledger & budget
<!-- LEDGER:BEGIN (généré par lab_ledger.py sync-state — ne pas éditer à la main) -->
- Ledger : **98** entrées (1 essais, dont 12 backfill hors budget, 81 superseded hors preuve) — FAIL 1 · superseded : PR-143
- Budget semaine 2026-W42 (effet policy : 2026-10-02) : **0/20** consommés (hors re-vérifications exemptées), reste 20
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
- Pool v8 : edge NON établi — HOLDOUT-X **FAIL** 11/10 (n=950, E[R] +0,064, IC95 [−0,038 ; +0,179], 3/6 fenêtres, champion +0,073). **GELÉ** : aucun cycle sans mécanisme nouveau pré-enregistré. Repro : `holdout_x_harness.py`
- premium-fade directionnel : CLOS (naked −9,6 bps ; « 87 % WR » = coûts 0 bps).
- premium-fade-listing : KILL ex ante 04/10 (22,2 % de 80 770 trades toxiques > 15 %) — CONTEXTE (docs/20).
- vol_spike_meme au spread réel : PASS 04/10 (+0,0161 $/trade, 0 liq ; TAKER_RT 28 bps).
- corr_months corrigé 05/10 : les verdicts de décorrélation tiennent (−0,055 / −0,650).
- Aster 13 mois : FORWARD-ONLY (« +24 %/26 j » = aucune info DD → verdict 90 j).

## En attente (pré-enregistré)
Murs+depth 06-07/10 · OI quadrant 07-08/10 · whaleflow+P3 08/10 · INV-N ~28/10 · H-CROWD-1 30/10 ·
INV-C ~mi-nov. Balayage hebdo = règle permanente (Ariad 04/10) ; le prize maker (12-24 bps meme)
attend l'extension du collecteur tape. **Kill rule ARMÉE (DECISIONS.md D-2)** : holdout-x FAIL ;
si liq-echo+depth-imbalance+long-flush-bounce échouent → GEL directionnel 1h (effort → maker
D-1 + portage). Pilote maker 7 j : verdict ~19/10.

## Règles (modèle local Bonsai : docs/39 §4)
AVANT : `lab_ledger.py check …` (3 = doublon, 4 = STOP → file B) · APRÈS : `log …` puis `sync-state`.
Bonsai : affirmations CITÉES vérifiées par `bonsai_verify.py verify` ; jamais un chiffre, jamais un verdict.
Aucun ordre autonome · protocole, coûts, symboles intouchables en session.
