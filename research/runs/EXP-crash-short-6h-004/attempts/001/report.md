# EXP-crash-short-6h-004 — confirmation

Hypothèse : Une bougie de -X % (ret_1h <= p10 expanding) continue de baisser à 6h — le flux forcé vendeur ne s'épuise pas en une bougie.

- spec_sha 08b7cf90e1fa7a25 · git c2fadaf · snapshot k1h-c22625d61aca89cf
- verdict : **CONFIRMED** · n 1908 · mean 1.0151491619106334

- BTCUSDT@6h : n 728 · mean 0.637
- ETHUSDT@6h : n 734 · mean 1.093
- SOLUSDT@6h : n 446 · mean 1.503

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (discovery_artifact)

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
| baseline long-and-hold 1x | $66.78 (ROI -33.22 %, DD 63.69 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.15 % · 2025-11 0.10 % · 2026-01 0.06 % · 2026-03 0.18 % · 2026-05 0.10 % · 2026-07 0.05 % (plafond 15 %) |
