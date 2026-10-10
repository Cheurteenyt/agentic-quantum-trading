"""Ronde 6 — D-03 + D-06 + D-08 + D-10 : les mineurs de l'infra nocturne.

D-03 (aster_blocktrades) : `exc.code in (418, 5, 502, 503)` — le 418
(ban IP, doctrine aster_rate : 2 min → 3 jours) était RETENTÉ après 1 s
(marteler un serveur qui a banni l'IP prolonge le ban), et le littéral `5`
n'existe pas en code HTTP (typo pour 500) : le 500 n'était JAMAIS retenté.
Désormais : 500/502/503 retry, 418 abort immédiat.

D-06 (fomo_access) : la docstring promet « 403 → un seul retry après
45 s » mais `attempt < RETRIES - 1` en accordait DEUX (le pattern martelé
qui a coûté le flag). Désormais : `attempt == 0`.

D-08 (aster_markprice_ws + aster_premium_collector) : un index
manquant/nul fabriquait une prime FICTIVE 0.0 — indistinguable d'une
vraie prime nulle dans premium_history (crowding_composite absorbe le
faux zéro). Désormais : la row est sautée comme une frame corrompue.

D-10 (daily_brief) : le connect fomo_rest.db était HORS du try — un
répertoire data/fomo absent tuait le brief entier (traceback) au lieu
d'une section « indispo ».

Aucun appel réseau réel.

    python tests/test_r6_night_minors.py
"""
from __future__ import annotations

import ast
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))   # scripts importés par chemin

import aster_blocktrades as bt  # noqa: E402
import fomo_access as fa  # noqa: E402
import aster_markprice_ws as amw  # noqa: E402


def _http_error(code: int):
    return urllib.error.HTTPError(
        "https://x", code, "err", {}, io.BytesIO(b""))


class _FakeResp:
    def __init__(self, payload=b"{}"):
        self.headers = {}
        self._raw = json.dumps(payload).encode() if isinstance(payload, dict) else payload

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestD03BlocktradesRetry(unittest.TestCase):
    def setUp(self):
        # ne touche jamais l'état de poids réel
        self._nw = mock.patch.object(
            bt.aster_rate, "note_weight", lambda *a, **k: None)
        self._nw.start()

    def tearDown(self):
        self._nw.stop()

    def test_500_est_desormais_reteme(self):
        calls = []
        def urlopen(req, timeout=None):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise _http_error(500)
            return _FakeResp({"ok": True})
        with mock.patch.object(bt.urllib.request, "urlopen", urlopen):
            payload, _w = bt.http_get_json("https://x/trades")
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(len(calls), 2, "un 500 doit être retenté (typo « 5 »)")

    def test_418_ban_ip_abort_immediat(self):
        calls = []
        def urlopen(req, timeout=None):
            calls.append(req.full_url)
            raise _http_error(418)
        with mock.patch.object(bt.urllib.request, "urlopen", urlopen):
            with self.assertRaises(urllib.error.HTTPError):
                bt.http_get_json("https://x/trades")
        self.assertEqual(len(calls), 1,
                         "un ban IP ne doit JAMAIS être martelé")

    def test_502_reteme_comportement_inchange(self):
        calls = []
        def urlopen(req, timeout=None):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise _http_error(502)
            return _FakeResp({"ok": True})
        with mock.patch.object(bt.urllib.request, "urlopen", urlopen):
            payload, _w = bt.http_get_json("https://x/trades")
        self.assertEqual(len(calls), 2)


class _FakeFetcher:
    """scrapling.Fetcher factice : status programmé, compte les appels."""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        st = self.statuses[min(self.calls - 1, len(self.statuses) - 1)]
        return type("R", (), {"status": st})()


