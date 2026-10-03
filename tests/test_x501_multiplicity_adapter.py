from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts/studies/x501_openmarket/x501_multiplicity_adapter.py"


def load():
    spec = importlib.util.spec_from_file_location("x501_multiplicity_adapter", ADAPTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AdapterTests(unittest.TestCase):
    def test_imports_and_reproduces_the_audited_numbers(self):
        m = load()
        out = m.analyze(m.load_trades(m.DEFAULT_TRADES), n_total=362)
        pool = dict(out["rows"])["POOL"]
        self.assertEqual(pool["n"], 868)
        self.assertAlmostEqual(pool["mean_R"], 0.0925, places=3)
        self.assertAlmostEqual(pool["t_iid"], 2.31, delta=0.02)
        self.assertAlmostEqual(pool["t_blocs"], 1.49, delta=0.03)
        self.assertEqual(out["bonf"].survivors, [], "à N=362 aucun test ne doit survivre à Bonferroni")
        self.assertAlmostEqual(out["z_star"], 3.64, delta=0.02)

    def test_main_runs(self):
        self.assertEqual(load().main([]), 0)


if __name__ == "__main__":
    unittest.main()
