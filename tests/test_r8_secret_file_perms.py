"""Ronde 8 — secrets : permissions et journalisation.

Trois constats ronde 8 :
  - D-05b : le cache JWT fomo (Privy, session prod-api.fomo.family) était
    écrit en 0644 non atomique par 4 écrivains concurrents — lisible par
    tout process local, lisible DÉCHIRÉ par un lecteur concurrent ;
  - N-1 : save_aster_key.py journalisait les 6 premiers caractères de la
    clé dans /tmp/save_key.log (world-readable, nom prédictible, open("a")
    suit les symlinks) ;
  - N-2/N-3 : fragments de clés/token échoés dans les journaux
    (web_agent.py init, fomo_ws_daemon.py RuntimeError CDP).

write_secret (scripts/secret_io.py) : mkstemp 0600 dans le répertoire
cible + os.replace — aucune fenêtre world-readable, aucune lecture
déchirée, rattrapage du mode au premier refresh même si le fichier
existe déjà en 0644.
"""
from __future__ import annotations

import ast
import contextlib
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.secret_io import write_secret


class TestWriteSecret(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "sub" / "cache.txt"
        self.target.parent.mkdir(parents=True, exist_ok=True)

    def test_mode_0600_et_contenu_exact(self):
        write_secret(self.target, "SECRETTOKEN")
        mode = stat.S_IMODE(os.stat(self.target).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(self.target.read_text(), "SECRETTOKEN")

    def test_bytes(self):
        write_secret(self.target, b"\x00\x01\xff")
        self.assertEqual(self.target.read_bytes(), b"\x00\x01\xff")

    def test_rattrapage_d_un_fichier_existant_0644(self):
        self.target.write_text("ancien 0644")
        os.chmod(self.target, 0o644)
        write_secret(self.target, "nouveau")
        self.assertEqual(stat.S_IMODE(os.stat(self.target).st_mode), 0o600)

    def test_aucun_tmp_residuel_apres_succes(self):
        write_secret(self.target, "ok")
        residue = [p for p in self.target.parent.iterdir() if p.name != self.target.name]
        self.assertEqual(residue, [])

    def test_echec_laisse_le_fichier_precedent_intact_et_nettoie_le_tmp(self):
        self.target.write_text("précédent")
        real_replace = os.replace

        def boom(a, b):
            raise OSError("remplacement simulé impossible")

        os.replace = boom
        try:
            with self.assertRaises(OSError):
                write_secret(self.target, "nouveau")
        finally:
            os.replace = real_replace
        self.assertEqual(self.target.read_text(), "précédent")
        residue = [p for p in self.target.parent.iterdir() if p.name != self.target.name]
        self.assertEqual(residue, [])

    def test_pas_de_fenetre_world_readable_pendant_lecteur_concurrent(self):
        # un lecteur qui lit PENDANT l'écriture ne voit jamais d'état déchiré :
        # le contenu du fichier final est TOUJOURS l'une des 2 versions complètes
        import threading
        write_secret(self.target, "AAAA")
        stop = threading.Event()
        seen = set()

        def reader():
            while not stop.is_set():
                # le fichier peut être absent le temps du rename : absent = on
                # réessaie (l'oracle compte les CONTENUS lus, jamais un échec)
                with contextlib.suppress(FileNotFoundError):
                    seen.add(self.target.read_text())

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        try:
            for i in range(30):
                write_secret(self.target, "AAAA" if i % 2 == 0 else f"BBBBBBBB{i}")
        finally:
            stop.set()
            t.join(timeout=2)
        # chaque lecture = une version COMPLÈTE (jamais tronquée/mixée)
        valid = {"AAAA"} | {f"BBBBBBBB{i}" for i in range(1, 30, 2)}
        torn = seen - valid
        self.assertFalse(torn, f"lectures déchirées : {torn}")


class _SourceOracle(unittest.TestCase):
    """Le contrat : plus aucun write_text nu sur un porteur de secret,
    plus aucun fragment de secret dans les journaux — une mutation qui
    restaure l'ancien code rougit ici."""

    SOURCES = {
        "fomo_ws_daemon": ROOT / "scripts" / "fomo_ws_daemon.py",
        "fomo_session_monitor": ROOT / "scripts" / "fomo_session_monitor.py",
        "fomo_rest_collector": ROOT / "scripts" / "fomo_rest_collector.py",
        "fomo_ohlcv_backfill": ROOT / "scripts" / "fomo_ohlcv_backfill.py",
    }
    JWT_VAR = {"fomo_ws_daemon": "JWT_CACHE", "fomo_session_monitor": "JWT_CACHE",
               "fomo_rest_collector": "JWT_CACHE", "fomo_ohlcv_backfill": "_JWT_CACHE"}

    def test_aucun_write_text_sur_les_caches_jwt(self):
        for mod, path in self.SOURCES.items():
            with self.subTest(module=mod):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and \
                       isinstance(node.func, ast.Attribute) and \
                       node.func.attr == "write_text" and \
                       isinstance(node.func.value, ast.Name) and \
                       node.func.value.id == self.JWT_VAR[mod]:
                        self.fail(f"{mod}:{node.lineno} : {self.JWT_VAR[mod]}.write_text() est de retour")

    def test_write_secret_importe_et_utilise_partout(self):
        for mod, path in self.SOURCES.items():
            with self.subTest(module=mod):
                src = path.read_text(encoding="utf-8")
                self.assertIn("write_secret", src, f"{mod} : helper non branché")

    def test_save_aster_key_plus_de_fragment_de_cle_ni_de_tmp(self):
        src = (ROOT / "scripts" / "save_aster_key.py").read_text(encoding="utf-8")
        self.assertNotIn("v[:6]", src)
        self.assertNotIn("/tmp", src)
        self.assertIn("O_NOFOLLOW", src)
        self.assertIn('0o600', src)

    def test_web_agent_ne_logue_plus_de_prefixe_de_cle(self):
        src = (ROOT / "backend" / "services" / "web_agent.py").read_text(encoding="utf-8")
        self.assertNotIn("api_key[:10]", src)

    def test_ws_daemon_ne_echo_plus_le_stdout_dans_l_exception(self):
        src = (ROOT / "scripts" / "fomo_ws_daemon.py").read_text(encoding="utf-8")
        self.assertNotIn("{r.stdout[:80]}", src)


if __name__ == "__main__":
    unittest.main()
