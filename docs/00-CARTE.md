# 🗺️ CARTE DU PROJET — un seul endroit pour tout trouver

> Mise à jour : 28/09/2026. Si un fichier bouge, cette carte bouge.
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

## 🔁 LES COLLECTEURS QUI TOURNENT 24/7 (systemd user)

| Service | Rythme | Rôle |
|---|---|---|
| `aster-depth-collector` | 24/7 WS/REST | Carnets d'ordres → `depth.db` (15 symboles) |
| `aster-liq-collector` | 24/7 WS | Liquidations → `klines.db:liq_events` |
| `fomo-tick-collector` | 24/7 | Ticks fomo → 1m OHLCV (flock anti-orphan, filtre QUOTE_MINTS) |
| `fomo-mobula-topup` | 15 min | Rattrapage bougies mobula sans navigateur (`fomo_mobula_topup.py`) |
| `fomo-paper-forward` | 15 min | Ledger forward des lancements (`fomo_paper_forward.py`) |
| `oi-collector` | 15 min | OI Aster → `klines.db:oi_history` (`oi_collector.py`) |
| `fomo-swaps-fresh` | 1 h | Page 1 des 13 baleines (`fomo_swaps_collector.py`) |
| `fomo-browser` | permanent | Chromium caché (special:fomo) + CDP :9222 |
| `trading-agent-nightly` | 03h00 (~70 étapes) | TOUTE la chaîne nocturne (voir unité) — les indicateurs câblés |
| `trading-agent-registre-noon` | 14h00 | Récolte X + liste privée + OI + scoring |
| `depth-heatmap` / `liquidation-watcher` | périodique | Rapports visuels |

## 🤖 LES AGENTS (.zcode/agents/)

`quant-researcher.md` · `fomo-data-engineer.md` · `bug-hunter.md` ·
`discord-bot.md` — le mode parallèle est codifié dans `AGENTS.md`
(dès que ≥ 2 flux indépendants : dispatch en agents parallèles).

## 📜 SCRIPTS VIVANTS par domaine (`scripts/`)

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
- `klines.db` — klines 1h **1 an** + `oi_history` + `liq_events` + `funding_history` (4,5 mois)
- `fomo.db` — 10 tables : positions, traders, tier_list, token_intel, new_coins,
  events, closed, clans, clan_holdings, clan_members
- `x_posts.db` — registre (560+ posts, calls, scores) + `x_pressure` + `x_signal_history`
  + `x_profiles` + `x_trends` + `x_lists_found`
- `depth.db` — carnets d'ordres (4,4M bins) + slippage mesuré
- `legacy_lanes.db` — les 17 092 lanes de juin 2026 (auditées)

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
