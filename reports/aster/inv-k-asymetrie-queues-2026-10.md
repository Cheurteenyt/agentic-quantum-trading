# INV-K « L'ASYMÉTRIE DES QUEUES » — PRÉ-ENREGISTREMENT (02/10/2026, AVANT toute mesure)

Statut : **EXPERIMENTAL** — gouvernance docs/38-gouvernance-recherche.md, tag
freeze-2026-10-02. Budget consommé : 1 expérience (famille `structure-meches`,
1/5 — famille neuve). Un seul seuil, un seul côté, aucune grille, STOP après verdict.

**Seal sha256 du pré-enregistrement** (hash du présent fichier AVANT l'ajout de
la section RÉSULTATS, hors le présent bloc — vérifiable sur le fichier final
par `awk '{print} /^# RÉSULTATS/{exit}' <ce fichier> | sed '7,10d' | sha256sum`) :
`58d01ce0380bae3539c1bf280262815c72fe01f215c78766db2b792783bc290c`

## ADJACENCE déclarée (obligatoire, jugée AVANT calcul)

1. **wick_retrace (T21, tué)** — `scripts/studies/aster_discovery_2123.py` :
   fade d'une MÈCHE ISOLÉE (`lw`/`uw` = fraction de range d'UNE bougie, gate
   ATR, hold court). Non-survivant T21 (absent des 4 survivants du registre).
   **Delta INV-K** : un ÉTAT roulant de 24 h de structure de mèches (ratio des
   MOYENNES high−close / close−low), pas un événement single-bar ; horizon
   forward 24-72 h, pas un fade à hold court. Construction jamais existée.
2. **INV-D (temps-structure, FAIL)** — mesurait le TEMPS sans magnitude
   (fraction de closes au-dessus). Ici la MAGNITUDE des mèches (haut vs bas),
   jamais testée en état roulant.
3. Familles mortes vérifiées au registre (INV-A/B/D/E/F/G/I, cascade, TP/SL,
   carry, garde DD, sizing) : aucune ne mesure le rapport queue-haute/
   queue-basse roulant. Adjacence jugée **acceptable** — l'expérience part.

## CONSTRUCTION (jamais existée)

Panel : les 6 majeures (BTC/ETH/SOL/BNB/XRP/DOGE USDT), klines 1h
`data/warehouse/klines.db` en LECTURE SEULE. À chaque close 1h d'indice i :

- Q_t = mean(high−close, bougies i−24..i−1) ÷ mean(close−low, bougies i−24..i−1)
  — fenêtre = les 24 bougies closes STRICTEMENT avant le close de décision
  (convention INV-D, zéro look-ahead : la bougie de décision ne date le signal).
- Intégrité : toute bougie violant high ≥ max(o,c) et low ≤ min(o,c) est rejetée
  (compte déclaré) ; dénominateur nul → Q_t = NaN, point exclu (compte déclaré).
- **Événement** : Q_t ≥ q95 TRAIN (un seul seuil, quantile 0.95 des Q_t TRAIN
  du panel poolé, calibré TRAIN seulement) — la queue haute écrase la basse de
  façon persistante.

## OPÉRATIONNALISATION des signes (figée avant mesure)

