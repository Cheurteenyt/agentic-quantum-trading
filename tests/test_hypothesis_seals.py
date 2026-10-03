from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def const(script: str, name: str) -> str:
    m = re.search(rf'^{name}\s*=\s*"([0-9a-f]{{64}})"', (ROOT / script).read_text(encoding="utf-8"), re.M)
    assert m, f"{name} introuvable dans {script}"
    return m.group(1)


class SealTests(unittest.TestCase):
    """Un pré-enregistrement scellé ne change plus : on AMENDE PAR AJOUT (fichier séparé, scellé à part)."""

    def test_crowding_composite_seals(self):
        s = "scripts/crowding_composite.py"
        self.assertEqual(sha(ROOT / "docs/lab/hypotheses/crowding-composite.md"), const(s, "EXPECTED_SEAL"),
                         "l'hypothèse scellée a été modifiée : le script refuserait de tourner (exit 2)")
        self.assertEqual(sha(ROOT / "docs/lab/hypotheses/crowding-composite.amendments.md"), const(s, "EXPECTED_AMEND_SEAL"))


if __name__ == "__main__":
    unittest.main()
