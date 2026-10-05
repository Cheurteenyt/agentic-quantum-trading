"""Tests du research bridge (Research OS PR 7) — les contrats d'outils JSON.

Chaque outil retourne {"ok": true, ...} ou {"ok": false, "code", "message"} —
jamais de traceback brut (brief V3 §58). Le contexte discovery est aveugle
à la validation (fuite B).

    python tests/test_research_bridge.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_bridge as rb  # noqa: E402


class TestContracts(unittest.TestCase):
    def test_context_discovery_est_blindle(self):
        """Fuite B : le contexte discovery ne doit contenir NI verdict de
        confirmation NI score OOS ni le détail des essais."""
        out = json.loads(rb.tool_context("discovery", None))
        self.assertTrue(out["ok"])
        ctx = out["context"]
        for banned in ("CONFIRMED", "REJECTED", "sharpe_oos", "mean"):
            self.assertNotIn(banned, ctx)

    def test_context_confirmation_sans_id_est_refuse(self):
        out = json.loads(rb.tool_context("confirmation", None))
        self.assertFalse(out["ok"])
        self.assertEqual(out["code"], "MISSING_ID")

    def test_mauvais_mode_refuse(self):
        out = json.loads(rb.tool_context("hologramme", None))
        self.assertFalse(out["ok"])
        self.assertEqual(out["code"], "BAD_MODE")

    def test_get_introuvable(self):
        out = json.loads(rb.tool_get("EXP-INEXISTANT"))
        self.assertFalse(out["ok"])
        self.assertEqual(out["code"], "NOT_FOUND")

    def test_verify_retourne_un_verdict(self):
        out = json.loads(rb.tool_verify("F-001"))
        self.assertTrue(out["ok"])
        self.assertIn(out["verdict"], ("SUPPORTED", "CONTRADICTED",
                                       "UNVERIFIED", "OK SUPPORTED"))


if __name__ == "__main__":
    unittest.main()
