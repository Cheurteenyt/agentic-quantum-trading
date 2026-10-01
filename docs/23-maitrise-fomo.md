# 23 — Matrice de maîtrise fomo.family

> **domain: FOMO** · index : [`fomo/README.md`](fomo/README.md) · data : `data/fomo/` · reports : `reports/fomo/`  
> **Ne pas** mélanger avec Aster (`the_machine`) ni OpenMarket.

> La carte vivante de TOUT ce que le site expose vs ce qu'on capture.
> Mise à jour à chaque nouveau chantier. Le standard : « capturé » = la table
> peuplée en continu, « partiel » = le sous-ensemble visible seulement,
> « manquant » = rien.

## L'architecture de collecte (l'état)

| Moteur | Transport | Ce qu'il porte |
|---|---|---|
| **daemon WS** (`fomo_ws_daemon.py`) | wss natif, sans navigateur | prix (dédup), swaps globaux, thèses live, pression token_details, ohlcv 30s (volume DEX), trending_tokens (la découverte), bougies 1m, signaux de sortie temps réel |
| **worker DOM** (`fomo_dom_worker.py`) | 1 page permanente, navigateur dédié :9222 | désormais **2 surfaces** : le walker bonding (sidebar) + la session JWT (le re-mint CDP) — tout le reste de l'onglet token est passé au REST |
| **collector REST** (`fomo_rest_collector.py`, 29/09 v2 « toute la carte ») | HTTPS prod-api, curl_cffi chrome131 + JWT, SANS navigateur | holders (97/appel + totalHolders + costBasis), thèses 24 h (500/token), swaps élite (curseur lastSwapId), trades fermés, top-100 all-time, clans, trending, feed d'activité, profils élite (4 endpoints), About batch (filterTokens), bonding (pre-graduation) — structure DÉCLARATIVE COLLECTES + skip par fraîcheur (captured_at), base dédiée fomo_rest.db |
| **timers** | signaux 5 min, paper forward 15 min | consensus sortie/entrée, thèses élite, réplications |

## La matrice des surfaces

