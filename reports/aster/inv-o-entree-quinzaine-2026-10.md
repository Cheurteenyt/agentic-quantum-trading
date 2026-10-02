# INV-O « L'ENTRÉE À LA QUINZAINE » — le raffinement 15m à l'intérieur de la bougie d'entrée

**VERDICT : FAIL — hypothèse réfutée** (réfutation RÉPLIQUÉE et MONOTONE, TRAIN et VAL).

Étude d'EXÉCUTION (amplificateur des stratégies vivantes — PAS un signal nouveau).
Domaine Aster, gouvernance docs/38, tag `freeze-2026-10-02`. Date : 02/10/2026.
Budget : **1 expérience consommée** — un seul raffinement testé, STOP, aucune variante
de la règle ne sera testée (PARAMETER_MUTATION).
Script one-shot : `scripts/studies/inv_o_entree_quinzaine.py` (modules machine réutilisés
EN LECTURE : `collect_featured` + `add_rolling_scores` + `collect_vol_spike` ; klines.db
ouverte en lecture seule uri mode=ro ; the_machine.py intact, mae_state.json non écrit).

**Seal du pré-enregistrement** : sha256 du texte exact de la section suivante =
`df11bc059048797c84cc1e666858bfe52778052177699caa1233850813fa85a9` (calculé sur le bloc PRÉ-ENREGISTREMENT tel qu'imprimé par le script AVANT
toute mesure ; ré-exécution du calcul au moment du rapport, digest identique).

---

## PRÉ-ENREGISTREMENT (écrit AVANT toute mesure — seal ci-dessus)

