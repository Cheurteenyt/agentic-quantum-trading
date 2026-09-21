"""Tests de la strategie momentum (EMA cross + filtre de regime).

    python tests/test_backtest_v2_strat_momentum.py

Le module momentum est charge par CHEMIN (importlib) plutot que via le
sous-package `strategies`, dont le __init__ importe aussi mean_reversion et
breakout : ainsi ces tests ne dependent pas de strategies soeurs.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
import tempfile
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


def _load_momentum():
    path = ROOT / "backend/services/backtest_v2/strategies/momentum.py"
    spec = importlib.util.spec_from_file_location("_momentum_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # requis pour @dataclass (introspection module)
    spec.loader.exec_module(mod)
    return mod


mom = _load_momentum()


# ---------------------------------------------------------------- fabrications


def _bars_from_closes(closes, spread=0.5):
    """Construit des Bar OHLC autour d'une liste de closes.

    open = close precedent (continuite), high/low = close +/- spread.
    """
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        hi = max(o, c) + spread
        lo = min(o, c) - spread
        out.append(Bar(ts=i * 3_600_000, open=o, high=hi, low=lo, close=c, volume=100.0))
        prev = c
    return out


def _uptrend(n=400):
    """Tendance haussiere reguliere : cross fast>slow ET close>regime => long."""
    return _bars_from_closes([100.0 + i * 0.5 for i in range(n)])


def _downtrend(n=400):
    return _bars_from_closes([300.0 - i * 0.5 for i in range(n)])


DEFAULT_PARAMS = {
    "fast_ema": 8,
    "slow_ema": 40,
    "regime_ema": 120,
    "allow_short": True,
    "stop_bps": 1000,
    "take_bps": 1000,
    "max_leverage": 3,
    "symbol": "BTCUSDT",
}


def _params(**over):
    p = dict(DEFAULT_PARAMS)
    p.update(over)
    return p


# --------------------------------------------------------------------- tests


class TestParamSpace(unittest.TestCase):
    def test_param_space_exported(self):
        self.assertTrue(hasattr(mom, "PARAM_SPACE"))
        self.assertIsInstance(mom.PARAM_SPACE, dict)
        for k in ("fast_ema", "slow_ema", "regime_ema", "allow_short",
                  "stop_bps", "take_bps", "max_leverage"):
            self.assertIn(k, mom.PARAM_SPACE)

    def test_cartesian_under_300(self):
        combos = list(itertools.product(*mom.PARAM_SPACE.values()))
        self.assertLess(len(combos), 300)
        self.assertGreater(len(combos), 0)

    def test_evaluate_exported(self):
        self.assertTrue(callable(mom.evaluate))


class TestEMA(unittest.TestCase):
    def test_ema_causal_length(self):
        closes = [1.0, 2.0, 3.0, 4.0]
        e = mom.ema_series(closes, 2)
        self.assertEqual(len(e), 4)
        self.assertEqual(e[0], 1.0)  # amorce sur le premier close

    def test_ema_last_bar_does_not_change_past(self):
        """EMA causale : muter le dernier close ne touche aucune valeur passee."""
        closes = [10.0, 11.0, 12.0, 13.0, 14.0]
        a = mom.ema_series(closes, 3)
        closes2 = list(closes)
        closes2[-1] = 999.0
        b = mom.ema_series(closes2, 3)
        self.assertEqual(a[:-1], b[:-1])

    def test_ema_invalid_period(self):
        with self.assertRaises(ValueError):
            mom.ema_series([1.0, 2.0], 0)


class TestSignals(unittest.TestCase):
    def test_long_signal_in_uptrend(self):
        bars = _uptrend()
        sig = mom.compute_signals(bars, _params())
        self.assertEqual(sig[-1], 1)  # cross haussier + close>regime => long

    def test_short_signal_in_downtrend(self):
        bars = _downtrend()
        sig = mom.compute_signals(bars, _params(allow_short=True))
        self.assertEqual(sig[-1], -1)

    def test_regime_filter_blocks_counter_trend(self):
        """Filtre de regime : jamais de position contre la tendance longue.

        En downtrend, un short est aligne (close<regime). On desactive short :
        aucune position ne doit alors etre prise (pas de long contre-tendance).
        """
        bars = _downtrend()
        sig = mom.compute_signals(bars, _params(allow_short=False))
        self.assertTrue(all(s != -1 for s in sig))
        # Pas de long en pleine tendance baissiere (close < regime partout tard).
        self.assertEqual(sig[-1], 0)

    def test_no_short_when_disallowed(self):
        bars = _downtrend()
        sig = mom.compute_signals(bars, _params(allow_short=False))
        self.assertNotIn(-1, sig)

    def test_warmup_is_flat(self):
        bars = _uptrend()
        sig = mom.compute_signals(bars, _params())
        # Avant l'amorce du regime (120), on reste plat.
        self.assertTrue(all(s == 0 for s in sig[:100]))


class TestSimulationAndPositions(unittest.TestCase):
    def test_position_follows_cross_sign_long(self):
        bars = _uptrend()
        trades, _ = mom.simulate(bars, _params())
        self.assertTrue(trades)
        self.assertEqual(trades[0].side, 1)  # long en uptrend

    def test_position_follows_cross_sign_short(self):
        bars = _downtrend()
        trades, _ = mom.simulate(bars, _params(allow_short=True))
        self.assertTrue(trades)
        self.assertEqual(trades[0].side, -1)  # short en downtrend

    def test_entry_executes_at_open_of_next_bar(self):
        """L'entree se fait a l'OPEN de i+1, jamais au close du signal."""
        bars = _uptrend()
        sig = mom.compute_signals(bars, _params())
        trades, _ = mom.simulate(bars, _params())
        first = trades[0]
        # Le signal a la barre first.entry_index-1 doit etre non nul.
        self.assertNotEqual(sig[first.entry_index - 1], 0)
        self.assertEqual(first.entry_price, bars[first.entry_index].open)

    def test_no_leak_ahead_mutating_last_bar(self):
        """Muter UNIQUEMENT la derniere barre ne change aucune entree passee."""
        bars = _uptrend()
        trades_a, _ = mom.simulate(bars, _params())
        entries_a = [(t.entry_index, t.side) for t in trades_a]

        mutated = list(bars)
        last = mutated[-1]
        mutated[-1] = Bar(ts=last.ts, open=last.open, high=last.high * 5,
                          low=last.low / 5, close=last.close * 3, volume=last.volume)
        trades_b, _ = mom.simulate(mutated, _params())
        entries_b = [(t.entry_index, t.side) for t in trades_b]

        # Toutes les entrees anterieures a la derniere barre sont identiques.
        n = len(bars)
        past_a = [e for e in entries_a if e[0] < n - 1]
        past_b = [e for e in entries_b if e[0] < n - 1]
        self.assertEqual(past_a, past_b)


class TestStops(unittest.TestCase):
    def test_stop_triggered_reduces_pnl(self):
        """Un stop serre coupe la perte plus tot -> PnL de trade >= sans stop.

        On fabrique un long qui part puis chute violemment. Avec un stop serre,
        la sortie est meilleure (perte bornee) qu'avec un stop tres large.
        """
        # Uptrend pour armer un long tenu, puis krach brutal en une barre.
        closes = [100.0 + i * 0.5 for i in range(300)] + [90.0]
        bars = _bars_from_closes(closes, spread=0.2)

        tight, _ = mom.simulate(bars, _params(stop_bps=200, take_bps=100000))
        loose, _ = mom.simulate(bars, _params(stop_bps=100000, take_bps=100000))

        # Trouver un trade long stoppe dans la version serree.
        stopped = [t for t in tight if t.reason == "stop" and t.side == 1]
        self.assertTrue(stopped, "aucun stop declenche dans la version serree")
        # Le stop borne la perte : le pire trade serre est meilleur que le pire large.
        worst_tight = min(t.net_return for t in tight)
        worst_loose = min(t.net_return for t in loose)
        self.assertGreater(worst_tight, worst_loose)

    def test_take_profit_can_trigger(self):
        bars = _uptrend()
        trades, _ = mom.simulate(bars, _params(take_bps=400, stop_bps=100000))
        self.assertTrue(any(t.reason == "take" for t in trades))


class TestCosts(unittest.TestCase):
    def test_costs_nonzero_and_summed_in_total(self):
        bars = _uptrend()
        ev = mom.evaluate(_params(), bars)
        c = ev.costs
        self.assertIsInstance(c, CostBreakdown)
        self.assertLess(c.fees_usd, 0.0)       # frais = charge negative
        self.assertLess(c.slippage_usd, 0.0)   # slippage = charge negative
        self.assertIsNotNone(c.funding_usd)    # jamais None
        self.assertTrue(c.liquidation_checked)
        self.assertIsNotNone(c.total_usd)      # complet => total mesurable
        # total = somme des 3 postes monetaires.
        expected = (c.fees_usd or 0.0) + (c.funding_usd or 0.0) + (c.slippage_usd or 0.0)
        self.assertAlmostEqual(c.total_usd, expected, places=9)

    def test_funding_flag_present_in_blob(self):
        bars = _uptrend()
        ev = mom.evaluate(_params(), bars)
        self.assertIn("funding_available", ev.blob)
        self.assertIsInstance(ev.blob["funding_available"], bool)
        # Si funding indisponible, il doit valoir 0.0 explicitement (jamais None).
        if not ev.blob["funding_available"]:
            self.assertEqual(ev.costs.funding_usd, 0.0)

    def test_costs_complete_even_with_no_trades(self):
        # slow_ema >= nombre de barres -> aucun signal, aucun trade.
        bars = _uptrend(n=60)
        ev = mom.evaluate(_params(slow_ema=100, regime_ema=200), bars)
        self.assertEqual(ev.closed_trades, 0)
        self.assertTrue(ev.costs.complete)
        self.assertEqual(ev.costs.total_usd, 0.0)


class TestContract(unittest.TestCase):
    def test_returns_strategyeval(self):
        bars = _uptrend()
        ev = mom.evaluate(_params(), bars)
        self.assertIsInstance(ev, StrategyEval)
        self.assertEqual(len(ev.bar_returns_per_bar), len(bars))
        self.assertEqual(ev.closed_trades, len(ev.trade_returns))
        self.assertIsInstance(ev.avg_holding_bars, int)

    def test_flat_bars_have_zero_return(self):
        bars = _uptrend()
        ev = mom.evaluate(_params(), bars)
        # Les premieres barres (warmup) sont hors position => rendement 0.
        self.assertEqual(ev.bar_returns_per_bar[0], 0.0)

    def test_deterministic(self):
        bars = _uptrend()
        a = mom.evaluate(_params(), bars)
        b = mom.evaluate(_params(), bars)
        self.assertEqual(list(a.bar_returns_per_bar), list(b.bar_returns_per_bar))
        self.assertEqual(list(a.trade_returns), list(b.trade_returns))
        self.assertEqual(a.closed_trades, b.closed_trades)
        self.assertEqual(a.avg_holding_bars, b.avg_holding_bars)
        self.assertEqual(a.costs.total_usd, b.costs.total_usd)


class TestEngineIntegration(unittest.TestCase):
    def test_evaluate_one_produces_lane_metrics(self):
        """Integration : evaluate_one juge la lane sans crash -> LaneMetrics."""
        bars = _uptrend(n=500)
        ev = mom.evaluate(_params(), bars)
        identity = LaneIdentity(
            symbol="BTCUSDT", interval="1h", side="both",
            trigger="ema_cross_8_40", execution_model="taker_market",
            leverage=3.0,
        )
        cfg = CampaignConfig(
            run_id="mom-int",
            data_snapshot_id="snap-mom-2026-08-09",
            gate_config=GateConfig(),
            walkforward_config=WalkForwardConfig(
                n_folds=3, min_train_bars=100, min_test_bars=30
            ),
        )
        metrics, gate, bench, extra = evaluate_one(identity, ev, bars, cfg,
                                                   param_sensitivity=0.1)
        self.assertIsInstance(metrics, LaneMetrics)
        self.assertEqual(metrics.closed_trades, ev.closed_trades)
        self.assertIn("walkforward", extra)
        # gate a un verdict booleen exploitable (pass/rejet), pas de crash.
        self.assertIn(gate.passed, (True, False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
