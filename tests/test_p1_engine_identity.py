#!/usr/bin/env python3
"""P1 (audit 2026-10-08) — l'identité de campagne doit couvrir la mesure.

`ENGINE_FILES` était une liste écrite à la main : 4 fichiers alors que la
clôture transitive réelle en compte **18**. Deux modules du cœur
scientifique étaient absents — `aster_indicators.py` (importé au niveau
module par `research_runner.py:56`, il fournit `volume_z`, une des
features) et `research_os.py` (importé au niveau module :91).

Conséquence directe du trou :

    aster_indicators.py modifié  ->  la mesure change
                               ->  engine_sha reste IDENTIQUE
                               ->  la spec DONE n'est PAS rejouée

C'est exactement ce que l'identité de campagne doit empêcher.

Ces tests verrouillent trois propriétés, dont la troisième est celle qui
compte vraiment : **il ne doit pas exister de module de mesure atteignable
qui ne soit ni haché ni explicitement exclu**. Un ajout à la main
corrigerait le symptôme en laissant le mécanisme ouvert.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import research_worker as w  # noqa: E402


class TestCouvertureDeLaCloture(unittest.TestCase):
    """Propriété 1 — pas de trou silencieux."""

    def test_tout_module_atteignable_est_hache_ou_exclu(self):
        """Rejoue la clôture et exige une partition EXHAUSTIVE.

        Si un module est atteignable et absent d'`ENGINE_FILES` sans être
        dans `NOT_MEASUREMENT`, il n'est couvert par rien : c'est
        exactement le bug audité.
        """
        atteignables: set[str] = set()

        def promener(p: Path) -> None:
            if p in w.ENGINE_FILES or str(p.relative_to(ROOT)) in w.NOT_MEASUREMENT:
                return
            if str(p) in {str(x) for x in atteignables}:
                return
            for mod in sorted(w._imports_de(p)):
                cible = w._resoudre(mod)
                if cible is not None:
                    promener(cible)
            atteignables.add(str(p))

        for nom in w.MEASUREMENT_ROOTS:
            racine = ROOT / "scripts" / nom
            self.assertTrue(racine.exists(), f"racine absente : {nom}")
            promener(racine)

        non_couverts = sorted(
            f for f in {str(p.relative_to(ROOT)) for p in
                        (ROOT / "x" for x in atteignables)}
            if f not in {str(p.relative_to(ROOT)) for p in w.ENGINE_FILES}
            and f not in w.NOT_MEASUREMENT
        )
        self.assertEqual(
            non_couverts, [],
            f"modules de mesure atteignables mais NI hachés NI exclus : "
            f"{non_couverts}")

    def test_les_racines_du_coeur_scientifique_sont_bien_couvertes(self):
        """Les deux absences de l'audit, nommées explicitement."""
        rel = {str(p.relative_to(ROOT)) for p in w.ENGINE_FILES}
        for attendu in ("scripts/aster_indicators.py",
                        "scripts/research_os.py",
                        "scripts/research_runner.py",
                        "scripts/label_matrix.py",
                        "scripts/universe.py",
                        "scripts/funding_series.py"):
            with self.subTest(fichier=attendu):
                self.assertIn(attendu, rel,
                              f"{attendu} a disparu de l'identité de campagne")

    def test_la_cloture_est_plus_large_qu_avant(self):
        """Garde-fou de non-régression sur le nombre."""
        self.assertGreaterEqual(len(w.ENGINE_FILES), 18,
                                f"{len(w.ENGINE_FILES)} fichiers — la clôture "
                                f"s'est rétrécie, un module de mesure a peut-être "
                                f"été exclu sans justification")


class TestDeterminisme(unittest.TestCase):
    def test_la_cloture_est_triee_et_stable(self):
        """Deux appels donnent le même tuple, dans le même ordre.

        Un sha qui dépend de l'ordre de découverte dépendrait du système de
        fichiers : deux machines donneraient deux `engine_sha` pour le même
        code, et toutes les specs DONE seraient invalidées à chaque
        migration.
        """
        a = w.measurement_files()
        b = w.measurement_files()
        self.assertEqual(a, b)
        rel = [str(p.relative_to(ROOT)) for p in a]
        self.assertEqual(rel, sorted(rel), "la clôture doit être triée")

    def test_chaque_exclusion_existe_sur_le_disque(self):
        """Une exclusion qui ne correspond à rien est un piège dormant."""
        for rel in w.NOT_MEASUREMENT:
            with self.subTest(exclusion=rel):
                self.assertTrue((ROOT / rel).exists(),
                                f"{rel} est exclu mais n'existe pas : "
                                f"l'exclusion ne protège rien et masque le fait "
                                f"que le nom a changé")


class TestLeShaSuitLeContenu(unittest.TestCase):
    """Propriétés 2 et 3 — un changement pertinent change le sha, un autre non."""

    def setUp(self):
        self.avant = w._engine_sha()

    def test_modifier_un_module_de_measure_change_le_sha(self):
        """Propriété 2 — le cas de l'audit, sur un fichier de mesure."""
        cible = ROOT / "scripts" / "aster_indicators.py"
        original = cible.read_bytes()
        try:
            cible.write_bytes(original + b"\n# F-048 probe\n")
            self.assertNotEqual(
                w._engine_sha(), self.avant,
                "modifier un module de mesure ne change PAS engine_sha : "
                "l'identité de campagne est percée")
        finally:
            cible.write_bytes(original)
        self.assertEqual(w._engine_sha(), self.avant, "restauration incomplète")

    def test_modifier_un_exclu_ne_change_pas_le_sha(self):
        """Propriété 3 — sinon le ratchet sert à rien.

        `portfolio_runner` est la CLI de confirmation, exclue pour ne pas
        invalider les discoveries à chaque retouche de CLI. Si son contenu
        entrait dans le sha, toute PR de CLI invaliderait le patrimoine.
        """
        cible = ROOT / "scripts" / "portfolio_runner.py"
        self.assertTrue(cible.exists())
        original = cible.read_bytes()
        try:
            cible.write_bytes(original + b"\n# probe\n")
            self.assertEqual(w._engine_sha(), self.avant,
                             "un module EXCLU entre dans le sha : le ratchet "
                             "devient inutilisable")
        finally:
            cible.write_bytes(original)

    def test_un_doc_ne_change_pas_le_sha(self):
        """La doctrine : un commit docs ne change pas ce qu'on mesure."""
        cible = ROOT / "docs" / "NUMEROTATION.md"
        original = cible.read_bytes()
        try:
            cible.write_bytes(original + b"\nprobe\n")
            self.assertEqual(w._engine_sha(), self.avant)
        finally:
            cible.write_bytes(original)

    def test_le_sha_est_stable_sans_modification(self):
        self.assertEqual(w._engine_sha(), self.avant, "le sha n'est pas stable a contenu identique")


class TestLeMecanismeNePeutPasEtreAffaibliSilencieusement(unittest.TestCase):
    """Les ratchets (bandit, `except: pass`) se désactivent si on relève
    leur base dans la même PR. Ici on vérifie que le MÉCANISME du ratchet
    reste cohérent avec ce qu'il compte."""

    def test_les_deux_references_existent_et_sont_lisibles(self):
        for rel in (".github/bandit-baseline.txt",
                    ".github/except-pass-baseline.json"):
            with self.subTest(reference=rel):
                self.assertTrue((ROOT / rel).exists(),
                                f"{rel} absent : le ratchet correspondant "
                                f"échouerait en CI")


if __name__ == "__main__":
    unittest.main()