#!/usr/bin/env python3
"""Lance toute la suite de tests du projet (stdlib unittest, pytest absent).

    python scripts/run_tests.py           # tout
    python scripts/run_tests.py backtest  # filtre sur le nom de fichier

Exit code 1 si un test echoue — utilisable tel quel en cron.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


SLOW_MARKERS = ("dexscreener", "onchain", "token_market", "arkham", "cex")
"""Fichiers de tests qui tapent le reseau : la suite complete met ~44 min a
cause d'eux. Un runner qu'on n'ose pas lancer ne protege personne, donc on
expose un mode rapide par defaut.
"""


def _without_slow(suite) -> unittest.TestSuite:
    """Retire les fichiers de tests qui tapent le reseau (44 min sinon).

    unittest charge chaque fichier dans un module nomme 'test_<fichier>'
    (sans extension) ; on filtre sur ce nom, qui est le seul endroit fiable.
    """
    out = unittest.TestSuite()
    for child in suite:
        if isinstance(child, unittest.TestSuite):
            out.addTest(_without_slow(child))
            continue
        module = (child.__class__.__module__ or "").lower()
        if any(m in module for m in SLOW_MARKERS):
            continue
        out.addTest(child)
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    fast = "--fast" in sys.argv
    all_ = "--all" in sys.argv
    if fast and all_:
        print("--fast et --all sont mutuellement exclusifs", file=sys.stderr)
        return 2
    pattern = args[0] if args else ""
    glob = f"test_*{pattern}*.py" if pattern else "test_*.py"

    # top_level_dir = tests/ : evite d'exiger un tests/__init__.py, qui
    # changerait la facon dont les tests existants du projet sont importes.
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(ROOT / "tests"), pattern=glob, top_level_dir=str(ROOT / "tests")
    )

    if fast and not all_:
        suite = _without_slow(suite)

    result = unittest.TextTestRunner(verbosity=1).run(suite)

    print()
    print(f"  tests   : {result.testsRun}")
    print(f"  echecs  : {len(result.failures)}")
    print(f"  erreurs : {len(result.errors)}")
    print(f"  ignores : {len(result.skipped)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
