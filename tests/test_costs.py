#!/usr/bin/env python3
"""P2 (audit Sonnet 5.5, R4) — verrous du modèle de coûts par symbole.

Le défaut d'origine : `cost_pct = 0,28` (%) PLAT appliqué à chaque symbole,
un magic number noyé dans les specs, et un `breakeven_cost_bps` demandé par
R2 mais jamais produit. Ici on verrouille :
  1. la priorité d'application (spec explicite > table > défaut) ;
  2. le breakeven — (net + coût) × 100, et ≤ 0 si l'hypothèse est morte
     même à coût nul ;
  3. la table ne fabrique RIEN : une entrée sans `source` datée est un
     défaut signalé (un coût sans provenance est une invention).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.costs import (  # noqa: E402
    DEFAUT_RT_PCT, breakeven_cost_bps, cout_rt_pct, verifier_table)


class LaPrioriteDApplication(unittest.TestCase):

    def test_le_defaut_est_la_mesure_meme_28bps(self):
        """La table du dépôt est VIDE (aucune mesure par symbole post-correctif)
        — le défaut doit être la mesure datée (meme TAKER_RT 28 bps)."""
        self.assertEqual(cout_rt_pct("PEPEUSDT"), DEFAUT_RT_PCT)
        self.assertEqual(DEFAUT_RT_PCT, 0.28)

    def test_la_spec_explicite_gagne_toujours(self):
        """Une spec qui pinne son coût garde son modèle (pas de re-écriture
        de l'histoire des specs existantes)."""
        self.assertEqual(cout_rt_pct("PEPEUSDT", spec_pct=0.42), 0.42)

    def test_l_override_table_bat_le_defaut_mais_pas_la_spec(self):
        """Avec un override mesuré dans la table : table > défaut,
        spec > table."""
        import unittest.mock as m
        import scripts.costs as C
        faux = {"defaut_rt_pct": 0.28,
                "par_symbole": {"ARBUSDT": {"rt_pct": 0.19,
                                            "source": "mesure test"}}}
        with m.patch.object(C, "_table", return_value=faux):
            self.assertEqual(cout_rt_pct("ARBUSDT"), 0.19)
            self.assertEqual(cout_rt_pct("BTCUSDT"), 0.28)
            self.assertEqual(cout_rt_pct("ARBUSDT", spec_pct=0.42), 0.42)

    def test_table_absente_ne_crash_pas(self):
        """Pas de table (ou illisible) → défaut. JAMAIS une exception qui
        tuerait un run pour un fichier de config manquant."""
        import unittest.mock as m
        import scripts.costs as C
        with m.patch.object(C, "TABLE", Path("/inexistant/t.yaml")):
            self.assertEqual(cout_rt_pct("X"), DEFAUT_RT_PCT)


class LeBreakeven(unittest.TestCase):

    def test_le_calcul_est_net_plus_cout_en_bps(self):
        # net -0,10 % + coût 0,28 % = brut +0,18 % → 18 bps de marge
        self.assertEqual(breakeven_cost_bps(-0.10, 0.28), 18.0)

    def test_mort_a_cout_nul_donne_un_breakeven_negatif(self):
        """Brut ≤ 0 → breakeven ≤ 0 : l'hypothèse ne passe à AUCUN coût.
        C'est l'information que R2 exigeait (le coût qui l'aurait sauvée
        n'existe pas)."""
        self.assertEqual(breakeven_cost_bps(-0.15, 0.10), -5.0)
        self.assertLessEqual(breakeven_cost_bps(-0.15, 0.10), 0.0)

    def test_marge_mince_donne_le_vrai_breakeven(self):
        """Net −0,05 à coût 0,10 → brut +0,05 : passerait à coût ≤ 5 bps."""
        self.assertEqual(breakeven_cost_bps(-0.05, 0.10), 5.0)

    def test_zero_net_au_cout_applique_donne_le_cout_en_bps(self):
        """Moyenne nette exactement 0 → le breakeven EST le coût appliqué."""
        self.assertEqual(breakeven_cost_bps(0.0, 0.28), 28.0)


class LaTableNeFabriqueRien(unittest.TestCase):

    def test_la_table_reelle_est_saine_ou_vide(self):
        """Le dépôt : table vide (honnête) → aucun problème signalé.
        Si un jour une entrée apparaît, elle DOIT porter sa source."""
        problemes = verifier_table()
        self.assertEqual(problemes, [], f"table : {problemes}")

    def test_une_entree_sans_source_est_un_defaut(self):
        import unittest.mock as m
        import scripts.costs as C
        faux = {"defaut_rt_pct": 0.28,
                "par_symbole": {"ARBUSDT": {"rt_pct": 0.19}}}
        with m.patch.object(C, "_table", return_value=faux):
            problemes = verifier_table()
        self.assertTrue(any("ARBUSDT" in p and "source" in p
                            for p in problemes), problemes)

    def test_une_entree_hors_bornes_est_un_defaut(self):
        import unittest.mock as m
        import scripts.costs as C
        faux = {"defaut_rt_pct": 0.28,
                "par_symbole": {"X": {"rt_pct": 99.0,
                                      "source": "mesure"}}}
        with m.patch.object(C, "_table", return_value=faux):
            problemes = verifier_table()
        self.assertTrue(any("X" in p for p in problemes), problemes)


if __name__ == "__main__":
    unittest.main()
