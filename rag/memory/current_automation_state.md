# Core Equity - Etat operationnel courant

Derniere mise a jour: 2026-05-24.

Ce fichier est le dashboard operationnel court du RAG. Il doit rester lisible en francais. Les noms d'endpoints, fonctions, statuts JSON et chemins de fichiers restent en anglais pour ne rien casser.

## Ordre de lecture recommande

Lire dans cet ordre:
1. `rag/memory/core_equity_operating_map.md`
2. `rag/memory/current_automation_state.md`
3. `docs/core-equity-aster-research-report.html`
4. `docs/core-equity-null-results-report.html`
5. `rag/memory/core_equity_null_results_map.md`
6. `rag/memory/aster_python_structure_rules.md`
7. `rag/memory/project_state.md` seulement si l'historique complet est necessaire

## Statut simple

Core Equity n'est pas pret pour du trading reel.

Core Equity est pret pour:
- recherche forensique
- paper-trading Aster short/fade
- ledger stateful paper
- rapports HTML/RAG propres
- monitoring manuel ou semi-automatique sans wallet

Core Equity n'est pas pret pour:
- signal client
- execution wallet
- ordre Aster reel
- copie trading
- label/mapping automatique
- promesse de rentabilite

## Resultat actif le plus important

Les voies positives actuelles sont:
- Aster short/fade sur replays trades recents et forward paper stateful
- Aster long breakout volume sur replay historique kline 60j

Resume:
- Le long/buy simple Aster order-flow a ete falsifie.
- Le long breakout volume strict devient positif sur replay 60j kline proxy.
- Le diagnostic cinematique a montre un pattern de type `volatility_whipsaw`.
- Le short/fade exploite mieux ces anomalies que le long.
- Le backtest short/fade etendu montre un edge paper.
- Le monitor stateful a deja persiste une sortie forward gagnante.

Chiffres a retenir:
- win-rate backtest short/fade etendu: `88.9%`
- profit factor backtest short/fade etendu: `3.45`
- PnL backtest short/fade etendu: `+17.08 USD`
- profit factor risque optimise: `5.34`
- PnL risque optimise: `+9.78 USD`
- smoke univers volatile Aster short/fade: `11` entrees, `7` sorties, WR ferme `100%`, PnL paper `+32.064411 USD` sur `WIFUSDT`, `ORDIUSDT`, `1000SATSUSDT`, `LABUSDT`, `ARBUSDT`
- selection univers short/fade sur 26 symboles: 21 disponibles, meilleur agregat `balanced_6_8_trail_4_2`, `44` entrees, `32` sorties, WR `71.875%`, PF `3.493217`, PnL `+50.867086 USD`
- watchlist forward recommandee actuelle: `1000SATSUSDT,ORDIUSDT,JUPUSDT,ARBUSDT,OPUSDT,SEIUSDT,WLDUSDT,TIAUSDT`
- symboles a eviter pour cette logique short/fade actuelle: `LABUSDT`, `APTUSDT`, `ADAUSDT`, `LINKUSDT`, `SOLUSDT`
- dry-run du monitor forward selectionne: `7` fermetures virtuelles, PnL session `+23.291945 USD`, `would_insert_rows=17`, `writes_performed=0`
- test directionnel "bon sens" long sur watchlist selectionnee:
  - longs immediats restent faibles sauf `long_high_volume_breakout_75`
  - `long_high_volume_breakout_75`: `7` entrees, `6` sorties, WR `66.6667%`, PF `1.760548`, PnL `+6.091832 USD`
  - watchlist long dediee actuelle: `TIAUSDT,SEIUSDT,JUPUSDT,WLDUSDT`
  - sur cette watchlist long dediee, `long_high_volume_breakout_75`: `5` entrees, `5` sorties, WR `80%`, PF `6.366566`, PnL `+11.886675 USD`
  - long pullback est negatif sur watchlist complete; ne pas le prioriser actuellement
- premier PnL forward realise: `+0.493947 USD`
- dernier PnL latent short connu: environ `+2.8291 USD`
- ledger snapshot connu: `430` lignes, `4` entrees, `1` sortie

## Parametres a ne pas changer pendant le track record

Entree:
- `aster_score >= 75.0`
- `window_volume_usd >= 1000`

