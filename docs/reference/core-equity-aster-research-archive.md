# Core Equity - Archive Aster Research

Derniere mise a jour: 2026-05-31.

Ce fichier conserve l'historique de recherche Aster. Le HTML principal
`docs/core-equity-aster-research-report.html` doit rester lisible comme dashboard
decisionnel; cette archive garde le detail des tests, pivots, endpoints,
resultats, limites et decisions qui ont mene aux pistes actuelles.

Statut: research-only / paper-trading only. Aucun trade reel, aucun wallet order,
aucune cle trading Aster, aucun signal client.

## 1. Pourquoi cette archive existe

Le rapport HTML Aster a ete simplifie pour devenir lisible. Cela ne veut pas dire
que les anciens tests sont jetes. Ils restent importants parce qu'ils montrent:

- quelles hypotheses ont ete falsifiees;
- quelles pistes ont produit un debut d'edge paper;
- quels parametres ont ete testes;
- quelles erreurs d'interpretation il faut eviter;
- pourquoi les runners actuels sont organises en champions + exploration.

Regle de lecture:

- HTML Aster = etat courant et decision.
- Archive Markdown = historique detaille et memoire de recherche.
- Null-results HTML = hypotheses non concluantes ou insuffisantes.
- CSV V2 = source quantitative primaire.

## 2. Chronologie synthetique

### Phase 1 - Aster foundation read-only

Module ajoute: `backend/services/onchain/aster/aster_agent_foundation.py`.

Objectif:

- explorer l'API publique Aster sans trading;
- tester REST, WebSocket, recent trades, ticker, order book;
- verifier un wallet uniquement en preview si `ASTER_AGENT_PRIVATE_KEY` existe;
- ne jamais logger la private key;
- ne jamais envoyer de transaction.

Endpoint:

- `/api/onchain/rpc/aster-agent-foundation-test`

Smoke initial:

- REST Aster `ping`, `time`, `exchangeInfo`, `recent_trades`,
  `ticker_24h`, `book_ticker`: HTTP `200`;
- latence REST moyenne: environ `638ms`;
- WebSocket reachable;
- recent trades BTCUSDT: `5`;
- wallet: `private_key_missing`, attendu.

Conclusion:

- Aster est bien accessible;
- Aster est un CEX/order book, pas un DEX visible wallet-to-wallet;
- l'hypothese "accumulation on-chain visible sur Aster" ne marche pas directement.

### Phase 2 - Order book anomaly detection

Extension de `aster_agent_foundation.py`.

Endpoint:

- `/api/onchain/rpc/aster-order-book-anomaly-detection-test`

Scores ajoutes:

- order book anomaly;
- volume anomaly;
- order flow anomaly;
- combined Aster score.

Smoke BTCUSDT:

- order book anomaly: environ `18.09`;
- volume anomaly: environ `60.64`;
- order flow anomaly: environ `25.67`;
- combined score: environ `33.13`;
- suspicious: `false`.

Conclusion:

- BTC efficient donne un score bas: validation negative saine.
- Le moteur ne crie pas au loup sur BTC.

### Phase 3 - Decision engine dry-run

Module ajoute: `backend/services/onchain/aster/aster_agent_decision_engine.py`.

State machine:

- `idle`;
- `observing`;
- `analyzing`;
- `deciding`;
- `executing` simule;
- `monitoring`;
- `exiting`.

Regles initiales:

- entrer si `aster_score >= 70`;
- si score DEX local existe: `behavioral_score >= 60`;
- volume 24h minimum `$50k`;
- position max `5%`;
- stop-loss `-15%`;
- take-profit `+50%`.

Endpoint:

- `/api/onchain/rpc/aster-agent-loop-test`

Smoke BTCUSDT:

- state `idle`;
- open positions `0`;
- Aster score environ `32.11`;
- no entry: `entry_rules_not_met`.

Conclusion:

- bonne structure agentique;
- aucun trading reel possible par design.

### Phase 4 - Paper trading sandbox ledger

Module principal:

