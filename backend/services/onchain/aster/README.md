# Aster Suite - Index operationnel

Derniere mise a jour: 2026-06-02

Ce dossier contient la suite Aster de Core Equity: adapters read-only, backtests,
paper trading, monitors forward et rapports. Il y a beaucoup de fichiers, mais
ils ne doivent pas tous etre lances. Ce README sert de carte.

Regle generale:

- aucun trade reel;
- aucun appel wallet;
- aucun signal client;
- aucun write hors ledger paper-trading explicitement confirme;
- les scripts de recherche ecrivent seulement des CSV/JSON locaux;
- les rapports lisent les artefacts et ne relancent pas de backtest lourd.

## Contrat anti-faux backtest

Cette section est prioritaire sur les anciens exemples de commandes. Elle existe
parce que plusieurs bons resultats papier ont ete declasses apres correction de
la methode. On garde l'historique, mais on ne repete pas les memes erreurs.

### Ce qu'un resultat doit contenir

Une ligne backtest exploitable doit conserver l'identite complete de la lane:

`output_tag + symbol + interval + side + trigger_reference + execution_model + leverage + score_window_size + strategy_profile_key`

Si un CSV/JSON ne permet pas de reconstruire cette identite, il est archive ou
exploratoire. Il ne doit pas servir a promouvoir une strategie.

### PnL, ROI et positions ouvertes

- `pnl_total_usd` doit representer le PnL realise.
- Le latent ouvert doit rester separe sous un champ du type
  `open_unrealized_pnl_usd`.
- Si on veut tout lire ensemble, utiliser explicitement
  `pnl_total_including_unrealized_usd`.
- Ne jamais classer une lane sur un solde final qui incorpore une position
  ouverte sans le signaler.

### Levier perps

Quand `leverage > 1`, les couts doivent etre calcules sur l'exposition
notionnelle, pas seulement sur la marge:

- `exposure_notional_usd = position_margin_usd * leverage`;
- frais maker/taker sur l'exposition;
- funding sur l'exposition;
- drawdown/liquidation evalues avec marge isolee ou proxy explicite;
- ROI final rapporte au capital papier, pas seulement au notional.

Un backtest qui augmente le levier sans recalculer frais, funding, liquidation
et margin risk est invalide pour decision.

### Prix de reference et execution

- `trigger_reference=mark_price` exige une reference futures valide.
- Interdit: valider une lane mark-price avec fallback Spot silencieux.
- `execution_model` doit rester visible: `taker_market`, `maker_post_only` ou
  `bbo_limit`.
- Les intervalles synthetiques `3h/5h` doivent etre agreges par timestamp absolu,
  pas par paquets arbitraires de bougies.

### Validation out-of-sample

Depuis le 2026-06-02 soir, les sorties V2 doivent exposer:

- `out_of_sample_status`;
- `train_closed_trades`, `train_win_rate`, `train_profit_factor`,
  `train_pnl_total_usd`;
- `validation_closed_trades`, `validation_win_rate`,
  `validation_profit_factor`, `validation_pnl_total_usd`;
- `train_validation_split`.

Une lane peut etre interessante en recherche si le train est bon. Elle ne devient
canditate decisionnelle que si la fenetre recente de validation reste positive.

### Artefacts et `latest`

- Toujours preferer les sorties taggees par `output_tag`.
- Ne pas utiliser `paper_trading_strategy_discovery_latest.json` comme source de
  decision: il peut etre ecrase par un smoke test.
- Les `*_heartbeat.json` prouvent qu'un runner tourne, pas qu'une strategie est
  rentable.
- Les vieux ROI/PF/WR de `LAB`, `HYPE`, `CRCL`, `MSFT`, `INTC`, `INJ`, etc. sont
  des pistes historiques tant qu'ils ne sont pas regeneres apres les correctifs.

### Validation obligatoire apres une session

Lire dans cet ordre:

1. CSV V2 tagge avec colonnes train/validation;
2. `aster_candidate_validation_queue_latest.csv`;
3. `aster_queue_reality_pack_validator_latest.csv`;
4. `aster_microstructure_replay_validator_latest.json`;
5. `aster_mark_index_replay_filter_latest.json`;
6. rapports `promotion_truth` / `lane_promotion_scoring`.

Ne jamais promouvoir une lane parce qu'elle est "best" dans un terminal. Le
terminal affiche le meilleur candidat du batch courant, pas une preuve finale.

### Correctifs appliques apres audit sous-agents

- Perps: `position_size_usd` est traite comme marge isolee papier; l'exposition
  notionnelle devient `margin * leverage`.
- V2: ajout de champs best-leverage apres couts et de champs
  realise/latent/total-including-unrealized.
- Scoring: le classement penalise plus fortement l'OOS echoue ou absent et
  prefere le ROI apres couts du meilleur levier tradable quand disponible.
- Promotion: `PROMOTION_READY` exige maintenant `mark_index_confirmed`;
  `mark_index_watch` et `not_checked` restent en watch.
- Truth report: suppression du fallback `symbol_only` dans les decisions de
  lane, pour eviter de coller une verite LAB 5h a une lane LAB 30m.
