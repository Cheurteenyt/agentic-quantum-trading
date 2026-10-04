"""FIX audit v3 (C1/C2/C6) — L'INVARIANCE DES PRINTS FUTURS.

Le test que l'audit réclamait : changer tous les prints de funding
postérieurs à une entrée ne doit strictement rien changer à ce trade —
ni à son coût, ni à son sens, ni à sa décision. np.interp et la moyenne
du cache violaient tous deux cette invariance ; l'as-of strict la garantit
par construction.

    python tests/test_lot4_funding_causality.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from scripts.funding_series import FundingSeries  # noqa: E402

H_MS = 3_600_000.0


def _load(name, rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mom = _load("_mom_causality", "backend/services/backtest_v2/strategies/momentum.py")
carry = _load("_carry_causality", "backend/services/backtest_v2/strategies/funding_carry.py")

PARAMS = {"fast_ema": 8, "slow_ema": 40, "regime_ema": 120,
          "allow_short": True, "stop_bps": 500, "take_bps": 100_000,
          "max_leverage": 3}


def _bar(i, o, h, l, c):
    return Bar(ts=i * H_MS, open=o, high=h, low=l, close=c, volume=100.0)


def _series(past, future):
    """past = [(t_ms, rate)] avant la fin du backtest ; future = les prints
    qu'on mutera — ils ne doivent rien changer aux décisions passées."""
    return FundingSeries.from_rows(list(past) + list(future))


class TestRateAsof(unittest.TestCase):
    def test_un_print_futur_ne_change_rien(self):
        s1 = FundingSeries.from_rows([(1 * H_MS, 0.0001), (9 * H_MS, 0.0009)])
        s2 = FundingSeries.from_rows([(1 * H_MS, 0.0001), (9 * H_MS, -0.0099)])
        # la décision à 2h voit exactement le même taux, quel que soit le futur
        self.assertEqual(s1.rate_asof(2 * H_MS), s2.rate_asof(2 * H_MS))
        self.assertAlmostEqual(s1.rate_asof(2 * H_MS), 0.01)

    def test_aucun_print_avant_le_debut(self):
        s = FundingSeries.from_rows([(5 * H_MS, 0.0001)])
        self.assertIsNone(s.rate_asof(1 * H_MS))


class TestMomentumFundingInvariance(unittest.TestCase):
    BARS = [_bar(0, 100, 100.01, 99.99, 100),
            _bar(1, 100, 100.5, 99.5, 101),
            _bar(2, 101, 101.5, 100.5, 101),
            _bar(3, 101, 101.5, 100.5, 101),
            _bar(4, 101, 101.5, 100.5, 101)]

    def setUp(self):
        mom.compute_signals = lambda b, p: [1, 1, 0, 0, 0]

    def test_mutuer_les_prints_futurs_ne_change_rien_au_trade(self):
        past = [(1.5 * H_MS, 0.0001), (2.5 * H_MS, 0.0002)]
        mom.load_funding_series = lambda symbol, db_path=None: _series(
            past, [(99 * H_MS, 0.999)])
        ev1 = mom.evaluate(dict(PARAMS), list(self.BARS))
        mom.load_funding_series = lambda symbol, db_path=None: _series(
            past, [(99 * H_MS, -0.5)])
        ev2 = mom.evaluate(dict(PARAMS), list(self.BARS))
        self.assertEqual(ev1.trade_returns, ev2.trade_returns)
        self.assertEqual(ev1.costs.funding_usd, ev2.costs.funding_usd)
        self.assertNotEqual(ev1.costs.funding_usd, 0.0)  # le coût est réel


class TestCarrySideAsof(unittest.TestCase):
    """C2 : le sens collecteur est décidé AS-OF — un funding qui change de
    signe inverse la position ; le futur ne décide pas du passé."""

    BARS = [_bar(i, 100, 100.5, 99.5, 100) for i in range(12)]

    def test_le_side_se_renverse_avec_le_funding_asof(self):
        # positif jusqu'à 5h (short collecte), négatif ensuite (long collecte)
        s = FundingSeries.from_rows(
            [(1 * H_MS, 0.0002), (5 * H_MS, -0.0002), (11 * H_MS, -0.0002)])
        carry.load_funding_series = lambda symbol, db_path=None: s
        ev = carry.evaluate(dict(carry.PARAM_SPACE_FALLBACK) if False
                            else {"hold_max_bars": 3, "stop_bps": 100_000,
                                  "max_leverage": 3, "allow_short": True},
                            list(self.BARS))
        sides = {t.side for t in _trades_of(ev)}
        self.assertIn(-1, sides)   # du short tôt (funding positif)
        self.assertIn(1, sides)    # du long tard (funding négatif)

    def test_le_futur_ne_change_rien_aux_trades_passes(self):
        s_past = [(1 * H_MS, 0.0002), (5 * H_MS, -0.0002)]
        carry.load_funding_series = lambda symbol, db_path=None: _series(
            s_past, [(99 * H_MS, 0.9)])
        ev1 = carry.evaluate({"hold_max_bars": 3, "stop_bps": 100_000,
                              "max_leverage": 3, "allow_short": True},
                             list(self.BARS))
        carry.load_funding_series = lambda symbol, db_path=None: _series(
            s_past, [(99 * H_MS, -0.9)])
        ev2 = carry.evaluate({"hold_max_bars": 3, "stop_bps": 100_000,
                              "max_leverage": 3, "allow_short": True},
                             list(self.BARS))
        self.assertEqual([t.side for t in _trades_of(ev1)],
                         [t.side for t in _trades_of(ev2)])
        self.assertEqual(ev1.trade_returns, ev2.trade_returns)


def _trades_of(ev):
    """Les trades reconstruits depuis le blob (entries + sides)."""
    class _T:
        def __init__(self, side):
            self.side = side
    return [_T(s) for _, s in ev.blob["entries"]]


if __name__ == "__main__":
    unittest.main()
