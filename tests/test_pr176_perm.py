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

class TestBHAtteignable(unittest.TestCase):
    """N1 — le BH n'était pas un filtre, c'était un refus automatique.

    Le plancher d'une p-value par permutation est `1/(n_perm+1)`. Pour que
    le meilleur candidat d'un lot de `m` specs franchisse le BH au rang 1,
    il faut `p <= q/m`, donc `n_perm >= m/q - 1`.

    Avec le défaut historique `n_perm = 99`, le plancher est 0,01 : le BH
    n'est franchissable que pour `m <= 10`. Sur un lot de 43 specs, AUCUN
    candidat ne pouvait passer — un edge réel de +0,4 % était écarté au
    même titre qu'un bruit. Le contrôle multiplicatif ne mesurait rien.
    """

    Q = 0.10

    def test_la_table_du_rapport(self):
        from scripts.research_runner import bh_min_perms
        for m, attendu in ((10, 99), (43, 429), (100, 999)):
            with self.subTest(m=m):
                self.assertEqual(bh_min_perms(m), attendu)

    def test_le_defaut_historique_etait_infranchissable(self):
        """Contrôle négatif : n_perm=99 doit rester inatteignable > 10."""
        from scripts.research_runner import bh_reachable
        p99 = 1.0 / 100
        self.assertTrue(bh_reachable(p99, 10))
        self.assertFalse(bh_reachable(p99, 43))
        self.assertFalse(bh_reachable(p99, 100))

    def test_avec_la_resolution_adaptative_le_seuil_est_atteignable(self):
        from scripts.research_runner import bh_min_perms, bh_reachable
        for m in (5, 10, 43, 100, 250):
            with self.subTest(m=m):
                n = bh_min_perms(m)
                self.assertTrue(bh_reachable(1.0 / (n + 1), m),
                                f"lot {m} : n_perm={n} ne suffit pas")

    def test_un_lot_vide_ne_divise_pas_par_zero(self):
        from scripts.research_runner import bh_min_perms, bh_reachable
        self.assertGreaterEqual(bh_min_perms(0), 99)
        self.assertFalse(bh_reachable(0.001, 0))

    def test_la_resolution_ne_descend_jamais_sous_le_defaut(self):
        """Un petit lot ne doit pas payer MOINS que le défaut historique."""
        from scripts.research_runner import bh_min_perms
        for m in range(1, 15):
            self.assertGreaterEqual(bh_min_perms(m), 99, f"m={m}")

    def test_le_plancher_decroit_bien_avec_la_resolution(self):
        from scripts.research_runner import bh_min_perms
        precedents = [bh_min_perms(m) for m in (10, 20, 50, 100, 200)]
        self.assertEqual(precedents, sorted(precedents))
        self.assertGreater(len(set(precedents)), 1,
                           "la résolution doit s'adapter à la taille du lot")


if __name__ == "__main__":
    unittest.main(verbosity=2)
