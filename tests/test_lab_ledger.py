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
        self.assertEqual(set(pol["budget"]), {"total_experiments", "per_family", "per_strategy", "max_parameter_variants"})
        self.assertTrue(all(isinstance(v, int) and v > 0 for v in pol["budget"].values()))
        entries = L.load(ROOT / "research" / "ledger" / "trials.jsonl", pol["effective"])
        self.assertGreater(len(entries), 0)
        self.assertTrue(all(e.get("verdict") in L.VERDICTS for e in entries))


if __name__ == "__main__":
    unittest.main()
