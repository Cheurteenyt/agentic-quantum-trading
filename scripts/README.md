# scripts/ — LA CARTE

> **Domaines (01/10/2026)** : ASTER ≠ FOMO ≠ OPENMARKET ≠ X.  
> **Horizons** : taguer chaque backtest `H-1Y` | `H-MULTI` | `H-LIVE` | `H-MICRO`.  
> **Lab** : `docs/lab/` — mortuary, primitives, hypothèses avant code.  
> Détail : `PROJECT_STRUCTURE.md`.

**Les 3 nocturnes (30/09)** : le domaine ASTER = trading-agent-nightly (03:00,
65 steps), le domaine X = x-nightly (03:21, 20 steps), le domaine FOMO =
fomo-nightly (03:55, 9 steps) — un domaine = une unité, jamais éditer une
unit pendant son run.

**Comment on travaille** (la convention) : toute nouvelle idée d'indicateur
naît en one-shot (`scripts/studies/`, ou racine si la brique est destinée
au nocturne) → discipline complète (baseline, train/val
temporel, wallet séquentiel, contrôle inverse, BLOC STATS) → verdict
inscrit dans `docs/20-registre-indicateurs.md` → si CANDIDAT/VALIDÉ, le
script est **câblé au nocturne du même domaine** ; sinon
il est **archivé dans `scripts/archive_studies/`** (§7), on ne supprime
jamais. Après tout fix d'échelle/unité : les ABSOLUS sont re-mesurés.

**Hypothèse d'abord** : `docs/lab/hypotheses/` + protocole `docs/lab/protocol.md`.

**La vérité** : `docs/20-registre-indicateurs.md` (statuts, chiffres, dates).
**Le graphe** : Ariad (MCP) — notes d'architecture liées au code.

---

## 1. LE NOYAU ASTER — ce qui EST la stratégie (ne jamais casser)

| Fichier | Rôle |
|---|---|
| `the_machine.py` | **Le portefeuille officiel** (3 flux, BLOC STATS, table mensuelle, moniteur MAE) — câblé nocturne ASTER |
| `anti_liq.py` | Le collecteur cascade discipliné + l'AL Score (rangs roulants) — câblé |
| `portfolio_sim.py` | Le simulateur + moniteur MAE + garde-fous ROI — câblé |
| `stacked_portfolio.py` | `run_stack` (le wallet partagé) + les flux funding — câblé |
| `backtest_indicators.py` | **Le harnais v5** — LA référence des définitions de signaux — câblé |
| `aster_indicators.py` | La lib d'indicateurs (RSI, ATR, vwap…) utilisée par le harnais |

## 2. LES SIGNAUX & JUGES ASTER — câblés au nocturne

| Fichier | Rôle |
|---|---|
| `confluence_exact.py` | La confluence v5 exacte (accel + vwap 3σ) — le profil qualité |
| `full_arsenal_2.py` | L'arsenal funding/momentum — contient le flux survivor |
| `mechanism_probe.py` | La sonde : cascade × liquidations directes (les acteurs) |
| `regime_filter.py` | Le régime BTC × volatilité (le quadrant à éviter) |
| `cascade_funding.py` | Le conditionnement funding de la cascade (verdict : nul) |
| `liq_storm.py` | La lecture live des liquidations (notre série forceOrder) |
| `paper_forward.py` | **LE JUGE ASTER** — les candidats sur données vivantes, 2×/jour |
| `lcs.py` | Le Lifecycle Composite Score (filtre de contexte) |
| `signal_audit.py` | La re-vérification à la main des définitions (après tout changement) |

## 3. LES COLLECTEURS — par domaine (la matière première, 24/7 ou nocturne)

### 3a. ASTER

| Fichier | Série |
|---|---|
| `funding_history_collector.py` | funding profond (71 symboles, 2023→) |
| `liq_collector.py` | liquidations forceOrder (service 24/7) |
| `depth_collector.py` | carnet d'ordres (1 Go, 15 symboles) |
| `refresh_aster_cache.py` | caches Aster (funding agrégés, tickers) |
| `fetch_klines.py` / `fetch_deep_klines.py` | bougies 1h/15m (1 an+) |
| `aster_health.py` | **watchdog ASTER (30/09, timer 5 min)** : 8 sondes — klines 1h > 25 h, OI/liq/blocks/premium/depth fraîcheur, CONTINUITÉ depth (0 trou > 15 min sur 24 h = la tolérance zéro du tir 06-07), cache funding > 25 h ; les tables d'ÉVÉNEMENTS se sondent au LastTriggerUSec du timer (un vieux MAX = un marché calme, pas un collecteur mort), état dans data/warehouse/aster_health_state.json |
| `aster_oi_history.py` | open interest (maison) |
| `oi_collector.py` | OI Aster toutes les 15 min → `klines.db` (timer) |
| `aster_blocktrades.py` | gros prints aggTrades (seuils adaptatifs BTC 99k/ETH 23k/SOL 2k) — timer 15 min |
| `basis_guard.py` / `flow_snapshot.py` | basis + flow |