- `backend/services/onchain/aster/aster_paper_trading_sandbox.py`

Endpoints initiaux:

- `/api/onchain/rpc/aster-paper-trading-schema-plan`;
- `/api/onchain/rpc/aster-paper-trading-ledger/create`;
- `/api/onchain/rpc/aster-paper-trading-run-preview`.

Table dediee:

- `aster_paper_trading_ledger`;
- creation uniquement avec confirm `CREATE_ASTER_PAPER_TRADING_LEDGER`;
- aucun write hors table paper trading.

Champs utiles:

- `run_id`;
- `symbol`;
- `state`;
- scores;
- prix entree/sortie;
- size USD;
- fees;
- slippage;
- PnL unrealized/realized;
- max drawdown;
- payload JSON brut.

Validation:

- schema-plan dry-run: no write;
- create confirme: table creee;
- second create: idempotent;
- BTCUSDT dry-run: aucune entree, ledger reste vide.

## 3. Hypotheses testees et verdicts

### Hypothese A - Acheter l'anomalie Aster order-flow brute

These:

- si `aster_score` est haut, acheter le token.

Resultat:

- long/buy seul Aster order-flow a ete falsifie;
- diagnostic cinematique: `volatility_whipsaw`;
- les trades avaient parfois du MFE positif mais finissaient souvent en stop-loss;
- le signal detectait souvent une zone agitee, pas une entree long fiable.

Decision:

- ne pas trader Aster order-flow long/buy seul.

### Hypothese B - Short/fade des anomalies

These:

- si l'anomalie marque une zone de distribution/wash, il faut fader/shorter
  au lieu d'acheter.

Resultats historiques importants:

- backtest short/fade etendu: WR `88.9%`, PF `3.45`, PnL paper `+17.08 USD`;
- risk management optimise: PF `5.34`, PnL paper `+9.78 USD`;
- univers volatile manuel (`WIF`, `ORDI`, `1000SATS`, `LAB`, `ARB`):
  `11` entrees, `7` sorties, WR ferme `100%`, PnL `+32.064411 USD`;
- selection univers short/fade sur `26` symboles:
  `21` disponibles, `44` entrees, `32` sorties, WR `71.875%`,
  PF `3.493217`, PnL `+50.867086 USD`.

Parametres short/fade qui ont bien tourne:

- entree: `aster_score >= 70` ou `75` selon les tests;
- volume window: `>= 1000`;
- stop-loss short: `+8%` a `+10%`;
- take-profit short: `-6%` a `-8%`;
- trailing activation: `4%`;
- trailing distance: `2%`;
- time-stop: zone `500-600` trades.

Watchlist short/fade issue de la selection:

- `1000SATSUSDT`;
- `ORDIUSDT`;
- `JUPUSDT`;
- `ARBUSDT`;
- `OPUSDT`;
- `SEIUSDT`;
- `WLDUSDT`;
- `TIAUSDT`.

Limite:

- edge interessant, mais plusieurs lectures plus recentes ont montre que la voie
  long breakout pouvait devenir plus prometteuse sur klines 60j.

### Hypothese C - Long breakout volume 60j

These:

- ne pas acheter l'anomalie brute;
- acheter seulement les breakouts volume stricts sur historiques plus longs.

Endpoint ajoute:

- `/api/onchain/rpc/aster-paper-trading-60d-kline-replay-preview`

Methodologie:

- klines Aster converties en evenements replayables;
- proxy bougies, pas tick-level;
- frais/slippage simules;
- read-only strict.

Smoke `TIAUSDT,SEIUSDT` sur `60j/1h`:

- long `long_high_volume_breakout_75`:
  `30` entrees, `30` sorties, WR `53.3333%`,
  PF `1.639454`, PnL paper `+40.083671 USD`;
- short optimise:
  `39` entrees, `39` sorties, WR `56.4103%`,
  PF `0.615159`, PnL `-46.851937 USD`.

Replay 60j/1h univers mixte:

