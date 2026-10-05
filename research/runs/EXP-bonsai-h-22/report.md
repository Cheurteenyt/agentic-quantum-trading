# EXP-bonsai-h-22 — confirmation

Hypothèse : [H-22] Volume Surge Reversion — ret_2h < 0.1 (falsification : ret_2h > 0.5)

- spec_sha be684a693c7e0f45 · git ea993a8 · snapshot k1h-8425ef597534f306
- verdict : **CONFIRMED** · n 3812 · mean 0.8949372375538487

- BTCUSDT@2h : n 445 · mean 0.537
- ETHUSDT@2h : n 447 · mean 0.926
- SOLUSDT@2h : n 347 · mean 1.130
- XRPUSDT@2h : n 390 · mean 0.860
- BNBUSDT@2h : n 392 · mean 0.697
- DOGEUSDT@2h : n 399 · mean 1.045
- ADAUSDT@2h : n 345 · mean 1.123
- AVAXUSDT@2h : n 348 · mean 0.912
- LINKUSDT@2h : n 354 · mean 0.986
- LTCUSDT@2h : n 345 · mean 0.833

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (recomputed_train)

| métrique | valeur |
|---|---|
| trades pris / events bruts | 3521 / 4003 |
| solde final | $135.32 |
| ROI période | +35.32 % |
| DD max (MTM horaire) | 0.21 % |
| liquidations | 0 |
| WR | 77.8 % |
| mois négatifs | 0 / 13 |
| pire mois / record | +0.81$ / +4.29$ |
| ret/DD | 170.5 |
| frais payés | $11.67 · funding net $+0.04 |
| DD worst intrabar / close-seul | 0.23 % / 0.12 % |
| concurrence max / marge max engagée | 10 positions / 10.0 % de l'équité |
| CAGR / Sharpe portefeuille / Sortino portefeuille | +33.2 % / 11.09 / 37.61 |
| profit factor / Sortino trade-level (secondaire) | 9.01 / 142.8 |
| concentration PnL sans top 1 / 5 / 10 % | $132.09 / $125.67 / $119.73 |
| CONTRE-FACTUEL sans top 10 % (re-joué, tailles recalculées) | $122.11 (liq 0) |
| n brut / sans chevauchement / effectif | 3521 / 1265 / 871.4 (autocorr +0.603 · 1552 buckets horaires) |
| bootstrap mean CI95 | [+0.000, +0.000] |
| bootstrap Sharpe portefeuille CI95 / t-stat CI95 | [+10.14, +12.28] / [+10.4, +12.6] |
| masse bootstrap mean > 0 | 0 réplications négatives / 2000 (blocs 24 h) |
| baseline long-and-hold 1x | $58.42 (ROI -41.58 %, DD 68.17 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.13 % · 2025-11 0.21 % · 2026-01 0.20 % · 2026-03 0.09 % · 2026-05 0.21 % · 2026-07 0.09 % (plafond 15 %) |
