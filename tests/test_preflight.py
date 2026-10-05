"""Tests du preflight (Research OS PR 3) — la leçon W42 en fixture.

Le crash W42 : une fonction couplée à la DB cassait malgré des imports
verts (colonne ts inexistante — la vraie colonne est open_time). Le
preflight doit attraper exactement ça AVANT qu'un slot soit engagé.

    python tests/test_preflight.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.preflight import preflight  # noqa: E402
from scripts.research_os import DataScope  # noqa: E402

H_MS = 3_600_000


def _scope():
    return DataScope("S-TEST", 0, 10 * H_MS, 10 * H_MS, 30 * H_MS)


def _good_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL,
        close_time INTEGER, snapshot_id TEXT, source TEXT, fetched_at REAL,
        taker_buy_volume REAL, quote_volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
    """)
    bars = [(0, 100, 101, 99, 100.5), (H_MS, 100.5, 101.5, 100, 101),
            (2 * H_MS, 101, 102, 100.5, 101.5), (3 * H_MS, 101.5, 102, 101, 101.8)]
    con.executemany(
        "INSERT INTO klines VALUES ('BTCUSDT', '1h', ?, ?, ?, ?, ?, 1.0, "
        "?+3599999, 'snap', 'test', 0, 0, 0)",
        [(t, o, h, l, c, t) for t, o, h, l, c in bars])
    con.execute("INSERT INTO funding_history VALUES ('BTCUSDT', ?, 0.0001)",
                (2 * H_MS,))
    con.commit()
    return con


class TestPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        self.con = _good_db(self.db)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_une_bonne_db_passe_le_preflight(self):
        res = preflight(_scope(), ["BTCUSDT"], db_path=self.db, con=self.con)
        self.assertEqual(res["verdict"], "PREFLIGHT_OK")
        self.assertTrue(all(c["ok"] for c in res["checks"]))

    def test_la_colonne_ts_inexistante_est_attrapee(self):
        """LE crash W42 : une requête sur une colonne qui n'existe pas."""
        self.con.execute("DROP TABLE klines")
        self.con.execute("CREATE TABLE klines (symbol TEXT, ts INTEGER)")
        res = preflight(_scope(), ["BTCUSDT"], db_path=self.db, con=self.con)
        self.assertEqual(res["verdict"], "PREFLIGHT_FAILED")
        self.assertTrue(any("colonnes klines" in c["check"] for c in res["checks"]))

    def test_un_symbole_sans_donnees_echoue(self):
        res = preflight(_scope(), ["BTCUSDT", "GHOSTUSDT"],
                        db_path=self.db, con=self.con)
        self.assertEqual(res["verdict"], "PREFLIGHT_FAILED")
        self.assertTrue(any("GHOSTUSDT" in c["check"] and not c["ok"]
                            for c in res["checks"]))

    def test_funding_manquant_echoue(self):
        self.con.execute("DELETE FROM funding_history")
        res = preflight(_scope(), ["BTCUSDT"], db_path=self.db, con=self.con)
        self.assertEqual(res["verdict"], "PREFLIGHT_FAILED")

    def test_une_db_absolue_est_unechec(self):
        res = preflight(_scope(), ["BTCUSDT"],
                        db_path=self.db.parent / "inexistante.db",
                        con=None)
        self.assertEqual(res["verdict"], "PREFLIGHT_FAILED")


if __name__ == "__main__":
    import tempfile
    unittest.main()
