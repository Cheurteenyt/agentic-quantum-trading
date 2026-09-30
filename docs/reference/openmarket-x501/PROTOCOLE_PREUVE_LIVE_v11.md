# OPÉRATION x501 — PROTOCOLE DE PREUVE LIVE v11 (90 jours, exécution maker)

## 1. Pourquoi ce protocole

La nuit v27 a falsifié les trois voies du « gate précis » en temporel strict
(règle funding z-score : train +31,4 → test −22,0 bps ; flush OI dédupliqué
24 h : +0,1 bps ; ML multivarié : AUC 0,4994 après correction du split). Le
seul levier NOUVEAU et positivement mesuré est l'**exécution maker** : fill
97,9 % à δ=2 bps (52 728 tentatives, fenêtre 1 h sur 708 j), avantage +4,1
bps/côté vs taker. Le Monte-Carlo officiel v20 (`scripts/x501_v20_results/
mc_v20.json`, 12 000 trajectoires, 4/4 audits verts, SANS haircut gate) chiffre
l'enjeu :

| Régime | bps/côté | Médiane 12 m | P(250 $) | P(50 100 $ @36 m) | Ruptures |
|---|---|---|---|---|---|
| Maker δ=2 central (fill 97,9 %) | 2,1 | **468 $** | 73,0 % | 21,3 % | 0 |
| Maker stress (fill 90 %) | 3,0 | 413 $ | 69,8 % | 16,4 % | 0 |
| Taker all-in (5,5 + 0,6) | 6,1 | **273 $** | 57,2 % | 5,8 % | 0 |

DD max strictement ≤ 25 % dans tous les régimes (max 25,0000 % par
construction du noyau). La preuve live doit donc démontrer **une seule chose
nouvelle** : que le fill-rate maker réel tient au-dessus du seuil qui fait
basculer le plan du régime 468 $ vers le régime 273 $ — pendant que le plan
de trading vit sa première fenêtre de 90 jours en capital réel.

## 2. Déploiement (zéro intervention manuelle)

