"""Tests du registre X — parsing des calls, dates X, verdicts TP/SL.

Les regressions ici sont celles qui corrompraient le registre en silence :
prix mal parses (separateurs FR), faux positifs de tickers nus, dates
venues du futur, verdicts devines au lieu de mesures.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import fetch_x_posts as fxp
from scripts import score_x_calls as sxc
from backend.services.backtest_v2.baselines import Bar


def _bar(ts_ms: int, high: float, low: float, close: float | None = None) -> Bar:
    return Bar(ts=ts_ms, open=close or high, high=high, low=low,
               close=close if close is not None else high, volume=0.0)


class RegistreDbTest(unittest.TestCase):
    """Base isolee par test : on remplace DB_PATH avant _connect()."""

    def setUp(self) -> None:
        self._old_path = fxp.DB_PATH
        fxp.DB_PATH = Path(tempfile.mkdtemp()) / "x_posts_test.db"
        self.con = fxp._connect()

    def tearDown(self) -> None:
        self.con.close()
        fxp.DB_PATH = self._old_path

    def _add_post(self, post_id: str, text: str) -> None:
        self.con.execute(
            """
            INSERT INTO x_posts (post_id, author_handle, text, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            (post_id, "tester", text, "2026-09-21T17:00:00Z"),
        )
        self.con.commit()

    def _calls(self) -> list[tuple]:
        return self.con.execute(
            "SELECT symbol, direction, entry_price, tp_price, sl_price, confidence "
            "FROM x_calls"
        ).fetchall()


class TestParseCalls(RegistreDbTest):
    def test_cashtag_et_direction_sans_prix(self) -> None:
        self._add_post("p1", "Today $BTC flipped my bullish level, sizing in")
        fxp._parse_calls(self.con)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0][0], calls[0][1]), ("BTC", "long"))
        self.assertIsNone(calls[0][2])

    def test_aucun_cashtag_aucun_call_regression_egld(self) -> None:
        self._add_post(
            "p2", "Kalshi surévalué... on n'a jamais vu ça depuis l'EGLD à 500$ "
                  "Le short post-IPO risque d'être grandiose"
        )
        fxp._parse_calls(self.con)
        self.assertEqual(self._calls(), [])

    def test_cashtag_sans_direction_aucun_call(self) -> None:
        self._add_post("p3", "$BTC is interesting these days")
        fxp._parse_calls(self.con)
        self.assertEqual(self._calls(), [])

    def test_prix_k_suffixe(self) -> None:
        self._add_post("p4", "Opend $btc short at 85.3k")
        fxp._parse_calls(self.con)
        (call,) = self._calls()
        self.assertEqual(call[0], "BTC")
        self.assertEqual(call[1], "short")
        self.assertEqual(call[2], 85300.0)
        self.assertEqual(call[5], "high")

    def test_separateur_milliers_francais(self) -> None:
        self._add_post("p5", "l'évident long à 83 000 $ sur $BTC, entrée jouée")
        fxp._parse_calls(self.con)
        (call,) = self._calls()
        self.assertEqual(call[0], "BTC")
        self.assertEqual(call[1], "long")
        self.assertEqual(call[2], 83000.0)

    def test_virgule_milliers_anglaise(self) -> None:
        self._add_post("p6", "$BTC long entry 83,000 here")
        fxp._parse_calls(self.con)
        (call,) = self._calls()
        self.assertEqual(call[2], 83000.0)

    def test_tp_sl_extraits(self) -> None:
        self._add_post("p7", "$BTC long, tp 90k, sl 82k, let's go")
        fxp._parse_calls(self.con)
        (call,) = self._calls()
        self.assertEqual(call[3], 90000.0)
        self.assertEqual(call[4], 82000.0)

    def test_parser_version_marque_les_lignes(self) -> None:
        self._add_post("p8", "$ETH short into the close")
        fxp._parse_calls(self.con)
        version = self.con.execute(
            "SELECT parser_version FROM x_calls LIMIT 1"
        ).fetchone()[0]
        self.assertEqual(version, fxp.PARSER_VERSION)


class TestResolvePostedAt(unittest.TestCase):
    def test_relatif_minutes(self) -> None:
        out = sxc.resolve_posted_at("Il y a 17 minutes", "2026-09-21T17:00:00Z")
        self.assertEqual(out, "2026-09-21T16:43:00Z")

    def test_relatif_heures(self) -> None:
        out = sxc.resolve_posted_at("Il y a 2 heures", "2026-09-21T17:00:00Z")
        self.assertEqual(out, "2026-09-21T15:00:00Z")

    def test_date_courte_annee_courante(self) -> None:
        out = sxc.resolve_posted_at("16 sept.", "2026-09-21T17:00:00Z")
        self.assertEqual(out, "2026-09-16T12:00:00Z")

    def test_date_courte_avec_annee(self) -> None:
        out = sxc.resolve_posted_at("27 oct. 2024", "2026-09-21T17:00:00Z")
        self.assertEqual(out, "2024-10-27T12:00:00Z")

    def test_date_future_retranche_un_an(self) -> None:
        # "31 déc." lu le 2 janvier : le post est de l'annee passee
        out = sxc.resolve_posted_at("31 déc.", "2026-01-02T10:00:00Z")
        self.assertEqual(out, "2025-12-31T12:00:00Z")

    def test_iso_avec_millisecondes_passe_telles_quelles(self) -> None:
        out = sxc.resolve_posted_at(
            "2026-09-21T17:36:44.000Z", "2026-09-21T18:00:00Z"
        )
        self.assertEqual(out, "2026-09-21T17:36:44.000Z")

    def test_none_restant_none(self) -> None:
        self.assertIsNone(sxc.resolve_posted_at(None, "2026-09-21T17:00:00Z"))
        self.assertIsNone(sxc.resolve_posted_at("date incompréhensible",
                                                "2026-09-21T17:00:00Z"))


