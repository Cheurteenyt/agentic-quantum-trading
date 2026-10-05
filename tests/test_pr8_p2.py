"""Tests PR-8 : liquidation SIMULÉE (premier franchissement réel),
CONTIGUOUS_MARK (staleness des marks), baseline premier mois,
registry_sync (chiffres scellés + drift).

    python tests/test_pr8_p2.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_runner import (  # noqa: E402
    baseline_hold, run_wallet_mtm)
from scripts import registry_sync  # noqa: E402
from scripts import research_runner as rr  # noqa: E402

H = 3_600_000


def _ev(sym="BTCUSDT", t=0, h=24, side=-1, ret=-2.0, entry=100.0, mae=0.5,
        fund=0.0, cost=0.0):
    return {"sym": sym, "t_ms": t * H, "exit_ms": (t + h) * H, "side": side,
            "ret_pct": ret, "entry": entry, "mae_pct": mae,
            "fund_pct": fund, "cost_pct": cost, "fund_prints": []}


def _marks_path(closes, sym="BTCUSDT"):
    n = len(closes)
    return {sym: {"t": np.arange(n) * H, "close": np.array(closes),
                  "high": np.array([c * 1.001 for c in closes]),
                  "low": np.array([c * 0.999 for c in closes])}}


class TestLiqSimulee(unittest.TestCase):
    def test_la_mort_au_premier_franchissement_pas_a_l_entree(self):
        """PR-8 : le short meurt à l'heure où le high franchit le seuil
        (t+12h ici), PAS à l'entrée — l'équité vit la trajectoire."""
        ev = [_ev(ret=-90.0, mae=9.6, entry=100.0)]
        closes = [100.0] * 12 + [110.0] * 12    # franchissement à t+12h
        w = run_wallet_mtm(ev, _marks_path(closes), capital=100.0,
                           cap_pct=1.0, lev=10.0)   # seuil 9,5 %
        self.assertEqual(w["liqs"], 1)
        self.assertAlmostEqual(w["solde"], 99.0, places=9)
        # le mark de 12h n'est CONNAISSABLE qu'à 13h (aucun look-ahead) :
        # la mort est datée de la première heure où le compte LA VOIT
        self.assertEqual(w["trade_pnls"][0]["exit_ms"], 13 * H)
        self.assertTrue(w["trade_pnls"][0]["liquidated"])
        self.assertEqual(w["liq_mode"], "simulated")

    def test_le_mode_stress_absorbe_a_l_entree(self):
        """L'ancienne convention reste disponible : borne conservatrice,
        la marge disparaît dès l'heure d'entrée."""
        ev = [_ev(ret=-90.0, mae=9.6, entry=100.0)]
        closes = [100.0] * 12 + [110.0] * 12
        w = run_wallet_mtm(ev, _marks_path(closes), capital=100.0,
                           cap_pct=1.0, lev=10.0, liq_mode="stress")
        self.assertEqual(w["liqs"], 1)
        self.assertAlmostEqual(w["solde"], 99.0, places=9)
        self.assertEqual(w["trade_pnls"][0]["exit_ms"], 24 * H)  # exit déclaré


class TestContiguousMark(unittest.TestCase):
    def test_la_staleness_des_marks_est_publiee(self):
        """Un trou de données dans les marks → stale_mark_hours et
        max_mark_gap_h le disent (le mark conservé reste documenté)."""
        ev = [_ev(ret=-2.0)]
        closes = [100.0] * 24
        mk = _marks_path(closes)
        # trou : les barres 5..9 manquent
        keep = [i for i in range(24) if not 5 <= i <= 9]
        mk["BTCUSDT"]["t"] = mk["BTCUSDT"]["t"][keep]
        mk["BTCUSDT"]["close"] = mk["BTCUSDT"]["close"][keep]
        mk["BTCUSDT"]["high"] = mk["BTCUSDT"]["high"][keep]
        mk["BTCUSDT"]["low"] = mk["BTCUSDT"]["low"][keep]
        w = run_wallet_mtm(ev, mk, capital=100.0, cap_pct=1.0, lev=1.0)
        self.assertGreater(w["stale_mark_hours"], 0)
        self.assertGreaterEqual(w["max_mark_gap_h"], 4)


class TestBaselinePremierMois(unittest.TestCase):
    def test_le_premier_mois_negatif_compte(self):
        """P2 : le premier mois se compare au capital initial — un mois 1
        négatif doit compter dans months_neg."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = sqlite3.connect(db)
            con.executescript("""
            CREATE TABLE klines (symbol TEXT, interval TEXT,
                open_time INTEGER, open REAL, high REAL, low REAL,
                close REAL, volume REAL);
            """)
            # 3 mois : le prix CHUTE de 30 % DANS le premier mois, puis flat
            for i in range(90 * 24):
                c = 100.0 * (1.0 - 0.3 * min(i / (30.0 * 24), 1.0))
                con.execute("INSERT INTO klines VALUES "
                            "('BTCUSDT','1h',?,100,101,99,?,1.0)", (i * H, c))
            con.commit()
            con.close()
            spec = {"data": {"symbols": ["BTCUSDT"]}}
            view = rr.DataView("t", "train", 0, 90 * 24 * H)
            bl = baseline_hold(spec, view, db_path=db, capital=100.0)
            self.assertGreaterEqual(bl["months_neg"], 1)


class TestRegistrySync(unittest.TestCase):
    def test_sealed_lit_les_artefacts(self):
        """registry_sync expose les chiffres scellés d'un run existant."""
        s = registry_sync.sealed("EXP-crash-short-6h-univ10")
        self.assertIsNotNone(s)
        self.assertEqual(s["confirmation"]["verdict"], "CONFIRMED")
        self.assertIn("wallet", s)
        self.assertIn("git_sha", s)

    def test_check_signale_le_drift(self):
        """Les runs produits par un autre état du code sont signalés —
        leurs chiffres sont historiques, pas reproductibles."""
        rc = registry_sync.check()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
