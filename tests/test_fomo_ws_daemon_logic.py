#!/usr/bin/env python3
"""Les tests unitaires de la logique pure du daemon WS fomo (hors réseau).

Couvre : HotSet (LRU + épinglage), SignalEngine (le consensus de sortie
glissant, idempotent), le rolling des bougies 1m et la dédup des ticks.

    .venv/bin/python -m unittest tests.test_fomo_ws_daemon_logic -v
"""
import unittest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class HotSetTests(unittest.TestCase):
    """Le budget de topics : les épinglés jamais évincés, le LRU tourne."""

    def setUp(self):
        import fomo_ws_daemon as d
        self.d = d
        d.MAX_PRICE_TOPICS = 5  # le budget réduit pour tester l'éviction
        self.hot = d.HotSet(["m1", "m2"])

    def tearDown(self):
        self.d.MAX_PRICE_TOPICS = 78

    def test_seed_is_lru(self):
        self.assertEqual(set(self.hot.lru), {"m1", "m2"})
        self.assertEqual(self.hot.pinned, set())

    def test_touch_new_and_evict(self):
        new, ev = self.hot.touch("m3")
        self.assertEqual(new, "m3")
        self.assertIsNone(ev)
        new, ev = self.hot.touch("m4")
        new, ev = self.hot.touch("m5")
        self.assertEqual(len(self.hot.lru), 5)  # m1..m5 = le budget exact
        self.assertIsNone(ev)
        # le budget saturé → le prochain touch évince le plus ancien
        new, ev = self.hot.touch("m6")
        self.assertEqual(ev, "m1")
        self.assertEqual(len(self.hot.lru), 5)

    def test_touch_existing_no_evict(self):
        for i in range(3, 10):
            self.hot.touch(f"m{i}")
        self.hot.touch("m3")  # re-touché = replacé en fin, pas d'éviction double
        self.assertIn("m3", self.hot.lru)

    def test_pin_never_evicted(self):
        self.hot.touch("m3")
        self.hot.touch("m4")
        new = self.hot.pin("m5")
        self.assertEqual(new, "m5")
        self.assertIn("m5", self.hot.pinned)
        self.assertNotIn("m5", self.hot.lru)
        # remplir le LRU → l'éviction ne touche JAMAIS les épinglés
        for i in range(6, 12):
            self.hot.touch(f"m{i}")
        self.assertIn("m5", self.hot.pinned)

    def test_pin_twice_idempotent(self):
        self.assertEqual(self.hot.pin("m3"), "m3")
        self.assertEqual(self.hot.pin("m3"), None)  # déjà épinglé

    def test_touch_after_pin_budget_full(self):
        for i in range(2, 5):
            self.hot.touch(f"m{i}")
        self.hot.pin("m5")
        # le budget 5 = saturé (m2..m4 en LRU + m5 épinglé + m1)…
        new, ev = self.hot.touch("m9")
        # soit l'éviction, soit le refus — mais jamais le dépassement
        self.assertLessEqual(len(self.hot.lru) + len(self.hot.pinned), 5)


class SignalEngineTests(unittest.TestCase):
    """Le consensus de sortie : 2 vendeurs distincts, la fenêtre, l'idempotence."""

    def setUp(self):
        import fomo_ws_daemon as d
        self.eng = d.SignalEngine()

    def test_single_seller_no_signal(self):
        self.assertIsNone(self.eng.on_top_sell("tok", "unipcs", "AAA"))

    def test_two_sellers_emit(self):
        self.eng.on_top_sell("tok", "unipcs", "AAA")
        h = self.eng.on_top_sell("tok", "pointfarmcap", "AAA")
        self.assertEqual(h, {"unipcs", "pointfarmcap"})

    def test_same_seller_twice_no_signal(self):
        self.eng.on_top_sell("tok", "unipcs", "AAA")
        self.assertIsNone(self.eng.on_top_sell("tok", "unipcs", "AAA"))

    def test_idempotent_same_bucket(self):
        self.eng.on_top_sell("tok", "unipcs", "AAA")
        self.eng.on_top_sell("tok", "pointfarmcap", "AAA")
        self.assertIsNone(self.eng.on_top_sell("tok", "Salem1299534", "AAA"))

    def test_different_tokens_independent(self):
        self.eng.on_top_sell("tokA", "unipcs", "AAA")
        h = self.eng.on_top_sell("tokB", "pointfarmcap", "BBB")
        self.assertIsNone(h)  # des tokens différents = pas de consensus

    def test_window_eviction(self):
        # un vieux vendeur (> 30 min) ne compte plus
        old_ts = __import__("time").time() - 31 * 60
        self.eng.sells.append((old_ts, "tok", "unipcs"))
        self.assertIsNone(self.eng.on_top_sell("tok", "pointfarmcap", "AAA"))


