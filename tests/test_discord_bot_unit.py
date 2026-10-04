"""Les tests unitaires du bot Discord — la logique pure, zéro réseau.

Le quant a sa suite (773 tests) ; le bot n'avait RIEN. Première couche :
les cookies signés du dashboard (le roundtrip, la falsification, l'expiration),
les regex de parse des calls, le registre du store sur une DB temporaire.
"""
from __future__ import annotations

import base64
import json
import tempfile
import time
import unittest
from pathlib import Path


class TestDashboardCookies(unittest.TestCase):
    """Le cookie de session du dashboard : signé HMAC, expirable, infalsifiable."""

    @classmethod
    def setUpClass(cls):
        from discord_bot import dashboard as d
        cls.d = d
        if not d.DISCORD_CLIENT_SECRET:
            raise unittest.SkipTest("DISCORD_CLIENT_SECRET absent du .env")

    def test_roundtrip(self):
        cookie = self.d._make_cookie("123456789012345678")
        self.assertEqual(self.d._read_cookie(cookie), "123456789012345678")

    def test_falsifie(self):
        # le payload est réécrit mais la signature reste celle de l'original
        cookie = self.d._make_cookie("111111111111111111")
        raw, sig = cookie.rsplit(".", 1)
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        body["uid"] = "999999999999999999"  # l'usurpation d'identité
        new_raw = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
        self.assertIsNone(self.d._read_cookie(f"{new_raw}.{sig}"))
        # et un cookie entièrement fabriqué sans clé
        self.assertIsNone(self.d._read_cookie(f"{raw}.deadbeef"))

    def test_expiration(self):
        body = json.dumps({"uid": "42", "exp": int(time.time()) - 10})
        raw = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
        signed = f"{raw}.{self.d._sign(raw.encode())}"
        self.assertIsNone(self.d._read_cookie(signed))

    def test_garbage(self):
        for junk in ("", "sans-point", "a.b", ".x", None):
            self.assertIsNone(self.d._read_cookie(junk or ""))


class TestCallParsing(unittest.TestCase):
    """Les regex des calls : $CASHTAG prioritaire, sinon le mot après la direction."""

    @classmethod
    def setUpClass(cls):
        from discord_bot.cogs import trading as t
        cls.t = t
        cls.SHORTS = {"short", "bearish", "vente", "vend", "shorting",
                      "shorted", "sold", "selling"}

    def _dir(self, text):
        m = self.t.DIRECTION_RE.search(text)
        return m.group(1).lower() if m else None

    def test_directions(self):
        self.assertEqual(self._dir("je short BTC ici"), "short")
        self.assertEqual(self._dir("LONG ETH maintenant"), "long")
        self.assertIsNone(self._dir("le temps passe"))

    def test_cashtag_prio(self):
        import re
        # le $CASHTAG gagne même quand un autre ticker suit la direction
        m = re.search(r"\$([A-Za-z]{2,10})", "short $SOL mais regarde PEPE")
        self.assertEqual(m.group(1), "SOL")

    def test_side_mapping(self):
        self.assertEqual(self._dir("short ADA"), "short")  # d = -1.0
        self.assertEqual(self._dir("long ADA"), "long")    # d = +1.0


class TestStoreRegistry(unittest.TestCase):
    """Le registre (salons/rôles/règles) sur une DB temporaire — le vrai schéma."""

    @classmethod
    def setUpClass(cls):
        from discord_bot import store
        cls.store = store
        cls._tmp = tempfile.TemporaryDirectory()
        store.DB = Path(cls._tmp.name) / "test_discord.db"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_roundtrip(self):
        s = self.store
        s.reg_set(123, "channel_log", "456")
        s.reg_set(123, "channel_log", "789")  # REPLACE — une seule valeur
        rows = s.reg_get(123, "channel_log")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], "789")
        self.assertEqual(s.reg_channel(123, "log"), 789)

    def test_regles_et_roles(self):
        s = self.store
        s.reg_set(1, "rule_no_links", "111")
        s.reg_set(1, "rule_no_links", "222")
        self.assertTrue(s.reg_rule(1, 111, "no_links"))
        self.assertFalse(s.reg_rule(1, 333, "no_links"))
        s.reg_set(1, "role_admin", "999")
        self.assertTrue(s.reg_has_role([888, 999], 1, "admin"))
        self.assertFalse(s.reg_has_role([888], 1, "admin"))

    def test_delete(self):
        s = self.store
        s.reg_set(2, "channel_bienvenue", "555")
        s.reg_del(2, "channel_bienvenue", "555")
        self.assertIsNone(s.reg_channel(2, "bienvenue"))

    def test_isolation_guildes(self):
        s = self.store
        s.reg_set(10, "channel_log", "111")
        s.reg_set(20, "channel_log", "222")
        self.assertEqual(s.reg_channel(10, "log"), 111)
        self.assertEqual(s.reg_channel(20, "log"), 222)
        s.reg_del(10, "channel_log", "111")
        self.assertEqual(s.reg_channel(20, "log"), 222)  # la guilde 20 intacte


if __name__ == "__main__":
    unittest.main()
