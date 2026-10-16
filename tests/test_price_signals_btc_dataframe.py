"""L'EXPLOSION n×n DE price_signals — le piège du DataFrame BTC.

Incident du 16/10/2026 : `signal_audit` a été SIGKILL à 31,5 Go RSS et
reproduit sous plafond — `price_signals(df, btc_df)` allouait (n, n+5)
cellules (≈ 16 Go à n = 44 898, le BTC 1h actuel).

Mécanisme : avec un DataFrame en `btc_close`, `beta` et `btc_r` deviennent
des DataFrames (5 colonnes) et la ligne

    disloc = sym_r - beta * btc_r

est une soustraction Series − DataFrame : pandas aligne alors l'INDEX de
la Series sur les COLONNES du DataFrame → une colonne par barre.

Le contrat (paramètre `btc_close`) est la série close. Cet oracle exige :
  1. un DataFrame BTC rend EXACTEMENT le même verdict que la Series close ;
  2. chaque masque de sortie est 1-D (aucun masque à ≈ n colonnes).

Appelants réels à la date de l'incident : `paper_forward.py` (nocturne, le
DataFrame à CHAQUE symbole), `signal_audit.py`, `full_arsenal.py`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import price_signals  # noqa: E402

N = 600


def _fixture(seed: int = 7):
    """600 barres 1h synthétiques ; `btc_df["close"] == btc_close`."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=N, freq="1h")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, N)))
    df = pd.DataFrame(
        {
            "open": close * (1.0 + rng.normal(0.0, 0.001, N)),
            "high": close * (1.0 + np.abs(rng.normal(0.0, 0.005, N))),
            "low": close * (1.0 - np.abs(rng.normal(0.0, 0.005, N))),
            "close": close,
            "volume": np.abs(rng.normal(1000.0, 200.0, N)),
        },
        index=idx,
    )
    btc_close = pd.Series(
        200.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, N))), index=idx)
    btc_df = pd.DataFrame(
        {
            "open": btc_close * 0.999,
            "high": btc_close * 1.002,
            "low": btc_close * 0.998,
            "close": btc_close,
            "volume": np.abs(rng.normal(5000.0, 500.0, N)),
        },
        index=idx,
    )
    return df, btc_df, btc_close


class TestPriceSignalsDataframeBtc(unittest.TestCase):
    def test_series_et_dataframe_rendent_le_meme_verdict(self):
        df, btc_df, btc_close = _fixture()
        out_serie = price_signals(df, btc_close)
        out_df = price_signals(df, btc_df)
        self.assertEqual(
            [(n, d) for n, d, _ in out_serie],
            [(n, d) for n, d, _ in out_df],
            "mêmes signaux (nom, direction) dans les deux formes",
        )
        for (name, _d, m_serie), (_n2, _d2, m_df) in zip(out_serie, out_df):
            self.assertEqual(
                m_df.ndim, 1,
                f"{name} : masque {m_df.ndim}-D — un DataFrame BTC aligne "
                f"l'index de la Series sur les colonnes (n×n : l'explosion "
                f"du 16/10)",
            )
            pd.testing.assert_series_equal(
                m_serie, m_df, check_names=False, obj=f"masque {name}")

    def test_les_signaux_beta_sont_presents_dans_les_deux_formes(self):
        df, btc_df, btc_close = _fixture()
        for out in (price_signals(df, btc_close), price_signals(df, btc_df)):
            noms = [n for n, _d, _m in out]
            self.assertIn("beta_dislocation_achat", noms)
            self.assertIn("beta_dislocation_vente", noms)

    def test_aucun_masque_ne_compte_ses_colonnes_en_barres(self):
        df, btc_df, _ = _fixture()
        for name, _d, m in price_signals(df, btc_df):
            ncols = 1 if m.ndim == 1 else m.shape[1]
            self.assertLess(
                ncols, 10,
                f"{name} : {ncols} colonnes ≈ n — l'index de la Series "
                f"devenu colonnes (l'explosion n×n)",
            )


if __name__ == "__main__":
    unittest.main()
