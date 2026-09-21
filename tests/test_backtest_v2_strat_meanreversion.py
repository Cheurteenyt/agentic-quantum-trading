"""Tests de la strategie mean-reversion (z-score sur moyenne mobile).

    python tests/test_backtest_v2_strat_meanreversion.py

Le module est charge par CHEMIN (importlib) plutot que via le sous-package
`strategies`, dont le __init__ est partiel : ces tests ne dependent d'aucune
strategie soeur.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.costs import CostBreakdown  # noqa: E402
from backend.services.backtest_v2.engine import (  # noqa: E402
    CampaignConfig,
    StrategyEval,
    evaluate_one,
)
from backend.services.backtest_v2.gates import GateConfig, LaneMetrics  # noqa: E402
from backend.services.backtest_v2.store import LaneIdentity  # noqa: E402
from backend.services.backtest_v2.walkforward import WalkForwardConfig  # noqa: E402


def _load_mr():
    path = ROOT / "backend/services/backtest_v2/strategies/mean_reversion.py"
    spec = importlib.util.spec_from_file_location("_mean_reversion_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # requis pour @dataclass (introspection module)
    spec.loader.exec_module(mod)
    return mod


mr = _load_mr()


# ---------------------------------------------------------------- fabrications


def _bars_from_closes(closes, spread=0.5):
    """Bar OHLC autour d'une liste de closes : open = close precedent."""
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        hi = max(o, c) + spread
        lo = min(o, c) - spread
        out.append(Bar(ts=i * 3_600_000, open=o, high=hi, low=lo, close=c, volume=100.0))
        prev = c
    return out


def _flat(n=200, level=100.0):
    """Marche parfaitement au centre : z indefini (dispersion nulle)."""
    return _bars_from_closes([level] * n)


def _tiny_noise(n=300, level=100.0):
    """Oscillation reguliere de faible amplitude : |z| reste borne (< 1.5)."""
    closes = [level + (0.5 if i % 2 == 0 else -0.5) for i in range(n)]
    return _bars_from_closes(closes)


def _plateau_then_crash(n=120, lookback=20, drop=-8.0):
    """Plateau bruite puis chute brutale -> z tres negatif -> LONG attendu."""
    closes = [100.0 + (0.2 if i % 2 else -0.2) for i in range(n)]
    closes[-1] = closes[-1] + drop
    # deux barres apres la chute pour laisser l'execution a l'open de i+1.
    closes.append(closes[-1])
    closes.append(closes[-1])
    return _bars_from_closes(closes)


def _plateau_then_spike(n=120, jump=8.0):
    closes = [100.0 + (0.2 if i % 2 else -0.2) for i in range(n)]
    closes[-1] = closes[-1] + jump
    closes.append(closes[-1])
    closes.append(closes[-1])
    return _bars_from_closes(closes)


DEFAULT_PARAMS = {
    "lookback": 20,
    "entry_z": 1.5,
    "exit_z": 0.5,
    "use_std": True,
    "allow_short": True,
    "stop_bps": 300,
    "take_bps": 200,
    "max_leverage": 3,
    "symbol": "BTCUSDT",
}


def _params(**over):
    p = dict(DEFAULT_PARAMS)
    p.update(over)
    return p


def _mutate_last(bars, factor=3.0):
    """Copie des bars avec UNIQUEMENT la derniere barre modifiee."""
    out = list(bars[:-1])
    last = bars[-1]
    out.append(
        Bar(
            ts=last.ts,
            open=last.open,
            high=last.high * factor,
            low=last.low / factor,
            close=last.close * factor,
            volume=last.volume,
        )
    )
    return out


# --------------------------------------------------------------------- tests


class TestParamSpace(unittest.TestCase):
    def test_param_space_exported(self):
        self.assertTrue(hasattr(mr, "PARAM_SPACE"))
        self.assertIsInstance(mr.PARAM_SPACE, dict)
        for k in ("lookback", "entry_z", "exit_z", "use_std", "allow_short",
                  "stop_bps", "take_bps", "max_leverage"):
            self.assertIn(k, mr.PARAM_SPACE)

    def test_cartesian_under_300(self):
        combos = list(itertools.product(*mr.PARAM_SPACE.values()))
        self.assertLess(len(combos), 300)
        self.assertGreater(len(combos), 0)

    def test_full_ranges_documented(self):
        self.assertEqual(sorted(mr.FULL_PARAM_RANGES), sorted(mr.PARAM_SPACE))

    def test_evaluate_exported(self):
        self.assertTrue(callable(mr.evaluate))


