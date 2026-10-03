# LE TOURNOI DE CALIBRATION BONSAI — OCTOBRE 2026 (scellé le 03/10, AVANT tout verdict)

## Le protocole de scoring (écrit avant)
Chaque prédiction = {PREDICTION, confiance}. Scoring en novembre, après chaque verdict réel :
- hit si le verdict réel correspond à la prédiction (FAIL prédit FAIL, etc. ; KILL/FAIL fusionnés quand la prédiction est « la famille meurt »)
- calibration : moyenne des confiances sur les hits vs les misses ; un modèle utile a hits ≈ confiances
- l'enregistrement est SCELLÉ (ce fichier, commit 03/10) : toute édition post-verdict = triche

## Les 9 prédictions (verbatim Bonsai, no-think, 03/10)

```
1. LUN 05/10 — P5 (discriminateur premium-fade-listing) : **FAIL** (confiance 70 %).
Raison décisive : le pattern conditionnel état→prix (premium élevé + listing récent) s’effondre à la généralisation car le sous-ensemble « listings <90 j » est statistiquement fragile et non robuste aux variations de liquidité ; le Δindex ≤0,5 %/15m est un artefact de fenêtre trop courte, pas un signal de causalité.

2. LUN 05/10 — P1-P4 (WR 65/60 % + espérance >+2 bps net) : **KILL** (confiance 75 %).
Raison décisive : si P5 échoue, la famille premium-fade-listing est invalide ; même si P5 passait, l’espérance nette >+2 bps sous coûts 8-18 bps RT est mathématiquement impossible sans un WR >80 % ou une taille de position anormale.

3. 06-07/10 — re-tir MURS du carnet (ASk → −14,2 bps/30 min, WR 76 %) : **FAIL** (confiance 65 %).
Raison décisive : le pattern placement ASK est un événement discret mais son WR 76 % sur fenêtre complète est suspect ; la re-tir sur fenêtre complète expose souvent à la sur-estimation de l’edge (survival bias) ; −14,2 bps/30 min est trop faible pour compenser les coûts 8-18 bps RT après frais.

4. 06-07/10 — verdict DEPTH (gradient directionnel décile −1,88 % vs +0,88 %, net-coûts <14 j) : **FAIL** (confiance 70 %).
Raison décisive : le gradient directionnel est un pattern conditionnel état→prix (dépendance du décile de liquidité) qui s’effondre à la généralisation ; net-coûts sous 14 j est trop court pour stabiliser le signal ; l’écart −1,88 % vs +0,88 % est trop faible pour générer un edge net >0 après coûts 8-18 bps.

5. 07-08/10 — re-tir OI QUADRANT H4/H5 (OI↑×prix / OI↓×prix) : **INSUFFISANT** (confiance 55 %).
Raison décisive : n suffisant et direction conforme cette fois est un critère vague ; l’OI quadrant est un événement discret mais dépend de la corrélation OI/prix qui varie selon le régime de marché ; sans n>300 par quadrant, l’incertitude est trop haute.

6. 08/10 — WHALEFLOW (réplication swaps baleines, edge derek518 +8,4 %, n=161) : **FAIL** (confiance 60 %).
Raison décisive : le backfill des 1 400 mints expose souvent à la sélection post-hoc ; l’edge +8,4 % sur n=161 est statistiquement fragile (IC 95 % ≈ ±3,8 %) ; la réplication après backfill est rarement stable car les mints introduisent du bruit.

7. 28/10 — INV-N (torsion premium |Z|≥3, z 7 j) : **FAIL** (confiance 70 %).
Raison décisive : (a) demi-vie de reversion <2 h est improbable car la reversion des premiums prend souvent 4-12 h ; (b) impact prix 4-12 h > étalon 12,2 bps net est trop optimiste car les coûts 8-18 bps RT mangent l’edge.

8. 30/10 — H-CROWD-1 (composite crowding, stratification par flux) : **FAIL** (confiance 65 %).
Raison décisive : le composite crowding est un pattern conditionnel état→prix (dépendance de 5 variables) qui s’effondre à la généralisation ; la stratification par flux réduit l’n par sous-groupe ; sans WR>70 %, l’espérance nette est négative.

9. FIN OCT — QUBO joint poids×levier ([0.857/0.857/2.0/0.857]×[11x/1x/1x/1x]) : **INSUFFISANT** (confiance 50 %).
Raison décisive : FULL $5 182, DD 23,3 %, 0 liq est un résultat backtest sans coûts ; la confirmation réelle dépend de l’exécution humaine à l’open et de la règle 0-liq ; sans ledger réel, l’incertitude est trop haute.

A. Le verdict le plus surprise : **N° 6 (WHALEFLOW)**.
Sens : il pourrait **PASS** (confiance 35 %) car le backfill des 1 400 mints pourrait révéler un edge structurel (corrélation baleines/mints) que les 161 swaps initiaux masquaient ; c’est le seul pattern discret avec n>100 et edge>8 %.

B. Ce qui n’est pas dans cette liste :
- **Le coût d’exécution humaine à l’open** : c’est le premier facteur de dégradation de l’edge (slippage, latence, erreur de timing) ; sans mesure réelle du coût d’exécution, aucun backtest sans coûts est valide.
- **Le risque de régime (régime de marché)** :

```

## L'état d'esprit du modèle
7 FAIL/KILL, 2 INSUFFISANT, 0 PASS — uniformément baissier, cohérent avec son audit
« mort clinique » du 03/10 matin. Sa seule lueur : whaleflow (surprise prédite, 35 % de
chances de PASS). Premier point de calibration possible : lundi 05/10 (P5).
