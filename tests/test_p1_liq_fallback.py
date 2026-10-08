#!/usr/bin/env python3
"""P1 (audit 2026-10-08 §27) — le repli de marge de maintenance était
OPTIMISTE, et il rendait le modèle flatteur.

`liq_move_for` retombait sur `MAINT_PCT = 2,5` pour tout symbole absent de
`liq_params`. C'est la valeur RÉELLE de BTC/ETH/BNB, et elle est fausse
pour presque tout le reste :

    ASTERUSDT   12,5 %  → repli 2,5 % : 10 points trop optimiste
    memecoins    16,66 % → repli 2,5 % : 14 points trop optimiste
    pire        25,0 %  → repli 2,5 % : 22,5 points trop optimiste

`distance = 100/L − mm` : une marge sous-estimée donne une distance de mort
SURESTIMÉE, donc des trades qui « survivent » au backtest et qui se
seraient liquidés. Le biais va dans la direction flatteuse — la pire
possible pour un modèle de risque.

Le défaut miroir est dans `lev_capped` : un symbole ABSENT n'était pas
plafonné du tout (`.get(symbol, (..., 0.0))[1]` → 0 → `if mx > 0 else lev`).
On simulait donc des ordres que l'échange refuse.

Mesuré sur le warehouse de prod : **8 symboles de l'univers 1h (586)**
n'ont aucune ligne dans `liq_params`. Ce n'est pas théorique.

Ces tests sont HERMÉTIQUES : ils patchent `liq_params` avec un jeu de
marges connu, sans base.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import portfolio_sim as ps  # noqa: E402


# marges réelles mesurées sur exchangeInfo (prod) : les majeures à 2,5,
# ASTER à 12,5, les memecoins à 16,66, le pire symbole à 25.
MARGES = {
    "BTCUSDT": (2.5, 20.0),
    "ETHUSDT": (2.5, 20.0),
    "ASTERUSDT": (12.5, 4.0),
    "MEMEUSDT": (16.66, 5.0),
    "PIREUSDT": (25.0, 2.0),
}


class _FauxParams:
    """Remplace la lecture de la table par un jeu connu, et restaure tout."""

    def __enter__(self):
        self._memo = ps._LIQ_PARAMS
        self._fb = ps.LIQ_FALLBACK_COUNT
        self._nv = ps.LIQ_NON_VIABLE
        ps._LIQ_PARAMS = dict(MARGES)
        ps.LIQ_FALLBACK_COUNT = 0
        ps.LIQ_NON_VIABLE = 0
        return self

    def __exit__(self, *exc):
        ps._LIQ_PARAMS = self._memo
        ps.LIQ_FALLBACK_COUNT = self._fb
        ps.LIQ_NON_VIABLE = self._nv
        return False


class TestRepliPrudent(unittest.TestCase):
    def setUp(self):
        self._ctx = _FauxParams()
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__()

    def test_la_marge_prudente_est_la_plus_haute(self):
        self.assertEqual(ps._maint_prudent(), 25.0)
        self.assertEqual(ps._lev_prudent(), 2.0)

    def test_un_symbole_absent_est_plus_risque_que_tous_les_connus(self):
        """La propriété qui compte : jamais plus sûr qu'un symbole connu.

        C'est l'inverse exact du bug : l'ancien repli donnait à
        SCRUSDT 7,5 % de distance de mort à 10x, soit la MÊME que BTC
        (2,5 % de marge). Un flux à 25 % de marge se voyait accorder la
        même protection qu'une majeure.
        """
        inconnu = ps.liq_move_for("INCONNUUSDT", 10)
        for symbole, (mm, _) in MARGES.items():
            with self.subTest(connu=symbole):
                connu = ps.liq_move_for(symbole, 10)
                self.assertLessEqual(
                    inconnu, connu,
                    f"le repli ({inconnu:.3f}) est plus large que le risque "
                    f"réel de {symbole} ({connu:.3f}) — le repli est optimiste")

    def test_un_symbole_absent_compte_le_repli(self):
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 0)
        ps.liq_move_for("INCONNUUSDT", 10)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 1,
                         "un calcul sur marge substituée doit être visible")
        ps.liq_move_for("BTCUSDT", 10)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 1,
                         "un symbole CONNU ne doit pas incrémenter le compteur")

    def test_un_symbole_absent_est_plafonne(self):
        """Le défaut miroir : avant, aucun plafond n'était appliqué."""
        self.assertEqual(ps.lev_capped("INCONNUUSDT", 20), 2.0)
        self.assertEqual(ps.lev_capped("BTCUSDT", 20), 20.0,
                         "un symbole connu garde son vrai max_leverage")
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 1)

    def test_les_marges_reelles_sont_inchangees(self):
        """Le correctif ne doit toucher QUE le cas absent."""
        self.assertAlmostEqual(ps.liq_move_for("BTCUSDT", 10), 7.5)
        self.assertAlmostEqual(ps.liq_move_for("BTCUSDT", 20), 2.5)
        self.assertAlmostEqual(ps.liq_move_for("ASTERUSDT", 4), 100 / 4 - 12.5)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 0)


