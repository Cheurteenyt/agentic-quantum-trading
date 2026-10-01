# x501 — HARNAIS v8 SUR BASE DEEP « depuis le début de l'actif » (v31) — 2026-10-02

Application de la politique verrouillée (docs/37, PR #16) au harnais OFFICIEL
v8 : 40 perps Binance USDT-M, gates IS/OOS, gate volatilité BTC D1, échelle
de sortie. Ce rapport documente l'extension de la base deep (9 → 40 symboles),
le portage fidèle du harnais, les verdicts des leviers figés et le
re-chiffrement Monte-Carlo v31.

## 1. Base deep 40 symboles

- Collecte via **CDN Binance Vision** (zips mensuels + quotidiens, sans
  rate-limit) avec volume taker natif, compléments API fapi blindés
  (backoffs 20→120 s) pour les plages antérieures au premier zip et les
  trous internes ; Bybit (12 symboles) reste en API backward.
- **1 817 324 barres 1h Binance / 40 symboles** (BTC depuis 2019-09-08,
  coupure 2026-09-30 23:00) + 528 077 barres Bybit / 12 symboles +
  **238 616 fundings** / 40 symboles (ts secondes).
- QA dédiée (`qa_deep40_v31.py`) : **15 contrôles, 0 échec** — 0 trou
  horaire > 2 h **sauf ICPUSDT 2022-08-31 23:00 → 2022-09-27 01:00
  (627 h, vérifié absent de l'API Binance : suspension réelle)** ;
  0 NULL taker ; funding contigu à 8 h pile ; cross-venue médiane
  **1,8 bps** (max méd 4,2, p99 ≤ 16,3).

## 2. Portage fidèle du harnais v8

`x501_v8_scale_deep_v31.py` est généré par **transformation contrôlée**
du source v8 (assertions sur chaque remplacement) : seul le chargement
des données change (CSV 36 mois → DB deep). Indicateurs (SymData patché
v5), moteur `run_stream`, **règles figées** (L1 gate θ ∈ {p50..p80} IS ;
seuils IS n≥40 / OOS n≥20 / E[R] ≥ +0,10 / PF ≥ 1,25 ; sorties V0-V3) et
séquence de décision sont **bit à bit**. Fenêtre effective :
**2019-11-08 → 2026-09-30 = 82,8 mois**, frontière IS/OOS 2023-12-28 ;
chaque alt entre au portefeuille à SON listing avec SON warmup.

## 3. Verdicts

| Levier | Verdict | Détail |
|---|---|---|
| L1 gate volatilité BTC D1 | **REJETÉ 4/4** | p50 OOS PF 1,14 (< 1,25) ; p70/p80 n insuffisants (14/1) |
| L2 échelle de sortie | **V3 retenu** | IS +0,085 / +24,2 R > V0 ; OOS +0,182, PF 1,48 |

**POOL v8 DEEP : 868 trades (284 main / 584 sat), E[R] +0,093**
(sat +0,135), WR 52,2 %, PF 1,21, cadence 10,5/mois. Par alpha :
A3 **+0,210** (PF 1,75, n=164), A4 +0,119 (n=525), A1 −0,093 (n=179).
Par année : 2021 −0,545 et 2025 −0,027 les deux creux ; 2026 **+0,308**
(+47,1 R, n=153).

Contraction de l'edge vs fenêtre 34 mois : **+0,180 → +0,093 (÷1,9)** —
2,4× plus douce que le moteur 8 symboles (v30 : ÷4,5). L'univers 40
symboles dilue la dépendance au régime BTC.

## 4. MC v31 (noyau v12 bit à bit, 12 000 chemins, 36 mois, seed 7)

| Scénario | bps | Médiane 12 m | IQR | P(≥250 $) | P(50 100 $)@12m |
|---|---|---|---|---|---|
| W0 référence deep | 0,0 | **146,7 $** | [100 ; 253] | 30,3 % | 0,00 % |
| W4 maker d5 | 1,7 | 130,1 $ | [93 ; 213] | 23,8 % | 0,00 % |
| W1 maker d2 | 2,0 | 127,9 $ | [92 ; 207] | 22,8 % | 0,00 % |
| W2 taker réel | 6,1 | 104,7 $ | [83 ; 150] | 11,8 % | 0,00 % |
| W3 stress | 8,2 | 97,5 $ | [81 ; 133] | 8,3 % | 0,00 % |

Audits T2 (0 rupture, maxDD 25,000000 %) et T3 (reproductibilité bit à
bit) **OK**.

## 5. Verdict officiel

- **Le re-chiffrement le plus complet du domaine** (82,8 mois × 40
  symboles, pool officiel du harnais v8) confirme la lecture v30 :
  **P(100 → 50 100 $)@12m = 0,00 % sur l'historique complet** — la
  cible 12 mois n'est pas portée par l'edge stationnaire ; la trajectoire
  x501 reste un objectif de RÉGIME favorable, pas un espoir de moyenne.
- Le cap DD 25 % reste **inviolé partout** — le système de survie tient
  sur 7 ans × 5 scénarios de coûts, 12 000 chemins chacun.
- Le harnais 40 symboles est la **meilleure configuration mesurée à ce
  jour** (+25 % de médiane vs v30) ; les chantiers suivants cohérents :
  exclusion des ères négatives mesurées (2021, 2025) via filtres de
  régime pré-enregistrés, et re-déduplication temporelle des flux
  A3/A4 sat (même protocole anti-mirage v27) avant toute promotion.