```
INV-O « L'ENTRÉE À LA QUINZAINE » — étude d'EXÉCUTION (one-shot, gel freeze-2026-10-02).

════════════════════════════════════════════════════════════════════════
PRÉ-ENREGISTREMENT (écrit AVANT toute mesure — rien ci-dessous n'est
calculé avant d'avoir imprimé ce bloc ; le seal sha256 du rapport couvre
ce texte exact).
════════════════════════════════════════════════════════════════════════
DOMAINE : Aster, gouvernance docs/38 (tag freeze-2026-10-02). Étude
d'EXÉCUTION (amplificateur des stratégies vivantes), PAS un signal
nouveau. Budget : 1 expérience, un seul raffinement testé.

FAMILLES MORTES VÉRIFIÉES (research/registry.yaml + docs/20) :
INV-A..M toutes REJECTED — aucune ne touche la sous-granularité
d'exécution. La loi gravée « open = optimum entrée+sortie » a été
mesurée à la granularité 1h ; INV-O pose la question JAMAIS posée :
à l'INTÉRIEUR de la bougie d'entrée, la sous-granularité 15m native
fait-elle mieux ? Aucune variante de seuil d'aucune famille morte
n'est réintroduite.

HYPOTHÈSE (pré-déclarée) :
  le raffinement 15m améliore l'espérance nette d'au moins +3 bps/entrée
  vs l'open 1h, SANS augmenter le MAE max du flux gated (la règle 0-liq
  doit tenir : le MAE gated ne monte pas).

RÈGLE DE CHOIX (UNE seule, zéro grille — pré-déclarée) :
  k* = premier k ∈ {1,2,3} tel que le close de la k-ième bougie 15m
  native de l'heure d'entrée est DU CÔTÉ de l'open 1h
  (LONG : close15m_k > open1h ; SHORT : close15m_k < open1h ; égalité =
  ni l'un ni l'autre, k sauté ; bougie 15m manquante = k sauté).
  Entrée = close15m_k*. Si aucun k ne qualifie → entrée à l'open 1h
  (fallback, identique bit-à-bit à la référence).
  CONTRÔLE INVERSE : miroir exact — premier k dont le close est CONTRE
  notre côté (LONG : close < open ; SHORT : close > open), sinon open.

POPULATION (mêmes signaux, MÊME moteur, seule l'exécution change —
une variable) :
  - flux 1 machine rejoué bit-à-bit EN LECTURE : cascade majors
    (collect_featured + add_rolling_scores + gate AL q66 sur les
    premiers 70 % d'événements, code exact de the_machine.main, sans
    l'écriture mae_state.json) — SHORT, hold 24h, entrée open t+1,
    exit close t+24 inchangé ;
  - flux 4 machine : vol_spike 6h (collect_vol_spike, hold=6, gate ATR
    p90 inclus) — long/short, entrée open t+1, exit close t+6 inchangé.
  Ensemble ÉVALUABLE : entrées dont l'heure d'entrée contient au moins
  une bougie 15m native pour le symbole (les heures sans 15m natif sont
  exclues et comptées — les deux bras y seraient identiques).

PROTOCOLE IMMUTABLE :
  - split 60/40 chrono GLOBAL (une seule estampe, ensemble évaluable
    poolé, les deux flux confondus) ;
  - coûts 18 bps RT identiques des deux côtés (étalon du domaine ;
    les frais machine propres — MAKER 4 / TAKER 28 — s'annulent dans
    le Δ, l'écart des bras en est invariant) ; espérance nette =
    ret directionnel brut (bps) − 18 bps ; funding exclu (fenêtre
    identique ±45 min, deuxième ordre, déclaré) ;
  - exit bit-exact : même close 1h que la référence (le plan de sortie
    ne change pas) ; seule l'ESTAMPE et le PRIX d'entrée changent ;
  - MAE : chemin depuis le prix d'entrée réel jusqu'au exit — à
    l'intérieur de l'heure d'entrée sur la grille 15m native (bougies
    strictement postérieures à la bougie d'entrée ; entrée à l'open =
    bougies 1..4 présentes), ensuite bougies 1h ei+1..exit ;
    LONG : (entry − min low)/entry ; SHORT : (max high − entry)/entry,
    borné à ≥ 0 ; le close d'entrée 15m est dans [low, high] de son
    heure par construction ;
  - critère MAE jugé sur TRAIN (le levier 0-liq se calibre sur TRAIN,
    doctrine) : max MAE gated variante ≤ max MAE gated référence ;
    VAL rapporté en descriptive ;
  - n ≥ 100 entrées TRAIN sinon « SOUS-PUISSENT » déclaré — aucun PASS
    possible ;
  - BLOC STATS mensuel par bras × split (notionnel 1x additif :
    trades, WR net, somme/moyenne bps nets, pire/record mois, mois
    négatifs) ; chevauchements vol_spike inclus des deux côtés — ce
    n'est PAS un wallet séquentiel (le run_stack ne sert qu'une
    promotion éventuelle, jamais le verdict d'exécution) ;
  - PASS (écrits AVANT) : C1 Δespérance nette (variante − référence)
    ≥ +3 bps en TRAIN ET en VAL ; C2 max MAE gated TRAIN variante
    ≤ référence (inchangé ou réduit) ; C3 contrôle inverse battu
    (Δrègle > Δcontrôle) en TRAIN ET en VAL.
  - FAIL = tout le reste → « FAIL — hypothèse réfutée », gravé, STOP.
  - QA : unités open_time (ms) vérifiées sur 1h ET 15m (leçon ts_ms) ;
    cohérence 1h-high vs max(15m highs) de l'heure d'entrée ; référence
    bit-à-bit contre les champs machine (entry/exit/price_ret) ;
    bougies 15m manquantes comptées.

INTERDITS respectés : data/fomo/ intact, aucun service, aucun install,
pas de & ; klines.db ouverte en lecture seule (uri mode=ro) pour les
requêtes propres du script ; les modules machine ne font que SELECT.
════════════════════════════════════════════════════════════════════════
```

---

## EXÉCUTION (après pré-enregistrement)

### QA (toutes passées)
- unités temporelles (leçon ts_ms) : `open_time` en **ms** côté klines.db, mais les
  événements machine portent `ts_ms` en **NANOSECONDES** (nom hérité, cf. anti_liq
  « ts_ms = des NS ») — normalisation ns→ms AVANT tout join ; 0 bougie 15m manquante
  dans les heures couvertes (0 fill-forward, recherche par existence pile).
