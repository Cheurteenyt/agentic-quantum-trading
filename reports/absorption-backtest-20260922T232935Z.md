# Backtest Absorption & Sweep — perps Aster

Généré : 22/09/2026 23:29 UTC · règles EXACTES de l'indicateur (delta ≥ 2× baseline, corps ≤ 40 %, sweep ≥ 0.15 ATR + reclaim).

**Règle pré-enregistrée** : N ≥ 10 ET winrate ≥ 55 % = prometteur ; N ≥ 10 et < 55 % = bruit classé ; N < 10 = insuffisant. Split 70/30. Coûts 8 bps aller-retour, slippage non inclus.

**Avertissement multiplicité** : ce rapport teste ~12 combinaisons par symbole ; à 5 % de hasard, 1 surviving sur 20 est ATTENDU sans edge réel.

### BTCUSDT — 3000 bougies 1h, 185 événements

train = 127 événements (70 % anciens) · val = 58 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 17 | 35.3 % | -20.9 | BRUIT (classé) |
| absorption_buy | +4h | 17 | 52.9 % | +11.0 | BRUIT (classé) |
| absorption_buy | +12h | 17 | 41.2 % | -12.6 | BRUIT (classé) |
| sweep_low | +1h | 44 | 43.2 % | -4.4 | BRUIT (classé) |
| sweep_low | +4h | 44 | 50.0 % | +11.0 | BRUIT (classé) |
| sweep_low | +12h | 44 | 36.4 % | -12.6 | BRUIT (classé) |
| absorption_sell | +1h | 21 | 38.1 % | -8.3 | BRUIT (classé) |
| absorption_sell | +4h | 21 | 52.4 % | +0.7 | BRUIT (classé) |
| absorption_sell | +12h | 21 | 33.3 % | -24.9 | BRUIT (classé) |
| sweep_high | +1h | 45 | 42.2 % | -8.1 | BRUIT (classé) |
| sweep_high | +4h | 45 | 46.7 % | -4.3 | BRUIT (classé) |
| sweep_high | +12h | 45 | 46.7 % | -5.5 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 18 | 44.4 % | -0.3 | BRUIT (classé) |
| absorption_buy | +4h | 18 | 44.4 % | -26.3 | BRUIT (classé) |
| absorption_buy | +12h | 18 | 44.4 % | -1.5 | BRUIT (classé) |
| sweep_low | +1h | 14 | 28.6 % | -10.3 | BRUIT (classé) |
| sweep_low | +4h | 14 | 28.6 % | -13.2 | BRUIT (classé) |
| sweep_low | +12h | 14 | 28.6 % | -21.9 | BRUIT (classé) |
| absorption_sell | +1h | 6 | 16.7 % | -25.4 | INSUFFISANT |
| absorption_sell | +4h | 6 | 0.0 % | -40.2 | INSUFFISANT |
| absorption_sell | +12h | 5 | 20.0 % | -124.2 | INSUFFISANT |
| sweep_high | +1h | 20 | 40.0 % | -9.4 | BRUIT (classé) |
| sweep_high | +4h | 20 | 45.0 % | -3.2 | BRUIT (classé) |
| sweep_high | +12h | 20 | 45.0 % | -31.2 | BRUIT (classé) |

### WIFUSDT — 3000 bougies 1h, 70 événements

train = 40 événements (70 % anciens) · val = 30 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 6 | 33.3 % | -8.0 | INSUFFISANT |
| absorption_buy | +4h | 6 | 0.0 % | -36.1 | INSUFFISANT |
| absorption_buy | +12h | 6 | 16.7 % | -40.6 | INSUFFISANT |
| sweep_low | +1h | 10 | 40.0 % | -8.0 | BRUIT (classé) |
| sweep_low | +4h | 10 | 60.0 % | +40.9 | PROMETTEUR (à confirmer) |
| sweep_low | +12h | 10 | 60.0 % | +28.6 | PROMETTEUR (à confirmer) |
| absorption_sell | +1h | 10 | 30.0 % | -8.0 | BRUIT (classé) |
| absorption_sell | +4h | 10 | 40.0 % | -15.1 | BRUIT (classé) |
| absorption_sell | +12h | 10 | 30.0 % | -97.3 | BRUIT (classé) |
| sweep_high | +1h | 14 | 42.9 % | -1.0 | BRUIT (classé) |
| sweep_high | +4h | 14 | 50.0 % | +55.2 | BRUIT (classé) |
| sweep_high | +12h | 14 | 57.1 % | +117.4 | PROMETTEUR (à confirmer) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 8 | 75.0 % | +97.6 | INSUFFISANT |
| absorption_buy | +4h | 8 | 62.5 % | +88.8 | INSUFFISANT |
| absorption_buy | +12h | 8 | 75.0 % | +398.4 | INSUFFISANT |
| sweep_low | +1h | 6 | 66.7 % | +43.1 | INSUFFISANT |
| sweep_low | +4h | 6 | 66.7 % | +150.4 | INSUFFISANT |
| sweep_low | +12h | 6 | 50.0 % | +152.6 | INSUFFISANT |
| absorption_sell | +1h | 4 | 50.0 % | +41.8 | INSUFFISANT |
| absorption_sell | +4h | 4 | 0.0 % | -112.3 | INSUFFISANT |
| absorption_sell | +12h | 4 | 25.0 % | -26.6 | INSUFFISANT |
| sweep_high | +1h | 12 | 33.3 % | -31.6 | BRUIT (classé) |
| sweep_high | +4h | 12 | 33.3 % | -125.1 | BRUIT (classé) |
| sweep_high | +12h | 11 | 27.3 % | -404.2 | BRUIT (classé) |

