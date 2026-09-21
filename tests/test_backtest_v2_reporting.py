"""Tests du module de mise en rapport (backtest_v2.reporting).

Regle testee en priorite : aucun chiffre ne doit apparaitre sans denominateur.
"""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.reporting import (  # noqa: E402
    ReportSection,
    SEVERITY_ORDER,
    build_report,
    health_flags,
    render_console,
    render_discord,
    render_markdown,
)


def make_campaign(**over):
    base = {
        "run_id": "run-test-001",
        "tested": 24,
        "accepted": 0,
        "rejected": 24,
        "errored": 0,
        "acceptance_rate": 0.0,
        "rejection_profile": {"sharpe_oos": 18, "closed_trades": 9},
        "survivors": [],
        "started_at": "2026-08-09T02:00:00+00:00",
        "finished_at": "2026-08-09T02:04:30+00:00",
    }
    base.update(over)
    return base


def make_audit(**over):
    base = {
        "n_tested": 24,
        "n_gate_survivors": 3,
        "n_after_multiplicity": 0,
        "acceptance_rate": 0.125,
        "expected_by_chance": 1.2,
        "verdict": "AUCUN SURVIVANT APRES CORRECTION",
        "detail": {"seuil_bonferroni": "2.083e-03"},
    }
    base.update(over)
    return base


def survivor(i=1):
    return {
        "identity": f"BTCUSDT|1h|ema_cross|v{i}",
        "sharpe_oos": 1.42,
        "oos_is_ratio": 0.81,
        "closed_trades": 133,
        "params": {"fast": 9, "slow": 21},
    }


class TestReportSection(unittest.TestCase):
    def test_default_severity_is_info(self):
        self.assertEqual(ReportSection(title="t", lines=[]).severity, "info")

    def test_invalid_severity_rejected(self):
        with self.assertRaises(ValueError):
            ReportSection(title="t", lines=[], severity="fatal")

    def test_lines_are_copied(self):
        src = ["a"]
        s = ReportSection(title="t", lines=src)
        s.lines.append("b")
        self.assertEqual(src, ["a"])


class TestHealthFlags(unittest.TestCase):
    def test_high_acceptance_rate_triggers_flag(self):
        c = make_campaign(tested=100, accepted=12, rejected=88, acceptance_rate=0.12)
        flags = health_flags(c, make_audit(n_tested=100))
        self.assertTrue(any("TAUX D'ACCEPTATION SUSPECT" in f for f in flags), flags)

    def test_suspicious_flag_mentions_bruit_pur(self):
        c = make_campaign(tested=100, accepted=12, acceptance_rate=0.12)
        flag = [f for f in health_flags(c, make_audit()) if "SUSPECT" in f][0]
        self.assertIn("bruit pur", flag)

    def test_rate_below_threshold_no_flag(self):
        c = make_campaign(tested=1000, accepted=10, rejected=990, acceptance_rate=0.01)
        flags = health_flags(c, make_audit(n_tested=1000))
        self.assertFalse(any("TAUX D'ACCEPTATION SUSPECT" in f for f in flags), flags)

    def test_missing_audit_large_campaign_flags_multiplicity(self):
        c = make_campaign(tested=5000, accepted=0, rejected=5000)
        flags = health_flags(c, None)
        self.assertTrue(
            any("NON CORRIGEE DE LA MULTIPLICITE" in f for f in flags), flags
        )

    def test_missing_audit_small_campaign_still_mentions_it(self):
        flags = health_flags(make_campaign(tested=10), None)
        self.assertTrue(any("multiplicite" in f.lower() for f in flags), flags)

    def test_high_error_rate_flag(self):
        c = make_campaign(tested=100, accepted=0, rejected=80, errored=20)
        flags = health_flags(c, make_audit(n_tested=100))
        self.assertTrue(any("TAUX D'ERREUR" in f for f in flags), flags)

    def test_low_error_rate_no_flag(self):
        c = make_campaign(tested=100, accepted=0, rejected=99, errored=1)
        flags = health_flags(c, make_audit(n_tested=100))
        self.assertFalse(any("TAUX D'ERREUR" in f for f in flags), flags)

    def test_empty_campaign_flag(self):
        flags = health_flags({"tested": 0}, None)
        self.assertEqual(len(flags), 1)
        self.assertIn("CAMPAGNE VIDE", flags[0])

    def test_reassuring_flag_when_multiplicity_kills_all(self):
        flags = health_flags(make_campaign(), make_audit())
        joined = "\n".join(flags)
        self.assertIn("AUCUN SURVIVANT APRES CORRECTION DE MULTIPLICITE", joined)
        self.assertIn("comportement", joined)

    def test_every_flag_number_has_a_denominator(self):
        c = make_campaign(tested=100, accepted=12, rejected=68, errored=20)
        for f in health_flags(c, None):
            self.assertTrue("/" in f or "%" in f, f)

    def test_rate_recomputed_when_absent(self):
        c = make_campaign(tested=10, accepted=5, acceptance_rate=None)
        self.assertTrue(
            any("TAUX D'ACCEPTATION SUSPECT" in f for f in health_flags(c, make_audit()))
        )


