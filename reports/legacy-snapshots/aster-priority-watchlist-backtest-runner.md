# Aster priority watchlist backtest runner

Date: 2026-05-31

## Objectif

Connecter le nouvel univers Aster/WS au moteur de backtest existant.

Avant:

- les runners utilisaient surtout des presets fixes: `core`, `macro`, `equities`;
- la watchlist Aster servait seulement a choisir manuellement les prochains symboles.

Maintenant:

- `aster_priority_watchlist_latest.json` devient une source locale de symboles;
- le runner lit cette watchlist;
- il delegue ensuite au moteur existant `backtest_strategy_discovery.py`.

## Fichiers

Logique:

`backend/services/onchain/aster/research/priority_watchlist_backtest_runner.py`

Wrapper CLI:

`backend/services/onchain/aster/backtest_priority_watchlist.py`

Plan local:

`backend/services/onchain/aster/aster_priority_watchlist_backtest_plan_latest.json`

Sorties backtest:

- `paper_trading_strategy_discovery_priority_watchlist_v2.csv`
- `paper_trading_strategy_discovery_priority_watchlist_latest.json`
- `paper_trading_strategy_rotation_priority_watchlist_latest.json`

## Commande plan-only

Utilise cette commande pour voir quels symboles seraient testes sans lancer le backtest:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_priority_watchlist `
  --plan-only `
  --max-symbols 12 `
  --min-priority-score 35
```

## Commande runner H24

Ce runner peut remplacer un terminal exploration manuel si tu veux tester les symboles issus de la watchlist Aster:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_priority_watchlist `
  --output-tag priority_watchlist `
  --groups both `
  --run-forever `
  --sleep-seconds 1200 `
  --lookback-days 60 `
  --windows 3 `
  --min-closed-trades 6 `
  --top-n-per-batch 10 `
  --top-n-global 60 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

## Methode

Le runner selectionne les lignes:

- `priority_watchlist`;
- `candidate_watchlist`;
- eventuellement `top_scored_sample` si inclus par statut.

Filtres par defaut:

- `max_symbols=12`;
- `min_priority_score=35`;
- `include_statuses=priority,candidate`;
- rejet si blockers presents;
- rejet si symbole explicitement exclu.

Puis il appelle:

`run_discovery()` ou `run_rotation()` dans `backtest_strategy_discovery.py`.

## Garde-fous

- Aucun nouveau moteur de strategie.
- Aucun trade reel.
- Aucun wallet.
- Aucun write DB.
- Aucun appel externe direct dans le runner.
- Le seul write direct est le plan JSON local.

## Lecture des resultats

Les resultats remontent automatiquement dans le cockpit consolide parce que le fichier CSV respecte le pattern:

`paper_trading_strategy_discovery_*_v2.csv`

Donc apres quelques cycles:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_research_consolidated_report
```

Le cockpit HTML affichera les nouveaux resultats avec `output_tag=priority_watchlist`.
