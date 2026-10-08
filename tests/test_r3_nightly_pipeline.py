#!/usr/bin/env python3
"""FIX R3 — pipeline nocturne dégradable : la batterie de non-régression.

Couvre :
  C-C3  service : les 3 premières étapes (refresh funding, funding_scanner,
        carry_hedged) sont tolérantes (ExecStart=-) — un exit 1 sporadique
        ne coupe plus les ~38 étapes suivantes.
  C-C2  refresh_aster_cache : une liste --symbols explicite n'est JAMAIS
        tronquée par --limit (25/73 frais = exactement l'ancien plafond).
  C-C1  memecoin_pulse : funding_row applique le contrat F-041 (cached_at
        > 25 h → (None, None)) — fini le « dernier règlement » de 15 jours.
  C-D1  listing_watcher : un hic réseau exchangeInfo → return 0.
  C-D2  listing_watcher : snapshot écrit en atomique, JSON corrompu →
        re-snapshot et return 0 (fin de l'empoisonnement auto-entretenu).
  C-D3  basis_guard : panne réseau totale → return 0 ; basis incalculable
        (prix nul) → warn et continue.
  C-C4  aster_health : sonde funding_cache_coverage (le MAX est aveugle au
        cache partiellement frais — 23/73 = sonde verte mensongère).
  C-C5  aster_health : `or 9e9` banni (0.0 falsy = fausse alerte ~3/j).
  C-C6  aster_health : une sonde qui lève alerte au lieu de tuer main().
  B-B   docstrings (MIN→MAX, run_stack −0,5 %).
"""
import json
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import scripts.aster_health as ah  # noqa: E402
import scripts.listing_watcher as lw  # noqa: E402
import scripts.memecoin_pulse as mp  # noqa: E402
import scripts.refresh_aster_cache as rac  # noqa: E402

DAY = 86400.0
NOW = time.time()


def _cache_json(tmp: str, ages_days: dict[str, float]) -> Path:
    p = Path(tmp) / "funding_cache.json"
    p.write_text(json.dumps({
        "updated_at": NOW,
        "symbols": {sym: {"cached_at": NOW - age * DAY,
                          "data": {"latest_funding_rate": 0.0001}}
                    for sym, age in ages_days.items()},
    }), encoding="utf-8")
    return p


class TestServiceTolerant(unittest.TestCase):
    """C-C3 / B-A : le head du nocturne ne coupe plus la chaîne."""

    def setUp(self):
        self.svc = (ROOT / "configs/systemd-user/trading-agent-nightly.service"
                    ).read_text(encoding="utf-8")

    def _exec_of(self, marker: str) -> str:
        for l in self.svc.split("\n"):
            if marker in l and l.startswith("ExecStart"):
                return l
        self.fail(f"ExecStart introuvable pour {marker}")

    def test_refresh_funding_est_tolerant(self):
        l = self._exec_of("refresh_aster_cache.py --refresh-funding")
        self.assertTrue(l.startswith("ExecStart=-"),
                        "l'étape 1 du nocturne doit être tolérante (C-C3)")

    def test_funding_scanner_et_carry_hedged_tolerants(self):
        for marker in ("scripts/funding_scanner.py", "scripts/carry_hedged.py"):
            l = self._exec_of(marker)
            self.assertTrue(l.startswith("ExecStart=-"),
                            f"{marker} doit être tolérant (B-A)")

    def test_la_campagne_est_derniere_et_tolerante(self):
        """Non-régression F-040 : --run/--review restent en fin et en -."""
        lines = [l for l in self.svc.split("\n") if l.startswith("ExecStart")]
        self.assertTrue(lines[-1].startswith("ExecStart=-"))
        self.assertIn("nightly_campaign.py --review", lines[-1])
        self.assertIn("nightly_campaign.py --run", lines[-2])


