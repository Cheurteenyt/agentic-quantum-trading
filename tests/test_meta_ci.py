#!/usr/bin/env python3
"""R3-bis (audit Sonnet 5.5) — verrou du test de MÉTA-CI.

Le rapport §R3 demande « **un seul** test de méta-CI (« chaque palier déclaré s'est
exécuté sur le dernier run ») au lieu d'un correctif par trou ».

`scripts/meta_ci.py` fait ce test. Ici, on verrouille l'invariant qui le rend durable :

  1. la liste des paliers OBLIGATOIRES est **DÉRIVÉE du workflow**, pas énumérée —
     un nouveau palier sans filtre de chemins devient obligatoire par construction,
     sans que personne ait à y penser (c'est exactement le mode d'échec que le rapport
     décrit : « chaque oubli est un faux vert ») ;
  2. la dérivation reproduit bien `OBLIGATOIRES` de `scripts/meta_ci.py` — si quelqu'un
     ajoute un palier non filtré et oublie de le déclarer, ce test rougit ;
  3. le détecteur distingue un palier qui a TOURNÉ d'un palier qui a DISPARU
     (mutation : `skipped` ⇒ rouge, nommé).

Le tout sans réseau : c'est le point du choix d'implémentation (les `needs.*.result`
du job `gate` au lieu de l'API GitHub).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import meta_ci  # noqa: E402

import yaml  # noqa: E402

CI = ROOT / ".github" / "workflows" / "ci.yml"


def _jobs() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


def _condition(job: dict) -> str:
    return " ".join(str(job.get("if", "")).split())


def _est_filtre_par_chemins(job: dict) -> bool:
    """Un job est filtré s'il consulte une sortie de `changes`."""
    return "needs.changes.outputs." in _condition(job)


def _tourne_sur_pr_et_push(job: dict) -> bool:
    """Le `if:` peut-il être vrai sur un `pull_request` ET sur un `push` ?

    On ne fait pas d'évaluation symbolique : on reconnaît les formes utilisées dans
    ce workflow. Un job sans `if:` tourne toujours. Un job dont le `if:` mentionne un
    événement qui n'est ni PR ni push (`merge_group`, `schedule`, `workflow_dispatch`)
    sans mention explicite de PR/push est exclu.
    """
    cond = _condition(job)
    if not cond:
        return True
    mentionne_event = ("github.event_name" in cond)
    if not mentionne_event:
        return True  # ex. gate : always() && !cancelled() — tourne partout
    # S'il y a une conjonction d'événements, il faut que PR et push soient acceptés.
    pr = "pull_request" in cond
    push = "'push'" in cond or '"push"' in cond or "== 'push'" in cond
    return pr and push


def _tous_les_obligatoires() -> set[str]:
    """L'union des paliers obligatoires sur tous les événements (pour les mutations)."""
    return {n for paliers in meta_ci.OBLIGATOIRES.values() for n in paliers}


def _obligatoires_derives() -> set[str]:
    """Les paliers obligatoires (union), DÉRIVÉS de la source du workflow.

    Obligatoire = pas de filtre de chemins ET tourne sur au moins un des événements
    déclarés dans `meta_ci.OBLIGATOIRES`.
    """
    return {
        nom for nom, job in _jobs().items()
        if not _est_filtre_par_chemins(job) and _tourne_sur_au_moins_un_gate(job)
    }


# Les événements hors gate : nocturne et manuel. Un job qui EXIGE l'un des deux
# (`==`) n'est pas un job de PR.
EVEREMENTS_HORS_GATE = ("schedule", "workflow_dispatch")


def _reserve_a_un_evnement_hors_gate(cond: str) -> bool:
    """Le `if:` EXIGE-t-il un événement hors gate ?

    ⚠️ `==` et non `!=` : `changes` a `if: github.event_name != 'schedule'`, ce qui
    est vrai SUR LES PR — ce n'est pas un job réservé au nocturne. Chercher la simple
    présence de la chaîne `'schedule'` classerait `changes` comme non obligatoire, à
    tort. C'est la forme exacte du piège « chercher une chaîne au lieu du sens » que
    ce dépôt a déjà rencontré (cf. `grep import pyflakes` comptant un commentaire).
    """
    return any(f"== '{ev}'" in cond for ev in EVEREMENTS_HORS_GATE)


def _tourne_sur_au_moins_un_gate(job: dict) -> bool:
    """Le job tourne-t-il sur au moins un événement de gate ?

    On ne fait pas d'évaluation symbolique complète — piège sans fond. On refuse
    seulement les jobs RÉSERVÉS à un déclenchement hors gate.
    """
    cond = _condition(job)
    if not cond:
        return True
    if "github.event_name" not in cond:
        return True  # always() && !cancelled() — tourne partout
    return not _reserve_a_un_evnement_hors_gate(cond)