- symboles: `TIA`, `SEI`, `JUP`, `WLD`, `1000SATS`, `ORDI`, `ARB`, `OP`;
- long: `71` entrees, `70` sorties, WR `52.8571%`,
  PF `1.189023`, PnL `+21.030065 USD`;
- short: PnL `-76.743395 USD`.

Replay 60j/15m shortlist:

- symboles: `TIA`, `JUP`, `ARB`, `1000SATS`, `ORDI`, `WLD`;
- long: `118` entrees, `114` sorties, WR `56.1404%`,
  PF `1.249227`, PnL `+47.080303 USD`;
- short: PnL `-111.525206 USD`.

Conclusion:

- la voie "bon sens" long devient plus interessante avec volume strict
  et timeframes adaptes;
- shorts utiles seulement de maniere selective, pas comme doctrine globale.

### Hypothese D - Multi-timeframe 60j

Endpoint:

- `/api/onchain/rpc/aster-paper-trading-multi-timeframe-replay-preview`

Timeframes testes:

- `1h`;
- `30m`;
- `15m`;
- `2h`;
- `3h`;
- `4h`;
- `5h`;
- `6h`.

Note:

- `3h` et `5h` sont synthetiques depuis les klines `1h` car Aster refuse
  parfois ces intervalles en direct.

Matrice basse timeframe `1h/30m/15m`:

- `TIAUSDT` long robuste, PnL cumule `+98.276561 USD`;
- `1000SATSUSDT` short robuste, PnL cumule `+42.459856 USD`;
- `ARB` et `JUP` longs prometteurs;
- `ORDI` et `WLD` faibles ou seulement prometteurs.

Matrice haute timeframe `2h/3h/4h/5h/6h`:

- `TIAUSDT` long robuste, PnL cumule `+67.061530 USD`;
- `JUPUSDT` long robuste, PnL cumule `+23.956817 USD`;
- `1000SATSUSDT` short prometteur, PnL `+4.073238 USD`;
- `ORDI` et `WLD` faibles.

Decisions issues de cette phase:

- long priorite 1: `TIAUSDT`;
- long priorite 2: `JUPUSDT`;
- long observation: `ARBUSDT`;
- short selectif: `1000SATSUSDT`;
- rejeter `ORDIUSDT` et `WLDUSDT` comme strategies principales a ce stade.

### Hypothese E - Sweep agressif ROI / win-rate

Univers:

- environ `26` symboles;
- timeframes `15m`, `30m`, `1h`, `2h`, `3h`, `4h`;
- variantes long/short.

Meilleures lanes:

- `TIAUSDT` long `score>=80`, `volume>=5k`,
  SL `-6%`, TP `+12%`, trailing `6%/3%`:
  `76` trades, WR `64.47%`, ROI `+15.76%`;
- `INJUSDT` long meme set:
  `31` trades, WR `80.65%`, ROI `+12.64%`;
- `INJUSDT` long frequent `score>=70`, `volume>=5k`,
  SL `-3%`, TP `+6%`, trailing `3%/1.5%`:
  `109` trades, WR `72.48%`, ROI `+10.37%`;
- `NEARUSDT` long `score>=75`, `volume>=1k`,
  SL `-4%`, TP `+8%`, trailing `4%/2%`:
  `63` trades, WR `68.25%`, ROI `+7.74%`;
- `BOMEUSDT` long:
  ROI `+8.54%`, mais qualite moindre car 15m/30m faibles;
- `LABUSDT` long/short donne de gros ROI mais fragile et dependant
  de certaines fenetres.

Conclusion:

- TIA avait le meilleur ROI brut;
- INJ avait une robustesse walk-forward plus interessante ensuite.

### Hypothese F - Focused walk-forward

Endpoint:

- `/api/onchain/rpc/aster-paper-trading-focused-walkforward-preview`

Objectif:

- separer les meilleures lanes en 3 fenetres temporelles sur 60j;
- reduire le risque d'overfit.

Smoke `TIA`, `INJ`, `NEAR`, `BOME`, `1000SATS`
sur `15m`, `1h`, `3h`:

