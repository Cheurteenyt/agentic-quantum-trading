"""Tests du registre de candidats — la validation OOS postérieure à la campagne.

    python tests/test_backtest_v2_candidates.py
    python scripts/run_tests.py backtest_v2

Le point central : un survivant de campagne n'est PAS une stratégie validée.
Ces tests vérifient que le registre refuse les doublons, filtre par âge réel,
applique les règles de décision CONFIRMED/REJECTED, expire les candidats
rouillés, et que le CHECK SQL défend contre les statuts invalides.

Stdlib unittest (pytest absent). Aucune dépendance externe.
"""
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from backend.services.backtest_v2.candidates import (
    Candidate,
    CandidateRegistry,
    CandidateStatus,
    DuplicateCandidateError,
)


def _days_ago_iso(days: float) -> str:
    """Chaîne ISO du moment il y a `days` jours (UTC, timespec seconde)."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def make_candidate(
    identity_key: str,
    run_id: str,
    days_ago: float = 40.0,
    sharpe_oos: float = 1.0,
    status: str = "pending",
    params: dict | None = None,
) -> Candidate:
    return Candidate(
        identity_key=identity_key,
        run_id=run_id,
        discovered_at=_days_ago_iso(days_ago),
        sharpe_oos_discovery=sharpe_oos,
        n_tested_in_campaign=10000,
        params=params if params is not None else {"threshold": 1, "window": 20},
        status=status,
    )


def fetch_row(reg: CandidateRegistry, identity_key: str, run_id: str) -> dict | None:
    row = reg.con.execute(
        "SELECT * FROM candidates WHERE identity_key=? AND run_id=?",
        (identity_key, run_id),
    ).fetchone()
    return dict(row) if row is not None else None


class TestDecide(unittest.TestCase):
    """Logique de décision pure (pas de DB) — facile à auditer."""

    def test_confirmed_when_all_criteria_met(self):
        status, reason = CandidateRegistry._decide(0.8, 200, 1.0)
        self.assertEqual(status, CandidateStatus.CONFIRMED.value)
        self.assertIn("confirme", reason)

    def test_rejected_low_sharpe(self):
        status, reason = CandidateRegistry._decide(0.3, 200, 1.0)
        self.assertEqual(status, CandidateStatus.REJECTED.value)
        self.assertIn("forward_sharpe", reason)

    def test_rejected_none_sharpe(self):
        # None = non mesuré = jamais un pass, même si trades présents.
        status, reason = CandidateRegistry._decide(None, 200, 1.0)
        self.assertEqual(status, CandidateStatus.REJECTED.value)
        self.assertIn("non mesure", reason)

    def test_rejected_none_trades(self):
        status, reason = CandidateRegistry._decide(0.8, None, 1.0)
        self.assertEqual(status, CandidateStatus.REJECTED.value)
        self.assertIn("non mesure", reason)

    def test_rejected_low_trades(self):
        status, reason = CandidateRegistry._decide(0.8, 50, 1.0)
        self.assertEqual(status, CandidateStatus.REJECTED.value)
        self.assertIn("forward_trades", reason)

    def test_rejected_degradation(self):
        # sharpe_oos_discovery=2.0 -> seuil = 1.0 ; 0.6 est une chute > 50 %.
        status, reason = CandidateRegistry._decide(0.6, 200, 2.0)
        self.assertEqual(status, CandidateStatus.REJECTED.value)
        self.assertIn("degradation", reason)


class TestCandidateRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = CandidateRegistry(Path(self.tmp.name) / "candidates.db")

    def tearDown(self):
        self.reg.close()
        self.tmp.cleanup()

    # ----------------------------------------------------------- register

    def test_register_returns_id(self):
        cid = self.reg.register(make_candidate("k1", "r1"))
        self.assertIsInstance(cid, int)
        self.assertEqual(cid, 1)

    def test_register_refuses_duplicate(self):
        self.reg.register(make_candidate("k1", "r1"))
        with self.assertRaises(DuplicateCandidateError):
            self.reg.register(make_candidate("k1", "r1"))
        # La ligne n'a pas été dupliquée : le UNIQUE SQL + la défense codée
        # tiennent le coup.
        n = self.reg.con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        self.assertEqual(n, 1)

    def test_invalid_status_rejected_by_sql_check(self):
        # Le CHECK SQL défend contre un statut fantaisie, pas la discipline.
        with self.assertRaises(sqlite3.IntegrityError):
            self.reg.register(make_candidate("kbad", "r1", status="bogus"))

    # ------------------------------------------------------------ pending

    def test_pending_returns_all_when_no_min_age(self):
        self.reg.register(make_candidate("k1", "r1", days_ago=1))
        self.reg.register(make_candidate("k2", "r1", days_ago=5))
        self.assertEqual(len(self.reg.pending()), 2)

    def test_pending_excludes_younger_than_min_age(self):
        # Découvert il y a 10 jours ; exigence 30 jours -> exclus.
        self.reg.register(make_candidate("k1", "r1", days_ago=10))
        self.assertEqual(self.reg.pending(min_age_days=30), [])

    def test_pending_includes_older_than_min_age(self):
        # Découvert il y a 40 jours ; exigence 30 jours -> inclus.
        self.reg.register(make_candidate("k1", "r1", days_ago=40))
        result = self.reg.pending(min_age_days=30)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].identity_key, "k1")

    def test_pending_only_pending_status(self):
        self.reg.register(make_candidate("k_pending", "r1", days_ago=40))
        # Celui-ci est confirmé -> ne doit plus apparaître en PENDING.
        self.reg.register(make_candidate("k_confirmed", "r1", days_ago=40))
        self.reg.confirm("k_confirmed", "r1", 0.8, 200)
        result = self.reg.pending(min_age_days=0)
        keys = [c.identity_key for c in result]
        self.assertIn("k_pending", keys)
        self.assertNotIn("k_confirmed", keys)

    # ------------------------------------------------------------ confirm

    def test_confirm_good_numbers_confirmed_and_stored(self):
        self.reg.register(make_candidate("k1", "r1", sharpe_oos=1.0))
        status = self.reg.confirm("k1", "r1", 0.8, 200)
        self.assertEqual(status, CandidateStatus.CONFIRMED.value)
        row = fetch_row(self.reg, "k1", "r1")
        self.assertEqual(row["status"], "confirmed")
        self.assertEqual(row["forward_sharpe"], 0.8)
        self.assertEqual(row["forward_trades"], 200)
        self.assertIsNotNone(row["evaluated_at"])
        self.assertIn("confirme", row["decision_reason"])

    def test_confirm_low_forward_sharpe_rejected_with_reason(self):
        self.reg.register(make_candidate("k1", "r1", sharpe_oos=1.0))
        status = self.reg.confirm("k1", "r1", 0.2, 200)
        self.assertEqual(status, CandidateStatus.REJECTED.value)
        row = fetch_row(self.reg, "k1", "r1")
        self.assertIn("forward_sharpe", row["decision_reason"])

    def test_confirm_none_forward_sharpe_rejected(self):
        self.reg.register(make_candidate("k1", "r1", sharpe_oos=1.0))
        status = self.reg.confirm("k1", "r1", None, 200)
        self.assertEqual(status, CandidateStatus.REJECTED.value)
        row = fetch_row(self.reg, "k1", "r1")
        self.assertEqual(row["status"], "rejected")
        self.assertIn("non mesure", row["decision_reason"])

    def test_confirm_not_found_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.reg.confirm("inexistant", "rX", 0.8, 200)

    # ------------------------------------------------------- expire_stale

    def test_expire_stale_expires_old_pending(self):
        self.reg.register(make_candidate("old", "r1", days_ago=100))
        n = self.reg.expire_stale(max_age_days=90)
        self.assertEqual(n, 1)
        self.assertEqual(fetch_row(self.reg, "old", "r1")["status"], "expired")

    def test_expire_stale_keeps_recent_pending(self):
        self.reg.register(make_candidate("recent", "r1", days_ago=10))
        n = self.reg.expire_stale(max_age_days=90)
        self.assertEqual(n, 0)
        self.assertEqual(fetch_row(self.reg, "recent", "r1")["status"], "pending")

    def test_expire_stale_ignores_non_pending(self):
        # Un candidat déjà confirmé (même vieux) n'est pas expiré.
        self.reg.register(make_candidate("done", "r1", days_ago=100))
        self.reg.confirm("done", "r1", 0.8, 200)
        n = self.reg.expire_stale(max_age_days=0)
        self.assertEqual(n, 0)
        self.assertEqual(fetch_row(self.reg, "done", "r1")["status"], "confirmed")

    # ------------------------------------------------------------- stats

    def test_stats_counts_per_status(self):
        self.reg.register(make_candidate("a1", "r1", days_ago=40))
        self.reg.confirm("a1", "r1", 0.8, 200)  # confirmed
        self.reg.register(make_candidate("b1", "r1", days_ago=40))
        self.reg.confirm("b1", "r1", 0.2, 200)  # rejected
        self.reg.register(make_candidate("p1", "r1", days_ago=40))  # pending
        self.reg.register(make_candidate("e1", "r1", days_ago=100))
        self.reg.expire_stale(max_age_days=90)  # expired

        s = self.reg.stats()
        self.assertEqual(s["confirmed"], 1)
        self.assertEqual(s["rejected"], 1)
        self.assertEqual(s["pending"], 1)
        self.assertEqual(s["expired"], 1)
        self.assertEqual(s["total"], 4)

    def test_stats_confirmation_rate_coherent(self):
        self.reg.register(make_candidate("a1", "r1", days_ago=40))
        self.reg.confirm("a1", "r1", 0.8, 200)
        self.reg.register(make_candidate("a2", "r1", days_ago=40))
        self.reg.confirm("a2", "r1", 0.9, 300)
        self.reg.register(make_candidate("b1", "r1", days_ago=40))
        self.reg.confirm("b1", "r1", 0.2, 200)
        self.reg.register(make_candidate("b2", "r1", days_ago=40))
        self.reg.confirm("b2", "r1", 0.8, 50)
        self.reg.register(make_candidate("p1", "r1", days_ago=40))
        self.reg.register(make_candidate("e1", "r1", days_ago=100))
        self.reg.expire_stale(max_age_days=90)

        s = self.reg.stats()
        # La somme des statuts == total
        self.assertEqual(
            s["confirmed"] + s["rejected"] + s["pending"] + s["expired"], s["total"]
        )
        # taux = confirmés / décidés (expirés et pending ne comptent pas)
        self.assertAlmostEqual(s["confirmation_rate"], 2 / 4)

    def test_params_json_roundtrip(self):
        params = {"threshold": 3, "window": 20, "nested": {"a": [1, 2]}}
        self.reg.register(make_candidate("k1", "r1", params=params))
        result = self.reg.pending(min_age_days=0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].params, params)


if __name__ == "__main__":
    unittest.main(verbosity=2)