class TestLevierNonViable(unittest.TestCase):
    """Issue #202 (C-B4) — `liq_move_for` pouvait renvoyer une valeur
    NÉGATIVE. Le repli prudent rend le cas réel : un symbole à 25 % de
    marge est liquidé dès l'entrée à 10x."""

    def setUp(self):
        self._ctx = _FauxParams()
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__()

    def test_distance_negative_bornee_a_zero(self):
        """100/10 − 25 = −15 : ce n'est pas une distance, c'est une absence.

        Le borner à 0 signifie exactement « liquidé à l'entrée », ce qui
        est la bonne traduction physique. Retourner −15 ferait croire à une
        mesure.
        """
        self.assertEqual(ps.liq_move_for("PIREUSDT", 10), 0.0)
        self.assertEqual(ps.LIQ_NON_VIABLE, 1)

    def test_le_bornage_est_compte_separement_du_repli(self):
        """Les deux compteurs décrivent deux situations distinctes.

        - symbole CONNU dont le levier demandé n'est pas viable : le
          budget est connu, la demande est excessive.
        - symbole INCONNU à un levier viable : la marge est substituée,
          mais la demande tient.

        L'inverse de mon premier essai de test : à 10x, un symbole
        inconnu ET un symbole connu à 25 % de marge sont tous deux non
        viables (100/10 − 25 = −15), donc les deux compteurs bougaient et
        le test ne distinguait rien. Le levier viable rend la distinction
        observable.
        """
        ps.liq_move_for("PIREUSDT", 10)      # connu, levier excessif
        self.assertEqual(ps.LIQ_NON_VIABLE, 1)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 0,
                         "un symbole connu n'est PAS un repli de marge")

        ps.liq_move_for("INCONNUUSDT", 2)    # inconnu, levier viable
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 1)
        self.assertEqual(ps.LIQ_NON_VIABLE, 1,
                         "à 2x le repli prudent (25 %) laisse 25 % de marge : "
                         "viable, donc pas de bornage")

    def test_un_symbole_inconnu_a_10x_est_liquide_a_l_entree(self):
        """Comportement ÉMERGENT du repli prudent — il est voulu, donc figé.

        Le repli prend la marge la plus haute observée (25 %). À 10x,
        100/10 = 10 < 25 : la marge de maintenance exige à elle seule plus
        que le notionnel, donc la position meurt à l'entrée. C'est le
        modèle PRUDENT qui le dit, là où l'ancien repli plat 2,5 % aurait
        fait apparaître un trade confortable à 7,5 % de distance.

        Ce n'est pas une surprise : `lev_capped` ramène ces symboles à 2x
        avant qu'ils n'atteignent 10x dans le flux réel. Le test le dit
        pour que la lecture du nombre ne soit pas un choc.
        """
        self.assertEqual(ps.liq_move_for("INCONNUUSDT", 10), 0.0)
        self.assertEqual(ps.LIQ_NON_VIABLE, 1)
        self.assertEqual(ps.lev_capped("INCONNUUSDT", 20), 2.0)

    def test_un_levier_viable_nest_pas_borne(self):
        self.assertGreater(ps.liq_move_for("PIREUSDT", 2), 0.0)
        self.assertGreater(ps.liq_move_for("MEMEUSDT", 4), 0.0)
        self.assertEqual(ps.LIQ_NON_VIABLE, 0)

    def test_le_vrai_max_leverage_evite_la_situation(self):
        """`lev_capped` doit rendre le levier viable : 25 % de marge exige
        100/25 = 4x de notionnel au maximum."""
        lev_reel = ps.lev_capped("PIREUSDT", 20)
        self.assertEqual(lev_reel, 2.0)
        self.assertGreater(ps.liq_move_for("PIREUSDT", lev_reel), 0.0,
                           "le levier plafonné par le symbole doit rester "
                           "viable — sinon on simule des liquidations à "
                           "l'entrée sur des ordres valides")


class TestSurUneTableVide(unittest.TestCase):
    """Base absente : on ne prétend pas avoir une lecture de l'univers."""

    def setUp(self):
        self._memo = ps._LIQ_PARAMS
        self._fb = ps.LIQ_FALLBACK_COUNT
        ps._LIQ_PARAMS = {}
        ps.LIQ_FALLBACK_COUNT = 0

    def tearDown(self):
        ps._LIQ_PARAMS = self._memo
        ps.LIQ_FALLBACK_COUNT = self._fb

    def test_repli_sur_la_constante_mais_compte(self):
        self.assertEqual(ps._maint_prudent(), ps.MAINT_PCT)
        self.assertEqual(ps._lev_prudent(), 1.0,
                         "sans table, on ne suppose pas qu'un levier est "
                         "autorisé")
        ps.liq_move_for("BTCUSDT", 10)
        self.assertEqual(ps.LIQ_FALLBACK_COUNT, 1,
                         "sur une base absente, CHAQUE trade est un repli : "
                         "le compteur le rend visible dans le rapport")


if __name__ == "__main__":
    unittest.main()