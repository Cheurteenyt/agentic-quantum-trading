"""Tests du housekeeping — rétention par familles et garde-fous.

Une rétention qui supprime trop (fichiers d'identité) ou pas assez serait
pire que pas de rétention : ces tests verrouillent les deux.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
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

class TieBreakTest(unittest.TestCase):
    """Le rétention ne doit JAMAIS dépendre de l'ordre de création.

    `dated_files` triait sur le `mtime` seul. `sorted()` étant stable, deux
    fichiers de mtime ÉGALE gardent l'ordre de `glob()` — qui est l'ordre du
    système de fichiers, pas un ordre défini.

    Mesuré sur le fichier de production du projet : `test_keeps_newest_n`
    échouait 7 fois sur 8 dans un sandbox à résolution de mtime grossière.
    Ici il passe 20 fois sur 20 — la résolution nanoseconde du filesystem
    masque le problème, ce qui est pire : l'oracle est vert par hasard.

    Le test force des mtimes IDENTIQUES avec `os.utime`, ce qui rend le cas
    déterministe et reproduit la panne à chaque exécution. Il vérifie aussi
    que le choix ne dépend pas de l'ordre de création.
    """

    def _fabricate(self, ordre_creation: list[int]) -> set[str]:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        ancien = hk.REPORTS
        hk.REPORTS = tmp
        self.addCleanup(lambda: setattr(hk, "REPORTS", ancien))
        noms = [f"campaign-nightly-2026090{i}T120000Z-x.md" for i in range(6)]
        for i in ordre_creation:                 # ordre AU CHOIX
            (tmp / noms[i]).write_text("x")
        # mtimes IDENTIQUES : c'est le cas réel de deux rapports produits
        # dans la même seconde par la campagne nocturne.
        fixe = time.time() - 86400
        for n in noms:
            os.utime(tmp / n, (fixe, fixe))
        return {p.name for p, _ in hk.prune(apply=False)}

    def test_mtimes_identiques_le_plus_ancien_part_igualement(self):
        """Avec le tie-break par nom, la réponse est la date DU NOM.

        6 fichiers, on en garde 5 -> le supprimé est le plus ancien, donc
        `…20260900…`. Le nom porte la date, donc c'est un ordre réel.
        """
        supprimes = self._fabricate([0, 1, 2, 3, 4, 5])
        self.assertEqual(supprimes, {"campaign-nightly-20260900T120000Z-x.md"})

    def test_la_suppression_ne_dépend_pas_de_l_ordre_de_création(self):
        """LA contre-preuve — le défaut que le test d'origine ne voyait pas.

        Même contenu, même mtimes, ordre de création inversé : le fichier
        supprimé doit être le MÊME. Avant le correctif, l'ordre inversé
        supprimait `…20260905…` — c'est-à-dire qu'`housekeeping.py` pouvait
        effacer le rapport le plus récent d'un lot.
        """
        croissant = self._fabricate([0, 1, 2, 3, 4, 5])
        decroissant = self._fabricate([5, 4, 3, 2, 1, 0])
        self.assertEqual(
            croissant, decroissant,
            "l'ordre de création décide de la suppression : le tri n'a pas "
            "de tie-break")

    def test_un_seul_temps_de_fuite(self):
        """Le tie-break ne doit pas casser le tri par mtime.

        Le nom ne prime PAS sur la date réelle : deux rapports de dates
        différentes doivent rester ordonnés par leur mtime.
        """
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        ancien = hk.REPORTS
        hk.REPORTS = tmp
        self.addCleanup(lambda: setattr(hk, "REPORTS", ancien))
        # un rapport ANCIEN mais au nom lexicographiquement grand
        vieux = tmp / "campaign-nightly-20260900T120000Z-x.md"
        # un rapport RÉCENT au nom lexicographiquement petit
        recent = tmp / "campaign-nightly-20260905T120000Z-x.md"
        vieux.write_text("x")
        recent.write_text("x")
        os.utime(vieux, (time.time() - 10 * 86400,) * 2)
        os.utime(recent, (time.time() - 86400,) * 2)
        ordre = [p.name for p in hk.dated_files("campaign-nightly-*.md")]
        self.assertEqual(ordre, [recent.name, vieux.name],
                         "le mtime doit primer sur le nom quand ils diffèrent")


if __name__ == "__main__":
    unittest.main()
