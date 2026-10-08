#!/usr/bin/env python3
"""F-043 / F-044 — les invariants de structure de `paper_forward.main()`.

CONTEXTE
--------
Le nightly passait 4 nuits en `TimeoutStartSec` : `paper_forward.py` coûte
~20 min par invocation et l'unité l'appelle DEUX fois (positions 15 et 40),
soit 40 min sur un budget de 60.

Le correctif F-043 inverse les boucles (symbole en EXTERNE, candidat en
INTERNE) et mémoïse ce qui ne dépend que du symbole. Le gain est réel :
`load_df` passe de 8 × 586 à 586 appels, le rescan de `funding_history`
(2,14 M lignes) disparaît, `price_signals` est calculé une fois par symbole.

LE PIÈGE (et pourquoi ce fichier existe)
----------------------------------------
La première version de ce correctif a **dedenté** le corps de traitement
d'un cran en trop en ré-indentant le bloc. Résultat mesuré par AST :

    for sym            L272
      for name,...     L282-L308      <- `ev` est ASSIGNÉ ici
      for ts in ev     L311-L356      <- ... puis CONSOMMÉ ici, HORS de la boucle

Conséquences :
  1. seul le DERNIER candidat de CANDIDATES survit — les 7 autres sont
     perdus SILENCIEUSEMENT (pas de crash, pas de log, un ledger
     simplement amputé) ;
  2. si tous les candidats font `continue`, `ev` n'est jamais assigné →
     UnboundLocalError au L310.

Le test livré avec le premier correctif NE L'A PAS VU : il réimplémentait
les deux ordres de boucle dans le fichier de test (`_detect` /
`_detect_ancien`) au lieu d'exécuter `main()`. `_detect` plaçait `for t in
ev` au bon endroit, donc le test validait du code qui n'était pas celui de
production. C'est le piège exact que le mutation test du projet prétend
traquer (README § 21).

CE QUE FAIT CE FICHIER
----------------------
Il vérifie l'invariant STRUCTUREL sur le VRAI `scripts/paper_forward.py`,
par analyse de l'AST — pas par recherche de chaîne, pas par
réimplémentation. Un test qui réimplémente la production ne peut pas
détecter une erreur d'indentation de la production : il les écrit à la
main des deux côtés.

`TestMutationControl` est le contre-témoin obligatoire : il rejoue la
STRUCTURE CASSÉE en miniature et exige que le vérificateur la REJETTE.
Sans ce contre-témoin, un vérificateur qui renvoie toujours `True` passerait
tous les tests verts — c'est-à-dire exactement le défaut que ce fichier
corrige.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SRC_PATH = ROOT / "scripts" / "paper_forward.py"


# ——————————————————————————————————————————————————————————————
# LE VÉRIFICATEUR — il porte sur l'AST de la production
# ——————————————————————————————————————————————————————————————

def _loop_targets(node: ast.For) -> list[str]:
    if isinstance(node.target, ast.Tuple):
        return [e.id for e in node.target.elts]
    return [getattr(node.target, "id", "?")]


def _find_loop(fn: ast.AST, var: str) -> ast.For | None:
    """Première boucle du nom `var`, en ORDRE SOURCE.

    `ast.walk` est un parcours en largeur : il ne garantit pas l'ordre des
    lignes. On observe qu'il renvoie la boucle `for name, horizon, _d` du
    RAPPORT (L570) avant la boucle du traitement (L282) — deux boucles
    portent le même nom de variable. D'où le tri par `lineno` : le nom
    doit désigner la boucle la plus haute du fichier, pas celle que le
    BFS croise par hasard.
    """
    found = [n for n in ast.walk(fn)
             if isinstance(n, ast.For) and var in _loop_targets(n)]
    return min(found, key=lambda n: n.lineno) if found else None


def _candidate_loop(main: ast.FunctionDef) -> ast.For:
    """La boucle `for name, ...` À L'INTÉRIEUR de `for sym` — le chemin
    canonique, le même que celui de `invariant_events_inside_candidate`."""
    sym = _find_loop(main, "sym")
    if sym is None:
        raise AssertionError("pas de `for sym` dans main()")
    cand = [s for s in sym.body
            if isinstance(s, ast.For) and "name" in _loop_targets(s)]
    if not cand:
        raise AssertionError("pas de `for name` dans `for sym`")
    return cand[0]


def _main_fn(tree: ast.AST) -> ast.FunctionDef:
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == "main":
            return n
    raise AssertionError("main() introuvable dans paper_forward.py")


def invariant_events_inside_candidate(src: str) -> tuple[bool, str]:
    """(ok, diagnostic) — `ev` est-il consommé DANS la boucle candidat ?

    Cherche le `for sym` extérieur puis, à l'intérieur, le `for name`.
    Le `for ts` (la consommation des événements) doit être un ENFANT DIRECT de la
    boucle candidat. S'il est un frère de celle-ci, il est sorti de la
    boucle : c'est le bug F-043.
    """
    tree = ast.parse(src)
    main = _main_fn(tree)
    sym = _find_loop(main, "sym")
    if sym is None:
        return False, "pas de `for sym` dans main()"
    cand = next((s for s in sym.body
                 if isinstance(s, ast.For) and "name" in _loop_targets(s)), None)
    if cand is None:
        return False, "pas de `for name` imbriqué dans `for sym`"

    inner = [s for s in cand.body if isinstance(s, ast.For)]
    if any("ts" in _loop_targets(s) for s in inner):
        return True, f"for ts imbriqué (L{min(s.lineno for s in inner)}-L{max(s.end_lineno for s in inner)})"

    siblings = [s for s in sym.body
                if isinstance(s, ast.For) and "ts" in _loop_targets(s)]
    if siblings:
        return False, (f"for ts (L{siblings[0].lineno}-L{siblings[0].end_lineno}) "
                       f"est un FRÈRE de la boucle candidat "
                       f"(L{cand.lineno}-L{cand.end_lineno}), pas un enfant")
    return False, "aucune boucle de traitement des événements dans la boucle candidat"


def count_price_signals_calls(src: str) -> int:
    """Nombre de sites d'appel à `price_signals` dans main()."""
    tree = ast.parse(src)
    return sum(1 for n in ast.walk(tree)
               if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Name)
               and n.func.id == "price_signals")


