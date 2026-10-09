"""C1+C3 (bug-hunter ronde 4) — le plan de permutation du WORKER est
dimensionné par le BH du lot, et le tri du grind admet les specs YAML.

C1 : le worker appelait run_discovery() sans n_perm → défaut 99 → plancher
     de p = 1/100 = 0,01. Le BH du `select` exige p <= q/m au rang 1 : avec
     la queue bonsai (37 specs), seuil = 0,0027 — AUCUN candidat du worker
     ne pouvait jamais survivre au BH, quel que soit son edge. Le fix
     PR-198 (cmd_grind, bh_min_perms) n'avait jamais été porté sur le
     worker. Même loi que le grind : n_perm = bh_min_perms(len(lot)).
C3 : la queue admet .yaml/.yml/.json (le worker aussi), mais cmd_grind
     parsait chaque file en JSON pour lire compute.class → json.JSONDecode
     Error sur une spec YAML VALIDE, avant la moindre mesure.

    python tests/test_c1_worker_perm_sizing.py
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_worker as rw  # noqa: E402
from scripts import research_runner as rr  # noqa: E402
from scripts.research_runner import bh_min_perms  # noqa: E402

SPEC = """\
id: EXP-{sid}
hypothesis: sizing n_perm / tri yaml
data:
  symbols: [BTCUSDT]
  # fenetres int ms epoch (garde A4 de #229 sur le combine : une date ISO
  # est un FAILED_PERMANENT en vrai run — les fixtures suivent la doctrine
  # deja appliquee par #225 pour test_research_worker.py)
  train_start: 1735689600000
  train_end: 1738368000000
  validation_start: 1738368000000
  validation_end: 1740787200000
signal:
  feature: funding_rate
  op: ">="
  threshold: 0
