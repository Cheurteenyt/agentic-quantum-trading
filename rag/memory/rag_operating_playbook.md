# RAG - Playbook operationnel

Ce fichier explique comment utiliser et maintenir le RAG Core Equity. Les commandes restent en anglais/PowerShell parce qu'elles sont executables; les explications sont en francais.

## Commandes quotidiennes

Health:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py health
```

Reindexer:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ingest --domain all
```

`ingest` rafraichit automatiquement la carte d'architecture generee avant indexation. Pour inspecter seulement la carte:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\build_project_map.py
```

Verifier si un domaine est stale:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py health --domain data
```

Si `freshness.is_stale=true`, reindexer le domaine avant de demander a Qwen/Codex de raisonner depuis le RAG.

Evaluer la qualite de retrieval:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\eval_rag.py
```

Auditer la geometrie des embeddings:

```powershell
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\embedding_spectrum.py --domain data --max-chunks 160 --save
```

Interpretation:
- `tight_low_deff`: les resumes/consolidations peuvent aider si les evals le confirment
- `middle_deff`: consolidation probablement neutre; garder le retrieval hybride
- `spread_high_deff`: eviter la compression par centroid; garder plusieurs chunks/medoids

La decision finale reste `eval_rag.py` ou un QA specifique a la tache.

## Routage par domaine

Utiliser le plus petit domaine utile:
- `--domain data`: donnees on-chain/marche, labels, RPC, Scrapling, DexScreener, Aster
- `--domain backend`: endpoints FastAPI, services, schemas
- `--domain frontend`: React UI, dashboards, appels API client
- `--domain memory`: decisions durables, posture securite, etat projet
- `--domain full`: questions transverses larges uniquement

Cela evite que le modele melange des contextes sans lien.

## Quand mettre a jour la memoire

Mettre a jour les fichiers RAG apres:
- nouvelle decision produit durable
- nouveau resultat de backtest/paper-trading
- nouvelle source externe
- nouveau module structurant
- conclusion importante qui ne doit pas etre redecouverte
- changement des garde-fous

Pour les resultats Aster positifs:
- mettre a jour `docs/core-equity-aster-research-report.html`
- mettre a jour `rag/memory/core_equity_operating_map.md`
- mettre a jour `rag/memory/current_automation_state.md`

Pour les hypotheses falsifiees:
- mettre a jour `docs/core-equity-null-results-report.html`
- mettre a jour `rag/memory/core_equity_null_results_map.md`

## Questions qui doivent bien marcher

Exemples utiles:
- `Ou en est la strategie Aster short/fade ?`
- `Quel est le prochain objectif Core Equity ?`
- `Quelles hypotheses ont deja ete falsifiees ?`
- `Quels endpoints Aster paper-trading sont utiles ?`
- `Quels garde-fous empechent le trading reel ?`
- `Quel fichier HTML contient les resultats positifs Aster ?`
- `Quel fichier archive les resultats non concluants ?`

## Parametres RTX 3070 8GB

Defaults stables:
- modele embedding: `BAAI/bge-small-en-v1.5`
- chunk size: `512`
- chunk overlap: `80`
- embedding batch size: `32`
- Qwen GGUF: Q4_K_M ou equivalent 9B quant
- contexte: `12288` si stable, sinon `8192`
- GPU layers: environ `30`, reduire si pression VRAM
- parallel: `1`

Defaults local advisor:
- sources recuperees: `4` par defaut, max `8`
- memoire durable par fichier: `3500` caracteres
- tokens reponse advisor: `1200`
- timeout advisor: `90s`

Si Qwen timeout:
- relancer avec `--context-mode memory`
- ou `--context-mode task-only`
- ou reduire `--answer-tokens 600 --memory-chars 2000`

## Qdrant

Mode actuel prefere: Qdrant server sur `http://127.0.0.1:6333`, container Docker `core-equity-qdrant`.

Demarrage:

```powershell
D:\trading-agent\rag\scripts\start_qdrant_server.ps1
```

Configuration:

```yaml
storage:
  qdrant_mode: server
```

Puis reindexer.

## Regle de langue

Les documents RAG lisibles par humain doivent etre en francais.

Garder en anglais uniquement:
- noms d'endpoints
- noms de fonctions
- noms de fichiers
- champs JSON
- statuts machine
- commandes shell
- constantes de confirmation

Objectif: lecture naturelle en francais sans casser les references techniques.
