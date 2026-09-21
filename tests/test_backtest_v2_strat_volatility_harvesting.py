"""Tests de la strategie volatility_harvesting (stdlib pure, unittest)."""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402
import itertools  # noqa: E402

from backend.services.backtest_v2.baselines import Bar, bars_from_klines  # noqa: E402
from backend.services.backtest_v2.costs import CostBreakdown  # noqa: E402
from backend.services.backtest_v2.engine import (  # noqa: E402
    CampaignConfig,
    StrategyEval,
    evaluate_one,
)
from backend.services.backtest_v2.gates import GateConfig, LaneMetrics  # noqa: E402
from backend.services.backtest_v2.store import LaneIdentity  # noqa: E402
from backend.services.backtest_v2.walkforward import WalkForwardConfig  # noqa: E402


def _load_strategy():
    path = ROOT / "backend/services/backtest_v2/strategies/volatility_harvesting.py"
    spec = importlib.util.spec_from_file_location("_volharvest_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # requis pour @dataclass (introspection module)
    spec.loader.exec_module(mod)
    return mod


vh = _load_strategy()


# ---------------------------------------------------------------- fabrications


def _params(**over):
    p = {"spread_bps": 10, "allow_short": True, "max_leverage": 3}
    p.update(over)
    return p


def _bar(i, close=100.0, range_pct=0.01, open_=None):
    half = close * range_pct / 2.0
    return Bar(
        ts=1_700_000_000_000 + i * 3_600_000,
        open=close if open_ is None else open_,
        high=close + half,
        low=close - half,
        close=close,
        volume=1000.0,
    )


def _wide(n=300, range_pct=0.02):
    """Serie a fourchette large (recolte possible partout)."""
    return [_bar(i, close=100.0 + (i % 7) * 0.1, range_pct=range_pct) for i in range(n)]


def _flat(n=50):
    """Serie a fourchette nulle (high == low)."""
    return [
        Bar(ts=1_700_000_000_000 + i * 3_600_000, open=100.0, high=100.0,
            low=100.0, close=100.0, volume=10.0)
        for i in range(n)
    ]


# ------------------------------------------------------------------- tests


class TestParamSpace(unittest.TestCase):
    def test_param_space_exported(self):
        self.assertIsInstance(vh.PARAM_SPACE, dict)
        for key in ("spread_bps", "allow_short", "max_leverage"):
            self.assertIn(key, vh.PARAM_SPACE)

    def test_param_space_values(self):
        self.assertEqual(list(vh.PARAM_SPACE["spread_bps"]), [5, 10, 20])
        self.assertEqual(list(vh.PARAM_SPACE["allow_short"]), [True])
        self.assertEqual(list(vh.PARAM_SPACE["max_leverage"]), [2, 3])

    def test_param_space_cartesian_under_300(self):
        combos = list(itertools.product(*[vh.PARAM_SPACE[k] for k in sorted(vh.PARAM_SPACE)]))
        self.assertEqual(len(combos), 6)
        self.assertLess(len(combos), 300)

    def test_every_combo_evaluates(self):
        bars = _wide(n=120)
        keys = sorted(vh.PARAM_SPACE)
        for combo in itertools.product(*[vh.PARAM_SPACE[k] for k in keys]):
            p = dict(zip(keys, combo))
            ev = vh.evaluate(p, bars)
            self.assertIsInstance(ev, StrategyEval)


class TestHarvest(unittest.TestCase):
    def test_wide_range_bar_is_positive_trade(self):
        """Fourchette large -> recolte strictement positive."""
        bars = _wide(n=50, range_pct=0.02)
        ev = vh.evaluate(_params(spread_bps=10), bars)
        self.assertGreater(ev.closed_trades, 0)
        self.assertTrue(any(r > 0 for r in ev.trade_returns))
        self.assertTrue(any(r > 0 for r in ev.bar_returns_per_bar))

    def test_range_below_spread_gives_no_trade(self):
        """Fourchette (10 bps) < marge de securite (20 bps) -> aucun trade."""
        bars = _wide(n=50, range_pct=0.001)  # 10 bps de fourchette
        ev = vh.evaluate(_params(spread_bps=20), bars)
        self.assertEqual(ev.closed_trades, 0)
        self.assertEqual(ev.trade_returns, [])
        self.assertTrue(all(r == 0.0 for r in ev.bar_returns_per_bar))

    def test_high_equals_low_gives_no_trade(self):
        ev = vh.evaluate(_params(), _flat(40))
        self.assertEqual(ev.closed_trades, 0)
        self.assertEqual(ev.avg_holding_bars, 0)

    def test_harvestable_fraction_zero_when_narrow(self):
        b = _bar(0, close=100.0, range_pct=0.0005)  # 5 bps
        self.assertEqual(vh.harvestable_fraction(b, 20), 0.0)
        self.assertGreater(vh.harvestable_fraction(b, 1), 0.0)

    def test_harvestable_fraction_zero_when_high_le_low(self):
        b = Bar(ts=0, open=100.0, high=100.0, low=100.0, close=100.0, volume=1.0)
        self.assertEqual(vh.harvestable_fraction(b, 5), 0.0)

    def test_first_bar_never_traded(self):
        """Aucune cotation sur la barre 0 : pas de signal anterieur."""
        bars = _wide(n=30, range_pct=0.03)
        ev = vh.evaluate(_params(), bars)
        self.assertEqual(ev.bar_returns_per_bar[0], 0.0)
        self.assertNotIn(0, ev.blob["harvest_bars"])

    def test_larger_spread_reduces_harvest(self):
        bars = _wide(n=80, range_pct=0.02)
        low = vh.evaluate(_params(spread_bps=5), bars)
        high = vh.evaluate(_params(spread_bps=20), bars)
        self.assertGreater(sum(low.bar_returns_per_bar), sum(high.bar_returns_per_bar))

    def test_avg_holding_is_one_bar(self):
        ev = vh.evaluate(_params(), _wide(n=60, range_pct=0.02))
        self.assertEqual(ev.avg_holding_bars, 1)

    def test_non_directional_returns_independent_of_close_drift(self):
        """Pas d'exposition close->close : renverser la derive ne change rien."""
        up = [_bar(i, close=100.0 + i, range_pct=0.02) for i in range(60)]
        down = [_bar(i, close=100.0 + i, range_pct=0.02) for i in range(60)][::-1]
        # meme distribution de fourchettes relatives -> memes signes de rendement
        ev_up = vh.evaluate(_params(), up)
        ev_down = vh.evaluate(_params(), down)
        self.assertTrue(all(r >= 0 for r in ev_up.bar_returns_per_bar))
        self.assertTrue(all(r >= 0 for r in ev_down.bar_returns_per_bar))


class TestAntiLookAhead(unittest.TestCase):
    def test_mutating_last_bar_changes_nothing_before(self):
        bars = _wide(n=200, range_pct=0.02)
        ref = vh.evaluate(_params(), bars)

        last = bars[-1]
        mutated = list(bars[:-1]) + [
            Bar(ts=last.ts, open=last.open * 1.5, high=last.high * 3.0,
                low=last.low * 0.3, close=last.close * 1.4, volume=last.volume * 9)
        ]
        out = vh.evaluate(_params(), mutated)

        self.assertEqual(
            list(ref.bar_returns_per_bar[:-1]), list(out.bar_returns_per_bar[:-1])
        )

    def test_signal_only_uses_past_bar(self):
        bars = _wide(n=100, range_pct=0.02)
        sig = vh.compute_signals(bars, _params())
        bars2 = list(bars[:-1]) + [_bar(99, close=100.0, range_pct=0.5)]
        sig2 = vh.compute_signals(bars2, _params())
        self.assertEqual(sig[:-1], sig2[:-1])


class TestCosts(unittest.TestCase):
    def test_costs_are_a_breakdown_and_non_null(self):
        ev = vh.evaluate(_params(), _wide(n=120, range_pct=0.02))
        self.assertIsInstance(ev.costs, CostBreakdown)
        self.assertIsNotNone(ev.costs.fees_usd)
        self.assertIsNotNone(ev.costs.slippage_usd)
        self.assertIsNotNone(ev.costs.funding_usd)
        self.assertTrue(ev.costs.liquidation_checked)
        self.assertLess(ev.costs.fees_usd, 0.0)
        self.assertLess(ev.costs.slippage_usd, 0.0)

    def test_total_usd_equals_sum_of_components(self):
        ev = vh.evaluate(_params(), _wide(n=120, range_pct=0.02))
        total = ev.costs.total_usd
        self.assertIsNotNone(total)
        expected = (ev.costs.fees_usd or 0.0) + (ev.costs.funding_usd or 0.0) \
            + (ev.costs.slippage_usd or 0.0)
        self.assertAlmostEqual(total, expected, places=9)

    def test_funding_explicit_when_unavailable(self):
        ev = vh.evaluate(_params(), _wide(n=60, range_pct=0.02))
        if not ev.blob["funding_available"]:
            self.assertEqual(ev.costs.funding_usd, 0.0)
            self.assertIsNotNone(ev.blob["funding_reason"])
            self.assertTrue(ev.costs.warnings)
        else:
            self.assertIsInstance(ev.costs.funding_usd, float)

    def test_no_trade_means_no_cost(self):
        ev = vh.evaluate(_params(), _flat(30))
        self.assertEqual(ev.costs.fees_usd, 0.0)
        self.assertEqual(ev.costs.slippage_usd, 0.0)
        self.assertTrue(ev.costs.liquidation_checked)

    def test_net_return_below_gross(self):
        bars = _wide(n=60, range_pct=0.02)
        trades, _ = vh.simulate(bars, _params())
        self.assertTrue(trades)
        for t in trades:
            self.assertLess(t.net_return, t.gross_return)

    def test_microstructure_not_validated(self):
        ev = vh.evaluate(_params(), _wide(n=60, range_pct=0.02))
        self.assertFalse(ev.microstructure_validated)


class TestDeterminism(unittest.TestCase):
    def test_same_inputs_same_output(self):
        bars = _wide(n=150, range_pct=0.02)
        a = vh.evaluate(_params(), bars)
        b = vh.evaluate(_params(), bars)
        self.assertEqual(list(a.bar_returns_per_bar), list(b.bar_returns_per_bar))
        self.assertEqual(a.closed_trades, b.closed_trades)
        self.assertEqual(list(a.trade_returns), list(b.trade_returns))
        self.assertEqual(a.avg_holding_bars, b.avg_holding_bars)
        self.assertEqual(a.costs.fees_usd, b.costs.fees_usd)
        self.assertEqual(a.costs.slippage_usd, b.costs.slippage_usd)
        self.assertEqual(a.costs.funding_usd, b.costs.funding_usd)
        self.assertEqual(a.blob["harvest_bars"], b.blob["harvest_bars"])

    def test_bars_from_klines_roundtrip(self):
        raw = [
            [1_700_000_000_000 + i * 3_600_000, "100", "102", "98", "101", "5"]
            for i in range(30)
        ]
        bars = bars_from_klines(raw)
        ev = vh.evaluate(_params(), bars)
        self.assertEqual(len(ev.bar_returns_per_bar), len(bars))


class TestEngineIntegration(unittest.TestCase):
    def test_evaluate_one_produces_lane_metrics(self):
        bars = _wide(n=500, range_pct=0.02)
        ev = vh.evaluate(_params(), bars)
        identity = LaneIdentity(
            symbol="BTCUSDT", interval="1h", side="both",
            trigger="vol_harvest_spread_10", execution_model="taker_market",
            leverage=3.0,
        )
        cfg = CampaignConfig(
            run_id="vh-int",
            data_snapshot_id="snap-vh-2026-08-09",
            gate_config=GateConfig(),
            walkforward_config=WalkForwardConfig(
                n_folds=3, min_train_bars=100, min_test_bars=30
            ),
        )
        metrics, gate, bench, extra = evaluate_one(
            identity, ev, bars, cfg, param_sensitivity=0.1
        )
        self.assertIsInstance(metrics, LaneMetrics)
        self.assertEqual(metrics.closed_trades, ev.closed_trades)
        self.assertIn("walkforward", extra)
        self.assertIn(gate.passed, (True, False))


class TestPackageImport(unittest.TestCase):
    """Import canonique par le sous-package (et pas seulement par chemin)."""

    def test_public_api_importable_from_package(self):
        from backend.services.backtest_v2.strategies.volatility_harvesting import (
            PARAM_SPACE,
            evaluate,
        )

        self.assertTrue(callable(evaluate))
        self.assertEqual(
            set(PARAM_SPACE),
            {"spread_bps", "allow_short", "max_leverage"},
        )
        n = 1
        for v in PARAM_SPACE.values():
            n *= len(v)
        self.assertLessEqual(n, 300)

    def test_package_evaluate_matches_path_loaded_module(self):
        from backend.services.backtest_v2.strategies.volatility_harvesting import (
            evaluate as pkg_evaluate,
        )

        bars = _wide(n=60)
        a = pkg_evaluate(_params(), bars)
        b = vh.evaluate(_params(), bars)
        self.assertEqual(list(a.bar_returns_per_bar), list(b.bar_returns_per_bar))
        self.assertEqual(list(a.trade_returns), list(b.trade_returns))
        self.assertFalse(a.microstructure_validated)


if __name__ == "__main__":
    unittest.main(verbosity=2)
