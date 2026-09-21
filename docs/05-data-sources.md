---
title: Sources de données — ce qui marche encore
status: living
owner: cheurteen
updated: 2026-08-09
---

# Sources de données

Quelles sources sont vivantes, ce qu'elles donnent, et à quoi elles servent pour
un backtest. Détail complet dans `reference/`.

## État en un coup d'œil

| Source | État | Usage |
|---|---|---|
| Aster REST (`fapi.asterdex.com`) | **VIVANT** — 16 endpoints validés | OHLCV, funding, carnet, mark/index |
| Aster WebSocket | **VIVANT** — aggTrade OK | flux temps réel, forward monitor |
| Hyperliquid WS | **VIVANT** | flux temps réel |
| Multi-exchange REST | **VIVANT** (`services/multi_exchange.py`) | prix cross-exchange |
| Firecrawl (web agent) | **VIVANT** | recherche & scraping |
| Caches locaux Aster | ⚠️ **GELÉS** depuis 2026-06 | **refresh obligatoire** |
| Stratégies Aster legacy | **MORT** | ne pas réutiliser |
| MT5 | **MORT** | ignorer |

## Le piège n°1 : les caches gelés

`exchange_info`, `funding`, `universe` sont des snapshots locaux **datant de juin
2026**. L'API est vivante, les caches ne le sont pas.

> Backtester sur ces caches = backtester sur un marché qui n'existe plus, avec
> des filtres de symboles et des taux de funding périmés. **Rafraîchis avant
> toute campagne.**

## Aster REST — endpoints validés

Smoke réel du 2026-05-31 : 48 probes, 48 exploitables, 0 échec de schéma.
Base : `https://fapi.asterdex.com`.

Pour un backtest, les six qui comptent :

```
/fapi/v3/klines            OHLCV historique          → la série de prix
/fapi/v3/fundingRate       historique funding        → coût de portage réel
/fapi/v3/fundingInfo       caps / floors / interval  → bornes du funding
/fapi/v3/exchangeInfo      filtres symbole           → tick/lot/min notional
/fapi/v3/depth             profondeur carnet         → modèle de slippage
/fapi/v3/premiumIndex      mark / index / funding    → liquidation & basis
```

Les autres validés : `ping`, `time`, `ticker/24hr`, `ticker/price`,
`ticker/bookTicker`, `trades`, `aggTrades`, `markPriceKlines`,
`indexPriceKlines`, `indexreferences`.

Appels sans symbole (utiles pour scanner l'univers) :
`bookTicker` → 448 lignes, `fundingInfo` → 602 lignes.

Détail : `reference/aster-data-source-validation.md`,
`reference/aster-official-docs-gap-audit.md`.

## Aster WebSocket

Streams marché documentés dans `reference/aster-websocket-market-streams.md`.
`aggTrade` vérifié en ligne. Sert au forward paper et à la validation
microstructure — pas au backtest historique.

## Le lien avec la méthodologie

Chaque poste de coût du §2.3 de `03-methodology.md` a sa source ici :

| Poste de coût | Source |
|---|---|
| fees | `exchangeInfo` (+ tier de fee du compte) |
| funding sur notionnel | `fundingRate` + `fundingInfo` |
| slippage | `depth` (profondeur vs taille d'ordre) |
| risque de liquidation | `premiumIndex` (mark price) |

**Un backtest qui ne tape pas ces quatre sources sous-estime ses coûts.** C'est
exactement l'erreur du legacy.

## Politique de cache

Voir `reference/local-cache-policy.md`. Principe : le cache accélère, il ne fait
pas foi. Tout artefact daté produit par un run va dans `reports/`, jamais dans
`docs/`.
