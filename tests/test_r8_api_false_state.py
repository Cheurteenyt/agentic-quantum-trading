"""Ronde 8 — fausses infos d'API et clamps manquants (front + backend).

C5  Agents.tsx transformait une erreur HTTP (401 gate, 500) en badge
    « INACTIF » et « No signals » — sans check res.ok, le payload d'erreur
    JSON remplaçait les données et running tombait à false.
C7  AlphaLab.tsx fabriquait un prix d'entrée à 0.5 pour un marché sans
    prix — le garde-fou backend missing_price était contourné et le PnL
    affiché portait sur une entrée inventée.
C2  backend/routers/agents.py : [-0:] = LISTE ENTIÈRE — limit=0/limit<0
    était un piège public (même clamp que main.py:911 désormais).
C3  backend/routers/news.py : un JSON Gemini absent/cassé laissait
    bias = {} SILENCIEUX — indistinguable d'une analyse valide amputée.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.routers import agents as agents_router

try:
    import firecrawl  # noqa: F401  (présent en CI via requirements)
except ImportError:
    # local sans firecrawl : stub minimal — la logique testée ici
    # (clamp limit, drapeau bias_parsed du cache) ne touche jamais le client
    import types
    _stub = types.ModuleType("firecrawl")

    class _FirecrawlStub:
        def __init__(self, *args, **kwargs) -> None: ...

    _stub.Firecrawl = _FirecrawlStub
    sys.modules["firecrawl"] = _stub

from backend.routers import news as news_router


def _signal_file(path: Path, ts: int, symbol: str) -> None:
    path.write_text(json.dumps({"symbol": symbol, "ts": ts}), encoding="utf-8")


class TestClampLimit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = agents_router.SIGNALS_DIR
        agents_router.SIGNALS_DIR = Path(self.tmp.name)
        self.addCleanup(setattr, agents_router, "SIGNALS_DIR", self._old)
        d = Path(self.tmp.name)
        for i in range(150):
            _signal_file(d / f"signal_{i:05d}.json", i, f"S{i}")

    def test_limit_zero_ne_renvoie_plus_toute_la_liste(self):
        out = agents_router.get_all_signals(limit=0)
        self.assertLessEqual(len(out["signals"]), 1)  # clamp min 1, JAMAIS tout

    def test_limit_negatif_pareil(self):
        out = agents_router.get_all_signals(limit=-5)
        self.assertLessEqual(len(out["signals"]), 1)

    def test_limit_borne_a_100(self):
        out = agents_router.get_all_signals(limit=500)
        self.assertLessEqual(len(out["signals"]), 100)

    def test_limit_normal_fonctionne(self):
        out = agents_router.get_all_signals(limit=2)
        self.assertEqual(len(out["signals"]), 2)

    def test_ordre_recent_dabord_conserve(self):
        out = agents_router.get_all_signals(limit=2)
        syms = [s["symbol"] for s in out["signals"]]
        self.assertEqual(syms, ["S149", "S148"])


class TestBiasParsed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = news_router.NEWS_DIR
        news_router.NEWS_DIR = Path(self.tmp.name)
        self.addCleanup(setattr, news_router, "NEWS_DIR", self._old)

    def _write_cache(self, bias):
        (Path(self.tmp.name) / "gold_analysis_latest.json").write_text(
            json.dumps({"ts": time.time(), "bias": bias}), encoding="utf-8")

    def test_cache_bias_valide_drapeau_vrai(self):
        self._write_cache({"direction": "bullish", "confidence": 0.7})
        out = asyncio.run(news_router.get_gold_bias())
        self.assertTrue(out["bias_parsed"])

    def test_cache_bias_vide_drapeau_faux(self):
        # l'ancien monde : {} sans drapeau — indistinguable d'une analyse OK
        self._write_cache({})
        out = asyncio.run(news_router.get_gold_bias())
        self.assertFalse(out["bias_parsed"])
        self.assertEqual(out["bias"], {})

    def test_le_drapeau_est_ecrit_sur_les_trois_sites_de_retour(self):
        src = (ROOT / "backend" / "routers" / "news.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("bias_parsed"), 3)


if __name__ == "__main__":
    unittest.main()
