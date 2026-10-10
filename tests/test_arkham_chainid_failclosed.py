#!/usr/bin/env python3
"""Fail-closed chain-id — un lookup hors map ne doit JAMAIS retomber sur
Ethereum mainnet en silence.

Bug fondateur (mesuré à l'exécution le 2026-10-10) :
`ETHERSCAN_CHAIN_IDS.get(chain, "1")` dans `_fetch_blockchain_data` —
la map n'avait ni la clé `base` ni `eth`. Un appel `chain='base'` envoyait
`chainid=1` (mainnet Ethereum) et renvoyait un solde plausible mais FAUX
tagué `chain='base'`. Pire : le router `arkham_lookup` accepte une chaîne
arbitraire (`Query`), et rien ne normalisait en amont. Une donnée de la
mauvaise blockchain, indétectable en aval.

Le correctif : `base` et `eth` ajoutés à la map, ET une sentinelle
`_CHAIN_NON_SUPPORTEE` fait sortir une ERREUR pour toute chaîne hors map
au lieu du défaut muet "1". Ce test verrouille les deux.

Ces tests ne touchent PAS le réseau : ils vérifient le garde AVANT tout
appel HTTP (une chaîne inconnue sort avant même de construire l'URL).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.arkham_scraper import (  # noqa: E402
    ETHERSCAN_CHAIN_IDS,
    _CHAIN_NON_SUPPORTEE,
    ArkhamScraper,
)


class TestChainIdMapComplete(unittest.TestCase):
    """La map doit couvrir toutes les chaînes que l'API annonce accepter."""

    def test_base_present(self):
        """Le bug fondateur : `base` manquait -> requête mainnet Ethereum."""
        self.assertIn("base", ETHERSCAN_CHAIN_IDS,
                      "sans 'base', un appel chain='base' retombait sur "
                      "le défaut Ethereum mainnet (bug silencieux)")
        self.assertEqual(ETHERSCAN_CHAIN_IDS["base"], "8453")

    def test_eth_alias_present(self):
        """`eth` doit résoudre explicitement, pas par un défaut implicite."""
        self.assertIn("eth", ETHERSCAN_CHAIN_IDS)
        self.assertEqual(ETHERSCAN_CHAIN_IDS["eth"], "1")

    def test_chaine_documentee_du_router_toutes_mappees(self):
        """Les chaînes que le router arkham_lookup documente dans son
        Query doivent toutes résoudre — sinon l'API ment à l'appelant."""
        # reprises de la description Query de arkham.py:3743
        for chain in ("ethereum", "bsc", "arbitrum", "polygon"):
            self.assertIn(chain, ETHERSCAN_CHAIN_IDS,
                          f"chaîne documentée par l'API mais hors map: {chain}")


class TestFailClosed(unittest.TestCase):
    """Une chaîne hors map sort une ERREUR, jamais une donnée fausse."""

    def _scr(self):
        return ArkhamScraper()

    def test_chaine_inconnue_retourne_erreur_pas_donnee(self):
        """Le garde fail-closed : avant tout appel HTTP, une chaîne
        inconnue renvoie {error: etherscan_chain_not_supported:...}."""
        scraper = self._scr()
        res = scraper._fetch_blockchain_data("0xdeadbeef", "chaine-bidonnée")
        self.assertIn("error", res,
                      "une chaîne inconnue DOIT sortir une erreur")
        self.assertTrue(
            res["error"].startswith("etherscan_chain_not_supported"),
            f"erreur inattendue: {res.get('error')}")
        # surtout: pas de balance inventée depuis la mauvaise blockchain
        self.assertIsNone(res.get("balance_wei"),
                          "ne JAMAIS renvoyer une balance pour une chaîne "
                          "non supportée")

    def test_sentinelle_distincte_de_none(self):
        """La sentinelle doit être un objet unique, pas None (None serait
        une valeur de dict valide et le garde `is None` serait un faux
        négatif)."""
        self.assertIsNot(_CHAIN_NON_SUPPORTEE, None)
        self.assertNotIn(_CHAIN_NON_SUPPORTEE, ETHERSCAN_CHAIN_IDS.values())


if __name__ == "__main__":
    unittest.main()
