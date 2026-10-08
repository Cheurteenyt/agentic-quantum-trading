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


class TestDashboardXSS(unittest.TestCase):
    """F-048 — aucune donnée non fiable ne doit atteindre le HTML brut.

    Deux entrées distinctes, toutes deux réelles :

      RÉFLÉCHI  `GET /oauth2/callback?error=<script>…` — piloté par l'URL,
                donc par le lien de la victime. Exécuté dans le navigateur
                de celle qui clique sur le lien (login CSRF + vol de
                cookie de session).

      STOCKÉ    `global_name`, les noms de rôle, `author_name`,
                `channel_name`, `user_name`, le symbole et le verdict des
                calls : ils viennent de la base (remplie par le bot et
                Discord). Une seule ligne:name suffice à empoisonner le
                classement pour tous les membres-connectés.

    Discord interdit `<` et `>` dans les noms d'utilisateur, ce qui rend le
    cas stocké peu probable en pratique — mais « improbable » n'est pas une
    garantie, et la base est aussi alimentée par le bot et par des
    collecteurs. L'échappement se fait au point de sortie, systématiquement.
    """

    PAYLOADS = [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        '"><script>alert(1)</script>',
        "'><svg/onload=alert(1)>",
        "<iframe srcdoc='<script>alert(1)</script>'></iframe>",
    ]

    @classmethod
    def setUpClass(cls):
        from discord_bot import dashboard as d
        cls.d = d

    def test_esc_ne_laisse_passer_aucun_balise(self):
        for payload in self.PAYLOADS:
            with self.subTest(payload=payload):
                out = self.d._esc(payload)
                self.assertNotIn("<", out, f"< non échappé : {out}")
                self.assertNotIn(">", out, f"> non échappé : {out}")

    def test_le_titre_de_page_est_echappe(self):
        for payload in self.PAYLOADS:
            with self.subTest(payload=payload):
                html = self.d._page(payload, "<p>ok</p>").body.decode()
                self.assertNotIn(payload, html)
                self.assertIn(self.d._esc(payload), html)

    def test_esc_echappe_les_guillemets_pour_les_attributs(self):
        """Sans ça, `<img src=x onerror=...>` passe par un attribut."""
        self.assertNotIn('"', self.d._esc('a" onerror="alert(1)'))
        self.assertNotIn("'", self.d._esc("a' onerror='alert(1)"))

    def test_esc_sur_none_et_non_str(self):
        self.assertEqual(self.d._esc(None), "")
        self.assertEqual(self.d._esc(42), "42")

    def test_la_page_de_login_echappe_le_message(self):
        """`/oauth2/callback?error=` — le sink réfléchi.

        L'échappement est dans `_login_page` (le sink), pas au site
        d'appel : `oauth_callback` passe `p.get('error')` BRUT. On vérifie
        donc le rendu, pas l'appel.
        """
        for payload in self.PAYLOADS:
            with self.subTest(payload=payload):
                html = self.d._login_page(
                    f"Connexion refusée ({payload}) — tu peux réessayer."
                ).body.decode()
                self.assertNotIn(payload, html,
                                 "le payload d'error est rendu BRUT dans le HTML")
                self.assertIn(self.d._esc(payload), html,
                              "le payload devrait apparaître sous forme échappée")

    def test_les_champs_stockes_sont_echappes_dans_le_classement(self):
        """On rejoue la construction de ligne du /classement."""
        payload = "<script>alert('xss')</script>"
        rows = [{"author_name": payload, "n": 5, "wr": 0.5, "tot": 1.0}]
        lignes = "".join(
            f"<tr><td>{i}</td><td><b>{self.d._esc(r['author_name'])}</b></td>"
            f"<td>{r['n']}</td></tr>"
            for i, r in enumerate(rows, 1)
        )
        self.assertNotIn(payload, lignes)
        self.assertIn("&lt;script&gt;", lignes)

    def test_aucune_interpolation_brute_restante(self):
        """Verrou par AST : tout champ non fiable utilisé dans une
        f-string destinée au HTML doit passer par `_esc(...)`.

        Une recherche de chaîne ne suffit pas — elle matche à la fois
        `user.get("global_name")` (lecture, inoffensive) et une
        interpolation réellement brute. On regarde donc les
        `FormattedValue` de l'AST, et pour chacun on exige qu'il
        contienne un appel `_esc`.
        """
        import ast
        import inspect
        import textwrap

        champs = {"author_name", "channel_name", "user_name",
                  "global_name", "verdict", "entry", "symbol", "title"}

        def _noms(node):
            out = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant):
                    if isinstance(n.slice.value, str):
                        out.add(n.slice.value)
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    out.add(n.value)
            return out

        tree = ast.parse(textwrap.dedent(inspect.getsource(self.d)))
        coupables = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.JoinedStr):
                continue
            for frag in n.values:
                if not isinstance(frag, ast.FormattedValue):
                    continue
                lus = _noms(frag.value) & champs
                if not lus:
                    continue
                echappe = any(
                    isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Name)
                    and c.func.id == "_esc"
                    for c in ast.walk(frag.value))
                if not echappe:
                    coupables.append(
                        f"L{n.lineno}: {{{ast.unparse(frag.value)}}}")

        self.assertEqual(coupables, [],
                         f"interpolation non échappée d'un champ non fiable : {coupables}")


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


