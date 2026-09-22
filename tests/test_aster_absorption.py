"""Tests du détecteur absorption/sweep natif Aster (scripts/aster_absorption.py).

Mêmes règles que l'indicateur MMT « Absorption & Sweep » (docs/17-mmt-m5.md).
Les régressions ici corrompraient les signaux en silence : absorption qui
devient un suivi de tendance, sweep qui avale le bruit, split buy/sell faux.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aster_absorption import atr, bars_from_klines, detect  # noqa: E402


def _bar(o=100.0, h=100.5, l=99.5, c=100.2, buy=55.0, sell=45.0, t=0):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "buy": buy, "sell": sell}


def _series(n=60, o=100.0, spread=0.5):
    return [
        _bar(o=o, h=o + spread, l=o - spread, c=o + 0.1, t=i * 1800)
        for i in range(n)
    ]


class AbsorptionTest(unittest.TestCase):
    def test_baseline_neutral_series_has_no_event(self):
        self.assertEqual(detect(_series(60)), [])

    def test_absorption_buy_detected(self):
        bars = _series(60)
        # pression vendeuse extrême (delta -100) mais clôture >= ouverture
        bars[-1] = _bar(o=100.0, h=100.5, l=99.5, c=100.2, buy=10.0, sell=110.0, t=59 * 1800)
        evs = detect(bars)
        self.assertEqual([e["kind"] for e in evs], ["absorption_buy"])
        self.assertEqual(evs[0]["i"], 59)

    def test_absorption_sell_detected(self):
        bars = _series(60)
        # delta acheteur extrême (+100) mais clôture <= ouverture
        bars[-1] = _bar(o=100.0, h=100.5, l=99.5, c=99.8, buy=110.0, sell=10.0, t=59 * 1800)
        self.assertEqual([e["kind"] for e in detect(bars)], ["absorption_sell"])

    def test_extreme_delta_with_follow_through_is_not_absorption(self):
        bars = _series(60)
        # delta vendeur extrême ET gros corps baissier : suivi de tendance, pas absorption
        bars[-1] = _bar(o=100.4, h=100.5, l=99.5, c=99.5, buy=10.0, sell=110.0, t=59 * 1800)
        self.assertEqual(detect(bars), [])


class SweepTest(unittest.TestCase):
    def test_sweep_low_detected_and_reclaimed(self):
        bars = _series(60)
        # perce le plus-bas des 20 précédentes (~0.9, ATR ~1) et reclaim en clôture haute
        bars[-1] = _bar(o=99.2, h=100.1, l=99.0, c=99.95, buy=55.0, sell=45.0, t=59 * 1800)
        self.assertEqual([e["kind"] for e in detect(bars)], ["sweep_low"])

    def test_shallow_pierce_is_not_sweep(self):
        bars = _series(60)
        # perforation d'un tick : bruit, pas un sweep
        bars[-1] = _bar(o=99.9, h=100.1, l=99.49, c=100.05, buy=55.0, sell=45.0, t=59 * 1800)
        self.assertEqual(detect(bars), [])

    def test_sweep_high_symmetric(self):
        bars = _series(60)
        bars[-1] = _bar(o=100.8, h=100.99, l=99.9, c=100.05, buy=55.0, sell=45.0, t=59 * 1800)
        self.assertEqual([e["kind"] for e in detect(bars)], ["sweep_high"])

    def test_warmup_respected(self):
        bars = _series(60)
        evs = detect(bars, len_baseline=100, sweep_len=100)
        self.assertEqual(evs, [])


class DataTest(unittest.TestCase):
    def test_bars_from_klines_delta_split(self):
        kline = [1790100000000, "100.0", "101.0", "99.0", "100.5", "10.0",
                 1790101799999, "1005.0", 8, "6.0", "603.0", "0"]
        bars = bars_from_klines([kline])
        self.assertEqual(bars[0]["buy"], 6.0)
        self.assertAlmostEqual(bars[0]["sell"], 4.0)
        self.assertEqual(bars[0]["t"], 1790100000)

    def test_atr_matches_manual_tr(self):
        bars = _series(20, o=100.0, spread=1.0)
        # chaque bougie : h=o+1, l=o-1, close précédent=o-0.9 → TR = max(2, 1.9, 0.1) = 2.0
        a = atr(bars, 15, period=14)
        self.assertIsNotNone(a)
        self.assertAlmostEqual(a, 2.0)


if __name__ == "__main__":
    unittest.main()
