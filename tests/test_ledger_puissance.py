#!/usr/bin/env python3
"""N6 — chaque verdict VIVANT du ledger doit porter un n lisible dans son run.

La règle fondatrice du dépôt est « N ≥ 10 » pour qu'un verdict compte
(README, Pre-registered rules). Mesure au HEAD : les 16 entrées vivantes
portaient 0 `n` dans le ledger — le N de multiplicité de `lab_ledger`
comptait des LIGNES, pas des observations. Et 2 verdicts (L96, L97)
pointaient vers `reports/...` et `scripts/studies/...` : pas des runs, donc
aucune mesure retrouvable nulle part.

Ces tests verrouillent :
  1. une entrée vivante dont le run porte un n >= 10 passe ;
  2. un run au summary SANS n est signalé NO_N (pas un « 0 » silencieux) ;
  3. un run ABSENT (ref orpheline) est signalé NO_RUN — fail-closed ;
  4. un n < 10 est signalé SOUS_PUISSANT (le verdict ne tient pas) ;
  5. une entrée `superseded` n'est PAS jugée (travail clos, pas un défaut) ;
  6. un PREREG n'est pas jugé (intention, pas encore de mesure) ;
  7. le DERNIER attempt fait foi (run re-mesuré porte son n à jour).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ledger_puissance as LP  # noqa: E402


class _Fixture:
    """Un ledger minimal + un arbre de runs, en temporaire."""

    def __init__(self, entries, runs):
        # entries: liste de dict (hypothesis, verdict, ref, superseded?, mode?)
        # runs: {run_id: {"n": int|None, "attempts": int, "summary_kind": str}}
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runs = self.root / "runs"
        self.runs.mkdir()
        self.ledger = self.root / "trials.jsonl"

        for rid, cfg in runs.items():
            d = self.runs / rid
            kind = cfg.get("summary_kind", "discovery")
            # le dernier attempt porte le summary (et le run racine aussi,
            # comme la vraie disposition)
            n_att = cfg.get("attempts", 1)
            for a in range(1, n_att + 1):
                ad = d / "attempts" / f"{a:03d}"
                ad.mkdir(parents=True)
                payload = {"verdict": "DISCOVERY_FAIL"}
                if cfg.get("n") is not None:
                    payload["n"] = cfg["n"]
                (ad / f"summary_{kind}.json").write_text(
                    json.dumps(payload), encoding="utf-8")
            # copie au dernier attempt à la racine (disposition réelle)
            payload = {"verdict": "DISCOVERY_FAIL"}
            if cfg.get("n") is not None:
                payload["n"] = cfg["n"]
            (d / f"summary_{kind}.json").write_text(
                json.dumps(payload), encoding="utf-8")

        lignes = []
        for e in entries:
            lignes.append(json.dumps({
                "date": "2026-10-05",
                "hypothesis": e["hypothesis"],
                "hypothesis_hash": e["hypothesis"],
                "family": "f", "strategy": "s",
                "verdict": e["verdict"],
                "ref": e.get("ref"),
                **({"superseded": "PR-143"} if e.get("superseded") else {}),
                **({"mode": "prereg"} if e.get("prereg") else {}),
            }, ensure_ascii=False))
        self.ledger.write_text("\n".join(lignes) + "\n", encoding="utf-8")

    def problemes(self):
        return LP.audit(ledger=self.ledger, runs_dir=self.runs)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.tmp.cleanup()


class TestPuissancePortee(unittest.TestCase):

    def _fixture_ref(self, f, rid):
        return str(f.runs / rid / "report.md")

    def _ecrit(self, f, **champs):
        base = {"date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s"}
        base.update(champs)
        f.ledger.write_text(json.dumps(base, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    def test_n_lu_dans_le_run_passe(self):
        with _Fixture([], {"EXP-a": {"n": 8678}}) as f:
            # ajoute l'entrée ledger APRÈS coup pour avoir le vrai ref
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "DISCOVERY_FAIL",
                "ref": self._fixture_ref(f, "EXP-a")}) + "\n", encoding="utf-8")
            pb = f.problemes()
            self.assertEqual(pb, [], "un run portant n>=10 doit passer")

    def test_run_sans_n_est_signale(self):
        with _Fixture([], {"EXP-b": {"n": None}}) as f:
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "DISCOVERY_FAIL",
                "ref": self._fixture_ref(f, "EXP-b")}) + "\n", encoding="utf-8")
            genres = [p["kind"] for p in f.problemes()]
            self.assertIn("NO_N", genres,
                          "un summary sans n doit être signalé, pas avalé "
                          "comme un 0 (fail-closed)")

    def test_run_absent_est_signale(self):
        with _Fixture([], {"EXP-c": {"n": 100}}) as f:
            # ref vers un run qui n'existe pas
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "DISCOVERY_FAIL",
                "ref": self._fixture_ref(f, "EXP-ABSENT")}) + "\n",
                encoding="utf-8")
            genres = [p["kind"] for p in f.problemes()]
            self.assertIn("NO_RUN", genres,
                          "un verdict dont le run est introuvable est un "
                          "défaut : sa mesure n'existe nulle part")

    def test_n_sous_seuil_est_signale(self):
        with _Fixture([], {"EXP-d": {"n": 4}}) as f:
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "DISCOVERY_FAIL",
                "ref": self._fixture_ref(f, "EXP-d")}) + "\n", encoding="utf-8")
            genres = [p["kind"] for p in f.problemes()]
            self.assertIn("SOUS_PUISSANT", genres,
                          "un n < 10 ne peut pas tenir un verdict")

    def test_superseded_nest_pas_juge(self):
        with _Fixture([], {"EXP-e": {"n": None}}) as f:
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "PASS",
                "superseded": "PR-143",
                "ref": self._fixture_ref(f, "EXP-e")}) + "\n", encoding="utf-8")
            self.assertEqual(f.problemes(), [],
                             "une ligne superseded est hors preuve : la "
                             "juger ici rendrait l'oracle rouge en "
                             "permanence sur du travail clos")

    def test_prereg_nest_pas_juge(self):
        with _Fixture([], {}) as f:
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "PREREG",
                "ref": None}) + "\n", encoding="utf-8")
            self.assertEqual(f.problemes(), [],
                             "un PREREG est une intention, pas une mesure "
                             "manquante")

    def test_dernier_attempt_fait_foi(self):
        """Un run re-mesuré porte son n à jour au DERNIER attempt."""
        with _Fixture([], {"EXP-f": {"n": 500, "attempts": 3}}) as f:
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "DISCOVERY_FAIL",
                "ref": self._fixture_ref(f, "EXP-f")}) + "\n", encoding="utf-8")
            self.assertEqual(f.problemes(), [],
                             "le n du dernier attempt doit être lu")

    def test_degression_explicite_dispense_et_reste_visible(self):
        """Un champ `n_degression` dispense du contrôle (CI verte) SANS
        masquer : le défaut reste écrit dans le ledger. C'est le pattern
        `# deep-audit:ignore` — une dérogation documentée, pas un silence."""
        with _Fixture([], {"EXP-g": {"n": None}}) as f:
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "DISCOVERY_FAIL",
                "ref": self._fixture_ref(f, "EXP-g"),
                "n_degression": "mesure perdue sans relancer le script"})
                + "\n", encoding="utf-8")
            self.assertEqual(f.problemes(), [],
                             "une dégression explicite dispense du contrôle")
            # mais elle reste LISIBLE dans le ledger
            e = json.loads(f.ledger.read_text().strip())
            self.assertIn("n_degression", e,
                          "la dérogation doit rester documentée, pas effacée")

    def test_ref_manuel_hors_runs_est_signale(self):
        """Un ref vers reports/ ou scripts/ (pas un run) est un défaut :
        le n n'est retrouvable nulle part par la machine. Bug fondateur
        de L96/L97 corrigé en pointant ref vers le run réel."""
        with _Fixture([], {}) as f:
            (f.ledger).write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": "h", "hypothesis_hash": "h",
                "family": "f", "strategy": "s", "verdict": "DISCOVERY_FAIL",
                "ref": "reports/un-rapport.md"}) + "\n", encoding="utf-8")
            genres = [p["kind"] for p in f.problemes()]
            self.assertIn("NO_RUN", genres,
                          "un ref qui ne pointe vers aucun run = n perdu")


if __name__ == "__main__":
    unittest.main()


class TestPiegeVerrou(unittest.TestCase):
    def test_doit_echouer_pour_prouver_le_verrou(self):
        self.assertEqual(1, 2, "PIÈGE: ce test doit échouer pour tester le gate")
