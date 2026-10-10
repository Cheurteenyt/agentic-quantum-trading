"""Issue #271 — wallet_analyzer : liquidité INCONNUE ≠ liquidité NULLE.

Le défaut : `_is_plausible_wallet_value` faisait `float(liquidity_usd or 0)`.
Un `liquidity_usd=None` (DexScreener muet, ou aucun pair) devenait `0.0`, la
branche `liquidity > 0` était sautée, et le `return True` final lisait
« plausible ». Mesure d'origine : `_is_plausible_wallet_value(1_000_000, None)`
rendait **True** — une position à 1 M$ sans liquidité connue passait le
contrôle de plausibilité, en silence.

Correction : trois verdicts (True / False / None), et l'appelant traite None
comme une raison de DÉGRADER, pas de valider. Ces tests verrouillent les deux :
le verdict tri-état ET la dégradation côté appelant.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import services.wallet_analyzer as wa  # noqa: E402


class PlausibleValueThreeStateTests(unittest.TestCase):
    """Le cœur du correctif : None est un verdict, pas un zéro."""

    def test_liquidite_inconnue_n_est_pas_plausible(self) -> None:
        # Le cas exact de l'issue. Avant : True. Maintenant : None (indécidable).
        self.assertIsNone(wa._is_plausible_wallet_value(1_000_000, None))

    def test_liquidite_inconnue_petite_valeur_aussi_indecidable(self) -> None:
        # Ce n'est pas une histoire de montant : sans liquidité, RIEN n'est
        # décidable, même 100 $.
        self.assertIsNone(wa._is_plausible_wallet_value(100, None))

    def test_liquidite_zero_reelle_reste_plausible(self) -> None:
        # 0 = le token est réellement illiquide, et on le SAIT. Ce cas garde
        # son verdict d'origine (True). C'est précisément ce que None ne doit
        # PAS devenir : les deux états ne doivent plus être confondus.
        self.assertTrue(wa._is_plausible_wallet_value(100, 0))
        self.assertTrue(wa._is_plausible_wallet_value(100, 0.0))

    def test_valeur_depassant_la_liquidite_reste_fausse(self) -> None:
        # Non-régression : le plafond valeur/liquidité fonctionne toujours.
        liq = 1_000.0
        trop = liq * wa._MAX_VALUE_TO_LIQUIDITY_RATIO + 1
        self.assertFalse(wa._is_plausible_wallet_value(trop, liq))
        self.assertTrue(wa._is_plausible_wallet_value(liq, liq))

    def test_valeur_absurde_ou_non_positive_fausse(self) -> None:
        self.assertFalse(wa._is_plausible_wallet_value(0, 5_000))
        self.assertFalse(wa._is_plausible_wallet_value(-1, 5_000))
        self.assertFalse(wa._is_plausible_wallet_value(1e12, 5_000))
        self.assertFalse(wa._is_plausible_wallet_value("abc", 5_000))

    def test_liquidite_non_numerique_indecidable_pas_plausible(self) -> None:
        # Une liquidité illisible est une liquidité inconnue, pas un feu vert.
        self.assertIsNone(wa._is_plausible_wallet_value(1_000, "n/a"))
        self.assertIsNone(wa._is_plausible_wallet_value(1_000, -5))


class DexScreenerApiErrorTests(unittest.TestCase):
    """Ligne 431 : une API muette renvoyait {} — indistinguable de « pas de pair »."""

    def test_api_en_echec_marque_liquidite_inconnue(self) -> None:
        def boom(*_a, **_k):
            raise OSError("réseau mort")

        with mock.patch.object(wa.urllib.request, "urlopen", boom):
            wa._DEX_CACHE.clear()
            data = wa._get_dexscreener_data("0xdead", "bsc")
        # L'information est préservée : la liquidité est INCONNUE (None), pas
        # nulle. C'est ce qui permet à l'appelant de dégrader au lieu de valider.
        self.assertIsNone(data.get("liquidity_usd"))
        self.assertTrue(data.get("api_error"))
        self.assertEqual(data.get("confidence"), "low")
        self.assertIn("api_error", data.get("checks") or [])

    def test_api_muette_et_pas_de_pair_sont_distinguables(self) -> None:
        """Les deux causes produisent désormais des blocs DIFFÉRENTS."""
        def boom(*_a, **_k):
            raise OSError("réseau mort")

        with mock.patch.object(wa.urllib.request, "urlopen", boom):
            wa._DEX_CACHE.clear()
            api_down = wa._get_dexscreener_data("0xaaa", "bsc")

        # Réponse valide mais vide = « pas de pair » (0 liquide, pas api_error).
        class _Resp:
            def read(self):
                return b"[]"

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

        with mock.patch.object(wa.urllib.request, "urlopen", lambda *_a, **_k: _Resp()):
            wa._DEX_CACHE.clear()
            no_pair = wa._get_dexscreener_data("0xbbb", "bsc")

        self.assertNotEqual(api_down, no_pair)
        self.assertTrue(api_down.get("api_error"))
        self.assertFalse(no_pair.get("api_error", False))
        self.assertEqual(no_pair.get("liquidity_usd"), 0)  # zéro CONNU


if __name__ == "__main__":
    unittest.main()
