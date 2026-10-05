"""Tests du research_runner (Research OS PR 6) — la porte unique end-to-end.

Le parcours complet sur des fixtures : une spec YAML (masque causal sur une
feature connue), discovery sur la vue TRAIN, confirm sur la validation (slot
consommé), les artefacts (spec_sha, manifest, summary), et la violation de
scope si discovery tente de sortir du TRAIN.

    python tests/test_research_runner.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_runner as rr  # noqa: E402
from scripts.research_os import DataScope, ScopeViolation  # noqa: E402

H_MS = 3_600_000


def _db(path, n=300, kill_pct=-3.0, from_bar=100):
    """Des barres 1h déterministes : plat, puis un crash de `kill_pct` %/barre
    pendant 20 barres à partir de `from_bar` (un event study doit le voir)."""
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
    """)
    price = 100.0
    for i in range(n):
        o = price
        c = price * (1 + kill_pct / 100.0 if from_bar <= i < from_bar + 20 else 1.0)
        hi = max(o, c) * 1.001
        lo = min(o, c) * 0.999
        con.execute("INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
                    (i * H_MS, o, hi, lo, c))
        if i % 8 == 0:   # un print de funding toutes les 8 barres (couverture)
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, 0.0001)", (i * H_MS + H_MS,))
        price = c
    con.commit()
    return con


def _spec(tmp, db, train_end_bar=150):
    spec = {
        "id": "EXP-test-001",
        "domain": "aster",
        "family": "volatility_exhaustion",
        "strategy": "runner-test",
        "hypothesis": "un crash aigu prolongé continue de baisser à court terme",
        "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                 "train_start": 0, "train_end": train_end_bar * H_MS,
                 "validation_start": train_end_bar * H_MS,
                 "validation_end": 300 * H_MS},
        "signal": {"feature": "ret_1h", "op": "<=", "quantile": 0.10, "side": -1},
        "horizons": [6],
        "cost_pct": 0.0,
        "criteria": {"min_n": 5, "min_mean": -100.0},
        "mode": "discovery",
    }
    sp = Path(tmp) / "EXP-test-001.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    return sp, spec


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        self.con = _db(self.db)
        self.spec_path, self.spec = _spec(self.tmp.name, self.db)
        self._runs_backup = rr.RUNS
        rr.RUNS = Path(self.tmp.name) / "runs"

    def tearDown(self):
        rr.RUNS = self._runs_backup
        self.con.close()
        self.tmp.cleanup()

    def test_discovery_produit_verdict_et_artefacts(self):
        res = rr.run_discovery(self.spec, db_path=self.db)
        self.assertIn(res["verdict"], ("DISCOVERY_PASS", "DISCOVERY_FAIL"))
        self.assertGreater(res["n"], 0)
        self.assertIn("label_hash", res)
        rdir = rr.write_artifacts(self.spec["id"], self.spec, res, "discovery",
                                  db_path=self.db)
        self.assertTrue((rdir / "manifest.json").exists())
        self.assertTrue((rdir / "spec.json").exists())
        s = json.loads((rdir / "summary_discovery.json").read_text(encoding="utf-8"))
        self.assertEqual(s["spec_sha"], rr.spec_sha(self.spec))

    def test_le_seuil_expanding_est_causal(self):
        """Un trade ancien ne connaît pas la distribution future : le seuil
        à la barre i ne dépend que des barres ≤ i (leçon C10)."""
        fvals = np.full(300, 1.0)
        fvals[100:120] = -5.0          # le crash
        thr = rr.expanding_threshold(fvals, 0.10)
        self.assertTrue(np.isnan(thr[:50]).all())
        # à la barre 200 (après le crash), le seuil intègre les -5 :
        self.assertLess(thr[200], thr[60])

    def test_confirm_consomme_un_slot_et_juge_la_validation(self):
        res = rr.run_discovery(self.spec, db_path=self.db)
        res2 = rr.run_confirmation(self.spec, db_path=self.db)
        self.assertEqual(res2["slots_consumed"], 1)
        self.assertIn(res2["verdict"], ("CONFIRMED", "REJECTED"))
        self.assertEqual(res2["validation_window"][0], 150 * H_MS)

    def test_discovery_ne_voit_jamais_la_validation(self):
        """La vue discovery borne les requêtes au TRAIN — sortir = violation."""
        scope = DataScope("EXP", 0, 150 * H_MS, 150 * H_MS, 300 * H_MS)
        v = scope.discovery_view()
        with self.assertRaises(ScopeViolation):
            v.assert_range(0, 200 * H_MS)

    def test_preflight_failed_zero_slot(self):
        """Un schéma cassé (la leçon open_time) → PREFLIGHT_FAILED, 0 slot."""
        self.con.executescript("DROP TABLE klines; CREATE TABLE klines (ts INTEGER);")
        self.con.commit()
        res = rr.run_confirmation(self.spec, db_path=self.db)
        self.assertEqual(res["verdict"], "PREFLIGHT_FAILED")
        self.assertEqual(res["slots_consumed"], 0)


if __name__ == "__main__":
    unittest.main()
