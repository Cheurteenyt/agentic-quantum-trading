# Backend Services Catalog

Ce dossier contient encore trop de modules au meme niveau. Ne pas deplacer ou supprimer
un service sans verifier ses imports dans `routers/`, `main.py` et les autres services.

## Core Runtime

- `collector.py` - collecte marche/systeme.
- `multi_exchange.py` - aggregation multi-exchange.
- `smart_engine.py` - logique trading/decision.
- `websocket_manager.py` - diffusion temps reel.
- `web_agent.py` - investigation web Firecrawl/Scrapling.

## Configuration

- `../config/trading.py` - configuration Python backend principale.
- `../../trading_config.py` - wrapper de compatibilite legacy uniquement. Le
  nouveau code doit importer `backend.config.trading`.

## Arkham / Entity Intelligence

- `arkham_scraper.py` - gros module legacy/actif pour tokens, holders et fallbacks.
  A garder pour l'instant: il expose `ArkhamDatabase`, `ArkhamScraper`,
  `get_arkham_scraper`, `get_arkham_db`, `get_entity_profile` et plusieurs
  constantes utilisees par `routers/arkham.py`.
- `arkham_tracker.py` - tracking Arkham-like.
- `entity_intelligence.py` - profils entites et labels locaux.
- `scrapling_probe.py` - miroir/probing Arkham via Scrapling.
  A garder pour l'instant: il contient les normalizers Arkham-like pour entity
  profile, balances, history, loans, volume, transfers et token flows.
- `scrapling_intelligence.py` - enrichment Scrapling plus cible.

## Alpha Lab

- `alpha_lab.py` - logique Alpha Lab. A garder: expose les APIs publiques Alpha
  Lab et garde les wrappers compatibles pour les routes.
- `alpha_simulation.py` - simulations prediction/copy et manipulation
  counterfactual. Le moteur manipulation recoit le risk analyzer en injection.
- `alpha_risk_models.py` - modeles Pydantic pour flags, sellability probe et
  resultat token risk.
- `alpha_risk.py` - moteur pur de scoring token risk. Le sellability probe est
  injecte par `alpha_lab.py` pour garder les appels reseau isoles.
- `alpha_sellability.py` - probes reseau DexScreener, Honeypot.is et explorer
  Scrapling/urllib pour verifier si un token est vendable.
- `alpha_wallets.py` - wallet probing et portefeuille client. A garder: connecte
  Cielo/Zerion, discovery, identity graph, PnL, copy preview et wallet surfaces.
- `alpha_premium_data.py` - sources premium/simulation.
- `wallet_analyzer.py` - analyse wallet/cache/token risk.

## On-Chain Data

- `onchain_engine.py` - orchestration RPC/DB publique, wrappers compatibles routers.
  A partir du 2026-05-23, ce fichier doit etre traite comme facade legacy:
  ne plus y ajouter de nouvelles lanes produit si un sous-module `services/onchain/`
  peut les accueillir. Pour Aster, ne pas ajouter de nouvelle logique produit
  ici; utiliser `services/onchain/aster/` et garder seulement des wrappers fins
  si les routes/tests historiques en ont besoin.
- `onchain_chains.py` - chain aliases, RPC URLs, fallbacks, tokens suivis.
- `onchain_quality.py` - classification qualite/fresh/risk.
- `onchain_coverage.py` - coverage labelled-vs-RPC par entite.
- `onchain_flows.py` - flows/counterparties locaux.
- `onchain_status.py` - statut read-only RPC/DB.
- `label_ledger.py` - ledger local des labels.
- `label_expansion.py` - expansion de labels.
- `seed_ingestion.py` - ingestion seeds vers onchain.
- `onchain/README.md` - regles de migration et domaines cibles.
- `onchain/REFACTOR_MAP.md` - carte de migration de `onchain_engine.py`.
- `onchain/core/constants.py` - constantes EVM/topics stables sans import du monolithe.
- `onchain/core/constants.py` expose aussi les maps d'endpoints publics
  Blockscout/SQD utilisees par les helpers bornes.
- `onchain/core/paths.py` - chemins par defaut DB/cache/backup onchain sans import du monolithe.
- `onchain/core/json.py` - helpers JSON/coercion/env purs.
- `onchain/core/addresses.py` - validation adresse EVM pure.
- `onchain/core/collections.py` - helpers de collection deterministes.
- `onchain/core/numbers.py` - helpers numeriques purs.
- `onchain/dex/event_reader.py` - helpers purs du local DEX event reader
  (preview logs, topic addresses, uint words, raw-event candidates).
- `onchain/dex/mapping_review.py` - builders DEX mapping review
  contrat/schema-plan/create/insert, appeles par la facade avec DB patchable.
- `onchain/dex/paircreated.py` - helpers bornes PairCreated/Blockscout/SQD sans
  persistance, re-exportes par la facade legacy.
- `onchain/events/abi.py` - decodeurs ABI/ERC20 purs.
- `onchain/events/parsers.py` - parsers EVM purs pour logs Swap/Transfer et resultats hex.
- `onchain/aster/` - namespace reserve et obligatoire pour la prochaine suite
  Aster data/API; suivre `rag/memory/aster_python_structure_rules.md`.
- `onchain/aster/scrapling_label_enrichment_batch.py` - preview read-only sur
  snapshots Scrapling normalises locaux uniquement; aucun scraping live, aucun
  appel externe, aucun label/evidence/mapping/signal/trade.
- `onchain/aster/dexscreener_enrichment_layer.py` - preview read-only
  DexScreener single-source pour enrichir les candidats comportementaux locaux
  avec volume/liquidite/txns/composite score; aucun write, label, mapping,
  signal, trade, fallback Scrapling ou fallback RPC.

## Older / Candidate Review

Ces modules sont references mais peuvent etre regroupes plus tard apres tests.
Ne pas supprimer tant que les routes correspondantes existent.

- `footprint.py`
- `intel_aggregator.py`
- `entity_intelligence.py`

## Refactor Policy

Priorite actuelle:

1. Garder `alpha_lab.py` et `alpha_wallets.py` comme coeur produit.
2. Garder `arkham_scraper.py` et `scrapling_probe.py` comme sources/normalizers
   tant que notre data RPC n'a pas remplace leurs usages.
3. Extraire progressivement des sous-modules stables, sans changer les imports
   publics utilises par les routers.
4. Ne pas continuer les micro-extractions de `onchain_engine.py` seulement pour
   reduire le nombre de lignes; extraire uniquement la famille touchee par une
   vraie tache produit/data.
5. Supprimer uniquement apres tests runtime et verification UI/API.

## Data Placement

Les fichiers `.db` ne doivent pas vivre dans `services/`.

Chemins actifs:

- `backend/data/entity/entity_labels.db`
- `backend/data/wallets/wallet_cache.db`
- `backend/data/onchain/onchain.db`
- `backend/data/arkham/label_ledger.db`

Anciennes copies archivees:

- `backend/data/legacy/entity_labels.db`
- `backend/data/legacy/wallet_cache.db`

Ne pas supprimer les anciennes copies avant un run backend propre et une verification UI/API.
