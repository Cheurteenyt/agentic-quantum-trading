---
name: quant-discipline
description: La doctrine expérimentale du projet (backtests, verdicts, promotion d'une stratégie). Utiliser dès qu'on teste un indicateur, un filtre ou une stratégie sur Aster ou fomo, qu'on veut « backtester », « valider », « améliorer la frontière », ou avant de promouvoir quoi que ce soit au forward — même si l'utilisateur propose juste une idée de signal.
---

# La doctrine quant (le pipeline obligatoire)

## Le chemin d'une idée

1. **One-shot** dans `scripts/studies/` (jamais à la racine — la racine = les
   briques permanentes, voir `scripts/README.md`).
2. **Baseline anti-dérive + horizons muraux exacts** — mesurer contre le
   harnais v5 (`backtest_indicators.py`), jamais contre une ré-implémentation
   approximative (les proxies ont menti : fdiv et confluence « mortes » en
   sim séquentiel étaient un artefact d'unité).
3. **Train/val TEMPOREL** (jamais aléatoire) + contrôle inverse (inverser le
   signal doit être pire — sinon c'est un artefact).
4. **Le test du wallet séquentiel** : tout candidat doit survivre au
   premier-arrivé sur le wallet partagé (`stacked_portfolio.run_stack`).
   Les backtests horizon-fixe positifs qui meurent en séquentiel = le cas
   courant, pas l'exception.
5. **BLOC STATS mensuel obligatoire** dans tout verdict (mois positifs/négatifs, DD, record).
6. **Verdict dans `docs/20-registre-indicateurs.md`** : NUL / CONTEXTE / CANDIDAT / VALIDÉ.
7. **Archivage** : étude close → `git mv scripts/archive_studies/` avec
   l'en-tête `# ARCHIVÉ (date)` — on ne supprime jamais, on re-catégorise.

## Les lois gravées

- **Tout chiffre non reproductible par le code committé = mort**, même gravé
  en mémoire (+8 560 %/an irréproductible → mort le jour même).
- Les verdicts **RELATIFS** survivent aux bugs d'unité, les **ABSOLUS** non —
  re-mesurer après tout fix d'échelle (le champ ts_ms en nanosecondes).
- **Les limites sélectionnent à l'envers** : les gagnants tombent
  immédiatement (loi d'exécution), open = optimum entrée+sortie.
- **Amplifier un edge VALIDÉ** plutôt qu'en tester un nouveau similaire
  (derek → vitesse, bonding → âge, fade → structure). La décorrélation
  (corr < 0,3 au wallet) vaut un edge en plus.
- **WR et ROI = deux colonnes JAMAIS fusionnées.**
- La cible user : 60-70 %/mois **stables**, gros WR, DD contrôlé.
- **La règle 0-liquidation** : `lev ≤ 100/(maxMAE + 0,5)`. MAE par flux :
  majors 7,66 % → plafond 12x ; vol_spike 94 % → 1x ; le survivor (LONG 1x)
  est inliquidable par construction.
- Le gate ATR p90 du survivor : ne JAMAIS l'assouplir (3 trades = 278 % de
  la contribution — la tail porte tout).
- **Le forward décide** : AUCUN bot — l'utilisateur seul exécute ;
  promotion gelée tant que le régime décroissant dure (la courbe T3).
- Les résultats viennent du forward et des carnets de tir datés
  (docs/20) — le mining sur data existante est FERMÉ.
