# 42 — Le miroir GitHub → GitLab (publication unidirectionnelle)

Date : 2026-10-15 · Auteur : portage depuis le dépôt Ariad · Statut : **amorçage**

## Pourquoi ce document

Ce dépôt n'existe que sur GitHub. Le miroir ajoute une **seconde copie
hébergée du code source**, mise à jour automatiquement à chaque fois que
`main` passe la CI. Ce n'est pas de la sauvegarde (un `git clone` suffit) :
c'est de la **continuité d'accès**. Un compte suspendu, une panne longue,
une politique de facturation qui change — et le code reste publié ailleurs,
avec son historique complet.

Le système est porté depuis le dépôt Ariad, où il tourne en production
depuis juillet 2026. Il n'a pas été réécrit : les deux scripts shell sont
repris **tels quels** (zéro valeur propre à Ariad), et seuls le workflow et
la documentation ont été adaptés.

## 1. La doctrine — unidirectionnelle, et ce n'est pas un détail

```
   push sur main
        │
        ▼
   CI GitHub (workflow « CI ») ──── échec ──▶  RIEN n'atteint GitLab
        │ succès
        ▼
   workflow_run (conclusion == success, event == push, branche == main)
        │
        ▼
   1. Valider l'identité de l'événement (l'API GitHub est re-interrogée)
   2. Checkout du vérificateur depuis un SHA FIGÉ
   3. Gate de signature du commit  ──── refus ──▶  RIEN n'est matérialisé
        │ accepté
        ▼
   4. Checkout de TARGET_SHA (données Git uniquement, aucun script exécuté)
   5. Matérialisation de la clé SSH
   6. Machine à états (dans le checkout FIGÉ)
   7. Nettoyage (toujours)
   8. Verdict final (toujours, dernier step, sort en 1 si FAILED)
```

**GitHub `main` est la seule source de vérité.** GitLab ne reçoit jamais un
commit qui n'a pas déjà passé la CI sur GitHub `main`. C'est la propriété
centrale, et tout le reste en découle.

Le système **inverse** a existé sur Ariad (GitLab canonique → GitHub
miroir). Il a été abandonné après un incident d'épuisement du quota de
runners partagés GitLab : la CI migrée côté GitLab consommait le quota au
point de bloquer les dépôts voisins, et la reprise a été longue parce que
le sens de vérité était ambigu pendant la migration. Le runbook d'Ariad est
explicite — *« The rollback must never put GitLab back as source of
truth »* — et ce document reprend la même interdiction.

### Les dix invariants

1. GitHub `main` est la seule source de vérité.
2. GitLab `main` ne reçoit que des commits déjà présents sur GitHub `main`.
3. Le miroir ne pousse **jamais** de branche de travail.
4. Le miroir ne crée **jamais** de merge request GitLab.
5. Le miroir ne force-pousse **jamais** (`--force`, `--force-with-lease`,
   `--mirror` sont interdits). *Un test le vérifie sur le source.*
6. Une divergence GitLab est un **incident à instruire**, jamais une
   réparation automatique. Le miroir échoue.
7. Aucun runner GitLab n'est requis.
8. Une CI GitHub rouge n'atteint **jamais** GitLab (le déclencheur
   `workflow_run` exige `conclusion == 'success'`).
9. Un run ancien ne **rollback** jamais GitLab. Si GitLab est déjà sur un
   sha plus récent et valide, le run ancien ne fait rien.
10. Les identifiants GitHub et GitLab sont **séparés**.

L'invariant 9 est le plus important en pratique, et c'est celui que les
tests vérifient le plus durement : il se produit à chaque fois qu'un run de
miroir est rejoué (`gh run rerun`) après qu'un run plus récent a déjà
avancé GitLab.

## 2. La machine à états

Le workflow compare trois sha : `TARGET_SHA` (le `main` validé par la CI),
`CURRENT_GITHUB_MAIN` (relu en direct) et `REMOTE_SHA` (GitLab `main`).

| État constaté | Résultat | Push |
|---|---|---|
| GitLab vide | `mirrored` | oui |
| GitLab = `TARGET_SHA` | `already-mirrored` | non, mais **re-vérifié** |
| GitLab est un ancêtre de `TARGET_SHA` | `mirrored` | oui (fast-forward) |
| GitLab est un descendant de `TARGET_SHA` | `newer-valid-mirror-present` | non |
| Divergence (commits GitLab hors GitHub) | `failed` / `DIVERGENCE` | non |
| Refus pre-receive | `failed` / `PROTECTED_BRANCH_REJECTED` | non |

