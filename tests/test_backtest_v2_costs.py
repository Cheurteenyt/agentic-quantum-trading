"""Tests du module costs — les 4 postes de cout.

    python tests/test_backtest_v2_costs.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.costs import (  # noqa: E402
    MAX_FUNDING_AGE_DAYS,
    CostDataUnavailable,
    check_liquidation,
    compute_costs,
    fee_bps,
    funding_cost_usd,
    load_funding_rate,
    quote_asset,
    round_trip_fees_usd,
    slippage_from_spread_usd,
    slippage_usd,
)

REAL_FUNDING_CACHE = (
    ROOT / "backend/services/onchain/aster/aster_public_funding_history_cache.json"
)


def fresh_cache(tmpdir: str, symbol="BTCUSDT", avg_bps=1.0, count=100, age_days=0.0):
    p = Path(tmpdir) / "funding.json"
    p.write_text(
        json.dumps(
            {
                "symbols": {
                    symbol: {
                        "cached_at": time.time() - age_days * 86400,
                        "data": {
                            "status": "ok",
                            "avg_funding_bps_per_8h": avg_bps,
                            "funding_count": count,
                            "last_funding_time": 1780387200000,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return p


class TestFees(unittest.TestCase):
    def test_quote_asset(self):
        self.assertEqual(quote_asset("BTCUSDT"), "USDT")
        self.assertEqual(quote_asset("BTCUSD1"), "USD1")
        self.assertEqual(quote_asset("WEIRD"), "UNKNOWN")

    def test_taker_vs_maker(self):
        self.assertEqual(fee_bps("BTCUSDT", "taker_market"), 4.0)
        self.assertEqual(fee_bps("BTCUSDT", "maker_post_only"), 0.0)

    def test_execution_model_changes_cost_8x(self):
        """Supposer maker quand on execute taker divise le cout par 8 sur USDT.
        C'est pour ca que execution_model fait partie de l'identite de lane."""
        taker = round_trip_fees_usd(10_000, "BTCUSDT", "taker_market")
        maker = round_trip_fees_usd(10_000, "BTCUSDT", "maker_post_only")
        self.assertAlmostEqual(taker, -8.0)
        self.assertAlmostEqual(maker, 0.0)

    def test_fees_always_negative(self):
        self.assertLess(round_trip_fees_usd(1000, "BTCUSDT", "taker_market"), 0)

    def test_unknown_quote_uses_worst_case(self):
        self.assertEqual(fee_bps("WEIRD", "taker_market"), 4.0)

    def test_bad_notional(self):
        with self.assertRaises(ValueError):
            round_trip_fees_usd(0, "BTCUSDT", "taker_market")


class TestFunding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_fresh(self):
        r = load_funding_rate("BTCUSDT", fresh_cache(self.tmp.name))
        self.assertEqual(r.sample_count, 100)
        self.assertFalse(r.is_stale)

    def test_stale_cache_raises(self):
        """Le cache reel est gele depuis juin 2026. Refus explicite."""
        p = fresh_cache(self.tmp.name, age_days=MAX_FUNDING_AGE_DAYS + 5)
        with self.assertRaises(CostDataUnavailable) as ctx:
            load_funding_rate("BTCUSDT", p)
        self.assertIn("rafraichir", str(ctx.exception))

    def test_missing_symbol_raises(self):
        with self.assertRaises(CostDataUnavailable):
            load_funding_rate("NOPEUSDT", fresh_cache(self.tmp.name))

    def test_real_project_cache_respects_freshness_contract(self):
        """Le VRAI cache du projet : accepte s'il est frais, refuse s'il est perime.

        La version initiale de ce test affirmait "le cache reel est perime".
        C'etait figer un ETAT temporaire, pas une invariante : le jour ou
        `scripts/refresh_aster_cache.py` a rafraichi les caches, le test a
        casse alors que le systeme s'etait AMELIORE.

        Un test doit verrouiller une propriete, pas une photo. La propriete
        ici : la fraicheur du cache et la decision de costs.py sont toujours
        coherentes, dans les deux sens.
        """
        if not REAL_FUNDING_CACHE.exists():
            self.skipTest("cache reel absent")

        blob = json.loads(REAL_FUNDING_CACHE.read_text(encoding="utf-8"))
        entry = (blob.get("symbols") or {}).get("BTCUSDT")
        if not entry:
            self.skipTest("BTCUSDT absent du cache reel")

        age_days = (time.time() - float(entry.get("cached_at") or 0)) / 86400.0

        if age_days > MAX_FUNDING_AGE_DAYS:
            with self.assertRaises(CostDataUnavailable):
                load_funding_rate("BTCUSDT", REAL_FUNDING_CACHE)
        else:
            rate = load_funding_rate("BTCUSDT", REAL_FUNDING_CACHE)
            self.assertFalse(rate.is_stale)
            self.assertGreater(rate.sample_count, 0)

    def test_empty_funding_history_is_refused_not_zeroed(self):
        """funding_count = 0 ne doit JAMAIS devenir un funding de 0.

        Certains symboles (BONK, FLOKI, MEME, SHIB au 2026-08-09) renvoient un
        historique vide. Les traiter comme un cout nul offrirait un avantage
        gratuit a exactement les paires les plus volatiles.
        """
        p = Path(self.tmp.name) / "empty.json"
        p.write_text(
            json.dumps(
                {
                    "symbols": {
                        "FLOKIUSDT": {
                            "cached_at": time.time(),
                            "data": {
                                "status": "empty",
                                "avg_funding_bps_per_8h": 0.0,
                                "funding_count": 0,
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(CostDataUnavailable):
            load_funding_rate("FLOKIUSDT", p)

    def test_funding_applies_to_notional_not_margin(self):
        """L'erreur du legacy : funding sur la marge au lieu du notionnel.
        Avec levier 5, le vrai cout est 5x l'estimation erronee."""
        r = load_funding_rate("BTCUSDT", fresh_cache(self.tmp.name, avg_bps=10.0))
        notional, leverage = 50_000.0, 5.0
        margin = notional / leverage

        correct = funding_cost_usd(notional, 24.0, "long", r)
        wrong = funding_cost_usd(margin, 24.0, "long", r)
        self.assertAlmostEqual(correct / wrong, leverage)
        self.assertAlmostEqual(correct, -150.0)  # 50000 * 0.001 * 3 periodes

    def test_long_pays_short_receives(self):
        r = load_funding_rate("BTCUSDT", fresh_cache(self.tmp.name, avg_bps=5.0))
        self.assertLess(funding_cost_usd(10_000, 8.0, "long", r), 0)
        self.assertGreater(funding_cost_usd(10_000, 8.0, "short", r), 0)

    def test_side_both_refused(self):
        """'both' n'a pas de signe de funding : doit etre resolu par trade."""
        r = load_funding_rate("BTCUSDT", fresh_cache(self.tmp.name))
        with self.assertRaises(ValueError):
            funding_cost_usd(10_000, 8.0, "both", r)

    def test_scales_with_holding_time(self):
        r = load_funding_rate("BTCUSDT", fresh_cache(self.tmp.name, avg_bps=8.0))
        c8 = funding_cost_usd(10_000, 8.0, "long", r)
        c24 = funding_cost_usd(10_000, 24.0, "long", r)
        self.assertAlmostEqual(c24 / c8, 3.0)


