# 40 — OpenMarket : le harnais v8 porté sur la base deep (40 symboles, v31)

**Date : 02/10/2026.** Application directe de la politique docs/37
(« tout backtest part du début de l'actif », docs/37) au harnais OFFICIEL v8 :
40 perps Binance USDT-M, gates IS/OOS, gate volatilité BTC D1 (L1),
échelle de sortie (L2). Ce chantier complète le re-chiffrement v30
(moteur 8 symboles) par le pool que la trajectoire officielle utilise
réellement — le pool P1 v8 et ses dérivés MC.

## 1. La base deep étendue de 9 à 40 symboles (`x501_collect_deep40_v31.py`)

Le collecteur v29 (API backward, pacing 0,42 s) est remplacé pour Binance
par le **CDN Binance Vision** (zips mensuels + quotidiens, sans
rate-limit, 4-5 s/symbole) avec le **volume taker natif dès l'origine**
(champ 10 des klines fapi), compléments API fapi blindés (backoffs
20→120 s) sur les trous internes et les plages antérieures au premier
zip (BTC 2019-09→2019-12, ETH 2019-11/12).

| Table | Volume | Contenu |
|---|---|---|
| `bn_kline_1h_deep` | **1 817 324 barres / 40 symboles** | klines 1h Binance depuis le listing de chaque actif (BTC 2019-09-08 → 2026-09-30), taker_buy 100 % |
| `bb_kline_1h_deep` | 528 077 barres / 12 symboles | klines 1h Bybit depuis le listing (backups cross-venue) |
| `bn_funding_deep` | 238 616 points / 40 symboles | funding 8 h Binance depuis le listing, **ts en SECONDES** (piège d'unité v29) |

QA (`qa_deep40_v31.py`, **15 contrôles, 0 échec**) : 0 trou horaire > 2 h
**sauf un trou RÉEL documenté** (ICPUSDT 2022-08-31 23:00 → 2022-09-27
01:00, 627 h — vérifié absent de l'API Binance elle-même, suspension de
trading) ; 0 NULL taker ; funding contigu à 8 h pile partout ;
cross-venue overlap médiane **1,8 bps** (max méd 4,2, p99 ≤ 16,3) — la
cohérence v29 se transpose à l'univers élargi.

## 2. Le portage fidèle (`x501_v8_scale_deep_v31.py`)

Généré par **transformation contrôlée** de `x501_v8_scale.py` (chaque
remplacement vérifié par assertion, moteur copié bit à bit) :

- le chargement CSV 36 mois est remplacé par la lecture DB deep
  (`bn_kline_1h_deep` + `bn_funding_deep`, ts funding secondes → ms) ;
- les **indicateurs (SymData patché v5 : e1z, atr1, vol1ma, adx1,
  atr1dpct), le moteur `run_stream` (harnais v7), les règles figées et
  la séquence de décision sont INCHANGÉS** : L1 gate θ ∈ {p50..p80}
  calibré sur IS uniquement, seuils IS n≥40 / OOS n≥20 / E[R] ≥ +0,10 /
  PF ≥ 1,25, sorties V0-V3 figées a priori, checkpoints identiques ;
- fenêtre de fait : **2019-11-08 → 2026-09-30 = 82,8 mois** (BTC deep,
  warmup 60 j + 24 barres), frontière IS/OOS **60 % chrono :
  2023-12-28**. Chaque alt entre dans le pool à son listing avec son
  propre warmup (comportement v8, qui devient non trivial en deep).

## 3. Verdicts des leviers figés (séquence v8 inchangée)

- **Phase A (V0, sans gate)** : 855 trades. Sat alts : IS +0,059 /
  OOS **+0,173** (PF 1,35) — l'OOS dépasse l'IS, signe d'un edge non
  saturé sur la période récente. Main BTC/ETH : IS −0,212 / OOS +0,128
  (A1 inverse entre blocs — même instabilité qu'en v8/v9).
- **Phase B (L1 gate volatilité)** : **REJETÉ 4/4** — p50 OOS PF 1,14
  (< 1,25), p60 négatif, p70/p80 n insuffisants. Le gate ATR D1 ne
  généralise pas sur 82,8 mois : il n'apportait rien hors fenêtre courte.
- **Phase C (L2 sorties)** : **V3 retenu** (TP1 +1,0R) : IS +0,085 /
  somme +24,2 R (> V0 +0,059/+16,3), OOS +0,182 / PF 1,48 (≥ seuils).
  La sortie précoce paie sur l'historique long, à l'opposé des runners
  V1/V2 (pensés sur 2023-2026).

## 4. Le pool v8 deep et le MC v31

**POOL : 868 trades (284 main / 584 sat), E[R] total +0,093**
(main +0,005 / sat +0,135), WR 52,2 %, PF 1,21, cadence 10,5/mois
(20,2/mois sur les 12 derniers mois). Par alpha : **A3 +0,210**
(PF 1,75, n=164) et **A4 +0,119** (PF 1,27, n=525) portent le pool ;
A1 −0,093 (n=179) le pénalise (déjà neutralisé en production : A1
premium seulement, et MC à cadence/pondérations fixées).

| Année | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| E[R] | +0,013 | **−0,545** | +0,162 | +0,018 | +0,201 | **−0,027** | **+0,308** |

La contraction vs la fenêtre 34 mois du pool v8 officiel
(E[R] +0,180 → **+0,093**, ÷1,9) est **2,4× plus douce** que celle du
moteur 8 symboles (v30 : ÷4,5) — l'univers 40 symboles (A4/A3 sur 38
alts) dilue la dépendance au régime BTC et restaure une part d'edge.

**MC v31** (`x501_mc_v31.py`, noyau v12 bit à bit, 12 000 chemins,
36 mois, seed 7, scénarios de coûts v20/maker_v27) :

| Scénario | bps/côté | Médiane 12 m | IQR | P(≥250 $) | P(50 100 $)@12m |
|---|---|---|---|---|---|
| W0 référence deep | 0,0 | **146,7 $** | [100 ; 253] | 30,3 % | **0,00 %** |
| W4 maker d5 | 1,7 | 130,1 $ | [93 ; 213] | 23,8 % | 0,00 % |
| W1 maker d2 central | 2,0 | 127,9 $ | [92 ; 207] | 22,8 % | 0,00 % |
| W2 taker réel | 6,1 | 104,7 $ | [83 ; 150] | 11,8 % | 0,00 % |
| W3 stress | 8,2 | 97,5 $ | [81 ; 133] | 8,3 % | 0,00 % |

Audits : T2 pire cas (0 rupture, maxDD **25,000000 %**) OK ; T3
reproductibilité bit à bit OK. **Le cap DD 25 % reste inviolé sur
12 000 chemins × 5 scénarios ; la cible 50 100 $ à 12 mois reste hors
portée sur l'historique complet** (médiane 146,7 $ — le meilleur
re-chiffrement honnête jamais obtenu, +25 % vs v30 grâce à l'univers
40 symboles, mais 4,4× sous la cible).

## 5. Artefacts

- `x501_collect_deep40_v31.py` + `collect_deep40_v31.json` — collecte Vision 40 symboles
- `qa_deep40_v31.py` — QA base deep + pool (15 contrôles, PASS)
- `x501_v8_scale_deep_v31.py` — portage du harnais v8 (transformation contrôlée)
- `research_v8_deep.json` + `trades_v8_deep.csv` — le pool 868 trades (le pool pkl reste local, git-ignoré)
- `x501_mc_v31.py` + `mc_v31.json` — MC sur pool deep
- Dépendances locales (non versionnées, workspace) : `om_v27.db` (tables `*_deep`),
  `x501_alpha_backtest.py`, `x501_engine_v5.py`, `x501_mc_v10/v11/v12.py`,
  `floor_v29.json` — pattern identique au MC v30 (docs/37).
