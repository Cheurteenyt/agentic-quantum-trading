# EXP-bonsai-h-18 — confirmation

Hypothèse : Volatility Squeeze Short

- spec_sha 8e9788e69c9fbb11 · git ea993a8 · snapshot k1h-bbb04c32ed0e1c22
- verdict : **CONFIRMED** · n 4929 · mean 0.3717657485075394

- BTCUSDT@6h : n 1381 · mean 0.319
- ETHUSDT@6h : n 1644 · mean 0.378
- SOLUSDT@6h : n 1904 · mean 0.405

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (recomputed_train)

| métrique | valeur |
|---|---|
| trades pris / events bruts | 2567 / 5181 |
| solde final | $109.11 |
| ROI période | +9.11 % |
| DD max (MTM horaire) | 0.45 % |
| liquidations | 0 |
| WR | 61.1 % |
| mois négatifs | 0 / 13 |
| pire mois / record | +0.21$ / +1.42$ |
| ret/DD | 20.5 |
| frais payés | $7.55 · funding net $+0.04 |
| DD worst intrabar / close-seul | 0.45 % / 0.44 % |
| concurrence max / marge max engagée | 3 positions / 3.0 % de l'équité |
| CAGR / Sharpe portefeuille / Sortino portefeuille | +8.6 % / 7.09 / 11.43 |
| profit factor / Sortino trade-level (secondaire) | 1.95 / 20.1 |
| concentration PnL sans top 1 / 5 / 10 % | $107.41 / $103.41 / $100.19 |
| CONTRE-FACTUEL sans top 10 % (re-joué, tailles recalculées) | $105.73 (liq 0) |
| n brut / sans chevauchement / effectif | 2567 / 1070 / 1058.0 (autocorr +0.416 · 1699 buckets horaires) |
| bootstrap mean CI95 | [+0.000, +0.000] |
| bootstrap Sharpe portefeuille CI95 / t-stat CI95 | [+5.39, +8.83] / [+5.5, +9.0] |
| masse bootstrap mean > 0 | 0 réplications négatives / 2000 (blocs 24 h) |
| baseline long-and-hold 1x | $66.78 (ROI -33.22 %, DD 63.69 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.29 % · 2025-11 0.21 % · 2026-01 0.24 % · 2026-03 0.37 % · 2026-05 0.15 % · 2026-07 0.18 % (plafond 15 %) |