class TestSlippage(unittest.TestCase):
    BOOK = [(100.0, 10.0), (100.5, 20.0), (101.0, 50.0)]

    def test_no_slippage_when_filled_at_reference(self):
        """Ordre absorbe par le premier niveau AU prix de reference -> 0.

        Physiquement correct, mais PIEGE : cela suppose que `reference_price`
        est deja le prix executable (best ask a l'achat). Si on passe un mid,
        le demi-spread disparait du calcul. Voir la note dans slippage_usd().
        """
        self.assertAlmostEqual(slippage_usd(500.0, self.BOOK, 100.0), 0.0)

    def test_slippage_appears_when_crossing_levels(self):
        s = slippage_usd(2000.0, self.BOOK, 100.0)
        self.assertLess(s, 0)

    def test_bigger_order_costs_more(self):
        small = slippage_usd(500.0, self.BOOK, 100.0)
        big = slippage_usd(3000.0, self.BOOK, 100.0)
        self.assertLess(big, small)

    def test_order_exceeding_book_raises(self):
        """Une lane non executable n'est pas une lane."""
        with self.assertRaises(CostDataUnavailable) as ctx:
            slippage_usd(1_000_000.0, self.BOOK, 100.0)
        self.assertIn("non executable", str(ctx.exception))

    def test_empty_book_raises(self):
        with self.assertRaises(CostDataUnavailable):
            slippage_usd(100.0, [], 100.0)

    def test_spread_fallback(self):
        s = slippage_from_spread_usd(10_000.0, 4.0)
        self.assertAlmostEqual(s, -2.0)


