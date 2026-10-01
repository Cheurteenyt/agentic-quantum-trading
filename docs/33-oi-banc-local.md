# 33 · OPENMARKET x501 — LE BANC DE TEST LOCAL DE L'OPEN INTEREST 1h

> Créé le 01/10/2026 (vague 8). La matière première désignée par `docs/26`
> (« l'entrepôt reste la matière première des prochains bancs, **OI 1h en
> tête** ») passe au banc AVANT tout usage. Étude :
> `scripts/studies/x501_openmarket/x501_oi_local.py` + QA
> `qa_oi_local_x501.py` (47 contrôles, 0 échec). Docs frères : 30
> (flux/funding), 31 (absorption-proxy), 32 (vwap + volume profile).

## LA QUESTION

L'open interest 1h — le capital total affiché sur le perp — porte-t-il une
information directionnelle exploitable à nos horizons (24 h / 72 h) ? Le
domaine ne l'a testé qu'une fois, en ÉVÉNEMENT CONTRARIEN : le gate
« flush OI » (ΔOI 6h ≤ −4,5 %, `docs/25` falsification n°2) — +0,1/+0,2 bps
dédupliqué, KILL. L'hypothèse INVERSE — l'OI comme TÉMOIN DE CONTINUATION
(le capital qui finance la tendance) — n'avait JAMAIS été mesurée.
`docs/26` l'exige : « tout re-test exige un pré-enregistrement explicite
d'une hypothèse nouvelle au registre, pas un re-run de curiosité » — c'est
exactement ce fichier.

## LE PRÉ-ENREGISTREMENT (gravé dans l'en-tête de l'étude AVANT toute mesure)

La grille (10 cellules de panel + 1 de pool, TOUTES rapportées) :

- **Étude A — capital brut** : score = ΔOI%_L = 100 × (OI[t−1] / OI[t−1−L] − 1),
  L ∈ {24, 72, 168} barres 1h, H ∈ {24, 72} (open→open, doctrine _MK),
  dichotomie à la médiane (convention vague 5). **H_OI1** : l'expansion du
  capital annonce la HAUSSE (AUC > 0,5 attendu).
- **Étude B — mouvement financé (quadrant OI × prix)** : score =
  signe(r_L) × ΔOI%_L avec r_L = close[t−1]/close[t−1−L] − 1 — positif quand
  le mouvement récent est financé dans son sens (OI↑ avec prix↑, OI↓ avec
  prix↓), négatif quand il ne l'est pas. Cible ALIGNÉE : fwd × signe(r_L).
  L ∈ {24, 72} × H ∈ {24, 72}. **H_OI2** : le mouvement financé CONTINUE
  (AUC > 0,5 attendu) — l'hypothèse raffinée du quadrant, la seule que la
  théorie du levier distingue.
- **Étude C — pool P1** : ΔOI%_24h au t_in (snapshot ≤ t_in − 1h), split
  médian, R haut vs bas — CONTEXTE par nature (in-sample de la sélection +
  cross-exchange L2), jamais promotion.

La convention temps stricte (transposée de la correction v27, `docs/26`) :
le timestamp d'un snapshot OI marque l'OUVERTURE de sa fenêtre horaire (état
mesuré à hh:00). À l'open de la barre T, le dernier snapshot CONNU est celui
de (T−1):00 — le snapshot T:00 paraît SIMULTANÉMENT à l'open et n'est JAMAIS
lu. Existence PILE des snapshots exigée (aucun fill-forward silencieux :
une absence invalide la décision) — résultat : **0 snapshot absent** sur la
fenêtre d'étude.

Le critère du domaine (inchangé, vagues 5-7) : AUC Mann-Whitney, IC 95 %
bootstrap 1 000 journées UTC seed 501, réduction 50 000 — KILL si l'IC
contient 0,5 ET |AUC−0,5| < 0,02 ; CANDIDAT si l'IC EXCLUT 0,5 ET
|AUC−0,5| ≥ 0,05 ET le sens confirme l'hypothèse pré-déclarée ; CONTEXTE si
le sens s'y oppose ; INCONCLU sinon.

