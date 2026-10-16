"""REGISTRE BOARD — le scoreboard HTML + le draft, exercés de bout en bout.

P1-c de l'audit externe (16/10) : `registre_board.py` (x-nightly) écrit
board + draft à CHAQUE cycle, sans qu'aucun test ne l'exécute. Une dérive
de schéma (colonnes de x_calls / x_call_scores / x_positioning) ne se
voyait qu'en production.

L'oracle construit la base avec les schémas RÉELS (`fetch_x_posts` +
`score_x_calls` : c'est le `_connect` réel qui la crée, migrations
comprises), exerce le vrai `main()` (push Telegram neutralisé) et vérifie :
  - les 3 artefacts écrits (board, historisé, draft) ;
  - la règle parser_version = MAX : un vieux call n'est PAS rendu ;
  - le JOIN souple : un call sans score apparaît sans crash ;
  - la base vide écrit quand même (premier cycle d'un jour neuf — la
    classe de panne de #314) ;
  - le push part avec exactement le draft écrit.
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
# scripts/ en sys.path : `score_x_calls` importe `fetch_klines`, qui fait
# `import aster_rate` (import « nu » de script) — même motif que
# test_audits_scripts_derive.py.
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import scripts.fetch_x_posts as fxp  # noqa: E402
import scripts.registre_board as rb  # noqa: E402
import scripts.score_x_calls as sxc  # noqa: E402
import scripts.telegram_notify as tn  # noqa: E402


class TestRegistreBoard(unittest.TestCase):
    def _seed(self, con: sqlite3.Connection) -> None:
        for pid, handle, text in (
                ("p1", "alice", "$BTC long"),
                ("p2", "bob", "$ETH short"),
                ("p3", "carol", "$OLD long"),
                ("p4", "dave", "$SOL long")):
            con.execute(
                "INSERT INTO x_posts (post_id, author_handle, text, fetched_at)"
                " VALUES (?, ?, ?, '2026-10-15T10:00:00Z')", (pid, handle, text))
        for handle, active in (("alice", 1), ("bob", 1), ("carol", 0)):
            con.execute(
                "INSERT INTO x_accounts (handle, added_at, active)"
                " VALUES (?, '2026-10-01', ?)", (handle, active))
        # UNIQUE(post_id, parser_version) : un call par post et par version.
        calls = [
            # (post, sym, dir, entry, horizon, conf, parser, tp, sl)
            ("p1", "BTC", "long", 60000.0, "4h", "high", "v3.1-regex",
             63000.0, 58000.0),
            ("p2", "ETH", "short", 3000.0, "4h", "medium", "v3.1-regex",
             2700.0, 3200.0),
            ("p4", "SOL", "long", 150.0, "4h", "low", "v3.1-regex",
             None, None),
            ("p3", "OLDSYM", "long", 1.0, "4h", "low", "v2-ancien",
             None, None),
        ]
        for p, sym, d, e, h, conf, ver, tp, sl in calls:
            con.execute(
                "INSERT INTO x_calls (post_id, symbol, direction, entry_price,"
                " horizon, confidence, parser_version, parsed_at, tp_price,"
                " sl_price) VALUES (?,?,?,?,?,?,?,'2026-10-15T12:30:00Z',?,?)",
                (p, sym, d, e, h, conf, ver, tp, sl))
        con.execute(
            "INSERT INTO x_call_scores (call_id, posted_at, entry_resolved,"
            " ret_1h, ret_24h, ret_7d, status, scored_at, engine_version)"
            " VALUES (1, '2026-10-15T12:30:00Z', 60012.5, 0.0125, 0.05, NULL,"
            " 'resolu', '2026-10-15T13:00:00Z', 'v1')")
        con.execute(
            "INSERT INTO x_call_scores (call_id, posted_at, entry_resolved,"
            " ret_1h, ret_24h, ret_7d, status, scored_at, engine_version)"
            " VALUES (2, '2026-10-15T12:30:00Z', 2999.0, -0.01, NULL, NULL,"
            " 'resolu', '2026-10-15T13:00:00Z', 'v1')")
        con.execute(
            "INSERT INTO x_call_verdicts (call_id, verdict, resolved_ts,"
            " engine_version, scored_at) VALUES (1, 'win',"
            " '2026-10-15T13:00:00Z', 'v1', '2026-10-15T13:00:00Z')")
        con.execute(
            "INSERT INTO x_call_verdicts (call_id, verdict, resolved_ts,"
            " engine_version, scored_at) VALUES (2, 'loss',"
            " '2026-10-15T13:00:00Z', 'v1', '2026-10-15T13:00:00Z')")
        con.execute(
            "INSERT INTO x_positioning VALUES ('2026-10-15', 'BTC', 3, 66.0)")
        con.execute(
            "INSERT INTO x_positioning VALUES ('2026-10-15', 'ETH', 2, 33.0)")
        con.execute(
            "INSERT INTO x_mentions VALUES ('PEPE', '2026-10-15', 5, 1234,"
            " 50000)")

    def _run(self, td: Path, seed: bool) -> tuple[int, Path, mock.MagicMock]:
        dbp = td / "x_posts.db"
        reports = td / "reports"
        envoi = mock.MagicMock(return_value=True)
        with mock.patch.object(fxp, "DB_PATH", dbp), \
             mock.patch.object(rb, "_connect", fxp._connect), \
             mock.patch.object(rb, "REPORTS", reports), \
             mock.patch.object(rb, "BOARD", reports / "registre-board.html"), \
             mock.patch.object(tn, "send_if_configured", envoi), \
             contextlib.redirect_stdout(io.StringIO()):
            con = fxp._connect()  # construit le schéma réel…
            con.executescript(sxc.SCORES_SCHEMA)
            con.executescript(sxc.VERDICTS_SCHEMA)
            if seed:
                self._seed(con)
            con.commit()
            con.close()
            rc = rb.main()  # … puis exerce l'écriture réelle
        self.assertEqual(rc, 0)
        return rc, reports, envoi

    def test_board_draft_et_poussee(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _, reports, envoi = self._run(td, seed=True)
            board = reports / "registre-board.html"
            self.assertTrue(board.exists())
            self.assertEqual(
                len(list(reports.glob("registre-board-*.html"))), 1)
            draft_path = reports / "registre-draft-post.txt"
            self.assertTrue(draft_path.exists())
            html = board.read_text(encoding="utf-8")
            # Cartes : 4 posts, 2 comptes actifs, 3 calls v3.1 (pas le v2).
            self.assertIn("<b>4</b>posts en base", html)
            self.assertIn("<b>2</b>comptes en watchlist", html)
            self.assertIn("<b>3</b>calls trackés", html)
            # Le call BTC win est rendu au complet.
            self.assertIn("@alice", html)
            self.assertIn('<td class="long">LONG</td>', html)
            self.assertIn("<td>60 000</td>", html)
            self.assertIn("<td>63 000 / 58 000</td>", html)
            self.assertIn("+1.25 %", html)
            self.assertIn("✓ win", html)
            self.assertIn("✗ loss", html)
            # SOL : échantillon sans score → LEFT JOIN souple, pas de crash.
            self.assertIn("SOL", html)
            # Le call « v2-ancien » n'est PAS rendu (parser_version = MAX).
            self.assertNotIn("OLDSYM", html)
            self.assertNotIn("@carol", html)
            # Positionnement : classe long/short selon le consensus.
            self.assertIn('<td class="long">66 % long</td>', html)
            self.assertIn('<td class="short">33 % long</td>', html)
            # Mentions : milliers espacés à la française.
            self.assertIn("$PEPE", html)
            self.assertIn("1 234 likes", html)
            self.assertIn("50 000 vues", html)
            # Draft : les 3 calls v3.1, verdicts rejoués.
            draft = draft_path.read_text(encoding="utf-8")
            self.assertIn("3 calls $BTC / $ETH trackés depuis crypto twitter.",
                          draft)
            self.assertIn("1 win / 1 loss.", draft)
            # Le push part avec EXACTEMENT le draft écrit.
            envoi.assert_called_once_with(draft)

    def test_base_vide_regenere_sans_plant(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _, reports, envoi = self._run(td, seed=False)
            html = (reports / "registre-board.html").read_text(
                encoding="utf-8")
            self.assertIn("aucun call", html)
            draft = (reports / "registre-draft-post.txt").read_text(
                encoding="utf-8")
            self.assertIn("0 calls $BTC / $ETH trackés", draft)
            self.assertIn("Premiers verdicts en maturation", draft)
            envoi.assert_called_once()


if __name__ == "__main__":
    unittest.main()