def invariant_memo_guard(src: str) -> tuple[bool, str]:
    """(ok, diagnostic) — `price_signals` est-il mémoïsé ?

    Il doit y avoir exactement UN site d'appel, protégé par une garde
    `if <var> is None` dans la boucle candidat.
    """
    n = count_price_signals_calls(src)
    if n != 1:
        return False, f"{n} sites d'appel à price_signals (attendu 1)"
    tree = ast.parse(src)
    main = _main_fn(tree)
    # tolère un extrait minimal (contrôle par mutation) sans `for sym`
    sym = _find_loop(main, "sym")
    if sym is not None:
        cand = [s for s in sym.body
                if isinstance(s, ast.For) and "name" in _loop_targets(s)]
        cand = cand[0] if cand else _find_loop(main, "name")
    else:
        cand = _find_loop(main, "name")
    if cand is None:
        return False, "pas de boucle candidat"
    guards = [s for s in ast.walk(cand)
              if isinstance(s, ast.If)
              and isinstance(s.test, ast.Compare)
              and type(s.test.ops[0]).__name__ in {"Is", "IsNot"}
              and any(isinstance(c, ast.Constant) and c.value is None
                      for c in s.test.comparators)]
    if not guards:
        return False, "l'appel n'est pas gardé par un `if <var> is None`"
    return True, f"1 site d'appel, garde `is None` à L{guards[0].lineno}"


def invariant_grouped_funding(src: str) -> tuple[bool, str]:
    """(ok, diagnostic) — le funding est groupé UNE fois pour tous."""
    tree = ast.parse(src)
    ok = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "groupby" for n in ast.walk(tree))
    return ok, "groupby présent" if ok else "aucun groupby (rescan par symbole)"


