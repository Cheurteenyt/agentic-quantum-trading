"""Tests du script de refresh des caches Aster. Aucun appel reseau reel."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "refresh_aster_cache", ROOT / "scripts" / "refresh_aster_cache.py"
)
rac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rac)

from backend.services.backtest_v2.costs import (  # noqa: E402
    CostDataUnavailable,
    load_funding_rate,
)


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(payload):
    def _open(req, timeout=None):
        return _FakeResp(payload)
    return _open


def failing_opener(req, timeout=None):
    raise urllib.error.URLError("reseau coupe")


FUNDING_ROWS = [
    {"symbol": "BTCUSDT", "fundingTime": 1780000000000 + i * 28_800_000,
     "fundingRate": "0.0001"}
    for i in range(40)
]


class TestCacheAge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent(self):
        self.assertIsNone(rac.cache_age_days(self.dir / "nope.json"))

    def test_fresh(self):
        p = self.dir / "c.json"
        rac.write_cache_atomic(p, {"cached_at": time.time(), "status": "ok"})
        age = rac.cache_age_days(p)
        self.assertIsNotNone(age)
        self.assertLess(age, 0.01)

    def test_old(self):
        p = self.dir / "c.json"
        old = time.time() - 90 * 86400
        rac.write_cache_atomic(p, {"symbols": {"BTCUSDT": {"cached_at": old}}})
        self.assertGreater(rac.cache_age_days(p), 80)

    def test_un_symbole_perime_ne_peut_pas_etre_masque_par_la_racine(self):
        """F-046 — LE TEST DU BUG.

        Le refresh réécrit `updated_at = time.time()` à la RACINE du
        fichier à chaque passe. Tant que `cache_age_days` prenait
        l'horodatage le plus récent, UN SEUL symbole rafraîchi suffisait à
        rendre tout le cache « frais ».

        Constat sur le fichier de production : `--check` annonçait 0,96 j
        « OK » alors que 71 des 73 symboles dataient de plus de 25 h
        (le plus ancien de 127,7 j). Le watchdog était structurellement
        incapable de voir la péremption qu'il prétend surveiller.

        On doit donc lire l'âge du symbole le PLUS ANCIEN.
        """
        now = time.time()
        p = self.dir / "c.json"
        rac.write_cache_atomic(p, {
            "updated_at": now,                       # le refresh vient de passer
            "symbols": {
                "FRAISUSDT": {"cached_at": now},
                "VIEUXUSDT": {"cached_at": now - 90 * 86400},
            },
        })
        age = rac.cache_age_days(p)
        self.assertGreater(
            age, 80,
            f"un symbole de 90 j est masqué par `updated_at` racine : "
            f"cache_age_days={age} — le garde F-041/F-046 est redevenu inerte")

    def test_symbol_ages_days_exclut_la_racine(self):
        """`updated_at` racine = horodatage du FICHIER, pas de la donnée."""
        now = time.time()
        p = self.dir / "c.json"
        rac.write_cache_atomic(p, {
            "updated_at": now,
            "symbols": {"AUSDT": {"cached_at": now - 2 * 86400}},
        })
        ages = rac.symbol_ages_days(p)
        self.assertEqual(set(ages), {"AUSDT"})
        self.assertAlmostEqual(ages["AUSDT"], 2.0, delta=0.01)

    def test_stale_symbols_nomme_les_symboles(self):
        now = time.time()
        p = self.dir / "c.json"
        rac.write_cache_atomic(p, {"updated_at": now, "symbols": {
            "OK1USDT": {"cached_at": now},
            "VIEUX1USDT": {"cached_at": now - 10 * 86400},
            "VIEUX2USDT": {"cached_at": now - 40 * 86400},
        }})
        perimes = rac.stale_symbols(p, 1.0)
        self.assertEqual([s for s, _ in perimes], ["VIEUX2USDT", "VIEUX1USDT"],
                         "triés du plus ancien au plus récent")
        self.assertAlmostEqual(dict(perimes)["VIEUX2USDT"], 40.0, delta=0.01)

    def test_cache_sans_symbole_horodate_retombe_sur_la_racine(self):
        p = self.dir / "c.json"
        rac.write_cache_atomic(p, {"cached_at": time.time(), "status": "ok"})
        self.assertLess(rac.cache_age_days(p), 0.01)
        self.assertEqual(rac.symbol_ages_days(p), {})

    def test_fichier_illisible_ne_leve_pas(self):
        p = self.dir / "c.json"
        p.write_text("{ pas du json", encoding="utf-8")
        self.assertIsNone(rac.cache_age_days(p))
        self.assertEqual(rac.symbol_ages_days(p), {})


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_content_and_no_tmp_left(self):
        p = self.dir / "c.json"
        rac.write_cache_atomic(p, {"a": 1, "b": [1, 2]})
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"a": 1, "b": [1, 2]})
        self.assertEqual([f.name for f in self.dir.iterdir()], ["c.json"])

    def test_original_intact_on_serialization_failure(self):
        p = self.dir / "c.json"
        rac.write_cache_atomic(p, {"ok": True})
        before = p.read_text(encoding="utf-8")

        with self.assertRaises(ValueError):
            rac.write_cache_atomic(p, {"bad": object()})

        self.assertEqual(p.read_text(encoding="utf-8"), before)
        self.assertEqual([f.name for f in self.dir.iterdir()], ["c.json"])


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_none_if_absent(self):
        self.assertIsNone(rac.backup_existing(self.dir / "nope.json"))

    def test_backup_created(self):
        p = self.dir / "c.json"
        rac.write_cache_atomic(p, {"v": 1})
        bak = rac.backup_existing(p)
        self.assertIsNotNone(bak)
        self.assertNotEqual(bak, p)
        self.assertTrue(bak.exists())
        self.assertIn(".bak-", bak.name)
        self.assertEqual(json.loads(bak.read_text(encoding="utf-8")), {"v": 1})


class TestFundingParsing(unittest.TestCase):
    def test_parse_structure(self):
        data = rac.parse_funding_rows("BTCUSDT", FUNDING_ROWS)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["funding_count"], 40)
        self.assertAlmostEqual(data["avg_funding_bps_per_8h"], 1.0, places=6)
        self.assertEqual(data["last_funding_time"], FUNDING_ROWS[-1]["fundingTime"])
        for k in ("symbol", "source", "avg_funding_rate", "min_funding_rate",
                  "max_funding_rate", "first_funding_time"):
            self.assertIn(k, data)

    def test_parse_empty(self):
        data = rac.parse_funding_rows("BTCUSDT", [])
        self.assertEqual(data["status"], "empty")
        self.assertEqual(data["funding_count"], 0)

    def test_fetch_with_mocked_opener(self):
        data = rac.fetch_funding_history(
            "BTCUSDT", limit=40, opener=fake_opener(FUNDING_ROWS)
        )
        self.assertEqual(data["status"], "ok")


class TestProbe(unittest.TestCase):
    def test_probe_failure_is_reported_not_raised(self):
        res = rac.probe_api(opener=failing_opener)
        self.assertFalse(res["reachable"])
        self.assertIsNotNone(res["error"])
        self.assertIsNone(res["latency_ms"])

    def test_probe_success(self):
        res = rac.probe_api(opener=fake_opener({"serverTime": int(time.time() * 1000)}))
        self.assertTrue(res["reachable"])
        self.assertIsNotNone(res["clock_drift_ms"])
        self.assertIsNone(res["error"])


class TestIntegrationWithCosts(unittest.TestCase):
    """Preuve decisive : un cache ecrit par le script est lisible par costs.py."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "aster_public_funding_history_cache.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_cache_accepted_by_load_funding_rate(self):
        res = rac.refresh_funding(
            ["BTCUSDT"],
            cache_path=self.cache,
            limit=40,
            sleep_s=0.0,
            opener=fake_opener(FUNDING_ROWS),
        )
        self.assertTrue(res["written"])

        rate = load_funding_rate("BTCUSDT", self.cache)
        self.assertEqual(rate.symbol, "BTCUSDT")
        self.assertAlmostEqual(rate.avg_bps_per_8h, 1.0, places=6)
        self.assertEqual(rate.sample_count, 40)
        self.assertFalse(rate.is_stale)
        self.assertLess(rate.age_days, 0.01)

    def test_stale_cache_still_rejected(self):
        payload = {
            "symbols": {
                "BTCUSDT": {
                    "cached_at": time.time() - 90 * 86400,
                    "data": rac.parse_funding_rows("BTCUSDT", FUNDING_ROWS),
                }
            },
            "updated_at": time.time() - 90 * 86400,
        }
        rac.write_cache_atomic(self.cache, payload)
        with self.assertRaises(CostDataUnavailable):
            load_funding_rate("BTCUSDT", self.cache)

    def test_refresh_failure_leaves_cache_untouched(self):
        rac.write_cache_atomic(self.cache, {"symbols": {}, "updated_at": 1.0})
        before = self.cache.read_text(encoding="utf-8")
        res = rac.refresh_funding(
            ["BTCUSDT"], cache_path=self.cache, sleep_s=0.0, opener=failing_opener
        )
        self.assertFalse(res["written"])
        self.assertEqual(self.cache.read_text(encoding="utf-8"), before)


class TestCheckMode(unittest.TestCase):
    def test_check_writes_nothing(self):
        mtimes = {
            p: p.stat().st_mtime
            for p in (rac.EXCHANGE_INFO_CACHE, rac.FUNDING_CACHE)
            if p.exists()
        }
        rc = rac.main(["--check", "--base-url", "http://127.0.0.1:9", "--timeout", "0.2"])
        self.assertIn(rc, (0, 1))
        for p, m in mtimes.items():
            self.assertEqual(p.stat().st_mtime, m, f"{p} a ete modifie en mode check")


if __name__ == "__main__":
    unittest.main(verbosity=2)
