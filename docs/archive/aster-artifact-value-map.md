# Aster artifact value map

Date: 2026-06-02

Objectif: ne plus se perdre dans les fichiers Aster. Cette page classe les
artefacts par valeur actuelle: decision, validation, exploration, historique ou
archive. Elle doit etre lue avant de relancer des backtests ou de conclure
qu'une strategie est bonne.

## Alerte de lecture post-correctifs

Depuis la mise a jour du 2026-06-02 soir, les anciens meilleurs resultats
`LAB`, `HYPE`, `CRCL`, `MSFT`, `INTC`, `INJ`, etc. sont a lire comme des
**pistes historiques**, pas comme une preuve actuelle. Plusieurs points qui
gonflaient ou melangeaient les performances ont ete corriges:

- PnL latent separe du PnL realise;
- frais, funding et exposition calcules avec le levier perps;
- `score_window_size` integre a l'identite de strategie;
- lanes de promotion et forward identifiees par strategie exacte, pas seulement
  par symbole/intervalle;
- `mark_price` strict: pas de validation futures via fallback spot;
- plans et sorties V2 tagges par `output_tag`;
- split train/validation sur la fenetre recente dans la recherche V2.

Conclusion pratique: un fichier `*_latest.json` non tagge peut etre stale ou
ecrase par un smoke test. Pour decider, lire d'abord les sorties taggees et les
colonnes V2 `out_of_sample_status`, `validation_pnl_total_usd`,
`validation_win_rate`, `validation_profit_factor`, puis seulement ensuite le ROI
historique.

## Regle de lecture

Un ROI papier seul ne decide rien.

Une lane n'a de valeur operationnelle que si elle garde son identite complete:

`output_tag + symbol + interval + side + trigger_reference + execution_model + leverage`

Et si elle passe les controles suivants:

1. backtest V2 / progress;
2. mark/index replay;
3. microstructure replay;
4. exchangeInfo / contraintes perps;
5. WS / forward readiness;
6. queue de validation.

## Source de verite actuelle

Ces fichiers ont la plus grande valeur aujourd'hui:

| Priorite | Fichier | Role |
| --- | --- | --- |
| P0 | `backend/services/onchain/aster/aster_wide_backtest_snapshot_latest.csv` | Resume large des meilleures lanes recentes apres consolidation. |
| P0 | `backend/services/onchain/aster/aster_candidate_validation_queue_latest.csv` | File d'action: quoi valider, quoi regarder, quoi rejeter. |
| P0 | `backend/services/onchain/aster/aster_mark_index_replay_filter_latest.json` | Verifie si le replay reste credible face au mark/index. |
| P0 | `backend/services/onchain/aster/aster_microstructure_replay_validator_latest.json` | Verifie spread, slippage, gaps, volume et profondeur. |
| P0 | `backend/services/onchain/aster/aster_promotion_truth_report_latest.json` | Verite stricte de promotion, utile mais a lire avec la queue actuelle. |
| P0 | `backend/services/onchain/aster/aster_lane_promotion_scoring_latest.csv` | Score de promotion synthetique. |
| P0 | `backend/services/onchain/aster/aster_queue_reality_pack_validator_latest.csv` | Validation pack top queue: mark/index + microstructure sur les meilleurs candidats. |
| P1 | `backend/services/onchain/aster/aster_research_consolidated_report_latest.json` | Rapport complet de recherche, volumineux, utile pour contexte. |
| P1 | `docs/core-equity-aster-current-state.html` | Lecture humaine de l'etat actuel. |
| P1 | `docs/core-equity-aster-documentation-hub.html` | Hub de navigation. |
| P1 | `docs/aster-working-map.md` | Memo RAG / travail quotidien. |
| P1 | `backend/services/onchain/aster/README.md` | Runbook dossier Aster. |

## Decision historique du 2026-06-02 avant re-run post-correctifs

Le tableau ci-dessous garde visible le travail effectue avant les derniers
correctifs de realisme. Il sert a savoir quelles lanes re-tester en priorite,
pas a valider une mise en reel.

| Lane | Valeur actuelle | Decision |
| --- | --- | --- |
| `LABUSDT long 30m/2h/3h/5h` | ROI papier tres fort; la meilleure lane `30m` fait ~48.8% ROI, WR ~67.5%, PF ~3.02, `microstructure_ok`, mais `mark_index_watch` avec divergences single-candle et moyenne elevee. | Candidat serieux en watch, pas promote aveugle. Priorite: forward/replay strict et surveillance par lane exacte. |
| `HYPEUSDT long 15m/30m/3h/5h` | ROI plus modeste, mais `mark_index_confirmed`, `microstructure_ok`, WS ready. | Candidat le plus propre techniquement. |
| `HUSDT long 4h` | ROI papier ~18.1%, WR ~91.7%, PF ~22.8, `mark_index_watch`, mais le dernier pack signale `thin_liquidity` / wide spread. | Recherche / rework microstructure avant forward confiance. |
| `PLAYUSDT 4h/5h` | ROI papier interessant mais `gap_risk`. | Recherche seulement. |
| `BOMEUSDT` | Ancien ROI attractif, mais `mark_index_rejected` et microstructure faible. | Rejet/rework tant que les validations restent mauvaises. |

