# x501_openmarket/ — LE DOMAINE OPENMARKET (kScripts + QA)

**Le domaine de la mission x501** (100 $ → 50 100 $, DD ≤ 25 % —
`docs/25-openmarket-x501.md`). Tout le code du domaine tient dans ce
dossier : les 12 kScripts, le scanner d'installation et les 7 QA statiques.
dossier : les 12 kScripts, le scanner d'installation et les 6 QA statiques.
origin/main
Les données restent locales (git-ignorées, `docs/26-openmarket-donnees.md`).

## Contenu

| Fichier | Rôle |
|---|---|
| `Operation_x501_Signature_H1.ks` / `_H4.ks` | le signal de base (signature), cadence H1 / H4 |
| `Operation_x501_Signature_H1_MK.ks` / `_H4_MK.ks` | **les versions maker** (limite δ=2–5, TTL, fallback taker, verrous pend*) + **vague 3 (docs/27-28)** : trail natif du runner (`useNativeTrail`, défaut false), groupes OCA nommés par tranche, `cancelAll()` post-halt (bug réel corrigé), rapport fin de run natif (closedTradeCount/WR/maxDrawdown) |
<<<<<<< HEAD
| `Operation_x501_Signature_H1_MK.ks` / `_H4_MK.ks` | **les versions maker** (limite δ=2–5, TTL, fallback taker, verrous pend*) + **vague 3 (docs/27-28)** : trail natif du runner (`useNativeTrail`, défaut false), groupes OCA nommés par tranche, `cancelAll()` post-halt (bug réel corrigé), rapport fin de run natif (closedTradeCount/WR/maxDrawdown) |
=======
<<<<<<< HEAD
| `Operation_x501_Signature_H1_MK.ks` / `_H4_MK.ks` | **les versions maker** (limite δ=2–5, TTL, fallback taker, verrous pend*) + **vague 3 (docs/27-28)** : trail natif du runner (`useNativeTrail`, défaut false), groupes OCA nommés par tranche, `cancelAll()` post-halt (bug réel corrigé), rapport fin de run natif (closedTradeCount/WR/maxDrawdown) |
=======
| `Operation_x501_Signature_H1_MK.ks` / `_H4_MK.ks` | **les versions maker** (limite δ=2–5, TTL, fallback taker, verrous pend*) |
origin/main
origin/main
>>>>>>> origin/main
>>>>>>> origin/main
| `Operation_x501_Signature_H1_RI.ks` | **vague 1 (docs/27)** — la Signature H1 + le filtre de RÉGIME INSTITUTIONNEL : score RI = 5 composantes écrêtées (ETF flow 3 j, CME OI × signe prix, DVOL vs MM 30, skew 1W, LSR contrarian), seuil ±0,10, no-repaint via buckets quotidiens complétés (`htf 1D`, jamais `[0]`), fail-open si les flux sont absents |
| `x501_observe_regime.ks` | **vague 1** — l'observe des 8 flux premium : table de disponibilité par flux, composantes RI brutes, alerte de bascule de quadrant (9 souscriptions) |
| `Operation_x501_Absorption_H1.ks` | **vague 2 (docs/27)** — l'absorption orderbook NATIVE : mur = `maxBidAmount`/`maxAskAmount` ≥ 3× sa moyenne 200, attaque = vague taker ≥ 2× sa moyenne, tenue = écrasement ≤ 0,8 %, reprise = EMA flux net + déséquilibre `sumBids`/`sumAsks` ≥ 1,2 — le pattern qui a produit l'AL Score d'Aster, dans le backtester |
| `Operation_x501_Alpha2_Cascade_Financement_H4.ks` | alpha cascade de financement |
| `Operation_x501_Alpha3_Eruption_Volatilite_H4.ks` | alpha éruption de volatilité |
| `Operation_x501_Alpha4_Confluence_MTF_H4.ks` | alpha confluence multi-timeframe |
| `x501_observe_flow_H1.ks` / `x501_observe_cvd4_btc_H1.ks` | collecteurs d'observation (zéro ordre, C4) |
| `x501_setup_kscript.js` | l'installation codifiée des kScripts |
| `x501_backtest_trades_BTCUSDT.csv` / `_ETHUSDT.csv` | exemples de sortie backtest |
<<<<<<< HEAD
origin/main
origin/main
| `x501_exploit_audit.py` + `exploit_audit.json` | l'audit d'exploitation kScript (53 capacités × 13 scripts → **75,5 %** : sources premium 7/8, orderbook 2/3, broker 15/16 — la case `profit=/loss=` en ticks REFUSÉE par design, docs/28) |
| `x501_verdict_ab.py` | **le moteur de verdict des A/B pré-enregistrés (docs/28)** : lit 2 CSV trades, bootstrap 10 000 seed 501, verdicts DATA_ABSENTE / PROMOTION / KILL / INCONCLU — stdlib pure, bit-à-bit, `--demo` pour la plomberie |
| `x501_fill_maker_surface.py` + `pool_P1_entrees.csv` + `fill_maker_surface.json` | **la chaîne de preuve maker (docs/29)** : surface de fill δ×TTL (80 symboles × 733 j = 2 053 015 tentatives), sélection réelle sur les 469 entrées du pool P1 (fallback −88,6 bps, biais concentré sur A4), grille δ×TTL, sortie analytique TP — verdict : delta réel +0,931 bps/jambe = 23,3 % du crédit MC v20 → candidat v21 (médianes 306,2 $ TTL=2 / 364,0 $ TTL=6) |
| `x501_mk_compteurs.py` | **la boucle de surveillance maker (docs/29 § 7)** : relevés CSV des compteurs `_MK` → test binomial exact → verdict INSUFFISANT / DIVERGENCE / CONFORME / DÉRIVE_BAS / DÉRIVE_HAUT — stdlib pure, `--demo` |
| `x501_flux_local.py` + `flux_local.json` | **le banc de test des flux dormants (docs/30, vague 5)** : le flux taker natif des klines (EMA 6/24/72 h) et le funding multi-années (3/7/30 j) en filtres continus, grille PRÉ-DÉCLARÉE 12 cellules + 2 sur le pool P1, verdict mécanique au critère AUC du domaine — **12/12 KILL** sur 2 053 975 barres (80 symboles × 1 092 j), plomberie prouvée vivante |
| `x501_abs_events_local.py` + `abs_events_local.json` | **le banc d'événements de l'absorption (docs/31, vague 6)** : le pattern absorption en PROXY klines (mur volume T−3 ≥ 3× SMA200, attaque directionnelle T−2 ≥ 2× SMA100, tenue T−1 à 0,8 %, reprise T−1 = EMA(D,6) bascule), 3 définitions IMBRIQUÉES (E1 attaque / E2 structure / E3 complet) × 2 directions × 2 horizons = 12 cellules + prime de structure E3 vs E1 + projection pool P1 — verdict mécanique au critère AUC + seuil pré-déclaré (+6 bps = ½ aller-retour taker) |
=======
<<<<<<< HEAD
| `x501_exploit_audit.py` + `exploit_audit.json` | l'audit d'exploitation kScript (53 capacités × 13 scripts → **75,5 %** : sources premium 7/8, orderbook 2/3, broker 15/16 — la case `profit=/loss=` en ticks REFUSÉE par design, docs/28) |
| `x501_verdict_ab.py` | **le moteur de verdict des A/B pré-enregistrés (docs/28)** : lit 2 CSV trades, bootstrap 10 000 seed 501, verdicts DATA_ABSENTE / PROMOTION / KILL / INCONCLU — stdlib pure, bit-à-bit, `--demo` pour la plomberie |
=======
| `x501_exploit_audit.py` + `exploit_audit.json` | l'audit d'exploitation kScript (53 capacités × 13 scripts → **67,9 %** : sources premium 7/8, orderbook 2/3) |
origin/main
origin/main
>>>>>>> origin/main
>>>>>>> origin/main
| `qa_kscript_x501.py` | QA générale des 5 stratégies (doc kScript scrapée) |
| `qa_scanner_x501.py` | QA du scanner (49 contrôles) |
| `qa_maker_x501.py` | QA des versions maker (M1–M15, non-régression M13) |
| `qa_observe_x501.py` | QA des collecteurs d'observation (13 contrôles/fichier) |
| `qa_vagues_x501.py` | QA des vagues 1-2-3 : RI + observe régime + absorption + les 2 `_MK` + le moteur de verdict (200 contrôles : no-repaint, fail-open, budget sources ≤ 10, pièges doc, piège OCA, pré-enregistrement, cohérence docs/28 ↔ moteur) |
| `qa_flux_local_x501.py` | QA du banc de flux (27 contrôles) : grille + verdicts + étalonnage AUC exact + **TEST D'ALTÉRATION** (look-ahead = l'AUC décolle : la plomberie voit un vrai signal) + zéro look-ahead (mutation des barres futures) + convention funding recalculée + pool 469 + AUC par symbole (anti-dilution) + re-exécution bit à bit |
| `qa_abs_events_x501.py` | QA du banc d'événements (62 contrôles, 9 familles) : le DÉTECTEUR testé sur séries synthétiques (chaque condition violée isolément + anti-batterie-triviale), invariant réel tbqv ≤ qv, nesting E3 ⊆ E2 ⊆ E1 sur données réelles, zéro look-ahead par mutation, règle NON_INTERPRETABLE en unitaire, re-exécution bit à bit |
<<<<<<< HEAD
| `qa_vagues_x501.py` | QA des vagues 1-2-3 : RI + observe régime + absorption + les 2 `_MK` + le moteur de verdict (200 contrôles : no-repaint, fail-open, budget sources ≤ 10, pièges doc, piège OCA, pré-enregistrement, cohérence docs/28 ↔ moteur) |
=======
<<<<<<< HEAD
| `qa_vagues_x501.py` | QA des vagues 1-2-3 : RI + observe régime + absorption + les 2 `_MK` + le moteur de verdict (200 contrôles : no-repaint, fail-open, budget sources ≤ 10, pièges doc, piège OCA, pré-enregistrement, cohérence docs/28 ↔ moteur) |
=======
| `qa_vagues_x501.py` | QA des vagues 1-2 : RI + observe régime + absorption (122 contrôles : no-repaint, fail-open, budget sources ≤ 10, pièges doc, pré-enregistrement) |
origin/main
origin/main
>>>>>>> origin/main
>>>>>>> origin/main