class TestFirstHit(unittest.TestCase):
    POSTED_MS = int(datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    H1 = 3_600_000

    def test_win_touch_tp_dabord(self) -> None:
        bars = [_bar(self.POSTED_MS + self.H1, high=91_500, low=89_500)]
        verdict, ts = sxc._first_hit(bars, self.POSTED_MS, "long", 91_000, 89_000)
        self.assertEqual(verdict, "win")
        self.assertEqual(ts, self.POSTED_MS + self.H1)

    def test_loss_touch_sl_dabord(self) -> None:
        bars = [_bar(self.POSTED_MS + self.H1, high=90_500, low=88_500)]
        verdict, _ = sxc._first_hit(bars, self.POSTED_MS, "long", 91_000, 89_000)
        self.assertEqual(verdict, "loss")

    def test_les_deux_dans_la_meme_bougie_indecis(self) -> None:
        bars = [_bar(self.POSTED_MS + self.H1, high=92_000, low=88_000)]
        verdict, _ = sxc._first_hit(bars, self.POSTED_MS, "long", 91_000, 89_000)
        self.assertEqual(verdict, "indecis")

    def test_short_inverse(self) -> None:
        # short : TP en dessous (89k), SL au dessus (91k) — la bougie descend
        # au TP sans toucher le SL -> win
        bars = [_bar(self.POSTED_MS + self.H1, high=90_500, low=88_500)]
        verdict, _ = sxc._first_hit(bars, self.POSTED_MS, "short", 89_000, 91_000)
        self.assertEqual(verdict, "win")

    def test_short_touche_sl(self) -> None:
        bars = [_bar(self.POSTED_MS + self.H1, high=91_500, low=89_500)]
        verdict, _ = sxc._first_hit(bars, self.POSTED_MS, "short", 89_000, 91_000)
        self.assertEqual(verdict, "loss")

    def test_bougies_avant_le_post_ignorees(self) -> None:
        bars = [_bar(self.POSTED_MS - self.H1, high=92_000, low=88_000)]
        verdict, ts = sxc._first_hit(bars, self.POSTED_MS, "long", 91_000, 89_000)
        self.assertEqual(verdict, "en_cours")
        self.assertIsNone(ts)

    def test_sans_touch_en_cours(self) -> None:
        bars = [_bar(self.POSTED_MS + self.H1, high=90_500, low=89_500)]
        verdict, _ = sxc._first_hit(bars, self.POSTED_MS, "long", 91_000, 89_000)
        self.assertEqual(verdict, "en_cours")


class TestForwardPrices(unittest.TestCase):
    def test_entry_close_derniere_bougie_avant_post(self) -> None:
        base = int(datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
        bars = [
            _bar(base, high=1, low=1, close=84_000),
            _bar(base + 3_600_000, high=1, low=1, close=85_000),
            _bar(base + 2 * 3_600_000, high=1, low=1, close=86_000),
        ]
        posted = base + 3_600_000 + 60_000  # pendant la 2e bougie
        self.assertEqual(sxc._entry_close(bars, posted), 85_000)

    def test_forward_close_premiere_bougie_apres_cible(self) -> None:
        base = int(datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
        bars = [_bar(base + i * 3_600_000, high=1, low=1, close=84_000 + i * 100)
                for i in range(5)]
        close = sxc._forward_close(bars, base, 2)
        self.assertEqual(close, 84_200)


class TestDerived(RegistreDbTest):
    """Positionnement de la foule et velocite des mentions."""

    def test_positioning_et_mentions(self) -> None:
        self._add_post("d1", "$BTC long here")
        self._add_post("d2", "$BTC short now")
        self._add_post("d3", "$ETH long, $BTC mentioned too")
        fxp._parse_calls(self.con)
        fxp._update_derived(self.con, day="2026-09-21")
        pos = {
            sym: (n, pct) for _, sym, n, pct in self.con.execute(
                "SELECT day, symbol, n_calls, pct_long FROM x_positioning")
        }
        self.assertEqual(pos["BTC"], (2, 50.0))
        self.assertEqual(pos["ETH"], (1, 100.0))
        men = dict(
            ((sym, n) for sym, day, n, *_ in self.con.execute(
                "SELECT symbol, day, n FROM x_mentions"))
        )
        # d1 + d2 + d3 mentionnent tous $BTC ; $ETH une seule fois
        self.assertEqual(men["BTC"], 3)
        self.assertEqual(men["ETH"], 1)


if __name__ == "__main__":
    unittest.main()


class TestParseCallsV3(RegistreDbTest):
    """v3 : ticker nu dans l'univers Aster, alias PEPE->1000PEPE, incrémental."""

    def setUp(self) -> None:
        super().setUp()
        self._old_universe = fxp._UNIVERSE_OVERRIDE
        fxp._UNIVERSE_OVERRIDE = {"BOME", "WIF", "1000PEPE", "TURBO"}

    def tearDown(self) -> None:
        fxp._UNIVERSE_OVERRIDE = self._old_universe
        super().tearDown()

    def test_ticker_nu_dans_univers_parse_confiance_low(self) -> None:
        self._add_post("v3a", "long BOME here we go boys")
        fxp._parse_calls(self.con)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0][0], calls[0][1], calls[0][5]), ("BOME", "long", "low"))

    def test_ticker_nu_hors_univers_ignore_regression_egld(self) -> None:
        self._add_post("v3b", "l'EGLD a 500$, long EGLD maintenant c'est le moment")
        fxp._parse_calls(self.con)
        self.assertEqual(self._calls(), [])

    def test_direction_doit_preceder_le_ticker(self) -> None:
        self._add_post("v3c", "BOME long setup tonight")
        fxp._parse_calls(self.con)
        self.assertEqual(self._calls(), [])

    def test_alias_pepe_vers_1000pepe(self) -> None:
        self._add_post("v3d", "$PEPE long to the moon")
        fxp._parse_calls(self.con)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "1000PEPE")

    def test_incremental_ne_reparse_pas_les_anciens(self) -> None:
        self._add_post("v3e", "$WIF long entry now")
        self.assertEqual(fxp._parse_calls(self.con), 1)
        self.assertEqual(fxp._parse_calls(self.con), 0)
        self.assertEqual(len(self._calls()), 1)

    def test_cashtag_sans_direction_reste_ignore(self) -> None:
        self._add_post("v3f", "$BOME is looking interesting today")
        fxp._parse_calls(self.con)
        self.assertEqual(self._calls(), [])