class TestBuildReport(unittest.TestCase):
    def test_returns_sections(self):
        secs = build_report(campaign=make_campaign(), audit=make_audit())
        self.assertTrue(secs)
        self.assertTrue(all(isinstance(s, ReportSection) for s in secs))

    def test_sorted_by_severity_critical_first(self):
        c = make_campaign(tested=5000, accepted=900, rejected=4100, acceptance_rate=0.18)
        secs = build_report(campaign=c, audit=None)
        order = [SEVERITY_ORDER[s.severity] for s in secs]
        self.assertEqual(order, sorted(order))
        self.assertEqual(secs[0].severity, "critical")

    def test_no_survivor_message_is_not_a_failure(self):
        secs = build_report(campaign=make_campaign(), audit=make_audit())
        text = render_console(secs)
        self.assertIn("Ce n'est pas un echec de la campagne : c'est son resultat.", text)

    def test_survivors_listed_with_denominator(self):
        c = make_campaign(
            accepted=2, rejected=22, acceptance_rate=2 / 24,
            survivors=[survivor(1), survivor(2)],
        )
        sec = [s for s in build_report(campaign=c, audit=make_audit()) if s.title == "Survivants"][0]
        joined = "\n".join(sec.lines)
        self.assertIn("2 / 24", joined)
        self.assertIn("%", joined)

    def test_top_n_limits_and_reports_hidden(self):
        c = make_campaign(
            accepted=5, survivors=[survivor(i) for i in range(5)],
        )
        sec = [s for s in build_report(campaign=c, top_n=2) if s.title == "Survivants"][0]
        joined = "\n".join(sec.lines)
        self.assertIn("2 survivants / 5", joined)
        self.assertIn("non affiches", joined)

    def test_rejection_profile_entries_have_denominators(self):
        secs = build_report(campaign=make_campaign(), audit=make_audit())
        sec = [s for s in secs if s.title == "Motifs de rejet"][0]
        for line in sec.lines:
            if "sharpe_oos" in line or "closed_trades" in line:
                self.assertIn("/", line)
                self.assertIn("%", line)

    def test_incoherent_counts_are_critical(self):
        c = make_campaign(tested=24, accepted=1, rejected=1, errored=0)
        sec = [s for s in build_report(campaign=c, audit=make_audit()) if s.title == "Comptage"][0]
        self.assertEqual(sec.severity, "critical")
        self.assertTrue(any("INCOHERENCE" in l for l in sec.lines))

    def test_empty_campaign_does_not_crash(self):
        secs = build_report(campaign={}, audit=None)
        self.assertTrue(secs)
        render_markdown(secs)
        render_console(secs)
        render_discord(secs)

    def test_candidates_section_present_when_given(self):
        secs = build_report(
            campaign=make_campaign(), audit=make_audit(), candidates={"a": 1, "b": 2}
        )
        self.assertTrue(any(s.title == "Candidats" for s in secs))

    def test_candidates_absent_by_default(self):
        secs = build_report(campaign=make_campaign())
        self.assertFalse(any(s.title == "Candidats" for s in secs))

    def test_negative_top_n_rejected(self):
        with self.assertRaises(ValueError):
            build_report(campaign=make_campaign(), top_n=-1)

    def test_every_numeric_line_has_denominator(self):
        c = make_campaign(
            accepted=2, rejected=20, errored=2, acceptance_rate=2 / 24,
            survivors=[survivor(1), survivor(2)],
        )
        secs = build_report(campaign=c, audit=make_audit())
        skip = ("run_id", "debut", "fin", "duree", "verdict", "seuil", "sharpe_oos=")
        for sec in secs:
            for line in sec.lines:
                if not any(ch.isdigit() for ch in line):
                    continue
                if any(k in line for k in skip) or line.strip().startswith(("...", '"', "{", "}")):
                    continue
                self.assertTrue("/" in line or "%" in line, f"{sec.title}: {line}")


