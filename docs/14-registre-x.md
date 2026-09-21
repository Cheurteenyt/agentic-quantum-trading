---
title: Le registre X — tenir le score de crypto twitter
status: living
owner: cheurteen
updated: 2026-09-21
---

# Le registre X

> Tout le monde publie des calls, personne ne tient le score. Le pipeline
> backtest_v2 sait déjà « évaluer une affirmation du passé contre des données
> arrivées après » — on le rebranche sur les posts X.

## La question à laquelle ce doc répond

Comment ingérer, stocker et parser les posts X qui constituent la matière
première du registre ?

## La chaîne

1. **Récolte** — navigateur (session connectée), extraction DOM → JSON
   (`post_id`, `author_handle`, `status_url`, `raw_label`).
2. **Ingestion** — `python scripts/fetch_x_posts.py --ingest-json posts.json`
   → `data/warehouse/x_posts.db` (tables `x_posts`, `x_accounts`, `x_calls`).
3. **Parsing v0** — `--parse-calls` : passe déterministe (symbole $TICKER +
   direction + prix d'entrée), confiance low/medium/high. Ne score que ce
   qu'elle lit sans ambiguïté.
4. **Scoring** (phase 3) — rendements forward des calls contre le warehouse
   klines : la machinerie `reevaluate_oos.py` s'applique telle quelle.

## Contrainte découverte le 2026-09-21 (importante)

X soft-throttle la navigation rapide : après quelques pages, les deep-links
`/search` ET les profils rebondissent vers l'accueil. Conséquences :

- volume nocturne = **quelques profils, espacés (15-30 s)**, pas de firehose ;
- les profils de la watchlist tiennent plus longtemps que `/search` ;
- le design watchlist-first est aussi le design anti-biais.

## Règles anti-biais (non négociables)

1. Watchlist diverse dès la création (data / aggregator / trader / retail).
2. Jamais d'ajout de compte APRÈS avoir vu ses résultats.
3. La correction de multiplicité s'appliquera aux track records : choisir le
   « gagnant » parmi 200 comptes, c'est 200 essais, pas 1.
4. Le parser ne devine pas. Un registre qui devine ment.
