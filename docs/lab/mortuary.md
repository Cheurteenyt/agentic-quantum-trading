# Mortuary — familles d’idées mortes (ne pas retenter à l’identique)

Source de vérité détaillée des chiffres : `docs/20-registre-indicateurs.md`.  
Ici : **familles** pour bloquer les boucles agent / grilles inutiles.

Format d’une ligne :

```text
| famille | domaine | pourquoi mort | ne-pas-retenter-sauf-si |
```

## Seed (depuis registres / archive_studies existants)

| famille | domaine | pourquoi mort | ne-pas-retenter-sauf-si |
|---|---|---|---|
| cascade × funding conditionnel simple | ASTER | nul au registre | nouveau mécanisme funding *non* “high/low funding gate” |
| CVD slope / sweep volumique textbook | ASTER | H2/H3 NUL | feature maison non dérivée du CVD standard |
| buy_ratio absorption H1 | ASTER | nul, pas de sizing | pattern Aster natif (murs maxBid/maxAsk) déjà autre piste |
| wallet DD guard prop-firm | ASTER | 12/12 nul (coupe le rebond) | — |
| cascade fractal 15m/30m | ASTER | mur des coûts | — |
| hold hybride 24h/72h via swap baleine | ASTER | doctrine hold24h tient | — |
| funding dimension velocity/dispersion | ASTER | nul | — |
| sizing conditionnel régime (gate sec) | ASTER | contrôle inverse ambigu | sizing *continu* déjà machine |
| fomo lifecycle mobula brut 1m/15m | FOMO | bougies à nettoyer, verdict NUL | après nettoyage data *prouvé* |
| TA standard seul (RSI, VWAP session, z-score funding) | ALL | edge arbitrée / hors Rail A | composé avec primitive *maison* listée |

## Règle

Toute nouvelle étude dont le titre ou le mécanisme tombe dans une famille ci-dessus **sans** clause `sauf-si` satisfaite → refus avant run.

Mettre à jour ce fichier **le même jour** qu’un verdict NUL de famille nouvelle.
