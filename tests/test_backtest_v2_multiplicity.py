"""Tests de la correction de multiplicite.

    python tests/test_backtest_v2_multiplicity.py

Le test decisif est `TestNoiseCampaign` : une campagne sur du BRUIT PUR doit
finir a zero survivant apres correction. C'est la reponse au constat du
2026-08-09 (8,3 % d'acceptation sur du bruit gaussien).
"""
from __future__ import annotations

import math
import random
import statistics
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.multiplicity import (  # noqa: E402
    audit_campaign,
    benjamini_hochberg,
    bonferroni,
    deflated_sharpe_ratio,
    norm_cdf,
    norm_ppf,
    sharpe_pvalue,
)


class TestNormal(unittest.TestCase):
    def test_cdf_known_values(self):
        self.assertAlmostEqual(norm_cdf(0.0), 0.5, places=9)
        self.assertAlmostEqual(norm_cdf(1.96), 0.975, places=3)
        self.assertAlmostEqual(norm_cdf(-1.96), 0.025, places=3)

    def test_ppf_inverts_cdf(self):
        for p in (0.001, 0.01, 0.1, 0.5, 0.9, 0.99, 0.999):
            self.assertAlmostEqual(norm_cdf(norm_ppf(p)), p, places=6)

    def test_ppf_known_values(self):
        self.assertAlmostEqual(norm_ppf(0.975), 1.959964, places=4)
        self.assertAlmostEqual(norm_ppf(0.5), 0.0, places=9)

    def test_ppf_domain(self):
        for bad in (0.0, 1.0, -0.1, 1.5):
            with self.assertRaises(ValueError):
                norm_ppf(bad)


class TestSharpePValue(unittest.TestCase):
    def test_zero_sharpe_is_half(self):
        self.assertAlmostEqual(sharpe_pvalue(0.0, 1000), 0.5, places=6)

    def test_higher_sharpe_lower_pvalue(self):
        self.assertLess(sharpe_pvalue(2.0, 1000), sharpe_pvalue(1.0, 1000))

    def test_more_observations_lower_pvalue(self):
        """Le meme Sharpe est plus credible sur un echantillon long."""
        self.assertLess(sharpe_pvalue(1.0, 2000), sharpe_pvalue(1.0, 200))

    def test_none_stays_none(self):
        """None = non mesure, jamais "pas significatif"."""
        self.assertIsNone(sharpe_pvalue(None, 1000))
        self.assertIsNone(sharpe_pvalue(1.0, 1))


class TestBonferroni(unittest.TestCase):
    def test_threshold_divides_by_n(self):
        v = bonferroni([0.01] * 10, alpha=0.05)
        self.assertAlmostEqual(v.threshold, 0.005)

    def test_single_test_unchanged(self):
        v = bonferroni([0.04], alpha=0.05)
        self.assertEqual(v.n_survivors, 1)

    def test_same_pvalue_dies_when_many_tests(self):
        """0,04 passe seul, meurt sur 100 essais. C'est tout le sujet."""
        self.assertEqual(bonferroni([0.04], alpha=0.05).n_survivors, 1)
        self.assertEqual(bonferroni([0.04] * 100, alpha=0.05).n_survivors, 0)

    def test_n_tested_overrides_length(self):
        """Les lanes rejetees par les gates ont consomme un essai.

        Ne corriger que sur les survivants revient a ignorer les tickets
        perdants — le biais exact du legacy.
        """
        strict = bonferroni([0.0001], alpha=0.05, n_tested=10_000)
        loose = bonferroni([0.0001], alpha=0.05)
        self.assertEqual(loose.n_survivors, 1)
        self.assertEqual(strict.n_survivors, 0)

    def test_expected_false_positives_reported(self):
        v = bonferroni([0.5] * 1000, alpha=0.05)
        self.assertAlmostEqual(v.expected_false_positives, 50.0)

    def test_none_pvalues_never_survive(self):
        v = bonferroni([None, None, 0.0000001], alpha=0.05)
        self.assertEqual(v.survivors, [2])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            bonferroni([0.1], alpha=0.0)
        with self.assertRaises(ValueError):
            bonferroni([0.1], n_tested=0)


class TestBenjaminiHochberg(unittest.TestCase):
    def test_less_conservative_than_bonferroni(self):
        pv = [0.001, 0.008, 0.02, 0.04, 0.3, 0.5]
        bh = benjamini_hochberg(pv, alpha=0.05)
        bf = bonferroni(pv, alpha=0.05)
        self.assertGreaterEqual(bh.n_survivors, bf.n_survivors)

    def test_all_null_rejects_all(self):
        rng = random.Random(7)
        pv = [rng.uniform(0.2, 1.0) for _ in range(200)]
        self.assertEqual(benjamini_hochberg(pv, alpha=0.05).n_survivors, 0)

    def test_strong_signals_survive(self):
        pv = [1e-9, 1e-8, 1e-7] + [0.6] * 97
        self.assertGreaterEqual(benjamini_hochberg(pv, alpha=0.05).n_survivors, 3)

    def test_survivor_indices_map_to_input(self):
        pv = [0.9, 1e-9, 0.8]
        self.assertIn(1, benjamini_hochberg(pv, alpha=0.05).survivors)


