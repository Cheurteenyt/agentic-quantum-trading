#!/usr/bin/env python3
"""F-038 — la marge de maintenance vient du maintMarginPercent par symbole.

(« RÉEL » au sens : lu dans exchangeInfo / liq_params, PAS une constante
codée en dur. La nuance #212 est ailleurs : c'est le taux du PREMIER palier,
pas le taux effectif d'une position à fort notionnel — voir la classe
TestApproximationPremierPalier.)

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

from scripts import portfolio_sim as ps  # noqa: E402
from scripts.portfolio_sim import (  # noqa: E402
    lev_capped, liq_move_for, liq_params)

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]


class TestLiqParamsSource(unittest.TestCase):
    def test_la_table_est_lue(self):
        if not liq_params():
            self.skipTest("liq_params vide (pas de DB en CI) — "
                          "le repli MAINT_PCT s'applique")
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
        """La formule reste exacte — pour les symboles VIABLES.

        F-047 borne les distances négatives à 0 (« liquidé à l'entrée ») :
        un symbole dont la marge exige à elle seule plus que le notionnel
        n'a pas de distance de mort, il meurt au démarrage. Le bornage a
        son propre test (tests/test_p1_liq_fallback.py).

        HERMÉTIQUE — la table est injectée. La version précédente lisait
        `liq_params()` du warehouse, absent en CI (`data/` est git-ignoré) :
        la boucle ne tournait pas, et mon garde `trouve > 0` a fait
        échouer la CI en « aucun couple viable ». Un test qui ne mesure
        rien parce qu'il n'a pas de données doit le dire, pas passer.
        """
        marge = ps._LIQ_PARAMS
        ps._LIQ_PARAMS = {"BTCUSDT": (2.5, 20.0), "ASTERUSDT": (12.5, 4.0),
                          "MEMEUSDT": (16.66, 5.0), "PIREUSDT": (25.0, 2.0)}
        try:
            for lev in (3, 5, 10, 20):
                for sym, (mm, _mx) in ps._LIQ_PARAMS.items():
                    attendu = 100.0 / lev - mm
                    if attendu <= 0:
                        continue
                    self.assertAlmostEqual(liq_move_for(sym, lev), attendu,
                                           msg=f"{sym} a {lev}x")
        finally:
            ps._LIQ_PARAMS = marge

    def test_lev_10x_sur_majeures_7_5_pas_9_5(self):
        for sym in MAJORS:
            if sym not in liq_params():
                self.skipTest(f"{sym} absent")
            self.assertAlmostEqual(liq_move_for(sym, 10), 7.5, msg=sym)

    def test_un_symbole_inconnu_replie_sur_le_maint_le_plus_haut(self):
        """F-047 — le repli est PRUDENT, dans le sens qui ne flatte pas.

        `distance = 100/L − mm` : un `mm` PLUS ÉLEVÉ donne une distance de
        mort PLUS COURTE, donc liquident plus tôt. Le repli doit donc
        prendre la marge la plus haute de la table, jamais la plus basse.

        Le test d'origine affirmait le repli plat sur `MAINT_PCT` (2,5 %) —
        la valeur des majeures, fausse pour ASTER (12,5 %), les memecoins
        (16,66 %) et le pire symbole (25 %). Sur ces trois cas, 2,5 % donne
        une distance de mort SURESTIMÉE : le backtest faisait survivre des
        trades qui auraient été liquidés.

        Noter l'incohérence du commentaire d'origine, qui disait « un
        repli trop-bas rend le moteur optimiste » puis prenait le maint le
        plus bas. Le raisonnement était juste, la conclusion inversée.
        """
        table = liq_params()
        if not table:
            self.skipTest("liq_params vide")
        attendu = max(mm for mm, _ in table.values())
        # borné à 0 : si la marge prudente dépasse 100/L, le symbole est
        # liquidé à l'entrée (cf. issue #202 et test_p1_liq_fallback.py)
        self.assertAlmostEqual(
            liq_move_for("ZZZ_NOT_A_SYMBOL", 10),
            max(0.0, 100.0 / 10 - attendu))

    def test_le_repli_est_le_plus_haut_maint_connu(self):
        """Le repli doit être CONSERVATEUR — et « conservateur » veut dire
        « marge la plus HAUTE », pas la plus basse.

        `distance = 100/L − mm` : plus `mm` est grand, plus la mort est
        proche. Le symbole le plus risqué de la table définit donc le
        repli. Prendre le plus BAS `mm` donnerait à un symbole inconnu la
        meilleure protection de l'univers — l'inverse de prudent.

        Ce test échouait avant F-047 avec un commentaire qui concluait
        l'inverse de son propre raisonnement.
        """
        table = liq_params()
        if not table:
            self.skipTest("liq_params vide")
        symbole_inconnu = "ZZZ_NOT_A_SYMBOL"
        for sym, (mm, _mx) in table.items():
            with self.subTest(symbole=sym):
                self.assertLessEqual(
                    liq_move_for(symbole_inconnu, 10), liq_move_for(sym, 10) + 1e-9,
                    f"le repli est plus large que le risque de {sym} "
                    f"(maint {mm} %) : il est optimiste")


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

    def test_un_symbole_sans_max_leverage_est_plafonne(self):
        """F-047 — un symbole INCONNU n'était pas plafonné du tout.

        `.get(symbol, (MAINT_PCT, 0.0))[1]` rendait 0, et `if mx > 0
        else lev` renvoyait le levier demandé inchangé : on simulait un
        ordre que l'échange refuse peut-être. Le plafond prudent est le
        plus BAS max_leverage de la table.

        Mesuré : 8 symboles de l'univers 1h (586) n'ont aucune ligne dans
        `liq_params`.
        """
        table = liq_params()
        if not table:
            self.skipTest("liq_params vide")
        prudent = min(mx for _, mx in table.values() if mx and mx > 0)
        self.assertAlmostEqual(lev_capped("ZZZ_NOT_A_SYMBOL", 3),
                               min(3.0, prudent))


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


    def test_lev_nul_ou_negatif_ne_crase_pas(self):
        """BUG fuzz 2026-10-10 : liq_move_for(sym, 0) levait ZeroDivisionError
        (100.0/lev sans garde), tuant un run sur un spec mal formé (lev: 0 /
        négatif, écrit à la main). Un levier non positif n'a aucun sens
        physique : on borne à 0 (« liquidé à l'entrée ») et on compte
        (LIQ_NON_VIABLE), comme le cas distance <= 0 de #202."""
        from scripts.portfolio_sim import liq_move_for
        for lev in (0, 0.0, -1, -20):
            self.assertEqual(liq_move_for("BTCUSDT", lev), 0.0,
                             f"lev={lev} doit borner à 0, pas crasher")

    def test_lev_positif_inchange(self):
        """Le fix ne doit PAS altérer les leviers valides."""
        from scripts.portfolio_sim import liq_move_for
        self.assertGreater(liq_move_for("BTCUSDT", 10), 0.0)


class TestApproximationPremierPalier(unittest.TestCase):
    """Issue #212 (P1 §27) — le modèle est une approximation au 1er PALIER.

    `liq_move_for` utilise `maintMarginPercent` d'`exchangeInfo`, qui décrit
    le PREMIER bracket de notionnel. Aster liquide par paliers
    (`leverageBrackets`, avec `cum`) : au-delà du 1er, la marge requise monte,
    donc la liquidation réelle arrive PLUS TÔT — le biais est OPTIMISTE à fort
    notionnel. Les paliers sont hors de portée (endpoint SIGNÉ, -1102 sans clé
    API wallet).

    Ce qu'on peut verrouiller sans la donnée :
      1. la docstring DIT l'approximation (sinon un lecteur croit à l'exactitude) ;
      2. on n'appelle plus le chiffre « la valeur réelle » ;
      3. à FAIBLE notionnel, `liq_move_for` coïncide avec le 1er palier — c'est
         l'acceptance (3) de l'issue, vérifiable sur la formule elle-même.
    """

    def test_la_docstring_declare_l_approximation(self):
        import scripts.portfolio_sim as ps
        doc = ps.liq_move_for.__doc__ or ""
        self.assertIn("1er PALIER", doc,
                      "la docstring doit dire l'approximation #212")
        self.assertIn("leverageBrackets", doc,
                      "la docstring doit nommer la donnée manquante")
        self.assertIn("SIGNÉ", doc,
                      "la docstring doit dire POURQUOI la donnée manque")

    def test_on_ne_pretend_plus_a_la_valeur_reelle(self):
        """Le mot exact qui rendait la lecture trompeuse (« la valeur réelle »)
        ne doit pas revenir dans la docstring.

        On pin le MOTIF D'OVERCLAIM (« la valeur réelle »), pas le mot isolé
        « réelle » : la docstring d'en-tête du module dit légitimement
        « donné publique, réelle ». Vérifier le mot seul ferait échouer un
        texte honnête — c'est le sens du syntagme qui ment, pas le qualificatif.
        """
        import scripts.portfolio_sim as ps
        doc = ps.liq_move_for.__doc__ or ""
        self.assertNotIn("la valeur réelle", doc)
        self.assertNotIn("valeur exacte", doc)

    def test_le_registre_porte_la_limite(self):
        """`docs/20` est le fichier que lit l'agent : la limite doit y être."""
        reg = (ROOT / "docs" / "20-registre-indicateurs.md").read_text(encoding="utf-8")
        self.assertIn("#212", reg)
        self.assertIn("1er palier", reg)

    def test_a_faible_notionnel_la_formule_est_le_1er_palier(self):
        """Acceptance (3) de #212 : à faible notionnel, `liq_move_for` DOIT
        coïncider avec le 1er bracket — les deux ne peuvent diverger que par
        les paliers supérieurs, absents ici. On le prouve sur la formule :
        seuil = 100/lev − maint_1er_bracket, exactement."""
        from scripts.portfolio_sim import liq_move_for
        memo, fb = ps._LIQ_PARAMS, ps.LIQ_FALLBACK_COUNT
        try:
            ps._LIQ_PARAMS = {"BTCUSDT": (2.5, 20.0), "PIREUSDT": (25.0, 2.0)}
            ps.LIQ_FALLBACK_COUNT = 0
            for lev in (1, 2, 4, 10, 20):
                attendu = 100.0 / lev - 2.5
                if attendu <= 0:
                    self.assertEqual(liq_move_for("BTCUSDT", lev), 0.0)
                else:
                    self.assertAlmostEqual(liq_move_for("BTCUSDT", lev), attendu,
                                           places=9)
            self.assertAlmostEqual(liq_move_for("BTCUSDT", 10), 7.5)
        finally:
            ps._LIQ_PARAMS, ps.LIQ_FALLBACK_COUNT = memo, fb


if __name__ == "__main__":
    unittest.main()