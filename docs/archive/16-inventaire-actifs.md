---
title: Inventaire des actifs — ce qui existe, ce qui dort, ce qui vaut de l'or
status: archived (28/09 — l'ère pré-refonte, voir docs/README.md)
owner: cheurteen
updated: 2026-09-21
---

# La question à laquelle ce doc répond

Qu'est-ce qui existe dans le projet, qu'est-ce qui vit, qu'est-ce qui dort —
et quels actifs dormants valent le plus pour les objectifs actifs (Registre X,
trading Aster, produits/monétisation) ?

## Verdicts par sous-système (exploration du 2026-09-21)

| Sous-système | Verdict |
|---|---|
| `backtest_v2/` + nightly + warehouse | **ALIVE** — 794 runs, 114 038 lanes, 0 accepté (les gates sont honnêtes) |
| Registre X (scripts fetch/score/board + x_posts.db) | **ALIVE** — 28 posts, 13 calls, session patchright persistante |
| `collector.py` + `footprint.py` + `smart_engine.py` (Hyperliquid WS) | **ALIVE mais sans UI** — tourne au boot de main.py, snapshots dans `backend/data/snapshots/` |
| `alpha_lab.py` + `alpha_wallets.py` + `alpha_premium_data.py` (Cielo/Zerion/Etherscan, clés live) | **ALIVE** — 23 endpoints `/api/alpha/*`, sous-utilisés |
| `arkham_scraper.py` + `arkham_tracker.py` + label ledger (696 labels promus) | **ALIVE** — trésor de labels dormants |
| `services/onchain/aster/` (~90 fichiers) | **GELÉ depuis juin** — lab de recherche complet, monitors paper, promotion scoring |
| `onchain_engine.py` (101 663 lignes) | **ALIVE** — monolithe façade, migration strangler en cours |
| `agent/` (RiskGuard, client GLM) | **DORMANT** — pas de clé GLM ; RiskGuard réutilisable tel quel |
| `routers/desktop.py`, MT5, qwen, scripts WSL | **MORT** (legacy Windows) |
| `frontend/` (7 pages, AlphaLab 2 100+ lignes) | **ALIVE** — page Terminal appelle des endpoints fantômes |

## Top 10 des actifs dormants (par valeur)

1. **Le lab Aster gelé** — ~90 modules + **4 618 trades paper réels** (ledger
   dans onchain.db, figé au 02/06) + lanes validées PF 5-8 (INJ 15m, BOME 3h,
   TIA 2h...). La réhydratation = rejouer ces lanes sous les gates de
   `backtest_v2` avec le warehouse actuel. C'est le plus gros actif du projet.
2. **Le Registre X** — moteur complet + session persistante. Accumulation de
   verdicts = le produit (docs/15).
3. **Scanner funding + carry** — branchés, rapports nocturnes.
4. **`backend/data/onchain/onchain.db`** (33 Mo) — 6 565 wallets, 17 060
   transfers : le pont entre les calls X et la réalité on-chain (quels
   wallets derrière les tokens appelés).
5. **Le trésor de labels Arkham** — 696 labels promus, 5 849 candidats,
   358 snapshots Scrapling (19 Mo).
6. **Le stack order-flow Hyperliquid sans UI** — collector/footprint/smart
   engine tournent à vide ; un panneau frontend ou un 2e flux du Registre
   (« ce que le tape a fait » vs « ce que X a dit »).
7. **L'intelligence de wallets premium** — clés Cielo/Zerion actives :
   un générateur de rapport « copier une whale » est vendable (couloir MOYEN).
8. **`agent/risk_guard.py`** — kill-switch propre (taille, perte max, nb
   positions) : la couche d'approbation de toute exécution future.
9. **Le ledger d'expériences comme contenu** — « 114 038 variantes testées,
   voilà pourquoi aucune n'a passé » = la marque anti-hype (couloir LONG).
10. **Un produit premium FINI, jamais publié** :
    `reports/anonymous_market_intelligence_case_file_ce001_premium.pdf`
    + son draft de thread X (`..._x_thread_draft_ce001.md`).

## Data avec du contenu que rien ne lit

- `backend/data/opportunities/` — 30 Mo, **7 330 JSON d'opportunités
  historiques** (avril 2026), zéro lecteur.
- `data/warehouse/legacy_lanes.db` — 22 Mo, 17 092 lanes archivées
  (`scripts/index_legacy_dataset.py` existe pour les réindexer).
- `backend/data/arkham/scrapling/` — 358 snapshots d'entités (19 Mo).
- Orphelins de migration à purger un jour : `data/signals/` (MT5),
  `data/chat|investigations|news|screenshots`, DB à 0 octets
  (`data/onchain.db`, `backend/data/onchain.db`, ...).

## Sécurité

- **2026-09-21 : clés API en clair purgées** de
  `backend/services/wallet_analyzer.py` (Etherscan/Covalent → lues depuis
  l'environnement). Elles restent dans l'historique git local (jamais pushé) ;
  si le repo part un jour sur un remote, réécrire l'historique avant.
- `backend/.env` contient des clés premium actives (Cielo, Zerion, Gemini,
  Firecrawl) + `ASTER_TESTNET_AGENT_PRIVATE_KEY` — ne jamais pousser ce
  fichier nulle part.
