"""R9-E — le sous-système élite FOMO était gelé, validé sur le clone10 :

1. [P0] fomo_ws_daemon.TOP_HANDLES n'était chargé qu'UNE fois au boot :
   le harvester horaire écrit top_handles dans ws_config.json et son contrat
   (« épinglés à la prochaine reconnexion, ≤ 1 h ») confondait reconnexion
   et restart — le service systemd tourne 24/7 (Restart=always) : l'élite du
   feed WS (épinglage prix/pression + top_trader=1, consommé par
   fomo_ws_signals WHERE top_trader=1) restait figée sur les handles du boot.
   Fix : reload à chaque reconnexion dans daemon_loop.
2. [P1] fomo_leaderboard_harvester : l'UI abrège les PnL ($1.2M/$950K) —
   les regexes exigeaient $digits purs : le rang entier était perdu
   silencieusement et la chaîne monotone se cassait ; knum ne gérait
   aucune échelle. Fix : [KMB]? dans les regexes + échelle dans knum.
3. [P1] harvester : < 10 lignes ne faisait qu'un AVERTISSEMENT puis écrivait
   QUAND MÊME (DELETE intégral + top_handles régénéré) : l'élite pouvait être
   écrasée par 3 handles d'un parse partiel. Fix : ABORT sans écriture.
4. [P1] fomo_ws_daemon --discover-uuid écrivait {"user_uuid": …} en remplaçant
   le JSON ENTIER : top_handles disparaissait de la config. Fix : fusion.

Mutations négatives : retirer le reload, rétablir l'écrasement, ou remettre
l'écriture inconditionnelle doit remettre les tests en échec.
"""
from __future__ import annotations

import ast
import asyncio
import contextlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.fomo_ws_daemon as fd  # noqa: E402
import scripts.fomo_leaderboard_harvester as fh  # noqa: E402


class KnumScaleTests(unittest.TestCase):
    def test_plain_and_commas(self):
        self.assertEqual(fh.knum("1,234.5"), 1234.5)
        self.assertEqual(fh.knum("950"), 950.0)

    def test_abbreviated_scales(self):
        self.assertEqual(fh.knum("1.2K"), 1200.0)
        self.assertEqual(fh.knum("950K"), 950_000.0)
        self.assertEqual(fh.knum("3.4M"), 3_400_000.0)
        self.assertEqual(fh.knum("1.2B"), 1_200_000_000.0)

    def test_invalid_and_empty(self):
        self.assertIsNone(fh.knum(""))
        self.assertIsNone(fh.knum("abc"))
        self.assertIsNone(fh.knum(None))


class ParseAbbreviatedTests(unittest.TestCase):
    """P1 : un rang au PnL abrégé ne doit plus être perdu."""

    def test_abbreviated_rank_is_parsed(self):
        # format réel : podium NON numéroté + liste à partir du rang 4
        text = (
            "Alpha\n@alpha1\n+\n$1.2M\n120+\n"
            "Beta\n@beta2\n+\n$950K\n80+\n"
            "4.\nGamma\n@gamma4\n+\n$500\n50+\n"
        )
        rows = fh.parse_leaderboard_text(text)
        handles = {h: p for _, _, h, p, _ in rows}
        self.assertIn("alpha1", handles, "le rang abrégé $1.2M doit être parsé")
        self.assertEqual(handles["alpha1"], 1_200_000.0)
        self.assertEqual(handles.get("beta2"), 950_000.0)

    def test_plain_values_unchanged(self):
        text = "Alpha\n@alpha1\n+\n$12,500.75\n120+\n4.\nGamma\n@gamma4\n+\n$500\n50+\n"
        rows = fh.parse_leaderboard_text(text)
        p = {h: v for _, _, h, v, _ in rows}
        self.assertEqual(p["alpha1"], 12500.75)


class HarvesterAbortTests(unittest.TestCase):
    """P1 : < 10 lignes doit ABORT sans écrire (ni DB, ni top_handles)."""

    def test_short_parse_aborts_before_write(self):
        """Oracle AST : la branche `len(rows) < 10` de main() doit contenir
        un return AVANT le DELETE FROM dom_leaderboard."""
        tree = ast.parse(
            (ROOT / "scripts" / "fomo_leaderboard_harvester.py")
            .read_text(encoding="utf-8"))
        main_fn = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "main")
        found_return_in_short_branch = False
        delete_after_short_branch = False
        for node in ast.walk(main_fn):
            if isinstance(node, ast.If):
                src = ast.unparse(node.test)
                if "rows" in src and "< 10" in src:
                    body_src = ast.unparse(ast.Module(body=node.body, type_ignores=[]))
                    self.assertIn("return", body_src,
                                  "la branche < 10 doit return (abort)")
                    found_return_in_short_branch = True
        src = ast.unparse(main_fn)
        delete_idx = src.index("DELETE FROM dom_leaderboard")
        short_idx = src.index("< 10")
        delete_after_short_branch = delete_idx > short_idx
        self.assertTrue(found_return_in_short_branch)
        self.assertTrue(delete_after_short_branch)
        # le return de la branche courte doit précéder le DELETE
        ret_idx = min(i for i, n in enumerate(ast.walk(main_fn))
                      if isinstance(n, ast.If) and "< 10" in ast.unparse(n.test)
                      for _ in [0])  # sentinel
        self.assertLess(short_idx, delete_idx)


