# Aster working map

Date: 2026-06-02

## Mise a jour critique du soir - lecture post-correctifs

Les docs ne sont pas cassees, mais les anciens chiffres Aster sont maintenant
des resultats **pre-correctifs**. Ils restent utiles comme historique de
recherche, mais ne doivent plus etre lus comme preuves de rentabilite.

Correctifs appliques avant de reprendre les decisions:

- PnL separe entre realise et latent: `pnl_total_usd` ne doit plus inclure une
  position encore ouverte.
- Cout perps plus realiste: fees/funding estimes sur l'exposition notionnelle
  avec levier, pas seulement sur la marge.
- Identite de lane stricte: `strategy_profile_key`, `score_window_size`,
  `output_tag`, side, interval, reference prix et modele d'execution doivent
  rester attaches au resultat.
- Intervalles synthetiques `3h/5h` corriges par timestamp, pas par paquets de
  bougies arbitraires.
- Mode `mark_price` rendu strict: pas de fallback Spot silencieux pour valider
  une lane Futures.
- Backtests V2 enrichis avec split train/validation et colonnes
  `out_of_sample_status`, `train_*`, `validation_*`.

Regle actuelle: une lane n'est candidate decisionnelle que si elle est regeneree
apres ces correctifs et qu'elle garde une validation positive sur la fenetre la
plus recente. Les anciens ROI/PF/WR restent dans l'archive, mais ne suffisent
plus pour promouvoir une strategie.

## Etat propre actuel

La suite Aster est maintenant separee en couches:

1. Donnees publiques Aster
2. Backtests / replay
3. Paper trading forward
4. Rapports et decisions
5. Execution reelle: bloquee volontairement

## Etat decisionnel actuel

La decision du 2026-06-02 vient du croisement:

- backtests V2/progress;
- dernier filtre `aster_mark_index_replay_filter_latest.json`;
- dernier validateur `aster_microstructure_replay_validator_latest.json`;
- queue `aster_candidate_validation_queue_latest.json`;
- rapports promotion/truth.

Lecture actuelle apres queue reality pack du soir:

- `LABUSDT long 30m`: meilleure piste papier, ROI jusqu'a environ `48.8%`,
  WR environ `67.5%`, PF environ `3.02`; microstructure OK, et le dernier
  pack top-queue retourne `mark_index_watch`, pas rejet. LAB reste une piste
  serieuse en watch: assez forte pour etre surveillee, pas assez propre pour
  etre promue sans forward/replay strict.
- `HYPEUSDT long 3h/5h/15m`: ROI plus faible, mais beaucoup plus propre
  techniquement: `mark_index_confirmed`, `microstructure_ok`, WS ready.
  Revue exchangeInfo encore requise a cause de `tight_market_take_bound`.
- `HUSDT long 4h`: ROI papier environ `18.1%`, WR environ `91.7%`, PF environ
  `22.8`; `mark_index_watch`, mais le dernier pack signale aussi une
  microstructure faible (`thin_liquidity` / wide spread). A retravailler avant
  forward confiance.
- `PLAYUSDT 4h/5h`: ROI papier interessant, mais `gap_risk`; garder en
  recherche uniquement.
- `BOMEUSDT`: rejete/rework pour l'instant: `mark_index_rejected` et
  `not_enough_trades`.

Regle: ne pas relancer une lane parce que le ROI brut est haut. Elle doit
passer au minimum `mark/index`, `microstructure`, `exchangeInfo` et la queue
de validation.

Nouveau module utile:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_queue_reality_pack_validator --top-n 12 --lookback-days 30 --write-snapshot
```

Ce module prend les top lanes de la queue et rafraichit mark/index +
microstructure ensemble. Dernier resultat utile: `3` clean (`HYPEUSDT`) +
`4` watch (`LABUSDT 30m/2h/3h/5h`) + `5` rework/rejet. Correction importante:
un bug d'agregation des intervalles synthetiques `3h/5h` avait fait paraitre
LAB plus mauvais qu'il ne l'etait; le verdict actuel est `watch`, pas
`rejected`.

## Decision actuelle: identifier avant de lancer

La suite Aster a maintenant une couche de registry. Avant de relancer un runner,
on doit savoir exactement quel fichier Python correspond a quelle famille de
strategie, quels artefacts il produit et si le script est actif, exploration,
controle, legacy ou archive.

Registry:

`docs/core-equity-aster-strategy-registry.html`

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_strategy_registry
```

Regle simple:

