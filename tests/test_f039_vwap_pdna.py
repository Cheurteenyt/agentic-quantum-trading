#!/usr/bin/env python3
"""F-039 — `replace(0, pd.NA)` casse le vwap168 sur fenêtre nulle.

Le bug : `.replace(0, pd.NA)` fait basculer la série en dtype **object**
dès qu'une fenêtre roulante est entièrement nulle, et l'`astype(float)`
qui suit lève

    TypeError: float() argument must be a string or a real number,
    not 'NAType'

C'est pas théorique : 8 symboles de l'univers ont une fenêtre de 168
barres 1h sans volume, donc `confluence_exact.py` (étape BLOQUANTE du
nightly) plantait à chaque run — et en `ExecStart=-`, donc en échec
silencieux.

Le correctif de PR-162 (`paper_forward.py`, `float("nan")`) n'avait pas
été propagé aux deux autres occurrences.

Ces tests vérifient la propriété qui compte : un vwap calculé sur un
volume nul doit donner NaN (comparaison False), jamais une exception.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WINDOW = 168
N = 400


def _df(volume):
    import pandas as pd
    n = len(volume)
    return pd.DataFrame({
        "open": [100.0 + i * 0.01 for i in range(n)],
        "high": [101.0 + i * 0.01 for i in range(n)],
        "low": [99.0 + i * 0.01 for i in range(n)],
        "close": [100.0 + i * 0.02 for i in range(n)],
        "volume": list(volume),
    }, index=pd.date_range("2025-01-01", periods=n, freq="h"))


def _vwap_dev(df):
    """Le motif EXACT des 3 scripts, tel qu'il est écrit."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = ((tp * df["volume"]).rolling(WINDOW).sum()
            / df["volume"].rolling(WINDOW).sum().replace(0, float("nan")))
    return ((df["close"] - vwap) / vwap).astype(float)


class TestVwapSurVolumeNul(unittest.TestCase):
    def test_volume_partiellement_nul(self):
        vol = [0.0] * WINDOW + [1.0e6] * (N - WINDOW)
        dev = _vwap_dev(_df(vol))
        self.assertEqual(str(dev.dtype), "float64")
        self.assertTrue(dev.iloc[WINDOW:].notna().any())

    def test_fenetre_entierement_nulle(self):
        """Le cas réel de la prod : 168 barres à volume nul."""
        vol = [0.0] * 300 + [1.0e6] * (N - 300)
        dev = _vwap_dev(_df(vol))
        self.assertEqual(str(dev.dtype), "float64")
        self.assertTrue(dev.isna().any(), "le dev NaN est attendu")

    def test_tout_nul(self):
        dev = _vwap_dev(_df([0.0] * N))
        self.assertEqual(str(dev.dtype), "float64")
        self.assertTrue(dev.isna().all())

    def test_volume_constant(self):
        """Volume régulier → le vwap est bien défini, le dev est fini."""
        dev = _vwap_dev(_df([1.0e6] * N))
        self.assertEqual(str(dev.dtype), "float64")
        tail = dev.iloc[WINDOW:]
        self.assertTrue(tail.notna().all())
        # la fixture monte de 0,02 %/barre : le close dépasse le vwap, donc
        # le dev est positif et borné — l'invariant est « fini et petit »,
        # pas « nul » (ce serait tester la fixture, pas le code)
        self.assertTrue(0.0 < float(tail.mean()) < 1.0)

    def test_aucune_exception(self):
        """Le vrai régression-test : l'ancien code LEVait une TypeError."""
        for vol in ([0.0] * N, [0.0] * 300 + [1.0e6] * (N - 300),
                    [1.0e6] * N, [0.0] * 200 + [0.0] * 100 + [5.0] * (N - 300)):
            with self.subTest(vol_zeroes=vol.count(0.0)):
                try:
                    _vwap_dev(_df(vol))
                except TypeError as e:       # pragma: no cover
                    self.fail(f"TypeError {e} — le correctif a été perdu")

    def test_pd_na_ferait_echouer(self):
        """Contrôle négatif : on prouve que pd.NA est bien le coupable.

        Si ce test échoue, c'est que pandas a changé de comportement et le
        fix n'est plus nécessaire — mais il reste inoffensif.
        """
        import pandas as pd
        df = _df([0.0] * 300 + [1.0e6] * (N - 300))
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vwap = ((tp * df["volume"]).rolling(WINDOW).sum()
                / df["volume"].rolling(WINDOW).sum().replace(0, pd.NA))
        self.assertEqual(str(vwap.dtype), "object",
                         "pandas ne bascule plus en object : pd.NA n'est "
                         "plus le coupable, le fix peut être reconsidéré")


class TestLesTroisScripts(unittest.TestCase):
    """Le motif a été corrigé dans les 3 scripts — verrou par lecture."""

    FILES = ["scripts/confluence_exact.py", "scripts/signal_ladder.py",
             "scripts/paper_forward.py"]

    def test_aucun_pd_na_dans_les_vwap(self):
        for rel in self.FILES:
            src = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(fichier=rel):
                for i, line in enumerate(src.splitlines(), 1):
                    if "pd.NA" in line and "FIX F-039" not in line \
                            and not line.strip().startswith("#"):
                        self.fail(f"{rel}:{i} : pd.NA hors commentaire → "
                                  f"TypeError sur fenêtre nulle")

    def test_les_trois_ont_la_garde_nan(self):
        for rel in self.FILES:
            src = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(fichier=rel):
                self.assertIn("replace(0, float(\"nan\"))", src)

    def test_stacked_portfolio_aussi(self):
        src = (ROOT / "scripts/stacked_portfolio.py").read_text(encoding="utf-8")
        self.assertIn("replace(0, float(\"nan\"))", src,
                      "le vwap168 de stacked_portfolio n'a pas la garde : "
                      "vwap_dev devient NaN silencieusement pour les "
                      "symboles à volume nul")


if __name__ == "__main__":
    unittest.main()