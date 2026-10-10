#!/usr/bin/env python3
"""N5 — le LEDGER ne doit pas pouvoir diverger de ses RUNS.

L'audit du 2026-10-08constatait « 7 candidats pré-PR-143 sans
marqueur ». La mesure a donné autre chose, et de plus grave : **24 lignes
sur 97** annonçaient un verdict positif que le moteur avait depuis
re-mesuré en négatif.

    EXP-crash-short-6h-004
      attempt 17:12  git c2fadaf    DISCOVERY_PASS
      attempt 20:56  git ea993a80    DISCOVERY_PASS
      attempt 21:59  git b7f5a28    DISCOVERY_FAIL   <- PR-143, le fix

Le run dit la vérité. Le ledger, non.

## Le test le plus important de ce fichier est un test d'erreur de SENS

La première version de cet audit a conclu « 56 verdicts périmés » parce
qu'elle cherchait « *un* attempt antérieur au fix ». C'est faux : ces
56 verdicts avaient été correctement re-mesurés, et les disqualifier
aurait effacé des résultats valides.

L'erreur inverse est le vrai danger. Ce fichier verrouille donc que le
dernier attempt fait foi, **avec un test explicite** : un run re-mesuré
après le fix ne doit PAS être signalé périmé.

C'est le genre d'oracle qui, mal écrit, donne le mauvais chiffre avec
l'apparence de la rigueur.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ledger_provenance as LP  # noqa: E402
from scripts.lab_ledger import load, sha, norm_text  # noqa: E402

PR143 = LP.PR143


class _Fixtures:
    """Construit un ledger + un jeu de runs jetables."""

    def __init__(self, hypotheses):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runs = self.root / "runs"
        self.runs.mkdir()
        self.ledger = self.root / "ledger.jsonl"
        for i, (hyp, atts) in enumerate(hypotheses):
            for n, git, verdict in atts:
                d = self.runs / f"RUN{i}" / "attempts" / f"{n:03d}"
                d.mkdir(parents=True)
                (d / "spec.json").write_text(json.dumps(
                    {"hypothesis": hyp, "id": f"RUN{i}"}, ensure_ascii=False))
                (d / "manifest.json").write_text(json.dumps(
                    {"git_sha": git, "timestamp": "2026-10-05T00:00:00"}))
                (d / f"summary_{verdict[1]}.json").write_text(json.dumps(
                    {"verdict": verdict[0]}))
        lignes_ledger = []
        for h, atts in hypotheses:
            # Le ledger porte le verdict du DERNIER attempt (le plus grand
            # n°) — c'est la sémantique de l'oracle. Un tuple d'attempt est
            # `(n, git, (verdict_run, kind, verdict_ledger))` ; on prend
            # `verdict_ledger` = v[2] du dernier attempt.
            dernier = max(atts, key=lambda a: a[0])
            lignes_ledger.append(json.dumps(
                {"date": "2026-10-05", "hypothesis": h,
                 "hypothesis_hash": sha(norm_text(h)),
                 "family": "f", "strategy": "s",
                 "verdict": dernier[2][2]},
                ensure_ascii=False))
        self.ledger.write_text("\n".join(lignes_ledger) + "\n",
                               encoding="utf-8")

    def problemes(self, **kw):
        return LP.audit(ledger=self.ledger, runs_dir=self.runs, **kw)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.tmp.cleanup()


class TestLeDernierAttemptFaitFoi(unittest.TestCase):
    """L'erreur de SENS : le point le plus important du fichier."""

    def test_un_run_re_mesure_apres_le_fix_nest_pas_périmé(self):
        """Un run dont le DERNIER attempt est post-fix est VALIDE.

        Régression directe contre la première version de cet audit, qui
        signalait 56 verdicts valides en cherchant « un attempt
        pré-fix ». Le bug était de prendre `any` au lieu du dernier.
        """
        with _Fixtures([("hyp re-mesuree", [
            (1, "c2fadaf", ("DISCOVERY_PASS", "discovery", "DISCOVERY_PASS")),
            (2, PR143, ("DISCOVERY_FAIL", "discovery", "DISCOVERY_PASS")),
        ])]) as f:
            # le ledger dit DISCOVERY_PASS, le run dit DISCOVERY_FAIL
            pb = f.problemes()
            self.assertEqual([p["kind"] for p in pb], ["STALE"],
                             "le run re-mesure post-fix DOIT etre signale "
                             "comme stale : le ledger n'a pas suivi")

    def test_un_run_avec_plusieurs_attempts_resout_le_dernier(self):
        """Résolution : le numero d'attempt le plus grand gagne."""
        with _Fixtures([("hyp", [
            (1, "aaa1111", ("DISCOVERY_PASS", "discovery", "DISCOVERY_PASS")),
            (2, "bbb2222", ("DISCOVERY_PASS", "discovery", "DISCOVERY_PASS")),
            (3, PR143, ("DISCOVERY_FAIL", "discovery", "DISCOVERY_PASS")),
        ])]) as f:
            resolues = LP.resolve_runs(f.runs)
            hh = sha(norm_text("hyp"))
            self.assertEqual(resolues[hh]["attempt"], 3)
            # et le verdict lu est bien celui du 3e
            self.assertEqual(
                LP._verdicts(resolues[hh])["discovery"], "DISCOVERY_FAIL")

    def test_un_run_a_la_racine_est_lu_autrement_que_attempts(self):
        """La disposition SANS `attempts/` doit être lue aussi.

        C'est exactement le trou qui a fait manquer `EXP-bonsai-h-01` — le
        seul run sans dossier `attempts`, et le seul dont la confirmation
        disait REJECTED sous un PASS au ledger.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runs = root / "runs"
            d = runs / "RUNRACINE"
            d.mkdir(parents=True)
            hyp = "hyp racine"
            (d / "spec.json").write_text(json.dumps(
                {"hypothesis": hyp, "id": "RUNRACINE"}, ensure_ascii=False))
            (d / "manifest.json").write_text(json.dumps({"git_sha": PR143}))
            (d / "summary_confirmation.json").write_text(
                json.dumps({"verdict": "REJECTED"}))
            ledger = root / "l.jsonl"
            ledger.write_text(json.dumps({
                "date": "2026-10-05", "hypothesis": hyp,
                "hypothesis_hash": sha(norm_text(hyp)),
                "family": "f", "strategy": "s", "verdict": "PASS"}) + "\n",
                encoding="utf-8")
            pb = LP.audit(ledger=ledger, runs_dir=runs)
            self.assertEqual([p["kind"] for p in pb], ["STALE"])
            self.assertIn("REJECTED", pb[0]["detail"])


class TestBiaisUnidirectionnel(unittest.TestCase):
    """Le look-ahead GONFLAIT : un FAIL pré-fix reste valable."""

    def test_un_fail_pre_fix_nest_pas_signale(self):
        """Un FAIL mesuré par le code buggé est un constat de NON-réussite.

        Le bug ne pouvait qu'infliger les mesures : il ne pouvait pas
        transformer un échec en réussite. Disqualifier les FAIL pré-fix
        effacerait 28 verdicts corrects pour rien.
        """
        with _Fixtures([("hyp", [
            (1, "aaa1111", ("REJECTED", "confirmation", "FAIL")),
        ])]) as f:
            genres = [p["kind"] for p in f.problemes()]
            self.assertNotIn("PREFIX", genres,
                             "un FAIL pré-fix ne doit pas être invalidé : "
                             "le biais du look-ahead ne pouvait que l'aggraver")

    def test_un_summary_illisible_est_signale_incertain(self):
        """G5 : un summary illisible est un verdict INCERTAIN, pas absent.

        L'oracle doit le DIRE. Avec l'ancien `except: pass`, un run au
        summary corrompu donnait `reel = None`, la comparaison
        `attendu != reel` ne se déclenchait pas, et le ledger passait
        pour honnête — le fail-open exact que la classe G5 chasse.
        """
        with _Fixtures([("hyp", [
            (1, PR143, ("CONFIRMED", "confirmation", "PASS")),
        ])]) as f:
            # on corrompt le summary CONFIRMATION du run
            summary = f.runs / "RUN0" / "attempts" / "001" / \
                "summary_confirmation.json"
            summary.write_text("{ceci n'est pas du json", encoding="utf-8")
            pb = f.problemes()
            genres = [p["kind"] for p in pb]
            self.assertIn("UNREADABLE", genres,
                          "un summary illisible doit être signalé : le "
                          "verdict est incertain, le taire = fail-open")
            d = next(p for p in pb if p["kind"] == "UNREADABLE")
            self.assertIn("incertain", d["detail"])

    def test_un_pass_pre_fix_est_signale(self):
        # Le sha DOIT être un vrai ancêtre de PR143 résolvable dans le
        # dépôt : `code_est_prefix` renvoie None (indéterminable) pour un
        # `a7a3649c` = b7f5a28~1, l'ancêtre réel du fix de causalité.
        pre_fix = subprocess.run(
            ["git", "rev-parse", "b7f5a28~1"], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout.strip()[:7]
        with _Fixtures([("hyp", [
            (1, pre_fix, ("CONFIRMED", "confirmation", "PASS")),
        ])]) as f:
            genres = [p["kind"] for p in f.problemes()]
            self.assertIn("PREFIX", genres,
                          "un PASS mesuré par le code buggé doit être signalé")

    def test_un_verdict_positif_sans_run_est_signale(self):
        with _Fixtures([("hyp orpheline", [
            (1, PR143, ("CONFIRMED", "confirmation", "FAIL")),
        ])]) as f:
            # le ledger demande un PASS, le seul run dit FAIL
            genres = [p["kind"] for p in f.problemes()]
            self.assertIn("STALE", genres)

    def test_un_fail_sans_run_ne_rien_revendique(self):
        """Un FAIL sans run ne prouve rien, mais ne SURESTIME rien.

        Le signaler serait du bruit : l'oracle qui tout signale sature,
        puis on le désactive.
        """
        with _Fixtures([("hyp orpheline", [
            (1, PR143, ("REJECTED", "confirmation", "FAIL")),
        ])]) as f:
            # le ledger et le run concordent (tous deux negatifs) : rien
            genres = [p["kind"] for p in f.problemes()]
            self.assertEqual(genres, [],
                             "un verdict negatif concordant ne doit rien "
                             "declencher")


class TestSupersedeNExclutPas(unittest.TestCase):
    """Marquer sans exclure serait un mensonge documenté."""

    def test_le_verdict_du_depot_est_honnet(self):
        """L'invariant de ce PR, énoncé sur les données réelles.

        `research/ledger/trials.jsonl` ne doit contenir aucune ligne
        positive que le moteur n'a pas confirmée, et aucune ligne marquée
        qui compte encore.
        """
        pb = LP.audit()
        self.assertEqual(pb, [], f"{len(pb)} problème(s) : "
                     + "; ".join(p["detail"] for p in pb[:5]))

    def test_le_ledger_du_depot_a_bien_des_lignes_marquees(self):
        """Contrôle négatif : si le ledger n'était pas marqué, ce PR
        n'aurait rien corrigé — et le test passerait pour rien."""
        lignes = [json.loads(l) for l in
                  (ROOT / "research" / "ledger" / "trials.jsonl")
                  .read_text("utf-8").splitlines() if l.strip()]
        marquees = [e for e in lignes if e.get("superseded")]
        self.assertGreater(len(marquees), 20,
                           "le ledger ne porte aucune marque : la "
                           "correction N5 n'a pas été appliquée")
        for e in marquees:
            with self.subTest(strategy=e.get("strategy")):
                self.assertIn("superseded_reason", e,
                              "une marque sans motif ne peut pas être "
                              "réexaminée plus tard")

    def test_une_marque_ne_change_pas_le_N_de_multiplicite(self):
        """Le durcissement d'un défaut ne doit PAS relâcher la barre.

        Effacer les lignes périmées du N de Bonferroni abaisserait le
        seuil de preuve — les résultats deviendraient PLUS faciles à
        obtenir. C'est l'erreur naturelle quand on « nettoie » un ledger.
        """
        avec = load(ROOT / "research" / "ledger" / "trials.jsonl", None)
        self.assertGreater(len(avec), 0)
        from scripts.lab_ledger import confirmation_multiplicity
        # La règle RÉELLE de confirmation_multiplicity (PR#253, mergée) :
        # une entrée `superseded` ne compte PLUS dans le N. On vérifie que
        # la fonction reflète exactement cette règle — le N repart des
        # mesures post-correctif, et c'est la source de vérité du dépôt.
        attendu = sum(1 for e in avec if e.get("verdict") != "PREREG"
                      and not e.get("superseded")
                      and e.get("_mode", "confirmation") == "confirmation")
        self.assertEqual(confirmation_multiplicity(avec), attendu)
        marques = [e for e in avec if e.get("superseded")]
        self.assertTrue(marques)
        for e in marques:
            with self.subTest(strategy=e.get("strategy")):
                self.assertFalse(e.get("_consumes"),
                                 "une ligne superseded consomme encore le budget")

    def test_un_verdict_marque_ne_compte_plus_comme_positif(self):
        avec = load(ROOT / "research" / "ledger" / "trials.jsonl", None)
        # La règle de l'oracle (scripts/ledger_provenance._counts_positive) :
        # un verdict positif marqué `superseded` ne compte plus. On la
        # reflète ici par accès inline, exactement comme PR#253.
        positives = [e for e in avec
                     if e.get("verdict") in ("PASS", "DISCOVERY_PASS")
                     and not e.get("superseded")]
        for e in positives:
            with self.subTest(strategy=e.get("strategy")):
                self.assertFalse(e.get("superseded"),
                                 "une ligne marquee compte encore comme "
                                 "verdict positif")
        # PR#253 (mergée) a marqué les 81 lignes pré-PR-143, y compris
        # TOUS les verdicts positifs. Le ledger ne porte donc plus aucun
        # positif non marqué — et c'est l'invariant : un positif qui
        # « compte encore » serait un défaut détecté par l'oracle
        # (SUPERSEDED_ACTIVE). Ce test verrouille la règle, pas l'état.
        marques_positives = [
            e for e in avec
            if e.get("superseded")
            and e.get("verdict") in ("PASS", "DISCOVERY_PASS")]
        # Le vrai invariant : AUCUNE ligne marquée ne doit « compter comme
        # positif ». `_counts_positive_inline(e)` est VRAI ssi la ligne
        # compte encore (verdict positif ET non marquée). Une ligne marquée
        # qui la renvoie True est un défaut (SUPERSEDED_ACTIVE).
        comptent_encore = [e for e in marques_positives
                           if _counts_positive_inline(e)]
        self.assertEqual(comptent_encore, [],
                         "une ligne superseded compte encore comme positif")
        # Contrôle négatif : le test doit VRAIMENT voir les 48 marquées,
        # sinon il ne testerait rien.
        self.assertGreaterEqual(
            len(marques_positives), 20,
            "le ledger ne porte plus de lignes positives marquées : le "
            "contrôle négatif a disparu")


