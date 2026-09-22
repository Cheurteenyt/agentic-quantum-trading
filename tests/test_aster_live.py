"""Tests du terminal live Aster (scripts/aster_live.py) — fonctions pures."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aster_live import bar, classify, fmt_qty, stream_url  # noqa: E402


class ClassifyTest(unittest.TestCase):
    def test_big_trade_above_multiple_of_median(self):
        self.assertEqual(classify(50.0, 2.0, 25.0), "big")

    def test_normal_trade_below_threshold(self):
        self.assertEqual(classify(10.0, 2.0, 25.0), "normal")

    def test_no_median_yet_means_normal(self):
        self.assertEqual(classify(100.0, 0.0, 25.0), "normal")


class FormatTest(unittest.TestCase):
    def test_fmt_qty_units(self):
        self.assertEqual(fmt_qty(1500.0), "1.5k")
        self.assertEqual(fmt_qty(55.5), "55.5")
        self.assertEqual(fmt_qty(0.123), "0.123")

    def test_bar_scales_to_max(self):
        self.assertEqual(bar(10.0, 10.0, width=10), "██████████")
        self.assertEqual(bar(5.0, 10.0, width=10), "█████")
        self.assertEqual(bar(0.0, 10.0, width=10), "█")  # minimum visible

    def test_bar_zero_max_is_empty(self):
        self.assertEqual(bar(5.0, 0.0, width=10), "")


class StreamUrlTest(unittest.TestCase):
    def test_combined_stream_contains_all_three(self):
        url = stream_url("BTCUSDT")
        self.assertIn("btcusdt@aggTrade", url)
        self.assertIn("btcusdt@depth20@100ms", url)
        self.assertIn("btcusdt@forceOrder", url)
        self.assertTrue(url.startswith("wss://fstream.asterdex.com/stream?streams="))


if __name__ == "__main__":
    unittest.main()
