"""GOLDEN TESTS des indicateurs du registre (Research OS PR 5, brief §57).

Chaque valeur de référence est calculée À LA MAIN sur des séries triviales :
une implémentation future qui change silencieusement la définition (la
leçon ATR v1→v2) casse ces tests au lieu de changer les résultats.

    python tests/test_feature_golden.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aster_indicators import bollinger, macd, volume_z  # noqa: E402


def _series(values):
    idx = pd.date_range("2026-01-01", periods=len(values), freq="1h")
    return pd.Series(values, index=idx, dtype=float)


class TestMacdGolden(unittest.TestCase):
    def test_constante_line_nulle(self):
        line, sig = macd(_series([100.0] * 40))
        self.assertTrue(np.allclose(line.values, 0.0))
        self.assertTrue(np.allclose(sig.values, 0.0))

    def test_seed_et_premiere_valeur(self):
        # close = [100, 110] : ema12[1] = 100 + (2/13)·10 = 101.53846…
        # ema26[1] = 100 + (2/27)·10 = 100.74074… → line[1] = 0.797726…
        line, sig = macd(_series([100.0, 110.0]))
        self.assertAlmostEqual(line.values[1], 10 * (2 / 13 - 2 / 27), places=12)
        # signal[1] = ema9(line)[1] = 0 + (2/10)·line[1]
        self.assertAlmostEqual(sig.values[1], (2 / 10) * line.values[1], places=12)


class TestBollingerGolden(unittest.TestCase):
    def test_constant_bands_collent_le_prix(self):
        lo, mid, hi = bollinger(_series([100.0] * 25))
        self.assertAlmostEqual(mid.values[-1], 100.0, places=12)
        self.assertAlmostEqual(hi.values[-1], 100.0, places=12)  # std = 0
        self.assertAlmostEqual(lo.values[-1], 100.0, places=12)

    def test_mid_et_std_sur_une_serie_connue(self):
        vals = [float(v) for v in range(1, 22)]   # 1..21
        lo, mid, hi = bollinger(_series(vals), n=20, k=2)
        # les 20 derniers : 2..21 → mid = 11.5, std (population, ddof=0 pandas
        # par défaut rolling std = sample ddof=1) : calculé depuis pandas
        self.assertAlmostEqual(mid.values[-1], 11.5, places=12)
        sd = float(np.std(vals[1:], ddof=1))
        self.assertAlmostEqual(hi.values[-1], 11.5 + 2 * sd, places=12)

    def test_warmup_nan_honnete(self):
        vals = [float(v) for v in range(1, 22)]
        lo, mid, hi = bollinger(_series(vals), n=20, k=2)
        self.assertTrue(np.isnan(mid.values[0]))
        self.assertTrue(np.isnan(hi.values[18]))


class TestVolumeZGolden(unittest.TestCase):
    def test_z_dune_barre_deux_ecarts_au_dessus(self):
        vol = [100.0] * 21
        vol[-1] = 300.0                     # la dernière : +200 au-dessus de la moyenne 100
        z = volume_z(_series(vol), n=20)
        # mean(21 valeurs) = 110, std(ddof=1) ≈ 43.59 → z ≈ (300-110)/43.59…
        # plus simple : les 20 premières sont constantes → leur fenêtre
        # (les 20 avant la dernière) a std=0 → NaN ; la fenêtre de la
        # dernière inclut 300 → z calculable et positif
        self.assertTrue(np.isnan(z.values[19]))   # std=0 sur vol constant
        self.assertGreater(z.values[20], 0)

    def test_volume_constant_std_nulle_donc_nan(self):
        z = volume_z(_series([100.0] * 25), n=20)
        self.assertTrue(np.isnan(z.values[-1]))   # std=0 → NaN (jamais 0)


if __name__ == "__main__":
    unittest.main()
