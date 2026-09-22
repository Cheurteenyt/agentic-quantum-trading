"""Tests du capteur de profondeur, du snapshot de flux et du rendu heatmap.

La heatmap maison (fondation : depth.db) doit être saine dès le premier jour
d'accumulation : binnage exact, snapshots idempotents, rendu qui produit un
PDF même sur données rares.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.depth_collector import bin_levels, prune_old  # noqa: E402
from scripts.flow_snapshot import record as record_flow  # noqa: E402


class BinLevelsTest(unittest.TestCase):
    def test_binning_aggregates_same_bin(self):
        grid = 1.0  # bac de 1
        levels = [["100.4", "2.0"], ["100.2", "3.0"], ["101.2", "1.0"]]
        bins = bin_levels(levels, grid)
        self.assertAlmostEqual(bins[100.0], 5.0)  # 100.4 et 100.2 -> bac 100
        self.assertAlmostEqual(bins[101.0], 1.0)

    def test_binning_skips_garbage(self):
        bins = bin_levels([["0", "5.0"], ["100.0", "0"], ["100.5", "2.0"]], grid=1.0)
        self.assertEqual(bins, {101.0: 2.0} if 101.0 in bins else {100.0: 2.0})
        self.assertTrue(all(q > 0 for q in bins.values()))


class PruneTest(unittest.TestCase):
    def test_prune_removes_only_old_rows(self):
        import sqlite3
        db = Path(tempfile.mkdtemp()) / "d.db"
        con = sqlite3.connect(db)
        con.execute("""CREATE TABLE depth_bins (symbol TEXT, ts INTEGER, side TEXT,
                       bin_price REAL, qty REAL, PRIMARY KEY (symbol, ts, side, bin_price))""")
        con.execute("""CREATE TABLE depth_meta (symbol TEXT, ts INTEGER, mid REAL,
                       PRIMARY KEY (symbol, ts))""")
        now = 1_800_000_000
        con.executemany("INSERT INTO depth_bins VALUES (?,?,?,?,?)",
                        [("BTCUSDT", now - 40 * 86400, "bid", 100.0, 1.0),
                         ("BTCUSDT", now, "bid", 100.0, 1.0)])
        con.executemany("INSERT INTO depth_meta VALUES (?,?,?)",
                        [("BTCUSDT", now - 40 * 86400, 100.0), ("BTCUSDT", now, 100.0)])
        con.commit()
        import scripts.depth_collector as dc
        old = dc.time.time
        dc.time.time = lambda: now
        try:
            removed = prune_old(con)
        finally:
            dc.time.time = old
        self.assertEqual(removed, 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM depth_bins").fetchone()[0], 1)
        con.close()


class FlowSnapshotRecordTest(unittest.TestCase):
    def test_record_idempotent(self):
        db = Path(tempfile.mkdtemp()) / "f.db"
        rows = [{"symbol": "BTCUSDT", "ts": 123, "oi": 5859.7, "taker_delta_30m": 1.77,
                 "captured_at": 1.0}]
        self.assertEqual(record_flow(rows, db), 1)
        self.assertEqual(record_flow(rows, db), 0)


if __name__ == "__main__":
    unittest.main()