### 3b. FOMO (préfixe `fomo_*` — ne pas brancher dans the_machine)

| Fichier | Série |
|---|---|
| `whale_radar.py` / `whale_flow.py` / `fomo_harvest.py` | la couche fomo |
| `fomo_tick_collector.py` | ticks fomo 24/7 → 1m OHLCV (flock anti-orphan, filtre QUOTE_MINTS) |
| `fomo_ws_daemon.py` | **daemon WS natif 24/7 (d9e23b4→v2)** : le socket prod-api/ws sans navigateur — le feed GLOBAL des swaps (ws_swaps typées, flag top_trader, ws_traders auto-appris) + les prix LRU 78 topics ; protocole : challenge JWT + subscribe, plafond ~80 topics, pacing 0.05 s |
| `fomo_rest_collector.py` | **collector REST (29/09, timer 30 min)** : les endpoints prod-api en Python pur (curl_cffi chrome131 + JWT partagé) — hodlers/top (97/appel + totalHolders), sortedThesis 24 h (500/token), swaps élite 100/appel, trades fermés, leaderboard/clans/trending → `fomo_rest.db` dédiée (1 écrivain) ; le DOM = le fallback |
| `fomo_health.py` | **watchdog (29/09, timer 5 min)** : 4 sondes — ticks figés > 300 s, collector REST > 40 min, chaîne JWT cassée, > 10 locks/30 min — alerte journal SUR TRANSITION seulement, état dans data/fomo/health_state.json |
| `fomo_paper_forward.py` | **LE JUGE FOMO** — le ledger forward des lancements (entrée à la naissance, anti-rug) + la règle `replication_derek` câblée (verdict à ≥ 5 CLOSED) — timer 15 min |
| `fomo_access.py` | **LA couche d'accès unifiée fomo (29/09)** — scrapling Fetcher (impersonation TLS, passe le Cloudflare, testé 200) : `fetch_fomo` / `fetch_mobula` / `fetch_prod_api` + rate-limit et retries backoffés ; urllib direct banni |
| `fomo_swaps_collector.py` | swaps des 13 baleines (pagination lastSwapId crackée, 12 562 swaps) — `_resolve`/`_store` **archivés 29/09** (doublons couverts + bug mint inversé dans _store) |
| `swaps_forward_v2.py` | re-run post-backfill complet (2 233 events) — **PASS** (edge +8,4 %, TRAIN +6,7 → VAL +12,3 %) |
| `derek_watch.py` | la détection temps réel des achats de derek518 (swap API in-page CDP, 1 passe/min) — bloqué par le mur d'auth 29/09 |
| `login_window_miner.py` | le mineur DOM résident de la fenêtre de login (:9223) — sans API, sans ban (1×/5 min) |
| `fomo_window_guard.py` | le garde de la fenêtre fomo-whale sur special:fomo (-98) (restart daemon+collector si dérive) |
| `fomo_bonding_monitor.py` | le moniteur de pré-graduation fomo → DEX |
| `fomo_history_collector.py` / `fomo_master_backfill.py` | backfill GT via mapping `_TF` (minute 1/5/15, hour 1h/4h) + top-up sélectif |
| … | les one-shots data fomo de la session 27-28/09 en §6b |

### 3c. X

| Fichier | Série |
|---|---|
| `x_harvest.py` / `fetch_x_posts.py` / `score_x_calls.py` | la couche X |

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

## 6. LA SESSION DU 27-28/09 — les nouveaux scripts (verdicts dans docs/20)

> **28/09** : les one-shots closes de cette session sont archivés dans
> `scripts/archive_studies/` — les noms ci-dessous y pointent désormais
> (liste verdict-par-verdict en §7).

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
| `fomo_lifecycle_study.py` / `fomo_lifecycle_v2.py` | lifecycle des lancements — **archivés 29/09** (v2 : verdict NUL, bougies mobula à nettoyer ; le filtre voisin-based vit dedans) |
| `k_scan.py` | le multiplicateur de taille absolu K (le dernier paramètre libre) — K=0,95 = **+6 419 %/an @ DD 24,9 %**, CANDIDAT à arbitrer |
| `meme_universe_audit.py` | audit de complétude de l'univers meme — 4 tier-1 câblés au nocturne (DRAM/PIEVERSE/VIRTUAL/MELANIA, +313 events/an), 2 tickers périmés corrigés |

