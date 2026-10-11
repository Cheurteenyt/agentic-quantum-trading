# 38 — Gouvernance de la recherche (l'audit du 02/10/2026)

**Source** : « Rapport d'audit et plan de restructuration » fourni par le user le
02/10/2026. **Verdict adopté** : FREEZE → CENTRALISER → REFACTOR → ISOLER →
VALIDATE → RESEARCH AGAIN. Le projet ne grossit plus ; il devient plus strict.

**Amendements** : §« Gel de la CI » (11/10, audit Sonnet 5.5 §R3) — cf. plus bas.

## Ce qui est RATIFIÉ et en place dès aujourd'hui (P0)

1. **Le gel** : tag `freeze-2026-10-02`. Pendant la restructuration : pas de
   nouvelles stratégies classiques, pas de tuning de masse, pas de montée de
   levier, pas de modification de protocole, pas de moteur nouveau. Le gel
   opérationnel existait déjà (promotions gelées en régime T3, chapitres fermés) —
   il est maintenant formel.
2. **Le registre machine-readable** : `research/registry.yaml` (domaine Aster).
   Toute expérience nouvelle vérifie le registre AVANT de partir ; même hypothèse
   ou variante de seuil seule = PARAMETER_MUTATION (consomme le budget, ne repart
   jamais comme étude nouvelle). FOMO / X / OpenMarket = registres propres à leurs
   domaines.
3. **Le budget d'expériences** : `agent/policy.yaml` — 20 expériences/semaine
   (5/famille, 3/stratégie, 12 variantes de paramètres max), épuisement = STOP,
   1 changement de stratégie max, 0 modification de protocole, validation
   obligatoire après chaque changement. Appliqué par l'orchestrateur, pas par le
   prompt seul.
4. **La règle d'or** : UNE expérience = UNE hypothèse + UNE modification
   principale + protocole inchangé + critères PASS/FAIL écrits AVANT. Un FAIL se
   grave et s'arrête — il ne se « répare » pas.
5. **Le LLM hors du chemin critique live** : déjà vrai par doctrine (« AUCUN bot —
   le forward décide, l'utilisateur seul exécute »), maintenant écrit.

## Ce qui EXISTAIT déjà (l'audit le demande, le registre le prouve)

- La convention d'exécution unique (signal close t → entrée open t+1 → sortie au
  plan du signal, stop intrabar prioritaire) — le harnais et `aster_survivors_forward`.
- Le forward paper comme juge (verdicts datés : survivants 90 j, vol_spike ~30
  trades, derek518 à ≥ 5 CLOSED côté fomo).
- La culture du FAIL gravé (docs/20 : 22+ verdicts, nuls compris) — le §29 de
  l'audit est la doctrine du projet depuis le début.
- La priorité ROBUSTESSE > retour maximum (leçon +8 560 %/an irréproductible →
  mort ; le forward qui saigne −5 % est affiché tel quel).

## Ce qui est PLANIFIÉ (pas aujourd'hui — les verdicts en cours d'abord)

- **Phase 1** (single source of truth : 1 moteur de backtest, 1 moteur de coûts,
  1 moteur de liquidation, 1 moteur accounting, couche `exchange/aster/`) —
  construite EN PARALLÈLE, sans couper le prod : les forwards qui jugent
  actuellement (survivants 90 j, campagne v5, vol_spike) ne sont pas refactorés
  en cours de verdict, cela invaliderait leurs résultats.
- **Phases 2-3** (refactor the_machine en orchestrateur mince, paper_forward sans
  logique cachée) — après la Phase 1 et les verdicts, via PR reviewées comme
  d'habitude.
- **Le locked test formel** : le mécanisme est posé (test window pré-déclarée par
  expérience dans le registre, jamais réutilisée entre générations) ; le choix du
  DATASET verrouillé est une décision du user, à ratifier.
- **QUBO** : rétrogradé recherche-only (déjà le cas opérationnellement) ; la
  comparaison equal-weight / risk-parity / inverse-vol / QUBO sur stratégies
  identiques reste à faire avant toute promotion.

