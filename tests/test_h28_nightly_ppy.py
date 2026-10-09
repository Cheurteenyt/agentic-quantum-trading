"""H-28 (audit ronde 4) — la correction de multiplicité nocturne était
calibrée sur 365 barres/an alors que les Sharpe OOS fournis sont annualisés
à la fréquence RÉELLE (8760 en 1h).

L'écart-type du Sharpe annualisé suit sqrt(ppy/n) : un ppy 365 au lieu de
8760 sous-estimait se d'un facteur sqrt(24) = 4,899, gonflait z, écrasait
les p-valeurs — le seuil effectif de Bonferroni tombait de Sharpe 19,2 à
3,93 sur une nuit typique : des lanes SANS edge passaient la correction.

    python tests/test_h28_nightly_ppy.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# fetch_klines importe `aster_rate` en top-level (flat, comme le lance le
# nightly depuis scripts/) — il faut scripts/ sur le path pour l'importer.
sys.path.insert(0, str(ROOT / "scripts"))

from scripts import nightly_campaign as nc  # noqa: E402
from backend.services.backtest_v2.gates import bars_per_year  # noqa: E402


class TestPpyForLanes(unittest.TestCase):
    def test_1h_donne_8760(self):
        ppy, note = nc._ppy_for_lanes(
            [{"sharpe_oos": 1.0, "interval": "1h"}])
        self.assertEqual(ppy, 8760)
        self.assertEqual(note, "")

    def test_frequence_reelle_par_intervalle(self):
        for itv, dt in nc._INTERVAL_MS.items():
            with self.subTest(interval=itv):
                ppy, _ = nc._ppy_for_lanes(
                    [{"sharpe_oos": 1.0, "interval": itv}])
                self.assertEqual(ppy, bars_per_year(dt))

    def test_campagne_mixte_prend_le_plus_strict(self):
        # 5m -> 105 120 barres/an ; 1h -> 8 760. Corriger une campagne
        # mixte à un ppy unique est une approximation : on prend le MAX
        # (le plus strict) et la note le dit.
        ppy, note = nc._ppy_for_lanes([
            {"sharpe_oos": 1.0, "interval": "1h"},
            {"sharpe_oos": 2.0, "interval": "5m"},
        ])
        self.assertEqual(ppy, max(bars_per_year(3_600_000),
                                  bars_per_year(300_000)))
        self.assertIn("mixte", note)
        self.assertIn("strict", note)

    def test_sans_survivant_aucun_ppy(self):
        ppy, note = nc._ppy_for_lanes([])
        self.assertIsNone(ppy)
        self.assertEqual(note, "")

    def test_lane_mesuree_sans_intervalle_refus(self):
        # fail-closed : sans intervalle, la correction retomberait
        # SILENCIEUSEMENT sur 365/an — le bug H-28 exactement
        with self.assertRaises(ValueError):
            nc._ppy_for_lanes([{"sharpe_oos": 5.0}])


class TestAuditFromCampaign(unittest.TestCase):
    """Le cas nocturne typique : 40 essais, 1 lane passe les gates avec
    Sharpe OOS 5,0 annualisé 8760 (1h), 432 obs OOS.

    ppy correct (8760)  : p = 0,133  > seuil 1,25e-3  -> REJETÉE
    ppy bugué (365)     : p = 2,7e-8 < seuil 1,25e-3  -> « candidate »
    """

    def test_lanes_sans_edge_rejetees_avec_ppy_reel(self):
        # 3 lanes mesurées (3 > expected=2 pour atteindre la branche
        # Bonferroni du verdict) : Sharpe 5,0 en 1h sur 432 obs donne
        # p = 0,133 — très loin du seuil 1,25e-3. Avec le ppy bugué (365),
        # p = 2,7e-8 : les TROIS étaient des « candidates ».
        out = nc.audit_from_campaign(
            {"tested": 40,
             "survivors": [{"sharpe_oos": 5.0, "interval": "1h"}] * 3},
            n_obs_per_lane=432)
        self.assertEqual(out["n_after_multiplicity"], 0)
        self.assertEqual(out["verdict"], "AUCUN SURVIVANT APRES CORRECTION")

    def test_vrai_edge_passe_encore(self):
        # Sharpe 15 en 1h sur 432 obs : p = 4,3e-4 < 1,25e-3 -> candidate.
        # Le fix resserre le filtre, il ne le ferme pas.
        out = nc.audit_from_campaign(
            {"tested": 40,
             "survivors": [{"sharpe_oos": 15.0, "interval": "1h"}] * 3},
            n_obs_per_lane=432)
        self.assertEqual(out["n_after_multiplicity"], 3)
        self.assertIn("CANDIDAT", out["verdict"])

    def test_sans_survivant_mesurable(self):
        out = nc.audit_from_campaign(
            {"tested": 40, "survivors": [{"sharpe_oos": None,
                                          "interval": "1h"}]},
            n_obs_per_lane=432)
        self.assertEqual(out["n_gate_survivors"], 0)
        self.assertEqual(out["verdict"], "AUCUNE LANE MESURABLE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
