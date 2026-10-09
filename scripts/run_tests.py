#!/usr/bin/env python3
"""Lance toute la suite de tests du projet (stdlib unittest, pytest absent).

    python scripts/run_tests.py           # tout
    python scripts/run_tests.py backtest  # filtre sur le nom de fichier
    python scripts/run_tests.py --fast    # mode CI : hors fichiers SLOW explicites
    python scripts/run_tests.py --fast --no-ratchet  # sans le garde de compte

Exit code 1 si un test echoue — utilisable tel quel en cron.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


SLOW_FILES: dict[str, str] = {
    # 684 fns d'auth, aucun time.sleep, > 420 s mesures ronde 8 sans finir
    # (cout de derivation repetee). Hors-ligne mais trop lent pour le gate.
    # Chemin de reintegradation : profiler/cacher les derivations, issue #235.
    "test_onchain_admin_auth": "lent (>420 s, 684 fns) — cf. issue #235",
}
"""Fichiers de tests exclus du mode --fast, un nom exact + la raison.

Historique (H-58) : l'ancien filtre excluait par SUBSTRING
("onchain", "cex", ...) — 9 fichiers / 1 225 fns (48,8 % de la suite) ne
tournaient JAMAIS en CI, dont 7 fichiers verts et rapides (mesure ronde 8 :
<= 0,4 s chacun). Le defaut est desormais « executer » : seul un fichier
explicitement listé ici, avec sa raison, est saute.

Issue #235 (ronde 11) : test_onchain_entity_chain_gaps (414 fns) est
REINTEGRE — ses 3 echecs etaient des defauts du TEST, pas du code
(2 tests non-hermetiques qui ne contrôlaient pas runtime_preflight ;
1 test à timestamps fossiles mai 2026 vs fenetre glissante 30 j), fixes
dans la PR. Cout : ~74 s local (le plus lent du gate, raison suffisant
pour rester hors nightly-only).
"""

BASELINE = ROOT / ".github" / "test-count-baseline.txt"
"""Compte de tests du mode --fast, commite. Le gate refuse de DESCENDRE :
une baisse du compte (fichier de tests retire, classe skippée, découverte
cassée) doit être une decision explicite commitee dans la PR qui l'explique,
jamais un effet de bord silencieux. Modele : bandit-baseline + audit_except_pass.
"""


def _without_slow(suite) -> unittest.TestSuite:
    """Retire UNIQUEMENT les fichiers de SLOW_FILES (nom de module exact).

    unittest charge chaque fichier dans un module nomme 'test_<fichier>'
    (sans extension) ; on filtre sur ce nom, qui est le seul endroit fiable.
    """
    out = unittest.TestSuite()
    for child in suite:
        if isinstance(child, unittest.TestSuite):
            out.addTest(_without_slow(child))
            continue
        module = (child.__class__.__module__ or "").lower()
        if module in SLOW_FILES:
            continue
        out.addTest(child)
    return out


def ratchet_verdict(tests_run: int, baseline_path: Path) -> int:
    """0 = ok, 1 = le compte a baissé. Hausse libre (baseline mise à jour
    en commit par la PR qui fait monter), baisse = refus.

    Fail-open volontaire si la baseline est absente/illisible (doctrine
    du ratchet CI ronde 7 : un dépôt sans baseline ne doit pas casser).
    """
    if not baseline_path.exists():
        print(f"  ratchet : baseline absente ({baseline_path.name}) — pas de gate")
        return 0
    try:
        expected = int(baseline_path.read_text().strip())
    except ValueError:
        print("  ratchet : baseline illisible — pas de gate")
        return 0
    if tests_run < expected:
        print(
            f"  ratchet : {tests_run} < baseline {expected} — des tests ont "
            "disparu du gate ; assumez-le en committant le nouveau baseline "
            "dans la PR qui l'explique, sinon corrigez."
        )
        return 1
    if tests_run > expected:
        print(
            f"  ratchet : {tests_run} > baseline {expected} — hausse libre ; "
            "commitez le nouveau baseline dans cette PR."
        )
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    fast = "--fast" in sys.argv
    all_ = "--all" in sys.argv
    no_ratchet = "--no-ratchet" in sys.argv
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

    if result.wasSuccessful() and fast and not all_ and not pattern and not no_ratchet:
        if ratchet_verdict(result.testsRun, BASELINE):
            return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
