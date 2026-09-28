---
title: Moteur de backtest v2 — gates, coûts, walk-forward, moteur
status: archived (28/09 — l'ère pré-refonte, voir docs/README.md)
owner: cheurteen
updated: 2026-08-09
---

# Moteur de backtest v2

> Ce module n'implémente **aucune stratégie**. Il implémente les garde-fous qui
> manquaient au legacy, et qui ont coûté plus de 4000 $.

Traduction exécutable de `03-methodology.md` (les règles) et `06-data.md`
(les 6 règles data).

## Structure

```
backend/services/backtest_v2/
├── __init__.py      SCHEMA_VERSION
├── gates.py         les juges  : motifs de rejet + 3 benchmarks
├── costs.py         les 4 postes de coût
├── walkforward.py   split OOS glissant + sensibilité paramétrique
├── baselines.py     buy & hold / momentum / aléatoire
├── store.py         le schéma : les 6 règles data câblées en SQL
├── engine.py        la boucle qui teste et QUI ÉCRIT TOUT
└── multiplicity.py  juge la CAMPAGNE : Bonferroni, FDR, Deflated Sharpe
```

**Stdlib pure.** Ni pandas, ni numpy, ni pytest (`pip install` est interdit sur
ce projet). Ce n'est pas une contrainte subie : le composant critique ne peut
pas casser à cause d'un upgrade de lib.

## Lancer

```bash
python scripts/run_tests.py backtest_v2   # 194 tests, ~5 s
python scripts/refresh_aster_cache.py --check
```

## Le principe

**`None` ne veut pas dire zéro, il veut dire non mesuré — donc rejet.**

Le legacy traitait un funding absent comme un funding nul. C'est comme ça qu'un
coût disparaît d'un backtest. Ici, une métrique non mesurée est un rejet, jamais
un pass par défaut.

## L'ordre d'écriture (délibéré)

Les juges ont été écrits **avant** le moteur. Un moteur qui produit des
résultats avant que les gates existent produit des mensonges — c'est
littéralement ce qui s'est passé.

## `gates.py` — les juges

Chaque motif de rejet correspond à une erreur mesurée sur le corpus legacy.
Les plus discriminants : `sample_too_small` (< 100 trades),
`overfit_oos_is_ratio` (< 0,6), `costs_incomplete`, `identity_incomplete`.

Un Sharpe astronomique n'est jamais un bon résultat : c'est une division par du
bruit numérique. `sharpe()` renvoie `None` si la variance est à l'échelle du
flottant.

## `costs.py` — les 4 postes

| Poste | Défense |
|---|---|
| fees | maker/taker selon `execution_model` |
| funding | **refus si cache > 30 jours** |
| slippage | **lève si le carnet ne peut pas absorber l'ordre** |
| liquidation | lève si le levier est incompatible |

**Le funding s'applique au notionnel, pas à la marge.** Erreur du legacy : avec
levier 5, le vrai coût est **5× l'estimation erronée**. Un test verrouille ce
ratio.

**`execution_model` change le coût d'un facteur 8** sur USDT. C'est pour ça
qu'il fait partie de l'identité de lane.

**`funding_count = 0` n'est pas un funding nul.** Constaté au 2026-08-09 sur
BONK, FLOKI, MEME, SHIB : historique vide. Les traiter comme gratuits offrirait
un avantage fictif à exactement les paires les plus volatiles. `costs.py` les
refuse (`status='empty'`).

Un total partiel n'existe pas : `total_usd` reste `None` tant que les 4 postes
ne sont pas mesurés.

> Un total partiel est pire qu'une absence de total : il a l'air d'un chiffre,
> et il sous-estime systématiquement.

### Piège : le choix de `reference_price`

`slippage_usd()` mesure l'écart au prix de référence fourni :
- **best ask** → impact de marché seul, **le demi-spread disparaît**
- **mid** → impact + demi-spread

En cas de doute, passer le mid — sous-estimer un coût est l'erreur qui coûte.

## `walkforward.py` — le split OOS

Vérifié indépendamment sur 6 configurations (rolling/anchored × embargo
0/5/20) : aucun chevauchement train/test, embargo respecté, et **aucune barre
OOS comptée deux fois** (sinon on gonfle artificiellement l'échantillon).

`param_sensitivity()` perturbe chaque paramètre de ±10 % et renvoie la
dégradation relative maximale. Une stratégie qui s'effondre à ±10 % est un
artefact d'optimisation, pas un edge.

## `baselines.py` — les 3 benchmarks

Buy & hold, momentum, et **aléatoire à même fréquence et même durée de
détention**. Tous **nets de coûts** : comparer une stratégie nette à un
benchmark brut est un mensonge qui favorise la stratégie.

**Zéro look-ahead** : signal sur barre `i` → exécution à l'open de `i+1`.
Vérifié en mutant la dernière barre à 1000 — aucune décision antérieure ne
bouge.

Le benchmark aléatoire est le plus important : il répond à « ce résultat est-il
distinguable du hasard ? ». Sur le legacy, des lanes affichaient 70 % de
win-rate sur 19 trades — indistinguable du bruit.

## `engine.py` — la boucle

**C'est ici que le biais de survivance est rendu impossible.**

`run_campaign()` appelle `store.record()` sur **chaque** combinaison évaluée.
Le rejet n'est pas une exception dans le flux : c'est le flux normal.

- une combinaison qui plante est comptée en erreur, la campagne continue
  (une campagne nocturne ne meurt pas sur un cas limite) — mais l'erreur reste
  visible dans le rapport
- l'ordre de la grille est déterministe (clés triées) : deux campagnes
  identiques produisent le même rapport
- les benchmarks (1000 tirages) ne tournent que sur les lanes ayant passé les
  gates — inutile de benchmarker une lane à 19 trades
- le compteur mémoire est réconcilié avec le store en fin de campagne ; toute
  divergence est signalée comme bug de persistance
- `format_report()` ne remonte que les survivants, **toujours avec le
  dénominateur**

Le détail des trades des benchmarks n'est pas archivé : il est reproductible à
partir du seed. L'archiver serait du volume mort — l'erreur exacte des 442 Mo
de CSV legacy.

## Le test de régression legacy

Le moteur rejoue les 17 092 lanes du dataset legacy :

```
sharpe_oos_too_low            17092  (100.0 %)
drawdown_too_deep             17092  (100.0 %)
overfit_oos_is_ratio          17092  (100.0 %)
param_instability             17092  (100.0 %)
costs_incomplete              17092  (100.0 %)
microstructure_unvalidated    17092  (100.0 %)
sample_too_small              17019  ( 99.6 %)
identity_incomplete           11905  ( 69.7 %)
SURVIVANTS                        0
```

Le legacy annonçait **+924 828 USD**. Le moteur en garde **zéro**.

> Si ce test repasse à > 0 un jour, ce n'est pas une bonne nouvelle :
> c'est que quelqu'un a affaibli les gates.

## Le taux d'acceptation est un signal d'alarme

Campagne de démonstration sur **du bruit gaussien pur** (aucun edge réel),
24 combinaisons :

```
testées   : 24
acceptées : 2      ← 8,3 %
rejetées  : 22
```

Les 2 « survivants » avaient 400 trades et un Sharpe OOS de 1,0 — **sur du bruit
pur, par construction**. C'est le rappel le plus important du projet :

> Les gates réduisent le bruit, ils ne l'éliminent pas. Sur un grand nombre de
> combinaisons, des faux positifs survivent **mécaniquement**.

8,3 % ici, 9,43 % pour le legacy. Le même ordre de grandeur, et la même cause :
tester beaucoup finit toujours par produire des gagnants apparents.

**Conséquence opérationnelle** : un survivant de campagne n'est pas une
stratégie validée, c'est un **candidat**. La validation exige une période
hors-échantillon *postérieure à la campagne* — des données que personne n'avait
au moment du test. C'est le rôle de `runner.py` (à venir) : conserver les
candidats et les réévaluer sur les données arrivées depuis.

## `multiplicity.py` — juger la campagne, pas la lane

**Le module le plus important après les gates.** Il répond au constat
ci-dessus : les gates jugent chaque lane isolément, ce qui est nécessaire mais
insuffisant.

> Le p-value d'une lane n'a aucun sens si on ne dit pas combien de lanes ont
> été testées pour la trouver.

Un Sharpe de 1,0 est remarquable sur un test unique. Sur 10 000 tests, c'est
l'attendu du hasard.

| Outil | Contrôle | Usage |
|---|---|---|
| `bonferroni` | FWER — proba d'**au moins un** faux positif | **passage en live** |
| `benjamini_hochberg` | FDR — **proportion** de faux positifs | exploration |
| `deflated_sharpe_ratio` | le Sharpe corrigé du nombre d'essais | arbitrage final |

Stdlib pure : `norm_ppf` est implémenté via l'algorithme d'Acklam (précision
~1e-9), pas de scipy.

### Le point critique : quel dénominateur

`n_tested` doit être le **nombre total de combinaisons testées**, pas le nombre
de survivants des gates. Une lane rejetée a quand même consommé un essai.

> Corriger sur les survivants plutôt que sur les essais revient à ignorer tous
> les tickets perdants — le biais exact qui a produit « +924 828 USD ».

Un test verrouille ça : la même p-value de 1e-4 survit sur 1 essai, meurt sur
10 000.

### Démonstration à l'échelle industrielle

10 000 combinaisons sur du **bruit gaussien pur**, aucun edge :

```
lanes avec Sharpe OOS > 1,0   : 1231      ← le hasard, rien d'autre
meilleur Sharpe observé       : 3,10
après correction Bonferroni   : 0
Deflated Sharpe du meilleur   : 0,398     (seuil 0,95)
VERDICT : AUCUN SURVIVANT APRÈS CORRECTION
```

**1231 « stratégies gagnantes » avec un Sharpe supérieur à 1, dont une à 3,10 —
et pas un seul signal réel.** Sans cette couche, une campagne nocturne
produirait ces 1231 lanes comme des découvertes.

C'est précisément ce que le legacy a fait à sa propre échelle.

### Contre-épreuve

Le module n'est pas un rejeteur aveugle : un test vérifie qu'un **vrai edge
fort survit** à la correction sur 100 essais. S'il rejetait tout, il serait
inutilisable.

## Reste à faire

- `runner.py` — orchestration nocturne : campagne → audit de multiplicité →
  conservation des candidats → **réévaluation sur données postérieures** →
  rapport Discord
- registre de candidats : un candidat n'est promu qu'après avoir survécu à une
  période OOS que personne n'avait au moment de la campagne

