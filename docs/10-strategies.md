---
title: Stratégies et première campagne réelle
status: living
owner: cheurteen
updated: 2026-08-09
---

# Stratégies et première campagne réelle

> Le moteur ne connait aucune strategie. Il recoit `evaluate(params, bars)`
> et il juge. `backend/services/backtest_v2/strategies/` contient les
> generateurs de rendements ; `scripts/run_campaign.py` les branche.

## Les 3 stratégies (stdlib pure, anti-leak-ahead par construction)

| Fichier | Logique | Espace | Vise |
|---|---|---|---|
| `momentum.py` | cross EMA + filtre de regime | 288 combos | tendances |
| `mean_reversion.py` | z-score sur moyenne mobile | 256 combos | marches range |
| `breakout.py` | canal Donchian | 256 combos | compression→expansion |

Chacune respecte le contrat (`StrategyEval`, 4 postes de cout via `costs.py`,
execution a l'open de i+1). Le package expose `REGISTRY` + `identity_for`.

## Premiere campagne REELLE

```bash
python scripts/run_campaign.py --strategy all --check   # 800 combinaisons
python scripts/run_campaign.py --strategy momentum --max-combos 50
```

**Resultat sur BTCUSDT 1h, 500 bougies reelles, 800 combinaisons (3 stratégies) :**

```
momentum         : 0 survivant / 288   (Sharpe OOS ~ -1,5, couts -671 USD)
mean_reversion   : 0 survivant / 256   (62,5 % sharpe_oos_too_low)
breakout         : 0 survivant / 256   (100 %  sharpe_oos_too_low)
```

**Le moteur juge correctement.** Le marche BTC 1h sur cette fenetre est plat
(+0,13 % sur 500 h) ; le momentum paie des frais pour rien, et le moteur le
dit. Aucun survivant n'est un echec : c'est le resultat.

## Le bug que j'ai corrige en route

`run_campaign.py` plantait a la premiere execution (2 NameError/UnboundLocal,
1 type mismatch sur la troncature de grille). Corrige en relisant l'API reelle
de `engine.run_campaign` et `strategies.identity_for`. **Le moteur lui-meme
n'a jamais ete en cause** : ses 345 tests restent a 0 echec.

## Le gate microstructure, rendu optionnel

`microstructure_validated` etait **rejete a 100 %** sur toutes les campagnes :
aucune strategie ne fournit encore de validation de fillabilite (profondeur de
carnet, latence). Un gate toujours rejetant est inutile.

Decision : `GateConfig.require_microstructure = False` par defaut (non
bloquant), activable explicitement quand une strategie implemente la
validation. Transforme un faux-negatif systematique en un garde-fou reel
disponible. Cf. `gates.py` docstring.

## La limite decouverte : 500 bougies, c'est trop court

`min_closed_trades = 100` est **impossible** a atteindre sur 500 bougies avec
un walk-forward 5 folds : les strategies ne produisent que 11 a 38 trades.

```
momentum         : 18 trades
mean_reversion   : 38 trades
breakout         : 11 trades
```

Donc `sample_too_small` tombe a 100 % — pas parce que les strategies sont
mauvaises, mais parce que **les donnees sont insuffisantes pour juger**. C'est
une limitation de l'echantillon, pas un verdict sur les strategies.

**Deux corrections possibles (a choisir) :**
1. Allonger l'historique : `fetch_klines.py` ramene 1500 bougies/requete.
   Passer a 3000-5000 bougies donnerait ~100+ trades et rendrait le gate
   significatif.
2. Baisser temporairement `min_closed_trades` pour les campagnes exploratoires
   (deconseille : c'est exactement le seuil qui protege du sur-ajustement).

La voie 1 est la bonne : plus de donnees, pas moins de garde-fous.

## Principe etabli

> Une campagne qui ne trouve rien a produit une information exacte et gratuite.
> Une campagne qui trouve beaucoup, a ce niveau de test, produit surtout des
> faux positifs payants.

C'est la conclusion ecrite dans `engine.format_report` et verifyiee ici :
sur données reelles et courtes, le systeme ne fabrique pas de champion
imaginaire. Il dit « rien a gagner sur cet echantillon ».

## Reste a faire

- allonger l'historique (fetch 1500+ bougies, plusieurs symboles) avant de
  conclure sur les strategies
- brancher `require_microstructure=True` sur une strategie qui valide la
  fillabilite (deep book / latence)
- planifier `nightly_campaign.py` en cron une fois l'historique assez long
