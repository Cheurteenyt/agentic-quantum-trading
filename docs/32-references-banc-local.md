# 32 · LE BANC DES RÉFÉRENCES DE LIQUIDITÉ — VWAP ET VOLUME PROFILE, LA 6ᵉ FALSIFICATION

> Créé le 01/10/2026 (vague 7). Étude : `scripts/studies/x501_openmarket/x501_refs_local.py`
> — QA : `qa_refs_local_x501.py` (39 contrôles, re-exécution bit à bit, digest
> `6af839e09c6136e8…`). Pré-enregistrement intégral dans l'en-tête du script,
> écrit AVANT toute mesure.

## LA QUESTION

Il restait, après les vagues 5 (filtres continus de flux) et 6 (structure
événementielle de l'absorption), **deux pouvoirs d'analyse réels jamais
mesurés** dans le registre `docs/27` : `vwap` et `volume profile` (famille
analyse, 3/5). Ce sont exactement les briques que TradingView facture et que
tout manuel d'exécution institutionnelle cite : le VWAP ancré session (« le
benchmark ») et le profil de volume journalier (VPOC, VAH, VAL — la « value
area »). Le domaine openmarket les a toujours ignorés (0 script). La vague 7
les passe au banc local AVANT tout run plateforme — la même économie que les
vagues 5-6 : des CPU-minutes au lieu des backtests du user.

**Ce qui n'est PAS banc-testé ici, et pourquoi (pré-déclaré)** : `ltf()` (TF
inférieur) et `minBidAmount/minAskAmount` (L1 du carnet) n'ont **aucune data
locale équivalente** — aucune falsification n'est possible, ils restent
documentés comme tels dans `docs/27`. Le langage (collections, loops, types,
streams, panes, libraries) et la visu (`plot/label`) restent de la dette de
style, sans edge (décision vague 1). `strategy.exit profit=/loss=` reste
refusé par design (docs/28), `ethena_positions` sans use case.

## LA DISCIPLINE (pré-enregistrée, l'essentiel)

