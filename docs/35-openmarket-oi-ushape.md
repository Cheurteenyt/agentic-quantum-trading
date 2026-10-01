# docs/35 — Le banc de la FORME EN U de H_R1 (vague 10)

> **Statut : le U joint NON ÉTABLI au critère du domaine — MAIS le côté bas
> de la purge franchit le gate : les 2 premiers CANDIDATS marginaux du
> domaine (10 vagues), et le 2ᵉ contexte du pool au-dessus du gate.**
> La case explicitement laissée ouverte par la vague 9 (`docs/34`, limite
> L8 : « la dichotomie médiane ne capte que le monotone — une extension
> exigerait un pré-enregistrement ») passe au banc avec son pré-enregistrement
> propre. La vague 10 n'ajoute PAS de falsification au comptage (il reste 9) :
> elle ouvre le chapitre des candidats.

## 1. LA QUESTION

La vague 9 a refusé H_R1 **monotone** (capital haut → grands mouvements :
3 KILL + 1 INCONCLU) et fermé la direction (4/4 KILL). Mais son critère
(dichotomie médiane du score signé + AUC Mann-Whitney) était
**structurellement aveugle à une forme non monotone** — gravé L8. La
formulation concurrente, pré-enregistrée ICI avant toute mesure : la
volatilité est maximale aux **DEUX EXTRÊMES** du régime (capital très haut →
cascades de liquidations ; capital très bas → re-pricing volatil post-purge,
compression d'OI), le centre (régime normal) est calme — la **forme en U**.
La discrimination est totale avec la vague 9 :

- **vague 9** : le niveau z_L(OI) testé MONOTONE (score signé) → H_R1 refusée ;
- **vague 10** : la FORME — le U joint (score |z|), le côté bas seul
  (le DISCRIMINANT), le miroir directionnel (test de cohérence), le pool
  en strates |z|.

## 2. LE PRÉ-ENREGISTREMENT (gravé le 01/10/2026, avant toute mesure)

Grille pré-déclarée, **12 cellules de panel + 1 cellule de pool**, toutes
mesurées et rapportées :

- **Étude A1 — LE U (test joint des deux extrêmes)** : score =
  **|z_L(OI[t−1])|**, distance au centre — centre **pré-déclaré à 0** (le
  z-score roulant est centré sur sa fenêtre par construction, limite L3) ;
  cible = **|fwd_H|**, sens attendu **+1**. L ∈ {720, 2160} × H ∈ {24, 72}
  = **4 cellules**.
- **Étude A2 — LE CÔTÉ BAS SEUL (le discriminant)** : sous-échantillon
  **z_L(OI[t−1]) < 0** (score signé), cible = **|fwd_H|**, sens attendu
  **−1** : le U prédit que les z TRÈS négatifs ont |fwd| GRAND (AUC < 0,5) ;
  le monotone H_R1 prédit l'OPPOSÉ. **4 cellules.**
- **Étude B — MIROIR DIRECTIONNEL** : score = |z_L|, cible = fwd_H **signé**,
  sens = **0** — toute séparation = CONTEXTE par définition. **4 cellules.**
- **Étude C — POOL P1 en strates |z|** : les 469 entrées certifiées,
  score = |z_720(OI)| au t_in, strates pré-déclarées : EXTRÊMES = |z| ≥
  quantile 80 % du pool, CENTRE = le reste ; bootstrap diff de médianes
  10 000. Hypothèse U : ΔR > 0. L figé à 720. **1 cellule, CONTEXTE.**

**COMPOSITION DU VERDICT U (pré-déclarée — une LECTURE, jamais un
remplacement)** : U VIVANT ⇔ A1 CANDIDAT (+1) **ET** A2 CANDIDAT (−1) sur la
MÊME cellule (les deux branches exigées — l'une seule est compatible avec un
monotone asymétrique) ; KILL-U si A2 sort AUC > 0,5 HORS de l'IC (le côté
bas va dans le sens monotone : contradiction frontale) ; sinon NON ÉTABLI.

Verdict mécanique par cellule : critère du domaine **inchangé** (KILL si IC
95 % bootstrap 1 000 journées UTC seed 501 contient 0,5 et |AUC−0,5| < 0,02 ;
CANDIDAT si l'IC exclut 0,5 ET |AUC−0,5| ≥ 0,05 ET le sens confirme ;
CONTEXTE sinon ; sens = 0 ne produit jamais CANDIDAT).

