"""Tests PR-6 : les métriques du rapport final et le bootstrap par blocs
(audit GLM 5.3 §36 + améliorations 2-3).

    python tests/test_portfolio_bootstrap.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_runner import (  # noqa: E402
    block_bootstrap, effective_sample_size, run_wallet_mtm)

H = 3_600_000


def _marks(flat=100.0, n=24, sym="BTCUSDT"):
    return {sym: {"t": np.arange(n) * H, "close": np.full(n, flat),
                  "high": np.full(n, flat), "low": np.full(n, flat)}}


def _ev(sym="BTCUSDT", t=0, h=24, side=-1, ret=-2.0, entry=100.0, mae=0.5,
        fund=0.0, cost=0.28):
    return {"sym": sym, "t_ms": t * H, "exit_ms": (t + h) * H, "side": side,
            "ret_pct": ret, "entry": entry, "mae_pct": mae,
            "fund_pct": fund, "cost_pct": cost,
            "fund_prints": []}


class TestAdvanced(unittest.TestCase):
    def _wallet(self, rets):
        """Des trades séquentiels non chevauchants (1/jour) sur marks plats."""
        evs = [_ev(t=k * 24, ret=r, cost=0.0, fund=0.0)
               for k, r in enumerate(rets)]
        return run_wallet_mtm(evs, _marks(), capital=100.0, cap_pct=1.0,
                              lev=1.0), evs

    def test_cagr_profit_factor(self):
        """CAGR sur la durée réelle, profit factor = gains bruts / pertes.
        Le short gagne quand ret < 0 : pnls [+0.3, −0.1, −0.1] $."""
        w, _ = self._wallet([-30.0, 10.0, 10.0])
        # places=2 : la marge suit l'équité composée (géométrie légitime)
        self.assertAlmostEqual(w["profit_factor"], 30.0 / 20.0, places=2)
        # 3 trades × 24 h = 3 jours ; CAGR annualisé cohérent
        self.assertGreater(w["cagr_pct"], 0)
        self.assertAlmostEqual(w["years"], 3 / 365.25, places=6)

    def test_solde_sans_top(self):
        """PnL sans top 1/5/10 % — l'edge ne doit pas tenir à une poignée
        de coups de chance ; ici un seul gros gagnant domine."""
        w, _ = self._wallet([2.0, 2.0, 2.0, -90.0])   # le 4e fait tout (short)
        self.assertLess(w["solde_sans_top1"], w["solde"] - 0.5)
        self.assertAlmostEqual(w["solde_sans_top1"], w["solde_sans_top5"],
                               places=9)   # 1 et 5 % de 4 trades = 1 trade

    def test_effective_n_serie_non_chevauchante(self):
        """Des trades séquentiels iid : n_nonoverlap = n, autocorr ~0,
        effective_n ≈ n."""
        rng = np.random.default_rng(7)
        rets = rng.normal(0.5, 1.0, 50).tolist()   # pseudo-aléatoire : ~iid
        w, evs = self._wallet(rets)
        eff = effective_sample_size(w["trade_pnls"])
        self.assertEqual(eff["n_raw"], 50)
        self.assertEqual(eff["n_nonoverlap"], 50)
        self.assertLess(abs(eff["autocorr_1"]), 0.35)
        self.assertGreater(eff["effective_n"], 30)

    def test_effective_n_serie_chevauchante(self):
        """50 trades se chevauchant (même heure, symboles différents) : la
        série est corrélée (même fenêtre de marché) — effective_n < n."""
        evs = [_ev(sym=f"S{k}", t=0, ret=-2.0, cost=0.0)
               for k in range(40)]
        w = run_wallet_mtm(evs, {}, capital=100.0, cap_pct=1.0, lev=1.0)
        eff = effective_sample_size(w["trade_pnls"])
        self.assertEqual(eff["n_raw"], 40)
        self.assertEqual(eff["n_nonoverlap"], 1)   # tout chevauche tout


class TestBootstrap(unittest.TestCase):
    def _pnls(self, rets, overlap=False):
        # net en DOLLARS pour notional 1 $ : le moteur convertit net/notional
        # ×100 en % — un ret de 0.10 % = 0.001 $
        return [{"t_ms": (0 if overlap else k * 24) * H,
                 "exit_ms": 24 * H, "notional": 1.0, "net": r / 100.0}
                for k, r in enumerate(rets)]

    def test_deterministe_avec_la_graine(self):
        pnls = self._pnls([1.0 + 0.1 * (k % 7) for k in range(200)])
        a = block_bootstrap(pnls, cost_pct=0.28, seed=42)
        b = block_bootstrap(pnls, cost_pct=0.28, seed=42)
        self.assertEqual(a["mean_ci95"], b["mean_ci95"])
        self.assertEqual(a["p_mean_gt0"], b["p_mean_gt0"])

    def test_ci95_contient_la_moyenne_et_p0_sur_edge_clair(self):
        """Un edge franc : P(mean > 0) = 1.0 et le CI95 autour de la
        moyenne — le CI95 ne doit pas toucher zéro."""
        pnls = self._pnls([1.0 + 0.3 * ((k * 7) % 11) for k in range(300)])
        bs = block_bootstrap(pnls, cost_pct=0.28, seed=42)
        self.assertEqual(bs["p_mean_gt0"], 1.0)
        point = float(np.mean([p["net"] / p["notional"] * 100
                               for p in pnls]))
        lo, hi = bs["mean_ci95"]
        self.assertLessEqual(lo, point + 0.2)
        self.assertGreaterEqual(hi, point - 0.2)
        self.assertGreater(lo, 0.0)        # l'edge franc ne touche pas 0

    def test_p_stress_utilise_le_cout_majore(self):
        """P(stress > 0) retire 0,5 × cost par trade — un edge de 0,15 %
        avec cost 0,28 % passe en base mais meurt au stress ×1,5."""
        rng = np.random.default_rng(11)
        pnls = self._pnls(rng.normal(0.10, 0.02, 300).tolist())
        bs = block_bootstrap(pnls, cost_pct=0.28, seed=42)
        self.assertEqual(bs["p_mean_gt0"], 1.0)     # base : +0.10 % franc
        self.assertLessEqual(bs["p_stress_gt0"], 0.05)  # stress : −0.04 %


class TestWalletEndToEnd(unittest.TestCase):
    def test_le_wallet_mtm_publie_tout(self):
        w = run_wallet_mtm([_ev(t=0, ret=-2.0)], _marks(),
                           capital=100.0, cap_pct=1.0, lev=1.0)
        for k in ("cagr_pct", "sortino", "profit_factor", "solde_sans_top1",
                  "solde_sans_top5", "solde_sans_top10", "trade_pnls",
                  "years"):
            self.assertIn(k, w)
        eff = effective_sample_size(w["trade_pnls"])
        self.assertEqual(eff["n_raw"], 1)
        bs = block_bootstrap(w["trade_pnls"], cost_pct=0.28)
        self.assertEqual(bs["iters"], 0)   # 1 trade : pas assez pour bootstrapper


if __name__ == "__main__":
    unittest.main()