- priorite 1:
  `INJUSDT` long strict `score>=80`, `volume>=5k`,
  SL `-6%`, TP `+12%`, trailing `6%/3%`, timeframe `15m`:
  `16` trades, WR `81.25%`, PF `5.355475`, ROI `+5.647579%`;
- priorite 2:
  `INJUSDT` long frequent `score>=70`, `volume>=5k`,
  SL `-3%`, TP `+6%`, trailing `3%/1.5%`, timeframe `15m`:
  `44` trades, WR `70.4545%`, PF `2.123240`, ROI `+3.678555%`;
- priorite 3:
  `NEARUSDT` long balanced `score>=75`, `volume>=5k`,
  SL `-4%`, TP `+8%`, trailing `4%/2%`, timeframe `15m`:
  `33` trades, WR `66.6667%`, PF `1.818847`, ROI `+2.807873%`.

Conclusion:

- `TIAUSDT` garde un ROI brut important;
- `INJUSDT` devient priorite forward car plus robuste en walk-forward;
- `NEARUSDT` devient diversification possible.

### Hypothese G - Focused optimization

Endpoint:

- `/api/onchain/rpc/aster-paper-trading-focused-optimization-preview`

Objectif:

- optimiser uniquement les pistes long prometteuses (`INJ`, `NEAR`, `TIA`);
- eviter de refaire un sweep global couteux.

Smoke `INJUSDT 15m`:

- `90` combinaisons testees;
- `61` candidates acceptees;
- meilleure lane:
  `score>=75`, `volume>=3k`, SL `-6%`, TP `+12%`,
  trailing `6%/3%`;
- `19` trades fermes;
- WR `78.9474%`;
- PF `4.639460`;
- ROI `+6.211458%`;
- PnL paper `+62.114582 USD`;
- writes `0`.

Decision:

- remplacer l'ancien `INJ 80/5k` par `INJ 75/3k`
  comme priorite forward paper;
- garder `80/3k` et `75/5k` comme variantes de controle.

## 4. Forward paper trading

### Optimized long forward monitor

Endpoint:

- `/api/onchain/rpc/aster-optimized-long-forward-monitor-preview`

Objectif:

- isoler les lanes long optimisees de l'ancien short/fade;
- persister seulement avec confirm `CONFIRM_FORWARD_PAPER_TRADE`.

Smoke dry-run 800 trades recents:

- portfolio `INJ+NEAR+TIA`;
- `10` signaux;
- WR ferme `75%`;
- PnL `+8.097303 USD`;
- writes `0`.

Premiere execution confirmee paper-only:

- `rows_inserted=10`;
- ledger: `10` entries, `5` exits;
- WR `80%`;
- PF `2.841265`;
- net PnL `+7.705056 USD`;
- max drawdown `6.714803 USD`.

### Stateful optimized long monitor

Endpoint:

- `/api/onchain/rpc/aster-optimized-long-stateful-monitor`

Script:

- `backend/services/onchain/aster/monitor_optimized_longs.py`

Objectif:

- reprendre les positions ouvertes du ledger;
- traiter uniquement les nouveaux trades;
- ajouter mark-to-market paper;
- eviter les positions fantomes.

Etat observe:

- ledger `14` entries / `8` exits;
- WR `87.5%`;
- PF `5.192943`;
- net PnL `+17.546012 USD`;
- INJ/NEAR ouverts avec latent positif a un moment du suivi.

