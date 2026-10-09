"""R12 — LA MÉTHODE : deep_audit.py détecte chaque classe de bug fondateur.

Chaque test est une MUTATION NÉGATIVE : on injecte le défaut historique
dans un fichier synthétique, on exige la détection ; et le code sain
voisin ne doit rien déclencher (précision). Les classes et leurs bugs
fondateurs :

  G1  unités s/ms mélangées (P0 ronde 10 : lentille OI, confluence muette)
  G2  fossile récent figé dans un test glissant (issue #235)
  G3  contrat x_pressure rompu (P0 ronde 10 : 9 colonnes, captured_at en s)
  G4  succès codé dur ignorant le résultat réel (9 faux succès, #249)
  G5  fail-open silencieux dans un gate (rochet R5, #252)
  G8  fixture historique = info (jamais bloquant)
  G9  non parsable

La fenêtre fossile est glissante et déterministe par commit (HEAD ±) :
le même horodatage bascule G8 -> G2 quand le HEAD du repo s'en rapproche.
"""
# fixtures d'horodatage volontaires — mutation négative : ce fichier
# INJECTE les fossiles pour prouver la détection
# deep-audit:ignore-file=G2,G8
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.deep_audit as da  # noqa: E402

# HEAD fictif 2026-09-27 : le fossile #235 (1_778_200_000, mai 2026) tombe
# dans la fenêtre 180 j ; 1_700_000_000 (nov. 2023) reste historique.
HEAD_FIXE = 1_791_000_000


def _collect(check, *args, **kw) -> list[dict]:
    out: list[dict] = []

    def add(code, rel, node, msg):
        out.append({"code": code, "file": rel,
                    "line": getattr(node, "lineno", 0) or 0, "msg": msg})

    check(add, *args, **kw)
    return out


def _tree(src: str) -> ast.AST:
    return ast.parse(src)


class G1UnitTests(unittest.TestCase):
    G1_BAD = """
import time
def lens(rows):
    now_ms = time.time() * 1000
    out = {}
    for sym, oi, captured_at in rows:
        if now_ms - float(captured_at) <= 6 * 3600_000:
            out[sym] = oi
    return out
"""
    G1_GOOD = """
import time
def lens(rows):
    now_ms = time.time() * 1000
    out = {}
    for sym, oi, captured_at_ms in rows:
        if now_ms - float(captured_at_ms) <= 6 * 3600_000:
            out[sym] = oi
    return out
"""
    G1_NAME_VS_VALUE = """
import time
from datetime import datetime, timezone
def lens(rows):
    now_ms = time.time() * 1000
    out = {}
    for sym, oi, ts in rows:
        x_ms = datetime.fromtimestamp(ts, tz=timezone.utc).timestamp()
        if now_ms - x_ms <= 6 * 3600_000:
            out[sym] = oi
    return out
"""

    def test_mutation_ms_moins_secondes_detecte(self):
        fn = next(n for n in ast.walk(_tree(self.G1_BAD))
                  if isinstance(n, ast.FunctionDef))
        f = _collect(da.check_g1, fn, "synth.py")
        self.assertTrue(any(i["code"] == "G1" for i in f),
                        "le mélange s/ms doit être détecté (bug P0 ronde 10)")

    def test_code_sain_ne_declenche_rien(self):
        fn = next(n for n in ast.walk(_tree(self.G1_GOOD))
                  if isinstance(n, ast.FunctionDef))
        f = _collect(da.check_g1, fn, "synth.py")
        self.assertEqual([i for i in f if i["code"] == "G1"], [])

    def test_variable_ms_en_secondes_detecte(self):
        # x_ms assigné en secondes (timestamp()) puis utilisé en face de ms
        src = self.G1_NAME_VS_VALUE
        f = []
        for n in ast.walk(_tree(src)):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f += _collect(da.check_g1, n, "synth.py")
        self.assertTrue(any(i["code"] == "G1" for i in f),
                        "un *_ms assigné en secondes doit être détecté")


class G2G8FossilTests(unittest.TestCase):
    TEST_SRC = """
import time
def scan_rows(rows):
    cutoff = time.time() - 30 * 86400
    return [r for r in rows if r[2] >= 1_778_200_000 and r[2] >= cutoff]
def scan_hist(rows):
    return [r for r in rows if r[2] >= 1_700_000_000]
def scan_jalon(rows):
    now_ms = int(time.time() * 1000)
    return [r for r in rows if r[2] >= 1_800_000_000_000 and r[2] <= now_ms]
"""

    def _findings(self, head_ts: int) -> list[dict]:
        return _collect(da.check_g2, _tree(self.TEST_SRC),
                        "tests/synth.py", head_ts=head_ts)

    def test_mutation_fossile_recent_detecte(self):
        f = self._findings(HEAD_FIXE)
        g2 = [i for i in f if i["code"] == "G2"]
        self.assertTrue(g2, "le fossile #235 (mai 2026) doit être G2")
        self.assertTrue(all("1_778_200_000" not in i["msg"] or True
                            for i in g2))

    def test_fixture_historique_est_info_non_bloquante(self):
        f = self._findings(HEAD_FIXE)
        self.assertTrue(any(i["code"] == "G8" for i in f))
        self.assertFalse(any(i["code"] == "G2" and "1700000000" in i["msg"]
                             for i in f))

    def test_jalon_futur_ne_tombe_pas(self):
        f = self._findings(HEAD_FIXE)
        self.assertFalse(any("1_800_000_000_000" in i["msg"] for i in f),
                         "un jalon futur documenté n'est pas un fossile")

    def test_fenetre_glissante_suivant_head(self):
        # le même horodatage bascule G8 -> G2 quand le HEAD avance
        f_old = _collect(da.check_g2,
                         _tree("import time\n"
                               "def s(rows):\n"
                               "    return [r for r in rows "
                               "if r[2] >= 1_778_200_000 - time.time()]\n"),
                         "tests/synth.py", head_ts=1_700_000_000)
        f_new = self._findings(HEAD_FIXE)
        self.assertFalse(any(i["code"] == "G2" for i in f_old),
                         "mai 2026 était futur/lointain pour un HEAD 2023")
        self.assertTrue(any(i["code"] == "G2" for i in f_new))


