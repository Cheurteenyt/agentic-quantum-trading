# Aster MCP - Plan de Setup Controle

Date: 2026-05-31  
Statut: plan de preparation, pas encore branche au trading reel.

## Objectif

Le repo `asterdex/aster-mcp` peut nous servir a remplacer une partie de nos hypotheses proxy par des donnees Aster plus proches du reel:

- funding rate et funding info;
- leverage brackets;
- commissions;
- exchange info;
- order book;
- klines;
- positions et balances en lecture seule si une cle read-only est configuree plus tard.

Le MCP expose aussi des outils dangereux comme creation/cancel d'ordre, changement de levier, changement de margin mode et transferts. Notre integration doit donc commencer en mode read-only strict.

## Decision

On ne connecte pas l'agent directement au MCP brut.

Architecture cible:

1. Aster MCP installe dans un environnement isole.
2. Wrapper local `read-only` cote Core Equity.
3. Le moteur backtest/paper consomme seulement les donnees autorisees.
4. Aucun ordre reel, aucun transfert, aucun changement de levier depuis l'agent.

## Installation isolee recommandee

Ne pas installer dans l'environnement backend principal.

```powershell
Set-Location D:\trading-agent
New-Item -ItemType Directory -Force external
git clone https://github.com/asterdex/aster-mcp external\aster-mcp

py -3.11 -m venv external\aster-mcp\.venv
external\aster-mcp\.venv\Scripts\python -m pip install -e external\aster-mcp
```

Tests de base:

```powershell
external\aster-mcp\.venv\Scripts\aster-mcp --help
external\aster-mcp\.venv\Scripts\aster-mcp list
```

Demarrage MCP:

```powershell
external\aster-mcp\.venv\Scripts\aster-mcp start
```

Ou en stdio pour un client MCP:

```powershell
external\aster-mcp\.venv\Scripts\python -m aster_mcp.simple_server
```

## Politique de securite

Interdit tant que le paper-trading n'a pas prouve une robustesse suffisante:

- `create_order`;
- `create_spot_order`;
- `cancel_order`;
- `cancel_all_orders`;
- `set_leverage`;
- `set_margin_mode`;
- `transfer_funds`;
- `transfer_spot_futures`;
- toute cle API avec permission trading;
- toute private key wallet dans le MCP.

Autorise pour la phase d'avance:

- `ping`;
- `get_server_info`;
- `get_exchange_info`;
- `get_ticker`;
- `get_order_book`;
- `get_klines`;
- `get_funding_rate`;
- `get_funding_info`;
- `get_leverage_bracket`;
- `get_commission_rate`;
- equivalents spot read-only.

## Integration Core Equity prevue

Module cree:

`backend/services/onchain/aster/aster_mcp_market_data_adapter.py`

Responsabilite:

- appeler uniquement les outils read-only;
- normaliser les champs utiles au moteur perps;
- alimenter les backtests avec:
  - maintenance margin / leverage bracket reel;
  - funding observe;
  - frais reels;
  - exchange filters;
  - mark/index price si disponible;
- ne jamais exposer de fonction ordre/transfer.

Endpoint admin cree:

`/api/onchain/rpc/aster-mcp-market-data-adapter-preview`

Statut de validation:

- `py_compile` OK sur le module et `backend/routers/onchain.py`;
- smoke reel read-only sur `BTCUSDT` et `INJUSDT` OK;
- endpoints publics V3 testes: `exchangeInfo`, `ticker/24hr`, `depth`, `klines`, `markPriceKlines`, `indexPriceKlines`, `premiumIndex`, `fundingRate`, `fundingInfo`, `indexreferences`;
- aucun credential, aucun wallet, aucun write, aucun ordre.

Exemple de smoke local sans lancer le serveur:

```powershell
Set-Location D:\trading-agent\backend
@'
from services.onchain.aster.aster_mcp_market_data_adapter import get_aster_mcp_market_data_adapter_preview
r = get_aster_mcp_market_data_adapter_preview(
    symbols="BTCUSDT",
    max_symbols=1,
    kline_limit=5,
    funding_limit=5,
    depth_limit=5,
)
print(r["adapter_status"], r["safety"], r["market_data"][0]["endpoint_status"])
'@ | python -
```

Resultat attendu:

