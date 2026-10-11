#!/usr/bin/env python3
"""P3 (audit Sonnet 5.5, R4) — les univers point-in-time : le delisting est
DÉRIVÉ (données × snapshot live), jamais saisi à la main, jamais « à tenir
à jour » (qui ne serait jamais tenu à jour).

Les défauts d'origine : `delisted_at` hardcodé None dans generate() (un
manifest qui cache le survivorship), `univ10` seul (les alts/memes sans
manifest → apply_universe fail-closed sur toute spec qui les déclare), et
la confusion trappeuse entre trou de COLLECTE et mort (1000PEPEUSDT a des
barres anciennes mais trade encore : le croiser avec le snapshot LIVE est
la seule lecture honnête).

Fixture : BTCUSDT majeure vivante · WIFUSDT meme morte en 2023 ·
ABCUSDT alt vivante · USDCUSDT stable.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.research_integrity import _coherence_point_in_time  # noqa: E402
from scripts.universe import _classe_auto  # noqa: E402

J2023_12 = "2023-12-01"
FIN_2023 = 1701388800000


def _db(tmp: Path) -> Path:
    import sqlite3
    db = tmp / "klines.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE klines (symbol TEXT, interval TEXT, "
                "open_time INTEGER, open REAL, high REAL, low REAL, "
                "close REAL, volume REAL)")
    con.execute("CREATE TABLE funding_history (symbol TEXT, "
                "funding_time INTEGER, rate REAL)")
    rows = []
    for sym, start, end in (("BTCUSDT", 1788278400000, 1791331200000),
                            ("ABCUSDT", 1788278400000, 1791331200000),
                            ("USDCUSDT", 1788278400000, 1791331200000),
                            ("WIFUSDT", 1672531200000, FIN_2023)):
        t = start
        while t <= end:
            rows.append((sym, "1h", t, 1.0, 1.0, 1.0, 1.0, 1.0))
            t += 3_600_000
    con.executemany("INSERT INTO klines VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return db


def _live(tmp: Path, trading: dict[str, str]) -> Path:
    p = tmp / "aster_universe.json"
    p.write_text(json.dumps({
        "captured_at": 1791683967.0,
        "symbols": {s: {"onboardDate": 1630051200000, "status": st}
                    for s, st in trading.items()}}), encoding="utf-8")
    return p


class LeDelistingEstDerive(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _db(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def _gen(self, trading: dict[str, str]) -> dict:
        import scripts.universe as U
        live = _live(Path(self.tmp.name), trading)
        with unittest.mock.patch.object(U, "LIVE_SNAPSHOT", live), \
             unittest.mock.patch.object(U, "UNIVERSE_DIR",
                                        Path(self.tmp.name) / "universe"):
            U.generate("test", ["BTCUSDT", "WIFUSDT", "ABCUSDT",
                                "USDCUSDT"], self.db)
            return U.load("test")

    def test_absent_du_snapshot_live_est_deliste(self):
        """WIFUSDT n'est plus listé → delisted_at = sa dernière observation,
        avec la PROVENANCE (leçon F7 : un chiffre sans source est une
        invention)."""
        m = self._gen({"BTCUSDT": "TRADING", "ABCUSDT": "TRADING"})
        e = m["symbols"]["WIFUSDT"]
        self.assertEqual(e["delisted_at"], J2023_12)
        self.assertIn("absent du snapshot live", e["deliste_source"])

    def test_trading_reste_vivant_meme_avec_barres_anciennes(self):
        """Le piège central : le test décisif est le STATUT LIVE — un
        symbole TRADING est vivant même si sa collecte s'arrête (trou de
        collecte ≠ mort)."""
        m = self._gen({"BTCUSDT": "TRADING", "ABCUSDT": "TRADING",
                       "WIFUSDT": "TRADING"})
        self.assertIsNone(m["symbols"]["WIFUSDT"]["delisted_at"])
        self.assertIsNone(m["symbols"]["WIFUSDT"]["deliste_source"])

    def test_status_non_trading_est_deliste(self):
        """Présent au snapshot mais status SETTLING/SETTLED = mort."""
        m = self._gen({"BTCUSDT": "TRADING", "ABCUSDT": "TRADING",
                       "WIFUSDT": "SETTLING"})
        e = m["symbols"]["WIFUSDT"]
        self.assertEqual(e["delisted_at"], J2023_12)
        self.assertIn("SETTLING", e["deliste_source"])

    def test_sans_snapshot_tout_est_vivant_honnetement(self):
        """Pas de snapshot live → null partout, et le manifest LE DIT
        (deliste_source_snapshot None) — on ne prétend pas dériver ce qu'on
        n'a pas dérivé."""
        import scripts.universe as U
        with unittest.mock.patch.object(U, "LIVE_SNAPSHOT",
                                        Path(self.tmp.name) / "absent.json"), \
             unittest.mock.patch.object(U, "UNIVERSE_DIR",
                                        Path(self.tmp.name) / "universe"):
            U.generate("test", ["BTCUSDT"], self.db)
            m = U.load("test")
        self.assertIsNone(m["deliste_source_snapshot"])
        self.assertIsNone(m["symbols"]["BTCUSDT"]["delisted_at"])


