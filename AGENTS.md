# ⚡ Hermes Agent — Trading Agent (Stable & Controlled)

## 🎯 OBJECTIF
Agent fullstack (FastAPI backend + React frontend).

Tu dois :
- analyser et corriger des bugs rapidement
- lire un minimum de fichiers
- éviter toute exploration inutile
- ne jamais casser l'environnement

---

# 📁 CHEMIN PROJET (OBLIGATOIRE)

Projet UNIQUE (machine omarchy, SSD monté) :

/run/media/cheurteen/Jeux SSD/trading-agent

⚠️ Le chemin contient un espace : TOUJOURS le quoter dans les commandes.
(L'ancien chemin WSL /mnt/d/trading-agent n'existe plus.)

---

# ⚡ ENVIRONNEMENT (omarchy, depuis 2026-09)

- Python : **géré par uv** — `.venv/` à la racine créé via `uv venv`
  (CPython 3.13 géré par uv, PAS le python pacman). Installs UNIQUEMENT via
  `uv pip install --python .venv/bin/python -r requirements.txt`.
  Jamais de pip système, pas de `python -m pip` dans le venv.
- Node : 26 — `npm` dans `frontend/` uniquement (pnpm recommandé quand
  installé : `sudo pacman -S pnpm`, store global anti-doublons).
- Campagne nocturne : systemd user timer `trading-agent-nightly.timer`
  (NE PAS lancer la campagne à la main en parallèle du timer)
- Runbook pipeline/backtest : `docs/13-orchestration.md`
- Tests rapides (hors réseau) : `.venv/bin/python scripts/run_tests.py --fast`

---

# 🚦 GATE DE VÉRITÉ — OBLIGATOIRE avant tout commit / PR

> **Toute IA qui touche ce repo DOIT faire passer ces commandes depuis la
> racine** (chemin quoté). Elles sont le contrat : la CI les rejoue à chaque
> push, un PR rouge est refusé. Ne PAS les contourner, ne PAS les « corriger »
> en baissant un baseline sans PR dédiée.

```bash
cd "/run/media/cheurteen/Jeux SSD/trading-agent"
.venv/bin/python scripts/run_tests.py --fast          # suite (2162 tests, 2 échecs connus/pré-existants)
.venv/bin/python scripts/deep_audit.py --check         # rochet classes G1-G10 (bloquant)
.venv/bin/python scripts/claim_verify.py --all         # preuves F-XXX (42/42 attendu)
.venv/bin/python scripts/research_integrity.py         # invariants I001-I009
.venv/bin/python scripts/ledger_provenance.py          # N5 : ledger ↔ runs (verdict du DERNIER attempt)
.venv/bin/python scripts/ledger_puissance.py           # N6 : chaque verdict vivant porte son n ≥ 10
.venv/bin/python scripts/audit_path_root.py            # G10 : parents[N] résout à la racine
.venv/bin/python -m pyflakes backend scripts tests     # noms indéfinis (bloquant)
```

**Si l'un de ces oracles rougit : c'est un VRAI défaut, pas un obstacle.** Le
corriger, ou documenter une dérogation explicite (`n_degression` dans le
ledger, `# deep-audit:ignore[=Gx]` dans le code) — jamais masquer en silence.
Doctrine complète : `docs/41-methode-audit-profond.md`.

**Ne JAMAIS citer un chiffre de performance sans son statut.** Les chiffres
`+5 082 %/an`, `+1 498 %/an`, `+3 905 %/an` sont **MORTS** (F-033/F-034) :
20 liqs réelles, DD 99,2 %, final $1. La vérité courante est dans
`research/STATE.md` + `docs/20-registre-indicateurs.md`, PAS dans le README
ni les vieux registres. Le registre `docs/21-vagues-registre.md` est
historique daté — ses chiffres d'époque ne sont pas des edges actuelles.

**`onchain_engine.py` = 101 663 lignes.** Ne PAS le lire en entier. Cibler
par fonction. C'est un monolithe connu (48% du backend) — ne pas ajouter de
fonction sans chercher l'existante d'abord (duplication = le défaut dominant).

---

## ❌ INTERDICTIONS ABSOLUES