- un backtest n'est pas une strategie s'il n'a pas `output_tag + symbol +
  interval + side + trigger_reference + execution_model + leverage`;
- un forward monitor doit etre lu via `event_type` ou `strategy_id`;
- une lane promue doit etre validee par exact-lane: `symbol + interval + side`.

## Decision historique: promotion stricte

Le dernier truth report du ledger reste utile, mais il ne suffit plus seul. Ce
bloc documente une decision stricte plus ancienne; elle est conservee pour ne
pas perdre le travail, mais elle est remplacee par la queue du 2026-06-02 pour
les choix actuels.

- `aster_strategy_truth_report.py`: verite par `event_type`;
- `aster_promotion_truth_report.py`: verite stricte par lane exacte;
- `aster_lane_promotion_scoring.py`: ranking robuste avec blockers.

Etat historique:

- `LABUSDT|5h|long`: ancien `PROMOTE_FORWARD_ONLY`;
- `LABUSDT|3h|long`: `WATCH_STRICT_FORWARD`;
- `INTCUSDT|30m|long`: `WATCH` dans le scoring, pas promote;
- `LABUSDT` 15m/30m/1h: rejetes par la couche stricte actuelle;
- `MSFTUSDT|4h|long`: discovered/observation, pas promote.

Conclusion mise a jour: on continue a explorer, mais on ne laisse pas un ancien
runner legacy, un ancien `PROMOTE`, ou un ROI CSV brut remplacer la decision de
la queue 2026-06-02. La lecture rapide actuelle est `LABUSDT 30m` pour ROI
papier et `HYPEUSDT` pour proprete technique.

## Couche data sources

Dossier:

`backend/services/onchain/aster/data_sources/`

Modules:

- `source_validation.py`: valide les endpoints REST publics.
- `public_universe_snapshot.py`: construit l'univers Aster all-symbol.
- `ws_market_stream_validation.py`: valide les streams WebSocket publics.
- `ws_forward_monitor_preview.py`: compare WS vs REST sur un symbole.
- `ws_symbol_quality_report.py`: score les symboles pour forward paper trading WS.

Les wrappers legacy restent en place pour ne rien casser.

## Cockpit principal

Rapport:

`docs/core-equity-aster-research-consolidated-report.html`

Carte code / runbook:

`docs/core-equity-aster-code-map.html`

Registry scripts / strategies:

`docs/core-equity-aster-strategy-registry.html`

Shortlist finale:

`docs/core-equity-aster-promotion-ready-lanes.html`

Il contient maintenant:

- Top lanes de backtest;
- Mark/index confirme/watch/rejete;
- Reality check;
- Runners / monitors;
- Validation des sources Aster;
- Univers public Aster;
- Qualite WebSocket forward.
- Watchlist priorisee.
- Double piste exploitation/exploration pour ne pas oublier les anciens backtests.

Regle documentaire:

- le cockpit consolide sert a lire les resultats;
- la shortlist promotion-ready sert a decider quoi tester en forward;
- la carte code sert a comprendre les fichiers, les commandes et les garde-fous;
- l'archive markdown garde les essais non concluants et les raisons de pivot;
- on evite de recreer un HTML pour chaque idee afin de ne pas perdre le fil.

## Snapshots importants

- `aster_data_source_validation_latest.json`: endpoints REST publics valides.
- `aster_public_universe_snapshot_latest.json`: universe Aster complet.
- `aster_ws_symbol_quality_report_latest.json`: qualite WS par symbole.
- `aster_priority_watchlist_latest.json`: symboles priorises pour les prochains tests.
- `aster_dual_track_research_report_latest.json`: piste exploitation, piste exploration, historique preserve.
- `aster_exploitation_champions_latest.json`: anciens champions revalides par quality/perps/mark-index.
- `aster_mark_index_replay_filter_latest.json`: filtre mark/index par symbole/timeframe.
- `aster_research_consolidated_report_latest.json`: cockpit JSON complet.
- `aster_exchangeinfo_run_status_latest.json`: etat local des runs exchangeInfo.
- `aster_microstructure_replay_validator_latest.json`: validation fillability des champions via depth + trades publics.
- `aster_promotion_ready_lanes_latest.json`: lanes candidates apres filtre microstructure.
- `aster_strategy_registry_latest.json`: registre des scripts/familles/statuts.
- `aster_promotion_truth_report_latest.json`: decision stricte par lane.
- `aster_lane_promotion_scoring_latest.json`: ranking promote/watch/discovered/rejected.
- `aster_candidate_validation_queue_latest.json`: prochaine action utile par lane, avec overlays mark/index et microstructure.
- `aster_volatile_crypto_discovery_latest.json`: radar cryptos volatiles public Aster.
- `aster_asset_strategy_recommendations_latest.json`: strategie recommandee par type d'actif.

Note importante: `aster_public_universe_snapshot_latest.json` contient maintenant aussi `all_research_universe` (`448` symboles tradables/analysables) et `all_rows` (`603` symboles vus dans les endpoints publics). Cela evite d'oublier les commodities, equities ou crypto hors top volume.

## Ce qui est maintenant mieux qu'avant

Avant:

- on tournait trop souvent sur les memes symboles;
- on ne savait pas toujours si les donnees Aster etaient fiables;
- les resultats de backtest etaient separes des diagnostics data.

Maintenant:

- on connait l'univers Aster complet: `603` symboles, `448` tradables;
- on sait quels endpoints REST/WS sont valides;
- le cockpit affiche la qualite data directement;
- on peut choisir les prochains symbols a tester avec une base plus propre.

## ExchangeInfo public integre aux backtests

Depuis le 2026-05-31, les nouveaux runs tagges `*_exchangeinfo` enrichissent
les resultats de `backtest_strategy_discovery.py` avec les contraintes publiques
Aster Futures:

- statut officiel du symbole;
- `triggerProtect`;
- `marketTakeBound`;
- filtres prix, lots, market lots, minNotional;
- verdict `exchange_filter_verdict` avec warnings/blockers.

Diagnostic local:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.research.exchangeinfo_run_status
```

