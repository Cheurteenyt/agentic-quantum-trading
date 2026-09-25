# 🗺️ CARTE DU PROJET — un seul endroit pour tout trouver

> Mise à jour : 25/09/2026. Si un fichier bouge, cette carte bouge.
> Doc d'architecture complète : `docs/02-architecture.md`.

## 🏆 LA MACHINE & LE REGISTRE (l'état de la stratégie)

- **Le portefeuille officiel** : `the_machine.py` (câblé nocturne) — cascade
  majeurs 10x gated AL Score + sizing vol-inverse, cascade memecoins 1x,
  survivor long 1x → **+2 829 %/an @ DD 27,8 %, 0 liquidation, 534 trades,
  record mensuel +88,5 %, 2 mois négatifs légers/13** (backtest 1 an, le
  paper forward 2×/jour juge sur le vivant).
- **La règle gravée** : levier ≤ 100/(maxMAE + 0,5) — MAE max gated 7,84 %
  → 10x = mort à 9,5 %, jamais atteinte (moniteur nocturne intégré).
- **Le candidat qualité** : cascade ∩ funding-rank-bas — WR 81 %, DD 5,4 %,
  0 liq, en accumulation forward (~2 trades/mois).
- **Le registre vivant de tous les indicateurs** (VALIDÉ/CANDIDAT/CONTEXTE/NUL,
  chiffres et dates) : `docs/20-registre-indicateurs.md`.
- **La carte des scripts** : `scripts/README.md` (76 fichiers en 5 groupes,
  la convention de travail).

## ⚙️ SERVICES SYSTEMD (qui tourne tout seul)

| Service | Rythme | Rôle |
|---|---|---|
| `trading-agent-nightly` | 03h00 (~70 étapes) | TOUTE la chaîne nocturne (voir unité) — **11 indicateurs maison câblés** |
| `trading-agent-registre-noon` | 14h00 | Récolte X + liste privée + OI + scoring |
| `aster-depth-collector` | 24/7 WS/REST | Carnets d'ordres → `depth.db` (15 symboles) |
| `aster-liq-collector` | 24/7 WS | Liquidations → `klines.db:liq_events` |
| `fomo-browser` | permanent | Chromium caché (special:fomo) + CDP :9222 |
| `depth-heatmap` / `liquidation-watcher` | périodique | Rapports visuels |

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

## 📚 DOCS (`docs/` — 01 → 18 numérotés + archive)
`03-methodology.md` (règle pré-enregistrée) · `07-backtest-engine.md` (l'alarme
taux d'acceptation) · `17-mmt-m5.md` (indicateurs MMT) · `18-roadmap-memecoin-x.md`
(le pivot complet)

## 🚫 RÈGLES
- Aucun ordre autonome — exécution = le user seul
- Tout signal : backtest pré-enregistré AVANT de croire (`docs/03-methodology.md`)
- Toujours la baseline anti-dérive : un short aveugle gagne 71 % à +90j
- Les clés vivent dans `.env` (git-ignoré) — TESTNET pour l'instant
