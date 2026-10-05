
## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (recomputed_train)

| métrique | valeur |
|---|---|
| trades pris / events bruts | 4016 / 6349 |
| solde final | $155.93 |
| ROI période | +55.93 % |
| DD max (MTM horaire) | 0.53 % |
| liquidations | 0 |
| WR | 73.8 % |
| mois négatifs | 0 / 13 |
| pire mois / record | +1.56$ / +8.14$ |
| ret/DD | 105.8 |
| frais payés | $14.36 · funding net $+0.13 |
| DD worst intrabar / close-seul | 0.54 % / 0.45 % |
| concurrence max / marge max engagée | 10 positions / 10.0 % de l'équité |
| CAGR / Sharpe portefeuille / Sortino portefeuille | +52.3 % / 10.35 / 21.59 |
| profit factor / Sortino trade-level (secondaire) | 4.73 / 79.3 |
| concentration PnL sans top 1 / 5 / 10 % | $151.15 / $139.77 / $129.23 |
| CONTRE-FACTUEL sans top 10 % (re-joué, tailles recalculées) | $141.93 (liq 0) |
| n brut / sans chevauchement / effectif | 4016 / 785 / 867.6 (autocorr +0.645 · 1369 buckets horaires) |
| bootstrap mean CI95 | [+0.000, +0.000] |
| bootstrap Sharpe portefeuille CI95 / t-stat CI95 | [+8.89, +11.73] / [+9.1, +12.0] |
| masse bootstrap mean > 0 | 0 réplications négatives / 2000 (blocs 24 h) |
| baseline long-and-hold 1x | $58.42 (ROI -41.58 %, DD 68.17 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.53 % · 2025-11 0.53 % · 2026-01 0.50 % · 2026-03 0.34 % · 2026-05 0.48 % · 2026-07 0.33 % (plafond 15 %) |
