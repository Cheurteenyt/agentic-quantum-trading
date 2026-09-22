"""Tests du housekeeping — rétention par familles et garde-fous.

Une rétention qui supprime trop (fichiers d'identité) ou pas assez serait
pire que pas de rétention : ces tests verrouillent les deux.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.housekeeping as hk  # noqa: E402


class PruneTest(unittest.TestCase):
    def setUp(self):
        self._old_reports = hk.REPORTS
        hk.REPORTS = Path(tempfile.mkdtemp())
        self._old_protected = hk.PROTECTED
        # neutraliser le git (tmpdir n'est pas un repo) : les fichiers ne sont pas suivis
        for i in range(6):
            (hk.REPORTS / f"campaign-nightly-2026090{i}T120000Z-x.md").write_text("x")
        (hk.REPORTS / "registre-draft-post.txt").write_text("garder")

    def tearDown(self):
        hk.REPORTS = self._old_reports
        hk.PROTECTED = self._old_protected

    def test_keeps_newest_n(self):
        actions = hk.prune(apply=False)
        names = {p.name for p, _ in actions}
        # 6 logs, on en garde 5 -> 1 supprimé (le plus ancien)
        self.assertEqual(len(names), 1)
        self.assertIn("campaign-nightly-20260900T120000Z-x.md", names)

    def test_never_touches_identity_files(self):
        actions = hk.prune(apply=False)
        self.assertNotIn("registre-draft-post.txt", {p.name for p, _ in actions})

    def test_html_removed_only_when_pdf_newer(self):
        html = hk.REPORTS / "registre-board.html"
        html.write_text("<html></html>")
        pdf = hk.REPORTS / "registre-board-20260922T000000Z.pdf"
        pdf.write_text("%PDF")
        actions = hk.prune(apply=False)
        self.assertIn(html, {p for p, _ in actions})
        # PDF plus VIEUX que le HTML -> on garde le HTML (conversion pas encore faite)
        older = hk.REPORTS / "registre-board-20260921T000000Z.pdf"
        older.write_text("%PDF")
        import os
        os.utime(older, (1, 1))
        pdf.unlink()
        actions = hk.prune(apply=False)
        self.assertNotIn(html, {p for p, _ in actions})


if __name__ == "__main__":
    unittest.main()
