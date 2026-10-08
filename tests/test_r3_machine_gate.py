#!/usr/bin/env python3
"""FIX R3 (C-B1) — le gate AL de the_machine tradait le tiers le PLUS risqué.

Histoire du bug :
    pré-167 (6760a16~1, l.147-148) :
        gated = [e for e in events
                 if not (np.isfinite(e["al_score"]) and e["al_score"] >= q66)]
        → on TRADE le tiers BAS (sûr).
    réécriture PR-167 (expanding) :
        if np.isfinite(_s) and _s >= _q66: gated.append(e)
        → on TRADE le tiers HAUT (risqué) : sens renversé.

La sémantique du score est non négociable : al_score HAUT = PLUS risqué
(RISK_UP : mean(vals <= v) ; RISK_DOWN : mean(vals >= v) — anti_liq, PR-172).
Toute la chaîne écarte le haut : size_by_policy (stacked_portfolio),
portfolio_sim l.254-256, full_arsenal_2 l.265-267.
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.the_machine import gate_expanding  # noqa: E402


def ref_pre167(events, min_hist=30):
    """La référence pré-167 mot pour mot (le comportement attendu)."""
    gated, hist, last = [], [], float("nan")
    for e in events:
        s = e.get("al_score", float("nan"))
        if len(hist) >= min_hist:
            q66 = float(np.nanquantile(hist, 2 / 3))
            last = q66
            if not (np.isfinite(s) and s >= q66):
                gated.append(e)
        elif np.isfinite(s):
            gated.append(e)
        if np.isfinite(s):
            hist.append(s)
    return gated, last


class TestGateExpanding(unittest.TestCase):
    def _events(self, n=300, seed=42):
        import random
        rnd = random.Random(seed)
        return [{"ts_ms": i,
                 "al_score": rnd.random() if i % 17 else float("nan")}
                for i in range(n)]

    def test_parite_bit_a_bit_avec_la_semantique_pre167(self):
        ev = self._events()
        got = gate_expanding(ev)
        want = ref_pre167(ev)
        self.assertEqual([e["ts_ms"] for e in got[0]],
                         [e["ts_ms"] for e in want[0]])
        self.assertTrue(
            (got[1] == want[1]) or (got[1] != got[1] and want[1] != want[1]))

    def test_le_gate_trades_le_tiers_bas_pas_le_haut(self):
        """Après le socle : aucun event au-dessus du q66 COURANT ne passe."""
        ev = self._events(400)
        gated, _ = gate_expanding(ev)
        hist = [e["al_score"] for e in sorted(ev, key=lambda x: x["ts_ms"])
                if np.isfinite(e.get("al_score", float("nan")))]
        # rejeu : pour chaque gardé post-socle, il devait être SOUS le q66
        # courant du moment (on rejoue la référence pour récupérer les q66)
        hist_roll, passed = [], True
        kept = {e["ts_ms"] for e in gated}
        for e in sorted(ev, key=lambda x: x["ts_ms"]):
            s = e.get("al_score", float("nan"))
            if len(hist_roll) >= 30:
                q66 = float(np.nanquantile(hist_roll, 2 / 3))
                if e["ts_ms"] in kept and np.isfinite(s) and s >= q66:
                    passed = False
            if np.isfinite(s):
                hist_roll.append(s)
        self.assertTrue(passed, "un event au-dessus du q66 courant a été gardé")

    def test_socle_30_toujours_trades(self):
        ev = self._events(60)
        gated, _ = gate_expanding(ev)
        kept = {e["ts_ms"] for e in gated}
        for i in range(30):
            if i % 17 == 0:            # i=0, i=17 : al_score NaN → non tradés
                self.assertNotIn(i, kept)
                continue
            self.assertIn(i, kept, f"event du socle {i} rejeté")

    def test_pas_de_gate_avant_30_scores(self):
        """Moins de 30 scores finis : le gate ne s'active jamais."""
        ev = self._events(20)          # i=0 et i=17 sont NaN → 18 finis < 30
        gated, last_q66 = gate_expanding(ev)
        self.assertEqual(len(gated), 18)
        self.assertTrue(all(np.isfinite(e["al_score"]) for e in gated))
        self.assertTrue(last_q66 != last_q66,
                        "q66 calculé alors que le socle 30 n'est pas atteint")

    def test_nan_est_trades_comme_avant(self):
        ev = [{"ts_ms": i,
               "al_score": float("nan") if i >= 30 else 0.1}
              for i in range(60)]
        gated, _ = gate_expanding(ev)
        kept = {e["ts_ms"] for e in gated}
        self.assertIn(30, kept, "NaN post-socle rejeté (comportement PR-167)")
        self.assertIn(45, kept)

    def test_ordre_temporel_contracte(self):
        ev = self._events(120)
        ev.reverse()
        gated, _ = gate_expanding(ev)
        ts = [e["ts_ms"] for e in gated]
        self.assertEqual(ts, sorted(ts), "sortie non triée temporellement")

    def test_le_fix_garde_le_tiers_sur_pas_le_tiers_risque(self):
        """Discriminateur de sens : scores uniformes → le gate post-socle
        rejette ~1/3 (s >= q66 ≈ 0,67) et garde ~2/3. L'ancien code inversé
        gardait ~1/3 (fraction ≈ 0,40), hors de l'intervalle ci-dessous."""
        ev = self._events(600, seed=7)
        gated, _ = gate_expanding(ev)
        n_finite = sum(1 for e in ev
                       if np.isfinite(e.get("al_score", float("nan"))))
        frac = len(gated) / n_finite
        self.assertGreater(frac, 0.55,
                           "le gate rejette trop — sens peut-être encore inversé")
        self.assertLess(frac, 0.90, "le gate ne rejette presque plus rien")


if __name__ == "__main__":
    unittest.main()
