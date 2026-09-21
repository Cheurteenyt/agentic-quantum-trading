"""Tests du walk-forward — stdlib unittest (pytest absent de l'env).

    python tests/test_backtest_v2_walkforward.py

Ces tests protegent le gate le plus discriminant du projet : si le split
train/validation fuit, TOUT le reste du pipeline redevient un generateur de
resultats flatteurs (docs/03-methodology.md sections 2.2 et 3).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.gates import (  # noqa: E402
    Gate,
    GateConfig,
    LaneMetrics,
    evaluate_gates,
)
from backend.services.backtest_v2.walkforward import (  # noqa: E402
    Fold,
    WalkForwardConfig,
    WalkForwardResult,
    make_folds,
    param_sensitivity,
    run_walkforward,
)

N_BARS = 1000


# ---------------------------------------------------------------- geometrie


class TestFoldGeometry(unittest.TestCase):
    def test_rolling_train_start_advances(self):
        """En rolling, la fenetre glisse : le passe lointain est oublie."""
        folds = make_folds(N_BARS, WalkForwardConfig(anchored=False))
        starts = [f.train_start for f in folds]
        self.assertEqual(starts, sorted(starts))
        self.assertLess(starts[0], starts[-1])
        # taille de train constante : c'est la definition d'une fenetre glissante
        self.assertEqual(len({f.train_bars for f in folds}), 1)

    def test_anchored_train_start_is_constant(self):
        """En anchored (expanding), le train part toujours de la barre 0."""
        folds = make_folds(N_BARS, WalkForwardConfig(anchored=True))
        self.assertTrue(all(f.train_start == 0 for f in folds))
        # ... et il grossit fold apres fold
        sizes = [f.train_bars for f in folds]
        self.assertEqual(sizes, sorted(sizes))
        self.assertLess(sizes[0], sizes[-1])

    def test_number_of_folds_respected(self):
        for n in (1, 2, 3, 5):
            with self.subTest(n_folds=n):
                folds = make_folds(N_BARS, WalkForwardConfig(n_folds=n))
                self.assertEqual(len(folds), n)
                self.assertEqual([f.index for f in folds], list(range(n)))

    def test_test_segments_are_disjoint_and_ordered(self):
        """Une barre ne doit etre comptee qu'une fois en OOS, sinon on gonfle
        artificiellement la taille de l'echantillon hors echantillon."""
        folds = make_folds(N_BARS, WalkForwardConfig())
        for prev, nxt in zip(folds, folds[1:]):
            self.assertLessEqual(prev.test_end, nxt.test_start)

    def test_bounds_stay_inside_series(self):
        for anchored in (False, True):
            for embargo in (0, 25):
                cfg = WalkForwardConfig(anchored=anchored, embargo_bars=embargo)
                for f in make_folds(N_BARS, cfg):
                    with self.subTest(anchored=anchored, embargo=embargo, i=f.index):
                        self.assertGreaterEqual(f.train_start, 0)
                        self.assertLessEqual(f.test_end, N_BARS)
                        self.assertGreater(f.train_bars, 0)
                        self.assertGreater(f.test_bars, 0)

    def test_minimums_are_enforced(self):
        cfg = WalkForwardConfig()
        for f in make_folds(N_BARS, cfg):
            self.assertGreaterEqual(f.train_bars, cfg.min_train_bars)
            self.assertGreaterEqual(f.test_bars, cfg.min_test_bars)


# ------------------------------------------------------------- anti-leakage


