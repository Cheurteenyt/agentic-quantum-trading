# x501_openmarket/ — LE DOMAINE OPENMARKET (kScripts + QA + bancs)

**Le domaine de la mission x501** (100 $ → 50 100 $, DD ≤ 25 % —
`docs/25-openmarket-x501.md`). Tout le code du domaine tient dans ce
dossier : les 13 kScripts, le scanner d'installation, les collecteurs
versionnés et les 13 QA statiques.
Les données restent locales (git-ignorées, `docs/26-openmarket-donnees.md`).

## Contenu

| Fichier | Rôle |
|---|---|
| `Operation_x501_Signature_H1.ks` / `_H4.ks` | le signal de base (signature), cadence H1 / H4 |
| `Operation_x501_Signature_H1_MK.ks` / `_H4_MK.ks` | **les versions maker** (limite δ=2–5, TTL, fallback taker, verrous pend*) + **vague 3 (docs/27-28)** : trail natif du runner (`useNativeTrail`, défaut false), groupes OCA nommés par tranche, `cancelAll()` post-halt (bug réel corrigé), rapport fin de run natif (closedTradeCount/WR/maxDrawdown) |
| `Operation_x501_Signature_H1_RI.ks` | **vague 1 (docs/27)** — la Signature H1 + le filtre de RÉGIME INSTITUTIONNEL : score RI = 5 composantes écrêtées (ETF flow 3 j, CME OI × signe prix, DVOL vs MM 30, skew 1W, LSR contrarian), seuil ±0,10, no-repaint via buckets quotidiens complétés (`htf 1D`, jamais `[0]`), fail-open si les flux sont absents |
| `x501_observe_regime.ks` | **vague 1** — l'observe des 8 flux premium : table de disponibilité par flux, composantes RI brutes, alerte de bascule de quadrant (9 souscriptions) |
| `Operation_x501_Absorption_H1.ks` | **vague 2 (docs/27)** — l'absorption orderbook NATIVE : mur = `maxBidAmount`/`maxAskAmount` ≥ 3× sa moyenne 200, attaque = vague taker ≥ 2× sa moyenne, tenue = écrasement ≤ 0,8 %, reprise = EMA flux net + déséquilibre `sumBids`/`sumAsks` ≥ 1,2 — le pattern qui a produit l'AL Score d'Aster, dans le backtester |
| `Operation_x501_Alpha2_Cascade_Financement_H4.ks` | alpha cascade de financement |
| `Operation_x501_Alpha3_Eruption_Volatilite_H4.ks` | alpha éruption de volatilité |
| `Operation_x501_Alpha4_Confluence_MTF_H4.ks` | alpha confluence multi-timeframe |
| `x501_observe_flow_H1.ks` / `x501_observe_cvd4_btc_H1.ks` | collecteurs d'observation (zéro ordre, C4) |
| `x501_observe_om_v29.ks` | **v29 (docs/37)** — collecteur d'observation openmarket zéro ordre : structure + régime + OI + funding, outils gratuits (zéro abonnement) |
| `x501_setup_kscript.js` | l'installation codifiée des kScripts |
| `x501_backtest_trades_BTCUSDT.csv` / `_ETHUSDT.csv` | exemples de sortie backtest |
| `x501_exploit_audit.py` + `exploit_audit.json` | l'audit d'exploitation kScript (53 capacités × 13 scripts → **75,5 %** : sources premium 7/8, orderbook 2/3, broker 15/16 — la case `profit=/loss=` en ticks REFUSÉE par design, docs/28) |
| `x501_verdict_ab.py` | **le moteur de verdict des A/B pré-enregistrés (docs/28)** : lit 2 CSV trades, bootstrap 10 000 seed 501, verdicts DATA_ABSENTE / PROMOTION / KILL / INCONCLU — stdlib pure, bit-à-bit, `--demo` pour la plomberie |
| `x501_fill_maker_surface.py` + `pool_P1_entrees.csv` + `fill_maker_surface.json` | **la chaîne de preuve maker (docs/29)** : surface de fill δ×TTL (80 symboles × 733 j = 2 053 015 tentatives), sélection réelle sur les 469 entrées du pool P1 (fallback −88,6 bps, biais concentré sur A4), grille δ×TTL, sortie analytique TP — verdict : delta réel +0,931 bps/jambe = 23,3 % du crédit MC v20 → candidat v21 (médianes 306,2 $ TTL=2 / 364,0 $ TTL=6) |
| `x501_mk_compteurs.py` | **la boucle de surveillance maker (docs/29 § 7)** : relevés CSV des compteurs `_MK` → test binomial exact → verdict INSUFFISANT / DIVERGENCE / CONFORME / DÉRIVE_BAS / DÉRIVE_HAUT — stdlib pure, `--demo` |
| `x501_flux_local.py` + `flux_local.json` | **le banc de test des flux dormants (docs/30, vague 5)** : le flux taker natif des klines (EMA 6/24/72 h) et le funding multi-années (3/7/30 j) en filtres continus, grille PRÉ-DÉCLARÉE 12 cellules + 2 sur le pool P1, verdict mécanique au critère AUC du domaine — **12/12 KILL** sur 2 053 975 barres (80 symboles × 1 092 j), plomberie prouvée vivante |
| `x501_abs_events_local.py` + `abs_events_local.json` | **le banc d'événements de l'absorption (docs/31, vague 6)** : le pattern absorption en PROXY klines, 3 définitions IMBRIQUÉES (E1/E2/E3) × 2 directions × 2 horizons = 12 cellules + prime de structure E3 vs E1 + projection pool P1 — verdict mécanique au critère AUC + seuil pré-déclaré (+6 bps) |
| `x501_refs_local.py` + `refs_local.json` | **le banc des références de liquidité (docs/32, vague 7)** : vwap de session + volume profile de la veille, grille PRÉ-DÉCLARÉE de 28 cellules aux DEUX hypothèses × 2 panels + pool P1 en CONTEXTE — **55 KILL / 1 INCONCLU / 0 CANDIDAT** (7ᵉ falsification) — numpy + `X501_DATA_DIR` |
| `x501_oi_local.py` + `oi_local.json` | **le banc de l'open interest 1h (docs/33, vague 8)** : capital brut (Étude A) + mouvement financé (Étude B) × horizons + pool P1 en CONTEXTE — **10/10 KILL** (AUC 0,4917–0,5019) sur 216 000 barres × 749 j, klines ET OI du même exchange, snapshot simultané JAMAIS lu — numpy + `X501_OI_DIR` |
| `x501_oi_regime_local.py` + `oi_regime_local.json` | **le banc de l'OI en contexte de régime (docs/34, vague 9)** : le NIVEAU du capital (z-score roulant) comme conditionneur — magnitude 3 KILL + 1 INCONCLU (H_R1 REFUSÉE), direction 4/4 KILL — **la 9ᵉ falsification** ; pool P1 : ΔR +0,469, P = 0,8192 (CONTEXTE, jamais promotion) — numpy + `X501_OI_DIR` |
| `x501_oi_ushape_local.py` + `oi_ushape_local.json` | **le banc de la forme en U de H_R1 (docs/35, vague 10)** : le U joint NON ÉTABLI (4/4 INCONCLU, composition pré-déclarée refuse), le côté bas seul → **2 CANDIDAT L2160** (AUC 0,4415/0,4454, Δ\|fwd\| +52 à +83 bps — les 2 premiers candidats marginaux du domaine), miroir directionnel 4/4 KILL ; pool strates : ΔR +0,934, P = 0,7381 (2ᵉ contexte) — numpy + `X501_OI_DIR` |
| `x501_lsr_local.py` + `lsr_local.json` | **le banc du LSR (docs/36, vague 11)** : la dernière source premium du filtre RI (72 000 lignes 4h + 13 200 lignes 1d sur ~2,74 ans) — contrarian NIVEAU 4/4 KILL (4h) ET 4/4 KILL (1d), flux du positionnement 1 j KILL, flux 7 j 2 INCONCLU sous le gate, pool P1 ΔR −0,315, P(Δ<0) = 0,8009 (3ᵉ contexte) — **la 10ᵉ falsification du domaine** — numpy + `X501_LSR_DIR` |
| `x501_collect_lsr_v11.py` + `x501_lsr_probe_v11.py` + `lsr_probe_v11.jsonl` | **le collecteur versionné du banc LSR (docs/36)** + la sonde de sémantique et sa preuve horodatée : Bybit v5 public (0 clé), `/v5/market/account-ratio` 4h/1d (pagination `cursor`), règle anti-partiel pré-enregistrée — la re-collecte n'est pas bit-compatible (data live) |
| `x501_collect_oi_v8.py` | **le collecteur versionné du banc OI (docs/33)** : Bybit v5 public (0 clé), klines 1h (pagination `end`) + OI 1h (pagination `cursor`), panel 12 symboles, JSONL + manifest — la reproductibilité porte sur l'étude à data fixée |
| `x501_probe_floor_v29.py` + `floor_v29.json` | **v29 (docs/37) — la sonde des PLANCHERS de données** : bisection 1 j sur 2 venues (Bybit + Binance fapi) × 12 symboles, date de listing perp USDT mesurée par symbole → l'horizon MAX de backtest (pool 12 = 3,42 ans ; 6 ans sur 9 symboles ; BTC 7,07 ans) |
| `x501_collect_deep_v29.py` + `collect_deep_v29.json` | **v29 (docs/37) — le collecteur DEEP** : klines 1h jusqu'au plancher de listing (Bybit 12 symboles + Binance 9 symboles = 1 041 871 barres) + funding Binance vers plancher (76 479 pts) — pacing weight-aware (0,42 s), backoffs 429/418, INSERT OR IGNORE UNIQUE, ts funding en SECONDES — DB locale git-ignorée (`om_v27.db`, tables `*_deep`) |
| `x501_baseline_6y_v29.py` + `baseline_6y_v29.json` | **v29 (docs/37) — la BASELINE 6 ANS** : f24 / MFE48 / MAE48 / vol par année sur 9 symboles × 6-7 ans, funding APR par année, stationnarité 60/40 chrono GLOBAL (train +33,8 → test +8,4 bps), cohérence cross-venue (méd 1,2–4,2 bps), 0 trou — la fenêtre de calibration MC v20 (23 mois) = pire cas du cycle 2019-2026 |
| `x501_collect_deep40_v31.py` + `collect_deep40_v31.json` | **v31 (docs/38) — le collecteur DEEP 40 SYMBOLES** : Binance Vision (zips mensuels/daily, sans rate-limit, taker natif) + compléments API blindés + Bybit API backward — 1 817 324 barres bn / 40 sym (BTC 2019-09-08 →), 528 077 bb / 12 sym, 238 616 fundings — le trou ICPUSDT 627 h est RÉEL (vérifié absent de Binance) |
| `qa_deep40_v31.py` | **v31 (docs/38) — la QA de la base deep 40 sym + du pool** : 15 contrôles (contiguïté 2 venues, 0 NULL taker, funding 8 h pile, cross-venue méd ≤ 5 bps, pool 868 bit à bit, cohérence research) — PASS ; skips déclarés sans data locale |
| `x501_v8_scale_deep_v31.py` + `research_v8_deep.json` + `trades_v8_deep.csv` | **v31 (docs/38) — le HARNAIS v8 porté sur la base deep** (transformation contrôlée du source v8, moteur bit à bit) : 40 perps × 82,8 mois, L1 gate ATR REJETÉ 4/4, L2 → V3 retenu, pool 868 trades E[R] +0,093 (sat +0,135), A3 +0,210 / A4 +0,119 — contraction ÷1,9 seulement (vs ÷4,5 moteur 8 sym v30) |
| `x501_mc_v31.py` + `mc_v31.json` | **v31 (docs/38) — le MC du pool v8 deep** (noyau v12 bit à bit, 12 000 chemins × 5 scénarios coûts v20) : W0 146,7 $ [100;253] P250 30,3 %, bande 97,5–146,7 $, maxDD 25,000000 % inviolé, P(50 100)@12m = 0,00 % — audits T2/T3 OK |
| `qa_kscript_x501.py` | QA générale des stratégies (doc kScript scrapée) |
| `qa_scanner_x501.py` | QA du scanner (49 contrôles) |
| `qa_maker_x501.py` | QA des versions maker (M1–M15, non-régression M13) |
| `qa_observe_x501.py` | QA des collecteurs d'observation (13 contrôles/fichier) |
| `qa_vagues_x501.py` | QA des vagues 1-2-3 : RI + observe régime + absorption + les 2 `_MK` + le moteur de verdict (200 contrôles : no-repaint, fail-open, budget sources ≤ 10, pièges doc, piège OCA, pré-enregistrement, cohérence docs/28 ↔ moteur) |
| `qa_fill_maker_x501.py` | QA de la preuve maker (71 contrôles, 74 avec la re-exécution bit à bit) |
| `qa_flux_local_x501.py` | QA du banc de flux (27 contrôles) : grille + verdicts + étalonnage AUC exact + **TEST D'ALTÉRATION** (look-ahead = l'AUC décolle) + zéro look-ahead par mutation + convention funding + pool 469 + AUC par symbole + re-exécution bit à bit |
| `qa_abs_events_x501.py` | QA du banc d'événements (62 contrôles, 9 familles) : détecteur sur séries synthétiques, invariant réel tbqv ≤ qv, nesting E3 ⊆ E2 ⊆ E1, zéro look-ahead par mutation, re-exécution bit à bit |
| `qa_refs_local_x501.py` | QA du banc des références (39 contrôles) : plomberie vivante (aimant planté AUC 0,911, continuation 0,929), zéro look-ahead par mutation, re-exécution bit à bit (digest 6af839e09c6136e8…) |
| `qa_oi_local_x501.py` | QA du banc OI (47 contrôles) : détecteur planté AUC 0,66 CANDIDAT / cas nul KILL, zéro look-ahead par MUTATION multiplicative+additive des snapshots futurs, pool 469/469, re-exécution bit à bit (digest b4b55400b05a69d1…) |
| `qa_oi_regime_x501.py` | QA du banc régime (63 contrôles) : rolling_z en unitaires (bug réel des fenêtres plates → NaN corrigé), détecteur monotone décalé, snapshot simultané jamais lu (test segmenté), re-exécution bit à bit (digest bf0b77ac6a74d8be…) |
| `qa_oi_ushape_x501.py` | QA du banc U-shape (79 contrôles, 1 skip déclaré) : détecteur du U planté → composition U VIVANT, détecteur MONOTONE refusé → KILL-U, composition en 7 branches, 2 bugs de CAS corrigés, re-exécution bit à bit (digest 3f9fb7781eaeb401…) |
| `qa_lsr_local_x501.py` | QA du banc LSR (49 contrôles) : détecteur contrarian planté sur pipeline synthétique en 3 runs, zéro look-ahead par mutation LSR + opens klines, ligne simultanée jamais lue, pool 469/469, re-exécution bit à bit (digest c8478385f7fce150…) |