Commandes typiques:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.monitor_optimized_longs --cycles 12 --sleep-seconds 300 --persist
```

### Multi-strategy monitor

Script:

- `backend/services/onchain/aster/monitor_multi_strategy.py`

But:

- faire tourner plusieurs lanes en parallele;
- eviter de ne tester qu'une seule strategie toute la journee;
- comparer baseline, regime filtered, inj only, tia only, etc.

Snapshot utile:

- `inj_only`: realise environ `+18.06 USD`, WR `75%`, PF `6.48`;
- `inj_tia_plus_candidates`: realise environ `+14.82 USD`, WR `75%`, PF `3.98`;
- `inj_tia_regime_filtered`: realise environ `+11.77 USD`, PF `1.85`;
- `baseline`: negatif ou faible;
- `near_only_observation`: faible ou negatif.

Limite:

- les positions ouvertes peuvent avoir un latent negatif;
- le realise seul ne suffit pas.

## 5. Strategy discovery V2 et runners H24

Script:

- `backend/services/onchain/aster/backtest_strategy_discovery.py`

Probleme resolu:

- les backtests se multiplient;
- l'ancien CSV global etait trop compact;
- `latest.json` pouvait etre ecrase par un smoke;
- il fallait des outputs tagges et des colonnes auditables.

Artefacts V2:

- `paper_trading_strategy_discovery_{tag}_v2.csv`;
- `paper_trading_strategy_discovery_{tag}_latest.json`;
- `paper_trading_strategy_rotation_{tag}_latest.json`;
- `paper_trading_strategy_discovery_heartbeat.json`.

Colonnes importantes:

- `schema_version`;
- `run_id`;
- `output_tag`;
- `symbol_preset`;
- `symbol_group`;
- `interval_group`;
- `lookback_days`;
- `windows`;
- `min_closed_trades_required`;
- `symbol`;
- `side`;
- `interval`;
- `search_mode`;
- `score_window_size`;
- `risk_profile`;
- `min_aster_score`;
- `min_window_volume_usd`;
- `stop_loss_pct`;
- `take_profit_pct`;
- `trailing_stop_activation_pct`;
- `trailing_stop_distance_pct`;
- `max_holding_trades`;
- `entries`;
- `closed_trades`;
- `wins`;
- `losses`;
- `win_rate`;
- `profit_factor`;
- `gross_profit_usd`;
- `gross_loss_usd`;
- `pnl_total_usd`;
- `roi_pct_on_paper_balance`;
- `max_drawdown_usd`;
- `positive_windows`;
- `best_tradable_leverage`;
- `best_tradable_leverage_roi_pct_on_margin`;
- `perps_invalid_leverages`;
- `perps_scenarios_json`;
- `candidate_json`.

Hardening:

- `--run-forever` est maintenant vraiment infini;
- heartbeat JSON atomique;
- latest JSON atomique;
- erreurs par batch non bloquantes;
- rotation CSV si header incompatible.

## 6. Perps isolated margin proxy

Probleme:

- multiplier le PnL par x10/x20 sans liquidation donne de faux espoirs.

Proxy ajoute:

- maintenance margin par defaut `0.5%`;
- funding proxy `1 bps / 8h`;
- estimation distance liquidation;
- rejet d'un levier si l'adverse move estime touche liquidation avant le stop.

Regles:

- ne pas promouvoir x10/x20 si `is_tradable_under_proxy=false`;
- utiliser `best_tradable_leverage`;
- garder en tete que ce n'est pas la formule officielle Aster.

Exemples actuels:

- `LABUSDT 5h`: x5 retenu, x10/x20 rejetes;
- `INTCUSDT 30m`: x5 retenu, x10/x20 rejetes;
- `BOMEUSDT 5h`: x10 retenu, x20 rejete;
- `INJUSDT 15m`: x10 retenu, x20 rejete.

## 7. Resultats snapshot 2026-05-31

Sources locales:

- `paper_trading_strategy_discovery_core_v2.csv`;
- `paper_trading_strategy_discovery_core_champions_v2.csv`;
- `paper_trading_strategy_discovery_macro_v2.csv`;
- `paper_trading_strategy_discovery_equities_v2.csv`;
- `paper_trading_multi_strategy_stateful_heartbeat.json`.

### Core crypto

Meilleurs setups:

- `LABUSDT 5h long`:
  ROI `+16.20%`, WR `76.5%`, PF `7.33`,
  `17` trades fermes, DD max `16.35`, levier proxy x5;
- `LABUSDT 3h long`:
  ROI `+14.67%`, WR `81.8%`, PF `10.72`,
  `11` trades fermes, levier proxy x5;
- `BOMEUSDT 5h long`:
  ROI `+6.97%`, WR `75.0%`, PF `7.02`,
  `8` trades fermes, levier proxy x10;
- `INJUSDT 15m long`:
  ROI `+6.78%`, WR `80.0%`, PF `6.60`,
  `15` trades fermes, levier proxy x10;
- `TIAUSDT 1h long`:
  ROI `+5.59%`, WR `68.8%`, PF `3.85`,
  `16` trades fermes;
- `ORDIUSDT 15m long`:
  ROI `+4.40%`, WR `55.2%`, PF `2.22`,
  `29` trades fermes.

Lecture:

- LAB est le champion ROI actuel mais a besoin de forward;
- INJ reste plus credible car deja observe en forward;
- BOME est interessant mais sample court.

### Equities

Meilleurs setups:

- `INTCUSDT 30m long`:
  ROI `+8.40%`, WR `90.9%`, PF `13.12`,
  `11` trades fermes, levier proxy x5;
- `DRAMUSDT 30m long`:
  ROI `+2.89%`, WR `59.3%`, PF `1.79`,
  `27` trades fermes;
- `AMZNUSDT 15m long`:
  ROI `+2.42%`, WR `73.3%`, PF `3.48`,
  `15` trades fermes;
- `NVDAUSDT 30m long`:
  ROI `+2.25%`, WR `75.0%`, PF `4.49`,
  `8` trades fermes;
- `MSFTUSDT 4h long`:
  ROI `+1.68%`, WR `87.5%`, PF tres haut mais sample faible.

Lecture:

- INTC est la piste equity principale;
- le reste sert a explorer, pas a conclure.

### Macro / commodities

Meilleurs setups:

- `CRCLUSDT 2h long`:
  ROI `+3.36%` a `+4.00%`, WR `75%` a `88.9%`,
  PF jusqu'a `15.94`;
- `XAGUSDT 15m long`:
  ROI autour de `+2.10%`, WR `80%`, PF `4.45`;
- `CLUSDT 2h long`:
  ROI `+1.57%`, WR `75%`, PF `3.43`.

Lecture:

- CRCL domine macro mais l'univers est etroit;
- continuer exploration macro hors CRCL.

## 8. Pourquoi les memes actifs reviennent

Les runners retournent souvent `LAB`, `INTC`, `CRCL`, parfois `INJ`.
Ce n'est pas forcement un bug:

- le backtest est deterministe sur le meme historique;
- les memes actifs dominent la grille;
- le runner champion doit justement les suivre;
- le runner exploration doit exclure les champions pour forcer de nouvelles pistes.

Solution ajoutee:

- `--exclude-symbols`;
- `--search-mode exploration`;
- `top_unique_symbols` dans JSON/heartbeat;
- output tags separes.

Commandes conceptuelles:

- runner champion: sans exclusion;
- runner exploration core: exclure `LABUSDT,INJUSDT,BOMEUSDT,TIAUSDT`;
- runner exploration equities: exclure `INTCUSDT,MSFTUSDT`;
- runner exploration macro: exclure `CRCLUSDT`.

## 9. Aster MCP

Source:

- `https://github.com/asterdex/aster-mcp`
- `https://github.com/asterdex/api-docs`

