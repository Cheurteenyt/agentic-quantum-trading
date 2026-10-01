# Protocole d’une étude (checklist)

Copier dans le header de chaque étude / rapport.

```text
domain:    ASTER | FOMO | OPENMARKET | X
horizon:   H-1Y | H-MULTI | H-LIVE | H-MICRO
window:    YYYY-MM-DD → YYYY-MM-DD
hypothesis: (1–3 phrases, mécanisme)
why_not_textbook: (pourquoi ce n’est pas un indicateur connu)
death_criteria: (quand on déclare NUL)
baseline: (buy&hold / random / inverse / machine flux concerné)
N_min:
param_critique: (un seul, pré-déclaré — ou aucun)
```

## Étapes

1. **Écrire** l’hypothèse dans `docs/lab/hypotheses/YYYY-MM-DD-slug.md` *avant* le code.
2. **Vérifier** mortuary : famille déjà morte ? → stop.
3. **Coder** dans `scripts/studies/` (ou préfixe domaine si collecteur permanent).
4. **Run** avec tag horizon + domain dans le stdout et le rapport.
5. **Verdict** : VALIDÉ | CANDIDAT | NUL | CONTEXTE → `docs/20-registre-indicateurs.md`.
6. **Mémoire** : NUL → ligne mortuary ; CANDIDAT/VALIDÉ → primitive ou composé dans `primitives.md`.
7. **Forward** seulement dans le paper du **même domaine**.

## Interdits

- Mélanger FOMO et Aster dans le même BLOC STATS
- Comparer H-1Y et H-MULTI sans le dire
- Grille multi-params après un null sur la même famille
- “Ça a l’air pro” comme justification d’entrée en Rail A
