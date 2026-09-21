# Aster - Audit des connaissances hors MCP

Date: 2026-05-31

Objectif: verifier ce que la documentation officielle Aster apporte au-dela du MCP et de nos endpoints publics deja branches, avant de continuer les backtests.

## Sources officielles consultees

- Aster order types: `https://docs.asterdex.com/trading/perpetuals/order-types`
- Aster Pro order types: `https://docs.asterdex.com/product/aster-pro/order-types`
- Aster margin: `https://docs.asterdex.com/product/aster-perpetuals/margin`
- Aster fees: `https://docs.asterdex.com/trading/perpetuals/fees-and-specs/fees`
- Aster funding rate: `https://docs.asterdex.com/trading/perpetuals/fees-and-specs/funding-rate`
- Aster liquidations: `https://docs.asterdex.com/trading/perpetuals/fees-and-specs/liquidations-1`
- Aster mark price: `https://docs.asterdex.com/product/aster-perpetuals/fees-and-specs/perpetuals-mark-price`
- Aster hedge mode: `https://docs.asterdex.com/trading/perpetuals/hedge-mode`
- Aster single/multi asset mode: `https://docs.asterdex.com/trading/perpetuals/single-asset-mode-and-multi-asset-mode`
- Aster stock perpetuals: `https://docs.asterdex.com/product/aster-perpetual-pro/stock-contracts`
- Aster Futures V3 account/trading API: `https://asterdex.github.io/aster-api-website/futures-v3/account%26trades/`
- Aster Futures V3 general info: `https://asterdex.github.io/aster-api-website/futures-v3/general-info/`
- Aster Futures V3 market data: `https://asterdex.github.io/aster-api-website/futures-v3/market-data/`
- Aster Futures WebSocket account info: `https://asterdex.github.io/aster-api-website/futures/user-data-streams/`
- Aster API changelog: `https://asterdex.github.io/aster-api-website/changelog/2026-5-26/`
- Aster Spot V3 general info: `https://asterdex.github.io/aster-api-website/spot-v3/general-info/`
- Aster Spot V3 market data: `https://asterdex.github.io/aster-api-website/spot-v3/market-data/`
- Aster Spot account/trading API: `https://asterdex.github.io/aster-api-website/spot/spot-account-and-trading-api/`
- Aster Spot WebSocket market data: `https://asterdex.github.io/aster-api-website/spot/websocket-market-data/`
- Aster single/multi asset collateral ratios: `https://docs.asterdex.com/trading/perpetuals/single-asset-mode-and-multi-asset-mode`
- Aster Shield stock market: `https://docs.asterdex.com/trading/shield-mode/stock-market`
- Aster costs of opening positions: `https://docs.asterdex.com/product/aster-perpetual-pro/fees-and-specs/costs-of-opening-positions`
- Aster ADL: `https://docs.asterdex.com/trading/perpetuals/fees-and-specs/auto-deleveraging-adl`
- Aster RPC general info: `https://asterdex.github.io/aster-api-website/rpc/general-info/`
- Aster futures WebSocket market streams: `https://asterdex.github.io/aster-api-website/futures/websocket-market-streams/`
- Aster Shield fees/specs: `https://docs.asterdex.com/trading/shield-mode/fees-and-specs`
- Aster 1001x fees/slippage: `https://docs.asterdex.com/product/1001x-simple/fees-and-slippage`
- Aster Perp Shield forex market: `https://docs.asterdex.com/product/perp-shield/forex-market`
- Aster Perp Shield stock market: `https://docs.asterdex.com/product/perp-shield/stock-market`
- Aster Perp Shield mark price: `https://docs.asterdex.com/trading/shield-mode/mark-price`
- Aster Perp Shield position mode: `https://docs.asterdex.com/product/perp-shield/position-mode`
- Aster RPC endpoints: `https://asterdex.github.io/aster-api-website/rpc/endpoints/`
- Aster Code integration flow: `https://asterdex.github.io/aster-api-website/asterCode/integration-flow/`
- Aster Code authentication: `https://asterdex.github.io/aster-api-website/asterCode/authentication/`
- Aster Code endpoints: `https://asterdex.github.io/aster-api-website/asterCode/endpoints/`
- Aster Chain endpoints: `https://asterdex.github.io/aster-api-website/aster-chain/endpoints/`
- Aster Futures V3 deposit & withdrawal: `https://asterdex.github.io/aster-api-website/futures-v3/deposit%26withdrawal/`
- Aster Futures V3 error codes: `https://asterdex.github.io/aster-api-website/futures-v3/error-codes/`
- Aster changelog 2026-05-22: `https://asterdex.github.io/aster-api-website/changelog/2026-5-22/`
- Aster changelog 2026-05-21: `https://asterdex.github.io/aster-api-website/changelog/2026-5-21/`

## Verification supplementaire du 2026-05-31

La relecture de la doc officielle confirme que notre socle public est bien oriente,
mais ajoute plusieurs details importants pour la suite des backtests.

### A. Donnees publiques qu'on peut encore mieux exploiter

La page Futures V3 Market Data confirme:

- `GET /fapi/v3/historicalTrades`: historique par `fromId`, poids `20`, max `1000`;
- `GET /fapi/v3/aggTrades`: accepte `fromId`, `startTime`, `endTime`, max `1000`,
  mais si `startTime` et `endTime` sont fournis, la fenetre doit rester inferieure
  a `1h`;
- `GET /fapi/v3/klines`: max `1500`, poids variable selon `limit`;
- `GET /fapi/v3/indexPriceKlines`: max `1500`, utilise `pair`;
- `GET /fapi/v3/markPriceKlines`: max `1500`, utilise `symbol`;
- `GET /fapi/v3/premiumIndex`: mark, index, funding courant, next funding;
- `GET /fapi/v3/fundingRate`: max `1000`, ordre ascendant, utile pour remplacer
  le proxy fixe.

Impact:

- pour un vrai replay 60j plus fin que les klines, `aggTrades` est exploitable
  mais doit etre pagine par fenetres `<1h`; ce n'est pas un simple appel large;
- les klines restent le meilleur compromis H24 pour explorer beaucoup de symboles;
- les top lanes doivent ensuite passer par une validation plus fine `aggTrades`
  ou WS forward, pas directement par execution.

### B. WebSocket user stream: indispensable pour l'execution, pas pour maintenant

La doc insiste sur le fait qu'en marche volatil, l'etat d'ordre/position doit
venir du WebSocket user data stream plutot que du REST.

Regles importantes:

- `listenKey` valide `60 minutes`;
- `PUT` prolonge la validite de `60 minutes`;
- `DELETE` ferme le stream;
- endpoint WS: `/ws/<listenKey>`;
- les messages user-data peuvent arriver desordonnes en periode lourde: il faut
  les reordonner avec `E`;
- une connexion WS dure au maximum `24h`, il faut prevoir reconnexion.

Impact:

- sans user stream, aucun moteur live reel ne doit etre considere fiable;
- notre paper trading peut rester REST/WS public, mais toute future execution
  doit avoir un module dedie: listenKey lifecycle, reconnect 24h, reorder by `E`,
  reconciliation position/order;