class TestNoLeakage(unittest.TestCase):
    """Le coeur du module : aucune barre de test ne doit avoir servi au train."""

    def test_train_and_test_never_overlap(self):
        for anchored in (False, True):
            for embargo in (0, 5, 40):
                cfg = WalkForwardConfig(anchored=anchored, embargo_bars=embargo)
                for f in make_folds(N_BARS, cfg):
                    train_idx = set(range(f.train_start, f.train_end))
                    test_idx = set(range(f.test_start, f.test_end))
                    with self.subTest(anchored=anchored, embargo=embargo, i=f.index):
                        self.assertEqual(
                            train_idx & test_idx,
                            set(),
                            "chevauchement train/test = leakage",
                        )
                        self.assertLessEqual(f.train_end, f.test_start)

    def test_embargo_gap_is_real(self):
        """Le trou mesure entre train_end et test_start vaut exactement l'embargo."""
        for embargo in (0, 10, 50):
            for anchored in (False, True):
                cfg = WalkForwardConfig(anchored=anchored, embargo_bars=embargo)
                for f in make_folds(N_BARS, cfg):
                    with self.subTest(embargo=embargo, anchored=anchored, i=f.index):
                        self.assertEqual(f.test_start - f.train_end, embargo)

    def test_embargoed_bars_belong_to_nobody(self):
        """Les barres d'embargo ne sont ni dans le train ni dans le test du fold."""
        cfg = WalkForwardConfig(embargo_bars=20)
        for f in make_folds(N_BARS, cfg):
            for i in range(f.train_end, f.test_start):
                self.assertFalse(f.train_start <= i < f.train_end)
                self.assertFalse(f.test_start <= i < f.test_end)

    def test_returns_slices_match_fold_bounds(self):
        """run_walkforward doit decouper exactement ce que make_folds annonce."""
        series = [0.01 * ((i % 7) - 3) for i in range(N_BARS)]
        res = run_walkforward(series, WalkForwardConfig(embargo_bars=15))
        for f, tr, te in zip(res.folds, res.train_returns, res.test_returns):
            self.assertEqual(tr, series[f.train_start:f.train_end])
            self.assertEqual(te, series[f.test_start:f.test_end])
            self.assertEqual(len(tr), f.train_bars)
            self.assertEqual(len(te), f.test_bars)


# ------------------------------------------------------------------ refus


class TestInsufficientData(unittest.TestCase):
    def test_too_few_bars_raises(self):
        """Mieux vaut aucun resultat qu'un resultat sur 40 barres."""
        with self.assertRaises(ValueError):
            make_folds(120, WalkForwardConfig())

    def test_zero_bars_raises(self):
        with self.assertRaises(ValueError):
            make_folds(0, WalkForwardConfig())

    def test_embargo_eating_everything_raises(self):
        with self.assertRaises(ValueError):
            make_folds(300, WalkForwardConfig(embargo_bars=500))

    def test_invalid_config_raises(self):
        for cfg in (
            WalkForwardConfig(n_folds=0),
            WalkForwardConfig(train_ratio=0.0),
            WalkForwardConfig(train_ratio=1.0),
            WalkForwardConfig(embargo_bars=-1),
        ):
            with self.subTest(cfg=cfg):
                with self.assertRaises(ValueError):
                    make_folds(N_BARS, cfg)


# ------------------------------------------------------------- fingerprint


class TestFingerprint(unittest.TestCase):
    def test_stable_and_short(self):
        self.assertEqual(len(WalkForwardConfig().fingerprint()), 12)
        self.assertEqual(
            WalkForwardConfig().fingerprint(), WalkForwardConfig().fingerprint()
        )

    def test_changes_with_protocol(self):
        base = WalkForwardConfig().fingerprint()
        self.assertNotEqual(base, WalkForwardConfig(n_folds=7).fingerprint())
        self.assertNotEqual(base, WalkForwardConfig(anchored=True).fingerprint())
        self.assertNotEqual(base, WalkForwardConfig(embargo_bars=5).fingerprint())


# --------------------------------------------------------- detection overfit


def _overfit_series(cfg: WalkForwardConfig, n_bars: int = N_BARS) -> list[float]:
    """Serie construite pour etre brillante en train et nulle en test.

    C'est la signature exacte d'une strategie sur-optimisee : les parametres
    ont ete choisis sur le train, ils ne transferent pas.
    """
    folds = make_folds(n_bars, cfg)
    series = [0.0] * n_bars
    # valeurs deterministes (aucun random) alternees pour donner de la variance
    for i in range(n_bars):
        series[i] = 0.001 if i % 2 == 0 else -0.0012  # neutre par defaut
    for f in folds:
        for i in range(f.train_start, f.train_end):
            series[i] = 0.020 if i % 2 == 0 else 0.010
    for f in folds:
        for i in range(f.test_start, f.test_end):
            series[i] = -0.010 if i % 2 == 0 else 0.005
    return series


