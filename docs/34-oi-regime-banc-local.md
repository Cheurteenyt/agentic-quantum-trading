# docs/34 — Le banc de l'OI en CONTEXTE DE RÉGIME (vague 9)

> **Statut : FERMÉ pour le mécanisme marginal — CONTEXTE documenté pour le conditionnel.**
> La case explicitement laissée ouverte par la vague 8 (`docs/33` : « l'OI 1 j
> pré-2024 en contexte de régime ») passe au banc. La 9ᵉ falsification du
> domaine, et le premier signal conditionnel des bancs locaux qui franchit le
> gate mécanique du contexte — sans promotion possible depuis un banc.

## 1. LA QUESTION

La vague 8 a fermé le **FLUX** du capital (ΔOI% en signal directionnel de
continuation : 10/10 KILL). Elle a laissé ouverte une case : l'OI comme
**RÉGIME** — le NIVEAU du capital affiché change-t-il la *distribution* des
rendements futurs ? La théorie du levier pré-dit une asymétrie de **magnitude**
(plus de capital affiché = plus de positions à financer = cascades plus grandes
dans les deux sens) ; elle ne pré-dit **aucune direction**. La vague 9 teste
exactement cette discrimination :

- **vague 8** : le flux (ΔOI) → direction → 10/10 KILL ;
- **vague 9** : le niveau (z-score roulant) → magnitude ET direction, avec
  l'hypothèse directionnelle pré-déclarée **nulle**.

## 2. LE PRÉ-ENREGISTREMENT (gravé le 01/10/2026, avant toute mesure)

Grille pré-déclarée, toutes les cellules mesurées et rapportées :

- **Étude A — MAGNITUDE (H_R1, la seule hypothèse que la théorie pré-dit)** :
  score = z_L(OI) = (OI[t−1] − mean_L(OI)) / std_L(OI), std de population,
  fenêtre roulante strictement dans le passé ; cible = **|fwd_H|** (magnitude
  open→open, doctrine _MK). L ∈ {720, 2160} (30 j, 90 j) × H ∈ {24, 72} =
  **4 cellules**, sens attendu +1 (AUC > 0,5 si H_R1).
- **Étude B — NIVEAU, test directionnel PAR DÉFAUT** : score identique, cible =
  fwd_H **signé**, sens attendu = **0** — toute séparation éventuelle est
  CONTEXTE par définition (un delta sans hypothèse pré-déclarée n'est jamais
  une promotion, leçon vague 7). **4 cellules.**
- **Étude C — POOL P1 en contexte** : les 469 entrées certifiées rejouées avec
  z_720(OI) au t_in (snapshot ≤ t_in − 1 h), split médian du score, R haut vs
  bas, bootstrap diff de médianes 10 000. L figé à 720 (le 2160 consommerait
  ~25 % de la fenêtre kline). **1 cellule**, CONTEXTE par nature.

Verdict mécanique au critère du domaine inchangé (KILL si IC 95 % bootstrap
1 000 journées UTC seed 501 contient 0,5 et |AUC−0,5| < 0,02 ; CANDIDAT si
l'IC exclut 0,5 ET |AUC−0,5| ≥ 0,05 ET le sens confirme l'hypothèse ;
CONTEXTE si le sens s'oppose ou si sens = 0).

## 3. LA COLLECTE (inchangée)

Le collecteur versionné de la vague 8 (`x501_collect_oi_v8.py`, Bybit v5
public, 0 €, 0 clé) fournit les mêmes JSONL : **12 symboles om_v27 × 18 000
klines 1h + OI 1h** = 216 000 barres × 749 j, 0 doublon, 0 gap, **0 snapshot
absent** dans la fenêtre (1 artefact OI = 0 pré-listing hors banc, note QA
vague 8). Klines ET OI du **même exchange** — zéro cross-exchange dans le
panel. Le z-score roulant (L ≤ 2160 h) reste strictement dans la fenêtre
kline : l'OI pré-2024 n'entre dans aucune statistique du banc (limite L1).

## 4. LES RÉSULTATS

Invalidées L=720 : **8 628 barres** d'amorçage (12 × 719, exactement la
comptabilité pré-déclarée), **0** fenêtre plate (std → 0).

**Étude A — MAGNITUDE (H_R1 : capital haut → grands mouvements, AUC > 0,5
attendu) : 3 KILL / 1 INCONCLU — la théorie du levier est REFUSÉE au critère
du domaine.**

