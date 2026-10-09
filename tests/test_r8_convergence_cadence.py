"""Ronde 8 — deux fossiles de la chaîne « convergence » Aster.

D-09 (fossil daté d43969f, commit de création d'aster_convergence) :
  le lookup portait sur `bias + fund_bias * 0` — la 3e lentille ne comptait
  JAMAIS dans le label : les clés ±3 (« CONFLUENCE 3/3 ») étaient
  inatteignables alors que la docstring promet « les TROIS lentilles », et
  l'annotation funding n'était déclenchée que pour bias >= 2 (jamais short).

Cadence (fossil de la famille cascade_funding) :
  memecoin_pulse.funding_row, funding_scanner._ann_pct et
  carry_hedged._ann_pct annualisaient à 3 règlements/8 h FIGÉS alors que le
  cache mesure l'intervalle réel par symbole (refresh_aster_cache FIX F12,
  médiane des gaps) et ne l'exposait à personne qui le consomme. Sur le
  cache réel : 14/25 symboles de l'univers de convergence mal annualisés
  (×8 à 1 h, ×2 à 4 h) — colonne « Funding ann. », seuils −30/+50 et
  classements carry évaluaient une quantité différente selon la cadence.

Fallback 8 h = cadence standard, bit-à-bit identique à l'ancien calcul
quand l'intervalle n'est pas mesuré (compat F-041 conservée).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.memecoin_pulse as mp
import scripts.funding_scanner as fs
import scripts.carry_hedged as ch
import scripts.aster_convergence as ac


def _cache(tmpdir: str, entries: dict) -> Path:
    """entries : symbol -> {cached_at (jours), rate, interval_h}"""
    blob = {"symbols": {}}
    now = time.time()
    for sym, spec in entries.items():
        blob["symbols"][sym] = {
            "cached_at": now - spec.get("days", 0.1) * 86400,
            "data": {
                "latest_funding_rate": spec.get("rate", 0.0001),
                "funding_interval_hours": spec.get("interval_h"),
            },
        }
    p = Path(tmpdir) / "funding_cache.json"
    p.write_text(json.dumps(blob), encoding="utf-8")
    return p


class TestCadenceMemecoinPulse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = mp.FUNDING_CACHE
        self.addCleanup(setattr, mp, "FUNDING_CACHE", self._old)

    def test_interval_1h_annualise_x8(self):
        mp.FUNDING_CACHE = _cache(self.tmp.name, {"AUSDT": {"rate": 0.0001, "interval_h": 1.0}})
        r, ann = mp.funding_row("AUSDT")
        self.assertAlmostEqual(r, 0.01)
        self.assertAlmostEqual(ann, 0.01 * 24.0 * 365)

    def test_interval_4h_annualise_x2(self):
        mp.FUNDING_CACHE = _cache(self.tmp.name, {"BUSDT": {"rate": 0.0001, "interval_h": 4.0}})
        _, ann = mp.funding_row("BUSDT")
        self.assertAlmostEqual(ann, 0.01 * 6.0 * 365)

    def test_interval_8h_inchange(self):
        mp.FUNDING_CACHE = _cache(self.tmp.name, {"CUSDT": {"rate": 0.0001, "interval_h": 8.0}})
        _, ann = mp.funding_row("CUSDT")
        self.assertAlmostEqual(ann, 0.01 * 3 * 365)

    def test_sans_interval_fallback_8h_compat_f041(self):
        mp.FUNDING_CACHE = _cache(self.tmp.name, {"DUSDT": {"rate": 0.0001, "interval_h": None}})
        _, ann = mp.funding_row("DUSDT")
        self.assertAlmostEqual(ann, 0.01 * 3 * 365)

    def test_interval_zero_ou_garbage_fallback(self):
        for iv in (0, 0.0, "abc"):
            mp.FUNDING_CACHE = _cache(self.tmp.name, {"EUSDT": {"rate": 0.0001, "interval_h": iv}})
            _, ann = mp.funding_row("EUSDT")
            self.assertAlmostEqual(ann, 0.01 * 3 * 365, msg=f"interval={iv!r}")

    def test_fraicheur_preservee(self):
        mp.FUNDING_CACHE = _cache(self.tmp.name, {"OLDUSDT": {"rate": 0.0001, "interval_h": 1.0, "days": 1.2}})
        self.assertEqual(mp.funding_row("OLDUSDT"), (None, None))


class TestCadenceFundingScanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = fs.CACHE
        self.addCleanup(setattr, fs, "CACHE", self._old)

    def test_ann_pct_par_cadence(self):
        self.assertAlmostEqual(fs._ann_pct(100.0, 1.0), 100.0 * 24.0 * 365 / 100)
        self.assertAlmostEqual(fs._ann_pct(100.0, 4.0), 100.0 * 6.0 * 365 / 100)
        self.assertAlmostEqual(fs._ann_pct(100.0, 8.0), 100.0 * 3 * 365 / 100)
        self.assertAlmostEqual(fs._ann_pct(100.0, None), 100.0 * 3 * 365 / 100)
        self.assertIsNone(fs._ann_pct(None, 1.0))

    def test_load_fresh_ranked_lit_l_intervalle(self):
        blob = {"symbols": {
            "ONEHUSDT": {"cached_at": time.time(), "data": {
                "latest_funding_bps_per_8h": 100.0, "avg_funding_bps_per_8h": 100.0,
                "funding_interval_hours": 1.0}},
            "EIGHTHUSDT": {"cached_at": time.time(), "data": {
                "latest_funding_bps_per_8h": 100.0, "avg_funding_bps_per_8h": 100.0,
                "funding_interval_hours": 8.0}},
        }}
        p = Path(self.tmp.name) / "c.json"
        p.write_text(json.dumps(blob), encoding="utf-8")
        fs.CACHE = p
        rows, _ = fs.load_fresh_ranked()
        by = {r["symbol"]: r["latest_ann"] for r in rows}
        self.assertAlmostEqual(by["ONEHUSDT"], 8760.0)   # 1 % × 24 × 365
        self.assertAlmostEqual(by["EIGHTHUSDT"], 1095.0)  # 1 % × 3 × 365


class TestCadenceCarryHedged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = ch.CACHE
        self.addCleanup(setattr, ch, "CACHE", self._old)

    def test_ann_pct_par_cadence(self):
        self.assertAlmostEqual(ch._ann_pct(100.0, 1.0), 100.0 * 24.0 * 365 / 100)
        self.assertAlmostEqual(ch._ann_pct(100.0, None), 100.0 * 3 * 365 / 100)
        self.assertIsNone(ch._ann_pct(0.0, 1.0))

    def test_load_fresh_sides_lit_l_intervalle(self):
        blob = {"symbols": {
            "FOURHUSDT": {"cached_at": time.time(), "data": {
                "latest_funding_bps_per_8h": 50.0, "funding_interval_hours": 4.0}},
        }}
        p = Path(self.tmp.name) / "c.json"
        p.write_text(json.dumps(blob), encoding="utf-8")
        ch.CACHE = p
        shorts, longs, _ = ch.load_fresh_sides()
        self.assertEqual(len(shorts), 1)
        self.assertAlmostEqual(shorts[0]["ann"], 50.0 * 6.0 * 365 / 100)  # ×2 vs avant


class _ConvergenceFixture(unittest.TestCase):
    """DB x_pressure + oi_history en mémoire-disque + funding_row factice."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.xdb = Path(self.tmp.name) / "x_posts.db"
        self.kdb = Path(self.tmp.name) / "klines.db"
        con = sqlite3.connect(self.xdb)
        con.execute("CREATE TABLE x_pressure (ticker TEXT, posts INT, velocity REAL, "
                    "longs INT, shorts INT, captured_at TEXT)")
        rows = [
            ("TESTL", 10, 2.0, 8, 2),   # long : X +1
            ("TESTS", 10, 2.0, 2, 9),   # short : X -1 (et OI -1 plus bas)
            ("TESTN", 10, 2.0, 2, 9),   # short sans funding
            ("TESTQ", 2, 0.0, 2, 0),    # < 3 posts : lentille X muette
        ]
        # captured_at est un timestamp EPOCH SECONDS (x_aster_pulse écrit
        # now) — l'interaction r9 (#243 fraîcheur × #237 fixture) : une
        # date ISO lève ValueError au filtre float(cap) ajouté par #243.
        # La fixture suit le contrat réel du producteur.
        con.executemany(
            "INSERT INTO x_pressure VALUES (?,?,?,?,?, ?)",
            [(r[0], r[1], r[2], r[3], r[4], time.time()) for r in rows])
        con.commit(); con.close()
        con = sqlite3.connect(self.kdb)
        con.execute("CREATE TABLE oi_history (symbol TEXT, open_interest REAL, captured_at_ms INTEGER)")
        data = [
            ("TESTLUSDT", 100.0, 1), ("TESTLUSDT", 110.0, 2),   # ΔOI +10 %
            ("TESTSUSDT", 100.0, 1), ("TESTSUSDT", 90.0, 2),    # ΔOI -10 %
            ("TESTNUSDT", 100.0, 1), ("TESTNUSDT", 90.0, 2),
        ]
        con.executemany("INSERT INTO oi_history VALUES (?,?,?)", data)
        con.commit(); con.close()
        ac.XDB = self.xdb
        ac.KDB = self.kdb
        ac.REPORTS = Path(self.tmp.name)
        self.addCleanup(self._restore_paths)

    def _restore_paths(self):
        import importlib
        importlib.reload(ac)

    def _fake_funding(self, annual_by_symbol: dict):
        def funding_row(symbol: str):
            if symbol in annual_by_symbol:
                return None, annual_by_symbol[symbol]
            return None, None
        return funding_row

    def _run(self, annual: dict) -> str:
        self._old_frow = mp.funding_row
        mp.funding_row = self._fake_funding(annual)
        self.addCleanup(setattr, mp, "funding_row", self._old_frow)
        self.assertEqual(ac.main(), 0)
        reports = list(Path(self.tmp.name).glob("aster-convergence-*.md"))
        self.assertEqual(len(reports), 1)
        return reports[0].read_text(encoding="utf-8")


