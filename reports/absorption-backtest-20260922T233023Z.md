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

### ETHUSDT — 3000 bougies 1h, 166 événements

train = 117 événements (70 % anciens) · val = 49 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 21 | 38.1 % | -22.0 | BRUIT (classé) |
| absorption_buy | +4h | 21 | 38.1 % | -35.0 | BRUIT (classé) |
| absorption_buy | +12h | 21 | 33.3 % | -26.9 | BRUIT (classé) |
| sweep_low | +1h | 39 | 41.0 % | -21.7 | BRUIT (classé) |
| sweep_low | +4h | 39 | 59.0 % | +16.1 | PROMETTEUR (à confirmer) |
| sweep_low | +12h | 39 | 48.7 % | -0.1 | BRUIT (classé) |
| absorption_sell | +1h | 23 | 39.1 % | -15.9 | BRUIT (classé) |
| absorption_sell | +4h | 23 | 52.2 % | +2.1 | BRUIT (classé) |
| absorption_sell | +12h | 23 | 39.1 % | -41.9 | BRUIT (classé) |
| sweep_high | +1h | 34 | 32.4 % | -10.6 | BRUIT (classé) |
| sweep_high | +4h | 34 | 38.2 % | -11.0 | BRUIT (classé) |
| sweep_high | +12h | 34 | 47.1 % | -3.8 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 9 | 44.4 % | -6.2 | INSUFFISANT |
| absorption_buy | +4h | 9 | 33.3 % | -35.5 | INSUFFISANT |
| absorption_buy | +12h | 9 | 55.6 % | +54.5 | INSUFFISANT |
| sweep_low | +1h | 11 | 63.6 % | +14.5 | PROMETTEUR (à confirmer) |
| sweep_low | +4h | 11 | 63.6 % | +13.4 | PROMETTEUR (à confirmer) |
| sweep_low | +12h | 11 | 54.5 % | +17.3 | BRUIT (classé) |
| absorption_sell | +1h | 8 | 25.0 % | -28.1 | INSUFFISANT |
| absorption_sell | +4h | 8 | 37.5 % | -15.4 | INSUFFISANT |
| absorption_sell | +12h | 7 | 28.6 % | -37.5 | INSUFFISANT |
| sweep_high | +1h | 20 | 25.0 % | -28.5 | BRUIT (classé) |
| sweep_high | +4h | 20 | 50.0 % | +0.0 | BRUIT (classé) |
| sweep_high | +12h | 20 | 40.0 % | -25.6 | BRUIT (classé) |

### SOLUSDT — 3000 bougies 1h, 173 événements

train = 116 événements (70 % anciens) · val = 57 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 16 | 43.8 % | -1.7 | BRUIT (classé) |
| absorption_buy | +4h | 16 | 56.2 % | +17.9 | PROMETTEUR (à confirmer) |
| absorption_buy | +12h | 16 | 56.2 % | +16.8 | PROMETTEUR (à confirmer) |
| sweep_low | +1h | 43 | 46.5 % | -1.7 | BRUIT (classé) |
| sweep_low | +4h | 43 | 44.2 % | -17.6 | BRUIT (classé) |
| sweep_low | +12h | 43 | 44.2 % | -24.6 | BRUIT (classé) |
| absorption_sell | +1h | 18 | 66.7 % | +25.6 | PROMETTEUR (à confirmer) |
| absorption_sell | +4h | 18 | 38.9 % | -5.3 | BRUIT (classé) |
| absorption_sell | +12h | 18 | 66.7 % | +74.6 | PROMETTEUR (à confirmer) |
| sweep_high | +1h | 39 | 46.2 % | -6.7 | BRUIT (classé) |
| sweep_high | +4h | 39 | 51.3 % | +2.2 | BRUIT (classé) |
| sweep_high | +12h | 39 | 48.7 % | -2.9 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 4 | 0.0 % | -33.7 | INSUFFISANT |
| absorption_buy | +4h | 4 | 25.0 % | -15.4 | INSUFFISANT |
| absorption_buy | +12h | 4 | 75.0 % | +138.9 | INSUFFISANT |
| sweep_low | +1h | 14 | 35.7 % | -5.9 | BRUIT (classé) |
| sweep_low | +4h | 14 | 50.0 % | +1.4 | BRUIT (classé) |
| sweep_low | +12h | 14 | 42.9 % | -112.0 | BRUIT (classé) |
| absorption_sell | +1h | 14 | 35.7 % | -16.6 | BRUIT (classé) |
| absorption_sell | +4h | 14 | 35.7 % | -37.1 | BRUIT (classé) |
| absorption_sell | +12h | 14 | 21.4 % | -115.2 | BRUIT (classé) |
| sweep_high | +1h | 24 | 45.8 % | -2.8 | BRUIT (classé) |
| sweep_high | +4h | 24 | 37.5 % | -33.6 | BRUIT (classé) |
| sweep_high | +12h | 24 | 41.7 % | -98.8 | BRUIT (classé) |

### BNBUSDT — 3000 bougies 1h, 150 événements

