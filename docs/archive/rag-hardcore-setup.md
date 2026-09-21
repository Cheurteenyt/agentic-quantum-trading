# Core Equity RAG Hardcore Setup

Objectif: installer un RAG local stable dans `D:\trading-agent`, utilisable avec Continue.dev, Codex et un modele local Qwen via llama.cpp / ik_llama.cpp.

## Architecture cible

```
D:\trading-agent\
  rag\
    config\
      rag.yaml
      continue.config.yaml
    indexes\
      qdrant\
      llamaindex_storage\
    scripts\
      ingest_repo.py
      query_repo.py
      rag_health.py
    sources\
      project_manifest.json
    README.md
```

Regle: le RAG reste isole dans `rag\`. Pas de fichiers temporaires a la racine.

## Phase 1 - Creer la structure propre

PowerShell depuis `D:\trading-agent`:

```powershell
New-Item -ItemType Directory -Force `
  .\rag, `
  .\rag\config, `
  .\rag\indexes, `
  .\rag\indexes\qdrant, `
  .\rag\indexes\llamaindex_storage, `
  .\rag\scripts, `
  .\rag\sources

New-Item -ItemType File -Force .\rag\README.md
```

## Phase 2 - Environnement Python dedie RAG

Ne pas melanger avec le backend FastAPI. Le RAG doit avoir son venv dedie pour eviter de casser le site.

```powershell
cd D:\trading-agent
py -3.11 -m venv .venv-rag
.\.venv-rag\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Packages recommandes:

```powershell
pip install llama-index llama-index-vector-stores-qdrant llama-index-embeddings-huggingface qdrant-client fastembed sentence-transformers pyyaml rich
```

Wheel CUDA utilise pour la RTX 3070:

```powershell
pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu118
```

Verification:

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

Si Windows bloque l'activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Phase 3 - Vector store

Pour ton setup Windows + RTX 3070 8GB, le choix stable est Qdrant local en mode embedded/path.

Pourquoi:
- plus robuste que Chroma sur gros projets,
- metadata filtering propre,
- persistance facile dans `rag\indexes\qdrant`,
- pas besoin de Docker.

Limite importante: le mode Qdrant local/embedded verrouille le dossier d'index. Pour un vrai setup multi-agent concurrent, passe a Qdrant server local.

Parametres:
- collection: `trading_agent_code_v1`
- distance: cosine
- vectors: 384 ou 768 selon embedding
- batch ingest: 32 a 64 documents

### Mode serveur recommande pour Codex + Continue + agents

Docker est la voie gratuite et stable si Docker Desktop est deja installe.

Demarrage:

```powershell
cd D:\trading-agent
.\rag\scripts\start_qdrant_server.ps1
```

Puis bascule `D:\trading-agent\rag\config\rag.yaml`:

```yaml
storage:
  qdrant_mode: server
  qdrant_url: http://127.0.0.1:6333
```

Re-ingestion apres bascule:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\ingest_repo.py
```

Pourquoi c'est mieux:
- Continue.dev, Codex et Qwen local peuvent lire le meme index en parallele.
- Plus de verrou `storage folder already accessed by another instance`.
- C'est plus proche d'une infra production, tout en restant local et gratuit.

Pour revenir au mode embedded:

```yaml
storage:
  qdrant_mode: local
```

## Phase 4 - Embeddings optimises RTX 3070

Choix recommande:
- Rapide et leger: `BAAI/bge-small-en-v1.5`, 384 dimensions
- Plus qualitatif mais plus lourd: `BAAI/bge-base-en-v1.5`, 768 dimensions

Pour sessions longues, commencer par `bge-small`.

Reglages:
- chunk_size: 512 tokens
- chunk_overlap: 80 tokens
- top_k retrieval: 8
- rerank top_n: 4
- metadata obligatoire: path, extension, module, git_branch, indexed_at

Pourquoi pas des chunks enormes:
- Qwen 9B local a besoin de contexte utile, pas de bruit.
- Les gros chunks degradent le rappel precis dans le code.
- 512/80 est un bon compromis code + docs.

