# INV-L « L'ACCORD DES HORIZONS » — PRÉ-ENREGISTREMENT (02/10/2026, AVANT toute mesure)

Statut : **EXPERIMENTAL** — gouvernance docs/38, tag freeze-2026-10-02. Budget
consommé : 1 expérience (famille `convergence-horizons`, 1/5 — neuve). Aucun
seuil, aucune grille (accord binaire des signes), STOP après verdict.

**Seal sha256 du pré-enregistrement** (hash du fichier AVANT l'ajout des
RÉSULTATS, hors ce bloc et le trailer de 5 lignes qui ouvre la section —
`awk '{print} /^# RÉSULTATS/{exit}' <fichier> | sed '7,10d' | head -n -5 | sha256sum`) :
`5f6a942d14fd60f943854f3ff25d3d0d5adb998a9562052ce4cf0d48bf11be20`

## ADJACENCE déclarée (obligatoire, jugée AVANT calcul)

1. **survivors_momentum_bear_lb48 (PAPER_FORWARD, registre)** — SHORT momentum
   mono-horizon (lb48) : magnitude/direction d'UN regard 48 h, stratégie
   armée en forward. **Delta INV-L** : la CONVERGENCE des SIGNES de TROIS
   horizons (24/72/168) comme conditionneur d'état, symétrique (2 branches),
   aucun seuil, aucune re-codification de la stratégie — l'information brute
   de l'accord, jamais testée.
2. **survivors_trend_long_ema50x200 (PAPER_FORWARD, registre)** — structure
   prix vs moyennes (EMA 50/200) mono-timeframe. Delta : ici des RENDEMENTS
   multi-jours bruts et leur unanimité directionnelle, pas un croisement
   d'EMA. Les deux stratégies ne sont PAS recodées.
3. **confluence v5 (docs/20)** — accel + vwap 3σ : confluence d'INDICATEURS
   intrabar, pas d'HORIZONS de rendement. Non adjacente.
4. **INV-D (temps-structure, FAIL)** — fraction des 24 closes au-dessus du
   close courant (chemin intraday, quantile). Ici : signes de rendements
   24/72/168 h, événement binaire sans quantile. Construction différente.
5. Familles mortes vérifiées (INV-A déviance, INV-B Herfindahl, INV-D,
   INV-E run-length, INV-F co-déformation, INV-G silence, INV-I tape,
   INV-K mèches, cascade, TP/SL, carry, garde DD, sizing) : aucune ne mesure
   l'unanimité des signes multi-horizons. Adjacence jugée **acceptable** —
   l'expérience part.

## CONSTRUCTION (jamais testée comme conditionneur)

Panel : les 6 majeures (BTC/ETH/SOL/BNB/XRP/DOGE USDT), klines 1h
`data/warehouse/klines.db` en LECTURE SEULE. À chaque close 1h d'indice i
(i ≥ 168) :

- ret24 = close(i)/close(i−24) − 1 ; ret72 = close(i)/close(i−72) − 1 ;
  ret168 = close(i)/close(i−168) − 1. Tous les closes utilisés sont connus au
  close de décision (le signal EST le close t, zéro look-ahead).
- Intégrité : toute bougie violant high ≥ max(o,c) et low ≤ min(o,c) est
  rejetée (compte déclaré) ; open_time dupliqué dédoublé ; ret nul (signe 0)
  → heure non classable (compte déclarée).
- **Événement ACCORD COMPLET** : les 3 retours de même signe. Deux branches
  mutuellement exclusives : haussier (3 positifs) / baissier (3 négatifs).
- **Gradient** : accords partiels 2/3 (exactement 2 même signe + 1 opposé)
  servent d'échelon inférieur — le 2/3 doit rendre MOINS que le 3/3.

## OPÉRATIONNALISATION des signes (figée avant mesure)

