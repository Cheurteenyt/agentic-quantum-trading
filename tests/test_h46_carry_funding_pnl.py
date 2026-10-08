"""H-46 (audit ronde 4) — funding_carry était jugé SANS son bord.

La jambe funding vivait uniquement dans costs.funding_usd (comptabilité)
et n'entrait NI dans trade.net_return NI dans la courbe d'équité : sur des
barres plates avec un funding +10 bps/8h collecté en short, la stratégie
mesurait −16 bps (les frais) au lieu de +552 bps réels. Le moteur jugeait
donc la collecte de funding... sans le funding.

    python tests/test_h46_carry_funding_pnl.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.strategies.funding_carry import (  # noqa: E402
    FEE_FRACTION_ROUND_TRIP,
    Trade,
    simulate,
)

T0 = 1_700_000_000_000  # ms, arbitraire
HOUR_MS = 3_600_000
FUNDING_BPS = 10.0      # +10 bps / 8h : les shorts encaissent


def _flat_bars(n: int) -> list[Bar]:
    """Barres 1h STRICTEMENT plates : tout le PnL vient du funding."""
    return [Bar(ts=T0 + i * HOUR_MS, open=100.0, high=100.0,
                low=100.0, close=100.0, volume=1_000.0) for i in range(n)]


class _ConstFser:
    """Duck-type FundingSeries : un taux CONSTANT connu de tout temps."""

    def rate_asof(self, ts_ms: float) -> float:
        return FUNDING_BPS


class _NeverFser:
    def rate_asof(self, ts_ms: float):
        return None


PARAMS = {"stop_bps": 500, "allow_short": True}


def _short_only(ts_ms: float) -> str:
    return "short"


class TestFundingLegInReturns(unittest.TestCase):
    def test_le_carry_encaisse_sur_barres_plates(self):
        # 400 barres plates, short collecteur, funding +10 bps/8h :
        # l'équité DOIT monter (avant le fix : elle descendait — les frais)
        bars = _flat_bars(400)
        trades, bar_ret = simulate(bars, PARAMS, _short_only, 168,
                                   fser=_ConstFser())
        self.assertTrue(trades)
        equity = 1.0
        for r in bar_ret:
            equity *= 1.0 + r
        self.assertGreater(equity, 1.0,
                           "le carry doit ENCAISSER le funding : une "
                           "équité finale < 1 sur des barres plates avec "
                           "un funding collecteur est le bug H-46")

    def test_net_return_porte_la_jambe_funding(self):
        bars = _flat_bars(400)
        trades, _ = simulate(bars, PARAMS, _short_only, 168,
                             fser=_ConstFser())
        for t in trades:
            with self.subTest(trade=(t.entry_index, t.exit_index)):
                self.assertGreater(t.funding_return, 0.0)
                # barres plates : gross = 0 -> net = funding - frais
                self.assertAlmostEqual(
                    t.net_return,
                    t.gross_return + t.funding_return
                    - FEE_FRACTION_ROUND_TRIP, places=12)
                self.assertGreater(
                    t.net_return, t.gross_return - FEE_FRACTION_ROUND_TRIP,
                    "le net doit contenir la jambe funding (H-46)")

    def test_equite_et_nets_racontent_la_meme_histoire(self):
        # Invariant de complétude au niveau SÉRIE : Σ bar_ret = Σ net_return.
        # (Par trade, la barre de roulement appartient aux DEUX trades —
        # sortie de l'un, entrée + premier accrual de l'autre au même open —
        # donc la découpe par slices n'est pas exacte ; la série l'est :
        # chaque frais/funding/jambe de prix est booké exactement une fois.)
        bars = _flat_bars(400)
        trades, bar_ret = simulate(bars, PARAMS, _short_only, 168,
                                   fser=_ConstFser())
        somme = sum(bar_ret)
        nets = sum(t.net_return for t in trades)
        self.assertAlmostEqual(somme, nets, places=10)

    def test_signe_du_cote_collecteur(self):
        # funding positif -> SHORT encaisse (jambe > 0) ;
        # funding positif -> LONG paie (jambe < 0)
        bars = _flat_bars(50)

        def long_only(ts_ms):
            return "long"

        trades, _ = simulate(bars, PARAMS, long_only, 168,
                             fser=_ConstFser())
        self.assertTrue(trades)
        self.assertLess(trades[0].funding_return, 0.0)

    def test_funding_indisponible_comportement_conserve(self):
        # fser=None ou rate_asof None : aucune jambe, funding_return = 0.0
        # explicite — le contrat « funding indisponible » ne change pas.
        bars = _flat_bars(50)
        for fser in (None, _NeverFser()):
            trades, bar_ret = simulate(bars, PARAMS, _short_only, 168,
                                       fser=fser)
            self.assertTrue(trades)
            for t in trades:
                self.assertEqual(t.funding_return, 0.0)
                self.assertAlmostEqual(
                    t.net_return,
                    t.gross_return - FEE_FRACTION_ROUND_TRIP, places=12)

    def test_longueur_de_holding_sensible(self):
        # Plus on porte, plus le bord s'accumule (168 barres 1h = 7 j) :
        # le funding d'un trade long-hold doit dominer celui d'un court-hold.
        bars = _flat_bars(200)
        short_hold, _ = simulate(bars, PARAMS, _short_only, 24,
                                 fser=_ConstFser())
        long_hold, _ = simulate(bars, PARAMS, _short_only, 168,
                                fser=_ConstFser())
        avg_short = sum(t.funding_return for t in short_hold) / len(short_hold)
        avg_long = sum(t.funding_return for t in long_hold) / len(long_hold)
        self.assertGreater(avg_long, avg_short)


if __name__ == "__main__":
    unittest.main(verbosity=2)