- aucun de ces endpoints ne doit etre active tant qu'on n'a pas une politique
  credentials read-only/testnet claire.

### C. Strategy orders OTO/OCO/OTOCO

La doc Futures V3 expose `POST /fapi/v3/placeStrategyOrder`:

- supporte `OTO`, `OCO`, `OTOCO`;
- utile pour attacher entree + stop + take profit cote exchange;
- endpoint `TRADE`, poids important, donc bloque maintenant.

Impact:

- pour le backtest, cela donne une structure cible: une position robuste devrait
  pouvoir etre exprimee comme entree + sortie reduce-only + TP/SL;
- avant execution reelle, il faudra verifier que nos strategies peuvent etre
  traduites en `strategy order` ou en sequence d'ordres atomique; sinon elles
  restent research-only.

### D. MMP / Market Maker Protection

La doc expose `POST/GET/DELETE/RESET /fapi/v3/mmp`.

MMP permet de limiter la quantite, valeur ou delta cumule rempli dans une fenetre,
puis de geler les ordres pendant une duree definie.

Impact:

- pas prioritaire pour notre paper trading retail;
- potentiellement utile plus tard pour une execution maker/BBO a grande frequence;
- a documenter comme garde-fou exchange, pas comme signal alpha.

### E. Leverage brackets et commission rate restent USER_DATA

La doc confirme:

- `GET /fapi/v3/leverageBracket` retourne les brackets, `initialLeverage`,
  `notionalCap`, `notionalFloor`, `maintMarginRatio`;
- `GET /fapi/v3/commissionRate` retourne `makerCommissionRate` et
  `takerCommissionRate` par symbole;
- ces endpoints sont `USER_DATA`, donc non publics.

Impact:

- notre maintenance margin reste un proxy tant qu'on n'a pas une policy
  credentials read-only/testnet;
- les frais officiels publics documentes suffisent pour les hypotheses par defaut,
  mais les frais reels compte peuvent diverger;
- les CSV doivent continuer a afficher clairement `maintenance_margin_source=proxy`.

### F. Spot V3: donnees publiques distinctes des perps

Spot V3 a sa propre base URL:

`https://sapi.asterdex.com`

Endpoints publics utiles:

- `GET /api/v3/exchangeInfo`;
- `GET /api/v3/depth`;
- `GET /api/v3/trades`;
- `GET /api/v3/historicalTrades`;
- `GET /api/v3/aggTrades`;
- `GET /api/v3/klines`;
- `GET /api/v3/ticker/24hr`;
- `GET /api/v3/ticker/price`;
- `GET /api/v3/ticker/bookTicker`;
- `GET /api/v3/commissionRate`.

Differences importantes vs futures:

- `ticker/24hr` sans symbole a un poids beaucoup plus eleve (`40`);
- `exchangeInfo` spot expose des filtres comme `MAX_NOTIONAL`, `NOTIONAL` et
  `PERCENT_PRICE_BY_SIDE`;
- `commissionRate` spot est documente dans Market Data et retourne maker/taker
  par symbole;
- les streams spot utilisent `wss://sstream.asterdex.com`, pas `fstream`;
- la reconstruction correcte du carnet WS spot exige le protocole snapshot +
  increments: subscribe depth, cache, fetch REST depth, drop `u <= lastUpdateId`,
  puis verifier `U/u/pu`.

Impact:

- notre fallback spot actuel permet de lire des trades/klines, mais il ne doit pas
  etre melange avec les hypotheses perps: pas de funding, pas de liquidation,
  pas de leverage;
- LAB ou d'autres symbols spot doivent etre etiquetes `market_type=spot` dans les
  validations fines;
- si une strategie n'est rentable que via fallback spot, elle n'est pas une strategie
  perps Aster et doit etre analysee separement.

### G. Stock perps: deux couches de contraintes

La doc `Stock Perpetuals` indique pour les stock perps:

- pre-market/off-hours 04:00-09:30 New York;
- market open 09:30-16:00;
- post-market/off-hours 16:00-20:00;
- market close/off-hours 20:00-04:00;
- hors market open, les limit orders trop agressifs de plus de `2%` vs mark price
  peuvent etre rejetes;
- les market orders peuvent remplir jusqu'a `2%` plus agressif que mark price,
  puis annuler le reste.

La doc `Shield Mode / Stock Market` ajoute une contrainte differente:

- stock perps jusqu'a `50x` en Shield Mode;
- le leverage max peut etre temporairement reduit une heure avant off-hours;
- off-hours: les updates de prix peuvent etre suspendues et les fonctions trading
  indisponibles;
- fermeture aussi pendant les jours feries US.

Impact:

- nos backtests equities actuels ne sont pas encore suffisamment realistes;
- il faut distinguer `stock_perp_pro_orderbook` vs `stock_perp_shield` si les
  symboles ne suivent pas les memes limites;
- un bon ROI sur `MSFTUSDT`, `INTCUSDT`, `NVDAUSDT`, etc. doit etre marque
  `needs_session_filter` tant qu'on ne simule pas les horaires US/New York et
  jours feries;
- `leverage x20` sur equities ne doit pas etre accepte automatiquement: selon le
  mode produit, le cap peut etre `10x`, `50x`, ou temporairement reduit.

### H. Collateral value ratios multi-asset

La doc single/multi asset precise:

- Single-Asset Mode: collateral USDT seulement, PnL par position;
- Multi-Asset Mode: collateral partage et PnL nettee, mais mode cross uniquement;
- chaque collateral a un value ratio.

Exemples BNB Chain documentes:

- USDT `99.99%`;
- USD1 `99%`;
- BTC / ETH / BNB `95%`;
- ASTER `80%`;
- LISTA / TWT `10%`.

Impact:

- notre choix actuel `isolated + single_asset + one_way` reste le plus propre;
- si on simule un jour multi-asset, il faudra appliquer les haircuts collateral,
  le netting PnL, et le risque cross;
- ne pas comparer un backtest isolated avec un futur run multi-asset sans label
  tres clair.

### I. Cout d'ouverture: open loss et asymetrie long/short

La doc `Costs of opening positions` donne un detail important pour notre moteur
perps: le cout d'ouverture ne se limite pas a `notional / leverage`.

Pour les limit et market orders, Aster calcule aussi un `open loss`:

`open_loss = contracts * abs(min(0, direction * (mark_price - order_price)))`

Avec `direction = 1` pour long et `-1` pour short.

Impact:

- un long agressif au-dessus du mark price peut demander plus de marge que le
  simple initial margin;
- un short agressif peut ne pas avoir le meme open loss selon la relation
  `order_price` / `mark_price`;
- nos backtests avec leverage x10/x20 sont encore trop propres s'ils ne verifient
  que liquidation/funding/frais sans simuler ce cout d'ouverture;
- prochaine amelioration utile: ajouter `open_loss_usd_estimate` et
  `opening_cost_usd_estimate` dans le modele perps, au moins pour les lanes
  championnes.

### J. ADL: risque non modele mais a documenter

La doc ADL explique que la priorite depend du profit non realise, du wallet balance
et de la margin ratio. Plus le `LeveragePnLQuantile` est eleve, plus le risque
d'auto-deleveraging augmente.

Impact:

