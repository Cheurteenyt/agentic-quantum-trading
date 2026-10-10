"""R9-B — deux défauts API validés sur le clone10 (main @8e73f90) :

1. [P0 sécu] vision.analyze_chart lisait N'IMPORTE QUEL chemin du serveur et
   envoyait son contenu en base64 à l'API Gemini (exfiltration de .env, clés,
   DBs via des notes ciblées). La route est admin-only, mais la boucle locale
   (local-open / tunnel CF) la rend atteignable. Fix : jail sur
   data/screenshots, par NOM de fichier.
2. [P1] famille [-limit:] sans clamp sur 4 routers (market.signals,
   chat.history, vision.history, intel.signals/recent) : limit=0 => [-0:]
   renvoyait la LISTE ENTIÈRE (chaque JSON chargé en RAM à chaque poll),
   limit négatif inversait le sens du slice. Même pattern que celui corrigé
   dans agents.py par une PR ouverte — les 4 sites restants le réclament.

Mutations négatives : rétablir la lecture arbitraire (1) ou retirer un clamp
(2) doit remettre les tests en échec.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import routers.vision as vision  # noqa: E402
import routers.market as market  # noqa: E402
import routers.chat as chat  # noqa: E402
import routers.intel as intel  # noqa: E402
from routers.vision import AnalyzeRequest, analyze_chart  # noqa: E402
from routers.market import get_signals  # noqa: E402
from routers.chat import get_history  # noqa: E402
from routers.vision import analysis_history  # noqa: E402
from routers.intel import get_recent_signals  # noqa: E402


class _SecretSessionStub:
    """Remplace aiohttp.ClientSession dans vision : échec immédiat, zéro
    réseau — le fallback screenshot doit s'arrêter proprement."""

    def __init__(self, *a, **k):
        raise ConnectionError("stub: pas de serveur screenshot en test")


class VisionJailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.secret = Path(self.tmp.name) / "secret.env"
        self.secret.write_text("CORE_ADMIN_TOKEN=supersecret\n", encoding="utf-8")
        self._orig_call_gemini = vision.call_gemini
        self._orig_aiohttp = vision.aiohttp.ClientSession
        vision.aiohttp.ClientSession = _SecretSessionStub
        self._signals_before = set(vision.SIGNALS_DIR.glob("vision_*.json")) \
            if vision.SIGNALS_DIR.exists() else set()

    def tearDown(self):
        vision.call_gemini = self._orig_call_gemini
        vision.aiohttp.ClientSession = self._orig_aiohttp
        after = set(vision.SIGNALS_DIR.glob("vision_*.json")) \
            if vision.SIGNALS_DIR.exists() else set()
        for f in after - self._signals_before:
            f.unlink(missing_ok=True)
        self.tmp.cleanup()

    def test_outside_file_is_not_read_and_never_reaches_gemini(self):
        seen: list = []

        async def fake_gemini(img_b64, **k):
            seen.append(img_b64)
            return "analysis"

        vision.call_gemini = fake_gemini
        req = AnalyzeRequest(screenshot_path=str(self.secret))
        result = asyncio.run(analyze_chart(req))
        self.assertEqual(seen, [],
                         "le contenu du fichier extérieur ne doit JAMAIS "
                         "atteindre Gemini")
        # le résultat ne contient pas le secret sous quelque forme
        self.assertNotIn("supersecret", json.dumps(result))

    def test_relative_escape_is_jailed_too(self):
        # ../.. remontant REEL (os.path.relpath garantit que le chemin sans
        # fix existerait vraiment) : la jail prend le NOM seulement
        import os
        seen: list = []

        async def fake_gemini(img_b64, **k):
            seen.append(img_b64)
            return "analysis"

        vision.call_gemini = fake_gemini
        esc = os.path.relpath(self.secret, Path.cwd())
        assert esc.startswith(".."), "le secret doit être hors du cwd pour ce test"
        req = AnalyzeRequest(screenshot_path=esc)
        result = asyncio.run(analyze_chart(req))
        self.assertEqual(seen, [])
        self.assertNotIn("supersecret", json.dumps(result))

    def test_legitimate_screenshot_in_dir_still_works(self):
        shots = vision.SCREENSHOTS_DIR
        shots.mkdir(parents=True, exist_ok=True)
        ok = shots / "r9_jail_ok.png"
        payload = b"\x89PNG-r9-test-payload"
        ok.write_bytes(payload)
        seen: list = []

        async def fake_gemini(img_b64, **k):
            seen.append(img_b64)
            return "analysis"

        try:
            vision.call_gemini = fake_gemini
            req = AnalyzeRequest(screenshot_path=str(ok))
            result = asyncio.run(analyze_chart(req))
        finally:
            ok.unlink(missing_ok=True)
        self.assertEqual(len(seen), 1, "une vraie capture doit être analysée")
        self.assertEqual(base64.b64decode(seen[0]), payload)
        self.assertEqual(result.get("analysis"), "analysis")

    def test_missing_file_falls_back_without_crash(self):
        async def fake_gemini(img_b64, **k):
            return "analysis"

        vision.call_gemini = fake_gemini
        req = AnalyzeRequest(screenshot_path=str(Path(self.tmp.name) / "absent.png"))
        result = asyncio.run(analyze_chart(req))
        # fallback screenshot stub (connexion refusée) => erreur propre
        self.assertIn("error", result)