## 3. LA COLLECTE (inchangée)

Le collecteur versionné de la vague 8 (`x501_collect_oi_v8.py`, Bybit v5
public, 0 €, 0 clé) fournit les mêmes JSONL : **12 symboles om_v27 × 18 000
klines 1h + OI 1h** = 216 000 barres × 749 j, 0 doublon, 0 gap, **0 snapshot
absent** dans la fenêtre (1 artefact OI = 0 pré-listing hors banc, note QA
vagues 8/9/10). Convention temps stricte transposée bit à bit : le snapshot
hh:00 marque l'OUVERTURE de sa fenêtre, à l'open de t le dernier snapshot
connu est (t−1):00 — le simultané n'est JAMAIS lu, existence PILE exigée,
0 fill-forward. Le z-score roulant (L ≤ 2160 h) reste strictement dans la
fenêtre kline.

## 4. LES RÉSULTATS

Invalidées L=720 : **8 628 barres** d'amorçage (12 × 719, comptabilité
pré-déclarée), **0** fenêtre plate (std → 0).

**Étude A1 — LE U JOINT (|z| → |fwd|, sens +1) : 4/4 INCONCLU** — l'IC
exclut 0,5 sur les QUATRE cellules (une séparation existe) mais toutes
restent sous le gate CANDIDAT 0,05 :

| Cellule | AUC | IC 95 % | Δ\|fwd\| (bps) | n | Verdict |
|---|---|---|---|---|---|
| L720_H24 | 0,5221 | [0,5093 ; 0,5311] | +20,39 | 207 072 | INCONCLU |
| L720_H72 | 0,5149 | [0,5024 ; 0,5259] | +23,61 | 206 496 | INCONCLU |
| L2160_H24 | 0,5350 | [0,5240 ; 0,5498] | +33,00 | 189 792 | INCONCLU |
| L2160_H72 | 0,5268 | [0,5167 ; 0,5483] | +44,53 | 189 216 | INCONCLU |

**Étude A2 — LE CÔTÉ BAS SEUL (le discriminant, sens −1 attendu) : 2 KILL à
L720, et 2 CANDIDAT à L2160 — les PREMIERS CANDIDATS marginaux du domaine.**

| Cellule | AUC | IC 95 % | Δ\|fwd\| (bps) | n | Verdict |
|---|---|---|---|---|---|
| L720_H24 | 0,4846 | [0,4717 ; 0,5022] | −13,99 | 94 994 | KILL |
| L720_H72 | 0,4915 | [0,4760 ; 0,5083] | −11,98 | 94 700 | KILL |
| **L2160_H24** | **0,4415** | [0,4198 ; 0,4588] | **−52,16** | 86 813 | **CANDIDAT** |
| **L2160_H72** | **0,4454** | [0,4206 ; 0,4692] | **−82,80** | 86 681 | **CANDIDAT** |

À L = 90 jours : les z TRÈS négatifs (l'extrême bas de l'OI) portent un
|fwd| médian **+52 à +83 bps plus grand** que les z négatifs modérés — un
delta de magnitude **au-dessus de l'étalon 12,2 bps A/R taker** (descriptif :
un delta sans AUC n'est pas un plan, mais ici l'AUC EST au-dessus du gate).

**COMPOSITION (pré-déclarée) : 4/4 U NON ÉTABLI** — A1 est sous le gate
0,05 partout ; la séparation de magnitude vient du côté bas SEUL. La forme
n'est PAS un U symétrique : le côté haut est faible (H_R1 refusée vague 9 :
AUC 0,5028–0,5150), le côté bas est fort. C'est un **régime de purge
unilatéral**.

**Étude B — MIROIR DIRECTIONNEL (sens = 0) : 4/4 KILL** — AUC 0,4954 /
0,4870 / 0,4909 / 0,4831, tous les IC contiennent 0,5, deltas −5,19 à
−27,63 bps. Cohérent avec les vagues 8/9 : le régime ne finance pas une
direction, pas même l'extrême bas.