- référence bit-à-bit : le bras référence (open 1h) reproduit EXACTEMENT les champs
  machine (`entry`, `exit`, `price_ret_short`) sur 4 162 entrées — assert passé 4 162/4 162.
- cohérence collecteurs : écart max |1h-high − max(15m highs)| de l'heure d'entrée =
  1,39 % (quelques heures de désalignement 1h/15m — sans effet sur le verdict : les
  DEUX bras utilisent la même grille fine).
- MAE de référence contre champ machine : max `mae_adverse` (1h) des 901 gated =
  **22,58 %** = exactement le max fin-15m du bras référence sur TRAIN — le replay est
  validé contre la machine elle-même.

### Population (mêmes signaux, même moteur, seule l'exécution change)
- flux 1 : cascade majors gated (gate AL q66 = 0,7556 sur les premiers 70 % → 901
  événements, code exact de the_machine.main) — SHORT, hold 24h, exit close t+24
  INCHANGÉ.
- flux 4 : vol_spike 6h (7 888 événements, gate ATR p90 inclus) — long/short, exit
  close t+6 INCHANGÉ.
- ensemble ÉVALUABLE (≥ 1 bougie 15m native dans l'heure d'entrée) : **4 162** entrées
  (exclues sans 15m natif : 4 627 — les deux bras y seraient identiques bit-à-bit).
- split 60/40 chrono GLOBAL : **2 497 TRAIN / 1 665 VAL** — estampe 2025-03-11 15:00 UTC
  (n_train >> 100 : étude PUISSANTE, pas sous-puissante).
- histogramme de la règle : k=0 (fallback open) 1 329 · k=1 2 038 · k=2 551 · k=3 244.
- coûts : 18 bps RT identiques des deux côtés (étalon du domaine ; le Δ des bras est
  invariant aux frais) ; funding exclu (fenêtre identique ±45 min, déclaré).

## RÉSULTATS

### TRAIN (n = 2 497 — gated 611 / vol_spike 1 886)
| Bras | Espérance nette (bps/entrée) | Δ vs référence | MAE max gated |
|---|---|---|---|
| référence open 1h | **−14,03** | — | **22,58 %** |
| variante 15m (règle) | −53,01 | **−38,98** | 24,13 % |
| contrôle inverse | +27,10 | +41,13 | — |

Descriptif par flux (bps nets) : gated ref −26,90 / var −47,36 (Δ −20,46) / ctl −5,99
(Δ +20,91) ; vol_spike ref −9,86 / var −54,84 (Δ −44,98) / ctl +37,82 (Δ +47,68).

### VAL (n = 1 665 — gated 239 / vol_spike 1 426)
| Bras | Espérance nette (bps/entrée) | Δ vs référence | MAE max gated |
|---|---|---|---|
| référence open 1h | **−5,01** | — | **15,79 %** |
| variante 15m (règle) | −45,99 | **−40,97** | 16,25 % |
| contrôle inverse | +35,97 | +40,98 | — |

Descriptif par flux (bps nets) : gated ref −29,11 / var −41,78 (Δ −12,67) / ctl −15,43
(Δ +13,68) ; vol_spike ref −0,98 / var −46,69 (Δ −45,72) / ctl +44,58 (Δ +45,56).

## VERDICT MÉCANIQUE (critères écrits AVANT)

| Critère | Seuil pré-écrit | Mesuré (TRAIN / VAL) | Verdict |
|---|---|---|---|
| C1 Δespérance ≥ +3 bps | TRAIN ET VAL | −38,98 / −40,97 bps | **ECHEC** |
| C2 MAE max gated TRAIN variante ≤ référence | 0-liq tient | 24,13 % > 22,58 % | **ECHEC** |
| C3 contrôle inverse battu | TRAIN ET VAL | −38,98 < +41,13 / −40,97 < +40,98 | **ECHEC** |

