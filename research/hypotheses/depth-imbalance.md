# DEPTH-IMB — l'imbalance du carnet top-10
domaine : aster · famille : microstructure · stratégie : depth_imbalance_15m
Mécanisme : l'excès d'ordres bid vs ask dans le top-10 niveaux signale un déséquilibre de liquidité qui précède les mouvements à court terme (15 min).
Prédiction : DepthImbalance > 0,25 → mouvement haussier ≥ 0,8 % en 15 min
Données : depth.db (30 s, 15 symboles, maturité 14 j le 13/10), moyenne glissante 30 min
PASS si WR ≥ 65 % ET ratio bénéfice/coût ≥ 1,8 sur n ≥ 100 · FAIL si WR < 55 %
Contrôles : inverse (AskVolume > BidVolume → baissier) · hors liquidations · par symbole
Hash du gel : <au commit> · Jugé sous : protocol_v1 · FORWARD-ONLY (depth 10 j — pas de rétrospectif)
