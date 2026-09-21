---
title: Index documentation — trading-agent
status: living
owner: cheurteen
updated: 2026-08-09
---

# Documentation — trading-agent

**Tu débarques ? Lis `01-onboarding.md`. Rien d'autre.**

Le pipeline est désormais **OPÉRATIONNEL** : la découverte (`nightly_campaign.py --run`) et la validation OOS (`reevaluate_oos.py`) sont câblées, et tournent chaque nuit en systemd timer sur 10 paires (BTC, ETH, SOL, XRP, BNB, DOGE, ADA, AVAX, LINK, LTC). Obtenir **0 survivant sur l'univers actuel** (6 stratégies / ~3000 bougies par paire) est un résultat **attendu, pas un bug** — voir `13-orchestration.md`.

## Les docs vivants

| Doc | Répond à la question |
|---|---|
| [`01-onboarding.md`](01-onboarding.md) | Je débarque sur le projet, je fais quoi ? |
| [`02-architecture.md`](02-architecture.md) | Où vit quoi dans le code ? |
| [`03-methodology.md`](03-methodology.md) | **Comment on évite de se mentir sur un backtest ?** ⚠️ critique |
| [`04-runbook.md`](04-runbook.md) | Quelles commandes je tape ? |
| [`05-data-sources.md`](05-data-sources.md) | Quelles sources de données marchent encore ? |
| [`06-data.md`](06-data.md) | **Comment la data est rangée, et ce qu'elle révèle** ⚠️ critique |
| [`07-backtest-engine.md`](07-backtest-engine.md) | Comment le moteur empêche le mensonge |
| [`08-contributing.md`](08-contributing.md) | Conventions de code, tests, où mettre quoi |
| [`09-pipeline.md`](09-pipeline.md) | **La chaîne automatisée : donnée → verdict** |
| [`10-strategies.md`](10-strategies.md) | Stratégies + première campagne réelle sur BTC 1h |
| [`11-campaign-real.md`](11-campaign-real.md) | Gardes ajoutées + résultat campagne 3001 bougies |
| [`12-nondirectional.md`](12-nondirectional.md) | 3 stratégies non-directionnelles + bilan 2598 combos |
| [`13-orchestration.md`](13-orchestration.md) | **La boucle découverte → validation OOS** (runbook) |

Plus `security/` — audits et accès réseau (Tailscale, ACL, threat models).

## Les 4 règles anti-prolifération

Ce dossier est passé de 36 fichiers à 5. Pour que ça reste vrai :

1. **Un doc = une question que quelqu'un pose vraiment.** Pas de question, pas de doc.
2. **Un snapshot daté n'est pas un doc.** Tout ce qui est une sortie de run
   (statut, health dashboard, quality report, watchlist, comparaison de lanes)
   va dans `reports/`, horodaté. Jamais ici.
3. **Pas de nouveau fichier à la racine de `docs/`.** Connaissance durable et
   rarement lue → `reference/`. Périmé mais à garder → `archive/`.
4. **Plus jamais de doc HTML** (décision 2026-09-21) : les rapports visuels
   sont produits en **PDF vectoriel** (via `scripts/html_to_pdf.py` ou rendu
   HTML→PDF comme CE-001 v2) ; le markdown reste le format des docs vivants.

## Les dossiers

- `reference/` — connaissance durable, rarement lue, jamais périmée
  (API Aster, streams WS, historique de recherche, accès client, RAG, roadmap stratégie).
- `archive/` — gelé, lecture seule. Contexte historique. **Ne pas utiliser
  comme source de décision.** Contient la suite Aster legacy (morte) et les
  anciens rapports HTML.
- `security/` — audits sécurité, ACL Tailscale, onboarding accès privé.

## État du projet en une ligne

La suite Aster **legacy est morte** (0 promotion, PnL négatif, WR 41 %) — voir
`03-methodology.md` pour ce qu'on en retient. Le **pipeline data Aster est
vivant**. La prochaine étape est un moteur de backtest strict et automatisé :
`reference/strategy-roadmap-2026-08.md`.
