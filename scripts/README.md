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
| `aster_blocktrades.py` | gros prints aggTrades (seuils adaptatifs BTC 99k/ETH 23k/SOL 2k) — timer 15 min |
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

## 6. LA SESSION DU 27-28/09 — les nouveaux scripts (tout reste, verdicts dans docs/20)

### 6a. Recherche quant (verdicts rendus, briques réutilisables)

| Fichier | Une ligne |
|---|---|
| `qubo_sizing.py` | QUBO discrétisé des poids (annealing, Q = cov TRAIN) — CANDIDAT +4 539 % @ 23,4 % |
| `qubo_joint_lev.py` | QUBO joint poids×levier (plafonds MAE par flux) — CANDIDAT **+5 082 % @ 23,3 %**, record +83,7 % |
| `qubo_per_symbol.py` | QUBO par symbole dans le flux majors (granularité 6 majeures) |
| `conditional_sizing.py` | sizing conditionnel par régime (jamais gate sec) — NUL (contrôle inverse ambigu) |
| `funding_dimension_study.py` | structure funding (velocity/dispersion/level) — NUL |
| `tilt_frontier.py` | frontière du multiplicateur tilt × meme — point final ×1,10 + meme ×0,5 |
| `tilt_volspike_test.py` | tilt × vol-spike + survivor ×2.0 — les derniers raffinements 4 flux |
| `h1_absorption_test.py` | H1 buy_ratio — NUL (aucun sizing branché) |
| `h2_h3_cvd_test.py` | H2 pente CVD + H3 sweep volumique — NUL/NUL |
| `capitulation_sweep_test.py` | H2bis capitulation + H3bis sweep (pré-enregistrés) — NUL / CONTEXTE |
| `wallclock_cascades.py` | l'heure d'entrée des cascades — CONTEXTE (artefact de régime) |
| `recascade_study.py` | re-cascades ≤ 7j (tag ex-ante) — CONTEXTE |
| `wallet_dd_guard.py` | garde drawdown wallet (désengagement prop-firm) — NUL 12/12 |
| `funding_hold_surv_map.py` | hold étendu funding-conditionnel NUL + carte hold survivor (72h confirmé) |
| `survivor_meme_test.py` | TAIL survivor (ATR > p90) flat — CANDIDAT avec réserve de concentration |
| `tail_machine_confirm.py` | TAIL au sizing machine réel — FAIL critère pré-enregistré → CONTEXTE |
| `p5_frequency_test.py` | les flux de fréquence P5 — vol_spike_6h CANDIDAT (câblé 4e flux) |
| `volspike_meme_test.py` | vol_spike sur memecoins — CANDIDAT confirmé (flux memecoin natif, majors ~1 %) |
| `carte_meme_hold.py` | carte hold × levier du flux meme — DÉGRADÉ (ne PAS lever) |
| `autopsie_mois_negatifs.py` | séparateurs des mois négatifs (fund7, fresh-peak) — profil n=1 |
| `fomo_lifecycle_study.py` / `fomo_lifecycle_v2.py` | lifecycle des lancements (v2 sur le corpus profond mobula) |
| `k_scan.py` | le multiplicateur de taille absolu K (le dernier paramètre libre) — K=0,95 = **+6 419 %/an @ DD 24,9 %**, CANDIDAT à arbitrer |
| `meme_universe_audit.py` | audit de complétude de l'univers meme — 4 tier-1 câblés au nocturne (DRAM/PIEVERSE/VIRTUAL/MELANIA, +313 events/an), 2 tickers périmés corrigés |

### 6b. Data fomo

| Fichier | Une ligne |
|---|---|
| `fomo_ohlcv_backfill.py` | backfill OHLCV via l'endpoint mobula de l'app (le crack 27/09 : 347k → 2,89M bougies) |
| `fomo_mobula_topup.py` | rattrapage de bougies sans navigateur — timer 15 min |
| `fomo_bonding_phase_study.py` | la phase bonding (premier gisement : les ×10 pré-pool) |
| `fomo_bonding_resolve.py` | la boucle bonding : tickers → mints → OHLCV mobula (collecteur réparé, âge + overlap) |
| `fomo_bonding_test.py` | mobula inclut-il la phase bonding ? (oui — le bonding est couvert) |
| `bonding_signal_study.py` | signaux bonding × trades |
| `fomo_swaps_collector.py` (+ `_resolve` / `_store`) | swaps des 13 baleines (pagination lastSwapId crackée, 12 562 swaps) |
| `swaps_forward_study.py` | l'edge de réplication skill-weighted des swaps |
| `swaps_forward_v2.py` | re-run post-backfill complet (2 233 events) — **PASS** (edge +8,4 %, TRAIN +6,7 → VAL +12,3 %) |
| `derek_replication_test.py` | wallet séquentiel de réplication derek518 — CANDIDAT (+88 %/26 j @ DD 6,4 %, robuste sans le top-3) |
| `fomo_paper_forward.py` | le ledger forward des lancements (entrée à la naissance, anti-rug) + la règle `replication_derek` câblée (verdict à ≥ 5 CLOSED) — timer 15 min |

### 6c. Infra & collecteurs

| Fichier | Une ligne |
|---|---|
| `qubo_forward_tracker.py` | les 3 configs machine (main / QUBO poids / QUBO joint) sur les MÊMES trades paper |
| `oi_collector.py` | OI Aster toutes les 15 min → `klines.db` (timer) |
| `flow_audit.py` | audit lecture-seule de la couche flow — les 2 bugs CRITIQUES de la chaîne forward patchés |
| `backfill_taker_volume.py` | backfill CVD (taker buy volume) + quote volume dans `klines.db` |
| `fetch_klines.py` | v2 : taker buy volume (CVD 1h + 15m à 100 %) |
| `mechanism_probe.py` | patché (audit Ariad) — champs fund7/vol7/liq24h loggés (la sonde P3) |

### 6d. Les tests d'octobre (pré-enregistrés AVANT le tir)

| Fichier | Tir |
|---|---|
| `oi_quadrant_test.py` | quadrant OI × prix (H4/H5) — **06-07/10** |
| `whaleflow_join_test.py` | whale_flow × prix (J+14) — **08/10** |
| `wall_detector.py` | les murs du carnet (PULL 91-98 % vs HIT, divergence 27 bp — HIT = continuation, PULL = faiblesse) — PROTOTYPE 4,3 j, **re-tir 06-07/10** |
| `depth_indicator_prototype.py` | géométrie 0-liquidation sur le micro-drift d'imbalance — prototype prêt |
| `backtest_depth.py` | le gate depth — la porte micro-structure du 20x |

---

**Le nocturne** (`trading-agent-nightly.service`, 03h01) exécute ~70 étapes :
collecteurs → klines → paper_forward → analytics (les fichiers câblés) →
fomo/X. **Le midi** (14h00) : récolte X + score + paper_forward.
Tout rapport du matin : `reports/<script>-<date>.md`.

Documentation centrale : [`docs/02-architecture.md`](../docs/02-architecture.md) ·
[`docs/README.md`](../docs/README.md) · registre : [`docs/20-registre-indicateurs.md`](../docs/20-registre-indicateurs.md)
