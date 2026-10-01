"""Tests du ledger papier des survivants T21 (scripts/aster_survivors_forward.py).

Contrat du moteur (sémantique T21, one-shot scripts/studies/aster_discovery_2123.py) :
entrée au close t -> exécutée à l'OPEN t+1 ; stop PRIORITAIRE intrabar au prix
du stop ; exit signal / time-stop à l'open SUIVANT du barre de décision
(entry_idx + hold + 1 pour un hold de N barres) ; un signal persistant
ré-entre dès que le slot est libre ; idempotence par clé naturelle
UNIQUE(strategy, symbol, entry_ts), jamais de réécriture d'une ligne closed.
Toute régression ici corrompt le verdict 90 j en silence.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aster_survivors_forward import (  # noqa: E402
    COST_RT, STRATEGIES, ensure_schema, replay_key, signal_arrays, sync_trades,
)

HOUR_MS = 3_600_000


def _mk(closes: list[float], t0: int = 1_700_000_000_000):
    """Barres factices 1h : o = close précédent, mèches ±0.1 autour du corps."""
    ts = np.array([t0 + i * HOUR_MS for i in range(len(closes))], dtype="int64")
    c = np.array(closes, dtype=float)
    o = np.empty_like(c)
    o[0] = closes[0]
    o[1:] = c[:-1]
    h = np.maximum(o, c) + 0.1
    l = np.minimum(o, c) - 0.1
    return ts, o, h, l


def _replay(closes, cfg_key, open_row=None, started_ms=0):
    ts, o, h, l = _mk(closes)
    df = pd.DataFrame({"ts": ts, "open": o, "high": h, "low": l,
                       "close": np.asarray(closes, dtype=float)})
    cfg = STRATEGIES[cfg_key]
    sig = signal_arrays(df, cfg)
    trades = replay_key(ts, o, h, l, sig, cfg, open_row, started_ms)
    return trades, sig, ts, o, h, l


class BreakoutTest(unittest.TestCase):
    CLOSES = [100.0] * 295 + [101.5, 101.4, 100.5, 100.4, 100.5]

    def test_entry_open_t1_et_stop_intrabar(self):
        trades, sig, ts, o, h, l = _replay(self.CLOSES, "breakout_don168")
        fs = int(np.argmax(sig["enter_long"]))
        self.assertTrue(sig["enter_long"][fs], "la cassure doit armer un signal long")
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t["direction"], "long")
        self.assertEqual(t["entry_ts"], int(ts[fs + 1]))
        self.assertEqual(t["entry_price"], float(o[fs + 1]))
        self.assertAlmostEqual(t["stop"], o[fs + 1] - 3.0 * sig["atr"][fs], places=9)
        self.assertEqual(t["status"], "closed")
        self.assertEqual(t["exit_reason"], "stop")
        self.assertEqual(t["exit_price"], t["stop"])
        eb = next(i for i in range(fs + 1, len(self.CLOSES)) if l[i] <= t["stop"])
        self.assertEqual(t["exit_ts"], int(ts[eb]))
        self.assertAlmostEqual(
            t["ret_pct"], (t["exit_price"] / t["entry_price"] - 1) * 100 - COST_RT * 100, places=9)

    def test_started_ms_gate_bloque_l_historique(self):
        ts = _mk(self.CLOSES)[0]
        trades, *_ = _replay(self.CLOSES, "breakout_don168", started_ms=int(ts[-1]))
        self.assertEqual(trades, [], "aucune entrée ne doit précéder started_ms")


class MomentumTest(unittest.TestCase):
    # 848 barres à 100, 3 barres de crash (95, 92, 90) puis flat : le signal
    # short persiste (ret48 = -10 % pendant 48 barres) -> trade 1 (time-stop,
    # entré à 95 AVANT le plancher) puis ré-entrée immédiate (slot libre)
    # encore ouverte en fin de fenêtre.
    CLOSES = [100.0] * 848 + [95.0, 92.0, 90.0] + [90.0] * 49

    def test_short_time_stop_puis_reentree(self):
        trades, sig, ts, o, *_ = _replay(self.CLOSES, "momentum_bear_lb48")
        fs = int(np.argmax(sig["enter_short"]))
        self.assertTrue(sig["enter_short"][fs])
        self.assertEqual(len(trades), 2)
        t = trades[0]
        self.assertEqual(t["direction"], "short")
        self.assertEqual(t["entry_ts"], int(ts[fs + 1]))
        self.assertEqual(t["entry_price"], float(o[fs + 1]))
        self.assertAlmostEqual(t["stop"], o[fs + 1] + 3.0 * sig["atr"][fs], places=9)
        self.assertEqual(t["horizon"], 24)
        self.assertEqual(t["exit_reason"], "time")
        self.assertEqual(t["exit_ts"], int(ts[fs + 1 + 24 + 1]))
        self.assertEqual(t["exit_price"], float(o[fs + 1 + 24 + 1]))
        self.assertGreater(t["ret_pct"], 0, "short encaissé au crash : l'exit time doit être gagnant")
        self.assertEqual(trades[1]["status"], "open")
        self.assertEqual(trades[1]["entry_ts"], int(ts[fs + 27]))


class DeterminismTest(unittest.TestCase):
    def test_replay_deterministe(self):
        t1, *_ = _replay(BreakoutTest.CLOSES, "breakout_don168")
        t2, *_ = _replay(BreakoutTest.CLOSES, "breakout_don168")
        self.assertEqual(t1, t2)


class SyncTest(unittest.TestCase):
    CLOSES = MomentumTest.CLOSES

    def _db(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        ensure_schema(con)
        return con

    def test_open_puis_close_sans_duplication(self):
        con = self._db()
        # tir 1 : fenêtre tronquée avant la barre de time-stop -> position open
        t1, sig, ts, *_ = _replay(self.CLOSES[:873], "momentum_bear_lb48")
        self.assertEqual(len(t1), 1)
        self.assertEqual(t1[0]["status"], "open", "hold 24 non échu : la ligne doit rester open")
        self.assertEqual(sync_trades(con, "momentum_bear_lb48", "TESTUSDT", t1, 111), (1, 0))
        # tir 2 : mêmes barres -> idempotence, zéro nouvelle ligne
        self.assertEqual(sync_trades(con, "momentum_bear_lb48", "TESTUSDT", t1, 222), (0, 0))
        self.assertEqual(con.execute(
            "SELECT COUNT(*) FROM aster_survivors_paper").fetchone()[0], 1)
        # tir 3 : fenêtre complète -> UPDATE open->closed + ré-entrée insérée
        t3, *_ = _replay(self.CLOSES, "momentum_bear_lb48")
        self.assertEqual(sync_trades(con, "momentum_bear_lb48", "TESTUSDT", t3, 333), (1, 1))
        rows = con.execute("SELECT * FROM aster_survivors_paper ORDER BY entry_ts").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]["status"], rows[0]["exit_reason"]), ("closed", "time"))
        self.assertEqual(rows[0]["captured_at"], 111, "captured_at d'entrée jamais réécrit")
        self.assertEqual(rows[1]["status"], "open")

    def test_un_slot_par_strategie(self):
        con = self._db()
        t_open = {"direction": "long", "entry_ts": 1, "entry_price": 100.0, "stop": 95.0,
                  "horizon": None, "exit_ts": None, "exit_price": None, "exit_reason": None,
                  "ret_pct": None, "status": "open"}
        sync_trades(con, "trend_long_ema50x200", "TESTUSDT", [t_open], 1)
        sync_trades(con, "trend_long_ema50x200", "TESTUSDT", [dict(t_open, entry_ts=2)], 2)
        self.assertEqual(con.execute(
            "SELECT COUNT(*) FROM aster_survivors_paper WHERE status='open'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
