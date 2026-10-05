> ⚖️ **STATUT (clarifié 2026-10-05)** : PROPOSITION scellée (tag `protocol-v2-ratified`, 02/10) mais **NON APPLIQUÉE** — le propriétaire a dit « pas pour l'instant », v1 reste la loi opérationnelle. La ratification explicite (décision du propriétaire) est un prérequis de toute comparaison inter-protocole — interdite en l'état.

# PROTOCOL_V2 — le walk-forward fenêtre par fenêtre

**STATUT : PROPOSITION — en attente de ratification user** (le protocole v1 reste
intouchable tant que la signature n'est pas posée ; la ratification se fait par un
tag git `protocol-v2-ratified` + la ligne ci-dessous décochée).

## Pourquoi (la leçon des 7 inventions + l'audit §33)

La moyenne masque les morts : une stratégie peut être « rentable en moyenne » et
mourir dans 2 fenêtres sur 6 — c'est exactement le profil des 7 inventions jugées
le 02/10 (train promet, val tue). La question qui vaut n'est pas « quel est le
meilleur résultat historique » mais « qui survit fenêtre par fenêtre ». La vision
user « rentable sur toutes les années » devient ici un CRITÈRE D'ACCEPTATION
mécanique, pas un espoir.

## Ce que v2 change (et ce qu'il ne change pas)

- **v1 reste la loi** pour les verdicts déjà gravés (docs/20, registry) — un
  protocole nouveau = un univers nouveau, aucune comparaison inter-protocole.
- **Les promotions futures exigent v2.** Une stratégie candidate doit passer
  ci-dessous AVANT la pipeline classique (OOS → coûts → régimes → forward).
- Les expériences en cours (INV-C) déclarent AU MOMENT DU GEL sous quel protocole
  elles seront jugées — jamais les deux.

## Les fenêtres (domaine Aster, data 1h ≈ 13 mois et croissante)

1. **6 fenêtres chronologiques de 2 mois**, découpage fixé à la ratification
   (proposition : 2025-09→11, →2026-01, →03, →05, →07, →09) puis les fenêtres
   futures s'ajoutent au fil du forward — le set est GELÉ, jamais ré-ajusté.
2. **Walk-forward strict** : pour chaque fenêtre W_i, tout calibrage (seuils,
   quantiles, fits) utilise uniquement les données < W_i ; W_i est un test.
3. **Un embargo de 72 h** entre train et test (anti-fuite de frontière).

## Les critères PASS par fenêtre (tous pré-déclarés par expérience)

1. Espérance nette de W_i > 0 aux coûts réels — **et** aux coûts ×1,5 (le stress
   coût de l'audit §27 ; l'edge qui meurt à 1,5× = fragile, refusé).
2. Aucune fenêtre sous le plancher pré-déclaré (par ex. > −15 % de la marge —
   la valeur se fixe dans le pré-enregistrement de chaque expérience).
3. **Minimum 5/6 fenêtres PASS** — la moyenne ne suffit jamais, le pire mois
   fait foi.
4. Dégradation train→test mesurée et rapportée fenêtre par fenêtre (le ratio
   test/train décline de plus de 70 % = refusé, même si tout passe).

## Les règles héritées (inchangées, rappel)

- Une expérience = une variable principale, critères écrits AVANT.
- Tout critère de régime = test **par état contre le base-rate** (leçon INV-H :
  le +16 pts d'un HMM « gagnant » était un artefact de prédicteur constant).
- MAGNITUDE ≠ DIRECTION (leçon OI vague 10) — toute séparation directionnelle
  détectée hors hypothèse = CONTEXTE.
- Priorités : ROBUSTESSE > OOS > coûts > régimes > risque > retour.
- 0-liquidation, coûts réels, le forward reste le juge final — v2 est un filtre
  AVANT le forward, il ne le remplace pas.

## Ce que v2 donne au user

Un candidat promu sous v2 a survécu à chaque tranche de marché disponible, aux
coûts stressés, sans masque de moyenne — c'est la version mécanique et honnête
de « rentable sur toutes les années ». Les fenêtres futures du forward complètent
le set chaque mois : une stratégie vivante doit continuer de passer, sinon elle
retire son statut (RETIRED, jamais effacée).