Dernier etat historique observe:

- `core_exchangeinfo`: ancien meilleur candidat `LABUSDT 5h`, ROI ~16.13%,
  WR ~70.8%, PF ~3.61, verdict `warning`;
- `macro_equity_exchangeinfo`: ancien meilleur candidat `INTCUSDT 30m`,
  ROI ~7.79%, WR ~90%, PF ~12.24, verdict `warning`;
- `equities_explore_exchangeinfo` et `aster_v2_exchangeinfo`: encore en cycle.

Mise a jour 2026-06-02: ces anciens meilleurs cas ne suffisent plus seuls.
La decision prioritaire doit passer par `aster_candidate_validation_queue`,
car elle applique aussi les overlays mark/index et microstructure les plus
recents.

## Validation microstructure des champions

Nouvelle couche ajoutee le 2026-05-31:

`backend/services/onchain/aster/aster_microstructure_replay_validator.py`

Objectif: verifier qu'une lane profitable sur CSV aurait probablement pu etre
executee en conditions Aster reelles. Le validateur est read-only et utilise
uniquement les endpoints publics:

- `GET /fapi/v3/aggTrades`;
- fallback `GET /fapi/v3/historicalTrades` si disponible;
- `GET /fapi/v3/depth`.

Mesures:

- nombre de trades reels dans la fenetre;
- volume quote observe;
- gaps entre trades;
- spread best bid/ask;
- profondeur top10;
- slippage simule pour une taille par defaut de 100 USDT.

Verdicts:

- `microstructure_ok`: carnet et flux suffisants;
- `thin_liquidity`: volume, profondeur, spread ou slippage insuffisant;
- `gap_risk`: trop de trous temporels entre trades;
- `not_enough_trades`: echantillon trop petit pour croire le backtest.

Dernier smoke utile:

- `LABUSDT 30m long`: `microstructure_ok`;
- `HYPEUSDT 15m/30m/2h/3h/5h long`: `microstructure_ok`;
- `PLAYUSDT 4h/5h long`: `gap_risk`;
- `BOMEUSDT 1h/2h/4h`: `not_enough_trades` + spread/slippage trop fragiles.

Conclusion pratique mise a jour: `LABUSDT 30m` reste la lane ROI la plus
credible, mais `HYPEUSDT` est plus sain techniquement. Les belles lanes
equities/macro doivent passer ce filtre avant toute promotion.

## Demo/testnet Aster

Statut du 2026-06-01:

- agent wallet testnet dedie cree et autorise depuis Metamask;
- signature EIP-712 validee cote backend;
- balance testnet lue en read-only (`BTC`, `ASTER`, `USDT`, `AFEE`);
- aucun ordre, aucun wallet trade, aucun write DB.

Endpoints:

- `/api/onchain/rpc/aster-demo-testnet-readiness-preview`;
- `/api/onchain/rpc/aster-demo-order-intent-validator-preview`.

Verdict important: le testnet ne liste pas les champions qui nous interessent
actuellement (`LABUSDT`, `INJUSDT`, `TIAUSDT`, `INTCUSDT`). Il est donc utile
pour valider la signature, les tailles minimales, les filtres d'ordre et les
garde-fous, mais pas pour prouver la rentabilite des lanes championnes.

Smoke ordre fictif:

- `BTCUSDT` 50 USDT: bloque par quantite/min notional;
- `BTCUSDT` 100 USDT et plus: intention d'ordre valide;
- champions actuels: bloques car absents du testnet.

Decision: ne pas perdre de temps a forcer le testnet sur les champions absents.
Continuer la selection strategique sur mainnet public read-only + microstructure,
et garder le testnet comme banc de validation d'execution generique.

## Shortlist promotion-ready

Module:

`backend/services/onchain/aster/aster_promotion_ready_lanes_report.py`

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report
```

Le rapport prend les top lanes du cockpit consolide, dedupe par
`symbol/interval/side`, puis appelle le validateur microstructure.

Dernier resultat observe:

- `PROMOTION_READY`: 2 lanes;
- `WATCH_MORE_DATA`: 3 lanes;
- `BLOCKED_MICROSTRUCTURE`: 2 lanes.

Les deux lanes promotion-ready sont:

- `LABUSDT long 5h`: ROI ~16.20%, PF ~7.33, WR ~76.5%, microstructure OK;
- `LABUSDT long 3h`: ROI ~14.67%, PF ~10.72, WR ~81.8%, microstructure OK.

Les lanes `INTCUSDT 30m` et `MSFTUSDT 4h` restent bloquees malgre de beaux
ratios statistiques, car le flux recent contient trop peu de trades reels.

Le meme module sert maintenant aussi de forward monitor dedie aux seules lanes
`PROMOTION_READY`.

Cycle dry-run:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report --forward-cycle --cycles 1 --forward-window-trades 1000
```