Le panel : les **12 symboles om_v27** (manifeste `docs/26`, liste v17 reprise
à l'identique) — BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, SUI, APT,
1000PEPE (USDT). Klines 1h ET OI 1h du MÊME exchange (Bybit v5, catégorie
linear) : la sémantique d'exécution du domaine (Bybit VIP0, `docs/25`),
zéro cross-exchange dans le panel.

## LA COLLECTE (gratuite, versionnée, re-exécutable)

`x501_collect_oi_v8.py` — Bybit v5 public (0 €, 0 clé, 0 secret) : klines 1h
(endpoint `/v5/market/kline`, interval=60, limit=1000, pagination par `end`
décroissant) + OI 1h (endpoint `/v5/market/open-interest`, intervalTime=1h,
limit=200, pagination par `cursor` — le paramètre `end` est IGNORÉ par cet
endpoint, mesuré le 01/10/2026). 12 symboles × 18 000 klines + 29 915 à
40 000 snapshots OI (cap collecteur 40 000 points = ~4,5 ans sur les
majeures ; la profondeur réelle Bybit est supérieure, le cap suffit
largement à la fenêtre d'étude). Audit : **216 000 barres, 0 doublon, 0 gap,
0 snapshot absent** sur la fenêtre d'étude (749 jours, 11/09/2024 →
01/10/2026). Un artefact de collecte, HORS banc : APTUSDT OI = 0.0 le
18/10/2022 (pré-listing, hors fenêtre, rapporté par la QA en note).

## LES RÉSULTATS (10/10 KILL)

| cellule (12 symboles × 749 j = 216 000 barres, 0 gap, 0 snapshot absent) | AUC | IC 95 % | delta médian | verdict |
|---|---|---|---|---|
| A capital brut L24 × H24 / H72 | 0,4952 / 0,4917 | contiennent 0,5 | −6,7 / −19,7 bps | **KILL ×2** |
| A capital brut L72 × H24 / H72 | 0,4921 / 0,5006 | contiennent 0,5 | −6,5 / +5,7 bps | **KILL ×2** |
| A capital brut L168 × H24 / H72 | 0,4933 / 0,4990 | contiennent 0,5 | −8,7 / −6,1 bps | **KILL ×2** |
| B mouvement financé L24 × H24 / H72 | 0,4960 / 0,4957 | contiennent 0,5 | −3,9 / −9,5 bps | **KILL ×2** |
| B mouvement financé L72 × H24 / H72 | 0,4936 / 0,5019 | contiennent 0,5 | −3,6 / +9,2 bps | **KILL ×2** |
| C pool P1 ΔOI% 24h (186/469 entrées, CONTEXTE) | — | IC delta [−1,02, +1,23] | +0,281 R, P = 0,660 | **INCONCLU** (< gate 0,70) |

La fenêtre complète : 11/09/2024 → 01/10/2026, 288 décisions d'amorçage
(les 24 premières barres de chaque symbole, ΔOI 24 h non défini) — aucune
décision invalidée par absence de données.

## LA LECTURE MÉCANIQUE

Aucune des deux hypothèses ne surnage : le capital affiché ne prédit PAS la
direction, ni brut (H_OI1), ni conditionné au quadrant prix (H_OI2). Les
deltas médianes (−19,7 à +9,2 bps) sont descriptifs et restent sous l'étalon
12,2 bps aller-retour taker — un delta sans AUC n'est pas un plan (leçon
vague 7 répétée). Le verdict est SYMÉTRIQUE des falsifications précédentes
de positionnement : le flux taker (vague 5), le funding (vague 5),
l'absorption-proxy (vague 6), et désormais l'OI (vague 8) ferment la même
porte — sur perps USDT 1h, les témoins de positionnement ne portent pas
d'edge directionnel exploitable à nos horizons de détention.

