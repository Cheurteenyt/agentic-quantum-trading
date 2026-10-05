# EXP-bonsai-h-18-univ10 — confirmation

Hypothèse : RÉPLICATION UNIVERSE : le squeeze (range_pct < 2.0 ET ret_1h < -0.3) porte un short 6h sur les 10 majeures

- spec_sha 2f753312a1efda4a · git ea993a8 · snapshot k1h-8425ef597534f306
- verdict : **CONFIRMED** · n 18902 · mean 0.35044764413209206

- BTCUSDT@6h : n 1381 · mean 0.319
- ETHUSDT@6h : n 1644 · mean 0.378
- SOLUSDT@6h : n 1904 · mean 0.405
- XRPUSDT@6h : n 1896 · mean 0.380
- BNBUSDT@6h : n 1481 · mean 0.363
- DOGEUSDT@6h : n 1932 · mean 0.440
- ADAUSDT@6h : n 2292 · mean 0.348
- AVAXUSDT@6h : n 2259 · mean 0.277
- LINKUSDT@6h : n 2169 · mean 0.314
- LTCUSDT@6h : n 1944 · mean 0.298

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (recomputed_train)

| métrique | valeur |
|---|---|
| trades pris / events bruts | 9347 / 19955 |
| solde final | $134.79 |
| ROI période | +34.79 % |
| DD max (MTM horaire) | 0.99 % |
| liquidations | 0 |
| WR | 59.0 % |
| mois négatifs | 0 / 13 |
| pire mois / record | +0.44$ / +5.33$ |
| ret/DD | 35.3 |
| frais payés | $31.18 · funding net $+0.33 |
| DD worst intrabar / close-seul | 1.05 % / 0.91 % |
| concurrence max / marge max engagée | 10 positions / 10.0 % de l'équité |
| CAGR / Sharpe portefeuille / Sortino portefeuille | +32.7 % / 6.93 / 11.38 |
| profit factor / Sortino trade-level (secondaire) | 1.76 / 31.9 |
| concentration PnL sans top 1 / 5 / 10 % | $127.33 / $110.62 / $96.99 |
| CONTRE-FACTUEL sans top 10 % (re-joué, tailles recalculées) | $118.85 (liq 0) |
| n brut / sans chevauchement / effectif | 9347 / 1292 / 1960.2 (autocorr +0.653 · 3592 buckets horaires) |
| bootstrap mean CI95 | [+0.000, +0.000] |
| bootstrap Sharpe portefeuille CI95 / t-stat CI95 | [+5.18, +8.63] / [+5.3, +8.8] |
| masse bootstrap mean > 0 | 0 réplications négatives / 2000 (blocs 24 h) |
| baseline long-and-hold 1x | $58.42 (ROI -41.58 %, DD 68.17 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.75 % · 2025-11 0.67 % · 2026-01 0.69 % · 2026-03 0.88 % · 2026-05 0.51 % · 2026-07 0.98 % (plafond 15 %) |