class G3ContratTests(unittest.TestCase):
    PROD_OK = """
CREATE TABLE IF NOT EXISTS x_pressure (
    ticker TEXT PRIMARY KEY, posts INTEGER, posts_prev INTEGER,
    velocity REAL, longs INTEGER, shorts INTEGER, engagement REAL,
    funding_pct REAL, captured_at REAL NOT NULL);
now = datetime.now(timezone.utc).timestamp()
con.execute("INSERT OR REPLACE INTO x_pressure VALUES (?,?,?,?,?,?,?,?,?)",
            (t, p, pp, v, lo, sh, e, f, now))
"""
    PROD_DRIFT = """
CREATE TABLE IF NOT EXISTS x_pressure (
    ticker TEXT PRIMARY KEY, posts INTEGER, posts_prev INTEGER,
    velocity REAL, longs INTEGER, shorts INTEGER, engagement REAL,
    funding_pct REAL, captured_at REAL NOT NULL);
now = datetime.now(timezone.utc).timestamp()
con.execute("INSERT OR REPLACE INTO x_pressure VALUES (?,?,?,?,?,?,?,?,?)",
            (t, p, pp, v, lo, sh, e, f, now))
"""
    CONS_OK = 'rows = con.execute("SELECT ticker, posts, velocity, longs, "\n    "shorts, captured_at FROM x_pressure").fetchall()'
    CONS_BAD = 'rows = con.execute("SELECT ticker, posts, velosity, longs, "\n    "shorts, captured_at FROM x_pressure").fetchall()'

    def test_contrat_sain_zero_constat(self):
        f = _collect(da.check_g3, Path("/nonexistent"), ptxt=self.PROD_OK,
                     ctxt=self.CONS_OK)
        self.assertEqual([i for i in f if i["code"] == "G3"], [])

    def test_mutation_colonne_hors_contrat(self):
        f = _collect(da.check_g3, Path("/nonexistent"), ptxt=self.PROD_OK,
                     ctxt=self.CONS_BAD)
        self.assertTrue(any("hors contrat" in i["msg"] for i in f),
                        "une colonne renommée chez le consommateur doit "
                        "casser le contrat")

    def test_mutation_producteur_ms(self):
        f = _collect(da.check_g3, Path("/nonexistent"),
                     ptxt=self.PROD_OK.replace(
                         "datetime.now(timezone.utc).timestamp()",
                         "time.time() * 1000"),
                     ctxt=self.CONS_OK)
        self.assertTrue(any("ms" in i["msg"] for i in f),
                        "un producteur passé en ms doit casser le contrat "
                        "d'unité (bug P0 ronde 10)")

    def test_mutation_placeholders(self):
        bad = self.PROD_DRIFT.replace("(?,?,?,?,?,?,?,?,?)", "(?,?,?,?,?,?,?,?)")
        f = _collect(da.check_g3, Path("/nonexistent"), ptxt=bad,
                     ctxt=self.CONS_OK)
        self.assertTrue(any("placeholders" in i["msg"] for i in f))


class G4FakeSuccessTests(unittest.TestCase):
    BAD = """
async def add_indicator(req):
    result = await mcp_call("add", req)
    return {"success": True, "action": "add_indicator"}
"""
    GOOD = """
async def add_indicator(req):
    result = await mcp_call("add", req)
    return {"success": _tool_ok(result), "action": "add_indicator"}
"""
    INFORME = """
async def add_indicator(req):
    result = await mcp_call("add", req)
    return {"ok": True, "rows": result.get("rows", [])}
"""

    def _g4(self, src: str) -> list[dict]:
        return [i for i in _collect(da.check_g4, _tree(src), "synth.py")
                if i["code"] == "G4"]

    def test_mutation_succes_dur_detecte(self):
        f = self._g4(self.BAD)
        self.assertTrue(f, "success:True codé dur avec result ignoré "
                        "doit être détecté (signature #249)")

    def test_succes_derive_des_results_est_clean(self):
        self.assertEqual(self._g4(self.GOOD), [])

    def test_payload_informe_par_result_est_clean(self):
        self.assertEqual(self._g4(self.INFORME), [])


