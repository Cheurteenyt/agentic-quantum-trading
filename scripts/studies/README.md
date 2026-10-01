# scripts/studies/ — one-shots vivants

## Règles

1. **Un domaine par étude** (ASTER / FOMO / OPENMARKET / X).
2. **Horizon taggé** dans le script et le rapport (`H-1Y`, `H-MULTI`, …).
3. Hypothèse écrite d’abord dans `docs/lab/hypotheses/`.
4. Verdict → `docs/20` + `docs/lab/mortuary.md` ou `primitives.md`.
5. Close → `scripts/archive_studies/` (ne pas supprimer).

## Domaines déjà isolés

| Dossier / préfixe | Domaine |
|---|---|
| `x501_openmarket/` | OPENMARKET — ne pas importer depuis the_machine |
| études `fomo_*` / `swaps_*` à la racine scripts | FOMO (préfixe nom) |
| études cascade / OI / depth / machine | ASTER |

OpenMarket reste le modèle : **un dossier = un domaine**. Les études Aster/FOMO one-shot peuvent rester plates tant que le préfixe et le header domain/horizon sont stricts.
