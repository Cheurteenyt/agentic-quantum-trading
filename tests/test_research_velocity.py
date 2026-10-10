#!/usr/bin/env python3
"""E5 — vélocité de la recherche : les métriques doivent refléter le ledger
VIVANT, pas l'historique invalidé.

Le fait dur de la revue (2026-10-10) : 657 commits, 0 candidat, et AUCUN
indicateur de productivité. Ce test verrouille la métrique : elle compte les
entrées NON-superseded (une entrée superseded est hors preuve — s'en créditer
serait compter du travail invalidé), et distingue « tranchée » (un résultat)
de « candidat » (le vrai produit).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.research_velocity as RV  # noqa: E402


class TestVelocityMetriques(unittest.TestCase):

    def _ecrit(self, tmp: Path, entrees: list[dict]) -> Path:
        p = tmp / "trials.jsonl"
        p.write_text("\n".join(json.dumps(e, ensure_ascii=False)
                               for e in entrees) + "\n", encoding="utf-8")
        return p

    def test_compte_que_les_vivants(self):
        """Une entrée superseded NE compte PAS comme productivité."""
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ecrit(Path(d), [
                {"date": "2026-10-06", "verdict": "DISCOVERY_FAIL"},
                {"date": "2026-10-06", "verdict": "PASS", "superseded": "PR-143"},
            ])
            import unittest.mock as m
            with m.patch.object(RV, "LEDGER", ledger):
                m_ = RV.metriques(RV.charger())
            self.assertEqual(m_["total_vivant"], 1,
                             "la PASS superseded ne doit PAS compter")
            self.assertEqual(m_["cette_semaine"]["candidats"], 0,
                             "un candidat superseded n'est pas un candidat")

    def test_fail_est_un_resultat_pas_zero(self):
        """Un DISCOVERY_FAIL est une hypothèse tranchée (résultat), pas un vide."""
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ecrit(Path(d), [
                {"date": "2026-10-06", "verdict": "DISCOVERY_FAIL"},
            ])
            import unittest.mock as m
            with m.patch.object(RV, "LEDGER", ledger):
                mm = RV.metriques(RV.charger())
            cs = mm["cette_semaine"]
            self.assertEqual(cs["lots"], 1)
            self.assertEqual(cs["tranchees"], 1,
                             "un FAIL = 1 hypothèse tranchée (pas 0)")
            self.assertEqual(cs["candidats"], 0,
                             "un FAIL n'est PAS un candidat")

    def test_candidat_positif_compte(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ecrit(Path(d), [
                {"date": "2026-10-06", "verdict": "PASS"},
            ])
            import unittest.mock as m
            with m.patch.object(RV, "LEDGER", ledger):
                mm = RV.metriques(RV.charger())
            self.assertEqual(mm["cette_semaine"]["candidats"], 1)

    def test_semaine_courante_est_la_plus_recente(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ecrit(Path(d), [
                {"date": "2026-09-28", "verdict": "FAIL"},   # semaine précédente
                {"date": "2026-10-06", "verdict": "FAIL"},   # semaine courante
            ])
            import unittest.mock as m
            with m.patch.object(RV, "LEDGER", ledger):
                mm = RV.metriques(RV.charger())
            self.assertEqual(mm["semaine_courante"], "2026-W41")
            self.assertEqual(mm["cette_semaine"]["lots"], 1,
                             "seule la semaine courante compte dans 'cette_semaine'")

    def test_ledger_reel_zero_lot_visible(self):
        """Le ledger RÉEL du dépôt : la métrique doit tourner sans planter et
        refléter les 16 vivants (toutes DISCOVERY_FAIL)."""
        m_ = RV.metriques(RV.charger())
        self.assertEqual(m_["total_vivant"], 16)
        # toutes les vivantes sont des échecs -> 0 candidat, c'est le signal
        self.assertEqual(m_["cette_semaine"]["candidats"], 0)


if __name__ == "__main__":
    unittest.main()
