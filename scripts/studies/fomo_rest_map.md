# CARTE REST FOMO — surfaces DOM du worker → endpoints prod-api (29/09, soir)

Méthode : sniffing passif CDP (listeners sur la page résidente du worker,
`scripts/studies/fomo_rest_map_probe.py --sniff`, 4 runs 20:28→21:09) puis
replay python pur curl_cffi chrome131 (JWT jwt_cache.json, pacing 1,2 s).
Preuves brutes : `reports/fomo_rest_map_capture.json` (76 URLs + verdicts).
Une page fomo NEUVE concurrente ne rend pas l'app (« Try again » puis blanc) :
seul le sniffing passif était viable pendant que le worker est résident.

## Table surface → endpoint → verdict (replay = 200 en python pur sauf mention)

| Surface worker | Endpoint(s) prod-api exacts | Verdict replay | Sort de la surface |
|---|---|---|---|
| do_sidebar (trending) | POST /proxy/trendingTokens `{}` (50 tokens) ; GET /proxy/verifiedTokens (219-452 tokens) | 200 | **MOURT** |
| do_most_held (clic timeout 6000 ms) | aucun XHR dédié (4 runs de sniff) — onglet alimenté par WS/tri client | n/a | **MOURT** (REST : verifiedTokens tri `holders` ; le clic DOM est mort de lui-même) |
| walker trending | POST /proxy/trendingTokens | 200 | **MOURT** |
| walker bonding | WS topic `pre_graduated_tokens` ; REST snapshot : trendingTokens/verifiedTokens `launchpad.graduationPercent<100` | 200 (snapshot) | **HYBRIDE** (live=WS déjà écouté par fomo-ws-signals ; snapshot=REST) |
| walker graduated | WS topic `graduated_tokens` ; REST idem bonding | 200 (snapshot) | **HYBRIDE** (DOM parse « 0 entrées » constaté 2×) |
| walker alerts | GET /feed/tradingActivity?limit=50&threshold=1000 (+WS trading_activity) | 200 | **HYBRIDE** (probable — à confirmer en comparant 12 entrées DOM vs items REST) |
| walker leaderboard | GET /v2/leaderboard/24h ; GET /v2/leaderboard?window=7d | 200 | **MOURT** (DOM « 0 entrées » constaté) |
| do_top100 (all-time) | **GET /v2/leaderboard?window=alltime&limit=100** → 100 lignes totalPnL/totalVolume/numTrades/swapCount/topHoldings/clan | 200 | **MOURT** (endpoint découvert par sonde, jamais vu en DOM) |
| do_session | POST /v2/users, GET /config (bootstrap session) | 200 | reste DOM/JWT-cache (pas de la donnée) |
| do_holders (page token) | GET /hodlers/top?tokens=[{"address","networkId"}…] (JSON URL-encodé) ; GET /hodlers/devs?tokenAddress=&networkId= ; POST /hodlers/friends `{tokens:[…]}` ; POST /proxy/tokenDetails `{tokenId:"mint:networkId"}` ; POST /proxy/tokenWarnings `{address,networkId}` | 200 | **MOURT** |
| do_theses | GET /feed/token/thesis?tokenAddress=&networkId=&threshold= ; GET /feed/token/sortedThesis?…&afterTime=&limit=500&beforeTime= (curseur temporel) | 200 | **MOURT** |
| do_clans (/clans) | GET /v2/clans/leaderboard?window=24h&limit=50 | 200 | **MOURT** (innerText DOM = 51 chars : ne capture déjà rien) |
| do_feed (/feed) | GET /feed/tradingActivity?limit=50&threshold=1000 → {items, hasNextPage} | 200 | **MOURT** (innerText DOM = 51 chars) |
| do_profiles (positions+top trades) | GET /v2/users/<uuid> ; /v2/users/<uuid>/balances ; /v2/users/<uuid>/leaderboard ; GET /v2/userTokens/aggregatedSnapshotById?userId=&snapshotId= ; GET /trades?userId=&orderBy=closedAt(&tokenAddress=) ; GET /v2/users/<uuid>/swaps(&tokenAddress=) | 200 | **MOURT** |
| header/About (launchpad/supply/created/contract) | POST /proxy/filterTokens avec body = **tableau de chaînes** ["mint:networkId",…] → token{address,totalSupply,socialLinks}, launchpad{launchpadName,graduationPercent}, createdAt. Idem trendingTokens/verifiedTokens | 200 | **MOURT** — tokenDetails NE donne PAS le About (27 clés = activité buy/sell/holders/top10 seulement) |
| swap_history | GET /v2/users/<uuid>/swaps?limit=100&lastSwapId= (validé 29/09) ; variante &tokenAddress= | 200 | **MOURT** |

Paramètres clés vérifiés : `networkId` (1399811149=solana, 4663=evm test) ;
thesis threshold=1000 ; sortedThesis curseurs afterTime/beforeTime/limit/userId ;
hodlers/top accepte un batch de tokens.

## Surprises

1. **Les onglets hero (Trending/Bonding/Graduated/Most held) n'émettent pas d'XHR**
   : alimentés par WS (topics `trending_tokens`, `pre_graduated_tokens`,
   `graduated_tokens` — 2614/195/2532 frames vues dans le résumé du worker).
   Le REST ne donne que le snapshot ; le live reste le WS déjà exploité.
2. **filterTokens ≠ tokenDetails** : filterTokens (POST batch) porte le About
   complet (supply/launchpad/contract/socials/created) ; tokenDetails ne porte
   QUE l'activité de trading. Le collector qui cherchait le supply côté
   tokenDetails ne le trouvera jamais.
3. **Le DOM du worker est déjà à moitié mort** : clans/feed = 51 chars,
   bonding/leaderboard = 0 entrées, most_held = clic qui timeout — pendant ce
   temps chaque page token déclenche ~10 XHR rejouables 200. De plus, ouvrir
   une 2e page fomo concurrente fait « Try again »/blanc et a coïncidé avec un
   crash du worker (`page irécupérable` 20:30:42, restart fomo-browser 20:31:48)
   : ne jamais sonder en créant des pages pendant que le worker tourne.
4. Endpoints découverts hors liste couverte : `/v2/leaderboard?window=alltime|7d`,
   `/hodlers/friends` (POST), `/feed/tradingActivity`, `/proxy/verifiedTokens`,
   `/tokenAllowList/detailed`, `/watchlist`, POST `/proxy/tokenWarnings`.

## Ordre d'attaque proposé (tuer les surfaces DOM)

1. **Pages token** (do_holders + do_theses + swap_history — le plus lourd,
   ~10 XHR/token en itératif) : hodlers/top+devs+friends, feed/token/thesis+
   sortedThesis, proxy/tokenDetails+tokenWarnings, proxy/filterTokens.
2. **do_profiles** : v2/users/<uuid> + balances + leaderboard +
   aggregatedSnapshotById + trades + swaps — REST pur, boucle handles.
3. **do_top100 + walker leaderboard** : /v2/leaderboard?window=alltime|7d|24h
   (1 requête remplace une navigation + parse).
4. **do_feed + do_clans** : /feed/tradingActivity, /v2/clans/leaderboard
   (surfaces DOM déjà vides → gain immédiat).
5. **do_sidebar/walker trending/most_held/bonding/graduated** : snapshot via
   trendingTokens+verifiedTokens+filterTokens (tri graduationPercent/holders) ;
   le live reste sur fomo-ws-signals (WS).
6. **do_session** : remplacer par le cycle JWT cache (déjà fait côté REST) —
   la surface ne sert qu'à maintenir la page DOM vivante.
