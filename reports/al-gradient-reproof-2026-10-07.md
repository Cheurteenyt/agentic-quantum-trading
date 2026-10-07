# RE-PREUVE DU GRADIENT AL SCORE (formule conforme PR-172) — 07/10/2026

**Déclencheur** : PR-172 (bdd48fa) a corrigé la direction du rang RISK_DOWN
(`mean(vals <= -v)` → `mean(vals >= v)`) — l'ancienne formule rendait
`cascade_depth` MORTE (rang saturé à 1.0 sur 100 % des events : la valeur
courante était niée, pas la fenêtre). Le gradient validé du 24/09
(WR 53,7 → 64,3 %) ayant été MESURÉ sous le score buggy, la convention
quant-discipline exige la re-preuve avant adoption. C'est fait ci-dessous.

**Méthode** (reproductible) :
```python
from scripts.anti_liq import collect_featured, add_rolling_scores
from scripts.portfolio_sim import btc_regime_series
evs = collect_featured(btc_regime_series(), 'majors')
add_rolling_scores(evs)          # score CORRIGÉ
# split temporel 70/30, terciles du score, liq-rate + WR short par tercile
```
Données : 1105 events majors scorés (1168 collectés, 63 en warm-up NaN),
snapshot klines.db du 07/10 matin (après purge PR-170 des barres partielles).

## Résultats

| Split | Tercile | n | liq % | WR_short % | ret_short moyen |
|---|---|---|---|---|---|
| TRAIN | T1 (bas) | 258 | **11,2 %** | **52,3 %** | −0,140 % |
| TRAIN | T2 | 257 | 19,5 % | 46,7 % | −0,260 % |
| TRAIN | T3 (haut) | 258 | **26,7 %** | **45,0 %** | −0,109 % |
| VAL | T1 (bas) | 111 | **4,5 %** | 44,1 % | −0,118 % |
| VAL | T2 | 111 | 7,2 % | **51,4 %** | **+0,369 %** |
| VAL | T3 (haut) | 110 | **15,5 %** | 43,6 % | −0,081 % |

## Lecture

1. **Le score corrigé fait son travail anti-liq** : gradient de liq-rate
   MONOTONE croissant avec le score — 11,2→26,7 % en train, 4,5→15,5 %
   en validation (×3,4 T1→T3 en val). La direction « haut = risqué » est
   confirmée SUR LA FORMULE CONFORME.
2. **Le gate de la machine sélectionne l'autre bout** : `the_machine` garde
   `al_score >= q66` = le tercile T3 = 26,7 %/15,5 % de liqs — le côté le
   PLUS liq-prone. Sous le score corrigé, le gradient de WR est
   DÉCROISSANT en train (52,3→45,0) : l'ancien gradient croissant
   (53,7→64,3 %) n'est PAS reproductible.
3. **Nuance** : les rets courts moyens par tercile sont proches
   (train : −0,140 / −0,260 / −0,109) — les liqs écrasent la queue mais
   l'espérance brute par event ne tranche pas seule ; le sizing
   vol-inverse + le levier asservi changent l'équation au niveau wallet.
4. Cohérent avec le verdict du 04/10 (commit 4cfa246) : « le gate AL score
   est INVERSÉ dans le régime récent — son tercile haut perd −16$ quand le
   mid gagne +14$ » — la re-preuve montre que l'inversion n'est pas
   seulement un artefact de régime : elle est structurelle à la formule
   conforme.

## Décision requise (au propriétaire)

Le sens du gate de la machine (`>= q66` vs `<= q33`) est une décision de
recherche, pas un fix mécanique :
- **(a) inverser le gate** (garder T1 = le côté anti-liq) → à juger par la
  machine complète (wallet run_stack, DISCOVERY train-only d'abord) ;
- **(b) conserver le gate** et documenter que la machine sélectionne
  délibérément le tercile volatil (l'anti-liq passe alors par le levier
  asservi MAE, pas par le gate) ;
- **(c) scinder** : gate T1 pour le flux 10x, T3 conservé pour un flux
  séparé — nouvelle famille, pré-enregistrement requis.

En attendant la décision, la re-sync d'al_score_v2 (copie machine) est
suspendue : elle dépend du sens choisi.