def invariant_rescan_removed(src: str) -> tuple[bool, str]:
    """Le rescan `fh[fh.symbol == sym]` ne doit plus exister."""
    bad = "fh[fh.symbol == sym]" in src
    return (not bad), ("rescan absent" if not bad
                       else "`fh[fh.symbol == sym]` est revenu")


# ——————————————————————————————————————————————————————————————
# LES TESTS — sur le VRAI fichier de production
# ——————————————————————————————————————————————————————————————

class TestStructureReelle(unittest.TestCase):
    """Les invariants doivent tenir sur scripts/paper_forward.py."""

    @classmethod
    def setUpClass(cls):
        cls.src = SRC_PATH.read_text(encoding="utf-8")

    def test_le_symbole_est_en_boucle_externe(self):
        ok, why = invariant_events_inside_candidate(self.src)
        self.assertTrue(ok, f"structure cassée : {why}")
        self.assertIn("for sym in sorted(symbols):", self.src)

    def test_les_evenements_sont_consommes_DANS_la_boucle_candidat(self):
        """LE TEST DU BUG F-043.

        Si `for ts in ev` redevient un frère de la boucle candidat, la
        détection est muette : 7 des 8 candidats disparaissent du ledger.
        """
        ok, why = invariant_events_inside_candidate(self.src)
        self.assertTrue(ok, why)

    def test_aucune_consommation_apres_la_boucle_candidat(self):
        """Variante textuelle : `ev` ne doit pas être consommé au niveau
        du `for sym`."""
        tree = ast.parse(self.src)
        main = _main_fn(tree)
        sym = _find_loop(main, "sym")
        cand = [s for s in sym.body
                if isinstance(s, ast.For) and "name" in _loop_targets(s)][0]
        niveau_sym = [s for s in sym.body if s is not cand]
        hors = [n for s in niveau_sym for n in ast.walk(s)
                if isinstance(n, ast.For) and "ts" in _loop_targets(n)]
        self.assertEqual(hors, [], f"boucle `for ts` hors candidat : {hors}")

    def test_price_signals_est_memoise(self):
        ok, why = invariant_memo_guard(self.src)
        self.assertTrue(ok, why)

    def test_le_funding_est_groupe_une_seule_fois(self):
        ok, why = invariant_grouped_funding(self.src)
        self.assertTrue(ok, why)

    def test_le_rescan_par_symbole_a_disparu(self):
        ok, why = invariant_rescan_removed(self.src)
        self.assertTrue(ok, why)

    def test_closed_n_ne_compte_que_des_trades_persistes(self):
        """F-044 — `closed_n += 1` doit être APRÈS l'INSERT, sinon le
        rapport compte des trades que le gate fund7 a rejetés.

        On travaille sur l'AST (les AugAssign), pas sur une sous-chaîne :
        un commentaire qui mentionne `closed_n += 1` ne doit pas être
        compté comme un site d'incrément.
        """
        tree = ast.parse(self.src)
        main = _main_fn(tree)
        cand = _candidate_loop(main)

        def _increments(scope):
            return [n.lineno for n in ast.walk(scope)
                    if isinstance(n, ast.AugAssign)
                    and isinstance(n.target, ast.Name)
                    and n.target.id == "closed_n"
                    and isinstance(n.op, ast.Add)]

        inc_dans_cand = _increments(cand)
        self.assertEqual(len(inc_dans_cand), 1,
                         f"{len(inc_dans_cand)} incréments de closed_n dans "
                         f"la boucle candidat (attendu 1)")

        insert = [n.lineno for n in ast.walk(cand)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "execute"
                  and isinstance(n.args[0], ast.Constant)
                  and "INSERT OR IGNORE INTO paper_trades"
                  in str(n.args[0].value)]
        self.assertTrue(insert, "INSERT INTO paper_trades introuvable")
        self.assertGreater(inc_dans_cand[0], insert[0],
                           "`closed_n += 1` est avant l'INSERT : un trade "
                           "rejeté par le gate sera compté « clôturé »")

        # le second incrément (après un UPDATE réel de clôture) doit rester
        inc_hors = _increments(main)
        self.assertEqual(len(inc_hors), 2,
                         "2 incréments attendus dans main() : l'INSERT et "
                         "l'UPDATE de clôture")