class TestTradability(unittest.TestCase):
    """Gate microstructure : spread top-10 live + frais legacy par symbole."""

    def test_collectionnable_selon_spread(self) -> None:
        from scripts.score_x_calls import tradability

        spreads = {"WIFUSDT": 5.0, "BOMEUSDT": 150.0}
        res = tradability({"BOME", "WIF"}, spread_fetch=spreads.get)
        self.assertTrue(res["WIF"]["collectionnable"])
        self.assertFalse(res["BOME"]["collectionnable"])
        self.assertEqual(res["BOME"]["spread_bps"], 150.0)
        self.assertEqual(res["WIF"]["fee_bps"], 4.0)  # frais taker USDT legacy

    def test_spread_indisponible_n_est_pas_collectionnable(self) -> None:
        from scripts.score_x_calls import tradability

        res = tradability({"BTC"}, spread_fetch=lambda pair: None)
        self.assertFalse(res["BTC"]["collectionnable"])
        self.assertIsNone(res["BTC"]["spread_bps"])

    def test_usd1_a_des_frais_reduits(self) -> None:
        from scripts.score_x_calls import tradability

        res = tradability({"FOO"}, spread_fetch=lambda pair: 1.0)
        # FOOUSDT : quote inconnue -> fallback 4 bps ; USD1 reste 0.5 via le legacy
        self.assertEqual(res["FOO"]["fee_bps"], 4.0)


class TestParseCallsV31(RegistreDbTest):
    """v3.1 : verbes d'action réels (bought/aped/sold) — le style fomo."""

    def setUp(self) -> None:
        super().setUp()
        self._old_universe = fxp._UNIVERSE_OVERRIDE
        fxp._UNIVERSE_OVERRIDE = {"PAID", "WIF", "TURBO"}

    def tearDown(self) -> None:
        fxp._UNIVERSE_OVERRIDE = self._old_universe
        super().tearDown()

    def test_market_bought_est_un_long(self) -> None:
        # le call réel de frogmanhaha raté par v2/v3
        self._add_post("v31a", "Market bought around $300k worth of\n$PAID\nto get myself about 1% of the supply")
        fxp._parse_calls(self.con)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0][0], calls[0][1]), ("PAID", "long"))

    def test_sold_est_un_exit_pas_un_short(self) -> None:
        self._add_post("v31b", "sold my $WIF bags, taking profits here")
        fxp._parse_calls(self.con)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "exit")

    def test_aped_est_un_long(self) -> None:
        self._add_post("v31c", "aped into $TURBO, this one prints")
        fxp._parse_calls(self.con)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0][0], calls[0][1]), ("TURBO", "long"))
