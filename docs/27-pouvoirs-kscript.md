# 27 · POUVOIRS kScript — LE REGISTRE D'EXPLOITATION

> Créé le 01/10/2026. Réponse chiffrée au diagnostic : « tu as des outils
> puissants gratuits par rapport à TradingView, tu n'exploites aucun pouvoir ».
> Méthode reproductible : `scripts/studies/x501_openmarket/x501_exploit_audit.py`
> (chaque capacité sourcée des 78 pages de doc scrapée, testée contre nos 10 scripts).

## LE VERDICT GLOBAL

**28/53 capacités exploitées = 52,8 %** — sur les 53 pouvoirs du langage
identifiés dans la doc officielle (quick-reference + 78 pages), nos 9
kScripts + le scanner en utilisent 28. Le cœur broker perps est bien
exploité (11/16 : `instrument="perps"`, `leverage`, `makerFeePercent`/
`takerFeePercent`, `funding="data"`, `onLiquidation`, `pyramiding`,
`slippageModel`, `closeAll`, getters d'équité — 8/10 scripts), les alertes
et la lib TA aussi. **Le trou est la data** : la famille « sources
premium » est à **1/8**, l'orderbook à 1/3, les sorties broker avancées à
0. Détail par famille :

| Famille | Exploité | Verdict |
|---|---|---|
| alertes | 2/2 | complet |
| données (sources/TF) | 7/9 | bon |
| broker (exécution) | 11/16 | bon, sorties avancées à 0 |
| analyse (TA/CVD/sessions) | 3/5 | acceptable |
| orderbook (depth native) | 1/3 | **le pattern gagnant d'Aster, dormant** |
| sources premium (institutionnelles) | 1/8 | **le scandale** |
| langage (collections/loops/libraries) | 2/8 | dette de style, pas d'edge |
| visu | 1/2 | mineur |

## LES 7 FLUX INSTITUTIONNELS GRATUITS (0 usage — TradingView les facture)

La page `core-concepts/data-sources` liste les flux que `source()` charge
directement dans un kScript, sans API externe, sans clé, inclus dans le
backtester gratuit. Nos scripts n'en consomment que 3 (`funding_rate`,
`liquidations`, `open_interest`) + `buy_sell_volume` dans 1 script. Les 7
restants :

1. **`etf_flow` / `etf_holding` / `etf_premium_rate`** — la pression ETF
   BTC/ETH au quotidien : le moteur du régime 2024-2026, absent de nos
   filtres de régime.
2. **`cme_oi`** — l'open interest CME : les institutionnels, notre meilleur
   proxy de « smart money » structurel.
3. **`deribit_implied_volatility` / `deribit_volatility_index`** — le VIX
   crypto : le régime de vol que le regime_filter cherche à deviner depuis
   les bougies.
4. **`options_open_interest` / `options_volume` / `skew`** — le skew
   d'options : la position du marché sur la direction, en avance sur le
   spot.
5. **`long_short_ratio`** — le LSR : on en avait collecté 8 jours à la main
   (angle mort documenté dans `docs/26-openmarket-donnees.md`)… il est
   NATIF. L'angle mort disparaît.
6. **`binance_treasury_balance`** — la trésorerie Binance : pression
   structurelle d'échange.
7. **`ethena_positions`** — le carry USDe : le flux de financement
   structurel.

## L'ORDERBOOK NATIF (le pattern qui a rapporté sur Aster)

Sur Aster, la data premium qui a fait la différence était le carnet
d'ordres : `depth.db` (54 M bins, 30 s, 15 symboles), `wall_detector.py`,
`aster_absorption.py`. kScript embarque la même couche **en natif** :
`sumBids`/`sumAsks` (pression par profondeur `depthPct`), et surtout
`maxBidAmount`/`maxAskAmount` — **la détection des baleines dans le
carnet, une ligne, dans le backtest**. Usage actuel : `sumBids/sumAsks`
dans 1 script sur 10, les max/min amounts nulle part. C'est la vague 2 du
plan ci-dessous.

## LES 4 SORTIES BROKER DORMANTES (broker 16 − 11)

`strategy.exit(profit=/loss=)` (brackets 1 ligne), **`trailPoints=`/
`trailOffset=`** (trailing stop NATIF — le `_MK` code sa sortie à la main),
`ocaName=` (brackets OCA), `strategy.cancelAll()`, et les stats natives
`strategy.maxDrawdown()`/`closedTradeCount()` (les rapports de preuve live
re-calculent à la main ce que le broker simulé fournit).

## LE PLAN D'ACTIVATION (3 vagues, ordre d'impact sur la médiane)

**Vague 1 — le régime institutionnel (impact max, effort min).** Un filtre
de régime composite branché sur les sources premium : ETF flow (3 j) ×
skew options × vol Deribit × CME OI. Testé comme le régime BTC du domaine
Aster (le quadrant à éviter/à chercher), pré-enregistré, falsifié sur 733 j
de klines avant promotion. Chaque −X % de trades perdus dans le mauvais
régime vaut, à la règle des coûts (`docs/25`), plusieurs bps/côté.

