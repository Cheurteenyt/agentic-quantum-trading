"""FIX lot2 — F3 (funding as-of, la mort de la moyenne full-sample) et
F12 (l'intervalle de funding devient une donnée mesurée, jamais supposée).

Bug prouvé : les sims chargeaient sum(rates)/len(rates)/8 et appliquaient
cette moyenne à CHAQUE trade historique — un trade 2022 recevait la
moyenne 2022-2026 (look-ahead pur), et un trade d'un contrat à 4h
recevait un taux divisé par 8 au lieu de 4.

    python tests/test_lot2_funding_asof.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))   # refresh_aster_cache importe aster_rate

from backend.services.backtest_v2.costs import (  # noqa: E402
    FundingRate, funding_cost_usd, load_funding_rate)
from scripts.funding_series import FundingSeries, funding_series_all  # noqa: E402
from scripts.portfolio_sim import run_sim  # noqa: E402
from scripts.refresh_aster_cache import parse_funding_rows  # noqa: E402
from scripts.stacked_portfolio import run_stack  # noqa: E402

H_MS = 3_600_000.0

ROWS = [(0.0, 0.0001), (8 * H_MS, 0.0002), (16 * H_MS, 0.0004)]
# en points de % : 0.01, 0.02, 0.04


def _series():
    return FundingSeries.from_rows(ROWS)


class TestFundingSeries(unittest.TestCase):
    def test_interval_mesure_mediane_des_gaps(self):
        self.assertAlmostEqual(_series().interval_h, 8.0)
        rows4 = [(0.0, 0.0001), (4 * H_MS, 0.0002), (8 * H_MS, 0.0003)]
        self.assertAlmostEqual(FundingSeries.from_rows(rows4).interval_h, 4.0)

    def test_from_rows_accepte_un_ordre_quelconque(self):
        fs = FundingSeries.from_rows(list(reversed(ROWS)))
        self.assertAlmostEqual(fs.sum_pct_between(-1, 17 * H_MS), 0.07)

    def test_from_rows_vide_refuse(self):
        with self.assertRaises(ValueError):
            FundingSeries.from_rows([])

    def test_fenetre_ferme_a_droite_ouverte_a_gauche(self):
        fs = _series()
        self.assertAlmostEqual(fs.sum_pct_between(-1, 8 * H_MS), 0.03)
        # le taux à t=0 est exclu (t0 exclusif) : fenêtre (0, 8h-1] → vide
        self.assertAlmostEqual(fs.sum_pct_between(0, 8 * H_MS - 1), 0.0)
        # le taux à t=0 compte si l'entrée est AVANT lui
        self.assertAlmostEqual(fs.sum_pct_between(-1, 8 * H_MS - 1), 0.01)
        # le taux à l'entrée exacte est exclu, celui à la sortie compte
        self.assertAlmostEqual(fs.sum_pct_between(1, 8 * H_MS), 0.02)

    def test_aucun_taux_fabrique_hors_observations(self):
        fs = _series()
        self.assertEqual(fs.sum_pct_between(-100 * H_MS, -1), 0.0)
        self.assertEqual(fs.sum_pct_between(17 * H_MS, 999 * H_MS), 0.0)
        self.assertEqual(fs.sum_pct_between(10, 5), 0.0)


def _event(ts_ms, hold_h=16.0, sign=1):
    return {"strategy": "s", "ts_ms": int(ts_ms * 1e6), "lev": 1.0,
            "mae_adverse": 1.0, "fee_rt_bps": 0.0, "sym": "XUSDT",
            "hold_h": hold_h, "price_ret_short": 0.0, "fund_sign": sign}


class TestRunStackAsOf(unittest.TestCase):
    def test_le_funding_reel_de_la_fenetre_est_applique(self):
        # entrée 5h, hold 16h → (5h, 21h] couvre les taux à 8h et 16h : 0.06 %
        ev = _event(5 * H_MS)
        r = run_stack([ev], 100.0, lambda e: 0.1, {"XUSDT": _series()})
        # notional = 100 × 0,1 × 1 = 10 → fund = 10 × 0.06/100 = 0.006
        self.assertAlmostEqual(r["balance"], 100.006, places=9)
        self.assertAlmostEqual(r["funding"], 0.006, places=9)

    def test_le_shim_float_legacy_tient_encore(self):
        ev = _event(0.0, hold_h=24.0)
        r = run_stack([ev], 100.0, lambda e: 0.1, {"XUSDT": 0.01})  # %/h
        # fund = 10 × 0.01/100 × 24 = 0.024
        self.assertAlmostEqual(r["balance"], 100.024, places=9)

    def test_symbole_sans_funding_ne_explose_pas(self):
        r = run_stack([_event(0.0)], 100.0, lambda e: 0.1, {})
        self.assertAlmostEqual(r["balance"], 100.0)


class TestRunSimAsOf(unittest.TestCase):
    def test_le_funding_reel_de_la_fenetre_est_applique(self):
        ev = _event(5 * H_MS)
        r = run_sim([ev], 100.0, 0.1, {"XUSDT": _series()}, 0, 0)
        # notional = 100 × 0,1 × LEV(20) = 200 → fund = 200 × 0.06/100 = 0.12
        self.assertAlmostEqual(r["balance"], 100.12, places=9)


class TestFundingPaidPct(unittest.TestCase):
    def test_la_fenetre_du_trade_seule_compte(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE funding_history (symbol TEXT, "
                    "funding_time INTEGER, rate REAL)")
        con.executemany(
            "INSERT INTO funding_history VALUES (?,?,?)",
            [("XUSDT", 5 * H_MS, 0.0001),    # avant l'entrée 10h : exclu
             ("XUSDT", 12 * H_MS, 0.0002),   # dans (10h, 20h] : compté
             ("XUSDT", 19 * H_MS, 0.0004),   # dedans : compté
             ("XUSDT", 25 * H_MS, 0.0008)])  # après la sortie : exclu
        from scripts.paper_forward import funding_paid_pct
        s = funding_paid_pct(con, "XUSDT", 10 * H_MS, 20 * H_MS)
        self.assertAlmostEqual(s, 0.06)   # (0.0002 + 0.0004) × 100
        self.assertAlmostEqual(
            funding_paid_pct(con, "YUSDT", 0, 999 * H_MS), 0.0)


class TestFundingIntervalCosts(unittest.TestCase):
    """F12 : l'intervalle vient du cache mesuré, le /8 supposé est mort."""

    def test_un_intervalle_de_4h_double_le_cout(self):
        base = dict(symbol="X", avg_bps_per_8h=1.0, sample_count=10,
                    last_funding_time_ms=0, cached_at=time.time())
        c8 = funding_cost_usd(1000.0, 8.0, "long",
                              FundingRate(**base, interval_hours=8.0))
        c4 = funding_cost_usd(1000.0, 8.0, "long",
                              FundingRate(**base, interval_hours=4.0))
        self.assertAlmostEqual(c8, -0.1)
        self.assertAlmostEqual(c4, -0.2)

    def test_cache_sans_cle_intervalle_defaut_8h(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cache.json"
            p.write_text(json.dumps({"symbols": {"XUSDT": {
                "cached_at": time.time(),
                "data": {"status": "ok", "avg_funding_bps_per_8h": 1.0,
                         "funding_count": 5, "last_funding_time": 123}}}}))
            rate = load_funding_rate("XUSDT", cache_path=p)
            self.assertEqual(rate.interval_hours, 8.0)

    def test_parse_funding_rows_publie_l_intervalle_mesure(self):
        rows = [{"fundingTime": 0, "fundingRate": "0.0001"},
                {"fundingTime": 4 * H_MS, "fundingRate": "0.0002"},
                {"fundingTime": 8 * H_MS, "fundingRate": "0.0003"}]
        payload = parse_funding_rows("XUSDT", rows)
        self.assertAlmostEqual(payload["funding_interval_hours"], 4.0)


class TestLoaderUnique(unittest.TestCase):
    def test_funding_series_all_lit_la_base_reelle(self):
        # le warehouse n'existe pas chez le runner CI : le test ne porte que
        # là où la donnée réelle est (localement / sur la machine de grind)
        if not (ROOT / "data" / "warehouse" / "klines.db").exists():
            self.skipTest("warehouse DB absente (CI)")
        out = funding_series_all()
        self.assertGreater(len(out), 0)
        some = next(iter(out.values()))
        self.assertIsInstance(some, FundingSeries)
        self.assertGreater(some.interval_h, 0.0)


if __name__ == "__main__":
    unittest.main()
