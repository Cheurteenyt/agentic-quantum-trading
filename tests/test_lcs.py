"""LCS — le rapport de backtest, et LE contrat « zéro look-ahead ».

P1-c de l'audit externe (16/10) : `lcs.py` alimente la chaîne nocturne
(`--today`, la carte de chasse) et écrit le rapport de backtest — sans
aucun test qui l'exécute.

Trois oracles :
  - `rolling_pctile` : le percentile du jour i est celui de la VEILLE
    (fenêtre décalée) — une valeur ne peut pas se juger elle-même ;
  - `symbol_lcs` : muter les barres APRÈS un jour D ne change AUCUNE
    composante des jours ≤ D (le contrat du docstring) ;
  - `main()` : rapport écrit en mode backtest ; `--today` ne doit RIEN
    écrire (lecture seule).
"""
from __future__ import annotations

import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import scripts.lcs as lcs  # noqa: E402

# Schéma réel (les colonnes que lit backtest_indicators.load_df + la table
# funding_history du warehouse) — une dérive de colonne doit casser CE
# test, pas le nocturne.
K_SCHEMA = (
    "CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,"
    " open REAL, high REAL, low REAL, close REAL, volume REAL)",
    "CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,"
    " rate REAL)",
)


def _df(close: np.ndarray, start: str = "2026-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(close), freq="1h")
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": np.full(len(close), 1000.0)},
        index=idx,
    )


class TestRollingPctile(unittest.TestCase):
    def test_percentile_decale_d_un_jour(self) -> None:
        s = pd.Series(np.arange(120.0))
        r = lcs.rolling_pctile(s, 90)
        # Fenêtre pleine à i-1 ≥ 89 : la valeur de i=90 est le rang de la
        # VEILLE (le max de sa fenêtre) — NaN avant, 1.0 ensuite.
        self.assertTrue(r.iloc[:90].isna().all())
        self.assertAlmostEqual(r.iloc[90], 1.0, places=9)
        d = lcs.rolling_pctile(pd.Series(np.arange(120.0, 0.0, -1.0)), 90)
        # Décroissant : la veille est le min de sa fenêtre → 1/90.
        self.assertAlmostEqual(d.iloc[90], 1 / 90, places=9)


class TestSymbolLcs(unittest.TestCase):
    def test_composantes_dd_age_funding(self) -> None:
        n = 20 * 24
        jour = np.arange(n) // 24
        close = np.where((jour >= 10) & (jour < 14), 65.0, 100.0)
        close = np.where(jour >= 14, 70.0, close)
        out = lcs.symbol_lcs(_df(close), None)
        self.assertEqual(len(out), 20)
        # Âge : la zone de mort commence à J+7 (composante 0 → 1).
        self.assertEqual(out["age_sig"].iloc[6], 0.0)
        self.assertEqual(out["age_sig"].iloc[7], 1.0)
        # Drawdown : bande 20-50 % (0 au calme, 1 à -35 %).
        self.assertEqual(out["dd_sig"].iloc[9], 0.0)
        self.assertEqual(out["dd_sig"].iloc[12], 1.0)
        # Sans funding, la composante reste neutre.
        self.assertTrue((out["funding_sig"] == 0.5).all())
        # Fenêtre percentile 90 j non remplie → stretch neutre (NaN,
        # remonté à 0.5 dans le score).
        self.assertTrue(out["stretch_sig"].isna().all())
        # lcs = moyenne des 4 composantes × 100 : 50 (calme, dd=0) puis
        # 75 (bande, dd=1) — la formule exacte est verrouillée.
        self.assertAlmostEqual(out["lcs"].iloc[9], 50.0, places=9)
        self.assertAlmostEqual(out["lcs"].iloc[12], 75.0, places=9)

    def test_ignore_le_futur(self) -> None:
        n = 130 * 24
        x = np.arange(n)
        df1 = _df(100.0 + 30.0 * np.sin(x / 400.0) + x * 0.02)
        df2 = df1.copy()
        coupe = pd.Timestamp("2026-05-01")  # J+120 (2026-01-01 + 120 j)
        mask = df2.index >= coupe
        for c in ("open", "high", "low", "close"):
            df2.loc[mask, c] *= 2.0
        out1 = lcs.symbol_lcs(df1, None)
        out2 = lcs.symbol_lcs(df2, None)
        # La mutation du futur est réelle — sinon l'égalité serait vide.
        apres = out2.index >= coupe
        self.assertFalse(
            out1.loc[apres, "close"].equals(out2.loc[apres, "close"]))
        # Jours où le percentile existe (fenêtre 90 j remplie) et ≤ D :
        # aucune composante ne bouge (tout est rétrograde).
        premier = out1["stretch_sig"].first_valid_index()
        self.assertIsNotNone(premier)
        sel = (out1.index >= premier) & (out1.index < coupe)
        self.assertGreater(int(sel.sum()), 0)
        self.assertTrue(out1.loc[sel, "stretch_sig"].notna().all())
        for col in ("stretch_sig", "dd_sig", "age_sig", "lcs"):
            pd.testing.assert_series_equal(
                out1.loc[sel, col], out2.loc[sel, col], check_names=False)


