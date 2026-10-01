# x501_openmarket/ — LE DOMAINE OPENMARKET (kScripts + QA)

**Le domaine de la mission x501** (100 $ → 50 100 $, DD ≤ 25 % —
`docs/25-openmarket-x501.md`). Tout le code du domaine tient dans ce
dossier : les 12 kScripts, le scanner d'installation et les 10 QA statiques.
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
| `x501_setup_kscript.js` | l'installation codifiée des kScripts |
| `x501_backtest_trades_BTCUSDT.csv` / `_ETHUSDT.csv` | exemples de sortie backtest |
| `x501_exploit_audit.py` + `exploit_audit.json` | l'audit d'exploitation kScript (53 capacités × 13 scripts → **75,5 %** : sources premium 7/8, orderbook 2/3, broker 15/16 — la case `profit=/loss=` en ticks REFUSÉE par design, docs/28) |
| `x501_verdict_ab.py` | **le moteur de verdict des A/B pré-enregistrés (docs/28)** : lit 2 CSV trades, bootstrap 10 000 seed 501, verdicts DATA_ABSENTE / PROMOTION / KILL / INCONCLU — stdlib pure, bit-à-bit, `--demo` pour la plomberie |
| `x501_fill_maker_surface.py` + `pool_P1_entrees.csv` + `fill_maker_surface.json` | **la chaîne de preuve maker (docs/29)** : surface de fill δ×TTL (80 symboles × 733 j = 2 053 015 tentatives), sélection réelle sur les 469 entrées du pool P1 (fallback −88,6 bps, biais concentré sur A4), grille δ×TTL, sortie analytique TP — verdict : delta réel +0,931 bps/jambe = 23,3 % du crédit MC v20 → candidat v21 (médianes 306,2 $ TTL=2 / 364,0 $ TTL=6) |
| `x501_mk_compteurs.py` | **la boucle de surveillance maker (docs/29 § 7)** : relevés CSV des compteurs `_MK` → test binomial exact → verdict INSUFFISANT / DIVERGENCE / CONFORME / DÉRIVE_BAS / DÉRIVE_HAUT — stdlib pure, `--demo` |
| `x501_flux_local.py` + `flux_local.json` | **le banc de test des flux dormants (docs/30, vague 5)** : le flux taker natif des klines (EMA 6/24/72 h) et le funding multi-années (3/7/30 j) en filtres continus, grille PRÉ-DÉCLARÉE 12 cellules + 2 sur le pool P1, verdict mécanique au critère AUC du domaine — **12/12 KILL** sur 2 053 975 barres (80 symboles × 1 092 j), plomberie prouvée vivante |
| `x501_abs_events_local.py` + `abs_events_local.json` | **le banc d'événements de l'absorption (docs/31, vague 6)** : le pattern absorption en PROXY klines (mur volume T−3 ≥ 3× SMA200, attaque directionnelle T−2 ≥ 2× SMA100, tenue T−1 à 0,8 %, reprise T−1 = EMA(D,6) bascule), 3 définitions IMBRIQUÉES (E1 attaque / E2 structure / E3 complet) × 2 directions × 2 horizons = 12 cellules + prime de structure E3 vs E1 + projection pool P1 — verdict mécanique au critère AUC + seuil pré-déclaré (+6 bps = ½ aller-retour taker) |
| `x501_refs_local.py` + `refs_local.json` | **le banc des références de liquidité (docs/32, vague 7)** : vwap de session (ancrage 00h UTC, reset journalier) + volume profile de la veille (48 bins, VPOC, value area 70 %), grille PRÉ-DÉCLARÉE de 28 cellules aux DEUX hypothèses (V1 aimant / V2 cross / P1 vpoc / P2 rejet VA / P3 breakout VA — P2 et P3 conditionnent les mêmes événements avec attentes opposées) × 2 panels (POOL80 + LIQUIDE8) + focus BTC/ETH + pool P1 en CONTEXTE (F1 mauvais côté vwap, F2 hors value area, flags sur open(T)) — 55 KILL / 1 INCONCLU / 0 CANDIDAT (7ᵉ falsification) — numpy + `X501_DATA_DIR` |
| `x501_oi_local.py` + `oi_local.json` | **le banc de l'open interest 1h (docs/33, vague 8)** : le capital affiché testé en TÉMOIN DE CONTINUATION — Étude A capital brut (ΔOI%_L, L ∈ {24,72,168}) + Étude B mouvement financé (signe(r_L)×ΔOI%, cible alignée, L ∈ {24,72}) × H ∈ {24,72} + pool P1 en CONTEXTE — 10/10 KILL (AUC 0,4917–0,5019) sur 216 000 barres × 749 j (12 symboles om_v27, klines ET OI du même exchange Bybit, 0 snapshot absent, snapshot simultané JAMAIS lu) — numpy + `X501_OI_DIR` |
| `x501_oi_regime_local.py` + `oi_regime_local.json` | **le banc de l'OI en contexte de régime (docs/34, vague 9)** : le NIVEAU du capital (z-score roulant L ∈ {720,2160}, std de population, fenêtre strictement au passé) comme conditionneur de la distribution des rendements — Étude A magnitude (H_R1 monotone, cible \|fwd\|, sens +1) : 3 KILL + 1 INCONCLU, la théorie du levier REFUSÉE ; Étude B direction (sens = 0, toute séparation = CONTEXTE) : 4/4 KILL — la 9ᵉ falsification ; Étude C pool P1 (z_720 au t_in, split médian, bootstrap 10 000) : ΔR +0,469, P = 0,8192 ≥ gate 0,70 (n = 181, CONTEXTE, jamais promotion) — numpy + `X501_OI_DIR` |
| `x501_oi_ushape_local.py` + `oi_ushape_local.json` | **le banc de la forme en U de H_R1 (docs/35, vague 10)** : la FORME concurrente pré-enregistrée (volatilité maximale aux DEUX extrêmes du régime, centre calme, centre pré-déclaré à 0) — Étude A1 le U joint (\|z_L\| → \|fwd\|, sens +1) : 4/4 INCONCLU (l'IC exclut 0,5 mais tous sous le gate 0,05) ; Étude A2 le côté bas seul (le DISCRIMINANT, sens −1) : 2 KILL L720 + **2 CANDIDAT L2160** (AUC 0,4415/0,4454, Δ\|fwd\| +52 à +83 bps — les 2 premiers candidats marginaux du domaine en 10 vagues) ; composition pré-déclarée : U NON ÉTABLI ×4 ; Étude B miroir directionnel : 4/4 KILL ; Étude C pool strates \|z_720\| ≥ q80 : ΔR +0,934, P = 0,7381 ≥ gate 0,70 (2ᵉ contexte, in-sample + cross-exchange, jamais promotion) — numpy + `X501_OI_DIR` |
| `x501_collect_oi_v8.py` | **le collecteur versionné du banc OI (docs/33)** : Bybit v5 public (0 clé), klines 1h (pagination `end`) + OI 1h (pagination `cursor`), panel 12 symboles, JSONL + manifest — la re-collecte n'est pas bit-compatible (data live), la reproductibilité porte sur l'étude à data fixée |
| `qa_kscript_x501.py` | QA générale des 5 stratégies (doc kScript scrapée) |
| `qa_scanner_x501.py` | QA du scanner (49 contrôles) |
| `qa_maker_x501.py` | QA des versions maker (M1–M15, non-régression M13) |
| `qa_observe_x501.py` | QA des collecteurs d'observation (13 contrôles/fichier) |
| `qa_vagues_x501.py` | QA des vagues 1-2-3 : RI + observe régime + absorption + les 2 `_MK` + le moteur de verdict (200 contrôles : no-repaint, fail-open, budget sources ≤ 10, pièges doc, piège OCA, pré-enregistrement, cohérence docs/28 ↔ moteur) |
| `qa_flux_local_x501.py` | QA du banc de flux (27 contrôles) : grille + verdicts + étalonnage AUC exact + **TEST D'ALTÉRATION** (look-ahead = l'AUC décolle : la plomberie voit un vrai signal) + zéro look-ahead (mutation des barres futures) + convention funding recalculée + pool 469 + AUC par symbole (anti-dilution) + re-exécution bit à bit |
| `qa_abs_events_x501.py` | QA du banc d'événements (62 contrôles, 9 familles) : le DÉTECTEUR testé sur séries synthétiques (chaque condition violée isolément + anti-batterie-triviale), invariant réel tbqv ≤ qv, nesting E3 ⊆ E2 ⊆ E1 sur données réelles, zéro look-ahead par mutation, règle NON_INTERPRETABLE en unitaire, re-exécution bit à bit |
| `qa_oi_local_x501.py` | QA du banc OI (47 contrôles) : le DÉTECTEUR (OI planté corrélé au forward → AUC 0,66 CANDIDAT, cas nul KILL), le zéro look-ahead par MUTATION multiplicative+additive des snapshots futurs (scores passés bit à bit), les 4 branches du verdict en unitaire, le pool 469/469 (entry = open×(1 + side×2 bps)), l'audit de collecte, la re-exécution bit à bit (digest gravé) |
| `qa_oi_regime_x501.py` | QA du banc régime (63 contrôles) : rolling_z en unitaires (cas à la main L=3, amorçage, boucle naïve, snapshot NaN propagé, fenêtre plate → NaN — bug réel corrigé), le DÉTECTEUR monotone (niveau planté dans la magnitude avec le décalage vague 8 → CANDIDAT ; la même plomberie décolle sur le signé pour l'étude B, verdict CONTEXTE forcé par sens=0), le cas nul KILL, le zéro look-ahead par MUTATION des snapshots ET des barres futures, le snapshot simultané jamais lu par sa barre (test segmenté), les 4 branches + sens=0 ne promeut jamais, le pool 469/469, l'audit de collecte, la re-exécution bit à bit (digest gravé) |
| `qa_oi_ushape_x501.py` | QA du banc U-shape (79 contrôles, 1 skip déclaré) : le DÉTECTEUR du U planté (magnitude en U dans le forward → A1 CANDIDAT + A2 CANDIDAT → composition **U VIVANT**), le DÉTECTEUR MONOTONE REFUSÉ par la composition (A2 sens opposé → **KILL-U** même si A1 décolle — le banc distingue les deux formes), le cas nul KILL, la COMPOSITION en 7 branches unitaires, le score \|z\| et la sélection A2 en cas à la main (2 bugs de CAS corrigés : médiane −1,5, premier jet plantait un monotone), le zéro look-ahead par MUTATION des snapshots ET des barres futures (scores signés ET \|z\| bit à bit), le snapshot simultané jamais lu, le pool 469/469, l'audit de collecte, la re-exécution bit à bit (digest gravé) |

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
`qa_oi_local_x501.py` et `qa_oi_regime_x501.py` s'exécutent en plus avec
leur data : `X501_DATA_DIR` / `X501_OI_DIR`). Certaines QA
écrivent leurs détails JSON dans `results/` (artefact de run local — ne pas
commiter). Aucune dépendance externe : stdlib pure (numpy requis pour les
études avec data 1h : `X501_DATA_DIR`, `X501_OI_DIR`).