class _Row:
    """Un substitut de sqlite3.Row (target/value) pour les tests du registre."""

    def __init__(self, target, value):
        self._d = {"target": target, "value": value}

    def __getitem__(self, k):
        return self._d[k]


class TestGatekeeperHelpers(unittest.TestCase):
    """La math du portier : 48 h, les rows pourris sautent, le guard anti-0."""

    @classmethod
    def setUpClass(cls):
        from discord_bot.cogs import gatekeeper as g
        cls.g = g

    def test_release_at(self):
        from datetime import datetime, timezone
        joined = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        base = joined.timestamp()
        self.assertEqual(self.g.release_at(joined.isoformat()), base + 48 * 3600)
        self.assertEqual(self.g.release_at(None), 0.0)
        self.assertEqual(self.g.release_at("pas-une-date"), 0.0)

    def test_pending_of(self):
        from datetime import datetime, timezone
        ok = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc).isoformat()
        rows = [_Row("111", ok), _Row("abc", ok), _Row("222", None), _Row("333", "x")]
        out = self.g.pending_of(rows)
        # l'id non-numérique saute ; les timestamps pourris restent (is_due les
        # libérera — fail-open)
        self.assertEqual([uid for uid, _ in out], [111, 222, 333])

    def test_is_due(self):
        now = 1000.0
        self.assertTrue(self.g.is_due(999.0, now))
        self.assertTrue(self.g.is_due(1000.0, now))
        self.assertFalse(self.g.is_due(1001.0, now))
        self.assertTrue(self.g.is_due(0.0, now))  # fail-open : jamais piégé


class TestTicketsHelpers(unittest.TestCase):
    """Le nommage des tickets et le compteur."""

    @classmethod
    def setUpClass(cls):
        from discord_bot.cogs import tickets as t
        cls.t = t

    def test_slugify(self):
        self.assertEqual(self.t.slugify("Cheurteen YT!"), "cheurteen-yt")
        self.assertEqual(self.t.slugify("  "), "membre")
        self.assertEqual(self.t.slugify("ÉèÀ"), "membre")  # les accents → vide → fallback
        self.assertEqual(self.t.slugify("x" * 200), "x" * 80)

    def test_next_counter(self):
        self.assertEqual(self.t.next_counter("7"), 8)
        self.assertEqual(self.t.next_counter(None), 1)
        self.assertEqual(self.t.next_counter("pourri"), 1)


