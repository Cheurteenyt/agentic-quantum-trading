#!/usr/bin/env python3
"""F-041 — la fraîcheur du cache funding est un CONTRAT, pas une information.

Le cache est un SNAPSHOT live (F-030) : chaque symbole porte son propre
`cached_at`. Mesuré en prod au moment du fix :

    mtime du fichier : 15,5 h   → sonde VERTE
    48/73 symboles avec cached_at > 25 h
     9/73 avec cached_at > 30 j
    max : 127 j (SKYAIUSDT)

Le mtime ne bouge que quand le fichier est réécrit — un symbole non
rafraîchi garde sa vieille valeur ET le fichier est touché par les
autres symboles. La sonde était donc structurellement incapable de voir
la péremption.

Pire : `funding_scanner.py` et `carry_hedged.py` (tous deux `ExecStart=`
BLOQUANTS du nightly) consommaient `latest_funding_bps_per_8h` SANS
aucun contrôle d'âge. Un funding vieux de 4 mois annualisé à 3×365 donne
un chiffre qui a l'air d'un taux et qui n'en est pas un.
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.carry_hedged import FUNDING_MAX_AGE_S, load_fresh_sides  # noqa: E402
from scripts.funding_scanner import load_fresh_ranked  # noqa: E402

NOW = time.time()
DAY = 86400


def _cache(tmp: str, ages_days: dict[str, float]) -> Path:
    """Un cache de la bonne forme : {symbols: {SYM: {cached_at, data}}}."""
    p = Path(tmp) / "cache.json"
    p.write_text(json.dumps({
        "updated_at": NOW,
        "symbols": {
            sym: {
                "cached_at": NOW - age * DAY,
                "data": {
                    "latest_funding_bps_per_8h": 10.0 if i % 2 == 0 else -10.0,
                    "avg_funding_bps_per_8h": 8.0 if i % 2 == 0 else -8.0,
                },
            }
            for i, (sym, age) in enumerate(ages_days.items())
        },
    }), encoding="utf-8")
    return p


class TestFiltreParFraicheur(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = None
        import scripts.funding_scanner as fs
        import scripts.carry_hedged as ch
        self.fs, self.ch = fs, ch
        self.old = (fs.CACHE, ch.CACHE)
        fs.CACHE = _cache(self.tmp.name, {"FRESH": 0.1, "OLD": 400.0})
        ch.CACHE = fs.CACHE

    def tearDown(self):
        self.fs.CACHE, self.ch.CACHE = self.old
        self.tmp.cleanup()

    def test_un_symbole_perime_est_rejete(self):
        rows, rejected = load_fresh_ranked()
        self.assertEqual([r["symbol"] for r in rows], ["FRESH"])
        self.assertEqual(rejected, 1)

    def test_le_fresh_passe(self):
        rows, rejected = load_fresh_ranked()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "FRESH")

    def test_sans_cached_at_le_symbole_est_rejete(self):
        """L'absence d'horodatage n'est pas une fraîcheur."""
        p = Path(self.tmp.name) / "cache.json"
        blob = json.loads(p.read_text(encoding="utf-8"))
        del blob["symbols"]["FRESH"]["cached_at"]
        p.write_text(json.dumps(blob), encoding="utf-8")
        rows, rejected = load_fresh_ranked()
        self.assertEqual(rows, [])
        self.assertEqual(rejected, 2)   # FRESH (sans horodatage) + OLD (400 j)

    def test_la_fenetre_est_25h(self):
        self.assertEqual(FUNDING_MAX_AGE_S, 25 * 3600)

    def test_carry_hedged_filtre_aussi(self):
        shorts, longs, rejected = load_fresh_sides()
        self.assertEqual(rejected, 1)
        self.assertEqual([r["symbol"] for r in shorts + longs], ["FRESH"])

    def test_tout_perime_donne_vide(self):
        self.fs.CACHE = _cache(self.tmp.name, {"A": 30.0, "B": 60.0})
        self.ch.CACHE = self.fs.CACHE
        rows, rejected = load_fresh_ranked()
        self.assertEqual(rows, [])
        self.assertEqual(rejected, 2)

    def test_aucune_exception_sur_cache_malforme(self):
        p = Path(self.tmp.name) / "cache.json"
        p.write_text("{not json", encoding="utf-8")
        try:
            load_fresh_ranked()
            load_fresh_sides()
        except Exception as e:       # pragma: no cover
            self.fail(f"exception sur cache malforme : {e!r}")


class TestSondeAsterHealth(unittest.TestCase):
    def test_la_sonde_lit_le_max_des_cached_at(self):
        """Le max = le symbole le PLUS FRAIS. Le min serait toujours rouge."""
        src = (ROOT / "scripts/aster_health.py").read_text(encoding="utf-8")
        self.assertIn("time.time() - max(stamps)", src)
        self.assertNotIn("time.time() - min(stamps)", src)

    def test_la_sonde_ne_lit_plus_le_mtime(self):
        src = (ROOT / "scripts/aster_health.py").read_text(encoding="utf-8")
        self.assertNotIn("os.path.getmtime(CACHE)", src,
                         "le mtime du fichier ne peut pas dater un symbole")

    def test_la_sonde_sur_le_cache_reel(self):
        """La sonde doit répondre un nombre, pas None, sur la prod."""
        import scripts.aster_health as ah
        age = ah.funding_cache_age()
        self.assertIsNotNone(age)
        self.assertGreater(age, 0)


class TestConsommateursBloquants(unittest.TestCase):
    """Les deux consommateurs sont ExecStart= (bloquants) dans le nightly."""

    def test_ils_filtrent(self):
        for rel in ("scripts/funding_scanner.py", "scripts/carry_hedged.py"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(fichier=rel):
                self.assertIn("cached_at", src)
                self.assertIn("FUNDING_MAX_AGE_S", src)

    def test_le_rapport_signale_les_rejets(self):
        src = (ROOT / "scripts/funding_scanner.py").read_text(encoding="utf-8")
        self.assertIn("rejete(s)", src)
        src2 = (ROOT / "scripts/carry_hedged.py").read_text(encoding="utf-8")
        self.assertIn("rejete(s)", src2)


if __name__ == "__main__":
    unittest.main()