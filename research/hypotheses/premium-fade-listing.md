# HYPOTHÈSE PRÉ-ENREGISTRÉE — premium-fade-listing (armée lun 05/10, budget réouvert)

**Pré-enregistrée le 03/10** (budget épuisé 24/20 — ce fichier ne consomme RIEN, il fige
les critères AVANT le backtest). Source des critères discriminateurs : simulation
adversariale Bonsai 03/10 (le desk d'arbitrage de listings), PAS dérivée de nos données.

## L'hypothèse

Sur Aster, le fade du premium perp-vs-index sur les listings **< 90 jours d'âge** capture
un déséquilibre de liquidité structurel (l'unwind des teneurs de marché de listing), pas
une compensation de flux toxique. Preuve d'appui (audit 03/10, TRAIN-only par la loi) :
+8,5 bps (2025) et +8,8 bps net (2026), n = 77 569, WR ~58 %, cohérent sur 2 années.

## La config (gelée, identique à la cellule universe de l'audit)

- Data : premium_15m, W=96 barres (24h), |z| ≥ 2, H=4 barres (1h), entrée premium_open[t+1],
  sortie premium_close[t+H], non-overlap, coûts 8 bps RT, split temporel 70/30.
- Univers : trades dont le symbole a **< 90 j** au ts d'entrée (première barre premium = proxy listing).
- Gradient d'âge PRÉ-DÉCLARÉ en 3 bandes : [0-7 j] [7-30 j] [30-90 j] — le verdict se lit
  par bande, AUCUNE optimisation du seuil 90 j (il vient de l'audit = données déjà vues).

## Le discriminateur adversarial (le cœur du pré-enregistrement)

Δindex_15m de la bougie signal = Δperp_15m − Δpremium_15m (dérivé, l'indexPriceKlines = 400).

- **Trade VALIDE** si |z| ≥ 2 ET |Δindex_15m| ≤ 0,5 % (le premium s'emballe SANS le prix
  = déséquilibre de liquidité, l'edge listing).
- **Trade TOXIQUE** si |z| ≥ 2 ET |Δindex_15m| > 0,5 % (le premium suit un pump = on est
  l'éponge de la volatilité, le salaire du flux toxique).
- **KILL ex ante** : si > 15 % des trades listing violent le filtre (flux toxique dominant
  dans la famille), la famille est morte SANS backtest conditionnel — interdit de « réparer »
  par le filtre après coup (le filtre fait partie de l'hypothèse, pas un patch).

## Data prep requise avant le run (dimanche, hors budget)

Backfill klines 15m backward pour les symboles < 90 j de l'univers premium_15m
(historiques courts = quelques minutes). Sans eux, Δperp_15m n'existe pas (19 syms seulement).

## Critères PASS/FAIL (écrits avant toute mesure)

- P1 WR VAL ≥ 55 % (les listings sont bruités, la barre 60 % du claim d'audit est TRAIN-only)
- P2 espérance nette VAL > +2 bps/trade (au-dessus de la marge d'exécution humaine)
- P3 contrôle inverse (chase) strictement pire en VAL
- P4 gradient d'âge monotone : esp(0-7 j) ≥ esp(7-30 j) ≥ esp(30-90 j) — la datation EST le mécanisme
- P5 le discriminateur : ≥ 85 % des trades valides (sinon KILL avant P1-P4)
- P6 BLOC STATS mensuel : ≥ 60 % de mois positifs VAL, DD et record reportés
- Échec de P2 ou P5 → la famille premium-fade-listing meurt au registre, sans appel.

## Le miroir Bonsai (le piège à surveiller pendant le run)

La coupure < 90 j a été trouvée en DÉCOMPOSANT les données qui ont produit le +8,8 —
le risque = sur-interprétation causale d'un artefact de sélection. Seuls garde-fous :
le split temporel (VAL jamais vue pour la décision), la réplication 2025/2026 (déjà faite),
et le discriminateur théorique (seuils venant de la théorie adversariale, pas de nos données).

## Red-team de l'évaluateur (03/10 soir, Bonsai — vérifié par l'agent, AVANT tout run)

L'évaluateur `scripts/studies/premium_fade_listing_test.py` (smoke OK sur synthétique) a été
attaqué avant exécution. Résultats vérifiés : (1) unités premium = fractions décimales
(BTC 0,000889 = 8,9 bps) — la conversion ×10⁴ est juste ; (2) alignement premium↔perp aux
open_time identiques : 10 000/10 000 sur BTC (reindex + skip des NaN, les manquants sont
comptés non-évaluables) ; (3) non-overlap PAR symbole (le `last` reset dans le groupby) ;
(4) âge négatif impossible par construction (les ts sont des barres premium du même symbole).
L'amendement Δindex EXACT (index = perp/(1+prem)) est confirmé par le red-team : erreur du
premier ordre ≈ 0,017 % aux magnitudes extrêmes — négligeable vs le seuil 0,5 %, le premier
ordre reste en colonne de sensibilité. Aucun bug réel trouvé. L'évaluateur est verrouillé ;
toute modification APRÈS le run de lundi = interdite.

## LE VERDICT (04/10 — le run réel, gate GO sous la comptabilité v2 16/20)

**KILL (P5) — la famille premium-fade-listing est MORTE au registre.**

| Critère | Résultat | Verdict |
|---|---|---|
| **P5 discriminateur** | **22,2 % de toxiques** (seuil 15 %) — concordant premier ordre/exact (22,2/22,2) | **FAIL → KILL** |
| P1 WR train/val | 4,9 % (n=708) / 55,2 % (n=62 162) | FAIL |
| P2 espérance VAL | +4,61 bps | pass |
| P3 contrôle inverse | −20,61 vs +4,61 | pass |
| P4 gradient d'âge | 0-7j +9,4 → 7-30j +6,0 → 30-90j +3,8 (monotone) | pass |
| P6 mois positifs | 62 % | pass |

n = 80 770 trades listing <90 j (un crash de plomberie — colonne `period` créée après usage — a interrompu la PREMIERE exécution AVANT tout verdict ; fixé et tracé ici, les critères n'ont pas bougé d'un iota).

**La lecture honnête** : le mécanisme directionnel existe (P3/P4 passent — le fade bat le chase et se date) MAIS plus d'1 signal sur 5 est un pump suivi (Δindex > 0,5 %) — la ligne ex ante était 15 %. **Interdit de « réparer » par le filtre après coup** : la règle était écrite avant, elle tue. Le gradient P4 et l'espérance P2 sont gravés comme CONTEXTE pour une éventuelle réouverture si un discriminateur THÉORIQUE plus fin émerge un jour — pas aujourd'hui.

**Calibration Bonsai** : P5 FAIL prédit à 70 % = **HIT** (1er point du tournoi, 1/1).

Docs/20 : inscription immédiate. Ledger : FAIL 29e essai, 17/20 W40.