class TestOverfitDetection(unittest.TestCase):
    def test_brilliant_train_dead_test_is_flagged(self):
        cfg = WalkForwardConfig()
        res = run_walkforward(_overfit_series(cfg), cfg)
        self.assertIsNotNone(res.sharpe_is)
        self.assertIsNotNone(res.sharpe_oos)
        self.assertGreater(res.sharpe_is, 0)
        self.assertIsNotNone(res.oos_is_ratio)
        self.assertLess(
            res.oos_is_ratio,
            GateConfig().min_oos_is_ratio,
            "un overfit evident doit sortir sous le seuil 0.6",
        )

    def test_homogeneous_series_keeps_ratio_near_one(self):
        """Meme regime partout : le OOS doit reproduire le IS."""
        cfg = WalkForwardConfig()
        series = [(0.012, -0.004, 0.008, -0.002)[i % 4] for i in range(N_BARS)]
        res = run_walkforward(series, cfg)
        self.assertIsNotNone(res.oos_is_ratio)
        self.assertGreater(res.oos_is_ratio, 0.8)
        self.assertLess(res.oos_is_ratio, 1.2)

    def test_ratio_is_none_when_is_not_positive(self):
        """Sharpe IS <= 0 : le ratio n'a pas de sens, on ne l'invente pas."""
        cfg = WalkForwardConfig()
        series = [-0.02 if i % 2 == 0 else -0.005 for i in range(N_BARS)]
        res = run_walkforward(series, cfg)
        self.assertIsNotNone(res.sharpe_is)
        self.assertLess(res.sharpe_is, 0)
        self.assertIsNone(res.oos_is_ratio)

    def test_flat_series_yields_none_not_zero(self):
        """Variance = bruit numerique -> None (NON MESURE), jamais 0.0."""
        res = run_walkforward([0.01] * N_BARS, WalkForwardConfig())
        self.assertIsNone(res.sharpe_is)
        self.assertIsNone(res.sharpe_oos)
        self.assertIsNone(res.oos_is_ratio)
        self.assertTrue(all(s is None for s in res.fold_sharpes_oos))
        self.assertIsNone(res.degradation_std)

    def test_fold_sharpes_and_stability(self):
        cfg = WalkForwardConfig()
        series = [(0.012, -0.004, 0.008, -0.002)[i % 4] for i in range(N_BARS)]
        res = run_walkforward(series, cfg)
        self.assertEqual(len(res.fold_sharpes_oos), cfg.n_folds)
        self.assertIsNotNone(res.degradation_std)
        self.assertGreaterEqual(res.degradation_std, 0.0)

    def test_result_carries_protocol_fingerprint(self):
        cfg = WalkForwardConfig(anchored=True)
        res = run_walkforward(
            [(0.012, -0.004, 0.008, -0.002)[i % 4] for i in range(N_BARS)], cfg
        )
        self.assertIsInstance(res, WalkForwardResult)
        self.assertEqual(res.config_fingerprint, cfg.fingerprint())

    def test_deterministic(self):
        cfg = WalkForwardConfig()
        series = _overfit_series(cfg)
        a = run_walkforward(series, cfg)
        b = run_walkforward(series, cfg)
        self.assertEqual(a.sharpe_is, b.sharpe_is)
        self.assertEqual(a.sharpe_oos, b.sharpe_oos)
        self.assertEqual(a.folds, b.folds)


# ------------------------------------------------------- sensibilite params


