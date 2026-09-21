# Aster WebSocket market streams

Date: 2026-05-31

## Objectif

Identifier les donnees temps reel Aster disponibles sans API key et verifier qu'elles fonctionnent vraiment.

Module:

`backend/services/onchain/aster/aster_ws_market_stream_validation.py`

Endpoint:

`/api/onchain/rpc/aster-ws-market-stream-validation-preview`

## Source officielle

Documentation officielle Aster:

`https://asterdex.github.io/aster-api-website/futures/websocket-market-streams/`

Base URL:

`wss://fstream.asterdex.com`

## Streams verifies en reel

Smoke reel du 2026-05-31:

- streams tested: `4`
- validated streams: `4`
- failed_or_schema_mismatch: `0`

| Stream | Type | Resultat |
|---|---|---|
| `btcusdt@aggTrade` | aggregate trade stream | validated |
| `btcusdt@kline_1m` | kline stream | validated |
| `btcusdt@depth5@500ms` | order book depth stream | validated |
| `!markPrice@arr@1s` | mark/index/funding all-symbol array | validated |

## Streams publics connus mais pas encore branches

La doc officielle liste aussi:

- `<symbol>@bookTicker`;
- `!bookTicker`;
- `<symbol>@forceOrder`;
- `!forceOrder@arr`;
- `<symbol>@depth<levels>` avec niveaux `5`, `10`, `20`;
- `<symbol>@depth`, `<symbol>@depth@500ms`, `<symbol>@depth@100ms`.

Priorite:

1. `!bookTicker`: utile pour surveiller spread/bid/ask all-symbol sans REST.
2. `!forceOrder@arr`: utile pour detecter les regimes de liquidation/stress.
3. `depth@100ms`: utile seulement pour validation fine d'une lane championne,
   pas pour scanner tout l'univers.

Limite importante:

- `forceOrder` ne donne pas un historique complet; il ne publie que la liquidation
  la plus recente par fenetre de `1000ms`.
- Ce flux sert donc de filtre de regime forward, pas de backtest 60j complet.

## Donnees utiles

### `aggTrade`

Permet un suivi temps reel du flux d'execution:

- prix;
- quantite;
- trade time;
- maker side (`m`);
- aggregate trade id.

Utilite:

- detecter order-flow anormal;
- remplacer certains polls REST;
- reduire le retard du forward monitor.

### `kline_1m`

Permet de recevoir la bougie courante sans attendre un polling REST:

- open;
- high;
- low;
- close;
- volume;
- taker buy volume;
- nombre de trades;
- statut closed/open.

Utilite:

- forward paper trading plus reactif;
- multi-timeframe temps reel.

### `depth5@500ms`

Permet de lire le haut du carnet en temps reel:

- bids;
- asks;
- update ids.

Utilite:

- spread live;
- imbalance;
- detection spoofing/order book pressure;
- meilleure simulation slippage.

### `!markPrice@arr@1s`

Retourne un tableau all-symbol avec:

- mark price;
- index price;
- funding rate;
- next funding time.

Utilite:

- surveiller tous les symboles sans appeler `premiumIndex` en boucle;
- detecter divergence mark/index en temps reel;
- filtrer les actifs dangereux avant execution paper.

### `!forceOrder@arr`

Permet de voir les liquidations forcees publiques en temps reel:

- symbole;
- side;
- type d'ordre;
- prix moyen;
- quantite;
- statut;
- trade time.

Utilite:

- detecter cascade de liquidation;
- eviter de prendre une lane en plein regime extreme;
- tagger un signal comme `liquidation_regime_dependent` s'il ne marche que dans
  ces phases.

### `!bookTicker`

Permet un snapshot temps reel all-symbol du meilleur bid/ask:

- bid price;
- bid quantity;
- ask price;
- ask quantity;
- update id / event time.

Utilite:

- calculer le spread forward sans poll REST;
- repérer les symboles qui deviennent trop illiquides;
- reduire le nombre d'appels `ticker/bookTicker`.

## Garde-fous

Le validateur:

- utilise uniquement WebSocket public;
- ne depend pas d'une librairie externe;
- lit un seul message par stream;
- ne persiste rien;
- ne trade pas;
- ne touche aucun wallet;
- ne cree aucun signal client.

## Limites

- Le test valide la connectivite et le schema, pas la stabilite 24h.
- Les streams doivent gerer ping/pong et reconnexion avant usage en daemon.
- Les limites officielles mentionnent une deconnexion possible a 24h et des limites de messages entrants.

## Prochaine etape utile

Construire un `ws_forward_monitor_preview` read-only qui compare:

- polling REST actuel;
- WebSocket `aggTrade` + `depth` + `markPrice`;
- latence;
- nombre d'evenements;
- coherence prix/mark/index.

Ce sera une couche de monitoring, pas de trading reel.

Extension suivante conseillee:

- ajouter un smoke read-only de `!bookTicker`;
- ajouter un smoke read-only de `!forceOrder@arr`;
- exposer dans le rapport WS les flags `has_recent_liquidation_event` et
  `all_symbol_bookticker_available`.
