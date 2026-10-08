#!/usr/bin/env python3
"""C-B3 — le seuil p66 du porte-feuille empilé ne doit pas regarder le futur.

AVANT :

    k = int(len(cascade) * 0.7)
    q66 = float(np.nanquantile([e["al_score"] for e in cascade[:k]], 2/3))

`collect_featured` trie par `ts_ms` (anti_liq.py:83), donc `cascade[:k]`
= les 70 % PREMIERS du sample, et ce quantile UNIQUE était appliqué à tous
les événements — y compris les 30 % finaux. Le seuil de sizing au temps t
voyait donc jusqu'à 70 % d'histoire future.

Ces tests sont HERMÉTIQUES : aucune base, aucun réseau, aucun `main()`. Ils
rejouent les deux logiques sur des scores synthétiques et comparent la
DÉCISION par événement, pas une statistique globale — c'est la seule façon
de voir un look-ahead, un agrégat peut le masquer.

La contre-preuve est explicite : un edge planté DANS la fenêtre future
change la décision avec la logique full-sample, et ne la change PAS avec la
logique expanding. C'est le mutation test du motif.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from scripts.stacked_portfolio import (  # noqa: E402
    size_by_policy, stamp_expanding_q66)

MIN_HIST = 30


def _events(scores: list[float]) -> list[dict]:
    """Une cascade synthétique, horodatée toutes les heures."""
    base = 1_700_000_000_000
    return [{"ts_ms": base + i * 3_600_000, "al_score": s,
             "strategy": "cascade"} for i, s in enumerate(scores)]


def _logic_ancienne(events: list[dict]) -> list[bool]:
    """Le code d'origine : UN seuil sur 70 % du sample, appliqué partout.

    On reproduit `size_by_policy` avec son scalaire, pas la fonction réelle,
    pour que le test porte sur le LOOK-AHEAD et pas sur le refactor.
    """
    k = int(len(events) * 0.7)
    q66 = float(np.nanquantile([e["al_score"] for e in events[:k]], 2 / 3))
    return [bool(e["al_score"] >= q66) for e in events]   # True = GATÉ


def _logic_expanding(events: list[dict]) -> list[bool]:
    stampes, _ = stamp_expanding_q66(events, min_hist=MIN_HIST)
    return [bool(np.isfinite(e["_q66_asof"]) and e["al_score"] >= e["_q66_asof"])
            for e in stampes]


def _q66_ancienne(scores: list[float]) -> float:
    """La formule d'origine, seule — le SEUIL qu'elle produisait.

    Reproduite ici (et non dans le code de production) pour que le test
    porte sur le motif de look-ahead, pas sur le refactor de sizing.
    """
    k = int(len(scores) * 0.7)
    return float(np.nanquantile(scores[:k], 2 / 3))


def _seuils(events: list[dict], min_hist: int = MIN_HIST) -> list[float]:
    """Les seuils as-of, NaN compris, dans l'ordre temporel."""
    stampes, _ = stamp_expanding_q66(events, min_hist=min_hist)
    return [e["_q66_asof"] for e in stampes]


def _memes(a: list[float], b: list[float]) -> bool:
    """Égalité de deux listes de seuils, NaN == NaN.

    `==` sur des listes de floats renvoie False dès qu'un NaN est présent
    (`nan != nan`), ce qui ferait échouer un test correct. C'est exactement
    le piège qui a fait perdre 20 minutes sur ce fichier.
    """
    if len(a) != len(b):
        return False
    return all((np.isnan(x) and np.isnan(y)) or x == y for x, y in zip(a, b))