P&L net d'un trade : `net_long(r) = (1+r)(1−c)−1` / `net_short(r) =
(1−r)(1−c)−1`, c = 18 bps RT, r = rendement brut entrée→sortie. Branches
nettes = espérance du TRADE de la branche (LONG sur accord haussier,
SHORT sur accord baissier), BLOC 24-72 = moyenne des 3 espérances d'horizon
(convention INV-K). Aucune dérivation par le drift : la branche doit payer
ses coûts elle-même.

## HYPOTHÈSE PRÉ-DÉCLARÉE

L'accord complet des 3 horizons prédit la CONTINUATION dans le sens de
l'accord sur 24-72 h (le momentum converge). Le contrôle inverse =
l'ÉPUISEMENT (l'accord prédit le retournement) doit être pire : sur accord
haussier le SHORT < LONG ; sur accord baissier le LONG < SHORT.

## PASS/FAIL écrits AVANT

- PASS = (1) branche haussière nette LONG > 0 en TRAIN ET VAL (bloc 24-72) ;
  (2) branche baissière nette SHORT > 0 en TRAIN ET VAL ; (3) gradient
  MONOTONE : complet 3/3 > partiel 2/3 pour CHAQUE branche, TRAIN ET VAL ;
  (4) contrôle inverse battu aux 2 branches et 2 splits ; (5) n train ≥ 100
  PAR BRANCHE sinon « sous-puissant » déclaré (non tranchable).
- FAIL = tout le reste — « FAIL — hypothèse réfutée », gravé, STOP
  (budget = 1 expérience, aucun seuil/fenêtre/côté supplémentaire).

## PROTOCOLE IMMUTABLE (0 modification)

Split 60/40 chrono GLOBAL du panel (convention INV-D/K : ts_split = tmin +
0.60·(tmax−tmin)) ; entrée = open de la 1re barre ≥ t+1h (tolérance +3h) ;
sorties au close t+h, horizons 24/48/72 ; 1x sans levier (0 liquidation par
construction) ; coûts 18 bps RT ; BLOC STATS mensuel sur wallet premier-arrivé
par symbole (1 position/symbole, trades LONG/SHORT 24h des 2 branches,
notionnel fixe — garde-fou composé-des-mois = final par construction).
Honnêteté panel : BNB/XRP/DOGE ~1 an de données → 100 % VAL (déclaré) ;
dépendance : runs d'heures-accords consécutifs comptés (un accord persiste
typiquement plusieurs heures — n brut >> n effectif, le wallet premier-arrivé
est l'estimateur honnête).

---
---

# RÉSULTATS (exécution post-scellage — rien ci-dessus n'a précédé le seal)

Script : `scripts/studies/inv_l_accord_horizons.py` (DB ro, 160 233 barres
panel, 1 bougie BTC rejetée par contrôle d'intégrité mèches, 394 heures à
ret nul exclues, 430 sans forward complet → 158 401 points valides).
Split 60/40 global = **2024-09-19 08:24 UTC**. Honêteté panel : BNB/XRP/DOGE
0 événement TRAIN (données ~1 an) → 100 % VAL. L'événement n'est PAS rare :
accords complets = **~50 % des heures** (haussier 38 987, baissier 39 740 ;
partiels 2/3 : 39 006 / 40 668). Incident de code de RAPPORT documenté : le
compteur de runs v1 comptait les symboles (6) au lieu des runs — corrigé,
chemin du verdict ré-exécuté **bit-identique** (diff nul hors la ligne du
compteur) ; dépendance corrigée : 4 379 runs bull / 4 701 bear (run max
108 h / 141 h) — ~9 heures-événements par run, le wallet premier-arrivé est
l'estimateur honnête.

## Bloc 24-72 (espérances nettes, bps)

| branche | split | n | h24 | h48 | h72 | BLOC branche net | brut | contrôle net |
|---|---|---|---|---|---|---|---|---|
| HAUSSIER (LONG=hyp.) | TRAIN | 19598 | +6.7 | +28.3 | +51.0 | **+28.7** | +46.7 | SHORT −64.7 |
| HAUSSIER (LONG=hyp.) | VAL | 19389 | +0.4 | +10.6 | +9.4 | **+6.8** | +24.8 | SHORT −42.8 |
| BAISSIER (SHORT=hyp.) | TRAIN | 19883 | −12.3 | −29.7 | −26.4 | **−13.2** (driftL −22.8) | −4.8 | LONG −22.8 |
| BAISSIER (SHORT=hyp.) | VAL | 19857 | −9.2 | +7.9 | +28.0 | **−44.9** (driftL **+8.9**) | +26.9 | LONG **+8.9** |

## Les quatre critères pré-enregistrés

1. **Branche haussière LONG > 0 (train et val)** : OUI — +28.7 / +6.8 bps
   (mais VAL +6.8 bps = à peine au-dessus des coûts).
2. **Branche baissière SHORT > 0 (train et val)** : NON — TRAIN −13.2 bps
   (le drift est bien négatif, −22.8 bps, mais ne paie pas les 18 bps RT) ;
   VAL −44.9 bps avec drift **INVERSÉ** (+8.9 bps : le marché MONTE après
   l'accord baissier complet en VAL).
3. **Gradient complet 3/3 > partiel 2/3** : NON — tenu sur la branche
   haussière aux 2 splits (train +28.7 vs −4.5 ; val +6.8 vs −47.0) mais
   INVERSÉ sur la baissière en VAL (complet −44.9 < partiel +3.8).
4. **Contrôle inverse battu** : NON — battu sur la branche haussière (SHORT
   < LONG aux 2 splits) et sur la baissière en TRAIN (LONG −22.8 < SHORT
   −13.2), mais PERDU sur la baissière en VAL (LONG +8.9 > SHORT −44.9).

n train 19598 / 19883 ≥ 100 par branche (puissante, pas de déclaration de
sous-puissance).

## BLOC STATS mensuel (wallet premier-arrivé, LONG/SHORT 1x 24h, notionnel fixe)

5 164 trades (vs 78 727 heures-événements bruts ; long 2 529 / short 2 635) —
**WR_net 43.8 %, 0 liq (1x par construction), cumul −771.10 %, ROI/an
−152.5 %, DD 794.29 %, 40/61 mois négatifs, record 2026-08 +94.1 %, pire
2026-03 −136.5 %**. Garde-fou composé-des-mois = final par construction.
Détail des 61 mois dans la sortie du script (re-run déterministe).

## VERDICT : FAIL — hypothèse réfutée (asymétrique)

**L'accord complet des 3 horizons ne porte PAS une continuation symétrique.**
La branche baissière est morte aux deux critères décisifs (SHORT net négatif
en TRAIN ET VAL, gradient inversé en VAL, contrôle perdu en VAL : l'accord
baissier persistant précède la REPRISE haussière en VAL, pas la chute). La
branche haussière seule tient (continuation positive aux 2 splits, contrôle
battu) mais VAL +6.8 bps net = porté à peine au-dessus des 18 bps RT — non
actionnable, et un critère sur quatre ne fait pas un PASS. Cohérent avec la
leçon INV-K : sur Aster 1h, les états baissiers PERSISTANTS ne délivrent
jamais un short net — ils précèdent l'absorption des vendeurs. Et l'accord
des signes est l'état par défaut d'un marché à dérive (~50 % des heures),
pas une anomalie : il n'encode pas d'information rare. Budget = 1 expérience
consommée, STOP — tout re-test (côté haussier seul, autre fenêtre d'accord,
seuil de magnitude) = PARAMETER_MUTATION interdite sans nouveau
pré-enregistrement + budget.
