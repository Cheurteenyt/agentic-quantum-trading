# Aster WS symbol quality report

Date: 2026-05-31

## Objectif

Savoir quels symboles Aster sont vraiment adaptés au forward paper trading temps reel via WebSocket.

Module:

`backend/services/onchain/aster/aster_ws_symbol_quality_report.py`

Endpoint:

`/api/onchain/rpc/aster-ws-symbol-quality-report-preview`

Snapshot:

`backend/services/onchain/aster/aster_ws_symbol_quality_report_latest.json`

## Methode

Pour chaque symbole, le rapport appelle:

- `get_aster_ws_forward_monitor_preview`;
- WebSocket `aggTrade`;
- WebSocket `kline_1m`;
- WebSocket `depth5@500ms`;
- WebSocket `!markPrice@arr@1s`;
- REST `ticker/24hr`;
- REST `bookTicker`;
- REST `premiumIndex`.

Il calcule un score `0-100` selon:

- streams recus / streams attendus;
- latence WS;
- coherence trade WS vs last price REST;
- coherence mark WS vs mark REST;
- spread WS;
- volume 24h.

Verdicts:

- `ws_forward_ready`: utilisable en forward monitor;
- `ws_forward_watch`: utilisable mais a surveiller;
- `ws_forward_risky`: trop instable/silencieux pour forward sans prudence.

## Smoke reel

Smoke du 2026-05-31 sur `BTCUSDT,LABUSDT,INJUSDT`:

- symbols tested: `3`
- ws_forward_ready: `2`
- ws_forward_watch: `0`
- ws_forward_risky: `1`

| Symbole | Score | Verdict | Notes |
|---|---:|---|---|
| BTCUSDT | 100 | ws_forward_ready | aucun warning |
| LABUSDT | 93 | ws_forward_ready | divergence mark/rest moderee |
| INJUSDT | 52 | ws_forward_risky | stream manquant en fenetre courte, spread/volume moderes |

Recommandation actuelle:

- `BTCUSDT`
- `LABUSDT`

## Lecture pratique

Ce rapport ne dit pas "acheter" ou "shorter".

Il dit:

- ce symbole est assez vivant en WS;
- le flux est coherent avec REST;
- le spread et la liquidite permettent de surveiller en temps reel;
- ou au contraire, ce symbole risque de produire du bruit ou des trous de donnees.

## Garde-fous

- Aucun write DB.
- Aucun trade.
- Aucun wallet.
- Aucun endpoint signe.
- Aucun signal client.
- `write_snapshot=True` ecrit uniquement un JSON local de diagnostic.

## Integration dans les backtests

Cette etape est maintenant branchee dans le workflow Aster v2.

Le runner `backtest_aster_v2` peut lancer un refresh WS avant de reconstruire son plan:

```powershell
python -m services.onchain.aster.backtest_aster_v2 --plan-only --auto-ws-preflight --ws-preflight-max-symbols 10
```

Les nouveaux CSV discovery v2 conservent ensuite la qualite WS par candidat:

- `ws_quality_verdict`;
- `ws_quality_score`;
- `ws_quality_risks`;
- `ws_quality_warnings`;
- `ws_spread_bps`;
- `ws_latency_ms`;
- `ws_streams_received`;
- `ws_streams_expected`.

Regle de lecture:

- une bonne lane + `ws_forward_ready` devient un meilleur candidat forward;
- une bonne lane + `ws_forward_watch` reste a surveiller;
- une bonne lane + `ws_forward_risky` doit rester en recherche, meme si le ROI du backtest est eleve.
