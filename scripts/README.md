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

## 3. LES COLLECTEURS — par domaine

### 3a. ASTER

| Fichier | Série |
|---|---|
| `funding_history_collector.py` | funding profond (71 symboles, 2023→) |
| `liq_collector.py` | liquidations forceOrder (service 24/7) |
| `depth_collector.py` | carnet d'ordres |
| `refresh_aster_cache.py` | caches Aster |
| `fetch_klines.py` / `fetch_deep_klines.py` | bougies 1h/15m |
| `aster_health.py` | watchdog ASTER |
| `aster_oi_history.py` / `oi_collector.py` | open interest maison |
| `aster_blocktrades.py` | gros prints |
| `basis_guard.py` / `flow_snapshot.py` | basis + flow |

### 3b. FOMO (préfixe `fomo_*` — ne pas brancher dans the_machine)

| Fichier | Série |
|---|---|
| `fomo_tick_collector.py` | ticks → 1m OHLCV |
| `fomo_ws_daemon.py` | daemon WS natif |
| `fomo_rest_collector.py` | REST prod-api |
| `fomo_health.py` | watchdog FOMO |
| `fomo_paper_forward.py` | **LE JUGE FOMO** |
| `fomo_access.py` | couche d'accès unifiée |
| `fomo_swaps_collector.py` / `swaps_forward_v2.py` | swaps + edge |
| … | voir §6b |

### 3c. X

| Fichier | Série |
|---|---|
| `x_harvest.py` / `fetch_x_posts.py` / `score_x_calls.py` | harvest + scoring |

## 4–7. Recherche, outils, sessions, archive

Inchangé en substance : one-shots, `archive_studies/`, exceptions CANDIDAT à la racine.
Voir historique git pour le détail session 27–28/09 ; la vérité reste `docs/20`.

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