- Truth report / scoring: suppression des fallbacks `side_token`,
  `legacy_token` et `base_lane_key`. Une lane sans identite strategique complete
  est maintenant `identity_missing` et ne peut plus heriter d'une verite voisine.
- V2: les estimations top-level `round_trip_fee_usd_estimate`,
  `funding_cost_usd_estimate` et `exchange_filter_verdict` utilisent maintenant
  l'exposition notionnelle du meilleur levier tradable, pas seulement la marge.
- Focused optimizer: le plafond implicite de 5 symboles est retire au profit
  d'un plafond de securite a 30 symboles, pour ne plus tronquer les watchlists.
- Aster v2 runner: un `output_tag` non-default n'ecrase plus le plan
  `latest` global; les plans tagges restent separes.
- Forward ledger: si `trade_id` manque, l'idempotence utilise un hash stable
  du payload/symbole/action au lieu de supprimer silencieusement la ligne.
- RL lane policy: ajout d'un garde-fou anti-erreur par lane. Une lane ne peut
  plus etre promue si `mistake_guardrail_verdict != clean`, meme si le ROI/PF
  est attractif. Les raisons sont visibles via `mistake_blockers`,
  `mistake_warnings` et `required_next_actions`.

### RL comme garde-fou qualite

Le RL actuel n'est pas une promesse que le code ne fera plus jamais d'erreur.
Son role dans notre setup est plus concret: refuser de recommander des lanes
qui ressemblent aux erreurs deja rencontrees.

Il bloque ou degrade notamment:

- CSV `_progress_` utilises comme resultat final;
- identite incomplete de strategie/lane;
- validateurs `mark_index`, `microstructure` ou `reality_pack` plus vieux que
  le CSV source;
- OOS absent ou echoue;
- microstructure non verifiee ou illiquide;
- `exchange_filter` absent, warning ou bloque;
- levier invalide ou non revalide;
- PnL latent ouvert melange avec PnL realise;
- echantillon trop faible.

Lecture operationnelle:

- `clean`: peut entrer dans une discussion forward;
- `watch_only`: piste interessante mais pas decisionnelle;
- `review_required`: il manque une validation ou une correction;
- `promotion_blocked`: ne pas promouvoir, meme si le terminal affiche un ROI fort.

### Lecture du run post-fix du 2026-06-03

Apres les correctifs, les resultats papier les plus hauts ne suffisent toujours
pas a promouvoir une lane:

- `LABUSDT 30m` ressort encore tres fort en paper backtest post-fix
  (`~50.69%` ROI papier, `WR ~65.5%`, `PF ~2.79`, `87` trades fermes,
  OOS passe), mais le controle mark/index cible le rejette sur `15m/30m/2h/3h/5h`.
  Conclusion: `LAB` reste une piste de recherche, pas une lane forward propre.
- Les lanes strictement propres du pack realite restent `HYPEUSDT`
  (`15m`, `3h`, `5h`), avec `mark_index_confirmed` et `microstructure_ok`,
  mais ROI plus modeste (`~5.2-5.7%`).
- Les challengers post-fix (`INJUSDT`, `INTCUSDT`, `WLDUSDT`, `CRCLUSDT`,
  `DRAMUSDT`, `JUPUSDT`, `NVDAUSDT`, `MSFTUSDT`) sont utiles pour exploration,
  mais leur microstructure/mark-index n'est pas encore assez propre pour
  promotion.

Decision: pour la prochaine session, ne pas classer sur ROI brut. Lancer les
runners de recherche pour trouver des challengers, puis promouvoir uniquement
les lanes qui passent `mark_index_confirmed` + `microstructure_ok` + OOS.

## Structure du dossier

La migration vers une suite Aster plus propre a commence doucement.

### `data_sources/`

Nouveaux modules read-only pour decouvrir et valider les donnees Aster:

- `data_sources/source_validation.py`: valide les endpoints REST publics et leurs schemas;
- `data_sources/public_universe_snapshot.py`: construit l'univers public Aster all-symbol;
- `data_sources/ws_market_stream_validation.py`: valide les streams WebSocket publics;
- `data_sources/ws_forward_monitor_preview.py`: compare WS vs REST pour un symbole;
- `data_sources/ws_symbol_quality_report.py`: classe les symboles selon leur qualite WS.

Les anciens imports restent compatibles via wrappers:

- `aster_data_source_validation.py`
- `aster_public_universe_snapshot.py`
- `aster_ws_market_stream_validation.py`
- `aster_ws_forward_monitor_preview.py`
- `aster_ws_symbol_quality_report.py`

Regle: les nouveaux modules de data source doivent aller dans `data_sources/`.
Les gros modules legacy, notamment `aster_paper_trading_sandbox.py`, restent en place pour ne pas casser les runners.

### Testnet/demo Aster

Le testnet est valide pour la signature et la lecture compte, mais pas pour
valider directement nos champions:

- agent wallet testnet dedie autorise depuis Metamask;
- `GET /fapi/v3/balance` read-only OK via signature EIP-712;
- `BTC`, `ASTER`, `USDT`, `AFEE` visibles;
- `LABUSDT`, `INJUSDT`, `TIAUSDT`, `INTCUSDT` absents du testnet;
- aucun ordre demo n'a ete place.