Runner AFK paper ledger:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report --forward-cycle --run-forever --sleep-seconds 300 --forward-window-trades 1000 --persist
```

Sorties:

- `paper_trading_promotion_ready_forward_monitor.csv`;
- `paper_trading_promotion_ready_forward_heartbeat.json`.

Dernier smoke dry-run: 2 lanes suivies, health `active`, aucune ecriture,
2 positions virtuelles ouvertes dans la fenetre de replay.

Post-mortem strict du ledger promotion-ready:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report --strict-ledger-postmortem --limit-pairs 60
```

Sortie:

- `aster_promotion_ready_strict_ledger_postmortem_latest.json`.

Dernier resultat: `strict_filter_reduces_damage`. Sur 30 sorties persistées,
le PnL promotion-ready passe d'environ `-5.37 USD` a `-3.67 USD` si on garde
seulement les entrees avec au moins 50 trades, 20k USD de quote volume et un
gap maximal <= 30s dans la fenetre d'entree. C'est une amelioration, mais pas
encore une validation: LAB 3h/5h reste non rentable en forward strict.

Runner strict dedie:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report --strict-forward-cycle --run-forever --sleep-seconds 300 --forward-window-trades 1000 --persist
```

Sorties:

- `paper_trading_strict_promotion_ready_forward_monitor.csv`;
- `paper_trading_strict_promotion_ready_forward_heartbeat.json`.

Ce runner ecrit avec `event_type=forward_strict_promotion_ready_long_*`, donc
les resultats stricts restent separes du monitor promotion-ready historique.

## Truth report du ledger et promotion truth

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_strategy_truth_report
```

Sorties:

- `docs/core-equity-aster-strategy-truth-report.html`;
- `backend/services/onchain/aster/aster_strategy_truth_report_latest.json`.

Role: arreter de lire seulement le PnL realise. Le rapport classe chaque
`event_type` avec PnL realise, PnL latent, total realise+latent, WR, PF et un
verdict (`PROMOTE`, `WATCH`, `RISKY_PROFIT`, `STOP_OR_REWORK`,
`INSUFFICIENT_SAMPLE`).

Commande stricte par lane:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_truth_report
```

Commande ranking robuste:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_lane_promotion_scoring
```

Dernier constat: le truth report par `event_type` peut encore afficher deux
strategies en `PROMOTE`, mais le croisement strict par lane ne garde qu'une lane
vraiment promouvable maintenant: `LABUSDT|5h|long`. `LABUSDT|3h|long` reste en
watch strict, et les autres variantes LAB ne doivent pas etre confondues avec
la 5h.

Lecture prioritaire: `promotion truth > lane scoring > strategy truth >
research consolidated`. Un ROI backtest eleve reste une piste tant qu'il n'a pas
passe cette chaine.

