# Aster runner health dashboard

Date: 2026-05-31

## Objectif

Verifier en une commande si les runners Aster H24 travaillent vraiment.

Le dashboard lit uniquement les artefacts locaux:

- CSV `paper_trading_strategy_discovery_*_v2.csv`
- JSON `paper_trading_strategy_discovery_*_latest.json`
- heartbeat `paper_trading_strategy_discovery_heartbeat.json`
- plan `aster_v2_runner_plan_latest.json`

## Endpoint

`/api/onchain/rpc/aster-runner-health-dashboard-preview`

## Module

`backend/services/onchain/aster/research/runner_health_dashboard.py`

## Snapshot

`backend/services/onchain/aster/aster_runner_health_dashboard_latest.json`

## Etat du smoke initial

Tags attendus:

- `aster_v2_strict`
- `aster_v2`
- `macro_equity_explore`
- `core_explore_fresh`

Resultat:

- `missing_csv=4`
- `tags_with_csv=0`
- `active_heartbeat_tags=0`
- `v2_backtest_ready=13`
- `v2_needs_ws_validation=8`

Interpretation:

Les commandes ont peut-etre ete lancees, mais aucun des quatre tags attendus n'a encore ecrit son CSV local. Il faut laisser les terminaux terminer au moins un cycle ou verifier qu'ils n'ont pas ete lances avec un autre `output-tag`.

## Commande locale

```powershell
Set-Location D:\trading-agent\backend
python -c "from services.onchain.aster.research.runner_health_dashboard import get_aster_runner_health_dashboard_preview; r=get_aster_runner_health_dashboard_preview(write_snapshot=True); print(r['summary']); print(r['missing_tags'])"
```

## Garde-fous

- aucun appel Aster;
- aucun write DB;
- aucun trade;
- aucun wallet;
- snapshot JSON local seulement.
