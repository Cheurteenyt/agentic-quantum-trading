# Reports — par domaine

**Règle** : un rapport = un domaine. Pas de mélange FOMO / Aster / OpenMarket dans le même fichier « officiel ».

| Dossier | Domaine | Contenu typique |
|---|---|---|
| [`aster/`](aster/) | ASTER | machine, régimes, decay cascade, paper Aster |
| [`fomo/`](fomo/) | FOMO | paper fomo, lifecycle |
| [`openmarket/`](openmarket/) | OPENMARKET | baselines x501, MC |
| [`x/`](x/) | X | harvest / calls |

## Fichiers migrés (01/10/2026, stubs supprimés le 02/10/2026)

| Ancien path | Nouveau path |
|---|---|
| `reports/openmarket-x501-baseline-2026-10-01.md` | [`openmarket/x501-baseline-2026-10-01.md`](openmarket/x501-baseline-2026-10-01.md) |
| `reports/openmarket-x501-baseline-2026-09-30.md` | [`openmarket/x501-baseline-2026-09-30.md`](openmarket/x501-baseline-2026-09-30.md) |
| `reports/decay-curve-2026-09-28.md` | [`aster/decay-curve-2026-09-28.md`](aster/decay-curve-2026-09-28.md) |

Les stubs intermédiaires ont été supprimés (les liens pointent désormais directement
vers `openmarket/` et `aster/` ; seule référence externe mise à jour : docs/25).

Runtime logs → `logs/`, pas ici.
