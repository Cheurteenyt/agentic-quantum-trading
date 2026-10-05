"""Tests des corrections de vérité v8 (rapport GLM 5.3, PR-1).

La liste d'acceptation §39 : opérateurs exacts, provenance funding,
funding dans le snapshot, bornes [start,end), sortie H dans la fenêtre,
dernier label H, masque gapless, inverse gate, overrides du convertisseur,
MAE long du forward, READY à 4 gates.

    python tests/test_v8_truth_fixes.py
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
from scripts.bonsai_batch_to_queue import convert  # noqa: E402
from scripts.label_matrix import build_matrix, snapshot_id  # noqa: E402

H_MS = 3_600_000


class TestOperators(unittest.TestCase):
    def test_table_operateurs_exacte(self):
        """GLM 5.3 §39 : <, <=, >, >= sont EXACTS ; l'invalide est refusé.
        L'ancien code exécutait « tout sauf >= » comme <=."""
        v = np.array([2.0])
        self.assertFalse(bool(rr.apply_op(v, "<", 2.0)[0]))
        self.assertTrue(bool(rr.apply_op(v, "<=", 2.0)[0]))
        self.assertFalse(bool(rr.apply_op(v, ">", 2.0)[0]))
        self.assertTrue(bool(rr.apply_op(v, ">=", 2.0)[0]))
        with self.assertRaises(ValueError):
            rr.apply_op(v, "===", 2.0)

    def test_load_spec_refuse_un_operateur_inconnu(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = {"id": "X", "hypothesis": "h",
                    "data": {"symbols": ["BTCUSDT"], "train_start": 0,
                             "train_end": 1, "validation_start": 1,
                             "validation_end": 2},
                    "signal": {"feature": "ret_1h", "op": "===",
                               "quantile": 0.5, "side": -1},
                    "horizons": [6]}
            p = Path(tmp) / "s.json"
            p.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaises(ValueError):
                rr.load_spec(p)


class TestFundingProvenance(unittest.TestCase):
    def _db(self, path, rate):
        con = sqlite3.connect(path)
        con.executescript("""
        CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL);
        CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
            rate REAL);
        """)
        for i in range(80):
            con.execute("INSERT INTO klines VALUES "
                        "('BTCUSDT','1h',?,100,101,99,100,1.0)", (i * H_MS,))
            if i % 8 == 0:
                con.execute("INSERT INTO funding_history VALUES "
                            "('BTCUSDT', ?, ?)", ((i + 1) * H_MS, rate))
        con.commit()
        return con

    def test_fund_last_vient_de_la_db_du_run(self):
        """GLM 5.3 №2 : mêmes klines, funding différent → fund_last
        différent. Aucun chemin ne retombe sur le warehouse implicite."""
        with tempfile.TemporaryDirectory() as tmp:
            dbA, dbB = Path(tmp) / "A.db", Path(tmp) / "B.db"
            conA, conB = self._db(dbA, 0.01), self._db(dbB, -0.05)
            fa = rr.compute_features(conA, "BTCUSDT", db_path=dbA)["fund_last"]
            fb = rr.compute_features(conB, "BTCUSDT", db_path=dbB)["fund_last"]
            self.assertGreater(float(np.nanmax(fa)), 0.0)
            self.assertLess(float(np.nanmax(fb)), 0.0)

    def test_le_funding_change_le_snapshot(self):
        """GLM 5.3 №3 : modifier UNE ligne de funding change l'identité —
        le cache des labels est invalidé."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = self._db(db, 0.01)
            s0 = snapshot_id(db)
            con.execute("UPDATE funding_history SET rate=-0.03 "
                        "WHERE rowid=1")
            con.commit()
            s1 = snapshot_id(db)
            self.assertNotEqual(s0, s1)
            con.close()


class TestBoundsAndLabels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
        CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL);
        CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
            rate REAL);
        """)
        price = 100.0
        for i in range(300):
            c = price * (0.97 if 100 <= i < 120 else 1.0)
            con.execute("INSERT INTO klines VALUES "
                        "('BTCUSDT','1h',?,100.0,?,?,?,1.0)",
                        (i * H_MS, max(price, c) * 1.001,
                         min(price, c) * 0.999, c))
            price = c
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_bornes_start_end_exclusives(self):
        """GLM 5.3 №8 : [start, end) — la barre frontière end n'appartient
        PAS à la vue (les fenêtres adjacentes ne la comptent pas deux fois)."""
        con = sqlite3.connect(self.db)
        feats = rr.compute_features(con, "BTCUSDT", db_path=self.db)
        con.close()
        view = rr.DataView("t", "train", 0, 10 * H_MS)   # barres 0..9
        spec = {"signal": {"conditions": [
            {"feature": "range_pct", "op": ">=", "threshold": 0.0}],
            "side": -1}}
        mask = rr.event_mask(spec, feats, view)
        # v14 : l'entrée est la bougie SUIVANTE du signal — la barre 0 ne
        # peut pas être une entrée (aucun signal à −1) → 9 entrées (1..9)
        self.assertEqual(int(mask.sum()), 9)       # pas 10, pas 11

    def test_la_sortie_doit_rester_dans_la_vue(self):
        """GLM 5.3 №7 : un event dont l'horizon H déborde de la fenêtre est
        INÉLIGIBLE — il consommerait les prix de la fenêtre suivante."""
        _, matrix = build_matrix(["BTCUSDT"], (6,), db_path=self.db,
                                 use_cache=False)
        spec = {"id": "X", "data": {"symbols": ["BTCUSDT"]},
                "signal": {"conditions": [
                    {"feature": "ret_1h", "op": "<=", "threshold": -1.0}],
                    "side": -1},
                "horizons": [6], "cost_pct": 0.0}
        # v14 : le signal du crash (100..119) entre à la bougie SUIVANTE
        # (101..120) — vue [0, 106h) : l'entrée la plus précoce (101h)
        # sort à 107h → AUCUN trade complet dans la vue
        view = rr.DataView("t", "train", 0, 106 * H_MS)
        st = rr._study(spec, matrix, view, +1.0, self.db)
        self.assertEqual(st["BTCUSDT@6h"]["n"], 0)
        # vue [0, 112h) : sorties ≤ 112h → entrées 101..106 → 6 events
        view2 = rr.DataView("t", "train", 0, 112 * H_MS)
        st2 = rr._study(spec, matrix, view2, +1.0, self.db)
        self.assertEqual(st2["BTCUSDT@6h"]["n"], 6)

    def test_dernier_label_h_valide_present(self):
        """GLM 5.3 №24 : i = n-H est un event VALIDE (H barres restantes) —
        l'ancien noyau le jetait."""
        _, matrix = build_matrix(["BTCUSDT"], (6,), db_path=self.db,
                                 use_cache=False)
        cols = matrix["BTCUSDT"]
        self.assertTrue(np.isfinite(cols["ret_6"][294]))   # n=300, n-H=294
        self.assertTrue(np.isnan(cols["ret_6"][295]))

    def test_masque_gapless_traverse_pas_un_trou(self):
        """GLM 5.3 №19 : un label dont la fenêtre contient un trou horaire
        est NaN — « 6 barres » qui valent 8 h réelles ne sont plus un 6h."""
        con = sqlite3.connect(self.db)
        con.execute("DELETE FROM klines WHERE open_time=?", (10 * H_MS,))
        con.commit()
        con.close()
        _, matrix = build_matrix(["BTCUSDT"], (6,), db_path=self.db,
                                 use_cache=False)
        cols = matrix["BTCUSDT"]
        self.assertTrue(np.isfinite(cols["ret_6"][4]))    # barres 4..9 : pleines
        self.assertTrue(np.isnan(cols["ret_6"][6]))       # 6..11 : trou à 10

    def test_discovery_gate_inverse(self):
        """GLM 5.3 №9 : le contrôle inverse GATE — un edge_advantage sous le
        seuil du protocole refuse la découverte."""
        spec = {"id": "X", "domain": "aster", "family": "f", "strategy": "s",
                "hypothesis": "h",
                "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                         "train_start": 0, "train_end": 150 * H_MS,
                         "validation_start": 150 * H_MS,
                         "validation_end": 300 * H_MS},
                "signal": {"feature": "ret_1h", "op": "<=",
                           "quantile": 0.10, "side": -1},
                "horizons": [6], "cost_pct": 0.0,
                "criteria": {"min_n": 5, "min_mean": -100.0},
                "mode": "discovery"}
        res = rr.run_discovery(spec, db_path=self.db)
        self.assertEqual(res["verdict"], "DISCOVERY_PASS")
        self.assertGreater(res["edge_advantage"], 0.0)
        # le même run avec un seuil d'avantage inatteignable → FAIL
        proto = {"discovery_gate": {"min_edge_advantage_pct": 999.0}}
        import scripts.research_os as ros
        if ros._PROTOCOL_CACHE is None:
            ros.load_confirmation_protocol()
        real = ros._PROTOCOL_CACHE
        ros._PROTOCOL_CACHE = {**real, **proto}
        try:
            res2 = rr.run_discovery(spec, db_path=self.db)
            self.assertEqual(res2["verdict"], "DISCOVERY_FAIL")
        finally:
            ros._PROTOCOL_CACHE = real


