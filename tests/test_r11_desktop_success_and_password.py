#!/usr/bin/env python3
"""Ronde 11 — desktop.py : le succès se dérive des results MCP, le password
ne voyage plus en query param.

AVANT :
  - 9 handlers renvoyaient « success: True » codé dur — une action ratée
    (Timeout 30s, isError MCP) était rapportée comme réussie au frontend
    (contraste : mouse_click/keyboard_input dérivaient déjà du result).
  - launch/ninjatrader/full attendait ?password=… : le mot de passe NT8
    finissait dans les access-logs uvicorn/proxy (le pair nt8_login
    utilisait déjà un body LoginRequest).

Tests hermétiques : le module est importé (aucune connexion MCP n'est
établie à l'import), _tool_ok est testé unitairement, et des oracles AST
interdisent la régression.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.routers.desktop import (  # noqa: E402
    LaunchFullRequest, _tool_ok, launch_ninjatrider_full)

SRC = (ROOT / "backend" / "routers" / "desktop.py").read_text(encoding="utf-8")


class TestToolOk(unittest.TestCase):
    def test_result_mcp_sain(self):
        self.assertTrue(_tool_ok({"result": {"content": []}}))

    def test_erreur_timeout(self):
        self.assertFalse(_tool_ok({"error": "Timeout 30s"}))

    def test_iserror_mcp(self):
        self.assertFalse(_tool_ok({"result": {"isError": True, "content": []}}))

    def test_non_dict_et_multiple(self):
        self.assertFalse(_tool_ok(None))
        self.assertFalse(_tool_ok({"result": {"content": []}}, {"error": "x"}))
        self.assertTrue(_tool_ok({"result": {"content": []}},
                                 {"result": {"content": []}}))


class TestSuccessDerive(unittest.TestCase):
    def test_plus_aucun_success_codé_dur(self):
        """AST : aucun littéral « success: True » dans le router."""
        tree = ast.parse(SRC)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if (isinstance(k, ast.Constant) and k.value == "success"
                            and isinstance(v, ast.Constant)
                            and v.value is True):
                        self.fail(
                            f"« success: True » codé dur l.{node.lineno}")

    def test_password_en_body_pas_en_query(self):
        """La signature du launcher complet prend un LaunchFullRequest."""
        import inspect
        sig = inspect.signature(launch_ninjatrider_full)
        self.assertIs(sig.parameters["req"].annotation, LaunchFullRequest)
        # et plus aucun paramètre 'password' de route en query
        tree = ast.parse(SRC)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args:
                    if arg.arg == "password":
                        self.fail(
                            f"paramètre de route 'password' (query) l.{arg.lineno}")

    def test_launch_model_existe_et_valide(self):
        m = LaunchFullRequest(password="secret")
        self.assertEqual(m.password, "secret")
        self.assertEqual(LaunchFullRequest().password, "")


if __name__ == "__main__":
    unittest.main()
