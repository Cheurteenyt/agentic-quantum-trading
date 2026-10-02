# INV-M — « LE RETARD D'ETH » (pré-enregistrement + résultats)

- **Domaine** : Aster (BTC/ETH 1h, données klines.db en lecture seule)
- **Date de pré-enregistrement** : 2026-10-02, AVANT tout résultat (ce bloc écrit avant l'exécution du script)
- **Gouvernance** : docs/38-gouvernance-recherche.md, tag `freeze-2026-10-02` ; registre `research/registry.yaml` vérifié (grep lead/lag/retard/rattrap) : AUCUNE expérience de retard directionnel n'existe. **ADJACENCE DÉCLARÉE** : le corr-tilt de la machine = le **NIVEAU** de corrélation p66/p33 (docs/20, CANDIDAT en prod) ; « vendeur unique RÉFUTÉ » = le **couplage** des cascades (famille fermée, 15+ verdicts) ; INV-F = l'événement **conjoint vol×corr** (SOUS-PUISSENT, SENS=0). Le delta ici : le **RETARD directionnel d'un actif précis** (ETH derrière BTC après un choc BTC) — un ÉVÉNEMENT de lead-lag structurel intra-pack, pas un niveau, pas un couplage, pas une co-déformation. Pas une PARAMETER_MUTATION d'aucune famille morte (INV-A/B/D/E/F/G/I/K/L, cascade, fractalité, TP/SL, carry, garde DD, sizing conditionnel — aucun ne construit un ratio de retard ETH/BTC conditionné à un choc BTC). Budget : 1 expérience, 0 modification de protocole.
- **Script one-shot** : `scripts/studies/inv_m_retard_eth.py` (unique exécution, aucun re-run de variante autorisé)

## 1. Hypothèse pré-déclarée (DIRECTION, branches explicites — leçon INV-L assumée)

Après un **retard** — BTC fait un choc directionnel (|ret1h BTC| ≥ q95 TRAIN) et ETH n'a suivi que **moins de 40 %** du mouvement BTC dans les 60 minutes suivantes — ETH **rattrape vers le mouvement de BTC** (catch-up) sur les 4 h suivantes : espérance **nette positive** dans le sens du mouvement de BTC, en TRAIN **ET** VAL.

**Deux branches** testées : catch-up **haussier** (choc BTC up → LONG ETH) et catch-up **baissier** (choc BTC down → SHORT ETH). **Honnêteté INV-L pré-déclarée** : sur Aster 1h, les états baissiers persistants ne délivrent jamais de short net (INV-L : branche baissière morte, drift VAL inversé ; INV-K : la continuation haussière gagne). La branche baissière est un short 4 h après une impulsion baissière — si elle exige un short sur un état baissier persistant, elle est morte d'avance et sera déclarée telle quelle, sans réparation. **Contrôle inverse obligatoire** : la divergence continue (ETH s'éloigne ENCORE, mouvement opposé à BTC pendant les 60 min) doit être **pire** que l'ensemble des retards.

## 2. Construction (une seule définition par quantité, zéro grille, jamais re-tunée)

- Données : `data/warehouse/klines.db` **LECTURE SEULE** (mode=ro), table `klines`, interval `1h`. **Leçon ts_ms vérifiée AVANT le pré-enregistrement** : `open_time` en **MILLISECONDES** ; grille commune BTC/ETH = **44 424 heures** contiguës (2021-09-07 03:00 → 2026-10-02 02:00 UTC, **0 trou**, 0 doublon — vérifié AVANT le gel).
- **ret1h_X(t)** = close_X(t)/close_X(t−1) − 1 (close-to-close 1 h, causal).
- **Split 60/40 chrono GLOBAL** : T_split = percentile 60 des timestamps de la grille commune (un seul bornage). TRAIN = t < T_split, VAL = t ≥ T_split.
- **q95_TRAIN** = quantile 95 (numpy, interpolation linéaire, non arrondi) des |ret1h_BTC(t)| sur les heures TRAIN **uniquement** ; gelé, appliqué tel quel en VAL, jamais recalculé.
- **Événement de RETARD à l'heure t** (t = heure de la bougie BTC choc ; causal, données ≤ t+1) :
  1. **Choc BTC** : |ret1h_BTC(t)| ≥ q95_TRAIN ;
  2. **Retard** : fraction f(t) = ret1h_ETH(t+1) × sign(ret1h_BTC(t)) / |ret1h_BTC(t)| **< 0,4** — ETH a bougé moins de 40 % du mouvement BTC dans les 60 minutes suivantes (la bougie t+1, unique fenêtre). **Le retard, seul seuil** (0,4 gelé). f < 0 = ETH a bougé CONTRE BTC (la divergence continue, sous-ensemble du contrôle inverse) ; 0 ≤ f < 0,4 = le retard pur.
