# 41 — La méthode d'audit fiable (oracles en dépôt, boucle d'apprentissage)

Date : 2026-10-10 · HEAD d'origine : 7f0fcbd (649 commits) · Auteur : ronde 12

## Pourquoi ce document

Deux failles de méthode ont coûté cher avant cette ronde. Première faille :
la chasse aux bugs reposait sur des rondes manuelles — chaque bug (9 faux
succès, unités s/ms, fossiles de tests, contrat de données rompu, fail-open
de gate) a été trouvé à la main, corrigé à la main, et **rien** ne
redétecterait une réintroduction. Deuxième faille : la ronde 11 a attendu un
rapport d'audit externe (Sonnet 5.5) dont le contenu n'est jamais arrivé
dans le canal — le constat a dû être re-vérifié directement contre le code.
Une méthode qui dépend d'un rapport qui peut ne pas arriver, ou d'un humain
qui se souvient d'un motif, n'est pas une méthode.

La doctrine est donc : **l'audit vit dans le dépôt**. Chaque classe de bug
réellement rencontrée devient un détecteur AST déterministe, exécuté par la
CI à chaque push, rochété pour que la dette ne puisse plus croître. Le
rapport externe redevient un plus — pas une dépendance.

## Les trois couches

### Couche 1 — les oracles existants (inchangés)

| Oracle | Ce qu'il garantit | Mode |
|---|---|---|
| `audit_check.py` | les constats de l'audit du 2026-10-02 (A1-F5) restent corrigés | bloquant sur `--fail-on` |
| `audit_except_pass.py` | la dette `except: pass` (207) cesse de croître, fichier par fichier | rochet bloquant |
| pyflakes | aucun nom indéfini (B7) | bloquant |
| bandit / gitleaks / pip-audit | avis sécurité, secrets, CVE dépendances | rochets bloquants |
| `run_tests.py` + baseline | le compte de tests ne descend jamais ; la suite COMPLÈTE tourne chaque nuit (R1) | ratchet + cron 02:30 UTC |

### Couche 2 — `deep_audit.py` : les classes G (nouveauté ronde 12)

Chaque classe référence le bug fondateur qui l'a méritée. Une classe
n'entre dans le filet **que** prouvée par un bug réel — pas de spéculation.

| Code | Classe | Bug fondateur | Stock au 2026-10-10 |
|---|---|---|---|
| G1 | secondes/millisecondes mélangés dans une même expression ; variable `*_ms` assignée en secondes | P0 ronde 10 : lentille OI lue en ms, fixture en s → confluence 3/3 inatteignable **en silence** | 0 |
| G2 | horodatage **récent** (fenêtre HEAD − 180 j → HEAD + 1 j) figé dans un test qui utilise l'heure courante | issue #235 : timestamps mai 2026 vs fenêtre glissante 30 j → 3 échecs fantômes | 243 |
| G3 | contrat `x_pressure` : DDL ≠ 9 colonnes, placeholders ≠ 9, unité `captured_at` non prouvée en secondes, colonnes consommées hors contrat | P0 ronde 10 : fixture ISO dans `captured_at` | 0 |
| G4 | `success: True` codé dur alors qu'une variable `result*` est en portée **et ignorée** par le payload | #249 : 9 handlers desktop rapportaient réussi des actions ratées (Timeout, isError MCP) | 53 |
| G5 | handler `except Exception` sans trace dans une fonction `verdict/gate/ratchet/enforce/require/must_*` | R5/#252 : rochet fail-open en CI | 0 |
| G8 | horodatage historique (2020-2025) figé — **info, jamais bloquant** | même famille que G2, fixtures de données passées | 34 |
| G9 | fichier `.py` non parsable | — (l'oracle pyflakes n'attrape que les noms) | 0 |

La fenêtre G2 est **glissante et déterministe par commit** (le HEAD du
checkout fait foi) : un fossile écrit ce mois-ci est chassé ; quand le
présent dépasse un horodatage figé, il bascule automatiquement de G8 (info)
vers G2 (bloquant au rochet). C'est exactement la trajectoire du bug #235,
qui a dormi puis a rougi sans que personne ne touche au fichier.

Rochet (mode `--check`, doctrine `audit_except_pass`) : le compte par
fichier et par classe ne doit pas augmenter ; une réduction est libre et
encouragée (`--reset` dans la PR qui réduit) ; la CI compare aussi au
baseline de `origin/main` pour qu'une PR ne puisse pas relever sa propre
référence. Référence committée : `.github/deep-audit-baseline.json`
(330 constats sur 14 fichiers au jour 0).

Suppression locale (décision explicite, visible en review) :
`# deep-audit:ignore[=G1,G4]` sur la ligne fautive ou juste au-dessus ;
`# deep-audit:ignore-file[=G2]` en tête de fichier. Le fichier de tests du
noyau (`tests/test_r12_deep_audit.py`) utilise ce marqueur car il **injecte**
volontairement les fossiles pour prouver la détection.

### Couche 3 — le protocole de merge scripté (`scripts/premerge_audit.sh`)

Le re-audit avant merge, exécuté manuellement depuis la ronde 10, devient un
script à gates : (1) fetch et capture de `origin/main` ; (2) CI verte sur le
head de la PR ; (3) `update-branch` puis CI verte sur l'état fusionné réel
(une PR verte sur une vieille base ne prouve rien — leçon des merges croisés
#243/#237) ; (4) re-vérification que `origin/main` n'a pas bougé ; (5) merge
squash épinglé sur le sha vérifié ; (6) vérification post-merge. Chaque gate
refuse d'avancer en cas d'échec. Le token passe par la variable d'environnement
`GH`, jamais en dur.

## La boucle d'apprentissage

    constat manuel (chasse, rapport externe, incident réel)
      → re-vérification CONTRE LE CODE (jamais cru sur parole)
      → PR : fix + test + mutation négative (le test doit échouer sans le fix)
      → si le motif est réintroduisible : nouvelle classe G dans deep_audit
        avec le bug fondateur en référence, mesurée, rochétée
      → le filet grandit d'un cran, définitivement.

Une correction sans filet est une correction qui se refermera. Une classe
sans bug fondateur est une spéculation qui produira du bruit. Les deux
extrêmes sont interdits.

## Commandes

    python3 scripts/deep_audit.py                  # scan + liste des constats
    python3 scripts/deep_audit.py --check          # gate CI : rochet (bloquant)
    python3 scripts/deep_audit.py --reset          # réécrit la référence (PR de réduction)
    python3 scripts/deep_audit.py --json out.json  # sortie machine diffable
    python3 scripts/run_tests.py deep_audit        # les 22 mutations négatives du noyau
    GH=<token> bash scripts/premerge_audit.sh 255  # protocole de merge complet