class TestConfluence3of3(_ConvergenceFixture):
    def test_confluence_long_3_sur_3_atteignable(self):
        # X +1, OI +1, funding +1 (annual >= 50) → l'ancien `* 0` bornait à 2/3
        report = self._run({"TESTLUSDT": 60.0})
        self.assertIn("CONFLUENCE 3/3", report)

    def test_confluence_short_3_sur_3_atteignable(self):
        report = self._run({"TESTSUSDT": -60.0})
        self.assertIn("CONFLUENCE 3/3 (short)", report)

    def test_annotation_funding_symetrique_cote_short(self):
        # ancien code : `bias >= 2` — l'annotation n'apparaissait jamais en short
        report = self._run({"TESTSUSDT": -60.0})
        self.assertIn("funding négatif (crowded short)", report)

    def test_annotation_funding_cote_long_conservee(self):
        report = self._run({"TESTLUSDT": 60.0})
        self.assertIn("funding élevé (crowded long)", report)

    def test_short_2_sur_3_sans_funding_reste_2_3(self):
        report = self._run({"TESTNUSDT": None})
        self.assertIn("convergence 2/3 (short)", report)
        self.assertNotIn("CONFLUENCE 3/3", report)

    def test_funding_neutre_ne_produit_pas_de_confluence(self):
        # funding d'accord mais sous le seuil : 2/3 seulement, pas d'annotation
        report = self._run({"TESTLUSDT": 10.0})
        self.assertIn("convergence 2/3", report)
        self.assertNotIn("CONFLUENCE 3/3", report)


class TestAntiRegressionSource(unittest.TestCase):
    def test_plus_de_terme_mort_dans_le_source(self):
        src = (ROOT / "scripts" / "aster_convergence.py").read_text(encoding="utf-8")
        self.assertNotIn("fund_bias * 0", src)
        self.assertIn("bias + fund_bias", src)

    def test_annotation_symetrisee(self):
        src = (ROOT / "scripts" / "aster_convergence.py").read_text(encoding="utf-8")
        self.assertIn("abs(bias) >= 2 and fund_bias != 0", src)

    def test_les_trois_annualiseurs_consomment_l_intervalle(self):
        for mod, fname in ((mp, "funding_row"), (fs, "_ann_pct"), (ch, "_ann_pct")):
            with self.subTest(module=mod.__name__):
                self.assertTrue(hasattr(mod, "_per_day_for"),
                                f"{mod.__name__} : helper de cadence manquant")
                self.assertAlmostEqual(mod._per_day_for(1.0), 24.0)


if __name__ == "__main__":
    unittest.main()
