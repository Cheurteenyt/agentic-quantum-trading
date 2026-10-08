#!/usr/bin/env python3
"""R3 C-D5 (#215) — le code de sortie de `fetch_klines` distingue l'échec
TOTAL de l'échec PARTIEL.

Avant : `if res["failed"]: return 1`. Un seul symbole en échec suffisait.

Cette ligne de l'unité est un `ExecStart=` **sans** le préfixe `-` :

    ExecStart=... fetch_klines.py --fetch --symbols "..." --target-bars 3000

donc systemd **avortait les 12 étapes suivantes** — dont
`paper_forward`, `qubo_forward_tracker`, `reevaluate_oos`,
`aster_absorption`, `basis_guard`, `flow_snapshot`, `depth_heatmap`,
`housekeeping --apply`, `memecoin_pulse`, `listing_watcher` — alors que
**11 séries sur 12** venaient d'être écrites correctement.

Un hic réseau de 20 s sur un symbole coûtait une nuit entière de rapports,
et un Warehouse incomplet produisait des rapports qui semblaient bons parce
qu'ils n'existaient pas.

Même décision que le PR #189 pour `refresh_aster_cache` : le refresh
partiel est un état TOLÉRABLE, journalisé par systemd. L'échec **total**
reste un échec — c'est lui qu'il faut voir.

Ces tests n'utilisent **aucun réseau** : `fetch_and_store` est injectable,
et `main()` est patché sur son `_fetch` interne.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_klines as fk  # noqa: E402

SYMS = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]


def _rows(n=10):
    out = []
    for i in range(n):
        c = 100.0 + i
        out.append([1_700_000_000_000 + i * 3_600_000, c, c + 1, c - 1, c,
                    10.0, 1_700_000_000_000 + (i + 1) * 3_600_000 - 1])
    return out


class TestEchecTotalVsPartiel(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "k.db")
        self._orig_fetch = fk.fetch_klines
        self._orig_pag = fk.fetch_klines_paginated

    def tearDown(self):
        fk.fetch_klines = self._orig_fetch
        fk.fetch_klines_paginated = self._orig_pag
        self.tmp.cleanup()

    def _lancer(self, echecs: set[str]):
        """`main()` avec un fetch qui échoue pour les symboles de `echecs`.

        `main()` construit sa propre closure `_fetch`, on patche donc les
        deux fonctions qu'elle appelle — pas `fetch_and_store`, dont la
        signature de test est déjà utilisée ailleurs.
        """
        def faux_fetch(sym, *, interval, limit, base_url, timeout, **kw):
            if sym in echecs:
                raise fk.AsterFetchError("reseau indisponible (simule)")
            return _rows(min(limit, 10))

        def faux_pag(sym, *, interval, target_bars, base_url, timeout, **kw):
            if sym in echecs:
                return [], {"requests": 1, "fetched": 0, "reached_target": False,
                            "reason": "erreur", "first_ts": 0, "last_ts": 0}
            n = min(target_bars, 10)
            return _rows(n), {"requests": 1, "fetched": n,
                              "reached_target": True, "reason": "cible atteinte",
                              "first_ts": 0, "last_ts": 0}

        fk.fetch_klines = faux_fetch
        fk.fetch_klines_paginated = faux_pag
        return fk.main(["--fetch", "--db", self.db, "--interval", "1h",
                        "--sleep", "0", "--target-bars", "10",
                        "--symbols", ",".join(SYMS)])

    def test_echec_partiel_ne_coupe_pas_la_chaine(self) -> None:
        """11/12 réussis → la nuit continue. C'est le bug de l'issue."""
        rc = self._lancer({"BBBUSDT"})
        self.assertEqual(rc, 0,
                         "un seul symbole en échec coupe les 12 etapes "
                         "suivantes de l'unite")

    def test_echec_majoritaire_ne_coupe_pas_la_chaine(self) -> None:
        """3 sur 4 : c'est une mauvaise nuit, pas une nuit perdue."""
        rc = self._lancer({"BBBUSDT", "CCCUSDT", "DDDUSDT"})
        self.assertEqual(rc, 0)

    def test_echec_total_reste_un_echec(self) -> None:
        """Zéro série récupérée DOIT rester visible — c'est le vrai problème."""
        rc = self._lancer(set(SYMS))
        self.assertEqual(rc, 1,
                         "un echec total ne doit pas etre tolere : il n'y a "
                         "rien a rapporter et il faut le voir")

    def test_aucun_symbole_inchange_rien(self) -> None:
        self.assertEqual(self._lancer(set()), 0)

    def test_les_series_reussies_sont_bien_ecrites(self) -> None:
        """La tolérance ne doit pas coûter de données."""
        import sqlite3
        self._lancer({"BBBUSDT"})
        con = sqlite3.connect(self.db)
        try:
            n = con.execute("SELECT COUNT(DISTINCT symbol) FROM klines "
                            "WHERE interval='1h'").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n, len(SYMS) - 1,
                         "les symboles reussis doivent etre dans le warehouse")


if __name__ == "__main__":
    unittest.main()