"""Oracles du gate de sélection des tests (ronde 8 — H-58).

Le filtre SUBSTRING historique de run_tests.py
(SLOW_MARKERS = "dexscreener", "onchain", "token_market", "arkham", "cex")
excluait 48,8 % de la suite (1 225 fns / 9 fichiers) sans que rien ne le
signale — dont 7 fichiers verts mesurés <= 0,4 s et 684 fns d'auth.

Ces tests verrouillent :
  1. le défaut = exécuter (un nom qui CONTIENT un marqueur historique
     n'est plus une raison d'exclusion) ;
  2. l'exclusion = explicite, par nom de module exact, avec raison ;
  3. chaque entrée de SLOW_FILES pointe vers un fichier réel de tests/
     (pas de nom fantôme qui ferait croire à une exclusion maîtrisée) ;
  4. le compte de tests du mode fast ne peut pas baisser en silence
     (ratchet baseline, modèle bandit-baseline / audit_except_pass).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_tests import SLOW_FILES, _without_slow, ratchet_verdict


def _fake_case(module_name: str) -> unittest.TestCase:
    """Un TestCase dont SEUL le nom de module importe (le filtre ne lit
    jamais le code du test, seulement child.__class__.__module__)."""

    class _Fake(unittest.TestCase):
        def runTest(self) -> None:
            pass

    _Fake.__module__ = module_name
    return _Fake("runTest")


def _suite(*module_names: str) -> unittest.TestSuite:
    return unittest.TestSuite([_fake_case(m) for m in module_names])


class TestSelectionExplicite(unittest.TestCase):
    def test_le_defaut_est_executer_malgre_un_marqueur_historique(self):
        # H-58 exactement : 'test_cexactly_local' contient le substring
        # 'cex' — l'ancien filtre l'aurait tué en silence. Le nouveau le
        # garde : le défaut est d'exécuter.
        self.assertEqual(_without_slow(_suite("test_cexactly_local")).countTestCases(), 1)

    def test_fichier_liste_slow_est_exclu(self):
        key = next(iter(SLOW_FILES))
        self.assertEqual(_without_slow(_suite(key)).countTestCases(), 0)

    def test_fichier_ordinaire_est_conserve(self):
        self.assertEqual(
            _without_slow(_suite("test_run_tests_selection")).countTestCases(), 1
        )

    def test_l_exclusion_est_par_nom_exact_pas_par_fragment(self):
        # un module qui CONTIENT le nom d'un fichier lent n'est pas exclu
        key = next(iter(SLOW_FILES))
        self.assertEqual(
            _without_slow(_suite(key + "_variant")).countTestCases(), 1
        )

    def test_chaque_entree_slow_files_pointe_vers_un_fichier_reel_avec_raison(self):
        for key, reason in SLOW_FILES.items():
            with self.subTest(key=key):
                self.assertTrue(
                    (ROOT / "tests" / f"{key}.py").exists(),
                    f"SLOW_FILES[{key}] = nom fantôme (aucun fichier tests/{key}.py)",
                )
                self.assertTrue(reason.strip(), f"SLOW_FILES[{key}] : raison exigée")


class TestRatchetCompte(unittest.TestCase):
    def _baseline(self, text: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "test-count-baseline.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_baisse_refusee(self):
        self.assertEqual(ratchet_verdict(1299, self._baseline("1300\n")), 1)

    def test_compte_stable_accepte(self):
        self.assertEqual(ratchet_verdict(1300, self._baseline("1300\n")), 0)

    def test_hausse_libre(self):
        self.assertEqual(ratchet_verdict(1427, self._baseline("1300\n")), 0)

    def test_baseline_absente_fail_open_documente(self):
        # doctrine ratchet ronde 7 : un dépôt sans baseline ne casse pas
        self.assertEqual(
            ratchet_verdict(10, Path("/nonexistent/test-count-baseline.txt")), 0
        )

    def test_baseline_illisible_fail_open(self):
        self.assertEqual(ratchet_verdict(10, self._baseline("pas-un-nombre\n")), 0)


class TestAntiRegressionSource(unittest.TestCase):
    """Le mécanisme lui-même ne doit pas pouvoir redevenir un substring
    silencieux — oracle sur le source (mutation = restauration de
    l'ancien filtre → ces assertions rougissent)."""

    def test_plus_de_marqueurs_substring_dans_le_source(self):
        src = (ROOT / "scripts" / "run_tests.py").read_text(encoding="utf-8")
        self.assertNotIn("SLOW_MARKERS", src)
        self.assertNotIn("m in module", src)

    def test_le_filtrage_lit_une_egalite_exacte(self):
        src = (ROOT / "scripts" / "run_tests.py").read_text(encoding="utf-8")
        self.assertIn("module in SLOW_FILES", src)


if __name__ == "__main__":
    unittest.main()
