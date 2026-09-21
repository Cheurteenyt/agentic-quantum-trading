---
title: Architecture — où vit quoi
status: living
owner: cheurteen
updated: 2026-08-09
---

# Architecture

Remplace l'ancien `PROJECT_STRUCTURE.md` et les 7 `README.md` de sous-dossiers.

## Flux mental

Raisonne toujours dans ce sens quand tu débugues :

```
Frontend (React) → API HTTP → Router → Service → Data (cache / API externe / DB)
```

Un symptôme frontend a presque toujours sa cause dans un service. Remonte le
flux, ne devine pas.

---

## `backend/` — FastAPI

```
backend/
├── main.py          point d'entrée FastAPI
├── config/          config backend (trading.py = ex trading_config.py)
├── routers/         couche HTTP — un fichier par domaine
├── services/        logique métier — c'est ici que sont les bugs
├── data/            données locales du backend
└── static/          build front servi par le backend
```

**Routers** (`backend/routers/`) — la surface HTTP :

| Router | Domaine |
|---|---|
| `market.py` | données marché, prix, exchanges |
| `onchain.py` | lanes on-chain, Aster, analyses chain |
| `alpha_lab.py` | expérimentation stratégies |
| `intel.py` / `news.py` | agrégation intelligence & news |
| `arkham.py` / `entity.py` | tracking entités & wallets |
| `agents.py` / `chat.py` | agent local, conversation |
| `desktop.py` / `vision.py` | intégrations client |

**Services** (`backend/services/`) — la logique. Trois familles :

- **alpha\_\*** — `alpha_lab`, `alpha_risk`, `alpha_simulation`,
  `alpha_sellability`, `alpha_wallets`, `alpha_premium_data`.
  Simulation et risque. C'est le voisinage naturel du futur moteur de backtest.
- **onchain\_\*** + `onchain/` — couverture, qualité, flux, entités, statut.
  ⚠️ `onchain_engine.py` est une **façade legacy**. Le code neuf va dans
  `backend/services/onchain/`, jamais dans la façade.
- **collecte / intel** — `multi_exchange`, `collector`, `arkham_*`,
  `scrapling_intelligence`, `intel_aggregator`, `footprint`.

Suite Aster : tout sous `backend/services/onchain/aster/`. Le code de stratégie
y est **mort** (voir `03-methodology.md`), mais les validateurs
(`ws_symbol_quality`, `mark_index`, `microstructure`) et le dataset archivé
restent utiles.

---

## `frontend/` — React + Vite + TypeScript

```
frontend/src/
├── App.tsx / main.tsx
├── pages/         écrans        ← priorité debug
├── services/      appels API    ← priorité debug
├── hooks/         état & data   ← priorité debug
├── components/    UI
├── contexts/      état global
└── i18n.tsx       traductions
```

Aucun script Python ne doit se trouver sous `frontend/src/`.

---

## Les autres dossiers

| Dossier | Rôle |
|---|---|
| `agent/` | package agent local (`SYSTEM.md` = prompt, utilisé par `routers/agents.py`) |
| `rag/` | RAG : config, index, `memory/`, sources. Les décisions produit se reflètent ici |
| `configs/` | config non-secrète, groupée par intégration |
| `data/` | snapshots locaux et données runtime |
| `reports/` | **sorties générées, horodatées** — y compris `legacy-snapshots/` |
| `scripts/` | utilitaires dev : `qwen/`, `security/`, `archive/` |
| `logs/` | logs locaux uniquement |
| `archives/` | artefacts historiques non-runtime |
| `tmp/` | scratch ignoré (contient les sauvegardes de nettoyage) |
| `integrations/` | ponts externes — ⚠️ MT5 = legacy mort |

---

## Politique de racine

La racine ne contient que : `AGENTS.md`, `PROJECT_STRUCTURE.md`,
`.gitignore`, `.env.example`, `requirements.txt`, le launcher
(`start_all.sh`), les wrappers de compatibilité, et les dossiers ci-dessus.
(`SESSION_LOG.md` et `.SESSION_CHECKPOINT.md` vivent dans `archives/`
depuis la migration omarchy 2026-09 ; `start_all.bat` a été supprimé.)

Pas de script de test, de screenshot, de log, de backup ni de patch one-off à la
racine.

---

## Wrappers de compatibilité

Ces fichiers n'existent que pour ne pas casser des commandes existantes. **Le
code neuf importe la vraie implémentation, jamais le wrapper.**

```
mt5_bridge.py                             -> integrations/mt5/bridge.py   (MORT)
trading_config.py                         -> backend/config/trading.py
scripts/local_qwen_review.py              -> scripts/qwen/local_qwen_review.py
scripts/benchmark_local_qwen_profiles.py  -> scripts/qwen/...
scripts/benchmark_core_equity_qwen_reviews.py -> scripts/qwen/...
scripts/validate_tailscale_acl.py         -> scripts/security/validate_tailscale_acl.py
```

---

## Secrets

`.env` à la racine. Jamais lu, jamais affiché, jamais commit. `.env.example`
documente les clés attendues sans valeur.
