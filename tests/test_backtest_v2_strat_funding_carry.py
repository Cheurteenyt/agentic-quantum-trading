"""Tests de la strategie funding_carry (collecte de funding, non-directionnelle).

    python tests/test_backtest_v2_strat_funding_carry.py

Le module est charge par CHEMIN (importlib) plutot que via le sous-package
`strategies`, dont le __init__ est partiel : ces tests ne dependent d'aucune
strategie soeur.
"""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import time
from unittest.mock import patch

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.costs import (  # noqa: E402
    CostBreakdown,
    CostDataUnavailable,
    FundingRate,
)
from backend.services.backtest_v2.engine import (  # noqa: E402
    CampaignConfig,
    StrategyEval,
    evaluate_one,
)
from backend.services.backtest_v2.gates import GateConfig, LaneMetrics  # noqa: E402
from backend.services.backtest_v2.store import LaneIdentity  # noqa: E402
from backend.services.backtest_v2.walkforward import WalkForwardConfig  # noqa: E402


def _load_fc():
    import importlib.util

    path = ROOT / "backend/services/backtest_v2/strategies/funding_carry.py"
    spec = importlib.util.spec_from_file_location("_funding_carry_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # requis pour @dataclass (introspection module)
    spec.loader.exec_module(mod)
    return mod


fc = _load_fc()


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


def _wiggle(n=400, level=100.0):
    """Serie deterministe a faible amplitude (pas de stop sur une barre normale)."""
    import math

    closes = [level + 3.0 * math.sin(i / 15.0) for i in range(n)]
    return _bars_from_closes(closes)


class _ConstSeries:
    """Série funding à taux constant (même signe que l'ancienne moyenne) —
    le contrat as-of : rate_asof(ts) et sum_pct_between(t0, t1)."""

    def __init__(self, avg_pct):
        self.avg = avg_pct

    def rate_asof(self, ts_ms):
        return self.avg

    def sum_pct_between(self, t0_ms, t1_ms):
        return self.avg * max(0.0, (t1_ms - t0_ms) / 3_600_000.0)


def _make_series(avg, symbol="BTCUSDT"):
    """Stub du loader : un taux constant du signe voulu."""
    return _ConstSeries(avg)


def _params(**over):
    p = {
        "side_filter": ("auto",),
        "hold_max_bars": 168,
        "allow_short": True,
        "stop_bps": 500,
        "max_leverage": 3,
        "symbol": "BTCUSDT",
    }
    p.update(over)
    return p


# --------------------------------------------------------------------- tests


class TestParamSpace(unittest.TestCase):
    def test_param_space_exported(self):
        self.assertTrue(hasattr(fc, "PARAM_SPACE"))
        self.assertIsInstance(fc.PARAM_SPACE, dict)
        for k in ("side_filter", "hold_max_bars", "allow_short", "stop_bps",
                  "max_leverage"):
            self.assertIn(k, fc.PARAM_SPACE)

    def test_cartesian_under_300(self):
        import itertools

        combos = list(itertools.product(*fc.PARAM_SPACE.values()))
        self.assertGreater(len(combos), 0)
        self.assertLess(len(combos), 300)

    def test_evaluate_exported(self):
        self.assertTrue(callable(fc.evaluate))


class TestSideSelection(unittest.TestCase):
    def test_positive_funding_gives_short(self):
        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            ev = fc.evaluate(_params(), bars)
        self.assertGreater(ev.closed_trades, 0)
        self.assertTrue(all(s == -1 for _, s in ev.blob["entries"]))

    def test_negative_funding_gives_long(self):
        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(-0.30)):
            ev = fc.evaluate(_params(), bars)
        self.assertGreater(ev.closed_trades, 0)
        self.assertTrue(all(s == 1 for _, s in ev.blob["entries"]))

    def test_zero_funding_is_flat(self):
        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(0.0)):
            ev = fc.evaluate(_params(), bars)
        self.assertEqual(ev.closed_trades, 0)

    def test_allow_short_false_blocks_short_side(self):
        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            ev = fc.evaluate(_params(allow_short=False), bars)
        # funding positif -> short collecteur ; shorts interdits -> plat.
        self.assertEqual(ev.closed_trades, 0)

    def test_unavailable_funding_is_flat(self):
        bars = _wiggle()
        with patch.object(
            fc, "load_funding_series",
            lambda symbol, cache_path=None: (_ for _ in ()).throw(
                CostDataUnavailable("cache perime")
            ),
        ):
            ev = fc.evaluate(_params(), bars)
        self.assertEqual(ev.closed_trades, 0)
        self.assertFalse(ev.blob["funding_available"])
        self.assertEqual(ev.costs.funding_usd, 0.0)
        self.assertTrue(ev.costs.warnings)


