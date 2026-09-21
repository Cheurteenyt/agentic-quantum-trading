# Core Equity - Carte des resultats nuls

Derniere mise a jour: 2026-05-26.

Ce fichier garde la memoire des hypotheses qui semblaient logiquement rentables, mais qui n'ont pas donne de signal exploitable dans les donnees actuelles.

Important: ce n'est pas un journal d'echec. C'est une protection contre les boucles couteuses. Si une voie a deja ete testee sans edge, ne pas la relancer sans nouvelle donnee ou nouvelle methode.

## Separation importante avec Aster

La voie Aster positive actuelle n'est pas documentee ici.

Pour le resultat positif:
- lire `docs/core-equity-aster-research-report.html`
- voies: Aster short/fade selectif et Aster long breakout optimise
- resultats historiques utiles: INJUSDT 15m long strict `ROI +6.98%`, `WR 86.67%`, `PF 8.93`; TIAUSDT 2h long `ROI +3.25%`, `WR 68.75%`, `PF 2.42`
- resultats forward paper au 2026-05-26: ledger long optimise `20` entrees, `14` sorties, `WR 71.43%`, `PF 5.87`, `PnL realise +29.95 USD`, `MDD 6.71 USD`
- multi-strategy monitor: lanes isolees par `event_type` (`baseline`, `regime_filtered`, `utc_01_cluster`) pour eviter la contamination des stats
- mise a jour 2026-05-27: separation INJ/TIA/NEAR confirmee. `inj_tia_regime_filtered` est positif (`2` sorties, `WR 100%`, `PnL +8.924 USD`), tandis que `near_only_observation` est negatif (`1` sortie, `WR 0%`, `PnL -4.727 USD`). NEAR reste hors panier principal.
- fin 2026-05-27: elargir vers JUP/BOME n'a pas encore donne une preuve superieure. Le probleme principal devient les positions ouvertes qui trainent en latent negatif; nouvelles lanes fast time-stop `max_holding_trades=300`.
- mise a jour 2026-05-28: le time-stop 300 global est invalide pour TIA (`tia_fast_time_stop` negatif), mais reste interessant sur INJ (`inj_fast_time_stop` positif). Nouvelle lane a tester: `inj_fast_tia_standard`, avec `INJUSDT=300` et `TIAUSDT=600` via `max_holding_trades_by_symbol`.
- mise a jour 2026-05-29: nouvelle direction plus productive que les monitors repetes: `backtest_strategy_discovery.py` scanne des groupes multi-symboles/multi-timeframes. Meilleurs nouveaux candidats proxy: `BOMEUSDT 3h long` (`ROI +6.85%`, `WR 88.89%`, `PF 13.17`, `9` trades fermes, `3/3` fenetres positives) et `TIAUSDT 2h long` (`ROI +4.43%`, `WR 81.82%`, `PF 5.94`). Prochaine etape logique: forward monitor kline/timeframe-aware dedie BOME 3h / TIA 2h.
- le scanner discovery supporte maintenant un mode rotation AFK (`--cycles` / `--run-forever`) et classe les champions par `high_winrate`, `high_roi`, `balanced`, `low_drawdown_efficiency`, `deep_sample`; utiliser ce mode plutot que laisser tourner une seule strategie live.

Ce fichier archive seulement:
- CEX listing prediction non prouvee
- DEX pump long non prouve
- honeypot/scam correlation non prouvee
- DexScreener-first trop faible
- Aster long/buy seul falsifie
- hybride Aster + DEX insuffisamment aligne

## Posture produit autorisee

Autorise:
- recherche
- diagnostic
- paper-trading Aster short/fade
- documentation
- plans bornes read-only
- ecritures paper-trading dediees avec confirm

Interdit:
- signal client
- trade reel
- wallet order
- opt-in client
- label CEX write non source-backed
- mapping DEX depuis indices faibles
- scraping non borne

## Hypotheses falsifiees ou bloquees

### 1. UFLOKI comme opportunite long source-backed

Hypothese:
- Avec PairCreated proof, Transfer context, Sync/liquidity repair et outcome windows, UFLOKI pouvait devenir une premiere opportunite fiable.

Resultat:
- Les donnees sont devenues mesurables et propres.
- Le replay shadow a rejete le long.
- Les gates favorable move, net move et adverse move n'ont pas valide le signal.

Verdict:
- utile comme cas de recherche/control
- pas de signal client
- pas de trade

### 2. Behavioral score eleve = pump DEX

Hypothese:
- Un score comportemental eleve devait annoncer un pump DEX.

Resultat:
- Candidats forts autour de `82`.
- MFE moyen tres faible.
- MFE apres frictions autour de `-9.8848%`.
- Aucun candidat DEX-pump exploitable dans l'echantillon actuel.

Verdict:
- le score detecte une anomalie
- il ne detecte pas encore un alpha long DEX

### 3. Entrer plus tot avec T0 shift

Hypothese:
- Le score final arrive trop tard; entrer aux seuils 40/50/60/70 pouvait sauver le trade.

Resultat:
- Les seuils plus bas n'ont pas produit d'edge apres frictions.
- Le pattern ressemble davantage a wash/circular/distribution qu'a accumulation pre-pump.

Verdict:
- ne pas baisser le seuil pour forcer un signal

### 4. Directional intent classifier comme alpha long

Hypothese:
- La coordination pouvait etre separee en accumulation tradable vs wash/distribution.

Resultat:
- Circularite elevee.
- Hold/freeze faible.
- Aucun candidat alpha-ready long.