- notre paper trading ne simule pas l'ADL;
- sur levier eleve, un backtest peut etre profitable tout en etant expose a un
  risque de reduction forcee en marche extreme;
- `GET /fapi/v3/adlQuantile` existe, mais c'est `USER_DATA`; donc bloque tant que
  nous n'avons pas de credentials read-only/testnet;
- les lanes x20 doivent rester marquees `adl_not_modelled` tant qu'on ne peut pas
  lire ou approximer ce risque.

### K. RPC / privacy publique: non prioritaire pour notre alpha

La doc RPC expose une base differente:

`https://tapi.asterdex.com/info`

Elle mentionne notamment la confidentialite des open orders / fills selon les
parametres du compte.

Impact:

- utile pour comprendre l'ecosysteme Aster, mais pas directement exploitable pour
  nos backtests publics;
- ne remplace pas les feeds futures/spot officiels;
- ne doit pas etre ajoute au moteur de replay tant qu'on ne sait pas precisement
  quel payload stable on veut consommer.

### L. Liquidation streams publics: donnees de stress a tester

La doc Futures WebSocket expose deux streams publics utiles:

- `<symbol>@forceOrder`;
- `!forceOrder@arr`.

Ces streams publient des snapshots de liquidations forcees. Pour chaque symbole,
seule la derniere liquidation dans une fenetre de `1000ms` est poussee; s'il n'y
a pas de liquidation, aucun message n'est emis.

Impact:

- ce n'est pas une source historique complete;
- c'est tres utile en forward/paper pour detecter un regime de stress;
- une strategie qui performe seulement pendant des cascades de liquidation doit
  etre taggee `liquidation_regime_dependent`;
- prochaine amelioration data: ajouter un validateur read-only `forceOrder`
  public, comme on l'a fait pour `aggTrade`, `depth`, `kline` et `markPrice`.

### M. FundingInfo et indexReferences: deja valides, pas assez exploites

La doc Futures V3 confirme deux endpoints publics importants:

- `GET /fapi/v3/fundingInfo`: `interestRate`, `fundingIntervalHours`,
  `fundingFeeCap`, `fundingFeeFloor`;
- `GET /fapi/v3/indexreferences`: composition de l'index price avec exchanges
  sources et poids.

Etat actuel:

- les probes publics les valident deja;
- le reality check en extrait deja une partie;
- le cockpit ne les met pas encore assez en avant comme facteurs de risque.

Impact:

- `fundingIntervalHours` peut etre `4h`, `8h`, ou autre selon symbole; le moteur
  ne doit pas supposer `8h` partout;
- `fundingFeeCap/Floor` larges indiquent un symbole potentiellement violent;
- `index_reference_count` faible ou references concentrees = risque de mark/index
  plus fragile;
- prochaine amelioration: ajouter dans les CSV un champ explicite
  `index_reference_count`, `funding_interval_hours`, `funding_cap_floor_width`.

### N. Produits Shield / 1001x: ne pas melanger avec Aster Pro perps

La documentation Shield et 1001x decrit des logiques differentes:

- Shield Mode peut utiliser profit-share, flat fee, dynamic slippage;
- 1001x a des frais d'ouverture/fermeture propres, funding par bloc, execution
  fee et liquidation formulas specifiques;
- Degen/1001x peut aller jusqu'a des leviers extremes, mais ce n'est pas notre
  moteur orderbook perps actuel.

Impact:

- ces pages sont utiles pour comprendre l'ecosysteme, mais elles ne doivent pas
  modifier les backtests Aster Pro orderbook;
- si on veut tester Shield ou 1001x, il faudra un `product_mode` separe:
  `pro_orderbook_perp`, `shield_perp`, `simple_1001x`;
- ne pas utiliser les frais 1001x/Shield pour corriger les CSV perps actuels.

### O. Forex / RWA / commodities: sessions et produit a separer

La doc `Perp Shield / Forex Market` indique:

- EUR/USDT et GBP/USDT sont des paires forex Shield;
- leverage jusqu'a `500x`;
- marche ouvert lundi-jeudi;
- fermeture vendredi a partir de `23:00 UTC` en DST ou `22:00 UTC` hors DST;
- samedi ferme;
- dimanche ferme jusqu'a `23:00 UTC` en DST ou `22:00 UTC` hors DST;
- baisse temporaire du leverage max une heure avant off-hours;
- fermeture pendant les jours feries US.

La doc `Perp Shield / Stock Market` confirme aussi que XAU/XAG suivent des
contraintes de fermeture pendant les jours feries US.

Impact:

- les paires macro (`XAUUSDT`, `XAGUSDT`, `CLUSDT`, `BZUSDT`, `CRCLUSDT`,
  `ORCLUSDT`) ne doivent pas toutes etre traitees comme crypto 24/7;
- il faut un champ futur `session_model`: `crypto_24_7`, `us_equity_session`,
  `forex_week_session`, `commodity_session_unknown`;
- les bons backtests `CRCLUSDT 2h` / `XAUUSDT` doivent rester exploitables, mais
  tagges `needs_session_model` avant promotion;
- si une paire macro vient de Shield et non du carnet Pro, son modele doit etre
  `shield_perp`, pas `pro_orderbook_perp`.

### P. Shield mark price et position mode: information utile mais hors moteur actuel

La doc Shield `Mark Price` indique une difference majeure: Shield n'a pas de carnet
d'ordres public, donc le mark price y est egal au last price dans ce mode.

La doc Shield `Position Mode` indique:

- positions isolees par paire;
- pas de hedge mode;
- pas d'ajout de marge a une position existante.

Impact:

- ces regles sont incompatibles avec notre simulateur actuel de carnet Pro;
- elles peuvent inspirer un moteur `shield_perp` plus simple, mais il ne faut pas
  les appliquer silencieusement aux CSV `pro_orderbook_perp`;
- si un actif macro/equity renvoie de bons chiffres, il faut verifier le produit
  exact: Pro orderbook, Spot, Shield, ou 1001x.

### Q. Smoke public supplementaire: bookTicker / fundingInfo / indexReferences

Smoke read-only effectue le 2026-05-31 avec la base reelle utilisee par notre code:

`https://fapi.asterdex.com`

Resultats:

- `GET /fapi/v3/ticker/bookTicker` sans symbole:
  - `448` book tickers retournes;
  - premier symbole observe: `BTCUSDT`;
  - utilite: spread all-symbol et bid/ask pour prefiltrer les lanes.
- `GET /fapi/v3/fundingInfo` sans symbole:
  - `602` configs funding retournees;
  - exemple observe: `TRUTHUSDT` avec `fundingIntervalHours=1`;
  - utilite: ne pas supposer funding `8h` partout.
- `GET /fapi/v3/indexreferences?symbol=BTCUSDT`:
  - `8` references index observees;
  - premiere reference: `binance`, poids observe `0.43480174`;
  - utilite: mesurer la concentration de l'index.

Point important:

- La documentation montre parfois `https://fapi3.asterdex.com` dans les exemples,
  mais depuis notre environnement cet host retourne `403`.
- Notre code utilise `https://fapi.asterdex.com`, qui repond correctement.

Impact:

- ajouter `bookticker_all_count`, `funding_info_all_count`,
  `index_reference_count` dans les rapports data quality;
- ajouter `funding_interval_hours` et `funding_cap_floor_width` dans les CSV v2;
- utiliser `ticker/24hr.firstId/lastId/count` pour borner une future pagination
  `historicalTrades` / `aggTrades` sur les champions.

### R. Limite cachee des trades historiques: pas d'ADL ni insurance fund

La doc Futures V3 precise que:

- `trades`;
- `historicalTrades`;
- `aggTrades`;

retournent uniquement les market trades remplis dans l'order book. Les trades
insurance fund et ADL ne sont pas inclus.

Impact:

- une validation microstructure `aggTrades` est meilleure que les klines, mais
  elle ne reconstruit pas tout le risque systemique;
- les cascades ADL/liquidation doivent venir de `forceOrder`/risk flags, pas des
  trades historiques classiques;
- les rapports devront distinguer `orderbook_trade_replay` de
  `system_risk_events_not_included`.

### S. RPC public: donnees compte par adresse, privacy-aware

La doc RPC expose:

`POST https://tapi.asterdex.com/info`

Methodes documentees:

- `aster_getBalance`;
- `aster_openOrders`;
- `aster_userFills`;
- `aster_spotOpenOrders`;
- `aster_spotUserFills`.

Smoke read-only du 2026-05-31 avec l'adresse zero:

- `aster_getBalance`: repond avec `accountPrivacy="enabled"`;
- `aster_openOrders`: repond avec `accountPrivacy="enabled"`;
- `aster_userFills`: repond avec `accountPrivacy="enabled"` et une fenetre de
  temps, sans fills.

Contraintes importantes:

- les fills sont limites a des fenetres de `7 jours`;
- les open orders retournent au maximum `1000` records;
- certains endpoints ne montrent que les ordres depuis le genesis block timestamp
  `1772678119418`;
- la privacy peut masquer les details.

Impact:

- utile plus tard pour verifier notre propre wallet paper/live sans endpoint
  `USER_DATA` signe, si on accepte un mode audit read-only adresse;
- pas utile pour backtester le marche global;
- ne pas scanner des adresses tierces sans raison de recherche claire;
- documenter comme `address_state_rpc`, pas comme `market_data`.

### T. Aster Code / Builder: informations utiles pour execution future, pas pour maintenant

La doc Aster Code decrit:

- creation d'un Agent/API Wallet via `approveAgent`;
- permissions `canSpotTrade`, `canPerpTrade`, `canWithdraw`;
- IP whitelist;
- expiration de l'agent;
- builder address et `maxFeeRate`;
- signature EIP-712 avec deux modes:
  - management endpoints: signature dynamique;
  - trading endpoints: signature du querystring final dans `Message.msg`;
- chainId mainnet `1666`, testnet `714`.

Garde-fous a retenir:

- `canWithdraw` doit rester `false`;
- un agent doit etre expire dans le temps;
- l'IP whitelist doit etre obligatoire si un jour on branche execution;
- builder `feeRate` doit rester inferieur ou egal au `maxFeeRate` approuve;
- aucun de ces endpoints ne doit entrer dans nos runners de backtest.

Impact:

- utile pour le futur plan d'execution securise;
- hors scope tant qu'on cherche seulement des backtests;
- ajouter dans la roadmap une policy `agent_read_only_or_paper_first`, avant
  toute cle privee ou ordre reel.

### U. Aster Chain endpoints: privacy/status/transfer, hors backtest

La doc Aster Chain expose:

- base URL: `https://chainapi.asterdex.com`;
- `GET /aster-chain/v3/account/status` (`USER_DATA`);
- `POST /aster-chain/v3/account/modify-status` (`TRADE`);
- `POST /aster-chain/v3/transfer` (`WITHDRAW`).

Impact:

- utile pour comprendre la privacy Aster Chain;
- `transfer` est explicitement hors scope;
- ne doit pas etre branche dans le moteur de recherche;
- si un jour on documente un wallet setup, la seule information utile est:
  verifier/forcer la privacy et ne jamais activer transfer/withdraw dans un agent.

### V. Public deposit/withdraw assets: utile wallet setup, pas backtest

La doc Deposit & Withdrawal expose aussi des endpoints publics sur `www.asterdex.com`
pour lister assets et frais par chaine.

Smoke read-only du 2026-05-31:

- `GET /bapi/futures/v1/public/future/aster/deposit/assets?chainIds=56&networks=EVM&accountType=spot`
  - reponse `success=true`;
  - `53` assets retournes sur BNB Chain/EVM/spot.
- `GET /bapi/futures/v1/public/future/aster/withdraw/assets?chainIds=56&networks=EVM&accountType=spot`
  - reponse `success=true`;
  - `53` assets retournes;
  - `withdrawType` observe: `autoWithdraw`.
- `GET /bapi/futures/v1/public/future/aster/estimate-withdraw-fee?chainId=56&network=EVM&currency=ASTER&accountType=spot`
  - reponse `success=true`;
  - `gasCost` observe: `0.1389`;
  - `gasUsdValue` observe: `0.1`.

Impact:

- utile pour savoir quels assets/chains sont supportes si on prepare un wallet
  dedie;
- utile pour documenter les frais de retrait, mais pas pour evaluer une strategie;
- ne doit pas entrer dans les CSV de backtest;
- endpoints withdrawal signes et transfert restent interdits.

### W. Rate limits / erreurs: donnees operationnelles a respecter

La doc Futures V3 General Info ajoute plusieurs regles importantes:

- `403`: WAF limit violee;
- `429`: rate limit casse, il faut backoff;
- `418`: IP auto-bannie apres abus de `429`;
- `503`: statut d'execution inconnu, ne pas traiter aveuglement comme echec;
- nonce V3 en microsecondes, ecart max avec server time: `10 secondes`;
- Aster recommande WebSocket pour reduire la pression REST.

Impact:

- nos fetchers doivent continuer a backoff sur `429/5xx`;
- un endpoint qui retourne `403` depuis un host ne veut pas dire que la source
  fonctionnelle est invalide si l'autre host officiel repond;
- si on ajoute plus de probes, preferer all-symbol endpoints et WebSocket plutot
  que spammer symbole par symbole.

### X. Prediction Testnet / Demo: hors scope actuel

La documentation liste aussi Prediction Testnet et Demo.

Impact:

- utile uniquement si on veut tester un produit prediction separe;
- aucune valeur directe pour nos backtests Aster Pro perps actuels;
- a garder documente comme `out_of_scope_product`, pas comme source manquante.

### Y. Error codes Futures V3: mapping utile pour runners longs

La page officielle `futures-v3/error-codes` confirme plusieurs familles
d'erreurs qu'il faut interpreter proprement:

- `-1003 TOO_MANY_REQUESTS`: trop de requetes, il faut privilegier WebSocket ou
  endpoints all-symbol plutot que poller symbole par symbole.
- `-1006 UNEXPECTED_RESP` et `-1007 TIMEOUT`: statut d'execution inconnu. En
  paper/live futur, ne jamais supposer automatiquement que l'action a echoue.
