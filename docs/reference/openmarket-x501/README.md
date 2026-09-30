# openmarket-x501/ — LA BIBLIOTHÈQUE DE RÉFÉRENCE

Les livrables formatés du domaine x501 (9 PDF + 2 protocoles), un seul
endroit, ordre de lecture conseillé. Le doc maître : `docs/25-openmarket-x501.md`.

## Le plan et sa validation

| Livrable | Ce que c'est |
|---|---|
| `Operation_x501_Plan_Trading_OpenMarket.pdf` | LE plan : mission 100 $ → 50 100 $, contraintes DD ≤ 25 %, régimes V1–V5 |
| `Operation_x501_Rapport_Validation_Backtest.pdf` | la validation du signal de base (S3) avant toute simulation |
| `Operation_x501_Simulation_MonteCarlo.pdf` | la MC v18 (12 000 trajectoires, bandes de coûts, P(250 $) par régime) |
| `Operation_x501_Moteur_V5_Mesure_MonteCarlo.pdf` | la mesure du moteur V5 et ses hypothèses de coût |
| `Operation_x501_Perps_Stress_Lab.pdf` | le stress lab perps (la bande pessimiste V5 : 215,7 $) |

## Le programme et son exécution

| Livrable | Ce que c'est |
|---|---|
| `Operation_x501_Programme_12_Mois_MultiAlpha.pdf` | le programme 12 mois multi-alpha (V1 → V3, les dates de passage) |
| `Operation_x501_Campagne_v9_Flux.pdf` | la campagne v9 — le flux (les signaux, leurs fenêtres) |
| `Operation_x501_Campagne_v12_Gestion.pdf` | la campagne v12 — la gestion (sizing, stops, DD) |
| `Operation_x501_Maitrise_Plateforme.pdf` | la maîtrise openmarket.xyz (kScript, inputs, persist) |
| `Operation_x501_Addendum_kScript.pdf` | l'addendum kScript (les règles syntaxiques vérifiées par les QA) |

## Les protocoles (md, vivants)

| Livrable | Ce que c'est |
|---|---|
| `PROTOCOLE_COLLECTE_v10.md` | ce qu'on collecte, à quel rythme, et pourquoi (v10) |
| `PROTOCOLE_PREUVE_LIVE_v11.md` | **la preuve live 90 j** : relevés 4×/jour, équité, fills, DD, dérive vs sim (v11) |

Les PDF sont figés par date de production (les chiffres qu'ils portent sont
les leurs) ; la vérité à jour reste les docs 25/26 et la baseline `reports/`.