train = 110 événements (70 % anciens) · val = 40 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 17 | 41.2 % | -7.7 | BRUIT (classé) |
| absorption_buy | +4h | 17 | 41.2 % | -3.0 | BRUIT (classé) |
| absorption_buy | +12h | 17 | 35.3 % | -36.4 | BRUIT (classé) |
| sweep_low | +1h | 37 | 35.1 % | -11.8 | BRUIT (classé) |
| sweep_low | +4h | 37 | 37.8 % | -9.9 | BRUIT (classé) |
| sweep_low | +12h | 37 | 35.1 % | -23.0 | BRUIT (classé) |
| absorption_sell | +1h | 16 | 68.8 % | +14.3 | PROMETTEUR (à confirmer) |
| absorption_sell | +4h | 16 | 25.0 % | -21.9 | BRUIT (classé) |
| absorption_sell | +12h | 16 | 25.0 % | -65.8 | BRUIT (classé) |
| sweep_high | +1h | 40 | 52.5 % | +1.1 | BRUIT (classé) |
| sweep_high | +4h | 40 | 50.0 % | +0.3 | BRUIT (classé) |
| sweep_high | +12h | 40 | 42.5 % | -11.0 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 4 | 25.0 % | -6.3 | INSUFFISANT |
| absorption_buy | +4h | 4 | 25.0 % | -18.7 | INSUFFISANT |
| absorption_buy | +12h | 4 | 75.0 % | +83.5 | INSUFFISANT |
| sweep_low | +1h | 13 | 38.5 % | -1.3 | BRUIT (classé) |
| sweep_low | +4h | 13 | 46.2 % | -42.1 | BRUIT (classé) |
| sweep_low | +12h | 13 | 38.5 % | -48.3 | BRUIT (classé) |
| absorption_sell | +1h | 5 | 60.0 % | +6.7 | INSUFFISANT |
| absorption_sell | +4h | 5 | 60.0 % | +36.8 | INSUFFISANT |
| absorption_sell | +12h | 4 | 50.0 % | +32.3 | INSUFFISANT |
| sweep_high | +1h | 18 | 22.2 % | -24.8 | BRUIT (classé) |
| sweep_high | +4h | 18 | 50.0 % | +3.5 | BRUIT (classé) |
| sweep_high | +12h | 18 | 33.3 % | -64.9 | BRUIT (classé) |

### DOGEUSDT — 3000 bougies 1h, 167 événements

train = 108 événements (70 % anciens) · val = 59 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 20 | 30.0 % | -8.0 | BRUIT (classé) |
| absorption_buy | +4h | 20 | 50.0 % | +0.3 | BRUIT (classé) |
| absorption_buy | +12h | 20 | 45.0 % | -9.1 | BRUIT (classé) |
| sweep_low | +1h | 38 | 60.5 % | +5.8 | PROMETTEUR (à confirmer) |
| sweep_low | +4h | 38 | 57.9 % | +7.8 | PROMETTEUR (à confirmer) |
| sweep_low | +12h | 38 | 47.4 % | -9.1 | BRUIT (classé) |
| absorption_sell | +1h | 21 | 52.4 % | +1.9 | BRUIT (classé) |
| absorption_sell | +4h | 21 | 66.7 % | +17.0 | PROMETTEUR (à confirmer) |
| absorption_sell | +12h | 21 | 61.9 % | +31.7 | PROMETTEUR (à confirmer) |
| sweep_high | +1h | 29 | 48.3 % | -4.0 | BRUIT (classé) |
| sweep_high | +4h | 29 | 65.5 % | +12.7 | PROMETTEUR (à confirmer) |
| sweep_high | +12h | 29 | 58.6 % | +29.0 | PROMETTEUR (à confirmer) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 13 | 15.4 % | -28.3 | BRUIT (classé) |
| absorption_buy | +4h | 13 | 53.8 % | +29.0 | BRUIT (classé) |
| absorption_buy | +12h | 13 | 46.2 % | -17.4 | BRUIT (classé) |
| sweep_low | +1h | 17 | 41.2 % | -10.4 | BRUIT (classé) |
| sweep_low | +4h | 17 | 64.7 % | +34.6 | PROMETTEUR (à confirmer) |
| sweep_low | +12h | 17 | 35.3 % | -44.0 | BRUIT (classé) |
| absorption_sell | +1h | 8 | 12.5 % | -32.8 | INSUFFISANT |
| absorption_sell | +4h | 8 | 50.0 % | +22.6 | INSUFFISANT |
| absorption_sell | +12h | 8 | 12.5 % | -79.5 | INSUFFISANT |
| sweep_high | +1h | 21 | 52.4 % | +19.2 | BRUIT (classé) |
| sweep_high | +4h | 21 | 61.9 % | +28.4 | PROMETTEUR (à confirmer) |
| sweep_high | +12h | 21 | 47.6 % | -43.2 | BRUIT (classé) |

### BOMEUSDT — 3000 bougies 1h, 47 événements

train = 19 événements (70 % anciens) · val = 28 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 3 | 33.3 % | -8.0 | INSUFFISANT |
| absorption_buy | +4h | 3 | 33.3 % | -8.0 | INSUFFISANT |
| absorption_buy | +12h | 3 | 33.3 % | -25.1 | INSUFFISANT |
| sweep_low | +1h | 6 | 33.3 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 6 | 33.3 % | -8.0 | INSUFFISANT |
| sweep_low | +12h | 6 | 50.0 % | +83.8 | INSUFFISANT |
| absorption_sell | +1h | 3 | 66.7 % | +197.6 | INSUFFISANT |
| absorption_sell | +4h | 3 | 100.0 % | +230.8 | INSUFFISANT |
| absorption_sell | +12h | 3 | 66.7 % | +33.8 | INSUFFISANT |
| sweep_high | +1h | 7 | 28.6 % | -82.3 | INSUFFISANT |
| sweep_high | +4h | 7 | 42.9 % | -8.0 | INSUFFISANT |
| sweep_high | +12h | 7 | 28.6 % | -8.0 | INSUFFISANT |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 5 | 40.0 % | -30.6 | INSUFFISANT |
| absorption_buy | +4h | 5 | 40.0 % | -2.9 | INSUFFISANT |
| absorption_buy | +12h | 5 | 60.0 % | +191.1 | INSUFFISANT |
| sweep_low | +1h | 8 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 8 | 75.0 % | +61.6 | INSUFFISANT |
| sweep_low | +12h | 8 | 87.5 % | +144.6 | INSUFFISANT |
| absorption_sell | +1h | 7 | 42.9 % | -8.0 | INSUFFISANT |
| absorption_sell | +4h | 7 | 14.3 % | -57.8 | INSUFFISANT |
| absorption_sell | +12h | 7 | 42.9 % | -61.7 | INSUFFISANT |
| sweep_high | +1h | 8 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_high | +4h | 8 | 75.0 % | +38.4 | INSUFFISANT |
| sweep_high | +12h | 8 | 37.5 % | -137.2 | INSUFFISANT |

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