class TestForwardV8(unittest.TestCase):
    def _db(self, path):
        con = sqlite3.connect(path)
        con.executescript("""
        CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, volume REAL);
        CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
            rate REAL);
        """)
        for i in range(30):
            con.execute("INSERT INTO klines VALUES "
                        "('BTCUSDT','1h',?,100,101,99,100,1.0)", (i * H_MS,))
        con.commit()
        return con

    def test_mae_long_est_une_distance_adverse_positive(self):
        """GLM 5.3 №12 : long, entry 100, low 90 → MAE +10 % (l'ancien code
        donnait −10 % : un long ne pouvait JAMAIS être liquidé)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = self._db(db)
            con.execute("UPDATE klines SET low=90.0 WHERE open_time=?",
                        (2 * H_MS,))
            con.commit()
            con.close()
            spec = {"data": {"symbols": ["BTCUSDT"]},
                    "signal": {"side": 1}, "horizons": [6], "cost_pct": 0.0}
            events = [{"symbol": "BTCUSDT", "open_time_ms": 0}]
            trades = rf._closed_trades(spec, events, db, now_ms=20 * H_MS)
            self.assertEqual(len(trades), 1)
            self.assertAlmostEqual(trades[0]["mae_pct"], 10.0, places=6)

    def test_ready_exige_les_quatre_gates(self):
        """GLM 5.3 №11 : READY = jours ∧ trades ∧ Sharpe ∧ vs-discovery —
        un Sharpe négatif ou une moyenne effondrée bloque, même à 41 jours
        et 100 trades."""
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            rdir = runs / "EXP-ready"
            rdir.mkdir(parents=True)
            spec = {"id": "EXP-ready", "data": {"symbols": ["BTCUSDT"]},
                    "signal": {"side": -1}, "horizons": [6], "cost_pct": 0.0}
            (rdir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (rdir / "summary_discovery.json").write_text(
                json.dumps({"mean": 1.0}), encoding="utf-8")
            (rdir / "summary_confirmation.json").write_text(json.dumps(
                {"verdict": "CONFIRMED", "protocol_id": "protocol-v2"}),
                encoding="utf-8")
            (rdir / "manifest.json").write_text(json.dumps(
                {"timestamp": "1970-01-10T00:00:00+00:00"}), encoding="utf-8")
            db = Path(tmp) / "k.db"
            con = self._db(db)
            for k in range(126):   # des prints de funding (gate v10)
                con.execute("INSERT INTO funding_history VALUES "
                            "('BTCUSDT', ?, 0.0001)", ((k * 8 + 1) * H_MS,))
            con.commit()
            con.close()
            # 120 trades fermés, alternance +5/+6 % (Sharpe positif élevé)
            fwd = Path(tmp) / "forward"
            fwd.mkdir()
            with open(fwd / "EXP-ready.jsonl", "w", encoding="utf-8") as fh:
                for k in range(120):
                    fh.write(json.dumps({"symbol": "BTCUSDT",
                                         "open_time_ms": k * 2 * H_MS}) + "\n")
            # klines : un short qui gagne 5-6 % par trade (close 94-95)
            con = sqlite3.connect(db)
            for k in range(120):
                c = 94.5 if k % 2 == 0 else 94.0
                for j in range(6):
                    con.execute(
                        "INSERT OR REPLACE INTO klines VALUES "
                        "('BTCUSDT','1h',?,100,101,94,?,1.0)",
                        ((k * 2 + j) * H_MS, c))
            con.commit()
            con.close()
            s = rf.status("EXP-ready", db_path=db,
                          now_ms=1000 * H_MS,      # ~33 j après le manifest
                          runs_dir=runs, forward_dir=fwd)
            m = s["maturation"]
            self.assertTrue(m["days_pass"])
            self.assertTrue(m["trades_pass"])
            self.assertTrue(m["sharpe_pass"])
            self.assertTrue(m["vs_discovery_pass"])
            self.assertTrue(m["ready"])


class TestConvertOverrides(unittest.TestCase):
    def test_override_cli_pilote(self):
        """GLM 5.3 №25 : --min-n/--min-mean pilotent RÉELLEMENT la spec."""
        batch = {"hypotheses": [{
            "id": "H-99", "mechanism": "m", "feature": "ret_1h",
            "side": "short", "horizon_h": 6, "compute_class": "small",
            "conditions": [{"feature": "ret_1h", "op": "<=", "quantile": 0.1}]}]}
        specs, _ = convert(batch, ["BTCUSDT"])
        self.assertEqual(specs[0]["criteria"]["min_n"], 50)   # défaut small
        specs2, _ = convert(batch, ["BTCUSDT"], min_n_override=500,
                            min_mean_override=0.1)
        self.assertEqual(specs2[0]["criteria"]["min_n"], 500)
        self.assertEqual(specs2[0]["criteria"]["min_mean"], 0.1)


if __name__ == "__main__":
    unittest.main()