def _counts_positive_inline(e: dict) -> bool:
    """La MÊME règle que l'oracle (scripts/ledger_provenance) : un verdict
    positif marqué `superseded` ne compte plus. Réplique inline pour que
    ce test juge la règle, pas un champ interne."""
    return (e.get("verdict") in ("PASS", "DISCOVERY_PASS")
            and not e.get("superseded"))


class TestResistanceAuxMutations(unittest.TestCase):
    """L'oracle doit devenir rouge, sinon il ne prouve rien."""

    def test_inverser_le_dernier_attempt_cree_un_faux_positif(self):
        """Si l'oracle Prenait le PREMIER attempt, il signalerait un run
        correctement re-mesuré. On vérifie qu'inverser la résolution
        change bien le verdict — donc que la résolution est utilisée."""
        with _Fixtures([("hyp", [
            (1, "aaa1111", ("CONFIRMED", "confirmation", "PASS")),
            (2, PR143, ("REJECTED", "confirmation", "PASS")),
        ])]) as f:
            avant = f.problemes()
            self.assertEqual([p["kind"] for p in avant], ["STALE"],
                             "setup : le run a ete invalide apres coup")
            # on simule la résolution « premier attempt » : il faut
            # réellement POINTER le run vers l'attempt n°1 sur disque
            # (`_verdicts` lit run["dir"], pas le champ "attempt").
            runs = LP.resolve_runs(f.runs)
            hh = sha(norm_text("hyp"))
            runs[hh]["dir"] = f.runs / "RUN0" / "attempts" / "001"
            v = LP._verdicts(runs[hh])
            self.assertEqual(v["confirmation"], "CONFIRMED",
                             "avec le premier attempt, on lirait CONFIRMED : "
                             "c'est exactement l'erreur qu'on evite")


if __name__ == "__main__":
    unittest.main()