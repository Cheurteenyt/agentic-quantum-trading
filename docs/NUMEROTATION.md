# Docs de numérotation — `docs/`

## La numérotation a une collision historique assumée : `21`

`docs/21-goal-performances.md` et `docs/21-vagues-registre.md` portent le
même numéro **volontairement** : le PR #182 a scindé un registre de 922
lignes en « l'état vivant » (`docs/20`) et « les vagues datées » (`docs/21`).
Les deux fichiers sont le même sujet — le registre — vu sous deux angles.

Ne pas renuméroter : cela casserait les renvois des faits déjà enregistrés
(`research/evidence/facts.jsonl`, qui pointent F-033/F-034/F-035 vers
`docs/21-vagues-registre.md`).

## Règle pour la suite

Le prochain numéro libre se prend **au-dessus du maximum existant**, pas au
premier trou. Le maximum était `39` avant le 08/10/2026 ; `40` est donc
alloué à `40-openmarket-harnais-deep-40sym.md`, qui portait auparavant `38` et
entrait en collision avec `38-gouvernance-recherche.md` (sujet sans rapport).

Le trou apparent de `22` à `32` n'est pas une invitation : ces numéros ont
été utilisés puis supprimés, et les réattribuer ferait porter à deux
documents différents des renvois déjà écrits.

## Renommer un doc

1. `git mv` (l'historique suit le fichier)
2. mettre à jour **tous** les renvois, y compris dans `scripts/studies/**`
   et `research/evidence/facts.jsonl`
3. vérifier :

   ```bash
   grep -rn "<ancien-nom>" --include="*.md" --include="*.py" . \
     --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=.git
   ```

   doit ne rien renvoyer
4. `python3 scripts/claim_verify.py --all` doit rester à 42/42 SUPPORTED —
   c'est l'oracle qui détecte un renvoi cassé vers un fait enregistré