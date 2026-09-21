# Aster WS forward monitor preview

Date: 2026-05-31

## Objectif

Comparer la donnee temps reel WebSocket Aster avec les snapshots REST publics, sans daemon et sans trading.

Module:

`backend/services/onchain/aster/aster_ws_forward_monitor_preview.py`

Endpoint:

`/api/onchain/rpc/aster-ws-forward-monitor-preview`

## Ce que le preview lit

Pour un symbole donne, le preview lit:

- WebSocket `aggTrade`;
- WebSocket `kline_1m`;
- WebSocket `depth5@500ms`;
- WebSocket `!markPrice@arr@1s`;
- REST `ticker/24hr`;
- REST `ticker/bookTicker`;
- REST `premiumIndex`.

Il compare ensuite:

- dernier trade WS vs last price REST;
- mark price WS vs mark price REST;
- profondeur/spread WS;
- kline live;
- presence du symbole dans le stream all-symbol mark/index.

## Smoke reel

Smoke du 2026-05-31:

### BTCUSDT

- health_status: `active`
- streams received: `4/4`
- ws_trade_vs_rest_last_price_bps: `0.054158`
- ws_mark_vs_rest_mark_bps: `0.00791`

### LABUSDT

- health_status: `active`
- streams received: `4/4`
- ws_trade_vs_rest_last_price_bps: `4.508344`
- ws_mark_vs_rest_mark_bps: `1.023485`

## Detail important

Le combined stream peut ne pas livrer les 4 flux dans la fenetre courte du smoke.

Le module utilise donc un fallback:

- il tente le combined stream;
- si un stream manque, il ouvre ce stream individuellement;
- le rapport marque `fallback_individual=True` sur les streams recuperes par fallback.

Cela garde le preview robuste sans daemon long.

## Utilite

Cette couche permet de preparer:

- un forward monitor plus reactif;
- une comparaison REST vs WS;
- une detection de latence;
- une meilleure simulation du slippage et du spread live;
- une transition future vers monitoring continu, toujours paper/read-only.

## Garde-fous

- Aucun write.
- Aucun trade.
- Aucun wallet.
- Aucun endpoint signe.
- Aucun signal client.
- `dry_run=True` obligatoire.

Ce preview est un diagnostic de donnees, pas une execution.
