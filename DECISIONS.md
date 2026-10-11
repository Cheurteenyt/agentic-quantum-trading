# DECISIONS.md — les décisions ⚖ du propriétaire (datées, critères écrits AVANT)

> Convention (docs/39 §7) : les décisions ⚖ appartiennent au propriétaire.
> Ce fichier les rend TRAÇABLE : une décision = un critère de succès écrit
> AVANT l'exécution + une date de verdict. Le propriétaire a délégué la
> rédaction à l'agent (11/10) ; chaque entrée reste ratifiable (amendment
> daté ci-dessous, jamais une réécriture).

## D-1 · Le programme maker est une STRATÉGIE À PART (décision du 11/10)

**Contexte** : bloquée depuis le 04/10 (rapport audit-repo §R4-P1). Le
holdout-x FAIL (11/10 : l'edge v8 ne sépare pas du bruit sur 48 symboles
jamais vus, champion apparié même profil) **renforce** la lecture du
rapport : le maker n'est PAS un moyen de repêcher les specs de découverte
directionnelles — c'est une stratégie distincte qui CAPTE le spread.

**Décision** : option (a) du rapport — **pilote maker 7 jours** sur ~10
memes, collecteur existant, en SIMULATION (le collecteur tape existe ; le
prize maker 12-24 bps meme attend l'extension du collecteur tape — placé
en prérequis du pilote, pas en blocage de la décision).

**Critère de succès (écrit le 11/10, AVANT le pilote)** :
- ≥ 5 000 fills simulés sur ≥ 10 jours ;
- revenu net par fill ≥ 2 bps ;
- borne basse IC95 (bootstrap blocs-jours) > 0.
**Échec** si l'un manque → option (b) abandon du maker, effort réaffecté
au portage delta-neutre (funding couvert ~99,9 %).

**Prérequis daté** : vérifier le barème maker/taker d'Aster (inconnu du
rapport §4) AVANT le premier jour du pilote — un barème maker ≥ 2 bps
rendrait le critère inaccessible ex ante.

**Verdict du pilote** : ~19/10 (7 jours après le début effectif).

## D-2 · La règle de kill de la ligne directionnelle Aster (ARMÉE le 11/10)

**La règle (écrite le 11/10, avant les verdicts qui la déclenchent)** :
si `holdout-x` ET les 3 hypothèses à mécanisme (`liq-echo`, `depth-imbalance`,
`long-flush-bounce`) échouent → **GEL** de la recherche directionnelle sur
barres 1h Aster (base de réussite ≈ 0) et réaffectation de l'effort au
maker (D-1) et au portage delta-neutre.

**État au 11/10** : holdout-x **FAIL** (1/4). Les 3 autres sont datées :
`liq-echo` jugé à n ≥ 30 (~mi-nov), `depth-imbalance` et `long-flush-bounce`
selon leurs échéances forward. Le gel ne peut être déclenché qu'au 4e FAIL.

**Ce que le gel interdirait** : tout nouveau backtest directionnel 1h Aster
pré-enregistré ; les specs déjà forward continuent leur course (un gel ne
retire jamais un verdict daté).

## Historique des décisions antérieures (référencées, pas re-décidées)

- D3 protocol_v2 (docs/39) : PROPOSITION — ratification par tag
  `protocol-v2-ratified` (décision propriétaire, pas encore posée).
- D4 Holdout (docs/39) : « le pool v8 est brûlé sur ses 40 symboles » —
  le holdout-x FAIL du 11/10 apporte la preuve empirique (le champion
  apparié montre le même profil) ; la déclaration formelle reste au
  propriétaire.
- D8 Cible ×501 : mesurée inatteignable (MC v31 P = 0,00 %) — inchangée.
