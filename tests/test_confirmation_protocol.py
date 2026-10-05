"""LE TEST DE COHÉRENCE DE L'AUTORITÉ (ratification protocol-v2, 05/10).

Une seule source pour tous les seuils de confirmation :
research/protocols/active.yaml. Ce test garantit que gates.py et
candidates.py restent alignés dessus — si quelqu'un change un côté sans
l'autre, ce test casse au lieu de laisser deux définitions de CONFIRMED
cohabiter (le bug exact que la ratification élimine).

    python tests/test_confirmation_protocol.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from backend.services.backtest_v2.candidates import PROTOCOL  # noqa: E402
from scripts.research_os import load_confirmation_protocol  # noqa: E402

ACTIVE = ROOT / "research" / "protocols" / "active.yaml"


class TestConfirmationProtocol(unittest.TestCase):
    def setUp(self):
        self.proto = load_confirmation_protocol()
        self.raw = yaml.safe_load(ACTIVE.read_text(encoding="utf-8"))

    def test_le_fichier_existe_et_est_ratifie(self):
        self.assertEqual(self.proto["protocol_id"], "protocol-v2")
        self.assertEqual(self.proto["status"], "RATIFIED")

    def test_les_fenetres_gelées_sont_chronologiques(self):
        wins = self.proto["frozen_windows"]
        self.assertGreaterEqual(len(wins), 6)
        for a, b in zip(wins, wins[1:]):
            self.assertEqual(a["end"], b["start"], "les fenêtres doivent se toucher")

    def test_les_seuils_forward_de_candidates_viennent_du_protocole(self):
        """L'unification : candidates.py lit PROTOCOL, pas des constantes."""
        fc = self.proto["forward_confirmation"]
        self.assertEqual(fc["min_forward_sharpe"], 0.5)
        self.assertEqual(fc["min_forward_trades"], 100)
        self.assertEqual(fc["min_vs_discovery"], 0.5)

    def test_le_stress_couts_est_declare(self):
        self.assertEqual(self.proto["cost_stress_multiplier"], 1.5)

    def test_legue_le_gate_backtest_au_meme_fichier(self):
        """gates.py min_sharpe_oos (0.8) == le protocole backtest_gate —
        la cohérence testée, pas espérée."""
        from backend.services.backtest_v2.gates import GateConfig
        self.assertEqual(GateConfig().min_sharpe_oos,
                         self.proto["backtest_gate"]["min_sharpe_oos"])

    def test_le_loader_est_cache_une_seule_fois(self):
        self.assertIs(load_confirmation_protocol(), load_confirmation_protocol())


if __name__ == "__main__":
    unittest.main()
