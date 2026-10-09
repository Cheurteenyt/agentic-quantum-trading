"""Ronde 6 — A1 + A4 + A3 : le gate de confirmation et la validation des specs.

A1 : le gate de fraîcheur des données de la CONFIRMATION comparait le
snapshot GLOBAL (hash de TOUTES les 1h + tout le funding). Or la db
dérive EN CONTINU (le nocturne append des barres) — tout append entre la
découverte et la confirmation déclenchait CONFIRMATION_BLOCKED et une
re-discovery obligatoire pour rien. Désormais : le gate compare le hash
FENÊTRÉ [0, validation_end) (dataset_window_sha) — une correction
historique DANS la fenêtre bloque toujours (fail-closed), un append
AU-DELÀ de la fenêtre est tracé et non bloquant. Artefact legacy (sans
dws) : gate strict inchangé.

A4 : les fenêtres de spec doivent être des int ms epoch — une date ISO
crashait en int() profond (FAILED_PERMANENT sans message).

A3 : le kernel ne résout que '1h' — un timeframe déclaré ≠ 1h serait
mesuré en 1h en silence : refus précoce.

    python tests/test_r6_confirm_gate_dws.py
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

from scripts import research_runner as rr  # noqa: E402
from scripts.label_matrix import dataset_window_sha  # noqa: E402

H_MS = 3_600_000
VAL_END = 300 * H_MS


def _db(path, n=300):
    """Le même socle que test_research_runner : plat + crash déterministe."""
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
    """)
    price = 100.0
    for i in range(n):
        o = price
        c = price * (1 - 0.03) if 100 <= i < 120 else 1.0 and price
        c = price * (0.97 if 100 <= i < 120 else 1.0)
        hi = max(o, c) * 1.001
        lo = min(o, c) * 0.999
        con.execute("INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
                    (i * H_MS, o, hi, lo, c))
        if i % 8 == 0:
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, 0.0001)", (i * H_MS + H_MS,))
        price = c
    con.commit()
    return con


def _spec(tmp, mode="confirmation"):
    spec = {
        "id": "EXP-r6-001",
        "domain": "aster", "family": "f", "strategy": "r6",
        "hypothesis": "gate fenêtré",
        "data": {"symbols": ["BTCUSDT"],
                 "train_start": 0, "train_end": 150 * H_MS,
                 "validation_start": 150 * H_MS,
                 "validation_end": VAL_END},
        "signal": {"feature": "ret_1h", "op": "<=", "quantile": 0.10,
                   "side": -1},
        "horizons": [6], "cost_pct": 0.0,
        "criteria": {"min_n": 5, "min_mean": -100.0},
        "mode": mode,
    }
    sp = Path(tmp) / "EXP-r6-001.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    return sp, spec


PROTO_MINI = {
    "protocol_id": "protocol-v2",
    "frozen_windows": [{"start": "1970-01", "end": "1970-02"}],
    "embargo_hours": 0, "windows_pass_required": 1,
    "cost_stress_multiplier": 1.5, "degradation_max_pct": 70,
    "max_window_loss_pct": 15,
}


class TestConfirmGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        self.con = _db(self.db)
        self.spec_path, self.spec = _spec(self.tmp.name)
        self._runs_backup = rr.RUNS
        rr.RUNS = Path(self.tmp.name) / "runs"

    def tearDown(self):
        rr.RUNS = self._runs_backup
        self.con.close()
        self.tmp.cleanup()

    def _discover(self):
        res_d = rr.run_discovery(self.spec, db_path=self.db)
        rr.write_artifacts(self.spec["id"], self.spec, res_d, "discovery",
                           db_path=self.db)
        return res_d

    def _confirm(self):
        return rr.run_confirmation(self.spec, db_path=self.db,
                                   protocol=PROTO_MINI)

    def test_discovery_scelle_le_dws(self):
        res = self._discover()
        self.assertEqual(
            res["dataset_window_sha"],
            dataset_window_sha(self.db, VAL_END))
        s = json.loads((rr.RUNS / "EXP-r6-001" / "summary_discovery.json")
                       .read_text(encoding="utf-8"))
        self.assertEqual(s["dataset_window_sha"],
                         dataset_window_sha(self.db, VAL_END))

    def test_cycle_standard_passe_toujours(self):
        """Non-régression : sans dérive, la confirmation n'est pas bloquée."""
        self._discover()
        res = self._confirm()
        self.assertIn(res["verdict"], ("CONFIRMED", "REJECTED"))
        self.assertEqual(res["slots_consumed"], 1)

    def test_append_apres_la_fenetre_ne_bloque_plus(self):
        """LE test A1 : un append nocturne au-delà de validation_end dérive
        le snapshot GLOBAL mais ne doit PAS bloquer la confirmation —
        l'ancien gate rendait toute confirmation impossible après un
        append (CONFIRMATION_BLOCKED, re-discovery obligatoire)."""
        self._discover()
        con = sqlite3.connect(self.db)
        for i in range(5):
            con.execute(
                "INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
                ((VAL_END + i * H_MS), 100.0, 101.0, 99.0, 100.5))
        con.commit()
        con.close()
        res = self._confirm()
        self.assertIn(res["verdict"], ("CONFIRMED", "REJECTED"),
                      "l'append au-delà de la fenêtre ne doit plus bloquer")
        self.assertEqual(res["slots_consumed"], 1)
        # la dérive est tracée dans l'artefact (gate_notes)
        self.assertTrue(res["discovery_artifact"]["gate_notes"])

    def test_correction_dans_la_fenetre_bloque_toujours(self):
        """Fail-closed : une correction historique DANS la fenêtre change le
        dws → CONFIRMATION_BLOCKED (re-discovery obligatoire, comme voulu)."""
        self._discover()
        con = sqlite3.connect(self.db)
        con.execute("UPDATE klines SET close=close*1.5 WHERE open_time=?",
                    (80 * H_MS,))
        con.commit()
        con.close()
        res = self._confirm()
        self.assertEqual(res["verdict"], "CONFIRMATION_BLOCKED")
        self.assertEqual(res["slots_consumed"], 0)
        self.assertIn("correction historique", res["reason"])

    def test_artefact_legacy_sans_dws_gate_strict_inchange(self):
        """Un artefact d'avant le dws : le gate snapshot GLOBAL reste
        strict (fail-closed de l'ère legacy)."""
        self._discover()
        sf = rr.RUNS / "EXP-r6-001" / "summary_discovery.json"
        s = json.loads(sf.read_text(encoding="utf-8"))
        s.pop("dataset_window_sha", None)
        s["snapshot"] = "snap-legacy-perime"
        sf.write_text(json.dumps(s), encoding="utf-8")
        res = self._confirm()
        self.assertEqual(res["verdict"], "CONFIRMATION_BLOCKED")
        self.assertIn("snapshot", res["reason"])

    def test_artefact_legacy_sans_dws_snapshot_ok_passe(self):
        self._discover()
        sf = rr.RUNS / "EXP-r6-001" / "summary_discovery.json"
        s = json.loads(sf.read_text(encoding="utf-8"))
        s.pop("dataset_window_sha", None)   # snapshot reste correct
        sf.write_text(json.dumps(s), encoding="utf-8")
        res = self._confirm()
        self.assertIn(res["verdict"], ("CONFIRMED", "REJECTED"))


class TestLoadSpecGuards(unittest.TestCase):
    """A4 (types) + A3 (timeframe) : refus précoce, message limpide."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.spec = {
            "id": "X", "hypothesis": "h",
            "data": {"symbols": ["BTCUSDT"], "train_start": 0,
                     "train_end": 1, "validation_start": 1,
                     "validation_end": 2},
            "signal": {"feature": "ret_1h", "op": "<=", "quantile": 0.1},
            "horizons": [6],
        }

    def _write(self, spec, name="X.json"):
        p = self.dir / name
        p.write_text(json.dumps(spec), encoding="utf-8")
        return p

    def test_date_iso_refusee_avec_message_clair(self):
        s = json.loads(json.dumps(self.spec))
        s["data"]["train_start"] = "2025-01-01"
        with self.assertRaises(ValueError) as ctx:
            rr.load_spec(self._write(s))
        self.assertIn("int ms epoch", str(ctx.exception))

    def test_bool_refuse(self):
        s = json.loads(json.dumps(self.spec))
        s["data"]["validation_end"] = True   # bool n'est pas un int légal
        with self.assertRaises(ValueError):
            rr.load_spec(self._write(s))

    def test_timeframe_4h_refuse(self):
        s = json.loads(json.dumps(self.spec))
        s["timeframe"] = "4h"
        with self.assertRaises(ValueError) as ctx:
            rr.load_spec(self._write(s))
        self.assertIn("1h", str(ctx.exception))

    def test_timeframe_absent_ok(self):
        p = self._write(self.spec)
        spec = rr.load_spec(p)
        self.assertEqual(spec["id"], "X")

    def test_timeframe_1h_ok(self):
        s = json.loads(json.dumps(self.spec))
        s["timeframe"] = "1h"
        spec = rr.load_spec(self._write(s))
        self.assertEqual(spec["timeframe"], "1h")


if __name__ == "__main__":
    unittest.main(verbosity=2)
