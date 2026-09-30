# 29 — Fill maker mesuré : la chaîne de preuve complète (hypothèse → mesure → surveillance)

> Statut : **NIVEAU EXÉCUTION** — cette note ferme le maillon faible n°1 de la MC v20.
> Les chiffres officiels du domaine restent **v20** tant que la review n'a pas validé
> le candidat v21 décrit ici (§ 6). Daté du 01/10/2026, pré-enregistré avant tout
> relevé papier des compteurs `_MK`.

## 1. Pourquoi cette étude existe

La MC v20 (12 000 trajectoires, chiffres officiels : maker δ=2 → médiane 468,4 $,
taker all-in → 272,7 $, +71,8 % pour le maker) repose sur **deux hypothèses durcies
en constantes** dans son en-tête :

- **(H1)** fill 97,9 % à δ=2 bps / 95,8 % à δ=5 (52 728 tentatives, 1h/708 j) —
  le script qui a produit cette mesure n'a **jamais été versionné**, le nombre est
  incrusté sans sa méthode ;
- **(H2)** le maker est un **simple delta de coût uniforme** (4,0 bps/jambe vs taker
  all-in 6,1) : la **sélection** — qui est fillé, qui tombe en fallback taker, qui
  est invalidé — n'y est pas modélisée du tout.

Le diagnostic récurrent du domaine s'applique ici comme ailleurs : un outil
puissant gratuit (les ordres limites et la microstructure qu'on mesure avec la
data premium locale) n'a de valeur que **mesurée**. Cette étude mesure, sans rien
modifier au moteur ni au pool certifié.

## 2. Matériel et conventions (reproductibles)

- **Data** : klines 1h format Binance, 80 symboles × 733 j (01/10/2023 → 26/09/2026,
  26 208 barres chacun) — la couche 1h de l'entrepôt du domaine (docs/26).
  Chemin : `X501_DATA_DIR` (défaut `data/x501_1h` du repo).
- **Pool P1 certifié** : 469 trades (alphas A1/A3/A4, déc 2023 → sept 2026, 373
  shorts / 96 longs, dist médiane 242 bps, E[R] +0,180, WR 46,5 %). Les entrées
  sont versionnées pour l'audit : `scripts/studies/x501_openmarket/pool_P1_entrees.csv`
  (sym, t_in, side, entry, stop déduit, dist_bps, R certifié, alpha).
  Convention du pool vérifiée : `entry == open(t_in)` (123/123 BTC), le signal est
  à `t_in − 1h` — exactement la sémantique des `_MK` (limite placée à la clôture
  du signal, vivante pendant TTL barres).
- **Constantes d'exécution** (mesures v16/v17, Bybit VIP0 USDT-perp) : fee taker
  5,5 bps, fee maker 2,0 bps, demi-spread 0,6 bps, taker all-in **6,1 bps**.
  Delta d'un fill limite sans gap vs taker all-in : prix δ (2,0) + fees (3,5) +
  spread évité (0,6) = **6,1 bps** ; la MC v20 n'en crédite que 4,1 (elle ignore
  le gain de prix et le spread) — le surplus est une marge de conservatisme qui
  travaille DANS notre sens, mesurée ci-dessous.

## 3. Niveau A — la surface de fill physique δ×TTL (toutes barres, 2 053 015 tentatives)

Méthode : pour **chaque barre** de chaque symbole, un ordre limite hypothétique est
placé à la clôture (buy **sous** le prix, sell **au-dessus**), la mèche des barres
suivantes décide : toucher le niveau = fill ; gap au-delà = fill au prix
d'ouverture (favorable). P(fill) par (δ, TTL), buy | sell, en % :

| δ \ TTL | 1 | 2 | 3 | 6 | 12 |
|---|---|---|---|---|---|
| 1 | 94,6 / 94,5 | 96,3 / 96,3 | 96,8 / 96,8 | 97,2 / 97,2 | 97,5 / 97,5 |
| 2 | 94,0 / 93,8 | 96,0 / 95,9 | 96,6 / 96,5 | 97,1 / 97,1 | 97,4 / 97,4 |
| 3 | 93,1 / 92,9 | 95,6 / 95,5 | 96,3 / 96,2 | 96,9 / 96,9 | 97,3 / 97,3 |
| 5 | 91,2 / 90,8 | 94,6 / 94,5 | 95,6 / 95,5 | 96,5 / 96,5 | 97,0 / 97,0 |
| 8 | 88,2 / 87,7 | 93,0 / 92,8 | 94,4 / 94,3 | 95,8 / 95,7 | 96,6 / 96,6 |
| 10 | 86,2 / 85,5 | 91,8 / 91,5 | 93,6 / 93,4 | 95,3 / 95,2 | 96,2 / 96,3 |
| 15 | 81,1 / 80,2 | 88,8 / 88,4 | 91,3 / 91,1 | 93,9 / 93,8 | 95,3 / 95,4 |

