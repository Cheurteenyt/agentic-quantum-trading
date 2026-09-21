"""Tests de la strategie breakout (Donchian) — backtest_v2.

Ce projet a perdu >4000 USD sur des backtests trompeurs : ces tests visent
d'abord le look-ahead et l'evaporation des couts.

Stdlib pure (unittest), aucune dependance externe.
"""
import itertools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.engine import (  # noqa: E402
    CampaignConfig,
    StrategyEval,
    evaluate_one,
    expand_grid,
)
from backend.services.backtest_v2.gates import GateConfig, LaneMetrics  # noqa: E402
from backend.services.backtest_v2.store import LaneIdentity  # noqa: E402
from backend.services.backtest_v2.walkforward import WalkForwardConfig  # noqa: E402

# Le module breakout est charge par CHEMIN (importlib) plutot que via le
# sous-package `strategies`, dont le __init__ est partiel.
import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "_breakout_under_test",
    ROOT / "backend" / "services" / "backtest_v2" / "strategies" / "breakout.py",
)
bo = importlib.util.module_from_spec(_SPEC)
sys.modules["_breakout_under_test"] = bo  # requis par dataclasses (resolution des types)
_SPEC.loader.exec_module(bo)


HOUR_MS = 3_600_000


def _params(**over):
    p = {
        "donchian_len": 10,
        "breakout_mult": 0.0,
        "confirmation_bars": 1,
        "use_close": False,
        "allow_short": True,
        "stop_bps": 500,
        "take_bps": 800,
        "max_leverage": 2,
    }
    p.update(over)
    return p


def _bar(i, o, h, l, c, v=10.0):
    return Bar(ts=i * HOUR_MS, open=o, high=h, low=l, close=c, volume=v)


def _flat(n=60, price=100.0):
    """Serie strictement plate : aucun nouveau max/min possible."""
    return [_bar(i, price, price, price, price) for i in range(n)]


def _range_then_up(n_flat=30, n_up=30, base=100.0, step=1.0):
    """Range plat puis rampe haussiere : breakout LONG franc."""
    bars = []
    for i in range(n_flat):
        p = base + (0.2 if i % 2 else -0.2)
        bars.append(_bar(i, base, p + 0.3, p - 0.3, p))
    for k in range(n_up):
        p = base + 1.0 + step * k
        bars.append(_bar(n_flat + k, p - 0.5, p + 0.5, p - 0.6, p))
    return bars


def _range_then_down(n_flat=30, n_dn=30, base=100.0, step=1.0):
    bars = []
    for i in range(n_flat):
        p = base + (0.2 if i % 2 else -0.2)
        bars.append(_bar(i, base, p + 0.3, p - 0.3, p))
    for k in range(n_dn):
        p = base - 1.0 - step * k
        bars.append(_bar(n_flat + k, p + 0.5, p + 0.6, p - 0.5, p))
    return bars


def _uptrend(n=500, base=100.0):
    bars = []
    for i in range(n):
        p = base * (1.0 + 0.002 * i)
        bars.append(_bar(i, p * 0.999, p * 1.004, p * 0.996, p))
    return bars


# ------------------------------------------------------------------ canal


class TestDonchianChannel(unittest.TestCase):
    def test_excludes_current_bar(self):
        bars = [
            _bar(0, 10, 12, 8, 11),
            _bar(1, 11, 13, 9, 12),
            _bar(2, 12, 99, 1, 50),  # extreme sur la barre courante
        ]
        chan = bo.donchian_channel(bars, 2, 2)
        self.assertEqual(chan, (8.0, 13.0))  # la barre 2 n'entre pas dans le canal

    def test_none_when_not_enough_history(self):
        bars = _flat(5)
        self.assertIsNone(bo.donchian_channel(bars, 2, 10))

    def test_invalid_length_raises(self):
        with self.assertRaises(ValueError):
            bo.donchian_channel(_flat(30), 20, 0)


# ---------------------------------------------------------------- signaux