**FAIL — hypothèse réfutée.** Réfutation RÉPLIQUÉE (Δ ≈ −39/−41 bps aux deux splits,
même magnitude = pas un artefact de régime), MONOTONE au bloc mensuel (la variante
dégrade 40/43 mois TRAIN et 18/20 mois VAL), et le contrôle inverse bat la référence
d'AUSSI LOIN (+41 bps) dans les deux splits — le mauvais côté 15m est un MEILLEUR
prix d'entrée, le bon côté un DÉGÉNERATEUR.

## BLOC STATS MENSUEL (notionnel 1x additif, chevauchements inclus — PAS un wallet
séquentiel ; le run_stack ne servirait qu'une promotion éventuelle, jamais ce verdict)

```
[BLOC STATS MENSUEL TRAIN] notionnel 1x additif (chevauchements inclus, pas un wallet séquentiel)
  référence open     n=2497 WR 48.8 % | mois: 43 | somme bps -35031 | pire mois -170.15 bps/entrée | record +63.59 | négatifs 27/43
    | Mois | Trades | WR | bps somme | bps moyenne |
    | 2021-09 | 21 | 38 % | -1413.9 | -67.33 |
    | 2021-10 | 33 | 27 % | -5614.9 | -170.15 |
    | 2021-11 | 36 | 53 % | +398.4 | +11.07 |
    | 2021-12 | 34 | 47 % | -2023.4 | -59.51 |
    | 2022-01 | 114 | 52 % | -2477.3 | -21.73 |
    | 2022-02 | 26 | 46 % | -3089.8 | -118.84 |
    | 2022-03 | 21 | 57 % | -1048.6 | -49.93 |
    | 2022-04 | 31 | 55 % | +638.2 | +20.59 |
    | 2022-05 | 105 | 50 % | +3707.4 | +35.31 |
    | 2022-06 | 110 | 50 % | -645.1 | -5.86 |
    | 2022-07 | 32 | 56 % | +454.4 | +14.20 |
    | 2022-08 | 38 | 42 % | -164.0 | -4.31 |
    | 2022-09 | 47 | 36 % | -3583.0 | -76.23 |
    | 2022-10 | 51 | 63 % | +2034.6 | +39.89 |
    | 2022-11 | 103 | 53 % | +1967.3 | +19.10 |
    | 2022-12 | 59 | 42 % | -1039.0 | -17.61 |
    | 2023-01 | 85 | 44 % | -7847.4 | -92.32 |
    | 2023-02 | 83 | 45 % | -2558.5 | -30.83 |
    | 2023-03 | 99 | 57 % | +2070.5 | +20.91 |
    | 2023-04 | 50 | 62 % | +1179.6 | +23.59 |
    | 2023-05 | 35 | 63 % | +294.7 | +8.42 |
    | 2023-06 | 59 | 54 % | -75.4 | -1.28 |
    | 2023-07 | 35 | 54 % | +2225.5 | +63.59 |
    | 2023-08 | 46 | 59 % | +1110.4 | +24.14 |
    | 2023-09 | 34 | 44 % | -1239.2 | -36.45 |
    | 2023-10 | 54 | 65 % | +1526.7 | +28.27 |
    | 2023-11 | 48 | 38 % | -1383.9 | -28.83 |
    | 2023-12 | 46 | 39 % | -3465.7 | -75.34 |
    | 2024-01 | 67 | 55 % | -1908.8 | -28.49 |
    | 2024-02 | 40 | 60 % | +759.8 | +18.99 |
    | 2024-03 | 69 | 36 % | -506.5 | -7.34 |
    | 2024-04 | 82 | 52 % | +4200.5 | +51.23 |
    | 2024-05 | 51 | 45 % | -1513.6 | -29.68 |
    | 2024-06 | 42 | 45 % | -1661.6 | -39.56 |
    | 2024-07 | 49 | 43 % | -530.4 | -10.82 |
    | 2024-08 | 101 | 44 % | -3264.5 | -32.32 |
    | 2024-09 | 35 | 43 % | -1661.4 | -47.47 |
    | 2024-10 | 39 | 49 % | +552.5 | +14.17 |
    | 2024-11 | 58 | 36 % | -2232.1 | -38.48 |
    | 2024-12 | 75 | 48 % | -762.2 | -10.16 |
    | 2025-01 | 101 | 51 % | +1335.7 | +13.22 |
    | 2025-02 | 96 | 50 % | -1372.9 | -14.30 |
    | 2025-03 | 57 | 40 % | -6404.6 | -112.36 |
  variante 15m       n=2497 WR 42.5 % | mois: 43 | somme bps -132357 | pire mois -181.37 bps/entrée | record +27.81 | négatifs 40/43
    | Mois | Trades | WR | bps somme | bps moyenne |
    | 2021-09 | 21 | 33 % | -2654.3 | -126.39 |
    | 2021-10 | 33 | 24 % | -5985.2 | -181.37 |
    | 2021-11 | 36 | 44 % | -935.6 | -25.99 |
    | 2021-12 | 34 | 41 % | -3168.3 | -93.19 |
    | 2022-01 | 114 | 43 % | -9082.8 | -79.67 |
    | 2022-02 | 26 | 46 % | -3478.6 | -133.79 |
    | 2022-03 | 21 | 52 % | -1849.3 | -88.06 |
    | 2022-04 | 31 | 52 % | -64.7 | -2.09 |
    | 2022-05 | 105 | 41 % | -2147.5 | -20.45 |
    | 2022-06 | 110 | 45 % | -6674.6 | -60.68 |
    | 2022-07 | 32 | 50 % | -378.4 | -11.83 |
    | 2022-08 | 38 | 37 % | -1384.8 | -36.44 |
    | 2022-09 | 47 | 32 % | -4841.5 | -103.01 |
    | 2022-10 | 51 | 59 % | +773.6 | +15.17 |
    | 2022-11 | 103 | 47 % | -3098.6 | -30.08 |
    | 2022-12 | 59 | 39 % | -3049.2 | -51.68 |
    | 2023-01 | 85 | 40 % | -10539.2 | -123.99 |
    | 2023-02 | 83 | 36 % | -4893.6 | -58.96 |
    | 2023-03 | 99 | 46 % | -1383.8 | -13.98 |
    | 2023-04 | 50 | 52 % | -693.3 | -13.87 |
    | 2023-05 | 35 | 51 % | -252.2 | -7.21 |
    | 2023-06 | 59 | 46 % | -2727.0 | -46.22 |
    | 2023-07 | 35 | 54 % | +973.4 | +27.81 |
    | 2023-08 | 46 | 48 % | -428.7 | -9.32 |
    | 2023-09 | 34 | 35 % | -2072.9 | -60.97 |
    | 2023-10 | 54 | 52 % | -713.3 | -13.21 |
    | 2023-11 | 48 | 35 % | -2764.2 | -57.59 |
    | 2023-12 | 46 | 30 % | -4892.8 | -106.37 |
    | 2024-01 | 67 | 39 % | -4370.2 | -65.23 |
    | 2024-02 | 40 | 52 % | -450.4 | -11.26 |
    | 2024-03 | 69 | 32 % | -3964.2 | -57.45 |
    | 2024-04 | 82 | 50 % | +1122.9 | +13.69 |
    | 2024-05 | 51 | 37 % | -3333.3 | -65.36 |
    | 2024-06 | 42 | 43 % | -2939.9 | -70.00 |
    | 2024-07 | 49 | 37 % | -1895.9 | -38.69 |
    | 2024-08 | 101 | 37 % | -8120.0 | -80.40 |
    | 2024-09 | 35 | 40 % | -2390.5 | -68.30 |
    | 2024-10 | 39 | 44 % | -522.6 | -13.40 |
    | 2024-11 | 58 | 34 % | -4230.6 | -72.94 |
    | 2024-12 | 75 | 41 % | -3417.5 | -45.57 |
    | 2025-01 | 101 | 48 % | -4891.6 | -48.43 |
    | 2025-02 | 96 | 46 % | -5720.9 | -59.59 |
    | 2025-03 | 57 | 39 % | -8824.8 | -154.82 |
  contrôle inverse   n=2497 WR 54.4 % | mois: 43 | somme bps +67671 | pire mois -128.20 bps/entrée | record +118.98 | négatifs 15/43
    | Mois | Trades | WR | bps somme | bps moyenne |
    | 2021-09 | 21 | 38 % | -473.2 | -22.53 |
    | 2021-10 | 33 | 36 % | -4230.5 | -128.20 |
    | 2021-11 | 36 | 56 % | +1172.1 | +32.56 |
    | 2021-12 | 34 | 50 % | -531.4 | -15.63 |
    | 2022-01 | 114 | 58 % | +2208.8 | +19.38 |
    | 2022-02 | 26 | 50 % | -1942.8 | -74.72 |
    | 2022-03 | 21 | 57 % | -464.0 | -22.10 |
    | 2022-04 | 31 | 58 % | +1374.6 | +44.34 |
    | 2022-05 | 105 | 57 % | +9043.9 | +86.13 |
    | 2022-06 | 110 | 55 % | +5774.6 | +52.50 |
    | 2022-07 | 32 | 59 % | +2199.0 | +68.72 |
    | 2022-08 | 38 | 45 % | +1058.1 | +27.85 |
    | 2022-09 | 47 | 47 % | -1522.0 | -32.38 |
    | 2022-10 | 51 | 65 % | +3353.3 | +65.75 |
    | 2022-11 | 103 | 54 % | +7455.1 | +72.38 |
    | 2022-12 | 59 | 49 % | +1254.2 | +21.26 |
    | 2023-01 | 85 | 47 % | -2751.5 | -32.37 |
    | 2023-02 | 83 | 48 % | -542.9 | -6.54 |
    | 2023-03 | 99 | 64 % | +5956.8 | +60.17 |
    | 2023-04 | 50 | 64 % | +2284.4 | +45.69 |
    | 2023-05 | 35 | 63 % | +753.5 | +21.53 |
    | 2023-06 | 59 | 59 % | +1576.4 | +26.72 |
    | 2023-07 | 35 | 57 % | +3269.6 | +93.42 |
    | 2023-08 | 46 | 61 % | +2230.5 | +48.49 |
    | 2023-09 | 34 | 53 % | -719.9 | -21.17 |
    | 2023-10 | 54 | 67 % | +2608.3 | +48.30 |
    | 2023-11 | 48 | 48 % | +1066.5 | +22.22 |
    | 2023-12 | 46 | 43 % | -1573.5 | -34.21 |
    | 2024-01 | 67 | 60 % | +933.1 | +13.93 |
    | 2024-02 | 40 | 62 % | +2632.3 | +65.81 |
    | 2024-03 | 69 | 46 % | +3630.0 | +52.61 |
    | 2024-04 | 82 | 60 % | +9756.3 | +118.98 |
    | 2024-05 | 51 | 51 % | -147.9 | -2.90 |
    | 2024-06 | 42 | 48 % | -941.6 | -22.42 |
    | 2024-07 | 49 | 53 % | +864.4 | +17.64 |
    | 2024-08 | 101 | 54 % | +3827.3 | +37.89 |
    | 2024-09 | 35 | 46 % | -918.5 | -26.24 |
    | 2024-10 | 39 | 51 % | +1051.3 | +26.96 |
    | 2024-11 | 58 | 48 % | -278.6 | -4.80 |
    | 2024-12 | 75 | 60 % | +2802.0 | +37.36 |
    | 2025-01 | 101 | 54 % | +5100.7 | +50.50 |
    | 2025-02 | 96 | 59 % | +3282.9 | +34.20 |
    | 2025-03 | 57 | 46 % | -3811.0 | -66.86 |

[BLOC STATS MENSUEL VAL] notionnel 1x additif (chevauchements inclus, pas un wallet séquentiel)
  référence open     n=1665 WR 48.9 % | mois: 20 | somme bps -8348 | pire mois -147.22 bps/entrée | record +69.32 | négatifs 13/20
    | Mois | Trades | WR | bps somme | bps moyenne |
    | 2025-03 | 19 | 37 % | -942.0 | -49.58 |
    | 2025-04 | 73 | 48 % | -3929.1 | -53.82 |
    | 2025-05 | 50 | 46 % | -923.6 | -18.47 |
    | 2025-06 | 42 | 50 % | -1439.5 | -34.27 |
    | 2025-07 | 27 | 30 % | -663.5 | -24.57 |
    | 2025-08 | 32 | 38 % | -2623.5 | -81.98 |
    | 2025-09 | 43 | 35 % | -2610.4 | -60.71 |
    | 2025-10 | 63 | 35 % | -9275.1 | -147.22 |
    | 2025-11 | 55 | 56 % | +3812.5 | +69.32 |
    | 2025-12 | 81 | 48 % | -1531.1 | -18.90 |
    | 2026-01 | 107 | 53 % | -1098.9 | -10.27 |
    | 2026-02 | 99 | 58 % | +2123.0 | +21.44 |
    | 2026-03 | 94 | 51 % | +128.6 | +1.37 |
    | 2026-04 | 86 | 52 % | +2202.1 | +25.61 |
    | 2026-05 | 91 | 47 % | +2118.2 | +23.28 |
    | 2026-06 | 152 | 61 % | +8440.9 | +55.53 |
    | 2026-07 | 32 | 44 % | -1548.8 | -48.40 |
    | 2026-08 | 189 | 52 % | +5695.0 | +30.13 |
    | 2026-09 | 325 | 45 % | -6222.3 | -19.15 |
    | 2026-10 | 5 | 20 % | -60.3 | -12.05 |
  variante 15m       n=1665 WR 42.0 % | mois: 20 | somme bps -76568 | pire mois -200.07 bps/entrée | record +7.85 | négatifs 18/20
    | Mois | Trades | WR | bps somme | bps moyenne |
    | 2025-03 | 19 | 26 % | -1442.7 | -75.93 |
    | 2025-04 | 73 | 36 % | -7148.3 | -97.92 |
    | 2025-05 | 50 | 44 % | -2376.4 | -47.53 |
    | 2025-06 | 42 | 43 % | -2530.2 | -60.24 |
    | 2025-07 | 27 | 30 % | -1117.5 | -41.39 |
    | 2025-08 | 32 | 34 % | -3306.0 | -103.31 |
    | 2025-09 | 43 | 23 % | -3311.5 | -77.01 |
    | 2025-10 | 63 | 22 % | -12604.4 | -200.07 |
    | 2025-11 | 55 | 45 % | +431.8 | +7.85 |
    | 2025-12 | 81 | 41 % | -3748.5 | -46.28 |
    | 2026-01 | 107 | 48 % | -4294.9 | -40.14 |
    | 2026-02 | 99 | 52 % | -3497.2 | -35.33 |
    | 2026-03 | 94 | 47 % | -4180.1 | -44.47 |
    | 2026-04 | 86 | 44 % | -347.4 | -4.04 |
    | 2026-05 | 91 | 44 % | -179.2 | -1.97 |
    | 2026-06 | 152 | 50 % | +949.9 | +6.25 |
    | 2026-07 | 32 | 34 % | -2088.4 | -65.26 |
    | 2026-08 | 189 | 45 % | -3981.8 | -21.07 |
    | 2026-09 | 325 | 40 % | -21392.3 | -65.82 |
    | 2026-10 | 5 | 20 % | -402.9 | -80.59 |
  contrôle inverse   n=1665 WR 54.8 % | mois: 20 | somme bps +59890 | pire mois -75.24 bps/entrée | record +102.47 | négatifs 8/20
    | Mois | Trades | WR | bps somme | bps moyenne |
    | 2025-03 | 19 | 47 % | -366.2 | -19.27 |
    | 2025-04 | 73 | 51 % | -1349.0 | -18.48 |
    | 2025-05 | 50 | 50 % | +107.1 | +2.14 |
    | 2025-06 | 42 | 55 % | -548.9 | -13.07 |
    | 2025-07 | 27 | 41 % | -278.9 | -10.33 |
    | 2025-08 | 32 | 41 % | -1466.5 | -45.83 |
    | 2025-09 | 43 | 40 % | -1758.4 | -40.89 |
    | 2025-10 | 63 | 44 % | -4740.4 | -75.24 |
    | 2025-11 | 55 | 60 % | +5636.1 | +102.47 |
    | 2025-12 | 81 | 54 % | +1501.0 | +18.53 |
    | 2026-01 | 107 | 61 % | +5143.0 | +48.07 |
    | 2026-02 | 99 | 61 % | +7237.8 | +73.11 |
    | 2026-03 | 94 | 54 % | +4982.5 | +53.01 |
    | 2026-04 | 86 | 56 % | +6141.3 | +71.41 |
    | 2026-05 | 91 | 56 % | +4938.5 | +54.27 |
    | 2026-06 | 152 | 67 % | +14804.3 | +97.40 |
    | 2026-07 | 32 | 53 % | -983.5 | -30.73 |
    | 2026-08 | 189 | 58 % | +12932.2 | +68.42 |
    | 2026-09 | 325 | 51 % | +7956.2 | +24.48 |
    | 2026-10 | 5 | 40 % | +1.9 | +0.38 |
```