Lectures :

- **Monotonies strictes** : P(fill) décroît en δ (une limite plus loin est touchée
  moins souvent) et croît en TTL — contrôles de cohérence passés (la QA les
  vérifie).
- **Symétrie buy/sell** : écart maximal 0,7 pt — le marché 24/7 n'a pas de dérive
  structurelle de mèches sur 733 j, le contrôle tient.
- **La référence durcie 97,9 % (δ=2) correspond à TTL≈3-6 toutes barres** : la
  mesure H1 est compatible avec cette méthode, mais elle mesurait probablement un
  horizon différent. Elle reste le chiffre durci de la MC v20 ; cette table en est
  la reconstruction à méthodologie ouverte.
- **Par tercile de volatilité (ATR%, buy, δ=2/TTL=2)** : t0 (basse) 97,2 %,
  t1 (médiane) 92,3 %, t2 (haute) 98,6 %. Pattern non monotone : les tendances
  modérées fillent MOINS (mèches asymétriques qui s'éloignent du niveau), les
  régimes extrêmes traversent tout. Noté tel quel, compris mais non exploité
  (aucun filtre de régime d'exécution ne peut se pré-enregistrer proprement sur
  cette seule observation).

## 4. Niveau B — la sélection réelle sur les signaux du pool P1 (le cœur)

Même machine, mais **aux barres de signal réelles** (les 469 entrées du pool),
rejouées en doctrine `_MK` exacte : limite placée à la clôture du signal, fill
intrabar, **fallback taker** à l'expiration TTL, invalidation si clôture au-delà
du stop sans fill. δ=2, TTL=2 (la config actuelle des `_MK`) :

| Cas | n | % | delta d'exécution vs taker certifié |
|---|---|---|---|
| **Fill maker** | 440 | 93,82 % | **+6,24 bps** en moyenne (p50 +6,1 ; la limite à δ sous le prix capture fees + spread + δ ; les gaps favorables ajoutent +0,14) |
| **Fallback taker** | 29 | 6,18 % | **−88,6 bps** en moyenne (p50 −69,7 ; p10 −152) : quand l'ordre limite ne se remplit pas en 2 barres, le prix a COURU — c'est le biais de sélection adverse, exactement |
| **Invalidé** | 0 | 0 % | — l'invalidation ne déclenche jamais : la limite est toujours entre le signal et le stop, une clôture au-delà du stop a forcément traversé la limite (contrôle mécanique) |

**Delta d'entrée moyen : +0,375 bps** — contre **4,0 bps supposés par la MC v20**.
Le maker δ=2/TTL=2 ne vaut que **9,4 % du crédit** que la MC lui donne. La raison
tient en un nombre : 29 fallbacks à −88,6 bps effacent 440 fills à +6,24.

**Par alpha (delta mix, bps)** :

| Alpha | n | delta moyen |
|---|---|---|
| A1 | 100 | **+2,226** |
| A3 | 82 | **+1,983** |
| A4 (cascade/éruption) | 287 | **−0,730** |

La sélection adverse est **concentrée sur A4** (61 % du pool) : les éruptions de
volatilité sont des trains qui partent — l'ordre limite rate le départ 6 % du
temps et paie 70-150 bps le rattrapage. Sur A1/A3 (signaux plus lents), le maker
gagne un delta positif. C'est une découverte structurelle : **l'exécution maker
ne s'active pas uniformément sur tous les alphas**.

**Grille δ×TTL sur les mêmes signaux (delta mix moyen, bps)** :

| Config | fill % | fallback % | delta mix |
|---|---|---|---|
| δ=1, TTL=1 | 94,03 | 5,97 | +1,722 |
| δ=1, TTL=2 | 95,74 | 4,26 | +1,644 |
| δ=2, TTL=1 | 91,26 | 8,74 | +0,927 |
| **δ=2, TTL=2 (actuelle)** | 93,82 | 6,18 | **+0,375** |
| δ=2, TTL=3 | 94,88 | 5,12 | +1,906 |
| **δ=2, TTL=6** | **97,44** | **2,56** | **+2,897** |
| δ=3, TTL=2 | 92,96 | 7,04 | +0,362 |
| δ=3, TTL=3 | 94,24 | 5,76 | +2,005 |
| δ=5, TTL=2 | 90,62 | 9,38 | +0,633 |
| δ=5, TTL=3 | 91,90 | 8,10 | +1,992 |

Deux lectures :

- La config actuelle des `_MK` (δ=2, TTL=2) est **quasi la pire de la grille** :
  TTL=2 laisse 6,18 % des signaux tomber dans le pire des cas (fallback sur train
  parti).
- **TTL=6 (δ=2) triple le delta** (+2,897 bps, fill 97,44 %, fallback 2,56 %).
  Le mécanisme est structurel (TTL↑ → fill↑ mécanique de la surface → moins de
  fallbacks désastreux), pas du fitting sur échantillon. **Mais** le coût caché
  n'est pas mesurable ici : un fill tardif entre dans un signal qui a 6 h —
  l'érosion temporelle de l'edge n'est observable qu'en papier (limite L6).
  Le TTL=6 est donc un **candidat pré-enregistré à falsifier en papier**, pas une
  recommandation : voir § 7 (run MK6 ajouté au protocole A/B docs/28).

## 5. Niveau C — la jambe de sortie (analytique)

Les jambes du pool : stop 264, tp1 209, tp2 126, trail 106, flipST 20, avortée 76,
trendflip 2, fin 1. Analyse par fraction de position :

- **TP1/TP2 (36,3 % du notional de sortie)** : sortie AU NIVEAU = ordre limite.
  En réel, delta maker vs taker sur ces jambes = fees (3,5) + spread évité (0,6)
  = **4,1 bps**, avec fill quasi certain (le prix CROISE le niveau pour
  l'atteindre ; un gap au-delà remplit AU gap, favorable). L'hypothèse MC tient
  sur les TP — c'est le seul endroit où elle tient.
- **Stop/trail/flipST/trendflip/avortée/fin (63,7 %)** : sorties au marché,
  taker des deux régimes → **delta 0**.

**Delta de sortie pondéré : 1,488 bps** (36,3 % × 4,1).

## 6. Verdict — le candidat v21

| | entrée (mesurée) | sortie (analytique) | **par jambe** |
|---|---|---|---|
| δ=2/TTL=2 | +0,375 bps | +1,488 bps | **+0,931 bps** |
| δ=2/TTL=6 | +2,897 bps | +1,488 bps | **+2,193 bps** |

Le crédit MC v20 (4,0 bps/jambe) est **réfuté** pour l'entrée : le maker réel en
vaut 23,3 % (TTL=2) à 54,8 % (TTL=6). Traduction en médiane par le noyau MC
(réutilisation du noyau v11/v12 bit-à-bit, pool P1, 12 000 trajectoires, 36 mois ;
contrôles verts : S0 641,99 $ reproduit, D2 468,4 $ et taker 272,7 $ retrouvés,
monotonie OK) :

| Scénario | extra par jambe | médiane 12 m | p25 | p75 | P(250 $) | P(50 100 $ @36 m) |
|---|---|---|---|---|---|---|
| S0 référence | 0 | **642,0 $** | 277 | 1 692 | 80,1 % | 35,7 % |
| Maker v20 supposé (δ=2/TTL=2, fill 97,9 %) | 2,1 | **468,4 $** | 213 | 1 187 | 73,0 % | 21,3 % |
| **Maker MESURÉ (δ=2/TTL=2)** | 5,169 | **306,2 $** | 157 | 740 | 61,3 % | 8,1 % |
| **Maker MESURÉ (δ=2/TTL=6)** | 3,908 | **364,0 $** | 176 | 898 | 66,5 % | 12,7 % |
| Taker all-in | 6,1 | **272,7 $** | 145 | 640 | 57,2 % | 5,8 % |

- **L'avantage maker réel est +12,3 % de médiane (306,2 vs 272,7 $), pas +71,8 %.**
  Il reste positif et mécanique, mais la MC v20 l'a gonflé d'un facteur ~4 sur
  l'entrée.
- **Le TTL=6 remonte l'avantage à +33,6 %** (364,0 $) — à la condition non mesurée
  que l'edge du signal survit à 6 h d'attente (L6) : à falsifier en papier AVANT
  toute promotion.
- Le x501 complet (36 mois) passe de 21,3 % (v20 maker) à **8,1 %** (TTL=2) /
  **12,7 %** (TTL=6) en probabilité de 50 100 $ — la mission x501 à 12 mois reste
  hors d'atteinte du V1 seul dans TOUS les scénarios ; la hiérarchie
  (V1 → V2 multi-alpha → V3 gestion) n'est pas changée, mais ses marges oui.
- **Statut** : ces médianes sont un **candidat v21**. Les chiffres officiels
  (docs/25, baseline 2026-10-01) ne bougent pas tant que la review n'a pas
  validé la mesure et ses limites (§ 8). Après validation : nouvelle baseline
  datée, docs/25 table officielle ré-éditée, les `_MK` gardent δ=2/TTL=2 par
  défaut (le TTL=6 ne passe en défaut qu'après le run papier MK6).

## 7. La boucle de surveillance — les compteurs `_MK` ont maintenant une hypothèse à tester

La mesure historique est une mesure **passée**. La preuve que le régime maker
tient en vraie exécution passe par les compteurs internes des `_MK`
(`mkFills/mkFb/mkTOut/mkInv`, rapport fin de run sur `isLastBar`), maintenant
reliés à une hypothèse explicite : **93,82 %** de fill maker pur (440/469),
**0 %** d'invalidation.

L'outil `x501_mk_compteurs.py` transforme un relevé CSV en verdict mécanique
(stdlib pure, test binomial exact, ordre des verdicts : INSUFFISANT (n<30) →
DIVERGENCE (mkInv>0 : audit d'état OBLIGATOIRE — l'invalidation ne devrait
jamais déclencher) → CONFORME / DÉRIVE_BAS / DÉRIVE_HAUT (p<0,05)) :

```
python3 x501_mk_compteurs.py releve.csv    # verdict + JSON à côté du relevé
python3 x501_mk_compteurs.py --demo        # démo auto-contenue
```

Format du relevé (une ligne par run/rélevé, agrégé par le parseur) :

```
date_iso,symbole,timeframe,mkFills,mkFb,mkTOut,mkInv,fallback_on
2026-10-05,BTCUSDT,H1,31,2,1,0,1
```

**Run MK6 ajouté au protocole A/B (docs/28, extension pré-enregistrée du
01/10/2026)** : `Signature_H1_MK` avec makerTTL=6 vs makerTTL=2 (BTC + ETH),
critères de verdict inchangés (bootstrap 10 000, N_MIN 20, PROMOTION/KILL/
INCONCLU dans l'ordre du protocole). Ce que la mesure historique ne peut pas
dire — l'edge survit-il à 6 h d'attente ? — seul le run répondra.

## 8. Limites pré-enregistrées

- **L1** l'ordre de passage intrabar (limite vs stop dans la MÊME barre) n'est
  pas observable en 1h : la doctrine fill-puis-invalide suit l'ordre des prix
  (la limite est toujours entre le signal et le stop).
- **L2** le mid n'est pas mesuré : le gain de prix est calculé vs le prix taker
  original (open de la barre d'exécution) ; le spread 0,6 bps est une mesure
  moyenne — seule la composante « prix » dépend de la data, les composantes
  fees/spread sont des constantes du marché réel.
- **L3** les tentatives de la surface se chevauchent (un ordre par barre) :
  estimateur cohérent de P(touch | horizon), autocorrélation documentée.
- **L4** la composition des jambes (quelles sorties existent) est tenue
  inchangée par le changement de régime d'entrée (un décalage de 2 bps sur un
  stop à ~242 bps) — approximation du premier ordre.
- **L5** le delta de sortie est analytique (4,1 bps sur TP, 0 ailleurs), pas
  mesuré : le fill TP limite est considéré certain.
- **L6** l'érosion temporelle de l'edge pour les fills tardifs (TTL long) n'est
  PAS mesurable sur data historique sans re-run complet du moteur : c'est LA
  question que le run papier MK6 tranche.

## 9. Reproduction

```bash
# prérequis : data klines 1h format Binance (couche 1h docs/26) dans data/x501_1h
X501_DATA_DIR=data/x501_1h python3 scripts/studies/x501_openmarket/x501_fill_maker_surface.py
# -> fill_maker_surface.json (surface + niveau B + grille + niveau C + verdict)

python3 scripts/studies/x501_openmarket/x501_mk_compteurs.py --demo
# -> verdicts compteurs _MK (format relevé § 7)
```

Les médianes du § 6 sont produites par le noyau MC du domaine (v11/v12, pool P1,
seed 7, cad 3 — reproductibles bit à bit) rejoué avec `extra = 6,1 − delta_par_jambe`
sur les scénarios 5,169 et 3,908 bps/jambe.

## 10. Ce que ça change pour la mission

- **Le maker reste le levier d'exécution n°1, mais mesuré** : +12,3 % de médiane
  en l'état, +33,6 % si le TTL=6 survit au papier. Plus jamais un taux de fill
  incrusté sans sa méthode : la surface de ce document est la référence
  reproductible.
- **La sélection adverse est concentrée sur A4** : toute future activation du
  maker par alpha doit lire cette table (A1 +2,2 / A3 +2,0 / A4 −0,7) —
  l'exécution est une décision PAR ALPHA, pas globale.
- **La règle des coûts reste la boussole** : −2 bps de coût ≈ +25 % de médiane ;
  chaque point de fill manquant vaut ~88 bps sur les signaux A4 — le fallback
  taker est le coût le plus cher du système, plus cher que n'importe quel fee.
- **L'ordre du jour ne change pas** : preuve live 90 j (protocole v11) avant tout
  capital réel, compteurs `_MK` relevés chaque semaine, registre docs/20 à
  chaque verdict.
