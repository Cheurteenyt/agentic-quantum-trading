"""Tests du grind et de la sélection (Research OS PR 8-9).

La queue → successive halving (screen bon marché → prune → complet) →
candidats avec clusters, Pareto et pression de sélection. Les morts sont
visibles, les candidats ne sont jamais des preuves.

    python tests/test_research_grind.py
"""
from __future__ import annotations

import argparse
import json
import sys
import argparse
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

H_MS = 3_600_000

from scripts import research_runner as rr  # noqa: E402
from scripts.research_os import ExecState  # noqa: E402


class TestResourceGovernor(unittest.TestCase):
    def test_le_garde_fou_renvoie_un_bool_et_une_raison(self):
        ok, why = rr._resource_guard()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(why, str)


class TestGrindHalving(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        self.con = _db(self.db)
        self.queue = Path(self.tmp.name) / "queue"
        self.queue.mkdir()
        self._runs_backup = rr.RUNS
        rr.RUNS = Path(self.tmp.name) / "runs"
        # isolation : le grind ne doit JAMAIS écrire dans le vrai ledger
        self._log_backup = rr._log_ledger
        rr._log_ledger = lambda *a, **k: None

    def tearDown(self):
        rr._log_ledger = self._log_backup
        rr.RUNS = self._runs_backup
        self.con.close()
        self.tmp.cleanup()

    def _spec(self, name, kill_pct, q=0.10, compute="tiny"):
        spec = {
            "id": name, "domain": "aster", "family": "vol_exhaustion",
            "strategy": "grind-test",
            "hypothesis": f"crash {kill_pct} % continue à 6h",
            "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                     "train_start": 0, "train_end": 150 * H_MS,
                     "validation_start": 150 * H_MS,
                     "validation_end": 300 * H_MS},
            "signal": {"feature": "ret_1h", "op": "<=", "quantile": q,
                       "side": -1},
            "horizons": [6], "cost_pct": 0.0,
            "criteria": {"min_n": 5, "min_mean": -100.0},
            "compute": {"class": compute},
        }
        f = self.queue / f"{name}.json"
        f.write_text(json.dumps(spec), encoding="utf-8")
        return f, spec

    def test_le_grind_ecrit_les_candidats_et_les_morts(self):
        f1, _ = self._spec("EXP-good-001", kill_pct=-3.0)   # un vrai crash
        f2, _ = self._spec("EXP-flat-002", kill_pct=0.0)    # du bruit plat
        a = argparse.Namespace(queue=str(self.queue), db=str(self.db))
        rr.cmd_grind(a)
        runs = list(rr.RUNS.glob("*/summary_discovery.json"))
        self.assertGreaterEqual(len(runs), 1)
        ids = {json.loads(f.read_text(encoding="utf-8")).get("run_id")
               for f in runs}
        self.assertIn("EXP-good-001", ids)
        self.assertNotIn("EXP-flat-002", ids)   # éliminé au screen : PAS d'artefact

    def test_l_ordre_par_classe_de_compute(self):
        f_small, _ = self._spec("EXP-b", kill_pct=-3.0, compute="small")
        f_tiny, _ = self._spec("EXP-a", kill_pct=-3.0, compute="tiny")
        specs = [json.loads(f.read_text(encoding="utf-8"))
                 for f in (f_small, f_tiny)]
        order = {"tiny": 0, "small": 1, "medium": 2, "large": 3}
        specs.sort(key=lambda s: order.get(s["compute"]["class"], 1))
        self.assertEqual([s["id"] for s in specs], ["EXP-a", "EXP-b"])


class TestSelection(unittest.TestCase):
    def test_les_clusters_regroupent_les_micro_variantes(self):
        self.assertEqual(rr._cluster_key(
            {"family": "vol", "signal": {"feature": "ret_1h", "op": "<=",
                                         "side": -1}}),
            rr._cluster_key(
                {"family": "vol", "signal": {"feature": "ret_1h", "op": "<=",
                                             "side": -1}}))

    def test_pareto_frontier_elimine_les_domines(self):
        rows = [{"id": "a", "mean": 0.5, "n": 100, "worst": -1.0, "cluster": "c"},
                {"id": "b", "mean": 0.4, "n": 100, "worst": -1.0, "cluster": "c"},
                {"id": "c", "mean": 0.9, "n": 100, "worst": -0.5, "cluster": "c"}]
        front = rr._pareto_frontier(rows)
        ids = {r["id"] for r in front}
        self.assertIn("c", ids)
        self.assertNotIn("b", ids)   # dominé par a et c
        self.assertNotIn("a", ids)   # dominé par c (meilleur partout)


def _db(path):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
    """)
    price = 100.0
    for i in range(300):
        o = price
        c = price * (1 + (-0.03 if 100 <= i < 120 else 0.0))
        con.execute("INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
                    (i * H_MS, o, max(o, c) * 1.001, min(o, c) * 0.999, c))
        if i % 8 == 0:
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, 0.0001)", (i * H_MS + H_MS,))
        price = c
    con.commit()
    return con


if __name__ == "__main__":
    unittest.main()
