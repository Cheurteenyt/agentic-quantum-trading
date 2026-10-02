# INV-E — « LE RYTHME DU FUNDING » (pré-enregistrement + résultats)

- **Domaine** : Aster (panel cross-symboles, données klines.db en lecture seule)
- **Date de pré-enregistrement** : 2026-10-02, AVANT tout résultat (ce bloc écrit avant l'exécution du script)
- **Gouvernance** : docs/38-gouvernance-recherche.md, tag `freeze-2026-10-02` ; registre `research/registry.yaml` vérifié (grep run-length/persistence/séquence/rythme) : AUCUNE expérience de persistance du funding antérieure → expérience GÉNUILEMENT nouvelle (pas une PARAMETER_MUTATION). Les 6 entrées famille `funding` du registre portent toutes sur le NIVEAU (carry, extrême, contre-courant, rank) — ici c'est une statistique de STRUCTURE TEMPORELLE (persistance du signe), classée famille `funding-persistence`. Budget : 1 expérience, 0 modification de protocole.
- **Script one-shot** : `scripts/studies/inv_e_rythme_funding.py` (unique exécution, aucun re-run de variante autorisé)

## 1. Hypothèse pré-déclarée (MAGNITUDE, PAS DIRECTION)

**Leçon OI vague 10 appliquée : les extrêmes prédisent l'AMPLITUDE, jamais le sens.**

Après une séquence de funding exceptionnellement longue (le même signe persiste bien au-delà de l'habitude = un positionnement qui s'entête), l'**AMPLITUDE** forward 48-96 h (somme des |ret| 1h) est **supérieure à la médiane**. C'est un **CONDITIONNEUR DE TAILLE** (gate de magnitude pour dimensionner une exposition existante), **PAS un signal**.

**SENS = 0** : toute séparation directionnelle détectée (signe du run vs rendement forward) est enregistrée comme **CONTEXTE descriptif**, jamais comme un signal — pré-déclaré avant toute mesure.

## 2. Construction (une seule définition, zéro grille, jamais re-tunée)

- Données : `data/warehouse/klines.db` **LECTURE SEULE** (mode=ro) — table `funding_history` (donnée profonde, ~8 h) + `klines` interval `1h`. **Leçon ts_ms vérifiée** : `funding_time` et `open_time` sont en **MILLISECONDES** (1683302400000 = 2023-05-05) — unité contrôlée avant tout join.
- **Univers** (fixé sur la couverture de donnée AVANT toute statistique de résultat) : symboles dont l'intervalle **médian** de funding = 8 h et ≥ 90 observations. Soit 14 symboles : 11 majeures (ADA, ARB, AVAX, BNB, BTC, DOGE, ETH, LINK, LTC, SOL, XRP — 1 016 périodes, 2025-10-27 → 2026-10-01) + les 3 perps actions (NVDA, DRAM, GOOGL). QNTUSDT exclu (11 obs). Les symboles à cadence 1 h/4 h (ASTERUSDT, memecoins récents) sont **hors périmètre par construction** : la statistique de run-length n'a de sens que sur une cadence homogène 8 h.
- **Série par symbole** : observations de funding ordonnées par `funding_time`. Signe : +1 si rate > 0, −1 si rate < 0, **0 si rate = 0** (les zéros, massifs sur les perps actions, **cassent** la séquence — absence de positionnement, pas un positionnement).
- **R_t (run-length)** : pour une période de signe ≠ 0, nombre consécutif d'observations de **même signe** se terminant à t. R_t est **causal** (ne compte que les périodes passées, y compris antérieures au split — aucune fuite). Les zéros cassent.
- **Split 60/40 chrono GLOBAL** : T_split = percentile 60 des timestamps de funding **uniques poolés** (un seul bornage temporel pour tous les symboles). TRAIN = t < T_split, VAL = t ≥ T_split.
- **Seuil unique** : q90 = quantile 90 (interpolation linéaire numpy, **non arrondi**) de la distribution R **TRAIN SEULEMENT** (périodes signe ≠ 0, poolés tous symboles). **Événement** = période signe ≠ 0 avec R_t ≥ q90. Un seul seuil, jamais recalculé en VAL.
- **Amplitude forward** : A_t = Σ des 48 retours 1h close-to-close |close(b)/close(b−1 h) − 1| sur les barres `open_time` ∈ [t+48 h ; t+95 h] (base requise : barre t+47 h ; prix(t+96 h) = close de la barre t+95 h). Couverture 1h incomplète → période **exclue, comptée, documentée**. Unité : **bps**.
- **Δ|fwd|** = médiane(A | événements) − médiane(A | **toutes** les périodes mesurables du split considéré, signe quelconque) — la médiane inconditionnelle est la référence du gate.
- **Étalon** : **12,2 bps** = aller/retour taker. Un gate de taille ne vaut que s'il déplace l'amplitude attendue de plus que ce qu'un aller-retour taker coûte.
- **Dépendance déclarée** : les événements d'un même run sont corrélés (un long run déclenche R_t ≥ q90 à chaque période qu'il dure) — n est traité comme des périodes, la dépendance est documentée en limitation.