class CandleRollTests(unittest.TestCase):
    """Les bougies 1m : o/h/l/c corrects, la dédup sans perte d'info."""

    def _writer(self):
        import fomo_ws_daemon as d
        with patch.object(d, "DB_TICKS", ":memory:"), \
             patch.object(d, "DB_SWAPS", ":memory:"):
            w = d.Writer.__new__(d.Writer)
            w.tick_q, w.swap_q, w.thesis_q, w.event_q = [], [], [], []
            w.trader_q = {}
            w.last_px = {}
            w.candles, w.swap_vol = {}, {}
            w.last_flush = 0
            w.n_ticks = w.n_swaps = w.n_top = w.n_sells_top = 0
            w.n_candles = w.n_theses = w.n_events = w.n_dedup = w.n_errors = 0
            w.n_bad_px = 0
            w.unknown_types = set()
            w.con_ticks = MagicMock()
            w.con_swaps = MagicMock()
            return w

    def test_candle_ohlc(self):
        w = self._writer()
        minute = 1790640000 * 1000
        w.add_price("mintA:1399811149", {"timestamp": 1790640000, "priceUsd": 1.0})
        w.add_price("mintA:1399811149", {"timestamp": 1790640010, "priceUsd": 2.0})
        w.add_price("mintA:1399811149", {"timestamp": 1790640020, "priceUsd": 0.5})
        w.add_price("mintA:1399811149", {"timestamp": 1790640030, "priceUsd": 1.5})
        c = w.candles["mintA"]
        self.assertEqual(c, [minute, 1.0, 2.0, 0.5, 1.5])

    def test_dedup_identical_price(self):
        w = self._writer()
        w.add_price("mintA:1399811149", {"timestamp": 1790640000, "priceUsd": 1.0})
        n1 = len(w.tick_q)
        w.add_price("mintA:1399811149", {"timestamp": 1790640001, "priceUsd": 1.0})
        self.assertEqual(len(w.tick_q), n1)  # le même prix = pas de tick
        self.assertEqual(w.n_dedup, 1)
        w.add_price("mintA:1399811149", {"timestamp": 1790640002, "priceUsd": 1.1})
        self.assertEqual(len(w.tick_q), n1 + 1)  # le changement = écrit

    def test_new_minute_new_candle(self):
        w = self._writer()
        w.add_price("mintA:1399811149", {"timestamp": 1790640000, "priceUsd": 1.0})
        w.add_price("mintA:1399811149", {"timestamp": 1790640060, "priceUsd": 2.0})
        self.assertEqual(len(w.candles), 1)  # l'ancienne bougie = roulée par _roll
        # sans roll, le buffer = la nouvelle minute
        c = list(w.candles.values())[0]
        self.assertEqual(c[0], 1790640060 * 1000)

    # ── Fuzz 2026-10-10 : le garde sur priceUsd ──────────────────────────
    # `float()` accepte "nan"/"inf"/"1e400" SANS lever d'erreur, et en Python
    # max(nan, x) = nan : un seul prix non fini rendait high/low nan À VIE,
    # puis la bougie corrompue partait en DB (toutes les stats en aval
    # faussées, en silence). Un prix doit être FINI et > 0.

    _PRIX_INVALIDES = [
        float("nan"), float("inf"), float("-inf"),   # les non-finis
        "nan", "1e400",                              # les chaînes pièges
        "abc",                                       # la chaîne non numérique
        0, -5, -0.0,                                 # le zéro et les négatifs
    ]

    def test_prix_non_fini_ou_negatif_rejete(self):
        w = self._writer()
        for bad in self._PRIX_INVALIDES:
            w.add_price("mintA:1399811149", {"timestamp": 1790640000, "priceUsd": bad})
        self.assertEqual(len(w.tick_q), 0,
                         "aucun tick non fini/<=0 ne doit être écrit")
        self.assertNotIn("mintA", w.candles,
                         "aucune bougie ne doit naître d'un prix invalide")
        self.assertEqual(w.n_bad_px, len(self._PRIX_INVALIDES),
                         "chaque rejet doit être COMPTÉ (fail-closed visible)")

    def test_prix_nan_n_empoisonne_pas_la_bougie(self):
        """Le cœur du bug : après un tick sain, un nan ne doit pas figer
        high/low — c'est là que max(nan, x) = nan faisait le dégât."""
        w = self._writer()
        w.add_price("mintA:1399811149", {"timestamp": 1790640000, "priceUsd": 1.0})
        w.add_price("mintA:1399811149", {"timestamp": 1790640010, "priceUsd": float("nan")})
        w.add_price("mintA:1399811149", {"timestamp": 1790640020, "priceUsd": 2.0})
        c = w.candles["mintA"]
        self.assertTrue(all(x == x for x in c[1:]),
                        f"bougie empoisonnée par un nan : {c}")
        self.assertEqual(c, [1790640000 * 1000, 1.0, 2.0, 1.0, 2.0])

    def test_prix_valide_passe_toujours(self):
        """Le garde ne doit pas être un refus en bloc : un prix fini > 0
        passe, et le compteur de rejets reste à zéro."""
        w = self._writer()
        w.add_price("mintA:1399811149", {"timestamp": 1790640000, "priceUsd": 1.0})
        w.add_price("mintA:1399811149", {"timestamp": 1790640010, "priceUsd": "2.5"})
        self.assertEqual(len(w.tick_q), 2)
        self.assertEqual(w.n_bad_px, 0)


if __name__ == "__main__":
    unittest.main()