| Cellule | AUC | IC 95 % | Δ|fwd| (bps) | n | Verdict |
|---|---|---|---|---|---|
| L720_H24 | 0,5117 | [0,4987 ; 0,5243] | +11,46 | 207 072 | KILL |
| L720_H72 | 0,5150 | [0,5024 ; 0,5292] | +24,72 | 206 496 | INCONCLU |
| L2160_H24 | 0,5063 | [0,4904 ; 0,5222] | +7,29 | 189 792 | KILL |
| L2160_H72 | 0,5028 | [0,4867 ; 0,5202] | +6,80 | 189 216 | KILL |

Le seul IC qui exclut 0,5 (L720_H72, AUC 0,5150) reste **très sous** le gate
CANDIDAT (0,05) : une séparation de 1,5 pt d'AUC n'est pas un régime.

**Étude B — NIVEAU → direction (aucune hypothèse pré-déclarée, sens = 0) :
4/4 KILL** — AUC 0,5014 / 0,5130 / 0,5079 / 0,5152, tous les IC contiennent
0,5, deltas −0,20 à +20,87 bps descriptifs. Cohérent avec la vague 8 : le
flux ne finance pas une direction, le niveau non plus.

**Étude C — pool P1 (CONTEXTE, in-sample + cross-exchange, jamais
promotion) : le PREMIER contexte des bancs locaux qui franchit le gate
mécanique P ≥ 0,70.**

| Mesure | Valeur |
|---|---|
| n | 181 (283 hors panel 12) |
| split médian du z-score | 90 haut / 91 bas |
| R médian haut vs bas | **+0,087 vs −0,382** |
| ΔR médian | **+0,469** |
| WR haut vs bas | 52,2 % vs 45,1 % |
| R moyen haut vs bas | +0,406 vs +0,064 |
| IC 95 % du ΔR | [−0,903 ; +1,349] |
| **P(ΔR > 0)** | **0,8192** |

## 5. LA LECTURE

1. **Le mécanisme marginal est FERMÉ** — le niveau du capital affiché ne
   conditionne ni la magnitude (H_R1 refusée : 3 KILL + 1 INCONCLU, le seul
   IC non mort à 0,5150 est 3,3× sous le gate) ni la direction (4/4 KILL) des
   rendements open→open sur le panel. C'est la **9ᵉ falsification du domaine**
   (fz, flush OI, ML, hypothèse fill maker docs/29, flux/funding,
   absorption-proxy, vwap + VP, OI 1h, et désormais le régime OI) — et le
   **5ᵉ verdict symétrique des familles de positionnement** (flux taker,
   funding, absorption-proxy, OI-flux, OI-niveau).
2. **Le conditionnel existe dans la donnée** — sur les 181 entrées du pool P1
   du panel, le régime OI-haut au moment de l'entrée sépare +0,469 R de
   médiane avec P = 0,8192 ≥ 0,70. Trois garde-fous, pré-déclarés : c'est
   **in-sample** (le pool P1 est déjà une sélection), c'est **cross-exchange**
   (entrées Binance × OI Bybit, L4), et n = 181 avec un IC de bootstrap
   [−0,90 ; +1,35] qui contient largement 0. Le contraste avec le marginal
   (AUC ≈ 0,51 partout) est la leçon de la vague 6 à l'envers : le régime ne
   dit RIEN en marginal et se montre — éventuellement — en **interaction avec
   un événement directionnel**. C'est exactement le rôle d'un filtre de
   contexte, pas d'un signal.
3. **Ce que ce résultat AUTORISE** : la case « régime OI » entre dans la
   liste des filtres candidats au protocole A/B (`docs/28`) — SANS toucher à
   la priorisation pré-enregistrée de la file (RI → MK6 → TRAIL → ABS). Un
   run « OI-regime filter » sera construit sous forme de kScript à filtre
   figé (z_720 ≥ médiane) uniquement si le user décide de le passer dans la
   file. **Ce que ce résultat N'AUTORISE PAS** : toute promotion des chiffres
   C dans docs/25 (ils restent contexte), toute modification de la grille ou
   des seuils, et tout re-test sans pré-enregistrement (`docs/26`).

## 6. FERMÉ / NON FERMÉ

- **FERMÉ** : l'OI en régime marginal (magnitude monotone H_R1 + direction)
  au critère du domaine, panel 12 × 749 j — la 9ᵉ falsification.