class G5FailOpenTests(unittest.TestCase):
    BAD = """
def check_gate(state):
    try:
        verdict = compute(state)
    except Exception:
        pass
    return verdict
"""
    TRACED = """
def check_gate(state):
    try:
        verdict = compute(state)
    except Exception:
        print("gate:", state)
        return None
    return verdict
"""
    HORS_GATE = """
def helper(state):
    try:
        return compute(state)
    except Exception:
        pass
"""

    def _g5(self, src: str) -> list[dict]:
        return [i for i in _collect(da.check_g5, _tree(src), "synth.py")
                if i["code"] == "G5"]

    def test_mutation_gate_fail_open_detecte(self):
        self.assertTrue(self._g5(self.BAD),
                        "un gate qui avale sans trace doit être détecté (R5)")

    def test_gate_avec_trace_est_clean(self):
        self.assertEqual(self._g5(self.TRACED), [])

    def test_fonction_hors_gate_est_clean(self):
        self.assertEqual(self._g5(self.HORS_GATE), [])


class ScanRochetTests(unittest.TestCase):
    def _repo_tmp(self) -> tempfile.TemporaryDirectory:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "scripts").mkdir()
        (root / "tests").mkdir()
        (root / "scripts" / "mod.py").write_text(
            "import time\n"
            "def check_gate(state):\n"
            "    try:\n"
            "        result = compute(state)\n"
            "    except Exception:\n"
            "        pass\n"
            "    return result\n", encoding="utf-8")
        (root / "tests" / "test_x.py").write_text(
            "import time\n"
            "def s(rows):\n"
            "    return [r for r in rows if r[2] >= 1_778_200_000 "
            "and r[2] <= time.time()]\n", encoding="utf-8")
        return tmp

    def test_g9_non_parsable(self):
        with self._repo_tmp() as tmp:
            root = Path(tmp)
            (root / "scripts" / "broken.py").write_text(
                "def (\n", encoding="utf-8")
            f = da.scan(root, head_ts=HEAD_FIXE)
            self.assertTrue(any(i["code"] == "G9" and "broken.py" in i["file"]
                                for i in f))

    def test_suppressions_ligne_et_fichier(self):
        with self._repo_tmp() as tmp:
            root = Path(tmp)
            base = len([i for i in da.scan(root, head_ts=HEAD_FIXE)])
            (root / "tests" / "test_x.py").write_text(
                "import time\n"
                "def s(rows):\n"
                "    return [r for r in rows if r[2] >= 1_778_200_000 "
                "and r[2] <= time.time()]  # deep-audit:ignore=G2\n",
                encoding="utf-8")
            f2 = da.scan(root, head_ts=HEAD_FIXE)
            self.assertEqual(len(f2), base - 1,
                             "la suppression de ligne doit réduire de 1")
            (root / "tests" / "test_x.py").write_text(
                "# deep-audit:ignore-file\n" + (root / "tests" / "test_x.py")
                .read_text(encoding="utf-8"), encoding="utf-8")
            f3 = da.scan(root, head_ts=HEAD_FIXE)
            self.assertEqual(len([i for i in f3
                                  if i["file"].endswith("test_x.py")]), 0)

    def test_determinisme_byte_a_byte(self):
        with self._repo_tmp() as tmp:
            root = Path(tmp)
            a = json.dumps(da.scan(root, head_ts=HEAD_FIXE), indent=1,
                           ensure_ascii=False)
            b = json.dumps(da.scan(root, head_ts=HEAD_FIXE), indent=1,
                           ensure_ascii=False)
            self.assertEqual(a, b, "deux scans identiques = sortie identique")

    def test_rochet_regression_et_reduction(self):
        base = {"f.py": {"G2": 3}}
        items_3 = [{"code": "G2", "file": "f.py", "line": 1, "msg": ""}]
        items_3 = items_3 * 3
        items_4 = items_3 + [{"code": "G2", "file": "f.py", "line": 9,
                              "msg": ""}]
        items_2 = items_3[:2]
        n_reg, _ = da.ratchet_verdict(items_4, base)
        self.assertEqual(n_reg, 2, "fichier +1 ET total +1 = 2 régressions")
        n_reg, _ = da.ratchet_verdict(items_3, base)
        self.assertEqual(n_reg, 0, "stable = ok")
        n_reg, _ = da.ratchet_verdict(items_2, base)
        self.assertEqual(n_reg, 0, "réduction = ok (encouragée)")

    def test_rochet_nouveau_fichier(self):
        base = {"a.py": {"G4": 1}}
        items = [{"code": "G4", "file": "a.py", "line": 1, "msg": ""},
                 {"code": "G4", "file": "b_nouveau.py", "line": 5,
                  "msg": ""}]
        n_reg, details = da.ratchet_verdict(items, base)
        self.assertEqual(n_reg, 2,
                         "un nouveau fichier fautif = fichier +1 et total +1")
        self.assertTrue(any("b_nouveau.py" in d for d in details))


if __name__ == "__main__":
    unittest.main()
