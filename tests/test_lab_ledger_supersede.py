"""N5 (audit Sonnet 5.5) — les verdicts antérieurs à une correction de
causalité ne doivent plus compter comme preuve.

PR-143 (2026-10-05) a corrigé LE P0 look-ahead : « tous les résultats
précédents sont invalidés et re-mesurés ». Or le ledger gardait 81
entrées pré-PR-143 (dont 25 PASS + 23 DISCOVERY_PASS) sans aucun champ
`superseded` — elles comptaient encore dans le statut, le N de
multiplicité (donc le seuil de Bonferroni) et le budget.

Ces tests verrouillent :
  1. `supersede` marque STRICTEMENT les entrées antérieures à --before ;
  2. le marquage est idempotent (relancer ne re-marque rien) ;
  3. une entrée superseded sort du N de multiplicité, du budget
     (_consumes) et des verdicts actifs du bloc STATE ;
  4. une entrée superseded ne bloque plus une re-mesure (pas de
     DUPLICATE) — c'est le but : re-mesurer après correction ;
  5. l'historique n'est jamais supprimé : les 97 lignes restent 97.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.lab_ledger import (  # noqa: E402
    DEFAULT_BUDGET,
    assess,
    confirmation_multiplicity,
    load,
    norm_text,
    parse_dt,
    sha,
    status_md,
)


def _entry(date: str, verdict: str, hyp: str = "edge X au crash",
           family: str = "fam", strategy: str = "strat") -> dict:
    return {
        "date": date,
        "ts": f"{date}T12:00:00Z",
        "family": family,
        "strategy": strategy,
        "hypothesis": hyp,
        # MÊME hash que lab_ledger : sha(norm_text(hyp)) — sinon le dedup
        # ne pourrait jamais matcher la fixture
        "hypothesis_hash": sha(norm_text(hyp)),
        "verdict": verdict,
        "n": 200,
    }


class SupersedeLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "trials.jsonl"
        rows = [
            _entry("2026-10-01", "PASS", "hyp pre A"),
            _entry("2026-10-03", "FAIL", "hyp pre B"),
            _entry("2026-10-07", "DISCOVERY_FAIL", "hyp post C"),
        ]
        self.ledger.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n",
            encoding="utf-8",
        )

    def _run_supersede(self, *extra: str) -> int:
        from scripts.lab_ledger import main
        return main(["--ledger", str(self.ledger), "supersede",
                     "--before", "2026-10-05T23:58:04Z", "--by", "PR-143",
                     "--reason", "look-ahead corrige", *extra])

    def test_supersede_marque_strictement_les_antérieures(self):
        rc = self._run_supersede()
        self.assertEqual(rc, 0)
        rows = [json.loads(l) for l in self.ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(rows), 3, "l'historique n'est jamais supprimé")
        pre = [r for r in rows if r["date"] < "2026-10-05"]
        self.assertEqual(len(pre), 2)
        for r in pre:
            self.assertEqual(r["superseded"], "PR-143")
            self.assertEqual(r["superseded_reason"], "look-ahead corrige")
        post = next(r for r in rows if r["date"] >= "2026-10-05")
        self.assertNotIn("superseded", post, "l'entrée post-correctif reste active")

    def test_supersede_est_idempotent(self):
        self._run_supersede()
        rows_before = self.ledger.read_text(encoding="utf-8")
        rc = self._run_supersede()
        self.assertEqual(rc, 0)
        self.assertEqual(self.ledger.read_text(encoding="utf-8"), rows_before)

    def test_superseded_sort_du_N_de_multiplicité_et_du_budget(self):
        self._run_supersede()
        entries = load(self.ledger, None)
        # 1 seule confirmation active : la pré-FAIL B et pré-PASS A sont hors preuve,
        # la post-C est une DISCOVERY (mode discovery ? non — pas de champ mode ->
        # confirmation). 2 pré marquées + 1 post non marquée => N = 1.
        self.assertEqual(confirmation_multiplicity(entries), 1)
        self.assertFalse(any(e["_consumes"] for e in entries if e.get("superseded")))

    def test_superseded_ne_compte_pas_dans_les_verdicts_actifs(self):
        self._run_supersede()
        md = status_md(load(self.ledger, None),
                       {"total_experiments": 20, "per_family": 5, "per_strategy": 3,
                        "max_parameter_variants": 12, "prior_trials": 0},
                       __import__("scripts.lab_ledger", fromlist=["parse_dt"]).parse_dt("2026-10-10"),
                       None)
        self.assertIn("2 superseded hors preuve", md)
        self.assertIn("superseded : PR-143", md)
        # les verdicts actifs ne contiennent ni le PASS ni le FAIL pré-correctif
        # (les DISCOVERY_* n'ont jamais figuré dans cette ligne — comportement
        # existant inchangé, le suffixe "superseded :" les trace à part)
        active = md.split("superseded :")[0]
        self.assertNotIn("PASS 1", active)
        self.assertNotIn("FAIL 1", active)

    def test_superseded_ne_bloque_plus_une_remesure(self):
        # passe par assess() : le test protège le FILTRE de dedup dans le
        # code, pas seulement un appel direct à dedup_verdict
        self._run_supersede()
        entries = load(self.ledger, None)
        res = assess(entries, dict(DEFAULT_BUDGET), parse_dt("2026-10-10"),
                     "fam", "strat", "hyp pre A", {},
                     mode="confirmation", snapshot="default")
        self.assertNotEqual(
            res["status"], "NO-OP",
            f"une hypothèse superseded ne doit plus donner DUPLICATE : {res['msgs']}",
        )


if __name__ == "__main__":
    unittest.main()