- `adapter_status = ok` si Aster repond;
- endpoints `ticker`, `depth`, `klines`, `mark_price_klines`, `index_price_klines`, `premium_index`, `funding`, `funding_info`, `index_references` a `ok`;
- `would_write = false`;
- `would_execute_trade = false`;
- `would_send_wallet_transaction = false`;
- `would_store_credentials = false`.

Notes importantes:

- `indexPriceKlines` utilise le parametre `pair`, pas `symbol`;
- `leverageBracket` et `commissionRate` sont `USER_DATA`, donc non appeles dans cette preview publique;
- ces deux derniers resteront bloques tant qu'on n'a pas une politique credentials read-only explicite.

## Capability audit MCP

Module ajoute:

`backend/services/onchain/aster/aster_mcp_capability_audit.py`

Endpoint admin:

`/api/onchain/rpc/aster-mcp-capability-audit-preview`

Rapport local:

`docs/aster-mcp-capability-audit.md`

Role:

- clarifier ce qu'Aster/MCP peut nous apporter maintenant sans credential;
- separer les capacites publiques deja integrees, les capacites publiques non integrees, les endpoints `USER_DATA` signes et les actions trade/transfer bloquees;
- eviter de melanger recherche de donnees, wallet, execution et backtests.

Conclusion operationnelle:

- **a faire maintenant sans credential**: replay `markPriceKlines` / `indexPriceKlines`, filtre premium mark-index, funding public reel, WebSocket public read-only;
- **a reporter**: `leverageBracket`, `commissionRate`, balances, positions, user data stream, car ils demandent une politique credentials read-only/testnet;
- **a bloquer**: create/cancel order, leverage/margin write, transfers.

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_mcp_capability_audit
```

## Filtre mark/index replay

Module ajoute:

`backend/services/onchain/aster/aster_mark_index_replay_filter.py`

Endpoint admin:

`/api/onchain/rpc/aster-mark-index-replay-filter-preview`

Role:

- verifier que les champions de backtest ne viennent pas uniquement d'un last-price de perp trop eloigne du mark/index;
- comparer `klines`, `markPriceKlines` et `indexPriceKlines` sur les memes timeframes;
- utiliser le p95 de divergence pour distinguer une meche isolee d'une divergence persistante.

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.aster_mark_index_replay_filter
```

Premier snapshot complet:

- `24` combinaisons symbole/timeframe testees;
- `2` confirmees, `14` watch, `8` rejetees;
- `CRCLUSDT 5h/3h` confirme;
- `LABUSDT`, `INJUSDT`, `INTCUSDT` en watch car divergence single-candle mais pas persistante;
- `BOMEUSDT` et `TIAUSDT` rejetes sur cet echantillon car divergence mark/index persistante.

## Reality check perps read-only

Endpoint ajoute:

`/api/onchain/rpc/aster-perps-reality-check-preview`

Objectif:

- ne pas chercher une nouvelle strategie;
- filtrer la qualite reelle des symboles avant de promouvoir une lane de backtest;
- eviter les faux bons resultats dus a un marche trop fin, un spread large, une divergence mark/index ou un funding anormal.

Le diagnostic combine:

- statut `TRADING` depuis `exchangeInfo`;
- filtres d'execution `triggerProtect`, `marketTakeBound`, `minNotional`, `tickSize`, `stepSize`, `MARKET_LOT_SIZE`, `PERCENT_PRICE`;
- types d'ordres et `timeInForce` supportes par symbole;
- volume 24h quote;
- volume et nombre de trades sur la fenetre kline;
- spread et top-10 depth;
- premium mark/index en bps;
- divergence mark/index sur klines;
- funding recent et funding config;
- nombre de references d'index.

Verdicts:

- `backtest_quality_ok`: lane eligible pour un runner reality-checked;
- `backtest_quality_watch`: continuer a tester, mais ne pas promouvoir sans prudence;
- `backtest_quality_risky`: review manuelle avant toute promotion.

Smoke du 2026-05-31:

- `LABUSDT`: `backtest_quality_watch`, score qualite `79`, filtres d'execution presents (`triggerProtect=0.1`, `marketTakeBound=0.1`, `minNotional=5`);
- `INJUSDT`: `backtest_quality_watch`, score qualite `72`, filtres d'execution presents (`triggerProtect=0.05`, `marketTakeBound=0.05`, `minNotional=5`);
- `INTCUSDT`: `backtest_quality_watch`, score qualite `61`, volume 24h faible;
- `CRCLUSDT`: `backtest_quality_watch`, score qualite `61`, volume 24h faible.

## Runner reality-checked

Script ajoute:

`backend/services/onchain/aster/backtest_reality_checked.py`

Principe:

1. lancer le discovery existant sans modifier sa logique;
2. prendre les meilleurs candidats;
3. appeler le reality check public Aster V3;
4. garder seulement les lanes qui passent le filtre qualite;
5. ecrire des artefacts separes pour ne pas polluer les runners existants.

Artefacts:

- `paper_trading_reality_checked_backtest.csv`;
- `paper_trading_reality_checked_backtest_latest.json`;
- `paper_trading_reality_checked_heartbeat.json`.

Smoke valide:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.backtest_reality_checked `
  --symbols LABUSDT,INJUSDT `
  --groups low `
  --lookback-days 7 `
  --windows 1 `
  --min-closed-trades 2 `
  --top-n-per-batch 5 `
  --top-n-global 10 `
  --batch-size 2 `
  --output-tag smoke_reality `
  --min-quality-score 70 `
  --allowed-quality-verdicts backtest_quality_ok,backtest_quality_watch `
  --kline-limit 10
```

Usage H24 recommande:

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

Version plus permissive pour exploration:

```powershell
python -m services.onchain.aster.backtest_reality_checked `
  --symbol-preset all `
  --output-tag all_reality_watch `
  --groups both `
  --run-forever `
  --sleep-seconds 1800 `
  --search-mode exploration `
  --min-quality-score 65 `
  --allowed-quality-verdicts backtest_quality_ok,backtest_quality_watch