## LA LEÇON (gravée)

1. **La loi « open = optimum » survit à la sous-granularité** — elle était mesurée à
   la granularité 1h, elle tient À L'INTÉRIEUR de la bougie : attendre un close 15m
   « confirmé » du bon côté coûte ~39-41 bps/entrée, 2x l'étalon des coûts RT. La
   confirmation précoce paie le prix de la confirmation : le bounce/fade machine se
   joue à l'open, pas après le premier quart d'heure.
2. **Le contrôle inverse est le vrai enseignant (CONTEXTE, non actionnable)** : entrer
   quand le premier quart d'heure va CONTRE le trade (SHORT au-dessus de l'open 1h,
   fade au-delà du spike) améliore l'espérance de +41 bps aux deux splits — mécanique
   d'ABSORPTION cohérente avec les leçons gravées (INV-K : les attaques absorbées
   précèdent la continuation ; les clusters de prints fadent). C'était un CONTRÔLE,
   pas une hypothèse : toute réutilisation = nouveau pré-enregistrement + budget. Ce
   n'est PAS un signal de réparation du FAIL.
3. **MAE : le raffinement dégrade aussi le 0-liq** (+1,55 pt de MAE max gated TRAIN :
   24,13 % vs 22,58 %) — entrer plus tard au « mauvais prix confirmé » réduit la marge
   de levier au lieu de l'augmenter.
4. Honêteté panel : 4 627 entrées exclues (pas de 15m natif — BNB/XRP pré-08/2026,
   symboles sans 15m) ; désalignement 1h/15m résiduel max 1,39 % documenté ; incident
   de code de RAPPORT documenté (variable morte dans refine() repérée et retirée avant
   la 1re exécution ; ajout v2 d'une statistique descriptive (MAE machine + histogramme
   k) — chemin du verdict ré-exécuté bit-identique, diff nul sur les 3 critères).
5. Adjacence déclarée : INV-O ne ré-invente aucune famille morte (INV-A..M intactes) ;
   la famille cascade TF-court (28/09, NUL) touchait le SIGNAL 15m, pas l'EXÉCUTION
   intra-bougie des signaux 1h ; la famille exit (hold fixe optimum) inchangée.

**STOP.** Budget consommé. Aucune autre fenêtre 15m (1re/2e/3e prise séparément),
aucun autre flux, aucun seuil — la quinzaine est close.
