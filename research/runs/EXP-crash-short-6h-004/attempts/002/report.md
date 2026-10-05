# EXP-crash-short-6h-004 — confirmation

Hypothèse : Une bougie de -X % (ret_1h <= p10 expanding) continue de baisser à 6h — le flux forcé vendeur ne s'épuise pas en une bougie.

- spec_sha 36fd7202eb96c4e4 · git ea993a8 · snapshot k1h-bbb04c32ed0e1c22
- verdict : **CONFIRMED** · n 1855 · mean 1.0178233452021221

- BTCUSDT@6h : n 708 · mean 0.639
- ETHUSDT@6h : n 714 · mean 1.093
- SOLUSDT@6h : n 433 · mean 1.513

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (recomputed_train)

| métrique | valeur |
|---|---|
| trades pris / events bruts | 1173 / 1908 |
| solde final | $112.80 |
| ROI période | +12.80 % |
| DD max (MTM horaire) | 0.20 % |
| liquidations | 0 |
| WR | 73.8 % |
| mois négatifs | 0 / 13 |
| pire mois / record | +0.39$ / +2.17$ |
| ret/DD | 65.1 |
| frais payés | $3.51 · funding net $+0.01 |
| DD worst intrabar / close-seul | 0.21 % / 0.19 % |
| concurrence max / marge max engagée | 3 positions / 3.0 % de l'équité |
| CAGR / Sharpe portefeuille / Sortino portefeuille | +12.1 % / 9.97 / 19.90 |
| profit factor / Sortino trade-level (secondaire) | 5.01 / 48.1 |
| concentration PnL sans top 1 / 5 / 10 % | $111.75 / $109.05 / $106.63 |
| CONTRE-FACTUEL sans top 10 % (re-joué, tailles recalculées) | $109.96 (liq 0) |
| n brut / sans chevauchement / effectif | 1173 / 525 / 374.3 (autocorr +0.516 · 688 buckets horaires) |
| bootstrap mean CI95 | [+0.000, +0.000] |
| bootstrap Sharpe portefeuille CI95 / t-stat CI95 | [+8.41, +11.53] / [+8.6, +11.8] |
| masse bootstrap mean > 0 | 0 réplications négatives / 2000 (blocs 24 h) |
| baseline long-and-hold 1x | $66.78 (ROI -33.22 %, DD 63.69 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.17 % · 2025-11 0.17 % · 2026-01 0.13 % · 2026-03 0.20 % · 2026-05 0.14 % · 2026-07 0.10 % (plafond 15 %) |