class TestMain(unittest.TestCase):
    def _db(self, td: Path) -> Path:
        dbp = td / "klines.db"
        con = sqlite3.connect(dbp)
        for stmt in K_SCHEMA:
            con.execute(stmt)
        n = 700  # > 500 requis par main(), ≈ 30 jours
        idx = pd.date_range("2026-05-01", periods=n, freq="1h")
        x = np.arange(n)
        close = 100.0 + x * 0.05 + 5.0 * np.sin(x / 90.0)
        con.executemany(
            "INSERT INTO klines VALUES (?,?,?,?,?,?,?,?)",
            [("TESTUSDT", "1h", int(t.timestamp() * 1000), float(c),
              float(c * 1.01), float(c * 0.99), float(c), 1000.0)
             for t, c in zip(idx, close)])
        t0 = int(pd.Timestamp("2026-05-01").timestamp() * 1000)
        con.executemany(
            "INSERT INTO funding_history VALUES (?,?,?)",
            [("TESTUSDT", t0 + k * 8 * 3_600_000, 0.0001 * (1 + k % 5))
             for k in range(80)])
        con.commit()
        con.close()
        return dbp

    def test_backtest_ecrit_le_rapport(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            dbp = self._db(td)
            reports = td / "reports"
            reports.mkdir()  # en production reports/ existe toujours
            buf = io.StringIO()
            with mock.patch.object(lcs, "KDB", dbp), \
                 mock.patch.object(lcs, "REPORTS", reports), \
                 mock.patch.object(sys, "argv", ["lcs.py"]), \
                 contextlib.redirect_stdout(buf):
                rc = lcs.main()
            self.assertEqual(rc, 0)
            rapports = list(reports.glob("lcs-backtest-*.md"))
            self.assertEqual(len(rapports), 1)
            txt = rapports[0].read_text(encoding="utf-8")
            self.assertIn("# LCS — le score composite", txt)
            self.assertIn("zéro look-ahead", txt)
            self.assertIn("| Décile LCS (hier) | N | WR short 24h | Médiane |",
                          txt)
            self.assertIn("jours×symboles ->", buf.getvalue())

    def test_today_ne_doit_rien_ecrire(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            dbp = self._db(td)
            reports = td / "reports"  # volontairement PAS créé
            buf = io.StringIO()
            with mock.patch.object(lcs, "KDB", dbp), \
                 mock.patch.object(lcs, "REPORTS", reports), \
                 mock.patch.object(sys, "argv", ["lcs.py", "--today"]), \
                 contextlib.redirect_stdout(buf):
                rc = lcs.main()
            self.assertEqual(rc, 0)
            self.assertIn("la carte de chasse du jour", buf.getvalue())
            # le SYMBOLE, pas la date : un f-string {index:14s} sur un
            # Timestamp afficherait « 14s » (format strftime littéral).
            self.assertIn("TESTUSDT", buf.getvalue())
            self.assertIn("LCS 50", buf.getvalue())
            self.assertFalse(reports.exists())


if __name__ == "__main__":
    unittest.main()
