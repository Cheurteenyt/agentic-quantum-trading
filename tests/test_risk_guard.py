"""Tests RiskGuard — contrats de retour et limites strictes.

Preuves des bugs fixes dans agent/risk_guard.py :
  1. deactivate_kill_switch etait annote -> bool mais retournait un dict.
  2. can_trade acceptait current_position == max_position_size (strict >).

    python tests/test_risk_guard.py
    python scripts/run_tests.py risk_guard --fast
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.risk_guard import RiskGuard  # noqa: E402


class KillSwitchContractTest(unittest.TestCase):
    def test_default_kill_switch_on(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KILL_SWITCH_ENABLED", None)
            g = RiskGuard()
            self.assertTrue(g.kill_switch_enabled)
            r = g.can_trade()
            self.assertFalse(r["allowed"])
            self.assertIn("Kill switch", r["reason"])

    def test_deactivate_returns_dict_not_bool(self):
        g = RiskGuard()
        out = g.deactivate_kill_switch()
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("status"), "Kill switch deactivated")
        self.assertFalse(g.kill_switch_enabled)

    def test_activate_returns_dict(self):
        g = RiskGuard()
        g.deactivate_kill_switch()
        out = g.activate_kill_switch()
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("status"), "Kill switch activated")
        self.assertTrue(g.kill_switch_enabled)


class PositionLimitTest(unittest.TestCase):
    def setUp(self):
        self.g = RiskGuard()
        self.g.kill_switch_enabled = False
        self.g.max_position_size = 0.02
        self.g.max_daily_loss = 0.05
        self.g.max_open_positions = 3

    def test_position_at_max_is_blocked(self):
        """Regression: was `>` only, so == max still allowed."""
        r = self.g.can_trade(current_position=0.02)
        self.assertFalse(r["allowed"])
        self.assertIn("Position size", r["reason"])

    def test_position_below_max_is_allowed(self):
        r = self.g.can_trade(current_position=0.019)
        self.assertTrue(r["allowed"])

    def test_open_positions_at_max_is_blocked(self):
        r = self.g.can_trade(open_positions=3)
        self.assertFalse(r["allowed"])
        self.assertIn("Open positions", r["reason"])

    def test_daily_loss_breach(self):
        r = self.g.can_trade(daily_pnl=-0.06)
        self.assertFalse(r["allowed"])
        self.assertIn("Daily loss", r["reason"])


class StatusTest(unittest.TestCase):
    def test_get_status_keys(self):
        g = RiskGuard()
        s = g.get_status()
        for k in (
            "kill_switch_enabled",
            "max_position_size",
            "max_daily_loss",
            "max_open_positions",
        ):
            self.assertIn(k, s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
