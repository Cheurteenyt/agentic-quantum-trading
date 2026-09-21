---
title: Campagne réelle, gardes et leçon de données
status: living
owner: cheurteen
updated: 2026-08-09
---

# Campagne réelle, gardes et leçon de données

> Le systeme peut maintenant dire non de facon significative. La lecon du
> 2026-08-09 : ce n'est pas le moteur qui manquait, c'etaient les donnees.

## Ce qui a ete corrige (ingeniosité, pas ajouts gratuits)

### 1. Refus sous-echantillonne (garde ajoutee)
La premiere campagne a tourne sur 500 bougies : 11-38 trades/lane, donc
`sample_too_small` tombait a 100 % — pas parce que les strategies etaient
mauvaises, mais parce que les donnees etaient trop courtes pour le
walk-forward 5 folds.

`run_campaign.py --check` mesure maintenant le nombre de trades REEL d'une
lane pilote (1ere combo de chaque strategie) et refuse poliment si < 100 :

```
BTCUSDT 1h : 500 barres  -> lane pilote = 38 trades < 100  -> INUTILISABLE
BTCUSDT 1h : 3001 barres -> lane pilote = ~600 trades      -> OK
```

Pas d'estimation theorique bidon : on evalue une lane et on compte.

### 2. Multiplicite GLOBALE (angle mort ferme)
`run_campaign` juge une strategie a la fois. Si on ne retenait que le meilleur
survivant *global*, on oubliait les 2 autres strategies dans le denominateur
-> re-selection bias, EXACTEMENT le piege du legacy.

`_run_all` agrege tous les survivants de toutes les strategies et applique
UNE seule correction de multiplicite sur le nombre TOTAL de combinaisons
testees (800, pas 256 par strategie). `audit_campaign` porte sur `n_tested`
global.

### 3. Fetch pagine (agent delegue)
`fetch_klines.py --fetch-range BTCUSDT --target-bars 3000` pagine par blocs de
1500. Resultat : **3001 bougies BTCUSDT 1h, 0 trou, provenance conservee.**

### 4. Gate microstructure optionnel
`require_microstructure=False` par defaut : aucune strategie ne valide encore
la fillabilite, donc ce gate etait toujours rejetant = inutile. Disponible
pour activation.

## Resultat de la campagne reelle (multi-paires, 3001 bougies chacune)

```
momentum        : 0 survivant / 288   (sample_too_small 58 % -> des lanes passent)
mean_reversion  : 0 survivant / 256   (sample_too_small 37 %)
breakout        : 0 survivant / 256   (sample_too_small 100 % : trades longs)
```

**Aucune strategie ne trouve d'edge significatif sur BTC 1h sur cette
fenetre.** C'est un resultat honnete, pas un bug. Le marche n'a favorise
aucune de ces trois classes sur 3001 bougies.

Point clé : avec 500 bougies, `sample_too_small` etait a 100 % (on ne pouvait
rien conclure). Avec 3001, il tombe a 37-58 % — le systeme DEVIENT capable de
dire oui. Le fait qu'il dise non est la reponse reelle du marche.

### Extension multi-symboles (ETH, SOL)

`fetch_klines.py --fetch-range ETHUSDT SOLUSDT --target-bars 3000` ->
3000 bougies chacune, 0 trou. `run_campaign.py` itere maintenant sur TOUTES les
paires : une campagne `all` teste 1632 combinaisons (800 par paire × 3
paires via troncature), et l'audit de multiplicite global porte sur ce total.

```
campagne globale (BTC+ETH+SOL, 40 combos/strategie) :
  testees     : 864 / 864
  survivants  : 0
  audit global : 1632 combinaisons testees -> 0 survivant
```

Le moteur refuse le bruit, refuse le sous-echantillon, refuse le
re-selection-bias multi-strategie ET multi-symbole. Il est pret a signaler un
vrai edge si le marche en produit un.

## Ce que ca prouve

> Une campagne qui ne trouve rien a produit une information exacte et
> gratuite. Une campagne qui trouve beaucoup, a ce niveau de test, produit
> surtout des faux positifs payants.

Le pipeline refuse le bruit (demo du 10000 sur bruit pur), refuse le
sous-echantillon (garde 1), et refuse le re-selection-bias (garde 2). Il est
desormais pret a signaler un vrai edge si le marche en produit un.

## Prochaines etapes logiques

1. **Plus de symboles** : ETHUSDT, SOLUSDT, puis altcoins volatils ou le
   edge est plus probable. `fetch_klines.py --fetch-range ETHUSDT --target-bars 3000`.
2. **Plus d'intervalles** : 15m, 4h — des regimes differents.
3. **Microstructure** : brancher `require_microstructure=True` sur une
   strategie qui valide la fillabilite (profondeur de carnet, latence).
4. **Cron** : `nightly_campaign.py` une fois l'historique assez long et
   plusieurs symboles couverts.
5. **Nouvelles familles** : si ces 3 classes ne performent pas, tester
   funding-rate arbitrage, perp basis, ou market-making — des edges plus
   structurels que directionnels.
