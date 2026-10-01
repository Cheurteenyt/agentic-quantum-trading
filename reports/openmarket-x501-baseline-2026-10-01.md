# Baseline openmarket ×501 — réédition v2 (2026-10-01)

> Réédition de `openmarket-x501-baseline-2026-09-30.md` intégrant le reclassement
> officiel MC v20 (Task 28) et la couche signaux om_v29 (PR #2 volet 1). Toutes les
> valeurs citées proviennent des JSON produits par les scripts versionnés du dépôt
> (`scripts/x501_v21_results/`). Aucun chiffre ne sort d'une mémoire humaine : tout
> est régénérable par re-exécution.

## 1. Mission et contraintes (inchangées)

Objectif : porter 100 $ sur openmarket.xyz vers 50 100 $ en 12 mois (×501, +50 000 %)
en pilotage entièrement automatique, avec un drawdown maximal strict de 25 %, un
capital fixe (aucun apport, aucun retrait) et zéro intervention manuelle. La contrainte
de drawdown est une contrainte physique du moteur (ratchet), pas une ligne de reporting :
le pire cas mesuré sur 12 000 trajectoires v20 est de 25,000000 % exactement, sans une
décimale de dépassement. L'objectif ×501 à 12 mois n'est pas un engagement : c'est la
cible d'asymptote qui fixe le cap, les probabilités atteignables sont chiffrées plus bas
(jalon 250 $ à 12 m : 73,3 % en exécution maker). Le chemin honnête vers l'objectif passe
par 36 mois (P(50 100) à 36 m : 23,5 % en maker δ=5) — ce point est gravé depuis v17
et n'est pas renégocié par cette réédition.

## 2. Reclassement officiel MC v20 (sans gate, coûts mesurés)

Les falsifications v27 (détail section 3) ont retiré tous les scénarios « gate » de la
config officielle ; le noyau ratchet v12 bit à bit a donc été re-exécuté en 12 000
trajectoires × 36 mois, sans haircut gate, avec la courbe de coûts alignée sur la mesure
maker réelle (52 728 tentatives, fenêtre 4 h, `x501_maker_v27.py`). La référence
certifiée 641,99 $ est reproduite au centime (audit T0), la continuité v17 S1 est bit à
bit (475,36 $), la repro T3 est bit à bit — la chaîne de certification n'a pas bougé.

| Scénario | bps/côté | Médiane 12 m | [P25 ; P75] | P(250) 12 m | P(1250) 12 m |
|---|---|---|---|---|---|
| W0 référence certifiée | 0,0 | **641,99 $** | [277 ; 1 692] | 80,1 % | 33,2 % |
| W4 maker δ=5 | 1,7 | **496,13 $** | [224 ; 1 272] | 74,4 % | 26,7 % |
| W1 maker δ=2 (central) | 2,0 | **475,36 $** | [216 ; 1 208] | 73,3 % | 26,7 % |
| W2 taker réel | 6,1 | **272,66 $** | [145 ; 640] | 57,2 % | — |
| W3 stress | 8,2 | **215,66 $** | — | — | — |

La lecture d'ingénierie est sans ambiguïté : l'écart maker/taker vaut **+202,7 $ de
médiane 12 m (+74 %)** entre 6,1 et 2,0 bps. L'exécution maker n'est donc pas une
optimisation cosmétique, c'est le seul levier chiffré qui déplace la médiane d'une zone
vers l'autre. C'est pourquoi la Task 28 l'a instrumentée dans le code exécutable :
entrées passées d'ordres marché à des ordres limite à close ± δ (slider 0–20 bps,
défaut 2), TTL d'annulation de 5 barres (jamais d'entrée sur signal périmé), machine
d'état protégée (le reset à plat ne s'applique qu'en l'absence de limite vivante, sinon
la position s'ouvrirait sans TP/SL), fill compté sur `positionAvgPrice` réel.

Fragilité n°1 maintenue ouverte et assumée : les fills 97,9 % (δ=2) / 95,8 % (δ=5)
viennent d'une mesure statique ; la circularité levier + fill maker ne sera considérée
comme validée qu'après les fills réels `_MK` en papier et la preuve live 90 j
(protocole v11, 4 relevés/jour). Rien de ce qui précède ne repose sur une promesse de
fill : le scénario W2 taker réel (272,66 $) est dans la baseline précisément pour
encadrer le cas où le maker ne serait pas déployable.

## 3. Falsifications actées (rappel v27, non re-négocié)

Sur 23 mois horaires et ~560 000 points collectés en API publiques gratuites, les trois
voies « gate précis » ont été tuées en walk-forward chronologique réel, et la baseline
les tient pour mortes jusqu'à preuve contraire sur données fraîches :

- **Règle fz signal-6** : split 60/40 chrono, train +31,4 bps → test **−22,0 bps**
  (inversion de signe) → KILL walk-forward. La dose-réponse fz n'est pas monotone.
- **Flush OI horaire** : 5 576 événements bruts à +46,1 bps d'excès s'effondrent à
  **+0,1 bps** après dédup 24 h (1 464 événements) — le mirage était du double-comptage
  de clusters. MFE48 des flush ≈ baseline (3,1–3,3 % vs 3,03 %).
