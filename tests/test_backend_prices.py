"""r7 — le backend renvoyait des PRIX FANTÔMES comme prix live.

Trois replis inventés, affichés au Dashboard avec le badge LIVE :

1. `get_prices` : `binance.get("btc", {"price": 78407.5, ...})` — un BTC
   d'une autre époque, renvoyé dès que l'appel d'un SEUL symbole
   réussissait (`source = "binance+scrape" if binance` masquait l'échec
   partiel). Le frontend `firstFiniteNumber(..., prices?.btc?.price)`
   affichait le chiffre faux plutôt que de passer à la vraie source
   suivante (le WS).
2. `_fetch_xau_price` : repli `4679.0` sur échec Yahoo — même faille.
3. `_market_update_payload` : `change_24h: 0.0` codé en dur, diffusé
   pour chaque coin à chaque tick — le TickerStrip l'affichait
   « +0.00% » en vert (change >= 0), un faux signal haussier permanent.

Fix : un prix indisponible est null / {} / champ absent. Le frontend
(firstFiniteNumber, firstUsefulPercent, `change != null`) retombe
alors sur la source suivante au lieu d'afficher un chiffre faux.

Tests SANS réseau : les caches globaux sont pré-remplis (TTL), urlopen
est remplacé.

    python tests/test_backend_prices.py
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))   # imports 'services.*' de main.py

_spec = importlib.util.spec_from_file_location(
    "backend_main", ROOT / "backend" / "main.py")
main = importlib.util.module_from_spec(_spec)
sys.modules["backend_main"] = main
_spec.loader.exec_module(main)


try:
    from fastapi.testclient import TestClient
    HAS_CLIENT = True
except ImportError:          # pragma: no cover - fastapi est dans le lock
    HAS_CLIENT = False


def _preparer_caches(binance: dict, xau: dict | None = None):
    """Pré-remplit les caches TTL : aucun appel réseau dans les tests."""
    main._BINANCE_CACHE = {"data": binance, "ts": time.time()}
    if xau is not None:
        main._XAU_CACHE = {"data": xau, "ts": time.time()}


@unittest.skipUnless(HAS_CLIENT, "fastapi/httpx requis")
class TestGetPrices(unittest.TestCase):
    def _get(self) -> dict:
        import asyncio
        return asyncio.run(main.get_prices())

    def test_prix_complets(self):
        _preparer_caches({
            "btc": {"price": 63000.0, "change_24h": 1.5},
            "eth": {"price": 3100.0, "change_24h": -0.4},
        })
        r = self._get()
        self.assertEqual(r["btc"]["price"], 63000.0)
        self.assertEqual(r["eth"]["price"], 3100.0)
        self.assertEqual(r["source"], "binance")

    def test_echec_partiel_aucun_prix_fantome(self):
        """LE bug : eth réussit, btc échoue -> btc devait valoir 78407.5
        avec source 'binance+scrape'. Désormais : null + 'partial'."""
        _preparer_caches({
            "eth": {"price": 3100.0, "change_24h": -0.4},
        })
        r = self._get()
        self.assertIsNone(r["btc"]["price"])
        self.assertIsNone(r["btc"]["change_24h"])
        self.assertEqual(r["eth"]["price"], 3100.0)
        self.assertEqual(r["source"], "binance-partial")
        self.assertNotIn("78407.5", str(r), "aucun BTC fantôme")

    def test_echec_total_aucun_prix_fantome(self):
        _preparer_caches({})
        r = self._get()
        self.assertIsNone(r["btc"]["price"])
        self.assertIsNone(r["eth"]["price"])
        self.assertEqual(r["source"], "unavailable")


class TestPayloadBroadcast(unittest.TestCase):
    def test_aucun_change_24h_factice(self):
        class _OB(dict):
            pass

        class _Mkt:
            last_price = 100.0
            orderbook = {"bids": [{"px": 99.5}], "asks": [{"px": 100.5}]}

        class _MktZero:
            last_price = 0.0
            orderbook = {}

        payload = main._market_update_payload(
            {"BTC": _Mkt(), "FLAT": _MktZero()}, {"price": 4679.5}, 123.0)
        self.assertEqual(payload["type"], "market_update")
        self.assertEqual(payload["hyperliquid"]["BTC"]["px"], 100.0)
        self.assertEqual(payload["hyperliquid"]["BTC"]["bid"], 99.5)
        self.assertNotIn("change_24h", payload["hyperliquid"]["BTC"],
                         "le 0.0 codé en dur ne doit pas revenir")
        self.assertNotIn("FLAT", payload["hyperliquid"],
                         "px == 0 est filtré comme avant")

    def test_orderbook_vide_replie_sur_px(self):
        class _Mkt:
            last_price = 50.0
            orderbook = {"bids": [], "asks": []}

        payload = main._market_update_payload({"X": _Mkt()}, {}, 1.0)
        self.assertEqual(payload["hyperliquid"]["X"]["bid"], 50.0)


class TestXauEchecReseau(unittest.TestCase):
    def test_echec_yahoo_renvoie_dict_vide(self):
        """Avant : {'price': 4679.0, ..., 'source': 'fallback'} — un prix
        d'or inventé. Désormais : {} (indisponible ≠ faux)."""
        main._XAU_CACHE = {"data": {"keep": True}, "ts": 0.0}   # TTL forcé
        import urllib.request
        import urllib.error

        class _Boom:
            def __init__(self, *a, **k):
                raise urllib.error.URLError("réseau coupé (test)")

        old = urllib.request.urlopen
        urllib.request.urlopen = _Boom
        try:
            out = main._fetch_xau_price()
        finally:
            urllib.request.urlopen = old
        self.assertEqual(out, {})
        self.assertNotIn("price", out)


class TestOracleStatique(unittest.TestCase):
    """Les littéraux fantômes ne doivent plus exister dans main.py."""

    def test_aucun_prix_hardcode(self):
        src = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fantomes = {"78407.5", "2359.75", "4679.0"}
        restants = [
            ast.unparse(n) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, float)
            and str(n.value) in fantomes
        ]
        self.assertEqual(restants, [],
                         f"prix inventé réintroduit : {restants}")


if __name__ == "__main__":
    unittest.main()
