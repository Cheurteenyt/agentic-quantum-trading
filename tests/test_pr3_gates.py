"""Tests PR-3 (audit GLM 5.3 post-#135) : provenance manifest, sortie
exactement sur la frontière de fenêtre, funding MTM aux prints réels,
DD/stress par fenêtre comme gates, gate de couverture funding au forward.

    python tests/test_pr3_gates.py
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

from scripts import research_forward as rf  # noqa: E402
from scripts import research_runner as rr  # noqa: E402
from scripts.label_matrix import build_matrix  # noqa: E402
from scripts.portfolio_runner import run_wallet_mtm  # noqa: E402

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


class TestExitBoundary(unittest.TestCase):
    def test_la_sortie_exactement_sur_la_fin_est_valide(self):
        """P1 off-by-one : fenêtre [0, 100h], H=6, entrée 94h → sortie 100h
        = barres 94..99, PARFAITEMENT contenue → l'event doit compter."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = _db(db)
            con.close()
            _, matrix = build_matrix(["BTCUSDT"], (6,), db_path=db,
                                     use_cache=False)
            spec = {"id": "X", "data": {"symbols": ["BTCUSDT"]},
                    "signal": {"conditions": [
                        {"feature": "ret_1h", "op": "<=", "threshold": -1.0}],
                        "side": -1},
                    "horizons": [6], "cost_pct": 0.0}
            # le crash couvre les barres 100..119 ; on veut un event dont la
            # SORTIE tombe pile sur la fin : entrée 94h → sortie 100h.
            # Le bar 94 n'a pas ret ≤ −1 (le crash démarre à 100) → on force
            # un masque par conditions absurdes qui couvre TOUTES les barres :
            spec["signal"] = {"conditions": [
                {"feature": "range_pct", "op": ">=", "threshold": 0.0}],
                "side": -1}
            view = rr.DataView("t", "train", 0, 100 * H)
            st = rr._study(spec, matrix, view, +1.0, db)
            # barres 0..94 éligibles (exit ≤ 100h) = 95 events
            self.assertEqual(st["BTCUSDT@6h"]["n"], 95)
            # vue fin 99h : sortie ≤ 99 → entrées 0..93 = 94 events
            view2 = rr.DataView("t", "train", 0, 99 * H)
            st2 = rr._study(spec, matrix, view2, +1.0, db)
            self.assertEqual(st2["BTCUSDT@6h"]["n"], 94)


class TestFundingMtm(unittest.TestCase):
    def test_le_funding_est_accredite_aux_heures_exactes(self):
        """P0 MTM funding : un print unique +1 % à t+12h doit laisser la
        courbe plate jusqu'à 12h PUIS sauter — pas 1/24 chaque heure."""
        ev = [{"sym": "BTCUSDT", "t_ms": 0, "exit_ms": 24 * H, "side": -1,
               "ret_pct": 0.0, "entry": 100.0, "mae_pct": 0.5,
               "fund_pct": 1.0, "cost_pct": 0.0,
               "fund_prints": [(12 * H, 1.0)]}]   # +1 % du notional à 12h
        closes = [100.0] * 24
        marks = {"BTCUSDT": {
            "t": np.arange(24) * H,
            "close": np.array(closes),
            "high": np.array(closes), "low": np.array(closes)}}
        w = run_wallet_mtm(ev, marks, capital=100.0, cap_pct=1.0, lev=1.0)
        # notional 1 $ → +1 % = +0,01 $ à 12h ; solde final = 100,01
        self.assertAlmostEqual(w["solde"], 100.01, places=9)
        self.assertAlmostEqual(w["funding_net"], 0.01, places=9)


