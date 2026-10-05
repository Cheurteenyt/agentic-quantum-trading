"""Tests du fast research kernel (Research OS PR 4) — la matrice de labels.

Le contrat : des barres synthétiques dont l'avenir est CONNU par
construction → les labels doivent être exacts, le cache doit être stable,
et le futur doit être NaN (jamais fabriqué).

    python tests/test_label_matrix.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.label_matrix import (  # noqa: E402
    HORIZONS, event_study, label_hash, snapshot_id)

H_MS = 3_600_000


def _db(path, n=60, ramp=0.0):
    """Des barres 1h déterministes : close monte de `ramp` %/barre."""
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
    """)
    price = 100.0
    for i in range(n):
        o = price
        c = price * (1 + ramp / 100.0)
        # mèches symétriques connues : high = max(o,c) × 1.01, low = min × 0.99
        hi = max(o, c) * 1.01
        lo = min(o, c) * 0.99
        con.execute("INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
                    (i * H_MS, o, hi, lo, c))
        price = c
    con.commit()
    return con


class TestLabels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        self.con = _db(self.db, n=60, ramp=1.0)   # +1 %/barre

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_ret_H_exact_sur_une_rampue_connu(self):
        from scripts.label_matrix import build_matrix
        lh, mat = build_matrix(["BTCUSDT"], horizons=(2, 6), db_path=self.db,
                               use_cache=False)
        cols = mat["BTCUSDT"]
        # ramp 1 %/barre, convention close(i+H-1)/open(i) :
        # ret_2[0] = close(1)/open(0) = 1.01² - 1 ≈ 2.01 %
        self.assertAlmostEqual(cols["ret_2"][0], ((1.01) ** 2 - 1) * 100,
                               places=9)
        self.assertAlmostEqual(cols["ret_6"][10], ((1.01) ** 6 - 1) * 100,
                               places=9)

    def test_hi_lo_meches_exactes(self):
        from scripts.label_matrix import build_matrix
        _, mat = build_matrix(["BTCUSDT"], horizons=(2,), db_path=self.db,
                              use_cache=False)
        cols = mat["BTCUSDT"]
        # hi_2[0] = max(high[0..1])/open[0] - 1 : la fixture fabrique
        # high = max(open, close) × 1.01 → high[0] = 101×1.01 = 102.01,
        # high[1] = 102.01×1.01 = 103.0301 → le max / 100 - 1 :
        self.assertAlmostEqual(cols["hi_2"][0], 103.0301 / 100 - 1, places=9)
        self.assertAlmostEqual(cols["lo_2"][0], 99.0 / 100 - 1, places=9)

    def test_le_futur_inexistant_est_nan_jamais_fabrique(self):
        """v8 (GLM 5.3 №24) : le DERNIER event H (i = n-H) est VALIDE — il
        dispose encore des H barres i..n-1 ; seul ce qui dépasse est NaN."""
        from scripts.label_matrix import build_matrix
        _, mat = build_matrix(["BTCUSDT"], horizons=(6,), db_path=self.db,
                              use_cache=False)
        cols = mat["BTCUSDT"]
        n = len(cols["ret_6"])
        self.assertTrue(np.isnan(cols["ret_6"][n - 1]))
        self.assertFalse(np.isnan(cols["ret_6"][n - 6]))   # valide depuis v8
        self.assertTrue(np.isnan(cols["ret_6"][n - 5]))    # au-delà : NaN
        self.assertFalse(np.isnan(cols["ret_6"][0]))

    def test_le_funding_est_la_somme_des_prints_de_la_fenetre(self):
        # 3 prints de 0,01 % aux heures 1, 2, 3 : un hold de 3h depuis h0
        # encaisse (short) 0.03 %
        self.con.executemany(
            "INSERT INTO funding_history VALUES ('BTCUSDT', ?, 0.0001)",
            [(1 * H_MS,), (2 * H_MS,), (3 * H_MS,)])
        self.con.commit()   # sinon l'autre connexion ne voit pas les prints
        from scripts.label_matrix import build_matrix
        _, mat = build_matrix(["BTCUSDT"], horizons=(3,), db_path=self.db,
                              use_cache=False)
        self.assertAlmostEqual(mat["BTCUSDT"]["fund_3"][0], 0.03, places=9)

    def test_le_cache_est_stable_et_invalide_par_horizons(self):
        from scripts.label_matrix import build_matrix
        lh1, _ = build_matrix(["BTCUSDT"], horizons=(6,), db_path=self.db)
        lh2, _ = build_matrix(["BTCUSDT"], horizons=(6,), db_path=self.db)
        self.assertEqual(lh1, lh2)                      # recharger = même hash
        lh3, _ = build_matrix(["BTCUSDT"], horizons=(12,), db_path=self.db)
        self.assertNotEqual(lh1, lh3)                   # autres horizons = autre hash


class TestEventStudy(unittest.TestCase):
    def _cols(self):
        n = 50
        cols = {"open_time_ns": np.arange(n) * H_MS * 10**6,
                "entry": np.full(n, 100.0)}
        for H in (6,):
            ret = np.full(n, np.nan)
            ret[:n - H] = 1.0                       # +1 % de prix partout
            cols[f"ret_{H}"] = ret
            cols[f"hi_{H}"] = np.where(np.arange(n) < n - H, 3.0, np.nan)
            cols[f"lo_{H}"] = np.where(np.arange(n) < n - H, -0.5, np.nan)
            cols[f"fund_{H}"] = np.where(np.arange(n) < n - H, 0.02, np.nan)
        return cols

    def test_le_cote_position_est_applique(self):
        mask = np.zeros(50, dtype=bool)
        mask[: 50 - 6] = True
        short = event_study(self._cols(), mask, 6, side=-1, cost_pct=0.28)
        lng = event_study(self._cols(), mask, 6, side=1, cost_pct=0.28)
        # prix +1 % : le LONG gagne 1 %, le SHORT perd 1 % (funding 0.02 :
        # le short encaisse, le long paie)
        self.assertAlmostEqual(short["mean"], -1.0 + 0.02 - 0.28, places=9)
        self.assertAlmostEqual(lng["mean"], 1.0 - 0.02 - 0.28, places=9)

    def test_les_stats_conditionnelles_ne_voient_pas_le_futur_du_masque(self):
        cols = self._cols()
        mask_full = np.ones(50, dtype=bool)
        mask_trunc = mask_full.copy()
        mask_trunc[40:] = False
        a = event_study(cols, mask_full, 6, side=-1, cost_pct=0.28)
        b = event_study(cols, mask_trunc, 6, side=-1, cost_pct=0.28)
        self.assertEqual(b["n"], a["n"] - sum(1 for i in range(40, 50)
                                              if i < 50 - 6))
        self.assertAlmostEqual(a["mean"], b["mean"], places=12)  # ordre de somme numpy

    def test_masque_vide(self):
        mask = np.zeros(50, dtype=bool)
        self.assertEqual(event_study(self._cols(), mask, 6, side=-1)["n"], 0)


if __name__ == "__main__":
    unittest.main()
