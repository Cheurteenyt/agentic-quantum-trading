"""FIX lot2 — F7 (gap de stop), F6 (MAE réel), F14 (algèbre benchmark).

Bugs prouvés par l'audit :
- F7 : un gap d'ouverture au-delà du stop remplissait AU PRIX DU STOP
  (impossible — le prix n'y est jamais passé) ; le modèle taker_market
  doit exécuter à l'open disponible.
- F6 : check_liquidation recevait la distance du SUPPOSÉ stop comme MAE ;
  le MAE doit venir du chemin réellement observé, gaps compris.
- F14 : le moteur comparait sum(trade_returns) (stratégie) au composé
  prod(1+r)-1 (benchmarks) — deux algèbres pour le même gate.

    python tests/test_lot2_engine_fixes.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import (  # noqa: E402
    Bar, BaselineTrade, _build_result, compounded_total_return)


def _load(name, rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mom = _load("_mom_lot2", "backend/services/backtest_v2/strategies/momentum.py")

PARAMS = {"fast_ema": 8, "slow_ema": 40, "regime_ema": 120,
          "allow_short": True, "stop_bps": 500, "take_bps": 100_000,
          "max_leverage": 3}


def _bar(i, o, h, l, c):
    return Bar(ts=i * 3_600_000, open=o, high=h, low=l, close=c, volume=100.0)


class TestStopGap(unittest.TestCase):
    """F7 : le fill de stop ne peut pas être meilleur que l'open gapé."""

    def test_long_gap_sous_le_stop_remplit_a_l_open(self):
        bars = [_bar(0, 100, 101, 99, 100),
                _bar(1, 100, 101, 99.5, 100.5),
                _bar(2, 94, 94.5, 93, 93.5),      # open 94 < stop 95 : GAP
                _bar(3, 93, 94, 92, 93)]
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        trades, _ = mom.simulate(bars, PARAMS)
        self.assertEqual(trades[0].reason, "stop")
        self.assertEqual(trades[0].exit_price, 94.0)      # AVANT le fix : 95.0
        self.assertAlmostEqual(trades[0].gross_return, -0.06)

    def test_short_gap_au_dessus_du_stop_remplit_a_l_open(self):
        bars = [_bar(0, 100, 101, 99, 100),
                _bar(1, 100, 100.5, 99, 100),
                _bar(2, 106, 107, 105.5, 106.5),  # open 106 > stop 105 : GAP
                _bar(3, 106, 107, 105, 106)]
        mom.compute_signals = lambda b, p: [-1, -1, 0, 0]
        trades, _ = mom.simulate(bars, PARAMS)
        self.assertEqual(trades[0].reason, "stop")
        self.assertEqual(trades[0].exit_price, 106.0)     # AVANT le fix : 105.0
        self.assertAlmostEqual(trades[0].gross_return, -0.06)

    def test_stop_intrabar_sans_gap_inchangen(self):
        bars = [_bar(0, 100, 101, 99, 100),
                _bar(1, 100, 101, 99.5, 100.5),
                _bar(2, 99.5, 100, 94.5, 95),     # low 94.5 <= stop 95, pas de gap
                _bar(3, 95, 96, 94, 95)]
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        trades, _ = mom.simulate(bars, PARAMS)
        self.assertEqual(trades[0].reason, "stop")
        self.assertEqual(trades[0].exit_price, 95.0)


class TestMaeReel(unittest.TestCase):
    """F6 : worst_adverse_pct vient du chemin observé, pas du stop supposé."""

    def test_le_gap_depasse_le_stop_dans_le_mae(self):
        bars = [_bar(0, 100, 101, 99, 100),
                _bar(1, 100, 101, 99.5, 100.5),
                _bar(2, 94, 94.5, 93, 93.5),
                _bar(3, 93, 94, 92, 93)]
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        trades, _ = mom.simulate(bars, PARAMS)
        # AVANT le fix, le MAE rapporté = stop = 5 % ; réel : le fill à 94.
        self.assertAlmostEqual(trades[0].worst_adverse_pct, 0.06)

    def test_stop_intrabar_mae_egale_la_distance_du_stop(self):
        bars = [_bar(0, 100, 101, 99, 100),
                _bar(1, 100, 101, 99.5, 100.5),
                _bar(2, 99.5, 100, 94.5, 95),
                _bar(3, 95, 96, 94, 95)]
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        trades, _ = mom.simulate(bars, PARAMS)
        self.assertAlmostEqual(trades[0].worst_adverse_pct, 0.05)

    def test_un_gagnant_porte_son_pire_creux(self):
        bars = [_bar(0, 100, 101, 99, 100),
                _bar(1, 100, 101, 99.5, 100.5),
                _bar(2, 100.5, 101, 98.5, 100.5),  # creux à -1,5 % sans stop
                _bar(3, 105, 105.5, 104, 104.5)]   # sortie reverse à 105
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        trades, _ = mom.simulate(bars, PARAMS)
        self.assertEqual(trades[0].reason, "reverse")
        self.assertAlmostEqual(trades[0].worst_adverse_pct, 0.015)


class TestAlgebreBenchmark(unittest.TestCase):
    """F14 : UNE seule algèbre — composée, jamais la somme."""

    def test_compose_deux_fois_10_pct_vaut_21_pct(self):
        self.assertAlmostEqual(compounded_total_return([0.1, 0.1]), 0.21)
        self.assertNotEqual(sum([0.1, 0.1]), 0.21)   # l'ancienne algèbre

    def test_vide_et_negatifs(self):
        self.assertEqual(compounded_total_return([]), 0.0)
        self.assertAlmostEqual(compounded_total_return([-0.5, -0.5]), -0.75)

    def test_build_result_utilise_le_compose(self):
        trades = [BaselineTrade(0, 1, "long", 0.1, 0.1),
                  BaselineTrade(1, 2, "long", 0.1, 0.1)]
        self.assertAlmostEqual(_build_result("t", trades).total_return, 0.21)


if __name__ == "__main__":
    unittest.main()
