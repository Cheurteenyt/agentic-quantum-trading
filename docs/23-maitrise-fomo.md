# 23 — Matrice de maîtrise fomo.family

> La carte vivante de TOUT ce que le site expose vs ce qu'on capture.
> Mise à jour à chaque nouveau chantier. Le standard : « capturé » = la table
> peuplée en continu, « partiel » = le sous-ensemble visible seulement,
> « manquant » = rien.

## L'architecture de collecte (l'état)

| Moteur | Transport | Ce qu'il porte |
|---|---|---|
| **daemon WS** (`fomo_ws_daemon.py`) | wss natif, sans navigateur | prix (dédup), swaps globaux, thèses live, pression token_details, ohlcv 30s (volume DEX), trending_tokens (la découverte), bougies 1m, signaux de sortie temps réel |
| **worker DOM** (`fomo_dom_worker.py`) | 1 page permanente, navigateur dédié :9222 | sidebar (trending/most held), bonding, graduated, alerts, top-100+élite, clans/feed (bruts), profils top traders (courant + top trades), holders scroll-capture, theses archive, header token |
| **timers** | signaux 5 min, paper forward 15 min | consensus sortie/entrée, thèses élite, réplications |

## La matrice des surfaces

### Niveau token (par token chaud, 12 / passe 30 min)
| Surface | État | Table | Manque |
|---|---|---|---|
| Header (MC, prix, holders, liquidité, top-10 %, buys/sells) | ✅ capturé | fomo_token_header | — |
| Holders (position, PnL %, MC d'entrée, hold, thèse) | 🟡 partiel | fomo_token_holders | ~300/3 543 — la profondeur au-delà = le long tail |
| Thesis (l'archive des thèses + likes) | 🟡 partiel | fomo_token_theses | le scroll-capture à câbler comme les holders |
| Swaps historiques (l'archive AVANT notre capture) | ✅ capturé | fomo_token_swap_history | l'accumulation (la profondeur du scroll) |
| About (launchpad, supply, network, created, contract) | ✅ capturé | fomo_token_header (5 colonnes About) | les socials + l'état de la bonding curve |
| Panneau position ?tradeId (l'entrée moyenne, les holders par trade) | ❌ manquant | fomo_token_intel (1 ligne morte) | la visite du panneau |
| Chart overlays (my swaps, thesis, min size) | ❌ manquant | — | l'app aux overlays |

### Niveau trader
| Surface | État | Table | Manque |
|---|---|---|---|
| Top-100 all-time + l'élite dynamique | ✅ capturé | dom_leaderboard | — |
| Trades fermés (format $invested • hold) | 🟡 5 pages/session | dom_profile_trades | les 28 pages paginées = l'historique complet |
| Positions courantes | ✅ capturé | dom_profile_positions | — |
| Graphe social (mutuals/following/followers) | ✅ capturé | ws_traders | le graphe entre traders (qui suit qui) |
| Courbe d'équité (le graphique du profil) | ❌ manquant | — | le data derrière le chart |
| Swap history paginé (lastSwapId = cracké, API 401) | 🟡 partiel | fomo_swaps | la reprise quand l'auth revient |
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
| Pré-graduation (topic natif pre_graduated_tokens) | ✅ | fomo_pre_graduated | le branchement au prédicteur de graduation |
| Sortie consensus (< 2 s) | ✅ | ws_signals | le branchement paper forward |

### Surfaces sociales / secondaires
| Surface | État | Manque |
|---|---|---|
| Clans (liste + holdings) | 🟡 brut | le parse fin + la page clans (la nav a bougé) |
| Feed (les posts) | 🟡 brut (51 chars = vide) | le follow-based = notre compte ne suit personne |
| Search | ❌ | jamais explorée |
| Most held | 🟡 le clic = à régler | l'onglet sidebar scrollable |
| Messages / Send / notes | ❌ | hors edge |
| Referrals / points | ❌ | hors edge |

## L'ordre d'attaque (l'alpha décroissant)
1. ~~Swaps historiques par token~~ ✅ FAIT (29/09) — fomo_token_swap_history en capture continue
2. **About** ✅ FAIT (29/09, dans fomo_token_header) — reste l'état de la bonding curve
3. **L'onglet Thesis scroll** — l'archive complète (le même pattern que les holders)
4. **Les 28 pages fermées** pour l'élite-20 — l'historique réalisé complet
5. **Le panneau ?tradeId** — l'intel par trade
6. **Les parseurs aux sélecteurs du census** — la robustesse aux changements d'UI

## Les leçons d'architecture (gravées)
- fomo.db = la base HOT du daemon (les ticks 2 s) → les tables DOM = sur fomo_swaps.db (le lock = la panne racine des routes holders)
- La txn d'écriture = un commit PAR PASSE : la connexion walker survit au boot du worker, une txn jamais committée tient le verrou WAL en continu → TOUT le daemon gèle (la panne du 29/09 : 0 tick écrit pendant 1h30, 378 flush différés)
- Le DDL des tables vit dans ensure_tables/ensure_dbs + l'INSERT = liste de colonnes explicite : un CREATE inline avalé par except ne crée JAMAIS la table (swap_history), un ALTER désynchronisé de l'INSERT déraille en silence (header 15 vs 14), et un parseur non importé perd ses lignes sans bruit (parse_token_swaps, NameError avalé)
- Les listes du site = virtualisées → scroll conteneur + dédupe, toujours
- Les labels = SINGULIERS avec le compteur (« Thesis (3,846) ») — les matchs exacts
- La nav = 100 % clics SPA, les URL directes = « Go home »
- Le transport des données = un WS partagé invisible au CDP page — le listener passif = la découverte