class TestManifestProvenance(unittest.TestCase):
    def test_le_manifest_porte_la_provenance_complete(self):
        """P0 provenance : git_sha intégral + git_dirty + diff_sha +
        label_version + protocol_id — un run sur arbre sale est traçable."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = _db(db)
            con.close()
            spec = {"id": "EXP-prov", "domain": "aster", "family": "f",
                    "strategy": "s", "hypothesis": "h",
                    "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                             "train_start": 0, "train_end": 150 * H,
                             "validation_start": 150 * H,
                             "validation_end": 200 * H},
                    "signal": {"feature": "ret_1h", "op": "<=",
                               "quantile": 0.10, "side": -1},
                    "horizons": [6], "cost_pct": 0.0,
                    "criteria": {"min_n": 5}, "mode": "discovery"}
            res = rr.run_discovery(spec, db_path=db)
            saved = rr.RUNS
            rr.RUNS = Path(tmp) / "runs"
            try:
                rdir = rr.write_artifacts(spec["id"], spec, res, "discovery",
                                          db_path=db)
                m = json.loads((rdir / "manifest.json").read_text(
                    encoding="utf-8"))
            finally:
                rr.RUNS = saved
            self.assertIn("git_dirty", m)
            self.assertIn("diff_sha", m)
            self.assertIn("label_version", m)
            self.assertEqual(m["label_version"], "v2")
            self.assertEqual(m["protocol_id"], "protocol-v2")
            self.assertGreaterEqual(len(m["git_sha"]), 7)


class TestWindowGates(unittest.TestCase):
    def test_fenetre_jugee_sur_trois_gates(self):
        """P1 : chaque fenêtre porte pass_base / pass_stress / pass_dd et
        pass = ET des trois — une fenêtre stress-négative ne passe plus."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = _db(db)
            con.close()
            spec = {"id": "X", "domain": "aster", "family": "f",
                    "strategy": "s", "hypothesis": "h",
                    "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                             "train_start": 0, "train_end": 150 * H,
                             "validation_start": 150 * H,
                             "validation_end": 200 * H},
                    "signal": {"feature": "ret_1h", "op": "<=",
                               "quantile": 0.10, "side": -1},
                    "horizons": [6], "cost_pct": 0.0,
                    "criteria": {"min_n": 5, "min_mean": -100.0},
                    "mode": "confirmation"}
            res_d = rr.run_discovery(spec, db_path=db)
            rr.RUNS = Path(tmp) / "runs"
            rr.RUNS.mkdir(parents=True, exist_ok=True)
            rr.write_artifacts(spec["id"], spec, res_d, "discovery",
                               db_path=db)
            proto = {"frozen_windows": [{"start": "1970-01", "end": "1970-02"}],
                     "embargo_hours": 0, "windows_pass_required": 1,
                     "cost_stress_multiplier": 1.5,
                     "degradation_max_pct": 70, "max_window_loss_pct": 15}
            res = rr.run_confirmation(spec, db_path=db, protocol=proto)
            w = res["per_window"]["1970-01"]
            for k in ("pass_base", "pass_stress", "pass_dd", "stress_mean",
                      "max_dd_mtm"):
                self.assertIn(k, w, k)
            # l'agrégat validation est clampé au span des fenêtres gelées :
            # la validation [150h, 200h] ⊆ [0, 744h] → inchangée ici
            self.assertEqual(res["validation_window"][1], 200 * H)


class TestForwardFundGate(unittest.TestCase):
    def test_la_couverture_funding_est_un_gate(self):
        """P1 forward : READY exige fund_pass (couverture ≥ 95 %) — un
        candidat à 49 % de funding inconnu ne peut plus déclarer READY."""
        self.assertTrue(True)  # la logique est couverte par le flag fund_pass
        # vérification directe du calcul de couverture
        from scripts.research_forward import status  # noqa: F401
        # test unitaire : fund_known_pct < 95 bloque ready
        spec = {"data": {"symbols": ["BTCUSDT"]}, "signal": {"side": -1},
                "horizons": [6], "cost_pct": 0.0}
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            rdir = runs / "EXP-fg"
            rdir.mkdir(parents=True)
            (rdir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (rdir / "summary_discovery.json").write_text(
                json.dumps({"mean": 1.0}), encoding="utf-8")
            (rdir / "summary_confirmation.json").write_text(json.dumps(
                {"verdict": "CONFIRMED", "protocol_id": "protocol-v2"}),
                encoding="utf-8")
            (rdir / "manifest.json").write_text(json.dumps(
                {"timestamp": "1970-01-10T00:00:00+00:00"}), encoding="utf-8")
            db = Path(tmp) / "k.db"
            con = _db(db)
            con.close()
            fwd = Path(tmp) / "forward"
            fwd.mkdir()
            # 120 trades : la moitié à funding inconnu (fund_known False)
            with open(fwd / "EXP-fg.jsonl", "w", encoding="utf-8") as fh:
                for k in range(120):
                    fh.write(json.dumps({"symbol": "BTCUSDT",
                                         "open_time_ms": k * 2 * H}) + "\n")
            con = sqlite3.connect(db)
            for k in range(120):
                for j in range(6):
                    con.execute(
                        "INSERT OR REPLACE INTO klines VALUES "
                        "('BTCUSDT','1h',?,100,101,94,99,1.0)",
                        ((k * 2 + j) * H,))
            con.commit()
            con.close()
            s = rf.status("EXP-fg", db_path=db, now_ms=1000 * H,
                          runs_dir=runs, forward_dir=fwd)
            m = s["maturation"]
            self.assertFalse(m["fund_pass"])     # funding_history vide → 0 %
            self.assertFalse(m["ready"])


if __name__ == "__main__":
    unittest.main()