Trois verdicts du workflow :

- **SUCCESS** — parité exacte, invariants de miroir tenus, signature valide,
  nettoyage réussi.
- **SUPERSEDED** — GitLab est déjà plus loin, et c'est valide. Ce **n'est
  pas un échec** : c'est la preuve que la course entre deux runs a été
  arbitrée correctement. Le run ancien n'a rien détruit.
- **FAILED** — tout le reste. Le job sort en 1.

Le verdict final est le **dernier** step et sort en 1 : un job qui ne
faithfully rapporterait pas l'état effectif serait un rapport muet.

## 3. La racine de confiance : pourquoi un SHA figé

Le gate de signature et la machine à états ne sont **pas** exécutés depuis
`main`, ni depuis `TARGET_SHA`. Ils sont chargés depuis un commit figé,
`TRUSTED_VERIFIER_SHA`.

La raison est circulaire et il faut la voir : `TARGET_SHA` est précisément
ce qui est en cours de vérification. Si le vérificateur venait de
`TARGET_SHA`, un commit malveillant fournirait son propre juge. Le sha figé
casse cette circularité — le juge vient d'un commit antérieur, déjà validé.

Corollaire : **le checkout de `TARGET_SHA` ne sert que de données Git.**
Aucun script qu'il contient n'est exécuté pendant que la clé GitLab est
matérialisée.

Rotation : publier un PR de mise à jour du runtime, le fusionner (squash),
vérifier que la CI et un miroir passent, **puis** mettre à jour le sha dans
un PR séparé — jamais dans le même.

## 4. Mise en place — la liste à cocher

Le miroir ne peut pas fonctionner avant que ces étapes soient faites. Elles
sont manuelles parce qu'elles touchent à des identifiants.

### 4.1 Côté GitLab

**Le projet doit être créé VIDE** — pas de README, pas de licence, pas de
`.gitignore`. Ce n'est pas une préférence de style : la machine à états
refuse un `main` GitLab qui n'est pas un ancêtre de `main` GitHub
(`scripts/ci/mirror-main-to-gitlab.sh`, contrôle de divergence). Un commit
initial créerait un historique sans aucun rapport avec celui de GitHub, et
le tout premier miroir sortirait en `DIVERGENCE`. L'échec serait correct —
mais il coûterait une reconstruction complète du projet pour rien.

```bash
# 0. Si le token glab est expiré (l'API rend alors 401 invalid_token)
glab auth login --hostname gitlab.com

# Le projet vit dans le GROUPE cheurteen1, pas sous l'utilisateur : sans
# `namespace_id`, `POST /projects` le crée dans `cheurteen/`, où le
# workflow ne regarde pas.
GID="$(glab api "namespaces?search=cheurteen1" \
  | jq -r '.[] | select(.kind=="group") | .id')"

# 1. Projet privé, SANS commit initial
glab api projects -X POST \
  -F name=agentic-quantum-trading \
  -F path=agentic-quantum-trading \
  -F namespace_id="$GID" \
  -F visibility=private \
  -F initialize_with_readme=false

# PID : l'ID NUMÉRIQUE, jamais le chemin encodé. La forme
# `projects/cheurteen1%2Fagentic-quantum-trading/…` rend par intermittence
# un 404 `{"error":"404 Not Found"}` — un format qui n'est même pas celui
# de GitLab — sur les POST comme sur les GET. L'ID, lui, répond toujours.
PID="$(glab api "groups/$GID/projects" \
  | jq -r '.[] | select(.path=="agentic-quantum-trading") | .id')"

# 2. Paire de clés DÉDIÉE, sans phrase secrète (la CI ne peut pas en saisir)
ssh-keygen -t ed25519 -f ~/.ssh/aqt-gitlab-mirror \
  -C "github-actions-aqt-mirror" -N ""

# 3. Deploy key avec droit d'écriture
glab api "$PID/deploy_keys" -X POST \
  -F title=github-actions-aqt-mirror \
  -F can_push=true \
  -F key="$(cat ~/.ssh/aqt-gitlab-mirror.pub)"

# 4. Autoriser cette deploy key sur main protégé (l'étape qui échoue le plus)
DID="$(glab api "$PID/deploy_keys" \
  | jq -r '.[] | select(.title=="github-actions-aqt-mirror") | .id')"
glab api "$PID/protected_branches" -X POST \
  -F name=main \
  -F "allowed_to_push=[{\"access_level\":40},{\"deploy_key_id\":$DID}]" \
  -F 'allowed_to_merge=[{"access_level":40}]'

# 5. L'empreinte de la clé CLIENT, pour l'environnement GitHub
ssh-keygen -lf ~/.ssh/aqt-gitlab-mirror.pub
```

