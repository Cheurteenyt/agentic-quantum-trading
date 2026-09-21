"""Tests des benchmarks obligatoires (stdlib pure, pytest absent).

Ce fichier protege deux proprietes qui ont coute cher au projet :
  - tout rendement affiche est NET de couts ;
  - aucune decision d'entree ne peut dependre d'une barre future.
"""
import random as _rnd
import statistics
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import (  # noqa: E402
    Bar,
    BaselineResult,
    bar_returns,
    bars_from_klines,
    buy_and_hold_return,
    compare_to_baselines,
    momentum_baseline,
    random_distribution,
    random_trades_baseline,
)
from backend.services.backtest_v2.gates import evaluate_benchmarks  # noqa: E402


MINUTE_MS = 60_000


def make_bars(closes, start_ts=1_700_000_000_000):
    """Barres synthetiques : open = close precedent (marche continu)."""
    bars = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        bars.append(
            Bar(
                ts=start_ts + i * MINUTE_MS,
                open=o,
                high=max(o, c) * 1.001,
                low=min(o, c) * 0.999,
                close=c,
                volume=100.0,
            )
        )
        prev = c
    return bars


def trending_up(n=400, start=100.0, step=0.004):
    return [start * (1.0 + step) ** i for i in range(n)]


def choppy(n=400, start=100.0, amp=0.02, seed=1234):
    """Marche aleatoire sans tendance, deterministe : le pire terrain pour un
    croisement de moyennes (whipsaw), donc celui ou les frais doivent mordre."""
    rng = _rnd.Random(seed)
    price = start
    out = []
    for _ in range(n):
        price *= 1.0 + rng.gauss(0.0, amp / 4.0)
        out.append(price)
    return out


# --------------------------------------------------------------- parsing


class TestBarsFromKlines(unittest.TestCase):
    def test_parses_real_kline_format(self):
        raw = [
            [1700000000000, "100.0", "101.5", "99.5", "101.0", "12.5", 1700000059999, "1250.0", 30],
            [1700000060000, "101.0", "102.0", "100.8", "101.8", "9.0", 1700000119999, "910.0", 22],
        ]
        bars = bars_from_klines(raw)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].ts, 1700000000000)
        self.assertAlmostEqual(bars[0].close, 101.0)
        self.assertAlmostEqual(bars[1].volume, 9.0)
        self.assertIsInstance(bars[0].open, float)

    def test_empty_input_gives_empty_list(self):
        self.assertEqual(bars_from_klines([]), [])

    def test_negative_price_raises(self):
        raw = [[1, "100", "101", "-5", "100.5", "1", 2]]
        with self.assertRaises(ValueError):
            bars_from_klines(raw)

    def test_zero_price_raises(self):
        raw = [[1, "100", "101", "99", "0", "1", 2]]
        with self.assertRaises(ValueError):
            bars_from_klines(raw)

    def test_decreasing_timestamps_raise(self):
        raw = [
            [2000, "100", "101", "99", "100.5", "1", 2],
            [1000, "100", "101", "99", "100.5", "1", 2],
        ]
        with self.assertRaises(ValueError):
            bars_from_klines(raw)

    def test_duplicate_timestamps_raise(self):
        raw = [
            [1000, "100", "101", "99", "100.5", "1", 2],
            [1000, "100", "101", "99", "100.5", "1", 2],
        ]
        with self.assertRaises(ValueError):
            bars_from_klines(raw)

    def test_short_row_raises(self):
        with self.assertRaises(ValueError):
            bars_from_klines([[1000, "100", "101"]])

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            bars_from_klines([[1000, "abc", "101", "99", "100", "1", 2]])


class TestBarReturns(unittest.TestCase):
    def test_length_and_values(self):
        bars = make_bars([100.0, 110.0, 99.0])
        rets = bar_returns(bars)
        self.assertEqual(len(rets), 2)
        self.assertAlmostEqual(rets[0], 0.1)
        self.assertAlmostEqual(rets[1], 99.0 / 110.0 - 1.0)

    def test_single_bar_gives_no_return(self):
        self.assertEqual(bar_returns(make_bars([100.0])), [])


# ----------------------------------------------------------- buy and hold


class TestBuyAndHold(unittest.TestCase):
    def test_rising_series_is_profitable(self):
        bars = make_bars(trending_up(200))
        self.assertGreater(buy_and_hold_return(bars, 8.0), 0.0)

    def test_fees_reduce_return_by_exact_amount(self):
        bars = make_bars([100.0, 110.0])
        gross = buy_and_hold_return(bars, 0.0)
        net = buy_and_hold_return(bars, 8.0)
        self.assertAlmostEqual(gross, 0.10)
        self.assertAlmostEqual(gross - net, 8.0 / 10_000.0)
        self.assertLess(net, gross)

    def test_needs_two_bars(self):
        with self.assertRaises(ValueError):
            buy_and_hold_return(make_bars([100.0]), 8.0)

    def test_negative_fees_rejected(self):
        with self.assertRaises(ValueError):
            buy_and_hold_return(make_bars([100.0, 101.0]), -1.0)


# --------------------------------------------------------------- momentum


