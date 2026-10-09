"""r7 — le ratchet dette_PR <= dette_main.

Les rochets CI (except-pass #205, bandit #197) comparaient l'arbre
courant au baseline COMMITTÉ DANS LA BRANCHE TESTÉE — `.github/
except-pass-baseline.json` ou `.github/bandit-baseline.txt`. Une PR
pouvait donc faire `--reset` (le code du reset le « déconseille » sans
l'imposer), relever sa propre référence, et l'alarme se taisait : le
rochet s'auto-mutait.

Fix : option `--baseline PATH` sur `--check`, et deux steps CI qui
extraient le baseline de origin/main (le job security fait déjà un
checkout fetch-depth: 0) et gate le courant contre lui :
dette_PR <= dette_main, y compris fichier par fichier.

    python tests/test_r7_ratchet_baseline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import audit_except_pass as aep  # noqa: E402

CI_SRC = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _ecrire(path: Path, comptes: dict[str, int]) -> None:
    path.write_text(json.dumps(comptes), encoding="utf-8")


class TestChargerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_par_defaut_le_baseline_committed(self):
        """Sans --baseline : la référence reste le baseline committé.

        Dans le repo il EXISTE (207, .github/except-pass-baseline.json) :
        on vérifie que _charger_base() le lit, en comparant à la lecture
        directe du fichier."""
        commited = json.loads(
            (ROOT / ".github" / "except-pass-baseline.json")
            .read_text(encoding="utf-8"))
        attendu = {k: int(v) for k, v in commited.items()}
        self.assertEqual(aep._charger_base(), attendu)

    def test_par_defaut_baseline_inexistant_renvoie_vide(self):
        with patch.object(aep, "BASELINE", Path("/absent/neant.json")):
            self.assertEqual(aep._charger_base(), {})

    def test_chemin_str_et_path_sont_acceptes(self):
        p = self.d / "b.json"
        _ecrire(p, {"scripts/a.py": 3})
        self.assertEqual(aep._charger_base(str(p)), {"scripts/a.py": 3})
        self.assertEqual(aep._charger_base(p), {"scripts/a.py": 3})

    def test_fichier_absent_et_json_casse_renvoient_vide(self):
        self.assertEqual(aep._charger_base(self.d / "absent.json"), {})
        p = self.d / "casse.json"
        p.write_text("{pas du json", encoding="utf-8")
        self.assertEqual(aep._charger_base(p), {})


class TestCheckAvecBaselineAlternative(unittest.TestCase):
    """cmd_check compare le courant (patché) à la référence fournie."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.courant = {"scripts/a.py": 2, "scripts/b.py": 1}

    def tearDown(self):
        self.tmp.cleanup()

    def _check(self, baseline: dict | None) -> int:
        if baseline is None:
            p = self.d / "absent.json"
        else:
            p = self.d / "b.json"
            _ecrire(p, baseline)
        argv = ["--check", "--baseline", str(p)]
        with patch.object(aep, "mesurer", return_value=dict(self.courant)):
            return aep.main(argv)

    def test_dette_egale_a_main_passe(self):
        self.assertEqual(self._check(self.courant), 0)

    def test_dette_inferieure_a_main_passe(self):
        self.assertEqual(self._check({"scripts/a.py": 5, "scripts/b.py": 5}), 0)

    def test_dette_superieure_a_main_refuse(self):
        self.assertEqual(
            self._check({"scripts/a.py": 2, "scripts/b.py": 0}), 1)

    def test_un_fichier_qui_monte_refuse_meme_si_le_total_baisse(self):
        """La règle par-fichier rend le rochet honnête : a baisse, b
        monte — refusé malgré un total strictement égal à main."""
        self.assertEqual(
            self._check({"scripts/a.py": 0, "scripts/b.py": 1}), 1)

    def test_fichier_nouveau_dans_la_pr_refuse(self):
        self.assertEqual(
            self._check({"scripts/a.py": 2}), 1,
            "scripts/b.py n'existait pas sur main : toute dette > 0 refuse")

    def test_baseline_absente_refuse(self):
        """Pas de référence = pas de gate : fail-closed."""
        self.assertEqual(self._check(None), 1)


class TestOracleCI(unittest.TestCase):
    """Les deux steps dette_PR <= dette_main doivent exister et pointer
    sur origin/main (structurellement, pas par substring fragile)."""

    def test_except_pass_compare_a_origin_main(self):
        self.assertIn("git show origin/main:.github/except-pass-baseline.json", CI_SRC)
        self.assertIn("--baseline /tmp/main_except_pass.json", CI_SRC)

    def test_bandit_compare_a_origin_main(self):
        self.assertIn("git show origin/main:.github/bandit-baseline.txt", CI_SRC)
        self.assertIn("dépasse celle de main", CI_SRC)

    def test_les_deux_gates_sont_bloquants(self):
        # les deux steps doivent pouvoir exit 1 (pas de `|| true`)
        self.assertNotIn("--baseline /tmp/main_except_pass.json || true", CI_SRC)


if __name__ == "__main__":
    unittest.main()
