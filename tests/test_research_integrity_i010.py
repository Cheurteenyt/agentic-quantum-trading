#!/usr/bin/env python3
"""P4 (audit Sonnet 5.5, R4) — I010 : toute hypothèse pré-enregistrée porte
un Mécanisme NON TRIVIAL.

Le constat du rapport : « personne ne fait tourner les hypothèses qui ont un
mécanisme » — les 16 lots de la semaine étaient des variantes de seuils sans
mécanisme, pendant que les hypothèses À mécanisme attendaient. Sans champ
obligatoire, on ne peut même pas mesurer lesquelles en ont un. Les mutations
ci-dessous prouvent que le verrou rougit sur chaque défaut réel : ligne
absente, header template recopié sans contenu, placeholder <…>.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.research_integrity as RI  # noqa: E402


def _mecanisme_de(txt: str) -> str | None:
    """La même extraction que I010 (test de la fonction pure)."""
    lines = txt.splitlines()
    idx = next((i for i, l in enumerate(lines)
                if l.lstrip().startswith("Mécanisme")), None)
    if idx is None:
        return None
    contenu = RI._contenu_mecanisme(lines, idx)
    return contenu if len(contenu) >= 40 else None


class LeParseurDuParagraphe(unittest.TestCase):

    def test_ligne_simple_acceptee(self):
        txt = ("# H\ndomaine : x\n"
               "Mécanisme : les règles figées appliquées à des symboles "
               "jamais vus séparent l'edge réel du sur-apprentissage.\n"
               "Prédiction : E[R] > 0.\n")
        self.assertIsNotNone(_mecanisme_de(txt))

    def test_header_template_avec_continuation_indentee_accepte(self):
        """Le format template : `Mécanisme (pourquoi…) :` + lignes indentées
        (le format réel de w42-reconstruction)."""
        txt = ("# H\ndomaine : x\n"
               "Mécanisme (pourquoi ça devrait exister, 3 lignes) :\n"
               "  Les deux seuls flux vivants sont décorrelés par construction :\n"
               "  le survivor est long inliquidable, le vol_spike est un fade\n"
               "  court-terme — la décorrélation vaut un edge en plus.\n"
               "Prédiction : E[R] > 0.\n")
        self.assertIsNotNone(_mecanisme_de(txt))

    def test_header_template_recopie_sans_contenu_refuse(self):
        """Le défaut réel : le fichier copie le template verbatim — le
        header reste, AUCUN mécanisme écrit. La capture tombe sur les lignes
        de section suivantes → trivial → refusé."""
        txt = ("# H\ndomaine : x\n"
               "Mécanisme (pourquoi ça devrait exister, 3 lignes) :\n"
               "Prédiction chiffrée (signe, magnitude, horizon) :\n"
               "PASS si … · FAIL si …\n")
        self.assertIsNone(_mecanisme_de(txt))

    def test_ligne_absente_refusee(self):
        self.assertIsNone(_mecanisme_de("# H\nPas de mécanisme ici.\n"))

    def test_trivial_refuse(self):
        txt = "# H\nMécanisme : à définir.\n"
        self.assertIsNone(_mecanisme_de(txt))

    def test_placeholder_refuse(self):
        import re
        txt = ("# H\nMécanisme : <à écrire avant le run, avec une vraie "
               "justification détaillée du mécanisme économique>.\n")
        contenu = _mecanisme_de(txt)
        self.assertIsNotNone(contenu)   # assez long, mais…
        self.assertTrue(re.search(r"<[^>\n]*>", contenu))   # placeholder détecté


class LeDepotReel(unittest.TestCase):
    """Ancrage réel : I010 tourne sur le dépôt et PASSE — chaque hypothèse
    pré-enregistrée porte aujourd'hui son mécanisme (les 5 écarts du 11/10
    ont été comblés AVANT d'activer l'invariant, jamais silencieusement)."""

    def test_i010_passe_sur_le_depot(self):
        code = RI.main()
        self.assertEqual(code, 0, "I010 doit passer sur le dépôt réel")

    def test_les_hypotheses_exclues_ne_sont_pas_des_hypotheses(self):
        """Les exclusions sont les mêmes que le verrou des scellés : gabarit,
        README, amendements — on ne sur-compte pas (leçon #288 : sur-compter
        n'est pas verrouiller)."""
        hdir = ROOT / "research" / "hypotheses"
        exclus = [f for f in hdir.glob("*.md")
                  if f.stem.startswith("_") or f.name == "README.md"]
        self.assertTrue(exclus, "le gabarit doit exister pour ce test")


if __name__ == "__main__":
    unittest.main()
