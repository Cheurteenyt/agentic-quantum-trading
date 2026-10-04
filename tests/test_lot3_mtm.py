"""FIX lot3 (F8) — le DD mark-to-market du wallet.

Bug prouvé : run_stack ne bougeait `balance` qu'aux clôtures (bookées à
l'ENTRÉE de surcroît) — un trade +5 % final qui passait par −8 % latent
laissait le max_dd à ~0 alors que le portefeuille avait réellement subi
le creux. Désormais : le pnl sain est booké À LA SORTIE, et les marks
horaires de l'event dessinent le chemin latent (equity = réalisé +
non réalisé) ; le sizing reste sur le réalisé.

    python tests/test_lot3_mtm.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.stacked_portfolio import run_stack  # noqa: E402


def _event(ts_ms=0, hold_h=6.0, ret=5.0, marks=None, strategy="s"):
    e = {"strategy": strategy, "ts_ms": ts_ms, "lev": 1.0,
         "mae_adverse": 1.0, "fee_rt_bps": 0.0, "sym": "XUSDT",
         "hold_h": hold_h, "price_ret_short": ret, "fund_sign": 1}
    if marks is not None:
        e["marks"] = marks
    return e


class TestMtM(unittest.TestCase):
    def test_le_dd_voit_le_creux_latent_dun_gagnant(self):
        # short +5 % final, mais −8 % latent à h1 : l'ancien code donnait 0
        ev = _event(marks=[(1.0, -8.0), (3.0, 2.0), (6.0, 5.0)])
        r = run_stack([ev], 100.0, lambda e: 0.1, {})
        self.assertEqual(r["n"], 1)
        self.assertAlmostEqual(r["balance"], 100.5)   # booké à la sortie
        # equity au mark h1 = 100 + 10 × (-8)/100 = 99.2 → dd = 0.8 %
        self.assertAlmostEqual(r["max_dd"], 0.8, places=9)

    def test_sans_marks_le_dd_reste_le_chemin_des_sorties(self):
        ev = _event()   # un seul gagnant, aucun mark : aucun creux possible
        r = run_stack([ev], 100.0, lambda e: 0.1, {})
        self.assertEqual(r["max_dd"], 0.0)
        self.assertAlmostEqual(r["balance"], 100.5)

    def test_le_bookage_se_fait_a_la_sortie_pas_a_l_entree(self):
        # deux trades : le 2e démarre AVANT que le 1e ne sorte — le sizing
        # du 2e doit voir le wallet SANS le pnl encore non réalisé du 1er
        e1 = _event(ts_ms=0, hold_h=6.0, ret=50.0)          # sort à 6h : +5.0
        e2 = _event(ts_ms=2 * 3600 * 10**9, hold_h=6.0, ret=0.0,
                    strategy="t")
        r = run_stack([e1, e2], 100.0, lambda e: 0.1, {})
        self.assertEqual(r["n"], 2)
        # à l'entrée du 2e (2h), le +5 du 1er n'est PAS encore booké :
        # sa marge est calculée sur 100, pas sur 105
        self.assertAlmostEqual(r["trades"][1]["margin"], 100.0 * 0.1, places=9)

    def test_les_marks_ne_doublent_pas_le_pnl_du_trade_vivant(self):
        # au mark final (dt = hold), l'equity ≈ le réalisé : pas de double compte
        ev = _event(marks=[(6.0, 5.0)])
        r = run_stack([ev], 100.0, lambda e: 0.1, {})
        self.assertAlmostEqual(r["balance"], 100.5)
        self.assertAlmostEqual(r["max_dd"], 0.0)

    def test_liq_bookage_immediat_et_sans_marks(self):
        ev = _event(ret=-50.0)                     # mae >= liq_move → liq
        ev["mae_adverse"] = 99.9                   # liq_move = 100/1 - 0,5 = 99,5
        r = run_stack([ev], 100.0, lambda e: 0.1, {})
        self.assertEqual(r["n_liq"], 1)
        self.assertAlmostEqual(r["balance"], 90.0)  # -marge, booké à l'entrée
        self.assertEqual(r["trades"][0]["liq"], True)


if __name__ == "__main__":
    unittest.main()
