# INV-H — « LA SUPERPOSITION DE RÉGIMES » (pré-enregistrement + résultats)

- **Domaine** : Aster (BTC + ETH 1h, les 2 séries les plus profondes ; données klines.db en lecture seule)
- **Date de pré-enregistrement** : 2026-10-02, AVANT tout résultat (ce bloc écrit avant l'exécution du script)
- **Gouvernance** : docs/38-gouvernance-recherche.md, tag `freeze-2026-10-02` ; registre `research/registry.yaml` vérifié (grep hmm / markov / superposition / baum / posterior / crisp sur registry.yaml et docs/20-registre-indicateurs.md) : AUCUNE expérience antérieure → expérience GÉNUILEMENT nouvelle (pas une PARAMETER_MUTATION).
- **Adjacence déclarée** : T7/T9 (`aster_deep_regimes.py`, `aster_multiregime_stack.py`) utilisaient des CLASSIFICATIONS DE RÉGIME DURES (règles bull/bear/memes) comme gates d'exposition d'un stack — jamais un posterior probabiliste, jamais une question de persistance. T20 (`aster_orderflow_regimes.py`) mesurait des régimes de PRINTS du tape (90 j, direction 24 h, NUL). INV-G a gravé « la volatilité prédit la volatilité ». Ici la question est TOUTE AUTRE : la qualité de PRÉDICTION DE PERSISTANCE du régime à 7 j — HMM (transitions apprises) vs hypothèse implicite de l'adaptateur 90 j (le régime persiste). Zéro trade, zéro edge directionnel recherché.
- **Script one-shot** : `scripts/studies/inv_h_superposition_regimes.py` (unique exécution, aucun re-run de variante autorisé)

## 1. Hypothèse pré-déclarée (LA question falsifiable)

L'adaptateur 90 j suppose IMPLICITEMENT que le régime observé à t est le même à t+7j. Le HMM gaussien 3 états, via sa matrice de transition APPRISE sur TRAIN, propose une alternative : la superposition (p_crise, p_chop, p_tendance — trois probabilités qui somment à 1) propagée 168 h par A^168.

**Hypothèse : le HMM prédit l'état crisp à t+168 h avec une précision STRICTEMENT supérieure au naïf (« l'état crisp à t est le même à t+7j »), en TRAIN ET en VAL.**

## 2. Construction (une seule définition, zéro grille, jamais re-tunée)