### Niveau token (par token chaud, 12 / passe 30 min)
| Surface | État | Table | Manque |
|---|---|---|---|
| Header (MC, prix, holders, liquidité, top-10 %, buys/sells) | ✅ capturé | fomo_token_header | — |
| Holders (position, PnL, cost basis, entrée moyenne) | ✅ capturé (REST) | fomo_rest_snapshots=hodlers_top | 97/appel + totalHolders exact — le scroll DOM = fallback |
| Thesis (l'archive des thèses) | ✅ capturé (REST) | fomo_rest_snapshots=thesis_sorted | 500/24 h/token (fenêtre afterTime/beforeTime obligatoire) |
| Swaps historiques (l'archive AVANT notre capture) | ✅ capturé | fomo_token_swap_history | l'accumulation (la profondeur du scroll) |
| About (launchpad, supply, network, created, contract) | ✅ capturé | fomo_token_header (5 colonnes About) | les socials + l'état de la bonding curve |
| Panneau position ?tradeId (l'entrée moyenne, les holders par trade) | ❌ manquant | fomo_token_intel (1 ligne morte) | la visite du panneau |
| Chart overlays (my swaps, thesis, min size) | ❌ manquant | — | l'app aux overlays |

### Niveau trader
| Surface | État | Table | Manque |
|---|---|---|---|
| Top-100 all-time + l'élite dynamique | ✅ capturé (REST, remplace dom_leaderboard) | fomo_rest_snapshots=leaderboard_alltime (+ /v2/leaderboard/24h pour l'élite) | — |
| Trades fermés | ✅ capturé (REST) | fomo_rest_snapshots=trades_closed | le backfill incrémental lastTradeId |
| Positions courantes | ✅ capturé (REST, remplace dom_profile_positions) | fomo_rest_snapshots=profile_user/balances | — |
| Graphe social (mutuals/following/followers) | ✅ capturé | ws_traders | le graphe entre traders (qui suit qui) |
| Courbe d'équité (le graphique du profil) | ❌ manquant | — | le data derrière le chart |
| Swap history paginé (lastSwapId = cracké) | ✅ capturé (REST) | fomo_rest_swaps | — |
| Découverte : holders skilles → la rotation | ✅ la boucle | ws_traders + la rotation | l'accumulation |

### Niveau flux temps réel
| Surface | État | Table | Manque |
|---|---|---|---|
| Prix (dédup, 40-78 topics) | ✅ | fomo_ticks | la profondeur au-delà du hot set |
| Swaps globaux (buy/sell, MC, équité) | ✅ | ws_swaps | — |
| Thèses live | ✅ | ws_theses | — |
| Pression (buys/sells, volumes achat/vente) | ✅ | ws_token_details | — |
| Volume DEX (ohlcv 30s) | ✅ | fomo_ohlcv | — |
| Découverte (trending_tokens snapshot) | ✅ | fomo_tokens | les tokens pré-trending (bonding) = le worker 15 min |
| Pré-graduation (topic natif pre_graduated_tokens) | ✅ | fomo_pre_graduated (WS live) + fomo_rest_snapshots=bonding_snapshot (REST 30 min) — bonding/graduated = WS live + REST snapshot | le branchement au prédicteur de graduation |
| Sortie consensus (< 2 s) | ✅ | ws_signals | le branchement paper forward |

### Surfaces sociales / secondaires
| Surface | État | Manque |
|---|---|---|
| Clans (liste + holdings) | ✅ capturé (REST, remplace le DOM brut) | fomo_rest_snapshots=clans | le parse fin à la lecture |
| Feed (les posts/trades) | ✅ capturé (REST, remplace le DOM 51 chars) | fomo_rest_snapshots=trading_activity_feed | le follow-based = notre compte ne suit personne |
| Search | ❌ | — | jamais explorée |
| Most held | ✅ remplacé REST | fomo_rest_snapshots=verified_tokens (tri `holders` à la lecture) | les onglets hero n'émettent AUCUN XHR — le clic DOM était mort |
| Messages / Send / notes | ❌ | hors edge |
| Referrals / points | ❌ | hors edge |

## L'ordre d'attaque (l'alpha décroissant)
1. ~~Swaps historiques par token~~ ✅ FAIT (29/09) — fomo_token_swap_history en capture continue
2. **About** ✅ FAIT (29/09, dans fomo_token_header) — reste l'état de la bonding curve
3. **L'onglet Thesis scroll** — l'archive complète (le même pattern que les holders)
4. **Les 28 pages fermées** pour l'élite-20 — l'historique réalisé complet
5. **Le panneau ?tradeId** — l'intel par trade
6. **Les parseurs aux sélecteurs du census** — la robustesse aux changements d'UI

## Le référentiel chart↔trader (29/09 nuit) — « reconstruire n'importe quelle chart fomo avec ses traders »

| Brique | Où | Précision |
|---|---|---|
| La courbe prix | fomo_ohlcv 1m (5,14 M bougies / 1 414 assets, lag ~0) + fomo_ticks (hot set, 1-45 s) | bougie native |
| **La MC native** | **fomo_mc_samples** (fomo.db) : les frames trending_tokens portaient marketCap/priceUSD/supply/holders — le daemon les JETAIT ; désormais échantillonnées (1/min/mint ou ΔMC ≥ 0,5 %, snapshot ET update ET pre_graduated) | native, supply variable suivie |
| MC(t) calculée | MC = prix_tick(t) × supply_interp(t) (supply = market_cap/price_usd par échantillon, interpolé entre deux captured_at) | ±4-10 % si supply figée → NE PLUS figer |
| Les trades | ws_swaps (live, hot set) + **fomo_rest_token_trades** (+~2 400/jour, walk du feed tradingActivity, curseur lastId — le filtre tokenAddress est IGNORÉ par l'API : mint toujours attribué par item.tokenAddress) + fomo_rest_swaps (élite) | **chaque trade porte marketCap/fdv/price/equity/usdAmount AU TRADE** |
| Les traders | ws_traders (fomo_swaps.db), fomo_traders (373 handles), hodlers_top (averageEntryPrice/costBasis par holder), leaderboard | l'entrée moyenne sans date = la limite actuelle |
| La reconstruction | **scripts/fomo_chart_trader.py --mint <mint>** → PDF (courbe fusionnée bougies+ticks, buys/sells, lignes d'entrée des holders, axe MC log) | la preuve : STONK, 3 784 pts, 1 828 trades, 660 entrées |

Les pièges référentiels : le feed global est FAIBLE (20-75/h) — l'archive vient du walk incrémental, pas du live ; `token_details` ne porte QUE la pression (0 MC/supply) ; le filtre tokenAddress d'tradingActivity est un placebo ; toute donnée WS reçue et non persistée = un backtest amputé (le parking de 130 Mo/jour, refermé par le drain du worker).

## Les leçons d'architecture (gravées)
- fomo.db = la base HOT du daemon (les ticks 2 s) → les tables DOM = sur fomo_swaps.db (le lock = la panne racine des routes holders)
- La txn d'écriture = un commit PAR PASSE : la connexion walker survit au boot du worker, une txn jamais committée tient le verrou WAL en continu → TOUT le daemon gèle (la panne du 29/09 : 0 tick écrit pendant 1h30, 378 flush différés)
- Le DDL des tables vit dans ensure_tables/ensure_dbs + l'INSERT = liste de colonnes explicite : un CREATE inline avalé par except ne crée JAMAIS la table (swap_history), un ALTER désynchronisé de l'INSERT déraille en silence (header 15 vs 14, ws_traders 9 vs 6 — le flush des traders perdait des lignes toutes les 2 s), et un parseur non importé perd ses lignes sans bruit (parse_token_swaps, NameError avalé)
- Le WAF (Cloudflare) bloque le fingerprint TLS, PAS l'API : curl_cffi impersonate chrome131 + Bearer JWT = 200 partout (la sonde REST du 29/09). « Pas d'API de données » était FAUX : les endpoints XHR (hodlers/top, feed/token/thesis, v2/users/<id>/swaps, trades, proxy/trendingTokens) n'apparaissent qu'en naviguant les onglets token — la sonde scripts/studies/fomo_rest_probe.py les capture et les rejoue
- La collecte REST = une base DÉDIÉE (fomo_rest.db, 1 écrivain) : la leçon du lock du 29/09 appliquée d'office
- Le collector REST = structure DÉCLARATIVE (COLLECTES + fraîcheur par captured_at) — une collecte sans skip de fraîcheur est un bug
- Les listes du site = virtualisées → scroll conteneur + dédupe, toujours
- Les labels = SINGULIERS avec le compteur (« Thesis (3,846) ») — les matchs exacts
- La nav = 100 % clics SPA, les URL directes = « Go home »
- Le transport des données = un WS partagé invisible au CDP page — le listener passif = la découverte