Sortie short:
- `stop_loss_pct=10.0`
- `take_profit_pct=-8.0`
- `trailing_stop_activation_pct=4.0`
- `trailing_stop_distance_pct=2.0`
- `max_holding_trades=600` ou zone cible `500-600`

Watchlist prioritaire:
- `LABUSDT`
- `ORDIUSDT`
- `1000SATSUSDT`
- `WIFUSDT`

## Surfaces operationnelles

Endpoints:
- `/api/onchain/rpc/aster-agent-command-center-preview`
- `/api/onchain/rpc/aster-paper-trading-stateful-session-monitor`
- `/api/onchain/rpc/aster-paper-trading-executor-confirm`
- `/api/onchain/rpc/aster-paper-trading-optimizer-executor-confirm`
- `/api/onchain/rpc/aster-paper-trading-ledger-analytics`
- `/api/onchain/rpc/aster-api-resilience-test`
- `/api/onchain/rpc/aster-volatile-universe-short-backtest-preview`
- `/api/onchain/rpc/aster-short-fade-universe-selection-preview`
- `/api/onchain/rpc/aster-selected-short-fade-forward-monitor-preview`
- `/api/onchain/rpc/aster-paper-trading-60d-kline-replay-preview`

Dernier ajout:
- `get_aster_paper_trading_60d_kline_replay_preview` ajoute un replay historique read-only sur klines Aster, par defaut `60j` en intervalle `1h`. Methodologie: proxy bougies, pas replay tick-level; chaque kline est convertie en evenement replayable avec volume quote et biais taker buy.
- Smoke 60j kline proxy sur `TIAUSDT,SEIUSDT`: long `long_high_volume_breakout_75` = `30` entrees, `30` sorties, WR `53.3333%`, PF `1.639454`, PnL paper `+40.083671 USD`; short optimise = `39` entrees, `39` sorties, WR `56.4103%`, PF `0.615159`, PnL paper `-46.851937 USD`; `writes_performed=0`.
- Replay 60j/1h sur `TIAUSDT,SEIUSDT,JUPUSDT,WLDUSDT,1000SATSUSDT,ORDIUSDT,ARBUSDT,OPUSDT`: long `71` entrees, `70` sorties, WR `52.8571%`, PF `1.189023`, PnL paper `+21.030065 USD`; short optimise PnL `-76.743395 USD`.
- Replay 60j/15m sur `TIAUSDT,JUPUSDT,ARBUSDT,1000SATSUSDT,ORDIUSDT,WLDUSDT`: long `118` entrees, `114` sorties, WR `56.1404%`, PF `1.249227`, PnL paper `+47.080303 USD`; short optimise PnL `-111.525206 USD`.
- Meilleurs candidats long 60j: `TIAUSDT`, `JUPUSDT`, `ARBUSDT`. `1000SATSUSDT` reste meilleur en short selectif sur le test 15m (`+21.129133 USD`, PF `2.363407`).
- `get_aster_paper_trading_multi_timeframe_replay_preview` compare maintenant `1h,30m,15m,5m` sur 60j. Garde-fou: `5m` est bloque pour 60j car trop granulaire en preview non persistant.
- Matrice 60j multi-timeframe (`1h/30m/15m`) sur `TIA,JUP,ARB,1000SATS,ORDI,WLD`: `TIAUSDT` long robuste, PnL cumule `+98.276561 USD`; `1000SATSUSDT` short robuste, PnL cumule `+42.459856 USD`. Autres: ARB/JUP long prometteurs, ORDI/WLD seulement prometteurs/faibles.
- Timeframes hauts ajoutes: `2h,3h,4h,5h,6h`. Les intervalles `3h` et `5h` sont reconstruits localement depuis les klines `1h` car Aster les refuse en direct.
- Matrice 60j haute timeframe (`2h/3h/4h/5h/6h`) sur `TIA,JUP,ARB,1000SATS,ORDI,WLD`: `TIAUSDT` long robuste PnL cumule `+67.061530 USD`; `JUPUSDT` long robuste `+23.956817 USD`; `1000SATSUSDT` short prometteur `+4.073238 USD`; ORDI/WLD faibles.
- Le rapport HTML Aster est restructure en format backtest de qualite: protocole, regles d'entree/sortie, matrice globale par timeframe, matrice par symbole, decision par actif, endpoints d'execution et garde-fous. Fichier: `docs/core-equity-aster-research-report.html`.
- Decisions actuelles apres matrice detaillee: `TIAUSDT` long priorite 1; `JUPUSDT` long priorite 2; `ARBUSDT` long observation; `1000SATSUSDT` short/fade selectif; `ORDIUSDT` et `WLDUSDT` non retenus comme strategies principales.
- Sweep agressif ROI/win-rate sur 26 symboles, timeframes `15m,30m,1h,2h,3h,4h`, variantes long/short. Meilleures lanes robustes:
  - `TIAUSDT` long `score>=80`, `volume>=5k`, SL `-6%`, TP `+12%`, trailing `6%/3%`: `76` trades fermes, WR `64.47%`, PnL `+157.612440 USD`, ROI `+15.76%`.
  - `INJUSDT` long meme strategie: `31` trades fermes, WR `80.65%`, PnL `+126.386160 USD`, ROI `+12.64%`, positif sur `15m/30m/1h/2h`.
  - `NEARUSDT` long `score>=75`, `volume>=1k`, SL `-4%`, TP `+8%`, trailing `4%/2%`: `63` trades fermes, WR `68.25%`, PnL `+77.414878 USD`, ROI `+7.74%`.
  - `BOMEUSDT` long `score>=80`, `volume>=5k`, SL `-6%`, TP `+12%`: `90` trades fermes, WR `54.44%`, PnL `+85.400445 USD`, ROI `+8.54%`; moins propre car 15m/30m faibles.
  - `LABUSDT` long ROI `+13.96%` mais fragile car dependant du 4h; `LABUSDT` short 15m ROI `+5.94%` mais negatif sur timeframes plus hauts.