horizons: [24]
{compute}
"""


def _mk_queue(base: Path, n: int, suffix: str = ".json") -> Path:
    q = base / "queue"
    q.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (q / f"EXP-{i:03d}{suffix}").write_text(
            SPEC.format(sid=f"{i:03d}", compute=""), encoding="utf-8")
    return q


class TestWorkerPermSizing(unittest.TestCase):
    """La boucle complète du worker, moteur mocké — le plan n_perm."""

    def _run(self, tmp: Path, fake, n_specs: int = 11):
        patches = [
            mock.patch.object(rw, "RUNTIME", tmp / "rt"),
            mock.patch.object(rw, "CHECKPOINT",
                              tmp / "rt" / "grind_checkpoint.json"),
            mock.patch.object(rw, "LEASE", tmp / "rt" / "worker.json"),
            mock.patch.object(rw, "LOCK", tmp / "rt" / "worker.lock"),
            mock.patch.object(rw, "ARCHIVE", tmp / "rt" / "archive"),
            mock.patch.object(rw, "_git_engine_dirty", lambda: False),
            mock.patch.object(rw, "MAX_RETRIES", 3),
            mock.patch.object(rr, "run_discovery", fake),
            mock.patch.object(rr, "_passes", lambda res, spec: False),
        ]
        q = _mk_queue(tmp, n_specs)
        for p in patches:
            p.start()
        try:
            return rw.run_worker(q, db_path=tmp / "nope.db")
        finally:
            for p in patches:
                p.stop()

    def test_n_perm_dimensionne_par_le_lot(self):
        # 11 specs → n_perm = ceil(11/0.10) - 1 = 109 : le BH du rang 1
        # (0.10/11 = 0.0091) redevient ATTEIGNABLE (plancher 1/110 = 0.0091)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            calls = []

            def fake(spec, db_path=None, n_perm=99):
                calls.append((spec["id"], n_perm))
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            self.assertEqual(self._run(tmp, fake, n_specs=11), rw.EXIT_OK)
            attendu = bh_min_perms(11)
            self.assertEqual(attendu, 109)
            self.assertEqual(
                {n for _, n in calls}, {attendu},
                "le worker doit passer le n_perm DIMENSIONNÉ au moteur, "
                "pas le défaut 99")
            ck = json.loads(
                (tmp / "rt" / "grind_checkpoint.json").read_text())
            self.assertEqual(ck["n_perm"], attendu)

    def test_petit_lot_conserve_le_plancher_99(self):
        # doctrine bh_min_perms : le plancher de 99 est conservé pour ne
        # pas dégrader les petits lots (m <= 10 → BH atteignable à 99)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            calls = []

            def fake(spec, db_path=None, n_perm=99):
                calls.append((spec["id"], n_perm))
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            self.assertEqual(self._run(tmp, fake, n_specs=5), rw.EXIT_OK)
            self.assertEqual(bh_min_perms(5), 99)
            self.assertEqual({n for _, n in calls}, {99})

    def test_n_perm_scelle_dans_l_item_done(self):
        # provenance : l'item DONE porte le plan de permutation utilisé —
        # sans ceci, une p publiée est intraceable à son plan d'échantillon
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            ck_path = tmp / "rt" / "grind_checkpoint.json"

            def fake(spec, db_path=None, n_perm=99):
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            self.assertEqual(self._run(tmp, fake, n_specs=11), rw.EXIT_OK)
            ck = json.loads(ck_path.read_text())
            self.assertEqual(ck["items"]["EXP-000"]["n_perm"],
                             bh_min_perms(11))

    def test_divergence_n_perm_signalee_sans_remesure(self):
        # un item DONE mesuré sous un AUTRE plan porte une p non comparable
        # au BH du lot actuel : signalé au checkpoint (n_perm_stale), et
        # PAS re-mesuré (le skip reste la compétence de l'identité, #220)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            ck_path = tmp / "rt" / "grind_checkpoint.json"
            calls = []

            def fake(spec, db_path=None, n_perm=99):
                calls.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1,
                        "snapshot": "s"}

            self.assertEqual(self._run(tmp, fake, n_specs=11), rw.EXIT_OK)
            self.assertEqual(len(calls), 11)
            # falsification : EXP-000 aurait été mesuré sous n_perm=42
            ck = json.loads(ck_path.read_text())
            ck["items"]["EXP-000"]["n_perm"] = 42
            ck_path.write_text(json.dumps(ck), encoding="utf-8")

            self.assertEqual(self._run(tmp, fake, n_specs=11), rw.EXIT_OK)
            self.assertEqual(len(calls), 11,
                             "un DONE avec un autre n_perm n'est pas "
                             "re-mesuré ici (skip = compétence identité)")
            ck = json.loads(ck_path.read_text())
            self.assertEqual(ck.get("n_perm_stale"), ["EXP-000"])


class TestGrindTriYaml(unittest.TestCase):
    """C3 : le tri du grind admet les specs YAML (le worker aussi)."""

    def _spec_body(self, sid: str, compute: str) -> str:
        return SPEC.format(sid=sid,
                           compute=f"compute:\n  class: {compute}\n")

    def test_yaml_valide_est_trie_et_mesure_sans_crash(self):
        # EXP-a.yaml (medium) sort AVANT EXP-b.json (small) en ordre alpha,
        # mais le tri par classe compute doit inverser : small (1) d'abord.
        # SUR LE CODE PRÉ-FIX, ce test lève json.JSONDecodeError au tri.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            q = tmp / "queue"
            q.mkdir(parents=True)
            (q / "EXP-a.yaml").write_text(
                self._spec_body("a", "medium"), encoding="utf-8")
            (q / "EXP-b.json").write_text(
                self._spec_body("b", "small"), encoding="utf-8")
            ordre = []

            def fake_screen(spec, db):
                ordre.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1}

            patches = [
                mock.patch.object(rr, "_stage1_screen", fake_screen),
                mock.patch.object(rr, "_passes",
                                  lambda res, spec: False),
                mock.patch.object(rr, "_resource_guard",
                                  lambda: (True, "")),
            ]
            for p in patches:
                p.start()
            try:
                rc = rr.cmd_grind(argparse.Namespace(
                    queue=str(q), db=str(tmp / "k.db")))
            finally:
                for p in patches:
                    p.stop()
            self.assertEqual(rc, 0)
            self.assertEqual(ordre, ["EXP-b", "EXP-a"],
                             "le tri par classe compute doit s'appliquer "
                             "aux specs YAML comme aux JSON")

    def test_yaml_invalide_ne_bloque_pas_le_tri(self):
        # un YAML illisible est classé par défaut au tri (la mesure jugera)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            q = tmp / "queue"
            q.mkdir(parents=True)
            (q / "EXP-cass.yaml").write_text(
                "compute: [unclosed", encoding="utf-8")
            (q / "EXP-ok.json").write_text(
                self._spec_body("ok", "small"), encoding="utf-8")
            ordre = []

            def fake_screen(spec, db):
                ordre.append(spec["id"])
                return {"verdict": "DISCOVERY_FAIL", "n": 5, "mean": 0.1}

            # la spec cassée sera jugée par load_spec à la mesure : on
            # mocke aussi load_spec pour isoler le TRI du JUGEMENT
            real_load_spec = rr.load_spec
            patches = [
                mock.patch.object(rr, "_stage1_screen", fake_screen),
                mock.patch.object(rr, "_passes",
                                  lambda res, spec: False),
                mock.patch.object(rr, "_resource_guard",
                                  lambda: (True, "")),
                mock.patch.object(rr, "load_spec",
                                  lambda f: real_load_spec(f)
                                  if f.suffix == ".json"
                                  else {"id": f.stem, "horizons": [6]}),
            ]
            for p in patches:
                p.start()
            try:
                rc = rr.cmd_grind(argparse.Namespace(
                    queue=str(q), db=str(tmp / "k.db")))
            finally:
                for p in patches:
                    p.stop()
            self.assertEqual(rc, 0)
            self.assertEqual(sorted(ordre), ["EXP-cass", "EXP-ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
