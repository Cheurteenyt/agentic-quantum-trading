"""LE PLACEBO — le vrai run_discovery sur une marche aléatoire pure.

Tout DISCOVERY_PASS sur ce bruit est un look-ahead résiduel ou un gate
sous le bruit (B4, audit Sonnet 5.5). Les 4 specs de référence sont les
mêmes que l'audit : elles PASSaient 4/4 avant le fix de causalité PR-143,
elles doivent FAIL 4/4 pour toujours.

    python tests/test_placebo_random_walk.py
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_runner as RR  # noqa: E402

H1 = 3_600_000
T0 = 1609459200000
N_BARS = 8000
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
REF_SPECS = ["EXP-crash-short-6h-004", "EXP-bonsai-h-01",
             "EXP-bonsai-h-18", "EXP-bonsai-h-25"]


def _make_rw_db(db: Path) -> None:
    """Une marche aléatoire pure : AUCUN edge possible par construction."""
    rng = np.random.default_rng(23)
    con = sqlite3.connect(db)
    con.execute("create table klines(symbol text, interval text, "
                "open_time integer, open real, high real, low real, "
                "close real, volume real)")
    con.execute("create table funding_history(symbol text, "
                "funding_time integer, rate real)")
    for s in SYMS:
        c = 100 * np.exp(np.cumsum(rng.standard_t(5, N_BARS) * 0.0045))
        o = np.concatenate(([100.0], c[:-1]))
        con.executemany(
            "insert into klines values (?,?,?,?,?,?,?,?)",
            [(s, "1h", T0 + i * H1, float(o[i]), float(max(o[i], c[i]) * 1.001),
              float(min(o[i], c[i]) * 0.999), float(c[i]),
              float(rng.lognormal(5, .5))) for i in range(N_BARS)])
        con.executemany(
            "insert into funding_history values (?,?,?)",
            [(s, T0 + k * 8 * H1, float(rng.normal(1e-4, 3e-4)))
             for k in range(N_BARS // 8)])
    con.commit()
    con.close()


class TestPlaceboRandomWalk(unittest.TestCase):
    def test_zero_pass_sur_bruit_pur(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "k.db"
            _make_rw_db(db)
            n_pass = n_run = 0
            for sid in REF_SPECS:
                hits = glob.glob(f"{ROOT}/research/**/{sid}.json",
                                 recursive=True)
                if not hits:
                    continue          # spec absente : pas une erreur de placebo
                sp = json.loads(Path(hits[0]).read_text(encoding="utf-8"))
                sp["data"].update({
                    "symbols": list(SYMS), "train_start": T0,
                    "train_end": T0 + N_BARS * H1,
                    "validation_start": T0 + N_BARS * H1,
                    "validation_end": T0 + N_BARS * H1 + 1})
                sp.pop("universe", None)
                sp["data"].pop("universe", None)
                with contextlib.redirect_stdout(io.StringIO()):
                    r = RR.run_discovery(sp, db_path=db)
                n_run += 1
                n_pass += r["verdict"] == "DISCOVERY_PASS"
            self.assertGreaterEqual(n_run, 3,
                                    "les specs de référence sont introuvables")
            self.assertEqual(
                n_pass, 0,
                "DISCOVERY_PASS sur marche aléatoire pure — look-ahead "
                "résiduel ou gate sous le bruit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
