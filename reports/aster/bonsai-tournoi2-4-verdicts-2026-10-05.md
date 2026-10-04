# TOURNOI 2 — les 4 verdicts de la semaine (scellé le 05/10, scoring ≤ jeudi)

## Les prédictions (verbatim Bonsai)
```
PREDICTION (1) PASS + 65 % ; la divergence HIT/PULL (27 bp) est un signal de micro-structure cohérente, mais le −14,2 bp sur 30 min reste vulnérable à la dérive du spread sur ~2 semaines de depth sans ajustement du gate garde-fou.

PREDICTION (2) FAIL + 70 % ; le gradient directionnel (38,8 % vs 55,3 % WR) survit historiquement, mais sous la fenêtre < 14 j et net-coûts, le décile bas de profondeur (-1,88 %) ne compense pas les frais de transaction et la latence, rendant le signal statistiquement insignifiant.

PREDICTION (3) PASS + 80 % ; avec n>3 et la direction conforme H4 confirmée par les cascades récentes, le re-tir OI QUADRANT H4/H5 atteint le seuil minimal de robustesse pour valider la détection des chasses aux stops.

PREDICTION (4) PASS + 75 % ; le backfill des 1 400 mints couvre 98 % des achats historiques non trackés, et l'edge +8,4 % (t=2,65) sur 2 233 events reste significatif, avec derek518 (n=161, edge +38 %) comme preuve de skill reproductible.

(A) WHALEFLOW, le design :
- Coupe 1 : Backtest sur une fenêtre temporelle disjointe (ex: 2020-2022) avec critère de kill si l'edge tombe sous +5 % (p-value > 0,05).
- Coupe 2 : Sensibilité aux frais de transaction (ex: +0,1 % par trade) avec critère de kill si le DD dépasse 8 % (vs 6,4 % historique).
- Coupe 3 : Validation sur un sous-ensemble de mints récents (ex: 100 derniers) avec critère de kill si le WR des baleines (n>=161) chute sous 60 %.
Si le FAIL vient : seule mesure complémentaire = re-tir sur une fenêtre de 6 mois avec n>=2000 events et ajustement du seuil de filtre (âge >=7 j -> >=10 j) pour éliminer les mints à maturité proche.

(B) LE MIROIR : La semaine a montré que le projet est en phase de calibration, où la mort des cellules et des claims est un signal de maturité, et la chose à ne PAS faire maintenant est d'augmenter la complexité des modèles sans d'abord stabiliser la base de données et les métriques de performance.

```

## Les traps capturés au scellement (à retenir au scoring)
1. **L'inversion du 98 %** : Bonsai monte whaleflow de 35 % (tournoi 1) à 75 % en lisant
   « 98 % des achats étaient sur des mints NON trackés » comme « le backfill couvre 98 % » —
   c'est L'INVERSE (les 98 % étaient le problème ; la couverture du backfill reste à prouver).
2. **La coupe 1 cite « 2020-2022 »** — la whale tape n'existe pas avant 2026 : fabrication.
3. **Le garde-fou de maturité vérifié le 05/10** : whale_flow = span 8 j (≥ 6,5 ✓),
   7 jours de snapshots (≥ 7 ✓), 1 006 snapshots × 789 tickers — le test de jeudi tournera,
   mais sur une fenêtre JEUNE : l'edge réclamé (+8,4 %, t=2,65, n=2 233) vient du lineage swaps,
   pas de ce join 8 j. Le verdict réel sera probablement plus modeste que les deux lueurs.

## Le scorecard cumulé
Tournoi 1 (9 prédictions, scoring novembre) · listing P5 : HIT (1/1) · pick de tri 32-cellules :
contredit par le registre (0/1) · Tournoi 2 : 4 prédictions scellées ce soir, scoring ≤ jeudi.