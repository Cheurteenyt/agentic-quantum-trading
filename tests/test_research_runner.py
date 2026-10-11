"""Tests du research_runner (Research OS PR 6 + porte conforme v6).

Le parcours complet sur des fixtures : une spec YAML (masque causal sur une
feature connue), discovery sur la vue TRAIN, confirm sous protocole (mode
guard, fenêtres gelées, seuils gelés, stress de coûts, slot consommé), les
artefacts (spec_sha, manifest, summary), et la violation de scope si
discovery tente de sortir du TRAIN.

    python tests/test_research_runner.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import research_runner as rr  # noqa: E402
from scripts.research_os import DataScope, ScopeViolation  # noqa: E402

H_MS = 3_600_000


def _db(path, n=300, kill_pct=-3.0, from_bar=100):
    """Des barres 1h déterministes : plat, puis un crash de `kill_pct` %/barre
    pendant 20 barres à partir de `from_bar` (un event study doit le voir)."""
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE klines (symbol TEXT, interval TEXT, open_time INTEGER,
        open REAL, high REAL, low REAL, close REAL, volume REAL);
    CREATE TABLE funding_history (symbol TEXT, funding_time INTEGER, rate REAL);
    """)
    price = 100.0
    for i in range(n):
        o = price
        c = price * (1 + kill_pct / 100.0 if from_bar <= i < from_bar + 20 else 1.0)
        hi = max(o, c) * 1.001
        lo = min(o, c) * 0.999
        con.execute("INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
                    (i * H_MS, o, hi, lo, c))
        if i % 8 == 0:   # un print de funding toutes les 8 barres (couverture)
            con.execute("INSERT INTO funding_history VALUES "
                        "('BTCUSDT', ?, 0.0001)", (i * H_MS + H_MS,))
        price = c
    con.commit()
    return con


def _spec(tmp, db, train_end_bar=150, mode="confirmation"):
    spec = {
        "id": "EXP-test-001",
        "domain": "aster",
        "family": "volatility_exhaustion",
        "strategy": "runner-test",
        "hypothesis": "un crash aigu prolongé continue de baisser à court terme",
        "data": {"symbols": ["BTCUSDT"], "timeframe": "1h",
                 "train_start": 0, "train_end": train_end_bar * H_MS,
                 "validation_start": train_end_bar * H_MS,
                 "validation_end": 300 * H_MS},
        "signal": {"feature": "ret_1h", "op": "<=", "quantile": 0.10, "side": -1},
        "horizons": [6],
        "cost_pct": 0.0,
        "criteria": {"min_n": 5, "min_mean": -100.0},
        "mode": mode,
    }
    sp = Path(tmp) / "EXP-test-001.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    return sp, spec


