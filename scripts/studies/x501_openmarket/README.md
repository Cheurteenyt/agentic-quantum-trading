# x501_openmarket/ — LE DOMAINE OPENMARKET (kScripts + QA)

**Le domaine de la mission x501** (100 $ → 50 100 $, DD ≤ 25 % —
`docs/25-openmarket-x501.md`). Tout le code du domaine tient dans ce
dossier : les 12 kScripts, le scanner d'installation et les 6 QA statiques.
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
| `qa_kscript_x501.py` | QA générale des 5 stratégies (doc kScript scrapée) |
| `qa_scanner_x501.py` | QA du scanner (49 contrôles) |
| `qa_maker_x501.py` | QA des versions maker (M1–M15, non-régression M13) |
| `qa_observe_x501.py` | QA des collecteurs d'observation (13 contrôles/fichier) |
| `qa_vagues_x501.py` | QA des vagues 1-2-3 : RI + observe régime + absorption + les 2 `_MK` + le moteur de verdict (200 contrôles : no-repaint, fail-open, budget sources ≤ 10, pièges doc, piège OCA, pré-enregistrement, cohérence docs/28 ↔ moteur) |

## Comment valider (une commande, zéro dépendance)

```bash
cd scripts/studies/x501_openmarket
python3 qa_kscript_x501.py && python3 qa_scanner_x501.py \
  && python3 qa_maker_x501.py && python3 qa_observe_x501.py \
  && python3 qa_vagues_x501.py && python3 qa_fill_maker_x501.py
```

Attendu : **6× PASS — 0 échec** (357 contrôles au total, +3 avec la data
premium pour la re-exécution bit à bit). Certaines QA
écrivent leurs détails JSON dans `results/` (artefact de run local — ne pas
commiter). Aucune dépendance externe : stdlib pure, les fichiers cibles sont
résolus relativement à ce dossier (l'étude de fill a besoin de numpy et de la
data 1h : `X501_DATA_DIR`).

## Statut (01/10/2026)

- 5/5 QA **PASS** (200 contrôles pour `qa_vagues_x501.py`, les 4 existantes re-vérifiées)
  + `qa_fill_maker_x501.py` (**71 contrôles**, 74 avec la re-exécution bit à bit de l'étude).
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
