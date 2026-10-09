"""R9-A — quatre défauts de câblage backend validés sur le clone10 (main @8e73f90) :

1. [P0] intel_aggregator.start_aggregator() n'avait AUCUN appelant :
   _batch_loop ne tournait jamais, pending_signals n'était ni drainé ni
   nettoyé (croissance infinie), le cooldown restait inopérant (il n'est
   mis à jour que dans _batch_loop) et _broadcast_callback restait None —
   les signaux intel n'atteignaient jamais le WS frontend pendant que
   /api/intel/* répondait success: true.
2. [P1] websocket_manager.broadcast itérait la liste VIVANTE avec des await :
   un connect()/disconnect() concurrent levait RuntimeError (list changed
   size during iteration), avalé par l'appelant — ticks perdus sans trace.
3. [P1] collector.handle_trades appelait le global footprint_manager nu :
   trades est souscrit AVANT l2Book et à chaque reconnexion — tout trade
   arrivant avant le premier l2Book levait AttributeError (None) avalé par
   l'except : trades perdus de la footprint en silence.
4. [P1] collector.snapshot_loop écrivait via write_text (tronque puis
   écrit, non atomique) : un read_text concurrent dans la fenêtre de
   troncature levait JSONDecodeError => HTTP 500 intermittent.

Mutations négatives attendues : retirer le handler startup (1), réitérer la
liste vivante (2), rétablir le global nu (3), rétablir write_text direct (4).
"""
from __future__ import annotations

import asyncio
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.collector import (  # noqa: E402
    MarketState,
    handle_trades,
    state as collector_state,
    footprint_manager as _fm_module_var,
)
import services.collector as collector  # noqa: E402
import services.websocket_manager as wsm  # noqa: E402
from services.intel_aggregator import aggregator, start_aggregator  # noqa: E402


