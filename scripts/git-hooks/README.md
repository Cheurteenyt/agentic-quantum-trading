# Git hooks du projet

## Installation (après un clone)
```bash
cp scripts/git-hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

## pre-push
Bloque les pushs directs sur `main`. **Tout changement passe par une PR** :
```bash
git checkout -b feat/mon-travail
git add ... && git commit
git push -u origin feat/mon-travail
gh pr create --title "..." --body "Ce que ça fait, pourquoi, comment vérifier"
gh pr merge --squash --delete-branch
```
La CI (`.github/workflows/ci.yml`) doit être verte avant le merge.
