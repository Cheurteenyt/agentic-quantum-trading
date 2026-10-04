"""Tests du vérificateur de preuves (Research Firewall, couche 4).

Le firewall n'est utile que si son juge est lui-même mécanique et sans
détail : SUPPORTED / CONTRADICTED / UNVERIFIED sur des fixtures.

    python tests/test_claim_verify.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import claim_verify as cv  # noqa: E402


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "code.py").write_text(
            "def atr(df, n=24):\n    return 1\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _verify(self, fact):
        return cv.verify(fact, base=self.root)

    def test_fait_supported_quand_les_patterns_tiennent(self):
        res = self._verify({
            "id": "F-T1", "path": "code.py", "status": "fixed",
            "claim": "l'ATR est un True Range",
            "require_present": ["def atr", "return 1"],
            "require_absent": ["interpolation futuriste"]})
        self.assertEqual(res["verdict"], "SUPPORTED")

    def test_fait_contredit_quand_le_vieux_code_revient(self):
        res = self._verify({
            "id": "F-T2", "path": "code.py", "status": "fixed",
            "claim": "bug corrigé",
            "require_absent": ["def atr"]})
        self.assertEqual(res["verdict"], "CONTRADICTED")
        self.assertIn("interdit PRÉSENT", res["reason"])

    def test_fait_contredit_quand_le_fix_disparait(self):
        res = self._verify({
            "id": "F-T3", "path": "code.py", "status": "fixed",
            "claim": "fix présent",
            "require_present": ["return 42"]})
        self.assertEqual(res["verdict"], "CONTRADICTED")
        self.assertIn("requis absent", res["reason"])

    def test_fait_unverified_si_le_fichier_manque(self):
        res = self._verify({
            "id": "F-T4", "path": "introuvable.py", "status": "confirmed",
            "claim": "quoi qu'il en soit"})
        self.assertEqual(res["verdict"], "UNVERIFIED")

    def test_ledger_illisible_devient_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "facts.jsonl"
            bad.write_text("{pas du json}\n", encoding="utf-8")
            facts = cv.load_ledger(bad)
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0]["status"], "UNVERIFIED")

    def test_le_ledger_reel_tient(self):
        """Le vrai ledger doit être auto-cohérent au moment du commit."""
        facts = cv.load_ledger(cv.LEDGER)
        self.assertGreater(len(facts), 20)
        bad = [f["id"] for f in facts if cv.verify(f)["verdict"] != "SUPPORTED"]
        self.assertEqual(bad, [], f"faits contredits: {bad}")


if __name__ == "__main__":
    unittest.main()
