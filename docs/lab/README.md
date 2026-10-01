# Lab grind — création d’indicateurs sans plafond

Objectif : **plus on tourne, meilleurs sont les indicateurs**, pas “catalogue fini → silence”.

## Les 3 rails

| Rail | Rôle | Fichiers |
|---|---|---|
| **A — Génération** | Hypothèses *non-standard* (pas du TA textbook) | `hypotheses/`, `scripts/studies/` |
| **B — Falsification** | N min, anti-drift, coûts, OOS, verdict | méthodo `docs/03`, registre `docs/20` |
| **C — Mémoire** | Ne pas retenter les morts ; composer les vivants | `mortuary.md`, `primitives.md` |

## Règles d’entrée (Rail A)

Une idée entre **seulement si** ≥ 2 conditions :

1. Source non publique standard (Aster micro, FOMO skill-weighted, X privé, composite maison…)
2. Hypothèse écrite *avant* le code (mécanisme → prédiction → critère de mort)
3. Pas un clone nommable “RSI / funding z-score / VWAP session” sans mentir

**Domaines :** une hypothèse = **un** domaine (`ASTER` | `FOMO` | `OPENMARKET` | `X`). Pas de mix dans le même run.

**Horizon :** tag obligatoire `H-1Y` | `H-MULTI` | `H-LIVE` | `H-MICRO` (voir `PROJECT_STRUCTURE.md`).

## Cadence hebdo

| Jour | Acte |
|---|---|
| Lun | 1–3 hypothèses écrites dans `hypotheses/` |
| Mar–Mer | Étude dans `scripts/studies/` (budget compute fixe) |
| Jeu | Verdict → `docs/20` + mortuary ou primitives |
| Ven | CANDIDAT → paper du **même domaine** ; sinon `archive_studies/` |

Nocturnes = **paper + collectors + re-eval**, pas de grilles sauvages de nouvelles idées.

## Anti-boucle agent

Si une proposition est dans `mortuary.md` (même famille) → **refus**.  
Si ce n’est ni une primitive ni un composé de primitives → **refus**.  
Si le domaine ou l’horizon est omis → **refus**.

## Index

- [`mortuary.md`](mortuary.md) — familles mortes
- [`primitives.md`](primitives.md) — briques encore composables
- [`protocol.md`](protocol.md) — checklist d’une étude
- [`hypotheses/`](hypotheses/) — file d’hypothèses pré-code