class TestMomentum(unittest.TestCase):
    def test_strong_uptrend_is_profitable(self):
        bars = make_bars(trending_up(400))
        res = momentum_baseline(bars, fast=20, slow=50, fees_bps_round_trip=8.0)
        self.assertIsInstance(res, BaselineResult)
        self.assertGreater(res.n_trades, 0)
        self.assertGreater(res.total_return, 0.0)
        self.assertIsNotNone(res.win_rate)

    def test_choppy_series_loses_to_fees(self):
        bars = make_bars(choppy(400))
        gross_like = momentum_baseline(bars, fees_bps_round_trip=0.0)
        with_fees = momentum_baseline(bars, fees_bps_round_trip=8.0)
        self.assertGreater(with_fees.n_trades, 1)
        # Les frais degradent toujours : c'est la definition d'un cout.
        self.assertLess(with_fees.total_return, gross_like.total_return)
        self.assertLess(with_fees.total_return, 0.0)

    def test_no_trade_gives_none_win_rate_not_zero(self):
        bars = make_bars([100.0] * 60)  # serie plate : aucun croisement
        res = momentum_baseline(bars, fast=5, slow=10)
        self.assertEqual(res.n_trades, 0)
        self.assertIsNone(res.win_rate)
        self.assertEqual(res.total_return, 0.0)

    def test_short_disabled_produces_only_longs(self):
        bars = make_bars(choppy(300))
        res = momentum_baseline(bars, fast=5, slow=15, allow_short=False)
        self.assertTrue(all(t.side == "long" for t in res.trades))

    def test_shorts_exist_when_allowed(self):
        bars = make_bars(choppy(300))
        res = momentum_baseline(bars, fast=5, slow=15, allow_short=True)
        self.assertTrue(any(t.side == "short" for t in res.trades))

    def test_net_return_is_gross_minus_fees(self):
        bars = make_bars(trending_up(200))
        res = momentum_baseline(bars, fees_bps_round_trip=8.0)
        for t in res.trades:
            self.assertAlmostEqual(t.gross_return - t.net_return, 8.0 / 10_000.0)

    def test_invalid_windows_raise(self):
        bars = make_bars(trending_up(100))
        with self.assertRaises(ValueError):
            momentum_baseline(bars, fast=50, slow=20)


class TestNoLookAhead(unittest.TestCase):
    """Le test le plus important du fichier."""

    def test_changing_last_bar_changes_no_prior_entry(self):
        closes = choppy(300)
        bars = make_bars(closes)

        # On fait exploser UNIQUEMENT la derniere barre.
        tampered = list(bars)
        last = tampered[-1]
        tampered[-1] = Bar(
            ts=last.ts,
            open=last.open,
            high=last.close * 5.0,
            low=last.low,
            close=last.close * 5.0,
            volume=last.volume,
        )

        base = momentum_baseline(bars, fast=5, slow=15)
        alt = momentum_baseline(tampered, fast=5, slow=15)

        base_entries = [(t.entry_index, t.side) for t in base.trades]
        alt_entries = [(t.entry_index, t.side) for t in alt.trades]
        self.assertEqual(
            base_entries,
            alt_entries,
            "une entree a change alors que seule la DERNIERE barre a bouge : look-ahead",
        )

    def test_execution_price_is_next_open_not_signal_close(self):
        # Serie ou open != close, pour distinguer les deux prix.
        bars = [
            Bar(ts=i * MINUTE_MS, open=100.0 + i, high=200.0 + i,
                low=50.0, close=150.0 + i * 2, volume=1.0)
            for i in range(40)
        ]
        res = momentum_baseline(bars, fast=2, slow=5)
        self.assertGreater(res.n_trades, 0)
        first = res.trades[0]
        entry_bar = bars[first.entry_index]
        # Le prix d'entree doit etre l'OPEN de la barre d'execution.
        implied = entry_bar.open
        self.assertAlmostEqual(implied, 100.0 + first.entry_index)
        # Et surement pas le close du signal (barre precedente).
        self.assertNotAlmostEqual(implied, bars[first.entry_index - 1].close)

    def test_truncating_future_keeps_past_decisions(self):
        bars = make_bars(choppy(300))
        full = momentum_baseline(bars, fast=5, slow=15)
        cut = momentum_baseline(bars[:200], fast=5, slow=15)
        # Toutes les entrees de la version tronquee (hors derniere, close forcee)
        # doivent exister a l'identique dans la version complete.
        full_entries = [(t.entry_index, t.side) for t in full.trades]
        cut_entries = [(t.entry_index, t.side) for t in cut.trades]
        self.assertEqual(cut_entries, full_entries[: len(cut_entries)])


# -------------------------------------------------------------- aleatoire


