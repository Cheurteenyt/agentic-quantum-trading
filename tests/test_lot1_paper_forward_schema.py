"""FIX lot1 — F4 (PK paper_trades + horizon_h, migration préservant les
lignes) et F11 (funding_pct persisté).

Bug prouvé : PRIMARY KEY (signal, symbol, signal_ts) sans horizon_h +
pré-check sans horizon + INSERT OR IGNORE → les candidats bi-horizons
(24/168, 1440/2160) s'avaluaient mutuellement ; l'horizon 2160 est resté
à 0 trades depuis l'origine (88 trades 1440h, 0 2160h).

    python tests/test_lot1_paper_forward_schema.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.paper_forward import ensure_paper_schema, funding_applied_pct  # noqa: E402

OLD_SCHEMA = """CREATE TABLE paper_trades (
    signal TEXT NOT NULL, symbol TEXT NOT NULL, horizon_h INTEGER NOT NULL,
    direction INTEGER NOT NULL, signal_ts INTEGER NOT NULL,
    entry_ts INTEGER NOT NULL, entry_price REAL NOT NULL,
    exit_ts INTEGER, exit_price REAL, ret_pct REAL,
    funding_pct REAL, status TEXT NOT NULL, created_at REAL NOT NULL,
    PRIMARY KEY (signal, symbol, signal_ts))"""


def _pk_cols(con, table="paper_trades"):
    return [r[1] for r in sorted(
        (r for r in con.execute(f"PRAGMA table_info({table})") if r[5]),
        key=lambda r: r[5])]


class TestFreshSchema(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")

    def test_la_pk_fraiche_porte_horizon_h(self):
        ensure_paper_schema(self.con)
        self.assertEqual(_pk_cols(self.con),
                         ["signal", "symbol", "signal_ts", "horizon_h"])

    def test_deux_horizons_meme_signal_coexistent(self):
        ensure_paper_schema(self.con)
        base = ("INSERT OR IGNORE INTO paper_trades (signal, symbol, "
                "horizon_h, direction, signal_ts, entry_ts, entry_price, "
                "ret_pct, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)")
        for horizon in (24, 168):
            self.con.execute(base, ("sig_a", "BTCUSDT", horizon, -1,
                                    1_700_000_000_000, 1_700_000_360_000,
                                    100.0, None, "open", 0.0))
        n = self.con.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE signal='sig_a'").fetchone()[0]
        self.assertEqual(n, 2)   # AVANT le fix : 1 (le second était avalé)

    def test_le_precheck_ne_bloque_plus_le_second_horizon(self):
        """Le pattern exact du writer : pré-check puis INSERT OR IGNORE."""
        ensure_paper_schema(self.con)
        args_base = ("sig_a", "BTCUSDT", 1_700_000_000_000)
        for horizon in (1440, 2160):
            if self.con.execute(
                "SELECT 1 FROM paper_trades WHERE signal=? AND symbol=? "
                "AND signal_ts=? AND horizon_h=?",
                args_base + (horizon,)).fetchone():
                continue
            self.con.execute(
                "INSERT OR IGNORE INTO paper_trades (signal, symbol, "
                "horizon_h, direction, signal_ts, entry_ts, entry_price, "
                "status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("sig_a", "BTCUSDT", horizon, -1, 1_700_000_000_000,
                 1_700_000_360_000, 100.0, "open", 0.0))
        horizons = {r[0] for r in self.con.execute(
            "SELECT horizon_h FROM paper_trades")}
        self.assertEqual(horizons, {1440, 2160})


class TestMigrationOldPk(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute(OLD_SCHEMA)
        self.con.executescript("""
        INSERT INTO paper_trades VALUES ('s1','BTCUSDT',24,-1,111,111,100.0,
            NULL,NULL,NULL,NULL,'open',1.0);
        INSERT INTO paper_trades VALUES ('s1','BTCUSDT',168,-1,222,222,100.0,
            555,99.0,-1.5,NULL,'closed',2.0);
        INSERT INTO paper_trades VALUES ('s2','ETHUSDT',72,1,333,333,50.0,
            NULL,NULL,NULL,NULL,'open',3.0);
        """)
        self.con.commit()

    def test_les_lignes_survivent_a_la_migration(self):
        ensure_paper_schema(self.con)
        self.assertEqual(_pk_cols(self.con),
                         ["signal", "symbol", "signal_ts", "horizon_h"])
        n = self.con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        self.assertEqual(n, 3)
        row = self.con.execute(
            "SELECT ret_pct, status FROM paper_trades "
            "WHERE signal='s1' AND horizon_h=168").fetchone()
        self.assertEqual(row, (-1.5, "closed"))
        self.assertFalse(self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='paper_trades_old_pk'"
        ).fetchone())

    def test_la_migration_est_idempotente(self):
        ensure_paper_schema(self.con)
        ensure_paper_schema(self.con)   # second passage : no-op
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM paper_trades").fetchone()[0], 3)

    def test_les_colonnes_sonde_survivent_si_presentes(self):
        self.con.execute("ALTER TABLE paper_trades ADD COLUMN fund7 REAL")
        self.con.execute("UPDATE paper_trades SET fund7=0.7 "
                         "WHERE signal='s1' AND horizon_h=24")
        ensure_paper_schema(self.con)
        v = self.con.execute(
            "SELECT fund7 FROM paper_trades WHERE signal='s1' "
            "AND horizon_h=24").fetchone()[0]
        self.assertAlmostEqual(v, 0.7)
        ensure_paper_schema(self.con)   # les ALTER sonde re-passent sans erreur


class TestFundingPersiste(unittest.TestCase):
    """F11 : funding_pct = le funding appliqué au ret (payé < 0, reçu > 0).
    FIX lot2 (F3) : l'entrée est la SOMME des taux réels de la fenêtre
    (funding_paid_pct) — le signature (rate_horaire, hold) est mort avec
    la moyenne full-sample."""

    def test_un_long_paie_un_funding_positif(self):
        self.assertAlmostEqual(funding_applied_pct(1, 0.24), -0.24)

    def test_un_short_recoit_un_funding_positif(self):
        self.assertAlmostEqual(funding_applied_pct(-1, 0.24), 0.24)

    def test_un_funding_negatif_inverse_le_sens(self):
        self.assertAlmostEqual(funding_applied_pct(1, -0.24), 0.24)

    def test_le_ret_est_recomputable_depuis_les_parties_persistees(self):
        """La promesse d'auditabilité : ret = prix - coûts + funding_pct."""
        price_ret = 2.0
        cost = 0.28
        fund = funding_applied_pct(-1, 0.48)   # short, 2 taux de 0,24 %
        self.assertAlmostEqual(price_ret - cost + fund,
                               price_ret - cost + 0.48)


if __name__ == "__main__":
    unittest.main()