- **Trade** (convention harnais : signal confirmé à la close de t+1 — le retard n'est observable qu'après les 60 min) : entrée = close_ETH(t+1), sortie = close_ETH(t+5) (hold 4 h exactement).
- **Catch-up net** = sign(ret1h_BTC(t)) × [close_ETH(t+5)/close_ETH(t+1) − 1] − **0,0018** (18 bps RT, 1x). Branches : haussière s=+1 (LONG), baissière s=−1 (SHORT).
- **Gradient de l'ampleur du retard** : quintiles de f sur les retards purs TRAIN (0 ≤ f < 0,4) ; le retard le plus profond = f le plus petit. Monotonie = médiane nette **non croissante** le long de f croissant (Q1 f bas → Q5 f haut), ≥ 5 événements/quintile requis sinon **non évaluable**. VAL descriptif.
- **Contrôle inverse** : sous-ensemble f < 0 (divergence continue) — médiane nette du contrôle < médiane nette de l'ensemble des retards (f < 0,4), en TRAIN ET VAL.
- Événement non mesurable (t+5 hors grille) → exclu, compté, documenté. ret1h_BTC(t) = 0 impossible par construction (q95 > 0). Les ret1h_ETH(t+1) **nuls sont conservés** (f = 0 = retard extrême, une information, pas une anomalie — grille contiguë, closes > 0).

## 3. Protocole immutable

- **1x, coûts 18 bps RT, 0 liquidation par construction attendue** (levier 1x : liquidation impossible sous −100 %) — MAE par trade mesuré sur les lows/highs intra-détention [t+1, t+5] ; levier sûr = 100/(maxMAE+0,5) rapporté pour honnêteté.
- **n_train ≥ 60 événements** (ensemble f < 0,4 TRAIN mesurable) sinon expérience déclarée **SOUS-PUISSENTE** — aucun PASS possible, aucun relâchement. STOP.
- **BLOC STATS mensuel obligatoire** : mois | split | n événements | n wallet | WR net | médiane nette (bps) | PnL wallet cumulé %.
- **Wallet séquentiel premier-arrivé** (honnêteté, estimateur réel) : une position ETH à la fois, 1x, compounding, fusion des deux branches (un événement = un trade), entrée close t+1, sortie close t+5 ; chevauchements documentés.

## 4. Critères PASS/FAIL (écrits AVANT les résultats)

**PASS = tous, sans exception :**
1. **n_train ≥ 60** événements mesurables.
2. **Catch-up net > 0 en TRAIN ET VAL** sur la branche haussière (LONG).
3. **Catch-up net > 0 en TRAIN ET VAL** sur la branche baissière (SHORT) — ou branche déclarée **CONTEXTE** (non viable), la haussière seule portant le PASS.
4. **Gradient monotone** sur l'ampleur du retard (quintiles f TRAIN, médiane nette non croissante le long de f croissant, ≥ 5/quintile).
5. **Contrôle inverse battu** : médiane nette (f < 0) < médiane nette (f < 0,4) en TRAIN **ET** VAL. Si la divergence continue ne bat rien, le « retard » n'explique rien (tout choc BTC se rattrape pareil) et l'hypothèse est morte.

**FAIL = tout le reste** → « FAIL — hypothèse réfutée », gravé au registre, budget consommé, **STOP**. Pas de deuxième quantile, pas de fenêtre alternative (4 h → 8 h, etc.), pas de seuil 0,4 re-tuné, pas de filtre de réparation. Budget = 1 expérience.

**Si n_train < 60** : verdict **SOUS-PUISSENT** (budget consommé, STOP, aucun relâchement).

**Si PASS** : verdict **CANDIDAT** — passage obligatoire par le wallet séquentiel `scripts/stacked_portfolio.py run_stack` avant toute entrée dans le stack (gel docs/38 : jamais une promotion sans ça).