Diagnostic anti-overfit ajoute:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_promotion_ready_lanes_report --entry-micro-diagnostic --forward-window-trades 1000
```

Sortie:

- `aster_entry_microstructure_diagnostic_latest.json`.

Dernier smoke: 2 entrees rejouees sur `LABUSDT`, 2 verdicts
`microstructure_ok`, pass-rate `100%`, environ 96 trades et 45.2k USDT de flux
dans la fenetre d'entree testee.

Limite: pas de depth historique public dans ce test; on valide donc la
liquidite trade-tape autour de l'entree, pas le spread historique exact.

## Funding public reel dans le modele perps

Depuis la mise a jour du 2026-05-31, `backtest_strategy_discovery.py`
ne s'appuie plus uniquement sur le proxy fixe `1 bps / 8h` pour les
scenarios perps.

Le moteur recupere maintenant, une fois par symbole et par cycle, l'historique
public Aster:

`GET /fapi/v3/fundingRate?symbol=...&limit=100`

Implementation:

- module: `backend/services/onchain/aster/aster_perps_model.py`;
- cache local court: `aster_public_funding_history_cache.json`;
- integration discovery: `backend/services/onchain/aster/backtest_strategy_discovery.py`;
- colonnes CSV v2 ajoutees: `funding_source`, `funding_status`,
  `funding_count`, `funding_avg_bps_per_8h`, `funding_cost_usd_estimate`;
- fallback: si Aster bloque ou rate-limit, le moteur utilise encore le proxy
  fixe, mais le statut est visible dans le CSV.

Interpretation:

- funding positif: les longs paient les shorts;
- funding negatif: les shorts paient les longs;
- le cout/credit est applique au scenario perps en plus des frais officiels
  taker/maker deja modelises.

Impact:

- les comparaisons de leviers deviennent plus realistes;
- les strategies longues/shorts sur timeframes `2h` a `6h` sont mieux penalisees
  ou creditees selon le carry reel Aster;
- les anciens CSV restent utiles comme historique, mais les nouveaux runs tagges
  avec le schema v2 enrichi sont plus fiables pour classer les lanes.

## Frais officiels par symbole dans les nouveaux replays discovery

Le moteur `get_aster_paper_trading_focused_optimization_preview` utilisait
historiquement `fee_bps=6.0` par defaut. C'etait prudent, mais trop grossier.

Depuis le 2026-05-31:

- si `fee_bps` n'est pas fourni, le replay utilise `execution_fee_bps(symbol)`;
- `USDT` taker = `4.0` bps;
- `USD1` taker = `0.5` bps;
- maker/post-only reste modele a `0.0` bps dans `aster_perps_model.py`, mais la
  simulation de non-fill maker n'est pas encore active;
- chaque candidat conserve `fee_bps_applied` et `slippage_bps_applied` dans son
  `candidate_json`.

Impact:

- les nouveaux backtests sont moins penalises artificiellement que les anciens;
- les contrats `USD1` deviennent comparables avec leurs vrais frais beaucoup plus bas;
- les anciens resultats restent archivables, mais ne doivent pas etre melanges
  sans mentionner leur fee model.

## Mark/index visible dans les nouveaux CSV discovery

Les nouveaux CSV discovery v2 lisent aussi le snapshot existant:

`backend/services/onchain/aster/aster_mark_index_replay_filter_latest.json`

Ils n'appellent pas l'API mark/index pendant chaque batch discovery. Ils attachent
simplement, quand elle existe deja, la validation `(symbol, interval)`:

- `mark_index_verdict`;
- `mark_index_p95_last_index_bps`;
- `mark_index_avg_last_index_bps`;
- `mark_index_warnings`;
- `mark_index_blockers`.

Impact:

- une lane profitable mais `mark_index_rejected` peut etre identifiee directement
  dans le CSV, avant promotion;
- une lane `not_checked` reste exploitable en exploration, mais doit passer le
  filtre mark/index avant d'etre consideree robuste;
- le snapshot mark/index peut etre rafraichi separement, sans ralentir tous les
  runners H24.

## Replay optionnel sur mark price

Le runner discovery accepte maintenant:

`--trigger-reference mark_price`

Par defaut, les runners restent en `last_price` pour ne pas casser la continuite
historique. En mode `mark_price`, les klines futures last-price sont alignees avec
`/fapi/v3/markPriceKlines` et le replay utilise le close mark price comme prix
de decision/exit. Si le symbole est spot ou si le mark price manque, le moteur
retombe sur le last price et le signale dans les fetch failures.

Commande de comparaison conseillee, a lancer seulement quand on veut comparer
une lane stricte:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 `
  --output-tag aster_v2_mark `
  --require-preflight-ready `
  --trigger-reference mark_price `
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

Objectif: comparer `aster_v2_strict` en last price avec `aster_v2_mark` en mark
price. Une lane qui reste bonne dans les deux modes est plus credible qu'une
lane qui n'existe que sur last price.

## Modele d'execution explicite

Le discovery accepte maintenant:

`--execution-model taker_market|maker_post_only|bbo_limit`

Etat actuel:

- `taker_market`: modele historique, fill immediat, frais taker officiels par symbole,
  slippage complet;
- `maker_post_only`: frais maker `0 bps`, slippage `0 bps`, mais encore sans
  simulation de queue/non-fill;
- `bbo_limit`: frais maker `0 bps`, slippage proxy reduit de moitie, encore sans
  simulation exacte des ordres BBO/pegged.

Garde-fou important: les modes maker/BBO sont des proxies de cout, pas encore des
simulateurs de fill parfaits. Une lane qui ne devient bonne qu'en `maker_post_only`
doit etre marquee `needs_fill_model_validation` avant promotion.

Commande de comparaison maker/BBO:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 `
  --output-tag aster_v2_bbo `
  --require-preflight-ready `
  --execution-model bbo_limit `
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

## WebSocket branche dans le workflow discovery

La derniere priorite Aster n'est plus seulement un diagnostic separe.

Depuis le 2026-05-31:

- `backtest_aster_v2` accepte `--auto-ws-preflight`;
- le runner rafraichit les symboles `needs_ws_validation` via le rapport WS public;
- le plan v2 est regenere apres refresh;
- les nouveaux CSV discovery v2 attachent le snapshot WS local par symbole.

Colonnes ajoutees dans les nouveaux CSV v2:

- `ws_quality_verdict`;
- `ws_quality_score`;
- `ws_quality_risks`;
- `ws_quality_warnings`;
- `ws_quote_volume_24h`;
- `ws_spread_bps`;
- `ws_latency_ms`;
- `ws_streams_received`;
- `ws_streams_expected`.

Interpretation:

- `ws_forward_ready`: symbole propre pour forward/paper en priorite;
- `ws_forward_watch`: exploitable mais a surveiller;
- `ws_forward_risky`: backtest possible en exploration, mais pas prioritaire pour
  forward paper strict.

Commande conseillee pour les prochains runs stricts:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 `
  --output-tag aster_v2_strict `
  --auto-ws-preflight `
  --ws-preflight-max-symbols 10 `
  --require-preflight-ready `
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

