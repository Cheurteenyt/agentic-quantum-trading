"""Tests du moteur — la garantie anti-biais-de-survivance.

    python tests/test_backtest_v2_engine.py
"""
from __future__ import annotations

import math
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
    expand_grid,
    format_report,
    run_campaign,
)
from backend.services.backtest_v2.gates import Gate, GateConfig  # noqa: E402
from backend.services.backtest_v2.store import BacktestStore, LaneIdentity  # noqa: E402
from backend.services.backtest_v2.walkforward import WalkForwardConfig  # noqa: E402


def make_bars(n: int = 800) -> list[Bar]:
    """Serie synthetique deterministe : tendance douce + oscillation."""
    out = []
    for i in range(n):
        px = 100.0 + i * 0.05 + math.sin(i / 11.0) * 2.0
        out.append(Bar(ts=i * 3_600_000, open=px, high=px + 1, low=px - 1, close=px, volume=100.0))
    return out


def complete_costs() -> CostBreakdown:
    c = CostBreakdown()
    c.fees_usd = -8.0
    c.funding_usd = -3.0
    c.slippage_usd = -2.0
    c.liquidation_checked = True
    c.liquidation_safe = True
    return c


def incomplete_costs() -> CostBreakdown:
    c = CostBreakdown()
    c.fees_usd = -8.0
    c.missing.append("funding: cache perime")
    return c


def ident_for(params: dict) -> LaneIdentity:
    return LaneIdentity(
        symbol=params.get("symbol", "BTCUSDT"),
        interval=params.get("interval", "1h"),
        side="both",
        trigger=f"thr_{params.get('threshold', 1)}",
        execution_model="taker_market",
        leverage=float(params.get("leverage", 3)),
    )


def good_eval(params: dict, bars) -> StrategyEval:
    """Une lane qui passe tous les gates : rendements stables, 300 trades."""
    rets = [0.002 if i % 3 else -0.001 for i in range(len(bars))]
    equity = [100.0]
    for r in rets:
        equity.append(equity[-1] * (1 + r))
    return StrategyEval(
        bar_returns_per_bar=rets,
        closed_trades=300,
        trade_returns=[0.01] * 300,
        avg_holding_bars=5,
        costs=complete_costs(),
        microstructure_validated=True,
        equity_curve=equity,
    )


def tiny_sample_eval(params: dict, bars) -> StrategyEval:
    """La lane MOYENNE du legacy : 19 trades."""
    ev = good_eval(params, bars)
    ev.closed_trades = 19
    ev.trade_returns = [0.05] * 19
    return ev


class TestGrid(unittest.TestCase):
    def test_cartesian_product(self):
        g = list(expand_grid({"a": [1, 2], "b": ["x", "y"]}))
        self.assertEqual(len(g), 4)

    def test_deterministic_order(self):
        space = {"b": [1, 2], "a": [3, 4]}
        self.assertEqual(list(expand_grid(space)), list(expand_grid(space)))

    def test_empty_space(self):
        self.assertEqual(list(expand_grid({})), [{}])


