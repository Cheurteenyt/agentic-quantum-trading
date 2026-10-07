"""PR-161 — les invariants du research worker (crash-consistency).

Couvre les P1 de l'audit post-#160 : FAILED_PERMANENT réellement terminal,
queue_sha lié aux chemins, migration schema_version=2 (jamais silencieuse),
identité engine/db/queue, métriques dérivées de items, dédup du ledger,
et le refus des collisions de spec_id.

    python tests/test_research_worker.py
"""
from __future__ import annotations

import json
import os
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
            with mock.patch.object(rw, "ARCHIVE", td / "archive"), \
                 mock.patch.object(rw, "_engine_sha_at", lambda c: "e1"):
                ck2, note = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
            self.assertTrue(ck2["items"]["EXP-1"]["migrated"])
            self.assertEqual(ck2["schema_version"], rw.SCHEMA_VERSION)
            self.assertEqual(ck2["engine_sha"], "e1")
            self.assertIn("transportés", note)
            self.assertIn("prouvé", note)
            self.assertTrue(any((td / "archive").iterdir()))

    def test_ere_pr160_moteur_inverifiable_pas_de_transport(self):
        with tempfile.TemporaryDirectory() as td:
            ck = {"items": {"EXP-1": {"state": "DONE"}},
                  "db_snapshot": "db1", "git_sha": "deadbeef00",
                  "queue_sha": "q"}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"):
                ck2, note = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
            self.assertEqual(ck2, {})
            self.assertIn("invérifiable", note)

    def test_ere_pr160_moteur_change_pas_de_transport(self):
        with tempfile.TemporaryDirectory() as td:
            ck = {"items": {"EXP-1": {"state": "DONE"}},
                  "db_snapshot": "db1", "git_sha": "440648e",
                  "queue_sha": "q"}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"), \
                 mock.patch.object(rw, "_engine_sha_at", lambda c: "ANCIEN"):
                ck2, note = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
            self.assertEqual(ck2, {})
            self.assertIn("MOTEUR a changé", note)

    def test_engine_sha_at_commit_reel(self):
        # intégration : le moteur à 440648e est calculable depuis git —
        # PR-179 : un clone SHALLOW (l'ancien défaut CI) n'a pas les
        # ancêtres → skip propre au lieu d'un faux échec
        shallow = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            capture_output=True, text=True, cwd=ROOT).stdout.strip()
        if shallow == "true":
            self.skipTest("clone shallow : l'ancêtre 440648e est absent")
        self.assertIsNotNone(rw._engine_sha_at("440648e"))
        self.assertIsNone(rw._engine_sha_at("0000000"))

    def test_db_derivee_transporte_quand_meme(self):
        # PR-163 (P0 du bug-hunter) : la db est appendée en continu —
        # le drift ne bloque PLUS le transport (moteur prouvé identique)
        with tempfile.TemporaryDirectory() as td:
            ck = {"items": {"EXP-1": {"state": "DONE", "spec_sha": "a"}},
                  "db_snapshot": "ANCIENNE", "git_sha": "440648e",
                  "queue_sha": "q"}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"), \
                 mock.patch.object(rw, "_engine_sha_at", lambda c: "e1"):
                ck2, note = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
            self.assertTrue(ck2["items"]["EXP-1"]["migrated"])
            self.assertIn("db dérivée", note)
            self.assertEqual(ck2["db_snapshot"], "db1")

    def test_ere_pr160_sans_git_sha_inverifiable(self):
        with tempfile.TemporaryDirectory() as td:
            ck = {"items": {"EXP-1": {"state": "DONE"}},
                  "db_snapshot": "db-AUTRE"}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"):
                ck2, note = rw._migrate_checkpoint(ck, "db1", "e1", "q1")
            self.assertEqual(ck2, {})
            self.assertIn("invérifiable", note)

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

    def test_db_derive_conserve(self):
        # PR-163 : la db dérive en continu (append) — items CONSERVÉS
        with tempfile.TemporaryDirectory() as td:
            ck = {"schema_version": 2, "engine_sha": "e1",
                  "db_snapshot": "ANCIENNE", "queue_sha": "q1",
                  "items": {"EXP-1": {"state": "DONE"}}}
            with mock.patch.object(rw, "ARCHIVE", Path(td) / "archive"):
                ck2, notes = rw._reconcile_identity(ck, "db1", "e1", "q1")
            self.assertTrue(ck2["items"])
            self.assertEqual(ck2["db_snapshot"], "db1")
            self.assertTrue(notes and "dérivé" in notes[0])

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
    def test_derive_de_items_fallback(self):
        items = {"a": {"state": "DONE"}, "b": {"state": "DONE"},
                 "c": {"state": "FAILED_PERMANENT"},
                 "d": {"state": "FAILED_RETRYABLE"}}
        self.assertEqual(rw._status_counts(items, None, 6),
                         {"done": 2, "failed_permanent": 1,
                          "failed_retryable": 1, "remaining": 3})

    def test_derive_du_manifeste(self):
        # PR-163 : seul le manifeste compte — une spec modifiée (sha ≠)
        # ou disparue de la queue reste « remaining », un item orphelin
        # ne masque plus rien
        manifest = [{"id": "a", "sha": "s1"}, {"id": "b", "sha": "s2"},
                    {"id": "c", "sha": "s3"}, {"id": "e", "sha": "s5"}]
        items = {"a": {"state": "DONE", "spec_sha": "s1"},
                 "b": {"state": "FAILED_PERMANENT", "spec_sha": "s2"},
                 "c": {"state": "DONE", "spec_sha": "ANCIEN"},
                 "d": {"state": "DONE", "spec_sha": "orphelin"}}
        self.assertEqual(rw._status_counts(items, manifest, 4),
                         {"done": 1, "failed_permanent": 1,
                          "failed_retryable": 0, "remaining": 2})


