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

# ⚙️ ENVIRONNEMENT (omarchy, depuis 2026-09)

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
