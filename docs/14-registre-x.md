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

1. **Récolte** — deux voies : extraction navigateur (session ZCode) → JSON
   labels ARIA, ou harvester autonome (ci-dessous) → JSON propre avec
   timestamps ISO réels.
2. **Ingestion** — `python scripts/fetch_x_posts.py --ingest-json posts.json`
   → `data/warehouse/x_posts.db` (tables `x_posts`, `x_accounts`, `x_calls`).
3. **Parsing v1** — `--parse-calls` : **$CASHTAG obligatoire** (les tickers
   nus généraient des faux positifs type « l'EGLD »), direction, prix
   d'entrée (multiplicateurs k/m gérés), confiance medium/high.
4. **Scoring** — `python scripts/score_x_calls.py --score` : rendements
   forward directionnels +1h/+24h/+7j contre le warehouse klines, rapport
   horodaté dans `reports/`. Branché au timer nocturne.

## Récolte autonome (headless, opérationnelle depuis 2026-09-21)

1. **UNE fois** : `python scripts/x_harvest.py --login` — fenêtre Chromium
   visible (patchright, anti-détection : X refuse la connexion depuis un
   navigateur d'automation standard), se connecter à X ; le script détecte
   la session, sauvegarde le profil (`data/x_browser_profile/`, hors git)
   et se ferme seul.
2. **Ensuite** : `python scripts/x_harvest.py --profiles thatdevlr,lookonchain`
   — headless, pauses 18-32 s entre profils, abort après 2 rebonds
   consécutifs (respect du throttle), `latest.json` à chemin fixe.
3. `--status` vérifie que la session du profil est encore valide.

## Branchement au timer nocturne (2026-09-21)

La chaîne `x_harvest --profiles (watchlist)` → `--ingest-json latest.json` →
`--parse-calls` → `score_x_calls --score` tourne chaque nuit à la FIN du
service `trading-agent-nightly` — après le pipeline stratégies, pour qu'un
souci de scraping ne bloque jamais la campagne. La session du profil
persiste des mois ; si `--status` expire un jour, un `--login` de 60 s
la renouvelle.

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
