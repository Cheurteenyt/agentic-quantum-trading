"""Tests de l'univers historique (PR-5, audit GLM 5.3 №30/§35).

Le manifest est GÉNÉRÉ depuis le warehouse (zéro saisie manuelle) ; le
moteur tradable() est le masque anti-survivorship ; le runner refuse une
spec déclarant un univers incohérent.

    python tests/test_universe.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.universe as uni  # noqa: E402
from scripts import research_runner as rr  # noqa: E402

H = 3_600_000


def _db(path, days_btc=40, days_eth=10):
    """BTC observable 40 jours, ETH 10 jours (listing tardif simulé)."""
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
        rate REAL);
    """)
    for i in range(days_btc * 24):
        con.execute("INSERT INTO klines VALUES "
                    "('BTCUSDT','1h',?,100,101,99,100,1.0)", (i * H,))
    for i in range(days_eth * 24):
        con.execute("INSERT INTO klines VALUES "
                    "('ETHUSDT','1h',?,50,51,49,50,1.0)",
                    ((30 * 24 + i) * H,))   # ETH démarre au jour 30
    con.execute("INSERT INTO funding_history VALUES "
                "('BTCUSDT', ?, 0.0001)", (5 * 24 * H,))
    con.commit()
    return con


class TestUniverse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        self.con = _db(self.db)
        self._uni_dir = uni.UNIVERSE_DIR
        uni.UNIVERSE_DIR = Path(self.tmp.name) / "universe"

    def tearDown(self):
        uni.UNIVERSE_DIR = self._uni_dir
        self.con.close()
        self.tmp.cleanup()

    def test_generate_depuis_les_donnees(self):
        """Le manifest reflète les spans RÉELS — ETH listé au jour 30 est
        visible, le funding_start aussi ; zéro chiffre manuel."""
        uni.generate("test", ["BTCUSDT", "ETHUSDT"], db_path=self.db)
        m = uni.load("test")
        self.assertEqual(m["symbols"]["BTCUSDT"]["bars"], 40 * 24)
        self.assertEqual(m["symbols"]["ETHUSDT"]["bars"], 10 * 24)
        self.assertEqual(m["symbols"]["ETHUSDT"]["gaps"], 0)
        self.assertEqual(m["symbols"]["BTCUSDT"]["funding_prints"], 1)

    def test_tradable_est_le_masque_anti_survivorship(self):
        """№30 : avant le listing → NON ; dans le span → OUI ; un actif
        inconnu du manifest → JAMAIS."""
        uni.generate("test", ["BTCUSDT", "ETHUSDT"], db_path=self.db)
        m = uni.load("test")
        d0 = 0
        d10 = 10 * 24 * H
        d35 = 35 * 24 * H
        self.assertTrue(uni.tradable(m, "BTCUSDT", d0))
        self.assertFalse(uni.tradable(m, "ETHUSDT", d10))    # avant listing
        self.assertTrue(uni.tradable(m, "ETHUSDT", d35))     # après listing
        self.assertFalse(uni.tradable(m, "SOLUSDT", d35))    # inconnu

    def test_check_refuse_les_absents(self):
        uni.generate("test", ["BTCUSDT"], db_path=self.db)
        m = uni.load("test")
        missing, empty = uni.check(m, ["BTCUSDT", "SOLUSDT"])
        self.assertEqual(missing, ["SOLUSDT"])
        self.assertEqual(empty, [])

    def test_le_runner_refuse_un_univers_incoherent(self):
        """Une spec déclarant un univers où un symbole manque est refusée
        avant tout calcul (pré-enregistrement honnête)."""
        uni.generate("test", ["BTCUSDT"], db_path=self.db)
        spec = {"id": "X", "domain": "aster", "family": "f", "strategy": "s",
                "hypothesis": "h",
                "data": {"symbols": ["BTCUSDT", "ETHUSDT"], "timeframe": "1h",
                         "train_start": 0, "train_end": 1,
                         "validation_start": 1, "validation_end": 2},
                "signal": {"feature": "ret_1h", "op": "<=", "quantile": 0.5,
                           "side": -1},
                "horizons": [6], "universe": "test"}
        sp = Path(self.tmp.name) / "spec.json"
        sp.write_text(__import__("json").dumps(spec), encoding="utf-8")
        with self.assertRaises(ValueError):
            rr.load_spec(sp)

    def test_delisting_coupe_la_tradabilite(self):
        """delisted_at (à tenir à jour manuellement, signalé comme tel)
        coupe l'actif après sa mort."""
        uni.generate("test", ["BTCUSDT"], db_path=self.db)
        m = uni.load("test")
        m["symbols"]["BTCUSDT"]["delisted_at"] = "1970-01-20"
        self.assertTrue(uni.tradable(m, "BTCUSDT", 19 * 24 * H))
        self.assertFalse(uni.tradable(m, "BTCUSDT", 25 * 24 * H))


if __name__ == "__main__":
    unittest.main()
