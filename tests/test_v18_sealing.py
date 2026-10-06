"""Tests v18 — le scellement et le risque complet (audit GLM 5.3
post-#149, PR-150).

    python tests/test_v18_sealing.py
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

from scripts import research_runner as rr  # noqa: E402
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


SPEC = {"id": "X",
        "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                 "train_start": 0, "train_end": 90 * H,
                 "validation_start": 90 * H, "validation_end": 200 * H},
        "signal": {"feature": "ret_1h", "op": "<=", "threshold": -1000.0,
                   "side": -1},
        "horizons": [6], "cost_pct": 0.0}


class TestExecutionSha(unittest.TestCase):
    def test_univers_change_le_sha_d_execution(self):
        """№1 : deux specs ne différant que par l'univers ont des shas
        d'exécution DIFFÉRENTS (l'ancien core les confondait)."""
        a = {**SPEC, "mode": "confirmation", "universe": "univ10"}
        b = {**SPEC, "mode": "confirmation", "universe": "autre"}
        self.assertNotEqual(rr.spec_execution_sha(a), rr.spec_execution_sha(b))
        # la mode seule ne change rien (la dérivation légitime)
        c = {**SPEC, "mode": "discovery", "universe": "univ10"}
        self.assertEqual(rr.spec_execution_sha(a), rr.spec_execution_sha(c))

    def test_universe_sha_est_le_contenu(self):
        """№7 : universe_sha = le hash du CONTENU du manifest — renommer le
        fichier ne change pas le sceau, modifier le contenu si."""
        with tempfile.TemporaryDirectory() as tmp:
            udir = Path(tmp) / "universe"
            udir.mkdir()
            manifest = {"symbols": {"BTCUSDT": {"first_bar_ms": 0,
                                                "last_bar_ms": 100 * H}}}
            (udir / "u.yaml").write_text(json.dumps(manifest),
                                         encoding="utf-8")
            import scripts.universe as uni
            saved = uni.UNIVERSE_DIR
            uni.UNIVERSE_DIR = udir
            try:
                s1 = rr.universe_sha("u")
                (udir / "u.yaml").write_text(
                    json.dumps(manifest) + "\n# modifié", encoding="utf-8")
                s2 = rr.universe_sha("u")
                self.assertNotEqual(s1, s2)   # le CONTENU est scellé
            finally:
                uni.UNIVERSE_DIR = saved


class TestLiqCausal(unittest.TestCase):
    def test_le_mode_simule_ne_regarde_pas_le_mae_futur(self):
        """№5 : en mode simulé, une position dont le MAE futur dépasse le
        seuil mais dont les MARKS observés ne franchissent JAMAIS le seuil
        SURVIT (la décision vient des marks, pas du futur)."""
        ev = [{"sym": "BTCUSDT", "t_ms": 0, "exit_ms": 12 * H, "side": -1,
               "ret_pct": -4.0, "entry": 100.0, "mae_pct": 9.6,  # > seuil 9,5
               "fund_pct": 0.0, "cost_pct": 0.0, "fund_prints": []}]
        # marks : le high ne dépasse JAMAIS 104 (adverse max 4 % < 9,5 %)
        closes = [100.0] * 12
        highs = [104.0] * 12
        marks = {"BTCUSDT": {"t": np.arange(12) * H,
                             "close": np.array(closes),
                             "high": np.array(highs),
                             "low": np.array([99.0] * 12)}}
        w = run_wallet_mtm(ev, marks, capital=100.0, cap_pct=1.0, lev=10.0,
                           liq_mode="simulated")
        # le MAE du kernel (hi de la fenêtre) dit 9,6 ≥ 9,5 → l'ANCIEN
        # moteur tuait ; le mode simulé causal regarde les marks observés
        # (max 4 %) → SURVIT et encaisse
        self.assertEqual(w["liqs"], 0)
        self.assertAlmostEqual(w["solde"], 100.4, places=6)  # +4 % de 1 $

    def test_le_mode_stress_garde_la_borne_ex_ante(self):
        """Le mode stress conserve l'absorption à l'entrée (la borne
        conservatrice explicite, les deux conventions coexistent nommées)."""
        ev = [{"sym": "BTCUSDT", "t_ms": 0, "exit_ms": 12 * H, "side": -1,
               "ret_pct": -4.0, "entry": 100.0, "mae_pct": 9.6,
               "fund_pct": 0.0, "cost_pct": 0.0, "fund_prints": []}]
        closes = [100.0] * 12
        marks = {"BTCUSDT": {"t": np.arange(12) * H,
                             "close": np.array(closes),
                             "high": np.array([104.0] * 12),
                             "low": np.array([99.0] * 12)}}
        w = run_wallet_mtm(ev, marks, capital=100.0, cap_pct=1.0, lev=10.0,
                           liq_mode="stress")
        self.assertEqual(w["liqs"], 1)
        self.assertAlmostEqual(w["solde"], 99.0, places=6)


class TestMultipliciteUnique(unittest.TestCase):
    def test_le_state_et_le_checker_partagent_le_n(self):
        """№6 : confirmation_multiplicity est LA définition — discoveries
        et PREREG exclus."""
        from scripts.lab_ledger import confirmation_multiplicity
        entries = [{"verdict": "PASS", "_mode": "confirmation"},
                   {"verdict": "DISCOVERY_FAIL", "_mode": "discovery"},
                   {"verdict": "PREREG", "_mode": "confirmation"},
                   {"verdict": "FAIL", "_mode": "confirmation",
                    "reverify": True}]
        # les reverify comptent AUSSI dans le N (cumulatif) — le fix №1 de
        # PR-147 ne les exempte que des PLAFOONDS, pas de la multiplicité
        self.assertEqual(confirmation_multiplicity(entries), 2)


if __name__ == "__main__":
    unittest.main()
