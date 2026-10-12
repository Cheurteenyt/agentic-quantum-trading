"""Les points d'entrée `scripts/*.py` démarrent par leur CHEMIN, pas seulement
par `-m` (P1 de l'audit 2026-10-11).

LE TROU : `research_worker.py` faisait `from scripts.label_matrix import …`
(l.51) AVANT de mettre la racine au `sys.path` (l.55). L'import marchait sous
`python -m scripts.research_worker` (l'importeur place la racine) et dans les
tests (ROOT inséré en tête de fichier) — mais `python3 scripts/research_worker.py`
(le chemin documenté dans la docstring du module lui-même !) plantait à
l'import : `ModuleNotFoundError: No module named 'scripts'`.

    « Les tests importent, personne ne lance. »

Le défaut n'existe QUE si l'import `scripts.*` est exécuté AU CHARGEMENT
(niveau module) avant le bootstrap `sys.path`. Un import paresseux dans une
fonction, sous `try/except`, est sain (`x_harvest.py` l.407) — le compter
serait un faux positif.

Deux volets, tous deux rapides :
  * STATIQUE (AST) — repère l'ordre import/bootstrappe au niveau module ;
  * DYNAMIQUE — confirme le vrai bug en lançant le cas d'espèce par son chemin
    (l'audit l'a nommé : `research_worker.py`) et en généralisant le lancement
    aux scripts signalés par l'AST (un faux positif statique est réfuté ici).

Pas de « lancer les 171 scripts » : 171 × subprocess ≈ 13 min, inutilisable en
CI — et l'exit code ne prouve rien (`whale_radar.py` charge, puis continue et
rend 1 sans données).
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _lignes_bootstrap(tree: ast.AST) -> int | None:
    """1re ligne où la racine est mise sur sys.path (sys.path.insert/append)."""
    ligne = None
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("insert", "append")
                and isinstance(n.func.value, ast.Attribute)
                and n.func.value.attr == "path"):
            ligne = n.lineno if ligne is None else min(ligne, n.lineno)
    return ligne


def _import_module_scripts_avant(tree: ast.AST, limite: int) -> int | None:
    """1re ligne d'un `import scripts.*` AU NIVEAU MODULE (pas dans une
    fonction/classe) avant `limite` ; None sinon."""
    def _scan(corps: list[ast.stmt]) -> int | None:
        for n in corps:  # corps du module uniquement
            if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("scripts"):
                return n.lineno
            if isinstance(n, ast.Import) and any(a.name.startswith("scripts") for a in n.names):
                return n.lineno
        return None
    ligne = _scan(tree.body)
    if ligne is None:
        return None
    return ligne if ligne < limite else None


def _fautifs_statiques() -> list[tuple[str, str]]:
    """Scripts dont un import scripts.* au niveau module précède le bootstrap."""
    out = []
    for f in sorted((ROOT / "scripts").glob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        boot = _lignes_bootstrap(tree)
        limite = boot if boot is not None else 10 ** 9
        imp = _import_module_scripts_avant(tree, limite)
        if imp is not None:
            where = "AUCUN sys.path.insert" if boot is None else f"bootstrap l.{boot}"
            out.append((str(f), f"import scripts.* l.{imp} < {where}"))
    return out


def _plante_par_son_chemin(chemin: str) -> bool:
    """True si le script échoue à l'IMPORT lancé par son chemin."""
    try:
        r = subprocess.run(
            [sys.executable, chemin, "--help"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False  # a chargé et travaille
    return "ModuleNotFoundError" in (r.stderr or "")


class LAvecImportScriptsEstBootstrappe(unittest.TestCase):
    """Trouvé le 11/10 : `python3 scripts/research_worker.py --help` plantait."""

    def test_aucun_import_module_scripts_avant_sys_path(self) -> None:
        """Un ordre fautif est suspect — mais n'est retenu que s'il PLANTE."""
        suspects = _fautifs_statiques()
        # Le vivier des suspects est petit (0-1) : on les lance tous pour
        # séparer un vrai bug d'un faux positif de l'AST.
        reels = [(c, d) for c, d in suspects if _plante_par_son_chemin(c)]
        ecartes = [Path(c).name for c, _ in suspects if not _plante_par_son_chemin(c)]
        msg = ("des scripts plantent lancés par leur chemin "
               "(import `scripts.*` au niveau module avant sys.path) :\n  "
               + "\n  ".join(f"{Path(c).name} — {d}" for c, d in reels))
        if ecartes:
            msg += f"\n(suspects AST écartés car ils chargent : {ecartes})"
        self.assertEqual([Path(c).name for c, _ in reels], [], msg)

    def test_le_worker_specifiquement(self) -> None:
        """Le cas d'espèce : lancé par son chemin, il doit charger et répondre."""
        w = str(ROOT / "scripts" / "research_worker.py")
        r = subprocess.run(
            [sys.executable, w, "--help"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        self.assertNotIn("ModuleNotFoundError", r.stderr or "",
                         "research_worker.py doit charger la racine AVANT ses "
                         "imports internes:\n" + (r.stderr or "")[-400:])
        self.assertIn("usage:", r.stdout or "")


if __name__ == "__main__":
    unittest.main()
