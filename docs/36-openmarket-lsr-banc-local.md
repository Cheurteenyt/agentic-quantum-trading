# 36 · OPENMARKET — LE BANC DU LSR (vague 11)

> Créé le 01/10/2026. La dernière source premium du filtre RI (`docs/27`,
> vague 1, composante n°5 « LSR top traders contrarian ») passe au banc.
> `docs/26` gravait : « le LSR 4 h (8 jours) ne permet aucun test de gate —
> il est collecté pour plus tard, pas exploité ». Le « plus tard » est
> arrivé : le collecteur versionné `x501_collect_lsr_v11.py` (Bybit v5
> public, pagination `cursor` — le paramètre `interval` n'existe pas sur
> cet endpoint, mesuré) livre **72 000 lignes LSR 4h + 13 200 lignes LSR 1d**
> sur les 12 symboles om_v27, fenêtre commune **2024-01-05 → 2026-09-30
> (~2,74 ans)**, 0 doublon, 0 gap, 0 valeur hors domaine. Le LSR passe de
> 8 jours intestables à un panel profond falsifiable. Étude :
> `x501_lsr_local.py`, sortie versionnée `lsr_local.json` (digest
> SHA-256 `c8478385f7fce150…`), QA `qa_lsr_local_x501.py` (49 contrôles,
> 0 échec).

## LA DISCRIMINATION AVEC LES VAGUES PRÉCÉDENTES

Cinq bancs ont déjà fermé les familles de positionnement : le funding
(prix du positionnement, vague 5), le FLUX du CAPITAL ΔOI (vague 8), le
NIVEAU du CAPITAL (vague 9), la FORME en U du régime capital (vague 10).
Restait le POSITIONNEMENT DE LA FOULE : la fraction de comptes longs (le
LSR) et sa BASCULE. L'hypothèse à tester est celle que le filtre RI
revendique depuis la vague 1 : **contrarian** — la foule longue pré-cède
la baisse (sens −1). Son miroir mécanique : le FLUX du positionnement (les
comptes qui basculent), discrimination exacte avec la vague 8 qui mesurait
le flux du capital. Aucune de ces cellules n'a été regardée avant
l'écriture du pré-enregistrement dans l'en-tête de `x501_lsr_local.py`.

## LE PRÉ-ENREGISTREMENT (gravé AVANT tout chiffre)

13 cellules, TOUTES mesurées et rapportées :

| étude | score | cible | sens | grille |
|---|---|---|---|---|
| A — contrarian NIVEAU | z_L(buyRatio 4h) | fwd_H signé | −1 | L ∈ {180, 540} barres 4h (30 j, 90 j) × H ∈ {6, 18} (24 h, 72 h) |
| B — FLUX du positionnement | buyRatio[t−1] − buyRatio[t−1−L_Δ] | fwd_H signé | −1 | L_Δ ∈ {6, 42} (1 j, 7 j) × H ∈ {6, 18} |
| C — RÉPLICATION 1d | z_L(buyRatio 1d) | fwd_H signé | −1 | L ∈ {30, 90} j × H ∈ {1, 3} j |
| D — pool P1 CONTEXTE | z_180(buyRatio 4h) au t_in | R du pool | −1 | split médian, bootstrap diff médianes 10 000 |

Critère AUC du domaine inchangé (KILL si IC contient 0,5 et |AUC−0,5| <
0,02 ; CANDIDAT si l'IC exclut 0,5 ET |AUC−0,5| ≥ 0,05 ET le sens confirme ;
CONTEXTE si l'IC exclut 0,5 mais le sens s'oppose ; INCONCLU sinon) ;
bootstrap IC 1 000 par journées UTC, seed 501, réduction 50 000 ;
l'étalon d'exploitabilité reste 12,2 bps A/R taker. Convention temps
stricte transposée des vagues 8/9/10 : à l'open de la barre t, la dernière
ligne LSR connue est estampillée t−P ; la ligne pile à l'open n'est JAMAIS
lue (le shift `s_full[1:] = score[:-1]` grave la règle au bit près). La
règle de consommation est SÛRE sous les deux interprétations d'estampillage
(START partiel ou END) : zéro look-ahead dans les deux cas, une période de
lag déclarative au pire.

## LA DONNÉE ET SA SÉMANTIQUE MESURÉE

La sonde `lsr_probe_v11` (8 passes à cheval sur la frontière 03:00 UTC du
01/10/2026, 2 symboles × 3 périodes) a mesuré la sémantique d'estampillage
AVANT le commit — **verdict : sémantique END**. La ligne estampillée T
couvre la fenêtre [T−P, T) et est publiée FINALISÉE peu après T : la ligne
1h estampillée 03:00 est apparue à 03:04:44 (publication ≤ 4,7 min) avec
une valeur jamais réécrite, tandis que la ligne 02:00 est restée
strictement identique (0,5864) sur les 9 passes à cheval sur la frontière
; aucune ligne partielle n'est exposée par l'endpoint. **Correction datée
(03:15 UTC) de la première note de collecte (02:47)** qui supposait une
publication partielle en place de la fenêtre en cours — la sonde l'a
réfutée. La règle de consommation de l'étude (la barre t lit la ligne
estampillée t−P) lisait donc des fenêtres closes à t−P avec une période
entière de marge : conservative sous la sémantique mesurée, et elle était
sûre sous les deux interprétations (la mécanique d'analyse est inchangée,
la mesure ne tranche que le lag déclaratif).

