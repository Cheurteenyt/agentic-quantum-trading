---
title: Orchestration de la boucle découverte → validation OOS
status: living
owner: cheurteen
updated: 2026-08-09
---

# Orchestration — la boucle découverte/validation

> Le pipeline ne dit pas seulement non une fois. Il dit non **en continu**, et
> garde la preuve. Ce runbook explique comment lancer la boucle et ce qui se
> passe à chaque étape.

### But

Transformer le pipeline manuel (un run ponctuel, lu, puis oublié) en un
**détecteur d'edge permanent et gardé** : chaque jour, on teste l'univers
connu ; tout ce qui survit aux gardes devient un candidat en attente ; après
30 jours de données inédites, le candidat est confirmé ou expiré. Un edge réel
ne peut atterrir en live que s'il a traversé cette chaîne — jamais sorti d'un
backtest unique.

### Séquence (la chaîne)

1. **Données fraîches** — `fetch_klines.py` ramène les bougies réelles
   (provenance + détection de trous). Sans data neuve, la campagne refusera.
2. **`nightly_campaign.py --run`** — lance la campagne complète : l'engine
   teste toutes les combinaisons, `gates.py` juge chaque lane,
   `multiplicity.py` applique la correction **GLOBALE** (toutes stratégies ×
   toutes paires), les survivants sont **enregistrés comme candidats**
   (`candidates.py`), et un rapport est produit (avec dénominateurs).
3. **Attendre 30 jours** — les candidats mûrissent sur des données qu'ils
   n'ont jamais vues. Évaluer plus tôt = réutiliser la fenêtre de découverte.
4. **`reevaluate_oos.py`** — rejoue chaque candidat mûr sur les données OOS
   réelles arrivées depuis : `forward_sharpe`, `forward_trades`, et le ratio
   de maintien du sharpe → **confirm** ou **expire** (rejet motivé).
5. **Live** — un candidat **CONFIRMÉ** (les trois conditions OOS remplies) est
   le seul habilité à passer en live. Un survivant non confirmé n'y va jamais.

### Commandes

```bash
# 1) Données fraîches — vérifier puis récupérer
python scripts/fetch_klines.py --check
python scripts/fetch_klines.py --fetch-range BTCUSDT ETHUSDT SOLUSDT --target-bars 3000
```

```bash
# 2) Campagne + gates + multiplicité GLOBALE + register candidats + rapport
python scripts/nightly_campaign.py --run
```

```bash
# 3) Attendre 30 jours — aucune commande.
#    Le temps est le validateur ; vérifier entre-temps les candidats mûrs :
python scripts/nightly_campaign.py --review
```

```bash
# 4) Réévaluation OOS sur données réelles postérieures (confirm / expire)
python scripts/reevaluate_oos.py
```

```bash
# 5) Live — UNIQUEMENT si confirmé par l'étape 4.
#    Hors périmètre de ce runbook : brancher le candidat confirmé en live.
```

### Garde-fous

Trois niveaux, **aucun ne se saute** :

- **Gates lane (`gates.py`)** — refuse le sous-échantillon (< 100 trades),
  l'overfit, les coûts absents. Sans ça, une lane trop courte passe par
  accident et devient un faux gagnant.
- **Multiplicité campagne (`multiplicity.py`, GLOBALE)** — correction
  Bonferroni sur le nombre **total** de combinaisons testées (toutes
  stratégies, toutes paires). Sauter ça industrialise le faux positif : à
  1000+ essais, un « gagnant » par hasard est l'issue la plus probable.
- **Temps / candidats (`candidates.py` + 30j)** — aucun survivant ne va en
  live sans période OOS postérieure obligatoire. Sauter ça fait passer en
  live un résultat qui n'a jamais vu de donnée inédite.

Pourquoi on ne saute aucun : chacun ferme un angle mort différent (trop peu de
trades, trop d'essais, pas de temps). Enchaînés, ils transforment « j'ai un
backtest gagnant » en « j'ai une hypothèse survivante à confirmer ».

### Interpréter un rapport

- **0 survivant** — *info utile, pas échec.* Le marché n'a favorisé aucune
  classe testée sur la fenêtre. C'est la réponse réelle, gratuite, et honnête.
  Sur l'univers actuel (6 stratégies / 3 paires / ~9000 bougies) un 0 est
  **attendu**, pas un bug.
- **≥ 1 survivant** — *à confirmer dans le temps.* C'est un candidat, pas une
  stratégie. Il attend 30j, puis `reevaluate_oos.py` tranche. Un survivant non
  confirmé est un rejet, jamais un live.

### Fréquence suggérée

- **Quotidienne** : `nightly_campaign.py --run` (idéalement en cron la nuit).
- **+30j après chaque découverte** : `reevaluate_oos.py` sur les candidats
  mûrs (`pending(min_age_days=30)`).