## Comment valider (une commande, zéro dépendance)

```bash
cd scripts/studies/x501_openmarket
python3 qa_kscript_x501.py && python3 qa_scanner_x501.py \
  && python3 qa_maker_x501.py && python3 qa_observe_x501.py \
  && python3 qa_vagues_x501.py && python3 qa_fill_maker_x501.py \
  && python3 qa_flux_local_x501.py && python3 qa_abs_events_x501.py
```

Attendu : **8× PASS — 0 échec** (446 contrôles au total, +3 avec la data
  && python3 qa_flux_local_x501.py
```

Attendu : **7× PASS — 0 échec** (384 contrôles au total, +3 avec la data
origin/main
premium pour les re-exécutions bit à bit). Certaines QA
écrivent leurs détails JSON dans `results/` (artefact de run local — ne pas
commiter). Aucune dépendance externe : stdlib pure (numpy requis pour les
2 études avec data 1h : `X501_DATA_DIR`).

## Statut (01/10/2026)

- 8/8 QA **PASS** (200 contrôles pour `qa_vagues_x501.py`, les 7 existantes re-vérifiées)
<<<<<<< HEAD
  && python3 qa_vagues_x501.py && python3 qa_fill_maker_x501.py
```

Attendu : **6× PASS — 0 échec** (357 contrôles au total, +3 avec la data
premium pour la re-exécution bit à bit). Certaines QA
écrivent leurs détails JSON dans `results/` (artefact de run local — ne pas
commiter). Aucune dépendance externe : stdlib pure, les fichiers cibles sont
résolus relativement à ce dossier (l'étude de fill a besoin de numpy et de la
data 1h : `X501_DATA_DIR`).
origin/main

## Statut (01/10/2026)

- 5/5 QA **PASS** (200 contrôles pour `qa_vagues_x501.py`, les 4 existantes re-vérifiées)
origin/main
  + `qa_fill_maker_x501.py` (**71 contrôles**, 74 avec la re-exécution bit à bit de l'étude)
  + `qa_flux_local_x501.py` (**27 contrôles**, dont le test d'altération qui prouve que la
  plomberie du banc détecte un vrai signal : AUC look-ahead BTC 0,6103 / ETH 0,6065).
- **Vague 5 — le banc de test des flux dormants est FERMÉ** (`docs/30-flux-funding-banc-local.md`) :
  le flux taker natif des klines et le funding multi-années, derniers pouvoirs data dormants,
  passés au banc AVANT tout run kScript — **12/12 cellules KILL** au critère AUC du domaine
  (80 symboles × 1 092 j = 2 053 975 barres, 0 gap, grille pré-déclarée, re-exécution bit à
  bit) ; le pool P1 (CONTEXTE) : flux delta +0,089 R (P = 0,686, INCONCLU), funding
  −0,096 R (P = 0,359). Le pattern absorption ÉVÉNEMENTIEL (vague 2) n'est pas réfuté —
  son juge reste le protocole A/B.
- **Vague 6 — le banc d'événements de l'absorption est FERMÉ en ombre klines** (`docs/31-absorption-banc-evenements.md`) :
  prime de structure E3 vs E1 **RÉFUTÉE 0/4** (−26,4/−54,2 bps LONG : la confirmation est TARDIVE,
  le rebond se joue dans la barre de tenue ; SHORT anti-signal AUC 0,477–0,489 : le mur perd) ;
  le proxy du mur sélectionne la plaine illiquide (62,7 % de rendements forward exactement nuls) ;
  pool P1 : 12/469 matchés, ΔR +0,13, P = 0,652 (INCONCLU) — **ABS_DEPRIORISE** : file de runs
  recommandée RI → MK6 → TRAIL → ABS (`docs/28`), le pattern orderbook réel reste jugé par le protocole.
  + `qa_fill_maker_x501.py` (**71 contrôles**, 74 avec la re-exécution bit à bit de l'étude).
origin/main
origin/main
- **⚠ Révision exécution (docs/29)** : le fill « 97,9 % à δ=2 » durci dans la MC v20
  n'avait pas sa méthode versionnée — la mesure reproductible (surface δ×TTL +
  sélection sur le pool P1) donne 93,82 % aux barres de signal, avec un fallback
  taker à **−88,6 bps** (sélection adverse concentrée sur A4) : le maker réel vaut
  +0,931 bps/jambe et non 4,0 → candidat v21 (306,2 $ / 364,0 $ TTL=6) en attente
  de review. La grille montre que TTL=6 triple le delta (+2,897 bps) : run MK6
  pré-enregistré au protocole A/B (docs/28) pour falsifier l'érosion temporelle.
- Les `_MK` gardent δ=2/TTL=2 par défaut — `useNativeTrail=false` : la référence
  MC v20 reste bit-à-bit tant que la review n'a pas tranché.
=======
  && python3 qa_vagues_x501.py
```

<<<<<<< HEAD
Attendu : **5× PASS — 0 échec** (286 contrôles au total). Certaines QA
=======
Attendu : **5× PASS — 0 échec** (208 contrôles au total). Certaines QA
origin/main
écrivent leurs détails JSON dans `results/` (artefact de run local — ne pas
commiter). Aucune dépendance externe : stdlib pure, les fichiers cibles sont
résolus relativement à ce dossier.

## Statut (01/10/2026)

- 5/5 QA **PASS** (200 contrôles pour `qa_vagues_x501.py`, les 4 existantes re-vérifiées).
- Les `_MK` sont la version d'exécution de référence (fill 97,9 % à δ=2) —
  `useNativeTrail=false` par défaut : la référence MC v20 reste bit-à-bit.
origin/main
>>>>>>> origin/main
>>>>>>> origin/main
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
<<<<<<< HEAD
  RI on/off sur BTC et ETH, absorption vs signature (+ trail natif on/off,
  + MK6 TTL=2 vs 6) — les CSV déposés dans `ab/`, le verdict tombe,
  l'entrée au registre `docs/20`.
<<<<<<< HEAD
  RI on/off sur BTC et ETH, absorption vs signature (+ trail natif on/off,
  + MK6 TTL=2 vs 6) — les CSV déposés dans `ab/`, le verdict tombe,
  l'entrée au registre `docs/20`.
=======
  RI on/off sur BTC et ETH, absorption vs signature (+ trail natif on/off) —
  les CSV déposés dans `ab/`, le verdict tombe, l'entrée au registre `docs/20`.
=======
- 5/5 QA **PASS** (122 contrôles pour `qa_vagues_x501.py`, les 4 existantes inchangées).
- Les `_MK` sont la version d'exécution de référence (fill 97,9 % à δ=2).
- **Vagues 1-2 activées** (registre d'exploitation : `docs/27-pouvoirs-kscript.md`) :
  le taux d'exploitation monte de 52,8 % à **67,9 %** (36/53) — 8 flux premium
  branchés (sources premium 1/8 → 7/8), les 4 fonctions orderbook natives
  utilisées (1/3 → 2/3). Backtests A/B pré-enregistrés à exécuter :
  RI on/off sur BTC et ETH, absorption vs signature — verdict au registre `docs/20`.
- **Vague 3 (hygiène, aucun edge espéré)** : `trailPoints` dans les `_MK`,
  `ocaName`, `strategy.maxDrawdown()` dans les rapports — à faire.
origin/main
origin/main
>>>>>>> origin/main
>>>>>>> origin/main
- Protocoles d'exécution : `docs/reference/openmarket-x501/PROTOCOLE_*`.
- Statut de la mission et roadmap : `docs/25-openmarket-x501.md`.
