---
title: Data — architecture et exploitation du dataset
status: living
owner: cheurteen
updated: 2026-08-09
---

# Data

> En trading, la data mal rangée coûte plus cher qu'une mauvaise stratégie : elle
> fait croire à des résultats qui n'existent pas. Ce doc explique comment la data
> du projet est organisée et ce qu'elle dit réellement.

## 1. Le warehouse

```
data/
├── warehouse/              couche interrogeable — GÉNÉRÉE, jamais éditée
│   └── legacy_lanes.db     17 092 lanes de backtest legacy, indexées
├── arkham/  news/  signals/  snapshots/  investigations/
├── chat/  screenshots/  logs/
└── onchain.db
```

Principe : **les sources brutes ne bougent jamais, la couche interrogeable est
reconstructible.** `data/warehouse/` peut être supprimé et régénéré en 30 s.
Aucune décision ne doit dépendre d'un fichier qu'on ne sait pas reproduire.

```bash
python scripts/index_legacy_dataset.py --stats
```

## 2. Le problème : 442 Mo qui ne servaient à rien

Le dataset legacy Aster, tel qu'archivé :

```
56 CSV · 442 Mo · 17 092 lignes  →  26 Ko par ligne
```

26 Ko par ligne pour des métriques de backtest, c'est anormal. Mesure des
colonnes sur le plus gros fichier :

| Colonne | Poids | Part |
|---|---:|---:|
| `candidate_json` | 15,4 Mo | 52,2 % |
| `perps_scenarios_json` | 9,4 Mo | 32,0 % |
| `leverage_scenarios_json` | 3,6 Mo | 12,1 % |
| **total `*_json`** | **28,4 Mo** | **96,3 %** |

**96 % du volume est dans trois colonnes JSON jamais requêtées.** Le dataset
n'était pas gros, il était mal rangé. Résultat : personne ne l'interrogeait,
donc personne ne voyait ce qu'il contenait.

Après indexation, colonnes lourdes exclues :

```
355 Mo de CSV  →  23 Mo de SQLite  ·  15x plus compact  ·  114 colonnes
```

Requêtable en millisecondes, six variantes de schéma réconciliées.

## 3. La réconciliation de schéma

Les 56 CSV n'ont pas le même en-tête — **6 variantes**, de 51 à 118 colonnes :

| Variante | Lignes | Fichiers | Ce qu'elle apporte |
|---|---:|---:|---|
| `v0_118cols` | 5 185 | 12 | **génération corrigée** : split train/validation, PnL réalisé/latent séparés, coûts de funding |
| `v4_51cols` | 4 777 | 3 | socle minimal |
| `v1_98cols` | 3 009 | 27 | + microstructure, WS quality, filtres exchange |
| `v3_95cols` | 2 639 | 8 | idem sans profil de stratégie |
| `v2_53cols` | 1 480 | 4 | socle + profils |
| `v5_99cols` | 2 | 2 | résidu |

L'intersection commune ne fait que **51 colonnes** : comparer naïvement des
lignes de variantes différentes, c'est comparer des choses qui ne mesurent pas
la même chose. L'index conserve `schema_variant` sur chaque ligne pour rendre
l'erreur impossible.

La variante `v0_118cols` est la plus intéressante : c'est la génération d'après
correctifs, la seule avec `train_*` / `validation_*` et
`pnl_realized_usd` / `open_unrealized_pnl_usd` séparés.

## 4. L'identité de lane, reconstruite

Le bug structurel du legacy était `truth_match_scope = identity_missing` : les
résultats n'étaient pas rattachables à une configuration précise. L'index
reconstruit une identité canonique sur six champs :

```
symbol | interval | side | risk_profile | execution_model | best_tradable_leverage
```

Verdict mesuré :

```
17 092 lignes
 1 131 identités distinctes
11 905 lignes à identité INCOMPLÈTE  →  69,7 %
   987 identités testées plusieurs fois
```

**Sept lignes sur dix ne sont pas rattachables à une configuration complète.**
Elles ne sont pas comparables, donc pas exploitables comme preuve. Le bug n'était
pas cosmétique : il invalidait la majorité du corpus.

## 5. Ce que la data révèle — le biais de survivance, mesuré

C'est le résultat le plus important de cette indexation. Les statistiques
globales du dataset :

```
lanes avec PnL     : 17 092
PnL > 0            : 17 092   →  100,0 %
PnL moyen          : +54,11 USD
PnL cumulé         : +924 828 USD
PnL minimum        : +0,58 USD      ← aucune lane perdante. AUCUNE.
overfit (train+/val-) : 0  (0,0 %)
```

Un dataset de recherche où **100 % des stratégies gagnent et 0 % overfittent
n'existe pas.** Ce n'est pas un résultat, c'est un artefact. L'explication est
dans les compteurs internes des runs :

```
combinaisons testées   : 1 117 620
candidats acceptés     :   105 357
taux d'acceptation     :      9,43 %
```

**Le CSV ne contient que les survivants.** Un million de combinaisons testées,
seuls les gagnants écrits sur disque. Les 442 Mo ne sont pas un dataset de
recherche : c'est une vitrine.

Et le filtre de sélection appliqué était le PnL du backtest lui-même — donc le
`+924 828 USD` mesure exactement une chose : **la capacité du filtre à
sélectionner ce sur quoi il filtre.** Zéro information sur la performance future.

Le coup de grâce est dans le nombre de trades :