class TestDeflatedSharpe(unittest.TestCase):
    def test_single_trial_high_sharpe_survives(self):
        p = deflated_sharpe_ratio(2.0, n_trials=1, n_obs=1000,
                                  variance_of_trial_sharpes=0.0)
        self.assertGreater(p, 0.95)

    def test_many_trials_erode_the_same_sharpe(self):
        """Le MEME Sharpe vaut moins quand on a essaye 10 000 fois."""
        few = deflated_sharpe_ratio(1.5, 10, 1000, 0.5)
        many = deflated_sharpe_ratio(1.5, 10_000, 1000, 0.5)
        self.assertGreater(few, many)

    def test_dispersion_erodes_confidence(self):
        low = deflated_sharpe_ratio(1.5, 1000, 1000, 0.1)
        high = deflated_sharpe_ratio(1.5, 1000, 1000, 2.0)
        self.assertGreater(low, high)

    def test_negative_skew_penalised(self):
        """Les rendements de trading ne sont pas gaussiens : ignorer skew et
        kurtosis surestime la significativite."""
        normal = deflated_sharpe_ratio(1.5, 100, 1000, 0.5, skew=0.0, kurtosis=3.0)
        fat = deflated_sharpe_ratio(1.5, 100, 1000, 0.5, skew=-1.5, kurtosis=9.0)
        self.assertNotAlmostEqual(normal, fat, places=6)

    def test_probability_bounds(self):
        for nt in (1, 10, 1000, 100_000):
            p = deflated_sharpe_ratio(1.0, nt, 500, 0.4)
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            deflated_sharpe_ratio(1.0, 0, 100, 0.1)
        with self.assertRaises(ValueError):
            deflated_sharpe_ratio(1.0, 10, 1, 0.1)
        with self.assertRaises(ValueError):
            deflated_sharpe_ratio(1.0, 10, 100, -1.0)


class TestNoiseCampaign(unittest.TestCase):
    """LE test du module : une campagne sur du bruit doit finir a zero."""

    def _noise_sharpes(self, n_lanes: int, n_obs: int, seed: int) -> list[float]:
        """Simule n_lanes strategies SANS aucun edge et renvoie leurs Sharpe."""
        rng = random.Random(seed)
        out = []
        for _ in range(n_lanes):
            rets = [rng.gauss(0.0, 0.01) for _ in range(n_obs)]
            m = statistics.fmean(rets)
            s = statistics.stdev(rets)
            out.append((m / s) * math.sqrt(365) if s > 0 else 0.0)
        return out

    def test_pure_noise_campaign_yields_no_survivor(self):
        """1000 strategies sans edge : les meilleures paraissent excellentes,
        la correction les elimine toutes."""
        sharpes = self._noise_sharpes(1000, 500, seed=1)
        best = max(sharpes)
        self.assertGreater(best, 0.8, "le hasard produit bien des Sharpe eleves")

        audit = audit_campaign(
            n_tested=1000, sharpes_oos=sharpes, n_obs_per_lane=500
        )
        self.assertEqual(audit.n_after_multiplicity, 0)

    def test_audit_reports_the_denominator(self):
        sharpes = self._noise_sharpes(200, 400, seed=3)
        a = audit_campaign(n_tested=200, sharpes_oos=sharpes, n_obs_per_lane=400)
        self.assertEqual(a.n_tested, 200)
        self.assertAlmostEqual(a.expected_by_chance, 10.0)
        self.assertIn("rappel", a.detail)

    def test_gate_rejected_lanes_still_count_as_trials(self):
        """10 survivants issus de 10 000 essais : la correction doit porter
        sur 10 000, pas sur 10."""
        sharpes = self._noise_sharpes(10, 500, seed=5)
        lenient = audit_campaign(n_tested=10, sharpes_oos=sharpes, n_obs_per_lane=500)
        strict = audit_campaign(n_tested=10_000, sharpes_oos=sharpes, n_obs_per_lane=500)
        self.assertGreaterEqual(lenient.n_after_multiplicity,
                                strict.n_after_multiplicity)

    def test_genuine_edge_survives(self):
        """Contre-epreuve : un vrai edge fort DOIT passer, sinon le module
        serait inutilisable."""
        rng = random.Random(11)
        n_obs = 2000
        rets = [rng.gauss(0.004, 0.01) for _ in range(n_obs)]
        m, s = statistics.fmean(rets), statistics.stdev(rets)
        sharpe = (m / s) * math.sqrt(365)

        a = audit_campaign(n_tested=100, sharpes_oos=[sharpe], n_obs_per_lane=n_obs)
        self.assertGreater(a.n_after_multiplicity, 0, f"sharpe={sharpe:.2f} rejete")

    def test_suspicious_flag(self):
        sharpes = self._noise_sharpes(50, 300, seed=13)
        a = audit_campaign(n_tested=50, sharpes_oos=sharpes, n_obs_per_lane=300)
        self.assertIsInstance(a.is_suspicious, bool)

    def test_no_measurable_lane(self):
        a = audit_campaign(n_tested=500, sharpes_oos=[None] * 5, n_obs_per_lane=400)
        self.assertEqual(a.n_gate_survivors, 0)
        self.assertIn("AUCUNE LANE MESURABLE", a.verdict)

    def test_invalid_n_tested(self):
        with self.assertRaises(ValueError):
            audit_campaign(n_tested=0, sharpes_oos=[1.0], n_obs_per_lane=100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
