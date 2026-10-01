# 🗺️ CARTE DU PROJET — un seul endroit pour tout trouver

> Mise à jour : 30/09/2026. Si un fichier bouge, cette carte bouge.
> Doc d'architecture complète : `docs/02-architecture.md`.

## 🏆 LA MACHINE & LE REGISTRE (l'état de la stratégie)

- **Le portefeuille officiel** : `the_machine.py` (câblé nocturne) —
  **4 flux** : cascade majeurs gated AL Score + sizing vol-inverse,
  cascade memecoins 1x, survivor long 1x, vol_spike_6h (câblé 27/09) →
  **main : +3 905 %/an @ DD 24,8 %, 0 liquidation** ; 2 candidats QUBO en
  paper forward parallèle (`qubo_forward_tracker.py`) : **QUBO joint
  poids×levier +5 082 %/an @ DD 23,3 %, record +83,7 %** (marge MAE 9 %
  surveillée) — la table des 3 configs : `docs/21-goal-performances.md`.
- **La règle gravée** : levier ≤ 100/(maxMAE + 0,5) — MAE max gated 7,84 %
  → 11x = mort à 8,59 %, marge 9 %, moniteur nocturne intégré.
- **Le candidat qualité** : cascade ∩ funding-rank-bas — WR 81 %, DD 5,4 %,
  0 liq, en accumulation forward (~2 trades/mois).
- **Le registre vivant de tous les indicateurs** (VALIDÉ/CANDIDAT/CONTEXTE/NUL,
  chiffres et dates) : `docs/20-registre-indicateurs.md`.
- **La carte des scripts** : `scripts/README.md` (136 fichiers en 6 groupes,
  la convention de travail) — la couche institutionnelle fine 27-28/09 :
  murs (`wall_detector.py`), prints (`aster_blocktrades.py`, timer 15 min),
  réplication derek518 (`replication_derek` dans `fomo_paper_forward.py`).

## 🌐 LE DOMAINE OPENMARKET x501 (intégré le 30/09)

