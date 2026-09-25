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

## Priorité 1 — RÉSOUDRE L'ANOMALIE DES 20 % (bloquant, cette semaine)

Deux runs « identiques » du wallet gated divergent de 20 % ($1 266 vs
$1 598). Il y a un bug non trouvé dans le cœur. **Tant que ce n'est pas
résolu, tous les chiffres sont suspects.**

- [ ] Logger le hash de chaque événement (sym + ts + entry + exit + MAE)
      dans `portfolio_sim` et `anti_liq`
- [ ] Diff exact des deux runs → isoler la cause (unité ? ordre ? données ?)
- [ ] Fix + re-mesure de TOUTE la frontière (règle des absolus)
- **Critère d'acceptation** : deux runs consécutifs identiques au centime

## Priorité 2 — LE FORWARD DE LA MACHINE (cette semaine)

La machine 3 flux n'est jugée nulle part sur le vivant.

- [ ] Ajouter les 3 flux de `the_machine.py` au paper forward
      (cascade_majors_10x, cascade_meme, survivor_long — trades paper
      avec leur sizing réel)
- [ ] Le rapport nocturne : la table mensuelle FORWARD du portefeuille
      (pas seulement les candidats unitaires)
- **Critère d'acceptation** : chaque flux a ses trades forward enregistrés
  chaque nuit ; la table mensuelle forward se met à jour 2×/jour

## Priorité 3 — LE CONDITIONNEUR DE QUEUE (quand N ≥ 10, ~1-2 semaines)

Les 8 liqs de l'ancienne frontière clusterent en 3 épisodes de marché.
La sonde de mécanisme mesure les tempêtes.

- [ ] Quand `mechanism_probe` a N ≥ 10 : le gate « tempête d'acteurs en
      cours » (notional longs liquidés 6h > seuil → pas de short)
- [ ] Test : combien de liqs historiques le gate aurait évitées, combien
      de gagnants perdus
- **Critère d'acceptation** : le gate élimine ≥ 50 % des liqs à ≤ 10 %
      des gagnants — sinon il reste une sonde descriptive

## Priorité 4 — LES GISEMENTS DATÉS (le calendrier)

| Date | Gisement | Livrable |
|---|---|---|
| ~6/10 | depth.db maker (J+14) | Le fill-rate réel du maker sur nos entrées |
| ~8/10 | whale_flow × prix (J+14) | La corrélation flux d'hier × prix du jour |
| ~10/10 | liq_events (2 semaines+) | La sonde de mécanisme lisible + le backtest des tempêtes |
| continu | funding profond | Le forward du candidat qualité (81 % WR, ~2 trades/mois) |

## Priorité 5 — LES NOUVEAUX FLUX DE FRÉQUENCE (la régularité)

La loi établie : la régularité mensuelle = le N de paris indépendants.
Chaque flux décorrelé même faible (+5-10 %/an) lisse la courbe.

- [ ] Tester 2-3 flux de fréquence supplémentaires (15m contagion fine,
      structure de volume, transitions de carte croisées funding)
- [ ] Les flux retenus entrent à 1x avec sizing vol-inverse

## La règle de gouvernance (ne pas déroger)

1. Toute mesure passe par le wallet séquentiel + contrôle inverse.
2. Les ABSOLUS sont re-mesurés après chaque fix.
3. Le paper forward tranche — un backtest n'est jamais une preuve.
4. 0 liquidation = contrainte dure, pas une cible.
5. Un indicateur n'existe pas tant qu'il ne tourne pas chaque nuit.
