"""FIX lot1 — F5 (levier machine), F9 (GLMClient), F10 (reset types),
F13 (run_stack fallback).

Chaque test reproduit d'abord le bug prouvé par l'audit, puis verrouille
le comportement corrigé.

    python tests/test_lot1_agent_stack.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.client import GLMClient  # noqa: E402
from agent.state_manager import StateManager  # noqa: E402
from scripts.stacked_portfolio import run_stack  # noqa: E402
from scripts.the_machine import MAINT_MAJORS, levier_majors_safe  # noqa: E402


class TestLevierMajorsSafe(unittest.TestCase):
    """F5 : the_machine forçait e["lev"] = 10 même quand lev_safe < 10.

    RÉÉCRIT par F-038 : le dénominateur est le maintMarginPercent réel des
    majeures (2,5 %), plus 0,5. L'ancien test encodait l'ère codifiée — il
    affirmait 10x à MAE 7,84 % alors que la ligne de mort réelle à 10x est
    7,5 %, donc le MAE observée DÉPASSait la borne et la règle 0-liq du
    README était infirmée par elle-même. Le test encodait le bug.
    """

    def test_le_cap_ne_bine_pas_sur_un_mae_sain(self):
        # MAE 1 % → lev_safe très au-dessus du cap de 10 → le cap bind
        self.assertEqual(levier_majors_safe(1.0), 10.0)
        # l'ère observée (7,84 %) donne 9,23x : SOUS le cap, la règle bite
        self.assertAlmostEqual(levier_majors_safe(7.84), 100 / (7.84 + 3.0))
        self.assertLess(levier_majors_safe(7.84), 10.0)

    def test_le_cap_plafonne_sur_un_mae_chaud(self):
        # dénominateur = MAE + maint (2,5) + sécurité (0,5)
        self.assertAlmostEqual(levier_majors_safe(15.0), 100 / 18.0)
        self.assertAlmostEqual(levier_majors_safe(25.0), 100 / 28.0)

    def test_le_cap_est_surchargeable(self):
        self.assertEqual(levier_majors_safe(1.0, cap=4.0), 4.0)

    def test_la_regle_0_liq_tient_pour_le_mae_observe(self):
        """L'invariant que le README AFFIRMAIT et que le dur 0,5 violait.

        Pour tout MAE, le levier rendu doit donner un mouvement de mort
        STRICTEMENT supérieur au MAE : sinon le trade se fait tuer.
        """
        for mae in (1.0, 3.5, 7.84, 9.5, 15.0, 25.0, 60.0):
            lev = levier_majors_safe(mae)
            mort = 100.0 / lev - MAINT_MAJORS
            self.assertGreater(
                mort, mae,
                f"MAE {mae} % liquidé à {mort:.2f} % : la règle 0-liq est "
                f"violée (lev {lev:.2f}x)")


class _BoomSession:
    def post(self, *a, **k):
        raise ConnectionError("boom réseau")


class _OkSession:
    def post(self, *a, **k):
        class _R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}],
                        "usage": {"total_tokens": 1}}
        return _R()


def _bare_client(session):
    """GLMClient sans __init__ (pas de DB, pas d'env)."""
    c = GLMClient.__new__(GLMClient)
    c.base_url = "http://localhost"
    c.api_key = "test-key"
    c.session = session
    return c


class TestGLMClientErrors(unittest.TestCase):
    """F9 : le except appelait StateManager.log_error() inexistant —
    l'AttributeError masquait la vraie erreur API."""

    def test_erreur_reseau_renvoie_none_sans_attributeerror(self):
        c = _bare_client(_BoomSession())
        with self.assertLogs("agent.client", level="ERROR"):
            self.assertIsNone(c.call([{"role": "user", "content": "x"}]))

    def test_chemin_nominal_toujours_intact(self):
        c = _bare_client(_OkSession())
        out = c.call([{"role": "user", "content": "x"}])
        self.assertEqual(out["content"], "ok")


class TestResetDailyStats(unittest.TestCase):
    """F10 : reset écrasait daily_pnl/daily_trades en '{}' — le contrat
    float/int cassait (risk_guard compare daily_pnl < -max_daily_loss)."""

    def test_round_trip_reset_conserve_les_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            sm = StateManager(db_path=str(Path(tmp) / "state.db"))
            sm.save_risk_state({"daily_pnl": -0.06, "daily_trades": 12})
            sm.reset_daily_stats()
            st = sm.load_risk_state()
            self.assertIsInstance(st["daily_pnl"], float)
            self.assertIsInstance(st["daily_trades"], int)
            self.assertEqual(st["daily_pnl"], 0.0)
            self.assertEqual(st["daily_trades"], 0)


class _Event(dict):
    """Un event minimal pour run_stack (ts_ms en ns, convention du repo)."""
    def __init__(self, ts_ns=0):
        super().__init__(strategy="s", ts_ms=ts_ns, lev=1.0,
                         mae_adverse=1.0, fee_rt_bps=28.0, sym="XUSDT",
                         hold_h=24.0, price_ret_short=5.0)


class TestRunStackApi(unittest.TestCase):
    """F13 : size_fn=None tombait sur `sz = size` — NameError latent."""

    def test_size_fn_none_est_refuse_tot_et_clairement(self):
        with self.assertRaises(ValueError):
            run_stack([_Event()], 100.0, None, {})

    def test_chemin_nominal_unchanged(self):
        r = run_stack([_Event()], 100.0, lambda e: 0.1, {})
        self.assertEqual(r["n"], 1)
        self.assertGreater(r["balance"], 100.0)

    def test_sizer_2_args_recoit_l_etat_du_wallet(self):
        seen = {}
        r = run_stack([_Event()], 100.0,
                      lambda e, st: (seen.update(st), 0.1)[1], {})
        self.assertEqual(r["n"], 1)
        self.assertIn("balance", seen)


if __name__ == "__main__":
    unittest.main()
