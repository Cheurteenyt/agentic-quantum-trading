"""Les invariants du harnais FORWARD DEPTH-IMB (spec pré-enregistrée).

On teste les fonctions PURES (verdict, stats, agrégat, MA, outcome) sur des
données synthétiques — jamais la base de 10 Go. Le point qui compte : le
harnais est FORWARD-ONLY, donc **sans gel il ne juge RIEN** (un harnais sans
état est une intention, pas un gel).

    .venv/bin/python -m pytest tests/test_depth_imbalance_forward.py -q
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import depth_imbalance_forward as d  # noqa: E402


class LeVerdictSuitLesSeuilsDeLaSpec(unittest.TestCase):
    """PASS : WR ≥ 65 % ET ratio ≥ 1,8 sur n ≥ 100 · FAIL : WR < 55 %."""

    def test_n_sous_le_minimum_est_insuffisant(self) -> None:
        v = d.verdict_of({"n": 99, "wr_pos": 90.0, "ratio": 5.0})
        self.assertIn("INSUFFISANT", v)

    def test_wr_sous_55_est_fail(self) -> None:
        self.assertIn("FAIL", d.verdict_of({"n": 500, "wr_pos": 54.9, "ratio": 5.0}))

    def test_pass_exige_le_wr_ET_le_ratio(self) -> None:
        # WR bon mais ratio trop faible → pas un PASS
        self.assertFalse(
            d.verdict_of({"n": 500, "wr_pos": 70.0, "ratio": 1.79}).startswith("PASS"))
        self.assertTrue(
            d.verdict_of({"n": 500, "wr_pos": 65.0, "ratio": 1.8}).startswith("PASS"))

    def test_entre_deux_n_est_ni_pass_ni_fail(self) -> None:
        v = d.verdict_of({"n": 500, "wr_pos": 60.0, "ratio": 0.5})
        self.assertIn("ENTRE-DEUX", v)


class LeSansGelNeJugeRien(unittest.TestCase):
    """FORWARD-ONLY : pas de gel => aucun signal (le trou « intention ≠ état »)."""

    def test_le_gel_est_none_si_le_fichier_n_est_pas_commite(self) -> None:
        # le fichier EST commité en CI — on vérifie surtout que la fonction
        # rend un entier plausible (ms) ou None, jamais un 0 silencieux
        g = d.gel_start_ms()
        self.assertTrue(g is None or (isinstance(g, int) and g > 1_000_000_000_000))

    def test_la_moyenne_glissante_est_de_30_min(self) -> None:
        self.assertEqual(d.MA_MIN, 30)
        self.assertEqual(d.THRESHOLD, 0.25)
        self.assertEqual(d.HORIZON_MIN, 15)


class LesFonctionsPures(unittest.TestCase):

    def test_add_ma_lisse_sur_la_fenetre(self) -> None:
        # 1 snapshot / 5 min → la fenêtre 30 min couvre ~7 points
        ts = list(range(0, 3600 * 3, 300))
        df = pd.DataFrame({"ts": ts, "mid": [100.0] * len(ts),
                           "imb": [1.0] * len(ts)})
        out = d.add_ma(df)
        self.assertAlmostEqual(out["ma"].iloc[-1], 1.0, places=6)

    def test_outcomes_mesure_le_drift_a_l_horizon(self) -> None:
        # mid constant puis +1 % : à t+15min le drift est +1 %
        ts = list(range(0, 3600, 60))
        mid = [100.0] * 15 + [101.0] * 45
        df = pd.DataFrame({"ts": ts, "mid": mid})
        dr = d.outcomes(df, 15)
        self.assertAlmostEqual(dr[0], 1.0, places=6)

    def test_aggregate_pondere_par_n(self) -> None:
        rows = [{"n": 100, "mean_pct": 1.0, "wr_pos": 60.0, "wr_target": 0.0,
                 "cost_pct": 0.28},
                {"n": 300, "mean_pct": 2.0, "wr_pos": 80.0, "wr_target": 0.0,
                 "cost_pct": 0.28}]
        agg = d._aggregate(rows)
        self.assertEqual(agg["n"], 400)
        self.assertAlmostEqual(agg["mean_pct"], 1.75, places=6)   # (1*100+2*300)/400
        self.assertAlmostEqual(agg["wr_pos"], 75.0, places=6)

    def test_stats_vides_ne_divisent_pas(self) -> None:
        self.assertEqual(d._stats(np.array([]), 0.28), {"n": 0})


class LeShaCiteEstCeluiQueLeHarnaisDerive(unittest.TestCase):
    """La spec cite un sha de gel : il doit être CELUI que le harnais calcule.

    Sans ce verrou, la ligne « Hash du gel » redevient une intention qu'on
    recopie à la main — et un squash-merge la fait diverger en silence
    (vécu : la spec citait le commit de branche, le harnais dérivait celui
    de `main`).
    """

    def test_le_sha_cite_par_la_spec_est_le_gel_reel(self) -> None:
        import re
        import subprocess
        txt = (ROOT / "research" / "hypotheses" / "depth-imbalance.md").read_text(
            encoding="utf-8")
        ligne = [ln for ln in txt.splitlines() if ln.startswith("Hash")][0]
        m = re.search(r"\b([0-9a-f]{7,40})\b", ligne)
        self.assertIsNotNone(m, "la ligne « Hash du gel » ne cite aucun sha")
        sha = m.group(1)
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%H", "--", d.SELF_REL],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        commits = out.stdout.split()
        if not commits:  # arbre sans historique git : le verrou ne s'applique pas
            self.skipTest("pas d'historique git pour ce fichier")
        self.assertTrue(
            commits[-1].startswith(sha),
            f"la spec cite {sha} mais le harnais dérive {commits[-1][:12]} — "
            "le gel est un état : recopier le sha réel.")


if __name__ == "__main__":
    unittest.main()
