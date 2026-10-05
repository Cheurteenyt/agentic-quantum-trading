# EXP-bonsai-h-29 — confirmation

Hypothèse : [H-29] Momentum-Range Confirmation — ret_6h > 0.5 (falsification : ret_6h < 0.3)

- spec_sha 9ec1c3969a778b85 · git ea993a8 · snapshot k1h-8425ef597534f306
- verdict : **CONFIRMED** · n 5631 · mean 1.1237606534353581

- BTCUSDT@6h : n 668 · mean 0.670
- ETHUSDT@6h : n 663 · mean 1.013
- SOLUSDT@6h : n 403 · mean 1.460
- XRPUSDT@6h : n 612 · mean 1.206
- BNBUSDT@6h : n 648 · mean 0.797
- DOGEUSDT@6h : n 532 · mean 1.444
- ADAUSDT@6h : n 630 · mean 1.357
- AVAXUSDT@6h : n 437 · mean 1.482
- LINKUSDT@6h : n 541 · mean 1.187
- LTCUSDT@6h : n 497 · mean 0.914

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (recomputed_train)

| métrique | valeur |
|---|---|
| trades pris / events bruts | 3784 / 5942 |
| solde final | $150.82 |
| ROI période | +50.82 % |
| DD max (MTM horaire) | 0.88 % |
| liquidations | 0 |
| WR | 74.5 % |
| mois négatifs | 0 / 13 |
| pire mois / record | +2.00$ / +6.16$ |
| ret/DD | 57.7 |
| frais payés | $13.14 · funding net $-0.14 |
| DD worst intrabar / close-seul | 1.58 % / 0.82 % |
| concurrence max / marge max engagée | 10 positions / 10.1 % de l'équité |
| CAGR / Sharpe portefeuille / Sortino portefeuille | +47.6 % / 10.15 / 18.97 |
| profit factor / Sortino trade-level (secondaire) | 4.50 / 68.1 |
| concentration PnL sans top 1 / 5 / 10 % | $146.30 / $135.93 / $126.74 |
| CONTRE-FACTUEL sans top 10 % (re-joué, tailles recalculées) | $138.99 (liq 0) |
| n brut / sans chevauchement / effectif | 3784 / 776 / 982.0 (autocorr +0.588 · 1350 buckets horaires) |
| bootstrap mean CI95 | [+0.000, +0.000] |
| bootstrap Sharpe portefeuille CI95 / t-stat CI95 | [+8.56, +11.61] / [+8.7, +11.9] |
| masse bootstrap mean > 0 | 0 réplications négatives / 2000 (blocs 24 h) |
| baseline long-and-hold 1x | $58.42 (ROI -41.58 %, DD 68.17 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.41 % · 2025-11 0.88 % · 2026-01 0.85 % · 2026-03 0.28 % · 2026-05 0.54 % · 2026-07 0.63 % (plafond 15 %) |
