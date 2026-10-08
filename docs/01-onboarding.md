---
title: Onboarding — je débarque sur le projet
status: living
owner: cheurteen
updated: 2026-08-09
---

# Onboarding

Bienvenue. Lis cette page en entier avant de toucher au code. 10 minutes.

## 0. Prérequis — Python 3.13 EXACTEMENT

Le `requirements.lock` contient `audioop-lts==0.2.2`, dont le marqueur est
`Requires-Python: >=3.13`. Sur une version antérieure, l'installation échoue
ou, pire, `pip install --no-deps` laisse un module manquant qui ne se révèle
qu'à l'exécution.

```bash
python3 --version        # doit afficher 3.13.x
uv venv --python 3.13    # ou : python3.13 -m venv .venv
uv pip install --python .venv/bin/python --no-deps -r requirements.lock
```

C'est aussi ce que fait la CI (`.github/workflows/ci.yml`, `python-version: "3.13"`).

## 1. Le contexte, sans enrobage

Ce projet a **coûté plus de 4000 $ en pertes réelles**. La cause n'est pas un
manque d'idées de stratégies — il y en a eu des dizaines. La cause est que des
backtests ont eu l'air rentables alors qu'ils ne l'étaient pas.

Conséquence directe sur ta façon de travailler ici :

> **Le livrable de valeur n'est pas une stratégie qui gagne en backtest.
> C'est la preuve qu'une stratégie ne gagne PAS.**

Un résultat négatif honnête vaut mieux qu'un résultat positif douteux. Si tu
trouves une stratégie à Sharpe 3, le réflexe attendu ici est de chercher le bug,
pas d'ouvrir le champagne.

Avant d'écrire la moindre ligne de moteur de backtest : lis
[`03-methodology.md`](03-methodology.md). Non négociable.

## 2. Le projet en 30 secondes

```
D:\trading-agent
├── backend/       FastAPI — routers/ + services/  (le cœur)
├── frontend/      React + Vite
├── agent/         package agent local (SYSTEM.md = prompt de l'agent)
├── rag/           RAG : config, index, memory/, sources
├── integrations/  ponts externes  ⚠️ MT5 = legacy mort, ignorer
├── configs/       config non-secrète par domaine
├── data/          snapshots locaux + données runtime
├── reports/       sorties générées, horodatées
├── scripts/       utilitaires dev (qwen/, security/)
├── docs/          tu es ici
└── archives/      artefacts historiques non-runtime
```

Détail dans [`02-architecture.md`](02-architecture.md).

## 3. Les règles dures (`AGENTS.md`)

La racine contient `AGENTS.md`. Il s'applique aux agents IA **et à toi**. Les
points qui comptent :

- **Analyse par défaut.** On ne lance pas de serveur, on ne fait pas de commande
  lourde, sauf demande explicite.
- **Jamais** `pip install`, `npm install`, ni scan global type `find /`.
- On ne relance pas un serveur en boucle. Une fois, timeout court, stop à la
  première erreur.
- Lecture ciblée : quelques fichiers par sujet, pas d'exploration à l'aveugle.
- Priorité backend : `routers/` puis `services/`. Frontend : `pages/`,
  `services/`, `hooks/`.
- Raisonner toujours dans le sens : **Frontend → API → Router → Service → Data**.

## 4. Secrets

Les clés vivent dans `.env`. **On ne les lit pas, on ne les affiche pas, on ne
les commit pas.** Il n'y a pas d'exception à cette règle.

## 5. Lancer le projet (seulement si on te le demande)

```bash
# backend
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
curl -s http://localhost:8000/health   # doit répondre avant d'aller plus loin

# frontend
cd frontend && npm run dev
```

Commandes complètes dans [`04-runbook.md`](04-runbook.md).

## 6. Ce qui est mort, ce qui est vivant

| Sujet | État |
|---|---|
| Stratégies Aster legacy | **MORT** — 0 promotion, PnL négatif, WR 41 % |
| API + WebSocket Aster (données) | **VIVANT** — caches locaux à rafraîchir |
| MT5 (`mt5_bridge.py`) | **MORT** — résidu legacy, ne rien construire dessus |
| Moteur de backtest strict | **À CONSTRUIRE** — c'est le chantier actuel |

Ne repars pas du code de stratégie legacy. Repars de la **méthodologie**
legacy — c'est elle qui a de la valeur.

## 7. Ta première contribution utile

Dans l'ordre :

1. Lis `03-methodology.md` (comment on évite de se mentir).
2. Lis `08-contributing.md` (conventions, tests, environnement).
3. Lis `06-data.md` (ce que la data révèle) et `07-backtest-engine.md`.
4. Lance `python scripts/run_tests.py` — tout doit être vert avant que tu touches à quoi que ce soit.
5. Demande quel morceau du moteur tu prends.

## 8. Périmètre

Ton accès couvre ce projet et la recherche web pour le faire avancer. Sur ce
périmètre tu as la même autorité que le porteur du projet. En dehors : rien.