Endpoints utiles:

- `/api/onchain/rpc/aster-demo-testnet-readiness-preview`
- `/api/onchain/rpc/aster-demo-order-intent-validator-preview`

Conclusion: garder le testnet comme banc de verification execution/signature.
Ne pas l'utiliser comme preuve de rentabilite des lanes championnes tant que les
symboles ne sont pas disponibles dessus.

## Commandes a utiliser

## Decision historique avant re-runs post-correctifs

Ne pas confondre un ROI papier haut avec une lane tradable. Le bloc ci-dessous
garde visible le travail fait avant le contrat anti-faux backtest. Il sert a
choisir quoi re-tester, pas a conclure.

- `LABUSDT long 30m`: meilleur ROI papier actuel, `mark_index_watch`,
  `microstructure_ok`; a tester en forward/replay strict, pas en confiance
  aveugle.
- `HYPEUSDT long 3h/5h/15m`: ROI plus modeste mais meilleure qualite realite:
  `mark_index_confirmed`, `microstructure_ok`, WS ready; revue exchangeInfo
  requise pour `tight_market_take_bound`.
- `PLAYUSDT`: recherche seulement tant que `gap_risk` reste present.
- `BOMEUSDT`: rejete/rework pour l'instant (`mark_index_rejected`,
  `not_enough_trades`).

Ordre de lecture obligatoire apres une session de backtests:

1. `python -m services.onchain.aster.aster_candidate_validation_queue`
2. `python -m services.onchain.aster.aster_research_consolidated_report`
3. `python -m services.onchain.aster.aster_promotion_truth_report`

La queue de validation est la source la plus utile pour savoir quoi faire
ensuite: valider mark/index, valider microstructure, garder en watch, ou rejeter.

### 0. Registry des scripts et familles de strategies

Avant d'ajouter ou de relancer un runner, regenerer la registry:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_strategy_registry
```

Sorties:

- `docs/core-equity-aster-strategy-registry.html`
- `backend/services/onchain/aster/aster_strategy_registry_latest.json`

Cette registry ne lance aucun backtest. Elle sert a savoir quel fichier Python
correspond a quelle famille de strategie, quels artefacts il produit, et si le
script est `active_core`, `active_exploration`, `active_control`,
`legacy_watch` ou `archive`.

Regle importante: une strategie backtestee n'est pas identifiee seulement par
son symbole. Elle doit garder `output_tag + symbol + interval + side +
trigger_reference + execution_model + leverage`. Une strategie forward doit
etre identifiee par `event_type` ou `strategy_id`.

### 0 bis. Queue de validation des candidats

Apres une journee de backtests, generer la file de validation:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_candidate_validation_queue
```

Sorties:

- `docs/core-equity-aster-candidate-validation-queue.html`
- `backend/services/onchain/aster/aster_candidate_validation_queue_latest.json`
- `backend/services/onchain/aster/aster_candidate_validation_queue_latest.csv`

Cette queue ne lance aucun backtest. Elle lit les CSV discovery V2, deduplique
les strategies par cible concrete, puis indique l'action utile: validation
mark/index, validation WS, revue microstructure, forward strict ou rejet.

### 0 ter. Radar cryptos volatiles

Avant de figer une watchlist crypto, generer la liste des paires Aster qui
bougent vraiment:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_volatile_crypto_discovery
```

Sorties:

- `docs/core-equity-aster-volatile-crypto-discovery.html`
- `backend/services/onchain/aster/aster_volatile_crypto_discovery_latest.json`
- `backend/services/onchain/aster/aster_volatile_crypto_discovery_latest.csv`

Ce radar utilise seulement les endpoints publics Aster. Il classe les cryptos
par mouvement 24h, volume, nombre de trades, spread, premium mark/index et
funding. Une crypto volatile n'est pas une strategie valide: elle devient une
cible de discovery, puis doit passer la queue de validation.

### 0 quater. Recommandations strategie par actif

Pour savoir quelle strategie tester selon le type d'actif:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_asset_strategy_recommendations
```

Sorties:

- `docs/core-equity-aster-asset-strategy-recommendations.html`
- `backend/services/onchain/aster/aster_asset_strategy_recommendations_latest.json`
- `backend/services/onchain/aster/aster_asset_strategy_recommendations_latest.csv`

Ce rapport relie les resultats de backtest, la volatilite, les memecoins, les
stocks synthetiques et les commodities. Il expose notamment
`memecoin_symbols_csv`, `volatile_runner_symbols_csv`, la meilleure strategie
observee par symbole et la prochaine famille de strategie a tester.

### 0 quinquies. Audit des fichiers de travail

Pour comprendre le dossier sans casser les chemins fixes:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_workspace_file_audit
```

Sorties:

- `docs/core-equity-aster-workspace-file-audit.html`
- `backend/services/onchain/aster/aster_workspace_file_audit_latest.json`
- `backend/services/onchain/aster/aster_workspace_file_audit_latest.csv`

Regle importante: les artefacts `*_latest.json`, les CSV de progress et les
caches restent dans le dossier racine tant que les runners les lisent en chemin
fixe. On les audite et on les documente, mais on ne les deplace pas sans
modifier explicitement les chemins dans le code.

### Archivage controle des artefacts legacy

Preview read-only:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_workspace_artifact_archiver
```

