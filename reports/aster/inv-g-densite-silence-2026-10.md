# INV-G — « LA DENSITÉ DE SILENCE » (pré-enregistrement + résultats)

- **Domaine** : Aster (panel cross-symboles, données klines.db en lecture seule)
- **Date de pré-enregistrement** : 2026-10-02, AVANT tout résultat (ce bloc écrit avant l'exécution du script)
- **Gouvernance** : docs/38-gouvernance-recherche.md, tag `freeze-2026-10-02` ; registre `research/registry.yaml` vérifié (grep silence / retours nuls / heures plates / densité de retour) : AUCUNE expérience antérieure → expérience GÉNUILEMENT nouvelle (pas une PARAMETER_MUTATION).
- **Adjacence déclarée** : T20 (01/10, reports/aster_orderflow_regimes.md) a mesuré la **densité de PRINTS du tape** (BTC/ETH seuls, 90 j d'aster_tape, FAIT descriptif, prédiction directionnelle NUL 0/8). Ici c'est autre chose : la **densité de RETOURS NULS par symbole** sur klines 1h profonds (5 ans de majeures + 1 an de memecoins), avec une **prédiction forward de MAGNITUDE jamais formulée** (T20 n'a testé que la direction 24 h). La proximité est thématique (le « calme »), la statistique, la donnée et la prédiction sont distinctes.
- **Script one-shot** : `scripts/studies/inv_g_densite_silence.py` (unique exécution, aucun re-run de variante autorisé)

## 1. Hypothèse pré-déclarée (MAGNITUDE, PAS DIRECTION)

**Leçon OI vague 10 appliquée : les extrêmes prédisent l'AMPLITUDE, jamais le sens.**

La liquidité qui s'en va laisse des heures plates : un symbole dont la **fraction d'heures « mortes »** (|ret| 1h < 0,05 %) sur les 72 dernières bougies devient **inhabituellement élevée** (S_t ≥ q90 TRAIN, un seul seuil, zéro grille) entre en **silence inhabituel**. Hypothèse : ce silence précède des **QUEUES PLUS ÉPAISSES** — l'**AMPLITUDE** forward 48-96 h (somme des |ret| 1h) des événements dépasse la **médiane inconditionnelle** de plus que l'**étalon 12,2 bps** (aller/retour taker). C'est un **CONDITIONNEUR DE TAILLE** (gate de magnitude pour dimensionner une exposition existante), **PAS un signal** — un tel gate ne vaut que s'il déplace l'amplitude attendue de plus que ce qu'un aller-retour taker coûte.

**SENS = 0** : toute séparation directionnelle détectée (dérive forward signée après silence) est enregistrée comme **CONTEXTE descriptif**, jamais comme un signal — pré-déclaré avant toute mesure.

## 2. Construction (une seule définition, zéro grille, jamais re-tunée)

- Données : `data/warehouse/klines.db` **LECTURE SEULE** (mode=ro) — table `klines` interval `1h`. **Leçon ts_ms vérifiée** : `open_time` est en **MILLISECONDES** (1630476000000 = 2021-09-01) — unité contrôlée par assertion avant tout calcul. Doublons (symbol, open_time) = 0 ; grille 1h alignée = 0 exception (3 sources cohabitent sans collision : aster, aster_klines_ws, aster_public_klines_fapi_v3).
- **Univers** (fixé sur la couverture de donnée AVANT toute statistique de résultat) : symboles avec **≥ 2 000 barres 1h** (≈ 83 j — assez profond pour remplir la fenêtre roulante 72 h + la fenêtre forward). Règle appliquée : **33 symboles** (BTC, ETH, SOL depuis 2021 ; ASTER depuis 2025-09 ; les memecoins depuis leur cotation). Exclus par la règle : CATE (1 002), MEME (667), PONS (896), PAID (117), QNT (89), SI (19), XDP (57), CT (15) barres. La composition exacte des 33 est imprimée par le script (triée, avec dates).
- **Retour horaire** : r_b = close(b)/close(b−1 h) − 1. Une **heure « morte »** = |r_b| < 0,05 % (= 5 bps, strict). **S_t** = fraction des **72 dernières bougies** (barres t−71 h … t) mortes — causal, ne regarde rien après t. Mesurable ssi les **168 barres contiguës t−72 h … t+95 h** existent (base du premier ret S = t−72 h ; base du premier ret A = t+47 h) — sinon la période est **exclue, comptée, documentée**.
- **Split 60/40 chrono GLOBAL** : T_split = percentile 60 des open_time **uniques poolés** tous symboles (un seul bornage temporel, non arrondi). TRAIN = t < T_split, VAL = t ≥ T_split.
- **Seuil unique** : q90 = quantile 90 (interpolation linéaire numpy, **non arrondi**) de la distribution S **TRAIN SEULEMENT** (périodes mesurables poolées). **Événement** = S_t ≥ q90. Un seul seuil, jamais recalculé en VAL.
- **Amplitude forward** : A_t = Σ des |r_b| (en **bps**) sur les 48 barres open_time ∈ [t+48 h ; t+95 h] — même convention que le bloc gelé INV-E. La fenêtre de silence (72 h avant t) et la fenêtre d'amplitude (48-96 h après t) sont disjointes : **aucune fuite possible**.
- **Δ|fwd|** = médiane(A | événements) − médiane(A | **toutes** les périodes mesurables du split considéré) — la médiane inconditionnelle est la référence du gate.
- **Contrôle inverse** : périodes S_t ≤ q10 TRAIN (le silence le plus faible). **Gradient** : quintiles de S_t (bornes q20/q40/q60/q80 TRAIN) → médiane(A) par quintile.

## 3. Protocole immutable

- **Pas de trade, pas de levier, pas de wallet séquentiel** : conditionneur de taille — 0 liquidation **par construction**. Le gate ne s'appliquerait qu'à une exposition d'une stratégie existante (gel : aucune promotion).
- **n_train ≥ 100 événements mesurés** sinon expérience déclarée **SOUS-PUISSENTE** telle quelle (échec de puissance ≠ réfutation).
- **BLOC STATS mensuel** obligatoire (mois | split | n événements | n toutes | médiane A événements | médiane A toutes | Δ).
- Limitation déclarée : les événements d'un même épisode de silence sont **corrélés dans le temps** (72 h de lookback se chevauchent) — n est traité comme des heures, la dépendance est documentée en limitation.

## 4. Critères PASS/FAIL (écrits AVANT les résultats)

**PASS = les quatre, sans exception :**
1. **Δ|fwd| médian TRAIN > 12,2 bps** (au-dessus de l'étalon A/R taker).
2. **Réplication VAL** : Δ|fwd| médian VAL > 0, **même signe** que TRAIN (la magnitude se réplique hors train).
3. **Gradient monotone** : quintiles de S_t sur les périodes mesurables TRAIN (Q1 → Q5) → médiane(A) **non décroissante** Q1 ≤ Q2 ≤ Q3 ≤ Q4 ≤ Q5 (VAL descriptif).
4. **Contrôle inverse battu** : médiane(A | S_t ≤ q10) < médiane(A | événements) sur **TRAIN ET VAL** — si les heures les moins silencieuses portent la même magnitude, le silence n'explique rien (amplitude ubiquitaire) et l'hypothèse est morte.

**FAIL = tout le reste** → « FAIL — hypothèse réfutée », gravé au registre, budget consommé, **STOP**. Pas de deuxième quantile, pas de fenêtre alternative, pas de filtre de réparation. Budget = 1 expérience.

**Si PASS** : verdict **CONTEXTE / CANDIDATE gate de sizing** — jamais un signal autonome ; SENS = 0 : toute séparation directionnelle observée = CONTEXTE non actionnable.

---

# RÉSULTATS (exécution unique du 02/10/2026)

> **Seal du pré-enregistrement** : sha256 du bloc ci-dessus, gelé AVANT exécution :
> `14f311c2ed4dd4a0bdb5c8772219905243712a18c42cf6a2a8a5469ce63f4668`


Note d'intégrité : deux incidents, aucun critère/seuil/fenêtre/protocole touché — le calcul gelé est resté bit-identique (les stats principales de la 1re impression et de l'exécution complète coïncident au dixième de bps près). (1) La 1re exécution a **crashé** dans le BLOC STATS mensuel (bug d'indexation de rapport : `ev & m` au lieu de `ev[m]`) — après l'impression des stats principales, zéro statistique perdue ou modifiée. (2) L'attribution descriptive des événements par symbole utilisait un dict `timestamp → symbole` **écrasé** par l'ordre alphabétique (XRP créditée de 83 588 événements = impossible, elle n'a que 8 956 barres) — corrigée en portant le symbole dans l'enregistrement lui-même. Les deux corrections sont du code de RAPPORT uniquement ; l'exécution corrigée complète est l'**exécution unique** de référence, aucun re-run de variante.

## Exécution

- Univers règle (≥ 2 000 barres 1h) : **33 symboles** — BTC/ETH/SOL profonds (2021-09/09/09 → 2026-10-02), ASTER (2025-09-18), les majeures et memecoins 2025-09 → 2026-10-02, les perps actions (GOOGL, NVDA) et les cotations 2026 (BOME, PNUT, TURBO, DOGS, WIF, NOT, H, PORTAL, DRAM, MELANIA, PIEVERSE, VIRTUAL, LAB, FARTCOIN, HYPE, MOODENG, NEIRO, PENGU, TRUMP). 8 exclus par la règle (CATE, MEME, PONS, PAID, QNT, SI, XDP, CT).
- **T_split = 2024-09-19 07:48 UTC** (44 564 timestamps uniques poolés, bornage non arrondi). Conséquence structurelle pré-visible du split global : TRAIN ne contient que les 3 symboles profonds (BTC/ETH/SOL), VAL contient les 33 — le seuil q90 est calibré sur la distribution des 3 majeures et appliqué au panel complet. Protocole gelé appliqué tel quel, conséquence documentée.
- Périodes mesurables (S et A) : **337 042** (TRAIN 79 668 / VAL 257 374), **0 exclue** (trou : 0 — la grille 1h est complète sur toute la couverture).
- **Seuil TRAIN** : q90(S_t) = **0,197183** = 14,2/72 heures mortes (q10 = 0,0282 ; quintiles q20/q40/q60/q80 = 0,0423/0,0704/0,0986/0,1549). INTERPRÉTATION : sur les majeures, être dans le q90 de silence = ≥ 15 heures plates sur 3 jours.
- **Événements : TRAIN 8 965 (11,3 % des heures TRAIN), VAL 86 286 (33,5 % des heures VAL)** — le taux VAL triple parce que le panel VAL ajoute 30 symboles structurellement plus plats (memecoins morts, perps actions) que les 3 majeures qui ont calibré le seuil. Taux d'événement global 28,3 % : la règle gelée transfère mal la calibration train → panel, documenté en limitation.
- Attribution (corrigée) : TRAIN = BTC 4 848 / ETH 3 028 / SOL 1 089 (la zone morte SOL post-FTX 2022-2023 porte ses mois) ; VAL top = NVDA 8 343, MOODENG 7 612, NEIRO 7 270, PNUT 5 850, BOME 5 649, TURBO 5 478, GOOGL 4 399, BTC 4 068 (n'apparaissent que les 8 premiers).

## Vérification des critères

| # | Critère (gelé) | Résultat |
|---|---|---|
| — | n_train ≥ 100 événements | **OK** (8 965) — expérience pleinement puissante, la réfutation vaut |
| 1 | Δ\|fwd\| médian TRAIN > 12,2 bps | **FAUX** — medA évts 1 247,2 vs médiane toutes 2 192,2 → **Δ = −945,0 bps** (les silences inhabituels sont SOUS la médiane de −43 %, à l'OPPOSÉ de l'étalon) |
| 2 | Δ\|fwd\| VAL > 0 même signe que TRAIN | **FAUX** — VAL Δ = **−413,1 bps** (medA évts 1 974,8 vs 2 388,0) : même signe que TRAIN mais négatif — la réplication est celle de la RÉFUTATION, pas de l'hypothèse |
| 3 | Gradient quintiles Q1 ≤ Q2 ≤ … ≤ Q5 (TRAIN) | **FAUX — inversé STRICTEMENT** : Q1 3 440,6 > Q2 2 762,3 > Q3 2 343,5 > Q4 1 929,7 > Q5 1 370,1 (VAL descriptif identique : 3 934,6 → 1 964,5) — l'amplitude forward DÉCROÎT monotoniquement avec le silence |
| 4 | Contrôle inverse battu (TRAIN ET VAL) | **FAUX** — TRAIN S_t ≤ q10 (n = 11 383) : medA **3 440,6 ≫ 1 247,2** (2,8× plus ample) ; VAL (n = 26 928) : 3 934,6 ≫ 1 974,8 — les heures les MOINS silencieuses portent les queues les plus épaisses |

**VERDICT : FAIL — hypothèse réfutée.** Les quatre critères sont faux, la réfutation est **répliquée dans les deux splits et monotone** : sur les klines 1h Aster, le silence inhabituel précède des queues plus **MINCES**, pas plus épaisses — l'inverse exact de l'hypothèse pré-déclarée. Budget = 1 expérience consommée, **STOP** : aucun 2e quantile, aucune fenêtre alternative, aucun filtre de réparation.

## BLOC STATS mensuel (médiane A en bps ; 0 liq par construction — pas de trade, pas de levier)

| Mois | Split | n evts | n toutes | medA evts | medA toutes | Delta |
|---|---|---|---|---|---|---|
| 2021-09 | TRAIN | 0 | 1 596 | — | 3 301,0 | — |
| 2021-10 | TRAIN | 0 | 2 232 | — | 2 639,7 | — |
| 2021-11 | TRAIN | 0 | 2 160 | — | 2 759,2 | — |
| 2021-12 | TRAIN | 1 | 2 232 | 1 521,1 | 2 616,8 | −1 095,7 |
| 2022-01 | TRAIN | 0 | 2 232 | — | 3 111,3 | — |
| 2022-02 | TRAIN | 0 | 2 016 | — | 3 296,6 | — |
| 2022-03 | TRAIN | 44 | 2 232 | 1 740,8 | 2 394,5 | −653,8 |
| 2022-04 | TRAIN | 47 | 2 160 | 2 110,8 | 2 067,5 | +43,3 |
| 2022-05 | TRAIN | 0 | 2 232 | — | 3 290,0 | — |
| 2022-06 | TRAIN | 0 | 2 160 | — | 4 187,6 | — |
| 2022-07 | TRAIN | 0 | 2 232 | — | 3 486,4 | — |
| 2022-08 | TRAIN | 11 | 2 232 | 1 657,6 | 2 483,9 | −826,3 |
| 2022-09 | TRAIN | 0 | 2 160 | — | 2 570,7 | — |
| 2022-10 | TRAIN | 314 | 2 232 | 1 194,4 | 1 620,1 | −425,7 |
| 2022-11 | TRAIN | 297 | 2 160 | 1 868,2 | 2 419,4 | −551,2 |
| 2022-12 | TRAIN | 658 | 2 232 | 751,0 | 1 251,5 | −500,5 |
| 2023-01 | TRAIN | 586 | 2 232 | 1 092,5 | 1 966,9 | −874,5 |
| 2023-02 | TRAIN | 266 | 2 016 | 2 243,9 | 1 797,8 | +446,1 |
| 2023-03 | TRAIN | 284 | 2 232 | 2 955,9 | 2 357,5 | +598,4 |
| 2023-04 | TRAIN | 402 | 2 160 | 1 540,6 | 1 593,5 | −52,9 |
| 2023-05 | TRAIN | 596 | 2 232 | 1 140,9 | 1 299,8 | −158,9 |
| 2023-06 | TRAIN | 437 | 2 160 | 1 425,5 | 1 602,7 | −177,3 |
| 2023-07 | TRAIN | 798 | 2 232 | 941,3 | 1 123,8 | −182,5 |
| 2023-08 | TRAIN | 1 277 | 2 232 | 876,8 | 1 185,6 | −308,8 |
| 2023-09 | TRAIN | 980 | 2 160 | 1 057,2 | 1 238,6 | −181,5 |
| 2023-10 | TRAIN | 653 | 2 232 | 1 180,1 | 1 480,5 | −300,4 |
| 2023-11 | TRAIN | 67 | 2 160 | 1 222,4 | 1 851,0 | −628,6 |
| 2023-12 | TRAIN | 75 | 2 232 | 1 432,5 | 2 066,4 | −633,9 |
| 2024-01 | TRAIN | 15 | 2 232 | 1 507,1 | 1 994,4 | −487,3 |
| 2024-02 | TRAIN | 82 | 2 088 | 1 628,2 | 2 078,2 | −450,1 |
| 2024-03 | TRAIN | 3 | 2 232 | 3 185,8 | 2 975,7 | +210,1 |
| 2024-04 | TRAIN | 0 | 2 160 | — | 2 836,4 | — |
| 2024-05 | TRAIN | 113 | 2 232 | 1 464,4 | 1 903,1 | −438,7 |
| 2024-06 | TRAIN | 792 | 2 160 | 1 649,7 | 1 627,6 | +22,1 |
| 2024-07 | TRAIN | 38 | 2 232 | 3 095,1 | 2 288,7 | +806,4 |
| 2024-08 | TRAIN | 26 | 2 232 | 1 859,6 | 2 308,4 | −448,8 |
| 2024-09 | TRAIN | 162 | 2 160 | 2 251,3 | 2 053,1 | +198,1 |
| 2024-10 | VAL | 446 | 2 232 | 1 870,0 | 1 861,7 | +8,3 |
| 2024-11 | VAL | 0 | 2 160 | — | 2 789,9 | — |
| 2024-12 | VAL | 77 | 2 232 | 1 441,1 | 2 550,6 | −1 109,5 |
| 2025-01 | VAL | 270 | 2 232 | 2 193,8 | 2 593,0 | −399,2 |
| 2025-02 | VAL | 256 | 2 016 | 2 698,0 | 2 793,0 | −95,0 |
| 2025-03 | VAL | 169 | 2 232 | 1 864,7 | 2 437,0 | −572,3 |
| 2025-04 | VAL | 119 | 2 160 | 4 646,4 | 2 251,2 | +2 395,2 |
| 2025-05 | VAL | 75 | 2 232 | 1 431,1 | 2 204,1 | −773,1 |
| 2025-06 | VAL | 262 | 2 160 | 1 067,5 | 1 967,0 | −899,5 |
| 2025-07 | VAL | 340 | 2 232 | 1 351,1 | 1 955,4 | −604,3 |
| 2025-08 | VAL | 210 | 2 232 | 1 263,8 | 2 398,5 | −1 134,7 |
| 2025-09 | VAL | 659 | 3 852 | 1 021,0 | 2 168,9 | −1 147,9 |
| 2025-10 | VAL | 2 027 | 14 410 | 2 350,6 | 3 095,2 | −744,6 |
| 2025-11 | VAL | 1 947 | 14 400 | 3 403,5 | 3 454,1 | −50,6 |
| 2025-12 | VAL | 3 243 | 15 012 | 1 897,9 | 2 293,7 | −395,8 |
| 2026-01 | VAL | 4 627 | 17 022 | 2 482,2 | 2 599,8 | −117,7 |
| 2026-02 | VAL | 5 149 | 16 128 | 2 378,8 | 2 847,8 | −469,1 |
| 2026-03 | VAL | 5 703 | 17 942 | 1 875,5 | 2 182,7 | −307,2 |
| 2026-04 | VAL | 7 053 | 18 187 | 1 990,6 | 1 948,7 | +41,9 |
| 2026-05 | VAL | 9 033 | 21 114 | 2 087,6 | 2 163,8 | −76,1 |
| 2026-06 | VAL | 10 762 | 23 760 | 2 174,8 | 2 519,4 | −344,6 |
| 2026-07 | VAL | 12 760 | 24 552 | 1 413,9 | 1 663,0 | −249,1 |
| 2026-08 | VAL | 12 660 | 24 552 | 1 696,5 | 2 060,6 | −364,1 |
| 2026-09 | VAL | 8 380 | 21 483 | 2 318,5 | 2 761,8 | −443,4 |

Le mois est le mois du timestamp signal t. Sur les 56 mois porteurs d'événements : **47 Δ négatifs / 9 positifs**, aucun au-dessus de l'étalon de façon persistante (les 9 positifs : 2022-04 +43,3 ; 2023-02 +446,1 ; 2023-03 +598,4 ; 2024-03 +210,1 ; 2024-07 +806,4 ; 2024-09 +198,1 ; 2024-10 +8,3 ; 2025-04 +2 395,2 ; 2026-04 +41,9 — dispersion de régime, jamais répliquée deux mois de suite sauf 2023-02/03).

## Observation CONTEXTE (SENS = 0, non actionnable, jamais un signal)

- **La structure trouvée est l'INVERSE de l'hypothèse et elle est stable** : gradient d'amplitude strictement décroissant avec le silence dans les DEUX splits (TRAIN 3 440,6 → 1 370,1 ; VAL 3 934,6 → 1 964,5) — c'est le **vol clustering** élémentaire : l'activité engendre l'activité, le calme engendre le calme. La « densité de silence » est un **normaliseur de régime de volatilité** (une heure plate appelle une heure plate), pas un détecteur de compression explosive.
- Le pendant T20 se confirme par la négative : T20 avait trouvé « la densité EST le mouvement, pas son orientation » sur le tape ; ici la **platitude EST le calme, pas l'expansion** — les deux statistiques de densité (prints, retours nuls) décrivent le régime présent, aucune ne prédit une queue à venir sur Aster.
- Contexte directionnel (descriptif, sous les coûts, NON actionnable) : dérive forward signée [t+48h ; t+95h] des événements : TRAIN **+0,027 %** médiane (vs −0,006 % base), VAL **−0,000 %** (vs −0,204 % base) — aucun edge directionnel exploitable, signe instable entre splits, conformément à SENS = 0.
- Limitations documentées : (1) le seuil q90 calibré sur les 3 majeures TRAIN produit 33,5 % d'heures événements en VAL (panel 33 symboles plus plats) — la calibration ne transfère pas, mais la réfutation ne repose PAS sur ce transfert (elle vaut déjà sur TRAIN seul : Δ −945 bps, gradient inversé, contrôle battu) ; (2) chevauchement des fenêtres 72 h → n = des heures corrélées ; (3) les épisodes de silence d'un même mois sont dépendants.

## Leçon gravée

**Sur Aster 1h, l'ABSENCE ne précède pas l'EXPANSION — elle précède l'ABSENCE.** La volatilité est la seule chose qui prédit la volatilité : toute statistique d'absence (heures plates, densité de silence) est un marqueur de régime courant, jamais un détecteur de queue à venir. Toute réutilisation de S_t, du seuil 0,05 %, de la fenêtre 72 h ou de la fenêtre 48-96 h = nouveau pré-enregistrement + budget, jamais une re-catégorisation silencieuse.

Script : `scripts/studies/inv_g_densite_silence.py` (exécution unique du 02/10/2026, DB ro, 0 écriture data).
