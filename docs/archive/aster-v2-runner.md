# Aster v2 runner

Date: 2026-05-31

## Objectif

Créer une commande unique qui combine:

- les champions historiques revalidés;
- les candidats review encore utiles;
- les nouveaux symboles issus de la watchlist Aster.

Ce runner ne remplace pas le moteur de backtest. Il orchestre proprement les inputs du nouveau système Aster puis délègue à:

`backend/services/onchain/aster/backtest_strategy_discovery.py`

## Fichiers

Logique:

`backend/services/onchain/aster/research/aster_v2_runner.py`

Wrapper CLI:

`backend/services/onchain/aster/backtest_aster_v2.py`

Plan local:

`backend/services/onchain/aster/aster_v2_runner_plan_latest.json`

Sorties backtest:

- `paper_trading_strategy_discovery_aster_v2_v2.csv`
- `paper_trading_strategy_discovery_aster_v2_latest.json`
- `paper_trading_strategy_rotation_aster_v2_latest.json`

## Inputs

Le runner lit:

- `aster_exploitation_champions_latest.json`;
- `aster_priority_watchlist_backtest_plan_latest.json`.
- `aster_public_universe_snapshot_latest.json`;
- `aster_ws_symbol_quality_report_latest.json`.

Par défaut, il garde:

- exploitation: décisions `keep_testing` ou `promote_to_forward_candidate`;
- review: décisions `needs_reality_check`;
- exploration diversifiée: priority watchlist, crypto liquide de l'univers Aster, commodities et equities.

Il exclut automatiquement les champions rejetés (`reject_or_manual_review`).

## Exploration diversifiée

Le runner v2 ne doit pas tourner uniquement sur les mêmes champions. Depuis la mise à jour du 2026-05-31, il construit une exploration round-robin:

- `priority_watchlist`: symboles dynamiques issus de la watchlist Aster.
- `crypto_universe`: meilleurs symboles crypto du snapshot public Aster, triés par tradability, spread et volume.
- `commodities`: `XAUUSDT`, `XAGUSDT`, `CLUSDT`, `BZUSDT`, `CRCLUSDT`, `ORCLUSDT` quand ils sont disponibles.
- `equities`: `NVDAUSDT`, `METAUSDT`, `AMDUSDT`, `DRAMUSDT`, `MSFTUSDT`, `INTCUSDT`, etc. quand ils sont disponibles.

Attention recherche officielle:

- les cryptos peuvent etre analysees comme marche 24/7;
- les equities ont des sessions New York et des off-hours;
- le forex Shield a des fermetures weekend/UTC et jours feries US;
- XAU/XAG peuvent aussi fermer pendant les jours feries US;
- les commodities doivent rester `needs_session_model` tant qu'on ne confirme pas
  leur produit exact et leurs horaires.

Donc un bon ROI sur macro/equities est utile, mais pas encore equivalent a un bon
ROI crypto tant qu'il n'a pas passe le filtre de session.

Le dernier plan généré contient 21 symboles runnable:

`LABUSDT,INJUSDT,INTCUSDT,CRCLUSDT,MSFTUSDT,ASTERUSDT,BTCUSDT,CLUSDT,METAUSDT,BNBUSDT,ETHUSDT,XAUUSDT,NVDAUSDT,HYPEUSDT,ETHUSD1,XAGUSDT,AMDUSDT,SOLUSDT,SOLUSD1,BZUSDT,DRAMUSDT`

Lecture importante: beaucoup de ces symboles sont `needs_ws_validation`, pas bloqués. Cela signifie que l'univers Aster les connaît et que le backtest peut les explorer, mais qu'il faut encore enrichir leur qualité WebSocket avant d'en faire du forward paper sérieux.

## Refresh WS preflight

Le refresh WS v2 évite d'écraser l'historique: il teste seulement les symboles demandés, fusionne leurs nouvelles lignes dans `aster_ws_symbol_quality_report_latest.json`, puis régénère `aster_v2_runner_plan_latest.json`.

Endpoint admin:

`/api/onchain/rpc/aster-v2-ws-preflight-refresh-preview`

