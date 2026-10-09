#!/usr/bin/env python3
"""Ronde 11 — knum : UNE conversion pour les nombres abrégés de l'UI fomo.

Après le fix partiel #244 (K/M/B dans le harvester seul), trois angles
morts restaient et cassaient le contrat « rang entier, chaîne monotone » :

  1. fomo_top_traders_miner.knum = float(s.replace(",", "")) : ValueError
     sur tout suffixe — la quantité POS abrégée « 1.2K » tuait la ligne.
  2. ancres [KMB] sans T : « 2.3T » cassait l'ancre de ligne entière.
  3. formats réels d'UI échappés : « 1.234,5 » (point de milliers fr —
     donnait 1.2345, erreur x1000 silencieuse), « 1 234,5 » (NBSP),
     « -1.2K » (moins U+2212), et le podium/liste n'acceptaient AUCUN
     perdant (le '+' du PnL était hardcodé dans LB_RE/POD_RE).

Tests hermétiques : aucune base, aucun réseau.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fomo_knum import knum  # noqa: E402
from scripts.fomo_leaderboard_harvester import (  # noqa: E402
    parse_leaderboard_text)


class TestKnum(unittest.TestCase):
    def test_contrats_de_base(self):
        self.assertEqual(knum("1,234.5"), 1234.5)
        self.assertEqual(knum("1.2K"), 1200.0)
        self.assertEqual(knum("1.2M"), 1.2e6)
        self.assertEqual(knum("1.2B"), 1.2e9)
        self.assertEqual(knum("1234"), 1234.0)
        self.assertIsNone(knum(""))
        self.assertIsNone(knum("N/A"))
        self.assertIsNone(knum(None))

    def test_trillion(self):
        """2.3T : aucun suffixe T nulle part avant la ronde 11."""
        self.assertEqual(knum("2.3T"), 2.3e12)

    def test_moins_typographique(self):
        """Le moins U+2212 de l'UI (pas le '-' ASCII)."""
        self.assertEqual(knum("\u22121.2K"), -1200.0)
        self.assertEqual(knum("-1.2K"), -1200.0)

    def test_format_fr_point_de_milliers(self):
        """« 1.234,5 » : l'ancien knum donnait 1.2345 (erreur x1000)."""
        self.assertEqual(knum("1.234,5"), 1234.5)

    def test_format_fr_espace_milliers(self):
        self.assertEqual(knum("1\u00a0234,5"), 1234.5)   # NBSP
        self.assertEqual(knum("1 234,5"), 1234.5)        # espace simple
        self.assertEqual(knum("1\u202f234,5"), 1234.5)   # espace fine

    def test_us_classique(self):
        self.assertEqual(knum("1,234"), 1234.0)
        self.assertEqual(knum("12,5"), 12.5)             # décimale fr

    def test_jamais_d_exception(self):
        """Une ligne UI étrange ne doit pas tuer un harvest."""
        for weird in ("1.2.3.4", "K", "---", "1.2KK", "1..2"):
            try:
                knum(weird)
            except Exception as e:   # noqa: BLE001
                self.fail(f"knum({weird!r}) a levé {e!r}")


_LB = (
    # le podium all-time (NON numéroté, POD_RE)
    "\nDave\n@dave\n+\n$2.3T\n99+\n"
    "\nAlice\n@alice\n+\n$1.2M\n50+\n"
    "\nBob\n@bob\n+\n$900,000\n40+\n"
    # la liste numérotée (LB_RE, dès le rang 4)
    "\n4.\nEve\n@eve\n+\n$500,000\n30+\n"
    "\n5.\nFrank\n@frank\n+\n$100K\n20+\n"
    "\n6.\nCarol\n@carol\n-\n$1.2K\n10+\n")


class TestLeaderboardSignesEtT(unittest.TestCase):
    def test_perdant_negatif_et_trillion(self):
        """Carol (-$1.2K) était invisible (le '+' hardcodé) ; 2.3T aussi."""
        rows = parse_leaderboard_text(_LB)
        by_handle = {h: (r, p) for r, _n, h, p, _t in rows}
        # le perdant est parsé NÉGATIF (pas +1200)
        self.assertIn("carol", by_handle)
        self.assertEqual(by_handle["carol"][1], -1200.0)
        # le trillion (suffixe T) : 2.3T
        self.assertIn("dave", by_handle)
        self.assertEqual(by_handle["dave"][1], 2.3e12)

    def test_gagnants_inchanges_et_ordre(self):
        """Régression : le '+' ASCII et K/M/B de #244 restent corrects."""
        rows = parse_leaderboard_text(_LB)
        # rows = (rank, name, handle, pnl, trades)
        # le podium trié desc : Dave (2.3T), Alice (1.2M), Bob (900K)
        self.assertEqual([h for _, _, h, _p, _t in rows[:3]],
                         ["dave", "alice", "bob"])
        self.assertEqual(rows[0][3], 2.3e12)
        self.assertEqual(rows[1][3], 1.2e6)
        self.assertEqual(rows[2][3], 900_000.0)
        # la liste ALL suit, chaîne monotone : Eve, Frank, Carol
        self.assertEqual([h for _, _, h, _p, _t in rows[3:]],
                         ["eve", "frank", "carol"])
        self.assertEqual([r for r, _, _, _, _t in rows[3:]], [4, 5, 6])


if __name__ == "__main__":
    unittest.main()