## La recherche Aster « nouvelle vague » (l'audit §61) vs le registre

L'audit demande : forced-flow, microstructure, crowding, régimes. L'état du
registre : la lignée microstructure-tape est CLOSE (T17/T18 NUL, T20 CONTEXTE),
la famille cascade est FERMÉE (15+ verdicts + chapitre mécanisme), la famille
funding-structure est FAIL. Restent GÉNUILEMENT ouverts et dans l'esprit de
l'audit : la classification JOinte continuation/absorption/exhaustion (price shock
+ OI shock + liq burst + flow — les tirs OI H4/H5 du 06-07/10 sont la première
tranche), et le composite crowding (fresh/crowded/late) — pré-enregistré AVANT
tout test, budget consommé, une variable à la fois.

## Gel de la CI (audit Sonnet 5.5, §R3 — 11/10)

**Le constat.** Sept commits consécutifs portent sur le même gate (`le filtre
core couvre enfin…` ×3, `ne peut plus se désactiver en silence`, `l'oracle était
fail-open`, `bandit fail-closed`). Ils réparent des défauts **de ma propre
conception en paliers** : un filtre de chemins qui doit énumérer *toutes* les
entrées de *tous* les oracles est fragile par nature, et chaque oubli est un faux
vert. La CI a absorbé la semaine au détriment de la recherche.

**Le gel.** À compter du **11/10/2026**, la CI est déclarée **terminée**. Tag
`freeze-ci-2026-10-11`. Pendant **2 semaines** (jusqu'au **25/10/2026**) :

- **tout commit `ci(...)` doit citer un incident RÉEL** — le `#NNN` qui le
  documente — et non décrire le correctif (« je répare la CI » n'est pas un
  incident). Un `ci(fix)` nu est précisément la signature d'un gate qu'on
  rafistole sans avoir nommé le trou ;
- les **seuls** correctifs CI admis sont ceux d'un incident **daté et nommé**
  (une étape qui n'a pas tourné, un oracle fail-open mesuré, un filtre qui
  laissait passer). Le filtre `core` n'est **plus** une raison suffisante : depuis
  #281→#289, plus rien d'obligatoire n'est filtré (`t1-cheap` porte les oracles
  bon marché **sans filtre**, `meta_ci.py` refuse un palier obligatoire `skipped`).

**Pourquoi une règle de revue et pas un gate bloquant de plus.** Un hook
`commit-msg` qui refuse un `ci(...)` mal formé finirait en `--no-verify` — c'est
la leçon F2 sous une autre forme (« un gate toujours rouge apprend à l'agent à
l'ignorer »). La règle est donc **vérifiable, pas contraignante** :
`scripts/audit_ci_commits.py` mesure la plage `freeze-ci-2026-10-11..HEAD` et
nomme le fautif s'il y en a un. **Mesuré le 11/10 : 15/15** commits `ci(...)` de
l'historique citent déjà un incident — la convention était *observée mais jamais
déclarée*. On la déclare et on la rend visible, on n'invente rien.

**Fin du gel.** Au **25/10/2026**, deux issues possibles, tranchées par la
mesure et non par l'habitude :

1. la CI n'a pas bougé pendant 2 semaines → le gel a tenu, on lève la règle (elle
   a rempli son rôle : rendre visible ce qui ne l'était pas) ;
2. un `ci(...)` sans incident est apparu → il est **examiné**, pas puni :
   soit le trou était réel et la règle a bien joué (il faut citer l'incident
   *a posteriori*), soit la règle est trop large et on la corrige.

⚠️ **Ce qui n'est PAS gelé** : la recherche (R1, holdout-x), les verdicts en
cours, la Phase 1 de restitution. Le gel porte sur **la porte**, pas sur ce
qu'elle laisse passer. La métrique qui juge le gel n'est pas « la CI est
immobile » mais **« la part de recherche remonte »** (§R3-5 : `% de PR de la
semaine qui exécutent ou pré-enregistrent une hypothèse`, objectif ≥ 50 %, à
afficher dans `research_velocity.py`).