Ces commandes ont été exécutées pour de vrai le 15/10/2026 : projet vide
(`empty_repo: true`, zéro branche), deploy key `can_push: true`, et règle
`main` listant `github-actions-aqt-mirror` **et** Maintainers, force push
désactivé.

L'étape 4 est **gratuite**, et la nuance mérite d'être écrite parce que la
documentation de l'API prête à confusion : la page *Protected branches* est
donnée en `Free, Premium, Ultimate`, et la section « Enable deploy key
access » n'y porte **aucun** badge payant — contrairement aux sections
« groupes », « utilisateurs nommés » et « Code Owners », qui portent chacune
le leur. Ce qui est payant, c'est d'autoriser des *groupes* ou des
*utilisateurs nommés* ; une *deploy key* ne l'est pas.

L'API, elle, annote `allowed_to_push` « Premium and Ultimate only » — cet
avertissement vise les formes `user_id`/`group_id` : le 15/10/2026, GitLab
a accepté `allowed_to_push` avec une deploy key, en Free. S'il refuse
malgré tout — version plus ancienne, autre offre — faire l'étape 4 à la
main : c'est le chemin qu'utilise le runbook d'Ariad, et il est éprouvé.

```
GitLab → agentic-quantum-trading → Settings → Repository → Branch rules
       → main → Allowed to push and merge → Edit
       → Maintainers + github-actions-aqt-mirror (deploy key) → Save changes
```

État attendu — celui d'Ariad en production :

```
Branch                    : main
Allowed to merge          : Maintainers
Allowed to push and merge : Maintainers + deploy key
Allowed to force push     : NON   (doit rester désactivé)
```

Le projet étant vide, cette règle existe **avant** `main` : la toute
première poussée du miroir est donc déjà autorisée, sans course entre la
création de la branche et son autorisation.

*Si l'étape 3 rend « key already exists »*, la clé est déjà enregistrée :
passer à l'étape 4.

### 4.2 Côté GitHub

Créer un environnement nommé exactement **`gitlab-passive-mirror`**,
restreint à la branche `main`, **sans reviewer requis** (sinon chaque miroir
attend un humain).

| Nom | Type | Valeur |
|---|---|---|
| `GITLAB_MIRROR_SSH_PRIVATE_KEY` | secret | la clé **privée** complète, format OpenSSH, sans phrase secrète |
| `GITLAB_REPOSITORY_SSH_URL` | variable | `git@gitlab.com:cheurteen1/agentic-quantum-trading.git` |
| `GITLAB_KNOWN_HOSTS` | variable | la ligne ci-dessous, telle quelle |
| `GITLAB_MIRROR_KEY_FINGERPRINT` | variable | `SHA256:...` de l'étape 5 de §4.1 |
| `GITLAB_ED25519_HOST_FINGERPRINT` | variable | `SHA256:eUXGGm1YGsMAS7vkcx6JOJdOGHPem5gQp4taiCfCLB8` |

**`GITLAB_KNOWN_HOSTS`** doit contenir le *contenu* de la ligne, jamais un
chemin : la variable n'est lue qu'en CI, où aucun fichier local n'existe.

```
gitlab.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAfuCHKVTjquxvt6CM6tdG4SLp1Btn/nOeHHE5UOzRdf
```

Le runtime force `StrictHostKeyChecking=yes` **et**
`HostKeyAlgorithms=ssh-ed25519` : cette seule ligne suffit, inutile de
coller les clés RSA ou ECDSA.

La valeur se revérifie à tout moment, en une commande — et c'est la même
source que celle utilisée pour la poser :

```bash
ssh-keyscan -t ed25519 gitlab.com
```

Vérifié le 15/10/2026 : la clé servie par GitLab.com est identique à celle
ci-dessus, donc l'empreinte `SHA256:eUXGG…` de la ligne suivante est la
bonne. Si GitLab fait tourner sa clé hôte, **c'est un diff visible** — et le
miroir échoue avec `Host key verification failed`, pas en silence.

