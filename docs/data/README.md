# Docs — Data (contrats d’entrepôt)

La data **vit** sous `data/` (gitignored). Ici : uniquement la **documentation du contrat** (schéma, qui écrit, fraîcheur, interdits).

## Ne jamais mélanger

| Entrepôt | Doc | Domaine | Interdit |
|---|---|---|---|
| Vue globale | [06-data.md](../06-data.md) | index | — |
| Aster warehouse / klines / OI / depth / liq | [24-donnees-aster.md](../24-donnees-aster.md) | ASTER | Joindre des tables FOMO « pour le fun » |
| OpenMarket om_v27 | [26-openmarket-donnees.md](../26-openmarket-donnees.md) | OPENMARKET | Servir de vérité pour the_machine |
| FOMO (ticks, rest, ws) | [23-maitrise-fomo.md](../23-maitrise-fomo.md) | FOMO | Nourrir le BLOC STATS Aster |

## Règles d’écriture doc data

1. Un changement de schéma → mettre à jour **le** doc du domaine le même jour.
2. Pas de dumps CSV/JSON dans `docs/`.
3. Les rapports d’audit one-shot ("on a trouvé 12 bugs") → `reports/<domaine>/`, pas un nouveau `docs/99-...` permanent sauf contrat durable.
4. Horizon / fenêtre des backtests sur cette data = tagué dans le *rapport*, pas implicite dans le contrat data.

## Watchdogs

| Domaine | Script | État |
|---|---|---|
| ASTER | `scripts/aster_health.py` | `data/warehouse/aster_health_state.json` |
| FOMO | `scripts/fomo_health.py` | `data/fomo/health_state.json` |
