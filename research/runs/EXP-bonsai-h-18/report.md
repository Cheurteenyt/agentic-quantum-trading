# EXP-bonsai-h-18 — confirmation

Hypothèse : Volatility Squeeze Short

- spec_sha 0a7cfb39471f6846 · git c2fadaf · snapshot k1h-c22625d61aca89cf
- verdict : **CONFIRMED** · n 5181 · mean 0.3609647405948849

- BTCUSDT@6h : n 1443 · mean 0.314
- ETHUSDT@6h : n 1722 · mean 0.368
- SOLUSDT@6h : n 2016 · mean 0.388

## WALLET (couche portefeuille)

Vue validation · 100$ · marge ≤ 1.0 %/trade · lev 1x · une position par symbole · bookage au mois de sortie · seuils gelés (discovery_artifact)

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
| baseline long-and-hold 1x | $66.78 (ROI -33.22 %, DD 63.69 %) — l'edge doit BATTRE ça |
| DD par fenêtre gelée | 2025-09 0.27 % · 2025-11 0.17 % · 2026-01 0.23 % · 2026-03 0.34 % · 2026-05 0.11 % · 2026-07 0.17 % (plafond 15 %) |
