# Core Equity - Carte operationnelle

Derniere mise a jour: 2026-05-24.

Ce fichier est la carte courte a lire en premier par Codex, Qwen, le Prompt Manager ou un futur agent. Pour l'historique detaille, utiliser `rag/memory/project_state.md`.

## Objectif produit

Core Equity vise a devenir un systeme autonome d'intelligence crypto et de controle trading, mais seulement apres preuves paper-trading et garde-fous.

Objectif final:
- collecter et nettoyer des donnees on-chain / marche de haute qualite
- detecter des comportements de manipulation avant qu'ils deviennent evidents
- classifier les patterns: wash, distribution, accumulation, CEX-flow, scam, treasury, unknown
- separer preuve source-backed, preuve comportementale et preuve economique
- tester en shadow/paper avant toute execution reelle
- permettre a un futur Trade Agent d'agir uniquement sous Policy/Risk gates stricts

Priorite court terme:
- ne pas chercher un trade reel
- ne pas creer de signal client
- continuer le track record Aster short/fade en paper-trading
- garder les tests non concluants dans leur archive dediee

## Realite produit actuelle

Core Equity n'est pas trading-ready en reel.

Ce qui est vrai aujourd'hui:
- Le moteur forensique detecte des anomalies et rejette de fausses pistes.
- Plusieurs hypotheses initiales ont ete falsifiees: CEX listing prediction, DEX pump long, honeypot correlation, Aster long/buy seul.
- Deux voies positives existent maintenant: Aster short/fade paper-trading recent et Aster long breakout volume sur replay kline 60j.
- Le premier forward paper realise est positif: `+0.493947 USD`.
- Les derniers shorts ouverts connus etaient en PnL latent positif: environ `+2.8291 USD`.
- Tout reste paper-only: aucun ordre wallet, aucun trade reel, aucune cle trading.

## Voie positive active

Voie: Aster short/fade paper-trading.

These:
- Les anomalies order-flow Aster simples ne doivent pas etre achetees en long sans filtre.
- Le long breakout volume strict (`aster_score >= 75`, `window_volume_usd >= 5000`, SL `-6%`, TP `+10%`, trailing `6%/3%`) devient positif sur replay historique 60j.
- Elles marquent souvent des zones a fader.
- La strategie short/fade semble meilleure que le long sur les replays actuels.

Resultats utiles:
- Backtest short/fade etendu: win-rate `88.9%`, profit factor `3.45`, PnL paper `+17.08 USD`.
- Parametres risque optimises: profit factor `5.34`, PnL paper `+9.78 USD`.
- Scan univers volatile Aster short/fade: meilleur set `balanced_6_8_trail_4_2`, `11` entrees, `7` sorties, WR ferme `100%`, PnL paper `+32.064411 USD` sur 5 actifs connus. Verdict encore prudent: echantillon ferme trop petit.
- Selection univers short/fade: 26 symboles testes, 21 disponibles, `44` entrees, `32` sorties, WR `71.875%`, PF `3.493217`, PnL paper `+50.867086 USD`.
- Watchlist forward recommandee: `1000SATSUSDT`, `ORDIUSDT`, `JUPUSDT`, `ARBUSDT`, `OPUSDT`, `SEIUSDT`, `WLDUSDT`, `TIAUSDT`.
- Monitor forward selectionne dry-run: `7` sorties virtuelles, PnL session `+23.291945 USD`, `17` lignes qui seraient inserees, `0` write par defaut.
- Test "bon sens" long: la seule piste long positive actuelle est `long_high_volume_breakout_75` avec WR `66.6667%`, PF `1.760548`, PnL paper `+6.091832 USD`; les longs immediats simples et pullbacks restent globalement negatifs.
- Watchlist long dediee: `TIAUSDT`, `SEIUSDT`, `JUPUSDT`, `WLDUSDT`. Sur cette sous-selection, `long_high_volume_breakout_75` donne WR `80%`, PF `6.366566`, PnL paper `+11.886675 USD`.
- Replay historique 60j ajoute: `/api/onchain/rpc/aster-paper-trading-60d-kline-replay-preview`. Il utilise les klines Aster en proxy bougies, pas les trades tick-level. Smoke `TIAUSDT,SEIUSDT` sur `60j/1h`: long breakout WR `53.3333%`, PF `1.639454`, PnL paper `+40.083671 USD`; short optimise PF `0.615159`, PnL paper `-46.851937 USD`.
- Replay 60j/1h univers mixte (`TIA,SEI,JUP,WLD,1000SATS,ORDI,ARB,OP`): long `71` entrees, `70` sorties, WR `52.8571%`, PF `1.189023`, PnL paper `+21.030065 USD`; short PnL `-76.743395 USD`.
- Replay 60j/15m shortlist (`TIA,JUP,ARB,1000SATS,ORDI,WLD`): long `118` entrees, `114` sorties, WR `56.1404%`, PF `1.249227`, PnL paper `+47.080303 USD`; short PnL `-111.525206 USD`.
- Meilleurs longs 60j a prioriser: `TIAUSDT`, `JUPUSDT`, `ARBUSDT`. Short selectif encore utile sur `1000SATSUSDT`.
- Replay 60j multi-timeframe ajoute: `/api/onchain/rpc/aster-paper-trading-multi-timeframe-replay-preview`. Timeframes testes `1h,30m,15m`; `5m` bloque par garde-fou car trop granulaire pour preview 60j sans persistance locale.
- Robustesse multi-timeframe: `TIAUSDT` long robuste avec PnL cumule `+98.276561 USD`; `1000SATSUSDT` short robuste avec PnL cumule `+42.459856 USD`. ARB/JUP long prometteurs mais moins robustes; ORDI/WLD faibles/prometteurs seulement.
- Timeframes hauts `2h,3h,4h,5h,6h` ajoutes. `3h` et `5h` sont synthetiques depuis les klines `1h` car l'API Aster les refuse en direct.
- Robustesse haute timeframe 60j: `TIAUSDT` long robuste PnL cumule `+67.061530 USD`; `JUPUSDT` long robuste `+23.956817 USD`; `1000SATSUSDT` short prometteur `+4.073238 USD`.
- Rapport HTML Aster transforme en rapport de backtest detaille: protocole, source de donnees, frais/slippage, capital paper, granularites, matrices par timeframe/symbole, decisions par actif et limites du proxy kline.
- Decisions actuelles: priorite long `TIAUSDT`; second long `JUPUSDT`; observation long `ARBUSDT`; short selectif `1000SATSUSDT`; rejeter `ORDIUSDT` et `WLDUSDT` comme strategies principales pour l'instant.
- Sweep agressif ajoute au rapport Aster. Nouvelles meilleures lanes:
  - `TIAUSDT` long `80/5k/SL6/TP12/trailing6-3`: `76` trades, WR `64.47%`, ROI `+15.76%`.
  - `INJUSDT` long meme set: `31` trades, WR `80.65%`, ROI `+12.64%`.
  - `NEARUSDT` long `75/1k/SL4/TP8/trailing4-2`: `63` trades, WR `68.25%`, ROI `+7.74%`.
  - `BOMEUSDT` long: ROI `+8.54%` mais qualite moindre.
  - `LABUSDT` long/short donne de gros ROI mais plus fragile et a verifier hors echantillon.
