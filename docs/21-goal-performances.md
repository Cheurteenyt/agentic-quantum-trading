# 21 — GOAL : la machine validée sur le vivant

> Objectif de la phase : transformer la frontière backtestée en **stratégie
> forward-validée, rentable chaque mois, faible DD, gros ROI, 0 liquidation**.
> Horizon : 4 semaines. Créé le 25/09/2026.

## La cible chiffrée (la spec du user)

| Métrique | Cible |
|---|---|
| Mois négatifs | **0-1 sur 12** (actuellement 2-3/13) |
| Record mensuel | ≥ 80 % (atteint : +88,5 % dans le backtest) |
| Max DD | ≤ 25 % |
| Liquidations | **0, sans exception** |
| ROI annuel | ≥ 1 000 % backtesté, confirmé forward |

## L'état de la machine au 27/09 (les 3 configs au forward)

| Config | Poids [majors, meme, survivor, vol_spike] | Levier | FULL (100 $) | Annalisé | DD max | Record | Pire mois | Liq | Statut |
|---|---|---|---|---|---|---|---|---|---|
| **main** (référence) | historiques | 10x/1x/1x/1x | $4 005 | +3 905 %/an | 24,8 % | — | -10,1 % | 0 | au forward |
| **QUBO poids** (`qubo_sizing.py`) | [0.857, 0.857, 2.0, 1.143] | 10x/1x/1x/1x | $4 639 | +4 539 %/an | 23,4 % | +78,7 % | -14,4 % | 0 | CANDIDAT |
| **QUBO joint poids×levier** (`qubo_joint_lev.py`) | [0.857, 0.857, 2.0, 0.857] | **11x**/1x/1x/1x | **$5 182** | **+5 082 %/an** | **23,3 %** | **+83,7 %** | -13,4 % | 0 | CANDIDAT — ⚠️ marge MAE 9 % |

27/09 : 19+ verdicts consommés (16 nuls/contextes, 3 candidats) ; 2 bugs
CRITIQUES de la chaîne forward patchés (audit `flow_audit.py`, Ariad) ; les
holds 24h/72h/6h = des optimums mesurés (design evidence-locked,
`funding_hold_surv_map.py`) ; les 3 configs avancent côte à côte sur les
MÊMES trades paper (`qubo_forward_tracker.py`).

## Le volet institutionnel (état au 28/09) — 5 couches, toutes datées de tir

La couche institutionnelle fine est en place : **5 couches** (murs, prints,
OI H4/H5, sonde liq, whale_flow), chacune avec sa date de tir — plus la
boucle réplication derek518 câblée au forward.

| Couche | Outil | Tir |
|---|---|---|
| les murs du carnet | `wall_detector.py` (PROTOTYPE 4,3 j non-mature) | **re-tir 06-07/10** |
| les gros prints | `aster_blocktrades.py` (timer 15 min câblé) — le fade = **détecteur d'absorption**, pas de continuation | le cross prints × OI squeeze dans **2 semaines** |
| OI × prix (H4/H5) | `oi_quadrant_test.py` | **06-07/10** |
| sonde liq | `liq_storm.py` | ~**10/10** |
| whale_flow × prix | `whaleflow_join_test.py` | **08/10** |

Et la **boucle réplication derek518** : swaps-forward v2 PASS → wallet test
CANDIDAT (+88 %/26 j @ DD 6,4 %, robuste sans le top-3) → la règle
`replication_derek` câblée dans `fomo_paper_forward.py` — **le verdict
forward à ≥ 5 CLOSED**.

## Priorité 1 — ✅ RÉSOLUE (25/09) : l'anomalie des 20 % n'était pas un bug

Deux runs « identiques » du wallet gated divergeaient de 20 % ($1 266 vs
$1 598). Le diff événement par événement (hash md5) : **les 164 trades
sont les mêmes, mais les événements à al_score NaN** (les ~2 premiers
mois, avant que la fenêtre roulante de 90j ne se remplisse) **sont
taillés par ATR dans le run A et à plat 24 % dans le run B** — et ces
trades d'octobre-novembre étant les gros gagnants, le compounding de
toute l'année divergeait (d'où 0 hash identique : chaque PnL diffère).

- [x] Diff exact des deux runs → cause isolée (NaN-score early trades)
- [x] Le comportement correct confirmé : tailles par ATR (ce que
      `the_machine.py` fait — pas de re-check du score après le gate)