- Sweep focalise haut ROI confirme les lanes prioritaires:
  - Priorite 1: `TIAUSDT` long `score>=80`, `volume>=5k`, SL `-6%`, TP `+12%`, trailing `6%/3%`: `76` trades, WR `64.47%`, ROI `+15.76%`, PnL `+157.61 USD`, positif sur `15m/30m/1h/2h/3h`.
  - Priorite 2: `INJUSDT` long meme set: `31` trades, WR `80.65%`, ROI `+12.64%`, PnL `+126.39 USD`, positif sur `15m/30m/1h/2h`.
  - Priorite 3: `INJUSDT` long frequent `score>=70`, `volume>=5k`, SL `-3%`, TP `+6%`, trailing `3%/1.5%`: `109` trades, WR `72.48%`, ROI `+10.37%`.
- Endpoint ajoute: `/api/onchain/rpc/aster-paper-trading-focused-walkforward-preview`. Objectif: decouper les meilleures lanes en 3 fenetres temporelles 60j pour reduire le risque d'overfit.
- Smoke walk-forward focalise `TIA,INJ,NEAR,BOME,1000SATS` sur `15m,1h,3h`: meilleurs candidats robustes:
  - `INJUSDT` long strict `score>=80`, `volume>=5k`, SL `-6%`, TP `+12%`, trailing `6%/3%`, timeframe `15m`: `16` trades fermes, WR `81.25%`, PF `5.355475`, ROI `+5.647579%`, PnL `+56.475795 USD`.
  - `INJUSDT` long frequent `score>=70`, `volume>=5k`, SL `-3%`, TP `+6%`, trailing `3%/1.5%`, timeframe `15m`: `44` trades fermes, WR `70.4545%`, PF `2.123240`, ROI `+3.678555%`, PnL `+36.785550 USD`.
  - `NEARUSDT` long balanced `score>=75`, `volume>=5k`, SL `-4%`, TP `+8%`, trailing `4%/2%`, timeframe `15m`: `33` trades fermes, WR `66.6667%`, PF `1.818847`, ROI `+2.807873%`, PnL `+28.078734 USD`.
