"""Tests de la strategie funding_fade (mean-reversion sur le funding).

    python tests/test_backtest_v2_strat_funding_fade.py

Le module est charge par CHEMIN (importlib) plutot que via le sous-package
`strategies`, dont le __init__ est partiel : ces tests ne dependent d'aucune
strategie soeur.
"""
from __future__ import annotations

import importlib.util
import itertools
import math
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


def _load_ff():
    path = ROOT / "backend/services/backtest_v2/strategies/funding_fade.py"
    spec = importlib.util.spec_from_file_location("_funding_fade_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # requis pour @dataclass (introspection module)
    spec.loader.exec_module(mod)
    return mod


ff = _load_ff()


# ------------------------------------------------------------------ helpers


def _bars_from_closes(closes, ts0: int = 1_700_000_000_000) -> list[Bar]:
    bars: list[Bar] = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        bars.append(
            Bar(
                ts=ts0 + i * 3_600_000,
                open=o,
                high=max(o, c) * 1.001,
                low=min(o, c) * 0.999,
                close=c,
                volume=10.0,
            )
        )
        prev = c
    return bars


def _flat_bars(n: int = 600) -> list[Bar]:
    return _bars_from_closes([100.0] * n)


def _drifting_bars(n: int = 600) -> list[Bar]:
    return _bars_from_closes(
        [100.0 * (1.0 + 0.0003 * i + 0.004 * math.sin(i / 11.0)) for i in range(n)]
    )


def _params(**over) -> dict:
    p = {
        "lookback": 100,
        "entry_z": 1.5,
        "exit_z": 0.5,
        "allow_short": True,
        "stop_bps": 400,
        "max_leverage": 3,
        "symbol": "BTCUSDT",
    }
    p.update(over)
    return p


def _spike_series(n: int, spike_at: int, direction: int) -> list[float]:
    """Funding plat + bruit minuscule, avec un pic (haut ou bas) a `spike_at`."""
    base = [1.0 + (0.001 if i % 2 else -0.001) for i in range(n)]
    for k in range(spike_at, min(n, spike_at + 40)):
        base[k] = 1.0 + direction * 5.0
    return base


# -------------------------------------------------------------------- tests


class TestParamSpace(unittest.TestCase):
    def test_param_space_under_300_combos(self):
        total = 1
        for v in ff.PARAM_SPACE.values():
            total *= len(v)
        self.assertLess(total, 300)
        self.assertEqual(total, 48)

    def test_param_space_keys(self):
        self.assertEqual(
            sorted(ff.PARAM_SPACE),
            ["allow_short", "entry_z", "exit_z", "lookback", "max_leverage", "stop_bps"],
        )
        self.assertEqual(list(ff.PARAM_SPACE["allow_short"]), [True])


class TestFundingSeries(unittest.TestCase):
    def test_series_is_deterministic_per_symbol(self):
        a = ff.synthetic_funding_series(300, 0.46, "BTCUSDT")
        b = ff.synthetic_funding_series(300, 0.46, "BTCUSDT")
        self.assertEqual(a, b)

    def test_series_differs_between_symbols(self):
        a = ff.synthetic_funding_series(300, 0.46, "BTCUSDT")
        b = ff.synthetic_funding_series(300, 0.46, "ETHUSDT")
        self.assertNotEqual(a, b)

    def test_series_centered_on_base(self):
        base = 0.46
        s = ff.synthetic_funding_series(2110, base, "BTCUSDT")
        mean = sum(s) / len(s)
        self.assertLess(abs(mean - base), 0.2)

    def test_resolve_funding_unavailable_is_explicit_zero_center(self):
        missing = ROOT / "tests" / "_no_such_funding_cache_xyz.json"
        series, avg, flags = ff.resolve_funding(50, "BTCUSDT", missing)
        self.assertFalse(flags["funding_available"])
        self.assertIsNotNone(flags["funding_reason"])
        self.assertIsNone(avg)
        self.assertEqual(len(series), 50)
        self.assertLess(abs(sum(series) / len(series)), 1.0)

    def test_blob_documents_synthetic_approximation(self):
        ev = ff.evaluate(_params(), _flat_bars())
        self.assertTrue(ev.blob["funding_series_synthetic"])
        self.assertIn("SYNTH", ev.blob["funding_series_note"].upper())


class TestZScore(unittest.TestCase):
    def test_zscore_zero_before_warmup(self):
        z = ff.rolling_zscore([float(i) for i in range(50)], 20)
        self.assertTrue(all(v == 0.0 for v in z[:19]))
        self.assertNotEqual(z[19], 0.0)

    def test_zscore_flat_series_is_zero(self):
        z = ff.rolling_zscore([3.0] * 40, 10)
        self.assertTrue(all(v == 0.0 for v in z))

    def test_zscore_is_causal(self):
        vals = [float(i % 7) for i in range(80)]
        z_full = ff.rolling_zscore(vals, 20)
        z_trunc = ff.rolling_zscore(vals[:60], 20)
        self.assertEqual(z_full[:60], z_trunc)

    def test_invalid_lookback_raises(self):
        with self.assertRaises(ValueError):
            ff.rolling_zscore([1.0, 2.0], 1)


class TestSignals(unittest.TestCase):
    def test_high_funding_z_goes_short(self):
        n = 300
        series = _spike_series(n, 150, +1)
        sig = ff.compute_signals(_flat_bars(n), _params(lookback=100), series)
        self.assertIn(-1, sig)
        self.assertNotIn(1, sig)

    def test_low_funding_z_goes_long(self):
        n = 300
        series = _spike_series(n, 150, -1)
        sig = ff.compute_signals(_flat_bars(n), _params(lookback=100), series)
        self.assertIn(1, sig)
        self.assertNotIn(-1, sig)

    def test_no_trade_when_z_small(self):
        n = 300
        series = [1.0 + (0.001 if i % 2 else -0.001) for i in range(n)]
        sig = ff.compute_signals(_flat_bars(n), _params(lookback=100), series)
        self.assertTrue(all(s == 0 for s in sig))
        ev = ff.evaluate(_params(funding_bps_series=series), _flat_bars(n))
        self.assertEqual(ev.closed_trades, 0)

    def test_exit_when_z_returns_to_mean(self):
        n = 400
        series = _spike_series(n, 150, +1)
        sig = ff.compute_signals(_flat_bars(n), _params(lookback=100, exit_z=0.5), series)
        self.assertIn(-1, sig)
        self.assertEqual(sig[-1], 0)

    def test_signals_flat_during_warmup(self):
        n = 300
        series = _spike_series(n, 10, +1)
        sig = ff.compute_signals(_flat_bars(n), _params(lookback=200), series)
        self.assertTrue(all(s == 0 for s in sig[:199]))

    def test_invalid_exit_z_raises(self):
        with self.assertRaises(ValueError):
            ff.compute_signals(_flat_bars(50), _params(entry_z=1.5, exit_z=1.5))


class TestAntiLookAhead(unittest.TestCase):
    def test_mutating_last_bar_leaves_past_entries_unchanged(self):
        bars = _drifting_bars(600)
        base = ff.evaluate(_params(), bars)

        last = bars[-1]
        mutated = list(bars[:-1]) + [
            Bar(
                ts=last.ts,
                open=last.open,
                high=last.high * 5.0,
                low=last.low / 5.0,
                close=last.close * 3.0,
                volume=last.volume,
            )
        ]
        after = ff.evaluate(_params(), mutated)

        past_base = [e for e in base.blob["entries"] if e[0] < len(bars) - 1]
        past_after = [e for e in after.blob["entries"] if e[0] < len(bars) - 1]
        self.assertEqual(past_base, past_after)
        self.assertEqual(
            list(base.bar_returns_per_bar)[:-1], list(after.bar_returns_per_bar)[:-1]
        )

    def test_signals_only_executed_next_bar_open(self):
        n = 300
        series = _spike_series(n, 150, +1)
        bars = _flat_bars(n)
        sig = ff.compute_signals(bars, _params(lookback=100), series)
        trades, _ = ff.simulate(bars, _params(lookback=100), series)
        self.assertTrue(trades)
        first = trades[0]
        # entree a l'indice i => signal non nul deja present en i-1
        self.assertNotEqual(sig[first.entry_index - 1], 0)
        self.assertEqual(sig[first.entry_index - 1], first.side)


class TestCosts(unittest.TestCase):
    def test_costs_non_zero_and_total_is_sum(self):
        bars = _drifting_bars(600)
        ev = ff.evaluate(_params(), bars)
        self.assertGreater(ev.closed_trades, 0)
        c = ev.costs
        self.assertIsInstance(c, CostBreakdown)
        self.assertNotEqual(c.fees_usd, 0.0)
        self.assertNotEqual(c.slippage_usd, 0.0)
        self.assertIsNotNone(c.funding_usd)
        self.assertTrue(c.liquidation_checked)
        self.assertTrue(c.complete)
        self.assertAlmostEqual(
            c.total_usd, c.fees_usd + c.funding_usd + c.slippage_usd, places=9
        )

    def test_funding_unavailable_is_zero_not_none(self):
        bars = _drifting_bars(600)
        missing = ROOT / "tests" / "_no_such_funding_cache_xyz.json"
        ev = ff.evaluate(_params(funding_cache=missing), bars)
        self.assertFalse(ev.blob["funding_available"])
        self.assertIsNotNone(ev.blob["funding_reason"])
        self.assertEqual(ev.costs.funding_usd, 0.0)
        self.assertIsNotNone(ev.costs.total_usd)

    def test_no_trades_means_zero_costs_but_checked(self):
        n = 300
        series = [1.0] * n
        ev = ff.evaluate(_params(funding_bps_series=series), _flat_bars(n))
        self.assertEqual(ev.closed_trades, 0)
        self.assertEqual(ev.costs.fees_usd, 0.0)
        self.assertEqual(ev.costs.slippage_usd, 0.0)
        self.assertTrue(ev.costs.liquidation_checked)
        self.assertTrue(ev.costs.liquidation_safe)


class TestContract(unittest.TestCase):
    def test_evaluate_returns_strategy_eval(self):
        ev = ff.evaluate(_params(), _drifting_bars(600))
        self.assertIsInstance(ev, StrategyEval)
        self.assertEqual(len(ev.bar_returns_per_bar), 600)
        self.assertEqual(len(ev.trade_returns), ev.closed_trades)
        self.assertIsInstance(ev.avg_holding_bars, int)
        self.assertFalse(ev.microstructure_validated)
        self.assertEqual(len(ev.equity_curve), 601)

    def test_net_return_includes_fees_and_funding(self):
        bars = _drifting_bars(600)
        trades, _ = ff.simulate(bars, _params())
        self.assertTrue(trades)
        for t in trades:
            self.assertAlmostEqual(
                t.net_return,
                t.price_return + t.funding_return - ff.FEE_FRACTION_ROUND_TRIP,
                places=12,
            )

    def test_deterministic(self):
        bars = _drifting_bars(600)
        a = ff.evaluate(_params(), bars)
        b = ff.evaluate(_params(), bars)
        self.assertEqual(list(a.bar_returns_per_bar), list(b.bar_returns_per_bar))
        self.assertEqual(list(a.trade_returns), list(b.trade_returns))
        self.assertEqual(a.closed_trades, b.closed_trades)
        self.assertEqual(a.avg_holding_bars, b.avg_holding_bars)
        self.assertEqual(a.costs.total_usd, b.costs.total_usd)
        self.assertEqual(a.blob, b.blob)

    def test_zero_return_when_out_of_position(self):
        n = 300
        ev = ff.evaluate(_params(funding_bps_series=[1.0] * n), _drifting_bars(n))
        self.assertEqual(ev.closed_trades, 0)
        self.assertTrue(all(r == 0.0 for r in ev.bar_returns_per_bar))

    def test_short_earns_positive_funding_leg(self):
        n = 300
        series = _spike_series(n, 150, +1)  # funding tres positif -> short encaisse
        trades, _ = ff.simulate(_flat_bars(n), _params(lookback=100), series)
        self.assertTrue(trades)
        shorts = [t for t in trades if t.side == -1]
        self.assertTrue(shorts)
        self.assertGreater(sum(t.funding_return for t in shorts), 0.0)


class TestGridRuns(unittest.TestCase):
    def test_all_grid_combos_evaluate(self):
        bars = _drifting_bars(400)
        keys = list(ff.PARAM_SPACE)
        for combo in itertools.product(*(ff.PARAM_SPACE[k] for k in keys)):
            params = dict(zip(keys, combo))
            params["symbol"] = "BTCUSDT"
            ev = ff.evaluate(params, bars)
            self.assertIsInstance(ev, StrategyEval)


class TestEngineIntegration(unittest.TestCase):
    def test_evaluate_one_produces_lane_metrics(self):
        bars = _drifting_bars(500)
        ev = ff.evaluate(_params(), bars)
        identity = LaneIdentity(
            symbol="BTCUSDT", interval="1h", side="both",
            trigger="funding_z_100_1.5", execution_model="taker_market",
            leverage=3.0,
        )
        cfg = CampaignConfig(
            run_id="ff-int",
            data_snapshot_id="snap-ff-2026-08-09",
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
