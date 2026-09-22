"""Tests de l'accumulation order-flow (flow_events) et du garde-fou basis.

Ces briques alimentent la future backtest des signaux absorption/sweep :
une accumulation corrompue (doublons, params mélangés) invaliderait tout
verdict futur — d'où l'idempotence et la signature de paramètres.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aster_absorption import param_signature, record_events  # noqa: E402
from scripts.basis_guard import basis_pct, init_db, record_snapshots  # noqa: E402

PARAMS = dict(len_baseline=50, thr_mult=2.0, max_body_frac=0.4,
              sweep_len=20, sweep_atr_frac=0.15)


def _row(symbol="BTCUSDT", kind="sweep_low", bar_time=1790100000, interval="30m"):
    return {
        "symbol": symbol,
        "interval": interval,
        "kind": kind,
        "bar_time": bar_time,
        "close": 86000.0,
        "delta": -537.4,
        "baseline_abs_delta": 250.0,
        "depth_atr": 0.63,
        "params": param_signature(PARAMS),
    }


class FlowRecordTest(unittest.TestCase):
    def test_param_signature_changes_with_params(self):
        a = param_signature(PARAMS)
        b = dict(PARAMS, thr_mult=3.0)
        self.assertNotEqual(a, param_signature(b))
        self.assertEqual(a, param_signature(PARAMS))  # stable

    def test_record_is_idempotent(self):
        db = Path(tempfile.mkdtemp()) / "flow_test.db"
        rows = [_row(), _row(kind="absorption_buy", bar_time=1790101800)]
        self.assertEqual(record_events(rows, db), 2)
        # même fenêtre rejouée (cas nightly quotidien) : 0 doublon
        self.assertEqual(record_events(rows, db), 0)
        # paramètres différents = nouvelle famille, pas de corruption
        other = dict(_row(), params="l50_t3.0_b0.4_s20_a0.15")
        self.assertEqual(record_events([other], db), 1)

    def test_record_empty_is_noop(self):
        db = Path(tempfile.mkdtemp()) / "flow_test.db"
        self.assertEqual(record_events([], db), 0)


class BasisTest(unittest.TestCase):
    def test_basis_pct_math(self):
        self.assertAlmostEqual(basis_pct(101.0, 100.0), 1.0)
        self.assertAlmostEqual(basis_pct(99.0, 100.0), -1.0)

    def test_basis_pct_zero_binance_raises(self):
        with self.assertRaises(ValueError):
            basis_pct(100.0, 0.0)

    def test_record_snapshots_idempotent(self):
        db = Path(tempfile.mkdtemp()) / "basis_test.db"
        init_db(db)
        rows = [{"symbol": "BTCUSDT", "aster_price": 1.0, "binance_price": 1.0,
                 "basis_pct": 0.0, "captured_at": 123.0}]
        self.assertEqual(record_snapshots(rows, db), 1)
        self.assertEqual(record_snapshots(rows, db), 0)


if __name__ == "__main__":
    unittest.main()
