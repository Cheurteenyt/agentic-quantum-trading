---
description: "Tests → commit → push : le rituel de livraison avec un message qui raconte"
---

Livre le travail en cours sur "/run/media/cheurteen/Jeux SSD/trading-agent" (chemin avec espace → TOUJOURS quoter) :

1. `.venv/bin/python scripts/run_tests.py --fast` — si un test échoue, STOP : rapporte l'échec, ne committe pas un rouge.
2. `git status -s` + `git diff --stat` : vérifier que chaque fichier modifié est intentionnel (jamais de fichier de données inattendu, jamais de secret/JWT dans les dumps de reports/).
3. Un commit par THEME logique (pas un blob) : message en français, style du repo (« fomo: CE QUE ÇA FAIT — les chiffres de preuve, les leçons »), commence par le résultat.
4. `git push origin main` + `git log --oneline -1` pour la confirmation.

Rapport final : les tests (X verts), les commits (hash + thème), l'état push. Si rien à committer, dis-le franchement.
