#!/usr/bin/env python3
"""R3-③ (audit Sonnet 5.5) — un commit `ci(...)` doit citer un incident RÉEL.

## Pourquoi cet oracle

Le rapport §R3 note que 7 commits consécutifs ont porté sur le même gate, en
réparant « des défauts de ma propre conception en paliers ». Sa troisième
recommandation est une **règle de revue**, pas du code :

    « déclarer la CI terminée pour 2 semaines : tout nouveau commit `ci(...)`
      doit citer un incident réel »

Une règle de revue non écrite n'existe pas — c'est la leçon du chantier entier
(une spec qui AFFIRME un gel sans en avoir un, #288). Ici, la règle **est déjà
observée** : mesuré le 11/10, **12/12** commits `ci(...)` de l'historique citent
un `#NNN` et nomment un défaut concret. Elle n'était simplement jamais DÉCLARÉE
ni vérifiable.

Cet oracle la rend vérifiable. Il ne s'agit pas de punir : il s'agit qu'un
`ci(fix)` nu — « je répare la CI » sans dire quel incident — devienne
**détectable** au lieu de passer inaperçu.

## La règle, précise et étroite

Un sujet de commit qui commence par `ci(` doit contenir une référence `#NNN`
(le numéro de PR ou d'issue qui documente l'incident). C'est tout.
  - On N'EXIGE PAS une longueur minimale, un mot-clé, ou une forme de phrase :
    ce serait juger le style, et un oracle qui juge le style apprend à écrire
    pour l'oracle.
  - On n'exige RIEN des autres préfixes (`research`, `fix`, `docs`…) : les
    correctifs CI ont un coût collectif particulier (ils touchent la porte que
    tout le monde traverse), c'est ce qui justifie de les tracer.

## Pourquoi PAS un gate bloquant en permanence

⚠️ Ce serait le piège F2 (« un gate toujours rouge apprend à l'agent à
l'ignorer ») sous une autre forme : un hook `commit-msg` qui refuse tout commit
mal formé finit contourné (`--no-verify`), et la règle meurt.

La règle du rapport est **bornée dans le temps** (« pour 2 semaines »). L'oracle
l'est donc aussi : il ne BLOQUE que pendant la fenêtre de gel déclarée
(`GEL_DEBUT`..`GEL_FIN`). Après la fenêtre, un `ci(...)` nu ne fait plus rougir —
il émet une **notice** disant que le gel a expiré et qu'il faut le ratifier ou
le lever. Le gate reste donc VERT hors fenêtre : jamais rouge pour rien.

## Usage

    python3 scripts/audit_ci_commits.py                 # la branche vs origin/main
    python3 scripts/audit_ci_commits.py <revrange>      # ex. freeze-ci-..HEAD
    python3 scripts/audit_ci_commits.py --all           # tout l'historique
    python3 scripts/audit_ci_commits.py --list          # les commits ci(...) vus

Sortie 0 = chaque `ci(...)` cite un incident (ou bien le gel est expiré → notice).
Sortie 1 = au moins un `ci(...)` nu PENDANT le gel, et l'oracle le NOMME.
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
import sys

# ═══ Fenêtre de gel de la CI (docs/38 — audit Sonnet 5.5 §R3) ═══
# Déclarée le 11/10/2026 pour 2 semaines. AVANT : la règle n'existe pas.
# APRÈS : elle n'est plus bloquante (le gel a expiré) — on le dit, on ne rougit
# pas. Un gate qu'on oublie de lever est un gate qu'on apprend à ignorer (F2).
GEL_DEBUT = _dt.date(2026, 10, 11)
GEL_FIN = _dt.date(2026, 10, 25)

# Un sujet de commit `ci(...)` : `ci`, puis un scope parenthésé ou rien, puis `:` ou espace.
SUJET_CI = re.compile(r"^ci(?:\([^)]*\))?\s*[:\-—]?\s*(.*)$")
# La référence d'incident. `#123` est la forme utilisée par le dépôt (squash merge
# ajoute `(#NNN)`), mais on accepte aussi `GH-123` / `issue 123` par tolérance.
INCIDENT = re.compile(r"(#\d+|GH-\d+|\bissue\s+\d+|incident\s+\S)", re.I)


def est_commit_ci(sujet: str) -> bool:
    return sujet.startswith("ci(") or sujet.startswith("ci:")


def cite_un_incident(sujet: str) -> bool:
    """Le sujet porte-t-il une référence d'incident ?"""
    return bool(INCIDENT.search(sujet))


def commits(revrange: str) -> list[tuple[str, str]]:
    """[(sha_court, sujet)] pour la plage donnée."""
    out = subprocess.run(
        ["git", "log", "--format=%h%x00%s", revrange],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"git log a échoué sur {revrange!r} : {out.stderr.strip()}")
    lignes = []
    for ligne in out.stdout.splitlines():
        if "\x00" in ligne:
            h, s = ligne.split("\x00", 1)
            lignes.append((h, s))
    return lignes


def fautifs(revrange: str) -> list[tuple[str, str]]:
    """Les commits `ci(...)` qui NE citent PAS d'incident."""
    return [(h, s) for h, s in commits(revrange)
            if est_commit_ci(s) and not cite_un_incident(s)]


def tous_les_ci(revrange: str) -> list[tuple[str, str]]:
    return [(h, s) for h, s in commits(revrange) if est_commit_ci(s)]


def gel_actif(aujourd_hui: _dt.date | None = None) -> bool:
    """Le gel est-il en vigueur ? (état, pas intention — cf. #288)."""
    auj = aujourd_hui or _dt.date.today()
    return GEL_DEBUT <= auj <= GEL_FIN


def main(argv: list[str]) -> int:
    revrange = "origin/main..HEAD"
    for a in argv:
        if a == "--all":
            revrange = "HEAD"
        elif a == "--list":
            for h, s in tous_les_ci(revrange):
                print(f"{h} {s}")
            return 0
        elif not a.startswith("-"):
            revrange = a

    ci_vus = tous_les_ci(revrange)
    mauvais = fautifs(revrange)
    actif = gel_actif()

    if not ci_vus:
        print(f"CI-COMMITS : aucun commit `ci(...)` dans {revrange} — rien à vérifier")
        return 0

    if mauvais and actif:
        for h, s in mauvais:
            print(f"::error::CI-COMMITS : {h} — « {s[:70]} » ne cite aucun incident (#NNN)")
        print(f"CI-COMMITS : {len(mauvais)}/{len(ci_vus)} commit(s) `ci(...)` sans incident cité "
              f"— le gel CI est EN VIGUEUR jusqu'au {GEL_FIN.isoformat()} : nommer l'incident réel")
        return 1

    if mauvais and not actif:
        # Le gel a expiré : on SIGNALE, on ne bloque pas (F2).
        for h, s in mauvais:
            print(f"::notice::CI-COMMITS : {h} — « {s[:70]} » ne cite aucun incident (#NNN)")
        print(f"CI-COMMITS : {len(mauvais)}/{len(ci_vus)} commit(s) `ci(...)` sans incident cité — "
              f"gel EXPIRÉ (fin {GEL_FIN.isoformat()}) : la règle doit être re-ratifiée ou levée (docs/38)")
        return 0

    suffixe = " (gel en vigueur)" if actif else f" (gel expiré {GEL_FIN.isoformat()}, notice)"
    print(f"CI-COMMITS : {len(ci_vus)}/{len(ci_vus)} commit(s) `ci(...)` citent un incident{suffixe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
