# Aster data source validation

Date: 2026-05-31

## Objectif

Continuer la recherche de donnees Aster sans supposer que la documentation suffit.

Chaque source doit passer trois controles:

- elle existe dans la documentation officielle Aster;
- elle repond en appel public read-only;
- le payload contient les champs attendus pour nos backtests.

Endpoint interne ajoute:

`/api/onchain/rpc/aster-data-source-validation-preview`

Module:

`backend/services/onchain/aster/aster_data_source_validation.py`

## Sources officielles utilisees

- Futures V3 Market Data: `https://asterdex.github.io/aster-api-website/futures-v3/market-data/`
- Futures V3 Account & Trading: `https://asterdex.github.io/aster-api-website/futures-v3/account%26trades/`

## Sources validees en probe reel

Smoke reel du 2026-05-31 sur `LABUSDT,INJUSDT,BTCUSDT`, `sample_limit=5`:

- probes: `48`
- usable_for_backtest: `48`
- failed_or_schema_mismatch: `0`
- endpoint types validated: `16`

Snapshot genere:

`backend/services/onchain/aster/aster_data_source_validation_latest.json`

Ce snapshot est maintenant lu par le rapport consolide:

`docs/core-equity-aster-research-consolidated-report.html`

Endpoints valides:

| Endpoint | Utilite backtest | Statut |
|---|---:|---|
| `/fapi/v3/ping` | connectivite | validated |
| `/fapi/v3/time` | clock drift / timestamp sanity | validated |
| `/fapi/v3/exchangeInfo` | filtres symbole/execution | validated |
| `/fapi/v3/ticker/24hr` | volume/liquidite 24h | validated |
| `/fapi/v3/ticker/price` | reference prix simple | validated |
| `/fapi/v3/ticker/bookTicker` | best bid/ask | validated |
| `/fapi/v3/depth` | profondeur carnet | validated |
| `/fapi/v3/trades` | recent trades / order-flow replay | validated |
| `/fapi/v3/aggTrades` | flux compresse | validated |
| `/fapi/v3/klines` | OHLCV historique | validated |
| `/fapi/v3/markPriceKlines` | mark price historique | validated |
| `/fapi/v3/indexPriceKlines` | index price historique | validated |
| `/fapi/v3/premiumIndex` | mark/index/funding snapshot | validated |
| `/fapi/v3/fundingRate` | historique funding | validated |
| `/fapi/v3/fundingInfo` | caps/floors/interval funding | validated |
| `/fapi/v3/indexreferences` | references d'index | validated |

## Smoke supplementaire all-symbol

Smoke read-only du 2026-05-31 avec la base active du code:

`https://fapi.asterdex.com`

Resultats observes:

| Endpoint | Resultat observe | Utilite |
|---|---:|---|
| `/fapi/v3/ticker/bookTicker` sans symbole | 448 lignes | spread/bid/ask all-symbol |
| `/fapi/v3/fundingInfo` sans symbole | 602 lignes | interval/cap/floor funding par symbole |
| `/fapi/v3/indexreferences?symbol=BTCUSDT` | 8 references | concentration de l'index BTC |

Note importante:

- Les exemples officiels Futures V3 mentionnent parfois `https://fapi3.asterdex.com`.
- Depuis notre environnement, `fapi3` retourne `403`.
- Le host operationnel utilise par nos modules est `https://fapi.asterdex.com`.

Cette difference doit rester documentee pour eviter de croire que l'endpoint est
casse alors que seul le host d'exemple est bloque.

## Donnee negative importante

La doc Futures V3 indique que `trades`, `historicalTrades` et `aggTrades`
retournent les trades executes dans l'order book uniquement.

Ils n'incluent pas:

- insurance fund trades;
- ADL trades.

Donc une future validation microstructure `aggTrades`/`historicalTrades` doit etre
lue comme `orderbook_trade_replay`, pas comme replay complet du risque systemique.

## Politique de securite

Le validator est strictement:

- read-only;
- dry-run;
- sans ordre;
- sans wallet;
- sans API key;
- sans write DB;
- sans signal client.

Les endpoints `TRADE`, `USER_DATA`, `WITHDRAW`, transferts et changements de leverage/margin restent bloques.

## Pourquoi c'est important

Avant cette etape, on ajoutait parfois une source parce qu'elle etait documentee.
Maintenant, une source Aster doit etre marquee `usable_for_backtest=True` par test reel avant d'influencer nos rapports.

La prochaine amelioration logique est de brancher ces validations dans les rapports Aster pour afficher:

- quelles sources sont actuellement fiables;
- quelles sources sont en erreur/rate-limit;
- quels resultats de backtest dependent de quelles sources.