def _mk_json_file(d: Path, name: str) -> Path:
    f = d / name
    f.write_text(json.dumps({"r9": name}), encoding="utf-8")
    return f


class ClampTests(unittest.TestCase):
    """P1 : limit=0 ne doit plus renvoyer la liste entière, ni en négatif."""

    @staticmethod
    def _count(r):
        if isinstance(r, dict):
            for k in ("signals", "history"):
                if k in r:
                    return len(r[k])
            for v in r.values():
                if isinstance(v, list):
                    return len(v)
            return 0
        return len(r)

    def _run_dir_case(self, dirpath: Path, glob: str, maker, fetcher, names):
        """HERMÉTIQUE (10/10) : les routers résolvent `data/signals` et
        `data/chat` RELATIVEMENT au cwd (`Path("data/signals")`). Sans ce
        chdir, le test écrivait ses 3 fixtures dans le VRAI `data/` du dépôt
        et lisait en plus les fichiers qui s'y trouvaient déjà — vert en CI
        (clone propre, `data/*` gitignoré) et rouge en local dès qu'un seul
        `signal_*.json` traînait : 3 fixtures + 4 vrais = 7 au lieu de 3.
        On s'exécute donc dans un ROOT temporaire, où l'ambiant est vide par
        construction. Le cwd est restauré même en cas d'échec.
        """
        cwd0 = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                dirpath.mkdir(parents=True, exist_ok=True)
                for n in names:
                    maker(dirpath, n)
                r0 = asyncio.run(fetcher(limit=0))
                rn = asyncio.run(fetcher(limit=-1))
                r2 = asyncio.run(fetcher(limit=2))
                rb = asyncio.run(fetcher(limit=1000))
        finally:
            os.chdir(cwd0)
        return self._count(r0), self._count(rn), self._count(r2), self._count(rb)

    def test_market_signals_clamped(self):
        c0, cn, c2, cb = self._run_dir_case(
            market.Path("data/signals"), "signal_*.json",
            _mk_json_file, get_signals,
            [f"signal_r9test{i}.json" for i in range(3)])
        self.assertEqual((c0, cn, c2, cb), (1, 1, 2, 3),
                         "limit=0/-1 => 1 (clampé), limit=2 => 2, limit=1000 => 3")

    def test_chat_history_clamped(self):
        c0, cn, c2, cb = self._run_dir_case(
            chat.HISTORY_DIR, "chat_*.json",
            _mk_json_file, get_history,
            [f"chat_r9test{i}.json" for i in range(3)])
        self.assertEqual((c0, cn, c2, cb), (1, 1, 2, 3))

    def test_vision_history_clamped(self):
        c0, cn, c2, cb = self._run_dir_case(
            vision.SIGNALS_DIR, "vision_*.json",
            _mk_json_file, analysis_history,
            [f"vision_r9test{i}.json" for i in range(3)])
        self.assertEqual((c0, cn, c2, cb), (1, 1, 2, 3))

    def test_intel_recent_signals_clamped(self):
        invs = [
            {"id": f"i{i}", "started_at": i, "completed_at": float(i),
             "result": {"triggered_signal": {
                 "type": "listing", "source": "r9", "priority": "HIGH",
                 "data": {}}}}
            for i in range(3)
        ]

        class StubAgent:
            def list_active_investigations(self, limit: int = 20):
                return invs

        orig = intel.get_web_agent
        intel.get_web_agent = lambda: StubAgent()
        try:
            r0 = asyncio.run(get_recent_signals(limit=0))
            r2 = asyncio.run(get_recent_signals(limit=2))
        finally:
            intel.get_web_agent = orig
        self.assertEqual(len(r0), 1, "limit=0 doit être clampé à 1")
        self.assertEqual(len(r2), 2)


if __name__ == "__main__":
    unittest.main()
