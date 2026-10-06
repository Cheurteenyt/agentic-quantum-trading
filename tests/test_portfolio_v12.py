"""Tests PR-7 : les métriques au niveau PORTEFEUILLE (audit GLM 5.3
post-#138) — la vraie unité d'observation est la courbe d'équité horaire.

    python tests/test_portfolio_v12.py
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
    block_bootstrap_hourly, effective_sample_size, run_wallet_mtm)

H = 3_600_000


def _marks(flat=100.0, n=200, sym="BTCUSDT"):
    return {sym: {"t": np.arange(n) * H, "close": np.full(n, flat),
                  "high": np.full(n, flat), "low": np.full(n, flat)}}


def _ev(sym="BTCUSDT", t=0, h=24, side=-1, ret=-2.0, entry=100.0, mae=0.5,
        fund=0.0, cost=0.28):
    return {"sym": sym, "t_ms": t * H, "exit_ms": (t + h) * H, "side": side,
            "ret_pct": ret, "entry": entry, "mae_pct": mae,
            "fund_pct": fund, "cost_pct": cost, "fund_prints": []}


class TestLiqNormalisee(unittest.TestCase):
    def test_une_liquidation_est_dans_trade_pnls(self):
        """P1 : une liquidation produit le MÊME objet normalisé que les
        autres trades — PF, top-N, effective-N et bootstrap la consomment."""
        w = run_wallet_mtm([_ev(ret=50.0, mae=9.6)], _marks(),
                           capital=100.0, cap_pct=1.0, lev=10.0,
                           liq_mode="stress")
        self.assertEqual(w["liqs"], 1)
        self.assertEqual(len(w["trade_pnls"]), 1)
        tp = w["trade_pnls"][0]
        self.assertTrue(tp["liquidated"])
        self.assertAlmostEqual(tp["net"], -1.0, places=9)   # −marge
        self.assertAlmostEqual(w["profit_factor"], 0.0, places=9)


class TestPortfolioMetrics(unittest.TestCase):
    def test_sharpe_portefeuille_sur_la_courbe(self):
        """Le Sharpe PORTEFEUILLE est calculé sur les rendements HORAIRES de
        l'équité MTM — pas sur les trades ; il diffère du trade-level."""
        evs = [_ev(t=k * 24, ret=(-1.0) ** k * 3.0, cost=0.0, fund=0.0)
               for k in range(10)]
        w = run_wallet_mtm(evs, _marks(), capital=100.0, cap_pct=1.0,
                           lev=1.0)
        self.assertIsNotNone(w["portfolio_sharpe"])
        self.assertIsNotNone(w["portfolio_sortino"])
        self.assertIn("trade_sortino", w)          # renommé honnêtement
        self.assertNotIn("sortino", w)             # l'ancien nom ambigu est mort

    def test_sharpe_differente_de_la_t_stat(self):
        """P1 : Sharpe = mean/sd annualisé ; t-stat = mean/(sd/√n) — deux
        objets distincts, publiés séparément."""
        rng = np.random.default_rng(3)
        rets = rng.normal(0.0002, 0.001, 500)
        bs = block_bootstrap_hourly(rets, block_hours=24, seed=42)
        lo, hi = bs["sharpe_ci95"]
        tlo, thi = bs["t_stat_ci95"]
        # le Sharpe annualisé = t_stat × √(heures_an/n) — pour n=500 :
        # √(8766/500) ≈ 4,19 → les deux objets NE SONT PAS le même nombre
        ratio = hi / max(thi, 1e-9)
        self.assertGreater(ratio, 3.5)
        self.assertLess(ratio, 5.0)
        self.assertNotAlmostEqual(bs["sharpe_ci95"][1],
                                  bs["t_stat_ci95"][1], places=2)
        # le Sharpe de la série complète : mean/sd × √(24×365,25)
        sr = rets.mean() / rets.std(ddof=1) * np.sqrt(24 * 365.25)
        self.assertLess(lo, sr + 1.0)
        self.assertGreater(hi, sr - 1.0)

    def test_sortino_portefeuille_ge_sharpe(self):
        """Le Sortino (downside uniquement) doit dépasser le Sharpe sur une
        série à pertes bornées — le contrôle de cohérence manquant."""
        evs = [_ev(t=k * 24, ret=(-1.0) ** k * 3.0, cost=0.0, fund=0.0)
               for k in range(10)]
        w = run_wallet_mtm(evs, _marks(), capital=100.0, cap_pct=1.0,
                           lev=1.0)
        self.assertGreaterEqual(w["portfolio_sortino"],
                                w["portfolio_sharpe"])