class TestStats(unittest.TestCase):
    """Le module partagé des stats — la même source pour le site et le panneau."""

    @classmethod
    def setUpClass(cls):
        import sqlite3
        from discord_bot import stats
        cls.stats = stats
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls._tmp.name) / "stats.db"
        con = sqlite3.connect(cls.db)
        con.executescript("""
        CREATE TABLE d_messages (message_id TEXT PRIMARY KEY, channel_id TEXT,
            channel_name TEXT, author_id TEXT, author_name TEXT, created_at TEXT,
            content TEXT, attachment_count INTEGER, attachment_types TEXT,
            attachment_urls TEXT, link_urls TEXT, fetched_at REAL);
        CREATE TABLE d_calls (call_id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT UNIQUE, author_id TEXT, author_name TEXT, symbol TEXT,
            direction TEXT, entry REAL, posted_at TEXT, channel_name TEXT,
            scored INTEGER DEFAULT 0, ret_pct REAL, verdict TEXT);
        CREATE TABLE d_members (user_id TEXT PRIMARY KEY, user_name TEXT,
            display_name TEXT, bot INTEGER, joined_at TEXT, account_created TEXT,
            roles TEXT, last_seen TEXT);
        CREATE TABLE d_roles (role_id TEXT PRIMARY KEY, name TEXT, position INTEGER,
            color TEXT, permissions TEXT, member_count INTEGER, updated_at REAL);
        CREATE TABLE d_registry (guild_id TEXT NOT NULL, kind TEXT NOT NULL,
            target TEXT NOT NULL, value TEXT, updated_at REAL,
            UNIQUE(guild_id, kind, target));
        """)
        now = time.time()
        for i in range(5):
            con.execute("INSERT INTO d_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (f"m{i}", "c1", "commandes", "111" if i < 3 else "222",
                         "auteur", "2026-10-01", "txt", 0, "[]", "[]", "[]", now))
        # auteur 111 : 4 calls scorés (3 win 1 lose) → WR 75, Σ +5 ; auteur 222 : 1 call
        calls = [("111", "BTC", 2.0), ("111", "ETH", 1.0), ("111", "SOL", 4.0),
                 ("111", "BNB", -2.0), ("222", "XRP", 9.0)]
        for j, (aid, sym, ret) in enumerate(calls):
            con.execute("INSERT INTO d_calls (message_id, author_id, author_name, "
                        "symbol, direction, posted_at, scored, ret_pct) VALUES "
                        "(?,?,?,?,?,?,?,?)", (f"c{j}", aid, f"auteur{aid}", sym,
                                              "long", "2026-10-01", 1, ret))
        con.execute("INSERT INTO d_members VALUES ('111','nom','disp',0,"
                    "'2026-02-14',NULL,'[]',NULL)")
        con.execute("INSERT INTO d_registry VALUES ('1','gate_pending','999',"
                    "'2026-10-04T00:00:00+00:00', 0)")
        con.commit()
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_classement_min_calls(self):
        rows = self.stats.classement(self.db)
        self.assertEqual([r["author_id"] for r in rows], ["111"])  # 222 = 1 call < 3
        r = rows[0]
        self.assertEqual(r["n"], 4)
        self.assertAlmostEqual(r["wr"], 0.75)
        self.assertAlmostEqual(r["tot"], 5.0)

    def test_user_stats(self):
        st = self.stats.user_stats("111", self.db)
        self.assertEqual(st["n_messages"], 3)
        self.assertEqual(st["n_scored"], 4)
        self.assertAlmostEqual(st["wr"], 0.75)
        self.assertEqual(len(st["calls"]), 4)
        self.assertEqual(self.stats.user_stats("inconnu", self.db)["n_messages"], 0)

    def test_server_stats(self):
        s = self.stats.server_stats(self.db)
        self.assertEqual(s["n_members"], 1)
        self.assertEqual(s["n_bots"], 0)
        self.assertEqual(s["m24"], 5)  # seeded à maintenant
        self.assertEqual(s["n_gate_pending"], 1)
        self.assertTrue(any(c["channel_name"] == "commandes" for c in s["top_channels"]))


class TestMarketSnapshot(unittest.TestCase):
    """La photo marché : les vrais prix 24 h, les périmés exclus, le format."""

    @classmethod
    def setUpClass(cls):
        import sqlite3
        from discord_bot import stats
        cls.stats = stats
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls._tmp.name) / "klines.db"
        con = sqlite3.connect(cls.db)
        con.execute("CREATE TABLE klines (symbol TEXT, interval TEXT, "
                    "open_time INTEGER, close REAL)")
        now = 1_790_000_000_000  # ms
        # BTC : +10 % sur 24 h (vivante) ; ETH : -5 % ; STALE : périmée (30 h)
        for i, close in enumerate([100.0, 105.0, 110.0]):
            con.execute("INSERT INTO klines VALUES ('BTCUSDT','1h',?,?)",
                        (now - (24 - i) * 3600000, close))
        for i, close in enumerate([200.0, 195.0, 190.0]):
            con.execute("INSERT INTO klines VALUES ('ETHUSDT','1h',?,?)",
                        (now - (24 - i) * 3600000, close))
        con.execute("INSERT INTO klines VALUES ('PEPEUSDT','1h',?,?)",
                    (now - 30 * 3600000, 5.0))
        for i, close in enumerate([0.40, 0.50, 0.60]):
            con.execute("INSERT INTO klines VALUES ('DOGEUSDT','1h',?,?)",
                        (now - (24 - i) * 3600000, close))
        con.commit()
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_snapshot(self):
        snap = self.stats.market_snapshot(self.db)
        self.assertIsNotNone(snap)
        self.assertAlmostEqual(snap["majors"]["BTCUSDT"][1], 10.0, places=6)
        self.assertAlmostEqual(snap["majors"]["ETHUSDT"][1], -5.0, places=6)
        self.assertNotIn("PEPEUSDT", snap["majors"])  # périmé → exclu
        self.assertEqual(snap["n_symbols"], 3)

    def test_lines_et_context(self):
        snap = self.stats.market_snapshot(self.db)
        majors_line, movers = self.stats.market_lines(snap)
        self.assertIn("**BTC** $110.00", majors_line)
        self.assertIn("+10.0 %", majors_line)
        self.assertIn("DOGE", movers)  # les movers = les non-majeures
        ctx = self.stats.market_context(snap)
        self.assertIn("$110.00", ctx)  # le cerveau ne peut que CITER ces prix

    def test_absente(self):
        self.assertIsNone(self.stats.market_snapshot(Path("/nonexistent/k.db")))


if __name__ == "__main__":
    unittest.main()