**Étude C — pool P1 en strates |z| (CONTEXTE, in-sample + cross-exchange,
jamais promotion) : le DEUXIÈME contexte au-dessus du gate P ≥ 0,70.**

| Mesure | Valeur |
|---|---|
| n | 181 (283 hors panel 12) |
| quantile 80 % de \|z_720\| | 1,6146 |
| strates | 37 extrêmes / 144 centre |
| R médian extrêmes vs centre | **+0,645 vs −0,289** |
| ΔR médian | **+0,934** |
| R moyen extrêmes vs centre | +0,383 vs +0,196 |
| WR extrêmes vs centre | 54,1 % vs 47,2 % |
| IC 95 % du ΔR | [−1,025 ; +1,444] |
| **P(ΔR > 0)** | **0,7381** |

## 5. LA LECTURE

1. **Le U joint n'est PAS établi** au critère du domaine (4/4 INCONCLU :
   l'IC exclut 0,5 partout mais 1,5–3,5 pts d'AUC, tous sous le gate 0,05).
   La composition pré-déclarée le refuse — la même règle qui a servi à
   fermer les 9 falsifications refuse un U dilué.
2. **Le côté bas de la purge franchit le gate à L = 90 jours** — AUC
   0,4415/0,4454 (5,5 pts SOUS 0,5, IC excluant franchement 0,5, sens −1
   confirmé). C'est le **premier CANDIDAT marginal du domaine en 10
   vagues**. La cohérence théorique est exactement celle du registre : la
   falsification n°2 (flush OI) était tuée en **direction** ; ici on mesure
   la **magnitude post-purge** — l'extrême bas de l'OI prédit l'AMPLITUDE
   des mouvements, jamais leur sens (étude B : 4/4 KILL).
3. **L'asymétrie est la découverte** : côté haut faible (vague 9 : AUC
   0,5028–0,5150), côté bas fort (vague 10 : AUC 0,4415–0,4454). La théorie
   du levier « capital haut = cascades » est refusée DEUX fois (vagues 9
   et 10) ; la théorie de la purge « capital très bas = re-pricing volatil »
   survit au discriminant. Le chapitre des candidats s'ouvre sur un régime
   de purge, pas sur un régime de euphorie.
4. **Le conditionnel existe des DEUX côtés de la grille |z|** : le split
   médian OI-haut (vague 9, P = 0,8192) et les extrêmes |z| (vague 10,
   P = 0,7381) franchissent tous deux le gate de contexte. Garde-fous
   inchangés et pré-déclarés : **in-sample** (le pool est déjà une
   sélection), **cross-exchange** (entrées Binance × OI Bybit), n_extr = 37
   avec IC [−1,03 ; +1,44] contenant largement 0.
5. **Ce que ça AUTORISE** : deux candidats entrent dans la liste du
   protocole A/B (`docs/28`) — « régime OI-bas extrême » (magnitude, L2160)
   et « régime |z| extrême » (contexte pool) — SANS toucher à la
   priorisation pré-enregistrée de la file (RI → MK6 → TRAIL → ABS). Tout
   run futur se construit en kScript à filtre figé, uniquement si le user
   le passe dans la file. **Ce que ça N'AUTORISE PAS** : toute promotion
   des chiffres A2/C (CANDIDAT ≠ edge ; le gate AUC n'est pas une
   espérance de PnL), toute modification de grille ou de seuils, tout
   re-test sans pré-enregistrement (`docs/26`).

## 6. FERMÉ / NON FERMÉ

- **NON ÉTABLI au critère** : le U joint de la magnitude (4/4 INCONCLU sous
  le gate 0,05) — la composition pré-déclarée le refuse ; le comptage des
  falsifications RESTE à 9.
- **FERMÉ (re-confirmation)** : le miroir directionnel du régime (4/4
  KILL) — la famille directionnelle des positionnements reste close
  (vagues 8/9/10).
- **CANDIDATS (jamais promotion)** : le côté bas à L2160 (AUC 0,4415 /
  0,4454 — premiers candidats marginaux du domaine) et le contexte pool
  strates |z| (P = 0,7381 — deuxième contexte au-dessus du gate). La voie
  est le protocole A/B, jamais un banc.