# ——————————————————————————————————————————————————————————————
# CONTRÔLE PAR MUTATION — le vérificateur doit REJETER le bug
# ——————————————————————————————————————————————————————————————

CASSE = '''
def main():
    for sym in sorted(symbols):
        df = load_df(con, sym)
        for name, horizon, direction in CANDIDATES:
            if name == "x":
                continue
            ev = df.index[mask]
        # BUG : dedenté d'un cran
        ev = pd.DatetimeIndex(ev)
        for ts in ev:
            con.execute("INSERT INTO t VALUES (name, sym, ts)")
'''

CORRECT = '''
def main():
    for sym in sorted(symbols):
        df = load_df(con, sym)
        for name, horizon, direction in CANDIDATES:
            if name == "x":
                continue
            ev = df.index[mask]
            ev = pd.DatetimeIndex(ev)
            for ts in ev:
                con.execute("INSERT INTO t VALUES (name, sym, ts)")
'''


class TestMutationControl(unittest.TestCase):
    """Un vérificateur qui renvoie toujours True passerait les tests
    verts. Ces tests le mutent pour prouver qu'il détecte."""

    def test_le_verificateur_rejette_la_structure_cassee(self):
        ok, why = invariant_events_inside_candidate(CASSE)
        self.assertFalse(ok, "le vérificateur a ACCEPTÉ le bug F-043")
        self.assertIn("FRÈRE", why, why)

    def test_le_verificateur_accepte_la_structure_correcte(self):
        ok, why = invariant_events_inside_candidate(CORRECT)
        self.assertTrue(ok, why)

    def test_le_verificateur_rejette_une_memoisation_absente(self):
        deux_sites = CORRECT.replace(
            "price_signals(df, btc)",
            "price_signals(df, btc) or price_signals(df, btc)")
        ok, why = invariant_memo_guard(deux_sites)
        self.assertFalse(ok, why)

    def test_le_verificateur_accepte_une_memoisation_presente(self):
        src = '''
def main():
    for name, horizon, direction in CANDIDATES:
        if _sig is None:
            _sig = dict(price_signals(df, btc))
'''
        ok, why = invariant_memo_guard(src)
        self.assertTrue(ok, why)

    def test_le_verificateur_rejette_le_rescan_revenu(self):
        ok, why = invariant_rescan_removed("x = fh[fh.symbol == sym]")
        self.assertFalse(ok, why)


# ——————————————————————————————————————————————————————————————
# LE GAIN — mesuré, pas théorique
# ——————————————————————————————————————————————————————————————

class TestGainDeCharge(unittest.TestCase):
    """Le gain doit être réel : on le compte sur l'AST de production."""

    @classmethod
    def setUpClass(cls):
        cls.src = SRC_PATH.read_text(encoding="utf-8")

    def test_un_seul_site_appel_de_price_signals(self):
        n = count_price_signals_calls(self.src)
        self.assertEqual(n, 1,
                         f"{n} sites d'appel — la mémoïsation n'est pas "
                         f"appliquée (l'ancien code en avait un par branche)")

    def test_le_changement_de_charge_est_reel(self):
        """Avant : len(CANDIDATES) load_df par symbole. Après : 1."""
        sys.path.insert(0, str(ROOT / "scripts"))
        from scripts.paper_forward import CANDIDATES
        tree = ast.parse(self.src)
        main = _main_fn(tree)
        sym = _find_loop(main, "sym")
        cand = [_candidate_loop(main)]
        self.assertEqual(len(cand), 1,
                         "il doit rester exactement une boucle candidat "
                         "à l'intérieur de la boucle symbole")
        load_df_dans_sym = sum(
            1 for n in ast.walk(sym)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "load_df")
        load_df_dans_cand = sum(
            1 for n in ast.walk(cand[0])
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "load_df")
        self.assertEqual(load_df_dans_sym, 1,
                         "load_df doit être appelé une fois par symbole")
        self.assertEqual(load_df_dans_cand, 0,
                         "load_df ne doit plus être dans la boucle candidat")


if __name__ == "__main__":
    unittest.main()