## Phase 5 - Fichiers a indexer

Inclure:
- `backend\routers\*.py`
- `backend\services\*.py`
- `frontend\src\pages\*.tsx`
- `frontend\src\components\*.tsx`
- `frontend\src\services\*.ts`
- `docs\*.md`
- `AGENTS.md`

Exclure:
- `.venv*`
- `node_modules`
- `dist`
- `build`
- `logs`
- `tmp`
- `rag\indexes`
- `__pycache__`
- fichiers `_test_*.py`, `_fix*.py`, `patch_*.py` sauf si on veut volontairement indexer l'historique

## Phase 6 - llama.cpp / ik_llama.cpp pour Qwen

Serveur local conseille:

```powershell
D:\trading-agent\rag\scripts\run_local_llm.ps1
```

Commande equivalente manuelle:

```powershell
D:\llama-server\llama-b8407-bin-win-cuda-12.4-x64\llama-server.exe `
  -m "D:\llama-server\models\qwen3.5\Qwen3.5-9B-Claude-4.6-HighIQ-INSTRUCT-HERETIC-UNCENSORED.Q4_K_M.gguf" `
  --host 127.0.0.1 `
  --port 8080 `
  -c 12288 `
  -ngl 30 `
  -fa on `
  --reasoning off `
  --reasoning-format none `
  --threads 8 `
  --parallel 1
```

RTX 3070 8GB:
- quant: `Q4_K_M` pour 9B si tu veux garder du contexte.
- `-ngl 30`: preset prudent RTX 3070 8GB.
- `-c 12288`: stable pour Qwen 9B Q4 sur 8GB. Monte a `16384` seulement si VRAM OK.
- `--parallel 1`: plus stable pour longues sessions.
- `-fa on`: flash attention si build compatible.
- `--reasoning off --reasoning-format none`: important pour Continue.dev, sinon certains builds Qwen renvoient le texte dans `reasoning_content` et l'UI peut afficher une reponse vide.

Si OOM:
1. baisse `-ngl` a 28,
2. baisse contexte a `-c 16384`,
3. ferme navigateur/jeux/GPU heavy,
4. utilise quant `Q4_K_S` si necessaire.

## Phase 7 - Continue.dev

Fichier cible:

```powershell
notepad $env:USERPROFILE\.continue\config.yaml
```

Template projet:

```powershell
Copy-Item D:\trading-agent\rag\config\continue.config.yaml $env:USERPROFILE\.continue\config.yaml
```

Attention: cette commande remplace la config Continue actuelle. Si tu as deja une config importante, copie seulement les blocs `models`, `context` et `rules`.

Config de base:

```yaml
name: Core Equity Local Hybrid
version: 0.0.1
schema: v1

models:
  - name: Qwen Local ik_llama.cpp
    provider: openai
    model: qwen3.5-9b
    apiBase: http://127.0.0.1:8080/v1
    apiKey: local
    roles:
      - chat
      - edit
      - apply
    defaultCompletionOptions:
      temperature: 0.15
      maxTokens: 4096

  - name: Qwen Local ik Autocomplete
    provider: openai
    model: qwen3.5-9b
    apiBase: http://127.0.0.1:8080/v1
    apiKey: local
    roles:
      - autocomplete
    autocompleteOptions:
      debounceDelay: 450
      maxPromptTokens: 2048
      onlyMyCode: true
    defaultCompletionOptions:
      temperature: 0.05
      maxTokens: 256

context:
  - provider: code
  - provider: docs
  - provider: diff
  - provider: terminal
  - provider: problems
  - provider: folder
```

Note: pour autocomplete pur, un modele coder FIM 1.5B/7B est souvent meilleur qu'un chat 9B. Si Qwen3.5-9B n'est pas FIM, garde-le pour chat/edit et utilise plus tard `Qwen2.5-Coder-1.5B` pour autocomplete.