`check_mirror_setup.py` **recalcule** l'empreinte depuis la clé au lieu de
comparer les deux variables entre elles. La nuance compte : deux variables
remplies de travers de la même façon se confirmeraient mutuellement, alors
qu'un recalcul ne peut pas confirmer une clé fausse.

Les commandes correspondantes. **L'ordre compte** : l'environnement est créé
d'abord *avec sa politique de branche*, parce que les appels suivants se
contentent d'y déposer secret et variables.

```bash
REPO=Cheurteenyt/agentic-quantum-trading
ENV=gitlab-passive-mirror

# 1. L'environnement, restreint à `main` par une politique de branche
#    explicite (et non « toutes les branches protégées »).
#    Le corps JSON est écrit en clair : les crochets de `--field` et
#    l'inférence de type sur les booléens prêtent à confusion, et une
#    politique mal posée ne se voit qu'au premier run.
gh api -X PUT "repos/$REPO/environments/$ENV" --input - <<'JSON'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
JSON

gh api -X POST "repos/$REPO/environments/$ENV/deployment-branch-policies" \
  -F name=main --jq '.name'

# 2. Le secret — la clé PRIVÉE, lue sur stdin. Jamais en argument : elle
#    resterait dans l'historique du shell.
gh secret set GITLAB_MIRROR_SSH_PRIVATE_KEY --env "$ENV" --repo "$REPO" \
  < ~/.ssh/aqt-gitlab-mirror

# 3. Les quatre variables
gh variable set GITLAB_REPOSITORY_SSH_URL --env "$ENV" --repo "$REPO" \
  --body "git@gitlab.com:cheurteen1/agentic-quantum-trading.git"

gh variable set GITLAB_KNOWN_HOSTS --env "$ENV" --repo "$REPO" \
  --body "gitlab.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAfuCHKVTjquxvt6CM6tdG4SLp1Btn/nOeHHE5UOzRdf"

gh variable set GITLAB_MIRROR_KEY_FINGERPRINT --env "$ENV" --repo "$REPO" \
  --body "$(ssh-keygen -lf ~/.ssh/aqt-gitlab-mirror.pub | awk '{print $2}')"

gh variable set GITLAB_ED25519_HOST_FINGERPRINT --env "$ENV" --repo "$REPO" \
  --body "SHA256:eUXGGm1YGsMAS7vkcx6JOJdOGHPem5gQp4taiCfCLB8"
```

Puis vérifier l'ensemble d'un coup :

```bash
python scripts/ci/check_mirror_setup.py
```

Il contrôle l'existence et la restriction de branche de l'environnement, la
présence du secret et des quatre variables, l'égalité **stricte** de l'URL
avec celle du workflow, et surtout : il **recalcule** l'empreinte de la clé
hôte épinglée au lieu de comparer les deux variables entre elles.

Une chose lui échappe, et il le dit : il ne parle qu'à l'API GitHub.
L'autorisation de la deploy key sur `main` protégé (§4.1, étape 4) sort
donc en `[MANUEL]` — « à vérifier à la main » — et jamais en `OK`. C'est
le point qui, mal fait, ne se manifeste qu'au premier push, sous la forme
d'un refus `pre-receive`.

### 4.3 Le pin de confiance

`TRUSTED_VERIFIER_SHA` vaut `5b79f6e7170f132f91e581a47d1378070c051eb2` :
le commit de fusion (squash) du PR #308, celui qui a introduit
`scripts/ci/` sur `main`. C'est lui, le juge — les scripts du miroir sont
exécutés depuis **ce** commit, jamais depuis `main`, jamais depuis
`TARGET_SHA`.

Un PR ne peut pas citer son propre commit de fusion : il n'existe pas
encore au moment où on l'écrit. D'où deux PR successifs — #308 pose les
scripts, celui-ci pose le pin. Entre les deux, le workflow échoue à
l'étape 1, et c'est correct (*fail-closed*) : l'échec ne portait que sur
lui.

Le sha a été vérifié **signé** (`verified: true`, `reason: valid`) avant
d'être écrit ici. La porte de signature refuse les commits non signés : un
pin non signé aurait rendu le miroir mort-né, et le diagnostic n'aurait
parlé que de signature.

