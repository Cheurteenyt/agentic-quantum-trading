#!/usr/bin/env python3
"""Tests du warehouse de klines. AUCUN appel reseau reel (opener injecte)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json  # noqa: E402
import sqlite3  # noqa: E402
import urllib.error  # noqa: E402

from scripts import fetch_klines as fk  # noqa: E402
from backend.services.backtest_v2.baselines import (  # noqa: E402
    Bar,
    bars_from_klines,
    momentum_baseline,
)

HOUR = 3_600_000
T0 = 1_700_000_000_000


def make_rows(n, start=T0, step=HOUR, base=100.0, drift=1.0):
    """Serie synthetique continue et strictement croissante."""
    rows = []
    for i in range(n):
        c = base + drift * i
        rows.append([
            start + i * step,
            c,            # open
            c + 2.0,      # high
            c - 2.0,      # low
            c + 0.5,      # close
            10.0 + i,     # volume
            start + (i + 1) * step - 1,
        ])
    return rows


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_opener(payload, capture=None):
    def _open(req, timeout=None):
        if capture is not None:
            capture.append(req.full_url)
        return FakeResponse(payload)
    return _open


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.con = fk.init_db(":memory:")

    def tearDown(self):
        self.con.close()

    def _insert(self, open_time, o, h, l, c, v):
        self.con.execute(
            "INSERT INTO klines (symbol, interval, open_time, open, high, low, "
            "close, volume, close_time, snapshot_id, source, fetched_at) "
            "VALUES ('BTCUSDT','1h',?,?,?,?,?,?,?, 'snap','src', 0.0)",
            (open_time, o, h, l, c, v, open_time + HOUR),
        )

    def test_schema_version_recorded(self):
        row = self.con.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()
        self.assertEqual(int(row["value"]), fk.SCHEMA_VERSION)

    def test_schema_rejects_zero_price(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert(T0, 0.0, 10.0, 5.0, 8.0, 1.0)

    def test_schema_rejects_negative_price(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert(T0, 10.0, 10.0, 5.0, -8.0, 1.0)

    def test_schema_rejects_high_below_low(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert(T0, 10.0, 5.0, 9.0, 8.0, 1.0)

    def test_schema_rejects_negative_volume(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert(T0, 10.0, 12.0, 9.0, 11.0, -1.0)

    def test_schema_accepts_valid_row(self):
        self._insert(T0, 10.0, 12.0, 9.0, 11.0, 0.0)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM klines").fetchone()[0], 1)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.con = fk.init_db(":memory:")

    def tearDown(self):
        self.con.close()

    def test_store_inserts_all(self):
        res = fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(10))
        self.assertEqual(res["inserted"], 10)
        self.assertEqual(res["skipped"], 0)

    def test_reinsertion_creates_no_duplicate(self):
        rows = make_rows(10)
        fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        res = fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        self.assertEqual(res["inserted"], 0)
        self.assertEqual(res["skipped"], 10)
        total = self.con.execute("SELECT COUNT(*) FROM klines").fetchone()[0]
        self.assertEqual(total, 10)

    def test_partial_overlap_counts_correctly(self):
        fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(10))
        res = fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(15))
        self.assertEqual(res["inserted"], 5)
        self.assertEqual(res["skipped"], 10)

    def test_symbols_are_isolated(self):
        fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(5))
        fk.store_klines(self.con, "ETHUSDT", "1h", make_rows(5))
        self.assertEqual(len(fk.load_bars(self.con, "BTCUSDT", "1h")), 5)
        self.assertEqual(len(fk.load_bars(self.con, "ETHUSDT", "1h")), 5)

    def test_unknown_interval_rejected(self):
        with self.assertRaises(ValueError):
            fk.store_klines(self.con, "BTCUSDT", "7q", make_rows(3))


class ParseTests(unittest.TestCase):
    def test_row_too_short_raises(self):
        with self.assertRaises(fk.KlineParseError):
            fk.parse_kline_row([T0, 1.0, 2.0])

    def test_non_numeric_raises(self):
        with self.assertRaises(fk.KlineParseError):
            fk.parse_kline_row([T0, "abc", 2.0, 1.0, 1.5, 3.0, T0 + 1])

    def test_zero_price_raises(self):
        with self.assertRaises(fk.KlineParseError):
            fk.parse_kline_row([T0, 0.0, 2.0, 1.0, 1.5, 3.0, T0 + 1])

    def test_high_below_low_raises(self):
        with self.assertRaises(fk.KlineParseError):
            fk.parse_kline_row([T0, 1.0, 1.0, 2.0, 1.5, 3.0, T0 + 1])

    def test_negative_volume_raises(self):
        with self.assertRaises(fk.KlineParseError):
            fk.parse_kline_row([T0, 1.0, 2.0, 1.0, 1.5, -3.0, T0 + 1])

    def test_none_row_raises(self):
        with self.assertRaises(fk.KlineParseError):
            fk.parse_kline_row(None)

    def test_malformed_batch_raises_in_store(self):
        con = fk.init_db(":memory:")
        rows = make_rows(3)
        rows[1][2] = -5.0  # high negatif
        with self.assertRaises(fk.KlineParseError):
            fk.store_klines(con, "BTCUSDT", "1h", rows)
        con.close()


class GapTests(unittest.TestCase):
    def setUp(self):
        self.con = fk.init_db(":memory:")

    def tearDown(self):
        self.con.close()

    def test_no_gap_on_continuous_series(self):
        fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(50))
        self.assertEqual(fk.detect_gaps(self.con, "BTCUSDT", "1h"), [])

    def test_gap_detected(self):
        rows = make_rows(10)
        del rows[5]  # trou artificiel
        fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        gaps = fk.detect_gaps(self.con, "BTCUSDT", "1h")
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0], (T0 + 4 * HOUR, T0 + 6 * HOUR))

    def test_multiple_gaps(self):
        rows = make_rows(20)
        for idx in (15, 10, 5):
            del rows[idx]
        fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        self.assertEqual(len(fk.detect_gaps(self.con, "BTCUSDT", "1h")), 3)

    def test_empty_series_has_no_gap(self):
        self.assertEqual(fk.detect_gaps(self.con, "BTCUSDT", "1h"), [])

    def test_store_reports_gaps(self):
        rows = make_rows(6)
        del rows[3]
        res = fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        self.assertEqual(len(res["gaps"]), 1)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.con = fk.init_db(":memory:")

    def tearDown(self):
        self.con.close()

    def test_snapshot_id_deterministic(self):
        fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(10))
        a = fk.snapshot_id_for("BTCUSDT", "1h", self.con)
        b = fk.snapshot_id_for("BTCUSDT", "1h", self.con)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("aster-BTCUSDT-1h-"))

    def test_snapshot_id_changes_when_data_changes(self):
        fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(10))
        before = fk.snapshot_id_for("BTCUSDT", "1h", self.con)
        fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(12))
        after = fk.snapshot_id_for("BTCUSDT", "1h", self.con)
        self.assertNotEqual(before, after)

    def test_snapshot_stored_with_rows(self):
        res = fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(4))
        row = self.con.execute(
            "SELECT DISTINCT snapshot_id FROM klines").fetchone()
        self.assertEqual(row["snapshot_id"], res["snapshot_id"])
        snap = self.con.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?",
            (res["snapshot_id"],)).fetchone()
        self.assertEqual(snap["bar_count"], 4)
        self.assertEqual(snap["source"], fk.SOURCE)


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.con = fk.init_db(":memory:")

    def tearDown(self):
        self.con.close()

    def test_stats_empty(self):
        st = fk.warehouse_stats(self.con)
        self.assertEqual(st["total_bars"], 0)
        self.assertEqual(st["series_count"], 0)

    def test_stats_consistent(self):
        fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(10))
        fk.store_klines(self.con, "ETHUSDT", "1h", make_rows(7))
        st = fk.warehouse_stats(self.con)
        self.assertEqual(st["total_bars"], 17)
        self.assertEqual(st["series_count"], 2)
        self.assertEqual(sum(s["bars"] for s in st["series"]), 17)
        self.assertEqual(st["schema_version"], fk.SCHEMA_VERSION)

    def test_stats_reports_gaps(self):
        rows = make_rows(8)
        del rows[4]
        fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        st = fk.warehouse_stats(self.con)
        self.assertEqual(st["series"][0]["gaps"], 1)


class LoadBarsTests(unittest.TestCase):
    def setUp(self):
        self.con = fk.init_db(":memory:")

    def tearDown(self):
        self.con.close()

    def test_load_bars_matches_bars_from_klines(self):
        """Contrat central : le warehouse relit ce que baselines sait parser."""
        rows = make_rows(30)
        fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        stored = fk.load_bars(self.con, "BTCUSDT", "1h")
        direct = bars_from_klines(rows)
        self.assertEqual(stored, direct)
        self.assertTrue(all(isinstance(b, Bar) for b in stored))

    def test_load_bars_range_filter(self):
        fk.store_klines(self.con, "BTCUSDT", "1h", make_rows(20))
        bars = fk.load_bars(self.con, "BTCUSDT", "1h",
                            start_ts=T0 + 5 * HOUR, end_ts=T0 + 9 * HOUR)
        self.assertEqual(len(bars), 5)
        self.assertEqual(bars[0].ts, T0 + 5 * HOUR)

    def test_load_bars_sorted_even_if_inserted_unsorted(self):
        rows = make_rows(10)
        rows.reverse()
        fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        bars = fk.load_bars(self.con, "BTCUSDT", "1h")
        self.assertEqual([b.ts for b in bars], sorted(b.ts for b in bars))

    def test_momentum_baseline_runs_on_loaded_bars(self):
        """Integration decisive : les barres du warehouse alimentent le
        benchmark momentum sans conversion intermediaire."""
        rows = make_rows(200)
        # Retournement pour forcer un croisement de moyennes mobiles.
        for i in range(100, 200):
            c = 100.0 + 99.0 - (i - 100)
            rows[i][1] = c
            rows[i][2] = c + 2.0
            rows[i][3] = c - 2.0
            rows[i][4] = c + 0.5
        fk.store_klines(self.con, "BTCUSDT", "1h", rows)
        bars = fk.load_bars(self.con, "BTCUSDT", "1h")
        res = momentum_baseline(bars, fast=5, slow=20)
        self.assertEqual(res.name, "momentum")
        self.assertGreater(res.n_trades, 0)
        self.assertIsNotNone(res.win_rate)


class FetchTests(unittest.TestCase):
    """Aucun reseau : l'opener est injecte."""

    def test_fetch_klines_uses_public_endpoint(self):
        seen = []
        rows = make_rows(3)
        out = fk.fetch_klines("btcusdt", interval="1h", limit=3,
                              opener=fake_opener(rows, seen))
        self.assertEqual(out, rows)
        self.assertIn("/fapi/v3/klines", seen[0])
        self.assertIn("symbol=BTCUSDT", seen[0])
        self.assertIn("limit=3", seen[0])

    def test_fetch_klines_caps_limit(self):
        seen = []
        fk.fetch_klines("BTCUSDT", limit=99999, opener=fake_opener([], seen))
        self.assertIn(f"limit={fk.MAX_LIMIT}", seen[0])

    def test_fetch_klines_network_error_is_wrapped(self):
        def boom(req, timeout=None):
            raise urllib.error.URLError("down")
        with self.assertRaises(fk.AsterFetchError):
            fk.fetch_klines("BTCUSDT", opener=boom)

    def test_fetch_klines_http_error_is_wrapped(self):
        def boom(req, timeout=None):
            raise urllib.error.HTTPError("u", 429, "rate", None, None)
        with self.assertRaises(fk.AsterFetchError):
            fk.fetch_klines("BTCUSDT", opener=boom)

    def test_fetch_klines_rejects_non_list_payload(self):
        with self.assertRaises(fk.AsterFetchError):
            fk.fetch_klines("BTCUSDT", opener=fake_opener({"code": -1}))

    def test_fetch_klines_empty_symbol(self):
        with self.assertRaises(ValueError):
            fk.fetch_klines("  ", opener=fake_opener([]))

    def test_fetch_and_store_with_injected_fetcher(self):
        con = fk.init_db(":memory:")
        rows = make_rows(12)

        def fetcher(sym, interval="1h", limit=10, base_url="", timeout=0):
            return rows

        res = fk.fetch_and_store(con, ["BTCUSDT"], interval="1h", fetcher=fetcher)
        self.assertEqual(res["ok"], 1)
        self.assertEqual(res["details"]["BTCUSDT"]["inserted"], 12)
        con.close()

    def test_fetch_and_store_failure_is_reported_not_swallowed(self):
        con = fk.init_db(":memory:")

        def fetcher(sym, **kw):
            raise fk.AsterFetchError("boom")

        res = fk.fetch_and_store(con, ["BTCUSDT"], fetcher=fetcher)
        self.assertEqual(res["ok"], 0)
        self.assertEqual(res["failed"], ["BTCUSDT"])
        con.close()