- Decision recherche actuelle: prioriser `INJUSDT` long 15m pour forward paper; garder `NEARUSDT` long 15m comme diversification; retrograder `TIAUSDT` derriere INJ car le walk-forward 1h reste prometteur mais moins robuste (`15` trades, WR `53.3333%`, PF `2.306387`, ROI `+4.226306%`).
- Documentation HTML Aster retravaillee: ajout d'un `Decision board`, d'un bloc `Niveau de preuve actuel`, d'une explication `Comment lire les ROI`, et d'une lecture priorisee des lanes (`INJUSDT` long 15m priorite 1, `INJUSDT` frequent priorite 2, `NEARUSDT` long 15m diversification). Le rapport contient maintenant 12 sections et 12 tables structurees.
- Endpoint ajoute: `/api/onchain/rpc/aster-paper-trading-focused-optimization-preview`. Il optimise uniquement les pistes long prometteuses (`INJUSDT`, `NEARUSDT`, `TIAUSDT`) sur score, volume, SL/TP/trailing, avec walk-forward 3 fenetres et read-only strict.
- Smoke optimisation focalisee `INJUSDT/15m`: `90` combinaisons testees, `61` candidates acceptees. Meilleure lane: `score>=75`, `volume>=3k`, SL `-6%`, TP `+12%`, trailing `6%/3%`, `19` trades fermes, WR `78.9474%`, PF `4.639460`, ROI `+6.211458%`, PnL `+62.114582 USD`, `writes_performed=0`.
- Nouvelle priorite forward paper: remplacer l'ancien INJ strict `80/5k` par `INJUSDT 15m score>=75 volume>=3k SL6 TP12 trailing6/3`, tout en gardant `80/3k` et `75/5k` comme variantes de controle.
- Endpoint ajoute: `/api/onchain/rpc/aster-optimized-long-forward-monitor-preview`. Il isole les lanes long optimisees (`INJUSDT`, `NEARUSDT`, `TIAUSDT`) du short/fade et persiste seulement avec `CONFIRM_FORWARD_PAPER_TRADE`.
- Smoke dry-run forward long optimise 800 trades recents: portfolio `INJ+NEAR+TIA` = `10` signaux, WR ferme `75%`, PnL `+8.097303 USD`, writes `0`. Detail: `INJ` PnL `-2.572506` avec 1 position ouverte latente `+1.866195`; `NEAR` PnL `+2.583814` avec 1 position ouverte; `TIA` PnL `+8.085995` avec 2/2 sorties gagnantes.
- Premiere execution confirmee paper-only du monitor long optimise: `rows_inserted=10`, `writes_performed=10`, `health_status=active`, aucun wallet/trade reel. Ledger analytics apres insertion: `total_entries=10`, `total_exits=5`, WR `80%`, PF `2.841265`, net PnL `+7.705056 USD`, max drawdown `6.714803 USD`.
- Script CLI ajoute: `backend/services/onchain/aster/monitor_optimized_longs.py`. Il suit `INJUSDT,NEARUSDT,TIAUSDT`, ecrit `paper_trading_optimized_long_monitor.csv`, reste dry-run par defaut et n'insere en ledger paper qu'avec `--persist` (confirm interne `CONFIRM_FORWARD_PAPER_TRADE`). Dry-run valide: `would_insert_rows=10`, ledger exits `5`, net PnL `+7.705056`, WR `0.8`.
- Diagnostic monitor long: le replay forward stateless finissait par renvoyer des valeurs proches sans inserer, car il ne reprenait pas vraiment les positions ouvertes du ledger. Correction ajoutee: `get_aster_optimized_long_stateful_monitor` + endpoint `/api/onchain/rpc/aster-optimized-long-stateful-monitor`.
- Le stateful long optimise lit les anciennes positions `forward_optimized_long_replay`, cree les nouvelles lignes sous `forward_optimized_long_stateful`, traite uniquement les nouveaux trades, et persiste des `mark_to_market` paper pour conserver `last_processed_trade_id`, peak et PnL latent. Cycle confirme: `rows_inserted=2`, `closed_in_session=0`, active INJ latent `+1.207538`, active NEAR latent `+1.505653`; ledger reste `14` entries, `8` exits, WR `87.5%`, PF `5.192943`, net PnL `+17.546012`.
  - Priorite 4: `NEARUSDT` long `score>=75`, `volume>=5k`, SL `-4%`, TP `+8%`: `67` trades, WR `67.16%`, ROI `+7.39%`.