class DaemonReloadTests(unittest.TestCase):
    """P0 : la reconnexion doit recharger top_handles."""

    def setUp(self):
        self._old_top = fd.TOP_HANDLES
        self._old_load = fd.load_top_handles
        self._old_session = fd.session

    def tearDown(self):
        fd.TOP_HANDLES = self._old_top
        fd.load_top_handles = self._old_load
        fd.session = self._old_session

    def test_reload_happens_on_reconnect(self):
        fd.TOP_HANDLES = {"old_handle"}
        fd.load_top_handles = lambda: {"new_handle_1", "new_handle_2"}

        calls = {"sleep": 0}

        async def fake_sleep(t):
            calls["sleep"] += 1
            if calls["sleep"] >= 1:
                raise KeyboardInterrupt  # sort de daemon_loop après 1 reload

        async def broken_session(*a, **k):
            raise ConnectionError("ws down")

        fd.session = broken_session
        real_mod = fd.asyncio
        fd.asyncio = types.SimpleNamespace(sleep=fake_sleep)  # patch LOCAL au module

        async def runner():
            writer = types.SimpleNamespace(log_session_end=lambda n: None)
            with contextlib.suppress(KeyboardInterrupt):
                await fd.daemon_loop("uuid", [], writer)

        try:
            asyncio.run(runner())
        finally:
            fd.asyncio = real_mod
        self.assertEqual(calls["sleep"], 1, "une reconnexion doit avoir eu lieu")
        self.assertEqual(fd.TOP_HANDLES, {"new_handle_1", "new_handle_2"},
                         "la reconnexion doit recharger l'élite depuis "
                         "ws_config.json")

    def test_reload_failure_keeps_previous_set(self):
        fd.TOP_HANDLES = {"stable"}

        def boom():
            raise RuntimeError("ws_config illisible")

        fd.load_top_handles = boom

        async def fake_sleep(t):
            raise KeyboardInterrupt

        async def broken_session(*a, **k):
            raise ConnectionError("x")

        fd.session = broken_session
        real_mod = fd.asyncio
        fd.asyncio = types.SimpleNamespace(sleep=fake_sleep)

        async def runner():
            writer = types.SimpleNamespace(log_session_end=lambda n: None)
            with contextlib.suppress(KeyboardInterrupt):
                await fd.daemon_loop("uuid", [], writer)

        try:
            asyncio.run(runner())
        finally:
            fd.asyncio = real_mod
        self.assertEqual(fd.TOP_HANDLES, {"stable"},
                         "si le reload échoue, l'ancien set reste valable")


def _raise_connection_error():
    async def _c():
        raise ConnectionError("ws down")
    return _c()


class DiscoverMergeTests(unittest.TestCase):
    """P1 : --discover-uuid doit FUSIONNER, pas écraser ws_config.json."""

    def test_discover_preserves_top_handles(self):
        """Oracle AST : l'écriture de CONFIG dans discover_uuid doit passer
        par une lecture préalable du cfg existant (fusion)."""
        src = ast.unparse(ast.parse(
            (ROOT / "scripts" / "fomo_ws_daemon.py").read_text(encoding="utf-8")))
        # isole discover_uuid
        tree = ast.parse(
            (ROOT / "scripts" / "fomo_ws_daemon.py").read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "discover_uuid")
        body = ast.unparse(fn).replace("'", '"')  # unparse normalise les quotes
        self.assertIn('json.loads(CONFIG.read_text())', body,
                      "le cfg existant doit être relu avant écriture")
        self.assertIn('cfg["user_uuid"]', body,
                      "l'UUID doit être fusionné dans le cfg existant")
        # l'écriture écrasante d'origine est interdite
        self.assertNotIn('CONFIG.write_text(json.dumps({"user_uuid"',
                         body.replace("'", '"'),
                         "l'écrasement du JSON entier est interdit")


if __name__ == "__main__":
    unittest.main()
