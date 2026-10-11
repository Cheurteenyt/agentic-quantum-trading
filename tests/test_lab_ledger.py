from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lab_ledger as L  # noqa: E402

NOW = "2026-10-06T10:00:00Z"   # lundi, semaine ISO 41 ; effet de la policy : 2026-10-02
POLICY = ("version: 1\nfrozen_tag: freeze-2026-10-02\nweekly_budget:\n  total_experiments: {t}\n  per_family: {f}\n"
          "  per_strategy: {s}\n  max_parameter_variants: {v}\n  on_exhaustion: STOP\nagent_limits:\n  max_files_modified: 8\n")


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.led, self.pol = d / "t.jsonl", d / "policy.yaml"
        self.policy(20, 5, 3, 12)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def policy(self, t, f, s, v):
        self.pol.write_text(POLICY.format(t=t, f=f, s=s, v=v), encoding="utf-8")

    def run_cli(self, *argv, now=NOW):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = L.main(["--ledger", str(self.led), "--policy", str(self.pol), "--now", now, *argv])
        return code, buf.getvalue()

    def log(self, hyp, verdict="FAIL", fam="f", st="s", date=None, params=()):
        extra = ["--date", date] if date else []
        return self.run_cli("log", "--family", fam, "--strategy", st, "--hypothesis", hyp, "--verdict", verdict,
                            *extra, *(["--params", *params] if params else []))

    def check(self, hyp, fam="f", st="s", params=(), now=NOW):
        return self.run_cli("check", "--family", fam, "--strategy", st, "--hypothesis", hyp,
                            *(["--params", *params] if params else []), now=now)

    def test_selftest_passes(self):
        self.assertEqual(L.main(["selftest"]), L.EXIT_OK)

    def test_empty_ledger_is_go(self):
        self.assertEqual(self.check("x")[0], L.EXIT_OK)

    def test_log_without_date_does_not_crash(self):
        self.assertEqual(self.log("sans date")[0], L.EXIT_OK)
        self.assertEqual(len(L.load(self.led, None)), 1)

    def test_reformulated_duplicate_is_noop_even_under_another_strategy(self):
        self.log("La Majeure Déviante !", st="s1")
        self.assertEqual(self.check("la majeure deviante", st="s1")[0], L.EXIT_DUP)
        self.assertEqual(self.check("la majeure deviante", fam="autre", st="autre")[0], L.EXIT_DUP)

    def test_other_params_is_mutation_not_duplicate(self):
        self.log("hyp", params=("q=90",))
        code, out = self.check("hyp", params=("q=95",))
        self.assertEqual(code, L.EXIT_OK)
        self.assertIn("PARAMETER_MUTATION", out)

    def test_max_parameter_variants(self):
        self.policy(20, 5, 5, 2)
        self.log("hyp", params=("k=1",))
        self.log("hyp", params=("k=2",))
        self.assertEqual(self.check("hyp", params=("k=3",))[0], L.EXIT_STOP)

    def test_family_cap(self):
        for i in range(5):
            self.log(f"h{i}", fam="f1", st=f"s{i}")
        self.assertEqual(self.check("neuve", fam="f1", st="s9")[0], L.EXIT_STOP)

    def test_strategy_cap(self):
        for i in range(3):
            self.log(f"h{i}", fam=f"f{i}", st="s1")
        self.assertEqual(self.check("neuve", fam="f9", st="s1")[0], L.EXIT_STOP)

    def test_total_cap_from_policy_file(self):
        self.policy(2, 5, 3, 12)
        self.log("a", fam="f1", st="s1")
        self.log("b", fam="f2", st="s2")
        self.assertEqual(self.check("c", fam="f3", st="s3")[0], L.EXIT_STOP)

    def test_every_non_prereg_verdict_consumes(self):
        self.policy(3, 5, 3, 12)
        for i, v in enumerate(("NUL", "SOUS_PUISSANT", "INCONCLU")):
            self.log(f"h{i}", verdict=v, fam=f"f{i}", st=f"s{i}")
        self.assertEqual(self.check("neuve", fam="z", st="z")[0], L.EXIT_STOP)

    def test_prereg_does_not_consume(self):
        self.policy(1, 5, 3, 12)
        self.log("prereg", verdict="PREREG")
        self.assertEqual(self.check("autre", fam="g", st="g")[0], L.EXIT_OK)

    def test_entries_before_policy_effect_are_backfill(self):
        self.policy(1, 5, 3, 12)
        self.log("ancienne", date="2026-10-01")
        self.assertEqual(self.check("neuve", fam="g", st="g")[0], L.EXIT_OK)

    def test_iso_week_boundary(self):
        self.policy(1, 5, 3, 12)
        self.log("dimanche", date="2026-10-04")  # semaine 40
        self.assertEqual(self.check("lundi", fam="g", st="g", now="2026-10-05T08:00:00Z")[0], L.EXIT_OK)
        self.assertEqual(self.check("dimanche bis", fam="g", st="g", now="2026-10-04T23:00:00Z")[0], L.EXIT_STOP)

    def test_log_over_budget_is_recorded_anyway(self):
        self.policy(1, 5, 3, 12)
        self.log("a", fam="f1", st="s1")
        code, out = self.log("b", fam="f2", st="s2")
        self.assertEqual(code, L.EXIT_OK)
        self.assertIn("enregistré quand même", out)
        self.assertEqual(len(L.load(self.led, None)), 2)

    def test_legacy_format_is_read(self):
        legacy = {"date": "2026-10-03", "family": "premium", "strategy": "premium_fade_full", "hypothesis": "Audit du claim 87pct",
                  "hypothesis_hash": "4262860ee0820ee6", "verdict": "FAIL", "params": {"cell": "replica"}}
        self.led.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
        code, out = self.check("audit du CLAIM 87pct", fam="premium", st="autre", params=("cell=replica",))
        self.assertEqual(code, L.EXIT_DUP, out)

    def test_sync_state_is_idempotent(self):
        self.log("a")
        state = Path(self.tmp.name) / "STATE.md"
        state.write_text("# STATE\ntexte\n", encoding="utf-8")
        self.run_cli("sync-state", "--state", str(state))
        first = state.read_text(encoding="utf-8")
        self.run_cli("sync-state", "--state", str(state))
        self.assertEqual(first, state.read_text(encoding="utf-8"))
        self.assertIn(L.BEGIN, first)
        self.assertIn("texte", first)

    def test_tstar_reference_values(self):
        self.assertAlmostEqual(L.tstar(1), 1.96, places=2)
        self.assertAlmostEqual(L.tstar(10), 2.81, places=2)
        self.assertAlmostEqual(L.tstar(100), 3.48, places=2)

    def test_real_repo_ledger_and_policy_parse(self):
        pol = L.read_policy(ROOT / "agent" / "policy.yaml")
        self.assertEqual(set(pol["budget"]), {"total_experiments", "per_family",
                                              "per_strategy", "max_parameter_variants",
                                              "prior_trials"})
        self.assertTrue(all(isinstance(v, int) and v > 0 for v in pol["budget"].values()))
        entries = L.load(ROOT / "research" / "ledger" / "trials.jsonl", pol["effective"])
        self.assertGreater(len(entries), 0)
        self.assertTrue(all(e.get("verdict") in L.VERDICTS for e in entries))