### 6b. Data fomo

| Fichier | Une ligne |
|---|---|
| `fomo_ohlcv_backfill.py` | backfill OHLCV via l'endpoint mobula de l'app (le crack 27/09 : 347k → 2,89M bougies) |
| `fomo_mobula_topup.py` | rattrapage de bougies sans navigateur — timer 15 min |
| `fomo_bonding_phase_study.py` | la phase bonding (premier gisement : les ×10 pré-pool) — **archivé 29/09** (étude close, verdict au registre) |
| `fomo_bonding_resolve.py` | la boucle bonding : tickers → mints → OHLCV mobula (collecteur réparé, âge + overlap) |
| `fomo_bonding_test.py` | mobula inclut-il la phase bonding ? (oui — le bonding est couvert) — **archivé 29/09** (one-shot, réponse documentée) |
| `bonding_signal_study.py` | signaux bonding × trades |
| `fomo_swaps_collector.py` | swaps des 13 baleines (pagination lastSwapId crackée, 12 562 swaps) — `_resolve`/`_store` **archivés 29/09** (doublons couverts + bug mint inversé dans _store) |
| `fomo_access.py` | **LA couche d'accès unifiée fomo (29/09)** — scrapling Fetcher (impersonation TLS, passe le Cloudflare, testé 200) : `fetch_fomo` / `fetch_mobula` / `fetch_prod_api` + rate-limit et retries backoffés ; urllib direct banni |
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

## 7. ARCHIVE ÉTUDES (`scripts/archive_studies/`) — le 28/09

Les one-shots d'études CLOSES (verdict NUL/CONTEXTE/fermé ET aucun import
d'un fichier vivant) y sont déplacés tels quels, chacun avec en tête :
`# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md`.
Les imports croisés entre archivés ont un fallback `scripts.archive_studies.*`,
les `ROOT = parents[1]` ont été ajustés d'un cran → ré-exécutables. La racine
de `scripts/` reste = les permanents (noyau, collecteurs, machine, harnais,
candidats forward). **Règle d'archivage** : verdict rendu ET aucun fichier
vivant ne l'importe.

