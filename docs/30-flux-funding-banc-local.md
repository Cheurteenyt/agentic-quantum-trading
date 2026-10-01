# 30 · OPENMARKET — LE BANC DE TEST LOCAL DES FLUX DORMANTS (vague 5)

> Créé le 01/10/2026. Le flux taker natif des klines et le funding
> multi-années deviennent des signaux MESURÉS — avec la grille pré-déclarée
> et le verdict mécanique. Les chiffres de recherche : `docs/25`,
> la chaîne de preuve maker : `docs/29`, le registre : `docs/20`.

## LA QUESTION (le pouvoir dormant exactement)

Le diagnostic fondateur des vagues d'exploitation : « tu as des outils
puissants gratuits et tu n'exploites aucun pouvoir ». Les vagues 1-3 ont
branché les capacités kScript (75,5 %), la vague 4 a mesuré le fill maker.
Restait le dernier pouvoir dormant, le plus massif : **deux séries gratuites
et natives n'avaient JAMAIS servi de signal** — (i) le **flux taker** des
klines Binance 1h (`taker_buy_quote_volume` : la quote agressive côté
acheteur, à chaque barre — le proxy historique de l'absorption que la vague 2
exploite en live via l'orderbook) et (ii) le **funding Binance 8h**
multi-années (le thermomètre du positionnement). La vague 5 les passe au
banc : 80 symboles × **26 208 barres 1h** (01/10/2023 → 27/10/2026, 1 092 j,
**0 gap**) = **2 053 975 barres**, 3 285 paiements de funding par symbole.
Une minute de CPU locale au lieu de 8 runs kScript du user — la question est
tranchée AVANT de dépenser les backtests de la plateforme.

## LA DISCIPLINE (pré-enregistrée avant la première mesure)

La grille, les hypothèses et le verdict sont gravés dans l'en-tête de
`x501_flux_local.py` AVANT tout chiffre — aucune cellule n'a été regardée
avant l'écriture du fichier. **Grille pré-déclarée** : 12 cellules de panel,
toutes rapportées (aucun choix post-hoc de lookback) —

| famille | score | lookbacks pré-déclarés | horizons | hypothèse (sens gravé AVANT) |
|---|---|---|---|---|
| **A. flux taker** | D = 2·tbqv/qv − 1, score = EMA(D, L) sur les barres clôturées | L ∈ {6, 24, 72} barres | H ∈ {24, 72} barres (open→open) | **continuation** (AUC > 0,5 attendu — le mécanisme absorption) |
| **B. funding** | moyenne des K derniers paiements 8h ≤ t | K ∈ {9, 21, 90} (3/7/30 j) | H ∈ {24, 72} barres | **contrarian** (AUC < 0,5 attendu — crowding payé cher) |

**Verdict mécanique par cellule** (le critère AUC du domaine, celui qui a
exigé AUC ≥ 0,60 sur 60 j frais pour le ML) : IC 95 % (bootstrap 1 000 par
journées UTC, seed 501) **contient** 0,5 et |AUC − 0,5| < 0,02 = **KILL** ;
l'IC contient 0,5 sinon = **INCONCLU** ; l'IC **exclut** 0,5, |AUC − 0,5| ≥
0,05 et le sens confirme l'hypothèse = **CANDIDAT** (registre docs/20,
re-test 60 j frais exigé, jamais de promotion directe) ; sens opposé =
**CONTEXTE** (hint post-hoc, convention registre 27/09). Convention temps
stricte : à l'open de t, barres connues ≤ t−1, paiements connus ≤ t.

## LES RÉSULTATS (flux_local.json, reproductible bit à bit)

**Étude A — flux taker : 6/6 KILL.** AUC de 0,5008 (L6_H24) à 0,5038
(L24_H24), tous les IC 95 % contiennent 0,5 largement (ex. L24_H24 :
[0,4959, 0,5119]) ; deltas médians +9,3 à +31,9 bps, tous dans le bruit.
**Étude B — funding : 6/6 KILL.** AUC 0,4956 (K9_H72) à 0,5103 (K90_H72),
IC contenant tous 0,5 ; deltas −21,7 à +46,7 bps. Le soupçon K90 (30 j)
au sens « momentum du carry » (delta +46,7 bps à H72) reste sous le seuil
(|AUC − 0,5| = 0,0103 < 0,02) — statut KILL, pas de re-test opportuniste.

**Étude C — projeté sur le pool P1 (CONTEXTE par nature, in-sample de la
sélection)** : score flux L24 sur les 469 entrées → delta médian
**+0,089 R** (P(bootstrap delta > 0) = **0,686**) — sous le seuil de
promotion du moteur (0,70) ET sous le Δ minimal (+0,10 R) : **INCONCLU**.
Score funding K21 → delta **−0,096 R** (P = **0,359**) : direction
contrarian mais non concluant au moteur. La médiane R du pool est
**−0,319** (asymétrie breakout : moyenne +0,180, WR faible, RR élevé) —
le filtre flux aurait relevé la médiane de −0,370 à −0,281 sans être
significatif. Aucun filtre ne rentre dans les kScripts sur cette base.

