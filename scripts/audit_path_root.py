#!/usr/bin/env python3
"""G10 (deep-audit, ronde 13) — `Path(__file__).resolve().parents[N]` dans
un sous-dossier de `scripts/` doit résoudre à la RACINE du repo, pas à
`scripts/`.

## Le bug fondateur

Un agent copie l'en-tête d'un script racine (`scripts/x.py`, où
`parents[1]` = racine) dans un sous-dossier (`scripts/studies/x.py`, où
`parents[1]` = `scripts/`). Le `ROOT` résout alors vers `scripts/`, et
tout `ROOT / "data/..."` cherche `scripts/data/...` qui n'existe pas.
Le script plante SEULEMENT au lancement, jamais à l'import — donc rien
ne le signale, et un agent qui le relance croit à un problème de données.

Mesure au 2026-10-10 (audit) : **17 occurrences** de ce pattern, mais la
plép PART dans `archive/` et `archive_studies/` — du code retiré, 0
référence, jamais exécuté. Les scripts VIVANTS utilisent soit
`STUDIES_DIR.parents[1]` (correct : STUDIES_DIR = scripts/studies, donc
parents[1] = racine), soit un `parents[1]` INTENTIONNEL pour mettre
`scripts/` dans `sys.path` (trouver un module frère de la racine).

## Pourquoi un oracle et pas un patch

Patcher les 17 lignes d'archive aujourd'hui serait du bruit sur du code
mort. Le vrai risque est la RÉINTRODUCTION : un agent copie encore un
en-tête, et le prochain script vivant plante en silence. Cet oracle rend
le motif détectable, et un test prouve qu'il distingue le vrai bug du
faux (import frère intentionnel, STUDIES_DIR correct).

## Ce qu'il signale, précisément

Uniquement dans `scripts/` HORS `archive*` : `Path(__file__).resolve()
.parents[N]` (ou `.parents[N]` sur `__file__`) dont la résolution N'est
PAS la racine du repo. Il NE signale PAS :
  - un `sys.path.insert(0, ...)` (ajouter scripts/ au path est légitime) ;
  - un `.parents[N]` sur une variable de dossier (STUDIES_DIR, etc.) dont
    la résolution est correcte — c'est le cas normal des studies/ ;
  - quoi que ce soit dans `archive/` (code retiré).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Dossiers de scripts/ considérés VIVANTS (le reste = archive, hors scope).
ARCHIVE_MARKERS = ("archive", "archive_studies")


def _vivant(rel: Path) -> bool:
    parts = rel.parts
    return not any(p in ARCHIVE_MARKERS or p.startswith("archive")
                   for p in parts)


def _resout(expr_src: str, fichier: Path) -> Path | None:
    """Évalue `Path(__file__).resolve().parents[N]` pour ce fichier.

    Reproduit la sémantique pathlib SANS exécuter le code du script (qui
    pourrait avoir des effets). Retourne None si l'expression n'est pas
    un `parents[N]` sur `__file__`.
    """
    m = re.search(r"parents\[(\d+)\]", expr_src)
    if not m:
        return None
    n = int(m.group(1))
    # `Path(__file__).resolve()` = le fichier lui-même (déjà absolu ici)
    base = fichier.resolve()
    try:
        return base.parents[n]
    except IndexError:
        return None


def scan(root: Path | None = None) -> list[dict]:
    root = Path(root or ROOT)
    racine = root.resolve()
    out: list[dict] = []
    for f in sorted((root / "scripts").rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(racine)
        if not _vivant(rel):
            continue
        try:
            src = f.read_text(encoding="utf-8-sig", errors="ignore")
            arbre = ast.parse(src)
        except (OSError, SyntaxError):
            continue

        # On re-scan en TEXTE plutôt qu'en AST : la ligne `ROOT =
        # Path(__file__).resolve().parents[1]` est courte et hors
        # commentaire dans la pratique, et le texte voit le `[N]` que
        # l'AST fragmenterait en Subscript(slice=Constant) — plus fragile
        # à remonter qu'une regex sur la ligne.
        for i, line in enumerate(src.splitlines(), 1):
            if "__file__" not in line or "parents[" not in line:
                continue
            if line.lstrip().startswith("#"):
                continue
            # ignorer sys.path.insert : légitime
            if "sys.path" in line:
                continue
            n = _resout(line, f)
            if n is not None and n != racine:
                out.append({
                    "file": str(rel), "line": i,
                    "resout": str(n),
                    "code": line.strip()[:90],
                })
    return out


def main() -> int:
    constats = scan()
    if not constats:
        print("G10 PATH ROOT: PASS — aucun parents[N] sur __file__ ne "
              "résout hors de la racine du repo (hors archive)")
        return 0
    print(f"G10 PATH ROOT: {len(constats)} CAS(S)")
    for c in constats:
        print(f"  {c['file']}:{c['line']} — résout vers {c['resout']}")
        print(f"      {c['code']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