- Sweep focalise: meilleur prochain axe = long momentum/breakout. Priorites:
  - `TIAUSDT` long `80/5k/SL6/TP12/trailing6-3`: `76` trades, WR `64.47%`, ROI `+15.76%`.
  - `INJUSDT` long `80/5k/SL6/TP12/trailing6-3`: `31` trades, WR `80.65%`, ROI `+12.64%`.
  - `INJUSDT` long frequent `70/5k/SL3/TP6/trailing3-1.5`: `109` trades, WR `72.48%`, ROI `+10.37%`.
- Endpoint `focused-walkforward-preview` ajoute pour separer les meilleures lanes en 3 fenetres temporelles 60j. Smoke `15m/1h/3h` sur `TIA,INJ,NEAR,BOME,1000SATS`: `INJUSDT` long strict 15m devient priorite 1 (`16` trades, WR `81.25%`, PF `5.355475`, ROI `+5.647579%`); `INJUSDT` long frequent 15m priorite 2 (`44` trades, WR `70.4545%`, PF `2.123240`, ROI `+3.678555%`); `NEARUSDT` long 15m priorite 3 (`33` trades, WR `66.6667%`, PF `1.818847`, ROI `+2.807873%`).
- Nouvelle lecture: `TIAUSDT` a le meilleur ROI brut dans le sweep, mais `INJUSDT` a la meilleure robustesse walk-forward. Pour la suite, privilegier validation forward paper sur `INJUSDT` 15m et `NEARUSDT` 15m avant d'augmenter le levier ou la frequence.
- Rapport HTML Aster restructure pour lecture decisionnelle: hero recentre sur lanes filtrees, `Decision board`, `Niveau de preuve actuel`, explication des ROI paper, endpoint `focused-walkforward-preview` ajoute dans la table des surfaces, et parametres operationnels mis a jour vers `INJUSDT`/`NEARUSDT` long 15m.
- Endpoint `focused-optimization-preview` ajoute pour optimiser les lanes long prometteuses sans refaire un sweep global. Meilleur resultat smoke `INJUSDT 15m`: `score>=75`, `volume>=3k`, SL `-6%`, TP `+12%`, trailing `6/3`, `19` trades fermes, WR `78.9474%`, PF `4.639460`, ROI `+6.211458%`, PnL paper `+62.114582 USD`. C'est maintenant la priorite 1 forward paper.
- Endpoint `aster-optimized-long-forward-monitor-preview` ajoute pour suivre en forward paper les lanes long optimisees, separees du short/fade. Smoke 800 trades recents sur `INJ,NEAR,TIA`: PnL total `+8.097303 USD`, WR ferme `75%`, `10` signaux dry-run, writes `0`. Ce monitor est la surface principale pour construire le track record long.
- Premier run confirme paper-only du monitor long optimise insere `10` rows ledger. Metriques ledger: `10` entries, `5` exits, WR `80%`, PF `2.841265`, net PnL `+7.705056 USD`, MDD `6.714803 USD`. Objectif suivant: repeter jusqu'a `30` sorties fermees avant toute decision live.
- Script `monitor_optimized_longs.py` ajoute pour repeter le forward long optimise proprement. Commande: `cd backend && python -m services.onchain.aster.monitor_optimized_longs --cycles 12 --sleep-seconds 300 --persist`; sans `--persist`, dry-run uniquement avec log CSV.
- Le monitor long optimise utilise maintenant le vrai endpoint stateful `/api/onchain/rpc/aster-optimized-long-stateful-monitor`. Il reprend les positions ouvertes du ledger, ne traite que les nouveaux trades, et ajoute des mark-to-market paper pour eviter les positions fantomes. Dernier etat: ledger `14` entries / `8` exits, WR `87.5%`, PF `5.192943`, net PnL `+17.546012`, INJ/NEAR encore ouverts en latent positif.
  - `NEARUSDT` long `75/5k/SL4/TP8/trailing4-2`: `67` trades, WR `67.16%`, ROI `+7.39%`.