class TestZScore(unittest.TestCase):
    def test_none_before_full_window(self):
        z = mr.zscore_series([1.0, 2.0, 3.0, 4.0], 3)
        self.assertEqual(z[:2], [None, None])
        self.assertIsNotNone(z[2])

    def test_none_when_dispersion_zero(self):
        """Serie plate : le z-score n'existe pas — None, PAS 0.0."""
        z = mr.zscore_series([100.0] * 10, 5)
        self.assertTrue(all(v is None for v in z))

    def test_zscore_sign(self):
        closes = [10.0, 10.0, 10.0, 10.0, 5.0]
        z = mr.zscore_series(closes, 5)
        self.assertLess(z[-1], 0.0)

    def test_mad_variant_differs(self):
        closes = [10.0, 12.0, 9.0, 14.0, 8.0, 20.0]
        z_std = mr.zscore_series(closes, 6, use_std=True)[-1]
        z_mad = mr.zscore_series(closes, 6, use_std=False)[-1]
        self.assertNotAlmostEqual(z_std, z_mad)

    def test_invalid_lookback_raises(self):
        with self.assertRaises(ValueError):
            mr.zscore_series([1.0, 2.0], 1)

    def test_zscore_last_bar_does_not_change_past(self):
        closes = [10.0, 11.0, 9.0, 12.0, 8.0, 13.0]
        a = mr.zscore_series(closes, 3)
        b = mr.zscore_series(closes[:-1] + [99.0], 3)
        self.assertEqual(a[:-1], b[:-1])


class TestSignals(unittest.TestCase):
    def test_long_when_z_very_negative(self):
        bars = _plateau_then_crash()
        sigs = mr.compute_signals(bars, _params())
        self.assertIn(1, sigs)

    def test_short_when_z_very_positive(self):
        bars = _plateau_then_spike()
        sigs = mr.compute_signals(bars, _params())
        self.assertIn(-1, sigs)

    def test_allow_short_false_blocks_shorts(self):
        bars = _plateau_then_spike()
        sigs = mr.compute_signals(bars, _params(allow_short=False))
        self.assertNotIn(-1, sigs)

    def test_no_signal_when_market_centered(self):
        """|z| petit (marche au centre) -> aucune position."""
        bars = _tiny_noise()
        sigs = mr.compute_signals(bars, _params(entry_z=2.5))
        self.assertEqual(set(sigs), {0})

    def test_flat_market_gives_no_signal(self):
        sigs = mr.compute_signals(_flat(), _params())
        self.assertEqual(set(sigs), {0})

    def test_exit_z_must_be_below_entry_z(self):
        with self.assertRaises(ValueError):
            mr.compute_signals(_tiny_noise(), _params(entry_z=1.5, exit_z=1.5))


class TestNoLookAhead(unittest.TestCase):
    def test_mutating_last_bar_changes_no_past_signal(self):
        bars = _plateau_then_crash()
        base = mr.compute_signals(bars, _params())
        muted = mr.compute_signals(_mutate_last(bars), _params())
        self.assertEqual(base[:-1], muted[:-1])

    def test_mutating_last_bar_changes_no_past_entry(self):
        bars = _plateau_then_crash()
        ev_a = mr.evaluate(_params(), bars)
        ev_b = mr.evaluate(_params(), _mutate_last(bars))
        entries_a = [e for e in ev_a.blob["entries"] if e[0] < len(bars) - 1]
        entries_b = [e for e in ev_b.blob["entries"] if e[0] < len(bars) - 1]
        self.assertEqual(entries_a, entries_b)

    def test_execution_at_next_open_not_current_close(self):
        """Une entree ne peut jamais avoir lieu sur la barre du signal."""
        bars = _plateau_then_crash()
        trades, _ = mr.simulate(bars, _params())
        sigs = mr.compute_signals(bars, _params())
        for t in trades:
            self.assertGreaterEqual(t.entry_index, 1)
            self.assertEqual(sigs[t.entry_index - 1], t.side)
            self.assertEqual(t.entry_price, bars[t.entry_index].open)


class TestStops(unittest.TestCase):
    def _stop_bars(self):
        """Chute -> LONG, puis effondrement continu : le stop doit sauter."""
        closes = [100.0 + (0.2 if i % 2 else -0.2) for i in range(60)]
        closes[-1] = closes[-1] - 6.0
        closes += [94.0, 90.0, 85.0, 80.0, 75.0]
        return _bars_from_closes(closes)

    def test_stop_triggers(self):
        bars = self._stop_bars()
        trades, _ = mr.simulate(bars, _params(stop_bps=150, take_bps=10_000))
        self.assertTrue(any(t.reason == "stop" for t in trades))

    def test_tight_stop_reduces_pnl_vs_wide(self):
        bars = self._stop_bars()
        tight = mr.evaluate(_params(stop_bps=150, take_bps=10_000), bars)
        wide = mr.evaluate(_params(stop_bps=300, take_bps=10_000), bars)
        self.assertLess(sum(wide.trade_returns), 0.0)
        self.assertGreater(sum(tight.trade_returns), sum(wide.trade_returns))

    def test_take_profit_triggers(self):
        closes = [100.0 + (0.2 if i % 2 else -0.2) for i in range(60)]
        closes[-1] = closes[-1] - 6.0
        closes += [96.0, 99.0, 102.0]
        bars = _bars_from_closes(closes)
        trades, _ = mr.simulate(bars, _params(stop_bps=10_000, take_bps=100))
        self.assertTrue(any(t.reason == "take" for t in trades))