**Vague 2 — l'absorption native.** `maxBidAmount/maxAskAmount` +
`sumBids/sumAsks` à depthPct 1–5 % : l'alpha absorption (le mur qui tient =
soutien) testé en one-shot `scripts/studies/`, avec la même discipline que
la vague 1. Sur Aster, c'est la famille qui a produit l'AL Score et le
profil qualité (WR 81 %, DD 5,4 %).

**Vague 3 — l'hygiène d'exécution.** `trailPoints` dans les `_MK` (sortie
native, moins de code, moins de bugs), `ocaName` pour les brackets,
`strategy.maxDrawdown()` dans les rapports, `cancelAll` à l'invalidation.
Aucun edge espéré ici — de la robustesse et de la lisibilité, qui réduisent
le risque de bug du harnais (la leçon T7 d'Aster).

La règle de promotion ne change pas d'un iota : tout candidat passe par le
backtest pré-enregistré (méthode `docs/03-methodology.md`), le registre
(`docs/20-registre-indicateurs.md`) reçoit le verdict chiffré, et le papier
forward reste le juge. Exploiter les pouvoirs ne veut PAS dire croire plus
vite — ça veut dire tester plus de portes, avec la même clé.

## EXÉCUTION — LES VAGUES 1-2 SONT ACTIVÉES (le 01/10/2026)

Les trois scripts ci-dessous sont écrits, pré-enregistrés et passent la QA
statique (`qa_vagues_x501.py` — 122 contrôles, 0 échec ; les 4 QA existantes
restent PASS). Ils EXPLOITENT les familles dormantes : **le taux d'exploitation
monte de 28/53 (52,8 %) à 36/53 (67,9 %)** — sources premium **1/8 → 7/8**
(reste `ethena_positions`, sans use case à ce stade), orderbook **1/3 → 2/3**,
données 7/9 → 8/9. 17 dormants restants : la vague 3 (5 sorties broker, hygiène
sans edge), `minBid/minAsk`, volume profile, le langage (collections, loops,
bibliothèques — dette de style, pas d'edge).

**Le fix review-2 (dans l'esprit des 3 correctifs de la review PR #1)** : la
regex de la capacité `options_oi / options_volume / skew` était invalide
(parenthèse capture non fermée → fallback `re.escape` = chaîne littérale jamais
matchée → capacité comptée DORMANTE à tort). Le bug se révélait précisément
parce que la vague 1 branche ces flux. Corrigé en `"(?:options_[a-z_]*|skew)"`,
l'audit reste bit-à-bit reproductible (13 scripts : 12 .ks + le scanner).

| Fichier | Vague | Ce qu'il fait |
|---|---|---|
| `Operation_x501_Signature_H1_RI.ks` | 1 | la Signature H1 + le filtre de régime institutionnel : score RI = moyenne des 5 composantes écrêtées (ETF flow 3 j en sigma, CME OI 3 j × signe prix, DVOL vs MM 30, dérive skew 1W sur 5 j, LSR top traders contrarian), seuil ±0,10, poids égaux figés dans le code |
| `x501_observe_regime.ks` | 1 | l'observe des 8 flux premium (9 souscriptions) : table de disponibilité par flux, composantes brutes, alerte de bascule de quadrant — la vérification « le flux répond » AVANT le filtre |
| `Operation_x501_Absorption_H1.ks` | 2 | le pattern Aster en natif : mur = `maxBidAmount`/`maxAskAmount` ≥ 3× sa moyenne 200, attaque = vague taker ≥ 2× sa moyenne, tenue = écrasement intrabar ≤ 0,8 %, reprise = EMA flux net 6 + déséquilibre de carnet ≥ 1,2 (`sumBids`/`sumAsks`) |

**La discipline no-repaint des flux lents (le piège qui tuait le backtest).**
`etf_flow`/`cme_oi`/`skew` sont DAILY : sur un chart 1h, l'engine
forward-fille la valeur du jour en cours dès 00h alors que la donnée réelle
n'est publiée qu'en fin de journée. Les trois scripts ne lisent donc JAMAIS
le bucket courant des séries lentes : ils projettent via `htf(..., "1D")`
et lisent `[1]` et avant (les buckets complétés). `long_short_ratio` n'a
pas de membre `.time` (lecture snapshot directe), le DVOL est continu
(lecture `[0]` sûre), le skew s'épelle `onemonth`.

**Le fail-open (pré-enregistré).** Si moins de 3 des 5 composantes RI
répondent sur un symbole (data premium absente), le filtre devient
TRANSPARENT : le backtest mesure « aucun effet » et non « tout bloqué ».
L'observe donne la table de disponibilité par symbole pour le vérifier
visuellement avant tout backtest.

**Les limites assumées.** (1) L'agrégation `htf()` d'une série `.value`
(dernière valeur vs somme du bucket) doit être confirmée au premier run :
si les valeurs ETF ressortent ~24× celles de la plateforme, la composante
se saturera et la falsification le montrera immédiatement — c'est écrit
ici AVANT le run. (2) La profondeur d'historique orderbook en backtest est
limitée (la doc donne ~1 semaine à 1m, des mois à 1h) : le backtest du
pattern absorption est une falsification initiale sur la fenêtre
DISPONIBLE, pas une preuve 733 j — la vraie validation = papier forward
(protocole v11), les alertes « mur géant » des deux scripts stratégies
servent au comptage en direct.

**Prochain jalon (vague 3 — hygiène, aucun edge espéré)** : `trailPoints`
dans les `_MK`, `ocaName` pour les brackets, `strategy.maxDrawdown()` dans
les rapports de preuve live. Puis les backtests A/B pré-enregistrés des
vagues 1-2 (RI on/off sur BTC et ETH ; absorption vs signature) et le
verdict au registre `docs/20`.

## EXÉCUTION — LA VAGUE 3 EST ACTIVÉE + LE PROTOCOLE A/B EST PRÉ-ENREGISTRÉ (le 01/10/2026)

**La vague 3 (hygiène broker, aucun edge espéré — la fidélité d'exécution,
pas un signal)** est câblée dans les DEUX `_MK` (H1 et H4), pré-enregistrée
dans leurs en-têtes :

| ajout | capacité kScript | ce que ça change |
|---|---|---|
| trail natif du runner (input `useNativeTrail`, **défaut false** = la référence MC v20 reste bit-à-bit) + `trailNativePct` (1,5 %) | `trailPoints`/`trailOffset` | le RUN porte un trail qui ratatine INTRABAR (la piste manuelle ne ratatine qu'à la clôture) ; la piste manuelle reste en stop plancher sur la même jambe ; `trailPoints = tp2R × riskPx` = activation immédiate à l'armement (l'excursion favorable TP2 est déjà atteinte) |
| groupes OCA nommés PAR TRANCHE (`x501L-TP1`, `x501L-TP2`, `x501L-RUN`, idem côté S) + `ocaName="x501L"/"x501S"` sur les 6 entrées | `ocaName` | les noms remontent au log du testeur (preuve live) ; PRÉ-ENREGISTRÉ : ocaName = « quand l'un remplit, les autres s'annulent » — l'échelle TP1/TP2/RUN ne partage JAMAIS un même groupe (un TP1 rempli ne doit pas tuer le runner) |
| `strategy.cancelAll()` au coupe-circuit -25 % quand flat | `strategy.cancelAll()` | **bug réel corrigé** : un ordre limite maker encore en file pouvait remplir APRÈS l'arrêt du plan (-25 %) et rouvrir une position ; la file entière est purgée, idempotent |
| rapport fin de run (plotTable + alert sur `isLastBar`) | `closedTradeCount`, `winTradeCount`, `lossTradeCount`, `maxDrawdown` | les getters NATIFS croisent nos compteurs internes (nTr/WR/maxDD en USD vs ddPct interne, mkFills/mkFb/mkTOut/mkInv) — toute divergence = bug d'état à corriger AVANT la preuve live (protocole v11) |

**Le refus pré-enregistré** : `strategy.exit profit=/loss=` (distances en
ticks de l'API) reste DORMANT par design — dépendant de la taille de tick du
symbole, notre échelle calcule des prix absolus depuis la distance de stop
réelle. Famille broker : **15/16**, la case refusée est documentée, pas
oubliée. Le taux d'exploitation monte de **36/53 (67,9 %) à 40/53
(75,5 %)** — `x501_exploit_audit.py` re-run bit-à-bit (13 scripts : 12 .ks +
le setup js).

**Le protocole A/B des vagues 1-2 est PRÉ-ENREGISTRÉ** dans
`docs/28-protocole-ab-x501.md` (6 runs, critères figés le 01/10/2026, 4
verdicts dans l'ordre : DATA_ABSENTE / PROMOTION / KILL / INCONCLU) avec le
moteur déterministe `x501_verdict_ab.py` (bootstrap 10 000, seed 501, stdlib
pure). Les 3 tests (RI-BTC, RI-ETH, ABS-BTC/ETH) sont entrés au registre
`docs/20` au statut PRÉ-ENREGISTRÉ. Le cas attendu au premier run est
INCONCLU (n_B < 20) : la règle « fenêtre élargie, JAMAIS de promotion sous
N_MIN — pas même quand le bootstrap sourit » est écrite AVANT les runs, et
la démo du moteur sur les CSV de référence l'illustre (P = 0,9358, n_B = 15
→ INCONCLU imposé).
origin/main
origin/main
