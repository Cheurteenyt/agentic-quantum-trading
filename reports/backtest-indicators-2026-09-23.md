# Backtest indicateurs Aster — 1h, 31+ symboles, avril → septembre
Combinaisons testées : 403 signaux×symboles. Coût 8 bps. Split 70/30 temporel.
Règle CONFIRMÉ : train N≥10 & WR≥55 % PUIS val N≥5 & WR≥55 %.

## Pooled par signal (tous symboles confondus)

| Signal | H | N | Winrate | Verdict |
|---|---|---|---|---|
| bb_squeeze_break_up | +1h | 1590 | 28.6 % | BRUIT |
| bb_squeeze_break_up | +24h | 1578 | 47.4 % | BRUIT |
| bb_squeeze_break_up | +72h | 1564 | 43.9 % | BRUIT |
| donchian_breakdown | +1h | 3486 | 25.5 % | BRUIT |
| donchian_breakdown | +24h | 3478 | 45.8 % | BRUIT |
| donchian_breakdown | +72h | 3428 | 46.6 % | BRUIT |
| donchian_breakout | +1h | 3475 | 31.2 % | BRUIT |
| donchian_breakout | +24h | 3445 | 47.7 % | BRUIT |
| donchian_breakout | +72h | 3357 | 44.7 % | BRUIT |
| ema_death_cross | +1h | 2111 | 29.1 % | BRUIT |
| ema_death_cross | +24h | 2100 | 48.4 % | BRUIT |
| ema_death_cross | +72h | 2070 | 52.2 % | BRUIT |
| ema_golden_cross | +1h | 2120 | 28.1 % | BRUIT |
| ema_golden_cross | +24h | 2113 | 46.0 % | BRUIT |
| ema_golden_cross | +72h | 2081 | 44.3 % | BRUIT |
| macd_cross_down | +1h | 3723 | 29.9 % | BRUIT |
| macd_cross_down | +24h | 3686 | 48.1 % | BRUIT |
| macd_cross_down | +72h | 3652 | 50.1 % | BRUIT |
| macd_cross_up | +1h | 3718 | 30.3 % | BRUIT |
| macd_cross_up | +24h | 3695 | 46.1 % | BRUIT |
| macd_cross_up | +72h | 3652 | 46.7 % | BRUIT |
| rsi_surachat_reprise | +1h | 1473 | 30.8 % | BRUIT |
| rsi_surachat_reprise | +24h | 1449 | 52.0 % | BRUIT |
| rsi_surachat_reprise | +72h | 1411 | 52.9 % | BRUIT |
| rsi_survente_reprise | +1h | 1391 | 28.8 % | BRUIT |
| rsi_survente_reprise | +24h | 1390 | 49.4 % | BRUIT |
| rsi_survente_reprise | +72h | 1372 | 53.4 % | BRUIT |
| stoch_surachat_reprise | +1h | 6682 | 33.5 % | BRUIT |
| stoch_surachat_reprise | +24h | 6622 | 50.2 % | BRUIT |
| stoch_surachat_reprise | +72h | 6479 | 52.9 % | BRUIT |
| stoch_survente_reprise | +1h | 6572 | 33.7 % | BRUIT |
| stoch_survente_reprise | +24h | 6533 | 47.6 % | BRUIT |
| stoch_survente_reprise | +72h | 6426 | 48.1 % | BRUIT |
| vol_spike_reversal_long | +1h | 398 | 42.7 % | BRUIT |
| vol_spike_reversal_long | +24h | 397 | 51.4 % | BRUIT |
| vol_spike_reversal_long | +72h | 388 | 46.1 % | BRUIT |
| vol_spike_reversal_short | +1h | 493 | 38.1 % | BRUIT |
| vol_spike_reversal_short | +24h | 491 | 53.2 % | BRUIT |
| vol_spike_reversal_short | +72h | 477 | 53.7 % | BRUIT |

## Confirmations par symbole (train + val)