# le mini-protocole des tests : les fenêtres gelées de la FIXTURE (l'epoch
# 1970 des barres synthétiques) — le MÉCANISME est testé ici, les VALEURS
# viennent d'active.yaml en production.
PROTO_MINI = {
    "protocol_id": "protocol-v2",
    "frozen_windows": [{"start": "1970-01", "end": "1970-02"}],
    "embargo_hours": 0,
    "windows_pass_required": 1,
    "cost_stress_multiplier": 1.5,
    "degradation_max_pct": 70,
    "max_window_loss_pct": 15,
}


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.db"
        self.con = _db(self.db)
        self.spec_path, self.spec = _spec(self.tmp.name, self.db)
        self._runs_backup = rr.RUNS
        rr.RUNS = Path(self.tmp.name) / "runs"

    def tearDown(self):
        rr.RUNS = self._runs_backup
        self.con.close()
        self.tmp.cleanup()

    def test_discovery_produit_verdict_et_artefacts(self):
        res = rr.run_discovery(self.spec, db_path=self.db)
        self.assertIn(res["verdict"], ("DISCOVERY_PASS", "DISCOVERY_FAIL"))
        self.assertGreater(res["n"], 0)
        self.assertIn("label_hash", res)
        # v6 : la découverte gèle ses seuils (la confirmation les réutilisera)
        self.assertIn("frozen_thresholds", res)
        self.assertIn("BTCUSDT", res["frozen_thresholds"])
        rdir = rr.write_artifacts(self.spec["id"], self.spec, res, "discovery",
                                  db_path=self.db)
        self.assertTrue((rdir / "manifest.json").exists())
        self.assertTrue((rdir / "spec.json").exists())
        s = json.loads((rdir / "summary_discovery.json").read_text(encoding="utf-8"))
        self.assertEqual(s["spec_sha"], rr.spec_sha(self.spec))
        self.assertIn("frozen_thresholds", s)

    def test_le_seuil_expanding_est_causal(self):
        """Un trade ancien ne connaît pas la distribution future : le seuil
        à la barre i ne dépend que des barres ≤ i (leçon C10)."""
        fvals = np.full(300, 1.0)
        fvals[100:120] = -5.0          # le crash
        thr = rr.expanding_threshold(fvals, 0.10)
        self.assertTrue(np.isnan(thr[:50]).all())
        # à la barre 200 (après le crash), le seuil intègre les -5 :
        self.assertLess(thr[200], thr[60])

    def test_confirm_consomme_un_slot_et_juge_la_validation(self):
        res_d = rr.run_discovery(self.spec, db_path=self.db)
        rr.write_artifacts(self.spec["id"], self.spec, res_d, "discovery",
                           db_path=self.db)
        res2 = rr.run_confirmation(self.spec, db_path=self.db,
                                   protocol=PROTO_MINI)
        self.assertEqual(res2["slots_consumed"], 1)
        self.assertIn(res2["verdict"], ("CONFIRMED", "REJECTED"))
        self.assertEqual(res2["validation_window"][0], 150 * H_MS)
        # v6 : l'évaluation par fenêtre gelée est dans le verdict
        self.assertIn("per_window", res2)
        self.assertEqual(res2["windows_required"], 1)
        self.assertIn("train_mean", res2)
        self.assertIn("stress_mean", res2)

    def test_confirm_sans_artefact_est_bloque(self):
        """v8 (GLM 5.3 №17) : sans artefact de découverte (seuils gelés), la
        confirmation est BLOQUÉE (0 slot) — le re-calcul train n'est plus un
        fallback silencieux du chemin officiel."""
        rr.run_discovery(self.spec, db_path=self.db)   # pas de write_artifacts
        res = rr.run_confirmation(self.spec, db_path=self.db,
                                  protocol=PROTO_MINI)
        self.assertEqual(res["verdict"], "CONFIRMATION_BLOCKED")
        self.assertEqual(res["slots_consumed"], 0)

    def test_confirm_refuse_une_spec_discovery(self):
        """v6 : la garde MODE — une spec déclarée discovery ne passe jamais
        la porte de confirmation (0 slot, pas d'étude)."""
        _, spec_d = _spec(self.tmp.name, self.db, mode="discovery")
        res = rr.run_confirmation(spec_d, db_path=self.db,
                                  protocol=PROTO_MINI)
        self.assertEqual(res["verdict"], "MODE_MISMATCH")
        self.assertEqual(res["slots_consumed"], 0)

    def test_confirm_refuse_une_validation_hors_fenetres(self):
        """v6 : active.yaml est l'autorité — une validation qui n'intersecte
        pas les fenêtres gelées est refusée (0 slot)."""
        spec = dict(self.spec)
        spec["data"] = dict(self.spec["data"])
        spec["data"]["validation_start"] = 800 * H_MS   # > fin de fenêtre mini
        spec["data"]["validation_end"] = 900 * H_MS
        res = rr.run_confirmation(spec, db_path=self.db, protocol=PROTO_MINI)
        self.assertEqual(res["verdict"], "WINDOW_MISMATCH")
        self.assertEqual(res["slots_consumed"], 0)

    def test_confirm_ne_recalibre_pas_sur_la_validation(self):
        """v6 : les seuils gelés — la confirmation utilise la valeur de
        l'expanding quantile à la fin du TRAIN (l'artefact fait foi), même
        si la distribution de la validation la justifierait autrement."""
        res_d = rr.run_discovery(self.spec, db_path=self.db)
        rr.write_artifacts(self.spec["id"], self.spec, res_d, "discovery",
                           db_path=self.db)
        sfile = rr.RUNS / self.spec["id"] / "summary_discovery.json"
        self.assertTrue(sfile.exists())
        s = json.loads(sfile.read_text(encoding="utf-8"))
        frozen = s["frozen_thresholds"]["BTCUSDT"]
        res = rr.run_confirmation(self.spec, db_path=self.db,
                                  protocol=PROTO_MINI)
        self.assertEqual(res["frozen_src"], "discovery_artifact")
        # le seuil gelé est un nombre fini (le train compte 150 barres)
        self.assertTrue(np.isfinite(frozen[0]))

    def test_agregat_pondere_par_n(self):
        """v6 : la moyenne agrégée est pondérée par n — un symbole à 10
        events ne pèse pas autant qu'un symbole à 1 000."""
        per_symbol = {"A@6h": {"n": 10, "mean": 2.0},
                      "B@6h": {"n": 1000, "mean": 0.0}}
        _, mean = rr._aggregate(per_symbol, min_n=5)
        self.assertLess(mean, 0.02)      # ≈ 0.0198, pas 1.0 (moyenne simple)
        self.assertEqual(mean, (2.0 * 10 + 0.0 * 1000) / 1010)

    def test_funding_absent_est_nan_pas_zero(self):
        """v6 : un symbole SANS funding_history → fund_H = NaN (l'inconnu),
        pas 0.0 ; l'event study rapporte fund_cov = 0."""
        self.con.execute("DELETE FROM funding_history")
        self.con.commit()
        from scripts.label_matrix import build_matrix, event_study
        _, matrix = build_matrix(["BTCUSDT"], (6,), db_path=self.db,
                                 use_cache=False)
        cols = matrix["BTCUSDT"]
        self.assertTrue(np.isnan(cols["fund_6"]).all())
        mask = np.isfinite(cols["ret_6"])
        st = event_study(cols, mask, 6, side=-1, cost_pct=0.0)
        self.assertEqual(st["fund_cov"], 0.0)

    def test_discovery_ne_voit_jamais_la_validation(self):
        """La vue discovery borne les requêtes au TRAIN — sortir = violation."""
        scope = DataScope("EXP", 0, 150 * H_MS, 150 * H_MS, 300 * H_MS)
        v = scope.discovery_view()
        with self.assertRaises(ScopeViolation):
            v.assert_range(0, 200 * H_MS)

    def test_preflight_failed_zero_slot(self):
        """Un schéma cassé (la leçon open_time) → PREFLIGHT_FAILED, 0 slot."""
        self.con.executescript("DROP TABLE klines; CREATE TABLE klines (ts INTEGER);")
        self.con.commit()
        res = rr.run_confirmation(self.spec, db_path=self.db,
                                  protocol=PROTO_MINI)
        self.assertEqual(res["verdict"], "PREFLIGHT_FAILED")
        self.assertEqual(res["slots_consumed"], 0)


    def test_range_pct_close_zero_est_nan_pas_inf(self):
        """BUG fuzz 2026-10-10 : range_pct = (h-l)/c. Un close à 0 ou négatif
        (bougie pourrie) donnait inf — et inf passe le sens `>` d'un masque
        (inf > X == True), comptant une barre morte comme signal valide. Fix :
        c<=0 -> NaN avant la division ; NaN est rejeté par les DEUX sens de
        comparaison (nan < X et nan > X sont False), comme fund_last.
        Données prod propres (0 close=0) : défense, pas bug actif."""
        H_MS = 3_600_000
        # insérer une barre avec close=0 parmi des barres saines
        self.con.execute(
            "INSERT INTO klines VALUES ('BTCUSDT','1h',?,?,?,?,?,1.0)",
            (500 * H_MS, 100.0, 105.0, 95.0, 0.0))  # close = 0 !
        self.con.commit()
        feats = rr.compute_features(self.con, "BTCUSDT", db_path=self.db)
        rp = feats["range_pct"]
        # la barre pourrie (close=0) doit être NaN, JAMAIS inf
        self.assertFalse(np.isinf(rp).any(),
                         "un close<=0 ne doit JAMAIS produire un range_pct=inf")
        # et la barre saine doit garder sa valeur (pas de régression)
        barre_saine = rp[0]
        self.assertTrue(np.isfinite(barre_saine),
                        "une barre saine doit garder un range_pct fini")