- **NON FERMÉ (hors périmètre)** : l'OI en ÉVÉNEMENT de liquidation
  real-time (websocket, autre mécanique) ; le LSR 4 h (8 j de data) ; un
  centre de U décalé ≠ 0 (limite L3 — exigerait un pré-enregistrement
  propre) ; les strates quintiles strictes Q1∪Q5 (limite L4 — la
  dichotomie médiane de |z| est la mécanique standard du domaine).
- Re-test interdit sans pré-enregistrement explicite d'une hypothèse
  nouvelle (règle `docs/26`).

## 7. LES LIMITES (pré-enregistrées dans l'en-tête)

L1 marginal vs conditionnel : le U peut être absent en marginal et présent
en conditionnel (leçon vague 6 à l'envers) — les DEUX sont mesurés et
rapportés, aucune promotion croisée. L2 |fwd| open→open n'est pas la
volatilité intrabar (L7 vague 9) — c'est la grandeur que le plan x501
capture (entrées à l'open, doctrine _MK). L3 le centre du U est pré-déclaré
à 0 (centre naturel du z-score) ; un centre décalé serait partiellement
manqué par |z|. L4 la dichotomie médiane de |z| met ~50 % des barres côté
« extrêmes » (pas les 40 % des quintiles) — mécanique standard inchangée.
L5 cross-exchange du pool (Binance × Bybit), CONTEXTE par nature. L6 l'OI
Bybit est le capital Bybit, pas le capital global. L7 l'IC bootstrap
rééchantillonne les journées (clusters 24 h), évaluation sur échantillon
réduit déterministe de 50 000 points. L8 horizons en barres (gaps rares,
comptés).

## 8. LA REPRODUCTION

```bash
X501_OI_DIR=<dir des {SYM}_klines.jsonl et {SYM}_oi.jsonl> \
    python3 x501_oi_ushape_local.py      # écrit oi_ushape_local.json
X501_OI_DIR=... X501_DATA_DIR=... python3 qa_oi_ushape_x501.py  # 79 contrôles
x501_collect_oi_v8.py                   # re-collecte (vague 8, inchangée)
```

La re-collecte n'est PAS bit-compatible (data live) : la reproductibilité
bit à bit porte sur l'ÉTUDE à data fixée — le digest SHA-256 du JSON
`oi_ushape_local.json` (3f9fb7781eaeb401…) est gravé dans la QA (contrôles
R1.5–R1.8) et re-vérifié à chaque exécution.

## 9. LA QA (79 contrôles, 0 échec, 1 skip déclaré)

Le DÉTECTEUR du U est vivant (magnitude plantée en U dans le forward :
A1 décolle CANDIDAT +1 ET A2 décolle CANDIDAT −1, la composition conclut
**U VIVANT**) ; le DÉTECTEUR MONOTONE est REFUSÉ par la composition
(magnitude plantée monotone strictement positive : A2 sort AUC > 0,55 dans
le sens opposé → **KILL-U** même si A1 décolle — le banc distingue les deux
formes et refuse un U inexistant, la leçon anti double-dip en plomberie) ;
le cas nul ne décolle pas (les deux cellules KILL, NON ÉTABLI) ; la
COMPOSITION en unitaires sur 7 branches ; le score |z| et la sélection A2
en cas à la main (médiane du sous-échantillon recalculée DANS le
sous-échantillon = −1,5 ; deux bugs de CAS de QA corrigés en cours : la
médiane attendue fausse, et le premier jet du cas S5.4 plantait un
MONOTONE — AUC 1,0 — au lieu d'un U) ; `rolling_z` en unitaires (noyau
hérité vague 9 : cas L=3, boucle naïve, amorçage, NaN propagé, fenêtre
plate → NaN) ; le ZÉRO LOOK-AHEAD par mutation multiplicative + additive
des snapshots futurs (les scores SIGNÉS et |z| passés restent bit à bit) et
des barres futures ; le snapshot SIMULTANÉ jamais lu par sa barre (test
segmenté) ; les 4 branches du verdict + sens = 0 ne promeut jamais ; le
pool 469/469 (convention vague 4 re-vérifiée ; P1.3 SKIP déclaré : data
Binance absente de la machine d'exécution, la vérification 469/469 tient de
la vague 9) ; l'audit de collecte ; la re-exécution bit à bit.
