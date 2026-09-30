# x501_openmarket/ — LE DOMAINE OPENMARKET (kScripts + QA)

**Le domaine de la mission x501** (100 $ → 50 100 $, DD ≤ 25 % —
`docs/25-openmarket-x501.md`). Tout le code du domaine tient dans ce
dossier : les 9 kScripts, le scanner d'installation et les 4 QA statiques.
Les données restent locales (git-ignorées, `docs/26-openmarket-donnees.md`).

## Contenu

| Fichier | Rôle |
|---|---|
| `Operation_x501_Signature_H1.ks` / `_H4.ks` | le signal de base (signature), cadence H1 / H4 |
| `Operation_x501_Signature_H1_MK.ks` / `_H4_MK.ks` | **les versions maker** (limite δ=2–5, TTL, fallback taker, verrous pend*) |
| `Operation_x501_Alpha2_Cascade_Financement_H4.ks` | alpha cascade de financement |
| `Operation_x501_Alpha3_Eruption_Volatilite_H4.ks` | alpha éruption de volatilité |
| `Operation_x501_Alpha4_Confluence_MTF_H4.ks` | alpha confluence multi-timeframe |
| `x501_observe_flow_H1.ks` / `x501_observe_cvd4_btc_H1.ks` | collecteurs d'observation (zéro ordre, C4) |
| `x501_setup_kscript.js` | l'installation codifiée des kScripts |
| `x501_backtest_trades_BTCUSDT.csv` / `_ETHUSDT.csv` | exemples de sortie backtest |
| `qa_kscript_x501.py` | QA générale des 5 stratégies (doc kScript scrapée) |
| `qa_scanner_x501.py` | QA du scanner (49 contrôles) |
| `qa_maker_x501.py` | QA des versions maker (M1–M15, non-régression M13) |
| `qa_observe_x501.py` | QA des collecteurs d'observation (13 contrôles/fichier) |

## Comment valider (une commande, zéro dépendance)

```bash
cd scripts/studies/x501_openmarket
python3 qa_kscript_x501.py && python3 qa_scanner_x501.py \
  && python3 qa_maker_x501.py && python3 qa_observe_x501.py
```

Attendu : **4× PASS — 0 échec**. Les 4 QA écrivent leurs détails JSON dans
`results/` (artefact de run local — ne pas commiter). Aucune dépendance
externe : stdlib pure, les fichiers cibles sont résolus relativement à ce
dossier.

## Statut (30/09/2026)

- 4/4 QA **PASS** au moment de l'intégration.
- Les `_MK` sont la version d'exécution de référence (fill 97,9 % à δ=2).
- Protocoles d'exécution : `docs/reference/openmarket-x501/PROTOCOLE_*`.
- Statut de la mission et roadmap : `docs/25-openmarket-x501.md`.