class LaListeDesObligatoiresEstDerivee(unittest.TestCase):
    """Un palier non filtré est obligatoire PAR CONSTRUCTION."""

    def test_la_derivation_trouve_quelque_chose(self):
        """Garde d'ancrage : une dérivation qui ne trouve rien ne verrouille rien."""
        self.assertTrue(_obligatoires_derives(),
                        "aucun palier obligatoire dérivé — le parseur ne lit plus le workflow")

    def test_la_derivation_correspond_a_meta_ci(self):
        """Le script et le workflow disent la même chose — sinon, l'un des deux ment."""
        derives = _obligatoires_derives()
        declare = _tous_les_obligatoires()
        self.assertEqual(
            derives, declare,
            f"dérivé du workflow = {sorted(derives)} ; déclaré dans meta_ci = {sorted(declare)}. "
            "Un palier non filtré doit être OBLIGATOIRE, et un palier filtré ne doit pas l'être."
        )

    def test_les_paliers_filtres_ne_sont_pas_obligatoires(self):
        """C'est leur FONCTION de sauter sur une PR docs-only — ne pas les exiger."""
        filtres = {n for n, j in _jobs().items() if _est_filtre_par_chemins(j)}
        self.assertEqual(filtres & _tous_les_obligatoires(), set(),
                         "un palier filtré a été déclaré obligatoire : il rougirait à tort")

    def test_les_paliers_doivent_etre_des_jobs_reels(self):
        """Un nom obligatoire qui n'existe pas dans le workflow est une coquille."""
        manquants = _tous_les_obligatoires() - set(_jobs())
        self.assertEqual(manquants, set(), f"paliers déclarés mais absents du workflow : {manquants}")

    def test_t2_et_t3_ne_sont_pas_obligatoires(self):
        """La merge queue est inactive : les exiger rougirait sur CHAQUE PR."""
        tous = _tous_les_obligatoires()
        for palier in ("t2-full", "t3-night"):
            self.assertNotIn(palier, tous,
                             f"{palier} ne tourne pas sur PR/push — l'exiger serait faux")

    def test_t1_cheap_n_est_pas_obligatoire_sur_merge_group(self):
        """LE faux positif mesuré : t1-cheap a `if: == pull_request || == push`.

        Sur merge_group il saute LÉGITIMEMENT. L'exiger y produirait un faux rouge —
        et « un gate toujours rouge apprend à l'agent à l'ignorer » (leçon F2).
        """
        self.assertNotIn("t1-cheap", meta_ci.paliers_requis("merge_group"),
                         "t1-cheap ne tourne pas sur merge_group : l'exiger serait un faux rouge")
        self.assertIn("t1-cheap", meta_ci.paliers_requis("pull_request"))
        self.assertIn("t1-cheap", meta_ci.paliers_requis("push"))


class UnPalierQuiADisparuEstDetecte(unittest.TestCase):
    """Le détecteur distingue « a tourné » de « a disparu » — prouvé par mutation."""

    def test_un_run_complet_est_vert(self):
        jobs = {n: "success" for n in meta_ci.paliers_requis("pull_request")}
        self.assertEqual(meta_ci.disparus("pull_request", jobs), [])

    def test_mutation_un_palier_obligatoire_skipped(self):
        """LE défaut : un palier obligatoire saute ⇒ le gate se croit vert sans mesurer.

        Générique sur la liste courante : on fait sauter chacun des paliers
        obligatoires (sur PR, l'événement le plus large), un par un, et chacun doit
        être signalé et nommé.
        """
        requis = meta_ci.paliers_requis("pull_request")
        self.assertTrue(requis, "aucun palier obligatoire sur PR — le test ne prouve rien")
        for cible in requis:
            jobs = {n: "success" for n in requis}
            jobs[cible] = "skipped"
            d = meta_ci.disparus("pull_request", jobs)
            self.assertEqual([n for n, _ in d], [cible],
                             f"« {cible} » skipped doit être le seul signalé")

    def test_mutation_palier_absent(self):
        """Un palier qui n'apparaît pas du tout est aussi une disparition.

        On ne code PAS en dur quel palier manque : le test doit rester vrai si la
        liste des obligatoires change légitimement. On retire UN SEUL palier d'un run
        complet et on exige qu'il soit exactement celui signalé.
        """
        requis = meta_ci.paliers_requis("pull_request")
        cible = sorted(requis)[0]
        partiel = {n: "success" for n in requis if n != cible}
        d = meta_ci.disparus("pull_request", partiel)
        self.assertEqual([n for n, _ in d], [cible],
                         f"retirer « {cible} » du run doit être signalé, et lui seul")

    def test_un_echec_n_est_pas_une_disparition(self):
        """`failure` = le palier A tourné (et a dit non) — ce n'est pas un trou."""
        jobs = {n: "failure" for n in meta_ci.paliers_requis("pull_request")}
        self.assertEqual(meta_ci.disparus("pull_request", jobs), [])

    def test_sur_schedule_rien_n_est_obligatoire(self):
        """`schedule` ne lance que T3 : exiger t1-cheap serait un faux rouge quotidien."""
        self.assertEqual(meta_ci.paliers_requis("schedule"), ())
        self.assertEqual(meta_ci.disparus("schedule", {"gate": "success"}), [])

    def test_le_parseur_refuse_une_entree_illisible(self):
        """Une env var mal formée doit ROUGIR, pas être interprétée en silence."""
        with self.assertRaises(ValueError):
            meta_ci.parse_jobs("t1-cheap")


if __name__ == "__main__":
    unittest.main()
