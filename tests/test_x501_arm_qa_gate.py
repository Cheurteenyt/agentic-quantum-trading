"""Tests du gate A5 du pont d'armement x501 (fail-closed sur le QA statique).

Le pont d'armement (x501_arm_v23.py) est le dernier câble avant exécution
réelle. Son contrôle A5 — « qa_kscript_x501.py doit passer 0 échec » —
était fail-open : `qa_ok = "0 échec" in out or r.returncode == 0`. La
moitié du critère suffisait : un QA qui imprime « 3 échec(s) » en sortant
0 ARMait le pont ; un QA qui sort != 0 après avoir imprimé « 0 échec »
aussi. Les deux critères sont alignés en nominal (le QA sort
`1 if total else 0`) — le `or` ne changeait le verdict QUE dans les cas
pathologiques, exactement là où un pont d'armement doit fail-closed.

    python tests/test_x501_arm_qa_gate.py
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import x501_arm_v23 as arm  # noqa: E402

ARM_SRC = (ROOT / "scripts" / "x501_arm_v23.py").read_text(encoding="utf-8")


class TestQaGate(unittest.TestCase):
    """La fonction pure : les DEUX preuves, ou rien."""

    def test_nominal_pass(self):
        # QA vert nominal : « PASS — 0 échec » + exit 0
        self.assertTrue(arm.qa_gate(0, "===\nRESULTAT GLOBAL : PASS — 0 échec\n"))

    def test_echecs_avec_returncode_zero_est_refuse(self):
        # LE bug : comptage cassé / wrapper qui mange le code retour.
        # Avant le fix : ARMÉ. Après : NO-ARM.
        self.assertFalse(arm.qa_gate(0, "RESULTAT GLOBAL : 3 échec(s)"))

    def test_collision_dizaines_est_refuse(self):
        # 2e bug, attrapé par ces tests : le pivot « 0 échec » matchait
        # « 1**0 échec**(s) », « 2**0 échec**(s) »… un QA rouge à 10, 20,
        # 100 échecs imprimait un faux vert. Le pivot exact immunise.
        for total in (10, 20, 30, 100, 1000):
            self.assertFalse(
                arm.qa_gate(0, f"RESULTAT GLOBAL : {total} échec(s)"),
                f"{total} échec(s) armait le pont")

    def test_returncode_nonzero_malgre_zero_echec_est_refuse(self):
        # QA qui détecte une erreur système APRÈS le résumé (crash final,
        # timeout propre) : sortie != 0, résumé vert. Avant : ARMÉ.
        self.assertFalse(arm.qa_gate(1, "RESULTAT GLOBAL : PASS — 0 échec"))

    def test_echecs_avec_returncode_nonzero_est_refuse(self):
        self.assertFalse(arm.qa_gate(1, "RESULTAT GLOBAL : 12 échec(s)"))

    def test_sortie_vide_est_refuse(self):
        # QA crashé avant d'imprimer quoi que ce soit, exit 0 (wrapper) :
        # aucun résumé = aucune preuve = NO-ARM.
        self.assertFalse(arm.qa_gate(0, ""))


class TestOracleStatique(unittest.TestCase):
    """Le site d'appel doit utiliser qa_gate — le `or returncode` ne doit
    JAMAIS revenir (AST, pas grep : l'affichage peut mentir)."""

    def test_aucun_or_sur_returncode_dans_le_pont(self):
        tree = ast.parse(ARM_SRC)
        for node in ast.walk(tree):
            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                txt = ast.unparse(node)
                self.assertNotIn(
                    "returncode", txt,
                    f"fail-open réintroduit : `{txt}`")

    def test_le_site_a5_appelle_qa_gate(self):
        self.assertIn(
            "if not qa_gate(r.returncode, r.stdout + r.stderr):", ARM_SRC,
            "l'appel site A5 doit passer par la fonction gate")

    def test_la_fonction_est_un_and(self):
        tree = ast.parse(ARM_SRC)
        fns = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "qa_gate"]
        self.assertEqual(len(fns), 1)
        # corps hors docstring (même convention que audit_except_pass)
        body = [s for s in fns[0].body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        self.assertEqual(len(body), 1, "qa_gate = une seule expression return")
        ret = body[0]
        self.assertIsInstance(ret, ast.Return)
        self.assertIsInstance(ret.value, ast.BoolOp)
        self.assertIsInstance(ret.value.op, ast.And, "AND, pas OR")


if __name__ == "__main__":
    unittest.main()
