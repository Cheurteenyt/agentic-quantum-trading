# INV-F — « LA CO-DÉFORMATION » (pré-enregistrement + résultats)

- **Domaine** : Aster (panel cross-symboles, données klines.db en lecture seule)
- **Date de pré-enregistrement** : 2026-10-02, AVANT tout résultat (ce bloc écrit avant l'exécution du script)
- **Gouvernance** : docs/38-gouvernance-recherche.md, tag `freeze-2026-10-02` ; registre `research/registry.yaml` vérifié (grep corr/co-déformation/régime) : le corr-tilt de la machine utilise le **NIVEAU** de corrélation (registry, stratégie validée en prod), l'adaptateur 90 j le **bord roulant**, la breadth est **descriptive** (`breadth_sizing_multiplier` REJECTED 28/09). AUCUNE expérience d'**ÉVÉNEMENT** de saut conjoint vol×corr n'existe → expérience GÉNUILEMENT nouvelle (pas une PARAMETER_MUTATION), famille `regime-transition`. Contexte : les 4 inventions de la vague 1-2 (déviante, concentration, asymétrie de vitesse, rythme du funding) sont mortes AU MÊME ENDROIT — la validation temporelle (régime T3). Cette expérience attaque le tueur lui-même : détecter la TRANSITION de régime par un événement mesurable. Budget : 1 expérience, 0 modification de protocole.
- **Script one-shot** : `scripts/studies/inv_f_codeformation.py` (unique exécution, aucun re-run de variante autorisé)

## 1. Hypothèse pré-déclarée (MAGNITUDE, PAS DIRECTION — leçon OI vague 10)

Une **co-déformation** du pack des 6 majeures — la vol du pack **double en ≤ 72 h** pendant que la corrélation moyenne **traverse son q80 train** — est un ÉVÉNEMENT de transition de régime (un saut conjoint entre états, pas un niveau). Après cet événement, l'**AMPLITUDE** forward 7-14 j (moyenne des |ret| 1h) est **supérieure à la baseline sans événement** de plus que l'étalon **12,2 bps** (aller/retour taker).

**SENS = 0** : c'est un **GATE de régime** (conditionneur de taille/filtre pour stratégies existantes), **jamais un signal directionnel**. Toute séparation directionnelle détectée est enregistrée comme **CONTEXTE descriptif**, jamais comme un signal — pré-déclaré avant toute mesure. Pas de trade, pas de levier : 0 liquidation **par construction**.

## 2. Construction (une seule définition par quantité, zéro grille, jamais re-tunée)

- Données : `data/warehouse/klines.db` **LECTURE SEULE** (mode=ro), table `klines`, interval `1h`. **Leçon ts_ms vérifiée** : `open_time` est en **MILLISECONDES** sur grille horaire exacte — vérifié AVANT le pré-enregistrement : les 6 symboles sont 100 % on-grid (open_time % 3 600 000 = 0), zéro doublon, zéro trou interne.
- **Panel** (fixé sur la couverture AVANT toute statistique de résultat) : les 6 majeures BTC, ETH, SOL, BNB, XRP, DOGE (USDT). **Heures communes** = 8 956 heures où les 6 ont un close : 2025-09-24 02:00 UTC → 2026-10-02 03:00 UTC (373,1 jours, BNB/XRP/DOGE bornent le début). Un seul maillage, aucune reconstruction.
- **ret24_i(t)** = close_i(t)/close_i(t−24) − 1 (close-to-close 24 h, causal, barres t et t−24).
- **Fenêtre W = 72 h** (3 jours) pour les DEUX statistiques — cohérence : la fenêtre des stats = l'horizon de doublage déclaré.
  - **σ_i(t)** = écart-type (ddof=1) des 72 dernières valeurs ret24_i (barres t−71 … t).
  - **V_t** = moyenne des 6 σ_i(t) — **la vol du pack**.
  - **C_t** = moyenne des 15 corrélations de Pearson pairwise des séries ret24_i sur les 72 dernières heures (toutes les heures de la fenêtre ont un panel complet par construction).
- **q80_TRAIN** = quantile 80 (numpy, interpolation linéaire, **non arrondi**) des C_t de **toutes les heures TRAIN** où C est défini. Un seul seuil, calculé TRAIN SEULEMENT, appliqué tel quel en VAL, jamais recalculé.
- **Événement de CO-DÉFORMATION à l'heure t** (causal, données ≤ t, les DEUX conditions dans la même heure t) :
  1. **Doublage** : V_t ≥ 2 × min(V_{t−1}, …, V_{t−72}) — la vol du pack a doublé en ≤ 72 h ;
  2. **Traversée** : C_t > q80_train **ET** C_{t−1} ≤ q80_train — la corrélation **passe** au-dessus de son q80 train (événement de traversée, pas un état : une corrélation qui reste > q80 pendant des semaines ne compte qu'à sa traversée).
- **Amplitude forward 7-14 j** : A_t = moyenne des |close(b)/close(b−1) − 1| sur les **168 barres** b ∈ [t+168 h ; t+335 h] (7 j = début, 14 j = fin, inclus). Événement non mesurable (barres manquantes au-delà de t+335) → **exclu, compté, documenté**. Unité : **bps**.
- **Δ|fwd|** = médiane(A | événements) − médiane(A | heures **sans événement**), par split (la baseline exclut les heures-événements).
- **Gradient de l'ampleur** : J_t = V_t / min(V_{t−1}…V_{t−72}) (rapport de saut) sur les événements TRAIN ; terciles (q33,3/q66,7) ; médiane(A) **non décroissante** T1 ≤ T2 ≤ T3 ; ≥ 5 événements par tercile requis sinon gradient **non évaluable** (critère non satisfait). VAL descriptif.
- **Split 60/40 chrono GLOBAL** : T_split = percentile 60 des timestamps du panel = **2026-05-05 19:00 UTC** (un seul bornage temporel). TRAIN = t < T_split, VAL = t ≥ T_split.
- **Étalon** : **12,2 bps** = aller/retour taker. Un gate de régime ne vaut que s'il déplace l'amplitude attendue de plus qu'un aller-retour taker.

## 3. Protocole immutable

- **Pas de trade, pas de levier, pas de wallet séquentiel** : gate de régime — 0 liquidation **par construction**. Le gate ne s'appliquerait qu'à conditionner des expositions de stratégies existantes (gel : aucune promotion).
- **n_train ≥ 30 événements** (heures-événements TRAIN mesurables) sinon expérience déclarée **SOUS-PUISSENTE** telle quelle — échec de puissance ≠ réfutation formelle, mais **aucun PASS possible** et aucun relâchement de seuil/fenêtre pour « mesurer ». STOP.
- **BLOC STATS mensuel** obligatoire : mois | split | n événements | n mesurables | médiane A événements | médiane A sans événement | Δ.
- Chevauchement des fenêtres forward entre événements proches : documenté en limitation (les traversées sont naturellement éparses).

## 4. Critères PASS/FAIL (écrits AVANT les résultats)

**PASS = les cinq, sans exception :**
1. **n_train ≥ 30 événements** mesurables.
2. **Δ|fwd| médian TRAIN > 12,2 bps** (au-dessus de l'étalon A/R taker).
3. **Réplication VAL** : Δ|fwd| médian VAL > 0 (même signe que TRAIN).
4. **Gradient monotone** sur l'ampleur du saut : terciles J (TRAIN), médiane(A) non décroissante T1 ≤ T2 ≤ T3, ≥ 5 événements/tercile.
5. **Contrôle inverse battu** : médiane(A | sans événement) < médiane(A | événements) sur **TRAIN ET VAL** — si les périodes ordinaires portent la même amplitude, la co-déformation n'explique rien (amplitude ubiquitaire) et l'hypothèse est morte.

**FAIL = tout le reste** → « FAIL — hypothèse réfutée », gravé au registre, budget consommé, **STOP**. Pas de deuxième quantile, pas de fenêtre alternative, pas de filtre de réparation. Budget = 1 expérience.

**Si n_train < 30** : verdict **SOUS-PUISSENT** (budget consommé, STOP, aucun relâchement).

**Si PASS** : verdict **CONTEXTE / CANDIDATE gate de régime** — jamais un signal autonome ; SENS = 0 : toute séparation directionnelle observée = CONTEXTE non actionnable.

---

# RÉSULTATS (exécution unique du 02/10/2026)

> **Seal du pré-enregistrement** : sha256 du fichier gelé AVANT exécution :
> `8e6fa1bf0e64b5e073c12e8bb86355b451da24ab4493b3030f58f6a5c2ded665`

Note d'intégrité : deux incidents **pré-résultats**, aucun critère/seuil/fenêtre/protocole touché. (1) La première exécution a **crashé** sur une assertion de forme du panel (ordre d'itération symbole/heure) — intervenu **avant toute statistique affichée** ; mise en conformité avec le texte gelé, l'exécution corrigée est l'**exécution unique**. (2) L'horodatage du début de panel écrit au §2 (« 2025-09-24 02:00 UTC ») est une conversion à la main fausse de 4 h ; la vérification machine donne **2025-09-23 22:00 UTC → 2026-10-02 01:00 UTC** (8 956 heures, T_split = percentile 60 **inchangé** = 2026-05-05 19:00 UTC, vérifié deux fois indépendamment). Aucune définition affectée.

## Exécution

- Panel : **8 956 heures communes** (BTC/ETH/SOL/BNB/XRP/DOGE, 100 % on-grid, zéro trou, zéro doublon). TRAIN 5 373 h / VAL 3 583 h. V/C définis sur **8 837 heures** (à partir de 2025-09-28 21:00 UTC) ; A_t mesurable sur **8 621 heures** (TRAIN 5 373 / VAL 3 248 — les événements VAL après le 18/09/2026 n'ont pas de fenêtre forward complète).
- **q80(C) TRAIN = 0,9260** (n = 5 254 heures) : les corrélations 72 h des ret24 des 6 majeures sont ≥ 0,93 pour un cinquième des heures — le pack est structurellement hyper-intégré ; c'est le **doublement de V** qui fait la rareté, pas la traversée de C.
- **Événements (doublement V ≥ 2× ET traversée C > q80 dans la même heure) : TRAIN 8 mesurables, VAL 3 mesurables** (1 VAL brute non mesurable, faute de 14 j de donnée). **12 épisodes distincts** (gap ≥ 24 h) : la définition de traversée s'auto-décluster — n = 8 événements réellement indépendants, pas des heures corrélées d'un même épisode.
- Face-validité : l'événement du **2025-10-11 07:00 UTC** (J = 2,06) est la cascade de liquidations du 10-11 octobre 2025 — l'événement attrape bien les vraies transitions.

## Vérification des critères

| # | Critère (gelé) | Résultat |
|---|---|---|
| — | n_train ≥ 30 événements | **ÉCHOUÉ — 8 < 30** → verdict **SOUS-PUISSENT** (gelé : aucun PASS possible) |
| 1 | Δ\|fwd\| médian TRAIN > 12,2 bps | **FAUX** (descriptif hors puissance) — medA évts 29,9 vs medA sans événement 32,2 → **Δ = −2,3 bps** (SOUS la baseline, étalon 12,2 non approché) |
| 2 | Δ\|fwd\| médian VAL > 0 | **FAUX** — Δ = **−0,6 bps** (medA évts 23,7 vs 24,3) |
| 3 | Gradient monotone terciles J (TRAIN) | **FAUX et non évaluable** (3/2/3 < 5 par tercile) — T1 33,8 = T2 33,8 > T3 29,4 : **décroissant** |
| 4 | Contrôle inverse battu (TRAIN ET VAL) | **FAUX** — les heures ordinaires sont PLUS amples que les événements (TRAIN 32,2 > 29,9 ; VAL 24,3 > 23,7) |

## BLOC STATS mensuel (médiane A en bps ; 0 liq par construction — pas de trade, pas de levier)

| Mois | Split | n évts | n mesurables | medA évts | medA sans | Δ |
|---|---|---|---|---|---|---|
| 2025-09 | TRAIN | 0 | 51 | — | 38,4 | — |
| 2025-10 | TRAIN | 2 | 744 | 29,4 | 34,6 | **−5,2** (pire) |
| 2025-11 | TRAIN | 1 | 720 | 35,1 | 36,0 | −0,8 |
| 2025-12 | TRAIN | 1 | 744 | 26,9 | 23,9 | +3,0 |
| 2026-01 | TRAIN | 1 | 744 | 29,9 | 29,5 | +0,4 |
| 2026-02 | TRAIN | 2 | 672 | 37,2 | 40,7 | **−3,4** |
| 2026-03 | TRAIN | 0 | 744 | — | 32,2 | — |
| 2026-04 | TRAIN | 1 | 720 | 29,4 | 23,0 | +6,5 (record) |
| 2026-05 | VAL | 1 | 629 | 52,4 | 24,6 | +27,8 (record VAL) |
| 2026-06 | VAL | 0 | 720 | — | 29,5 | — |
| 2026-07 | VAL | 1 | 744 | 19,5 | 21,5 | −1,9 |
| 2026-08 | VAL | 1 | 744 | 23,7 | 24,1 | −0,4 |
| 2026-09 | VAL | 0 | 411 | — | 24,2 | — |

Le seul Δ nettement positif (2026-05 VAL, +27,8) porte sur **1 événement** — zéro poids de preuve. Garde-fou composé-des-mois vs final : cohérent, aucune divergence cachée, simplement pas assez d'événements pour rien.

## CONTEXTE (SENS = 0, pré-déclaré non actionnable)

- Dérive forward 7-14 j (BTC, t+168→t+335) après événement : TRAIN **−0,86 %** (n=8), VAL **−3,49 %** (n=3) — descriptif uniquement, SENS = 0 gravé.
- Mécanisme apparent : le doublement de V + la traversée de C se produisent **à la queue** des bouffées de vol (post-pic) — la co-déformation détecte la fin d'une transition, pas son anticipation ; l'amplitude 7-14 j suivante est alors déjà retombée au niveau ordinaire.

## VERDICT : **SOUS-PUISSENT — budget consommé, STOP**

L'événement de co-déformation tel que gelé (doublement de la vol du pack en ≤ 72 h ET traversée du q80 de corrélation dans la même heure) est **structurellement rare sur 373 jours de panel : 8 événements TRAIN** (12 épisodes sur tout l'historique), très en-dessous du plancher de puissance de 30 — verdict **SOUS-PUISSENT**, aucun PASS possible, aucun relâchement de seuil/fenêtre autorisé. Et les checks descriptifs hors puissance ne donnent **aucun soutien** à l'hypothèse : Δ = −2,3 bps TRAIN (étalon 12,2 non approché, mauvais signe), −0,6 bps VAL, gradient décroissant, contrôle inverse non battu — les heures ordinaires portent la même amplitude que les heures-événements. Budget = 1 expérience consommée, **STOP** : pas de deuxième quantile, pas de fenêtre alternative, pas de détente du doublement.

Observations gravées (NON promouvables, NON testées) : (1) la corrélation 72 h du pack est ≥ 0,93 un cinquième du temps — sur les majeures Aster, le NIVEAU de corrélation est saturé et seul un ÉVÉNEMENT conjoint pouvait porter de l'information ; (2) l'événement conjoint, même rare, arrive POST-pic (queue de bouffée) — la transition de régime se détecte au plus tôt par le doublement de V **seul** (le J du 10-11/10/2025 était déjà 2,06), jamais par la corrélation qui ne confirme qu'ensuite ; toute réutilisation exigerait un nouveau pré-enregistrement + budget.
