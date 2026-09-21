# Core Equity RAG

RAG local dedie au projet `D:\trading-agent`.

## Commandes

```powershell
cd D:\trading-agent
.\.venv-rag\Scripts\Activate.ps1
python .\rag\scripts\rag_tool.py health
python .\rag\scripts\rag_tool.py ingest --dry-run
python .\rag\scripts\rag_tool.py ingest
python .\rag\scripts\rag_tool.py ingest --domain all
python .\rag\scripts\rag_tool.py query "Where is Arkham coverage computed?"
python .\rag\scripts\rag_tool.py ask "Where is Arkham coverage computed?" --prompt-only
```

## Routine economique avant patch

Utilise le plus petit domaine possible avant de lire le repo:

```powershell
# Decisions durables, priorites, securite client
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py query --domain memory "Quelle est la contrainte actuelle sur Alpha Lab ?"

# UI / React / wallet connect client
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py query --domain frontend "Ou est rendu le verdict Alpha Lab ?"

# RPC, Arkham-like, labels, CEX deposits, holders
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py query --domain data "Ou est calcule le holder-flow proxy ?"

# FastAPI, auth, routers, services generaux
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py query --domain backend "Quel endpoint protege la session wallet Alpha Lab ?"

# Aster, backtests, validators, politique RL offline
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py query --domain aster "Quelle lane Aster est actuellement la plus propre et pourquoi ?"
```

Regle courte:

- `memory` avant une decision produit/securite.
- `frontend` avant un patch visuel ou client wallet.
- `data` avant toute modification RPC/Arkham-like/labels.
- `aster` avant toute decision sur backtests, runners, validators, RL lane policy ou docs Aster.
- `backend` avant routes, auth, jobs, storage.
- `security` avant wallet connect, Tailscale, Supabase auth, admin/client tokens.
- `full` seulement quand le sujet traverse vraiment tout le repo.

Ne lance pas `ingest --domain all` par reflexe. Reindexe uniquement le domaine touche, puis `memory` si une decision durable a change.

## Domaines RAG

Le RAG est maintenant separe en domaines pour eviter que Qwen melange backend, frontend, data Arkham/RPC et memoire projet.

Collections:

- `full` -> `trading_agent_code_v1`: vue complete, utile pour les questions transverses.
- `backend` -> `core_code_backend`: FastAPI routers/services/schemas.
- `frontend` -> `core_code_frontend`: React pages/components/services/hooks.
- `data` -> `core_data_architecture`: Arkham-like labels, RPC, on-chain, Scrapling, Alpha data.
- `aster` -> `core_aster_research`: recherche Aster, paper trading, strategy discovery, validators, RL lane policy et docs HTML Aster.
- `memory` -> `core_memory_decisions`: decisions durables, protocoles, playbooks.
- `security` -> `core_security_context`: acces client, wallet safety, auth gates, Tailscale/private access.

Commandes utiles:

```powershell
# Voir les domaines disponibles
python .\rag\scripts\rag_tool.py health --domain data

# Indexer toutes les collections specialisees
python .\rag\scripts\rag_tool.py ingest --domain all

# Questionner uniquement la couche data
python .\rag\scripts\rag_tool.py query "Comment augmenter les labels sans faux positifs ?" --domain data

# Questionner uniquement la recherche Aster
python .\rag\scripts\rag_tool.py query "Pourquoi HYPE est promu et LAB ne l'est pas ?" --domain aster

# Questionner uniquement le frontend
python .\rag\scripts\rag_tool.py ask "Ou ameliorer Alpha Lab sans casser les appels API ?" --domain frontend --prompt-only
```

## Evaluation RAG par domaine

Le fichier `rag/evals/golden_questions.yaml` contient des questions avec un `domain` attendu.

```powershell
# Eval complete, chaque question utilise son domaine
python .\rag\scripts\eval_rag.py

# Eval d'un domaine uniquement
python .\rag\scripts\eval_rag.py --domain data --json
python .\rag\scripts\eval_rag.py --domain frontend --json
```

Objectif: garder au moins `85%` de reussite. Si un domaine baisse, corriger d'abord `rag/config/rag.yaml` ou les questions golden avant de faire confiance au RAG.

## Environnements Python actifs

- Backend WSL: `D:\trading-agent\.venv.wsl`
- Backend/utilitaires Windows: `D:\trading-agent\.venv-win`
- RAG/Continue/LlamaIndex: `D:\trading-agent\.venv-rag`

