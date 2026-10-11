# HOLDOUT-X — les symboles jamais vus du pool v8
domaine : openmarket · famille : cross-sectionnel · stratégie : pool_v8_rules_frozen
Mécanisme : les règles v8 (4 alphas, coûts, TP maker) appliquées TELLES QUELLES à ≥ 40 symboles JAMAIS utilisés dans le pool. Le seul holdout propre restant pour valider que l'edge v8 n'est pas du sur-apprentissage de symbole. C'est la question laissée ouverte par docs/40 : le pool 40 symboles contient déjà les 40 symboles du harnais (A1/A3/A4 y sont mesurés), donc « l'edge tient-il sur des symboles HORS pool » n'a jamais été testé — la contraction v8 (+0,180 → +0,093, docs/40 §4) est compatible avec les deux lectures (edge réel mais mince sur le régime / sur-apprentissage de symbole), et seule cette épreuve les sépare.
Prédiction : E[R] > 0 en borne basse IC95 blocs-mois, n ≥ 400
Données : base deep 7 ans, mêmes coûts que le pool v8, même protocole.
Univers de test : ≥ 40 perps Binance USDT-M JAMAIS présents dans SYMS_40 (x501_collect_deep40_v31.py:28) ni dans le pool v8 officiel — liste FIGÉE avant collecte (on ne choisit pas l'univers après avoir vu les résultats).
Univers de référence (contrôle, pas le sujet) : les 40 symboles originaux du pool v8.
Source : CDN Binance Vision (zips mensuels + quotidiens, sans rate-limit) ; klines 1h depuis le listing de chaque actif, volume taker natif ; funding 8 h en SECONDES (piège d'unité v29).
Moteur : x501_engine_deep_v30.py — identique bit à bit à x501_alpha_backtest.py (4 alphas, pipeline par barre 1h confirmée, fillModel pessimiste). x501_alpha_backtest.py n'est PAS versionné dans le dépôt (docs/25 : il vit dans le sandbox /home/z/my-project/scripts/) ; l'engine deep est son équivalent versionné et documenté, c'est lui qui fait foi.
Coûts (constantes CFG de l'engine, figées) : taker 4,5 bps + slippage 2 bps (marché/stop) ; TP maker 1,8 bps sans slippage. Stress ×1,5 exigé en plus (protocol_v2 critère 1).
Split : walk-forward strict protocol_v2 — 6 fenêtres chrono de 2 mois, embargo 72 h, tout calibrage sur données < W_i uniquement.
PASS si E[R] > 0 ET borne basse IC95 > 0 ET n ≥ 400 ET ≥ 5/6 fenêtres PASS ET E[R] tient à coûts ×1,5 · FAIL si borne haute < +0,05 R · SOUS_PUISSANT si n < 400 (l'edge détectable IC95 dépasse alors +0,10 R : on ne conclut pas)
Contrôles : les 40 symboles originaux en référence (le champion) · base-rate par état (MAGNITUDE ≠ DIRECTION) · hors top 5 % (un symbole ne porte pas le verdict) · comparaison appariée au champion (mêmes fenêtres, mêmes coûts)
Hash du gel : non gelée — le harnais n'existe pas encore (cette spec est le contrat, pas le run). Gel obligatoire AU COMMIT DU HARNAIS et AVANT toute collecte : le sha du commit de gel remplace cette ligne, et l'univers de test (≥ 40 symboles hors SYMS_40) y est figé. · Jugé sous : protocol_v2
