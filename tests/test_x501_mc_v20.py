#!/usr/bin/env python3
"""Tests du moteur MC v20 reconstruit (OpenMarket ×501, PR #13).

Couverture demandée :
  1. le seed est bit-à-bit (re-exécution identique + cohérence avec le JSON versionné) ;
  2. les probabilités sont bornées [0, 1] ;
  3. le DD cap 25 % est respecté (ratchet physique : jamais au-delà, au bit près).

Lancement : .venv/bin/python -m unittest tests.test_x501_mc_v20 -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "studies" / "x501_openmarket"))

import x501_mc_v20 as mc  # noqa: E402

RESULTS_PATH = mc.RESULTS_PATH
EPS = 1e-12


def _public(res: dict) -> dict:
    """Les métriques officielles uniquement (sans les stats internes « _ »)."""
    return {k: v for k, v in res.items() if not k.startswith("_")}


class X501McV20Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = mc.load_pool()
        cls.run1 = mc.run_all(cls.info)
        cls.run2 = mc.run_all(cls.info)

    def test_01_pool_conforme(self):
        """Le pool est exactement celui de la mission : 31 trades embarqués."""
        self.assertEqual(self.info["n_trades"], 31)
        self.assertEqual(self.info["pool"].size, 31)
        self.assertEqual(self.info["n12"], 65)  # 31 trades / 5,76 mois → 65/12 m
        self.assertEqual(self.info["n36"], 194)

    def test_02_seed_bit_a_bit(self):
        """Deux exécutions complètes avec le même seed sont identiques bit à bit."""
        self.assertEqual(_public(self.run1), _public(self.run2))
        # Et les floats sont exactement égaux (pas approximatifs) :
        for name, _bps in mc.SCENARIOS:
            for key in ("median_12m", "p250", "p500", "p1250", "x501_36m"):
                a = self.run1[name][key]
                b = self.run2[name][key]
                self.assertEqual(a, b, f"{name}.{key} diffère bit à bit: {a!r} vs {b!r}")

    def test_03_json_versionne_bit_a_bit(self):
        """Le JSON versionné au dépôt correspond bit à bit à une re-exécution."""
        self.assertTrue(RESULTS_PATH.exists(), f"JSON manquant: {RESULTS_PATH}")
        saved = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved["seed"], mc.SEED)
        for name, _bps in mc.SCENARIOS:
            for key in ("median_12m", "p250", "p500", "p1250", "x501_36m"):
                self.assertIn(name, saved)
                self.assertEqual(
                    saved[name][key], self.run1[name][key], f"{name}.{key}"
                )

    def test_04_probabilites_bornees(self):
        """Toutes les probabilités sont dans [0, 1] pour les 5 scénarios."""
        for name, _bps in mc.SCENARIOS:
            for key in ("p250", "p500", "p1250", "x501_36m"):
                p = self.run1[name][key]
                self.assertGreaterEqual(p, 0.0, f"{name}.{key}")
                self.assertLessEqual(p, 1.0, f"{name}.{key}")

    def test_05_dd_cap_strict(self):
        """DD max ≤ 25 % au bit près sur les 60 000 trajectoires (5 × 12 000)."""
        for name, _bps in mc.SCENARIOS:
            dd = self.run1[name]["_stats"]["_max_dd"]
            self.assertGreaterEqual(dd, 0.0, f"{name}: DD négatif")
            self.assertLessEqual(dd, mc.DD_CAP + EPS, f"{name}: DD cap rompu ({dd!r})")

    def test_06_monotonie_couts(self):
        """La médiane décroît avec le coût : S0 > pur > δ2 > stress > taker."""
        m = {n: self.run1[n]["median_12m"] for n, _ in mc.SCENARIOS}
        self.assertGreater(m["S0_reference"], m["MAKER_PURE"])
        self.assertGreater(m["MAKER_PURE"], m["MAKER_DELTA2"])
        self.assertGreater(m["MAKER_DELTA2"], m["MAKER_STRESS"])
        self.assertGreater(m["MAKER_STRESS"], m["TAKER"])

    def test_07_ancres_docs25(self):
        """Les 2 ancres de calibration reproduisent docs/25 (S0 642,0 / TAKER 272,7)."""
        self.assertAlmostEqual(self.run1["S0_reference"]["median_12m"], 642.0, delta=0.01)
        self.assertAlmostEqual(self.run1["TAKER"]["median_12m"], 272.7, delta=0.01)


if __name__ == "__main__":
    unittest.main()
