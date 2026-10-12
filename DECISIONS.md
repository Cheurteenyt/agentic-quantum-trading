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

**Prérequis VÉRIFIÉ le 12/10** — source officielle
(`docs.asterdex.com/trading/perpetuals/fees-and-specs/fees`, relevée le
12/10/2026 ; corroborée par `docs/reference/aster-official-docs-gap-audit.md`,
qui citait déjà la même URL le 31/05) :

| Catégorie | Maker | Taker |
|---|---|---|
| Crypto — General | **0 bps** | 4 bps (0,04 %, modulé VIP) |
| Crypto — Group B | 0 bps | **10 bps** (0,1 %) |
| RWA | 0 bps | 1,25 bps (depuis 07/09/2026) |
| USD1 (BTC/ETH/SOL) | 0 bps | 4 bps |

- **Conséquence 1 — le critère est accessible** : maker = **0 bps sur TOUTES
  les catégories** (« All maker fees are 0 bps »). La crainte d'un barème
  maker ≥ 2 bps qui aurait rendu « ≥ 2 bps net/fill » inatteignable ex ante
  est **levée**. Le pilote peut démarrer sur ce plan.
- **Conséquence 2 — le repli taker n'est pas uniforme** : les non-fills
  paient 4 bps (General) à **10 bps** (Group B). Le pilote doit donc
  (a) choisir ses ~10 memes dans un **groupe connu** et (b) modéliser le
  **taux de fill**, sinon le coût du fallback est sous-estimé — c'est le
  « fill_status » que `docs/reference/aster-official-docs-gap-audit.md`
  (§1.a) déclare encore **non implémenté** (« les modes maker/BBO doivent
  être lus comme proxies de coût, pas comme preuve de fill »).
- ⚠️ `scripts/portfolio_sim.py` porte `MAKER_BPS = 2` (proxy conservateur
  antérieur) alors que l'officiel est **0** : le simulateur est *pessimiste*
  sur les frais maker, ce qui est du bon côté du biais (il ne fabrique pas
  un edge). À ne pas « corriger » vers 0 sans revoir le modèle de fill.

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
