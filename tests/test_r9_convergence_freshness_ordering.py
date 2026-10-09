"""R9-D — trois défauts d'ordre/fraîcheur nocturnes validés sur le clone10 :

1. [P1] aster_convergence._oi_velocity : les 2 derniers snapshots OI étaient
   pris QUELLE QUE SOIT leur âge — un oi-collector arrêté 3 jours produisait
   un ΔOI fossile affiché comme actuel et votant dans la confluence, alors
   que crowding_composite impose OI_MAX_STALE_H = 6 h. Fix : garde 6 h sur
   le snapshot le plus récent (+ garde NULL).
2. [P1] aster_convergence._x_pressure : captured_at n'était NI sélectionné
   NI filtré — x_aster_pulse réécrit en INSERT OR REPLACE par ticker : si le
   pulse ne tourne plus, une ligne fossile votait indéfiniment. Fix : garde
   26 h (1 cycle nightly + marge).
3. [P1] ordre producteur/consommateur : trading-agent-nightly.timer (03:00)
   lançait aster_convergence AVANT x-nightly.timer (03:20) qui écrit
   x_pressure — la lentille X du rapport était structurellement à J-1. Et
   dans x-nightly.service, x_aster_pulse tournait AVANT fetch_x_posts
   --parse-calls : les calls/consensus de x_pressure et x_signal_history
   reflétaient la veille. Fix : X 02:40 → trading-agent 03:10, pulse déplacé
   après parse-calls + scoring.

Mutations négatives : retirer une garde de fraîcheur ou remettre le pulse
avant parse-calls doit remettre les tests en échec.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.aster_convergence as ac  # noqa: E402

NOW_MS = 1_800_000_000_000  # jalon fixe (les gardes utilisent time.time(),
# les tests monkeypatchent via des âges relatifs calculés à partir de now réel)


class OiVelocityFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "klines.db"
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE oi_history (symbol TEXT, open_interest REAL, "
                    "captured_at_ms INTEGER)")
        con.commit()
        con.close()
        self._old = ac.KDB
        ac.KDB = str(self.db)

    def tearDown(self):
        ac.KDB = self._old
        self.tmp.cleanup()

    def _snap(self, sym: str, oi: float, age_h: float) -> None:
        ts = int((ac.time.time() - age_h * 3600) * 1000)
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO oi_history VALUES (?,?,?)", (sym, oi, ts))
        con.commit()
        con.close()

    def test_fresh_snapshot_gives_delta(self):
        self._snap("FRESHUSDT", 100.0, 2.0)
        self._snap("FRESHUSDT", 110.0, 1.0)
        out = ac._oi_velocity()
        self.assertIn("FRESH", out)
        self.assertAlmostEqual(out["FRESH"], 10.0)

    def test_fossil_snapshot_is_rejected(self):
        self._snap("FOSSILUSDT", 100.0, 73.0)
        self._snap("FOSSILUSDT", 110.0, 72.0)
        out = ac._oi_velocity()
        self.assertNotIn("FOSSIL", out,
                         "un ΔOI vieux de 3 jours ne doit pas voter")

    def test_null_timestamp_is_rejected_without_crash(self):
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO oi_history VALUES (?,?,?)", ("NULLTSUSDT", 100.0, None))
        con.execute("INSERT INTO oi_history VALUES (?,?,?)", ("NULLTSUSDT", 110.0, None))
        con.commit()
        con.close()
        out = ac._oi_velocity()  # TypeError avant le garde pts[0][1]
        self.assertNotIn("NULLTS", out)

    def test_only_one_snapshot_is_rejected(self):
        self._snap("LONEUSDT", 100.0, 1.0)
        self.assertNotIn("LONE", ac._oi_velocity())


class XPressureFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "x_posts.db"
        con = sqlite3.connect(self.db)
        con.execute("""CREATE TABLE x_pressure (
            ticker TEXT PRIMARY KEY, posts INTEGER, posts_prev INTEGER,
            velocity REAL, longs INTEGER, shorts INTEGER, engagement REAL,
            funding_pct REAL, captured_at REAL NOT NULL)""")
        con.commit()
        con.close()
        self._old = ac.XDB
        ac.XDB = str(self.db)

    def tearDown(self):
        ac.XDB = self._old
        self.tmp.cleanup()

    def _row(self, ticker: str, age_s: float | None) -> None:
        cap = None if age_s is None else ac.time.time() - age_s
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO x_pressure VALUES (?,?,?,?,?,?,?,?,?)",
                    (ticker, 5, 3, 1.7, 2, 1, 10.0, 0.05, cap))
        con.commit()
        con.close()

    def test_fresh_row_is_kept(self):
        self._row("FRESH", 3600.0)
        self.assertIn("FRESH", ac._x_pressure())

    def test_fossil_row_is_rejected(self):
        self._row("FOSSIL", 72 * 3600.0)
        self.assertNotIn("FOSSIL", ac._x_pressure(),
                         "une ligne fossile ne doit pas voter indéfiniment")

    def test_null_captured_at_is_rejected_without_crash(self):
        # schéma RELÂCHÉ volontaire : la DDL réelle impose NOT NULL, mais le
        # garde défensif doit survivre à un schéma futur sans contrainte
        con = sqlite3.connect(self.db)
        con.execute("DROP TABLE x_pressure")
        con.execute("""CREATE TABLE x_pressure (
            ticker TEXT PRIMARY KEY, posts INTEGER, posts_prev INTEGER,
            velocity REAL, longs INTEGER, shorts INTEGER, engagement REAL,
            funding_pct REAL, captured_at REAL)""")
        con.execute("INSERT INTO x_pressure VALUES (?,?,?,?,?,?,?,?,?)",
                    ("NULLTS", 5, 3, 1.7, 2, 1, 10.0, 0.05, None))
        con.commit()
        con.close()
        out = ac._x_pressure()  # float(None) sans garde
        self.assertNotIn("NULLTS", out)


class NightlyOrderingTests(unittest.TestCase):
    """P1 : le producteur (x_aster_pulse) doit précéder le consommateur."""

    @staticmethod
    def _calendar_hours(path: Path) -> float:
        txt = path.read_text(encoding="utf-8")
        m = re.search(r"OnCalendar=\*-\*-\*\s+(\d{1,2}):(\d{2})", txt)
        assert m, f"OnCalendar introuvable dans {path.name}"
        return int(m.group(1)) + int(m.group(2)) / 60.0

    def test_producer_timer_before_consumer_timer(self):
        x = self._calendar_hours(ROOT / "configs/systemd-user/x-nightly.timer")
        ta = self._calendar_hours(
            ROOT / "configs/systemd-user/trading-agent-nightly.timer")
        fomo = self._calendar_hours(ROOT / "configs/systemd-user/fomo-nightly.timer")
        self.assertLess(x, ta, "x_aster_pulse (producteur) doit tourner avant "
                               "aster_convergence (consommateur)")
        self.assertLess(ta, fomo, "le nocturne aster doit rester avant fomo "
                                  "(wave_detector lit le harvest X frais)")

    def test_pulse_runs_after_parse_calls_in_x_nightly(self):
        svc = (ROOT / "configs/systemd-user/x-nightly.service").read_text(encoding="utf-8")
        idx_pulse = svc.index("scripts/x_aster_pulse.py")
        idx_parse = svc.index("--parse-calls")
        self.assertGreater(idx_pulse, idx_parse,
                           "x_aster_pulse doit suivre --parse-calls "
                           "(sinon calls/consensus à J-1)")


if __name__ == "__main__":
    unittest.main()
