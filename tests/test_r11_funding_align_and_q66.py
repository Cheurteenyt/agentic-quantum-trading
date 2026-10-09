#!/usr/bin/env python3
"""Ronde 11 — le reindex funding nu crashait (NULL/dup) et muent en silence (s vs ms),
et le gate q66 de confluence_exact regardait 70 % d'histoire FUTURE (C-B3).

Trois scripts (signal_ladder, confluence_exact, backtest_indicators) faisaient :

    rate = fh_sym.set_index("funding_time")["rate"].astype(float).sort_index()
    rate.index = pd.to_datetime(rate.index, unit="ms")
    aligned = rate.reindex(df.index, method="ffill", limit=8)

Poisons réels de funding_history :
  1. funding_time NULL -> NaT -> reindex(pad) exige un index monotone :
     ValueError (reproduit).
  2. (symbol, funding_time) dupliqué -> « cannot reindex on an axis with
     duplicate labels » (reproduit ; PR-166 documente des prints à +1..17 ms
     de l'heure pile : deux lignes par heure après troncature).
  3. unité s assumée ms : dates 1970 -> diff(3) NaN -> accel muette en
     SILENCE (anti_liq.py:93 et stacked_portfolio.py:91 insèrent en s).

Le look-ahead C-B3 : `q66 = quantile(cascade[:70%])` appliqué à TOUS les
events — le sizing au temps t voyait jusqu'à 70 % d'histoire future. Corrigé
dans stacked_portfolio (stamp_expanding_q66), VIVANT dans confluence_exact.

Tests hermétiques : aucune base, aucun réseau. La contre-preuve (l'ancien
code crashait bien) est exécutée contre la logique d'origine réécrite
localement — c'est la mutation négative du motif.
"""
from __future__ import annotations

import ast
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scripts.funding_align import align_funding_rate  # noqa: E402

IDX = pd.date_range("2024-01-01", periods=48, freq="1h")
BASE_MS = 1_704_067_200_000          # 2024-01-01 00:00 UTC en ms
RATES = [0.0001, 0.0002, 0.0003, 0.0004, 0.0005, 0.0006]


def _saine() -> pd.DataFrame:
    return pd.DataFrame({
        "funding_time": [BASE_MS + i * 8 * 3_600_000 for i in range(6)],
        "rate": RATES,
    })


def _ancien_code(fh_sym: pd.DataFrame, target_index) -> pd.Series:
    """L'ancien motif NU, réécrit ici pour la contre-preuve (mutation)."""
    rate = fh_sym.set_index("funding_time")["rate"].astype(float).sort_index()
    rate.index = pd.to_datetime(rate.index, unit="ms")
    return rate.reindex(target_index, method="ffill", limit=8)


