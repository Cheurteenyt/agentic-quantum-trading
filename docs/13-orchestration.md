> ⚖️ **PÉRIMÈTRE (audit GPT v3 §14)** : ce document est le RUNBOOK opérationnel (quand lancer quoi). Les critères scientifiques de confirmation font autorité dans `research/protocols/` + `agent/policy.yaml`. MISE À JOUR à la ratification (05/10) : le protocol-v2 est RATIFIÉ — l'autorité des SEUILS est `research/protocols/active.yaml` ; la logique de 30 jours ci-dessous = le MÉCANISME de maturation du runbook (les seuils font foi dans active.yaml).

---
title: Orchestration de la boucle découverte → validation OOS
status: living
owner: cheurteen
updated: 2026-10-05
---

# Orchestration — la boucle découverte/validation

> Le pipeline ne dit pas seulement non une fois. Il dit non **en continu**, et
> garde la preuve. Ce runbook explique comment lancer la boucle et ce qui se
> passe à chaque étape.

## Les 3 nocturnes (30/09) — la séparation des domaines

Le nocturne unique de 102 steps mélangeait ASTER, FOMO et X : une édition du
fichier unit pendant un run (« command vanished ») abandonnait la queue des
steps EN SILENCE — 3 nuits de whale_radar perdues (27-29/09). Découpage :

| Unité | Heure | Steps | Domaine |
|---|---|---|---|
| trading-agent-nightly | 03:00 | 65 | ASTER (caches, klines, machine, campagne, ménage) |
| x-nightly | 03:21 | 20 | X (harvest, scores, rotation, pont aster, registre X) |
| fomo-nightly | 03:55 | 9 | FOMO (garde-fenêtre, radar baleines, ondes, flows, harvest) |