### PNUTUSDT — 3000 bougies 1h, 36 événements

train = 30 événements (70 % anciens) · val = 6 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 5 | 40.0 % | -8.0 | INSUFFISANT |
| absorption_buy | +4h | 5 | 40.0 % | -61.5 | INSUFFISANT |
| absorption_buy | +12h | 5 | 40.0 % | -61.5 | INSUFFISANT |
| sweep_low | +1h | 13 | 53.8 % | +18.2 | BRUIT (classé) |
| sweep_low | +4h | 13 | 23.1 % | -98.5 | BRUIT (classé) |
| sweep_low | +12h | 13 | 46.2 % | -8.0 | BRUIT (classé) |
| sweep_high | +1h | 12 | 50.0 % | +13.6 | BRUIT (classé) |
| sweep_high | +4h | 12 | 50.0 % | +45.5 | BRUIT (classé) |
| sweep_high | +12h | 12 | 75.0 % | +162.9 | PROMETTEUR (à confirmer) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 1 | 0.0 % | -8.0 | INSUFFISANT |
| absorption_buy | +4h | 1 | 0.0 % | -8.0 | INSUFFISANT |
| absorption_buy | +12h | 1 | 100.0 % | +223.4 | INSUFFISANT |
| sweep_low | +1h | 1 | 0.0 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 1 | 100.0 % | +86.2 | INSUFFISANT |
| sweep_low | +12h | 1 | 100.0 % | +492.7 | INSUFFISANT |
| absorption_sell | +1h | 4 | 75.0 % | +62.5 | INSUFFISANT |
| absorption_sell | +4h | 4 | 25.0 % | -157.0 | INSUFFISANT |
| absorption_sell | +12h | 4 | 25.0 % | -135.7 | INSUFFISANT |

### MOODENGUSDT — 3000 bougies 1h, 25 événements

train = 15 événements (70 % anciens) · val = 10 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 1 | 0.0 % | -8.0 | INSUFFISANT |
| absorption_buy | +4h | 1 | 0.0 % | -8.0 | INSUFFISANT |
| absorption_buy | +12h | 1 | 0.0 % | -588.9 | INSUFFISANT |
| sweep_low | +1h | 8 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 8 | 37.5 % | -24.6 | INSUFFISANT |
| sweep_low | +12h | 8 | 12.5 % | -352.4 | INSUFFISANT |
| absorption_sell | +1h | 2 | 50.0 % | +52.7 | INSUFFISANT |
| absorption_sell | +4h | 2 | 50.0 % | +210.1 | INSUFFISANT |
| absorption_sell | +12h | 2 | 50.0 % | +129.2 | INSUFFISANT |
| sweep_high | +1h | 4 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_high | +4h | 4 | 50.0 % | +34.0 | INSUFFISANT |
| sweep_high | +12h | 4 | 75.0 % | +70.8 | INSUFFISANT |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 1 | 0.0 % | -132.6 | INSUFFISANT |
| absorption_buy | +4h | 1 | 0.0 % | -111.0 | INSUFFISANT |
| absorption_buy | +12h | 1 | 0.0 % | -305.1 | INSUFFISANT |
| sweep_low | +1h | 4 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 4 | 25.0 % | -113.7 | INSUFFISANT |
| sweep_low | +12h | 4 | 75.0 % | +355.2 | INSUFFISANT |
| absorption_sell | +1h | 1 | 100.0 % | +38.0 | INSUFFISANT |
| absorption_sell | +4h | 1 | 0.0 % | -178.9 | INSUFFISANT |
| absorption_sell | +12h | 1 | 0.0 % | -10.2 | INSUFFISANT |
| sweep_high | +1h | 4 | 75.0 % | +23.9 | INSUFFISANT |
| sweep_high | +4h | 4 | 0.0 % | -110.7 | INSUFFISANT |
| sweep_high | +12h | 4 | 0.0 % | -140.3 | INSUFFISANT |

### NEIROUSDT — 3000 bougies 1h, 48 événements

train = 17 événements (70 % anciens) · val = 31 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 2 | 50.0 % | +100.5 | INSUFFISANT |
| absorption_buy | +4h | 2 | 50.0 % | +267.2 | INSUFFISANT |
| absorption_buy | +12h | 2 | 50.0 % | +76.1 | INSUFFISANT |
| sweep_low | +1h | 4 | 0.0 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 4 | 50.0 % | +98.2 | INSUFFISANT |
| sweep_low | +12h | 4 | 25.0 % | -8.0 | INSUFFISANT |
| absorption_sell | +1h | 6 | 16.7 % | -8.0 | INSUFFISANT |
| absorption_sell | +4h | 6 | 50.0 % | +20.9 | INSUFFISANT |
| absorption_sell | +12h | 6 | 66.7 % | +389.9 | INSUFFISANT |
| sweep_high | +1h | 5 | 0.0 % | -8.0 | INSUFFISANT |
| sweep_high | +4h | 5 | 0.0 % | -178.2 | INSUFFISANT |
| sweep_high | +12h | 5 | 40.0 % | -138.4 | INSUFFISANT |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 7 | 57.1 % | +117.1 | INSUFFISANT |
| absorption_buy | +4h | 7 | 42.9 % | -110.5 | INSUFFISANT |
| absorption_buy | +12h | 7 | 57.1 % | +429.8 | INSUFFISANT |
| sweep_low | +1h | 7 | 71.4 % | +71.8 | INSUFFISANT |
| sweep_low | +4h | 7 | 85.7 % | +115.7 | INSUFFISANT |
| sweep_low | +12h | 7 | 71.4 % | +129.2 | INSUFFISANT |
| absorption_sell | +1h | 7 | 42.9 % | -8.0 | INSUFFISANT |
| absorption_sell | +4h | 7 | 42.9 % | -78.9 | INSUFFISANT |
| absorption_sell | +12h | 7 | 42.9 % | -113.2 | INSUFFISANT |
| sweep_high | +1h | 10 | 60.0 % | +42.1 | PROMETTEUR (à confirmer) |
| sweep_high | +4h | 10 | 60.0 % | +87.9 | PROMETTEUR (à confirmer) |
| sweep_high | +12h | 10 | 60.0 % | +144.3 | PROMETTEUR (à confirmer) |

