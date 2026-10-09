"""Ronde 5 — D-01 + D-02 : les deux MAJEURS de l'infra nocturne.

D-01 (aster_depth_engine) : le prune quotidien recevait la connexion de la
boucle asyncio et l'utilisait DANS un thread worker (asyncio.to_thread) →
sqlite3.ProgrammingError garanti au premier changement de jour → le
pruner mourait en silence ~5 min après chaque démarrage, la rétention
30 j ne s'exécutait jamais (croissance disque non bornée). Le fix : une
connexion jetable OUVERTE DANS le thread + un échec ne tue plus la tâche.

D-02 (aster_rate) : ~10 écrivains réels partagent aster_rate_state.json
en read-modify-write SANS verrou avec write_text direct → lost update
(l'entrée d'un collecteur disparaît) et torn write (JSON corrompu lu
comme {} → état effacé → sonde anti-ban VERTE avec 2200/2400 de poids
réel). Le fix : flock exclusif + tmp+os.replace.

    python tests/test_d01_d02_infra_night.py
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))   # aster_rate importé par chemin

from scripts import aster_depth_engine as ade  # noqa: E402
import aster_rate as ar  # noqa: E402


class TestD01Prune(unittest.TestCase):
    """Le bug exact : une connexion de la boucle utilisée dans un thread
    worker lève ProgrammingError ; une connexion OUVERTE dans le thread
    réussit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "depth.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
        CREATE TABLE depth_bins (symbol TEXT, ts INTEGER, side TEXT,
            bin_price REAL, qty REAL);
        CREATE TABLE depth_meta (symbol TEXT, ts INTEGER, mid REAL);
        """)
        now = int(time.time())
        old = now - (ade.RETENTION_DAYS + 2) * 86400
        for ts, n in ((old, 7), (now, 11)):
            for i in range(n):
                con.execute("INSERT INTO depth_bins VALUES ('BTCUSDT', ?, "
                            "'bid', ?, 1.0)", (ts - i * 60, 100.0 + i))
            con.execute("INSERT INTO depth_meta VALUES ('BTCUSDT', ?, 100.0)",
                        (ts,))
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_prune_old_dans_un_thread_worker_reussit(self):
        """LE test du bug : asyncio.to_thread(prune_old, con_de_la_boucle)
        levait sqlite3.ProgrammingError. La nouvelle signature prend le
        CHEMIN et ouvre la connexion dans le thread."""
        async def run():
            return await asyncio.to_thread(ade.prune_old, self.db)
        removed = asyncio.run(run())
        self.assertEqual(removed, 7)
        # les fraîches survivent, les vieilles (bins ET meta) sont prunées
        cutoff = int(time.time()) - ade.RETENTION_DAYS * 86400
        con = sqlite3.connect(self.db)
        old_bins = con.execute(
            "SELECT COUNT(*) FROM depth_bins WHERE ts < ?",
            (cutoff,)).fetchone()[0]
        old_meta = con.execute(
            "SELECT COUNT(*) FROM depth_meta WHERE ts < ?",
            (cutoff,)).fetchone()[0]
        kept_meta = con.execute("SELECT COUNT(*) FROM depth_meta").fetchone()[0]
        con.close()
        self.assertEqual(old_bins, 0)
        self.assertEqual(old_meta, 0)
        self.assertEqual(kept_meta, 1)   # la meta fraîche survit

    def test_le_motif_d_origine_leve_programming_error(self):
        """Documente le bug D-01 : une connexion créée dans le thread A et
        utilisée dans le thread B lève sqlite3.ProgrammingError — c'est
        exactement ce que faisait le pruner (asyncio.to_thread(prune_old,
        self.con)). D'où la signature CHEMIN : la connexion est ouverte
        DANS le thread."""
        con = sqlite3.connect(self.db)
        async def run():
            def bad():
                con.execute("CREATE INDEX IF NOT EXISTS idx_x ON depth_bins(ts)")
            with self.assertRaises(sqlite3.ProgrammingError):
                await asyncio.to_thread(bad)
        asyncio.run(run())
        con.close()

    def test_prune_old_accepte_path_et_str(self):
        self.assertGreater(ade.prune_old(str(self.db)), 0)

    def test_prune_old_db_sans_table_leve_sqlite_error_attrapable(self):
        # db créée vide par sqlite3.connect : pas de tables → OperationalError
        empty = Path(self.tmp.name) / "empty.db"
        with self.assertRaises(sqlite3.Error):
            ade.prune_old(empty)

    def test_pruner_survit_a_un_echec(self):
        """La boucle : un échec de prune n'est plus une mort silencieuse —
        la tâche reste vivante et re-tente au prochain cycle."""
        async def run():
            ade._running = True
            eng = ade.Engine(sqlite3.connect(":memory:"), ())
            sleeps = {"n": 0}

            async def fake_sleep(_s):
                sleeps["n"] += 1
                if sleeps["n"] >= 3:
                    ade._running = False   # arrête la boucle après 3 cycles

            with mock.patch.object(ade, "prune_old",
                                   side_effect=sqlite3.Error("db morte")), \
                 mock.patch.object(ade.asyncio, "sleep", fake_sleep):
                await asyncio.wait_for(eng.pruner(), timeout=5)
            return sleeps["n"]
        cycles = asyncio.run(run())
        self.assertEqual(cycles, 3, "la boucle a survécu à 3 échecs consécutifs")


class TestD02RateState(unittest.TestCase):
    """Le RMW multi-écrivains : sérialisé par flock, écriture atomique."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "aster_rate_state.json"
        self.lock = Path(self.tmp.name) / "aster_rate_state.lock"
        self._p_state = mock.patch.object(ar, "STATE", self.state)
        self._p_lock = mock.patch.object(ar, "LOCK", self.lock)
        self._p_state.start()
        self._p_lock.start()

    def tearDown(self):
        self._p_state.stop()
        self._p_lock.stop()
        self.tmp.cleanup()

    @staticmethod
    def _hdr(w: str):
        return {"X-MBX-USED-WEIGHT-1M": w}

    def test_deux_sources_successives_persistent_les_deux(self):
        self.assertEqual(ar.note_weight(self._hdr("500"), "oi_collector"), 500)
        self.assertEqual(ar.note_weight(self._hdr("2200"), "fetch_klines"), 2200)
        blob = json.loads(self.state.read_text())
        self.assertEqual(blob["max_recent"]["oi_collector"], 500)
        self.assertEqual(blob["max_recent"]["fetch_klines"], 2200)
        self.assertEqual(ar.worst_weight(), 2200)

    def test_huit_threads_concurrents_rien_n_est_perdu(self):
        """Lost update : 8 collecteurs (threads) notent chacun leur source
        — l'état final contient LES 8, et le fichier reste un JSON valide
        (jamais torn)."""
        sources = {f"src{i}": str(100 + i * 11) for i in range(8)}
        def worker(item):
            s, w = item
            for _ in range(5):
                ar.note_weight(self._hdr(w), s)
        threads = [threading.Thread(target=worker, args=(it,))
                   for it in sources.items()]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        blob = json.loads(self.state.read_text())   # lève si torn
        self.assertEqual(set(blob["max_recent"]), set(sources),
                         "un écrivain concurrent a été perdu (lost update)")
        self.assertEqual(
            blob["max_recent"],
            {s: int(w) for s, w in sources.items()})

    def test_echec_d_ecriture_visible_mais_jamais_bloquant(self):
        # répertoire d'état rendu inscriptible-faux : STATE reste absent,
        # note_weight retourne None (fail-soft) sans lever
        with mock.patch.object(ar, "_write_atomic",
                               side_effect=OSError("disque plein")):
            self.assertIsNone(ar.note_weight(self._hdr("300"), "x"))

    def test_header_absent_ne_touche_pas_le_fichier(self):
        self.assertIsNone(ar.note_weight({}, "oi_collector"))
        self.assertFalse(self.state.exists())

    def test_cle_inconnue_preservee(self):
        self.state.write_text(json.dumps({"updated_at": 1,
                                          "future_key": {"a": 1}}))
        ar.note_weight(self._hdr("42"), "s")
        blob = json.loads(self.state.read_text())
        self.assertEqual(blob["future_key"], {"a": 1})

    def test_rotation_par_source_apres_rotations(self):
        ar.note_weight(self._hdr("2000"), "vieux")
        # simule une note fraîche d'une AUTRE source bien après ROTATE_S
        future = time.time() + ar.ROTATE_S + 10
        with mock.patch.object(ar.time, "time", return_value=future):
            ar.note_weight(self._hdr("300"), "frais")
        blob = json.loads(self.state.read_text())
        self.assertNotIn("vieux", blob["max_recent"],
                         "le max périmé doit expirer (rotation par source)")
        self.assertEqual(blob["max_recent"]["frais"], 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