La collecte applique la règle anti-partiel pré-enregistrée : toute ligne
T > now − 3P est droppée (deux périodes de refroidissement après clôture)
et la barre kline en cours est droppée (seul son open est stable, doctrine
_MK). Conséquence déclarée : les 2 dernières barres de chaque panel par
symbole n'ont pas de ligne LSR pile — **48 snap absents** (4h) comptés,
tous en queue de fenêtre (prouvé par la QA S8.4). Les klines sont du MÊME
exchange que le LSR (Bybit linear) — zéro cross-exchange dans le panel ;
le pool D croise, lui, des entrées Binance avec le LSR Bybit (limite L4,
comme les vagues 9/10).

## LES RÉSULTATS (12 symboles × ~2,74 ans = 72 000 barres 4h + 13 200 lignes 1d)

| cellule | AUC (IC 95 %) | delta médian | verdict |
|---|---|---|---|
| **A contrarian niveau** L180_H6 | 0,4920 [0,4754–0,5031] | −2,39 bps | **KILL** |
| A L180_H18 | 0,4863 [0,4685–0,5007] | −20,28 bps | **KILL** |
| A L540_H6 | 0,4915 [0,4774–0,5084] | −2,44 bps | **KILL** |
| A L540_H18 | 0,4872 [0,4678–0,5044] | −18,00 bps | **KILL** |
| **B flux** D6_H6 | 0,4919 [0,4816–0,5037] | −1,67 bps | **KILL** |
| B D6_H18 | 0,4906 [0,4784–0,5027] | −7,35 bps | **KILL** |
| B D42_H6 | 0,4824 [0,4707–0,4953] | −12,66 bps | **INCONCLU** (IC exclut 0,5, sous le gate) |
| B D42_H18 | 0,4758 [0,4605–0,4879] | −52,66 bps | **INCONCLU** (IC exclut 0,5, sous le gate) |
| **C réplication 1d** L30_H1 | 0,5054 [0,4897–0,5210] | +11,66 bps | **KILL** |
| C L30_H3 | 0,5000 [0,4816–0,5180] | +7,15 bps | **KILL** |
| C L90_H1 | 0,4983 [0,4805–0,5163] | +1,83 bps | **KILL** |
| C L90_H3 | 0,4883 [0,4705–0,5074] | −22,12 bps | **KILL** |
| **D pool P1** (n = 239/469 ; 220 hors panel, 3 hors fenêtre, 7 score NaN) | — | ΔR −0,315, P(Δ<0) = 0,8009 | **CONTEXTE** (jamais promotion) |

## LA LECTURE MÉCANIQUE

L'hypothèse contrarian NIVEAU (le cœur de la composante RI) est **KILL
4/4 sur le panel 4h et 4/4 sur la réplication 1d** : les AUC sont
0,4863–0,5054, tous les IC contiennent 0,5. Le FLUX du positionnement sur
1 jour (D6) est KILL 2/2 ; sur 7 jours (D42) les DEUX IC **excluent 0,5**
(0,4824 et 0,4758) — une trace directionnelle contrarian existe, elle est
2 à 3× sous le gate CANDIDAT 0,05 du domaine et reste donc INCONCLU ; son
delta H18 (−52,66 bps) dépasse l'étalon 12,2 bps mais un delta sans AUC
n'est pas un plan (leçon vague 7). La cohérence de DIRECTION est réelle et
documentée : **10/12 cellules panel ont un AUC < 0,5** (le sens contrarian
pré-déclaré) et le pool P1 sépare dans le MÊME sens (les entrées faites
quand la foule est longue perdent −0,315 R de médiane, P(Δ<0) = 0,8009 ≥
gate 0,70) — mais la règle du domaine est sans appel : la direction qui se
montre partout sans jamais franchir le gate d'amplitude n'est PAS un
signal. La convention de signe du gate pool des vagues 9/10 était écrite
pour un sens +1 (P(Δ>0) ≥ 0,70) ; transposée au sens −1 pré-déclaré de la
famille, elle lit P(Δ<0) ≥ 0,70 → 0,8009. **L'ambiguïté du
pré-enregistrement est assumée** (le sens du gate pool aurait dû être
gravé explicitement — leçon enregistrée pour les prochains bancs) ; le
statut reste CONTEXTE par nature (in-sample de la sélection +
cross-exchange L4), jamais promotion, la seule voie = un run A/B dédié
(docs/28) si le user le décide. Le n = 239 (vs 181 vague 9) s'explique :
le pool D consomme la dernière ligne LSR close par `searchsorted` sans
exiger l'alignement pile avec une open kline — même garantie zéro
look-ahead, prouvée par la QA S7.