### TURBOUSDT — 3000 bougies 1h, 48 événements

train = 29 événements (70 % anciens) · val = 19 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 9 | 33.3 % | -8.0 | INSUFFISANT |
| absorption_buy | +4h | 9 | 33.3 % | -16.9 | INSUFFISANT |
| absorption_buy | +12h | 9 | 44.4 % | -28.3 | INSUFFISANT |
| sweep_low | +1h | 8 | 12.5 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 8 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_low | +12h | 8 | 12.5 % | -91.8 | INSUFFISANT |
| absorption_sell | +1h | 6 | 66.7 % | +34.5 | INSUFFISANT |
| absorption_sell | +4h | 6 | 66.7 % | +66.9 | INSUFFISANT |
| absorption_sell | +12h | 6 | 83.3 % | +134.0 | INSUFFISANT |
| sweep_high | +1h | 6 | 16.7 % | -8.0 | INSUFFISANT |
| sweep_high | +4h | 6 | 33.3 % | -20.0 | INSUFFISANT |
| sweep_high | +12h | 6 | 66.7 % | +142.3 | INSUFFISANT |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 1 | 100.0 % | +39.4 | INSUFFISANT |
| absorption_buy | +4h | 1 | 0.0 % | -671.3 | INSUFFISANT |
| absorption_buy | +12h | 1 | 0.0 % | -673.1 | INSUFFISANT |
| sweep_low | +1h | 7 | 57.1 % | +3.0 | INSUFFISANT |
| sweep_low | +4h | 7 | 28.6 % | -86.7 | INSUFFISANT |
| sweep_low | +12h | 7 | 57.1 % | +44.1 | INSUFFISANT |
| absorption_sell | +1h | 4 | 25.0 % | -8.0 | INSUFFISANT |
| absorption_sell | +4h | 4 | 25.0 % | -8.0 | INSUFFISANT |
| absorption_sell | +12h | 4 | 75.0 % | +687.6 | INSUFFISANT |
| sweep_high | +1h | 7 | 57.1 % | +5.2 | INSUFFISANT |
| sweep_high | +4h | 7 | 57.1 % | +5.2 | INSUFFISANT |
| sweep_high | +12h | 7 | 28.6 % | -440.2 | INSUFFISANT |

### PENGUUSDT — 3000 bougies 1h, 159 événements

train = 110 événements (70 % anciens) · val = 49 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 26 | 42.3 % | -3.2 | BRUIT (classé) |
| absorption_buy | +4h | 26 | 38.5 % | -51.1 | BRUIT (classé) |
| absorption_buy | +12h | 26 | 26.9 % | -107.3 | BRUIT (classé) |
| sweep_low | +1h | 41 | 43.9 % | -8.0 | BRUIT (classé) |
| sweep_low | +4h | 41 | 43.9 % | -24.0 | BRUIT (classé) |
| sweep_low | +12h | 41 | 43.9 % | -52.3 | BRUIT (classé) |
| absorption_sell | +1h | 16 | 37.5 % | -4.6 | BRUIT (classé) |
| absorption_sell | +4h | 16 | 50.0 % | +7.0 | BRUIT (classé) |
| absorption_sell | +12h | 16 | 56.2 % | +13.6 | PROMETTEUR (à confirmer) |
| sweep_high | +1h | 27 | 37.0 % | -24.7 | BRUIT (classé) |
| sweep_high | +4h | 27 | 63.0 % | +65.6 | PROMETTEUR (à confirmer) |
| sweep_high | +12h | 27 | 48.1 % | -14.5 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 9 | 55.6 % | +11.6 | INSUFFISANT |
| absorption_buy | +4h | 9 | 66.7 % | +46.3 | INSUFFISANT |
| absorption_buy | +12h | 8 | 37.5 % | -24.5 | INSUFFISANT |
| sweep_low | +1h | 13 | 46.2 % | -8.0 | BRUIT (classé) |
| sweep_low | +4h | 13 | 38.5 % | -47.3 | BRUIT (classé) |
| sweep_low | +12h | 13 | 15.4 % | -96.2 | BRUIT (classé) |
| absorption_sell | +1h | 8 | 37.5 % | -8.0 | INSUFFISANT |
| absorption_sell | +4h | 8 | 50.0 % | +11.7 | INSUFFISANT |
| absorption_sell | +12h | 8 | 50.0 % | +80.2 | INSUFFISANT |
| sweep_high | +1h | 19 | 47.4 % | -25.6 | BRUIT (classé) |
| sweep_high | +4h | 18 | 55.6 % | +151.8 | PROMETTEUR (à confirmer) |
| sweep_high | +12h | 18 | 50.0 % | +199.3 | BRUIT (classé) |

### NOTUSDT — 3000 bougies 1h, 32 événements

