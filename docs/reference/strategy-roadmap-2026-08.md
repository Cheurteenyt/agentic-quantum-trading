# Roadmap — Stratégies crypto VIABLES (post-Aster)

Date: 2026-08-09. Profil `trading`. Projet `D:\trading-agent`.

## Leçon du legacy Aster (à ne jamais répéter)
- Long-only stateful en régime extrême = cuit. Le marché 2025-26 bouge à la
  seconde (Trump-era, années de pertes). Être exposé unidirectionnellement ne tient pas.
- Backtests "calmes" mai-juin 26 non représentatifs. Il faut du train/val OOS
  sur données FRAÎCHES (refresh des caches Aster requis).
- Vrai coût = fees + funding sur notionnel + slippage + risque de liquidation.
- Validation microstructure (fillabilité) obligatoire avant promo.

## Principes de conception (non négociables)
1. **Directionnel bicôte** : autoriser long ET short. Pas de biais structurel.
2. **Filtre de régime** : ne pas trader (ou réduire taille) en régime de
   volatilité non-directionnelle / gap risk.
3. **Filtre de volatilité** : taille et seuil d'entrée dépendent de la vol réalisée.
4. **Benchmark strict dès le départ** : chaque lane = `symbol + interval + side
   + trigger + execution_model + leverage`, avec `train_*` / `validation_*` séparés.
5. **Paper-only** jusqu'à preuve de bord (aucun ordre réel).

## Piste 1 — Volatility-breakout régime-aware (PRIORITAIRE)
- Entrée : rupture de range (ex. écart vs bandes de volatilité type ATR/Keltner)
  sur 15m/1h, validée par une direction du funding ou du orderflow.
- Side : long si rupture haussière + funding pas trop négatif, short si baisse.
- Filtre régime : ATR(period) vs médiane → si vol > seuil, taille réduite / skip.
- Sortie : retracement du range ou stop ATR multiple.

## Piste 2 — Funding/perp mean-reversion (secondaire)
- Sur perps Aster : si funding extrême (shorts payent beaucoup) + prix sur
  étirement, position contre le consensus (short si tout le monde short, etc.).
- Risque : régime trending peut tuer le mean-reversion → filtre de trend obligatoire.

## Piste 3 — Microstructure/WS (réutilise l'existant)
- Les validateurs `ws_symbol_quality`, `mark_index`, `microstructure` du legacy
  sont bons. On les REUTILISE pour filtrer les lanes des pistes 1/2.

## Plan d'exécution
1. [ ] Refresh data Aster (exchangeInfo/funding/universe) — commandes existantes.
2. [ ] `strategies_v2/vol_breakout.py` : scaffold + signal + backtest strict.
3. [ ] `strategies_v2/regime_filter.py` : ATR/vol + session filter.
4. [ ] `strategies_v2/backtest_strict.py` : moteur train/val OOS + coûts réels.
5. [ ] Valider microstructure via les outils legacy avant promo.
6. [ ] Paper forward, puis seulement discuter réel.

## Arborescence nouvelle
```
backend/services/onchain/aster/strategies_v2/
  __init__.py
  vol_breakout.py          # Piste 1
  regime_filter.py         # filtre vol/régime
  funding_mean_reversion.py# Piste 2
  backtest_strict.py       # moteur benchmark strict
  README.md
```
