# CUSUM-REGIME — le détecteur de sauts discrets
domaine : aster · famille : regime · stratégie : cusum_shift_detector
Mécanisme : les changements de régime sont des SAUTS discrets, pas des transitions lisses. Le CUSUM (cumulative sum des déviations de la moyenne de référence) détecte les sauts que les z-scores et les HMM ratent parce qu'il accumule l'évidence au lieu de mesurer l'état instantané.
Prédiction : les heures post-saut CUSUM ont une distribution de retours DIFFÉRENTE des heures pré-saut — et la différence est exploitable (le drift post-saut est systématique).
Données : klines 1h, les 6 majeures, ~9,5 mois. Le CUSUM est calculé sur les retours 1h avec la moyenne de référence figée au début de chaque période.
Coûts : 18 bps RT. 1x. Split 70/30 chrono.
PASS si : le drift post-saut est systématique (même signe en train et val) ET la différence pré/post est > 2× l'erreur-type ET le contrôle inverse (pré-saut devrait être plat) est battu.
FAIL si : le drift post-saut n'est pas systématique OU la différence n'est pas significative.
SOUS_PUISSANT si n_sauts < 20 en train.
Contrôles : inverse (le drift devrait être nul si le CUSUM ne capte rien) · le base-rate par direction du saut.
Hash du gel : <commit> · Jugé sous : protocol_v1 · Le seuil CUSUM = 3× σ des retours de référence (pré-déclaré, pas tuné).
