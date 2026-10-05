# EXP-crash-short-6h-univ10 — confirmation

Hypothèse : RÉPLICATION UNIVERSE : le même flux forcé vendeur (ret_1h <= p10 expanding) continue de baisser à 6h sur les 10 majeures, pas seulement BTC/ETH/SOL

- spec_sha b7f9ce3286915a3a · git c2fadaf · snapshot k1h-c22625d61aca89cf
- verdict : **CONFIRMED** · n 6349 · mean 1.1311968308639107

- BTCUSDT@6h : n 728 · mean 0.637
- ETHUSDT@6h : n 734 · mean 1.093
- SOLUSDT@6h : n 446 · mean 1.503
- XRPUSDT@6h : n 631 · mean 1.197
- BNBUSDT@6h : n 692 · mean 0.841
- DOGEUSDT@6h : n 546 · mean 1.411
- ADAUSDT@6h : n 747 · mean 1.244
- AVAXUSDT@6h : n 562 · mean 1.251
- LINKUSDT@6h : n 643 · mean 1.336
- LTCUSDT@6h : n 620 · mean 1.043

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (discovery_artifact)

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
| baseline long-and-hold 1x | $58.42 (ROI -41.58 %, DD 68.17 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.44 % · 2025-11 0.29 % · 2026-01 0.23 % · 2026-03 0.24 % · 2026-05 0.30 % · 2026-07 0.18 % (plafond 15 %) |
