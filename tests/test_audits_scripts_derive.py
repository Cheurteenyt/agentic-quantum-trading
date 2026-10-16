"""LA DÉRIVE DES SCRIPTS D'AUDIT — ce que RIEN ne re-détectait.

Le balayage de vérification du 16/10 a trouvé deux scripts d'audit cassés
en silence : aucun test ne les exerce, aucun gate CI ne les couvre.

  - `flow_audit.py` interrogeait `oi_history.captured_at` alors que le
    collecteur OI reconstruit (27/09) écrit `captured_at_ms` (en ms) :
    crash `sqlite3.OperationalError: no such column: captured_at`.

  - `meme_universe_audit.py` — le mode documenté « resume depuis side-DB »
    (sans `--fetch`) ouvrait sa side-DB du jour par simple `sqlite3.connect` :
    sur un jour neuf, le fichier est créé VIDE (0 octet) et la requête
    `klines` plante. Le garde refuse désormais explicitement, au lieu de
    planter — et sans jamais écrire de rapport trompeur.

Tests oracle :
  - le schéma de la fixture flow est le schéma RÉEL du warehouse
    (PRAGMA table_info sur data/warehouse/klines.db, relevé 16/10) ;
  - la reprise meme exerce le vrai `main()` — réseau neutralisé
    (`aster_universe_live`), fetch/données stubbés à la frontière.
"""
from __future__ import annotations

import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# scripts/ en sys.path : certains modules font des imports « nus » quand ils
# sont lancés en script (ex. `import aster_rate` dans fetch_klines.py) — motif
# déjà utilisé par d'autres tests (test_aster_depth_engine.py, & co).
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import scripts.flow_audit as fa  # noqa: E402
import scripts.meme_universe_audit as mua  # noqa: E402

# Schéma réel de klines.db (16/10) — une dérive de nom de colonne doit
# casser ce test, pas la production à 3 h du matin.
FLOW_SCHEMA = (
    "CREATE TABLE flow_events (symbol TEXT, interval TEXT, kind TEXT,"
    " bar_time INTEGER, close REAL, delta REAL, baseline REAL,"
    " depth_atr REAL, params TEXT, captured_at INTEGER)",
    "CREATE TABLE flow_snapshots (symbol TEXT, ts INTEGER, oi REAL,"
    " taker_delta_30m REAL, captured_at INTEGER)",
    "CREATE TABLE signal_events (signal TEXT, symbol TEXT, ts_ms INTEGER,"
    " direction TEXT, sversion TEXT)",
    "CREATE TABLE lifecycle_map (cell TEXT, age_bucket TEXT, dd_bucket TEXT,"
    " n INTEGER, wr_long REAL, wr_short REAL, med_long REAL, med_short REAL,"
    " captured_at INTEGER)",
    "CREATE TABLE basis_snapshots (symbol TEXT, aster_price REAL,"
    " binance_price REAL, basis_pct REAL, captured_at INTEGER)",
    "CREATE TABLE oi_history (symbol TEXT, open_interest REAL, price REAL,"
    " captured_at_ms INTEGER)",
)

# 1_790_000_000_000 ms = septembre 2026 (unité ms, pas secondes : une
# relecture naïve en s donnerait l'an 58600 — l'assertion le verrait).
CAPTURED_MS = 1_790_000_000_000


class TestFlowAuditOiHistoryMs(unittest.TestCase):
    def test_flow_audit_lit_oi_history_en_ms(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dbp = Path(td) / "klines.db"
            con = sqlite3.connect(dbp)
            for stmt in FLOW_SCHEMA:
                con.execute(stmt)
            con.execute(
                "INSERT INTO oi_history VALUES ('TESTUSDT', 1000.0, 1.0, ?)",
                (CAPTURED_MS,),
            )
            con.commit()
            con.close()

            attendu = datetime.fromtimestamp(
                CAPTURED_MS / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")

            buf = io.StringIO()
            with mock.patch.object(fa, "DB", dbp), \
                 mock.patch.object(sys, "argv", ["flow_audit.py"]), \
                 contextlib.redirect_stdout(buf):
                rc = fa.main()

            self.assertEqual(rc, 0)
            sortie = buf.getvalue()
            self.assertIn("oi_history", sortie)
            self.assertIn(attendu, sortie)


class TestMemeUniverseSideDb(unittest.TestCase):
    EVENT = {
        "sym": "TESTMEMEUSDT",
        "ts_ms": 1_790_000_000_000_000_000,  # nanosecondes (idx_ns)
        "price_ret_short": 1.0,
        "fee_rt_bps": 4.0,
        "mae_adverse": 5.0,
    }

    def _kdb(self, td: Path) -> Path:
        dbp = td / "k.db"
        con = sqlite3.connect(dbp)
        con.execute("CREATE TABLE klines (symbol TEXT, interval TEXT)")
        con.execute("INSERT INTO klines VALUES ('TESTMEMEUSDT', '1h')")
        con.commit()
        con.close()
        return dbp

    def _run(self, td: Path, side: Path) -> tuple[int, str]:
        buf = io.StringIO()
        with mock.patch.object(mua, "KDB", self._kdb(td)), \
             mock.patch.object(mua, "SIDE_DB", side), \
             mock.patch.object(mua, "REPORTS", td / "reports"), \
             mock.patch.object(
                 mua, "aster_universe_live", lambda: {"TESTMEMEUSDT"}), \
             mock.patch.object(
                 mua, "collect_meme", lambda con: [dict(self.EVENT)]), \
             mock.patch.object(
                 mua, "coverage_days", lambda con, sym: (120.0, 600)), \
             contextlib.redirect_stdout(buf):
            rc = mua.main([])
        return rc, buf.getvalue()

    def test_side_db_absente_refuse_sans_rapport(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            rc, sortie = self._run(td, td / "side.db")
            self.assertEqual(rc, 2)
            self.assertIn("side-DB absente", sortie)
            self.assertIn("--fetch", sortie)
            # aucun rapport trompeur : la reprise n'a rien testé
            self.assertFalse((td / "reports").exists())

    def test_side_db_vide_refuse_explicitement(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            side = td / "side.db"
            sqlite3.connect(side).close()  # le fichier 0-octet vécu
            rc, sortie = self._run(td, side)
            self.assertEqual(rc, 2)
            self.assertIn("sans table klines", sortie)

    def test_side_db_avec_klines_reprise_normale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            side = td / "side.db"
            con = sqlite3.connect(side)
            con.execute("CREATE TABLE klines (symbol TEXT, interval TEXT)")
            con.execute("INSERT INTO klines VALUES ('TESTMEMEUSDT', '1h')")
            con.commit()
            con.close()
            rc, sortie = self._run(td, side)
            self.assertEqual(rc, 0)
            self.assertIn("AJOUTABLE", sortie)
            self.assertIn("verdict", sortie)
            rapports = list(
                (td / "reports").glob("meme-universe-audit-*.md"))
            self.assertEqual(len(rapports), 1)


if __name__ == "__main__":
    unittest.main()