## Comment valider (une commande, zéro dépendance)

```bash
cd scripts/studies/x501_openmarket
python3 qa_kscript_x501.py && python3 qa_scanner_x501.py \
  && python3 qa_maker_x501.py && python3 qa_observe_x501.py \
  && python3 qa_vagues_x501.py && python3 qa_fill_maker_x501.py \
  && python3 qa_flux_local_x501.py && python3 qa_abs_events_x501.py
```

Attendu : **8× PASS — 0 échec** (446 contrôles au total, +3 avec la data
premium pour les re-exécutions bit à bit ; les QA `qa_refs_local_x501.py`,
`qa_oi_local_x501.py`, `qa_oi_regime_x501.py`, `qa_oi_ushape_x501.py` et
`qa_lsr_local_x501.py` s'exécutent en plus avec leur data :
`X501_DATA_DIR` / `X501_OI_DIR` / `X501_LSR_DIR`). Certaines QA
écrivent leurs détails JSON dans `results/` (artefact de run local — ne pas
commiter). Aucune dépendance externe : stdlib pure (numpy requis pour les
études avec data 1h). Les bancs v29 (planchers / collecte deep / baseline
6 ans) s'exécutent contre la DB locale `om_v27.db` — hors git par design.

## Statut (02/10/2026)