- Forward confirme: 1 sortie gagnante, PnL realise `+0.493947 USD`.
- Ledger paper snapshot connu: `430` lignes, `4` entrees, `1` sortie.

Seuil avant conclusion plus forte:
- attendre au moins `10` sorties fermees dans le ledger
- surveiller win-rate, profit factor, net PnL et max drawdown
- ne pas modifier les parametres pendant la fenetre d'observation

## Parametres Aster a conserver pendant l'observation

Entree short/fade:
- `aster_score >= 75.0`
- `window_volume_usd >= 1000`
- watchlist prioritaire: `LABUSDT`, `ORDIUSDT`, `1000SATSUSDT`, `WIFUSDT`
- watchlist short/fade selectionnee par donnees: `1000SATSUSDT`, `ORDIUSDT`, `JUPUSDT`, `ARBUSDT`, `OPUSDT`, `SEIUSDT`, `WLDUSDT`, `TIAUSDT`

Sortie short optimisee:
- stop-loss: `+10%` au-dessus de l'entree
- take-profit: `-8%` sous l'entree
- trailing activation: `4%`
- trailing distance: `2%`
- time-stop cible: `500-600` trades

Entree long breakout 60j:
- `aster_score >= 75.0`
- `window_volume_usd >= 5000`
- watchlist prioritaire: `TIAUSDT`, `JUPUSDT`, `ARBUSDT`
- sortie: SL `-6%`, TP `+10%`, trailing activation `6%`, trailing distance `3%`

## Surfaces utiles

Rapports HTML:
- `docs/core-equity-aster-research-report.html`: rapport positif Aster short/fade
- `docs/core-equity-null-results-report.html`: archive des hypotheses falsifiees
- `docs/core-equity-rag-dashboard.html`: tableau de bord RAG court

Endpoints Aster utiles:
- `/api/onchain/rpc/aster-agent-command-center-preview`
- `/api/onchain/rpc/aster-paper-trading-stateful-session-monitor`
- `/api/onchain/rpc/aster-paper-trading-optimizer-executor-confirm`
- `/api/onchain/rpc/aster-paper-trading-ledger-analytics`
- `/api/onchain/rpc/aster-api-resilience-test`
- `/api/onchain/rpc/aster-volatile-universe-short-backtest-preview`
- `/api/onchain/rpc/aster-short-fade-universe-selection-preview`
- `/api/onchain/rpc/aster-selected-short-fade-forward-monitor-preview`
- `/api/onchain/rpc/aster-paper-trading-60d-kline-replay-preview`
- `/api/onchain/rpc/aster-paper-trading-multi-timeframe-replay-preview`
- `/api/onchain/rpc/aster-paper-trading-60d-kline-replay-preview`

Script local:
- `backend/services/onchain/aster/monitor_shorts.py`
- Le monitor est organise en mode multi-strategies: forward selected monitor + sweep short/fade read-only.
- Par defaut, aucune ecriture ledger depuis le monitor (`dry_run_forward`). Pour persister la lane selected uniquement: `ASTER_MONITOR_PERSIST=1`.
- CSV:
  - `paper_trading_multi_strategy_monitor.csv`
  - `paper_trading_strategy_monitor.csv`
  - `paper_trading_directional_strategy_monitor.csv`
  - `paper_trading_monitor.csv` conserve l'ancien historique simple.

## Toujours interdit

Interdit tant qu'un objectif produit explicite ne le change pas:
- signal client
- ordre wallet
- trade reel
- cle trading Aster
- opt-in client
- label CEX write
- mapping DEX faible
- scraping non borne
- agent autonome non borne

## Regle Prompt Manager

Quand un prochain objectif est genere:
- commencer par ce fichier
- lire `current_automation_state.md` pour le snapshot operationnel
- lire `core_equity_null_results_map.md` seulement pour eviter de repeter les fausses pistes
- lire `project_state.md` uniquement pour l'historique
- preferer les missions en francais
- conserver les noms techniques, endpoints, fonctions et champs JSON en anglais
- ne jamais transformer un resultat paper en signal client
