"""P0-③ (audit 2026-10-08) — dataset_window_sha : le skip du worker ne
voyait que le spec_sha, jamais les DONNÉES.

Le contrat (fail-closed) :
  - une CORRECTION historique dans la fenêtre scientifique d'une spec
    DONE (klines 1h ou funding, y compris AVANT train_start — le warmup
    expanding charge tout l'historique) exige une RE-MESURE ;
  - un APPEND au-delà de validation_end (l'actif continue d'exister) ne
    doit PAS invalider la mesure — le skip reste stable ;
  - une barre open_time == validation_end n'appartient PAS à la fenêtre
    (convention demi-ouverte du runner) ;
  - seules les klines 1h comptent (la mesure ne résout que lui) ;
  - un item DONE/FAILED_PERMANENT sans dataset_window_sha (ère legacy)
    est re-mesuré une fois puis scellé ;
  - dws incalculable (spec illisible, db illisible) = jamais terminal ;
  - le manifeste scelle le dws attendu et --status ne compte plus « done »
    un item dont la fenêtre a changé.

    python tests/test_dataset_window_sha.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_worker as rw  # noqa: E402
from scripts.label_matrix import dataset_window_sha  # noqa: E402

H_MS = 3_600_000
END_MS = 20 * H_MS          # validation_end de la spec de test
TRAIN_START = 5 * H_MS
TRAIN_END = 10 * H_MS
VAL_START = 10 * H_MS


def _db(path: Path, n_bars: int = 25) -> Path:
    """Une mini-warehouse déterministe : BTCUSDT 1h (0..n-1 × H_MS) + 2
    prints funding — les barres >= END_MS simulent le « futur » appendable
    (l'actif continue d'exister au-delà de la fenêtre scientifique)."""
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER,
        rate REAL);
    """)
    for i in range(n_bars):
        con.execute(
            "INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
            (i * H_MS, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i))
    con.execute("INSERT INTO funding_history VALUES ('BTCUSDT', ?, 0.01)",
                (6 * H_MS,))
    con.execute("INSERT INTO funding_history VALUES ('BTCUSDT', ?, 0.02)",
                (14 * H_MS,))
    con.commit()
    con.close()
    return path


SPEC_BODY = f"""\
id: EXP-DWS
hypothesis: P0-3 dataset_window_sha
data:
  symbols: [BTCUSDT]
  train_start: {TRAIN_START}
  train_end: {TRAIN_END}
  validation_start: {VAL_START}
  validation_end: {END_MS}
signal:
  feature: funding_rate
  op: ">="
  threshold: 0
horizons: [24]
"""


def _mk_queue(base: Path, body: str = SPEC_BODY,
              name: str = "EXP-DWS.json") -> Path:
    q = base / "queue"
    q.mkdir(parents=True, exist_ok=True)
    (q / name).write_text(body, encoding="utf-8")
    return q


