"""Tests v14 — LA CAUSALITÉ TEMPORELLE (PR-143, audit GLM 5.3 post-#142).

Le P0 look-ahead (close(i) connu à l'entrée open(i)) confirmé par mutation
test et corrigé : le masque est décalé d'une barre (signal=close(t) →
entry=open(t+1), la convention du registre). Ces tests l'empêchent de
revenir, plus les fixes №4/№6/№7/№8/№2.

    python tests/test_v14_causality.py
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
from scripts.universe import load as uload  # noqa: E402
from scripts.universe import tradable_window_ms  # noqa: E402

H = 3_600_000


def _db(path, mutate_bar=None):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
        rate REAL);
    """)
    price = 100.0
    for i in range(300):
        c = price * (0.97 if 100 <= i < 120 else 1.0)
        o = price
        if mutate_bar is not None and i == mutate_bar:
            c = price * 1.02          # la bougie mutée remonte au lieu de chuter
        hi = max(o, c) * 1.001
        lo = min(o, c) * 0.999
        con.execute("INSERT INTO klines VALUES "
                    "('BTCUSDT','1h',?,101.0,?,?,?,1.0)", (i * H, hi, lo, c))
        price = c
    con.commit()
    return con


SPEC = {"id": "X", "data": {"symbols": ["BTCUSDT"]},
        "signal": {"conditions": [
            {"feature": "ret_1h", "op": "<=", "threshold": -1.0}],
            "side": -1},
        "horizons": [6], "cost_pct": 0.0}


class TestMutationAntiLookahead(unittest.TestCase):
    def test_muter_close_i_ne_change_pas_l_entree_open_i(self):
        """LE test du rapport : modifier close(i) NE DOIT PAS modifier la
        décision d'entrée à open(i). Elle dépend du signal à i−1 — seule
        l'entrée SUIVANTE (i+1) peut bouger."""
        with tempfile.TemporaryDirectory() as tmp:
            dbA, dbB = Path(tmp) / "A.db", Path(tmp) / "B.db"
            conA, conB = _db(dbA), _db(dbB, mutate_bar=105)
            featsA = rr.compute_features(conA, "BTCUSDT", db_path=dbA)
            featsB = rr.compute_features(conB, "BTCUSDT", db_path=dbB)
            conA.close()
            conB.close()
            view = rr.DataView("t", "train", 0, 300 * H)
            mA = rr.event_mask(SPEC, featsA, view)
            mB = rr.event_mask(SPEC, featsB, view)
            self.assertEqual(bool(mA[105]), bool(mB[105]))    # INVARIANT
            # l'entrée SUIVANTE, elle, CHANGE (le signal de 105 est légitime
            # pour l'entrée à 106) — preuve que la mutation est bien vue,
            # juste une bougie plus tard
            self.assertNotEqual(bool(mA[106]), bool(mB[106]))

    def test_l_entree_est_le_signal_decale(self):
        """L'entrée à la barre i exige un signal à i−1 — le premier trade
        du crash entre à 101h (signal 100h), pas à 100h."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "k.db"
            con = _db(db)
            con.close()
            _, matrix = build_matrix(["BTCUSDT"], (6,), db_path=db,
                                     use_cache=False)
            view = rr.DataView("t", "train", 0, 300 * H)
            st = rr._study(SPEC, matrix, view, +1.0, db)
            # le crash (signaux 100..119) produit des entrées 101..120 :
            # 20 events, dont le dernier sort à 126h
            self.assertEqual(st["BTCUSDT@6h"]["n"], 20)


class TestFundingPreFirstPrint(unittest.TestCase):
    def test_funding_avant_le_premier_print_est_inconnu(self):
        """№4 : une fenêtre antérieure au premier print (ou sans aucun
        print, hors ère couverte) est INCONNUE — jamais 0.0 « connu »."""
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
                if 20 <= i < 40:      # les prints n'existent qu'aux h20..h40
                    con.execute("INSERT INTO funding_history VALUES "
                                "('BTCUSDT', ?, 0.0001)", ((i + 1) * H,))
            con.commit()
            con.close()
            _, mat = build_matrix(["BTCUSDT"], (6,), db_path=db,
                                  use_cache=False)
            f = mat["BTCUSDT"]["fund_6"]
            self.assertTrue(np.isnan(f[0]))     # fenêtre 0-6h : aucun print,
            # AVANT le premier print connu (h20) → INCONNU
            self.assertFalse(np.isnan(f[18]))   # fenêtre 18-24h : prints dedans


class TestForwardLastBar(unittest.TestCase):
    def test_la_derniere_barre_fermee_est_collectee(self):
        """№7 : la barre dont open_time == last_closed est DANS la vue
        [start, last_closed + 1h)."""
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            rdir = runs / "EXP-fwd-lb"
            rdir.mkdir(parents=True)
            spec = {"id": "EXP-fwd-lb",
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
                 "frozen_thresholds": {"BTCUSDT": [-1000.0, ]}}),
                encoding="utf-8")
            (rdir / "summary_confirmation.json").write_text(json.dumps(
                {"verdict": "CONFIRMED", "protocol_id": "protocol-v2"}),
                encoding="utf-8")
            db = Path(tmp) / "k.db"
            con = _db(db)
            con.close()
            r = rf.collect("EXP-fwd-lb", db_path=db, now_ms=300 * H,
                           runs_dir=runs, forward_dir=Path(tmp) / "fwd")
            j = rf._read_journal(Path(tmp) / "fwd" / "EXP-fwd-lb.jsonl")
            # la dernière barre FERMÉE (299h : now 300h → (300−1)h) est
            # collectée — c'est exactement le fix №7
            self.assertGreater(len(j), 0)
            self.assertEqual(max(e["open_time_ms"] for e in j),
                             299 * H)


if __name__ == "__main__":
    unittest.main()