train = 17 événements (70 % anciens) · val = 15 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 3 | 0.0 % | -146.3 | INSUFFISANT |
| absorption_buy | +4h | 3 | 66.7 % | +29.3 | INSUFFISANT |
| absorption_buy | +12h | 3 | 66.7 % | +42.5 | INSUFFISANT |
| sweep_low | +1h | 4 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 4 | 50.0 % | +29.3 | INSUFFISANT |
| sweep_low | +12h | 4 | 25.0 % | -71.0 | INSUFFISANT |
| absorption_sell | +1h | 2 | 0.0 % | -8.0 | INSUFFISANT |
| absorption_sell | +4h | 2 | 50.0 % | +107.2 | INSUFFISANT |
| absorption_sell | +12h | 2 | 50.0 % | +160.1 | INSUFFISANT |
| sweep_high | +1h | 8 | 62.5 % | +87.1 | INSUFFISANT |
| sweep_high | +4h | 8 | 75.0 % | +208.1 | INSUFFISANT |
| sweep_high | +12h | 8 | 87.5 % | +162.5 | INSUFFISANT |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 4 | 0.0 % | -20.7 | INSUFFISANT |
| absorption_buy | +4h | 4 | 75.0 % | +34.4 | INSUFFISANT |
| absorption_buy | +12h | 4 | 50.0 % | +66.7 | INSUFFISANT |
| sweep_low | +1h | 2 | 0.0 % | -8.0 | INSUFFISANT |
| sweep_low | +4h | 2 | 100.0 % | +198.4 | INSUFFISANT |
| sweep_low | +12h | 2 | 100.0 % | +120.5 | INSUFFISANT |
| absorption_sell | +1h | 5 | 20.0 % | -8.0 | INSUFFISANT |
| absorption_sell | +4h | 5 | 20.0 % | -8.0 | INSUFFISANT |
| absorption_sell | +12h | 5 | 20.0 % | -148.3 | INSUFFISANT |
| sweep_high | +1h | 4 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_high | +4h | 4 | 25.0 % | -8.0 | INSUFFISANT |
| sweep_high | +12h | 4 | 50.0 % | +15.2 | INSUFFISANT |

### DOGSUSDT — 3000 bougies 1h, 67 événements

train = 42 événements (70 % anciens) · val = 25 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 12 | 16.7 % | -8.0 | BRUIT (classé) |
| absorption_buy | +4h | 12 | 50.0 % | +19.0 | BRUIT (classé) |
| absorption_buy | +12h | 12 | 66.7 % | +101.2 | PROMETTEUR (à confirmer) |
| sweep_low | +1h | 7 | 14.3 % | -28.3 | INSUFFISANT |
| sweep_low | +4h | 7 | 57.1 % | +5.6 | INSUFFISANT |
| sweep_low | +12h | 7 | 42.9 % | -59.8 | INSUFFISANT |
| absorption_sell | +1h | 7 | 14.3 % | -32.6 | INSUFFISANT |
| absorption_sell | +4h | 7 | 57.1 % | +36.3 | INSUFFISANT |
| absorption_sell | +12h | 7 | 85.7 % | +219.3 | INSUFFISANT |
| sweep_high | +1h | 16 | 31.2 % | -8.0 | BRUIT (classé) |
| sweep_high | +4h | 16 | 50.0 % | +2.6 | BRUIT (classé) |
| sweep_high | +12h | 16 | 68.8 % | +180.2 | PROMETTEUR (à confirmer) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 2 | 50.0 % | +206.7 | INSUFFISANT |
| absorption_buy | +4h | 2 | 0.0 % | -90.0 | INSUFFISANT |
| absorption_buy | +12h | 2 | 0.0 % | -191.4 | INSUFFISANT |
| sweep_low | +1h | 5 | 20.0 % | -57.9 | INSUFFISANT |
| sweep_low | +4h | 5 | 40.0 % | -57.7 | INSUFFISANT |
| sweep_low | +12h | 5 | 20.0 % | -217.2 | INSUFFISANT |
| absorption_sell | +1h | 6 | 50.0 % | +29.0 | INSUFFISANT |
| absorption_sell | +4h | 6 | 33.3 % | -36.9 | INSUFFISANT |
| absorption_sell | +12h | 6 | 83.3 % | +56.8 | INSUFFISANT |
| sweep_high | +1h | 12 | 33.3 % | -8.0 | BRUIT (classé) |
| sweep_high | +4h | 12 | 50.0 % | +13.8 | BRUIT (classé) |
| sweep_high | +12h | 12 | 41.7 % | -22.2 | BRUIT (classé) |

### TRUMPUSDT — 3000 bougies 1h, 145 événements

train = 92 événements (70 % anciens) · val = 53 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 15 | 60.0 % | +14.7 | PROMETTEUR (à confirmer) |
| absorption_buy | +4h | 15 | 26.7 % | -40.0 | BRUIT (classé) |
| absorption_buy | +12h | 15 | 46.7 % | -23.8 | BRUIT (classé) |
| sweep_low | +1h | 41 | 48.8 % | -8.0 | BRUIT (classé) |
| sweep_low | +4h | 41 | 43.9 % | -20.4 | BRUIT (classé) |
| sweep_low | +12h | 41 | 46.3 % | -20.4 | BRUIT (classé) |
| absorption_sell | +1h | 13 | 38.5 % | -26.4 | BRUIT (classé) |
| absorption_sell | +4h | 13 | 53.8 % | +65.9 | BRUIT (classé) |
| absorption_sell | +12h | 13 | 69.2 % | +53.9 | PROMETTEUR (à confirmer) |
| sweep_high | +1h | 23 | 52.2 % | +2.9 | BRUIT (classé) |
| sweep_high | +4h | 23 | 52.2 % | +17.1 | BRUIT (classé) |
| sweep_high | +12h | 23 | 56.5 % | +39.0 | PROMETTEUR (à confirmer) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 10 | 30.0 % | -41.9 | BRUIT (classé) |
| absorption_buy | +4h | 10 | 60.0 % | +88.1 | PROMETTEUR (à confirmer) |
| absorption_buy | +12h | 10 | 20.0 % | -138.7 | BRUIT (classé) |
| sweep_low | +1h | 20 | 35.0 % | -35.4 | BRUIT (classé) |
| sweep_low | +4h | 20 | 45.0 % | -12.6 | BRUIT (classé) |
| sweep_low | +12h | 20 | 35.0 % | -45.0 | BRUIT (classé) |
| absorption_sell | +1h | 11 | 54.5 % | +43.6 | BRUIT (classé) |
| absorption_sell | +4h | 11 | 54.5 % | +7.0 | BRUIT (classé) |
| absorption_sell | +12h | 11 | 45.5 % | -65.8 | BRUIT (classé) |
| sweep_high | +1h | 12 | 50.0 % | +51.0 | BRUIT (classé) |
| sweep_high | +4h | 12 | 41.7 % | -0.8 | BRUIT (classé) |
| sweep_high | +12h | 12 | 41.7 % | -39.7 | BRUIT (classé) |

