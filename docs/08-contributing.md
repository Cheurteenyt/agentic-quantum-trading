---
title: Contribuer — conventions et garde-fous
status: living
owner: cheurteen
updated: 2026-08-09
---

# Contribuer

Les conventions du projet, apprises à leurs dépens. Chaque règle ici a un coût
réel derrière elle.

## Le contrat en une phrase

> Le livrable de valeur n'est pas une stratégie qui gagne.
> C'est **la preuve qu'une stratégie ne gagne pas**.

Si tu trouves un Sharpe 3, cherche le bug. Sur ce projet, un résultat trop beau
a toujours été un bug — 6768 lanes testées, 0 promotion propre.

## Environnement — ce qui est disponible

```
Python 3.11 · Windows · shell = git-bash (syntaxe POSIX, /d/trading-agent)
```

**`pip install` est interdit.** Non négociable (`AGENTS.md`). Conséquence :

| Disponible | PAS disponible |
|---|---|
| stdlib complète | pandas |
| `sqlite3`, `json`, `csv` | numpy |
| `unittest` | pytest |
| `urllib.request` | requests, httpx |

Ce n'est pas une contrainte subie, c'est un choix assumé sur le module
critique : `backend/services/backtest_v2/` est **stdlib pure** et ne peut pas
casser à cause d'un upgrade de lib.

## Lancer les vérifications

```bash
python scripts/run_tests.py               # toute la suite
python scripts/run_tests.py backtest_v2   # filtre par nom de fichier
python scripts/docs_audit.py              # doc stale / non déclarée
```

Les deux sortent en code 1 si problème — utilisables en cron.

## Les 5 règles de code

### 1. `None` ne veut jamais dire zéro
`None` = **non mesuré**. Une métrique non mesurée est un **rejet**, jamais un
pass par défaut. Le legacy traitait un funding absent comme un funding nul :
c'est comme ça qu'un coût disparaît d'un backtest.

```python
# NON — le coût s'évapore silencieusement
funding = get_funding(symbol) or 0.0

# OUI — l'absence est une donnée
try:
    funding = load_funding_rate(symbol)
except CostDataUnavailable as exc:
    breakdown.missing.append(f"funding: {exc}")
```

### 2. Lever plutôt que renvoyer `None` sur une donnée critique
Un appelant distrait peut ignorer un `None`. Il ne peut pas ignorer une
exception. Voir `load_funding_rate()`.

### 3. Jamais `except: pass`
Explicitement listé comme bug prioritaire dans `AGENTS.md`. Attrape une
exception précise, et fais-en quelque chose de visible.

### 4. Déterminisme obligatoire
Tout aléatoire passe par `random.Random(seed)`, jamais le module global. **Un
benchmark non reproductible ne prouve rien.**

### 5. Zéro look-ahead
Un signal calculé sur la barre `i` n'est exécutable qu'à l'**open de `i+1`**.
C'est le bug classique qui fabrique de fausses stratégies gagnantes. Quand tu
écris de la logique de signal, écris le test anti-look-ahead avec.

## Les tests

Style `unittest`, en-tête standard (le projet n'a **pas** de `tests/__init__.py`
— ne pas en ajouter, ça changerait l'import des tests existants) :

```python
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.gates import evaluate_gates

class TestQuelqueChose(unittest.TestCase):
    def test_ce_qui_doit_etre_vrai(self):
        """Le POURQUOI du test, pas le quoi."""
        ...

if __name__ == "__main__":
    unittest.main(verbosity=2)
```

Un bon test ici **verrouille une erreur passée**. Exemples réels dans la suite :

- `test_funding_applies_to_notional_not_margin` — verrouille le ratio ×5 sur
  levier 5. Si quelqu'un « optimise » en repassant sur la marge, ça casse.
- `test_legacy_corpus_is_fully_rejected` — les 17 092 lanes legacy doivent
  toutes être rejetées. Si ça passe à > 0, les gates ont été affaiblis.
- `test_real_project_cache_is_stale` — le cache funding réel doit être refusé.

## Nommage et langue

- **Code, noms de fonctions, variables : anglais.**
- **Docstrings et commentaires : français.**
- Les commentaires expliquent le **pourquoi**, pas le quoi. Le quoi est déjà
  dans le code.

## Où mettre quoi

| Type | Emplacement |
|---|---|
| logique métier neuve | `backend/services/` |
| moteur de backtest | `backend/services/backtest_v2/` |
| lanes on-chain neuves | `backend/services/onchain/` (jamais la façade legacy) |
| tests | `tests/test_*.py` |
| utilitaire dev | `scripts/` |
| sortie de run, rapport daté | `reports/` — **jamais `docs/`** |
| doc vivante | `docs/0X-*.md` + déclarer dans `scripts/docs_audit.py` |
| connaissance durable | `docs/reference/` |

## Avant de proposer un changement

1. `python scripts/run_tests.py` → 0 échec
2. `python scripts/docs_audit.py` → exit 0
3. Si tu as touché au comportement des gates ou des coûts : **vérifie que le
   test de régression legacy rejette toujours 100 % du corpus**
4. Si tu as découvert un piège, documente-le à l'endroit où quelqu'un le
   rencontrera — docstring d'abord, doc ensuite

## Le repo n'est pas sous git

Il n'y a pas de `.git`. Donc : **aucune suppression sans sauvegarde préalable**.
Les sauvegardes de nettoyage vont dans `tmp/`.

Quand git sera initialisé, à exclure : `data/warehouse/` (généré),
`logs/`, `tmp/`, `__pycache__/`, `.env`.

## Secrets

`.env` à la racine. **Jamais lu, jamais affiché, jamais commit.** Aucune
exception, y compris « juste pour débugger ».
