"""Le garde de copie des unités systemd (configs/systemd-user ↔ installées).

Il a été écrit après une dérive RÉELLE : `trading-agent-nightly.service`
installé le 05/10 portait encore les étapes bloquantes que le FIX R3 (08/10)
avait rendues tolérantes. Les correctifs étaient dans git, jamais déployés —
et rien ne le disait.

On teste sur des dossiers temporaires : jamais `~/.config/systemd` du poste.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import audit_systemd_units as u  # noqa: E402


class LaCopieDoitEtreFidele(unittest.TestCase):

    def _dirs(self, repo: dict, installe: dict):
        a, b = tempfile.TemporaryDirectory(), tempfile.TemporaryDirectory()
        for base, files in ((a.name, repo), (b.name, installe)):
            for nom, txt in files.items():
                (Path(base) / nom).write_text(txt, encoding="utf-8")
        return a, b

    def test_copie_identique_est_fidele(self) -> None:
        svc = "[Service]\nExecStart=/x.py\n"
        a, b = self._dirs({"s.service": svc}, {"s.service": svc})
        r = u.comparer(Path(a.name), Path(b.name))
        self.assertEqual(r["divergentes"], [])
        self.assertEqual(r["fideles"], ["s.service"])
        a.cleanup(); b.cleanup()

    def test_un_execstart_different_est_une_divergence(self) -> None:
        # le cas vécu : `ExecStart=` (bloquant) vs `ExecStart=-` (tolérant)
        repo = {"s.service": "[Service]\nExecStart=-/x.py\n"}
        installe = {"s.service": "[Service]\nExecStart=/x.py\n"}
        a, b = self._dirs(repo, installe)
        self.assertEqual(u.comparer(Path(a.name), Path(b.name))["divergentes"],
                         ["s.service"])
        a.cleanup(); b.cleanup()

    def test_un_commentaire_different_n_est_PAS_une_divergence(self) -> None:
        """Juger le commentaire serait juger le style, pas le comportement."""
        repo = {"s.service": "# version dépôt\n[Service]\nExecStart=/x.py\n"}
        installe = {"s.service": "# version installée (autre note)\n[Service]\nExecStart=/x.py\n"}
        a, b = self._dirs(repo, installe)
        self.assertEqual(u.comparer(Path(a.name), Path(b.name))["divergentes"], [])
        a.cleanup(); b.cleanup()

    def test_versionnee_non_installee_est_signalee_mais_pas_une_derive(self) -> None:
        a, b = self._dirs({"s.service": "[Service]\n"}, {})
        r = u.comparer(Path(a.name), Path(b.name))
        self.assertEqual(r["non_installees"], ["s.service"])
        self.assertEqual(r["divergentes"], [])
        a.cleanup(); b.cleanup()

    def test_les_timers_sont_couverts(self) -> None:
        a, b = self._dirs({"t.timer": "[Timer]\nOnCalendar=*-*-* 03:00:00\n"},
                          {"t.timer": "[Timer]\nOnCalendar=*-*-* 04:00:00\n"})
        self.assertEqual(u.comparer(Path(a.name), Path(b.name))["divergentes"],
                         ["t.timer"])
        a.cleanup(); b.cleanup()

    def test_repo_absent_est_signale(self) -> None:
        with tempfile.TemporaryDirectory() as b:
            self.assertTrue(u.comparer(Path("/inexistant"), Path(b))["repo_absent"])


if __name__ == "__main__":
    unittest.main()
