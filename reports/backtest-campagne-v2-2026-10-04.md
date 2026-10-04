# Campagne backtest v2 — prix + funding, régimes, robustesse
04/10/2026 01:00 UTC — 30645 combinaisons signal×symbole, 5 horizons, coûts = 8 bps de frais + slippage mesuré ×2 ≈ 28 bps RT (la convention machine ; l'étiquette « 8 bps » initiale était trompeuse).
Règle CONFIRMÉ (pré-enregistrée) : pooled N≥10 & WR≥55 % en TRAIN(70 %) puis confirmé en VAL(30 %). Audit de multiplicité en fin de rapport.

## Résultats poolés (tous symboles)

| Signal | H | N | WR | Δ blind | Médiane | Pire | Robuste hors big-moves ? | Verdict |
|---|---|---|---|---|---|---|---|---|
| bb_squeeze_break_up | +1h | 7590 | 19.4 % | -9.9 pts | -0.28 % | -30.1 % | 19 % | BRUIT |
| bb_squeeze_break_up | +4h | 7586 | 32.1 % | -5.0 pts | -0.28 % | -79.9 % | 32 % | BRUIT |
| bb_squeeze_break_up | +12h | 7532 | 38.8 % | -3.6 pts | -0.30 % | -83.3 % | 39 % | BRUIT |
| bb_squeeze_break_up | +24h | 7419 | 42.6 % | -1.4 pts | -0.37 % | -84.1 % | 43 % | BRUIT |
| bb_squeeze_break_up | +72h | 7171 | 46.0 % | -0.5 pts | -0.50 % | -88.1 % | 46 % | BRUIT |
| bb_squeeze_break_up | +168h | 6738 | 50.2 % | +5.0 pts | +0.05 % | -90.5 % | 50 % | BRUIT |
| bb_squeeze_break_up | +336h | 5897 | 55.1 % | +13.7 pts | +1.55 % | -93.8 % | 55 % | BRUIT |
| bb_squeeze_break_up | +720h | 4119 | 56.6 % | +17.7 pts | +2.87 % | -97.9 % | 57 % | BRUIT |
| bb_squeeze_break_up | +1440h | 1199 | 43.9 % | -2.7 pts | -3.59 % | -72.2 % | 44 % | BRUIT |
| bb_squeeze_break_up | +2160h | 1167 | 40.7 % | -13.1 pts | -7.74 % | -77.1 % | 41 % | BRUIT |
| beta_dislocation_achat | +1h | 485 | 31.1 % | +1.8 pts | -0.28 % | -14.6 % | 31 % | BRUIT |
| beta_dislocation_achat | +4h | 485 | 37.1 % | -0.1 pts | -0.28 % | -11.2 % | 37 % | BRUIT |
| beta_dislocation_achat | +12h | 440 | 50.2 % | +7.9 pts | +0.02 % | -33.8 % | 51 % | BRUIT |
| beta_dislocation_achat | +24h | 440 | 58.4 % | +14.3 pts | +0.65 % | -26.5 % | 59 % | BRUIT |
| beta_dislocation_achat | +72h | 440 | 54.3 % | +7.8 pts | +0.55 % | -43.0 % | 55 % | BRUIT |
| beta_dislocation_achat | +168h | 440 | 50.0 % | +4.8 pts | +0.10 % | -71.2 % | 50 % | BRUIT |
| beta_dislocation_achat | +336h | 440 | 49.8 % | +8.4 pts | -0.25 % | -80.5 % | 50 % | BRUIT |
| beta_dislocation_achat | +720h | 295 | 54.2 % | +15.3 pts | +4.03 % | -86.5 % | 55 % | BRUIT |
| beta_dislocation_achat | +1440h | 134 | 42.5 % | -4.1 pts | -6.41 % | -60.1 % | 43 % | BRUIT |
| beta_dislocation_achat | +2160h | 134 | 37.3 % | -16.5 pts | -11.86 % | -63.9 % | 35 % | BRUIT |
| beta_dislocation_vente | +1h | 1225 | 28.0 % | -1.3 pts | -0.28 % | -21.3 % | 28 % | BRUIT |
| beta_dislocation_vente | +4h | 1225 | 40.0 % | +2.8 pts | -0.28 % | -55.5 % | 40 % | BRUIT |
| beta_dislocation_vente | +12h | 1225 | 38.6 % | -3.7 pts | -0.70 % | -86.1 % | 39 % | BRUIT |
| beta_dislocation_vente | +24h | 1204 | 40.8 % | -3.3 pts | -1.11 % | -134.0 % | 41 % | BRUIT |
| beta_dislocation_vente | +72h | 1180 | 41.6 % | -4.9 pts | -1.84 % | -148.5 % | 42 % | BRUIT |
| beta_dislocation_vente | +168h | 1180 | 44.6 % | -0.6 pts | -1.58 % | -184.2 % | 45 % | BRUIT |
| beta_dislocation_vente | +336h | 1055 | 43.5 % | +2.1 pts | -2.10 % | -349.7 % | 44 % | BRUIT |
| beta_dislocation_vente | +720h | 729 | 37.2 % | -1.7 pts | -6.86 % | -662.7 % | 37 % | BRUIT |
| beta_dislocation_vente | +1440h | 124 | 57.3 % | +10.7 pts | +4.87 % | -217.6 % | 59 % | BRUIT |
| beta_dislocation_vente | +2160h | 124 | 63.7 % | +9.9 pts | +15.02 % | -283.4 % | 66 % | CONFIRMÉ |
| climax_top_short | +1h | 391 | 18.9 % | -10.4 pts | -0.28 % | -7.2 % | 19 % | BRUIT |
| climax_top_short | +4h | 391 | 34.5 % | -2.7 pts | -0.28 % | -30.1 % | 35 % | BRUIT |
| climax_top_short | +12h | 385 | 41.3 % | -1.1 pts | -0.26 % | -36.4 % | 41 % | BRUIT |
| climax_top_short | +24h | 382 | 46.3 % | +2.3 pts | -0.20 % | -101.2 % | 46 % | BRUIT |
| climax_top_short | +72h | 371 | 49.6 % | +3.1 pts | -0.09 % | -221.2 % | 50 % | BRUIT |
| climax_top_short | +168h | 360 | 47.5 % | +2.3 pts | -0.47 % | -232.2 % | 48 % | BRUIT |
| climax_top_short | +336h | 298 | 37.2 % | -4.2 pts | -2.63 % | -379.1 % | 37 % | BRUIT |
| climax_top_short | +720h | 187 | 34.8 % | -4.1 pts | -5.73 % | -213.9 % | 35 % | BRUIT |
| donchian_breakdown | +1h | 15694 | 18.4 % | -10.9 pts | -0.28 % | -28.7 % | 18 % | BRUIT |
| donchian_breakdown | +4h | 15682 | 32.1 % | -5.1 pts | -0.28 % | -161.5 % | 32 % | BRUIT |
| donchian_breakdown | +12h | 15419 | 39.3 % | -3.0 pts | -0.28 % | -207.7 % | 39 % | BRUIT |
| donchian_breakdown | +24h | 15367 | 42.3 % | -1.8 pts | -0.42 % | -194.0 % | 42 % | BRUIT |
| donchian_breakdown | +72h | 14901 | 44.3 % | -2.2 pts | -0.64 % | -357.4 % | 44 % | BRUIT |
| donchian_breakdown | +168h | 13929 | 43.6 % | -1.6 pts | -1.27 % | -472.1 % | 44 % | BRUIT |
| donchian_breakdown | +336h | 12595 | 39.7 % | -1.7 pts | -3.15 % | -481.4 % | 40 % | BRUIT |
| donchian_breakdown | +720h | 9046 | 38.0 % | -0.9 pts | -6.00 % | -634.7 % | 38 % | BRUIT |
| donchian_breakdown | +1440h | 2708 | 48.6 % | +2.0 pts | -0.85 % | -1668.0 % | 49 % | BRUIT |
| donchian_breakdown | +2160h | 2267 | 53.3 % | -0.5 pts | +2.75 % | -526.2 % | 54 % | BRUIT |
| donchian_breakout | +1h | 16402 | 21.0 % | -8.3 pts | -0.28 % | -36.0 % | 21 % | BRUIT |
| donchian_breakout | +4h | 16397 | 32.7 % | -4.5 pts | -0.28 % | -79.9 % | 33 % | BRUIT |
| donchian_breakout | +12h | 16292 | 39.6 % | -2.8 pts | -0.31 % | -83.3 % | 40 % | BRUIT |
| donchian_breakout | +24h | 16103 | 43.3 % | -0.7 pts | -0.39 % | -86.8 % | 43 % | BRUIT |
| donchian_breakout | +72h | 15665 | 47.4 % | +0.8 pts | -0.30 % | -89.8 % | 47 % | BRUIT |
| donchian_breakout | +168h | 14854 | 51.1 % | +5.9 pts | +0.21 % | -91.1 % | 51 % | BRUIT |
| donchian_breakout | +336h | 13001 | 55.2 % | +13.8 pts | +1.65 % | -97.9 % | 55 % | BRUIT |
| donchian_breakout | +720h | 9236 | 59.1 % | +20.2 pts | +4.01 % | -99.7 % | 59 % | CONFIRMÉ |
| donchian_breakout | +1440h | 2755 | 50.5 % | +3.9 pts | +0.36 % | -95.7 % | 50 % | BRUIT |
| donchian_breakout | +2160h | 2291 | 44.3 % | -9.5 pts | -4.91 % | -76.5 % | 44 % | BRUIT |
| ema_death_cross | +1h | 14810 | 17.9 % | -11.4 pts | -0.28 % | -28.7 % | 18 % | BRUIT |
| ema_death_cross | +4h | 14771 | 32.8 % | -4.4 pts | -0.28 % | -90.2 % | 33 % | BRUIT |
| ema_death_cross | +12h | 14562 | 40.6 % | -1.8 pts | -0.28 % | -159.4 % | 41 % | BRUIT |
| ema_death_cross | +24h | 14495 | 43.1 % | -1.0 pts | -0.35 % | -214.1 % | 43 % | BRUIT |
| ema_death_cross | +72h | 14005 | 46.0 % | -0.6 pts | -0.45 % | -608.9 % | 46 % | BRUIT |
| ema_death_cross | +168h | 13129 | 44.8 % | -0.3 pts | -1.02 % | -532.6 % | 45 % | BRUIT |
| ema_death_cross | +336h | 11700 | 41.6 % | +0.2 pts | -2.49 % | -693.7 % | 42 % | BRUIT |
| ema_death_cross | +720h | 8795 | 37.6 % | -1.3 pts | -5.81 % | -664.3 % | 38 % | BRUIT |
| ema_death_cross | +1440h | 3035 | 45.4 % | -1.2 pts | -3.10 % | -1177.3 % | 45 % | BRUIT |
| ema_death_cross | +2160h | 2262 | 54.1 % | +0.3 pts | +3.51 % | -502.7 % | 54 % | BRUIT |
| ema_golden_cross | +1h | 14580 | 19.0 % | -10.3 pts | -0.28 % | -39.7 % | 19 % | BRUIT |
| ema_golden_cross | +4h | 14569 | 31.9 % | -5.3 pts | -0.28 % | -79.9 % | 32 % | BRUIT |
| ema_golden_cross | +12h | 14509 | 39.1 % | -3.3 pts | -0.31 % | -83.3 % | 39 % | BRUIT |
| ema_golden_cross | +24h | 14333 | 43.6 % | -0.5 pts | -0.33 % | -84.1 % | 44 % | BRUIT |
| ema_golden_cross | +72h | 13906 | 47.5 % | +0.9 pts | -0.29 % | -88.1 % | 47 % | BRUIT |
| ema_golden_cross | +168h | 13116 | 51.8 % | +6.6 pts | +0.33 % | -90.6 % | 52 % | BRUIT |
| ema_golden_cross | +336h | 11752 | 55.9 % | +14.5 pts | +1.80 % | -96.7 % | 56 % | BRUIT |
| ema_golden_cross | +720h | 8685 | 59.8 % | +20.9 pts | +4.55 % | -100.8 % | 60 % | CONFIRMÉ |
| ema_golden_cross | +1440h | 3013 | 53.0 % | +6.4 pts | +2.13 % | -104.4 % | 53 % | BRUIT |
| ema_golden_cross | +2160h | 2271 | 44.8 % | -9.0 pts | -4.28 % | -76.8 % | 45 % | BRUIT |
| failed_ath_breakout_short | +1h | 2073 | 27.9 % | -1.4 pts | -0.28 % | -26.2 % | 28 % | BRUIT |
| failed_ath_breakout_short | +4h | 2071 | 44.2 % | +7.1 pts | -0.25 % | -36.5 % | 44 % | BRUIT |
| failed_ath_breakout_short | +12h | 2053 | 47.8 % | +5.5 pts | -0.13 % | -99.5 % | 48 % | BRUIT |
| failed_ath_breakout_short | +24h | 2044 | 53.8 % | +9.8 pts | +0.44 % | -206.1 % | 54 % | BRUIT |
| failed_ath_breakout_short | +72h | 2015 | 52.3 % | +5.7 pts | +0.33 % | -608.9 % | 52 % | BRUIT |
| failed_ath_breakout_short | +168h | 1909 | 51.2 % | +6.1 pts | +0.43 % | -368.2 % | 51 % | BRUIT |
| failed_ath_breakout_short | +336h | 1611 | 47.7 % | +6.3 pts | -0.68 % | -523.1 % | 48 % | BRUIT |
| failed_ath_breakout_short | +720h | 1319 | 40.3 % | +1.4 pts | -3.95 % | -429.9 % | 40 % | BRUIT |
| failed_ath_breakout_short | +1440h | 280 | 37.9 % | -8.7 pts | -9.40 % | -465.2 % | 38 % | BRUIT |
| failed_ath_breakout_short | +2160h | 48 | 83.3 % | +29.5 pts | +24.96 % | -25.5 % | 83 % | CONFIRMÉ |
| funding_accel_momentum | +1h | 18032 | 16.1 % | -13.1 pts | -0.28 % | -21.2 % | 16 % | BRUIT |
| funding_accel_momentum | +4h | 18014 | 30.5 % | -6.6 pts | -0.28 % | -53.5 % | 31 % | BRUIT |
| funding_accel_momentum | +12h | 17974 | 36.5 % | -5.9 pts | -0.41 % | -63.5 % | 36 % | BRUIT |
| funding_accel_momentum | +24h | 17876 | 48.8 % | +4.7 pts | -0.08 % | -84.5 % | 49 % | BRUIT |
| funding_accel_momentum | +72h | 17502 | 54.6 % | +8.1 pts | +0.50 % | -88.6 % | 55 % | BRUIT |
| funding_accel_momentum | +168h | 16829 | 54.2 % | +9.0 pts | +0.96 % | -89.0 % | 54 % | BRUIT |
| funding_accel_momentum | +336h | 15598 | 57.2 % | +15.8 pts | +2.02 % | -97.4 % | 57 % | CONFIRMÉ |
| funding_accel_momentum | +720h | 12189 | 68.8 % | +30.0 pts | +7.62 % | -99.3 % | 69 % | CONFIRMÉ |
| funding_accel_momentum | +1440h | 5596 | 77.5 % | +30.9 pts | +21.82 % | -73.6 % | 77 % | BRUIT |
| funding_accel_momentum | +2160h | 563 | 25.9 % | -27.9 pts | -19.94 % | -53.3 % | 26 % | BRUIT |
| funding_div_miroir_long | +1h | 19376 | 24.2 % | -5.1 pts | -0.28 % | -30.1 % | 24 % | BRUIT |
| funding_div_miroir_long | +4h | 19328 | 36.9 % | -0.3 pts | -0.29 % | -79.9 % | 37 % | BRUIT |
| funding_div_miroir_long | +12h | 19244 | 42.5 % | +0.2 pts | -0.43 % | -85.8 % | 43 % | BRUIT |
| funding_div_miroir_long | +24h | 19098 | 43.4 % | -0.7 pts | -0.78 % | -87.4 % | 43 % | BRUIT |
| funding_div_miroir_long | +72h | 18567 | 45.5 % | -1.0 pts | -0.86 % | -89.8 % | 45 % | BRUIT |
| funding_div_miroir_long | +168h | 17695 | 47.7 % | +2.6 pts | -0.59 % | -90.8 % | 48 % | BRUIT |
| funding_div_miroir_long | +336h | 15204 | 53.1 % | +11.7 pts | +1.16 % | -98.2 % | 53 % | BRUIT |
| funding_div_miroir_long | +720h | 10109 | 55.7 % | +16.8 pts | +3.58 % | -99.8 % | 56 % | BRUIT |
| funding_div_miroir_long | +1440h | 798 | 46.6 % | +0.0 pts | -1.78 % | -60.3 % | 47 % | BRUIT |
| funding_div_miroir_long | +2160h | 568 | 28.9 % | -24.9 pts | -18.18 % | -49.8 % | 28 % | BRUIT |
| funding_div_plus_vwap_short | +1h | 2192 | 36.1 % | +6.8 pts | -0.28 % | -25.7 % | 36 % | BRUIT |
| funding_div_plus_vwap_short | +4h | 2188 | 50.3 % | +13.1 pts | +0.03 % | -55.5 % | 50 % | BRUIT |
| funding_div_plus_vwap_short | +12h | 2180 | 55.8 % | +13.5 pts | +0.47 % | -65.1 % | 56 % | BRUIT |
| funding_div_plus_vwap_short | +24h | 2164 | 54.8 % | +10.7 pts | +0.74 % | -175.2 % | 55 % | BRUIT |
| funding_div_plus_vwap_short | +72h | 2128 | 57.3 % | +10.8 pts | +1.67 % | -389.0 % | 57 % | CONFIRMÉ |
| funding_div_plus_vwap_short | +168h | 1968 | 58.3 % | +13.2 pts | +2.09 % | -313.5 % | 58 % | CONFIRMÉ |
| funding_div_plus_vwap_short | +336h | 1617 | 50.4 % | +9.0 pts | +0.27 % | -259.9 % | 50 % | BRUIT |
| funding_div_plus_vwap_short | +720h | 1047 | 38.5 % | -0.4 pts | -7.79 % | -563.1 % | 38 % | BRUIT |
| funding_div_plus_vwap_short | +1440h | 96 | 75.0 % | +28.4 pts | +20.89 % | -34.5 % | 75 % | CONFIRMÉ |
| funding_div_plus_vwap_short | +2160h | 92 | 87.0 % | +33.1 pts | +25.71 % | -36.0 % | 87 % | CONFIRMÉ |
| funding_extreme_contre_courant | +1h | 16514 | 16.8 % | -12.5 pts | -0.28 % | -33.6 % | 17 % | BRUIT |
| funding_extreme_contre_courant | +4h | 16483 | 31.4 % | -5.8 pts | -0.28 % | -99.3 % | 31 % | BRUIT |
| funding_extreme_contre_courant | +12h | 16442 | 40.0 % | -2.4 pts | -0.30 % | -275.4 % | 40 % | BRUIT |
| funding_extreme_contre_courant | +24h | 16337 | 43.7 % | -0.4 pts | -0.37 % | -292.1 % | 44 % | BRUIT |
| funding_extreme_contre_courant | +72h | 15863 | 47.8 % | +1.3 pts | -0.27 % | -471.1 % | 48 % | BRUIT |
| funding_extreme_contre_courant | +168h | 14826 | 46.8 % | +1.6 pts | -0.68 % | -571.4 % | 47 % | BRUIT |
| funding_extreme_contre_courant | +336h | 12779 | 48.6 % | +7.1 pts | -0.60 % | -479.2 % | 49 % | BRUIT |
| funding_extreme_contre_courant | +720h | 8653 | 60.1 % | +21.3 pts | +4.06 % | -631.0 % | 60 % | CONFIRMÉ |
| funding_extreme_contre_courant | +1440h | 3770 | 62.3 % | +15.7 pts | +6.06 % | -217.1 % | 62 % | BRUIT |
| funding_extreme_contre_courant | +2160h | 235 | 30.6 % | -23.2 pts | -17.46 % | -44.5 % | 29 % | BRUIT |
| funding_extreme_plus_div_short | +1h | 22 | 72.7 % | +43.4 pts | +0.07 % | -0.9 % | 73 % | BRUIT |
| funding_extreme_plus_div_short | +4h | 22 | 90.9 % | +53.7 pts | +2.39 % | -1.2 % | 91 % | CONFIRMÉ |
| funding_extreme_plus_div_short | +12h | 22 | 63.6 % | +21.3 pts | +0.67 % | -8.2 % | 64 % | CONFIRMÉ |
| funding_extreme_plus_div_short | +24h | 22 | 45.5 % | +1.4 pts | -4.02 % | -175.2 % | 45 % | BRUIT |
| funding_extreme_plus_div_short | +72h | 22 | 36.4 % | -10.2 pts | -10.67 % | -389.0 % | 36 % | BRUIT |
| funding_extreme_plus_div_short | +168h | 22 | 36.4 % | -8.8 pts | -14.69 % | -313.5 % | 36 % | BRUIT |
| funding_extreme_plus_div_short | +336h | 20 | 40.0 % | -1.4 pts | -11.21 % | -49.7 % | 40 % | BRUIT |
| funding_extreme_plus_div_short | +720h | 16 | 0.0 % | -38.9 pts | -58.38 % | -294.4 % | 0 % | BRUIT |
| funding_flip_neg | +1h | 9297 | 11.3 % | -18.0 pts | -0.28 % | -41.9 % | 11 % | BRUIT |
| funding_flip_neg | +4h | 9283 | 28.0 % | -9.2 pts | -0.28 % | -45.6 % | 28 % | BRUIT |
| funding_flip_neg | +12h | 9270 | 48.0 % | +5.6 pts | -0.10 % | -174.1 % | 48 % | BRUIT |
| funding_flip_neg | +24h | 9231 | 38.2 % | -5.9 pts | -0.55 % | -209.1 % | 38 % | BRUIT |
| funding_flip_neg | +72h | 9109 | 35.8 % | -10.8 pts | -1.33 % | -448.4 % | 36 % | BRUIT |
| funding_flip_neg | +168h | 8917 | 36.2 % | -8.9 pts | -2.85 % | -387.8 % | 36 % | BRUIT |
| funding_flip_neg | +336h | 8537 | 34.0 % | -7.5 pts | -4.64 % | -390.6 % | 34 % | BRUIT |
| funding_flip_neg | +720h | 7018 | 20.8 % | -18.1 pts | -10.71 % | -518.4 % | 21 % | BRUIT |
| funding_flip_neg | +1440h | 3797 | 17.5 % | -29.1 pts | -26.07 % | -217.1 % | 17 % | BRUIT |
| funding_flip_neg | +2160h | 368 | 75.0 % | +21.2 pts | +18.58 % | -75.8 % | 76 % | CONFIRMÉ |
| funding_flip_pos | +1h | 7898 | 15.8 % | -13.5 pts | -0.28 % | -24.5 % | 16 % | BRUIT |
| funding_flip_pos | +4h | 7898 | 28.3 % | -8.9 pts | -0.28 % | -60.3 % | 28 % | BRUIT |
| funding_flip_pos | +12h | 7888 | 34.5 % | -7.8 pts | -0.46 % | -58.3 % | 35 % | BRUIT |
| funding_flip_pos | +24h | 7863 | 49.0 % | +4.9 pts | -0.08 % | -61.8 % | 49 % | BRUIT |
| funding_flip_pos | +72h | 7780 | 56.4 % | +9.9 pts | +0.56 % | -70.0 % | 56 % | BRUIT |
| funding_flip_pos | +168h | 7605 | 56.6 % | +11.4 pts | +1.63 % | -87.5 % | 57 % | BRUIT |
| funding_flip_pos | +336h | 7294 | 61.5 % | +20.1 pts | +3.33 % | -95.7 % | 62 % | CONFIRMÉ |
| funding_flip_pos | +720h | 5909 | 77.7 % | +38.8 pts | +11.20 % | -97.4 % | 78 % | CONFIRMÉ |
| funding_flip_pos | +1440h | 2932 | 82.4 % | +35.8 pts | +29.92 % | -60.8 % | 82 % | BRUIT |
| funding_flip_pos | +2160h | 368 | 25.0 % | -28.8 pts | -18.77 % | -48.3 % | 25 % | BRUIT |
| funding_prix_divergence_long | +1h | 19376 | 24.2 % | -5.1 pts | -0.28 % | -30.1 % | 24 % | BRUIT |
| funding_prix_divergence_long | +4h | 19328 | 36.9 % | -0.3 pts | -0.29 % | -79.9 % | 37 % | BRUIT |
| funding_prix_divergence_long | +12h | 19244 | 42.5 % | +0.2 pts | -0.43 % | -85.8 % | 43 % | BRUIT |
| funding_prix_divergence_long | +24h | 19098 | 43.4 % | -0.7 pts | -0.78 % | -87.4 % | 43 % | BRUIT |
| funding_prix_divergence_long | +72h | 18567 | 45.5 % | -1.0 pts | -0.86 % | -89.8 % | 45 % | BRUIT |
| funding_prix_divergence_long | +168h | 17695 | 47.7 % | +2.6 pts | -0.59 % | -90.8 % | 48 % | BRUIT |
| funding_prix_divergence_long | +336h | 15204 | 53.1 % | +11.7 pts | +1.16 % | -98.2 % | 53 % | BRUIT |
| funding_prix_divergence_long | +720h | 10109 | 55.7 % | +16.8 pts | +3.58 % | -99.8 % | 56 % | BRUIT |
| funding_prix_divergence_long | +1440h | 798 | 46.6 % | +0.0 pts | -1.78 % | -60.3 % | 47 % | BRUIT |
| funding_prix_divergence_long | +2160h | 568 | 28.9 % | -24.9 pts | -18.18 % | -49.8 % | 28 % | BRUIT |
| funding_prix_divergence_short | +1h | 19342 | 24.7 % | -4.6 pts | -0.28 % | -33.3 % | 25 % | BRUIT |
| funding_prix_divergence_short | +4h | 19314 | 39.4 % | +2.2 pts | -0.28 % | -77.7 % | 39 % | BRUIT |
| funding_prix_divergence_short | +12h | 19188 | 45.8 % | +3.5 pts | -0.25 % | -109.1 % | 46 % | BRUIT |
| funding_prix_divergence_short | +24h | 19085 | 46.2 % | +2.1 pts | -0.32 % | -175.2 % | 46 % | BRUIT |
| funding_prix_divergence_short | +72h | 18665 | 45.3 % | -1.2 pts | -0.86 % | -389.0 % | 45 % | BRUIT |
| funding_prix_divergence_short | +168h | 17365 | 45.6 % | +0.5 pts | -1.14 % | -461.5 % | 46 % | BRUIT |
| funding_prix_divergence_short | +336h | 15629 | 41.2 % | -0.2 pts | -4.30 % | -632.0 % | 41 % | BRUIT |
| funding_prix_divergence_short | +720h | 10466 | 41.0 % | +2.1 pts | -6.41 % | -657.3 % | 41 % | BRUIT |
| funding_prix_divergence_short | +1440h | 932 | 58.6 % | +12.0 pts | +3.35 % | -616.0 % | 58 % | BRUIT |
| funding_prix_divergence_short | +2160h | 736 | 70.7 % | +16.8 pts | +17.22 % | -70.7 % | 72 % | BRUIT |
| macd_cross_down | +1h | 21579 | 18.2 % | -11.1 pts | -0.28 % | -54.1 % | 18 % | BRUIT |
| macd_cross_down | +4h | 21554 | 32.3 % | -4.9 pts | -0.28 % | -90.2 % | 32 % | BRUIT |
| macd_cross_down | +12h | 21306 | 40.0 % | -2.3 pts | -0.28 % | -238.0 % | 40 % | BRUIT |
| macd_cross_down | +24h | 21192 | 43.4 % | -0.7 pts | -0.29 % | -303.3 % | 43 % | BRUIT |
| macd_cross_down | +72h | 20551 | 46.4 % | -0.1 pts | -0.40 % | -608.9 % | 46 % | BRUIT |
| macd_cross_down | +168h | 19369 | 45.3 % | +0.1 pts | -0.98 % | -581.1 % | 45 % | BRUIT |
| macd_cross_down | +336h | 17303 | 41.2 % | -0.2 pts | -2.61 % | -618.6 % | 41 % | BRUIT |
| macd_cross_down | +720h | 12614 | 38.4 % | -0.5 pts | -5.37 % | -974.1 % | 38 % | BRUIT |
| macd_cross_down | +1440h | 4207 | 46.2 % | -0.4 pts | -2.74 % | -1149.6 % | 46 % | BRUIT |
| macd_cross_down | +2160h | 3263 | 53.2 % | -0.6 pts | +3.02 % | -485.4 % | 53 % | BRUIT |
| macd_cross_up | +1h | 21227 | 18.4 % | -10.9 pts | -0.28 % | -32.2 % | 18 % | BRUIT |
| macd_cross_up | +4h | 21214 | 31.8 % | -5.3 pts | -0.28 % | -48.8 % | 32 % | BRUIT |
| macd_cross_up | +12h | 21146 | 41.4 % | -1.0 pts | -0.29 % | -63.0 % | 41 % | BRUIT |
| macd_cross_up | +24h | 20990 | 45.1 % | +1.1 pts | -0.28 % | -80.0 % | 45 % | BRUIT |
| macd_cross_up | +72h | 20321 | 48.1 % | +1.6 pts | -0.25 % | -82.2 % | 48 % | BRUIT |
| macd_cross_up | +168h | 19179 | 52.1 % | +6.9 pts | +0.44 % | -90.5 % | 52 % | BRUIT |
| macd_cross_up | +336h | 17072 | 57.1 % | +15.6 pts | +2.04 % | -96.6 % | 57 % | BRUIT |
| macd_cross_up | +720h | 12471 | 60.0 % | +21.1 pts | +4.66 % | -100.8 % | 60 % | CONFIRMÉ |
| macd_cross_up | +1440h | 4163 | 53.2 % | +6.6 pts | +2.51 % | -104.4 % | 53 % | BRUIT |
| macd_cross_up | +2160h | 3211 | 46.7 % | -7.1 pts | -3.08 % | -77.1 % | 47 % | BRUIT |
| precision_quad | +1h | 775 | 40.5 % | +11.2 pts | -0.28 % | -26.4 % | 41 % | BRUIT |
| precision_quad | +4h | 775 | 55.0 % | +17.8 pts | +0.32 % | -55.5 % | 55 % | BRUIT |
| precision_quad | +12h | 775 | 52.3 % | +9.9 pts | +0.21 % | -78.7 % | 52 % | BRUIT |
| precision_quad | +24h | 771 | 51.8 % | +7.7 pts | +0.27 % | -87.5 % | 52 % | BRUIT |
| precision_quad | +72h | 757 | 59.0 % | +12.5 pts | +1.97 % | -106.5 % | 59 % | CONFIRMÉ |
| precision_quad | +168h | 707 | 61.8 % | +16.6 pts | +2.87 % | -134.9 % | 62 % | CONFIRMÉ |
| precision_quad | +336h | 597 | 51.4 % | +10.0 pts | +0.49 % | -156.6 % | 51 % | BRUIT |
| precision_quad | +720h | 429 | 44.1 % | +5.2 pts | -3.36 % | -563.1 % | 44 % | BRUIT |
| precision_quad | +1440h | 52 | 76.9 % | +30.3 pts | +20.89 % | -13.9 % | 77 % | CONFIRMÉ |
| precision_quad | +2160h | 52 | 92.3 % | +38.5 pts | +27.62 % | -0.7 % | 92 % | CONFIRMÉ |
| precision_rsi75 | +1h | 1429 | 36.5 % | +7.2 pts | -0.28 % | -25.7 % | 37 % | BRUIT |
| precision_rsi75 | +4h | 1429 | 50.4 % | +13.2 pts | +0.04 % | -55.5 % | 50 % | BRUIT |
| precision_rsi75 | +12h | 1425 | 53.8 % | +11.5 pts | +0.29 % | -78.7 % | 54 % | BRUIT |
| precision_rsi75 | +24h | 1421 | 52.6 % | +8.5 pts | +0.38 % | -87.5 % | 53 % | BRUIT |
| precision_rsi75 | +72h | 1395 | 61.0 % | +14.5 pts | +2.45 % | -299.4 % | 61 % | CONFIRMÉ |
| precision_rsi75 | +168h | 1313 | 60.4 % | +15.2 pts | +2.81 % | -303.2 % | 60 % | CONFIRMÉ |
| precision_rsi75 | +336h | 1099 | 50.0 % | +8.5 pts | -0.14 % | -241.4 % | 50 % | BRUIT |
| precision_rsi75 | +720h | 749 | 42.9 % | +4.0 pts | -3.89 % | -563.1 % | 43 % | BRUIT |
| precision_rsi75 | +1440h | 80 | 70.0 % | +23.4 pts | +23.91 % | -34.5 % | 70 % | BRUIT |
| precision_rsi75 | +2160h | 76 | 84.2 % | +30.4 pts | +25.71 % | -36.0 % | 84 % | CONFIRMÉ |
| precision_volume | +1h | 1057 | 40.7 % | +11.4 pts | -0.28 % | -26.4 % | 41 % | BRUIT |
| precision_volume | +4h | 1057 | 52.0 % | +14.9 pts | +0.12 % | -55.5 % | 52 % | BRUIT |
| precision_volume | +12h | 1053 | 54.0 % | +11.7 pts | +0.40 % | -90.4 % | 54 % | BRUIT |
| precision_volume | +24h | 1045 | 50.0 % | +6.0 pts | +0.00 % | -88.1 % | 50 % | BRUIT |
| precision_volume | +72h | 1029 | 56.7 % | +10.1 pts | +1.22 % | -204.1 % | 57 % | CONFIRMÉ |
| precision_volume | +168h | 949 | 59.7 % | +14.6 pts | +2.29 % | -314.4 % | 60 % | CONFIRMÉ |
| precision_volume | +336h | 767 | 51.5 % | +10.1 pts | +0.42 % | -521.7 % | 51 % | BRUIT |
| precision_volume | +720h | 521 | 42.4 % | +3.5 pts | -4.33 % | -563.1 % | 42 % | BRUIT |
| precision_volume | +1440h | 56 | 78.6 % | +32.0 pts | +20.89 % | -13.9 % | 79 % | CONFIRMÉ |
| precision_volume | +2160h | 56 | 92.9 % | +39.0 pts | +27.62 % | -0.7 % | 93 % | CONFIRMÉ |
| rsi_surachat_reprise | +1h | 9744 | 18.8 % | -10.5 pts | -0.28 % | -30.2 % | 19 % | BRUIT |
| rsi_surachat_reprise | +4h | 9741 | 33.8 % | -3.3 pts | -0.28 % | -104.5 % | 34 % | BRUIT |
| rsi_surachat_reprise | +12h | 9630 | 41.4 % | -0.9 pts | -0.28 % | -99.5 % | 41 % | BRUIT |
| rsi_surachat_reprise | +24h | 9574 | 46.4 % | +2.4 pts | -0.25 % | -206.1 % | 46 % | BRUIT |
| rsi_surachat_reprise | +72h | 9355 | 47.3 % | +0.7 pts | -0.31 % | -558.1 % | 47 % | BRUIT |
| rsi_surachat_reprise | +168h | 8902 | 46.5 % | +1.4 pts | -0.66 % | -353.2 % | 47 % | BRUIT |
| rsi_surachat_reprise | +336h | 7670 | 42.7 % | +1.3 pts | -2.01 % | -523.1 % | 43 % | BRUIT |
| rsi_surachat_reprise | +720h | 5459 | 39.0 % | +0.1 pts | -4.67 % | -607.7 % | 39 % | BRUIT |
| rsi_surachat_reprise | +1440h | 1436 | 47.8 % | +1.2 pts | -2.18 % | -1340.1 % | 48 % | BRUIT |
| rsi_surachat_reprise | +2160h | 1062 | 54.8 % | +1.0 pts | +4.66 % | -444.1 % | 55 % | BRUIT |
| rsi_survente_reprise | +1h | 8423 | 15.1 % | -14.1 pts | -0.28 % | -23.1 % | 15 % | BRUIT |
| rsi_survente_reprise | +4h | 8356 | 30.8 % | -6.4 pts | -0.28 % | -53.1 % | 31 % | BRUIT |
| rsi_survente_reprise | +12h | 8304 | 39.7 % | -2.7 pts | -0.29 % | -60.2 % | 40 % | BRUIT |
| rsi_survente_reprise | +24h | 8269 | 47.0 % | +3.0 pts | -0.20 % | -64.0 % | 47 % | BRUIT |
| rsi_survente_reprise | +72h | 8102 | 51.4 % | +4.9 pts | +0.19 % | -79.9 % | 51 % | BRUIT |
| rsi_survente_reprise | +168h | 7574 | 56.1 % | +11.0 pts | +1.15 % | -87.0 % | 56 % | BRUIT |
| rsi_survente_reprise | +336h | 6960 | 59.2 % | +17.7 pts | +2.97 % | -95.0 % | 59 % | CONFIRMÉ |
| rsi_survente_reprise | +720h | 5060 | 61.7 % | +22.8 pts | +5.34 % | -100.8 % | 62 % | CONFIRMÉ |
| rsi_survente_reprise | +1440h | 1580 | 55.9 % | +9.3 pts | +4.63 % | -104.4 % | 56 % | BRUIT |
| rsi_survente_reprise | +2160h | 1079 | 45.4 % | -8.4 pts | -4.73 % | -75.2 % | 45 % | BRUIT |
| stoch_surachat_reprise | +1h | 21061 | 21.2 % | -8.1 pts | -0.28 % | -41.9 % | 21 % | BRUIT |
| stoch_surachat_reprise | +4h | 21056 | 37.3 % | +0.1 pts | -0.28 % | -104.5 % | 37 % | BRUIT |
| stoch_surachat_reprise | +12h | 20947 | 43.2 % | +0.9 pts | -0.27 % | -146.6 % | 43 % | BRUIT |
| stoch_surachat_reprise | +24h | 20721 | 46.0 % | +1.9 pts | -0.25 % | -256.4 % | 46 % | BRUIT |
| stoch_surachat_reprise | +72h | 20133 | 47.3 % | +0.8 pts | -0.33 % | -524.1 % | 47 % | BRUIT |
| stoch_surachat_reprise | +168h | 19044 | 45.3 % | +0.1 pts | -0.92 % | -460.3 % | 45 % | BRUIT |
| stoch_surachat_reprise | +336h | 16748 | 41.9 % | +0.5 pts | -2.44 % | -541.1 % | 42 % | BRUIT |
| stoch_surachat_reprise | +720h | 12131 | 39.6 % | +0.7 pts | -4.65 % | -666.5 % | 40 % | BRUIT |
| stoch_surachat_reprise | +1440h | 4130 | 48.3 % | +1.7 pts | -1.31 % | -1480.1 % | 48 % | BRUIT |
| stoch_surachat_reprise | +2160h | 3447 | 53.9 % | +0.1 pts | +3.90 % | -504.1 % | 54 % | BRUIT |
| stoch_survente_reprise | +1h | 20947 | 20.2 % | -9.1 pts | -0.28 % | -32.9 % | 20 % | BRUIT |
| stoch_survente_reprise | +4h | 20854 | 35.6 % | -1.5 pts | -0.28 % | -29.2 % | 36 % | BRUIT |
| stoch_survente_reprise | +12h | 20706 | 42.3 % | -0.1 pts | -0.28 % | -68.5 % | 42 % | BRUIT |
| stoch_survente_reprise | +24h | 20593 | 46.7 % | +2.7 pts | -0.21 % | -78.6 % | 47 % | BRUIT |
| stoch_survente_reprise | +72h | 19924 | 49.1 % | +2.6 pts | -0.13 % | -84.0 % | 49 % | BRUIT |
| stoch_survente_reprise | +168h | 18679 | 52.0 % | +6.9 pts | +0.39 % | -90.0 % | 52 % | BRUIT |
| stoch_survente_reprise | +336h | 16648 | 57.4 % | +16.0 pts | +2.21 % | -96.8 % | 57 % | BRUIT |
| stoch_survente_reprise | +720h | 12048 | 59.6 % | +20.8 pts | +4.50 % | -99.8 % | 60 % | CONFIRMÉ |
| stoch_survente_reprise | +1440h | 3927 | 50.6 % | +4.0 pts | +0.59 % | -103.7 % | 51 % | BRUIT |
| stoch_survente_reprise | +2160h | 3316 | 45.3 % | -8.5 pts | -4.34 % | -76.0 % | 45 % | BRUIT |
| streak_rouge_fade_long | +1h | 1708 | 38.8 % | +9.5 pts | -0.20 % | -16.3 % | 39 % | BRUIT |
| streak_rouge_fade_long | +4h | 1702 | 46.9 % | +9.8 pts | -0.10 % | -32.1 % | 47 % | BRUIT |
| streak_rouge_fade_long | +12h | 1663 | 47.6 % | +5.3 pts | -0.13 % | -38.8 % | 48 % | BRUIT |
| streak_rouge_fade_long | +24h | 1655 | 47.3 % | +3.2 pts | -0.24 % | -57.7 % | 47 % | BRUIT |
| streak_rouge_fade_long | +72h | 1601 | 47.3 % | +0.8 pts | -0.31 % | -76.2 % | 47 % | BRUIT |
| streak_rouge_fade_long | +168h | 1488 | 48.5 % | +3.3 pts | -0.35 % | -89.2 % | 49 % | BRUIT |
| streak_rouge_fade_long | +336h | 1330 | 49.1 % | +7.7 pts | -0.30 % | -96.4 % | 49 % | BRUIT |
| streak_rouge_fade_long | +720h | 1037 | 52.0 % | +13.1 pts | +0.95 % | -98.3 % | 52 % | BRUIT |
| streak_rouge_fade_long | +1440h | 606 | 47.2 % | +0.6 pts | -1.59 % | -74.2 % | 47 % | BRUIT |
| streak_rouge_fade_long | +2160h | 556 | 44.1 % | -9.7 pts | -5.47 % | -68.3 % | 44 % | BRUIT |
| streak_vert_fade_short | +1h | 1749 | 40.0 % | +10.7 pts | -0.19 % | -28.6 % | 40 % | BRUIT |
| streak_vert_fade_short | +4h | 1748 | 44.2 % | +7.0 pts | -0.15 % | -71.4 % | 44 % | BRUIT |
| streak_vert_fade_short | +12h | 1741 | 49.1 % | +6.7 pts | -0.06 % | -103.5 % | 49 % | BRUIT |
| streak_vert_fade_short | +24h | 1725 | 50.4 % | +6.4 pts | +0.04 % | -267.3 % | 50 % | BRUIT |
| streak_vert_fade_short | +72h | 1680 | 47.9 % | +1.4 pts | -0.27 % | -273.6 % | 48 % | BRUIT |
| streak_vert_fade_short | +168h | 1596 | 46.6 % | +1.4 pts | -0.57 % | -376.5 % | 47 % | BRUIT |
| streak_vert_fade_short | +336h | 1408 | 47.9 % | +6.4 pts | -0.73 % | -420.5 % | 48 % | BRUIT |
| streak_vert_fade_short | +720h | 1126 | 47.1 % | +8.2 pts | -1.28 % | -412.7 % | 47 % | BRUIT |
| streak_vert_fade_short | +1440h | 652 | 49.5 % | +2.9 pts | -0.14 % | -1446.1 % | 49 % | BRUIT |
| streak_vert_fade_short | +2160h | 593 | 56.3 % | +2.5 pts | +6.86 % | -181.9 % | 56 % | BRUIT |
| sweep_liquidite_long | +1h | 8057 | 31.0 % | +1.7 pts | -0.28 % | -33.5 % | 31 % | BRUIT |
| sweep_liquidite_long | +4h | 8050 | 40.3 % | +3.2 pts | -0.28 % | -79.9 % | 40 % | BRUIT |
| sweep_liquidite_long | +12h | 7975 | 44.1 % | +1.8 pts | -0.27 % | -83.3 % | 44 % | BRUIT |
| sweep_liquidite_long | +24h | 7943 | 47.5 % | +3.4 pts | -0.18 % | -84.1 % | 47 % | BRUIT |
| sweep_liquidite_long | +72h | 7679 | 49.4 % | +2.9 pts | -0.07 % | -88.1 % | 49 % | BRUIT |
| sweep_liquidite_long | +168h | 7213 | 50.3 % | +5.2 pts | +0.08 % | -90.5 % | 50 % | BRUIT |
| sweep_liquidite_long | +336h | 6456 | 53.6 % | +12.2 pts | +1.17 % | -96.4 % | 54 % | BRUIT |
| sweep_liquidite_long | +720h | 4969 | 54.7 % | +15.8 pts | +2.02 % | -99.5 % | 55 % | BRUIT |
| sweep_liquidite_long | +1440h | 2359 | 49.3 % | +2.7 pts | -0.50 % | -103.7 % | 49 % | BRUIT |
| sweep_liquidite_long | +2160h | 2160 | 45.9 % | -7.9 pts | -4.28 % | -76.0 % | 46 % | BRUIT |
| sweep_liquidite_short | +1h | 9202 | 31.7 % | +2.4 pts | -0.28 % | -64.7 % | 32 % | BRUIT |
| sweep_liquidite_short | +4h | 9198 | 42.4 % | +5.2 pts | -0.25 % | -104.5 % | 42 % | BRUIT |
| sweep_liquidite_short | +12h | 9134 | 47.3 % | +4.9 pts | -0.13 % | -93.9 % | 47 % | BRUIT |
| sweep_liquidite_short | +24h | 9052 | 49.2 % | +5.2 pts | -0.06 % | -150.0 % | 49 % | BRUIT |
| sweep_liquidite_short | +72h | 8813 | 49.0 % | +2.5 pts | -0.12 % | -347.2 % | 49 % | BRUIT |
| sweep_liquidite_short | +168h | 8355 | 47.8 % | +2.6 pts | -0.46 % | -460.3 % | 48 % | BRUIT |
| sweep_liquidite_short | +336h | 7260 | 45.3 % | +3.9 pts | -1.47 % | -518.6 % | 45 % | BRUIT |
| sweep_liquidite_short | +720h | 5394 | 44.3 % | +5.4 pts | -2.36 % | -582.5 % | 44 % | BRUIT |
| sweep_liquidite_short | +1440h | 2382 | 50.2 % | +3.6 pts | +0.20 % | -1429.5 % | 50 % | BRUIT |
| sweep_liquidite_short | +2160h | 2163 | 54.0 % | +0.1 pts | +3.80 % | -491.9 % | 54 % | BRUIT |
| vol_spike_retournement_long | +1h | 3024 | 31.6 % | +2.3 pts | -0.28 % | -30.3 % | 32 % | BRUIT |
| vol_spike_retournement_long | +4h | 3021 | 38.6 % | +1.4 pts | -0.29 % | -79.9 % | 39 % | BRUIT |
| vol_spike_retournement_long | +12h | 2993 | 42.7 % | +0.3 pts | -0.34 % | -83.3 % | 43 % | BRUIT |
| vol_spike_retournement_long | +24h | 2972 | 44.3 % | +0.3 pts | -0.41 % | -84.1 % | 44 % | BRUIT |
| vol_spike_retournement_long | +72h | 2870 | 48.2 % | +1.7 pts | -0.22 % | -88.1 % | 48 % | BRUIT |
| vol_spike_retournement_long | +168h | 2712 | 50.6 % | +5.5 pts | +0.14 % | -90.5 % | 51 % | BRUIT |
| vol_spike_retournement_long | +336h | 2412 | 54.2 % | +12.8 pts | +1.16 % | -96.4 % | 54 % | BRUIT |
| vol_spike_retournement_long | +720h | 1770 | 53.8 % | +14.9 pts | +1.77 % | -98.0 % | 54 % | BRUIT |
| vol_spike_retournement_long | +1440h | 689 | 47.8 % | +1.2 pts | -2.25 % | -75.2 % | 48 % | BRUIT |
| vol_spike_retournement_long | +2160h | 630 | 47.9 % | -5.9 pts | -1.65 % | -73.0 % | 48 % | BRUIT |
| vol_spike_retournement_short | +1h | 3508 | 30.8 % | +1.5 pts | -0.28 % | -57.8 % | 31 % | BRUIT |
| vol_spike_retournement_short | +4h | 3507 | 42.8 % | +5.7 pts | -0.25 % | -65.5 % | 43 % | BRUIT |
| vol_spike_retournement_short | +12h | 3471 | 46.8 % | +4.5 pts | -0.16 % | -119.9 % | 47 % | BRUIT |
| vol_spike_retournement_short | +24h | 3445 | 48.7 % | +4.6 pts | -0.10 % | -206.1 % | 49 % | BRUIT |
| vol_spike_retournement_short | +72h | 3333 | 48.1 % | +1.5 pts | -0.30 % | -171.5 % | 48 % | BRUIT |
| vol_spike_retournement_short | +168h | 3139 | 48.4 % | +3.3 pts | -0.27 % | -381.5 % | 48 % | BRUIT |
| vol_spike_retournement_short | +336h | 2755 | 43.6 % | +2.1 pts | -1.88 % | -385.8 % | 44 % | BRUIT |
| vol_spike_retournement_short | +720h | 1972 | 43.5 % | +4.6 pts | -2.68 % | -677.3 % | 44 % | BRUIT |
| vol_spike_retournement_short | +1440h | 727 | 52.5 % | +5.9 pts | +1.35 % | -225.6 % | 53 % | BRUIT |
| vol_spike_retournement_short | +2160h | 655 | 56.8 % | +3.0 pts | +5.16 % | -320.9 % | 57 % | BRUIT |
| volume_mort_cassure | +1h | 2694 | 33.7 % | +4.4 pts | -0.28 % | -32.2 % | 34 % | BRUIT |
| volume_mort_cassure | +4h | 2693 | 37.4 % | +0.2 pts | -0.34 % | -41.0 % | 37 % | BRUIT |
| volume_mort_cassure | +12h | 2680 | 42.1 % | -0.3 pts | -0.43 % | -49.2 % | 42 % | BRUIT |
| volume_mort_cassure | +24h | 2661 | 43.6 % | -0.5 pts | -0.51 % | -50.3 % | 44 % | BRUIT |
| volume_mort_cassure | +72h | 2604 | 46.8 % | +0.2 pts | -0.48 % | -60.9 % | 47 % | BRUIT |
| volume_mort_cassure | +168h | 2503 | 47.1 % | +1.9 pts | -0.54 % | -86.3 % | 47 % | BRUIT |
| volume_mort_cassure | +336h | 2290 | 49.0 % | +7.5 pts | -0.24 % | -94.9 % | 49 % | BRUIT |
| volume_mort_cassure | +720h | 1940 | 51.4 % | +12.6 pts | +0.46 % | -98.4 % | 51 % | BRUIT |
| volume_mort_cassure | +1440h | 1303 | 45.9 % | -0.7 pts | -2.24 % | -75.2 % | 46 % | BRUIT |
| volume_mort_cassure | +2160h | 1253 | 41.3 % | -12.5 pts | -8.93 % | -76.5 % | 41 % | BRUIT |
| vwap_extreme_reprise_long | +1h | 1641 | 25.5 % | -3.8 pts | -0.28 % | -16.2 % | 25 % | BRUIT |
| vwap_extreme_reprise_long | +4h | 1639 | 37.2 % | -0.0 pts | -0.28 % | -38.2 % | 37 % | BRUIT |
| vwap_extreme_reprise_long | +12h | 1614 | 44.4 % | +2.0 pts | -0.28 % | -39.6 % | 44 % | BRUIT |
| vwap_extreme_reprise_long | +24h | 1602 | 49.1 % | +5.0 pts | -0.07 % | -47.9 % | 49 % | BRUIT |
| vwap_extreme_reprise_long | +72h | 1551 | 56.6 % | +10.1 pts | +0.88 % | -56.9 % | 57 % | BRUIT |
| vwap_extreme_reprise_long | +168h | 1483 | 59.7 % | +14.6 pts | +1.99 % | -69.4 % | 60 % | CONFIRMÉ |
| vwap_extreme_reprise_long | +336h | 1420 | 58.5 % | +17.0 pts | +2.77 % | -74.9 % | 59 % | BRUIT |
| vwap_extreme_reprise_long | +720h | 850 | 56.1 % | +17.2 pts | +2.76 % | -80.4 % | 56 % | BRUIT |
| vwap_extreme_reprise_long | +1440h | 353 | 47.9 % | +1.3 pts | -1.97 % | -67.9 % | 47 % | BRUIT |
| vwap_extreme_reprise_long | +2160h | 352 | 49.7 % | -4.1 pts | -0.38 % | -66.7 % | 48 % | BRUIT |
| vwap_extreme_reprise_short | +1h | 2085 | 35.4 % | +6.1 pts | -0.28 % | -58.6 % | 35 % | BRUIT |
| vwap_extreme_reprise_short | +4h | 2083 | 46.8 % | +9.6 pts | -0.16 % | -125.1 % | 47 % | BRUIT |
| vwap_extreme_reprise_short | +12h | 2072 | 50.6 % | +8.3 pts | +0.05 % | -65.6 % | 51 % | BRUIT |
| vwap_extreme_reprise_short | +24h | 2054 | 52.0 % | +8.0 pts | +0.22 % | -147.0 % | 52 % | BRUIT |
| vwap_extreme_reprise_short | +72h | 2011 | 53.2 % | +6.7 pts | +0.54 % | -394.0 % | 53 % | BRUIT |
| vwap_extreme_reprise_short | +168h | 1879 | 52.3 % | +7.1 pts | +0.64 % | -524.5 % | 52 % | BRUIT |
| vwap_extreme_reprise_short | +336h | 1562 | 45.7 % | +4.3 pts | -1.21 % | -377.6 % | 46 % | BRUIT |
| vwap_extreme_reprise_short | +720h | 1089 | 39.9 % | +1.1 pts | -4.56 % | -563.1 % | 40 % | BRUIT |
| vwap_extreme_reprise_short | +1440h | 427 | 52.7 % | +6.1 pts | +1.77 % | -254.9 % | 53 % | BRUIT |
| vwap_extreme_reprise_short | +2160h | 423 | 51.8 % | -2.0 pts | +1.31 % | -420.9 % | 52 % | BRUIT |

## Régimes de marché (signaux avec N≥50)

| Signal | H | N | Hausse | Baisse | Vol haute | Vol basse |
|---|---|---|---|---|---|---|
| bb_squeeze_break_up | +1h | 7590 | 21 % (n=3471) | 22 % (n=1460) | 14 % (n=2212) | 25 % (n=447) |
| bb_squeeze_break_up | +4h | 7586 | 34 % (n=3471) | 34 % (n=1460) | 26 % (n=2211) | 41 % (n=444) |
| bb_squeeze_break_up | +12h | 7532 | 40 % (n=3451) | 42 % (n=1430) | 33 % (n=2211) | 49 % (n=440) |
| bb_squeeze_break_up | +24h | 7419 | 43 % (n=3338) | 45 % (n=1430) | 37 % (n=2211) | 57 % (n=440) |
| bb_squeeze_break_up | +72h | 7171 | 50 % (n=3246) | 50 % (n=1306) | 36 % (n=2180) | 55 % (n=439) |
| bb_squeeze_break_up | +168h | 6738 | 51 % (n=3043) | 49 % (n=1304) | 50 % (n=1966) | 49 % (n=425) |
| bb_squeeze_break_up | +336h | 5897 | 54 % (n=2699) | 55 % (n=1035) | 56 % (n=1923) | 62 % (n=240) |
| bb_squeeze_break_up | +720h | 4119 | 57 % (n=1989) | 57 % (n=750) | 56 % (n=1273) | 57 % (n=107) |
| bb_squeeze_break_up | +1440h | 1199 | 45 % (n=843) | 45 % (n=137) | 40 % (n=186) | 30 % (n=33) |
| bb_squeeze_break_up | +2160h | 1167 | 43 % (n=816) | 37 % (n=137) | 33 % (n=181) | 42 % (n=33) |
| beta_dislocation_achat | +1h | 485 | — | 37 % (n=46) | 50 % (n=24) | 29 % (n=414) |
| beta_dislocation_achat | +4h | 485 | — | 39 % (n=46) | 33 % (n=24) | 37 % (n=414) |
| beta_dislocation_achat | +12h | 440 | — | 50 % (n=46) | 50 % (n=24) | 50 % (n=369) |
| beta_dislocation_achat | +24h | 440 | — | 50 % (n=46) | 38 % (n=24) | 61 % (n=369) |
| beta_dislocation_achat | +72h | 440 | — | 57 % (n=46) | 42 % (n=24) | 55 % (n=369) |
| beta_dislocation_achat | +168h | 440 | — | 46 % (n=46) | 33 % (n=24) | 51 % (n=369) |
| beta_dislocation_achat | +336h | 440 | — | 63 % (n=46) | 29 % (n=24) | 49 % (n=369) |
| beta_dislocation_achat | +720h | 295 | — | 58 % (n=31) | 21 % (n=24) | 57 % (n=239) |
| beta_dislocation_achat | +1440h | 134 | — | — | 25 % (n=24) | 44 % (n=98) |
| beta_dislocation_achat | +2160h | 134 | — | — | 12 % (n=24) | 43 % (n=98) |
| beta_dislocation_vente | +1h | 1225 | 37 % (n=52) | 27 % (n=1088) | — | 40 % (n=84) |
| beta_dislocation_vente | +4h | 1225 | 54 % (n=52) | 38 % (n=1088) | — | 63 % (n=84) |
| beta_dislocation_vente | +12h | 1225 | 52 % (n=52) | 37 % (n=1088) | — | 49 % (n=84) |
| beta_dislocation_vente | +24h | 1204 | 52 % (n=31) | 40 % (n=1088) | — | 43 % (n=84) |
| beta_dislocation_vente | +72h | 1180 | 39 % (n=31) | 41 % (n=1064) | — | 52 % (n=84) |
| beta_dislocation_vente | +168h | 1180 | 48 % (n=31) | 45 % (n=1064) | — | 31 % (n=84) |
| beta_dislocation_vente | +336h | 1055 | 45 % (n=31) | 45 % (n=939) | — | 26 % (n=84) |
| beta_dislocation_vente | +720h | 729 | 52 % (n=31) | 36 % (n=666) | — | 52 % (n=31) |
| beta_dislocation_vente | +1440h | 124 | 68 % (n=31) | 54 % (n=61) | — | 52 % (n=31) |
| beta_dislocation_vente | +2160h | 124 | 84 % (n=31) | 61 % (n=61) | — | 48 % (n=31) |
| climax_top_short | +1h | 391 | 18 % (n=143) | 18 % (n=105) | 19 % (n=117) | 27 % (n=26) |
| climax_top_short | +4h | 391 | 29 % (n=143) | 31 % (n=105) | 44 % (n=117) | 31 % (n=26) |
| climax_top_short | +12h | 385 | 42 % (n=142) | 33 % (n=102) | 52 % (n=117) | 21 % (n=24) |
| climax_top_short | +24h | 382 | 47 % (n=139) | 42 % (n=102) | 53 % (n=117) | 25 % (n=24) |
| climax_top_short | +72h | 371 | 48 % (n=134) | 33 % (n=99) | 68 % (n=114) | 38 % (n=24) |
| climax_top_short | +168h | 360 | 45 % (n=129) | 43 % (n=99) | 52 % (n=108) | 58 % (n=24) |
| climax_top_short | +336h | 298 | 38 % (n=112) | 30 % (n=70) | 41 % (n=103) | — |
| climax_top_short | +720h | 187 | 34 % (n=74) | 23 % (n=48) | 43 % (n=60) | — |
| donchian_breakdown | +1h | 15694 | 13 % (n=4420) | 17 % (n=1795) | 19 % (n=7053) | 29 % (n=2426) |
| donchian_breakdown | +4h | 15682 | 29 % (n=4420) | 29 % (n=1795) | 34 % (n=7050) | 35 % (n=2417) |
| donchian_breakdown | +12h | 15419 | 39 % (n=4414) | 35 % (n=1748) | 42 % (n=7050) | 37 % (n=2207) |
| donchian_breakdown | +24h | 15367 | 42 % (n=4362) | 39 % (n=1748) | 45 % (n=7050) | 36 % (n=2207) |
| donchian_breakdown | +72h | 14901 | 41 % (n=4163) | 43 % (n=1651) | 49 % (n=6925) | 35 % (n=2162) |
| donchian_breakdown | +168h | 13929 | 43 % (n=3835) | 50 % (n=1651) | 43 % (n=6310) | 43 % (n=2133) |
| donchian_breakdown | +336h | 12595 | 43 % (n=3339) | 41 % (n=1395) | 38 % (n=6240) | 40 % (n=1621) |
| donchian_breakdown | +720h | 9046 | 36 % (n=2579) | 36 % (n=1237) | 39 % (n=4135) | 41 % (n=1095) |
| donchian_breakdown | +1440h | 2708 | 51 % (n=376) | 50 % (n=111) | 47 % (n=1563) | 52 % (n=658) |
| donchian_breakdown | +2160h | 2267 | 52 % (n=293) | 46 % (n=78) | 55 % (n=1251) | 52 % (n=645) |
| donchian_breakout | +1h | 16402 | 21 % (n=7182) | 25 % (n=3818) | 17 % (n=4257) | 23 % (n=1145) |
| donchian_breakout | +4h | 16397 | 33 % (n=7182) | 36 % (n=3818) | 28 % (n=4255) | 37 % (n=1142) |
| donchian_breakout | +12h | 16292 | 41 % (n=7138) | 43 % (n=3770) | 34 % (n=4255) | 43 % (n=1129) |
| donchian_breakout | +24h | 16103 | 44 % (n=6949) | 45 % (n=3770) | 38 % (n=4255) | 53 % (n=1129) |
| donchian_breakout | +72h | 15665 | 51 % (n=6780) | 49 % (n=3571) | 38 % (n=4188) | 57 % (n=1126) |
| donchian_breakout | +168h | 14854 | 53 % (n=6362) | 49 % (n=3567) | 50 % (n=3847) | 49 % (n=1078) |
| donchian_breakout | +336h | 13001 | 54 % (n=5605) | 53 % (n=3015) | 57 % (n=3746) | 61 % (n=635) |
| donchian_breakout | +720h | 9236 | 59 % (n=4154) | 62 % (n=2343) | 58 % (n=2434) | 54 % (n=305) |
| donchian_breakout | +1440h | 2755 | 49 % (n=1537) | 54 % (n=652) | 54 % (n=436) | 39 % (n=130) |
| donchian_breakout | +2160h | 2291 | 44 % (n=1336) | 48 % (n=570) | 39 % (n=255) | 42 % (n=130) |
| ema_death_cross | +1h | 14810 | 14 % (n=4748) | 17 % (n=2085) | 19 % (n=6115) | 26 % (n=1862) |
| ema_death_cross | +4h | 14771 | 31 % (n=4748) | 31 % (n=2085) | 34 % (n=6109) | 35 % (n=1829) |
| ema_death_cross | +12h | 14562 | 42 % (n=4741) | 38 % (n=2049) | 41 % (n=6109) | 36 % (n=1663) |
| ema_death_cross | +24h | 14495 | 45 % (n=4674) | 40 % (n=2049) | 45 % (n=6109) | 34 % (n=1663) |
| ema_death_cross | +72h | 14005 | 42 % (n=4494) | 45 % (n=1965) | 51 % (n=5944) | 37 % (n=1602) |
| ema_death_cross | +168h | 13129 | 43 % (n=4176) | 53 % (n=1965) | 43 % (n=5408) | 43 % (n=1580) |
| ema_death_cross | +336h | 11700 | 44 % (n=3612) | 42 % (n=1658) | 39 % (n=5289) | 44 % (n=1141) |
| ema_death_cross | +720h | 8795 | 37 % (n=2804) | 33 % (n=1479) | 38 % (n=3785) | 45 % (n=727) |
| ema_death_cross | +1440h | 3035 | 48 % (n=720) | 44 % (n=214) | 42 % (n=1651) | 54 % (n=450) |
| ema_death_cross | +2160h | 2262 | 51 % (n=607) | 46 % (n=181) | 56 % (n=1032) | 57 % (n=442) |
| ema_golden_cross | +1h | 14580 | 20 % (n=6189) | 24 % (n=2631) | 14 % (n=4540) | 20 % (n=1220) |
| ema_golden_cross | +4h | 14569 | 33 % (n=6189) | 37 % (n=2631) | 26 % (n=4534) | 36 % (n=1215) |
| ema_golden_cross | +12h | 14509 | 40 % (n=6172) | 42 % (n=2595) | 34 % (n=4534) | 44 % (n=1208) |
| ema_golden_cross | +24h | 14333 | 44 % (n=5996) | 44 % (n=2595) | 41 % (n=4534) | 52 % (n=1208) |
| ema_golden_cross | +72h | 13906 | 50 % (n=5793) | 47 % (n=2474) | 41 % (n=4434) | 57 % (n=1205) |
| ema_golden_cross | +168h | 13116 | 53 % (n=5333) | 47 % (n=2474) | 52 % (n=4164) | 52 % (n=1145) |
| ema_golden_cross | +336h | 11752 | 54 % (n=4758) | 54 % (n=2197) | 58 % (n=4059) | 62 % (n=738) |
| ema_golden_cross | +720h | 8685 | 60 % (n=3669) | 61 % (n=1762) | 60 % (n=2869) | 54 % (n=385) |
| ema_golden_cross | +1440h | 3013 | 51 % (n=1420) | 56 % (n=499) | 58 % (n=891) | 38 % (n=203) |
| ema_golden_cross | +2160h | 2271 | 44 % (n=1159) | 47 % (n=403) | 46 % (n=507) | 41 % (n=202) |
| failed_ath_breakout_short | +1h | 2073 | 26 % (n=825) | 25 % (n=502) | 31 % (n=656) | 38 % (n=90) |
| failed_ath_breakout_short | +4h | 2071 | 42 % (n=825) | 44 % (n=502) | 48 % (n=656) | 42 % (n=88) |
| failed_ath_breakout_short | +12h | 2053 | 51 % (n=822) | 41 % (n=489) | 50 % (n=656) | 40 % (n=86) |
| failed_ath_breakout_short | +24h | 2044 | 54 % (n=813) | 53 % (n=489) | 56 % (n=656) | 37 % (n=86) |
| failed_ath_breakout_short | +72h | 2015 | 49 % (n=801) | 46 % (n=482) | 62 % (n=646) | 45 % (n=86) |
| failed_ath_breakout_short | +168h | 1909 | 49 % (n=759) | 50 % (n=482) | 55 % (n=586) | 45 % (n=82) |
| failed_ath_breakout_short | +336h | 1611 | 48 % (n=637) | 50 % (n=373) | 46 % (n=566) | 54 % (n=35) |
| failed_ath_breakout_short | +720h | 1319 | 42 % (n=534) | 31 % (n=347) | 45 % (n=416) | 64 % (n=22) |
| failed_ath_breakout_short | +1440h | 280 | 39 % (n=102) | 42 % (n=33) | 35 % (n=141) | — |
| macd_cross_down | +1h | 21579 | 16 % (n=7392) | 18 % (n=3613) | 18 % (n=8474) | 26 % (n=2100) |
| macd_cross_down | +4h | 21554 | 32 % (n=7392) | 31 % (n=3613) | 33 % (n=8469) | 34 % (n=2080) |
| macd_cross_down | +12h | 21306 | 44 % (n=7386) | 36 % (n=3538) | 39 % (n=8469) | 34 % (n=1913) |
| macd_cross_down | +24h | 21192 | 47 % (n=7272) | 40 % (n=3538) | 44 % (n=8469) | 35 % (n=1913) |
| macd_cross_down | +72h | 20551 | 44 % (n=7029) | 43 % (n=3431) | 51 % (n=8247) | 40 % (n=1844) |
| macd_cross_down | +168h | 19369 | 47 % (n=6669) | 50 % (n=3430) | 43 % (n=7477) | 43 % (n=1793) |
| macd_cross_down | +336h | 17303 | 45 % (n=5915) | 43 % (n=2777) | 38 % (n=7276) | 40 % (n=1335) |
| macd_cross_down | +720h | 12614 | 40 % (n=4351) | 35 % (n=2435) | 38 % (n=4948) | 44 % (n=880) |
| macd_cross_down | +1440h | 4207 | 50 % (n=1359) | 45 % (n=451) | 42 % (n=1871) | 51 % (n=526) |
| macd_cross_down | +2160h | 3263 | 55 % (n=1140) | 43 % (n=418) | 56 % (n=1182) | 50 % (n=523) |
| macd_cross_up | +1h | 21227 | 19 % (n=8230) | 22 % (n=3598) | 15 % (n=7605) | 20 % (n=1794) |
| macd_cross_up | +4h | 21214 | 32 % (n=8230) | 37 % (n=3598) | 29 % (n=7600) | 32 % (n=1786) |
| macd_cross_up | +12h | 21146 | 41 % (n=8213) | 47 % (n=3566) | 39 % (n=7600) | 43 % (n=1767) |
| macd_cross_up | +24h | 20990 | 45 % (n=8060) | 48 % (n=3566) | 42 % (n=7597) | 53 % (n=1767) |
| macd_cross_up | +72h | 20321 | 50 % (n=7718) | 49 % (n=3469) | 43 % (n=7371) | 59 % (n=1763) |
| macd_cross_up | +168h | 19179 | 54 % (n=7284) | 49 % (n=3469) | 51 % (n=6797) | 55 % (n=1629) |
| macd_cross_up | +336h | 17072 | 56 % (n=6390) | 56 % (n=2923) | 58 % (n=6477) | 59 % (n=1282) |
| macd_cross_up | +720h | 12471 | 60 % (n=4815) | 64 % (n=2567) | 59 % (n=4331) | 49 % (n=758) |
| macd_cross_up | +1440h | 4163 | 55 % (n=1649) | 61 % (n=562) | 52 % (n=1428) | 44 % (n=524) |
| macd_cross_up | +2160h | 3211 | 48 % (n=1305) | 54 % (n=413) | 43 % (n=972) | 45 % (n=521) |
| rsi_surachat_reprise | +1h | 9744 | 18 % (n=3958) | 19 % (n=2351) | 18 % (n=2768) | 26 % (n=667) |
| rsi_surachat_reprise | +4h | 9741 | 33 % (n=3958) | 34 % (n=2351) | 34 % (n=2768) | 36 % (n=664) |
| rsi_surachat_reprise | +12h | 9630 | 43 % (n=3952) | 38 % (n=2293) | 43 % (n=2768) | 39 % (n=617) |
| rsi_surachat_reprise | +24h | 9574 | 48 % (n=3896) | 45 % (n=2293) | 48 % (n=2768) | 39 % (n=617) |
| rsi_surachat_reprise | +72h | 9355 | 44 % (n=3822) | 42 % (n=2221) | 56 % (n=2714) | 46 % (n=598) |
| rsi_surachat_reprise | +168h | 8902 | 45 % (n=3674) | 49 % (n=2220) | 47 % (n=2423) | 50 % (n=585) |
| rsi_surachat_reprise | +336h | 7670 | 44 % (n=3182) | 45 % (n=1782) | 39 % (n=2360) | 44 % (n=346) |
| rsi_surachat_reprise | +720h | 5459 | 41 % (n=2330) | 35 % (n=1454) | 38 % (n=1535) | 44 % (n=140) |
| rsi_surachat_reprise | +1440h | 1436 | 51 % (n=753) | 47 % (n=373) | 38 % (n=277) | 61 % (n=33) |
| rsi_surachat_reprise | +2160h | 1062 | 62 % (n=617) | 43 % (n=350) | 53 % (n=62) | 55 % (n=33) |
| rsi_survente_reprise | +1h | 8423 | 12 % (n=2232) | 13 % (n=1038) | 15 % (n=3740) | 22 % (n=1413) |
| rsi_survente_reprise | +4h | 8356 | 28 % (n=2232) | 32 % (n=1038) | 30 % (n=3722) | 36 % (n=1364) |
| rsi_survente_reprise | +12h | 8304 | 40 % (n=2227) | 42 % (n=1021) | 37 % (n=3722) | 46 % (n=1334) |
| rsi_survente_reprise | +24h | 8269 | 45 % (n=2192) | 48 % (n=1021) | 45 % (n=3722) | 56 % (n=1334) |
| rsi_survente_reprise | +72h | 8102 | 52 % (n=2135) | 53 % (n=962) | 47 % (n=3672) | 61 % (n=1333) |
| rsi_survente_reprise | +168h | 7574 | 57 % (n=1997) | 53 % (n=962) | 56 % (n=3327) | 57 % (n=1288) |
| rsi_survente_reprise | +336h | 6960 | 58 % (n=1818) | 60 % (n=869) | 59 % (n=3274) | 60 % (n=999) |
| rsi_survente_reprise | +720h | 5060 | 64 % (n=1367) | 64 % (n=716) | 62 % (n=2315) | 53 % (n=662) |
| rsi_survente_reprise | +1440h | 1580 | 70 % (n=209) | 85 % (n=105) | 55 % (n=811) | 44 % (n=455) |
| rsi_survente_reprise | +2160h | 1079 | 57 % (n=40) | 60 % (n=20) | 44 % (n=568) | 45 % (n=451) |
| stoch_surachat_reprise | +1h | 21061 | 19 % (n=8628) | 22 % (n=4191) | 21 % (n=6518) | 33 % (n=1724) |
| stoch_surachat_reprise | +4h | 21056 | 36 % (n=8628) | 36 % (n=4191) | 39 % (n=6515) | 40 % (n=1722) |
| stoch_surachat_reprise | +12h | 20947 | 44 % (n=8611) | 41 % (n=4149) | 45 % (n=6515) | 38 % (n=1672) |
| stoch_surachat_reprise | +24h | 20721 | 48 % (n=8387) | 46 % (n=4149) | 46 % (n=6513) | 37 % (n=1672) |
| stoch_surachat_reprise | +72h | 20133 | 44 % (n=8151) | 46 % (n=3940) | 54 % (n=6386) | 42 % (n=1656) |
| stoch_surachat_reprise | +168h | 19044 | 44 % (n=7657) | 49 % (n=3937) | 45 % (n=5850) | 46 % (n=1600) |
| stoch_surachat_reprise | +336h | 16748 | 43 % (n=6681) | 43 % (n=3304) | 40 % (n=5679) | 41 % (n=1084) |
| stoch_surachat_reprise | +720h | 12131 | 40 % (n=5014) | 36 % (n=2745) | 41 % (n=3722) | 43 % (n=650) |
| stoch_surachat_reprise | +1440h | 4130 | 50 % (n=1928) | 44 % (n=685) | 46 % (n=1123) | 56 % (n=394) |
| stoch_surachat_reprise | +2160h | 3447 | 55 % (n=1609) | 48 % (n=589) | 55 % (n=859) | 54 % (n=390) |
| stoch_survente_reprise | +1h | 20947 | 20 % (n=7141) | 23 % (n=2999) | 19 % (n=8400) | 23 % (n=2407) |
| stoch_survente_reprise | +4h | 20854 | 36 % (n=7141) | 38 % (n=2999) | 34 % (n=8378) | 38 % (n=2336) |
| stoch_survente_reprise | +12h | 20706 | 42 % (n=7123) | 45 % (n=2980) | 40 % (n=8378) | 49 % (n=2225) |
| stoch_survente_reprise | +24h | 20593 | 45 % (n=7010) | 51 % (n=2980) | 44 % (n=8378) | 57 % (n=2225) |
| stoch_survente_reprise | +72h | 19924 | 52 % (n=6746) | 49 % (n=2847) | 44 % (n=8129) | 59 % (n=2202) |
| stoch_survente_reprise | +168h | 18679 | 53 % (n=6309) | 46 % (n=2846) | 53 % (n=7370) | 54 % (n=2154) |
| stoch_survente_reprise | +336h | 16648 | 54 % (n=5502) | 57 % (n=2346) | 60 % (n=7178) | 58 % (n=1622) |
| stoch_survente_reprise | +720h | 12048 | 60 % (n=4118) | 65 % (n=2066) | 59 % (n=4771) | 53 % (n=1093) |
| stoch_survente_reprise | +1440h | 3927 | 53 % (n=1148) | 61 % (n=381) | 49 % (n=1722) | 44 % (n=676) |
| stoch_survente_reprise | +2160h | 3316 | 45 % (n=918) | 55 % (n=289) | 44 % (n=1439) | 45 % (n=670) |
| streak_rouge_fade_long | +1h | 1708 | 39 % (n=474) | 43 % (n=167) | 37 % (n=717) | 41 % (n=350) |
| streak_rouge_fade_long | +4h | 1702 | 46 % (n=474) | 49 % (n=167) | 44 % (n=717) | 53 % (n=344) |
| streak_rouge_fade_long | +12h | 1663 | 46 % (n=474) | 57 % (n=166) | 45 % (n=717) | 51 % (n=306) |
| streak_rouge_fade_long | +24h | 1655 | 43 % (n=466) | 56 % (n=166) | 44 % (n=717) | 57 % (n=306) |
| streak_rouge_fade_long | +72h | 1601 | 45 % (n=449) | 55 % (n=154) | 48 % (n=700) | 46 % (n=298) |
| streak_rouge_fade_long | +168h | 1488 | 45 % (n=407) | 47 % (n=154) | 51 % (n=632) | 48 % (n=295) |
| streak_rouge_fade_long | +336h | 1330 | 45 % (n=357) | 54 % (n=119) | 51 % (n=623) | 47 % (n=231) |
| streak_rouge_fade_long | +720h | 1037 | 49 % (n=254) | 60 % (n=104) | 52 % (n=471) | 52 % (n=208) |
| streak_rouge_fade_long | +1440h | 606 | 44 % (n=116) | 42 % (n=26) | 51 % (n=300) | 44 % (n=164) |
| streak_rouge_fade_long | +2160h | 556 | 44 % (n=104) | 57 % (n=23) | 42 % (n=270) | 46 % (n=159) |
| streak_vert_fade_short | +1h | 1749 | 35 % (n=785) | 42 % (n=441) | 43 % (n=367) | 51 % (n=156) |
| streak_vert_fade_short | +4h | 1748 | 44 % (n=785) | 41 % (n=441) | 50 % (n=366) | 42 % (n=156) |
| streak_vert_fade_short | +12h | 1741 | 48 % (n=784) | 49 % (n=436) | 53 % (n=366) | 48 % (n=155) |
| streak_vert_fade_short | +24h | 1725 | 52 % (n=769) | 49 % (n=436) | 56 % (n=365) | 35 % (n=155) |
| streak_vert_fade_short | +72h | 1680 | 46 % (n=755) | 49 % (n=413) | 54 % (n=359) | 39 % (n=153) |
| streak_vert_fade_short | +168h | 1596 | 45 % (n=704) | 46 % (n=413) | 50 % (n=331) | 48 % (n=148) |
| streak_vert_fade_short | +336h | 1408 | 48 % (n=627) | 46 % (n=361) | 48 % (n=328) | 53 % (n=92) |
| streak_vert_fade_short | +720h | 1126 | 49 % (n=508) | 42 % (n=308) | 46 % (n=249) | 57 % (n=61) |
| streak_vert_fade_short | +1440h | 652 | 47 % (n=349) | 51 % (n=148) | 53 % (n=112) | 58 % (n=43) |
| streak_vert_fade_short | +2160h | 593 | 58 % (n=318) | 54 % (n=138) | 52 % (n=94) | 60 % (n=43) |
| sweep_liquidite_long | +1h | 8057 | 33 % (n=2151) | 38 % (n=1150) | 28 % (n=3339) | 30 % (n=1417) |
| sweep_liquidite_long | +4h | 8050 | 41 % (n=2151) | 43 % (n=1150) | 39 % (n=3337) | 41 % (n=1412) |
| sweep_liquidite_long | +12h | 7975 | 43 % (n=2146) | 48 % (n=1124) | 42 % (n=3337) | 49 % (n=1368) |
| sweep_liquidite_long | +24h | 7943 | 46 % (n=2114) | 47 % (n=1124) | 45 % (n=3337) | 56 % (n=1368) |
| sweep_liquidite_long | +72h | 7679 | 50 % (n=1988) | 50 % (n=1065) | 46 % (n=3267) | 56 % (n=1359) |
| sweep_liquidite_long | +168h | 7213 | 51 % (n=1862) | 46 % (n=1065) | 51 % (n=2942) | 52 % (n=1344) |
| sweep_liquidite_long | +336h | 6456 | 49 % (n=1620) | 52 % (n=885) | 56 % (n=2904) | 55 % (n=1047) |
| sweep_liquidite_long | +720h | 4969 | 54 % (n=1270) | 59 % (n=756) | 54 % (n=2125) | 52 % (n=818) |
| sweep_liquidite_long | +1440h | 2359 | 49 % (n=398) | 60 % (n=148) | 51 % (n=1207) | 43 % (n=606) |
| sweep_liquidite_long | +2160h | 2160 | 42 % (n=352) | 60 % (n=128) | 46 % (n=1080) | 44 % (n=600) |
| sweep_liquidite_short | +1h | 9202 | 30 % (n=3821) | 29 % (n=2162) | 34 % (n=2418) | 41 % (n=801) |
| sweep_liquidite_short | +4h | 9198 | 42 % (n=3821) | 40 % (n=2162) | 45 % (n=2415) | 43 % (n=800) |
| sweep_liquidite_short | +12h | 9134 | 48 % (n=3813) | 42 % (n=2115) | 51 % (n=2415) | 44 % (n=791) |
| sweep_liquidite_short | +24h | 9052 | 50 % (n=3731) | 47 % (n=2115) | 53 % (n=2415) | 42 % (n=791) |
| sweep_liquidite_short | +72h | 8813 | 46 % (n=3664) | 47 % (n=1989) | 57 % (n=2371) | 43 % (n=789) |
| sweep_liquidite_short | +168h | 8355 | 46 % (n=3465) | 48 % (n=1987) | 51 % (n=2145) | 45 % (n=758) |
| sweep_liquidite_short | +336h | 7260 | 47 % (n=3049) | 46 % (n=1630) | 44 % (n=2095) | 36 % (n=486) |
| sweep_liquidite_short | +720h | 5394 | 46 % (n=2392) | 40 % (n=1328) | 45 % (n=1417) | 46 % (n=257) |
| sweep_liquidite_short | +1440h | 2382 | 49 % (n=1294) | 49 % (n=513) | 52 % (n=415) | 57 % (n=160) |
| sweep_liquidite_short | +2160h | 2163 | 55 % (n=1184) | 49 % (n=492) | 56 % (n=329) | 56 % (n=158) |
| vol_spike_retournement_long | +1h | 3024 | 32 % (n=1089) | 37 % (n=611) | 29 % (n=954) | 27 % (n=370) |
| vol_spike_retournement_long | +4h | 3021 | 38 % (n=1089) | 44 % (n=611) | 37 % (n=953) | 36 % (n=368) |
| vol_spike_retournement_long | +12h | 2993 | 40 % (n=1079) | 48 % (n=600) | 40 % (n=953) | 50 % (n=361) |
| vol_spike_retournement_long | +24h | 2972 | 43 % (n=1058) | 46 % (n=600) | 43 % (n=953) | 50 % (n=361) |
| vol_spike_retournement_long | +72h | 2870 | 50 % (n=1018) | 47 % (n=558) | 46 % (n=934) | 52 % (n=360) |
| vol_spike_retournement_long | +168h | 2712 | 54 % (n=950) | 50 % (n=557) | 49 % (n=851) | 46 % (n=354) |
| vol_spike_retournement_long | +336h | 2412 | 54 % (n=848) | 54 % (n=467) | 55 % (n=837) | 55 % (n=260) |
| vol_spike_retournement_long | +720h | 1770 | 52 % (n=661) | 57 % (n=361) | 54 % (n=578) | 54 % (n=170) |
| vol_spike_retournement_long | +1440h | 689 | 46 % (n=266) | 54 % (n=116) | 52 % (n=211) | 36 % (n=96) |
| vol_spike_retournement_long | +2160h | 630 | 47 % (n=244) | 57 % (n=108) | 45 % (n=182) | 46 % (n=96) |
| vol_spike_retournement_short | +1h | 3508 | 27 % (n=1055) | 28 % (n=779) | 33 % (n=1188) | 41 % (n=486) |
| vol_spike_retournement_short | +4h | 3507 | 40 % (n=1055) | 44 % (n=779) | 43 % (n=1188) | 48 % (n=485) |
| vol_spike_retournement_short | +12h | 3471 | 48 % (n=1052) | 44 % (n=757) | 49 % (n=1188) | 43 % (n=474) |
| vol_spike_retournement_short | +24h | 3445 | 48 % (n=1026) | 52 % (n=757) | 50 % (n=1188) | 42 % (n=474) |
| vol_spike_retournement_short | +72h | 3333 | 46 % (n=985) | 48 % (n=710) | 54 % (n=1166) | 39 % (n=472) |
| vol_spike_retournement_short | +168h | 3139 | 47 % (n=915) | 52 % (n=710) | 49 % (n=1050) | 44 % (n=464) |
| vol_spike_retournement_short | +336h | 2755 | 47 % (n=796) | 44 % (n=590) | 42 % (n=1036) | 40 % (n=333) |
| vol_spike_retournement_short | +720h | 1972 | 44 % (n=616) | 37 % (n=491) | 47 % (n=692) | 47 % (n=173) |
| vol_spike_retournement_short | +1440h | 727 | 51 % (n=228) | 40 % (n=91) | 55 % (n=281) | 60 % (n=127) |
| vol_spike_retournement_short | +2160h | 655 | 58 % (n=200) | 41 % (n=81) | 61 % (n=249) | 56 % (n=125) |
| volume_mort_cassure | +1h | 2694 | 34 % (n=1412) | 40 % (n=637) | 27 % (n=487) | 28 % (n=158) |
| volume_mort_cassure | +4h | 2693 | 38 % (n=1412) | 40 % (n=637) | 33 % (n=486) | 37 % (n=158) |
| volume_mort_cassure | +12h | 2680 | 44 % (n=1403) | 41 % (n=634) | 37 % (n=486) | 45 % (n=157) |
| volume_mort_cassure | +24h | 2661 | 45 % (n=1384) | 43 % (n=634) | 39 % (n=486) | 44 % (n=157) |
| volume_mort_cassure | +72h | 2604 | 50 % (n=1360) | 44 % (n=609) | 40 % (n=478) | 50 % (n=157) |
| volume_mort_cassure | +168h | 2503 | 49 % (n=1307) | 46 % (n=606) | 46 % (n=439) | 40 % (n=151) |
| volume_mort_cassure | +336h | 2290 | 48 % (n=1205) | 49 % (n=542) | 51 % (n=428) | 49 % (n=115) |
| volume_mort_cassure | +720h | 1940 | 51 % (n=1045) | 52 % (n=491) | 52 % (n=315) | 45 % (n=89) |
| volume_mort_cassure | +1440h | 1303 | 46 % (n=788) | 47 % (n=305) | 48 % (n=140) | 36 % (n=70) |
| volume_mort_cassure | +2160h | 1253 | 42 % (n=753) | 43 % (n=296) | 37 % (n=134) | 34 % (n=70) |
| vwap_extreme_reprise_long | +1h | 1641 | 18 % (n=334) | 25 % (n=157) | 22 % (n=670) | 36 % (n=480) |
| vwap_extreme_reprise_long | +4h | 1639 | 32 % (n=334) | 33 % (n=157) | 36 % (n=668) | 43 % (n=480) |
| vwap_extreme_reprise_long | +12h | 1614 | 44 % (n=334) | 44 % (n=149) | 41 % (n=668) | 50 % (n=463) |
| vwap_extreme_reprise_long | +24h | 1602 | 48 % (n=322) | 53 % (n=149) | 47 % (n=668) | 52 % (n=463) |
| vwap_extreme_reprise_long | +72h | 1551 | 62 % (n=299) | 55 % (n=141) | 51 % (n=654) | 62 % (n=457) |
| vwap_extreme_reprise_long | +168h | 1483 | 62 % (n=283) | 56 % (n=141) | 57 % (n=606) | 63 % (n=453) |
| vwap_extreme_reprise_long | +336h | 1420 | 61 % (n=272) | 53 % (n=122) | 58 % (n=601) | 59 % (n=425) |
| vwap_extreme_reprise_long | +720h | 850 | 63 % (n=173) | 46 % (n=92) | 65 % (n=294) | 47 % (n=291) |
| vwap_extreme_reprise_long | +1440h | 353 | — | — | 57 % (n=96) | 44 % (n=253) |
| vwap_extreme_reprise_long | +2160h | 352 | — | — | 52 % (n=95) | 49 % (n=253) |
| vwap_extreme_reprise_short | +1h | 2085 | 36 % (n=726) | 34 % (n=798) | 38 % (n=417) | 38 % (n=144) |
| vwap_extreme_reprise_short | +4h | 2083 | 49 % (n=726) | 43 % (n=798) | 50 % (n=415) | 47 % (n=144) |
| vwap_extreme_reprise_short | +12h | 2072 | 54 % (n=722) | 44 % (n=792) | 58 % (n=415) | 48 % (n=143) |
| vwap_extreme_reprise_short | +24h | 2054 | 56 % (n=704) | 45 % (n=792) | 61 % (n=415) | 48 % (n=143) |
| vwap_extreme_reprise_short | +72h | 2011 | 55 % (n=687) | 43 % (n=779) | 70 % (n=402) | 53 % (n=143) |
| vwap_extreme_reprise_short | +168h | 1879 | 54 % (n=633) | 47 % (n=779) | 58 % (n=330) | 60 % (n=137) |
| vwap_extreme_reprise_short | +336h | 1562 | 50 % (n=526) | 42 % (n=668) | 45 % (n=308) | 50 % (n=60) |
| vwap_extreme_reprise_short | +720h | 1089 | 54 % (n=347) | 30 % (n=584) | 47 % (n=118) | 45 % (n=40) |
| vwap_extreme_reprise_short | +1440h | 427 | 59 % (n=221) | 44 % (n=180) | — | — |
| vwap_extreme_reprise_short | +2160h | 423 | 64 % (n=217) | 37 % (n=180) | — | — |

## Risque de LIQUIDATION selon le levier (confirmés)

Part des trades dont l'excursion adverse touche ~100/levier %

| Signal | H | 3x | 5x | 10x |
|---|---|---|---|---|
| beta_dislocation_vente | +2160h | 46.0 % (n=124) | 59.7 % (n=124) | 81.5 % (n=124) |
| donchian_breakout | +720h | 20.8 % (n=8516) | 29.6 % (n=4307) | 61.8 % (n=3885) |
| ema_golden_cross | +720h | 20.7 % (n=8006) | 30.0 % (n=4141) | 61.4 % (n=3753) |
| failed_ath_breakout_short | +2160h | 10.4 % (n=48) | 31.2 % (n=48) | 58.3 % (n=48) |
| funding_accel_momentum | +336h | 13.7 % (n=14068) | 13.6 % (n=6737) | 44.0 % (n=5619) |
| funding_accel_momentum | +720h | 19.3 % (n=11058) | 24.8 % (n=5842) | 53.5 % (n=4914) |
| funding_div_plus_vwap_short | +72h | 21.5 % (n=1906) | 25.6 % (n=696) | 49.1 % (n=546) |
| funding_div_plus_vwap_short | +168h | 30.9 % (n=1760) | 36.3 % (n=650) | 57.1 % (n=518) |
| funding_div_plus_vwap_short | +1440h | 4.2 % (n=96) | 8.3 % (n=96) | 54.2 % (n=96) |
| funding_div_plus_vwap_short | +2160h | 8.7 % (n=92) | 13.0 % (n=92) | 52.2 % (n=92) |
| funding_extreme_contre_courant | +720h | 31.1 % (n=7684) | 34.8 % (n=3444) | 57.2 % (n=2804) |
| funding_extreme_plus_div_short | +4h | 0.0 % (n=18) | 0.0 % (n=4) | 0.0 % (n=4) |
| funding_extreme_plus_div_short | +12h | 0.0 % (n=18) | 0.0 % (n=4) | 0.0 % (n=4) |
| funding_flip_neg | +2160h | 10.9 % (n=368) | 36.1 % (n=368) | 71.5 % (n=368) |
| funding_flip_pos | +336h | 8.1 % (n=6770) | 7.0 % (n=3312) | 37.4 % (n=2750) |
| funding_flip_pos | +720h | 11.7 % (n=5509) | 17.1 % (n=2989) | 48.4 % (n=2503) |
| macd_cross_up | +720h | 20.7 % (n=11502) | 30.4 % (n=5872) | 60.5 % (n=5313) |
| precision_quad | +72h | 27.7 % (n=685) | 29.0 % (n=276) | 58.3 % (n=216) |
| precision_quad | +168h | 35.1 % (n=639) | 37.1 % (n=264) | 62.1 % (n=206) |
| precision_quad | +1440h | 0.0 % (n=52) | 7.7 % (n=52) | 53.8 % (n=52) |
| precision_quad | +2160h | 0.0 % (n=52) | 7.7 % (n=52) | 53.8 % (n=52) |
| precision_rsi75 | +72h | 22.7 % (n=1279) | 27.3 % (n=484) | 49.5 % (n=380) |
| precision_rsi75 | +168h | 31.8 % (n=1201) | 36.8 % (n=462) | 52.7 % (n=364) |
| precision_rsi75 | +2160h | 10.5 % (n=76) | 15.8 % (n=76) | 52.6 % (n=76) |
| precision_volume | +72h | 26.9 % (n=915) | 27.5 % (n=334) | 55.3 % (n=264) |
| precision_volume | +168h | 36.3 % (n=843) | 36.3 % (n=314) | 62.4 % (n=250) |
| precision_volume | +1440h | 0.0 % (n=56) | 7.1 % (n=56) | 57.1 % (n=56) |
| precision_volume | +2160h | 0.0 % (n=56) | 7.1 % (n=56) | 57.1 % (n=56) |
| rsi_survente_reprise | +336h | 10.7 % (n=6381) | 17.2 % (n=2600) | 48.1 % (n=2309) |
| rsi_survente_reprise | +720h | 18.0 % (n=4683) | 29.1 % (n=2148) | 59.4 % (n=1935) |
| stoch_survente_reprise | +720h | 21.2 % (n=11146) | 30.5 % (n=5915) | 61.6 % (n=5349) |
| vwap_extreme_reprise_long | +168h | 11.5 % (n=1370) | 17.7 % (n=611) | 40.3 % (n=554) |
Seuil réel = 100/levier − maintMarginPercent du symbole (exchangeInfo),
levier plafonné au max réellement autorisé par symbole (PONS/CATE/MEME : 3x).
Un % de liquidation > 0 rend la stratégie morte au levier considéré —
la médiane positive ne sauve pas un compte liquidé.

## Audit de multiplicité

- cellules signal×horizon testées : 356
- confirmés poolés : 32 (attendus par hasard ≈ 9)
- confirmés AU-DESSUS DU DRIFT (Δ blind ≥ +5 pts) : 32
- VERDICT GLOBAL : CANDIDATS AU-DESSUS DU DRIFT à examiner

Rappel : un signal « robuste » doit garder son WR hors big-moves ET
sur plusieurs régimes. Tout le reste = bruit, et on le dit.
