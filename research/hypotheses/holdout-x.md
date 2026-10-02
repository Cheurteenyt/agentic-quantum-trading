# HOLDOUT-X — les symboles jamais vus du pool v8
domaine : openmarket · famille : cross-sectionnel · stratégie : pool_v8_rules_frozen
Mécanisme : les règles v8 (4 alphas, coûts, TP maker) appliquées TELLES QUELLES à ≥ 40 symboles JAMAIS utilisés dans le pool. Le seul holdout propre restant pour valider que l'edge v8 n'est pas du sur-apprentissage de symbole.
Prédiction : E[R] > 0 en borne basse IC95 blocs-mois, n ≥ 400
Données : base deep 7 ans, mêmes coûts que le pool v8, même protocole
PASS si E[R] > 0 ET borne basse IC95 > 0 ET n ≥ 400 · FAIL si borne haute < +0,05 R
Contrôles : les 40 symboles originaux en référence (le champion)
Hash du gel : <à committer avant le run> · Jugé sous : protocol_v2