class TestLookAheadP66(unittest.TestCase):
    def test_le_seuil_dun_evenement_ne_dépend_pas_du_futur(self) -> None:
        """LA contre-preuve — la propriété causale, énoncée directement.

        Le SEUIL porté par un événement ne doit dépendre que des scores
        ANTERIEURS à lui. On le vérifie en rejouant le même préfixe avec
        deux suffixes très différents : sur le préfixe, les seuils doivent
        être strictement identiques.

        C'est le test qui distingue une correction d'un simple refactor :
        la formule full-sample (un scalaire sur `[:int(0.7*N)]`) applique
        à tous les événements ne peut PAS satisfaire cette propriété, car
        ajouter du futur change `int(0.7*N)`.
        """
        prefixe = [0.9] * 20 + [0.1] * 40
        chaud = _events(prefixe + [0.99] * 10)
        froid = _events(prefixe + [0.05] * 10)
        self.assertTrue(
            _memes(_seuils(chaud)[:60], _seuils(froid)[:60]),
            "les seuils du préfixe diffèrent selon le futur : le seuil n'est "
            "pas as-of, le look-ahead n'est pas corrigé")

    def test_le_seuil_croît_avec_le_seul_passé(self) -> None:
        """Le quantile expanding doit être monotone non décroissant."""
        evs = _events([0.1] * 40 + [0.5 + i * 0.01 for i in range(20)])
        stampes, _ = stamp_expanding_q66(evs, min_hist=MIN_HIST)
        seuils = [e["_q66_asof"] for e in stampes if np.isfinite(e["_q66_asof"])]
        self.assertGreater(len(seuils), 5, "trop peu de seuils finis")
        self.assertEqual(seuils, sorted(seuils),
                         "un quantile expanding ne peut pas reculer")

    def test_le_warmup_nest_gaté_pas(self) -> None:
        """Avant `min_hist`, pas de seuil → pas de gate.

        C'est la sémantique de `the_machine.gate_expanding`
        (`elif np.isfinite(s): gated.append(e)`), reprise telle quelle.
        """
        evs = _events([0.1] * (MIN_HIST + 10))
        stampes, _ = stamp_expanding_q66(evs, min_hist=MIN_HIST)
        for e in stampes[:MIN_HIST]:
            self.assertTrue(np.isnan(e["_q66_asof"]), "warm-up : seuil attendu NaN")
        for e in stampes[MIN_HIST:]:
            self.assertTrue(np.isfinite(e["_q66_asof"]))

    def test_un_score_nan_nepollue_pas_lhistorique(self) -> None:
        """Un NaN n'entre pas dans l'historique du quantile.

        On garde le MÊME nombre d'événements et on ne change que la valeur
        du bloc : si le NaN entrait dans `hist`, il décalerait le quantile
        de tous les événements suivants. On vérifie donc que les seuils
        APRÈS le bloc sont inchangés.
        """
        avec_nan = _events([0.1] * 40 + [float("nan")] * 5 + [0.2] * 5)
        avec_val = _events([0.1] * 40 + [0.15] * 5 + [0.2] * 5)
        a, b = _seuils(avec_nan), _seuils(avec_val)
        self.assertEqual(len(a), len(b))
        self.assertTrue(
            _memes(a[45:], b[45:]),
            "les seuils APRÈS le bloc diffèrent : le NaN est entré dans "
            "l'historique du quantile")

    def test_les_events_sont_triés_par_temps(self) -> None:
        """L'expanding exige l'ordre temporel — on le contracte."""
        evs = _events([0.1] * 60)
        for i, e in enumerate(evs):        # on les présente à l'envers
            evs[i]["ts_ms"] = 1_800_000_000_000 - i * 3_600_000
        stampes, _ = stamp_expanding_q66(evs, min_hist=MIN_HIST)
        ts = [e["ts_ms"] for e in stampes]
        self.assertEqual(ts, sorted(ts),
                         "stamp_expanding_q66 doit rendre les events triés "
                         "par ts_ms")

    def test_size_by_policy_lit_le_seuil_as_of(self) -> None:
        """Le gate doit suivre `_q66_asof`, pas le scalaire de repli.

        On prend le scalaire qui GATERAIT le score (0.9 >= 0.8) et un
        `_q66_asof` qui ne le gate pas (0.95 > 0.9). Avec le scalaire seul,
        le trade serait à 0 ; avec l'estampille, il est dimensionné.
        """
        e = {"strategy": "cascade", "al_score": 0.9, "_q66_asof": 0.95}
        fn = size_by_policy({"cascade": 0.075}, gate_thr=0.8)
        self.assertAlmostEqual(fn(e), 0.075,
                               msg="le seuil as-of n'a pas été lu : le "
                                   "scalaire a gagné")

        # sans estampille, le repli scalaire s'applique (compatibilité)
        sans = {"strategy": "cascade", "al_score": 0.9}
        self.assertEqual(fn(sans), 0.0)

    def test_size_by_policy_gère_le_warmup(self) -> None:
        """`_q66_asof` NaN → pas de gate → taille nominale."""
        e = {"strategy": "cascade", "al_score": 0.9, "_q66_asof": float("nan")}
        fn = size_by_policy({"cascade": 0.075}, gate_thr=0.8)
        self.assertAlmostEqual(fn(e), 0.075)

    def test_les_strategies_non_cascade_sont_inchangees(self) -> None:
        """Le repli garde `size_by_policy(..., q66)` valide partout."""
        fn = size_by_policy({"cascade": 0.045, "funding_div": 0.015,
                             "confluence": 0.01}, gate_thr=0.8)
        for strat, attendu in (("funding_div", 0.015), ("confluence", 0.01)):
            self.assertAlmostEqual(fn({"strategy": strat}), attendu)