## Phase 8 - Integration Codex + modele local

Workflow recommande:

1. Codex = pilote principal pour changements critiques, architecture, patchs verifies.
2. Qwen local = copilote rapide pour questions courtes, recherche dans RAG, brouillons, explications.
3. LlamaIndex = memoire locale durable du projet.
4. Continue.dev = interface IDE pour utiliser Qwen + contexte code.

Regle d'or: le RAG ne doit pas remplacer les tests. Il sert a recuperer le contexte et reduire les tokens, pas a certifier le code.

## Phase 9 - Pieges Windows

- Chemins avec backslash: preferer `Pathlib` en Python.
- Encodage: lire/ecrire en `utf-8`.
- Long paths: activer si necessaire:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

- Antivirus Windows Defender peut ralentir Qdrant et GGUF. Exclure uniquement:
  - `D:\trading-agent\rag\indexes`
  - dossier modele GGUF
- Ne pas indexer `node_modules` ni `.venv`.
- Ne pas stocker de cles API dans l'index RAG.

## Phase 10 - Validation

Checks attendus:

```powershell
.\.venv-rag\Scripts\Activate.ps1
python .\rag\scripts\rag_health.py
python .\rag\scripts\ingest_repo.py --dry-run
python .\rag\scripts\query_repo.py "Where is Arkham coverage computed?"
python .\rag\scripts\ask_repo.py "Where is Arkham coverage computed?" --prompt-only
```

Objectif:
- ingestion < 5 minutes pour le repo utile,
- requete RAG < 2 secondes sur CPU/GPU,
- reponses avec chemins sources,
- zero fichier secret indexe.

Checks mode serveur:

```powershell
.\rag\scripts\start_qdrant_server.ps1
(Invoke-WebRequest http://127.0.0.1:6333/collections).Content
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_health.py
```

Si `rag_health.py` indique `qdrant_status.available: false`, Docker n'est pas lance ou le port `6333` est deja pris.

## Phase 11 - Reponses RAG avec Qwen local

Le script `ask_repo.py` fait le pont entre:
- LlamaIndex/Qdrant pour recuperer les sources.
- `llama-server` compatible OpenAI pour generer une reponse locale.
- Codex/Continue.dev si tu veux simplement reutiliser le prompt.

Mode prompt seulement:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\ask_repo.py "Where is Alpha Lab wallet analysis implemented?" --prompt-only
```

Mode Qwen local:

```powershell
D:\trading-agent\rag\scripts\run_local_llm.ps1
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\ask_repo.py "Where is Alpha Lab wallet analysis implemented?"
```

Si tu obtiens `llm_error`, le serveur llama.cpp / ik_llama.cpp n'est pas lance sur `http://127.0.0.1:8080/v1`.

Transition vers `ik_llama.cpp`:

```powershell
D:\trading-agent\rag\scripts\run_local_llm.ps1 -UseIkLlama
```

Le script utilise maintenant le build local:

```text
D:\ik_llama.cpp\build\bin\llama-server.exe
```

Si tu le mets ailleurs, passe le chemin:

```powershell
D:\trading-agent\rag\scripts\run_local_llm.ps1 -ServerExe "D:\chemin\ik_llama.cpp\llama-server.exe"
```

Build local officiel realise:

```powershell
git clone https://github.com/ikawrakow/ik_llama.cpp D:\ik_llama.cpp
cmd /c "call `"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat`" && cd /d D:\ik_llama.cpp && cmake -B build -G Ninja -DGGML_NATIVE=ON -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DCMAKE_BUILD_TYPE=Release"
cmd /c "call `"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat`" && cd /d D:\ik_llama.cpp && cmake --build build --config Release --target llama-server -j 8"
```

Pour les longues sessions:
- Codex garde la main sur les patchs critiques.
- Qwen local repond aux questions de navigation code avec `ask_repo.py`.
- Continue.dev utilise Qwen pour brouillons/edit rapides.
- Le RAG fournit toujours les chemins sources pour eviter les hallucinations.