class PaginationTests(unittest.TestCase):
    """Pagination sans reseau : opener injecte, pages controlees."""

    def _paging_opener(self, page_sizes, calls, fail_at=None):
        """Opener qui renvoie des pages contigues de tailles donnees.

        `fail_at` (1-indexe) leve une URLError -> AsterFetchError en amont.
        """
        state = {"n": 0, "next_ts": T0}

        def _open(req, timeout=None):
            state["n"] += 1
            calls.append(req.full_url)
            if fail_at is not None and state["n"] == fail_at:
                raise urllib.error.URLError("down")
            idx = state["n"] - 1
            size = page_sizes[idx] if idx < len(page_sizes) else 0
            rows = make_rows(size, start=state["next_ts"])
            state["next_ts"] += size * HOUR
            return FakeResponse(rows)

        return _open

    def test_paginates_until_short_page(self):
        calls = []
        rows, meta = fk.fetch_klines_paginated(
            "BTCUSDT", interval="1h", target_bars=5000,
            opener=self._paging_opener([1500, 1500, 200], calls))
        self.assertEqual(meta["requests"], 3)
        self.assertEqual(meta["fetched"], 3200)
        self.assertEqual(len(rows), 3200)
        self.assertFalse(meta["reached_target"])
        self.assertEqual(meta["first_ts"], T0)
        self.assertEqual(meta["last_ts"], T0 + 3199 * HOUR)
        self.assertEqual(len(calls), 3)
        # Chaque requete apres la premiere repart de la derniere open_time + 1 pas.
        self.assertIn(f"startTime={T0 + 1500 * HOUR}", calls[1])

    def test_reaches_target_exactly(self):
        calls = []
        rows, meta = fk.fetch_klines_paginated(
            "BTCUSDT", interval="1h", target_bars=3000,
            opener=self._paging_opener([1500, 1500], calls))
        self.assertTrue(meta["reached_target"])
        self.assertEqual(meta["fetched"], 3000)
        self.assertEqual(meta["requests"], 2)
        self.assertEqual(len(rows), 3000)

    def test_stops_on_end_of_history_without_raising(self):
        calls = []
        rows, meta = fk.fetch_klines_paginated(
            "BTCUSDT", interval="1h", target_bars=5000,
            opener=self._paging_opener([300], calls))
        self.assertEqual(meta["requests"], 1)
        self.assertEqual(meta["fetched"], 300)
        self.assertFalse(meta["reached_target"])
        self.assertFalse(meta["reason"].startswith("error:"))
        self.assertEqual(len(rows), 300)

    def test_empty_first_page_is_not_an_error(self):
        calls = []
        rows, meta = fk.fetch_klines_paginated(
            "BTCUSDT", interval="1h", target_bars=3000,
            opener=self._paging_opener([0], calls))
        self.assertEqual(rows, [])
        self.assertEqual(meta["fetched"], 0)
        self.assertIsNone(meta["first_ts"])
        self.assertFalse(meta["reached_target"])

    def test_network_error_keeps_what_was_fetched(self):
        calls = []
        rows, meta = fk.fetch_klines_paginated(
            "BTCUSDT", interval="1h", target_bars=5000,
            opener=self._paging_opener([1500, 1500], calls, fail_at=2))
        self.assertEqual(meta["fetched"], 1500)
        self.assertEqual(len(rows), 1500)
        self.assertEqual(meta["requests"], 1)   # la 2e a echoue
        self.assertFalse(meta["reached_target"])
        self.assertTrue(meta["reason"].startswith("error:"))

    def test_stored_rows_from_pagination_are_continuous(self):
        con = fk.init_db(":memory:")
        rows, meta = fk.fetch_klines_paginated(
            "BTCUSDT", interval="1h", target_bars=3000,
            opener=self._paging_opener([1500, 1500], []))
        snap = fk.snapshot_id_for_rows("BTCUSDT", "1h",
                                       [fk.parse_kline_row(r, i)
                                        for i, r in enumerate(rows)])
        res = fk.store_klines(con, "BTCUSDT", "1h", rows, snapshot_id=snap)
        self.assertEqual(res["inserted"], 3000)
        self.assertEqual(res["gaps"], [])
        con.close()

    def test_unknown_interval_rejected_before_network(self):
        with self.assertRaises(ValueError):
            fk.fetch_klines_paginated("BTCUSDT", interval="9q",
                                      opener=fake_opener([]))

    def test_empty_symbol_rejected(self):
        with self.assertRaises(ValueError):
            fk.fetch_klines_paginated("  ", opener=fake_opener([]))


class CliTests(unittest.TestCase):
    def test_default_mode_is_check_and_writes_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "klines.db"
            rc = fk.main(["--db", str(db)])
            self.assertEqual(rc, 1)          # base absente
            self.assertFalse(db.exists())    # --check n'a rien cree

    def test_check_on_populated_db(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "klines.db"
            con = fk.init_db(db)
            fk.store_klines(con, "BTCUSDT", "1h", make_rows(30))
            con.close()
            self.assertEqual(fk.main(["--db", str(db)]), 0)
            self.assertEqual(
                fk.main(["--db", str(db), "--export", "BTCUSDT", "--interval", "1h"]), 0)

    def test_bad_interval_returns_2(self):
        self.assertEqual(fk.main(["--interval", "13q"]), 2)

    def test_interval_ms_table(self):
        self.assertEqual(fk.interval_ms("1h"), HOUR)
        self.assertEqual(fk.interval_ms("1d"), 24 * HOUR)
        with self.assertRaises(ValueError):
            fk.interval_ms("nope")


if __name__ == "__main__":
    unittest.main(verbosity=2)