class TestCosts(unittest.TestCase):
    def setUp(self):
        self.bars = _plateau_then_crash()
        self.ev = mr.evaluate(_params(), self.bars)

    def test_costs_is_breakdown(self):
        self.assertIsInstance(self.ev.costs, CostBreakdown)

    def test_four_posts_never_none(self):
        c = self.ev.costs
        self.assertIsNotNone(c.fees_usd)
        self.assertIsNotNone(c.slippage_usd)
        self.assertIsNotNone(c.funding_usd)
        self.assertTrue(c.liquidation_checked)

    def test_fees_and_slippage_non_zero_when_trades(self):
        self.assertGreater(self.ev.closed_trades, 0)
        self.assertNotEqual(self.ev.costs.fees_usd, 0.0)
        self.assertNotEqual(self.ev.costs.slippage_usd, 0.0)

    def test_total_equals_sum_of_components(self):
        c = self.ev.costs
        self.assertIsNotNone(c.total_usd)
        self.assertAlmostEqual(
            c.total_usd, c.fees_usd + c.funding_usd + c.slippage_usd, places=9
        )

    def test_funding_flag_present_in_blob(self):
        self.assertIn("funding_available", self.ev.blob)
        self.assertIsInstance(self.ev.blob["funding_available"], bool)
        if not self.ev.blob["funding_available"]:
            # funding indisponible -> 0.0 EXPLICITE + avertissement
            self.assertEqual(self.ev.costs.funding_usd, 0.0)
            self.assertTrue(self.ev.costs.warnings)


class TestContract(unittest.TestCase):
    def test_returns_strategy_eval(self):
        bars = _plateau_then_crash()
        ev = mr.evaluate(_params(), bars)
        self.assertIsInstance(ev, StrategyEval)
        self.assertEqual(len(ev.bar_returns_per_bar), len(bars))
        self.assertEqual(ev.closed_trades, len(ev.trade_returns))
        self.assertIsInstance(ev.avg_holding_bars, int)
        self.assertFalse(ev.microstructure_validated)

    def test_zero_return_when_out_of_position(self):
        ev = mr.evaluate(_params(), _tiny_noise())
        self.assertEqual(ev.closed_trades, 0)
        self.assertTrue(all(r == 0.0 for r in ev.bar_returns_per_bar))

    def test_deterministic(self):
        bars = _plateau_then_crash()
        a = mr.evaluate(_params(), bars)
        b = mr.evaluate(_params(), bars)
        self.assertEqual(list(a.bar_returns_per_bar), list(b.bar_returns_per_bar))
        self.assertEqual(list(a.trade_returns), list(b.trade_returns))
        self.assertEqual(a.closed_trades, b.closed_trades)
        self.assertEqual(a.avg_holding_bars, b.avg_holding_bars)
        self.assertEqual(a.costs.total_usd, b.costs.total_usd)
        self.assertEqual(a.blob, b.blob)

    def test_net_return_includes_fees(self):
        bars = _plateau_then_crash()
        trades, _ = mr.simulate(bars, _params())
        for t in trades:
            self.assertAlmostEqual(
                t.net_return, t.gross_return - mr.FEE_FRACTION_ROUND_TRIP, places=12
            )


class TestGridRuns(unittest.TestCase):
    def test_all_grid_combos_evaluate(self):
        bars = _plateau_then_crash()
        keys = list(mr.PARAM_SPACE)
        for combo in itertools.product(*(mr.PARAM_SPACE[k] for k in keys)):
            params = dict(zip(keys, combo))
            params["symbol"] = "BTCUSDT"
            ev = mr.evaluate(params, bars)
            self.assertIsInstance(ev, StrategyEval)


class TestEngineIntegration(unittest.TestCase):
    def test_evaluate_one_produces_lane_metrics(self):
        bars = _bars_from_closes(
            [100.0 + 5.0 * ((i % 40) - 20) / 20.0 for i in range(500)]
        )
        ev = mr.evaluate(_params(), bars)
        identity = LaneIdentity(
            symbol="BTCUSDT", interval="1h", side="both",
            trigger="zscore_20_1.5", execution_model="taker_market",
            leverage=3.0,
        )
        cfg = CampaignConfig(
            run_id="mr-int",
            data_snapshot_id="snap-mr-2026-08-09",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
