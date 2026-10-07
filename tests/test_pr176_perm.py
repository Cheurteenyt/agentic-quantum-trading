"""PR-176 — le gate par PERMUTATION CIRCULAIRE (B4, audit Sonnet 5.5).

Le n nominal des events horaires chevauchants ne se croit pas : la
sélection des candidats passe par la p-value de permutation (BH q=0.10
sur le lot). Calibration de l'audit : P(p<0,05) = 4,7 % sous H0.

    python tests/test_pr176_perm.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.research_runner import _perm_loop  # noqa: E402

H = 6
N = 3000


def _cols(rng, edge: float = 0.0, mask: np.ndarray | None = None):
    """cols minimal pour event_study : ret/hi/lo + masque facultatif.
    edge < 0 = un CRASH sur les events (le short gagne)."""
    ret = rng.normal(0, 0.6, N)
    if mask is not None and edge:
        ret = ret.copy()
        ret[mask] += edge
    hi = np.abs(rng.normal(0, 0.3, N))
    lo = -np.abs(rng.normal(0, 0.3, N))
    return {"ret_6": ret, "hi_6": hi, "lo_6": lo}


class TestPermGate(unittest.TestCase):
    def test_bruit_pur_p_grande(self):
        rng = np.random.default_rng(7)
        mask = np.zeros(N, dtype=bool)
        mask[rng.choice(N, 300, replace=False)] = True
        cols = _cols(rng)
        # pos_ret du short = -ret - coût
        mean_obs = float((-cols["ret_6"][mask] - 0.28).mean())
        p = _perm_loop([(cols, mask)], H, -1, 0.28,
                       mean_obs=mean_obs, n_perm=99, seed=1)
        self.assertGreater(p, 0.10, "un bruit pur ne doit pas passer BH")

    def test_edge_injecte_p_petite(self):
        rng = np.random.default_rng(7)
        mask = np.zeros(N, dtype=bool)
        mask[rng.choice(N, 300, replace=False)] = True
        cols = _cols(rng, edge=-0.9, mask=mask)   # crash sur les events
        mean_obs = float((-cols["ret_6"][mask] - 0.28).mean())
        p = _perm_loop([(cols, mask)], H, -1, 0.28,
                       mean_obs=mean_obs, n_perm=99, seed=1)
        self.assertLess(p, 0.05, "un edge de -0,9 % doit passer la permutation")

    def test_masque_decale_perd_son_alignement(self):
        # le roll détruit l'alignement : la moyenne permutée d'un signal
        # pur retombe au bruit (le cœur du contrôle)
        rng = np.random.default_rng(11)
        mask = np.zeros(N, dtype=bool)
        mask[rng.choice(N, 300, replace=False)] = True
        cols = _cols(rng, edge=-0.9, mask=mask)
        mean_obs = float((-cols["ret_6"][mask] - 0.28).mean())
        # mean_obs fort, mais le mean PERMUTÉ (masque roulé) ≈ -coût :
        # la p doit être petite, pas 1.0
        p = _perm_loop([(cols, mask)], H, -1, 0.28,
                       mean_obs=mean_obs, n_perm=99, seed=2)
        self.assertLessEqual(p, 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
