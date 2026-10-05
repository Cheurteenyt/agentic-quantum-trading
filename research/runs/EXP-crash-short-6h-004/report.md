# EXP-crash-short-6h-004 — confirmation

Hypothèse : Une bougie de -X % (ret_1h <= p10 expanding) continue de baisser à 6h — le flux forcé vendeur ne s'épuise pas en une bougie.

- spec_sha 08b7cf90e1fa7a25 · git c162faa · snapshot k1h-83424f79e713e8c6
- verdict : **CONFIRMED** · n 1908 · mean 1.014251690736629

- BTCUSDT@6h : n 728 · mean 0.635
- ETHUSDT@6h : n 734 · mean 1.092
- SOLUSDT@6h : n 446 · mean 1.505

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (discovery_artifact)

| métrique | valeur |
|---|---|
| trades pris / events bruts | 1173 / 1908 |
| solde final | $112.79 |
| ROI période | +12.79 % |
| DD max | 0.18 % |
| liquidations | 0 |
| WR | 73.7 % |
| mois négatifs | 0 / 13 |
| pire mois / record | +0.38$ / +2.16$ |
| ret/DD | 69.9 |
| frais payés | $3.51 · funding net $+0.00 |
| baseline long-and-hold 1x | $66.78 (ROI -33.22 %, DD 63.69 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.15 % · 2025-11 0.10 % · 2026-01 0.06 % · 2026-03 0.18 % · 2026-05 0.10 % · 2026-07 0.05 % (plafond 15 %) |