class TestCounterfactual(unittest.TestCase):
    def test_contre_factuel_differe_de_la_concentration(self):
        """P1 : retirer arithmétiquement le top-N (concentration) n'est pas
        re-jouer le wallet sans ces trades (les tailles se recalculent)."""
        # 4 trades : le 4e est un énorme gagnant qui gonfle toutes les
        # tailles suivantes — le contre-factuel re-dimensionne tout
        evs = [_ev(t=k * 24, ret=-90.0 if k == 0 else -2.0, cost=0.0,
                   fund=0.0) for k in range(11)]
        w = run_wallet_mtm(evs, _marks(), capital=100.0, cap_pct=1.0,
                           lev=1.0)
        pnls = w["trade_pnls"]
        top = sorted(pnls, key=lambda x: -x["net"])[0]
        conc = 100.0 + sum(p["net"] for p in pnls) - top["net"]
        cf = run_wallet_mtm([e for e in evs
                             if e["t_ms"] != top["t_ms"]], _marks(),
                            capital=100.0, cap_pct=1.0, lev=1.0)
        self.assertNotAlmostEqual(cf["solde"], conc, places=3)
        self.assertGreater(cf["solde"], 100.0)   # sans le gagnant : les
        # autres trades restent gagnants, re-dimensionnés sur 100 $


class TestEffectiveN(unittest.TestCase):
    def test_invariant_a_l_ordre_des_simultanes(self):
        """P2 : l'ordre des trades à timestamp identique ne doit pas changer
        l'autocorrélation ni l'effective_n."""
        rets = [2.0 - 0.1 * (k % 7) for k in range(40)]
        evs_a = [_ev(sym=f"S{k:02d}", t=0, ret=rets[k], cost=0.0)
                 for k in range(40)]
        w_a = run_wallet_mtm(evs_a, {}, capital=100.0, cap_pct=1.0, lev=1.0)
        # MÊMES données, ordre de la LISTE inversé (le tri (t_ms, sym)
        # doit normaliser) — changer sym↔ret changerait les données
        evs_b = list(reversed(evs_a))
        w_b = run_wallet_mtm(evs_b, {}, capital=100.0, cap_pct=1.0, lev=1.0)
        e_a, e_b = effective_sample_size(w_a["trade_pnls"]), \
            effective_sample_size(w_b["trade_pnls"])
        self.assertEqual(e_a["n_time_buckets"], 1)
        self.assertEqual(e_a["autocorr_1"], e_b["autocorr_1"])
        self.assertEqual(e_a["effective_n"], e_b["effective_n"])


class TestCagrSpan(unittest.TestCase):
    def test_le_cagr_mesure_la_duree_de_la_vue(self):
        """P2 : le CAGR est annualisé sur la VUE (span), pas sur le
        premier trade → dernier exit — les mois plats comptent."""
        evs = [_ev(t=0, ret=-2.0, cost=0.0), _ev(t=24 * 30, ret=-2.0,
                                                 cost=0.0)]
        span = (0, 200 * 24 * H)        # la vue dure 200 jours
        w = run_wallet_mtm(evs, _marks(n=200 * 24), capital=100.0,
                           cap_pct=1.0, lev=1.0, span=span)
        self.assertAlmostEqual(w["years"], 200 / 365.25, places=6)
        w2 = run_wallet_mtm(evs, _marks(n=200 * 24), capital=100.0,
                            cap_pct=1.0, lev=1.0)   # sans span : 744 h
        self.assertAlmostEqual(w2["years"], 744 / 24 / 365.25, places=6)


class TestProvenance(unittest.TestCase):
    def test_incoherence_spec_sha_refuse_le_wallet(self):
        """P0/P1 : manifest ≠ summary_confirmation ≠ spec.json → refus de
        publier le wallet (avant tout calcul d'affichage)."""
        from scripts import portfolio_runner as pr
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            rdir = runs / "EXP-sha"
            rdir.mkdir(parents=True)
            spec = {"id": "EXP-sha",
                    "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                             "train_start": 0, "train_end": 40 * H,
                             "validation_start": 40 * H,
                             "validation_end": 80 * H},
                    "signal": {"feature": "ret_1h", "op": "<=",
                               "threshold": -1000.0, "side": -1},
                    "horizons": [6], "cost_pct": 0.0}
            (rdir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            sha = pr.rr.spec_sha(spec)
            (rdir / "summary_discovery.json").write_text(json.dumps(
                {"verdict": "DISCOVERY_PASS", "spec_sha": sha,
                 "frozen_thresholds": {}}), encoding="utf-8")
            # le manifeste pointe vers UNE AUTRE spec → incohérence
            (rdir / "manifest.json").write_text(json.dumps(
                {"spec_sha": "deadbeef" * 4, "snapshot": "x"}),
                encoding="utf-8")
            saved = pr.RUNS
            pr.RUNS = runs
            try:
                with self.assertRaises(ValueError):
                    pr.wallet_for_run("EXP-sha", db_path=_missing_db(tmp),
                                      view_kind="train")
            finally:
                pr.RUNS = saved


def _missing_db(tmp):
    from scripts.label_matrix import build_matrix
    # une mini-DB saine : le garde doit lever AVANT tout calcul lourd
    db = Path(tmp) / "k.db"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
        rate REAL);
    """)
    for i in range(80):
        con.execute("INSERT INTO klines VALUES "
                    "('BTCUSDT','1h',?,100,101,99,100,1.0)", (i * H,))
    con.commit()
    con.close()
    return db


if __name__ == "__main__":
    unittest.main()
