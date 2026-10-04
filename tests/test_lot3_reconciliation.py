"""FIX lot3 (F2) — LA RÉCONCILIATION coûts ↔ courbe d'equity.

Bug prouvé : le CostBreakdown rapportait fees + funding + slippage en USD
mais la courbe (bar_ret → equity → Sharpe/DD) ne portait que les fees —
le slippage d'AUCUNE stratégie et le funding de 2/3 n'y entraient jamais.
La comptabilité est maintenant unique : les fractions bookées dans la
courbe et les USD du rapport viennent du MÊME calcul par trade
(USD == fraction × BOOK_NOTIONAL_USD, exactement ; les charges sont
SIGNÉES négatives, conventions round_trip_fees_usd / slippage_usd /
funding_cost_usd).

    python tests/test_lot3_reconciliation.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.costs import (  # noqa: E402
    CostDataUnavailable, FundingRate)


def _load(name, rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mom = _load("_mom_lot3", "backend/services/backtest_v2/strategies/momentum.py")

PARAMS = {"fast_ema": 8, "slow_ema": 40, "regime_ema": 120,
          "allow_short": True, "stop_bps": 500, "take_bps": 100_000,
          "max_leverage": 3}


def _bar(i, o, h, l, c):
    return Bar(ts=i * 3_600_000, open=o, high=h, low=l, close=c, volume=100.0)


def _flat_bars():
    # prix plat : les jambes de prix sont nulles, ne restent que les coûts
    return [_bar(i, 100, 100.01, 99.99, 100) for i in range(4)]


def _fake_rate():
    return FundingRate(symbol="BTCUSDT", avg_bps_per_8h=1.0, sample_count=10,
                       last_funding_time_ms=0, cached_at=time.time(),
                       interval_hours=8.0)


class TestReconciliation(unittest.TestCase):
    def setUp(self):
        # cache funding stubbé : 1 bp/8h — un long de 2 barres paie
        mom.load_funding_rate = lambda symbol, cache_path=None: _fake_rate()

    def test_la_courbe_porte_le_funding_et_le_slippage(self):
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        ev = mom.evaluate(dict(PARAMS), _flat_bars())
        br = list(ev.bar_returns_per_bar)
        book = mom.BOOK_NOTIONAL_USD
        fund_frac = ev.costs.funding_usd / book       # signé : long paie < 0
        slip_frac = ev.costs.slippage_usd / book      # charge signée < 0
        self.assertLess(fund_frac, 0)
        self.assertLess(slip_frac, 0)
        # la barre de sortie porte exactement funding + slippage (+ la fee)
        self.assertAlmostEqual(br[3] + mom.FEE_FRACTION_PER_FILL,
                               fund_frac + slip_frac, places=15)

    def test_le_net_du_trade_reconcile_avec_le_rapport(self):
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        ev = mom.evaluate(dict(PARAMS), _flat_bars())
        book = mom.BOOK_NOTIONAL_USD
        # jambes de prix nulles : net = funding + slippage - fees (tout signé)
        self.assertAlmostEqual(
            ev.trade_returns[0],
            ev.costs.funding_usd / book + ev.costs.slippage_usd / book
            - mom.FEE_FRACTION_ROUND_TRIP, places=15)

    def test_un_short_encaisse_le_funding_dans_sa_courbe(self):
        mom.compute_signals = lambda b, p: [-1, -1, 0, 0]
        ev = mom.evaluate(dict(PARAMS), _flat_bars())
        br = list(ev.bar_returns_per_bar)
        fund_frac = ev.costs.funding_usd / mom.BOOK_NOTIONAL_USD
        self.assertGreater(fund_frac, 0)       # un short encaisse
        self.assertAlmostEqual(br[3] + mom.FEE_FRACTION_PER_FILL,
                               fund_frac
                               + ev.costs.slippage_usd / mom.BOOK_NOTIONAL_USD,
                               places=15)

    def test_equity_finale_reconcile_les_parties(self):
        """Le test d'or : equity = (1-fee_entry) × (1-fee_exit + fund + slip)."""
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        ev = mom.evaluate(dict(PARAMS), _flat_bars())
        book = mom.BOOK_NOTIONAL_USD
        fee = mom.FEE_FRACTION_PER_FILL
        expected = (1 - fee) * (1 - fee + ev.costs.funding_usd / book
                                + ev.costs.slippage_usd / book)
        # AVANT le fix : le niveau était (1-fee)² — slippage et funding
        # étaient invisibles. La courbe mord maintenant :
        self.assertLess(ev.equity_curve[-1], (1 - fee) ** 2)
        self.assertAlmostEqual(ev.equity_curve[-1], expected, places=12)

    def test_sans_cache_funding_le_zero_est_explicite(self):
        def _no_cache(symbol, cache_path=None):
            raise CostDataUnavailable("pas de cache")
        mom.load_funding_rate = _no_cache
        mom.compute_signals = lambda b, p: [1, 1, 0, 0]
        ev = mom.evaluate(dict(PARAMS), _flat_bars())
        self.assertEqual(ev.costs.funding_usd, 0.0)   # 0.0 EXPLICITE
        self.assertLess(ev.costs.slippage_usd, 0.0)   # le slippage, lui, mord


class TestFundingFadeSlippage(unittest.TestCase):
    def test_le_slippage_entre_dans_la_courbe_et_le_net(self):
        ff = _load("_ff_lot3", "backend/services/backtest_v2/strategies/funding_fade.py")
        bars = _flat_bars()
        injected = [0.0] * len(bars)   # funding neutre : ne reste que les coûts
        ff.compute_signals = lambda b, p, s: [1, 1, 0, 0]
        params = dict(PARAMS, lookback=100, entry_z=1.5, exit_z=0.3,
                      funding_bps_series=injected)
        ev = ff.evaluate(params, bars)
        book = ff.BOOK_NOTIONAL_USD
        slip_frac = ev.costs.slippage_usd / book
        self.assertLess(slip_frac, 0)
        self.assertEqual(len(ev.trade_returns), 1)
        # net = 0 (prix) + 0 (funding neutre) + slip_frac - fee_rt
        self.assertAlmostEqual(
            ev.trade_returns[0], slip_frac - ff.FEE_FRACTION_ROUND_TRIP,
            places=12)


if __name__ == "__main__":
    unittest.main()