## LA PLOMBERIE EST PROUVÉE VIVANTE (le point qui fait la valeur du KILL)

Un KILL ne vaut que si le harnais détecterait un vrai signal. La QA
(`qa_flux_local_x501.py`, **9 familles, 0 échec**) contient le **test
d'altération** : en décalant le score d'une barre vers l'avant
(look-ahead), l'AUC DÉCOLLE — BTC 0,5306 vs 0,5079 strict ; et sur le
rendement intrabar de la même barre, **BTC 0,6103 / ETH 0,6065** : le flux
taker CONTIENT de l'information (l'agression coïncide avec le mouvement),
la plomberie la voit, et le verdict strict ~0,5 est donc le résultat réel
d'un filtre exploitable qui n'existe pas — pas un bug. Les autres contrôles :
étalonnage AUC sur cas exacts (séparations parfaites, ex-aequo), mutation
des barres futures = score inchangé (zéro look-ahead), convention funding
recalculée indépendamment, 469 entrées du pool avec t_in = opens exacts,
AUC par symbole sur 8 liquides ≈ 0,5 (le pooling ne dilue rien :
0,4978/0,5022/0,5009), re-exécution **bit à bit** (7 406 octets).

## CE QUE ÇA FERME — ET CE QUE ÇA NE FERME PAS

**Clos** : le *niveau continu* du flux taker (EMA 6-72 h) et la *moyenne*
du funding (3-30 j) comme FILTRES de signal au panel — 12 cellules mortes
au critère du domaine, la question ne sera pas re-posée sous cette forme.
C'est la 5e falsification fermée du domaine (fz −22,0 bps, flush OI +0,1/+0,2
bps, ML AUC 0,4994, et maintenant flux + funding panel).

**Pas clos** : le **pattern absorption événementiel** de la vague 2 (mur ≥ 3×
moy 200, attaque ≥ 2×, tenue ≤ 0,8 %, reprise ≥ 1,2) n'est PAS réfuté — c'est
un événement ordonné à 4 conditions, pas un score de moyenne, et son champ
orderbook (`maxBidAmount`) n'a pas d'équivalent dans les klines. Le protocole
A/B (docs/28) reste son juge. La leçon du banc : un filtre « flux moyen » est
mort ; seule la structure événementielle peut prétendre à un pouvoir —
exactement la leçon du registre Aster (« la dynamique bat la moyenne »).

**SUITE (vague 6, `docs/31`) — la structure événementielle a été passée au
banc en proxy klines** : prime de structure E3 vs E1 réfutée 0/4 (la
confirmation est TARDIVE — le rebond se joue dans la barre de tenue), le
miroir SHORT est anti-signal (le mur perd), le proxy du mur sélectionne la
plaine illiquide. Ce que cette fermeture NE couvre PAS : le pattern
orderbook RÉEL (maxBidAmount), jugé par les runs 3-4 du protocole —
désormais EN QUEUE de file (ABS_DEPRIORISE, derrière RI/MK6).

origin/main
origin/main
origin/main
origin/main
origin/main
**L'usage de la data** : `docs/26` re-qualifie les séries — le funding et le
flux taker sont désormais **banc-testés** (collectés, mesurés, fermés au
panel) et non plus simplement dormants. La collecte continue (l'entrepôt
s'étend, les fenêtres se rallongent) ; un re-test nécessiterait un
PRÉ-ENREGISTREMENT explicite au registre avec une hypothèse nouvelle, pas un
re-run de curiosité.

## REPRODUCTION

```bash
X501_DATA_DIR=<dir des {SYM}_1h.csv et {SYM}_funding.csv> \
    python3 scripts/studies/x501_openmarket/x501_flux_local.py   # -> flux_local.json
X501_DATA_DIR=<dir> python3 scripts/studies/x501_openmarket/qa_flux_local_x501.py
```

Limites pré-enregistrées (L1-L5, en-tête du script) : le flux est Binance, pas
openmarket (le MÉCANISME est testé, pas le venue exact) ; l'IC bootstrap
rééchantillonne les journées sur un échantillon réduit déterministe de
50 000 points par cellule (l'AUC ponctuelle est full-sample) ; la dichotomie
à la médiane mesure la séparation HAUT/BAS, pas la forme monotone ; les
horizons sont en barres, pas en heures calendaires.

Bande de coûts de lecture : taker 6,1 bps/côté, maker 2 bps/côté —
l'étalon d'exploitabilité d'un filtre reste 12,2 bps aller-retour taker.
