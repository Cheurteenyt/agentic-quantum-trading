"""Tests de la couche portefeuille (Research OS PR-B, rapport v6).

Le wallet séquentiel sur des events synthétiques : anti-chevauchement par
symbole, cap de marge, liquidation ex ante (MAE ≥ 100/lev − 0,5), funding
signé, bookage au mois de sortie, DD max — et la baseline long-and-hold
sur une fixture DB.

    python tests/test_portfolio_runner.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_runner import (  # noqa: E402
    baseline_hold, collect_events, run_wallet)
from scripts import research_runner as rr  # noqa: E402

H_MS = 3_600_000


def _ev(sym="BTCUSDT", t=0, h=24, side=-1, ret=1.0, mae=0.5, fund=0.01,
        cost=0.28):
    return {"sym": sym, "t_ms": t * H_MS, "exit_ms": (t + h) * H_MS,
            "side": side, "ret_pct": ret, "mae_pct": mae,
            "fund_pct": fund, "cost_pct": cost}


class TestWallet(unittest.TestCase):
    def test_pnl_mathematique_basique(self):
        """1 trade 1x, marge 1 % de 100 $, short sur ret −1 % (il gagne),
        funding +0,01 reçu par le short, coût 0,28 → pnl = 1$ × 0,73/100."""
        w = run_wallet([_ev(ret=-1.0, fund=0.01, cost=0.28)],
                       capital=100.0, cap_pct=1.0, lev=1.0)
        self.assertAlmostEqual(w["solde"], 100.0 + 0.0073, places=6)
        self.assertEqual(w["trades"], 1)
        self.assertEqual(w["liqs"], 0)

    def test_le_long_paie_le_funding_positif(self):
        """Convention signée : side +1 → fund_signed = −fund."""
        w = run_wallet([_ev(side=1, ret=0.0, fund=0.01, cost=0.0)],
                       capital=100.0, cap_pct=1.0, lev=1.0)
        self.assertAlmostEqual(w["solde"], 100.0 - 0.0001, places=9)
        self.assertAlmostEqual(w["funding_net"], -0.0001, places=9)

    def test_anti_chevauchement_par_symbole(self):
        """Le 2e trade BTC qui chevauche le 1er est sauté ; le trade d'un
        AUTRE symbole sur la même fenêtre passe (le portefeuille tient
        plusieurs positions en parallèle)."""
        evs = [_ev(sym="BTCUSDT", t=0, ret=1.0),
               _ev(sym="BTCUSDT", t=10, ret=5.0),    # chevauche → sauté
               _ev(sym="ETHUSDT", t=10, ret=5.0)]    # autre symbole → pris
        w = run_wallet(evs, capital=100.0, cap_pct=1.0, lev=1.0)
        self.assertEqual(w["trades"], 2)
        self.assertEqual(w["skipped_overlap"], 1)

    def test_liquidation_ex_ante_coute_la_marge(self):
        """MAE ≥ 100/lev − 0,5 → liquidation, perte = la marge engagée.
        À 10x : seuil 9,5 % ; un MAE 9,6 % tue, un MAE 9,4 % survit — et le
        ret de la bougie de mort est IGNORÉ (la mort, pas le mark)."""
        dead = _ev(ret=-20.0, mae=9.6)
        alive = _ev(ret=-20.0, mae=9.4)      # short gagnant qui survit
        w = run_wallet([dead], capital=100.0, cap_pct=1.0, lev=10.0)
        self.assertEqual(w["liqs"], 1)
        self.assertAlmostEqual(w["solde"], 99.0, places=9)
        w2 = run_wallet([alive], capital=100.0, cap_pct=1.0, lev=10.0)
        self.assertEqual(w2["liqs"], 0)
        self.assertGreater(w2["solde"], 100.0)

    def test_cap_de_marge_sur_equite_courante(self):
        """La marge suit l'équité COURANTE : après une perte, le notional
        rétrécit (la géométrie de la descente), pas une marge constante."""
        # short perdant : le prix monte de 50 % → gross = −50.27 %
        evs = [_ev(t=0, ret=50.0), _ev(t=100, ret=50.0)]
        w = run_wallet(evs, capital=100.0, cap_pct=1.0, lev=1.0)
        # 1er : marge 1,0 → pnl −0,5027 → éq 99,4973
        # 2e : marge 0,994973 → pnl −0,500173 → éq 98,9971271
        self.assertAlmostEqual(w["solde"], 98.9971271, places=4)

    def test_dd_max_et_mois_negatifs(self):
        # 3 mois différents (1000h > 744h) ; le short gagne quand ret < 0
        evs = [_ev(t=0, ret=-2.0),           # +0.0173
               _ev(t=1000, ret=80.0),        # −0.8027 (le mois 2 perd)
               _ev(t=2000, ret=-3.0)]        # +0.0271
        w = run_wallet(evs, capital=100.0, cap_pct=1.0, lev=1.0)
        self.assertGreater(w["max_dd_pct"], 0.5)
        self.assertEqual(w["months_neg"], 1)
        self.assertEqual(w["months_total"], 3)


class TestBaseline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
        CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL);
        """)
        # BTC ×2 sur 3 jours (courbe 100→200), ETH plat
        for i in range(72):
            c = 100.0 * (1 + i / 71.0)
            con.execute("INSERT INTO klines VALUES "
                        "('BTCUSDT','1h',?,100,101,99,?,1.0)",
                        (i * H_MS, c))
            con.execute("INSERT INTO klines VALUES "
                        "('ETHUSDT','1h',?,50,51,49,50,1.0)", (i * H_MS,))
        con.commit()
        con.close()
        self.spec = {"data": {"symbols": ["BTCUSDT", "ETHUSDT"]}}
        self.view = rr.DataView("test-fixture", "confirmation", 0, 72 * H_MS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_baseline_equal_weight_hold(self):
        bl = baseline_hold(self.spec, self.view, db_path=self.db,
                           capital=100.0)
        # BTC double (+100 %), ETH plat → portefeuille +50 %
        self.assertAlmostEqual(bl["roi_pct"], 50.0, delta=1.0)
        self.assertAlmostEqual(bl["solde"], 150.0, delta=1.0)
        # DD d'une courbe montante = 0
        self.assertAlmostEqual(bl["max_dd_pct"], 0.0, places=6)
        self.assertEqual(bl["months_neg"], 0)


class TestCollectEvents(unittest.TestCase):
    def test_events_portent_mae_et_funding(self):
        """collect_events convertit les fractions hi/lo du kernel en % et
        applique la convention MAE par côté (short = high)."""
        import numpy as np
        tmp = tempfile.TemporaryDirectory()
        db = Path(tmp.name) / "k.db"
        con = sqlite3.connect(db)
        con.executescript("""
        CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL);
        """)
        # 120 barres plates (les features viennent d'une matrice injectée)
        for i in range(120):
            con.execute("INSERT INTO klines VALUES "
                        "('BTCUSDT','1h',?,100,101,99,100,1.0)",
                        (i * H_MS,))
        con.commit()
        con.close()
        spec = {"data": {"symbols": ["BTCUSDT"]},
                "signal": {"feature": "ret_1h", "op": "<=",
                           "threshold": 1000.0, "side": -1},
                "horizons": [6], "cost_pct": 0.28}
        feats = rr.compute_features(sqlite3.connect(db), "BTCUSDT")
        n = 120
        ret = np.full(n, 1.0)
        hi = np.full(n, 0.01)          # fractions du kernel
        hi[100] = 0.20                 # la barre 100 : high +20 % au-dessus
        lo = np.full(n, 0.005)
        fund = np.full(n, 0.01)
        matrix_cols = {"BTCUSDT": {
            "open_time_ns": feats["open_time_ns"],
            "entry": np.full(n, 100.0),
            "ret_6": ret, "hi_6": hi, "lo_6": lo, "fund_6": fund}}

        class V:
            start_ms = 0
            end_ms = 120 * H_MS

        events, fund_cov = collect_events(spec, matrix_cols,
                                          {"BTCUSDT": feats}, V(),
                                          db_path=db)
        self.assertGreater(len(events), 0)
        self.assertGreater(fund_cov, 0.99)   # fund_6 fourni → connu
        e0 = events[0]
        self.assertEqual(e0["side"], -1)
        self.assertEqual(e0["cost_pct"], 0.28)
        # la barre 100 (high +20 %) porte MAE 20 % côté short
        e100 = [e for e in events if e["t_ms"] == 100 * H_MS][0]
        self.assertAlmostEqual(e100["mae_pct"], 20.0, places=6)
        self.assertAlmostEqual(e100["fund_pct"], 0.01, places=9)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
