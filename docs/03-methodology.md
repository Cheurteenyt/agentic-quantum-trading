---
title: Méthodologie — comment on évite de se mentir
status: living
owner: cheurteen
updated: 2026-10-06
---

# Méthodologie anti-faux-backtest

**Le doc le plus important du repo.** Il condense ce que la suite Aster legacy a
coûté à apprendre : plus de 4000 $ de pertes réelles, ~6700 lanes testées,
**0 promotion propre**.

> ⚖️ **AUTORITÉ DES GATES (mis à jour le 06/10)** : les critères de
> confirmation COURANTS sont ceux de `research/protocols/active.yaml`
> (protocol-v2 : ≥ 5/6 fenêtres gelées PASS, stress de coûts ×1,5, DD MTM
> par fenêtre ≤ 15 %, couverture funding, causalité v14
> signal=close(t) → entry=open(t+1) verrouillée par mutation test, forward
> 30 j à 5 gates). La table du §3 ci-dessous est le **LEGACY** — ses leçons
> restent valides, ses seuils ne jugent plus rien.

⚠️ **La leçon du 05/10 s'ajoute à ce doc** : le Research OS a produit 7
candidats « confirmés » en une journée — tous morts le soir quand le
mutation test a révélé que le signal regardait la bougie sur laquelle il
entrait (look-ahead d'une bougie). Un moteur sans causalité verrouillée
produit des candidats par construction, pas par découverte.

Sources : `reference/aster-working-map.md`,
`reference/core-equity-aster-research-archive.md`, `archive/` (rapports HTML).

---

## 1. Le verdict legacy, en chiffres

Ce que le pipeline Aster a réellement produit avant d'être arrêté :

- `promote = 0`, `reject = 5`, `watch = 2`
- PnL paper cumulé : **−5,37 USD** baseline, **−3,67 USD** après filtre strict
- Win-rate strict : **0,409 (41 %)**
- MFE après frictions : **−9,88 %**, win-rate **0 %** sur Aster long seul
- Moteur RL sur **6768 lanes** → verdict `blocked_no_clean_promotions`

Retiens le dernier chiffre. **6768 configurations testées, zéro promotion
propre.** Ce n'est pas de la malchance : c'est ce qui arrive quand on cherche le
gagnant dans une grille au lieu de chercher un bord réel.

---

## 2. Les cinq mensonges qui ont coûté cher

### 2.1 Le biais long-only en régime extrême
Toutes les lanes étaient long-only stateful. Le marché 2025-26 bouge à la
seconde. Une exposition unidirectionnelle ne survit pas.
→ **Règle : toute stratégie doit pouvoir être long ET short.** Pas de biais
structurel de direction.

### 2.2 La période de backtest non représentative
Les backtests tournaient sur mai-juin 2026, une fenêtre calme. Les ROI affichés
(LAB ~48 %) sont des artefacts de régime.
→ **Règle : train/validation OOS strict sur données FRAÎCHES**, et la fenêtre de
test doit contenir au moins un régime de stress.

### 2.3 Les coûts sous-estimés
Le coût réel d'une perp, ce n'est pas le fee. C'est :
```
fees (maker/taker réels)
+ funding sur le NOTIONNEL (pas sur la marge)
+ slippage (fonction de la taille vs profondeur du carnet)
+ risque de liquidation
```
Les vieux ROI ignoraient le funding sur notionnel avec levier.
→ **Règle : un backtest sans ces quatre postes n'est pas un backtest.**

### 2.4 Le PnL latent mélangé au PnL réalisé
Les rapports additionnaient positions fermées et positions ouvertes. Une lane
"rentable" était souvent une lane qui portait une perte non matérialisée.
→ **Règle : PnL réalisé et PnL latent toujours séparés, jamais sommés.**

### 2.5 L'identité de lane cassée — le bug structurel
`truth_match_scope = identity_missing` sur **toutes** les lanes. Le pipeline de
vérité ne rattachait pas les résultats aux bonnes configurations (une lane 5h
comparée à une lane 30m). Toute la couche d'évaluation mesurait du bruit.
→ **Règle : contrat d'identité de lane obligatoire.** Une lane est définie par :
```
symbol + interval + side + trigger + execution_model + leverage
```
Deux résultats ne se comparent que si ces six champs sont identiques. Un
résultat sans identité complète est jeté, pas rattrapé.

---

## 3. Les gates LEGACY — critères de rejet automatique (historique)

> ⚠️ Ces seuils ont été remplacés par protocol-v2 (active.yaml) le 05/10.
> La table reste pour l'histoire et pour l'esprit : « un seul échec = rejet,
> pas d'exception ».

Une stratégie qui échoue à **un seul** de ces tests est rejetée. Pas de
discussion, pas d'exception « mais celle-là est spéciale ».

| Gate | Seuil de rejet |
|---|---|
| Nombre de trades | < 100 en OOS |
| Sharpe OOS | < 0,8 |
| Drawdown max | > 25 % |
| Dégradation OOS/IS | ratio < 0,6 |
| Stabilité des paramètres | perf s'effondre si un param bouge de ±10 % |
| Microstructure | fillabilité non validée |
| Coûts | un des quatre postes du §2.3 manquant |

La dégradation OOS/IS est le gate le plus discriminant : une stratégie qui fait
Sharpe 2,5 en train et 0,9 en test est **overfittée**, pas bonne.

---

## 4. Les benchmarks — battre quoi, exactement

Une stratégie ne se juge jamais dans l'absolu. Elle doit battre les trois, en
OOS, coûts inclus :

1. **Buy & hold** sur le même actif, même période.
2. **Entrées aléatoires** à fréquence et durée de détention identiques
   (n ≥ 1000 tirages, on compare à la distribution — pas à la moyenne).
3. **Momentum simple** (ex. croisement de moyennes), la baseline naïve.

Le benchmark random est le plus important : il répond à « est-ce que ce résultat
est distinguable du hasard ? ». Si la stratégie tombe dans le corps de la
distribution aléatoire, il n'y a pas de bord.

---

## 5. Le cycle de vie d'une stratégie

```
idée
  → backtest strict (coûts complets + identité de lane)
  → gates §3            ← rejet automatique ici, sans appel
  → benchmarks §4       ← doit battre les trois
  → validation microstructure (fillabilité réelle)
  → forward paper       ← durée minimale imposée, pas de raccourci
  → discussion réel     ← une DISCUSSION, pas une promotion automatique
```

Aucune étape ne se saute. Le legacy a sauté « validation microstructure » et
« forward paper de durée suffisante ». Les rares `PROMOTE` n'étaient que du
forward paper jamais validé en conditions réelles.

---

## 6. Ce qu'on garde du legacy

Trois choses ont de la valeur résiduelle :

1. **Le dataset** — ~442 Mo de CSV de backtests paper, archivés dans
   `backend/services/onchain/aster/archive/research_artifacts/legacy_discovery_batches/`.
   Utile comme jeu de test négatif : un nouveau moteur doit retrouver que ces
   lanes sont mauvaises. **C'est un test de régression du moteur lui-même.**
2. **Les validateurs** — `ws_symbol_quality`, `mark_index`, `microstructure`.
   Ils sont bons, on les réutilise tels quels.
3. **Cette méthodologie.**

Le code de stratégie legacy, lui, ne se réutilise pas.

---

## 7. Automatisation : le piège

L'objectif est de faire tourner les backtests en continu, la nuit. Le danger est
évident : **automatiser la génération de résultats sans automatiser leur
réfutation, c'est produire 500 mensonges par nuit au lieu d'un.**

Donc, dans l'ordre de construction :

1. Les gates et les benchmarks **d'abord**.
2. Le moteur de backtest ensuite.
3. L'orchestration en dernier.

Et une règle de sortie : **le rapport automatique ne remonte que ce qui passe
les gates.** S'il n'y a rien, il ne dit rien. Un rapport qui liste 400
candidats est un rapport que personne ne lit.
