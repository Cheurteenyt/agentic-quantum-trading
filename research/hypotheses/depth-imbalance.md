# DEPTH-IMB — l'imbalance du carnet top-10
domaine : aster · famille : microstructure · stratégie : depth_imbalance_15m
Mécanisme : l'excès d'ordres bid vs ask dans le top-10 niveaux signale un déséquilibre de liquidité qui précède les mouvements à court terme (15 min).
Prédiction : DepthImbalance > 0,25 → mouvement haussier ≥ 0,8 % en 15 min
Données : depth.db (30 s, 15 symboles, maturité 14 j le 13/10), moyenne glissante 30 min
PASS si WR ≥ 65 % ET ratio bénéfice/coût ≥ 1,8 sur n ≥ 100 · FAIL si WR < 55 %
Contrôles : inverse (AskVolume > BidVolume → baissier) · hors liquidations · par symbole
Hash du gel : **1f25c0f** (2026-10-13 20:58:38 UTC) — le commit qui a introduit `scripts/depth_imbalance_forward.py` dans `main` ; le harnais DÉRIVE son gel de ce commit (`git --diff-filter=A`, `--gel` l'affiche), il ne le déclare pas à la main (le gel est un ÉTAT, pas une intention). · Jugé sous : protocol_v1 · FORWARD-ONLY : le harnais ne juge QUE les signaux postérieurs au gel ; `--include-past` n'est qu'une mesure, jamais un verdict.