class TestDwsCalc(unittest.TestCase):
    """Le hash fenêtré : il bouge si et seulement si le contenu sous la
    fenêtre bouge."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _db(Path(self.tmp.name) / "k.db")
        self.dws = dataset_window_sha(self.db, END_MS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stable_et_prefixe(self):
        # le cache mtime doit rendre l'appel idempotent sur le même état
        self.assertEqual(dataset_window_sha(self.db, END_MS), self.dws)
        self.assertTrue(self.dws.startswith("dws-"))
        self.assertEqual(len(self.dws), 20)

    def test_append_apres_la_fenetre_ne_bouge_pas(self):
        # l'actif continue d'exister : l'append nocturne (>= END_MS) ne
        # doit PAS invalider une spec DONE
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
                    (30 * H_MS, 130.0, 131.0, 129.0, 130.5))
        con.commit()
        con.close()
        self.assertEqual(dataset_window_sha(self.db, END_MS), self.dws)

    def test_funding_apres_la_fenetre_ne_bouge_pas(self):
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO funding_history VALUES ('BTCUSDT', ?, 0.05)",
                    (25 * H_MS,))
        con.commit()
        con.close()
        self.assertEqual(dataset_window_sha(self.db, END_MS), self.dws)

    def test_correction_dans_la_fenetre_bouge(self):
        con = sqlite3.connect(self.db)
        con.execute("UPDATE klines SET close=close*1.5 WHERE open_time=?",
                    (5 * H_MS,))
        con.commit()
        con.close()
        self.assertNotEqual(dataset_window_sha(self.db, END_MS), self.dws)

    def test_insertion_barre_manquante_dans_la_fenetre_bouge(self):
        # l'état de départ a un TROU volontaire (barre 12 absente) :
        # son remplissage change la fenêtre (gapless des labels)
        con = sqlite3.connect(self.db)
        con.execute("DELETE FROM klines WHERE open_time=?", (12 * H_MS,))
        con.commit()
        con.close()
        dws_troue = dataset_window_sha(self.db, END_MS)
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
            (12 * H_MS, 112.0, 113.0, 111.0, 112.5))
        con.commit()
        con.close()
        self.assertNotEqual(dataset_window_sha(self.db, END_MS), dws_troue)

    def test_correction_funding_dans_la_fenetre_bouge(self):
        con = sqlite3.connect(self.db)
        con.execute("UPDATE funding_history SET rate=0.09 WHERE funding_time=?",
                    (6 * H_MS,))
        con.commit()
        con.close()
        self.assertNotEqual(dataset_window_sha(self.db, END_MS), self.dws)

    def test_borne_demi_ouverte_la_barre_frontiere_est_exclue(self):
        con = sqlite3.connect(self.db)
        con.execute("UPDATE klines SET close=close*2 WHERE open_time=?",
                    (END_MS,))  # open_time == validation_end
        con.commit()
        con.close()
        self.assertEqual(dataset_window_sha(self.db, END_MS), self.dws)

    def test_autres_intervalles_ignores(self):
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO klines VALUES ('BTCUSDT','4h',?,?,?,?,?,1.0)",
            (0, 100.0, 101.0, 99.0, 100.5))
        con.commit()
        con.close()
        self.assertEqual(dataset_window_sha(self.db, END_MS), self.dws)

    def test_warmup_gauche_couvert_une_correction_avant_train_start_bouge(self):
        # la borne gauche est la PREMIÈRE barre (les features expanding
        # chargent tout l'historique antérieur) — une correction à t=1h,
        # bien avant train_start (5h), doit invalider
        con = sqlite3.connect(self.db)
        con.execute("UPDATE klines SET close=close*1.7 WHERE open_time=?",
                    (1 * H_MS,))
        con.commit()
        con.close()
        self.assertNotEqual(dataset_window_sha(self.db, END_MS), self.dws)

    def test_db_absente_hash_du_vide_deterministe(self):
        absent = Path(self.tmp.name) / "nope.db"
        a = dataset_window_sha(absent, END_MS)
        b = dataset_window_sha(absent, END_MS)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("dws-"))
        self.assertNotEqual(a, self.dws)


class TestDwsTerminal(unittest.TestCase):
    """_is_terminal exige le dws : égal, différent, legacy, incalculable.
    (Signature combinée avec l'identité d'exécution de PR #220 : le skip
    est fail-closed sur les DEUX autorités — identité ET fenêtre.)"""

    ID = "a1b2c3d4e5f60718"

    def _ok(self, prev, sha="abc", dws="d1"):
        return rw._is_terminal(prev, sha, self.ID, dws)

    def test_dws_egal_terminal(self):
        self.assertTrue(self._ok(
            {"state": "DONE", "spec_sha": "abc",
             "execution_identity": self.ID, "dataset_window_sha": "d1"}))

    def test_dws_different_remesure(self):
        # LA protection P0-③ : les données sous la fenêtre ont changé
        self.assertFalse(self._ok(
            {"state": "DONE", "spec_sha": "abc",
             "execution_identity": self.ID, "dataset_window_sha": "d1"},
            dws="d2"))

    def test_item_legacy_sans_dws_remesure(self):
        self.assertFalse(self._ok(
            {"state": "DONE", "spec_sha": "abc",
             "execution_identity": self.ID}))

    def test_dws_incalculable_jamais_terminal(self):
        self.assertFalse(self._ok(
            {"state": "DONE", "spec_sha": "abc",
             "execution_identity": self.ID, "dataset_window_sha": "d1"},
            dws=None))

    def test_permanent_sans_dws_remesure(self):
        self.assertFalse(self._ok(
            {"state": "FAILED_PERMANENT", "spec_sha": "abc",
             "execution_identity": self.ID}))


class TestDwsSkipCycle(unittest.TestCase):
    """Le cycle e2e du worker avec une vraie mini-warehouse — le skip
    devient sensible aux données sous la fenêtre."""

    def _run(self, tmp: Path, db: Path, fake, max_retries=3):
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
        q = _mk_queue(tmp)
        for p in patches:
            p.start()
        try:
            return rw.run_worker(q, db_path=db)
        finally:
            for p in patches:
                p.stop()

    def _ck(self, tmp: Path) -> dict:
        return json.loads(
            (tmp / "rt" / "grind_checkpoint.json").read_text())

    def test_cycle_scelle_puis_skip(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            db = _db(tmp / "k.db")
            calls = []

            def fake(spec, db_path=None, **_kw):
                calls.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-DWS"])
            ck = self._ck(tmp)
            it = ck["items"]["EXP-DWS"]
            self.assertEqual(it["state"], "DONE")
            # l'item porte le dws d'EXÉCUTION = le dws réel de la db
            self.assertEqual(it["dataset_window_sha"],
                             dataset_window_sha(db, END_MS))
            self.assertEqual(ck["manifest"][0]["dws"], it["dataset_window_sha"])
            # 2e lancement : SKIP (ni la spec ni la fenêtre n'ont bougé)
            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-DWS"])

    def test_correction_historique_remesure(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            db = _db(tmp / "k.db")
            calls = []

            def fake(spec, db_path=None, **_kw):
                calls.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-DWS"])
            # LA CORRECTION HISTORIQUE : une barre TRAIN re-écrite
            con = sqlite3.connect(db)
            con.execute("UPDATE klines SET close=close*1.5 WHERE open_time=?",
                        (7 * H_MS,))
            con.commit()
            con.close()
            # le checkpoint ne porte PAS encore le dws → re-mesure, puis
            # le nouvel item scellé porte le NOUVEAU dws
            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-DWS", "EXP-DWS"])
            it = self._ck(tmp)["items"]["EXP-DWS"]
            self.assertEqual(it["dataset_window_sha"],
                             dataset_window_sha(db, END_MS))
            # et le skip redevient stable
            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-DWS", "EXP-DWS"])

    def test_append_apres_fenetre_skip_conserve(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            db = _db(tmp / "k.db")
            calls = []

            def fake(spec, db_path=None, **_kw):
                calls.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            # l'APPEND nocturne : des barres au-delà de validation_end
            con = sqlite3.connect(db)
            con.execute("INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
                        (30 * H_MS, 130.0, 131.0, 129.0, 130.5))
            con.commit()
            con.close()
            # le skip DOIT rester (l'append ne touche pas la fenêtre)
            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-DWS"])

    def test_item_legacy_sans_dws_remesure_une_fois(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            db = _db(tmp / "k.db")
            calls = []

            def fake(spec, db_path=None, **_kw):
                calls.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            # un checkpoint ère pré-P0-③ : l'item DONE ne porte pas de dws
            tmp_rt = tmp / "rt"
            tmp_rt.mkdir(parents=True)
            (tmp_rt / "grind_checkpoint.json").write_text(json.dumps({
                "schema_version": rw.SCHEMA_VERSION,
                "items": {"EXP-DWS": {"state": "DONE", "spec_sha": None}},
            }))
            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-DWS"])
            it = self._ck(tmp)["items"]["EXP-DWS"]
            self.assertTrue(it["dataset_window_sha"].startswith("dws-"))
            # puis terminal
            self.assertEqual(self._run(tmp, db, fake), rw.EXIT_OK)
            self.assertEqual(calls, ["EXP-DWS"])

    def test_spec_illisible_ne_bloque_pas_la_boucle(self):
        # le parse tolérant du skip : une spec cassée = dws None = pas de
        # skip — le run normal la classe (FAILED_PERMANENT), la boucle vit
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            db = _db(tmp / "k.db")
            calls = []

            def fake(spec, db_path=None, **_kw):
                calls.append(spec["id"])
                raise ValueError("spec invalide (test)")

            # yaml VALIDE mais spec incomplète : _spec_validation_end →
            # None (pas de data.validation_end), load_spec lève ValueError
            # (permanent) — la boucle survit, l'item n'a jamais de dws
            body = "x: 1"
            q = _mk_queue(tmp, body=body, name="EXP-BROKEN.json")
            self.assertIn("EXP-BROKEN.json", [p.name for p in q.iterdir()])
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
                rc = rw.run_worker(q, db_path=db)
            finally:
                for p in patches:
                    p.stop()
            self.assertEqual(rc, rw.EXIT_FAILED)
            # la spec cassée lève AU parse (load_spec), jamais au fake —
            # la boucle a survécu et l'a classée FAILED_PERMANENT
            self.assertEqual(calls, [])
            ck = self._ck(tmp)
            self.assertEqual(ck["items"]["EXP-BROKEN"]["state"],
                             "FAILED_PERMANENT")
            # jamais de dws : jamais skipée
            self.assertIsNone(
                ck["items"]["EXP-BROKEN"].get("dataset_window_sha"))


class TestDwsStatusCounts(unittest.TestCase):
    """--status : un DONE à dws périmé n'est plus done (remaining)."""

    def test_done_dws_perime_devient_remaining(self):
        manifest = [{"id": "a", "sha": "s1", "dws": "d-NOUVEAU"}]
        items = {"a": {"state": "DONE", "spec_sha": "s1",
                       "dataset_window_sha": "d-ANCIEN"}}
        self.assertEqual(rw._status_counts(items, manifest, 1),
                         {"done": 0, "failed_permanent": 0,
                          "failed_retryable": 0, "remaining": 1})

    def test_done_dws_ok_compte(self):
        manifest = [{"id": "a", "sha": "s1", "dws": "d1"}]
        items = {"a": {"state": "DONE", "spec_sha": "s1",
                       "dataset_window_sha": "d1"}}
        self.assertEqual(rw._status_counts(items, manifest, 1),
                         {"done": 1, "failed_permanent": 0,
                          "failed_retryable": 0, "remaining": 0})

    def test_manifeste_sans_dws_aucune_exigence_ajoutee(self):
        # manifeste ère pré-P0-③ (pas de clé dws) : comptage inchangé
        manifest = [{"id": "a", "sha": "s1"}]
        items = {"a": {"state": "DONE", "spec_sha": "s1"}}
        self.assertEqual(rw._status_counts(items, manifest, 1),
                         {"done": 1, "failed_permanent": 0,
                          "failed_retryable": 0, "remaining": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