class TestRefreshSymbolsContrat(unittest.TestCase):
    """C-C2 : --symbols explicite = contrat, jamais tronqué."""

    def setUp(self):
        self.calls: list[list[str]] = []
        self._old_rf = rac.refresh_funding
        self._old_ds = rac.default_symbols

        def fake_rf(syms, **kw):
            self.calls.append(list(syms))
            return {"ok": len(syms), "failed": [], "backup": None}

        rac.refresh_funding = fake_rf
        rac.default_symbols = lambda limit=None: [
            f"DEF{i}USDT" for i in range(limit or 0)]

    def tearDown(self):
        rac.refresh_funding = self._old_rf
        rac.default_symbols = self._old_ds

    def test_liste_explicite_non_tronquee_par_limit(self):
        with redirect_stdout(StringIO()):
            rc = rac.main(["--refresh-funding", "--symbols",
                           "AAAUSDT,BBBUSDT,CCCUSDT,DDDUSDT,EEEUSDT",
                           "--limit", "3"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls[-1],
                         ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT"],
                         "une liste explicite de 5 a été tronquée à 3 (C-C2)")

    def test_limit_sapplique_aux_default_symbols(self):
        with redirect_stdout(StringIO()):
            rac.main(["--refresh-funding", "--limit", "3"])
        self.assertEqual(self.calls[-1], ["DEF0USDT", "DEF1USDT", "DEF2USDT"])


class TestMemecoinPulseFraicheur(unittest.TestCase):
    """C-C1 : le lecteur applique le contrat F-041."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = mp.FUNDING_CACHE

    def tearDown(self):
        mp.FUNDING_CACHE = self._old
        self.tmp.cleanup()

    def _use(self, ages_days):
        mp.FUNDING_CACHE = _cache_json(self.tmp.name, ages_days)

    def test_cache_frais_publie(self):
        self._use({"FRESHUSDT": 0.1})
        r, ann = mp.funding_row("FRESHUSDT")
        self.assertAlmostEqual(r, 0.01)
        self.assertAlmostEqual(ann, 0.01 * 3 * 365)

    def test_cache_perime_rejete(self):
        self._use({"OLDUSDT": 1.1})          # 26,4 h
        self.assertEqual(mp.funding_row("OLDUSDT"), (None, None))

    def test_pile_a_25h_rejete(self):
        self._use({"BOUNDUSDT": 25 / 24 + 1e-6})
        self.assertEqual(mp.funding_row("BOUNDUSDT"), (None, None))

    def test_sans_cached_at_rejete(self):
        self._use({"NOSTAMPUSDT": 0.0})
        p = Path(self.tmp.name) / "funding_cache.json"
        blob = json.loads(p.read_text(encoding="utf-8"))
        del blob["symbols"]["NOSTAMPUSDT"]["cached_at"]
        p.write_text(json.dumps(blob), encoding="utf-8")
        self.assertEqual(mp.funding_row("NOSTAMPUSDT"), (None, None))

    def test_cache_absent_rejete(self):
        mp.FUNDING_CACHE = Path(self.tmp.name) / "absent.json"
        self.assertEqual(mp.funding_row("XUSDT"), (None, None))


class TestListingWatcherResilient(unittest.TestCase):
    """C-D1 / C-D2 : hic réseau → 0 ; JSON corrompu → re-snapshot."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_snap = lw.ROOT, lw.SNAPSHOT
        self.old_argv = sys.argv
        lw.ROOT = Path(self.tmp.name)
        lw.SNAPSHOT = Path(self.tmp.name) / "warehouse" / "aster_universe.json"
        sys.argv = ["listing_watcher.py"]

    def tearDown(self):
        lw.ROOT, lw.SNAPSHOT = self.old_root, self.old_snap
        sys.argv = self.old_argv
        self.tmp.cleanup()

    def test_ecriture_atomique_sans_residu(self):
        target = Path(self.tmp.name) / "snap.json"
        lw._write_atomic(target, '{"a": 1}')
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"a": 1})
        self.assertFalse(target.with_name(target.name + ".tmp").exists())

    def test_reseau_ko_retourne_0(self):
        def boom():
            raise TimeoutError("exchangeInfo down")
        old = lw.live_universe
        lw.live_universe = boom
        try:
            with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
                rc = lw.main()
        finally:
            lw.live_universe = old
        self.assertEqual(rc, 0, "un hic réseau ne doit pas avorter le nocturne")

    def test_snapshot_corrompu_ressnapshotte(self):
        lw.SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        lw.SNAPSHOT.write_text('{"captured_at": 1, "symbols": {"TRUNC', encoding="utf-8")
        uni = {"AAAUSDT": {"status": "TRADING"}}
        old = lw.live_universe
        lw.live_universe = lambda: uni
        try:
            with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
                rc = lw.main()
        finally:
            lw.live_universe = old
        self.assertEqual(rc, 0)
        fresh = json.loads(lw.SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(fresh["symbols"], uni)


class TestBasisGuardTolerant(unittest.TestCase):
    """C-D3 : panne totale → 0 ; prix dégénéré → warn, pas de crash."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_argv = sys.argv

    def tearDown(self):
        sys.argv = self.old_argv
        self.tmp.cleanup()

    def _run(self):
        import scripts.basis_guard as bg
        sys.argv = ["basis_guard.py"]
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            return bg.main()

    def test_panne_reseau_totale_retourne_0(self):
        import scripts.basis_guard as bg
        old = bg.last_price
        bg.last_price = lambda url, sym: (_ for _ in ()).throw(OSError("down"))
        try:
            self.assertEqual(self._run(), 0,
                             "une panne Aster+Binance ne doit pas avorter le nocturne")
        finally:
            bg.last_price = old

    def test_prix_nul_ne_crash_pas(self):
        import scripts.basis_guard as bg
        calls = {"n": 0}

        def fake(url, sym):
            calls["n"] += 1
            return 0.0 if calls["n"] % 2 == 0 else 1.0  # Binance nul

        old = bg.last_price
        bg.last_price = fake
        try:
            self.assertEqual(self._run(), 0)
        finally:
            bg.last_price = old


class TestAsterHealthSondes(unittest.TestCase):
    """C-C4 / C-C6 : coverage + sonde levante = alerte, pas crash."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cache, self.old_state, self.old_checks = \
            ah.CACHE, ah.STATE, ah.CHECKS
        ah.STATE = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        ah.CACHE, ah.STATE, ah.CHECKS = \
            self.old_cache, self.old_state, self.old_checks
        self.tmp.cleanup()

    def _use_cache(self, ages_days):
        ah.CACHE = _cache_json(self.tmp.name, ages_days)

    def test_coverage_partiellement_frais(self):
        self._use_cache({"A": 0.1, "B": 0.2, "C": 30.0})
        cov = ah.funding_cache_coverage()
        self.assertAlmostEqual(cov, 2 / 3)
        # la sonde MAX, elle, reste verte (0,1 j) : c'est TOUT le problème C-C4
        self.assertLess(ah.funding_cache_age(), 25 * 3600)

    def test_coverage_cache_corrompu_est_alerte(self):
        p = Path(self.tmp.name) / "broken.json"
        p.write_text("{oops", encoding="utf-8")
        ah.CACHE = p
        self.assertEqual(ah.funding_cache_coverage(), -1.0)

    def test_sonde_levante_alerte_sans_crasher(self):
        def boom():
            raise AttributeError("blob au mauvais format")
        ah.CHECKS = [("boom", boom, "test sonde levante")]
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            rc = ah.main()
        self.assertEqual(rc, 0, "une sonde qui lève ne doit pas tuer main()")
        state = json.loads(ah.STATE.read_text(encoding="utf-8"))
        self.assertFalse(state["checks"]["boom"]["ok"])

    def test_plus_aucun_or_9e9_dans_le_code(self):
        """C-C5 : l'âge 0.0 (falsy) n'est plus 9e9 ; seul None l'est."""
        self.assertEqual(ah._age_or_inf(0.0), 0.0)
        self.assertEqual(ah._age_or_inf(None), 9e9)


if __name__ == "__main__":
    unittest.main()