- `-1015 TOO_MANY_ORDERS`: trop de nouveaux ordres.
- `-1112 NO_DEPTH`: pas de profondeur disponible.
- `-1121 BAD_SYMBOL`: symbole invalide ou indisponible.
- `-2016 NO_TRADING_WINDOW`: pas de fenetre de trading trouvee. Tres important
  pour equities, commodities et tout actif avec session.
- `-2018 BALANCE_NOT_SUFFICIENT` / `-2019 MARGIN_NOT_SUFFICIENT`: balance ou
  marge insuffisante.
- `-2027 MAX_LEVERAGE_RATIO` / `-2028 MIN_LEVERAGE_RATIO`: leverage impossible
  avec la taille/marge courante.
- `-4004`, `-4005`, `-4014`, `-4023`: quantite/prix ne respectent pas min/max,
  tick size ou step size.
- `-4016` / `-4024`: prix hors bornes `PERCENT_PRICE` autour du mark price.
- `-4047` / `-4048`: impossible de changer margin type avec ordres ouverts ou
  position ouverte.
- `-4061 POSITION_SIDE_NOT_MATCH`: position side incompatible avec le mode du
  compte.
- `-4082`: taille de batch order invalide.
- `-4088 NO_PLACE_ORDER_PERMISSION`: permission de placement absente.

Impact:

- les backtests equities/macro doivent porter `no_trading_window_risk` tant que
  les sessions ne sont pas modelisees;
- les lanes x10/x20 doivent garder `max_leverage_ratio_risk`;
- le fill model doit simuler `PERCENT_PRICE`, `MIN_NOTIONAL`, `LOT_SIZE`,
  `MARKET_LOT_SIZE`, `tickSize` et `stepSize`;
- en paper trading, un timeout API doit declencher verification du ledger/order
  state, pas une reexecution aveugle.

### Z. ExchangeInfo public: distribution reelle des contraintes symbole

Smoke public du 2026-05-31 via `GET /fapi/v3/exchangeInfo`:

- `symbols_count=453`;
- tous les symboles observes exposent:
  `PRICE_FILTER`, `LOT_SIZE`, `MARKET_LOT_SIZE`, `MAX_NUM_ORDERS`,
  `MAX_NUM_ALGO_ORDERS`, `MIN_NOTIONAL`, `PERCENT_PRICE`;
- distribution `triggerProtect`: `0.0500` sur 282 symboles, `0.1000` sur 127,
  `0.0200` sur 29, puis quelques cas `0.0300`, `0.0600`, `0.0800`,
  `0.1500`, `0.2000`;
- distribution `marketTakeBound`: `0.05` sur 282 symboles, `0.10` sur 128,
  `0.02` sur 29, puis quelques cas `0.03`, `0.06`, `0.08`, `0.15`, `0.20`;
- `liquidationFee`: `0.025000` sur 452 symboles, `0.015000` sur 1 symbole.

Exemples utiles:

- `LABUSDT`: `triggerProtect=0.1000`, `marketTakeBound=0.10`,
  `PERCENT_PRICE=[0.9000, 1.1000]`, `minNotional=5`.
- `WIFUSDT`: `triggerProtect=0.1000`, `marketTakeBound=0.10`.
- `1000SATSUSDT`: `triggerProtect=0.0500`, `marketTakeBound=0.05`.
- `BTCUSDT`: `triggerProtect=0.0200`, `marketTakeBound=0.02`.
- `INTCUSDT`, `MSFTUSDT`, `CRCLUSDT`: `triggerProtect=0.0200`,
  `marketTakeBound=0.02`.
- Cas non standards observes: `AVLUSDT` a `marketTakeBound=0.20`; `MBLUSDT`,
  `TREEUSDT`, `GUAUSDT`, `1000WOJAKUSDT`, `POPMARTUSDT` ont `0.15`;
  `SNDKUSDT` et `MSTRUSDT` sont a `0.03`.

Impact:

- une lane micro-cap crypto peut tolerer des bornes d'execution plus larges
  qu'une lane equity/macro;
- comparer `LABUSDT 5h` et `INTCUSDT 30m` sans `marketTakeBound` /
  `PERCENT_PRICE` est fragile;
- CSV futur a ajouter: `trigger_protect`, `market_take_bound`,
  `percent_price_up`, `percent_price_down`, `min_notional`, `tick_size`,
  `step_size`, `liquidation_fee_rate`;
- les meilleurs ROI doivent etre repasses avec un filtre `exchangeInfo`.

Implementation appliquee le 2026-05-31:

- `aster_perps_model.py` ajoute un cache public `exchangeInfo` all-symbol;
- `backtest_strategy_discovery.py` enrichit les CSV V2 avec:
  `exchange_info_status`, `symbol_status`, `trigger_protect`,
  `market_take_bound`, `percent_price_up`, `percent_price_down`,
  `min_notional`, `tick_size`, `step_size`, `market_step_size`,
  `liquidation_fee_rate`, `exchange_filter_verdict`,
  `exchange_filter_warnings`, `exchange_filter_blockers`;
- smoke `LABUSDT/INTCUSDT`: `LABUSDT` remonte bien `marketTakeBound=0.10`,
  `PERCENT_PRICE=[0.9000, 1.1000]`, `minNotional=5`, verdict `warning`
  a cause de `wide_market_take_bound`.

### AA. Changelog recent: STP, Strategy Orders, Aster Chain

Changelog officiel:

- 2026-05-21: ajout du mode `STP` Futures V3 (`EXPIRE_TAKER`,
  `EXPIRE_MAKER`, `EXPIRE_BOTH`) au niveau compte et ordre.
- 2026-05-22: ajout des `Strategy Orders` Futures V3: `OTO`, `OCO`, `OTOCO`.
  Les endpoints de placement/update ont un poids `50` et sont `TRADE`.
- 2026-05-22: ajout Aster Chain avec account status et transfer signe.
- 2026-05-26: ajout Prediction Testnet, deja classe hors scope actuel.

Decision:

- `STP` est utile plus tard pour eviter self-trade/wash involontaire si on trade
  reellement, mais n'a pas d'effet sur nos backtests read-only actuels;
- `Strategy Orders` pourraient representer OCO/OTOCO natifs pour execution
  future, mais restent interdits maintenant;
- Aster Chain transfer est `WITHDRAW`/signe: documente, mais exclu des runners.

### AB. ExchangeInfo assets et rate limits: dernier morceau public utile

Probe public du 2026-05-31 via `GET /fapi/v3/exchangeInfo`:

- `assets_count=33`;
- tous les assets observes dans le snapshot ont `marginAvailable=true`;
- assets de marge observes: `USDT`, `BTC`, `BNB`, `ETH`, `SOL`, `BUSD`,
  `CAKE`, `USDC`, `VUSDT`, `CUSDT`, `HAY`, `BONUSUSD`, `USDBC`, `LISTA`,
  `LISUSD`, `WBETH`, `SLISBNB`, `STONE`, `RSETH`, `JLP`, `SOLVBTC`,
  `FBTC`, `PUMPBTC`, `USDF`, `USDCE`, `USD1`, `AFEE`, `ASBNB`, `FORM`,
  `CDL`, `ASTER`, `TWT`, `U`;