Archivage confirme:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_workspace_artifact_archiver --confirm CONFIRM_ASTER_ARCHIVE_LEGACY_ARTIFACTS
```

L'archiver deplace uniquement les artefacts smoke, snapshots legacy et anciens
moniteurs vers `archive/research_artifacts/`. Les tags actifs comme
`core_prod_mark_bbo`, `aster_v2_prod`, `macro_equity_prod_mark_bbo`,
`priority_watchlist_prod`, `focused_candidate_validation` et
`memecoin_volatile_strategy_search` sont explicitement proteges.

### 1. Cockpit principal

Avant de lancer de nouveaux backtests, generer le rapport de verite du ledger:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_strategy_truth_report
```

Sorties:

- `docs/core-equity-aster-strategy-truth-report.html`
- `backend/services/onchain/aster/aster_strategy_truth_report_latest.json`

Ce rapport est volontairement brutal: il classe chaque `event_type` avec PnL
realise, latent ouvert, total realise+latent, win-rate, profit factor et
verdict. Il ne suffit plus seul a promouvoir une lane: il doit etre croise avec
`aster_promotion_truth_report.py`, qui valide par lane exacte
`symbol + interval + side`.

Decision operationnelle historique, remplacee par la queue du 2026-06-02:

- source de decision stricte: `aster_promotion_truth_report.py`;
- ranking robuste des anciennes lanes: `aster_lane_promotion_scoring.py`;
- ancienne lane promouvable en strict forward-only: `LABUSDT|5h|long`;
- lanes `WATCH`: notamment `LABUSDT|3h|long` et `INTCUSDT|30m|long`, a garder
  comme observation, pas comme preuve de trading reel;
- tout runner legacy (`monitor_multi_strategy.py`, `monitor_optimized_longs.py`,
  `monitor_shorts.py`) doit etre lu via son `event_type` et ne doit pas
  surclasser le rapport strict par lane.

Mise a jour importante: depuis le snapshot large et les validations du
2026-06-02, la decision rapide doit partir de `LABUSDT long 30m`,
`HYPEUSDT long 15m/30m/3h/5h`, et de la queue
`aster_candidate_validation_queue_latest.csv`. `LABUSDT 5h` reste historique,
mais ne doit plus surponderer la lane `30m` sans nouvelle confirmation
mark/index + microstructure.

Le piege principal a eviter: ne pas lire uniquement `net_pnl_usd`. Une strategie
peut paraitre rentable en realise mais etre mauvaise si son latent ouvert
degrade le total. Le cockpit verite classe donc sur `net + latent`, win-rate,
profit factor et risque ouvert.

Runner legacy a utiliser seulement si on veut continuer l'historique INJ/TIA,
sans le considerer comme lane promue stricte:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.monitor_multi_strategy `
  --strategies inj_tia_regime_filtered `
  --run-forever `
  --sleep-seconds 300 `
  --forward-window-trades 1000 `
  --persist
```

Runner legacy optimise a garder si on veut continuer la ligne
`forward_optimized_long_stateful`:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.monitor_optimized_longs `
  --symbols INJUSDT,NEARUSDT,TIAUSDT `
  --run-forever `
  --sleep-seconds 300 `
  --forward-window-trades 1000 `
  --persist
```

Runner strict actuellement prioritaire pour les lanes promotion truth:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report `
  --strict-forward-cycle `
  --run-forever `
  --sleep-seconds 300 `
  --forward-window-trades 1000 `
  --persist
```

Lecture: ce runner ne trade pas reellement. Il ecrit uniquement dans le ledger
paper-trading et garde les event types stricts separes.

Generer d'abord le rapport dual-track pour garder les anciens champions et les nouveaux candidats dans la meme carte:

```powershell
Set-Location D:\trading-agent\backend
python -c "from services.onchain.aster.aster_dual_track_research_report import get_aster_dual_track_research_report_preview; print(get_aster_dual_track_research_report_preview(write_snapshot=True)['summary'])"
```

Regenerer le rapport consolide apres quelques heures de runners:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_research_consolidated_report
```

Sorties:

- `docs/core-equity-aster-research-consolidated-report.html`
- `backend/services/onchain/aster/aster_research_consolidated_report_latest.json`

Ce rapport est le cockpit principal. Il lit les CSV existants et classe les
lanes sans relancer de trading. Il contient aussi la section dual-track:

- exploitation: ne pas abandonner `LABUSDT`, `INTCUSDT`, `CRCLUSDT`, `MSFTUSDT`, `INJUSDT`;
- exploration: tester les symboles de la watchlist priorisee sans remplacer trop vite les champions.

Generer ensuite la shortlist promotion-ready:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report
```

Sorties:

- `docs/core-equity-aster-promotion-ready-lanes.html`
- `backend/services/onchain/aster/aster_promotion_ready_lanes_latest.json`