Decision:

- utile pour market data, funding, leverage brackets, exchange info;
- dangereux si connecte brut car expose aussi ordres, transferts, leverage/margin.

Politique:

- installation isolee dans `external/aster-mcp`;
- aucune cle trading;
- phase read-only;
- wrapper local autorisant uniquement market data;
- interdire ordres, transfers, leverage/margin changes.

Etat implemente le 2026-05-31:

- module read-only: `backend/services/onchain/aster/aster_mcp_market_data_adapter.py`;
- endpoint admin: `/api/onchain/rpc/aster-mcp-market-data-adapter-preview`;
- donnees publiques V3 normalisees: `exchangeInfo`, `ticker/24hr`, `depth`, `klines`, `markPriceKlines`, `indexPriceKlines`, `premiumIndex`, `fundingRate`, `fundingInfo`, `indexreferences`;
- smoke reel `BTCUSDT` et `INJUSDT` valide avec statuts `ok`;
- correction importante: `indexPriceKlines` utilise `pair`, pas `symbol`;
- `leverageBracket` et `commissionRate` sont volontairement bloques car `USER_DATA`;
- aucun credential, aucun wallet, aucun write, aucun ordre;
- objectif: preparer le pont MCP/API Aster pour remplacer progressivement les proxies perps par des donnees reelles Aster.
- endpoint reality check: `/api/onchain/rpc/aster-perps-reality-check-preview`;
- role reality check: classer les symboles en `backtest_quality_ok`, `backtest_quality_watch`, `backtest_quality_risky` selon volume, spread, depth, premium mark/index, funding, references d'index et completeness des endpoints.

