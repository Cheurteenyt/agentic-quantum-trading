"""Tests v15 — l'intégrité des contrôles autour du moteur (audit GLM 5.3
post-#146) : REPLICATION ≠ REVERIFY, funding forward couvert, garde collect,
univers au forward, précision ms de l'univers.

    python tests/test_v15_integrity.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_forward as rf  # noqa: E402
from scripts.lab_ledger import assess, norm_text, sha  # noqa: E402
from scripts.universe import tradable_window_ms  # noqa: E402

H = 3_600_000


def _entry(hh="h", snap="S1", mode="confirmation", strategy="s"):
    # les _hh/_ph sont les HASHES réels (assess recalcule sha(norm_text))
    real_hh = sha(norm_text("h"))
    real_ph = sha(json.dumps({}, sort_keys=True))
    return {"_hh": hh if hh != "h" else real_hh,
            "_ph": real_ph,
            "_mode": mode, "_snapshot": snap,
            "_week": "2026-W41", "_consumes": True, "family": "f",
            "strategy": strategy, "verdict": "PASS",
            "date": "2026-10-05"}


class TestReverifyVsReplication(unittest.TestCase):
    def test_replication_nouveau_snapshot_consomme(self):
        """№1 : même hypothèse/params sur un NOUVEAU snapshot = REPLICATION
        — elle re-consomme les plafonds (l'ancien is_reverify sans snapshot
        permettait S1→S2→S3 gratuit)."""
        entries = [_entry(snap="S1")]
        budget = {"total_experiments": 20, "per_family": 1,
                  "per_strategy": 3, "max_parameter_variants": 12}
        # même hyp/params, snapshot S2, famille déjà à 1/1 → STOP
        now = datetime(2026, 10, 6, tzinfo=timezone.utc)
        res = assess(entries, budget, now, "f", "s",
                     "h", {}, mode="confirmation", snapshot="S2")
        self.assertEqual(res["status"], "STOP")
        # le MÊME snapshot S1 avec les mêmes plafonds... serait un DOUBLON
        # (dédupe) avant même la question des plafonds
        res2 = assess(entries, budget, now, "f", "s",
                      "h", {}, mode="confirmation", snapshot="S1")
        self.assertEqual(res2["status"], "NO-OP")


class TestForwardFundingCoverage(unittest.TestCase):
    def test_fenetre_sans_print_hors_era_est_inconnue(self):
        """№2 : un funding hors de l'ère couverte (avant le 1er print) est
        INCONNU — un 0.0 fabriqué gonflait la couverture."""
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
            for i in range(80):
                con.execute("INSERT INTO klines VALUES "
                            "('BTCUSDT','1h',?,100,101,99,100,1.0)",
                            (i * H,))
                if 40 <= i < 70:      # prints seulement h41..h70
                    con.execute("INSERT INTO funding_history VALUES "
                                "('BTCUSDT', ?, 0.0001)", ((i + 1) * H,))
            con.commit()
            con.close()
            spec = {"data": {"symbols": ["BTCUSDT"]},
                    "signal": {"side": -1}, "horizons": [6], "cost_pct": 0.0}
            # trade 1 : fenêtre 0-6h, AVANT le premier print (h41) → inconnu
            # trade 2 : fenêtre 50-56h, DANS l'ère mais aucun print dedans
            # (prints aux 41..70 → 51 est dedans en fait)... choisissons
            # 44-50h : prints 45 → connu
            trades = rf._closed_trades(
                spec,
                [{"symbol": "BTCUSDT", "open_time_ms": 0},
                 {"symbol": "BTCUSDT", "open_time_ms": 44 * H}],
                db, now_ms=80 * H)
            self.assertFalse(trades[0]["fund_known"])   # hors ère
            self.assertTrue(trades[1]["fund_known"])    # print dans fenêtre


class TestCollectGuard(unittest.TestCase):
    def test_collect_refuse_un_run_non_confirme(self):
        """№3 : la barrière est DANS la primitive — un --id explicite sur un
        run non confirmé (ou d'un autre protocole) ne journalise rien."""
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            rdir = runs / "EXP-nope"
            rdir.mkdir(parents=True)
            spec = {"id": "EXP-nope",
                    "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                             "train_start": 0, "train_end": 90 * H,
                             "validation_start": 90 * H,
                             "validation_end": 100 * H},
                    "signal": {"feature": "ret_1h", "op": ">=",
                               "threshold": -1000.0, "side": -1},
                    "horizons": [6], "cost_pct": 0.0}
            (rdir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (rdir / "summary_discovery.json").write_text(json.dumps(
                {"verdict": "DISCOVERY_PASS", "n": 5, "mean": 1.0,
                 "frozen_thresholds": {"BTCUSDT": [-1000.0]}}),
                encoding="utf-8")
            # PAS de summary_confirmation du tout
            db = Path(tmp) / "k.db"
            con = sqlite3.connect(db)
            con.executescript("""
            CREATE TABLE klines (symbol TEXT, interval TEXT,
                open_time INTEGER, open REAL, high REAL, low REAL,
                close REAL, volume REAL);
            CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
                rate REAL);
            """)
            for i in range(200):
                con.execute("INSERT INTO klines VALUES "
                            "('BTCUSDT','1h',?,100,101,99,100,1.0)",
                            (i * H,))
            con.commit()
            con.close()
            r = rf.collect("EXP-nope", db_path=db, now_ms=200 * H,
                           runs_dir=runs, forward_dir=Path(tmp) / "fwd")
            self.assertEqual(r["collected"], 0)
            self.assertIn("refusé", r.get("reason", ""))


class TestUniverseMs(unittest.TestCase):
    def test_la_precision_horaire_est_conservee(self):
        """№8 : tradable_window_ms utilise les champs ms (first/last_bar) —
        l'arrondi au jour rendait la dernière journée non tradable."""
        manifest = {"symbols": {"BTCUSDT": {
            "observed_start": "2026-01-01", "observed_end": "2026-01-10",
            "first_bar_ms": 10 * 86400_000,          # 10 jan 00:00
            "last_bar_ms": 19 * 86400_000 + 23 * H,  # 19 jan 23:00
            "bars": 100}}}
        t0, t1 = tradable_window_ms(manifest, "BTCUSDT")
        self.assertEqual(t0, 10 * 86400_000)
        self.assertEqual(t1, 19 * 86400_000 + 23 * H)   # pas le 19 à 00:00


if __name__ == "__main__":
    unittest.main()
