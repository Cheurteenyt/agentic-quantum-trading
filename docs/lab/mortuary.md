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

## OpenMarket — les familles tuées (vagues 5-11, 27-28/09)

| Famille | Verdict | Date | Preuve |
|---|---|---|---|
| **Flux taker natif + funding multi-années** | 12/12 KILL (AUC) | 27/09 | docs/30, vague 5 |
| **Absorption ordrebook proxy klines** | E3 vs E1 réfuté 0/4, ABS_DEPRIORISÉ | 27/09 | docs/31, vague 6 |
| **VWAP session + volume profile veille** | 55 KILL / 1 INCONCLU / 0 CANDIDAT | 27/09 | docs/32, vague 7 |
| **OI 1h — capital brut + mouvement financé** | 10/10 KILL (AUC 0,49-0,50) | 27/09 | docs/33, vague 8 |
| **OI z-score roulant (contexte régime)** | H_R1 refusée, direction 4/4 KILL | 27/09 | docs/34, vague 9 |
| **OI U-shape (le côté bas CANDIDAT L2160)** | U joint non établi, miroir 4/4 KILL | 27/09 | docs/35, vague 10 |
| **LSR contrarian Bybit 4h/1d** | 4/4 + réplication 4/4 KILL | 28/09 | docs/36, vague 11 |

## OpenMarket — les familles tuées (vagues 5-11, 27-28/09)

| Famille | Verdict | Preuve |
|---|---|---|
| Flux taker natif + funding multi-années | 12/12 KILL (AUC) | docs/30 vague 5 |
| Absorption ordrebook proxy klines | E3 vs E1 réfuté 0/4 | docs/31 vague 6 |
| VWAP session + volume profile veille | 55 KILL / 0 CANDIDAT | docs/32 vague 7 |
| OI 1h capital brut + mouvement financé | 10/10 KILL | docs/33 vague 8 |
| OI z-score roulant (contexte régime) | H_R1 refusée, 4/4 KILL | docs/34 vague 9 |
| OI U-shape (côté bas CANDIDAT L2160) | U non établi, miroir KILL | docs/35 vague 10 |
| LSR contrarian Bybit 4h/1d | 4/4 + réplication KILL | docs/36 vague 11 |