class TestNoLookAhead(unittest.TestCase):
    def test_mutate_last_bar_changes_no_past_entry(self):
        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            ev_a = fc.evaluate(_params(hold_max_bars=168), bars)
            # mute UNIQUEMENT la derniere barre.
            muted = list(bars[:-1]) + [
                Bar(ts=bars[-1].ts, open=bars[-1].open,
                    high=bars[-1].high * 3.0, low=bars[-1].low / 3.0,
                    close=bars[-1].close * 3.0, volume=bars[-1].volume)
            ]
            ev_b = fc.evaluate(_params(hold_max_bars=168), muted)
        n = len(bars)
        entries_a = [e for e in ev_a.blob["entries"] if e[0] < n - 1]
        entries_b = [e for e in ev_b.blob["entries"] if e[0] < n - 1]
        self.assertEqual(entries_a, entries_b)

    def test_execution_at_next_open_not_current_close(self):
        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            trades, _ = fc.simulate(bars, _params(), lambda ts: "short", 168)
        for t in trades:
            self.assertGreaterEqual(t.entry_index, 1)
            self.assertAlmostEqual(t.entry_price, bars[t.entry_index].open, places=9)


class TestCosts(unittest.TestCase):
    def setUp(self):
        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            self.bars = bars
            self.ev = fc.evaluate(_params(), bars)

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

    def test_funding_non_zero_when_available(self):
        self.assertGreater(self.ev.closed_trades, 0)
        self.assertNotEqual(self.ev.costs.funding_usd, 0.0)
        self.assertTrue(self.ev.blob["funding_available"])

    def test_total_equals_sum_of_components(self):
        c = self.ev.costs
        self.assertIsNotNone(c.total_usd)
        self.assertAlmostEqual(
            c.total_usd, c.fees_usd + c.funding_usd + c.slippage_usd, places=9
        )

    def test_funding_flag_present_in_blob(self):
        self.assertIn("funding_available", self.ev.blob)
        self.assertIsInstance(self.ev.blob["funding_available"], bool)


class TestContract(unittest.TestCase):
    def test_returns_strategy_eval(self):
        bars = _wiggle()
        ev = fc.evaluate(_params(), bars)
        self.assertIsInstance(ev, StrategyEval)
        self.assertEqual(len(ev.bar_returns_per_bar), len(bars))
        self.assertEqual(ev.closed_trades, len(ev.trade_returns))
        self.assertIsInstance(ev.avg_holding_bars, int)
        self.assertFalse(ev.microstructure_validated)

    def test_zero_return_when_out_of_position(self):
        bars = _wiggle()
        with patch.object(
            fc, "load_funding_series",
            lambda symbol, cache_path=None: (_ for _ in ()).throw(
                CostDataUnavailable("cache perime")
            ),
        ):
            ev = fc.evaluate(_params(), bars)
        self.assertEqual(ev.closed_trades, 0)
        self.assertTrue(all(r == 0.0 for r in ev.bar_returns_per_bar))

    def test_deterministic(self):
        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            a = fc.evaluate(_params(), bars)
            b = fc.evaluate(_params(), bars)
        self.assertEqual(list(a.bar_returns_per_bar), list(b.bar_returns_per_bar))
        self.assertEqual(list(a.trade_returns), list(b.trade_returns))
        self.assertEqual(a.closed_trades, b.closed_trades)
        self.assertEqual(a.avg_holding_bars, b.avg_holding_bars)
        self.assertEqual(a.costs.total_usd, b.costs.total_usd)
        self.assertEqual(a.blob, b.blob)

    def test_holding_bars_within_cap(self):
        bars = _wiggle()
        cap = 168
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            trades, _ = fc.simulate(bars, _params(hold_max_bars=cap), lambda ts: "short", cap)
        self.assertTrue(trades)
        for t in trades:
            self.assertLessEqual(t.holding_bars, cap)

    def test_rolling_produces_multiple_trades(self):
        bars = _wiggle(400)
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            ev = fc.evaluate(_params(hold_max_bars=168), bars)
        # 400 barres / 168 => au moins 2 roulements.
        self.assertGreater(ev.closed_trades, 1)
        self.assertIn("roll", ev.blob["exit_reasons"])


class TestGridRuns(unittest.TestCase):
    def test_all_grid_combos_evaluate(self):
        import itertools

        bars = _wiggle()
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            keys = list(fc.PARAM_SPACE)
            for combo in itertools.product(*(fc.PARAM_SPACE[k] for k in keys)):
                params = dict(zip(keys, combo))
                params["symbol"] = "BTCUSDT"
                ev = fc.evaluate(params, bars)
                self.assertIsInstance(ev, StrategyEval)


class TestEngineIntegration(unittest.TestCase):
    def test_evaluate_one_produces_lane_metrics(self):
        bars = _wiggle(500)
        with patch.object(fc, "load_funding_series",
                          lambda symbol, cache_path=None: _make_series(+0.46)):
            ev = fc.evaluate(_params(), bars)
        identity = LaneIdentity(
            symbol="BTCUSDT", interval="1h", side="both",
            trigger="funding_carry", execution_model="taker_market",
            leverage=3.0,
        )
        cfg = CampaignConfig(
            run_id="fc-int",
            data_snapshot_id="snap-fc-2026-08-09",
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
