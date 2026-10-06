"""Tests du portefeuille MTM (PR-2, rapport GLM 5.3 №5/№6/№29).

Le moteur d'équité horaire : equity_t = cash + Σ unrealized(mark_t) —
les positions sont marquées chaque heure, publiant MAX_DD_MTM, MAX_DD_MTM_WORST
et MAX_DD_CLOSE séparément. Acceptance §39 : un short entry 100 / high 118 /
exit gagnant doit montrer un DD proche de l'excursion adverse.

    python tests/test_portfolio_mtm.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_runner import (  # noqa: E402
    _fetch_marks, run_wallet_mtm)

H = 3_600_000


def _marks(closes, high_pad=1.001, low_pad=0.999, sym="BTCUSDT"):
    t = np.arange(len(closes)) * H
    return {sym: {"t": t, "close": np.array(closes),
                  "high": np.array([c * high_pad for c in closes]),
                  "low": np.array([c * low_pad for c in closes])}}


def _ev(sym="BTCUSDT", t=0, h=24, side=-1, ret=1.0, entry=100.0, mae=0.5,
        fund=0.0, cost=0.28):
    return {"sym": sym, "t_ms": t * H, "exit_ms": (t + h) * H, "side": side,
            "ret_pct": ret, "entry": entry, "mae_pct": mae,
            "fund_pct": fund, "cost_pct": cost}


class TestMtm(unittest.TestCase):
    def test_le_dd_mtm_reflete_l_excursion_adverse(self):
        """Acceptance §39 : short entry 100, marks à 118 en cours de route,
        sortie gagnante — le DD MTM montre l'excursion (+18 % du notional),
        l'ancien DD close-seul montrait ~0."""
        ev = [_ev(ret=-1.0, entry=100.0, mae=0.5, cost=0.0)]
        closes = [100.0, 104, 108, 112, 116, 118, 115, 110] + [105] * 9 \
            + [103, 102, 99] + [99] * (24 - 16)
        w = run_wallet_mtm(ev, _marks(closes), capital=100.0, cap_pct=1.0,
                           lev=1.0)
        self.assertGreater(w["max_dd_mtm"], 0.15)      # 18 % de 1 $ ≈ 0.18 %
        self.assertLess(w["max_dd_close"], 0.001)      # l'ancien était aveugle
        self.assertGreaterEqual(w["max_dd_mtm_worst"], w["max_dd_mtm"])
        self.assertAlmostEqual(w["solde"], 100.01, places=6)  # +1 % de 1 $

    def test_comptabilite_reconciliee(self):
        """Δequity = realized + funding − fees — exactement, au centime."""
        ev = [_ev(ret=-2.0, entry=100.0, fund=0.03, cost=0.28)]
        closes = [100.0] * 24
        w = run_wallet_mtm(ev, _marks(closes), capital=100.0, cap_pct=1.0,
                           lev=1.0)
        # realized = +2 % de notional ; fund = +0.03 % ; fees = 0.28 %
        expected = 100.0 + (0.02 + 0.0003 - 0.0028)   # × notional ≈ 1 $
        self.assertAlmostEqual(w["solde"], expected, places=6)

    def test_liquidation_absorbee_des_l_entree(self):
        """La marge condamnée disparaît de l'équité DÈS l'heure d'entrée —
        le MTM la voit, le close-seul ne la voyait qu'à la sortie."""
        ev = [_ev(ret=-20.0, entry=100.0, mae=9.6, cost=0.0)]
        closes = [100.0] * 24
        # la sémantique STRESS (borne ex ante) est testée explicitement
        w = run_wallet_mtm(ev, _marks(closes), capital=100.0, cap_pct=1.0,
                           lev=10.0, liq_mode="stress")
        self.assertEqual(w["liqs"], 1)
        self.assertAlmostEqual(w["solde"], 99.0, places=6)
        self.assertGreaterEqual(w["max_dd_mtm"], 0.99)   # 1 $ sur ~100 $

    def test_concurrence_et_marge_mesurees(self):
        """№29 : 3 positions simultanées à cap 1 % → max_concurrency 3,
        marge engagée max 3 % de l'équité."""
        evs = [_ev(sym="BTCUSDT", t=0, ret=-1.0, entry=100.0, cost=0.0),
               _ev(sym="ETHUSDT", t=0, ret=-1.0, entry=100.0, cost=0.0),
               _ev(sym="SOLUSDT", t=0, ret=-1.0, entry=100.0, cost=0.0)]
        marks = {}
        for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            marks.update(_marks([100.0] * 24, sym=s))
        w = run_wallet_mtm(evs, marks, capital=100.0, cap_pct=1.0, lev=1.0)
        self.assertEqual(w["max_concurrency"], 3)
        self.assertAlmostEqual(w["max_margin_used_pct"], 3.0, places=6)
        # l'heure de sortie compte 0 position ouverte : 3×24/25 = 2.88
        self.assertAlmostEqual(w["avg_concurrency"], 2.88, places=2)
        self.assertAlmostEqual(w["max_gross_notional_pct"], 3.0, places=6)

    def test_le_funding_partiel_est_inconnu(self):
        """№5 au kernel : une fenêtre de funding qui dépasse le dernier print
        connu est NaN — jamais un partiel présenté comme complet."""
        import sqlite3
        import tempfile
        from scripts.label_matrix import build_matrix
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = sqlite3.connect(db)
            con.executescript("""
            CREATE TABLE klines (symbol TEXT, interval TEXT,
                open_time INTEGER, open REAL, high REAL, low REAL,
                close REAL, volume REAL);
            CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
                rate REAL);
            """)
            for i in range(40):
                con.execute("INSERT INTO klines VALUES "
                            "('BTCUSDT','1h',?,100,101,99,100,1.0)",
                            (i * H,))
                if i < 10:   # les prints s'arrêtent à h10
                    con.execute("INSERT INTO funding_history VALUES "
                                "('BTCUSDT', ?, 0.0001)", ((i + 1) * H,))
            con.commit()
            con.close()
            _, mat = build_matrix(["BTCUSDT"], (6,), db_path=db,
                                  use_cache=False)
            f = mat["BTCUSDT"]["fund_6"]
            self.assertFalse(np.isnan(f[0]))    # fenêtre 0-6h ⊆ prints ✓
            self.assertTrue(np.isnan(f[8]))     # fenêtre 8-14h > dernier print


if __name__ == "__main__":
    unittest.main()
