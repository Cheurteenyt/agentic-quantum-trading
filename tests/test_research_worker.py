"""PR-161 — les invariants du research worker (crash-consistency).

Couvre les P1 de l'audit post-#160 : FAILED_PERMANENT réellement terminal,
queue_sha lié aux chemins, migration schema_version=2 (jamais silencieuse),
identité engine/db/queue, métriques dérivées de items, dédup du ledger,
et le refus des collisions de spec_id.

    python tests/test_research_worker.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_worker as rw  # noqa: E402

SPEC_BODY = """\
id: EXP-T1
hypothesis: test de collision/migration
data:
  symbols: [BTCUSDT]
  train_start: "2025-01-01"
  train_end: "2025-02-01"
  validation_start: "2025-02-01"
  validation_end: "2025-03-01"
signal:
  feature: funding_rate
  op: ">="
  threshold: 0
horizons: [24]
"""


def _mk_queue(base: Path, specs: dict) -> Path:
    q = base / "queue"
    q.mkdir(parents=True, exist_ok=True)
    for name, body in specs.items():
        p = q / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return q


class TestQueueSha(unittest.TestCase):
    def test_path_bound(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            qa = _mk_queue(td / "a", {"EXP-A.json": "x: 1"})
            qb = _mk_queue(td / "b", {"EXP-B.json": "x: 1"})
            self.assertNotEqual(rw._queue_sha(qa), rw._queue_sha(qb))

    def test_stable_and_recursive(self):
        with tempfile.TemporaryDirectory() as td:
            q = _mk_queue(Path(td),
                          {"EXP-A.json": "x: 1", "sub/EXP-B.json": "y: 2"})
            self.assertEqual(rw._queue_sha(q), rw._queue_sha(q))


class TestTerminal(unittest.TestCase):
    def test_done_terminal(self):
        self.assertTrue(
            rw._is_terminal({"state": "DONE", "spec_sha": "abc"}, "abc"))

    def test_permanent_terminal(self):
        self.assertTrue(rw._is_terminal(
            {"state": "FAILED_PERMANENT", "spec_sha": "abc"}, "abc"))

    def test_permanent_sans_sha_rejoue(self):
        # l'item PR-160 (sans spec_sha) n'était PAS terminal — le bug audit
        self.assertFalse(rw._is_terminal({"state": "FAILED_PERMANENT"}, "abc"))

    def test_spec_modifie_remesure(self):
        self.assertFalse(rw._is_terminal(
            {"state": "DONE", "spec_sha": "abc"}, "zzz"))


class TestMigration(unittest.TestCase):
    def test_legacy_sans_identite_archive_frais(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ck = {"items": {"EXP-1": {"state": "DONE", "spec_sha": "a"}},
                  "job_id": "old"}
            with mock.patch.object(rw, "ARCHIVE", td / "archive"):
                ck2, note = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
            self.assertEqual(ck2, {})
            self.assertIn("LEGACY", note)
            self.assertTrue(any((td / "archive").iterdir()))

    def test_ere_pr160_transporte_les_items(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ck = {"items": {"EXP-1": {"state": "DONE", "spec_sha": "a"}},
                  "db_snapshot": "db1", "queue_sha": "ancien-algo",
                  "git_sha": "440648e"}
            with mock.patch.object(rw, "ARCHIVE", td / "archive"):
                ck2, note = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
            self.assertTrue(ck2["items"]["EXP-1"]["migrated"])
            self.assertEqual(ck2["schema_version"], rw.SCHEMA_VERSION)
            self.assertEqual(ck2["engine_sha"], "e1")
            self.assertIn("transportés", note)
            self.assertTrue(any((td / "archive").iterdir()))

    def test_db_inconnue_pas_de_transport(self):
        with tempfile.TemporaryDirectory() as td:
            ck = {"items": {"EXP-1": {"state": "DONE"}},
                  "db_snapshot": "db-AUTRE"}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"):
                ck2, _ = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
            self.assertEqual(ck2, {})

    def test_schema_courant_intact(self):
        ck = {"schema_version": rw.SCHEMA_VERSION, "items": {}}
        ck2, note = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
        self.assertIs(ck2, ck)
        self.assertEqual(note, "")


class TestIdentite(unittest.TestCase):
    def test_moteur_change_reinitialise(self):
        with tempfile.TemporaryDirectory() as td:
            ck = {"schema_version": 2, "engine_sha": "ANCIEN",
                  "db_snapshot": "db1", "queue_sha": "q1",
                  "items": {"EXP-1": {"state": "DONE"}}}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"):
                ck2, notes = rw._reconcile_identity(ck, "db1", "NOUVEAU",
                                                    "q1")
            self.assertEqual(ck2, {})
            self.assertTrue(notes and "IDENTITÉ" in notes[0])

    def test_db_change_reinitialise(self):
        with tempfile.TemporaryDirectory() as td:
            ck = {"schema_version": 2, "engine_sha": "e1",
                  "db_snapshot": "ANCIENNE", "queue_sha": "q1", "items": {}}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"):
                ck2, _ = rw._reconcile_identity(ck, "db1", "e1", "q1")
            self.assertEqual(ck2, {})

    def test_queue_seule_change_conserve(self):
        with tempfile.TemporaryDirectory() as td:
            ck = {"schema_version": 2, "engine_sha": "e1",
                  "db_snapshot": "db1", "queue_sha": "ANCIENNE-Q",
                  "items": {"EXP-1": {"state": "DONE"}}}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"):
                ck2, notes = rw._reconcile_identity(ck, "db1", "e1",
                                                    "NOUVELLE-Q")
            self.assertTrue(ck2["items"])
            self.assertEqual(ck2["queue_sha"], "NOUVELLE-Q")
            self.assertIn("conservés", notes[0])


class TestLoadSpecs(unittest.TestCase):
    def test_collision_refusee(self):
        with tempfile.TemporaryDirectory() as td:
            q = _mk_queue(Path(td),
                          {"a/EXP-1.json": "{}", "b/EXP-1.json": "{}"})
            with self.assertRaises(ValueError) as ctx:
                rw._load_specs(q)
            self.assertIn("collision", str(ctx.exception))

    def test_done_exclu_et_sha_present(self):
        with tempfile.TemporaryDirectory() as td:
            q = _mk_queue(Path(td), {"EXP-1.json": "x: 1",
                                     "done/EXP-0.json": "x: 0"})
            out = rw._load_specs(q)
            self.assertEqual([sid for _, sid, _ in out], ["EXP-1"])
            self.assertTrue(all(len(sha) == 16 for _, _, sha in out))


class TestStatusCounts(unittest.TestCase):
    def test_derive_de_items(self):
        items = {"a": {"state": "DONE"}, "b": {"state": "DONE"},
                 "c": {"state": "FAILED_PERMANENT"},
                 "d": {"state": "FAILED_RETRYABLE"}}
        self.assertEqual(rw._status_counts(items, 6),
                         {"done": 2, "failed_permanent": 1,
                          "failed_retryable": 1, "remaining": 3})


class TestEngineSha(unittest.TestCase):
    def test_lie_aux_chemins_et_au_contenu(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            f1 = td / "mod_a.py"
            f2 = td / "mod_b.py"
            f1.write_text("x = 1")
            f2.write_text("y = 2")
            with mock.patch.object(rw, "ROOT", td), \
                 mock.patch.object(rw, "ENGINE_FILES", (f1, f2)):
                a = rw._engine_sha()
                f2.write_text("y = 3")
                self.assertNotEqual(rw._engine_sha(), a)


class TestRunWorker(unittest.TestCase):
    """La boucle complète avec le moteur mocké — skip/résumé/terminal."""

    def _run(self, tmp: Path, fake, max_retries=3):
        patches = [
            mock.patch.object(rw, "RUNTIME", tmp / "rt"),
            mock.patch.object(rw, "CHECKPOINT",
                              tmp / "rt" / "grind_checkpoint.json"),
            mock.patch.object(rw, "LEASE", tmp / "rt" / "worker.json"),
            mock.patch.object(rw, "LOCK", tmp / "rt" / "worker.lock"),
            mock.patch.object(rw, "ARCHIVE", tmp / "rt" / "archive"),
            mock.patch.object(rw, "_git_engine_dirty", lambda: False),
            mock.patch.object(rw, "MAX_RETRIES", max_retries),
        ]
        from scripts import research_runner as rr
        patches += [
            mock.patch.object(rr, "run_discovery", fake),
            mock.patch.object(rr, "_passes", lambda res, spec: False),
        ]
        q = _mk_queue(tmp, {"EXP-T1.json": SPEC_BODY})
        for p in patches:
            p.start()
        try:
            return rw.run_worker(q, db_path=tmp / "nope.db")
        finally:
            for p in patches:
                p.stop()

    def test_cycle_complet_puis_skip(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            ck_path = tmp / "rt" / "grind_checkpoint.json"
            calls = []

            def fake(spec, db_path=None):
                calls.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            self.assertEqual(self._run(tmp, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-T1"])
            ck = json.loads(ck_path.read_text())
            self.assertEqual(ck["status"], "DONE")
            self.assertEqual(ck["schema_version"], rw.SCHEMA_VERSION)
            self.assertEqual(ck["items"]["EXP-T1"]["state"], "DONE")
            self.assertEqual(len(ck["items"]["EXP-T1"]["spec_sha"]), 16)
            self.assertEqual(
                ck["manifest"],
                [{"id": "EXP-T1",
                  "sha": ck["items"]["EXP-T1"]["spec_sha"]}])
            # 2e lancement : la spec est SKIPPÉE (pas de re-mesure)
            self.assertEqual(self._run(tmp, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-T1"])

    def test_permanent_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            ck_path = tmp / "rt" / "grind_checkpoint.json"
            calls = []

            def fake(spec, db_path=None):
                calls.append(spec["id"])
                raise ValueError("spec invalide (test)")

            self.assertEqual(self._run(tmp, fake, max_retries=1),
                             rw.EXIT_FAILED)
            ck = json.loads(ck_path.read_text())
            self.assertEqual(ck["status"], "DONE_WITH_ERRORS")
            self.assertEqual(ck["items"]["EXP-T1"]["state"],
                             "FAILED_PERMANENT")
            self.assertTrue(ck["items"]["EXP-T1"]["spec_sha"])
            # LE BUG DE L'AUDIT : le FAILED_PERMANENT est RÉELLEMENT terminal
            self.assertEqual(self._run(tmp, fake), rw.EXIT_FAILED)
            self.assertEqual(calls, ["EXP-T1"])

    def test_id_fichier_incoherent_permanent(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            calls = []

            def fake(spec, db_path=None):
                calls.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 1, "mean": 0.0,
                        "snapshot": "s"}

            body = SPEC_BODY.replace("id: EXP-T1", "id: EXP-AUTRE")
            q = _mk_queue(tmp, {"EXP-T1.json": body})
            patches = [
                mock.patch.object(rw, "RUNTIME", tmp / "rt"),
                mock.patch.object(rw, "CHECKPOINT",
                                  tmp / "rt" / "grind_checkpoint.json"),
                mock.patch.object(rw, "LEASE", tmp / "rt" / "worker.json"),
                mock.patch.object(rw, "LOCK", tmp / "rt" / "worker.lock"),
                mock.patch.object(rw, "ARCHIVE", tmp / "rt" / "archive"),
                mock.patch.object(rw, "_git_engine_dirty", lambda: False),
                mock.patch.object(rw, "MAX_RETRIES", 1),
            ]
            from scripts import research_runner as rr
            patches += [
                mock.patch.object(rr, "run_discovery", fake),
                mock.patch.object(rr, "_passes", lambda res, spec: False),
            ]
            for p in patches:
                p.start()
            try:
                rc = rw.run_worker(q, db_path=tmp / "nope.db")
            finally:
                for p in patches:
                    p.stop()
            self.assertEqual(rc, rw.EXIT_FAILED)
            self.assertEqual(calls, [])
            ck = json.loads(
                (tmp / "rt" / "grind_checkpoint.json").read_text())
            self.assertEqual(ck["items"]["EXP-T1"]["state"],
                             "FAILED_PERMANENT")


class TestLedgerDedup(unittest.TestCase):
    def _log(self, ledger: Path, snapshot: str = "snap1"):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "lab_ledger.py"),
             "--ledger", str(ledger), "log",
             "--date", "2026-10-07",
             "--family", "testfam", "--strategy", "teststr",
             "--hypothesis", "h1", "--verdict", "DISCOVERY_FAIL",
             "--mode", "discovery", "--snapshot", snapshot],
            capture_output=True, text=True, cwd=ROOT)

    def test_meme_mesure_noop(self):
        with tempfile.TemporaryDirectory() as td:
            led = Path(td) / "trials.jsonl"
            r1 = self._log(led)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            r2 = self._log(led)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertIn("NO-OP", r2.stdout)
            lines = [l for l in led.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)

    def test_snapshot_different_logge(self):
        with tempfile.TemporaryDirectory() as td:
            led = Path(td) / "trials.jsonl"
            r1 = self._log(led, "snap1")
            self.assertEqual(r1.returncode, 0, r1.stderr)
            r2 = self._log(led, "snap2")
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertNotIn("NO-OP", r2.stdout)
            lines = [l for l in led.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
