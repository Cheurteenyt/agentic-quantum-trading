"""Ronde 5 — les fossiles pré-F-038 du pipeline nocturne alignés sur
liq_move_for (le modèle officiel F-038/#202/#213).

Quatre fichiers de PROD nocturne (trading-agent-nightly.service) portaient
encore un seuil de liquidation fossile, parallèle à liq_move_for :

- backtest_indicators.py : `mm or 0` — une marge de maintenance NULL
  devenait 0 → seuil 100/L au lieu de 100/L − mm (à 10x : 10,0 % au lieu
  de 7,5 %) → la section « Risque de LIQUIDATION » du rapport nocturne
  sous-comptait les liquidations ; la table absente passait en silence
  (except pass).
- cascade_funding.py : seuil figé `>= 4.5` (= 100/20 − 0.5 pré-F-038) —
  les MAE ∈ [2,5 ; 4,5) jugées vivantes : sous-comptage flatteur dans la
  table de terciles.
- stacked_portfolio.py : fallback du registre `100/3 − 0.5` (32,83 %)
  quel que soit le symbole — ~2× trop haut pour un memecoin (16,66 %).
- anti_liq.py : LIQ_MOVE_PCT plat calculé à l'import (2,5 %) — coïncide
  avec les majeures mais ignore les memecoins, non prudent, non compté.

Le contrat : tout le pipeline nocturne passe par liq_move_for (marge
réelle, repli PRUDENT compté, non-viable → 0.0), et les motifs fossiles
ne réapparaissent pas.

    python tests/test_r5_liq_fossils.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import portfolio_sim as ps  # noqa: E402


class TestLiqMoveForModeleOfficiel(unittest.TestCase):
    """Le différentiel entre le seuil plat pré-F-038 et le modèle réel."""

    def setUp(self):
        ps.LIQ_FALLBACK_COUNT = 0
        ps.LIQ_NON_VIABLE = 0

    def test_majeure_mm_25_a_20x(self):
        with mock.patch.object(ps, "_LIQ_PARAMS",
                               {"BTCUSDT": (2.5, 125.0)}):
            self.assertAlmostEqual(ps.liq_move_for("BTCUSDT", 20), 2.5)

    def test_memecoin_mm_1666_a_20x_non_viable(self):
        # 100/20 − 16,66 < 0 → liquidé à l'ENTRÉE (0.0, compté #202) —
        # l'ancien seuil plat 2,5 % laissait croire qu'il pouvait survivre
        with mock.patch.object(ps, "_LIQ_PARAMS",
                               {"MEMEUSDT": (16.66, 3.0)}):
            self.assertEqual(ps.liq_move_for("MEMEUSDT", 20), 0.0)
            self.assertEqual(ps.LIQ_NON_VIABLE, 1)

    def test_symbole_hors_table_repli_prudent_compte(self):
        # le repli = la plus HAUTE marge observée (prudent) + compteur
        with mock.patch.object(ps, "_LIQ_PARAMS",
                               {"BTCUSDT": (2.5, 125.0),
                                "MEMEUSDT": (16.66, 3.0)}):
            d = ps.liq_move_for("INCONNUSDT", 20)
            self.assertEqual(d, max(0.0, 100.0 / 20 - 16.66))
            self.assertEqual(ps.LIQ_FALLBACK_COUNT, 1)

    def test_ancien_seuil_plat_expose_un_memecoin_inexistant(self):
        """LE test du fossile : l'ancien seuil plat 2,5 % et le modèle réel
        divergent sur un memecoin à 20x — un event à MAE 1 % était jugé
        VIVANT par le fossile alors qu'il est liquidé à l'entrée."""
        ancien_seuil_plat = 100.0 / 20 - 2.5   # 2,5 % (LIQ_MOVE_PCT)
        self.assertEqual(ancien_seuil_plat, 2.5)
        with mock.patch.object(ps, "_LIQ_PARAMS",
                               {"MEMEUSDT": (16.66, 3.0)}):
            reel = ps.liq_move_for("MEMEUSDT", 20)
        event_mae_1pct = 1.0
        self.assertTrue(event_mae_1pct < ancien_seuil_plat,
                        "le fossile le jugeait vivant")
        self.assertTrue(event_mae_1pct >= reel,
                        "le modèle réel le juge liquidé à l'entrée")


class TestNoFossileRestant(unittest.TestCase):
    """Oracle anti-fossile : les motifs pré-F-038 ne réapparaissent pas
    dans le pipeline nocturne."""

    NIGHTLY_PROD = (
        "scripts/backtest_indicators.py",
        "scripts/cascade_funding.py",
        "scripts/stacked_portfolio.py",
        "scripts/anti_liq.py",
    )

    def test_backtest_indicators_plus_de_mm_or_0(self):
        src = (ROOT / "scripts/backtest_indicators.py").read_text()
        # motif de CODE du fossile (pas les commentaires qui le documentent)
        self.assertNotIn('"mm": mm or 0', src,
                         "une mm NULL redeviendrait 0 : seuil optimiste")
        self.assertIn("liq_move_for(sym, L)", src)

    def test_cascade_funding_plus_de_seuil_45_fige(self):
        src = (ROOT / "scripts/cascade_funding.py").read_text()
        self.assertNotIn(">= 4.5", src,
                         "le seuil pré-F-038 100/20−0.5 est réapparu")
        self.assertIn("liq_move_for", src)

    def test_stacked_plus_de_100_sur_3_moins_05(self):
        src = (ROOT / "scripts/stacked_portfolio.py").read_text()
        self.assertNotIn("100 / 3 - 0.5", src,
                         "le prix de mort figé 32,83 % est réapparu")
        self.assertIn("liq_move_for", src)

    def test_anti_liq_plus_de_seuil_plat_import(self):
        src = (ROOT / "scripts/anti_liq.py").read_text()
        self.assertNotIn("LIQ_MOVE_PCT", src.replace(
            "# Fossile ronde 5 : LIQ_MOVE_PCT était un seuil PLAT", ""),
            "le seuil plat calculé à l'import est réapparu")
        # #201 : le levier de scénario est UNE constante (SCENARIO_LEV), pas un
        # littéral 20 répété ici et dans le pnl. On épingle la FORME (constante),
        # pas la valeur — sinon ce test lui-même devient le fossile.
        self.assertIn("liq_move_for(sym, SCENARIO_LEV)", src,
                      "le seuil doit être calculé au MÊME levier que le label")
        self.assertNotIn("liq_move_for(sym, 20)", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
