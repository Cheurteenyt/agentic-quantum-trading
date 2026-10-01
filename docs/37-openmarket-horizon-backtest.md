# 37 — OpenMarket : l'horizon de backtest « depuis le début de l'actif » (v29)

**Règle verrouillée (02/10/2026)** : tout backtest openmarket part du
**début de l'actif** — c'est-à-dire du listing du contrat perp USDT du
symbole, mesuré, pas déclaré. Plus jamais d'horizon arbitraire tronqué
(400 j, 733 j) : chaque symbole est backtesté sur sa profondeur réelle,
et les études multi-symboles déclarent explicitement la fenêtre commune
qu'elles utilisent. La limite n'est **pas l'API** : Bybit kline 1h est
paginable illimité et Binance fapi aussi — la limite est la **date de
listing** du perp sur chaque venue.

## 1. Les planchers mesurés (sonde `x501_probe_floor_v29.py`)

Méthode : bisection par fenêtre de 1 jour sur `kline 1h` Bybit et
Binance fapi + `open-interest 1d` Bybit + `fundingRate` Binance, 12
symboles. Résultat brut : `floor_v29.json`.

| Symbole | kline 1h Bybit | kline 1h Binance | OI 1d Bybit | Funding Binance | Années (venue profonde) |
|---|---|---|---|---|---|
| BTCUSDT | 2020-03-25 | **2019-09-08** | 2020-08-04 | 2019-09-10 | **7,07** |
| ETHUSDT | 2021-03-14 | **2019-11-27** | 2020-10-21 | 2019-11-27 | **6,85** |
| XRPUSDT | 2021-05-13 | **2020-01-06** | 2021-05-13 | 2020-01-06 | **6,74** |
| LINKUSDT | 2020-10-21 | **2020-01-17** | 2020-10-21 | 2020-01-17 | **6,71** |
| BNBUSDT | 2021-06-29 | **2020-02-10** | 2021-06-29 | 2020-02-10 | **6,64** |
| ADAUSDT | 2021-03-18 | **2020-07-03** | 2021-03-18 | 2020-01-19 | **6,25** |
| DOGEUSDT | 2021-07-03 | **2020-07-31** | 2021-06-02 | 2020-07-10 | **6,15** |
| SOLUSDT | 2021-10-14 | **2020-09-14** | 2021-06-29 | 2020-09-13 | **6,05** |
| AVAXUSDT | 2021-09-15 | **2020-09-23** | 2021-09-15 | 2020-09-22 | **6,03** |
| APTUSDT | 2022-10-19 | 2022-10-19 | 2022-10-19 | 2022-10-18 | **4,00** |
| 1000PEPEUSDT | 2023-05-03 | 2023-05-05 | 2023-05-03 | 2023-05-05 | **3,42** |
| SUIUSDT | 2023-05-03 | 2023-09-14 | 2023-05-03 | 2023-05-03 | **3,42** |

Trois horizons officiels en résultent :

- **Pool 12/12 (fenêtre commune)** : **3,42 ans** depuis 2023-05-03
  (SUI et 1000PEPE imposent le plancher sur Bybit) — +70 % par rapport
  aux 2,01 ans utilisés jusqu'ici (734 j).
- **« 6 ans »** : validé sur **9/12 symboles** (BTC, ETH, BNB, XRP, ADA,
  LINK, DOGE, SOL, AVAX via Binance) ; exclus APT (4,0), 1000PEPE
  (3,4), SUI (3,4).
- **Plafond absolu** : **7,07 ans** (BTC, listing Binance 2019-09-08) —
  aucune donnée perp USDT antérieure n'existe chez ces venues.

## 2. La base deep (collecteur `x501_collect_deep_v29.py`)

