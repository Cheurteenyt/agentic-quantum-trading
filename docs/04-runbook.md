---
title: Runbook — commandes propres
status: living
owner: cheurteen
updated: 2026-08-09
---

# Runbook

> Origine : `aster-production-runbook.md` (2026-06-01). La suite Aster legacy est
> morte (voir `03-methodology.md`), mais **les règles d'hygiène de run
> ci-dessous restent valables** et servent de base au futur runner automatisé.

## Lancer le projet

```bash
# backend — UNE SEULE FOIS
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
curl -s http://localhost:8000/health   # doit répondre avant d'aller plus loin

# frontend
cd frontend && npm run dev
```

## Auditer la documentation

```bash
python scripts/docs_audit.py         # exit 1 si un doc est stale / non déclaré
python scripts/index_legacy_dataset.py --stats   # (re)construit le warehouse legacy
python scripts/run_tests.py          # toute la suite (72 tests backtest_v2)
```

## Règles d'hygiène de run (héritage Aster)

Objectif: laisser le PC travailler proprement toute la journee sans produire un
tas de CSV impossibles a interpreter.

## Regle principale

Chaque backtest doit etre identifiable. Depuis le schema
`aster_strategy_discovery_v2_1`, les CSV de discovery ajoutent:

- `strategy_profile_id`: identite complete de la strategie;
- `strategy_profile_family`: famille lisible (`crypto_liquid_momentum`,
  `macro_commodity_slow_confirmation`, etc.);
- `strategy_profile_key`: cle compacte pour regrouper/filtrer.

Donc un resultat n'est plus seulement `LABUSDT 5h`. C'est:

`output_tag + symbol_preset + symbol + side + interval + search_mode + trigger_reference + execution_model + risk_profile + seuils + leverage`.

## Objectif demain

Faire tourner peu de lanes, mais mieux:

- 1 terminal exploitation crypto stricte;
- 1 terminal exploration Aster v2;
- 1 terminal macro/equity exploration;
- 1 terminal controle/reporting ponctuel, pas obligatoirement en boucle.

Ne pas lancer 8 terminaux qui testent presque la meme chose. Le CPU peut suivre,
mais la valeur vient de la diversite controlee, pas du bruit. La vraie limite a
surveiller est l'API Aster: `429`, `403`, `418`, timeouts et latence p95.

## Controle API avant d'ajouter des terminaux

Avant de passer de 4 a 5/6 terminaux, lancer un probe read-only:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_api_capacity_probe `
  --symbols BTCUSDT,LABUSDT,INJUSDT,XAUUSDT,NVDAUSDT `
  --requests 40 `
  --max-parallel 5 `
  --timeout-seconds 8
```

Sortie:

- `backend/services/onchain/aster/aster_api_capacity_probe_latest.json`

Lecture:

- `safe_to_expand_carefully`: on peut ajouter 1 terminal exploration.
- `slow_hold`: garder le nombre actuel, ne pas ajouter.
- `unstable_reduce`: reduire les terminaux ou augmenter `sleep-seconds`.
- `rate_limited_reduce`: `429`, il faut ralentir.
- `danger_stop`: `403/418`, stopper l'expansion.

Le probe ne trade pas, n'utilise aucun endpoint signe et ne fait aucun write DB.

## Radar volatilite crypto

Avant de lancer une exploration crypto focalisee, regenerer le radar des
cryptos Aster volatiles:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_volatile_crypto_discovery
```

Lire ensuite:

- `backend/services/onchain/aster/aster_volatile_crypto_discovery_latest.csv`
- `docs/core-equity-aster-volatile-crypto-discovery.html`

La colonne importante est `symbol`. Elle permet de construire un runner
`--symbols ...` avec les actifs qui bougent vraiment, au lieu de rester bloque
sur une watchlist fixe.

## Terminal 1 - Exploitation core stricte

