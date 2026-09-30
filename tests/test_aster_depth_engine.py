#!/usr/bin/env python3
"""Tests du moteur diff-depth aster_depth_engine (docs/24, phase d'ombre) :
application des diffs (qty 0 = suppression), chaînage pu, trou -> resync,
fenêtre de rattachement au snapshot, compat binning avec depth_collector,
comparateur d'acceptation, répartition des connexions."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import aster_depth_engine as de
from depth_collector import SYMBOLS

statistics_median = __import__("statistics").median


def diff(u, pu, bids=(), asks=(), U=None):
    return {"e": "depthUpdate", "s": "BTCUSDT", "U": U if U is not None else u,
            "u": u, "pu": pu, "b": [list(x) for x in bids], "a": [list(x) for x in asks]}


def snap_state(last_update_id=100):
    st = de.BookState("BTCUSDT")
    st.bids = {"100.0": 1.0, "99.0": 2.0}
    st.asks = {"101.0": 1.5, "102.0": 2.5}
    st.last_u = last_update_id
    st.synced = True
    return st


class TestApplyLevels(unittest.TestCase):
    def test_qty_zero_supprime(self):
        st = snap_state()
        de.apply_levels(st, diff(101, 100, bids=[("100.0", "0")],
                                 asks=[("101.0", "0"), ("103.0", "4")]))
        self.assertNotIn("100.0", st.bids)
        self.assertNotIn("101.0", st.asks)          # suppression
        self.assertEqual(st.asks["103.0"], 4.0)     # ajout
        self.assertEqual(st.bids["99.0"], 2.0)      # intact

    def test_qty_remplace(self):
        st = snap_state()
        de.apply_levels(st, diff(101, 100, bids=[("99.0", "7.5")]))
        self.assertEqual(st.bids["99.0"], 7.5)


class TestApplyLive(unittest.TestCase):
    def test_chaine_ok(self):
        st = snap_state(last_update_id=100)
        de.apply_live(st, diff(105, 100))
        self.assertEqual(st.last_u, 105)

    def test_vieux_ignore(self):
        st = snap_state(last_update_id=100)
        de.apply_live(st, diff(100, 99))
        self.assertEqual(st.last_u, 100)

    def test_trou_leve(self):
        st = snap_state(last_update_id=100)
        with self.assertRaises(de.GapError):
            de.apply_live(st, diff(110, 99))  # pu != last_u

    def test_anche_straddle_apres_snapshot(self):
        """1er diff post-resync : pu < lastUpdateId mais U<=last_u+1<=u -> OK."""
        st = snap_state(last_update_id=100)
        st.awaiting_anchor = True
        de.apply_live(st, diff(103, 97, U=95, bids=[("99.0", "5")]))
        self.assertEqual(st.last_u, 103)
        self.assertFalse(st.awaiting_anchor)
        de.apply_live(st, diff(106, 103))  # ensuite chaînage normal
        self.assertEqual(st.last_u, 106)

    def test_ancre_compteur_global_live(self):
        """Cas réel Aster : U très au-dessus de last_u -> ancre acceptée."""
        st = snap_state(last_update_id=100)
        st.awaiting_anchor = True
        de.apply_live(st, diff(200000, 199000, U=199500))
        self.assertEqual(st.last_u, 200000)
        self.assertFalse(st.awaiting_anchor)
        de.apply_live(st, diff(200004, 200000))  # régime : chaînage normal
        self.assertEqual(st.last_u, 200004)

    def test_vieux_pendant_ancre_ignore(self):
        st = snap_state(last_update_id=100)
        st.awaiting_anchor = True
        de.apply_live(st, diff(98, 97, U=90))  # u <= last_u : jeté, ancre gardée
        self.assertTrue(st.awaiting_anchor)


class TestDrainBuffer(unittest.TestCase):
    def test_rattachement_ok(self):
        st = snap_state(last_update_id=100)
        st.buffer = deque_of([diff(98, 97),            # u <= lastUpdateId : jeté
                              diff(103, 97, U=95),     # 1er gardé : ancre Aster
                              diff(107, 103)])
        self.assertTrue(de.drain_buffer(st))
        self.assertEqual(st.last_u, 107)

    def test_ancre_compteur_global(self):
        """Cas réel Aster (30/09) : le 1er diff post-snapshot a U très supérieur
        à lastUpdateId (compteur global non contigu) -> appliqué quand même."""
        st = snap_state(last_update_id=100)
        st.buffer = deque_of([diff(200000, 199000, U=199500)])
        self.assertTrue(de.drain_buffer(st))
        self.assertEqual(st.last_u, 200000)

    def test_cassure_pu_dans_buffer(self):
        st = snap_state(last_update_id=100)
        st.buffer = deque_of([diff(103, 97, U=95), diff(107, 104)])  # pu!=103
        self.assertFalse(de.drain_buffer(st))


def deque_of(evs):
    from collections import deque
    return deque(evs, maxlen=400)


class TestCompareBook(unittest.TestCase):
    def fresh_snap(self, bids, asks):
        return {"lastUpdateId": 1, "bids": [[p, str(q)] for p, q in bids],
                "asks": [[p, str(q)] for p, q in asks]}

    def test_match_parfait(self):
        st = snap_state()
        row = de.compare_book(st, self.fresh_snap(
            [("100.0", 1.0), ("99.0", 2.0)], [("101.0", 1.5), ("102.0", 2.5)]))
        self.assertEqual(row["verdict"], "MATCH")

    def test_carnet_stale(self):
        st = snap_state()
        st.bids = {"50.0": 1.0}  # carnet figé loin du marché
        row = de.compare_book(st, self.fresh_snap(
            [("100.0", 1.0), ("99.0", 2.0)], [("101.0", 1.5), ("102.0", 2.5)]))
        self.assertEqual(row["verdict"], "MISMATCH")

    def test_non_synchro(self):
        st = snap_state()
        st.synced = False
        row = de.compare_book(st, self.fresh_snap(
            [("100.0", 1.0)], [("101.0", 1.5)]))
        self.assertEqual(row["verdict"], "MISMATCH")

    def test_mid_hors_tolerance(self):
        st = snap_state()
        st.asks = {"110.0": 1.5}  # mid décalé de ~4 %
        row = de.compare_book(st, self.fresh_snap(
            [("100.0", 1.0), ("99.0", 2.0)], [("101.0", 1.5), ("102.0", 2.5)]))
        self.assertEqual(row["verdict"], "MISMATCH")

    def test_qty_x100_bug_unite(self):
        """Prix présents mais qty x100 = bug d'unité -> MISMATCH (médiane ratio)."""
        st = snap_state()
        st.bids = {"100.0": 100.0, "99.0": 200.0}
        st.asks = {"101.0": 150.0, "102.0": 250.0}
        row = de.compare_book(st, self.fresh_snap(
            [("100.0", 1.0), ("99.0", 2.0)], [("101.0", 1.5), ("102.0", 2.5)]))
        self.assertEqual(row["verdict"], "MISMATCH")

    def test_side_stats_churn(self):
        """_side_stats : présence à ±1 niveau vs strict qty, médiane ratio."""
        book = {"100.0": 1.0, "99.92": 5.0}
        present, strict, med = de._side_stats(
            [(100.0, 1.0), (99.95, 4.0), (99.9, 3.0)], book, 100.0)
        self.assertEqual(present, 3)   # tous à ±1.5 tick (tick médian = 0.05)
        self.assertEqual(strict, 2)    # 1.0 exact ; 4.0->5.0 (25%) ; 3.0->5.0 (67%) non
        self.assertAlmostEqual(med, statistics_median([1.0, 5.0 / 4.0, 5.0 / 3.0]))


class TestBinningCompat(unittest.TestCase):
    def test_memes_bins_que_depth_collector(self):
        levels = [["100.0", "1.0"], ["100.01", "2.0"], ["99.99", "3.0"]]
        grid = 100.0 * de.BIN_FRAC
        a = de.bin_levels(levels, grid)
        from depth_collector import bin_levels as dc_bin
        self.assertEqual(a, dc_bin(levels, grid))


class TestGroups(unittest.TestCase):
    def test_repartition_3x5_sans_trou(self):
        eng = de.Engine.__new__(de.Engine)  # sans __init__ (pas de DB)
        eng.states = {}
        eng.groups = [SYMBOLS[i::de.N_CONNS] for i in range(de.N_CONNS)]
        self.assertEqual(len(eng.groups), 3)
        self.assertTrue(all(len(g) == 5 for g in eng.groups))
        flat = sorted(s for g in eng.groups for s in g)
        self.assertEqual(flat, sorted(SYMBOLS))


if __name__ == "__main__":
    unittest.main()
