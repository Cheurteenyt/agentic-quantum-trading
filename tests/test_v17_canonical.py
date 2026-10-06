"""Tests v17 — le chemin canonique (audit GLM 5.3 post-#148, PR-149).

Un SignalEvent doit être consommé pareillement par l'event-study, le wallet
et le forward : l'univers contraint les TROIS chemins, les prints de
funding gardent leurs horodatages, les trous partiels sont détectés, un
artefact de découverte altéré est refusé, une écriture ledger échouée
échoue la confirmation.

    python tests/test_v17_canonical.py
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


SPEC = {"id": "X", "data": {"symbols": ["BTCUSDT"]},
        "signal": {"conditions": [
            {"feature": "ret_1h", "op": "<=", "threshold": -1.0}],
            "side": -1},
        "horizons": [24], "cost_pct": 0.0}


class TestUniverseTroisChemins(unittest.TestCase):
    """№1 : l'univers contraint event-study, wallet ET forward — pas
    seulement _study(). L'event à h=90, horizon 24h, univers finissant
    à h=106 : entry+24h = 114 > 106 → exclu PARTOUT."""

    def _setup(self, tmp):
        db = Path(tmp) / "k.db"
        con = _db(db, n=200)
        con.close()
        _, matrix = build_matrix(["BTCUSDT"], (24,), db_path=db,
                                 use_cache=False)
        manifest = {"symbols": {"BTCUSDT": {
            "observed_start": "1970-01-01", "first_bar_ms": 0,
            "last_bar_ms": 106 * H, "bars": 107}}}
        udir = Path(tmp) / "universe"
        udir.mkdir(exist_ok=True)
        (udir / "u.yaml").write_text(json.dumps(manifest), encoding="utf-8")
        spec = {**SPEC, "universe": "u"}
        import scripts.universe as uni
        saved = uni.UNIVERSE_DIR
        uni.UNIVERSE_DIR = udir
        return db, matrix, spec, saved, uni

    def test_le_wallet_respecte_l_univers(self):
        """№1 : collect_events (le chemin wallet/DD) exclut l'event dont
        la sortie déborde du span tradable."""
        with tempfile.TemporaryDirectory() as tmp:
            db, matrix, spec, saved, uni = self._setup(tmp)
            try:
                con = sqlite3.connect(db)
                feats = rr.compute_features(con, "BTCUSDT", db_path=db)
                con.close()
                view = rr.DataView("t", "train", 0, 200 * H)
                from scripts.portfolio_runner import collect_events
                evs, _ = collect_events(spec, matrix,
                                        {"BTCUSDT": feats}, view,
                                        db_path=db)
                # l'event du crash (signaux 100..119 → entrées 101..120)
                # : une entrée à 101h sort à 125h > 106h → exclue
                self.assertTrue(all(e["exit_ms"] <= 107 * H for e in evs))
            finally:
                uni.UNIVERSE_DIR = saved


class TestFundingPrintsForward(unittest.TestCase):
    def test_les_prints_gardent_leurs_horodatages(self):
        """№2 : le forward produit des prints HORODATÉS (l'ancien
        fund_prints=[] forçait l'accrual à la sortie)."""
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
            for i in range(40):
                con.execute("INSERT INTO klines VALUES "
                            "('BTCUSDT','1h',?,100,101,99,100,1.0)",
                            (i * H,))
            # des prints à +2h et +4h d'un trade entré à 0h (+ un print
            # à +7h pour couvrir la fenêtre jusqu'à sa sortie à +6h)
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, 0.0005)", (2 * H,))
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, -0.0002)", (4 * H,))
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, 0.0001)", (7 * H,))
            con.commit()
            con.close()
            spec = {"data": {"symbols": ["BTCUSDT"]},
                    "signal": {"side": -1}, "horizons": [6], "cost_pct": 0.0}
            trades = rf._closed_trades(
                spec, [{"symbol": "BTCUSDT", "open_time_ms": 0,
                        "entry_open": 100.0}], db, now_ms=40 * H)
            prints = trades[0]["fund_prints"]
            self.assertEqual([p[0] for p in prints], [2 * H, 4 * H])
            # signés : short reçoit +0.05, paie −0.02 (points de %)
            self.assertAlmostEqual(prints[0][1], 0.05, places=9)
            self.assertAlmostEqual(prints[1][1], -0.02, places=9)


