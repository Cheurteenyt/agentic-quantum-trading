"""Tests du moteur backtest_v2 — stdlib unittest (pytest absent de l'env).

    python -m unittest tests.test_backtest_v2 -v

Le test central est `TestLegacyRegression` : le moteur rejoue le dataset legacy
et DOIT le rejeter. S'il retrouve les +924 828 USD du legacy, c'est le moteur
qui est casse (docs/06-data.md section 8).
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.gates import (  # noqa: E402
    Gate,
    GateConfig,
    LaneMetrics,
    evaluate_benchmarks,
    evaluate_gates,
    max_drawdown_pct,
    percentile,
    random_benchmark_percentile,
    sharpe,
)
from backend.services.backtest_v2.store import (  # noqa: E402
    BacktestStore,
    IdentityError,
    LaneIdentity,
)

LEGACY_DB = ROOT / "data/warehouse/legacy_lanes.db"


def clean_metrics(**over) -> LaneMetrics:
    """Une lane qui passe tous les gates. On la degrade champ par champ."""
    base = dict(
        closed_trades=250,
        sharpe_oos=1.4,
        sharpe_is=1.8,
        max_drawdown_pct=12.0,
        fees_usd=-40.0,
        funding_usd=-15.0,
        slippage_usd=-22.0,
        liquidation_risk_checked=True,
        pnl_realized_usd=310.0,
        pnl_unrealized_usd=-8.0,
        microstructure_validated=True,
        param_sensitivity=0.18,
    )
    base.update(over)
    return LaneMetrics(**base)


def ident(**over) -> LaneIdentity:
    base = dict(
        symbol="BTCUSDT",
        interval="1h",
        side="both",
        trigger="vol_breakout_atr",
        execution_model="taker_mark",
        leverage=3.0,
    )
    base.update(over)
    return LaneIdentity(**base)


# --------------------------------------------------------------------- stats


class TestStats(unittest.TestCase):
    def test_sharpe_needs_sample(self):
        self.assertIsNone(sharpe([]))
        self.assertIsNone(sharpe([0.01]))

    def test_sharpe_zero_variance_is_none(self):
        """Variance nulle -> Sharpe infini. On renvoie None, jamais +inf."""
        self.assertIsNone(sharpe([0.01] * 50))

    def test_sharpe_positive_series(self):
        s = sharpe([0.01, -0.005, 0.02, 0.001, -0.002, 0.015])
        self.assertIsNotNone(s)
        self.assertGreater(s, 0)

    def test_max_drawdown(self):
        self.assertAlmostEqual(max_drawdown_pct([100, 120, 60, 90]), 50.0)
        self.assertAlmostEqual(max_drawdown_pct([100, 110, 120]), 0.0)
        self.assertIsNone(max_drawdown_pct([100]))

    def test_percentile(self):
        v = list(range(1, 101))
        self.assertAlmostEqual(percentile(v, 50), 50.5)
        self.assertAlmostEqual(percentile(v, 0), 1)
        self.assertAlmostEqual(percentile(v, 100), 100)
        with self.assertRaises(ValueError):
            percentile([], 50)


# --------------------------------------------------------------------- gates


class TestGates(unittest.TestCase):
    def test_clean_lane_passes(self):
        v = evaluate_gates(clean_metrics(), identity_complete=True)
        self.assertTrue(v.passed, v.detail)
        self.assertEqual(v.failures, [])

    def test_sample_too_small(self):
        v = evaluate_gates(clean_metrics(closed_trades=19), identity_complete=True)
        self.assertIn(Gate.SAMPLE_TOO_SMALL, v.failures)

    def test_legacy_average_lane_is_rejected(self):
        """La lane MOYENNE du legacy : 19 trades, WR 70 %. Doit etre rejetee."""
        v = evaluate_gates(clean_metrics(closed_trades=19), identity_complete=True)
        self.assertFalse(v.passed)
        self.assertEqual(v.primary_failure, Gate.SAMPLE_TOO_SMALL)

    def test_unmeasured_is_not_zero(self):
        """None = non mesure = rejet. Jamais un pass par defaut."""
        for field in ("fees_usd", "funding_usd", "slippage_usd"):
            with self.subTest(field=field):
                v = evaluate_gates(clean_metrics(**{field: None}), identity_complete=True)
                self.assertIn(Gate.COSTS_INCOMPLETE, v.failures)

    def test_liquidation_unchecked_rejects(self):
        v = evaluate_gates(
            clean_metrics(liquidation_risk_checked=False), identity_complete=True
        )
        self.assertIn(Gate.COSTS_INCOMPLETE, v.failures)

    def test_overfit_detected(self):
        v = evaluate_gates(
            clean_metrics(sharpe_is=2.5, sharpe_oos=0.9), identity_complete=True
        )
        self.assertIn(Gate.OVERFIT, v.failures)

    def test_missing_split_is_overfit_rejection(self):
        v = evaluate_gates(clean_metrics(sharpe_is=None), identity_complete=True)
        self.assertIn(Gate.OVERFIT, v.failures)

    def test_drawdown_gate(self):
        v = evaluate_gates(clean_metrics(max_drawdown_pct=40.0), identity_complete=True)
        self.assertIn(Gate.DRAWDOWN_TOO_DEEP, v.failures)

    def test_param_instability(self):
        v = evaluate_gates(clean_metrics(param_sensitivity=0.8), identity_complete=True)
        self.assertIn(Gate.PARAM_UNSTABLE, v.failures)

    def test_identity_incomplete(self):
        v = evaluate_gates(clean_metrics(), identity_complete=False)
        self.assertIn(Gate.IDENTITY_INCOMPLETE, v.failures)

    def test_all_failures_reported_not_just_first(self):
        """On veut TOUS les motifs : un rapport a un seul motif est inutile."""
        v = evaluate_gates(
            LaneMetrics(closed_trades=5, sharpe_oos=0.1, max_drawdown_pct=90.0),
            identity_complete=False,
        )
        self.assertGreaterEqual(len(v.failures), 5)

    def test_config_fingerprint_changes_with_thresholds(self):
        a = GateConfig().fingerprint()
        b = GateConfig(min_closed_trades=50).fingerprint()
        self.assertNotEqual(a, b)


# ---------------------------------------------------------------- benchmarks


class TestBenchmarks(unittest.TestCase):
    def test_random_benchmark_is_deterministic(self):
        pool = [0.01, -0.008, 0.015, -0.012, 0.005] * 20
        a = random_benchmark_percentile(0.5, pool, 30, seed=7)
        b = random_benchmark_percentile(0.5, pool, 30, seed=7)
        self.assertEqual(a, b)

    def test_mediocre_strategy_fails_random(self):
        """Une strategie au milieu de la distribution aleatoire = pas de bord."""
        pool = [0.01, -0.01] * 50
        v = evaluate_benchmarks(
            strategy_return=0.0,
            buy_hold_return=-0.5,
            momentum_return=-0.5,
            pool_returns=pool,
            n_trades=40,
        )
        self.assertIn(Gate.BENCH_RANDOM, v.failures)

    def test_strong_strategy_passes_random(self):
        pool = [0.01, -0.01] * 50
        v = evaluate_benchmarks(
            strategy_return=5.0,
            buy_hold_return=0.1,
            momentum_return=0.2,
            pool_returns=pool,
            n_trades=40,
        )
        self.assertTrue(v.passed, v.detail)

    def test_missing_benchmark_is_failure(self):
        v = evaluate_benchmarks(1.0, None, None, [0.01, -0.01] * 50, 20)
        self.assertIn(Gate.BENCH_BUY_HOLD, v.failures)
        self.assertIn(Gate.BENCH_MOMENTUM, v.failures)


# -------------------------------------------------------------------- store


class TestIdentity(unittest.TestCase):
    def test_valid_identity(self):
        self.assertEqual(len(ident().hash), 16)
        self.assertIn("BTCUSDT", ident().key)

    def test_empty_field_refused(self):
        with self.assertRaises(IdentityError):
            ident(symbol="")

    def test_question_mark_refused(self):
        """69,7 % du legacy avait des '?' dans l'identite. Plus jamais."""
        with self.assertRaises(IdentityError):
            ident(interval="?")

    def test_bad_leverage_refused(self):
        with self.assertRaises(IdentityError):
            ident(leverage=0)

    def test_hash_is_stable_and_discriminant(self):
        self.assertEqual(ident().hash, ident().hash)
        self.assertNotEqual(ident().hash, ident(interval="4h").hash)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = BacktestStore(Path(self.tmp.name) / "t.db")
        cfg = GateConfig()
        self.store.start_run("r1", cfg.__dict__, cfg.fingerprint(), "snap-2026-08-09")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_run_requires_data_snapshot(self):
        cfg = GateConfig()
        with self.assertRaises(ValueError):
            self.store.start_run("r2", cfg.__dict__, cfg.fingerprint(), "")

    def test_losers_are_persisted(self):
        """Regle 1 : le rejet est le chemin normal."""
        m = clean_metrics(closed_trades=8)
        g = evaluate_gates(m, identity_complete=True)
        self.assertFalse(g.passed)
        self.store.record("r1", ident(), {"closed_trades": 8}, g)
        n = self.store.con.execute("SELECT COUNT(*) FROM lanes").fetchone()[0]
        self.assertEqual(n, 1)

    def test_rejection_profile(self):
        for i, trades in enumerate([5, 9, 12, 400]):
            m = clean_metrics(closed_trades=trades)
            g = evaluate_gates(m, identity_complete=True)
            self.store.record(
                "r1", ident(symbol=f"SYM{i}USDT"), {"closed_trades": trades}, g
            )
        prof = {r["motif"]: r["n"] for r in self.store.rejection_profile("r1")}
        self.assertEqual(prof.get(Gate.SAMPLE_TOO_SMALL.value), 3)
        self.assertEqual(prof.get("passed"), 1)

    def test_unknown_metric_refused(self):
        g = evaluate_gates(clean_metrics(), identity_complete=True)
        with self.assertRaises(ValueError):
            self.store.record("r1", ident(), {"roi_magique": 999}, g)

    def test_blob_isolated_from_metrics(self):
        """Regle 3 : les blobs hors table de metriques."""
        g = evaluate_gates(clean_metrics(), identity_complete=True)
        lane_id = self.store.record(
            "r1", ident(), {"closed_trades": 250}, g, blob={"big": "x" * 5000}
        )
        cols = {r[1] for r in self.store.con.execute("PRAGMA table_info(lanes)")}
        self.assertFalse([c for c in cols if c.endswith("_json") and "gate" not in c and "bench" not in c])
        got = self.store.con.execute(
            "SELECT payload_json FROM lane_blobs WHERE lane_id=?", (lane_id,)
        ).fetchone()
        self.assertIn("big", got[0])

    def test_realized_and_unrealized_never_summed(self):
        """Regle 5 : deux cles distinctes dans le resume, jamais un total."""
        g = evaluate_gates(clean_metrics(), identity_complete=True)
        self.store.record(
            "r1", ident(),
            {"pnl_realized_usd": 100.0, "pnl_unrealized_usd": -400.0}, g,
        )
        s = self.store.run_summary("r1")
        self.assertEqual(s["pnl_realized_usd_survivors"], 100.0)
        self.assertEqual(s["pnl_unrealized_usd_survivors"], -400.0)
        self.assertNotIn("pnl_total_usd", s)

    def test_denominator_recomputed_from_rows(self):
        """Regle 6 : tested/accepted/rejected recalcules, pas tenus a la main."""
        for i, t in enumerate([5, 5, 250]):
            m = clean_metrics(closed_trades=t)
            g = evaluate_gates(m, identity_complete=True)
            b = evaluate_benchmarks(5.0, 0.1, 0.2, [0.01, -0.01] * 50, 40)
            self.store.record(
                "r1", ident(symbol=f"S{i}USDT"), {"closed_trades": t}, g, b
            )
        c = self.store.finish_run("r1")
        self.assertEqual(c["tested"], 3)
        self.assertEqual(c["accepted"], 1)
        self.assertEqual(c["rejected"], 2)

    def test_sql_check_blocks_bad_side(self):
        """Le schema lui-meme refuse, pas seulement le code Python."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.con.execute(
                "INSERT INTO lanes (run_id, schema_version, recorded_at,"
                " identity_hash, identity_key, symbol, interval, side, trigger,"
                " execution_model, leverage, gate_passed, gate_config_fingerprint)"
                " VALUES ('r1','v','t','h','k','BTC','1h','sideways','trg','ex',1,1,'fp')"
            )

    def test_sql_check_blocks_empty_symbol(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.con.execute(
                "INSERT INTO lanes (run_id, schema_version, recorded_at,"
                " identity_hash, identity_key, symbol, interval, side, trigger,"
                " execution_model, leverage, gate_passed, gate_config_fingerprint)"
                " VALUES ('r1','v','t','h','k','','1h','long','trg','ex',1,1,'fp')"
            )


# ------------------------------------------------------- regression legacy


class TestLegacyRegression(unittest.TestCase):
    """LE test. Le moteur rejoue le legacy et doit le rejeter.

    Le legacy affichait +924 828 USD sur 17 092 lanes, 100 % gagnantes.
    Si les gates laissent passer ce corpus, les gates sont casses.
    """

    @classmethod
    def setUpClass(cls):
        if not LEGACY_DB.exists():
            raise unittest.SkipTest(
                f"{LEGACY_DB} absent — lancer scripts/index_legacy_dataset.py"
            )
        cls.con = sqlite3.connect(LEGACY_DB)
        cls.con.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def _replay(self):
        rows = self.con.execute(
            "SELECT symbol, interval, side, risk_profile, execution_model,"
            " best_tradable_leverage, closed_trades, win_rate, pnl_total_usd,"
            " train_pnl_total_usd, validation_pnl_total_usd, identity_key"
            " FROM lanes"
        ).fetchall()
        passed = 0
        motifs: dict[str, int] = {}
        for r in rows:
            identity_complete = "?" not in (r["identity_key"] or "?")
            m = LaneMetrics(
                closed_trades=int(r["closed_trades"]) if r["closed_trades"] else None,
                # le legacy ne mesurait ni Sharpe OOS, ni DD %, ni couts complets,
                # ni sensibilite parametrique, ni microstructure -> None partout
            )
            v = evaluate_gates(m, identity_complete=identity_complete)
            if v.passed:
                passed += 1
            for g in v.failures:
                motifs[g.value] = motifs.get(g.value, 0) + 1
        return len(rows), passed, motifs

    def test_legacy_corpus_is_fully_rejected(self):
        total, passed, motifs = self._replay()
        print(f"\n  legacy rejoue : {total} lanes")
        for k, n in sorted(motifs.items(), key=lambda x: -x[1]):
            print(f"    {k:<32} {n:>6}  ({100*n/total:.1f} %)")
        print(f"    {'SURVIVANTS':<32} {passed:>6}")
        self.assertGreater(total, 10000, "dataset legacy incomplet")
        self.assertEqual(
            passed, 0,
            "le moteur laisse passer des lanes legacy — les gates sont casses",
        )

    def test_sample_gate_catches_the_bulk(self):
        """99,6 % du legacy a < 100 trades. Le gate doit le voir."""
        total, _, motifs = self._replay()
        small = motifs.get(Gate.SAMPLE_TOO_SMALL.value, 0)
        self.assertGreater(small / total, 0.99)

    def test_identity_gate_catches_seven_in_ten(self):
        """69,7 % du legacy a une identite incomplete."""
        total, _, motifs = self._replay()
        bad = motifs.get(Gate.IDENTITY_INCOMPLETE.value, 0)
        self.assertGreater(bad / total, 0.6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
