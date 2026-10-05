# EXP-bonsai-h-31 — confirmation

Hypothèse : [H-31] High Volume Low Return Mean Reversion — ret_1h < 0.1 (falsification : ret_1h > 0.5)

- spec_sha 08b1685a5971ac12 · git ea993a8 · snapshot k1h-8425ef597534f306
- verdict : **CONFIRMED** · n 1195 · mean 1.5960257896111647

- BTCUSDT@1h : n 170 · mean 0.891
- ETHUSDT@1h : n 161 · mean 1.465
- SOLUSDT@1h : n 99 · mean 1.908
- XRPUSDT@1h : n 110 · mean 1.611
- BNBUSDT@1h : n 127 · mean 1.207
- DOGEUSDT@1h : n 106 · mean 2.003
- ADAUSDT@1h : n 113 · mean 1.799
- AVAXUSDT@1h : n 100 · mean 2.098
- LINKUSDT@1h : n 112 · mean 1.860
- LTCUSDT@1h : n 97 · mean 1.720

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (recomputed_train)

| métrique | valeur |
|---|---|
| trades pris / events bruts | 1260 / 1260 |
| solde final | $122.13 |
| ROI période | +22.13 % |
| DD max (MTM horaire) | 0.04 % |
| liquidations | 0 |
| WR | 99.6 % |
| mois négatifs | 0 / 13 |
| pire mois / record | +0.42$ / +2.68$ |
| ret/DD | 559.5 |
| frais payés | $3.94 · funding net $+0.01 |
| DD worst intrabar / close-seul | 0.38 % / 0.03 % |
| concurrence max / marge max engagée | 10 positions / 10.0 % de l'équité |
| CAGR / Sharpe portefeuille / Sortino portefeuille | +20.8 % / 9.79 / 88.73 |
| profit factor / Sortino trade-level (secondaire) | 2932.69 / 4748.0 |
| concentration PnL sans top 1 / 5 / 10 % | $120.79 / $118.36 / $116.07 |
| CONTRE-FACTUEL sans top 10 % (re-joué, tailles recalculées) | $115.51 (liq 0) |
| n brut / sans chevauchement / effectif | 1260 / 481 / 324.1 (autocorr +0.591 · 481 buckets horaires) |
| bootstrap mean CI95 | [+0.000, +0.000] |
| bootstrap Sharpe portefeuille CI95 / t-stat CI95 | [+8.74, +11.11] / [+8.9, +11.4] |
| masse bootstrap mean > 0 | 0 réplications négatives / 2000 (blocs 24 h) |
| baseline long-and-hold 1x | $58.42 (ROI -41.58 %, DD 68.17 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.03 % · 2025-11 0.03 % · 2026-01 0.04 % · 2026-03 0.04 % · 2026-05 0.03 % · 2026-07 0.02 % (plafond 15 %) |