class StartupWiringTests(unittest.TestCase):
    """P0 : le handler startup doit démarrer l'aggregator (callback + boucles)."""

    def test_main_has_startup_handler_wiring_start_aggregator(self):
        """Oracle AST : main.py contient un handler startup qui importe ET
        attend start_aggregator — sans quoi les signaux ne sortent jamais."""
        tree = ast.parse((BACKEND / "main.py").read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if node.name != "_start_intel_aggregator":
                continue
            decs = [
                ast.unparse(d) for d in node.decorator_list
            ]
            self.assertIn("app.on_event('startup')", [d.replace('"', "'") for d in decs],
                          "le handler doit être enregistré au startup de l'app")
            src = ast.unparse(node)
            self.assertIn("start_aggregator", src)
            self.assertIn("await", src, "start_aggregator doit être attendu (coroutine)")
            found = True
        self.assertTrue(found, "handler startup _start_intel_aggregator introuvable")

    def test_start_aggregator_starts_loops_and_callback(self):
        """Dynamique : après start_aggregator, la boucle tourne et le callback
        WS est posé — c'est exactement ce que le startup exécutera."""

        async def run():
            await start_aggregator()
            self.assertIsNotNone(aggregator._batch_loop_task,
                                 "_batch_loop doit être une tâche créée")
            self.assertIsNotNone(aggregator._cleanup_task)
            self.assertIsNotNone(aggregator._broadcast_callback,
                                 "le callback broadcast doit être posé")

            # le callback posé est bien le broadcast du manager WS
            # (égalité de bound method : __self__ + __func__)
            self.assertEqual(aggregator._broadcast_callback, wsm.manager.broadcast)

            await aggregator.stop()

        asyncio.run(run())


class FakeWS:
    def __init__(self, name: str, on_send=None):
        self.name = name
        self.on_send = on_send
        self.received: list = []

    async def accept(self):  # appelé par manager.connect
        pass

    async def send_json(self, data):
        if self.on_send is not None:
            self.on_send()
        self.received.append(data)


class BroadcastRaceTests(unittest.TestCase):
    """P1 : broadcast doit survivre à un connect/disconnect concurrent."""

    def setUp(self):
        wsm.manager.active.clear()

    def tearDown(self):
        wsm.manager.active.clear()

    def test_disconnect_during_broadcast_does_not_skip_clients(self):
        # NB (mesure anti-mirage) : une liste Python ne lève PAS RuntimeError
        # en itération avec mutation (c'est vrai pour dict/set) — le défaut
        # réel est un SAUT D'INDEX : retirer un élément AVANT l'index courant
        # décale la liste et fait sauter le client suivant (tick perdu sans
        # trace). w1 est déconnecté pendant l'envoi de w2 => w3 doit quand
        # même recevoir le tick.
        w1, w2, w3 = FakeWS("w1"), FakeWS("w2"), FakeWS("w3")
        w2.on_send = lambda: wsm.manager.disconnect(w1)

        async def run():
            await wsm.manager.connect(w1)   # connect est async (accept)
            await wsm.manager.connect(w2)
            await wsm.manager.connect(w3)
            await wsm.manager.broadcast({"type": "tick", "px": 1.0})

        asyncio.run(run())
        self.assertEqual(len(w1.received), 1)
        self.assertEqual(len(w2.received), 1)
        self.assertEqual(len(w3.received), 1,
                         "w3 ne doit pas être sauté par le décalage d'index")
        self.assertNotIn(w1, wsm.manager.active)

    def test_broadcast_delivers_to_all_when_no_mutation(self):
        w1, w2 = FakeWS("a"), FakeWS("b")

        async def run():
            await wsm.manager.connect(w1)
            await wsm.manager.connect(w2)
            await wsm.manager.broadcast({"type": "tick"})

        asyncio.run(run())
        self.assertEqual(len(w1.received), 1)
        self.assertEqual(len(w2.received), 1)


class FootprintLazyTests(unittest.TestCase):
    """P1 : le premier trade (avant tout l2Book) doit atteindre la footprint."""

    def setUp(self):
        self._saved = collector.footprint_manager
        collector_state.markets.clear()

    def tearDown(self):
        collector.footprint_manager = self._saved
        collector_state.markets.clear()

    def test_first_trade_initializes_footprint_manager(self):
        collector.footprint_manager = None
        collector_state.markets["TEST"] = MarketState("TEST")
        ts = 1_700_000_000_000
        handle_trades("TEST", [{"sz": "1.0", "side": "B", "px": "100.0", "time": ts}])
        # avant fix : AttributeError (None.process_trade) avalé par l'except,
        # le global restait None et le trade était perdu
        self.assertIsNotNone(collector.footprint_manager,
                             "le lazy-init doit se produire au premier trade")

    def test_trade_reaches_footprint_manager(self):
        calls: list = []

        class FakeFM:
            def process_trade(self, *a, **k):
                calls.append(a)

        collector.footprint_manager = FakeFM()
        collector_state.markets["TEST"] = MarketState("TEST")
        ts = 1_700_000_000_000
        handle_trades("TEST", [{"sz": "2.5", "side": "B", "px": "42.0", "time": ts}])
        self.assertEqual(len(calls), 1, "le trade doit être feedé à la footprint")
        self.assertEqual(calls[0][0], "TEST")
        self.assertEqual(calls[0][1], 42.0)
        self.assertEqual(calls[0][2], 2.5)
        # la CVD/le marché restent mis à jour (non régression)
        self.assertEqual(collector_state.markets["TEST"].cvd, 2.5)


class SnapshotAtomicTests(unittest.TestCase):
    """P1 : l'écriture snapshot doit être atomique (tmp + os.replace)."""

    def test_snapshot_loop_uses_atomic_replace(self):
        """Oracle AST : dans snapshot_loop, write_text ne vise plus `path`
        directement et un os.replace publie le tmp."""
        tree = ast.parse(
            (BACKEND / "services" / "collector.py").read_text(encoding="utf-8")
        )
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "snapshot_loop"
        )
        src = ast.unparse(fn)
        self.assertIn("os.replace", src, "la publication doit passer par os.replace")
        self.assertIn(".tmp", src, "l'écriture doit viser un fichier temporaire")
        # le write_text direct sur `path` (troncature non atomique) est interdit
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "write_text":
                self.assertNotEqual(ast.unparse(node.func.value), "path",
                                    "write_text direct sur path = fenêtre non atomique")


if __name__ == "__main__":
    unittest.main()