Ce rapport prend les meilleures lanes du cockpit, lance le validateur
microstructure public, puis separe `PROMOTION_READY`, `WATCH_MORE_DATA` et
`BLOCKED_MICROSTRUCTURE`.

Tester un cycle forward des seules lanes promotion-ready, sans ecriture:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report `
  --forward-cycle `
  --cycles 1 `
  --forward-window-trades 1000
```

Runner AFK paper ledger, si on veut persister le track record virtuel:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report `
  --forward-cycle `
  --run-forever `
  --sleep-seconds 300 `
  --forward-window-trades 1000 `
  --persist
```

Ce mode ne cree aucun trade reel. `--persist` ecrit uniquement dans le ledger
paper-trading avec le confirm interne existant.

Variante stricte recommandee apres post-mortem:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report `
  --strict-forward-cycle `
  --run-forever `
  --sleep-seconds 300 `
  --forward-window-trades 1000 `
  --persist
```

Sorties:

- `paper_trading_strict_promotion_ready_forward_monitor.csv`
- `paper_trading_strict_promotion_ready_forward_heartbeat.json`

Cette variante garde les memes lanes promotion-ready mais refuse les entrees
dont la fenetre d'entree est trop mince: moins de 50 trades, moins de 20k USD
de volume quote, ou gap maximal superieur a 30 secondes. Elle utilise un
`event_type` separe `forward_strict_promotion_ready_long_*` pour ne pas melanger
les resultats avec l'ancien monitor.

Diagnostic anti-overfit des entrees:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report `
  --entry-micro-diagnostic `
  --forward-window-trades 1000
```

Sortie:

- `backend/services/onchain/aster/aster_entry_microstructure_diagnostic_latest.json`

Ce diagnostic rejoue les lanes promotion-ready, extrait les timestamps d'entree,
puis verifie le flux `aggTrades` autour de chaque entree. Limite connue:
l'API publique utilisee ici ne donne pas de snapshot de carnet historique, donc
ce test valide la liquidite trade-tape au moment d'entree, pas le spread exact
historique.

Post-mortem strict du ledger promotion-ready:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report `
  --strict-ledger-postmortem `
  --limit-pairs 60
```

Sortie:

- `backend/services/onchain/aster/aster_promotion_ready_strict_ledger_postmortem_latest.json`

Lecture actuelle: les filtres stricts reduisent les pertes mais ne rendent pas
encore la lane positive. Sur le dernier post-mortem promotion-ready, 30 sorties
ont ete verifiees; le PnL passe d'environ `-5.37 USD` a `-3.67 USD` en excluant
les entrees trop minces. Les blockers dominants sont:

- `entry_tape_quote_volume_lt_20k`
- `entry_tape_too_few_trades_lt_50`
- `entry_tape_gap_gt_30s`

Conclusion operationnelle: le probleme n'est plus seulement le signal; c'est la
qualite d'entree microstructure. Ne pas promouvoir une lane forward tant que ce
post-mortem ne montre pas un PnL strict positif ou une amelioration forte et
stable.

Generer ensuite la feuille d'actions:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_research_action_report
```

Sorties:

- `docs/aster-research-actions.md`
- `backend/services/onchain/aster/aster_research_actions_latest.json`

Cette feuille transforme le cockpit en decisions simples:

- `PROMOTE_TO_FORWARD`
- `KEEP_RUNNING_WATCH`
- `NEEDS_REALITY_CHECK`
- `KEEP_RUNNING`
- `EXPLORE_MORE`
- `STOP_OR_DEPRIORITIZE`

Valider les anciens champions avec les nouveaux garde-fous:

```powershell
Set-Location D:\trading-agent\backend
python -c "from services.onchain.aster.aster_exploitation_champions_validator import get_aster_exploitation_champions_validation_preview; r=get_aster_exploitation_champions_validation_preview(max_champions=8); print(r['summary'])"
python -m services.onchain.aster.aster_research_consolidated_report
```

Sorties:

- `aster_exploitation_champions_latest.json`
- `paper_trading_exploitation_champions_v2.csv`
- section `Champions historiques revalides` dans le cockpit HTML.

### 2. Runner champions core

Continue de suivre les meilleurs actifs connus:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_strategy_discovery `
  --symbol-preset core `
  --output-tag core_champions `
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

### 3. Runner exploration core

Cherche des challengers sans laisser LAB/INJ dominer tout:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_strategy_discovery `
  --symbol-preset core `
  --output-tag core_explore `
  --exclude-symbols LABUSDT,INJUSDT,BOMEUSDT,TIAUSDT `
  --search-mode exploration `
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

### 4. Runner macro / commodities

Surveille XAU, oil, CRCL et autres actifs macro:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_strategy_discovery `
  --symbol-preset macro `
  --output-tag macro `
  --groups both `
  --run-forever `
  --sleep-seconds 900 `
  --lookback-days 60 `
  --windows 3 `
  --min-closed-trades 6 `
  --top-n-per-batch 10 `
  --top-n-global 50 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

### 5. Runner watchlist Aster priorisee

Teste les symboles choisis par `aster_priority_watchlist_latest.json`, donc par l'univers public Aster + qualite WS + volume/spread/funding/premium.

Plan sans backtest:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_priority_watchlist `
  --plan-only `
  --max-symbols 12 `
  --min-priority-score 35