- **v31 — le harnais v8 officiel est porté sur la base deep « depuis le début de l'actif »**
  (`docs/40-openmarket-harnais-deep-40sym.md`) : base étendue 9 → **40 symboles** via Binance Vision
  (2,34 M barres au total, QA 15 contrôles PASS, trou ICP réel documenté) ; portage par transformation
  contrôlée (moteur/règles bit à bit) ; **L1 gate ATR REJETÉ 4/4, L2 → V3 retenu** ; pool 868 trades
  E[R] +0,093 (contraction ÷1,9 vs fenêtre 34 mois — 2,4× plus douce que le moteur 8 sym) ;
  **MC v31 : W0 146,7 $ [100;253], P(50 100)@12m = 0,00 %, maxDD 25,000000 % inviolé** —
  le re-chiffrement le plus complet du domaine, meilleure configuration mesurée (+25 % vs v30).
- **v29 — l'horizon de backtest est verrouillé « depuis le début de l'actif » et la base deep est en place** (`docs/37-openmarket-horizon-backtest.md`) : sonde des planchers (bisection 2 venues × 12 symboles — la limite est le LISTING des perps USDT, pas l'API), collecte deep **1 041 871 barres klines 1h + 76 479 fundings, 0 trou, cohérence cross-venue méd 1,2–4,2 bps** (p99 ≤ 16,3) ; pool 12/12 = **3,42 ans**, **6 ans validés sur 9/12 symboles**, plafond absolu **7,07 ans (BTC)** ; baseline 6 ans : 513 637 obs f24, stationnarité 60/40 chrono train **+33,8 → test +8,4 bps** (même signe, contraction ×4), f24 BTC 2025-2026 ~0 bps, funding APR 30,6 % (2021) → 2,9 % (2026), MFE48 médian 3,69 % → 1,76 % — **la fenêtre de calibration MC v20 (23 mois) est le PIRE CAS du cycle 2019-2026** : la trajectoire officielle reste calibrée conservatrice.
- 10/10 QA **PASS** (200 contrôles pour `qa_vagues_x501.py`, les existantes re-vérifiées) :
  `qa_oi_local_x501.py` (47), `qa_fill_maker_x501.py` (71→74), `qa_flux_local_x501.py` (27,
  test d'altération AUC look-ahead BTC 0,6103 / ETH 0,6065), `qa_oi_regime_x501.py` (63),
  `qa_oi_ushape_x501.py` (79, 1 skip), `qa_lsr_local_x501.py` (49) — re-exécutions bit à bit,
  digests gravés.
- **Vague 11 — le banc du LSR : la dernière source premium est fermée, la 10ᵉ falsification**
  (`docs/36-openmarket-lsr-banc-local.md`) : contrarian NIVEAU KILL 4/4 (4h) ET 4/4 (1d),
  flux 1 j KILL, flux 7 j 2 INCONCLU 2–3× sous le gate ; 10/12 cellules AUC < 0,5 ; le pool P1
  sépare dans le sens contrarian (ΔR −0,315, P(Δ<0) = 0,8009, 3ᵉ contexte, jamais promu).
- **Vague 10 — le banc de la FORME EN U : le U joint NON ÉTABLI, le côté bas CANDIDAT**
  (`docs/35-openmarket-oi-ushape.md`) : 4/4 INCONCLU + miroir KILL 4/4 (falsifications
  restent à 9) MAIS le côté bas franchit le gate à L = 2160 (AUC 0,4415 / 0,4454, Δ|fwd|
  +52 à +83 bps) — les 2 premiers candidats marginaux du domaine en 10 vagues ; pool strates
  2ᵉ contexte (ΔR +0,934, P = 0,7381) ; candidats au protocole A/B sans toucher à la file.
- **Vague 9 — l'OI en contexte de régime est FERMÉ pour le mécanisme marginal**
  (`docs/34-oi-regime-banc-local.md`) : H_R1 REFUSÉE (3 KILL + 1 INCONCLU), direction 4/4
  KILL ; pool P1 franchit le gate de contexte (ΔR +0,469, P = 0,8192, n = 181).
- **Vague 8 — le banc de l'open interest 1h est FERMÉ** (`docs/33-oi-banc-local.md`) :
  10/10 KILL aux deux hypothèses, collecteur versionné — la 8ᵉ falsification du domaine.
- **Vague 7 — le banc des références de liquidité est FERMÉ** (`docs/32-references-banc-local.md`) :
  55 KILL / 1 INCONCLU / 0 CANDIDAT sur 56 cellules (2 048 055 décisions) ; meilleur delta
  +44,4 bps H72 reste KILL (AUC 0,5136) ; plomberie vivante (aimant 0,911, continuation 0,929) —
  la famille analyse de docs/27 est CLOSE.
- **Vague 6 — le banc d'événements de l'absorption est FERMÉ en ombre klines**
  (`docs/31-absorption-banc-evenements.md`) : prime de structure E3 vs E1 RÉFUTÉE 0/4
  (−26,4/−54,2 bps LONG), le proxy sélectionne la plaine illiquide (62,7 % de forwards nuls) ;
  pool P1 12/469, ΔR +0,13, P = 0,652 — **ABS_DEPRIORISE** (file RI → MK6 → TRAIL → ABS).
- **Vague 5 — le banc de test des flux dormants est FERMÉ** (`docs/30-flux-funding-banc-local.md`) :
  **12/12 cellules KILL** (2 053 975 barres) ; pool P1 : flux +0,089 R (P = 0,686), funding
  −0,096 R (P = 0,359).
- **⚠ Révision exécution (docs/29)** : la mesure reproductible (surface δ×TTL + sélection pool P1)
  donne 93,82 % aux barres de signal avec fallback taker à **−88,6 bps** : le maker réel vaut
  +0,931 bps/jambe et non 4,0 → candidat v21 (306,2 $ / 364,0 $ TTL=6) en attente de review.
  La grille montre que TTL=6 triple le delta (+2,897 bps) : run MK6 pré-enregistré au protocole
  A/B pour falsifier l'érosion temporelle. Les `_MK` gardent δ=2/TTL=2 par défaut —
  `useNativeTrail=false` : la référence MC v20 reste bit-à-bit tant que la review n'a pas tranché.
- **Vagues 1-2-3 activées** (registre d'exploitation : `docs/27-pouvoirs-kscript.md`) :
  le taux d'exploitation monte de 52,8 % à **75,5 %** (40/53) — 8 flux premium
  branchés (7/8), les 4 fonctions orderbook natives (2/3), le broker hygiène
  (15/16, `profit=/loss=` en ticks refusé par design). La vague 3 corrige un
  BUG RÉEL : un ordre limite maker pouvait remplir APRÈS le coupe-circuit -25 %.
- **Le protocole A/B est PRÉ-ENREGISTRÉ** (`docs/28-protocole-ab-x501.md`,
  critères figés le 01/10/2026, moteur `x501_verdict_ab.py` seed 501) :
  RI on/off sur BTC et ETH, absorption vs signature (+ trail natif on/off,
  + MK6 TTL=2 vs 6) — les CSV déposés dans `ab/`, le verdict tombe,
  l'entrée au registre `docs/20`.
- Protocoles d'exécution : `docs/reference/openmarket-x501/PROTOCOLE_*`.
- Statut de la mission et roadmap : `docs/25-openmarket-x501.md`.