class LesClassesSontObjectives(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _db(Path(self.tmp.name))
        d = Path(self.tmp.name)
        (d / "universe").mkdir()
        import yaml
        (d / "universe" / "univ10.yaml").write_text(yaml.safe_dump(
            {"universe": "univ10",
             "symbols": {"BTCUSDT": {"bars": 1}}}), encoding="utf-8")
        import scripts.universe as U
        self._patch = unittest.mock.patch.object(U, "UNIVERSE_DIR",
                                                 d / "universe")
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def test_meme_est_la_liste_machine_intersectee_au_warehouse(self):
        from scripts.memecoin_pulse import MEMECOINS
        got = _classe_auto("meme", self.db)
        attendu = sorted(set(MEMECOINS) & {"BTCUSDT", "ABCUSDT",
                                           "USDCUSDT", "WIFUSDT"})
        self.assertEqual(got, attendu)
        self.assertIn("WIFUSDT", got, "WIFUSDT est dans MEMECOINS")

    def test_alts_exclut_majeures_meme_et_stables(self):
        got = _classe_auto("alts", self.db)
        self.assertIn("ABCUSDT", got)
        self.assertNotIn("BTCUSDT", got, "majeure")
        self.assertNotIn("WIFUSDT", got, "meme")
        self.assertNotIn("USDCUSDT", got, "stable")

    def test_majeures_vient_du_manifest(self):
        self.assertEqual(_classe_auto("majeures", self.db), ["BTCUSDT"])


class LaCoherencePointInTime(unittest.TestCase):

    def test_delisting_sans_source_est_un_defaut(self):
        m = {"symbols": {"X": {"observed_start": "2023-01-01",
                               "observed_end": "2023-12-01",
                               "delisted_at": "2023-12-01"}}}
        p = _coherence_point_in_time("t", m)
        self.assertTrue(any("deliste_source" in x for x in p), p)

    def test_delisting_source_et_date_cohérente_passe(self):
        m = {"symbols": {"X": {"observed_start": "2023-01-01",
                               "observed_end": "2023-12-01",
                               "delisted_at": "2023-12-01",
                               "deliste_source": "absent du snapshot live"}}}
        self.assertEqual(_coherence_point_in_time("t", m), [])

    def test_delisting_avant_lobservation_est_un_defaut(self):
        m = {"symbols": {"X": {"observed_start": "2023-06-01",
                               "observed_end": "2023-12-01",
                               "delisted_at": "2023-01-01",
                               "deliste_source": "x"}}}
        p = _coherence_point_in_time("t", m)
        self.assertTrue(any("observed_start" in x for x in p), p)

    def test_le_depot_reel_passe(self):
        """Ancrage réel : I011 doit passer sur les manifests du dépôt."""
        import yaml
        udir = ROOT / "research" / "universe"
        problemes = []
        for f in sorted(udir.glob("*.yaml")):
            m = yaml.safe_load(f.read_text(encoding="utf-8"))
            problemes.extend(_coherence_point_in_time(f.stem, m or {}))
        self.assertEqual(problemes, [], problemes)


if __name__ == "__main__":
    unittest.main()