- **Données** : `data/warehouse/klines.db` **LECTURE SEULE** (mode=ro) — BTCUSDT et ETHUSDT interval `1h`. **Leçon ts_ms vérifiée** : `open_time` en **MILLISECONDES** (assertion > 1e12 avant tout join). Doublons (symbol, open_time) comptés = 0 attendu ; grille horaire contiguë par série **assertée** (tout gap → STOP, pas de réparation silencieuse).
- **Features par série** (2, causales) : r_t = close_t/close_{t−1} − 1 ; rv24_t = √(Σ des r² sur les 24 dernières bougies 1h). Z-score **par feature avec les moments TRAIN de la série uniquement**, appliqué tel quel à VAL.
- **Split 60/40 chrono GLOBAL, fixé AVANT le fit** : T_split = percentile 60 des open_time **uniques poolés** BTC+ETH (un seul bornage temporel, non arrondi — même convention que INV-G). TRAIN = t < T_split, VAL = t ≥ T_split. Le panel fait ~4,4 ans : **l'horizon 7 j (168 h) est tenable, aucun repli t+24h/t+48h nécessaire** (décidé a priori).
- **Modèle** : UN HMM gaussien 3 états **diagonal** PAR SÉRIE, features (r, rv24). hmmlearn ABSENT du venv → **Baum-Welch implémenté à la main en numpy** (aucune installation). Architecture unique : 3 états, gaussien diagonal — **zéro grille d'architecture** (pas de 2/4/5 états, pas de covariance pleine, pas d'autre feature).
- **Fit EM TRAIN ONLY** : init déterministe sans RNG — hard-labels par terciles de rv24 TRAIN (état bas rv / milieu / haut rv) → moments diagonaux initiaux, transitions par comptes de transitions entre hard-labels, π0 = distribution stationnaire de A. Boucle EM (forward-backward à échelle de Rabiner, numpy pur) : max 300 itérations, convergence si |Δ loglik| < 1e-6. Plancher de variance 1e-8 (garde numérique). **AUCUN re-fit sur VAL** — les paramètres TRAIN sont gelés.
- **Filtre causal continu** : le forward-filter tourne sur la série ENTIÈRE avec les paramètres TRAIN gelés (comportement d'un adaptateur live). À chaque close t : posterior filtré (p1, p2, p3). **État crisp** = argmax si max posterior ≥ 0,8 ; sinon PAS d'état crisp à t (heure ambiguë).
- **Étiquetage des états** (déterministe, défini sur TRAIN) : états ordonnés par moyenne TRAIN de rv24 — la plus haute rv = **CRISE** ; des deux restants, la plus haute moyenne TRAIN de r = **TENDANCE**, l'autre = **CHOP**. Les états bruts de chaque HMM (indépendants) sont ensuite re-mappés sur cet étiquetage CANONIQUE commun (CRISE/TENDANCE/CHOP) — tout pooling et tout critère par état opèrent sur l'étiquette canonique, jamais sur l'index brut.
- **Vérité terrain** (déclaré, autoreférentielle assumée) : l'état crisp filtré à t+168 (causal, obs ≤ t+168). Le test porte sur la persistance TELLE QUE LE MODÈLE LA DÉFINIT ; le naïf est jugé sur la MÊME cible — comparaison interne cohérente.
- **Événement d'évaluation** : t tel que (a) crisp(t) existe (posterior ≥ 0,8), (b) crisp(t+168) existe, (c) t et t+168 dans le MÊME split. Split de l'événement = split de t (temps de décision). Les heures ambiguës (posterior < 0,8) sont exclues et comptées.
- **Prédictions** : naïf = crisp(t). HMM = argmax(π_t · A^168) où π_t est la superposition COMPLÈTE (les 3 probabilités) — la prédiction HMM est toujours formulée (sans condition de confiance).
- **Métrique principale** : précision poolée BTC+ETH par split (fraction d'événements prédits corrects). Par série et par état : descriptif + critère 3.

## 3. Protocole immutable

- **Pas de trade, pas de levier, pas de wallet séquentiel** : détecteur de régime évalué en CLASSIFICATION — 0 liquidation par construction. Un éventuel PASS = verdict **CONTEXTE/CANDIDATE détecteur de régime rapide (gate)** — JAMAIS un signal autonome ; la promotion passerait par la pipeline complète (gel docs/38 : aucune promotion aujourd'hui).
- **Garde de puissance pré-déclaré** (pas une réparation) : le critère par état n'est évalué que sur les états avec **n ≥ 100 événements** de vérité terrain dans le split ; un état plus rare est rapporté en descriptif et ne peut falsifier par bruit. Garde jamais déclenché attendu (milliers d'heures par état sur 4,4 ans).
- **BLOC STATS mensuel obligatoire** (mois du temps de décision t | split | n événements | couverture crisp | précision naïf | précision HMM | écart).
- **Budget = 1 expérience** : aucun re-fit, aucun 2e horizon, pas de 4 états, pas d'autres features, pas de seuil de crisp alternatif.

## 4. Critères PASS/FAIL (écrits AVANT les résultats)

**PASS = les trois, sans exception :**
1. **Précision HMM > précision naïve en TRAIN ET en VAL** (poolé BTC+ETH, inégalité stricte).
2. **Écart ≥ 5 points de pourcentage dans les DEUX splits** (HMM − naïf).
3. **L'avantage tient sur les 3 états (pas seulement crise)** : pour CHACUN des 3 états s avec n_s ≥ 100 (n_s = événements de vérité terrain = s), précision HMM > précision naïf sur le sous-ensemble {truth = s}, **en TRAIN ET en VAL**.

**FAIL = tout le reste** → « FAIL — hypothèse réfutée », gravé au registre, budget consommé, **STOP**. Pas de 4 états, pas d'autres features, pas de re-fit, pas d'horizon alternatif.

**Si PASS** : verdict **CONTEXTE/CANDIDATE** — détecteur de régime rapide, un GATE (conditionneur d'exposition pour stratégies existantes), jamais un signal autonome ; promotion = pipeline complète (wallet séquentiel inclus), hors gel.

<!-- SEAL-BOUNDARY -->

---

# RÉSULTATS (exécution unique du 02/10/2026)

> **Seal du pré-enregistrement** : sha256 du bloc ci-dessus (fichier gelé au stade pré-enregistrement, avant l'exécution), vérifiable en tronquant au marqueur `<!-- SEAL-BOUNDARY -->` :
> `d9d1fb829ca98223e201f796a603930b0cba7d625c6e8919f991970fb9dd523f`

Note d'intégrité : un incident, aucun critère/seuil/protocole touché. La 1re exécution a **crashé dans le code d'ÉTIQUETAGE** (moyennes TRAIN calculées sur le tableau global au lieu des means PAR ÉTAT du modèle — `IndexError` AVANT tout calcul d'événement ou de statistique ; seuls données/split/fits/filtre avaient été imprimés, tous déterministes sans RNG). La ré-exécution corrigée est l'**exécution unique de référence** ; les fits imprimés avant/après coïncident bit à bit (loglik −46478.28 / −44520.10). Aucun re-run de variante.

## Exécution

- **Données** : BTCUSDT 44 564 barres 1h (2021-09-01 06:00 → 2026-10-02 01:00 UTC), ETHUSDT 44 423 (2021-09-07 03:00 → 2026-10-02 01:00) — 0 doublon, grilles contiguës assertées, `open_time` en ms asserté.
- **T_split = 2024-09-19 17:24:00.000 UTC** (percentile 60 des 88 939 timestamps uniques poolés, non arrondi). TRAIN : BTC 26 724 h / ETH 26 583 h ; VAL : 17 816 h chacun.
- **Fits (TRAIN only, gelés)** : BTC EM 130 iters, loglik −46 478.28, A diag [0.9776, 0.9665, 0.9662], stationnaire [0.368, 0.422, 0.210] ; ETH EM 67 iters, loglik −44 520.10, A diag [0.9785, 0.9702, 0.9746], stationnaire [0.346, 0.416, 0.239]. Étiquetage canonique : CRISE = rv24 TRAIN la plus haute (z +1.46 BTC / +1.34 ETH), TENDANCE = rv basse + ret ≥ 0, CHOP = rv basse + ret ≤ 0 (retours moyens TRAIN par état tous ≈ 0 : |z| ≤ 0.002 — les états séparent la VOL, pas la direction, cohérent avec la leçon INV-G).
- **Filtre causal continu** (params TRAIN gelés) : couverture crisp (posterior max ≥ 0.8) = **93.8 % (BTC) / 94.1 % (ETH)** — la superposition est confidante presque partout ; 5 364 heures ambiguës exclues au total.
- **Événements d'évaluation** (crisp à t ET t+168 h, même split) : **77 926** (TRAIN 46 874 / VAL 31 052) — expérience pleinement puissante (garde n ≥ 100 écrasé).
- Horizon 7 j (168 h) tenu tel que pré-enregistré — panel 4,4 ans, aucun repli 24/48 h nécessaire.

## Vérification des critères

| # | Critère (gelé) | Résultat |
|---|---|---|
| 1 | HMM > naïf en TRAIN ET VAL (poolé) | **OK** — TRAIN 41.10 % vs 25.18 % ; VAL 41.59 % vs 25.15 % |
| 2 | Écart ≥ 5 pts dans les deux splits | **OK** — TRAIN **+15.92 pts**, VAL **+16.44 pts** (répliqué par série : BTC +16.19/+13.78, ETH +15.66/+19.10) |
| 3 | Avantage sur les 3 états (garde n ≥ 100) | **FAUX — effondrement dégénéré** : HMM **0.00 %** sur CRISE (naïf 13.78 %) et **0.00 %** sur TENDANCE (naïf 29.76 %) vs **100.00 %** sur CHOP, en TRAIN ; identique en VAL (CRISE 0.00 vs 17.48, TENDANCE 0.00 vs 30.70, CHOP 100.00). L'avantage ne tient que sur l'état majoritaire stationnaire |

**VERDICT : FAIL — hypothèse réfutée** (critère 3 violé dans les deux splits). Budget = 1 expérience consommée, **STOP** : pas de 4 états, pas d'autres features, pas de re-fit, pas d'horizon alternatif.

## Lecture mécaniste (pourquoi c'est réfuté — et ce que ça grave)

1. **La mémoire du HMM meurt avant 7 j** : auto-transitions apprises 0.966-0.978 par HEURE → 0.9776^168 ≈ 0.020, 0.9662^168 ≈ 0.003. À l'horizon 168 h, A^168 ≈ distribution stationnaire : **pi_t @ A^168 oublie la superposition** et retombe sur les fréquences de long terme. La matrice de confusion le montre sans ambiguïté : le HMM prédit CHOP (état majoritaire stationnaire, 42 %) pour **100 % des heures** TRAIN et VAL.
2. **L'« avantage » +16 pts est un artefact de base-rate** : précision HMM 41.10 % = exactement la fréquence a priori de CHOP dans l'échantillon d'évaluation (41.1 %). Le prédicteur constant « toujours CHOP » obtient la même chose. Les critères 1-2 seuls auraient validé un prédicteur constant — c'est précisément ce que le critère 3 pré-déclaré existait pour attraper, et il a attrapé.
3. **Le naïf est SOUS le hasard** : 25.2 % contre ~35 % (TRAIN) / ~37 % (VAL) pour un tirage au sort aux marges de l'échantillon — la persistance crisp à 7 j est **anti-corrélée** (rv24 est mean-reverting à l'échelle semaine : un état de vol extrême à t appelle l'état opposé à t+7j). L'hypothèse implicite de l'adaptateur 90 j (« le régime tient ») est donc non seulement non-battue par le HMM : elle est elle-même mauvaise à 7 j — mais pour les DEUX prédicteurs, la bonne stratégie à 7 j est de prédire la base-rate, pas l'état courant.
4. **Cohérence inter-splits** : l'artefact se réplique identiquement en TRAIN et VAL (écart +15.92/+16.44, dégénérescence identique) — la réfutation n'est pas un mirage de régime, elle est structurelle au modèle.

## BLOC STATS mensuel (poolé BTC+ETH ; mois du temps de décision t ; couverture = événements / heures éligibles ; 0 liq par construction — pas de trade, pas de levier)

| Mois | Split | n evts | couv | naïf | HMM | écart (pts) |
|---|---|---|---|---|---|---|
| 2021-09 | TRAIN | 1 076 | 86.8 % | 27.04 % | 43.59 % | +16.54 |
| 2021-10 | TRAIN | 1 194 | 80.2 % | 26.47 % | 65.58 % | +39.11 |
| 2021-11 | TRAIN | 1 233 | 85.6 % | 19.46 % | 47.20 % | +27.74 |
| 2021-12 | TRAIN | 1 262 | 84.8 % | 25.12 % | 56.26 % | +31.14 |
| 2022-01 | TRAIN | 1 321 | 88.8 % | 40.58 % | 45.04 % | +4.47 |
| 2022-02 | TRAIN | 1 110 | 82.6 % | 23.78 % | 39.91 % | +16.13 |
| 2022-03 | TRAIN | 1 248 | 83.9 % | 20.99 % | 65.22 % | +44.23 |
| 2022-04 | TRAIN | 1 312 | 91.1 % | 17.84 % | 66.46 % | +48.63 |
| 2022-05 | TRAIN | 1 294 | 87.0 % | 25.50 % | 36.63 % | +11.13 |
| 2022-06 | TRAIN | 1 335 | 92.7 % | 20.45 % | 23.15 % | +2.70 |
| 2022-07 | TRAIN | 1 333 | 89.6 % | 24.83 % | 39.46 % | +14.63 |
| 2022-08 | TRAIN | 1 285 | 86.4 % | 28.48 % | 49.88 % | +21.40 |
| 2022-09 | TRAIN | 1 267 | 88.0 % | 28.18 % | 50.04 % | +21.86 |
| 2022-10 | TRAIN | 1 294 | 87.0 % | 27.51 % | 29.68 % | +2.16 |
| 2022-11 | TRAIN | 1 313 | 91.2 % | 34.42 % | 30.01 % | −4.42 |
| 2022-12 | TRAIN | 1 385 | 93.1 % | 15.09 % | 10.83 % | −4.26 |
| 2023-01 | TRAIN | 1 290 | 86.7 % | 26.67 % | 39.22 % | +12.56 |
| 2023-02 | TRAIN | 1 186 | 88.2 % | 22.60 % | 41.91 % | +19.31 |
| 2023-03 | TRAIN | 1 308 | 87.9 % | 50.00 % | 47.17 % | −2.83 |
| 2023-04 | TRAIN | 1 288 | 89.4 % | 25.85 % | 38.35 % | +12.50 |
| 2023-05 | TRAIN | 1 295 | 87.0 % | 17.76 % | 24.09 % | +6.33 |
| 2023-06 | TRAIN | 1 304 | 90.6 % | 31.67 % | 28.37 % | −3.30 |
| 2023-07 | TRAIN | 1 435 | 96.4 % | 11.43 % | 12.54 % | +1.11 |
| 2023-08 | TRAIN | 1 436 | 96.5 % | 11.84 % | 9.40 % | −2.44 |
| 2023-09 | TRAIN | 1 352 | 93.9 % | 16.20 % | 23.59 % | +7.40 |
| 2023-10 | TRAIN | 1 351 | 90.8 % | 19.32 % | 27.54 % | +8.22 |
| 2023-11 | TRAIN | 1 254 | 87.1 % | 21.85 % | 44.26 % | +22.41 |
| 2023-12 | TRAIN | 1 354 | 91.0 % | 17.21 % | 49.11 % | +31.91 |
| 2024-01 | TRAIN | 1 272 | 85.5 % | 25.47 % | 35.85 % | +10.38 |
| 2024-02 | TRAIN | 1 237 | 88.9 % | 12.29 % | 48.34 % | +36.05 |
| 2024-03 | TRAIN | 1 311 | 88.1 % | 38.52 % | 52.40 % | +13.88 |
| 2024-04 | TRAIN | 1 241 | 86.2 % | 36.02 % | 53.51 % | +17.49 |
| 2024-05 | TRAIN | 1 322 | 88.8 % | 38.20 % | 47.66 % | +9.46 |
| 2024-06 | TRAIN | 1 270 | 88.2 % | 17.24 % | 44.57 % | +27.32 |
| 2024-07 | TRAIN | 1 302 | 87.5 % | 27.65 % | 63.36 % | +35.71 |
| 2024-08 | TRAIN | 1 304 | 87.6 % | 36.04 % | 55.29 % | +19.25 |
| 2024-09 | TRAIN | 500 | 55.6 % | 24.60 % | 63.40 % | +38.80 |
| 2024-09 | VAL | 421 | 78.0 % | 7.36 % | 58.43 % | +51.07 |
| 2024-10 | VAL | 1 264 | 84.9 % | 15.03 % | 50.47 % | +35.44 |
| 2024-11 | VAL | 1 216 | 84.4 % | 24.26 % | 56.09 % | +31.83 |
| 2024-12 | VAL | 1 331 | 89.4 % | 36.44 % | 47.63 % | +11.19 |
| 2025-01 | VAL | 1 259 | 84.6 % | 18.27 % | 48.61 % | +30.34 |
| 2025-02 | VAL | 1 198 | 89.1 % | 34.39 % | 32.72 % | −1.67 |
| 2025-03 | VAL | 1 258 | 84.5 % | 38.63 % | 41.02 % | +2.38 |
| 2025-04 | VAL | 1 298 | 90.1 % | 32.74 % | 41.68 % | +8.94 |
| 2025-05 | VAL | 1 271 | 85.4 % | 31.24 % | 36.51 % | +5.27 |
| 2025-06 | VAL | 1 297 | 90.1 % | 16.89 % | 31.92 % | +15.03 |
| 2025-07 | VAL | 1 350 | 90.7 % | 14.37 % | 45.41 % | +31.04 |
| 2025-08 | VAL | 1 329 | 89.3 % | 20.02 % | 47.18 % | +27.16 |
| 2025-09 | VAL | 1 324 | 91.9 % | 23.64 % | 21.83 % | −1.81 |
| 2025-10 | VAL | 1 266 | 85.1 % | 31.60 % | 51.34 % | +19.75 |
| 2025-11 | VAL | 1 223 | 84.9 % | 20.11 % | 57.48 % | +37.37 |
| 2025-12 | VAL | 1 325 | 89.0 % | 26.79 % | 32.53 % | +5.74 |
| 2026-01 | VAL | 1 260 | 84.7 % | 13.25 % | 29.52 % | +16.27 |
| 2026-02 | VAL | 1 190 | 88.5 % | 36.97 % | 66.72 % | +29.75 |
| 2026-03 | VAL | 1 286 | 86.4 % | 30.02 % | 62.13 % | +32.12 |
| 2026-04 | VAL | 1 259 | 87.4 % | 23.43 % | 39.08 % | +15.65 |
| 2026-05 | VAL | 1 347 | 90.5 % | 24.94 % | 30.88 % | +5.94 |
| 2026-06 | VAL | 1 253 | 87.0 % | 31.05 % | 51.16 % | +20.11 |
| 2026-07 | VAL | 1 359 | 91.3 % | 20.38 % | 22.81 % | +2.43 |
| 2026-08 | VAL | 1 419 | 95.4 % | 23.19 % | 22.55 % | −0.63 |
| 2026-09 | VAL | 1 049 | 90.7 % | 23.45 % | 30.31 % | +6.86 |

54/62 lignes mois-split à écart positif — mais c'est l'artefact de base-rate du point 2 qui gagne la majorité des mois ; le critère 3 pré-déclaré tranche : FAIL. Cohérent avec le garde-fou doctrine : les verdicts RELATIFS (ici l'écart agrégé) survivent aux bugs, la décomposition par état est le garde-fou composé.

## Limitations déclarées

- La vérité terrain est l'état crisp filtré du HMM lui-même (autoreférentielle, pré-déclarée) : le test porte sur la persistance TELLE QUE LE MODÈLE LA DÉFINIT — le naïf est jugé sur la même cible, la comparaison reste interne-cohérente.
- Les événements consécutifs se chevauchent (fenêtre forward 168 h) : n traité comme des heures, dépendance documentée.
- Le seuil crisp 0.8 laisse 93-94 % des heures crisp — l'échantillon sur-représente les heures confidantes ; les heures ambiguës (6 %) sont exclues des deux prédicteurs symétriquement.
- 3 états gaussiens diagonaux sur (ret, rv24) : les retours moyens par état sont ≈ 0 (|z| ≤ 0.002) — l'étiquette TENDANCE porte sur une micro-dérive (≈ +0.001 z), la séparation réelle est la volatilité. Aucun re-tuning autorisé.

## Leçon gravée

**À l'horizon 7 j, la matrice de transition APPRISE d'un HMM 3 états dit elle-même que le régime ne persiste pas : pi_t @ A^168 oublie la superposition et retombe sur la stationnaire.** L'adaptateur 90 j n'est pas battu par un HMM sur sa propre cible ; et la persistance crisp à 7 j est anti-corrélée (le naïf est sous le hasard). Tout usage futur d'un régime HMM doit se limiter à des horizons OÙ LA MÉMOIRE DES TRANSITIONS VIT (≪ 1/(1−a_ii) heures, ici ~30-40 h), et son évaluation doit TOUJOURS inclure un critère par état contre le base-rate — le critère agrégé seul valide des prédicteurs constants.