class TestCampaign(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = BacktestStore(Path(self.tmp.name) / "c.db")
        self.bars = make_bars()
        self.cfg = CampaignConfig(
            run_id="run-test",
            data_snapshot_id="snap-test-2026-08-09",
            gate_config=GateConfig(),
            walkforward_config=WalkForwardConfig(n_folds=3, min_train_bars=100, min_test_bars=30),
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _run(self, evaluate, space=None, sens=lambda p: 0.15):
        return run_campaign(
            store=self.store,
            cfg=self.cfg,
            bars=self.bars,
            param_space=space or {"threshold": [1, 2, 3]},
            identity_for=ident_for,
            evaluate=evaluate,
            sensitivity_for=sens,
        )

    def test_every_combination_is_persisted(self):
        """LE test : rejets ecrits en base, pas seulement les gagnants.

        Le legacy testait 1 117 620 combinaisons et n'en ecrivait que les
        gagnantes. Ici, testees == lignes en base.
        """
        r = self._run(tiny_sample_eval, space={"threshold": [1, 2, 3, 4, 5]})
        n_rows = self.store.con.execute("SELECT COUNT(*) FROM lanes").fetchone()[0]
        self.assertEqual(r.tested, 5)
        self.assertEqual(n_rows, 5)
        self.assertEqual(r.accepted, 0)
        self.assertEqual(r.rejected, 5)

    def test_rejection_motive_recorded(self):
        r = self._run(tiny_sample_eval)
        self.assertIn(Gate.SAMPLE_TOO_SMALL.value, r.rejection_profile)
        rows = self.store.rejection_profile("run-test")
        self.assertTrue(any(x["motif"] == Gate.SAMPLE_TOO_SMALL.value for x in rows))

    def test_incomplete_costs_rejected(self):
        def ev(p, b):
            e = good_eval(p, b)
            e.costs = incomplete_costs()
            return e

        r = self._run(ev)
        self.assertEqual(r.accepted, 0)
        self.assertIn(Gate.COSTS_INCOMPLETE.value, r.rejection_profile)

    def test_missing_sensitivity_rejected(self):
        """Sensibilite non testee = rejet, jamais un pass par defaut."""
        r = self._run(good_eval, sens=lambda p: None)
        self.assertIn(Gate.PARAM_UNSTABLE.value, r.rejection_profile)

    def test_denominator_matches_store(self):
        r = self._run(tiny_sample_eval, space={"threshold": [1, 2, 3, 4]})
        s = self.store.run_summary("run-test")
        self.assertEqual(s["tested"], r.tested)
        self.assertEqual(s["accepted"], r.accepted)
        self.assertEqual(s["rejected"], r.rejected)
        self.assertEqual(r.errors, [])

    def test_errors_do_not_kill_campaign(self):
        """Une campagne nocturne ne meurt pas sur un cas limite."""
        def flaky(p, b):
            if p["threshold"] == 2:
                raise RuntimeError("boom")
            return tiny_sample_eval(p, b)

        r = self._run(flaky)
        self.assertEqual(r.tested, 3)
        self.assertEqual(r.errored, 1)
        self.assertTrue(any("boom" in e for e in r.errors))

    def test_stop_on_error_propagates(self):
        self.cfg.stop_on_error = True

        def boom(p, b):
            raise RuntimeError("stop")

        with self.assertRaises(RuntimeError):
            self._run(boom)

    def test_bad_identity_counted_not_hidden(self):
        def bad_ident(p):
            return LaneIdentity(
                symbol="", interval="1h", side="both", trigger="t",
                execution_model="taker_market", leverage=1.0,
            )

        r = run_campaign(
            store=self.store, cfg=self.cfg, bars=self.bars,
            param_space={"threshold": [1, 2]},
            identity_for=bad_ident, evaluate=good_eval,
            sensitivity_for=lambda p: 0.1,
        )
        self.assertEqual(r.errored, 2)
        self.assertIn(Gate.IDENTITY_INCOMPLETE.value, r.rejection_profile)

    def test_acceptance_rate_available(self):
        r = self._run(tiny_sample_eval, space={"threshold": [1, 2, 3, 4]})
        self.assertEqual(r.acceptance_rate, 0.0)
        self.assertIn("acceptance_rate", r.as_dict())

    def test_report_shows_denominator_when_empty(self):
        r = self._run(tiny_sample_eval)
        out = format_report(r)
        self.assertIn("AUCUN SURVIVANT", out)
        self.assertIn("testees", out)
        self.assertIn("Motifs de rejet", out)

    def test_survivor_must_pass_gates_and_benchmarks(self):
        """Une lane qui passe les gates mais pas les benchmarks n'est PAS
        un survivant : la vue `survivors` exige les deux."""
        r = self._run(good_eval, space={"threshold": [1]})
        rows = self.store.con.execute(
            "SELECT gate_passed, bench_passed FROM lanes"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        if rows[0]["gate_passed"] and not rows[0]["bench_passed"]:
            self.assertEqual(r.accepted, 0)
            self.assertIn("survivors", r.as_dict())

    def test_blob_isolated(self):
        self._run(tiny_sample_eval, space={"threshold": [1]})
        n = self.store.con.execute("SELECT COUNT(*) FROM lane_blobs").fetchone()[0]
        self.assertEqual(n, 1)

    def test_run_is_reproducible(self):
        """Deux campagnes identiques -> profils de rejet identiques."""
        a = self._run(tiny_sample_eval, space={"threshold": [1, 2, 3]})
        store2 = BacktestStore(Path(self.tmp.name) / "c2.db")
        self.cfg.run_id = "run-test-2"
        b = run_campaign(
            store=store2, cfg=self.cfg, bars=self.bars,
            param_space={"threshold": [1, 2, 3]},
            identity_for=ident_for, evaluate=tiny_sample_eval,
            sensitivity_for=lambda p: 0.15,
        )
        store2.close()
        self.assertEqual(a.rejection_profile, b.rejection_profile)
        self.assertEqual(a.tested, b.tested)


if __name__ == "__main__":
    unittest.main(verbosity=2)