- **CONTEXTE documenté, NON PROMU** : le conditionnel pool P1 (P = 0,8192) —
  in-sample + cross-exchange, à trancher uniquement par un run A/B dédié si
  le user le décide.
- **NON FERMÉ (hors périmètre)** : l'OI en ÉVÉNEMENT de liquidation
  real-time (websocket, autre mécanique) ; ~~la forme en **U** de H_R1
  (limite L8 : la dichotomie médiane ne capte que le monotone — une
  extension exigerait un pré-enregistrement)~~ **→ traitée par la vague 10
  (`docs/35`) avec son pré-enregistrement : le U joint NON ÉTABLI (4/4
  INCONCLU sous le gate 0,05), le côté bas de la purge CANDIDAT à L2160
  (premiers candidats marginaux du domaine)** ; le LSR 4 h (8 j de data).
  real-time (websocket, autre mécanique) ; la forme en **U** de H_R1
  (limite L8 : la dichotomie médiane ne capte que le monotone — une
  extension exigerait un pré-enregistrement) ; le LSR 4 h (8 j de data).
origin/main
- Re-test interdit sans pré-enregistrement explicite d'une hypothèse
  nouvelle (règle `docs/26`).

## 7. LES LIMITES (pré-enregistrées dans l'en-tête)

L1 le z-score est relatif à la fenêtre kline (749 j), pas à l'historique OI
complet (~4,5 ans) — le régime est in-fenêtre ; le niveau absolu séculaire
exigerait des klines alignées qui n'existent pas localement. L2 l'OI Bybit
est le capital Bybit, pas le capital global (limite L1 vague 8). L3 l'IC
bootstrap rééchantillonne les journées (clusters 24 h), évaluation sur
échantillon réduit déterministe de 50 000 points. L4 l'étude C croise des
entrées pool (Binance) avec l'OI Bybit — cross-exchange assumé, CONTEXTE.
L5 horizons en barres (gaps rares, comptés). L6 la dichotomie à la médiane
mesure la séparation HAUT/BAS, pas la forme monotone. L7 |fwd| n'est pas la
volatilité réalisée intrabar — c'est la grandeur que le plan x501 capture
(entrées à l'open). L8 la forme en U de H_R1 n'est pas couverte par la
dichotomie médiane (cf. § 6).

## 8. LA REPRODUCTION

```bash
X501_OI_DIR=<dir des {SYM}_klines.jsonl et {SYM}_oi.jsonl> \
    python3 x501_oi_regime_local.py      # écrit oi_regime_local.json
X501_OI_DIR=... X501_DATA_DIR=... python3 qa_oi_regime_x501.py  # 63 contrôles
x501_collect_oi_v8.py                   # re-collecte (vague 8, inchangée)
```

La re-collecte n'est PAS bit-compatible (data live) : la reproductibilité
bit à bit porte sur l'ÉTUDE à data fixée — le digest SHA-256 du JSON
`oi_regime_local.json` (bf0b77ac6a74d8be…) est gravé dans la QA
(contrôles R1.5–R1.8) et re-vérifié à chaque exécution.

## 9. LA QA (63 contrôles, 0 échec, 0 skip)

Le DÉTECTEUR vivant sur pipeline synthétique complet (niveau d'OI planté
monotone dans la magnitude du forward, décalage d'une barre de la vague 8 :
AUC > 0,55 CANDIDAT sur l'étude A ; la même plomberie décolle sur le signé
pour l'étude B, verdict CONTEXTE forcé par sens = 0) ; le cas nul reste KILL
(pas de batterie triviale) ; le ZÉRO LOOK-AHEAD par mutation multiplicative +
additive des snapshots futurs ET des barres futures (les scores passés
restent bit à bit, deux mutations — leçon vague 7) ; le snapshot SIMULTANÉ
jamais lu par sa propre barre (muté : passé et barre simultanée inchangés,
fenêtres postérieures changent — le test n'est pas vide) ; `rolling_z` en
unitaires (cas à la main L=3, amorçage, contre-vérification boucle naïve,
snapshot NaN propagé) ; le cas dégénéré fenêtre plate → NaN (bug réel
corrigé pendant l'écriture : les erreurs float de var = s2/L − m² produisaient
±inf, seuil relatif 1e-6 gravé) ; les 4 branches du verdict + sens = 0 ne
promeut jamais ; le pool 469/469 (entry = open × (1 + side × 2 bps),
convention vague 4) ; l'audit de collecte ; la re-exécution bit à bit.
