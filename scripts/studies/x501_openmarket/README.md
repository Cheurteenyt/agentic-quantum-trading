# x501_openmarket/ — LE DOMAINE OPENMARKET (kScripts + QA)

**Le domaine de la mission x501** (100 $ → 50 100 $, DD ≤ 25 % —
`docs/25-openmarket-x501.md`). Tout le code du domaine tient dans ce
dossier : les 12 kScripts, le scanner d'installation et les 6 QA statiques.
Les données restent locales (git-ignorées, `docs/26-openmarket-donnees.md`).

## Contenu

| Fichier | Rôle |
|---|---|
| `Operation_x501_Signature_H1.ks` / `_H4.ks` | le signal de base (signature), cadence H1 / H4 |
| `Operation_x501_Signature_H1_MK.ks` / `_H4_MK.ks` | **les versions maker** (limite δ=2–5, TTL, fallback taker, verrous pend*) |
| `Operation_x501_Signature_H1_RI.ks` | **vague 1 (docs/27)** — la Signature H1 + le filtre de RÉGIME INSTITUTIONNEL : score RI = 5 composantes écrêtées (ETF flow 3 j, CME OI × signe prix, DVOL vs MM 30, skew 1W, LSR contrarian), seuil ±0,10, no-repaint via buckets quotidiens complétés (`htf 1D`, jamais `[0]`), fail-open si les flux sont absents |
| `x501_observe_regime.ks` | **vague 1** — l'observe des 8 flux premium : table de disponibilité par flux, composantes RI brutes, alerte de bascule de quadrant (9 souscriptions) |
| `Operation_x501_Absorption_H1.ks` | **vague 2 (docs/27)** — l'absorption orderbook NATIVE : mur = `maxBidAmount`/`maxAskAmount` ≥ 3× sa moyenne 200, attaque = vague taker ≥ 2× sa moyenne, tenue = écrasement ≤ 0,8 %, reprise = EMA flux net + déséquilibre `sumBids`/`sumAsks` ≥ 1,2 — le pattern qui a produit l'AL Score d'Aster, dans le backtester |
| `Operation_x501_Alpha2_Cascade_Financement_H4.ks` | alpha cascade de financement |
| `Operation_x501_Alpha3_Eruption_Volatilite_H4.ks` | alpha éruption de volatilité |
| `Operation_x501_Alpha4_Confluence_MTF_H4.ks` | alpha confluence multi-timeframe |
| `x501_observe_flow_H1.ks` / `x501_observe_cvd4_btc_H1.ks` | collecteurs d'observation (zéro ordre, C4) |
| `x501_setup_kscript.js` | l'installation codifiée des kScripts |
| `x501_backtest_trades_BTCUSDT.csv` / `_ETHUSDT.csv` | exemples de sortie backtest |
| `x501_exploit_audit.py` + `exploit_audit.json` | l'audit d'exploitation kScript (53 capacités × 10 scripts → 52,8 %) |
| `qa_kscript_x501.py` | QA générale des 5 stratégies (doc kScript scrapée) |
| `qa_scanner_x501.py` | QA du scanner (49 contrôles) |
| `qa_maker_x501.py` | QA des versions maker (M1–M15, non-régression M13) |
| `qa_observe_x501.py` | QA des collecteurs d'observation (13 contrôles/fichier) |
| `qa_vagues_x501.py` | QA des vagues 1-2 : RI + observe régime + absorption (122 contrôles : no-repaint, fail-open, budget sources ≤ 10, pièges doc, pré-enregistrement) |

## Comment valider (une commande, zéro dépendance)

```bash
cd scripts/studies/x501_openmarket
python3 qa_kscript_x501.py && python3 qa_scanner_x501.py \
  && python3 qa_maker_x501.py && python3 qa_observe_x501.py \
  && python3 qa_vagues_x501.py
```

Attendu : **5× PASS — 0 échec** (208 contrôles au total). Certaines QA
écrivent leurs détails JSON dans `results/` (artefact de run local — ne pas
commiter). Aucune dépendance externe : stdlib pure, les fichiers cibles sont
résolus relativement à ce dossier.

## Statut (01/10/2026)

- 5/5 QA **PASS** (122 contrôles pour `qa_vagues_x501.py`, les 4 existantes inchangées).
- Les `_MK` sont la version d'exécution de référence (fill 97,9 % à δ=2).
- **Vagues 1-2 activées** (registre d'exploitation : `docs/27-pouvoirs-kscript.md`) :
  8 flux premium branchés (sources premium 1/8 → 8), les 4 fonctions orderbook
  natives utilisées (1/3 → 4/3). Backtests A/B pré-enregistrés à exécuter :
  RI on/off sur BTC et ETH, absorption vs signature — verdict au registre `docs/20`.
- **Vague 3 (hygiène, aucun edge espéré)** : `trailPoints` dans les `_MK`,
  `ocaName`, `strategy.maxDrawdown()` dans les rapports — à faire.
- Protocoles d'exécution : `docs/reference/openmarket-x501/PROTOCOLE_*`.
- Statut de la mission et roadmap : `docs/25-openmarket-x501.md`.