- `rateLimits` publics observes:
  - `REQUEST_WEIGHT`: `2400` par `1 MINUTE`;
  - `ORDERS`: `1200` par `1 MINUTE`;
  - `ORDERS`: `300` par `10 SECOND`.

Impact:

- pour nos backtests actuels en mode `single_asset` et paper balance USD, on ne
  doit pas simuler multi-collateral automatiquement;
- si un jour on teste multi-asset, `autoAssetExchange` et `marginAvailable`
  devront etre branches explicitement;
- les runners H24 doivent eviter le polling symbole-par-symbole inutile: le budget
  `REQUEST_WEIGHT=2400/min` existe, mais notre politique reste conservatrice.

### AC. Futures account/trading: ce qui reste signe et donc hors backtest

La page Futures Account & Trading contient plusieurs endpoints utiles pour une
future execution verifiee, mais aucun ne doit entrer dans les runners read-only
actuels:

- `GET /fapi/v3/income` (`USER_DATA`, weight `30`): historique income,
  commissions, transfers, funding, etc. Fenetre max `7 jours` si
  `startTime/endTime`.
- `GET /fapi/v3/leverageBracket` (`USER_DATA`): source exacte des notional caps
  et maintenance margin brackets.
- `GET /fapi/v3/adlQuantile` (`USER_DATA`): valeurs `0..4`, mises a jour toutes
  les `30s`, utile pour risque ADL reel.
- `GET /fapi/v3/forceOrders` (`USER_DATA`): liquidations/ADL propres au compte.
- `GET /fapi/v3/commissionRate` (`USER_DATA`, weight `20`): maker/taker reels par
  symbole.
- MMP (`/fapi/v3/mmp`, `/mmpReset`): garde-fou market maker, avec limites
  `qtyLimit`, `valueLimit`, `deltaLimit`, fenetre et freeze.
- `POST /fapi/v3/batchOrders`: max `5` ordres, weight `5`.
- `POST /fapi/v3/placeStrategyOrder`: `OTO`, `OCO`, `OTOCO`, weight `50`.
- sub-account, migrate assets, register/approve agent: surfaces operationnelles
  sensibles, dont `WITHDRAW` pour migration.

Decision:

- ces endpoints deviennent une checklist future `read_only_credentials_policy`;
- aucune signature, aucun API key trading, aucun wallet order maintenant;
- le moteur doit continuer a marquer:
  `commission_rate_source=official_default_or_proxy`,
  `maintenance_margin_source=proxy_until_signed_leverage_bracket_policy`,
  `adl_not_modelled`, `account_income_not_reconciled`.

### AD. Couverture globale actuelle

Etat apres cette passe:

- Market data Futures V3: largement couverte et partiellement branchee
  (`klines`, `markPriceKlines`, `fundingRate`, `exchangeInfo`, `bookTicker`,
  `fundingInfo`, `indexreferences`).
- WebSocket public: suffisamment documente pour preflight (`bookTicker`,
  `depth`, `trade`, `markPrice`, `forceOrder`).
- Spot V3: documente comme produit separe, pas melange aux perps.
- Shield / 1001x / Prediction: documentes comme produits separes ou hors-scope.
- Wallet/account/execution: documente pour plus tard, mais bloque volontairement.

Ce qui manque encore vraiment pour un moteur perps complet:

1. imputation funding par position selon timestamps exacts;
2. fill model `aggTrades/historicalTrades` sur les champions;
3. session model equities/macro;
4. maintenance margin tier exact via `leverageBracket` si policy read-only;
5. reconciliation paper/live via user stream si on passe un jour a execution.

## Ce que le MCP / public market data ne nous donne pas encore

### 1. Parametres d'ordre utiles a simuler, mais pas a executer

La doc Aster liste plusieurs comportements d'ordres qui changent fortement le backtest:

- `MARKET`: execution immediate avec slippage.
- `LIMIT`: controle du prix, mais risque de non-fill.
- `STOP_LIMIT` / `STOP_MARKET`.
- `TRAILING_STOP_MARKET`.
- `POST_ONLY`: maker-only, rejet si l'ordre prend de la liquidite.
- `TP/SL` avec reference `MARK_PRICE` ou `CONTRACT_PRICE`.
- `REDUCE_ONLY`: sortie uniquement, impossible d'augmenter ou retourner la position.
- `BBO`: placement au best bid/offer.
- TIF: `GTC`, `IOC`, `FOK`.
- `GTX`: post-only dans l'API, utilise notamment par les chase/BBO orders.
- `HIDDEN`: present dans `exchangeInfo` / timeInForce pour certains contextes, mais pas prioritaire pour notre moteur.
- `pegPriceType`: BBO peg `COUNTERPARTY_1` ou `QUEUE_1`.
- `pegOffset`: offset signe depuis le BBO.
- `priceLimit`: cap/floor absolu pour les ordres BBO-pegged.
- `stpMode`: self-trade prevention `EXPIRE_TAKER`, `EXPIRE_MAKER`, `EXPIRE_BOTH`.
- `newOrderRespType`: `ACK` ou `RESULT`.

Impact sur notre moteur:

- Nos replays actuels ressemblent surtout a des executions taker/market ou proxy kline.
- Il manque une simulation `maker/post-only` avec probabilite de fill.
- Il manque une comparaison `TP/SL sur mark price` vs `TP/SL sur last price`.
- `reduceOnly` doit devenir une contrainte obligatoire si un jour on simule des exits realistes.

Priorite code:

1. Ajouter un `execution_model` dans les backtests: `taker_market`, `maker_post_only`, `bbo_limit`, `stop_market_mark`, `stop_market_last`.
2. Ajouter un champ `trigger_reference`: `mark_price` ou `last_price`.
3. Ajouter un `fill_status`: `filled`, `partial`, `missed`, `rejected_post_only`.

Etat implementation 2026-05-31:

- `trigger_reference` est disponible (`last_price` / `mark_price`);
- `execution_model` est disponible pour `taker_market`, `maker_post_only`,
  `bbo_limit`;
- les couts changent selon le modele: taker officiel, maker `0 bps`, slippage
  complet/reduit/zero;
- le vrai `fill_status` et la simulation de queue maker restent a faire. Les modes
  maker/BBO doivent etre lus comme proxies de cout, pas comme preuve de fill.

### 1.b Regles API de trigger conditionnel

L'API V3 precise les regles conditionnelles:

- `workingType`: `MARK_PRICE` ou `CONTRACT_PRICE`, defaut `CONTRACT_PRICE`.
- `priceProtect=true`: quand le stop est atteint, l'ecart entre mark price et contract price ne doit pas depasser `triggerProtect` du symbole.
- `triggerProtect` vient de `GET /fapi/v3/exchangeInfo`.
- `STOP` / `STOP_MARKET`:
  - BUY: le prix de reference doit etre `>= stopPrice`;
  - SELL: le prix de reference doit etre `<= stopPrice`.
- `TAKE_PROFIT` / `TAKE_PROFIT_MARKET`:
  - BUY: le prix de reference doit etre `<= stopPrice`;
  - SELL: le prix de reference doit etre `>= stopPrice`.