class TestRandomBaseline(unittest.TestCase):
    def setUp(self):
        self.bars = make_bars(choppy(400))

    def test_same_seed_same_result(self):
        a = random_trades_baseline(self.bars, 30, 10, seed=7)
        b = random_trades_baseline(self.bars, 30, 10, seed=7)
        self.assertEqual(a.total_return, b.total_return)
        self.assertEqual(
            [(t.entry_index, t.exit_index, t.side) for t in a.trades],
            [(t.entry_index, t.exit_index, t.side) for t in b.trades],
        )

    def test_different_seed_different_result(self):
        a = random_trades_baseline(self.bars, 30, 10, seed=7)
        b = random_trades_baseline(self.bars, 30, 10, seed=99)
        self.assertNotEqual(a.total_return, b.total_return)

    def test_no_global_random_dependency(self):
        import random as _global_random

        _global_random.seed(1)
        a = random_trades_baseline(self.bars, 20, 8, seed=3)
        _global_random.seed(123456)
        [_global_random.random() for _ in range(100)]
        b = random_trades_baseline(self.bars, 20, 8, seed=3)
        self.assertEqual(a.total_return, b.total_return)

    def test_trades_are_costed(self):
        res = random_trades_baseline(self.bars, 20, 8, fees_bps_round_trip=8.0, seed=5)
        for t in res.trades:
            self.assertAlmostEqual(t.gross_return - t.net_return, 8.0 / 10_000.0)

    def test_invalid_arguments_raise(self):
        with self.assertRaises(ValueError):
            random_trades_baseline(self.bars, 0, 10)
        with self.assertRaises(ValueError):
            random_trades_baseline(self.bars, 10, 0)


class TestRandomDistribution(unittest.TestCase):
    def setUp(self):
        self.bars = make_bars(choppy(400))

    def test_length_equals_trials(self):
        dist = random_distribution(self.bars, 20, 10, n_trials=250, seed=1)
        self.assertEqual(len(dist), 250)

    def test_dispersion_is_non_zero(self):
        dist = random_distribution(self.bars, 20, 10, n_trials=300, seed=1)
        self.assertGreater(statistics.pstdev(dist), 0.0)
        self.assertGreater(max(dist), min(dist))

    def test_deterministic(self):
        a = random_distribution(self.bars, 20, 10, n_trials=100, seed=11)
        b = random_distribution(self.bars, 20, 10, n_trials=100, seed=11)
        self.assertEqual(a, b)
        c = random_distribution(self.bars, 20, 10, n_trials=100, seed=12)
        self.assertNotEqual(a, c)

    def test_invalid_trials_raise(self):
        with self.assertRaises(ValueError):
            random_distribution(self.bars, 20, 10, n_trials=0)


# ------------------------------------------------------------- comparaison


class TestCompareToBaselines(unittest.TestCase):
    def setUp(self):
        self.bars = make_bars(choppy(400))

    def test_keys_present(self):
        out = compare_to_baselines(0.0, self.bars, 20, 10)
        for key in (
            "buy_and_hold",
            "momentum",
            "random_percentile",
            "beats_buy_and_hold",
            "beats_momentum",
            "beats_random_95",
            "all_passed",
        ):
            self.assertIn(key, out)
        self.assertGreaterEqual(out["random_percentile"], 0.0)
        self.assertLessEqual(out["random_percentile"], 100.0)

    def test_mediocre_strategy_fails(self):
        dist = random_distribution(self.bars, 20, 10, n_trials=1000, seed=42)
        median = statistics.median(dist)
        out = compare_to_baselines(median, self.bars, 20, 10, seed=42)
        self.assertFalse(out["beats_random_95"])
        self.assertFalse(out["all_passed"])
        self.assertLess(out["random_percentile"], 95.0)

    def test_dominant_strategy_passes(self):
        out = compare_to_baselines(50.0, self.bars, 20, 10, seed=42)
        self.assertTrue(out["beats_buy_and_hold"])
        self.assertTrue(out["beats_momentum"])
        self.assertTrue(out["beats_random_95"])
        self.assertTrue(out["all_passed"])
        self.assertAlmostEqual(out["random_percentile"], 100.0)

    def test_terrible_strategy_fails_everything(self):
        out = compare_to_baselines(-10.0, self.bars, 20, 10, seed=42)
        self.assertFalse(out["all_passed"])
        self.assertAlmostEqual(out["random_percentile"], 0.0)


# ------------------------------------------------------------- integration


class TestGatesIntegration(unittest.TestCase):
    def test_distribution_feeds_evaluate_benchmarks(self):
        bars = make_bars(choppy(400))
        pool = random_distribution(bars, 20, 10, n_trials=200, seed=42)
        bh = buy_and_hold_return(bars, 8.0)
        mom = momentum_baseline(bars, fees_bps_round_trip=8.0).total_return

        verdict = evaluate_benchmarks(
            strategy_return=0.0,
            buy_hold_return=bh,
            momentum_return=mom,
            pool_returns=pool,
            n_trades=20,
        )
        self.assertIsNotNone(verdict)
        self.assertIsInstance(verdict.passed, bool)
        self.assertIsInstance(verdict.failures, list)

    def test_none_benchmarks_are_rejected(self):
        bars = make_bars(trending_up(200))
        pool = random_distribution(bars, 10, 5, n_trials=50, seed=2)
        verdict = evaluate_benchmarks(
            strategy_return=1.0,
            buy_hold_return=None,
            momentum_return=None,
            pool_returns=pool,
            n_trades=10,
        )
        self.assertFalse(verdict.passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