| Composant | Rôle | Intervention |
|---|---|---|
| `Operation_x501_Signature_H4_MK.ks` | plan de trading, entrées LIMIT δ=2 (maker), fallback taker, coupe-circuits -8/-15/-25 % | 1 coller + 1 alerte par chart 4h |
| `Operation_x501_Signature_H1_MK.ks` | idem, TF H1 (tier Plus) | optionnel, fidélité max |
| `x501_observe_flow_H1.ks` + `x501_observe_cvd4_btc_H1.ks` | collecte v10/v14 (B9, B6') — inchangés | déjà déployés |
| `scripts/x501_plan_v20.py` (démon 4×/j) | gates G1-G6 + jalons J+30/J+60/J+90 + journal | crontab `0 3,9,15,21 * * *` |

Réglages maker figés pour le démarrage : `makerMode=true`,
`makerDeltaBps=2`, `makerTTL=2` barres (≈8 h en H4, ≈2 h en H1),
`fallbackTaker=true`. Toute modification de ces réglages est une DÉCISION de
jalon (§4), jamais un ajustement ad hoc en cours de fenêtre.

## 3. Ce que le démon mesure à chaque passe (4×/jour)

Le démon `x501_plan_v20.py` exécute la collecte v17 (reader + Bybit +
cross-validation) puis applique les gates figées :

- **G1** volumes reader minimums (trade_agg ≥ 24/symbole, lsr ≥ 12, tvbs ≥ 100) ;
- **G2** cross-validation : 0 FAIL depuis la passe précédente ;
- **G3** spread moyen ≤ 3 bps (au-delà → recalibration MC à la bande S2) ;
- **G4** fraîcheur : dernier point de chaque table < 6 h ;
- **G5** protocole : journal de preuve présent, ancre J+0 cohérente, jalons
  non échus sans rapport ;
- **G6** fill-rate maker (dès le premier rapport tester disponible) :
  `fill_maker = makerFeesPaid/(makerFeesPaid + takerFeesPaid × 2,0/5,5)`
  — approximation par frais unitaires (fee maker 2,0 bps vs taker 5,5 bps) ;
  cible ≥ 0,95 (le backtest dit 0,979).

Chaque passe écrit une ligne JSONL append-only
(`scripts/x501_v20_results/scheduler_journal.jsonl`) : verdict GO/NO-GO, les
gates en échec le cas échéant, le fill-rate quand il est disponible. Le code
retour du démon (0/1) permet un alerting passif par crontab.

## 4. Jalons et critères figés AVANT mesure

### J+30 — contrôle qualité (aucune conclusion d'edge)
- Journal de preuve ≥ 80 % des passes attendues (≈ 360) ;
- Premier relevé tester : fill-rate maker, nombre de trades fermés, DD max
  de la courbe réelle ;
- **Décision** : GO si G1-G6 passent en médiane et DD < 25 % ; sinon
  diagnostic et re-démarrage de la fenêtre (l'ancre J+0 est re-posée).

### J+60 — verdict exécution (le jalon qui décide du régime de coût)
| Fill-rate maker réel | Décision figée |
|---|---|
| ≥ 0,95 | GO — régime 468 $ confirmé, réglages inchangés |
| 0,90 – 0,95 | bascule `makerDeltaBps=5` (backtest : fill 95,8 %) |
| 0,80 – 0,90 | bascule δ=10 + `fallbackTaker=true` (le fallback est déjà le comportement par défaut) |
| < 0,80 | bascule `makerMode=false` — le plan vit en taker, le MC v20 tient (273 $, P(250) 57,2 %) : **rien n'est cassé, le régime de coût change, documenté** |

En parallèle : lecture des R-multiples réels fermés (cible informative :
n ≥ 30 trades, E[R] empirique vs 0,1797 certifié, mais AUCUNE conclusion de
falsification à ce stade — la puissance statistique n'y est pas).

### J+90 — verdict de preuve complet
1. **Exécution** : fill-rate maker sur les 90 jours (moyenne + 20 dernières
   passes). Le régime retenu au J+60 est celui qui porte la suite.
2. **Plan** : E[R] réel sur n ≥ 100 trades fermés. Si E[R] > 0,15 R avec
   PF ≥ 1,30 et écart 1re/2e moitié < 0,10 R → le pool P1 est confirmé live ;
   sinon le pool est marqué DÉGRADÉ et le MC est re-ancré sur l'E[R] réel
   (le moteur accepte n'importe quelle grille de R mesurée).
3. **DD** : max drawdown réel vs coupe-circuits. Toute excursion > 25 %
   (inatteignable par construction du kill-switch, sauf gap inter-barres)
   déclenche l'arrêt définitif et le rapport d'incident.
4. **Décision** : GO (poursuite 12 m + intégration des verdicts B9/B6' de la
   collecte v10), HOLD (60 j de densification), ou KILL (documenté avec
   chiffres — la falsification honnête fait partie du protocole).

## 5. Critère de promotion d'un signal — durci (figé)

Toute promotion d'un signal du statut DIAGNOSTIC vers le statut TRADÉ exige
le double verrou, mesuré sur données fraîches (jamais vues par la recherche) :

1. **AUC temporel ≥ 0,60** sur 60 jours de données fraîches, split
   chronologique strict (tri global par temps — la correction v27 est
   non négociable), jamais de split inter-symboles ;
2. **E[R] live > +0,15 R** sur n ≥ 100 signaux avec PF ≥ 1,30 et stabilité
   quinzaines (écart d'E[R] entre moitiés < 0,10 R) — grille v14 inchangée.

État actuel : jamais atteint (AUC 0,4994 sur 23 mois × 201 408 obs). Ce
critère est scellé : aucune exception « parce que la période est favorable ».

## 6. Ce qui est déjà acquis (rappels non re-testés)

- Pool P1 certifié : 469 trades, E[R] 0,1797, audit v13 16/16, rejeu marge
  bit-exact (v15) : 0 liquidation 5×–20×, MAE max 4,0 %, funding 0,5 % de
  l'edge (break-even ×196,7) ;
- Noyau MC : 12 000 trajectoires × 36 mois, DD_CAP 25 % strict, 0 rupture
  sur toutes les bandes de coûts S0→S3 et maker→taker (v17 ET v20) ;
- Allocation G4-C3 : médiane 12 m ×2,3 vs uniforme, dominante 2024/2025/2026 ;
- Collecte v10/v14 : chaîne d'ingestion 7/7 tests, jalons B9/B6' à J+60/J+90.

## 7. Budget et limites

- Capital : 100 $ initial, aucun ajout, aucun retrait avant J+90 ;
- Alertes plateforme : 1 tir/barre fermée par collecteur (marge ×10 documentée) ;
- Disque : < 10 Mo pour 90 jours de journaux démon + collecte ;
- Limites connues : le fill-rate backtest (97,9 %) vient de barres 1h sur
  12 symboles — le live H4 peut dévier (moins de barres de fill) ; c'est
  précisément l'objet du jalon J+60. Le kScript marque chaque fill
  (diamond bleu = maker, diamond rouge = fallback) pour un contrôle visuel
  sans outils externes.
