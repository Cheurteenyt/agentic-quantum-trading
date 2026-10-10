#!/usr/bin/env python3
"""E5 — vélocité de la recherche : les métriques doivent refléter le ledger
VIVANT, pas l'historique invalidé.

Le fait dur de la revue (2026-10-10) : 657 commits, 0 candidat, et AUCUN
indicateur de productivité. Ce test verrouille la métrique : elle compte les
entrées NON-superseded (une entrée superseded est hors preuve — s'en créditer
serait compter du travail invalidé), et distingue « tranchée » (un résultat)
de « candidat » (le vrai produit).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.research_velocity as RV  # noqa: E402


class TestVelocityMetriques(unittest.TestCase):

    def _ecrit(self, tmp: Path, entrees: list[dict]) -> Path:
        p = tmp / "trials.jsonl"
        p.write_text("\n".join(json.dumps(e, ensure_ascii=False)
                               for e in entrees) + "\n", encoding="utf-8")
        return p

    def test_compte_que_les_vivants(self):
        """Une entrée superseded NE compte PAS comme productivité."""
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ecrit(Path(d), [
                {"date": "2026-10-06", "verdict": "DISCOVERY_FAIL"},
                {"date": "2026-10-06", "verdict": "PASS", "superseded": "PR-143"},
            ])
            import unittest.mock as m
            with m.patch.object(RV, "LEDGER", ledger):
                m_ = RV.metriques(RV.charger())
            self.assertEqual(m_["total_vivant"], 1,
                             "la PASS superseded ne doit PAS compter")
            self.assertEqual(m_["cette_semaine"]["candidats"], 0,
                             "un candidat superseded n'est pas un candidat")

    def test_fail_est_un_resultat_pas_zero(self):
        """Un DISCOVERY_FAIL est une hypothèse tranchée (résultat), pas un vide."""
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ecrit(Path(d), [
                {"date": "2026-10-06", "verdict": "DISCOVERY_FAIL"},
            ])
            import unittest.mock as m
            with m.patch.object(RV, "LEDGER", ledger):
                mm = RV.metriques(RV.charger())
            cs = mm["cette_semaine"]
            self.assertEqual(cs["lots"], 1)
            self.assertEqual(cs["tranchees"], 1,
                             "un FAIL = 1 hypothèse tranchée (pas 0)")
            self.assertEqual(cs["candidats"], 0,
                             "un FAIL n'est PAS un candidat")

    def test_candidat_positif_compte(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ecrit(Path(d), [
                {"date": "2026-10-06", "verdict": "PASS"},
            ])
            import unittest.mock as m
            with m.patch.object(RV, "LEDGER", ledger):
                mm = RV.metriques(RV.charger())
            self.assertEqual(mm["cette_semaine"]["candidats"], 1)

    def test_semaine_courante_est_la_plus_recente(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ecrit(Path(d), [
                {"date": "2026-09-28", "verdict": "FAIL"},   # semaine précédente
                {"date": "2026-10-06", "verdict": "FAIL"},   # semaine courante
            ])
            import unittest.mock as m
            with m.patch.object(RV, "LEDGER", ledger):
                mm = RV.metriques(RV.charger())
            self.assertEqual(mm["semaine_courante"], "2026-W41")
            self.assertEqual(mm["cette_semaine"]["lots"], 1,
                             "seule la semaine courante compte dans 'cette_semaine'")

    def test_ledger_reel_zero_lot_visible(self):
        """Le ledger RÉEL du dépôt : la métrique doit tourner sans planter et
        refléter les 16 vivants (toutes DISCOVERY_FAIL)."""
        m_ = RV.metriques(RV.charger())
        self.assertEqual(m_["total_vivant"], 16)
        # toutes les vivantes sont des échecs -> 0 candidat, c'est le signal
        self.assertEqual(m_["cette_semaine"]["candidats"], 0)


class TestHypothesesEnRetard(unittest.TestCase):
    """P5 (revue Sonnet 5.5) : les hypothèses pré-enregistrées sans verdict
    vivant doivent être MESURÉES (le retard invisible). Jointure exacte par
    `stratégie :` du .md ↔ champ `strategy` du ledger. On NE devine JAMAIS
    une correspondance (une hypothèse sans `stratégie :` est non-joignable)."""

    def _ecrit_ledger(self, tmp: Path, entrees: list[dict]) -> Path:
        p = tmp / "trials.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in entrees) + "\n",
                     encoding="utf-8")
        return p

    def _ecrit_hyp(self, tmp: Path, nom: str, strategie: str | None) -> Path:
        d = tmp / "hypotheses"
        d.mkdir(exist_ok=True)
        ligne = (f"stratégie : {strategie}\n" if strategie
                 else "Mécanisme : pas de stratégie déclarée ici.\n")
        f = d / f"{nom}.md"
        f.write_text(f"# {nom}\n{ligne}", encoding="utf-8")
        return f

    def _run(self, tmp: Path, entrees: list[dict], hyps: list[tuple]) -> dict:
        import unittest.mock as m
        ledger = self._ecrit_ledger(tmp, entrees)
        d = tmp / "hypotheses"
        d.mkdir(exist_ok=True)
        for nom, strat in hyps:
            self._ecrit_hyp(tmp, nom, strat)
        with m.patch.object(RV, "LEDGER", ledger), \
             m.patch.object(RV, "HYPOTHESES", d):
            return RV.hypotheses_en_retard(RV.charger())

    def test_jamais_tranchee_est_en_retard(self):
        """Hypothèse avec stratégie déclarée, AUCUN verdict au ledger."""
        with tempfile.TemporaryDirectory() as d:
            r = self._run(Path(d), [], [("h-neuve", "strat_neuve")])
        etats = {x["hypothese"]: x["etat"] for x in r["rapport"]}
        self.assertEqual(etats["h-neuve"], "jamais")
        self.assertEqual(r["n_en_retard"], 1)

    def test_tranchee_vivante_pas_en_retard(self):
        """Verdict VIVANT -> l'hypothèse est tranchée, PAS en retard."""
        with tempfile.TemporaryDirectory() as d:
            r = self._run(Path(d),
                          [{"strategy": "strat_ok", "verdict": "FAIL"}],
                          [("h-ok", "strat_ok")])
        self.assertEqual(r["rapport"][0]["etat"], "tranchee")
        self.assertEqual(r["n_en_retard"], 0,
                         "un FAIL vivant = tranchée, ce n'est PAS du retard")

    def test_superseded_only_est_en_retard(self):
        """Un verdict SUPERSEDED ne compte pas comme vivant -> en retard."""
        with tempfile.TemporaryDirectory() as d:
            r = self._run(Path(d),
                          [{"strategy": "s", "verdict": "PASS",
                            "superseded": "PR-143"}],
                          [("h-sup", "s")])
        self.assertEqual(r["rapport"][0]["etat"], "superseded_only")
        self.assertEqual(r["n_en_retard"], 1,
                         "un PASS superseded ne dispense pas du retard")

    def test_sans_strategie_est_non_joignable_jamais_devine(self):
        """Pas de `stratégie :` -> non joignable. On NE devine PAS la
        correspondance (doctrine : jamais fabriquer de donnée)."""
        with tempfile.TemporaryDirectory() as d:
            r = self._run(Path(d), [], [("h-muette", None)])
        self.assertEqual(r["rapport"][0]["etat"], "non_joignable")
        self.assertEqual(r["rapport"][0]["strategie"], None)
        self.assertEqual(r["n_en_retard"], 0)
        self.assertEqual(r["n_non_joignable"], 1)

    def test_gabarit_underscore_ignore(self):
        """_TEMPLATE.md n'est pas une hypothèse réelle -> ignoré."""
        with tempfile.TemporaryDirectory() as d:
            r = self._run(Path(d), [], [("_TEMPLATE", "<s>")])
        self.assertEqual(r["rapport"], [],
                         "le gabarit ne doit pas apparaître")

    def test_ledger_reel_mesure_le_retard(self):
        """Le dépôt RÉEL : il reste des hypothèses non tranchées (fait mesuré
        par la revue). Si le ledger rattrape, ce test passe à >=0 — c'est le
        but : voir le retard baisser. La jointure ne doit JAMAIS inventer."""
        r = RV.hypotheses_en_retard(RV.charger())
        self.assertGreaterEqual(r["n_en_retard"], 1,
                                "il reste des hypothèses non tranchées")
        for x in r["rapport"]:
            if x["etat"] != "non_joignable":
                self.assertIsNotNone(x["strategie"])


if __name__ == "__main__":
    unittest.main()
