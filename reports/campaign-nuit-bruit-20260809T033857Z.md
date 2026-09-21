# Rapport de campagne

## [CRITIQUE] Sante de la campagne

```text
[CRITICAL] TAUX D'ACCEPTATION SUSPECT : compatible avec du bruit pur — 1231 acceptees / 10000 (12,3 %) alors qu'un tirage aleatoire a alpha=5 % en produirait deja 500 / 10000 (5,0 %).
[INFO] AUCUN SURVIVANT APRES CORRECTION DE MULTIPLICITE : 1231 lanes passaient les gates / 10000 (12,3 %), 0 / 1231 survit a la correction. C'est le comportement attendu : les gates filtrent une lane, la multiplicite juge la campagne. Aucune perte d'argent possible ici.
[INFO] Verdict d'audit : AUCUN SURVIVANT APRES CORRECTION
```

## [ALERTE] Correction de multiplicite

```text
essais audites          : 10000 essais / 10000 (100,0 %)
passent les gates       : 1231 / 10000 (12,3 %)
survivent a la corr.    : 0 / 10000 (0,0 %)
attendus par hasard     : 500 / 10000 (5,0 %)
verdict                 : AUCUN SURVIVANT APRES CORRECTION
seuil_bonferroni        : 5.000e-06
lecture                 : sans correction, 500.0 faux positifs sont attendus sur 10000 essais au seuil 0.05
rappel                  : un survivant n'est pas une strategie validee : c'est un candidat, a reevaluer sur des donnees posterieures a la campagne
```

## [INFO] Campagne

```text
run_id      : nuit-bruit
debut       : 2026-08-09T02:00:00
fin         : 2026-08-09T04:12:00
duree       : 132,0 min
testees     : 10000 combinaisons / 10000 (100,0 %)
```

## [INFO] Comptage

```text
acceptees   : 1231 / 10000 (12,3 %)
rejetees    : 8769 / 10000 (87,7 %)
erreurs     : 0 / 10000 (0,0 %)
```

## [INFO] Survivants

```text
Un survivant est un CANDIDAT, pas une strategie validee : il doit etre reevalue sur des donnees posterieures a la campagne.

affiches : 10 survivants / 1231 (0,8 %)
survivants : 1231 / 10000 (12,3 %)

 1. BTCUSDT|1h|both|ma_0|taker_market|3 | sharpe_oos=3,10 | oos/is=1,20 | trades=400
 2. BTCUSDT|1h|both|ma_1|taker_market|3 | sharpe_oos=3,08 | oos/is=1,20 | trades=400
 3. BTCUSDT|1h|both|ma_2|taker_market|3 | sharpe_oos=3,06 | oos/is=1,20 | trades=400
 4. BTCUSDT|1h|both|ma_3|taker_market|3 | sharpe_oos=3,04 | oos/is=1,20 | trades=400
 5. BTCUSDT|1h|both|ma_4|taker_market|3 | sharpe_oos=3,02 | oos/is=1,20 | trades=400
 6. BTCUSDT|1h|both|ma_5|taker_market|3 | sharpe_oos=3,00 | oos/is=1,20 | trades=400
 7. BTCUSDT|1h|both|ma_6|taker_market|3 | sharpe_oos=2,98 | oos/is=1,20 | trades=400
 8. BTCUSDT|1h|both|ma_7|taker_market|3 | sharpe_oos=2,96 | oos/is=1,20 | trades=400
 9. BTCUSDT|1h|both|ma_8|taker_market|3 | sharpe_oos=2,94 | oos/is=1,20 | trades=400
10. BTCUSDT|1h|both|ma_9|taker_market|3 | sharpe_oos=2,92 | oos/is=1,20 | trades=400
... 1221 non affiches / 1231 (99,2 %)
```

## [INFO] Motifs de rejet

```text
Un rejet peut cumuler plusieurs motifs : le total ci-dessous peut depasser le nombre de combinaisons rejetees.

sample_too_small                   5000 / 10000 (50,0 %)
overfit_oos_is_ratio               3769 / 10000 (37,7 %)

total motifs : 8769 occurrences / 10000 (87,7 %)
```