class TestContreTemoins(unittest.TestCase):
    """Un vérificateur qui renvoie toujours `False` passerait les tests
    du dessus. Ces tests le mutent pour prouver qu'il détecte."""

    def test_min_hist_change_bien_le_nombre_de_seuils(self) -> None:
        """Le contre-témoin du contre-témoin : `min_hist` agit.

        Une liste de seuils se compare mal (NaN). On mesure donc le nombre
        de seuils FINIS, qui doit être `len(events) - min_hist` — c'est une
        relation exacte et sans ambiguïté.
        """
        evs = _events([0.1] * 40 + [0.2 + i * 0.05 for i in range(20)])
        for mh in (10, 30, 45):
            with self.subTest(min_hist=mh):
                finis = sum(1 for v in _seuils(evs, min_hist=mh)
                            if np.isfinite(v))
                self.assertEqual(finis, len(evs) - mh)

    def test_la_formule_ancienne_dependait_du_futur(self) -> None:
        """Montre que le motif corrigé était bien un look-ahead.

        La formule d'origine prend `[:int(0.7*N)]` : ajouter du futur change
        `N`, donc la borne de la fenêtre du quantile, donc le seuil ETALÉ
        sur les événements du préfixe. On le vérifie sur les VALEURS, pas
        sur une décision binaire — avec deux scores distincts seulement, le
        quantile en retient un et aucune décision ne peut basculer, ce qui
        rendrait le témoin muet.
        """
        prefixe = [0.3, 0.35, 0.4] * 20          # 60, trois valeurs distinctes
        q_avec = _q66_ancienne(prefixe + [0.99] * 10)
        q_sans = _q66_ancienne(prefixe)
        self.assertNotEqual(q_avec, q_sans,
                            "la formule ancienne est insensible au futur : "
                            "le témoin ne prouve rien")


class TestCablage(unittest.TestCase):
    """Le test de la fonction ne prouve pas que `main()` l'APPELLE.

    Première mutation faite sur ce correctif : j'ai rebranché la formule
    full-sample dans `main()` en laissant `stamp_expanding_q66` intacte —
    et les 10 tests sont restés verts. Une fonction correcte jamais appelée
    ne corrige rien. Ces tests verrouillent le câblage.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "scripts" / "stacked_portfolio.py").read_text(
            encoding="utf-8")

    def test_main_appelle_stamp_expanding_q66(self):
        self.assertIn("stamp_expanding_q66(cascade)", self.src,
                      "main() n'appelle plus stamp_expanding_q66 : le seuil "
                      "n'est plus as-of")

    def test_le_motif_full_sample_a_disparu(self):
        """`int(len(...) * 0.7)` = la fenêtre qui regarde le futur.

        Passé par AST, pas par regex : le motif apparaît LÉGITIMEMENT dans
        la docstring de `stamp_expanding_q66`, qui documente le code
        d'origine pour expliquer le correctif. Un grep le prendrait pour
        une régression — il faut distinguer le CODE du commentaire.
        """
        import ast
        tree = ast.parse(self.src)
        coupables = []
        for n in ast.walk(tree):
            # int(len(<x>) * <float>)
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "int" and len(n.args) == 1):
                continue
            mult = n.args[0]
            if not (isinstance(mult, ast.BinOp)
                    and isinstance(mult.op, ast.Mult)):
                continue
            if not isinstance(mult.left, ast.Call):
                continue
            l = mult.left.func
            if isinstance(l, ast.Name) and l.id == "len":
                coupables.append((n.lineno, ast.unparse(n)))
        self.assertEqual(
            coupables, [],
            f"le slicing `int(len(x)*0.7)` est de retour dans le CODE : "
            f"{coupables}")

    def test_aucun_nanquantile_direct_sur_une_tranche(self):
        """Plus aucun quantile calculé sur une tranche d'événements."""
        import ast
        tree = ast.parse(self.src)
        coupables = []
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "nanquantile"):
                continue
            src = ast.unparse(n)
            if "[" in src and ":" in src:
                coupables.append((n.lineno, src))
        self.assertEqual(coupables, [],
                         f"nanquantile sur une TRANCHE (look-ahead) : {coupables}")

    def test_size_by_policy_lit_bien_as_of_en_priorite(self):
        import ast
        tree = ast.parse(self.src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "size_by_policy")
        # ast.unparse normalise les guillemets : on matche sur le `get(`
        # plutôt que sur une chaîne littérale.
        src = ast.unparse(fn).replace('"', "'")
        self.assertIn("e.get('_q66_asof', gate_thr)", src,
                      "size_by_policy ne lit plus _q66_asof en priorité : "
                      "le seuil as-of est ignoré au profit du scalaire")

    def test_les_evenements_sont_passes_par_la_fonction(self):
        """`cascade` doit être le retour de la fonction (donc triée)."""
        self.assertIn("cascade, q66 = stamp_expanding_q66(cascade)", self.src,
                      "le retour trié n'est pas réutilisé : les événements "
                      "restent dans l'ordre d'origine")



if __name__ == "__main__":
    unittest.main()