Contrôle : `python scripts/ci/check_mirror_setup.py` refuse le pin
d'amorçage et vérifie la forme du sha. La signature du commit épinglé,
elle, est vérifiée par le workflow lui-même, à chaque exécution.

## 5. Écarts assumés depuis Ariad

**Le chemin `workflow_dispatch` a été retiré.** Ariad l'autorise parce que
son bot de fusion déclenche un CI *exact-SHA* et qu'un job nommé
« Exact main SHA preflight » garde ce déclenchement. Ce dépôt n'a ni l'un
ni l'autre : son workflow `CI` se déclenche à la main **sans** input
`expected_sha`. Conserver ce chemin aurait exigé d'inventer un contrôle
sans menace correspondante.

Conséquence pratique : un CI déclenché manuellement sur `main` produit un
miroir **sauté**, pas un miroir rouge. La reprise d'un miroir en échec
passe par `gh run rerun` sur le run de miroir lui-même — le payload
d'événement est conservé, donc la reprise ne dépend pas de
`workflow_dispatch`.

Ce choix est explicite dans l'en-tête du workflow, à l'endroit où un futur
lecteur le cherchera.

## 6. Incident de divergence

Si le miroir rapporte `DIVERGENCE` :

1. **Ne pas force-pousser sur GitLab.** Cela détruirait l'historique et
   effacerait la cause.
2. Inspecter la différence entre GitLab `main` et GitHub `main`.
3. Si GitLab porte des commits à conserver : les cherry-picker sur une
   branche GitHub, ouvrir un PR, fusionner normalement. Le miroir suivant
   fera avancer GitLab.
4. Si GitLab porte des commits parasites : avancer GitLab `main` vers un
   sha GitHub connu bon, par une action d'administration ponctuelle, et
   **documenter l'action**.
5. Si la divergence est inexpliquée : geler les deux dépôts et auditer.

## 7. Reprise manuelle (*break-glass*)

```bash
set -euo pipefail
KEY=~/.ssh/aqt-gitlab-mirror
URL=git@gitlab.com:cheurteen1/agentic-quantum-trading.git

GH_MAIN="$(git ls-remote https://github.com/Cheurteenyt/agentic-quantum-trading.git \
           refs/heads/main | awk '{print $1}')"
GL_MAIN="$(git ls-remote "$URL" refs/heads/main | awk '{print $1}')"

# Fast-forward eligible ?
git merge-base --is-ancestor "${GL_MAIN:-$GH_MAIN}" "$GH_MAIN"

GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" \
  git push --dry-run -o ci.no_pipeline "$URL" "$GH_MAIN:refs/heads/main"
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" \
  git push -o ci.no_pipeline "$URL" "$GH_MAIN:refs/heads/main"

git ls-remote "$URL" refs/heads/main   # doit valoir $GH_MAIN
```

**À ne jamais faire** : `--force`, `--mirror` ; pousser un sha qui n'a pas
passé la CI sur GitHub `main` ; pousser un sha qui n'est pas un ancêtre de
`main` (rollback) ; désactiver la protection de branche ; réactiver la CI
GitLab ; promouvoir GitLab canonique, même temporairement. Si l'un de ces
gestes semble nécessaire, s'arrêter et déclarer un incident.

## 8. Les trois clés à ne pas confondre

| Clé | Rôle | Où elle vit | Secrète ? |
|---|---|---|---|
| Deploy key GitLab (client) | le workflow s'authentifie auprès de GitLab | secret GitHub `GITLAB_MIRROR_SSH_PRIVATE_KEY` | **oui** |
| Clé hôte GitLab.com (serveur) | le client vérifie qu'il parle au vrai GitLab | variable `GITLAB_KNOWN_HOSTS` | non, publique |
| Clé de signature des commits GitHub | GitHub atteste la provenance d'un commit | chez GitHub | — |

La deuxième et la troisième sont **publiques**. Le piège documenté par
Ariad : « réparer » un échec de clé hôte en tournant la deploy key. Les deux
sont indépendantes et ne tournent pas au même rythme. Si GitLab tourne sa
clé hôte, le miroir échoue en `Host key verification failed` — c'est la
sécurité qui fonctionne, pas une panne.

Ne jamais désactiver `StrictHostKeyChecking`.

## 9. Ce qui est vérifié, et comment

Le portage inclut les tests d'exécution d'Ariad, réécrits en `unittest` :