class TestSignals(unittest.TestCase):
    def test_no_signal_on_flat_series(self):
        sigs = bo.compute_signals(_flat(60), _params())
        self.assertEqual(set(sigs), {0})

    def test_long_signal_on_new_high(self):
        sigs = bo.compute_signals(_range_then_up(), _params())
        self.assertIn(1, sigs)
        self.assertNotIn(-1, sigs)

    def test_short_signal_on_new_low(self):
        sigs = bo.compute_signals(_range_then_down(), _params())
        self.assertIn(-1, sigs)

    def test_allow_short_false_suppresses_shorts(self):
        sigs = bo.compute_signals(_range_then_down(), _params(allow_short=False))
        self.assertNotIn(-1, sigs)

    def test_confirmation_bars_delays_entry(self):
        bars = _range_then_up()
        s1 = bo.compute_signals(bars, _params(confirmation_bars=1))
        s2 = bo.compute_signals(bars, _params(confirmation_bars=2))
        self.assertEqual(len(s1), len(s2))
        # Le premier signal confirme arrive plus tard (ou pas du tout).
        first1 = next(i for i, s in enumerate(s1) if s != 0)
        nz2 = [i for i, s in enumerate(s2) if s != 0]
        self.assertTrue(not nz2 or nz2[0] > first1)

    def test_breakout_mult_makes_entry_harder(self):
        bars = _range_then_up(step=0.05)
        n0 = sum(1 for s in bo.compute_signals(bars, _params(breakout_mult=0.0)) if s)
        n1 = sum(1 for s in bo.compute_signals(bars, _params(breakout_mult=1.0)) if s)
        self.assertGreaterEqual(n0, n1)

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            bo.compute_signals(_flat(40), _params(confirmation_bars=0))
        with self.assertRaises(ValueError):
            bo.compute_signals(_flat(40), _params(breakout_mult=-1.0))


# ------------------------------------------------------- anti-look-ahead


class TestAntiLookAhead(unittest.TestCase):
    def test_mutating_last_bar_changes_no_past_signal(self):
        bars = _range_then_up()
        base = bo.compute_signals(bars, _params())
        mutated = list(bars)
        last = mutated[-1]
        mutated[-1] = Bar(last.ts, last.open, last.high * 5, last.low / 5,
                          last.close * 4, last.volume)
        after = bo.compute_signals(mutated, _params())
        self.assertEqual(base[:-1], after[:-1])

    def test_mutating_last_bar_changes_no_past_entry(self):
        bars = _range_then_up()
        a = bo.evaluate(_params(), bars)
        mutated = list(bars)
        last = mutated[-1]
        mutated[-1] = Bar(last.ts, last.open, last.high * 5, last.low / 5,
                          last.close * 4, last.volume)
        b = bo.evaluate(_params(), mutated)
        past_a = [e for e in a.blob["entries"] if e[0] < len(bars) - 1]
        past_b = [e for e in b.blob["entries"] if e[0] < len(bars) - 1]
        self.assertEqual(past_a, past_b)

    def test_entry_price_is_next_bar_open(self):
        bars = _range_then_up()
        sigs = bo.compute_signals(bars, _params())
        i = next(k for k, s in enumerate(sigs) if s != 0)
        trades, _ = bo.simulate(bars, _params())
        self.assertTrue(trades)
        first = trades[0]
        self.assertEqual(first.entry_index, i + 1)
        self.assertEqual(first.entry_price, bars[i + 1].open)


# ----------------------------------------------------------------- trades


class TestTrades(unittest.TestCase):
    def test_no_trade_without_breakout(self):
        ev = bo.evaluate(_params(), _flat(80))
        self.assertEqual(ev.closed_trades, 0)
        self.assertEqual(ev.trade_returns, [])
        self.assertEqual(set(ev.bar_returns_per_bar), {0.0})

    def test_long_trade_on_breakout_up(self):
        trades, _ = bo.simulate(_range_then_up(), _params())
        self.assertTrue(trades)
        self.assertEqual(trades[0].side, 1)

    def test_short_trade_on_breakout_down(self):
        trades, _ = bo.simulate(_range_then_down(), _params())
        self.assertTrue(trades)
        self.assertEqual(trades[0].side, -1)

    def test_tight_stop_reduces_pnl(self):
        bars = _range_then_up()
        wide = bo.evaluate(_params(stop_bps=500, take_bps=800), bars)
        tight = bo.evaluate(_params(stop_bps=1, take_bps=800), bars)
        self.assertIn("stop", tight.blob["exit_reasons"])
        self.assertLess(sum(tight.trade_returns), sum(wide.trade_returns))

    def test_stop_exit_price_respects_stop_level(self):
        bars = _range_then_down()
        trades, _ = bo.simulate(bars, _params(stop_bps=10))
        stops = [t for t in trades if t.reason == "stop"]
        self.assertTrue(stops)
        for t in stops:
            expected = t.entry_price * (1.0 + (10 / 10_000.0) * (1 if t.side == -1 else -1))
            self.assertAlmostEqual(t.exit_price, expected, places=9)


# ------------------------------------------------------------------ couts


