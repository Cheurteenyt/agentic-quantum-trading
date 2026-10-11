#!/usr/bin/env python3
"""R3-bis (audit Sonnet 5.5) — le test de MÉTA-CI.

## Pourquoi ce script existe

Le gate se neutralise de quatre façons, toutes fermées une par une entre #277 et #288 :
déclenchement (filtre de chemins), verdict (un `else` qui n'échoue pas), oracle-grep
(outil absent ⇒ sortie vide ⇒ vert), non-exécution (un bloquant en T2 jamais déclenché).

Chaque trou a été fermé par un correctif + un verrou DÉRIVÉ de la source
(`tests/test_ci_filtre_core.py`). Le rapport Sonnet 5.5 §R3 dit, à raison, que ce
correctif-par-trou est **fragile par nature** : « un filtre `core` qui doit énumérer
toutes les entrées de tous les oracles est fragile, et chaque oubli est un faux vert ».
Il demande donc **un seul test de méta-CI** : « chaque palier déclaré s'est exécuté sur
le dernier run ».

C'est ce test. Il ne regarde pas la DÉFINITION des paliers (ça, les verrous le font
déjà) — il regarde le **RÉSULTAT DU RUN**. Un palier qui devait tourner et qui sort
`skipped` est un palier qui a DISPARU en silence, même si sa définition est correcte.

## Le seul cas qui est un défaut, et pourquoi c'est le bon

Tous les paliers ne doivent PAS tourner à chaque événement :

  - `t1-core` / `t1-security` / `t1-frontend` : filtrés par chemins. Une PR docs-only
    les fait légitimement passer `skipped`. C'est leur fonction.
  - `t2-full` / `t3-night` : merge queue inactive / nocturne. `skipped` est la norme.
  - `changes` : absent sur `schedule` seulement.

Ce qui ne doit JAMAIS être `skipped` sur un `pull_request` ou un `push` :
`t1-cheap` et `gate`. Ces deux-là sont **sans filtre de chemins** et **sans condition
d'événement** (hors schedule). S'ils sautent, ce n'est pas un filtre qui a parlé —
c'est qu'on leur en a ajouté un, exactement le défaut que le rapport décrit. Un
`t1-cheap` `skipped` sur une PR = les oracles bon marché n'ont pas tourné et personne
ne l'a dit.

## Pourquoi pas l'API GitHub

La tentation est d'interroger `actions/runs/<id>/jobs`. C'est inutile ici et fragile :
le job `gate` a déjà TOUT ce qu'il faut dans `needs.<palier>.result`. On lit donc les
variables d'environnement, pas le réseau — pas de token, pas de rate-limit, pas de
latence, et le verdict porte sur le run COURANT par construction.

## Usage

    META_CI_EVENT=pull_request \
    META_CI_JOBS=t1-cheap=success,gate=success \
    python3 scripts/meta_ci.py

Sortie 0 = chaque palier obligatoire a bien tourné. Sortie 1 = au moins un a disparu,
et le script NOMME le palier. `--list` affiche ce qui est obligatoire.
"""

from __future__ import annotations

import os
import sys

# --- Ce qui est obligatoire, et pourquoi (la seule liste du dépôt) ----------------------
#
# Un palier est OBLIGATOIRE sur un événement donné si sa définition ne dépend NI d'un
# filtre de chemins NI d'une exclusion de cet événement. Autrement dit : quand on
# déclenche la CI sur cet événement, ce palier DOIT tourner — sinon il a disparu.
#
# ⚠️ « Obligatoire » dépend de l'ÉVÉNEMENT, et c'est un piège réel (mesuré en écrivant
# ce script) : `t1-cheap` a `if: github.event_name == 'pull_request' || == 'push'`.
# Sur `merge_group` il saute LÉGITIMEMENT. Le déclarer obligatoire partout aurait
# produit un faux rouge sur merge_group — or un gate qui rougit pour une mauvaise
# raison apprend à être ignoré (c'est la leçon F2 du dépôt : « un gate toujours rouge
# apprend à l'agent à l'ignorer »). La version naïve de ce script avait ce bug ; il est
# fermé ici et verrouillé par un test.
#
# La liste ci-dessous est DÉRIVÉE du workflow par `tests/test_meta_ci.py` : un nouveau
# palier non filtré devient obligatoire par construction, sans qu'on y pense.
OBLIGATOIRES = {
    "pull_request": ("changes", "t1-cheap", "gate"),
    "push": ("changes", "t1-cheap", "gate"),
    "merge_group": ("gate",),          # t1-cheap ne tourne PAS sur merge_group
    "workflow_dispatch": ("gate",),    # idem, seul T2 se déclenche
}

# Événements où la CI n'est pas un gate de PR : `schedule` ne lance que T3.
EVENEMENTS_HORS_GATE = ("schedule",)


def paliers_requis(event: str) -> tuple[str, ...]:
    """Les paliers qui DOIVENT avoir tourné pour cet événement."""
    if event in EVENEMENTS_HORS_GATE:
        return ()
    return OBLIGATOIRES.get(event, ())


def parse_jobs(brut: str) -> dict[str, str]:
    """`"t1-cheap=success,gate=skipped"` -> {palier: resultat}."""
    out: dict[str, str] = {}
    for item in brut.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"entrée illisible : {item!r} (attendu palier=résultat)")
        nom, res = item.split("=", 1)
        out[nom.strip()] = res.strip()
    return out


def disparus(event: str, jobs: dict[str, str]) -> list[tuple[str, str]]:
    """Les paliers obligatoires qui n'ont PAS tourné. Retourne [(palier, motif)]."""
    out: list[tuple[str, str]] = []
    for nom in paliers_requis(event):
        res = jobs.get(nom)
        if res is None:
            out.append((nom, "absent du run"))
        elif res == "skipped":
            out.append((nom, "skipped — le palier a disparu en silence"))
        # success / failure : le palier A tourné. `failure` est déjà un échec du
        # run, le gate n'a pas besoin de le re-signaler ici.
    return out


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for ev, paliers in OBLIGATOIRES.items():
            print(f"{ev}: {', '.join(paliers) if paliers else '(aucun)'}")
        return 0

    event = os.environ.get("META_CI_EVENT", "pull_request")
    brut = os.environ.get("META_CI_JOBS", "")
    try:
        jobs = parse_jobs(brut)
    except ValueError as e:
        print(f"::error::META-CI illisible — {e}")
        return 1

    requis = paliers_requis(event)
    if not requis:
        print(f"META-CI : événement {event!r} — aucun palier obligatoire (pas un gate de PR)")
        return 0

    absents = disparus(event, jobs)
    if absents:
        for nom, motif in absents:
            print(f"::error::META-CI : le palier obligatoire « {nom} » n'a pas tourné — {motif}")
        print(f"META-CI : {len(absents)}/{len(requis)} palier(s) obligatoire(s) disparu(s) "
              f"— le gate se serait cru vert sans avoir mesuré")
        return 1

    vus = ", ".join(f"{n}={jobs.get(n, '?')}" for n in requis)
    print(f"META-CI : tous les paliers obligatoires ont tourné ({vus})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
