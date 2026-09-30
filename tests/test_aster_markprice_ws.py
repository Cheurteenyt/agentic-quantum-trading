#!/usr/bin/env python3
"""Tests du collecteur premium WS (aster_markprice_ws) — parse des frames
!markPrice@arr, throttle 1/min/symbole, flush batch (2026-09-30)."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import aster_markprice_ws as mp

FRAME = ('[{"e":"markPriceUpdate","E":1790725500000,"s":"BTCUSDT",'
         '"p":"11794.15","i":"11784.62659091","P":"11784.25","r":"0.00038167",'
         '"T":1790736000000},'
         '{"e":"markPriceUpdate","E":1790725500000,"s":"HORS PARC",'
         '"p":"1.0","i":"1.0","r":"0.0001","T":1790736000000}]')


class TestParseFrame(unittest.TestCase):
    def test_tableau_nu(self):
        rows = mp.parse_frame(FRAME)
        self.assertEqual(len(rows), 2)
        btc = rows[0]
        self.assertEqual(btc["symbol"], "BTCUSDT")
        self.assertAlmostEqual(btc["mark"], 11794.15)
        self.assertAlmostEqual(btc["idx"], 11784.62659091)
        self.assertAlmostEqual(btc["rate"], 0.00038167)
        self.assertEqual(btc["next_funding_ms"], 1790736000000)
        # la prime = mark/index - 1, en %
        self.assertAlmostEqual(btc["prem"],
                               (11794.15 / 11784.62659091 - 1) * 100, places=4)

    def test_combined_stream(self):
        import json
        msg = json.dumps({"stream": "!markPrice@arr", "data": json.loads(FRAME)})
        self.assertEqual(len(mp.parse_frame(msg)), 2)

    def test_frame_corrompu(self):
        self.assertEqual(mp.parse_frame("pas du json"), [])
        self.assertEqual(mp.parse_frame('{"e":"x"}'), [])
        self.assertEqual(mp.parse_frame('[{"s":"BTCUSDT"}]'), [])  # clés manquantes


class TestThrottle(unittest.TestCase):
    ROWS = [{"symbol": "BTCUSDT", "mark": 1.0, "idx": 1.0, "prem": 0.0,
             "rate": 0.0, "next_funding_ms": 0, "captured_at_ms": 0}]

    def test_un_premier_puis_rien_puis_ok(self):
        last: dict[str, float] = {}
        self.assertEqual(len(mp.select_samples(self.ROWS, last, now_s=100.0)), 1)
        self.assertEqual(len(mp.select_samples(self.ROWS, last, now_s=159.0)), 0)
        self.assertEqual(len(mp.select_samples(self.ROWS, last, now_s=160.5)), 1)

    def test_symboles_independants(self):
        last: dict[str, float] = {}
        r2 = [dict(self.ROWS[0], symbol="ETHUSDT")]
        mp.select_samples(self.ROWS, last, now_s=100.0)
        self.assertEqual(len(mp.select_samples(r2, last, now_s=100.5)), 1)


class TestStore(unittest.TestCase):
    def test_flush_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = mp.DB_PATH
            mp.DB_PATH = Path(tmp) / "t.db"
            try:
                con = sqlite3.connect(str(mp.DB_PATH))
                con.execute("""CREATE TABLE premium_history (
                    symbol TEXT, mark_price REAL, index_price REAL,
                    premium_pct REAL, last_funding_rate REAL,
                    next_funding_time_ms INTEGER, captured_at_ms INTEGER,
                    PRIMARY KEY (symbol, captured_at_ms))""")
                con.commit()
                con.close()
                row = {"symbol": "BTCUSDT", "mark": 11794.15,
                       "idx": 11784.62659091, "prem": 0.0808,
                       "rate": 0.00038167, "next_funding_ms": 1790736000000,
                       "captured_at_ms": 1790725500000}
                self.assertEqual(mp.store([]), 0)   # 0 txn pour rien
                self.assertEqual(mp.store([row]), 1)
                self.assertEqual(mp.store([row]), 1)  # OR REPLACE : pas d'erreur
                con = sqlite3.connect(str(mp.DB_PATH))
                n, mark = con.execute(
                    "SELECT COUNT(*), mark_price FROM premium_history"
                ).fetchone()
                con.close()
                self.assertEqual(n, 1)
                self.assertAlmostEqual(mark, 11794.15)
            finally:
                mp.DB_PATH = old


class TestSymbols(unittest.TestCase):
    def test_parc_charge(self):
        self.assertGreaterEqual(len(mp.load_symbols()), 12)
        self.assertIn("BTCUSDT", mp.load_symbols())


if __name__ == "__main__":
    unittest.main()
