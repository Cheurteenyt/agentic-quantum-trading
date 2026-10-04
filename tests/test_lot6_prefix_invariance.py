"""FIX audit v3 (§20) — LE PREFIX INVARIANCE TEST, le détecteur générique
de fuites de futur.

Principe : une décision prise à l'instant t ne doit dépendre d'AUCUNE
donnée postérieure à t. Donc run(dataset complet) et run(dataset tronqué
à T) produisent des décisions IDENTIQUES pour tous les timestamps < T.
Ce test découvre automatiquement les leaks que des tests manuels oublient
(funding interpolé, ATR de bougie future, seuil full-sample...).

Couvert ici (les primitives pures, causalité par construction) :
  - funding as-of (rate_asof / sum_pct_between) ;
  - les quantiles expanding (le gate p90) ;
  - le RSI Wilder ;
  - l'ATR Wilder.

    python tests/test_lot6_prefix_invariance.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.funding_series import FundingSeries  # noqa: E402

H_MS = 3_600_000.0


def _load(name, rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ai = _load("_ai_prefix", "scripts/aster_indicators.py")


def _df(n=600, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": 1.0}, index=idx)


class TestFundingAsofInvariance(unittest.TestCase):
    def test_les_prints_futurs_ne_changent_rien(self):
        full = FundingSeries.from_rows([(i * H_MS, 0.0001 * (i % 7 + 1))
                                        for i in range(1, 100)])
        for t_ms in (2 * H_MS, 40 * H_MS, 80 * H_MS):
            exit_ms = t_ms + 10 * H_MS
            v_full = full.rate_asof(t_ms)
            s_sum = full.sum_pct_between(t_ms, exit_ms)
            # le dataset tronqué à la SORTIE du trade : tous les prints
            # postérieurs à la sortie supprimés → strictement rien ne change
            trunc = FundingSeries.from_rows(
                [(i * H_MS, 0.0001 * (i % 7 + 1))
                 for i in range(1, 100) if i * H_MS <= exit_ms])
            self.assertEqual(trunc.rate_asof(t_ms), v_full)
            self.assertEqual(trunc.sum_pct_between(t_ms, exit_ms), s_sum)


class TestExpandingQuantileInvariance(unittest.TestCase):
    def test_le_gate_dun_event_ne_voit_pas_le_futur(self):
        rng = np.random.default_rng(3)
        atrs = list(np.abs(rng.normal(1.0, 0.3, 300)))
        events = sorted(zip(
            (i * H_MS for i in range(300)), atrs), key=lambda x: x[0])

        def gate(dataset):
            kept = []
            for i, (ts, a) in enumerate(dataset):
                past = [x[1] for x in dataset[:i]]
                thr = (float(np.nanquantile(past, 0.90))
                       if len(past) >= 50 else float("inf"))
                if a <= thr:
                    kept.append(ts)
            return kept

        full = gate(events)
        trunc = gate([e for e in events if e[0] < 200 * H_MS])
        self.assertEqual([t for t in full if t < 200 * H_MS], trunc)


class TestIndicatorsCausalite(unittest.TestCase):
    def test_rsi_et_atr_invariants_au_futur(self):
        df_full = _df()
        for T in (200, 400):
            df_trunc = df_full.iloc[:T]
            for fn in (ai.rsi, ai.atr):
                full = fn(df_full, n=14)
                trunc = fn(df_trunc, n=14)
                np.testing.assert_allclose(
                    np.asarray(trunc.values, dtype=float),
                    np.asarray(full.values[:T], dtype=float),
                    rtol=1e-12, atol=1e-12,
                    err_msg=f"{fn.__name__} dépend du futur à T={T}")


if __name__ == "__main__":
    unittest.main()