## Statut (01/10/2026)

- 10/10 QA **PASS** (200 contrôles pour `qa_vagues_x501.py`, les existantes re-vérifiées)
  + `qa_oi_local_x501.py` (**47 contrôles**, 0 échec : détecteur planté AUC 0,66 / cas nul KILL,
  zéro look-ahead par mutation multiplicative+additive des snapshots OI futurs, re-exécution
  bit à bit de l'étude complète — digest b4b55400b05a69d1…, pool re-vérifié 469/469).
  + `qa_fill_maker_x501.py` (**71 contrôles**, 74 avec la re-exécution bit à bit de l'étude)
  + `qa_flux_local_x501.py` (**27 contrôles**, dont le test d'altération qui prouve que la
  plomberie du banc détecte un vrai signal : AUC look-ahead BTC 0,6103 / ETH 0,6065).
  + `qa_oi_regime_x501.py` (**63 contrôles**, 0 échec : rolling_z en unitaires avec le bug réel
  corrigé des fenêtres plates → NaN, détecteur monotone décalé vague 8, mutations snapshots
  + barres, snapshot simultané test segmenté, re-exécution bit à bit — digest bf0b77ac6a74d8be…).
  + `qa_oi_ushape_x501.py` (**79 contrôles**, 0 échec, 1 skip déclaré : le détecteur du U planté
  → composition U VIVANT, le détecteur MONOTONE refusé → KILL-U même si A1 décolle — le banc
  distingue les deux formes, la composition en 7 branches, 2 bugs de CAS de QA corrigés
  (médiane −1,5 ; premier jet plantait un monotone), mutations double, re-exécution bit à bit
  — digest 3f9fb7781eaeb401…).
- **Vague 10 — le banc de la FORME EN U : le U joint NON ÉTABLI, le côté bas de la purge
  CANDIDAT** (`docs/35-openmarket-oi-ushape.md`) : le U joint reste sous le gate du domaine
  (4/4 INCONCLU, la composition pré-déclarée refuse) et le miroir directionnel KILL 4/4 —
  le comptage des falsifications RESTE à 9 ; MAIS le côté bas de la purge franchit le gate
  à L = 90 j (AUC 0,4415 / 0,4454, sens −1 confirmé, Δ|fwd| +52 à +83 bps) — **les 2 premiers
  candidats marginaux du domaine en 10 vagues** — et le pool en strates |z| franchit le gate
  de contexte une 2ᵉ fois (ΔR +0,934, P = 0,7381) ; régime de purge unilatéral, candidats au
  protocole A/B sans toucher à la file (RI → MK6 → TRAIL → ABS).
- **Vague 9 — le banc de l'OI en contexte de régime est FERMÉ pour le mécanisme marginal**
  (`docs/34-oi-regime-banc-local.md`) : le NIVEAU du capital (z-score roulant) ne conditionne
  ni la magnitude (H_R1 de la théorie du levier REFUSÉE : 3 KILL + 1 INCONCLU) ni la direction
  (4/4 KILL) — la 9ᵉ falsification du domaine, 5ᵉ verdict symétrique des familles de
  positionnement ; le conditionnel pool P1 franchit le gate de contexte (ΔR +0,469,
  P = 0,8192 ≥ 0,70, n = 181) — filtre candidat au protocole A/B, jamais promotion depuis
  un banc, la file du user reste RI → MK6 → TRAIL → ABS.
- **Vague 8 — le banc de l'open interest 1h est FERMÉ** (`docs/33-oi-banc-local.md`) : 
  le capital affiché ne finance pas une direction prévisible — 10/10 KILL aux deux hypothèses
  (capital brut + mouvement financé), collecteur versionné, la 8ᵉ falsification du domaine.
  La case ouverte « OI en contexte de régime » → **fermée par la vague 9** (docs/34).
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
- **Vague 7 — le banc des références de liquidité est FERMÉ** (`docs/32-references-banc-local.md`) :
  vwap de session + volume profile de la veille, les 2 derniers pouvoirs d'analyse réels
  (les briques payantes de TradingView), passés au banc AVANT tout run — grille pré-déclarée
  de 28 cellules aux DEUX hypothèses (mean-reversion ET continuation, P2/P3 sur les mêmes
  événements avec attentes opposées) : **55 KILL / 1 INCONCLU / 0 CANDIDAT** sur 56 cellules
  (80 symboles × 1 092 j = 2 048 055 décisions, 288 s) ; le meilleur delta (+44,4 bps H72)
  reste KILL (AUC 0,5136, la queue n'est pas une séparation de rangs) ; pool P1 : F1
  mauvais côté vwap ΔR −0,581 (P = 0,42, INCONCLU au gate), F2 hors value area +0,148
  (P = 0,52) ; plomberie prouvée vivante (aimant planté AUC 0,911, continuation plantée
  0,929, zéro look-ahead par mutation — le profil de la journée en cours n'entre jamais),
  re-exécution bit à bit (39 contrôles, digest 6af839e09c6136e8…) — la famille analyse de
  docs/27 est CLOSE (ltf/minBid : sans data locale ; langage/visu : dette de style).
- **⚠ Révision exécution (docs/29)** : le fill « 97,9 % à δ=2 » durci dans la MC v20
  n'avait pas sa méthode versionnée — la mesure reproductible (surface δ×TTL +
  sélection sur le pool P1) donne 93,82 % aux barres de signal, avec un fallback
  taker à **−88,6 bps** (sélection adverse concentrée sur A4) : le maker réel vaut
  +0,931 bps/jambe et non 4,0 → candidat v21 (306,2 $ / 364,0 $ TTL=6) en attente
  de review. La grille montre que TTL=6 triple le delta (+2,897 bps) : run MK6
  pré-enregistré au protocole A/B (docs/28) pour falsifier l'érosion temporelle.
- Les `_MK` gardent δ=2/TTL=2 par défaut — `useNativeTrail=false` : la référence
  MC v20 reste bit-à-bit tant que la review n'a pas tranché.
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
