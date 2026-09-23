# Campagne backtest v2 — prix + funding, régimes, robustesse
23/09/2026 22:30 UTC — 902 combinaisons signal×symbole, 5 horizons, coûts 8 bps.
Règle CONFIRMÉ (pré-enregistrée) : pooled N≥10 & WR≥55 % en TRAIN(70 %) puis confirmé en VAL(30 %). Audit de multiplicité en fin de rapport.

## Résultats poolés (tous symboles)

| Signal | H | N | WR | Δ blind | Médiane | Pire | Robuste hors big-moves ? | Verdict |
|---|---|---|---|---|---|---|---|---|
| bb_squeeze_break_up | +1h | 1885 | 24.6 % | -9.5 pts | -0.28 % | -10.1 % | 24 % | BRUIT |
| bb_squeeze_break_up | +4h | 1885 | 35.0 % | -5.4 pts | -0.28 % | -17.7 % | 35 % | BRUIT |
| bb_squeeze_break_up | +12h | 1885 | 39.3 % | -6.8 pts | -0.45 % | -43.4 % | 39 % | BRUIT |
| bb_squeeze_break_up | +24h | 1876 | 42.0 % | -7.1 pts | -0.46 % | -45.1 % | 42 % | BRUIT |
| bb_squeeze_break_up | +72h | 1864 | 44.3 % | -7.4 pts | -0.80 % | -82.6 % | 44 % | BRUIT |
| bb_squeeze_break_up | +168h | 1830 | 42.8 % | -11.5 pts | -1.16 % | -79.1 % | 42 % | BRUIT |
| bb_squeeze_break_up | +336h | 1793 | 43.0 % | -13.7 pts | -1.82 % | -95.6 % | 42 % | BRUIT |
| bb_squeeze_break_up | +720h | 1682 | 40.4 % | -17.6 pts | -3.18 % | -99.5 % | 40 % | BRUIT |
| bb_squeeze_break_up | +1440h | 1510 | 37.2 % | -26.4 pts | -10.40 % | -99.9 % | 37 % | BRUIT |
| bb_squeeze_break_up | +2160h | 1299 | 25.6 % | -45.3 pts | -20.79 % | -100.0 % | 26 % | BRUIT |
| beta_dislocation_achat | +1h | 359 | 37.6 % | +3.4 pts | -0.28 % | -14.1 % | 38 % | BRUIT |
| beta_dislocation_achat | +4h | 359 | 40.4 % | +0.0 pts | -0.28 % | -12.6 % | 43 % | BRUIT |
| beta_dislocation_achat | +12h | 359 | 44.3 % | -1.8 pts | -0.37 % | -40.8 % | 46 % | BRUIT |
| beta_dislocation_achat | +24h | 359 | 46.8 % | -2.3 pts | -0.28 % | -39.4 % | 48 % | BRUIT |
| beta_dislocation_achat | +72h | 359 | 45.1 % | -6.6 pts | -0.78 % | -40.1 % | 45 % | BRUIT |
| beta_dislocation_achat | +168h | 359 | 39.0 % | -15.3 pts | -3.78 % | -86.1 % | 41 % | BRUIT |
| beta_dislocation_achat | +336h | 359 | 38.4 % | -18.3 pts | -5.34 % | -93.6 % | 40 % | BRUIT |
| beta_dislocation_achat | +720h | 349 | 34.1 % | -23.9 pts | -6.98 % | -99.3 % | 35 % | BRUIT |
| beta_dislocation_achat | +1440h | 345 | 37.1 % | -26.6 pts | -9.15 % | -99.8 % | 39 % | BRUIT |
| beta_dislocation_achat | +2160h | 342 | 41.2 % | -29.6 pts | -8.79 % | -99.9 % | 42 % | BRUIT |
| beta_dislocation_vente | +1h | 288 | 32.3 % | -1.9 pts | -0.28 % | -17.7 % | 29 % | BRUIT |
| beta_dislocation_vente | +4h | 288 | 41.7 % | +1.3 pts | -0.28 % | -12.4 % | 41 % | BRUIT |
| beta_dislocation_vente | +12h | 288 | 51.4 % | +5.3 pts | +0.17 % | -14.6 % | 55 % | BRUIT |
| beta_dislocation_vente | +24h | 288 | 56.2 % | +7.2 pts | +0.87 % | -104.4 % | 62 % | BRUIT |
| beta_dislocation_vente | +72h | 285 | 54.0 % | +2.3 pts | +0.78 % | -193.0 % | 59 % | BRUIT |
| beta_dislocation_vente | +168h | 283 | 57.6 % | +3.3 pts | +1.97 % | -96.8 % | 62 % | BRUIT |
| beta_dislocation_vente | +336h | 278 | 54.0 % | -2.8 pts | +1.17 % | -341.1 % | 61 % | BRUIT |
| beta_dislocation_vente | +720h | 268 | 59.7 % | +1.7 pts | +4.74 % | -1091.8 % | 66 % | BRUIT |
| beta_dislocation_vente | +1440h | 229 | 60.3 % | -3.4 pts | +6.71 % | -3999.6 % | 60 % | CONFIRMÉ |
| beta_dislocation_vente | +2160h | 217 | 50.2 % | -20.6 pts | +0.93 % | -10596.8 % | 53 % | BRUIT |
| donchian_breakdown | +1h | 4067 | 24.7 % | -9.4 pts | -0.28 % | -95.9 % | 25 % | BRUIT |
| donchian_breakdown | +4h | 4066 | 34.3 % | -6.0 pts | -0.28 % | -77.0 % | 34 % | BRUIT |
| donchian_breakdown | +12h | 4043 | 42.2 % | -3.9 pts | -0.32 % | -122.4 % | 42 % | BRUIT |
| donchian_breakdown | +24h | 4042 | 45.3 % | -3.8 pts | -0.32 % | -145.2 % | 45 % | BRUIT |
| donchian_breakdown | +72h | 4032 | 48.9 % | -2.8 pts | -0.13 % | -381.6 % | 49 % | BRUIT |
| donchian_breakdown | +168h | 3997 | 53.2 % | -1.1 pts | +0.64 % | -462.2 % | 53 % | BRUIT |
| donchian_breakdown | +336h | 3881 | 56.2 % | -0.5 pts | +1.87 % | -653.0 % | 56 % | BRUIT |
| donchian_breakdown | +720h | 3660 | 56.3 % | -1.7 pts | +2.62 % | -1972.4 % | 56 % | BRUIT |
| donchian_breakdown | +1440h | 3315 | 62.0 % | -1.7 pts | +9.55 % | -8099.8 % | 62 % | BRUIT |
| donchian_breakdown | +2160h | 2931 | 67.9 % | -2.9 pts | +16.43 % | -9845.1 % | 68 % | BRUIT |
| donchian_breakout | +1h | 3817 | 26.5 % | -7.6 pts | -0.28 % | -24.4 % | 26 % | BRUIT |
| donchian_breakout | +4h | 3817 | 36.4 % | -4.0 pts | -0.28 % | -43.6 % | 36 % | BRUIT |
| donchian_breakout | +12h | 3817 | 39.9 % | -6.1 pts | -0.42 % | -56.9 % | 39 % | BRUIT |
| donchian_breakout | +24h | 3805 | 41.5 % | -7.6 pts | -0.55 % | -62.0 % | 41 % | BRUIT |
| donchian_breakout | +72h | 3768 | 42.8 % | -9.0 pts | -0.97 % | -89.1 % | 43 % | BRUIT |
| donchian_breakout | +168h | 3696 | 42.2 % | -12.1 pts | -1.49 % | -91.7 % | 42 % | BRUIT |
| donchian_breakout | +336h | 3614 | 41.4 % | -15.3 pts | -2.18 % | -98.3 % | 41 % | BRUIT |
| donchian_breakout | +720h | 3401 | 40.0 % | -18.0 pts | -3.90 % | -99.5 % | 40 % | BRUIT |
| donchian_breakout | +1440h | 3016 | 34.8 % | -28.8 pts | -11.73 % | -99.9 % | 35 % | BRUIT |
| donchian_breakout | +2160h | 2639 | 26.6 % | -44.2 pts | -20.60 % | -100.0 % | 26 % | BRUIT |
| ema_death_cross | +1h | 3748 | 24.0 % | -10.2 pts | -0.28 % | -43.4 % | 24 % | BRUIT |
| ema_death_cross | +4h | 3748 | 36.7 % | -3.7 pts | -0.28 % | -36.5 % | 37 % | BRUIT |
| ema_death_cross | +12h | 3726 | 43.7 % | -2.3 pts | -0.28 % | -68.4 % | 44 % | BRUIT |
| ema_death_cross | +24h | 3720 | 47.0 % | -2.1 pts | -0.21 % | -171.9 % | 47 % | BRUIT |
| ema_death_cross | +72h | 3705 | 53.1 % | +1.4 pts | +0.36 % | -216.9 % | 53 % | BRUIT |
| ema_death_cross | +168h | 3667 | 54.4 % | +0.1 pts | +0.93 % | -566.0 % | 54 % | BRUIT |
| ema_death_cross | +336h | 3583 | 56.2 % | -0.5 pts | +1.73 % | -774.7 % | 56 % | BRUIT |
| ema_death_cross | +720h | 3359 | 57.6 % | -0.4 pts | +3.33 % | -1972.4 % | 58 % | BRUIT |
| ema_death_cross | +1440h | 3005 | 65.4 % | +1.8 pts | +11.52 % | -9955.7 % | 65 % | BRUIT |
| ema_death_cross | +2160h | 2677 | 72.8 % | +2.0 pts | +19.19 % | -9242.4 % | 73 % | CONFIRMÉ |
| ema_golden_cross | +1h | 3844 | 24.6 % | -9.5 pts | -0.28 % | -17.4 % | 24 % | BRUIT |
| ema_golden_cross | +4h | 3844 | 35.3 % | -5.1 pts | -0.28 % | -34.9 % | 35 % | BRUIT |
| ema_golden_cross | +12h | 3844 | 39.5 % | -6.5 pts | -0.45 % | -56.2 % | 39 % | BRUIT |
| ema_golden_cross | +24h | 3839 | 40.8 % | -8.3 pts | -0.58 % | -60.1 % | 41 % | BRUIT |
| ema_golden_cross | +72h | 3823 | 41.2 % | -10.6 pts | -1.07 % | -74.7 % | 41 % | BRUIT |
| ema_golden_cross | +168h | 3777 | 42.4 % | -11.9 pts | -1.50 % | -91.7 % | 43 % | BRUIT |
| ema_golden_cross | +336h | 3694 | 41.6 % | -15.1 pts | -2.21 % | -98.1 % | 42 % | BRUIT |
| ema_golden_cross | +720h | 3472 | 40.1 % | -17.9 pts | -4.13 % | -99.5 % | 40 % | BRUIT |
| ema_golden_cross | +1440h | 3124 | 34.1 % | -29.6 pts | -12.08 % | -99.9 % | 34 % | BRUIT |
| ema_golden_cross | +2160h | 2764 | 27.1 % | -43.7 pts | -20.04 % | -99.9 % | 27 % | BRUIT |
| funding_accel_momentum | +1h | 192 | 28.6 % | -5.5 pts | -0.22 % | -2.6 % | 29 % | BRUIT |
| funding_accel_momentum | +4h | 192 | 45.8 % | +5.5 pts | -0.05 % | -7.6 % | 46 % | BRUIT |
| funding_accel_momentum | +12h | 192 | 55.7 % | +9.7 pts | +0.10 % | -25.3 % | 55 % | BRUIT |
| funding_accel_momentum | +24h | 192 | 49.5 % | +0.4 pts | -0.07 % | -28.4 % | 49 % | BRUIT |
| funding_accel_momentum | +72h | 179 | 60.3 % | +8.6 pts | +0.84 % | -31.6 % | 60 % | BRUIT |
| funding_accel_momentum | +168h | 150 | 61.3 % | +7.0 pts | +1.88 % | -31.3 % | 61 % | BRUIT |
| funding_accel_momentum | +336h | 85 | 58.8 % | +2.1 pts | +1.35 % | -27.9 % | 58 % | BRUIT |
| funding_accel_momentum | +720h | 10 | 90.0 % | +32.0 pts | +8.27 % | -3.6 % | — | BRUIT |
| funding_extreme_contre_courant | +1h | 91 | 30.8 % | -3.4 pts | -0.28 % | -4.2 % | 31 % | BRUIT |
| funding_extreme_contre_courant | +4h | 91 | 41.8 % | +1.4 pts | -0.17 % | -13.5 % | 42 % | BRUIT |
| funding_extreme_contre_courant | +12h | 91 | 46.2 % | +0.1 pts | -0.12 % | -27.9 % | 46 % | BRUIT |
| funding_extreme_contre_courant | +24h | 91 | 53.8 % | +4.8 pts | +0.14 % | -23.9 % | 54 % | BRUIT |
| funding_extreme_contre_courant | +72h | 81 | 46.9 % | -4.8 pts | -0.89 % | -28.0 % | 47 % | BRUIT |
| funding_extreme_contre_courant | +168h | 67 | 65.7 % | +11.4 pts | +4.12 % | -30.6 % | 66 % | CONFIRMÉ |
| funding_extreme_contre_courant | +336h | 22 | 54.5 % | -2.2 pts | +1.29 % | -6.2 % | 55 % | BRUIT |
| funding_flip_neg | +1h | 79 | 19.0 % | -15.2 pts | -0.28 % | -2.2 % | 19 % | BRUIT |
| funding_flip_neg | +4h | 79 | 32.9 % | -7.5 pts | -0.25 % | -2.4 % | 33 % | BRUIT |
| funding_flip_neg | +12h | 79 | 41.8 % | -4.3 pts | -0.24 % | -6.8 % | 42 % | BRUIT |
| funding_flip_neg | +24h | 79 | 48.1 % | -1.0 pts | -0.20 % | -11.0 % | 48 % | BRUIT |
| funding_flip_neg | +72h | 72 | 50.0 % | -1.8 pts | +0.11 % | -23.8 % | 50 % | BRUIT |
| funding_flip_neg | +168h | 64 | 39.1 % | -15.2 pts | -1.57 % | -45.5 % | 39 % | BRUIT |
| funding_flip_neg | +336h | 34 | 32.4 % | -24.4 pts | -2.17 % | -20.4 % | 32 % | BRUIT |
| funding_flip_pos | +1h | 47 | 21.3 % | -12.9 pts | -0.18 % | -1.5 % | 21 % | BRUIT |
| funding_flip_pos | +4h | 47 | 36.2 % | -4.2 pts | -0.33 % | -3.8 % | 36 % | BRUIT |
| funding_flip_pos | +12h | 47 | 46.8 % | +0.8 pts | -0.16 % | -5.0 % | 47 % | BRUIT |
| funding_flip_pos | +24h | 47 | 51.1 % | +2.0 pts | +0.02 % | -7.9 % | 51 % | BRUIT |
| funding_flip_pos | +72h | 45 | 53.3 % | +1.6 pts | +0.04 % | -7.8 % | 53 % | BRUIT |
| funding_flip_pos | +168h | 38 | 68.4 % | +14.1 pts | +2.55 % | -10.9 % | 68 % | BRUIT |
| funding_flip_pos | +336h | 16 | 50.0 % | -6.7 pts | +0.45 % | -5.9 % | 50 % | BRUIT |
| funding_prix_divergence_long | +1h | 172 | 28.5 % | -5.7 pts | -0.28 % | -3.5 % | 28 % | BRUIT |
| funding_prix_divergence_long | +4h | 172 | 47.7 % | +7.3 pts | -0.05 % | -7.0 % | 48 % | BRUIT |
| funding_prix_divergence_long | +12h | 172 | 39.0 % | -7.1 pts | -0.66 % | -17.2 % | 36 % | BRUIT |
| funding_prix_divergence_long | +24h | 172 | 38.4 % | -10.7 pts | -1.49 % | -12.8 % | 33 % | BRUIT |
| funding_prix_divergence_long | +72h | 137 | 52.6 % | +0.8 pts | +0.18 % | -32.8 % | 48 % | BRUIT |
| funding_prix_divergence_long | +168h | 104 | 34.6 % | -19.7 pts | -1.84 % | -34.3 % | 30 % | BRUIT |
| funding_prix_divergence_long | +336h | 71 | 43.7 % | -13.1 pts | -1.05 % | -29.6 % | 31 % | BRUIT |
| funding_prix_divergence_long | +720h | 13 | 69.2 % | +11.2 pts | +10.24 % | -3.0 % | — | BRUIT |
| funding_prix_divergence_short | +1h | 192 | 22.9 % | -11.2 pts | -0.33 % | -3.8 % | 23 % | BRUIT |
| funding_prix_divergence_short | +4h | 192 | 44.8 % | +4.4 pts | -0.29 % | -12.7 % | 45 % | BRUIT |
| funding_prix_divergence_short | +12h | 192 | 60.9 % | +14.9 pts | +0.17 % | -10.1 % | 61 % | CONFIRMÉ |
| funding_prix_divergence_short | +24h | 192 | 54.7 % | +5.6 pts | +0.36 % | -37.1 % | 55 % | BRUIT |
| funding_prix_divergence_short | +72h | 180 | 42.8 % | -9.0 pts | -1.18 % | -26.6 % | 43 % | BRUIT |
| funding_prix_divergence_short | +168h | 159 | 29.6 % | -24.8 pts | -4.87 % | -50.1 % | 30 % | BRUIT |
| funding_prix_divergence_short | +336h | 67 | 38.8 % | -17.9 pts | -0.22 % | -25.6 % | 39 % | BRUIT |
| macd_cross_down | +1h | 5405 | 25.5 % | -8.6 pts | -0.28 % | -95.9 % | 25 % | BRUIT |
| macd_cross_down | +4h | 5405 | 39.5 % | -0.9 pts | -0.28 % | -67.3 % | 39 % | BRUIT |
| macd_cross_down | +12h | 5401 | 45.6 % | -0.5 pts | -0.22 % | -200.3 % | 46 % | BRUIT |
| macd_cross_down | +24h | 5381 | 47.4 % | -1.7 pts | -0.19 % | -227.5 % | 47 % | BRUIT |
| macd_cross_down | +72h | 5346 | 50.9 % | -0.9 pts | +0.13 % | -222.7 % | 51 % | BRUIT |
| macd_cross_down | +168h | 5281 | 54.5 % | +0.2 pts | +0.80 % | -612.7 % | 55 % | BRUIT |
| macd_cross_down | +336h | 5158 | 57.0 % | +0.3 pts | +1.75 % | -774.7 % | 57 % | BRUIT |
| macd_cross_down | +720h | 4857 | 58.5 % | +0.5 pts | +3.34 % | -1559.9 % | 59 % | BRUIT |
| macd_cross_down | +1440h | 4348 | 64.2 % | +0.6 pts | +10.87 % | -10276.8 % | 64 % | BRUIT |
| macd_cross_down | +2160h | 3867 | 70.2 % | -0.7 pts | +18.00 % | -10283.9 % | 70 % | CONFIRMÉ |
| macd_cross_up | +1h | 5288 | 23.5 % | -10.6 pts | -0.28 % | -27.4 % | 23 % | BRUIT |
| macd_cross_up | +4h | 5288 | 34.9 % | -5.5 pts | -0.28 % | -58.8 % | 35 % | BRUIT |
| macd_cross_up | +12h | 5288 | 39.8 % | -6.2 pts | -0.44 % | -63.7 % | 39 % | BRUIT |
| macd_cross_up | +24h | 5282 | 42.5 % | -6.6 pts | -0.50 % | -82.7 % | 42 % | BRUIT |
| macd_cross_up | +72h | 5252 | 43.3 % | -8.5 pts | -0.85 % | -86.1 % | 43 % | BRUIT |
| macd_cross_up | +168h | 5183 | 42.6 % | -11.7 pts | -1.45 % | -96.2 % | 43 % | BRUIT |
| macd_cross_up | +336h | 5056 | 41.2 % | -15.5 pts | -2.38 % | -98.1 % | 41 % | BRUIT |
| macd_cross_up | +720h | 4770 | 40.3 % | -17.8 pts | -3.78 % | -99.5 % | 40 % | BRUIT |
| macd_cross_up | +1440h | 4257 | 35.3 % | -28.3 pts | -11.14 % | -99.9 % | 35 % | BRUIT |
| macd_cross_up | +2160h | 3761 | 29.6 % | -41.2 pts | -18.78 % | -99.9 % | 29 % | BRUIT |
| rsi_surachat_reprise | +1h | 1866 | 26.5 % | -7.7 pts | -0.28 % | -45.4 % | 27 % | BRUIT |
| rsi_surachat_reprise | +4h | 1866 | 39.6 % | -0.8 pts | -0.28 % | -49.5 % | 40 % | BRUIT |
| rsi_surachat_reprise | +12h | 1865 | 46.1 % | +0.1 pts | -0.22 % | -143.9 % | 47 % | BRUIT |
| rsi_surachat_reprise | +24h | 1857 | 50.6 % | +1.5 pts | +0.05 % | -86.0 % | 51 % | BRUIT |
| rsi_surachat_reprise | +72h | 1828 | 53.6 % | +1.9 pts | +0.55 % | -184.5 % | 55 % | BRUIT |
| rsi_surachat_reprise | +168h | 1774 | 57.2 % | +2.8 pts | +1.32 % | -365.0 % | 58 % | BRUIT |
| rsi_surachat_reprise | +336h | 1740 | 56.5 % | -0.2 pts | +1.84 % | -606.3 % | 58 % | BRUIT |
| rsi_surachat_reprise | +720h | 1629 | 58.4 % | +0.3 pts | +3.50 % | -1344.8 % | 60 % | BRUIT |
| rsi_surachat_reprise | +1440h | 1411 | 62.7 % | -0.9 pts | +9.72 % | -6969.9 % | 63 % | BRUIT |
| rsi_surachat_reprise | +2160h | 1230 | 72.3 % | +1.5 pts | +18.94 % | -11077.6 % | 72 % | CONFIRMÉ |
| rsi_survente_reprise | +1h | 1988 | 22.4 % | -11.7 pts | -0.28 % | -24.8 % | 23 % | BRUIT |
| rsi_survente_reprise | +4h | 1986 | 37.3 % | -3.1 pts | -0.28 % | -41.3 % | 37 % | BRUIT |
| rsi_survente_reprise | +12h | 1975 | 45.2 % | -0.8 pts | -0.24 % | -63.7 % | 45 % | BRUIT |
| rsi_survente_reprise | +24h | 1974 | 46.1 % | -2.9 pts | -0.28 % | -82.7 % | 46 % | BRUIT |
| rsi_survente_reprise | +72h | 1972 | 49.0 % | -2.7 pts | -0.14 % | -86.1 % | 49 % | BRUIT |
| rsi_survente_reprise | +168h | 1959 | 47.2 % | -7.1 pts | -0.67 % | -96.2 % | 47 % | BRUIT |
| rsi_survente_reprise | +336h | 1891 | 42.9 % | -13.8 pts | -1.82 % | -98.1 % | 43 % | BRUIT |
| rsi_survente_reprise | +720h | 1815 | 42.9 % | -15.2 pts | -3.17 % | -99.4 % | 43 % | BRUIT |
| rsi_survente_reprise | +1440h | 1663 | 37.3 % | -26.4 pts | -10.49 % | -99.8 % | 38 % | BRUIT |
| rsi_survente_reprise | +2160h | 1494 | 34.6 % | -36.2 pts | -13.75 % | -99.9 % | 34 % | BRUIT |
| stoch_surachat_reprise | +1h | 5617 | 26.0 % | -8.1 pts | -0.28 % | -45.4 % | 26 % | BRUIT |
| stoch_surachat_reprise | +4h | 5617 | 39.9 % | -0.5 pts | -0.27 % | -106.9 % | 40 % | BRUIT |
| stoch_surachat_reprise | +12h | 5615 | 46.5 % | +0.5 pts | -0.16 % | -139.8 % | 47 % | BRUIT |
| stoch_surachat_reprise | +24h | 5602 | 49.2 % | +0.1 pts | -0.07 % | -128.8 % | 49 % | BRUIT |
| stoch_surachat_reprise | +72h | 5560 | 53.0 % | +1.2 pts | +0.36 % | -256.1 % | 53 % | BRUIT |
| stoch_surachat_reprise | +168h | 5466 | 55.1 % | +0.8 pts | +0.90 % | -556.8 % | 55 % | BRUIT |
| stoch_surachat_reprise | +336h | 5342 | 56.7 % | -0.1 pts | +1.74 % | -766.9 % | 57 % | BRUIT |
| stoch_surachat_reprise | +720h | 5040 | 59.1 % | +1.0 pts | +3.56 % | -1464.0 % | 60 % | BRUIT |
| stoch_surachat_reprise | +1440h | 4483 | 64.6 % | +0.9 pts | +11.25 % | -9159.6 % | 64 % | BRUIT |
| stoch_surachat_reprise | +2160h | 3957 | 71.9 % | +1.1 pts | +19.67 % | -10596.8 % | 72 % | CONFIRMÉ |
| stoch_survente_reprise | +1h | 5712 | 25.5 % | -8.7 pts | -0.28 % | -24.8 % | 25 % | BRUIT |
| stoch_survente_reprise | +4h | 5711 | 37.6 % | -2.8 pts | -0.28 % | -30.6 % | 38 % | BRUIT |
| stoch_survente_reprise | +12h | 5689 | 42.6 % | -3.4 pts | -0.28 % | -70.8 % | 43 % | BRUIT |
| stoch_survente_reprise | +24h | 5683 | 45.0 % | -4.1 pts | -0.35 % | -90.6 % | 45 % | BRUIT |
| stoch_survente_reprise | +72h | 5659 | 45.2 % | -6.5 pts | -0.66 % | -92.7 % | 45 % | BRUIT |
| stoch_survente_reprise | +168h | 5593 | 43.6 % | -10.8 pts | -1.36 % | -98.5 % | 44 % | BRUIT |
| stoch_survente_reprise | +336h | 5440 | 41.7 % | -15.0 pts | -2.30 % | -99.4 % | 42 % | BRUIT |
| stoch_survente_reprise | +720h | 5134 | 41.0 % | -17.0 pts | -3.72 % | -99.4 % | 41 % | BRUIT |
| stoch_survente_reprise | +1440h | 4629 | 35.0 % | -28.6 pts | -11.19 % | -99.8 % | 35 % | BRUIT |
| stoch_survente_reprise | +2160h | 4128 | 29.4 % | -41.4 pts | -18.47 % | -99.9 % | 29 % | BRUIT |
| streak_rouge_fade_long | +1h | 790 | 35.9 % | +1.8 pts | -0.18 % | -36.5 % | 36 % | BRUIT |
| streak_rouge_fade_long | +4h | 790 | 39.6 % | -0.8 pts | -0.27 % | -46.5 % | 40 % | BRUIT |
| streak_rouge_fade_long | +12h | 784 | 46.3 % | +0.3 pts | -0.18 % | -39.3 % | 47 % | BRUIT |
| streak_rouge_fade_long | +24h | 783 | 44.8 % | -4.2 pts | -0.42 % | -65.0 % | 46 % | BRUIT |
| streak_rouge_fade_long | +72h | 780 | 45.9 % | -5.9 pts | -0.56 % | -91.8 % | 46 % | BRUIT |
| streak_rouge_fade_long | +168h | 777 | 41.6 % | -12.7 pts | -1.67 % | -98.4 % | 42 % | BRUIT |
| streak_rouge_fade_long | +336h | 750 | 38.4 % | -18.3 pts | -3.14 % | -99.3 % | 38 % | BRUIT |
| streak_rouge_fade_long | +720h | 729 | 36.8 % | -21.3 pts | -5.12 % | -99.3 % | 37 % | BRUIT |
| streak_rouge_fade_long | +1440h | 678 | 31.1 % | -32.5 pts | -15.35 % | -99.8 % | 32 % | BRUIT |
| streak_rouge_fade_long | +2160h | 635 | 24.9 % | -45.9 pts | -19.63 % | -99.6 % | 24 % | BRUIT |
| streak_vert_fade_short | +1h | 781 | 38.3 % | +4.1 pts | -0.20 % | -29.8 % | 38 % | BRUIT |
| streak_vert_fade_short | +4h | 781 | 43.9 % | +3.5 pts | -0.16 % | -27.0 % | 44 % | BRUIT |
| streak_vert_fade_short | +12h | 781 | 46.7 % | +0.7 pts | -0.17 % | -35.0 % | 48 % | BRUIT |
| streak_vert_fade_short | +24h | 778 | 50.0 % | +0.9 pts | +0.00 % | -40.6 % | 50 % | BRUIT |
| streak_vert_fade_short | +72h | 771 | 55.9 % | +4.1 pts | +0.71 % | -141.6 % | 56 % | BRUIT |
| streak_vert_fade_short | +168h | 747 | 56.9 % | +2.6 pts | +1.28 % | -235.7 % | 57 % | BRUIT |
| streak_vert_fade_short | +336h | 732 | 60.4 % | +3.7 pts | +2.41 % | -395.2 % | 62 % | BRUIT |
| streak_vert_fade_short | +720h | 694 | 62.0 % | +3.9 pts | +4.54 % | -1193.2 % | 63 % | BRUIT |
| streak_vert_fade_short | +1440h | 627 | 68.7 % | +5.1 pts | +14.84 % | -3811.0 % | 68 % | CONFIRMÉ |
| streak_vert_fade_short | +2160h | 568 | 75.9 % | +5.1 pts | +22.01 % | -10596.8 % | 77 % | CONFIRMÉ |
| sweep_liquidite_long | +1h | 2811 | 31.9 % | -2.2 pts | -0.28 % | -61.6 % | 32 % | BRUIT |
| sweep_liquidite_long | +4h | 2810 | 43.4 % | +3.0 pts | -0.19 % | -76.8 % | 44 % | BRUIT |
| sweep_liquidite_long | +12h | 2795 | 45.3 % | -0.8 pts | -0.23 % | -85.0 % | 46 % | BRUIT |
| sweep_liquidite_long | +24h | 2793 | 45.4 % | -3.7 pts | -0.34 % | -87.2 % | 46 % | BRUIT |
| sweep_liquidite_long | +72h | 2782 | 45.7 % | -6.1 pts | -0.57 % | -93.9 % | 46 % | BRUIT |
| sweep_liquidite_long | +168h | 2759 | 42.7 % | -11.7 pts | -1.42 % | -98.0 % | 43 % | BRUIT |
| sweep_liquidite_long | +336h | 2689 | 40.5 % | -16.2 pts | -2.48 % | -99.4 % | 41 % | BRUIT |
| sweep_liquidite_long | +720h | 2535 | 40.2 % | -17.8 pts | -3.96 % | -99.4 % | 40 % | BRUIT |
| sweep_liquidite_long | +1440h | 2325 | 32.7 % | -30.9 pts | -12.24 % | -99.9 % | 33 % | BRUIT |
| sweep_liquidite_long | +2160h | 2101 | 26.7 % | -44.1 pts | -18.87 % | -99.9 % | 26 % | BRUIT |
| sweep_liquidite_short | +1h | 2877 | 33.5 % | -0.7 pts | -0.27 % | -45.4 % | 34 % | BRUIT |
| sweep_liquidite_short | +4h | 2877 | 43.8 % | +3.4 pts | -0.17 % | -42.2 % | 44 % | BRUIT |
| sweep_liquidite_short | +12h | 2877 | 49.3 % | +3.2 pts | -0.05 % | -75.5 % | 49 % | BRUIT |
| sweep_liquidite_short | +24h | 2863 | 51.8 % | +2.7 pts | +0.13 % | -123.3 % | 52 % | BRUIT |
| sweep_liquidite_short | +72h | 2834 | 55.2 % | +3.4 pts | +0.72 % | -303.8 % | 55 % | BRUIT |
| sweep_liquidite_short | +168h | 2773 | 56.9 % | +2.6 pts | +1.29 % | -373.2 % | 57 % | BRUIT |
| sweep_liquidite_short | +336h | 2714 | 58.0 % | +1.3 pts | +1.99 % | -535.0 % | 58 % | BRUIT |
| sweep_liquidite_short | +720h | 2569 | 59.2 % | +1.1 pts | +3.51 % | -1289.3 % | 59 % | BRUIT |
| sweep_liquidite_short | +1440h | 2304 | 67.7 % | +4.1 pts | +12.88 % | -7446.4 % | 68 % | CONFIRMÉ |
| sweep_liquidite_short | +2160h | 2053 | 76.9 % | +6.0 pts | +22.14 % | -8980.8 % | 77 % | CONFIRMÉ |
| vol_spike_retournement_long | +1h | 888 | 34.1 % | -0.0 pts | -0.28 % | -20.0 % | 34 % | BRUIT |
| vol_spike_retournement_long | +4h | 888 | 41.0 % | +0.6 pts | -0.29 % | -24.3 % | 41 % | BRUIT |
| vol_spike_retournement_long | +12h | 886 | 43.6 % | -2.5 pts | -0.30 % | -68.0 % | 43 % | BRUIT |
| vol_spike_retournement_long | +24h | 883 | 44.5 % | -4.6 pts | -0.34 % | -87.6 % | 44 % | BRUIT |
| vol_spike_retournement_long | +72h | 875 | 43.1 % | -8.7 pts | -0.80 % | -84.4 % | 43 % | BRUIT |
| vol_spike_retournement_long | +168h | 864 | 42.7 % | -11.6 pts | -1.19 % | -81.0 % | 43 % | BRUIT |
| vol_spike_retournement_long | +336h | 838 | 39.4 % | -17.3 pts | -2.50 % | -97.9 % | 39 % | BRUIT |
| vol_spike_retournement_long | +720h | 792 | 37.8 % | -20.3 pts | -3.97 % | -99.3 % | 38 % | BRUIT |
| vol_spike_retournement_long | +1440h | 727 | 33.8 % | -29.8 pts | -10.75 % | -99.8 % | 34 % | BRUIT |
| vol_spike_retournement_long | +2160h | 656 | 30.6 % | -40.2 pts | -18.14 % | -99.9 % | 30 % | BRUIT |
| vol_spike_retournement_short | +1h | 1099 | 30.8 % | -3.3 pts | -0.28 % | -45.4 % | 31 % | BRUIT |
| vol_spike_retournement_short | +4h | 1099 | 40.6 % | +0.2 pts | -0.28 % | -39.2 % | 40 % | BRUIT |
| vol_spike_retournement_short | +12h | 1090 | 48.0 % | +1.9 pts | -0.12 % | -35.9 % | 47 % | BRUIT |
| vol_spike_retournement_short | +24h | 1090 | 50.7 % | +1.7 pts | +0.03 % | -43.5 % | 50 % | BRUIT |
| vol_spike_retournement_short | +72h | 1087 | 54.8 % | +3.1 pts | +0.45 % | -80.3 % | 55 % | BRUIT |
| vol_spike_retournement_short | +168h | 1070 | 55.6 % | +1.3 pts | +1.08 % | -169.0 % | 55 % | BRUIT |
| vol_spike_retournement_short | +336h | 1030 | 58.2 % | +1.4 pts | +1.99 % | -469.0 % | 58 % | BRUIT |
| vol_spike_retournement_short | +720h | 969 | 57.4 % | -0.7 pts | +3.46 % | -884.5 % | 58 % | BRUIT |
| vol_spike_retournement_short | +1440h | 865 | 65.5 % | +1.9 pts | +12.20 % | -7224.4 % | 65 % | CONFIRMÉ |
| vol_spike_retournement_short | +2160h | 791 | 72.2 % | +1.4 pts | +19.28 % | -10828.6 % | 73 % | CONFIRMÉ |
| volume_mort_cassure | +1h | 1312 | 33.5 % | -0.6 pts | -0.28 % | -14.9 % | 33 % | BRUIT |
| volume_mort_cassure | +4h | 1312 | 40.1 % | -0.3 pts | -0.26 % | -17.7 % | 40 % | BRUIT |
| volume_mort_cassure | +12h | 1312 | 42.2 % | -3.8 pts | -0.36 % | -46.7 % | 42 % | BRUIT |
| volume_mort_cassure | +24h | 1307 | 44.2 % | -4.9 pts | -0.35 % | -47.6 % | 44 % | BRUIT |
| volume_mort_cassure | +72h | 1294 | 44.4 % | -7.3 pts | -0.84 % | -89.1 % | 44 % | BRUIT |
| volume_mort_cassure | +168h | 1270 | 43.0 % | -11.3 pts | -1.50 % | -91.7 % | 43 % | BRUIT |
| volume_mort_cassure | +336h | 1259 | 39.5 % | -17.2 pts | -2.70 % | -98.3 % | 39 % | BRUIT |
| volume_mort_cassure | +720h | 1192 | 37.2 % | -20.8 pts | -4.99 % | -99.5 % | 36 % | BRUIT |
| volume_mort_cassure | +1440h | 1093 | 29.3 % | -34.4 pts | -15.91 % | -99.9 % | 29 % | BRUIT |
| volume_mort_cassure | +2160h | 987 | 19.7 % | -51.2 pts | -24.43 % | -100.0 % | 19 % | BRUIT |
| vwap_extreme_reprise_long | +1h | 658 | 31.0 % | -3.2 pts | -0.28 % | -24.8 % | 31 % | BRUIT |
| vwap_extreme_reprise_long | +4h | 658 | 40.3 % | -0.1 pts | -0.28 % | -32.5 % | 42 % | BRUIT |
| vwap_extreme_reprise_long | +12h | 657 | 42.9 % | -3.1 pts | -0.30 % | -29.0 % | 45 % | BRUIT |
| vwap_extreme_reprise_long | +24h | 657 | 46.7 % | -2.3 pts | -0.38 % | -42.3 % | 47 % | BRUIT |
| vwap_extreme_reprise_long | +72h | 657 | 53.7 % | +2.0 pts | +0.54 % | -52.2 % | 53 % | BRUIT |
| vwap_extreme_reprise_long | +168h | 655 | 49.9 % | -4.4 pts | -0.07 % | -47.4 % | 53 % | BRUIT |
| vwap_extreme_reprise_long | +336h | 638 | 45.0 % | -11.7 pts | -1.28 % | -48.4 % | 45 % | BRUIT |
| vwap_extreme_reprise_long | +720h | 620 | 42.9 % | -15.1 pts | -2.72 % | -62.4 % | 44 % | BRUIT |
| vwap_extreme_reprise_long | +1440h | 579 | 34.9 % | -28.8 pts | -9.77 % | -75.6 % | 35 % | BRUIT |
| vwap_extreme_reprise_long | +2160h | 529 | 40.6 % | -30.2 pts | -10.63 % | -53.8 % | 39 % | BRUIT |
| vwap_extreme_reprise_short | +1h | 507 | 33.9 % | -0.2 pts | -0.28 % | -30.7 % | 35 % | BRUIT |
| vwap_extreme_reprise_short | +4h | 507 | 44.4 % | +4.0 pts | -0.28 % | -34.5 % | 46 % | BRUIT |
| vwap_extreme_reprise_short | +12h | 507 | 51.9 % | +5.8 pts | +0.13 % | -163.2 % | 54 % | BRUIT |
| vwap_extreme_reprise_short | +24h | 505 | 51.1 % | +2.0 pts | +0.09 % | -94.0 % | 53 % | BRUIT |
| vwap_extreme_reprise_short | +72h | 497 | 57.1 % | +5.4 pts | +1.06 % | -171.0 % | 59 % | BRUIT |
| vwap_extreme_reprise_short | +168h | 483 | 59.0 % | +4.7 pts | +1.95 % | -139.0 % | 62 % | BRUIT |
| vwap_extreme_reprise_short | +336h | 478 | 53.8 % | -2.9 pts | +1.57 % | -499.2 % | 56 % | BRUIT |
| vwap_extreme_reprise_short | +720h | 449 | 56.8 % | -1.2 pts | +3.67 % | -1100.3 % | 61 % | BRUIT |
| vwap_extreme_reprise_short | +1440h | 345 | 71.3 % | +7.7 pts | +15.00 % | -4048.1 % | 71 % | CONFIRMÉ |
| vwap_extreme_reprise_short | +2160h | 308 | 80.2 % | +9.4 pts | +22.44 % | -11139.1 % | 80 % | CONFIRMÉ |