Ne jamais :
- utiliser /home/user/*
- utiliser /mnt/trading-agent
- utiliser des chemins approximatifs
- lancer find /mnt ou scans globaux
- lancer pip install / npm install hors du projet
  (uniquement `.venv/bin/pip` pour le backend, `npm` dans `frontend/`)
- lancer des commandes avec &
- relancer un serveur plusieurs fois
- modifier l'environnement système

---

# ⚡ MODE PAR DÉFAUT (SAFE)

Par défaut :
- analyse uniquement
- ne lance aucun serveur
- ne fait aucune commande lourde

---

# ⚡ MODE DEBUG LIVE (STRICT)

Uniquement si l'utilisateur dit :
- debug live
- test runtime
- lance le projet

---

## 🧪 PROCÉDURE DEBUG LIVE

### 1. Vérifier les chemins

pwd
ls -la "/run/media/cheurteen/Jeux SSD/trading-agent"
ls -la "/run/media/cheurteen/Jeux SSD/trading-agent/backend"
ls -la "/run/media/cheurteen/Jeux SSD/trading-agent/frontend"

Si erreur → STOP

---

### 2. Lancer backend (UNE SEULE FOIS)

cd "/run/media/cheurteen/Jeux SSD/trading-agent/backend" && ../.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

---

### 3. Attendre 5 secondes

---

### 4. Tester API

curl -s http://localhost:8000/health

Si erreur → STOP

---

### 5. Lancer frontend

cd "/run/media/cheurteen/Jeux SSD/trading-agent/frontend" && npm run dev

---

### 6. Analyser uniquement

- erreurs console
- erreurs API
- endpoints cassés
- données vides

---

## ⚠️ LIMITES DEBUG LIVE

- lancer une seule fois
- timeout court
- pas de boucle
- pas de retry automatique
- stopper dès erreur

---

# ⚡ GRAPHIFY

Non installé sur omarchy (2026-09). Les données restent dans `graphify-out/`.
Si réinstallé un jour : `graphify query "<problème>" --graph ./graphify-out/graph.json --budget 800`, puis max 2 fichiers, ne pas relancer.

---

# ⚡ LECTURE CODE

- max 2 fichiers
- max 2 lectures par fichier

### Backend priorité :
- routers/
- services/

### Frontend priorité :
- pages/
- services/
- hooks/

---

# ⚡ FLOW LOGIQUE

Toujours raisonner :

Frontend → API → Router → Service → Data

---

# ⚡ BUGS PRIORITAIRES

### Backend :
- except: pass
- cache [] ou None
- contract_address manquant
- fallback API cassé
- return prématuré

### Frontend :
- mauvais endpoint
- undefined / null
- mauvaise structure JSON
- données non affichées

---

# ⚡ MODE PATCH

Toujours répondre avec :

### Analyse
### Problème
### Patch minimal
### Test

---

# ⚡ LIMITES

- max 5 itérations
- max 2 fichiers
- pas de refactor global
- pas de modification inutile

---

# ⚡ SI ERREUR ENVIRONNEMENT

Si :
- dépendance manquante
- module absent
- erreur système

Alors :
- STOP immédiatement
- afficher l'erreur
- proposer solution
- ne rien installer automatiquement

---

# ⚡ OBJECTIF PERFORMANCE

- réponse rapide
- ciblage précis
- zéro perte de tokens

# ⚡ MODE PARALLÈLE (subagents) — par défaut

Le user veut de la VITESSE : dès qu'une tâche a ≥ 2 flux indépendants,
les dispatcher en Agent parallèles (UN SEUL message, plusieurs appels Agent).
- Le thread principal garde : coordination, services systemd, git push final.
- Long/network (backfills, collectes) → Bash en run_in_background, JAMAIS bloquant.
- Analyse/read-only sur une DB + écritures sur une AUTRE DB : parallèle OK.
- Deux écrivains sur la MÊME DB : jamais en parallèle (WAL ou pas).
- Pattern éprouvé : 1 background bash + 2 agents courts (analyse, docs+git).
- Chaque agent : prompt autoportant (chemins quotés, .venv/bin/python,
  interdictions explicites, format de réponse chiffré, ~12 lignes max).

# ⚡ CONVENTION SCRIPTS (études & racine de scripts/) — depuis le 28/09

- Les one-shots d'études naissent dans `scripts/studies/` (ou directement
  dans `scripts/archive_studies/` si la doctrine est déjà close) ; seuls les
  scripts PERMANENTS (collecteurs, the_machine, paper_forward, harnais,
  briques du nocturne) restent à la racine de `scripts/`.
- Une étude CLOSE (verdict NUL/CONTEXTE/fermé dans docs/20-registre-indicateurs.md)
  est archivée par `git mv` dans `scripts/archive_studies/` avec l'en-tête
  `# ARCHIVÉ (date)` — on ne supprime jamais, on re-catégorise.
- Condition d'archivage : verdict rendu ET aucun fichier vivant ne l'importe
  (grep avant de déplacer). Carte racine : `scripts/README.md`.


# ⚡ RESEARCH FIREWALL (depuis le 05/10 — audit GPT v3 §26-27)

Le modèle est libre de penser, proposer et expérimenter — il n'est JAMAIS
l'autorité de vérité. La vérité = hypothèse → code → exécution → résultat →
vérification → evidence → ledger → STATE.

- **Ledger de preuves** : `research/evidence/facts.jsonl` (35 faits seedés)
  — schéma et règles dans `research/evidence/README.md`.
- **Le vérificateur** : `python scripts/claim_verify.py --all` (exit 1 si un
  fait est CONTRADICTED/UNVERIFIED). Un fait contredit se corrige via PR.
- **Le brief d'entrée de session** : `python scripts/context_manifest.py` —
  HEAD + STATE + les faits + le budget + les derniers verdicts. LIRE CELA
  AVANT docs/20 (146 Ko) ou toute relecture massive.
- **La règle** : toute affirmation porte son id de fait (F-XXX) ou sa
  commande de reproduction. UNVERIFIED n'entre jamais dans STATE.md.

# ⚡ RESEARCH OS (depuis le 05/10 — brief Research OS V3, PR 1-3)

Deux modes, deux budgets (policy.yaml + lab_ledger v3) :
- **DISCOVERY** : `--mode discovery` — TRAIN only, hors budget scientifique,
  JAMAIS promote ; le compute est gouverné, pas le budget.
- **CONFIRMATION** : pré-enregistré, protocole gelé, le budget 20/sem
  s'applique ; N de multiplicité CUMULATIF (jamais remis à zéro par la
  semaine).
- **La policy est dans `agent/policy.yaml`** (PAS à la racine) — `prior_trials:
  341` y est défini ; c'est ce qui alimente le N de Bonferroni (341 + confirmations
  vivantes + 1). La chercher à la racine donne un `prior=0` silencieux et un N faux.
- **PREFLIGHT avant tout run couplé à la DB** : `python scripts/preflight.py
  ...` — IMPORT OK ≠ PIPELINE OK (le crash open_time du 05/10). Un smoke
  test sur données réelles est la règle.
- Le journal d'états : research/ledger/experiments.jsonl (append-only).