## 3. Protocole immutable

- **Pas de trade, pas de levier, pas de wallet séquentiel** : conditionneur de taille — 0 liquidation **par construction**. Le gate ne s'appliquerait qu'à une exposition d'une stratégie existante (gel : aucune promotion).
- **n_train ≥ 100 événements mesurés** sinon expérience déclarée **SOUS-PUISSENTE** telle quelle (échec de puissance ≠ réfutation).
- **BLOC STATS mensuel** obligatoire (mois | split | n événements | n mesurables | médiane A événements | médiane A toutes | Δ).
- Les périodes signe 0 sont dans la base de référence mais jamais événements.

## 4. Critères PASS/FAIL (écrits AVANT les résultats)

**PASS = les quatre, sans exception :**
1. **Δ|fwd| médian TRAIN > 12,2 bps** (au-dessus de l'étalon A/R taker).
2. **Réplication VAL** : Δ|fwd| médian VAL > 0 (même signe, la magnitude se réplique hors train).
3. **Gradient monotone** : quintiles de R sur les périodes signe ≠ 0 TRAIN (Q1 → Q5) → médiane(A) **non décroissante** Q1 ≤ Q2 ≤ Q3 ≤ Q4 ≤ Q5 (VAL descriptif).
4. **Contrôle inverse battu** : médiane(A | R ≤ q10 train) < médiane(A | événements) sur **TRAIN ET VAL** — si les séquences les plus courtes portent la même magnitude, la « persistance » n'explique rien (amplitude ubiquitaire) et l'hypothèse est morte.

**FAIL = tout le reste** → « FAIL — hypothèse réfutée », gravé au registre, budget consommé, **STOP**. Pas de deuxième quantile, pas de fenêtre alternative, pas de filtre de réparation. Budget = 1 expérience.

**Si PASS** : verdict **CONTEXTE / CANDIDATE gate de sizing** — jamais un signal autonome ; SENS = 0 : toute séparation directionnelle observée = CONTEXTE non actionnable.

---

# RÉSULTATS (exécution unique du 02/10/2026)

> **Seal du pré-enregistrement** : sha256 du bloc ci-dessus, gelé AVANT exécution :
> `501c47979d2f833caecb2b39899b9bcc38634604de8eaa87aa5106b31abb2d5b`

Note d'intégrité : deux incidents **pré-résultats**, aucun critère/seuil/fenêtre/protocole touché. (1) La première exécution a **crashé** (KeyError) sur un off-by-one de la boucle d'amplitude — `range(49,97)` au lieu de `range(48,96)` du texte gelé (barres t+48 h…t+95 h) ; le crash est intervenu sur la **première période mesurée**, zéro statistique affichée ; le code a été mis en conformité avec le texte gelé. (2) La règle d'univers gelée (médiane 8 h + ≥ 90 obs) donne **36** symboles porteurs de funding — les 22 supplémentaires (1000PEPE, AAPL, TSLA, COIN, MSTR…) n'ont **aucune** barre 1h en warehouse → **0 période mesurable** ; le panneau effectif est exactement celui déclaré (14 symboles). L'exécution corrigée est l'**exécution unique** ; aucun re-run de variante.

## Exécution

- Univers règle : 36 symboles → **14 mesurables** (ADA, ARB, AVAX, BNB, BTC, DOGE, DRAM, ETH, GOOGL, LINK, LTC, NVDA, SOL, XRP), 22 sans klines 1h.
- **T_split = 2026-04-22 12:48 UTC** (1 447 timestamps uniques poolés — bornage non arrondi car timestamps off-grid des perps actions, règle gelée appliquée telle quelle).
- Périodes : **8 651 mesurables** (TRAIN 4 292 / VAL 4 359) ; 22 814 exclues couverture 1h (dont les 22 symboles sans klines) ; 7 550 périodes signe 0 mesurables (dans la base de référence, jamais événements).
- **R TRAIN** (signe ≠ 0) : n = 3 858 — q10 = 1, q50 = 5, **q90 = 51 périodes ≈ 17 jours de même signe**, max 212 (≈ 70 j). R VAL max : 359 (≈ 4 mois).
- **Événements : TRAIN 393, VAL 1 005 — tous run+**. Les périodes de funding négatif existent (1 516 en train, 486 en val) mais **aucun run négatif n'atteint jamais q90** sur toute l'histoire : la persistance extrême est unilatérale (financement structurellement long-biais sur Aster).
- Dépendance (pré-déclarée en limitation) : les 393 événements train proviennent de **~15 runs distincts** (≈ 26 périodes/run) ; les 1 005 val de ~15 runs (≈ 67/run). n = des périodes, fortement clusterisées — documenté, non corrigé (protocole gelé).

## Vérification des critères

| # | Critère (gelé) | Résultat |
|---|---|---|
| — | n_train ≥ 100 événements | **OK** (393) — expérience pleinement puissante, pas de sous-puissance |
| 1 | Δ\|fwd\| médian TRAIN > 12,2 bps | **FAUX** — medA évts 1 835,8 vs médiane toutes 2 163,2 → **Δ = −327,5 bps** (les événements sont SOUS la médiane) |
| 2 | Δ\|fwd\| médian VAL > 0 | vrai formellement (**+443,3 bps**) mais **signe inversé vs train** = artefact de régime, pas une réplication |
| 3 | Gradient monotone Q1 ≤ … ≤ Q5 (TRAIN) | **FAUX** — Q1 vide (discrétisation : q20 = 1) ; Q2 2 243,8 ≤ Q3 2 346,8 ≤ Q4 2 382,1 puis **chute Q5 2 023,9** (VAL descriptif : monotone croissant 1 596,7 → 2 128,8) |
| 4 | Contrôle inverse battu (TRAIN ET VAL) | **FAUX** — TRAIN R ≤ q10 (=1, n = 828) : medA **2 202,2 > 1 835,8** (les séquences les plus courtes sont PLUS amples que les événements) ; VAL battu (1 607,6 < 2 178,0) mais le critère exige les deux |

## BLOC STATS mensuel (médiane A en bps ; 0 liq par construction — pas de trade, pas de levier)

| Mois | Split | n évts | n toutes | medA évts | medA toutes | Δ |
|---|---|---|---|---|---|---|
| 2025-10 | TRAIN | 0 | 99 | — | 2 727,9 | — |
| 2025-11 | TRAIN | 54 | 691 | 2 317,2 | 3 044,7 | **−727,5** |
| 2025-12 | TRAIN | 32 | 768 | 1 307,3 | 1 922,3 | **−615,0** |
| 2026-01 | TRAIN | 138 | 768 | 1 933,1 | 2 056,9 | −123,8 |
| 2026-02 | TRAIN | 62 | 624 | 1 643,4 | 2 679,8 | **−1 036,4** (pire) |
| 2026-03 | TRAIN | 7 | 783 | 1 506,4 | 1 932,8 | **−426,4** |
| 2026-04 | TRAIN | 100 | 559 | 1 786,0 | 1 553,4 | +232,5 |
| 2026-04 | VAL | 72 | 234 | 1 506,2 | 1 230,6 | +275,6 |
| 2026-05 | VAL | 332 | 926 | 2 092,2 | 1 735,9 | +356,3 |
| 2026-06 | VAL | 182 | 764 | 2 696,1 | 2 139,4 | +556,8 |
| 2026-07 | VAL | 118 | 840 | 1 829,2 | 1 584,0 | +245,2 |
| 2026-08 | VAL | 122 | 896 | 1 664,6 | 1 639,0 | +25,6 |
| 2026-09 | VAL | 179 | 699 | 2 811,9 | 1 941,4 | +870,4 (record) |

- **Δ négatif sur 5 des 6 mois TRAIN pleins** (pire −1 036,4 en février) ; **Δ positif sur 6/6 mois VAL** — l'effet change de signe EXACTEMENT au split : la signature d'un artefact de régime, pas d'un mécanisme. Garde-fou composé-des-mois vs final : les totaux par mois confirment le Δ global de chaque split, aucune divergence cachée.

## CONTEXTE (SENS = 0, pré-déclaré non actionnable)

- **Tous les événements sont des runs de funding positif** — le « rythme » mesuré est celui de l'enlisement des longs, jamais des shorts.
- Direction forward 48-96 h après événement : TRAIN médiane **−0,43 %** (WR 42 %), VAL **−0,45 %** (WR 44 %) — dérive baissière légère et cohérente entre splits (le positionnement long payeur s'érode), MAIS : pré-déclaré SENS = 0 → jamais un signal ; ~0,45 % brut vs 12,2 bps d'A/R taker, tout trade directionnel serait de toute façon mangé par les coûts ; aucune métrique de trade au-delà du descriptif.

## VERDICT : **FAIL — hypothèse réfutée**

Après une séquence de funding exceptionnellement longue (R ≥ 51 périodes ≈ 17 jours, un seul seuil), l'amplitude forward 48-96 h est **INFÉRIEURE** à la médiane en train (−327,5 bps, étalon 12,2 bps non approché), le gradient quintiles **n'est pas monotone** (chute au quintile extrême), et le contrôle inverse n'est **pas battu** : en train, les séquences les plus courtes (R ≤ 1) portent une amplitude **supérieure** aux événements (2 202,2 vs 1 835,8 bps). L'inversion de signe train (−327,5) / val (+443,3) — la val portée par les seuls mois volatils mai-sept 2026 — scelle l'artefact de régime : la persistance du signe du funding n'annonce ni l'amplitude ni rien de tradable. Budget = 1 expérience consommée, **STOP** : pas de deuxième quantile, pas de fenêtre alternative, pas de filtre de réparation.

Observation gravée (NON promouvable, NON testée — même donnée, même budget) : la persistance extrême est **unilatérale** (0 run négatif ≥ q90 sur 339 jours × 14 symboles) — sur Aster, une longue séquence de funding est toujours une longue séquence POSITIVE ; le run-length n'est donc pas un conditionneur symétrique et ne pourra jamais le devenir dans ce cadre. Toute réutilisation exigerait un nouveau pré-enregistrement + budget.
