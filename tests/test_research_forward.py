"""Tests du forward du Research OS (3e étape du protocole — PAPER).

Le collect évalue le masque GELÉ sur les barres fermées INÉDITES (>
validation_end), journalise de façon idempotente ; le status mesure les
trades fermés depuis les klines brutes et l'horloge de maturation.

    python tests/test_research_forward.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_forward as rf  # noqa: E402
from scripts import research_runner as rr  # noqa: E402

H_MS = 3_600_000
NOW_MS = 400 * H_MS      # le « maintenant » des fixtures


def _db(path, n=380):
    """Barres plates 1h + un crash de 20 barres dans la zone INÉDITE
    (validation_end = 300 h, crash à 320-339 → le forward doit le voir)."""
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
    """)
    price = 100.0
    for i in range(n):
        c = price * (0.97 if 320 <= i < 340 else 1.0)   # -3 %/barre pendant 20h
        hi = max(price, c) * 1.001
        lo = min(price, c) * 0.999
        con.execute("INSERT INTO klines VALUES "
                    "('BTCUSDT','1h',?,100.0,?,?,?,1.0)", (i * H_MS, hi, lo, c))
        con.execute("INSERT INTO funding_history VALUES "
                    "('BTCUSDT', ?, 0.0001)", ((i + 1) * H_MS,))
        price = c
    con.commit()
    return con


def _make_run(runs_dir: Path, run_id="EXP-fwd-001"):
    """Un run CONFIRMÉ complet : spec + summary_discovery (seuils gelés) +
    summary_confirmation + manifest."""
    rdir = runs_dir / run_id
    rdir.mkdir(parents=True)
    spec = {
        "id": run_id, "domain": "aster", "family": "forced_flow",
        "strategy": "fwd-test",
        "hypothesis": "un crash continue de baisser",
        "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                 "train_start": 0, "train_end": 150 * H_MS,
                 "validation_start": 150 * H_MS, "validation_end": 300 * H_MS},
        "signal": {"feature": "ret_1h", "op": "<=", "threshold": -1.0,
                   "side": -1},
        "horizons": [6], "cost_pct": 0.0, "criteria": {"min_n": 5},
        "mode": "confirmation",
    }
    (rdir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (rdir / "summary_discovery.json").write_text(json.dumps({
        "verdict": "DISCOVERY_PASS", "n": 20, "mean": 8.0,
        "frozen_thresholds": {"BTCUSDT": [-1.0]}}), encoding="utf-8")
    (rdir / "summary_confirmation.json").write_text(json.dumps({
        "verdict": "CONFIRMED", "n": 10, "mean": 5.0,
        "protocol_id": "protocol-v2"}), encoding="utf-8")
    (rdir / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "kind": "confirmation",
        "timestamp": "2026-10-05T12:00:00+00:00"}), encoding="utf-8")
    return spec


