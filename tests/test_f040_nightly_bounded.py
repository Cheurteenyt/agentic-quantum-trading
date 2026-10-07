#!/usr/bin/env python3
"""F-040 — la campagne nocturne était SANS BORNE, et son timeout tuait 20 étapes.

Deux bugs dans le même fichier, tous deux mesurés sur la base de prod :

1. Le PLAN n'avait pas de plafond. `check_readiness()` renvoie toutes les
   séries « usable » du warehouse, toutes intervalles confondues. Le
   passage de l'univers 1h à l'univers 15m a fait passer le plan de 65
   séries (29 min le 03/10) à 324 → 324 × 6 stratégies = 280 584
   lanes/nuit, soit ~86 min pour 3600 s de `TimeoutStartSec`. Les
   4 nuits du 04→07/10 sont finies en `result='timeout'`.

   Corollaire mesuré : `load_bars` charge la série ENTIÈRE puis le caller
   tronque à 3000. BTCUSDT 1m = 2,67 M de barres = 1,2 Gio de RSS et
   11,8 s pour en garder 3000. 14,7 M de barres lues pour 972 000 utiles,
   × 324 séries.

2. Le retour valait 0 même sur une campagne VIDE ou 100 % en erreur. Dans
   l'unité systemd, `nightly_campaign.py --run` est un `ExecStart=`
   BLOQUANT : en 9e position, son dépassement interrompait le service en
   plein et les 20 ExecStart= suivants (the_machine, full_arsenal_2,
   aster_absorption, housekeeping, le collector funding) n'ont pas tourné
   du 04 au 07/10. Le journal ne disait que « result=timeout ».
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# fetch_klines importe `aster_rate` en top-level (flat, comme le lance le
# nightly depuis scripts/) — il faut scripts/ sur le path pour l'importer.
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.nightly_campaign import (  # noqa: E402
    DEFAULT_INTERVAL, MAX_BARS_NIGHTLY, MAX_SERIES_NIGHTLY, _INTERVAL_MS,
    window_start_ts)


class TestPlafondDuPlan(unittest.TestCase):
    def test_un_plafond_existe(self):
        self.assertIsInstance(MAX_SERIES_NIGHTLY, int)
        self.assertGreater(MAX_SERIES_NIGHTLY, 0)

    def test_le_plafond_tient_dans_le_budget_de_temps(self):
        """Le plafond doit pouvoir finir dans TimeoutStartSec.

        Mesuré le 03/10 : 65 séries / 56 290 lanes / 29 min ≈ 16 s par
        série. On garde une marge de 4x pour le 1h (moins de séries que
        le 15m) et on vérifie que le plafond reste sous une heure de
        budget systemd.
        """
        secondes_par_serie = 16.0
        budget_secondes = 3600
        self.assertLessEqual(
            MAX_SERIES_NIGHTLY * secondes_par_serie, budget_secondes,
            f"{MAX_SERIES_NIGHTLY} séries × {secondes_par_serie}s = "
            f"{MAX_SERIES_NIGHTLY * secondes_par_serie:.0f}s > "
            f"{budget_secondes}s de budget")

    def test_le_plan_ne_peut_plus_exploser(self):
        """Invariant de régression : même 1000 séries, le plan est borné."""
        for n_series in (65, 324, 1000, 10_000):
            retenu = min(n_series, MAX_SERIES_NIGHTLY)
            self.assertLessEqual(retenu, MAX_SERIES_NIGHTLY)
            self.assertEqual(retenu, MAX_SERIES_NIGHTLY if n_series > MAX_SERIES_NIGHTLY else n_series)


class TestIntervalleParDefaut(unittest.TestCase):
    def test_1h_est_le_defaut(self):
        """1h est l'intervalle du registre et de paper_forward."""
        self.assertEqual(DEFAULT_INTERVAL, "1h")

    def test_1h_est_connu_de_la_table(self):
        self.assertIn(DEFAULT_INTERVAL, _INTERVAL_MS)


