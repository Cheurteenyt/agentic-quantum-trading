"""LIQ-STORM — le rapport de liquidations exercé de bout en bout.

P1-c de l'audit externe (16/10) : les scripts qui écrivent des rapports
de décision tournaient sans AUCUN test qui les exécute — une dérive de
schéma (`liq_events`) ou un refactor cassé ne se voyaient qu'à 3 h du
matin, dans un `ExecStart=-` qui avale l'échec.

L'oracle exerce le VRAI `main()` sur une base fixture au schéma réel
(liq_collector.py, relevé 16/10), `REPORTS` redirigé — trois contrats :
  - < 20 événements → aucun rapport (série trop jeune, on ne prétend
    rien lire) ;
  - bouffée 4h > p90 de la série → STORM OUI + ratio long/short 24h ;
  - calme → STORM non, et le top des longs liquidés vient des SELL.
"""
from __future__ import annotations

import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import scripts.liq_storm as ls  # noqa: E402

# Schéma réel de liq_events (liq_collector.py, clé primaire composite
# incluse) — une dérive de nom/ordre de colonne doit casser CE test.
LIQ_SCHEMA = (
    "CREATE TABLE liq_events (symbol TEXT NOT NULL, side TEXT NOT NULL,"
    " qty REAL NOT NULL, price REAL NOT NULL, event_time INTEGER NOT NULL,"
    " notional REAL NOT NULL, source TEXT NOT NULL, captured_at REAL NOT NULL,"
    " PRIMARY KEY (symbol, side, event_time, price, qty))",
)

T0 = 1_790_000_000_000  # ms — septembre 2026, comme les séries du warehouse
H4 = 4 * 3_600_000


class TestLiqStorm(unittest.TestCase):
    def _db(self, td: Path, rows: list[tuple]) -> Path:
        dbp = td / "klines.db"
        con = sqlite3.connect(dbp)
        for stmt in LIQ_SCHEMA:
            con.execute(stmt)
        con.executemany("INSERT INTO liq_events VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()
        con.close()
        return dbp

    def _run(self, dbp: Path, reports: Path) -> tuple[int, str]:
        buf = io.StringIO()
        with mock.patch.object(ls, "KDB", dbp), \
             mock.patch.object(ls, "REPORTS", reports), \
             contextlib.redirect_stdout(buf):
            rc = ls.main()
        return rc, buf.getvalue()

    @staticmethod
    def _ev(sym: str, side: str, t: int, notional: float, tag: float) -> tuple:
        # `tag` décolle le prix : la PK (symbol, side, event_time, price, qty)
        # interdit deux lignes rigoureusement identiques.
        price = 50.0 + tag
        return (sym, side, notional / price, price, t, notional,
                "ws_forceOrder", 0.0)

    def test_serie_trop_jeune_aucun_rapport(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            rows = [self._ev("BTCUSDT", "SELL", T0 + k * H4, 10.0, float(k))
                    for k in range(10)]
            dbp = self._db(td, rows)
            reports = td / "reports"  # volontairement PAS créé
            rc, out = self._run(dbp, reports)
            self.assertEqual(rc, 0)
            self.assertIn("seulement 10 événements", out)
            self.assertIn("série trop jeune", out)
            self.assertEqual(list(reports.glob("liq-storm-*.md")), [])

    def test_tempete_bouffee_au_dessus_du_p90(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            # 24 bouffées de 4 h à $10 (k=0..23), puis 2 événements de $1000
            # dans les 4 h finales : p90 = 10, bouffée courante = 2010.
            rows = [self._ev("BTCUSDT", "SELL", T0 + k * H4, 10.0, float(k))
                    for k in range(24)]
            now = T0 + 24 * H4
            rows.append(self._ev("BTCUSDT", "SELL", now, 1000.0, 91.0))
            rows.append(self._ev("BTCUSDT", "SELL", now, 1000.0, 92.0))
            dbp = self._db(td, rows)
            reports = td / "reports"
            reports.mkdir()
            rc, out = self._run(dbp, reports)
            self.assertEqual(rc, 0)
            self.assertIn("storm=OUI", out)
            rapports = list(reports.glob("liq-storm-*.md"))
            self.assertEqual(len(rapports), 1)
            txt = rapports[0].read_text(encoding="utf-8")
            self.assertIn("26 événements accumulés", txt)
            self.assertIn("$2,010 (p90 série : $10)", txt)
            self.assertIn("⚠ OUI — tempête en cours", txt)
            # sell_24h = 6×10 (k=18..23) + 2×1000 ; buy = 0 → 2060.0×
            self.assertIn("2060.0×", txt)
            self.assertIn("tailwind short", txt)
            self.assertIn("| BTCUSDT | $2,060 |", txt)

    def test_calme_pas_de_tempete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            # Bouffées décroissantes $1000→$120 (p90 ≈ $916), queue calme :
            # la bouffée courante (k=21-22, $280) reste sous le p90.
            rows = [self._ev("ETHUSDT", "BUY", T0 + k * H4, 1000.0 - 40.0 * k,
                             float(k)) for k in range(23)]
            dbp = self._db(td, rows)
            reports = td / "reports"
            reports.mkdir()
            rc, out = self._run(dbp, reports)
            self.assertEqual(rc, 0)
            self.assertIn("storm=non", out)
            txt = list(reports.glob("liq-storm-*.md"))[0].read_text(
                encoding="utf-8")
            self.assertIn("| **STORM** | **non** |", txt)
            self.assertIn("0.0×", txt)
            self.assertIn("(équilibré)", txt)


if __name__ == "__main__":
    unittest.main()