Premier smoke reality check:

- `LABUSDT`: `backtest_quality_ok`, score `86`;
- `INJUSDT`: `backtest_quality_watch`, score `79`;
- `INTCUSDT`: `backtest_quality_watch`, score `61`, volume 24h faible;
- `CRCLUSDT`: `backtest_quality_watch`, score `61`, volume 24h faible.

Doc:

- `docs/aster-mcp-setup-plan.md`
- `docs/aster-mcp-phantom-wallet-setup.md`

## 10. Decisions actuelles

Continuer:

- `LABUSDT 5h/3h` en backtest champion;
- `INJUSDT 15m` en forward paper;
- `INTCUSDT 30m` en equities;
- `CRCLUSDT 2h` en macro;
- exploration des challengers via exclusions.

Ne pas faire:

- pas de trading reel;
- pas de x20 automatique;
- pas de conclusion sur un seul ROI;
- pas de signal client;
- pas de modification des parametres forward avant assez de sorties.

Seuils avant decision plus forte:

- au moins `30` sorties forward fermees pour une lane prioritaire;
- PF > `1.3`;
- drawdown supportable;
- latent ouvert sous controle;
- resultats non concentres sur une seule fenetre.

## 11. Fichiers de reference

Rapports:

- `docs/core-equity-aster-research-report.html`: dashboard courant;
- `docs/core-equity-aster-research-consolidated-report.html`: classement automatique multi-CSV avec lanes, symboles, timeframes, reality check et monitors;
- `docs/core-equity-aster-research-archive.md`: cette archive;
- `docs/core-equity-null-results-report.html`: hypotheses falsifiees;
- `docs/core-equity-rag-dashboard.html`: dashboard RAG.

Scripts/modules:

- `backend/services/onchain/aster/aster_agent_foundation.py`;
- `backend/services/onchain/aster/aster_agent_decision_engine.py`;
- `backend/services/onchain/aster/aster_mcp_market_data_adapter.py`;
- `backend/services/onchain/aster/aster_paper_trading_sandbox.py`;
- `backend/services/onchain/aster/backtest_strategy_discovery.py`;
- `backend/services/onchain/aster/monitor_optimized_longs.py`;
- `backend/services/onchain/aster/monitor_multi_strategy.py`;
- `backend/services/onchain/aster/monitor_shorts.py`.

Artefacts:

- `paper_trading_strategy_discovery_*_v2.csv`;
- `paper_trading_strategy_discovery_*_latest.json`;
- `paper_trading_strategy_discovery_heartbeat.json`;
- `paper_trading_multi_strategy_stateful_heartbeat.json`;
- `paper_trading_optimized_long_stateful_heartbeat.json`;
- ledger SQLite `aster_paper_trading_ledger`.

## 12. Note finale

Le travail Aster ne doit pas etre reduit au dernier dashboard. Les tests non
concluants ont ete utiles: ils ont evite de trader des faux signaux. Les tests
positifs actuels sont utiles aussi, mais seulement en paper/backtest. La bonne
trajectoire est:

1. continuer les runners champions;
2. forcer exploration via exclusions;
3. analyser les CSV V2 tagges;
4. construire un forward track record;
5. remplacer les proxies perps par donnees Aster reelles;
6. ne parler de trading reel qu'apres preuves forward suffisantes.