- **Convention temps stricte** (vagues 5-6) : décision à l'open de T, barres
  ≤ T−1 seulement (open(T) lui-même est le prix d'entrée) ; rendement forward
  = open(T+H) − open(T), signé par la direction, H ∈ {24, 72}.
- **VWAP de session** : ancré 00h UTC, tp = (h+l+c)/3, pondération
  quote_volume, reset journalier — évalué à T−1, donc causal.
- **Volume profile de la veille** : le jour D−1 COMPLET (où D = journée de T)
  — chaque barre 1h répartit son quote_volume uniformément sur [low, high],
  48 bins ; VPOC = bin de volume max (ex-aequo → le plus bas) ; value area =
  expansion gourmande (ex-aequo → le dessous) jusqu'à ≥ 70 % ; VAH/VAL = les
  bords. Limite L1 assumée : l'allocation 1h est une OMBRE du profil fin —
  le banc teste l'INFORMATION du niveau, pas sa précision.
- **La grille : 28 cellules** — V1 aimant vwap (mean-reversion, seuils
  0/0,5 %/1 % × 2 directions × 2 horizons = 12) ; V2 cross vwap
  (continuation, 4) ; P1 aimant VPOC (4) ; P2 rejet de la value area (4) ;
  P3 breakout de la value area (4). **P2 et P3 conditionnent les MÊMES
  événements avec des attentes OPPOSÉES** — le litige mean-reversion vs
  breakout est tranché par la donnée, pas par le goût.
- **Robustesses pré-déclarées** : la même grille sur le panel LIQUIDE8
  (BTC, ETH, BNB, SOL, XRP, DOGE, ADA, LINK) ; focus BTC/ETH sur les
  cellules cœur ; AUC par symbole (anti-dilution).
- **Critère du domaine (inchangé)** : AUC Mann-Whitney flag vs complément,
  IC 95 % bootstrap 1 000 par journées UTC seed 501 (réduction 50 k) ;
  KILL si l'IC contient 0,5 et |AUC−0,5| < 0,02 ; CANDIDAT si l'IC exclut
  0,5, |AUC−0,5| ≥ 0,05 et sens confirmé ; sinon INCONCLU. Règle d'ex-aequo
  (vague 6) : ≥ 50 % de zéros dans le sous-ensemble flaggé =
  NON_INTERPRETABLE.
- **Pool P1 en CONTEXTE** (jamais un argument de promotion) : F1 « payer le
  prix étendu » (entrée du mauvais côté du vwap de session) et F2 hors value
  area de la veille ; flags évalués sur open(T) (doctrine _MK) — la colonne
  `entry` du pool vaut open×(1 + side×2 bps), l'entrée 2 bps adverse
  (convention vague 4, re-vérifiée 469/469 par la QA).

## LES RÉSULTATS (80 symboles × 1 092 j = 2 048 055 décisions, 288 s)

**Bilan mécanique : 55 KILL / 1 INCONCLU / 0 CANDIDAT** sur les 56 cellules
(28 pool + 28 liquide8). L'AUC médiane des deux panels vaut **0,504** ; les
extrêmes vont de 0,4851 (P3 SHORT H24, liquide8) à 0,5136 (P2 LONG H72,
pool). **Aucune famille ne surnage, aucun symbole ne surnage** (max par
symbole ≈ 0,528, isolé et non confirmé).

| Famille | Cellules (pool) | Verdict | Ce que dit la donnée |
|---|---|---|---|
| V1 aimant vwap (mean-reversion) | 12 | **12 KILL** (+1 INCONCLU liquide8 sur s=1 % LONG H24, IC [0,50001 ; 0,5297], \|AUC−0,5\| = 0,013 < 0,05) | les deltas vont de +1,3 à +24,4 bps mais tous les IC contiennent 0,5 — le « benchmark institutionnel » ne ramène rien de mesurable à H24/H72 |
| V2 cross vwap (continuation) | 4 | **4 KILL** | deltas −8,6 à +10,2 bps, dans le bruit |
| P1 aimant VPOC | 4 | **4 KILL** | deltas +19,9/+20,1 bps SANS séparation de rangs (AUC ≈ 0,504) : la queue, pas le signal |
| P2 rejet value area | 4 | **4 KILL** | le meilleur delta du banc (+44,4 bps H72 LONG) reste KILL (AUC 0,5136, IC contient 0,5) — la queue encore |
| P3 breakout value area | 4 | **4 KILL** | le miroir EXACT de P2 (−44,4 bps H72 SHORT) : mêmes événements, attente opposée, même verdict — le litige est tranché : NI rejet NI continuation |

**La leçon structurelle** : le delta médian de P2 (+44,4 bps à H72) est
exactement le miroir de P3 (−44,4 bps) — c'est la preuve interne que la
grille est honnête ; mais l'AUC reste ~0,51 : le delta vient de la queue des
distributions (les événements « sous la VAL » contiennent les krachs qui
rebondissent fort ET ceux qui ne rebondissent jamais), pas d'une séparation
de rangs exploitable. Un delta médian flatteux sans séparation de rangs, la
leçon est la même que la vague 4 (les fallbacks) : **la queue n'est pas un
plan**.

**Pool P1 (469 entrées, opens 469/469, 0 référence manquante)** :

| Filtre | n_flag / n_comp | ΔR médian | P(boot) | Verdict |
|---|---|---|---|---|
| F1 mauvais côté vwap | 343 / 126 | **−0,581 R** | 0,42 | INCONCLU (sous le gate) |
| F2 hors value area | 116 / 353 | +0,148 R | 0,52 | INCONCLU |

F1 est le chiffre le plus « tentant » du banc : les entrées du mauvais côté
du vwap de session ont une médiane −0,321 R contre +0,260 R pour les autres.
Le bootstrap le dit non signé (P = 0,42), l'échantillon est in-sample, le
gate de promotion (docs/28 : P ≥ 0,70 ET Δ ≥ +0,10 R ET N_MIN) est loin.
**La règle gravée s'applique : jamais de promotion in-sample, le juge reste
le protocole A/B.** Si un jour ce filtre devait être testé pour de vrai, il
passerait par un run pré-enregistré, pas par ce tableau.

## CE QUE ÇA FERME — ET CE QUE ÇA NE FERME PAS

**Fermé (la 7ᵉ falsification du domaine)** : vwap et volume profile, aux
deux hypothèses (mean-reversion ET continuation), sur le pool entier ET sur
les liquides, avec la plomberie prouvée vivante par la QA (le détecteur voit
une aimantation plantée à AUC 0,911 et une continuation plantée à AUC 0,929 ;
le zéro look-ahead est prouvé par mutation, y compris la tentation la plus
subtile : le profil de la journée EN COURS n'entre jamais dans la décision —
la veille seule). Le registre d'exploitation `docs/27` est désormais **clos
pour toute la famille analyse** : chaque pouvoir y est exploité, mesuré et
fermé, refusé par design, sans data locale, ou de la dette de style.

**Le bilan complet des falsifications du domaine x501** :
1. fz (−22,0 bps, KILL) ; 2. flush OI (+0,1/+0,2 bps, KILL) ;
3. ML 11 features (AUC 0,4994 < 0,60) ; 4. l'hypothèse d'entrée maker de la
MC v20 (le fill réel +0,375 bps contre 4,0 crédités — `docs/29`, vague 4) ;
5. flux taker + funding (12/12 cellules, vague 5) ; 6. absorption en proxy
klines (prime de structure 0/4, vague 6) ; **7. VWAP + volume profile
(55 KILL / 1 INCONCLU / 0 CANDIDAT, vague 7)**.

**Non fermé (et pourquoi)** : le champ orderbook que les klines ne voient pas
(maxBidAmount/maxAskAmount, le mur RÉEL du pattern Aster — jugé par le run
ABS du protocole A/B, en queue de file, rôle renforcé par le contraste) ;
les flux premium en tant que FILTRES DE RÉGIME (le filtre RI vague 1, dont
le juge est le run RI) ; la preuve forward (papier _MK, compteurs, protocole
v11) qui reste le juge final de tout ce qui précède.

## LA REPRODUCTION

```
cd scripts/studies/x501_openmarket
python3 x501_refs_local.py          # ~5 min, écrit refs_local.json
python3 qa_refs_local_x501.py       # 39 contrôles + re-exécution bit à bit
```

Déterminisme : seed 501, aucune source d'aléa hors les bootstraps seedés ;
le digest SHA-256 du JSON (hors `duree_s`) est `6af839e09c6136e8…` — une
re-exécution sur la même data doit le retrouver à l'octet près.
