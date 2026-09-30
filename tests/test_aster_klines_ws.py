#!/usr/bin/env python3
"""Tests du collecteur klines WS (aster_klines_ws) — parse kline x=true/x=false,
parade debit (plan de demotion), forme snapshot_id (docs/24, 2026-09-30)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import aster_klines_ws as kw


def kline_frame(closed: bool, sym: str = "BTCUSDT", itv: str = "15m",
                t: int = 1790725200000, o: str = "11794.15") -> str:
    k = {"t": t, "T": t + 899_999, "s": sym, "i": itv, "o": o,
         "c": "11800.00", "h": "11810.5", "l": "11790.0", "v": "123.45",
         "q": "1456789.0", "V": "60.5", "x": closed}
    return json.dumps({"stream": f"{sym.lower()}@kline_{itv}",
                       "data": {"e": "kline", "E": t + 100, "s": sym, "k": k}})


class TestParseKline(unittest.TestCase):
    def test_bougie_fermee(self):
        rows = kw.parse_frame(kline_frame(closed=True))
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertTrue(r["closed"])
        self.assertEqual(r["symbol"], "BTCUSDT")
        self.assertEqual(r["interval"], "15m")
        self.assertEqual(r["open_time"], 1790725200000)
        self.assertEqual(r["close_time"], 1790725200000 + 899_999)
        self.assertAlmostEqual(r["open"], 11794.15)
        self.assertAlmostEqual(r["high"], 11810.5)
        self.assertAlmostEqual(r["low"], 11790.0)
        self.assertAlmostEqual(r["close"], 11800.0)
        self.assertAlmostEqual(r["volume"], 123.45)
        self.assertAlmostEqual(r["taker_buy_volume"], 60.5)
        self.assertAlmostEqual(r["quote_volume"], 1456789.0)

    def test_update_intermediaire_marquee_non_closed(self):
        rows = kw.parse_frame(kline_frame(closed=False))
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["closed"])
        # le filtre runtime (parade b) : x=false n'atteint jamais le buffer
        self.assertEqual([r for r in rows if r["closed"]], [])

    def test_frame_nu_sans_combined(self):
        raw = json.dumps({"e": "kline", "E": 1, "s": "BTCUSDT",
                          "k": json.loads(kline_frame(True))["data"]["k"]})
        rows = kw.parse_frame(raw)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["closed"])

    def test_frames_hors_kline_ignores(self):
        self.assertEqual(kw.parse_frame('{"result":null,"id":1}'), [])
        self.assertEqual(kw.parse_frame('not json at all'), [])
        self.assertEqual(kw.parse_frame('[]'), [])

    def test_prix_invalide_ecarte(self):
        # open=0 violerait le CHECK (open > 0) : la ligne est ecartee au
        # parse pour ne pas perdre tout le batch au flush.
        self.assertEqual(kw.parse_frame(kline_frame(True, o="0")), [])


class TestUniversEtUrl(unittest.TestCase):
    def test_univers_nocturne(self):
        self.assertEqual(len(kw.UNIVERSE_1H), 36)
        self.assertEqual(len(kw.UNIVERSE_15M), 15)
        self.assertTrue(set(kw.UNIVERSE_15M) <= set(kw.UNIVERSE_1H))

    def test_build_url_51_streams_minuscules(self):
        active = kw.initial_active()
        url = kw.build_url(active)
        streams = url.split("?streams=")[1].split("/")
        self.assertEqual(len(streams), 51)  # 36 x 1h + 15 x 15m
        self.assertTrue(url.startswith(kw.WS_BASE))
        self.assertTrue(all(s == s.lower() for s in streams))
        self.assertIn("btcusdt@kline_1h", streams)
        self.assertIn("btcusdt@kline_15m", streams)
        self.assertIn("melaniausdt@kline_1h", streams)


class TestPlanDemotion(unittest.TestCase):
    def test_sous_la_limite_aucune_demotion(self):
        demote, proj = kw.plan_demotion(["A", "B"], {"A": 20, "B": 10})
        self.assertEqual(demote, set())
        self.assertAlmostEqual(proj, 3.0)

    def test_les_moins_actifs_dabord(self):
        # total 96 msgs/10s = 9.6/s > 8 : on demote J(4),I(5),H(6),G(7)
        # puis projected 7.4/s < 8 -> F est epargne (moins actifs d'abord).
        demote, proj = kw.plan_demotion(
            ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
            {"A": 20, "B": 15, "C": 12, "D": 10, "E": 9,
             "F": 8, "G": 7, "H": 6, "I": 5, "J": 4})
        self.assertEqual(demote, {"J", "I", "H", "G"})
        self.assertAlmostEqual(proj, 7.4)
        self.assertLess(proj, kw.RATE_LIMIT_PER_S)

    def test_keep_min_respecte(self):
        demote, _ = kw.plan_demotion(
            ["A", "B", "C", "D", "E"],
            {"A": 900, "B": 800, "C": 700, "D": 600, "E": 100}, keep_min=2)
        self.assertEqual(len({"A", "B", "C", "D", "E"} - demote), 2)

    def test_symbole_muets_demotes_en_premier(self):
        # keep_min=1 : C (0 msg) et B partent, A (le plus actif) reste.
        demote, proj = kw.plan_demotion(
            ["A", "B", "C"], {"A": 100, "B": 90}, keep_min=1)
        self.assertEqual(demote, {"C", "B"})
        self.assertAlmostEqual(proj, 10.0)


class TestSnapshotId(unittest.TestCase):
    def test_forme_identique_a_fetch_klines(self):
        snap = kw.snapshot_id_rows("BTCUSDT", "15m", [1790725200000] * 3)
        self.assertEqual(snap, "aster-BTCUSDT-15m-1790725200000-1790725200000-3")


if __name__ == "__main__":
    unittest.main()
