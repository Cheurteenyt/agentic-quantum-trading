# LONG-FLUSH-BOUNCE — la capitulation des longs est le signal d'achat
domaine : aster · famille : institutions · stratégie : long_flush_bounce_72h
Mécanisme : les GROSSES liquidations de longs (SELL side) représentent la capitulation des vendeurs. Après la capitulation, le prix rebondit (l'absorption des vendeurs — la loi de nuit confirmée par l'asymétrie mesurée ce soir : corr +0,105 à 72h, spread T3-T1 +1,655 %).
Prédiction : les entrées LONG après une capitulation (liq SELL ≥ p90 roulant 7j ET drawdown ≥ 3 % depuis le high 24h) ont une espérance positive à 72h.
Données : liq_events (SELL side, 11 j), klines 1h (33 symboles avec liq + klines).
Coûts : 18 bps RT taker. Levier 1x. Sizing : 20 % du capital par trade (le poids survivor).
Split : 70/30 chrono (7,7 j train / 3,3 j val — SOUS-PUISSANT déclaré d'office).
PASS si : E[ret] > 0 après coûts en TRAIN ET VAL, WR > 50 %, MAE max < 50 %.
FAIL si : E[ret] ≤ 0 OU WR < 40 %.
SOUS_PUISSANT si n < 10 en VAL (déclaré : le split VAL ne couvre que 3,3 jours).
Contrôles : inverse (SHORT la capitulation → devrait perdre) · par symbole · hors petites liq (< p50).
Hash du gel : <commit> · Jugé sous : protocol_v1 · FORWARD-ONLY pour le verdict définitif.