```
trades par lane      : min 6 · moyenne 19,3 · max 151
lanes < 100 trades   : 17 019 / 17 092   →   99,6 %
win-rate moyen       : 0,700
```

Un win-rate de 70 % sur **19 trades** n'a aucune signification statistique.
Ces lanes auraient toutes été rejetées par le premier gate de
`03-methodology.md` (< 100 trades → rejet). **99,6 % du corpus ne passe pas le
gate le plus élémentaire.**

### Pourquoi c'est la découverte utile

Le legacy avait déjà tous les bons validateurs — microstructure, mark/index, WS
quality. Ce qui manquait n'était pas un outil, c'était **la trace des perdants**.
Sans les échecs, impossible de savoir si un succès est du signal ou du bruit.

> Un pipeline de backtest qui n'écrit que ses gagnants ne produit pas de la
> connaissance, il produit de la confiance injustifiée.

## 6. Les règles data qui en découlent

Contraintes de conception du futur moteur, directement issues du diagnostic :

1. **Écrire les perdants.** Toute combinaison testée est persistée, avec son
   motif de rejet. Le taux de rejet est une métrique de premier plan, pas un
   déchet.
2. **Identité obligatoire à l'écriture.** Une ligne sans les six champs
   d'identité est refusée à l'insertion — pas réparée après coup.
3. **Colonnes lourdes séparées.** Les blobs JSON vont dans une table annexe
   liée par `identity_hash`, jamais dans la table de métriques.
4. **Schéma versionné explicitement.** `schema_version` sur chaque ligne, et
   refus de comparer deux versions différentes sans conversion déclarée.
5. **Réalisé et latent jamais sommés.** Deux colonnes, deux agrégats, jamais
   un total commun.
6. **Le compteur de tests fait partie du résultat.** `tested`, `accepted`,
   `rejected_by_gate` accompagnent toute publication. Un résultat sans son
   dénominateur n'est pas publiable.

## 7. Interroger le warehouse

```bash
sqlite3 data/warehouse/legacy_lanes.db
```

```sql
-- la génération corrigée, seule à avoir un vrai split OOS
SELECT symbol, interval, side, train_pnl_total_usd, validation_pnl_total_usd,
       closed_trades, win_rate
FROM lanes
WHERE schema_variant = 'v0_118cols'
  AND closed_trades >= 100          -- gate n°1
ORDER BY validation_pnl_total_usd DESC
LIMIT 20;

-- combien survivent au gate le plus simple ?
SELECT schema_variant,
       COUNT(*)                          AS total,
       SUM(closed_trades >= 100)         AS passe_gate_trades
FROM lanes GROUP BY 1;

-- lanes rejouées plusieurs fois : la variance entre runs est le vrai signal
SELECT identity_key, COUNT(*) n,
       MIN(pnl_total_usd), MAX(pnl_total_usd)
FROM lanes
WHERE identity_key NOT LIKE '%?%'
GROUP BY 1 HAVING n > 3
ORDER BY MAX(pnl_total_usd) - MIN(pnl_total_usd) DESC
LIMIT 15;
```

## 8. Usage : test de régression du moteur

Ce dataset a une valeur précise, et une seule : **c'est un jeu de test négatif.**

Le nouveau moteur de backtest, lancé sur ces mêmes configurations, doit
retrouver que ces lanes ne sont pas exploitables — 99,6 % rejetées pour
échantillon insuffisant, identité incomplète sur 69,7 %.

**S'il retrouve +924 828 USD, c'est le moteur qui est cassé.** C'est le premier
test à écrire, avant toute stratégie.

## CARTE DES BASES VIVANTES (28/09)

| Base | Contenu | Écrivains (timers) |
|---|---|---|
| `data/warehouse/klines.db` | klines 1h+15m (CVD taker 100 %), funding_history, liq_events, oi_history (15 min), block_trades+tape_1m (15 min), signal_events, paper_trades (le forward Aster), flow_events, lifecycle_map | fetch_klines (nocturne), oi-collector, aster-blocktrades, paper_forward (nocturne) |
| `data/warehouse/depth.db` | depth_bins 500 niveaux × 15 symboles (24/7, ~30 M lignes) — maturité 14 j le 06-07/10 | aster-depth-collector |
| `data/fomo/fomo.db` | fomo_ohlcv (1 353+ mints, 6,79 M bougies — mobula), fomo_tokens, fomo_ticks, fomo_new_coins (age_minutes), fomo_positions/closed/events, whale_flow, fomo_price_history | tick collector 24/7, mobula-topup 15 min (sélectif + topup_dead), harvest nocturne |
| `data/fomo/fomo_swaps.db` | 12 562+ swaps baleines (13 traders, pagination lastSwapId) | fomo-swaps-fresh (horaire) |
| `data/fomo/fomo_paper.db` | le ledger forward fomo (102+ trades : 3 horizons + anti-rug + replication_derek) | fomo-paper-forward 15 min |
| `data/warehouse/x_posts.db` | le registre X (les récoltes midi/nuit) | X harvest |
| **archivées** | backtest.db (legacy juin), klines_audit_*.db (side-DB d'audits), x.db/onchain.db (0 octet) | — |

LA RÈGLE DE CONFLIT : un écrivain par DB — les passes lourdes (backfills) prennent la fenêtre exclusive (stop systemd VÉRIFIÉ), les passes courtes coexistent via WAL + busy_timeout.