class TestCosts(unittest.TestCase):
    def test_costs_non_zero_when_trades(self):
        ev = bo.evaluate(_params(), _range_then_up())
        self.assertGreater(ev.closed_trades, 0)
        self.assertIsNotNone(ev.costs.fees_usd)
        self.assertIsNotNone(ev.costs.slippage_usd)
        self.assertIsNotNone(ev.costs.funding_usd)
        self.assertLess(ev.costs.fees_usd, 0.0)
        self.assertLess(ev.costs.slippage_usd, 0.0)
        self.assertTrue(ev.costs.liquidation_checked)

    def test_total_equals_sum_of_components(self):
        ev = bo.evaluate(_params(), _range_then_up())
        self.assertAlmostEqual(
            ev.costs.total_usd,
            ev.costs.fees_usd + ev.costs.funding_usd + ev.costs.slippage_usd,
            places=9,
        )

    def test_funding_flag_present_and_explicit(self):
        ev = bo.evaluate(_params(), _range_then_up())
        self.assertIn("funding_available", ev.blob)
        self.assertIsInstance(ev.blob["funding_available"], bool)
        if not ev.blob["funding_available"]:
            self.assertEqual(ev.costs.funding_usd, 0.0)
            self.assertIsNotNone(ev.blob["funding_reason"])

    def test_no_trades_costs_are_zero_but_measured(self):
        ev = bo.evaluate(_params(), _flat(80))
        self.assertEqual(ev.costs.fees_usd, 0.0)
        self.assertEqual(ev.costs.slippage_usd, 0.0)
        self.assertEqual(ev.costs.funding_usd, 0.0)
        self.assertTrue(ev.costs.liquidation_checked)
        self.assertEqual(ev.costs.total_usd, 0.0)


# ---------------------------------------------------------------- contrat


class TestContract(unittest.TestCase):
    def test_returns_strategyeval(self):
        bars = _range_then_up()
        ev = bo.evaluate(_params(), bars)
        self.assertIsInstance(ev, StrategyEval)
        self.assertEqual(len(ev.bar_returns_per_bar), len(bars))
        self.assertEqual(ev.closed_trades, len(ev.trade_returns))
        self.assertIsInstance(ev.avg_holding_bars, int)
        self.assertFalse(ev.microstructure_validated)

    def test_first_bar_return_is_zero(self):
        ev = bo.evaluate(_params(), _range_then_up())
        self.assertEqual(ev.bar_returns_per_bar[0], 0.0)

    def test_deterministic(self):
        bars = _range_then_up()
        a = bo.evaluate(_params(), bars)
        b = bo.evaluate(_params(), bars)
        self.assertEqual(list(a.bar_returns_per_bar), list(b.bar_returns_per_bar))
        self.assertEqual(list(a.trade_returns), list(b.trade_returns))
        self.assertEqual(a.closed_trades, b.closed_trades)
        self.assertEqual(a.avg_holding_bars, b.avg_holding_bars)
        self.assertEqual(a.costs.total_usd, b.costs.total_usd)
        self.assertEqual(a.blob["entries"], b.blob["entries"])


# ------------------------------------------------------------ param space


class TestParamSpace(unittest.TestCase):
    def test_param_space_exported_and_under_300(self):
        self.assertIsInstance(bo.PARAM_SPACE, dict)
        total = 1
        for v in bo.PARAM_SPACE.values():
            self.assertTrue(len(v) >= 1)
            total *= len(v)
        self.assertLess(total, 300)
        self.assertEqual(total, len(list(expand_grid(bo.PARAM_SPACE))))
        self.assertEqual(
            total, len(list(itertools.product(*bo.PARAM_SPACE.values())))
        )

    def test_full_ranges_cover_specified_keys(self):
        expected = {
            "donchian_len", "breakout_mult", "confirmation_bars", "use_close",
            "allow_short", "stop_bps", "take_bps", "max_leverage",
        }
        self.assertEqual(set(bo.FULL_PARAM_RANGES), expected)
        self.assertEqual(set(bo.PARAM_SPACE), expected)

    def test_every_grid_combo_evaluates(self):
        bars = _range_then_up(n_flat=120, n_up=60)
        for combo in list(expand_grid(bo.PARAM_SPACE))[:12]:
            ev = bo.evaluate(combo, bars)
            self.assertEqual(len(ev.bar_returns_per_bar), len(bars))


# ------------------------------------------------------------ integration


class TestEngineIntegration(unittest.TestCase):
    def test_evaluate_one_produces_lane_metrics(self):
        bars = _uptrend(n=500)
        ev = bo.evaluate(_params(donchian_len=20), bars)
        identity = LaneIdentity(
            symbol="BTCUSDT", interval="1h", side="both",
            trigger="donchian_20_break", execution_model="taker_market",
            leverage=2.0,
        )
        cfg = CampaignConfig(
            run_id="bo-int",
            data_snapshot_id="snap-bo-2026-08-09",
            gate_config=GateConfig(),
            walkforward_config=WalkForwardConfig(
                n_folds=3, min_train_bars=100, min_test_bars=30
            ),
        )
        metrics, gate, bench, extra = evaluate_one(identity, ev, bars, cfg,
                                                   param_sensitivity=0.1)
        self.assertIsInstance(metrics, LaneMetrics)
        self.assertEqual(metrics.closed_trades, ev.closed_trades)
        self.assertIsNotNone(gate)
        self.assertIsInstance(extra, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