class TestTrouPartiel(unittest.TestCase):
    def test_un_print_manquant_dans_le_calendrier_est_detecte(self):
        """№5 : calendrier 8h avec le print de 16h ABSENT — la fenêtre
        8→32h contient des prints mais un attendu manque → INCONNUE."""
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
            # calendrier 8h : prints 1h, 9h, [16h MANQUANT], 25h, 33h
            for hh in (1, 9, 25, 33):
                con.execute("INSERT INTO funding_history VALUES "
                            "('BTCUSDT', ?, 0.0001)", (hh * H,))
            con.commit()
            con.close()
            _, mat = build_matrix(["BTCUSDT"], (6,), db_path=db,
                                  use_cache=False)
            f = mat["BTCUSDT"]["fund_6"]
            # fenêtre 20→26h : le segment [9h, 25h) de 16h (> 1,5×8h)
            # intersecte la fenêtre → un print attendu manque → INCONNUE
            self.assertTrue(np.isnan(f[20]))
            # fenêtre 0→6h : print à 1h, segments sains (8h ≤ 1,5×8h) → connu
            self.assertFalse(np.isnan(f[0]))


class TestDiscoveryPinning(unittest.TestCase):
    def test_artefact_altere_refuse(self):
        """Bloc B4 : une spec courante dont le CŒUR diffère de l'artefact
        de découverte → CONFIRMATION_BLOCKED (spec A + seuils B ≠ preuve)."""
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            rdir = runs / "EXP-pin"
            rdir.mkdir(parents=True)
            spec = {"id": "EXP-pin",
                    "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                             "train_start": 0, "train_end": 90 * H,
                             "validation_start": 90 * H,
                             "validation_end": 200 * H},
                    "signal": {"feature": "ret_1h", "op": "<=",
                               "threshold": -1000.0, "side": -1},
                    "horizons": [6], "cost_pct": 0.0,
                    "mode": "confirmation"}
            (rdir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            # la découverte a été mesurée sur un CŒUR DIFFÉRENT (un autre
            # seuil) — le pinning doit le voir
            disc = dict(spec)
            disc["signal"] = {"feature": "ret_1h", "op": "<=",
                              "threshold": -2.0, "side": -1}
            (rdir / "summary_discovery.json").write_text(json.dumps({
                "verdict": "DISCOVERY_PASS", "n": 5, "mean": 1.0,
                "protocol_id": "protocol-v2",
                "spec_execution_sha": rr.spec_execution_sha(disc),
                "frozen_thresholds": {"BTCUSDT": [-2.0]}}), encoding="utf-8")
            saved = rr.RUNS
            rr.RUNS = runs
            # la fixture _db retourne la CONNEXION — le chemin est construit
            db_path = Path(tmp) / "k.db"
            _db(db_path)
            try:
                res = rr.run_confirmation(spec, db_path=db_path,
                                           protocol={"protocol_id":
                                                     "protocol-v2",
                                                     "frozen_windows": [
                                                         {"start": "1970-01",
                                                          "end": "1970-02"}],
                                                     "embargo_hours": 0,
                                                     "windows_pass_required": 1,
                                                     "cost_stress_multiplier":
                                                         1.5,
                                                     "degradation_max_pct": 70,
                                                     "max_window_loss_pct": 15})
            finally:
                rr.RUNS = saved
            self.assertEqual(res["verdict"], "CONFIRMATION_BLOCKED")
            self.assertIn("spec d'exécution", res["reason"])
            self.assertIn("snapshot None", res["reason"])   # l'artefact ne
            # porte pas le snapshot courant (fixture minimale)


class TestLedgerFailClosed(unittest.TestCase):
    def test_ledger_echoue_confirme_echoue(self):
        """Bloc B6 : une écriture ledger échouée fait ÉCHOUER la
        confirmation (l'ancien check=False publiait un CONFIRMED sans sa
        ligne de budget)."""
        from scripts import research_runner as rr
        spec = {"family": "f", "strategy": "s", "hypothesis": "h"}
        real_run = rr.subprocess.run

        def failing_run(cmd, **kw):
            class R:
                returncode = 1
                stderr = "ledger verrouillé"
                stdout = ""
            return R()
        rr.subprocess.run = failing_run
        try:
            with self.assertRaises(RuntimeError):
                rr._log_ledger(spec, "PASS", "confirmation", "ref",
                               snapshot="S1", fail_closed=True)
        finally:
            rr.subprocess.run = real_run


if __name__ == "__main__":
    unittest.main()