```

Runner H24:

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

Ce runner ne remplace pas les champions historiques. Il alimente la piste exploration du rapport dual-track.

### 6. Runner Aster v2 unifie

Orchestre automatiquement:

- champions revalides (`LABUSDT`, `INJUSDT`, `INTCUSDT`);
- review utile (`CRCLUSDT`, `MSFTUSDT` selon le dernier snapshot);
- exploration issue de la priority watchlist.

Plan sans backtest:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 --plan-only
```

Runner H24:

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

### 7. Runner equities

Surveille actions tokenisees Aster:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_strategy_discovery `
  --symbol-preset equities `
  --output-tag equities `
  --groups both `
  --run-forever `
  --sleep-seconds 1200 `
  --lookback-days 60 `
  --windows 3 `
  --min-closed-trades 6 `
  --top-n-per-batch 10 `
  --top-n-global 50 `
  --batch-size 3 `
  --leverage-values 1,2,3,5,10,20
```

### 8. Runner reality-checked

File de promotion qualite: garde seulement les lanes qui passent le controle
volume/spread/mark-index/funding/index references.

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_reality_checked `
  --symbol-preset core `
  --output-tag core_reality `
  --groups both `
  --run-forever `
  --sleep-seconds 1200 `
  --lookback-days 60 `
  --windows 3 `
  --min-closed-trades 8 `
  --top-n-per-batch 10 `
  --top-n-global 30 `
  --batch-size 5 `
  --leverage-values 1,2,3,5,10,20 `
  --min-quality-score 75 `
  --allowed-quality-verdicts backtest_quality_ok
```

## Modules principaux

### Adapters / donnees externes

- `aster_mcp_market_data_adapter.py`
  - public Aster Futures V3 read-only;
  - normalise ticker, depth, klines, mark/index price, premium, funding;
  - expose le reality check perps;
  - aucun credential, aucun ordre.

- `aster_mcp_capability_audit.py`
  - matrice locale des capacites Aster/MCP;
  - separe public REST deja integre, WebSocket public a ajouter, USER_DATA bloque et trade/transfer interdit;
  - produit `docs/aster-mcp-capability-audit.md`;
  - ne fait aucun appel reseau, aucun credential, aucun ordre.

- `aster_mark_index_replay_filter.py`
  - filtre read-only de validation perps;
  - compare `lastPriceKlines`, `markPriceKlines` et `indexPriceKlines`;
  - utilise le p95 de divergence pour eviter qu'une seule meche invalide toute la lane;
  - produit `aster_mark_index_replay_filter_latest.json`;
  - aucun credential, aucun ordre.

- `aster_microstructure_replay_validator.py`
  - filtre read-only de fillability pour champions backtest;
  - lit `aggTrades` puis fallback `historicalTrades`, plus `depth`;
  - mesure nombre de trades, volume quote reel, gaps, spread, profondeur et slippage simule;
  - verdicts: `microstructure_ok`, `thin_liquidity`, `gap_risk`, `not_enough_trades`;
  - produit `aster_microstructure_replay_validator_latest.json`;
  - aucun credential, aucun ordre, aucun write DB.

- `dexscreener_enrichment_layer.py`
  - pont DexScreener read-only pour candidats locaux;
  - ancien axe de recherche, encore utile en reference.

- `dexscreener_first_discovery_layer.py`
  - decouverte externe-first DexScreener;
  - utile historiquement, pas runner prioritaire actuellement.

- `scrapling_label_enrichment_batch.py`
  - lecture locale de snapshots normalises uniquement;
  - aucun scraping live.

### Backtests / runners

- `backtest_strategy_discovery.py`
  - runner principal multi-symboles / multi-timeframes;
  - produit les CSV V2 tagges;
  - supporte `--symbol-preset`, `--output-tag`, `--exclude-symbols`, `--search-mode`.

- `backtest_reality_checked.py`
  - runner de promotion qualite;
  - lance discovery puis filtre avec Aster reality check.

- `backtest_champion_lanes.py`
  - ancien runner ponctuel focalise champions;
  - garder comme reference, preferer `backtest_strategy_discovery.py`.

### Paper trading / forward

- `aster_paper_trading_sandbox.py`
  - gros module central actuel;
  - contient ledger, replay, stateful monitors, optimisation, forward;
  - fragile car volumineux, mais stable pour l'instant;
  - ne pas refactorer pendant que les runners tournent.

- `monitor_multi_strategy.py`
  - monitor stateful multi-strategy;
  - utile pour forward paper trading, pas pour discovery brute.

- `monitor_optimized_longs.py`
  - monitor de lanes longues optimisees;
  - utile en forward, mais attention aux resultats repetitifs si pas assez de nouveaux trades.

- `monitor_shorts.py`
  - ancien axe short/fade;
  - garde comme reference, pas prioritaire aujourd'hui.

### Rapports