| Script (archivé) | Une ligne — le verdict |
|---|---|
| `conditional_sizing.py` | sizing conditionnel par régime — NUL (contrôle inverse ambigu) |
| `funding_dimension_study.py` | structure funding (velocity/dispersion/level) — NUL |
| `h1_absorption_test.py` | H1 buy_ratio — NUL (hint inverse → CONTEXTE de H2) |
| `h2_h3_cvd_test.py` | H2 pente CVD + H3 sweep volumique — NUL/NUL (hints post-hoc → CONTEXTE) |
| `capitulation_sweep_test.py` | H2bis capitulation + H3bis sweep (pré-enregistrés) — NUL / CONTEXTE |
| `wallclock_cascades.py` | heure d'entrée des cascades — CONTEXTE (artefact du régime 2025) |
| `recascade_study.py` | re-cascades ≤ 7j (tag ex-ante) — CONTEXTE (ni continuation premium ni épuisement) |
| `funding_hold_surv_map.py` | hold étendu funding-conditionnel — NUL (le hold 24h reste l'optimum) ; carte hold survivor : 72h confirmé |
| `wallet_dd_guard.py` | garde drawdown wallet (prop-firm) — NUL 12/12 (couper en DD coupe le rebond) |
| `tail_machine_confirm.py` | TAIL survivor au sizing machine réel — FAIL critère pré-enregistré → CONTEXTE |
| `tilt_volspike_test.py` | tilt × vol-spike + survivor ×2.0 — VERDICT OFF (aucun adopté), survivor garde p90 ; la frontière reste `tilt_frontier.py` |
| `hybrid_hold_test.py` | hold hybride 24h/72h conditionné au swap baleine — NUL (la doctrine hold24h tient) |
| `whale_attention_test.py` | l'attention baleine change-t-elle le régime du token — FAIL (hint anti-filtre post-T0 0-7j) |
| `cascade_fractal_test.py` | cascade 15m/30m vs champion 1h/24h — NUL (mur des coûts ; fractalité de fréquence ≠ fractalité d'espérance) |
| `carte_meme_hold.py` | carte hold × levier du flux meme — DÉGRADÉ (ne PAS lever) |
| `swaps_forward_study.py` | swaps → forward v1 — remplacé par `swaps_forward_v2.py` (PASS) |
| `derek_replication_test.py` | réplication derek518 (étude, +88 %/26 j) — close ; le forward vit dans `fomo_paper_forward.py` (règle `replication_derek`) |
| `qubo_per_symbol.py` | QUBO par symbole (flux majors) — CONTEXTE |
| `autopsie_mois_negatifs.py` | séparateurs des mois négatifs (fund7, fresh-peak) — profil n=1 (sonde P3 en octobre) |
| `fomo_lifecycle_study.py` | lifecycle v1 — re-catégorisé (métriques 15m sous-estiment les pumps <15 min), remplacé par v2 |
| `fomo_lifecycle_v2.py` | lifecycle v2 corpus profond — verdict NUL (bougies mobula à nettoyer avant tout backtest 1m/15m) — archivé 29/09 |
| `fomo_launch_study.py` | première étude launches (5 tokens) — remplacée par lifecycle v2/v3 |
| `fomo_ohlcv_collector.py` | collecteur OHLCV playwright — remplacé par `fomo_tick_collector.py` (24/7) — archivé 29/09 |
| `fomo_bonding_phase_study.py` | étude de la phase bonding — close 27/09, verdict au registre — archivé 29/09 |
| `fomo_bonding_test.py` | one-shot : mobula couvre la bonding (pool_created_at GT) — archivé 29/09 |
| `fomo_chart_probe.py` | sonde one-shot de la source chart — archivé 29/09 |
| `fomo_swaps_param_hunt.py` / `fomo_swaps_modal_probe.py` / `fomo_swaps_js_grep.py` / `fomo_swaps_module_grep.py` / `fomo_swaps_pagination_probe.py` | sondes one-shot pagination swaps — la réponse (lastSwapId) est câblée dans le collector — archivés 29/09 |
| `fomo_swaps_resolve.py` / `fomo_swaps_fetch_browser.py` / `fomo_swaps_store.py` | one-shots/doublons couverts par `fomo_swaps_collector.py` (_store avait le bug mint inversé) — archivés 29/09 |

**Exceptions gardées à la racine malgré un verdict non-VALIDÉ** :
`k_scan.py` (CANDIDAT à arbitrer), `survivor_meme_test.py` + `volspike_meme_test.py`
(vivant — l'un importe l'autre), `lifecycle_v3_scale.py`
(doctrine vivante), `depth_indicator_prototype.py` + `wall_detector.py`
(re-tir 06-07/10), `tilt_frontier.py`, `qubo_sizing.py` / `qubo_joint_lev.py`
(CANDIDATS en paper forward), `p5_frequency_test.py` (vol_spike câblé 4e flux).

## 8. LE DOMAINE OPENMARKET x501 (`scripts/studies/x501_openmarket/`)

> **DOMAINE ISOLÉ** — ne jamais mélanger avec La Machine / FOMO / X.
> Programme OpenMarket (100 $ → 50 100 $, DD ≤ 25 %) : `docs/25-openmarket-x501.md`.
> Un dossier = le domaine entier. Carte interne : `scripts/studies/x501_openmarket/README.md`.
> Rapports → `reports/openmarket/` uniquement.

| Contenu | Une ligne |
|---|---|
| `Operation_x501_Signature_*.ks` | stratégies signature / maker / RI / absorption |
| `x501_observe_*.ks` | observe (zéro ordre) |
| `x501_setup_kscript.js` | installation codifiée |
| `qa_*_x501.py` | QA statiques (stdlib) |

## 9. LAB GRIND + DOMAINES (01/10/2026)

Voir `PROJECT_STRUCTURE.md` et `docs/lab/README.md`.

- **4 domaines** : ASTER / FOMO / OPENMARKET / X — zéro mélange de métriques.
- **Horizons** : tout backtest tagué `H-1Y` | `H-MULTI` | `H-LIVE` | `H-MICRO`.
- **Nouvelles idées** : hypothèse dans `docs/lab/hypotheses/` → étude → registre → mortuary/primitives.
- **Nocturnes** restent séparés (Aster / X / FOMO) — ne pas fusionner les units.

---

**Le nocturne** (`trading-agent-nightly.service`, 03h01) exécute ~70 étapes :
collecteurs → klines → paper_forward → analytics (les fichiers câblés) →
fomo/X. **Le midi** (14h00) : récolte X + score + paper_forward.
Tout rapport du matin : `reports/<script>-<date>.md`.

Documentation centrale : [`docs/02-architecture.md`](../docs/02-architecture.md) ·
[`docs/README.md`](../docs/README.md) · registre : [`docs/20-registre-indicateurs.md`](../docs/20-registre-indicateurs.md)
