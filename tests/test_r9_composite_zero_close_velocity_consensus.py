"""R9-C — trois défauts de composites validés sur le clone10 (main @8e73f90) :

1. crowding_composite.compute_symbol : la garde `close_i <= 0` ne protège QUE
   la bougie courante — la base du rendement 24 h (bars[i-24][1]) n'est jamais
   vérifiée : close 0.0 => ZeroDivisionError, close NULL => TypeError, sur
   --full (le tir pré-enregistré du 2026-10-30). Close NULL crashe AUSSI la
   bougie elle-même à la garde (None <= 0).
2. wave_detector.x_velocity : hier = 0 mention => ratio FABRIQUÉ à 2.0 (même
   pour 1 seul post) => 20 pts de vélocité => flag écrit en base avec un
   artefact de collecte (trou du harvest) plutôt qu'un embrasement mesuré.
3. x_aster_pulse : consensus "0.0" par défaut quand aucun call — indistinguable
   en base d'un consensus neutre réel (calls longs == shorts) sur la table
   x_signal_history, matière première du futur backtest des indicateurs X.

Chaque correctif est verrouillé par ses assertions ; la mutation négative
(restaurer le code d'origine) doit remettre chaque test en échec.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.crowding_composite as cc  # noqa: E402
import scripts.wave_detector as wd  # noqa: E402
import scripts.x_aster_pulse as xap  # noqa: E402

H = 3600_000
T0 = 1_600_000_000_000 - (1_600_000_000_000 % H)  # jalon horaire fixe


def _mk_crowding_con(fault_idx: int = 500, fault_close=100.0) -> sqlite3.Connection:
    """DB in-memory : 744 bougies 1h (31 j), tables satellites vides.

    Le close fautif est place a fault_idx (>= ~480) : la composante volume
    n'est calculee que quand ref_keys >= VOL_MIN_DAYS (=20 jours de reference),
    donc un defaut situe dans les ~20 premiers jours ne serait JAMAIS evalue
    (ni sans fix, ni avec) — le test serait vert pour la mauvaise raison.
    """
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
                             close REAL, quote_volume REAL);
        CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
        CREATE TABLE premium_history (symbol TEXT, captured_at_ms INTEGER, premium_pct REAL);
        CREATE TABLE oi_history (symbol TEXT, captured_at_ms INTEGER,
                                 open_interest REAL, price REAL);
        CREATE TABLE oi_history_bulk (symbol TEXT, captured_at_ms INTEGER,
                                      open_interest REAL, price REAL);
        CREATE TABLE liq_events (symbol TEXT, event_time INTEGER, side TEXT, notional REAL);
    """)
    rows = []
    for i in range(744):
        c = fault_close if i == fault_idx else 100.0
        rows.append(("TESTUSDT", "1h", T0 + i * H, c, 1000.0))
    con.executemany("INSERT INTO klines VALUES (?,?,?,?,?)", rows)
    return con


class CrowdingZeroCloseTests(unittest.TestCase):
    """P0 : --full ne doit pas crasher sur une close 0.0/NULL du collecteur."""

    def test_zero_close_24h_ago_is_skipped(self):
        # close 0.0 a la bougie 500 : l'iteration i=524 (base = bougie 500)
        # levait ZeroDivisionError avant fix (ref_keys >= 20 atteint)
        con = _mk_crowding_con(fault_idx=500, fault_close=0.0)
        try:
            out = cc.compute_symbol(con, "TESTUSDT")
        finally:
            con.close()
        self.assertEqual(len(out), 719)  # bougie close<=0 sautee

    def test_null_close_of_the_candle_itself_is_skipped(self):
        # close NULL : la bougie elle-même crashait a la garde (None <= 0)
        con = _mk_crowding_con(fault_idx=500, fault_close=None)
        try:
            out = cc.compute_symbol(con, "TESTUSDT")  # TypeError avant fix
        finally:
            con.close()
        self.assertEqual(len(out), 719)

    def test_null_close_only_as_24h_base_is_skipped(self):
        # NULL a la bougie 501 : la bougie est sautee par la garde (fix 361)
        # et l'iteration i=525 (base = bougie 501) crashait en TypeError (fix 372)
        con = _mk_crowding_con(fault_idx=501, fault_close=None)
        try:
            out = cc.compute_symbol(con, "TESTUSDT")
        finally:
            con.close()
        self.assertEqual(len(out), 719)

    def test_sane_universe_still_yields_volume_component(self):
        # oracle anti-regression : sur un historique sain, la composante
        # volume reste calculee (le garde n'a pas tout neutralise)
        con = _mk_crowding_con()
        try:
            out = cc.compute_symbol(con, "TESTUSDT")
        finally:
            con.close()
        self.assertEqual(len(out), 720)
        with_vol = [r for r in out if "volume" in r["components"]]
        self.assertTrue(with_vol, "la composante volume doit rester calculee")