- **1 041 871 barres klines 1h** : Bybit `bb_kline_1h_deep`
  (528 018 lignes, 12 symboles jusqu'au plancher Bybit) + Binance
  `bn_kline_1h_deep` (513 853 lignes, 9 symboles jusqu'au plancher
  Binance).
- **76 479 fundings** Binance (`bn_funding_deep`) complétés vers le
  plancher de chaque symbole (les 6 000 points/symbole de v21 plafonnaient
  à 2021-04 ; la topup couvre 2019-09 → 2021-04, ts en **secondes** dans
  cette table — piège d'unité documenté et corrigé).
- Hygiène d'ingestion : INSERT OR IGNORE sous contrainte UNIQUE(symbol,
  ts), pacing weight-aware Binance (0,42 s — weight 10/page, budget
  2 400/min), backoffs 429/418 (20→120 s), reprise incrémentale par
  `MIN(ts)`.
- **Audit** : **0 trou horaire** dans les deux tables (plus grand écart
  < 2 h partout), cohérence cross-venue sur l'overlap Bybit/Binance :
  **médiane 1,2–4,2 bps, p99 ≤ 16,3 bps** sur les 9 symboles communs —
  la baseline v21/v27 (Bybit) se transpose à Binance sans recalage.
- Les DB restent **locales et git-ignorées** (`data_x501/`, docs/26) ;
  le repo porte les collecteurs versionnés + les JSON de résultats.

## 3. La baseline 6 ans (`x501_baseline_6y_v29.py`)

513 637 observations f24 (pool 9 symboles Binance, `f24 = close[t+24h]/
close[t] − 1` en bps), protocole v27 inchangé (pas de signal, mesure
descriptive) :

- **Stationnarité, split 60/40 chrono GLOBAL** (obs triées par ts, jamais
  empilées par symbole — leçon ml_deep v27) : train **+33,8 bps** → test
  **+8,4 bps**. Même signe (pas de KILL au sens du protocole), mais la
  contraction ×4 est réelle et sa coupure tombe au 2024-02-22.
- **Par année (BTC)** : 2020 +45,2 / 2021 +22,7 / 2022 **−23,1** (bear) /
  2023 +28,8 / 2024 +25,1 / 2025 **+0,6** / 2026 **+0,8** bps. Le biais
  long f24 s'est **évaporé depuis 2025** ; 2022 reste le seul signe
  négatif du cycle.
- **Funding APR (BTC)** : 17,2 % (2020) → **30,6 %** (2021) → 4,2 %
  (2022) → 11,9 % (2024) → **5,1 % (2025) / 2,9 % (2026)** — le carry
  s'est contracté ×6 depuis 2021.
- **MFE48 médian (BTC)** : 3,69 % (2021) → **1,76–1,79 %** (2025-2026) —
  la matière première des sorties TP s'est contractée ×2.
- 2019 (2743 h de BTC seulement) : f24 −25,2 bps — le tout début du
  marché perp était un régime bear court, intégré pour mémoire.

**Lecture officielle** : la fenêtre de calibration du MC v20 (les 23
derniers mois) est le **PIRE CAS du cycle complet 2019-2026** — f24,
funding et MFE48 y sont simultanément à leur plus bas. La trajectoire
officielle (100 $ → 50 100 $, bande 216-642 $ à 12 m selon les coûts)
est donc calibrée sur le régime le plus défavorable du marché, pas le
plus favorable. Le re-chiffrement complet sur 6 ans exige le portage du
moteur d'alphas (pool P1) sur les tables deep — chantier séparé, non
engagé dans cette vague. La règle « depuis le début de l'actif » s'applique
dès maintenant à toute nouvelle étude du domaine.

## 4. Artefacts

- `scripts/studies/x501_openmarket/x501_probe_floor_v29.py` + `floor_v29.json`
- `scripts/studies/x501_openmarket/x501_collect_deep_v29.py` + `collect_deep_v29.json`
- `scripts/studies/x501_openmarket/x501_baseline_6y_v29.py` + `baseline_6y_v29.json`
- DB locale : `om_v27.db` (tables `bb_kline_1h_deep`, `bn_kline_1h_deep`,
  `bn_funding_deep` étendue) — git-ignorée.
- Collecteur d'observation associé : `x501_observe_om_v29.ks` (zéro ordre).
