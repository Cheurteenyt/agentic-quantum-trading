#!/usr/bin/env python3
"""R3-③ (audit Sonnet 5.5) — verrou de l'oracle « un commit ci(...) cite un incident ».

Le rapport §R3 demande de « déclarer la CI terminée pour 2 semaines : tout nouveau
commit `ci(...)` doit citer un incident réel ». `scripts/audit_ci_commits.py` rend
la règle vérifiable. Ici on verrouille :

  1. l'oracle distingue un `ci(...)` qui cite un incident d'un `ci(...)` qui n'en
     cite pas — c'est le SEUL service qu'il rend (mutation) ;
  2. la règle reste ÉTROITE : un `fix(ci) ...` ou un `research(...)` n'est PAS un
     commit `ci(...)` et n'est jamais fautif. Un oracle qui déborde sur d'autres
     préfixes serait un oracle qui juge du style ;
  3. l'historique RÉEL du dépôt passe — si un jour un `ci(...)` nu entre dans
     `main`, ce test le dit (il ne s'agit pas de le cacher, mais de le voir).
"""

from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_ci_commits as a  # noqa: E402


class LaRegleEstEtroite(unittest.TestCase):
    """`ci(...)` seulement — pas de jugement de style, pas de débordement."""

    def test_les_scopes_ci_sont_reconnus(self):
        for sujet in ("ci(fix) x", "ci: x", "ci(ratchet): x", "ci(gate) x"):
            self.assertTrue(a.est_commit_ci(sujet), sujet)

    def test_les_autres_prefixes_sont_hors_perimetre(self):
        """Le rapport ne parle que des commits `ci(...)` — ne pas élargir."""
        for sujet in (
            "fix(ci) correction du workflow (#291)",
            "research(ledger) R2 — un verdict sans chiffres est REFUSE (#287)",
            "docs(38) la gouvernance",
            "chore: ménage",
        ):
            self.assertFalse(a.est_commit_ci(sujet), sujet)

    def test_citation_incident(self):
        self.assertTrue(a.cite_un_incident("ci(gate) muet (#285)"))
        self.assertTrue(a.cite_un_incident("ci: PR-179 shallow checkout (#179)"))
        self.assertFalse(a.cite_un_incident("ci(fix) je répare la CI"))
        self.assertFalse(a.cite_un_incident("ci: corrections diverses"))


class UnCiNuEstDetecte(unittest.TestCase):
    """Le SEUL service de l'oracle : voir un `ci(...)` sans incident (mutation)."""

    def _fautifs(self, commits: list[tuple[str, str]]) -> list[str]:
        """Applique la règle à une liste de commits simulée."""
        return [h for h, s in commits
                if a.est_commit_ci(s) and not a.cite_un_incident(s)]

    def test_mutation_ci_nu_est_fautif(self):
        c = [("aaaa111", "ci(fix) je répare la CI"), ("bbbb222", "ci(gate) muet (#285)")]
        self.assertEqual(self._fautifs(c), ["aaaa111"])

    def test_tous_les_ci_cites_passent(self):
        c = [("aaaa111", "ci(gate) muet (#285)"), ("bbbb222", "ci(ratchet): r7 (#234)")]
        self.assertEqual(self._fautifs(c), [])

    def test_un_non_ci_sans_reference_n_est_jamais_fautif(self):
        """La règle ne réclame RIEN des autres préfixes."""
        c = [("aaaa111", "chore: ménage"), ("bbbb222", "docs(38): gouvernance")]
        self.assertEqual(self._fautifs(c), [])


class LeGelEstUnEtatPasUneIntention(unittest.TestCase):
    """La règle du rapport est BORNÉE dans le temps (« pour 2 semaines »).

    Le piège qu'on refuse : un gate qui reste rouge APRÈS l'expiration du gel —
    l'agent apprend à l'ignorer (F2). Le gel doit donc être un ÉTAT VÉRIFIABLE
    (des dates), pas une intention (un texte qui dit « gelé »).
    """

    def test_dans_la_fenetre_le_gel_est_actif(self):
        self.assertTrue(a.gel_actif(datetime.date(2026, 10, 11)))
        self.assertTrue(a.gel_actif(datetime.date(2026, 10, 18)))
        self.assertTrue(a.gel_actif(datetime.date(2026, 10, 25)))

    def test_hors_fenetre_le_gel_est_inactif(self):
        """Avant la déclaration ET après l'expiration : pas de rouge."""
        self.assertFalse(a.gel_actif(datetime.date(2026, 10, 10)))
        self.assertFalse(a.gel_actif(datetime.date(2026, 10, 26)))
        self.assertFalse(a.gel_actif(datetime.date(2027, 1, 1)))

    def test_la_fenetre_est_de_deux_semaines(self):
        """Le rapport dit « 2 semaines » — pas « jusqu'à ce qu'on se lasse »."""
        self.assertEqual((a.GEL_FIN - a.GEL_DEBUT).days, 14)


class LHistoriqueReelPasse(unittest.TestCase):
    """Le dépôt observe déjà la règle — et on le MESURE, on ne le suppose pas."""

    def test_il_y_a_des_commits_ci_dans_l_historique(self):
        """Garde d'ancrage : sans commit `ci(...)`, l'oracle ne prouve rien."""
        vus = a.tous_les_ci("HEAD")
        self.assertGreater(len(vus), 5,
                           "moins de 6 commits `ci(...)` trouvés — le scanner ne lit plus git")

    def test_aucun_ci_nu_dans_l_historique(self):
        """État mesuré le 11/10 : 15/15 citent un incident.

        ⚠️ Ce test n'est PAS une interdiction de régresser : si un `ci(...)` nu
        entre dans `main`, il faut soit le corriger, soit assumer ici pourquoi.
        Ce qu'on refuse, c'est qu'il passe INAPERÇU.
        """
        mauvais = a.fautifs("HEAD")
        self.assertEqual(
            mauvais, [],
            f"commits `ci(...)` sans incident cité : {mauvais}. "
            "La règle R3 demande de citer l'incident réel (le #NNN qui le documente)."
        )


if __name__ == "__main__":
    unittest.main()