class DiscoveryVerdictExigeSaGrandeur(unittest.TestCase):
    """N6 (audit Sonnet 5.5, R2) — un verdict de découverte SANS chiffres est refusé.

    Mesure qui a motivé la règle : au 11/10, les 16 lignes vivantes du ledger sont
    toutes DISCOVERY_FAIL et AUCUNE ne porte `n` ni `er`. Un DISCOVERY_FAIL sans n
    ni moyenne ne dit ni la distance au seuil ni le coût d'équilibre : information
    nulle. Le refus est FAIL-CLOSED (exit erreur), pas un avertissement.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.led, self.pol = d / "t.jsonl", d / "policy.yaml"
        self.pol.write_text(POLICY.format(t=20, f=5, s=3, v=12), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = L.main(["--ledger", str(self.led), "--policy", str(self.pol),
                           "--now", NOW, *argv])
        return code, buf.getvalue()

    def disc(self, hyp, verdict="DISCOVERY_FAIL", *, n=None, er=None, backfill=False, st="s"):
        argv = ["log", "--family", "f", "--strategy", st, "--hypothesis", hyp,
                "--verdict", verdict, "--mode", "discovery"]
        if n is not None:
            argv += ["--n", str(n)]
        if er is not None:
            argv += ["--er", str(er)]
        if backfill:
            argv.append("--backfill")
        return self.run_cli(*argv)

    def test_discovery_fail_sans_chiffres_est_refuse(self):
        code, out = self.disc("h")
        self.assertEqual(code, L.EXIT_ERR)
        self.assertIn("REFUS", out)
        self.assertEqual(len(L.load(self.led, None)), 0, "rien ne doit être écrit")

    def test_discovery_fail_avec_n_et_er_est_accepte(self):
        code, _ = self.disc("h", n=400, er=-0.02)
        self.assertEqual(code, L.EXIT_OK)
        entries = L.load(self.led, None)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["n"], 400)
        self.assertEqual(entries[0]["er"], -0.02)

    def test_discovery_pass_sans_chiffres_est_refuse(self):
        # les DEUX verdicts DISCOVERY_* sont couverts, pas seulement FAIL
        self.assertEqual(self.disc("h", verdict="DISCOVERY_PASS")[0], L.EXIT_ERR)

    def test_n_nul_ou_negatif_est_refuse(self):
        # n=0 (ou absent) ne compte pas comme une mesure
        self.assertEqual(self.disc("h", n=0, er=0.1)[0], L.EXIT_ERR)
        self.assertEqual(self.disc("h2", n=-5, er=0.1)[0], L.EXIT_ERR)

    def test_er_seul_sans_n_est_refuse(self):
        # il faut LES DEUX grandeurs : er seul reste non exploitable
        self.assertEqual(self.disc("h", er=0.1)[0], L.EXIT_ERR)

    def test_n_seul_sans_er_est_refuse(self):
        # symétrique : n seul (le cas le plus probable en pratique — on logue
        # le compte de trades mais pas l'effet) doit être refusé aussi
        self.assertEqual(self.disc("h", n=400)[0], L.EXIT_ERR)

    def test_prereg_reste_exempte(self):
        # PREREG n'affirme aucun résultat : pas de grandeur exigée
        code, _ = self.run_cli("log", "--family", "f", "--strategy", "s", "--hypothesis",
                               "h", "--verdict", "PREREG", "--mode", "discovery")
        self.assertEqual(code, L.EXIT_OK)

    def test_backfill_reste_la_porte_de_sortie_historique(self):
        # les entrées antérieures à la règle passent par --backfill
        code, _ = self.disc("historique", backfill=True)
        self.assertEqual(code, L.EXIT_OK)
        self.assertEqual(len(L.load(self.led, None)), 1)

    def test_les_verdicts_de_confirmation_ne_sont_pas_concernes(self):
        # périmètre volontairement limité à DISCOVERY_* (le run scellé porte les
        # chiffres pour la confirmation, cf. research_integrity I007)
        code, _ = self.run_cli("log", "--family", "f", "--strategy", "s",
                               "--hypothesis", "h", "--verdict", "FAIL")
        self.assertEqual(code, L.EXIT_OK)

    def test_le_ledger_du_depot_porte_encore_des_discovery_sans_chiffres(self):
        """Verrou de MÉMOIRE : le passif est encore là (0 ligne DISCOVERY_* avec n).

        Ce test documente l'état mesuré — il passe tant que le passif existe.
        Le jour où quelqu'un backfille les 16 lignes, il rougira et il faudra le
        retourner : c'est volontaire, pour que la dette ne s'oublie pas.
        """
        pol = L.read_policy(ROOT / "agent" / "policy.yaml")
        entries = L.load(ROOT / "research" / "ledger" / "trials.jsonl", pol["effective"])
        disc = [e for e in entries if e.get("verdict") in L.DISCOVERY_VERDICTS]
        sans_grandeur = [e for e in disc if e.get("n") is None and e.get("er") is None]
        self.assertGreater(len(disc), 0, "il doit rester des DISCOVERY_* au ledger")
        # le passif mesuré le 11/10 : toutes sans grandeur
        self.assertGreater(len(sans_grandeur), 0,
                           "si ce chiffre tombe à 0, les lignes ont été backfillées : "
                           "retourner ce test pour l'exiger désormais")


if __name__ == "__main__":
    unittest.main()