### FARTCOINUSDT — 3000 bougies 1h, 117 événements

train = 79 événements (70 % anciens) · val = 38 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 18 | 38.9 % | -8.0 | BRUIT (classé) |
| absorption_buy | +4h | 18 | 33.3 % | -73.3 | BRUIT (classé) |
| absorption_buy | +12h | 18 | 38.9 % | -184.1 | BRUIT (classé) |
| sweep_low | +1h | 30 | 40.0 % | -8.0 | BRUIT (classé) |
| sweep_low | +4h | 30 | 40.0 % | -57.6 | BRUIT (classé) |
| sweep_low | +12h | 30 | 40.0 % | -84.3 | BRUIT (classé) |
| absorption_sell | +1h | 9 | 55.6 % | +17.6 | INSUFFISANT |
| absorption_sell | +4h | 9 | 66.7 % | +164.5 | INSUFFISANT |
| absorption_sell | +12h | 9 | 55.6 % | +162.9 | INSUFFISANT |
| sweep_high | +1h | 22 | 45.5 % | -0.9 | BRUIT (classé) |
| sweep_high | +4h | 22 | 54.5 % | +19.2 | BRUIT (classé) |
| sweep_high | +12h | 22 | 63.6 % | +75.8 | PROMETTEUR (à confirmer) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 9 | 44.4 % | -14.1 | INSUFFISANT |
| absorption_buy | +4h | 9 | 44.4 % | -178.3 | INSUFFISANT |
| absorption_buy | +12h | 9 | 33.3 % | -284.7 | INSUFFISANT |
| sweep_low | +1h | 5 | 60.0 % | +6.2 | INSUFFISANT |
| sweep_low | +4h | 5 | 40.0 % | -1.8 | INSUFFISANT |
| sweep_low | +12h | 5 | 40.0 % | -324.6 | INSUFFISANT |
| absorption_sell | +1h | 7 | 71.4 % | +24.1 | INSUFFISANT |
| absorption_sell | +4h | 7 | 42.9 % | -8.0 | INSUFFISANT |
| absorption_sell | +12h | 7 | 14.3 % | -267.1 | INSUFFISANT |
| sweep_high | +1h | 17 | 47.1 % | -1.0 | BRUIT (classé) |
| sweep_high | +4h | 17 | 52.9 % | +6.0 | BRUIT (classé) |
| sweep_high | +12h | 17 | 41.2 % | -45.7 | BRUIT (classé) |

### 1000PEPEUSDT — 3000 bougies 1h, 169 événements

train = 113 événements (70 % anciens) · val = 56 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 23 | 52.2 % | +2.8 | BRUIT (classé) |
| absorption_buy | +4h | 23 | 43.5 % | -5.9 | BRUIT (classé) |
| absorption_buy | +12h | 23 | 34.8 % | -73.3 | BRUIT (classé) |
| sweep_low | +1h | 49 | 55.1 % | +8.5 | PROMETTEUR (à confirmer) |
| sweep_low | +4h | 49 | 51.0 % | +0.7 | BRUIT (classé) |
| sweep_low | +12h | 49 | 61.2 % | +39.9 | PROMETTEUR (à confirmer) |
| absorption_sell | +1h | 17 | 47.1 % | -10.3 | BRUIT (classé) |
| absorption_sell | +4h | 17 | 35.3 % | -34.3 | BRUIT (classé) |
| absorption_sell | +12h | 17 | 41.2 % | -45.2 | BRUIT (classé) |
| sweep_high | +1h | 24 | 37.5 % | -57.4 | BRUIT (classé) |
| sweep_high | +4h | 24 | 58.3 % | +50.6 | PROMETTEUR (à confirmer) |
| sweep_high | +12h | 24 | 45.8 % | -9.1 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 15 | 60.0 % | +4.7 | PROMETTEUR (à confirmer) |
| absorption_buy | +4h | 15 | 53.3 % | +4.4 | BRUIT (classé) |
| absorption_buy | +12h | 15 | 40.0 % | -78.7 | BRUIT (classé) |
| sweep_low | +1h | 12 | 33.3 % | -46.0 | BRUIT (classé) |
| sweep_low | +4h | 12 | 58.3 % | +17.3 | PROMETTEUR (à confirmer) |
| sweep_low | +12h | 12 | 50.0 % | +17.7 | BRUIT (classé) |
| absorption_sell | +1h | 6 | 50.0 % | +32.3 | INSUFFISANT |
| absorption_sell | +4h | 6 | 50.0 % | +107.5 | INSUFFISANT |
| absorption_sell | +12h | 6 | 50.0 % | +228.6 | INSUFFISANT |
| sweep_high | +1h | 23 | 56.5 % | +25.1 | PROMETTEUR (à confirmer) |
| sweep_high | +4h | 23 | 52.2 % | +2.0 | BRUIT (classé) |
| sweep_high | +12h | 23 | 47.8 % | -13.0 | BRUIT (classé) |

### DRAMUSDT — 3000 bougies 1h, 164 événements