Le décalage préserve les dépendances : le X-nightly finit avant le
fomo-nightly pour que wave_detector (la fusion baleines × X) lise le harvest
frais. La règle : **ne jamais éditer un fichier unit pendant son run**, et un
domaine = une unité (une édition n'emporte plus les autres domaines).

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
# 1) Données fraîches — vérifier puis récupérer (--fetch-range prend UNE paire)
python scripts/fetch_klines.py --check
python scripts/fetch_klines.py --fetch-range BTCUSDT --target-bars 3000
python scripts/fetch_klines.py --fetch-range ETHUSDT --target-bars 3000
python scripts/fetch_klines.py --fetch-range SOLUSDT --target-bars 3000
# ... et idem pour XRPUSDT BNBUSDT DOGEUSDT ADAUSDT AVAXUSDT LINKUSDT LTCUSDT.
# Depuis 2026-09-21, le timer systemd fait les 10 paires automatiquement.
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
  Sur l'univers actuel (6 stratégies / 10 paires / ~3000 bougies chacune) un 0 est
  **attendu**, pas un bug.
- **≥ 1 survivant** — *à confirmer dans le temps.* C'est un candidat, pas une
  stratégie. Il attend 30j, puis `reevaluate_oos.py` tranche. Un survivant non
  confirmé est un rejet, jamais un live.

### Fréquence suggérée

- **Quotidienne** : `nightly_campaign.py --run` (idéalement en cron la nuit).
- **+30j après chaque découverte** : `reevaluate_oos.py` sur les candidats
  mûrs (`pending(min_age_days=30)`).

### Dette : le mobula top-up, 3e écrivain borné de fomo.db (29/09)

- Les 16 « database is locked » de 19h47-19h51 venaient d'une **transaction
  fantôme** : un commit en échec « locked » sans rollback laissait la txn
  ouverte, tenant le write-lock pendant les appels réseau (3,5 s/token).
  Fix : rollback systématique sur toute voie d'échec (`fomo_mobula_topup.py`).
- `topup_dead` a migré vers `data/fomo/fomo_mobula.db` (lecteur unique,
  copie one-time ATTACH mode=ro, COUNT vérifié 13=13).
- `fomo_ohlcv` reste écrit dans fomo.db : 15+ lecteurs (dont derek_watch.py)
  rendent une base dédiée cassante. Dette assumée : writer borné (commit par
  token, rollback anti-fantôme, busy_timeout 30 s, budget de passe 480 s).

## La porte conforme v6 + la couche portefeuille (05/10)

Le Research OS a sa chaîne complète — la découverte produit, la porte de
confirmation JUGE sous protocole, la couche portefeuille dit ce que vit un
wallet de 100 $ (audit GPT v6, 10 réclamations confirmées et corrigées).

### La découverte (gratuite, TRAIN only)

```bash
# une spec
python3 scripts/research_runner.py discovery --spec research/queue/EXP-xxx.json
# la file entière (récursive — bonsai/ inclus, done/ exclu)
python3 scripts/research_runner.py grind
# la sélection (clusters + Pareto, AUCUN verdict de PASS ici)
python3 scripts/research_runner.py select
```

La découverte gèle ses **seuils** (l'expanding quantile à la dernière barre
TRAIN) dans `research/runs/<id>/summary_discovery.json` →
`frozen_thresholds`. C'est l'artefact que la confirmation réutilisera tels
quels — re-calibrer sur la validation est structurellement impossible.

### La confirmation (1 slot, protocole-v2 obligatoire)

```bash
python3 scripts/research_runner.py confirm --spec research/queue/EXP-xxx.json
```

La porte applique, dans l'ordre : **MODE_MISMATCH** (une spec déclarée
`mode: discovery` ne passe jamais — 0 slot) → **WINDOW_MISMATCH** (la
validation doit intersecter les fenêtres gelées d'`active.yaml` ; une
fenêtre tronquée est tracée `coverage_pct` et INÉLIGIBLE au PASS) →
preflight (0 slot sur échec d'infra) → étude **par fenêtre gelée** avec
seuils gelés + embargo 72h à la frontière train→validation → verdict :
`windows_pass ≥ windows_pass_required` (5/6) ET moyenne pondérée par n >
min_mean ET **chaque fenêtre** : mean > 0 ∧ stress ×1,5 > 0 ∧ DD MTM ≤
max_window_loss_pct (15 %) ET couverture funding ≥ min_fund_coverage ET
dégradation train→validation ≤ 70 %.
**CONFIRMED ≠ promote.** Le verdict ouvre le droit au wallet et au forward
(maturation 30 jours, seuils forward_confirmation d'active.yaml).

### Le wallet (la couche portefeuille)

```bash
python3 scripts/research_runner.py portfolio --id EXP-xxx                    # vue dispo
python3 scripts/research_runner.py portfolio --id EXP-xxx --view validation  # exige un confirm
python3 scripts/research_runner.py portfolio --id EXP-xxx --baseline         # buy-and-hold seul
```

Un wallet sur la vue **validation** exige un run de confirmation existant
(l'artefact fait foi) — la vue **train** est libre. Séquence : une position
par symbole (anti-chevauchement), marge ≤ 1 % de l'équité courante, lev 1x
défaut, liquidation **simulée** (défaut PR-8 : mort au premier franchissement réel
du seuil sur le chemin intrabar ; `liq_mode="stress"` garde la borne ex
ante — MAE ≥ 100/lev − 0,5), bookage au mois de sortie, DD par fenêtre
gelée contre le plafond `max_window_loss_pct` (15 %). Causalité v14 :
signal=close(t) → entry=open(t+1), verrouillée par mutation test.
Le rapport inclut la **baseline equal-weight long-and-hold** des mêmes
symboles : un edge qui ne bat pas ses propres actifs tenus passifs est une
narration. Sur CONFIRMED, le bloc WALLET est appendu automatiquement au
report.md du run.

### Ce qui a changé le 05/10 (audit v6) — à savoir pour lire les anciens chiffres

- **funding absent = NaN** (plus 0.0) : les symboles sans funding_history ne
  matchent plus les conditions `fund_last` ; `event_study` rapporte
  `fund_cov`. Les discoveries d'avant le fix (H-01 notamment) sont à
  re-mesurer avant tout confirm.
- **snapshot_id** hash high/low/volume en plus de close : un backfill de
  bougies invalide le cache des labels (re-build au premier run, ~minutes).
- **moyenne agrégée pondérée par n** : un symbole à 3 events ne pèse plus
  autant qu'un symbole à 3 000.
- `grind` est récursif (les sous-dossiers de la queue sont traités).

## Le forward du Research OS — la 3e étape (05/10)

La confirmation a jugé sur les fenêtres gelées ; le protocole exige ensuite la
MATURATION : 30 jours de données inédites (`forward_confirmation` d'active.yaml
: min_forward_sharpe 0.5, min_forward_trades 100, min_vs_discovery 0.5). Le
module `scripts/research_forward.py` fait vivre les candidats CONFIRMÉS :

```bash
python3 scripts/research_forward.py --collect        # tous les confirmés (nocturne 03:00)
python3 scripts/research_forward.py --status         # l'horloge de maturation
python3 scripts/research_runner.py forward --collect # la même porte (porte unique)
```

- **COLLECT** (branché au nocturne après le fetch klines, `ExecStart=-`) :
  évalue le masque GELÉ sur les barres 1h fermées postérieures au
  `validation_end` — les données qu'aucun fitting n'a jamais vues — et
  journalise `research/forward/<run_id>.jsonl` (append-only, idempotent par
  (symbole, open_time) : une nuit manquée ne perd rien, rejouée ne double rien).
- **STATUS** : les trades fermés mesurés depuis les klines brutes (mêmes
  conventions que le kernel), stats courantes, mini-wallet (run_wallet),
  horloge de maturation (jours depuis le manifest de confirmation + trades).
- Le forward opère VOLONTAIREMENT hors DataScope (les fenêtres gelées
  s'arrêtent au validation_end — tout ce qui suit est le test en cours).
  Aucun seuil n'y est re-calibré JAMAIS. READY (30 j + 100 trades) ⇒ review
  de protocole, JAMAIS promote automatique.

Collecte initiale (05/10) : crash-short-6h 49 trades fermés à +0,801 %/trade
(WR 87,8 %), h-18 155 trades à +0,385 %/trade (WR 65,8 %) — les deux tiennent
leur edge hors échantillon dès les premières semaines.

## Le portefeuille MTM (PR-2, 05/10)

Le wallet du Research OS publie désormais TROIS drawdowns, au lieu d'un seul
flaté : **MAX_DD_MTM** (équité horaire mark-to-market, marks = dernier prix
clôturé connu), **MAX_DD_MTM_WORST** (marks intrabar hi/lo — la borne haute
de l'excursion adverse, short au high / long au low) et **MAX_DD_CLOSE**
(l'ancien, clôture-seule, conservé pour comparaison). La marge est
dimensionnée sur l'équité MTM courante ; la liquidation ex ante absorbe la
marge entière dès l'heure d'entrée ; la comptabilité se réconcilie exactement
(Δequity = realized + funding − fees) ; la concurrence est mesurée
(max/avg_concurrency, marge engagée, exposition gross/long/short).

Fix kernel associé (trouvé par le test de complétude funding) : la série
FundingSeries est en MILLISECONDS — l'ancien /1e6 parasitait fund_H (garbage
≈ 0) et rendait fund_last constant. LABEL_VERSION bumpée v2 : tout le cache
des labels a été reconstruit et les 4 candidats confirmés re-run (verdicts
inchangés, DD légèrement plus honnêtes).