class WaveVelocityTests(unittest.TestCase):
    """P1 : hier = 0 mention n'est PAS un embrasement mesurable (ratio fabriqué)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "x_posts.db"
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE x_mentions (symbol TEXT, day TEXT, n INTEGER)")
        con.commit()
        con.close()
        self._old = wd.X_DB
        wd.X_DB = str(self.db)

    def tearDown(self):
        wd.X_DB = self._old
        self.tmp.cleanup()

    def _add(self, sym: str, day: str, n: int) -> None:
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO x_mentions VALUES (?,?,?)", (sym, day, n))
        con.commit()
        con.close()

    def test_no_yesterday_mentions_gives_ratio_none(self):
        self._add("AAA", "2026-10-09", 0)
        self._add("AAA", "2026-10-10", 1)
        n, ratio = wd.x_velocity("AAA", "2026-10-10")
        self.assertEqual(n, 1)
        self.assertIsNone(ratio, "1 post avec hier=0 : aucun ratio mesurable")

    def test_real_x2_velocity_still_measured(self):
        self._add("BBB", "2026-10-09", 1)
        self._add("BBB", "2026-10-10", 2)
        self.assertEqual(wd.x_velocity("BBB", "2026-10-10"), (2, 2.0))

    def test_zero_mentions_today_keeps_real_zero_ratio(self):
        # 0 mention aujourd'hui avec base hier=3 : ratio RÉEL 0.0 (chute),
        # PAS un ratio fabriqué — vel_pts le nota 0 de toute façon
        self._add("CCC", "2026-10-09", 3)
        self.assertEqual(wd.x_velocity("CCC", "2026-10-10"), (0, 0.0))

    def test_first_ever_appearance_gives_none(self):
        # première apparition absolue (aucune ligne hier ni avant)
        self._add("DDD", "2026-10-10", 1)
        self.assertEqual(wd.x_velocity("DDD", "2026-10-10"), (1, None))


class XSignalConsensusTests(unittest.TestCase):
    """P2 : consensus NULL (aucun call) doit se distinguer d'un neutre réel 0.0."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "x_posts.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
            CREATE TABLE x_posts (post_id TEXT PRIMARY KEY, fetched_at TEXT,
                                  text TEXT, metrics TEXT, author_handle TEXT);
            CREATE TABLE x_calls (post_id TEXT, symbol TEXT, direction TEXT);
        """)
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        yday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        posts = []
        # BTC : 2 posts aujourd'hui + 1 hier, AUCUN call (dans MAJEURS)
        for k in range(2):
            posts.append((f"x{k}", f"{today}T12:0{k}:00Z", "watch $BTC", "{}", "a"))
        posts.append(("x9", f"{yday}T12:00:00Z", "watch $BTC", "{}", "a"))
        # ETH : 1 post auj + 1 hier, 1 long + 1 short => consensus neutre RÉEL
        posts.append(("y0", f"{today}T12:00:00Z", "watch $ETH", "{}", "b"))
        posts.append(("y9", f"{yday}T12:00:00Z", "watch $ETH", "{}", "b"))
        # SOL : 1 post auj, 3 longs + 1 short => +0.5
        posts.append(("z0", f"{today}T12:00:00Z", "watch $SOL", "{}", "c"))
        con.executemany("INSERT INTO x_posts VALUES (?,?,?,?,?)", posts)
        calls = [
            ("y0", "ETH", "long"), ("y0", "ETH", "short"),   # consensus neutre RÉEL
            ("z0", "SOL", "long"), ("z0", "SOL", "long"), ("z0", "SOL", "long"),
            ("z0", "SOL", "short"),                           # 3 long / 1 short
        ]
        con.executemany("INSERT INTO x_calls VALUES (?,?,?)", calls)
        con.commit()
        con.close()
        self._olds = (xap.XDB, xap.REPORTS)
        xap.XDB = self.db
        xap.REPORTS = Path(self.tmp.name)
        import scripts.memecoin_pulse as mp
        self._mp_old = mp.funding_row
        mp.funding_row = lambda sym: (0.0, None)  # stub sans réseau

    def tearDown(self):
        xap.XDB, xap.REPORTS = self._olds
        import scripts.memecoin_pulse as mp
        mp.funding_row = self._mp_old
        self.tmp.cleanup()

    def test_consensus_none_vs_real_zero(self):
        self.assertEqual(xap.main(), 0)
        con = sqlite3.connect(self.db)
        try:
            rows = {t: c for t, c in
                    con.execute("SELECT ticker, consensus FROM x_signal_history")}
        finally:
            con.close()
        self.assertIsNone(rows["BTC"], "aucun call => consensus NULL, pas 0.0")
        self.assertEqual(rows["ETH"], 0.0, "1 long / 1 short => neutre RÉEL 0.0")
        self.assertEqual(rows["SOL"], 0.5, "3 long / 1 short => +0.5")
        # l'unité 0.0 réel doit rester distincte de NULL même après round()
        self.assertIsNot(rows["ETH"], None)


if __name__ == "__main__":
    unittest.main()
