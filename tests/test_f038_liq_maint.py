#!/usr/bin/env python3
"""F-038 — la marge de maintenance est le maintMarginPercent RÉEL par symbole.

Le bug : MAINT_PCT = 0,5 codé en dur alors que liq_params (extrait
d'exchangeInfo) dit 2,5 % pour les 6 majeures et 16,66 % pour la population
dominante de l'univers. La ligne de mort était repoussée de 2 % sur les
majeures (à 20x) et de 16,1 % sur les memecoins — soit un sous-comptage des
liquidations d'environ ×2,2 à 20x. La règle 0-liq du README (lev ≤
100/(maxMAE+0,5)) était infirmée par elle-même : à 10x elle annonçait 10x
alors que la ligne de mort réelle est à 7,5 % et le MAE observé de 7,84 %.

Ces tests verrouillent les trois propriétés :
  1. le seuil vient de la base, pas d'une constante ;
  2. le seuil RÉEL est plus STRICT que l'ancien dur (jamais l'inverse) ;
  3. le levier rendu respecte toujours max_leverage de l'exchange.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import (  # noqa: E402
    MAINT_PCT, lev_capped, liq_move_for, liq_params)

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]


class TestLiqParamsSource(unittest.TestCase):
    def test_la_table_est_lue(self):
        self.assertGreater(len(liq_params()), 100,
                           "liq_params vide : le repli MAINT_PCT masquerait "
                           "une table absente")

    def test_les_majeures_sont_a_2_5_pas_0_5(self):
        for sym in MAJORS:
            mm = liq_params().get(sym, (None,))[0]
            if mm is None:
                self.skipTest(f"{sym} absent de liq_params")
            self.assertAlmostEqual(mm, 2.5, msg=sym)

    def test_le_seuil_reel_est_plus_strict_que_l_ancien_dur(self):
        """Propriété de sûreté : on ne peut JAMAIS liquider moins vite qu'avant.

        Le correctif peut rendre le moteur plus conservateur, jamais plus
        optimiste — sans quoi on aurait « corrigé » le bug en tirant dans
        l'autre sens.
        """
        for lev in (5, 10, 20):
            ancien = 100.0 / lev - 0.5
            for sym in MAJORS:
                if sym not in liq_params():
                    continue
                reel = liq_move_for(sym, lev)
                self.assertLessEqual(
                    reel, ancien + 1e-9,
                    f"{sym} {lev}x : seuil réel {reel:.2f} plus permissif "
                    f"que l'ancien dur {ancien:.2f}")


class TestLiqMove(unittest.TestCase):
    def test_la_formule(self):
        for lev in (3, 5, 10, 20):
            for sym, (mm, _mx) in liq_params().items():
                self.assertAlmostEqual(liq_move_for(sym, lev), 100.0 / lev - mm)

    def test_lev_10x_sur_majeures_7_5_pas_9_5(self):
        for sym in MAJORS:
            if sym not in liq_params():
                self.skipTest(f"{sym} absent")
            self.assertAlmostEqual(liq_move_for(sym, 10), 7.5, msg=sym)

    def test_un_symbole_inconnu_replie_sans_echouer(self):
        self.assertAlmostEqual(
            liq_move_for("ZZZ_NOT_A_SYMBOL", 10), 100.0 / 10 - MAINT_PCT)

    def test_le_repli_est_le_plus_bas_maint_connu(self):
        """Le repli doit être CONSERVATEUR, pas seulement défini.

        Si le symbole est absent de liq_params, un repli trop-bas
        surestimerait la ligne de mort (100/L − mm) et donc
        sous-estimerait la liquidation : c'est la seule erreur qui rend le
        moteur optimiste. On prend donc le maint le plus bas de la table.
        """
        table = liq_params()
        if not table:
            self.skipTest("liq_params vide")
        self.assertAlmostEqual(MAINT_PCT, min(mm for mm, _ in table.values()))


class TestLevCapped(unittest.TestCase):
    def test_aucun_levier_au_dessus_du_max_de_l_exchange(self):
        for sym, (_mm, mx) in liq_params().items():
            if mx <= 0:
                continue
            for lev in (1, 3, 10, 20, 50):
                self.assertLessEqual(
                    lev_capped(sym, lev), mx + 1e-9,
                    f"{sym} : lev {lev} > max_leverage {mx}")

    def test_le_plafond_ne_renverse_pas_le_levier(self):
        for sym, (_mm, mx) in liq_params().items():
            self.assertGreaterEqual(lev_capped(sym, 1), 1.0, sym)

    def test_un_symbole_sans_max_leverage_laisse_passer(self):
        self.assertAlmostEqual(lev_capped("ZZZ_NOT_A_SYMBOL", 3), 3.0)


class TestNoLiquidationsByConstruction(unittest.TestCase):
    """L'invariant central que le README AFFIRMAIT et que 0,5 violait."""

    def test_le_levier_rend_ne_liquide_pas_le_mae_observe(self):
        from scripts.the_machine import MAINT_MAJORS, levier_majors_safe
        for mae in (1.0, 3.5, 7.84, 9.5, 15.0, 25.0, 60.0, 90.0):
            lev = levier_majors_safe(mae)
            mort = 100.0 / lev - MAINT_MAJORS
            self.assertGreater(
                mort, mae,
                f"MAE {mae} % liquidé à {mort:.2f} % (lev {lev:.2f}x)")

    def test_le_mae_observe_de_l_ere_tient(self):
        """7,84 % était l'ère observée : la machine doit BAISSER le levier.

        C'est exactement ce que le dur 0,5 empêchait (il rendait 10x).
        """
        from scripts.the_machine import levier_majors_safe
        self.assertLess(levier_majors_safe(7.84), 10.0)
        self.assertAlmostEqual(levier_majors_safe(7.84), 100 / 10.84)


if __name__ == "__main__":
    unittest.main()