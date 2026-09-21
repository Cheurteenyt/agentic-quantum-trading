---
title: Pipeline automatisé — de la donnée au verdict
status: living
owner: cheurteen
updated: 2026-08-09
---

# Pipeline automatisé

> L'automatisation ne rend pas un backtest plus fiable. Elle rend un backtest
> faux **plus rapide**. C'est pourquoi les défenses ont été écrites avant
> l'orchestration.

## La chaîne

```
fetch_klines.py      données réelles + provenance + détection de trous
        ↓
engine.py            campagne : teste tout, ÉCRIT TOUT (gagnants et perdants)
        ↓
gates.py             juge UNE lane      (< 100 trades, overfit, coûts absents)
        ↓
multiplicity.py      juge LA CAMPAGNE   (10 000 essais → correction Bonferroni)
        ↓
candidates.py        juge LE TEMPS      (période OOS postérieure obligatoire)
        ↓
reporting.py         rapport avec dénominateurs, jamais un chiffre nu
        ↓
nightly_campaign.py  orchestration
```

**L'ordre n'est pas négociable.** Sauter la multiplicité industrialise le faux
positif. Sauter les candidats fait passer en live un résultat qui n'a jamais vu
de donnée inédite.

## Commandes

```bash
python scripts/fetch_klines.py --check
python scripts/fetch_klines.py --fetch --symbols BTCUSDT --interval 1h --limit 1500

python scripts/nightly_campaign.py --check     # le pipeline peut-il tourner ?
python scripts/nightly_campaign.py --review    # candidats mûrs à réévaluer
```

`--check` est le mode par défaut partout : **rien ne s'écrit sans demande
explicite.**

## `fetch_klines.py` — les données réelles

Warehouse SQLite `data/warehouse/klines.db`.

- `PRIMARY KEY (symbol, interval, open_time)` → un re-fetch ne duplique jamais
- `CHECK` SQL : prix > 0, `high >= low`, volume >= 0 — vérifié : le schéma
  refuse bien un prix négatif et un `high < low`
- `snapshot_id` de provenance stocké avec chaque barre — sans provenance, un
  run n'est pas reproductible
- **`detect_gaps()`** : un trou dans les bougies fausse un backtest
  *silencieusement*. C'est la pire des sorties, donc on refuse plutôt que de
  deviner.

État actuel (2026-09-21) : **10 paires × ~3000 bougies 1h réelles, 0 trou** —
refresh nocturne automatisé par le timer systemd.

## `candidates.py` — le temps comme validateur

Un survivant de campagne n'est pas une stratégie : c'est un **candidat**.

Règle de confirmation (les trois conditions, sinon rejet motivé) :
```
forward_sharpe >= 0,5
forward_trades >= 100
forward_sharpe >= 0,5 × sharpe_oos_discovery
```

`pending(min_age_days=30)` ne renvoie que les candidats découverts il y a plus
de 30 jours. **Évaluer immédiatement reviendrait à réutiliser les données de la
découverte** — le contraire d'une validation.

`forward_sharpe = None` → rejeté. Non mesuré n'est jamais un pass.

## `reporting.py` — jamais un chiffre nu

Règle unique : **aucun chiffre sans son dénominateur.** « 2 survivants » est
interdit ; « 2 survivants / 24 testées (8,3 %) » est obligatoire.

`health_flags()` produit des alertes en français explicite :

```
! TAUX D'ACCEPTATION SUSPECT : compatible avec du bruit pur — 1231 acceptées
  / 10000 (12,3 %) alors qu'un tirage aléatoire à alpha=5 % en produirait déjà
  500 / 10000 (5,0 %).

! CAMPAGNE NON CORRIGÉE DE LA MULTIPLICITÉ : à ce volume, obtenir un
  « gagnant » par hasard est l'issue la plus probable.
```

Les sections sont triées par sévérité — `critical` en premier, parce qu'un
rapport lu à 8h du matin doit livrer le danger avant le détail. Sortie Discord
découpée sous 1900 caractères sans jamais couper un bloc de code.

## Test de bout en bout

Scénario réel rejoué : 10 000 combinaisons sur du bruit pur.

```
gates              : 1231 survivants / 10000 (12,3 %)
multiplicité       :    0 / 1231
candidats créés    :    0
rapport            : reports/campaign-nuit-bruit-*.md
```

**1231 « stratégies gagnantes » entrent, zéro candidat sort.** La chaîne fait
exactement son travail.

## Le premier résultat sur données réelles

BTCUSDT 1h, 500 bougies réelles, momentum net de frais :

```
prix 64677 → 64764  (+0,13 %)     volatilité annualisée 27,7 %
buy & hold net de frais           +0,0005

ma_5_20     -0,0375   28 trades   WR 46 %
ma_10_50    -0,0778   11 trades   WR 27 %
ma_20_100   -0,1070    7 trades   WR 14 %
ma_12_26    -0,0911   18 trades   WR 33 %
```

**Les quatre configurations perdent.** Sur un marché plat (+0,13 % sur 500
heures), le momentum paie des frais pour rien — c'est le comportement attendu,
et c'est un résultat honnête.

Aucune de ces lanes n'aurait passé les gates de toute façon (7 à 28 trades,
loin des 100 requis).

> Le pipeline produit sa première vérité : sur ces données, il n'y a rien à
> gagner. C'est exactement le livrable de valeur défini dans
> `03-methodology.md`.

## Ce que le pipeline ne fait PAS

`review_candidates()` **liste** les candidats mûrs, il ne les évalue pas. La
réévaluation exige de rejouer une stratégie concrète sur les données arrivées
depuis. Exposer le travail à faire plutôt que le simuler est délibéré : une
fausse confirmation automatique serait pire que pas de confirmation du tout.

## Reste à faire

- brancher une vraie stratégie sur `engine.py` (le moteur ne connaît aucune
  stratégie, par conception)
- élargir le warehouse : plusieurs symboles, plusieurs intervalles, historique
  plus long (1500 barres par requête)
- planifier `nightly_campaign.py` en cron une fois qu'une stratégie réelle est
  branchée
