"""PR-166 — les invariants moteur issus des 3 chasses aux bugs Aster
(noyau données/labels + moteur de mesure).

    python tests/test_pr166_engine.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.funding_series import FundingSeries  # noqa: E402
from scripts.research_runner import DataView, event_mask  # noqa: E402

H_MS = 3_600_000


class TestJitterFunding(unittest.TestCase):
    def test_print_jitter_inclus_dans_sa_fenetre(self):
        # PR-166 (P1 noyau) : le print de settlement à 8h + 17 ms doit
        # être compté dans la fenêtre (0, 8h] — l'ancien jitter le
        # rejetait vers la fenêtre SUIVANTE (biais directionnel)
        fs = FundingSeries.from_rows(
            [(8 * H_MS + 17, 0.0001)])
        self.assertAlmostEqual(fs.sum_pct_between(0, 8 * H_MS), 0.01,
                               places=9)
        self.assertAlmostEqual(fs.sum_pct_between(0, 8 * H_MS - 1), 0.0,
                               places=9)

    def test_dedup_premier_arrive(self):
        # PR-166 : la dédup garde la PREMIÈRE occurrence dans l'ordre
        # d'arrivée (l'ancien tri (t, rate) gardait le rate MIN)
        fs = FundingSeries.from_rows([(0, 0.0005), (0, -0.0002)])
        self.assertAlmostEqual(fs.sum_pct_between(-1, 1), 0.05, places=9)


class TestMonoThreshold(unittest.TestCase):
    def test_threshold_declare_honore(self):
        # PR-166 (P1 moteur) : un threshold DÉCLARÉ est honoré — l'ancien
        # code n'exécutait que quantile (0.95 par défaut) : la discovery
        # ne mesurait pas le signal qu'elle prétendait mesurer
        spec = {"id": "T", "signal": {"feature": "ret_1h",
                                      "op": "<=", "threshold": -30.0}}
        feats = {"open_time_ns": np.arange(6) * H_MS * 10**6,
                 "ret_1h": np.array([0.0, -31.0, -5.0, -40.0, 0.0, -1.0])}
        view = DataView("snap", "train", 0, 6 * H_MS)
        mask = event_mask(spec, feats, view)
        # raw = ret <= -30 → [F, T, F, T, F, F] ; entrée = barre suivante
        self.assertEqual(mask.tolist(),
                         [False, False, True, False, True, False])


if __name__ == "__main__":
    unittest.main(verbosity=2)