- `aster_research_consolidated_report.py`
  - cockpit principal;
  - lit les CSV/JSON et genere HTML/JSON;
  - a lancer manuellement apres plusieurs cycles.

- `aster_research_action_report.py`
  - lit le JSON consolide;
  - produit `docs/aster-research-actions.md`;
  - dedupe les lanes par action/symbol/side/timeframe pour eviter les repetitions;
  - ne relance aucun backtest.

- `aster_today_summary_2026_05_31.json`
  - snapshot du jour;
  - reference historique, pas un runner.

### Fondation agent

- `aster_agent_foundation.py`
  - phase 1/2: API explorer, wallet preview, order book anomaly;
  - read-only.

- `aster_agent_decision_engine.py`
  - state machine dry-run;
  - pas de trade reel.

## Artefacts importants

### A lire en priorite

- `docs/core-equity-aster-documentation-hub.html`
- `docs/core-equity-aster-current-state.html`
- `docs/core-equity-aster-strategy-registry.html`
- `docs/core-equity-aster-promotion-truth-report.html`
- `docs/core-equity-aster-lane-promotion-scoring.html`
- `docs/core-equity-aster-code-map.html`
- `docs/aster-production-runbook.md`
- `docs/core-equity-aster-research-consolidated-report.html`
- `docs/core-equity-aster-promotion-ready-lanes.html`
- `docs/core-equity-aster-strategy-truth-report.html`
- `docs/core-equity-aster-research-report.html` (archive historique)
- `docs/core-equity-aster-research-archive.md`
- `docs/aster-mcp-setup-plan.md`
- `docs/aster-mcp-capability-audit.md`
- `docs/aster-official-docs-gap-audit.md`

### CSV principaux

- `paper_trading_strategy_discovery_core_champions_v2.csv`
- `paper_trading_strategy_discovery_core_v2.csv`
- `paper_trading_strategy_discovery_macro_v2.csv`
- `paper_trading_strategy_discovery_equities_v2.csv`
- `paper_trading_strategy_discovery_core_exchangeinfo_v2.csv`
- `paper_trading_strategy_discovery_macro_equity_exchangeinfo_v2.csv`
- `paper_trading_reality_checked_backtest.csv`

### ExchangeInfo reality check

Les runs tagges `*_exchangeinfo` ajoutent les contraintes publiques Aster
directement dans les CSV v2: statut du symbole, `triggerProtect`,
`marketTakeBound`, filtres prix/lot/minNotional et verdict
`exchange_filter_verdict`.

Diagnostic local, sans API et sans trade:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.research.exchangeinfo_run_status
```

Dernier etat utile du 2026-05-31:

- `core_exchangeinfo`: CSV pret, meilleur candidat `LABUSDT 5h`, ROI ~16.13%, WR ~70.8%, PF ~3.61, verdict `warning`.
- `macro_equity_exchangeinfo`: CSV pret, meilleur candidat `INTCUSDT 30m`, ROI ~7.79%, WR ~90%, PF ~12.24, verdict `warning`.
- `equities_explore_exchangeinfo` et `aster_v2_exchangeinfo`: en attente de fin de cycle au dernier controle.

### Archive locale

- `archive/research_artifacts/`
  - anciens CSV `.legacy_*`;
  - artefacts de smoke test;
  - donnees conservees pour trace, mais non utilisees par les runners H24.

### Heartbeats

- `paper_trading_strategy_discovery_heartbeat.json`
- `paper_trading_reality_checked_heartbeat.json`
- `paper_trading_multi_strategy_stateful_heartbeat.json`
- `paper_trading_optimized_long_stateful_heartbeat.json`

### Rapports MCP / qualite marche

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_mcp_capability_audit
```

Sorties:

- `docs/aster-mcp-capability-audit.md`;
- `backend/services/onchain/aster/aster_mcp_capability_audit_latest.json`.

Lecture rapide:

- priorite 1: replay mark/index public pour reduire les faux edges last-price;
- priorite 2: sampler WebSocket public read-only;
- priorite 3: remplacer le proxy funding par l'historique funding public;
- credentials `USER_DATA` uniquement apres politique read-only explicite;
- trade/transfer toujours bloque.

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_mark_index_replay_filter
```

Sortie:

- `backend/services/onchain/aster/aster_mark_index_replay_filter_latest.json`.

Dernier snapshot utile 2026-06-02:

- `HYPEUSDT 15m/30m/2h/3h/5h`: `mark_index_confirmed`;
- `LABUSDT 30m`: `mark_index_watch`, encore exploitable en recherche stricte;
- `LABUSDT 5h`: ancien champion ROI, mais a ne plus surponderer sans nouvelle confirmation mark/index;
- `PLAYUSDT 4h/5h`: `mark_index_watch`, mais microstructure fragile;
- `BOMEUSDT`: `mark_index_rejected`, a rejeter/rework.

### Validation microstructure des champions

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_microstructure_replay_validator --champions LABUSDT:30m:long,HYPEUSDT:3h:long,HYPEUSDT:5h:long,PLAYUSDT:5h:long,BOMEUSDT:2h:long
```

Sortie:

