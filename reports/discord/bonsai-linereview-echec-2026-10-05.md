# LA TENTATIVE DE REVIEW LIGNE PAR LIGNE PAR BONSAI — ÉCHEC DOCUMENTÉ (05/10)

## Ce qui s'est passé
Le code réel (store.py + capture.py + bonsai_judge.py + le triage semantic.py, strippé des
docstrings = 4 039 tokens) soumis à Bonsai pour une review ligne par ligne. Résultat :
**le modèle est tombé en mode écho-complétion** — au lieu d'analyser, il a répété le code du
prompt et halluciné des fonctions fictives (un `_reg_init` qui n'existe pas, un `reg_rule`
manglé) en complétant le pattern du code plutôt qu'en le lisant.

## La limite de capacité documentée
- Le contexte du serveur : 8 192 tokens. Le code 4 039 + le prompt ~500 = ~4 600 tokens en
  entrée — ça TENAIT. L'échec n'est pas le débordement, c'est le MODE : un 27B en no-think
  à qui on montre du code après une consigne de review fait du PATTERN-COMPLETION, pas de
  l'analyse. La review ligne par ligne = au-delà de sa capacité actuelle.
- Ce qui marche chez Bonsai : les designs d'architecture (avec des contraintes), les
  prédictions scellées, les red-teams conceptuels. Ce qui ne marche pas : la lecture
  attentive de code volumineux inline.

## LA REVIEW SÉVÈRE FAITE PAR L'AGENT (ce que Bonsai aurait dû trouver)
1. **PAS DE WAL sur discord.db** — la leçon 75dd088 du projet (WAL + timeout 60) jamais
   appliquée au domaine Discord. FIXÉ : PRAGMA journal_mode=WAL + synchronous=NORMAL sur
   chaque connexion (vérifié : journal_mode = wal).
2. **3 CREATE TABLE d_mod_actions en doublon** (le schéma + mod_db + warns_of) — FIXÉ
   (le schéma global couvre, les helpers ne recréent plus).
3. **La fuite mémoire** : le dict _msg_times de l'anti-spam croissait sans borne (chaque
   auteur y reste pour toujours) — FIXÉ : purge des auteurs inactifs > 10 min à 500 entrées.
4. (Les 3 fixs de la review précédente déjà mergés : la DB hors event loop, le catch-up
   par last_message_id, le verrou LLM.)

## La règle pour la suite
Les reviews de code : l'agent (qui connaît chaque ligne) + les outils (py_compile, les
tests). Bonsai : les designs, les prédictions, les red-teams conceptuels — avec ses sorties
TOUJOURS vérifiées ligne à ligne avant adoption.