class TestQueueShaDone(unittest.TestCase):
    def test_done_exclu_du_sel(self):
        # PR-163 : le sel queue et le manifeste décrivent le MÊME ensemble
        with tempfile.TemporaryDirectory() as td:
            q1 = _mk_queue(Path(td) / "q1", {"EXP-1.json": "x: 1"})
            q2 = _mk_queue(Path(td) / "q2",
                           {"EXP-1.json": "x: 1", "done/EXP-0.json": "x: 0"})
            self.assertEqual(rw._queue_sha(q1), rw._queue_sha(q2))


class TestSingleton(unittest.TestCase):
    def test_flock_refuse_second(self):
        import fcntl as _fcntl
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rt = tmp / "rt"
            rt.mkdir()
            fh = open(rt / "worker.lock", "w")
            _fcntl.flock(fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            patches = [
                mock.patch.object(rw, "RUNTIME", rt),
                mock.patch.object(rw, "CHECKPOINT",
                                  rt / "grind_checkpoint.json"),
                mock.patch.object(rw, "LEASE", rt / "worker.json"),
                mock.patch.object(rw, "LOCK", rt / "worker.lock"),
                mock.patch.object(rw, "ARCHIVE", rt / "archive"),
                mock.patch.object(rw, "_git_engine_dirty", lambda: False),
            ]
            for p in patches:
                p.start()
            try:
                rc = rw.run_worker(
                    _mk_queue(tmp, {"EXP-T1.json": SPEC_BODY}),
                    db_path=tmp / "nope.db")
            finally:
                _fcntl.flock(fh, _fcntl.LOCK_UN)
                fh.close()
                for p in patches:
                    p.stop()
            self.assertEqual(rc, rw.EXIT_FAILED)


class TestStatus(unittest.TestCase):
    def _run_status(self, ck: dict, lease: dict, rt: Path) -> dict:
        (rt / "grind_checkpoint.json").write_text(json.dumps(ck))
        (rt / "worker.json").write_text(json.dumps(lease))
        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch.object(rw, "CHECKPOINT",
                               rt / "grind_checkpoint.json"), \
             mock.patch.object(rw, "LEASE", rt / "worker.json"):
            with contextlib.redirect_stdout(buf):
                rw.status()
        return json.loads(buf.getvalue())

    def test_shape_counts_et_hb_dead(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rt = tmp / "rt"
            rt.mkdir()
            ck = {"job_id": "j1", "git_sha": "g", "engine_sha": "e",
                  "schema_version": 2, "status": "RUNNING",
                  "items": {"a": {"state": "DONE", "spec_sha": "s1"}},
                  "manifest": [{"id": "a", "sha": "s1"},
                               {"id": "b", "sha": "s2"}],
                  "candidates": [], "queue_total": 2}
            # pid vivant (le test lui-même) mais sa cmdline ne porte PAS
            # research_worker.py en basename → alive False (anti-recyclage)
            d = self._run_status(
                ck, {"pid": os.getpid(),
                     "heartbeat_at": "2026-10-07T05:00:00+00:00"}, rt)
            self.assertEqual(d["done"], 1)
            self.assertEqual(d["remaining"], 1)
            self.assertFalse(d["worker_alive"])
            self.assertFalse(d["hb_dead"])
            self.assertIn("lease_stale", d)

    def test_pid_worker_reconnu_par_basename(self):
        # PR-163 : un process dont un argument porte EXACTEMENT le
        # basename research_worker.py est reconnu (et test_research_worker.py
        # ne l'est pas — la sous-chaîne suffisait avant)
        import time as _time
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rt = tmp / "rt"
            rt.mkdir()
            ck = {"status": "RUNNING", "items": {}, "manifest": [],
                  "candidates": [], "queue_total": 0}
            proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(5)",
                 "research_worker.py"])
            try:
                for _ in range(60):
                    try:
                        with open(f"/proc/{proc.pid}/cmdline", "rb") as fh:
                            if b"research_worker" in fh.read():
                                break
                    except OSError:
                        pass
                    _time.sleep(0.05)
                d = self._run_status(
                    ck, {"pid": proc.pid,
                         "heartbeat_at": "2026-10-07T05:00:00+00:00"}, rt)
                self.assertTrue(d["worker_alive"])
                # le même pid avec la cmdline du TEST ne l'est pas
                d2 = self._run_status(
                    ck, {"pid": os.getpid(),
                         "heartbeat_at": "2026-10-07T05:00:00+00:00"}, rt)
                self.assertFalse(d2["worker_alive"])
            finally:
                proc.kill()
                proc.wait()

    def test_lease_corrompu_ne_tue_pas_status(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rt = tmp / "rt"
            rt.mkdir()
            ck = {"status": "RUNNING", "items": {}, "manifest": [],
                  "candidates": [], "queue_total": 0}
            (rt / "grind_checkpoint.json").write_text(json.dumps(ck))
            (rt / "worker.json").write_text("{corrompu")
            import io
            import contextlib
            buf = io.StringIO()
            with mock.patch.object(rw, "CHECKPOINT",
                                   rt / "grind_checkpoint.json"), \
                 mock.patch.object(rw, "LEASE", rt / "worker.json"):
                with contextlib.redirect_stdout(buf):
                    rw.status()
            self.assertIn("status", json.loads(buf.getvalue()))


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

    def test_git_en_erreur_est_sale(self):
        # PR-162 : git indisponible = on ne peut pas PROUVER l'arbre propre
        from types import SimpleNamespace
        with mock.patch.object(
                rw.subprocess, "run",
                return_value=SimpleNamespace(returncode=128, stdout="")):
            self.assertTrue(rw._git_engine_dirty())


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