class TestD06Fomo403(unittest.TestCase):
    def setUp(self):
        # aucun vrai sleep : 45 s de backoff 403 et le throttle 1.5 s
        self._sleep = mock.patch.object(fa.time, "sleep", lambda s: None)
        self._sleep.start()

    def tearDown(self):
        self._sleep.stop()

    def _run_get(self, statuses):
        fake = _FakeFetcher(statuses)
        with mock.patch.object(fa, "Fetcher", fake):
            with self.assertRaises(RuntimeError) as ctx:
                fa._get("https://fomo.family/x")
        self.assertIn("HTTP", str(ctx.exception))
        return fake.calls

    def test_403_un_seul_retry_comme_documente(self):
        calls = self._run_get([403])
        self.assertEqual(calls, 2,
                         "docstring : « 403 → un seul retry » — l'ancien "
                         "code en accordait 2 (pattern martelé)")

    def test_401_echec_immediat(self):
        calls = self._run_get([401])
        self.assertEqual(calls, 1)

    def test_429_retries_complets_inchanges(self):
        calls = self._run_get([429])
        self.assertEqual(calls, fa.RETRIES)


class TestD08PremiumFictive(unittest.TestCase):
    def test_idx_nul_la_row_est_sautee(self):
        frame = json.dumps({"data": [{"s": "BTCUSDT", "p": "100", "i": "0",
                                      "r": "0.0001", "T": 1}]})
        self.assertEqual(amw.parse_frame(frame), [],
                         "une prime fictive 0.0 ne doit plus être fabriquée")

    def test_idx_valide_la_prime_est_calculee(self):
        frame = json.dumps({"data": [{"s": "BTCUSDT", "p": "101", "i": "100",
                                      "r": "0.0001", "T": 1}]})
        rows = amw.parse_frame(frame)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["prem"], 1.0)

    def test_idx_absent_la_row_est_sautee(self):
        frame = json.dumps({"data": [{"s": "BTCUSDT", "p": "100",
                                      "r": "0.0001", "T": 1}]})
        self.assertEqual(amw.parse_frame(frame), [])

    def test_oracle_premium_collector_plus_de_prime_fictive(self):
        src = (ROOT / "scripts/aster_premium_collector.py").read_text()
        self.assertNotIn("if idx else 0.0", src,
                         "la prime fictive 0.0 est réapparue")


class TestD10DailyBriefConnectDansTry(unittest.TestCase):
    def test_oracle_ast_le_connect_fomo_est_dans_le_try(self):
        tree = ast.parse(
            (ROOT / "scripts/daily_brief.py").read_text())
        found_connect_in_try = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for stmt in node.body:
                if (isinstance(stmt, ast.Assign)
                        and isinstance(stmt.value, ast.Call)
                        and getattr(stmt.value.func, "attr", "") == "connect"
                        and any("fomo_rest.db" in ast.dump(a)
                                for a in stmt.value.args)):
                    found_connect_in_try = True
        self.assertTrue(found_connect_in_try,
                        "le connect fomo_rest.db doit être DANS le try "
                        "(un répertoire data/fomo absent ne doit pas tuer "
                        "le brief entier)")

    def test_repertoire_fomo_absent_le_brief_survit(self):
        """Le test D-10 bout-en-bout : le script complet s'exécute dans le
        clone (data/ absente) — AVANT le fix il crashait au connect.

        HERMÉTIQUE (10/10) : `daily_brief.py` résout son ROOT par
        `Path(__file__).resolve().parents[1]`. On le rejoue donc depuis un
        ROOT TEMPORAIRE, où `data/` n'existe pas par construction. L'ancienne
        version le lançait depuis le vrai dépôt : elle n'était verte que sur
        une machine où `data/fomo/` manquait — donc en CI (data/ gitignoré)
        et jamais chez le dev, où le brief lisait les vraies DB.
        """
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "scripts").mkdir()
            (t / "reports").mkdir()   # daily_brief écrit son log ici
            shutil.copy2(ROOT / "scripts" / "daily_brief.py",
                         t / "scripts" / "daily_brief.py")
            r = subprocess.run(
                [sys.executable, str(t / "scripts" / "daily_brief.py")],
                capture_output=True, text=True, timeout=60,
                env={"PATH": "/usr/bin:/bin", "HOME": tmp})
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertIn("GRADUATIONS : indispo", r.stdout)
            # …et le brief va jusqu'au BOUT (les sections 5-6 ne sont pas
            # perdues en route, c'est tout l'objet du fix D-10)
            self.assertIn("ACTIONS du jour", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