train = 133 événements (70 % anciens) · val = 31 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 36 | 50.0 % | +5.3 | BRUIT (classé) |
| absorption_buy | +4h | 36 | 55.6 % | +83.8 | PROMETTEUR (à confirmer) |
| absorption_buy | +12h | 36 | 55.6 % | +97.2 | PROMETTEUR (à confirmer) |
| sweep_low | +1h | 33 | 60.6 % | +26.1 | PROMETTEUR (à confirmer) |
| sweep_low | +4h | 33 | 51.5 % | +9.9 | BRUIT (classé) |
| sweep_low | +12h | 33 | 54.5 % | +78.7 | BRUIT (classé) |
| absorption_sell | +1h | 26 | 42.3 % | -26.2 | BRUIT (classé) |
| absorption_sell | +4h | 26 | 38.5 % | -20.2 | BRUIT (classé) |
| absorption_sell | +12h | 26 | 50.0 % | +46.9 | BRUIT (classé) |
| sweep_high | +1h | 38 | 34.2 % | -8.0 | BRUIT (classé) |
| sweep_high | +4h | 38 | 50.0 % | +2.6 | BRUIT (classé) |
| sweep_high | +12h | 38 | 50.0 % | +19.3 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 3 | 33.3 % | -16.5 | INSUFFISANT |
| absorption_buy | +4h | 3 | 33.3 % | -59.1 | INSUFFISANT |
| absorption_buy | +12h | 3 | 66.7 % | +223.7 | INSUFFISANT |
| sweep_low | +1h | 11 | 72.7 % | +23.0 | PROMETTEUR (à confirmer) |
| sweep_low | +4h | 11 | 45.5 % | -0.7 | BRUIT (classé) |
| sweep_low | +12h | 11 | 63.6 % | +16.1 | PROMETTEUR (à confirmer) |
| absorption_sell | +1h | 8 | 87.5 % | +64.4 | INSUFFISANT |
| absorption_sell | +4h | 8 | 62.5 % | +105.7 | INSUFFISANT |
| absorption_sell | +12h | 8 | 50.0 % | +119.1 | INSUFFISANT |
| sweep_high | +1h | 9 | 44.4 % | -8.0 | INSUFFISANT |
| sweep_high | +4h | 9 | 44.4 % | -35.8 | INSUFFISANT |
| sweep_high | +12h | 9 | 55.6 % | +17.3 | INSUFFISANT |

### PIEVERSEUSDT — 3000 bougies 1h, 88 événements

train = 60 événements (70 % anciens) · val = 28 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 15 | 46.7 % | -0.4 | BRUIT (classé) |
| absorption_buy | +4h | 15 | 53.3 % | +25.9 | BRUIT (classé) |
| absorption_buy | +12h | 15 | 66.7 % | +18.4 | PROMETTEUR (à confirmer) |
| sweep_low | +1h | 18 | 38.9 % | -8.0 | BRUIT (classé) |
| sweep_low | +4h | 18 | 38.9 % | -8.0 | BRUIT (classé) |
| sweep_low | +12h | 18 | 55.6 % | +33.2 | PROMETTEUR (à confirmer) |
| absorption_sell | +1h | 5 | 20.0 % | -69.5 | INSUFFISANT |
| absorption_sell | +4h | 5 | 20.0 % | -409.7 | INSUFFISANT |
| absorption_sell | +12h | 5 | 40.0 % | -326.8 | INSUFFISANT |
| sweep_high | +1h | 22 | 27.3 % | -12.5 | BRUIT (classé) |
| sweep_high | +4h | 22 | 27.3 % | -57.4 | BRUIT (classé) |
| sweep_high | +12h | 22 | 36.4 % | -124.4 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 6 | 33.3 % | -20.2 | INSUFFISANT |
| absorption_buy | +4h | 6 | 33.3 % | -83.8 | INSUFFISANT |
| absorption_buy | +12h | 6 | 16.7 % | -289.8 | INSUFFISANT |
| sweep_low | +1h | 5 | 20.0 % | -42.3 | INSUFFISANT |
| sweep_low | +4h | 5 | 40.0 % | -39.6 | INSUFFISANT |
| sweep_low | +12h | 5 | 80.0 % | +87.7 | INSUFFISANT |
| absorption_sell | +1h | 4 | 75.0 % | +129.8 | INSUFFISANT |
| absorption_sell | +4h | 4 | 100.0 % | +322.2 | INSUFFISANT |
| absorption_sell | +12h | 4 | 100.0 % | +537.1 | INSUFFISANT |
| sweep_high | +1h | 13 | 38.5 % | -39.2 | BRUIT (classé) |
| sweep_high | +4h | 13 | 53.8 % | +8.1 | BRUIT (classé) |
| sweep_high | +12h | 13 | 38.5 % | -160.9 | BRUIT (classé) |

### LABUSDT — 3000 bougies 1h, 183 événements

train = 141 événements (70 % anciens) · val = 42 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 25 | 44.0 % | -8.0 | BRUIT (classé) |
| absorption_buy | +4h | 25 | 32.0 % | -70.4 | BRUIT (classé) |
| absorption_buy | +12h | 25 | 52.0 % | +51.4 | BRUIT (classé) |
| sweep_low | +1h | 37 | 27.0 % | -111.6 | BRUIT (classé) |
| sweep_low | +4h | 37 | 37.8 % | -74.6 | BRUIT (classé) |
| sweep_low | +12h | 37 | 43.2 % | -105.4 | BRUIT (classé) |
| absorption_sell | +1h | 38 | 34.2 % | -20.9 | BRUIT (classé) |
| absorption_sell | +4h | 38 | 68.4 % | +142.5 | PROMETTEUR (à confirmer) |
| absorption_sell | +12h | 38 | 73.7 % | +260.1 | PROMETTEUR (à confirmer) |
| sweep_high | +1h | 41 | 43.9 % | -35.1 | BRUIT (classé) |
| sweep_high | +4h | 41 | 46.3 % | -26.7 | BRUIT (classé) |
| sweep_high | +12h | 41 | 58.5 % | +102.2 | PROMETTEUR (à confirmer) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 9 | 66.7 % | +16.6 | INSUFFISANT |
| absorption_buy | +4h | 8 | 50.0 % | +22.2 | INSUFFISANT |
| absorption_buy | +12h | 8 | 25.0 % | -180.4 | INSUFFISANT |
| sweep_low | +1h | 8 | 25.0 % | -32.4 | INSUFFISANT |
| sweep_low | +4h | 8 | 25.0 % | -29.2 | INSUFFISANT |
| sweep_low | +12h | 8 | 37.5 % | -39.2 | INSUFFISANT |
| absorption_sell | +1h | 8 | 62.5 % | +16.4 | INSUFFISANT |
| absorption_sell | +4h | 8 | 50.0 % | +20.3 | INSUFFISANT |
| absorption_sell | +12h | 8 | 75.0 % | +212.7 | INSUFFISANT |
| sweep_high | +1h | 17 | 47.1 % | -8.0 | BRUIT (classé) |
| sweep_high | +4h | 17 | 47.1 % | -20.1 | BRUIT (classé) |
| sweep_high | +12h | 17 | 64.7 % | +192.8 | PROMETTEUR (à confirmer) |

