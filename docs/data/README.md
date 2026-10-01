# Docs — Data (contrats d’entrepôt)

Vue d’ensemble complète : **[`06-data.md`](../06-data.md)** (réécrit 01/10/2026).

## Ne jamais mélanger

| Entrepôt | Doc | Domaine |
|---|---|---|
| Vue globale | [06-data.md](../06-data.md) | index |
| Aster warehouse / klines / OI / depth | [24-donnees-aster.md](../24-donnees-aster.md) | **ASTER** |
| OpenMarket om_v27 / data_x501 | [26-openmarket-donnees.md](../26-openmarket-donnees.md) | **OPENMARKET** |
| FOMO ticks/REST/paper | [23-maitrise-fomo.md](../23-maitrise-fomo.md) | **FOMO** |
| X posts | 06 § X | **X** |
| Legacy lanes | 06 §3 | preuve négative seulement |

## Règles

1. Changement de schéma → doc du domaine **le même jour**.
2. Pas de dumps dans `docs/`.
3. Audits one-shot → `reports/<domaine>/`.
4. Horizon backtest tagué dans le *rapport*, pas dans le contrat data.

## Watchdogs

| Domaine | Script | État |
|---|---|---|
| ASTER | `aster_health.py` | `data/warehouse/aster_health_state.json` |
| FOMO | `fomo_health.py` | `data/fomo/health_state.json` |
