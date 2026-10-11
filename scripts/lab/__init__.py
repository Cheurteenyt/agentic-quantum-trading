#!/usr/bin/env python3
"""E2 (audit Sonnet 5.5) — LE LAB DE RECHERCHE comme UN package.

Le constat de l'audit : la recherche vivait en ~20 modules éparpillés dans
scripts/ sans frontière déclarée — impossible de dire ce qui EST le lab.
Ce package déclare la surface : chaque membre est importable comme unité
(`from scripts.lab import ledger`) et la liste EST la définition du lab.

⚠️ Les fichiers ne sont PAS déplacés : les chemins `scripts/lab_ledger.py`
etc. sont CITÉS par l'audit, STATE.md, AGENTS.md, le CI et les docs — les
bouger pour de la cosmétique casserait plus que ça n'apporte. Le package
est la FRONTIÈRE déclarée et vérifiable (audit_check E4), pas un
déménagement.

Membres (la surface du lab) :
    costs          le modèle de coûts par symbole + breakeven (P2)
    lab_ledger     le ledger (check/log/status/selftest)
    label_matrix   les labels 1h + event_study
    research_forward le forward journalier
    research_integrity les invariants I001-I011
    research_os    les primitives (Mode, DataScope, protocole)
    research_runner  le moteur discovery/confirmation
    research_velocity  la vélocité + échéances
    universe       les univers point-in-time (P3)
"""
from __future__ import annotations

import importlib

# La SURFACE du lab — l'ajout/retrait d'un membre est un acte de recherche
# structurant (PR dédiée), pas un import de plus.
SURFACE: tuple[str, ...] = (
    "costs",
    "lab_ledger",
    "label_matrix",
    "research_forward",
    "research_integrity",
    "research_os",
    "research_runner",
    "research_velocity",
    "universe",
)


def __getattr__(name: str):
    """Import paresseux : `from scripts.lab import ledger` importe
    scripts/ledger sans charger tout le lab (numpy/pandas ne paient que
    quand on les demande)."""
    if name in SURFACE:
        return importlib.import_module(f"scripts.{name}")
    raise AttributeError(
        f"{name!r} n'est pas dans la surface du lab {SURFACE}")


def membres_importables() -> tuple[str, ...]:
    """Chaque membre déclaré s'importe-il réellement ? Retourne les
    manquants (vide = la surface tient)."""
    manquants = []
    for name in SURFACE:
        try:
            importlib.import_module(f"scripts.{name}")
        except Exception:
            manquants.append(name)
    return manquants
