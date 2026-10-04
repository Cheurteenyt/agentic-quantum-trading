# W41 — LES TROIS CHANTIERS QUBO (pré-enregistrés le 05/10, avant tout run)

Le contexte : la famille premium-tilt est FERMÉE (v1 FAIL, v2-A FAIL, v2-B FAIL
pire — PR #87-88). La cellule 11x codifiée est MORTE sur la fenêtre récente
(1 liq VAL, SOL MAE 13,08 %, wallet -21,2 % AVANT la liq — la run saignait déjà).
Les trois chantiers ci-dessous sont pré-enregistrés avec leurs critères ; AUCUN
run avant lundi (W41). Budget W41 : 3 expériences consacrées.

## CHANTIER 1 — LE MONEY MANAGEMENT LIQ-TOLÉRANT (priorité n°1, Bonsai d'accord)

L'intuition du propriétaire : quelques liquidations absorbables ≠ mort, SI la
marge par trade est plafonnée. Design : la marge par trade ≤ k% du wallet
(grille k ∈ {1, 2, 4} %), le levier reste ≤ plafond 0-liq par flux, le nombre
de liqs toléré par fenêtre ∈ {1, 3}, mode défensif (levier ÷2) après la k-ième.
La règle « 1 liq = MORTE » reste la loi des cellules à marge pleine ; ce
chantier crée la famille « marge plafonnée » (un autre univers, comparaisons
vs la cellule morte en INFO seulement).
**PASS** : DD ≤ 25 % sur la fenêtre récente, le ROI/an ≥ la baseline 8x
(à définir au run), les liq ≤ k, le rebond post-liq manqué < 15 % du capital
perdu. **FAIL** : DD > 25 % ou le rebond manqué ≥ 15 % (la loi d'exécution).

## CHANTIER 2 — LE STRESS-TEST FUNDING (le risque plateforme, priorité n°2)

Les faits mesurés : les majors PAIENT +2,0 % cumulé sur la fenêtre (médian
+0,0117 %/event, tout long), le scénario cadence ×8 = +15,6 % — contre un
objectif ~20 %/an c'est structurel. LES 3 FLUX ALTS (meme 6 523, survivor
1 655, vol_spike 27 008 events) n'ont AUCUN funding_last : le JOIN au
funding_history (71 symboles, 2023→) se fait à l'étude. Scénarios : cadence
×8, rate ×2, cap supprimé.
**PASS** : le coût funding du scénario ×8 reste < 10 % du ROI brut par flux.
**FAIL** : ≥ 10 % → le flux reçoit un plafond de coût ou le hold se raccourcit.
Le monitor forward : le coût funding par flux chaque semaine, l'alerte à 5 %.

## CHANTIER 3 — LE TILT PAR-SYMBOLE SUR LES 3 FLUX ALTS (priorité n°3)

Le tilt que la famille fermée n'a jamais testé : le funding du SYMBOLE de
l'event (pas une médiane marché), les 3 flux alts. Design Bonsai :
T = funding_last / médiane-du-symbole (TRAIN), T > 1,5 → levier ÷2, le quorum
de fraîcheur (la stamp ≤ 48 h sinon pas de tilt).
**PASS** : le DD des flux alts -5 % sans perdre > 10 % de ROI. **FAIL** :
sinon — et la sur-réaction aux pics ponctuels est le danger nommé (le quorum
de fraîcheur + la médiane TRAIN la bornent).

## L'ordre d'exécution W41 : 1 → 2 → 3 (Bonsai : le MM est la première ligne
de défense ; le stress funding dimensionne ensuite ; le tilt affine en dernier).
