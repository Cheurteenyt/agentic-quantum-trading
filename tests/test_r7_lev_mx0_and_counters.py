#!/usr/bin/env python3
"""r7 — les replis de marge/plafond restants étaient SILENCIEUX.

Trois trous restés vivants après #213 (repli marge prudent) et le fix des
symboles absents de lev_capped :

1. `lev_capped`, cas mx == 0 : ligne PRÉSENTE dans liq_params mais
   max_leverage NULL (chargé 0.0) — `return min(lev, mx) if mx > 0 else lev`
   rendait `lev` INCHANGÉ : plafond ignoré ET compteur muet. Le défaut
   miroir de F-047 côté levier, skippé explicitement par le test f038
   (`if mx <= 0: continue`).
2. `the_machine._maint_of` / `full_arsenal_2` l.232 : `.get(symbol,
   (fallback, 0.0))[0]` substituait la marge en silence — le « Lev sûr »
   publié lisait 2,5 % pour un memecoin à 16,66 %.
3. Aucun rapport ne lisait LIQ_FALLBACK_COUNT/LIQ_NON_VIABLE : le
   commentaire « un run sur une base absente se VOIT donc » était faux.

Fix : lev_capped compte ; maint_for() factorise le repli COMPTÉ ;
replis_check() publie les compteurs dans le rapport portfolio-sim.

Ces tests sont HERMÉTIQUES : même pattern que test_p1_liq_fallback (pas
de base).

    python tests/test_r7_lev_mx0_and_counters.py
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import portfolio_sim as ps  # noqa: E402

# un symbole CONNU mais dont le max_leverage est NULL (chargé 0.0)
MARGES = {
    "BTCUSDT": (2.5, 20.0),
    "MEMEUSDT": (16.66, 5.0),
    "NULMXUSDT": (2.5, 0.0),      # le chemin mort avant le fix
    "PIREUSDT": (25.0, 2.0),
}


class _FauxParams:
    def __enter__(self):
        self._memo = ps._LIQ_PARAMS
        self._fb = ps.LIQ_FALLBACK_COUNT
        self._nv = ps.LIQ_NON_VIABLE
        ps._LIQ_PARAMS = dict(MARGES)
        ps.LIQ_FALLBACK_COUNT = 0
        ps.LIQ_NON_VIABLE = 0
        return self

    def __exit__(self, *exc):
        ps._LIQ_PARAMS = self._memo
        ps.LIQ_FALLBACK_COUNT = self._fb
        ps.LIQ_NON_VIABLE = self._nv
        return False


class TestLevCappedMaxInconnu(unittest.TestCase):
    """Le chemin mx == 0 : le plafond est INCONNU, pas inexistant."""

    def setUp(self):
        self._ctx = _FauxParams()
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__()

    def test_mx_nul_est_plafonne_au_prudent(self):
        """Avant : min(lev, 0.0) if 0 > 0 else lev -> lev INCHANGÉ.
        Un ordre à 20x était simulé exécutable sans aucune donnée."""
        self.assertEqual(ps.lev_capped("NULMXUSDT", 20), 2.0,
                         "max_leverage NULL = plafond prudent (2x ici), "
                         "PAS le levier demandé")

    def test_mx_nul_compte_le_repli(self):
        avant = ps.LIQ_FALLBACK_COUNT
        ps.lev_capped("NULMXUSDT", 20)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, avant + 1,
                         "une contrainte inconnue est une substitution : "
                         "elle doit se voir")

    def test_mx_nul_a_bas_levier_ne_revient_pas_plus_haut(self):
        self.assertEqual(ps.lev_capped("NULMXUSDT", 1), 1.0,
                         "le repli plafonne, il n'élève jamais")

    def test_les_connus_ne_comptent_pas(self):
        ps.lev_capped("BTCUSDT", 20)
        ps.lev_capped("MEMEUSDT", 5)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 0)


class TestMaintFor(unittest.TestCase):
    """Le repli par catégorie, factorisé et compté."""

    def setUp(self):
        self._ctx = _FauxParams()
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__()

    def test_symbole_connu_renvoie_sa_marge_sans_compter(self):
        self.assertEqual(ps.maint_for("MEMEUSDT", 2.5), 16.66)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 0)

    def test_symbole_absent_renvoie_le_fallback_et_compte(self):
        self.assertEqual(ps.maint_for("SCRUSDT", 2.5), 2.5)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 1)

    def test_le_fallback_par_categorie_est_conserve(self):
        """MAINT_MEME = _maint_of('PONSUSDT', 16.66) : un repli GLOBAL
        prudent (max observé = 25) serait FAUX côté meme. Le fallback
        paramétrique reste, seule la substitution est comptée."""
        self.assertEqual(ps.maint_for("PONSUSDT", 16.66), 16.66)
        self.assertNotEqual(ps.maint_for("PONSUSDT", 16.66), 25.0)


class TestReplisCheck(unittest.TestCase):
    """La publication : le rapport doit DIRE combien de substitutions."""

    def setUp(self):
        self._ctx = _FauxParams()
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__()

    def test_zero_est_vert(self):
        self.assertEqual(ps.replis_check(),
                         "replis marge/plafond substitués : 0 (OK)")

    def test_non_zero_est_un_bandeau(self):
        ps.liq_move_for("INCONNUUSDT", 10)
        ps.lev_capped("NULMXUSDT", 20)
        ligne = ps.replis_check()
        self.assertIn("2", ligne)
        self.assertIn("⚠", ligne, "un compteur > 0 doit porter le bandeau")

    def test_la_publication_existe_dans_main(self):
        src = (ROOT / "scripts" / "portfolio_sim.py").read_text(encoding="utf-8")
        self.assertIn("checks.append(replis_check())", src,
                      "le garde-fou doit être branché dans le rapport")


class TestOracleStatique(unittest.TestCase):
    """Les sites de substitution en ligne ne doivent pas revenir."""

    def test_plus_de_get_fallback_de_marge_dans_the_machine(self):
        src = (ROOT / "scripts" / "the_machine.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        mauvais = [ast.unparse(n) for n in ast.walk(tree)
                   if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Call)
                   and getattr(n.func.func, "id", "") == "liq_params"]
        self.assertEqual(mauvais, [],
                         f"repli silencieux réintroduit : {mauvais}")

    def test_plus_de_get_fallback_de_marge_dans_full_arsenal_2(self):
        src = (ROOT / "scripts" / "full_arsenal_2.py").read_text(encoding="utf-8")
        self.assertNotIn("liq_params().get(e[", src)
        self.assertIn("mm = maint_for(e[\"sym\"], MAINT_PCT)", src)

    def test_lev_capped_ne_rend_plus_lev_inchange(self):
        # AST structurel (pas de grep : la docstring du fix CITE le bug —
        # un oracle textuel s'attrape lui-même, leçon ronde 5).
        src = (ROOT / "scripts" / "portfolio_sim.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fns = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "lev_capped"]
        self.assertEqual(len(fns), 1)
        dangereux = [
            ast.unparse(n) for n in ast.walk(fns[0])
            if isinstance(n, ast.IfExp)
            and isinstance(n.orelse, ast.Name) and n.orelse.id == "lev"
        ]
        self.assertEqual(
            dangereux, [],
            f"le chemin mx<=0 doit rester branché au repli : {dangereux}")


if __name__ == "__main__":
    unittest.main()