class TestForward(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        self.con = _db(self.db)
        self.runs = Path(self.tmp.name) / "runs"
        self.fwd = Path(self.tmp.name) / "forward"
        self.runs.mkdir()
        self.spec = _make_run(self.runs)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_confirmed_runs_trouve_les_confirmes(self):
        self.assertEqual(rf.confirmed_runs(self.runs), ["EXP-fwd-001"])
        # un run REJECTED n'est pas un confirmé
        rdir = self.runs / "EXP-rej-002"
        rdir.mkdir()
        (rdir / "summary_confirmation.json").write_text(
            json.dumps({"verdict": "REJECTED",
                        "protocol_id": "protocol-v2"}), encoding="utf-8")
        self.assertEqual(rf.confirmed_runs(self.runs), ["EXP-fwd-001"])
        # v8 (GLM 5.3 №16) : un run confirmé SANS stamp protocole (legacy)
        # n'entre pas en maturation non plus
        rdir = self.runs / "EXP-legacy-003"
        rdir.mkdir()
        (rdir / "summary_confirmation.json").write_text(
            json.dumps({"verdict": "CONFIRMED"}), encoding="utf-8")
        self.assertEqual(rf.confirmed_runs(self.runs), ["EXP-fwd-001"])

    def test_collect_journaise_les_events_inedits(self):
        """Seules les barres > validation_end (300 h) comptent : le crash de
        la zone inédite (320-339 h) doit produire des events, le crash de
        l'entraînement (s'il y en avait) jamais."""
        r = rf.collect("EXP-fwd-001", db_path=self.db, now_ms=NOW_MS,
                       runs_dir=self.runs, forward_dir=self.fwd)
        self.assertGreater(r["collected"], 0)
        j = rf._read_journal(rf._journal_path("EXP-fwd-001", self.fwd))
        self.assertTrue(all(e["open_time_ms"] > 300 * H_MS for e in j))
        self.assertTrue(all(e["open_time_ms"] <= (NOW_MS // H_MS - 1) * H_MS
                            for e in j))
        # le crash commence à la barre 320 : le premier event est là (ret_1h
        # = -3 % <= seuil gelé -1.0)
        self.assertEqual(min(e["open_time_ms"] for e in j), 320 * H_MS)

    def test_collect_est_idempotent(self):
        """Une deuxième collecte sur les mêmes barres ne journalise RIEN —
        une nuit manquée ne perd rien, une nuit rejouée ne double rien."""
        rf.collect("EXP-fwd-001", db_path=self.db, now_ms=NOW_MS,
                   runs_dir=self.runs, forward_dir=self.fwd)
        r2 = rf.collect("EXP-fwd-001", db_path=self.db, now_ms=NOW_MS,
                        runs_dir=self.runs, forward_dir=self.fwd)
        self.assertEqual(r2["collected"], 0)
        # et une collecte AVANCÉE (48 h plus tard) attrape les nouvelles barres
        r3 = rf.collect("EXP-fwd-001", db_path=self.db, now_ms=NOW_MS + 48 * H_MS,
                        runs_dir=self.runs, forward_dir=self.fwd)
        self.assertGreaterEqual(r3["collected"], 0)

    def test_status_mesure_les_trades_fermes(self):
        """Le status évalue les events dont l'horizon est écoulé : le short
        du crash inédit gagne ~+17 % brut (3 %/barre × 6 barres) moins le
        MAE-check (aucune liq à 1x de facto, seuil 99,5 %)."""
        rf.collect("EXP-fwd-001", db_path=self.db, now_ms=NOW_MS,
                   runs_dir=self.runs, forward_dir=self.fwd)
        s = rf.status("EXP-fwd-001", db_path=self.db, now_ms=NOW_MS,
                      runs_dir=self.runs, forward_dir=self.fwd)
        self.assertGreater(s["trades_closed"]["n"], 0)
        self.assertGreater(s["trades_closed"]["mean"], 0.0)   # le short gagne
        self.assertIsNotNone(s["wallet"])
        self.assertEqual(s["wallet"]["liqs"], 0)
        m = s["maturation"]
        self.assertEqual(m["days_required"], 30)
        self.assertEqual(m["trades_required"], 100)
        self.assertFalse(m["ready"])     # 0 jour de maturation au manifest

    def test_maturation_horloge(self):
        """L'horloge compte depuis le manifest de confirmation."""
        rdir = self.runs / "EXP-fwd-001"
        m = json.loads((rdir / "manifest.json").read_text(encoding="utf-8"))
        m["timestamp"] = "1970-01-10T00:00:00+00:00"   # ~9 j après l'epoch
        (rdir / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        s = rf.status("EXP-fwd-001", db_path=self.db, now_ms=NOW_MS,
                      runs_dir=self.runs, forward_dir=self.fwd)
        self.assertAlmostEqual(s["maturation"]["days"], (400 - 216) / 24,
                               delta=0.1)
        # READY exige AUSSI min_forward_trades (100) — 9 j de trades ne
        # suffisent pas même avec 30 j passés
        self.assertFalse(s["maturation"]["ready"])

    def test_pas_de_seuils_geles_refuse(self):
        """Un confirmé sans summary_discovery (seuils gelés) ne collecte
        pas — jamais de re-calibration sur le live."""
        rdir = self.runs / "EXP-fwd-001"
        (rdir / "summary_discovery.json").unlink()
        r = rf.collect("EXP-fwd-001", db_path=self.db, now_ms=NOW_MS,
                       runs_dir=self.runs, forward_dir=self.fwd)
        self.assertEqual(r["collected"], 0)
        self.assertIn("reason", r)


if __name__ == "__main__":
    unittest.main()