class TestLiquidation(unittest.TestCase):
    def test_safe_position(self):
        c = check_liquidation(100.0, "long", 3.0, 0.005, worst_adverse_pct=5.0)
        self.assertTrue(c.safe)
        self.assertAlmostEqual(c.distance_pct, 32.83, places=1)

    def test_liquidated_position(self):
        c = check_liquidation(100.0, "long", 20.0, 0.005, worst_adverse_pct=10.0)
        self.assertFalse(c.safe)
        self.assertIn("liquidee", c.reason)

    def test_leverage_incompatible_with_maintenance(self):
        c = check_liquidation(100.0, "long", 250.0, 0.005, worst_adverse_pct=0.1)
        self.assertFalse(c.safe)
        self.assertIn("immediate", c.reason)

    def test_short_liq_price_above_entry(self):
        c = check_liquidation(100.0, "short", 5.0, 0.005, worst_adverse_pct=1.0)
        self.assertGreater(c.liquidation_price, 100.0)

    def test_long_liq_price_below_entry(self):
        c = check_liquidation(100.0, "long", 5.0, 0.005, worst_adverse_pct=1.0)
        self.assertLess(c.liquidation_price, 100.0)


class TestCostBreakdown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = fresh_cache(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _full(self, **over):
        args = dict(
            notional_usd=10_000.0,
            symbol="BTCUSDT",
            side="long",
            execution_model="taker_market",
            holding_hours=12.0,
            entry_price=100.0,
            leverage=3.0,
            maintenance_margin_rate=0.005,
            worst_adverse_pct=5.0,
            spread_bps=4.0,
            funding_cache=self.cache,
        )
        args.update(over)
        return compute_costs(**args)

    def test_complete_breakdown(self):
        c = self._full()
        self.assertTrue(c.complete, c.missing)
        self.assertIsNotNone(c.total_usd)
        self.assertLess(c.total_usd, 0)

    def test_partial_total_is_none(self):
        """Un total partiel a l'air d'un chiffre et sous-estime systematiquement."""
        c = self._full(spread_bps=None)
        self.assertFalse(c.complete)
        self.assertIsNone(c.total_usd)
        self.assertTrue(any("slippage" in m for m in c.missing))

    def test_stale_funding_marks_incomplete(self):
        stale = fresh_cache(self.tmp.name, age_days=200)
        c = self._full(funding_cache=stale)
        self.assertFalse(c.complete)
        self.assertTrue(any("funding" in m for m in c.missing))

    def test_missing_liquidation_inputs(self):
        c = self._full(worst_adverse_pct=None)
        self.assertFalse(c.liquidation_checked)
        self.assertFalse(c.complete)

    def test_liquidated_lane_flagged_unsafe(self):
        c = self._full(leverage=20.0, worst_adverse_pct=10.0)
        self.assertTrue(c.liquidation_checked)
        self.assertFalse(c.liquidation_safe)
        self.assertFalse(c.as_metrics()["liquidation_checked"])

    def test_book_preferred_over_spread(self):
        c = self._full(book_levels=[(100.0, 500.0)])
        self.assertFalse(any("demi-spread" in w for w in c.warnings))

    def test_spread_fallback_warns(self):
        c = self._full()
        self.assertTrue(any("demi-spread" in w for w in c.warnings))

    def test_as_metrics_feeds_gates(self):
        """Integration : un breakdown complet doit satisfaire le gate couts."""
        from backend.services.backtest_v2.gates import Gate, LaneMetrics, evaluate_gates

        c = self._full()
        m = LaneMetrics(
            closed_trades=250, sharpe_oos=1.4, sharpe_is=1.8,
            max_drawdown_pct=12.0, param_sensitivity=0.2,
            microstructure_validated=True,
            **{k: v for k, v in c.as_metrics().items() if k != "liquidation_checked"},
            liquidation_risk_checked=c.as_metrics()["liquidation_checked"],
        )
        v = evaluate_gates(m, identity_complete=True)
        self.assertNotIn(Gate.COSTS_INCOMPLETE, v.failures)
        self.assertTrue(v.passed, v.detail)

    def test_incomplete_costs_reach_the_gate(self):
        from backend.services.backtest_v2.gates import Gate, LaneMetrics, evaluate_gates

        c = self._full(spread_bps=None)
        m = LaneMetrics(
            closed_trades=250, sharpe_oos=1.4, sharpe_is=1.8,
            max_drawdown_pct=12.0, param_sensitivity=0.2,
            microstructure_validated=True,
            fees_usd=c.fees_usd, funding_usd=c.funding_usd,
            slippage_usd=c.slippage_usd,
            liquidation_risk_checked=c.as_metrics()["liquidation_checked"],
        )
        v = evaluate_gates(m, identity_complete=True)
        self.assertIn(Gate.COSTS_INCOMPLETE, v.failures)


if __name__ == "__main__":
    unittest.main(verbosity=2)