- **Critère d'acceptation** : ✓ même fn = déterministe au centime

**Verdict : aucun bug moteur. Les chiffres officiels tiennent
(+1 498 %/an base 24 %, +2 829 % la machine 3 flux).**

## Priorité 2 — ✅ ARMÉE (27/09) : le forward des 3 configs + la marge MAE 9 %

La machine est jugée sur le vivant en **3 configs parallèles sur les MÊMES
trades paper** (`qubo_forward_tracker.py`, ledger 2×/jour) — main, QUBO
poids, QUBO joint poids×levier (voir la table d'état ci-dessus).

- [x] Les 3 configs au paper forward avec leur sizing réel
- [x] Le rapport nocturne : la table mensuelle FORWARD du portefeuille
- ⚠️ **Marge MAE majors sous surveillance permanente** : VAL 7,84 % vs
  seuil 8,59 % à 11x = **9 % de tête seulement** — contrôle à chaque
  nocturne ; retour mécanique à 10x si la marge se resserre.
- **Critère d'acceptation** : chaque config a ses trades forward enregistrés
  chaque nuit ; le paper forward tranche la promotion (2-4 semaines).

## Priorité 3 — ✅ ARMÉE (27/09) : la sonde de mécanisme câblée

`mechanism_probe.py` patché (l'audit Ariad) — les champs **fund7 / vol7 /
liq24h** sont loggés à chaque signal (l'hypothèse fund7 ≥ p75 sort de
l'autopsie des mois négatifs, n=1 indicatif).

- [x] Sonde câblée au nocturne, les champs loggés
- [ ] Tir 08/10 : `whaleflow_join_test.py` + le gate « tempête d'acteurs
      en cours » quand N ≥ 10
- **Critère d'acceptation** : inchangé — le gate élimine ≥ 50 % des liqs
      à ≤ 10 % des gagnants, sinon il reste une sonde descriptive

## Priorité 4 — ✅ ARMÉE (27/09) : les tirs d'octobre pré-enregistrés

| Date | Gisement | Livrable | Outil |
|---|---|---|---|
| **06-07/10** | quadrant OI × prix (H4/H5 pré-enregistrées AVANT tout calcul) | le verdict du quadrant | `oi_quadrant_test.py` |
| **08/10** | whale_flow × prix (J+14) | la corrélation flux d'hier × prix du jour | `whaleflow_join_test.py` |
| ~10/10 | liq_events (2 semaines+) | la sonde de mécanisme lisible + le backtest des tempêtes | `liq_storm.py` |
| prototype **prêt** | depth.db maker — géométrie 0-liq sur l'imbalance | le fill-rate réel du maker sur nos entrées | `depth_indicator_prototype.py` |
| continu | funding profond | le forward du candidat qualité (81 % WR, ~2 trades/mois) | `paper_forward.py` |

Entre-temps (27/09) : la famille exit est CLOSE — le hold 24h (cascades),
72h (survivor) et 6h (vol_spike) sont des optimums mesurés
(`funding_hold_surv_map.py`, design evidence-locked).

## Priorité 5 — ✅ RÉSOLUE (27/09) : vol_spike_6h = le 4e flux

La loi tenait : la régularité = le N de paris indépendants. **vol_spike_6h**
(fade du range ≥ 4× médiane 14j, gate ATR, hold 6h) passe tous les critères
(`p5_frequency_test.py`) : N 820/an, WR 53,7 %, 0 liq, corr cascade -0,22,
remplit les mois creux. **Câblé 4e flux** au nocturne (sizing vol-inverse).

`volspike_meme_test.py` : majors ~1 % du flux global → vol_spike_6h EST un
flux memecoin natif — pas de créneau stack séparé, précision d'universe
pour le forward et les poids QUBO.

Les autres portes : dd_cross 24h/72h NUL · vol_spike_12h NUL · funding_sat
CONTEXTE (thin, maker-only) · TAIL survivor CONTEXTE (échoue au critère
wallet au sizing machine, `tail_machine_confirm.py`).

## La règle de gouvernance (ne pas déroger)

1. Toute mesure passe par le wallet séquentiel + contrôle inverse.
2. Les ABSOLUS sont re-mesurés après chaque fix.
3. Le paper forward tranche — un backtest n'est jamais une preuve.
4. 0 liquidation = contrainte dure, pas une cible.
5. Un indicateur n'existe pas tant qu'il ne tourne pas chaque nuit.