Le programme **100 $ → 50 100 $ en 12 mois** (×501, DD ≤ 25 % strict,
zéro intervention) — `docs/25-openmarket-x501.md` (mission, chiffres
officiels, doctrine, roadmap) · `docs/26-openmarket-donnees.md`
(l'entrepôt om_v27 audité vert : 226 800 doublons purgés, index UNIQUE) ·
`docs/27-pouvoirs-kscript.md` (l'audit d'exploitation : **40/53 capacités
= 75,5 %** — sources premium 7/8, orderbook 2/3, broker 15/16 ; vagues 1-2
activées, **vague 3 hygiène broker activée**, `docs/28-protocole-ab-x501.md`
= les A/B PRÉ-ENREGISTRÉS des vagues 1-2 (8 runs, dont MK6 TTL=2 vs 6),
3 tests au registre docs/20) · **vague 5 : le banc de test local des flux
dormants (`docs/30`) — le flux taker natif et le funding passés au banc
AVANT tout run kScript : 12/12 cellules KILL au critère AUC** (80 symboles
× 1 092 j = 2 053 975 barres, grille pré-déclarée, plomberie prouvée
vivante ; les pouvoirs data sont désormais TOUS banc-testés : fz, flush
OI, ML, flux, funding) · **vague 6 : le banc d'événements de l'absorption
(`docs/31`) — la structure événementielle passée au banc en proxy klines
AVANT les runs ABS : prime de structure RÉFUTÉE 0/4 (la confirmation est
TARDIVE, le rebond se joue dans la barre de tenue), miroir SHORT
anti-signal, ABS_DEPRIORISE — file de runs recommandée : RI → MK6 → TRAIL
→ ABS**) · **vague 7 : le banc des références de liquidité (`docs/32`) —
vwap de session + volume profile de la veille (les 2 derniers pouvoirs
d'analyse réels, les briques payantes de TradingView) passés au banc AVANT
tout run : grille pré-déclarée de 28 cellules aux DEUX hypothèses
(mean-reversion ET continuation) → 55 KILL / 1 INCONCLU / 0 CANDIDAT sur 56
cellules (2 048 055 décisions, plomberie prouvée vivante AUC 0,91/0,93,
zéro look-ahead par mutation) — la 7ᵉ falsification, la famille analyse de
docs/27 est CLOSE**) · **vague 8 : le banc de l'open interest 1h (`docs/33`)
— la matière première désignée par docs/26 (« OI 1h en tête ») testée en
TÉMOIN DE CONTINUATION — l'hypothèse INVERSE du flush OI déjà tué : capital
brut ΔOI% + mouvement financé signe(r_L)×ΔOI%, × H{24,72} — sur 12 symboles
avec klines ET OI du MÊME exchange (Bybit) → 10/10 KILL (AUC 0,4917–0,5019,
216 000 barres × 749 j, 0 doublon, 0 snapshot absent, plomberie prouvée
vivante détecteur 0,66, zéro look-ahead par mutation double) — la 8ᵉ
falsification, collecteur versionné `x501_collect_oi_v8.py`**) · **vague 9 :
le banc de l'OI en CONTEXTE DE RÉGIME (`docs/34`) — la case ouverte de la
vague 8 fermée : le NIVEAU du capital (z-score roulant 30 j / 90 j, par
opposition au flux ΔOI déjà tué) testé comme conditionneur de la distribution
— l'hypothèse de la théorie du levier H_R1 (capital haut → |fwd| plus grand)
REFUSÉE (3 KILL + 1 INCONCLU, AUC 0,5028–0,5150), direction 4/4 KILL — la 9ᵉ
falsification, 5ᵉ verdict symétrique des familles de positionnement ; le
conditionnel pool P1 franchit le gate de contexte (ΔR +0,469, P = 0,8192 ≥
0,70, n = 181, in-sample + cross-exchange) — filtre candidat au protocole
A/B, jamais promotion depuis un banc**).
falsification, collecteur versionné `x501_collect_oi_v8.py`**).
docs/27 est CLOSE**).
→ ABS**).
OI, ML, flux, funding).
3 tests au registre docs/20).
origin/main
origin/main
origin/main
origin/main
origin/main
**MC v20, SANS haircut gate (01/10), 4 audits verts** : maker δ=2
**468,4 $** (P(250) 73,0 %) vs taker 272,7 $ (P(250) 57,2 %) —
**+71,8 % de médiane pour le maker**, x501 @ 36 m 21,3 % vs 5,8 % ;
règle : +2 bps de coût/côté ≈ −20 à −28 % de médiane.
**⚠ Révision exécution EN ATTENTE DE REVIEW (docs/29)** : la mesure
reproductible du fill maker (surface δ×TTL 2 053 015 tentatives + sélection
sur le pool P1) **réfute l'hypothèse d'entrée v20** (delta réel +0,375 bps,
fallback à −88,6 bps, biais concentré sur A4) → candidat v21 : médiane
**306,2 $** (TTL=2) / **364,0 $** (TTL=6, +33,6 % vs taker). Le code : 12 kScripts + 10 QA **PASS** dans
**306,2 $** (TTL=2) / **364,0 $** (TTL=6, +33,6 % vs taker). Le code : 12 kScripts + 7 QA **PASS** dans
**306,2 $** (TTL=2) / **364,0 $** (TTL=6, +33,6 % vs taker). Le code : 12 kScripts + 6 QA **PASS** dans
= les A/B PRÉ-ENREGISTRÉS des vagues 1-2, 3 tests au registre docs/20).
`docs/27-pouvoirs-kscript.md` (l'audit d'exploitation : **36/53 capacités
= 67,9 %** — sources premium 7/8, orderbook 2/3 ; vagues 1-2 activées).
origin/main
**MC v20, SANS haircut gate (01/10), 4 audits verts** : maker δ=2
**468,4 $** (P(250) 73,0 %) vs taker 272,7 $ (P(250) 57,2 %) —
**+71,8 % de médiane pour le maker**, x501 @ 36 m 21,3 % vs 5,8 % ;
règle : +2 bps de coût/côté ≈ −20 à −28 % de médiane. Le code : 12 kScripts + 6 QA **PASS** dans
origin/main
origin/main
origin/main
origin/main
origin/main
origin/main
`scripts/studies/x501_openmarket/` (versions maker `_MK` = l'exécution de
référence, fill 97,9 % à δ=2 ; l'audit d'exploitation kScript
`x501_exploit_audit.py` ; **vagues 1-2 du plan d'exploitation ACTIVÉES le
01/10 : filtre régime institutionnel sur 5 flux premium + absorption
orderbook native, `docs/27`**). Les livrables : `docs/reference/openmarket-x501/`
(9 PDF + 2 protocoles). Baseline : `reports/openmarket-x501-baseline-2026-10-01.md`
(v20, l'édition 30/09 est conservée pour la trace).
**Pivot 30/09 : la recherche Aster/FOMO est gelée au profit d'OpenMarket**
(les collecteurs continuent, plus aucun effort de recherche).

## 🔁 LES COLLECTEURS QUI TOURNENT 24/7 (systemd user)

| Service | Rythme | Rôle |
|---|---|---|
| `aster-depth-collector` | 24/7 WS/REST | Carnets d'ordres → `depth.db` (15 symboles) — **veille inhibée** (continuité 14 j du tir 06-07), watchdog anti-stall interne |
| `aster-liq-collector` | 24/7 WS | Liquidations → `klines.db:liq_events` |
| `fomo-ws-daemon` | 24/7 | Socket natif prod-api : prix, swaps, thèses, `pre_graduated_tokens`, **MC samples** (`fomo_mc_samples`) |
| `fomo-tick-collector` | 24/7 | Ticks fomo → 1m OHLCV (flock anti-orphan, filtre QUOTE_MINTS) |
| `fomo-browser` | permanent | Chromium caché (special:fomo, no_focus) + CDP :9222 — la session JWT |
| `fomo-rest-collector` | 30 min | TOUTE l'historique/snapshots REST → `fomo_rest.db` (structure déclarative) |
| `fomo-paper-forward` | 15 min | Ledger forward des lancements (`fomo_paper_forward.py`) |
| `fomo-mobula-topup` | 15 min | Rattrapage bougies mobula sans navigateur (`fomo_mobula_topup.py`) |
| `oi-collector` | 15 min | OI Aster → `klines.db:oi_history` (`oi_collector.py`) |
| `aster-blocktrades` / `aster-premium` | 15 min | Gros prints institutionnels + premium/funding |
| `derek-watch` | 1 min | Les swaps de derek518 via REST (l'edge répliqué) |
| `fomo-swaps-fresh` | 1 h | Page 1 des 13 baleines (`fomo_swaps_collector.py`) |
| `aster-health` / `fomo-health` | 5 min | **Les 2 watchdogs** (sondes + alertes sur transition) |
| `trading-agent-nightly` | 03h00 (65 steps) | **Le nocturne ASTER** (caches, klines, machine, campagne, ménage) |
| `x-nightly` | 03h21 (20 steps) | **Le nocturne X** (harvest, scores, rotation, registre X) |
| `fomo-nightly` | 03h55 (9 steps) | **Le nocturne FOMO** (garde-fenêtre, radar, ondes, flows, harvest) |
| `trading-agent-registre-noon` | 14h00 | Récolte X + liste privée + OI + scoring |

## 🤖 LES AGENTS (.zcode/agents/)

`quant-researcher.md` · `fomo-data-engineer.md` · `bug-hunter.md` ·
`discord-bot.md` — le mode parallèle est codifié dans `AGENTS.md`
(dès que ≥ 2 flux indépendants : dispatch en agents parallèles).

## 📜 SCRIPTS VIVANTS par domaine (`scripts/`)

### Aster — la journée du 30/09 (la chaîne T1-T13, les commits 80a4b0e → 9c9d0e6)
- La couche de données refaite : le moteur diff-depth EN PROD (cutover, 0 trou),
  4 WS natifs, le bulk bapi 642 symboles, le compteur de poids, les 2 watchdogs
  (11+4 sondes), la rétention câblée — docs/24 (la carte + la feuille de route P1-P6 FAIT)
- **Le backtest arrière POSSIBLE sur Aster** (klines sans trou jusqu'à 2021-09 —
  9,1 M bougies backfillées) : la règle forward-only ne s'applique pas ici
- **LE BUG DU HARNAIS corrigé** (les pertes de stop jamais comptées + les frais
  omis → l'accounting mark-to-market) : le nocturne 01/10 = la 1re campagne honnête
- **T8 : la machine codifiée = un artefact de fenêtre** (la cascade 10x liquidée
  dans 6/7 régimes ; les ABSOLUS docs/21 dépendent du warm-up, les RELATIFS
  tiennent) — les décisions au registre docs/20, section 30/09
- **Le gate fund7 > 0,5 bps/8h PRÉ-ENREGISTRÉ** (le mécanisme P3 validé N=61) —
  les verdicts à 90 j ; le registre traders Aster (06h53, 245 adresses jour 1)
- **Le domaine OpenMarket x501 mergé** (les PR #1-4 de l'agent web, review
  passée : 4 QA, bit-à-bit, la vague 4 = 40/53 pouvoirs) — la recherche Aster/FOMO
  gelée au profit d'OpenMarket (les collecteurs continuent)

### Aster — données & indicateurs
- `fetch_klines.py` / `fetch_deep_klines.py` — klines (standard / 1 an profond)
- `refresh_aster_cache.py`, `funding_scanner.py`, `carry_hedged.py`, `basis_guard.py`
- `aster_oi_history.py` — OI historique MAISON (nuits+midi)
- `aster_live.py` — terminal temps réel WS
- `aster_absorption.py`, `depth_heatmap.py`, `flow_snapshot.py`, `depth_collector.py`

### X.com (registre & veille)
- `x_harvest.py` — profils / searches / quotes / replies / meta / trends / feed / list
- `x_rotation.py` — rotation cashtag + quotes/replies/meta des top calls
- `x_list_build.py` — crée la liste privée « trading-agent » (41 membres)
- `fetch_x_posts.py` — ingestion registre + parse calls + scoring
- `score_x_calls.py` — verdicts des calls (colonne audience)
- `x_aster_pulse.py` — pression X par perp × funding → `x_pressure`
- `aster_convergence.py` — convergence X × OI × funding par perp

### fomo.family
- `fomo_harvest.py` — positions/panneaux/alerts/clans/tokens (daemon caché)
- `whale_radar.py` — radar 39 profils pondérés par compétence
- `wave_detector.py` — détecteur d'ondes + ledger `wave_flags`
- `memecoin_pulse.py`, `listing_watcher.py`, `registre_board.py`

### Backtests & fiabilité
- `backtest_indicators.py` — campagne v5 (indicateurs+funding, baseline anti-drift,
  régimes, liquidation par levier, SELFTEST à chaque run)
- `aster_indicators.py` — moteur d'indicateurs (sans lib TA)
- `slippage_measured.py` — slippage réel depuis nos carnets
- `housekeeping.py` — rétention rapports + état projet
- `run_tests.py` — `--fast` pour valider avant de commit

### Compte & clés
- `save_aster_key.py` — saisie invisible des credentials → `.env` (TESTNET pour l'instant)
- `aster_account.py` — sonde signée EIP-712 (solde/positions) — prête, attend clé privée API wallet

## 🗄️ ENTREPÔTS (`data/`)
- `warehouse/klines.db` — **le domaine ASTER** : klines 1h **1 an** + `oi_history` +
  `liq_events` + `funding_history` + `block_trades` + `premium_history` +
  `paper_trades` (le ledger machine, colonnes sonde P3) + `signal_events`
- `warehouse/depth.db` — carnets d'ordres (54 M bins, 15 symboles, cadence 30 s)
- `warehouse/x_posts.db` — registre X (posts, calls, scores) + `x_pressure`
- `fomo/fomo.db` — **la base HOT du daemon fomo** : fomo_ticks (2 s), `fomo_mc_samples`
  (la MC native échantillonnée), fomo_tokens, fomo_ohlcv, fomo_pre_graduated (16 k)
- `fomo/fomo_swaps.db` — le worker DOM : holders/theses/header + ws_traders + ws_swaps
- `fomo/fomo_rest.db` — **le collector REST** : fomo_rest_snapshots (toute la carte) +
  fomo_rest_swaps + fomo_rest_token_trades (les trades avec MC AU TRADE)
- `fomo/fomo_mobula.db` — le top-up (topup_dead) · `fomo/fomo_paper.db` — le ledger
  forward fomo (réplication derek, anti-rug)
- `x_browser_profile` — cache navigateur X (nettoyable)

## 📊 RAPPORTS (`reports/`) — rétention automatique (housekeeping)
`whale-radar` (7j) · `x-aster-pulse` (7j) · `aster-convergence` (7j) · `memecoin-pulse` (3)
· `backtest-campagne-v2` (5) · `registre-honnetete` (3) · `depth-heatmap` (9)
· `etat-projet.md` (réécrit chaque nuit)

## 📦 ARCHIVES (à ne pas confondre avec le vivant)
- `scripts/archive/` — 9 scripts retirés (legacy dataset, benchmarks Qwen,
  backtest absorption v1, audits one-off)
- `docs/archive/` — analyses PDF des époques passées
- `backend/.../legacy_discovery_batches/` — les 442 Mo de CSV de juin (source de
  `legacy_lanes.db`)

## 📚 DOCS (`docs/` — 00 → 21 numérotés + archive)
`03-methodology.md` (règle pré-enregistrée) · `07-backtest-engine.md` (l'alarme
taux d'acceptation) · `17-mmt-m5.md` (indicateurs MMT) · `18-roadmap-memecoin-x.md`
(le pivot complet) · `20-registre-indicateurs.md` (le registre vivant) ·
`21-goal-performances.md` (l'état de la machine et les 5 chantiers)

## 🚫 RÈGLES
- Aucun ordre autonome — exécution = le user seul
- Tout signal : backtest pré-enregistré AVANT de croire (`docs/03-methodology.md`)
- Toujours la baseline anti-dérive : un short aveugle gagne 71 % à +90j
- Les clés vivent dans `.env` (git-ignoré) — TESTNET pour l'instant