But: continuer les actifs qui ont deja montre quelque chose, avec identite
stratégie propre et schema v2_1.

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_strategy_discovery `
  --symbol-preset core `
  --output-tag core_prod_mark_bbo `
  --search-mode deep `
  --trigger-reference mark_price `
  --execution-model bbo_limit `
  --groups both `
  --run-forever `
  --sleep-seconds 1800 `
  --lookback-days 60 `
  --windows 4 `
  --min-closed-trades 8 `
  --top-n-per-batch 12 `
  --top-n-global 100 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

## Terminal 2 - Exploration Aster v2

But: ne pas rester bloque sur les memes paires. Le runner v2 combine champions,
watchlist et univers public Aster.

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 `
  --output-tag aster_v2_prod `
  --groups both `
  --run-forever `
  --sleep-seconds 1800 `
  --lookback-days 60 `
  --windows 3 `
  --min-closed-trades 6 `
  --top-n-per-batch 10 `
  --top-n-global 80 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

## Terminal 3 - Macro/equity exploration

But: chercher des edges sur commodities/actions sans les melanger avec le core.

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_strategy_discovery `
  --symbol-preset macro_equity `
  --output-tag macro_equity_prod_mark_bbo `
  --search-mode exploration `
  --trigger-reference mark_price `
  --execution-model bbo_limit `
  --groups both `
  --run-forever `
  --sleep-seconds 2400 `
  --lookback-days 60 `
  --windows 4 `
  --min-closed-trades 8 `
  --top-n-per-batch 12 `
  --top-n-global 100 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

## Terminal 4 - Promotion strict forward paper

But: suivre uniquement les lanes deja passees par promotion/microstructure, pas
faire de la discovery brute.

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report `
  --strict-forward-cycle `
  --run-forever `
  --sleep-seconds 300 `
  --forward-window-trades 1000 `
  --persist
```

Ce terminal ecrit seulement dans le ledger paper-trading. Aucun trade reel.

## Terminal 5 optionnel - seulement si le probe est safe

Si le probe retourne `safe_to_expand_carefully`, ajouter un seul runner
exploration priority watchlist:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_priority_watchlist `
  --output-tag priority_watchlist_prod `
  --groups both `
  --run-forever `
  --sleep-seconds 1800 `
  --lookback-days 60 `
  --windows 3 `
  --min-closed-trades 6 `
  --top-n-per-batch 10 `
  --top-n-global 80 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

Ne pas ajouter un 6e runner tant qu'un second probe ne confirme pas que l'API
reste saine.

## Rapport du soir

Quand tu rentres, ne lis pas les terminaux ligne par ligne. Regenere les rapports:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_strategy_registry
python -m services.onchain.aster.aster_workspace_file_audit
python -m services.onchain.aster.aster_volatile_crypto_discovery
python -m services.onchain.aster.aster_asset_strategy_recommendations
python -m services.onchain.aster.aster_candidate_validation_queue
python -m services.onchain.aster.aster_research_consolidated_report
python -m services.onchain.aster.aster_strategy_truth_report
python -m services.onchain.aster.aster_promotion_truth_report
python -m services.onchain.aster.aster_lane_promotion_scoring
```

Lecture recommandee:

- `aster_candidate_validation_queue`: quoi valider ensuite, sans relancer de backtest inutile;
- `aster_volatile_crypto_discovery`: quelles cryptos Aster meritent une exploration car elles bougent vraiment;
- `aster_asset_strategy_recommendations`: quelle famille de strategie tester selon le type d'actif, avec une liste memecoin et volatile prete a copier;
- `aster_workspace_file_audit`: quels fichiers sont code actif, wrappers, artefacts generes, caches ou legacy;
- `aster_research_consolidated_report`: cockpit large des resultats;
- `aster_promotion_truth_report`: decision stricte par lane;
- `aster_lane_promotion_scoring`: ranking robuste des anciennes lanes.

Lecture:

1. `docs/core-equity-aster-current-state.html`
2. `docs/core-equity-aster-lane-promotion-scoring.html`
3. `docs/core-equity-aster-promotion-truth-report.html`
4. `docs/core-equity-aster-research-consolidated-report.html`
5. `docs/core-equity-aster-strategy-registry.html`

## Ce qu'on veut voir

Un resultat devient interessant seulement si:

- `strategy_profile_id` stable;
- au moins 8-15 trades fermes;
- plusieurs fenetres positives;
- PF > 1.3;
- drawdown acceptable;
- mark/index pas rejete;
- exchangeInfo pas bloque;
- microstructure ok avant forward;
- forward paper positif avec latent inclus.

Si un actif ressort souvent mais toujours avec le meme `strategy_profile_id`,
ce n'est pas une nouvelle decouverte: c'est la meme strategie qui se repete.