```

## Ameliorations recommandees apres lecture de la documentation Aster

La documentation officielle Aster indique que `V3` est la voie recommandee pour les nouvelles integrations, alors que `V1` ne supporte plus la creation de nouvelles API keys depuis le 2026-03-25. Le MCP supporte encore `HMAC` et `V3`, mais notre integration Core Equity doit privilegier un chemin compatible V3.

### 1. Wrapper read-only avec allowlist dure

Le MCP expose des outils utiles et dangereux dans le meme serveur. Avant de l'utiliser dans Core Equity, creer un wrapper local qui refuse tout outil hors allowlist.

Autoriser:

- `ping`
- `get_server_info`
- `get_exchange_info`
- `get_ticker`
- `get_order_book`
- `get_klines`
- `get_funding_rate`
- `get_funding_info`
- `get_leverage_bracket`
- `get_commission_rate`
- `get_balance` read-only seulement si compte dedie
- `get_positions` read-only seulement si compte dedie

Bloquer:

- `create_order`
- `create_spot_order`
- `cancel_order`
- `cancel_all_orders`
- `set_leverage`
- `set_margin_mode`
- `transfer_funds`
- `transfer_spot_futures`
- toute route `TRADE` ou `WITHDRAW`

### 2. Market data adapter plus riche que le MCP brut

Le wrapper ne doit pas seulement relayer les reponses. Il doit normaliser les donnees utiles a nos backtests:

- `exchangeInfo`: tick size, step size, min notional, percent price, market take bound, liquidation fee;
- `klines`: OHLCV, quote volume, taker buy base/quote volume, number of trades;
- `markPriceKlines`: historique mark price pour eviter de backtester seulement sur last price;
- `indexPriceKlines`: index price pour mesurer premium/perp divergence;
- `premiumIndex`: mark price, index price, last funding rate, next funding time;
- `fundingRate`: historique funding pour remplacer notre funding proxy;
- `leverageBracket`: initial leverage max, notional floor/cap, maintenance margin ratio, cum;
- `commissionRate`: maker/taker reels par symbole.

### 3. Remplacer notre proxy perps par des donnees Aster

Aujourd'hui `backtest_strategy_discovery.py` utilise:

- maintenance margin proxy `0.5%`;
- funding proxy `1 bps / 8h`;
- liquidation estimee approximative.

Avec Aster MCP + API V3, on doit remplacer progressivement:

- maintenance margin par `maintMarginRatio` depuis `leverageBracket`;
- funding par `fundingRate` / `premiumIndex`;
- fees par `commissionRate`;
- contraintes d'ordre par `exchangeInfo` filters;
- validation de prix par mark price + `PERCENT_PRICE`.

### 4. Gestion rate-limit stricte

La doc Aster precise:

- `429`: rate limit;
- `418`: IP auto-bannie apres violations repetees;
- `403`: WAF limit;
- `503`: statut d'execution inconnu pour certains appels, a ne pas traiter comme un simple echec.

Notre adapter doit donc:

- lire les headers `X-MBX-USED-WEIGHT-*` quand disponibles;
- garder un budget local par minute;
- backoff exponentiel sur `429`;
- circuit breaker temporaire sur `418`;
- ne jamais retry en boucle;
- journaliser `api_status=degraded` plutot que casser un backtest.

### 5. Support WebSocket read-only

La doc recommande les WebSocket pour reduire la pression REST. A terme, le wrapper devrait permettre:

- market streams publics;
- mark price stream;
- book ticker stream;
- kline stream;
- liquidation stream read-only si disponible;
- local order book reconstruit proprement avec controle sequence/update id.

Pour l'instant, ne pas brancher de user stream tant qu'on n'a pas de compte dedie et de wrapper strict.

### 6. V3 signer hygiene

V3 utilise:

- `user`: adresse main wallet;
- `signer`: API wallet / agent;
- `nonce`: timestamp microsecondes;
- `signature`: signee par la private key du signer.

Risques documentes:

- confusion millisecondes / microsecondes;
- mauvais tri des parametres;
- nonce reutilise;
- signer private key confondue avec private key du wallet principal.

Regles Core Equity:

- jamais la private key Phantom principale;
- signer dedie uniquement;
- nonce monotone centralise si on utilise V3;
- aucune route `TRADE` avant decision explicite future;
- testnet ou read-only d'abord.

### 7. Testnet avant compte reel

La doc Aster fournit aussi des endpoints testnet. Avant toute lecture account en production:

- installer le MCP en local isole;
- tester public market data sans credentials;
- tester V3 signer sur testnet si possible;
- valider que le wrapper bloque les routes dangereuses;
- seulement ensuite envisager une API key read-only production.

## Impact sur le moteur perps

Aujourd'hui, `backtest_strategy_discovery.py` contient une couche proxy:

- maintenance margin par defaut: `0.5%`;
- funding proxy: `1 bps / 8h`;
- liquidation estimee par levier;
- rejet de leviers si liquidation avant stop.

Avec Aster MCP, l'objectif n'est pas de trader plus vite. L'objectif est de rendre ce proxy plus proche du reel:

- remplacer `DEFAULT_MAINTENANCE_MARGIN_RATE` par les brackets Aster;
- remplacer `DEFAULT_FUNDING_BPS_PER_8H` par le funding historique/recent;
- verifier les frais avec `get_commission_rate`;
- eviter de promouvoir des lanes qui sont bonnes en proxy mais mauvaises apres funding/frais/liquidation.

## Checklist avant activation

- MCP installe dans `external/aster-mcp`, jamais dans le backend principal.
- Aucune cle trading configuree.
- Si une cle est necessaire, read-only uniquement.
- Pour un wallet Phantom, suivre `docs/aster-mcp-phantom-wallet-setup.md`: Phantom signe dans Aster UI, le MCP ne doit jamais recevoir la seed ou la private key principale Phantom.
- Wrapper Core Equity read-only cree.
- Tests read-only valides sur BTCUSDT, LABUSDT, INJUSDT.
- RAG mis a jour.
- Aucun endpoint de trade expose.

## References

- GitHub: `https://github.com/asterdex/aster-mcp`
- Docs officielles Aster Futures V3 market data: `https://asterdex.github.io/aster-api-website/futures-v3/market-data/`
- Docs officielles Aster Perpetuals API/WebSocket: `https://docs.asterdex.com/product/aster-perpetuals/api/api-documentation`
- Guide integration: `https://raw.githubusercontent.com/asterdex/aster-mcp/main/docs/Aster-MCP-External-Integration.md`
- Wallet Phantom / Aster: `docs/aster-mcp-phantom-wallet-setup.md`
