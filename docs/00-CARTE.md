# 🗺️ CARTE DU PROJET — un seul endroit pour tout trouver

> Mise à jour : 01/10/2026 (nettoyage post-merge). Si un fichier bouge, cette carte bouge.
> Doc d'architecture complète : `docs/02-architecture.md`.

## 🏆 LA MACHINE & LE REGISTRE (l'état de la stratégie)

- **Le portefeuille officiel** : `the_machine.py` (câblé nocturne) —
  **4 flux** : cascade majeurs gated AL Score + sizing vol-inverse,
  cascade memecoins 1x, survivor long 1x, vol_spike_6h (câblé 27/09).
- **Chiffres backtest (référence de table, pas une preuve)** : main
  **+3 905 %/an @ DD 24,8 %, 0 liquidation** ; QUBO joint poids×levier
  **+5 082 %/an @ DD 23,3 %, record +83,7 %** (marge MAE 9 % surveillée).
  Table des 3 configs : `docs/21-goal-performances.md`.
- **⚠️ Verdict T8 (30/09)** : ces **ABSOLUS sont des artefacts de fenêtre /
warm-up DB** (même moteur → +651 % → +3 905 % selon l'état de la base ;
cascade 10x liquidée dans 6/7 régimes deep). Les **RELATIFS** (ordre des
  flux, structure des gates) tiennent. Le paper forward reste le seul juge
  — détails et décisions au registre `docs/20`, section 30/09.
- **La règle gravée** : levier ≤ 100/(maxMAE + 0,5) — MAE max gated 7,84 %
  → 11x = mort à 8,59 %, marge 9 %, moniteur nocturne intégré.
- **Le candidat qualité** : cascade ∩ funding-rank-bas — WR 81 %, DD 5,4 %,
  0 liq, en accumulation forward (~2 trades/mois).
- **Le registre vivant** (VALIDÉ/CANDIDAT/CONTEXTE/NUL, chiffres et dates) :
  `docs/20-registre-indicateurs.md`.
- **La carte des scripts** : `scripts/README.md` — couche institutionnelle
  fine 27-28/09 : murs (`wall_detector.py`), prints (`aster_blocktrades.py`,
  timer 15 min), réplication derek518 (`replication_derek` dans
  `fomo_paper_forward.py`).

## 🌐 LE DOMAINE OPENMARKET x501 (intégré le 30/09)

Programme **100 $ → 50 100 $ en 12 mois** (×501, DD ≤ 25 % strict, zéro
intervention).

| Doc | Rôle |
|---|---|
| `docs/25-openmarket-x501.md` | mission, chiffres officiels, doctrine, roadmap |
| `docs/26-openmarket-donnees.md` | entrepôt om_v27 (226 800 doublons purgés, index UNIQUE) |
| `docs/27-pouvoirs-kscript.md` | registre d'exploitation kScript |
| `docs/28-protocole-ab-x501.md` | A/B pré-enregistrés vagues 1-2 (+ MK6) |
| `docs/29-fill-maker-mesure.md` | mesure fill maker — candidat v21 en attente de review |
| `docs/30` … `docs/33` | bancs locaux (flux, absorption, réfs liquidité, OI 1h) |

**Exploitation kScript (canonique, vague 3 activée)** : **40/53 = 75,5 %**
(sources premium 7/8, orderbook 2/3, broker 15/16). Famille analyse CLOSE
après les bancs vagues 5–8 (KILL massifs, plomberie prouvée, zéro look-ahead).

**MC v20 (chiffres officiels, baseline 01/10)** : maker δ=2 médiane **468,4 $**
(P(250) 73,0 %) vs taker **272,7 $** (P(250) 57,2 %) — **+71,8 % de médiane
maker** ; x501 @ 36 m 21,3 % vs 5,8 %. Règle : +2 bps de coût/côté ≈ −20 à
−28 % de médiane.

**⚠️ Révision exécution EN ATTENTE DE REVIEW (`docs/29`)** : la mesure
reproductible du fill maker réfute l'hypothèse d'entrée v20 (delta réel
+0,375 bps à δ=2/TTL=2, fallback −88,6 bps, biais concentré sur A4).
Candidat v21 : médiane **306,2 $** (TTL=2) / **364,0 $** (TTL=6, +33,6 % vs
taker). Les chiffres officiels restent **v20** tant que la review n'a pas
validé.

Code & études : `scripts/studies/x501_openmarket/` (versions maker `_MK`,
audit `x501_exploit_audit.py`). Livrables : `docs/reference/openmarket-x501/`.
Baseline : `reports/openmarket-x501-baseline-2026-10-01.md`.