class TestParamSensitivity(unittest.TestCase):
    def test_flat_function_is_robust(self):
        """Un score insensible aux parametres : degradation nulle."""
        d = param_sensitivity(lambda p: 1.0, {"len": 20.0, "mult": 2.0})
        self.assertIsNotNone(d)
        self.assertAlmostEqual(d, 0.0)

    def test_narrow_peak_is_unstable(self):
        """Pic etroit : le score s'effondre des qu'on bouge de 10 %.
        C'est un artefact de recherche, pas un edge."""

        def evaluate(p: dict) -> float:
            if abs(p["len"] - 20.0) < 0.2 and abs(p["mult"] - 2.0) < 0.02:
                return 2.0
            return 0.1

        d = param_sensitivity(evaluate, {"len": 20.0, "mult": 2.0})
        self.assertIsNotNone(d)
        self.assertGreater(d, GateConfig().max_param_degradation)

    def test_improvement_is_not_negative_degradation(self):
        """Un voisinage meilleur ne cree pas une degradation negative."""
        d = param_sensitivity(lambda p: 1.0 + p["len"], {"len": 20.0})
        self.assertIsNotNone(d)
        self.assertGreaterEqual(d, 0.0)

    def test_none_when_evaluate_always_raises(self):
        def boom(p: dict) -> float:
            raise RuntimeError("backtest casse")

        self.assertIsNone(param_sensitivity(boom, {"len": 20.0}))

    def test_none_when_all_perturbations_fail(self):
        """Base mesurable mais aucun essai exploitable = NON MESURE."""
        calls = {"n": 0}

        def evaluate(p: dict) -> float:
            calls["n"] += 1
            if calls["n"] == 1:
                return 1.0
            raise RuntimeError("perturbation non evaluable")

        self.assertIsNone(param_sensitivity(evaluate, {"len": 20.0}))

    def test_none_when_base_score_is_zero(self):
        """Degradation relative a zero : indefinie, donc None."""
        self.assertIsNone(param_sensitivity(lambda p: 0.0, {"len": 20.0}))

    def test_non_numeric_params_are_skipped(self):
        seen: list[dict] = []

        def evaluate(p: dict) -> float:
            seen.append(dict(p))
            return 1.0

        param_sensitivity(evaluate, {"len": 20.0, "mode": "long", "flag": True})
        # base + 2 essais sur le seul parametre reellement numerique
        self.assertEqual(len(seen), 3)
        self.assertTrue(all(s["mode"] == "long" for s in seen))

    def test_perturbation_pct_is_applied(self):
        seen: list[float] = []

        def evaluate(p: dict) -> float:
            seen.append(p["len"])
            return 1.0

        param_sensitivity(evaluate, {"len": 100.0}, perturbation_pct=10.0)
        self.assertEqual(len(seen), 3)
        self.assertAlmostEqual(seen[0], 100.0)
        self.assertAlmostEqual(max(seen), 110.0)
        self.assertAlmostEqual(min(seen), 90.0)


# ------------------------------------------------------- integration gates


class TestGateIntegration(unittest.TestCase):
    def test_overfitted_walkforward_triggers_overfit_gate(self):
        """Le pont entre ce module et le juge : un walk-forward overfitte
        DOIT produire Gate.OVERFIT dans les failures."""
        cfg = WalkForwardConfig()
        res = run_walkforward(_overfit_series(cfg), cfg)
        m = LaneMetrics(
            closed_trades=250,
            sharpe_is=res.sharpe_is,
            sharpe_oos=res.sharpe_oos,
            max_drawdown_pct=12.0,
            fees_usd=-40.0,
            funding_usd=-15.0,
            slippage_usd=-22.0,
            liquidation_risk_checked=True,
            microstructure_validated=True,
            param_sensitivity=0.18,
        )
        v = evaluate_gates(m, identity_complete=True)
        self.assertFalse(v.passed)
        self.assertIn(Gate.OVERFIT, v.failures)

    def test_unmeasured_sharpe_is_still_rejected(self):
        """Serie plate -> Sharpe None -> rejet, jamais un pass par defaut."""
        res = run_walkforward([0.01] * N_BARS, WalkForwardConfig())
        m = LaneMetrics(
            closed_trades=250,
            sharpe_is=res.sharpe_is,
            sharpe_oos=res.sharpe_oos,
            max_drawdown_pct=12.0,
            fees_usd=-40.0,
            funding_usd=-15.0,
            slippage_usd=-22.0,
            liquidation_risk_checked=True,
            microstructure_validated=True,
            param_sensitivity=0.18,
        )
        v = evaluate_gates(m, identity_complete=True)
        self.assertIn(Gate.OVERFIT, v.failures)

    def test_param_sensitivity_feeds_param_unstable_gate(self):
        def evaluate(p: dict) -> float:
            return 2.0 if abs(p["len"] - 20.0) < 0.2 else 0.1

        d = param_sensitivity(evaluate, {"len": 20.0})
        m = LaneMetrics(
            closed_trades=250,
            sharpe_is=1.8,
            sharpe_oos=1.4,
            max_drawdown_pct=12.0,
            fees_usd=-40.0,
            funding_usd=-15.0,
            slippage_usd=-22.0,
            liquidation_risk_checked=True,
            microstructure_validated=True,
            param_sensitivity=d,
        )
        v = evaluate_gates(m, identity_complete=True)
        self.assertIn(Gate.PARAM_UNSTABLE, v.failures)


if __name__ == "__main__":
    unittest.main(verbosity=2)