Les anciens doublons `.venv`, `.venv.partial` et `backend\.venv` ont ete archives dans `tmp\`.

## Continue.dev

Template pret:

```powershell
Copy-Item .\rag\config\continue.config.yaml $env:USERPROFILE\.continue\config.yaml
```

Ne fais cette copie que si tu veux remplacer ta config Continue actuelle.

## Qdrant modes

Le mode par defaut est `local`: simple et persistant, mais il verrouille `rag\indexes\qdrant` pendant qu'un process le lit.

Pour les longues sessions avec Codex + Continue.dev + modele local, utilise le mode serveur:

```powershell
D:\trading-agent\rag\scripts\start_qdrant_server.ps1
```

Puis mets `storage.qdrant_mode: server` dans `D:\trading-agent\rag\config\rag.yaml` et relance l'ingestion.

## Regles

- Ne pas indexer `.env`, cles API, `.venv`, `node_modules`, logs ou fichiers temporaires.
- Ne pas indexer DB dumps, archives, builds, images, caches ou `rag/memory/generated_project_map.md`.
- Les indexes locaux restent dans `rag\indexes\`.
- Le RAG sert a recuperer du contexte, pas a remplacer les tests.
- Qdrant local ne supporte pas plusieurs requetes simultanees. Pour du multi-agent concurrent, passer a Qdrant server.

## Memoire projet

Les fichiers durables sont dans `D:\trading-agent\rag\memory\` et sont indexes par le RAG:

- `project_state.md`: etat actuel du projet, decisions data/security, chemins importants.
- `agent_improvement_protocol.md`: boucle d'auto-amelioration agent controlee.
- `rag_operating_playbook.md`: commandes, reglages RTX 3070 et routines RAG.
- `model_routing_guide.md`: choix Codex/Qwen selon le risque, le cout token et le type de tache.

Important: l'auto-amelioration agent est autorisee uniquement comme boucle controlee `observe -> propose -> patch -> test -> record`. Pas de modification autonome cachee, pas de backfill massif, pas de secrets dans la memoire.

## Qwen local via ik_llama.cpp

Serveur principal recommande:

```powershell
D:\trading-agent\rag\scripts\run_local_llm.ps1 -UseIkLlama
```

Le script utilise `D:\ik_llama.cpp\build\bin\llama-server.exe` si disponible, avec fallback vers l'ancien `llama-server`.

Pour stopper le serveur local:

```powershell
D:\trading-agent\rag\scripts\stop_local_llm.ps1
```

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\ask_repo.py "Which files should I inspect for Alpha Lab wallet analysis?"
```

Si le serveur local n'est pas lance, ajoute `--prompt-only` pour generer le prompt RAG avec sources, puis colle-le dans Continue.dev ou Codex.

## Local Advisor read-only

Pour faire travailler Qwen local en parallele sans lui donner le droit de modifier les fichiers, utilise le mode advisor:

```powershell
cd D:\trading-agent
D:\trading-agent\rag\scripts\run_local_llm.ps1 -UseIkLlama
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py "Que doit-on verifier avant d'ameliorer la data RPC Arkham-like ?"
```

Le rapport est ecrit dans:

```text
D:\trading-agent\rag\reports\
```

Regles:

- Qwen local lit le RAG et propose des hypotheses.
- Qwen local ne modifie aucun fichier.
- Codex reste le seul agent qui decide, patch et verifie.
- Si le serveur local n'est pas lance, utilise `--prompt-only` pour generer le prompt advisor.
- Les presets utilisent maintenant le domaine le plus pertinent par defaut: `priority-data` et `candidate-labels` -> `data`, `frontend-alpha` -> `frontend`, `critic` et `security-client` -> `memory`.

Roles utiles:

```powershell
# Analyste data RPC / labels
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --role data --domain data "Que manque-t-il pour augmenter la couverture RPC sans doublons ?"

# Critique securite/client
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --role security --domain memory "Quels risques avant d'exposer le site aux clients ?"

# Memoire seulement, sans snippets de code
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --role critic --context-mode memory "Quelles hypotheses sont faibles dans notre plan data ?"

# Aucun contexte projet, seulement le brief donne
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --context-mode task-only "Critique ce plan sans acceder au projet: ..."
```

Le mode recommande au quotidien est `--context-mode rag --max-sources 4`: Qwen ne lit que quelques extraits RAG + memoire durable, puis Codex garde le controle.

Presets contrôlés:

```powershell
# Priorité data actuelle
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset priority-data

# Vérifier le sas label_candidates
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset candidate-labels

# Sécurité client, mémoire seulement
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset security-client

# Critique globale, mémoire seulement
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\local_advisor.py --preset critic
```

Qwen ne se prompt pas automatiquement en continu. Les presets donnent à Codex une façon rapide de lancer une production utile, bornée et read-only quand on en a besoin.

## Choix du modele Codex/Qwen

Le guide durable est dans:

```text
D:\trading-agent\rag\memory\model_routing_guide.md
```

Regle courte:

- GPT-5.5 High/XHigh pour securite, data architecture, labels/RPC, wallet/client access, gros bugs.
- GPT-5.5 Medium ou GPT-5.4 High pour patches clairs, UI, docs, tests.
- Qwen local uniquement comme advisor read-only avec le bon domaine RAG.