- `backend/services/onchain/aster/aster_microstructure_replay_validator_latest.json`.

Lecture rapide du smoke 2026-06-02:

- `LABUSDT 30m long`: `microstructure_ok`, environ 1000 trades observes, volume quote recent solide, spread faible;
- `HYPEUSDT 15m/30m/2h/3h/5h long`: `microstructure_ok`, volume quote eleve et spread faible;
- `PLAYUSDT 4h/5h long`: `gap_risk`, a garder en recherche uniquement;
- `BOMEUSDT 1h/2h/4h`: `not_enough_trades`, spread/slippage trop faibles pour croire le replay.

Usage: un champion ROI/PF ne doit pas etre promu s'il echoue ici, sauf si on reduit la taille de position ou si une fenetre plus liquide confirme le contraire.

### Politique RL offline de selection des lanes

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.research.aster_rl_lane_policy --top-n 120
```

Sorties:

- `backend/services/onchain/aster/aster_rl_lane_policy_latest.json`
- `backend/services/onchain/aster/aster_rl_lane_policy_latest.csv`
- `docs/core-equity-aster-rl-lane-policy.html`

Role:

- classer les lanes deja backtestees avec une politique offline de type contextual-bandit;
- clarifier que ce n'est pas encore un modele IA neuronal: pas de `torch`, pas de PPO/SAC, pas de poids entraines;
- rester sans dependance lourde (`gymnasium`, `stable-baselines3`, `torch` non installes);
- ne lire que les CSV/JSON locaux;
- combiner ROI/PF/WR avec les garde-fous mark/index, microstructure, OOS et reality pack;
- rejeter les beaux ROI qui ne passent pas la realite marche;
- afficher `validation_freshness_verdict` pour ne pas promouvoir une lane avec validateurs stale.
- separer exploitation (`top_recommendations`) et couverture multi-actifs (`balanced_portfolio_recommendations`, `exploration_queue`).

Dernier smoke 2026-06-04:

- `6046` lanes lues;
- `207` recommandations uniques apres dedupe `symbol + interval + side`;
- top symbole: `HYPEUSDT`;
- top lanes propres: `HYPEUSDT 3h long`, `HYPEUSDT 5h long`, `HYPEUSDT 15m long`;
- statut top: `validation_passed_clean`, `mark_index_confirmed`, `microstructure_ok`;
- `LABUSDT` reste un historique important, mais la politique ne le promeut pas tant que mark/index et microstructure stricte ne confirment pas proprement.
- Si les derniers CSV discovery sont plus recents que `mark_index`, `microstructure` ou `reality_pack`, relancer les validateurs avant promotion forward.

## Etat des pistes

### Pistes prometteuses

- `LABUSDT long 30m`: meilleur ROI papier actuel, mais statut `mark_index_watch`;
- `HYPEUSDT long 3h/5h/15m`: ROI plus faible, mais meilleure qualite technique (`mark_index_confirmed`, `microstructure_ok`);
- `LABUSDT` autres timeframes: a garder dans l'historique, mais ne pas les laisser remplacer la lane 30m sans nouvelle validation.

### Pistes a filtrer avec prudence

- `PLAYUSDT`: ROI papier interessant, mais `gap_risk`;
- equities et commodities: resultats parfois beaux mais volume souvent mince;
- `BOMEUSDT`: rejete/rework tant que mark/index et microstructure restent mauvais;
- leviers x10/x20: souvent rejetes par proxy liquidation/drawdown;
- lanes avec peu de trades fermes: ne pas promouvoir.

### Pistes archivees / non prioritaires

- prediction CEX listing par flux wallets;
- pump DEX via behavioral score seul;
- long Aster order-flow seul;
- short/fade non-stateful sans validation forward suffisante.

## Regles de decision

Une lane devient interessante seulement si:

- ROI realise positif sur 60 jours;
- PF > 1.3 apres frais/funding/slippage;
- WR raisonnable, pas juste un artefact de faible echantillon;
- au moins 8 trades fermes en backtest;
- split train/validation positif, surtout sur la fenetre recente;
- drawdown supportable;
- latent ouvert separe et non utilise pour gonfler le score;
- identite complete de lane conservee;
- reality check `ok` ou `watch` avec raison acceptable;
- confirmation forward paper si on veut aller plus loin.

Ne jamais promouvoir une lane uniquement parce que le ROI est eleve ou parce
qu'elle apparait plusieurs fois comme "best" dans un terminal.

## Dette technique connue

- `aster_paper_trading_sandbox.py` est trop gros.
- Les CSV grossissent vite.
- Certains rapports HTML ont ete reconstruits plusieurs fois; l'archive markdown garde l'historique.
- Les scripts sont encore a plat dans le dossier Aster.

Plan de rangement futur, a faire seulement quand les runners ne tournent pas:

- `adapters/`: Aster MCP/API, DexScreener, Scrapling.
- `runners/`: discovery, reality checked, monitors.
- `reports/`: consolidated report, summaries.
- `core/`: scoring/replay/ledger commun.
- `legacy/`: anciens runners non prioritaires.

Pour l'instant, ne pas deplacer les fichiers: stabilite > rangement parfait.