Le P&L net d'un trade est `net_long(r) = (1+r)(1−c)−1` / `net_short(r) =
(1−r)(1−c)−1`, c = 18 bps RT, r = rendement brut entrée→sortie. L'hypothèse
porte sur l'ESPÉRANCE FORWARD DU PRIX (dénomination LONG). « Espérance nette
< 0 (short) » = le drift forward net, dénommé long (net_long), < 0 — c'est la
condition de baisse qui valide le short structurel ; le P&L net du trade SHORT
lui-même (net_short) est rapporté à côté : un PASS avec net_short ≤ 0 = edge
directionnel réel mais sous les coûts → non actionnable, déclaré tel quel
(le wallet séquentiel trancherait de toute façon avant tout stack).

## HYPOTHÈSE PRÉ-DÉCLARÉE

La queue haute écrasante = le rejet du haut persiste dans la structure →
espérance forward 24-72 h NÉGATIVE (short structurel). Contrôle inverse
obligatoire : la continuation haussière (le LONG sur les mêmes événements)
doit être pire.

## PASS/FAIL écrits AVANT

- PASS = (1) espérance nette < 0 (short — cf. opérationnalisation : bloc 24-72
  net_long) en TRAIN ET VAL ; (2) gradient MONOTONE sur les quintiles de Q_t
  (bornes TRAIN, espérance nette SHORT h24 croissante Q1→Q5, inversions
  adjacentes ≤ 1, Q5 = max) en TRAIN ET VAL ; (3) contrôle inverse battu :
  net_short > net_long à CHACUN des 3 horizons, TRAIN ET VAL ; (4) n train
  ≥ 100 événements sinon « sous-puissant » déclaré (non tranchable).
- FAIL = tout le reste — « FAIL — hypothèse réfutée », gravé, STOP
  (budget = 1 expérience, aucun 2e quantile ni côté ni fenêtre).

## PROTOCOLE IMMUTABLE (0 modification)

Split 60/40 chrono GLOBAL du panel (convention INV-D : ts_split = tmin +
0.60·(tmax−tmin)) ; entrée = open de la 1re barre ≥ t+1h (tolérance +3h) ;
sorties au close t+h, horizons 24/48/72 ; BLOC 24-72 = moyenne des 3 espérances
d'horizon ; 1x sans levier (0 liquidation par construction, déclaré) ; coûts
18 bps RT ; BLOC STATS mensuel sur wallet premier-arrivé par symbole (1
position/symbole, trades SHORT 24h, notionnel fixe — garde-fou composé-des-mois
= final par construction). Honêteté panel : BNB/XRP/DOGE ~1 an de données →
100 % VAL (déclaré).

---
---

# RÉSULTATS (exécution post-scellage — rien ci-dessous n'a précédé le seal)

Script : `scripts/studies/inv_k_asymetrie_queues.py` (DB ro, 160 089 barres
panel, 1 bougie BTC rejetée par contrôle d'intégrité mèches, 6 points
dénominateur nul exclus, 432 sans forward complet → 159 651 points valides).
Split 60/40 global = **2024-09-19 08:24 UTC** ; q95 TRAIN = **1.4836**
(médiane Q 0.977) ; bornes quintiles TRAIN [0.7887, 0.9160, 1.0409, 1.2054].
Honnêteté panel : BNB/XRP/DOGE 0 événement TRAIN (données ~1 an) → 100 % VAL.

## Bloc 24-72 (espérances nettes, bps)

| split | n | h24 drift L | h48 drift L | h72 drift L | BLOC drift L net | BLOC SHORT net | brut |
|---|---|---|---|---|---|---|---|
| TRAIN | 3991 | +22.3 (WR 54.0 %) | +24.1 | +37.7 | **+28.1** | −64.1 | +46.1 |
| VAL | 4094 | −6.8 (WR 47.3 %) | +12.8 | +19.4 | **+8.4** | −44.4 | +26.5 |

Le drift net est **POSITIF aux deux splits** : le marché MONTE après l'état
queue-haute-écrasante. Le trade SHORT perd net (−64.1/−44.4 bps).

## Les trois critères pré-enregistrés

1. **Espérance nette < 0 (short)** : NON — +28.1 bps TRAIN, +8.4 bps VAL
   (positif = signe INVERSÉ de l'hypothèse, les deux splits).
2. **Contrôle inverse (continuation haussière pire)** : NON — le SHORT est
   PIRE que le LONG aux 3 horizons et aux 2 splits (train S/L : −58.3/+22.3,
   −60.1/+24.1, −73.7/+37.7 ; val : −29.2/−6.8, −48.8/+12.8, −55.4/+19.4).
   C'est la CONTINUATION qui gagne.
3. **Gradient quintiles monotone** : NON — TRAIN 3 inversions adjacentes,
   Q5 ≠ max (−0.353 % vs max −0.100 % au Q1) ; VAL Q5 ≠ max. L'espérance
   short ne croît PAS avec Q.

n train = 3991 ≥ 100 (puissante, pas de déclaration de sous-puissance).

## BLOC STATS mensuel (wallet premier-arrivé, SHORT 1x 24h, notionnel fixe)

1 212 trades (vs 8 085 événements bruts) — **WR_net 45.5 %, 0 liq (1x par
construction), cumul −363.66 %, ROI/an −71.9 %, DD 393.30 %, 41/61 mois
négatifs, record 2025-02 +64.1 %, pire 2021-11 −57.3 %**. Garde-fou
composé-des-mois = final par construction. Détail des 61 mois dans la sortie
du script (re-run déterministe).

## VERDICT : FAIL — hypothèse réfutée (triple)

**La queue haute écrasante ne encode pas un rejet persistant : elle précède la
CONTINUATION haussière** (drift net +28.1/+8.4 bps train/val, contrôle inverse
perdu dans le sens exactement opposé). Cohérent mécaniquement avec la lecture
absorption déjà gravée (docs/20 : les attaques acheteuses absorbées précèdent
la continuation — la dynamique traverse le mur) : un état 24h où la mèche
haute moyenne écrase la basse = l'absorption acheteuse des replis, pas
l'épuisement. Observation inverse descriptive NON actionnable ici (le LONG
brut +46.1/+26.5 bps porte à peine les coûts ; aucun côté ni quantile ni
fenêtre supplémentaire toléré). Budget = 1 expérience consommée, STOP — tout
re-test (miroir q05, autre fenêtre, autre côté) = PARAMETER_MUTATION interdite
sans nouveau pré-enregistrement + budget.
