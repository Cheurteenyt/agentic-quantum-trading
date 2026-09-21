# Aster - Regles de structure Python

Derniere mise a jour: 2026-06-02.

Objectif: empecher la suite Aster de recreer un gros monolithe comme `onchain_engine.py`, tout en gardant le code testable, lisible et sur.

## Decision produit

- `backend/services/onchain_engine.py` reste une facade legacy/compatibilite.
- Ne pas ajouter de nouvelles lanes Aster directement dans `onchain_engine.py`.
- Le travail Aster doit vivre sous `backend/services/onchain/aster/`.
- Les wrappers de compatibilite sont acceptes seulement si un routeur/test existant importe encore depuis `services.onchain_engine`.
- Ne pas extraire du legacy pour le plaisir: extraire seulement la famille de fonctions touchee par une vraie tache produit/data.

## Modules Aster existants et role

- `aster_agent_foundation.py`: exploration API Aster, wallet preview, listener read-only.
- `aster_agent_decision_engine.py`: state machine et decisions dry-run/paper, sans ordre reel.
- `aster_paper_trading_sandbox.py`: ledger paper-trading, replays, analytics, short/fade, monitors stateful.
- `monitor_shorts.py`: boucle locale de monitoring paper short/fade et CSV.
- `scrapling_label_enrichment_batch.py`: lecture locale de snapshots Scrapling normalises uniquement.
- `dexscreener_enrichment_layer.py`: enrichissement DexScreener leger pour candidats locaux.
- `dexscreener_first_discovery_layer.py`: decouverte DexScreener-first, read-only.

## Modules futurs si necessaires

Creer seulement si le besoin devient reel:
- `client.py`: appels Aster/provider bornes, timeouts, retries, aucun write DB.
- `schemas.py`: contrats TypedDict/dataclass/Pydantic et payloads normalises.
- `discovery.py`: selection read-only des candidats et disponibilite data.
- `scoring.py`: scoring anomalie/risque si `aster_paper_trading_sandbox.py` devient trop gros.
- `policy.py`: gates de securite et decisions de readiness.
- `audit.py`: builders de recus audit, `would_write`, `writes_performed`.

## Regles de taille et couplage

- Viser des fichiers autour de 300-800 lignes.
- Inspecter/splitter un fichier Aster qui depasse environ 800 lignes.
- Splitter avant 1200 lignes sauf reference statique.
- Pas de `utils.py`, `helpers.py`, `new_engine.py` generiques.
- Pas de module one-off par token.
- Les primitives partagees doivent aller dans un module clairement nomme, pas dans `onchain_engine.py`.

## Regles de securite

- Par defaut: read-only et dry-run-first.
- Aucun label, mapping, signal client, trade, wallet order ou opt-in par defaut.
- Les appels provider/API doivent etre bornes, timeout-aware et caches si necessaire.
- Les ecritures DB exigent:
  - nom explicite `create_`, `insert_`, `persist_`, `apply_` ou `run_`
  - confirm contract
  - idempotence/dedupe
  - validation/smoke
- Les ecritures autorisees aujourd'hui concernent uniquement la table paper-trading dediee avec confirm.

## Voie Aster active

La voie active est maintenant `Aster V2 research + backtest discovery
post-correctifs + validation reality pack`.

Ancienne voie importante a conserver comme historique: `short/fade
paper-trading`. Elle a produit de vrais enseignements, mais ne doit plus etre
la seule ancre decisionnelle.

Ne pas relancer les voies non concluantes sauf preuve nouvelle:
- long/buy order-flow seul
- hybride Aster + DEX avec intersection trop faible
- recalibrage long micro-cap

Continuer plutot:
- runners discovery tagges par `output_tag`
- validation out-of-sample V2
- mark/index strict
- microstructure replay
- queue reality pack
- ledger analytics seulement pour les forwards paper explicites
- RAG reindex apres toute mise a jour durable

## Regles anti-erreurs statistiques

Toute modification de code backtest doit verifier:

- PnL realise separe du latent ouvert;
- frais/funding calcules sur exposition notionnelle si levier;
- `score_window_size` inclus dans l'identite de strategie;
- `trigger_reference` et `execution_model` conserves jusqu'au CSV;
- pas de fallback Spot silencieux pour `mark_price`;
- intervalles synthetiques agreges par timestamp;
- sorties taggees par `output_tag`;
- colonnes V2 `train_*`, `validation_*`, `out_of_sample_status` preservees.

Si un changement casse un de ces points, les nouveaux resultats doivent etre
marques exploratoires et non decisionnels.

## Routage des prochaines taches

- API/fetch/retry Aster -> `aster_paper_trading_sandbox.py` ou futur `client.py`
- replay/backtest/paper ledger -> `aster_paper_trading_sandbox.py`
- decision state machine -> `aster_agent_decision_engine.py`
- rapport/documentation -> `docs/core-equity-aster-research-report.html`
- regles structurelles -> ce fichier

Toujours implementer la plus petite surface utile.