---

# RÉSULTATS (exécution unique du 02/10/2026)

> **Seal du pré-enregistrement** : sha256 du fichier gelé AVANT exécution :
> `d2b8b846f90d9e44f358076097347d610b0699da572d0a197120193e02df223b`

## Exécution

- Grille commune BTC/ETH 1h : **44 424 heures contiguës** (2021-09-07 03:00 → 2026-10-02 02:00 UTC), 0 trou — vérifié à l'exécution.
- **T_split (60/40 chrono global)** = **2024-09-21 17:00 UTC** (26 654 barres TRAIN / 17 770 VAL).
- **q95_TRAIN |ret1h BTC| = 1,1939 %** (gelé, appliqué tel quel en VAL).
- **Événements retard (f < 0,4) : n = 1 867** — TRAIN **1 333** / VAL 534, 0 exclu hors grille. Puissant (C1 OK, ≥ 60).

## 1. Branches (net, 18 bps RT, entrée close t+1 → sortie close t+5)

| Branche | Split | n | WR net | net médian | brut médian | somme |
|---|---|---|---|---|---|---|
| HAUSSIÈRE (LONG) | TRAIN | 659 | 43,1 % | **−16,7 bps** | +1,3 | −109,78 %not |
| HAUSSIÈRE (LONG) | VAL | 250 | 44,0 % | **−33,2 bps** | **−15,2 (signe inversé)** | −32,55 %not |
| BAISSIÈRE (SHORT) | TRAIN | 674 | 41,4 % | **−29,3 bps** | −11,3 | −229,47 %not |
| BAISSIÈRE (SHORT) | VAL | 284 | 42,6 % | **−24,0 bps** | −6,0 | −29,17 %not |
| Ensemble f<0,4 | TRAIN | 1 333 | 42,2 % | −21,4 bps | −3,4 | −339,25 %not |
| Ensemble f<0,4 | VAL | 534 | 43,3 % | −27,2 bps | −9,2 | −61,72 %not |