class LesGrandeursVontAuLedger(unittest.TestCase):
    """N6 (audit Sonnet 5.5, R2) — le défaut RACINE : `_log_ledger` JETAIT les
    grandeurs.

    Mesure qui a motivé le test : au 11/10 le worker calculait `n` et `mean`,
    les AFFICHAIT (« n 5 · mean 0.100 »), puis `_log_ledger` construisait sa
    commande sans jamais passer --n ni --er. D'où 16 lignes DISCOVERY_* muettes.
    Ce test capture la commande réellement construite et exige que les trois
    grandeurs y soient — il rougit si on les retire.
    """

    def _commande(self, **kw):
        captured = {}

        class _Faux:
            returncode = 0
            stdout = stderr = ""

        def _fake_run(argv, *a, **k):
            captured["argv"] = argv
            return _Faux()

        orig = rr.subprocess.run
        rr.subprocess.run = _fake_run
        try:
            rr._log_ledger({"family": "f", "strategy": "s", "hypothesis": "h"},
                           "DISCOVERY_FAIL", "discovery", "ref",
                           snapshot="snap", fail_closed=True, **kw)
        finally:
            rr.subprocess.run = orig
        return captured["argv"]

    def test_n_er_se_sont_transmis_au_cli(self):
        argv = self._commande(n=400, er=-0.02, se=0.01)
        self.assertIn("--n", argv)
        self.assertEqual(argv[argv.index("--n") + 1], "400")
        self.assertIn("--er", argv)
        self.assertEqual(argv[argv.index("--er") + 1], "-0.02")
        self.assertIn("--se", argv)
        self.assertEqual(argv[argv.index("--se") + 1], "0.01")

    def test_sans_grandeur_aucun_flag_n_est_ajoute(self):
        # ne pas passer de valeur ne doit PAS fabriquer un --n orphelin
        argv = self._commande()
        self.assertNotIn("--n", argv)
        self.assertNotIn("--er", argv)


if __name__ == "__main__":
    unittest.main()