- **Gate ML (11 features)** : après correction du split inter-symboles déguisé, l'AUC
  chrono réel est **0,4994** (L1) / 0,5327 (L2), les 4 plis roulants alternent le signe
  (0,483/0,533/0,488/0,471) → bruit. Le score ML reste DIAGNOSTIC ONLY (A6), critère de
  promotion durci : AUC temporel ≥ 0,60 sur 60 j de données fraîches, jamais atteint.
- Le facteur ×22 (V4, 38 991 $) est une borne supérieure diagnostique, PAS un plan.

## 4. Couche signaux om_v29 — « outils gratuits > TradingView » (PR #2 volet 1)

Réponse mesurée à la critique héritée : les 4 familles de signaux rendues possibles par
la collecte gratuite ont été testées sous le protocole anti-mirage gravé (dédup
temporelle 1/4 h ou 1/24 h, split chrono GLOBAL par ts 60/40, verdict sur le TEST
uniquement, baseline recalculée dans chaque split). Verdicts (`signaux_om_v29.json`,
210 912 observations f24) :

| Signal | Verdict | Mesure test décisive |
|---|---|---|
| S1 carry funding (annualisé, quintiles) | **KILL** | train +29,6 → test **−8,6** bps (inversion) ; quintiles test non monotones (−2,8 / +13,5 / +10,9 / −13,9 / −11,4) |
| S2 impulsion OI × prix (4 quadrants 24 h) | **ADVISORY** | dispersion test **28,1 bps** : flush (OI−p−) **+9,9** vs tendance_L (OI+p+) **−18,2** ; n_test 20 348 ; rangs non stables train/test → pas de gate |
| S3a position range 90 j | **KILL** | test non monotone (+4,7 / +18,9 / −25,9 / −11,3 / +9,5) |
| S3b compression range 30/90 | **KILL** | signe inversé train/test |
| S4 régime vol × E[R] alphas (terciles ATR% 1h) | **DIAG** | 183/469 trades classables (kline 400 j) ; T1 ER_long +0,82 R vs T3 −0,33 R — in-sample, n=60–65/tercile, non actionnable |

Intégration opérationnelle, sans toucher à un seul contrôle bloquant : le pont
d'armement expose un **A7 advisory** (même pattern que le A6 ML de v25) qui charge le
contexte courant par symbole (`contexte_om_v29.json`, fraîcheur < 26 h) et le logge à
chaque armement — funding annualisé, position dans le range, compression, verdicts.
La passe live du 2026-10-01 est ARMED avec A7 actif (12 longs / 9 shorts / 3 bloqués
partiels / 0 écartés). Le collecteur d'observation `x501_observe_om_v29.ks` rend la
même couche lisible sur le graphe openmarket sans abonnement (structure D1, régime
ATR%, OI natif, funding), QA observe 3/3 PASS. La preuve temporelle de S2 s'accumule
maintenant automatiquement à chaque relevé 4×/j ; c'est le seul des quatre signaux qui
a survécu au protocole, et il n'a droit à aucune décision bloquante avant qu'elle soit
concluante.

## 5. Config officielle certifiée (inchangée dans ses blocages)

- Pool : 469 trades (2023-12 → 2026-09), 40+ symboles, 10 alphas (A1L..A6S), diversité
  validée par MC — les filtrages alpha (A4 seul 563 $) et symbole (walk-forward 693 $
  vs 1 664 $ tout) sont KILL : la fréquence et la diversité gagnent.
- Autorité de blocage : gate signal-6 (règles conservatrices MC-validées) ; échelle
  risque 50/25/100 ; trail résiduel validé supérieur (le trail serré 75 %/88 % est
  KILL : WR 19 %, sorti par le bruit).
- Exécution : maker δ=2 instrumenté (ordre limite + TTL 5 barres + état protégé) ;
  fallback marché = scénario W2 chiffré.
- Boucle zéro intervention re-certifiée bout en bout après chaque modification de code :
  QA statique (scanner PASS 0 échec, kscript PASS 0 échec, observe 3/3 PASS) → SHA256
  manifeste → planificateur GO (G1–G5) → ARMED → journal.
- Cadence : 0 3,9,15,21 UTC (hors fenêtres funding) ; protocole 90 j (4 relevés/jour)
  en service, journal `scheduler_loop_v23.jsonl`.

## 6. Probabilités officielles et jalons (source MC v20, W1 maker δ=2)

Jalons 12 m : P(≥250 $) 73,3 % ; P(≥500 $) 52,1 % ; P(≥1 250 $) 26,7 %. À 36 mois,
P(≥50 100 $) vaut 23,5 % en maker δ=5 et 35,7 % en référence 0 bps — l'écart entre ces
deux chiffres EST le prix de l'exécution, et il est plus grand que tout ce que les
falsifications ont laissé comme espoir de gate. La stratégie officielle est donc fixée :
pas de nouveau gate tant que la preuve temporelle ne l'exige pas, tout le surplus
d'effort va à l'exécution (fills réels `_MK`, slippage in-situ) et à la discipline
90 j. Le prochain jalon de décision est J+30 du protocole live ; toute modification de
la config avant cette date devra passer le même protocole de falsification que v26/v27.
