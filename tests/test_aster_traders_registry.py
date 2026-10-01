#!/usr/bin/env python3
"""Les tests du registre longitudinal des traders Aster (scripts/
aster_traders_registry.py) — les fonctions pures + le fix DDL-avant-état
(le crash 30/09 21:06 : la lecture d'état sur une base vierge)."""
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import aster_traders_registry as reg


class CastTests(unittest.TestCase):
    def test_rank_string_cast(self):
        # le piège T2 : rank arrive en STRING côté API
        self.assertEqual(reg.to_i("1"), 1)
        self.assertEqual(reg.to_i(" 42 "), 42)

    def test_rank_invalide(self):
        self.assertIsNone(reg.to_i(None))
        self.assertIsNone(reg.to_i("abc"))
        self.assertIsNone(reg.to_i(""))

    def test_volume_zero_legitime(self):
        # le piège T2 : volume=0 est LÉGITIME (45/400 lignes du sort pnl_rank)
        self.assertEqual(reg.to_f(0), 0.0)
        self.assertEqual(reg.to_f("0"), 0.0)

    def test_valeur_absente(self):
        self.assertIsNone(reg.to_f(None))
        self.assertIsNone(reg.to_f(""))


class StreakTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 30)

    def test_streak_consecutif(self):
        days = {}
        for i in range(7):
            d = (self.today - timedelta(days=i)).isoformat()
            days.setdefault("WALLET1", set()).add(d)
        self.assertEqual(reg.streak_days(days, "WALLET1", self.today), 7)

    def test_streak_casse(self):
        days = {}
        for i in (0, 1, 2, 4, 5):  # le trou au jour 3
            d = (self.today - timedelta(days=i)).isoformat()
            days.setdefault("WALLET2", set()).add(d)
        self.assertEqual(reg.streak_days(days, "WALLET2", self.today), 3)

    def test_inconnu(self):
        self.assertEqual(reg.streak_days({}, "WALLETX", self.today), 1)


class DDLFirstTests(unittest.TestCase):
    def test_ddl_avant_etat_sur_base_vierge(self):
        # le crash 30/09 21:06 : la lecture d'état AVANT le DDL sur une base
        # vierge levait « no such table: aster_traders » — le DDL doit
        # précéder toute lecture
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "klines.db"
            con = sqlite3.connect(str(db))
            con.execute("PRAGMA busy_timeout=45000")
            con.execute(reg.DDL)  # l'ordre corrigé : le DDL d'abord
            row = con.execute(
                "SELECT MAX(captured_day) FROM aster_traders").fetchone()[0]
            self.assertIsNone(row)  # la table vide lit None, ne lève plus
            con.close()


if __name__ == "__main__":
    unittest.main()