## Régimes de marché (signaux avec N≥50)

| Signal | H | N | Hausse | Baisse | Vol haute | Vol basse |
|---|---|---|---|---|---|---|
| bb_squeeze_break_up | +1h | 1885 | 26 % (n=1065) | 33 % (n=261) | 18 % (n=441) | 19 % (n=118) |
| bb_squeeze_break_up | +4h | 1885 | 35 % (n=1065) | 36 % (n=261) | 36 % (n=441) | 30 % (n=118) |
| bb_squeeze_break_up | +12h | 1885 | 39 % (n=1065) | 40 % (n=261) | 40 % (n=441) | 36 % (n=118) |
| bb_squeeze_break_up | +24h | 1876 | 44 % (n=1058) | 38 % (n=259) | 41 % (n=441) | 36 % (n=118) |
| bb_squeeze_break_up | +72h | 1864 | 46 % (n=1054) | 35 % (n=251) | 46 % (n=441) | 39 % (n=118) |
| bb_squeeze_break_up | +168h | 1830 | 44 % (n=1029) | 35 % (n=243) | 48 % (n=441) | 32 % (n=117) |
| bb_squeeze_break_up | +336h | 1793 | 43 % (n=1024) | 42 % (n=235) | 47 % (n=426) | 28 % (n=108) |
| bb_squeeze_break_up | +720h | 1682 | 42 % (n=969) | 32 % (n=226) | 43 % (n=383) | 30 % (n=104) |
| bb_squeeze_break_up | +1440h | 1510 | 39 % (n=860) | 35 % (n=210) | 39 % (n=340) | 24 % (n=100) |
| bb_squeeze_break_up | +2160h | 1299 | 26 % (n=714) | 25 % (n=189) | 24 % (n=302) | 32 % (n=94) |
| beta_dislocation_achat | +1h | 359 | — | — | 41 % (n=124) | 36 % (n=226) |
| beta_dislocation_achat | +4h | 359 | — | — | 41 % (n=124) | 41 % (n=226) |
| beta_dislocation_achat | +12h | 359 | — | — | 39 % (n=124) | 48 % (n=226) |
| beta_dislocation_achat | +24h | 359 | — | — | 43 % (n=124) | 50 % (n=226) |
| beta_dislocation_achat | +72h | 359 | — | — | 43 % (n=124) | 47 % (n=226) |
| beta_dislocation_achat | +168h | 359 | — | — | 34 % (n=124) | 43 % (n=226) |
| beta_dislocation_achat | +336h | 359 | — | — | 28 % (n=124) | 46 % (n=226) |
| beta_dislocation_achat | +720h | 349 | — | — | 31 % (n=124) | 37 % (n=217) |
| beta_dislocation_achat | +1440h | 345 | — | — | 43 % (n=124) | 33 % (n=215) |
| beta_dislocation_achat | +2160h | 342 | — | — | 39 % (n=123) | 43 % (n=213) |
| beta_dislocation_vente | +1h | 288 | 26 % (n=76) | 35 % (n=169) | — | 32 % (n=41) |
| beta_dislocation_vente | +4h | 288 | 37 % (n=76) | 46 % (n=169) | — | 37 % (n=41) |
| beta_dislocation_vente | +12h | 288 | 46 % (n=76) | 56 % (n=169) | — | 44 % (n=41) |
| beta_dislocation_vente | +24h | 288 | 53 % (n=76) | 57 % (n=169) | — | 56 % (n=41) |
| beta_dislocation_vente | +72h | 285 | 59 % (n=76) | 49 % (n=166) | — | 63 % (n=41) |
| beta_dislocation_vente | +168h | 283 | 61 % (n=76) | 58 % (n=164) | — | 49 % (n=41) |
| beta_dislocation_vente | +336h | 278 | 66 % (n=76) | 49 % (n=162) | — | 50 % (n=38) |
| beta_dislocation_vente | +720h | 268 | 66 % (n=76) | 54 % (n=152) | — | 71 % (n=38) |
| beta_dislocation_vente | +1440h | 229 | 66 % (n=76) | 58 % (n=113) | — | 61 % (n=38) |
| beta_dislocation_vente | +2160h | 217 | 53 % (n=74) | 58 % (n=104) | — | 27 % (n=37) |
| donchian_breakdown | +1h | 4067 | 16 % (n=943) | 16 % (n=191) | 23 % (n=1954) | 38 % (n=979) |
| donchian_breakdown | +4h | 4066 | 29 % (n=943) | 29 % (n=191) | 35 % (n=1954) | 39 % (n=978) |
| donchian_breakdown | +12h | 4043 | 41 % (n=936) | 35 % (n=191) | 41 % (n=1954) | 46 % (n=962) |
| donchian_breakdown | +24h | 4042 | 43 % (n=935) | 42 % (n=191) | 45 % (n=1954) | 48 % (n=962) |
| donchian_breakdown | +72h | 4032 | 52 % (n=933) | 48 % (n=183) | 46 % (n=1954) | 52 % (n=962) |
| donchian_breakdown | +168h | 3997 | 54 % (n=900) | 61 % (n=181) | 50 % (n=1954) | 57 % (n=962) |
| donchian_breakdown | +336h | 3881 | 58 % (n=886) | 50 % (n=181) | 53 % (n=1871) | 62 % (n=943) |
| donchian_breakdown | +720h | 3660 | 55 % (n=854) | 56 % (n=162) | 51 % (n=1743) | 67 % (n=901) |
| donchian_breakdown | +1440h | 3315 | 59 % (n=748) | 66 % (n=134) | 58 % (n=1574) | 71 % (n=859) |
| donchian_breakdown | +2160h | 2931 | 68 % (n=597) | 76 % (n=123) | 71 % (n=1374) | 62 % (n=837) |
| donchian_breakout | +1h | 3817 | 26 % (n=1937) | 36 % (n=738) | 19 % (n=783) | 23 % (n=359) |
| donchian_breakout | +4h | 3817 | 36 % (n=1937) | 40 % (n=738) | 34 % (n=783) | 37 % (n=359) |
| donchian_breakout | +12h | 3817 | 40 % (n=1937) | 41 % (n=738) | 40 % (n=783) | 39 % (n=359) |
| donchian_breakout | +24h | 3805 | 44 % (n=1928) | 38 % (n=735) | 41 % (n=783) | 38 % (n=359) |
| donchian_breakout | +72h | 3768 | 45 % (n=1913) | 35 % (n=713) | 44 % (n=783) | 41 % (n=359) |
| donchian_breakout | +168h | 3696 | 43 % (n=1862) | 37 % (n=698) | 47 % (n=783) | 38 % (n=353) |
| donchian_breakout | +336h | 3614 | 41 % (n=1839) | 43 % (n=679) | 47 % (n=758) | 31 % (n=338) |
| donchian_breakout | +720h | 3401 | 41 % (n=1739) | 38 % (n=653) | 44 % (n=680) | 28 % (n=329) |
| donchian_breakout | +1440h | 3016 | 37 % (n=1561) | 34 % (n=551) | 37 % (n=588) | 24 % (n=316) |
| donchian_breakout | +2160h | 2639 | 26 % (n=1346) | 24 % (n=491) | 25 % (n=512) | 34 % (n=290) |
| ema_death_cross | +1h | 3748 | 17 % (n=1276) | 23 % (n=325) | 24 % (n=1490) | 37 % (n=657) |
| ema_death_cross | +4h | 3748 | 33 % (n=1276) | 37 % (n=325) | 38 % (n=1490) | 42 % (n=657) |
| ema_death_cross | +12h | 3726 | 42 % (n=1267) | 43 % (n=325) | 44 % (n=1490) | 46 % (n=644) |
| ema_death_cross | +24h | 3720 | 46 % (n=1261) | 42 % (n=325) | 48 % (n=1490) | 48 % (n=644) |
| ema_death_cross | +72h | 3705 | 53 % (n=1260) | 48 % (n=311) | 51 % (n=1490) | 59 % (n=644) |
| ema_death_cross | +168h | 3667 | 54 % (n=1227) | 57 % (n=308) | 51 % (n=1488) | 62 % (n=644) |
| ema_death_cross | +336h | 3583 | 56 % (n=1214) | 52 % (n=308) | 54 % (n=1439) | 64 % (n=622) |
| ema_death_cross | +720h | 3359 | 55 % (n=1157) | 57 % (n=281) | 53 % (n=1326) | 73 % (n=595) |
| ema_death_cross | +1440h | 3005 | 61 % (n=1027) | 70 % (n=225) | 63 % (n=1181) | 75 % (n=572) |
| ema_death_cross | +2160h | 2677 | 72 % (n=845) | 77 % (n=211) | 75 % (n=1060) | 68 % (n=561) |
| ema_golden_cross | +1h | 3844 | 27 % (n=1692) | 30 % (n=676) | 18 % (n=1014) | 25 % (n=462) |
| ema_golden_cross | +4h | 3844 | 36 % (n=1692) | 37 % (n=676) | 33 % (n=1014) | 35 % (n=462) |
| ema_golden_cross | +12h | 3844 | 41 % (n=1692) | 36 % (n=676) | 39 % (n=1014) | 41 % (n=462) |
| ema_golden_cross | +24h | 3839 | 43 % (n=1688) | 37 % (n=675) | 41 % (n=1014) | 39 % (n=462) |
| ema_golden_cross | +72h | 3823 | 44 % (n=1683) | 33 % (n=664) | 43 % (n=1014) | 39 % (n=462) |
| ema_golden_cross | +168h | 3777 | 44 % (n=1657) | 37 % (n=652) | 46 % (n=1014) | 35 % (n=454) |
| ema_golden_cross | +336h | 3694 | 43 % (n=1632) | 40 % (n=639) | 46 % (n=983) | 28 % (n=440) |
| ema_golden_cross | +720h | 3472 | 41 % (n=1528) | 39 % (n=620) | 47 % (n=897) | 25 % (n=427) |
| ema_golden_cross | +1440h | 3124 | 35 % (n=1371) | 34 % (n=542) | 41 % (n=797) | 20 % (n=414) |
| ema_golden_cross | +2160h | 2764 | 23 % (n=1172) | 29 % (n=502) | 30 % (n=707) | 30 % (n=383) |
| macd_cross_down | +1h | 5405 | 19 % (n=1914) | 25 % (n=606) | 30 % (n=2063) | 31 % (n=822) |
| macd_cross_down | +4h | 5405 | 36 % (n=1914) | 41 % (n=606) | 41 % (n=2063) | 43 % (n=822) |
| macd_cross_down | +12h | 5401 | 44 % (n=1912) | 47 % (n=606) | 45 % (n=2063) | 49 % (n=820) |
| macd_cross_down | +24h | 5381 | 48 % (n=1896) | 48 % (n=602) | 46 % (n=2063) | 49 % (n=820) |
| macd_cross_down | +72h | 5346 | 53 % (n=1895) | 50 % (n=568) | 48 % (n=2063) | 53 % (n=820) |
| macd_cross_down | +168h | 5281 | 56 % (n=1866) | 59 % (n=544) | 51 % (n=2052) | 57 % (n=819) |
| macd_cross_down | +336h | 5158 | 59 % (n=1843) | 53 % (n=544) | 53 % (n=1976) | 65 % (n=795) |
| macd_cross_down | +720h | 4857 | 57 % (n=1751) | 62 % (n=504) | 53 % (n=1832) | 72 % (n=770) |
| macd_cross_down | +1440h | 4348 | 65 % (n=1567) | 63 % (n=408) | 60 % (n=1631) | 74 % (n=742) |
| macd_cross_down | +2160h | 3867 | 74 % (n=1320) | 68 % (n=377) | 71 % (n=1456) | 63 % (n=714) |
| macd_cross_up | +1h | 5288 | 27 % (n=1992) | 31 % (n=658) | 16 % (n=1814) | 24 % (n=824) |
| macd_cross_up | +4h | 5288 | 36 % (n=1992) | 37 % (n=658) | 32 % (n=1814) | 36 % (n=824) |
| macd_cross_up | +12h | 5288 | 40 % (n=1992) | 41 % (n=658) | 39 % (n=1814) | 40 % (n=824) |
| macd_cross_up | +24h | 5282 | 41 % (n=1986) | 45 % (n=658) | 44 % (n=1814) | 41 % (n=824) |
| macd_cross_up | +72h | 5252 | 41 % (n=1982) | 42 % (n=632) | 46 % (n=1814) | 42 % (n=824) |
| macd_cross_up | +168h | 5183 | 41 % (n=1925) | 44 % (n=622) | 46 % (n=1814) | 38 % (n=822) |
| macd_cross_up | +336h | 5056 | 41 % (n=1898) | 46 % (n=621) | 44 % (n=1740) | 31 % (n=797) |
| macd_cross_up | +720h | 4770 | 41 % (n=1799) | 41 % (n=586) | 45 % (n=1608) | 27 % (n=777) |
| macd_cross_up | +1440h | 4257 | 36 % (n=1593) | 38 % (n=462) | 41 % (n=1458) | 21 % (n=744) |
| macd_cross_up | +2160h | 3761 | 28 % (n=1344) | 32 % (n=415) | 29 % (n=1291) | 34 % (n=711) |
| rsi_surachat_reprise | +1h | 1866 | 21 % (n=1021) | 33 % (n=437) | 31 % (n=314) | 37 % (n=94) |
| rsi_surachat_reprise | +4h | 1866 | 38 % (n=1021) | 41 % (n=437) | 40 % (n=314) | 51 % (n=94) |
| rsi_surachat_reprise | +12h | 1865 | 45 % (n=1021) | 48 % (n=437) | 46 % (n=314) | 51 % (n=93) |
| rsi_surachat_reprise | +24h | 1857 | 49 % (n=1014) | 54 % (n=436) | 50 % (n=314) | 57 % (n=93) |
| rsi_surachat_reprise | +72h | 1828 | 52 % (n=1006) | 58 % (n=415) | 51 % (n=314) | 63 % (n=93) |
| rsi_surachat_reprise | +168h | 1774 | 56 % (n=965) | 62 % (n=405) | 54 % (n=312) | 62 % (n=92) |
| rsi_surachat_reprise | +336h | 1740 | 57 % (n=954) | 56 % (n=404) | 52 % (n=299) | 70 % (n=83) |
| rsi_surachat_reprise | +720h | 1629 | 58 % (n=909) | 61 % (n=370) | 53 % (n=273) | 74 % (n=77) |
| rsi_surachat_reprise | +1440h | 1411 | 61 % (n=811) | 65 % (n=307) | 62 % (n=218) | 75 % (n=75) |
| rsi_surachat_reprise | +2160h | 1230 | 75 % (n=688) | 72 % (n=280) | 64 % (n=194) | 62 % (n=68) |
| rsi_survente_reprise | +1h | 1988 | 20 % (n=338) | 25 % (n=84) | 19 % (n=983) | 29 % (n=583) |
| rsi_survente_reprise | +4h | 1986 | 37 % (n=338) | 39 % (n=84) | 36 % (n=983) | 40 % (n=581) |
| rsi_survente_reprise | +12h | 1975 | 45 % (n=338) | 44 % (n=84) | 44 % (n=983) | 48 % (n=570) |
| rsi_survente_reprise | +24h | 1974 | 44 % (n=337) | 50 % (n=84) | 46 % (n=983) | 47 % (n=570) |
| rsi_survente_reprise | +72h | 1972 | 46 % (n=336) | 58 % (n=83) | 50 % (n=983) | 47 % (n=570) |
| rsi_survente_reprise | +168h | 1959 | 50 % (n=325) | 57 % (n=82) | 49 % (n=982) | 41 % (n=570) |
| rsi_survente_reprise | +336h | 1891 | 47 % (n=319) | 44 % (n=77) | 45 % (n=939) | 37 % (n=556) |
| rsi_survente_reprise | +720h | 1815 | 48 % (n=305) | 41 % (n=70) | 50 % (n=898) | 29 % (n=542) |
| rsi_survente_reprise | +1440h | 1663 | 43 % (n=252) | 43 % (n=58) | 43 % (n=830) | 25 % (n=523) |
| rsi_survente_reprise | +2160h | 1494 | 40 % (n=202) | 47 % (n=49) | 32 % (n=731) | 35 % (n=512) |
| stoch_surachat_reprise | +1h | 5617 | 20 % (n=2345) | 29 % (n=900) | 29 % (n=1648) | 35 % (n=724) |
| stoch_surachat_reprise | +4h | 5617 | 38 % (n=2345) | 39 % (n=900) | 42 % (n=1648) | 44 % (n=724) |
| stoch_surachat_reprise | +12h | 5615 | 48 % (n=2343) | 47 % (n=900) | 45 % (n=1648) | 47 % (n=724) |
| stoch_surachat_reprise | +24h | 5602 | 50 % (n=2333) | 53 % (n=897) | 45 % (n=1648) | 52 % (n=724) |
| stoch_surachat_reprise | +72h | 5560 | 53 % (n=2320) | 57 % (n=868) | 50 % (n=1648) | 55 % (n=724) |
| stoch_surachat_reprise | +168h | 5466 | 56 % (n=2250) | 58 % (n=850) | 52 % (n=1648) | 59 % (n=718) |
| stoch_surachat_reprise | +336h | 5342 | 58 % (n=2220) | 53 % (n=847) | 53 % (n=1579) | 67 % (n=696) |
| stoch_surachat_reprise | +720h | 5040 | 58 % (n=2119) | 59 % (n=802) | 54 % (n=1446) | 74 % (n=673) |
| stoch_surachat_reprise | +1440h | 4483 | 62 % (n=1900) | 68 % (n=660) | 59 % (n=1280) | 79 % (n=643) |
| stoch_surachat_reprise | +2160h | 3957 | 75 % (n=1609) | 73 % (n=598) | 70 % (n=1145) | 67 % (n=605) |
| stoch_survente_reprise | +1h | 5712 | 26 % (n=1862) | 35 % (n=444) | 21 % (n=2354) | 29 % (n=1052) |
| stoch_survente_reprise | +4h | 5711 | 39 % (n=1862) | 39 % (n=444) | 34 % (n=2354) | 42 % (n=1051) |
| stoch_survente_reprise | +12h | 5689 | 42 % (n=1855) | 37 % (n=444) | 42 % (n=2354) | 47 % (n=1036) |
| stoch_survente_reprise | +24h | 5683 | 43 % (n=1849) | 44 % (n=444) | 45 % (n=2354) | 48 % (n=1036) |
| stoch_survente_reprise | +72h | 5659 | 43 % (n=1848) | 43 % (n=421) | 49 % (n=2354) | 42 % (n=1036) |
| stoch_survente_reprise | +168h | 5593 | 41 % (n=1795) | 37 % (n=414) | 48 % (n=2349) | 40 % (n=1035) |
| stoch_survente_reprise | +336h | 5440 | 40 % (n=1774) | 44 % (n=413) | 45 % (n=2239) | 36 % (n=1014) |
| stoch_survente_reprise | +720h | 5134 | 41 % (n=1678) | 38 % (n=377) | 47 % (n=2094) | 29 % (n=985) |
| stoch_survente_reprise | +1440h | 4629 | 37 % (n=1477) | 30 % (n=311) | 40 % (n=1903) | 24 % (n=938) |
| stoch_survente_reprise | +2160h | 4128 | 27 % (n=1231) | 25 % (n=295) | 28 % (n=1681) | 37 % (n=921) |
| streak_rouge_fade_long | +1h | 790 | 38 % (n=177) | 41 % (n=39) | 34 % (n=351) | 37 % (n=223) |
| streak_rouge_fade_long | +4h | 790 | 44 % (n=177) | 51 % (n=39) | 36 % (n=351) | 41 % (n=223) |
| streak_rouge_fade_long | +12h | 784 | 45 % (n=175) | 44 % (n=39) | 44 % (n=351) | 52 % (n=219) |
| streak_rouge_fade_long | +24h | 783 | 44 % (n=174) | 51 % (n=39) | 42 % (n=351) | 48 % (n=219) |
| streak_rouge_fade_long | +72h | 780 | 38 % (n=174) | 50 % (n=36) | 52 % (n=351) | 42 % (n=219) |
| streak_rouge_fade_long | +168h | 777 | 37 % (n=172) | 36 % (n=36) | 48 % (n=350) | 37 % (n=219) |
| streak_rouge_fade_long | +336h | 750 | 30 % (n=170) | 44 % (n=36) | 46 % (n=328) | 32 % (n=216) |
| streak_rouge_fade_long | +720h | 729 | 35 % (n=164) | 31 % (n=36) | 43 % (n=315) | 29 % (n=214) |
| streak_rouge_fade_long | +1440h | 678 | 26 % (n=149) | 28 % (n=29) | 41 % (n=296) | 22 % (n=204) |
| streak_rouge_fade_long | +2160h | 635 | 21 % (n=131) | 15 % (n=27) | 23 % (n=273) | 30 % (n=204) |
| streak_vert_fade_short | +1h | 781 | 32 % (n=394) | 40 % (n=159) | 43 % (n=152) | 59 % (n=76) |
| streak_vert_fade_short | +4h | 781 | 45 % (n=394) | 35 % (n=159) | 49 % (n=152) | 49 % (n=76) |
| streak_vert_fade_short | +12h | 781 | 48 % (n=394) | 42 % (n=159) | 47 % (n=152) | 49 % (n=76) |
| streak_vert_fade_short | +24h | 778 | 52 % (n=391) | 48 % (n=159) | 45 % (n=152) | 53 % (n=76) |
| streak_vert_fade_short | +72h | 771 | 58 % (n=388) | 46 % (n=155) | 57 % (n=152) | 62 % (n=76) |
| streak_vert_fade_short | +168h | 747 | 58 % (n=373) | 56 % (n=149) | 51 % (n=152) | 66 % (n=73) |
| streak_vert_fade_short | +336h | 732 | 63 % (n=366) | 55 % (n=149) | 52 % (n=146) | 76 % (n=71) |
| streak_vert_fade_short | +720h | 694 | 62 % (n=349) | 57 % (n=141) | 58 % (n=133) | 79 % (n=71) |
| streak_vert_fade_short | +1440h | 627 | 68 % (n=323) | 65 % (n=111) | 66 % (n=122) | 83 % (n=71) |
| streak_vert_fade_short | +2160h | 568 | 78 % (n=291) | 74 % (n=100) | 72 % (n=109) | 75 % (n=68) |
| sweep_liquidite_long | +1h | 2811 | 39 % (n=634) | 43 % (n=190) | 26 % (n=1265) | 33 % (n=722) |
| sweep_liquidite_long | +4h | 2810 | 45 % (n=634) | 47 % (n=190) | 42 % (n=1265) | 44 % (n=721) |
| sweep_liquidite_long | +12h | 2795 | 42 % (n=629) | 45 % (n=190) | 45 % (n=1265) | 49 % (n=711) |
| sweep_liquidite_long | +24h | 2793 | 45 % (n=627) | 44 % (n=190) | 45 % (n=1265) | 47 % (n=711) |
| sweep_liquidite_long | +72h | 2782 | 41 % (n=626) | 46 % (n=180) | 50 % (n=1265) | 42 % (n=711) |
| sweep_liquidite_long | +168h | 2759 | 45 % (n=607) | 40 % (n=178) | 45 % (n=1263) | 37 % (n=711) |
| sweep_liquidite_long | +336h | 2689 | 38 % (n=599) | 42 % (n=173) | 45 % (n=1220) | 34 % (n=697) |
| sweep_liquidite_long | +720h | 2535 | 41 % (n=575) | 34 % (n=157) | 48 % (n=1135) | 28 % (n=668) |
| sweep_liquidite_long | +1440h | 2325 | 31 % (n=510) | 31 % (n=123) | 40 % (n=1045) | 22 % (n=647) |
| sweep_liquidite_long | +2160h | 2101 | 22 % (n=428) | 25 % (n=116) | 25 % (n=924) | 33 % (n=633) |
| sweep_liquidite_short | +1h | 2877 | 28 % (n=1364) | 35 % (n=572) | 37 % (n=643) | 51 % (n=298) |
| sweep_liquidite_short | +4h | 2877 | 41 % (n=1364) | 45 % (n=572) | 44 % (n=643) | 51 % (n=298) |
| sweep_liquidite_short | +12h | 2877 | 48 % (n=1364) | 47 % (n=572) | 50 % (n=643) | 56 % (n=298) |
| sweep_liquidite_short | +24h | 2863 | 49 % (n=1352) | 54 % (n=570) | 51 % (n=643) | 60 % (n=298) |
| sweep_liquidite_short | +72h | 2834 | 53 % (n=1342) | 60 % (n=551) | 52 % (n=643) | 62 % (n=298) |
| sweep_liquidite_short | +168h | 2773 | 54 % (n=1301) | 64 % (n=532) | 54 % (n=643) | 63 % (n=297) |
| sweep_liquidite_short | +336h | 2714 | 57 % (n=1282) | 59 % (n=531) | 53 % (n=631) | 71 % (n=270) |
| sweep_liquidite_short | +720h | 2569 | 58 % (n=1210) | 62 % (n=515) | 53 % (n=582) | 71 % (n=262) |
| sweep_liquidite_short | +1440h | 2304 | 66 % (n=1105) | 73 % (n=440) | 63 % (n=505) | 77 % (n=254) |
| sweep_liquidite_short | +2160h | 2053 | 78 % (n=951) | 80 % (n=415) | 73 % (n=462) | 73 % (n=225) |
| vol_spike_retournement_long | +1h | 888 | 34 % (n=330) | 53 % (n=135) | 23 % (n=247) | 37 % (n=176) |
| vol_spike_retournement_long | +4h | 888 | 39 % (n=330) | 39 % (n=135) | 42 % (n=247) | 45 % (n=176) |
| vol_spike_retournement_long | +12h | 886 | 44 % (n=330) | 36 % (n=135) | 43 % (n=247) | 49 % (n=174) |
| vol_spike_retournement_long | +24h | 883 | 45 % (n=327) | 43 % (n=135) | 48 % (n=247) | 40 % (n=174) |
| vol_spike_retournement_long | +72h | 875 | 43 % (n=326) | 39 % (n=128) | 47 % (n=247) | 40 % (n=174) |
| vol_spike_retournement_long | +168h | 864 | 46 % (n=321) | 42 % (n=122) | 43 % (n=247) | 36 % (n=174) |
| vol_spike_retournement_long | +336h | 838 | 39 % (n=317) | 34 % (n=119) | 45 % (n=238) | 37 % (n=164) |
| vol_spike_retournement_long | +720h | 792 | 36 % (n=306) | 40 % (n=114) | 46 % (n=219) | 27 % (n=153) |
| vol_spike_retournement_long | +1440h | 727 | 28 % (n=276) | 36 % (n=99) | 45 % (n=202) | 28 % (n=150) |
| vol_spike_retournement_long | +2160h | 656 | 25 % (n=247) | 38 % (n=93) | 30 % (n=177) | 37 % (n=139) |
| vol_spike_retournement_short | +1h | 1099 | 25 % (n=322) | 31 % (n=135) | 30 % (n=409) | 41 % (n=233) |
| vol_spike_retournement_short | +4h | 1099 | 41 % (n=322) | 42 % (n=135) | 33 % (n=409) | 53 % (n=233) |
| vol_spike_retournement_short | +12h | 1090 | 51 % (n=322) | 52 % (n=135) | 43 % (n=409) | 50 % (n=224) |
| vol_spike_retournement_short | +24h | 1090 | 53 % (n=322) | 59 % (n=135) | 47 % (n=409) | 50 % (n=224) |
| vol_spike_retournement_short | +72h | 1087 | 62 % (n=321) | 55 % (n=133) | 52 % (n=409) | 50 % (n=224) |
| vol_spike_retournement_short | +168h | 1070 | 55 % (n=309) | 64 % (n=128) | 56 % (n=409) | 51 % (n=224) |
| vol_spike_retournement_short | +336h | 1030 | 58 % (n=303) | 57 % (n=127) | 58 % (n=393) | 58 % (n=207) |
| vol_spike_retournement_short | +720h | 969 | 60 % (n=288) | 57 % (n=123) | 51 % (n=366) | 67 % (n=192) |
| vol_spike_retournement_short | +1440h | 865 | 63 % (n=264) | 71 % (n=82) | 61 % (n=332) | 75 % (n=187) |
| vol_spike_retournement_short | +2160h | 791 | 72 % (n=225) | 79 % (n=78) | 73 % (n=308) | 67 % (n=180) |
| volume_mort_cassure | +1h | 1312 | 33 % (n=717) | 45 % (n=264) | 23 % (n=226) | 30 % (n=105) |
| volume_mort_cassure | +4h | 1312 | 38 % (n=717) | 44 % (n=264) | 41 % (n=226) | 43 % (n=105) |
| volume_mort_cassure | +12h | 1312 | 42 % (n=717) | 42 % (n=264) | 40 % (n=226) | 48 % (n=105) |
| volume_mort_cassure | +24h | 1307 | 47 % (n=713) | 37 % (n=263) | 46 % (n=226) | 39 % (n=105) |
| volume_mort_cassure | +72h | 1294 | 48 % (n=707) | 38 % (n=256) | 41 % (n=226) | 43 % (n=105) |
| volume_mort_cassure | +168h | 1270 | 45 % (n=688) | 39 % (n=252) | 43 % (n=226) | 39 % (n=104) |
| volume_mort_cassure | +336h | 1259 | 40 % (n=683) | 40 % (n=251) | 42 % (n=222) | 29 % (n=103) |
| volume_mort_cassure | +720h | 1192 | 39 % (n=643) | 37 % (n=244) | 37 % (n=205) | 27 % (n=100) |
| volume_mort_cassure | +1440h | 1093 | 33 % (n=596) | 27 % (n=211) | 26 % (n=188) | 21 % (n=98) |
| volume_mort_cassure | +2160h | 987 | 20 % (n=529) | 16 % (n=189) | 18 % (n=176) | 28 % (n=93) |
| vwap_extreme_reprise_long | +1h | 658 | 29 % (n=49) | — | 30 % (n=219) | 31 % (n=379) |
| vwap_extreme_reprise_long | +4h | 658 | 45 % (n=49) | — | 46 % (n=219) | 36 % (n=379) |
| vwap_extreme_reprise_long | +12h | 657 | 35 % (n=49) | — | 51 % (n=219) | 39 % (n=378) |
| vwap_extreme_reprise_long | +24h | 657 | 47 % (n=49) | — | 55 % (n=219) | 42 % (n=378) |
| vwap_extreme_reprise_long | +72h | 657 | 61 % (n=49) | — | 60 % (n=219) | 49 % (n=378) |
| vwap_extreme_reprise_long | +168h | 655 | 58 % (n=48) | — | 52 % (n=219) | 47 % (n=377) |
| vwap_extreme_reprise_long | +336h | 638 | 48 % (n=48) | — | 49 % (n=213) | 42 % (n=366) |
| vwap_extreme_reprise_long | +720h | 620 | 47 % (n=45) | — | 51 % (n=199) | 38 % (n=366) |
| vwap_extreme_reprise_long | +1440h | 579 | 47 % (n=34) | — | 51 % (n=176) | 26 % (n=361) |
| vwap_extreme_reprise_long | +2160h | 529 | 39 % (n=18) | — | 41 % (n=149) | 41 % (n=354) |
| vwap_extreme_reprise_short | +1h | 507 | 30 % (n=282) | 38 % (n=143) | 39 % (n=69) | — |
| vwap_extreme_reprise_short | +4h | 507 | 44 % (n=282) | 46 % (n=143) | 39 % (n=69) | — |
| vwap_extreme_reprise_short | +12h | 507 | 55 % (n=282) | 52 % (n=143) | 41 % (n=69) | — |
| vwap_extreme_reprise_short | +24h | 505 | 54 % (n=280) | 47 % (n=143) | 46 % (n=69) | — |
| vwap_extreme_reprise_short | +72h | 497 | 60 % (n=280) | 51 % (n=135) | 54 % (n=69) | — |
| vwap_extreme_reprise_short | +168h | 483 | 62 % (n=274) | 54 % (n=128) | 52 % (n=69) | — |
| vwap_extreme_reprise_short | +336h | 478 | 60 % (n=273) | 43 % (n=127) | 45 % (n=66) | — |
| vwap_extreme_reprise_short | +720h | 449 | 63 % (n=261) | 41 % (n=117) | 55 % (n=60) | — |
| vwap_extreme_reprise_short | +1440h | 345 | 68 % (n=230) | 73 % (n=62) | 81 % (n=43) | — |
| vwap_extreme_reprise_short | +2160h | 308 | 78 % (n=200) | 81 % (n=58) | 85 % (n=40) | — |