**Pivot 30/09** : recherche Aster/FOMO **gelée** au profit d'OpenMarket
(les collecteurs continuent, plus d'effort de recherche sur ces axes).

## 🔁 LES COLLECTEURS QUI TOURNENT 24/7 (systemd user)

| Service | Rythme | Rôle |
|---|---|---|
| `aster-depth-collector` | 24/7 WS/REST | Carnets d'ordres → `depth.db` (15 symboles) — veille inhibée (continuité 14 j tir 06-07), watchdog anti-stall |
| `aster-liq-collector` | 24/7 WS | Liquidations → `klines.db:liq_events` |
| `fomo-ws-daemon` | 24/7 | Socket natif prod-api : prix, swaps, thèses, `pre_graduated_tokens`, MC samples |
| `fomo-tick-collector` | 24/7 | Ticks fomo → 1m OHLCV (flock anti-orphan, filtre QUOTE_MINTS) |
| `fomo-browser` | permanent | Chromium caché (special:fomo) + CDP :9222 — session JWT |
| `fomo-rest-collector` | 30 min | Historique/snapshots REST → `fomo_rest.db` |
| `fomo-paper-forward` | 15 min | Ledger forward des lancements |
| `fomo-mobula-topup` | 15 min | Rattrapage bougies mobula sans navigateur |
| `oi-collector` | 15 min | OI Aster → `klines.db:oi_history` |
| `aster-blocktrades` / `aster-premium` | 15 min | Gros prints + premium/funding |
| `derek-watch` | 1 min | Swaps derek518 via REST |
| `fomo-swaps-fresh` | 1 h | Page 1 des 13 baleines |
| `aster-health` / `fomo-health` | 5 min | Watchdogs (sondes + alertes sur transition) |
| `trading-agent-nightly` | 03h00 (65 steps) | Nocturne ASTER (caches, klines, machine, campagne, ménage) |
| `x-nightly` | 03h21 (20 steps) | Nocturne X (harvest, scores, rotation, registre) |
| `fomo-nightly` | 03h55 (9 steps) | Nocturne FOMO (garde-fenêtre, radar, ondes, flows) |
| `trading-agent-registre-noon` | 14h00 | Récolte X + liste privée + OI + scoring |

## 🤖 LES AGENTS (`.zcode/agents/`)

`quant-researcher.md` · `fomo-data-engineer.md` · `bug-hunter.md` ·
`discord-bot.md` — mode parallèle codifié dans `AGENTS.md`.

## 📜 SCRIPTS VIVANTS par domaine (`scripts/`)

### Aster — journée du 30/09 (chaîne T1-T13)
- Couche data refaite : moteur diff-depth EN PROD, 4 WS natifs, bulk bapi
  642 symboles, watchdogs, rétention — `docs/24` (P1-P6 FAIT)
- Backtest arrière possible (klines sans trou jusqu'à 2021-09, 9,1 M bougies)
- **Bug du harnais corrigé** (pertes de stop + frais omis → accounting MTM) :
  nocturne 01/10 = 1re campagne honnête
- **T8** : machine codifiée = artefact de fenêtre (voir section Machine)
- Gate fund7 > 0,5 bps/8h **pré-enregistré** (mécanisme P3, N=61) — verdicts à 90 j
- Domaine OpenMarket x501 mergé (PR #1-4) ; recherche Aster/FOMO gelée

### Aster — données & indicateurs
- `fetch_klines.py` / `fetch_deep_klines.py` — klines (standard / 1 an profond)
- `refresh_aster_cache.py`, `funding_scanner.py`, `carry_hedged.py`, `basis_guard.py`
- `aster_oi_history.py` — OI historique maison (nuits+midi)
- `aster_live.py` — terminal temps réel WS
- `aster_absorption.py`, `depth_heatmap.py`, `flow_snapshot.py`, `depth_collector.py`

### X.com (registre & veille)
- `x_harvest.py`, `x_rotation.py`, `x_list_build.py`, `fetch_x_posts.py`
- `score_x_calls.py`, `x_aster_pulse.py`, `aster_convergence.py`

### fomo.family
- `fomo_harvest.py`, `whale_radar.py`, `wave_detector.py`
- `memecoin_pulse.py`, `listing_watcher.py`, `registre_board.py`

### Backtests & fiabilité
- `backtest_indicators.py` — campagne v5 (baseline anti-drift, SELFTEST)
- `aster_indicators.py`, `slippage_measured.py`, `housekeeping.py`
- `run_tests.py --fast` — valider avant de commit

### Compte & clés
- `save_aster_key.py` — credentials → `.env` (TESTNET pour l'instant)
- `aster_account.py` — sonde EIP-712 (attend clé privée API wallet)

## 🗄️ ENTREPÔTS (`data/`)
- `warehouse/klines.db` — domaine ASTER (klines, oi_history, liq_events,
  funding, block_trades, premium, paper_trades, signal_events)
- `warehouse/depth.db` — carnets (54 M bins, 15 symboles, 30 s)
- `warehouse/x_posts.db` — registre X + `x_pressure`
- `fomo/fomo.db` — base HOT daemon (ticks, MC samples, tokens, OHLCV, pre_graduated)
- `fomo/fomo_swaps.db` · `fomo/fomo_rest.db` · `fomo/fomo_mobula.db` · `fomo/fomo_paper.db`

## 📊 RAPPORTS (`reports/`) — rétention automatique (housekeeping)
`whale-radar` (7j) · `x-aster-pulse` (7j) · `aster-convergence` (7j) ·
`memecoin-pulse` (3) · `backtest-campagne-v2` (5) · `registre-honnetete` (3) ·
`depth-heatmap` (9) · `etat-projet.md` (réécrit chaque nuit)

## 📦 ARCHIVES (ne pas confondre avec le vivant)
- `scripts/archive/` — scripts retirés
- `docs/archive/` — analyses PDF époques passées
- `backend/.../legacy_discovery_batches/` — CSV juin (source `legacy_lanes.db`)

## 📚 DOCS (`docs/`)
`03-methodology.md` (pré-enregistrement) · `20-registre-indicateurs.md` ·
`21-goal-performances.md` · `24-donnees-aster.md` · `25`–`33` (OpenMarket)

## 🚫 RÈGLES
- Aucun ordre autonome — exécution = le user seul
- Tout signal : backtest pré-enregistré AVANT de croire (`docs/03-methodology.md`)
- Baseline anti-dérive : un short aveugle gagne 71 % à +90j
- Les clés vivent dans `.env` (git-ignoré) — TESTNET pour l'instant
- Main protégée : changements uniquement via PR