| Fichier | Tests | Ce qu'il exerce |
|---|---|---|
| `tests/test_ci_mirror_runtime.py` | 23 | la machine à états contre de **vrais dépôts nus** |
| `tests/test_ci_signature_gate.py` | 41 | le gate de signature contre un **faux GitHub** (serveur HTTP local) |

Les scénarios ne lisent pas le source pour y chercher des chaînes : ils
exécutent le script et vérifient l'état du dépôt après coup. Un extrait :
dépôt vide → pousse ; en avance → **ne rollback pas** ; divergent → échoue
sans pousser ; 401 → **pas** de retry ; 500 → exactement 3 requêtes.

### Les mutations

Un test qui passe ne prouve rien tant qu'on n'a pas montré qu'il casse. Dix
mutations de sens ont été appliquées aux scripts, et **les dix ont été
détectées** :

| Mutation | Détectée par |
|---|---|
| M1 inverser la classification d'ascendance | `test_en_avance_mais_valide_ne_rollback_pas` |
| M2 désactiver la détection de divergence | `test_divergence_echoue_sans_pousser` |
| M3 retirer le garde-fou `GITHUB_ACTIONS` | `test_github_actions_desactive_les_hooks` |
| M4 désactiver l'émission des sorties | `test_chaque_cle_apparait_exactement_une_fois` |
| S1 ne plus comparer le sha retourné | `test_sha_different` |
| S2 ne plus nommer « non signé » | `test_non_signe` |
| S3 recopier `verified_at: null` | `test_non_signe` |
| S4 accepter une raison hors énumération | `test_raison_hors_enumeration` |
| S5 retenter un 401 | `test_401_et_404_ne_sont_pas_retentes` |
| S6 autoriser le mode test sous `GITHUB_ACTIONS` | `test_github_actions_desactive_le_mode_test` |

**S4 a survécu à sa première version.** Le test envoyait
`verified: true` avec une raison inconnue — mais le contrôle de cohérence
(« `verified=true` exige `reason=valid` ») refusait **avant**, donc le test
ne testait pas l'énumération qu'il prétendait couvrir. Seul
`verified: false` + raison inconnue isole ce contrôle. Le test a été
corrigé. C'est exactement le genre de faux positif silencieux que la
mutation révèle et que la lecture ne voit pas.

### Ce qui n'est PAS testé

- **Le workflow YAML lui-même** n'est pas exercé de bout en bout. Il est
  validé par `actionlint` (vérifié : exit 0), ce qui couvre la syntaxe et
  les expressions, pas la sémantique.
- **Le vrai GitLab** n'est jamais contacté par les tests. Ce qui est
  vérifié, c'est le comportement contre des dépôts nus locaux.
- **Le comportement de GitLab sur `main` protégé** ne peut être reproduit
  localement : c'est le rôle du refus `pre-receive` simulé, et de
  `GITLAB_MIRROR_KEY_FINGERPRINT` côté configuration.

## 10. Diagnostic

| Symptôme | Catégorie | Cause probable |
|---|---|---|
| `Host key verification failed` | `HOST_KEY_MISMATCH` | GitLab a tourné sa clé hôte, ou `GITLAB_KNOWN_HOSTS` est vide/fauché |
| `Permission denied (publickey)` | `SSH_PUBLICKEY_REJECTED` | mauvaise clé, ou clé absente du projet GitLab |
| `not allowed to push… protected branches` | `PROTECTED_BRANCH_REJECTED` | deploy key en écriture **non autorisée sur `main`** |
| `failed to update ref` / non-fast-forward | `NON_FAST_FORWARD` | GitLab a avancé ; c'est un cas normal, pas une panne |
| `DIVERGENCE` | `DIVERGENCE` | commits GitLab absents de GitHub → **incident** |
| Le job échoue à `not a valid 40-char hex SHA: 0` | config | `TRUSTED_VERIFIER_SHA` encore à l'amorçage |

## 11. Références

- `scripts/ci/mirror-main-to-gitlab.sh` — la machine à états (générique)
- `scripts/ci/verify-github-commit-signature.sh` — le gate (générique)
- `scripts/ci/check_mirror_setup.py` — le contrôle de configuration
- `.gitlab-ci.yml` — désactive explicitement toute CI GitLab
- Source : dépôt Ariad, `docs/operations/GITHUB_GITLAB_BRANCH_BRIDGE.md`