## Donnees Aster documentees mais pas encore branchees

Audit source:

`docs/aster-official-docs-gap-audit.md`

La recherche documentaire officielle du 2026-05-31 ajoute quatre points a garder
en memoire:

- `aggTrades` / `historicalTrades`: utiles pour valider les champions plus finement
  que les klines, mais `aggTrades` impose des fenetres `<1h` quand on utilise
  `startTime/endTime`;
- WebSocket user stream: indispensable pour une execution reelle fiable, car les
  messages ordre/position doivent etre recuperes via listenKey et reordonnes avec
  `E`; bloque tant qu'on n'a pas de policy credentials;
- `placeStrategyOrder` (`OTO`, `OCO`, `OTOCO`): utile plus tard pour verifier qu'une
  strategie peut etre exprimee cote exchange avec entree + TP/SL, mais `TRADE`;
- MMP: protection market maker, utile seulement si on pousse un vrai modele
  maker/BBO, pas prioritaire pour les backtests actuels.

Nouvelle priorite recherche:

1. garder les runners kline 60j pour explorer large;
2. prendre les champions uniquement;
3. les revalider ensuite avec une passe `aggTrades`/`historicalTrades` plus fine;
4. ne promouvoir que les lanes qui restent bonnes apres frais, funding, mark/index,
   WS quality et validation microstructure.

## Watchlist priorisee

Le generateur de watchlist est initialise.

Module:

`backend/services/onchain/aster/research/watchlist_priority_builder.py`

Il consomme:

- `aster_public_universe_snapshot_latest.json`;
- `aster_ws_symbol_quality_report_latest.json`;
- `aster_mark_index_replay_filter_latest.json`;

Et produit une liste de symboles priorises:

- liquides;
- spread raisonnable;
- WS forward ready/watch;
- forte variation 24h ou funding/premium interessant;
- non deja surexploites par les runners actuels.

Snapshot actuel:

`backend/services/onchain/aster/aster_priority_watchlist_latest.json`

Symboles recommandes au dernier run:

- `BTCUSDT`
- `ASTERUSDT`
- `HYPEUSDT`
- `BNBUSDT`
- `ETHUSDT`
- `ETHUSD1`
- `PLAYUSDT`
- `SOLUSDT`

## Runner watchlist priorisee

Le pont entre la nouvelle couche univers/WS et l'ancien moteur de backtest est maintenant:

`backend/services/onchain/aster/backtest_priority_watchlist.py`

Il lit:

`backend/services/onchain/aster/aster_priority_watchlist_latest.json`

Puis delegue au moteur existant:

`backend/services/onchain/aster/backtest_strategy_discovery.py`

Sorties:

- `paper_trading_strategy_discovery_priority_watchlist_v2.csv`
- `paper_trading_strategy_discovery_priority_watchlist_latest.json`
- `aster_priority_watchlist_backtest_plan_latest.json`

Commande plan-only:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_priority_watchlist --plan-only
```

Commande H24:

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

## Prochaine etape conseillee

Lancer les deux pistes en parallele:

- exploitation: continuer a suivre les champions historiques, mais seulement si
  la queue de validation ne les rejette pas;
- priorite actuelle: `LABUSDT 30m` et `HYPEUSDT` avant `INTCUSDT`,
  `CRCLUSDT`, `MSFTUSDT`, `INJUSDT`;
- exploration: lancer un runner discovery dedie sur la watchlist priorisee,
  puis comparer les resultats au cockpit principal avant de les mettre dans les
  runners H24.

Le rapport dual-track sert de garde-fou: un nouveau symbole n'efface pas un ancien champion tant qu'il ne l'a pas battu avec assez de trades fermes et un reality check acceptable.

## Validation des champions historiques

Pour travailler vraiment les anciens backtests, on utilise:

`backend/services/onchain/aster/research/exploitation_champions_validator.py`

Il consomme la piste `exploitation_track`, puis ajoute:

- quality check perps public;
- mark/index replay check;
- score de validation;
- decision: `promote_to_forward_candidate`, `keep_testing`, `needs_reality_check`, `reject_or_manual_review`, `deprioritize`.

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -c "from services.onchain.aster.aster_exploitation_champions_validator import get_aster_exploitation_champions_validation_preview; r=get_aster_exploitation_champions_validation_preview(max_champions=8); print(r['summary'])"
```

## Runner Aster v2

Le runner unifie du nouveau systeme est:

`backend/services/onchain/aster/backtest_aster_v2.py`

Il lit:

- `aster_exploitation_champions_latest.json`;
- `aster_priority_watchlist_backtest_plan_latest.json`;
- `aster_public_universe_snapshot_latest.json`;
- `aster_ws_symbol_quality_report_latest.json`.

Puis il construit:

`backend/services/onchain/aster/aster_v2_runner_plan_latest.json`

Il combine:

- exploitation: champions `keep_testing` / `promote_to_forward_candidate`;
- review: champions `needs_reality_check`;
- exploration: symboles de la watchlist priorisee.

Preflight:

- `backtest_ready`: universe + WS assez propres;
- `needs_ws_validation`: universe OK mais WS pas encore valide;
- `needs_universe_refresh`: ancien snapshot universe incomplet;
- `blocked_data_quality`: ne doit pas etre lance.

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_aster_v2 --plan-only
```

## Regle de prudence

Un symbole prometteur dans cette carte n'est pas un signal.

Il devient seulement:

- candidat backtest;
- candidat paper forward;
- candidat review.

Aucun ordre reel, aucun wallet, aucun signal client.

## Donnees officielles Aster a integrer plus tard

La recherche doc du 2026-05-31 ajoute trois zones a ne pas oublier:

1. Spot V3 est un marche distinct des perps.
   - Base URL: `https://sapi.asterdex.com`.
   - WS spot: `wss://sstream.asterdex.com`.
   - Pas de funding, pas de liquidation, pas de leverage.
   - Une lane rentable via fallback spot doit etre marquee `market_type=spot`.

2. Stock perps / equities ont des contraintes de session.
   - Horaires de reference New York.
   - Hors session open, ordres trop agressifs vs mark price peuvent etre rejetes.
   - Les bons ROI equities (`MSFTUSDT`, `INTCUSDT`, `NVDAUSDT`, etc.) doivent
     rester `needs_session_filter` tant que le replay ne simule pas les horaires
     US et jours feries.

3. Le modele perps peut encore etre durci.
   - Aster documente `open_loss` dans le cout d'ouverture.
   - Aster documente l'ADL, mais la quantile ADL est `USER_DATA`.
   - Les lanes x10/x20 doivent donc afficher clairement:
     `open_loss_not_modelled` ou `open_loss_estimated`, et `adl_not_modelled`.

4. WebSocket public a encore deux flux utiles.
   - `!bookTicker` pour spread/bid/ask all-symbol sans poll REST.
   - `!forceOrder@arr` pour detecter les regimes de liquidation.
   - Ces flux sont read-only et compatibles avec notre politique actuelle.

5. Aster a plusieurs produits qu'il ne faut pas melanger.
   - `pro_orderbook_perp`: notre moteur actuel.
   - `spot`: fallback sans leverage/funding/liquidation.
   - `shield_perp` et `simple_1001x`: frais/slippage/liquidation differents,
     donc moteur separe obligatoire si on les teste un jour.

6. Les marches macro ont besoin d'un modele de session.
   - Forex Shield: ouvert lundi-jeudi, vendredi ferme en fin de journee UTC,
     samedi ferme, dimanche reouverture tardive UTC.
   - Stocks: horaires New York + off-hours.
   - XAU/XAG peuvent fermer pendant les jours feries US.
   - Les commodities type `CLUSDT`, `BZUSDT`, `CRCLUSDT`, `ORCLUSDT` doivent
     rester `needs_session_model` tant qu'on n'a pas confirme leur produit exact.

7. Donnees publiques all-symbol confirmees.
   - `/ticker/bookTicker` sans symbole retourne `448` lignes depuis `fapi.asterdex.com`.
   - `/fundingInfo` sans symbole retourne `602` lignes.
   - `/indexreferences?symbol=BTCUSDT` retourne `8` references.
   - Les exemples `fapi3.asterdex.com` peuvent retourner `403`; utiliser la base
     operationnelle `https://fapi.asterdex.com`.
   - `trades`, `historicalTrades` et `aggTrades` excluent insurance fund et ADL:
     la validation microstructure reste orderbook-only.

8. RPC adresse existe mais n'est pas market-data.
   - `https://tapi.asterdex.com/info` expose balance, open orders et fills par
     adresse, en JSON-RPC 2.0.
   - Smoke adresse zero: reponse OK mais `accountPrivacy=enabled`.
   - Fills limites a `7 jours`, open orders max `1000`.
   - Usage futur possible: audit de notre propre wallet/paper-live.
   - Usage interdit maintenant: scanner des adresses tierces ou enrichir les
     backtests de marche global avec des comptes utilisateurs.

9. Aster Code / Agent / Builder est une future surface execution.
   - `approveAgent`, `updateAgent`, `deleteAgent`, `approveBuilder`.
   - Permissions importantes: `canSpotTrade`, `canPerpTrade`, `canWithdraw`.
   - Garde-fou futur: `canWithdraw=false`, expiration, IP whitelist, signer dedie.
   - Hors runners actuels.

10. Deposit/withdraw public assets existe mais reste wallet setup.
    - BNB Chain/EVM/spot smoke: `53` deposit assets et `53` withdraw assets.
    - Fee estimate ASTER smoke: `gasCost=0.1389`, `gasUsdValue=0.1`.
    - Utile pour preparer un wallet dedie, pas pour scorer une lane.
    - Endpoints withdrawal signes et transferts restent interdits.

