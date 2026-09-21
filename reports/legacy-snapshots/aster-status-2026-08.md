# Aster Suite — Statut réel (2026-08-09)

> Document de vérité court. Les autres docs aster sont historiques / méthodologie.
> Celui-ci dit où on en est VRAIMENT.

## Verdict
**La suite Aster est MORTE en l'état. Aucune stratégie n'est viable.**
Si on avait suivi ces lanes jusqu'à aujourd'hui, on serait "cook" (en perte).

## Preuves (mesurées, pas supposées)
- Dernière activité réelle : **2026-06-04** (~66 jours de froid au 2026-08-09).
- `aster_promotion_truth_report` (03/06) : `promote = 0`, `reject = 5`, `watch = 2`.
- PnL paper cumulé : baseline **−5.37 USD**, après filtre strict **−3.67 USD** (négatif).
- Win-rate strict : **0.409 (41%)**.
- `core-equity-null-results-report.html` : MFE après frictions **−9.88 %**,
  **0 % win-rate** Aster long seul, PnL paper Aster long **−29.04 USD**.
- Dernier moteur RL (`aster_rl_lane_policy`, 6768 lanes, 04/06) :
  verdict **`blocked_no_clean_promotions`** → 0/1 promotion propre.
- Bug structurel : `truth_match_scope = identity_missing` sur TOUTES les lanes
  → le pipeline de vérité ne matchait pas proprement les lanes (LAB 5h vs 30m…).

## Pourquoi c'est mort (régime de marché)
- Marché crypto 2025–2026 : volatilité extrême à la seconde (ère Trump, années
  de pertes massives). Un backtest "calme" de mai–juin 2026 ne survive pas.
- Les vieux ROI (LAB ~48%, HYPE, etc.) sont **déclassés en pré-correctifs**
  (PnL latent mélangé, coûts perps sans levier, intervalles 3h/5h buggés).
- Même les few "PROMOTE" n'étaient que du forward paper, jamais validé en réel.

## Ce qui reste utile (valeur résiduelle)
1. **Le dataset** : ~442 Mo de CSV de backtests paper (archivés proprement dans
   `backend/services/onchain/aster/archive/research_artifacts/legacy_discovery_batches/`).
2. **La méthodologie anti-faux-backtest** (README aster) : contrat d'identité de
   lane, PnL réalisé/latent séparés, coûts sur notionnel, split train/validation OOS.
3. **Le pipeline data vivant** : API Aster publique `fapi.asterdex.com` + WebSocket
   toujours en ligne (vérifié 2026-08-09, ping 200, BTCUSDT ~64860, WS aggTrade OK).
   Seuls les caches locaux (`exchange_info`, `funding`, `universe`) sont gelés → refresh requis.

## Nettoyage effectué (2026-08-09)
- `aster/` root : 265 → 111 fichiers. 154 batchs datés (442 Mo) déplacés vers
  `archive/research_artifacts/legacy_discovery_batches/`. `.py`, `*_latest.json`,
  caches `aster_public_*.json` et monitors forward gardés (chemins fixes des runners).
- `docs/` : 18 `core-equity-aster-*.html` stalés déplacés vers `docs/archive/`.
  31 `.md` méthodologie gardés.

## Prochaine étape : stratégies crypto VIABLES
Objectif : construire des stratégies qui tiennent un régime de volatilité extrême.
Contraintes non négociables (leçon du legacy) :
- Benchmark **train/validation OOS strict** dès le départ, sur données FRAÎCHES.
- Coûts réels (fees + funding sur notionnel + slippage + liquidation) modélisés.
- Validation microstructure (fillabilité) obligatoire avant toute promo.
- Aucun trade réel, paper-only, jusqu'à preuve de bord.

Voir `docs/strategy-roadmap-2026-08.md` pour le plan d'attaque.