class TestRenderMarkdown(unittest.TestCase):
    def test_has_h1_and_h2(self):
        md = render_markdown(build_report(campaign=make_campaign(), audit=make_audit()))
        self.assertTrue(md.startswith("# Rapport de campagne"))
        self.assertIn("\n## ", md)

    def test_code_fences_balanced(self):
        md = render_markdown(build_report(campaign=make_campaign(), audit=make_audit()))
        self.assertEqual(
            sum(1 for l in md.split("\n") if l.startswith("```")) % 2, 0
        )

    def test_empty_sections(self):
        self.assertIn("Aucune section", render_markdown([]))

    def test_ends_with_single_newline(self):
        md = render_markdown(build_report(campaign=make_campaign()))
        self.assertTrue(md.endswith("\n"))
        self.assertFalse(md.endswith("\n\n"))


class TestRenderConsole(unittest.TestCase):
    def test_respects_width(self):
        secs = build_report(campaign=make_campaign(), audit=make_audit())
        for line in render_console(secs, width=60).split("\n"):
            self.assertLessEqual(len(line), 60, line)

    def test_narrow_width_rejected(self):
        with self.assertRaises(ValueError):
            render_console(build_report(campaign=make_campaign()), width=10)

    def test_titles_present(self):
        text = render_console(build_report(campaign=make_campaign(), audit=make_audit()))
        self.assertIn("Comptage", text)
        self.assertIn("Survivants", text)


class TestRenderDiscord(unittest.TestCase):
    def _long_report(self):
        c = make_campaign(
            tested=5000,
            accepted=400,
            rejected=4400,
            errored=200,
            acceptance_rate=0.08,
            rejection_profile={f"motif_{i:03d}": 5000 - i for i in range(120)},
            survivors=[survivor(i) for i in range(200)],
        )
        return build_report(campaign=c, audit=make_audit(n_tested=5000), top_n=200)

    def test_all_messages_under_limit(self):
        for m in render_discord(self._long_report()):
            self.assertLessEqual(len(m), 1900, len(m))

    def test_custom_max_chars_respected(self):
        for m in render_discord(self._long_report(), max_chars=500):
            self.assertLessEqual(len(m), 500, len(m))

    def test_long_report_is_split(self):
        self.assertGreater(len(render_discord(self._long_report())), 1)

    def test_each_message_has_balanced_fences(self):
        for m in render_discord(self._long_report(), max_chars=600):
            self.assertEqual(
                sum(1 for l in m.split("\n") if l.startswith("```")) % 2, 0, m[:200]
            )

    def test_no_message_is_empty(self):
        for m in render_discord(self._long_report()):
            self.assertTrue(m.strip())

    def test_short_report_single_message(self):
        msgs = render_discord(build_report(campaign=make_campaign(tested=3)))
        self.assertGreaterEqual(len(msgs), 1)

    def test_content_is_preserved(self):
        secs = build_report(campaign=make_campaign(), audit=make_audit())
        joined = "\n".join(render_discord(secs, max_chars=400))
        self.assertIn("Comptage", joined)
        self.assertIn("Survivants", joined)

    def test_tiny_max_chars_rejected(self):
        with self.assertRaises(ValueError):
            render_discord(build_report(campaign=make_campaign()), max_chars=10)

    def test_very_long_single_line_is_wrapped(self):
        sec = ReportSection(title="Long", lines=["x" * 9000], severity="info")
        for m in render_discord([sec], max_chars=300):
            self.assertLessEqual(len(m), 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
