"""C2bis (bug-hunter ronde 4) — le forward applique la règle d'ÈRE du
kernel (PR-166) : une fenêtre qui straddle le PREMIER print funding est
INCONNUE, pas « 0 connu avec un partiel ».

Le kernel (label_matrix, PR-166) : « connu = commencé après le premier
print, point ». Le forward gardait la clause `or (k1 > k0)` (supprimée du
kernel) : ses trades pré-listing-funding étaient fund_known=True avec un
funding PARTIEL présenté comme complet — le gate de maturation
fund_known_pct (>= 95 %) maturait READY sur une couverture que le
protocole backtest aurait comptée inconnue, et les rets forward incluaient
un funding non comparable au discovery_mean (gate vs_pass).

    python tests/test_c2bis_forward_fund_era.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_forward as rf  # noqa: E402

H_MS = 3_600_000
NOW_MS = 200 * H_MS


def _db(path: Path):
    """Barres plates 1h (0..199) ; premier print funding à 8 h, puis
    tous les 8 h. La fenêtre (4 h, 10 h] du trade straddle le 1er print."""
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
    """)
    for i in range(200):
        con.execute("INSERT INTO klines VALUES "
                    "('BTCUSDT','1h',?,100.0,100.1,99.9,100.0,1.0)",
                    (i * H_MS,))
    for k in range(8, 200, 8):
        con.execute("INSERT INTO funding_history VALUES "
                    "('BTCUSDT', ?, 0.0001)", (k * H_MS,))
    con.commit()
    return con


SPEC = {
    "id": "EXP-c2bis", "domain": "aster", "family": "forced_flow",
    "strategy": "fwd-test", "hypothesis": "ère funding straddle",
    "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
             "train_start": 0, "train_end": 50 * H_MS,
             "validation_start": 50 * H_MS, "validation_end": 100 * H_MS},
    "signal": {"feature": "ret_1h", "op": "<=", "threshold": -1.0,
               "side": -1},
    "horizons": [6], "cost_pct": 0.0, "criteria": {"min_n": 5},
    "mode": "confirmation",
}


class TestFundEraForward(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        _db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _closed(self, events):
        return rf._closed_trades(SPEC, events, self.db, NOW_MS)

    def test_fenetre_straddle_premier_print_inconnue(self):
        # open 4 h, horizon 6 h -> fenêtre (4 h, 10 h] : le 1er print (8 h)
        # est DANS la fenêtre mais la fenêtre COMMENCE avant. Règle PR-166
        # du kernel : connu = commencé après le premier print, point.
        # PRÉ-FIX : la clause or (k1 > k0) rendait ce trade fund_known=True
        # avec un partiel (le print 8 h) présenté comme complet.
        events = [{"symbol": "BTCUSDT", "open_time_ms": 4 * H_MS,
                   "side": -1, "horizon_h": 6, "entry_open": 100.0}]
        trades = self._closed(events)
        self.assertEqual(len(trades), 1)
        self.assertFalse(trades[0]["fund_known"],
                         "une fenêtre qui straddle le 1er print est "
                         "INCONNUE (règle kernel PR-166), jamais « 0 "
                         "connu avec un partiel »")
        self.assertIsNone(trades[0]["fund_pct"])
        self.assertEqual(trades[0]["fund_prints"], [])

    def test_fenetre_post_1er_print_connu(self):
        # contrôle positif : open 10 h, fenêtre (10 h, 16 h] — commencée
        # APRÈS le 1er print, contenant le print 16 h : connu, le print
        # 16 h est accrû
        events = [{"symbol": "BTCUSDT", "open_time_ms": 10 * H_MS,
                   "side": -1, "horizon_h": 6, "entry_open": 100.0}]
        trades = self._closed(events)
        self.assertEqual(len(trades), 1)
        self.assertTrue(trades[0]["fund_known"])
        self.assertAlmostEqual(trades[0]["fund_pct"], 0.01, places=9)
        self.assertEqual([p[0] for p in trades[0]["fund_prints"]],
                         [16 * H_MS])

    def test_fenetre_avant_premier_print_inconnue(self):
        # open 2 h, fenêtre (2 h, 8 h] : AUCUN print (le 1er est à 8 h,
        # exclusif de la borne droite) ni straddle ni contenu : inconnu
        events = [{"symbol": "BTCUSDT", "open_time_ms": 2 * H_MS,
                   "side": -1, "horizon_h": 6, "entry_open": 100.0}]
        trades = self._closed(events)
        self.assertEqual(len(trades), 1)
        self.assertFalse(trades[0]["fund_known"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
