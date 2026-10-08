"""C4 (bug-hunter ronde 4) — un DD INCONNU (marks partiels) est NOMMÉ dans
le rapport wallet, jamais imprimé comme « nan % » silencieux.

Le producteur (wallet_per_window, FIX v19) met dd_status=UNKNOWN et
max_dd_pct=NaN quand un symbole a des marks insuffisants. Le consommateur
(window_dd_breach) filtrait par comparaison brute : nan > plafond = False
→ la fenêtre disparaissait du rapport officiel, en contradiction avec le
gate fail-closed du confirm (FIX v14 : un DD inconnu n'est plus un PASS).

    python tests/test_c4_dd_unknown_rapport.py
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import portfolio_runner as pr  # noqa: E402

NAN = float("nan")


def _w(per_window, breach, unknown):
    return {
        "view": "validation", "wallet": {
            "capital": 100.0, "cap_pct": 10.0, "lev": 10, "trades": 3,
            "n_events": 4, "solde": 103.0, "roi_pct": 3.0,
            "max_dd_pct": 5.0, "liqs": 0, "wr_pct": 66.7, "months_neg": 0,
            "months_total": 2, "worst_month": 1.0, "best_month": 2.0,
            "ret_dd": 0.6, "fees": 0.4, "funding_net": 0.0},
        "n_events": 4, "frozen_src": "discovery_artifact",
        "per_window": per_window, "max_window_loss_pct": 15.0,
        "window_dd_breach": breach, "window_dd_unknown": unknown,
    }


class TestDdUnknownRapport(unittest.TestCase):
    def test_fenetre_inconnue_nomme_et_non_nan(self):
        # une fenêtre UNKNOWN : « nan % » interdit, bandeau DD INCONNU requis
        w = _w({"2025-01": {"max_dd_pct": NAN, "dd_status": "UNKNOWN"},
                "2025-02": {"max_dd_pct": 8.0, "dd_status": "MTM"}},
               [], ["2025-01"])
        bloc = pr.wallet_report_block(w)
        self.assertNotIn("nan", bloc.lower(),
                         "« nan % » n'est pas un chiffre : le rapport doit "
                         "écrire INCONNU")
        self.assertIn("INCONNU (marks partiels)", bloc)
        self.assertIn("2025-01", bloc)
        self.assertIn("⚠️ DD INCONNU", bloc)
        self.assertNotIn("DÉPASSEMENT", bloc)

    def test_breach_reel_toujours_signale(self):
        # régression : le dépassement mesuré garde son bandeau
        w = _w({"2025-01": {"max_dd_pct": 22.0, "dd_status": "MTM"}},
               ["2025-01"], [])
        bloc = pr.wallet_report_block(w)
        self.assertIn("22.00 %", bloc)
        self.assertIn("DÉPASSEMENT plafond DD", bloc)
        self.assertNotIn("DD INCONNU", bloc)

    def test_production_window_dd_unknown(self):
        # la couche out de wallet_for_run sépare breach (mesuré) et
        # unknown (inconnu) : nan > plafond est False, mais UNKNOWN est
        # nommé. Test au niveau du MÊME filtre que wallet_for_run, avec
        # les deux statuts du producteur.
        per_window = {"2025-01": {"max_dd_pct": NAN, "dd_status": "UNKNOWN"},
                      "2025-02": {"max_dd_pct": 8.0, "dd_status": "MTM"},
                      "2025-03": {"max_dd_pct": 22.0, "dd_status": "MTM"}}
        plafond = 15.0
        breach = [k for k, w_ in per_window.items()
                  if w_["max_dd_pct"] > plafond]
        unknown = [k for k, w_ in per_window.items()
                   if w_.get("dd_status") == "UNKNOWN"]
        self.assertEqual(breach, ["2025-03"],
                         "nan n'est pas un dépassement mesuré")
        self.assertEqual(unknown, ["2025-01"],
                         "la fenêtre UNKNOWN est nommée explicitement")

    def test_nan_comparaison_est_le_bug(self):
        # l'oracle du bug : la comparaison brute rendait l'UNKNOWN invisible
        self.assertFalse(NAN > 15.0, "nan > plafond est False : c'est le "
                                     "fail-open que le fix neutralise en "
                                     "nommant la fenêtre")
        self.assertTrue(math.isnan(NAN))


if __name__ == "__main__":
    unittest.main(verbosity=2)