**Statut : KILL du LSR contrarian niveau (4/4 + réplication 4/4), KILL du
flux 1 j, INCONCLU sous le gate pour le flux 7 j — LA 10ᵉ FALSIFICATION DU
DOMAINE** (fz, flush OI, ML, hypothèse fill maker docs/29, flux/funding,
absorption-proxy, vwap + volume profile, OI 1h, OI-régime, LSR). Le
comptage des CANDIDATS marginaux reste à 2 (vague 10, côté bas de la
purge). Le contexte pool P1 (P = 0,8009, sens contrarian) est le 3ᵉ
contraste conditionnel au-dessus du gate de contexte, NON PROMU. La QA
(49 contrôles, 0 échec) prouve la plomberie vivante : détecteur contrarian
planté sur pipeline synthétique complet (4h décolle CANDIDAT, le 1d nul du
même run ne décolle pas, le 1d planté décolle, le tout-nul ne décolle
jamais — 3 runs), zéro look-ahead par mutation multiplicative+additive des
lignes LSR ET des opens klines futures (scores passés bit à bit), contrôle
inverse (muter le passé change le futur), la ligne simultanée jamais lue
(test segmenté), les 4 branches du verdict en unitaire (KILL par
multisets identiques → AUC pile 0,5), le pool 469/469 et la règle
searchsorted, l'audit de collecte (cutoffs, grille pile, domaine (0,1),
gaps), la re-exécution bit à bit (digest c8478385f7fce150…).

## FERMÉ / NON FERMÉ

**Fermé (le LSR tous comptes Bybit, famille du signal)** : le contrarian
niveau 30 j/90 j aux horizons 24 h/72 h (panel 4h ET réplication 1d) ; le
flux du positionnement 1 j ; le contexte conditionnel documenté sans
promotion. **NON fermé (hors périmètre, pré-enregistrement requis)** : la
FORME en U du LSR (leçon vague 10 — toute extension de forme exige son
propre pré-enregistrement) ; le LSR « top traders » Binance (l'instrument
exact du filtre RI — 30 j d'historique maximum chez Binance, pas de
profondeur exploitable : la famille reste testée, pas l'instrument) ; le
LSR notionnel (buyRatio compte des COMPTES, limite L9). La liste des NON
FERMÉ data locales du domaine se réduit à : l'OI en ÉVÉNEMENT de
liquidation real-time (websocket — pas d'historique, la collecte devrait
démarrer des semaines avant tout banc). Re-test interdit sans
pré-enregistrement explicite d'une hypothèse nouvelle.

## LES LIMITES (pré-enregistrées dans l'en-tête de l'étude)

L1 le LSR Bybit account-ratio est la fraction de COMPTES longs (1 compte =
1 voix, indépendamment de la taille), pas un ratio notionnel ni le « top
traders » Binance du filtre RI — le banc teste la FAMILLE sur la seule
source profonde gratuite ; L2 publication finalisée peu après T (sonde v11
: sémantique END, δ ≤ ~4,7 min mesuré au 1h) — en backtest la ligne
[t−2P, t−P) est lue à l'open t (une période entière de marge,
conservative), le délai live exact sera mesuré par le papier v11 ; L3 la
sémantique d'estampillage est TRANCHÉE par la sonde (END) — la règle de
consommation était sûre sous les deux cas, la mesure ne change que le lag
déclaratif ; L4 le
pool D croise des entrées Binance avec le LSR Bybit (arbitrage à la
seconde, CONTEXTE par nature) ; L5 horizons en barres, doctrine _MK ; L6
la dichotomie médiane mesure la séparation HAUT/BAS, pas la forme — la
forme en U du LSR n'est pas testée ici ; L7 le z-score est relatif à la
fenêtre kline (~2,74 ans), pas séculaire ; L8 panel 1d : le bootstrap par
journées = par barres (1 barre/jour), l'IC ne corrige aucune
autocorrélation ; L9 une foule de petits comptes longs et un seul gros
short donnent un LSR long — la leçon des squeezes, le signal est testé
tel quel.

## REPRODUCTION

```bash
python3 scripts/studies/x501_openmarket/x501_collect_lsr_v11.py   # collecte (Bybit public, 0 clé)
X501_LSR_DIR=data/x501_lsr python3 scripts/studies/x501_openmarket/x501_lsr_local.py
X501_LSR_DIR=data/x501_lsr python3 scripts/studies/x501_openmarket/qa_lsr_local_x501.py
python3 scripts/studies/x501_openmarket/x501_lsr_probe_v11.py     # (optionnel) re-mesure de la sémantique
```

Preuve de la sonde : `lsr_probe_v11.jsonl` (les passes horodatées, 48
lignes par passe — la valeur de la ligne 02:00 y est constante, la ligne
03:00 y apparaît à la passe de 03:04:44).

JSON versionné : `lsr_local.json` (digest SHA-256 gravé, re-exécution bit
à bit prouvée par la QA R/S9). La re-collecte n'est pas bit-compatible
(data live) : la reproductibilité porte sur l'ÉTUDE à data fixée.
