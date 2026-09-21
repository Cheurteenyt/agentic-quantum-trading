# Aster v2 strict vs large comparison

Date: 2026-05-31

## Objectif

Comparer automatiquement deux familles de runs:

- `aster_v2`: runner large, utile pour decouverte et exploration.
- `aster_v2_strict`: runner filtre par preflight universe + WebSocket, utile pour candidats plus propres.

Le but est d'eviter de relire les CSV a la main et de savoir rapidement:

- quel resultat est nouveau;
- quel resultat existe dans les deux modes;
- quel resultat disparait quand on applique le filtre WS;
- quels symboles du large ne sont pas strict-ready.

## Fichiers

Module:

`backend/services/onchain/aster/research/aster_v2_strict_vs_large_comparator.py`

Endpoint:

`/api/onchain/rpc/aster-v2-strict-vs-large-comparison-preview`

Snapshot:

`backend/services/onchain/aster/aster_v2_strict_vs_large_comparison_latest.json`

Cockpit:

`docs/core-equity-aster-research-consolidated-report.html`

## Methode

Le comparateur lit uniquement les CSV locaux:

- `paper_trading_strategy_discovery_aster_v2_v2.csv`
- `paper_trading_strategy_discovery_aster_v2_strict_v2.csv`

Il compare par lane stable:

`symbol + side + interval + search_mode + score_window_size + risk_profile + thresholds + stop/take/trailing/time-stop`

Il produit:

- `top_strict`
- `top_large`
- `strict_improved`
- `strict_degraded`
- `large_symbols_not_strict_ready`

## Etat actuel

Le comparateur est fonctionnel, mais le snapshot actuel indique que les CSV `aster_v2` / `aster_v2_strict` ne sont pas encore assez alimentes localement.

Interpretation:

- laisser le terminal `aster_v2_strict` terminer au moins un cycle;
- laisser aussi un terminal `aster_v2` large tourner si on veut une comparaison complete;
- relancer ensuite le comparateur ou le cockpit consolide.

## Commande

```powershell
Set-Location D:\trading-agent\backend
python -c "from services.onchain.aster.research.aster_v2_strict_vs_large_comparator import get_aster_v2_strict_vs_large_comparison_preview; r=get_aster_v2_strict_vs_large_comparison_preview(write_snapshot=True); print(r['comparison_status']); print(r['summary'])"
```

## Garde-fous

- lecture CSV locale uniquement;
- aucun appel Aster;
- aucun write DB;
- aucun trade;
- aucun wallet;
- snapshot JSON local seulement.
