#!/usr/bin/env python3
"""R9-screenshots — le clamp de `limit` sur `list_screenshots` (desktop.py).

Bug fondateur (trouvé par scan systématique 2026-10-10) : la campagne R9
avait corrigé le slice `[-limit:]` non clampé dans intel.py / market.py /
chat.py / vision.py, mais AVAIT MANQUÉ `desktop.py::list_screenshots`.
Un `GET /screenshots?limit=0` renvoyait `[-0:]` = **la LISTE ENTIÈRE** (tous
les .jpg chargés en RAM), et `limit=-1` inversait le sens du slice. Paramètre
router nu (pas de `Query(ge=1, le=)`), contrairement aux autres.

Ce test verrouille le clamp par AST (modèle test_r11 : on lit le source de
la fonction, pas besoin de monter un TestClient + un dossier screenshots).
Il échoue si quelqu'un retire le clamp ou réintroduit un slice nu.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "backend" / "routers" / "desktop.py"


def _fn_src(name: str) -> str | None:
    """Le source d'une fonction top-level dans desktop.py, ou None."""
    if not DESKTOP.exists():
        return None
    tree = ast.parse(DESKTOP.read_text(encoding="utf-8-sig", errors="ignore"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            return ast.get_source_segment(DESKTOP.read_text(
                encoding="utf-8-sig", errors="ignore"), node)
    return None


class TestListScreenshotsClamp(unittest.TestCase):

    def test_clamp_present_avant_le_slice(self):
        """La fonction doit clamper limit AVANT tout slice [-limit:]."""
        src = _fn_src("list_screenshots")
        self.assertIsNotNone(src, "list_screenshots absente de desktop.py")
        assert src is not None
        # le clamp max(1, min(...)) doit apparaître
        self.assertIn("max(1", src,
                      "list_screenshots doit clamper limit (max(1, min(...)))")
        self.assertIn("min(", src)
        # et le slice doit venir APRÈS le clamp (ordre dans le source)
        i_clamp = src.index("max(1")
        i_slice = src.index("[-limit")
        self.assertLess(i_clamp, i_slice,
                        "le clamp doit précéder le slice [-limit:]")

    def test_pas_de_slice_nu_sans_clamp(self):
        """Aucun slice [-limit:] ne doit exister sans clamp au-dessus dans
        la même fonction (le bug exact de desktop.py)."""
        src = _fn_src("list_screenshots")
        self.assertIsNotNone(src)
        assert src is not None
        # s'il y a un slice -limit ET pas de clamp -> échec
        if "[-limit" in src:
            self.assertIn("max(1", src,
                          "slice [-limit:] sans clamp = le bug R9 screenshots")


if __name__ == "__main__":
    unittest.main()
