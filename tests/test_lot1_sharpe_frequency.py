"""FIX lot1 (F1) — l'annualisation du Sharpe suit la fréquence réelle des barres.

Bug prouvé : gates.sharpe() défaut 365, walkforward ne passait JAMAIS la
fréquence → les séries 1h (8760 barres/an) étaient sous-annualisées d'un
facteur sqrt(24) ≈ 4.9 dans sharpe_is / sharpe_oos / fold_sharpes.

    python tests/test_lot1_sharpe_frequency.py
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.gates import bars_per_year, sharpe  # noqa: E402
from backend.services.backtest_v2.walkforward import (  # noqa: E402
    WalkForwardConfig, run_walkforward)


RETURNS = [0.01, -0.004, 0.007, -0.002, 0.012, -0.006, 0.003, 0.005,
           -0.003, 0.008, -0.001, 0.004] * 30   # 360 barres (min folds 100/30)


class TestBarsPerYear(unittest.TestCase):
    def test_mapping_des_intervals_standards(self):
        self.assertEqual(bars_per_year(60_000), 525600)          # 1m
        self.assertEqual(bars_per_year(300_000), 105120)         # 5m
        self.assertEqual(bars_per_year(900_000), 35040)          # 15m
        self.assertEqual(bars_per_year(3_600_000), 8760)         # 1h
        self.assertEqual(bars_per_year(14_400_000), 2190)        # 4h
        self.assertEqual(bars_per_year(86_400_000), 365)         # 1d

    def test_refuse_dt_non_positif(self):
        with self.assertRaises(ValueError):
            bars_per_year(0)
        with self.assertRaises(ValueError):
            bars_per_year(-1)


class TestSharpeFrequency(unittest.TestCase):
    def test_sharpe_1h_est_sharpe_journalier_fois_racine_24(self):
        s_day = sharpe(RETURNS, periods_per_year=365)
        s_hour = sharpe(RETURNS, periods_per_year=8760)
        self.assertIsNotNone(s_day)
        self.assertAlmostEqual(s_hour, s_day * math.sqrt(8760 / 365),
                               places=10)

    def test_le_ratio_oos_is_est_insensible_a_la_frequence(self):
        """Le facteur d'annualisation se cancelle dans le ratio — mais les
        ABSOLUS sharpe_is/sharpe_oos doivent scaler."""
        wf_day = run_walkforward(RETURNS, WalkForwardConfig(anchored=False),
                                 periods_per_year=365)
        wf_hour = run_walkforward(RETURNS, WalkForwardConfig(anchored=False),
                                  periods_per_year=8760)
        self.assertAlmostEqual(wf_hour.oos_is_ratio, wf_day.oos_is_ratio,
                               places=10)
        self.assertAlmostEqual(wf_hour.sharpe_is,
                               wf_day.sharpe_is * math.sqrt(24), places=8)

    def test_walkforward_recalcule_ses_sharpes_a_la_frequence_passee(self):
        wf = run_walkforward(RETURNS, WalkForwardConfig(anchored=False),
                             periods_per_year=8760)
        all_train = [r for seg in wf.train_returns for r in seg]
        self.assertAlmostEqual(wf.sharpe_is, sharpe(all_train, 8760),
                               places=10)


if __name__ == "__main__":
    unittest.main()
