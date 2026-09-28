---
title: Stratégies non-directionnelles et bilan complet
status: archived (28/09 — l'ère pré-refonte, voir docs/README.md)
owner: cheurteen
updated: 2026-08-09
---
> **LIRE AUSSI (la vérité à jour)** : docs/10-strategies.md + docs/20-registre-indicateurs.md


# Stratégies non-directionnelles et bilan complet

> Pivot du 2026-08-09 : les 3 familles directionnelles ne performent pas sur
> BTC/ETH/SOL 1h. On a teste les edges STRUCTURELS des perpetuals.

## Les 3 strategies non-directionnelles (agents delegates, verifiees)

| Strategie | Edge capture | PARAM_SPACE | Tests |
|-----------|--------------|-------------|-------|
| `funding_carry` | detient le cote qui encaisse le funding (short si >0, long si <0) | side_filter/hold_max_bars/stop/lev = 6 | 23 |
| `funding_fade` | mean-reversion SUR le funding (z-score extrem -> revient) | lookback/entry_z/exit_z/stop/lev = 48 | 29 |
| `volatility_harvesting` | market-making simule : capture high-low intra-barre | spread_bps/lev = 6 | 24 |

Coordonnees reelles du funding (cache frais) : BTC +0,46 bps/8h, ETH +0,30
bps/8h. SOL perime (ignore).

Notes d'implementation :
- `funding_carry` : sens collecteur resolu depuis le signe du funding (exogene
  au prix) -> anti-leak-ahead garanti (muter la derniere barre ne change rien).
- `funding_fade` : la serie de funding par barre est SYNTHETIQUE deterministe
  (3 sinusoides + enveloppe, phase = crc32(symbol)) centree sur la moyenne du
  cache. Approximation documentee dans le blob (`funding_series_synthetic`).
- `volatility_harvesting` : PnL = max(0, (high-low) - spread) ; 0 si fourchette
  < spread -> pas de trade, pas de cout.

## Resultat des campagnes reelles (3 paires, ~9000 bougies)

```
funding_carry        : 0 survivant / 36
funding_fade         : 0 survivant / 144
volatility_harvesting: 0 survivant / 18
```

**Campagne globale (all, 3 paires) : 2598 combinaisons testees -> 0 survivant.**

Aucun edge structurel mesurable non plus. Les raisons :
- `funding_*` : le funding moyen (+0,3/+0,46 bps/8h) est TROP FAIBLE pour
  compenser les frais de detention (8 bps RT + slippage) sur des positions
  qui traînent des jours. L'edge existe en theorie mais est mangé par les couts.
- `volatility_harvesting` : la fourchette intra-barre 1h, moins spread + frais,
  ne suffit pas. Le market-making reel exige un carnet (bid/ask) et une
  execution maker — ici on simule sur high-low, donc l'edge est surestime
  puis annule par les couts taker.

## Bilan du pipeline (etat final)

```
fetch pagine (3 paires, 3000 bougies chacune, 0 trou)
  -> engine (walk-forward 5 folds, 8 gates)
  -> multiplicity (audit GLOBAL tous symbols+strategies)
  -> candidates (registry 30j, decouverte vs reeval)
  -> reporting + run_campaign (multi-paires)
```

6 strategies enregistrees, 421 tests backtest_v2 + 53 fetch = **474 tests, 0 echec**.

## Ce que ca prouve (le vrai resultat)

Le systeme a refuse le bruit (demo 10000 bougies sur bruit pur), refuse le
sous-echantillon (garde ajoutee), refuse le re-selection-bias (multiplicite
globale), et dit NON de facon significative sur 2598 combinaisons reelles.

C'est une information exacte et gratuite : **sur cet univers (3 paires, 1h,
~125 jours), aucune des 6 strategies testees ne genere d'edge net apres couts
et correction de multiplicité.** Ce n'est pas un bug — c'est la reponse du
marche. Continuer a marteler ces familles = EV negatif.

## Ou on va (decisions restantes)

1. **Intervalles autres** : 15m (microstructure, MM plus fin), 4h (regimes
   longs). Un edge peut exister a une frequence ou l'autre.
2. **Plus de paires** : altcoins volatils (edge directionnel plus probable),
   ou perp exotiques avec funding structurellement eleve.
3. **Microstructure reelle** : brancher `require_microstructure=True` avec un
   vrai carnet (bid/ask) pour `volatility_harvesting` et `funding_*` -> l'edge
   de market-making devient mesurable au lieu de simule.
4. **Edges encore non testes** : perp basis (spot vs perp), funding arbitrage
   cross-exchange, ou stat-arb pairs.
5. **Cron** : `nightly_campaign.py` quand l'univers est assez large et les
   strategies assez diverses pour qu'un vrai signal emerge.