- `TRAILING_STOP_MARKET`:
  - `callbackRate` min `0.1`, max `5` selon New Order;
  - certaines sections Query/Cancel affichent max `4`, donc a traiter comme doc drift;
  - BUY: le plus bas apres placement doit etre `<= activationPrice`, puis dernier prix `>= low * (1 + callbackRate)`;
  - SELL: le plus haut apres placement doit etre `>= activationPrice`, puis dernier prix `<= high * (1 - callbackRate)`;
  - erreur `-2021 Order would immediately trigger` si activation invalide.

Impact:

- Notre trailing stop actuel est une approximation proche mais pas exacte.
- Il faut stocker `workingType`, `priceProtect` et `triggerProtect` dans les futurs backtests.
- Pour simuler des TP/SL realistes, on doit tester au moins deux variantes: `stop_market_last` et `stop_market_mark`.

### 1.c Chase / BBO orders

L'API expose `POST /fapi/v3/chase`:

- Ordre strategie BBO-pegged, post-only `GTX`.
- Re-peg automatique vers le top of book.
- BUY: prix = `bid1 - chaseOffset`.
- SELL: prix = `ask1 + chaseOffset`.
- `maxChaseOffset` annule si le marche s'eloigne trop.
- `priceLimit` empeche de chase au-dela d'un prix.
- Le service peut auto-cancel avec `OFFSET_CANCELLED`.

Impact:

- C'est potentiellement le meilleur modele pour une simulation maker/post-only.
- Mais pour le moment c'est `TRADE`; donc interdit en execution reelle.
- En backtest, on peut seulement simuler un `chase_maker_proxy` base sur depth/BBO.

### 2. Fees reels differents de nos proxies

La doc indique:

- USDT perps: maker `0%`, taker `0.04%`.
- USD1 perps: maker `0%`, taker `0.005%`.
- Les fees sont calculees sur le notional: `contracts * transaction price`.
- Le paiement en ASTER peut reduire les frais de 5%, mais il ne faut pas l'utiliser dans nos hypotheses par defaut.

Impact sur notre moteur:

- Notre proxy historique `fee_bps=6` est trop conservateur pour taker USDT (`4 bps`) et tres faux pour USD1 (`0.5 bps`).
- Les strategies maker/post-only peuvent devenir beaucoup plus fortes car maker fee = 0%, mais seulement si on simule correctement les non-fills.

Priorite code:

1. ~~Remplacer le fee proxy global par `fee_model`.~~ Fait dans
   `aster_perps_model.py` et applique au replay discovery quand `fee_bps` est omis:
   - `USDT_taker_bps=4.0`;
   - `USD1_taker_bps=0.5`;
   - `maker_bps=0.0`;
   - option `aster_fee_discount=false` par defaut.
2. Ajouter `quote_asset` depuis `exchangeInfo` pour choisir USDT vs USD1. Premiere
   version faite par suffixe symbole (`USDT` / `USD1`); enrichissement exchangeInfo
   reste utile plus tard pour les cas non standards.

### 3. Funding plus important que notre approximation

La doc funding precise:

- Longs payent les shorts quand le contrat est au-dessus du mark price.
- Shorts payent les longs quand le contrat est sous le mark price.
- Le funding peut avoir un decalage d'environ 15 secondes autour de l'heure de charge.
- La formule depend du premium index et de l'intervalle de funding `N`.
- En volatilite extreme, le floor/cap/intervalle peut changer.

Impact sur notre moteur:

- Notre proxy `1 bps / 8h` est insuffisant.
- Les backtests multi-heures (`3h`, `5h`, `6h`) doivent appliquer funding selon les timestamps reels de tenue.
- Un trade ouvert juste avant funding peut changer de resultat net.

Priorite code:

1. ~~Utiliser l'historique public funding par symbole.~~ Fait dans
   `aster_perps_model.py` via `GET /fapi/v3/fundingRate`.
2. Calculer `funding_paid_usd` / `funding_received_usd` par position selon side
   et temps de holding. Premiere version faite au niveau scenario perps avec
   cout/credit signe par side; precision par position encore a raffiner.
3. Ajouter un flag `funding_boundary_risk` si l'entree est proche d'une heure de funding.

Etat implementation 2026-05-31:

- le discovery recupere un snapshot funding public par symbole avec cache local;
- les CSV v2 exposent `funding_source`, `funding_status`,
  `funding_avg_bps_per_8h`, `funding_cost_usd_estimate`;
- fallback propre si Aster retourne 403/429/timeout;
- aucun endpoint signe, aucun wallet, aucun trade.

### 4. Liquidation et maintenance margin: il faut le mark price

La doc liquidation indique:

- La liquidation est declenchee quand `Margin < Maintenance margin`.
- Aster utilise le `Mark Price` pour rendre les liquidations plus justes et limiter la manipulation.
- Les positions cross hedge peuvent partager le meme liquidation price; en isolated, long/short ont des liquidations separees.
- Les maintenance margins dependent de tiers de taille positionnelle.

Impact sur notre moteur:

- Le filtre mark/index ajoute le bon premier garde-fou, mais il ne suffit pas.
- Notre liquidation proxy doit utiliser mark price, pas last price.
- Le moteur doit simuler `isolated` par defaut pour etre prudent.

Priorite code:

1. Deplacer la liquidation proxy vers `markPriceKlines`. Premiere etape faite:
   `backtest_strategy_discovery.py` accepte `--trigger-reference mark_price`
   et le replay peut utiliser les closes de `markPriceKlines` pour comparer les
   lanes last-price vs mark-price.
2. Ajouter `maintenance_margin_tier_source`: `proxy`, puis `signed_leverageBracket` plus tard.
3. Ajouter un `liquidation_distance_min_pct` dans tous les rapports.

### 4.b Mark price: formule et protections

La doc mark price indique que le mark price est la mediane de trois references:

- price index ajuste par funding/time-to-next-funding;
- price index + moving average 5 minutes;
- contract price.

Autres protections:

- Le price index vient de plusieurs grandes sources spot ponderees par volume.
- Si une source externe diverge trop, son poids peut etre mis a zero.
- Certaines docs mentionnent une protection sur last trade si la derniere transaction diverge de plus de 5% du mark price et qu'aucun nouveau trade n'arrive dans les 5 secondes.

Impact:

- Le mark price n'est pas juste un autre ticker: c'est la reference centrale de risque.
- Notre filtre mark/index est donc une validation structurelle, pas un gadget.
- Les strategies qui ne tiennent qu'au last price doivent rester `watch` ou `rejected`.

### 5. Margin modes et position modes

La doc indique:

- Cross margin: marge partagee entre positions.
- Isolated margin: marge par position.
- Le mode marge ne peut pas etre change apres ouverture d'une position ou ordre.
- Single-asset: USDT only, PnL individuel.
- Multi-asset: collateral partage, PnL nettee, conversions automatiques internes.
- Hedge mode: long et short simultanes sur le meme contrat.
- One-way: une seule direction par contrat.

Impact sur notre moteur:

- Nos backtests doivent rester en `isolated + single_asset + one_way` par defaut.
- Les resultats multi-strategies ne doivent pas netter les PnL comme si on etait en multi-asset/cross.
- Si on teste hedge mode, il faut un moteur separe car long et short simultanes changent les liquidations.

Priorite code:

1. Ajouter dans chaque report: `assumed_margin_mode=isolated`, `assumed_asset_mode=single_asset`, `assumed_position_mode=one_way`.
2. Interdire la comparaison directe avec un futur mode cross/multi-asset sans label clair.

### 6. Endpoints signes qui existent mais restent bloques

La doc API Futures V3 expose:

- `POST /fapi/v3/order` pour new order.
- `POST /fapi/v3/leverage`.
- `POST /fapi/v3/marginType`.
- `GET /fapi/v3/leverageBracket`.
- `GET /fapi/v3/commissionRate`.
- balance, positions, income, ADL, force orders, user data.

Decision:

- `TRADE` reste bloque.
- `TRANSFER` reste bloque.
- `USER_DATA` reste bloque jusqu'a une policy credentials read-only/testnet.
- Les seuls elements qui peuvent nous aider maintenant sans credentials sont les docs elles-memes + public market data.

### 7. Exchange filters publics utiles maintenant

`GET /fapi/v3/exchangeInfo` fournit plusieurs champs directement utiles:

- `status`: doit etre `TRADING`.
- `triggerProtect`: seuil max entre mark et contract price pour `priceProtect`.
- `PRICE_FILTER`: `minPrice`, `maxPrice`, `tickSize`.
- `LOT_SIZE`: `minQty`, `maxQty`, `stepSize`.
- `MARKET_LOT_SIZE`: limites propres aux market orders.
- `MIN_NOTIONAL`: notional minimum.
- `PERCENT_PRICE`: `multiplierUp`, `multiplierDown`.
- `MAX_NUM_ORDERS`, `MAX_NUM_ALGO_ORDERS`.
- `OrderType`: types d'ordres supportes par le symbole.
- `timeInForce`: TIF supportes, dont `GTC`, `IOC`, `FOK`, `GTX`, parfois `HIDDEN`.
- `liquidationFee`.
- `marketTakeBound`: ecart max depuis le mark price pour market order.

Impact:

- Reality check enrichi le 2026-05-31 avec `triggerProtect`, `marketTakeBound`, `minNotional`, `tickSize`, `stepSize`, `MARKET_LOT_SIZE`, `PERCENT_PRICE`, `orderTypes` et `timeInForce`.
- Les backtests doivent marquer un trade comme `order_would_be_rejected` si stop/limit/market viole ces filtres.
- Le CSV `paper_trading_reality_checked_backtest.csv` expose maintenant ces champs pour eviter de promouvoir une lane qui serait impossible a executer proprement sur Aster.

### 8. Donnees utiles mais pas prioritaires maintenant

- Hidden orders: interessant pour execution pro, mais impossible a valider sans carnet/fills reels; pas prioritaire.
- Scaled orders: utile pour execution de grosse taille, mais notre paper balance `1000 USD` ne justifie pas ce niveau de complexite.
- TWAP/Grid: strategies execution/automation, pas des signaux; a documenter mais pas brancher maintenant.
- Sub-account, migrate assets, transfers: hors scope et bloque.
- MMP / market maker protection: reserve market makers; pas utile au backtest retail.
- Account/order user data stream: utile plus tard si compte read-only/testnet; bloque maintenant.

### 9. Donnees speciales equities/stocks

La doc stock perpetuals ajoute des contraintes importantes:

- Jusqu'a `10x` leverage pour stock perps.
- Durant pre-market/post-market/market-close/off-hours, les ordres trop agressifs de plus de `2%` vs mark price peuvent etre rejetes.
- Les market orders peuvent remplir jusqu'a `2%` plus agressif que mark price, le reste peut etre annule.
- Aster peut ajuster funding, tick size, leverage max, risk limits et maintenance margin selon conditions.

Impact:

- Nos runners equities ne doivent pas etre compares aux cryptos sans filtre session.
- Il faut ajouter un champ futur `asset_class`: `crypto`, `stock_perp`, `commodity_perp`.
- Pour equities, un backtest devrait savoir si la bougie tombe en market open, pre-market, post-market ou close/off-hours.
- Tant qu'on ne simule pas ces sessions, les resultats equities restent `research_only`.

## Ce qu'on doit faire maintenant

Priorite actuelle pour de meilleurs backtests:

1. **Validation fine des top lanes**: ajouter une passe `aggTrades`/`historicalTrades`
   sur les champions, car les klines 60j restent un proxy.
2. **Fill model maker/BBO**: transformer `maker_post_only` et `bbo_limit` en vrai
   modele de fill/miss/reject, pas seulement un cout reduit.
3. **Funding par position**: appliquer le funding selon les timestamps reels de
   chaque trade ferme, pas seulement une estimation moyenne par symbole.
4. **Session filters equities/commodities**: ne pas lire les actions/commodities
   comme les cryptos 24/7 sans filtrer les heures actives.
5. **Read-only/testnet credentials policy**: preparer plus tard, uniquement pour
   lire `leverageBracket`, `commissionRate`, positions et user stream. Aucun trade.

Ce qu'il ne faut pas faire maintenant:

- Ne pas brancher `POST /fapi/v3/order`.
- Ne pas connecter Phantom/private key au moteur de backtest.
- Ne pas configurer API key trading.
- Ne pas simuler cross/multi-asset sans moteur dedie.
- Ne pas utiliser `placeStrategyOrder`, `chase`, `mmp` ou `listenKey` hors policy
  credentials explicite.

## Decision operationnelle

Avant de chercher plus de strategies, le moteur doit devenir plus proche d'Aster:

- frais reels;
- funding reel;
- liquidation mark-price;
- execution model explicite;
- assumptions marge/position visibles.

Une strategie qui reste profitable apres ces quatre filtres vaut beaucoup plus qu'une strategie brute avec gros ROI.

## Implementation appliquee le 2026-05-31

Module ajoute:

`backend/services/onchain/aster/aster_perps_model.py`

Branchements:

- `backtest_strategy_discovery.py` utilise maintenant un modele de frais issu de la doc officielle:
  - USDT taker `4.0` bps;
  - USD1 taker `0.5` bps;
  - maker `0.0` bps;
  - pas de discount ASTER par defaut.
- Les scenarios perps soustraient maintenant une estimation de frais round-trip en plus du proxy funding.
- Les CSV V2 ajoutent:
  - `effective_fee_bps`;
  - `round_trip_fee_usd_estimate`;
  - `assumed_margin_mode`;
  - `assumed_asset_mode`;
  - `assumed_position_mode`;
  - `assumed_execution_model`;
  - `assumed_trigger_reference`;
  - `perps_assumptions_json`.
- Le rapport consolide HTML lit `effective_fee_bps`.

Limites restantes mises a jour:

- le funding public est integre par symbole, mais pas encore impute exactement
  position par position selon les heures de funding traversees;
- les brackets de maintenance margin restent proxy jusqu'a politique credentials
  read-only/testnet;
- `maker_post_only` et `bbo_limit` existent, mais restent des proxies de cout
  sans vraie simulation de queue/non-fill;
- `trigger_reference=mark_price` existe, mais l'exact margin engine Aster n'est
  pas reproduit;
- le WebSocket public est branche au preflight, mais le user-data stream signe
  reste bloque.

