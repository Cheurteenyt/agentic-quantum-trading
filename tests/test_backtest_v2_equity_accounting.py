"""Tests d'accounting de l'equite — le bug T7 (stops non comptes, frais absents).

Avant le fix, la barre de stop restait a 0.0 dans `bar_ret` : la perte stoppee
n'entrait JAMAIS dans la courbe d'equite, et les fees n'y figuraient pas non
plus. Preuve T7 : funding_carry BTC bear 2022, equite +237 % vs somme des
trades -124 % (reports/aster_deep_regimes.md).

Invariants EXACTS apres fix (accounting mark-to-market, fees par fill) :
  1. Jambe de stop : bar_ret[x] = side*(exit/base - 1) - FEE_PER_FILL
     (base = close precedent, ou open d'entree si stop sur la barre d'entree ;
     funding_fade y ajoute le funding de la barre).
  2. Identite globale : equity[-1] = prod(1 + bar_ret)
                       = prod_t (1 + gross_t) * (1 - FEE_PER_FILL)^(2*n_t)
     l'equite decrit donc le MEME flux de trades que la couche honnete.
  3. Regression : l'equite DESCEND pendant un trade stoppe (avant le fix,
     elle restait plate ou montait : la perte etait invisible).

    python tests/test_backtest_v2_equity_accounting.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.costs import FundingRate  # noqa: E402

STRAT_DIR = ROOT / "backend" / "services" / "backtest_v2" / "strategies"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, STRAT_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # requis pour @dataclass (introspection module)
    spec.loader.exec_module(mod)
    return mod


mom = _load("_acct_momentum", "momentum.py")
bo = _load("_acct_breakout", "breakout.py")
mr = _load("_acct_meanrev", "mean_reversion.py")
fc = _load("_acct_fcarry", "funding_carry.py")
ff = _load("_acct_ffade", "funding_fade.py")

MODULES = {"momentum": mom, "breakout": bo, "mean_reversion": mr,
           "funding_carry": fc, "funding_fade": ff}

HOUR_MS = 3_600_000


def _bars_from_closes(closes, spread=0.5):
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(
            Bar(ts=i * HOUR_MS, open=o, high=max(o, c) + spread,
                low=min(o, c) - spread, close=c, volume=100.0)
        )
        prev = c
    return out


def _fresh_rate(symbol="BTCUSDT", bps=0.44):
    return FundingRate(symbol, bps, 9999, 0, time.time())


def _stub_carry_funding():
    fc.load_funding_rate = lambda *a, **k: _fresh_rate()


def _prod(seq):
    out = 1.0
    for r in seq:
        out *= 1.0 + r
    return out


def _equity_from(bar_ret):
    eq = [1.0]
    for r in bar_ret:
        eq.append(eq[-1] * (1.0 + r))
    return eq


# ------------------------------------------------------------------ scenarios
# Chaque scenario renvoie (trades, bar_ret, bars) et contient au moins un stop.


def _mom_stop_scenario():
    """Hausse puis effondrement : un long entre puis stoppe (-2 %)."""
    closes = [100.0 + i * 0.5 for i in range(30)] + [70.0, 65.0, 60.0, 58.0, 57.0]
    bars = _bars_from_closes(closes)
    params = dict(fast_ema=3, slow_ema=10, regime_ema=20, allow_short=False,
                  stop_bps=200, take_bps=100_000, max_leverage=2)
    trades, br = mom.simulate(bars, params)
    return trades, br, bars, None


def _bo_stop_scenario():
    """Range puis breakout long puis crash : stop (sur la barre d'entree)."""
    bars = []
    for i in range(30):
        p = 100.0 + (0.2 if i % 2 else -0.2)
        bars.append(Bar(ts=i * HOUR_MS, open=100.0, high=p + 0.3, low=p - 0.3,
                        close=p, volume=10.0))
    for k in range(10):
        p = 101.0 + k
        i = 30 + k
        bars.append(Bar(ts=i * HOUR_MS, open=p - 0.5, high=p + 0.5, low=p - 0.6,
                        close=p, volume=10.0))
    prev = bars[-1].close
    for k in range(5):
        i = 40 + k
        c = prev - 8.0 * (k + 1)
        bars.append(Bar(ts=i * HOUR_MS, open=prev, high=prev + 0.5,
                        low=min(prev, c) - 1.0, close=c, volume=10.0))
        prev = c
    params = dict(donchian_len=10, breakout_mult=0.0, confirmation_bars=1,
                  use_close=False, allow_short=False, stop_bps=500,
                  take_bps=800, max_leverage=2)
    trades, br = bo.simulate(bars, params)
    return trades, br, bars, None


def _mr_stop_scenario():
    """Plateau puis chute : des longs mean-reversion stoppes en serie."""
    closes = [100.0] * 120 + [94.0, 93.0] + [80.0, 70.0, 60.0, 55.0, 50.0, 48.0]
    bars = _bars_from_closes(closes)
    params = dict(lookback=20, entry_z=2.5, exit_z=0.5, use_std=True,
                  allow_short=False, stop_bps=150, take_bps=10_000,
                  max_leverage=3)
    trades, br = mr.simulate(bars, params)
    return trades, br, bars, None


def _fc_stop_scenario():
    """Short collecteur dans une MONTREE : stops repetes + roulements + eod."""
    _stub_carry_funding()
    closes = [200.0 + i * 0.8 for i in range(80)]
    bars = _bars_from_closes(closes)
    trades, br = fc.simulate(bars, dict(stop_bps=200, hold_max_bars=30),
                             lambda ts: "short", 30)
    return trades, br, bars, None


def _ff_stop_scenario():
    """Spike de funding -> entree, puis prix en scie +/-4 % : stop certain."""
    n = 200
    series = [0.0] * 80 + [6.0] * (n - 80)
    closes = [100.0] * 100
    c = 100.0
    for i in range(100, n):
        c = c * 1.04 if (i // 2) % 2 == 0 else c * 0.96
        closes.append(c)
    bars = _bars_from_closes(closes)
    params = dict(lookback=50, entry_z=1.0, exit_z=0.2, allow_short=True,
                  stop_bps=200, max_leverage=3)
    trades, br = ff.simulate(bars, params, series)
    return trades, br, bars, series


SCENARIOS = [
    ("momentum", _mom_stop_scenario, None),
    ("breakout", _bo_stop_scenario, None),
    ("mean_reversion", _mr_stop_scenario, None),
    ("funding_carry", _fc_stop_scenario, None),
    ("funding_fade", _ff_stop_scenario, "series"),
]


class TestStopAccounting(unittest.TestCase):
    """Le coeur du bug T7 : la perte stoppee doit vivre dans bar_ret/equite."""

    def test_every_scenario_has_stopped_trades(self):
        for name, scen, _series in SCENARIOS:
            trades, _br, _bars, _s = scen()
            self.assertTrue(
                any(t.reason == "stop" for t in trades),
                f"{name}: aucun stop declenche, scenario invalide",
            )

    def test_stop_loss_booked_in_bar_returns(self):
        """La barre de stop porte la jambe side*(exit/base-1) - fee (pas 0.0)."""
        checked = 0
        for name, scen, _series in SCENARIOS:
            trades, br, bars, series = scen()
            fee = MODULES[name].FEE_FRACTION_PER_FILL
            for t in trades:
                if t.reason != "stop" or t.exit_index == 0:
                    continue
                # base du dernier mark : open d'entree si stop des la barre
                # d'entree, sinon close de la barre precedente.
                if t.exit_index == t.entry_index:
                    base = bars[t.exit_index].open
                else:
                    base = bars[t.exit_index - 1].close
                # stop sur la barre d'entree : la barre porte AUSSI le fee
                # d'entree (deux fills sur la meme barre).
                n_fees = 2 if t.exit_index == t.entry_index else 1
                expected = t.side * (t.exit_price / base - 1.0) - n_fees * fee
                if series is not None:
                    # funding_fade : le funding de la barre de stop est accrue
                    # (position detenue pendant la barre ; barres d'1h).
                    expected += -t.side * (series[t.exit_index] / 10_000.0) * (1.0 / 8.0)
                self.assertAlmostEqual(
                    br[t.exit_index], expected, places=10,
                    msg=f"{name}: jambe de stop barre {t.exit_index} fausse "
                        f"({br[t.exit_index]:+.6f} != {expected:+.6f})",
                )
                checked += 1
        self.assertGreater(checked, 0, "aucune jambe de stop verifiee")

    def test_stop_dips_equity(self):
        """Regression T7 : l'equite DESCEND pendant un trade stoppe.

        Avant le fix, la barre de stop valait 0.0 : l'equite restait plate
        (ou montait) pendant que le trade perdait son stop.
        """
        for name, scen, _series in SCENARIOS:
            trades, br, _bars, _s = scen()
            equity = _equity_from(br)
            for t in trades:
                if t.reason != "stop":
                    continue
                window = equity[t.entry_index: t.exit_index + 2]
                self.assertLess(
                    min(window), equity[t.entry_index],
                    msg=f"{name}: equite plate pendant le trade stoppe "
                        f"[{t.entry_index},{t.exit_index}] — perte invisible",
                )


class TestEquityReconciliation(unittest.TestCase):
    """L'equite doit decrire le MEME flux que la couche honnete (trades)."""

    def test_global_multiplicative_identity(self):
        """equity[-1] = prod(1+bar_ret) = prod_t (1+gross_t)*(1-fee)^(2n)."""
        for name, scen, _series in SCENARIOS:
            trades, br, _bars, _s = scen()
            equity = _equity_from(br)
            self.assertEqual(len(equity), len(br) + 1, name)
            # 1. equity == produit des rendements par barre (exact)
            self.assertAlmostEqual(equity[-1], _prod(br), places=9, msg=name)
            if name == "funding_fade":
                # Scenario scie +/-4 % : en compense (1x re-marque), un short
                # verifie prod(1-r) != 1/prod(1+r) des que |r| n'est plus
                # petit — geometrie de composition, pas accounting. Ce module
                # reste couvert par test_funding_fade_reconciliation_approx
                # et les tests exacts (jambe de stop, equite qui plonge).
                continue
            # 2. equity == flux de trades (gross + fees par fill). Les fees
            #    additifs partagent la barre avec une jambe de prix : le
            #    produit exact differe des cross-terms fee*jambe (< 5e-3),
            #    contre un ecart T7 de +3.6 (equite +237 % vs flux -124 %).
            fee = MODULES[name].FEE_FRACTION_PER_FILL
            expected = 1.0
            for t in trades:
                expected *= (1.0 + t.gross_return) * (1.0 - fee) ** 2
            self.assertLess(
                abs(equity[-1] - expected), 5e-3,
                msg=f"{name}: equite != flux de trades "
                    f"({equity[-1] - 1:+.4%} vs {expected - 1:+.4%})",
            )

    def test_funding_fade_reconciliation_approx(self):
        """funding_fade : l'equite suit la somme des trades au bruit de
        composition pres (scie +/-4 %) — le biais T7 etait de +3.6."""
        trades, br, _bars, _s = _ff_stop_scenario()
        equity = _equity_from(br)
        sum_net = sum(t.net_return for t in trades)
        self.assertLess(abs((equity[-1] - 1.0) - sum_net), 0.10)


class TestPerFillFees(unittest.TestCase):
    """Les fees sont bookes a CHAQUE fill : moitie a l'entree, moitie a la sortie."""

    def test_fee_constant_is_half_round_trip(self):
        for name, mod in MODULES.items():
            self.assertAlmostEqual(
                mod.FEE_FRACTION_PER_FILL, mod.FEE_FRACTION_ROUND_TRIP / 2.0,
                msg=f"{name}: le fee par fill doit valoir la moitie de l'aller-retour",
            )

    def test_flat_series_pays_nothing(self):
        """Sans trade, aucune jambe de fee : bar_ret reste a zero."""
        _stub_carry_funding()
        bars = _bars_from_closes([100.0 + 0.01 * (i % 3) for i in range(40)])
        # EMAs sans cross net sur une serie plate -> 0 trade, 0 fee.
        trades, br = mom.simulate(
            bars, dict(fast_ema=3, slow_ema=60, regime_ema=200,
                       allow_short=False, stop_bps=200, take_bps=200,
                       max_leverage=2)
        )
        self.assertEqual(trades, [])
        self.assertTrue(all(r == 0.0 for r in br))


if __name__ == "__main__":
    unittest.main(verbosity=2)