### HYPEUSDT — 3000 bougies 1h, 177 événements

train = 118 événements (70 % anciens) · val = 59 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 23 | 43.5 % | -21.8 | BRUIT (classé) |
| absorption_buy | +4h | 23 | 47.8 % | -15.5 | BRUIT (classé) |
| absorption_buy | +12h | 23 | 60.9 % | +55.5 | PROMETTEUR (à confirmer) |
| sweep_low | +1h | 33 | 51.5 % | +0.4 | BRUIT (classé) |
| sweep_low | +4h | 33 | 66.7 % | +31.6 | PROMETTEUR (à confirmer) |
| sweep_low | +12h | 33 | 66.7 % | +106.0 | PROMETTEUR (à confirmer) |
| absorption_sell | +1h | 20 | 65.0 % | +34.5 | PROMETTEUR (à confirmer) |
| absorption_sell | +4h | 20 | 70.0 % | +32.1 | PROMETTEUR (à confirmer) |
| absorption_sell | +12h | 20 | 65.0 % | +99.3 | PROMETTEUR (à confirmer) |
| sweep_high | +1h | 42 | 59.5 % | +11.7 | PROMETTEUR (à confirmer) |
| sweep_high | +4h | 42 | 54.8 % | +21.1 | BRUIT (classé) |
| sweep_high | +12h | 42 | 47.6 % | -11.5 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 15 | 46.7 % | -10.8 | BRUIT (classé) |
| absorption_buy | +4h | 15 | 46.7 % | -20.1 | BRUIT (classé) |
| absorption_buy | +12h | 15 | 73.3 % | +96.3 | PROMETTEUR (à confirmer) |
| sweep_low | +1h | 16 | 50.0 % | +3.4 | BRUIT (classé) |
| sweep_low | +4h | 16 | 37.5 % | -22.4 | BRUIT (classé) |
| sweep_low | +12h | 16 | 68.8 % | +52.6 | PROMETTEUR (à confirmer) |
| absorption_sell | +1h | 10 | 40.0 % | -11.9 | BRUIT (classé) |
| absorption_sell | +4h | 10 | 40.0 % | -20.5 | BRUIT (classé) |
| absorption_sell | +12h | 9 | 22.2 % | -41.4 | INSUFFISANT |
| sweep_high | +1h | 18 | 44.4 % | -16.0 | BRUIT (classé) |
| sweep_high | +4h | 18 | 55.6 % | +13.3 | PROMETTEUR (à confirmer) |
| sweep_high | +12h | 18 | 38.9 % | -28.7 | BRUIT (classé) |

### HUSDT — 3000 bougies 1h, 167 événements

train = 122 événements (70 % anciens) · val = 45 (30 % récents).
Coûts : 8 bps aller-retour. Slippage non inclus.

### Train (70 %)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 30 | 43.3 % | -2.7 | BRUIT (classé) |
| absorption_buy | +4h | 30 | 60.0 % | +20.5 | PROMETTEUR (à confirmer) |
| absorption_buy | +12h | 30 | 50.0 % | +66.9 | BRUIT (classé) |
| sweep_low | +1h | 20 | 40.0 % | -51.8 | BRUIT (classé) |
| sweep_low | +4h | 20 | 30.0 % | -195.2 | BRUIT (classé) |
| sweep_low | +12h | 20 | 60.0 % | +230.7 | PROMETTEUR (à confirmer) |
| absorption_sell | +1h | 23 | 34.8 % | -49.2 | BRUIT (classé) |
| absorption_sell | +4h | 23 | 30.4 % | -127.1 | BRUIT (classé) |
| absorption_sell | +12h | 23 | 56.5 % | +27.0 | PROMETTEUR (à confirmer) |
| sweep_high | +1h | 49 | 42.9 % | -36.4 | BRUIT (classé) |
| sweep_high | +4h | 49 | 38.8 % | -26.3 | BRUIT (classé) |
| sweep_high | +12h | 49 | 49.0 % | -0.9 | BRUIT (classé) |

### Val (30 % récents)

| événement | horizon | N | winrate | médiane bps | verdict |
|---|---|---|---|---|---|
| absorption_buy | +1h | 8 | 25.0 % | -43.1 | INSUFFISANT |
| absorption_buy | +4h | 8 | 50.0 % | +29.3 | INSUFFISANT |
| absorption_buy | +12h | 8 | 37.5 % | -217.3 | INSUFFISANT |
| sweep_low | +1h | 18 | 27.8 % | -18.2 | BRUIT (classé) |
| sweep_low | +4h | 18 | 38.9 % | -19.4 | BRUIT (classé) |
| sweep_low | +12h | 18 | 38.9 % | -64.8 | BRUIT (classé) |
| absorption_sell | +1h | 6 | 33.3 % | -16.6 | INSUFFISANT |
| absorption_sell | +4h | 6 | 33.3 % | -9.4 | INSUFFISANT |
| absorption_sell | +12h | 6 | 83.3 % | +105.2 | INSUFFISANT |
| sweep_high | +1h | 13 | 38.5 % | -29.4 | BRUIT (classé) |
| sweep_high | +4h | 13 | 53.8 % | +12.6 | BRUIT (classé) |
| sweep_high | +12h | 13 | 53.8 % | +60.7 | BRUIT (classé) |