- `get_aster_selected_short_fade_forward_monitor_preview` lance le monitor stateful sur la watchlist selectionnee avec les parametres short/fade optimises: score `70`, volume `1000`, SL `8%`, TP `-6%`, trailing `4%/2%`.
- Smoke dry-run: symbols `1000SATSUSDT,ORDIUSDT,JUPUSDT,ARBUSDT,OPUSDT,SEIUSDT,WLDUSDT,TIAUSDT`; `closed_in_session=7`, `realized_pnl_session=+23.291945`, `would_insert_rows=17`, `writes_performed=0`, `health_status=active`.
- `get_aster_short_fade_universe_selection_preview` transforme le backtest volatile en selection exploitable: `selected_forward_candidate`, `watchlist_needs_more_closed_trades`, `rejected_negative_or_no_signal`.
- Smoke selection valide: recommended CSV `1000SATSUSDT,ORDIUSDT,JUPUSDT,ARBUSDT,OPUSDT,SEIUSDT,WLDUSDT,TIAUSDT`.
- Walk-forward configurable avec parametres short optimises: `short_stop_loss_pct`, `short_take_profit_pct`, `trailing_stop_activation_pct`, `trailing_stop_distance_pct`, `min_aster_score`, `min_window_volume_usd`.
- `get_aster_volatile_universe_short_backtest_preview` scanne un univers Aster volatile ou une liste manuelle, applique un sweep short/fade read-only, et agrege les resultats par parametre.
- Smoke manuel valide sur `WIFUSDT,ORDIUSDT,1000SATSUSDT,LABUSDT,ARBUSDT`: meilleur set `balanced_6_8_trail_4_2`, `11` entrees, `7` sorties, WR ferme `100%`, PnL `+32.064411 USD`, verdict `no_conclusive_edge` car echantillon ferme encore trop petit.
- `get_aster_paper_trading_stateful_session_monitor` ecrit maintenant un `session_run_id` stable par cycle et inclut `last_processed_trade_id` dans les payloads forward entry/exit.
- Le replay stateful ignore strictement les trades dont `trade_id <= last_processed_trade_id`, pour eviter les fantomes apres downtime API ou restart.
- `/api/onchain/rpc/aster-agent-command-center-preview` donne une vue unifiee: positions ouvertes, sorties recentes, performance des 30 dernieres sorties, sante API et staging dry-run.
- Smoke staging dry-run sur `LABUSDT,ORDIUSDT,1000SATSUSDT`: `ok=True`, `writes_performed=0`, `would_execute_trade=False`, `open_positions=3`, `recent_exits=1`, `api_status=active`.

Module principal:
- `backend/services/onchain/aster/aster_paper_trading_sandbox.py`

Script de monitoring:
- `backend/services/onchain/aster/monitor_shorts.py`
- Le script compare maintenant plusieurs strategies short/fade en un cycle via `get_aster_volatile_universe_short_backtest_preview`.
- Par defaut, la lane forward selectionnee reste dry-run; pour persister les rows paper selected, definir `ASTER_MONITOR_PERSIST=1`.
- Logs separes:
  - `paper_trading_monitor.csv`: ancien historique simple conserve
  - `paper_trading_multi_strategy_monitor.csv`: resume par cycle multi-strategies
  - `paper_trading_strategy_monitor.csv`: une ligne par strategie testee
  - `paper_trading_directional_strategy_monitor.csv`: compare short, long momentum et long pullback

Docs:
- `docs/core-equity-aster-research-report.html`
- `docs/core-equity-null-results-report.html`
- `docs/core-equity-rag-dashboard.html`

## Regle d'observation

Ne pas conclure trop vite.

Attendre au minimum:
- `total_exits >= 10`
- `win_rate >= 55%`
- `profit_factor >= 1.3`
- drawdown acceptable sur capital paper theorique

Si les sorties stagnent:
- ne pas changer immediatement les parametres
- laisser le monitor tourner
- verifier seulement la sante API et le ledger

## Garde-fous

Toujours vrai:
- `would_execute_trade=false`
- pas de wallet order
- pas de cle trading
- pas de signal client
- pas d'opt-in
- pas de DB write hors table paper-trading dediee
- toute ecriture paper exige un confirm explicite

## Prochaine action recommandee

Continuer le monitor paper short/fade jusqu'a obtenir un vrai echantillon de sorties.

Ne pas lancer une nouvelle hypothese de trading tant que:
- le ledger short/fade n'a pas assez de sorties
- le rapport Aster n'a pas ete mis a jour avec les nouvelles metriques
- le RAG n'a pas ete reindexe apres modification durable