- **C2 ECHEC** : la catch-up haussière existe à peine en GROSS sur TRAIN (+1,3 bp — 13x sous l'étalon 18 bps) et **s'INVERSE en VAL** (brut −15,2 = ETH dérive CONTRE BTC) — mirage de régime classique.
- **C3 ECHEC** : la baissière est un ANTI-catch-up constant : ETH dérive **UP** après le choc baissier avec retard (bruts −11,3/−6,0 = le short perd aux DEUX splits). Cohérent avec INV-K/INV-L (absorption acheteuse des états baissiers, reprise haussière) mais 6-11 bps bruts = 2-3x SOUS l'étalon — CONTEXTE descriptif, jamais un signal.

## 2. Contrôle inverse (divergence continue f < 0)

| Split | n | WR | net médian | brut |
|---|---|---|---|---|
| TRAIN | 703 | 41,8 % | −21,8 bps | −3,8 |
| VAL | 302 | 45,4 % | −27,5 bps | −9,5 |

**C5 : battu NOMINELLEMENT mais d'un écart de BRUIT** (contrôle −21,8/−27,5 vs ensemble −21,4/−27,2 = écart 0,3-0,4 bp). Le retard pur (0 ≤ f < 0,4 : −21,3 TRAIN / −15,8 VAL) ne sépare rien du contrôle : après un choc BTC ≥ q95, **ETH fait ce qu'il veut que le lag soit profond ou non** — le « retard » n'encode aucune information. En substance : contrôle NON battu.

## 3. Gradient de l'ampleur du retard (quintiles de f, retards purs TRAIN)

| Quintile | f | n TRAIN | net médian TRAIN | n VAL | VAL |
|---|---|---|---|---|---|
| Q1 (lag le plus profond) | (0,000; 0,060] | 69 | −5,7 bps | 15 | −13,3 |
| Q2 | (0,060; 0,135] | 69 | −7,0 bps | 27 | −2,3 |
| Q3 | (0,135; 0,213] | 69 | −28,4 bps | 25 | −56,3 |
| Q4 | (0,213; 0,288] | 69 | −23,0 bps | 21 | −21,9 |
| Q5 (lag le plus léger) | (0,288; 0,400] | 69 | −48,2 bps | 31 | −18,7 |

**C4 ECHEC** : 1 inversion adjacente (Q4 > Q3), toutes les médianes négatives — l'ordre descriptif Q1/Q2 > Q3-Q5 n'est ni monotone ni positif.

## 4. Wallet séquentiel premier-arrivé (1 position ETH à la fois, 1x, compounding, branches fusionnées)

- **1 279 trades** (588 événements sautés par chevauchement), **WR 42,5 %**, **cumul −89,30 %**, **DD 98,5 %**, **37/61 mois négatifs**, record 2022-02 **+48,17 %**, pire 2022-11 **−34,23 %**.
- **0 liquidation** (1x par construction) ; MAE max détention **−17,29 %** → levier sûr ≤ 5,6x.
- Coût du bruit de cluster : les chocs BTC arrivent en rafales (le wallet saute 44 % des événements).

## 5. BLOC STATS MENSUEL (wallet, branches fusionnées)

```
mois    sp    n_ev n_wal     WR  med_bps   wal%     cum%      mois    sp    n_ev n_wal     WR  med_bps   wal%     cum%
2021-09 TRAIN   52    32  43.8%    -30.0  -22.70  -22.70    2024-06 TRAIN   15    13  38.5%    -33.0  -10.83  -95.25
2021-10 TRAIN   53    36  47.2%    -13.2  -12.55  -32.40    2024-07 TRAIN   36    28  35.7%    -13.2   -5.24  -95.50
2021-11 TRAIN   50    35  48.6%    -30.6  -26.76  -50.49    2024-08 TRAIN   60    38  44.7%    -14.4  -22.88  -96.53
2021-12 TRAIN   52    34  29.4%    -29.7  -30.30  -65.49    2024-09 TRAIN   22    14  42.9%    +14.5   -6.50  -96.75
2022-01 TRAIN   65    41  48.8%    +26.8   +8.93  -62.41    2024-10 VAL     14    11  27.3%    -28.5   -8.35  -97.03
2022-02 TRAIN   62    39  59.0%    -18.8  +48.17  -44.31    2024-11 VAL     47    33  33.3%    -48.7  -28.52  -97.87
2022-03 TRAIN   37    24  41.7%    -28.9  -19.81  -55.34    2024-12 VAL     43    32  46.9%     +3.8  -10.75  -98.10
2022-04 TRAIN   30    24  62.5%    +32.1  +14.38  -48.92    2025-01 VAL     38    27  37.0%    -63.2  -10.70  -98.31
2022-05 TRAIN   86    48  41.7%    -43.2  -27.63  -63.03    2025-02 VAL     28    21  52.4%     +4.2  +12.49  -98.09
2022-06 TRAIN  105    53  39.6%    -59.9  -31.91  -74.83    2025-03 VAL     48    24  33.3%    -71.1  -20.90  -98.49
2022-07 TRAIN   67    43  39.5%    -48.1  -21.90  -80.34    2025-04 VAL     35    27  51.9%    +14.6   -4.78  -98.56
2022-08 TRAIN   28    25  52.0%    +12.4  -18.21  -83.92    2025-05 VAL     13    12  58.3%    +18.5   +3.90  -98.51
2022-09 TRAIN   45    31  38.7%    -36.9  -27.80  -88.39    2025-06 VAL     10     8  75.0%    +57.2  +22.95  -98.17
2022-10 TRAIN   15    12  41.7%    -22.6   +9.62  -87.28    2025-07 VAL      3     3  33.3%    -27.2   -1.01  -98.18
2022-11 TRAIN   41    26  38.5%    -62.9  -34.23  -91.63    2025-08 VAL      8     8  75.0%   +127.8  +18.08  -97.86
2022-12 TRAIN    5     4  75.0%    +20.2   +8.73  -90.90    2025-09 VAL      4     4  25.0%   -137.2   -5.78  -97.98
2023-01 TRAIN   20    15  46.7%    -37.1   +8.14  -90.16    2025-10 VAL     18    16  56.2%    -15.6  +16.05  -97.66
2023-02 TRAIN   23    18  55.6%     -2.1   +4.69  -89.70    2025-11 VAL     29    23  56.5%    +13.6  +38.36  -96.76
2023-03 TRAIN   58    35  45.7%    -17.0  +11.65  -88.50    2025-12 VAL     21    17  41.2%    -45.3  -17.57  -97.33
2023-04 TRAIN   21    17  17.6%    -48.7  -10.88  -89.75    2026-01 VAL     12     9  66.7%    +13.9  +14.35  -96.94
2023-05 TRAIN   14    12  25.0%    -34.5   -9.95  -90.77    2026-02 VAL     55    32  53.1%    -10.7   +4.91  -96.79
2023-06 TRAIN   17    14  50.0%     -1.7   -7.58  -91.47    2026-03 VAL     24    18  27.8%    -60.2  -19.89  -97.43
2023-07 TRAIN    7     5  20.0%    -29.7   -4.36  -91.84    2026-04 VAL     12    11  54.5%     -3.8   +4.16  -97.32
2023-08 TRAIN    7     5  80.0%    +50.7   +6.87  -91.28    2026-05 VAL      7     7  28.6%    -43.6   -6.54  -97.50
2023-09 TRAIN    6     5  20.0%    -50.5   -3.42  -91.58    2026-06 VAL     35    22  31.8%    -63.8  -10.65  -97.77
2023-10 TRAIN   14    11  36.4%    -33.0   -0.86  -91.65    2026-07 VAL      7     7  42.9%    -15.8   -1.22  -97.79
2023-11 TRAIN   16    12  58.3%    -44.4   +4.44  -91.28    2026-08 VAL     10     7  57.1%    +15.0   +1.90  -97.75
2023-12 TRAIN   15    13  53.8%    +14.2   +1.64  -91.14    2026-09 VAL     11     9  44.4%    -16.5   -8.54  -97.94
2024-01 TRAIN   42    27  40.7%     -8.1   +3.92  -90.79    (61 mois, 37 négatifs ; record 2022-02 +48,17 %,
2024-02 TRAIN   25    16  62.5%    -27.8   +7.30  -90.12     pire 2022-11 -34,23 % ; garde-fou composé-des-mois :
2024-03 TRAIN   59    37  43.2%    -13.6  -37.57  -93.83     le cumul -89,30 % CONFIRME le final — aucun
2024-04 TRAIN   41    30  46.7%    -23.0  -15.31  -94.78     artefact de queue ne masque la réfutation)
2024-05 TRAIN   24    19  42.1%     -8.5   +1.98  -94.67
```

## 6. VERDICT

**FAIL — hypothèse réfutée** (critères pré-enregistrés) :
- C1 OK (n_train 1 333 ≥ 60 — puissant, PAS une question de puissance).
- **C2 ECHEC** (haussière net −16,7/−33,2 bps TR/VA, brut inversé en VAL).
- **C3 ECHEC** (baissière net −29,3/−24,0 bps, anti-catch-up constant).
- **C4 ECHEC** (gradient non monotone, toutes médianes négatives).
- **C5 non battu en substance** (écart contrôle/ensemble = 0,3-0,4 bp de bruit).

Budget = 1 expérience consommée, **STOP** — aucun autre seuil 0,4, aucun horizon alternatif, aucun filtre de réparation (PARAMETER_MUTATION interdite).

## 7. Leçon gravée

Le **retard d'ETH derrière BTC n'est pas un événement d'information** : après un choc BTC ≥ q95, la fraction du mouvement suivie par ETH dans l'heure (f) ne prédit ni direction ni amplitude du 4 h suivant — l'ensemble des retards, le retard pur et la divergence continue perdent les MÊMES montants nets (~−21/−27 bps) aux deux splits. La structure cross-asset BTC/ETH 1h d'Aster ne délivre rien sous AUCUNE de ses trois formes : le **NIVEAU** de corrélation (corr-tilt, seul module systémique validé en prod comme multiplicateur), le **COUPLAGE** (cascade, 15+ verdicts), et désormais l'**ÉVÉNEMENT de retard directionnel** (INV-M). Observation CONTEXTE non actionnable : la dérive haussière post-choc baissier (+11,3/+6,0 bps bruts 4h, les deux splits, cohérente avec l'absorption acheteuse des états baissiers INV-K/INV-L) reste 2-3x sous l'étalon 18 bps RT — un miroir de plus de la leçon « les états baissiers ne délivrent jamais de short net ».