- donchian_breakdown @ ADAUSDT +72h : train 102/59 (58 %), val 23/13 (57 %)
- ema_death_cross @ ADAUSDT +72h : train 45/26 (58 %), val 18/11 (61 %)
- stoch_surachat_reprise @ ARBUSDT +24h : train 158/87 (55 %), val 63/37 (59 %)
- rsi_surachat_reprise @ ASTERUSDT +72h : train 18/15 (83 %), val 12/7 (58 %)
- vol_spike_reversal_short @ ASTERUSDT +72h : train 12/7 (58 %), val 8/5 (62 %)
- rsi_survente_reprise @ AVAXUSDT +72h : train 50/30 (60 %), val 7/5 (71 %)
- stoch_survente_reprise @ AVAXUSDT +24h : train 223/123 (55 %), val 79/46 (58 %)
- vol_spike_reversal_short @ AVAXUSDT +72h : train 21/12 (57 %), val 10/6 (60 %)
- rsi_survente_reprise @ BNBUSDT +24h : train 32/19 (59 %), val 7/6 (86 %)
- rsi_survente_reprise @ BNBUSDT +72h : train 32/22 (69 %), val 7/5 (71 %)
- ema_golden_cross @ BNBUSDT +24h : train 44/26 (59 %), val 17/11 (65 %)
- rsi_survente_reprise @ BTCUSDT +1h : train 50/29 (58 %), val 8/5 (62 %)
- rsi_surachat_reprise @ BTCUSDT +72h : train 44/25 (57 %), val 19/11 (58 %)
- vol_spike_reversal_long @ BTCUSDT +24h : train 17/13 (76 %), val 5/3 (60 %)
- macd_cross_down @ CATEUSDT +72h : train 24/15 (62 %), val 5/3 (60 %)
- stoch_survente_reprise @ CATEUSDT +72h : train 46/26 (57 %), val 11/7 (64 %)
- vol_spike_reversal_short @ DOGEUSDT +24h : train 10/6 (60 %), val 12/7 (58 %)
- rsi_survente_reprise @ DOGSUSDT +72h : train 47/26 (55 %), val 9/8 (89 %)
- rsi_survente_reprise @ ETHUSDT +72h : train 44/27 (61 %), val 8/7 (88 %)
- rsi_surachat_reprise @ ETHUSDT +24h : train 39/25 (64 %), val 22/14 (64 %)
- vol_spike_reversal_long @ FARTCOINUSDT +24h : train 12/7 (58 %), val 5/4 (80 %)
- rsi_survente_reprise @ HUSDT +72h : train 17/12 (71 %), val 14/9 (64 %)
- macd_cross_up @ HUSDT +72h : train 82/46 (56 %), val 28/17 (61 %)
- bb_squeeze_break_up @ HUSDT +72h : train 26/16 (62 %), val 16/10 (62 %)
- ema_golden_cross @ HUSDT +72h : train 49/28 (57 %), val 13/9 (69 %)
- ema_golden_cross @ HYPEUSDT +24h : train 45/25 (56 %), val 20/12 (60 %)
- rsi_surachat_reprise @ LABUSDT +72h : train 33/20 (61 %), val 10/8 (80 %)
- stoch_surachat_reprise @ LABUSDT +72h : train 128/79 (62 %), val 45/26 (58 %)
- vol_spike_reversal_short @ LABUSDT +72h : train 11/8 (73 %), val 6/4 (67 %)
- rsi_survente_reprise @ LINKUSDT +72h : train 36/22 (61 %), val 8/5 (62 %)
- bb_squeeze_break_up @ LINKUSDT +72h : train 58/33 (57 %), val 13/10 (77 %)
- vol_spike_reversal_short @ LINKUSDT +72h : train 23/13 (57 %), val 10/6 (60 %)
- rsi_survente_reprise @ LTCUSDT +72h : train 26/15 (58 %), val 5/5 (100 %)
- ema_death_cross @ MOODENGUSDT +24h : train 45/25 (56 %), val 20/11 (55 %)
- ema_death_cross @ MOODENGUSDT +72h : train 45/27 (60 %), val 19/12 (63 %)
- rsi_surachat_reprise @ NEIROUSDT +24h : train 27/19 (70 %), val 16/12 (75 %)
- rsi_surachat_reprise @ NEIROUSDT +72h : train 27/18 (67 %), val 14/10 (71 %)
- ema_death_cross @ PENGUUSDT +24h : train 47/26 (55 %), val 19/11 (58 %)
- ema_death_cross @ PENGUUSDT +72h : train 47/26 (55 %), val 18/12 (67 %)
- rsi_survente_reprise @ PNUTUSDT +24h : train 39/22 (56 %), val 15/9 (60 %)
- rsi_survente_reprise @ PORTALUSDT +24h : train 36/20 (56 %), val 7/4 (57 %)
- rsi_survente_reprise @ PORTALUSDT +72h : train 36/21 (58 %), val 7/5 (71 %)
- rsi_survente_reprise @ SOLUSDT +72h : train 40/23 (57 %), val 12/9 (75 %)
- vol_spike_reversal_long @ SOLUSDT +24h : train 13/8 (62 %), val 5/3 (60 %)
- vol_spike_reversal_short @ SOLUSDT +1h : train 13/8 (62 %), val 5/3 (60 %)
- rsi_surachat_reprise @ TRUMPUSDT +24h : train 18/11 (61 %), val 14/8 (57 %)
- ema_death_cross @ TRUMPUSDT +24h : train 54/30 (56 %), val 18/10 (56 %)
- ema_death_cross @ TRUMPUSDT +72h : train 54/32 (59 %), val 17/10 (59 %)
- vol_spike_reversal_short @ TRUMPUSDT +24h : train 12/8 (67 %), val 5/4 (80 %)
- vol_spike_reversal_short @ TRUMPUSDT +72h : train 12/8 (67 %), val 5/3 (60 %)
- rsi_surachat_reprise @ TURBOUSDT +24h : train 43/25 (58 %), val 16/12 (75 %)
- ema_death_cross @ XRPUSDT +72h : train 45/34 (76 %), val 22/14 (64 %)
- vol_spike_reversal_short @ XRPUSDT +24h : train 12/7 (58 %), val 9/5 (56 %)
- vol_spike_reversal_short @ XRPUSDT +72h : train 12/9 (75 %), val 9/7 (78 %)

## Audit de multiplicité

- signaux × horizons poolés : 39
- confirmations pooled : 0 (attendues par hasard ≈ 1 au seuil 55 %/N≥10)
- confirmations par symbole : 54 (sur 1209 combinaisons)
- VERDICT GLOBAL : aucun edge démontré — cohérent avec la culture des résultats nuls
