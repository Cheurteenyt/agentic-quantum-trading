#!/usr/bin/env python3
"""G10 — `Path(__file__).resolve().parents[N]` doit résoudre à la racine.

Test de SENS : l'oracle doit signaler le VRAI bug (parents[1] sur un
script en sous-dossier vivant -> scripts/) et PAS les faux (imports
scripts/ légitimes, STUDIES_DIR.parents[1] correct, archive dormant).

Le bug fondateur : un agent copie l'en-tête d'un script racine dans un
sous-dossier. parents[1] résout vers scripts/, ROOT/"data/..." cherche
scripts/data/... inexistant. Plante au lancement seulement, jamais à
l'import — donc invisible sans cet oracle.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.audit_path_root as G10  # noqa: E402


class _Arbre:
    """Un repo fictif minimal avec la structure scripts/<dossier>/fichier."""

    def __init__(self, fichiers: dict[str, str]):
        # fichiers: {"studies/x.py": "code...", "archive/y.py": "..."}
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel, code in fichiers.items():
            p = self.root / "scripts" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(code, encoding="utf-8")

    def scan(self):
        return G10.scan(root=self.root)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.tmp.cleanup()


# En-têtes types, reproduits fidèlement
ROOT_BON = 'ROOT = Path(__file__).resolve().parents[1]\nDB = ROOT / "data" / "x.db"\n'
ROOT_BUG = 'ROOT = Path(__file__).resolve().parents[1]\nDB = ROOT / "data" / "x.db"\n'
IMPORT_OK = 'import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\nfrom frere import x\n'
STUDIES_OK = ('from pathlib import Path\nSTUDIES_DIR = Path(__file__).resolve().parent\n'
              'ROOT = STUDIES_DIR.parents[1]\nDB = ROOT / "data" / "x.db"\n')


class TestG10(unittest.TestCase):

    def test_script_racine_sain(self):
        with _Arbre({"racine.py": ROOT_BON}) as a:
            self.assertEqual(a.scan(), [], "parents[1] à la racine = correct")

    def test_sous_dossier_vivant_buggue(self):
        """LE bug fondateur : parents[1] dans studies/ resout vers scripts/."""
        with _Arbre({"studies/x.py": ROOT_BUG}) as a:
            c = a.scan()
            self.assertEqual(len(c), 1, "le sous-dossier vivant DOIT être signalé")
            self.assertTrue(c[0]["resout"].endswith("scripts"),
                            f"attendu resolution vers scripts/, eu {c[0]['resout']}")

    def test_import_frere_legitime_pas_signale(self):
        """sys.path.insert(0, .../parents[1]) pour trouver un module de
        scripts/ est LÉGITIME — ce n'est pas un ROOT mal résolu."""
        with _Arbre({"studies/probe.py": IMPORT_OK}) as a:
            self.assertEqual(a.scan(), [],
                             "un sys.path.insert vers scripts/ est intentionnel")

    def test_studies_dir_parents1_correct_pas_signale(self):
        """STUDIES_DIR = parent ; ROOT = STUDIES_DIR.parents[1] resout à la
        racine — c'est le motif NORMAL des scripts vivants studies/."""
        with _Arbre({"studies/y.py": STUDIES_OK}) as a:
            self.assertEqual(a.scan(), [],
                             "STUDIES_DIR.parents[1] resout à la racine : correct")

    def test_archive_hors_scope(self):
        """Le code retiré (archive/) n'est pas jugé : 0 référence, jamais
        lancé. Le patcher serait du bruit."""
        with _Arbre({"archive/z.py": ROOT_BUG}) as a:
            self.assertEqual(a.scan(), [],
                             "archive/ est hors scope (code retiré)")

    def test_archive_studies_hors_scope(self):
        with _Arbre({"archive_studies/w.py": ROOT_BUG}) as a:
            self.assertEqual(a.scan(), [],
                             "archive_studies/ est hors scope")

    def test_commentaire_pas_signale(self):
        with _Arbre({"studies/c.py":
                     '# ROOT = Path(__file__).resolve().parents[1]  # vieux\n'
                     'ROOT = Path(__file__).resolve().parent.parent\n'}) as a:
            self.assertEqual(a.scan(), [],
                             "une ligne commentée ne doit pas être signalée")


if __name__ == "__main__":
    unittest.main()