La précision du banc (ce qui fait la valeur du KILL) : la QA (47 contrôles,
0 échec) prouve la plomberie VIVANTE — le détecteur : un OI planté corrélé
au forward futur fait DÉCOLLER l'AUC (0,66 mesuré, verdict CANDIDAT), le cas
nul reste KILL (pas de batterie triviale) ; le ZÉRO LOOK-AHEAD est prouvé
par MUTATION des snapshots futurs — multiplicative ET additive — les scores
passés restent bit à bit ; la RE-EXÉCUTION BIT À BIT de l'étude complète
(digest SHA-256 b4b55400b05a69d1…) ; le pool P1 re-vérifié 469/469
(entry = open × (1 + side × 2 bps), convention vague 4).

## FERMÉ / NON FERMÉ

- **FERMÉ** : l'OI 1h en signal continu (capital brut) et en quadrant
  (mouvement financé) au critère du domaine, sur le panel 12 × 749 j — la
  **8ᵉ falsification du domaine** (fz, flush OI, ML, hypothèse fill maker
  docs/29, flux/funding, absorption-proxy, vwap + volume profile, et
  désormais OI 1h).
- **NON FERMÉ (hors périmètre de ce banc)** : l'OI en ÉVÉNEMENT de
  liquidation real-time (le flux websocket des liquidations — autre
  mécanique, autre data, non couvert) ; ~~l'OI 1 j pré-2024 en contexte de
  régime~~ → **FERMÉ par la vague 9 (`docs/34`)** : le niveau (z-score
  roulant) ne conditionne ni la magnitude ni la direction — 9ᵉ
  falsification ; le LSR 4 h (8 jours de data,
  mécanique, autre data, non couvert) ; l'OI 1 j pré-2024 en contexte de
  régime (statut `docs/26` inchangé) ; le LSR 4 h (8 jours de data,
origin/main
  « collecté pour plus tard », statut inchangé).
- Re-test interdit sans pré-enregistrement explicite d'une hypothèse
  nouvelle (règle `docs/26`).

## LIMITES (pré-enregistrées dans l'en-tête)

L1 l'OI Bybit est le capital Bybit, pas le capital global cross-exchange —
le banc mesure le MÉCANISME, pas le marché total. L2 l'étude C croise des
entrées pool (data Binance, vague 4) avec l'OI Bybit — cross-exchange
assumé (arbitrage à la seconde), CONTEXTE par nature. L3 l'IC bootstrap
rééchantillonne les journées (clusters 24 h) et évalue l'AUC sur un
échantillon réduit déterministe de 50 000 points (l'AUC ponctuelle est
full-sample). L4 l'étude C n'est évaluable que sur les symboles du panel 12
(186/469 entrées, le reste rapporté hors panel). L5 les horizons sont en
barres, pas en heures calendaires (gaps rares, comptés). L6 la dichotomie à
la médiane mesure la séparation HAUT/BAS, pas la forme monotone de la
relation.

## LA REPRODUCTION

```bash
X501_OI_DIR=<dir des {SYM}_klines.jsonl et {SYM}_oi.jsonl> \
    python3 x501_oi_local.py          # écrit oi_local.json (déterministe)
X501_OI_DIR=... X501_DATA_DIR=... python3 qa_oi_local_x501.py   # 47 contrôles
python3 x501_collect_oi_v8.py      # re-collecte (X501_OI_OUT)
```

La re-collecte n'est PAS bit-compatible (data live) : la reproductibilité
bit à bit porte sur l'ÉTUDE à data fixée — le digest du JSON `oi_local.json`
est gravé dans la QA (contrôles R1.5-R1.8) et re-vérifié à chaque exécution.
Sortie : `oi_local.json` versionné, déterministe, digest interne.