## Risque de LIQUIDATION selon le levier (confirmés)

Part des trades dont l'excursion adverse touche ~100/levier %

| Signal | H | 3x | 5x | 10x |
|---|---|---|---|---|
| beta_dislocation_vente | +1440h | 40.2 % | 55.9 % | 69.0 % |
| ema_death_cross | +2160h | 30.4 % | 45.5 % | 69.4 % |
| funding_extreme_contre_courant | +168h | 0.0 % | 3.0 % | 20.9 % |
| funding_prix_divergence_short | +12h | 0.0 % | 0.0 % | 2.1 % |
| macd_cross_down | +2160h | 31.8 % | 46.4 % | 68.8 % |
| rsi_surachat_reprise | +2160h | 33.3 % | 46.7 % | 69.3 % |
| stoch_surachat_reprise | +2160h | 30.6 % | 45.2 % | 69.0 % |
| streak_vert_fade_short | +1440h | 22.2 % | 35.9 % | 61.2 % |
| streak_vert_fade_short | +2160h | 22.5 % | 37.1 % | 63.7 % |
| sweep_liquidite_short | +1440h | 25.1 % | 38.4 % | 63.4 % |
| sweep_liquidite_short | +2160h | 25.6 % | 39.6 % | 66.2 % |
| vol_spike_retournement_short | +1440h | 24.0 % | 37.8 % | 63.5 % |
| vol_spike_retournement_short | +2160h | 27.2 % | 42.7 % | 67.4 % |
| vwap_extreme_reprise_short | +1440h | 25.8 % | 40.0 % | 62.6 % |
| vwap_extreme_reprise_short | +2160h | 30.8 % | 41.2 % | 64.3 % |
Un % de liquidation > 0 rend la stratégie morte au levier
considéré — la médiane positive ne sauve pas un compte liquidé.

## Audit de multiplicité

- cellules signal×horizon testées : 264
- confirmés poolés : 15 (attendus par hasard ≈ 7)
- confirmés AU-DESSUS DU DRIFT (Δ blind ≥ +5 pts) : 7
- VERDICT GLOBAL : CANDIDATS AU-DESSUS DU DRIFT à examiner

Rappel : un signal « robuste » doit garder son WR hors big-moves ET
sur plusieurs régimes. Tout le reste = bruit, et on le dit.
