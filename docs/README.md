# Documentation — carte de lecture

**Entrée projet** : [`00-CARTE.md`](00-CARTE.md) · **Structure** : [`../PROJECT_STRUCTURE.md`](../PROJECT_STRUCTURE.md) · **Lab** : [`lab/README.md`](lab/README.md)

Règles :
- **1 doc = 1 domaine** (ASTER / FOMO / OPENMARKET / X) sauf les docs *transverses*.
- **Data** : chaque entrepôt a sa doc ; ne pas fusionner les chiffres entre bases.
- **Horizons** de backtest : tag `H-1Y` | `H-MULTI` | `H-LIVE` | `H-MICRO` dans les rapports.

---

## 1. Transverse (lire dans l’ordre)

| Doc | Rôle |
|---|---|
| [00-CARTE](00-CARTE.md) | Carte vivante du projet entier |
| [01-onboarding](01-onboarding.md) | Arrivée sur le repo |
| [02-architecture](02-architecture.md) | Architecture |
| [03-methodology](03-methodology.md) | Discipline backtest (harnais, pré-enregistrement) |
| [04-runbook](04-runbook.md) | Ops / dépannage |
| [08-contributing](08-contributing.md) | Contribution |
| [13-orchestration](13-orchestration.md) | Nocturnes + timers (un domaine = une unit) |
| [lab/](lab/README.md) | Grind indicateurs : mortuary, primitives, hypothèses |

---

## 2. Data (entrepôts — ne pas mélanger)

Index détaillé → [`data/README.md`](data/README.md)

| Doc | Entrepôt / sujet | Domaine |
|---|---|---|
| [06-data](06-data.md) | Vue d’ensemble des bases vivantes + qui écrit quoi | ALL (index) |
| [24-donnees-aster](24-donnees-aster.md) | Warehouse Aster / klines / OI / depth / liq | **ASTER** |
| [26-openmarket-donnees](26-openmarket-donnees.md) | Entrepôt om_v27, manifest, coûts | **OPENMARKET** |
| [23-maitrise-fomo](23-maitrise-fomo.md) | Pipeline FOMO (ticks, REST, WS, paper) | **FOMO** |

Données runtime : `data/` (gitignored). La doc décrit le *contrat* ; les fichiers bruts ne vont pas dans `docs/`.

---

## 3. ASTER — machine, signaux, registre

Index → [`aster/README.md`](aster/README.md)

| Doc | Rôle |
|---|---|
| [10-strategies](10-strategies.md) | Historique des stratégies |
| [20-registre-indicateurs](20-registre-indicateurs.md) | **Source de vérité** des verdicts (tous domaines, sections) |
| [21-goal-performances](21-goal-performances.md) | Plan P1–P5 + dates de tir |
| [22-nos-indicateurs](22-nos-indicateurs.md) | Créations maison (règle + preuve) |
| [24-donnees-aster](24-donnees-aster.md) | Data Aster |

Rapports chiffrés → `reports/aster/` (pas ici).

---

## 4. FOMO

Index → [`fomo/README.md`](fomo/README.md)

| Doc | Rôle |
|---|---|
| [23-maitrise-fomo](23-maitrise-fomo.md) | Maîtrise pipeline + accès |

Rapports → `reports/fomo/`. Paper = `scripts/fomo_paper_forward.py` (pas `the_machine`).

---

## 5. OPENMARKET x501

Index → [`openmarket/README.md`](openmarket/README.md)

| Doc | Rôle |
|---|---|
| [25-openmarket-x501](25-openmarket-x501.md) | Mission, chiffres, roadmap |
| [26-openmarket-donnees](26-openmarket-donnees.md) | Data om_v27 |
| [27-pouvoirs-kscript](27-pouvoirs-kscript.md) | Registre capacités kScript (exploitation) |
| [28-protocole-ab-x501](28-protocole-ab-x501.md) | Protocole A/B pré-enregistré |
| [29-fill-maker-mesure](29-fill-maker-mesure.md) | Preuve fill maker |
| [30-flux-funding-banc-local](30-flux-funding-banc-local.md) | Banc flux / funding (KILL) |
| [31-absorption-banc-evenements](31-absorption-banc-evenements.md) | Banc absorption |
| [32-references-banc-local](32-references-banc-local.md) | VWAP / volume profile (famille close) |
| [33-oi-banc-local](33-oi-banc-local.md) | Banc OI continuation |
| [34-oi-regime-banc-local](34-oi-regime-banc-local.md) | Banc OI régime |
| [35-openmarket-oi-ushape](35-openmarket-oi-ushape.md) | Banc forme en U OI |
| [36-openmarket-lsr-banc-local](36-openmarket-lsr-banc-local.md) | Banc LSR |

**Isolé** de La Machine. Code : `scripts/studies/x501_openmarket/`. Rapports : `reports/openmarket/`.

---

## 6. Infra externe encore vivante

| Doc | Rôle |
|---|---|
| [17-mmt-m5](17-mmt-m5.md) | Terminal MMT/M5 |

---

## 7. Archive

Anciens docs annotés : [`archive/`](archive/) (si présent) — bibliothèque, pas vérité opérationnelle.

---

## Où *ne pas* écrire

| Mauvais réflexe | Bon endroit |
|---|---|
| Coller un ROI FOMO dans un doc OpenMarket | `reports/fomo/` + section FOMO du registre |
| Mettre un banc kScript dans 00-CARTE | doc 30–36 ou 25 |
| Logger de la data brute dans docs/ | `data/` (gitignore) + contrat dans 06/24/26 |
| Nouvelle idée d’indicateur sans hypothèse | `lab/hypotheses/` d’abord |