Verdict:
- utile pour classifier
- insuffisant pour acheter

### 5. Stealth accumulation / quiet pools

Hypothese:
- Les vrais signaux rentables etaient peut-etre des quiet pools avec accumulation discrete.

Resultat:
- `0` candidat stealth alpha-ready dans l'echantillon actuel.
- Beaucoup de pools calmes existent, mais trop recentes ou non prouvees.

Verdict:
- piste plausible mais non prouvee
- besoin de cohortes plus larges et mieux agees

### 6. CEX listing prediction bridge

Hypothese:
- Stealth accumulation + CEX deposits pouvait predire des listings type LAB/RAVE.

Resultat:
- `tokens_with_any_cex_deposit_rows=0`
- `tokens_with_source_backed_cex_destinations=0`
- La base de hot wallets CEX source-backed est insuffisante.
- LAB/LONG manquent de contexte local comparable.
- B a du contexte raw, mais ses destinations ne sont pas des CEX source-backed.

Verdict:
- bloque par donnees de reference CEX
- ne pas backfill au hasard pour sauver l'hypothese

### 7. Honeypot/scam detector

Hypothese:
- Les scores comportementaux eleves pouvaient predire honeypot/scam.

Resultat:
- Correlation insuffisante dans l'echantillon teste.
- Le moteur detecte de l'anomalie, pas forcement de la malveillance contractuelle.

Verdict:
- ne pas vendre comme honeypot scanner

### 8. DexScreener-first outliers

Hypothese:
- Inverser l'entonnoir avec DexScreener devait fournir plus vite des tokens exploitables.

Resultat:
- Trop peu de candidats.
- Beaucoup de tokens avec `behavioral_score=null`.
- Echantillon insuffisant pour recalibrer proprement les seuils.

Verdict:
- utile comme radar marche
- insuffisant comme moteur de decision

### 9. Aster long/buy order-flow seul

Hypothese:
- Les anomalies Aster order-flow devaient etre achetees en long.

Resultat:
- Le long a fini en stop-loss frequents.
- Backtest long etendu negatif.
- Diagnostic cinematique: `volatility_whipsaw`.

Verdict:
- ne pas trader Aster en long sur ce signal
- cette falsification a mene au pivot short/fade, documente ailleurs

### 10. Hybride Aster + DEX

Hypothese:
- Le score Aster combine avec un score DEX local devait filtrer les faux signaux.

Resultat:
- Les univers ne s'alignent pas assez.
- Trop peu de tokens ont a la fois score DEX local et listing Aster.
- Le test final reel est neutre.

Verdict:
- ne pas valider l'hybride avec une intersection aussi petite

## Decision de recherche

Ne pas revenir a ces hypotheses sans:
- nouvelle cohorte
- nouvelle source de donnees
- nouvelle preuve source-backed
- nouvelle methode de sortie paper
- comparaison contre le track record Aster short/fade

## Clarification Aster - 2026-05-30

Le resultat negatif "Aster long/buy order-flow seul" ne doit plus etre lu comme une invalidation de tout le travail Aster.

Ce qui est invalide:
- acheter le score order-flow brut sans optimisation;
- transformer une anomalie CEX en signal long direct;
- conclure depuis un seul `latest.json` potentiellement ecrase.

Ce qui reste prometteur et documente dans `docs/core-equity-aster-research-report.html`:
- `LABUSDT 5h long`: ROI historique `+15.19%`, WR `63.6%`, PF `3.45`, `22` trades fermes.
- `LABUSDT 1h long`: ROI `+13.92%`, WR `69.2%`, PF `5.22`, DD `11.43$`.
- `LABUSDT 3h long`: ROI `+13.72%`, WR `81.8%`, PF `10.57`.
- `INJUSDT 15m long`: WR jusqu'a `92.8%`, PF jusqu'a `14.52` sur runs recents.
- `TIAUSDT 3h long`: profil stable, WR `86.7%` a `91.7%`, PF `13.0` a `19.0`.
- `BOMEUSDT 3h long`: ROI `+6.85%`, WR `88.9%`, PF `13.17`.

Regle de suivi:
- lire le CSV append-only `paper_trading_strategy_discovery.csv` pour l'historique;
- separer les futures campagnes par univers (`core`, `macro`, `equities`) pour eviter d'ecraser les latest;
- ne pas promouvoir une lane sans forward paper persiste ou sans sample suffisant.

Mise a jour 2026-05-31:
- le suivi des nouveaux backtests doit utiliser les artefacts V2 tagges:
  - `paper_trading_strategy_discovery_{tag}_v2.csv`
  - `paper_trading_strategy_discovery_{tag}_latest.json`
  - `paper_trading_strategy_rotation_{tag}_latest.json`
- l'ancien `paper_trading_strategy_discovery_latest.json` reste un artefact de compatibilite, pas une source de verite suffisante.
- les resultats avec levier doivent etre lus via la couche perps proxy:
  - `best_tradable_leverage` prime sur les anciens multiplicateurs de PnL;
  - `perps_invalid_leverages` doit etre vide ou compris avant promotion;
  - `perps_scenarios_json` documente marge isolee, liquidation estimee, funding proxy et adverse move;
  - ne jamais promouvoir un `x10` ou `x20` si la liquidation arrive avant le stop.

## Docs associees

- Archive HTML: `docs/core-equity-null-results-report.html`
- Rapport Aster positif: `docs/core-equity-aster-research-report.html`
- Dashboard RAG: `docs/core-equity-rag-dashboard.html`
- Historique complet: `rag/memory/project_state.md`