11. Contraintes operationnelles API.
    - `403` = WAF, `429` = rate limit, `418` = ban IP, `503` = statut inconnu.
    - Nonce V3 en microsecondes, tolerance server time `10s`.
    - Preferer WebSocket / all-symbol pour eviter de surcharger REST.

12. Error codes a transformer en flags backtest.
    - `-2016 NO_TRADING_WINDOW`: risque majeur pour equities/macro.
    - `-2027/-2028`: leverage impossible avec taille/marge courante.
    - `-4016/-4024`: prix hors bornes mark-price `PERCENT_PRICE`.
    - `-4004/-4005/-4014/-4023`: rejet possible par qty/tick/step size.
    - `-1006/-1007`: statut inconnu, jamais de reexecution aveugle en paper/live.

13. `exchangeInfo` public donne les vraies bornes par symbole.
    - Smoke 2026-05-31: `453` symboles publics.
    - Tous exposent `PRICE_FILTER`, `LOT_SIZE`, `MARKET_LOT_SIZE`,
      `MIN_NOTIONAL`, `PERCENT_PRICE`.
    - `marketTakeBound` observe: majoritairement `0.05`, puis `0.10`, `0.02`,
      avec quelques cas `0.15/0.20`.
    - `triggerProtect` observe: majoritairement `0.0500`, puis `0.1000`,
      `0.0200`.
    - `LABUSDT` et `WIFUSDT` sont plus permissifs (`marketTakeBound=0.10`) que
      `INTCUSDT`, `MSFTUSDT`, `CRCLUSDT` (`0.02`).
    - Les CSV doivent ajouter `trigger_protect`, `market_take_bound`,
      `percent_price_up/down`, `tick_size`, `step_size`, `min_notional`,
      `liquidation_fee_rate`.
    - Implementation appliquee: `paper_trading_strategy_discovery_*_v2.csv`
      expose maintenant ces champs et un `exchange_filter_verdict`.

14. Changelog recent a ne pas oublier.
    - 2026-05-21: `STP` (`EXPIRE_TAKER`, `EXPIRE_MAKER`, `EXPIRE_BOTH`).
    - 2026-05-22: Strategy Orders `OTO/OCO/OTOCO`, poids `50`, signed/TRADE.
    - 2026-05-22: Aster Chain transfer signe.
    - Ces surfaces sont documentees, mais hors runners read-only actuels.

15. Dernier morceau public `exchangeInfo`: assets de marge et rate limits.
    - `assets_count=33`, tous `marginAvailable=true` dans le snapshot observe.
    - Assets observes: `USDT`, `BTC`, `BNB`, `ETH`, `SOL`, `BUSD`, `CAKE`,
      `USDC`, `USD1`, `ASTER`, etc.
    - Rate limits observes: `REQUEST_WEIGHT=2400/min`, `ORDERS=1200/min`,
      `ORDERS=300/10s`.
    - Pour nous: rester conservateur, privilegier endpoints all-symbol et WS.

16. Futures account/trading reste signe et hors runners.
    - `income`, `leverageBracket`, `adlQuantile`, `forceOrders`,
      `commissionRate`, MMP, batch orders, strategy orders, sub-account,
      migration assets.
    - Utile plus tard avec une policy credentials read-only stricte.
    - Pas utile maintenant pour backtests publics, sauf comme liste des limites
      non modelisees.

Priorite recommandee:

1. Continuer l'exploration kline 60j large.
2. Ne promouvoir que les meilleurs champions.
3. Rejouer ces champions avec mark/index + WS quality.
4. Ajouter ensuite une validation microstructure `aggTrades`/`historicalTrades`.
5. Ajouter `!bookTicker` et `!forceOrder@arr` au preflight WS.
6. Pour equities/macro, ajouter un filtre de session avant de prendre les ROI au serieux.
7. Ajouter dans les CSV les risques: `funding_interval_hours`,
   `funding_cap_floor_width`, `index_reference_count`,
   `system_risk_events_not_included`.
8. Garder RPC/Aster Code dans la documentation d'execution future, pas dans la
   boucle backtest.
9. Garder deposit/withdraw assets en doc wallet setup, jamais comme signal.
10. Ajouter un filtre `exchangeInfo` sur les champions avant de conclure sur ROI.
11. Considerer la couverture docs Aster comme presque complete cote public; les
    prochaines ameliorations doivent plutot brancher les donnees deja connues.

## Status exchangeInfo runners

Outil local ajoute:

`backend/services/onchain/aster/research/exchangeinfo_run_status.py`

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.research.exchangeinfo_run_status
```

Role:

- lit uniquement les heartbeats et CSV locaux `*_exchangeinfo*`;
- ne relance aucun backtest;
- ne fait aucun appel Aster;
- indique si les CSV sont encore `running_waiting_for_cycle_end` ou deja
  `csv_ready`;
- snapshot local: `aster_exchangeinfo_run_status_latest.json`.
