"""Tests v16 — les invariants de recherche (audit GLM 5.3 post-#147).

    python tests/test_v16_integrity.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_runner as rr  # noqa: E402
from scripts.lab_ledger import (  # noqa: E402
    confirmation_multiplicity, norm_text, sha)
from scripts.research_os import UniverseViolation  # noqa: E402
from scripts.label_matrix import build_matrix  # noqa: E402
from scripts.universe import tradable_window_ms  # noqa: E402

H = 3_600_000


def _db(path, n=200):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
        rate REAL);
    """)
    price = 100.0
    for i in range(n):
        c = price * (0.97 if 100 <= i < 120 else 1.0)
        con.execute("INSERT INTO klines VALUES "
                    "('BTCUSDT','1h',?,100.0,?,?,?,1.0)",
                    (i * H, max(price, c) * 1.001,
                     min(price, c) * 0.999, c))
        price = c
    con.commit()
    return con


SPEC = {"id": "X", "data": {"symbols": ["BTCUSDT"]},
        "signal": {"conditions": [
            {"feature": "ret_1h", "op": "<=", "threshold": -1.0}],
            "side": -1},
        "horizons": [6], "cost_pct": 0.0}


class TestUniverseFailClosed(unittest.TestCase):
    def _feats(self, db):
        con = sqlite3.connect(db)
        f = rr.compute_features(con, "BTCUSDT", db_path=db)
        con.close()
        return f

    def test_manifest_absent_leve(self):
        """FAIL-CLOSED : un univers DÉCLARÉ mais introuvable lève — jamais
        « continue sans contrainte » (l'ancien fail-open annulait la
        protection qu'on venait d'installer)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = _db(db)
            con.close()
            feats = self._feats(db)
            spec = {**SPEC, "universe": "inexistant"}
            view = rr.DataView("t", "train", 0, 300 * H)
            with self.assertRaises(UniverseViolation):
                rr.apply_universe(spec, "BTCUSDT",
                                  np.ones(300, dtype=bool), feats, 6)

    def test_symbole_absent_leve(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = _db(db)
            con.close()
            feats = self._feats(db)
            manifest = {"symbols": {"ETHUSDT": {
                "observed_start": "1970-01-01",
                "first_bar_ms": 0, "last_bar_ms": 300 * H}}}
            mfile = Path(tmp) / "universe" / "u.yaml"
            mfile.parent.mkdir(parents=True)
            mfile.write_text(json.dumps(manifest), encoding="utf-8")
            spec = {**SPEC, "universe": "u"}
            import scripts.universe as uni
            saved = uni.UNIVERSE_DIR
            uni.UNIVERSE_DIR = mfile.parent
            try:
                with self.assertRaises(UniverseViolation):
                    rr.apply_universe(spec, "BTCUSDT",
                                      np.ones(300, dtype=bool), feats, 6)
            finally:
                uni.UNIVERSE_DIR = saved


class TestUniversePerHorizon(unittest.TestCase):
    def test_multi_horizon_respecte_le_span(self):
        """№3 : l'univers est appliqué PAR HORIZON — une entrée à h=80 avec
        un univers finissant à h=106 passe pour H=6 mais PAS pour H=24
        (l'ancien horizons[0] laissait le H=72/24 sortir)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = _db(db, n=120)
            con.close()
            feats_db = sqlite3.connect(db)
            feats = rr.compute_features(feats_db, "BTCUSDT", db_path=db)
            feats_db.close()
            manifest = {"symbols": {"BTCUSDT": {
                "observed_start": "1970-01-01",
                "first_bar_ms": 0,
                "last_bar_ms": 106 * H + H,   # les données vont jusqu'à 107h
                "bars": 107}}}
            mfile = Path(tmp) / "universe" / "u.yaml"
            mfile.parent.mkdir(parents=True)
            mfile.write_text(json.dumps(manifest), encoding="utf-8")
            spec = {**SPEC, "universe": "u"}
            import scripts.universe as uni
            saved = uni.UNIVERSE_DIR
            uni.UNIVERSE_DIR = mfile.parent
            try:
                ones = np.ones(120, dtype=bool)
                m6 = rr.apply_universe(spec, "BTCUSDT", ones, feats, 6)
                m24 = rr.apply_universe(spec, "BTCUSDT", ones, feats, 24)
                # une entrée à h=80 : +6h = 86 ≤ 107 ✓ ; +24h = 104 ≤ 107 ✓
                # — prenons h=100 : +6h=106 ✓ ; +24h=124 ✗
                self.assertTrue(m6[100])
                self.assertFalse(m24[100])
            finally:
                uni.UNIVERSE_DIR = saved


class TestFundingHole(unittest.TestCase):
    def test_fenetre_ge_sans_print_dans_un_trou_est_inconnue(self):
        """№4 : prints à h0 et h24 (trou de 24h vs intervalle attendu) —
        une fenêtre H=6 dans le trou sans AUCUN print est INCONNUE (un
        print aurait dû exister), pas « 0 connu »."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = sqlite3.connect(db)
            con.executescript("""
            CREATE TABLE klines (symbol TEXT, interval TEXT,
                open_time INTEGER, open REAL, high REAL, low REAL,
                close REAL, volume REAL);
            CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
                rate REAL);
            """)
            for i in range(60):
                con.execute("INSERT INTO klines VALUES "
                            "('BTCUSDT','1h',?,100,101,99,100,1.0)",
                            (i * H,))
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, 0.0001)", (1 * H,))
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, 0.0001)", (25 * H,))
            con.commit()
            con.close()
            _, mat = build_matrix(["BTCUSDT"], (6,), db_path=db,
                                  use_cache=False)
            f = mat["BTCUSDT"]["fund_6"]
            self.assertFalse(np.isnan(f[0]))    # fenêtre 0-6h ⊆ ère, print
            self.assertTrue(np.isnan(f[20]))    # 20-26h : dans le trou 1-25h
            self.assertTrue(np.isnan(f[40]))    # 40-46h : trou aussi


class TestSnapshotDb(unittest.TestCase):
    def test_le_precheck_utilise_la_db_du_run(self):
        """№1 : le snapshot du pré-check = celui de la DB du run — un --db
        custom produit un snapshot différent du warehouse."""
        from scripts.label_matrix import snapshot_id
        with tempfile.TemporaryDirectory() as tmp:
            dbA = Path(tmp) / "A.db"
            con = _db(dbA, n=100)
            con.close()
            dbB = Path(tmp) / "B.db"
            con = _db(dbB, n=110)
            con.close()
            self.assertNotEqual(snapshot_id(dbA), snapshot_id(dbB))
            # le pré-check reçoit bien la db du run (capture des args)
            captured = {}
            import scripts.research_runner as rr
            real_run = rr.subprocess.run

            def fake_run(cmd, **kw):
                captured["cmd"] = cmd
                return real_run(cmd, **kw)
            rr.subprocess.run = fake_run
            try:
                spec = {"family": "f", "strategy": "s", "hypothesis": "h"}
                ok, _ = rr._budget_precheck(spec, db_path=dbA)
            finally:
                rr.subprocess.run = real_run
            self.assertIn(str(snapshot_id(dbA)),
                          " ".join(captured["cmd"]))


class TestMultiplicity(unittest.TestCase):
    def test_une_seule_definition(self):
        """№6 : le N de multiplicité exclut les discoveries ET les PREREG —
        la même fonction pour le STATE et le checker."""
        entries = [{"verdict": "PASS", "_mode": "confirmation"},
                   {"verdict": "FAIL", "_mode": "confirmation"},
                   {"verdict": "DISCOVERY_FAIL", "_mode": "discovery"},
                   {"verdict": "PREREG", "_mode": "confirmation"}]
        self.assertEqual(confirmation_multiplicity(entries), 2)


if __name__ == "__main__":
    unittest.main()