Smoke du 2026-05-31:

- symboles testés: `CLUSDT`, `NVDAUSDT`, `XAUUSDT`, `ASTERUSDT`, `BNBUSDT`;
- lignes WS fusionnées: `8`;
- WS ready: `4`;
- WS watch: `3`;
- WS risky: `1`;
- plan v2 après refresh: `7` `backtest_ready`, `14` `needs_ws_validation`, `0` bloqué.

Refresh complet v2 du 2026-05-31:

- snapshot WS fusionné: `21` symboles testés;
- WS ready: `9`;
- WS watch: `4`;
- WS risky: `8`;
- plan strict v2: `13` symboles `backtest_ready`, `8` `needs_ws_validation`, `0` bloqué;
- symboles strict-ready: `LABUSDT`, `ASTERUSDT`, `BTCUSDT`, `CLUSDT`, `BNBUSDT`, `ETHUSDT`, `XAUUSDT`, `NVDAUSDT`, `HYPEUSDT`, `ETHUSD1`, `XAGUSDT`, `SOLUSDT`, `SOLUSD1`;
- symboles encore risky/watch-blocked pour forward strict: `INJUSDT`, `INTCUSDT`, `CRCLUSDT`, `MSFTUSDT`, `METAUSDT`, `AMDUSDT`, `BZUSDT`, `DRAMUSDT`.

Interpretation: ces 8 symboles peuvent rester en backtest exploration, mais ils ne doivent pas etre promus en forward strict avant une amelioration WS/liquidite ou une review manuelle.

Commande Python locale:

```powershell
Set-Location D:\trading-agent\backend
python -c "from services.onchain.aster.research.aster_v2_ws_preflight_refresh import get_aster_v2_ws_preflight_refresh_preview; print(get_aster_v2_ws_preflight_refresh_preview(symbols='CLUSDT,NVDAUSDT,XAUUSDT,ASTERUSDT,BNBUSDT', max_symbols=5, batch_size=2, timeout_seconds=5, write_snapshot=True)['refreshed_v2_preflight_summary'])"
```

## Preflight universe / WS

Avant de lancer le backtest, le runner classe chaque symbole:

- `backtest_ready`: present dans l'univers Aster, tradable, pas bloque, et WS `ready/watch`.
- `needs_ws_validation`: present dans l'univers mais WS absent, incomplet ou risqué.
- `needs_universe_refresh`: champion valide mais absent d'un ancien snapshot universe abrégé.
- `blocked_data_quality`: absent de l'univers ou bloque par status/spread.

Le mode par defaut reste pragmatique: il lance tout symbole non bloque, mais le cockpit affiche clairement ceux qui doivent encore passer la validation WS.

Mode strict:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 --plan-only --require-preflight-ready
```

Avec le dernier snapshot, le mode strict ne retient que les symboles deja propres cote WS/universe. C'est utile pour du forward paper strict, pas forcement pour l'exploration.

## Commande plan-only

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 --plan-only
```

Cette commande ne lance aucun backtest. Elle affiche simplement les symboles choisis.

## Commande H24 recommandée

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 `
  --output-tag aster_v2 `
  --groups both `
  --run-forever `
  --sleep-seconds 1200 `
  --lookback-days 60 `
  --windows 3 `
  --min-closed-trades 6 `
  --top-n-per-batch 10 `
  --top-n-global 80 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

## Commande exploitation stricte

Si on veut seulement les champions validés, sans exploration:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 `
  --output-tag aster_v2_exploitation `
  --no-exploration `
  --max-review 0 `
  --groups both `
  --run-forever `
  --sleep-seconds 900 `
  --lookback-days 60 `
  --windows 3 `
  --min-closed-trades 8 `
  --top-n-per-batch 10 `
  --top-n-global 50 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

## Garde-fous

- Aucun trade réel.
- Aucun wallet.
- Aucun write DB.
- Aucun endpoint signé.
- Le runner écrit seulement un plan JSON local et les CSV/JSON de backtest existants.
- Les résultats restent du backtest/paper research.