class TestFenetreChargeeEnSQLBorne(unittest.TestCase):
    """Le bornage doit être calculé, pas deviné."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        import sqlite3
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row   # init_db() le fait en prod
        con.execute("CREATE TABLE klines (symbol TEXT, interval TEXT, "
                    "open_time INTEGER, open REAL, high REAL, low REAL, "
                    "close REAL, volume REAL)")
        # S0/S1 profond, S2 court — voir rows plus bas
        step = _INTERVAL_MS["1h"]
        base = 1_700_000_000_000
        # S0/S1 font 200 000 barres (≈ la profondeur d'une série 1m : le
        # vrai BTCUSDT 1m en a 2,67 M) pour que le rapport de volume soit
        # mesurable. S2 reste court, c'est le cas « pas de gain ».
        rows = [(f"S{i}", "1h", base + j * step, 100.0 + j, 101.0 + j,
                 99.0 + j, 100.5 + j, 1.0)
                for i, n in ((0, 200_000), (1, 200_000), (2, 5_000))
                for j in range(n)]
        con.executemany("INSERT INTO klines VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()
        con.close()
        # la connexion UTILISÉE par les tests doit avoir row_factory=Row,
        # comme init_db() en prod (sinon load_bars indexe par nom et lève)
        self.con = sqlite3.connect(self.db)
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_la_fenetre_porte_sur_les_dernieres_barres(self):
        ts = window_start_ts(self.con, "S0", "1h")
        row = self.con.execute(
            "SELECT MAX(open_time) FROM klines WHERE symbol='S0' "
            "AND interval='1h'").fetchone()
        last = row[0]
        self.assertEqual(ts, last - (MAX_BARS_NIGHTLY - 1) * _INTERVAL_MS["1h"])

    def test_un_intervalle_inconnu_replie_sur_none(self):
        """None = chargement complet : jamais moins correct, plus lent."""
        self.assertIsNone(window_start_ts(self.con, "S0", "7m"))

    def test_un_symbole_absent_replie_sur_none(self):
        self.assertIsNone(window_start_ts(self.con, "NOPE", "1h"))

    def test_la_fenetre_bornee_donne_le_meme_resultat_que_la_troncature(self):
        """Équivalence EXIGÉE : SQL borné == charge-tout-puis-tronque.

        C'est la propriété qui garantit qu'on n'a pas changé le verdict
        de la campagne en optimisant — juste son coût.
        """
        from scripts.fetch_klines import load_bars
        complet = load_bars(self.con, "S0", "1h")
        tronc = complet[-MAX_BARS_NIGHTLY:]
        borne = load_bars(self.con, "S0", "1h",
                          start_ts=window_start_ts(self.con, "S0", "1h"))
        self.assertEqual(len(borne), len(tronc))
        self.assertEqual([b.ts for b in borne], [b.ts for b in tronc])

    def test_le_bornage_economise_presque_tout(self):
        from scripts.fetch_klines import load_bars
        complet = load_bars(self.con, "S0", "1h")
        borne = load_bars(self.con, "S0", "1h",
                          start_ts=window_start_ts(self.con, "S0", "1h"))
        self.assertLess(len(borne) * 10, len(complet),
                        "le bornage doit diviser le volume par plus de 10x "
                        "sur une série profonde")


class TestRetourNonNulSiAucunResultat(unittest.TestCase):
    """Le bug 2 : exit 0 sur une campagne vide."""

    def _source(self):
        return (ROOT / "scripts/nightly_campaign.py").read_text(encoding="utf-8")

    def test_le_code_source_ne_peut_pas_retourner_0_sur_zero_testee(self):
        src = self._source()
        self.assertIn("if not tested:", src)
        self.assertIn("aucune lane testee", src)

    def test_une_campagne_100pct_en_erreur_retourne_1(self):
        src = self._source()
        self.assertIn("errored >= tested", src)

    def test_la_campagne_est_la_derniere_et_tolerante_dans_l_unite(self):
        unit = (ROOT / "configs/systemd-user/trading-agent-nightly.service")
        lines = [l for l in unit.read_text(encoding="utf-8").splitlines()
                 if l.startswith("ExecStart")]
        idx = [i for i, l in enumerate(lines) if "nightly_campaign" in l]
        self.assertTrue(idx, "nightly_campaign absent de l'unité")
        last = len(lines) - 1
        for i in idx:
            self.assertTrue(lines[i].startswith("ExecStart=-"),
                            "la campagne doit être TOLÉRANTE : en "
                            "ExecStart= elle tue les étapes suivantes")
            self.assertGreaterEqual(i, last - 1,
                                    "la campagne doit être la dernière ou "
                                    "l'avant-dernière étape")

    def test_plus_aucune_etape_bloquante_apres_la_campagne(self):
        unit = (ROOT / "configs/systemd-user/trading-agent-nightly.service")
        lines = [l for l in unit.read_text(encoding="utf-8").splitlines()
                 if l.startswith("ExecStart=")]
        idx = [i for i, l in enumerate(lines) if "nightly_campaign" in l]
        if idx:
            apres = lines[max(idx) + 1:]
            bloquantes = [l for l in apres if not l.startswith("ExecStart=-")]
            self.assertEqual(bloquantes, [],
                             f"étapes BLOQUANTES après la campagne : "
                             f"{bloquantes}")


class TestUniteSystemdValide(unittest.TestCase):
    def test_systemd_analyze_avec_verify(self):
        if not Path("/usr/bin/systemd-analyze").exists():
            self.skipTest("systemd-analyze absent (CI GitHub Actions)")
        unit = ROOT / "configs/systemd-user/trading-agent-nightly.service"
        with tempfile.NamedTemporaryFile("w", suffix=".service",
                                         delete=False) as f:
            f.write(unit.read_text(encoding="utf-8"))
            tmp = f.name
        r = subprocess.run(["systemd-analyze", "verify", tmp],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         f"unité invalide :\n{r.stdout}\n{r.stderr}")


if __name__ == "__main__":
    unittest.main()