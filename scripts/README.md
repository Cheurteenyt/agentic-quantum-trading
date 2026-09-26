# scripts/ — LA CARTE

**Comment on travaille** (la convention) : toute nouvelle idée d'indicateur
naît en one-shot dans `scripts/` → discipline complète (baseline, train/val
temporel, wallet séquentiel, contrôle inverse, BLOC STATS) → verdict
inscrit dans `docs/20-registre-indicateurs.md` → si CANDIDAT/VALIDÉ, le
script est **câblé au nocturne** (`trading-agent-nightly.service`) ; sinon
il reste avec son verdict rendu, on ne supprime jamais. Après tout fix
d'échelle/unité : les ABSOLUS sont re-mesurés.

**La vérité** : `docs/20-registre-indicateurs.md` (statuts, chiffres, dates).
**Le graphe** : Ariad (MCP) — notes d'architecture liées au code.

---

## 1. LE NOYAU — ce qui EST la stratégie (ne jamais casser)

| Fichier | Rôle |
|---|---|
| `the_machine.py` | **Le portefeuille officiel** (3 flux, BLOC STATS, table mensuelle, moniteur MAE) — câblé nocturne |
| `anti_liq.py` | Le collecteur cascade discipliné + l'AL Score (rangs roulants) — câblé |
| `portfolio_sim.py` | Le simulateur + moniteur MAE + garde-fous ROI — câblé |
| `stacked_portfolio.py` | `run_stack` (le wallet partagé) + les flux funding — câblé |
| `backtest_indicators.py` | **Le harnais v5** — LA référence des définitions de signaux — câblé |
| `aster_indicators.py` | La lib d'indicateurs (RSI, ATR, vwap…) utilisée par le harnais |

## 2. LES SIGNAUX & JUGES — câblés au nocturne

| Fichier | Rôle |
|---|---|
| `confluence_exact.py` | La confluence v5 exacte (accel + vwap 3σ) — le profil qualité |
| `full_arsenal_2.py` | L'arsenal funding/momentum — contient le flux survivor |
| `mechanism_probe.py` | La sonde : cascade × liquidations directes (les acteurs) |
| `regime_filter.py` | Le régime BTC × volatilité (le quadrant à éviter) |
| `cascade_funding.py` | Le conditionnement funding de la cascade (verdict : nul) |
| `liq_storm.py` | La lecture live des liquidations (notre série forceOrder) |
| `paper_forward.py` | **LE JUGE** — les candidats sur données vivantes, 2×/jour |
| `lcs.py` | Le Lifecycle Composite Score (filtre de contexte) |
| `signal_audit.py` | La re-vérification à la main des définitions (après tout changement) |

## 3. LES COLLECTEURS — la matière première (24/7 ou nocturne)

| Fichier | Série |
|---|---|
| `funding_history_collector.py` | funding profond (71 symboles, 2023→) |
| `liq_collector.py` | liquidations forceOrder (service 24/7) |
| `depth_collector.py` | carnet d'ordres (1 Go, 15 symboles) |
| `refresh_aster_cache.py` | caches Aster (funding agrégés, tickers) |
| `fetch_klines.py` / `fetch_deep_klines.py` | bougies 1h/15m (1 an+) |
| `whale_radar.py` / `whale_flow.py` / `fomo_harvest.py` | la couche fomo |
| `fomo_tick_collector.py` | ticks fomo 24/7 → 1m OHLCV (flock anti-orphan, filtre QUOTE_MINTS) |
| `fomo_history_collector.py` / `fomo_master_backfill.py` | backfill GT via mapping `_TF` (minute 1/5/15, hour 1h/4h) + top-up sélectif |
| `x_harvest.py` / `fetch_x_posts.py` / `score_x_calls.py` | la couche X |
| `aster_oi_history.py` | open interest (maison) |
| `basis_guard.py` / `flow_snapshot.py` | basis + flow |

## 4. LA RECHERCHE — one-shots à verdict rendu (on ne supprime pas)

`squeeze` (miroir mort) · `launch_pump` (asymétrie réelle, non tradeable) ·
`signal_ladder` (l'anti-condition vwap) · `cascade_exit` (famille exit fermée) ·
`full_arsenal` (les 4 signaux prix à 1x) · `backtest_stack` (legacy) ·
`backtest_exotique` (divergence marquée) · `backtest_cascade*` ·
`backtest_lifecycle` (LA carte) · `backtest_longterm` · `backtest_crash` ·
`backtest_matrix` · `backtest_retest` / `backtest_rebreak` ·
`backtest_maker_taker` · `backtest_depth` · `backtest_institutional` ·
`backtest_x20` · `backtest_fast` (EN QUARANTAINE) · `synthesize_intervals`

## 5. LES OUTILS

`run_tests.py` (627 tests) · `housekeeping.py` · `html_to_pdf.py` ·
`registre_board.py` · `save_aster_key.py` · `telegram_notify.py` ·
`security/validate_tailscale_acl.py`

---

**Le nocturne** (`trading-agent-nightly.service`, 03h01) exécute ~70 étapes :
collecteurs → klines → paper_forward → analytics (les fichiers câblés) →
fomo/X. **Le midi** (14h00) : récolte X + score + paper_forward.
Tout rapport du matin : `reports/<script>-<date>.md`.

Documentation centrale : [`docs/02-architecture.md`](../docs/02-architecture.md) ·
[`docs/README.md`](../docs/README.md) · registre : [`docs/20-registre-indicateurs.md`](../docs/20-registre-indicateurs.md)