class TestAlignFundingRate(unittest.TestCase):
    def test_saine_identique_a_l_ancien_code(self):
        """Contrat : sur une entrée saine, le helper est BIT-À-BIT l'ancien."""
        pd.testing.assert_series_equal(
            align_funding_rate(_saine(), IDX, limit=8),
            _ancien_code(_saine(), IDX))

    def test_null_ne_crash_pas_et_est_exclu(self):
        """Poison 1 : une ligne funding_time NULL levait ValueError."""
        fh = pd.DataFrame({
            "funding_time": [None] + [BASE_MS + i * 8 * 3_600_000
                                      for i in range(6)],
            "rate": [0.0009] + RATES,
        })
        got = align_funding_rate(fh, IDX, limit=8)
        self.assertFalse(got.isna().all(), "tout NaN : la ligne NULL a tout tué")
        # contre-preuve : l'ancien code crashait bien (mutation du motif)
        with self.assertRaises(ValueError):
            _ancien_code(fh, IDX)

    def test_doublons_ne_crash_pas_premier_gagnant(self):
        """Poison 2 : des prints à ±ms de l'heure -> labels dupliqués."""
        ft = [BASE_MS, BASE_MS + 17, BASE_MS + 2 * 8 * 3_600_000]
        fh = pd.DataFrame({"funding_time": ft * 2,
                           "rate": RATES[:3] * 2})
        got = align_funding_rate(fh, IDX, limit=8)
        # premier-gagnant : le rate de BASE_MS+17 est ignoré
        k = got.index.get_indexer([pd.Timestamp(BASE_MS, unit="ms")])[0]
        self.assertEqual(float(got.iloc[k]), RATES[0])
        with self.assertRaises(ValueError):
            _ancien_code(fh, IDX)

    def test_secondes_converties_ms(self):
        """Poison 3 : un flux en secondes ne doit pasdater en 1970."""
        fh_s = pd.DataFrame({
            "funding_time": [BASE_MS // 1000 + i * 8 * 3600 for i in range(6)],
            "rate": RATES,
        })
        pd.testing.assert_series_equal(
            align_funding_rate(fh_s, IDX, limit=8),
            _ancien_code(_saine(), IDX))

    def test_tout_null_serie_vide_sans_crash(self):
        fh = pd.DataFrame({"funding_time": [None, None],
                           "rate": [0.0001, 0.0002]})
        got = align_funding_rate(fh, IDX, limit=8)
        self.assertEqual(len(got), len(IDX))   # alignée, tout NaN


class TestEnrichSurvitAuxPoisons(unittest.TestCase):
    """Integration : signal_ladder.enrich sur une DB synthétique.

    Reproduit le crash ronde 11 : une seule ligne funding_history avec
    funding_time NULL faisait mourir `enrich` (reindex pad non monotone).
    """

    def _db(self, funding_time_col):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "k.db"
        con = sqlite3.connect(p)
        con.execute(
            "CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)")
        base = 1_700_000_000_000 - 400 * 3_600_000   # 400 bougies avant
        rows = []
        px = 100.0
        for i in range(400):
            px *= 1.0 + (i % 7 - 3) / 5000.0
            t = base + i * 3_600_000
            rows.append(("BTCUSDT", "1h", t, px, px * 1.001, px * 0.999,
                         px, 1000.0 + i))
        con.executemany("INSERT INTO klines VALUES (?,?,?,?,?,?,?,?)", rows)
        con.execute(
            "CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, "
            "rate REAL)")
        frows = [("BTCUSDT", funding_time_col(i), 0.0001 + i / 10_000)
                 for i in range(6)]
        con.executemany("INSERT INTO funding_history VALUES (?,?,?)", frows)
        con.commit()
        return con, rows

    def test_enrich_survit_a_une_ligne_null(self):
        import scripts.signal_ladder as sl
        con, rows = self._db(
            lambda i: None if i == 3 else BASE_MS + i * 8 * 3_600_000)
        events = [{"sym": "BTCUSDT", "ts_ms": rows[350][2],
                   "price_ret_short": 0.4, "al_score": 1.0}]
        got = sl.enrich(con, events)          # AVANT : ValueError
        self.assertEqual(len(got), 1)
        self.assertIn("funding_accel", got[0])
        con.close()

    def test_enrich_survit_aux_doublons(self):
        import scripts.signal_ladder as sl
        con, rows = self._db(
            lambda i: BASE_MS + (i // 2) * 8 * 3_600_000)   # 3 heures x2
        events = [{"sym": "BTCUSDT", "ts_ms": rows[350][2],
                   "price_ret_short": 0.4, "al_score": 1.0}]
        got = sl.enrich(con, events)          # AVANT : ValueError
        self.assertEqual(len(got), 1)
        con.close()


class TestQ66ExpandingConfluenceExact(unittest.TestCase):
    """C-B3 dans confluence_exact : le scalaire 70 % est INTERDIT."""

    def test_source_sans_le_scalaire_lookahead(self):
        src = (ROOT / "scripts" / "confluence_exact.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        # 1) le motif de la mutation : int(len(cascade) * 0.7)
        for node in ast.walk(tree):
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)):
                for operand in (node.left, node.right):
                    if (isinstance(operand, ast.Constant)
                            and operand.value == 0.7):
                        self.fail("scalaire 0.7 (look-ahead C-B3) de retour")
        # 2) le branchement : le stamp et le seuil par event sont présents
        self.assertIn("stamp_expanding_q66", src)
        self.assertIn('_q66_asof', src)

    def test_warmup_puis_seuil_expanding(self):
        """Dynamique : le stamp colle un seuil NaN pendant le warm-up."""
        from scripts.stacked_portfolio import stamp_expanding_q66
        evs = [{"ts_ms": 1_700_000_000_000 + i * 3_600_000,
                "al_score": float(i % 10), "strategy": "cascade"}
               for i in range(40)]
        stamped, last = stamp_expanding_q66(evs, min_hist=30)
        # les 30 premiers (pas d'histoire suffisante) : NaN -> pas gaté
        self.assertTrue(all(np.isnan(e["_q66_asof"]) for e in stamped[:30]))
        # à partir de 30 : un seuil FINI, ne voyant que le passé
        self.assertTrue(np.isfinite(stamped[30]["_q66_asof"]))
        self.assertTrue(np.isfinite(last))

    def test_labels_2_jambes_et_morts_purges(self):
        """Le header honnête + les variables mortes supprimées."""
        src = (ROOT / "scripts" / "confluence_exact.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertNotIn("accel_only", names, "variable morte de retour")
        # « funding accel + prix » = 3 jambes annoncées pour un masque à 2
        self.assertNotIn("funding accel + prix", src)
        # le masque réel reste à 2 jambes, bien branché
        self.assertIn("accel & (dev > 3 * dev.rolling(168).std())", src)


class TestSignalLadderSansQ66Mort(unittest.TestCase):
    def test_source_sans_le_q66_mort(self):
        src = (ROOT / "scripts" / "signal_ladder.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)):
                for operand in (node.left, node.right):
                    if (isinstance(operand, ast.Constant)
                            and operand.value == 0.7):
                        self.fail("le q66 (mort ET look-ahead) est de retour")


class TestBacktestIndicatorsBranche(unittest.TestCase):
    def test_source_utilise_le_helper(self):
        src = (ROOT / "scripts" / "backtest_indicators.py").read_text(
            encoding="utf-8")
        self.assertIn("align_funding_rate", src)
        # l'ancien bloc nu est parti : plus de set_index funding_time nu
        self.assertNotIn('set_index("funding_time")["rate"]', src)


if __name__ == "__main__":
    unittest.main()
