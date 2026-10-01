"""Tests du gate fund7 de paper_forward (mécanisme P3 pré-enregistré 30/09).

Le protocole est pré-enregistré : toute régression ici change SILENCIEUSEMENT
le périmètre du gate (familles gate-d, seuil, sens de l'inégalité). L'unité
fund7 (%/8h, rate décimal ×100) est vérifiée de bout en bout sur une SQLite
synthétique en /tmp — la preuve sur prod est COUNT(fund7 > 0,005) = 32/61,
la reproduction exacte du « 32/61 à fund7 > 0,5 bps/8h » de p2.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import paper_forward as pf  # noqa: E402
from scripts.mechanism_probe import fund7_at  # noqa: E402

WIN7_MS = 7 * 24 * 3600 * 1000


class GateFund7Test(unittest.TestCase):
    def setUp(self):
        pf.GATE_STATS.update(checked=0, skipped=0)

    def test_seuil_bps_sur_l_echelle_stockee(self):
        """0,5 bps/8h = 0,005 %/8h dans l'échelle de fund7_at."""
        self.assertEqual(pf.GATE_FUND7_MIN_PCT, 0.005)
        self.assertFalse(pf.fund7_gate_pass(
            "machine_cascade_meme", "MOODENG", 0.003))   # 0,3 bp → skip
        self.assertTrue(pf.fund7_gate_pass(
            "machine_cascade_meme", "MOODENG", 0.008))   # 0,8 bp → passe
        self.assertFalse(pf.fund7_gate_pass(
            "sweep_liquidite_short", "FARTCOIN", 0.005))  # borne : ≤ → skip
        self.assertTrue(pf.fund7_gate_pass(
            "sweep_liquidite_short", "FARTCOIN", 0.0051))
        self.assertEqual(pf.GATE_STATS,
                         {"checked": 4, "skipped": 2})

    def test_fund7_absent_sans_carburant_confirme(self):
        """fund7 = 0.0 (données absentes) → skip : le gate est mécanisme."""
        self.assertFalse(pf.fund7_gate_pass("machine_cascade_meme", "X", 0.0))

    def test_familles_hors_gate(self):
        """vol_spike (fund7 méd −0,04) et flux hors sonde ne sont PAS gate-d."""
        for sig in ("machine_vol_spike_6h", "machine_cascade_majors",
                    "machine_deep_fast", "cascade_funding_rank_low",
                    "funding_extreme_contre_courant"):
            self.assertTrue(pf.fund7_gate_pass(sig, "X", -0.05), sig)
        self.assertEqual(pf.GATE_STATS["checked"], 0)

    def test_unite_fund7_bout_en_bout_sur_copie_tmp(self):
        """rate décimal 0,0001 (baseline BTC) → fund7_at = 0,01 %/8h.

        Chaîne d'unité complète sur une SQLite en /tmp : si quelqu'un
        change l'échelle de fund7_at (ou de funding_history), le seuil
        0,005 du gate devient faux — ce test le casse.
        """
        with tempfile.TemporaryDirectory() as td:
            con = sqlite3.connect(str(Path(td) / "u.db"))
            con.executescript(
                "CREATE TABLE funding_history (symbol TEXT, funding_time "
                "INTEGER, rate REAL);")
            # 7j de funding décimal à 0,0001/8h (= 1 bp/8h = 0,01 %/8h)
            rows = [("TESTUSDT", t, 0.0001)
                    for t in range(10_000_000, 10_000_000 + WIN7_MS, 8 * 3600 * 1000)]
            con.executemany("INSERT INTO funding_history VALUES (?,?,?)", rows)
            f7 = fund7_at(con, "TESTUSDT", 10_000_000 + WIN7_MS)
            self.assertAlmostEqual(f7, 0.01, places=9)   # % /8h
            # 0,005 %/8h = 0,5 bps : exactement le seuil du gate
            self.assertAlmostEqual(pf.GATE_FUND7_MIN_PCT, f7 / 2, places=12)
            con.close()


if __name__ == "__main__":
    unittest.main()