## Backtests recents a garder visibles

Ces CSV sont utiles parce qu'ils representent les runs recents encore actifs:

| Output tag | Fichier principal | Usage |
| --- | --- | --- |
| `core_prod_mark_bbo` | `paper_trading_strategy_discovery_core_prod_mark_bbo_v2.csv` | Core crypto / champions historiques sous modele mark+BBO. |
| `focused_candidate_validation` | `paper_trading_strategy_discovery_focused_candidate_validation_v2.csv` | Validation ciblee des candidats de valeur. |
| `aster_v2_prod` | `paper_trading_strategy_discovery_aster_v2_prod_v2.csv` | Univers Aster v2 plus large. |
| `priority_watchlist_prod` | `paper_trading_strategy_discovery_priority_watchlist_prod_v2.csv` | Watchlist prioritaire / nouveaux symboles. |
| `macro_equity_prod_mark_bbo` | `paper_trading_strategy_discovery_macro_equity_prod_mark_bbo_v2.csv` | Equities / commodities / macro. |
| `memecoin_volatile_strategy_search` | `paper_trading_strategy_discovery_memecoin_volatile_strategy_search_v2.csv` | Meme/volatilite, utile pour chercher des outliers. |

Les fichiers `*_progress_v2.csv` montrent l'etat pendant les runs continus.
Les fichiers `*_latest.json` donnent le dernier resume complet du tag.
Les fichiers `*_heartbeat.json` servent seulement a savoir si un runner tourne.

## Fichiers de controle et de qualite

| Fichier | Valeur |
| --- | --- |
| `aster_public_exchange_info_cache.json` | Contraintes Aster: tick, step, minNotional, triggerProtect, marketTakeBound. |
| `aster_public_funding_history_cache.json` | Funding public, utile pour realisme perps. |
| `aster_api_capacity_probe_latest.json` | Limites pratiques API / rate-limit. |
| `aster_strategy_registry_latest.json` | Inventaire des scripts et familles de strategies. |
| `aster_workspace_file_audit_latest.csv` | Audit local des fichiers Aster. |
| `aster_workspace_artifact_archive_plan_latest.csv` | Plan read-only d'archivage des vieux artefacts. |

## Historique a conserver mais ne plus utiliser comme decision

Ces resultats ont de la valeur historique, mais ne doivent plus promouvoir une
lane seuls:

- anciens `paper_trading_champion_lanes_backtest*`;
- anciens monitors `paper_trading_monitor.csv`,
  `paper_trading_multi_strategy_monitor.csv`,
  `paper_trading_directional_strategy_monitor.csv`;
- anciens meilleurs `LABUSDT 5h`, `BOMEUSDT 3h/5h`, `TIAUSDT 2h`,
  `CRCLUSDT`, `MSFTUSDT`, `INJUSDT`, `INTCUSDT` sans validation actuelle;
- tout CSV sans `output_tag` clair ou sans passage par mark/index +
  microstructure.

## Ce qui vaut une action maintenant

1. Regenerer la queue apres chaque grosse session:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_candidate_validation_queue
```

2. Regenerer le rapport consolide:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_research_consolidated_report
```

3. Regenerer le truth/promotion report:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_truth_report
python -m services.onchain.aster.aster_lane_promotion_scoring
```

4. Lire dans cet ordre:

- `aster_queue_reality_pack_validator_latest.csv`;
- `aster_wide_backtest_snapshot_latest.csv`;
- `aster_candidate_validation_queue_latest.csv`;
- `core-equity-aster-current-state.html`;
- `core-equity-aster-documentation-hub.html`.

## Decision hygiene

Si un fichier dit "promote" mais que la queue actuelle dit `mark_index_watch`,
`mark_index_rejected`, `gap_risk`, `not_enough_trades` ou `exchange_warning`,
la queue gagne.

Si deux docs se contredisent, prendre la plus recente dans cet ordre:

1. `rag/memory/project_state.md` top section;
2. `docs/aster-artifact-value-map.md`;
3. `docs/aster-working-map.md`;
4. `backend/services/onchain/aster/README.md`;
5. anciens rapports HTML.
